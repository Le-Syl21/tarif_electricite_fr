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
    assert hass.states.get("sensor.prix_kwh_actuel").state == "0.1985"
    assert hass.states.get("sensor.source_des_prix").state == "edf"
    assert hass.states.get("sensor.abonnement_mensuel").state == "31.14"


async def test_hphc_switches_on_the_minute(
    hass: HomeAssistant, network, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(datetime(2026, 9, 19, 21, 59, 30, tzinfo=PARIS))
    await _setup(hass, {"option": "hphc", "power": 6}, {"offpeak_hours": "22:00-06:00"})
    assert hass.states.get("sensor.periode_actuelle").state == "hp"
    assert hass.states.get("sensor.prix_kwh_actuel").state == "0.2142"
    assert hass.states.get("sensor.source_des_prix").state == "cre"
    assert hass.states.get("sensor.abonnement_mensuel").state == "15.86"  # EDF's

    freezer.tick(40)
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.periode_actuelle").state == "hc"
    assert hass.states.get("sensor.prix_kwh_actuel").state == "0.1589"


async def test_tempo_red_night(
    hass: HomeAssistant, network, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(datetime(2026, 12, 2, 3, 0, tzinfo=PARIS))
    await _setup(hass, {"option": "tempo", "power": 9})
    # 03:00 on 2 December still belongs to the red Tempo day of 1 December.
    assert hass.states.get("sensor.couleur_du_jour").state == "rouge"
    assert hass.states.get("sensor.couleur_de_demain").state == "blanc"
    assert hass.states.get("sensor.periode_actuelle").state == "rouge_hc"
    assert hass.states.get("sensor.prix_kwh_actuel").state == "0.1615"
    assert hass.states.get("sensor.prix_kwh_rouge_hp").state == "0.7295"


async def test_all_sources_down_keeps_last_prices(
    hass: HomeAssistant, network, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(datetime(2026, 9, 19, 12, tzinfo=PARIS))
    entry = await _setup(hass, {"option": "base", "power": 6})
    assert hass.states.get("sensor.prix_kwh_actuel").state == "0.2001"

    network.clear_requests()
    for url in (*CRE_URLS.values(), EDF_GRID_URL):
        network.get(url, status=503)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.prix_kwh_actuel").state == "0.2001"
    assert hass.states.get("sensor.prix_en_vigueur_depuis").attributes["cre_reachable"] is False


async def test_red_tomorrow_heat_until_offpeak_ends(
    hass: HomeAssistant, network, freezer: FrozenDateTimeFactory
) -> None:
    # 22:30 on a Tempo day: off-peak is on, ends at 06:00, and tomorrow's
    # colour (white in the mock) is already known.
    freezer.move_to(datetime(2026, 12, 1, 22, 30, tzinfo=PARIS))
    await _setup(hass, {"option": "tempo", "power": 9})
    offpeak = hass.states.get("binary_sensor.heures_creuses")
    assert offpeak.state == "on"
    assert offpeak.attributes["next_change"] == "2026-12-02T06:00:00+01:00"
    assert hass.states.get("sensor.couleur_de_demain").state == "blanc"


async def test_offpeak_binary_hphc_and_none_for_base(
    hass: HomeAssistant, network, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(datetime(2026, 9, 19, 14, 0, tzinfo=PARIS))
    await _setup(hass, {"option": "hphc", "power": 6}, {"offpeak_hours": "1h/7h30 & 13h/14h30"})
    offpeak = hass.states.get("binary_sensor.heures_creuses")
    assert offpeak.state == "on"
    assert offpeak.attributes["next_change"] == "2026-09-19T14:30:00+02:00"

    freezer.tick(31 * 60)
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.heures_creuses").state == "off"


async def test_offpeak_binary_always_off_for_base(
    hass: HomeAssistant, network, freezer: FrozenDateTimeFactory
) -> None:
    # Base has no off-peak hours, but the sensor exists so the same automation
    # works whatever the contract.
    freezer.move_to(datetime(2026, 9, 19, 2, 0, tzinfo=PARIS))
    await _setup(hass, {"option": "base", "power": 6})
    offpeak = hass.states.get("binary_sensor.heures_creuses")
    assert offpeak.state == "off"
    assert offpeak.attributes["next_change"] is None


async def test_old_entity_ids_are_renamed(
    hass: HomeAssistant, network, freezer: FrozenDateTimeFactory
) -> None:
    """An install made before 1.0 keeps its entities, under the new ids."""
    from homeassistant.helpers import entity_registry as er

    freezer.move_to(datetime(2026, 12, 1, 12, tzinfo=PARIS))  # red day in the mock
    await hass.config.async_set_time_zone("Europe/Paris")
    entry = MockConfigEntry(
        domain=DOMAIN, data={"option": "tempo", "power": 9}, unique_id="tempo_9", title="test"
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "tempo_9_price_now",
        suggested_object_id="tarif_bleu_tempo_9_kva_prix_actuel",
        config_entry=entry,
    )
    assert old.entity_id == "sensor.tarif_bleu_tempo_9_kva_prix_actuel"

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert registry.async_get_entity_id("sensor", DOMAIN, "tempo_9_price_now") == (
        "sensor.prix_kwh_actuel"
    )
    assert hass.states.get("sensor.prix_kwh_actuel").state == "0.7295"  # red day, peak


async def test_taken_entity_id_is_left_alone(
    hass: HomeAssistant, network, freezer: FrozenDateTimeFactory
) -> None:
    """A name already used by something else is not stolen."""
    from homeassistant.helpers import entity_registry as er

    freezer.move_to(datetime(2026, 9, 19, 12, tzinfo=PARIS))
    await hass.config.async_set_time_zone("Europe/Paris")
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor", "template", "someone_else", suggested_object_id="prix_kwh_actuel"
    )
    entry = MockConfigEntry(
        domain=DOMAIN, data={"option": "tempo", "power": 9}, unique_id="tempo_9", title="test"
    )
    entry.add_to_hass(hass)
    registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "tempo_9_price_now",
        suggested_object_id="tarif_bleu_tempo_9_kva_prix_actuel",
        config_entry=entry,
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get_entity_id("sensor", DOMAIN, "tempo_9_price_now") == (
        "sensor.tarif_bleu_tempo_9_kva_prix_actuel"
    )


def _grid(price: str, adjustment: float = 0.0) -> dict:
    return {
        "type": "grid",
        "stat_energy_from": "sensor.meter",
        "stat_energy_to": None,
        "stat_cost": None,
        "entity_energy_price": price,
        "number_energy_price": None,
        "stat_compensation": None,
        "entity_energy_price_export": None,
        "number_energy_price_export": None,
        "cost_adjustment_day": adjustment,
    }


@pytest.fixture
def energy(hass: HomeAssistant):
    """A real energy manager without the recorder the energy integration needs."""
    from homeassistant.components.energy.data import EnergyManager

    manager = EnergyManager(hass)
    manager.data = EnergyManager.default_preferences()
    hass.config.components.add("energy")

    async def get(_hass):
        return manager

    with patch("homeassistant.components.energy.data.async_get_manager", get):
        yield manager


async def test_energy_fixed_cost_follows_subscription(
    hass: HomeAssistant, network, energy, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(datetime(2026, 9, 19, 12, tzinfo=PARIS))
    energy.data["energy_sources"] = [
        _grid("sensor.prix_kwh_actuel"),
        _grid("sensor.someone_elses_price", 0.5),
    ]
    await _setup(hass, {"option": "base", "power": 18}, {"energy_fixed_cost": True})
    assert hass.states.get("sensor.abonnement_mensuel").state == "31.14"
    ours, other = energy.data["energy_sources"]
    assert ours["cost_adjustment_day"] == round(31.14 * 12 / 365, 4)
    assert other["cost_adjustment_day"] == 0.5


async def test_energy_fixed_cost_left_alone_when_off(
    hass: HomeAssistant, network, energy, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(datetime(2026, 9, 19, 12, tzinfo=PARIS))
    energy.data["energy_sources"] = [_grid("sensor.prix_kwh_actuel", 0.7)]
    await _setup(hass, {"option": "base", "power": 18})
    assert energy.data["energy_sources"][0]["cost_adjustment_day"] == 0.7


async def test_options_flow_tempo_offers_fixed_cost(hass: HomeAssistant, network) -> None:
    entry = await _setup(hass, {"option": "tempo", "power": 9})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert list(result["data_schema"].schema) == ["energy_fixed_cost"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"energy_fixed_cost": True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"energy_fixed_cost": True}


async def test_options_flow_hphc_checks_offpeak(hass: HomeAssistant, network) -> None:
    entry = await _setup(hass, {"option": "hphc", "power": 6}, {"offpeak_hours": "22:00-06:00"})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"offpeak_hours": "nope", "energy_fixed_cost": False}
    )
    assert result["errors"] == {"offpeak_hours": "invalid_offpeak"}


def _cost_grid(**flow) -> dict:
    return {**_grid("sensor.prix_kwh_actuel"), **flow}


async def test_cost_statistics_of_our_grid_sources(
    hass: HomeAssistant, network, energy, freezer: FrozenDateTimeFactory
) -> None:
    from custom_components.tarif_electricite_fr.cost import async_cost_statistics

    freezer.move_to(datetime(2026, 9, 19, 12, tzinfo=PARIS))
    hass.data["energy"] = {"cost_sensors": {"sensor.meter": "sensor.meter_cost"}}
    energy.data["energy_sources"] = [
        _cost_grid(),  # cost generated by the energy integration
        _cost_grid(stat_energy_from="sensor.meter2", stat_cost="sensor.own_cost"),
        {**_grid("sensor.someone_elses_price"), "stat_energy_from": "sensor.meter3"},
        # Preferences saved before the flat grid source: imports in flow_from.
        {
            "type": "grid",
            "flow_from": [
                {
                    "stat_energy_from": "sensor.meter4",
                    "stat_cost": "sensor.old_cost",
                    "entity_energy_price": "sensor.prix_kwh_actuel",
                }
            ],
            "flow_to": [],
        },
    ]
    entry = await _setup(hass, {"option": "base", "power": 18})
    assert await async_cost_statistics(hass, entry.entry_id) == [
        "sensor.meter_cost",
        "sensor.own_cost",
        "sensor.old_cost",
    ]


async def test_cost_sensors_add_the_subscription_pro_rata(
    hass: HomeAssistant, network, energy, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(datetime(2026, 9, 19, 12, tzinfo=PARIS))
    hass.data["energy"] = {"cost_sensors": {"sensor.meter": "sensor.meter_cost"}}
    energy.data["energy_sources"] = [_cost_grid()]
    windows = []

    async def energy_cost(_hass, statistic_ids, start, end):
        assert statistic_ids == ["sensor.meter_cost"]
        windows.append(end - start)
        return 1.5

    with patch("custom_components.tarif_electricite_fr.sensor.async_energy_cost", energy_cost):
        await _setup(hass, {"option": "base", "power": 18})
    day = round(31.14 * 12 / 365, 4)
    for entity_id, days in [
        ("sensor.cout_derniere_heure", 1 / 24),
        ("sensor.cout_24_heures", 1),
        ("sensor.cout_7_jours", 7),
        ("sensor.cout_30_jours", 30),
    ]:
        state = hass.states.get(entity_id)
        assert float(state.state) == round(1.5 + day * days, 2), entity_id
        assert state.attributes["energy_cost"] == 1.5
        assert state.attributes["subscription_share"] == round(day * days, 2)
        assert state.attributes["unit_of_measurement"] == "€"
    assert sorted(w.total_seconds() for w in windows) == [3600, 86400, 7 * 86400, 30 * 86400]


async def test_cost_sensors_unknown_without_energy_dashboard(
    hass: HomeAssistant, network, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to(datetime(2026, 9, 19, 12, tzinfo=PARIS))
    await _setup(hass, {"option": "base", "power": 18})
    assert hass.states.get("sensor.cout_30_jours").state == "unknown"
