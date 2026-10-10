"""Esteira — generate a reel caption for a post (esteira-contract.md section 5.3).

The caption is RETURNED, never saved: the user edits it and PATCHes the post. Refusals happen before
the model is called: a foreign post is a 404, a post without a completed roteiro a 422
``sem_roteiro``, the per-user daily cap a 429 + ``Retry-After``, a missing AI key / exhausted org
budget a 503.

The per-user daily cap (``legendas_dia_usuario``) is the count of the user's rows in
``cs_legenda_geracoes`` (migration 242) over a rolling 24 h window. A row is written only once the
model was actually reached (a missing key, an exhausted budget or a provider failure costs no slot;
an unparseable reply does, the model was paid).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from noctusai_lib.integrations.llm import LLMBudgetExceeded, LLMNotConfigured, resolve_api_key

from app.modules.media_creation.prompts.legenda_reel import (
    LEGENDA_REEL_SYSTEM_PROMPT,
    LegendaParseError,
    build_legenda_user_message,
    parse_legenda,
)
from app.modules.media_creation.services import geracao_jobs
from app.modules.media_creation.services.roteiro_service import make_chat_roteiro_llm

logger = logging.getLogger(__name__)

POSTS = "cs_posts"
ROTEIROS = "cs_roteiros"
HEADLINES = "cs_headlines"
MARCA_PERFIL = "cs_marca_perfil"
GERACOES = "cs_legenda_geracoes"
JANELA = timedelta(hours=24)

MSG_SEM_ROTEIRO = "Conclua o roteiro do post antes de gerar a legenda."
MSG_LIMITE = "Limite diário de legendas atingido"
MSG_IA_NAO_CONFIGURADA = "A IA não está configurada para esta conta."
MSG_ORCAMENTO = "O orçamento de IA da organização foi excedido."
MSG_IA_FALHOU = "A IA não conseguiu gerar a legenda. Tente novamente."

#: ``(system_prompt, user_message, org_id) -> raw model reply`` (the roteiro seam's shape).
LegendaLlm = Callable[[str, str, Optional[str]], Awaitable[str]]


class LegendaError(Exception):
    def __init__(self, status: int, detail: Any, headers: Optional[dict[str, str]] = None):
        super().__init__(str(detail))
        self.status = status
        self.detail = detail
        self.headers = headers


def get_legenda_llm() -> LegendaLlm:
    """DI seam for the model (Anthropic + ``geracao_llm_model``). Tests override with a fake."""
    return make_chat_roteiro_llm()


#: ``(org_id) -> None``; raises :class:`LegendaError` 503 when no AI key resolves.
IaCheck = Callable[[Optional[str]], None]


def check_ia_configurada(org_id: Optional[str]) -> None:
    try:
        resolve_api_key("anthropic", org_id)
    except LLMNotConfigured as exc:
        raise LegendaError(503, {"code": "ia_nao_configurada", "detail": MSG_IA_NAO_CONFIGURADA}) from exc


def get_legenda_ia_check() -> IaCheck:
    """DI seam for :func:`check_ia_configurada`. Tests override with a no-op."""
    return check_ia_configurada


class LegendaService:
    def __init__(
        self, db: Any, org_id: str, user_id: str, *, cfg: Any, llm: LegendaLlm,
        ia_check: IaCheck = check_ia_configurada,
    ):
        self.ia_check = ia_check
        self.db = db
        self.org_id = org_id
        self.user_id = user_id
        self.cfg = cfg
        self.llm = llm

    def _um(self, table: str, cols: str, row_id: Any) -> Optional[dict[str, Any]]:
        rows = self.db.table(table).select(cols).eq("id", str(row_id)).eq("org_id", self.org_id).execute().data
        return rows[0] if rows else None

    def _contexto(self, post_id: str) -> dict[str, str]:
        post = self._um(POSTS, "id,marca_id,headline_id,roteiro_id", post_id)
        if post is None:
            raise LegendaError(404, "Post não encontrado")
        roteiro = self._um(ROTEIROS, "id,status,conteudo,headline_texto", post["roteiro_id"]) if post.get("roteiro_id") else None
        if roteiro is None or roteiro.get("status") != "completo" or not (roteiro.get("conteudo") or "").strip():
            raise LegendaError(422, {"code": "sem_roteiro", "detail": MSG_SEM_ROTEIRO})
        headline = roteiro.get("headline_texto") or ""
        if post.get("headline_id"):
            h = self._um(HEADLINES, "id,texto", post["headline_id"])
            headline = (h or {}).get("texto") or headline
        perfil = (
            self.db.table(MARCA_PERFIL).select("bio,ctas").eq("marca_id", str(post["marca_id"])).execute().data or [{}]
        )[0]
        return {
            "roteiro": roteiro["conteudo"], "headline": headline,
            "bio": perfil.get("bio") or "", "ctas": perfil.get("ctas") or "",
        }

    def _assert_cap(self) -> None:
        """429 + Retry-After when the user already generated ``legendas_dia_usuario`` captions in 24 h."""
        limite = int(self.cfg.legendas_dia_usuario)
        desde = datetime.now(timezone.utc) - JANELA
        rows = (
            self.db.table(GERACOES).select("created_at")
            .eq("org_id", self.org_id).eq("user_id", self.user_id)
            .gte("created_at", desde.isoformat()).order("created_at").limit(limite).execute().data or []
        )
        if len(rows) >= limite:
            mais_antiga = datetime.fromisoformat(str(rows[0]["created_at"]).replace("Z", "+00:00"))
            espera = max(1, int((mais_antiga + JANELA - datetime.now(timezone.utc)).total_seconds()))
            raise LegendaError(429, {"code": "limite_diario", "detail": MSG_LIMITE}, headers={"Retry-After": str(espera)})

    def _registrar(self, post_id: str) -> None:
        """Spend one slot: the model was reached."""
        self.db.table(GERACOES).insert({
            "org_id": self.org_id, "user_id": self.user_id, "post_id": post_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

    async def gerar(self, post_id: str) -> dict[str, Any]:
        ctx = self._contexto(post_id)
        self.ia_check(self.org_id)
        await geracao_jobs.assert_orcamento_ia(self.org_id)
        self._assert_cap()
        try:
            reply = await self.llm(
                LEGENDA_REEL_SYSTEM_PROMPT, build_legenda_user_message(**ctx), self.org_id,
            )
        except LLMNotConfigured as exc:
            raise LegendaError(503, {"code": "ia_nao_configurada", "detail": MSG_IA_NAO_CONFIGURADA}) from exc
        except LLMBudgetExceeded as exc:
            raise LegendaError(503, {"code": "orcamento_ia_excedido", "detail": MSG_ORCAMENTO}) from exc
        except Exception as exc:  # noqa: BLE001 - provider failure surfaced as 502, no slot spent
            logger.error("legenda: IA falhou post=%s (%s: %s)", post_id, type(exc).__name__, exc)
            raise LegendaError(502, {"code": "ia_falhou", "detail": MSG_IA_FALHOU}) from exc
        self._registrar(post_id)
        try:
            return parse_legenda(reply)
        except LegendaParseError as exc:
            logger.warning("legenda: resposta inválida post=%s (%s)", post_id, exc)
            raise LegendaError(502, {"code": "ia_resposta_invalida", "detail": MSG_IA_FALHOU}) from exc


__all__ = [
    "LegendaError",
    "LegendaService",
    "get_legenda_ia_check",
    "get_legenda_llm",
]
