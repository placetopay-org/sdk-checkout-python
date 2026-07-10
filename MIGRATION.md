# Migration — Python SDK: `andrextor/python-checkout` → `placetopay-checkout`

This guide walks through every user-visible change between the legacy
community SDK (`andrextor/python-checkout` v1.0.0) and the new official SDK
(`placetopay-checkout` v1.0.0).

---

## TL;DR

```bash
pip uninstall checkout-p2p                   # old package
pip install placetopay-checkout              # new package
```

```diff
- from checkout import Checkout
+ from placetopay.checkout import Checkout, Settings, Environment, Country
```

Then adjust the constructor (below) and you're done. Method names, model
shapes and endpoint coverage are compatible at the wire level — the
differences are in idiomatic Python API.

---

## 1. Import path

| Old                                        | New                                                    |
| ------------------------------------------ | ------------------------------------------------------ |
| `from checkout import Checkout`            | `from placetopay.checkout import Checkout`             |
| `from checkout.messages.requests…`         | `from placetopay.checkout.models.session import …`     |
| `from checkout.entities.status import …`   | `from placetopay.checkout.models.common import Status` |

## 2. Construction

**Before**

```python
checkout = Checkout({
    "base_url": "https://checkout-test.placetopay.com/",
    "tranKey":  "…",
    "login":    "…",
})
```

**After**

```python
from placetopay.checkout import Checkout, Settings, Environment, Country

checkout = Checkout(Settings(
    login=…,
    secret_key=…,                             # was: tranKey
    environment=Environment.SANDBOX,          # preferred over base_url
    country=Country.COLOMBIA,                 # optional; picks locale+currency
))
```

Key differences:

- The credential used to sign is now called **`secret_key`** (matches the
  official docs and the Java/.NET SDKs). The legacy name `tranKey` was
  confusing because `tranKey` on the wire is the *computed digest*, not the
  secret.
- `base_url` is replaced by the `Environment` preset. Pass `base_url=` only
  when you need a custom gateway host (e.g. a corporate proxy) — HTTP is
  rejected at configuration time unless it targets localhost.
- `Country` supplies the default `locale` + `currency` and picks the correct
  base URL for the region (e.g. Ecuador resolves to
  `checkout.placetopay.ec`).

## 3. Method renames

| Legacy method                       | New method                           |
| ----------------------------------- | ------------------------------------ |
| `request(…)`                        | `create_session(…)`                  |
| `query(request_id)`                 | `query_session(request_id)`          |
| `collect(…)`                        | `collect(…)` *(unchanged)*           |
| `reverse(internal_reference)`       | `reverse(internal_reference)` *(unchanged)* |
| `invalidateToken(InvalidateToKenRequest(…))` | `invalidate_token(InvalidateTokenRequest(…))` *(snake_case + typo fixed)* |
| *(not available)*                   | `cancel_session(request_id)` **new** |

## 4. The `to_dic()` bug

The legacy SDK defined `InvalidateToKenRequest.to_dic()` (typo). Any code that
worked around it stops working:

```diff
- request = InvalidateToKenRequest(instrument=…)
- data    = request.to_dic()                  # legacy typo
- checkout.invalidateToken(request)
+ from placetopay.checkout.models.instrument import InvalidateTokenRequest
+ checkout.invalidate_token(InvalidateTokenRequest(instrument=…))
```

The SDK serializes on your behalf — there is no `.to_dict()` or `.to_dic()`
you need to call.

## 5. Error handling

The legacy SDK raised `HttpException` subclasses that carried the raw body.
The new SDK exposes a typed hierarchy rooted at `PlaceToPayError`:

```diff
  try:
      checkout.create_session(req)
- except HttpException as e:
-     print(e.status_code, e.response_body)
+ except ValidationError as e:
+     for fe in e.field_errors:
+         print(fe)
+ except AuthenticationError:
+     pass
+ except RateLimitError as e:
+     time.sleep(e.retry_after.total_seconds() if e.retry_after else 2)
+ except NetworkError as e:
+     print("transport failed:", e.__cause__)
```

## 6. Signature changes in the auth block

If you construct `Auth` blocks manually (tests, advanced integrations):

```diff
- auth = Authentication(login=…, tran_key=…).to_dict()
+ from placetopay.checkout.auth import new_auth
+ auth = new_auth(login=…, secret_key=…)       # returns pydantic model
+ auth_dict = auth.model_dump(by_alias=True, exclude_none=True)
```

The new `Auth` model carries an optional `additional` map for
merchant-specific metadata the gateway records — see
`Settings.auth_additional`.

## 7. Webhook verification

The legacy SDK didn't ship a webhook verifier; new code can use:

```python
from placetopay.checkout import verify_notification

@app.post("/placetopay/webhook")
def webhook(payload: dict):
    if not verify_notification(payload, secret_key=SECRET):
        return ("invalid signature", 403)
    ...
```

SHA-256 is the default. Legacy servers that still emit SHA-1 hex signatures
can use `verify_notification_legacy` while the server migrates.

## 8. Security improvements you get for free

- **SHA-256 signing** instead of the legacy SDK's mixed behavior.
- **Cryptographic nonce** (`secrets.token_bytes`) — the legacy SDK used
  `random.getrandbits`, which is not cryptographically secure.
- **Automatic log redaction** of PAN, CVV, `tranKey`, `nonce`, tokens, pin,
  and password fields at DEBUG level.
- **HTTPS enforcement** at configuration time (plain `http://` rejected
  unless it targets localhost for tests).

## 9. New features

- `cancel_session(request_id)` — stop a pending session before the buyer
  pays.
- `invalidate_token(request)` — revoke a stored token.
- `Settings.auth_additional` — merchant-specific metadata transmitted with
  each authenticated session.
- `CollectRequest.provider` — optional processor override.
- `Discount` entity modeled explicitly.
- `Status.is_approved / is_rejected / is_error` and
  `SessionInformation.last_transaction / last_approved_transaction /
  last_authorization` convenience helpers.
- Typed `autopay` / `type=autopay` session support.
