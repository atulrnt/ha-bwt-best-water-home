import datetime as dt
import unittest

from custom_components.bwt_best_water_home.api import (
    BwtAuthError,
    BwtBestWaterHomeClient,
    _bucketed_stats_window,
    _format_graphql_datetime,
)
from custom_components.bwt_best_water_home.accumulator import WaterAccumulator


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def post_json(self, url, payload, headers):
        self.calls.append((url, payload, headers))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class BwtClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_discovers_customer_product_and_skyline_stats(self):
        transport = FakeTransport([
            {"data": {"userProfile": {"assignedCustomerIds": ["cust-1"]}}},
            {"data": {"userProfile": {"myProducts": {"items": [
                {
                    "productInstanceId": "pid-1",
                    "customProductName": "My Perla Optimum",
                    "productVariantName": "myperla",
                    "isOnlineOperation": True,
                    "customerInformation": {"site": {"timeZone": {"timeZoneId": "Europe/Vienna"}}},
                    "productShadow": {"__typename": "SkylineShadow", "lastTimeDataReceived": "2026-05-28T09:42:20.691Z", "wifiRssi_dbm": -70},
                }
            ]}}}},
            {"data": {"water": {"measurementUnit": "Litre", "dataPoints": [{"date": "2026-05-27T22:00:00.000Z", "value": 41}]}, "salt": {"measurementUnit": "Gram", "dataPoints": [{"date": "2026-05-27T22:00:00.000Z", "value": 0}]}}},
        ])
        client = BwtBestWaterHomeClient("Bearer access-token", transport=transport)

        customer_id = await client.get_customer_id()
        products = await client.get_products(customer_id)
        stats = await client.get_device_stats(customer_id, products[0])

        self.assertEqual(customer_id, "cust-1")
        self.assertEqual(products[0].product_instance_id, "pid-1")
        self.assertEqual(products[0].name, "My Perla Optimum")
        self.assertEqual(products[0].shadow_type, "SkylineShadow")
        self.assertEqual(products[0].time_zone, "Europe/Vienna")
        self.assertEqual(stats.water_unit, "Litre")
        self.assertEqual(stats.water_points[0].value, 41)
        self.assertEqual(transport.calls[0][2]["authorization"], "Bearer access-token")
        self.assertEqual(transport.calls[1][2]["ctx-current-customer-id"], "cust-1")
        self.assertEqual(transport.calls[2][1]["variables"]["format"], "Day")
        self.assertEqual(transport.calls[2][1]["variables"]["ianaTimeZone"], "Europe/Vienna")

    async def test_client_uses_app_perla_statistics_for_perla_shadow(self):
        transport = FakeTransport([
            {"data": {"water": {"measurementUnit": "Litre", "dataPoints": [{"date": "2026-05-27T22:00:00.000Z", "value": 123}]}, "salt": {"measurementUnit": "Kilogram", "dataPoints": [{"date": "2026-05-27T22:00:00.000Z", "value": 1.5}]}}},
        ])
        client = BwtBestWaterHomeClient("access-token", transport=transport)
        product = type("Product", (), {"product_instance_id": "perla-1", "shadow_type": "PerlaShadow"})()

        stats = await client.get_device_stats("cust-1", product, time_zone="Europe/Brussels")

        payload = transport.calls[0][1]
        query = payload["query"]
        self.assertIn("perlaTreatedWaterStatistics", query)
        self.assertIn("perlaResourceStatistics", query)
        self.assertNotIn("skylineStatisticsTotalWaterConsumption", query)
        self.assertEqual(payload["variables"]["productInstanceId"], "perla-1")
        self.assertEqual(payload["variables"]["format"], "Day")
        self.assertEqual(payload["variables"]["ianaTimeZone"], "UTC")
        self.assertEqual(transport.calls[0][2]["ctx-current-customer-id"], "cust-1")
        self.assertEqual(transport.calls[0][2]["experimental-features"], "CustomerContext")
        self.assertEqual(stats.water_unit, "Litre")
        self.assertEqual(stats.water_points[0].value, 123)
        self.assertEqual(stats.salt_unit, "Kilogram")
        self.assertEqual(stats.salt_points[0].value, 1.5)

    async def test_client_raises_auth_error_for_graphql_unauthorized(self):
        transport = FakeTransport([
            {"errors": [{"extensions": {"code": "UNAUTHORIZED"}, "message": "no current customer id"}], "data": {"userProfile": None}}
        ])
        client = BwtBestWaterHomeClient("access-token", transport=transport)

        with self.assertRaises(BwtAuthError):
            await client.get_customer_id()

    def test_http_500_authentication_body_is_auth_error(self):
        from custom_components.bwt_best_water_home.api import _is_auth_error_response

        parsed = {
            "type": "System.Exception",
            "title": "Error while authenticating request.",
            "status": 500,
            "detail": "Error while authenticating request.",
            "NyotaRequestTraceId": "trace-id",
        }

        self.assertTrue(_is_auth_error_response(500, parsed))
        self.assertFalse(_is_auth_error_response(500, {"title": "Generic server error"}))

    def test_stats_window_matches_app_closed_daily_range(self):
        now = dt.datetime(2026, 6, 4, 12, 34, 56, tzinfo=dt.UTC)

        from_date, until_date = _bucketed_stats_window(days=7, time_zone="Europe/Brussels", now=now)

        self.assertEqual(_format_graphql_datetime(from_date), "2026-05-27T22:00:00.000Z")
        self.assertEqual(_format_graphql_datetime(until_date), "2026-06-03T21:59:59.999Z")

    def test_perla_app_window_uses_utc(self):
        now = dt.datetime(2026, 6, 4, 12, 34, 56, tzinfo=dt.UTC)

        from_date, until_date = _bucketed_stats_window(days=7, time_zone="UTC", now=now)

        self.assertEqual(_format_graphql_datetime(from_date), "2026-05-28T00:00:00.000Z")
        self.assertEqual(_format_graphql_datetime(until_date), "2026-06-03T23:59:59.999Z")


