"""Config flow and entities in a running Home Assistant, network mocked."""

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.tarif_electricite_fr.const import (
    CRE_URLS,
    DOMAIN,
    EDF_GRID_URL,
    RTE_TEMPO_URL,
)
from custom_components.tarif_electricite_fr.prices import parse_edf_tables

from .conftest import cre_text, edf_page

PARIS = ZoneInfo("Europe/Paris")


def _edf_grid(_content: bytes):
    page = edf_page()
    return parse_edf_tables(page["text"], page["tables"])


@pytest.fixture
def network(aioclient_mock: AiohttpClientMocker):
    for option, url in CRE_URLS.items():
        aioclient_mock.get(url, text=cre_text(option), headers={"Last-Modified": "x"})
    aioclient_mock.get(EDF_GRID_URL, content=b"%PDF-")
    aioclient_mock.get(
        RTE_TEMPO_URL,
        json={
            "values": {"2026-12-01": "RED", "2026-12-02": "WHITE", "2026-12-02-fallback": "false"}
        },
    )
    aioclient_mock.get(
        RTE_TEMPO_URL.replace("tempoLight", "tempo"),
        json={"values": {"2026-11-30": "BLUE", "2026-12-01": "RED"}},
    )
    with patch("custom_components.tarif_electricite_fr.coordinator.parse_edf_pdf", _edf_grid):
        yield aioclient_mock


async def _setup(hass: HomeAssistant, data: dict, options: dict | None = None) -> MockConfigEntry:
    await hass.config.async_set_time_zone("Europe/Paris")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=data,
        options=options or {},
        unique_id=f"{data['option']}_{data['power']}",
        title="test",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_flow_hphc(hass: HomeAssistant, network) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"option": "hphc"})
    assert result["step_id"] == "power"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"power": "9", "offpeak_hours": "25:00-06:00"}
    )
    assert result["errors"] == {"offpeak_hours": "invalid_offpeak"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"power": "9", "offpeak_hours": "01:30-07:30, 12:30-14:30"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"option": "hphc", "power": 9}
    assert result["options"] == {"offpeak_hours": "01:30-07:30, 12:30-14:30"}
    assert result["title"] == "Tarif Bleu Heures Creuses 9 kVA"


async def test_flow_duplicate_aborts(hass: HomeAssistant, network) -> None:
    await _setup(hass, {"option": "base", "power": 6})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"option": "base"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"power": "6"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_base_18_kva_comes_from_edf(
    hass: HomeAssistant, network, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(datetime(2026, 9, 19, 12, tzinfo=PARIS))
    await _setup(hass, {"option": "base", "power": 18})
    assert hass.states.get("sensor.test_price_now").state == "0.1985"
    assert hass.states.get("sensor.test_price_source").state == "edf"
    assert hass.states.get("sensor.test_monthly_subscription").state == "31.14"


async def test_hphc_switches_on_the_minute(
    hass: HomeAssistant, network, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(datetime(2026, 9, 19, 21, 59, 30, tzinfo=PARIS))
    await _setup(hass, {"option": "hphc", "power": 6}, {"offpeak_hours": "22:00-06:00"})
    assert hass.states.get("sensor.test_period_now").state == "hp"
    assert hass.states.get("sensor.test_price_now").state == "0.2142"
    assert hass.states.get("sensor.test_price_source").state == "cre"
    assert hass.states.get("sensor.test_monthly_subscription").state == "15.86"  # EDF's

    freezer.tick(40)
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_period_now").state == "hc"
    assert hass.states.get("sensor.test_price_now").state == "0.1589"


async def test_tempo_red_night(
    hass: HomeAssistant, network, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(datetime(2026, 12, 2, 3, 0, tzinfo=PARIS))
    await _setup(hass, {"option": "tempo", "power": 9})
    # 03:00 on 2 December still belongs to the red Tempo day of 1 December.
    assert hass.states.get("sensor.test_tempo_colour_today").state == "rouge"
    assert hass.states.get("sensor.test_tempo_colour_tomorrow").state == "blanc"
    assert hass.states.get("sensor.test_period_now").state == "rouge_hc"
    assert hass.states.get("sensor.test_price_now").state == "0.1615"
    assert hass.states.get("sensor.test_price_red_day_peak").state == "0.7295"


async def test_all_sources_down_keeps_last_prices(
    hass: HomeAssistant, network, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(datetime(2026, 9, 19, 12, tzinfo=PARIS))
    entry = await _setup(hass, {"option": "base", "power": 6})
    assert hass.states.get("sensor.test_price_now").state == "0.2001"

    network.clear_requests()
    for url in (*CRE_URLS.values(), EDF_GRID_URL):
        network.get(url, status=503)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.test_price_now").state == "0.2001"
    assert hass.states.get("sensor.test_prices_in_force_since").attributes["cre_reachable"] is False
