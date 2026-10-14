"""Quotes HTTP surface.

`make_quotes_router(...)` -- the STAFF API at `/api/quotes`. Org staff may read (`auth_dependency`); every write
(create / edit / delete / revise / send / decide / convert / sign) additionally requires `admin_dependency`.

`make_quotes_public_router(...)` -- the CUSTOMER API at `/api/public/quotes/{token}`: no session, the signed
expiring token IS the credential (org + quote bound into it, `links.py`). Rate-limited, allow-listed output
(`public.py`), one indistinguishable 404 for every bad token.

Everything the organ does not own arrives as an injected dependency: db, auth, e-mail sender, link secret, the
convert-on-accept handler, the e-signature adapter, the DOCX template. A route whose dependency the host did not
supply answers a typed 503 (`email_indisponivel` / `link_indisponivel` / `assinatura_indisponivel`), never a 500.

🔴 NEVER `get_admin_client().schema(...)` in here: `get_db` already returns the product's schema-scoped client.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

# NOC-REMEDIATE[organ-common-lift]: `_apply_limit` is the commerce router's private rate-limit wrapper; it moves to the
# shared organ module with the other lifted helpers -- repoint this import then. — 2026-10-14
from noctusai_lib.domain.commerce.router import RateLimit, _apply_limit
from noctusai_lib.integrations.docx_render import DocxRenderAdapter, get_docx_render_adapter
from noctusai_lib.integrations.email.types import EmailSender
from noctusai_lib.integrations.signature import SignatureAdapter
from noctusai_lib.primitives.exceptions import NotFoundError
from noctusai_lib.primitives.responses import paginated_response, success_response

from . import decisions as decisions_svc
from . import delivery as delivery_svc
from . import esign as esign_svc
from . import links
from . import public as public_svc
from . import quotes as quotes_svc
from . import render as render_svc
from ._common import Scope
from .config import QuotesConfig, QuotesContext
from .delivery import IssuerResolver, issuer_name
from .errors import (
    EMAIL_INDISPONIVEL,
    LINK_INDISPONIVEL,
    QuotesError,
    bad_link,
)
from .handler import NoopQuoteAcceptHandler, QuoteAcceptHandler
from .schemas import (
    CalculateBody,
    NewVersionBody,
    PublicAcceptBody,
    PublicRejectBody,
    QuoteBody,
    QuotePatch,
    SendBody,
    SignatureBody,
    StaffAcceptBody,
    StaffRejectBody,
)
from .types import Channel

#: A quote's single docx template: `(context) -> .docx bytes` (the host owns the tenant's letterhead).
DocxTemplate = Callable[[QuotesContext], bytes]


def _dump(model: Any, **kw: Any) -> dict:
    return model.model_dump(mode="python", **kw)


def _absent() -> None:
    """Stand-in dependency for an optional host dependency that was not supplied (resolves to `None`)."""
    return None


def _default_handler() -> QuoteAcceptHandler:
    return NoopQuoteAcceptHandler()


def make_quotes_router(
    cfg: QuotesConfig,
    auth_dependency: Callable[..., Any],
    admin_dependency: Callable[..., Any],
    *,
    resolve_context: Callable[[Any, Any], QuotesContext],
    get_db: Callable[..., Any],
    get_handler: Callable[..., QuoteAcceptHandler] = _default_handler,
    get_email: Optional[Callable[..., EmailSender]] = None,
    get_link_secret: Optional[Callable[..., str]] = None,
    accept_url: Optional[Callable[[str], str]] = None,
    issuer: Optional[IssuerResolver] = None,
    get_signature: Optional[Callable[..., SignatureAdapter]] = None,
    docx_template: Optional[DocxTemplate] = None,
    get_docx_adapter: Callable[..., DocxRenderAdapter] = lambda: get_docx_render_adapter(real=True),
    prefix: str = "/api/quotes",
    tags: Optional[list[str]] = None,
) -> APIRouter:
    """Build the staff router.

    Args:
        auth_dependency: the product's license-gated `get_current_user_org` (401 / 403 live there).
        admin_dependency: the org-admin gate; raises 403 for staff.
        resolve_context: `(auth_value, db) -> QuotesContext(db, org_id, user_id, is_admin)`.
        get_db: FastAPI dependency returning the schema-scoped client.
        get_handler: dependency returning the convert-on-accept `QuoteAcceptHandler` (default: no-op).
        get_email / get_link_secret / accept_url: needed by `POST /{id}/send` (`accept_url(token)` is the URL of the
            host's public accept page). Without them the route answers 503, not 500.
        issuer: `(org_id) -> {"name": ...}` the seller identity printed on PDFs / e-mails.
        get_signature: dependency returning a `SignatureAdapter`; mounts the signature routes when given.
        docx_template: `(ctx) -> bytes` of the tenant's Word template; mounts `GET /{id}/docx` when given.
    """
    router = APIRouter(prefix=prefix, tags=tags or ["quotes"])

    def ctx_dep(auth=Depends(auth_dependency), db=Depends(get_db)) -> QuotesContext:
        return resolve_context(auth, db)

    def scope(ctx: QuotesContext) -> Scope:
        return Scope(ctx.db, cfg, str(ctx.org_id))

    admin = Depends(admin_dependency)

    @router.get("", name="quotes_list")
    async def list_route(
        status: Optional[str] = Query(None),
        party_id: Optional[UUID] = Query(None),
        q: Optional[str] = Query(None, max_length=100),
        include_versions: bool = Query(False),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        ctx: QuotesContext = Depends(ctx_dep),
    ) -> dict:
        rows, total, page, size = quotes_svc.list_quotes(
            scope(ctx), status=status, party_id=str(party_id) if party_id else None, q=q,
            include_versions=include_versions, page=page, page_size=page_size,
        )
        return paginated_response(rows, total, page, size)

    @router.post("", status_code=201, name="quotes_create")
    async def create_route(body: QuoteBody, _a=admin, ctx: QuotesContext = Depends(ctx_dep)) -> dict:
        return success_response(quotes_svc.create_quote(scope(ctx), _dump(body), user_id=ctx.user_id))

    @router.post("/calculate", name="quotes_calculate")
    async def calculate_route(body: CalculateBody, ctx: QuotesContext = Depends(ctx_dep)) -> dict:
        return success_response(quotes_svc.calculate(scope(ctx), _dump(body)))

    @router.post("/expire-due", name="quotes_expire_due")
    async def expire_due_route(_a=admin, ctx: QuotesContext = Depends(ctx_dep)) -> dict:
        return success_response({"expired": quotes_svc.expire_due(scope(ctx))})

    @router.get("/{quote_id}", name="quotes_get")
    async def get_route(quote_id: UUID, ctx: QuotesContext = Depends(ctx_dep)) -> dict:
        return success_response(quotes_svc.get_quote(scope(ctx), quote_id))

    @router.patch("/{quote_id}", name="quotes_update")
    async def update_route(quote_id: UUID, body: QuotePatch, _a=admin, ctx: QuotesContext = Depends(ctx_dep)) -> dict:
        return success_response(
            quotes_svc.update_quote(scope(ctx), quote_id, _dump(body, exclude_unset=True), user_id=ctx.user_id)
        )

    @router.delete("/{quote_id}", status_code=204, name="quotes_delete")
    async def delete_route(quote_id: UUID, _a=admin, ctx: QuotesContext = Depends(ctx_dep)) -> Response:
        quotes_svc.delete_quote(scope(ctx), quote_id, user_id=ctx.user_id)
        return Response(status_code=204)

    @router.get("/{quote_id}/events", name="quotes_events")
    async def events_route(quote_id: UUID, ctx: QuotesContext = Depends(ctx_dep)) -> dict:
        return success_response(quotes_svc.list_events(scope(ctx), quote_id))

    @router.post("/{quote_id}/versions", status_code=201, name="quotes_new_version")
    async def version_route(
        quote_id: UUID, body: Optional[NewVersionBody] = None, _a=admin, ctx: QuotesContext = Depends(ctx_dep)
    ) -> dict:
        valid_until: Optional[date] = body.valid_until if body else None
        return success_response(quotes_svc.new_version(scope(ctx), quote_id, valid_until=valid_until, user_id=ctx.user_id))

    @router.post("/{quote_id}/send", name="quotes_send")
    async def send_route(
        quote_id: UUID,
        body: SendBody,
        _a=admin,
        ctx: QuotesContext = Depends(ctx_dep),
        sender=Depends(get_email or _absent),
        secret=Depends(get_link_secret or _absent),
    ) -> dict:
        if secret is None or accept_url is None:
            raise QuotesError(LINK_INDISPONIVEL, "Links de orçamento não estão configurados.", 503)
        if body.channel == "email" and sender is None:
            raise QuotesError(EMAIL_INDISPONIVEL, "O envio de e-mail não está configurado.", 503)
        result = await delivery_svc.send_quote(
            scope(ctx), quote_id, channel=body.channel, to=body.to, message=body.message, link_secret=secret,
            accept_url=accept_url, email_sender=sender, issuer=issuer, user_id=ctx.user_id,
        )
        return success_response(result)

    @router.post("/{quote_id}/accept", name="quotes_accept")
    async def accept_route(
        quote_id: UUID, body: StaffAcceptBody, request: Request, _a=admin, ctx: QuotesContext = Depends(ctx_dep),
        handler: QuoteAcceptHandler = Depends(get_handler),
    ) -> dict:
        out = decisions_svc.accept_quote(
            scope(ctx), quote_id, channel=Channel.STAFF, signer_name=body.signer_name, note=body.note, user_id=ctx.user_id,
            ip=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"), handler=handler,
        )
        return success_response(quotes_svc.get_quote(scope(ctx), quote_id) | {"acceptance": out["acceptance"]})

    @router.post("/{quote_id}/reject", name="quotes_reject")
    async def reject_route(
        quote_id: UUID, body: StaffRejectBody, request: Request, _a=admin, ctx: QuotesContext = Depends(ctx_dep)
    ) -> dict:
        decisions_svc.reject_quote(
            scope(ctx), quote_id, channel=Channel.STAFF, signer_name=body.signer_name, reason=body.reason, user_id=ctx.user_id,
            ip=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"),
        )
        return success_response(quotes_svc.get_quote(scope(ctx), quote_id))

    @router.post("/{quote_id}/convert", name="quotes_convert")
    async def convert_route(
        quote_id: UUID, _a=admin, ctx: QuotesContext = Depends(ctx_dep), handler: QuoteAcceptHandler = Depends(get_handler)
    ) -> dict:
        return success_response(decisions_svc.convert_quote(scope(ctx), quote_id, handler))

    @router.get("/{quote_id}/acceptance", name="quotes_acceptance")
    async def acceptance_route(quote_id: UUID, ctx: QuotesContext = Depends(ctx_dep)) -> dict:
        s = scope(ctx)
        quotes_svc.get_row(s, quote_id)
        return success_response(decisions_svc.get_acceptance(s, quote_id))

    def _render_ctx(ctx: QuotesContext, quote_id: UUID) -> dict:
        s = scope(ctx)
        view = quotes_svc.get_quote(s, quote_id)
        return render_svc.quote_context(
            view, view["lines"], party_name=str((view.get("party") or {}).get("legal_name") or ""), issuer_name=issuer_name(issuer, s.org_id)
        )

    @router.get("/{quote_id}/pdf", name="quotes_pdf")
    async def pdf_route(quote_id: UUID, ctx: QuotesContext = Depends(ctx_dep)) -> Response:
        data = render_svc.render_pdf(_render_ctx(ctx, quote_id))
        return Response(content=data, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="orcamento.pdf"'})

    if docx_template is not None:

        @router.get("/{quote_id}/docx", name="quotes_docx")
        async def docx_route(
            quote_id: UUID, ctx: QuotesContext = Depends(ctx_dep), adapter: DocxRenderAdapter = Depends(get_docx_adapter)
        ) -> Response:
            data = render_svc.render_docx(adapter, docx_template(ctx), _render_ctx(ctx, quote_id))
            return Response(
                content=data,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={"Content-Disposition": 'attachment; filename="orcamento.docx"'},
            )

    if get_signature is not None:

        @router.post("/{quote_id}/signature", status_code=201, name="quotes_signature_request")
        async def signature_request_route(
            quote_id: UUID, body: SignatureBody, _a=admin, ctx: QuotesContext = Depends(ctx_dep),
            adapter: SignatureAdapter = Depends(get_signature),
        ) -> dict:
            return success_response(
                await esign_svc.request_signature(
                    scope(ctx), quote_id, adapter, [_dump(x) for x in body.signers], message=body.message, issuer=issuer,
                    user_id=ctx.user_id,
                )
            )

        @router.get("/{quote_id}/signature", name="quotes_signature_status")
        async def signature_status_route(
            quote_id: UUID, ctx: QuotesContext = Depends(ctx_dep), adapter: SignatureAdapter = Depends(get_signature)
        ) -> dict:
            return success_response(await esign_svc.refresh_signature(scope(ctx), quote_id, adapter))

    return router


def make_quotes_public_router(
    cfg: QuotesConfig,
    *,
    get_db: Callable[..., Any],
    get_link_secret: Callable[..., str],
    get_handler: Callable[..., QuoteAcceptHandler] = _default_handler,
    issuer: Optional[IssuerResolver] = None,
    is_org_active: Optional[Callable[[Any, str], bool]] = None,
    client_ip: Optional[Callable[[Request], Optional[str]]] = None,
    rate_limit: Optional[RateLimit] = None,
    prefix: str = "/api/public/quotes",
    tags: Optional[list[str]] = None,
) -> APIRouter:
    """The PUBLIC accept router (no login).

    `rate_limit` (e.g. slowapi's `limiter.limit`) is applied with `cfg.public_rate_limit` on the read / PDF routes and
    `cfg.decision_rate_limit` on accept / reject. Every handler takes `request: Request` first so a limiter can key on
    it. `client_ip` extracts the recorded address (default `request.client.host`; behind a proxy the host passes its
    trusted-header reader -- the organ never trusts `X-Forwarded-For` by itself).
    `is_org_active(db, org_id)` lets the host refuse links of an org whose licence lapsed (same 404 as a bad token).
    """
    router = APIRouter(prefix=prefix, tags=tags or ["quotes-public"])

    def limited(limit: str, fn: Callable) -> Callable:
        return _apply_limit(rate_limit, limit, fn)

    def open_scope(token: str, db: Any, secret: str) -> tuple[Scope, str]:
        org_id, quote_id = links.open_token(secret, token)
        if is_org_active is not None and not is_org_active(db, org_id):
            raise bad_link()
        s = Scope(db, cfg, org_id)
        try:
            quotes_svc.get_row(s, quote_id)
        except NotFoundError as exc:  # a validly-signed token for a deleted quote must look like any other bad token
            raise bad_link() from exc
        return s, quote_id

    def ip_of(request: Request) -> Optional[str]:
        if client_ip is not None:
            return client_ip(request)
        return request.client.host if request.client else None

    async def view(request: Request, token: str, db=Depends(get_db), secret: str = Depends(get_link_secret)) -> dict:
        s, quote_id = open_scope(token, db, secret)
        return success_response(public_svc.public_quote(s, quote_id, issuer=issuer, mark_viewed=True))

    async def pdf(request: Request, token: str, db=Depends(get_db), secret: str = Depends(get_link_secret)) -> Response:
        s, quote_id = open_scope(token, db, secret)
        shown = public_svc.public_quote(s, quote_id, issuer=issuer)
        row = quotes_svc.get_row(s, quote_id)
        ctx = render_svc.quote_context(
            {**row, "status": shown["status"]}, quotes_svc.quote_lines(s, quote_id), party_name=shown["party_name"], issuer_name=shown["issuer_name"]
        )
        return Response(
            content=render_svc.render_pdf(ctx), media_type="application/pdf",
            headers={"Content-Disposition": 'inline; filename="orcamento.pdf"'},
        )

    async def accept(
        request: Request, token: str, body: PublicAcceptBody, db=Depends(get_db), secret: str = Depends(get_link_secret),
        handler: QuoteAcceptHandler = Depends(get_handler),
    ) -> dict:
        s, quote_id = open_scope(token, db, secret)
        decisions_svc.accept_quote(
            s, quote_id, channel=Channel.PUBLIC_LINK, signer_name=body.name, agree=body.agree, ip=ip_of(request),
            user_agent=request.headers.get("user-agent"), handler=handler,
        )
        return success_response(public_svc.public_quote(s, quote_id, issuer=issuer))

    async def reject(
        request: Request, token: str, body: PublicRejectBody, db=Depends(get_db), secret: str = Depends(get_link_secret)
    ) -> dict:
        s, quote_id = open_scope(token, db, secret)
        decisions_svc.reject_quote(
            s, quote_id, channel=Channel.PUBLIC_LINK, signer_name=body.name, reason=body.reason, ip=ip_of(request),
            user_agent=request.headers.get("user-agent"),
        )
        return success_response(public_svc.public_quote(s, quote_id, issuer=issuer))

    router.add_api_route("/{token}", limited(cfg.public_rate_limit, view), methods=["GET"], name="quotes_public_view")
    router.add_api_route("/{token}/pdf", limited(cfg.public_rate_limit, pdf), methods=["GET"], name="quotes_public_pdf")
    router.add_api_route("/{token}/accept", limited(cfg.decision_rate_limit, accept), methods=["POST"], name="quotes_public_accept")
    router.add_api_route("/{token}/reject", limited(cfg.decision_rate_limit, reject), methods=["POST"], name="quotes_public_reject")
    return router


__all__ = ["DocxTemplate", "make_quotes_public_router", "make_quotes_router"]
