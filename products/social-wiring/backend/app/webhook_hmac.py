"""The WAHA webhook HMAC secret in a deploy context (security review L2, 2026-11-03).

With `WAHA_WEBHOOK_HMAC_SECRET` SET, the webhook routes verify it and refuse an unsigned / badly signed call with a strict 401
(`webhook_endpoint`, unchanged). With it UNSET in a deploy context the routes still accept (the shared WAHA does not sign today, so
refusing would make Julia and the inbox deaf) -- but that is a degraded-security state and is NEVER silent: an ERROR
`webhook_hmac_desativado` once per process, and `/api/health` reports it in `startup_hook_error` (the seed's named degraded-boot
field) from the lifespan hook.

NOC-REMEDIATE[waha-hmac-prod]: enable signing (runbook: products/social-wiring/README.md "Enabling the WAHA webhook HMAC"), then this
module's accept-unsigned branch can become a refusal — 2026-11-03.
"""
from __future__ import annotations

import logging
from typing import Any

from noctusai_lib.config.deploy_config import is_deploy_context

logger = logging.getLogger(__name__)

CODIGO = "webhook_hmac_desativado"
_AVISADO = False


class WebhookHmacDesativado(RuntimeError):
    """Raised by the lifespan hook so the seed parks it on `/api/health` `startup_hook_error`."""


def desativado(cfg: Any) -> bool:
    """True when this is a deploy context and no HMAC secret is configured."""
    return is_deploy_context() and not (getattr(cfg, "waha_webhook_hmac_secret", "") or "").strip()


def avisar_uma_vez(cfg: Any, rota: str) -> bool:
    """Log the ERROR `webhook_hmac_desativado` the first time per process an unsigned-capable webhook is served without a secret.
    Returns whether the state is degraded (the call is accepted either way)."""
    global _AVISADO
    if not desativado(cfg):
        return False
    if not _AVISADO:
        _AVISADO = True
        logger.error(
            "%s: %s -- WAHA webhooks are accepted UNSIGNED in a deploy context (WAHA_WEBHOOK_HMAC_SECRET is not set); "
            "set it and the same hmac key on the WAHA session to enable verification", rota, CODIGO)
    return True


def sinalizar_na_saude(cfg: Any) -> None:
    """Lifespan hook tail: in the degraded state raise, so the seed logs it and `/api/health` carries it in `startup_hook_error`."""
    if desativado(cfg):
        raise WebhookHmacDesativado(CODIGO)


def _resetar_para_testes() -> None:
    """Test seam: the once-per-process latch."""
    global _AVISADO
    _AVISADO = False
