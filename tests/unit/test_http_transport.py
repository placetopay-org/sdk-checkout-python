"""Unit tests for :mod:`placetopay.checkout.http`.

Closes the "silent failure" gap flagged during review — exercises retry
policy, ``Retry-After`` parsing, PCI/PII redaction and error-mapping
without requiring a live sandbox.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest
import requests
import responses

from placetopay.checkout.client import Checkout
from placetopay.checkout.environment import Environment
from placetopay.checkout.errors import (
    AuthenticationError,
    NetworkError,
    NotFoundError,
    PlaceToPayError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from placetopay.checkout.http import HttpTransport, parse_retry_after, redact_body
from placetopay.checkout.settings import Settings


def _record_sleep(calls: list[float], seconds: float) -> None:
    calls.append(seconds)


# ─── Fixtures ────────────────────────────────────────────────────────────
@pytest.fixture
def settings() -> Settings:
    return Settings(
        login="test-login",
        secret_key="test-secret",
        environment=Environment.SANDBOX,
        retry_max_attempts=3,
        retry_initial_delay_ms=1,   # near-zero so tests don't actually sleep
        retry_max_delay_ms=5,
        timeout_connect=5.0,
        timeout_read=5.0,
    )


@pytest.fixture
def transport(settings: Settings) -> HttpTransport:
    return HttpTransport(settings)


@pytest.fixture
def client(settings: Settings) -> Checkout:
    return Checkout(settings)


@pytest.fixture
def sandbox_url() -> str:
    return "https://checkout-test.placetopay.com"


# ─── Redaction ───────────────────────────────────────────────────────────
class TestRedaction:
    def test_auth_fields_are_fully_masked(self) -> None:
        body = {
            "auth": {
                "login": "visible",
                "tranKey": "super-secret-digest",
                "nonce": "super-secret-nonce",
                "seed": "2026-04-22T00:00:00+00:00",
            },
        }
        redacted = redact_body(body)
        assert redacted["auth"]["login"] == "visible"
        assert redacted["auth"]["tranKey"] == "***"
        assert redacted["auth"]["nonce"] == "***"
        assert redacted["auth"]["seed"] == body["auth"]["seed"]

    def test_card_pan_keeps_last_four(self) -> None:
        body = {"instrument": {"card": {"number": "4111111111111111", "cvv": "123"}}}
        redacted = redact_body(body)
        assert redacted["instrument"]["card"]["number"] == "************1111"
        assert redacted["instrument"]["card"]["cvv"] == "***"

    def test_token_keeps_last_four(self) -> None:
        body = {"instrument": {"token": {"token": "tk-abcdefghij"}}}
        redacted = redact_body(body)
        assert redacted["instrument"]["token"]["token"].endswith("ghij")
        assert redacted["instrument"]["token"]["token"].count("*") >= 4

    def test_pin_password_secretkey_fully_masked(self) -> None:
        body = {
            "instrument": {"pin": "1234", "password": "secret"},
            "secretKey": "never-log",
        }
        redacted = redact_body(body)
        assert redacted["instrument"]["pin"] == "***"
        assert redacted["instrument"]["password"] == "***"
        assert redacted["secretKey"] == "***"

    def test_nested_redaction_in_lists(self) -> None:
        body = {"payment": [{"instrument": {"card": {"cvv": "999"}}}]}
        redacted = redact_body(body)
        assert redacted["payment"][0]["instrument"]["card"]["cvv"] == "***"

    def test_non_sensitive_fields_pass_through(self) -> None:
        body = {"reference": "ORDER-1", "amount": {"currency": "COP", "total": 50000}}
        assert redact_body(body) == body

    def test_redact_does_not_mutate_input(self) -> None:
        original = {"auth": {"tranKey": "x"}}
        _ = redact_body(original)
        assert original["auth"]["tranKey"] == "x"  # unchanged


# ─── Retry-After parsing ────────────────────────────────────────────────
class TestParseRetryAfter:
    def test_none_returns_none(self) -> None:
        assert parse_retry_after(None) is None
        assert parse_retry_after("") is None

    def test_numeric_seconds(self) -> None:
        assert parse_retry_after("30") == timedelta(seconds=30)

    def test_http_date(self) -> None:
        future = datetime.now(UTC) + timedelta(seconds=60)
        result = parse_retry_after(format_datetime(future))
        assert result is not None
        # Allow small clock drift in the test.
        assert timedelta(seconds=50) <= result <= timedelta(seconds=65)

    def test_past_http_date_returns_zero(self) -> None:
        past = datetime.now(UTC) - timedelta(seconds=60)
        result = parse_retry_after(format_datetime(past))
        assert result == timedelta(seconds=0)

    def test_unparseable_returns_none(self) -> None:
        assert parse_retry_after("not-a-date-or-number") is None


# ─── Retry policy ────────────────────────────────────────────────────────
class TestRetryPolicy:
    def test_succeeds_after_one_failure(
        self, client: Checkout, sandbox_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Patch sleep so tests don't actually wait.
        monkeypatch.setattr(HttpTransport, "_sleep", staticmethod(lambda s: None))

        with responses.RequestsMock() as rsps:
            rsps.post(f"{sandbox_url}/api/session/42", status=500, json={})
            rsps.post(
                f"{sandbox_url}/api/session/42",
                status=200,
                json={
                    "requestId": 42,
                    "status": {"status": "OK", "date": "2026-04-22T00:00:00+00:00"},
                },
            )
            info = client.query_session(42)
            assert info.request_id == 42
            assert len(rsps.calls) == 2  # 1 failure + 1 retry

    def test_gives_up_after_max_attempts(
        self, client: Checkout, sandbox_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(HttpTransport, "_sleep", staticmethod(lambda s: None))

        with responses.RequestsMock() as rsps:
            rsps.post(
                f"{sandbox_url}/api/session/43",
                status=500,
                json={"status": {"status": "ERROR"}},
            )
            rsps.post(f"{sandbox_url}/api/session/43", status=500, json={})
            rsps.post(f"{sandbox_url}/api/session/43", status=500, json={})
            with pytest.raises(ServerError) as exc_info:
                client.query_session(43)
            assert exc_info.value.status_code == 500
            assert len(rsps.calls) == 3  # retry_max_attempts

    def test_does_not_retry_on_4xx(
        self, client: Checkout, sandbox_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(HttpTransport, "_sleep", staticmethod(lambda s: None))

        with responses.RequestsMock() as rsps:
            rsps.post(
                f"{sandbox_url}/api/session/44",
                status=400,
                json={"status": {"status": "FAILED", "reason": "?X", "message": "Bad"}},
            )
            with pytest.raises(ValidationError):
                client.query_session(44)
            assert len(rsps.calls) == 1  # no retry on 4xx

    def test_honors_retry_after_on_429(
        self, client: Checkout, sandbox_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        slept: list[float] = []
        monkeypatch.setattr(
            HttpTransport, "_sleep", staticmethod(lambda seconds: _record_sleep(slept, seconds))
        )

        with responses.RequestsMock() as rsps:
            rsps.post(
                f"{sandbox_url}/api/session/45",
                status=429,
                json={},
                headers={"Retry-After": "2"},
            )
            rsps.post(
                f"{sandbox_url}/api/session/45",
                status=200,
                json={
                    "requestId": 45,
                    "status": {"status": "OK", "date": "2026-04-22T00:00:00+00:00"},
                },
            )
            info = client.query_session(45)
            assert info.request_id == 45
            # First sleep is the Retry-After (clamped to max_delay_ms=5ms in test settings).
            assert slept, "expected at least one sleep"

    def test_network_failure_wraps_as_network_error(
        self, client: Checkout, sandbox_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(HttpTransport, "_sleep", staticmethod(lambda s: None))

        with responses.RequestsMock() as rsps:
            # Simulate a connection error on every attempt.
            rsps.post(f"{sandbox_url}/api/session/46", body=requests.ConnectionError("boom"))
            rsps.post(f"{sandbox_url}/api/session/46", body=requests.ConnectionError("boom"))
            rsps.post(f"{sandbox_url}/api/session/46", body=requests.ConnectionError("boom"))
            with pytest.raises(NetworkError):
                client.query_session(46)
            assert len(rsps.calls) == 3


# ─── Error mapping ───────────────────────────────────────────────────────
class TestErrorMapping:
    @pytest.mark.parametrize(
        "status_code,expected_type",
        [
            (400, ValidationError),
            (401, AuthenticationError),
            (404, NotFoundError),
            (429, RateLimitError),
            (500, ServerError),
            (502, ServerError),
            (418, PlaceToPayError),  # unknown mapping
        ],
    )
    def test_status_code_maps_to_typed_error(
        self,
        client: Checkout,
        sandbox_url: str,
        status_code: int,
        expected_type: type[BaseException],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(HttpTransport, "_sleep", staticmethod(lambda s: None))
        # 5xx and 429 retry up to max_attempts; 4xx & "unknown" fail on first
        # response.
        attempts = 3 if status_code >= 500 or status_code == 429 else 1
        with responses.RequestsMock() as rsps:
            for _ in range(attempts):
                rsps.post(
                    f"{sandbox_url}/api/session/99",
                    status=status_code,
                    json={
                        "status": {
                            "status": "ERROR",
                            "reason": "X1",
                            "message": "oops",
                            "date": "2026-04-22T00:00:00+00:00",
                        }
                    },
                )
            with pytest.raises(expected_type) as exc_info:
                client.query_session(99)

            # All typed errors carry the parsed Status object.
            if isinstance(exc_info.value, PlaceToPayError):
                assert exc_info.value.status is not None
                assert exc_info.value.status.reason == "X1"

    def test_rate_limit_error_exposes_retry_after(
        self,
        client: Checkout,
        sandbox_url: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(HttpTransport, "_sleep", staticmethod(lambda s: None))
        with responses.RequestsMock() as rsps:
            for _ in range(3):
                rsps.post(
                    f"{sandbox_url}/api/session/99",
                    status=429,
                    json={},
                    headers={"Retry-After": "7"},
                )
            with pytest.raises(RateLimitError) as exc_info:
                client.query_session(99)
            assert exc_info.value.retry_after == timedelta(seconds=7)


# ─── Auth injection on the wire ──────────────────────────────────────────
class TestAuthInjection:
    def test_every_request_carries_fresh_auth(
        self, client: Checkout, sandbox_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(HttpTransport, "_sleep", staticmethod(lambda s: None))
        with responses.RequestsMock() as rsps:
            rsps.post(
                f"{sandbox_url}/api/session/99",
                status=200,
                json={
                    "requestId": 99,
                    "status": {"status": "OK", "date": "2026-04-22T00:00:00+00:00"},
                },
            )
            rsps.post(
                f"{sandbox_url}/api/session/99",
                status=200,
                json={
                    "requestId": 99,
                    "status": {"status": "OK", "date": "2026-04-22T00:00:01+00:00"},
                },
            )
            client.query_session(99)
            client.query_session(99)

            req1 = json.loads(rsps.calls[0].request.body)
            req2 = json.loads(rsps.calls[1].request.body)
            assert "auth" in req1 and "auth" in req2
            assert req1["auth"]["login"] == "test-login"
            # Fresh nonces every request.
            assert req1["auth"]["nonce"] != req2["auth"]["nonce"]

    def test_additional_field_flows_to_wire(
        self, sandbox_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(HttpTransport, "_sleep", staticmethod(lambda s: None))

        client = Checkout(Settings(
            login="L",
            secret_key="S",
            environment=Environment.SANDBOX,
            auth_additional={"tenant": "acme", "channel": "web"},
        ))
        with responses.RequestsMock() as rsps:
            rsps.post(
                f"{sandbox_url}/api/session/77",
                status=200,
                json={
                    "requestId": 77,
                    "status": {"status": "OK", "date": "2026-04-22T00:00:00+00:00"},
                },
            )
            client.query_session(77)
            req = json.loads(rsps.calls[0].request.body)
            assert req["auth"]["additional"] == {"tenant": "acme", "channel": "web"}

    def test_user_agent_contains_sdk_identifier(
        self, client: Checkout, sandbox_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(HttpTransport, "_sleep", staticmethod(lambda s: None))
        with responses.RequestsMock() as rsps:
            rsps.post(
                f"{sandbox_url}/api/session/99",
                status=200,
                json={
                    "requestId": 99,
                    "status": {"status": "OK", "date": "2026-04-22T00:00:00+00:00"},
                },
            )
            client.query_session(99)
            ua = rsps.calls[0].request.headers.get("User-Agent", "")
            assert ua.startswith("placetopay-sdk-python/")
            assert "python/" in ua
