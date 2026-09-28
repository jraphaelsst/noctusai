"""Assistente IA do negócio — resumo, próxima ação, rascunho de mensagem
(roadmap R11 "AI assist", contract §E2).

Context = the lead + the negócio (stage, value, owner, stage history) + the
card-hub timeline (notes, checklist events, documents — metadata only, never a
document's content) + the negócio's orçamentos. The model is Claude through the
seed LLM stack (`noctusai_lib.integrations.llm.chat_completion`, provider
`anthropic`), pinned to `claude-sonnet-4-6` (leftovers item 16): "the first
Anthropic chat model the seed catalog lists" used to mean claude-opus-5 —
flagship-tier cost and liable to silently change again on the next catalog
reorder — for drafting client-facing messages that need real quality but not
that budget. `GeradorTexto.model` still lets a caller (tests, a future
operator setting) override the pin explicitly.

`cache=False` on every call: the prompt carries a named person's contact data
and the agency's notes about them (LGPD — the response cache is for
deterministic, non-personal prompts).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from noctusai_lib.domain.card_hub.timeline import get_timeline
from noctusai_lib.integrations.llm import build_cached_messages, chat_completion
from noctusai_lib.integrations.llm.models import models_for

from app.services import quadro_comum as qc

logger = logging.getLogger(__name__)

__all__ = ["GeradorTexto", "gerar", "modelo_padrao", "montar_contexto"]

PROVEDOR = "anthropic"
#: Pinned (leftovers item 16) — see the module docstring.
MODELO_PADRAO_ID = "claude-sonnet-4-6"

_SISTEMA = (
    "Você é o assistente comercial de uma agência de marketing digital brasileira. "
    "Responda SEMPRE em português do Brasil, com objetividade, usando apenas os fatos "
    "do contexto fornecido — nunca invente dados, valores, datas ou compromissos. "
    "Se faltar informação para algo, diga o que falta."
)

_INSTRUCOES = {
    "resumo": (
        "Faça um resumo executivo deste negócio em até 6 tópicos curtos: quem é o lead, "
        "o que ele precisa, em que etapa está e há quanto tempo, propostas enviadas e o "
        "que aconteceu de relevante na linha do tempo."
    ),
    "proxima_acao": (
        "Recomende a PRÓXIMA ação comercial concreta para avançar este negócio, com o "
        "porquê em uma frase e um prazo sugerido. Se houver risco de perda, aponte-o."
    ),
    "rascunho_mensagem": (
        "Escreva um rascunho de mensagem para o lead que ajude a avançar o negócio, "
        "pronto para o vendedor revisar e enviar. Não prometa nada que não esteja no contexto."
    ),
}
_CANAL = {
    "email": "Formato: e-mail — inclua uma linha 'Assunto:' e um corpo cordial e profissional.",
    "whatsapp": "Formato: WhatsApp — curto, direto e cordial, sem assunto, no máximo 3 parágrafos curtos.",
}


def modelo_padrao() -> str:
    """The pinned assistant model (`MODELO_PADRAO_ID`), verified against the
    seed catalog. Raises if it is no longer listed there — an unroutable
    assistant must fail loudly, never silently fall back to whichever model
    happens to sort first."""
    ids_catalogo = {m.id for m in models_for(PROVEDOR, "chat")}
    if MODELO_PADRAO_ID not in ids_catalogo:
        raise RuntimeError(
            f"modelo padrão do assistente ({MODELO_PADRAO_ID}) não está no catálogo de modelos do seed"
        )
    return MODELO_PADRAO_ID


@dataclass
class GeradorTexto:
    """The one LLM call, as an injectable seam (`chat` defaults to the seed's
    `chat_completion`; tests pass one backed by the seed `FakeProvider`)."""

    chat: Callable[..., Awaitable[str]] = chat_completion
    provider: str = PROVEDOR
    model: Optional[str] = None
    chamadas: list[dict] = field(default_factory=list)

    async def __call__(self, messages: list[dict], *, org_id: str) -> str:
        modelo = self.model or modelo_padrao()
        self.chamadas.append({"provider": self.provider, "model": modelo, "org_id": org_id})
        return await self.chat(
            messages,
            provider=self.provider,
            model=modelo,
            org_id=org_id,
            temperature=0.4,
            max_tokens=1200,
            cache=False,
        )


def _enxuto(linha: Optional[dict], campos: tuple[str, ...]) -> Optional[dict]:
    if not linha:
        return None
    return {c: linha.get(c) for c in campos if linha.get(c) not in (None, "", {}, [])}


def montar_contexto(db: Any, admin_db: Any, org_id: str, negocio_id: str) -> dict:
    """Everything the model sees, and nothing more (data minimisation).

    Raises the seed `NotFoundError` (→ 404) for a negócio outside the org.
    """
    from app.card_hub import CARD_HUB_NEGOCIO

    negocio = qc.carregar(db, "negocio", org_id, negocio_id, rotulo="negócio")
    lead = qc.carregar(db, "lead", org_id, str(negocio["lead_id"]), rotulo="lead")
    etapas = {
        str(e["id"]): e.get("label")
        for e in db.table("pipeline_stages").select("id, label").eq("org_id", org_id)
        .eq("pipeline", "comercial").execute().data or []
    }
    responsavel = None
    if negocio.get("responsavel_id"):
        prof = (
            db.table("profissional").select("nome").eq("id", negocio["responsavel_id"])
            .eq("org_id", org_id).execute().data or []
        )
        responsavel = prof[0].get("nome") if prof else None
    historico = sorted(
        db.table("pipeline_movimentos").select("de_etapa_id, para_etapa_id, motivo, created_at")
        .eq("org_id", org_id).eq("pipeline", "comercial").eq("entidade_id", negocio_id)
        .execute().data or [],
        key=lambda r: str(r.get("created_at") or ""),
    )
    orcamentos = (
        db.table("orcamento")
        .select("versao, titulo, status, total_mensal, validade, enviado_em, respondido_em, motivo_recusa")
        .eq("org_id", org_id).eq("negocio_id", negocio_id).execute().data or []
    )
    timeline = get_timeline(CARD_HUB_NEGOCIO, admin_db, org_id, negocio_id, limit=30)["items"]
    return {
        "lead": _enxuto(lead, (
            "nome", "empresa", "email", "telefone", "instagram", "origem", "como_conheceu",
            "especificacoes", "observacoes", "status",
            # Módulo-1 pré-qualificação fields (achado #8) — the aba's own
            # text claims the assistant "lê o lead", but these were the four
            # fields a formulário lead actually carries and the model never
            # saw: nicho, orçamento, canais already in use, and what hurts.
            "nicho", "canais_atuais", "dores", "orcamento_disponivel",
        )),
        "negocio": {
            **(_enxuto(negocio, ("titulo", "valor_estimado", "status", "stage_entered_at",
                                 "motivo_perda", "created_at")) or {}),
            "etapa": etapas.get(str(negocio.get("etapa_id"))),
            "responsavel": responsavel,
        },
        "historico_etapas": [
            {
                "de": etapas.get(str(m.get("de_etapa_id"))),
                "para": etapas.get(str(m.get("para_etapa_id"))),
                "motivo": m.get("motivo"),
                "quando": m.get("created_at"),
            }
            for m in historico
        ],
        "orcamentos": [_enxuto(o, tuple(o.keys())) for o in orcamentos],
        "linha_do_tempo": [
            {k: v for k, v in item.items() if k not in ("id", "ator") and v not in (None, "", [], {})}
            for item in timeline
        ],
    }


async def gerar(
    gerador: GeradorTexto, contexto: dict, *, acao: str, canal: Optional[str], org_id: str
) -> str:
    instrucao = _INSTRUCOES[acao]
    if acao == "rascunho_mensagem":
        instrucao += " " + _CANAL.get(canal or "whatsapp", _CANAL["whatsapp"])
    usuario = (
        f"{instrucao}\n\nContexto (JSON):\n"
        f"{json.dumps(contexto, ensure_ascii=False, default=str, indent=1)}"
    )
    texto = await gerador(
        build_cached_messages(_SISTEMA, usuario, provider=gerador.provider), org_id=org_id
    )
    return (texto or "").strip()
