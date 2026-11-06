"""Agent turn metrics for NoctusAI platform admins (``agents.turn_metrics``, migration 066) -- cost, speed, size.

Contract: ``products/agents/projects/julia-v2/CONTRACT.md`` section 14. Platform admin ONLY (``require_platform_admin``:
401 without credentials, 403 for any tenant member or product token). These figures are shown ONLY in the agents app;
no other product reads this router. Aggregates are computed in the app over the window's rows (capped, ``truncado``).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_turn_metrics_store_dep, require_platform_admin
from app.routers.studio_agents_router import get_studio_definition_store_dep, resolve_agent
from app.stores.turn_metrics import LIMITE_LINHAS
from app.studio import metricas as agg
from noctusai_lib.api.auth.session import AuthContext

router = APIRouter(prefix="/api/studio", tags=["studio-metricas"])

JANELA_PADRAO_DIAS = 7
ORIGENS = "^(canal|eval|todos)$"


def _janela(desde: datetime | None, ate: datetime | None) -> tuple[datetime, datetime]:
    fim = ate or datetime.now(timezone.utc)
    ini = desde or (fim - timedelta(days=JANELA_PADRAO_DIAS))
    return (ini if ini.tzinfo else ini.replace(tzinfo=timezone.utc)), (fim if fim.tzinfo else fim.replace(tzinfo=timezone.utc))


def _ler(store, key: str, desde, ate, org_id, origem: str, thread_id=None) -> tuple[list[dict[str, Any]], bool]:
    rows = store.listar(
        key, desde=desde, ate=ate, org_id=org_id, origem=None if origem == "todos" else origem, thread_id=thread_id)
    return rows, len(rows) >= LIMITE_LINHAS


def _cabecalho(key, desde, ate, origem, org_id, truncado) -> dict[str, Any]:
    return {
        "agent_key": key, "janela": {"desde": desde.isoformat(), "ate": ate.isoformat()}, "origem": origem,
        "org_id": str(org_id) if org_id else None, "truncado": truncado,
    }


@router.get("/agents/{key}/metricas")
def metricas_resumo(
    key: str, desde: datetime | None = None, ate: datetime | None = None, org_id: UUID | None = None,
    origem: str = Query("canal", pattern=ORIGENS),
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep), metricas=Depends(get_turn_metrics_store_dep),
) -> dict[str, Any]:
    resolve_agent(store, ctx.org_id, key, studio_only=False, allow_instancia=True)
    ini, fim = _janela(desde, ate)
    rows, truncado = _ler(metricas, key, ini, fim, org_id, origem)
    return {
        **_cabecalho(key, ini, fim, origem, org_id, truncado),
        "resumo": agg.resumir(rows),
        "serie_diaria": agg.serie_diaria(rows),
        "por_versao": agg.por_chave(rows, lambda r: r.get("compiled_hash"), "compiled_hash"),
        "por_org": agg.por_chave(rows, lambda r: str(r["org_id"]), "org_id"),
    }


@router.get("/agents/{key}/metricas/turnos")
def metricas_turnos(
    key: str, desde: datetime | None = None, ate: datetime | None = None, org_id: UUID | None = None,
    origem: str = Query("canal", pattern=ORIGENS), limite: int = Query(50, ge=1, le=200), pagina: int = Query(1, ge=1),
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep), metricas=Depends(get_turn_metrics_store_dep),
) -> dict[str, Any]:
    resolve_agent(store, ctx.org_id, key, studio_only=False, allow_instancia=True)
    ini, fim = _janela(desde, ate)
    rows, truncado = _ler(metricas, key, ini, fim, org_id, origem)
    pagina_rows = rows[(pagina - 1) * limite: pagina * limite]
    return {
        **_cabecalho(key, ini, fim, origem, org_id, truncado),
        "total": len(rows), "pagina": pagina, "limite": limite, "itens": [agg.turno_publico(r) for r in pagina_rows],
    }


@router.get("/agents/{key}/metricas/threads")
def metricas_threads(
    key: str, desde: datetime | None = None, ate: datetime | None = None, org_id: UUID | None = None,
    origem: str = Query("canal", pattern=ORIGENS), limite: int = Query(50, ge=1, le=200),
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep), metricas=Depends(get_turn_metrics_store_dep),
) -> dict[str, Any]:
    resolve_agent(store, ctx.org_id, key, studio_only=False, allow_instancia=True)
    ini, fim = _janela(desde, ate)
    rows, truncado = _ler(metricas, key, ini, fim, org_id, origem)
    threads = agg.por_chave([r for r in rows if r.get("thread_id")], lambda r: r["thread_id"], "thread_id")
    return {**_cabecalho(key, ini, fim, origem, org_id, truncado), "total": len(threads), "itens": threads[:limite]}


@router.get("/agents/{key}/metricas/threads/{thread_id}")
def metricas_thread(
    key: str, thread_id: UUID, origem: str = Query("todos", pattern=ORIGENS),
    ctx: AuthContext = Depends(require_platform_admin),
    store=Depends(get_studio_definition_store_dep), metricas=Depends(get_turn_metrics_store_dep),
) -> dict[str, Any]:
    resolve_agent(store, ctx.org_id, key, studio_only=False, allow_instancia=True)
    rows, truncado = _ler(metricas, key, None, None, None, origem, thread_id=thread_id)
    rows = sorted(rows, key=lambda r: r["created_at"])
    return {
        "agent_key": key, "thread_id": str(thread_id), "origem": origem, "truncado": truncado,
        "resumo": agg.resumir(rows), "turnos": [agg.turno_publico(r) for r in rows],
    }
