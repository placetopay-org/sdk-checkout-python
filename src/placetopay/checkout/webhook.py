"""Webhook signature verification helpers.

PlaceToPay signs notifications as::

    signature = hash(request_id || status.status || status.date || secret_key)

Reference Java SDK uses **SHA-1 hex**. Sandbox validation confirmed that
current PlaceToPay webhook signatures use **SHA-256**. We still ship
**both** verifiers for interoperability and document both:

* :func:`verify_notification` — SHA-256; use for servers known to emit
  SHA-256 signatures (all post-migration deployments).
* :func:`verify_notification_legacy` — SHA-1; use for legacy servers that
  still emit SHA-1 hex signatures (reference behavior).

Both functions are **constant-time** (``hmac.compare_digest``) to avoid
timing-side-channel attacks.
"""

from __future__ import annotations

import hashlib
import hmac
import warnings
from typing import Any

__all__ = [
    "build_signature_base",
    "verify_notification",
    "verify_notification_legacy",
]


def build_signature_base(payload: dict[str, Any], secret_key: str) -> str:
    """Compose the pre-hash signature string from a notification payload.

    The base is ``{requestId}{status.status}{status.date}{secret_key}``
    (same convention as the reference Java/C# SDKs).

    :raises KeyError: if ``requestId`` or ``status`` is missing.
    :raises TypeError: if ``status`` is not a mapping.
    """
    request_id = payload["requestId"]
    status = payload["status"]
    if not isinstance(status, dict):
        raise TypeError(
            "payload['status'] must be a dict with 'status' and 'date' keys"
        )
    # Use empty-string fallback so missing optionals don't crash the digest.
    # The ``or ""`` arm covers the case where the key exists but is ``None``
    # (e.g. ``{"status": None}`` — ``.get`` returns ``None``, not the default).
    status_code = status.get("status", "") or ""
    date = status.get("date", "") or ""
    return f"{request_id}{status_code}{date}{secret_key}"


def verify_notification(payload: dict[str, Any], secret_key: str) -> bool:
    """Verify a webhook payload's ``signature`` field using SHA-256.

    The signature on the payload is assumed to be lowercase hex.

     .. warning::
         Primary verifier for current PlaceToPay deployments. If your server
         still emits SHA-1, use :func:`verify_notification_legacy`.
    """
    expected_sig = payload.get("signature")
    if not isinstance(expected_sig, str):
        return False
    base = build_signature_base(payload, secret_key)
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()
    return hmac.compare_digest(digest, expected_sig)


def verify_notification_legacy(
    payload: dict[str, Any], secret_key: str
) -> bool:
    """Verify a SHA-1 hex signature (legacy / pre-migration servers).

    .. deprecated::
       **Prefer :func:`verify_notification` (SHA-256).** SHA-1 is
       cryptographically deprecated and only kept for interop with
       deployments still on the PHP SDK's default algorithm. Each call
       emits a :class:`DeprecationWarning`; open a ticket with PlaceToPay
       to enable SHA-256 webhook signing on your merchant account.
    """
    warnings.warn(
        "verify_notification_legacy uses SHA-1 and is retained only for "
        "backward compatibility with unmigrated servers. Prefer "
        "verify_notification (SHA-256). Scheduled for removal in SDK v2.",
        DeprecationWarning,
        stacklevel=2,
    )
    expected_sig = payload.get("signature")
    if not isinstance(expected_sig, str):
        return False
    base = build_signature_base(payload, secret_key)
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()
    return hmac.compare_digest(digest, expected_sig)
