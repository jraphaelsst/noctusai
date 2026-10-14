"""Order invoices -- plan, enqueue, issue, copy, cancel, reconcile (slice B2).

Flow (CONTRACT 2.4 "Invoices", D36/D37):

    on_order_paid(order)        -> rows (status `processing`, ref assigned) + one `commerce.invoice.issue`
                                   job each (dedupe_key = ref), only if `auto_issue_invoices`
    job: issue                  -> provider.issue(ref) -> authorized: persist + copy PDF/XML into the
                                   PRIVATE bucket | rejected: `rejection` + staff alert | processing:
                                   poll again later | retryable provider failure: the worker's backoff
    on_order_revoked(order)     -> `commerce.invoice.cancel` job per authorized invoice
    job: cancel                 -> provider.cancel(ref, reason>=15) -> cancelled | provider refusal
                                   (e.g. the cancel window passed): `rejection` + staff alert
    webhook                     -> `get(kind, ref)` is the ONLY truth; the body is never read for state

One document per tax treatment present on the order: `service_nfse` -> `nfse`, `goods_nfe` -> `nfe`;
`rights_receipt` / `none` -> nothing here (P5 receipt/certificate). An item's treatment is its
product's `tax_treatment_override`, else the store profile's mapping for the item's `product_type`.

The row is created BEFORE the job so `ref` (the dedupe key) exists at enqueue time and a retry of
the same logical issue is a no-op; a re-issue after a rejection is a new `seq` (= a new ref).
`register_*` are the sync, DB-only halves (callable from sync webhook code); `issue_invoices_for_order`
/ `on_order_paid` / `on_order_revoked` add the (async) enqueue.

Secrets: tokens / certificates never reach this module (provider-internal); provider refusal
reasons are the only provider text stored or e-mailed, truncated.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable, Mapping, Optional

from noctusai_lib.domain.jobs import DeadLetterError, Job, JobRepository, RetryPolicy
from noctusai_lib.domain.jobs.repo import RescheduleLater
from noctusai_lib.domain.payments.event_inbox import EventInbox
from noctusai_lib.integrations.email.types import EmailSender, OutgoingEmail
from noctusai_lib.integrations.invoices import (
    Address,
    InvoiceEvent,
    InvoiceItem,
    InvoiceProvider,
    InvoiceProviderError,
    InvoiceRequest,
    InvoiceResult,
    InvoiceTaker,
)
from noctusai_lib.integrations.persistence.table_reads import paged_rows
from noctusai_lib.integrations.storage.protocol import StorageBackend
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import digits, first, get_row, new_id, now, now_iso, tbl
from .config import CommerceConfig
from .errors import CommerceError, conflict, not_found
from .fiscal_types import (
    DOCUMENT_URL_TTL_SECONDS,
    LIVE_STATUSES,
    MIN_CANCEL_REASON_CHARS,
    REISSUABLE_STATUSES,
    InvoiceKind,
    InvoiceStatus,
    company_ref_of,
)
from .orders import get_order, list_items
from .profile import get_profile
from .types import TaxTreatment

logger = logging.getLogger(__name__)

INVOICES = "commerce_invoices"
ISSUE_JOB = "commerce.invoice.issue"
CANCEL_JOB = "commerce.invoice.cancel"

#: Backoff for the issue/cancel jobs. The host passes the SAME policy to its `Worker` (the worker's
#: policy is the retry-vs-dead-letter authority; the handlers use it to know the LAST attempt).
INVOICE_RETRY_POLICY = RetryPolicy(max_retries=5, backoff_seconds=30.0, backoff_multiplier=2.0, max_backoff_seconds=1800.0)

#: How long a document may stay `processing` at the provider before we record it as an error.
PROCESSING_MAX_AGE = timedelta(hours=6)
POLL_DELAY_SECONDS = 30.0

_TREATMENT_TO_KIND = {TaxTreatment.SERVICE_NFSE.value: InvoiceKind.NFSE, TaxTreatment.GOODS_NFE.value: InvoiceKind.NFE}
_ISSUABLE_ORDER_STATUSES = frozenset({"paid", "partially_refunded"})
_REVOKED_ORDER_STATUSES = frozenset({"refunded", "chargeback"})

#: status -> statuses a reconcile may move it to (a stale read must never un-authorize or un-cancel).
_ALLOWED_MOVES: dict[str, frozenset[str]] = {
    InvoiceStatus.PROCESSING.value: frozenset(s.value for s in InvoiceStatus),
    InvoiceStatus.AUTHORIZED.value: frozenset({InvoiceStatus.AUTHORIZED.value, InvoiceStatus.CANCELLED.value}),
    InvoiceStatus.CANCELLED.value: frozenset({InvoiceStatus.CANCELLED.value}),
    InvoiceStatus.REJECTED.value: frozenset(s.value for s in InvoiceStatus),
    InvoiceStatus.ERROR.value: frozenset(s.value for s in InvoiceStatus),
}


@dataclass(frozen=True)
class InvoiceRuntime:
    """The IO a reconcile needs. Instances (not factories): built per request / per job."""

    cfg: CommerceConfig
    make_provider: Callable[[str], InvoiceProvider]
    storage: StorageBackend
    mailer: Optional[EmailSender] = None


# ─── reads / refs ────────────────────────────────────────────────────────


def build_ref(org_id: Any, order_id: Any, kind: InvoiceKind, seq: int) -> str:
    """`"{org_short}-{order_id}-{kind}-{n}"` -- 8 + 36 + 4 + digits chars, inside the provider's 64."""
    return f"{str(org_id).replace('-', '')[:8]}-{order_id}-{kind.value}-{seq}"


