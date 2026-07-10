"""Transaction and subscription models (response side, mostly).

Also defines :class:`AutopayRequest` which travels *in* the
``CreateSessionRequest`` body when ``type=autopay``.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from placetopay.checkout.models.common import (
    Amount,
    AmountConversion,
    Discount,
    NameValuePair,
    Status,
    _CheckoutModel,
)


class SubscriptionInformation(_CheckoutModel):
    """Information returned by the gateway for a subscription result."""

    type: str | None = None
    status: Status | None = None
    instrument: list[NameValuePair] | None = None


class ProcessorField(_CheckoutModel):
    """Gateway processor metadata field.

    In practice, ``value`` can be scalar, boolean, or object depending on
    acquirer/processor integrations, so we keep it as ``Any`` on response
    models.
    """

    keyword: str | None = None
    value: Any | None = None
    display_on: str | None = None


class Transaction(_CheckoutModel):
    """An individual payment transaction within a session.

    Fields mirror the OpenAPI ``Transaction`` schema. Anything not sent
    back by the server stays ``None``.
    """

    status: Status | None = None
    reference: str | None = None
    internal_reference: int | None = None
    payment_method: str | None = None
    payment_method_name: str | None = None
    issuer_name: str | None = None
    amount: AmountConversion | None = None
    authorization: str | None = None
    receipt: str | None = None
    franchise: str | None = None
    refunded: bool | None = None
    processor_fields: list[ProcessorField] | None = None
    agreement: str | None = None
    agreement_type: str | None = None
    dispersion: dict[str, Any] | None = None
    discount: Discount | None = None
    subscription: SubscriptionInformation | None = None

    @property
    def is_approved(self) -> bool:
        """Convenience: did this transaction reach an APPROVED state?"""
        return self.status is not None and self.status.is_approved

    @property
    def is_rejected(self) -> bool:
        return self.status is not None and self.status.is_rejected

    @property
    def is_successful(self) -> bool:
        return self.status is not None and self.status.is_successful


class AutopayRequest(_CheckoutModel):
    """Required block on ``CreateSessionRequest`` when ``type=autopay``."""

    periodicity: str | None = None
    interval: int | None = Field(default=None, ge=1)
    next_payment: str | None = None
    max_periods: int | None = Field(default=None, ge=-1)
    amount: Amount | None = None
    due_date: str | None = None
    notification_url: str | None = None


__all__ = [
    "AutopayRequest",
    "ProcessorField",
    "SubscriptionInformation",
    "Transaction",
]
