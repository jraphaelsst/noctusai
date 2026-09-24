"""`clientes` (person layer) — CRUD + the identity-resolution backfill.

Contract: `products/social-wiring/projects/lead-card-hub-p1-PROJECT.md` §4/§7.
The matching algorithm itself (the C1-C6 predicate, name normalization,
`SourceRow` extraction) lives in `identidade_service.py`, kept I/O-free so it
is unit-testable without a database (`048_clientes_person_layer.sql`'s header
explains why). This module is the I/O layer: it fetches `leads` /
`meta_ads_leads` rows, calls into `identidade_service` to decide what to do
with them, and writes `clientes` / `cliente_touches` / `cliente_merges` /
`atendimentos.cliente_id`.

Slice B (routers, contract §5) imports this module's public functions —
`list_clientes`, `get_cliente`, `get_touches`, `update_cliente`,
`list_review_groups`, `merge_clientes`, `undo_merge` — and does not modify
it (see the PROJECT.md §6 slice table: B's file list is routers + main.py
only).

RUNNING THE BACKFILL — DRY-RUN FIRST (feeds contract §7)
----------------------------------------------------------
`run_backfill(client, org_id, dry_run=True)` only ever SELECTs from
`leads`/`meta_ads_leads` — it never touches `clientes`/`cliente_touches`/
`cliente_merges`/`atendimentos`, so it can run against the LIVE
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
3. `atendimentos.cliente_id` repoint only ever touches rows where
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

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.primitives.exceptions import ValidationError_

from app.services import identidade_service as ident
from app.services import table_reads
from app.services.identidade_service import SourceRow

logger = logging.getLogger(__name__)

__all__ = [
    "ClienteNotFound",
    "MergeNotFound",
    "MergeAlreadyUndone",
    "ClienteEhSobreviventeDeMerge",
    "BackfillReport",
    "run_backfill",
    "attach_lead_now",
    "list_clientes",
    "get_cliente",
    "get_touches",
    "update_cliente",
    "excluir_cliente",
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


class ClienteEhSobreviventeDeMerge(Exception):
    """`excluir_cliente` blocked: `cliente_merges.cliente_id_sobrevivente`
    carries NO `ON DELETE` (migration 048's header — undo must keep
    resolving to a live row), so this cliente cannot be hard-deleted while
    it is still the surviving side of a merge. Raised BEFORE any mutation
    (a proactive read, not a caught Postgres FK-violation) so the router
    can answer with a clear pt-BR 409 instead of a raw constraint error."""


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
    atendimentos_repointed: int = 0
    atendimentos_already_pointed: int = 0
    atendimentos_orphaned: list = field(default_factory=list)
    # P1.4 completion (lead-card-hub roadmap §1/§5): a Meta lead fires BOTH
    # `spawn_funil_card_on_lead` and `spawn_funil_card_on_meta_lead`, so two
    # `atendimentos` rows can share one `cliente_id`. This counts rows
    # this run marked `substituida_por` on — see `_collapse_atendimentos`.
    atendimentos_collapsed: int = 0
    # D16 (roadmap lead-card-hub-2026-08) — a new touch attaching to a
    # cliente the inactivity sweep had previously marked inactive flips it
    # back on right here (`_reactivate_if_inactive`). Counted separately
    # from `clientes_created`: this is an UPDATE on an EXISTING row, not a
    # new identity.
    clientes_reactivated: int = 0

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
            "atendimentos_repointed": self.atendimentos_repointed,
            "atendimentos_already_pointed": self.atendimentos_already_pointed,
            "atendimentos_orphaned": list(self.atendimentos_orphaned),
            "atendimentos_collapsed": self.atendimentos_collapsed,
            "clientes_reactivated": self.clientes_reactivated,
        }


# ─── low-level table helpers ─────────────────────────────────────────────


def _t(client: Any, name: str):
    # `client` is already `social_wiring`-scoped — see the module
    # docstring's "client MUST ALREADY BE SCHEMA-SCOPED" section for why
    # this deliberately does NOT call `.schema(_SCHEMA)` here.
    return client.table(name)


_IN_FILTER_BATCH = table_reads.IN_FILTER_BATCH


# Canonical definition in `app.services.table_reads` — this was the first
# copy, `card_hub` was the second, `imovel_hub` the third. Kept as an alias
# so `list_review_groups`' call site reads unchanged.
_batched = table_reads.batched


def _paginate_query(run) -> list[dict]:
    """Drain a range-parameterised query past PostgREST's 1 000-row cap.
    `run(start, end)` must apply `.range(start, end)` and execute."""
    out: list[dict] = []
    start = 0
    while True:
        rows = (run(start, start + _PAGE - 1)).data or []
        out.extend(rows)
        if len(rows) < _PAGE:
            return out
        start += _PAGE


def _select_all_where(
    client: Any, table: str, org_id: UUID, eq_filters: dict, columns: str = "*"
) -> list[dict]:
    """`_select_all` plus extra equality filters, paginated."""
    out: list[dict] = []
    start = 0
    while True:
        query = _t(client, table).select(columns).eq("org_id", str(org_id))
        for k, v in eq_filters.items():
            query = query.eq(k, v)
        rows = query.range(start, start + _PAGE - 1).execute().data or []
        out.extend(rows)
        if len(rows) < _PAGE:
            return out
        start += _PAGE


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
    `atendimentos.cliente_id` for whatever that resolution newly
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
        # 🔴 SOURCES THAT ALREADY HAVE A TOUCH ARE NOT DONE WITH.
        #
        # Everything above deliberately skips them (`new_sources`), because
        # identity resolution must not re-cluster a person on every pass. But
        # the source ROW keeps changing after its touch is written — a lead
        # created with an empty name and corrected 27 minutes later is the
        # exact case reported from production (`José Roberto`, 2026-09-02):
        # the cliente was created 2s after the lead, from a row that was still
        # blank, and NOTHING ever revisited it. The correction landed on the
        # lead and never reached the person.
        #
        # So contact data is refreshed from ALL sources, separately from
        # clustering. Fill-if-empty, so this can run every pass and can never
        # undo an operator's edit.
        _refresh_contato_from_sources(client, org_id, sources)
        _repoint_atendimentos(client, org_id, report)
        # P1.4 completion: collapse whatever now shares a cliente_id — both
        # the sets this run just repointed AND any that already existed
        # from a prior run. Steady-state by construction: this call sits
        # inside the SAME 6-hourly sweep `clientes_backfill_job` already
        # runs per org, so a new duplicate pair never needs its own
        # one-shot migration the way `048`'s did (see
        # `clientes_backfill_job.py`'s module docstring for that lesson).
        _collapse_atendimentos(client, org_id, report)

    return report


def attach_lead_now(client: Any, org_id: UUID, lead_row: dict) -> Optional[str]:
    """Resolve + attach ONE just-created `leads` row's cliente SYNCHRONOUSLY.

    🔴 Why this exists (found 2026-09-21, verified live). `create_lead`
    already schedules `clientes_backfill_job.run_now` as a `BackgroundTask` —
    but that closes the gap to "a couple of seconds", and `contato_norm` is
    already present and fully resolvable at the moment this function is
    called: deferring it to ANY sweep, even a fast one, buys nothing. This
    runs BEFORE the 201 is returned, so a hand-created lead's card is
    workable (has a titular `stage_gate` will accept) the instant the
    operator sees it, not a background-task tick later.

    NOT a second person-resolution implementation. A keyed source reuses
    `_resolve_group` — the exact function `run_backfill` groups keyed
    sources through, called here with a group of one — so dedupe-by-key,
    the C1-C6 name classification, and `cliente_touches`/merge bookkeeping
    are the identical code path the steady-state sweep uses. A keyless
    source reuses `_create_clientes_for_cluster` with
    `identidade_incerta=True` — `run_backfill`'s own keyless branch — so a
    lead with no usable `contato_norm` still gets an uncertain-identity
    cliente attached (a titular `stage_gate` accepts) rather than being left
    unresolved; "could not resolve to a canonical key" is NOT "attachment
    failed" and must never block or fail lead creation.

    Only the FINAL step — pointing `atendimentos.cliente_id` at the result
    — is written narrowly here rather than via `_repoint_atendimentos`:
    that helper scans the ORG'S ENTIRE `atendimentos` table, which is the
    right cost for a periodic sweep and the wrong cost to add to every
    single `POST /api/leads`. This looks up and repoints only the one row
    migration 034's trigger just spawned for `lead_row["id"]`.

    Never raises. `create_lead` must not fail because identity resolution
    did — a rare race (two leads sharing one `contato_norm` created in the
    same instant, unleased, unlike the sweep) can trip a unique-constraint
    error on `clientes`; the lead itself is already saved by the time this
    runs, so a failure here is swallowed, logged, and left for the next
    `clientes_backfill` sweep (background task on this request, or the
    scheduled steady-state pass) to reconcile — which it can, because this
    function's writes are the SAME idempotent operations that sweep already
    performs. Returns the attached `cliente_id`, or `None` when nothing was
    attached (logged, not raised).
    """
    try:
        source = ident.leads_row_to_source(lead_row)
        report = BackfillReport(org_id=str(org_id), dry_run=False)
        if source.chave_canonica:
            _resolve_group(client, org_id, [source], report, dry_run=False)
        else:
            report.keyless_clientes += 1
            _create_clientes_for_cluster(
                client, org_id,
                nome=ident.longest_raw_name([source]),
                chave_canonica=None, chave_tipo=None, identidade_incerta=True,
                members=[source], report=report, dry_run=False,
            )
        cliente_id = _cliente_id_for_source(client, org_id, source)
        if cliente_id:
            _repoint_one_atendimento(client, org_id, source, cliente_id)
        return cliente_id
    except Exception:
        logger.error(
            "clientes_service.attach_lead_now: failed to attach lead %s "
            "(org %s) synchronously — the card stays unworkable until the "
            "next clientes_backfill sweep picks it up.",
            lead_row.get("id"), org_id, exc_info=True,
        )
        return None


def _cliente_id_for_source(client: Any, org_id: UUID, source: SourceRow) -> Optional[str]:
    """The `cliente_id` a resolved source's touch was just written under.

    Single-row, indexed lookup — not `_existing_touch_keys`'s org-wide scan
    — since the caller already knows exactly which `(origem_tabela,
    origem_id)` it just resolved."""
    rows = (
        _t(client, "cliente_touches")
        .select("cliente_id")
        .eq("org_id", str(org_id))
        .eq("origem_tabela", source.origem_tabela)
        .eq("origem_id", source.origem_id)
        .limit(1)
        .execute()
    ).data or []
    return rows[0]["cliente_id"] if rows else None


def _repoint_one_atendimento(
    client: Any, org_id: UUID, source: SourceRow, cliente_id: str
) -> None:
    """`_repoint_atendimentos`'s update, scoped to the ONE `atendimentos` row
    migration 034's trigger spawned for this source — never a full-table
    scan (see `attach_lead_now`'s docstring for why that cost does not
    belong on the create-lead request path). The `cliente_id IS NULL`
    guard makes this idempotent against a concurrent sweep that already
    repointed the same row."""
    origem_col = "lead_id" if source.origem_tabela == "leads" else "meta_ads_lead_id"
    _t(client, "atendimentos").update({"cliente_id": cliente_id}).eq(
        "org_id", str(org_id)
    ).eq(origem_col, source.origem_id).is_("cliente_id", "null").execute()


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
            # An already-resolved person picks up contact data that only
            # arrived on this later touch — fill-if-empty, so nothing an
            # operator typed is overwritten.
            _enrich_cliente(client, target["id"], members, dry_run=dry_run)
            continue

        report.stragglers_parked_for_review += 1
        _create_clientes_for_cluster(
            client, org_id,
            nome=ident.longest_raw_name(members),
            chave_canonica=None, chave_tipo=None, identidade_incerta=True,
            members=members, report=report, dry_run=dry_run,
        )


def _refresh_contato_from_sources(
    client: Any, org_id: UUID, sources: list[SourceRow]
) -> None:
    """Re-read EVERY source and top up its cliente's blank contact columns.

    This is the half that makes a lead EDIT reach the person. Clustering is
    deliberately one-shot per source (a touch is written once and the row is
    skipped forever after), which is right for identity — re-clustering on
    every pass would let a person's group churn. It is wrong for CONTACT DATA,
    which the operator keeps correcting on the lead long after the touch was
    written.

    Cheap and idempotent: one read of the org's touches, then an UPDATE only
    for clientes that actually have a blank to fill. A steady-state pass finds
    nothing and writes nothing.
    """
    touches = _select_all(
        client, "cliente_touches", org_id, columns="cliente_id,origem_tabela,origem_id"
    )
    if not touches:
        return

    por_origem = {(s.origem_tabela, s.origem_id): s for s in sources}
    membros_por_cliente: dict[str, list[SourceRow]] = {}
    for t in touches:
        origem = por_origem.get((t.get("origem_tabela"), t.get("origem_id")))
        if origem is not None:
            membros_por_cliente.setdefault(t["cliente_id"], []).append(origem)

    for cliente_id, members in membros_por_cliente.items():
        _enrich_cliente(client, cliente_id, members, dry_run=False)


def _contato_dos_membros(members: list[SourceRow]) -> dict[str, str]:
    """`celular` / `email` for a cluster — first member that supplies each.

    Only non-empty keys are returned, so this can be splatted into an INSERT
    without writing NULLs, and into an UPDATE without clobbering a value an
    operator typed. "First wins" rather than "last wins" because members are
    the sources that resolved to one person and the earliest is the one the
    rest were matched against.
    """
    out: dict[str, str] = {}
    for m in members:
        if "celular" not in out and m.telefone:
            out["celular"] = m.telefone
        if "email" not in out and m.email:
            out["email"] = m.email
    return out


def _enrich_cliente(
    client: Any, cliente_id: str, members: list[SourceRow], *, dry_run: bool
) -> None:
    """Fill a cliente's blank `nome` / `celular` / `email` from new touches.

    🔴 FILL-IF-EMPTY, never overwrite. A cliente's columns can hold values an
    operator typed by hand, and a later campaign touch carrying a worse
    spelling of the same person must not silently replace them. Only a column
    that is currently NULL/blank is written.

    This is what lets an ALREADY-RESOLVED person pick up contact data that
    arrives after their cliente row was created — the case where a keyless
    cluster was made first and the phone only showed up on a later touch.
    """
    if dry_run:
        return
    candidatos = _contato_dos_membros(members)
    nome = ident.longest_raw_name(members)
    if nome:
        candidatos["nome"] = nome
    if not candidatos:
        return

    atual = _t(client, "clientes").select("nome, celular, email").eq("id", cliente_id).execute()
    linha = (atual.data or [None])[0]
    if not linha:
        return

    patch = {
        campo: valor
        for campo, valor in candidatos.items()
        if not (linha.get(campo) or "").strip()
    }
    if patch:
        _t(client, "clientes").update(patch).eq("id", cliente_id).execute()


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
        # The person's CONTACT DATA, not the identity key. Without these the
        # card showed "—" beside a lead whose phone was in the column, and the
        # stage gate refused the move because the checklist had nothing to
        # tick — including for KEYLESS clusters, which lose the key by
        # definition and so used to lose the phone with it.
        **_contato_dos_membros(members),
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
        _reactivate_if_inactive(client, org_id, cliente_id, report)


def _reactivate_if_inactive(
    client: Any, org_id: UUID, cliente_id: str, report: BackfillReport
) -> None:
    """D16's reactivation half: a fresh touch attaching to an EXISTING
    cliente the inactivity sweep (`clientes_inactivity_service.py`) had
    put to sleep means the person is reachable again — leaving them
    hidden after a new inquiry would be the exact same silent-
    disappearance failure the sweep exists to avoid, just inverted.

    Deliberately lives HERE (touch-insert time), not in the sweep: this is
    the one place a subsequent `clientes_backfill_job` run already
    discovers a new touch landing on an already-resolved identity
    (`_reconcile_against_existing` -> `_attach_touches`), so reactivating
    right here costs nothing extra — the sweep would otherwise have to
    re-scan every inactive cliente's touch history on every tick just to
    catch this.

    Reads the row FRESH (not a snapshot a caller up the stack might be
    holding) so this cannot race a concurrent sweep tick into a stale
    write. Only reactivates a cliente the SWEEP put to sleep
    (`arquivado_em IS NULL`) — a MANUALLY archived cliente
    (`arquivado_em IS NOT NULL`) is a deliberate human decision this
    function must never override; see this module's / `clientes_
    inactivity_service.py`'s state table for the full
    ativo/inativo_em/arquivado_em matrix."""
    rows = (
        _t(client, "clientes")
        .select("ativo,arquivado_em")
        .eq("id", cliente_id)
        .eq("org_id", str(org_id))
        .execute()
    ).data or []
    if not rows:
        return
    current = rows[0]
    if current.get("ativo") or current.get("arquivado_em") is not None:
        return  # already active, or a manual archive — not this function's call
    _t(client, "clientes").update({
        "ativo": True,
        "inativo_em": None,
        "inativo_threshold_dias": None,
        "reativado_em": _now(),
        "updated_at": _now(),
    }).eq("id", cliente_id).eq("org_id", str(org_id)).execute()
    report.clientes_reactivated += 1


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


def _repoint_atendimentos(client: Any, org_id: UUID, report: BackfillReport) -> None:
    # 🔴 MUST paginate. An unpaginated PostgREST select silently caps at 1 000
    # rows and reports success — it did exactly that on the live 2026-08-13
    # backfill, repointing 1 000 of 1 365 negociações and returning
    # `atendimentos_orphaned: []`, i.e. "clean". The 365 left with a NULL
    # cliente_id were invisible in the report. Note `touches` two lines below
    # already used `_select_all`: the helper existed, in this same function,
    # and one of the two queries simply did not use it.
    rows = _select_all(
        client,
        "atendimentos",
        org_id,
        columns="id,lead_id,meta_ads_lead_id,cliente_id",
    )

    touches = _select_all(
        client, "cliente_touches", org_id, columns="origem_tabela,origem_id,cliente_id"
    )
    by_origem = {(t["origem_tabela"], t["origem_id"]): t["cliente_id"] for t in touches}

    for n in rows:
        if n.get("cliente_id"):
            report.atendimentos_already_pointed += 1
            continue

        origem: Optional[tuple[str, str]] = None
        if n.get("lead_id"):
            origem = ("leads", str(n["lead_id"]))
        elif n.get("meta_ads_lead_id"):
            origem = ("meta_ads_leads", str(n["meta_ads_lead_id"]))

        cliente_id = by_origem.get(origem) if origem else None
        if cliente_id is None:
            report.atendimentos_orphaned.append(n["id"])
            continue

        _t(client, "atendimentos").update({"cliente_id": cliente_id}).eq(
            "id", n["id"]
        ).execute()
        report.atendimentos_repointed += 1


def _collapse_atendimentos(client: Any, org_id: UUID, report: BackfillReport) -> None:
    """P1.4 completion — collapse `atendimentos` rows that share a
    `cliente_id` into one Funil board card (roadmap `project-history/
    roadmaps/lead-card-hub-2026-08.md` §1: `spawn_funil_card_on_lead` +
    `spawn_funil_card_on_meta_lead` fire for the SAME Meta-sourced human,
    so one person gets two cards — 125 pairs measured, 100% forward rate).

    Mirrors migration `054`'s SQL survivor rule EXACTLY (same three-way
    order, same interpretation call), so the one-shot migration and this
    steady-state pass never disagree about which row wins:

      1. `status == 'aberta'` (open) beats any closed status — an open
         deal is never hidden behind a closed one, so it can never
         silently vanish from `obter_funil` (which only shows `aberta`
         cards);
      2. among rows of the same openness, the FURTHEST-ADVANCED STAGE
         wins, resolved from THIS org's own `pipeline_stages.posicao`
         for the `funil` pipeline — never a hardcoded slug, since stages
         are user-editable rows;
      3. tie-break: the oldest `created_at`;
      4. final tie-break: the lower `id`, so an identical timestamp still
         resolves deterministically.

    Only rows with `cliente_id IS NOT NULL AND substituida_por IS NULL`
    are candidates. A row already collapsed by a prior run therefore
    drops out of the grouping on the very next call — that is what makes
    this idempotent across the 6-hourly sweep, exactly like every other
    step in this module (see the module docstring's IDEMPOTENCY section).
    Nothing is ever deleted: a loser is marked (`substituida_por`,
    `colapsada_em`), never removed, so it stays reversible by nulling
    those two columns alone (D3's undo bar, applied here without a
    separate `cliente_merges`-shaped table because there is nothing to
    reconstruct — the row itself never stopped existing).
    """
    rows = _select_all(
        client,
        "atendimentos",
        org_id,
        columns="id,cliente_id,etapa_id,status,created_at,substituida_por",
    )
    stage_rows = _select_all_where(
        client, "pipeline_stages", org_id, {"pipeline": "funil"},
        columns="id,posicao",
    )
    posicao_by_etapa = {s["id"]: s.get("posicao", -1) for s in stage_rows}

    groups: dict[str, list[dict]] = {}
    for n in rows:
        if not n.get("cliente_id") or n.get("substituida_por"):
            continue
        groups.setdefault(n["cliente_id"], []).append(n)

    def _sort_key(n: dict) -> tuple:
        aberta_first = 0 if n.get("status") == "aberta" else 1
        posicao_desc = -posicao_by_etapa.get(n.get("etapa_id"), -1)
        created = n.get("created_at") or ""
        return (aberta_first, posicao_desc, created, str(n["id"]))

    for cliente_id, group in groups.items():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=_sort_key)
        survivor = ordered[0]
        for loser in ordered[1:]:
            _t(client, "atendimentos").update({
                "substituida_por": survivor["id"],
                "colapsada_em": _now(),
            }).eq("id", loser["id"]).execute()
            report.atendimentos_collapsed += 1


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

#: `GET /api/clientes?q=` columns — nome, celular, email (leads-novo-lead
#: 2026-09-24). Used to be `nome` alone: the board search and the
#: Base-de-Leads "Novo lead" cliente picker both need to find "Fernando" by
#: typing his phone or his e-mail just as much as his name — a lead/atendimento
#: operator routinely has a phone number typed into WhatsApp and nothing else.
_CLIENTES_SEARCH_COLS = ("nome", "celular", "email")


def _ids_matching_termo(client: Any, org_id: UUID, termo: str) -> set[str]:
    """Every `clientes.id` whose `nome`, `celular` or `email` ILIKE-matches
    `termo` — one query per column, unioned in Python.

    🔴 NOT a single `.or_(...)` expression across the three columns.
    `imovel_hub.busca_service`'s module header documents why (same mock,
    same trap): `MockRequestBuilder.or_()` (`noctusai_lib/testing/mocks.py`)
    records a synthetic MATCH-ALL predicate rather than actually filtering,
    so an `.or_()`-based search would pass every test (it "finds" everything)
    and silently return the wrong, unfiltered set in production — the first
    honest signal would be an operator reporting the picker offers the whole
    client base. Per-column `ilike` evaluates identically in both worlds,
    exactly like `busca_service._ilike_rows`.

    NOC-REMEDIATE[clientes-busca-accent-fold]: case-insensitive (Postgres
    ILIKE) but not accent-insensitive — typing "fernicio" will not match a
    stored "Fernício". `imovel_hub.busca_service` carries the identical gap
    (`NOC-REMEDIATE[imovel-busca-accent-fold]`); this is N=2 for the same
    class (a DB-side `unaccent()`-derived generated column), triaged per the
    DRY N=2 rule rather than formalized here — batch both when a third
    surface needs it. — 2026-09-24
    """
    ids: set[str] = set()
    for coluna in _CLIENTES_SEARCH_COLS:
        rows = (
            _t(client, "clientes")
            .select("id")
            .eq("org_id", str(org_id))
            .ilike(coluna, f"%{termo}%")
            .limit(_PAGE)
            .execute()
        ).data or []
        ids.update(str(r["id"]) for r in rows if r.get("id"))
    return ids


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
    built here (see the Slice A delivery note).

    `q` matches `nome` OR `celular` OR `email` (`_ids_matching_termo`) — a
    live typeahead (the "Novo lead" cliente picker) is typed a phone number
    at least as often as a name."""
    query = _t(client, "clientes").select("*", count="exact").eq("org_id", str(org_id))
    if ativo is not None:
        query = query.eq("ativo", ativo)
    if q:
        termo = q.strip()
        matching_ids = _ids_matching_termo(client, org_id, termo) if termo else set()
        if not matching_ids:
            return {"items": [], "total": 0, "page": page, "pages": 1}
        query = query.in_("id", sorted(matching_ids))

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


# ─── A human edit of a DOCUMENT-sourced value (the reverse of migration 138) ─
#
# 138 built the admin-adjudication queue for the OTHER direction: an
# extraction disagreeing with a value already on `clientes`. The owner's
# provenance directive (2026-09-19), quoted verbatim in this dispatch's
# brief, closes the gap on THIS side too: "humans input data, extracted from
# official files are the truth. if a robot input a data, then a human edits
# an extracted-data, human overwrites with admin confirmation and logs for
# history and rollback."
#
# So: a human PATCH touching a field whose CURRENT value came from a
# document (`<campo>_origem` neither NULL nor `'manual'`) never silently
# overwrites it. An org admin/owner's edit applies immediately — they ARE
# the confirmation — but still gets logged to `cliente_campo_conflitos` with
# `status='aceito'`, pre-decided, so `valor_anterior` survives as the way
# back exactly like an accepted extraction conflict does. Anyone else's edit
# is held back (removed from the write payload — the document value keeps
# prevailing) and opens a `status='pendente'` row for an admin to decide via
# the EXISTING `PUT /conflitos/{id}/decidir` route
# (`identidade_extracao_service.resolver_conflito`, unchanged: it is already
# generic over which `campo` and which `origem_proposto` it is deciding).
#
# 🔴 Deliberately NOT importing `identidade_extracao_service` to reuse its
# `_registrar_conflito` — that module imports `app.modules.card_hub.services`,
# which imports THIS module (`clientes_service`), so the reverse import here
# would be circular. The insert shape below is intentionally the same few
# columns, kept in sync by hand (both write the same `cliente_campo_
# conflitos` table `resolver_conflito` reads generically).
CONFLITOS_TABLE = "cliente_campo_conflitos"

