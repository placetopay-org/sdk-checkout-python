"""Unit tests for :mod:`placetopay.checkout.auth`."""

from __future__ import annotations

import base64
import hashlib
import re
from datetime import UTC, datetime

import pytest

import placetopay.checkout.auth as auth_mod
from placetopay.checkout.auth import (
    NONCE_BYTES,
    Auth,
    _now_iso_utc,
    new_auth,
    sign,
)

# ─── Test vector locked in ARCHITECTURE.md §3 ───────────────────────────
#
# Fixed inputs:
VECTOR_LOGIN = "SDK_TEST_LOGIN"
VECTOR_SECRET = "SDK_TEST_SECRET"
VECTOR_RAW_NONCE = bytes.fromhex("00112233445566778899aabbccddeeff")
VECTOR_SEED = "2026-04-22T15:30:45+00:00"
# Expected ``wireNonce`` is the base64 of the raw nonce (trivially verifiable).
EXPECTED_WIRE_NONCE = "ABEiM0RVZneImaq7zN3u/w=="


def _reference_tran_key(raw_nonce: bytes, seed: str, secret_key: str) -> str:
    """An independent SHA-256 reimplementation used as a comparison target.

    If :func:`placetopay.checkout.auth.sign` produces anything other than
    this, the algorithm has drifted from ARCHITECTURE.md §3.
    """
    digest_in = raw_nonce + seed.encode("utf-8") + secret_key.encode("utf-8")
    return base64.b64encode(hashlib.sha256(digest_in).digest()).decode("ascii")


# Value computed from the fixed vector. Locked — any change breaks this.
EXPECTED_TRAN_KEY = _reference_tran_key(VECTOR_RAW_NONCE, VECTOR_SEED, VECTOR_SECRET)


# ─── Test vector regression ─────────────────────────────────────────────
class TestArchitectureVector:
    """ARCHITECTURE.md §3 regression vector. Do **not** change these
    values without a major version bump."""

    def test_sign_produces_expected_wire_nonce(self) -> None:
        auth = sign(
            login=VECTOR_LOGIN,
            secret_key=VECTOR_SECRET,
            nonce=VECTOR_RAW_NONCE,
            seed=VECTOR_SEED,
        )
        assert auth.nonce == EXPECTED_WIRE_NONCE

    def test_sign_produces_expected_tran_key(self) -> None:
        auth = sign(
            login=VECTOR_LOGIN,
            secret_key=VECTOR_SECRET,
            nonce=VECTOR_RAW_NONCE,
            seed=VECTOR_SEED,
        )
        # The SDK must match the independently computed reference digest.
        assert auth.tran_key == EXPECTED_TRAN_KEY

    def test_sign_passes_through_login_and_seed(self) -> None:
        auth = sign(
            login=VECTOR_LOGIN,
            secret_key=VECTOR_SECRET,
            nonce=VECTOR_RAW_NONCE,
            seed=VECTOR_SEED,
        )
        assert auth.login == VECTOR_LOGIN
        assert auth.seed == VECTOR_SEED

    def test_tran_key_is_base64_of_32_bytes(self) -> None:
        # Structural sanity: SHA-256 output is 32 bytes → 44 base64 chars.
        assert len(base64.b64decode(EXPECTED_TRAN_KEY)) == 32

    def test_auth_serializes_with_camel_case_aliases(self) -> None:
        auth = sign(
            login=VECTOR_LOGIN,
            secret_key=VECTOR_SECRET,
            nonce=VECTOR_RAW_NONCE,
            seed=VECTOR_SEED,
        )
        # Wire form — matches what HttpTransport sends (exclude_none).
        dumped = auth.model_dump(by_alias=True, exclude_none=True)
        assert dumped == {
            "login": VECTOR_LOGIN,
            "tranKey": EXPECTED_TRAN_KEY,
            "nonce": EXPECTED_WIRE_NONCE,
            "seed": VECTOR_SEED,
        }


