"""Contracts HTTP surface -- `make_contracts_router(cfg, auth_dependency, admin_dependency, ...)` at `/api/contracts`.

Authorization (same split as finance / parties): org STAFF may read (`auth_dependency`); every write
additionally requires `admin_dependency` (the host's `require_org_admin(...)`). Unauthenticated is a
strict 401 (it lives in the host's auth dep). RLS is the floor: every service call is org-scoped.

Same factory shape as `make_parties_router`: the seed cannot know the product's auth or its
schema-scoped database accessor, so they arrive as FastAPI DEPENDENCIES; the seams arrive as
callables resolved PER REQUEST (never captured at import):

- `get_billing(db) -> ContractsBilling` -- where receivables go (`make_contracts_billing("supabase", ...)`);
- `get_signature(ctx) -> SignatureAdapter | None` -- optional e-signature (org-scoped credentials);
- `get_storage` -- optional FastAPI dependency returning a `StorageBackend` (attachments);
- `renderer` -- `DocumentRenderer` turning the contract text into the file sent for signature.

`POST /{id}/attachments` is an `UploadFile` route: list `ATTACHMENT_UPLOAD_PATH_PATTERN` in
`max_body_path_overrides` (`{ATTACHMENT_UPLOAD_PATH_PATTERN: ATTACHMENT_UPLOAD_MAX_BYTES}`).

🔴 NEVER `get_admin_client().schema(...)` in here: `get_db` already returns the product's schema-scoped client.
"""
from __future__ import annotations

from typing import Any, Callable, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile

from noctusai_lib.primitives.responses import paginated_response, success_response

from . import attachments as att_svc
from . import billing_run as billing_svc
from . import contracts as svc
from . import documents
from . import signature as sig_svc
from ._common import Scope
from .config import ContractsConfig, ContractsContext
from .errors import ARMAZENAMENTO_NAO_CONFIGURADO, conflict
from .schemas import (
    AmendmentBody, CancelSignatureBody, ContractBody, ContractPatch, ReadjustBody, RenderBody, SignatureBody, SuspendBody,
    TerminateBody, UsageBody,
)


def _dump(model: Any, **kw: Any) -> dict:
    return model.model_dump(mode="python", **kw)