#: Every identity/qualificação field a document extractor can also write —
#: `identidade_extracao_service.CAMPOS`' item_keys, plus `nome_oficial`
#: (071, now also human-editable — see migration 148's note on why it was
#: "never written by hand" before this dispatch). Migration 153 added
#: `rg_orgao_expedidor` (its own provenance now, no longer riding with `rg`)
#: and `profissao` (whose quintet 137 already had but which was missing
#: here, so a hand edit never stamped `'manual'`).
_CAMPOS_COM_ORIGEM: tuple[str, ...] = (
    "nome_oficial", "cpf", "rg", "rg_orgao_expedidor", "data_nascimento", "genero",
    "estado_civil", "regime_bens", "data_casamento", "nacionalidade", "profissao",
)

#: Migration 153 — fields whose provenance quintet covers a GROUP of columns.
#: `campo` is the `cliente_campo_conflitos.campo` the group uses (the same
#: constants `identidade_extracao_service` writes); `prefixo` names the
#: `<prefixo>_origem/_documento_id/_em` columns; `colunas` are the members.
#: A human edit of any member is gated and stamped as the whole group.
_GRUPOS_COM_ORIGEM: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "endereco",
        "endereco",
        (
            "endereco_cep", "endereco_logradouro", "endereco_numero",
            "endereco_complemento", "endereco_bairro", "endereco_cidade",
            "endereco_uf",
        ),
    ),
    ("conjuge_cliente_id", "conjuge", ("conjuge_cliente_id",)),
)


