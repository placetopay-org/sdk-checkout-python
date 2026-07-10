"""Tests for the PHP-parity improvements.

Covers:
* ``auth.additional`` flows from :class:`Settings` → :class:`Auth` → wire JSON.
* ``CollectRequest.provider`` serializes on the wire.
* :class:`Discount` entity roundtrip.
* :class:`Status` convenience predicates (``is_approved`` / ``is_rejected`` / ``is_error``).
* :class:`SessionInformation` transaction helpers (``last_transaction`` /
  ``last_approved_transaction`` / ``last_authorization``).
* :class:`Transaction` convenience predicates.
"""

from __future__ import annotations

from datetime import UTC, datetime

from placetopay.checkout.auth import NONCE_BYTES, new_auth, sign
from placetopay.checkout.client import Checkout
from placetopay.checkout.environment import Country, Environment
from placetopay.checkout.models.collect import CollectRequest
from placetopay.checkout.models.common import (
    Amount,
    Discount,
    Person,
    Status,
    StatusCode,
)
from placetopay.checkout.models.instrument import Instrument, Token
from placetopay.checkout.models.session import Payment, SessionInformation
from placetopay.checkout.models.transaction import Transaction
from placetopay.checkout.settings import Settings
from placetopay.checkout.models.common import NameValuePair
from placetopay.checkout.models.transaction import SubscriptionInformation


# ─── auth.additional ────────────────────────────────────────────────────────
class TestAuthAdditional:
    def test_additional_omitted_when_none(self) -> None:
        auth = new_auth(login="L", secret_key="S")
        dumped = auth.model_dump(by_alias=True, exclude_none=True)
        assert "additional" not in dumped

    def test_additional_roundtrips(self) -> None:
        extra = {"merchantId": "42", "channel": "web"}
        auth = new_auth(login="L", secret_key="S", additional=extra)
        dumped = auth.model_dump(by_alias=True, exclude_none=True)
        assert dumped["additional"] == extra

    def test_sign_deterministic_with_additional(self) -> None:
        raw = bytes.fromhex("00112233445566778899aabbccddeeff")
        a = sign("L", "S", raw, "2026-04-22T15:30:45+00:00", additional={"k": "v"})
        b = sign("L", "S", raw, "2026-04-22T15:30:45+00:00", additional={"k": "v"})
        assert a == b
        assert a.additional == {"k": "v"}

    def test_additional_does_not_change_digest(self) -> None:
        """``additional`` is NOT part of the hash input — adding it must not
        alter ``tranKey``."""
        raw = bytes.fromhex("00112233445566778899aabbccddeeff")
        without = sign("L", "S", raw, "2026-04-22T15:30:45+00:00")
        with_extra = sign("L", "S", raw, "2026-04-22T15:30:45+00:00",
                          additional={"merchantId": "42"})
        assert without.tran_key == with_extra.tran_key
        assert without.nonce == with_extra.nonce


class TestSettingsAuthAdditional:
    def test_settings_stores_auth_additional(self) -> None:
        s = Settings(
            login="L",
            secret_key="S",
            environment=Environment.SANDBOX,
            country=Country.COLOMBIA,
            auth_additional={"tenant": "acme"},
        )
        assert s.auth_additional == {"tenant": "acme"}

    def test_client_propagates_additional_to_auth(self) -> None:
        client = Checkout(Settings(
            login="L",
            secret_key="S",
            environment=Environment.SANDBOX,
            auth_additional={"tenant": "acme", "origin": "mobile"},
        ))
        auth = client._new_auth()
        assert auth.additional == {"tenant": "acme", "origin": "mobile"}


# ─── CollectRequest.provider ────────────────────────────────────────────────
class TestCollectProvider:
    def _base(self, **extra: object) -> CollectRequest:
        return CollectRequest(
            payer=Person(document="1040035000", document_type="CC",
                         name="Test", surname="Buyer", email="t@example.com"),
            payment=Payment(
                reference="r1",
                description="d",
                amount=Amount(currency="COP", total=10_000),
            ),
            instrument=Instrument(token=Token(token="tok-abc")),
            **extra,
        )

    def test_provider_defaults_to_none(self) -> None:
        req = self._base()
        dumped = req.model_dump(by_alias=True, exclude_none=True)
        assert "provider" not in dumped

    def test_provider_serializes_when_set(self) -> None:
        req = self._base(provider="evertec")
        dumped = req.model_dump(by_alias=True, exclude_none=True)
        assert dumped["provider"] == "evertec"


# ─── Discount entity ────────────────────────────────────────────────────────
class TestDiscountEntity:
    def test_roundtrip_all_fields(self) -> None:
        d = Discount(code="XMAS25", type="percentage",
                     amount=25.0, base=100.0, percent=25.0)
        wire = d.model_dump(by_alias=True, exclude_none=True)
        assert wire == {
            "code": "XMAS25",
            "type": "percentage",
            "amount": 25.0,
            "base": 100.0,
            "percent": 25.0,
        }
        restored = Discount.model_validate(wire)
        assert restored == d

    def test_transaction_parses_nested_discount(self) -> None:
        tx = Transaction.model_validate({
            "status": {"status": "APPROVED", "date": "2026-04-22T15:30:45+00:00"},
            "discount": {"code": "PROMO", "amount": 5_000.0, "base": 50_000.0},
        })
        assert isinstance(tx.discount, Discount)
        assert tx.discount.code == "PROMO"


