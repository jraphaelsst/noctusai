"""Real estate product-code validators.

Ported verbatim from
``products/social-wiring/backend/app/services/crm_service.py``
(lifted 2026-05-20 via ``social-wiring-vista-seed-lift``).
"""

from __future__ import annotations

import re
from typing import Optional

# Product code format: a 2–4 letter tenant prefix followed by 3–6 digits.
#
# Deliberately NOT ``^ONE\d{3,6}$``. That premise — every product code starts
# with ``ONE`` — is contradicted by the tenant's own catalog. A census of all
# 1919 imóveis on ``oneconsu-rest`` (2026-08-03) found six live prefixes:
# ``ONE`` 1634, ``CA`` 177, ``TE`` 84, ``AR`` 10, ``AP`` 7, ``GA`` 6, ``PR`` 1.
# The old anchored pattern therefore rejected 285 real imóveis (14.9%) at every
# call site — including ``integrations.vista.real.get_property``, which refuses
# the code before making any HTTP call, so those imóveis were simply
# unreachable.
#
# Deliberately generic rather than an alternation over those six prefixes: the
# prefix set is tenant-defined and drifts as the tenant adds property classes.
# Hardcoding one tenant's list here is the same mistake as hardcoding the Vista
# field set — see ``KB § INTEGRATIONS/vista.md`` § 6 on per-tenant calibration.
PRODUCT_CODE_PATTERN = re.compile(r"^[A-Z]{2,4}\d{3,6}$")

# Free-text scanner — the same shape with word boundaries, for pulling a code
# out of a message body rather than validating one already in hand.
#
# SINGLE SOURCE OF TRUTH. This previously lived as three separate hand-synced
# copies (``whatsapp_intake_service`` twice, ``conversation_module`` once) with
# a comment instructing future editors to keep them aligned by hand. They
# drifted the moment the prefix widened, so the constant moved here and the
# consumers import it.
#
# Being generic, this can over-match a non-code token that happens to be 2–4
# letters followed by 3–6 digits (e.g. ``IPTU2024``). That is bounded: every
# consumer validates the candidate and then resolves it against the CRM, so a
# false extraction becomes a failed lookup, never a wrong record. The previous
# behaviour — silently never matching a ``CA``/``TE`` code at all — was the
# worse failure, because it was invisible.
PRODUCT_CODE_SCAN_PATTERN = re.compile(r"\b[A-Z]{2,4}\d{3,6}\b", re.IGNORECASE)


def validate_product_code(code: str) -> bool:
    """Check if a product code matches the expected format."""
    return bool(PRODUCT_CODE_PATTERN.match(code))


def extract_product_code(text: str) -> Optional[str]:
    """Return the first product code found in ``text``, upper-cased.

    Returns ``None`` when the text carries no code-shaped token. Callers are
    expected to `validate_product_code` the result before trusting it — the
    scanner is intentionally permissive (see `PRODUCT_CODE_SCAN_PATTERN`).
    """
    match = PRODUCT_CODE_SCAN_PATTERN.search(text)
    return match.group(0).upper() if match else None


def find_product_codes(text: str) -> list[str]:
    """Return every product code found in ``text``, upper-cased, in order.

    Duplicates are preserved — callers that want the distinct set should
    de-duplicate themselves (content-stats counts both totals).
    """
    return [m.upper() for m in PRODUCT_CODE_SCAN_PATTERN.findall(text)]
