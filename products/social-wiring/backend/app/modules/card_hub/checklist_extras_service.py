"""Operator-authored checklist lines — the per-client half of the card.

WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT
---------------------------------------------
`documento_checklist_service` owns the MANDATORY list: eight items identical
for every client, defined in code so adding a ninth is a deploy rather than a
per-client backfill. This module owns the other half — a line an operator typed
for THIS person and nobody else ("condomínio: enviar convenção", "escritura
anterior"). Same surface on screen, two homes, because the two are different
kinds of fact: one is a decision about every client, the other is a note about
one.

🔴 `concluido` IS DERIVED, NEVER STORED
---------------------------------------
Migration 068's argument, applied to this table rather than re-litigated. A
`texto` line is done when it has text; an `arquivo` line is done when it holds a
live document. Both facts already live in the row, so a stored `concluido` could
only agree with them or be silently wrong — and here there is a concrete writer
that would make it wrong with nobody watching: the retention sweep
(`documentos_service.run_retention_sweep`) soft-deletes documents on a schedule
and knows nothing about this table. A stored tick would outlive the file it
asserts. Derivation has no such interval.

🔴 DELETING THE FILE KEEPS THE LINE
-----------------------------------
The product rule, stated here because the code has to be read as meaning it and
not as an oversight: `remover_documento` soft-deletes the `cliente_documentos`
row, NULLs `documento_id`, and leaves the extra standing — empty, underived, and
ready for a fresh upload. The line is the REQUEST; the document is only its
current answer. A cascade that removed the line along with the file would delete
the request because someone sent the wrong scan.

Uploading onto a line that already holds a document REPLACES it, by the same
reading: the request did not change, its answer did. The displaced document is
soft-deleted (never orphaned), so it stays in the Documentos tab's history and
its access log survives.

🔴 A CROSSED WRITE IS A 422, NOT A SILENT IGNORE
------------------------------------------------
A `texto` line refuses a document and an `arquivo` line refuses `valor_texto`.
Both are caller bugs — `tipo` is chosen at creation and returned on every read —
and a 200 that quietly dropped the value would show as a line that will not
tick, with nothing anywhere saying why.

Storage, LGPD category, retention and the access log are NOT re-implemented
here: `documentos_service.upload_documento` / `delete_documento` are the one
path a file enters or leaves this product by, and a second one would be a second
place for the retention policy to be wrong.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.modules.card_hub import documentos_service as docs_svc
from app.modules.card_hub.services import _now, _paged_rows, _t, ensure_cliente
from app.services import table_reads

logger = logging.getLogger(__name__)

TABLE = "cliente_checklist_extras"
DOCUMENTOS_TABLE = "cliente_documentos"

#: Mirrors the CHECK in migration 083. Both exist on purpose: the schema
#: protects the API surface, the CHECK protects every other writer.
TIPOS_VALIDOS = ("texto", "arquivo")

#: The `tipo_documento` an extra's upload is filed under.
#:
#: An operator-authored line has no document TAXONOMY behind it by definition —
#: whatever they are asking for is the thing the catalogue did not anticipate.
#: `outro` is the catalogue's own answer for that (migration 057 seeds it
#: `ativo = true`, categoria `nao_classificado`, 365-day retention), so the
#: upload goes through the same allow-list and the same retention policy every
#: other document does. Inventing a per-extra type would mean a row in
#: `cliente_documento_tipos` with no retention anybody had decided on, which is
#: precisely the hardcoded-`if` that migration exists to prevent.
TIPO_DOCUMENTO = "outro"

_MOTIVO_SUBSTITUICAO = "substituído por novo upload no item do checklist"
_MOTIVO_REMOCAO = "removido do item do checklist"


class TipoIncompativel(ValueError):
    """The write does not match the line's `tipo`.

    A `ValueError` the router turns into a 422, mirroring how
    `documento_checklist_service.marcar` signals an unknown `item_key`. NOT a
    `ValidationError_`: the seed maps that to 400, and this is the same class of
    caller mistake the sibling route already answers with 422 — two adjacent
    checklist endpoints disagreeing on the status code for "you sent the wrong
    shape" is a distinction the frontend would have to encode for no reason.
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
    """The rule, as a pure function: is this line satisfied?

    Pure and dependency-free on purpose, exactly like
    `documento_checklist_service.derivar` — this decides whether the card claims
    a request has been answered, so it is testable without a database.

    Whitespace-only text is NOT satisfied: a `valor_texto` of `"   "` passes a
    NOT NULL check and satisfies nobody.
    """
    if row.get("tipo") == "texto":
        valor = row.get("valor_texto")
        return bool(valor.strip()) if isinstance(valor, str) else valor is not None
    return documento is not None


