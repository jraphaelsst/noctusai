"""Which Esteira post a headline / roteiro is bound to (esteira-contract.md section 5.3).

The relationship lives on ``cs_posts`` (``headline_id`` / ``roteiro_id`` FKs, each unique), so the
library rows carry no column of their own: the ``post`` of a row is a lookup on the post table,
done ONCE per page of rows (two reads, never one per row), org-scoped. Shared by the headline
and roteiro presenters so both answer the same ``{id, titulo, etapa_label} | null`` shape
(``PostRef`` in ``frontend/src/types/geracao.ts``).
"""
from __future__ import annotations

from typing import Any, Iterable, Literal

from noctusai_lib.integrations.persistence.table_reads import batched

POSTS = "cs_posts"
STAGES = "pipeline_stages"

Coluna = Literal["headline_id", "roteiro_id"]


def post_refs(db: Any, org_id: str, coluna: Coluna, ids: Iterable[Any]) -> dict[str, dict[str, str]]:
    """``{library_row_id: {id, titulo, etapa_label}}`` for the rows that are bound to a post."""
    wanted = sorted({str(i) for i in ids if i})
    if not wanted:
        return {}
    posts: list[dict[str, Any]] = []
    for chunk in batched(wanted):
        posts.extend(
            db.table(POSTS).select(f"id,titulo,etapa_id,{coluna}")
            .eq("org_id", org_id).in_(coluna, chunk).execute().data or []
        )
    if not posts:
        return {}
    labels: dict[str, str] = {}
    etapa_ids = sorted({str(p["etapa_id"]) for p in posts if p.get("etapa_id")})
    for chunk in batched(etapa_ids):
        for s in db.table(STAGES).select("id,label").eq("org_id", org_id).in_("id", chunk).execute().data or []:
            labels[str(s["id"])] = s["label"]
    return {
        str(p[coluna]): {
            "id": str(p["id"]),
            "titulo": p["titulo"],
            "etapa_label": labels.get(str(p.get("etapa_id")), ""),
        }
        for p in posts
        if p.get(coluna)
    }
