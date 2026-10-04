"""Consumer → Studio sync routes of Agent Packages: project sources (§G2),
learnings (§H2) and the project/learning read views the Studio tabs use.

Auth (§A8, §I) — the only routes a ``pk_*`` token may reach besides
``agent_packages_router``:

* ``PUT  /api/studio/agents/{key}/projects/{slug}/sources`` — scope
  ``project-knowledge:write`` (or an org admin).
* ``POST /api/studio/agents/{key}/learnings`` — scope ``learnings:write``
  (or an org admin).
* ``GET  /api/studio/agents/{key}/learnings`` — scope ``learnings:read`` (or
  any org member) — the promote tool reads accepted rows with it.
* ``PATCH /api/studio/agents/{key}/learnings/{id}`` — ADMIN USER only
  (``require_admin`` is ``user_only``: a token gets 403 ``user_required``).
* ``GET  /api/studio/agents/{key}/projects`` — any org member (user only).

Every route is org-scoped by ``ctx.org_id`` and refuses anything that is not
a ``dev-advisor`` studio agent with 404 ``agent_not_found``.
"""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import settings
from app.dependencies import (
    require_admin,
    require_learnings_read,
    require_learnings_write,
    require_member,
    require_project_knowledge_write,
)
from app.routers.agent_packages_router import resolve_dev_advisor
from app.routers.studio_agents_router import get_studio_definition_store_dep, http_error, store_errors
from app.routers.studio_knowledge_router import get_studio_knowledge_store_dep
from app.schemas.packages import (
    PROJECT_SLUG_MAX,
    SLUG_PATTERN,
    LearningListOut,
    LearningNewOut,
    LearningOut,
    LearningReviewIn,
    LearningsPushIn,
    LearningsPushOut,
    ProjectListOut,
    ProjectOut,
    SourceItem,
    SourcesBody,
    SourcesSyncOut,
    manifest_items,
)
from app.stores.agent_packages import LearningInput, LearningRecord, learning_row_sha
from app.stores.errors import NotFound
from app.studio.project_sources import SourcesRefused, collection_slug, sources_sha, sync_project_sources
from noctusai_lib.api.auth.session import AuthContext

router = APIRouter(prefix="/api/studio/agents", tags=["agent-packages"])

#: The body-cap pattern ``app.main`` registers for the sources PUT (§G2: 25 MB).
SOURCES_BODY_LIMIT_PATTERN = "/api/studio/agents/*/projects/*/sources"


def get_agent_package_store_dep():
    """Seam over ``get_agent_package_store`` — tests override it with one
    shared ``FakeAgentPackageStore``."""
    from app.stores.agent_packages import get_agent_package_store

    return get_agent_package_store(settings)


def _learning_out(rec: LearningRecord) -> LearningOut:
    return LearningOut(
        id=rec.id, project_slug=rec.project_slug, row_sha=rec.row_sha, data=rec.data, tipo=rec.tipo,
        texto=rec.texto, evidencia=rec.evidencia, row_status=rec.row_status, status=rec.status,
        nota=rec.review_note, reviewed_by=rec.reviewed_by, reviewed_at=rec.reviewed_at,
        created_at=rec.created_at,
    )


def _project_slug_or_422(slug: str) -> str:
    import re

    if len(slug) > PROJECT_SLUG_MAX or not re.fullmatch(SLUG_PATTERN, slug):
        raise http_error(422, "invalid_project_slug", "Slug de projeto inválido.")
    return slug


# ── §G2 — project sources ───────────────────────────────────────────────────


@router.put("/{key}/projects/{slug}/sources", response_model=SourcesSyncOut)
async def put_project_sources(
    key: str,
    slug: str,
    body: SourcesBody | list[SourceItem],
    ctx: AuthContext = Depends(require_project_knowledge_write),
    definitions=Depends(get_studio_definition_store_dep),
    knowledge=Depends(get_studio_knowledge_store_dep),
    packages=Depends(get_agent_package_store_dep),
) -> SourcesSyncOut:
    agent = resolve_dev_advisor(definitions, ctx.org_id, key)
    project = _project_slug_or_422(slug)
    try:
        items = manifest_items(body)
    except ValueError as exc:
        raise http_error(422, "duplicate_path", str(exc)) from exc
    try:
        with store_errors():
            result = sync_project_sources(
                org_id=ctx.org_id, agent_id=agent.id, project_slug=project, items=items,
                author_id=ctx.user_id, packages=packages, knowledge=knowledge,
            )
    except SourcesRefused as exc:
        raise http_error(exc.status, exc.code, exc.detail, **exc.extra) from exc
    return SourcesSyncOut(**result)


