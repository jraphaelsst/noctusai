"""
NoctusAI shared LLM client.

All products access LLMs exclusively through this module. No product code
imports `openai`, `anthropic`, or `google-genai` directly — those
live behind the `LLMProvider` Protocol in `noctusai_lib.llm.providers`.

Usage at product startup (main.py):

    from noctusai_lib.credentials import configure_credentials, resolve_credential
    from noctusai_lib.llm import LLMConfig

    configure_credentials(
        supabase_url=settings.supabase_url,
        supabase_anon_key=settings.supabase_anon_key,
        supabase_service_role_key=settings.supabase_service_role_key,
    )

    llm_config = LLMConfig(
        key_provider=lambda provider, org_id=None: resolve_credential(
            f"{provider}_api_key", org_id
        ),
        default_provider="openai",
        default_chat_model="gpt-4o-mini",
    )

    app = create_product_app(..., llm_config=llm_config)

Usage in services (Phase 4 wires these entry points):

    from noctusai_lib.llm import chat_completion, generate_embedding, build_cached_messages

    summary = await chat_completion(
        messages=build_cached_messages(SYSTEM_PROMPT, user_text),
        model="gpt-4o",
        org_id=user.org_id,
    )
"""
from noctusai_lib.llm.audio import transcribe_audio
from noctusai_lib.llm.cache import (
    CacheBackend,
    InMemoryCacheBackend,
    build_cache_key,
)
from noctusai_lib.llm.chat import (
    build_cached_messages,
    chat_completion,
    chat_completion_stream,
)
from noctusai_lib.llm.client import (
    configure_llm,
    get_llm_config,
    get_provider,
    resolve_api_key,
    shutdown_llm,
)
from noctusai_lib.llm.config import KeyProvider, LLMConfig
from noctusai_lib.llm.embeddings import generate_embedding
from noctusai_lib.llm.vision import analyze_image
from noctusai_lib.llm.budget import (
    compute_spend_usd,
    compute_status as compute_budget_status,
    configure_budget_module,
    enforce_budget,
    fetch_budget_brl,
    is_configured as is_budget_configured,
)
from noctusai_lib.llm.exceptions import (
    LLMAPIError,
    LLMBudgetExceeded,
    LLMNotConfigured,
    ProviderNotImplemented,
)
from noctusai_lib.llm.models import (
    MODELS,
    ModelEntry,
    ModelKind,
    all_providers,
    is_stub_model,
    models_for,
)

# Side-effect import: populates the provider registry with openai, anthropic,
# and gemini. FakeProvider is available via `from noctusai_lib.llm.providers
# import FakeProvider` but NOT auto-registered (tests own the instance).
from noctusai_lib.llm import providers as _providers  # noqa: F401
from noctusai_lib.llm.providers import FakeProvider
from noctusai_lib.llm.providers.base import LLMProvider
from noctusai_lib.llm.registry import (
    get_provider_class,
    list_providers,
    register,
)
from noctusai_lib.llm.usage import (
    InMemoryUsageSink,
    SupabaseUsageSink,
    UsageEvent,
    UsageSink,
    estimate_cost_usd,
    record_usage,
)

__all__ = [
    # Configuration
    "LLMConfig",
    "KeyProvider",
    "configure_llm",
    "get_llm_config",
    "get_provider",
    "resolve_api_key",
    "shutdown_llm",
    # Exceptions
    "LLMAPIError",
    "LLMBudgetExceeded",
    "LLMNotConfigured",
    "ProviderNotImplemented",
    # Budget guardrails (Phase 18 X4)
    "compute_spend_usd",
    "compute_budget_status",
    "configure_budget_module",
    "enforce_budget",
    "fetch_budget_brl",
    "is_budget_configured",
    # Model catalog
    "MODELS",
    "ModelEntry",
    "ModelKind",
    "all_providers",
    "is_stub_model",
    "models_for",
    # Providers & registry
    "LLMProvider",
    "FakeProvider",
    "get_provider_class",
    "list_providers",
    "register",
    # High-level entry points (what product services call)
    "chat_completion",
    "chat_completion_stream",
    "build_cached_messages",
    "generate_embedding",
    "transcribe_audio",
    "analyze_image",
    # Response cache (Phase 8)
    "CacheBackend",
    "InMemoryCacheBackend",
    "build_cache_key",
    # Usage accounting (Phase 15)
    "UsageEvent",
    "UsageSink",
    "InMemoryUsageSink",
    "SupabaseUsageSink",
    "estimate_cost_usd",
    "record_usage",
]