def _valor_grupo(row: dict, colunas: tuple[str, ...]) -> Optional[str]:
    """A group's value as the TEXT a conflict row holds: the bare value for a
    one-column group, JSON of the parts otherwise (what
    `identidade_extracao_service.resolver_conflito` parses back). None when
    every member is empty."""
    if all(not row.get(c) for c in colunas):
        return None
    if len(colunas) == 1:
        return str(row.get(colunas[0]))
    return json.dumps(
        {c.removeprefix("endereco_"): row.get(c) for c in colunas}, ensure_ascii=False
    )


def _conflito_pendente_existente(
    client: Any, org_id: UUID, cliente_id: UUID, campo: str
) -> bool:
    rows = (
        _t(client, CONFLITOS_TABLE)
        .select("id")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .eq("campo", campo)
        .eq("status", "pendente")
        .limit(1)
        .execute()
    ).data or []
    return bool(rows)


def _abrir_conflito_edicao_manual(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    campo: str,
    *,
    valor_anterior: Any,
    origem_anterior: Optional[str],
    valor_proposto: Any,
) -> None:
    """A non-admin's edit of a document-sourced field — held back from
    `clientes`, opened as a `pendente` conflict instead. Mirrors
    `identidade_extracao_service._registrar_conflito`'s own dedupe: skip the
    insert (and the doomed second row the partial UNIQUE index would refuse
    anyway) when a pending conflict for this (cliente, campo) already
    exists — a second PATCH attempt while the first is still awaiting a
    decision is not a second conflict."""
    if _conflito_pendente_existente(client, org_id, cliente_id, campo):
        return
    _t(client, CONFLITOS_TABLE).insert(
        {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "cliente_id": str(cliente_id),
            "campo": campo,
            "valor_anterior": valor_anterior,
            "origem_anterior": origem_anterior,
            "valor_proposto": valor_proposto,
            "origem_proposto": "manual",
            "confianca_proposta": None,
            "fonte_tabela": None,
            "fonte_id": None,
            "status": "pendente",
            "notificado_em": None,
            "decidido_por": None,
            "decidido_em": None,
            "created_at": _now(),
        }
    ).execute()


