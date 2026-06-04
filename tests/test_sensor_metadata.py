import importlib
import sys
import types
import unittest


class SensorMetadataTests(unittest.TestCase):
    def setUp(self):
        self._module_names = [
            "homeassistant",
            "homeassistant.components",
            "homeassistant.components.sensor",
            "homeassistant.config_entries",
            "homeassistant.const",
            "homeassistant.core",
            "homeassistant.helpers",
            "homeassistant.helpers.entity_platform",
            "homeassistant.helpers.event",
            "homeassistant.helpers.restore_state",
            "homeassistant.util",
            "homeassistant.util.dt",
            "custom_components.bwt_best_water_home.sensor",
        ]
        self._saved_modules = {name: sys.modules.get(name) for name in self._module_names}

        homeassistant = types.ModuleType("homeassistant")
        components = types.ModuleType("homeassistant.components")
        sensor = types.ModuleType("homeassistant.components.sensor")
        config_entries = types.ModuleType("homeassistant.config_entries")
        const = types.ModuleType("homeassistant.const")
        core = types.ModuleType("homeassistant.core")
        helpers = types.ModuleType("homeassistant.helpers")
        entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
        event = types.ModuleType("homeassistant.helpers.event")
        restore_state = types.ModuleType("homeassistant.helpers.restore_state")
        util = types.ModuleType("homeassistant.util")
        util_dt = types.ModuleType("homeassistant.util.dt")

        class SensorEntity:
            pass

        class RestoreEntity:
            pass

        setattr(sensor, "SensorDeviceClass", types.SimpleNamespace(WATER="water", WEIGHT="weight"))
        setattr(sensor, "SensorEntity", SensorEntity)
        setattr(sensor, "SensorStateClass", types.SimpleNamespace(
            MEASUREMENT="measurement",
            TOTAL="total",
            TOTAL_INCREASING="total_increasing",
        ))
        setattr(config_entries, "ConfigEntry", object)
        setattr(const, "UnitOfVolume", types.SimpleNamespace(CUBIC_METERS="m³", LITERS="L"))
        setattr(const, "UnitOfMass", types.SimpleNamespace(KILOGRAMS="kg", GRAMS="g"))
        setattr(core, "HomeAssistant", object)
        setattr(entity_platform, "AddEntitiesCallback", object)
        setattr(event, "async_track_point_in_time", lambda *args, **kwargs: (lambda: None))
        setattr(restore_state, "RestoreEntity", RestoreEntity)
        setattr(util_dt, "now", lambda: None)

        setattr(homeassistant, "components", components)
        setattr(homeassistant, "config_entries", config_entries)
        setattr(homeassistant, "const", const)
        setattr(homeassistant, "core", core)
        setattr(homeassistant, "helpers", helpers)
        setattr(homeassistant, "util", util)
        setattr(components, "sensor", sensor)
        setattr(helpers, "entity_platform", entity_platform)
        setattr(helpers, "event", event)
        setattr(helpers, "restore_state", restore_state)
        setattr(util, "dt", util_dt)

        sys.modules["homeassistant"] = homeassistant
        sys.modules["homeassistant.components"] = components
        sys.modules["homeassistant.components.sensor"] = sensor
        sys.modules["homeassistant.config_entries"] = config_entries
        sys.modules["homeassistant.const"] = const
        sys.modules["homeassistant.core"] = core
        sys.modules["homeassistant.helpers"] = helpers
        sys.modules["homeassistant.helpers.entity_platform"] = entity_platform
        sys.modules["homeassistant.helpers.event"] = event
        sys.modules["homeassistant.helpers.restore_state"] = restore_state
        sys.modules["homeassistant.util"] = util
        sys.modules["homeassistant.util.dt"] = util_dt
        sys.modules.pop("custom_components.bwt_best_water_home.sensor", None)

    def tearDown(self):
        for name, module in self._saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def test_daily_water_sensor_uses_home_assistant_valid_water_state_class(self):
        sensor_module = importlib.import_module("custom_components.bwt_best_water_home.sensor")

        self.assertEqual(sensor_module.BwtDailyWaterSensor._attr_device_class, "water")
        self.assertEqual(sensor_module.BwtDailyWaterSensor._attr_state_class, "total")


if __name__ == "__main__":
    unittest.main()
