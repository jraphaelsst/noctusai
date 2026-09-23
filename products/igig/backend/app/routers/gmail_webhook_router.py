"""Gmail reply-watch push receiver (slice B, roadmap R8).

  POST /api/webhooks/gmail/push   PUBLIC — Pub/Sub push subscription target

Verify BEFORE anything else (KB § PATTERNS/security/webhook-signatures.md):
the Google-signed OIDC token Pub/Sub attaches is checked by the seed
``verify_push_token`` against ``GMAIL_PUSH_AUDIENCE`` and the pinned
``GMAIL_PUSH_SERVICE_ACCOUNT`` — any Google service account can mint a token
for any audience, so an audience-only check would prove nothing about who
sent it. Missing push config ⇒ 503: an unverifiable push is refused, never
processed.

Responses: 204 processed (or nothing to do) · 400 malformed envelope · 401
token refused · 503 push config missing · 500 processing failure (Pub/Sub
redelivers; the reply log is unique per message, so a retry cannot double).
"""
# NOTE: no `from __future__ import annotations` — consistent with the other
# IgIg routers.
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from noctusai_lib.integrations.gmail import (
    GmailPushAuthError,
    GmailPushEnvelopeError,
    parse_push_envelope,
    verify_push_token,
)
from noctusai_lib.integrations.gmail.push import TokenVerifier

from app.config import settings
from app.email_deps import (
    EmailSenderFactory,
    GmailClientFactory,
    get_email_sender_factory,
    get_email_settings,
    get_gmail_client_factory,
    get_push_token_verifier,
)
from app.pipelines import get_admin_db, get_core_db
from app.rate_limit import limiter
from app.repositories import Repositorios
from app.services import email_config, orcamento_email
from app.services.email_config import EmailSettings
from app.store import get_repositorios_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks/gmail", tags=["webhooks"])


@router.post("/push", status_code=204)
@limiter.limit(settings.webhook_rate_limit)
async def receber_push(
    request: Request,
    verifier: Optional[TokenVerifier] = Depends(get_push_token_verifier),
    admin_db: Any = Depends(get_admin_db),
    core: Any = Depends(get_core_db),
    repos: Repositorios = Depends(get_repositorios_admin),
    gmail_factory: GmailClientFactory = Depends(get_gmail_client_factory),
    sender_factory: EmailSenderFactory = Depends(get_email_sender_factory),
    cfg: EmailSettings = Depends(get_email_settings),
) -> Response:
    gcp = email_config.gcp_config(cfg)
    if gcp is None:
        logger.error(
            "push do gmail RECUSADO: configuração GCP ausente (%s)",
            ", ".join(email_config.gcp_faltando(cfg)),
        )
        raise HTTPException(status_code=503, detail="Push do Gmail não configurado.")
    try:
        verify_push_token(
            request.headers.get("authorization"),
            audience=gcp.audience,
            expected_service_account=gcp.service_account,
            verifier=verifier,
        )
    except GmailPushAuthError as erro:
        logger.warning("push do gmail recusado: %s", erro)
        raise HTTPException(status_code=401, detail="Token de push inválido.") from erro
    try:
        nota = parse_push_envelope(await request.body())
    except GmailPushEnvelopeError as erro:
        logger.warning("push do gmail malformado: %s", erro)
        raise HTTPException(status_code=400, detail="Envelope de push inválido.") from erro

    resultado = await orcamento_email.processar_notificacao(
        admin_db, repos, core, nota,
        gmail_factory=gmail_factory, sender_factory=sender_factory, settings=cfg,
    )
    logger.info(
        "push do gmail processado mailbox=%s pubsub=%s watches=%d respostas=%d",
        nota.email_address, nota.pubsub_message_id, resultado["watches"], resultado["respostas"],
    )
    return Response(status_code=204)
