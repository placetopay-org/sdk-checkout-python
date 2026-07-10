"""Namespace package for the PlaceToPay SDK family.

The actual SDK lives in :mod:`placetopay.checkout`. This top-level module
exists only to host that sub-package and re-export its public entry points
for users who prefer ``from placetopay import Checkout``.
"""

from placetopay.checkout import (
    Checkout,
    Country,
    Environment,
    Settings,
)
from placetopay.checkout.errors import (
    AuthenticationError,
    NetworkError,
    NotFoundError,
    PlaceToPayError,
    RateLimitError,
    ServerError,
    ValidationError,
)

__all__ = [
    "AuthenticationError",
    "Checkout",
    "Country",
    "Environment",
    "NetworkError",
    "NotFoundError",
    "PlaceToPayError",
    "RateLimitError",
    "ServerError",
    "Settings",
    "ValidationError",
]
