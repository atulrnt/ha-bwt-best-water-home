# BWT Best Water Home for Home Assistant

HACS custom integration for BWT Best Water Home / AIDU-backed water softeners such as **BWT My Perla Optimum**.

This is an unofficial interoperability project. It does not include BWT application code or BWT-owned brand assets.

## Disclaimer

This project is not affiliated with, endorsed by, sponsored by, or supported by BWT. BWT and related product names are trademarks of their respective owners. Use this integration at your own risk; cloud APIs may change, rate-limit, or stop working at any time.

## Status

Tested and working integration using the BWT Best Water Home / AIDU cloud backend:

- `https://api.aidu.solutions/api/graphql/homeapp/`
- auth authority `https://account.bwt-group.com`
- OAuth client `bwt-best-water-app-prod`
- app redirect URI `com.bwt.home.app://signin`

The integration supports the app-observed cloud statistic fields for:

- `productShadow.__typename: PerlaShadow`
  - `perlaTreatedWaterStatistics`
  - `perlaResourceStatistics`
- `productShadow.__typename: SkylineShadow`
  - `skylineStatisticsTotalWaterConsumption`
  - `skylineStatisticsTotalSaltConsumption`

The BWT API currently appears to provide bucketed consumption values, not a true lifetime water counter. This integration therefore derives the Energy-dashboard water total by checkpointing and summing closed daily buckets.

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

## Current auth flow

The setup flow uses a normal-browser OAuth/PKCE flow:

1. Home Assistant shows a BWT login link built from the confirmed BWT Best Water Home public-client OAuth values.
2. The user opens that URL in a normal browser, not an iframe or embedded/headless browser.
3. After login, the user pastes the final redirected URL or authorization code back into Home Assistant.
4. Home Assistant validates the OAuth `state`, exchanges `code + code_verifier` for tokens, then discovers the user's BWT products.

This avoids embedding the provider login page inside Home Assistant and avoids asking Home Assistant to handle the user's BWT password.

Do not commit tokens, authorization codes, account IDs, serial numbers, callback URLs, or raw API responses.

## Privacy and security

- Credentials and OAuth tokens are stored only in the Home Assistant config entry for this integration.
- The integration sends requests only to the configured BWT/AIDU cloud endpoints needed for device discovery, token refresh, and statistics polling.
- The integration does not collect telemetry and does not send data to this repository or its maintainer.
- When reporting bugs, redact access tokens, refresh tokens, authorization codes, account IDs, customer IDs, serial numbers, callback URLs, and raw API responses.

## Polling schedule

The integration polls the BWT cloud on a cron schedule configured from the integration options:

```text
Settings → Devices & services → BWT Best Water Home → Configure
```

Default schedule:

```cron
0 2 * * *
```

This means once per day at 02:00 in the configured IANA time zone, defaulting to `Europe/Brussels`. You can configure another standard five-field cron expression if needed, but conservative polling is recommended to avoid unnecessary BWT API calls and rate-limit/session issues.

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
