from __future__ import annotations

import asyncio
import datetime as dt
from typing import TYPE_CHECKING

from .api import BwtAuthError, BwtBestWaterHomeClient, ExecutorTransport
from .const import DEFAULT_CRON_SCHEDULE, DEFAULT_SCAN_INTERVAL_MINUTES, DEFAULT_TIME_ZONE, DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

try:
    from homeassistant import config_entries
    from homeassistant.const import Platform
    PLATFORMS = [Platform.SENSOR, Platform.BUTTON]
except ModuleNotFoundError:  # Allows unit tests of pure modules without HA installed.
    config_entries = None
    PLATFORMS = ["sensor", "button"]



class BwtRuntime:
    def __init__(self, hass: "HomeAssistant", entry: "ConfigEntry") -> None:
        from homeassistant.const import CONF_ACCESS_TOKEN

        self.hass = hass
        self.entry = entry
        self.client = BwtBestWaterHomeClient(entry.data[CONF_ACCESS_TOKEN], transport=ExecutorTransport(hass))
        self.customer_id: str | None = entry.data.get("customer_id")
        self.product_id: str | None = entry.data.get("product_instance_id")
        self.product_name: str | None = None
        self.time_zone = entry.options.get("time_zone", entry.data.get("time_zone", DEFAULT_TIME_ZONE))
        self.scan_interval = dt.timedelta(minutes=entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL_MINUTES))
        self.cron_schedule = entry.options.get("cron_schedule", entry.data.get("cron_schedule", DEFAULT_CRON_SCHEDULE))
        self.last_stats = None
        self.last_products = []
        self._refresh_listeners = []
        self._refresh_lock = asyncio.Lock()
        self._ready = asyncio.Event()
        self._reauth_started = False

    def add_refresh_listener(self, listener):
        self._refresh_listeners.append(listener)

        def remove_listener() -> None:
            if listener in self._refresh_listeners:
                self._refresh_listeners.remove(listener)

        return remove_listener

    async def async_refresh(self) -> None:
        if self.customer_id is None:
            self.customer_id = await self.client.get_customer_id()
        self.last_products = await self.client.get_products(self.customer_id)
        selected_product = None
        if self.product_id is None:
            app_supported = [p for p in self.last_products if p.shadow_type in ("PerlaShadow", "SkylineShadow")]
            selected_product = app_supported[0] if app_supported else self.last_products[0]
            self.product_id = selected_product.product_instance_id
            self.product_name = selected_product.name
        else:
            for product in self.last_products:
                if product.product_instance_id == self.product_id:
                    selected_product = product
                    self.product_name = product.name
                    break
        if selected_product is None:
            selected_product = self.last_products[0]
        self.last_stats = await self.client.get_device_stats(self.customer_id, selected_product, time_zone=self.time_zone)
        self._ready.set()

    async def async_refresh_and_notify(self) -> None:
        async with self._refresh_lock:
            try:
                await self.async_refresh()
            except BwtAuthError:
                await self._async_start_reauth()
                raise
            for listener in tuple(self._refresh_listeners):
                listener()

    async def _async_start_reauth(self) -> None:
        if self._reauth_started or config_entries is None:
            return
        self._reauth_started = True
        await self.hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_REAUTH, "entry_id": self.entry.entry_id},
            data=self.entry.data,
        )

    async def async_wait_ready(self) -> None:
        await self._ready.wait()


async def async_setup_entry(hass: "HomeAssistant", entry: "ConfigEntry") -> bool:
    runtime = BwtRuntime(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: "HomeAssistant", entry: "ConfigEntry") -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
