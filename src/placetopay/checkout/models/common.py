"""Cross-endpoint shared models.

Every model here inherits :class:`_CheckoutModel`, which applies the
camelCase alias generator and ``populate_by_name`` so attribute access
stays Pythonic while the wire format matches the OpenAPI spec.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _CheckoutModel(BaseModel):
    """Shared base: camelCase on the wire, snake_case in Python.

    - ``populate_by_name=True`` → can instantiate with either form.
    - ``extra="ignore"`` → unknown fields in *responses* are silently
      dropped (ARCHITECTURE.md §13, forward compatibility).
    - ``ser_json_bytes='base64'`` — not set; we don't have raw bytes on
      the wire.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
        str_strip_whitespace=True,
    )


# ─── Status ────────────────────────────────────────────────────────────
class StatusCode(StrEnum):
    OK = "OK"
    APPROVED = "APPROVED"
    APPROVED_PARTIAL = "APPROVED_PARTIAL"
    PARTIAL = "PARTIAL"
    PENDING = "PENDING"
    PENDING_VALIDATION = "PENDING_VALIDATION"
    REJECTED = "REJECTED"
    REFUNDED = "REFUNDED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"


class Status(_CheckoutModel):
    """Transaction / session status carrier."""

    status: StatusCode | None = None
    reason: str | None = None
    message: str | None = None
    date: datetime | None = None

    @property
    def is_successful(self) -> bool:
        """True when the operation's status is one of the 'good' codes."""
        return self.status in {
            StatusCode.OK,
            StatusCode.APPROVED,
            StatusCode.APPROVED_PARTIAL,
        }

    @property
    def is_approved(self) -> bool:
        """True when ``status == APPROVED``. Matches PHP SDK ``isApproved()``."""
        return self.status == StatusCode.APPROVED

    @property
    def is_rejected(self) -> bool:
        """True when ``status == REJECTED``. Matches PHP SDK ``isRejected()``."""
        return self.status == StatusCode.REJECTED

    @property
    def is_error(self) -> bool:
        """True when ``status == ERROR``. Matches PHP SDK ``isError()``."""
        return self.status == StatusCode.ERROR

    @property
    def is_pending(self) -> bool:
        """True when pending processor/user action."""
        return self.status in {StatusCode.PENDING, StatusCode.PENDING_VALIDATION}


# ─── Person / Address ─────────────────────────────────────────────────
class Address(_CheckoutModel):
    street: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=80)
    state: str | None = Field(default=None, max_length=80)
    postal_code: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, max_length=2)
    phone: str | None = Field(default=None, max_length=30)


class Person(_CheckoutModel):
    document: str | None = Field(default=None, max_length=20)
    document_type: str | None = None
    name: str | None = Field(default=None, max_length=80)
    surname: str | None = Field(default=None, max_length=80)
    company: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=120)
    mobile: str | None = Field(default=None, max_length=30)
    address: Address | None = None


# ─── Amount ───────────────────────────────────────────────────────────
class AmountBase(_CheckoutModel):
    currency: str = Field(..., min_length=3, max_length=3)
    total: float = Field(..., ge=0)


class TaxDetail(_CheckoutModel):
    kind: str
    amount: float
    base: float


class AmountDetail(_CheckoutModel):
    kind: str
    amount: float


class Discount(_CheckoutModel):
    """Explicit discount entity — mirrors the PHP SDK's ``Discount`` class.

    The gateway may return this object inside an approved transaction's
    ``discount`` slot. Present for forward compatibility; the SDK does not
    require callers to construct one.
    """

    code: str | None = None
    type: str | None = None
    amount: float | None = None
    base: float | None = None
    percent: float | None = None


class Amount(AmountBase):
    taxes: list[TaxDetail] | None = None
    details: list[AmountDetail] | None = None


class AmountConversion(_CheckoutModel):
    """Gateway-reported conversion between two currencies."""

    from_: AmountBase | None = Field(default=None, alias="from")
    to: AmountBase | None = None
    factor: float | None = None

    # The field name ``from`` is a Python keyword, so we store it as
    # ``from_`` internally and alias it explicitly. The camelCase alias
    # generator would still produce "from" here, but we set the alias
    # explicitly for clarity.


# ─── Items / modifiers / dispersion ───────────────────────────────────
class Item(_CheckoutModel):
    sku: str | None = None
    name: str | None = None
    category: str | None = None
    qty: str | None = None
    price: float | None = None
    tax: float | None = None


class Recurring(_CheckoutModel):
    periodicity: str | None = None
    interval: int | None = Field(default=None, ge=1)
    next_payment: str | None = None
    max_periods: int | None = Field(default=None, ge=-1)
    due_date: str | None = None
    notification_url: str | None = None


class NameValuePair(_CheckoutModel):
    keyword: str
    value: Any
    display_on: str | None = None


class PaymentModifier(_CheckoutModel):
    type: str | None = None
    code: str | None = None
    additional: dict[str, str] | None = None


class DispersionItem(_CheckoutModel):
    agreement: str
    agreement_type: str
    amount: AmountBase


# ─── Raw response envelope ────────────────────────────────────────────
class ErrorResponse(_CheckoutModel):
    """Envelope for error payloads returned by the gateway.

    Per the OpenAPI spec only ``status`` is guaranteed, but servers often
    also include field-level errors; we capture those in ``extras``.
    """

    status: Status | None = None

    # Bonus: tolerate field-level detail if present.
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="allow",
    )

    @property
    def extras(self) -> dict[str, Any]:
        return dict(self.__pydantic_extra__ or {})


__all__ = [
    "Address",
    "Amount",
    "AmountBase",
    "AmountConversion",
    "AmountDetail",
    "Discount",
    "DispersionItem",
    "ErrorResponse",
    "Item",
    "NameValuePair",
    "PaymentModifier",
    "Person",
    "Recurring",
    "Status",
    "StatusCode",
    "TaxDetail",
    "_CheckoutModel",
]
