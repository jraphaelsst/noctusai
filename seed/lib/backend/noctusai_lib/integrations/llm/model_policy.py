"""Purpose-based model routing — callers say WHAT the call is for, the seed picks the tier.

    await chat_completion(messages, purpose="classify", org_id=...)
    await chat_with_tools(msgs, [tool], purpose="summarize", provider=..., ...)
    model = resolve_model("anthropic", "summarize")      # for callers that build the call themselves

PURPOSE → TIER → MODEL
  =============  ==========  ===============================================================
  purpose        tier        meaning
  =============  ==========  ===============================================================
  ``classify``   light       pick a label / route / yes-no — cheapest, fastest
  ``summarize``  light       condense text — cheapest, fastest
  ``extract``    standard    structured output from text — the measured default
  ``reason``     heavy       multi-step judgement — strongest
  ``chat``       (none)      no routing: the caller's / `LLMConfig` default model (today's behaviour)
  =============  ==========  ===============================================================

RULES
  - **Omitted ``purpose`` = today's behaviour**, bit for bit: no routing, no new code path.
  - **An explicit ``model=`` always wins** — the policy only fills a model the caller did not pin. ``purpose`` is
    still recorded on the usage row (`attribution.purpose`) so spend is reportable per purpose.
  - **The provider is never changed.** There is NO silent failover (`provider_choice.py`): the policy picks a
    MODEL of the provider the call already resolved. A provider with no routable row for the tier (a stub
    provider, a model the operator disabled in the catalog overlay, an unknown provider) resolves to ``None`` and
    the caller's default stands — logged at DEBUG, never an error.
  - Models come from the EFFECTIVE catalog (`models.models_for`: static rows + the operator overlay), chat kind,
    non-stub; the table below is an ORDERED candidate list per (provider, tier) — the first routable one wins.

ALIGNMENT with the measured routing (`documents/roteamento_modelos.py`, document extraction): the Anthropic
``standard`` head is that table's measured global primary and ``heavy`` its measured fallback
(`tests/integrations/llm/test_model_policy.py` pins both, so a recalibration that moves them fails loudly here
instead of silently forking). The ``light`` tier and the OpenAI/Gemini rows have no measurement behind them yet:
they are the catalog's cheapest / the conservative rows, to be replaced by evidence the same way.
"""
from __future__ import annotations

import logging
from typing import Literal, Optional

logger = logging.getLogger(__name__)

__all__ = ["PURPOSES", "Purpose", "TIERS", "resolve_model", "tier_for"]

Purpose = Literal["classify", "extract", "summarize", "reason", "chat"]
Tier = Literal["light", "standard", "heavy"]

PURPOSES: tuple[str, ...] = ("classify", "extract", "summarize", "reason", "chat")

#: purpose -> tier. ``chat`` is deliberately absent: it means "no routing".
_TIER_OF_PURPOSE: dict[str, Tier] = {
    "classify": "light",
    "summarize": "light",
    "extract": "standard",
    "reason": "heavy",
}

#: provider -> tier -> ordered candidate model ids (first routable in the effective catalog wins).
TIERS: dict[str, dict[str, tuple[str, ...]]] = {
    "anthropic": {
        "light": ("claude-haiku-5-5", "claude-haiku-4-5"),
        "standard": ("claude-sonnet-5", "claude-sonnet-5-5"),
        "heavy": ("claude-opus-5-5", "claude-opus-5"),
    },
    # Conservative until measured: today's default (gpt-4o-mini) stays the light row; the gpt-5.6-* family is not
    # routed to (no measurement, newer provider quirks) — heavy reuses gpt-4o, the strongest proven row.
    "openai": {
        "light": ("gpt-4o-mini",),
        "standard": ("gpt-4o",),
        "heavy": ("gpt-4o",),
    },
    "gemini": {
        "light": ("gemini-1.5-flash",),
        "standard": ("gemini-1.5-flash",),
        "heavy": ("gemini-1.5-pro",),
    },
}


def tier_for(purpose: Optional[str]) -> Optional[str]:
    """The tier of a purpose, ``None`` for ``chat`` / omitted (no routing). An unknown purpose raises — a typo
    must not silently route to the default."""
    if purpose is None or purpose == "chat":
        return None
    if purpose not in _TIER_OF_PURPOSE:
        raise ValueError(f"unknown LLM purpose {purpose!r}; expected one of {PURPOSES}")
    return _TIER_OF_PURPOSE[purpose]


def resolve_model(provider: str, purpose: Optional[str]) -> Optional[str]:
    """The model the policy picks for ``(provider, purpose)``, or ``None`` = "no routing, keep the caller's /
    config default" (``chat`` / omitted purpose, or no routable candidate for this provider)."""
    from .models import models_for

    tier = tier_for(purpose)
    if tier is None:
        return None
    candidates = TIERS.get(provider, {}).get(tier, ())
    routable = {m.id for m in models_for(provider, "chat") if not m.stub}
    for model_id in candidates:
        if model_id in routable:
            return model_id
    logger.debug("llm.model_policy: no routable %s/%s model (candidates=%s) — default model stands",
                 provider, tier, candidates)
    return None
