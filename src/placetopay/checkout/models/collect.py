"""Collect request model — direct charge using a stored instrument."""

from __future__ import annotations

from pydantic import Field

from placetopay.checkout.auth import Auth
from placetopay.checkout.models.common import NameValuePair, Person, _CheckoutModel
from placetopay.checkout.models.instrument import Instrument
from placetopay.checkout.models.session import Payment


class CollectRequest(_CheckoutModel):
    """Request body for ``POST /api/collect``.

    A ``payer`` (cardholder) and an ``instrument`` are always required;
    the instrument is typically a previously-tokenized card.

    The optional ``provider`` field mirrors the PHP SDK's ``provider``
    parameter — use it to pin the collect call to a specific payment
    processor when the gateway has more than one route available.
    """

    auth: Auth | None = None  # injected by the client
    locale: str | None = Field(default=None, pattern=r"^[a-z]{2}_[A-Z]{2}$")
    payer: Person
    buyer: Person | None = None
    payment: Payment
    instrument: Instrument
    ip_address: str | None = Field(default=None, max_length=46)
    user_agent: str | None = Field(default=None, max_length=255)
    fields: list[NameValuePair] | None = None
    provider: str | None = None


__all__ = ["CollectRequest"]
