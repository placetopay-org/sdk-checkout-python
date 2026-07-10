"""Authentication block builder.

Implements the SHA-256 auth algorithm locked in ARCHITECTURE.md §3.
Every request sent by :class:`~placetopay.checkout.client.Checkout` carries
one of these ``Auth`` blocks at the top level of the JSON body.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

NONCE_BYTES: int = 16
"""Fixed byte-length of the raw nonce. Locked across all PlaceToPay SDKs."""


class Auth(BaseModel):
    """Serializable auth block placed at the top of each request body.

    Field names are the exact on-the-wire keys (``login``, ``tranKey``,
    ``nonce``, ``seed``, ``additional``) — see ARCHITECTURE.md §3. Users
    of the SDK should *not* construct this directly; :class:`Checkout`
    injects it.

    The optional ``additional`` map mirrors the PHP SDK's ``authAdditional``
    config — extra merchant-specific metadata the gateway will record with
    the authenticated session. ``additional`` is NOT part of the signed
    digest; it is transmitted alongside it.
    """

    model_config = ConfigDict(populate_by_name=True, frozen=True)

    login: str
    tran_key: str = Field(alias="tranKey")
    nonce: str
    seed: str
    additional: dict[str, str] | None = None


def _now_iso_utc() -> str:
    """Current UTC timestamp in ISO-8601 with ``+00:00`` offset.

    We deliberately avoid :meth:`datetime.isoformat` in naive mode and
    avoid the ``Z`` suffix — the Java / .NET SDKs use the same
    ``+00:00`` form.
    """
    now = datetime.now(UTC).replace(microsecond=0)
    return now.isoformat()


def sign(
    login: str,
    secret_key: str,
    nonce: bytes,
    seed: str,
    additional: dict[str, str] | None = None,
) -> Auth:
    """Deterministically build an :class:`Auth` block.

    This is the exact algorithm all three PlaceToPay SDKs share
    (ARCHITECTURE.md §3):

    .. code-block:: text

        digest_in = raw_nonce ++ utf8(seed) ++ utf8(secret_key)
        tran_key  = base64(sha256(digest_in))
        wire_nonce = base64(raw_nonce)

    :param login:      merchant login identifier.
    :param secret_key: merchant secret (never transmitted; only hashed).
    :param nonce:      raw 16-byte nonce. **Must** be cryptographically
                       random (:func:`secrets.token_bytes`) in production;
                       tests pass a fixed value to reproduce the known
                       test vector.
    :param seed:       ISO-8601 timestamp string; included verbatim both
                       in the hash and on the wire.
    :param additional: optional map of extra auth metadata transmitted
                       alongside the digest (NOT part of the hash input).
    :raises ValueError: if ``nonce`` is not exactly 16 bytes.
    """
    if len(nonce) != NONCE_BYTES:
        raise ValueError(
            f"nonce must be exactly {NONCE_BYTES} bytes, got {len(nonce)}"
        )

    digest_in = nonce + seed.encode("utf-8") + secret_key.encode("utf-8")
    tran_key_b64 = base64.b64encode(hashlib.sha256(digest_in).digest()).decode("ascii")
    wire_nonce_b64 = base64.b64encode(nonce).decode("ascii")

    return Auth(
        login=login,
        tranKey=tran_key_b64,
        nonce=wire_nonce_b64,
        seed=seed,
        additional=additional,
    )


def new_auth(
    login: str,
    secret_key: str,
    additional: dict[str, str] | None = None,
) -> Auth:
    """Generate a fresh auth block with a secure random nonce and UTC seed.

    This is the normal production entry point; call it once per request.
    :func:`sign` is exposed separately for unit tests that pin nonce+seed.
    """
    return sign(
        login=login,
        secret_key=secret_key,
        nonce=secrets.token_bytes(NONCE_BYTES),
        seed=_now_iso_utc(),
        additional=additional,
    )
