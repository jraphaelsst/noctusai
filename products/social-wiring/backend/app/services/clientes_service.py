"""`clientes` (person layer) — CRUD + the identity-resolution backfill.

Contract: `products/social-wiring/projects/lead-card-hub-p1-PROJECT.md` §4/§7.
The matching algorithm itself (the C1-C6 predicate, name normalization,
`SourceRow` extraction) lives in `identidade_service.py`, kept I/O-free so it
is unit-testable without a database (`048_clientes_person_layer.sql`'s header
explains why). This module is the I/O layer: it fetches `leads` /
`meta_ads_leads` rows, calls into `identidade_service` to decide what to do
with them, and writes `clientes` / `cliente_touches` / `cliente_merges` /
`negociacoes_venda.cliente_id`.

Slice B (routers, contract §5) imports this module's public functions —
`list_clientes`, `get_cliente`, `get_touches`, `update_cliente`,
`list_review_groups`, `merge_clientes`, `undo_merge` — and does not modify
it (see the PROJECT.md §6 slice table: B's file list is routers + main.py
only).

RUNNING THE BACKFILL — DRY-RUN FIRST (feeds contract §7)
----------------------------------------------------------
`run_backfill(client, org_id, dry_run=True)` only ever SELECTs from
`leads`/`meta_ads_leads` — it never touches `clientes`/`cliente_touches`/
`cliente_merges`/`negociacoes_venda`, so it can run against the LIVE
database with NO prerequisite (this migration does not even need to be
applied yet). This is what should feed the tech-lead's "state the row
counts, get an explicit decision" conversation with the user (§7) — the
counts this repo's tests exercise are necessarily small fixtures (no dev
database exists to validate the live 13 330/1 152/399/1 413/389/... figures
against — see the Slice A delivery note); a real dry-run against
production is the only way to get the true numbers before 048 is applied.

IDEMPOTENCY + CONCURRENCY (§7)
--------------------------------
Safe to call repeatedly on a live, growing `leads` table:

1. Every source row already represented in `cliente_touches` (matched by
   the exact `(origem_tabela, origem_id)` the UNIQUE index enforces) is
   skipped outright — this alone makes "run it twice on unchanged data"
   a true no-op.
2. A genuinely NEW row under an ALREADY-SEEN `chave_canonica` is
   reconciled against whatever already exists for that key (a previous
   run's resolved survivor, or its review candidates) rather than
   reclassified from scratch:
   - Exact normalized-name match against an existing cliente -> the new
     row becomes a new touch on that cliente (its span is recomputed).
   - A lone nameless straggler where exactly one cliente already exists
     for the key -> attaches to it (mirrors C3's "nameless rides along").
   - Anything else (a name that matches none of the existing candidates)
     is parked as its OWN new review-visible cliente
     (`identidade_incerta=True`, no key claimed) rather than silently
     guessed onto an existing identity, or reclassified in a way that
     could quietly re-open an already-confirmed match. This is a
     deliberately conservative choice, not full re-classification of the
     combined old+new row set — flagged as a documented limitation (a
     follow-up could fold new evidence back into a PAST decision; this
     backfill never does that automatically).
3. `negociacoes_venda.cliente_id` repoint only ever touches rows where
   `cliente_id IS NULL`, so re-running never re-derives an already-set
   value.

`client` MUST ALREADY BE SCHEMA-SCOPED
-----------------------------------------
Every function here takes `client` and calls `client.table(name)`
directly — it never calls `client.schema("social_wiring")` itself.
Callers must pass an already-`social_wiring`-scoped client (real
Supabase admin client with `.schema("social_wiring")` applied once, or
a test double already bound). This mirrors
`app/modules/leads/deps.py::get_leads_client`'s documented fix for a
confirmed `MockSupabaseClient` defect: `.schema(name)` returns a BRAND
NEW wrapper with an EMPTY per-table row cache on every call, so a
`client.schema(SCHEMA).table(t)` pattern re-resolved inside every method
(the shape `imoveis_service.py`/`marcas_service.py` use) silently loses
every prior write the instant two SEPARATE calls re-derive the schema
binding — exactly what `run_backfill` does across its many separate
table accesses. `leads/deps.py` fixes this once, product-wide, with a
`WeakKeyDictionary`-cached scoped client; Slice B should reuse that same
pattern (a `get_clientes_client()` deps helper) rather than re-deriving
the schema binding per call when it wires the routers' DI.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from app.services import identidade_service as ident
from app.services.identidade_service import SourceRow

logger = logging.getLogger(__name__)

__all__ = [
    "ClienteNotFound",
    "MergeNotFound",
    "MergeAlreadyUndone",
    "BackfillReport",
    "run_backfill",
    "list_clientes",
    "get_cliente",
    "get_touches",
    "update_cliente",
    "list_review_groups",
    "merge_clientes",
    "undo_merge",
]

_SCHEMA = "social_wiring"
#: PostgREST's default unpaginated-select row cap — see
#: `imoveis_service.ImoveisService._select_all`'s docstring for the
#: measured bug this guards against (a bare `.select().execute()` over a
#: table bigger than this silently truncates with no error).
_PAGE = 1000

_MOTIVOS = ("C1", "C2", "C3", "C4", "C5", "C6")


class ClienteNotFound(Exception):
    """A `clientes` row doesn't exist or isn't owned by the org."""


class MergeNotFound(Exception):
    """A `cliente_merges` row doesn't exist or isn't owned by the org."""


class MergeAlreadyUndone(Exception):
    """`undo_merge` called on a merge whose `desfeito_em` is already set."""


# ─── report ──────────────────────────────────────────────────────────────


@dataclass
class BackfillReport:
    org_id: str
    dry_run: bool
    leads_scanned: int = 0
    meta_leads_scanned: int = 0
    keyless_clientes: int = 0
    groups_total: int = 0
    groups_reconciled: int = 0
    stragglers_parked_for_review: int = 0
    counts_by_motivo: dict = field(
        default_factory=lambda: {m: 0 for m in _MOTIVOS}
    )
    clientes_created: int = 0
    touches_created: int = 0
    merges_created: int = 0
    negociacoes_repointed: int = 0
    negociacoes_already_pointed: int = 0
    negociacoes_orphaned: list = field(default_factory=list)

    @property
    def touches_expected(self) -> int:
        """§4 P1.2's arithmetic check: `count(cliente_touches) ==
        count(leads) + count(meta_ads_leads)`. Only meaningful as a total
        across ALL runs (this report only counts what THIS call did) —
        callers asserting the platform invariant should compare the
        cumulative `cliente_touches` row count against
        `leads_scanned + meta_leads_scanned` from a single from-empty run,
        or against a fresh full scan."""
        return self.leads_scanned + self.meta_leads_scanned

    @property
    def auto_merge_groups(self) -> int:
        return sum(self.counts_by_motivo[m] for m in ("C1", "C2", "C3"))

    @property
    def review_groups(self) -> int:
        return sum(self.counts_by_motivo[m] for m in ("C4", "C5", "C6"))

    def as_dict(self) -> dict:
        return {
            "org_id": self.org_id,
            "dry_run": self.dry_run,
            "leads_scanned": self.leads_scanned,
            "meta_leads_scanned": self.meta_leads_scanned,
            "keyless_clientes": self.keyless_clientes,
            "groups_total": self.groups_total,
            "groups_reconciled": self.groups_reconciled,
            "stragglers_parked_for_review": self.stragglers_parked_for_review,
            "counts_by_motivo": dict(self.counts_by_motivo),
            "auto_merge_groups": self.auto_merge_groups,
            "review_groups": self.review_groups,
            "clientes_created": self.clientes_created,
            "touches_created": self.touches_created,
            "touches_expected": self.touches_expected,
            "merges_created": self.merges_created,
            "negociacoes_repointed": self.negociacoes_repointed,
            "negociacoes_already_pointed": self.negociacoes_already_pointed,
            "negociacoes_orphaned": list(self.negociacoes_orphaned),
        }


# ─── low-level table helpers ─────────────────────────────────────────────


def _t(client: Any, name: str):
    # `client` is already `social_wiring`-scoped — see the module
    # docstring's "client MUST ALREADY BE SCHEMA-SCOPED" section for why
    # this deliberately does NOT call `.schema(_SCHEMA)` here.
    return client.table(name)


def _select_all(
    client: Any, table: str, org_id: UUID, columns: str = "*"
) -> list[dict]:
    """Fetch EVERY row for `org_id`, paginating past PostgREST's row cap.
    Mirrors `imoveis_service.ImoveisService._select_all` — same bug class,
    same fix."""
    out: list[dict] = []
    start = 0
    while True:
        result = (
            _t(client, table)
            .select(columns)
            .eq("org_id", str(org_id))
            .range(start, start + _PAGE - 1)
            .execute()
        )
        rows = result.data or []
        out.extend(rows)
        if len(rows) < _PAGE:
            return out
        start += _PAGE


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── backfill ────────────────────────────────────────────────────────────


def run_backfill(client: Any, org_id: UUID, *, dry_run: bool = False) -> BackfillReport:
    """Resolve identity for every `leads`/`meta_ads_leads` row for `org_id`
    not already represented in `cliente_touches`, and repoint
    `negociacoes_venda.cliente_id` for whatever that resolution newly
    covers. See the module docstring for the idempotency/concurrency
    contract and the dry-run/prod-read note.
    """
    report = BackfillReport(org_id=str(org_id), dry_run=dry_run)

    leads_rows = _select_all(client, "leads", org_id)
    meta_rows = _select_all(client, "meta_ads_leads", org_id)
    report.leads_scanned = len(leads_rows)
    report.meta_leads_scanned = len(meta_rows)

    sources = [ident.leads_row_to_source(r) for r in leads_rows] + [
        ident.meta_lead_row_to_source(r) for r in meta_rows
    ]

    existing_touch_keys = set() if dry_run else _existing_touch_keys(client, org_id)
    new_sources = [
        s for s in sources if (s.origem_tabela, s.origem_id) not in existing_touch_keys
    ]

    keyed = [s for s in new_sources if s.chave_canonica]
    keyless = [s for s in new_sources if not s.chave_canonica]

    report.keyless_clientes += len(keyless)
    for row in keyless:
        _create_clientes_for_cluster(
            client, org_id,
            nome=ident.longest_raw_name([row]),
            chave_canonica=None, chave_tipo=None, identidade_incerta=True,
            members=[row], report=report, dry_run=dry_run,
        )

    groups: dict[str, list[SourceRow]] = {}
    for s in keyed:
        groups.setdefault(s.chave_canonica, []).append(s)
    report.groups_total += len(groups)

    for group_rows in groups.values():
        _resolve_group(client, org_id, group_rows, report, dry_run=dry_run)

    if not dry_run:
        _repoint_negociacoes(client, org_id, report)

    return report


def _existing_touch_keys(client: Any, org_id: UUID) -> set[tuple[str, str]]:
    rows = _select_all(client, "cliente_touches", org_id, columns="origem_tabela,origem_id")
    return {(r["origem_tabela"], r["origem_id"]) for r in rows}


def _find_existing_for_key(client: Any, org_id: UUID, chave_canonica: str) -> list[dict]:
    """Every cliente already touching this key — a resolved keyed survivor
    AND/OR unresolved review candidates — found through
    `cliente_touches.chave_canonica`, never through `clientes.chave_canonica`
    alone (a review candidate's own key is NULL by design)."""
    touch_rows = (
        _t(client, "cliente_touches")
        .select("cliente_id")
        .eq("org_id", str(org_id))
        .eq("chave_canonica", chave_canonica)
        .execute()
    ).data or []
    cliente_ids = sorted({r["cliente_id"] for r in touch_rows})
    if not cliente_ids:
        return []
    rows = _t(client, "clientes").select("*").in_("id", cliente_ids).execute().data or []
    return rows


def _resolve_group(
    client: Any, org_id: UUID, rows: list[SourceRow], report: BackfillReport, *, dry_run: bool
) -> None:
    key = rows[0].chave_canonica
    existing = [] if dry_run else _find_existing_for_key(client, org_id, key)

    if not existing:
        classification = ident.classify_group(rows)
        report.counts_by_motivo[classification.motivo] += 1
        _create_clusters(client, org_id, rows, classification, report, dry_run=dry_run)
        return

    report.groups_reconciled += 1
    _reconcile_against_existing(client, org_id, rows, existing, report, dry_run=dry_run)


def _create_clusters(
    client: Any,
    org_id: UUID,
    rows: list[SourceRow],
    classification: "ident.GroupClassification",
    report: BackfillReport,
    *,
    dry_run: bool,
) -> None:
    key = rows[0].chave_canonica
    tipo = rows[0].chave_tipo
    clusters = ident.build_clusters(rows, classification)

    if classification.auto_merge:
        members = clusters[None]
        cliente_id = _create_clientes_for_cluster(
            client, org_id,
            nome=ident.longest_raw_name(members),
            chave_canonica=key, chave_tipo=tipo, identidade_incerta=False,
            members=members, report=report, dry_run=dry_run,
        )

        named = list(classification.named_clusters.items())
        if len(named) >= 2:
            survivor_norm, _survivor_rows = max(
                named, key=lambda kv: len(ident.longest_raw_name(kv[1]) or "")
            )
            for norm, sub_members in named:
                if norm == survivor_norm:
                    continue
                _record_merge(
                    client, org_id,
                    cliente_id_sobrevivente=cliente_id,
                    nome_absorvido=ident.longest_raw_name(sub_members),
                    chave_canonica_absorvido=key,
                    chave_tipo_absorvido=tipo,
                    identidade_incerta_absorvido=False,
                    motivo=classification.motivo,
                    automatico=True,
                    members=sub_members,
                    report=report,
                    dry_run=dry_run,
                )
        return

    # Review: one cliente per cluster (including a lone nameless cluster,
    # if any — see `identidade_service.build_clusters`), none claims the key.
    for members in clusters.values():
        _create_clientes_for_cluster(
            client, org_id,
            nome=ident.longest_raw_name(members),
            chave_canonica=None, chave_tipo=None, identidade_incerta=True,
            members=members, report=report, dry_run=dry_run,
        )


def _reconcile_against_existing(
    client: Any,
    org_id: UUID,
    rows: list[SourceRow],
    existing: list[dict],
    report: BackfillReport,
    *,
    dry_run: bool,
) -> None:
    existing_by_norm = {
        ident.normalize_name(r.get("nome")): r for r in existing if r.get("nome")
    }
    by_norm: dict[str, list[SourceRow]] = {}
    for r in rows:
        by_norm.setdefault(ident.normalize_name(r.nome), []).append(r)

    for norm, members in by_norm.items():
        target = existing_by_norm.get(norm)
        if target is None and not norm and len(existing) == 1:
            # A lone nameless straggler with exactly one existing identity
            # for this key — mirrors C3's "nameless rides along" rule.
            target = existing[0]

        if target is not None:
            _attach_touches(client, org_id, target["id"], members, report, dry_run=dry_run)
            continue

        report.stragglers_parked_for_review += 1
        _create_clientes_for_cluster(
            client, org_id,
            nome=ident.longest_raw_name(members),
            chave_canonica=None, chave_tipo=None, identidade_incerta=True,
            members=members, report=report, dry_run=dry_run,
        )


def _create_clientes_for_cluster(
    client: Any,
    org_id: UUID,
    *,
    nome: Optional[str],
    chave_canonica: Optional[str],
    chave_tipo: Optional[str],
    identidade_incerta: bool,
    members: list[SourceRow],
    report: BackfillReport,
    dry_run: bool,
) -> str:
    primeiro, ultimo = ident.span([m.ocorreu_em for m in members])
    cliente_id = str(uuid4())
    row = {
        "id": cliente_id,
        "org_id": str(org_id),
        "nome": nome,
        "chave_canonica": chave_canonica,
        "chave_tipo": chave_tipo,
        "identidade_incerta": identidade_incerta,
        "ativo": True,
        "primeiro_contato_em": primeiro,
        "ultimo_contato_em": ultimo,
        "created_at": _now(),
    }
    report.clientes_created += 1
    if not dry_run:
        _t(client, "clientes").insert(row).execute()

    # The touch carries the REAL key even when the cliente itself does not
    # claim it (review candidates) — see the migration header.
    real_key = members[0].chave_canonica
    _insert_touches(client, org_id, cliente_id, members, real_key, report, dry_run=dry_run)
    return cliente_id


def _insert_touches(
    client: Any,
    org_id: UUID,
    cliente_id: str,
    members: list[SourceRow],
    chave_canonica: Optional[str],
    report: BackfillReport,
    *,
    dry_run: bool,
) -> None:
    payload = [
        {
            "id": str(uuid4()),
            "cliente_id": cliente_id,
            "org_id": str(org_id),
            "origem_tabela": r.origem_tabela,
            "origem_id": r.origem_id,
            "ocorreu_em": r.ocorreu_em,
            "nome": r.nome,
            "chave_canonica": chave_canonica,
            "origem_label": r.origem_label,
            "created_at": _now(),
        }
        for r in members
    ]
    report.touches_created += len(payload)
    if dry_run or not payload:
        return
    _t(client, "cliente_touches").insert(payload).execute()


def _attach_touches(
    client: Any,
    org_id: UUID,
    cliente_id: str,
    members: list[SourceRow],
    report: BackfillReport,
    *,
    dry_run: bool,
) -> None:
    key = members[0].chave_canonica
    _insert_touches(client, org_id, cliente_id, members, key, report, dry_run=dry_run)
    if not dry_run:
        _recompute_span(client, org_id, cliente_id)


def _recompute_span(client: Any, org_id: UUID, cliente_id: str) -> None:
    rows = (
        _t(client, "cliente_touches")
        .select("ocorreu_em")
        .eq("cliente_id", cliente_id)
        .execute()
    ).data or []
    if not rows:
        return
    primeiro, ultimo = ident.span([r["ocorreu_em"] for r in rows])
    _t(client, "clientes").update(
        {"primeiro_contato_em": primeiro, "ultimo_contato_em": ultimo, "updated_at": _now()}
    ).eq("id", cliente_id).eq("org_id", str(org_id)).execute()


def _record_merge(
    client: Any,
    org_id: UUID,
    *,
    cliente_id_sobrevivente: str,
    nome_absorvido: Optional[str],
    chave_canonica_absorvido: Optional[str],
    chave_tipo_absorvido: Optional[str],
    identidade_incerta_absorvido: bool,
    motivo: str,
    automatico: bool,
    members: list[SourceRow],
    report: BackfillReport,
    dry_run: bool,
) -> None:
    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "cliente_id_sobrevivente": cliente_id_sobrevivente,
        # Synthetic — no row was ever inserted for the losing cluster
        # (would collide with uq_sw_clientes_org_chave). See the migration
        # header + identidade_service's module docstring.
        "cliente_id_absorvido": str(uuid4()),
        "motivo": motivo,
        "automatico": automatico,
        "nome_absorvido": nome_absorvido,
        "chave_canonica_absorvido": chave_canonica_absorvido,
        "chave_tipo_absorvido": chave_tipo_absorvido,
        "identidade_incerta_absorvido": identidade_incerta_absorvido,
        "touches_movidos": [
            {"origem_tabela": r.origem_tabela, "origem_id": r.origem_id} for r in members
        ],
        "created_at": _now(),
    }
    report.merges_created += 1
    if dry_run:
        return
    _t(client, "cliente_merges").insert(row).execute()


def _repoint_negociacoes(client: Any, org_id: UUID, report: BackfillReport) -> None:
    rows = (
        _t(client, "negociacoes_venda")
        .select("id,lead_id,meta_ads_lead_id,cliente_id")
        .eq("org_id", str(org_id))
        .execute()
    ).data or []

    touches = _select_all(
        client, "cliente_touches", org_id, columns="origem_tabela,origem_id,cliente_id"
    )
    by_origem = {(t["origem_tabela"], t["origem_id"]): t["cliente_id"] for t in touches}

    for n in rows:
        if n.get("cliente_id"):
            report.negociacoes_already_pointed += 1
            continue

        origem: Optional[tuple[str, str]] = None
        if n.get("lead_id"):
            origem = ("leads", str(n["lead_id"]))
        elif n.get("meta_ads_lead_id"):
            origem = ("meta_ads_leads", str(n["meta_ads_lead_id"]))

        cliente_id = by_origem.get(origem) if origem else None
        if cliente_id is None:
            report.negociacoes_orphaned.append(n["id"])
            continue

        _t(client, "negociacoes_venda").update({"cliente_id": cliente_id}).eq(
            "id", n["id"]
        ).execute()
        report.negociacoes_repointed += 1


# ─── merge / undo (also used by Slice B's review router) ────────────────


def _require_cliente(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    resp = (
        _t(client, "clientes")
        .select("*")
        .eq("id", str(cliente_id))
        .eq("org_id", str(org_id))
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise ClienteNotFound(f"cliente {cliente_id} not found for org {org_id}")
    return rows[0]


def merge_clientes(
    client: Any,
    org_id: UUID,
    *,
    cliente_id_sobrevivente: UUID,
    cliente_id_absorvido: UUID,
    motivo: str,
    automatico: bool = False,
) -> str:
    """Fold `cliente_id_absorvido` into `cliente_id_sobrevivente`: move
    every touch, snapshot the absorbed row into `cliente_merges` (D3),
    delete the absorbed row, recompute the survivor's span. Returns the
    new `cliente_merges.id`.

    This is for merging two rows that BOTH already exist as real
    `clientes` rows — the shape `POST /api/clientes/revisao/{grupo}/merge`
    needs (Slice B, `automatico=False`). The backfill's own automatic
    C2/C3 folding does NOT call this: it never inserts the losing cluster
    as a real row in the first place (see `_record_merge`).
    """
    absorbed = _require_cliente(client, org_id, cliente_id_absorvido)
    _require_cliente(client, org_id, cliente_id_sobrevivente)

    touches = (
        _t(client, "cliente_touches")
        .select("origem_tabela,origem_id")
        .eq("cliente_id", str(cliente_id_absorvido))
        .execute()
    ).data or []

    _t(client, "cliente_touches").update(
        {"cliente_id": str(cliente_id_sobrevivente)}
    ).eq("cliente_id", str(cliente_id_absorvido)).execute()

    merge_id = str(uuid4())
    _t(client, "cliente_merges").insert(
        {
            "id": merge_id,
            "org_id": str(org_id),
            "cliente_id_sobrevivente": str(cliente_id_sobrevivente),
            "cliente_id_absorvido": str(cliente_id_absorvido),
            "motivo": motivo,
            "automatico": automatico,
            "nome_absorvido": absorbed.get("nome"),
            "chave_canonica_absorvido": absorbed.get("chave_canonica"),
            "chave_tipo_absorvido": absorbed.get("chave_tipo"),
            "identidade_incerta_absorvido": bool(absorbed.get("identidade_incerta")),
            "touches_movidos": [
                {"origem_tabela": t["origem_tabela"], "origem_id": t["origem_id"]}
                for t in touches
            ],
            "created_at": _now(),
        }
    ).execute()

    _t(client, "clientes").delete().eq("id", str(cliente_id_absorvido)).eq(
        "org_id", str(org_id)
    ).execute()

    _recompute_span(client, org_id, str(cliente_id_sobrevivente))
    return merge_id


def undo_merge(client: Any, org_id: UUID, merge_id: UUID) -> str:
    """Reverse a merge USING ONLY `cliente_merges` (D3) — recreates a new
    cliente from the absorbed snapshot, moves back exactly the touches
    `touches_movidos` names, marks the merge undone. Returns the new
    cliente's id (deliberately a NEW id, not the original
    `cliente_id_absorvido` — see that column's `COMMENT ON COLUMN` in the
    migration)."""
    resp = (
        _t(client, "cliente_merges")
        .select("*")
        .eq("id", str(merge_id))
        .eq("org_id", str(org_id))
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise MergeNotFound(f"cliente_merges {merge_id} not found for org {org_id}")
    merge = rows[0]
    if merge.get("desfeito_em"):
        raise MergeAlreadyUndone(f"cliente_merges {merge_id} was already undone")

    new_id = str(uuid4())
    _t(client, "clientes").insert(
        {
            "id": new_id,
            "org_id": str(org_id),
            "nome": merge.get("nome_absorvido"),
            "chave_canonica": merge.get("chave_canonica_absorvido"),
            "chave_tipo": merge.get("chave_tipo_absorvido"),
            "identidade_incerta": bool(merge.get("identidade_incerta_absorvido")),
            "ativo": True,
            "created_at": _now(),
        }
    ).execute()

    for pair in merge.get("touches_movidos") or []:
        _t(client, "cliente_touches").update({"cliente_id": new_id}).eq(
            "origem_tabela", pair["origem_tabela"]
        ).eq("origem_id", pair["origem_id"]).execute()

    _t(client, "cliente_merges").update({"desfeito_em": _now()}).eq(
        "id", str(merge_id)
    ).execute()

    _recompute_span(client, org_id, new_id)
    _recompute_span(client, org_id, merge["cliente_id_sobrevivente"])
    return new_id


# ─── read surface (Slice B builds routers on top of these) ──────────────


def list_clientes(
    client: Any,
    org_id: UUID,
    *,
    ativo: Optional[bool] = True,
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 24,
) -> dict:
    """Board list (§5 `GET /api/clientes`). Default active-only (D4).
    `corretor_id` filtering is NOT implemented here — a cliente has no
    direct corretor column (it is decoupled from a single lead's
    corretor by design); resolving it needs a join through
    `cliente_touches` -> `leads.corretor_id` that is a routing/query
    decision, not a resolution-engine one. Flagged for Slice B, not
    built here (see the Slice A delivery note)."""
    query = _t(client, "clientes").select("*", count="exact").eq("org_id", str(org_id))
    if ativo is not None:
        query = query.eq("ativo", ativo)
    if q:
        query = query.ilike("nome", f"%{q}%")

    start = max(0, (page - 1) * page_size)
    result = (
        query.order("ultimo_contato_em", desc=True)
        .range(start, start + page_size - 1)
        .execute()
    )
    rows = result.data or []
    total = getattr(result, "count", None)
    total = len(rows) if total is None else total
    pages = max(1, (total + page_size - 1) // page_size)
    return {"items": rows, "total": total, "page": page, "pages": pages}


def get_cliente(client: Any, org_id: UUID, cliente_id: UUID) -> Optional[dict]:
    try:
        return _require_cliente(client, org_id, cliente_id)
    except ClienteNotFound:
        return None


def get_touches(
    client: Any, org_id: UUID, cliente_id: UUID, *, page: int = 1, page_size: int = 50
) -> dict:
    """The timeline feed (§5 `GET /api/clientes/{id}/touches`), chronological."""
    query = (
        _t(client, "cliente_touches")
        .select("*", count="exact")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
    )
    start = max(0, (page - 1) * page_size)
    result = query.order("ocorreu_em", desc=True).range(start, start + page_size - 1).execute()
    rows = result.data or []
    total = getattr(result, "count", None)
    total = len(rows) if total is None else total
    pages = max(1, (total + page_size - 1) // page_size)
    return {"items": rows, "total": total, "page": page, "pages": pages}


def update_cliente(client: Any, org_id: UUID, cliente_id: UUID, **updates: Any) -> dict:
    """PATCH (§5 `PATCH /api/clientes/{id}`) — nome, ativo/arquivado (D4)."""
    allowed = {"nome", "ativo", "arquivado_em", "inativo_em"}
    payload = {k: v for k, v in updates.items() if k in allowed}
    if not payload:
        return _require_cliente(client, org_id, cliente_id)

    payload["updated_at"] = _now()
    resp = (
        _t(client, "clientes")
        .update(payload)
        .eq("id", str(cliente_id))
        .eq("org_id", str(org_id))
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise ClienteNotFound(f"cliente {cliente_id} not found for org {org_id}")
    return rows[0]


def list_review_groups(client: Any, org_id: UUID) -> list[dict]:
    """The review queue (§5 `GET /api/clientes/revisao`) — every set of
    `identidade_incerta` clientes that shares a real key, discovered
    through `cliente_touches.chave_canonica` (never through
    `clientes.chave_canonica`, which is NULL for all of them by design).
    The 399 keyless clientes never surface here: they carry no
    `cliente_touches.chave_canonica` at all, so they can never form a
    group of size > 1. `motivo` is recomputed live from the candidates'
    `nome` values via `identidade_service.classify_names` rather than
    stored — it is a pure function of names that are already sitting on
    the rows, so persisting it would be a second source of truth that
    could drift the moment a candidate's `nome` is edited.
    """
    incerta_rows = (
        _t(client, "clientes")
        .select("*")
        .eq("org_id", str(org_id))
        .eq("identidade_incerta", True)
        .execute()
    ).data or []
    if not incerta_rows:
        return []

    ids = [r["id"] for r in incerta_rows]
    touch_rows = (
        _t(client, "cliente_touches")
        .select("cliente_id,chave_canonica")
        .eq("org_id", str(org_id))
        .in_("cliente_id", ids)
        .execute()
    ).data or []
    key_by_cliente: dict[str, str] = {}
    for t in touch_rows:
        if t.get("chave_canonica"):
            key_by_cliente.setdefault(t["cliente_id"], t["chave_canonica"])

    grouped: dict[str, list[dict]] = {}
    for r in incerta_rows:
        key = key_by_cliente.get(r["id"])
        if key:
            grouped.setdefault(key, []).append(r)

    groups: list[dict] = []
    for key, candidatos in grouped.items():
        if len(candidatos) < 2:
            continue  # a single incerta cliente under this key isn't a conflict
        motivo, _auto_merge = ident.classify_names([c.get("nome") for c in candidatos])
        groups.append({"chave_canonica": key, "motivo": motivo, "candidatos": candidatos})
    return groups
