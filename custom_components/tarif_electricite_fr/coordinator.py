"""Fetch prices and Tempo colours, keep the last good ones across restarts."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import tempo
from .const import (
    CONF_OFFPEAK,
    CONF_OPTION,
    CONF_POWER,
    CRE_URLS,
    DEFAULT_OFFPEAK,
    DOMAIN,
    EDF_GRID_REFRESH,
    EDF_GRID_URL,
    OPTION_TEMPO,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
    USER_AGENT,
)
from .periods import current_period, parse_offpeak
from .prices import GridError, Tariff, choose, parse_cre, parse_edf_pdf

_LOGGER = logging.getLogger(__name__)
_TIMEOUT = aiohttp.ClientTimeout(total=60)
_KEEP_COLOURS = timedelta(days=400)

type TarifConfigEntry = ConfigEntry[TarifCoordinator]


@dataclass
class TarifData:
    tariff: Tariff | None
    colours: dict[date, str] = field(default_factory=dict)
    cre_ok: bool = False
    edf_ok: bool = False


class TarifCoordinator(DataUpdateCoordinator[TarifData]):
    """One coordinator per option and subscribed power."""

    config_entry: TarifConfigEntry

    def __init__(self, hass: HomeAssistant, entry: TarifConfigEntry) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=UPDATE_INTERVAL
        )
        self.option: str = entry.data[CONF_OPTION]
        self.power: int = entry.data[CONF_POWER]
        self._store: Store[dict] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._session = async_get_clientsession(hass)
        self._cre_text: str | None = None
        self._cre_modified: str | None = None
        self._edf: Tariff | None = None
        self._edf_fetched: datetime | None = None
        self._last: Tariff | None = None
        self._colours: dict[date, str] = {}
        self._season_fetched: date | None = None
        self._unsub_tick = None

    @property
    def offpeak(self):
        return parse_offpeak(self.config_entry.options.get(CONF_OFFPEAK, DEFAULT_OFFPEAK))

    def period_now(self) -> str | None:
        return current_period(self.option, dt_util.now(), self.offpeak, self._colours)

    async def async_load(self) -> None:
        """Restore what the previous run knew, so a dead source is not a blank."""
        stored = await self._store.async_load() or {}
        self._cre_text = stored.get("cre_text")
        self._cre_modified = stored.get("cre_modified")
        if edf := stored.get("edf"):
            self._edf = Tariff.from_dict(edf)
        if last := stored.get("last"):
            self._last = Tariff.from_dict(last)
        self._colours = {
            date.fromisoformat(day): colour for day, colour in stored.get("colours", {}).items()
        }
        # Periods change on the minute (HP/HC, 06:00 and 22:00 for Tempo):
        # refresh the entities then, without fetching anything.
        self._unsub_tick = async_track_time_change(self.hass, self._tick, second=0)

    @callback
    def _tick(self, _now: datetime) -> None:
        if self.data is not None:
            self.async_update_listeners()

    async def async_shutdown(self) -> None:
        if self._unsub_tick:
            self._unsub_tick()
            self._unsub_tick = None
        await super().async_shutdown()

    async def _fetch_cre(self) -> bool:
        headers = {"User-Agent": USER_AGENT}
        if self._cre_modified and self._cre_text:
            headers["If-Modified-Since"] = self._cre_modified
        try:
            async with self._session.get(
                CRE_URLS[self.option], headers=headers, timeout=_TIMEOUT
            ) as resp:
                if resp.status == 304:
                    return True
                resp.raise_for_status()
                self._cre_text = (await resp.read()).decode("utf-8-sig")
                self._cre_modified = resp.headers.get("Last-Modified")
                return True
        except (aiohttp.ClientError, TimeoutError, UnicodeDecodeError) as err:
            _LOGGER.warning("CRE prices unavailable: %s", err)
            return False

    async def _fetch_edf(self, now: datetime) -> bool:
        if self._edf_fetched and now - self._edf_fetched < EDF_GRID_REFRESH:
            return True
        try:
            async with self._session.get(
                EDF_GRID_URL, headers={"User-Agent": USER_AGENT}, timeout=_TIMEOUT
            ) as resp:
                resp.raise_for_status()
                content = await resp.read()
            grid = await self.hass.async_add_executor_job(parse_edf_pdf, content)
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.warning("EDF price grid unavailable: %s", err)
            return False
        except GridError as err:
            _LOGGER.warning("EDF price grid not understood, ignored: %s", err)
            return False
        except Exception:  # pdfplumber raises its own errors on a broken file
            _LOGGER.exception("EDF price grid could not be read")
            return False
        self._edf = grid[self.option].get(self.power)
        self._edf_fetched = now
        return True

    async def _update_colours(self, today: date) -> None:
        if self._season_fetched != today:
            if season := await tempo.fetch_season(self._session, today):
                self._colours.update(season)
                self._season_fetched = today
        if today + timedelta(days=1) not in self._colours or today not in self._colours:
            self._colours.update(await tempo.fetch_recent(self._session, today))
        oldest = today - _KEEP_COLOURS
        self._colours = {d: c for d, c in self._colours.items() if d >= oldest}

    async def _async_update_data(self) -> TarifData:
        now = dt_util.now()
        today = now.date()

        cre_ok = await self._fetch_cre()
        edf_ok = await self._fetch_edf(now)

        cre = None
        if self._cre_text:
            try:
                cre = parse_cre(self._cre_text, self.option, self.power, today)
            except GridError as err:
                _LOGGER.warning("CRE prices not understood, ignored: %s", err)
                cre_ok = False
        tariff = choose(cre, self._edf, today) or self._last

        if self.option == OPTION_TEMPO:
            await self._update_colours(today)

        if tariff is None:
            raise UpdateFailed("No price source reachable and no price known yet")
        self._last = tariff

        await self._store.async_save(
            {
                "cre_text": self._cre_text,
                "cre_modified": self._cre_modified,
                "edf": self._edf.as_dict() if self._edf else None,
                "last": tariff.as_dict(),
                "colours": {d.isoformat(): c for d, c in self._colours.items()},
            }
        )
        return TarifData(tariff=tariff, colours=dict(self._colours), cre_ok=cre_ok, edf_ok=edf_ok)
