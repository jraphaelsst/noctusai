"""Documents, LGPD-complete (contract §2 `055`, ruling S2 / D5).

Every read of a document's CONTENT (a minted signed URL) and every delete
appends to `cliente_documento_acessos` — the access log. Listing document
METADATA (`GET .../documentos`) or listing the access log itself
(`GET .../acessos`) does NOT append — neither one accesses the file's
bytes.

Retention is table-driven (`cliente_documento_tipos`, migration `055`),
never a hardcoded `if`: `retencao_ate` is computed once, at upload time,
from that type's `retencao_dias`. The allow-list check the upload route
enforces is `ativo = true` on that same row — enabling a withheld type
(RG/CPF-class, seeded `ativo = false`) is a data change, not a deploy.

Storage: `noctusai_lib.integrations.storage.StorageBackend` (Protocol +
Fake + Real + factory), resolved via
`app.modules.card_hub.deps.get_storage_backend`. Object path
`{org_id}/clientes/{cliente_id}/{document_id}` — see migration `055`'s
object-RLS policies for why the first path segment must always be the
literal `org_id`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.api import scheduler as seed_scheduler
from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.modules.card_hub.deps import BUCKET, get_card_hub_client
from app.modules.card_hub.services import (
    _actor,
    _paged_rows,
    _resolve_actors,
    _t,
    ensure_cliente,
)

logger = logging.getLogger(__name__)

# Conservative server-side limits (contract §3: "Limits enforced
# server-side ... A rejected upload returns a typed error naming the
# limit it hit"). Module-local constants — mirrors
# `erp-imobiliario/app/services/storage_service.py`'s `MAX_FILE_SIZE`/
# `ALLOWED_TYPES` shape rather than a new `Settings` field, since this is
# a fixed platform policy, not per-deployment configuration.
#
# 🔴 CAPPED BY A PLATFORM CONSTRAINT THIS SLICE DID NOT RAISE: every
# request in this product passes through `MaxBodySizeMiddleware`, whose
# cap is `settings.max_body_bytes` — 1 MB by default, and NOT overridden
# by `SocialWiringSettings` today (confirmed empirically: a 15 MB upload
# 413'd at the middleware, before this endpoint's own check ever ran).
# 800 KB is set here to sit safely under that 1 MB ceiling with headroom
# for multipart boundary/header overhead. A real scanned contract or a
# multi-page planta commonly exceeds 800 KB, so this is a REAL product
# limitation, not a formality — raising it requires bumping
# `settings.max_body_bytes` for the whole product (the middleware has no
# per-route override), which is a broader decision than this slice's
# scope. Surfaced in the delivery note rather than silently widening a
# platform-wide DoS guard as a side effect of one feature.
MAX_UPLOAD_BYTES = 800 * 1024  # 800 KB — see the note above
ALLOWED_MIME_TYPES = frozenset(
    {"application/pdf", "image/jpeg", "image/png", "image/webp"}
)

_SIGNED_URL_TTL_SECONDS = 300  # short TTL, minted per request (contract §2)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> "datetime.date":
    return datetime.now(timezone.utc).date()


def _require_tipo_documento(client: Any, tipo_documento: str) -> dict:
    rows = (
        _t(client, "cliente_documento_tipos")
        .select("*")
        .eq("tipo_documento", tipo_documento)
        .execute()
    ).data or []
    if not rows:
        raise ValidationError_(
            f"tipo_documento desconhecido: {tipo_documento!r}", field="tipo_documento"
        )
    row = rows[0]
    if not row.get("ativo", False):
        raise ValidationError_(
            f"tipo_documento {tipo_documento!r} não está habilitado para upload "
            "(pendente de intake LGPD)",
            field="tipo_documento",
        )
    return row


def list_tipos_documento(client: Any) -> dict:
    rows = (
        _t(client, "cliente_documento_tipos")
        .select("*")
        .eq("ativo", True)
        .execute()
    ).data or []
    items = [
        {
            "tipo_documento": r["tipo_documento"],
            "categoria_lgpd": r["categoria_lgpd"],
            "descricao": r.get("descricao"),
        }
        for r in rows
    ]
    items.sort(key=lambda t: t["tipo_documento"])
    return {"items": items, "total": len(items)}


def _documento_out(row: dict, resolved_actors: dict) -> dict:
    return {
        "id": row["id"],
        "nome_original": row["nome_original"],
        "mime_type": row["mime_type"],
        "tamanho_bytes": row["tamanho_bytes"],
        "tipo_documento": row["tipo_documento"],
        "categoria_lgpd": row["categoria_lgpd"],
        "retencao_ate": row.get("retencao_ate"),
        "enviado_por": _actor(resolved_actors, row.get("enviado_por")),
        "created_at": row["created_at"],
        # No thumbnail pipeline in this slice (no image-processing step
        # exists anywhere in this product yet) — always `None`, which the
        # contract's `|null` shape explicitly allows. Not a silent gap:
        # surfaced in the delivery note, not hidden behind a fabricated URL.
        "thumbnail_url": None,
    }


def list_documentos(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    ensure_cliente(client, org_id, cliente_id)
    rows = _paged_rows(
        client,
        "cliente_documentos",
        org_id,
        eq_filters={"cliente_id": str(cliente_id)},
        extra=lambda q: q.is_("deleted_at", "null"),
    )
    resolved = _resolve_actors({r["enviado_por"] for r in rows if r.get("enviado_por")})
    items = [_documento_out(r, resolved) for r in rows]
    items.sort(key=lambda d: d["created_at"], reverse=True)
    return {"items": items, "total": len(items)}


async def upload_documento(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    cliente_id: UUID,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    tipo_documento: str,
    enviado_por: Optional[UUID],
) -> dict:
    ensure_cliente(client, org_id, cliente_id)

    if content_type not in ALLOWED_MIME_TYPES:
        raise ValidationError_(
            f"Tipo de arquivo não permitido: {content_type}. "
            f"Permitidos: {', '.join(sorted(ALLOWED_MIME_TYPES))}",
            field="mime_type",
        )
    if len(data) > MAX_UPLOAD_BYTES:
        max_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise ValidationError_(
            f"Arquivo excede o limite de {max_mb}MB ({len(data) // (1024 * 1024)}MB enviado)",
            field="tamanho_bytes",
        )

    tipo_row = _require_tipo_documento(client, tipo_documento)

    document_id = uuid4()
    storage_path = f"{org_id}/clientes/{cliente_id}/{document_id}"
    await storage.put(
        bucket=BUCKET,
        key=storage_path,
        data=data,
        content_type=content_type,
        metadata={"nome_original": filename},
    )

    retencao_dias = tipo_row.get("retencao_dias")
    retencao_ate = (
        (_today() + timedelta(days=retencao_dias)).isoformat() if retencao_dias else None
    )

    row = {
        "id": str(document_id),
        "org_id": str(org_id),
        "cliente_id": str(cliente_id),
        "storage_path": storage_path,
        "nome_original": filename,
        "mime_type": content_type,
        "tamanho_bytes": len(data),
        "tipo_documento": tipo_documento,
        "categoria_lgpd": tipo_row["categoria_lgpd"],
        "retencao_ate": retencao_ate,
        "enviado_por": str(enviado_por) if enviado_por else None,
        "deleted_at": None,
        "delete_motivo": None,
        "delete_solicitado_por": None,
        "created_at": _now(),
    }
    _t(client, "cliente_documentos").insert(row).execute()
    resolved = _resolve_actors({row["enviado_por"]} if row["enviado_por"] else set())
    return _documento_out(row, resolved)


def _require_documento(client: Any, org_id: UUID, cliente_id: UUID, documento_id: UUID) -> dict:
    rows = (
        _t(client, "cliente_documentos")
        .select("*")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .eq("id", str(documento_id))
        .execute()
    ).data or []
    if not rows or rows[0].get("deleted_at"):
        raise NotFoundError("cliente_documentos", str(documento_id))
    return rows[0]


def _log_acesso(client: Any, org_id: UUID, documento_id: UUID, usuario_id: Optional[UUID], acao: str) -> None:
    _t(client, "cliente_documento_acessos").insert(
        {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "documento_id": str(documento_id),
            "usuario_id": str(usuario_id) if usuario_id else None,
            "acao": acao,
            "created_at": _now(),
        }
    ).execute()


async def get_documento_url(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    cliente_id: UUID,
    documento_id: UUID,
    *,
    usuario_id: Optional[UUID],
    intent: str = "view",
) -> dict:
    """Mints a short-TTL signed URL and appends to the access log.

    `intent` selects the logged `acao` (`'view'` or `'download'`) — the
    contract names one endpoint (`GET .../url`) but requires BOTH actions
    to be loggable; a query param is the smallest surface that satisfies
    both without inventing a second route. Surfaced in the delivery note
    as an interpretation call."""
    if intent not in ("view", "download"):
        raise ValidationError_(f"intent inválido: {intent!r}", field="intent")
    documento = _require_documento(client, org_id, cliente_id, documento_id)
    url = await storage.signed_url(
        bucket=BUCKET, key=documento["storage_path"], expires_in_seconds=_SIGNED_URL_TTL_SECONDS
    )
    _log_acesso(client, org_id, documento_id, usuario_id, intent)
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=_SIGNED_URL_TTL_SECONDS)
    ).isoformat()
    return {"url": url, "expires_at": expires_at}


async def delete_documento(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    cliente_id: UUID,
    documento_id: UUID,
    *,
    motivo: str,
    usuario_id: Optional[UUID],
) -> None:
    documento = _require_documento(client, org_id, cliente_id, documento_id)
    _t(client, "cliente_documentos").update(
        {
            "deleted_at": _now(),
            "delete_motivo": motivo,
            "delete_solicitado_por": str(usuario_id) if usuario_id else None,
        }
    ).eq("id", str(documento_id)).execute()
    _log_acesso(client, org_id, documento_id, usuario_id, "delete")


def list_acessos(client: Any, org_id: UUID, cliente_id: UUID, documento_id: UUID) -> dict:
    # `_require_documento` would reject an already-soft-deleted document,
    # but its access log (including its own delete entry) must remain
    # readable — soft-delete is not erasure. A lighter existence check
    # (any row, deleted or not) is used here instead.
    exists = (
        _t(client, "cliente_documentos")
        .select("id")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .eq("id", str(documento_id))
        .execute()
    ).data or []
    if not exists:
        raise NotFoundError("cliente_documentos", str(documento_id))

    # An access log for one document can genuinely grow large over years
    # of view/download/delete traffic — paged, never a bare `.execute()`.
    rows = _paged_rows(
        client, "cliente_documento_acessos", org_id, eq_filters={"documento_id": str(documento_id)}
    )
    resolved = _resolve_actors({r["usuario_id"] for r in rows if r.get("usuario_id")})
    items = [
        {
            "id": r["id"],
            "usuario": _actor(resolved, r.get("usuario_id")),
            "acao": r["acao"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    items.sort(key=lambda a: a["created_at"], reverse=True)
    return {"items": items, "total": len(items)}


# ─── Retention sweep ──────────────────────────────────────────────────


def run_retention_sweep(client: Any, org_id: UUID) -> int:
    """Soft-deletes every non-deleted document past its `retencao_ate`
    date for `org_id`, appending a `delete` access-log entry attributed
    to no user (`usuario_id=None` — a system action, not a person's).
    Returns the count swept. Table-driven: the caller never encodes a
    per-type policy — `retencao_ate` was already computed at upload time
    from `cliente_documento_tipos`."""
    today = _today().isoformat()
    rows = (
        _t(client, "cliente_documentos")
        .select("id")
        .eq("org_id", str(org_id))
        .is_("deleted_at", "null")
        .lte("retencao_ate", today)
        .execute()
    ).data or []
    for row in rows:
        _t(client, "cliente_documentos").update(
            {
                "deleted_at": _now(),
                "delete_motivo": "retenção expirada (sweep automático)",
                "delete_solicitado_por": None,
            }
        ).eq("id", row["id"]).execute()
        _log_acesso(client, org_id, UUID(row["id"]), None, "delete")
    return len(rows)


def _list_org_ids(client: Any) -> list[UUID]:
    """Every org owning at least one `cliente_documentos` row — mirrors
    `app.services.clientes_backfill_job._list_org_ids`'s shape (single
    read column, paged, dedup in Python — PostgREST has no DISTINCT),
    composing the seed's shared pager instead of a hand-rolled loop."""

    def fetch_page(start: int, end: int):
        return _t(client, "cliente_documentos").select("org_id").order("id").range(start, end).execute().data

    seen: set[str] = set()
    for row in iter_paged_rows(fetch_page, label="cliente_documentos org_id scan"):
        if row.get("org_id"):
            seen.add(str(row["org_id"]))
    return [UUID(o) for o in sorted(seen)]


