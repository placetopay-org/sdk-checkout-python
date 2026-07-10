# Contributing — PlaceToPay Checkout Python SDK

Thanks for taking the time to contribute. This document walks through local
setup, the expected workflow for changes, and the quality bar we enforce.

## Local setup

```bash
git clone https://github.com/placetopay/checkout-python.git
cd checkout-python

python3.13 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

The SDK targets **Python 3.13+** (see `pyproject.toml`). Earlier versions are
out of scope.

## Running the test suite

```bash
pytest tests/                    # unit tests; coverage gate enforced ≥ 85 %
pytest --no-cov -q               # faster iteration without the coverage report
pytest -m integration            # sandbox-talking tests (skipped by default)
```

For live sandbox tests you need:

```bash
export PLACETOPAY_LOGIN=…
export PLACETOPAY_SECRET_KEY=…
```

## Linting, typing, formatting

```bash
ruff check src tests             # PEP 8 + project-specific rules
ruff format src tests            # auto-format
mypy src                         # strict typing
```

CI runs the same commands. A PR that breaks any of them will fail.

## Running the examples app

```bash
cd examples
pip install -r requirements.txt
cp .env.example .env             # fill in sandbox credentials
uvicorn app:app --reload
```

## Coding standards

- **Type-complete** — every function and method carries type annotations.
  `mypy` runs in `strict` mode; there is no "I'll add the types later".
- **Pydantic v2** for data models. Use `alias_generator=to_camel` +
  `populate_by_name=True` so snake_case in Python and camelCase on the wire.
- **Secrets never flow to logs.** The `redact_body` helper is the contract;
  add new sensitive field names to `_REDACT_FULL` / `_REDACT_LAST4` in
  `src/placetopay/checkout/http.py`.
- **No `random.*` for anything security-sensitive.** Use `secrets`.
- **HTTPS everywhere** — `Settings._validate_https_only` rejects plain `http`
  schemes; test endpoints on `localhost` are the only exception.

## The cross-SDK auth test vector

If you touch `auth.py`, the regression vector in `tests/unit/test_auth.py`
must continue to produce:

```
login     = "SDK_TEST_LOGIN"
secretKey = "SDK_TEST_SECRET"
rawNonce  = bytes.fromhex("00112233445566778899aabbccddeeff")
seed      = "2026-04-22T15:30:45+00:00"

→ wireNonce = "ABEiM0RVZneImaq7zN3u/w=="
→ tranKey   = "ktUB+Efbix9v8H/DxdxtDQu9u33E4BLGr6so+LrvAjs="
```

Any change in that output is a **cross-SDK contract break** and must be
discussed + mirrored in `checkout-dotnet` and `checkout-java` before merging.

## Pull requests

1. Branch off `main`.
2. Open a PR with a short description of **why** the change is needed
   (the "what" usually reads itself from the diff).
3. Ensure `pytest`, `ruff`, and `mypy` all pass locally.
4. Add tests for new behavior. Coverage threshold is enforced by the
   `--cov-fail-under=85` in `pyproject.toml`.
5. Update `CHANGELOG.md` under an `Unreleased` section following the
   [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.
6. Keep the auth test vector green (see above).

## Reporting issues

Use the GitHub issue tracker. For **security issues**, do NOT open a public
issue — email security@placetopay.com per [SECURITY.md](../SECURITY.md).

## License

By contributing, you agree your changes are licensed under the MIT license
(see [LICENSE](LICENSE)).
