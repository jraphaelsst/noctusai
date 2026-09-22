"""``POST /api/studio/agents/{key}/import`` — the agent bundle importer
(Agent Studio contract §D5, §F, §H7; slice BE-RT).

Admin-only, strictly validated (``AgentBundle``: ``extra="forbid"`` at every
level — an unknown key is a 422 naming its JSON path), size-capped at
``MAX_BUNDLE_BYTES`` (25 MB) for THIS route only — ``app.main`` registers the
exact ``/api/studio/agents/*/import`` wildcard pattern in
``max_body_path_overrides`` (a whole-segment wildcard, never a prefix, so no
sibling route inherits the raised cap). Never publishes. ``?dry_run=true``
returns the plan with zero writes.

Errors: store ``StudioConflict`` codes map to 409 through ``store_errors``
(notably ``slug_in_other_collection`` — an import never moves a document
between collections), ``ValueError`` to 422 ``invalid_field``.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.dependencies import require_admin
from app.routers.studio_agents_router import (
    get_knowledge_catalog_dep,
    get_studio_definition_store_dep,
    store_errors,
)
from app.routers.studio_evals_router import get_eval_store_dep
from app.routers.studio_knowledge_router import get_studio_knowledge_store_dep
from app.studio.importer import AgentBundle, ImportRefused, import_bundle
from noctusai_lib.api.auth.session import AuthContext

router = APIRouter(prefix="/api/studio/agents", tags=["studio-import"])

#: The body-cap pattern ``app.main`` registers (whole-segment wildcard).
IMPORT_BODY_LIMIT_PATTERN = "/api/studio/agents/*/import"


class ImportAgenteOut(BaseModel):
    criado: bool


class ImportRascunhoOut(BaseModel):
    version_id: UUID | None
    secoes: int
    skills: int
    arquivos: int


class ImportConhecimentoOut(BaseModel):
    colecoes_criadas: int
    documentos_criados: int
    documentos_atualizados: int
    documentos_inalterados: int


class ImportEvalsOut(BaseModel):
    criados: int
    atualizados: int


class ImportClientesOut(BaseModel):
    criados: int


class ImportSummaryOut(BaseModel):
    dry_run: bool
    agente: ImportAgenteOut
    rascunho: ImportRascunhoOut
    conhecimento: ImportConhecimentoOut
    evals: ImportEvalsOut
    clientes: ImportClientesOut
    avisos: list[str]


@router.post("/{key}/import", response_model=ImportSummaryOut)
async def import_agent_bundle(
    key: str,
    bundle: AgentBundle,
    dry_run: bool = Query(default=False),
    ctx: AuthContext = Depends(require_admin),
    definitions=Depends(get_studio_definition_store_dep),
    knowledge=Depends(get_studio_knowledge_store_dep),
    evals=Depends(get_eval_store_dep),
    catalog=Depends(get_knowledge_catalog_dep),
) -> ImportSummaryOut:
    try:
        with store_errors():
            summary = import_bundle(
                bundle,
                org_id=ctx.org_id,
                key=key,
                user_id=ctx.user_id,
                dry_run=dry_run,
                definitions=definitions,
                knowledge=knowledge,
                evals=evals,
                catalog=catalog,
            )
    except ImportRefused as exc:
        raise HTTPException(
            status_code=exc.status, detail={"detail": exc.detail, "code": exc.code}
        ) from exc
    return ImportSummaryOut(**summary)


__all__ = ["router", "IMPORT_BODY_LIMIT_PATTERN"]
