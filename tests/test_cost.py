"""The cost over a window, read from real recorder statistics."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.tarif_electricite_fr.cost import async_energy_cost, subscription_share

UTC = ZoneInfo("UTC")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    """The recorder has to come up before hass: request it first."""
    yield


async def test_energy_cost_is_the_change_over_the_window(hass: HomeAssistant) -> None:
    # An hourly cost that grows by 0.10 EUR every hour for two days.
    start = datetime(2026, 10, 1, tzinfo=UTC)
    async_import_statistics(
        hass,
        {
            "has_mean": False,
            "mean_type": StatisticMeanType.NONE,
            "has_sum": True,
            "name": None,
            "source": "recorder",
            "statistic_id": "sensor.meter_cost",
            "unit_of_measurement": "EUR",
            "unit_class": None,
        },
        [
            {"start": start + timedelta(hours=h), "sum": round(0.1 * (h + 1), 2), "state": 0.0}
            for h in range(48)
        ],
    )
    await async_wait_recording_done(hass)
    end = start + timedelta(hours=48)
    day = await async_energy_cost(hass, ["sensor.meter_cost"], end - timedelta(days=1), end)
    assert round(day, 2) == 2.4
    hour = await async_energy_cost(hass, ["sensor.meter_cost"], end - timedelta(hours=1), end)
    assert round(hour, 2) == 0.1
    both = await async_energy_cost(
        hass, ["sensor.meter_cost", "sensor.meter_cost"], end - timedelta(days=1), end
    )
    assert round(both, 2) == 4.8
    assert await async_energy_cost(hass, ["sensor.nothing"], end - timedelta(days=1), end) is None


def test_subscription_share() -> None:
    assert subscription_share(30.42, timedelta(days=1)) == round(30.42 * 12 / 365, 4)
    assert round(subscription_share(30.42, timedelta(hours=1)) * 24, 4) == round(
        30.42 * 12 / 365, 4
    )
