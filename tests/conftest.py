"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import responses

from placetopay.checkout import Checkout, Country, Environment, Settings


@pytest.fixture
def settings() -> Settings:
    """A minimal sandbox Settings instance with stable test credentials."""
    return Settings(
        login="SDK_TEST_LOGIN",
        secret_key="SDK_TEST_SECRET",
        environment=Environment.SANDBOX,
        country=Country.COLOMBIA,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[Checkout]:
    """A Checkout client wired to the sandbox base URL, HTTP mocked."""
    c = Checkout(settings)
    try:
        yield c
    finally:
        c.close()


@pytest.fixture
def mocked_responses() -> Iterator[responses.RequestsMock]:
    """Activate the :mod:`responses` library for per-test HTTP mocking."""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        yield rsps
