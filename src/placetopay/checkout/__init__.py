"""PlaceToPay Checkout Python SDK — public entry points.

Typical use::

    from placetopay.checkout import Checkout, Settings, Environment, Country

    client = Checkout(
        Settings(
            login="merchant-login",
            secret_key="merchant-secret",
            environment=Environment.SANDBOX,
            country=Country.COLOMBIA,
        )
    )

    response = client.create_session({
        "payment": {
            "reference": "ORDER-0001",
            "description": "Test order",
            "amount": {"currency": "COP", "total": 50000},
        },
        "returnUrl": "https://example.com/return",
        "ipAddress": "127.0.0.1",
        "userAgent": "Mozilla/5.0",
    })
    print(response.process_url)
"""

from placetopay.checkout._version import __version__
from placetopay.checkout.client import Checkout
from placetopay.checkout.document_helper import (
    is_business_document,
    is_valid_document,
    is_valid_type,
    supported_types,
)
from placetopay.checkout.environment import Country, Environment
from placetopay.checkout.errors import (
    AuthenticationError,
    NetworkError,
    NotFoundError,
    PlaceToPayError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from placetopay.checkout.models.collect import CollectRequest
from placetopay.checkout.models.instrument import InvalidateTokenRequest
from placetopay.checkout.models.reverse import ReverseRequest, ReverseResponse
from placetopay.checkout.models.session import (
    CancelSessionResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    SessionInformation,
)
from placetopay.checkout.settings import Settings
from placetopay.checkout.webhook import (
    verify_notification,
    verify_notification_legacy,
)

__all__ = [
    "AuthenticationError",
    "CancelSessionResponse",
    "Checkout",
    "CollectRequest",
    "Country",
    "CreateSessionRequest",
    "CreateSessionResponse",
    "Environment",
    "InvalidateTokenRequest",
    "NetworkError",
    "NotFoundError",
    "PlaceToPayError",
    "RateLimitError",
    "ReverseRequest",
    "ReverseResponse",
    "ServerError",
    "SessionInformation",
    "Settings",
    "ValidationError",
    "__version__",
    "is_business_document",
    "is_valid_document",
    "is_valid_type",
    "supported_types",
    "verify_notification",
    "verify_notification_legacy",
]
