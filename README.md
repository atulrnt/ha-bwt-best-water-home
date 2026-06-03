# BWT Best Water Home for Home Assistant

Experimental HACS custom integration for BWT Best Water Home / AIDU-backed water softeners such as **BWT My Perla Optimum**.

## Status

MVP / proof of concept. Confirmed against a Best Water Home account where the app exposes:

- `productShadow.__typename: SkylineShadow`
- `skylineStatisticsTotalWaterConsumption` in `Litre`
- `skylineStatisticsTotalSaltConsumption` in `Gram`

The BWT API currently appears to provide bucketed consumption values, not a true lifetime water counter for Skyline devices. This integration therefore derives the Energy-dashboard water total by checkpointing and summing closed daily buckets.

## Entities

- `sensor.<device>_water_total`
  - unit: `m³`
  - `device_class: water`
  - `state_class: total_increasing`
  - intended for Home Assistant Energy water dashboard
- `sensor.<device>_daily_water`
  - latest daily BWT bucket in litres
- `sensor.<device>_daily_salt`
  - latest daily BWT salt bucket in grams

## Installation via HACS custom repository

1. In HACS: **Integrations → ⋮ → Custom repositories**.
2. Add this repository URL.
3. Category: **Integration**.
4. Install **BWT Best Water Home**.
5. Restart Home Assistant.
6. Add integration: **Settings → Devices & services → Add integration → BWT Best Water Home**.

## Current auth limitation

This MVP still accepts a manually obtained BWT access token. The form accepts either the raw token or a value prefixed with `Bearer `.

The integration code now includes the safer manual browser OAuth/PKCE building blocks for the next config-flow iteration:

1. Home Assistant creates a BWT/AIDU authorization URL using the exact mobile-app redirect URI and PKCE challenge.
2. The user opens that URL in a normal browser, not an iframe or embedded/headless browser.
3. After login, the user pastes the final redirected URL or authorization code back into Home Assistant.
4. Home Assistant validates the OAuth `state` and can exchange `code + code_verifier` for tokens once the BWT/AIDU OAuth endpoint/client constants are confirmed.

This avoids embedding the provider login page inside Home Assistant and avoids asking Home Assistant to handle the user's BWT password.

Do not commit tokens, authorization codes, account IDs, serial numbers, callback URLs, or raw API responses.

## Polling schedule

The integration polls the BWT cloud on a cron schedule configured from the integration options:

```text
Settings → Devices & services → BWT Best Water Home → Configure
```

Default schedule:

```cron
0 2 * * *
```

This means once per day at 02:00 in the configured IANA time zone, defaulting to `Europe/Brussels`. The validator rejects schedules that can run more than once per day to avoid unnecessary BWT API calls and rate-limit/session issues.

The integration does not refresh immediately during Home Assistant startup; it waits for the next scheduled run.

## Accuracy warning

BWT softener consumption may not equal whole-house water consumption. It may only count softened-water branches and it is cloud/bucket based. For billing-grade or whole-house Energy data, a dedicated main water meter reader is still better.

## Development

Run tests with stdlib unittest:

```bash
python3 -m unittest discover tests
```

Syntax check:

```bash
python3 -m compileall -q custom_components tests
```