def make_contracts_router(
    cfg: ContractsConfig,
    auth_dependency: Callable[..., Any],
    admin_dependency: Callable[..., Any],
    *,
    resolve_context: Callable[[Any, Any], ContractsContext],
    get_db: Callable[..., Any],
    get_billing: Callable[[Any], Any],
    get_signature: Optional[Callable[[ContractsContext], Any]] = None,
    get_storage: Optional[Callable[..., Any]] = None,
    renderer: documents.DocumentRenderer = documents.plain_text_document,
    prefix: str = "/api/contracts",
    tags: Optional[list[str]] = None,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=tags or ["contracts"])

    def ctx_dep(auth=Depends(auth_dependency), db=Depends(get_db)) -> ContractsContext:
        return resolve_context(auth, db)

    def storage_dep(storage=Depends(get_storage)) -> Any:
        return storage

    def no_storage() -> None:
        return None

    storage = Depends(storage_dep if get_storage is not None else no_storage)
    admin = Depends(admin_dependency)

    def scope(ctx: ContractsContext) -> Scope:
        return Scope(ctx.db, cfg, str(ctx.org_id))

    def present(ctx: ContractsContext, row: dict, lines: Optional[list[dict]] = None) -> dict:
        return svc.present_contract(row, is_admin=ctx.is_admin, lines=lines)

    def detail(ctx: ContractsContext, contract_id: Any) -> dict:
        s = scope(ctx)
        return present(ctx, svc.get_contract(s, contract_id), svc.contract_lines(s, contract_id))

    def need_storage(st: Any) -> Any:
        if st is None:
            raise conflict(ARMAZENAMENTO_NAO_CONFIGURADO, "O armazenamento de anexos não está configurado neste ambiente.")
        return st

    # --- collection -------------------------------------------------------------------------------------------

    @router.get("", name="contracts_list")
    async def list_route(
        q: Optional[str] = Query(None, max_length=100),
        status: Optional[str] = Query(None),
        billing_model: Optional[str] = Query(None),
        party_id: Optional[str] = Query(None),
        expiring_within_days: Optional[int] = Query(None, ge=0, le=3650),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        ctx: ContractsContext = Depends(ctx_dep),
    ) -> dict:
        rows, total, page, size = svc.list_contracts(
            scope(ctx), q=q, status=status, billing_model=billing_model, party_id=party_id,
            expiring_within_days=expiring_within_days, page=page, page_size=page_size,
        )
        return paginated_response([present(ctx, r) for r in rows], total, page, size)

    @router.post("", status_code=201, name="contracts_create")
    async def create_route(body: ContractBody, _a=admin, ctx: ContractsContext = Depends(ctx_dep)) -> dict:
        row = svc.create_contract(scope(ctx), _dump(body), user_id=ctx.user_id)
        return success_response(detail(ctx, row["id"]))

    @router.post("/billing/run", name="contracts_billing_run")
    async def billing_run_route(_a=admin, ctx: ContractsContext = Depends(ctx_dep)) -> dict:
        """Run the daily billing job for THIS org now (idempotent) -- the same body the scheduler runs."""
        return success_response(billing_svc.contracts_generate_billing(ctx.db, cfg, get_billing(ctx.db), org_id=str(ctx.org_id)))

    # --- one contract -----------------------------------------------------------------------------------------

    @router.get("/{contract_id}", name="contracts_get")
    async def get_route(contract_id: UUID, ctx: ContractsContext = Depends(ctx_dep)) -> dict:
        return success_response(detail(ctx, contract_id))

    @router.patch("/{contract_id}", name="contracts_update")
    async def update_route(contract_id: UUID, body: ContractPatch, _a=admin, ctx: ContractsContext = Depends(ctx_dep)) -> dict:
        svc.update_contract(scope(ctx), contract_id, _dump(body, exclude_unset=True))
        return success_response(detail(ctx, contract_id))

    @router.delete("/{contract_id}", status_code=204, name="contracts_delete")
    async def delete_route(contract_id: UUID, _a=admin, ctx: ContractsContext = Depends(ctx_dep)) -> Response:
        svc.delete_contract(scope(ctx), contract_id)
        return Response(status_code=204)

    @router.post("/{contract_id}/activate", name="contracts_activate")
    async def activate_route(contract_id: UUID, _a=admin, ctx: ContractsContext = Depends(ctx_dep)) -> dict:
        svc.activate_contract(scope(ctx), contract_id, billing=get_billing(ctx.db))
        return success_response(detail(ctx, contract_id))

    @router.post("/{contract_id}/suspend", name="contracts_suspend")
    async def suspend_route(contract_id: UUID, body: SuspendBody, _a=admin, ctx: ContractsContext = Depends(ctx_dep)) -> dict:
        svc.suspend_contract(scope(ctx), contract_id, body.reason, user_id=ctx.user_id)
        return success_response(detail(ctx, contract_id))

    @router.post("/{contract_id}/resume", name="contracts_resume")
    async def resume_route(contract_id: UUID, _a=admin, ctx: ContractsContext = Depends(ctx_dep)) -> dict:
        svc.resume_contract(scope(ctx), contract_id, billing=get_billing(ctx.db), user_id=ctx.user_id)
        return success_response(detail(ctx, contract_id))

    @router.post("/{contract_id}/terminate", name="contracts_terminate")
    async def terminate_route(contract_id: UUID, body: TerminateBody, _a=admin, ctx: ContractsContext = Depends(ctx_dep)) -> dict:
        svc.terminate_contract(scope(ctx), contract_id, _dump(body), billing=get_billing(ctx.db), user_id=ctx.user_id)
        return success_response(detail(ctx, contract_id))

    @router.post("/{contract_id}/amendments", status_code=201, name="contracts_amend")
    async def amend_route(contract_id: UUID, body: AmendmentBody, _a=admin, ctx: ContractsContext = Depends(ctx_dep)) -> dict:
        data = {"summary": body.summary, "effective_on": body.effective_on, "changes": _dump(body.changes, exclude_unset=True)}
        svc.amend_contract(scope(ctx), contract_id, data, user_id=ctx.user_id)
        return success_response(detail(ctx, contract_id))

    @router.post("/{contract_id}/readjust", name="contracts_readjust")
    async def readjust_route(contract_id: UUID, body: ReadjustBody, _a=admin, ctx: ContractsContext = Depends(ctx_dep)) -> dict:
        result = svc.readjust_contract(scope(ctx), contract_id, _dump(body), user_id=ctx.user_id)
        result.pop("contract", None)
        return success_response(result)

    @router.get("/{contract_id}/versions", name="contracts_versions")
    async def versions_route(contract_id: UUID, ctx: ContractsContext = Depends(ctx_dep)) -> dict:
        return success_response(svc.list_versions(scope(ctx), contract_id))

    @router.get("/{contract_id}/billing-preview", name="contracts_billing_preview")
    async def preview_route(contract_id: UUID, count: int = Query(6, ge=1, le=36), ctx: ContractsContext = Depends(ctx_dep)) -> dict:
        return success_response(billing_svc.billing_preview(scope(ctx), contract_id, count))

    @router.get("/{contract_id}/billings", name="contracts_billings")
    async def billings_route(contract_id: UUID, ctx: ContractsContext = Depends(ctx_dep)) -> dict:
        return success_response(billing_svc.list_billings(scope(ctx), contract_id))

    @router.get("/{contract_id}/usage", name="contracts_usage")
    async def usage_route(contract_id: UUID, ctx: ContractsContext = Depends(ctx_dep)) -> dict:
        return success_response(svc.usage_summary(scope(ctx), contract_id))

    @router.post("/{contract_id}/usage", status_code=201, name="contracts_add_usage")
    async def add_usage_route(contract_id: UUID, body: UsageBody, _a=admin, ctx: ContractsContext = Depends(ctx_dep)) -> dict:
        return success_response(svc.add_usage(scope(ctx), contract_id, _dump(body), user_id=ctx.user_id))

    # --- document + signature ---------------------------------------------------------------------------------

    @router.post("/{contract_id}/document", name="contracts_render_document")
    async def render_route(contract_id: UUID, body: RenderBody, _a=admin, ctx: ContractsContext = Depends(ctx_dep)) -> dict:
        sig_svc.render_document(scope(ctx), contract_id, body.template)
        return success_response(detail(ctx, contract_id))

    def adapter(ctx: ContractsContext) -> Any:
        return get_signature(ctx) if get_signature is not None else None

    @router.post("/{contract_id}/signature", status_code=201, name="contracts_send_signature")
    async def send_signature_route(contract_id: UUID, body: SignatureBody, _a=admin, ctx: ContractsContext = Depends(ctx_dep)) -> dict:
        result = await sig_svc.send_for_signature(scope(ctx), adapter(ctx), contract_id, [_dump(sg) for sg in body.signers],
                                                  message=body.message, renderer=renderer)
        return success_response({**detail(ctx, contract_id), "signature_link": result.get("signature_link")})

    @router.post("/{contract_id}/signature/sync", name="contracts_sync_signature")
    async def sync_signature_route(contract_id: UUID, _a=admin, ctx: ContractsContext = Depends(ctx_dep)) -> dict:
        await sig_svc.sync_signature(scope(ctx), adapter(ctx), contract_id, billing=get_billing(ctx.db))
        return success_response(detail(ctx, contract_id))

    @router.post("/{contract_id}/signature/cancel", name="contracts_cancel_signature")
    async def cancel_signature_route(contract_id: UUID, body: CancelSignatureBody, _a=admin, ctx: ContractsContext = Depends(ctx_dep)) -> dict:
        await sig_svc.cancel_signature(scope(ctx), adapter(ctx), contract_id, body.reason)
        return success_response(detail(ctx, contract_id))

    # --- attachments ------------------------------------------------------------------------------------------

    @router.get("/{contract_id}/attachments", name="contracts_attachments")
    async def attachments_route(contract_id: UUID, st=storage, ctx: ContractsContext = Depends(ctx_dep)) -> dict:
        return success_response(await att_svc.list_attachments(scope(ctx), need_storage(st), contract_id))

    @router.post("/{contract_id}/attachments", status_code=201, name="contracts_add_attachment")
    async def add_attachment_route(
        contract_id: UUID,
        file: UploadFile = File(...),
        kind: str = Form("other"),
        _a=admin,
        st=storage,
        ctx: ContractsContext = Depends(ctx_dep),
    ) -> dict:
        data = await file.read(att_svc.MAX_ATTACHMENT_BYTES + 1)
        row = await att_svc.add_attachment(scope(ctx), need_storage(st), contract_id, filename=file.filename,
                                           content_type=file.content_type or "", data=data, kind=kind, user_id=ctx.user_id)
        return success_response(row)

    @router.delete("/{contract_id}/attachments/{attachment_id}", status_code=204, name="contracts_delete_attachment")
    async def delete_attachment_route(contract_id: UUID, attachment_id: UUID, _a=admin, st=storage,
                                      ctx: ContractsContext = Depends(ctx_dep)) -> Response:
        await att_svc.delete_attachment(scope(ctx), need_storage(st), contract_id, attachment_id)
        return Response(status_code=204)

    return router


__all__ = ["make_contracts_router"]
