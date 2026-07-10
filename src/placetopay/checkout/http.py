"""Thin HTTP transport around :mod:`requests`.

Responsibilities (ARCHITECTURE.md §4-9):

* Build and reuse one :class:`requests.Session` per :class:`Checkout` instance.
* Honor connect / read timeouts.
* Implement retry with exponential backoff + jitter on network errors,
  HTTP 5xx and 429 (honoring ``Retry-After``).
* Redact sensitive fields before DEBUG-logging.
* Translate HTTP status codes into the typed exception hierarchy.

The module is deliberately small and self-contained so users can bolt
instrumentation onto :class:`requests.Session` externally without
needing hooks in this file.
"""

from __future__ import annotations

import json
import logging
import platform
import random
import time
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import requests

from placetopay.checkout._version import __version__
from placetopay.checkout.errors import (
    AuthenticationError,
    NetworkError,
    NotFoundError,
    PlaceToPayError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from placetopay.checkout.models.common import ErrorResponse
from placetopay.checkout.settings import Settings

# ─── Redaction config (ARCHITECTURE §9) ───────────────────────────────
_REDACT_FULL: frozenset[str] = frozenset(
    {
        "trankey",
        "nonce",
        "cvv",
        "pin",
        "password",
        "secretkey",
        "code",  # on credit.code
    }
)
"""Field names (case-insensitive) whose values are fully masked as ``***``."""

_REDACT_LAST4: frozenset[str] = frozenset({"number", "token"})
"""Field names (case-insensitive) masked to last-4-digits only."""


def redact_body(body: Any) -> Any:
    """Return a deep copy of ``body`` with sensitive fields redacted.

    Safe for logging: never mutates the caller's dict.
    """
    if isinstance(body, dict):
        return {k: _redact_value(k, v) for k, v in body.items()}
    if isinstance(body, list):
        return [redact_body(item) for item in body]
    return body


def _redact_value(key: str, value: Any) -> Any:
    lowered = key.lower()
    if lowered in _REDACT_FULL:
        return "***"
    if lowered in _REDACT_LAST4 and isinstance(value, str) and len(value) > 4:
        return "*" * (len(value) - 4) + value[-4:]
    if isinstance(value, dict | list):
        return redact_body(value)
    return value


# ─── Retry-After parsing ──────────────────────────────────────────────
def parse_retry_after(value: str | None) -> timedelta | None:
    """Parse a ``Retry-After`` header into a ``timedelta``.

    Accepts either seconds or an HTTP-date; returns ``None`` for unparseable
    or absent values.
    """
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return timedelta(seconds=int(value))
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    delta = parsed - datetime.now(UTC)
    return delta if delta.total_seconds() > 0 else timedelta(seconds=0)


# ─── Transport ────────────────────────────────────────────────────────
class HttpTransport:
    """Owning wrapper around :class:`requests.Session`.

    One instance per :class:`Checkout` client. Thread-safe (the
    underlying Session is thread-safe for non-mutating requests, which
    is all the SDK does — config is immutable after construction).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session = requests.Session()
        self._logger = settings.logger or logging.getLogger("placetopay.checkout")

    # Exposed for advanced use (tracing middleware, custom adapters).
    @property
    def session(self) -> requests.Session:
        return self._session

    @property
    def settings(self) -> Settings:
        return self._settings

    def close(self) -> None:
        """Close the underlying HTTP session. Safe to call multiple times."""
        self._session.close()

    # ── Headers ───────────────────────────────────────────────────
    def build_headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        ua = self._user_agent()
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": ua,
        }
        headers.update(self._settings.additional_headers)
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        return headers

    def _user_agent(self) -> str:
        runtime = f"python/{platform.python_version()}"
        base = f"placetopay-sdk-python/{__version__} ({runtime})"
        if self._settings.user_agent_suffix:
            base += f" {self._settings.user_agent_suffix}"
        return base

    # ── Main entry ────────────────────────────────────────────────
    def post_json(
        self,
        path: str,
        body: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        timeout: tuple[float, float] | None = None,
    ) -> dict[str, Any]:
        """POST a JSON body and return the parsed JSON response.

        Handles retries, logging and error-translation. Always returns a
        dict; raises a :class:`PlaceToPayError` subclass on any failure.
        """
        url = self._settings.resolved_base_url + path
        headers = self.build_headers(idempotency_key=idempotency_key)
        effective_timeout = timeout or (
            self._settings.timeout_connect,
            self._settings.timeout_read,
        )

        self._log_request(url, headers, body)

        max_attempts = self._settings.retry_max_attempts
        last_exc: BaseException | None = None

        for attempt in range(1, max_attempts + 1):
            retryable: bool = False
            try:
                response = self._session.post(
                    url,
                    json=body,
                    headers=headers,
                    timeout=effective_timeout,
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                retryable = True
                self._log_retry(attempt, max_attempts, reason=str(exc))
            except requests.RequestException as exc:
                raise NetworkError(f"HTTP transport error: {exc}", cause=exc) from exc
            else:
                # 2xx → success path
                if 200 <= response.status_code < 300:
                    parsed = self._parse_body(response)
                    self._log_response(response.status_code, response.headers, parsed)
                    if not isinstance(parsed, dict):
                        raise PlaceToPayError(
                            "Unexpected non-JSON-object response",
                            raw_body=parsed,
                        )
                    return parsed

                # Retryable server-side status?
                retryable = response.status_code >= 500 or response.status_code == 429
                if not retryable or attempt == max_attempts:
                    raise self._build_error(response)

                # Honor Retry-After if present.
                retry_after = parse_retry_after(response.headers.get("Retry-After"))
                self._log_retry(
                    attempt,
                    max_attempts,
                    reason=f"HTTP {response.status_code}",
                )
                self._sleep_for(attempt, retry_after=retry_after)
                continue

            # retryable transport-level failure
            if retryable and attempt < max_attempts:
                self._sleep_for(attempt)
                continue
            # exhausted retries on a transport failure
            raise NetworkError(
                f"Network error after {attempt} attempt(s): {last_exc}",
                cause=last_exc,
            )

        # Defensive — unreachable, but keeps mypy happy.
        raise NetworkError(  # pragma: no cover
            "Unexpected fallthrough in retry loop",
            cause=last_exc,
        )

    # ── Retry backoff ────────────────────────────────────────────
    def _sleep_for(self, attempt: int, retry_after: timedelta | None = None) -> None:
        if retry_after is not None:
            # Cap to max_delay to avoid a server-directed DoS.
            cap = self._settings.retry_max_delay_ms / 1000.0
            wait = min(retry_after.total_seconds(), cap)
            self._sleep(max(0.0, wait))
            return

        initial = self._settings.retry_initial_delay_ms
        cap = self._settings.retry_max_delay_ms
        # exponential: initial * 2^(attempt-1)
        base = min(cap, initial * (2 ** (attempt - 1)))
        jittered = base * (0.5 + random.random() / 2.0)
        self._sleep(jittered / 1000.0)

    @staticmethod
    def _sleep(seconds: float) -> None:
        # Extracted so tests can monkey-patch.
        time.sleep(seconds)

    # ── Body parsing & error translation ─────────────────────────
    @staticmethod
    def _parse_body(response: requests.Response) -> Any:
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return response.text

    def _build_error(self, response: requests.Response) -> PlaceToPayError:
        parsed = self._parse_body(response)
        self._log_response(response.status_code, response.headers, parsed)

        status_obj = None
        reason: str | None = None
        message: str = f"HTTP {response.status_code}"
        request_id = response.headers.get("X-Request-Id")
        field_errors: list[dict[str, Any]] = []

        if isinstance(parsed, dict):
            try:
                err = ErrorResponse.model_validate(parsed)
                status_obj = err.status
                if status_obj is not None:
                    reason = status_obj.reason
                    if status_obj.message:
                        message = status_obj.message
                # Capture any field-level 'errors' list if present.
                extra_errors = err.extras.get("errors")
                if isinstance(extra_errors, list):
                    field_errors = [
                        fe for fe in extra_errors if isinstance(fe, dict)
                    ]
            except (ValueError, TypeError):
                # Pydantic ValidationError inherits from ValueError; both
                # mean the server's body did not match ErrorResponse — fall
                # back to status-only error info.
                pass

        kwargs: dict[str, Any] = {
            "status": status_obj,
            "reason": reason,
            "request_id": request_id,
            "raw_body": parsed,
        }
        code = response.status_code

        if code == 400:
            return ValidationError(message, field_errors=field_errors, **kwargs)
        if code == 401:
            return AuthenticationError(message, **kwargs)
        if code == 404:
            return NotFoundError(message, **kwargs)
        if code == 429:
            retry_after = parse_retry_after(response.headers.get("Retry-After"))
            return RateLimitError(message, retry_after=retry_after, **kwargs)
        if 500 <= code < 600:
            return ServerError(message, status_code=code, **kwargs)
        return PlaceToPayError(message, **kwargs)

    # ── Logging ──────────────────────────────────────────────────
    def _log_request(
        self,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any],
    ) -> None:
        if not self._logger.isEnabledFor(logging.DEBUG):
            return
        # Redact headers too (Authorization, X-Idempotency-Key are fine, but
        # we filter broadly in case consumers add sensitive ones).
        safe_headers = {
            k: ("***" if k.lower() in _REDACT_FULL else v) for k, v in headers.items()
        }
        self._logger.debug(
            "POST %s headers=%s body=%s",
            url,
            safe_headers,
            json.dumps(redact_body(body), default=str, sort_keys=True),
        )

    def _log_response(
        self,
        status_code: int,
        headers: Any,
        body: Any,
    ) -> None:
        if not self._logger.isEnabledFor(logging.DEBUG):
            return
        try:
            encoded = json.dumps(redact_body(body), default=str, sort_keys=True)
        except (TypeError, ValueError):
            encoded = repr(body)
        self._logger.debug(
            "← %d headers=%s body=%s",
            status_code,
            dict(headers),
            encoded,
        )

    def _log_retry(self, attempt: int, max_attempts: int, *, reason: str) -> None:
        if self._logger.isEnabledFor(logging.DEBUG):
            self._logger.debug(
                "retry %d/%d (reason=%s)", attempt, max_attempts, reason
            )


__all__ = [
    "HttpTransport",
    "parse_retry_after",
    "redact_body",
]