def run_retention_sweep_all_orgs(*, client: Any = None) -> int:
    """The scheduled sweep's body — every org, one pass. Returns the
    total rows swept across all orgs."""
    resolved_client = client or get_card_hub_client()
    total = 0
    for org_id in _list_org_ids(resolved_client):
        total += run_retention_sweep(resolved_client, org_id)
    return total


def _run_retention_sweep_job(*, run_fn: Any = None) -> None:
    """Scheduler entrypoint — swallows ALL exceptions so a bug in one run
    never crashes the scheduler or de-registers the job (mirrors
    `clientes_backfill_job._run_clientes_backfill_job`'s identical
    shape). `run_fn` is the test seam."""
    try:
        (run_fn or run_retention_sweep_all_orgs)()
    except Exception:
        logger.error("card_hub.documentos: retention sweep failed", exc_info=True)


def configure(*, scheduler: Any = None) -> None:
    """Register the retention sweep on the seed-side scheduler. Called
    from `app.modules.card_hub.register()` at import time, before
    `start_scheduler()` fires in `app/lifespan.py` — mirrors
    `clientes_backfill_job.configure()`'s identical shape. A fixed 24h
    interval (module-local, not a `Settings` field — this is a platform
    policy, not per-deployment configuration)."""
    (scheduler or seed_scheduler).register(
        "card_hub_documento_retention_sweep",
        _run_retention_sweep_job,
        hours=24,
    )
    logger.info("card_hub retention sweep scheduler configured: every 24h")


__all__ = [
    "ALLOWED_MIME_TYPES",
    "MAX_UPLOAD_BYTES",
    "configure",
    "delete_documento",
    "get_documento_url",
    "list_acessos",
    "list_documentos",
    "list_tipos_documento",
    "run_retention_sweep",
    "run_retention_sweep_all_orgs",
    "upload_documento",
]