def _out(row: dict, documento: Optional[dict]) -> dict:
    """One extra line, in the shape the card renders.

    `documento` is the summary from `documentos_service.documento_resumo` — the
    SAME projection the mandatory items carry, so the frontend renders both
    halves of the checklist through one row component.
    """
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


def _linhas(client: Any, org_id: UUID, cliente_id: UUID) -> list[dict]:
    """This client's live extras, in render order.

    Sorted in Python rather than by `.order()` because the ordering is
    two-column and the pager already owns the single `order_col` it needs for
    stable paging — asking PostgREST for a second sort key would fight it.
    `created_at` breaks a tie so two lines added with the same `ordem` (the
    default 0, which is every line until someone drags one) stay in the order
    they were typed instead of shuffling between requests.
    """
    rows = _paged_rows(
        client,
        TABLE,
        org_id,
        eq_filters={"cliente_id": str(cliente_id)},
        refine=lambda q: q.is_("deleted_at", "null"),
    )
    rows.sort(key=lambda r: (r.get("ordem") or 0, r.get("created_at") or ""))
    return rows


def _documentos_de(client: Any, org_id: UUID, rows: list[dict]) -> dict[str, dict]:
    """`documento_id -> live document row`, for a whole page of extras.

    ONE batched read for the list, never one per line: a card with a dozen
    `arquivo` lines would otherwise be a dozen round-trips, which is the N+1
    migration 080 had to undo elsewhere in this product. Written with the read
    rather than after the loop is discovered in production.

    A soft-deleted document is dropped here, so a line whose file was swept by
    retention comes back with `documento: null` and `concluido: false` — which
    is the honest answer: the thing that was asked for is no longer held.
    """
    ids = sorted({str(r["documento_id"]) for r in rows if r.get("documento_id")})
    if not ids:
        return {}
    docs = table_reads.in_batched_rows(
        client, DOCUMENTOS_TABLE, org_id, "id", ids
    )
    return {str(d["id"]): d for d in docs if d.get("deleted_at") is None}


def listar(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    ensure_cliente(client, org_id, cliente_id)
    rows = _linhas(client, org_id, cliente_id)
    docs = _documentos_de(client, org_id, rows)
    items = [
        _out(r, docs_svc.documento_resumo(docs.get(str(r.get("documento_id")))))
        for r in rows
    ]
    return {"items": items, "total": len(items)}


def _obter(client: Any, org_id: UUID, cliente_id: UUID, extra_id: UUID) -> dict:
    """The row, proven to belong to THIS cliente.

    The ownership check IS the security boundary: an id alone must never be
    enough to edit a line on someone else's card, so `cliente_id` is a filter
    here and not merely a path decoration.
    """
    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .eq("id", str(extra_id))
        .execute()
    ).data or []
    if not rows or rows[0].get("deleted_at"):
        raise NotFoundError(TABLE, str(extra_id))
    return rows[0]


def _um(client: Any, org_id: UUID, row: dict) -> dict:
    """Re-read the line's document (if any) and project it."""
    docs = _documentos_de(client, org_id, [row])
    return _out(row, docs_svc.documento_resumo(docs.get(str(row.get("documento_id")))))


