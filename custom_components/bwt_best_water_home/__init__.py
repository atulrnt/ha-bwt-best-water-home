from __future__ import annotations

import asyncio
import datetime as dt
from typing import TYPE_CHECKING

from .api import BwtBestWaterHomeClient, ExecutorTransport
from .const import DEFAULT_SCAN_INTERVAL_MINUTES, DEFAULT_TIME_ZONE, DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

try:
    from homeassistant.const import Platform
    PLATFORMS = [Platform.SENSOR]
except ModuleNotFoundError:  # Allows unit tests of pure modules without HA installed.
    PLATFORMS = ["sensor"]



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
        self.last_stats = None
        self.last_products = []
        self._ready = asyncio.Event()

    async def async_refresh(self) -> None:
        if self.customer_id is None:
            self.customer_id = await self.client.get_customer_id()
        self.last_products = await self.client.get_products(self.customer_id)
        if self.product_id is None:
            skyline = [p for p in self.last_products if p.shadow_type == "SkylineShadow"]
            product = skyline[0] if skyline else self.last_products[0]
            self.product_id = product.product_instance_id
            self.product_name = product.name
        else:
            for product in self.last_products:
                if product.product_instance_id == self.product_id:
                    self.product_name = product.name
                    break
        self.last_stats = await self.client.get_skyline_stats(self.customer_id, self.product_id, time_zone=self.time_zone)
        self._ready.set()

    async def async_wait_ready(self) -> None:
        await self._ready.wait()


async def async_setup_entry(hass: "HomeAssistant", entry: "ConfigEntry") -> bool:
    runtime = BwtRuntime(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    await runtime.async_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: "HomeAssistant", entry: "ConfigEntry") -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
