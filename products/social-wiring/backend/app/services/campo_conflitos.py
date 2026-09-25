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

THE D1 SAME-DOCUMENT-RE-READ REFINEMENT (2026-09-25 live case)
------------------------------------------------------------------
Every D1 apply path opens a conflict when the incoming reading disagrees
with what's stored — correct when the two readings come from DIFFERENT
documents (a genuine second opinion). Measured live: re-extracting a
document whose earlier reading is STILL machine-pending (unconfirmed) now
opens a conflict with ITSELF — `empresa_campo_conflitos` on
`motivo_situacao`/`natureza_juridica` (old piped-residue text vs. the SAME
Cartão CNPJ's clean re-read) and `cliente_campo_conflitos` on `endereco`
(the SAME `cliente_documentos` comprovante, first read incomplete, second
read complete). `mesmo_documento_pendente` is the shared PREDICATE every
apply path consults before opening a conflict: when the stored value's own
`*_documento_id` equals the incoming document's id AND the stored value is
still machine-pending (`origem` set, not `'manual'`, `*_confirmado_em`
NULL), the incoming reading REPLACES it — a refresh of the same source,
not a second opinion — instead of opening a conflict. A human-confirmed or
manually-typed value is NEVER touched this way (`confirmado_em` truthy or
`origem == 'manual'` both refuse). A reading from a DIFFERENT document
still conflicts exactly as before.

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


def mesmo_documento_pendente(
    *,
    origem_atual: Optional[str],
    confirmado_em_atual: Any,
    documento_id_atual: Optional[Any],
    documento_id_proposto: Optional[Any],
    origem_manual: str = "manual",
) -> bool:
    """Is the incoming (disagreeing) reading a RE-READ of the SAME
    document that produced the value currently stored — and is that
    stored value still machine-pending? See the module docstring's D1
    same-document-re-read refinement.

    `False` (never a replace, always a conflict) whenever ANY of:
    - `origem_atual` is empty/`None` (nothing stored to refresh) or equals
      `origem_manual` (a human typed it — never silently replaced);
    - `confirmado_em_atual` is truthy (a human already vouched for it —
      same rule, different column);
    - either document id is missing (nothing to compare);
    - the two document ids differ (a genuinely different source — the
      ordinary conflict case).

    Both ids are stringified before comparing — callers pass a mix of
    `UUID`/`str` across the three apply paths (`empresas`/`clientes`/
    `imovel_dados`), same convention every conflict row already uses."""
    if not origem_atual or origem_atual == origem_manual:
        return False
    if confirmado_em_atual:
        return False
    if documento_id_atual is None or documento_id_proposto is None:
        return False
    return str(documento_id_atual) == str(documento_id_proposto)


def fechar_conflitos_pendentes(
    client: Any,
    table: ConflictTable,
    org_id: Any,
    owner: Any,
    campo: str,
    *,
    decidido_por: Optional[Any] = None,
) -> int:
    """Close every OPEN (`status='pendente'`) conflict on (owner, campo) as
    `rejeitado` — never silently deleted, the record that a conflict was
    once open here stays auditable. A side-effect of a DIFFERENT
    legitimate write superseding what the pending row was proposing (a
    Crednet-truncation upgrade, or `mesmo_documento_pendente`'s same
    -document re-read replace) — not a background sweep. `decidido_por=
    None` marks a SYSTEM resolution (no admin account involved). Returns
    the number of rows closed.

    The N=3 formalization of what `empresas.dados_service.
    _fechar_conflitos_pendentes` and `imovel_hub.campos_extraidos_service`
    each independently grew for this SAME mechanic (this module's own
    recurrence rule, P0c contract §H6) — every D1 apply path calls this
    one instead of hand-rolling its own close-pending loop."""
    pendentes = (
        _t(client, table.table)
        .select("id")
        .eq("org_id", str(org_id))
        .eq(table.owner_col, str(owner))
        .eq("campo", campo)
        .eq("status", "pendente")
        .execute()
    ).data or []
    now = _now()
    for row in pendentes:
        _t(client, table.table).update(
            {
                "status": "rejeitado",
                "decidido_por": str(decidido_por) if decidido_por else None,
                "decidido_em": now,
            }
        ).eq("id", row["id"]).execute()
    return len(pendentes)


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
    "fechar_conflitos_pendentes",
    "mesmo_documento_pendente",
    "notificar_conflitos",
    "registrar_conflito",
]
