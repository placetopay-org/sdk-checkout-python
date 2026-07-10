"""Session models — create / query / cancel.

``CreateSessionRequest`` is the workhorse of the SDK; it covers the full
set of create-session features described in the OpenAPI spec including
the new ``type``/``autopay``/``metadata``/``dispersion``/``modifiers``/
``subscribe`` fields that the reference SDK did not model.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from placetopay.checkout.auth import Auth
from placetopay.checkout.models.common import (
    Amount,
    DispersionItem,
    Item,
    NameValuePair,
    PaymentModifier,
    Person,
    Recurring,
    Status,
    _CheckoutModel,
)
from placetopay.checkout.models.instrument import Instrument
from placetopay.checkout.models.transaction import (
    AutopayRequest,
    SubscriptionInformation,
    Transaction,
)


# ─── Payment (shared by create-session and collect) ───────────────────
class Payment(_CheckoutModel):
    reference: str = Field(..., max_length=32)
    description: str = Field(..., max_length=250)
    amount: Amount
    allow_partial: bool | None = False
    shipping: Person | None = None
    items: list[Item] | None = None
    fields: list[NameValuePair] | None = None
    recurring: Recurring | None = None
    subscribe: bool | None = False
    dispersion: list[DispersionItem] | None = None
    modifiers: list[PaymentModifier] | None = None
    agreement: str | None = None
    agreement_type: str | None = None
    instrument: Instrument | None = None


# ─── Subscription request (when a session subscribes only) ────────────
class SubscriptionRequest(_CheckoutModel):
    reference: str = Field(..., max_length=32)
    description: str = Field(..., max_length=250)
    fields: list[NameValuePair] | None = None


# ─── Create Session ───────────────────────────────────────────────────
class CreateSessionRequest(_CheckoutModel):
    """Request body for ``POST /api/session``.

    At least one of ``payment``, ``subscription`` or ``autopay`` must be
    supplied (ARCHITECTURE.md / OpenAPI ``oneOf`` constraint).
    """

    auth: Auth | None = None  # injected by the client
    locale: str | None = Field(default=None, pattern=r"^[a-z]{2}_[A-Z]{2}$")
    buyer: Person | None = None
    payer: Person | None = None
    payment: Payment | None = None
    subscription: SubscriptionRequest | None = None
    return_url: str = Field(..., max_length=255)
    cancel_url: str | None = Field(default=None, max_length=255)
    ip_address: str = Field(..., max_length=46)
    user_agent: str = Field(..., max_length=255)
    expiration: datetime | None = None
    payment_method: str | None = None
    skip_result: bool | None = False
    no_buyer_fill: bool | None = False
    capture_address: bool | None = False
    fields: list[NameValuePair] | None = None
    type: str | None = Field(
        default=None, description="Session type; one of {checkin, autopay}."
    )
    autopay: AutopayRequest | None = None
    metadata: dict[str, str] | None = Field(
        default=None,
        description=(
            "Free-form merchant metadata. Canonical keys the PlaceToPay API "
            "recognizes (API v2.26.8+): ``openingDate`` (ISO-8601 timestamp "
            "for when the customer opened the session/cart) and "
            "``beneficiaryId`` (identifier of the final beneficiary for "
            "regulated verticals). Extra keys are accepted and forwarded."
        ),
    )
    initiator_indicator: str | None = Field(
        default=None,
        description=(
            "API v2.27.1 — optional hint about who initiated the payment. "
            "Common values are ``CIT`` (cardholder-initiated transaction) "
            "and ``MIT`` (merchant-initiated transaction). Pass through as "
            "a string; the gateway validates the accepted vocabulary."
        ),
    )

    @model_validator(mode="after")
    def _require_one_of_payment_subscription_autopay(self) -> CreateSessionRequest:
        if (
            self.payment is None
            and self.subscription is None
            and self.autopay is None
        ):
            raise ValueError(
                "CreateSessionRequest requires one of `payment`, `subscription`, or `autopay`."
            )
        return self


class CreateSessionResponse(_CheckoutModel):
    status: Status
    request_id: int
    process_url: str


# ─── Session Information (query / collect response) ─────────────────
class SessionInformation(_CheckoutModel):
    """Response body for ``POST /api/session/{requestId}`` and ``POST /api/collect``."""

    request_id: int
    status: Status
    request: dict[str, Any] | None = None
    payment: list[Transaction] | None = None
    subscription: SubscriptionInformation | None = None
    autopay: list[dict[str, Any]] | None = None

    # ─── Transaction helpers (mirror PHP RedirectInformation API) ──
    def last_transaction(self, approved: bool = False) -> Transaction | None:
        """Most-recent transaction on this session.

        When ``approved=True``, walks the list and returns the first
        approved transaction (matching the PHP SDK's
        ``lastTransaction($approved)`` behavior). When ``False``, simply
        returns the last element of ``payment``.
        """
        if not self.payment:
            return None
        if approved:
            for txn in self.payment:
                if txn.is_approved:
                    return txn
            return None
        return self.payment[-1]

    def last_approved_transaction(self) -> Transaction | None:
        """Shortcut for :meth:`last_transaction` with ``approved=True``."""
        return self.last_transaction(approved=True)

    def last_authorization(self) -> str:
        """The authorization code of the last approved transaction, or ``""``.

        Safe to call even when there are no approved transactions yet.
        """
        txn = self.last_approved_transaction()
        if txn is None or txn.authorization is None:
            return ""
        return txn.authorization


class CancelSessionResponse(_CheckoutModel):
    status: Status
    session: SessionInformation | None = None


__all__ = [
    "CancelSessionResponse",
    "CreateSessionRequest",
    "CreateSessionResponse",
    "Payment",
    "SessionInformation",
    "SubscriptionRequest",
]
