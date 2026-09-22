"""`card_hub_routers(cfg, ...)` — the card-hub HTTP surface, mountable.

A factory (like `noctusai_lib.domain.pipeline.pipeline_stages_router`)
because the seed cannot know the product's auth dependency, its database
accessor, or its storage accessor. All three arrive as FastAPI DEPENDENCIES
(`auth_dependency`, `get_db`, `get_storage`), so a product keeps its own DI
seams — and its tests keep overriding them with
`app.dependency_overrides[...]` exactly as before.

🔴 TWO ROUTERS, AND THE ORDER THEY MOUNT IN MATTERS
---------------------------------------------------
`collection_router` carries the literal paths (`/tags`, `/tags/{tag_id}`,
`/documentos/tipos`); `entity_router` carries every `/{<id_param>}/...` path.
`GET /tags` has the same SHAPE as a product's own bare `GET /{id}` (Starlette
matches by path shape; a plain `str` converter has no UUID regex), so the
product must mount `collection_router` BEFORE any router that declares a bare
`/{id}` under the same prefix. Returning them separately is what lets it.

🔴 NEVER `get_admin_client().schema(...)` IN HERE
-------------------------------------------------
The `db` a handler uses is whatever the product's `get_db` dependency
returns — already schema-scoped, and cached by the product. Re-deriving a
schema client inside a seed factory poisons a shared admin client for every
cross-schema caller (the `62f82ba47` fix).

Routes (under `prefix`, `{id}` = `cfg.id_param`):
    GET                 /tags                           (collection)
    POST                /tags                           201
    PATCH / DELETE      /tags/{tag_id}                  DELETE 204
    GET                 /documentos/tipos
    GET                 /{id}/timeline?cursor&limit(1-200)&kinds=csv
    POST                /{id}/notas                     201
    PATCH / DELETE      /{id}/notas/{nota_id}           DELETE 204
    PUT                 /{id}/tags
    GET / PUT           /{id}/membros
    GET / POST          /{id}/checklist-extras          POST 201
    PATCH / DELETE      /{id}/checklist-extras/{eid}    DELETE 204
    POST / DELETE       /{id}/checklist-extras/{eid}/documento   DELETE 204
    GET / POST          /{id}/checklists                POST 201
    PATCH / DELETE      /{id}/checklists/{cid}          DELETE 204
    POST                /{id}/checklists/{cid}/itens    201
    PATCH / DELETE      /{id}/checklists/{cid}/itens/{iid}       DELETE 204
    GET / POST          /{id}/documentos                POST 201
    GET                 /{id}/documentos/{did}/url?intent=view|download
    DELETE              /{id}/documentos/{did}?motivo=  204 (motivo REQUIRED)
    GET                 /{id}/documentos/{did}/acessos
    GET                 /{id}/card

Route NAMES (hence OpenAPI operation ids) and body-schema names are the
lifted social-wiring ones, with the entity substituted where the original
carried it — so a product adopting the factory keeps its OpenAPI document.

Envelope: list responses `{"items": [...], "total": n}`; errors through the
seed's `AppException` handlers (`{"error": {"code", "message", ...}}`).
"""
from typing import Any, Callable, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Query,
    UploadFile,
)

from . import badges as badges_svc
from . import checklist_extras as extras_svc
from . import documentos as docs_svc
from . import services as svc
from . import timeline as timeline_svc
from .config import CardHubConfig, CardHubContext
from .schemas import (
    ChecklistCreateBody,
    ChecklistExtraCreateBody,
    ChecklistExtraPatchBody,
    ChecklistItemCreateBody,
    ChecklistItemUpdateBody,
    ChecklistUpdateBody,
    NotaCreateBody,
    NotaUpdateBody,
    TagCreateBody,
    TagUpdateBody,
    entity_tags_body,
    membros_body,
)

#: `(background, ctx, storage, entity_id, documento, tipo_documento) -> None`
#: — what a product's upload hook dependency RETURNS (e.g. queue an
#: identity-extraction background task for an identity-class upload).
DocumentoUploadHook = Callable[[BackgroundTasks, CardHubContext, Any, UUID, dict, str], None]


