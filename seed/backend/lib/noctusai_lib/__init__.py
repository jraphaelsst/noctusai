"""
NoctusAI Shared Backend — Common utilities for all NoctusAI backends.

Consolidates duplicated code (exceptions, responses, middleware, logging,
auth helpers, database factory, config base, credential resolution, LLM
access, and app bootstrap) so that each product backend imports from a
single source of truth.
"""
from noctusai_lib._version import __lib_version__
from noctusai_lib.credentials import configure_credentials, resolve_credential
from noctusai_lib.llm import (
    KeyProvider,
    LLMAPIError,
    LLMConfig,
    LLMNotConfigured,
    ProviderNotImplemented,
)

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
