"""`pipeline_board_router(cfg, ...)` — the funnel board + card routes.

A factory (like `pipeline_stages_router`) because the seed cannot know the
product's auth dependency, its client accessor or its audit sink. Routes, under
whatever prefix `mount_funnel` gives (`P`):

    GET   P/meta                       what the UI renders from (roles, reasons, gates, actions)
    GET   P/board                      PipelineColumn<Card>[]
    GET   P/board/orfaos               open cards the board cannot place
    POST  P/cards                      create (201) + entry movimento
    GET   P/cards/{id}  PATCH P/cards/{id}
    POST  P/cards/{id}/mover-etapa     gated; one movimento on a real stage change
    POST  P/cards/{id}/perder | reabrir | arquivar
    POST  P/cards/{id}/acoes/{codigo}  product action
    GET   P/cards/{id}/movimentos      keyset-paged history

Every write is audit-logged; every refusal happens before the first write.
Handlers are sync `def` on purpose: the supabase client is blocking, and a
sync handler runs in the threadpool instead of stalling the event loop.

ACCESS TIER: the router is created with `make_router(tier=cfg.tenancy, guard=
auth_dependency)` — a platform-tenancy funnel is a `platform` router, an org
funnel an `org` one — so the tier is declared and the guard is inherited by
every route added later. The product's `auth_dependency` must actually enforce
that tier (platform admin for `platform`).
"""
from __future__ import annotations

from typing import Any, Callable, Literal, Optional

from fastapi import Depends, Query

from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.domain.pipeline.router import PipelineContext

from . import service as svc
from .config import FunnelConfig
from .schemas import ActionBody, CardCreate, CardUpdate, MoverEtapa, Perder


