"""Operator-authored checklist lines — a request an operator typed for THIS
card and nobody else's ("condomínio: enviar convenção").

Lifted from social-wiring's `app/modules/card_hub/checklist_extras_service.py`
(migration 083).

🔴 `concluido` IS DERIVED, NEVER STORED
---------------------------------------
A `texto` line is done when it has (non-blank) text; an `arquivo` line is done
when it holds a LIVE document. Both facts already live in the row, so a stored
tick could only agree with them or be silently wrong — and the retention sweep
(`documentos.run_retention_sweep`) soft-deletes documents on a schedule with no
knowledge of this table. A stored tick would outlive the file it asserts.

🔴 DELETING THE FILE KEEPS THE LINE
-----------------------------------
The line is the REQUEST; the document is only its current answer.
`remover_documento` soft-deletes the document (with its LGPD access-log entry)
and NULLs `documento_id`; the line stays, empty and ready. Uploading onto an
occupied line REPLACES the answer (the displaced document is soft-deleted,
never orphaned).

🔴 A CROSSED WRITE IS A 422, NOT A SILENT IGNORE
------------------------------------------------
A `texto` line refuses a document and an `arquivo` line refuses `valor_texto`
(`TipoIncompativel`, which the router maps to 422 — the same status the
sibling checklist endpoints use for "you sent the wrong shape").

Storage, LGPD category, retention and the access log are NOT re-implemented:
`documentos.upload_documento` / `delete_documento` are the one path a file
enters or leaves by.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.persistence.table_reads import (
    in_batched_rows,
    paged_rows,
    table,
)
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from . import documentos as docs
from .config import CardHubConfig
from .services import ensure_entity, now_iso

logger = logging.getLogger(__name__)

#: Mirrors the CHECK the migration template emits. Both exist on purpose: the
#: schema protects the API surface, the CHECK protects every other writer.
TIPOS_VALIDOS = ("texto", "arquivo")

MOTIVO_SUBSTITUICAO = "substituído por novo upload no item do checklist"
MOTIVO_REMOCAO = "removido do item do checklist"


class TipoIncompativel(ValueError):
    """The write does not match the line's `tipo` (router → 422).

    NOT a `ValidationError_` (which the seed maps to 400): adjacent checklist
    endpoints disagreeing on the status for "you sent the wrong shape" is a
    distinction the frontend would have to encode for no reason.
    """

    def __init__(self, extra_tipo: str, tentativa: str):
        self.extra_tipo = extra_tipo
        self.tentativa = tentativa
        super().__init__(
            f"item do tipo {extra_tipo!r} não aceita {tentativa} — "
            f"tipos válidos para essa operação: "
            f"{'arquivo' if tentativa == 'documento' else 'texto'}"
        )


# ── derivation + projection ────────────────────────────────────────────────


def concluido_de(row: dict, documento: Optional[dict]) -> bool:
    """The rule, as a pure function: is this line satisfied? Whitespace-only
    text is NOT — `"   "` passes NOT NULL and satisfies nobody."""
    if row.get("tipo") == "texto":
        valor = row.get("valor_texto")
        return bool(valor.strip()) if isinstance(valor, str) else valor is not None
    return documento is not None


def _out(row: dict, documento: Optional[dict]) -> dict:
    return {
        "id": row["id"],
        "label": row.get("label"),
        "tipo": row.get("tipo"),
        "valor_texto": row.get("valor_texto"),
        "documento": documento,
        "concluido": concluido_de(row, documento),
        "ordem": row.get("ordem") or 0,
    }


# ── reads ──────────────────────────────────────────────────────────────────


def _linhas(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID) -> list[dict]:
    """Live lines in render order: `ordem`, then `created_at` (a tie keeps
    typing order instead of shuffling between requests). Sorted in Python —
    the pager owns the single `order_col` it needs for stable paging."""
    rows = paged_rows(
        db,
        cfg.tables.checklist_extras,
        org_id,
        eq_filters={cfg.entity_fk: str(entity_id)},
        refine=lambda q: q.is_("deleted_at", "null"),
    )
    rows.sort(key=lambda r: (r.get("ordem") or 0, r.get("created_at") or ""))
    return rows


def _documentos_de(cfg: CardHubConfig, db: Any, org_id: UUID, rows: list[dict]) -> dict[str, dict]:
    """`documento_id -> live row` for a whole page — ONE batched read, never
    one per line. A soft-deleted document is dropped, so its line derives back
    to `concluido: false` — the honest answer."""
    ids = sorted({str(r["documento_id"]) for r in rows if r.get("documento_id")})
    if not ids:
        return {}
    rows_docs = in_batched_rows(db, cfg.tables.documentos, org_id, "id", ids)
    return {str(d["id"]): d for d in rows_docs if d.get("deleted_at") is None}


def listar(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID) -> dict:
    ensure_entity(cfg, db, org_id, entity_id)
    rows = _linhas(cfg, db, org_id, entity_id)
    documentos = _documentos_de(cfg, db, org_id, rows)
    items = [
        _out(r, docs.documento_resumo(documentos.get(str(r.get("documento_id")))))
        for r in rows
    ]
    return {"items": items, "total": len(items)}


def _obter(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID, extra_id: UUID) -> dict:
    """The row, proven to belong to THIS entity — the ownership check IS the
    security boundary (an id alone never edits someone else's card)."""
    rows = (
        table(db, cfg.tables.checklist_extras)
        .select("*")
        .eq("org_id", str(org_id))
        .eq(cfg.entity_fk, str(entity_id))
        .eq("id", str(extra_id))
        .execute()
    ).data or []
    if not rows or rows[0].get("deleted_at"):
        raise NotFoundError(cfg.tables.checklist_extras, str(extra_id))
    return rows[0]


def _um(cfg: CardHubConfig, db: Any, org_id: UUID, row: dict) -> dict:
    documentos = _documentos_de(cfg, db, org_id, [row])
    return _out(row, docs.documento_resumo(documentos.get(str(row.get("documento_id")))))


# ── writes ─────────────────────────────────────────────────────────────────


def criar(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID, *, label: str, tipo: str) -> dict:
    """A new line, landing AFTER every existing one (where the operator was
    looking) rather than at the top because 0 is the default."""
    ensure_entity(cfg, db, org_id, entity_id)
    existentes = _linhas(cfg, db, org_id, entity_id)
    agora = now_iso()
    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        cfg.entity_fk: str(entity_id),
        "label": label.strip(),
        "tipo": tipo,
        "valor_texto": None,
        "documento_id": None,
        "ordem": max((e.get("ordem") or 0) for e in existentes) + 1 if existentes else 0,
        "created_at": agora,
        "updated_at": agora,
        "deleted_at": None,
    }
    table(db, cfg.tables.checklist_extras).insert(row).execute()
    return _out(row, None)