# ─── Status convenience ─────────────────────────────────────────────────────
class TestStatusPredicates:
    def test_is_approved(self) -> None:
        s = Status(status=StatusCode.APPROVED)
        assert s.is_approved is True
        assert s.is_rejected is False
        assert s.is_error is False
        assert s.is_successful is True

    def test_is_rejected(self) -> None:
        s = Status(status=StatusCode.REJECTED)
        assert s.is_rejected is True
        assert s.is_approved is False
        assert s.is_successful is False

    def test_is_error(self) -> None:
        s = Status(status=StatusCode.ERROR)
        assert s.is_error is True
        assert s.is_approved is False

    def test_none_status_is_none_of_the_above(self) -> None:
        s = Status()
        assert s.is_approved is False
        assert s.is_rejected is False
        assert s.is_error is False


# ─── SessionInformation helpers ─────────────────────────────────────────────
class TestSessionInformationHelpers:
    def _info(self, *transactions: Transaction) -> SessionInformation:
        return SessionInformation(
            request_id=1,
            status=Status(status=StatusCode.OK),
            payment=list(transactions) or None,
        )

    def _txn(self, code: StatusCode, authorization: str | None = None) -> Transaction:
        return Transaction(
            status=Status(status=code, date=datetime.now(UTC)),
            authorization=authorization,
        )

    def test_no_transactions_all_helpers_return_none_or_empty(self) -> None:
        info = self._info()
        assert info.last_transaction() is None
        assert info.last_approved_transaction() is None
        assert info.last_authorization() == ""

    def test_last_transaction_returns_tail_element_by_default(self) -> None:
        t1 = self._txn(StatusCode.REJECTED)
        t2 = self._txn(StatusCode.APPROVED, authorization="123")
        info = self._info(t1, t2)
        assert info.last_transaction() is t2

    def test_last_approved_walks_the_list(self) -> None:
        approved = self._txn(StatusCode.APPROVED, authorization="A")
        rejected = self._txn(StatusCode.REJECTED)
        info = self._info(approved, rejected)
        # last_approved_transaction picks the first APPROVED in order.
        assert info.last_approved_transaction() is approved
        assert info.last_authorization() == "A"

    def test_last_approved_returns_none_when_none_approved(self) -> None:
        info = self._info(self._txn(StatusCode.REJECTED), self._txn(StatusCode.FAILED))
        assert info.last_approved_transaction() is None
        assert info.last_authorization() == ""


# ─── Transaction convenience ────────────────────────────────────────────────
class TestTransactionPredicates:
    def test_is_approved(self) -> None:
        t = Transaction(status=Status(status=StatusCode.APPROVED))
        assert t.is_approved is True
        assert t.is_rejected is False
        assert t.is_successful is True

    def test_is_rejected(self) -> None:
        t = Transaction(status=Status(status=StatusCode.REJECTED))
        assert t.is_rejected is True
        assert t.is_approved is False
        assert t.is_successful is False

    def test_no_status(self) -> None:
        t = Transaction()
        assert t.is_approved is False
        assert t.is_rejected is False
        assert t.is_successful is False

    def test_processor_fields_accept_mixed_value_types(self) -> None:
        t = Transaction.model_validate({
            "status": {"status": "OK", "date": "2026-05-22T12:00:00+00:00"},
            "processorFields": [
                {"keyword": "is3ds", "value": True},
                {"keyword": "installments", "value": 1},
                {"keyword": "score", "value": 55002.35},
                {
                    "keyword": "installmentInfo",
                    "value": {
                        "code": "1",
                        "type": "00",
                        "category": "C",
                        "installments": 1,
                    },
                },
            ],
        })
        assert t.processor_fields is not None
        assert t.processor_fields[0].value is True
        assert t.processor_fields[1].value == 1
        assert t.processor_fields[2].value == 55002.35
        assert isinstance(t.processor_fields[3].value, dict)


# ─── Sanity: nonce size constant unchanged ─────────────────────────────────
def test_nonce_size_is_still_16_bytes() -> None:
    """Regression: the locked cross-SDK test vector depends on 16 bytes."""
    assert NONCE_BYTES == 16


# ─── NameValuePair.value accepts non-string types (Ecuador regression) ──────
class TestNameValuePairMixedValue:
    """Ecuador subscription responses return instrument[].value as an object,
    not a string. PHP uses mixed; Java tolerates via Jackson. Python must too."""

    def test_string_value(self) -> None:
        nvp = NameValuePair.model_validate({"keyword": "token", "value": "abc123"})
        assert nvp.value == "abc123"

    def test_dict_value(self) -> None:
        nvp = NameValuePair.model_validate(
            {"keyword": "token", "value": {"token": "abc123", "franchise": "VISA"}}
        )
        assert isinstance(nvp.value, dict)
        assert nvp.value["token"] == "abc123"

    def test_integer_value(self) -> None:
        nvp = NameValuePair.model_validate({"keyword": "installments", "value": 6})
        assert nvp.value == 6

    def test_none_value(self) -> None:
        nvp = NameValuePair.model_validate({"keyword": "flag", "value": None})
        assert nvp.value is None

    def test_subscription_info_with_object_instrument_value(self) -> None:
        """Full SubscriptionInformation parse for Ecuador-style response."""
        raw = {
            "type": "token",
            "status": {
                "status": "OK",
                "reason": "00",
                "message": "OK",
                "date": "2026-06-23T10:00:00+00:00",
            },
            "instrument": [
                {
                    "keyword": "token",
                    "value": {"token": "ec_token_abc", "franchise": "VISA"},
                    "displayOn": "none",
                },
                {"keyword": "lastDigits", "value": "1234", "displayOn": "receipt"},
            ],
        }
        info = SubscriptionInformation.model_validate(raw)
        assert info.type == "token"
        assert info.instrument is not None
        assert isinstance(info.instrument[0].value, dict)
        assert info.instrument[0].value["token"] == "ec_token_abc"
        assert info.instrument[1].value == "1234"
