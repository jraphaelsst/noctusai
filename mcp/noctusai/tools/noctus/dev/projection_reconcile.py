"""noctus.dev.projection_reconcile — does a stored state row agree with the
fold of the append-only log that is supposed to have produced it?

THE CONCEPT. A *projection* is a row whose value is derivable from a log:
``fin_entries.settled_cents`` is the signed sum of the entry's unreversed
``fin_settlements``; a pipeline card's ``etapa_id`` is the ``para_etapa_id``
of its latest ``pipeline_movimentos`` row; an agent's
``thread_participantes.estado`` is the ``para`` of its latest
``thread_participante_eventos`` row. The writer keeps both in step today by
convention (one function writes both). Nothing CHECKED that they agree —
this tool is that check, and later the gate for the event-store cutover
(event-sourcing-program P0). KB § PATTERNS/backend/projection-reconcile.md.

DESIGN.

* **Pairs are data.** ``DEFAULT_REGISTRY`` is a tuple of :class:`PairSpec`
  (product, schema, state table/key/value, log table/key/fold, behaviour
  when a key has no log). Adding a pair is one more entry; there is no
  per-pair code path. Two folds cover every pair so far: ``sum`` (signed,
  reversal-aware) and ``latest`` (last value by an order column).
* **Read-only by construction.** The only SQL this module emits is built by
  :func:`build_state_sql` / :func:`build_log_sql` from registry identifiers
  that must match ``^[a-z_][a-z0-9_]*$`` and literals that must match
  ``^[A-Za-z0-9_]+$`` — a single ``SELECT`` with no ``;`` (asserted). No
  caller-supplied text ever reaches SQL: callers only pick pair ids from the
  allowlist. Transport is ``migrate_product.make_sql_executor`` (the
  Supabase Management API, PAT resolved DB-first), the same path
  ``check_storage_no_public_buckets`` / ``schema_drift`` use.
* **The fold runs in Python** (:func:`fold_log` / :func:`diff_projection`),
  so the semantics — reversals, out-of-order rows, ties — are unit-tested on
  fixtures with no DB. Each side is fetched with ``LIMIT max_rows + 1``; a
  side that exceeds ``max_rows`` is ``inconclusive`` (a truncated fold would
  produce false drift), never folded partially.
* **Enumerated verdicts.** Per pair: ``consistent`` | ``drift`` |
  ``inconclusive`` (no credentials, query failed, table/column missing,
  too many rows, or keys whose latest log row is ambiguous) | ``skipped``
  (product asleep in ``deploy/fleet/active-scope.txt``). Overall:
  ``drift`` > ``inconclusive`` > ``consistent``; ``ok``/``exit_code 0``
  ONLY for ``consistent``. Unmeasurable is never green and never red.
* **Bounded output.** Counts per pair plus the first ``sample`` mismatches
  (default 5, max 50). Keys and projected values only (ids, cents, stage
  ids, state names) — no free text, no personal data.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import migrate_product as _mp

DEFAULT_PROJECT_REF = "nyplttplcoyiiqjrvtiw"
DEFAULT_SAMPLE = 5
MAX_SAMPLE = 50
DEFAULT_MAX_ROWS = 200_000

REPO_ROOT = Path(__file__).resolve().parents[5]
ACTIVE_SCOPE_REL = "deploy/fleet/active-scope.txt"

_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_LITERAL_RE = re.compile(r"^[A-Za-z0-9_]+$")

FOLD_SUM = "sum"
FOLD_LATEST = "latest"
#: a state key with NO log rows folds to the identity (0 for ``sum``) and is compared.
MISSING_LOG_IDENTITY = "identity"
#: a state key with NO log rows is counted as ``unlogged`` and not compared
#: (its initial value was never logged — e.g. a card created straight into a stage).
MISSING_LOG_UNLOGGED = "unlogged"


# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StateSpec:
    table: str
    key: tuple[str, ...]
    value: str


@dataclass(frozen=True)
class LogSpec:
    table: str
    #: log columns, positionally matching ``StateSpec.key``.
    key: tuple[str, ...]
    fold: str
    value: str
    #: ``latest``: timestamp column(s) ordering the log (normalised to fixed-width UTC text).
    order: tuple[str, ...] = ()
    #: equality filters on the log (column, literal), e.g. ``(("pipeline", "funil"),)``.
    where: tuple[tuple[str, str], ...] = ()
    #: ``sum``: a row whose ``sign_column`` value is in ``negative_values`` subtracts.
    sign_column: str | None = None
    negative_values: tuple[str, ...] = ()
    #: ``sum``: a row whose ``skip_when_set`` column is non-NULL (a reversal) is ignored.
    skip_when_set: str | None = None


@dataclass(frozen=True)
class PairSpec:
    id: str
    product: str
    schema: str
    description: str
    state: StateSpec
    log: LogSpec
    missing_log: str = MISSING_LOG_IDENTITY
    source: str = ""


def _finance_pair(product: str, schema: str, migration: str) -> PairSpec:
    return PairSpec(
        id=f"finance.settled_cents@{product}",
        product=product,
        schema=schema,
        description=(
            "fin_entries.settled_cents = SUM(payment) - SUM(refund) over the entry's "
            "fin_settlements WHERE reversed_at IS NULL (seed finance organ)."
        ),
        state=StateSpec(table="fin_entries", key=("id",), value="settled_cents"),
        log=LogSpec(
            table="fin_settlements",
            key=("entry_id",),
            fold=FOLD_SUM,
            value="amount_cents",
            sign_column="kind",
            negative_values=("refund",),
            skip_when_set="reversed_at",
        ),
        missing_log=MISSING_LOG_IDENTITY,
        source=f"seed/lib/backend/noctusai_lib/domain/finance/sql.py · {migration}",
    )


def _sw_pipeline_pair(pipeline: str, card_table: str, migration: str) -> PairSpec:
    return PairSpec(
        id=f"sw.pipeline.{pipeline}",
        product="social-wiring",
        schema="social_wiring",
        description=(
            f"{card_table}.etapa_id = para_etapa_id of the latest pipeline_movimentos row "
            f"(pipeline='{pipeline}', by created_at) for the card. Cards with no movement "
            "(created straight into a stage) are 'unlogged', not compared."
        ),
        state=StateSpec(table=card_table, key=("id",), value="etapa_id"),
        log=LogSpec(
            table="pipeline_movimentos",
            key=("entidade_id",),
            fold=FOLD_LATEST,
            value="para_etapa_id",
            order=("created_at",),
            where=(("pipeline", pipeline),),
        ),
        missing_log=MISSING_LOG_UNLOGGED,
        source=(
            "seed/lib/backend/noctusai_lib/domain/pipeline/moves.py · "
            f"products/social-wiring/backend/migrations/034_pipeline_funil_processos.sql · {migration}"
        ),
    )


#: The registered pairs — ACTIVE products only (asleep ones are skipped at
#: runtime anyway). Columns verified against origin/dev migrations 2026-11-07.
DEFAULT_REGISTRY: tuple[PairSpec, ...] = (
    _finance_pair("social-wiring", "social_wiring", "products/social-wiring/backend/migrations/260_finance.sql"),
    _finance_pair("nosnolimiar", "nosnolimiar", "products/nosnolimiar/backend/migrations/012_finance.sql"),
    _finance_pair("agents", "agents", "products/agents/backend/migrations/027_finance.sql"),
    _finance_pair("core", "public", "products/core/backend/migrations/085_finance.sql"),
    _sw_pipeline_pair("funil", "atendimentos", "products/social-wiring/backend/migrations/060_negociacoes_venda_to_atendimentos.sql"),
    _sw_pipeline_pair("processos_venda", "processos_venda", "products/social-wiring/backend/migrations/034_pipeline_funil_processos.sql"),
    _sw_pipeline_pair("esteira", "cs_posts", "products/social-wiring/backend/migrations/241_cs_esteira.sql"),
    PairSpec(
        id="agents.thread_participante.estado",
        product="agents",
        schema="agents",
        description=(
            "thread_participantes.estado = para of the latest thread_participante_eventos row "
            "(by created_at) for (thread_id, agent_id). add_participante logs de=NULL -> 'ativo', "
            "so a participant with no event is 'unlogged' (a writer that bypassed the store)."
        ),
        state=StateSpec(table="thread_participantes", key=("thread_id", "agent_id"), value="estado"),
        log=LogSpec(
            table="thread_participante_eventos",
            key=("thread_id", "agent_id"),
            fold=FOLD_LATEST,
            value="para",
            order=("created_at",),
        ),
        missing_log=MISSING_LOG_UNLOGGED,
        source=(
            "products/agents/backend/migrations/033_julia_v2_threads.sql · "
            "products/agents/backend/app/stores/threads.py"
        ),
    ),
)


# ---------------------------------------------------------------------------
# Validation + SQL construction (the ONLY SQL emitters in this module)
# ---------------------------------------------------------------------------


def _ident(name: str) -> str:
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ValueError(f"projection_reconcile: invalid SQL identifier {name!r}")
    return name


def _literal(value: str) -> str:
    if not isinstance(value, str) or not _LITERAL_RE.match(value):
        raise ValueError(f"projection_reconcile: invalid SQL literal {value!r}")
    return f"'{value}'"


def validate_pair(pair: PairSpec) -> None:
    """Raise ``ValueError`` on a malformed registry entry (checked before any SQL)."""
    _ident(pair.schema)
    _ident(pair.state.table)
    _ident(pair.state.value)
    _ident(pair.log.table)
    _ident(pair.log.value)
    for col in (*pair.state.key, *pair.log.key, *pair.log.order):
        _ident(col)
    if not pair.state.key or len(pair.state.key) != len(pair.log.key):
        raise ValueError(f"{pair.id}: state.key and log.key must be non-empty and the same length")
    for col, lit in pair.log.where:
        _ident(col)
        _literal(lit)
    if pair.log.fold == FOLD_SUM:
        if pair.log.sign_column:
            _ident(pair.log.sign_column)
        for lit in pair.log.negative_values:
            _literal(lit)
        if pair.log.skip_when_set:
            _ident(pair.log.skip_when_set)
    elif pair.log.fold == FOLD_LATEST:
        if not pair.log.order:
            raise ValueError(f"{pair.id}: a 'latest' fold needs at least one order column")
    else:
        raise ValueError(f"{pair.id}: unknown fold {pair.log.fold!r}")
    if pair.missing_log not in (MISSING_LOG_IDENTITY, MISSING_LOG_UNLOGGED):
        raise ValueError(f"{pair.id}: unknown missing_log {pair.missing_log!r}")
    if pair.log.fold == FOLD_LATEST and pair.missing_log == MISSING_LOG_IDENTITY:
        raise ValueError(f"{pair.id}: a 'latest' fold has no identity; use missing_log='unlogged'")


def _assert_single_select(sql: str) -> str:
    if not sql.startswith("SELECT ") or ";" in sql:
        raise ValueError("projection_reconcile: refusing to emit anything but one SELECT")
    return sql


def build_state_sql(pair: PairSpec, *, max_rows: int) -> str:
    s = pair.state
    cols = ", ".join([*(_ident(k) for k in s.key), _ident(s.value)])
    return _assert_single_select(
        f"SELECT {cols} FROM {_ident(pair.schema)}.{_ident(s.table)} LIMIT {int(max_rows) + 1}"
    )


def _order_alias(i: int) -> str:
    return f"_ord{i}"


def build_log_sql(pair: PairSpec, *, max_rows: int) -> str:
    lg = pair.log
    cols = [*(_ident(k) for k in lg.key), _ident(lg.value)]
    if lg.fold == FOLD_SUM:
        if lg.sign_column:
            cols.append(_ident(lg.sign_column))
        if lg.skip_when_set:
            cols.append(f"({_ident(lg.skip_when_set)} IS NOT NULL) AS _skip")
    else:
        # Fixed-width UTC text so a Python string compare IS a time compare
        # (Postgres trims trailing fractional zeros in its default output).
        for i, col in enumerate(lg.order):
            cols.append(
                f"to_char({_ident(col)} AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US') AS {_order_alias(i)}"
            )
    where = ""
    if lg.where:
        where = " WHERE " + " AND ".join(f"{_ident(c)} = {_literal(v)}" for c, v in lg.where)
    return _assert_single_select(
        f"SELECT {', '.join(cols)} FROM {_ident(pair.schema)}.{_ident(lg.table)}{where} LIMIT {int(max_rows) + 1}"
    )


# ---------------------------------------------------------------------------
# Fold + diff — pure, fixture-tested
# ---------------------------------------------------------------------------


def _key(row: dict[str, Any], cols: Iterable[str]) -> tuple[str, ...]:
    return tuple("" if row.get(c) is None else str(row.get(c)) for c in cols)


def _norm(fold: str, value: Any) -> Any:
    if value is None:
        return None
    if fold == FOLD_SUM:
        return int(value)
    return str(value)


@dataclass
class FoldResult:
    values: dict[tuple[str, ...], Any] = field(default_factory=dict)
    #: keys whose latest log rows tie on the order columns with DIFFERENT values.
    ambiguous: set[tuple[str, ...]] = field(default_factory=set)


def fold_log(pair: PairSpec, rows: Iterable[dict[str, Any]]) -> FoldResult:
    """Fold log rows into one value per key. Row order in ``rows`` is
    irrelevant: ``latest`` orders by the normalised order columns itself
    (out-of-order inserts/reads fold the same), and ``sum`` is commutative.
    A reversal (``skip_when_set`` non-NULL) contributes nothing."""
    lg = pair.log
    out = FoldResult()
    if lg.fold == FOLD_SUM:
        negative = set(lg.negative_values)
        for row in rows:
            if lg.skip_when_set and row.get("_skip"):
                continue
            k = _key(row, lg.key)
            amount = int(row.get(lg.value) or 0)
            if lg.sign_column and str(row.get(lg.sign_column)) in negative:
                amount = -amount
            out.values[k] = out.values.get(k, 0) + amount
        return out

    best: dict[tuple[str, ...], tuple[tuple[str, ...], Any]] = {}
    for row in rows:
        k = _key(row, lg.key)
        order = tuple(str(row.get(_order_alias(i)) or "") for i in range(len(lg.order)))
        value = _norm(FOLD_LATEST, row.get(lg.value))
        cur = best.get(k)
        if cur is None or order > cur[0]:
            best[k] = (order, value)
            out.ambiguous.discard(k)
        elif order == cur[0] and value != cur[1]:
            out.ambiguous.add(k)
    out.values = {k: v for k, (_, v) in best.items()}
    return out


def diff_projection(
    pair: PairSpec,
    state_rows: Iterable[dict[str, Any]],
    folded: FoldResult,
    *,
    sample: int = DEFAULT_SAMPLE,
) -> dict[str, Any]:
    """Compare stored state against the fold. Returns counts + bounded samples
    and the pair verdict (``consistent`` | ``drift`` | ``inconclusive``)."""
    fold = pair.log.fold
    key_cols = pair.state.key
    state_keys: set[tuple[str, ...]] = set()
    mismatches: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    n_mismatch = n_ambiguous = n_unlogged = n_compared = 0
    for row in state_rows:
        k = _key(row, key_cols)
        state_keys.add(k)
        stored = _norm(fold, row.get(pair.state.value))
        if k in folded.ambiguous:
            n_ambiguous += 1
            if len(ambiguous) < sample:
                ambiguous.append({"key": dict(zip(key_cols, k)), "state": stored})
            continue
        if k in folded.values:
            expected = folded.values[k]
        elif pair.missing_log == MISSING_LOG_IDENTITY:
            expected = 0
        else:
            n_unlogged += 1
            continue
        n_compared += 1
        if stored != expected:
            n_mismatch += 1
            if len(mismatches) < sample:
                mismatches.append({"key": dict(zip(key_cols, k)), "state": stored, "folded": expected})
    orphan_keys = [k for k in folded.values if k not in state_keys]
    if n_mismatch:
        verdict = "drift"
    elif n_ambiguous:
        verdict = "inconclusive"
    else:
        verdict = "consistent"
    return {
        "status": verdict,
        "state_rows": len(state_keys),
        "compared": n_compared,
        # consistent over ZERO compared keys proves nothing yet — said, not hidden.
        "vacuous": n_compared == 0,
        "mismatches": n_mismatch,
        "unlogged": n_unlogged,
        "ambiguous": n_ambiguous,
        "orphan_log_keys": len(orphan_keys),
        "mismatch_sample": mismatches,
        "ambiguous_sample": ambiguous,
        "orphan_log_sample": [dict(zip(key_cols, k)) for k in orphan_keys[:sample]],
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def read_active_scope(root: Path) -> set[str] | None:
    """Active product slugs from ``deploy/fleet/active-scope.txt``; ``None``
    when unreadable (then nothing is skipped and a warning is returned)."""
    path = root / ACTIVE_SCOPE_REL
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return {ln.strip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")}


def _inconclusive(pair: PairSpec, reason: str) -> dict[str, Any]:
    return {"id": pair.id, "product": pair.product, "schema": pair.schema, "status": "inconclusive", "reason": reason}


def reconcile_pair(
    pair: PairSpec,
    executor: _mp.SqlExecutor,
    *,
    sample: int = DEFAULT_SAMPLE,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> dict[str, Any]:
    validate_pair(pair)
    sides: dict[str, list[dict[str, Any]]] = {}
    for side, sql in (("state", build_state_sql(pair, max_rows=max_rows)), ("log", build_log_sql(pair, max_rows=max_rows))):
        res = executor.execute(sql)
        if not res.get("ok"):
            reason = f"{side} query failed: {(res.get('error') or 'unknown error')[:300]}"
            if res.get("transient"):
                reason += " (transient — retry)"
            return _inconclusive(pair, reason)
        rows = [r for r in (res.get("rows") or []) if isinstance(r, dict)]
        if len(rows) > max_rows:
            return _inconclusive(pair, f"{side} side exceeds max_rows={max_rows}; a truncated fold would report false drift")
        sides[side] = rows
    folded = fold_log(pair, sides["log"])
    out = {"id": pair.id, "product": pair.product, "schema": pair.schema}
    out.update(diff_projection(pair, sides["state"], folded, sample=sample))
    return out


def select_pairs(
    registry: tuple[PairSpec, ...],
    *,
    pairs: list[str] | None,
    product: str | None,
) -> tuple[list[PairSpec], list[str]]:
    known = {p.id: p for p in registry}
    unknown = [p for p in (pairs or []) if p not in known]
    chosen = [known[p] for p in pairs if p in known] if pairs else list(registry)
    if product:
        chosen = [p for p in chosen if p.product == product]
    return chosen, unknown


def projection_reconcile(
    *,
    pairs: list[str] | None = None,
    product: str | None = None,
    sample: int = DEFAULT_SAMPLE,
    max_rows: int = DEFAULT_MAX_ROWS,
    project_ref: str = DEFAULT_PROJECT_REF,
    worktree_path: str | None = None,
    executor: _mp.SqlExecutor | None = None,
    registry: tuple[PairSpec, ...] = DEFAULT_REGISTRY,
    active_scope: set[str] | None = None,
) -> dict[str, Any]:
    """Reconcile every selected pair; see the module docstring for verdicts."""
    sample = max(0, min(int(sample), MAX_SAMPLE))
    max_rows = max(1, int(max_rows))
    chosen, unknown = select_pairs(registry, pairs=pairs, product=product)
    registered = [p.id for p in registry]
    if unknown:
        return {"ok": False, "status": "error", "exit_code": 2,
                "error": f"unknown pair id(s) {unknown}; registered: {registered}", "pairs": []}
    if not chosen:
        return {"ok": False, "status": "error", "exit_code": 2,
                "error": f"no pair matches product={product!r}; registered: {registered}", "pairs": []}

    warnings: list[str] = []
    if active_scope is None:
        root = Path(worktree_path) if worktree_path else REPO_ROOT
        active_scope = read_active_scope(root)
        if active_scope is None:
            warnings.append(f"{ACTIVE_SCOPE_REL} unreadable under {root}; no pair skipped as asleep")

    if executor is None:
        executor = _mp.make_sql_executor(project_ref=project_ref)

    results: list[dict[str, Any]] = []
    for pair in chosen:
        if active_scope is not None and pair.product not in active_scope:
            results.append({"id": pair.id, "product": pair.product, "schema": pair.schema, "status": "skipped",
                            "reason": f"product asleep (not in {ACTIVE_SCOPE_REL})"})
            continue
        if executor is None:
            results.append(_inconclusive(
                pair,
                "NOC-REMEDIATE[credentials]: no supabase_access_token resolved (platform_settings "
                "'supabase_access_token' or env SUPABASE_ACCESS_TOKEN)",
            ))
            continue
        results.append(reconcile_pair(pair, executor, sample=sample, max_rows=max_rows))

    statuses = {r["status"] for r in results}
    if "drift" in statuses:
        status = "drift"
    elif "inconclusive" in statuses or statuses <= {"skipped"}:
        status = "inconclusive"
    else:
        status = "consistent"
    summary = {s: sum(1 for r in results if r["status"] == s) for s in ("consistent", "drift", "inconclusive", "skipped")}
    return {
        "ok": status == "consistent",
        "status": status,
        "exit_code": 0 if status == "consistent" else 1,
        "summary": summary,
        "pairs": results,
        "warnings": warnings,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.projection_reconcile",
        description=(
            "READ-ONLY projection check: for each registered state<->log pair, fold the "
            "append-only log and diff it against the stored state row. Pairs (data, not code): "
            "finance.settled_cents@<social-wiring|nosnolimiar|agents|core> (fin_entries.settled_cents vs "
            "signed unreversed fin_settlements), sw.pipeline.<funil|processos_venda|esteira> (card "
            "etapa_id vs latest pipeline_movimentos), agents.thread_participante.estado (estado vs "
            "latest thread_participante_eventos). Filter with pairs=[ids] or product=<slug>. "
            "Per pair: consistent | drift | inconclusive (no creds / query failed / table missing / "
            ">max_rows / ambiguous latest) | skipped (product asleep). ok only when every measured "
            "pair is consistent. Output: counts + first `sample` mismatches (max 50). Supabase "
            "Management API, SELECT-only SQL built from the registry. "
            "KB § PATTERNS/backend/projection-reconcile.md."
        ),
    )
    def _projection_reconcile(
        pairs: list[str] | None = None,
        product: str | None = None,
        sample: int = DEFAULT_SAMPLE,
        max_rows: int = DEFAULT_MAX_ROWS,
        project_ref: str = DEFAULT_PROJECT_REF,
        worktree_path: str | None = None,
    ) -> dict:
        return projection_reconcile(
            pairs=pairs, product=product, sample=sample, max_rows=max_rows,
            project_ref=project_ref, worktree_path=worktree_path,
        )


__all__ = [
    "DEFAULT_REGISTRY",
    "FoldResult",
    "LogSpec",
    "PairSpec",
    "StateSpec",
    "build_log_sql",
    "build_state_sql",
    "diff_projection",
    "fold_log",
    "projection_reconcile",
    "reconcile_pair",
    "register",
    "validate_pair",
]
