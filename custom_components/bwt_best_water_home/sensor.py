from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume, UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util
from homeassistant.helpers.restore_state import RestoreEntity

from .accumulator import WaterAccumulator
from .const import DOMAIN
from .cron_schedule import next_cron_time


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    entities = [
        BwtWaterTotalSensor(runtime, entry),
        BwtDailyWaterSensor(runtime, entry),
        BwtDailySaltSensor(runtime, entry),
    ]
    async_add_entities(entities)

    remove_scheduled_refresh = None

    async def _scheduled_refresh(now):
        nonlocal remove_scheduled_refresh
        await runtime.async_refresh()
        for entity in entities:
            entity.async_write_ha_state()
        remove_scheduled_refresh = _schedule_next_refresh(now)

    def _schedule_next_refresh(now=None):
        if now is None:
            now = dt_util.now()
        try:
            schedule_now = now.astimezone(ZoneInfo(runtime.time_zone))
        except ZoneInfoNotFoundError:
            schedule_now = now
        next_run = next_cron_time(runtime.cron_schedule, schedule_now)
        return async_track_point_in_time(hass, _scheduled_refresh, next_run)

    remove_scheduled_refresh = _schedule_next_refresh()
    entry.async_on_unload(lambda: remove_scheduled_refresh and remove_scheduled_refresh())


class BwtBaseSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, runtime, entry: ConfigEntry, suffix: str) -> None:
        self.runtime = runtime
        self.entry = entry
        self._attr_device_info = {
            "identifiers": {(DOMAIN, runtime.product_id or entry.entry_id)},
            "name": runtime.product_name or entry.title,
            "manufacturer": "BWT",
            "model": "My Perla / Skyline",
        }
        self._attr_unique_id = f"{entry.entry_id}_{suffix}"


class BwtWaterTotalSensor(BwtBaseSensor, RestoreEntity):
    _attr_name = "Water total"
    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS

    def __init__(self, runtime, entry: ConfigEntry) -> None:
        super().__init__(runtime, entry, "water_total")
        self.accumulator = WaterAccumulator()

    async def async_added_to_hass(self) -> None:
        if last_state := await self.async_get_last_state():
            self.accumulator = WaterAccumulator.from_state(last_state.attributes)

    @property
    def native_value(self):
        stats = self.runtime.last_stats
        if stats is None:
            return None
        state = self.accumulator.update_from_daily_litre_points(stats.water_points, now=dt.datetime.now(dt.UTC))
        return round(state.total_m3, 6)

    @property
    def extra_state_attributes(self):
        state = self.accumulator.as_state()
        return {
            "total_l": state.total_l,
            "last_processed": state.last_processed.isoformat() if state.last_processed else None,
            "source": "BWT Skyline daily bucket accumulator",
            "warning": "Derived from BWT softener bucketed consumption; not a direct main water meter.",
        }


class BwtDailyWaterSensor(BwtBaseSensor):
    _attr_name = "Daily water"
    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS

    def __init__(self, runtime, entry: ConfigEntry) -> None:
        super().__init__(runtime, entry, "daily_water")

    @property
    def native_value(self):
        stats = self.runtime.last_stats
        if not stats or not stats.water_points:
            return None
        return stats.water_points[-1].value


class BwtDailySaltSensor(BwtBaseSensor):
    _attr_name = "Daily salt"
    _attr_device_class = SensorDeviceClass.WEIGHT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfMass.GRAMS

    def __init__(self, runtime, entry: ConfigEntry) -> None:
        super().__init__(runtime, entry, "daily_salt")

    @property
    def native_value(self):
        stats = self.runtime.last_stats
        if not stats or not stats.salt_points:
            return None
        return stats.salt_points[-1].value
