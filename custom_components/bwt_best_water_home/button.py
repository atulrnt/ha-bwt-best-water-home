from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BwtForceDataPollingButton(runtime, entry)])


class BwtForceDataPollingButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Force data polling"

    def __init__(self, runtime, entry: ConfigEntry) -> None:
        self.runtime = runtime
        self.entry = entry
        self._attr_device_info = {
            "identifiers": {(DOMAIN, runtime.product_id or entry.entry_id)},
            "name": runtime.product_name or entry.title,
            "manufacturer": "BWT",
            "model": "My Perla / Skyline",
        }
        self._attr_unique_id = f"{entry.entry_id}_force_data_polling"

    async def async_press(self) -> None:
        await self.runtime.async_refresh_and_notify()