def list_invoices(db: Any, org_id: Any, order_id: Any) -> list[dict]:
    rows = paged_rows(db, INVOICES, org_id, eq_filters={"order_id": str(order_id)})
    return sorted(rows, key=lambda r: (str(r.get("kind")), int(r.get("seq") or 0)))


def get_invoice(db: Any, org_id: Any, invoice_id: Any) -> dict:
    row = get_row(db, INVOICES, org_id, invoice_id)
    if row is None:
        raise not_found("Nota fiscal")
    return row


def get_invoice_by_ref(db: Any, org_id: Any, ref: str) -> Optional[dict]:
    return first(tbl(db, INVOICES).select("*").eq("org_id", str(org_id)).eq("ref", ref).limit(1).execute())


def _update(db: Any, org_id: Any, invoice_id: Any, patch: Mapping[str, Any]) -> dict:
    saved = first(
        tbl(db, INVOICES).update({**patch, "updated_at": now_iso()}).eq("org_id", str(org_id)).eq("id", str(invoice_id)).execute()
    )
    if saved is None:
        raise not_found("Nota fiscal")
    return saved


# ─── planning ────────────────────────────────────────────────────────────


def _item_treatments(db: Any, org_id: Any, profile: Mapping[str, Any], items: list[dict]) -> dict[str, Any]:
    """item id -> (TaxTreatment value, product row | None)."""
    ids = sorted({str(i["product_id"]) for i in items if i.get("product_id")})
    products: dict[str, dict] = {}
    if ids:
        resp = tbl(db, "commerce_products").select("id,tax_treatment_override,attributes").eq("org_id", str(org_id)).in_("id", ids).execute()
        products = {str(p["id"]): dict(p) for p in (resp.data or [])}
    mapping = {str(getattr(k, "value", k)): str(getattr(v, "value", v)) for k, v in (profile.get("tax_treatment") or {}).items()}
    out: dict[str, Any] = {}
    for item in items:
        product = products.get(str(item.get("product_id"))) if item.get("product_id") else None
        treatment = (product or {}).get("tax_treatment_override") or mapping.get(str(item["product_type"])) or TaxTreatment.NONE.value
        out[str(item["id"])] = (treatment, product)
    return out


def plan_invoices(db: Any, org_id: Any, order_id: Any, profile: Mapping[str, Any]) -> dict[InvoiceKind, list[dict]]:
    """Order items grouped by the invoice kind their tax treatment calls for (none -> absent)."""
    items = list_items(db, org_id, order_id)
    treatments = _item_treatments(db, org_id, profile, items)
    plan: dict[InvoiceKind, list[dict]] = {}
    for item in items:
        treatment, product = treatments[str(item["id"])]
        kind = _TREATMENT_TO_KIND.get(treatment)
        if kind is not None:
            plan.setdefault(kind, []).append({**item, "_product": product})
    return plan


