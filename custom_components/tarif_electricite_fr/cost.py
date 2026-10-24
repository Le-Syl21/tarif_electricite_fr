"""What electricity cost over the last hour, day, week and month, subscription included.

The energy dashboard already turns the consumption into money with our price
sensor: it keeps a cost statistic for each grid connection priced by
`sensor.prix_kwh_actuel`. The change of that statistic over a sliding window is
the energy part. The recorder computes it from its 5-minute and hourly
statistics, which it keeps long after the state history is purged, so a 30-day
window works whatever `purge_keep_days` is. The subscription is added pro rata
of the window, at the same daily rate the energy dashboard fixed cost uses.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .energy import daily_cost

_LOGGER = logging.getLogger(__name__)


async def async_cost_statistics(hass: HomeAssistant, entry_id: str) -> list[str]:
    """Cost statistic ids of the grid connections priced by this entry's sensors."""
    if "energy" not in hass.config.components:
        return []
    from homeassistant.components.energy.data import async_get_manager  # noqa: PLC0415

    manager = await async_get_manager(hass)
    if manager.data is None:
        return []
    ours = {
        entity.entity_id
        for entity in er.async_entries_for_config_entry(er.async_get(hass), entry_id)
    }
    # The cost entities the energy integration created itself, by energy entity.
    generated = hass.data.get("energy", {}).get("cost_sensors", {})
    ids = []
    for source in manager.data["energy_sources"]:
        if source["type"] != "grid":
            continue
        # A grid source is flat since Home Assistant 2026.x; older preferences
        # list the imports in flow_from.
        for flow in [source, *source.get("flow_from", [])]:
            if flow.get("entity_energy_price") not in ours or not flow.get("stat_energy_from"):
                continue
            if stat := flow.get("stat_cost") or generated.get(flow["stat_energy_from"]):
                ids.append(stat)
    return ids


async def async_energy_cost(
    hass: HomeAssistant, statistic_ids: list[str], start: datetime, end: datetime
) -> float | None:
    """Sum of the change of each cost statistic between start and end, or None."""
    if "recorder" not in hass.config.components:
        return None
    from homeassistant.components.recorder import get_instance  # noqa: PLC0415
    from homeassistant.components.recorder.statistics import (  # noqa: PLC0415
        statistic_during_period,
    )

    total = None
    for statistic_id in statistic_ids:
        result = await get_instance(hass).async_add_executor_job(
            statistic_during_period, hass, start, end, statistic_id, {"change"}, None
        )
        if (change := result.get("change")) is not None:
            total = (total or 0.0) + change
    return total


def subscription_share(subscription_monthly: float, window: timedelta) -> float:
    """The part of the subscription that falls in a window, in EUR."""
    return daily_cost(subscription_monthly) * (window / timedelta(days=1))
