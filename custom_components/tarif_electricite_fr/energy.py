"""Keep the energy dashboard's fixed daily cost equal to the subscription.

The dashboard takes the fixed cost as a plain number (cost_adjustment_day), not an
entity, so it goes stale when the regulated subscription changes. When the user
turns this on, every grid connection whose import price is one of this entry's
sensors gets the subscription spread over the days of the year.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)


def daily_cost(subscription_monthly: float) -> float:
    """EUR per day for a subscription in EUR per month."""
    return round(subscription_monthly * 12 / 365, 4)


async def async_sync_fixed_cost(hass: HomeAssistant, entry_id: str, monthly: float) -> bool:
    """Write the daily subscription to the grid sources priced by this entry.

    Returns True when the energy preferences were changed.
    """
    if "energy" not in hass.config.components:
        return False
    from homeassistant.components.energy.data import async_get_manager  # noqa: PLC0415

    manager = await async_get_manager(hass)
    if manager.data is None:
        return False
    ours = {
        entity.entity_id
        for entity in er.async_entries_for_config_entry(er.async_get(hass), entry_id)
    }
    wanted = daily_cost(monthly)
    sources = []
    changed = False
    for source in manager.data["energy_sources"]:
        if (
            source["type"] == "grid"
            and source.get("entity_energy_price") in ours
            and source.get("cost_adjustment_day") != wanted
        ):
            _LOGGER.info(
                "Energy dashboard: fixed cost per day %s -> %s EUR (subscription %s EUR/month)",
                source.get("cost_adjustment_day"),
                wanted,
                monthly,
            )
            source = {**source, "cost_adjustment_day": wanted}
            changed = True
        sources.append(source)
    if changed:
        await manager.async_update({"energy_sources": sources})
    return changed
