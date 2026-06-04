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
            def __init__(self):
                self.context = {}
                self.hass = None

            def __init_subclass__(cls, **kwargs):
                super().__init_subclass__()

            def async_create_entry(self, *, title, data):
                return {"type": "create_entry", "title": title, "data": data}

            def async_show_form(self, *, step_id, data_schema, errors=None, description_placeholders=None):
                return {
                    "type": "form",
                    "step_id": step_id,
                    "data_schema": data_schema,
                    "errors": errors or {},
                    "description_placeholders": description_placeholders or {},
                }

            def async_abort(self, *, reason):
                return {"type": "abort", "reason": reason}

            async def async_set_unique_id(self, unique_id):
                self.unique_id = unique_id

            def _abort_if_unique_id_configured(self):
                return None

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
        config_entries.SOURCE_REAUTH = "reauth"
        config_entries.SOURCE_RECONFIGURE = "reconfigure"
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

        result = await options_flow.async_step_init({"time_zone": "Europe/Brussels", "cron_schedule": "not cron"})

        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"], {"cron_schedule": "invalid_cron"})

    async def test_reauth_flow_updates_existing_entry_token_and_reloads(self):
        config_flow = importlib.import_module("custom_components.bwt_best_water_home.config_flow")
        entry = types.SimpleNamespace(
            entry_id="entry-1",
            title="Softener",
            data={"access_token": "old-token", "customer_id": "customer-1", "product_instance_id": "product-1", "time_zone": "Europe/Brussels"},
            options={},
        )
        updated = []
        reloaded = []

        class ConfigEntries:
            def async_get_entry(self, entry_id):
                self_outer.assertEqual(entry_id, "entry-1")
                return entry

            def async_update_entry(self, target_entry, *, data):
                updated.append((target_entry, data))

            async def async_reload(self, entry_id):
                reloaded.append(entry_id)

        class Hass:
            config_entries = ConfigEntries()

            async def async_add_executor_job(self, func, *args):
                return func(*args)

        class Client:
            def __init__(self, token, transport):
                self_outer.assertEqual(token, "new-token")

            async def get_customer_id(self):
                return "customer-1"

            async def get_products(self, customer_id):
                self_outer.assertEqual(customer_id, "customer-1")
                return [types.SimpleNamespace(product_instance_id="product-1", name="Softener", shadow_type="SkylineShadow")]

        self_outer = self
        config_flow.BwtBestWaterHomeClient = Client
        config_flow.ExecutorTransport = lambda hass: object()
        config_flow.extract_authorization_code = lambda pasted, expected_state=None: "auth-code"
        config_flow.exchange_bwt_authorization_code_sync = lambda *, code, code_verifier: {"access_token": "new-token"}

        flow = config_flow.BwtConfigFlow()
        flow.hass = Hass()
        flow.context = {"entry_id": "entry-1"}

        result = await flow.async_step_reauth(entry.data)
        self.assertEqual(result["type"], "form")
        result = await flow.async_step_reauth_confirm({"callback_url": "com.bwt.home.app://signin?code=auth-code&state=x"})

        self.assertEqual(result, {"type": "abort", "reason": "reauth_successful"})
        self.assertEqual(updated, [(entry, {**entry.data, "access_token": "new-token"})])
        self.assertEqual(reloaded, ["entry-1"])

    async def test_reconfigure_flow_updates_existing_entry_credentials_and_reload(self):
        config_flow = importlib.import_module("custom_components.bwt_best_water_home.config_flow")
        entry = types.SimpleNamespace(
            entry_id="entry-1",
            title="Old Softener",
            data={"access_token": "old-token", "customer_id": "old-customer", "product_instance_id": "old-product", "time_zone": "Europe/Brussels"},
            options={},
        )
        updated = []
        reloaded = []

        class ConfigEntries:
            def async_get_entry(self, entry_id):
                self_outer.assertEqual(entry_id, "entry-1")
                return entry

            def async_update_entry(self, target_entry, *, title=None, data=None):
                updated.append((target_entry, title, data))

            async def async_reload(self, entry_id):
                reloaded.append(entry_id)

        class Hass:
            config_entries = ConfigEntries()

            async def async_add_executor_job(self, func, *args):
                return func(*args)

        class Client:
            def __init__(self, token, transport):
                self_outer.assertEqual(token, "new-token")

            async def get_customer_id(self):
                return "new-customer"

            async def get_products(self, customer_id):
                self_outer.assertEqual(customer_id, "new-customer")
                return [types.SimpleNamespace(product_instance_id="new-product", name="New Softener", shadow_type="SkylineShadow")]

        self_outer = self
        config_flow.BwtBestWaterHomeClient = Client
        config_flow.ExecutorTransport = lambda hass: object()
        config_flow.extract_authorization_code = lambda pasted, expected_state=None: "auth-code"
        config_flow.exchange_bwt_authorization_code_sync = lambda *, code, code_verifier: {"access_token": "new-token"}

        flow = config_flow.BwtConfigFlow()
        flow.hass = Hass()
        flow.context = {"entry_id": "entry-1"}

        result = await flow.async_step_reconfigure()
        self.assertEqual(result["type"], "form")
        result = await flow.async_step_reconfigure({"callback_url": "com.bwt.home.app://signin?code=auth-code&state=x", "time_zone": "Europe/Amsterdam"})

        self.assertEqual(result, {"type": "abort", "reason": "reconfigure_successful"})
        self.assertEqual(updated, [(
            entry,
            "New Softener",
            {
                "access_token": "new-token",
                "customer_id": "new-customer",
                "product_instance_id": "new-product",
                "time_zone": "Europe/Amsterdam",
            },
        )])
        self.assertEqual(reloaded, ["entry-1"])


if __name__ == "__main__":
    unittest.main()
