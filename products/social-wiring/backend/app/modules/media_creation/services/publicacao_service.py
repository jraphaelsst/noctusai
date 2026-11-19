"""Persistence of the Publicação block (``criacao-pipeline-contract.md`` 2.3, slice S9; migration 367).

Two moments, both single-writer (SW):

* :meth:`PublicacaoService.gravar` -- when the Diretor's reply is saved: one ``cs_chat_proposta_publicacoes`` row per option
  that carried a VALID block (``publicacoes.py``), the ``publicacao_gerada`` event per row and one ``publicacao_invalida``
  event counting the blocks the validator / binder dropped. Counts and ids only -- no text in the ledger.
* :meth:`PublicacaoService.aplicar_no_card` -- when the saga creates (or adopts) the card for a picked option: the caption,
  the five hashtags and the first comment land on ``cs_posts`` in ONE conditional update that only fires while the card's
  ``legenda`` is still NULL (a hand edit is never overwritten; the finalizer's own caption step then sees a caption and does
  not generate one). The post link is never touched: ``cs_posts.permalink`` is filled by the owner (contract 10.2).

The CTA objective / justification / sources stay on the publicação row until the pipeline's ``cs_posts`` columns land
(S4 migration 362). ``NOC-REMEDIATE[criacao-cta-no-post]`` -- 2026-12-15: copy them onto the card in
:meth:`aplicar_no_card` once ``cs_posts.cta_objetivo`` / ``cta_justificativa`` / ``fontes`` exist on dev.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Iterable, Optional

from app.modules.media_creation.services.publicacoes import PublicacaoValidada, Vinculo

logger = logging.getLogger(__name__)

TABELA = "cs_chat_proposta_publicacoes"
EVENTOS = "cs_fluxo_eventos"
POSTS = "cs_posts"


class PublicacaoService:
    def __init__(self, db: Any, org_id: str, user_id: Optional[str] = None) -> None:
        self.db = db
        self.org_id = org_id
        self.user_id = user_id

    # ── at reply-save time ───────────────────────────────────────────────────────────────────────────

    def gravar(
        self, conversa: dict[str, Any], mensagem_id: str, propostas: Iterable[dict[str, Any]], vinculo: Vinculo, invalidas: int,
    ) -> int:
        """Store the bound blocks. ``propostas`` are the saved rows (``id`` + ``ordem``); returns how many were stored."""
        por_ordem = {int(p["ordem"]): str(p["id"]) for p in propostas}
        linhas: list[dict[str, Any]] = []
        eventos: list[dict[str, Any]] = []
        for ordem, pub in sorted(vinculo.por_ordem.items()):
            proposta_id = por_ordem.get(ordem)
            if proposta_id is None:  # the binder matched an option the save did not keep: a bug, never a silent skip
                logger.error("publicacao: ordem %s sem proposta salva conversa=%s", ordem, conversa["id"])
                invalidas += 1
                continue
            linhas.append(self._linha(conversa, proposta_id, pub))
            eventos.append(self._evento(conversa, mensagem_id, "publicacao_gerada", proposta_id=proposta_id, contagem=1))
        total_invalidas = invalidas + vinculo.invalidas
        if total_invalidas:
            eventos.append(self._evento(conversa, mensagem_id, "publicacao_invalida", contagem=total_invalidas))
        if linhas:
            self.db.table(TABELA).insert(linhas).execute()
        if eventos:
            self.db.table(EVENTOS).insert(eventos).execute()
        return len(linhas)

    def _linha(self, conversa: dict[str, Any], proposta_id: str, pub: PublicacaoValidada) -> dict[str, Any]:
        return {
            "proposta_id": proposta_id, "org_id": self.org_id, "marca_id": conversa["marca_id"], "numero": pub.numero,
            "legenda": pub.legenda, "hashtags": list(pub.hashtags), "primeiro_comentario": pub.primeiro_comentario,
            "cta": pub.cta, "cta_objetivo": pub.cta_objetivo, "cta_justificativa": pub.cta_justificativa,
            "fontes": list(pub.fontes),
        }

    def _evento(
        self, conversa: dict[str, Any], mensagem_id: Optional[str], tipo: str, *, proposta_id: Optional[str] = None,
        contagem: Optional[int] = None, codigo: Optional[str] = None,
    ) -> dict[str, Any]:
        return {
            "id": str(uuid.uuid4()), "org_id": self.org_id, "marca_id": conversa["marca_id"], "conversa_id": conversa["id"],
            "proposta_id": proposta_id, "mensagem_id": mensagem_id, "ator_id": self.user_id, "tipo": tipo,
            "contagem": contagem, "codigo": codigo,
        }

    # ── at card time ─────────────────────────────────────────────────────────────────────────────────

    def da_proposta(self, proposta_id: str) -> Optional[dict[str, Any]]:
        rows = (
            self.db.table(TABELA).select("*").eq("proposta_id", proposta_id).eq("org_id", self.org_id).limit(1).execute().data
        )
        return rows[0] if rows else None

    def aplicar_no_card(self, proposta: dict[str, Any], post_id: str) -> bool:
        """Copy the stored block onto the card while its caption is empty. ``False`` = nothing to apply (no block, or the card
        already has a caption). A failure is recorded (``publicacao_falhou`` + the log) and returned as ``False``: the card
        and the saga go on, and the finalizer's caption step covers the empty caption."""
        pub = self.da_proposta(str(proposta["id"]))
        if pub is None:
            return False
        try:
            feito = bool(
                self.db.table(POSTS).update({
                    "legenda": pub["legenda"], "hashtags": list(pub["hashtags"]),
                    "primeiro_comentario": pub.get("primeiro_comentario"),
                }).eq("id", post_id).eq("org_id", self.org_id).is_("legenda", "null").execute().data
            )
        except Exception as exc:  # noqa: BLE001 - recorded below with its type only; the saga must not stop on a caption copy
            logger.exception("publicacao: falha ao aplicar no card proposta=%s post=%s", proposta["id"], post_id)
            self.db.table(EVENTOS).insert(self._evento(
                {"id": proposta["conversa_id"], "marca_id": proposta["marca_id"]}, None, "publicacao_falhou",
                proposta_id=str(proposta["id"]), codigo=type(exc).__name__[:60],
            )).execute()
            return False
        return feito


__all__ = ["PublicacaoService", "TABELA"]
