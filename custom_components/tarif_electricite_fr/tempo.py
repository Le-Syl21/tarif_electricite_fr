"""Tempo day colours, from RTE with a community API as fallback."""

from __future__ import annotations

import logging
from calendar import isleap
from datetime import date, timedelta

import aiohttp

from .const import COULEUR_TEMPO_URL, RTE_TEMPO_URL, USER_AGENT

_LOGGER = logging.getLogger(__name__)

_RTE_COLOURS = {"BLUE": "bleu", "WHITE": "blanc", "RED": "rouge"}
_CODE_COLOURS = {1: "bleu", 2: "blanc", 3: "rouge"}
_TIMEOUT = aiohttp.ClientTimeout(total=20)

# Days of each colour in a Tempo season (1 September - 31 August).
QUOTA_WHITE = 43
QUOTA_RED = 22


def season_of(day: date) -> str:
    start = day.year if day.month >= 9 else day.year - 1
    return f"{start}-{start + 1}"


def quotas(season: str) -> dict[str, int]:
    """Blue days fill the season: 365 or 366 days minus white and red ones."""
    end_year = int(season.split("-")[1])
    days = 366 if isleap(end_year) else 365
    return {"bleu": days - QUOTA_WHITE - QUOTA_RED, "blanc": QUOTA_WHITE, "rouge": QUOTA_RED}


def remaining(colours: dict[date, str], today: date) -> dict[str, int]:
    """Days of each colour left in today's season, today excluded."""
    season = season_of(today)
    left = quotas(season)
    for day, colour in colours.items():
        if season_of(day) == season and day <= today and colour in left:
            left[colour] -= 1
    return left


def _parse_rte(payload: dict) -> dict[date, str]:
    colours = {}
    for key, value in (payload.get("values") or {}).items():
        if key.endswith("-fallback") or value not in _RTE_COLOURS:
            continue
        try:
            colours[date.fromisoformat(key)] = _RTE_COLOURS[value]
        except ValueError:
            continue
    return colours


async def _get_json(session: aiohttp.ClientSession, url: str, params: dict | None = None):
    async with session.get(
        url, params=params, headers={"User-Agent": USER_AGENT}, timeout=_TIMEOUT
    ) as resp:
        resp.raise_for_status()
        return await resp.json(content_type=None)


async def fetch_recent(session: aiohttp.ClientSession, today: date) -> dict[date, str]:
    """Colours of today and, once published (around 11:00), tomorrow."""
    try:
        return _parse_rte(await _get_json(session, RTE_TEMPO_URL))
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        _LOGGER.debug("RTE Tempo colours unavailable (%s), trying the fallback", err)

    colours = {}
    for day in (today, today + timedelta(days=1)):
        try:
            data = await _get_json(session, f"{COULEUR_TEMPO_URL}/jourTempo/{day.isoformat()}")
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            _LOGGER.debug("Fallback Tempo colour for %s unavailable: %s", day, err)
            continue
        colour = _CODE_COLOURS.get(data.get("codeJour"))
        if colour:
            colours[day] = colour
    return colours


async def fetch_season(session: aiohttp.ClientSession, today: date) -> dict[date, str]:
    """Every known colour of today's season (for yesterday and the day counts)."""
    try:
        payload = await _get_json(
            session, RTE_TEMPO_URL.replace("tempoLight", "tempo"), {"season": season_of(today)}
        )
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        _LOGGER.debug("RTE Tempo season unavailable: %s", err)
        return {}
    return _parse_rte(payload)