def _superseder_conflitos_pendentes(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    campo: str,
    *,
    decidido_por: Optional[Any],
) -> None:
    """An admin's DIRECT edit of `campo` makes any pre-existing `pendente`
    conflict on that SAME (cliente, campo) stale — it proposed overwriting
    a document value that no longer exists (the admin just overwrote it a
    different way). Left alone, that row would keep sitting in the admin
    queue offering a decision about a value the record has already moved
    past. Closed as `rejeitado` (the admin's own edit is what happened
    instead, captured in its OWN fresh `aceito` row by the caller) rather
    than silently deleted — the record that a conflict was once open here
    stays auditable, same posture every other decided row gets."""
    now = _now()
    pendentes = (
        _t(client, CONFLITOS_TABLE)
        .select("id")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .eq("campo", campo)
        .eq("status", "pendente")
        .execute()
    ).data or []
    for row in pendentes:
        _t(client, CONFLITOS_TABLE).update(
            {
                "status": "rejeitado",
                "decidido_por": str(decidido_por) if decidido_por else None,
                "decidido_em": now,
            }
        ).eq("id", row["id"]).execute()


def _registrar_edicao_manual_confirmada(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    campo: str,
    *,
    valor_anterior: Any,
    origem_anterior: Optional[str],
    valor_proposto: Any,
    decidido_por: Optional[Any],
) -> None:
    """An admin/owner's edit of a document-sourced field — applied
    immediately (the caller has already written `valor_proposto` to
    `clientes` in the SAME PATCH), logged here PRE-DECIDED (`status=
    'aceito'`, `decidido_por` the admin themselves) so `valor_anterior`
    survives as the history/rollback record the owner's directive asks
    for. ALSO closes out (`_superseder_conflitos_pendentes`) any stale
    `pendente` row this same edit makes moot — see that function's
    docstring."""
    _superseder_conflitos_pendentes(
        client, org_id, cliente_id, campo, decidido_por=decidido_por
    )
    now = _now()
    _t(client, CONFLITOS_TABLE).insert(
        {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "cliente_id": str(cliente_id),
            "campo": campo,
            "valor_anterior": valor_anterior,
            "origem_anterior": origem_anterior,
            "valor_proposto": valor_proposto,
            "origem_proposto": "manual",
            "confianca_proposta": None,
            "fonte_tabela": None,
            "fonte_id": None,
            "status": "aceito",
            "notificado_em": None,
            "decidido_por": str(decidido_por) if decidido_por else None,
            "decidido_em": now,
            "created_at": now,
        }
    ).execute()


