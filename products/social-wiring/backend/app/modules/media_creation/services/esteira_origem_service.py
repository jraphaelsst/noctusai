"""Esteira -- the card's origin (estruturas-contract.md section 6.8, tier ``org``).

Composed at READ time from ``cs_posts`` -> ``cs_roteiros`` / ``cs_headlines`` -> ``cs_estrutura_usos`` ->
``cs_estruturas`` so ``esteira_service`` / ``routers/esteira.py`` stay untouched by the read side. Writes nothing.

``legenda.origem``: the finalizer's ``legenda_gerada`` event stores ``codigo = sha256(generated text)`` (never the
text); ``"ia"`` iff the card's current caption hashes to the latest such event of its flow, ``"usuario"`` when the
caption is non-NULL and differs (or no such event exists), ``None`` when the caption is NULL.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional

from app.modules.media_creation import estruturas_formatos as fmt
from app.modules.media_creation.services.headlines_roteiros_service import (
    HEADLINES, ROTEIRO_COLS, ROTEIROS, HeadlinesRoteirosError, apresentar_roteiro, conversas_visiveis, estruturas_usadas,
)

logger = logging.getLogger(__name__)

POSTS = "cs_posts"
EVENTOS = "cs_fluxo_eventos"


def sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


class EsteiraOrigemService:
    def __init__(self, db: Any, *, org_id: str, user_id: str):
        self.db = db
        self.org_id = str(org_id)
        self.user_id = str(user_id)

    def _um(self, table: str, cols: str, row_id: Any) -> Optional[dict[str, Any]]:
        rows = self.db.table(table).select(cols).eq("id", str(row_id)).eq("org_id", self.org_id).execute().data
        return rows[0] if rows else None

    def _legenda(self, post: dict[str, Any]) -> dict[str, Any]:
        texto = post.get("legenda")
        if texto is None:
            return {"texto": None, "origem": None}
        eventos: list[dict[str, Any]] = []
        filtros = [("post_id", post["id"])]
        if post.get("roteiro_id"):
            filtros.append(("roteiro_id", post["roteiro_id"]))
        for coluna, valor in filtros:
            eventos.extend(
                self.db.table(EVENTOS).select("codigo,created_at").eq("org_id", self.org_id)
                .eq("tipo", "legenda_gerada").eq(coluna, str(valor)).order("created_at", desc=True).limit(1)
                .execute().data or []
            )
        eventos = [e for e in eventos if e.get("codigo")]
        ultimo = max(eventos, key=lambda e: str(e.get("created_at") or ""), default=None)
        ia = ultimo is not None and sha256_texto(texto) == ultimo["codigo"]
        return {"texto": texto, "origem": "ia" if ia else "usuario"}

    def origem(self, post_id: str) -> dict[str, Any]:
        post = self._um(POSTS, "id,formato,legenda,headline_id,roteiro_id", post_id)
        if post is None:
            raise HeadlinesRoteirosError(404, "Post não encontrado")
        roteiro = self._um(ROTEIROS, ROTEIRO_COLS, post["roteiro_id"]) if post.get("roteiro_id") else None
        headline_id = post.get("headline_id") or (roteiro or {}).get("headline_id")
        headline = self._um(HEADLINES, "id,texto,conversa_id", headline_id) if headline_id else None

        usos = estruturas_usadas(
            self.db, self.org_id,
            roteiro_ids=[roteiro["id"]] if roteiro else (), headline_ids=[headline["id"]] if headline else (),
        )
        estruturas = (
            (usos.get(("roteiro", str(roteiro["id"]))) if roteiro else None)
            or (usos.get(("headline", str(headline["id"]))) if headline else None)
            or []
        )
        conversa_id = (roteiro or {}).get("conversa_id") or (headline or {}).get("conversa_id")
        conversa = conversas_visiveis(self.db, self.org_id, self.user_id, [conversa_id]).get(str(conversa_id)) if conversa_id else None

        resumo = apresentar_roteiro(roteiro) if roteiro else None
        try:
            do_card = fmt.formato_da_estrutura(post.get("formato"))
        except ValueError:
            logger.warning("esteira origem: formato de post desconhecido %r no card %s", post.get("formato"), post["id"])
            do_card = None
        return {
            "headline": None if headline is None else {"id": str(headline["id"]), "texto": headline["texto"]},
            "roteiro": resumo,
            "estruturas": estruturas,
            # the roteiro's own formato wins; a card without a roteiro answers the card's formato in Estrutura vocabulary
            "formato": resumo["formato"] if resumo else do_card,
            "legenda": self._legenda(post),
            "conversa": conversa,
        }
