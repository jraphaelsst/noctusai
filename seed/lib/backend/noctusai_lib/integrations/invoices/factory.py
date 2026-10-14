"""`make_invoice_provider` - Fake or one Real provider, fake-or-refuse.

Production guard (contract 4, D36). The Focus environment comes from CONFIG,
never from a request, and `producao` needs BOTH:

  1. env `FOCUSNFE_ALLOW_PRODUCTION=1` (an operator decision on the host), AND
  2. the platform-tier credential `focusnfe_environment=producao`.

Anything else is `homologacao` - except that a platform credential asking for
`producao` WITHOUT the env switch is REFUSED (`production_not_allowed`), not
silently downgraded: issuing "real" notes into homologacao while the operator
believes they are live is exactly the silent failure this guard exists to stop.

Token tier: a Focus token belongs to ONE environment. The platform credential
`focusnfe_token_environment` declares which; a declared tier that differs from
the resolved environment is refused, and `producao` additionally REQUIRES the
tier to be declared (fail-closed). Per-company tokens carry their environment
in `CompanyTokenStore` and are refused on mismatch there.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Optional, Union

import httpx

from noctusai_lib.integrations.fake_or_refuse import resolve_fake_or_refuse

from .errors import InvoiceNotConfigured
from .fake import FakeInvoiceProvider
from .focus import FocusNFeInvoiceProvider
from .types import InvoiceEnvironment

ENV_ALLOW_PRODUCTION = "FOCUSNFE_ALLOW_PRODUCTION"
CRED_TOKEN = "focusnfe_token"
CRED_ENVIRONMENT = "focusnfe_environment"
CRED_TOKEN_ENVIRONMENT = "focusnfe_token_environment"

_ENV_BY_VALUE = {e.value: e for e in InvoiceEnvironment}


def _platform_credential(key: str) -> Optional[str]:
    # Lazy: config.credentials pulls the supabase client (see security.api_keys).
    from noctusai_lib.config.credentials import resolve_credential

    return resolve_credential(key)


def resolve_invoice_environment(
    *,
    environment_credential: Optional[str] = None,
    allow_production_env: Optional[bool] = None,
    token_environment: Optional[str] = None,
    fetch_credential: Callable[[str], Optional[str]] = _platform_credential,
) -> InvoiceEnvironment:
    """Apply the production guard. Explicit args win over the platform lookup
    (tests / hosts that already resolved them)."""
    cred = (
        environment_credential
        if environment_credential is not None
        else fetch_credential(CRED_ENVIRONMENT)
    )
    allowed = (
        allow_production_env
        if allow_production_env is not None
        else os.environ.get(ENV_ALLOW_PRODUCTION) == "1"
    )
    tier = (
        token_environment
        if token_environment is not None
        else fetch_credential(CRED_TOKEN_ENVIRONMENT)
    )
    wanted = (cred or "").strip().lower() or InvoiceEnvironment.HOMOLOGACAO.value
    environment = _ENV_BY_VALUE.get(wanted)
    if environment is None:
        raise InvoiceNotConfigured(
            "focusnfe", "ambiente do provedor de notas invalido", code="environment_invalid"
        )
    if environment is InvoiceEnvironment.PRODUCAO and not allowed:
        raise InvoiceNotConfigured(
            "focusnfe",
            f"producao exige {ENV_ALLOW_PRODUCTION}=1 no ambiente do servidor",
            code="production_not_allowed",
        )
    tier_value = (tier or "").strip().lower() or None
    if environment is InvoiceEnvironment.PRODUCAO and tier_value is None:
        raise InvoiceNotConfigured(
            "focusnfe", "token de producao nao declarado", code="token_tier_undeclared"
        )
    if tier_value is not None and tier_value != environment.value:
        raise InvoiceNotConfigured(
            "focusnfe",
            "token do provedor pertence a outro ambiente",
            code="token_environment_mismatch",
        )
    return environment


def _refuse() -> Any:
    raise InvoiceNotConfigured(
        "focusnfe", "provedor de notas fiscais nao configurado", code="not_configured"
    )


def make_invoice_provider(
    provider: str = "focusnfe",
    *,
    use_fake: bool = False,
    allow_fake: bool = False,
    account_token: Optional[str] = None,
    environment_credential: Optional[str] = None,
    allow_production_env: Optional[bool] = None,
    token_environment: Optional[str] = None,
    company_tokens: Optional[Callable[[str], Optional[str]]] = None,
    default_company_token: Optional[str] = None,
    transport: Optional[httpx.BaseTransport] = None,
    fetch_credential: Callable[[str], Optional[str]] = _platform_credential,
    unconfigured: Callable[[], Any] = _refuse,
    **fake_kwargs: Any,
) -> Union[FakeInvoiceProvider, FocusNFeInvoiceProvider, Any]:
    """Fake when `use_fake`; otherwise the Real provider, or a declared refusal.

    `allow_fake` is the explicit opt-in to fall back to the Fake when the
    account token is absent (never inferred). `unconfigured` defaults to raising
    `InvoiceNotConfigured` (503-shaped); pass a sentinel-returning callable to
    branch instead.
    """
    if use_fake:
        return FakeInvoiceProvider(**fake_kwargs)
    if provider != "focusnfe":
        raise ValueError(f"make_invoice_provider: unknown provider {provider!r}")

    token = account_token if account_token is not None else fetch_credential(CRED_TOKEN)

    def _build_real() -> FocusNFeInvoiceProvider:
        env = resolve_invoice_environment(
            environment_credential=environment_credential,
            allow_production_env=allow_production_env,
            token_environment=token_environment,
            fetch_credential=fetch_credential,
        )
        return FocusNFeInvoiceProvider(
            account_token=token or "",
            environment=env,
            company_tokens=company_tokens,
            default_company_token=default_company_token,
            transport=transport,
        )

    return resolve_fake_or_refuse(
        configured=bool(token),
        build_real=_build_real,
        build_fake=lambda: FakeInvoiceProvider(**fake_kwargs),
        allow_fake=allow_fake,
        unconfigured=unconfigured,
    )
