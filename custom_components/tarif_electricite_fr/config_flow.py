"""Config flow: pick the option, the subscribed power and, for HP/HC, the off-peak hours."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    CONF_OFFPEAK,
    CONF_OPTION,
    CONF_POWER,
    DEFAULT_OFFPEAK,
    DOMAIN,
    OPTION_HPHC,
    OPTIONS,
    POWERS,
)
from .periods import parse_offpeak

_TITLES = {"base": "Base", "hphc": "Heures Creuses", "tempo": "Tempo"}


def _offpeak_error(value: str) -> str | None:
    try:
        parse_offpeak(value)
    except ValueError:
        return "invalid_offpeak"
    return None


class TarifConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._option: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._option = user_input[CONF_OPTION]
            return await self.async_step_power()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_OPTION): SelectSelector(
                        SelectSelectorConfig(
                            options=list(OPTIONS),
                            translation_key=CONF_OPTION,
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_power(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._option is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            power = int(user_input[CONF_POWER])
            offpeak = user_input.get(CONF_OFFPEAK, DEFAULT_OFFPEAK)
            if self._option == OPTION_HPHC and (error := _offpeak_error(offpeak)):
                errors[CONF_OFFPEAK] = error
            else:
                await self.async_set_unique_id(f"{self._option}_{power}")
                self._abort_if_unique_id_configured()
                options = {CONF_OFFPEAK: offpeak} if self._option == OPTION_HPHC else {}
                return self.async_create_entry(
                    title=f"Tarif Bleu {_TITLES[self._option]} {power} kVA",
                    data={CONF_OPTION: self._option, CONF_POWER: power},
                    options=options,
                )

        schema: dict[Any, Any] = {
            vol.Required(
                CONF_POWER, default="6" if self._option != "tempo" else "9"
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[str(p) for p in POWERS[self._option]],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        }
        if self._option == OPTION_HPHC:
            schema[vol.Required(CONF_OFFPEAK, default=DEFAULT_OFFPEAK)] = TextSelector()
        return self.async_show_form(step_id="power", data_schema=vol.Schema(schema), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return TarifOptionsFlow()


class TarifOptionsFlow(OptionsFlow):
    """Only HP/HC has something to change later: the off-peak hours."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self.config_entry.data[CONF_OPTION] != OPTION_HPHC:
            return self.async_abort(reason="nothing_to_configure")
        errors: dict[str, str] = {}
        if user_input is not None:
            if error := _offpeak_error(user_input[CONF_OFFPEAK]):
                errors[CONF_OFFPEAK] = error
            else:
                return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_OFFPEAK, DEFAULT_OFFPEAK)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Required(CONF_OFFPEAK, default=current): TextSelector()}),
            errors=errors,
        )
