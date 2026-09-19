"""What every entity of an entry shares."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN
from .coordinator import TarifCoordinator


def device_info(coordinator: TarifCoordinator) -> DeviceInfo:
    entry = coordinator.config_entry
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="EDF",
        model=f"Tarif Bleu {coordinator.option} {coordinator.power} kVA",
        entry_type=DeviceEntryType.SERVICE,
    )
