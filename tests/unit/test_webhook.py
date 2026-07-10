"""Unit tests for :mod:`placetopay.checkout.webhook`."""

from __future__ import annotations

import hashlib

import pytest

from placetopay.checkout.webhook import (
    build_signature_base,
    verify_notification,
    verify_notification_legacy,
)

SECRET = "test-secret"
PAYLOAD_BASE = {
    "requestId": 12345,
    "reference": "ORDER-1",
    "status": {
        "status": "APPROVED",
        "reason": "00",
        "message": "Approved",
        "date": "2026-04-22T15:30:45+00:00",
    },
}


def _sign(algorithm: str, payload: dict[str, object]) -> str:
    base = build_signature_base(payload, SECRET)
    return hashlib.new(algorithm, base.encode("utf-8")).hexdigest()


# ─── build_signature_base ───────────────────────────────────────────────
class TestBuildSignatureBase:
    def test_concatenates_in_canonical_order(self) -> None:
        # requestId || status.status || status.date || secret_key
        base = build_signature_base(PAYLOAD_BASE, SECRET)
        assert base == "12345APPROVED2026-04-22T15:30:45+00:00test-secret"

    def test_missing_fields_become_empty_string(self) -> None:
        payload: dict[str, object] = {"requestId": 1, "status": {}}
        base = build_signature_base(payload, SECRET)
        assert base == "1test-secret"

    def test_none_fields_become_empty_string(self) -> None:
        payload: dict[str, object] = {
            "requestId": 7,
            "status": {"status": None, "date": None},
        }
        base = build_signature_base(payload, SECRET)
        assert base == "7test-secret"

    def test_raises_keyerror_for_missing_request_id(self) -> None:
        with pytest.raises(KeyError):
            build_signature_base({"status": {}}, SECRET)

    def test_raises_type_error_when_status_not_dict(self) -> None:
        with pytest.raises(TypeError):
            build_signature_base({"requestId": 1, "status": "oops"}, SECRET)


# ─── verify_notification (SHA-256) ──────────────────────────────────────
class TestVerifyNotificationSha256:
    def test_valid_signature(self) -> None:
        payload = dict(PAYLOAD_BASE)
        payload["signature"] = _sign("sha256", payload)
        assert verify_notification(payload, SECRET) is True

    def test_tampered_status_fails(self) -> None:
        original = dict(PAYLOAD_BASE)
        original["signature"] = _sign("sha256", original)
        # Tamper the status AFTER signing.
        tampered = {**original, "status": {**original["status"], "status": "REJECTED"}}
        assert verify_notification(tampered, SECRET) is False

    def test_wrong_secret_fails(self) -> None:
        payload = dict(PAYLOAD_BASE)
        payload["signature"] = _sign("sha256", payload)
        assert verify_notification(payload, "wrong-secret") is False

    def test_missing_signature_returns_false(self) -> None:
        payload = dict(PAYLOAD_BASE)  # no "signature"
        assert verify_notification(payload, SECRET) is False

    def test_non_string_signature_returns_false(self) -> None:
        payload = {**PAYLOAD_BASE, "signature": 12345}
        assert verify_notification(payload, SECRET) is False

    def test_sha1_signature_is_rejected_by_sha256_verifier(self) -> None:
        payload = dict(PAYLOAD_BASE)
        payload["signature"] = _sign("sha1", payload)
        assert verify_notification(payload, SECRET) is False


# ─── verify_notification_legacy (SHA-1) ─────────────────────────────────
class TestVerifyNotificationLegacy:
    def test_valid_sha1_signature(self) -> None:
        payload = dict(PAYLOAD_BASE)
        payload["signature"] = _sign("sha1", payload)
        assert verify_notification_legacy(payload, SECRET) is True

    def test_tampered_payload_fails(self) -> None:
        original = dict(PAYLOAD_BASE)
        original["signature"] = _sign("sha1", original)
        tampered = {**original, "status": {**original["status"], "status": "REJECTED"}}
        assert verify_notification_legacy(tampered, SECRET) is False

    def test_sha256_signature_is_rejected_by_legacy_verifier(self) -> None:
        payload = dict(PAYLOAD_BASE)
        payload["signature"] = _sign("sha256", payload)
        assert verify_notification_legacy(payload, SECRET) is False

    def test_missing_signature_returns_false(self) -> None:
        payload = dict(PAYLOAD_BASE)
        assert verify_notification_legacy(payload, SECRET) is False

    def test_non_string_signature_returns_false(self) -> None:
        payload = {**PAYLOAD_BASE, "signature": None}
        assert verify_notification_legacy(payload, SECRET) is False
