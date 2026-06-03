from __future__ import annotations

import logging
from functools import partial

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import callback

from .api import BwtApiError, BwtAuthError, BwtBestWaterHomeClient, ExecutorTransport
from .auth_flow import (
    AuthRedirectError,
    ManualAuthSession,
    create_bwt_manual_auth_session,
    exchange_bwt_authorization_code_sync,
    extract_access_token,
    extract_authorization_code,
)
from .const import BWT_REDIRECT_URI, DEFAULT_CRON_SCHEDULE, DEFAULT_TIME_ZONE, DOMAIN, NAME
from .cron_schedule import validate_cron_string


_LOGGER = logging.getLogger(__name__)


class BwtConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._auth_session: ManualAuthSession | None = None
        self._reauth_entry = None
        self._reconfigure_entry = None

    @property
    def auth_session(self) -> ManualAuthSession:
        if self._auth_session is None:
            self._auth_session = create_bwt_manual_auth_session()
        return self._auth_session

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            token = (user_input.get(CONF_ACCESS_TOKEN) or "").strip()
            if not token:
                callback_url = (user_input.get("callback_url") or "").strip()
                if not callback_url:
                    errors["base"] = "missing_auth"
                else:
                    try:
                        code = extract_authorization_code(callback_url, expected_state=self.auth_session.state)
                        token_response = await self.hass.async_add_executor_job(
                            partial(
                                exchange_bwt_authorization_code_sync,
                                code=code,
                                code_verifier=self.auth_session.code_verifier,
                            )
                        )
                        token = extract_access_token(token_response)
                    except AuthRedirectError as exc:
                        _LOGGER.warning("BWT Best Water Home OAuth flow failed: %s", exc)
                        errors["base"] = "oauth"
                    except Exception:
                        _LOGGER.exception("Unexpected BWT Best Water Home OAuth exchange failure")
                        errors["base"] = "cannot_connect"
            if token and not errors:
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
                vol.Optional("callback_url"): str,
                vol.Optional(CONF_ACCESS_TOKEN): str,
                vol.Optional("time_zone", default=DEFAULT_TIME_ZONE): str,
            }),
            errors=errors,
            description_placeholders={
                "auth_url": self.auth_session.authorization_url,
                "redirect_uri": BWT_REDIRECT_URI,
            },
        )

    async def async_step_reauth(self, entry_data):
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            token = await self._async_token_from_auth_input(user_input, errors)
            if token and not errors:
                validation = await self._async_validate_token(token)
                if "error" in validation:
                    errors["base"] = validation["error"]
                else:
                    entry = self._reauth_entry or self.hass.config_entries.async_get_entry(self.context["entry_id"])
                    self.hass.config_entries.async_update_entry(
                        entry,
                        data={**entry.data, CONF_ACCESS_TOKEN: token},
                    )
                    await self.hass.config_entries.async_reload(entry.entry_id)
                    return self.async_abort(reason="reauth_successful")
        return self._show_auth_form("reauth_confirm", errors)

    async def async_step_reconfigure(self, user_input=None):
        if self._reconfigure_entry is None:
            self._reconfigure_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        errors = {}
        if user_input is not None:
            token = await self._async_token_from_auth_input(user_input, errors)
            if token and not errors:
                validation = await self._async_validate_token(token)
                if "error" in validation:
                    errors["base"] = validation["error"]
                else:
                    product = validation["product"]
                    entry = self._reconfigure_entry
                    data = {
                        CONF_ACCESS_TOKEN: token,
                        "customer_id": validation["customer_id"],
                        "product_instance_id": product.product_instance_id,
                        "time_zone": user_input.get("time_zone") or entry.data.get("time_zone", DEFAULT_TIME_ZONE),
                    }
                    self.hass.config_entries.async_update_entry(entry, title=product.name or NAME, data=data)
                    await self.hass.config_entries.async_reload(entry.entry_id)
                    return self.async_abort(reason="reconfigure_successful")
        default_time_zone = DEFAULT_TIME_ZONE
        if self._reconfigure_entry is not None:
            default_time_zone = self._reconfigure_entry.data.get("time_zone", DEFAULT_TIME_ZONE)
        return self._show_auth_form("reconfigure", errors, include_time_zone=True, default_time_zone=default_time_zone)

    def _show_auth_form(self, step_id, errors, *, include_time_zone=False, default_time_zone=DEFAULT_TIME_ZONE):
        schema = {
            vol.Optional("callback_url"): str,
            vol.Optional(CONF_ACCESS_TOKEN): str,
        }
        if include_time_zone:
            schema[vol.Optional("time_zone", default=default_time_zone)] = str
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={
                "auth_url": self.auth_session.authorization_url,
                "redirect_uri": BWT_REDIRECT_URI,
            },
        )

    async def _async_token_from_auth_input(self, user_input, errors) -> str:
        token = (user_input.get(CONF_ACCESS_TOKEN) or "").strip()
        if token:
            return token
        callback_url = (user_input.get("callback_url") or "").strip()
        if not callback_url:
            errors["base"] = "missing_auth"
            return ""
        try:
            code = extract_authorization_code(callback_url, expected_state=self.auth_session.state)
            token_response = await self.hass.async_add_executor_job(
                partial(
                    exchange_bwt_authorization_code_sync,
                    code=code,
                    code_verifier=self.auth_session.code_verifier,
                )
            )
            return extract_access_token(token_response)
        except AuthRedirectError as exc:
            _LOGGER.warning("BWT Best Water Home OAuth flow failed: %s", exc)
            errors["base"] = "oauth"
        except Exception:
            _LOGGER.exception("Unexpected BWT Best Water Home OAuth exchange failure")
            errors["base"] = "cannot_connect"
        return ""

    async def _async_validate_token(self, token: str) -> dict:
        client = BwtBestWaterHomeClient(token, transport=ExecutorTransport(self.hass))
        try:
            customer_id = await client.get_customer_id()
            products = await client.get_products(customer_id)
        except BwtAuthError as exc:
            _LOGGER.warning("BWT Best Water Home authentication failed: %s", exc)
            return {"error": "auth"}
        except BwtApiError as exc:
            _LOGGER.warning("BWT Best Water Home API request failed: %s", exc)
            return {"error": "cannot_connect"}
        except Exception:
            _LOGGER.exception("Unexpected BWT Best Water Home config flow failure")
            return {"error": "cannot_connect"}
        product = next((p for p in products if p.shadow_type == "SkylineShadow"), products[0] if products else None)
        if product is None:
            return {"error": "no_products"}
        return {"customer_id": customer_id, "product": product}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return BwtOptionsFlow(config_entry)


class BwtOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                cron_schedule = validate_cron_string((user_input.get("cron_schedule") or DEFAULT_CRON_SCHEDULE).strip())
            except ValueError:
                errors["cron_schedule"] = "invalid_cron"
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        "time_zone": (user_input.get("time_zone") or DEFAULT_TIME_ZONE).strip(),
                        "cron_schedule": cron_schedule,
                    },
                )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional("time_zone", default=self._config_entry.options.get("time_zone", self._config_entry.data.get("time_zone", DEFAULT_TIME_ZONE))): str,
                vol.Optional("cron_schedule", default=self._config_entry.options.get("cron_schedule", DEFAULT_CRON_SCHEDULE)): str,
            }),
            errors=errors,
        )
