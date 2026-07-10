from placetopay.checkout.environment import Country, Environment, resolve_base_url


def test_resolve_base_url_defaults_to_colombia_sandbox() -> None:
    assert resolve_base_url(None, None, None) == "https://checkout-test.placetopay.com"


def test_resolve_base_url_ecuador_sandbox_override() -> None:
    assert (
        resolve_base_url(Environment.SANDBOX, Country.ECUADOR, None)
        == "https://checkout-test.placetopay.ec"
    )


def test_resolve_base_url_ecuador_production_override() -> None:
    assert (
        resolve_base_url(Environment.PRODUCTION, Country.ECUADOR, None)
        == "https://checkout.placetopay.ec"
    )


def test_resolve_base_url_colombia_uses_default_environment_url() -> None:
    assert (
        resolve_base_url(Environment.PRODUCTION, Country.COLOMBIA, None)
        == "https://checkout.placetopay.com"
    )


def test_resolve_base_url_explicit_has_priority() -> None:
    assert (
        resolve_base_url(
            Environment.PRODUCTION,
            Country.ECUADOR,
            "https://custom.example.com/",
        )
        == "https://custom.example.com"
    )
