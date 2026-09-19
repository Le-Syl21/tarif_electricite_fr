"""Sensors: price now, period now, price of each period, subscription, Tempo colours."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import CURRENCY_EURO, EntityCategory, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import tempo
from .const import DOMAIN, OPTION_TEMPO, PERIODS, TEMPO_COLOURS
from .coordinator import TarifConfigEntry, TarifCoordinator
from .periods import tempo_day

PRICE_UNIT = f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}"


@dataclass(frozen=True, kw_only=True)
class TarifSensorDescription(SensorEntityDescription):
    value: Callable[[TarifCoordinator], Any]
    attributes: Callable[[TarifCoordinator], dict[str, Any]] | None = None


def _price_now(c: TarifCoordinator):
    period = c.period_now()
    if period is None or c.data.tariff is None:
        return None
    return c.data.tariff.prices.get(period)


def _source_attributes(c: TarifCoordinator) -> dict[str, Any]:
    tariff = c.data.tariff
    return (
        {
            "source": tariff.source,
            "valid_from": tariff.valid_from.isoformat(),
        }
        if tariff
        else {}
    )


def _colour(c: TarifCoordinator, days: int):
    return c.data.colours.get(tempo_day(dt_util.now()) + timedelta(days=days))


def _remaining(c: TarifCoordinator, colour: str) -> int:
    return tempo.remaining(c.data.colours, dt_util.now().date())[colour]


def _descriptions(option: str) -> list[TarifSensorDescription]:
    periods = PERIODS[option]
    sensors = [
        TarifSensorDescription(
            key="price_now",
            translation_key="price_now",
            native_unit_of_measurement=PRICE_UNIT,
            suggested_display_precision=4,
            value=_price_now,
            attributes=_source_attributes,
        ),
        TarifSensorDescription(
            key="period_now",
            translation_key="period_now",
            device_class=SensorDeviceClass.ENUM,
            options=list(periods),
            value=lambda c: c.period_now(),
        ),
        TarifSensorDescription(
            key="subscription",
            translation_key="subscription",
            device_class=SensorDeviceClass.MONETARY,
            native_unit_of_measurement=CURRENCY_EURO,
            suggested_display_precision=2,
            value=lambda c: c.data.tariff.subscription_monthly if c.data.tariff else None,
        ),
        TarifSensorDescription(
            key="valid_from",
            translation_key="valid_from",
            device_class=SensorDeviceClass.DATE,
            entity_category=EntityCategory.DIAGNOSTIC,
            value=lambda c: c.data.tariff.valid_from if c.data.tariff else None,
            attributes=lambda c: {"cre_reachable": c.data.cre_ok, "edf_reachable": c.data.edf_ok},
        ),
        TarifSensorDescription(
            key="source",
            translation_key="source",
            device_class=SensorDeviceClass.ENUM,
            options=["cre", "edf"],
            entity_category=EntityCategory.DIAGNOSTIC,
            value=lambda c: c.data.tariff.source if c.data.tariff else None,
        ),
    ]
    if len(periods) > 1:
        sensors += [
            TarifSensorDescription(
                key=f"price_{period}",
                translation_key=f"price_{period}",
                native_unit_of_measurement=PRICE_UNIT,
                suggested_display_precision=4,
                value=lambda c, p=period: c.data.tariff.prices.get(p) if c.data.tariff else None,
            )
            for period in periods
        ]
    if option == OPTION_TEMPO:
        sensors += [
            TarifSensorDescription(
                key="colour_today",
                translation_key="colour_today",
                device_class=SensorDeviceClass.ENUM,
                options=list(TEMPO_COLOURS),
                value=lambda c: _colour(c, 0),
            ),
            TarifSensorDescription(
                key="colour_tomorrow",
                translation_key="colour_tomorrow",
                device_class=SensorDeviceClass.ENUM,
                options=list(TEMPO_COLOURS),
                value=lambda c: _colour(c, 1),
            ),
        ]
        sensors += [
            TarifSensorDescription(
                key=f"remaining_{colour}",
                translation_key=f"remaining_{colour}",
                native_unit_of_measurement="d",
                value=lambda c, col=colour: _remaining(c, col),
            )
            for colour in TEMPO_COLOURS
        ]
    return sensors


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TarifConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        TarifSensor(coordinator, description) for description in _descriptions(coordinator.option)
    )


class TarifSensor(CoordinatorEntity[TarifCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: TarifSensorDescription

    def __init__(self, coordinator: TarifCoordinator, description: TarifSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="EDF",
            model=f"Tarif Bleu {coordinator.option} {coordinator.power} kVA",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self):
        return self.entity_description.value(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes is None:
            return None
        return self.entity_description.attributes(self.coordinator)