@router.get("/{key}/projects", response_model=ProjectListOut)
async def list_projects(
    key: str,
    ctx: AuthContext = Depends(require_member),
    definitions=Depends(get_studio_definition_store_dep),
    knowledge=Depends(get_studio_knowledge_store_dep),
    packages=Depends(get_agent_package_store_dep),
) -> ProjectListOut:
    agent = resolve_dev_advisor(definitions, ctx.org_id, key)
    by_project: dict[str, list] = {}
    for rec in packages.list_sources(ctx.org_id, agent.id):
        by_project.setdefault(rec.project_slug, []).append(rec)
    collections = {c.slug: c for c in knowledge.list_collections(ctx.org_id, agent.id)}
    items = []
    for slug in sorted(by_project):
        recs = by_project[slug]
        col = collections.get(collection_slug(slug))
        items.append(ProjectOut(
            slug=slug, colecao_id=col.id if col else None, total_fontes=len(recs),
            ultima_sincronizacao=max(r.synced_at for r in recs), sources_sha=sources_sha(recs),
        ))
    return ProjectListOut(items=items)


# ── §H2 — learnings ─────────────────────────────────────────────────────────


@router.post("/{key}/learnings", response_model=LearningsPushOut)
async def push_learnings(
    key: str,
    body: LearningsPushIn,
    ctx: AuthContext = Depends(require_learnings_write),
    definitions=Depends(get_studio_definition_store_dep),
    packages=Depends(get_agent_package_store_dep),
) -> LearningsPushOut:
    agent = resolve_dev_advisor(definitions, ctx.org_id, key)
    inputs: list[LearningInput] = []
    for i, row in enumerate(body.rows):
        sha = learning_row_sha(row.data, row.texto)
        if row.row_sha is not None and row.row_sha != sha:
            raise http_error(422, "row_sha_mismatch", f"rows[{i}].row_sha não corresponde a (data, texto).")
        inputs.append(LearningInput(
            data=row.data, tipo=row.tipo, texto=row.texto, evidencia=row.evidencia, row_status=row.status,
        ))
    with store_errors():
        inserted, duplicates = packages.insert_learnings(ctx.org_id, agent.id, body.project_slug, inputs)
    return LearningsPushOut(
        recebidas=len(inputs), novas=len(inserted), duplicadas=duplicates,
        novos=[LearningNewOut(id=r.id, row_sha=r.row_sha) for r in inserted],
    )


@router.get("/{key}/learnings", response_model=LearningListOut)
async def list_learnings(
    key: str,
    project: Annotated[str | None, Query(max_length=PROJECT_SLUG_MAX)] = None,
    status: Annotated[str | None, Query(pattern=r"^(novo|aceito|descartado|promovido)$")] = None,
    ctx: AuthContext = Depends(require_learnings_read),
    definitions=Depends(get_studio_definition_store_dep),
    packages=Depends(get_agent_package_store_dep),
) -> LearningListOut:
    agent = resolve_dev_advisor(definitions, ctx.org_id, key)
    rows = packages.list_learnings(ctx.org_id, agent.id, project_slug=project, status=status)
    return LearningListOut(items=[_learning_out(r) for r in rows])


@router.patch("/{key}/learnings/{learning_id}", response_model=LearningOut)
async def review_learning(
    key: str,
    learning_id: UUID,
    body: LearningReviewIn,
    ctx: AuthContext = Depends(require_admin),
    definitions=Depends(get_studio_definition_store_dep),
    packages=Depends(get_agent_package_store_dep),
) -> LearningOut:
    agent = resolve_dev_advisor(definitions, ctx.org_id, key)
    try:
        with store_errors():
            rec = packages.review_learning(
                ctx.org_id, agent.id, learning_id, status=body.status, note=body.nota, reviewer=ctx.user_id,
            )
    except NotFound as exc:
        raise http_error(404, "learning_not_found", "Aprendizado não encontrado.") from exc
    return _learning_out(rec)


__all__ = ["router", "SOURCES_BODY_LIMIT_PATTERN", "get_agent_package_store_dep"]
