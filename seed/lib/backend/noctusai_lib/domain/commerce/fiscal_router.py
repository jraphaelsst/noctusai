"""Fiscal HTTP surface (slice B2) -- two mountable router factories.

    commerce_fiscal_router(...)          back office   /api/commerce/{fiscal*, orders/{id}/invoices, invoices/*}
    commerce_invoice_webhook_router(...) provider callbacks   /api/webhooks/invoices/{provider}/{org_id}

Same dependency style as `commerce_staff_router`: auth, db, storage and the admin gate arrive as
FastAPI dependencies; the only callables that are NOT dependencies are `make_provider(org_id)`
(one provider per org/call -- the per-company token sink is org-bound) and `get_webhook_token(org_id)`
(the per-org secret, resolved per request and FAIL-CLOSED when unset).

Authorization: staff may READ (`GET /fiscal`, invoice list, document links); every write
(`PUT /fiscal`, certificate, cutover + rollback, issue, cancel) needs `admin_dependency`
(`require_org_admin(...)`), RLS being the floor, not the check.

Host duty: the certificate upload is an `UploadFile` route, so the host's
`max_body_path_overrides` MUST list `CERTIFICATE_UPLOAD_PATH_PATTERN: CERTIFICATE_UPLOAD_MAX_BYTES`
(`create_product_app` refuses to boot otherwise).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Literal, Optional, get_type_hints
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.domain.jobs import JobRepository
from noctusai_lib.domain.payments.event_inbox import EventInbox
from noctusai_lib.integrations.email.types import EmailSender
from noctusai_lib.integrations.invoices import (
    InvoiceProvider,
    InvoiceProviderError,
    InvoiceWebhookAuthError,
    NfseMode,
)
from noctusai_lib.integrations.storage.protocol import StorageBackend
from noctusai_lib.primitives.exceptions import NotFoundError
from noctusai_lib.primitives.responses import success_response

from . import fiscal as fiscal_svc
from . import invoices as inv_svc
from .config import CommerceConfig, CommerceContext
from .errors import CommerceError
from .fiscal_types import MAX_CERTIFICATE_BYTES, InvoiceKind
from .orders import get_order

logger = logging.getLogger(__name__)

RateLimit = Callable[[str], Callable[[Callable], Callable]]

#: Pattern + ceiling for the host's `max_body_path_overrides` (64 KB file + multipart framing + password).
CERTIFICATE_UPLOAD_PATH_PATTERN = "/api/commerce/fiscal/certificate"
CERTIFICATE_UPLOAD_MAX_BYTES = 128 * 1024


class FiscalBody(StrictHttpModel):
    expected_version: int = Field(ge=0)
    inscricao_municipal: Optional[str] = Field(default=None, max_length=30)
    inscricao_estadual: Optional[str] = Field(default=None, max_length=30)
    municipio_ibge: Optional[str] = Field(default=None, max_length=7)
    nfse_mode: Optional[NfseMode] = None
    auto_issue_invoices: Optional[bool] = None


class ConfirmBody(StrictHttpModel):
    confirm: str = Field(max_length=100)


class IssueBody(StrictHttpModel):
    kind: InvoiceKind


class CancelBody(StrictHttpModel):
    reason: str = Field(max_length=255)


def _apply_limit(rate_limit: Optional[RateLimit], limit: str, fn: Callable) -> Callable:
    """Wrap `fn` with the host's limiter, resolving the string annotations against THIS module first
    (a real slowapi wrapper lives in another module and would 500 every wrapped route otherwise --
    the same trap `router._apply_limit` documents)."""
    if rate_limit is None:
        return fn
    fn.__annotations__ = get_type_hints(fn, include_extras=True)
    return rate_limit(limit)(fn)


def _provider(make_provider: Callable[[str], InvoiceProvider], org_id: Any) -> InvoiceProvider:
    try:
        return make_provider(str(org_id))
    except InvoiceProviderError as exc:  # InvoiceNotConfigured -> 503
        raise fiscal_svc.map_provider_error(exc) from None


def commerce_fiscal_router(
    cfg: CommerceConfig,
    *,
    auth_dependency: Callable[..., Any],
    admin_dependency: Callable[..., Any],
    resolve_context: Callable[[Any, Any], CommerceContext],
    get_db: Callable[..., Any],
    get_storage: Callable[..., StorageBackend],
    get_jobs: Callable[..., JobRepository],
    make_provider: Callable[[str], InvoiceProvider],
    prefix: str = "/api/commerce",
    tags: Optional[list[str]] = None,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=tags or ["commerce-fiscal"])

    def ctx_dep(auth=Depends(auth_dependency), db=Depends(get_db)) -> CommerceContext:
        return resolve_context(auth, db)

    admin = Depends(admin_dependency)

    @router.get("/fiscal", name="commerce_get_fiscal")
    async def get_fiscal_route(ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        return success_response(fiscal_svc.get_fiscal(ctx.db, ctx.org_id))

    @router.put("/fiscal", name="commerce_put_fiscal")
    async def put_fiscal_route(body: FiscalBody, _a=admin, ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        data = body.model_dump(mode="python", exclude_unset=True, exclude={"expected_version"})
        view = await asyncio.to_thread(
            fiscal_svc.update_fiscal, ctx.db, ctx.org_id, ctx.user_id, data,
            expected_version=body.expected_version, provider=_provider(make_provider, ctx.org_id),
        )
        return success_response(view)

    @router.post("/fiscal/certificate", name="commerce_upload_certificate")
    async def upload_certificate_route(
        _a=admin,
        ctx: CommerceContext = Depends(ctx_dep),
        file: UploadFile = File(...),
        password: str = Form(...),
    ) -> dict:
        pfx = await file.read(MAX_CERTIFICATE_BYTES + 1)  # never buffer more than one byte past the cap
        try:
            result = await asyncio.to_thread(
                fiscal_svc.upload_certificate, ctx.db, ctx.org_id,
                pfx=pfx, password=password, provider=_provider(make_provider, ctx.org_id),
            )
        finally:
            pfx = b""
            password = ""
        return success_response(result)

    @router.post("/fiscal/nfse-cutover", name="commerce_nfse_cutover")
    async def cutover_route(body: ConfirmBody, _a=admin, ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        view = await asyncio.to_thread(
            fiscal_svc.request_cutover, ctx.db, ctx.org_id, ctx.user_id,
            confirm=body.confirm, provider=_provider(make_provider, ctx.org_id),
        )
        return success_response(view)

    @router.post("/fiscal/nfse-cutover/rollback", name="commerce_nfse_rollback")
    async def rollback_route(body: ConfirmBody, _a=admin, ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        view = await asyncio.to_thread(
            fiscal_svc.rollback_cutover, ctx.db, ctx.org_id, ctx.user_id,
            confirm=body.confirm, provider=_provider(make_provider, ctx.org_id),
        )
        return success_response(view)

    @router.get("/orders/{order_id}/invoices", name="commerce_list_invoices")
    async def list_invoices_route(order_id: UUID, ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        get_order(ctx.db, ctx.org_id, order_id)  # 404 for another org's / a missing order
        return success_response(inv_svc.list_invoices(ctx.db, ctx.org_id, order_id))

    @router.post("/orders/{order_id}/invoices", status_code=201, name="commerce_issue_invoice")
    async def issue_invoice_route(
        order_id: UUID, body: IssueBody, _a=admin, ctx: CommerceContext = Depends(ctx_dep), jobs=Depends(get_jobs)
    ) -> dict:
        return success_response(await inv_svc.issue_for_staff(ctx.db, ctx.org_id, order_id, body.kind, jobs=jobs))

    @router.post("/invoices/{invoice_id}/cancel", name="commerce_cancel_invoice")
    async def cancel_invoice_route(
        invoice_id: UUID, body: CancelBody, _a=admin, ctx: CommerceContext = Depends(ctx_dep), jobs=Depends(get_jobs)
    ) -> dict:
        return success_response(await inv_svc.request_cancel(ctx.db, ctx.org_id, invoice_id, body.reason, jobs=jobs))

    @router.get("/invoices/{invoice_id}/documents/{fmt}", name="commerce_invoice_document")
    async def document_route(
        invoice_id: UUID, fmt: Literal["pdf", "xml"], ctx: CommerceContext = Depends(ctx_dep), storage=Depends(get_storage)
    ) -> dict:
        return success_response(await inv_svc.document_url(cfg, storage, ctx.db, ctx.org_id, invoice_id, fmt))

    return router


def commerce_invoice_webhook_router(
    cfg: CommerceConfig,
    *,
    get_db: Callable[..., Any],
    get_storage: Callable[..., StorageBackend],
    get_event_inbox: Callable[..., EventInbox],
    make_provider: Callable[[str], InvoiceProvider],
    get_webhook_token: Callable[[str], Optional[str]],
    get_jobs: Optional[Callable[..., JobRepository]] = None,
    get_mailer: Optional[Callable[..., Optional[EmailSender]]] = None,
    rate_limit: Optional[RateLimit] = None,
    prefix: str = "/api/webhooks/invoices",
    tags: Optional[list[str]] = None,
) -> APIRouter:
    """`POST {prefix}/{provider}/{org_id}` -- the invoice provider's callback (contract 2.6).

    (1) per-org token in a HEADER, constant-time, resolved per request, FAIL-CLOSED when unset
    (inside `provider.parse_webhook`); (2) the `ref` must be one of THIS org's invoices; (3) inbox
    key `(provider, ref:status_hint)`; (4) `provider.get(kind, ref)` is the only truth -- the body's
    status / urls are never read; (5) `rate_limit` is the only throttle on the unauthenticated surface.
    Always 200 for a verified delivery we do not act on.
    """
    router = APIRouter(prefix=prefix, tags=tags or ["commerce-webhooks"])
    jobs_dep = get_jobs or (lambda: None)
    mailer_dep = get_mailer or (lambda: None)

    async def receive(
        request: Request,
        provider_name: str,
        org_id: UUID,
        db=Depends(get_db),
        storage=Depends(get_storage),
        inbox=Depends(get_event_inbox),
        jobs=Depends(jobs_dep),
        mailer=Depends(mailer_dep),
    ) -> dict:
        body = await request.body()
        provider = _provider(make_provider, org_id)
        if provider_name != provider.name:
            raise NotFoundError("Provedor")
        try:
            event = provider.parse_webhook(request.headers, body, token=get_webhook_token(str(org_id)) or None)
        except InvoiceWebhookAuthError:
            logger.warning("commerce invoice webhook: verification failed (org=%s)", org_id)
            raise CommerceError("assinatura_invalida", "Assinatura do webhook inválida.", 401) from None
        except InvoiceProviderError:
            raise CommerceError("webhook_invalido", "Corpo do webhook inválido.", 400) from None
        rt = inv_svc.InvoiceRuntime(cfg, make_provider, storage, mailer)
        try:
            outcome = await inv_svc.handle_invoice_event(rt, db, str(org_id), event, inbox=inbox, jobs=jobs)
        except InvoiceProviderError as exc:
            raise fiscal_svc.map_provider_error(exc) from None
        return {"received": True, "outcome": outcome}

    handler = _apply_limit(rate_limit, cfg.webhook_rate_limit, receive)
    router.add_api_route("/{provider_name}/{org_id}", handler, methods=["POST"], name="commerce_invoice_webhook")
    return router


__all__ = [
    "CERTIFICATE_UPLOAD_MAX_BYTES",
    "CERTIFICATE_UPLOAD_PATH_PATTERN",
    "commerce_fiscal_router",
    "commerce_invoice_webhook_router",
]
