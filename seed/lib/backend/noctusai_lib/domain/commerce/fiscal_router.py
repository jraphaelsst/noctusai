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

Platform admin (contract 0): pass `platform_admin_dependency` (e.g. `require_platform_admin(...)`, which
raises 403 unless the caller is platform staff) to let a platform admin ACTING ON ANOTHER ORG perform the
writes without being an admin of that org. The org itself is whatever `resolve_context` returns (the
org-picker's selected org) -- the dependency only widens WHO may write. The real actor stays the
caller: `updated_by` / `changed_by` / `approved_by` are the platform admin's own user id, and the
profile-version ledger snapshot carries `acted_by_platform_admin: true`. Omitted => unchanged: only
`admin_dependency` authorizes writes.

Host duty: the certificate upload is an `UploadFile` route, so the host's
`max_body_path_overrides` MUST list `CERTIFICATE_UPLOAD_PATH_PATTERN: CERTIFICATE_UPLOAD_MAX_BYTES`
(`create_product_app` refuses to boot otherwise).
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.domain._organ_common import RateLimit, apply_rate_limit
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
from noctusai_lib.integrations.invoices.webhook import verify_webhook_token
from noctusai_lib.primitives.exceptions import AppException
from noctusai_lib.primitives.responses import success_response

from . import fiscal as fiscal_svc
from . import invoices as inv_svc
from .config import CommerceConfig, CommerceContext
from .errors import CommerceError
from .fiscal_types import MAX_CERTIFICATE_BYTES, InvoiceKind
from .orders import get_order

logger = logging.getLogger(__name__)

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


@dataclass(frozen=True)
class _Outcome:
    ok: bool
    exc: Optional[BaseException] = None


def _soft(dep: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a gate dependency so a 403 from its BODY is recorded instead of raised (its own
    sub-dependencies -- authentication, the 401 -- still resolve and raise normally). The wrapper
    carries the gate's evaluated signature, so FastAPI resolves the same sub-dependencies."""

    async def wrapper(*args: Any, **kwargs: Any) -> _Outcome:
        try:
            out = dep(*args, **kwargs)
            if inspect.isawaitable(out):
                await out
            return _Outcome(True)
        except (HTTPException, AppException) as exc:
            return _Outcome(False, exc)

    try:
        wrapper.__signature__ = inspect.signature(dep, eval_str=True)  # type: ignore[attr-defined]
    except (NameError, TypeError):  # unresolvable string annotation: fall back to the raw signature
        wrapper.__signature__ = inspect.signature(dep)  # type: ignore[attr-defined]
    return wrapper


def _provider(make_provider: Callable[[str], InvoiceProvider], org_id: Any) -> InvoiceProvider:
    try:
        return make_provider(str(org_id))
    except InvoiceProviderError as exc:  # InvoiceNotConfigured -> 503
        raise fiscal_svc.map_provider_error(exc) from None


def _log_platform(platform: bool, ctx: CommerceContext, action: str) -> None:
    if platform:
        logger.info("commerce fiscal: platform admin %s did %s on org %s", ctx.user_id, action, ctx.org_id)


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
    platform_admin_dependency: Optional[Callable[..., Any]] = None,
    prefix: str = "/api/commerce",
    tags: Optional[list[str]] = None,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=tags or ["commerce-fiscal"])

    def ctx_dep(auth=Depends(auth_dependency), db=Depends(get_db)) -> CommerceContext:
        return resolve_context(auth, db)

    def _decide(admin_out: _Outcome, platform_out: Optional[_Outcome]) -> bool:
        """Org admin => False. Else, a platform admin (when configured) => True. Else the admin's 403."""
        if admin_out.ok:
            return False
        if platform_out is not None and platform_out.ok:
            return True
        raise admin_out.exc  # type: ignore[misc]

    if platform_admin_dependency is None:

        async def write_gate(admin_out: _Outcome = Depends(_soft(admin_dependency))) -> bool:
            return _decide(admin_out, None)

    else:

        async def write_gate(  # type: ignore[misc]
            admin_out: _Outcome = Depends(_soft(admin_dependency)),
            platform_out: _Outcome = Depends(_soft(platform_admin_dependency)),
        ) -> bool:
            return _decide(admin_out, platform_out)

    admin = Depends(write_gate)

    @router.get("/fiscal", name="commerce_get_fiscal")
    async def get_fiscal_route(ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        return success_response(fiscal_svc.get_fiscal(ctx.db, ctx.org_id))

    @router.put("/fiscal", name="commerce_put_fiscal")
    async def put_fiscal_route(body: FiscalBody, platform: bool = admin, ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        data = body.model_dump(mode="python", exclude_unset=True, exclude={"expected_version"})
        view = await asyncio.to_thread(
            fiscal_svc.update_fiscal, ctx.db, ctx.org_id, ctx.user_id, data,
            expected_version=body.expected_version, provider=_provider(make_provider, ctx.org_id), platform_actor=platform,
        )
        return success_response(view)

    @router.post("/fiscal/certificate", name="commerce_upload_certificate")
    async def upload_certificate_route(
        platform: bool = admin,
        ctx: CommerceContext = Depends(ctx_dep),
        file: UploadFile = File(...),
        password: str = Form(...),
    ) -> dict:
        pfx = await file.read(MAX_CERTIFICATE_BYTES + 1)  # never buffer more than one byte past the cap
        try:
            result = await asyncio.to_thread(
                fiscal_svc.upload_certificate, ctx.db, ctx.org_id,
                pfx=pfx, password=password, provider=_provider(make_provider, ctx.org_id),
                user_id=ctx.user_id, platform_actor=platform,
            )
        finally:
            pfx = b""
            password = ""
        return success_response(result)

    @router.post("/fiscal/nfse-cutover", name="commerce_nfse_cutover")
    async def cutover_route(body: ConfirmBody, platform: bool = admin, ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        view = await asyncio.to_thread(
            fiscal_svc.request_cutover, ctx.db, ctx.org_id, ctx.user_id,
            confirm=body.confirm, provider=_provider(make_provider, ctx.org_id), platform_actor=platform,
        )
        return success_response(view)

    @router.post("/fiscal/nfse-cutover/rollback", name="commerce_nfse_rollback")
    async def rollback_route(body: ConfirmBody, platform: bool = admin, ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        view = await asyncio.to_thread(
            fiscal_svc.rollback_cutover, ctx.db, ctx.org_id, ctx.user_id,
            confirm=body.confirm, provider=_provider(make_provider, ctx.org_id), platform_actor=platform,
        )
        return success_response(view)

    @router.get("/orders/{order_id}/invoices", name="commerce_list_invoices")
    async def list_invoices_route(order_id: UUID, ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        get_order(ctx.db, ctx.org_id, order_id)  # 404 for another org's / a missing order
        return success_response(inv_svc.list_invoices(ctx.db, ctx.org_id, order_id))

    @router.post("/orders/{order_id}/invoices", status_code=201, name="commerce_issue_invoice")
    async def issue_invoice_route(
        order_id: UUID, body: IssueBody, platform: bool = admin, ctx: CommerceContext = Depends(ctx_dep), jobs=Depends(get_jobs)
    ) -> dict:
        _log_platform(platform, ctx, "issue_invoice")
        return success_response(await inv_svc.issue_for_staff(ctx.db, ctx.org_id, order_id, body.kind, jobs=jobs))

    @router.post("/invoices/{invoice_id}/cancel", name="commerce_cancel_invoice")
    async def cancel_invoice_route(
        invoice_id: UUID, body: CancelBody, platform: bool = admin, ctx: CommerceContext = Depends(ctx_dep), jobs=Depends(get_jobs)
    ) -> dict:
        _log_platform(platform, ctx, "cancel_invoice")
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
        # AUTH FIRST, before any provider construction / DB / credential read: an unknown org, an
        # unset token, a wrong token and an unknown provider path are the SAME 401 (no existence or
        # invoicing-status oracle for an unauthenticated caller).
        denied = CommerceError("assinatura_invalida", "Assinatura do webhook inválida.", 401)
        try:
            verify_webhook_token(provider_name, request.headers, token=get_webhook_token(str(org_id)) or None)
        except InvoiceWebhookAuthError:
            logger.warning("commerce invoice webhook: verification failed (org=%s)", org_id)
            raise denied from None
        provider = _provider(make_provider, org_id)
        if provider_name != provider.name:
            raise denied
        try:
            event = provider.parse_webhook(request.headers, body, token=get_webhook_token(str(org_id)) or None)
        except InvoiceWebhookAuthError:
            raise denied from None
        except InvoiceProviderError:
            raise CommerceError("webhook_invalido", "Corpo do webhook inválido.", 400) from None
        rt = inv_svc.InvoiceRuntime(cfg, make_provider, storage, mailer)
        try:
            outcome = await inv_svc.handle_invoice_event(rt, db, str(org_id), event, inbox=inbox, jobs=jobs)
        except InvoiceProviderError as exc:
            raise fiscal_svc.map_provider_error(exc) from None
        return {"received": True, "outcome": outcome}

    handler = apply_rate_limit(rate_limit, cfg.webhook_rate_limit, receive)
    router.add_api_route("/{provider_name}/{org_id}", handler, methods=["POST"], name="commerce_invoice_webhook")
    return router


__all__ = [
    "CERTIFICATE_UPLOAD_MAX_BYTES",
    "CERTIFICATE_UPLOAD_PATH_PATTERN",
    "commerce_fiscal_router",
    "commerce_invoice_webhook_router",
]
