"""
NoctusAI Shared Backend — Common utilities for all NoctusAI backends.

Consolidates duplicated code (exceptions, responses, middleware, logging,
auth helpers, database factory, config base, credential resolution, LLM
access, and app bootstrap) so that each product backend imports from a
single source of truth.

**Lazy-loading note (2026-04-28).** The heavy attributes (LLM provider
classes, credential helpers) used to be eagerly imported at package load
time, which transitively pulled in `anthropic`, `openai`, `google.genai`,
`supabase`, `redis`, `jinja2`, etc. That meant ANY import of any
`noctusai_lib` sub-module — even the lightweight `logging_config` —
required the full backend SDK stack. CLI / MCP / utility consumers got
silent fallbacks because import errors in one transitive dep masked
the real cause. Per the audit in `projects/platform-logging-
standardization/PROJECT.md` (review item A1), the heavy attributes are
now resolved on first access via PEP-562 `__getattr__`. The public
import API (`from noctusai_lib import LLMConfig`) is unchanged.
"""
from __future__ import annotations

from noctusai_lib._version import __lib_version__

# Map: public attribute name → module path it lives in. Resolved lazily
# below; first access triggers the heavy import, subsequent accesses hit
# the cached `globals()` entry.
_LAZY_ATTRS = {
    # `noctusai_lib.config.credentials` imports supabase. Old path
    # `noctusai_lib.credentials` is a transitional shim — see
    # `KB § PATTERNS/seed-lib-layout.md § Migration history`.
    "configure_credentials": "noctusai_lib.config.credentials",
    "resolve_credential": "noctusai_lib.config.credentials",
    # `noctusai_lib.integrations.llm` imports anthropic, openai,
    # google.genai, redis. Old path `noctusai_lib.llm` is a transitional
    # shim — see `KB § PATTERNS/seed-lib-layout.md § Migration history`.
    "KeyProvider": "noctusai_lib.integrations.llm",
    "LLMConfig": "noctusai_lib.integrations.llm",
    "LLMAPIError": "noctusai_lib.integrations.llm",
    "LLMNotConfigured": "noctusai_lib.integrations.llm",
    "ProviderNotImplemented": "noctusai_lib.integrations.llm",
}


def __getattr__(name: str):
    """PEP 562 lazy attribute access for the heavy public surface."""
    module_path = _LAZY_ATTRS.get(name)
    if module_path is None:
        raise AttributeError(
            f"module 'noctusai_lib' has no attribute {name!r} "
            f"(known lazy attrs: {sorted(_LAZY_ATTRS)})"
        )
    import importlib
    module = importlib.import_module(module_path)
    value = getattr(module, name)
    globals()[name] = value  # cache so subsequent accesses skip __getattr__
    return value


def __dir__() -> list[str]:
    """Make `dir(noctusai_lib)` enumerate the lazy attrs alongside __all__."""
    return sorted(set(globals().keys()) | set(_LAZY_ATTRS.keys()))


__all__ = [
    "configure_credentials",
    "resolve_credential",
    "KeyProvider",
    "LLMConfig",
    "LLMAPIError",
    "LLMNotConfigured",
    "ProviderNotImplemented",
    # Runtime propagation breadcrumb (see `seed-inheritance-hardening` Phase 3)
    "__lib_version__",
]
