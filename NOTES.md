# BWT Best Water Home HACS Notes

This is a HACS-ready custom integration using confirmed BWT Best Water Home / AIDU GraphQL behavior.

## Publication checklist

Before publishing broadly:

- Add config-flow tests using Home Assistant's pytest fixtures.
- Decide how to handle bucket corrections/backfills from BWT.

## Sensitive data policy

Do not commit or publish credentials, tokens, callback URLs, account/customer IDs, serial numbers, device-specific IDs, personal contact details, or raw API responses. Use fake fixtures in tests and sanitized examples in documentation.
