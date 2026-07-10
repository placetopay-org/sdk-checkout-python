# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `query_session` / `collect` now accept heterogeneous
  `payment[].processorFields[].value` payloads (`str`, `int`, `float`, `bool`, JSON object)
  to avoid Pydantic validation failures on real gateway responses.

## [1.0.0] - 2026-04-24

First production release of the redesigned PlaceToPay Checkout Python SDK.
This is **not** a drop-in replacement for `checkout-p2p` / `andrextor/python-checkout`;
see the "Migration" section in the README.

### Added

- `placetopay.checkout.Checkout` client with six typed operations:
  `create_session`, `query_session`, `cancel_session`, `collect`, `reverse`, `invalidate_token`.
- Pydantic v2 request/response models for every endpoint in the
  PlaceToPay Checkout OpenAPI contract (includes new fields not in the
  reference SDK: `type=checkin|autopay`, `AutopayRequest`, `metadata`,
  `dispersion`, `modifiers`, `subscribe`, amount conversion, agreement/agreementType,
  full `Transaction.processorFields`).
- `Settings` configuration model with:
  - `Environment` enum (`SANDBOX`, `PRODUCTION`) and `Country` enum
    (`COLOMBIA`, `ECUADOR`) — composable and overridable via explicit `base_url`.
  - Configurable connect/read timeouts, retry policy, custom headers,
    user-agent suffix, and pluggable logger.
  - Rejects plain `http://` URLs and enforces mutual exclusivity of
    `environment` and `base_url`.
- Cryptographically secure auth (`auth.py`):
  - `sign(login, secret_key, nonce, seed)` — deterministic, unit-testable.
  - `new_auth(login, secret_key)` — generates fresh nonce via
    `secrets.token_bytes(16)` and ISO-8601 UTC seed.
  - Regression test for the SDK-wide SHA-256 test vector defined in
    `ARCHITECTURE.md` §3.
- HTTP transport with a single pooled `requests.Session`, exponential
  backoff + jitter, `Retry-After` honoring, and idempotency-key support
  on `create_session` / `collect` / `reverse`.
- Typed error hierarchy (`PlaceToPayError`, `AuthenticationError`,
  `ValidationError`, `NotFoundError`, `RateLimitError`, `NetworkError`,
  `ServerError`) matching the cross-SDK error taxonomy.
- Central DEBUG-level logging with redaction of `auth.tranKey`, `auth.nonce`,
  `card.number`, `cvv`, `pin`, `password`, `token`, `credit.code`.
- Webhook verification helpers: `verify_notification` (SHA-256, forward-looking)
  and `verify_notification_legacy` (SHA-1, for legacy server deployments).
- FastAPI example app (under `examples/`, not published) exercising
  all six endpoints + webhook against the sandbox.

### Security

- Uses `secrets.token_bytes(16)` for nonce generation. The legacy Python
  SDK used `random.getrandbits`, which is **not** cryptographically secure.
- `secret_key` is wrapped in `pydantic.SecretStr` and never logged.
- HTTPS-only; plain `http://` URLs are rejected at config time.

### Breaking changes from `andrextor/python-checkout` 1.0.0

- Import path: `from checkout import Checkout` → `from placetopay.checkout import Checkout`.
- Config class: `Settings(...)` with explicit `environment`/`country` presets;
  old free-form `base_url`-only config still works but is no longer the primary path.
- Removed the misspelled `InvalidateToKenRequest.to_dic()` method; use
  Pydantic's standard `model_dump(by_alias=True, exclude_none=True)`.
- Auth now uses a cryptographically-secure nonce (was `random.getrandbits`).
- Errors now use a typed exception hierarchy instead of a single
  `CheckoutException`.
- SOAP transport is removed. REST only.

[1.0.0]: https://github.com/placetopay/checkout-python/releases/tag/v1.0.0
