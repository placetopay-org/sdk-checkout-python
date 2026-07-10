"""Typed exception hierarchy.

See ARCHITECTURE.md §8. Every HTTP/transport failure the SDK raises is a
subclass of :class:`PlaceToPayError`; callers can choose to catch the
base class or narrow to the specific subtype.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from placetopay.checkout.models.common import Status


class PlaceToPayError(Exception):
    """Base class for every error raised by the SDK.

    Attributes:
        status:     parsed ``Status`` object from the API response, if any.
        reason:     short machine-readable reason code.
        message:    human-readable description.
        request_id: API request identifier, when exposed by the gateway.
        raw_body:   decoded response body (dict or str) — for debugging only;
                    do not branch on this in production code.
    """

    def __init__(
        self,
        message: str,
        *,
        status: Status | None = None,
        reason: str | None = None,
        request_id: str | None = None,
        raw_body: Any = None,
    ) -> None:
        super().__init__(message)
        self.message: str = message
        self.status: Status | None = status
        self.reason: str | None = reason
        self.request_id: str | None = request_id
        self.raw_body: Any = raw_body

    def __repr__(self) -> str:  # pragma: no cover - debug repr only
        return (
            f"{self.__class__.__name__}("
            f"message={self.message!r}, reason={self.reason!r}, "
            f"request_id={self.request_id!r})"
        )


class AuthenticationError(PlaceToPayError):
    """HTTP 401. Credentials or digest mismatch; check ``login``/``secret_key``."""


class ValidationError(PlaceToPayError):
    """HTTP 400. Request body failed server-side validation."""

    def __init__(
        self,
        message: str,
        *,
        field_errors: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.field_errors: list[dict[str, Any]] = field_errors or []


class NotFoundError(PlaceToPayError):
    """HTTP 404. Requested resource (session, transaction…) does not exist."""


class RateLimitError(PlaceToPayError):
    """HTTP 429. Caller is being rate-limited.

    Exposes :attr:`retry_after` as a :class:`datetime.timedelta` derived
    from the server's ``Retry-After`` header when present.
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after: timedelta | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.retry_after: timedelta | None = retry_after


class NetworkError(PlaceToPayError):
    """Connection / DNS / TLS / read-timeout failure.

    Wraps the underlying transport exception in :attr:`cause` so callers
    can inspect it for diagnostics without depending on ``requests``
    directly.
    """

    def __init__(
        self,
        message: str,
        *,
        cause: BaseException | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.cause: BaseException | None = cause
        if cause is not None:
            self.__cause__ = cause


class ServerError(PlaceToPayError):
    """HTTP 5xx. The gateway failed to process the request."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.status_code: int = status_code


__all__ = [
    "AuthenticationError",
    "NetworkError",
    "NotFoundError",
    "PlaceToPayError",
    "RateLimitError",
    "ServerError",
    "ValidationError",
]