# ── writes ─────────────────────────────────────────────────────────────────


def criar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    label: str,
    tipo: str,
) -> dict:
    """A new line. `ordem` lands after every existing one, so a line appears
    where the operator was looking — at the bottom — instead of jumping to the
    top of the list because 0 is the default."""
    ensure_cliente(client, org_id, cliente_id)
    existentes = _linhas(client, org_id, cliente_id)
    agora = _now()
    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "cliente_id": str(cliente_id),
        "label": label.strip(),
        "tipo": tipo,
        "valor_texto": None,
        "documento_id": None,
        "ordem": max((e.get("ordem") or 0) for e in existentes) + 1 if existentes else 0,
        "created_at": agora,
        "updated_at": agora,
        "deleted_at": None,
    }
    _t(client, TABLE).insert(row).execute()
    return _out(row, None)


def atualizar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    extra_id: UUID,
    *,
    label: Optional[str] = ...,
    valor_texto: Optional[str] = ...,
    ordem: Optional[int] = ...,
) -> dict:
    """`...` sentinels an unset field — only what the PATCH carried is written.

    An `arquivo` line REFUSES `valor_texto` (422). Accepting and ignoring it
    would leave the operator typing into a box whose contents vanish on every
    save, with a 200 saying it worked.
    """
    row = _obter(client, org_id, cliente_id, extra_id)

    if valor_texto is not ... and row.get("tipo") != "texto":
        raise TipoIncompativel(row.get("tipo") or "?", "valor_texto")

    updates: dict[str, Any] = {}
    if label is not ...:
        # Blank is refused rather than stored: a line with no label renders as
        # a row nobody can identify and the operator cannot tell it from a
        # rendering bug. The schema says NOT NULL; this says "not blank
        # either", which NOT NULL cannot express.
        limpo = (label or "").strip()
        if not limpo:
            raise ValidationError_("label não pode ser vazio", field="label")
        updates["label"] = limpo
    if valor_texto is not ...:
        # Blank clears the answer rather than storing whitespace — the line goes
        # back to unticked, which is what the operator meant by emptying it.
        limpo = (valor_texto or "").strip()
        updates["valor_texto"] = limpo or None
    if ordem is not ...:
        updates["ordem"] = int(ordem or 0)

    if updates:
        updates["updated_at"] = _now()
        _t(client, TABLE).update(updates).eq("id", str(extra_id)).execute()
        row = {**row, **updates}
    return _um(client, org_id, row)


def remover(client: Any, org_id: UUID, cliente_id: UUID, extra_id: UUID) -> None:
    """Soft delete, per the card_hub convention — one UPDATE to undo.

    The attached document (if any) is deliberately LEFT ALONE: it is a real
    document in this client's Documentos tab with its own retention clock and
    access log, and removing a checklist line is not a request to erase a file.
    """
    _obter(client, org_id, cliente_id, extra_id)
    _t(client, TABLE).update(
        {"deleted_at": _now(), "updated_at": _now()}
    ).eq("id", str(extra_id)).execute()


