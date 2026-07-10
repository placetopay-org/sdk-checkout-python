"""Reverse request / response models."""

from __future__ import annotations

from placetopay.checkout.auth import Auth
from placetopay.checkout.models.common import Status, _CheckoutModel
from placetopay.checkout.models.transaction import Transaction


class ReverseRequest(_CheckoutModel):
    """Request body for ``POST /api/reverse``."""

    auth: Auth | None = None  # injected by the client
    internal_reference: str


class ReverseResponse(_CheckoutModel):
    status: Status
    payment: Transaction | None = None


__all__ = ["ReverseRequest", "ReverseResponse"]
