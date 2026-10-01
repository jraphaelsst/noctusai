"""Captcha gate for this product's public forms (`/api/checkout`,
`/api/cadastro`) — ONE resolver, two honest states.

User decision 2026-10-01 ("captcha-off mode for soft launch"): when no
Turnstile keys are configured the public forms submit WITHOUT a captcha.
That used to happen implicitly — `make_turnstile_verifier(secret=None)`
fell back to the seed `FakeTurnstileVerifier`, which accepts any
non-empty token, so prod ran a fake security check it never declared.
This module replaces that with an EXPLICIT state:

- **enabled** (`turnstile_secret_key` resolves): a `RealTurnstileVerifier`,
  strict — a missing / rejected token is a 403, exactly as the contract
  says. The Fake is never constructed on this path.
- **disabled** (no secret anywhere): no verifier at all; an empty or
  missing token is accepted and every request logs ONE structured
  WARNING ("captcha desativado: nenhuma chave Turnstile configurada").
  Rate limiting on the routes is untouched.

The state is public (`GET /api/planos/publicos` → `captcha`), so the FE
renders the widget only when the backend will actually check it.

Edge case — secret set, site key missing: the form cannot obtain a
token, so it cannot be submitted. The gate stays `obrigatorio=True`
with `site_key=None` (never silently downgraded to "disabled" — the
operator configured a captcha), the FE shows "Cadastro temporariamente
indisponível", and the resolver logs an ERROR naming the missing key.

Test seam: the services' `turnstile_verifier=` constructor argument
(wrapped by `CaptchaGate.com_verificador`) and the router dependency
`get_captcha_resolver` (FastAPI `dependency_overrides`). The seed Fake
lives ONLY behind those seams.
"""
from __future__ import annotations

# NOC-REMEDIATE[fake-or-refuse-seed]: 3rd explicit "configured → real, unconfigured → declared state, Fake only via test seam" resolver in community (payments `_fake_ou_recusa`, WhatsApp `resolve_community_waha_client`, this one) — formalize in the seed (`noctusai_lib.integrations.turnstile` factory) — 2026-10-01

import logging
from dataclasses import dataclass
from typing import Callable, Optional

from noctusai_lib.integrations.turnstile import RealTurnstileVerifier, TurnstileVerifier
from noctusai_lib.security.api_keys import resolve_api_key

from app.config import settings

logger = logging.getLogger(__name__)

CAPTCHA_DESATIVADO_LOG = "captcha desativado: nenhuma chave Turnstile configurada"
CAPTCHA_SEM_SITE_KEY_LOG = (
    "captcha obrigatório mas sem site key: turnstile_secret_key configurada e "
    "turnstile_site_key ausente — os formulários públicos não podem ser enviados"
)


@dataclass(frozen=True)
class CaptchaGate:
    """The resolved captcha state for one org. `verificador is None` ⇔
    captcha disabled (no secret configured)."""

    verificador: Optional[TurnstileVerifier]
    site_key: Optional[str]

    @classmethod
    def desativado(cls) -> "CaptchaGate":
        return cls(verificador=None, site_key=None)

    @classmethod
    def com_verificador(cls, verificador: TurnstileVerifier, site_key: Optional[str] = None) -> "CaptchaGate":
        return cls(verificador=verificador, site_key=site_key)

    @property
    def obrigatorio(self) -> bool:
        return self.verificador is not None

    def publico(self) -> dict:
        """The additive `captcha` field of `GET /api/planos/publicos`."""
        return {"obrigatorio": self.obrigatorio, "site_key": self.site_key if self.obrigatorio else None}

    async def verificar(self, token: Optional[str], *, remote_ip: Optional[str], rota: str) -> bool:
        """True when the submission may proceed. Disabled → always True,
        with one structured WARNING per request."""
        if self.verificador is None:
            logger.warning(
                CAPTCHA_DESATIVADO_LOG,
                extra={"evento": "captcha_desativado", "rota": rota},
            )
            return True
        resultado = await self.verificador.verify(token or "", remote_ip=remote_ip)
        return resultado.success


CaptchaResolver = Callable[[str], CaptchaGate]


def resolve_captcha(
    org_id: str,
    *,
    resolve: Callable[[str, str], Optional[str]] = resolve_api_key,
) -> CaptchaGate:
    """Resolve this org's captcha state.

    Secret: org key store (`turnstile_secret_key`, Configurações) → the
    seed platform chain → `settings.community_turnstile_secret`
    (`COMMUNITY_TURNSTILE_SECRET`, the pre-key-store env name).
    Site key: org key store (`turnstile_site_key`) → platform chain →
    `settings.community_turnstile_site_key` (`COMMUNITY_TURNSTILE_SITE_KEY`).
    """
    secret = resolve("turnstile_secret_key", org_id) or settings.community_turnstile_secret or None
    if not secret:
        return CaptchaGate.desativado()
    site_key = resolve("turnstile_site_key", org_id) or settings.community_turnstile_site_key or None
    if not site_key:
        logger.error(
            CAPTCHA_SEM_SITE_KEY_LOG,
            extra={"evento": "captcha_sem_site_key", "org_id": org_id},
        )
    return CaptchaGate(verificador=RealTurnstileVerifier(secret=secret), site_key=site_key)


def get_captcha_resolver() -> CaptchaResolver:
    """FastAPI dependency — the router-level test seam
    (`app.dependency_overrides[get_captcha_resolver]`)."""
    return resolve_captcha
