# BWT Best Water Home HACS MVP

This is a HACS-ready custom integration scaffold generated from confirmed BWT Best Water Home / AIDU GraphQL behavior.

## Not production-ready yet

Before publishing broadly:

- Replace manual access-token entry with a real OAuth/PKCE flow or refresh-token handling.
- Test inside a Home Assistant dev container/core install.
- Add config-flow tests using Home Assistant's pytest fixtures.
- Decide how to handle bucket corrections/backfills from BWT.

## Sensitive data policy

Do not commit or publish credentials, tokens, callback URLs, account/customer IDs, serial numbers, device-specific IDs, personal contact details, or raw API responses. Use fake fixtures in tests and sanitized examples in documentation.
