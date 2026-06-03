import importlib
import sys
import types
import unittest


class RuntimeReauthTriggerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._module_names = [
            "homeassistant",
            "homeassistant.config_entries",
            "homeassistant.const",
            "homeassistant.core",
            "custom_components.bwt_best_water_home.__init__",
        ]
        self._saved_modules = {name: sys.modules.get(name) for name in self._module_names}

        homeassistant = types.ModuleType("homeassistant")
        config_entries = types.ModuleType("homeassistant.config_entries")
        const = types.ModuleType("homeassistant.const")
        core = types.ModuleType("homeassistant.core")

        setattr(config_entries, "ConfigEntry", object)
        setattr(config_entries, "SOURCE_REAUTH", "reauth")
        setattr(const, "CONF_ACCESS_TOKEN", "access_token")
        setattr(const, "Platform", types.SimpleNamespace(SENSOR="sensor", BUTTON="button"))
        setattr(core, "HomeAssistant", object)

        setattr(homeassistant, "config_entries", config_entries)
        setattr(homeassistant, "const", const)
        setattr(homeassistant, "core", core)
        sys.modules["homeassistant"] = homeassistant
        sys.modules["homeassistant.config_entries"] = config_entries
        sys.modules["homeassistant.const"] = const
        sys.modules["homeassistant.core"] = core
        sys.modules.pop("custom_components.bwt_best_water_home.__init__", None)

    def tearDown(self):
        for name, module in self._saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    async def test_auth_failure_starts_reauth_flow_for_entry(self):
        init_module = importlib.import_module("custom_components.bwt_best_water_home.__init__")

        started_flows = []

        class FlowManager:
            async def async_init(self, domain, *, context, data=None):
                started_flows.append((domain, context, data))

        hass = types.SimpleNamespace(config_entries=types.SimpleNamespace(flow=FlowManager()))
        entry = types.SimpleNamespace(entry_id="entry-1", data={"access_token": "expired-token"}, options={})
        runtime = init_module.BwtRuntime(hass, entry)

        class Client:
            async def get_customer_id(self):
                raise init_module.BwtAuthError("expired")

        runtime.client = Client()

        with self.assertRaises(init_module.BwtAuthError):
            await runtime.async_refresh_and_notify()

        self.assertEqual(started_flows, [(
            "bwt_best_water_home",
            {"source": "reauth", "entry_id": "entry-1"},
            entry.data,
        )])


if __name__ == "__main__":
    unittest.main()
