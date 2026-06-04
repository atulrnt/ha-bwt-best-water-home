import importlib
import sys
import types
import unittest


class RuntimeTokenRefreshTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_refreshes_expired_access_token_and_persists_rotated_refresh_token(self):
        init_module = importlib.import_module("custom_components.bwt_best_water_home.__init__")

        updated_entries = []

        class ConfigEntries:
            def async_update_entry(self, entry, **kwargs):
                updated_entries.append(kwargs)
                if "data" in kwargs:
                    entry.data = kwargs["data"]

        def executor_job(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        hass = types.SimpleNamespace(
            config_entries=ConfigEntries(),
            async_add_executor_job=executor_job,
        )
        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={"access_token": "old-access", "refresh_token": "old-refresh", "expires_at": 1},
            options={},
        )
        runtime = init_module.BwtRuntime(hass, entry)

        refresh_calls = []
        init_module.exchange_bwt_refresh_token_sync = lambda *, refresh_token: refresh_calls.append(refresh_token) or {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
        }

        class Client:
            async def get_customer_id(self):
                return "cust-1"

            async def get_products(self, customer_id):
                return [types.SimpleNamespace(
                    product_instance_id="pid-1",
                    name="Softener",
                    shadow_type="PerlaShadow",
                )]

            async def get_device_stats(self, customer_id, product, *, time_zone):
                return "stats"

        runtime.client = Client()

        await runtime.async_refresh_and_notify()

        self.assertEqual(refresh_calls, ["old-refresh"])
        self.assertEqual(entry.data["access_token"], "new-access")
        self.assertEqual(entry.data["refresh_token"], "new-refresh")
        self.assertEqual(runtime.last_stats, "stats")
        self.assertEqual(len(updated_entries), 1)

    async def test_auth_failure_refreshes_token_and_retries_once_before_reauth(self):
        init_module = importlib.import_module("custom_components.bwt_best_water_home.__init__")

        started_flows = []

        class FlowManager:
            async def async_init(self, domain, *, context, data=None):
                started_flows.append((domain, context, data))

        class ConfigEntries:
            flow = FlowManager()

            def async_update_entry(self, entry, **kwargs):
                if "data" in kwargs:
                    entry.data = kwargs["data"]

        def executor_job(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        hass = types.SimpleNamespace(
            config_entries=ConfigEntries(),
            async_add_executor_job=executor_job,
        )
        entry = types.SimpleNamespace(
            entry_id="entry-1",
            data={"access_token": "old-access", "refresh_token": "refresh-token"},
            options={},
        )
        runtime = init_module.BwtRuntime(hass, entry)
        init_module.exchange_bwt_refresh_token_sync = lambda *, refresh_token: {"access_token": "new-access", "expires_in": 3600}

        class Client:
            def __init__(self):
                self.calls = 0

            async def get_customer_id(self):
                self.calls += 1
                if self.calls == 1:
                    raise init_module.BwtAuthError("expired")
                return "cust-1"

            async def get_products(self, customer_id):
                return [types.SimpleNamespace(
                    product_instance_id="pid-1",
                    name="Softener",
                    shadow_type="PerlaShadow",
                )]

            async def get_device_stats(self, customer_id, product, *, time_zone):
                return "stats"

        client = Client()
        runtime.client = client

        await runtime.async_refresh_and_notify()

        self.assertEqual(client.calls, 2)
        self.assertEqual(entry.data["access_token"], "new-access")
        self.assertEqual(entry.data["refresh_token"], "refresh-token")
        self.assertEqual(started_flows, [])


if __name__ == "__main__":
    unittest.main()
