"""Tests for :mod:`placetopay.checkout.document_helper`.

Patterns ported verbatim from the PHP reference SDK; these tests lock the
behavior so any future change is intentional.
"""

from __future__ import annotations

import pytest

import placetopay.checkout.document_helper as dh
from placetopay.checkout import (
    is_business_document,
    is_valid_document,
    is_valid_type,
    supported_types,
)


class TestTypeRecognition:
    def test_known_types_are_valid(self) -> None:
        for t in ("CC", "CE", "TI", "NIT", "RUT", "PPN", "TAX", "LIC",
                   "SSN", "CIP", "CPF", "CI", "RUC", "DNI",
                   "CRCPF", "CPJ", "DIMEX", "DIDI", "CLRUT"):
            assert is_valid_type(t), f"expected {t} to be a known document type"

    def test_unknown_types_rejected(self) -> None:
        assert not is_valid_type("XYZ")
        assert not is_valid_type("")
        assert not is_valid_type("cc")  # case-sensitive

    def test_supported_types_returns_all_nineteen(self) -> None:
        assert len(supported_types()) == 19

    def test_supported_types_respects_exclude(self) -> None:
        assert "CC" not in supported_types(exclude=["CC"])
        assert "NIT" not in supported_types(exclude=("CC", "NIT"))


class TestBusinessDocuments:
    @pytest.mark.parametrize("type_code", ["NIT", "RUT", "RUC", "CLRUT"])
    def test_business_types(self, type_code: str) -> None:
        assert is_business_document(type_code)

    @pytest.mark.parametrize("type_code", ["CC", "CE", "TI", "PPN", "SSN", "CPF", "DNI"])
    def test_non_business_types(self, type_code: str) -> None:
        assert not is_business_document(type_code)

    def test_unknown_type_not_business(self) -> None:
        assert not is_business_document("UNKNOWN")


# ─── Valid examples per type (1 positive + 1 negative each) ────────────
class TestValidationPatterns:

    # Colombia
    @pytest.mark.parametrize("value", ["1040035000", "12345", "987654321"])
    def test_cc_valid(self, value: str) -> None:
        assert is_valid_document("CC", value)

    @pytest.mark.parametrize("value", ["0123456789", "abc123", "", "12"])
    def test_cc_invalid(self, value: str) -> None:
        assert not is_valid_document("CC", value)

    def test_ce_allows_letter_prefix(self) -> None:
        assert is_valid_document("CE", "12345")
        assert is_valid_document("CE", "abcde12345")
        assert not is_valid_document("CE", "012345")  # leading zero

    def test_ti_pattern(self) -> None:
        assert is_valid_document("TI", "12345")
        assert not is_valid_document("TI", "1234")

    def test_nit_pattern(self) -> None:
        assert is_valid_document("NIT", "900123456")
        assert not is_valid_document("NIT", "12345")
        assert not is_valid_document("NIT", "0900123456")

    def test_rut_pattern_matches_nit(self) -> None:
        assert is_valid_document("RUT", "900123456")
        assert not is_valid_document("RUT", "abc")

    # Generic
    def test_ppn_alphanumeric(self) -> None:
        assert is_valid_document("PPN", "AB123")
        assert is_valid_document("PPN", "passport_001")
        assert not is_valid_document("PPN", "abc")       # too short
        assert not is_valid_document("PPN", "!@#$")

    # USA
    def test_ssn_pattern(self) -> None:
        assert is_valid_document("SSN", "123456789")
        assert is_valid_document("SSN", "1234567890")    # 10 digits allowed by pattern
        assert not is_valid_document("SSN", "12345")

    # Panama
    def test_cip_pattern(self) -> None:
        assert is_valid_document("CIP", "8-123-456")
        assert is_valid_document("CIP", "PE-1234-567890")
        assert not is_valid_document("CIP", "invalid")

    # Brazil
    def test_cpf_pattern(self) -> None:
        assert is_valid_document("CPF", "12345678901")
        assert is_valid_document("CPF", "1234567890")
        assert not is_valid_document("CPF", "123.456.789-01")  # formatted CPF not accepted

    # Ecuador
    def test_ci_pattern(self) -> None:
        assert is_valid_document("CI", "1234567890")     # exactly 10 digits
        assert not is_valid_document("CI", "12345")
        assert not is_valid_document("CI", "12345678901")

    def test_ruc_pattern(self) -> None:
        assert is_valid_document("RUC", "1234567890123")  # exactly 13 digits
        assert not is_valid_document("RUC", "123456789")

    # Peru
    def test_dni_pattern(self) -> None:
        assert is_valid_document("DNI", "12345678")       # exactly 8 digits
        assert not is_valid_document("DNI", "1234567")

    # Costa Rica
    def test_crcpf(self) -> None:
        assert is_valid_document("CRCPF", "123456789")
        assert not is_valid_document("CRCPF", "012345678")

    def test_cpj(self) -> None:
        assert is_valid_document("CPJ", "1234567890")
        assert not is_valid_document("CPJ", "123456789")

    def test_dimex_and_didi(self) -> None:
        for type_code in ("DIMEX", "DIDI"):
            assert is_valid_document(type_code, "12345678901")
            assert is_valid_document(type_code, "123456789012")
            assert not is_valid_document(type_code, "1234567890")

    # Chile
    def test_clrut_pattern(self) -> None:
        assert is_valid_document("CLRUT", "12.345.678-9")
        assert is_valid_document("CLRUT", "12.345.678-K")
        assert is_valid_document("CLRUT", "12345678-k")
        assert not is_valid_document("CLRUT", "12345678")

    # Unknown type
    def test_unknown_type_always_invalid(self) -> None:
        assert not is_valid_document("UNKNOWN", "anything")

    # Type with no registered pattern (currently all types have patterns,
    # but defend against future additions).
    def test_known_type_without_pattern(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(dh, "SUPPORTED_TYPES", (*dh.SUPPORTED_TYPES, "NOPATTERN"))
        assert is_valid_document("NOPATTERN", "anything")
