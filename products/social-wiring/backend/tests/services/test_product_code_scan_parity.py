"""The product-code scanner is bound once in the seed, never re-declared here.

**Why this test exists.** The intake fast-path gate
(`whatsapp_intake_service`) and the state-machine handler
(`conversation_module`) must agree on what counts as a valid upload command
— when they disagree, a message matches one and not the other and the user
gets no reply at all. That agreement used to be enforced by a comment
telling future editors to keep three hand-written copies of the regex
aligned:

    # Keep tolerance aligned with conversation_module._regex_extract …
    _PRODUCT_CODE_RE = re.compile(r"\\bONE\\d{3,6}\\b", re.IGNORECASE)

They drifted the moment the tenant's prefix set turned out to be wider than
``ONE`` (a 2026-08-03 census of all 1919 imóveis found six live prefixes;
the ONE-only pattern silently never matched 14.9% of the catalog).

Both consumers now bind the single seed constant, so this asserts
**identity**, not equality — an equal-but-separate `re.compile` is exactly
the re-fork this guards against, and `==` would not catch it.
"""

from __future__ import annotations

from noctusai_lib.domain.real_estate import PRODUCT_CODE_SCAN_PATTERN

from app.services.conversation_module import _PRODUCT_CODE_RE as conversation_re
from app.services.whatsapp_intake_service import _PRODUCT_CODE_RE as intake_re


def test_conversation_module_binds_the_seed_scanner():
    assert conversation_re is PRODUCT_CODE_SCAN_PATTERN


def test_intake_service_binds_the_seed_scanner():
    assert intake_re is PRODUCT_CODE_SCAN_PATTERN


def test_both_gates_agree_on_a_non_one_prefixed_code():
    """The concrete regression: a `CA…` code must not match one gate only."""
    body = "bom dia, sobe o CA0190 pra mim"
    assert conversation_re.search(body) is not None
    assert intake_re.search(body) is not None