def atualizar(
    cfg: CardHubConfig,
    db: Any,
    org_id: UUID,
    entity_id: UUID,
    extra_id: UUID,
    *,
    label: Optional[str] = ...,
    valor_texto: Optional[str] = ...,
    ordem: Optional[int] = ...,
) -> dict:
    """`...` sentinels an unset field — only what the PATCH carried is written
    (`None` is a real value: clearing `valor_texto` unticks the line)."""
    row = _obter(cfg, db, org_id, entity_id, extra_id)

    if valor_texto is not ... and row.get("tipo") != "texto":
        raise TipoIncompativel(row.get("tipo") or "?", "valor_texto")

    updates: dict[str, Any] = {}
    if label is not ...:
        # NOT NULL cannot express "not blank"; this does.
        limpo = (label or "").strip()
        if not limpo:
            raise ValidationError_("label não pode ser vazio", field="label")
        updates["label"] = limpo
    if valor_texto is not ...:
        # Blank clears the answer rather than storing whitespace.
        limpo = (valor_texto or "").strip()
        updates["valor_texto"] = limpo or None
    if ordem is not ...:
        updates["ordem"] = int(ordem or 0)

    if updates:
        updates["updated_at"] = now_iso()
        table(db, cfg.tables.checklist_extras).update(updates).eq("id", str(extra_id)).execute()
        row = {**row, **updates}
    return _um(cfg, db, org_id, row)