def update_cliente(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    acting_user_id: Optional[Any] = None,
    is_admin: bool = False,
    **updates: Any,
) -> dict:
    """PATCH (§5 `PATCH /api/clientes/{id}`) — nome, ativo/arquivado (D4).

    `reativado_em` / `inativo_threshold_dias` are server-derived-only (see
    `clientes_router.py::update_cliente_route`, which is the only caller
    that ever passes them) — never accepted from the request body itself;
    `ClientePatchBody` doesn't even declare them as fields.

    The identity fields (migrations 068 + 073) are editable here because
    editing them is how most of the document-checklist items get satisfied — the
    checklist derives from these columns, so a PATCH that fills one ticks it on
    the next read with nothing to notify.

    `data_nascimento_origem` is stamped `'manual'` alongside any hand-edited
    birthdate rather than being accepted from the body: origin describes HOW a
    value arrived, so letting a caller assert it would let a client claim a
    machine read was typed by a person, or the reverse. A manual value also
    outranks every later automatic extraction, which is only safe if the
    server is the one that decided it was manual.

    🔴 `acting_user_id` / `is_admin` (owner directive, 2026-09-19) — see the
    module comment above `_abrir_conflito_edicao_manual`. Every field in
    `_CAMPOS_COM_ORIGEM` whose CURRENT value came from a document is gated:
    an admin's edit applies immediately (still logged for history/rollback);
    anyone else's is held back and queued for admin adjudication through the
    existing `cliente_campo_conflitos` machinery. The RETURN dict always
    carries `pendente_confirmacao` — the list of item_keys THIS call deferred
    (empty when nothing was) — so a caller (the PATCH route, the frontend
    form) never has to guess whether a field it just sent actually landed.
    """
    allowed = {
        "nome", "ativo", "arquivado_em", "inativo_em",
        "reativado_em", "inativo_threshold_dias",
        # Identity substrate (068) — what the document checklist derives from.
        "nome_completo", "email", "data_nascimento", "genero",
        # 073 — the two the checklist grew, same rule.
        "celular", "profissao",
        # 097 — qualificação civil. `cpf`/`rg` are checklist items like the
        # above; the rest are not, and are editable for a different reason:
        # a contract cannot qualify a party without them, and nothing else
        # in this product collects them.
        "cpf", "rg", "rg_orgao_expedidor",
        "estado_civil", "regime_bens", "conjuge_cliente_id", "nacionalidade",
        "endereco_cep", "endereco_logradouro", "endereco_numero",
        "endereco_complemento", "endereco_bairro", "endereco_cidade",
        "endereco_uf",
        # 117 (contract F6) — the marriage celebration date. A checklist item
        # like data_nascimento/genero/cpf/rg above, on the same terms.
        "data_casamento",
        # 071, now human-editable (owner directive, 2026-09-19 — see
        # `_CAMPOS_COM_ORIGEM`'s comment). Gated exactly like every field
        # above: a document-sourced `nome_oficial` needs admin confirmation
        # to be hand-corrected.
        "nome_oficial",
        # 148 — the manual half of contract F6's [Q11] freshness check.
        # Never gated (see that migration's header): no extractor ever
        # writes this column, so there is no document value to protect.
        "certidao_estado_civil_emitida_em",
    }
    payload = {k: v for k, v in updates.items() if k in allowed}
    if not payload:
        return {**_require_cliente(client, org_id, cliente_id), "pendente_confirmacao": []}

    # Fetched once, up front, whenever the PATCH touches ANY field this
    # function must compare against its EXISTING value — the gate below, and
    # (since `rg`/`cpf` are both in `_CAMPOS_COM_ORIGEM`) the rg==cpf
    # collision guard that used to fetch this separately.
    atual: Optional[dict] = None
    colunas_de_grupo = {c for _campo, _pref, cols in _GRUPOS_COM_ORIGEM for c in cols}
    if payload.keys() & (set(_CAMPOS_COM_ORIGEM) | colunas_de_grupo):
        atual = _require_cliente(client, org_id, cliente_id)

    pendentes: list[str] = []
    aprovados_admin: list[tuple[str, Any, Optional[str]]] = []
    #: The proposed value of a deferred GROUP, as conflict TEXT.
    valores_grupo_propostos: dict[str, Optional[str]] = {}
    grupos = {campo: (prefixo, colunas) for campo, prefixo, colunas in _GRUPOS_COM_ORIGEM}

    def _anterior(campo: str) -> Any:
        assert atual is not None
        if campo in grupos:
            return _valor_grupo(atual, grupos[campo][1])
        return atual.get(campo)

    def _origem_anterior(campo: str) -> Optional[str]:
        assert atual is not None
        prefixo = grupos[campo][0] if campo in grupos else campo
        return atual.get(f"{prefixo}_origem")

    def _proposto(campo: str) -> Any:
        if campo in grupos:
            return valores_grupo_propostos.get(campo)
        return updates.get(campo)

    if atual is not None:
        for campo in _CAMPOS_COM_ORIGEM:
            if campo not in payload:
                continue
            valor_atual = atual.get(campo)
            origem_atual = atual.get(f"{campo}_origem")
            eh_documento = bool(valor_atual) and origem_atual not in (None, "manual")
            if not eh_documento:
                continue
            if is_admin:
                aprovados_admin.append((campo, valor_atual, origem_atual))
                continue
            # Não-admin: NUNCA sobrescreve silenciosamente — vira pendência,
            # e o valor do documento continua prevalecendo até uma decisão.
            pendentes.append(campo)
            del payload[campo]
            if campo == "rg" and "rg_orgao_expedidor" in payload:
                # The issuer belongs to the NUMBER: an issuer edit cannot land
                # while the RG it qualifies is held back (true whether or not
                # the issuer's own provenance — 153 — says it came from a
                # document).
                del payload["rg_orgao_expedidor"]

        # Groups (153): the same gate, over the group as a unit.
        for campo, prefixo, colunas in _GRUPOS_COM_ORIGEM:
            tocadas = [c for c in colunas if c in payload]
            if not tocadas:
                continue
            valor_atual = _valor_grupo(atual, colunas)
            origem_atual = atual.get(f"{prefixo}_origem")
            if valor_atual is None or origem_atual in (None, "manual"):
                continue
            if is_admin:
                aprovados_admin.append((campo, valor_atual, origem_atual))
                continue
            pendentes.append(campo)
            proposto = {**atual, **{c: payload[c] for c in tocadas}}
            valores_grupo_propostos[campo] = _valor_grupo(proposto, colunas)
            for c in tocadas:
                del payload[c]

    if not payload:
        # Every touched field was deferred to admin confirmation — nothing
        # left to write. `atual` is guaranteed non-None here (the loop above
        # only runs, and only defers, when it is).
        assert atual is not None
        for campo in pendentes:
            _abrir_conflito_edicao_manual(
                client, org_id, cliente_id, campo,
                valor_anterior=_anterior(campo),
                origem_anterior=_origem_anterior(campo),
                valor_proposto=_proposto(campo),
            )
        return {**atual, "pendente_confirmacao": pendentes}

    # 🔴 RG == CPF is NOT refused here (nor anywhere else in this codebase,
    # 2026-09-22). It used to be — a hard `ValidationError_` on a PATCH
    # leaving the pair holding the same eleven digits, the copy-paste bug
    # `rg.is_same_as_cpf` exists to catch. But the new Carteira de
    # Identidade Nacional (CIN) uses the CPF number AS the identity number
    # by design: contract 08 (a human-typed reference) qualifies "TAUANE
    # GONÇALVES DIAS ... RG 448.864.938-66-IIGDR-SP e inscrita no CPF/MF
    # 448.864.938-66" — the same eleven digits in both boxes, correctly. A
    # refusal here would make this product unable to save a real CIN
    # holder's identity. The contract-generation gate still surfaces the
    # collision — as an `av.avisa("RG_IGUAL_CPF", ...)` warning for the
    # operator to confirm against the document, never a `bloqueia` — see
    # `contrato_gerador.derivacao._partes`.
    #
    # Every field in `_CAMPOS_COM_ORIGEM` still present in `payload` (i.e.
    # NOT deferred above) is a value the server is about to write — stamp its
    # provenance quintet the SAME way for all nine: `_origem='manual'`
    # (or `None` when the caller is clearing the field back to empty —
    # clearing must clear the origin too, an origin pointing at a value that
    # no longer exists is a lie the extractor would then honour),
    # `_documento_id=None` (a human always types, never points at a
    # document) and `_em` the moment of the write. `confirmado_por`/
    # `confirmado_em` are untouched — those belong to `confirmar_sugestao`'s
    # "a human vouched for a machine read" flow, a different action from
    # "a human typed a value".
    for campo in _CAMPOS_COM_ORIGEM:
        if campo not in payload:
            continue
        valor = payload[campo]
        payload[f"{campo}_origem"] = "manual" if valor else None
        payload[f"{campo}_documento_id"] = None
        payload[f"{campo}_em"] = _now() if valor else None

    # Groups (153): stamped as a unit — `'manual'` when the group ends up
    # holding anything, NULL provenance when the edit cleared it entirely.
    for _campo, prefixo, colunas in _GRUPOS_COM_ORIGEM:
        if not any(c in payload for c in colunas):
            continue
        base = atual if atual is not None else {}
        final = {**base, **{c: payload[c] for c in colunas if c in payload}}
        preenchido = _valor_grupo(final, colunas) is not None
        payload[f"{prefixo}_origem"] = "manual" if preenchido else None
        payload[f"{prefixo}_documento_id"] = None
        payload[f"{prefixo}_em"] = _now() if preenchido else None

    # 148 — the manual certidão-emission date. Same stamping shape as above,
    # minus `_documento_id`/`_confirmado_*`: that migration's column pair
    # has no such columns (no extractor ever writes it — see its header).
    if "certidao_estado_civil_emitida_em" in payload:
        valor = payload["certidao_estado_civil_emitida_em"]
        payload["certidao_estado_civil_emitida_em_origem"] = "manual" if valor else None
        payload["certidao_estado_civil_emitida_em_em"] = _now() if valor else None

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
    resultado = rows[0]

    for campo in pendentes:
        assert atual is not None
        _abrir_conflito_edicao_manual(
            client, org_id, cliente_id, campo,
            valor_anterior=_anterior(campo),
            origem_anterior=_origem_anterior(campo),
            valor_proposto=_proposto(campo),
        )
    for campo, valor_anterior, origem_anterior in aprovados_admin:
        _registrar_edicao_manual_confirmada(
            client, org_id, cliente_id, campo,
            valor_anterior=valor_anterior,
            origem_anterior=origem_anterior,
            valor_proposto=(
                _valor_grupo(resultado, grupos[campo][1])
                if campo in grupos
                else resultado.get(campo)
            ),
            decidido_por=acting_user_id,
        )

    return {**resultado, "pendente_confirmacao": pendentes}