def _no_upload_hook() -> None:
    return None


def card_hub_routers(
    cfg: CardHubConfig,
    *,
    auth_dependency: Callable[..., Any],
    resolve_context: Callable[[Any, Any], CardHubContext],
    get_db: Callable[..., Any],
    get_storage: Callable[..., Any],
    prefix: str = "",
    tags: Optional[list[str]] = None,
    documento_upload_hook: Optional[Callable[..., Optional[DocumentoUploadHook]]] = None,
) -> tuple[APIRouter, APIRouter]:
    """Build `(collection_router, entity_router)` for one card hub.

    Args:
        cfg: The card hub.
        auth_dependency: The product's FastAPI auth dependency (whatever it
            returns; it is where the 401 comes from).
        resolve_context: `(auth_value, db) -> CardHubContext` — maps the
            product's auth shape + db to the triple every handler uses.
        get_db: FastAPI dependency returning the schema-scoped PostgREST
            client.
        get_storage: FastAPI dependency returning a `StorageBackend`.
        prefix: Router prefix (`"/api/clientes"`).
        tags: OpenAPI tags (default `["card_hub"]`).
        documento_upload_hook: Optional FastAPI dependency returning a
            `DocumentoUploadHook` (or `None`), run after a successful
            `POST /{id}/documentos`. A dependency — not a plain callable — so
            the product's own collaborators stay DI-overridable in tests.
    """
    id_param = cfg.id_param
    route_tags = tags or ["card_hub"]
    collection_router = APIRouter(prefix=prefix, tags=route_tags)
    entity_router = APIRouter(prefix=prefix, tags=route_tags)
    EntityTagsBody = entity_tags_body(cfg)
    MembrosBody = membros_body(cfg)
    member_key = cfg.member_source.body_key
    upload_hook_dep = documento_upload_hook or _no_upload_hook

    def entity_path(suffix: str = "") -> str:
        return f"/{{{id_param}}}{suffix}"

    def entity_id_param() -> Any:
        return Path(..., alias=id_param)

    # ─── Tags (org catalogue — literal paths) ──────────────────────────

    @collection_router.get("/tags", name="list_tags_route")
    async def list_tags_route(auth=Depends(auth_dependency), db=Depends(get_db)) -> dict:
        ctx = resolve_context(auth, db)
        return svc.list_tags(cfg, ctx.db, ctx.org_id)

    @collection_router.post("/tags", status_code=201, name="create_tag_route")
    async def create_tag_route(
        body: TagCreateBody, auth=Depends(auth_dependency), db=Depends(get_db)
    ) -> dict:
        ctx = resolve_context(auth, db)
        return svc.create_tag(cfg, ctx.db, ctx.org_id, nome=body.nome, cor=body.cor)

    @collection_router.patch("/tags/{tag_id}", name="update_tag_route")
    async def update_tag_route(
        tag_id: UUID, body: TagUpdateBody, auth=Depends(auth_dependency), db=Depends(get_db)
    ) -> dict:
        ctx = resolve_context(auth, db)
        return svc.update_tag(cfg, ctx.db, ctx.org_id, tag_id, nome=body.nome, cor=body.cor)

    @collection_router.delete("/tags/{tag_id}", status_code=204, name="delete_tag_route")
    async def delete_tag_route(tag_id: UUID, auth=Depends(auth_dependency), db=Depends(get_db)):
        ctx = resolve_context(auth, db)
        svc.delete_tag(cfg, ctx.db, ctx.org_id, tag_id)

    # ─── Documentos tipos catalogue (literal path) ─────────────────────

    @collection_router.get("/documentos/tipos", name="list_tipos_documento_route")
    async def list_tipos_documento_route(auth=Depends(auth_dependency), db=Depends(get_db)) -> dict:
        ctx = resolve_context(auth, db)
        return docs_svc.list_tipos_documento(cfg, ctx.db)

    # ─── Timeline ──────────────────────────────────────────────────────

    @entity_router.get(entity_path("/timeline"), name="get_timeline_route")
    async def get_timeline_route(
        entity_id: UUID = entity_id_param(),
        cursor: Optional[str] = Query(None),
        limit: int = Query(50, ge=1, le=200),
        kinds: Optional[str] = Query(None),
        auth=Depends(auth_dependency),
        db=Depends(get_db),
    ) -> dict:
        ctx = resolve_context(auth, db)
        kind_set = {k.strip() for k in kinds.split(",") if k.strip()} if kinds else None
        return timeline_svc.get_timeline(
            cfg, ctx.db, ctx.org_id, entity_id, kinds=kind_set, cursor=cursor, limit=limit
        )

    # ─── Notas ─────────────────────────────────────────────────────────

    @entity_router.post(entity_path("/notas"), status_code=201, name="create_nota_route")
    async def create_nota_route(
        entity_id: UUID = entity_id_param(),
        body: NotaCreateBody = Body(...),
        auth=Depends(auth_dependency),
        db=Depends(get_db),
    ) -> dict:
        ctx = resolve_context(auth, db)
        return svc.create_nota(
            cfg, ctx.db, ctx.org_id, entity_id, corpo=body.corpo, tipo=body.tipo, autor_id=ctx.user_id
        )

    @entity_router.patch(entity_path("/notas/{nota_id}"), name="update_nota_route")
    async def update_nota_route(
        entity_id: UUID = entity_id_param(),
        nota_id: UUID = Path(...),
        body: NotaUpdateBody = Body(...),
        auth=Depends(auth_dependency),
        db=Depends(get_db),
    ) -> dict:
        ctx = resolve_context(auth, db)
        return svc.update_nota(cfg, ctx.db, ctx.org_id, entity_id, nota_id, corpo=body.corpo)

    @entity_router.delete(entity_path("/notas/{nota_id}"), status_code=204, name="delete_nota_route")
    async def delete_nota_route(
        entity_id: UUID = entity_id_param(),
        nota_id: UUID = Path(...),
        auth=Depends(auth_dependency),
        db=Depends(get_db),
    ):
        ctx = resolve_context(auth, db)
        svc.delete_nota(cfg, ctx.db, ctx.org_id, entity_id, nota_id)

    # ─── Entity <-> tags ───────────────────────────────────────────────

    @entity_router.put(entity_path("/tags"), name=f"set_{cfg.entity_kind}_tags_route")
    async def set_entity_tags_route(
        entity_id: UUID = entity_id_param(),  # type: ignore[valid-type]
        body: EntityTagsBody = Body(...),
        auth=Depends(auth_dependency),
        db=Depends(get_db),
    ) -> dict:
        ctx = resolve_context(auth, db)
        return svc.set_entity_tags(
            cfg, ctx.db, ctx.org_id, entity_id, tag_ids=body.tag_ids, criado_por=ctx.user_id
        )

    # ─── Membros ───────────────────────────────────────────────────────

    @entity_router.get(entity_path("/membros"), name="get_membros_route")
    async def get_membros_route(
        entity_id: UUID = entity_id_param(), auth=Depends(auth_dependency), db=Depends(get_db)
    ) -> dict:
        ctx = resolve_context(auth, db)
        return svc.get_membros(cfg, ctx.db, ctx.org_id, entity_id)

    @entity_router.put(entity_path("/membros"), name="set_membros_route")
    async def set_membros_route(
        entity_id: UUID = entity_id_param(),  # type: ignore[valid-type]
        body: MembrosBody = Body(...),
        auth=Depends(auth_dependency),
        db=Depends(get_db),
    ) -> dict:
        ctx = resolve_context(auth, db)
        return svc.set_membros(cfg, ctx.db, ctx.org_id, entity_id, member_ids=getattr(body, member_key))

    # ─── Checklist extras (operator-authored lines) ────────────────────

    @entity_router.get(entity_path("/checklist-extras"), name="list_checklist_extras_route")
    async def list_checklist_extras_route(
        entity_id: UUID = entity_id_param(), auth=Depends(auth_dependency), db=Depends(get_db)
    ) -> dict:
        ctx = resolve_context(auth, db)
        return extras_svc.listar(cfg, ctx.db, ctx.org_id, entity_id)

    @entity_router.post(
        entity_path("/checklist-extras"), status_code=201, name="create_checklist_extra_route"
    )
    async def create_checklist_extra_route(
        entity_id: UUID = entity_id_param(),
        body: ChecklistExtraCreateBody = Body(...),
        auth=Depends(auth_dependency),
        db=Depends(get_db),
    ) -> dict:
        ctx = resolve_context(auth, db)
        return extras_svc.criar(cfg, ctx.db, ctx.org_id, entity_id, label=body.label, tipo=body.tipo)

    @entity_router.patch(
        entity_path("/checklist-extras/{extra_id}"), name="patch_checklist_extra_route"
    )
    async def patch_checklist_extra_route(
        entity_id: UUID = entity_id_param(),
        extra_id: UUID = Path(...),
        body: ChecklistExtraPatchBody = Body(...),
        auth=Depends(auth_dependency),
        db=Depends(get_db),
    ) -> dict:
        ctx = resolve_context(auth, db)
        # `model_fields_set`, NOT `exclude_none`: absence is the only thing
        # that can mean "leave alone".
        enviados = {k: getattr(body, k) for k in body.model_fields_set}
        try:
            return extras_svc.atualizar(
                cfg,
                ctx.db,
                ctx.org_id,
                entity_id,
                extra_id,
                label=enviados.get("label", ...),
                valor_texto=enviados.get("valor_texto", ...),
                ordem=enviados.get("ordem", ...),
            )
        except extras_svc.TipoIncompativel as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @entity_router.delete(
        entity_path("/checklist-extras/{extra_id}"),
        status_code=204,
        name="delete_checklist_extra_route",
    )
    async def delete_checklist_extra_route(
        entity_id: UUID = entity_id_param(),
        extra_id: UUID = Path(...),
        auth=Depends(auth_dependency),
        db=Depends(get_db),
    ):
        ctx = resolve_context(auth, db)
        extras_svc.remover(cfg, ctx.db, ctx.org_id, entity_id, extra_id)

    @entity_router.post(
        entity_path("/checklist-extras/{extra_id}/documento"),
        name="upload_checklist_extra_documento_route",
    )
    async def upload_checklist_extra_documento_route(
        entity_id: UUID = entity_id_param(),
        extra_id: UUID = Path(...),
        file: UploadFile = File(...),
        auth=Depends(auth_dependency),
        db=Depends(get_db),
        storage=Depends(get_storage),
    ) -> dict:
        """Attach (or REPLACE) the file answering one `arquivo` line. No
        `tipo_documento` field: an operator-authored line is by definition
        the request the catalogue did not anticipate."""
        ctx = resolve_context(auth, db)
        data = await file.read()
        try:
            return await extras_svc.anexar_documento(
                cfg,
                ctx.db,
                storage,
                ctx.org_id,
                entity_id,
                extra_id,
                filename=file.filename or "arquivo",
                content_type=file.content_type or "application/octet-stream",
                data=data,
                enviado_por=ctx.user_id,
            )
        except extras_svc.TipoIncompativel as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @entity_router.delete(
        entity_path("/checklist-extras/{extra_id}/documento"),
        status_code=204,
        name="delete_checklist_extra_documento_route",
    )
    async def delete_checklist_extra_documento_route(
        entity_id: UUID = entity_id_param(),
        extra_id: UUID = Path(...),
        auth=Depends(auth_dependency),
        db=Depends(get_db),
        storage=Depends(get_storage),
    ):
        """Discard the FILE, keep the LINE. No `motivo` param: the reason is
        structural and always the same, so the service states it."""
        ctx = resolve_context(auth, db)
        await extras_svc.remover_documento(
            cfg, ctx.db, storage, ctx.org_id, entity_id, extra_id, usuario_id=ctx.user_id
        )

    # ─── Checklists ────────────────────────────────────────────────────

    @entity_router.get(entity_path("/checklists"), name="list_checklists_route")
    async def list_checklists_route(
        entity_id: UUID = entity_id_param(), auth=Depends(auth_dependency), db=Depends(get_db)
    ) -> dict:
        ctx = resolve_context(auth, db)
        return svc.list_checklists(cfg, ctx.db, ctx.org_id, entity_id)

    @entity_router.post(entity_path("/checklists"), status_code=201, name="create_checklist_route")
    async def create_checklist_route(
        entity_id: UUID = entity_id_param(),
        body: ChecklistCreateBody = Body(...),
        auth=Depends(auth_dependency),
        db=Depends(get_db),
    ) -> dict:
        ctx = resolve_context(auth, db)
        return svc.create_checklist(cfg, ctx.db, ctx.org_id, entity_id, titulo=body.titulo)

    @entity_router.patch(entity_path("/checklists/{checklist_id}"), name="update_checklist_route")
    async def update_checklist_route(
        entity_id: UUID = entity_id_param(),
        checklist_id: UUID = Path(...),
        body: ChecklistUpdateBody = Body(...),
        auth=Depends(auth_dependency),
        db=Depends(get_db),
    ) -> dict:
        ctx = resolve_context(auth, db)
        return svc.update_checklist(
            cfg, ctx.db, ctx.org_id, entity_id, checklist_id, titulo=body.titulo, posicao=body.posicao
        )

    @entity_router.delete(
        entity_path("/checklists/{checklist_id}"), status_code=204, name="delete_checklist_route"
    )
    async def delete_checklist_route(
        entity_id: UUID = entity_id_param(),
        checklist_id: UUID = Path(...),
        auth=Depends(auth_dependency),
        db=Depends(get_db),
    ):
        ctx = resolve_context(auth, db)
        svc.delete_checklist(cfg, ctx.db, ctx.org_id, entity_id, checklist_id)

    @entity_router.post(
        entity_path("/checklists/{checklist_id}/itens"),
        status_code=201,
        name="create_checklist_item_route",
    )
    async def create_checklist_item_route(
        entity_id: UUID = entity_id_param(),
        checklist_id: UUID = Path(...),
        body: ChecklistItemCreateBody = Body(...),
        auth=Depends(auth_dependency),
        db=Depends(get_db),
    ) -> dict:
        ctx = resolve_context(auth, db)
        return svc.create_checklist_item(cfg, ctx.db, ctx.org_id, entity_id, checklist_id, texto=body.texto)

    @entity_router.patch(
        entity_path("/checklists/{checklist_id}/itens/{item_id}"),
        name="update_checklist_item_route",
    )
    async def update_checklist_item_route(
        entity_id: UUID = entity_id_param(),
        checklist_id: UUID = Path(...),
        item_id: UUID = Path(...),
        body: ChecklistItemUpdateBody = Body(...),
        auth=Depends(auth_dependency),
        db=Depends(get_db),
    ) -> dict:
        ctx = resolve_context(auth, db)
        return svc.update_checklist_item(
            cfg,
            ctx.db,
            ctx.org_id,
            entity_id,
            checklist_id,
            item_id,
            texto=body.texto,
            concluido=body.concluido,
            posicao=body.posicao,
            concluido_por=ctx.user_id,
        )

    @entity_router.delete(
        entity_path("/checklists/{checklist_id}/itens/{item_id}"),
        status_code=204,
        name="delete_checklist_item_route",
    )
    async def delete_checklist_item_route(
        entity_id: UUID = entity_id_param(),
        checklist_id: UUID = Path(...),
        item_id: UUID = Path(...),
        auth=Depends(auth_dependency),
        db=Depends(get_db),
    ):
        ctx = resolve_context(auth, db)
        svc.delete_checklist_item(cfg, ctx.db, ctx.org_id, entity_id, checklist_id, item_id)

    # ─── Documentos (LGPD) ─────────────────────────────────────────────

    @entity_router.get(entity_path("/documentos"), name="list_documentos_route")
    async def list_documentos_route(
        entity_id: UUID = entity_id_param(), auth=Depends(auth_dependency), db=Depends(get_db)
    ) -> dict:
        ctx = resolve_context(auth, db)
        return docs_svc.list_documentos(cfg, ctx.db, ctx.org_id, entity_id)

    @entity_router.post(entity_path("/documentos"), status_code=201, name="upload_documento_route")
    async def upload_documento_route(
        background: BackgroundTasks,
        entity_id: UUID = entity_id_param(),
        file: UploadFile = File(...),
        tipo_documento: str = Form(...),
        auth=Depends(auth_dependency),
        db=Depends(get_db),
        storage=Depends(get_storage),
        upload_hook=Depends(upload_hook_dep),
    ) -> dict:
        ctx = resolve_context(auth, db)
        data = await file.read()
        documento = await docs_svc.upload_documento(
            cfg,
            ctx.db,
            storage,
            ctx.org_id,
            entity_id,
            filename=file.filename or "arquivo",
            content_type=file.content_type or "application/octet-stream",
            data=data,
            tipo_documento=tipo_documento,
            enviado_por=ctx.user_id,
        )
        if upload_hook is not None:
            upload_hook(background, ctx, storage, entity_id, documento, tipo_documento)
        return documento

    @entity_router.get(
        entity_path("/documentos/{documento_id}/url"), name="get_documento_url_route"
    )
    async def get_documento_url_route(
        entity_id: UUID = entity_id_param(),
        documento_id: UUID = Path(...),
        intent: str = Query("view", pattern="^(view|download)$"),
        auth=Depends(auth_dependency),
        db=Depends(get_db),
        storage=Depends(get_storage),
    ) -> dict:
        ctx = resolve_context(auth, db)
        return await docs_svc.get_documento_url(
            cfg, ctx.db, storage, ctx.org_id, entity_id, documento_id, usuario_id=ctx.user_id, intent=intent
        )

    @entity_router.delete(
        entity_path("/documentos/{documento_id}"), status_code=204, name="delete_documento_route"
    )
    async def delete_documento_route(
        entity_id: UUID = entity_id_param(),
        documento_id: UUID = Path(...),
        # A REQUIRED query param, not a body: DELETE-with-body is poorly
        # supported across the stack, and an LGPD delete without a recorded
        # reason is not an LGPD delete.
        motivo: str = Query(..., min_length=1),
        auth=Depends(auth_dependency),
        db=Depends(get_db),
        storage=Depends(get_storage),
    ):
        ctx = resolve_context(auth, db)
        await docs_svc.delete_documento(
            cfg, ctx.db, storage, ctx.org_id, entity_id, documento_id, motivo=motivo, usuario_id=ctx.user_id
        )

    @entity_router.get(
        entity_path("/documentos/{documento_id}/acessos"), name="list_acessos_route"
    )
    async def list_acessos_route(
        entity_id: UUID = entity_id_param(),
        documento_id: UUID = Path(...),
        auth=Depends(auth_dependency),
        db=Depends(get_db),
    ) -> dict:
        ctx = resolve_context(auth, db)
        return docs_svc.list_acessos(cfg, ctx.db, ctx.org_id, entity_id, documento_id)

    # ─── Card summary ──────────────────────────────────────────────────

    @entity_router.get(entity_path("/card"), name="get_card_route")
    async def get_card_route(
        entity_id: UUID = entity_id_param(), auth=Depends(auth_dependency), db=Depends(get_db)
    ) -> dict:
        ctx = resolve_context(auth, db)
        return badges_svc.get_card_resumo(cfg, ctx.db, ctx.org_id, entity_id)

    return collection_router, entity_router


__all__ = ["DocumentoUploadHook", "card_hub_routers"]