def pipeline_board_router(
    cfg: FunnelConfig,
    *,
    auth_dependency: Callable[..., Any],
    resolve_context: Callable[[Any], PipelineContext],
    success_response: Callable[[Any], Any],
    log_action: Callable[..., Any] | None = None,
    require_card_write: Callable[..., Any] | None = None,
    prefix: str = "",
    tags: list[str] | None = None,
):
    """Build the board/card router for one funnel.

    `require_card_write` gates every WRITE route (create / edit / move / lose /
    reopen / archive / action); reads stay open to anyone passing
    `auth_dependency`. The dependency raises (e.g. 403) to refuse. Omitted =>
    every authenticated caller may write.
    """
    router = make_router(tier=cfg.tenancy, guard=auth_dependency, prefix=prefix, tags=tags or ["funnel"])
    write = [Depends(require_card_write)] if require_card_write else []
    pcfg = cfg.pipeline

    def ctx_of(auth: Any) -> PipelineContext:
        return svc.scope(cfg, resolve_context(auth))

    def audit(ctx: PipelineContext, action: str, card_id: Any, text: str, meta: dict | None = None) -> None:
        if log_action:
            log_action(ctx.user_id, action, pcfg.entity_kind, str(card_id), text, {"pipeline": pcfg.pipeline, **(meta or {})})

    def one(row: dict) -> dict:
        dto = svc.card_dto(cfg, row)
        svc.attach_owner_names(cfg, [dto])
        return dto

    @router.get("/meta")
    def obter_meta(auth=Depends(auth_dependency)):
        ctx_of(auth)  # a tenant-less session is refused even for static metadata
        return success_response(svc.meta(cfg))

    @router.get("/board")
    def obter_board(
        busca: Optional[str] = Query(None),
        limite_por_etapa: int = Query(svc.LIMITE_CARDS_PADRAO, ge=1, le=1000),
        responsavel_id: Optional[str] = Query(None),
        status: Literal["aberto", "ganho", "perdido", "arquivado", "todos"] = Query("aberto"),
        auth=Depends(auth_dependency),
    ):
        ctx = ctx_of(auth)
        return success_response(
            svc.board(
                ctx.db, cfg, ctx.org_id, busca=busca, limite_por_etapa=limite_por_etapa,
                responsavel_id=responsavel_id, status=status,
            )
        )

    @router.get("/board/orfaos")
    def obter_orfaos(auth=Depends(auth_dependency)):
        ctx = ctx_of(auth)
        return success_response(svc.orphans(ctx.db, cfg, ctx.org_id))

    @router.post("/cards", status_code=201, dependencies=write)
    def criar_card(body: CardCreate, auth=Depends(auth_dependency)):
        ctx = ctx_of(auth)
        row = svc.create_card(ctx.db, cfg, ctx, body.model_dump())
        audit(ctx, "criar", row["id"], f"Criou {pcfg.entity_label} '{body.titulo}'", {"etapa_id": row.get("etapa_id")})
        return success_response(one(row))

    @router.get("/cards/{card_id}")
    def obter_card(card_id: str, auth=Depends(auth_dependency)):
        ctx = ctx_of(auth)
        return success_response(one(svc.get_card_row(ctx.db, cfg, ctx.org_id, card_id)))

    @router.patch("/cards/{card_id}", dependencies=write)
    def editar_card(card_id: str, body: CardUpdate, auth=Depends(auth_dependency)):
        ctx = ctx_of(auth)
        row, changed = svc.update_card(ctx.db, cfg, ctx, card_id, body.model_dump(exclude_unset=True))
        if changed:
            audit(ctx, "editar", card_id, f"Editou {pcfg.entity_label}", {"campos": changed})
        return success_response(one(row))

    @router.post("/cards/{card_id}/mover-etapa", dependencies=write)
    def mover_etapa(card_id: str, body: MoverEtapa, auth=Depends(auth_dependency)):
        ctx = ctx_of(auth)
        row, changed_stage = svc.move(ctx.db, cfg, ctx, card_id, body.model_dump())
        audit(
            ctx, "mover" if changed_stage else "reordenar", card_id,
            f"{'Moveu' if changed_stage else 'Reordenou'} {pcfg.entity_label}",
            {"para_etapa_id": body.para_etapa_id, "novo_indice": body.novo_indice, "motivo": body.motivo},
        )
        return success_response(one(row))

    @router.post("/cards/{card_id}/perder", dependencies=write)
    def perder(card_id: str, body: Perder, auth=Depends(auth_dependency)):
        ctx = ctx_of(auth)
        row = svc.lose_card(ctx.db, cfg, ctx, card_id, body.model_dump())
        audit(ctx, "perder", card_id, f"Marcou {pcfg.entity_label} como perdido", {"motivo_codigo": body.motivo_codigo})
        return success_response(one(row))

    @router.post("/cards/{card_id}/reabrir", dependencies=write)
    def reabrir(card_id: str, auth=Depends(auth_dependency)):
        ctx = ctx_of(auth)
        row, changed = svc.reopen_card(ctx.db, cfg, ctx, card_id)
        if changed:
            audit(ctx, "reabrir", card_id, f"Reabriu {pcfg.entity_label}")
        return success_response(one(row))

    @router.post("/cards/{card_id}/arquivar", dependencies=write)
    def arquivar(card_id: str, auth=Depends(auth_dependency)):
        ctx = ctx_of(auth)
        row = svc.archive_card(ctx.db, cfg, ctx, card_id)
        audit(ctx, "arquivar", card_id, f"Arquivou {pcfg.entity_label}")
        return success_response(one(row))

    @router.post("/cards/{card_id}/acoes/{codigo}", dependencies=write)
    def executar_acao(card_id: str, codigo: str, body: ActionBody, auth=Depends(auth_dependency)):
        ctx = ctx_of(auth)
        row, efeitos = svc.run_action(ctx.db, cfg, ctx, card_id, codigo, body.payload)
        audit(ctx, "acao", card_id, f"Executou a ação '{codigo}'", {"acao": codigo})
        return success_response({"card": one(row), "efeitos": efeitos})

    @router.get("/cards/{card_id}/movimentos")
    def listar_movimentos(
        card_id: str,
        cursor: Optional[str] = Query(None),
        limite: int = Query(50, ge=1, le=200),
        auth=Depends(auth_dependency),
    ):
        ctx = ctx_of(auth)
        return success_response(svc.list_movimentos(ctx.db, cfg, ctx.org_id, card_id, cursor=cursor, limit=limite))

    return router


__all__ = ["pipeline_board_router"]
