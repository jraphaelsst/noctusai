"""
Typed exceptions for the NoctusAI LLM layer.

All three subclass `AppException`, so the framework's exception handler
auto-formats them into standardized JSON error responses with Portuguese
messages and proper HTTP status codes.
"""
from __future__ import annotations

from typing import Optional

from noctusai_lib.exceptions import AppException


class LLMNotConfigured(AppException):
    """The resolved API key for the requested provider is empty/missing.

    Raised when `key_provider(provider, org_id)` returns None after checking
    all three tiers (org_settings, platform_settings, env). User-facing
    Portuguese message guides the user to the Core API Keys settings page.
    """

    def __init__(self, provider: str, message: Optional[str] = None):
        super().__init__(
            code="LLM_NOT_CONFIGURED",
            message=message or (
                f"{provider.capitalize()} API Key não configurada. "
                "Acesse Configurações > Chaves de API para configurar."
            ),
            status_code=400,
            details={"provider": provider},
        )


class LLMAPIError(AppException):
    """Downstream error from an LLM provider's API (rate-limit, timeout, etc.).

    Wraps the provider's original error message. Use `status_code=502` by
    default (Bad Gateway — upstream service failed) so callers can distinguish
    "our code is broken" (500) from "the provider returned an error" (502).
    """

    def __init__(self, provider: str, message: str, status_code: int = 502):
        super().__init__(
            code="LLM_API_ERROR",
            message=f"Erro na API {provider.capitalize()}: {message}",
            status_code=status_code,
            details={"provider": provider},
        )


class LLMBudgetExceeded(AppException):
    """The org's monthly LLM budget has been exhausted.

    Raised by `noctusai_lib.llm.budget.enforce_budget` BEFORE provider
    dispatch when current-month spend ≥ 100% of the configured monthly
    budget (`org_settings` key `monthly_llm_budget_brl`). Soft-warn
    threshold (80%) only logs and does not raise.

    Status code 429 (Too Many Requests) — closest match for "rate-limited
    by your own admin policy". Service code can `except LLMBudgetExceeded`
    and degrade gracefully (return cached value, fallback string, etc.).
    """

    def __init__(self, org_id: Optional[str], spent_brl: float, budget_brl: float):
        super().__init__(
            code="LLM_BUDGET_EXCEEDED",
            message=(
                f"Orçamento mensal de IA atingido (R$ {spent_brl:.2f} / "
                f"R$ {budget_brl:.2f}). Aumente o orçamento em Configurações "
                "ou aguarde o próximo ciclo mensal."
            ),
            status_code=429,
            details={
                "org_id": org_id,
                "spent_brl": round(spent_brl, 2),
                "budget_brl": round(budget_brl, 2),
            },
        )


class ProviderNotImplemented(AppException):
    """A stub provider's method was called outside UI-development mode.

    Anthropic and Gemini providers are stubs today — they refuse to serve
    responses unless `NOCTUSAI_ALLOW_STUB_PROVIDERS=1` is set in the
    environment. This prevents a stub from accidentally handling real
    production traffic.

    Status code 501 (Not Implemented) makes the nature of the failure obvious
    in server logs and API clients.
    """

    def __init__(self, provider: str):
        super().__init__(
            code="PROVIDER_NOT_IMPLEMENTED",
            message=(
                f"{provider.capitalize()} provider is a stub and not yet wired to "
                "the real SDK. Set NOCTUSAI_ALLOW_STUB_PROVIDERS=1 for "
                "UI-development mode, or implement the real provider."
            ),
            status_code=501,
            details={"provider": provider},
        )
