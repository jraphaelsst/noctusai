"""Bulk import of the imóveis' YouTube videos FROM Vista into `imovel_video_youtube` (project `julia-videos-prontos-youtube`, S3).

  POST /api/imoveis/videos-youtube/importar-vista            {dry_run=true, codigos?, limite?, org_id?} -> 202 {execucao_id, status,
                                                              ja_em_andamento}; the run goes on in the background
  GET  /api/imoveis/videos-youtube/importar-vista/{id}       ?resultados=a,b&limit=&offset= -> the run: status, contagens, per-code rows
                                                              (default filter = the actionable results; resultados=todos = every row)
  GET  /api/imoveis/videos-youtube/importar-vista            the latest runs (summary only)

Access tier: PLATFORM (a bulk write over a whole org's catalog; `require_platform_admin`): strict 401 without a session, 403 for
anyone who is not a NoctusAI platform admin. `org_id` defaults to the caller's org. `dry_run` defaults to TRUE and makes zero writes;
a real run writes only `origem='vista'` rows and never touches Vista. The org's Vista adapter comes from its own CredentialStore record
(`vista_credenciais`): an org without one is a 503 before anything starts. Rules + counts: `imovel_videos_vista_import_service`.
"""
# No `from __future__ import annotations`: FastAPI body models are resolved from the signature.
import asyncio
from typing import Any, Callable, Optional
from uuid import UUID

import anyio
from fastapi import Depends, Query
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.primitives.exceptions import AppException

from app.dependencies import coerce_org_uuid, get_admin_client, require_platform_admin
from app.modules.imovel_hub.deps import get_imovel_hub_client
from app.services import imovel_videos_vista_import_service as imp
from app.services import sync_lease, vista_credenciais

router = make_router(
    tier="platform", guard=require_platform_admin, prefix="/api/imoveis/videos-youtube/importar-vista",
    tags=["imoveis-video-youtube-importacao"],
)

#: Strong references to the in-flight runs (the loop only keeps a weak one).
_TAREFAS: set = set()


def get_import_vista_provider() -> Callable[[Any], Any]:
    """DI seam: org_id -> the org's Vista adapter, a 503 without a credential (tests return a FakeVistaAdapter)."""
    return vista_credenciais.adapter_ou_503


def get_import_lease() -> Callable[..., Any]:
    """DI seam: the cross-process lease (`sync_lease.lease`; tests pass an always-granted one)."""
    return sync_lease.lease


def get_import_agendador() -> Callable[[Any], None]:
    """DI seam: how the run is put in the background (a task on the running loop; tests keep the coroutine and drive it)."""
    def agendar(coro: Any) -> None:
        tarefa = asyncio.get_running_loop().create_task(coro)
        _TAREFAS.add(tarefa)
        tarefa.add_done_callback(_TAREFAS.discard)

    return agendar


class ImportarIn(StrictHttpModel):
    dry_run: bool = True
    codigos: Optional[list[str]] = Field(default=None, max_length=5000)
    limite: Optional[int] = Field(default=None, ge=1, le=100_000)
    org_id: Optional[UUID] = None


def _uid(auth: tuple) -> Optional[str]:
    user = auth[0]
    uid = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
    return str(uid) if uid else None


def _execucao_out(ex: imp.Execucao, **extra: Any) -> dict[str, Any]:
    return {"execucao_id": ex.id, "status": ex.relatorio.status, "dry_run": ex.relatorio.dry_run, **extra}


@router.post("", status_code=202)
async def importar(
    corpo: ImportarIn, auth: tuple = Depends(require_platform_admin), client: Any = Depends(get_imovel_hub_client),
    admin: Any = Depends(get_admin_client), vista_provider: Callable[[Any], Any] = Depends(get_import_vista_provider),
    lease_fn: Callable[..., Any] = Depends(get_import_lease), agendar: Callable[[Any], None] = Depends(get_import_agendador),
) -> dict[str, Any]:
    org_id = str(corpo.org_id or coerce_org_uuid(auth[2]))
    adapter = await anyio.to_thread.run_sync(lambda: vista_provider(org_id))  # 503 before anything is queued
    ex, nova = imp.EXECUCOES.iniciar(org_id, dry_run=corpo.dry_run, codigos=corpo.codigos, limite=corpo.limite, iniciado_por=_uid(auth))
    if nova:
        agendar(imp.executar(ex, client=client, admin=admin, adapter=adapter, lease_fn=lease_fn))
    return {"data": _execucao_out(ex, org_id=org_id, ja_em_andamento=not nova)}


@router.get("/{execucao_id}")
def obter(
    execucao_id: UUID, resultados: Optional[str] = Query(None, max_length=300), limit: int = Query(200, ge=1, le=5000),
    offset: int = Query(0, ge=0, le=100_000), auth: tuple = Depends(require_platform_admin),
) -> dict[str, Any]:
    ex = imp.EXECUCOES.obter(str(execucao_id))
    if ex is None:
        raise AppException("execucao_nao_encontrada", "Execução não encontrada (as execuções ficam na memória do processo).", status_code=404)
    filtro: Optional[tuple[str, ...]]
    if resultados == "todos":
        filtro = None
    elif resultados:
        filtro = tuple(r.strip() for r in resultados.split(",") if r.strip())
    else:
        filtro = imp.RESULTADOS_ACIONAVEIS
    return {"data": {"execucao_id": ex.id, **ex.relatorio.as_dict(resultados=filtro, limit=limit, offset=offset)}}


@router.get("")
def listar(auth: tuple = Depends(require_platform_admin)) -> dict[str, Any]:
    return {"data": [{"execucao_id": ex.id, **ex.relatorio.resumo()} for ex in imp.EXECUCOES.listar()]}


__all__ = ["router", "get_import_agendador", "get_import_lease", "get_import_vista_provider"]
