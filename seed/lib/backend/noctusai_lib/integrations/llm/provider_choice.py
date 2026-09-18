"""The lightweight manual LLM-provider switch — no local store, no UI.

WHY THIS EXISTS
----------------
`social-wiring`'s `app/services/api_keys_store.py` proved the shape a
per-org, manual, non-failover provider switch needs: read a setting named
`llm_<capability>_provider`, validate it against the capability's real
vendor set, fall back to the documented default (openai) when unset or
unknown. Its own docstring calls that shape "generic (product-agnostic)"
and then keeps it product-local anyway — deliberately, because that
product ALSO ships an encrypted local key store and an operator-facing
settings page, and generalising the two together would have coupled this
shape to that machinery.

Every other product's chat/vision call sites have neither. They call
`chat_completion(...)` / `analyze_image(...)` bare, which means the
process-wide `LLMConfig.default_provider` — "openai", set once in
`noctusai_seed.llm_defaults.default_llm_config` — decides for every org,
with no way to say otherwise short of an env-var-wide flip that moves
every product at once. The 2026-09-17 OpenAI-quota incident is what
surfaced that gap: a single vendor's outage took down every product with
no operator lever to pull.

This module is that lever, with NO new machinery: it reads the SAME
`org_settings` → `platform_settings` → env chain
(`noctusai_lib.config.credentials.resolve_credential`) social-wiring's
switch already reads, under the SAME setting names
(`llm_chat_provider` / `llm_vision_provider` / `llm_embedding_provider`)
it already established — so an operator (or an agent acting on the
operator's instruction) can flip a product's vendor with a single
`org_settings` row, exactly as was done for social-wiring itself, with
zero product-specific code beyond wrapping the existing call site in
`resolve_llm_provider(...)`.

A product that later wants an operator-facing settings PAGE (a spec, a
tested UI, a masked-secret store) still reaches for the fuller shape —
`noctusai_lib.security.api_keys` + `noctusai_seed.api_keys_router` — this
module does not replace that. It exists for the products that have no
such page today and should not need one just to stop being pinned to a
single vendor.

🔴 MANUAL, NOT A FALLBACK. Exactly the same reasoning as social-wiring's
switch: nothing here fails over on an error or a 429. A silent vendor
swap changes which model answered a request with nobody told, and predicting
"why does this read differently from yesterday" becomes unanswerable. The
operator picks; the pick is a value read once per call, never a retry
branch.

🔴 EMBEDDINGS NEVER OFFER "anthropic". `anthropic_provider.generate_embedding`
raises `ProviderNotImplemented` — that vendor has no embeddings endpoint at
all. A caller for the "embedding" capability must pass an `allowed` tuple
that excludes it; this module does not hardcode capability→vendor maps
because the real per-provider MODEL a caller then pins (e.g. `OCR_MODELS`
in `noctusai_lib.integrations.documents.transcription`) is call-site
knowledge, not this module's.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from noctusai_lib.config.credentials import resolve_credential

logger = logging.getLogger(__name__)

__all__ = ["resolve_llm_provider"]

#: The `org_settings` / `platform_settings` key a capability's switch reads,
#: e.g. `llm_chat_provider`. Matches the setting names social-wiring's
#: `api_keys_store.CHAT_PROVIDER_KEY` / `VISION_PROVIDER_KEY` /
#: `EMBEDDING_PROVIDER_KEY` already use, so a value an operator saved for
#: one product is discoverable under the same name for another.
_SETTING_PREFIX = "llm_"
_SETTING_SUFFIX = "_provider"


def resolve_llm_provider(
    capability: str,
    org_id: Optional[str],
    *,
    allowed: tuple[str, ...],
    default: str = "openai",
    resolver: Callable[[str, Optional[str]], Optional[str]] = resolve_credential,
) -> str:
    """Which vendor `capability` ("chat" / "vision" / "embedding") should
    use for this org. Always one of `allowed`; never raises.

    Reads `llm_<capability>_provider` through `resolver` (the platform
    3-tier chain by default: `org_settings` → `platform_settings` → env —
    see `noctusai_lib.config.credentials.resolve_credential`). Falls back
    to `default` when the setting was never saved OR holds a value outside
    `allowed` — the second case logs at WARNING because it can only mean a
    vendor was retired from `allowed` while an org still pointed at it, or
    the row was written by hand with a typo; running the documented default
    and saying so beats handing an unroutable vendor name to the LLM stack
    and failing one layer down with a message about a missing key.

    `default` MUST be a member of `allowed` — a caller asking for a default
    it does not also allow is a configuration bug in the CALL SITE, not a
    runtime condition to degrade from, so this is asserted rather than
    silently coerced.

    Args:
        capability: Names the setting (`llm_{capability}_provider`) and
            appears in the WARNING log line. Use `"chat"`, `"vision"`, or
            `"embedding"` — the three capabilities the seed's LLM entry
            points cover today.
        org_id: Scopes tier-1 (`org_settings`) resolution. `None` skips
            straight to `platform_settings` → env, same as every other
            `resolve_credential` caller.
        allowed: The vendors this call site can actually route to. For
            `"embedding"`, MUST exclude `"anthropic"` — see the module
            docstring.
        default: The vendor used when the setting is unset or invalid.
            Defaults to `"openai"` so wiring this into an existing call
            site changes NO behaviour for an org that has not opted in.
        resolver: DI seam for tests — same signature as
            `resolve_credential`, defaulting to the real platform chain.

    Returns:
        A value from `allowed`.
    """
    assert default in allowed, (
        f"resolve_llm_provider({capability!r}): default {default!r} is not "
        f"in allowed={allowed!r} — fix the call site."
    )
    key = f"{_SETTING_PREFIX}{capability}{_SETTING_SUFFIX}"
    raw = resolver(key, str(org_id) if org_id else None)
    chosen = (raw or "").strip()
    if not chosen:
        return default
    if chosen not in allowed:
        logger.warning(
            "resolve_llm_provider: %s=%r is not a routable %s vendor %s — using %r",
            key, chosen, capability, allowed, default,
        )
        return default
    return chosen
