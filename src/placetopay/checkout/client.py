"""The main :class:`Checkout` client.

Construct one per set of credentials and share across threads — the
underlying :class:`HttpTransport` pools its :class:`requests.Session`
so this is the fast path.

Every operation accepts either a typed request model *or* a plain
``dict``; the SDK coerces dicts into the corresponding model, injects
auth, sends the request and returns a typed response model.
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from placetopay.checkout.auth import Auth, new_auth
from placetopay.checkout.http import HttpTransport
from placetopay.checkout.models.collect import CollectRequest
from placetopay.checkout.models.common import Status
from placetopay.checkout.models.instrument import InvalidateTokenRequest
from placetopay.checkout.models.reverse import ReverseRequest, ReverseResponse
from placetopay.checkout.models.session import (
    CancelSessionResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    SessionInformation,
)
from placetopay.checkout.settings import Settings

M = TypeVar("M", bound=BaseModel)


class Checkout:
    """High-level client for the PlaceToPay Checkout API.

    Construction is cheap but the HTTP session it owns is not — prefer
    one long-lived instance per process.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._transport = HttpTransport(settings)

    # ── Lifecycle ────────────────────────────────────────────────
    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def transport(self) -> HttpTransport:
        """The underlying HTTP transport (advanced users: add adapters here)."""
        return self._transport

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._transport.close()

    def __enter__(self) -> Checkout:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    # ── Operations ───────────────────────────────────────────────
    def create_session(
        self,
        request: CreateSessionRequest | dict[str, Any],
        *,
        idempotency_key: str | None = None,
        timeout: tuple[float, float] | None = None,
    ) -> CreateSessionResponse:
        """``POST /api/session`` — create a new checkout session.

        Apply the country's default locale/currency if the caller
        did not supply them explicitly.
        """
        req = self._coerce(request, CreateSessionRequest)
        req = self._apply_country_defaults(req)
        body = self._serialize_with_auth(req)
        raw = self._transport.post_json(
            "/api/session",
            body,
            idempotency_key=idempotency_key,
            timeout=timeout,
        )
        return CreateSessionResponse.model_validate(raw)

    def query_session(
        self,
        request_id: int | str,
        *,
        timeout: tuple[float, float] | None = None,
    ) -> SessionInformation:
        """``POST /api/session/{requestId}`` — fetch a session's status."""
        body = self._auth_only_body()
        raw = self._transport.post_json(
            f"/api/session/{request_id}",
            body,
            timeout=timeout,
        )
        return SessionInformation.model_validate(raw)

    def cancel_session(
        self,
        request_id: int | str,
        *,
        timeout: tuple[float, float] | None = None,
    ) -> CancelSessionResponse:
        """``POST /api/session/{requestId}/cancel`` — cancel a pending session."""
        body = self._auth_only_body()
        raw = self._transport.post_json(
            f"/api/session/{request_id}/cancel",
            body,
            timeout=timeout,
        )
        return CancelSessionResponse.model_validate(raw)

    def collect(
        self,
        request: CollectRequest | dict[str, Any],
        *,
        idempotency_key: str | None = None,
        timeout: tuple[float, float] | None = None,
    ) -> SessionInformation:
        """``POST /api/collect`` — direct charge on a stored instrument."""
        req = self._coerce(request, CollectRequest)
        if req.locale is None and self._settings.country is not None:
            req = req.model_copy(update={"locale": self._settings.get_default_locale()})
        body = self._serialize_with_auth(req)
        raw = self._transport.post_json(
            "/api/collect",
            body,
            idempotency_key=idempotency_key,
            timeout=timeout,
        )
        return SessionInformation.model_validate(raw)

    def reverse(
        self,
        internal_reference: str | int | ReverseRequest | dict[str, Any],
        *,
        idempotency_key: str | None = None,
        timeout: tuple[float, float] | None = None,
    ) -> ReverseResponse:
        """``POST /api/reverse`` — reverse a previously approved transaction.

        Accepts either a bare ``internal_reference`` string/int or a full
        :class:`ReverseRequest` / dict.
        """
        if isinstance(internal_reference, ReverseRequest):
            req = internal_reference
        elif isinstance(internal_reference, dict):
            req = ReverseRequest.model_validate(internal_reference)
        else:
            req = ReverseRequest(internal_reference=str(internal_reference))
        body = self._serialize_with_auth(req)
        raw = self._transport.post_json(
            "/api/reverse",
            body,
            idempotency_key=idempotency_key,
            timeout=timeout,
        )
        return ReverseResponse.model_validate(raw)

    def invalidate_token(
        self,
        request: InvalidateTokenRequest | dict[str, Any],
        *,
        timeout: tuple[float, float] | None = None,
    ) -> Status:
        """``POST /api/instrument/invalidate`` — revoke a stored token."""
        req = self._coerce(request, InvalidateTokenRequest)
        body = self._serialize_with_auth(req)
        raw = self._transport.post_json(
            "/api/instrument/invalidate",
            body,
            timeout=timeout,
        )
        # The response envelope is ``{ "status": {...} }``.
        status_payload = raw.get("status", raw)
        return Status.model_validate(status_payload)

    # ── Internal helpers ─────────────────────────────────────────
    @staticmethod
    def _coerce(value: M | dict[str, Any], model: type[M]) -> M:
        if isinstance(value, model):
            return value
        if isinstance(value, dict):
            return model.model_validate(value)
        raise TypeError(
            f"Expected {model.__name__} or dict, got {type(value).__name__}"
        )

    def _new_auth(self) -> Auth:
        return new_auth(
            login=self._settings.login,
            secret_key=self._settings.get_secret_key(),
            additional=self._settings.auth_additional,
        )

    def _auth_only_body(self) -> dict[str, Any]:
        return {"auth": self._new_auth().model_dump(by_alias=True, exclude_none=True)}

    def _serialize_with_auth(self, request: BaseModel) -> dict[str, Any]:
        """Inject a fresh auth block and serialize the request to a JSON-ready dict."""
        updated = request.model_copy(update={"auth": self._new_auth()})
        return updated.model_dump(by_alias=True, exclude_none=True)

    def _apply_country_defaults(
        self, req: CreateSessionRequest
    ) -> CreateSessionRequest:
        country = self._settings.country
        if country is None:
            return req

        updates: dict[str, Any] = {}
        if req.locale is None:
            updates["locale"] = self._settings.get_default_locale()

        # Default currency in payment.amount if missing. Pydantic model
        # already demands currency (it's a required string), so we only
        # override when it's an obviously-empty placeholder — we cannot
        # usefully default it because the AmountBase validator rejects
        # ``currency=""``. Keep the door open for a future convenience
        # that constructs Amount-less payloads for callers.
        return req.model_copy(update=updates)


__all__ = ["Checkout"]