def excluir_cliente(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    """Hard delete (`DELETE /api/clientes/{id}`, owner directive
    2026-09-24) — admin/owner-only, enforced by the ROUTE (this function
    trusts its caller and does not re-check the role).

    Storage is deliberately NOT touched here: this module is the DB I/O
    layer only (see the module docstring), and a storage delete that ran
    before the DB delete could leave a file gone but its row still
    pointing at it if the DB call then failed. The caller (the route,
    which already holds `Depends(get_storage_backend)`) deletes each
    `cliente_documentos` row's `storage_path` from the bucket AFTER this
    call returns, using the `documentos` list below — collected BEFORE the
    cliente row is deleted, because `cliente_documentos` CASCADEs
    (migration 057) and its rows would otherwise be gone by the time the
    caller tried to read their paths.

    Ordering, and why:
      1. `cliente_merges.cliente_id_sobrevivente` has NO `ON DELETE`
         (migration 048) — checked FIRST, as a plain read, before any
         mutation runs. Raises `ClienteEhSobreviventeDeMerge` rather than
         letting a real delete attempt hit Postgres' bare FK-violation.
      2. `atendimentos.cliente_id` is `ON DELETE SET NULL` (048) — SET
         NULL alone would leave a person-less ghost card sitting on the
         funil board, so this deletes the cliente's atendimentos
         explicitly, BEFORE the cliente row (never after: after the
         cliente row is gone there is no `cliente_id` left to filter by).
      3. The `clientes` row itself. Every other child either CASCADEs
         (`cliente_documentos` 057, `cliente_notas`/`cliente_tag_links`/
         `cliente_membros`/`cliente_lembretes`/`cliente_checklists` 056,
         `documento_checklist_itens` 067, `atendimento_partes` 073,
         `cliente_checklist_extras` 083, `cliente_campo_conflitos` 138) or
         SETs NULL on its own (`negociacoes_venda` 048,
         `cliente_vinculo` 074, the qualificação-civil FKs 097, the
         certidões FKs 107, the matrícula-qualificações FKs 137) — no
         further app-level cleanup needed for any of those.
    """
    _require_cliente(client, org_id, cliente_id)

    sobrevivente = (
        _t(client, "cliente_merges")
        .select("id")
        .eq("org_id", str(org_id))
        .eq("cliente_id_sobrevivente", str(cliente_id))
        .limit(1)
        .execute()
    ).data or []
    if sobrevivente:
        raise ClienteEhSobreviventeDeMerge(
            f"cliente {cliente_id} is the surviving side of a merge and cannot be deleted"
        )

    documentos = _select_all_where(
        client, "cliente_documentos", org_id, {"cliente_id": str(cliente_id)},
        columns="id,storage_path",
    )

    atendimentos_removidos = (
        _t(client, "atendimentos")
        .delete()
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .execute()
    ).data or []

    (
        _t(client, "clientes")
        .delete()
        .eq("id", str(cliente_id))
        .eq("org_id", str(org_id))
        .execute()
    )

    return {
        "atendimentos_removidos": len(atendimentos_removidos),
        "documentos": documentos,
    }


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
    # 🔴 Paginated: an unpaginated select caps at 1 000 rows and reports
    # success. There are 1 177 identidade_incerta clientes live, so a bare
    # read silently dropped 177 of them from the queue.
    incerta_rows = _select_all_where(
        client, "clientes", org_id, {"identidade_incerta": True}
    )
    if not incerta_rows:
        return []

    # 🔴 Batched: PostgREST puts `in_` values in the URL QUERY STRING. ~1 000
    # UUIDs is a ~40 KB request line, which the server rejects with a bare
    # 400 ("JSON could not be generated") — that is what took /clientes/revisao
    # down in production on 2026-08-14. The batch size keeps the longest
    # request line comfortably under the usual 8 KB limit
    # (200 x 38 chars ~= 7.6 KB, and each batch is still paginated).
    ids = [r["id"] for r in incerta_rows]
    touch_rows: list[dict] = []
    for batch in _batched(ids, _IN_FILTER_BATCH):
        touch_rows.extend(
            _paginate_query(
                lambda start, end, b=batch: _t(client, "cliente_touches")
                .select("cliente_id,chave_canonica")
                .eq("org_id", str(org_id))
                .in_("cliente_id", b)
                .range(start, end)
                .execute()
            )
        )
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
