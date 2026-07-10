"""Payment instrument models (card, bank, token, credit) and the
``invalidateToken`` request envelope.

The reference Python SDK shipped an :class:`InvalidateToKenRequest` with
a misspelled ``to_dic()`` method. This SDK names it correctly
(:class:`InvalidateTokenRequest`) and deliberately does **not** expose a
bespoke ``to_dict``/``to_dic`` — callers use Pydantic's standard
``model_dump(by_alias=True, exclude_none=True)`` instead.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from placetopay.checkout.auth import Auth
from placetopay.checkout.models.common import _CheckoutModel


class Card(_CheckoutModel):
    name: str | None = None
    number: str | None = Field(default=None, description="PAN (masked in responses)")
    cvv: str | None = Field(default=None, description="Never logged")
    expiration_month: str | None = Field(default=None, pattern=r"^(0[1-9]|1[0-2])$")
    expiration_year: str | None = Field(default=None, pattern=r"^\d{2}$")
    installments: int | None = Field(default=None, ge=1)
    kind: str | None = Field(
        default=None,
        description="C=credit, A=debit savings, R=debit checking",
    )


class Bank(_CheckoutModel):
    code: str | None = None
    name: str | None = None
    einterface: int | None = None


class Token(_CheckoutModel):
    token: str | None = None
    subtoken: str | None = None
    franchise: str | None = None
    franchise_name: str | None = None
    issuer_name: str | None = None
    last_digits: str | None = None
    valid_until: datetime | None = None
    installments: int | None = None
    cvv: str | None = None


class Credit(_CheckoutModel):
    code: str | None = None
    type: str | None = None
    group_code: str | None = None
    installment: int | None = None


class Instrument(_CheckoutModel):
    """A payment instrument. At least one of ``token``, ``card``, ``bank``
    or ``credit`` must be supplied for most requests; validation is
    contextual so we don't enforce it here in general, only at the
    ``InvalidateTokenRequest`` boundary where a token is required.
    """

    token: Token | None = None
    card: Card | None = None
    bank: Bank | None = None
    credit: Credit | None = None
    pin: str | None = None
    password: str | None = None


# ─── InvalidateToken ──────────────────────────────────────────────────
class InvalidateTokenRequest(_CheckoutModel):
    """Envelope for ``POST /api/instrument/invalidate``.

    Auth is injected by the client at send time; callers never set it.
    """

    auth: Auth | None = None
    locale: str | None = None
    instrument: Instrument

    @model_validator(mode="after")
    def _require_token(self) -> InvalidateTokenRequest:
        if self.instrument.token is None or not self.instrument.token.token:
            raise ValueError(
                "InvalidateTokenRequest.instrument.token.token is required."
            )
        return self


__all__ = [
    "Bank",
    "Card",
    "Credit",
    "Instrument",
    "InvalidateTokenRequest",
    "Token",
]
