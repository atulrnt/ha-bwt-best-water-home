import datetime as dt
import unittest

from custom_components.bwt_best_water_home.api import BwtAuthError, BwtBestWaterHomeClient
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
                    "productShadow": {"__typename": "SkylineShadow", "lastTimeDataReceived": "2026-05-28T09:42:20.691Z", "wifiRssi_dbm": -70},
                }
            ]}}}},
            {"data": {"water": {"measurementUnit": "Litre", "dataPoints": [{"date": "2026-05-27T22:00:00.000Z", "value": 41}]}, "salt": {"measurementUnit": "Gram", "dataPoints": [{"date": "2026-05-27T22:00:00.000Z", "value": 0}]}}},
        ])
        client = BwtBestWaterHomeClient("Bearer access-token", transport=transport)

        customer_id = await client.get_customer_id()
        products = await client.get_products(customer_id)
        stats = await client.get_skyline_stats(customer_id, "pid-1", days=14)

        self.assertEqual(customer_id, "cust-1")
        self.assertEqual(products[0].product_instance_id, "pid-1")
        self.assertEqual(products[0].name, "My Perla Optimum")
        self.assertEqual(products[0].shadow_type, "SkylineShadow")
        self.assertEqual(stats.water_unit, "Litre")
        self.assertEqual(stats.water_points[0].value, 41)
        self.assertEqual(transport.calls[0][2]["authorization"], "Bearer access-token")
        self.assertEqual(transport.calls[1][2]["ctx-current-customer-id"], "cust-1")
        self.assertEqual(transport.calls[2][1]["variables"]["format"], "Day")

    async def test_client_raises_auth_error_for_graphql_unauthorized(self):
        transport = FakeTransport([
            {"errors": [{"extensions": {"code": "UNAUTHORIZED"}, "message": "no current customer id"}], "data": {"userProfile": None}}
        ])
        client = BwtBestWaterHomeClient("access-token", transport=transport)

        with self.assertRaises(BwtAuthError):
            await client.get_customer_id()


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
