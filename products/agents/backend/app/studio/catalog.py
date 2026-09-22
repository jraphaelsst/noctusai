"""Production :class:`~app.studio.models.KnowledgeCatalog` — the knowledge
summary the compiler needs (contract §C ``CompileInput.knowledge``), read
through BE-KE's :class:`~app.stores.studio_knowledge.StudioKnowledgeStore`.

BE-DEF's compile/publish routes depend on ``get_knowledge_catalog_dep``, which
fails closed (503) until bound — ``app.main`` binds it to this class (§J2).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.studio.models import CollectionSummary

__all__ = ["StoreKnowledgeCatalog"]


class StoreKnowledgeCatalog:
    """Every collection of the agent with its ACTIVE document count.

    One ``count_documents`` read per collection: an agent has a handful of
    collections (the corpus is navigated by structure), so this stays a few
    small queries per compile; the ordering the compiler emits is its own
    ``(ordem, slug)`` sort, never this list's order."""

    def __init__(self, knowledge: Any) -> None:
        self._knowledge = knowledge

    def collection_summaries(self, org_id: UUID, agent_id: UUID) -> list[CollectionSummary]:
        return [
            CollectionSummary(
                slug=c.slug,
                nome=c.nome,
                tag=c.tag,
                descricao=c.descricao or "",
                doc_count=self._knowledge.count_documents(org_id, agent_id, c.id, ativo_only=True),
                ordem=c.ordem,
            )
            for c in self._knowledge.list_collections(org_id, agent_id)
        ]
