"""Knowledge documents ↔ the seed editorial workflow (project
``seed-editorial-workflow``, slice E5).

A *governed* collection (``requer_revisao``) routes every document write through
the editorial state machine instead of landing live: a new document is a
``rascunho`` item whose row is ``ativo=false`` (invisible to retrieval); a
changed document mints a new draft version while the published one keeps
serving. The ``knowledge_documents`` ROW always carries the PUBLISHED content
(migration 018's publish trigger copies it), which is why retrieval needs no
second read path.

This module holds only the store-agnostic pieces both
``FakeStudioKnowledgeStore`` and ``SupabaseStudioKnowledgeStore`` share: the
content shape, the stable item ref, the draft identity and the
create-or-new-version decision.

Boundary (decided 2026-10-05, E5): agent-package sync (``app.studio.project_sources``)
is NEVER governed — developer-owned context stays git-is-the-source
(Decision Board agents-a1..a5). It writes with ``editorial=False`` and refuses
(409) to touch a governed document or collection rather than bypassing review.
"""
from __future__ import annotations

import uuid
from typing import Any, Mapping
from uuid import UUID

from app.stores._db_errors import StudioConflict
from noctusai_lib.domain.editorial import Action, EditorialStore, State

#: ``editorial_items.kind`` for a knowledge document; its ``ref`` is ``<agent_id>/<slug>``.
EDITORIAL_KIND = "knowledge_document"

#: Machine identity that authors imported/package drafts when no human is the
#: author. Display name ``Claude (rascunho)`` — a service identity, NOT a user
#: account (``editorial_versions.author_id`` has no FK), so a human editor can
#: approve its drafts (separation of duties compares ids).
CLAUDE_DRAFT_AUTHOR_ID = uuid.uuid5(uuid.NAMESPACE_URL, "noctusai:agents:claude-rascunho")
CLAUDE_DRAFT_AUTHOR_NAME = "Claude (rascunho)"

#: The grant a draft write is stamped with. Drafting is not an approval: the
#: admin gate already ran on the route, and every approval/publish still
#: needs its own real grant through ``editorial_router``.
DRAFT_GRANTS: tuple[str, ...] = ("editorial:editar",)


def item_ref(agent_id: UUID, slug: str) -> str:
    return f"{agent_id}/{slug}"


def version_content(
    *, titulo: str, tipo: str, resumo: str | None, proveniencia: Mapping[str, Any] | None,
    conteudo: str, source_sha: str,
) -> dict[str, Any]:
    """The JSON an editorial version carries for a document — exactly the
    columns migration 018's publish trigger copies onto the row."""
    return {
        "titulo": titulo, "tipo": tipo, "resumo": resumo,
        "proveniencia": dict(proveniencia or {}), "conteudo": conteudo, "source_sha": source_sha,
    }


def stage_draft(
    editorial: EditorialStore, *, org_id: UUID, ref: str, item_id: UUID | None,
    content: dict[str, Any], author_id: UUID | None,
) -> tuple[UUID, str]:
    """Create the item (``created``) or mint a new draft version on it
    (``updated``) — ``unchanged`` when the current version already carries this
    exact ``source_sha``. Returns ``(item_id, outcome)``.

    A document in review or archived cannot take a new version: that is a
    typed 409 the caller reports per item, never a silent overwrite.
    """
    actor = author_id or CLAUDE_DRAFT_AUTHOR_ID
    if item_id is None:
        res = editorial.create_item(
            org_id=org_id, kind=EDITORIAL_KIND, ref=ref, content=content, actor_id=actor, grants=DRAFT_GRANTS,
        )
        return res.item.id, "created"
    item = editorial.get_item(org_id, item_id)
    current = editorial.list_versions(org_id, item_id)[-1]
    if current.content.get("source_sha") == content["source_sha"]:
        return item_id, "unchanged"
    if item.state == State.ARQUIVADO.value:
        raise StudioConflict("editorial_archived", "documento arquivado: não aceita nova versão")
    if item.state not in (State.RASCUNHO.value, State.PUBLICADO.value):
        raise StudioConflict(
            "editorial_in_review",
            "documento em revisão: devolva-o a rascunho (ou aguarde) antes de enviar nova versão",
        )
    editorial.apply(
        org_id=org_id, item_id=item_id, action=Action.EDIT.value, actor_id=actor,
        grants=DRAFT_GRANTS, content=content,
    )
    return item_id, "updated"
