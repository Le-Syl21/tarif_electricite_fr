"""Tarif électricité FR: EDF "Tarif Bleu" regulated prices and Tempo colours."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import OBJECT_IDS
from .coordinator import TarifConfigEntry, TarifCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]


@callback
def _rename_old_entities(hass: HomeAssistant, entry: TarifConfigEntry) -> None:
    """Move entities created before 1.0 to the fixed entity ids.

    Up to 0.2 the entity id was built from the device name and the label in the
    language of Home Assistant, which gave things like
    sensor.tarif_bleu_tempo_15_kva_prix_jour_rouge_heures_pleines. An id already
    taken by something else is left alone rather than fought over.
    """
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        key = entity.unique_id.removeprefix(f"{entry.unique_id}_")
        if (object_id := OBJECT_IDS.get(key)) is None:
            continue
        wanted = f"{entity.domain}.{object_id}"
        if entity.entity_id == wanted or registry.async_get(wanted) is not None:
            continue
        _LOGGER.info("Renaming %s to %s", entity.entity_id, wanted)
        registry.async_update_entity(entity.entity_id, new_entity_id=wanted)


async def async_setup_entry(hass: HomeAssistant, entry: TarifConfigEntry) -> bool:
    _rename_old_entities(hass, entry)
    coordinator = TarifCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TarifConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: TarifConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
