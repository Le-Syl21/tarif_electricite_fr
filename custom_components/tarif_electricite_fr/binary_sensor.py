"""Binary sensor: on during off-peak hours (HP/HC and Tempo)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import OPTION_BASE
from .coordinator import TarifConfigEntry, TarifCoordinator
from .entity import device_info
from .periods import in_ranges, next_change, offpeak_ranges


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TarifConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if coordinator.option != OPTION_BASE:
        async_add_entities([OffpeakBinarySensor(coordinator)])


class OffpeakBinarySensor(CoordinatorEntity[TarifCoordinator], BinarySensorEntity):
    """On during off-peak hours; knows when they end or start next.

    Only the clock is needed, so it stays right when the price sources are
    down or, for Tempo, before the day's colour is known.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "offpeak"

    def __init__(self, coordinator: TarifCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id}_offpeak"
        self._attr_device_info = device_info(coordinator)

    @property
    def available(self) -> bool:
        return True

    def _ranges(self):
        return offpeak_ranges(self.coordinator.option, self.coordinator.offpeak)

    @property
    def is_on(self) -> bool:
        return in_ranges(dt_util.now().time(), self._ranges())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        change = next_change(dt_util.now(), self._ranges())
        return {"next_change": change.isoformat() if change else None}
