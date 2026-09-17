"""E-signature webhook receiver — contract §3.4.

Unauthenticated by design (mounted OUTSIDE `get_current_user_org`, same
posture `whatsapp_router.py`'s WAHA receiver documents): the provider's
own signature over the raw body is the only authenticity check. That check
is NOT reimplemented here — `noctusai_lib.integrations.signature.
SignatureAdapter.validar_webhook` owns the vendor wire shape and the HMAC
comparison (`D4SignAdapter` calls `noctusai_lib.security.webhook_
signatures.verify_hmac_sha256_hex` internally, so the shared HMAC helper
IS in the verification path — just one layer down, inside the seed IO
module rather than this router). This router never parses a
vendor-specific field and never imports `httpx` — the signature-
integration contract's own rule ("no vendor code outside configuration").

WHICH ORG'S CREDENTIALS VERIFY THE SIGNATURE
---------------------------------------------
`POST /api/webhooks/assinatura/{provedor}` carries no org segment — it is
ONE shared URL for every org on the platform, matching how a provider
webhook is actually registered (one callback URL per D4Sign account).
Credentials are therefore resolved at the PLATFORM tier
(`get_signature_adapter_factory()(None)` — `resolve_credential`'s
org_settings tier is skipped, platform_settings/env still apply) for THIS
route only; the org-scoped POST/GET/cancel routes in `card_hub/
assinatura_router.py` still resolve per-org. Once the signature verifies,
`EventoAssinatura.external_id` is looked up against
`atendimento_contrato_assinaturas` (`(provedor, external_id)` is UNIQUE —
migration 134) to find which org/contract it belongs to. An unknown id is
a retired envelope, not an attack, and gets a quiet 200 (contract §3.4) —
this is a deliberate design call surfaced to the tech-lead, not a re-guess
of an underspecified contract point: §1.4/§1.5 do not name a per-org
webhook URL shape, so a single shared platform credential is the only
verifiable reading absent one.

🔴 NO ``from __future__ import annotations`` IN THIS MODULE.
``@limiter.limit`` (slowapi) resolves the endpoint's ``Request`` parameter
by INSPECTING THE SIGNATURE AT RUNTIME. PEP 563 turns every annotation
into a string, so slowapi finds no ``Request``, and the route raises at
call time instead of at import — a failure that no unit test importing the
module would see. Same gotcha fixed in ``063ac09d`` for the community
api_keys router; gated by ``TestCheckSlowapiWithPep563``. Every annotation
below (``str``, ``Request``, the imported alias, ``dict``) resolves
eagerly, so the import buys nothing here anyway.
"""

import logging

from fastapi import APIRouter, Depends, Request

from noctusai_lib.integrations.signature import ProvedorNaoConfigurado, WebhookInvalido

from app.config import settings
from app.modules.card_hub import assinatura_service
from app.modules.card_hub.assinatura_service import WebhookAssinaturaInvalida
from app.modules.card_hub.deps import (
    SignatureAdapterFactory,
    get_card_hub_client,
    get_signature_adapter_factory,
    get_storage_backend,
)
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks/assinatura", tags=["webhooks"])


@router.post("/{provedor}")
@limiter.limit(settings.webhook_rate_limit)
async def post_assinatura_webhook(
    provedor: str,
    request: Request,
    client=Depends(get_card_hub_client),
    storage=Depends(get_storage_backend),
    adapter_factory: SignatureAdapterFactory = Depends(get_signature_adapter_factory),
) -> dict:
    corpo = await request.body()
    cabecalhos = dict(request.headers)

    try:
        adapter = adapter_factory(None)
    except (ProvedorNaoConfigurado, ValueError) as exc:
        # Cannot verify without the platform-tier credential (or an
        # unsupported `provedor`) — "cannot verify" is treated as
        # "invalid", never as a silent 200. See this module's docstring.
        logger.error(
            "assinatura webhook (%s): cannot verify — provider not "
            "configured at the platform tier: %s", provedor, exc,
        )
        raise WebhookAssinaturaInvalida() from exc

    try:
        evento = adapter.validar_webhook(corpo, cabecalhos)
    except WebhookInvalido as exc:
        logger.warning(
            "assinatura webhook (%s): signature rejected: %s", provedor, exc
        )
        raise WebhookAssinaturaInvalida() from exc

    return await assinatura_service.aplicar_evento_webhook(client, storage, adapter, evento)


__all__ = ["router"]