async def anexar_documento(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    cliente_id: UUID,
    extra_id: UUID,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    enviado_por: Optional[UUID] = None,
) -> dict:
    """Upload a file onto an `arquivo` line, replacing whatever it held.

    The file goes through `documentos_service.upload_documento` — the one path
    a document enters this product by, so it gets the same MIME allow-list, the
    same size limit, the same storage layout, the same LGPD category and the
    same retention clock as any other upload. Re-implementing any of that here
    would be a second place for the retention policy to be wrong.

    REPLACEMENT, not accumulation: the displaced document is soft-deleted with a
    stated reason, so it keeps its access log and stays visible in the
    Documentos tab as history rather than becoming an orphan nothing points at.
    The new row is linked only AFTER the upload succeeds — a failed upload
    leaves the line holding the document it already had.
    """
    row = _obter(client, org_id, cliente_id, extra_id)
    if row.get("tipo") != "arquivo":
        raise TipoIncompativel(row.get("tipo") or "?", "documento")

    documento = await docs_svc.upload_documento(
        client,
        storage,
        org_id,
        cliente_id,
        filename=filename,
        content_type=content_type,
        data=data,
        tipo_documento=TIPO_DOCUMENTO,
        enviado_por=enviado_por,
    )

    # Link the NEW document before displacing the old one. The reverse order
    # reads more naturally and is worse: if the displacement fails, the line is
    # left pointing at a document that is already gone, and the file the
    # operator just uploaded is attached to nothing. This way a failure leaves
    # the line correct and only the old row un-swept.
    anterior = row.get("documento_id")
    updates = {"documento_id": str(documento["id"]), "updated_at": _now()}
    _t(client, TABLE).update(updates).eq("id", str(extra_id)).execute()

    if anterior:
        try:
            await docs_svc.delete_documento(
                client,
                storage,
                org_id,
                cliente_id,
                UUID(str(anterior)),
                motivo=_MOTIVO_SUBSTITUICAO,
                usuario_id=enviado_por,
            )
        except NotFoundError:
            # The retention sweep soft-deletes documents on a schedule and
            # knows nothing about this table, so the row this line pointed at
            # may already be gone. Nothing to displace — but it is logged
            # rather than swallowed, because "the previous document vanished
            # before we could delete it" is a real thing to be able to see.
            logger.debug(
                "card_hub.checklist_extras: documento %s já removido ao "
                "substituir o anexo do item %s",
                anterior,
                extra_id,
            )
    return _um(client, org_id, {**row, **updates})


async def remover_documento(
    client: Any,
    storage: StorageBackend,
    org_id: UUID,
    cliente_id: UUID,
    extra_id: UUID,
    *,
    usuario_id: Optional[UUID] = None,
) -> None:
    """🔴 Discard the FILE, KEEP the LINE.

    This is the product rule, not an implementation detail: the card stays
    there, the document is deleted, and the operator can upload a fresh one onto
    the same line. So the document is soft-deleted through
    `documentos_service.delete_documento` (which appends the `delete` access-log
    entry an LGPD delete requires) and `documento_id` is NULLed — the extra
    itself is untouched and derives back to `concluido: false`.

    A no-op when the line holds nothing: deleting an absent file is not an
    error, and a 404 here would make the frontend's trash button race its own
    refetch.
    """
    row = _obter(client, org_id, cliente_id, extra_id)
    documento_id = row.get("documento_id")
    if not documento_id:
        return

    try:
        await docs_svc.delete_documento(
            client,
            storage,
            org_id,
            cliente_id,
            UUID(str(documento_id)),
            motivo=_MOTIVO_REMOCAO,
            usuario_id=usuario_id,
        )
    except NotFoundError:
        # Already gone — the retention sweep got there first. The operator
        # asked for the line to be empty and it is; refusing with a 404 would
        # leave a dangling `documento_id` behind on a line the card already
        # renders as empty. Logged, not swallowed.
        logger.debug(
            "card_hub.checklist_extras: documento %s já removido ao limpar o "
            "item %s",
            documento_id,
            extra_id,
        )
    # Unlinked either way: whether we deleted it or found it already deleted,
    # this line no longer points at anything.
    _t(client, TABLE).update(
        {"documento_id": None, "updated_at": _now()}
    ).eq("id", str(extra_id)).execute()


__all__ = [
    "TABLE",
    "TIPOS_VALIDOS",
    "TIPO_DOCUMENTO",
    "TipoIncompativel",
    "anexar_documento",
    "atualizar",
    "concluido_de",
    "criar",
    "listar",
    "remover",
    "remover_documento",
]