def register_invoices(
    db: Any, org_id: Any, order: Mapping[str, Any], *, kinds: Optional[list[InvoiceKind]] = None, retry_rejected: bool = False
) -> list[dict]:
    """Create the `processing` rows still missing for this order (sync, DB only, idempotent).

    A live document (processing / authorized / cancelled) of a kind blocks a second one; a
    rejected / errored one is re-issued under a NEW `seq` only when `retry_rejected` (staff).
    """
    profile = get_profile(db, org_id) or {}
    plan = plan_invoices(db, org_id, order["id"], profile)
    existing = list_invoices(db, org_id, order["id"])
    created: list[dict] = []
    for kind in plan:
        if kinds is not None and kind not in kinds:
            continue
        of_kind = [r for r in existing if r["kind"] == kind.value]
        if any(r["status"] in LIVE_STATUSES for r in of_kind):
            continue
        if of_kind and not retry_rejected:
            continue
        if of_kind and of_kind[-1]["status"] not in REISSUABLE_STATUSES:
            continue
        seq = max((int(r["seq"]) for r in of_kind), default=0) + 1
        row = {
            "id": new_id(),
            "org_id": str(org_id),
            "order_id": str(order["id"]),
            "kind": kind.value,
            "seq": seq,
            "ref": build_ref(org_id, order["id"], kind, seq),
            "status": InvoiceStatus.PROCESSING.value,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        try:
            created.append(first(tbl(db, INVOICES).insert(row).execute()) or row)
        except Exception as exc:  # noqa: BLE001 - narrowed right below
            if is_unique_violation(exc):
                logger.info("commerce invoice %s already registered (race); skipping", row["ref"])
                continue
            raise
    return created


async def _enqueue_issue(jobs: JobRepository, invoice: Mapping[str, Any]) -> None:
    await jobs.enqueue(
        type=ISSUE_JOB,
        payload={"org_id": str(invoice["org_id"]), "invoice_id": str(invoice["id"])},
        max_retries=INVOICE_RETRY_POLICY.max_retries,
        dedupe_key=str(invoice["ref"]),
    )


async def issue_invoices_for_order(
    db: Any,
    org_id: Any,
    order: Mapping[str, Any],
    *,
    jobs: JobRepository,
    kinds: Optional[list[InvoiceKind]] = None,
    retry_rejected: bool = False,
) -> list[dict]:
    """Register + enqueue one invoice per tax treatment present on the order."""
    rows = register_invoices(db, org_id, order, kinds=kinds, retry_rejected=retry_rejected)
    for row in rows:
        await _enqueue_issue(jobs, row)
    return rows


async def enqueue_pending_invoices(db: Any, jobs: JobRepository, org_id: Any = None) -> int:
    """Safety net for a crash between `register_invoices` and the enqueue: re-enqueue every
    `processing` row (dedupe_key = ref makes already-queued ones a no-op). Returns the count seen."""
    query = tbl(db, INVOICES).select("*").eq("status", InvoiceStatus.PROCESSING.value)
    if org_id is not None:
        query = query.eq("org_id", str(org_id))
    rows = [dict(r) for r in (query.limit(500).execute().data or [])]
    for row in rows:
        await _enqueue_issue(jobs, row)
    return len(rows)


# ─── hooks (called by the order machine) ─────────────────────────────────


def register_on_order_paid(db: Any, order: Mapping[str, Any]) -> list[dict]:
    """The sync half of `on_order_paid`: rows only, no job. Pair with `enqueue_pending_invoices`."""
    org_id = order["org_id"]
    profile = get_profile(db, org_id)
    if not profile or not profile.get("auto_issue_invoices"):
        return []
    return register_invoices(db, org_id, order)


async def on_order_paid(db: Any, order: Mapping[str, Any], *, jobs: JobRepository) -> list[dict]:
    """`-> paid`: enqueue the invoices when the store opted into `auto_issue_invoices`.

    The CALLER wraps this in try/log: a fiscal failure must not undo a payment, and
    `enqueue_pending_invoices` re-queues whatever was registered but not enqueued."""
    rows = register_on_order_paid(db, order)
    for row in rows:
        await _enqueue_issue(jobs, row)
    return rows


async def on_order_revoked(
    db: Any, order: Mapping[str, Any], *, jobs: JobRepository, reason: Optional[str] = None
) -> list[dict]:
    """Full refund / lost chargeback: enqueue a cancel for every authorized invoice of the order
    (independent of `auto_issue_invoices` -- an issued note must be cancelled)."""
    org_id = order["org_id"]
    why = reason or f"Pedido {order['id']} estornado integralmente"
    out = []
    for inv in list_invoices(db, org_id, order["id"]):
        if inv["status"] == InvoiceStatus.AUTHORIZED.value and not inv.get("cancel_requested_at"):
            out.append(await request_cancel(db, org_id, inv["id"], why, jobs=jobs))
    return out


# ─── staff actions ───────────────────────────────────────────────────────


async def issue_for_staff(
    db: Any, org_id: Any, order_id: Any, kind: InvoiceKind, *, jobs: JobRepository
) -> dict:
    """`POST /orders/{id}/invoices`: issue, or retry a rejected / errored one."""
    order = get_order(db, org_id, order_id)
    profile = get_profile(db, org_id) or {}
    if order["status"] not in _ISSUABLE_ORDER_STATUSES:
        raise conflict("pedido_nao_pago", "A nota só pode ser emitida para um pedido pago.")
    if not company_ref_of(profile):
        raise conflict("emissao_indisponivel", "Cadastre os dados fiscais e o certificado da loja antes de emitir.")
    if kind not in plan_invoices(db, org_id, order_id, profile):
        raise CommerceError("tipo_nota_invalido", "Este pedido não tem itens para esse tipo de nota.", 422, field="kind")
    rows = await issue_invoices_for_order(db, org_id, order, jobs=jobs, kinds=[kind], retry_rejected=True)
    if not rows:
        raise conflict("nota_ja_emitida", "Já existe uma nota desse tipo para o pedido.")
    return rows[0]


async def request_cancel(db: Any, org_id: Any, invoice_id: Any, reason: str, *, jobs: JobRepository) -> dict:
    """Record the cancel request and enqueue it (the provider call + retries run in the job)."""
    why = (reason or "").strip()
    if len(why) < MIN_CANCEL_REASON_CHARS:
        raise CommerceError(
            "justificativa_curta", f"Informe uma justificativa com pelo menos {MIN_CANCEL_REASON_CHARS} caracteres.", 422, field="reason"
        )
    inv = get_invoice(db, org_id, invoice_id)
    if inv["status"] != InvoiceStatus.AUTHORIZED.value:
        raise conflict("nota_nao_cancelavel", "Só uma nota autorizada pode ser cancelada.")
    if not inv.get("cancel_requested_at"):
        inv = _update(db, org_id, inv["id"], {"cancel_reason": why[:255], "cancel_requested_at": now_iso()})
    await jobs.enqueue(
        type=CANCEL_JOB,
        payload={"org_id": str(org_id), "invoice_id": str(inv["id"])},
        max_retries=INVOICE_RETRY_POLICY.max_retries,
        dedupe_key=f"{inv['ref']}:cancel",
    )
    return inv


async def document_url(cfg: CommerceConfig, storage: StorageBackend, db: Any, org_id: Any, invoice_id: Any, fmt: str) -> dict:
    """A short-lived signed URL for the private PDF / XML copy."""
    inv = get_invoice(db, org_id, invoice_id)
    key = inv.get("pdf_path" if fmt == "pdf" else "xml_path")
    if fmt not in ("pdf", "xml") or not key:
        raise not_found("Documento")
    ttl = min(DOCUMENT_URL_TTL_SECONDS, cfg.signed_url_ttl_seconds)  # dedicated, short: fiscal documents carry PII
    url = await storage.signed_url(bucket=cfg.bucket, key=key, expires_in_seconds=ttl)
    return {"url": url, "expires_in": ttl}


# ─── building the provider request ───────────────────────────────────────


def _allocate_discount(totals: list[int], discount: int) -> list[int]:
    """Spread `discount` over `totals` pro rata; the last line absorbs the rounding remainder."""
    gross = sum(totals)
    if discount <= 0 or gross <= 0:
        return list(totals)
    out, spent = [], 0
    for i, total in enumerate(totals):
        share = discount - spent if i == len(totals) - 1 else (discount * total) // gross
        spent += share
        out.append(max(total - share, 0))
    return out


def build_request(
    db: Any, org_id: Any, order: Mapping[str, Any], inv: Mapping[str, Any], profile: Mapping[str, Any], company_ref: str
) -> Optional[InvoiceRequest]:
    """The provider request for `inv`, or None when the buyer has no tax document (cannot be issued)."""
    kind = InvoiceKind(inv["kind"])
    lines = plan_invoices(db, org_id, order["id"], profile).get(kind, [])
    customer = get_row(db, "commerce_customers", org_id, order["customer_id"]) or {}
    doc = digits(order.get("buyer_doc") or customer.get("doc"))
    if not doc or not lines:
        return None
    all_items = list_items(db, org_id, order["id"])
    gross_all = sum(int(i["total_cents"]) for i in all_items) or 1
    order_discount = int(order.get("discount_cents") or 0)
    kind_gross = sum(int(i["total_cents"]) for i in lines)
    kind_discount = (order_discount * kind_gross) // gross_all
    nets = _allocate_discount([int(i["total_cents"]) for i in lines], kind_discount)
    items = []
    for line, net in zip(lines, nets):
        fiscal = ((line.get("_product") or {}).get("attributes") or {}).get("fiscal") or {}
        qty = int(line["qty"])
        items.append(
            InvoiceItem(
                description=str(line["title_snapshot"]),
                quantity=qty,
                unit_cents=round(net / qty),
                total_cents=net,
                service_code=str(fiscal.get("service_code", "")),
                nbs_code=str(fiscal.get("nbs_code", "")),
                cfop=str(fiscal.get("cfop", "")),
                ncm=str(fiscal.get("ncm", "")),
                c_class_trib=str(fiscal.get("c_class_trib", "")),
            )
        )
    addr = customer.get("address") or {}
    paid = order.get("paid_at")
    competence = date.fromisoformat(str(paid)[:10]) if paid else now().date()
    return InvoiceRequest(
        ref=inv["ref"],
        kind=kind,
        company_ref=company_ref,
        issued_on=now(),
        competence=competence,
        taker=InvoiceTaker(
            name=str(order.get("buyer_name") or customer.get("name") or ""),
            doc=doc,
            email=str(customer.get("email") or ""),
            address=Address(
                street=str(addr.get("street", "")),
                number=str(addr.get("number", "")),
                complement=str(addr.get("complement", "")),
                district=str(addr.get("district", "")),
                city=str(addr.get("city", "")),
                city_ibge=str(addr.get("city_ibge", "")),
                state=str(addr.get("state", "")),
                zip_code=digits(str(addr.get("zip_code", ""))),
            ),
        ),
        items=items,
        total_cents=sum(i.total_cents for i in items),
        additional_info=f"Pedido {order['id']}",
    )


# ─── reconcile: provider truth -> row ────────────────────────────────────


def _rejection(op: str, *, code: Optional[str], reasons: list[str]) -> dict:
    return {"op": op, "code": code, "reasons": [str(r)[:300] for r in reasons[:10]], "at": now_iso()}


async def alert_staff(rt: InvoiceRuntime, db: Any, org_id: Any, inv: Mapping[str, Any], rejection: Mapping[str, Any]) -> bool:
    """E-mail the store's contact about a refused / failed document. Failure to alert is LOGGED
    (visible), never raised -- it must not undo the state we just recorded."""
    profile = get_profile(db, org_id) or {}
    to = profile.get("contact_email")
    if rt.mailer is None or not to:
        logger.warning("commerce invoice %s needs attention but no alert channel is configured (org=%s)", inv["ref"], org_id)
        return False
    what = "o cancelamento da nota" if rejection.get("op") == "cancel" else "a emissão da nota"
    body = (
        f"Não foi possível concluir {what} {inv['ref']} (pedido {inv['order_id']}).\n\n"
        f"Motivo informado pelo emissor: {'; '.join(rejection.get('reasons') or []) or rejection.get('code') or 'indisponível'}.\n\n"
        "Abra o pedido no painel para corrigir os dados e tentar novamente."
    )
    try:
        await rt.mailer.send(OutgoingEmail(to=[str(to)], subject="Atenção: nota fiscal não concluída", text=body))
    except Exception:  # noqa: BLE001 - alerting is best-effort by design; logged, not silent
        logger.warning("commerce invoice alert e-mail failed (ref=%s org=%s)", inv["ref"], org_id, exc_info=False)
        return False
    return True


async def copy_documents(rt: InvoiceRuntime, db: Any, org_id: Any, inv: Mapping[str, Any], result: InvoiceResult) -> dict:
    """Copy the authorized PDF + XML into the PRIVATE bucket (D30 retention); idempotent."""
    provider = rt.make_provider(str(org_id))
    patch: dict[str, Any] = {}
    # NOC-REMEDIATE[finance-attachment-download-disposition]: StorageBackend.signed_url has no download=/Content-Disposition, so the XML is stored as octet-stream (a browser will not render it inline) -- same as finance attachments; destination: the storage seam grows `signed_url(download=)`. — 2026-10-14
    for fmt, url, mime in (("pdf", result.pdf_url, "application/pdf"), ("xml", result.xml_url, "application/octet-stream")):
        column = f"{fmt}_path"
        if inv.get(column) or not url:
            continue
        data = await asyncio.to_thread(provider.fetch_document, url)
        key = f"{org_id}/invoices/{inv['id']}.{fmt}"
        await rt.storage.put(bucket=rt.cfg.bucket, key=key, data=data, content_type=mime)
        patch[column] = key
    return _update(db, org_id, inv["id"], patch) if patch else dict(inv)


async def apply_result(
    rt: InvoiceRuntime,
    db: Any,
    org_id: Any,
    inv: Mapping[str, Any],
    result: InvoiceResult,
    *,
    jobs: Optional[JobRepository] = None,
) -> dict:
    """Persist what the provider says now (monotonic -- see `_ALLOWED_MOVES`), copy the documents
    on `authorized`, alert on a fresh rejection / error, and cancel a note that was authorized for
    an order refunded in the meantime."""
    new = result.status.value
    if new not in _ALLOWED_MOVES.get(inv["status"], frozenset()):
        logger.info("commerce invoice %s: ignoring provider move %s -> %s", inv["ref"], inv["status"], new)
        return dict(inv)
    patch: dict[str, Any] = {"status": new, "provider": rt.make_provider(str(org_id)).name}
    for col in ("number", "series", "access_key", "verification_code"):
        if getattr(result, col):
            patch[col] = getattr(result, col)
    if result.status is InvoiceStatus.AUTHORIZED:
        patch.update({"issued_at": inv.get("issued_at") or now_iso(), "rejection": None})
    elif result.status is InvoiceStatus.CANCELLED:
        patch["cancelled_at"] = inv.get("cancelled_at") or now_iso()
    elif result.status in (InvoiceStatus.REJECTED, InvoiceStatus.ERROR):
        patch["rejection"] = _rejection("issue", code=None, reasons=result.rejection_reasons)
    saved = _update(db, org_id, inv["id"], patch)
    if result.status is InvoiceStatus.AUTHORIZED:
        saved = await copy_documents(rt, db, org_id, saved, result)
        order = get_order(db, org_id, saved["order_id"])
        if jobs is not None and order["status"] in _REVOKED_ORDER_STATUSES and not saved.get("cancel_requested_at"):
            saved = await request_cancel(db, org_id, saved["id"], f"Pedido {order['id']} estornado integralmente", jobs=jobs)
    elif result.status in (InvoiceStatus.REJECTED, InvoiceStatus.ERROR) and inv["status"] != new:
        await alert_staff(rt, db, org_id, saved, saved["rejection"])
    return saved


async def record_failure(
    rt: InvoiceRuntime, db: Any, org_id: Any, inv: Mapping[str, Any], *, op: str, code: Optional[str], reasons: list[str], status: Optional[InvoiceStatus]
) -> dict:
    """A refusal / permanent failure: `rejection` (+ the new status for an issue) and a staff alert.
    A refused CANCEL leaves the note `authorized` (it still is) and only records why."""
    patch: dict[str, Any] = {"rejection": _rejection(op, code=code, reasons=reasons)}
    if status is not None:
        patch["status"] = status.value
    saved = _update(db, org_id, inv["id"], patch)
    await alert_staff(rt, db, org_id, saved, saved["rejection"])
    return saved


# ─── job handlers ────────────────────────────────────────────────────────

JobHandler = Callable[[Job], Any]


def _is_last_attempt(job: Job, policy: RetryPolicy) -> bool:
    return job.retry_count >= policy.max_retries


def _age(since: Any) -> timedelta:
    if not since:
        return timedelta(0)
    return now() - datetime.fromisoformat(str(since).replace("Z", "+00:00"))


def make_invoice_job_handlers(
    cfg: CommerceConfig,
    *,
    get_db: Callable[[], Any],
    make_provider: Callable[[str], InvoiceProvider],
    get_storage: Callable[[], StorageBackend],
    get_jobs: Callable[[], JobRepository],
    get_mailer: Optional[Callable[[], Optional[EmailSender]]] = None,
    retry_policy: RetryPolicy = INVOICE_RETRY_POLICY,
) -> dict[str, JobHandler]:
    """`{job type: async handler}` for `domain.jobs.Worker(handlers=..., retry_policy=retry_policy)`.

    Plain callables (not FastAPI deps): a worker has no request. `get_db` returns the product's
    schema-scoped client; `make_provider(org_id)` builds ONE provider per org/call.
    """

    def runtime() -> InvoiceRuntime:
        return InvoiceRuntime(cfg, make_provider, get_storage(), get_mailer() if get_mailer else None)

    async def issue(job: Job) -> None:
        org_id, invoice_id = job.payload["org_id"], job.payload["invoice_id"]
        db, rt = get_db(), runtime()
        inv = get_row(db, INVOICES, org_id, invoice_id)
        if inv is None:
            raise DeadLetterError(f"invoice {invoice_id} not found")
        if inv["status"] in (InvoiceStatus.REJECTED.value, InvoiceStatus.ERROR.value, InvoiceStatus.CANCELLED.value):
            return  # a staff retry registers a NEW row; nothing for this job to do
        try:
            if inv["status"] == InvoiceStatus.AUTHORIZED.value:  # a retry after a failed document copy
                provider = make_provider(str(org_id))
                result = await asyncio.to_thread(provider.get, InvoiceKind(inv["kind"]), inv["ref"], company_ref=company_ref_of(get_profile(db, org_id)))
                await copy_documents(rt, db, org_id, inv, result)
                return
            order = get_order(db, org_id, inv["order_id"])
            profile = get_profile(db, org_id) or {}
            company_ref = company_ref_of(profile)
            request = build_request(db, org_id, order, inv, profile, company_ref) if company_ref else None
            if request is None:
                why = "empresa fiscal nao cadastrada" if not company_ref else "comprador sem CPF/CNPJ ou pedido sem itens da nota"
                await record_failure(rt, db, org_id, inv, op="issue", code="dados_incompletos", reasons=[why], status=InvoiceStatus.REJECTED)
                return
            provider = make_provider(str(org_id))
            try:
                result = await asyncio.to_thread(provider.issue, request)
            except InvoiceProviderError as exc:
                if exc.retryable:
                    raise
                await record_failure(rt, db, org_id, inv, op="issue", code=exc.code, reasons=exc.reasons or [exc.message], status=InvoiceStatus.REJECTED)
                return
            saved = await apply_result(rt, db, org_id, inv, result, jobs=get_jobs())
            if saved["status"] == InvoiceStatus.PROCESSING.value:
                if _age(inv.get("created_at")) > PROCESSING_MAX_AGE:
                    await record_failure(rt, db, org_id, inv, op="issue", code="timeout", reasons=["o emissor nao concluiu a nota no prazo"], status=InvoiceStatus.ERROR)
                    return
                raise RescheduleLater(POLL_DELAY_SECONDS, "invoice still processing at the provider")
        except (RescheduleLater, DeadLetterError):
            raise
        except Exception:
            if _is_last_attempt(job, retry_policy):
                fresh = get_row(db, INVOICES, org_id, invoice_id) or inv
                await record_failure(rt, db, org_id, fresh, op="issue", code="falhas_repetidas", reasons=["o emissor ficou indisponivel; tente de novo mais tarde"], status=InvoiceStatus.ERROR)
                raise DeadLetterError("invoice issue failed after the last retry") from None
            raise

    async def cancel(job: Job) -> None:
        org_id, invoice_id = job.payload["org_id"], job.payload["invoice_id"]
        db, rt = get_db(), runtime()
        inv = get_row(db, INVOICES, org_id, invoice_id)
        if inv is None:
            raise DeadLetterError(f"invoice {invoice_id} not found")
        if inv["status"] != InvoiceStatus.AUTHORIZED.value:
            return  # already cancelled / never authorized: idempotent
        try:
            provider = make_provider(str(org_id))
            company_ref = company_ref_of(get_profile(db, org_id))
            try:
                result = await asyncio.to_thread(
                    provider.cancel, InvoiceKind(inv["kind"]), inv["ref"], reason=inv.get("cancel_reason") or "", company_ref=company_ref
                )
            except InvoiceProviderError as exc:
                if exc.retryable:
                    raise
                await record_failure(rt, db, org_id, inv, op="cancel", code=exc.code, reasons=exc.reasons or [exc.message], status=None)
                return
            if result.status is InvoiceStatus.CANCELLED:
                await apply_result(rt, db, org_id, inv, result)
                return
            if _age(inv.get("cancel_requested_at")) > PROCESSING_MAX_AGE:
                await record_failure(rt, db, org_id, inv, op="cancel", code="timeout", reasons=["o emissor nao concluiu o cancelamento no prazo"], status=None)
                return
            raise RescheduleLater(POLL_DELAY_SECONDS, "cancel still processing at the provider")
        except (RescheduleLater, DeadLetterError):
            raise
        except Exception:
            if _is_last_attempt(job, retry_policy):
                await record_failure(rt, db, org_id, inv, op="cancel", code="falhas_repetidas", reasons=["o emissor ficou indisponivel; tente cancelar de novo"], status=None)
                raise DeadLetterError("invoice cancel failed after the last retry") from None
            raise

    return {ISSUE_JOB: issue, CANCEL_JOB: cancel}


# ─── webhook ─────────────────────────────────────────────────────────────

DUPLICATE = "duplicate"
IGNORED = "ignored"
PROCESSED = "processed"


async def handle_invoice_event(
    rt: InvoiceRuntime, db: Any, org_id: Any, event: InvoiceEvent, *, inbox: EventInbox, jobs: Optional[JobRepository] = None
) -> str:
    """A VERIFIED invoice webhook. The body (status hint, urls) is never trusted: the row is
    reconciled from `provider.get(kind, ref)`. A `ref` that is not THIS org's is ignored (logged)."""
    inv = get_invoice_by_ref(db, org_id, event.ref)
    if inv is None:
        logger.warning("commerce invoice webhook: ref not found for org=%s (ignored)", org_id)
        return IGNORED
    provider = rt.make_provider(str(org_id))
    # Inbox dedupe only when the delivery names a status: `(ref, status_hint)` is then a real replay
    # key. A status-less body has no honest key (a constant would swallow every later delivery for
    # the ref forever), and none is needed -- the `get()` re-read below makes processing idempotent.
    key = f"{event.ref}:{event.status_hint.value}" if event.status_hint else None
    if key is not None and not inbox.claim(gateway=provider.name, event_id=key):
        return DUPLICATE
    try:
        company_ref = company_ref_of(get_profile(db, org_id))
        result = await asyncio.to_thread(provider.get, InvoiceKind(inv["kind"]), inv["ref"], company_ref=company_ref)
        await apply_result(rt, db, org_id, inv, result, jobs=jobs)
    except Exception:
        if key is not None:
            inbox.release(gateway=provider.name, event_id=key)  # let the provider's retry through
        raise
    return PROCESSED


__all__ = [
    "CANCEL_JOB",
    "INVOICES",
    "INVOICE_RETRY_POLICY",
    "ISSUE_JOB",
    "InvoiceRuntime",
    "alert_staff",
    "apply_result",
    "build_ref",
    "build_request",
    "copy_documents",
    "document_url",
    "enqueue_pending_invoices",
    "get_invoice",
    "get_invoice_by_ref",
    "handle_invoice_event",
    "issue_for_staff",
    "issue_invoices_for_order",
    "list_invoices",
    "make_invoice_job_handlers",
    "on_order_paid",
    "on_order_revoked",
    "plan_invoices",
    "register_invoices",
    "register_on_order_paid",
    "request_cancel",
]
