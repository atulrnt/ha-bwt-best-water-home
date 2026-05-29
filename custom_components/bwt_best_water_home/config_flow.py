from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import callback

from .api import BwtApiError, BwtAuthError, BwtBestWaterHomeClient, ExecutorTransport
from .const import DEFAULT_SCAN_INTERVAL_MINUTES, DEFAULT_TIME_ZONE, DOMAIN, NAME


_LOGGER = logging.getLogger(__name__)


class BwtConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            token = user_input[CONF_ACCESS_TOKEN].strip()
            client = BwtBestWaterHomeClient(token, transport=ExecutorTransport(self.hass))
            try:
                customer_id = await client.get_customer_id()
                products = await client.get_products(customer_id)
            except BwtAuthError as exc:
                _LOGGER.warning("BWT Best Water Home authentication failed: %s", exc)
                errors["base"] = "auth"
            except BwtApiError as exc:
                _LOGGER.warning("BWT Best Water Home API request failed: %s", exc)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected BWT Best Water Home config flow failure")
                errors["base"] = "cannot_connect"
            else:
                product = next((p for p in products if p.shadow_type == "SkylineShadow"), products[0] if products else None)
                if product is None:
                    errors["base"] = "no_products"
                else:
                    await self.async_set_unique_id(product.product_instance_id)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=product.name or NAME,
                        data={
                            CONF_ACCESS_TOKEN: token,
                            "customer_id": customer_id,
                            "product_instance_id": product.product_instance_id,
                            "time_zone": user_input.get("time_zone") or DEFAULT_TIME_ZONE,
                        },
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_ACCESS_TOKEN): str,
                vol.Optional("time_zone", default=DEFAULT_TIME_ZONE): str,
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return BwtOptionsFlow(config_entry)


class BwtOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional("time_zone", default=self.config_entry.options.get("time_zone", self.config_entry.data.get("time_zone", DEFAULT_TIME_ZONE))): str,
                vol.Optional("scan_interval", default=self.config_entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL_MINUTES)): int,
            }),
        )
