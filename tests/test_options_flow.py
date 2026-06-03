import importlib
import sys
import types
import unittest


class OptionsFlowCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._saved_modules = {name: sys.modules.get(name) for name in [
            "homeassistant",
            "homeassistant.config_entries",
            "homeassistant.const",
            "homeassistant.core",
            "voluptuous",
            "custom_components.bwt_best_water_home.config_flow",
        ]}

        voluptuous = types.ModuleType("voluptuous")
        voluptuous.Optional = lambda key, default=None: key
        voluptuous.Schema = lambda schema: schema
        sys.modules["voluptuous"] = voluptuous

        homeassistant = types.ModuleType("homeassistant")
        config_entries = types.ModuleType("homeassistant.config_entries")
        const = types.ModuleType("homeassistant.const")
        core = types.ModuleType("homeassistant.core")

        class ConfigFlow:
            def __init_subclass__(cls, **kwargs):
                super().__init_subclass__()

        class OptionsFlow:
            @property
            def config_entry(self):
                raise AssertionError("Home Assistant owns this read-only property")

            def async_create_entry(self, *, title, data):
                return {"type": "create_entry", "title": title, "data": data}

            def async_show_form(self, *, step_id, data_schema, errors=None):
                return {
                    "type": "form",
                    "step_id": step_id,
                    "data_schema": data_schema,
                    "errors": errors or {},
                }

        config_entries.ConfigFlow = ConfigFlow
        config_entries.OptionsFlow = OptionsFlow
        const.CONF_ACCESS_TOKEN = "access_token"
        const.Platform = types.SimpleNamespace(SENSOR="sensor", BUTTON="button")
        core.callback = lambda func: func

        homeassistant.config_entries = config_entries
        homeassistant.const = const
        homeassistant.core = core
        sys.modules["homeassistant"] = homeassistant
        sys.modules["homeassistant.config_entries"] = config_entries
        sys.modules["homeassistant.const"] = const
        sys.modules["homeassistant.core"] = core
        sys.modules.pop("custom_components.bwt_best_water_home.config_flow", None)

    def tearDown(self):
        for name, module in self._saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def test_options_flow_does_not_assign_home_assistant_config_entry_property(self):
        config_flow = importlib.import_module("custom_components.bwt_best_water_home.config_flow")
        entry = types.SimpleNamespace(options={}, data={})

        options_flow = config_flow.BwtConfigFlow.async_get_options_flow(entry)

        self.assertIs(options_flow._config_entry, entry)

    async def test_options_flow_uses_serializable_schema_types(self):
        config_flow = importlib.import_module("custom_components.bwt_best_water_home.config_flow")
        entry = types.SimpleNamespace(options={}, data={})
        options_flow = config_flow.BwtConfigFlow.async_get_options_flow(entry)

        result = await options_flow.async_step_init()

        self.assertIs(result["data_schema"]["cron_schedule"], str)

    async def test_options_flow_rejects_invalid_cron_schedule_without_raising(self):
        config_flow = importlib.import_module("custom_components.bwt_best_water_home.config_flow")
        entry = types.SimpleNamespace(options={}, data={})
        options_flow = config_flow.BwtConfigFlow.async_get_options_flow(entry)

        result = await options_flow.async_step_init({"time_zone": "Europe/Brussels", "cron_schedule": "*/5 * * * *"})

        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"], {"cron_schedule": "invalid_cron"})


if __name__ == "__main__":
    unittest.main()
