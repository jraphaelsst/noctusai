"""Every model the fleet actually calls must carry a price.

🔴 WHY THIS IS A TEST AND NOT A COMMENT
---------------------------------------
`usage.estimate_cost_usd` looks a model up in `MODELS` and returns `0.0`
when it finds nothing — deliberately, so pricing can never break a
successful LLM call. The cost is that an UNREGISTERED model is not loudly
broken; it is quietly free. It writes `cost_estimate_usd=0` on every
`llm_usage` row, `budget.compute_spend_usd` sums exactly that column, and
the org budget guardrail then reports a spend of zero forever while
looking perfectly armed.

That is the no-silent-errors shape: the safety net is disabled and the
dashboard says it is fine. `claude-opus-5` shipped in
`documents/transcription.py::OCR_MODELS` before it was priced here, so this
is a regression that has already happened once.

The pins below are the model ids the fleet can actually SELECT — the OCR
map's three vendors, plus the alternates its own comments recommend. A new
pin added there without a price here fails this test.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents.transcription import OCR_MODELS
from noctusai_lib.integrations.llm.models import MODELS
from noctusai_lib.integrations.llm.usage import estimate_cost_usd


def _priced(provider: str, model: str) -> bool:
    for entry in MODELS:
        if entry.provider == provider and entry.id == model:
            if (entry.cost_per_1m_input_tokens or 0) > 0:
                return True
    return False


#: NOC-REMEDIATE[llm-model-unpriced]: `gemini-2.0-flash` is selectable today
#: and priced nowhere, so an org that switches to Gemini gets the exact
#: silent-zero this file exists to prevent. It is listed rather than fixed
#: because Google has retired the 2.0 Flash rate from its published pricing
#: page, and a guessed number in a BUDGET GUARDRAIL is worse than a declared
#: gap: it would read as measured spend. Close this by confirming the rate
#: against Google's billing console for the account that holds the key, then
#: adding the `ModelEntry` and deleting this exemption.
#:
#: 🔴 The exemption is the named destination, NOT permission. A model may sit
#: here only while its price is genuinely unknown — never to quiet the test.
UNPRICED_KNOWN_GAPS: frozenset[tuple[str, str]] = frozenset(
    {("gemini", "gemini-2.0-flash")}
)


@pytest.mark.parametrize("provider,model", sorted(OCR_MODELS.items()))
def test_every_selectable_ocr_model_is_priced(provider: str, model: str) -> None:
    """An operator can select any of these in Settings → Chaves de API."""
    if (provider, model) in UNPRICED_KNOWN_GAPS:
        pytest.xfail(f"NOC-REMEDIATE[llm-model-unpriced]: {provider}/{model}")
    assert _priced(provider, model), (
        f"{provider}/{model} is selectable but unpriced — every call would "
        f"record cost 0 and the org budget guardrail would never fire"
    )


def test_the_gap_list_does_not_outlive_the_gap() -> None:
    """An exemption for a model that HAS since been priced is stale paperwork
    pretending to be a known issue. Fail when the fix landed and the marker
    did not — otherwise the list only ever grows."""
    for provider, model in UNPRICED_KNOWN_GAPS:
        assert not _priced(provider, model), (
            f"{provider}/{model} is priced now — remove it from "
            f"UNPRICED_KNOWN_GAPS and drop the NOC-REMEDIATE marker"
        )


@pytest.mark.parametrize(
    "provider,model",
    [
        ("anthropic", "claude-opus-5"),
        ("anthropic", "claude-sonnet-5"),
        ("anthropic", "claude-haiku-4-5"),
    ],
)
def test_the_documented_anthropic_swaps_are_priced(provider: str, model: str) -> None:
    """`OCR_MODELS` names the cheaper current-generation swaps in its own
    comment. A consumer taking that documented advice must not land on the
    zero-cost path either."""
    assert _priced(provider, model), f"{provider}/{model} unpriced"


def test_an_unregistered_model_really_does_cost_zero() -> None:
    """The failure mode this file exists to prevent, asserted directly rather
    than described — so the reason the tests above matter cannot rot."""
    assert estimate_cost_usd(
        provider="anthropic",
        model="claude-does-not-exist",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
    ) == 0.0


def test_a_registered_model_prices_a_million_tokens() -> None:
    assert estimate_cost_usd(
        provider="anthropic",
        model="claude-opus-5",
        prompt_tokens=1_000_000,
        completion_tokens=0,
    ) == pytest.approx(5.00)
