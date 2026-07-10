"""Pydantic v2 request / response models for the PlaceToPay Checkout API.

All models use ``alias_generator=to_camel`` + ``populate_by_name=True`` so
Python code uses idiomatic ``snake_case`` attributes while the wire JSON
is ``camelCase`` (what the gateway accepts and returns).

Use :meth:`pydantic.BaseModel.model_dump` with
``by_alias=True, exclude_none=True`` to serialize — the SDK's HTTP layer
does this automatically for outgoing requests.
"""

from placetopay.checkout.models.collect import CollectRequest
from placetopay.checkout.models.common import (
    Address,
    Amount,
    AmountBase,
    AmountConversion,
    AmountDetail,
    DispersionItem,
    Item,
    NameValuePair,
    PaymentModifier,
    Person,
    Recurring,
    Status,
    StatusCode,
    TaxDetail,
)
from placetopay.checkout.models.instrument import (
    Bank,
    Card,
    Credit,
    Instrument,
    InvalidateTokenRequest,
    Token,
)
from placetopay.checkout.models.reverse import ReverseRequest, ReverseResponse
from placetopay.checkout.models.session import (
    CancelSessionResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    Payment,
    SessionInformation,
    SubscriptionRequest,
)
from placetopay.checkout.models.transaction import (
    AutopayRequest,
    SubscriptionInformation,
    Transaction,
)

__all__ = [
    "Address",
    "Amount",
    "AmountBase",
    "AmountConversion",
    "AmountDetail",
    "AutopayRequest",
    "Bank",
    "CancelSessionResponse",
    "Card",
    "CollectRequest",
    "CreateSessionRequest",
    "CreateSessionResponse",
    "Credit",
    "DispersionItem",
    "Instrument",
    "InvalidateTokenRequest",
    "Item",
    "NameValuePair",
    "Payment",
    "PaymentModifier",
    "Person",
    "Recurring",
    "ReverseRequest",
    "ReverseResponse",
    "SessionInformation",
    "Status",
    "StatusCode",
    "SubscriptionInformation",
    "SubscriptionRequest",
    "TaxDetail",
    "Token",
    "Transaction",
]
