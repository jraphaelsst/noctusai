"""Real estate product-code validators.

Ported verbatim from
``products/social-wiring/backend/app/services/crm_service.py``
(lifted 2026-05-20 via ``social-wiring-vista-seed-lift``).
"""

from __future__ import annotations

import re

# Product code format: ONE followed by 3–6 digits
PRODUCT_CODE_PATTERN = re.compile(r"^ONE\d{3,6}$")


def validate_product_code(code: str) -> bool:
    """Check if a product code matches the expected format."""
    return bool(PRODUCT_CODE_PATTERN.match(code))
