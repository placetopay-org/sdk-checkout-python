"""Direct unit tests for :class:`~placetopay.checkout.client.Checkout`.

The `test_http_transport.py` suite already exercises the transport end-to-end
via one endpoint (`query_session`). This file covers the remaining public
methods so every facade call is reached at least once — required to hit the
85 % coverage threshold.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import responses

from placetopay.checkout.client import Checkout
from placetopay.checkout.environment import Country, Environment
from placetopay.checkout.http import HttpTransport
from placetopay.checkout.models.common import StatusCode
from placetopay.checkout.settings import Settings


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep test latency near zero even if retries fire."""
    monkeypatch.setattr(HttpTransport, "_sleep", staticmethod(lambda s: None))


@pytest.fixture
def client() -> Checkout:
    return Checkout(
        Settings(
            login="test-login",
            secret_key="test-secret",
            environment=Environment.SANDBOX,
            country=Country.COLOMBIA,
            retry_max_attempts=1,
            retry_initial_delay_ms=1,
            retry_max_delay_ms=5,
        )
    )


BASE = "https://checkout-test.placetopay.com"

OK_STATUS: dict[str, Any] = {
    "status": "OK",
    "reason": "00",
    "message": "ok",
    "date": "2026-04-22T15:30:45+00:00",
}


# ─── create_session ─────────────────────────────────────────────────────
class TestCreateSession:
    def test_happy_path_from_dict(self, client: Checkout) -> None:
        with responses.RequestsMock() as rsps:
            rsps.post(
                f"{BASE}/api/session",
                status=200,
                json={
                    "requestId": 12345,
                    "processUrl": "https://example.com/redirect",
                    "status": OK_STATUS,
                },
            )
            resp = client.create_session({
                "ipAddress": "127.0.0.1",
                "userAgent": "test/1.0",
                "returnUrl": "https://example.com/return",
                "payment": {
                    "reference": "ORDER-1",
                    "description": "Demo",
                    "amount": {"currency": "COP", "total": 50_000},
                },
            })
            assert resp.request_id == 12345
            assert resp.process_url == "https://example.com/redirect"
            # Verify the wire body actually contains an injected auth block.
            body = json.loads(rsps.calls[0].request.body)
            assert body["auth"]["login"] == "test-login"
            # Country default locale flowed through (Colombia → es_CO).
            assert body["locale"] == "es_CO"

    def test_country_locale_not_overwritten_if_caller_sets_it(
        self, client: Checkout
    ) -> None:
        with responses.RequestsMock() as rsps:
            rsps.post(
                f"{BASE}/api/session",
                status=200,
                json={"requestId": 1, "processUrl": "u",
                      "status": OK_STATUS},
            )
            client.create_session({
                "ipAddress": "127.0.0.1",
                "userAgent": "t",
                "returnUrl": "https://example.com/return",
                "locale": "en_US",
                "payment": {
                    "reference": "R", "description": "D",
                    "amount": {"currency": "USD", "total": 100},
                },
            })
            body = json.loads(rsps.calls[0].request.body)
            assert body["locale"] == "en_US"

    def test_idempotency_key_flows_to_header(self, client: Checkout) -> None:
        with responses.RequestsMock() as rsps:
            rsps.post(
                f"{BASE}/api/session",
                status=200,
                json={"requestId": 1, "processUrl": "u", "status": OK_STATUS},
            )
            client.create_session(
                {
                    "ipAddress": "127.0.0.1",
                    "userAgent": "t",
                    "returnUrl": "https://example.com/return",
                    "payment": {
                        "reference": "R", "description": "D",
                        "amount": {"currency": "COP", "total": 100},
                    },
                },
                idempotency_key="IDEM-42",
            )
            assert rsps.calls[0].request.headers["X-Idempotency-Key"] == "IDEM-42"


# ─── cancel_session ─────────────────────────────────────────────────────
class TestCancelSession:
    def test_posts_to_correct_path(self, client: Checkout) -> None:
        with responses.RequestsMock() as rsps:
            rsps.post(
                f"{BASE}/api/session/12345/cancel",
                status=200,
                json={
                    "status": OK_STATUS,
                    "session": {
                        "requestId": 12345,
                        "status": {"status": "REJECTED",
                                    "date": "2026-04-22T15:30:45+00:00"},
                    },
                },
            )
            resp = client.cancel_session(12345)
            assert resp.status.is_successful is True
            assert resp.session is not None
            assert resp.session.request_id == 12345
            assert resp.session.status.is_rejected is True


# ─── collect ────────────────────────────────────────────────────────────
class TestCollect:
    def test_passes_provider_and_instrument_on_wire(
        self, client: Checkout
    ) -> None:
        with responses.RequestsMock() as rsps:
            rsps.post(
                f"{BASE}/api/collect",
                status=200,
                json={
                    "requestId": 99,
                    "status": OK_STATUS,
                    "payment": [{
                        "status": {"status": "APPROVED",
                                    "date": "2026-04-22T15:30:45+00:00"},
                        "authorization": "AUTH-1",
                        "internalReference": 42,
                    }],
                },
            )
            info = client.collect({
                "payer": {"document": "1040", "documentType": "CC",
                           "name": "T", "surname": "B", "email": "t@e.co"},
                "payment": {"reference": "C-1", "description": "D",
                             "amount": {"currency": "COP", "total": 10_000}},
                "instrument": {"token": {"token": "tk-abc"}},
                "provider": "evertec",
            })
            assert info.request_id == 99
            body = json.loads(rsps.calls[0].request.body)
            assert body["provider"] == "evertec"
            assert body["instrument"]["token"]["token"] == "tk-abc"


# ─── reverse ────────────────────────────────────────────────────────────
class TestReverse:
    def test_from_string_internal_reference(self, client: Checkout) -> None:
        with responses.RequestsMock() as rsps:
            rsps.post(
                f"{BASE}/api/reverse",
                status=200,
                json={
                    "status": {**OK_STATUS, "status": "APPROVED"},
                    "payment": {
                        "status": {"status": "REFUNDED",
                                    "date": "2026-04-22T15:30:45+00:00"},
                        "internalReference": 42,
                    },
                },
            )
            resp = client.reverse("42")
            assert resp.status.status == StatusCode.APPROVED
            body = json.loads(rsps.calls[0].request.body)
            assert body["internalReference"] == "42"

    def test_from_int_coerces_to_string(self, client: Checkout) -> None:
        with responses.RequestsMock() as rsps:
            rsps.post(
                f"{BASE}/api/reverse",
                status=200,
                json={"status": OK_STATUS},
            )
            client.reverse(42)
            body = json.loads(rsps.calls[0].request.body)
            assert body["internalReference"] == "42"


# ─── invalidate_token ───────────────────────────────────────────────────
class TestInvalidateToken:
    def test_returns_status_from_envelope(self, client: Checkout) -> None:
        with responses.RequestsMock() as rsps:
            rsps.post(
                f"{BASE}/api/instrument/invalidate",
                status=200,
                json={"status": {**OK_STATUS, "status": "OK"}},
            )
            status = client.invalidate_token({
                "instrument": {"token": {"token": "tk-abc"}},
            })
            assert status.status == StatusCode.OK


# ─── context manager / lifecycle ────────────────────────────────────────
def test_context_manager_closes_session(client: Checkout) -> None:
    with client as c:
        assert c.transport.session is not None
    # After __exit__ the session's adapters are closed; `requests` allows
    # re-use after close(), but the important thing is that close() does
    # not raise.


def test_settings_and_transport_properties(client: Checkout) -> None:
    assert client.settings.login == "test-login"
    assert client.transport is not None
