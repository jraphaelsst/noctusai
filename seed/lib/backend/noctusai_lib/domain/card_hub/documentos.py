"""Card documents, LGPD-complete.

Lifted from social-wiring's `app/modules/card_hub/documentos_service.py`
(migration 057, ruling S2 / D5 — "no attachments now, governance later" was
refused: object RLS, per-type retention, delete-on-request and the access log
land together or not at all).

WHAT IS LOGGED
--------------
Every read of a document's CONTENT (a minted signed URL, `view` or
`download`) and every delete appends to the `documento_acessos` table.
Listing METADATA, or listing the access log itself, does not — neither
touches the file's bytes. The log is append-only by construction: no route
offers a mutation on it.

RETENTION
---------
Table-driven, never a hardcoded `if`: `retencao_ate` is stamped once, at
upload, from the type's retention (the catalogue's `retencao_dias`, or the
product's `DocumentoPolicy.retention_days` resolver). The upload allow-list is
the catalogue's `ativo = true` — enabling a withheld identity-class type is a
data change, never a deploy.

🔴 The scheduled sweep is registered EXPLICITLY (`register_retention_sweep`),
never as an import side effect: importing a module must not mutate a
process-global scheduler, and a product that mounts two card hubs must be able
to see — and name — both jobs.

STORAGE KEYS
------------
`{org_id}/{storage_segment}/{entity_id}/{document_id}`. The FIRST segment is
always the literal `org_id` — the object-RLS policies match on it, and a key
shaped otherwise is readable across orgs.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.persistence.table_reads import actor, paged_rows, table
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from .config import CardHubConfig
from .services import ensure_entity, now_iso

logger = logging.getLogger(__name__)

#: The `delete_motivo` a retention-sweep delete records.
RETENTION_SWEEP_MOTIVO = "retenção expirada (sweep automático)"


def today() -> date:
    """UTC today — the upload stamp and the sweep compare against the SAME
    clock, so both halves of retention agree on what "today" is."""
    return datetime.now(timezone.utc).date()


def format_bytes_human(n: int) -> str:
    """Human-readable byte count for a user-facing limit message.

    Never integer-divides to a misleading "0MB" — an 800 KB cap's
    `n // (1024*1024)` is 0, and "excede o limite de 0MB" reads as a broken
    feature rather than a real limit. MB with one decimal at/above 1 MB; whole
    KB below.
    """
    mb = n / (1024 * 1024)
    if mb >= 1:
        return f"{mb:.1f}MB"
    return f"{n / 1024:.0f}KB"


# ─── the type catalogue ──────────────────────────────────────────────────


def _require_tipo_documento(cfg: CardHubConfig, db: Any, tipo_documento: str) -> dict:
    rows = (
        table(db, cfg.tables.documento_tipos)
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


def list_tipos_documento(cfg: CardHubConfig, db: Any) -> dict:
    """The ENABLED types — the upload picker's options. A platform-wide
    taxonomy (no `org_id`), readable like an enum."""
    rows = (
        table(db, cfg.tables.documento_tipos)
        .select("*")
        .eq("ativo", True)
        .execute()
    ).data or []
    items = [
        {
            "tipo_documento": r["tipo_documento"],
            "categoria_lgpd": r["categoria_lgpd"],
            "descricao": r.get("descricao"),
            # Lets a picker group/flag identity types instead of guessing off
            # `categoria_lgpd` string-matching.
            "identidade": bool(r.get("identidade", False)),
        }
        for r in rows
    ]
    items.sort(key=lambda t: t["tipo_documento"])
    return {"items": items, "total": len(items)}


# ─── projections ─────────────────────────────────────────────────────────

#: The columns a checklist line needs to NAME the document satisfying it —
#: narrower than `documento_out` on purpose (no retention, no actor
#: resolution across a second schema client, no signed URL).
DOCUMENTO_RESUMO_COLUNAS = (
    "id",
    "nome_original",
    "mime_type",
    "tamanho_bytes",
    "created_at",
)


def documento_resumo(row: Optional[dict]) -> Optional[dict]:
    """The document summary a checklist line carries, or `None`.

    ONE definition for every checklist surface that points at a document, so
    the frontend renders them through one row component. `.get()` throughout:
    a caller may hand over a row it selected narrowly.
    """
    if row is None:
        return None
    return {key: row.get(key) for key in DOCUMENTO_RESUMO_COLUNAS}


def documento_base(row: dict, resolved_actors: dict) -> dict:
    """The 7-field core every documento-listing surface starts from — identity,
    the file's own metadata, WHO sent it (a resolved `{id, nome}`, never the
    raw id) and WHEN."""
    return {
        "id": row["id"],
        "nome_original": row["nome_original"],
        "mime_type": row["mime_type"],
        "tamanho_bytes": row["tamanho_bytes"],
        "tipo_documento": row["tipo_documento"],
        "enviado_por": actor(resolved_actors, row.get("enviado_por")),
        "created_at": row["created_at"],
    }


def documento_out(cfg: CardHubConfig, row: dict, resolved_actors: dict) -> dict:
    out = {
        **documento_base(row, resolved_actors),
        "categoria_lgpd": row["categoria_lgpd"],
        "retencao_ate": row.get("retencao_ate"),
        # No thumbnail pipeline exists — always `None`, which the contract's
        # `|null` shape allows. Never a fabricated URL.
        "thumbnail_url": None,
    }
    if cfg.documentos.extra_out_fields is not None:
        out.update(cfg.documentos.extra_out_fields(row))
    return out


# ─── reads ───────────────────────────────────────────────────────────────


def list_documentos(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID) -> dict:
    """Live documents, newest first. A soft-deleted row is excluded HERE,
    once — a list that forgot would show a document the user believes they
    deleted."""
    ensure_entity(cfg, db, org_id, entity_id)
    rows = paged_rows(
        db,
        cfg.tables.documentos,
        org_id,
        eq_filters={cfg.entity_fk: str(entity_id)},
        refine=lambda q: q.is_("deleted_at", "null"),
    )
    resolved = cfg.actor_resolver({r["enviado_por"] for r in rows if r.get("enviado_por")})
    items = [documento_out(cfg, r, resolved) for r in rows]
    items.sort(key=lambda d: d["created_at"], reverse=True)
    return {"items": items, "total": len(items)}


def require_documento(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID, documento_id: UUID) -> dict:
    """The live row, proven to belong to THIS entity — or a 404."""
    rows = (
        table(db, cfg.tables.documentos)
        .select("*")
        .eq("org_id", str(org_id))
        .eq(cfg.entity_fk, str(entity_id))
        .eq("id", str(documento_id))
        .execute()
    ).data or []
    if not rows or rows[0].get("deleted_at"):
        raise NotFoundError(cfg.tables.documentos, str(documento_id))
    return rows[0]


# ─── writes ──────────────────────────────────────────────────────────────


def _retencao_dias(cfg: CardHubConfig, db: Any, org_id: UUID, tipo_documento: str, tipo_row: dict) -> Optional[int]:
    hook = cfg.documentos.retention_days
    if hook is not None:
        return hook(db, org_id, tipo_documento, tipo_row)
    return tipo_row.get("retencao_dias")


async def upload_documento(
    cfg: CardHubConfig,
    db: Any,
    storage: StorageBackend,
    org_id: UUID,
    entity_id: UUID,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    tipo_documento: str,
    enviado_por: Optional[UUID],
    max_bytes: Optional[int] = None,
) -> dict:
    """Validate → put → insert. Refusals name the limit they hit (400).

    `max_bytes` overrides `cfg.documentos.max_upload_bytes` for this call — a
    PARAMETER so no test ever has to monkeypatch the configured value (a
    patched guard is a guard the test invented, not the one production runs).
    """
    ensure_entity(cfg, db, org_id, entity_id)
    policy = cfg.documentos
    limite = policy.max_upload_bytes if max_bytes is None else max_bytes

    if content_type not in policy.allowed_mime_types:
        raise ValidationError_(
            f"Tipo de arquivo não permitido: {content_type}. "
            f"Permitidos: {', '.join(sorted(policy.allowed_mime_types))}",
            field="mime_type",
        )
    if len(data) > limite:
        raise ValidationError_(
            f"Arquivo excede o limite de {format_bytes_human(limite)} "
            f"({format_bytes_human(len(data))} enviado)",
            field="tamanho_bytes",
        )

    tipo_row = _require_tipo_documento(cfg, db, tipo_documento)

    document_id = uuid4()
    storage_path = f"{org_id}/{cfg.storage_segment}/{entity_id}/{document_id}"
    await storage.put(
        bucket=cfg.bucket,
        key=storage_path,
        data=data,
        content_type=content_type,
        metadata={"nome_original": filename},
    )

    retencao_dias = _retencao_dias(cfg, db, org_id, tipo_documento, tipo_row)
    retencao_ate = (
        (today() + timedelta(days=retencao_dias)).isoformat() if retencao_dias else None
    )

    row = {
        "id": str(document_id),
        "org_id": str(org_id),
        cfg.entity_fk: str(entity_id),
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
        "created_at": now_iso(),
    }
    if policy.extra_insert_fields is not None:
        row.update(policy.extra_insert_fields(tipo_documento))
    table(db, cfg.tables.documentos).insert(row).execute()
    resolved = cfg.actor_resolver({row["enviado_por"]} if row["enviado_por"] else set())
    return documento_out(cfg, row, resolved)


def log_acesso(
    cfg: CardHubConfig, db: Any, org_id: UUID, documento_id: UUID, usuario_id: Optional[UUID], acao: str
) -> None:
    """Append one access-log row (`view` / `download` / `delete`)."""
    table(db, cfg.tables.documento_acessos).insert(
        {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "documento_id": str(documento_id),
            "usuario_id": str(usuario_id) if usuario_id else None,
            "acao": acao,
            "created_at": now_iso(),
        }
    ).execute()


async def get_documento_url(
    cfg: CardHubConfig,
    db: Any,
    storage: StorageBackend,
    org_id: UUID,
    entity_id: UUID,
    documento_id: UUID,
    *,
    usuario_id: Optional[UUID],
    intent: str = "view",
) -> dict:
    """Mint a short-TTL signed URL and append to the access log.

    `intent` selects the logged `acao` (`view` / `download`) — one endpoint,
    both actions loggable.
    """
    if intent not in ("view", "download"):
        raise ValidationError_(f"intent inválido: {intent!r}", field="intent")
    documento = require_documento(cfg, db, org_id, entity_id, documento_id)
    ttl = cfg.documentos.signed_url_ttl_seconds
    url = await storage.signed_url(
        bucket=cfg.bucket, key=documento["storage_path"], expires_in_seconds=ttl
    )
    log_acesso(cfg, db, org_id, documento_id, usuario_id, intent)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat()
    return {"url": url, "expires_at": expires_at}


async def delete_documento(
    cfg: CardHubConfig,
    db: Any,
    storage: StorageBackend,
    org_id: UUID,
    entity_id: UUID,
    documento_id: UUID,
    *,
    motivo: str,
    usuario_id: Optional[UUID],
) -> None:
    """Soft delete with a recorded reason + a `delete` access-log entry. An
    LGPD delete without a reason is not an LGPD delete (the route makes
    `motivo` a REQUIRED query param)."""
    require_documento(cfg, db, org_id, entity_id, documento_id)
    table(db, cfg.tables.documentos).update(
        {
            "deleted_at": now_iso(),
            "delete_motivo": motivo,
            "delete_solicitado_por": str(usuario_id) if usuario_id else None,
        }
    ).eq("id", str(documento_id)).execute()
    log_acesso(cfg, db, org_id, documento_id, usuario_id, "delete")


def list_acessos(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID, documento_id: UUID) -> dict:
    """The access log for one document, newest first.

    Deliberately NOT `require_documento`: a soft-deleted document's log —
    including its own delete entry — must stay readable. Soft delete is not
    erasure.
    """
    exists = (
        table(db, cfg.tables.documentos)
        .select("id")
        .eq("org_id", str(org_id))
        .eq(cfg.entity_fk, str(entity_id))
        .eq("id", str(documento_id))
        .execute()
    ).data or []
    if not exists:
        raise NotFoundError(cfg.tables.documentos, str(documento_id))

    rows = paged_rows(
        db, cfg.tables.documento_acessos, org_id, eq_filters={"documento_id": str(documento_id)}
    )
    resolved = cfg.actor_resolver({r["usuario_id"] for r in rows if r.get("usuario_id")})
    items = [
        {
            "id": r["id"],
            "usuario": actor(resolved, r.get("usuario_id")),
            "acao": r["acao"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    items.sort(key=lambda a: a["created_at"], reverse=True)
    return {"items": items, "total": len(items)}


# ─── retention sweep ─────────────────────────────────────────────────────


def run_retention_sweep(cfg: CardHubConfig, db: Any, org_id: UUID) -> int:
    """Soft-delete every live document of `org_id` past its `retencao_ate`,
    logging a `delete` attributed to NO user (a system action — attributing it
    to a person would put a deletion in their audit trail they did not make).
    Returns the count swept."""
    rows = (
        table(db, cfg.tables.documentos)
        .select("id")
        .eq("org_id", str(org_id))
        .is_("deleted_at", "null")
        .lte("retencao_ate", today().isoformat())
        .execute()
    ).data or []
    for row in rows:
        table(db, cfg.tables.documentos).update(
            {
                "deleted_at": now_iso(),
                "delete_motivo": RETENTION_SWEEP_MOTIVO,
                "delete_solicitado_por": None,
            }
        ).eq("id", row["id"]).execute()
        log_acesso(cfg, db, org_id, UUID(row["id"]), None, "delete")
    return len(rows)


def list_document_org_ids(cfg: CardHubConfig, db: Any) -> list[UUID]:
    """Every org owning at least one document row (single column, paged,
    dedup in Python — PostgREST has no DISTINCT)."""

    def fetch_page(start: int, end: int):
        return table(db, cfg.tables.documentos).select("org_id").order("id").range(start, end).execute().data

    seen: set[str] = set()
    for row in iter_paged_rows(fetch_page, label=f"{cfg.tables.documentos} org_id scan"):
        if row.get("org_id"):
            seen.add(str(row["org_id"]))
    return [UUID(o) for o in sorted(seen)]


def run_retention_sweep_all_orgs(cfg: CardHubConfig, db: Any) -> int:
    """The scheduled sweep's body — every org, one pass."""
    total = 0
    for org_id in list_document_org_ids(cfg, db):
        total += run_retention_sweep(cfg, db, org_id)
    return total


