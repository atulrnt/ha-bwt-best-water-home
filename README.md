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

This MVP expects a BWT access token from an external OAuth/PKCE helper. It does **not** yet embed the OAuth login flow inside Home Assistant.

Access tokens are short-lived. Generate a fresh token immediately before adding the integration. The form accepts either the raw token or a value prefixed with `Bearer `.

For a polished release, the next step should be either:

1. implement a Home Assistant OAuth external flow using the BWT public client + PKCE; or
2. store a refresh token and refresh access tokens automatically.

Do not commit tokens, account IDs, serial numbers, callback URLs, or raw API responses.

## Accuracy warning

BWT softener consumption may not equal whole-house water consumption. It may only count softened-water branches and it is cloud/bucket based. For billing-grade or whole-house Energy data, a dedicated main water meter reader is still better.

## Development

Run tests with stdlib unittest:

```bash
python3 -m unittest -v tests/test_client_and_accumulator.py
```

Syntax check:

```bash
python3 -m compileall -q custom_components tests
```