class AccumulatorTests(unittest.TestCase):
    def test_accumulator_adds_only_closed_buckets_once_and_converts_to_m3(self):
        acc = WaterAccumulator()
        now = dt.datetime(2026, 5, 29, 10, 0, tzinfo=dt.UTC)
        points = [
            (dt.datetime(2026, 5, 26, 22, 0, tzinfo=dt.UTC), 75),
            (dt.datetime(2026, 5, 27, 22, 0, tzinfo=dt.UTC), 41),
            (dt.datetime(2026, 5, 28, 22, 0, tzinfo=dt.UTC), 99),  # current/open bucket; skip
        ]

        result = acc.update_from_daily_litre_points(points, now=now)
        second = acc.update_from_daily_litre_points(points, now=now)

        self.assertEqual(result.total_l, 116)
        self.assertAlmostEqual(result.total_m3, 0.116)
        self.assertEqual(result.last_processed.isoformat(), "2026-05-27T22:00:00+00:00")
        self.assertEqual(second.total_l, 116)

    def test_accumulator_can_be_restored_from_extra_state_attributes(self):
        acc = WaterAccumulator.from_state({"total_l": 116, "last_processed": "2026-05-27T22:00:00+00:00"})
        now = dt.datetime(2026, 5, 30, 10, 0, tzinfo=dt.UTC)

        result = acc.update_from_daily_litre_points([
            (dt.datetime(2026, 5, 27, 22, 0, tzinfo=dt.UTC), 41),
            (dt.datetime(2026, 5, 28, 22, 0, tzinfo=dt.UTC), 99),
        ], now=now)

        self.assertEqual(result.total_l, 215)
        self.assertEqual(result.last_processed.isoformat(), "2026-05-28T22:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