def default_retention_job_id(cfg: CardHubConfig) -> str:
    return f"card_hub_{cfg.entity_kind}_documento_retention_sweep"


def register_retention_sweep(
    cfg: CardHubConfig,
    *,
    get_db: Callable[[], Any],
    scheduler: Any = None,
    job_id: Optional[str] = None,
    hours: int = 24,
    run_fn: Optional[Callable[[], Any]] = None,
) -> str:
    """Register the retention sweep on the seed scheduler. EXPLICIT — call it
    from the product's module registration, before `start_scheduler()`.

    `get_db` is called PER RUN (never captured), so a sweep always reads
    through whatever client the process currently resolves. `job_id` must be
    stable across releases: re-registering the same id replaces the job
    (idempotent), a changed id would register a second sweep. Default
    `card_hub_<entity_kind>_documento_retention_sweep`; a product that already
    shipped a job under another id passes it. `run_fn` replaces the job body
    (a test seam — the default is `run_retention_sweep_all_orgs(cfg,
    get_db())`). Returns the job id.

    The job swallows (and LOGS, with traceback) every exception: one failed run
    must never crash the scheduler or de-register the job.
    """
    from noctusai_lib.api import scheduler as seed_scheduler

    name = job_id or default_retention_job_id(cfg)

    def _job() -> None:
        try:
            if run_fn is not None:
                run_fn()
            else:
                run_retention_sweep_all_orgs(cfg, get_db())
        except Exception:
            logger.error("card_hub.documentos: retention sweep %s failed", name, exc_info=True)

    (scheduler or seed_scheduler).register(name, _job, hours=hours)
    logger.info("card_hub retention sweep %s configured: every %sh", name, hours)
    return name


__all__ = [
    "DOCUMENTO_RESUMO_COLUNAS",
    "RETENTION_SWEEP_MOTIVO",
    "default_retention_job_id",
    "delete_documento",
    "documento_base",
    "documento_out",
    "documento_resumo",
    "format_bytes_human",
    "get_documento_url",
    "list_acessos",
    "list_document_org_ids",
    "list_documentos",
    "list_tipos_documento",
    "log_acesso",
    "register_retention_sweep",
    "require_documento",
    "run_retention_sweep",
    "run_retention_sweep_all_orgs",
    "today",
    "upload_documento",
]
