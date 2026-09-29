"""Assistente IA do negócio (contract §E2).

  POST /api/comercial/negocios/{negocio_id}/assistente
       {acao: "resumo"|"proxima_acao"|"rascunho_mensagem", canal?: "email"|"whatsapp"}
       → {data: {texto}}

Claude via the seed LLM stack (`app/services/assistente.py`). Nothing is
written: the text is a suggestion the operator reads, edits and sends
themselves. LLM failures answer the contract's machine-error shape so the
card can say WHY (not configured / budget / provider down) instead of a
generic 500.

LGPD-GATED (`igig.assistente_negocio`, `app/services/ai_consent_features.py`):
the prompt carries the lead's name/empresa + the negócio's context — personal
data reaching Anthropic — so the route is gated by the platform's AI-consent
guard (`noctusai_lib.domain.ai.consent_required`). A caller without consent
gets HTTP 412 `{"error": {"code": "AI_CONSENT_REQUIRED", "message": ...}}`
(the seed's `AppException` envelope — `ApiError.code`/`.status` on the
frontend); the negócio card shows a pt-BR explanation + a link to
`/settings/ai` instead of a raw error
(`frontend/src/components/comercial/NegocioCardDialog.tsx`).

RATE-LIMITED PER CALLER (plat achado #22): `noctusai_lib.api.app_factory`
never installs `SlowAPIMiddleware`, so the Limiter's own `default_limits`
("100/minute") is inert — only a route explicitly wearing `@limiter.limit`
is ever throttled anywhere in this product (confirmed; not fixed here, it
is a seed-wide gap outside this file's scope, reported to the tech-lead).
This is the one endpoint in igig that spends real money per call (an
Anthropic completion), so it gets its OWN limit rather than waiting on that
seed fix.
"""
# NOTE: no `from __future__ import annotations` — this module IS rate-limited;
# see esteira_router.py for the slowapi/PEP 563 interaction.
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from noctusai_lib.domain.ai import consent_required
from noctusai_lib.integrations.llm import LLMAPIError, LLMBudgetExceeded, LLMNotConfigured
from noctusai_lib.primitives.responses import success_response
from slowapi.util import get_remote_address

from app.config import settings
from app.dependencies import coerce_org_uuid, get_current_user_org
from app.pipelines import get_admin_db, get_db
from app.rate_limit import limiter
from app.schemas.automacoes import AssistenteIn
from app.services import assistente

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/comercial/negocios", tags=["comercial-assistente"])


def get_gerador_texto() -> assistente.GeradorTexto:
    """DI seam for the LLM call — tests override with a `GeradorTexto` whose
    `chat` is backed by the seed `FakeProvider`."""
    return assistente.GeradorTexto()


def _falha(status: int, code: str, mensagem: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"detail": mensagem, "code": code})


def _caller_key(request: Request) -> str:
    """Rate-limit key = the caller's own bearer credential — "per user", not
    per visitor IP (an office shares one IP; a JWT does not). Falls back to
    the socket address when there is no Authorization header at all (should
    never happen past `get_current_user_org`'s own 401, but a key function
    must not raise)."""
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        return f"bearer:{authorization[7:]}"
    return get_remote_address(request)


@router.post("/{negocio_id}/assistente")
@limiter.limit(lambda: settings.assistente_rate_limit, key_func=_caller_key)
async def assistente_negocio(
    request: Request,
    negocio_id: str,
    payload: AssistenteIn,
    auth: tuple = Depends(get_current_user_org),
    _consent: None = Depends(consent_required("igig.assistente_negocio")),
    db: Any = Depends(get_db),
    admin_db: Any = Depends(get_admin_db),
    gerador: assistente.GeradorTexto = Depends(get_gerador_texto),
) -> dict:
    org_id = str(coerce_org_uuid(auth[2]))
    contexto = assistente.montar_contexto(db, admin_db, org_id, negocio_id)
    try:
        texto = await assistente.gerar(
            gerador, contexto, acao=payload.acao, canal=payload.canal, org_id=org_id
        )
    except LLMNotConfigured as exc:
        logger.warning("assistente: IA não configurada org=%s: %s", org_id, exc)
        raise _falha(503, "ia_nao_configurada",
                     "A IA não está configurada (chave da Anthropic ausente).") from exc
    except LLMBudgetExceeded as exc:
        logger.warning("assistente: orçamento de IA excedido org=%s", org_id)
        raise _falha(429, "orcamento_ia_excedido",
                     "O limite de uso de IA da organização foi atingido.") from exc
    except LLMAPIError as exc:
        logger.error("assistente: provedor de IA falhou org=%s: %s", org_id, exc)
        raise _falha(502, "ia_indisponivel",
                     "O provedor de IA não respondeu. Tente novamente em instantes.") from exc
    if not texto:
        logger.error("assistente: resposta vazia do modelo org=%s negocio=%s", org_id, negocio_id)
        raise _falha(502, "ia_resposta_vazia", "A IA não retornou texto. Tente novamente.")
    return success_response({"texto": texto})
