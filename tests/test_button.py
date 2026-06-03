import importlib
import sys
import types
import unittest


class ForcePollingButtonTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._module_names = [
            "homeassistant",
            "homeassistant.components",
            "homeassistant.components.button",
            "homeassistant.config_entries",
            "homeassistant.core",
            "homeassistant.helpers",
            "homeassistant.helpers.entity_platform",
            "custom_components.bwt_best_water_home.button",
        ]
        self._saved_modules = {name: sys.modules.get(name) for name in self._module_names}

        homeassistant = types.ModuleType("homeassistant")
        components = types.ModuleType("homeassistant.components")
        button = types.ModuleType("homeassistant.components.button")
        config_entries = types.ModuleType("homeassistant.config_entries")
        core = types.ModuleType("homeassistant.core")
        helpers = types.ModuleType("homeassistant.helpers")
        entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")

        class ButtonEntity:
            pass

        setattr(button, "ButtonEntity", ButtonEntity)
        setattr(config_entries, "ConfigEntry", object)
        setattr(core, "HomeAssistant", object)
        setattr(entity_platform, "AddEntitiesCallback", object)

        setattr(homeassistant, "components", components)
        setattr(homeassistant, "config_entries", config_entries)
        setattr(homeassistant, "core", core)
        setattr(homeassistant, "helpers", helpers)
        setattr(components, "button", button)
        setattr(helpers, "entity_platform", entity_platform)

        sys.modules["homeassistant"] = homeassistant
        sys.modules["homeassistant.components"] = components
        sys.modules["homeassistant.components.button"] = button
        sys.modules["homeassistant.config_entries"] = config_entries
        sys.modules["homeassistant.core"] = core
        sys.modules["homeassistant.helpers"] = helpers
        sys.modules["homeassistant.helpers.entity_platform"] = entity_platform
        sys.modules.pop("custom_components.bwt_best_water_home.button", None)

    def tearDown(self):
        for name, module in self._saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    async def test_setup_adds_force_data_polling_button(self):
        button_module = importlib.import_module("custom_components.bwt_best_water_home.button")
        runtime = types.SimpleNamespace(product_id="pid-1", product_name="Softener")
        entry = types.SimpleNamespace(entry_id="entry-1", title="BWT")
        hass = types.SimpleNamespace(data={"bwt_best_water_home": {"entry-1": runtime}})
        added = []

        await button_module.async_setup_entry(hass, entry, added.extend)

        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]._attr_unique_id, "entry-1_force_data_polling")
        self.assertEqual(added[0]._attr_name, "Force data polling")

    async def test_pressing_button_forces_refresh_and_notifies_entities(self):
        button_module = importlib.import_module("custom_components.bwt_best_water_home.button")

        class Runtime:
            product_id = "pid-1"
            product_name = "Softener"

            def __init__(self):
                self.refreshes = 0

            async def async_refresh_and_notify(self):
                self.refreshes += 1

        runtime = Runtime()
        entry = types.SimpleNamespace(entry_id="entry-1", title="BWT")
        entity = button_module.BwtForceDataPollingButton(runtime, entry)

        await entity.async_press()

        self.assertEqual(runtime.refreshes, 1)


if __name__ == "__main__":
    unittest.main()
