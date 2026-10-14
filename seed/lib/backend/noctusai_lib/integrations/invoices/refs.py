"""Identifier validation - a `ref` / `company_ref` reaches URL paths (and a
webhook supplies `ref`), so it is checked BEFORE any path is built."""
from __future__ import annotations

import re

from .errors import InvoiceProviderError

_REF = re.compile(r"^[A-Za-z0-9_-]{1,64}\Z")


def validate_ref(value: str, provider: str = "focusnfe") -> str:
    if not isinstance(value, str) or not _REF.match(value):
        raise InvoiceProviderError(provider, "referencia invalida", code="ref_invalido")
    return value
