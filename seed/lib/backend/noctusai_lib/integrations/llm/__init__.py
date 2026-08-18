"""
NoctusAI shared LLM client.

All products access LLMs exclusively through this module. No product code
imports `openai`, `anthropic`, or `google-genai` directly — those
live behind the `LLMProvider` Protocol in
`noctusai_lib.integrations.llm.providers`.

Usage at product startup (main.py):

    from noctusai_lib.config.credentials import configure_credentials, resolve_credential
    from noctusai_lib.integrations.llm import LLMConfig

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

    from . import chat_completion, generate_embedding, build_cached_messages

    summary = await chat_completion(
        messages=build_cached_messages(SYSTEM_PROMPT, user_text),
        model="gpt-4o",
        org_id=user.org_id,
    )
"""
from .audio import transcribe_audio
from .cache import (
    CacheBackend,
    InMemoryCacheBackend,
    build_cache_key,
)
from .chat import (
    build_cached_messages,
    chat_completion,
    chat_completion_stream,
)
from .client import (
    configure_llm,
    get_llm_config,
    get_provider,
    resolve_api_key,
    shutdown_llm,
)
from .config import KeyProvider, LLMConfig
from .embeddings import generate_embedding, generate_embeddings_batch
from .vision import analyze_image
from .refusal import analyze_image_with_refusal_retry, looks_like_refusal
from .budget import (
    compute_spend_usd,
    compute_status as compute_budget_status,
    configure_budget_module,
    enforce_budget,
    fetch_budget_brl,
    is_configured as is_budget_configured,
)
from .exceptions import (
    LLMAPIError,
    LLMBudgetExceeded,
    LLMNotConfigured,
    ProviderNotImplemented,
)
from .models import (
    MODELS,
    ModelEntry,
    ModelKind,
    all_providers,
    is_stub_model,
    models_for,
)

# Side-effect import: populates the provider registry with openai, anthropic,
# and gemini. FakeProvider is available via `from .providers
# import FakeProvider` but NOT auto-registered (tests own the instance).
from . import providers as _providers  # noqa: F401
from .providers import FakeProvider
from .providers.base import LLMProvider
from .registry import (
    get_provider_class,
    list_providers,
    register,
)
from .usage import (
    InMemoryUsageSink,
    SupabaseUsageSink,
    UsageEvent,
    UsageSink,
    estimate_cost_usd,
    record_usage,
)
from .inputs import (
    audio_bytes_to_named_buffer,
    image_bytes_to_data_url,
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
    "generate_embeddings_batch",
    "transcribe_audio",
    "analyze_image",
    "looks_like_refusal",
    "analyze_image_with_refusal_retry",
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
    # Input-shape helpers (vision data URLs, audio buffers)
    "image_bytes_to_data_url",
    "audio_bytes_to_named_buffer",
]
