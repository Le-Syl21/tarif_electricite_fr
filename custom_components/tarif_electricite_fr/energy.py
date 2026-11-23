"""Undo the old energy dashboard "fixed cost" option.

Up to 1.2 an option wrote the subscription into the grid connections'
cost_adjustment_day. Home Assistant never read that field (it is removed in
2026.12, home-assistant/core#192275), so the option did nothing. On start, an
entry that had it turned on takes the value back out of the grid connections
priced by its sensors, then forgets the option.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)


def daily_cost(subscription_monthly: float) -> float:
    """EUR per day for a subscription in EUR per month."""
    return round(subscription_monthly * 12 / 365, 4)


async def async_remove_fixed_cost(hass: HomeAssistant, entry_id: str) -> bool:
    """Drop cost_adjustment_day from the grid sources priced by this entry.

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
    sources = []
    changed = False
    for source in manager.data["energy_sources"]:
        if (
            source["type"] == "grid"
            and source.get("entity_energy_price") in ours
            and "cost_adjustment_day" in source
        ):
            _LOGGER.info(
                "Energy dashboard: removing the unused fixed cost %s written by 1.2",
                source["cost_adjustment_day"],
            )
            source = {k: v for k, v in source.items() if k != "cost_adjustment_day"}
            changed = True
        sources.append(source)
    if changed:
        await manager.async_update({"energy_sources": sources})
    return changed
