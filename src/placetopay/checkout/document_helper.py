"""Client-side document-number validation for LatAm identity / tax IDs.

Ported from the PHP SDK's ``Dnetix\\Redirection\\Helpers\\DocumentHelper``
(see ``reference/php-redirection/src/Helpers/DocumentHelper.php``) with
byte-exact regex patterns so validation decisions are identical.

Use this to reject obviously-malformed ``Person.document`` values before
hitting the gateway — the server will still validate authoritatively, but
catching bad input locally saves a round-trip and improves UX.

Example::

    from placetopay.checkout import is_valid_document, is_business_document

    is_valid_document("CC", "1040035000")  # → True
    is_valid_document("NIT", "900123456")  # → True (9 digits)
    is_business_document("NIT")            # → True
    is_business_document("CC")             # → False
"""

from __future__ import annotations

import re
from collections.abc import Iterable

__all__ = [
    "BUSINESS_DOCUMENT_TYPES",
    "SUPPORTED_TYPES",
    "VALIDATION_PATTERNS",
    "is_business_document",
    "is_valid_document",
    "is_valid_type",
    "supported_types",
]

# ─── Type codes — grouped by jurisdiction ────────────────────────────────
# Colombia
TYPE_CC = "CC"    # Cédula de Ciudadanía
TYPE_CE = "CE"    # Cédula de Extranjería
TYPE_TI = "TI"    # Tarjeta de Identidad (minor)
TYPE_RC = "RC"    # Registro Civil (birth certificate)
TYPE_NIT = "NIT"  # Business tax ID
TYPE_RUT = "RUT"  # Rol Único Tributario (business)

# Generic
TYPE_PPN = "PPN"  # Passport
TYPE_TAX = "TAX"
TYPE_LIC = "LIC"  # License
TYPE_CD = "CD"

# USA
TYPE_SSN = "SSN"

# Panama
TYPE_CIP = "CIP"

# Brazil
TYPE_CPF = "CPF"

# Ecuador
TYPE_CI = "CI"    # Cédula de Identidad
TYPE_RUC = "RUC"  # Registro Único Contribuyente (business)

# Peru
TYPE_DNI = "DNI"

# Costa Rica
TYPE_CRCPF = "CRCPF"  # Cédula personal física
TYPE_CPJ = "CPJ"      # Cédula personal jurídica (business)
TYPE_DIMEX = "DIMEX"  # Documento de identificación de Migración y Extranjería
TYPE_DIDI = "DIDI"    # Documento de identificación de diplomáticos

# Chile
TYPE_CLRUT = "CLRUT"  # Rol Único Tributario (business)

SUPPORTED_TYPES: tuple[str, ...] = (
    TYPE_CC, TYPE_CE, TYPE_TI, TYPE_NIT, TYPE_RUT,
    TYPE_PPN, TYPE_TAX, TYPE_LIC,
    TYPE_SSN, TYPE_CIP, TYPE_CPF, TYPE_CI, TYPE_RUC,
    TYPE_DNI, TYPE_CRCPF, TYPE_CPJ, TYPE_DIMEX, TYPE_DIDI,
    TYPE_CLRUT,
)

BUSINESS_DOCUMENT_TYPES: tuple[str, ...] = (
    TYPE_NIT, TYPE_RUT, TYPE_RUC, TYPE_CLRUT,
)

# Regex patterns — ported verbatim from PHP SDK DocumentHelper::$VALIDATION_PATTERNS
# so behavior is identical across languages.
VALIDATION_PATTERNS: dict[str, re.Pattern[str]] = {
    TYPE_CC:    re.compile(r"^[1-9][0-9]{3,9}$"),
    TYPE_CE:    re.compile(r"^([a-zA-Z]{1,5})?[1-9][0-9]{3,7}$"),
    TYPE_TI:    re.compile(r"^[1-9][0-9]{4,11}$"),
    TYPE_NIT:   re.compile(r"^[1-9]\d{6,9}$"),
    TYPE_RUT:   re.compile(r"^[1-9]\d{6,9}$"),
    TYPE_PPN:   re.compile(r"^[a-zA-Z0-9_]{4,16}$"),
    TYPE_TAX:   re.compile(r"^[a-zA-Z0-9_]{4,16}$"),
    TYPE_LIC:   re.compile(r"^[a-zA-Z0-9_]{4,16}$"),
    TYPE_SSN:   re.compile(r"^\d{3}\d{2,3}\d{4}$"),
    TYPE_CIP:   re.compile(r"^(PE|E|N|[23456789](?:AV|PI)?|1[0123]?(?:AV|PI)?)-?(\d{1,4})-?(\d{1,6})$"),
    TYPE_CPF:   re.compile(r"^\d{10,11}$"),
    TYPE_CI:    re.compile(r"^\d{10}$"),
    TYPE_RUC:   re.compile(r"^\d{13}$"),
    TYPE_DNI:   re.compile(r"^\d{8}$"),
    TYPE_CRCPF: re.compile(r"^[1-9][0-9]{8}$"),
    TYPE_CPJ:   re.compile(r"^[1-9][0-9]{9}$"),
    TYPE_DIMEX: re.compile(r"^[1-9][0-9]{10,11}$"),
    TYPE_DIDI:  re.compile(r"^[1-9][0-9]{10,11}$"),
    TYPE_CLRUT: re.compile(r"^(\d{1,2}(?:\.?\d{1,3}){2}-[\dkK])$"),
}


def supported_types(exclude: Iterable[str] | None = None) -> tuple[str, ...]:
    """Return the list of recognized document-type codes.

    :param exclude: optional iterable of type codes to omit from the result.
    """
    if not exclude:
        return SUPPORTED_TYPES
    excluded = set(exclude)
    return tuple(t for t in SUPPORTED_TYPES if t not in excluded)


def is_valid_type(document_type: str) -> bool:
    """True when ``document_type`` is one of the known type codes."""
    return document_type in SUPPORTED_TYPES


def is_valid_document(document_type: str, document: str) -> bool:
    """Validate ``document`` against the pattern registered for ``document_type``.

    Returns ``False`` for unknown types; returns ``True`` for known types that
    have no registered pattern.
    """
    if not is_valid_type(document_type):
        return False
    pattern = VALIDATION_PATTERNS.get(document_type)
    if pattern is None:
        return True
    return pattern.match(document) is not None


def is_business_document(document_type: str) -> bool:
    """True when ``document_type`` is one of the business-document codes
    (NIT, RUT, RUC, CLRUT).
    """
    return document_type in BUSINESS_DOCUMENT_TYPES