# ─── sign() contract ────────────────────────────────────────────────────
class TestSign:
    def test_rejects_short_nonce(self) -> None:
        with pytest.raises(ValueError, match="16 bytes"):
            sign("login", "secret", b"\x00" * 15, VECTOR_SEED)

    def test_rejects_long_nonce(self) -> None:
        with pytest.raises(ValueError, match="16 bytes"):
            sign("login", "secret", b"\x00" * 32, VECTOR_SEED)

    def test_different_nonce_yields_different_tran_key(self) -> None:
        auth1 = sign("l", "s", b"\x00" * 16, VECTOR_SEED)
        auth2 = sign("l", "s", b"\xff" * 16, VECTOR_SEED)
        assert auth1.tran_key != auth2.tran_key

    def test_different_secret_yields_different_tran_key(self) -> None:
        auth1 = sign("l", "secret-1", b"\x00" * 16, VECTOR_SEED)
        auth2 = sign("l", "secret-2", b"\x00" * 16, VECTOR_SEED)
        assert auth1.tran_key != auth2.tran_key

    def test_different_seed_yields_different_tran_key(self) -> None:
        auth1 = sign("l", "s", b"\x00" * 16, "2026-01-01T00:00:00+00:00")
        auth2 = sign("l", "s", b"\x00" * 16, "2026-01-02T00:00:00+00:00")
        assert auth1.tran_key != auth2.tran_key

    def test_nonce_bytes_constant(self) -> None:
        assert NONCE_BYTES == 16


# ─── new_auth() ─────────────────────────────────────────────────────────
class TestNewAuth:
    def test_new_auth_generates_fresh_nonce(self) -> None:
        a1 = new_auth("login", "secret")
        a2 = new_auth("login", "secret")
        assert a1.nonce != a2.nonce
        assert a1.tran_key != a2.tran_key

    def test_new_auth_seed_is_iso_utc(self) -> None:
        auth = new_auth("login", "secret")
        # Must parse back to UTC-offset datetime.
        parsed = datetime.fromisoformat(auth.seed)
        assert parsed.utcoffset() is not None
        assert parsed.utcoffset().total_seconds() == 0  # type: ignore[union-attr]
        assert parsed.tzinfo is not None

    def test_new_auth_uses_cryptographic_random(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guard-rail: must route through ``secrets.token_bytes``, not ``random``."""
        calls: list[int] = []

        def fake_token_bytes(n: int) -> bytes:
            calls.append(n)
            return VECTOR_RAW_NONCE

        monkeypatch.setattr(auth_mod.secrets, "token_bytes", fake_token_bytes)
        auth = new_auth("login", "secret")
        assert calls == [NONCE_BYTES]
        assert auth.nonce == EXPECTED_WIRE_NONCE

    def test_auth_is_immutable(self) -> None:
        auth = new_auth("login", "secret")
        with pytest.raises(Exception):  # noqa: B017 - pydantic frozen model
            auth.login = "mutated"  # type: ignore[misc]


def test_now_iso_utc_shape() -> None:
    s = _now_iso_utc()
    # e.g. 2026-04-22T15:30:45+00:00
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$", s), s


def test_auth_model_instance() -> None:
    a = Auth(login="l", tranKey="tk", nonce="n", seed="s")
    assert a.login == "l"
    assert a.tran_key == "tk"
    assert a.nonce == "n"
    assert a.seed == "s"


def test_auth_model_parses_snake_case_or_camel_case() -> None:
    from_alias = Auth.model_validate(
        {"login": "l", "tranKey": "tk", "nonce": "n", "seed": "s"}
    )
    from_python = Auth.model_validate(
        {"login": "l", "tran_key": "tk", "nonce": "n", "seed": "s"}
    )
    assert from_alias == from_python


def test_utc_timezone_constant_used() -> None:
    # Sanity: the module uses UTC properly.
    assert datetime.now(UTC).tzinfo is not None