def remover(cfg: CardHubConfig, db: Any, org_id: UUID, entity_id: UUID, extra_id: UUID) -> None:
    """Soft delete. The attached document is deliberately LEFT ALONE — it is
    a real document with its own retention clock and access log, and removing
    a line is not a request to erase a file."""
    _obter(cfg, db, org_id, entity_id, extra_id)
    table(db, cfg.tables.checklist_extras).update(
        {"deleted_at": now_iso(), "updated_at": now_iso()}
    ).eq("id", str(extra_id)).execute()


async def anexar_documento(
    cfg: CardHubConfig,
    db: Any,
    storage: StorageBackend,
    org_id: UUID,
    entity_id: UUID,
    extra_id: UUID,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    enviado_por: Optional[UUID] = None,
) -> dict:
    """Upload onto an `arquivo` line, REPLACING whatever it held.

    Filed under `cfg.checklist_extra_tipo_documento` through
    `documentos.upload_documento` — same allow-list, limits, storage layout,
    LGPD category and retention as any other upload. The NEW document is
    linked before the old one is displaced, so a failed displacement leaves the
    line correct and only the old row un-swept.
    """
    row = _obter(cfg, db, org_id, entity_id, extra_id)
    if row.get("tipo") != "arquivo":
        raise TipoIncompativel(row.get("tipo") or "?", "documento")

    documento = await docs.upload_documento(
        cfg,
        db,
        storage,
        org_id,
        entity_id,
        filename=filename,
        content_type=content_type,
        data=data,
        tipo_documento=cfg.checklist_extra_tipo_documento,
        enviado_por=enviado_por,
    )

    anterior = row.get("documento_id")
    updates = {"documento_id": str(documento["id"]), "updated_at": now_iso()}
    table(db, cfg.tables.checklist_extras).update(updates).eq("id", str(extra_id)).execute()

    if anterior:
        try:
            await docs.delete_documento(
                cfg,
                db,
                storage,
                org_id,
                entity_id,
                UUID(str(anterior)),
                motivo=MOTIVO_SUBSTITUICAO,
                usuario_id=enviado_por,
            )
        except NotFoundError:
            # The retention sweep may have soft-deleted it already — nothing
            # to displace. Logged, not swallowed.
            logger.debug(
                "card_hub.checklist_extras: documento %s já removido ao "
                "substituir o anexo do item %s",
                anterior,
                extra_id,
            )
    return _um(cfg, db, org_id, {**row, **updates})


async def remover_documento(
    cfg: CardHubConfig,
    db: Any,
    storage: StorageBackend,
    org_id: UUID,
    entity_id: UUID,
    extra_id: UUID,
    *,
    usuario_id: Optional[UUID] = None,
) -> None:
    """🔴 Discard the FILE, KEEP the LINE. A no-op on an empty line — a 404
    would make the trash button race its own refetch."""
    row = _obter(cfg, db, org_id, entity_id, extra_id)
    documento_id = row.get("documento_id")
    if not documento_id:
        return

    try:
        await docs.delete_documento(
            cfg,
            db,
            storage,
            org_id,
            entity_id,
            UUID(str(documento_id)),
            motivo=MOTIVO_REMOCAO,
            usuario_id=usuario_id,
        )
    except NotFoundError:
        # Already gone (the retention sweep got there first). The line must
        # still be unlinked below. Logged, not swallowed.
        logger.debug(
            "card_hub.checklist_extras: documento %s já removido ao limpar o item %s",
            documento_id,
            extra_id,
        )
    table(db, cfg.tables.checklist_extras).update(
        {"documento_id": None, "updated_at": now_iso()}
    ).eq("id", str(extra_id)).execute()


__all__ = [
    "MOTIVO_REMOCAO",
    "MOTIVO_SUBSTITUICAO",
    "TIPOS_VALIDOS",
    "TipoIncompativel",
    "anexar_documento",
    "atualizar",
    "concluido_de",
    "criar",
    "listar",
    "remover",
    "remover_documento",
]
