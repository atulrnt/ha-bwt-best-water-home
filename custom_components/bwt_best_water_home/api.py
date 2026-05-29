from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import json
from typing import Any, Protocol
from urllib import error, request

from .const import APP_VERSION, DEFAULT_TIME_ZONE, GRAPHQL_URL


class BwtError(Exception):
    """Base BWT integration error."""


class BwtAuthError(BwtError):
    """BWT token is missing, expired, or lacks the required customer context."""


class BwtApiError(BwtError):
    """BWT GraphQL returned an application-level or HTTP error."""


@dataclass(frozen=True)
class BwtProduct:
    product_instance_id: str
    name: str
    product_variant_name: str | None
    shadow_type: str | None
    is_online: bool | None
    last_data_received: str | None = None
    wifi_rssi_dbm: int | None = None


@dataclass(frozen=True)
class BwtDataPoint:
    date: dt.datetime
    value: float


@dataclass(frozen=True)
class BwtSkylineStats:
    water_unit: str | None
    water_points: list[BwtDataPoint]
    salt_unit: str | None
    salt_points: list[BwtDataPoint]


class BwtTransport(Protocol):
    async def post_json(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]: ...


class UrllibTransport:
    """Small stdlib transport; Home Assistant calls it through async_add_executor_job."""

    def post_json_sync(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        req = request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {"message": body}
            raise BwtApiError(f"BWT HTTP {exc.code}: {parsed}") from exc

    async def post_json(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        # This async method is useful for tests. In HA, ExecutorTransport wraps post_json_sync.
        return self.post_json_sync(url, payload, headers)


class BwtBestWaterHomeClient:
    def __init__(self, access_token: str, *, transport: BwtTransport | None = None, app_version: str = APP_VERSION) -> None:
        self.access_token = access_token
        self.transport = transport or UrllibTransport()
        self.app_version = app_version

    async def _graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        *,
        customer_id: str | None = None,
    ) -> dict[str, Any]:
        headers = {
            "content-type": "application/json",
            "accept": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "app-version": self.app_version,
        }
        if customer_id:
            headers["ctx-current-customer-id"] = customer_id
            headers["experimental-features"] = "CustomerContext"
        data = await self.transport.post_json(GRAPHQL_URL, {"query": query, "variables": variables or {}}, headers)
        errors = data.get("errors") or []
        if errors:
            codes = {((err.get("extensions") or {}).get("code") or "").upper() for err in errors}
            messages = "; ".join(str(err.get("message")) for err in errors)
            if "UNAUTHORIZED" in codes or "AUTHENTICATION_ERROR" in codes:
                raise BwtAuthError(messages)
            raise BwtApiError(messages)
        return data

    async def get_customer_id(self) -> str:
        query = """
        query UserProfileCustomers {
          userProfile { assignedCustomerIds myCustomers { id type } }
        }
        """
        data = await self._graphql(query)
        profile = (data.get("data") or {}).get("userProfile") or {}
        ids = profile.get("assignedCustomerIds") or [c.get("id") for c in profile.get("myCustomers") or [] if c.get("id")]
        if not ids:
            raise BwtAuthError("No BWT customer context id found")
        return ids[0]

    async def get_products(self, customer_id: str) -> list[BwtProduct]:
        query = """
        query UserProfileProducts {
          userProfile {
            myProducts { items {
              productInstanceId customProductName productVariantName isOnlineOperation
              productShadow {
                __typename
                ... on SkylineShadow { lastTimeDataReceived wifiRssi_dbm }
              }
            } }
          }
        }
        """
        data = await self._graphql(query, customer_id=customer_id)
        items = (((data.get("data") or {}).get("userProfile") or {}).get("myProducts") or {}).get("items") or []
        products: list[BwtProduct] = []
        for item in items:
            shadow = item.get("productShadow") or {}
            products.append(BwtProduct(
                product_instance_id=item["productInstanceId"],
                name=item.get("customProductName") or item.get("productVariantName") or item["productInstanceId"],
                product_variant_name=item.get("productVariantName"),
                shadow_type=shadow.get("__typename"),
                is_online=item.get("isOnlineOperation"),
                last_data_received=shadow.get("lastTimeDataReceived"),
                wifi_rssi_dbm=shadow.get("wifiRssi_dbm"),
            ))
        return products

    async def get_skyline_stats(
        self,
        customer_id: str,
        product_instance_id: str,
        *,
        days: int = 14,
        time_zone: str = DEFAULT_TIME_ZONE,
        resolution: str = "Day",
    ) -> BwtSkylineStats:
        now = dt.datetime.now(dt.UTC)
        query = """
        query SkylineStats($productInstanceId: String!, $format: IDataPointResolutionFormat, $fromDate: DateTime, $untilDate: DateTime, $ianaTimeZone: String) {
          water: skylineStatisticsTotalWaterConsumption(productInstanceId: $productInstanceId, format: $format, fromDate: $fromDate, untilDate: $untilDate, ianaTimeZone: $ianaTimeZone) {
            measurementUnit dataPoints { date value }
          }
          salt: skylineStatisticsTotalSaltConsumption(productInstanceId: $productInstanceId, format: $format, fromDate: $fromDate, untilDate: $untilDate, ianaTimeZone: $ianaTimeZone) {
            measurementUnit dataPoints { date value }
          }
        }
        """
        data = await self._graphql(query, {
            "productInstanceId": product_instance_id,
            "format": resolution,
            "fromDate": (now - dt.timedelta(days=days)).isoformat(),
            "untilDate": now.isoformat(),
            "ianaTimeZone": time_zone,
        }, customer_id=customer_id)
        stats = data.get("data") or {}
        water = stats.get("water") or {}
        salt = stats.get("salt") or {}
        return BwtSkylineStats(
            water_unit=water.get("measurementUnit"),
            water_points=_parse_points(water.get("dataPoints") or []),
            salt_unit=salt.get("measurementUnit"),
            salt_points=_parse_points(salt.get("dataPoints") or []),
        )


def _parse_points(points: list[dict[str, Any]]) -> list[BwtDataPoint]:
    parsed: list[BwtDataPoint] = []
    for point in points:
        raw_date = str(point["date"])
        if raw_date.endswith("Z"):
            raw_date = raw_date[:-1] + "+00:00"
        parsed.append(BwtDataPoint(date=dt.datetime.fromisoformat(raw_date), value=float(point["value"])))
    return parsed
