"""Shared write mechanics for a `<entidade>_campo_conflitos` table.

THE N=3 FORMALIZATION (owner decision, P0c contract §H6)
----------------------------------------------------------
`cliente_campo_conflitos` (migration 138) and `imovel_campo_conflitos`
(migration 154) each grew, independently, the SAME three mechanics: open a
row keyed to (owner, campo), skip a doomed second insert while an earlier
one is still `pendente` (dedupe), and announce every newly-opened row
best-effort (notify). `empresa_campo_conflitos` (migration 167) is the third
table needing exactly this — the recurrence rule forbids shipping a third
hand-rolled copy, so this module is that copy's replacement AND the first
two's: `identidade_extracao_service._registrar_conflito` /
`.notificar_conflitos` and `imovel_hub.campos_extraidos_service.aplicar` /
`.notificar` now call the functions below rather than duplicating their
insert/select shape, unchanged behaviour, unchanged tests.

WHAT THIS OWNS
--------------
- **open** (`registrar_conflito`) — one row, the same dozen columns every
  one of the three tables share (`id, org_id, <owner_col>, campo,
  valor_anterior, origem_anterior, valor_proposto, origem_proposto,
  confianca_proposta, fonte_tabela, fonte_id, status='pendente',
  notificado_em=None, decidido_por=None, decidido_em=None, created_at`),
  plus the one column only `imovel_campo_conflitos` carries
  (`documento_id_proposto` — see `ConflictTable.has_documento_id_proposto`).
- **dedupe-pending** (`conflito_pendente_existente`) — the same read every
  caller ran by hand before this: skip the insert (and the doomed second
  row the partial UNIQUE index would refuse anyway) when a `pendente`
  conflict for this (owner, campo) already exists.
- **notify** (`notificar_conflitos`) — best-effort per conflict, `notificado
  _em` stamped only on success, a missing notifier logged as a WARNING
  naming every conflict it could not announce — never silently dropped.

WHAT THIS DOES **NOT** OWN
---------------------------
The decision of what "same value" means per table (`imovel_hub`'s `iguais`,
`identidade_extracao_service`'s per-field/per-group comparisons), what gets
APPLIED back onto the owner row on accept (`resolver_conflito` / `resolver`
— three different row shapes, three different callers), and which notifier
METHOD to call for which surface (`notify_field_conflict` /
`notify_imovel_field_conflict` / `notify_empresa_field_conflict`). Those stay
with each caller: `notificar_conflitos` below takes an already-bound
`notify_one(conflito) -> Awaitable[Any]` callable, so the caller decides
which vendor method and which extra context (`cliente_nome`, `codigo`,
`empresa_nome`, ...) to pass — this module stays owner-column-agnostic.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional
from uuid import uuid4

from app.services import table_reads

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _t(client: Any, table: str):
    return table_reads.table(client, table)


@dataclass(frozen=True)
class ConflictTable:
    """One `<entidade>_campo_conflitos` table's shape.

    `owner_col` is the ONLY structural difference across the three tables
    today (`cliente_id` / `codigo` / `empresa_id`). `has_documento_id_
    proposto` covers `imovel_campo_conflitos`' one extra column — absent on
    `cliente_campo_conflitos` / `empresa_campo_conflitos`, which fold that
    fact into `fonte_id` alone.
    """

    table: str
    owner_col: str
    has_documento_id_proposto: bool = False


#: The three registered surfaces, so a caller need not restate the table
#: name / owner column at every call site.
CLIENTE = ConflictTable(table="cliente_campo_conflitos", owner_col="cliente_id")
IMOVEL = ConflictTable(
    table="imovel_campo_conflitos", owner_col="codigo", has_documento_id_proposto=True
)
EMPRESA = ConflictTable(table="empresa_campo_conflitos", owner_col="empresa_id")


def conflito_pendente_existente(
    client: Any, table: ConflictTable, org_id: Any, owner: Any, campo: str
) -> Optional[dict]:
    """The open (`status='pendente'`) conflict for (owner, campo), or
    `None`. `owner` is whatever `table.owner_col` names — a `cliente_id` /
    `codigo` / `empresa_id`, stringified the same way every caller already
    stringifies its ids."""
    rows = (
        _t(client, table.table)
        .select("*")
        .eq("org_id", str(org_id))
        .eq(table.owner_col, str(owner))
        .eq("campo", campo)
        .eq("status", "pendente")
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def registrar_conflito(
    client: Any,
    table: ConflictTable,
    org_id: Any,
    owner: Any,
    campo: str,
    *,
    valor_anterior: Any,
    origem_anterior: Optional[str],
    valor_proposto: Any,
    origem_proposto: str,
    confianca_proposta: Optional[str] = None,
    fonte_tabela: Optional[str] = None,
    fonte_id: Optional[Any] = None,
    documento_id_proposto: Optional[Any] = None,
) -> Optional[dict]:
    """Open a conflict, or skip when one is already pending for (owner,
    campo) — see the module docstring's "dedupe-pending". Returns the NEW
    row when one was actually inserted (so the caller can notify), or
    `None` when nothing was — the caller should treat both as "handled",
    never as an error.

    `documento_id_proposto` is written only when `table.has_documento_id_
    proposto` — passing it for `CLIENTE`/`EMPRESA` is silently ignored
    rather than refused, so a generic caller (a future field shared across
    surfaces) does not need to branch on which table it is writing.
    """
    if conflito_pendente_existente(client, table, org_id, owner, campo) is not None:
        return None
    linha: dict[str, Any] = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        table.owner_col: str(owner),
        "campo": campo,
        "valor_anterior": valor_anterior,
        "origem_anterior": origem_anterior,
        "valor_proposto": valor_proposto,
        "origem_proposto": origem_proposto,
        "confianca_proposta": confianca_proposta,
        "fonte_tabela": fonte_tabela,
        "fonte_id": str(fonte_id) if fonte_id else None,
        "status": "pendente",
        "notificado_em": None,
        "decidido_por": None,
        "decidido_em": None,
        "created_at": _now(),
    }
    if table.has_documento_id_proposto:
        linha["documento_id_proposto"] = (
            str(documento_id_proposto) if documento_id_proposto else None
        )
    _t(client, table.table).insert(linha).execute()
    return linha


async def notificar_conflitos(
    client: Any,
    table: ConflictTable,
    conflitos: list[dict],
    notify_one: Optional[Callable[[dict], Awaitable[Any]]],
) -> int:
    """Announce every NEWLY opened conflict, best-effort per conflict — a
    down WhatsApp session or SMTP server must not fail the extraction that
    raised the conflict; the row itself is already committed and listed by
    whichever `listar`/`conflitos_pendentes` reads this table.

    `notify_one(conflito)` is the caller's own bound notifier call — it
    already knows which vendor method and which extra context (a cliente's
    name, an imóvel's `codigo`, an empresa's razão social) to pass. This
    function owns only the loop, the try/except, and the `notificado_em`
    stamp on success.

    `notify_one=None` with conflicts to announce is logged as a WARNING
    naming every one of them — never silent, matching every other
    best-effort log in this schema.
    """
    if not conflitos:
        return 0
    if notify_one is None:
        logger.warning(
            "%s: %d conflito(s) aberto(s) sem notificador — registrados, "
            "não anunciados: %s",
            table.table, len(conflitos), [c.get("campo") for c in conflitos],
        )
        return 0
    enviados = 0
    for conflito in conflitos:
        try:
            await notify_one(conflito)
            _t(client, table.table).update({"notificado_em": _now()}).eq(
                "id", conflito["id"]
            ).execute()
            enviados += 1
        except Exception:  # noqa: BLE001 - a notify failure must not fail the caller
            logger.exception(
                "%s: could not notify conflict %s on campo %r",
                table.table, conflito.get("id"), conflito.get("campo"),
            )
    return enviados


__all__ = [
    "CLIENTE",
    "EMPRESA",
    "IMOVEL",
    "ConflictTable",
    "conflito_pendente_existente",
    "notificar_conflitos",
    "registrar_conflito",
]
