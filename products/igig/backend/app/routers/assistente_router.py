"""Assistente IA do negócio (contract §E2).

  POST /api/comercial/negocios/{negocio_id}/assistente
       {acao: "resumo"|"proxima_acao"|"rascunho_mensagem", canal?: "email"|"whatsapp"}
       → {data: {texto}}

Claude via the seed LLM stack (`app/services/assistente.py`). Nothing is
written: the text is a suggestion the operator reads, edits and sends
themselves. LLM failures answer the contract's machine-error shape so the
card can say WHY (not configured / budget / provider down) instead of a
generic 500.
"""
# NOTE: no `from __future__ import annotations` — consistent with the other
# IgIg routers; see esteira_router.py.
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from noctusai_lib.integrations.llm import LLMAPIError, LLMBudgetExceeded, LLMNotConfigured
from noctusai_lib.primitives.responses import success_response

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.pipelines import get_admin_db, get_db
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


@router.post("/{negocio_id}/assistente")
async def assistente_negocio(
    negocio_id: str,
    payload: AssistenteIn,
    auth: tuple = Depends(get_current_user_org),
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
