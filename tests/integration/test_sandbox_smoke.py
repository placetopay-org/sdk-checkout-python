"""End-to-end smoke test against the PlaceToPay sandbox.

Gated by environment variables — set ``PLACETOPAY_LOGIN`` and
``PLACETOPAY_SECRET_KEY`` to run. Never commit credentials to source
control.

Exercises the happy path of the session lifecycle that the sandbox can
validate without a human completing a UI flow:
``create_session`` → ``query_session`` → ``cancel_session`` →
``query_session``.

Marked ``integration`` so the rest of the suite stays hermetic. Run
locally with::

    PLACETOPAY_LOGIN=... PLACETOPAY_SECRET_KEY=... \\
        pytest -m integration tests/integration/test_sandbox_smoke.py
"""

from __future__ import annotations

import os
import uuid

import pytest

from placetopay.checkout import Checkout, Environment, Settings
from placetopay.checkout.models.common import Amount
from placetopay.checkout.models.session import CreateSessionRequest, Payment


@pytest.mark.integration
def test_session_lifecycle_against_sandbox() -> None:
    login = os.environ.get("PLACETOPAY_LOGIN")
    secret = os.environ.get("PLACETOPAY_SECRET_KEY")
    if not login or not secret:
        pytest.skip(
            "PLACETOPAY_LOGIN / PLACETOPAY_SECRET_KEY not set "
            "— skipping live sandbox test."
        )

    settings = Settings(
        login=login,
        secret_key=secret,
        environment=Environment.SANDBOX,
    )

    with Checkout(settings) as client:
        # 1) create
        request = CreateSessionRequest(
            ip_address="127.0.0.1",
            user_agent="checkout-python-smoke/1.0",
            return_url="https://example.com/return",
            payment=Payment(
                reference=f"smoke-py-{uuid.uuid4().hex[:8]}",
                description="Python SDK sandbox smoke test",
                amount=Amount(currency="COP", total=50_000),
            ),
        )
        created = client.create_session(request)
        assert created.request_id is not None and created.request_id > 0
        assert created.process_url
        request_id = created.request_id

        # 2) query — PENDING or OK both acceptable.
        info = client.query_session(request_id)
        assert info.status is not None

        # 3) cancel
        cancelled = client.cancel_session(request_id)
        assert cancelled.status is not None

        # 4) query again — should now be REJECTED.
        after_cancel = client.query_session(request_id)
        assert after_cancel.status is not None
        assert after_cancel.status.is_rejected, (
            f"expected REJECTED after cancel; got {after_cancel.status.status}"
        )
