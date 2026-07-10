"""Environment and country presets.

See ARCHITECTURE.md §12. ``Environment`` and ``Country`` compose; an
explicit ``base_url`` on :class:`Settings` always overrides these
presets.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class Environment(StrEnum):
    """Which PlaceToPay environment to target.

    Values carry the matching default base URL for the *Colombia* region
    (the canonical PlaceToPay environment). For other countries, compose
    with :class:`Country`.
    """

    SANDBOX = "sandbox"
    PRODUCTION = "production"

    @property
    def base_url(self) -> str:
        """Default base URL for this environment (Colombia region)."""
        return _ENVIRONMENT_URLS[self]


class Country(StrEnum):
    """Country preset - supplies default locale, currency and (for
    non-Colombia countries) a regional base URL override."""

    COLOMBIA = "CO"
    ECUADOR = "EC"

    @property
    def default_currency(self) -> str:
        return _COUNTRY_DEFAULTS[self]["currency"]

    @property
    def default_locale(self) -> str:
        return _COUNTRY_DEFAULTS[self]["locale"]

    def base_url_for(self, environment: Environment) -> str | None:
        """Regional base URL override for a given environment.

        Returns ``None`` for countries that share the default Colombia
        endpoint in that environment.
        """
        key = (
            "production_base_url"
            if environment is Environment.PRODUCTION
            else "sandbox_base_url"
        )
        return _COUNTRY_DEFAULTS[self].get(key)


_ENVIRONMENT_URLS: Final[dict[Environment, str]] = {
    Environment.SANDBOX: "https://checkout-test.placetopay.com",
    Environment.PRODUCTION: "https://checkout.placetopay.com",
}


# Country-specific defaults. The ``production_base_url`` key only exists
# for countries with a regional production endpoint different from the
# Colombia default.
_COUNTRY_DEFAULTS: Final[dict[Country, dict[str, str]]] = {
    Country.COLOMBIA: {
        "currency": "COP",
        "locale": "es_CO",
    },
    Country.ECUADOR: {
        "currency": "USD",
        "locale": "es_EC",
        "sandbox_base_url": "https://checkout-test.placetopay.ec",
        "production_base_url": "https://checkout.placetopay.ec",
    },
}


def resolve_base_url(
    environment: Environment | None,
    country: Country | None,
    explicit_base_url: str | None,
) -> str:
    """Compute the effective base URL for a client.

    Precedence, highest to lowest:

    1. ``explicit_base_url`` (escape hatch)
    2. ``country`` regional base URL override for the selected environment
    3. ``environment.base_url``

    If neither ``environment`` nor ``explicit_base_url`` is supplied,
    :class:`Environment.SANDBOX` is used.
    """
    if explicit_base_url:
        return explicit_base_url.rstrip("/")

    env = environment or Environment.SANDBOX

    if country is not None:
        regional = country.base_url_for(env)
        if regional:
            return regional.rstrip("/")

    return env.base_url.rstrip("/")
