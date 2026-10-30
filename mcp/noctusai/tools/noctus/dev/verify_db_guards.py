"""noctus.dev.verify_db_guards — executable proof that a declared database
guard actually REFUSES what it claims to refuse.

THE RECURRING FAILURE THIS CLOSES (owner directive, 2026-09-18):
structure-green is not behaviour-green. "RLS enabled, 17 policies" passed
identically whether or not the policy did anything, because
`erp-certidoes` was ALSO `public = true` and a public bucket serves
objects via `/object/public/{bucket}/{path}` — a route that bypasses
`storage.objects` RLS entirely. A check that confirms a trigger/CHECK/
constraint EXISTS is structural; this tool instead RUNS the exact
operation the guard claims to refuse and observes whether it actually
raises. The refusal IS the pass. "The operation succeeded" is the
finding, at whatever severity that guard's rationale names.

THIS RUNS AGAINST PRODUCTION — the same Supabase Management-API
`SqlExecutor` DI seam `noctus.dev.migrate_product` / `noctus.dev.
schema_drift` already use (`make_sql_executor`, PAT resolved DB-first).
There is no dev/staging fleet to point this at instead (`KB § PATTERNS/
devops/dev-fleet-dormant.md`) — which is exactly why every probe below is
ROLLBACK-ONLY BY CONSTRUCTION, not by convention. See `wrap_rollback_only`
for the mechanism and its docstring for the three independent reasons a
probe run through it can never commit.

FAIL-CLOSED POSTURE (mirrors `check_storage_no_public_buckets` /
`schema_drift`'s precedent — "we couldn't check" must never read as "it's
fine"): a probe with no fixture row to test against, an executor error
that doesn't carry a recognised outcome, or a wrapped statement that
somehow returns `ok=True` (meaning the probe's own classification logic
never ran) are ALL a FAILURE, never a skip and never a silent pass. A
guard you could not verify is not a guard you verified.

REGISTRY SHAPE
---------------
Probes are DATA (`GuardProbe`), the runner is generic (`run_probe`). Each
probe declares: the product/schema it lives in, the exact DB object
(`guard_name`) it proves, the migration(s) that introduced/extended it
(provenance — NOT the enforcement key; see `check_migration_guard_has_
probe` in `compliance.py` for how `guard_name` membership is what a
future migration is checked against), a human rationale, its `kind`
(`"write_refusal"` — attempt the forbidden write, expect an exception —
`"write_allowed"` — attempt a SANCTIONED write, expect it to succeed, an
unexpected refusal is the finding (migration 165's boilerplate-line
exception) — or `"state_assertion"` — read live state, expect it to be
clean), and
`sql` — the probe BODY, always exactly one `DO $noc_probe$ ... $noc_probe$;`
statement (see `_do_block`).

SELF-PROVISIONING — the default, not the exception (2026-09-19). Every
`write_refusal` probe in `DEFAULT_REGISTRY` provisions its OWN specimen
row(s) via `INSERT`, inside the SAME rolled-back transaction, rather than
depending on production already holding data in the state under test.
This closed a real defect: the first version of the
`matricula_extracoes.codigo` / `.imovel_documento_id` probes searched for
an EXISTING row matching a predicate, and a live prod run showed both
predicates matching ZERO rows — not transiently, but because no
extraction had ever been linked to an imóvel, a state that was never
going to change on its own. That made those two probes permanently
`no_fixture`, which `predeploy_check`'s `db_guards` leg (correctly, by
the fail-closed rule above) treats as blocking — a gate red FOREVER for a
reason unrelated to whether the guard works, "a red gate everyone learns
to ignore" arriving through ambient data state rather than a structural
blind spot. See `_self_provisioned_frozen_column_probe` for the pattern
(borrow one real `org_id` — the one ambient dependency every probe of
this shape still has, and correctly still `no_fixture` on a genuinely
org-less database — then INSERT whatever FK-satisfying row(s) THIS
column's guard needs, cascading up to three tables deep for
`imovel_documento_id`). `_frozen_column_probe` (dynamic-fixture,
pre-2026-09-19) remains as the documented fallback for a future guard
whose fixture genuinely cannot be safely fabricated — not the default.

CLASSIFICATION CHANNEL — one mechanism for every probe, both kinds.
Every probe body, regardless of outcome, ends by RAISE'ing a sentinel
exception of the shape ``NOC_PROBE:<outcome>: <detail>`` — computed and
classified ENTIRELY INSIDE Postgres via a nested
``BEGIN ... EXCEPTION WHEN OTHERS ... END`` block that inspects `SQLERRM`
against the specific text/constraint-name THIS guard is expected to
raise (never "any exception = pass" — a value that happens to trip an
UNRELATED constraint is classified `ambiguous`, not `refused`). Because
every path raises, `SqlExecutor.execute()` always returns ``ok=False``
for a probe; the Python runner never inspects `rows` (unreliable across a
multi-statement round trip) — it `re.search`s the propagated error text
for the sentinel and classifies from THAT, tolerant of whatever prefix/
wrapping the Management API's HTTP error body adds.

Outcome -> status:
  refused / clean / allowed -> "pass"      (the guard did what it claims)
  permitted / violation / blocked -> "finding"   (the guard did NOT fire — the bug)
  no_fixture / ambiguous -> "failure"   (could not verify at all)
  (executor ok=True, or no sentinel found in the error text) -> "failure"

`allowed` / `blocked` are the INVERSE-POLARITY pair for a `"write_allowed"`
probe (migration 165 — see `_self_provisioned_write_allowed_probe`): the
write under test is SANCTIONED, so success is the pass (`allowed`) and an
unexpected refusal is the finding (`blocked`) — the opposite mapping from
`permitted`/`refused`, which is why they are separate sentinel words rather
than a reused pair.

KB § PATTERNS/common/methodology-execution-discipline.md § 8 (structure-
green is not behaviour-green) · KB § PATTERNS/backend/database-rls.md.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from . import migrate_product as _mp

logger = logging.getLogger(__name__)

DEFAULT_PROJECT_REF = "nyplttplcoyiiqjrvtiw"

# The ONE dollar-quote tag every probe body must use. Fixed (not per-probe)
# so `wrap_rollback_only` can assert on it by literal prefix/suffix rather
# than a keyword scan — see that function's docstring.
_PROBE_TAG = "$noc_probe$"


def _do_block(body: str) -> str:
    """The ONLY constructor of a probe's `DO` statement. Every probe in
    `DEFAULT_REGISTRY` is built through this (directly or via the small
    per-shape helpers below) — never hand-assembled — so every probe body
    is, by construction, exactly one statement wrapped in the fixed
    `$noc_probe$` tag `wrap_rollback_only` checks for.
    """
    return f"DO {_PROBE_TAG}\n{body.strip()}\n{_PROBE_TAG};"


# ---------------------------------------------------------------------------
# The rollback-only wrapper — THE structural seam.
# ---------------------------------------------------------------------------


def wrap_rollback_only(probe_sql: str) -> str:
    """Sandwich a probe body between `BEGIN;` and `ROLLBACK;`. This is the
    ONLY function in this module (or anywhere else) that emits those two
    literal transaction-control statements — no `GuardProbe.sql` may
    contain its own, and this function REFUSES (raises `ValueError`,
    never silently strips) anything that isn't exactly one `DO $noc_probe$
    ... $noc_probe$;` statement, so a probe cannot smuggle a THIRD
    top-level statement in alongside it.

    THREE INDEPENDENT reasons a probe run through this can never commit —
    not by convention, by construction:

    1. This wrapper is the only emitter of `BEGIN;`/`ROLLBACK;` in this
       module, and this module is the only caller of
       `SqlExecutor.execute()` for a probe. There is no code path,
       anywhere in this tool, that emits `COMMIT`.
    2. Every probe body ends by RAISE'ing a sentinel exception on EVERY
       branch (see the module docstring) — the "guard refused" branch
       included. An uncaught exception aborts the enclosing transaction;
       PostgreSQL will not allow an aborted transaction to be committed
       (the *database engine's* ACID guarantee, not this code's
       discipline) — so even if the trailing literal `ROLLBACK;` below is
       never reached because the error already ended the multi-statement
       message, nothing can be applied.
    3. For the one branch where the probe body does NOT raise (the
       "operation unexpectedly succeeded" / `permitted` finding — the
       actual bug this tool exists to catch), the probe SQL immediately
       raises its own `NOC_PROBE:permitted:` sentinel right after the
       write, so branch (2) still applies. And even hypothetically, if a
       probe author's SQL had NO raise on that branch at all, the literal
       `ROLLBACK;` this wrapper appends would run and undo it — belt
       *and* suspenders, not either/or.

    A probe body that tried to issue its OWN `BEGIN`/`COMMIT`/`ROLLBACK`
    would not even need policing here: PostgreSQL raises `ERROR: invalid
    transaction termination` for a transaction-control statement inside a
    `DO` block that is itself nested in an already-open explicit
    transaction (exactly what this wrapper opens) — the database refuses
    it outright. This function's own check (probe body must be exactly
    one `DO $noc_probe$ ... $noc_probe$;` statement, built exclusively via
    `_do_block`) exists as a STATIC, pre-flight version of that same
    refusal, so a malformed probe never even reaches the database to find
    out.
    """
    body = (probe_sql or "").strip()
    if not body:
        raise ValueError("wrap_rollback_only: empty probe SQL")
    if not (body.startswith(f"DO {_PROBE_TAG}") and body.endswith(f"{_PROBE_TAG};")):
        raise ValueError(
            "wrap_rollback_only: probe SQL must be exactly one "
            f"`DO {_PROBE_TAG} ... {_PROBE_TAG};` statement built via "
            "_do_block — refusing to wrap anything else (a probe may not "
            "declare its own transaction boundary, and this is the only "
            "shape this wrapper trusts enough to sandwich)."
        )
    return f"BEGIN;\n{body}\nROLLBACK;"


# `re.search` (not `.match`) — tolerant of whatever prefix the Management
# API's HTTP error body wraps our message in ("ERROR: ", a JSON `detail`
# field, etc.). `re.DOTALL` so a `detail` spanning "lines" (RAISE's `%`
# substitutions can carry newlines from a caught SQLERRM) is captured whole.
_SENTINEL_RE = re.compile(
    r"NOC_PROBE:(?P<outcome>refused|permitted|clean|violation|allowed|blocked|"
    r"no_fixture|ambiguous|pending):"
    r"\s*(?P<detail>.*)",
    re.DOTALL,
)

_OUTCOME_STATUS: dict[str, str] = {
    "refused": "pass",
    "clean": "pass",
    "allowed": "pass",
    "permitted": "finding",
    "violation": "finding",
    "blocked": "finding",
    "no_fixture": "failure",
    "ambiguous": "failure",
    # The probed table does not exist in the target DB yet (its migration is not applied): neither a pass nor a
    # failure -- named and listed under `pending`, never counted as checked.
    "pending": "pending_migration",
}
_OUTCOME_SEVERITY: dict[str, str] = {
    "permitted": "high",
    "violation": "critical",
    "blocked": "high",
    "no_fixture": "high",
    "ambiguous": "high",
    "pending": "info",
}


@dataclass(frozen=True)
class GuardProbe:
    """One registry entry — DATA, not code. See module docstring."""

    id: str
    product: str
    schema: str
    guard_name: str
    kind: str  # "write_refusal" | "write_allowed" | "state_assertion"
    sql: str  # exactly one `DO $noc_probe$ ... $noc_probe$;` statement
    rationale: str
    migrations: tuple[str, ...] = field(default_factory=tuple)


def run_probe(probe: GuardProbe, executor: "_mp.SqlExecutor") -> dict[str, Any]:
    """Run one probe through the rollback-only wrapper and classify the
    outcome. Never raises — every failure mode (including a malformed
    probe) comes back as a typed result with `status="failure"`.
    """
    base: dict[str, Any] = {
        # Both `id` and `probe_id` on purpose: `id` is the plain/expected
        # field name for a caller reading this result generically (2026-
        # 09-18 — an external runner printed `?` for every probe reading
        # a bare `id`); `probe_id` stays for this module's own consumers
        # (predeploy_check.py's db_guards leg, this file's own tests) —
        # same value, never allowed to drift apart.
        "id": probe.id,
        "probe_id": probe.id,
        "product": probe.product,
        "schema": probe.schema,
        "guard_name": probe.guard_name,
        "kind": probe.kind,
    }
    try:
        wrapped = wrap_rollback_only(probe.sql)
    except ValueError as exc:
        return {
            **base,
            "status": "failure",
            "outcome": None,
            "severity": "high",
            "detail": f"malformed probe SQL, refused before execution: {exc}",
        }

    result = executor.execute(wrapped)
    if result.get("ok"):
        # Every probe body raises a sentinel on EVERY branch (see module
        # docstring) — `ok=True` means our own classification logic never
        # ran at all. Silence is not a pass: fail closed.
        return {
            **base,
            "status": "failure",
            "outcome": None,
            "severity": "high",
            "detail": (
                "probe SQL returned ok=True with no sentinel outcome raised "
                "— classification impossible. Treated as unverified "
                "(fail-closed), never as a silent pass."
            ),
        }

    error = result.get("error") or ""
    m = _SENTINEL_RE.search(error)
    if not m and result.get("transient"):
        # Transport failure that survived the executor's paced retries: no verdict was produced. Distinct from
        # a real failure; re-run just these via `probe_ids` (the retry button).
        return {
            **base,
            "status": "unverified_transient",
            "outcome": None,
            "severity": "info",
            "detail": f"transient transport failure after automatic retries: {error[:300]}",
        }
    if not m:
        return {
            **base,
            "status": "failure",
            "outcome": None,
            "severity": "high",
            "detail": (
                "could not classify the probe outcome — the executor's "
                f"error text carried no recognised NOC_PROBE sentinel: {error!r}"
            ),
        }

    outcome = m.group("outcome")
    detail = (m.group("detail") or "").strip()
    status = _OUTCOME_STATUS.get(outcome, "failure")
    severity = _OUTCOME_SEVERITY.get(outcome) if status != "pass" else None
    return {**base, "status": status, "outcome": outcome, "severity": severity, "detail": detail}


# ---------------------------------------------------------------------------
# Probe-shape builders — every registry entry below goes through one of
# these (never hand-assembled), so the sentinel/classification contract is
# uniform and centrally testable.
# ---------------------------------------------------------------------------


def _sql_lit(text: str) -> str:
    """Escape `text` for safe interpolation INSIDE a single-quoted SQL
    string literal — doubles every `'` (the standard SQL escape; the same
    thing `quote_literal()` does server-side, done client-side here since
    these strings are message TEXT, not values bound by the driver).

    THE BUG THIS CLOSES (caught live against prod, 2026-09-18): every
    `no_fixture` message below interpolates a Python string (a fixture
    predicate like `status = 'concluida'`, or a free-text description)
    DIRECTLY into a single-quoted `RAISE EXCEPTION '...'` literal. Any
    unescaped `'` in that string terminates the literal early — for
    `status = 'concluida'` the message became
    `'...matching [status = '` + bare `concluida] to probe ...'` as loose
    SQL tokens, a syntax error the executor reported as a generic
    `42601`, which the runner could not distinguish from "cannot
    classify" and reported as `failure` — while the guard underneath was
    completely healthy. A probe that appears to run and verifies
    nothing is exactly the class of bug this whole module exists to
    eliminate; see `KB § PATTERNS/common/methodology-execution-
    discipline.md § 8`. Applied to EVERY interpolated value that lands
    inside a message literal below — including ones that do not
    currently contain a quote — because "currently safe" is not a
    property a future registry entry can be trusted to preserve.
    """
    return (text or "").replace("'", "''")


def _frozen_column_probe(
    *,
    schema: str,
    table: str,
    column: str,
    fixture_predicate: str,
    bad_value_sql: str,
    guard_fragment: str,
) -> str:
    """UPDATE an EXISTING row's `column` to `bad_value_sql`, expecting the
    row-level guard to raise. Dynamic fixture (`fixture_predicate`) —
    depends on ambient production data already being in the state under
    test, rather than provisioning it fresh.

    🔴 THE FALLBACK SHAPE, NOT THE DEFAULT (2026-09-19). This was the
    ORIGINAL design for every `matricula_extracoes` frozen-column probe;
    it was replaced in the registry by
    `_self_provisioned_frozen_column_probe` after a live prod run showed
    `codigo`/`imovel_documento_id` reporting a PERMANENT `no_fixture`
    (zero matching rows in prod, and no reason to expect that will ever
    change) — which would have made `predeploy_check`'s `db_guards` leg
    permanently red for a reason unrelated to correctness, "a gate
    everyone learns to ignore" arriving through data state instead of a
    structural blind spot. Self-provisioning removes the ambient
    dependency entirely by inserting its own specimen row(s) inside the
    same rolled-back transaction. Kept here — still exported, still
    tested — as the documented exception path for a FUTURE guard whose
    fixture genuinely cannot be safely fabricated (e.g. an FK chain into
    a table this module has no business writing to, or one gated by a
    trigger with an un-auditable side effect); reach for
    `_self_provisioned_frozen_column_probe` first.

    The guard fires inside a `BEFORE UPDATE` trigger, which runs BEFORE
    Postgres validates any FK/CHECK on the new row value, so
    `bad_value_sql` need not itself be a valid value — but classification
    still checks `guard_fragment` against the caught `SQLERRM`, so a
    value that (surprisingly) trips a DIFFERENT constraint first is
    reported `ambiguous`, never a false `refused`.

    `fixture_predicate` is used TWICE, for two different purposes: raw
    (unescaped) in the `WHERE` clause, where it must stay executable SQL
    code — and `_sql_lit`-escaped in the `no_fixture` MESSAGE, where it is
    inert text inside a string literal. Conflating the two is exactly the
    quote-escaping bug this shape now guards against.
    """
    predicate_lit = _sql_lit(fixture_predicate)
    guard_fragment_lit = _sql_lit(guard_fragment)
    return _do_block(f"""
DECLARE
  v_id uuid;
BEGIN
  SELECT id INTO v_id FROM {schema}.{table} WHERE {fixture_predicate} LIMIT 1;
  IF v_id IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no row in {schema}.{table} matching [{predicate_lit}] to probe {column} against';
  END IF;
  BEGIN
    UPDATE {schema}.{table} SET {column} = {bad_value_sql} WHERE id = v_id;
    RAISE EXCEPTION 'NOC_PROBE:permitted: UPDATE {schema}.{table}.{column} for id=% succeeded — the write-once guard did not fire', v_id;
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{guard_fragment_lit}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
""")


def _insert_check_probe(
    *,
    schema: str,
    table: str,
    columns_sql: str,
    values_sql: str,
    fixture_from: str,
    fixture_description: str,
    guard_fragment: str,
) -> str:
    """INSERT a synthetic, throwaway row via `SELECT ... FROM {fixture_from}
    LIMIT 1` (borrowing an existing row's FK-satisfying columns —
    `org_id`/`extracao_id`/etc. — without mutating that row at all), with
    a `values_sql` deliberately shaped to trip one specific CHECK/UNIQUE
    constraint. `fixture_from` returning zero rows is `no_fixture` (the
    `SELECT ... LIMIT 1` would otherwise silently insert nothing and the
    probe would misreport `permitted` for having tested nothing at all —
    the exact "ambiguous result treated as a pass" shape this tool exists
    to refuse). `fixture_description` and `guard_fragment` are `_sql_lit`
    -escaped before landing inside a message literal — see `_sql_lit`.
    """
    desc_lit = _sql_lit(fixture_description)
    guard_fragment_lit = _sql_lit(guard_fragment)
    return _do_block(f"""
BEGIN
  IF NOT EXISTS (SELECT 1 FROM {fixture_from}) THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: {desc_lit}';
  END IF;
  BEGIN
    INSERT INTO {schema}.{table} ({columns_sql})
    SELECT {values_sql} FROM {fixture_from} LIMIT 1;
    RAISE EXCEPTION 'NOC_PROBE:permitted: INSERT into {schema}.{table} succeeded — the constraint under test did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{guard_fragment_lit}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
""")


def _state_assertion_probe(
    *,
    select_count_sql: str,
    clean_message: str,
    violation_message_prefix: str,
) -> str:
    """Read-only state check: `select_count_sql` must return 0. No write,
    no fixture — every rollback here is a structural no-op (nothing was
    ever mutated), included anyway for uniformity (every probe, of both
    kinds, goes through the exact same `wrap_rollback_only` seam).
    `clean_message` / `violation_message_prefix` are `_sql_lit`-escaped —
    see `_sql_lit`.
    """
    clean_lit = _sql_lit(clean_message)
    violation_lit = _sql_lit(violation_message_prefix)
    return _do_block(f"""
DECLARE
  v_count bigint;
BEGIN
  {select_count_sql}
  IF v_count > 0 THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: {violation_lit} % row(s)', v_count;
  END IF;
  RAISE EXCEPTION 'NOC_PROBE:clean: {clean_lit}';
END;
""")


# ---------------------------------------------------------------------------
# Registry — social_wiring.matricula_extracoes write-once guard
# (migrations 111/135/136; function `matricula_extracoes_protege_concluida`).
# ---------------------------------------------------------------------------

_SW_SCHEMA = "social_wiring"
_MATRICULA_TABLE = "matricula_extracoes"
_MATRICULA_GUARD_FN = "matricula_extracoes_protege_concluida"
_MATRICULA_GUARD_FRAGMENT = "não pode ser alterado"
_MATRICULA_MIGRATIONS = (
    "111_matricula_lgpd_followups.sql",
    "135_matricula_retencao_fonte.sql",
    "136_matricula_ruido_e_abertura.sql",
    # 154 redefines the function with ONE exception (a legacy **/<u> markup
    # strip, verified in the trigger); every probe below is a rewrite that is
    # NOT a markup strip, so each must still be refused.
    "154_imovel_extracao_proveniencia.sql",
    # 165 adds a SECOND exception (whole-line boilerplate deletion, verified
    # via matricula_texto_e_remocao_boilerplate) — see the write_allowed
    # probe below (the sanctioned edit) and the accompanying write_refusal
    # probe (a non-boilerplate line deletion, the shape a naive "is it
    # shorter and a subsequence" check alone would wrongly let through).
    "165_matricula_boilerplate_guard.sql",
)


def _self_provisioned_frozen_column_probe(
    *,
    probe_id: str,
    column: str,
    declare_extra: str,
    setup_sql: str,
    bad_value_sql: str,
    rationale_extra: str,
) -> GuardProbe:
    """SELF-PROVISIONING variant of the frozen-column write-once probe
    (2026-09-19 — see module docstring "SELF-PROVISIONING" section for
    why this replaced the earlier dynamic-fixture design). `setup_sql`
    INSERTs whatever synthetic row(s) this specific column needs (built
    fresh, inside the SAME rolled-back transaction) and MUST end with
    `v_id` set to the row under test. The only remaining external
    dependency, shared by every probe of this shape, is an existing
    `org_id` to borrow (see the SELECT immediately below) — see the
    module docstring for why that is a fundamentally different, much
    weaker dependency than "this SPECIFIC column has a non-null value
    somewhere", and correctly still `no_fixture` (never a skip) on a
    genuinely org-less database.
    """
    guard_fragment_lit = _sql_lit(_MATRICULA_GUARD_FRAGMENT)
    sql = _do_block(f"""
DECLARE
  v_org_id uuid;
  v_id uuid;
{declare_extra}
BEGIN
  SELECT org_id INTO v_org_id FROM {_SW_SCHEMA}.{_MATRICULA_TABLE} LIMIT 1;
  IF v_org_id IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no existing {_SW_SCHEMA}.{_MATRICULA_TABLE} row to borrow an org_id from (a genuinely org-less database)';
  END IF;
{setup_sql}
  BEGIN
    UPDATE {_SW_SCHEMA}.{_MATRICULA_TABLE} SET {column} = {bad_value_sql} WHERE id = v_id;
    RAISE EXCEPTION 'NOC_PROBE:permitted: UPDATE {_SW_SCHEMA}.{_MATRICULA_TABLE}.{column} for id=% succeeded — the write-once guard did not fire', v_id;
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{guard_fragment_lit}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
""")
    return GuardProbe(
        id=probe_id,
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name=_MATRICULA_GUARD_FN,
        kind="write_refusal",
        migrations=_MATRICULA_MIGRATIONS,
        rationale=(
            f"`{_MATRICULA_GUARD_FN}` (BEFORE UPDATE trigger) freezes "
            f"`{_MATRICULA_TABLE}.{column}` once the extraction has reached "
            "the state that makes it write-once — a generated deed already "
            "quotes what this row held at that point, so letting it move "
            "after the fact would silently change what an already-signed "
            "instrument is understood to have quoted. Same function, "
            "extended by 135/136 without weakening what 111 established for "
            "the earlier columns. " + rationale_extra
        ),
        sql=sql,
    )


def _self_provisioned_write_allowed_probe(
    *,
    probe_id: str,
    column: str,
    declare_extra: str,
    setup_sql: str,
    good_value_sql: str,
    rationale_extra: str,
) -> GuardProbe:
    """INVERSE-POLARITY sibling of `_self_provisioned_frozen_column_probe`
    (migration 165): the write under test is SANCTIONED — success is the
    pass (`allowed`), an unexpected refusal is the finding (`blocked`).
    Same self-provisioning discipline (own specimen row(s), inside the same
    rolled-back transaction, borrowing only an existing `org_id`) and the
    same `no_fixture` escape hatch on a genuinely org-less database.
    """
    guard_fragment_lit = _sql_lit(_MATRICULA_GUARD_FRAGMENT)
    sql = _do_block(f"""
DECLARE
  v_org_id uuid;
  v_id uuid;
{declare_extra}
BEGIN
  SELECT org_id INTO v_org_id FROM {_SW_SCHEMA}.{_MATRICULA_TABLE} LIMIT 1;
  IF v_org_id IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no existing {_SW_SCHEMA}.{_MATRICULA_TABLE} row to borrow an org_id from (a genuinely org-less database)';
  END IF;
{setup_sql}
  BEGIN
    UPDATE {_SW_SCHEMA}.{_MATRICULA_TABLE} SET {column} = {good_value_sql} WHERE id = v_id;
    RAISE EXCEPTION 'NOC_PROBE:allowed: UPDATE {_SW_SCHEMA}.{_MATRICULA_TABLE}.{column} for id=% succeeded — the sanctioned boilerplate-only edit was let through, as it should be', v_id;
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:allowed:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{guard_fragment_lit}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:blocked: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
""")
    return GuardProbe(
        id=probe_id,
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name=_MATRICULA_GUARD_FN,
        kind="write_allowed",
        migrations=_MATRICULA_MIGRATIONS,
        rationale=(
            f"`{_MATRICULA_GUARD_FN}` (BEFORE UPDATE trigger) must let a "
            "boilerplate-only line deletion through — `backfill_service."
            "normalizar_extracao`'s second pass (`remover_boilerplate`) "
            "writes exactly this shape for 7 of 8 real prod rows, including "
            "EUROVILLE-535's matrícula. A guard that (correctly) refuses "
            "every OTHER rewrite must not ALSO refuse this one. " + rationale_extra
        ),
        sql=sql,
    )


def _self_provisioned_insert_check_probe(
    *,
    probe_id: str,
    product: str,
    schema: str,
    table: str,
    guard_name: str,
    declare_extra: str,
    setup_sql: str,
    insert_sql: str,
    guard_fragment: str,
    rationale: str,
    migrations: tuple[str, ...],
) -> GuardProbe:
    """Self-provisioning sibling of `_insert_check_probe`: for a CHECK whose
    fixture needs MORE than one borrowed row (an FK chain this probe must
    build itself — see `imovel_dados`'s `(org_id, codigo)` FK to `imoveis`,
    which itself FKs `imovel_registry`), `setup_sql` INSERTs whatever the
    chain needs, inside the same rolled-back transaction, before the ONE
    INSERT under test (`insert_sql`) runs against `table`. The only
    remaining external dependency is an existing `org_id` to borrow — same
    `no_fixture` shape `_self_provisioned_frozen_column_probe` uses, for
    the identical reason (a genuinely org-less database is the only case
    this cannot self-provision past).
    """
    guard_fragment_lit = _sql_lit(guard_fragment)
    sql = _do_block(f"""
DECLARE
  v_org_id uuid;
{declare_extra}
BEGIN
  SELECT org_id INTO v_org_id FROM {schema}.{table} LIMIT 1;
  IF v_org_id IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no existing {schema}.{table} row to borrow an org_id from (a genuinely org-less database)';
  END IF;
{setup_sql}
  BEGIN
    {insert_sql}
    RAISE EXCEPTION 'NOC_PROBE:permitted: INSERT into {schema}.{table} succeeded — the constraint under test did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{guard_fragment_lit}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
""")
    return GuardProbe(
        id=probe_id,
        product=product,
        schema=schema,
        guard_name=guard_name,
        kind="write_refusal",
        migrations=migrations,
        rationale=rationale,
        sql=sql,
    )


# A fresh, collision-proof "código" value for the two probes that need one
# (`codigo` itself, and `imovel_documento_id`'s FK chain, which also needs
# a `codigo` — see the module docstring). Hyphens stripped only for
# readability in error messages; uniqueness comes from gen_random_uuid().
_FRESH_CODIGO_DECL = "v_codigo text := 'NOC-PROBE-' || replace(gen_random_uuid()::text, '-', '');"

_MATRICULA_PROBES: tuple[GuardProbe, ...] = (
    _self_provisioned_frozen_column_probe(
        probe_id="matricula_extracoes.texto_extraido.frozen_after_concluida",
        column="texto_extraido",
        declare_extra="",
        setup_sql=f"""
  INSERT INTO {_SW_SCHEMA}.{_MATRICULA_TABLE} (org_id, user_id, nome_arquivo, status, texto_extraido)
  VALUES (v_org_id, gen_random_uuid(), 'noc-probe.pdf', 'concluida', 'texto de prova do probe')
  RETURNING id INTO v_id;
""",
        bad_value_sql="'NOC-PROBE-' || gen_random_uuid()::text",
        rationale_extra="Self-provisions a throwaway `concluida` row — no ambient fixture required.",
    ),
    _self_provisioned_frozen_column_probe(
        probe_id="matricula_extracoes.codigo.frozen_after_set",
        column="codigo",
        declare_extra=f"  {_FRESH_CODIGO_DECL}",
        setup_sql=f"""
  INSERT INTO {_SW_SCHEMA}.imovel_registry (org_id, codigo_canonical) VALUES (v_org_id, v_codigo);
  INSERT INTO {_SW_SCHEMA}.{_MATRICULA_TABLE} (org_id, user_id, nome_arquivo, status, codigo)
  VALUES (v_org_id, gen_random_uuid(), 'noc-probe.pdf', 'pendente', v_codigo)
  RETURNING id INTO v_id;
""",
        bad_value_sql="COALESCE(codigo, '') || '-noc-probe'",
        rationale_extra=(
            "Self-provisions a throwaway `imovel_registry` row so `codigo`'s "
            "own composite FK (org_id, codigo) -> imovel_registry(org_id, "
            "codigo_canonical) is satisfied without depending on prod already "
            "having a linked extraction (which, as of 2026-09-18, it does not "
            "— this is the exact ambient-data dependency that turned "
            "`no_fixture` into a false, permanent predeploy block)."
        ),
    ),
    _self_provisioned_frozen_column_probe(
        probe_id="matricula_extracoes.imovel_documento_id.frozen_after_set",
        column="imovel_documento_id",
        declare_extra=f"  {_FRESH_CODIGO_DECL}\n  v_doc_id uuid;",
        setup_sql=f"""
  INSERT INTO {_SW_SCHEMA}.imovel_registry (org_id, codigo_canonical) VALUES (v_org_id, v_codigo);
  INSERT INTO {_SW_SCHEMA}.imoveis (org_id, codigo) VALUES (v_org_id, v_codigo);
  INSERT INTO {_SW_SCHEMA}.imovel_documentos
    (org_id, codigo, storage_path, nome_original, mime_type, tamanho_bytes, tipo_documento)
  VALUES (v_org_id, v_codigo, 'noc-probe/path.pdf', 'noc-probe.pdf', 'application/pdf', 0, 'matricula')
  RETURNING id INTO v_doc_id;
  INSERT INTO {_SW_SCHEMA}.{_MATRICULA_TABLE} (org_id, user_id, nome_arquivo, status, codigo, imovel_documento_id)
  VALUES (v_org_id, gen_random_uuid(), 'noc-probe.pdf', 'pendente', v_codigo, v_doc_id)
  RETURNING id INTO v_id;
""",
        bad_value_sql="gen_random_uuid()",
        rationale_extra=(
            "The deepest FK chain in this registry: `imovel_documento_id` -> "
            "imovel_documentos(id), whose OWN composite FK (org_id, codigo) -> "
            "imoveis(org_id, codigo) needs a real imóvel row, AND the sibling "
            "CHECK `imovel_documento_id IS NULL OR codigo IS NOT NULL` needs "
            "`codigo` set too (its own FK to imovel_registry, same as the "
            "`codigo` probe above). All three (imovel_registry, imoveis, "
            "imovel_documentos) are self-provisioned fresh — verified to carry "
            "no INSERT trigger (only a BEFORE UPDATE updated_at-touch on the "
            "first two) and no NOT-NULL column beyond what is set here, so "
            "this INSERT chain has no unaccounted side effect."
        ),
    ),
    _self_provisioned_frozen_column_probe(
        probe_id="matricula_extracoes.arquivo_origem_id.frozen_after_set",
        column="arquivo_origem_id",
        declare_extra="  v_arquivo_id uuid;",
        setup_sql=f"""
  INSERT INTO {_SW_SCHEMA}.matricula_extracao_arquivos (org_id, storage_path, nome_original, mime_type, tamanho_bytes)
  VALUES (v_org_id, 'noc-probe/path.pdf', 'noc-probe.pdf', 'application/pdf', 0)
  RETURNING id INTO v_arquivo_id;
  INSERT INTO {_SW_SCHEMA}.{_MATRICULA_TABLE} (org_id, user_id, nome_arquivo, status, arquivo_origem_id)
  VALUES (v_org_id, gen_random_uuid(), 'noc-probe.pdf', 'pendente', v_arquivo_id)
  RETURNING id INTO v_id;
""",
        bad_value_sql="gen_random_uuid()",
        rationale_extra="Self-provisions a throwaway `matricula_extracao_arquivos` row (no triggers, no further FKs).",
    ),
    _self_provisioned_frozen_column_probe(
        probe_id="matricula_extracoes.substituida_por.frozen_after_set",
        column="substituida_por",
        declare_extra="  v_superseded_id uuid;",
        setup_sql=f"""
  INSERT INTO {_SW_SCHEMA}.{_MATRICULA_TABLE} (org_id, user_id, nome_arquivo, status)
  VALUES (v_org_id, gen_random_uuid(), 'noc-probe-superseded.pdf', 'concluida')
  RETURNING id INTO v_superseded_id;
  INSERT INTO {_SW_SCHEMA}.{_MATRICULA_TABLE} (org_id, user_id, nome_arquivo, status, substituida_por)
  VALUES (v_org_id, gen_random_uuid(), 'noc-probe.pdf', 'concluida', v_superseded_id)
  RETURNING id INTO v_id;
""",
        bad_value_sql="gen_random_uuid()",
        rationale_extra=(
            "Self-referential — provisions its OWN two rows (the "
            "'superseded' row `substituida_por` points at, plus the row "
            "under test) entirely within `matricula_extracoes` itself, no "
            "other table involved."
        ),
    ),
    _self_provisioned_frozen_column_probe(
        probe_id="matricula_extracoes.ruido.frozen_after_concluida",
        column="ruido",
        declare_extra="",
        setup_sql=f"""
  INSERT INTO {_SW_SCHEMA}.{_MATRICULA_TABLE} (org_id, user_id, nome_arquivo, status)
  VALUES (v_org_id, gen_random_uuid(), 'noc-probe.pdf', 'concluida')
  RETURNING id INTO v_id;
""",
        bad_value_sql="'[{\"start\":0,\"end\":1,\"kind\":\"noc_probe\"}]'::jsonb",
        rationale_extra="Self-provisions a throwaway `concluida` row (`ruido` defaults to `[]`) — no ambient fixture required.",
    ),
    # ------------------------------------------------------------------
    # Migration 165 — the boilerplate-line exception, both directions.
    # ------------------------------------------------------------------
    _self_provisioned_write_allowed_probe(
        probe_id="matricula_extracoes.texto_extraido.boilerplate_only_deletion_allowed",
        column="texto_extraido",
        declare_extra="",
        setup_sql=f"""
  INSERT INTO {_SW_SCHEMA}.{_MATRICULA_TABLE} (org_id, user_id, nome_arquivo, status, texto_extraido)
  VALUES (
    v_org_id, gen_random_uuid(), 'noc-probe.pdf', 'concluida',
    E'Valide aqui\\neste documento\\n\\nMat. 3917 - conteudo real do probe'
  )
  RETURNING id INTO v_id;
""",
        good_value_sql="'Mat. 3917 - conteudo real do probe'",
        rationale_extra=(
            "The EUROVILLE-535 shape: two boilerplate lines "
            "('Valide aqui' / 'este documento') and a blank line ahead of "
            "the real content, all deleted in one UPDATE, the real content "
            "line kept byte-identical — exactly what "
            "matricula_texto_e_remocao_boilerplate must return true for."
        ),
    ),
    _self_provisioned_frozen_column_probe(
        probe_id="matricula_extracoes.texto_extraido.non_boilerplate_line_deletion_still_refused",
        column="texto_extraido",
        declare_extra="",
        setup_sql=f"""
  INSERT INTO {_SW_SCHEMA}.{_MATRICULA_TABLE} (org_id, user_id, nome_arquivo, status, texto_extraido)
  VALUES (
    v_org_id, gen_random_uuid(), 'noc-probe.pdf', 'concluida',
    E'Valide aqui\\nLinha real numero um\\nLinha real numero dois'
  )
  RETURNING id INTO v_id;
""",
        bad_value_sql="E'Valide aqui\\nLinha real numero um'",
        rationale_extra=(
            "THE shape that could fool a naive 'is NEW shorter and a "
            "subsequence of OLD' check alone: this rewrite deletes the "
            "boilerplate line's sibling — a genuine, real content line "
            "('Linha real numero dois') — while still being strictly "
            "shorter and a valid in-order subsequence of OLD's lines. "
            "Deletability is per-LINE (matricula_linha_e_boilerplate), not "
            "'the edit looks boilerplate-shaped overall', so this must "
            "still be refused."
        ),
    ),
)


# ---------------------------------------------------------------------------
# Registry — matricula_extracoes_ruido_shape CHECK (migration 136).
# ---------------------------------------------------------------------------

_RUIDO_SHAPE_PROBE = GuardProbe(
    id="matricula_extracoes.ruido.shape_check",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="matricula_extracoes_ruido_shape",
    kind="write_refusal",
    migrations=("136_matricula_ruido_e_abertura.sql",),
    rationale=(
        "A malformed `ruido` element (bad `kind`, `end < start`, negative "
        "`start`, non-array) would silently shift what a generated deed's "
        "quote subtracts, so it is refused at write time rather than "
        "discovered inside a signed instrument. Enforced by the CHECK "
        "constraint `matricula_extracoes_ruido_shape` via the IMMUTABLE "
        "helper `matricula_ruido_valido`."
    ),
    sql=_insert_check_probe(
        schema=_SW_SCHEMA,
        table=_MATRICULA_TABLE,
        columns_sql="org_id, user_id, nome_arquivo, ruido",
        values_sql=(
            "org_id, gen_random_uuid(), 'noc-probe.pdf', "
            "'[{\"start\":5,\"end\":1,\"kind\":\"bogus\"}]'::jsonb"
        ),
        fixture_from=f"{_SW_SCHEMA}.{_MATRICULA_TABLE}",
        fixture_description=f"no row in {_SW_SCHEMA}.{_MATRICULA_TABLE} to borrow an org_id from",
        guard_fragment='constraint "matricula_extracoes_ruido_shape"',
    ),
)


# ---------------------------------------------------------------------------
# Registry — imovel_dados título/ônus "pareado" CHECKs (migration 166,
# replacing 115's confirmado_em-paired ones — see that migration's header
# for why: 154's D1 machine-pending write for these two fields was
# refused by the OLD CHECK, a live prod bug (E2E-IMV-LIVRE), fixed by
# re-keying onto `_origem`). Each probe proves the RE-KEYED constraint
# still refuses a genuinely malformed row (value present, `_origem` NULL)
# — the fix must not have accidentally dropped enforcement entirely.
# ---------------------------------------------------------------------------

_IMOVEL_DADOS_TABLE_166 = "imovel_dados"
_IMOVEL_DADOS_MIGRATIONS = (
    "075_imovel_dados_cartorio.sql",
    "115_matricula_ato_detalhes.sql",
    "166_titulo_onus_confirmado_check_rekey.sql",
)
#: The self-provisioning chain `imovel_dados(org_id, codigo)` needs — its
#: own FK to `imoveis(org_id, codigo)`, which FKs `imovel_registry(org_id,
#: codigo_canonical)` — identical to the `imovel_documento_id` matricula
#: probe's first two steps (verified there to carry no INSERT trigger and
#: no unaccounted NOT-NULL column). Runs INSIDE the generic helper's outer
#: `BEGIN` block (after the org_id borrow it already performs), exactly
#: like every `_self_provisioned_frozen_column_probe.setup_sql` — a plain
#: statement sequence, no nested DECLARE/BEGIN (`v_codigo` must stay in
#: the OUTER scope so `insert_sql`, which runs after this, can still see it).
_IMOVEL_DADOS_DECLARE_EXTRA = (
    "  v_codigo text := 'NOC-PROBE-' || replace(gen_random_uuid()::text, '-', '');"
)
_IMOVEL_DADOS_SETUP_SQL = f"""
  INSERT INTO {_SW_SCHEMA}.imovel_registry (org_id, codigo_canonical) VALUES (v_org_id, v_codigo);
  INSERT INTO {_SW_SCHEMA}.imoveis (org_id, codigo) VALUES (v_org_id, v_codigo);
"""

_TITULO_PAREADO_PROBE = _self_provisioned_insert_check_probe(
    probe_id="imovel_dados.titulo_aquisitivo_texto_pareado.shape_check",
    product="social-wiring",
    schema=_SW_SCHEMA,
    table=_IMOVEL_DADOS_TABLE_166,
    guard_name="imovel_dados_titulo_aquisitivo_texto_pareado",
    declare_extra=_IMOVEL_DADOS_DECLARE_EXTRA,
    setup_sql=_IMOVEL_DADOS_SETUP_SQL,
    insert_sql=(
        f"INSERT INTO {_SW_SCHEMA}.{_IMOVEL_DADOS_TABLE_166} "
        "(org_id, codigo, titulo_aquisitivo_texto, titulo_aquisitivo_texto_origem) "
        "VALUES (v_org_id, v_codigo, 'NOC-PROBE-titulo-sem-origem', NULL);"
    ),
    guard_fragment='constraint "imovel_dados_titulo_aquisitivo_texto_pareado"',
    rationale=(
        "Migration 166 re-keyed this CHECK off `titulo_aquisitivo_texto_origem` "
        "(replacing 115's `_confirmado_em`-paired one, which refused 154's D1 "
        "machine-pending write — the live prod bug E2E-IMV-LIVRE hit) — this "
        "proves the re-keyed constraint still refuses a genuinely malformed "
        "row (a value with no `_origem` at all, machine-pending or "
        "otherwise), so relaxing the constraint for the pending case did not "
        "accidentally drop enforcement entirely."
    ),
    migrations=_IMOVEL_DADOS_MIGRATIONS,
)

_ONUS_CREDOR_PAREADO_PROBE = _self_provisioned_insert_check_probe(
    probe_id="imovel_dados.onus_credor_pareado.shape_check",
    product="social-wiring",
    schema=_SW_SCHEMA,
    table=_IMOVEL_DADOS_TABLE_166,
    guard_name="imovel_dados_onus_credor_pareado",
    declare_extra=_IMOVEL_DADOS_DECLARE_EXTRA,
    setup_sql=_IMOVEL_DADOS_SETUP_SQL,
    insert_sql=(
        f"INSERT INTO {_SW_SCHEMA}.{_IMOVEL_DADOS_TABLE_166} "
        "(org_id, codigo, onus_credor, onus_credor_origem) "
        "VALUES (v_org_id, v_codigo, 'NOC-PROBE-credor-sem-origem', NULL);"
    ),
    guard_fragment='constraint "imovel_dados_onus_credor_pareado"',
    rationale=(
        "Same reasoning and shape as `imovel_dados.titulo_aquisitivo_texto_"
        "pareado.shape_check`, for `onus_credor`."
    ),
    migrations=_IMOVEL_DADOS_MIGRATIONS,
)


# ---------------------------------------------------------------------------
# Registry — imovel_documento_acessos.acao CHECK (109, widened 111/115/150).
# ---------------------------------------------------------------------------

_ACAO_CHECK_PROBE = GuardProbe(
    id="imovel_documento_acessos.acao.shape_check",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="imovel_documento_acessos_acao_check",
    kind="write_refusal",
    migrations=(
        "109_matricula_estruturada.sql",
        "111_matricula_lgpd_followups.sql",
        "115_matricula_ato_detalhes.sql",
        "150_matricula_extracao_vincular_imovel.sql",
    ),
    rationale=(
        "`acao` is a closed vocabulary — every access-log reader (LGPD "
        "exports, the checklist/geração panels) matches on it by exact "
        "string, so a typo'd or free-text value would silently vanish from "
        "every one of them instead of erroring where it was written. "
        "Enforced by the CHECK constraint `imovel_documento_acessos_acao_"
        "check`, widened once per new logged action (109 'view'/'download'/"
        "'delete' -> 111 adds 'text_view' -> 115 adds 'detalhes_view' -> 150 "
        "adds 'imovel_vinculado') without ever loosening it to accept "
        "anything outside the named set."
    ),
    sql=_insert_check_probe(
        schema=_SW_SCHEMA,
        table="imovel_documento_acessos",
        columns_sql="org_id, extracao_id, acao",
        values_sql="org_id, id, 'noc-probe-not-a-real-acao'",
        fixture_from=f"{_SW_SCHEMA}.{_MATRICULA_TABLE}",
        fixture_description=(
            f"no row in {_SW_SCHEMA}.{_MATRICULA_TABLE} to attach a probe "
            "access-log row to (via extracao_id)"
        ),
        guard_fragment='constraint "imovel_documento_acessos_acao_check"',
    ),
)


_CERTIDAO_ACAO_CHECK_PROBE = GuardProbe(
    id="certidao_resultado_acessos.acao.shape_check",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="certidao_resultado_acessos_acao_check",
    kind="write_refusal",
    migrations=(
        "107_certidoes_estruturadas.sql",
        "196_certidao_releitura.sql",
    ),
    rationale=(
        "`acao` is the certidão LGPD content-read log's closed vocabulary — "
        "readers match it by exact string, so a free-text value would vanish "
        "from every one of them instead of erroring where it was written. "
        "Enforced by the CHECK constraint `certidao_resultado_acessos_acao_"
        "check` (107 'view'/'download'/'delete' -> 196 adds 'releitura'), "
        "never loosened to accept anything outside the named set."
    ),
    sql=_insert_check_probe(
        schema=_SW_SCHEMA,
        table="certidao_resultado_acessos",
        columns_sql="org_id, documento_id, acao",
        values_sql="org_id, id, 'noc-probe-not-a-real-acao'",
        fixture_from=f"{_SW_SCHEMA}.certidao_resultados",
        fixture_description=(
            f"no row in {_SW_SCHEMA}.certidao_resultados to attach a probe "
            "access-log row to (via documento_id)"
        ),
        guard_fragment='constraint "certidao_resultado_acessos_acao_check"',
    ),
)


# ---------------------------------------------------------------------------
# Registry — social_wiring.matricula_abertura_blocos constraints (136).
# ---------------------------------------------------------------------------

_ABERTURA_TABLE = "matricula_abertura_blocos"
_ABERTURA_FIXTURE_FROM = f"{_SW_SCHEMA}.{_MATRICULA_TABLE}"
_ABERTURA_FIXTURE_DESC = f"no row in {_SW_SCHEMA}.{_MATRICULA_TABLE} to attach a probe {_ABERTURA_TABLE} row to"


def _abertura_check_probe(probe_id: str, guard_name: str, campo: str, spans: str, rationale: str) -> GuardProbe:
    return GuardProbe(
        id=probe_id,
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name=guard_name,
        kind="write_refusal",
        migrations=("136_matricula_ruido_e_abertura.sql",),
        rationale=rationale,
        sql=_insert_check_probe(
            schema=_SW_SCHEMA,
            table=_ABERTURA_TABLE,
            columns_sql="org_id, extracao_id, campo, char_inicio, char_fim, rotulo_inicio, rotulo_fim",
            values_sql=f"org_id, id, {campo}, {spans}",
            fixture_from=_ABERTURA_FIXTURE_FROM,
            fixture_description=_ABERTURA_FIXTURE_DESC,
            guard_fragment=f'constraint "{guard_name}"',
        ),
    )


_ABERTURA_PROBES: tuple[GuardProbe, ...] = (
    _abertura_check_probe(
        "matricula_abertura_blocos.campo.allowed_values",
        # Unnamed column-level CHECK — Postgres's own auto-naming
        # convention for an unnamed CHECK is `<table>_<column>_check`.
        # NOT verified against a live database in this sandbox (no
        # credentials resolved here) — confirm this literal name via
        # `SELECT conname FROM pg_constraint WHERE conrelid =
        # 'social_wiring.matricula_abertura_blocos'::regclass` before
        # relying on this probe; if it disagrees, only `guard_name` below
        # and the matching `check_migration_guard_has_probe` allowlist (if
        # any) need updating — the probe's own INSERT still exercises the
        # real constraint regardless of what we call it.
        "matricula_abertura_blocos_campo_check",
        campo="'bogus_campo'",
        spans="0, 10, 0, 0",
        rationale=(
            "`campo` is restricted to the four typed abertura sub-spans "
            "(`descricao_imovel`, `cadastro_municipal`, `proprietarios`, "
            "`registro_anterior`) — a fifth value would make the contract's "
            "`objeto` clause resolve against an undefined slot."
        ),
    ),
    _abertura_check_probe(
        "matricula_abertura_blocos.char_span.non_negative_and_ordered",
        "matricula_abertura_blocos_span_valido",
        campo="'descricao_imovel'",
        spans="10, 5, 0, 0",  # char_fim (5) < char_inicio (10)
        rationale=(
            "`char_fim >= char_inicio` — an inverted span would quote the "
            "wrong slice (or none) at contract-render time."
        ),
    ),
    _abertura_check_probe(
        "matricula_abertura_blocos.rotulo_span.within_char_inicio",
        "matricula_abertura_blocos_rotulo_valido",
        campo="'cadastro_municipal'",
        spans="10, 20, 0, 15",  # rotulo_fim (15) > char_inicio (10)
        rationale=(
            "`rotulo_fim <= char_inicio` — the recognised label token "
            "must end before the block's own content starts, or the "
            "docx template's own \"IMÓVEL:\" label would be doubled."
        ),
    ),
)

_ABERTURA_UNIQUE_PROBE = GuardProbe(
    id="matricula_abertura_blocos.extracao_campo.unique",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="idx_sw_matricula_abertura_blocos_campo",
    kind="write_refusal",
    migrations=("136_matricula_ruido_e_abertura.sql",),
    rationale=(
        "One block per field per extraction — a second `IMÓVEL:` would "
        "make \"the property description\" ambiguous, and an ambiguous "
        "legal quote is a defect, not a choice to resolve at read time."
    ),
    sql=_do_block(f"""
DECLARE
  v_extracao_id uuid;
  v_org_id uuid;
BEGIN
  SELECT id, org_id INTO v_extracao_id, v_org_id FROM {_SW_SCHEMA}.{_MATRICULA_TABLE} LIMIT 1;
  IF v_extracao_id IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: {_sql_lit(_ABERTURA_FIXTURE_DESC)}';
  END IF;
  BEGIN
    INSERT INTO {_SW_SCHEMA}.{_ABERTURA_TABLE}
      (org_id, extracao_id, campo, char_inicio, char_fim, rotulo_inicio, rotulo_fim)
    VALUES (v_org_id, v_extracao_id, 'proprietarios', 0, 10, 0, 0);
    INSERT INTO {_SW_SCHEMA}.{_ABERTURA_TABLE}
      (org_id, extracao_id, campo, char_inicio, char_fim, rotulo_inicio, rotulo_fim)
    VALUES (v_org_id, v_extracao_id, 'proprietarios', 20, 30, 20, 20);
    RAISE EXCEPTION 'NOC_PROBE:permitted: duplicate (extracao_id, campo) insert succeeded — the unique guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%idx_sw_matricula_abertura_blocos_campo%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
)


_IMOBILIARIA_CNPJ_UNIQUE_PROBE = GuardProbe(
    id="org_imobiliarias.org_cnpj_ativa.unique",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="uq_sw_org_imobiliarias_org_cnpj_ativa",
    kind="write_refusal",
    migrations=("215_org_imobiliarias.sql",),
    rationale=(
        "Two ACTIVE signing companies of one org with the same CNPJ (digits "
        "compared, so formatting cannot dodge it) would make the contract's "
        "company choice ambiguous; the API pre-checks, this index is the "
        "backstop under a race."
    ),
    sql=_do_block(f"""
DECLARE
  v_org_id uuid;
BEGIN
  SELECT id INTO v_org_id FROM public.organizations LIMIT 1;
  IF v_org_id IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no public.organizations row to own a probe company';
  END IF;
  BEGIN
    INSERT INTO {_SW_SCHEMA}.org_imobiliarias (org_id, razao_social, cnpj)
    VALUES (v_org_id, 'noc-probe-a', '11222333000181');
    INSERT INTO {_SW_SCHEMA}.org_imobiliarias (org_id, razao_social, cnpj)
    VALUES (v_org_id, 'noc-probe-b', '11.222.333/0001-81');
    RAISE EXCEPTION 'NOC_PROBE:permitted: duplicate active CNPJ insert succeeded — the unique guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%uq_sw_org_imobiliarias_org_cnpj_ativa%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
)


_CLIENTE_ORIGEM_EXCLUIDA_UNIQUE_PROBE = GuardProbe(
    id="cliente_origens_excluidas.origem.unique",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="uq_sw_cliente_origens_excluidas_origem",
    kind="write_refusal",
    migrations=("216_cliente_origens_excluidas.sql",),
    rationale=(
        "One tombstone per source row (origem_tabela, origem_id), globally — "
        "the same identity as cliente_touches; the service upserts, this "
        "index is the backstop under a race."
    ),
    sql=_do_block(f"""
DECLARE
  v_org_id uuid;
BEGIN
  SELECT id INTO v_org_id FROM public.organizations LIMIT 1;
  IF v_org_id IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no public.organizations row to own a probe tombstone';
  END IF;
  BEGIN
    INSERT INTO {_SW_SCHEMA}.cliente_origens_excluidas (org_id, origem_tabela, origem_id, cliente_id)
    VALUES (v_org_id, 'leads', 'noc-probe-origem', gen_random_uuid());
    INSERT INTO {_SW_SCHEMA}.cliente_origens_excluidas (org_id, origem_tabela, origem_id, cliente_id)
    VALUES (v_org_id, 'leads', 'noc-probe-origem', gen_random_uuid());
    RAISE EXCEPTION 'NOC_PROBE:permitted: duplicate (origem_tabela, origem_id) insert succeeded — the unique guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%uq_sw_cliente_origens_excluidas_origem%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
)


_VISITA_MOTIVO_CHECK_PROBE = GuardProbe(
    id="visitas.nao_realizada_motivo.allowed_values",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="visitas_nao_realizada_motivo_valido",
    kind="write_refusal",
    migrations=("219_visita_feedback.sql",),
    rationale=(
        "`nao_realizada_motivo` is a closed vocabulary — the funnel metric "
        "(GET /api/metricas/atendimentos) groups missed visits by it, so a "
        "free-text value would split one reason across spellings instead of "
        "erroring where it was written."
    ),
    sql=_insert_check_probe(
        schema=_SW_SCHEMA,
        table="visitas",
        columns_sql="org_id, roteiro_id, codigo, ordem, nao_realizada_motivo",
        values_sql="org_id, roteiro_id, codigo, 9999, 'noc-probe-not-a-motivo'",
        fixture_from=f"{_SW_SCHEMA}.visitas",
        fixture_description=(
            f"no row in {_SW_SCHEMA}.visitas to borrow an FK-valid "
            "(roteiro_id, codigo) from"
        ),
        guard_fragment='constraint "visitas_nao_realizada_motivo_valido"',
    ),
)


_JULIA_AGENTE_EXIGE_AUTORIZADOS_PROBE = GuardProbe(
    id="whatsapp_connections.agente_leads_ativo.exige_autorizados",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="whatsapp_connections_agente_exige_autorizados",
    kind="write_refusal",
    migrations=("258_lais_agente_roteamento.sql",),
    rationale=(
        "Julia (the lead agent) on a line whose `authorized_numbers` is EMPTY would hand every "
        "lead to the operator bot and its tools: an empty list means 'everyone is authorized' "
        "to the One Chat gate. The invariant `agente_leads_ativo => authorized_numbers "
        "non-empty` is enforced on every write by this CHECK (it spans both columns, so "
        "emptying the list while Julia is on is refused too). CHECK fires before the unique "
        "indexes, so a throwaway row borrowing an existing (org_id, user_id) is safe."
    ),
    sql=_insert_check_probe(
        schema=_SW_SCHEMA,
        table="whatsapp_connections",
        columns_sql=(
            "org_id, user_id, label, base_url, encrypted_api_key, webhook_token, "
            "authorized_numbers, agente_leads_ativo, agente_leads_ativado_em, agente_leads_key"
        ),
        values_sql=(
            "org_id, user_id, 'noc-probe', 'https://noc-probe.invalid', 'x', 'noc-probe-token', "
            "'[]'::jsonb, true, now(), 'lead-imob'"
        ),
        fixture_from=f"{_SW_SCHEMA}.whatsapp_connections",
        fixture_description=(
            f"no row in {_SW_SCHEMA}.whatsapp_connections to borrow an (org_id, user_id) from"
        ),
        guard_fragment='constraint "whatsapp_connections_agente_exige_autorizados"',
    ),
)


_JULIA_AGENTE_EXIGE_ATIVADO_EM_PROBE = GuardProbe(
    id="whatsapp_connections.agente_leads_ativo.exige_ativado_em",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="whatsapp_connections_agente_exige_ativado_em",
    kind="write_refusal",
    migrations=("258_lais_agente_roteamento.sql",),
    rationale=(
        "A chat reaches Julia only if it did not exist before `agente_leads_ativado_em` "
        "(contract 11.1): a connection with Julia on and no such timestamp (or no agent key) "
        "would make the eligibility rule undecidable. The routing code fails closed on it; "
        "this CHECK makes the state unrepresentable."
    ),
    sql=_insert_check_probe(
        schema=_SW_SCHEMA,
        table="whatsapp_connections",
        columns_sql=(
            "org_id, user_id, label, base_url, encrypted_api_key, webhook_token, "
            "authorized_numbers, agente_leads_ativo, agente_leads_ativado_em, agente_leads_key"
        ),
        values_sql=(
            "org_id, user_id, 'noc-probe', 'https://noc-probe.invalid', 'x', 'noc-probe-token', "
            "'[\"+5511999990000\"]'::jsonb, true, NULL, 'lead-imob'"
        ),
        fixture_from=f"{_SW_SCHEMA}.whatsapp_connections",
        fixture_description=(
            f"no row in {_SW_SCHEMA}.whatsapp_connections to borrow an (org_id, user_id) from"
        ),
        guard_fragment='constraint "whatsapp_connections_agente_exige_ativado_em"',
    ),
)


_JULIA_CONEXAO_TRANSPORTE_PROBE = GuardProbe(
    id="whatsapp_connections.transporte.valido",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="whatsapp_connections_transporte_valido",
    kind="write_refusal",
    migrations=("275_lais_cloud.sql",),
    rationale=(
        "The transport of a line is `waha` or `cloud`; it decides whether a template / mass send may leave "
        "at all (contract A6). An unknown value would be read as neither and could fall through to the "
        "wrong sender. CHECK fires before the unique indexes, so a throwaway row borrowing an existing "
        "(org_id, user_id) is safe."
    ),
    sql=_insert_check_probe(
        schema=_SW_SCHEMA,
        table="whatsapp_connections",
        columns_sql="org_id, user_id, label, base_url, encrypted_api_key, webhook_token, transporte",
        values_sql="org_id, user_id, 'noc-probe', 'https://noc-probe.invalid', 'x', 'noc-probe-token', 'bogus'",
        fixture_from=f"{_SW_SCHEMA}.whatsapp_connections",
        fixture_description=(
            f"no row in {_SW_SCHEMA}.whatsapp_connections to borrow an (org_id, user_id) from"
        ),
        guard_fragment='constraint "whatsapp_connections_transporte_valido"',
    ),
)


_ORG_MEMBERSHIP_ENDED_IFF_REMOVED_PROBE = GuardProbe(
    id="org_memberships.ended_at.iff_removed",
    product="core",
    schema="public",
    guard_name="org_memberships_ended_iff_removed",
    kind="write_refusal",
    migrations=("079_org_memberships.sql",),
    rationale=(
        "A membership is ended exactly when it is `removed`. A `removed` row with "
        "no `ended_at` (or an active one with it) would let the org picker and the "
        "RLS re-check disagree about whether someone still belongs to an org — the "
        "revocation the multi-org model relies on. CHECK fires before the "
        "(user_id, org_id) unique index, so borrowing an existing profile's pair is safe."
    ),
    sql=_insert_check_probe(
        schema="public",
        table="org_memberships",
        columns_sql="user_id, org_id, org_role, status, ended_at",
        values_sql="id, org_id, 'member', 'removed', NULL",
        fixture_from="public.noctus_users",
        fixture_description="no row in public.noctus_users to borrow a (user_id, org_id) from",
        guard_fragment='constraint "org_memberships_ended_iff_removed"',
    ),
)


_ROTEIRO_FEEDBACK_STATUS_CHECK_PROBE = GuardProbe(
    id="roteiros.feedback_status.allowed_values",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="roteiros_feedback_status_valido",
    kind="write_refusal",
    migrations=("219_visita_feedback.sql",),
    rationale=(
        "`feedback_status` is the two-state 'visita aconteceu?' flag the "
        "daily prompt and the pending list filter on by exact string; a "
        "third spelling would make a roteiro invisible to both."
    ),
    sql=_insert_check_probe(
        schema=_SW_SCHEMA,
        table="roteiros",
        columns_sql="org_id, atendimento_id, feedback_status",
        values_sql="org_id, atendimento_id, 'noc-probe-not-a-status'",
        fixture_from=f"{_SW_SCHEMA}.roteiros",
        fixture_description=(
            f"no row in {_SW_SCHEMA}.roteiros to borrow an FK-valid "
            "atendimento_id from"
        ),
        guard_fragment='constraint "roteiros_feedback_status_valido"',
    ),
)


_CS_RESEARCH_ITEM_UNIQUE_PROBE = GuardProbe(
    id="cs_research_items.marca_variable_content.unique",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="cs_research_items_dedupe_uq",
    kind="write_refusal",
    migrations=("217_cs_research.sql",),
    rationale=(
        "Minha Pesquisa dedupe: one item per (marca, variable, lower(content)) "
        "so a case-variant re-add is a no-op, never a second row; the service "
        "pre-checks and reports it as skipped, this index is the backstop "
        "under a race."
    ),
    sql=_do_block(f"""
DECLARE
  v_org_id uuid;
  v_marca_id uuid;
BEGIN
  SELECT id INTO v_org_id FROM public.organizations LIMIT 1;
  IF v_org_id IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no public.organizations row to own a probe marca';
  END IF;
  INSERT INTO {_SW_SCHEMA}.marcas (org_id, slug, name)
  VALUES (v_org_id, 'noc-probe-pesquisa', 'noc-probe-pesquisa')
  RETURNING id INTO v_marca_id;
  BEGIN
    INSERT INTO {_SW_SCHEMA}.cs_research_items (org_id, marca_id, variable_slug, content, status, origin)
    VALUES (v_org_id, v_marca_id, 'GPT', 'noc probe item', 'approved', 'manual');
    INSERT INTO {_SW_SCHEMA}.cs_research_items (org_id, marca_id, variable_slug, content, status, origin)
    VALUES (v_org_id, v_marca_id, 'GPT', 'NOC PROBE ITEM', 'pending', 'ai_classified');
    RAISE EXCEPTION 'NOC_PROBE:permitted: case-variant duplicate item insert succeeded — the unique guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%cs_research_items_dedupe_uq%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
)


_CS_WAVE2_MIGRATION = "221_cs_research_extraction.sql"


def _cs_wave2_unique_probe(*, probe_id: str, guard_name: str, setup: str, first: str, second: str, rationale: str) -> GuardProbe:
    """Duplicate-insert probe for a migration-221 unique index (rolled back)."""
    return GuardProbe(
        id=probe_id,
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name=guard_name,
        kind="write_refusal",
        migrations=("217_cs_research.sql", _CS_WAVE2_MIGRATION),
        rationale=rationale,
        sql=_do_block(f"""
DECLARE
  v_org_id uuid;
  v_marca_id uuid;
  v_job_id uuid;
  v_topic_id uuid;
BEGIN
  SELECT id INTO v_org_id FROM public.organizations LIMIT 1;
  IF v_org_id IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no public.organizations row to own a probe marca';
  END IF;
  INSERT INTO {_SW_SCHEMA}.marcas (org_id, slug, name)
  VALUES (v_org_id, 'noc-probe-pesquisa-w2', 'noc-probe-pesquisa-w2')
  RETURNING id INTO v_marca_id;
{setup}
  BEGIN
{first}
{second}
    RAISE EXCEPTION 'NOC_PROBE:permitted: duplicate insert succeeded — the unique guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{guard_name}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
    )


_CS_JOB_INS = (
    f"    INSERT INTO {_SW_SCHEMA}.cs_extraction_jobs (org_id, marca_id, created_by, tipos, status, posts) "
    "VALUES (v_org_id, v_marca_id, '00000000-0000-0000-0000-00000000f0a1', ARRAY['pesquisa'], '{st}', '[]'::jsonb);"
)
_CS_JOB_SETUP = (
    f"  INSERT INTO {_SW_SCHEMA}.cs_extraction_jobs (org_id, marca_id, created_by, tipos, status, posts) "
    "VALUES (v_org_id, v_marca_id, '00000000-0000-0000-0000-00000000f0a2', ARRAY['pesquisa'], 'completed', '[]'::jsonb) "
    "RETURNING id INTO v_job_id;"
)
_CS_TOPIC_INS = (
    f"  INSERT INTO {_SW_SCHEMA}.cs_viral_topics (org_id, marca_id, topic, status, origin) "
    "VALUES (v_org_id, v_marca_id, '{t}', 'approved', 'manual')"
)

_CS_WAVE2_PROBES: tuple[GuardProbe, ...] = (
    _cs_wave2_unique_probe(
        probe_id="cs_viral_topics.marca_topic.unique",
        guard_name="cs_viral_topics_marca_topic_uq",
        setup="",
        first=_CS_TOPIC_INS.format(t="noc probe topic") + ";",
        second=_CS_TOPIC_INS.format(t="NOC PROBE TOPIC") + ";",
        rationale="One viral topic per (marca, lower(topic)); a case-variant re-add is a no-op, never a second row.",
    ),
    _cs_wave2_unique_probe(
        probe_id="cs_extraction_jobs.one_active_per_user.unique",
        guard_name="cs_extraction_jobs_one_active_per_user_uq",
        setup="",
        first=_CS_JOB_INS.format(st="queued"),
        second=_CS_JOB_INS.format(st="running"),
        rationale=(
            "At most one queued/running extraction per user, enforced in the database so two "
            "concurrent submits cannot both pass (the service maps the refusal to 409)."
        ),
    ),
    _cs_wave2_unique_probe(
        probe_id="cs_viral_topic_sources.post.unique",
        guard_name="cs_viral_topic_sources_post_uq",
        setup=_CS_TOPIC_INS.format(t="noc probe src topic") + "\n  RETURNING id INTO v_topic_id;",
        first=(
            f"    INSERT INTO {_SW_SCHEMA}.cs_viral_topic_sources (org_id, topic_id, source_kind, source_id) "
            "VALUES (v_org_id, v_topic_id, 'mc_post', 'noc-probe-post');"
        ),
        second=(
            f"    INSERT INTO {_SW_SCHEMA}.cs_viral_topic_sources (org_id, topic_id, source_kind, source_id) "
            "VALUES (v_org_id, v_topic_id, 'mc_post', 'noc-probe-post');"
        ),
        rationale="A post backs a topic at most once (NULL account_id coalesced), so re-extraction cannot duplicate sources.",
    ),
    _cs_wave2_unique_probe(
        probe_id="cs_extraction_post_runs.post.unique",
        guard_name="cs_extraction_post_runs_post_uq",
        setup=_CS_JOB_SETUP,
        first=(
            f"    INSERT INTO {_SW_SCHEMA}.cs_extraction_post_runs (org_id, marca_id, extracao_id, tipo, source_kind, source_id, status) "
            "VALUES (v_org_id, v_marca_id, v_job_id, 'pesquisa', 'mc_post', 'noc-probe-post', 'done');"
        ),
        second=(
            f"    INSERT INTO {_SW_SCHEMA}.cs_extraction_post_runs (org_id, marca_id, extracao_id, tipo, source_kind, source_id, status) "
            "VALUES (v_org_id, v_marca_id, v_job_id, 'pesquisa', 'mc_post', 'noc-probe-post', 'done');"
        ),
        rationale="One run row per (job, tipo, post): a retried handler resumes instead of paying the LLM twice.",
    ),
)


# ---------------------------------------------------------------------------
# Registry — social_wiring CoreStudio Geracao guards (migration 229).
# ---------------------------------------------------------------------------

_CS_GERACAO_MIGRATION = "229_cs_geracao.sql"
_CS_G_PERFIL_INS = (
    f"INSERT INTO {_SW_SCHEMA}.cs_perfis_monitorados (org_id, handle) "
    "VALUES (v_org_id, '{h}')"
)
_CS_G_VIRAL_INS = (
    f"INSERT INTO {_SW_SCHEMA}.cs_virais (org_id, perfil_id, ig_media_id) "
    "VALUES (v_org_id, v_perfil_id, '{m}')"
)
_CS_G_REF_INS = (
    f"INSERT INTO {_SW_SCHEMA}.cs_biblioteca_referencias (org_id, marca_id, modo, perfil_id, viral_id) "
    "VALUES (v_org_id, v_marca_id, {vals})"
)
_CS_G_LOTE_INS = (
    f"INSERT INTO {_SW_SCHEMA}.cs_headline_lotes (org_id, marca_id, created_by, origem, status) "
    "VALUES (v_org_id, v_marca_id, '00000000-0000-0000-0000-00000000f0b1', '{o}', '{st}')"
)


def _twice(stmt: str) -> str:
    """The same write twice, indented for the probe's inner block."""
    return f"    {stmt};\n    {stmt};"


def _cs_geracao_probe(
    *, probe_id: str, guard_name: str, setup: str, statements: str, permitted_msg: str, rationale: str,
    migration: str = _CS_GERACAO_MIGRATION,
) -> GuardProbe:
    """Refusal probe for a migration-229 guard (rolled back). `statements`
    run inside the inner block; the LAST one must be the refused write."""
    return GuardProbe(
        id=probe_id,
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name=guard_name,
        kind="write_refusal",
        migrations=(migration,),
        rationale=rationale,
        sql=_do_block(f"""
DECLARE
  v_org_id uuid;
  v_marca_id uuid;
  v_perfil_id uuid;
  v_viral_id uuid;
BEGIN
  SELECT id INTO v_org_id FROM public.organizations LIMIT 1;
  IF v_org_id IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no public.organizations row to own a probe marca';
  END IF;
  INSERT INTO {_SW_SCHEMA}.marcas (org_id, slug, name)
  VALUES (v_org_id, 'noc-probe-geracao', 'noc-probe-geracao')
  RETURNING id INTO v_marca_id;
{setup}
  BEGIN
{statements}
    RAISE EXCEPTION 'NOC_PROBE:permitted: {permitted_msg} - the guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{guard_name}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
    )


_CS_G_SETUP_PERFIL = "  " + _CS_G_PERFIL_INS.format(h="noc.probe.geracao") + "\n  RETURNING id INTO v_perfil_id;"
_CS_G_SETUP_VIRAL = (
    _CS_G_SETUP_PERFIL + "\n  " + _CS_G_VIRAL_INS.format(m="noc-probe-media") + "\n  RETURNING id INTO v_viral_id;"
)

_CS_BIBLIOTECA_OPTOUTS_MIGRATION = "233_cs_biblioteca_optouts.sql"

_CS_GERACAO_PROBES: tuple[GuardProbe, ...] = (
    _cs_geracao_probe(
        probe_id="cs_biblioteca_optouts.handle.unique",
        guard_name="cs_biblioteca_optouts_handle_uq",
        setup="",
        statements=_twice(
            f"INSERT INTO {_SW_SCHEMA}.cs_biblioteca_optouts (handle, origem) VALUES ('noc.probe.optout', 'admin')"
        ),
        permitted_msg="duplicate platform-wide opt-out handle insert succeeded",
        rationale="One opt-out per handle platform-wide: a creator's opt-out binds every org and a re-add is a no-op.",
        migration=_CS_BIBLIOTECA_OPTOUTS_MIGRATION,
    ),
    _cs_geracao_probe(
        probe_id="cs_perfis_monitorados.org_rede_handle.unique",
        guard_name="cs_perfis_monitorados_org_handle_uq",
        setup="",
        statements=_twice(_CS_G_PERFIL_INS.format(h="noc.probe.dup")),
        permitted_msg="duplicate (org, rede, handle) profile insert succeeded",
        rationale="One monitored profile per (org, rede, handle): a re-add is a no-op, never a second sync target.",
    ),
    _cs_geracao_probe(
        probe_id="cs_virais.perfil_media.unique",
        guard_name="cs_virais_perfil_media_uq",
        setup=_CS_G_SETUP_PERFIL,
        statements=_twice(_CS_G_VIRAL_INS.format(m="noc-probe-dup")),
        permitted_msg="duplicate (perfil, ig_media_id) viral insert succeeded",
        rationale="One viral row per (perfil, ig_media_id): a re-sync upserts instead of duplicating a post.",
    ),
    _cs_geracao_probe(
        probe_id="cs_biblioteca_referencias.modo_alvo.check",
        guard_name="cs_biblioteca_referencias_modo_alvo",
        setup=_CS_G_SETUP_PERFIL,
        statements="    " + _CS_G_REF_INS.format(vals="'perfil', NULL, NULL") + ";",
        permitted_msg="modo=perfil reference with no perfil_id succeeded",
        rationale="modo=perfil XOR modo=video: a reference must name exactly the target its mode implies.",
    ),
    _cs_geracao_probe(
        probe_id="cs_biblioteca_referencias.marca_perfil.unique",
        guard_name="cs_biblioteca_referencias_perfil_uq",
        setup=_CS_G_SETUP_PERFIL,
        statements=_twice(_CS_G_REF_INS.format(vals="'perfil', v_perfil_id, NULL")),
        permitted_msg="duplicate (marca, perfil) reference insert succeeded",
        rationale="One perfil reference per (marca, perfil) in the per-marca allow-list.",
    ),
    _cs_geracao_probe(
        probe_id="cs_biblioteca_referencias.marca_video.unique",
        guard_name="cs_biblioteca_referencias_video_uq",
        setup=_CS_G_SETUP_VIRAL,
        statements=_twice(_CS_G_REF_INS.format(vals="'video', NULL, v_viral_id")),
        permitted_msg="duplicate (marca, viral) reference insert succeeded",
        rationale="One video reference per (marca, viral) in the per-marca allow-list.",
    ),
    _cs_geracao_probe(
        probe_id="cs_headline_lotes.one_active_per_user.unique",
        guard_name="cs_headline_lotes_um_ativo_por_usuario_uq",
        setup="",
        statements=(
            "    " + _CS_G_LOTE_INS.format(o="form_me", st="criando") + ";\n"
            "    " + _CS_G_LOTE_INS.format(o="form_me", st="processando") + ";"
        ),
        permitted_msg="second active manual headline batch for one user succeeded",
        rationale=(
            "At most one criando/processando manual headline batch per user, enforced in the database "
            "so two concurrent submits cannot both pass (sugestao_auto batches are exempt)."
        ),
    ),
)


# ---------------------------------------------------------------------------
# Registry — social_wiring.imovel_dados_endereco_registro_confirmado CHECK
# (migration 139).
# ---------------------------------------------------------------------------
#
# Borrows `(org_id, codigo)` from an `imoveis` (Vista mirror) row that has NO
# `imovel_dados` row yet, rather than from `imovel_dados` itself — the mirror
# is populated by the sync regardless of whether anyone has authored cartório
# data, so it is far more likely to have a usable fixture; borrowing from
# `imovel_dados` directly would risk a PRIMARY KEY collision with an existing
# row (a duplicate-key error, not the CHECK under test) instead of a clean
# `no_fixture` when every imóvel already has one.

_IMOVEL_DADOS_TABLE = "imovel_dados"
_ENDERECO_REGISTRO_FIXTURE_FROM = (
    f"(SELECT i.org_id AS org_id, i.codigo AS codigo FROM {_SW_SCHEMA}.imoveis i "
    f"WHERE NOT EXISTS (SELECT 1 FROM {_SW_SCHEMA}.{_IMOVEL_DADOS_TABLE} d "
    f"WHERE d.org_id = i.org_id AND d.codigo = i.codigo) LIMIT 1) AS fx"
)
_ENDERECO_REGISTRO_FIXTURE_DESC = (
    f"no {_SW_SCHEMA}.imoveis row without an existing {_SW_SCHEMA}."
    f"{_IMOVEL_DADOS_TABLE} row to probe a fresh insert against"
)

_ENDERECO_REGISTRO_PROBE = GuardProbe(
    id="imovel_dados.endereco_registro.confirmed_pair",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="imovel_dados_endereco_registro_confirmado",
    kind="write_refusal",
    migrations=("139_imovel_endereco_registro.sql",),
    rationale=(
        "endereco_registro_texto (the posse clause's operator-confirmed "
        "address override — endereco-portaria-vs-imovel) and its "
        "confirmation timestamp must be set/cleared together: an address "
        "with no confirmation stamp is indistinguishable from an "
        "unreviewed suggestion, and printing an unreviewed address into a "
        "signed deed is exactly the risk this feature exists to close."
    ),
    sql=_insert_check_probe(
        schema=_SW_SCHEMA,
        table=_IMOVEL_DADOS_TABLE,
        columns_sql="org_id, codigo, endereco_registro_texto, endereco_registro_confirmado_em",
        values_sql="fx.org_id, fx.codigo, 'Rua Teste, nº 1', NULL",
        fixture_from=_ENDERECO_REGISTRO_FIXTURE_FROM,
        fixture_description=_ENDERECO_REGISTRO_FIXTURE_DESC,
        guard_fragment='constraint "imovel_dados_endereco_registro_confirmado"',
    ),
)


# ---------------------------------------------------------------------------
# Registry — social_wiring.imovel_dados_ultima_transferencia_manual_confirmado
# CHECK (migration 152).
# ---------------------------------------------------------------------------
#
# Same fixture shape as `_ENDERECO_REGISTRO_PROBE` above (same table,
# borrowing an `imoveis` código with no `imovel_dados` row yet) — the probe
# below trips the SAME family of bug the endereço one guards against: a
# manual override recorded WITHOUT its confirmation stamp is indistinguishable
# from an unreviewed suggestion, and `titulo_service.antigos_proprietarios`
# treats an unconfirmed override as "no override at all" (`_manual_ultima_
# transferencia` gates on `confirmado_em`) — so this is the guard that keeps
# a half-written override from silently vanishing rather than surfacing.

_ULTIMA_TRANSFERENCIA_MANUAL_PROBE = GuardProbe(
    id="imovel_dados.ultima_transferencia_manual.confirmed_pair",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="imovel_dados_ultima_transferencia_manual_confirmado",
    kind="write_refusal",
    # 306 widened it (a non-empty transmitentes list also counts as an answer).
    migrations=("152_ultima_transferencia_manual.sql", "306_imovel_campos_manuais.sql"),
    rationale=(
        "ultima_transferencia_manual_data (the [Q9] previous-owner rule's "
        "manual fallback, migration 152) and its confirmation timestamp "
        "must be set/cleared together — an unconfirmed value reads as no "
        "override at all (`titulo_service._manual_ultima_transferencia`), "
        "so a half-written row would silently vanish rather than answering "
        "the gate."
    ),
    sql=_insert_check_probe(
        schema=_SW_SCHEMA,
        table=_IMOVEL_DADOS_TABLE,
        columns_sql="org_id, codigo, ultima_transferencia_manual_data, ultima_transferencia_manual_confirmado_em",
        values_sql="fx.org_id, fx.codigo, DATE '2020-01-10', NULL",
        fixture_from=_ENDERECO_REGISTRO_FIXTURE_FROM,
        fixture_description=_ENDERECO_REGISTRO_FIXTURE_DESC,
        guard_fragment='constraint "imovel_dados_ultima_transferencia_manual_confirmado"',
    ),
)

_ULTIMA_TRANSFERENCIA_MANUAL_NATUREZA_PROBE = GuardProbe(
    id="imovel_dados.ultima_transferencia_manual.natureza_vocabulary",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="imovel_dados_ultima_transferencia_manual_natureza_check",
    kind="write_refusal",
    migrations=("152_ultima_transferencia_manual.sql",),
    rationale=(
        "ultima_transferencia_manual_natureza is restricted to the 4 natures "
        "`titulo_service.NATUREZAS_ULTIMA_TRANSFERENCIA` recognises for this "
        "rule (compra_e_venda/permuta/dacao/arrematacao) — NOT the seed's "
        "full 14-value NaturezaAto vocabulary. A value outside that (e.g. "
        "`hipoteca`, or `doacao` which the office deliberately excludes here) "
        "must never be silently accepted into the manual override."
    ),
    sql=_insert_check_probe(
        schema=_SW_SCHEMA,
        table=_IMOVEL_DADOS_TABLE,
        columns_sql=(
            "org_id, codigo, ultima_transferencia_manual_data, "
            "ultima_transferencia_manual_natureza, ultima_transferencia_manual_confirmado_em"
        ),
        values_sql="fx.org_id, fx.codigo, DATE '2020-01-10', 'hipoteca', NOW()",
        fixture_from=_ENDERECO_REGISTRO_FIXTURE_FROM,
        fixture_description=_ENDERECO_REGISTRO_FIXTURE_DESC,
        guard_fragment='constraint "imovel_dados_ultima_transferencia_manual_natureza_check"',
    ),
)

_ULTIMA_TRANSFERENCIA_MANUAL_NATUREZA_REQUER_DATA_PROBE = GuardProbe(
    id="imovel_dados.ultima_transferencia_manual.natureza_requer_data",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="imovel_dados_ultima_transferencia_manual_natureza_requer_data",
    kind="write_refusal",
    migrations=("152_ultima_transferencia_manual.sql",),
    rationale=(
        "A nature only means something alongside a date — it must never "
        "survive on its own (e.g. after `_data` is cleared but `_natureza` "
        "is left behind), which would print a nature for a transfer the "
        "gate no longer has a date for."
    ),
    sql=_insert_check_probe(
        schema=_SW_SCHEMA,
        table=_IMOVEL_DADOS_TABLE,
        columns_sql="org_id, codigo, ultima_transferencia_manual_natureza",
        values_sql="fx.org_id, fx.codigo, 'permuta'",
        fixture_from=_ENDERECO_REGISTRO_FIXTURE_FROM,
        fixture_description=_ENDERECO_REGISTRO_FIXTURE_DESC,
        guard_fragment='constraint "imovel_dados_ultima_transferencia_manual_natureza_requer_data"',
    ),
)

_ULTIMA_TRANSFERENCIA_MANUAL_EXCLUSIVA_PROBE = GuardProbe(
    id="imovel_dados.ultima_transferencia_manual.exclusiva",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="imovel_dados_ultima_transferencia_manual_exclusiva",
    kind="write_refusal",
    migrations=("152_ultima_transferencia_manual.sql",),
    rationale=(
        "A date AND 'não consta transferência registrada' set together is a "
        "contradiction, not a richer answer — `titulo_service.confirmar_"
        "ultima_transferencia_manual` refuses it too; this is the backstop "
        "against a caller that bypasses the service (or a future bug in it)."
    ),
    sql=_insert_check_probe(
        schema=_SW_SCHEMA,
        table=_IMOVEL_DADOS_TABLE,
        columns_sql=(
            "org_id, codigo, ultima_transferencia_manual_data, "
            "ultima_transferencia_manual_sem_registro, ultima_transferencia_manual_confirmado_em"
        ),
        values_sql="fx.org_id, fx.codigo, DATE '2020-01-10', TRUE, NOW()",
        fixture_from=_ENDERECO_REGISTRO_FIXTURE_FROM,
        fixture_description=_ENDERECO_REGISTRO_FIXTURE_DESC,
        guard_fragment='constraint "imovel_dados_ultima_transferencia_manual_exclusiva"',
    ),
)


# ---------------------------------------------------------------------------
# Registry — migration 306 (imóvel fields typed by hand, never upload-only).
# ---------------------------------------------------------------------------
#
# The `imovel_dados` probes borrow a REGISTRY código with no `imovel_dados`
# row (imovel_dados' FK is `imovel_registry`, migration 076) — a fresh insert,
# so no PRIMARY KEY collision can stand in for the CHECK under test. The
# `imovel_certidoes_manuais` probes borrow any registry código: every probe
# value violates a CHECK, and Postgres evaluates CHECKs before the UNIQUE
# index, so an existing typed row can never answer in the CHECK's place.

_CERTIDOES_MANUAIS_TABLE = "imovel_certidoes_manuais"
_REGISTRY_SEM_DADOS_FROM = (
    f"(SELECT r.org_id AS org_id, r.codigo_canonical AS codigo FROM {_SW_SCHEMA}.imovel_registry r "
    f"WHERE NOT EXISTS (SELECT 1 FROM {_SW_SCHEMA}.{_IMOVEL_DADOS_TABLE} d "
    f"WHERE d.org_id = r.org_id AND d.codigo = r.codigo_canonical) LIMIT 1) AS fx"
)
_REGISTRY_SEM_DADOS_DESC = (
    f"no {_SW_SCHEMA}.imovel_registry row without an existing {_SW_SCHEMA}."
    f"{_IMOVEL_DADOS_TABLE} row to probe a fresh insert against"
)
_REGISTRY_FROM = (
    f"(SELECT r.org_id AS org_id, r.codigo_canonical AS codigo "
    f"FROM {_SW_SCHEMA}.imovel_registry r LIMIT 1) AS fx"
)
_REGISTRY_DESC = f"no {_SW_SCHEMA}.imovel_registry row to borrow (org_id, codigo) from"


def _certidao_manual_probe(guard: str, values_sql: str, rationale: str, sufixo: str) -> GuardProbe:
    return GuardProbe(
        id=f"imovel_certidoes_manuais.{sufixo}",
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name=guard,
        kind="write_refusal",
        migrations=("306_imovel_campos_manuais.sql",),
        rationale=rationale,
        sql=_insert_check_probe(
            schema=_SW_SCHEMA,
            table=_CERTIDOES_MANUAIS_TABLE,
            columns_sql="org_id, codigo, tipo, numero, resultado",
            values_sql=values_sql,
            fixture_from=_REGISTRY_FROM,
            fixture_description=_REGISTRY_DESC,
            guard_fragment=f'constraint "{guard}"',
        ),
    )


_SW_CAMPOS_MANUAIS_PROBES: tuple[GuardProbe, ...] = (
    GuardProbe(
        id="imovel_dados.descricao_imovel.confirmed_pair",
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name="imovel_dados_descricao_imovel_confirmado",
        kind="write_refusal",
        migrations=("306_imovel_campos_manuais.sql",),
        rationale=(
            "The typed IMÓVEL: description wins over the matrícula's own block "
            "in the contract; a text with no confirmation stamp would print an "
            "unattributed description into a signed deed."
        ),
        sql=_insert_check_probe(
            schema=_SW_SCHEMA,
            table=_IMOVEL_DADOS_TABLE,
            columns_sql="org_id, codigo, descricao_imovel_texto, descricao_imovel_confirmado_em",
            values_sql="fx.org_id, fx.codigo, 'Apartamento teste', NULL",
            fixture_from=_REGISTRY_SEM_DADOS_FROM,
            fixture_description=_REGISTRY_SEM_DADOS_DESC,
            guard_fragment='constraint "imovel_dados_descricao_imovel_confirmado"',
        ),
    ),
    GuardProbe(
        id="imovel_dados.ultima_transferencia_manual.transmitentes_sem_registro",
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name="imovel_dados_ult_transf_transmitentes_sem_registro",
        kind="write_refusal",
        migrations=("306_imovel_campos_manuais.sql",),
        rationale=(
            "Names of who sold contradict 'não consta transferência registrada'; "
            "titulo_service refuses the pair, this is the backstop."
        ),
        sql=_insert_check_probe(
            schema=_SW_SCHEMA,
            table=_IMOVEL_DADOS_TABLE,
            columns_sql=(
                "org_id, codigo, ultima_transferencia_manual_sem_registro, "
                "ultima_transferencia_manual_transmitentes, ultima_transferencia_manual_confirmado_em"
            ),
            values_sql="fx.org_id, fx.codigo, TRUE, ARRAY['Vendedor Teste']::text[], NOW()",
            fixture_from=_REGISTRY_SEM_DADOS_FROM,
            fixture_description=_REGISTRY_SEM_DADOS_DESC,
            guard_fragment='constraint "imovel_dados_ult_transf_transmitentes_sem_registro"',
        ),
    ),
    _certidao_manual_probe(
        "imovel_certidoes_manuais_tipo_valido",
        "fx.org_id, fx.codigo, 'guia_iptu', NULL, NULL",
        "Only the contract's imóvel certidão tipos (cnd_iptu, cnd_condominio, "
        "matricula) may be typed; any other tipo is a row no reader consumes.",
        "tipo_valido",
    ),
    _certidao_manual_probe(
        "imovel_certidoes_manuais_resultado_valido",
        "fx.org_id, fx.codigo, 'cnd_iptu', NULL, 'nao_emitida'",
        "A certidão in hand was emitted — resultado is restricted to the "
        "imóvel CND vocabulary (documentos_service.RESULTADO_VALUES).",
        "resultado_valido",
    ),
    _certidao_manual_probe(
        "imovel_certidoes_manuais_campos_por_tipo",
        "fx.org_id, fx.codigo, 'cnd_condominio', 'X-1', NULL",
        "Each tipo carries only its own fields (CAMPOS_ESTRUTURA_POR_TIPO): a "
        "número on a condomínio declaration is a field the contract never reads.",
        "campos_por_tipo",
    ),
)


# ---------------------------------------------------------------------------
# Registry — social_wiring.imovel_dados_empreendimento_manual_confirmado
# CHECK (migration 158).
# ---------------------------------------------------------------------------
#
# Same fixture shape as `_ENDERECO_REGISTRO_PROBE`/`_ULTIMA_TRANSFERENCIA_
# MANUAL_PROBE` above (same table, borrowing an `imoveis` código with no
# `imovel_dados` row yet) — the same family of bug: an authored
# empreendimento name recorded WITHOUT its confirmation stamp is
# indistinguishable from a half-written row, and `carregador._empreendimento`
# would happily read it anyway (it does not check the stamp), so this is the
# guard that keeps a half-written override from silently landing.

_EMPREENDIMENTO_MANUAL_PROBE = GuardProbe(
    id="imovel_dados.empreendimento_manual.confirmed_pair",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="imovel_dados_empreendimento_manual_confirmado",
    kind="write_refusal",
    migrations=("158_imovel_empreendimento_manual.sql",),
    rationale=(
        "empreendimento_manual (the authored development/condomínio name "
        "for a manually registered imóvel with no Vista mirror row, "
        "migration 158) and its confirmation timestamp must be set/cleared "
        "together — the same half-written-row risk 139's endereco_registro "
        "and 152's ultima_transferencia_manual already guard against."
    ),
    sql=_insert_check_probe(
        schema=_SW_SCHEMA,
        table=_IMOVEL_DADOS_TABLE,
        columns_sql="org_id, codigo, empreendimento_manual, empreendimento_manual_confirmado_em",
        values_sql="fx.org_id, fx.codigo, 'Residencial Teste', NULL",
        fixture_from=_ENDERECO_REGISTRO_FIXTURE_FROM,
        fixture_description=_ENDERECO_REGISTRO_FIXTURE_DESC,
        guard_fragment='constraint "imovel_dados_empreendimento_manual_confirmado"',
    ),
)


# ---------------------------------------------------------------------------
# Registry — social_wiring.imovel_dados condomínio FK / casa de rua
# (migration 300): CHECK `imovel_dados_condominio_ou_casa_de_rua` + trigger
# `imovel_dados_condominio_mesma_org`.
# ---------------------------------------------------------------------------
#
# Same fresh-insert fixture as the 139/152/158 probes above, plus a
# SELF-PROVISIONED condomínio inside the same rolled-back transaction
# (`condominios` is empty in prod today — an ambient-data fixture would read
# `no_fixture` forever). The same-org trigger is BEFORE INSERT, so it fires
# BEFORE the CHECK: the CHECK probe provisions a condomínio of the fixture's
# OWN org (trigger passes, CHECK trips); the trigger probe provisions one of a
# random OTHER org.

_IMOVEL_CONDOMINIO_MESMA_ORG_FRAGMENT = "deve ser um condomínio da mesma organização"


def _imovel_condominio_probe(
    *, cond_org_sql: str, casa_de_rua_sql: str, guard_fragment: str, permitted_msg: str
) -> str:
    """INSERT a fresh `imovel_dados` row attached to a condomínio this probe
    provisions itself (org `cond_org_sql`), with `casa_de_rua_sql`."""
    fx = _ENDERECO_REGISTRO_FIXTURE_FROM
    return _do_block(f"""
DECLARE
  v_cond uuid := gen_random_uuid();
  v_org uuid;
  v_codigo text;
BEGIN
  SELECT fx.org_id, fx.codigo INTO v_org, v_codigo FROM {fx} LIMIT 1;
  IF v_org IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: {_sql_lit(_ENDERECO_REGISTRO_FIXTURE_DESC)}';
  END IF;
  INSERT INTO {_SW_SCHEMA}.condominios (id, org_id, nome, nome_normalizado)
  VALUES (v_cond, {cond_org_sql}, 'NOC PROBE', 'NOC PROBE ' || v_cond::text);
  BEGIN
    INSERT INTO {_SW_SCHEMA}.{_IMOVEL_DADOS_TABLE} (org_id, codigo, condominio_id, casa_de_rua)
    VALUES (v_org, v_codigo, v_cond, {casa_de_rua_sql});
    RAISE EXCEPTION 'NOC_PROBE:permitted: {_sql_lit(permitted_msg)}';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{_sql_lit(guard_fragment)}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
""")


_IMOVEL_CONDOMINIO_OU_CASA_DE_RUA_PROBE = GuardProbe(
    id="imovel_dados.condominio_ou_casa_de_rua",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="imovel_dados_condominio_ou_casa_de_rua",
    kind="write_refusal",
    migrations=("300_imovel_condominio_fk.sql",),
    rationale=(
        "An imóvel attached to a condomínio AND marked 'casa de rua' is a "
        "contradiction the contract would print either way — the API refuses "
        "it (422); this is the backstop against a writer that bypasses it."
    ),
    sql=_imovel_condominio_probe(
        cond_org_sql="v_org",
        casa_de_rua_sql="TRUE",
        guard_fragment='constraint "imovel_dados_condominio_ou_casa_de_rua"',
        permitted_msg="imovel_dados with condominio_id AND casa_de_rua was accepted",
    ),
)

_IMOVEL_CONDOMINIO_MESMA_ORG_PROBE = GuardProbe(
    id="imovel_dados.condominio_id.mesma_org",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="imovel_dados_condominio_mesma_org",
    kind="write_refusal",
    migrations=("300_imovel_condominio_fk.sql",),
    rationale=(
        "The FK alone accepts ANY org's condomínio; attaching an imóvel to "
        "another tenant's condomínio would leak that row into this org's "
        "contracts and /condominios stats. The trigger refuses it."
    ),
    sql=_imovel_condominio_probe(
        cond_org_sql="gen_random_uuid()",
        casa_de_rua_sql="FALSE",
        guard_fragment=_IMOVEL_CONDOMINIO_MESMA_ORG_FRAGMENT,
        permitted_msg="imovel_dados attached to another org's condominio was accepted",
    ),
)


# ---------------------------------------------------------------------------
# Registry — zero public storage.buckets (platform-wide; the LGPD guard).
# ---------------------------------------------------------------------------
#
# NOT a write_refusal probe: no DB-level trigger/constraint currently
# refuses `INSERT/UPDATE storage.buckets SET public = true` — the fix for
# the 2026-09-17 incident was flipping the two live rows back to
# `public = false` plus the LIVE-read gate `check_storage_no_public_
# buckets` (already wired into `predeploy_check`); there is no trigger to
# prove a refusal AGAINST. Honestly modelled as a `state_assertion`
# instead of fabricating a write-refusal probe against a guard that does
# not exist — see this module's return-note for the follow-up this opens.
#
# Platform-wide by design (matches `check_storage_no_public_buckets`'s own
# posture) — a bucket belongs to the whole Supabase project, not to one
# product's schema, so this ONE probe already covers erp-imobiliario's
# equivalent (migration 048) with no per-product duplication needed.

_STORAGE_BUCKETS_PROBE = GuardProbe(
    id="storage.buckets.zero_public",
    product="<platform>",
    schema="storage",
    guard_name="storage.buckets.public",
    kind="state_assertion",
    migrations=(),
    rationale=(
        "A public Supabase Storage bucket serves objects via "
        "`/object/public/{bucket}/{path}` — a route that bypasses "
        "storage.objects RLS entirely. THE incident (2026-09-17): "
        "erp-certidoes (102 CPF-bearing objects) and erp-geral were "
        "`public = true` live while 17 RLS policies on storage.objects "
        "gave zero protection. The rule is absolute, no exception "
        "(owner directive): platform-wide, forever, zero public buckets."
    ),
    sql=_state_assertion_probe(
        select_count_sql="SELECT count(*) INTO v_count FROM storage.buckets WHERE public = true;",
        clean_message="0 public buckets in storage.buckets",
        violation_message_prefix="public bucket(s) found LIVE in storage.buckets —",
    ),
)


# ---------------------------------------------------------------------------
# Registry — zero caller-executable SECURITY DEFINER functions outside the
# RLS-helper set, in every ACTIVE product schema (2026-10-06 hotfix; migrations
# core 061, social-wiring 209, community 016, academia 014, store 010,
# agents 019, igig 037). PostgREST exposes each function as /rpc/<name>; a
# SECURITY DEFINER function reachable by anon/authenticated is a privilege
# escalation (public.enforce_session_cap deleted ANY user's auth.sessions).
# Allowed to stay executable: a function an RLS policy / column default
# depends on (derived LIVE from pg_depend, same rule the migrations apply).
# Inactive schemas (erp, therapy, orbity, pilates, ...) ARE checked since 2026-10-06 (owner-authorized lockdown).
# ---------------------------------------------------------------------------

_SECDEF_ACTIVE_SCHEMAS = (
    "public", "core", "social_wiring", "community",
    "academia_de_reciclagem", "store", "agents", "igig",
    # Inactive-product schemas locked down 2026-10-06 (owner-authorized); kept enforced.
    "erp", "imobi_scheduling", "media_scheduling", "therapy", "orbity", "pilates",
)

_SECDEF_EXECUTE_PROBE = GuardProbe(
    id="secdef.execute.no_caller_executable_outside_rls_helpers",
    product="<platform>",
    schema="public",
    guard_name="secdef_execute_lockdown",
    kind="state_assertion",
    migrations=(),
    rationale=(
        "A SECURITY DEFINER function executable by anon/authenticated is "
        "directly callable as a PostgREST RPC, bypassing RLS and every app "
        "check. Only functions an RLS policy or column default depends on "
        "may stay caller-executable (they run inside the caller's query)."
    ),
    sql=_state_assertion_probe(
        select_count_sql=(
            "SELECT count(*) INTO v_count FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = ANY (ARRAY["
            + ",".join("'" + sc + "'" for sc in _SECDEF_ACTIVE_SCHEMAS)
            + "]) AND p.prosecdef AND p.prokind = 'f' "
            "AND (has_function_privilege('anon', p.oid, 'EXECUTE') "
            "OR has_function_privilege('authenticated', p.oid, 'EXECUTE')) "
            "AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = p.oid AND d.deptype = 'e') "
            "AND NOT EXISTS (SELECT 1 FROM pg_depend d "
            "WHERE d.refclassid = 'pg_proc'::regclass AND d.refobjid = p.oid "
            "AND d.classid IN ('pg_policy'::regclass, 'pg_attrdef'::regclass));"
        ),
        clean_message="no non-RLS-helper SECURITY DEFINER function is anon/authenticated-executable in active schemas",
        violation_message_prefix="SECURITY DEFINER function(s) callable by anon/authenticated outside the RLS-helper set:",
    ),
)


# ---------------------------------------------------------------------------
# Registry — academia_de_reciclagem.interessados unique lower(email)
# (migration 011).
# ---------------------------------------------------------------------------
#
# Self-provisioning: the table has no FK, so the probe inserts its own two
# rows (same address, different case) — no fixture row needed. Both inserts
# sit inside the sub-block that always ends in RAISE, so nothing persists.

_ACADEMIA_SCHEMA = "academia_de_reciclagem"

_INTERESSADOS_EMAIL_UNIQUE_PROBE = GuardProbe(
    id="interessados.email.unique_case_insensitive",
    product="academia-de-reciclagem",
    schema=_ACADEMIA_SCHEMA,
    guard_name="interessados_email_lower_key",
    kind="write_refusal",
    migrations=("011_interessados.sql",),
    rationale=(
        "One signup per address regardless of case — the public route "
        "upserts on lower(email) and promises the visitor an identical "
        "response either way; a second row for 'Maria@x' vs 'maria@x' "
        "would double every future communication and make the LGPD "
        "erasure (DELETE by id) leave a copy behind."
    ),
    sql=_do_block(f"""
BEGIN
  IF to_regclass('{_ACADEMIA_SCHEMA}.interessados') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: {_ACADEMIA_SCHEMA}.interessados does not exist (migration 011 not applied)';
  END IF;
  BEGIN
    INSERT INTO {_ACADEMIA_SCHEMA}.interessados (nome, whatsapp, email, consentimento_versao)
    VALUES ('NOC probe', '+5511900000000', 'noc-probe@exemplo.invalid', 'probe');
    INSERT INTO {_ACADEMIA_SCHEMA}.interessados (nome, whatsapp, email, consentimento_versao)
    VALUES ('NOC probe', '+5511900000000', 'NOC-Probe@Exemplo.invalid', 'probe');
    RAISE EXCEPTION 'NOC_PROBE:permitted: case-variant duplicate email insert succeeded — the unique guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%interessados_email_lower_key%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
)


# ---------------------------------------------------------------------------
# Registry — public.licenses: the platform org holds every product license
# (core migration 068; owner decision 2026-10-07). Three probes: the guard
# refuses revoking a platform license, live state has no unlicensed product,
# and a product inserted now is licensed to the platform org by the trigger.
# All three read the REAL platform org (`organizations.is_platform`, slug
# 'noctusai' marked by 068); for the state assertions its absence IS the
# violation, for the refusal probe it is `no_fixture` (still a failure).
# ---------------------------------------------------------------------------

_PLATFORM_ORG_MIGRATIONS = ("068_platform_org_all_licenses.sql",)

def _platform_org_fixture(outcome: str) -> str:
    """Resolve the platform org into `v_platform`. `outcome` is what a missing
    prerequisite means: `no_fixture` for the write_refusal probe (nothing to
    attempt the refusal against), `violation` for the state assertions (after
    068, "no platform org" IS the broken state)."""
    return f"""
  IF to_regprocedure('public.grant_platform_org_licenses()') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:{outcome}: public.grant_platform_org_licenses() missing — core 068 not applied';
  END IF;
  SELECT id INTO v_platform FROM public.organizations WHERE is_platform LIMIT 1;
  IF v_platform IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:{outcome}: no organizations row has is_platform = true — the platform org holds no guaranteed licenses';
  END IF;
"""


_PLATFORM_ORG_REVOKE_REFUSED_PROBE = GuardProbe(
    id="licenses.platform_org.revoke_refused",
    product="core",
    schema="public",
    guard_name="licenses_platform_org_guard",
    kind="write_refusal",
    migrations=_PLATFORM_ORG_MIGRATIONS,
    rationale=(
        "The platform org's licenses are what lets NoctusAI reach every "
        "product without any role/org-id bypass in the license gate; a "
        "revoked/expired platform license silently locks the operator out of "
        "a product (403 org_sem_licenca)."
    ),
    sql=_do_block("""
DECLARE
  v_platform uuid;
  v_lic uuid;
BEGIN
""" + _platform_org_fixture("no_fixture") + """
  SELECT id INTO v_lic FROM public.licenses
   WHERE org_id = v_platform AND status = 'active' LIMIT 1;
  IF v_lic IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: the platform org holds no active license to attempt revoking';
  END IF;
  BEGIN
    UPDATE public.licenses SET status = 'revoked' WHERE id = v_lic;
    RAISE EXCEPTION 'NOC_PROBE:permitted: revoking a platform-org license succeeded — the guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE 'licenses_platform_org_guard:%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
)

_PLATFORM_ORG_HOLDS_EVERY_PRODUCT_PROBE = GuardProbe(
    id="licenses.platform_org.holds_every_product",
    product="core",
    schema="public",
    guard_name="grant_platform_org_licenses",
    kind="state_assertion",
    migrations=_PLATFORM_ORG_MIGRATIONS,
    rationale=(
        "Live state: every products row has an ACTIVE, permanent (fim NULL) "
        "license for the platform org. A product missing one means the "
        "insert trigger was bypassed or dropped."
    ),
    sql=_do_block("""
DECLARE
  v_platform uuid;
  v_missing bigint;
BEGIN
""" + _platform_org_fixture("violation") + """
  SELECT count(*) INTO v_missing FROM public.products p
   WHERE NOT EXISTS (
     SELECT 1 FROM public.licenses l
      WHERE l.org_id = v_platform AND l.product_id = p.id
        AND l.status = 'active' AND l.fim IS NULL);
  IF v_missing > 0 THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: % product(s) without an active permanent platform-org license', v_missing;
  END IF;
  RAISE EXCEPTION 'NOC_PROBE:clean: the platform org holds an active permanent license for every product';
END;
"""),
)

_PLATFORM_ORG_NEW_PRODUCT_PROBE = GuardProbe(
    id="licenses.platform_org.new_product_licensed",
    product="core",
    schema="public",
    guard_name="products_grant_platform_org_license",
    kind="state_assertion",
    migrations=_PLATFORM_ORG_MIGRATIONS,
    rationale=(
        "The 'including future products' half: a product inserted now must "
        "come out licensed to the platform org with no further step. "
        "Self-provisions a throwaway product inside the rolled-back probe."
    ),
    sql=_do_block("""
DECLARE
  v_platform uuid;
  v_prod uuid;
BEGIN
""" + _platform_org_fixture("violation") + """
  BEGIN
    INSERT INTO public.products (nome, slug, url_base)
    VALUES ('NOC probe product', 'noc-probe-' || gen_random_uuid()::text, 'https://noc-probe.invalid')
    RETURNING id INTO v_prod;
  EXCEPTION WHEN OTHERS THEN
    RAISE EXCEPTION 'NOC_PROBE:ambiguous: could not self-provision the probe product: %', SQLERRM;
  END;
  IF NOT EXISTS (
    SELECT 1 FROM public.licenses
     WHERE org_id = v_platform AND product_id = v_prod
       AND status = 'active' AND fim IS NULL) THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: a newly inserted product got no platform-org license — the products insert trigger did not fire';
  END IF;
  RAISE EXCEPTION 'NOC_PROBE:clean: a new product is licensed to the platform org by construction';
END;
"""),
)



# ---------------------------------------------------------------------------
# Platform org picker (core 070) -- the selection store, its RPCs, the revocation
# trigger and the RLS helper current_org_id_for(). Every probe builds its own
# fixture INSIDE the rolled-back transaction (flips one product ready, forges the
# caller via request.jwt.claims / request.headers) so nothing persists.
# ---------------------------------------------------------------------------

_ORG_PICKER_MIGRATIONS = ("070_platform_org_selections.sql",)
#: Probes whose expectation is core 078's "every entry is a choice" (staff with no valid
#: selection on a ready product -> NULL): parked as pending_migration until 078 is applied.
_ORG_PICKER_ENTRY_MIGRATIONS = _ORG_PICKER_MIGRATIONS + ("078_org_picker_postgrest_entry.sql",)

_ORG_PICKER_DECLARE = """
DECLARE
  v_staff uuid; v_home uuid; v_plain uuid; v_plain_home uuid;
  v_pid uuid; v_slug text; v_schema text; v_target uuid; v_unlic uuid;
  v_sid uuid := gen_random_uuid();
  v_other_sid uuid := gen_random_uuid();
  v_got uuid; v_sel uuid; v_mtarget uuid;
"""

_ORG_PICKER_FIXTURE = """
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: public.current_org_id_for(text) missing — core 070 not applied';
  END IF;
  SELECT u.id, u.org_id INTO v_staff, v_home
    FROM public.noctus_users u JOIN public.organizations o ON o.id = u.org_id
   WHERE u.role = 'admin' AND o.is_platform AND u.org_role IN ('owner', 'admin') LIMIT 1;
  IF v_staff IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no platform staff user (role=admin, org_role owner/admin, in the is_platform org)';
  END IF;
  SELECT u.id, u.org_id INTO v_plain, v_plain_home
    FROM public.noctus_users u JOIN public.organizations o ON o.id = u.org_id
   WHERE COALESCE(u.role, '') <> 'admin' AND NOT o.is_platform
     AND COALESCE(u.org_role, '') <> ALL (ARRAY['membro']) LIMIT 1;
  IF v_plain IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no ordinary (non-staff, non-platform-org) user';
  END IF;
  SELECT p.id, p.slug, p.db_schema, l.org_id INTO v_pid, v_slug, v_schema, v_target
    FROM public.licenses l JOIN public.products p ON p.id = l.product_id
   WHERE p.db_schema IS NOT NULL AND l.status = 'active' AND (l.fim IS NULL OR l.fim > now())
     AND l.org_id <> v_home LIMIT 1;
  IF v_pid IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no product with a db_schema licensed to a non-platform org';
  END IF;
  SELECT o.id INTO v_unlic FROM public.organizations o
   WHERE o.id <> v_home AND NOT EXISTS (
     SELECT 1 FROM public.licenses l
      WHERE l.org_id = o.id AND l.product_id = v_pid AND l.status = 'active') LIMIT 1;
  UPDATE public.products SET org_picker_ready = true WHERE id = v_pid;
  -- The fixture users are REAL people who may hold a live selection right now (the owner
  -- using the product): end it inside this always-rolled-back probe, or a forged row
  -- collides with platform_org_selections_one_live and the probe reads as a failure.
  UPDATE public.platform_org_selections SET ended_at = now(), ended_by = 'exit'
   WHERE user_id IN (v_staff, v_plain) AND product_id = v_pid AND ended_at IS NULL;
  -- the helper requires the login to still exist in auth.sessions
  INSERT INTO auth.sessions (id, user_id) VALUES (v_sid, v_staff);
  INSERT INTO auth.sessions (id, user_id) VALUES (v_other_sid, v_staff);
"""


def _caller_sql(uid: str, sid: str = "v_sid", aal: str = "aal2", header: str | None = None) -> str:
    out = (
        f"  PERFORM set_config('request.jwt.claims', json_build_object('sub', {uid}, "
        f"'session_id', {sid}, 'aal', '{aal}')::text, true);\n"
    )
    if header is not None:
        out += (
            "  PERFORM set_config('request.headers', json_build_object("
            f"'x-noctus-acting-org', {header})::text, true);\n"
        )
    return out


def _org_picker_probe(
    *, probe_id: str, guard_name: str, kind: str, rationale: str, steps: str,
    migrations: tuple[str, ...] = _ORG_PICKER_MIGRATIONS,
) -> GuardProbe:
    return GuardProbe(
        id=probe_id,
        product="core",
        schema="public",
        guard_name=guard_name,
        kind=kind,
        migrations=migrations,
        rationale=rationale,
        sql=_do_block(_ORG_PICKER_DECLARE + "BEGIN\n" + _ORG_PICKER_FIXTURE + steps + "\nEND;\n"),
    )


def _picker_rpc_refusal_probe(
    *, probe_id: str, code: str, setup: str, call: str, rationale: str,
    migrations: tuple[str, ...] = _ORG_PICKER_MIGRATIONS,
) -> GuardProbe:
    return _org_picker_probe(
        probe_id=probe_id, guard_name="platform_org_selection_set", kind="write_refusal",
        rationale=rationale, migrations=migrations,
        steps=setup + f"""
  BEGIN
    {call}
    RAISE EXCEPTION 'NOC_PROBE:permitted: platform_org_selection_set succeeded — the {code} refusal did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE 'platform_org_selection:{code}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;""",
    )


def _picker_helper_probe(
    *, probe_id: str, rationale: str, steps: str, expect: str, what: str,
    migrations: tuple[str, ...] = _ORG_PICKER_MIGRATIONS,
) -> GuardProbe:
    """State assertion on ``current_org_id_for(v_schema)``: after ``steps`` forge a caller,
    `v_got` is compared with `expect` (a SQL uuid expression)."""
    return _org_picker_probe(
        probe_id=probe_id, guard_name="current_org_id_for", kind="state_assertion", rationale=rationale,
        migrations=migrations,
        steps=steps + f"""
  v_got := public.current_org_id_for(v_schema);
  IF v_got IS NOT DISTINCT FROM ({expect}) THEN
    RAISE EXCEPTION 'NOC_PROBE:clean: {what}';
  END IF;
  RAISE EXCEPTION 'NOC_PROBE:violation: {what} — helper returned %, expected %', v_got, ({expect});""",
    )


_ORG_PICKER_ONE_LIVE_PROBE = _org_picker_probe(
    probe_id="platform_org_selections.one_live_per_product.unique",
    guard_name="platform_org_selections_one_live",
    kind="write_refusal",
    rationale=(
        "At most ONE live selection per (user, product): the helper and the Python store both "
        "read 'the' live row, so two would make 'which org am I in' ambiguous."
    ),
    steps="""
  BEGIN
    INSERT INTO public.platform_org_selections (user_id, product_id, target_org_id, home_org_id, auth_session_id)
    VALUES (v_staff, v_pid, v_target, v_home, v_sid);
    INSERT INTO public.platform_org_selections (user_id, product_id, target_org_id, home_org_id, auth_session_id)
    VALUES (v_staff, v_pid, v_target, v_home, v_sid);
    RAISE EXCEPTION 'NOC_PROBE:permitted: a second LIVE selection for the same (user, product) succeeded — the unique guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%platform_org_selections_one_live%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;""",
)

_ORG_PICKER_SET_UNLICENSED_PROBE = _picker_rpc_refusal_probe(
    probe_id="platform_org_selection_set.refuses_unlicensed_target",
    code="target_not_licensed",
    setup="""
  IF v_unlic IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: every organization is licensed for the product — no unlicensed target to attempt';
  END IF;""",
    call="PERFORM public.platform_org_selection_set(v_staff, v_slug, v_unlic, v_sid);",
    rationale="Staff may only enter an org holding an ACTIVE license for the product (owner decision 2026-10-08).",
)

_ORG_PICKER_SET_NOT_READY_PROBE = _picker_rpc_refusal_probe(
    probe_id="platform_org_selection_set.refuses_not_ready_product",
    code="product_not_ready",
    setup="  UPDATE public.products SET org_picker_ready = false WHERE id = v_pid;",
    call="PERFORM public.platform_org_selection_set(v_staff, v_slug, v_target, v_sid);",
    rationale=(
        "A product whose policies are not all converted to current_org_id_for() must refuse the "
        "picker: staff would otherwise see the HOME org's rows while believing they act elsewhere."
    ),
)

_ORG_PICKER_HELPER_POSITIVE_PROBE = _picker_helper_probe(
    probe_id="current_org_id_for.returns_target_for_valid_selection",
    rationale=(
        "Positive control: a valid selection (staff, this login's session_id, aal2, licensed "
        "target) resolves to the target -- without it every 'returns home' probe below would "
        "pass vacuously on a helper that never honours a selection."
    ),
    steps="""
  PERFORM public.platform_org_selection_set(v_staff, v_slug, v_target, v_sid);
""" + _caller_sql("v_staff::text"),
    expect="v_target",
    what="a valid selection resolves to the target org",
)

_ORG_PICKER_HELPER_NON_STAFF_PROBE = _picker_helper_probe(
    probe_id="current_org_id_for.home_for_non_staff",
    rationale=(
        "A non-staff caller who is NOT a member of the named org never acts there: even with a "
        "(forged, table-level) selection row naming another org, the helper answers their HOME org."
    ),
    steps="""
  DELETE FROM public.org_memberships WHERE user_id = v_plain AND org_id = v_target;
  INSERT INTO public.org_memberships (user_id, org_id, org_role, status)
  VALUES (v_plain, v_plain_home, COALESCE((SELECT u.org_role FROM public.noctus_users u WHERE u.id = v_plain), 'member'), 'active')
  ON CONFLICT (user_id, org_id) DO UPDATE SET status = 'active', ended_at = NULL;
  INSERT INTO public.platform_org_selections (user_id, product_id, target_org_id, home_org_id, auth_session_id)
  VALUES (v_plain, v_pid, v_target, v_plain_home, v_sid);
""" + _caller_sql("v_plain::text"),
    expect="v_plain_home",
    what="a non-staff caller resolves to their home org",
    migrations=_ORG_PICKER_MIGRATIONS + ("079_org_memberships.sql",),
)

_ORG_PICKER_HELPER_SESSION_PROBE = _picker_helper_probe(
    probe_id="current_org_id_for.null_on_session_mismatch",
    rationale=(
        "A selection is bound to ONE login: another session_id (a new login) holds no valid "
        "selection, so -- every entry is a choice (core 078) -- it resolves NULL, never home."
    ),
    steps="""
  PERFORM public.platform_org_selection_set(v_staff, v_slug, v_target, v_sid);
""" + _caller_sql("v_staff::text", sid="v_other_sid"),
    expect="NULL::uuid",
    what="another login session_id resolves NULL (no valid selection)",
    migrations=_ORG_PICKER_ENTRY_MIGRATIONS,
)

# Core 073 put the aal2 rule behind products.org_picker_requires_mfa (owner switched it off
# 2026-10-09). Each probe pins the flag itself inside the rolled-back transaction, so both
# branches stay proven whatever the live value is.
_PIN_MFA_SQL = """
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
              AND table_name = 'products' AND column_name = 'org_picker_requires_mfa') THEN
    EXECUTE 'UPDATE public.products SET org_picker_requires_mfa = {val} WHERE id = $1' USING v_pid;
  ELSIF NOT {val} THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: products.org_picker_requires_mfa missing — core 073 not applied';
  END IF;
"""

_ORG_PICKER_HELPER_AAL1_PROBE = _picker_helper_probe(
    probe_id="current_org_id_for.home_for_aal1",
    rationale=(
        "When the product requires 2FA (org_picker_requires_mfa, the 2026-10-08 rule): an aal1 "
        "token resolves home even with a live selection."
    ),
    steps=_PIN_MFA_SQL.format(val="true") + """
  PERFORM public.platform_org_selection_set(v_staff, v_slug, v_target, v_sid);
""" + _caller_sql("v_staff::text", aal="aal1"),
    expect="v_home",
    what="an aal1 token resolves to the home org when the product requires 2FA",
)

_ORG_PICKER_HELPER_AAL1_OPTIONAL_PROBE = _picker_helper_probe(
    probe_id="current_org_id_for.target_for_aal1_when_mfa_optional",
    rationale=(
        "Core 073: with org_picker_requires_mfa = false (owner, 2026-10-09) an aal1 staff token "
        "with a valid selection resolves the target -- the switch really switches."
    ),
    steps=_PIN_MFA_SQL.format(val="false") + """
  PERFORM public.platform_org_selection_set(v_staff, v_slug, v_target, v_sid);
""" + _caller_sql("v_staff::text", aal="aal1"),
    expect="v_target",
    what="an aal1 token resolves to the target when the product does not require 2FA",
)

_ORG_PICKER_HELPER_LICENSE_PROBE = _picker_helper_probe(
    probe_id="current_org_id_for.null_when_target_unlicensed",
    rationale=(
        "The helper re-checks the license itself: a selection whose target holds no active "
        "license (inserted at table level, bypassing the RPC and the revocation trigger) is "
        "not a valid selection -- NULL (core 078), never the target and never home."
    ),
    steps="""
  IF v_unlic IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: every organization is licensed for the product — no unlicensed target to forge';
  END IF;
  INSERT INTO public.platform_org_selections (user_id, product_id, target_org_id, home_org_id, auth_session_id)
  VALUES (v_staff, v_pid, v_unlic, v_home, v_sid);
""" + _caller_sql("v_staff::text"),
    expect="NULL::uuid",
    what="an unlicensed target resolves NULL",
    migrations=_ORG_PICKER_ENTRY_MIGRATIONS,
)

_ORG_PICKER_HELPER_HEADER_PROBE = _picker_helper_probe(
    probe_id="current_org_id_for.home_on_narrowing_header_mismatch",
    rationale=(
        "A present x-noctus-acting-org that differs from the resolved org DENIES (NULL): a stale "
        "tab never reads or writes the wrong org."
    ),
    steps="""
  PERFORM public.platform_org_selection_set(v_staff, v_slug, v_target, v_sid);
""" + _caller_sql("v_staff::text", header="v_home::text"),
    expect="NULL::uuid",
    what="a mismatching x-noctus-acting-org is denied (NULL)",
)

_ORG_PICKER_HELPER_HEADER_MATCH_PROBE = _picker_helper_probe(
    probe_id="current_org_id_for.target_on_matching_header",
    rationale="Control for the narrowing header: a header equal to the target keeps the target.",
    steps="""
  PERFORM public.platform_org_selection_set(v_staff, v_slug, v_target, v_sid);
""" + _caller_sql("v_staff::text", header="upper(v_target::text)"),
    expect="v_target",
    what="a matching x-noctus-acting-org keeps the target org",
)


_ORG_PICKER_HELPER_STALE_HEADER_PROBE = _picker_helper_probe(
    probe_id="current_org_id_for.null_on_stale_header_without_selection",
    rationale=(
        "Staff whose selection ended elsewhere but whose tab still pins the old target: the "
        "home fall-through must DENY (NULL), not silently serve the home org."
    ),
    steps="""
""" + _caller_sql("v_staff::text", header="v_target::text"),
    expect="NULL::uuid",
    what="a pin header with no live selection is denied (NULL)",
)

_ORG_PICKER_HELPER_SESSION_GONE_PROBE = _picker_helper_probe(
    probe_id="current_org_id_for.null_when_auth_session_gone",
    rationale=(
        "A selection dies with its login: once the auth.sessions row is gone the selection is "
        "not valid and the helper resolves NULL (core 078), not home."
    ),
    steps="""
  PERFORM public.platform_org_selection_set(v_staff, v_slug, v_target, v_sid);
  DELETE FROM auth.sessions WHERE id = v_sid;
""" + _caller_sql("v_staff::text"),
    expect="NULL::uuid",
    what="a selection whose auth session is gone resolves NULL",
    migrations=_ORG_PICKER_ENTRY_MIGRATIONS,
)

_ORG_PICKER_HELPER_NOT_READY_PROBE = _picker_helper_probe(
    probe_id="current_org_id_for.home_when_product_not_ready",
    rationale="A product that is not org_picker_ready never honours a selection (table-level forged row).",
    steps="""
  INSERT INTO public.platform_org_selections (user_id, product_id, target_org_id, home_org_id, auth_session_id)
  VALUES (v_staff, v_pid, v_target, v_home, v_sid);
  ALTER TABLE public.products DISABLE TRIGGER products_revoke_org_selection;
  UPDATE public.products SET org_picker_ready = false WHERE id = v_pid;
""" + _caller_sql("v_staff::text"),
    expect="v_home",
    what="a not-ready product resolves to the home org",
)

_ORG_PICKER_HELPER_STAFF_ROLE_PROBE = _picker_helper_probe(
    probe_id="current_org_id_for.home_for_platform_admin_without_owner_or_admin_org_role",
    rationale="Staff additionally needs home org_role owner/admin: a platform-org admin-flag with a lesser org role never acts.",
    steps="""
  UPDATE public.noctus_users SET org_role = 'viewer' WHERE id = v_staff;
  INSERT INTO public.platform_org_selections (user_id, product_id, target_org_id, home_org_id, auth_session_id)
  VALUES (v_staff, v_pid, v_target, v_home, v_sid);
""" + _caller_sql("v_staff::text"),
    expect="v_home",
    what="role=admin without an owner/admin org_role resolves to the home org",
)

# Core 078 -- every entry is a choice: staff on a READY product with NO valid live selection
# whose token satisfies the MFA rule resolve NULL (the SQL half of resolve_effective_org's 409
# org_selection_required); an aal1 token on a product that requires 2FA keeps home (the
# resolver's mfa_required path).
_ORG_PICKER_HELPER_NO_SELECTION_PROBE = _picker_helper_probe(
    probe_id="current_org_id_for.null_for_staff_without_selection_on_ready_product",
    rationale=(
        "Core 078 (owner, 2026-10-12): platform staff on an org_picker_ready product with no live "
        "selection must NOT silently read their home org through PostgREST -- NULL until they pick."
    ),
    steps="\n" + _caller_sql("v_staff::text"),
    expect="NULL::uuid",
    what="staff without a selection on a ready product resolve NULL",
    migrations=_ORG_PICKER_ENTRY_MIGRATIONS,
)

_ORG_PICKER_HELPER_NO_SELECTION_AAL1_OPTIONAL_PROBE = _picker_helper_probe(
    probe_id="current_org_id_for.null_for_aal1_staff_without_selection_when_mfa_optional",
    rationale=(
        "Core 078 with org_picker_requires_mfa = false (the fleet setting since 2026-10-09): an aal1 "
        "staff token passes the MFA rule, so no selection still means NULL, not home."
    ),
    steps=_PIN_MFA_SQL.format(val="false") + _caller_sql("v_staff::text", aal="aal1"),
    expect="NULL::uuid",
    what="aal1 staff without a selection resolve NULL when the product does not require 2FA",
    migrations=_ORG_PICKER_ENTRY_MIGRATIONS,
)

_ORG_PICKER_HELPER_NO_SELECTION_AAL1_REQUIRED_PROBE = _picker_helper_probe(
    probe_id="current_org_id_for.home_for_aal1_staff_without_selection_when_mfa_required",
    rationale=(
        "Control for core 078: when the product requires 2FA an aal1 staff token is on the MFA "
        "path (resolver: home + mfa_required), so it keeps the home org even without a selection."
    ),
    steps=_PIN_MFA_SQL.format(val="true") + _caller_sql("v_staff::text", aal="aal1"),
    expect="v_home",
    what="aal1 staff without a selection keep the home org when the product requires 2FA",
    migrations=_ORG_PICKER_ENTRY_MIGRATIONS,
)

_ORG_PICKER_PRODUCT_REVOKE_PROBE = _org_picker_probe(
    probe_id="platform_org_selections.product_trigger.ends_selection",
    guard_name="products_revoke_org_selection",
    kind="state_assertion",
    rationale="Un-readying a product (or changing its schema) ends every live selection for it, by trigger.",
    steps="""
  v_sel := public.platform_org_selection_set(v_staff, v_slug, v_target, v_sid);
  UPDATE public.products SET org_picker_ready = false WHERE id = v_pid;
  IF EXISTS (SELECT 1 FROM public.platform_org_selections WHERE id = v_sel AND ended_by = 'revoked' AND ended_at IS NOT NULL) THEN
    RAISE EXCEPTION 'NOC_PROBE:clean: un-readying the product ended the live selection (revoked)';
  END IF;
  RAISE EXCEPTION 'NOC_PROBE:violation: the product lost org_picker_ready but the live selection was not revoked';""",
)

_ORG_PICKER_REVOKE_PROBE = _org_picker_probe(
    probe_id="platform_org_selections.revocation_trigger.ends_selection",
    guard_name="organizations_revoke_org_selection",
    kind="state_assertion",
    rationale=(
        "A live selection dies the moment its premise does: when the home org stops being "
        "is_platform the staff's selection is ended 'revoked' by trigger, not by app code."
    ),
    steps="""
  v_sel := public.platform_org_selection_set(v_staff, v_slug, v_target, v_sid);
  UPDATE public.organizations SET is_platform = false WHERE id = v_home;
  IF EXISTS (SELECT 1 FROM public.platform_org_selections WHERE id = v_sel AND ended_by = 'revoked' AND ended_at IS NOT NULL) THEN
    RAISE EXCEPTION 'NOC_PROBE:clean: losing is_platform ended the live selection (revoked)';
  END IF;
  RAISE EXCEPTION 'NOC_PROBE:violation: the home org lost is_platform but the live selection was not revoked';""",
)



# ---- Multi-org S2+S3 (core 081): a MEMBER selects through the same picker -------------------------
# Fixture: v_plain (a non-staff user with an active HOME membership) is made a member of v_mtarget --
# a licensed org that is neither their home nor the platform org -- with the role 'viewer', so
# "owner at home / viewer in the target" is the standing shape every probe checks against.
_ORG_MEMBER_MIGRATIONS = _ORG_PICKER_ENTRY_MIGRATIONS + (
    "079_org_memberships.sql", "081_org_member_selection.sql",
)

_ORG_MEMBER_FIXTURE = """
  IF to_regclass('public.org_memberships') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: public.org_memberships missing — core 079 not applied';
  END IF;
  SELECT l.org_id INTO v_mtarget
    FROM public.licenses l
   WHERE l.product_id = v_pid AND l.status = 'active' AND (l.fim IS NULL OR l.fim > now())
     AND l.org_id <> v_plain_home AND l.org_id <> v_home LIMIT 1;
  IF v_mtarget IS NULL THEN
    SELECT o.id INTO v_mtarget FROM public.organizations o
     WHERE o.id <> v_plain_home AND o.id <> v_home AND NOT o.is_platform LIMIT 1;
    IF v_mtarget IS NULL THEN
      RAISE EXCEPTION 'NOC_PROBE:no_fixture: no third organization to make the plain user a member of';
    END IF;
    INSERT INTO public.licenses (org_id, product_id, status) VALUES (v_mtarget, v_pid, 'active');
  END IF;
  INSERT INTO public.org_memberships (user_id, org_id, org_role, status)
  VALUES (v_plain, v_plain_home,
          COALESCE((SELECT u.org_role FROM public.noctus_users u WHERE u.id = v_plain), 'member'), 'active')
  ON CONFLICT (user_id, org_id) DO UPDATE SET status = 'active', ended_at = NULL;
  INSERT INTO public.org_memberships (user_id, org_id, org_role, status)
  VALUES (v_plain, v_mtarget, 'viewer', 'active')
  ON CONFLICT (user_id, org_id) DO UPDATE SET org_role = 'viewer', status = 'active', ended_at = NULL;
  -- D1 counts ELIGIBLE orgs: the borrowed user's OTHER real memberships and D5 blocks would make
  -- the expectation data-dependent, so they are set aside inside this rolled-back probe.
  UPDATE public.org_memberships SET status = 'removed', ended_at = now()
   WHERE user_id = v_plain AND org_id NOT IN (v_plain_home, v_mtarget) AND status = 'active';
  IF to_regclass('public.org_member_product_access') IS NOT NULL THEN
    EXECUTE 'UPDATE public.org_member_product_access SET unblocked_at = now()
              WHERE user_id = $1 AND unblocked_at IS NULL' USING v_plain;
  END IF;
"""

#: Core 083 (owner D1/D5, 2026-10-14): the member branch counts ELIGIBLE orgs and honours blocks.
_ACCESS_RULES_MIGRATIONS = _ORG_MEMBER_MIGRATIONS + ("083_member_access_rules.sql",)

_PLAIN_HOME_LICENSED_SQL = """
  INSERT INTO public.licenses (org_id, product_id, status)
  SELECT v_plain_home, v_pid, 'active'
   WHERE NOT EXISTS (SELECT 1 FROM public.licenses l
                      WHERE l.org_id = v_plain_home AND l.product_id = v_pid
                        AND l.status = 'active' AND (l.fim IS NULL OR l.fim > now()));
"""

_PLAIN_HOME_UNLICENSED_SQL = """
  DELETE FROM public.licenses WHERE org_id = v_plain_home AND product_id = v_pid;
"""

_BLOCK_SQL = """
  IF to_regclass('public.org_member_product_access') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: public.org_member_product_access missing — core 083 not applied';
  END IF;
  EXECUTE 'INSERT INTO public.org_member_product_access (user_id, org_id, product_id) VALUES ($1, $2, $3)'
    USING v_plain, {org}, v_pid;
"""

_ORG_MEMBER_REMOVE = """
  UPDATE public.org_memberships SET status = 'removed', ended_at = now()
   WHERE user_id = v_plain AND org_id = v_mtarget;
"""


def _member_refusal_probe(*, probe_id: str, rationale: str, setup: str) -> GuardProbe:
    return _picker_rpc_refusal_probe(
        probe_id=probe_id, code="not_a_member", rationale=rationale,
        setup=_ORG_MEMBER_FIXTURE + setup,
        call="PERFORM public.platform_org_selection_set(v_plain, v_slug, v_mtarget, v_sid);",
        migrations=_ORG_MEMBER_MIGRATIONS,
    )


def _member_helper_probe(
    *, probe_id: str, rationale: str, steps: str, expect: str, what: str,
    migrations: tuple[str, ...] = _ORG_MEMBER_MIGRATIONS,
) -> GuardProbe:
    return _picker_helper_probe(
        probe_id=probe_id, rationale=rationale, steps=_ORG_MEMBER_FIXTURE + steps,
        expect=expect, what=what, migrations=migrations,
    )


_ORG_MEMBER_NOT_A_MEMBER_PROBE = _member_refusal_probe(
    probe_id="platform_org_selection_set.refuses_non_member",
    rationale=(
        "Who may select org X: platform staff OR an ACTIVE member of X. A user with no membership in "
        "the target is refused by the RPC itself -- a compromised or buggy API caller cannot grant it."
    ),
    setup="  DELETE FROM public.org_memberships WHERE user_id = v_plain AND org_id = v_mtarget;",
)

_ORG_MEMBER_REMOVED_PROBE = _member_refusal_probe(
    probe_id="platform_org_selection_set.refuses_removed_member",
    rationale="A REMOVED membership is not a membership: the RPC refuses it exactly like a stranger.",
    setup=_ORG_MEMBER_REMOVE,
)

_ORG_MEMBER_POSITIVE_PROBE = _member_helper_probe(
    probe_id="current_org_id_for.member_selection_resolves_target",
    rationale=(
        "Positive control for members: an ACTIVE member's valid selection (this login, aal1 -- members "
        "never need 2FA, owner Q1 -- licensed target) resolves to the target even though the product "
        "requires 2FA for staff. Without it every 'stops resolving' probe passes vacuously."
    ),
    steps=_PIN_MFA_SQL.format(val="true") + """
  PERFORM public.platform_org_selection_set(v_plain, v_slug, v_mtarget, v_sid);
""" + _caller_sql("v_plain::text", aal="aal1"),
    expect="v_mtarget",
    what="a valid member selection resolves to the target org without aal2",
)

_ORG_MEMBER_REMOVED_FALLBACK_PROBE = _member_helper_probe(
    probe_id="current_org_id_for.removed_member_selection_falls_back_to_home",
    rationale=(
        "Revocation by recheck: ending the membership makes a live selection stop resolving on the "
        "very next query (nothing is cached in the JWT) -- the helper falls back to the HOME rule."
    ),
    steps="""
  INSERT INTO public.platform_org_selections (user_id, product_id, target_org_id, home_org_id, auth_session_id)
  VALUES (v_plain, v_pid, v_mtarget, v_plain_home, v_sid);
""" + _ORG_MEMBER_REMOVE + _caller_sql("v_plain::text", aal="aal1"),
    expect="v_plain_home",
    what="the selection of a removed member falls back to their home org",
)

_ORG_MEMBER_NEVER_REMOVED_ORG_PROBE = _member_helper_probe(
    probe_id="current_org_id_for.removed_member_never_resolves_the_removed_org",
    rationale=(
        "The profile follows a member's pick (owner Q3), so after a RPC selection the 'home' IS the "
        "target. Removing that membership must NOT fall back to it: the home rule itself needs an "
        "ACTIVE membership. With D1 (core 083) the one remaining eligible org (the old home, when "
        "licensed) is landed in silently; otherwise NULL -- never the org they were removed from."
    ),
    steps="""
  PERFORM public.platform_org_selection_set(v_plain, v_slug, v_mtarget, v_sid);
""" + _ORG_MEMBER_REMOVE + _caller_sql("v_plain::text", aal="aal1"),
    expect=(
        "CASE WHEN EXISTS (SELECT 1 FROM public.licenses l WHERE l.org_id = v_plain_home "
        "AND l.product_id = v_pid AND l.status = 'active' AND (l.fim IS NULL OR l.fim > now())) "
        "THEN v_plain_home ELSE NULL::uuid END"
    ),
    what="a removed member never resolves the removed org (the remaining eligible org, else NULL)",
    migrations=_ACCESS_RULES_MIGRATIONS,
)

_ORG_MEMBER_PIN_PROBE = _member_helper_probe(
    probe_id="current_org_id_for.member_pin_mismatch_denied",
    rationale="The pin header only NARROWS for members too: a header naming another org DENIES (NULL), never widens.",
    steps="""
  PERFORM public.platform_org_selection_set(v_plain, v_slug, v_mtarget, v_sid);
""" + _caller_sql("v_plain::text", aal="aal1", header="v_plain_home::text"),
    expect="NULL::uuid",
    what="a mismatching x-noctus-acting-org denies a member selection",
)

_ORG_MEMBER_CUSTOMER_PROBE = _member_helper_probe(
    probe_id="current_org_id_for.customer_role_membership_is_never_served",
    rationale=(
        "An end customer (customer-role membership) never acts through the picker: a selection of "
        "it is not honoured and it is never an ELIGIBLE org (D1, core 083) -- the membership grants "
        "a seat, not staff access. The user lands in their one eligible org (home), never the target."
    ),
    migrations=_ACCESS_RULES_MIGRATIONS,
    steps="""
  UPDATE public.org_memberships SET org_role = 'membro' WHERE user_id = v_plain AND org_id = v_mtarget;
  INSERT INTO public.platform_org_selections (user_id, product_id, target_org_id, home_org_id, auth_session_id)
  VALUES (v_plain, v_pid, v_mtarget, v_plain_home, v_sid);
""" + _caller_sql("v_plain::text", aal="aal1"),
    expect="v_plain_home",
    what="a customer-role membership is never served (the home org is)",
)

_ORG_MEMBER_HOME_REMOVED_PROBE = _member_helper_probe(
    probe_id="current_org_id_for.removed_home_is_never_served",
    rationale=(
        "Even with no selection at all, a user whose profile still names an org they were REMOVED "
        "from never resolves it: the home rule requires an ACTIVE membership. With D1 (core 083) "
        "their only remaining eligible org (the licensed target) is landed in instead."
    ),
    steps="""
  UPDATE public.org_memberships SET status = 'removed', ended_at = now()
   WHERE user_id = v_plain AND org_id = v_plain_home;
""" + _caller_sql("v_plain::text", aal="aal1"),
    expect="v_mtarget",
    what="a user removed from their home org never resolves it (the one eligible org instead)",
    migrations=_ACCESS_RULES_MIGRATIONS,
)

# ---- Multi-org S4b (core 083, owner decisions D1/D5 2026-10-14) ---------------------------------
_D1_TWO_ELIGIBLE_PROBE = _member_helper_probe(
    probe_id="current_org_id_for.member_with_two_eligible_orgs_and_no_selection_is_null",
    rationale=(
        "D1: a member with >=2 eligible orgs (active, non-customer, licensed, not blocked) chooses "
        "on EVERY entry -- without a valid selection PostgREST must not silently serve the "
        "last-active org (the SQL half of the resolver's 409 org_selection_required)."
    ),
    steps=_PLAIN_HOME_LICENSED_SQL + _caller_sql("v_plain::text", aal="aal1"),
    expect="NULL::uuid",
    what="two eligible orgs and no selection resolve NULL",
    migrations=_ACCESS_RULES_MIGRATIONS,
)

_D1_ONE_ELIGIBLE_PROBE = _member_helper_probe(
    probe_id="current_org_id_for.member_with_one_eligible_org_lands_there",
    rationale=(
        "D1: exactly ONE eligible org is landed in silently, even when it is not the last-active "
        "(profile) org -- here the home is unlicensed, so the licensed target is the only choice."
    ),
    steps=_PLAIN_HOME_UNLICENSED_SQL + _caller_sql("v_plain::text", aal="aal1"),
    expect="v_mtarget",
    what="the only eligible org is resolved without a selection",
    migrations=_ACCESS_RULES_MIGRATIONS,
)

_D5_BLOCKED_SELECTION_PROBE = _member_helper_probe(
    probe_id="current_org_id_for.blocked_org_is_never_resolved",
    rationale=(
        "D5: blocking a member from the product in an org makes a live selection of it stop "
        "resolving on the next query (re-checked every call); the remaining eligible org is served."
    ),
    steps=_PLAIN_HOME_LICENSED_SQL + """
  PERFORM public.platform_org_selection_set(v_plain, v_slug, v_mtarget, v_sid);
""" + _BLOCK_SQL.format(org="v_mtarget") + _caller_sql("v_plain::text", aal="aal1"),
    expect="v_plain_home",
    what="a blocked selected org is never resolved",
    migrations=_ACCESS_RULES_MIGRATIONS,
)

_D5_BLOCKED_PICK_PROBE = _picker_rpc_refusal_probe(
    probe_id="platform_org_selection_set.refuses_blocked_member",
    code="product_blocked",
    rationale="D5: the selection RPC itself refuses an org the member is blocked from for the product.",
    setup=_ORG_MEMBER_FIXTURE + _BLOCK_SQL.format(org="v_mtarget"),
    call="PERFORM public.platform_org_selection_set(v_plain, v_slug, v_mtarget, v_sid);",
    migrations=_ACCESS_RULES_MIGRATIONS,
)


def _block_table_probe(*, probe_id: str, guard_name: str, rationale: str, steps: str, what: str) -> GuardProbe:
    return _org_picker_probe(
        probe_id=probe_id, guard_name=guard_name, kind="write_refusal", rationale=rationale,
        migrations=_ACCESS_RULES_MIGRATIONS,
        steps=_ORG_MEMBER_FIXTURE + f"""
  BEGIN
{steps}
    RAISE EXCEPTION 'NOC_PROBE:permitted: {what} succeeded — the {guard_name} guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{guard_name}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;""",
    )


_D5_ONE_LIVE_BLOCK_PROBE = _block_table_probe(
    probe_id="org_member_product_access.one_live_block",
    guard_name="org_member_product_access_one_live",
    rationale="At most ONE live block per (user, org, product): unblocking closes THE row.",
    steps=_BLOCK_SQL.format(org="v_mtarget") + _BLOCK_SQL.format(org="v_mtarget"),
    what="a second live block for the same (user, org, product)",
)

_D5_APPEND_ONLY_PROBE = _block_table_probe(
    probe_id="org_member_product_access.append_only",
    guard_name="org_member_product_access_append_only",
    rationale=(
        "A block row is audit history: identity and blocked_at never change and a closed block is "
        "never re-opened or re-dated -- only closing a live block is allowed."
    ),
    steps=_BLOCK_SQL.format(org="v_mtarget") + """
    EXECUTE 'UPDATE public.org_member_product_access SET blocked_at = blocked_at - interval ''1 day''
              WHERE user_id = $1 AND org_id = $2' USING v_plain, v_mtarget;""",
    what="rewriting blocked_at of a block row",
)

_D5_UNBLOCK_PAIR_PROBE = _block_table_probe(
    probe_id="org_member_product_access.unblocked_by_needs_at",
    guard_name="org_member_product_access_unblocked_by_needs_at",
    rationale="An unblocker without an unblock time is a half-closed block; the CHECK refuses it.",
    steps="""
    EXECUTE 'INSERT INTO public.org_member_product_access (user_id, org_id, product_id, unblocked_by)
             VALUES ($1, $2, $3, $1)' USING v_plain, v_mtarget, v_pid;""",
    what="an unblocked_by without unblocked_at",
)

_D3_MOVE_FORBIDDEN_PROBE = _org_picker_probe(
    probe_id="team_member_move.refuses_an_actor_who_does_not_manage_both_orgs",
    guard_name="team_member_move",
    kind="write_refusal",
    migrations=_ACCESS_RULES_MIGRATIONS,
    rationale=(
        "D3: an org owner/admin may move a user only between orgs where they are owner/admin in "
        "BOTH (platform staff anywhere). A viewer in the source moving themselves out is refused in "
        "SQL -- no caller can skip it."
    ),
    steps=_ORG_MEMBER_FIXTURE + """
  BEGIN
    PERFORM public.team_member_move(v_plain, v_plain, v_mtarget, v_plain_home, 'member', 'add');
    RAISE EXCEPTION 'NOC_PROBE:permitted: a non-manager moved a user — the authority check did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE 'team_membership:forbidden%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;""",
)

_D4_SOLE_MEMBER_KEEPS_PROFILE_PROBE = _org_picker_probe(
    probe_id="team_member_remove.sole_member_keeps_the_profile_in_a_personal_org",
    guard_name="team_member_remove",
    kind="state_assertion",
    migrations=_ACCESS_RULES_MIGRATIONS,
    rationale=(
        "D4: removing a user whose ONLY active membership is this org never deletes the profile "
        "(audit history is append-only); in the same transaction it moves to a personal org of "
        "their own as its owner. Fires the deferred invariant IMMEDIATE (what COMMIT judges)."
    ),
    steps=_ORG_MEMBER_FIXTURE + """
  -- v_plain: a plain member of their home only (mtarget set aside), not an owner there
  UPDATE public.org_memberships SET status = 'removed', ended_at = now()
   WHERE user_id = v_plain AND org_id = v_mtarget;
  UPDATE public.org_memberships SET org_role = 'member' WHERE user_id = v_plain AND org_id = v_plain_home;
  INSERT INTO public.organizations (nome, slug, owner_id, is_personal)
  VALUES ('Pessoal — probe', 'noc-probe-' || gen_random_uuid()::text, v_plain, true)
  RETURNING id INTO v_target;
  BEGIN
    PERFORM public.team_member_remove(v_plain_home, v_plain, NULL::uuid, v_target);
    SET CONSTRAINTS public.org_memberships_profile_org_active IMMEDIATE;
  EXCEPTION WHEN OTHERS THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: removing the sole-org member raised: %', SQLERRM;
  END;
  IF EXISTS (SELECT 1 FROM public.noctus_users n WHERE n.id = v_plain AND n.org_id = v_target AND n.org_role = 'owner')
     AND EXISTS (SELECT 1 FROM public.org_memberships m
                  WHERE m.user_id = v_plain AND m.org_id = v_target AND m.status = 'active' AND m.org_role = 'owner') THEN
    RAISE EXCEPTION 'NOC_PROBE:clean: the profile is kept, owner of its personal org';
  END IF;
  RAISE EXCEPTION 'NOC_PROBE:violation: the profile was not moved to the personal org as its owner';""",
)

_ACCESS_RULES_PROBES: tuple[GuardProbe, ...] = (
    _D1_TWO_ELIGIBLE_PROBE,
    _D1_ONE_ELIGIBLE_PROBE,
    _D5_BLOCKED_SELECTION_PROBE,
    _D5_BLOCKED_PICK_PROBE,
    _D5_ONE_LIVE_BLOCK_PROBE,
    _D5_APPEND_ONLY_PROBE,
    _D5_UNBLOCK_PAIR_PROBE,
    _D3_MOVE_FORBIDDEN_PROBE,
    _D4_SOLE_MEMBER_KEEPS_PROFILE_PROBE,
)

# ---- Multi-org S5b (core 084, owner decisions P1/P3/P5 2026-10-14) -------------------------------
#: Core 084: owner grants are staff-only (P1), staff are never blocked (P3), blocks are owner-only (P5).
_OWNER_GRANT_MIGRATIONS = _ACCESS_RULES_MIGRATIONS + ("084_owner_grant_and_block_rules.sql",)


def _team_rpc_refusal_probe(
    *, probe_id: str, guard_name: str, code: str, rationale: str, setup: str, call: str,
) -> GuardProbe:
    """``call`` (a team RPC) must raise ``team_membership:<code>`` after ``setup``."""
    return _org_picker_probe(
        probe_id=probe_id, guard_name=guard_name, kind="write_refusal", rationale=rationale,
        migrations=_OWNER_GRANT_MIGRATIONS,
        steps=_ORG_MEMBER_FIXTURE + setup + f"""
  BEGIN
    {call}
    RAISE EXCEPTION 'NOC_PROBE:permitted: {guard_name} succeeded — the {code} refusal did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE 'team_membership:{code}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;""",
    )


_P1_SET_ROLE_OWNER_GRANT_PROBE = _team_rpc_refusal_probe(
    probe_id="team_member_set_role.refuses_owner_grant_by_non_staff",
    guard_name="team_member_set_role",
    code="owner_grant_forbidden",
    rationale=(
        "P1: granting `owner` in an org is for NoctusAI staff only. An org OWNER (not staff) promoting "
        "a member to owner is refused in SQL, decided from the actor -- no caller can skip it."
    ),
    setup="""
  UPDATE public.org_memberships SET org_role = 'owner' WHERE user_id = v_plain AND org_id = v_mtarget;
  INSERT INTO public.org_memberships (user_id, org_id, org_role, status)
  VALUES (v_staff, v_mtarget, 'member', 'active')
  ON CONFLICT (user_id, org_id) DO UPDATE SET org_role = 'member', status = 'active', ended_at = NULL;
""",
    call="PERFORM public.team_member_set_role(v_mtarget, v_staff, 'owner', v_plain);",
)

_P1_MOVE_OWNER_GRANT_PROBE = _team_rpc_refusal_probe(
    probe_id="team_member_move.refuses_owner_grant_by_non_staff",
    guard_name="team_member_move",
    code="owner_grant_forbidden",
    rationale=(
        "P1: the move target role follows the same rule -- an org owner of BOTH orgs (not staff) "
        "may move a user but never make them `owner` in the target."
    ),
    setup="""
  UPDATE public.org_memberships SET org_role = 'owner'
   WHERE user_id = v_plain AND org_id IN (v_plain_home, v_mtarget);
  INSERT INTO public.org_memberships (user_id, org_id, org_role, status)
  VALUES (v_staff, v_plain_home, 'member', 'active')
  ON CONFLICT (user_id, org_id) DO UPDATE SET org_role = 'member', status = 'active', ended_at = NULL;
  DELETE FROM public.org_memberships WHERE user_id = v_staff AND org_id = v_mtarget;
""",
    call="PERFORM public.team_member_move(v_plain, v_staff, v_plain_home, v_mtarget, 'owner', 'add');",
)

_P5_ADMIN_CANNOT_BLOCK_PROBE = _team_rpc_refusal_probe(
    probe_id="org_member_product_access_set.refuses_org_admin",
    guard_name="org_member_product_access_set",
    code="forbidden",
    rationale=(
        "P5: blocking/unblocking a member's product access is for the org's OWNER and NoctusAI staff "
        "only; an org ADMIN is refused in SQL."
    ),
    setup="""
  UPDATE public.org_memberships SET org_role = 'admin' WHERE user_id = v_plain AND org_id = v_mtarget;
""",
    call="PERFORM public.org_member_product_access_set(v_plain, v_mtarget, v_plain, v_slug, true);",
)

_P3_STAFF_NEVER_BLOCKED_PROBE = _team_rpc_refusal_probe(
    probe_id="org_member_product_access_set.refuses_blocking_staff",
    guard_name="org_member_product_access_set",
    code="cannot_block_staff",
    rationale="P3: NoctusAI staff can never be blocked from a product, not even by staff.",
    setup="""
  INSERT INTO public.org_memberships (user_id, org_id, org_role, status)
  VALUES (v_staff, v_mtarget, 'member', 'active')
  ON CONFLICT (user_id, org_id) DO UPDATE SET status = 'active', ended_at = NULL;
""",
    call="PERFORM public.org_member_product_access_set(v_staff, v_mtarget, v_staff, v_slug, true);",
)

_OWNER_GRANT_RULES_PROBES: tuple[GuardProbe, ...] = (
    _P1_SET_ROLE_OWNER_GRANT_PROBE,
    _P1_MOVE_OWNER_GRANT_PROBE,
    _P5_ADMIN_CANNOT_BLOCK_PROBE,
    _P3_STAFF_NEVER_BLOCKED_PROBE,
)

_ORG_MEMBER_ROLE_PROBE = _org_picker_probe(
    probe_id="platform_org_selection_set.member_role_is_the_target_membership_role",
    guard_name="platform_org_selection_set",
    kind="state_assertion",
    rationale=(
        "The #1 risk of multi-org (privilege leak): a member's pick moves their profile to the target "
        "with the role of THAT membership ('viewer'), never the role they hold elsewhere, and the "
        "memberships themselves are neither ended nor downgraded."
    ),
    migrations=_ORG_MEMBER_MIGRATIONS,
    steps=_ORG_MEMBER_FIXTURE + """
  PERFORM public.platform_org_selection_set(v_plain, v_slug, v_mtarget, v_sid);
  IF NOT EXISTS (SELECT 1 FROM public.noctus_users u
                  WHERE u.id = v_plain AND u.org_id = v_mtarget AND u.org_role = 'viewer') THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: the profile did not follow the pick with the target membership role';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.org_memberships m
                  WHERE m.user_id = v_plain AND m.org_id = v_mtarget AND m.status = 'active' AND m.org_role = 'viewer')
     OR NOT EXISTS (SELECT 1 FROM public.org_memberships m
                     WHERE m.user_id = v_plain AND m.org_id = v_plain_home AND m.status = 'active') THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: following the pick ended or downgraded a membership';
  END IF;
  RAISE EXCEPTION 'NOC_PROBE:clean: the member is a viewer in the target and both memberships are intact';""",
)

_ORG_MEMBER_PROFILE_ORG_ACTIVE_PROBE = GuardProbe(
    id="org_memberships.profile_org_stays_active",
    product="core",
    schema="public",
    guard_name="org_memberships_profile_org_active",
    kind="write_refusal",
    migrations=_ORG_MEMBER_MIGRATIONS,
    rationale=(
        "Every reader that trusts noctus_users.org_id (the Python resolver's common path, products "
        "without the picker) is revocation-safe only because ending the membership a profile points "
        "at is refused unless the profile moves in the same transaction. Without it a removed member "
        "keeps FastAPI access while RLS denies them."
    ),
    sql=_do_block("""
DECLARE
  v_user uuid;
  v_org uuid;
BEGIN
  SELECT n.id, n.org_id INTO v_user, v_org
    FROM public.noctus_users n
    JOIN public.org_memberships m ON m.user_id = n.id AND m.org_id = n.org_id AND m.status = 'active'
   LIMIT 1;
  IF v_user IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no profile with an active home membership to borrow';
  END IF;
  BEGIN
    UPDATE public.org_memberships SET status = 'removed', ended_at = now()
     WHERE user_id = v_user AND org_id = v_org;
    -- the guard is a DEFERRED constraint trigger and this probe always rolls back: fire it now
    SET CONSTRAINTS public.org_memberships_profile_org_active IMMEDIATE;
    RAISE EXCEPTION 'NOC_PROBE:permitted: ending the membership a profile points at succeeded — the guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE 'org_memberships_profile_org_active:%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
)

_ORG_MEMBER_PROBES: tuple[GuardProbe, ...] = (
    _ORG_MEMBER_PROFILE_ORG_ACTIVE_PROBE,
    _ORG_MEMBER_NOT_A_MEMBER_PROBE,
    _ORG_MEMBER_REMOVED_PROBE,
    _ORG_MEMBER_POSITIVE_PROBE,
    _ORG_MEMBER_REMOVED_FALLBACK_PROBE,
    _ORG_MEMBER_NEVER_REMOVED_ORG_PROBE,
    _ORG_MEMBER_PIN_PROBE,
    _ORG_MEMBER_CUSTOMER_PROBE,
    _ORG_MEMBER_HOME_REMOVED_PROBE,
    _ORG_MEMBER_ROLE_PROBE,
)


# ---- Multi-org S4 (core 082): remove / change-role / accept as MEMBERSHIP operations ---------------
# Each function is one transaction that must keep the 081 invariant (a profile's org is an ACTIVE
# membership) true at COMMIT. The refusals are write_refusals; the profile move is a state assertion
# that fires the DEFERRED invariant trigger IMMEDIATE so the probe judges the same thing COMMIT would.
_TEAM_OPS_MIGRATIONS = ("079_org_memberships.sql", "081_org_member_selection.sql", "082_team_membership_ops.sql")

_TEAM_LAST_OWNER_FIXTURE = """
DECLARE
  v_user uuid;
  v_org  uuid;
BEGIN
  IF to_regprocedure('public.team_member_remove(uuid,uuid)') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: public.team_member_remove missing — core 082 not applied';
  END IF;
  SELECT m.user_id, m.org_id INTO v_user, v_org
    FROM public.org_memberships m
   WHERE m.status = 'active' AND m.org_role = 'owner'
     AND NOT EXISTS (SELECT 1 FROM public.org_memberships o
                      WHERE o.org_id = m.org_id AND o.status = 'active' AND o.org_role = 'owner'
                        AND o.user_id <> m.user_id)
   LIMIT 1;
  IF v_user IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no organization with exactly one active owner';
  END IF;
  BEGIN
    {call}
    RAISE EXCEPTION 'NOC_PROBE:permitted: {what} succeeded — the last-owner refusal did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE 'team_membership:last_owner%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""

_TEAM_REMOVE_LAST_OWNER_PROBE = GuardProbe(
    id="team_member_remove.refuses_last_owner",
    product="core",
    schema="public",
    guard_name="team_member_remove",
    kind="write_refusal",
    migrations=_TEAM_OPS_MIGRATIONS,
    rationale=(
        "Ending the only ACTIVE owner of an org would leave it unadministrable; the refusal lives in "
        "the function (serialised on the organizations row) so no caller can skip it."
    ),
    sql=_do_block(_TEAM_LAST_OWNER_FIXTURE.format(
        call="PERFORM public.team_member_remove(v_org, v_user);", what="removing the last owner")),
)

_TEAM_SET_ROLE_LAST_OWNER_PROBE = GuardProbe(
    id="team_member_set_role.refuses_demoting_last_owner",
    product="core",
    schema="public",
    guard_name="team_member_set_role",
    kind="write_refusal",
    migrations=_TEAM_OPS_MIGRATIONS,
    rationale="Demoting the only ACTIVE owner is the same hole as removing them.",
    sql=_do_block(_TEAM_LAST_OWNER_FIXTURE.format(
        call="PERFORM public.team_member_set_role(v_org, v_user, 'member');", what="demoting the last owner")),
)

_TEAM_REMOVE_MOVES_PROFILE_PROBE = GuardProbe(
    id="team_member_remove.moves_profile_in_the_same_transaction",
    product="core",
    schema="public",
    guard_name="team_member_remove",
    kind="state_assertion",
    migrations=_TEAM_OPS_MIGRATIONS,
    rationale=(
        "Removing a member from their PROFILE org must move the profile to their most recently "
        "updated other ACTIVE membership in the SAME transaction (org_id + that membership's role): "
        "the deferred org_memberships_profile_org_active trigger refuses COMMIT otherwise. The probe "
        "fires that trigger IMMEDIATE, so it judges what COMMIT would."
    ),
    sql=_do_block("""
DECLARE
  v_user  uuid;
  v_home  uuid;
  v_other uuid;
  v_after uuid;
  v_arole text;
BEGIN
  IF to_regprocedure('public.team_member_remove(uuid,uuid)') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: public.team_member_remove missing — core 082 not applied';
  END IF;
  SELECT n.id, n.org_id INTO v_user, v_home
    FROM public.noctus_users n
    JOIN public.org_memberships m ON m.user_id = n.id AND m.org_id = n.org_id AND m.status = 'active'
   LIMIT 1;
  IF v_user IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no profile with an active home membership to borrow';
  END IF;
  SELECT o.id INTO v_other FROM public.organizations o WHERE o.id <> v_home LIMIT 1;
  IF v_other IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no second organization';
  END IF;
  -- a plain member at home (the last-owner refusal is not what this probe judges), a viewer elsewhere
  UPDATE public.org_memberships SET org_role = 'member' WHERE user_id = v_user AND org_id = v_home;
  INSERT INTO public.org_memberships (user_id, org_id, org_role, status)
  VALUES (v_user, v_other, 'viewer', 'active')
  ON CONFLICT (user_id, org_id) DO UPDATE SET org_role = 'viewer', status = 'active', ended_at = NULL;
  BEGIN
    PERFORM public.team_member_remove(v_home, v_user);
    SET CONSTRAINTS public.org_memberships_profile_org_active IMMEDIATE;
  EXCEPTION WHEN OTHERS THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: removing the member raised: %', SQLERRM;
  END;
  SELECT n.org_id, n.org_role INTO v_after, v_arole FROM public.noctus_users n WHERE n.id = v_user;
  IF v_after IS NOT DISTINCT FROM v_other AND v_arole = 'viewer'
     AND EXISTS (SELECT 1 FROM public.org_memberships m
                  WHERE m.user_id = v_user AND m.org_id = v_home AND m.status = 'removed' AND m.ended_at IS NOT NULL) THEN
    RAISE EXCEPTION 'NOC_PROBE:clean: the profile moved to the other membership with its role and the home membership ended';
  END IF;
  RAISE EXCEPTION 'NOC_PROBE:violation: profile org=% role=% (expected % / viewer) after removal from the profile org', v_after, v_arole, v_other;
END;
"""),
)

_TEAM_ACCEPT_ACTIVE_MEMBER_PROBE = GuardProbe(
    id="team_invitation_accept.refuses_an_active_member",
    product="core",
    schema="public",
    guard_name="team_invitation_accept",
    kind="write_refusal",
    migrations=_TEAM_OPS_MIGRATIONS,
    rationale=(
        "Accepting an invitation must not re-link or re-role a membership that is already ACTIVE "
        "(replays stay refused); the activation is conditional on removed/invited rows only."
    ),
    sql=_do_block("""
DECLARE
  v_user  uuid;
  v_home  uuid;
  v_email text;
  v_inv   uuid;
BEGIN
  IF to_regprocedure('public.team_invitation_accept(uuid,uuid)') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: public.team_invitation_accept missing — core 082 not applied';
  END IF;
  SELECT n.id, n.org_id, au.email INTO v_user, v_home, v_email
    FROM public.noctus_users n
    JOIN auth.users au ON au.id = n.id
    JOIN public.org_memberships m ON m.user_id = n.id AND m.org_id = n.org_id AND m.status = 'active'
   WHERE au.email IS NOT NULL
   LIMIT 1;
  IF v_user IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no profile with an auth email and an active home membership';
  END IF;
  INSERT INTO public.invitations (org_id, email, role, invited_by, token)
  VALUES (v_home, v_email, 'member', v_user, 'noc-probe-' || gen_random_uuid()::text)
  RETURNING id INTO v_inv;
  BEGIN
    PERFORM public.team_invitation_accept(v_inv, v_user);
    RAISE EXCEPTION 'NOC_PROBE:permitted: accepting an invitation into an org the user is already an active member of succeeded — the refusal did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE 'team_membership:already_member%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
)

_TEAM_OPS_PROBES: tuple[GuardProbe, ...] = (
    _TEAM_REMOVE_LAST_OWNER_PROBE,
    _TEAM_SET_ROLE_LAST_OWNER_PROBE,
    _TEAM_REMOVE_MOVES_PROFILE_PROBE,
    _TEAM_ACCEPT_ACTIVE_MEMBER_PROBE,
)



def _picker_constraint_probe(*, probe_id: str, guard_name: str, rationale: str, declare: str, steps: str, what: str) -> GuardProbe:
    return GuardProbe(
        id=probe_id, product="core", schema="public", guard_name=guard_name, kind="write_refusal",
        migrations=_ORG_PICKER_MIGRATIONS, rationale=rationale,
        sql=_do_block(f"""
DECLARE
{declare}
BEGIN
  BEGIN
{steps}
    RAISE EXCEPTION 'NOC_PROBE:permitted: {what} succeeded — the {guard_name} guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{guard_name}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
    )


_ORG_PICKER_DB_SCHEMA_UNIQUE_PROBE = _picker_constraint_probe(
    probe_id="products.db_schema.unique",
    guard_name="products_db_schema_key",
    rationale=(
        "current_org_id_for(p_schema) resolves the product FROM db_schema; two products sharing "
        "one schema would make a staff selection for one silently apply to the other."
    ),
    declare="  v_a uuid; v_b uuid; v_schema text;",
    steps="""    SELECT id, db_schema INTO v_a, v_schema FROM public.products WHERE db_schema IS NOT NULL LIMIT 1;
    SELECT id INTO v_b FROM public.products WHERE id <> v_a LIMIT 1;
    IF v_a IS NULL OR v_b IS NULL THEN
      RAISE EXCEPTION 'NOC_PROBE:no_fixture: needs two products rows, one with a db_schema';
    END IF;
    UPDATE public.products SET db_schema = v_schema WHERE id = v_b;""",
    what="giving two products the same db_schema",
)

_ORG_PICKER_READY_NEEDS_SCHEMA_PROBE = _picker_constraint_probe(
    probe_id="products.org_picker_ready.needs_db_schema",
    guard_name="products_org_picker_ready_needs_schema",
    rationale="A product flagged picker-ready must name its schema, else the RPC/helper cannot resolve it.",
    declare="  v_a uuid;",
    steps="""    SELECT id INTO v_a FROM public.products LIMIT 1;
    IF v_a IS NULL THEN
      RAISE EXCEPTION 'NOC_PROBE:no_fixture: needs one products row';
    END IF;
    UPDATE public.products SET db_schema = NULL, org_picker_ready = true WHERE id = v_a;""",
    what="marking a product org_picker_ready with no db_schema",
)

_ORG_PICKER_ENDED_PAIR_PROBE = _picker_constraint_probe(
    probe_id="platform_org_selections.ended_pair.check",
    guard_name="platform_org_selections_ended_pair",
    rationale="A selection is live (no ended_at, no ended_by) or ended (both): half-ended rows would be neither.",
    declare="  v_staff uuid; v_home uuid; v_pid uuid; v_org uuid;",
    steps="""    SELECT u.id, u.org_id INTO v_staff, v_home FROM public.noctus_users u LIMIT 1;
    SELECT id INTO v_pid FROM public.products LIMIT 1;
    SELECT id INTO v_org FROM public.organizations LIMIT 1;
    IF v_staff IS NULL OR v_pid IS NULL OR v_org IS NULL THEN
      RAISE EXCEPTION 'NOC_PROBE:no_fixture: needs one noctus_users, products and organizations row';
    END IF;
    INSERT INTO public.platform_org_selections
      (user_id, product_id, target_org_id, home_org_id, auth_session_id, ended_at, ended_by)
    VALUES (v_staff, v_pid, v_org, v_home, gen_random_uuid(), now(), NULL);""",
    what="inserting a selection with ended_at set but no ended_by",
)

# core 072 -- public.audit_acting_write(): a write the BROWSER sends to PostgREST while acting
# must leave exactly one audit row in the TARGET org; nobody else's write leaves any. The probe
# table lives in the fixture product's own schema (so current_org_id_for(v_schema) resolves) and
# is created + written as `authenticated` inside the rolled-back transaction.
_ACTING_AUDIT_DECLARE = _ORG_PICKER_DECLARE + "  v_n int; v_rid uuid; v_acting uuid; v_role text; v_tag uuid;\n"

_ACTING_AUDIT_SETUP = """
  IF to_regprocedure('public.audit_acting_write()') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: public.audit_acting_write() missing — core 072 not applied';
  END IF;
  EXECUTE format('CREATE TABLE %I.noc_probe_acting_audit (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid)', v_schema);
  EXECUTE format('GRANT INSERT ON %I.noc_probe_acting_audit TO authenticated', v_schema);
  EXECUTE format('GRANT USAGE ON SCHEMA %I TO authenticated', v_schema);
  EXECUTE format('CREATE TRIGGER audit_acting_write AFTER INSERT OR UPDATE OR DELETE ON %I.noc_probe_acting_audit '
                 'FOR EACH ROW EXECUTE FUNCTION public.audit_acting_write(%L)', v_schema, v_schema);
"""


def _acting_audit_probe(*, probe_id: str, rationale: str, caller: str, org: str, verdict: str) -> GuardProbe:
    """INSERT one probe row as ``authenticated`` with the caller forged by ``caller`` (after a live
    selection for v_staff exists), then hand the audit rows written for it to ``verdict``."""
    steps = _ACTING_AUDIT_SETUP + """
  PERFORM public.platform_org_selection_set(v_staff, v_slug, v_target, v_sid);
  SELECT s.id INTO v_sel FROM public.platform_org_selections s
   WHERE s.user_id = v_staff AND s.product_id = v_pid AND s.ended_at IS NULL;
""" + caller + f"""
  v_rid := gen_random_uuid();
  SET LOCAL ROLE authenticated;
  EXECUTE format('INSERT INTO %I.noc_probe_acting_audit (id, org_id) VALUES ($1, $2)', v_schema) USING v_rid, {org};
  RESET ROLE;
  SELECT count(*), max(a.org_id::text)::uuid, max(a.acting_org_id::text)::uuid, max(a.role), max(a.act_as_session_id::text)::uuid
    INTO v_n, v_got, v_acting, v_role, v_tag
    FROM public.audit_logs a
   WHERE a.resource_type = v_schema || '.noc_probe_acting_audit' AND a.resource_id = v_rid::text;
""" + verdict
    return GuardProbe(
        id=probe_id,
        product="core",
        schema="public",
        guard_name="audit_acting_write",
        kind="state_assertion",
        migrations=_ORG_PICKER_MIGRATIONS + ("072_audit_acting_write.sql",),
        rationale=rationale,
        sql=_do_block(_ACTING_AUDIT_DECLARE + "BEGIN\n" + _ORG_PICKER_FIXTURE + steps + "\nEND;\n"),
    )


_ACTING_AUDIT_ACTING_WRITE_PROBE = _acting_audit_probe(
    probe_id="audit_acting_write.acting_postgrest_write_is_audited_in_target",
    rationale=(
        "A staff member acting in another org who writes straight through PostgREST must leave "
        "exactly ONE audit row, client-visible in the TARGET org and tagged platform_support with "
        "the home org + the live selection -- otherwise the client cannot see who changed their data."
    ),
    caller=_caller_sql("v_staff::text"),
    org="v_target",
    verdict="""
  IF v_n = 1 AND v_got = v_target AND v_acting = v_home AND v_role = 'platform_support' AND v_tag = v_sel THEN
    RAISE EXCEPTION 'NOC_PROBE:clean: one acting audit row (org=target, acting=home, platform_support, selection id)';
  END IF;
  RAISE EXCEPTION 'NOC_PROBE:violation: acting write audit rows=% org=% acting=% role=% selection=% (expected 1 / % / % / platform_support / %)',
    v_n, v_got, v_acting, v_role, v_tag, v_target, v_home, v_sel;""",
)

_ACTING_AUDIT_PLAIN_WRITE_PROBE = _acting_audit_probe(
    probe_id="audit_acting_write.non_acting_write_writes_nothing",
    rationale=(
        "Control: an ordinary user writing in their own org is not acting -- the trigger must stay "
        "silent (no audit noise, and the positive probe above is not vacuous)."
    ),
    caller=_caller_sql("v_plain::text"),
    org="v_plain_home",
    verdict="""
  IF v_n = 0 THEN
    RAISE EXCEPTION 'NOC_PROBE:clean: a non-acting write wrote no acting audit row';
  END IF;
  RAISE EXCEPTION 'NOC_PROBE:violation: a non-acting write wrote % acting audit row(s)', v_n;""",
)


_ORG_PICKER_PROBES: tuple[GuardProbe, ...] = (
    _ORG_PICKER_DB_SCHEMA_UNIQUE_PROBE,
    _ORG_PICKER_READY_NEEDS_SCHEMA_PROBE,
    _ORG_PICKER_ENDED_PAIR_PROBE,
    _ORG_PICKER_ONE_LIVE_PROBE,
    _ORG_PICKER_SET_UNLICENSED_PROBE,
    _ORG_PICKER_SET_NOT_READY_PROBE,
    _ORG_PICKER_HELPER_POSITIVE_PROBE,
    _ORG_PICKER_HELPER_NON_STAFF_PROBE,
    _ORG_PICKER_HELPER_SESSION_PROBE,
    _ORG_PICKER_HELPER_AAL1_PROBE,
    _ORG_PICKER_HELPER_AAL1_OPTIONAL_PROBE,
    _ORG_PICKER_HELPER_LICENSE_PROBE,
    _ORG_PICKER_HELPER_HEADER_PROBE,
    _ORG_PICKER_HELPER_HEADER_MATCH_PROBE,
    _ORG_PICKER_REVOKE_PROBE,
    _ORG_PICKER_HELPER_STALE_HEADER_PROBE,
    _ORG_PICKER_HELPER_SESSION_GONE_PROBE,
    _ORG_PICKER_HELPER_NOT_READY_PROBE,
    _ORG_PICKER_HELPER_STAFF_ROLE_PROBE,
    _ORG_PICKER_HELPER_NO_SELECTION_PROBE,
    _ORG_PICKER_HELPER_NO_SELECTION_AAL1_OPTIONAL_PROBE,
    _ORG_PICKER_HELPER_NO_SELECTION_AAL1_REQUIRED_PROBE,
    _ORG_PICKER_PRODUCT_REVOKE_PROBE,
    *_ORG_MEMBER_PROBES,
    *_TEAM_OPS_PROBES,
    *_ACCESS_RULES_PROBES,
    *_OWNER_GRANT_RULES_PROBES,
    _ACTING_AUDIT_ACTING_WRITE_PROBE,
    _ACTING_AUDIT_PLAIN_WRITE_PROBE,
)


_CERTIDAO_CONSULTA_ORIGEM_PROBE = GuardProbe(
    id="certidao_consultas.origem.closed_vocabulary",
    product="social-wiring",
    schema="social_wiring",
    guard_name="certidao_consultas_origem_check",
    kind="write_refusal",
    migrations=("147_certidoes_origem_manual.sql",),
    rationale=(
        "`origem` decides whether a consulta is billable InfoSimples work "
        "or a manual registration that must never be billed or re-fetched; "
        "a value outside the two the code branches on would be treated as "
        "neither, silently."
    ),
    sql=_do_block("""
DECLARE
  alvo uuid;
BEGIN
  SELECT id INTO alvo FROM social_wiring.certidao_consultas LIMIT 1;
  IF alvo IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: social_wiring.certidao_consultas has no row to probe';
  END IF;
  BEGIN
    UPDATE social_wiring.certidao_consultas SET origem = 'noc_probe_invalida' WHERE id = alvo;
    RAISE EXCEPTION 'NOC_PROBE:permitted: origem accepted a value outside automatica|manual';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%certidao_consultas_origem_check%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
)



_CERTIDAO_CONSULTA_DOCUMENTO_PROBE = GuardProbe(
    id="certidao_consultas.documento.required_for_automatica",
    product="social-wiring",
    schema="social_wiring",
    guard_name="certidao_consultas_documento_automatica_check",
    kind="write_refusal",
    migrations=("307_certidao_consulta_manual_sem_documento.sql",),
    rationale=(
        "Migration 307 relaxed `documento` NOT NULL so a MANUAL cell holder "
        "can exist for a party known only by name (F86); an AUTOMATIC "
        "consulta is billed InfoSimples work whose CPF/CNPJ is the API "
        "parameter — one without it would be dispatched with nothing to look up."
    ),
    sql=_do_block("""
DECLARE
  alvo uuid;
BEGIN
  SELECT id INTO alvo FROM social_wiring.certidao_consultas WHERE origem = 'automatica' LIMIT 1;
  IF alvo IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: social_wiring.certidao_consultas has no automatica row to probe';
  END IF;
  BEGIN
    UPDATE social_wiring.certidao_consultas SET documento = NULL WHERE id = alvo;
    RAISE EXCEPTION 'NOC_PROBE:permitted: an automatica consulta accepted a NULL documento';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%certidao_consultas_documento_automatica_check%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
)

# ---------------------------------------------------------------------------
# Registry — agents Agent Studio (migrations 012 + 013).
# ---------------------------------------------------------------------------
#
# Fully self-provisioning: `agents.agents.org_id` has no FK, so every probe
# fabricates its own org id, agent, version(s) and children inside the
# rolled-back transaction — no production row is borrowed or touched. The
# only `no_fixture` path is "the migration is not applied" (to_regclass).
# Setup statements live INSIDE the classified sub-block on purpose: a setup
# failure surfaces as `ambiguous` (its SQLERRM never carries the guard's
# fragment), never as a false `refused`.

_AGENTS_SCHEMA = "agents"
_AGENTS_STUDIO_MIGRATIONS = ("012_agent_studio_definitions.sql",)
_AGENTS_KE_MIGRATIONS = ("013_agent_studio_knowledge_evals.sql",)
_AGENTS_PROBE_AGENT_SQL = (
    f"INSERT INTO {_AGENTS_SCHEMA}.agents (org_id, key, nome, runtime, definition_mode) "
    "VALUES (v_org, 'noc-probe', 'NOC probe', 'claude_sdk', 'studio') RETURNING id INTO v_agent;"
)


def _agents_version_sql(status: str, versao: int, into: str) -> str:
    return (
        f"INSERT INTO {_AGENTS_SCHEMA}.agent_versions "
        "(org_id, agent_id, versao, status, model, effort, created_by) "
        f"VALUES (v_org, v_agent, {versao}, '{status}', 'claude-opus-5', 'high', v_org) "
        f"RETURNING id INTO {into};"
    )


def _agents_studio_probe(
    *, probe_id: str, guard_name: str, attack_sql: str, guard_fragment: str, what: str, rationale: str,
    migrations: tuple[str, ...] = _AGENTS_STUDIO_MIGRATIONS, requires_table: str | None = None,
) -> GuardProbe:
    fragment_lit = _sql_lit(guard_fragment)
    what_lit = _sql_lit(what)
    extra_fixture = (
        f"""
  IF to_regclass('{_AGENTS_SCHEMA}.{requires_table}') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: {_AGENTS_SCHEMA}.{requires_table} does not exist ({migrations[0]} not applied)';
  END IF;"""
        if requires_table
        else ""
    )
    sql = _do_block(f"""
DECLARE
  v_org uuid := gen_random_uuid();
  v_agent uuid;
  v_version uuid;
  v_version2 uuid;
  v_skill uuid;
  v_file uuid;
  v_client uuid;
  v_case uuid;
  v_run uuid;
BEGIN
  IF to_regclass('{_AGENTS_SCHEMA}.agent_versions') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: {_AGENTS_SCHEMA}.agent_versions does not exist (migration 012 not applied)';
  END IF;{extra_fixture}
  BEGIN
    {_AGENTS_PROBE_AGENT_SQL}
{attack_sql}
    RAISE EXCEPTION 'NOC_PROBE:permitted: {what_lit} succeeded — the guard under test did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{fragment_lit}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
""")
    return GuardProbe(
        id=probe_id,
        product="agents",
        schema=_AGENTS_SCHEMA,
        guard_name=guard_name,
        kind="write_refusal",
        migrations=migrations,
        sql=sql,
        rationale=rationale,
    )


_AGENTS_STUDIO_PROBES: tuple[GuardProbe, ...] = (
    _agents_studio_probe(
        probe_id="agent_versions.one_ativa_per_agent",
        guard_name="agent_versions_one_ativa_idx",
        attack_sql=(
            f"    {_agents_version_sql('ativa', 1, 'v_version')}\n"
            f"    {_agents_version_sql('ativa', 2, 'v_version2')}"
        ),
        guard_fragment="agent_versions_one_ativa_idx",
        what="a second ativa version for the same agent",
        rationale=(
            "At most one published (ativa) version per agent (Agent Studio §A3): "
            "two would make 'the version a new conversation runs' ambiguous."
        ),
    ),
    _agents_studio_probe(
        probe_id="agent_versions.one_rascunho_per_agent",
        guard_name="agent_versions_one_rascunho_idx",
        attack_sql=(
            f"    {_agents_version_sql('rascunho', 1, 'v_version')}\n"
            f"    {_agents_version_sql('rascunho', 2, 'v_version2')}"
        ),
        guard_fragment="agent_versions_one_rascunho_idx",
        what="a second rascunho version for the same agent",
        rationale=(
            "Exactly one draft per agent (§A3) — two drafts would split edits "
            "and let the eval gate judge one while another is published."
        ),
    ),
    _agents_studio_probe(
        probe_id="agent_versions.published_is_immutable",
        guard_name="guard_agent_version_immutable",
        attack_sql=(
            f"    {_agents_version_sql('ativa', 1, 'v_version')}\n"
            f"    UPDATE {_AGENTS_SCHEMA}.agent_versions SET model = 'claude-sonnet-5' WHERE id = v_version;"
        ),
        guard_fragment="version_immutable",
        what="UPDATE of a published version's model",
        rationale=(
            "A published version is immutable (§A3/§H3): conversations and "
            "compiled_prompts point at it as proof of what ran."
        ),
    ),
    _agents_studio_probe(
        probe_id="agent_prompt_sections.published_parent_is_immutable",
        guard_name="guard_version_child_immutable",
        attack_sql=(
            f"    {_agents_version_sql('ativa', 1, 'v_version')}\n"
            f"    INSERT INTO {_AGENTS_SCHEMA}.agent_prompt_sections (org_id, version_id, chave, titulo, ordem, conteudo) "
            "VALUES (v_org, v_version, 'noc-probe', 'NOC probe', 1, 'x');"
        ),
        guard_fragment="version_immutable",
        what="INSERT of a prompt section into a published version",
        rationale=(
            "Sections/skills of a published version are frozen with it (§B1) — "
            "otherwise the published prompt text silently changes."
        ),
    ),
    _agents_studio_probe(
        probe_id="agent_skill_files.published_parent_is_immutable",
        guard_name="guard_skill_file_immutable",
        attack_sql=(
            f"    {_agents_version_sql('rascunho', 1, 'v_version')}\n"
            f"    INSERT INTO {_AGENTS_SCHEMA}.agent_skills (org_id, version_id, nome, descricao, corpo) "
            "VALUES (v_org, v_version, 'noc-probe', 'NOC probe', 'x') RETURNING id INTO v_skill;\n"
            f"    INSERT INTO {_AGENTS_SCHEMA}.agent_skill_files (org_id, skill_id, caminho, conteudo) "
            "VALUES (v_org, v_skill, 'noc-probe.md', 'x') RETURNING id INTO v_file;\n"
            f"    UPDATE {_AGENTS_SCHEMA}.agent_versions SET status = 'ativa' WHERE id = v_version;\n"
            f"    UPDATE {_AGENTS_SCHEMA}.agent_skill_files SET conteudo = 'changed' WHERE id = v_file;"
        ),
        guard_fragment="version_immutable",
        what="UPDATE of a skill file whose version was published",
        rationale=(
            "Skill reference files are part of the published version (§B1); "
            "they are reached through agent_skills, so they carry their own guard."
        ),
    ),
    _agents_studio_probe(
        probe_id="compiled_prompts.write_once",
        guard_name="guard_compiled_prompt_immutable",
        attack_sql=(
            f"    {_agents_version_sql('ativa', 1, 'v_version')}\n"
            f"    INSERT INTO {_AGENTS_SCHEMA}.compiled_prompts (org_id, hash, version_id, texto, manifest) "
            "VALUES (v_org, 'sha256:' || repeat('0', 64), v_version, 'x', '[]'::jsonb);\n"
            f"    UPDATE {_AGENTS_SCHEMA}.compiled_prompts SET texto = 'changed' WHERE org_id = v_org;"
        ),
        guard_fragment="compiled_prompt_immutable",
        what="UPDATE of a stored compiled prompt",
        rationale=(
            "compiled_prompts is the proof-of-use record (§A7): the exact text a "
            "turn ran with must never be rewritten after the fact."
        ),
    ),
    _agents_studio_probe(
        probe_id="agent_versions.published_delete_refused",
        guard_name="guard_agent_version_immutable",
        attack_sql=(
            f"    {_agents_version_sql('ativa', 1, 'v_version')}\n"
            f"    DELETE FROM {_AGENTS_SCHEMA}.agent_versions WHERE id = v_version;"
        ),
        guard_fragment="version_immutable",
        what="DELETE of a published version",
        rationale=(
            "Only a draft may be deleted (discard) — a published version is the "
            "proof of what conversations ran; deleting it erases history."
        ),
    ),
    _agents_studio_probe(
        probe_id="agent_versions.substituida_to_ativa_refused",
        guard_name="guard_agent_version_immutable",
        attack_sql=(
            f"    {_agents_version_sql('substituida', 1, 'v_version')}\n"
            f"    UPDATE {_AGENTS_SCHEMA}.agent_versions SET status = 'ativa' WHERE id = v_version;"
        ),
        guard_fragment="version_immutable",
        what="UPDATE of a superseded version back to ativa",
        rationale=(
            "Re-activation must go through a new draft + publish (eval gate, audit); "
            "flipping substituida -> ativa would bypass both."
        ),
    ),
    _agents_studio_probe(
        probe_id="agent_prompt_sections.child_delete_under_published_parent",
        guard_name="guard_version_child_immutable",
        attack_sql=(
            f"    {_agents_version_sql('rascunho', 1, 'v_version')}\n"
            f"    INSERT INTO {_AGENTS_SCHEMA}.agent_prompt_sections (org_id, version_id, chave, titulo, ordem, conteudo) "
            "VALUES (v_org, v_version, 'noc-probe', 'NOC probe', 1, 'x');\n"
            f"    UPDATE {_AGENTS_SCHEMA}.agent_versions SET status = 'ativa' WHERE id = v_version;\n"
            f"    DELETE FROM {_AGENTS_SCHEMA}.agent_prompt_sections WHERE version_id = v_version;"
        ),
        guard_fragment="version_immutable",
        what="DELETE of a section of a published version",
        rationale=(
            "Removing a section silently changes the published prompt exactly like "
            "an edit would — the child guard must refuse DELETE too."
        ),
    ),
    _agents_studio_probe(
        probe_id="compiled_prompts.delete_refused",
        guard_name="guard_compiled_prompt_immutable",
        attack_sql=(
            f"    {_agents_version_sql('ativa', 1, 'v_version')}\n"
            f"    INSERT INTO {_AGENTS_SCHEMA}.compiled_prompts (org_id, hash, version_id, texto, manifest) "
            "VALUES (v_org, 'sha256:' || repeat('0', 64), v_version, 'x', '[]'::jsonb);\n"
            f"    DELETE FROM {_AGENTS_SCHEMA}.compiled_prompts WHERE org_id = v_org;"
        ),
        guard_fragment="compiled_prompt_immutable",
        what="DELETE of a stored compiled prompt outside erase_compiled_prompts",
        rationale=(
            "Proof-of-use rows are write-once (§A7); the ONLY deletion path is the "
            "service_role LGPD erasure function `agents.erase_compiled_prompts`."
        ),
    ),
    _agents_studio_probe(
        probe_id="agents.publicacao_limiar_floor",
        guard_name="agents_publicacao_limiar_floor",
        attack_sql=f"    UPDATE {_AGENTS_SCHEMA}.agents SET publicacao_limiar = 0.1 WHERE id = v_agent;",
        guard_fragment="agents_publicacao_limiar_floor",
        what="UPDATE of publicacao_limiar below the 0.5 floor",
        rationale=(
            "A threshold of 0.1 makes the publish eval gate decorative (wave-1 "
            "security review H2) — the floor holds whatever the write path."
        ),
    ),
    _agents_studio_probe(
        probe_id="agent_versions.override_reason_len",
        guard_name="agent_versions_override_reason_len",
        attack_sql=(
            f"    INSERT INTO {_AGENTS_SCHEMA}.agent_versions "
            "(org_id, agent_id, versao, status, model, effort, created_by, publish_override_reason) "
            "VALUES (v_org, v_agent, 1, 'ativa', 'claude-opus-5', 'high', v_org, '   curto      ');"
        ),
        guard_fragment="agent_versions_override_reason_len",
        what="a publish override reason under 20 chars once trimmed",
        rationale=(
            "Bypassing the eval gate must carry a real, reviewable reason (L1) — "
            "whitespace padding must not satisfy it."
        ),
    ),
    _agents_studio_probe(
        probe_id="agent_audit_log.append_only",
        guard_name="guard_audit_log_append_only",
        attack_sql=(
            f"    INSERT INTO {_AGENTS_SCHEMA}.agent_audit_log (org_id, agent_id, acao) "
            "VALUES (v_org, v_agent, 'publicado');\n"
            f"    UPDATE {_AGENTS_SCHEMA}.agent_audit_log SET acao = 'publicado_override' WHERE agent_id = v_agent;"
        ),
        guard_fragment="audit_log_append_only",
        what="UPDATE of an audit log row",
        rationale=(
            "The governance audit trail (threshold changes, publishes, overrides, "
            "discards) is append-only — a rewritable log proves nothing."
        ),
    ),
    _agents_studio_probe(
        probe_id="agent_audit_log.agent_id_null_needs_the_delete_rpc",
        guard_name="guard_audit_log_append_only",
        migrations=("012_agent_studio_definitions.sql", "048_agent_lifecycle_delete.sql"),
        attack_sql=(
            f"    INSERT INTO {_AGENTS_SCHEMA}.agent_audit_log (org_id, agent_id, acao) "
            "VALUES (v_org, v_agent, 'publicado');\n"
            f"    UPDATE {_AGENTS_SCHEMA}.agent_audit_log SET agent_id = NULL WHERE agent_id = v_agent;"
        ),
        guard_fragment="audit_log_append_only",
        what="UPDATE of an audit row's agent_id to NULL outside agents.excluir_agente",
        rationale=(
            "048 lets the audit log lose exactly one thing -- agent_id -> NULL -- and only while the transaction-local "
            "flag agents.agent_delete is on (set by the deletion RPC around its DELETE). Without the flag the "
            "carve-out must not open: a caller that can reach the table cannot unlink the trail from its agent."
        ),
    ),
    _agents_studio_probe(
        probe_id="agent_audit_log.identifica_agente",
        guard_name="agent_audit_log_identifica_agente",
        migrations=("012_agent_studio_definitions.sql", "048_agent_lifecycle_delete.sql"),
        attack_sql=(
            f"    INSERT INTO {_AGENTS_SCHEMA}.agent_audit_log (org_id, agent_id, acao) "
            "VALUES (v_org, NULL, 'agente_criado');"
        ),
        guard_fragment="agent_audit_log_identifica_agente",
        what="an audit row naming no agent (agent_id NULL and agent_key NULL)",
        rationale=(
            "048 makes agent_id nullable so the trail outlives a deleted agent; the CHECK keeps that from becoming "
            "an anonymous row: a row without an agent_id must carry the agent_key snapshot."
        ),
    ),
    _agents_studio_probe(
        probe_id="agent_audit_log.delete_refused",
        guard_name="guard_audit_log_append_only",
        migrations=("012_agent_studio_definitions.sql", "048_agent_lifecycle_delete.sql"),
        attack_sql=(
            f"    INSERT INTO {_AGENTS_SCHEMA}.agent_audit_log (org_id, agent_id, acao) "
            "VALUES (v_org, v_agent, 'publicado');\n"
            f"    DELETE FROM {_AGENTS_SCHEMA}.agent_audit_log WHERE agent_id = v_agent;"
        ),
        guard_fragment="audit_log_append_only",
        what="DELETE of an audit log row",
        rationale=(
            "The carve-out of 048 is an UPDATE of agent_id only; a DELETE stays refused under every flag state "
            "(deleting an agent unlinks its audit rows, it never removes them)."
        ),
    ),
    _agents_studio_probe(
        probe_id="agent_client_entries.active_cap",
        guard_name="guard_client_entry_cap",
        attack_sql=(
            f"    INSERT INTO {_AGENTS_SCHEMA}.agent_clients (org_id, agent_id, slug, nome) "
            "VALUES (v_org, v_agent, 'noc-probe', 'NOC probe') RETURNING id INTO v_client;\n"
            f"    INSERT INTO {_AGENTS_SCHEMA}.agent_client_entries (org_id, client_id, tipo, titulo) "
            "SELECT v_org, v_client, 'nota', 'n' || g FROM generate_series(1, 200) AS g;\n"
            f"    INSERT INTO {_AGENTS_SCHEMA}.agent_client_entries (org_id, client_id, tipo, titulo) "
            "VALUES (v_org, v_client, 'nota', 'overflow');"
        ),
        guard_fragment="client_entries_cap",
        what="a 201st active entry on one client",
        rationale=(
            "The client brain is compiled into every bound turn (a live, ungated "
            "prompt input) — capped at 200 active entries (M3)."
        ),
    ),
    _agents_studio_probe(
        probe_id="agents.eval_runs.one_active_per_version",
        guard_name="eval_runs_one_active_per_version_idx",
        migrations=_AGENTS_KE_MIGRATIONS,
        requires_table="eval_runs",
        attack_sql=(
            f"    {_agents_version_sql('rascunho', 1, 'v_version')}\n"
            f"    INSERT INTO {_AGENTS_SCHEMA}.eval_runs (org_id, agent_id, version_id, compiled_hash, status, limiar, started_by) "
            "VALUES (v_org, v_agent, v_version, 'sha256:noc-probe-1', 'pendente', 0.8, v_org);\n"
            f"    INSERT INTO {_AGENTS_SCHEMA}.eval_runs (org_id, agent_id, version_id, compiled_hash, status, limiar, started_by) "
            "VALUES (v_org, v_agent, v_version, 'sha256:noc-probe-2', 'executando', 0.8, v_org);"
        ),
        guard_fragment="eval_runs_one_active_per_version_idx",
        what="a second pendente/executando eval_runs row for the same version_id",
        rationale=(
            "At most one `pendente`/`executando` eval run per version — "
            "`POST .../evals/runs` maps a second concurrent request into 409 "
            "`run_in_progress` (contract §D4). Without this partial unique "
            "index two runs could race: both write `eval_results` for the "
            "same version, and the publish gate would read whichever finished "
            "last as the answer, silently discarding the other run's verdict."
        ),
    ),
    _agents_studio_probe(
        probe_id="eval_results.status_check",
        guard_name="eval_results_status_check",
        migrations=(*_AGENTS_KE_MIGRATIONS, "014_agent_studio_cost.sql"),
        requires_table="eval_results",
        attack_sql=(
            f"    {_agents_version_sql('ativa', 1, 'v_version')}\n"
            f"    INSERT INTO {_AGENTS_SCHEMA}.eval_cases (org_id, agent_id, slug, titulo, entrada, criterios) "
            "VALUES (v_org, v_agent, 'noc-probe', 'NOC probe', 'entrada', '{\"deve\": [\"x\"]}'::jsonb) "
            "RETURNING id INTO v_case;\n"
            f"    INSERT INTO {_AGENTS_SCHEMA}.eval_runs (org_id, agent_id, version_id, compiled_hash, status, limiar, started_by) "
            "VALUES (v_org, v_agent, v_version, 'sha256:noc-probe', 'pendente', 0.8, v_org) "
            "RETURNING id INTO v_run;\n"
            f"    INSERT INTO {_AGENTS_SCHEMA}.eval_results (org_id, run_id, case_id, status) "
            "VALUES (v_org, v_run, v_case, 'lixo');"
        ),
        guard_fragment="eval_results_status_check",
        what="an eval_results row with a status outside the CHECK's allowlist",
        rationale=(
            "Contract §L: `'pulado'` (the cost-cap skip status) joins "
            "pendente/aprovado/reprovado/erro — the CHECK must still reject "
            "anything outside that fixed set, including a typo that would "
            "otherwise silently corrupt the run's aprovados/score math."
        ),
    ),
    _agents_studio_probe(
        probe_id="eval_runs.modelo_geracao_allowlist",
        guard_name="eval_runs_modelo_geracao_check",
        migrations=(*_AGENTS_KE_MIGRATIONS, "014_agent_studio_cost.sql"),
        requires_table="eval_runs",
        attack_sql=(
            f"    {_agents_version_sql('ativa', 1, 'v_version')}\n"
            f"    INSERT INTO {_AGENTS_SCHEMA}.eval_runs "
            "(org_id, agent_id, version_id, compiled_hash, status, limiar, started_by, modelo_geracao) "
            "VALUES (v_org, v_agent, v_version, 'sha256:noc-probe', 'pendente', 0.8, v_org, 'claude-opus-5');"
        ),
        guard_fragment="eval_runs_modelo_geracao_check",
        what="an eval run whose modelo_geracao is outside the cheaper-iteration allowlist",
        rationale=(
            "Contract §L: the cheaper-iteration override exists to let a run "
            "cost LESS than the version's own model, never more — the "
            "allowlist (claude-sonnet-5/claude-haiku-4-5) is deliberately "
            "narrower than `agent_versions.model`'s, and this CHECK is the "
            "only thing stopping a request from naming `claude-opus-5` here "
            "and defeating that intent."
        ),
    ),
    _agents_studio_probe(
        probe_id="eval_runs.limite_usd_cap",
        guard_name="eval_runs_limite_usd_check",
        migrations=(*_AGENTS_KE_MIGRATIONS, "014_agent_studio_cost.sql"),
        requires_table="eval_runs",
        attack_sql=(
            f"    {_agents_version_sql('ativa', 1, 'v_version')}\n"
            f"    INSERT INTO {_AGENTS_SCHEMA}.eval_runs "
            "(org_id, agent_id, version_id, compiled_hash, status, limiar, started_by, limite_usd) "
            "VALUES (v_org, v_agent, v_version, 'sha256:noc-probe', 'pendente', 0.8, v_org, 50.01);"
        ),
        guard_fragment="eval_runs_limite_usd_check",
        what="a run limite_usd above the $50 cap",
        rationale=(
            "Contract §L: the per-run cost cap only protects the org's "
            "wallet if it is itself bounded — an unbounded `limite_usd` "
            "would let one run authorize an unlimited Anthropic bill, the "
            "exact failure mode this feature exists to prevent."
        ),
    ),
    _agents_studio_probe(
        probe_id="agent_personas.model_allowlist",
        guard_name="agent_personas_model_check",
        migrations=("006_agents.sql", "015_haiku_model.sql"),
        attack_sql=(
            f"    INSERT INTO {_AGENTS_SCHEMA}.agent_personas "
            "(org_id, agent_id, versao, nome, papel, model, effort, created_by) "
            "VALUES (v_org, v_agent, 1, 'NOC probe', 'papel', 'claude-invalid-model', 'high', v_org);"
        ),
        guard_fragment="agent_personas_model_check",
        what="a Bia persona whose model is outside the allowlist",
        rationale=(
            "Contract §E.1: `agent_personas.model` is a closed vocabulary — "
            "widened by migration 015 to add `claude-haiku-4-5` alongside "
            "claude-opus-5/claude-sonnet-5 — and this CHECK is the only "
            "thing stopping a request from writing a value the runtime has "
            "no dispatch for."
        ),
    ),
    _agents_studio_probe(
        probe_id="agent_versions.model_allowlist",
        guard_name="agent_versions_model_check",
        migrations=("012_agent_studio_definitions.sql", "015_haiku_model.sql"),
        attack_sql=(
            f"    {_agents_version_sql('rascunho', 1, 'v_version')}\n"
            f"    UPDATE {_AGENTS_SCHEMA}.agent_versions SET model = 'claude-invalid-model' WHERE id = v_version;"
        ),
        guard_fragment="agent_versions_model_check",
        what="an agent_versions row whose model is outside the allowlist",
        rationale=(
            "Contract §A10/§B1: `agent_versions.model` is a closed "
            "vocabulary — widened by migration 015 to add "
            "`claude-haiku-4-5` alongside claude-opus-5/claude-sonnet-5 — "
            "and this CHECK is the only thing stopping a published version "
            "from carrying a model id the Claude Agent SDK runtime cannot "
            "launch."
        ),
    ),
    _agents_studio_probe(
        probe_id="agent_versions.provider_allowlist",
        guard_name="agent_versions_provider_check",
        migrations=("012_agent_studio_definitions.sql", "024_llm_provider_runtime.sql"),
        # A provider outside the allowlist ALSO fails agent_versions_model_check (the
        # model list is per provider), and Postgres reports that one first -- so the
        # probe drops model_check inside its always-rolled-back transaction to prove
        # provider_check on its own.
        attack_sql=(
            f"    {_agents_version_sql('rascunho', 1, 'v_version')}\n"
            f"    ALTER TABLE {_AGENTS_SCHEMA}.agent_versions DROP CONSTRAINT agent_versions_model_check;\n"
            f"    UPDATE {_AGENTS_SCHEMA}.agent_versions SET provider = 'noc-probe-vendor' WHERE id = v_version;"
        ),
        guard_fragment="agent_versions_provider_check",
        what="an agent_versions row whose provider is outside the allowlist",
        rationale=(
            "Lais A1 (migration 024): `provider` selects which key an `llm` turn "
            "resolves and which vendor it is billed to; this CHECK is the only "
            "thing stopping a version from naming a provider the runtime has no "
            "dispatch (or per-org key) for."
        ),
    ),
    _agents_studio_probe(
        probe_id="agent_versions.model_provider_pairing",
        guard_name="agent_versions_model_check",
        migrations=("012_agent_studio_definitions.sql", "024_llm_provider_runtime.sql"),
        attack_sql=(
            f"    {_agents_version_sql('rascunho', 1, 'v_version')}\n"
            f"    UPDATE {_AGENTS_SCHEMA}.agent_versions SET provider = 'openai' WHERE id = v_version;"
        ),
        guard_fragment="agent_versions_model_check",
        what="an openai version that still names an anthropic model",
        rationale=(
            "Lais A1 (migration 024): the model allowlist is PROVIDER-KEYED — a "
            "claude model under provider 'openai' (or the reverse) would be sent "
            "to the wrong vendor with the org's other vendor's key; the CHECK is "
            "what refuses the mismatched pair at the row."
        ),
    ),
    _agents_studio_probe(
        probe_id="agents.runtime_allowlist",
        guard_name="agents_runtime_check",
        migrations=("012_agent_studio_definitions.sql", "024_llm_provider_runtime.sql"),
        attack_sql=(
            f"    UPDATE {_AGENTS_SCHEMA}.agents SET runtime = 'noc-probe-runtime' WHERE id = v_agent;"
        ),
        guard_fragment="agents_runtime_check",
        what="an agents row whose runtime is outside claude_sdk/external/llm",
        rationale=(
            "Lais A1 (migration 024): `agents.runtime` selects which runtime runs "
            "the agent (`claude_sdk`, `external`, and now `llm`); this CHECK is "
            "the only thing stopping a typo from producing an agent no runtime "
            "dispatches."
        ),
    ),
    _agents_studio_probe(
        probe_id="conversations.channel_owner_identity",
        guard_name="conversations_channel_owner_check",
        migrations=("012_agent_studio_definitions.sql", "025_channel_conversations.sql"),
        requires_table="channel_inbound",
        attack_sql=(
            f"    INSERT INTO {_AGENTS_SCHEMA}.conversations (org_id, agent_id, owner_user_id) "
            "VALUES (v_org, v_agent, NULL);"
        ),
        guard_fragment="conversations_channel_owner_check",
        what="a user conversation (no channel) with no owner",
        rationale=(
            "Lais A2 (migration 025): `owner_user_id` became nullable ONLY for channel "
            "conversations; this CHECK is what keeps every user conversation owned — "
            "without it an ownerless row would be invisible to the owner-scoped routes "
            "and readable by no one, or (worse) matched by a null-owner lookup."
        ),
    ),
    # `conversations.channel_identity_unique` (uq_agents_conversations_channel_ref, migration 025) is retired:
    # migration 035 (Julia v2 M4) DROPS that per-agent index and replaces it with the per-thread identity
    # `uq_agents_threads_channel` (org, channel, channel_ref) WHERE tipo = 'thread_lead', probed below as
    # `conversations.one_thread_per_channel_ref`. Probing a guard a later migration removes on purpose fails
    # every DB that is past 035 (prod, 2026-10-21) while proving nothing.
    _agents_studio_probe(
        probe_id="channel_inbound.message_idempotency_unique",
        guard_name="uq_agents_channel_inbound_msg",
        migrations=("012_agent_studio_definitions.sql", "025_channel_conversations.sql"),
        requires_table="channel_inbound",
        attack_sql=(
            f"    INSERT INTO {_AGENTS_SCHEMA}.conversations (org_id, agent_id, channel, channel_ref) "
            "VALUES (v_org, v_agent, 'whatsapp', '{\"connection_id\": \"c\", \"chat_id\": \"x\"}'::jsonb) "
            "RETURNING id INTO v_version;\n"
            f"    INSERT INTO {_AGENTS_SCHEMA}.channel_inbound "
            "(org_id, connection_id, provider_message_id, conversation_id, texto_sha256) "
            "VALUES (v_org, v_org, 'wamid.noc-probe', v_version, repeat('a', 64));\n"
            f"    INSERT INTO {_AGENTS_SCHEMA}.channel_inbound "
            "(org_id, connection_id, provider_message_id, conversation_id, texto_sha256) "
            "VALUES (v_org, v_org, 'wamid.noc-probe', v_version, repeat('b', 64));"
        ),
        guard_fragment="uq_agents_channel_inbound_msg",
        what="the same (org, connection, provider_message_id) recorded twice",
        rationale=(
            "Lais A2 (migration 025, contract §10.1 M2): this UNIQUE is the idempotency "
            "key — without it a re-sent webhook batch would run a second model turn "
            "(and bill it) instead of replaying the stored reply."
        ),
    ),
)


# ---------------------------------------------------------------------------
# Registry — agents Julia v2 migrations 031–040 (A-CONT / A-QUAL / A-THREAD /
# A-EVAL / A-SKILLS / A-RT2). Every probe SELF-PROVISIONS its specimen (agent,
# version, standard, lead, thread, library skill) inside the rolled-back
# transaction -- no dependency on production holding any Julia row. A probe
# whose migration is not in agents' `schema_migrations` ledger yet is parked
# as `pending_migration` (never run, never a failure) until it is applied.
# Replaced the `_GUARD_PROBE_ALLOWLIST` entries that said "unapplied" (Julia
# v2 A-polish #12); proven on the real chain in
# `tests/test_agents_julia_v2_probes_on_replay.py`.
# ---------------------------------------------------------------------------

def _m(nn: str) -> str:
    return {
        "031": "031_julia_v2_conteudo.sql", "032": "032_julia_v2_qualificacao.sql",
        "037": "037_julia_v2_conformidade.sql", "044": "044_julia_v2_guardrails.sql",
        "033": "033_julia_v2_threads.sql", "034": "034_julia_v2_controles.sql",
        "035": "035_julia_v2_threads_constraints.sql", "038": "038_julia_v2_evals_roteiro.sql",
        "039": "039_julia_v2_skills_compartilhadas.sql", "040": "040_julia_v2_pin_catalogo.sql",
        "042": "042_julia_v2_lead_opt_out_eventos.sql", "043": "043_julia_v2_lead_reativacao.sql",
        "046": "046_julia_v2_proveniencia_canario.sql",
    }[nn]


_JV2 = _AGENTS_SCHEMA
#: Self-provisioning snippets (variables declared by `_julia_v2_probe`).
_JV2_AGENT = _AGENTS_PROBE_AGENT_SQL
_JV2_AGENT2 = (
    f"INSERT INTO {_JV2}.agents (org_id, key, nome, runtime, definition_mode) "
    "VALUES (v_org, 'noc-probe-2', 'NOC probe 2', 'claude_sdk', 'studio') RETURNING id INTO v_agent2;"
)
_JV2_VERSION = _agents_version_sql("rascunho", 1, "v_version")
#: The platform org is BORROWED, never inserted: creating an organizations row fires every product's org triggers
#: (licenses, ERP site config, ...), side effects a probe must not depend on. Runs BEFORE the classified block, so a
#: missing platform org is `no_fixture` (a failure to see), never `ambiguous`.
_JV2_PLAT_ORG_FIXTURE = """
  SELECT id INTO v_plat FROM public.organizations WHERE is_platform LIMIT 1;
  IF v_plat IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no organizations row has is_platform = true (core 068)';
  END IF;"""
_JV2_PADRAO = (
    f"INSERT INTO {_JV2}.qualificacao_padroes (chave, nome) VALUES ('noc-probe-' || v_sufixo, 'NOC probe') "
    "RETURNING id INTO v_padrao;\n"
    f"    INSERT INTO {_JV2}.qualificacao_versoes (padrao_id, versao) VALUES (v_padrao, 1) RETURNING id INTO v_pv;"
)
_JV2_PADRAO_PUBLICADO = _JV2_PADRAO + (
    f"\n    UPDATE {_JV2}.qualificacao_versoes SET status = 'publicada', publicada_em = now(), publicada_por = v_org "
    "WHERE id = v_pv;"
)
_JV2_LEAD = (
    f"INSERT INTO {_JV2}.lead_refs (org_id, produto, ref_externa) "
    "VALUES (v_org, 'social-wiring', 'noc-probe-' || v_sufixo) RETURNING id INTO v_lead;"
)


def _jv2_thread(into: str = "v_thread", chat: str = "'noc-probe-' || v_sufixo") -> str:
    return (
        f"INSERT INTO {_JV2}.conversations (org_id, agent_id, owner_user_id, tipo, channel, channel_ref, lead_ref_id) "
        f"VALUES (v_org, v_agent, v_org, 'thread_lead', 'whatsapp', jsonb_build_object('chat_id', {chat}), v_lead) "
        f"RETURNING id INTO {into};"
    )


_JV2_SKILL = (
    f"INSERT INTO {_JV2}.skills_biblioteca (chave, nome) VALUES ('noc-probe-' || v_sufixo, 'NOC probe') "
    "RETURNING id INTO v_skill;\n"
    f"    INSERT INTO {_JV2}.skill_versoes (skill_id, versao, descricao_modelo, corpo) "
    "VALUES (v_skill, 1, 'quando abrir', 'corpo') RETURNING id INTO v_sv;"
)
_JV2_SKILL_PUBLICADA = _JV2_SKILL + (
    f"\n    UPDATE {_JV2}.skill_versoes SET status = 'publicada', publicada_em = now(), publicada_por = v_org "
    "WHERE id = v_sv;"
)


def _julia_v2_probe(
    *, probe_id: str, guard_name: str, migrations: tuple[str, ...], setup: str, attack: str,
    fragments: tuple[str, ...], what: str, rationale: str, fixture: str = "",
) -> GuardProbe:
    """One write-refusal probe: setup + attack inside the classified sub-block (a setup failure is `ambiguous`,
    never a false `refused`); `refused` iff the error carries one of `fragments` (the guard's own name / code)."""
    what_lit = _sql_lit(what)
    cond = " OR ".join(f"SQLERRM LIKE '%{_sql_lit(f)}%'" for f in fragments)
    # every table the probe touches must exist: a missing one is `no_fixture` (named), never `ambiguous`
    tabelas = sorted(set(re.findall(rf"\b{_JV2}\.([a-z_]+)\b", setup + attack)))
    existe = "".join(
        f"\n  IF to_regclass('{_JV2}.{t}') IS NULL THEN\n"
        f"    RAISE EXCEPTION 'NOC_PROBE:no_fixture: {_JV2}.{t} does not exist (its migration is not applied)';\n"
        "  END IF;"
        for t in tabelas
    )
    sql = _do_block(f"""
DECLARE
  v_org uuid := gen_random_uuid();
  v_sufixo text := substr(replace(gen_random_uuid()::text, '-', ''), 1, 12);
  v_agent uuid; v_agent2 uuid; v_version uuid; v_plat uuid;
  v_padrao uuid; v_pv uuid; v_pv2 uuid; v_lead uuid; v_thread uuid; v_thread2 uuid;
  v_skill uuid; v_sv uuid; v_sv2 uuid; v_registro uuid; v_acesso uuid;
BEGIN{existe}{fixture}
  BEGIN
    {setup}
    {attack}
    RAISE EXCEPTION 'NOC_PROBE:permitted: {what_lit} succeeded — the guard under test did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF {cond} THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
""")
    return GuardProbe(
        id=probe_id, product="agents", schema=_JV2, guard_name=guard_name, kind="write_refusal",
        migrations=migrations, sql=sql, rationale=rationale,
    )


def _jv2_agent_insert(cols: str, vals: str) -> str:
    return (f"INSERT INTO {_JV2}.agents (org_id, key, nome, runtime, definition_mode, {cols}) "
            f"VALUES (v_org, 'noc-probe-' || v_sufixo, 'NOC probe', 'claude_sdk', 'studio', {vals});")


# S3a (migration 049): AI draft generation + data-driven platform definitions. Proven on the real chain in
# test_agents_geracao_probes_on_replay.py.
_AGENTS_GERACAO_PROBES: tuple[GuardProbe, ...] = (
    _agents_studio_probe(
        probe_id="geracoes.limite_usd_cap",
        guard_name="geracoes_limite_check",
        migrations=("049_agent_geracao.sql",),
        requires_table="geracoes",
        attack_sql=(
            f"    INSERT INTO {_AGENTS_SCHEMA}.geracoes (org_id, agent_id, status, briefing, areas_solicitadas, modelo, "
            "provider, limite_usd, criado_por) "
            "VALUES (v_org, v_agent, 'pendente', '{}'::jsonb, ARRAY['secoes']::text[], 'claude-opus-5', 'anthropic', 5.01, v_org);"
        ),
        guard_fragment="geracoes_limite_check",
        what="a generation run with a spend cap above US$ 5.00",
        rationale=(
            "The owner's cap on one AI draft generation (US$ 5.00) is enforced by the database as well as by the "
            "pipeline: no caller that reaches the table can book a run that may spend more."
        ),
    ),
    _agents_studio_probe(
        probe_id="geracoes.one_active_per_agent",
        guard_name="geracoes_one_active_idx",
        migrations=("049_agent_geracao.sql",),
        requires_table="geracoes",
        attack_sql=(
            f"    INSERT INTO {_AGENTS_SCHEMA}.geracoes (org_id, agent_id, status, briefing, areas_solicitadas, modelo, "
            "provider, limite_usd, criado_por) "
            "VALUES (v_org, v_agent, 'pendente', '{}'::jsonb, ARRAY['secoes']::text[], 'claude-opus-5', 'anthropic', 1, v_org);\n"
            f"    INSERT INTO {_AGENTS_SCHEMA}.geracoes (org_id, agent_id, status, briefing, areas_solicitadas, modelo, "
            "provider, limite_usd, criado_por) "
            "VALUES (v_org, v_agent, 'executando', '{}'::jsonb, ARRAY['textos']::text[], 'claude-opus-5', 'anthropic', 1, v_org);"
        ),
        guard_fragment="geracoes_one_active_idx",
        what="a second pendente|executando generation run for the same agent",
        rationale=(
            "At most one AI generation in flight per agent: two would write the same draft rows concurrently and "
            "double the spend."
        ),
    ),
    _agents_studio_probe(
        probe_id="agents.definicao_attributes_only_on_platform_definitions",
        guard_name="agents_definicao_atributos_check",
        migrations=("049_agent_geracao.sql",),
        requires_table="geracoes",
        attack_sql=(
            f"    UPDATE {_AGENTS_SCHEMA}.agents SET padrao_qualificacao = 'noc-probe' WHERE id = v_agent;"
        ),
        guard_fragment="agents_definicao_atributos_check",
        what="a qualification standard on an org-scope agent",
        rationale=(
            "What a platform definition carries as data (qualification scope/standard, first-draft settings, role) "
            "exists only on definition_scope='plataforma' rows: an org agent or an instance carrying them would be "
            "read by a mechanism that must find them on the definition."
        ),
    ),
)


_ISOLATION_MIGS = (_m("031"), "049_agent_geracao.sql", "050_definition_org_grants.sql")
_PLAT_DEF_COLS = "org_id, key, nome, runtime, definition_mode, definition_scope, conteudo_modo"
_PLAT_DEF_VALS = "v_plat, 'noc-probe-' || v_sufixo, 'NOC probe', 'llm', 'studio', 'plataforma', 'linhas'"

# 050: org/app configuration reaches an org only through an explicit grant (KB § PATTERNS/compliance/org-config-isolation.md).
_AGENTS_ISOLATION_PROBES: tuple[GuardProbe, ...] = (
    _julia_v2_probe(
        probe_id="agents.product_owned_definition_never_instanciavel",
        guard_name="agents_product_owned_not_instanciavel", migrations=_ISOLATION_MIGS, setup="",
        fixture=_JV2_PLAT_ORG_FIXTURE,
        attack=(f"INSERT INTO {_JV2}.agents ({_PLAT_DEF_COLS}, owner_product, instanciavel) "
                f"VALUES ({_PLAT_DEF_VALS}, 'noc-probe', true);"),
        fragments=("agents_product_owned_not_instanciavel",),
        what="a product-owned platform definition opened to every org (instanciavel=true)",
        rationale="A definition owned by one product/app is never instantiated in every org: another org's or app's "
                  "configuration reaches an org only through an explicit definition_org_grants row.",
    ),
    _julia_v2_probe(
        probe_id="agents.instance_requires_grant", guard_name="guard_agent_definition_scope",
        migrations=_ISOLATION_MIGS,
        setup=(f"INSERT INTO {_JV2}.agents ({_PLAT_DEF_COLS}, instanciavel) VALUES ({_PLAT_DEF_VALS}, false) "
               "RETURNING id INTO v_agent2;"),
        fixture=_JV2_PLAT_ORG_FIXTURE,
        attack=(f"INSERT INTO {_JV2}.agents (org_id, key, nome, runtime, definition_mode, definition_scope, "
                "definition_agent_id, conteudo_modo) VALUES "
                "(v_org, 'noc-probe-' || v_sufixo, 'NOC probe', 'llm', 'studio', 'instancia', v_agent2, 'linhas');"),
        fragments=("definition_not_granted",),
        what="an instance of a closed definition for an org that was never granted it",
        rationale="A closed (non-instanciavel) definition is held only by granted orgs: an ungranted instance is the "
                  "cross-org configuration leak (julia/social-wiring reaching every org), refused by the database.",
    ),
)


_AGENTS_JULIA_V2_PROBES: tuple[GuardProbe, ...] = (
    # ── 031 · platform definition / instance / content mode ──
    _julia_v2_probe(
        probe_id="agents.definition_scope_vocab", guard_name="agents_definition_scope_check",
        migrations=(_m("031"),), setup="", attack=_jv2_agent_insert("definition_scope", "'noc_probe'"),
        fragments=("agents_definition_scope_check",), what="an agent with an unknown definition_scope",
        rationale="definition_scope is org | plataforma | instancia: an unknown scope would bypass the "
                  "platform-definition and instance rules every Julia resolution relies on (CONTRACT 2.6).",
    ),
    _julia_v2_probe(
        probe_id="agents.conteudo_modo_vocab", guard_name="agents_conteudo_modo_check",
        migrations=(_m("031"),), setup="", attack=_jv2_agent_insert("conteudo_modo", "'noc_probe'"),
        fragments=("agents_conteudo_modo_check",), what="an agent with an unknown conteudo_modo",
        rationale="conteudo_modo selects the compiler (legado strings vs DB rows): an unknown value would compile "
                  "under neither contract.",
    ),
    _julia_v2_probe(
        probe_id="agents.only_an_instance_names_a_definition", guard_name="agents_definition_agent_scope",
        migrations=(_m("031"),), setup=_JV2_AGENT, attack=_jv2_agent_insert("definition_agent_id", "v_agent"),
        fragments=("agents_definition_agent_scope",), what="an org-scoped agent pointing at a definition",
        rationale="Only an instancia row names its definition; any other row doing so would make resolution "
                  "follow a hop that should not exist.",
    ),
    _julia_v2_probe(
        probe_id="agents.platform_definition_is_never_legacy", guard_name="agents_scope_conteudo",
        migrations=(_m("031"),), setup="", fixture=_JV2_PLAT_ORG_FIXTURE,
        attack=(f"INSERT INTO {_JV2}.agents (org_id, key, nome, runtime, definition_mode, definition_scope, conteudo_modo) "
                "VALUES (v_plat, 'noc-probe-' || v_sufixo, 'NOC probe', 'llm', 'studio', 'plataforma', 'legado');"),
        fragments=("agents_scope_conteudo",), what="a platform definition in legacy content mode",
        rationale="A platform-defined agent's every model-visible string is a DB row; legacy mode would bring the "
                  "code-held prompt strings back for it (owner rule: content only in the DB).",
    ),
    # agents_one_plataforma_per_key stays in compliance._GUARD_PROBE_ALLOWLIST (it only bites for a SECOND
    # platform org, which a side-effect-free probe cannot fabricate -- the rationale is there).
    _julia_v2_probe(
        probe_id="agents.platform_definition_lives_in_the_platform_org", guard_name="guard_agent_definition_scope",
        migrations=(_m("031"),), setup="",
        attack=(f"INSERT INTO {_JV2}.agents (org_id, key, nome, runtime, definition_mode, definition_scope, conteudo_modo) "
                "VALUES (v_org, 'noc-probe-' || v_sufixo, 'NOC probe', 'llm', 'studio', 'plataforma', 'linhas');"),
        fragments=("definition_not_platform",), what="a platform definition owned by a non-platform org",
        rationale="IP (CONTRACT 0.4): the platform's prompts live only in the platform org; a definition in a "
                  "tenant org would be readable/editable as that tenant's own content.",
    ),
    _julia_v2_probe(
        probe_id="agent_audit_log.acao_vocab", guard_name="agent_audit_log_acao_check",
        migrations=(_m("031"), _m("034")), setup=_JV2_AGENT,
        attack=f"INSERT INTO {_JV2}.agent_audit_log (org_id, agent_id, acao) VALUES (v_org, v_agent, 'noc_probe_inventada');",
        fragments=("agent_audit_log_acao_check",), what="an audit row with an unknown acao",
        rationale="The audit log is the accountability record of definition reads/MCP writes/control changes: "
                  "free-text actions would make it unqueryable by what happened.",
    ),
    # ── 032 · the qualification standard + per-lead records ──
    _julia_v2_probe(
        probe_id="lead_qualificacao_registros.lead_words_required", guard_name="lead_qualificacao_registros_trecho_lead_check",
        migrations=(_m("032"),), setup="\n    ".join((_JV2_AGENT, _JV2_PADRAO, _JV2_LEAD)),
        attack=(f"INSERT INTO {_JV2}.lead_qualificacao_registros "
                "(org_id, lead_ref_id, agent_id, versao_id, criterio_chave, valor, fonte) "
                "VALUES (v_org, v_lead, v_agent, v_pv, 'operacao', '\"compra\"'::jsonb, 'lead_informou');"),
        fragments=("lead_qualificacao_registros_trecho_lead_check",), what="a lead_informou record with no trecho",
        rationale="The model may only record what the lead said, in the lead's own words (CONTRACT 3.5 E2).",
    ),
    _julia_v2_probe(
        probe_id="qualificacao_versoes.published_needs_who_and_when", guard_name="qualificacao_versoes_publicada_completa",
        migrations=(_m("032"),),
        setup=(f"INSERT INTO {_JV2}.qualificacao_padroes (chave, nome) VALUES ('noc-probe-' || v_sufixo, 'NOC probe') "
               "RETURNING id INTO v_padrao;"),
        attack=f"INSERT INTO {_JV2}.qualificacao_versoes (padrao_id, versao, status) VALUES (v_padrao, 1, 'publicada');",
        fragments=("qualificacao_versoes_publicada_completa",), what="a published standard version with no publisher",
        rationale="A published standard is what every lead is scored by: who published it and when is mandatory.",
    ),
    _julia_v2_probe(
        probe_id="agent_versions.qualificacao_pin_never_a_draft", guard_name="guard_agent_version_qualificacao_pin",
        migrations=(_m("032"), _m("040")), setup="\n    ".join((_JV2_AGENT, _JV2_VERSION, _JV2_PADRAO)),
        attack=f"UPDATE {_JV2}.agent_versions SET qualificacao_versao_id = v_pv WHERE id = v_version;",
        fragments=("invalid_payload",), what="an agent version pinned to a DRAFT standard version",
        rationale="A pinned standard must be immutable (published or archived, 040): a draft pin would let the "
                  "rubric change under a version that was judged with another one.",
    ),
    _julia_v2_probe(
        probe_id="lead_qualificacao_registros.append_only", guard_name="guard_lead_qualificacao_append_only",
        migrations=(_m("032"),), setup="\n    ".join((
            _JV2_AGENT, _JV2_PADRAO, _JV2_LEAD,
            f"INSERT INTO {_JV2}.lead_qualificacao_registros (org_id, lead_ref_id, agent_id, versao_id, criterio_chave, "
            "valor, fonte) VALUES (v_org, v_lead, v_agent, v_pv, 'operacao', '\"compra\"'::jsonb, 'migracao') "
            "RETURNING id INTO v_registro;")),
        attack=f"UPDATE {_JV2}.lead_qualificacao_registros SET valor = '\"aluguel\"'::jsonb WHERE id = v_registro;",
        fragments=("append_only",), what="UPDATE of a recorded qualification answer",
        rationale="Records are history: nobody (model, API, admin) edits what a lead said; only the two erasure "
                  "functions delete (LGPD).",
    ),
    _julia_v2_probe(
        probe_id="qualificacao_criterios.published_parent_is_immutable", guard_name="guard_qualificacao_filho_immutable",
        migrations=(_m("032"),), setup=_JV2_PADRAO_PUBLICADO,
        attack=(f"INSERT INTO {_JV2}.qualificacao_criterios (versao_id, chave, grupo, rotulo, tipo) "
                "VALUES (v_pv, 'noc_probe', 'contato', 'NOC', 'texto');"),
        fragments=("version_immutable",), what="INSERT of a criterion into a published standard version",
        rationale="A published standard's criteria/stages/parameters are frozen with it; otherwise scores already "
                  "computed would no longer be reproducible.",
    ),
    _julia_v2_probe(
        probe_id="qualificacao_versoes.published_is_immutable", guard_name="guard_qualificacao_versao_immutable",
        migrations=(_m("032"),), setup=_JV2_PADRAO_PUBLICADO,
        attack=f"UPDATE {_JV2}.qualificacao_versoes SET notas = 'changed' WHERE id = v_pv;",
        fragments=("version_immutable",), what="UPDATE of a published standard version",
        rationale="Only publicada -> arquivada moves a published standard version; its content is frozen.",
    ),
    _julia_v2_probe(
        probe_id="qualificacao_versoes.one_draft_per_standard", guard_name="uq_qualificacao_versoes_um_rascunho",
        migrations=(_m("032"),), setup=_JV2_PADRAO,
        attack=f"INSERT INTO {_JV2}.qualificacao_versoes (padrao_id, versao) VALUES (v_padrao, 2);",
        fragments=("uq_qualificacao_versoes_um_rascunho",), what="a second draft of the same standard",
        rationale="One draft per standard: two would split edits and let a publish ship the wrong one.",
    ),
    _julia_v2_probe(
        probe_id="lead_identificacao_acessos.append_only", guard_name="guard_lead_identificacao_acessos_append_only",
        migrations=(_m("032"),), setup="\n    ".join((_JV2_LEAD, (
            f"INSERT INTO {_JV2}.lead_identificacao_acessos (org_id, lead_ref_id, ator_user_id) "
            "VALUES (v_org, v_lead, v_org) RETURNING id INTO v_acesso;"))),
        attack=f"DELETE FROM {_JV2}.lead_identificacao_acessos WHERE id = v_acesso;",
        fragments=("append_only",), what="DELETE of an identity-access audit row",
        rationale="Who decrypted a lead's CPF/RG, and when, is accountability (owner 0.4, LGPD): it is never "
                  "erased, not even by the lead-erasure path.",
    ),
    # ── 033 / 035 · the shared lead thread ──
    _julia_v2_probe(
        probe_id="thread_handoffs.exactly_one_destination", guard_name="thread_handoffs_para_check",
        migrations=(_m("033"),), setup="\n    ".join((_JV2_AGENT, _JV2_LEAD, _jv2_thread())),
        attack=(f"INSERT INTO {_JV2}.thread_handoffs (org_id, thread_id, lead_ref_id, de_agent_id, para_tipo, "
                "motivo_codigo, resumo) VALUES (v_org, v_thread, v_lead, v_agent, 'humano', 'noc_probe', 'x');"),
        fragments=("thread_handoffs_para_check",), what="a hand-off to a human with no user",
        rationale="A hand-off names exactly one destination (agent, user or role); a destination-less hand-off "
                  "loses the lead between agents (CONTRACT 0.4: the org owner is the default).",
    ),
    _julia_v2_probe(
        probe_id="conversations.tipo_vocab", guard_name="conversations_tipo_check",
        migrations=(_m("033"),), setup=_JV2_AGENT,
        attack=(f"INSERT INTO {_JV2}.conversations (org_id, agent_id, owner_user_id, tipo) "
                "VALUES (v_org, v_agent, v_org, 'noc_probe');"),
        fragments=("conversations_tipo_check",), what="a conversation with an unknown tipo",
        rationale="tipo separates studio chats from lead threads; an unknown one would escape both code paths.",
    ),
    _julia_v2_probe(
        probe_id="conversations.thread_is_a_channel_row", guard_name="conversations_thread_channel_check",
        migrations=(_m("033"),), setup=_JV2_AGENT,
        attack=(f"INSERT INTO {_JV2}.conversations (org_id, agent_id, owner_user_id, tipo) "
                "VALUES (v_org, v_agent, v_org, 'thread_lead');"),
        # 035 replaces this CHECK with the stronger conversations_thread_lead_check (channel AND lead): the
        # behaviour (no channel-less thread) is what is probed, whichever of the two holds it.
        fragments=("conversations_thread_channel_check", "conversations_thread_lead_check"),
        what="a lead thread with no channel",
        rationale="A lead thread is a channel row; a channel-less thread could never be found by the turn route.",
    ),
    _julia_v2_probe(
        probe_id="thread_participantes.one_active", guard_name="uq_agents_thread_participantes_one_active",
        migrations=(_m("033"),), setup="\n    ".join((_JV2_AGENT, _JV2_AGENT2, _JV2_LEAD, _jv2_thread())),
        attack=(f"INSERT INTO {_JV2}.thread_participantes (thread_id, agent_id, org_id, estado) VALUES "
                "(v_thread, v_agent, v_org, 'ativo'), (v_thread, v_agent2, v_org, 'ativo');"),
        fragments=("uq_agents_thread_participantes_one_active",), what="two active agents on one thread",
        rationale="Risk 11: at most ONE agent answers a lead at a time, enforced by the database.",
    ),
    _julia_v2_probe(
        probe_id="messages.role_vocab", guard_name="messages_role_check",
        migrations=(_m("033"),), setup="\n    ".join((_JV2_AGENT, _JV2_LEAD, _jv2_thread())),
        attack=(f"INSERT INTO {_JV2}.messages (org_id, conversation_id, role, texto) "
                "VALUES (v_org, v_thread, 'noc_probe', 'x');"),
        fragments=("messages_role_check",), what="a message with an unknown role",
        rationale="Message roles drive history labelling and the model context; an unknown role would be "
                  "rendered as nobody's turn.",
    ),
    _julia_v2_probe(
        probe_id="conversations.one_thread_per_channel_ref", guard_name="uq_agents_threads_channel",
        migrations=(_m("035"),), setup="\n    ".join((_JV2_AGENT, _JV2_LEAD, _jv2_thread())),
        attack=_jv2_thread("v_thread2"),
        fragments=("uq_agents_threads_channel",), what="a second thread for the same (org, channel, chat)",
        rationale="One shared thread per lead chat (CONTRACT 6.1): two would split the history agents read.",
    ),
    _julia_v2_probe(
        probe_id="conversations.thread_has_a_lead", guard_name="conversations_thread_lead_check",
        migrations=(_m("035"),), setup=_JV2_AGENT,
        attack=(f"INSERT INTO {_JV2}.conversations (org_id, agent_id, owner_user_id, tipo, channel, channel_ref) "
                "VALUES (v_org, v_agent, v_org, 'thread_lead', 'whatsapp', jsonb_build_object('chat_id', v_sufixo));"),
        fragments=("conversations_thread_lead_check",), what="a lead thread with no lead_ref",
        rationale="Every thread belongs to a lead (opt-out, retention, qualification all hang on lead_ref_id).",
    ),
    # ── 034 · controls ──
    _julia_v2_probe(
        probe_id="agents.modo_operacao_vocab", guard_name="agents_modo_operacao_check",
        migrations=(_m("034"),), setup="", attack=_jv2_agent_insert("modo_operacao", "'noc_probe'"),
        fragments=("agents_modo_operacao_check",), what="an agent with an unknown modo_operacao",
        rationale="modo_operacao (ligado | drenando | desligado) decides whether the agent may answer at all; an "
                  "unknown value must not exist (the controls fail closed on it).",
    ),
    _julia_v2_probe(
        probe_id="agents.dreno_inatividade_dias_range", guard_name="agents_dreno_inatividade_dias_check",
        migrations=(_m("034"),), setup="", attack=_jv2_agent_insert("dreno_inatividade_dias", "0"),
        fragments=("agents_dreno_inatividade_dias_check",), what="a drain idle window of 0 days",
        rationale="The drain closes threads idle N days (owner Q3: 7, editable 1..365); 0 would close every thread "
                  "at once.",
    ),
    # ── 038 · mechanism evals ──
    _julia_v2_probe(
        probe_id="eval_cases.suite_vocab", guard_name="eval_cases_suite_check",
        migrations=(_m("038"),), setup=_JV2_AGENT,
        attack=(f"INSERT INTO {_JV2}.eval_cases (org_id, agent_id, slug, titulo, entrada, criterios, suite) "
                "VALUES (v_org, v_agent, 'noc-probe', 't', 'e', '{\"deve\": [\"x\"]}'::jsonb, 'noc_probe');"),
        fragments=("eval_cases_suite_check",), what="an eval case with an unknown suite",
        rationale="The suite decides which runner judges a case (judge vs deterministic asserts); an unknown suite "
                  "would be judged by neither and silently skipped by the publish gate.",
    ),
    _julia_v2_probe(
        probe_id="eval_cases.k_range", guard_name="eval_cases_k_check",
        migrations=(_m("038"),), setup=_JV2_AGENT,
        attack=(f"INSERT INTO {_JV2}.eval_cases (org_id, agent_id, slug, titulo, entrada, criterios, k) "
                "VALUES (v_org, v_agent, 'noc-probe', 't', 'e', '{\"deve\": [\"x\"]}'::jsonb, 0);"),
        fragments=("eval_cases_k_check",), what="an eval case with k = 0",
        rationale="pass^k with k = 0 is vacuously green: a case that never ran would open the publish gate.",
    ),
    _julia_v2_probe(
        probe_id="eval_cases.judge_case_needs_criteria", guard_name="eval_cases_criterios_ou_mecanismo",
        migrations=(_m("038"),), setup=_JV2_AGENT,
        attack=(f"INSERT INTO {_JV2}.eval_cases (org_id, agent_id, slug, titulo, entrada, criterios) "
                "VALUES (v_org, v_agent, 'noc-probe', 't', 'e', '{}'::jsonb);"),
        fragments=("eval_cases_criterios_ou_mecanismo",), what="a comportamento case with no criteria",
        rationale="A judge case with nothing to judge always passes; the CHECK keeps the judge suite meaningful.",
    ),
    _julia_v2_probe(
        probe_id="eval_cases.mechanism_case_needs_script_and_asserts", guard_name="eval_cases_mecanismo_conteudo",
        migrations=(_m("038"),), setup=_JV2_AGENT,
        attack=(f"INSERT INTO {_JV2}.eval_cases (org_id, agent_id, slug, titulo, entrada, criterios, suite) "
                "VALUES (v_org, v_agent, 'noc-probe', 't', 'e', '{}'::jsonb, 'mecanismo');"),
        fragments=("eval_cases_mecanismo_conteudo",), what="a mecanismo case with no roteiro/asserts",
        rationale="A mechanism case IS its script + deterministic asserts; without them it would pass every run.",
    ),
    _julia_v2_probe(
        probe_id="eval_mecanismo_runs.approved_only_when_all_green", guard_name="eval_mecanismo_runs_aprovado_consistente",
        migrations=(_m("038"),), setup="\n    ".join((_JV2_AGENT, _JV2_VERSION)),
        attack=(f"INSERT INTO {_JV2}.eval_mecanismo_runs (org_id, agent_id, version_id, compiled_hash, driver, status, "
                "aprovado, started_by) VALUES (v_org, v_agent, v_version, 'sha256:noc', 'live', 'executando', true, v_org);"),
        fragments=("eval_mecanismo_runs_aprovado_consistente",), what="an approved mechanism run that never finished",
        rationale="Only a finished, complete, under-budget, all-green live run may be 'aprovado' -- the publish "
                  "gate trusts this flag (also enforced in publish_agent_version).",
    ),
    _julia_v2_probe(
        probe_id="eval_mecanismo_runs.one_executing_per_version", guard_name="uq_eval_mecanismo_runs_um_em_execucao",
        migrations=(_m("038"),), setup="\n    ".join((_JV2_AGENT, _JV2_VERSION)),
        attack="\n    ".join(
            f"INSERT INTO {_JV2}.eval_mecanismo_runs (org_id, agent_id, version_id, compiled_hash, driver, status, "
            "started_by) VALUES (v_org, v_agent, v_version, 'sha256:noc', 'live', 'executando', v_org);"
            for _ in (1, 2)),
        fragments=("uq_eval_mecanismo_runs_um_em_execucao",), what="two executing mechanism runs for one version",
        rationale="One in-flight mechanism run per version: two would double the live-model spend and race on the "
                  "gate's 'newest run' read.",
    ),
    # ── 039 · the shared skill library ──
    _julia_v2_probe(
        probe_id="skill_versoes.published_is_immutable", guard_name="guard_skill_versao_immutable",
        migrations=(_m("039"),), setup=_JV2_SKILL_PUBLICADA,
        attack=f"UPDATE {_JV2}.skill_versoes SET corpo = 'changed' WHERE id = v_sv;",
        fragments=("version_immutable",), what="UPDATE of a published library skill version's body",
        rationale="A pinned skill version is what a published agent version was judged with; its body is frozen.",
    ),
    _julia_v2_probe(
        probe_id="skill_versao_arquivos.published_parent_is_immutable", guard_name="guard_skill_arquivo_immutable",
        migrations=(_m("039"),), setup=_JV2_SKILL_PUBLICADA,
        attack=(f"INSERT INTO {_JV2}.skill_versao_arquivos (skill_versao_id, caminho, conteudo) "
                "VALUES (v_sv, 'noc-probe.md', 'x');"),
        fragments=("version_immutable",), what="INSERT of a reference file into a published skill version",
        rationale="Reference files are part of the published skill version: frozen with it.",
    ),
    _julia_v2_probe(
        probe_id="agent_version_skill_refs.never_pin_a_draft", guard_name="guard_agent_version_skill_ref",
        migrations=(_m("039"),), setup="\n    ".join((_JV2_AGENT, _JV2_VERSION, _JV2_SKILL)),
        attack=(f"INSERT INTO {_JV2}.agent_version_skill_refs (org_id, version_id, skill_id, skill_versao_id) "
                "VALUES (v_org, v_version, v_skill, v_sv);"),
        fragments=("invalid_payload",), what="a pin to a DRAFT library skill version",
        rationale="A draft is mutable: pinning it would let a skill body change under a judged agent version (D7).",
    ),
    _julia_v2_probe(
        probe_id="skill_versoes.one_draft_per_skill", guard_name="uq_skill_versoes_um_rascunho",
        migrations=(_m("039"),), setup=_JV2_SKILL,
        attack=(f"INSERT INTO {_JV2}.skill_versoes (skill_id, versao, descricao_modelo, corpo) "
                "VALUES (v_skill, 2, 'quando', 'corpo');"),
        fragments=("uq_skill_versoes_um_rascunho",), what="a second draft of the same library skill",
        rationale="One draft per skill: two would split edits and let a publish ship the wrong body.",
    ),
    # ── 044 · Julia guardrails: the rule parameters are well formed ──
    _julia_v2_probe(
        probe_id="conformidade_regras.parametros_objeto", guard_name="conformidade_regras_parametros_objeto_check",
        migrations=(_m("037"), _m("044")), setup=_JV2_AGENT,
        attack=(f"INSERT INTO {_JV2}.conformidade_regras (org_id, agent_id, regra, parametros) "
                "VALUES (v_org, v_agent, 'padroes_proibidos', '[\"x\"]'::jsonb);"),
        fragments=("conformidade_regras_parametros_objeto_check",), what="a conformance rule whose parameters are not a JSON object",
        rationale="Every reader does `parametros.get(...)`: a list or scalar would crash the turn that reads the rule, on a public line.",
    ),
    _julia_v2_probe(
        probe_id="conformidade_regras.escala_limiares_ordem", guard_name="conformidade_regras_escala_limiares_check",
        migrations=(_m("037"), _m("044")), setup=_JV2_AGENT,
        attack=(f"INSERT INTO {_JV2}.conformidade_regras (org_id, agent_id, regra, parametros) "
                "VALUES (v_org, v_agent, 'escala_seguranca', '{\"limiar_suspeito\": 3, \"limiar_handoff\": 3}'::jsonb);"),
        fragments=("conformidade_regras_escala_limiares_check",), what="an escalation whose hand-off threshold is not above the restricted-mode threshold",
        rationale="limiar_handoff must be strictly above limiar_suspeito or the restricted-mode step is skipped: the lead goes from normal straight to hand-off.",
    ),
    _julia_v2_probe(
        probe_id="conformidade_regras.escala_limiares_faixa", guard_name="conformidade_regras_escala_limiares_check",
        migrations=(_m("037"), _m("044")), setup=_JV2_AGENT,
        attack=(f"INSERT INTO {_JV2}.conformidade_regras (org_id, agent_id, regra, parametros) "
                "VALUES (v_org, v_agent, 'escala_seguranca', '{\"limiar_suspeito\": 0}'::jsonb);"),
        fragments=("conformidade_regras_escala_limiares_check",), what="an escalation threshold of zero",
        rationale="A zero threshold would put every lead in restricted mode from the first message; thresholds are integers 1..20.",
    ),
    # ── 042 · a lead that asks to stop is never dropped silently ──
    _julia_v2_probe(
        probe_id="lead_opt_out_eventos.origem_vocab", guard_name="lead_opt_out_eventos_origem_check",
        migrations=(_m("042"),), setup=_JV2_LEAD,
        attack=(f"INSERT INTO {_JV2}.lead_opt_out_eventos (org_id, lead_ref_id, origem, motivo) "
                "VALUES (v_org, v_lead, 'noc_probe', 'x');"),
        fragments=("lead_opt_out_eventos_origem_check",), what="an opt-out event with an unknown origin",
        rationale="origem (agente | operador | integracao) tells the owner WHO stopped the lead; an unknown value would be an event nobody can attribute.",
    ),
    _julia_v2_probe(
        probe_id="lead_opt_out_eventos.motivo_not_blank", guard_name="lead_opt_out_eventos_motivo_check",
        migrations=(_m("042"),), setup=_JV2_LEAD,
        attack=(f"INSERT INTO {_JV2}.lead_opt_out_eventos (org_id, lead_ref_id, origem, motivo) "
                "VALUES (v_org, v_lead, 'agente', '   ');"),
        fragments=("lead_opt_out_eventos_motivo_check",), what="an opt-out event with a blank reason",
        rationale="The owner's record says WHY the lead was dropped (owner decision 2026-10-21): a blank reason is the silent disengage this table exists to prevent.",
    ),
    _julia_v2_probe(
        probe_id="lead_opt_out_eventos.notificacao_status_vocab", guard_name="lead_opt_out_eventos_notificacao_check",
        migrations=(_m("042"),), setup=_JV2_LEAD,
        attack=(f"INSERT INTO {_JV2}.lead_opt_out_eventos (org_id, lead_ref_id, origem, motivo, notificacao_status) "
                "VALUES (v_org, v_lead, 'agente', 'x', 'talvez');"),
        fragments=("lead_opt_out_eventos_notificacao_check",), what="an opt-out event with an unknown notification status",
        rationale="pendente | enviada | falhou is how a failed notice stays visible; an unknown status would hide whether the owner was told.",
    ),
    _julia_v2_probe(
        probe_id="lead_opt_out_eventos.mensagem_lead_cap", guard_name="lead_opt_out_eventos_mensagem_check",
        migrations=(_m("042"),), setup=_JV2_LEAD,
        attack=(f"INSERT INTO {_JV2}.lead_opt_out_eventos (org_id, lead_ref_id, origem, motivo, mensagem_lead) "
                "VALUES (v_org, v_lead, 'agente', 'x', repeat('x', 1001));"),
        fragments=("lead_opt_out_eventos_mensagem_check",), what="an opt-out event quoting more than 1000 characters of the lead",
        rationale="The lead's own words are personal data: the quote is capped so the table cannot become a message archive.",
    ),
    # ── 043 · an operator can lift an opt-out, on the record ──
    _julia_v2_probe(
        probe_id="lead_opt_out_eventos.tipo_vocab", guard_name="lead_opt_out_eventos_tipo_check",
        migrations=(_m("043"),), setup=_JV2_LEAD,
        attack=(f"INSERT INTO {_JV2}.lead_opt_out_eventos (org_id, lead_ref_id, tipo, origem, motivo) "
                "VALUES (v_org, v_lead, 'noc_probe', 'operador', 'x');"),
        fragments=("lead_opt_out_eventos_tipo_check",), what="a consent-history event of an unknown type",
        rationale="tipo (opt_out | reativacao) is how the owner's history tells a lead stopping from an operator putting it back; an unknown value would be an event nobody can read.",
    ),
    _julia_v2_probe(
        probe_id="lead_refs.opt_in_origem_vocab", guard_name="lead_refs_opt_in_origem_check",
        migrations=(_m("043"),), setup=_JV2_LEAD,
        attack=f"UPDATE {_JV2}.lead_refs SET opt_in_origem = 'noc_probe' WHERE id = v_lead;",
        fragments=("lead_refs_opt_in_origem_check",), what="a lead consent with an unknown origin",
        rationale="opt_in_origem says HOW the lead came back (lead_iniciou, formulario_meta, campanha_ctwa, importado, reativacao_manual); an unknown value is a consent nobody can account for.",
    ),
    _julia_v2_probe(
        probe_id="registrar_opt_out.refuses_an_unknown_origin", guard_name="lead_opt_out_eventos_origem_check",
        migrations=(_m("042"),), setup=_JV2_LEAD,
        # the schema is quoted so the table-existence preflight (which reads `agents.<name>` as a table) does not
        # mistake the function for one; the lead_refs / lead_opt_out_eventos tables it needs are checked via setup.
        attack="PERFORM \"agents\".registrar_opt_out(v_org, 'social-wiring', 'noc-probe-' || v_sufixo, now(), 'telepatia');",
        fragments=("lead_opt_out_eventos_origem_check",), what="the opt-out RPC called with an unknown origin",
        rationale="The RPC is the only writer of the event (service role): its origin must hit the same CHECK, "
                  "so no caller can record an opt-out the owner cannot attribute.",
    ),
    # ── 046 · provenance is structural; the prompt stays in the prompt ──
    _julia_v2_probe(
        probe_id="messages.evento_is_a_code", guard_name="messages_evento_codigo_check",
        migrations=(_m("046"),), setup="\n    ".join((_JV2_AGENT, _JV2_LEAD, _jv2_thread())),
        attack=(f"INSERT INTO {_JV2}.messages (org_id, conversation_id, role, texto) "
                "VALUES (v_org, v_thread, 'evento', 'Reescreva a resposta sem repetir as instrucoes internas.');"),
        fragments=("messages_evento_codigo_check",), what="a thread event row carrying prose instead of a code",
        rationale="The correction wording is prompt text: an evento row is a machine code (conformidade:<regra>), "
                  "so nothing a person reads in the thread can be the DB prompt.",
    ),
    _julia_v2_probe(
        probe_id="messages.meta_is_an_object", guard_name="messages_meta_check",
        migrations=(_m("046"),), setup="\n    ".join((_JV2_AGENT, _JV2_LEAD, _jv2_thread())),
        attack=(f"INSERT INTO {_JV2}.messages (org_id, conversation_id, role, texto, meta) "
                "VALUES (v_org, v_thread, 'user', 'x', '[1]'::jsonb);"),
        fragments=("messages_meta_check",), what="message meta that is not a JSON object",
        rationale="meta holds the structural facts about a line (media, staff author); a non-object would be read as nothing.",
    ),
    _julia_v2_probe(
        probe_id="messages.meta_size_cap", guard_name="messages_meta_check",
        migrations=(_m("046"),), setup="\n    ".join((_JV2_AGENT, _JV2_LEAD, _jv2_thread())),
        attack=(f"INSERT INTO {_JV2}.messages (org_id, conversation_id, role, texto, meta) "
                "VALUES (v_org, v_thread, 'user', 'x', jsonb_build_object('midia', repeat('x', 9000)));"),
        fragments=("messages_meta_check",), what="message meta over 8000 characters",
        rationale="Media text is capped at the edge (2000 characters); the table backs that up so meta cannot become a blob store.",
    ),
    _julia_v2_probe(
        probe_id="agent_version_marcadores.marcador_shape", guard_name="agent_version_marcadores_marcador_check",
        migrations=(_m("046"),), setup="\n    ".join((_JV2_AGENT, _JV2_VERSION)),
        attack=(f"INSERT INTO {_JV2}.agent_version_marcadores (version_id, org_id, marcador) "
                "VALUES (v_version, v_org, 'curto');"),
        fragments=("agent_version_marcadores_marcador_check",), what="a honeytoken that is short or not hex",
        rationale="The honeytoken is a random machine value; a guessable or word-like one would fire on ordinary text.",
    ),
)


# ---------------------------------------------------------------------------
# Registry — migration 154 (imóvel extraction under D1): the structured-read
# lifecycle CHECK and the one-open-conflict-per-field UNIQUE.
# ---------------------------------------------------------------------------
#
# Both borrow `(org_id, codigo_canonical)` from `imovel_registry` — the FK
# target of both tables — and INSERT a throwaway specimen inside the
# rolled-back transaction, the self-provisioning shape (no dependency on
# production already holding a document or a conflict).

_REGISTRY_FIXTURE_FROM = f"{_SW_SCHEMA}.imovel_registry"
_REGISTRY_FIXTURE_DESC = f"no row in {_SW_SCHEMA}.imovel_registry to borrow (org_id, codigo) from"

_ESTRUTURA_STATUS_PROBE = GuardProbe(
    id="imovel_documentos.estrutura_status.allowed_values",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="imovel_documentos_estrutura_status_check",
    kind="write_refusal",
    migrations=("154_imovel_extracao_proveniencia.sql",),
    rationale=(
        "`estrutura_status` drives the D3 retry sweep (`documentos_service."
        "varrer_estrutura_pendentes` selects `pendente`/`processando`/`erro` "
        "by exact value) — a value outside the vocabulary would make a "
        "document invisible to recovery AND to its terminal states at once."
    ),
    sql=_insert_check_probe(
        schema=_SW_SCHEMA,
        table="imovel_documentos",
        columns_sql=(
            "org_id, codigo, storage_path, nome_original, mime_type, "
            "tamanho_bytes, tipo_documento, estrutura_status"
        ),
        values_sql=(
            "org_id, codigo_canonical, 'noc-probe', 'noc-probe.pdf', "
            "'application/pdf', 0, 'matricula', 'noc_probe_bogus'"
        ),
        fixture_from=_REGISTRY_FIXTURE_FROM,
        fixture_description=_REGISTRY_FIXTURE_DESC,
        guard_fragment='constraint "imovel_documentos_estrutura_status_check"',
    ),
)

_IMOVEL_CONFLITO_ABERTO_PROBE = GuardProbe(
    id="imovel_campo_conflitos.one_open_per_field",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="uq_sw_imovel_campo_conflitos_aberto",
    kind="write_refusal",
    migrations=("154_imovel_extracao_proveniencia.sql",),
    rationale=(
        "One PENDING conflict per (imóvel, field): a re-extraction must not "
        "pile up a second question (and a second notification) while the "
        "first is unanswered — D1's 'a human is notified and decides' "
        "degrades into noise otherwise. The app checks first "
        "(`campos_extraidos_service.aplicar`); this index is the backstop."
    ),
    sql=_do_block(f"""
DECLARE
  v_org_id uuid;
  v_codigo text;
BEGIN
  SELECT org_id, codigo_canonical INTO v_org_id, v_codigo FROM {_REGISTRY_FIXTURE_FROM} LIMIT 1;
  IF v_org_id IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: {_sql_lit(_REGISTRY_FIXTURE_DESC)}';
  END IF;
  BEGIN
    INSERT INTO {_SW_SCHEMA}.imovel_campo_conflitos
      (org_id, codigo, campo, valor_proposto, origem_proposto, status)
    VALUES (v_org_id, v_codigo, 'noc_probe_campo', '"a"'::jsonb, 'matricula', 'pendente');
    INSERT INTO {_SW_SCHEMA}.imovel_campo_conflitos
      (org_id, codigo, campo, valor_proposto, origem_proposto, status)
    VALUES (v_org_id, v_codigo, 'noc_probe_campo', '"b"'::jsonb, 'matricula', 'pendente');
    RAISE EXCEPTION 'NOC_PROBE:permitted: a second pending conflict for the same field was accepted — the unique guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%uq_sw_imovel_campo_conflitos_aberto%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
)


# ---------------------------------------------------------------------------
# Registry — migration 175 (automatic divergence resolution): the widened
# `status` CHECK on `cliente_campo_conflitos`/`empresa_campo_conflitos`
# (`'resolvido_automatico'` joins `pendente`/`aceito`/`rejeitado`).
# `imovel_campo_conflitos` shares the same CHECK shape but already had no
# probe registered for IT specifically either — 138/154/167 raised it
# unprobed originally; these two close the cliente/empresa half of that gap
# the same `check_migration_guard_has_probe` gate now enforces on ANY
# migration that re-declares the constraint (this one does, to add the new
# value) rather than leaving it silently un-verified going forward.
# ---------------------------------------------------------------------------

_CLIENTE_CONFLITO_STATUS_PROBE = GuardProbe(
    id="cliente_campo_conflitos.status.allowed_values",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="cliente_campo_conflitos_status_check",
    kind="write_refusal",
    migrations=("175_campo_conflitos_resolucao_automatica.sql",),
    rationale=(
        "`status` drives who ever SEES a conflict: `conflitos_pendentes` "
        "(the admin queue) and `contrato_gerador.validacao_extracao."
        "listar_conflitos` (the contract gate) both filter on the exact "
        "vocabulary (`pendente`/`aceito`/`rejeitado`/`resolvido_"
        "automatico`) — a value outside it would silently vanish from both "
        "without ever surfacing as an error."
    ),
    sql=_insert_check_probe(
        schema=_SW_SCHEMA,
        table="cliente_campo_conflitos",
        columns_sql="org_id, cliente_id, campo, valor_proposto, origem_proposto, status",
        values_sql=(
            "org_id, id, 'noc_probe_campo', 'noc_probe_valor', "
            "'noc_probe_origem', 'noc_probe_bogus'"
        ),
        fixture_from=f"{_SW_SCHEMA}.clientes",
        fixture_description=f"no row in {_SW_SCHEMA}.clientes to borrow (org_id, id) from",
        guard_fragment='constraint "cliente_campo_conflitos_status_check"',
    ),
)

_EMPRESA_CONFLITO_STATUS_PROBE = GuardProbe(
    id="empresa_campo_conflitos.status.allowed_values",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="empresa_campo_conflitos_status_check",
    kind="write_refusal",
    migrations=("175_campo_conflitos_resolucao_automatica.sql",),
    rationale=(
        "Same vocabulary contract as `cliente_campo_conflitos` above, for "
        "the empresa-scoped conflicts `app.modules.empresas` opens."
    ),
    sql=_insert_check_probe(
        schema=_SW_SCHEMA,
        table="empresa_campo_conflitos",
        columns_sql="org_id, empresa_id, campo, valor_proposto, origem_proposto, status",
        values_sql=(
            "org_id, id, 'noc_probe_campo', '\"noc_probe_valor\"'::jsonb, "
            "'noc_probe_origem', 'noc_probe_bogus'"
        ),
        fixture_from=f"{_SW_SCHEMA}.empresas",
        fixture_description=f"no row in {_SW_SCHEMA}.empresas to borrow (org_id, id) from",
        guard_fragment='constraint "empresa_campo_conflitos_status_check"',
    ),
)

_ATENDIMENTO_CONFLITO_STATUS_PROBE = GuardProbe(
    id="atendimento_campo_conflitos.status.allowed_values",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="atendimento_campo_conflitos_status_check",
    kind="write_refusal",
    migrations=("200_atendimento_campo_conflitos_resolucao_automatica.sql",),
    rationale=(
        "Same vocabulary contract as `cliente_campo_conflitos` above, for the "
        "deal-side conflicts `card_hub.negociacao_extracao_service` opens — "
        "`listar_conflitos` and the contract gate filter on it; a value "
        "outside it would silently vanish from both. Holds before AND after "
        "200 (171's inline CHECK carries the same name), so the probe is "
        "valid whether or not 200 has been applied."
    ),
    sql=_insert_check_probe(
        schema=_SW_SCHEMA,
        table="atendimento_campo_conflitos",
        columns_sql="org_id, atendimento_id, campo, valor_proposto, origem_proposto, status",
        values_sql=(
            "org_id, id, 'noc_probe_campo', '\"noc_probe_valor\"'::jsonb, "
            "'noc_probe_origem', 'noc_probe_bogus'"
        ),
        fixture_from=f"{_SW_SCHEMA}.atendimentos",
        fixture_description=f"no row in {_SW_SCHEMA}.atendimentos to borrow (org_id, id) from",
        guard_fragment='constraint "atendimento_campo_conflitos_status_check"',
    ),
)


# ---------------------------------------------------------------------------
# Registry — igig CRM foundation (migrations 017 pipelines, 018 CRM, 019 card
# hub; plus the 006/010 guards whose SQLite mirrors that change touched).
# ---------------------------------------------------------------------------
#
# Fully self-provisioning, same shape as the agents probes: every igig table's
# `org_id` has no FK, so each probe fabricates its own org, stage, lead,
# negócio, cliente… inside the rolled-back transaction — no production row is
# borrowed or touched. The only `no_fixture` path is "migration 018 is not
# applied" (checked on the newest table every fixture here depends on). Setup
# statements live INSIDE the classified sub-block, so a setup failure surfaces
# as `ambiguous`, never a false `refused`.

_IGIG_SCHEMA = "igig"
_IGIG_PIPELINE_MIGRATIONS = ("017_igig_pipeline.sql",)
_IGIG_CRM_MIGRATIONS = ("018_igig_crm.sql",)
_IGIG_CARD_HUB_MIGRATIONS = ("019_card_hub.sql",)
_IGIG_ORCAMENTOS_MIGRATIONS = ("020_igig_orcamentos.sql",)
_IGIG_AUTOMACOES_MIGRATIONS = ("018_igig_crm.sql", "023_igig_automacoes.sql")

#: Fixture snippets (PL/pgSQL statements), composed per probe.
_IGIG_STAGE = (
    f"INSERT INTO {_IGIG_SCHEMA}.pipeline_stages (org_id, pipeline, slug, label) "
    "VALUES (v_org, 'comercial', 'noc_probe', 'NOC probe') RETURNING id INTO v_stage;"
)
_IGIG_ESTEIRA_STAGE = (
    f"INSERT INTO {_IGIG_SCHEMA}.pipeline_stages (org_id, pipeline, slug, label) "
    "VALUES (v_org, 'esteira', 'noc_probe', 'NOC probe') RETURNING id INTO v_stage;"
)
_IGIG_LEAD = (
    f"INSERT INTO {_IGIG_SCHEMA}.lead (org_id, nome) VALUES (v_org, 'NOC probe') "
    "RETURNING id INTO v_lead;"
)
_IGIG_NEGOCIO = (
    f"INSERT INTO {_IGIG_SCHEMA}.negocio (org_id, lead_id, titulo, etapa_id) "
    "VALUES (v_org, v_lead, 'NOC probe', v_stage) RETURNING id INTO v_negocio;"
)
_IGIG_CLIENTE = (
    f"INSERT INTO {_IGIG_SCHEMA}.cliente (org_id, nome) VALUES (v_org, 'NOC probe') "
    "RETURNING id INTO v_cliente;"
)

_IGIG_AUTOMACAO = (
    f"INSERT INTO {_IGIG_SCHEMA}.automacao (org_id, pipeline, etapa_id, gatilho) "
    "VALUES (v_org, 'comercial', v_stage, 'entrada_etapa');"
)
#: One execution keyed on the probe's single automação + single entry row.
_IGIG_EXECUCAO_DA_ENTRADA = (
    f"INSERT INTO {_IGIG_SCHEMA}.automacao_execucao "
    "(org_id, automacao_id, entidade_id, movimento_id, status) "
    "SELECT v_org, a.id, v_org, m.id, 'sucesso' "
    f"FROM {_IGIG_SCHEMA}.automacao a, {_IGIG_SCHEMA}.pipeline_movimentos m "
    "WHERE a.org_id = v_org AND m.org_id = v_org;"
)

def _fresh_org_write_refusal_probe(
    *, product: str, schema: str, exists_table: str, exists_migration: str,
    declare_vars: tuple[str, ...], probe_id: str, guard_name: str,
    setup_sql: tuple[str, ...], attack_sql: str, what: str, rationale: str,
    migrations: tuple[str, ...],
) -> GuardProbe:
    """One self-provisioned write-refusal probe on a FRESH org id.

    For products whose `org_id` columns carry no FK (igig, community), the
    probe mints `v_org := gen_random_uuid()` and builds whatever rows it
    needs itself — no borrowed fixture, so it runs on an empty database too.
    The expected refusal is classified on `guard_name` itself appearing in
    SQLERRM: Postgres names the violated constraint/index in both the CHECK
    and the UNIQUE message. `declare_vars` are extra `name type` locals the
    setup needs.
    """
    name_lit = _sql_lit(guard_name)
    what_lit = _sql_lit(what)
    setup = "\n".join(f"    {stmt}" for stmt in setup_sql)
    declares = "".join(f"\n  {v};" for v in declare_vars)
    sql = _do_block(f"""
DECLARE
  v_org uuid := gen_random_uuid();{declares}
BEGIN
  IF to_regclass('{schema}.{exists_table}') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: {schema}.{exists_table} does not exist (migration {exists_migration} not applied)';
  END IF;
  BEGIN
{setup}
    {attack_sql}
    RAISE EXCEPTION 'NOC_PROBE:permitted: {what_lit} succeeded — the guard under test did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{name_lit}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
""")
    return GuardProbe(
        id=probe_id,
        product=product,
        schema=schema,
        guard_name=guard_name,
        kind="write_refusal",
        migrations=migrations,
        sql=sql,
        rationale=rationale,
    )


_IGIG_PROBE_VARS = (
    "v_stage uuid", "v_lead uuid", "v_negocio uuid", "v_cliente uuid",
    "v_pauta uuid", "v_tarefa uuid", "v_orcamento uuid",
)


def _igig_probe(
    *, probe_id: str, guard_name: str, setup_sql: tuple[str, ...], attack_sql: str, what: str,
    rationale: str, migrations: tuple[str, ...],
) -> GuardProbe:
    """One self-provisioned igig write-refusal probe (see
    `_fresh_org_write_refusal_probe`)."""
    return _fresh_org_write_refusal_probe(
        product="igig", schema=_IGIG_SCHEMA, exists_table="negocio", exists_migration="018",
        declare_vars=_IGIG_PROBE_VARS, probe_id=probe_id, guard_name=guard_name,
        setup_sql=setup_sql, attack_sql=attack_sql, what=what, rationale=rationale,
        migrations=migrations,
    )


def _igig_card_hub_probes(prefix: str, entity_setup: tuple[str, ...], entity_var: str) -> tuple[GuardProbe, ...]:
    t = _IGIG_SCHEMA
    return (
        _igig_probe(
            probe_id=f"{prefix}_notas.one_descricao",
            guard_name=f"uq_{prefix}_notas_one_descricao",
            setup_sql=entity_setup + (
                f"INSERT INTO {t}.{prefix}_notas (org_id, {prefix}_id, tipo, corpo) "
                f"VALUES (v_org, {entity_var}, 'descricao', 'a');",
            ),
            attack_sql=(
                f"INSERT INTO {t}.{prefix}_notas (org_id, {prefix}_id, tipo, corpo) "
                f"VALUES (v_org, {entity_var}, 'descricao', 'b');"
            ),
            what=f"a second live descricao on one {prefix} card",
            rationale=(
                "The card has ONE description (the seed card hub answers a typed "
                "409 on a second); two would make the card render whichever the "
                "read happened to return first."
            ),
            migrations=_IGIG_CARD_HUB_MIGRATIONS,
        ),
        _igig_probe(
            probe_id=f"{prefix}_tags.unique_name_case_insensitive",
            guard_name=f"uq_{prefix}_tags_org_nome",
            setup_sql=(
                f"INSERT INTO {t}.{prefix}_tags (org_id, nome, cor) VALUES (v_org, 'NOC Probe', '#000000');",
            ),
            attack_sql=(
                f"INSERT INTO {t}.{prefix}_tags (org_id, nome, cor) VALUES (v_org, 'noc probe', '#000000');"
            ),
            what=f"a case-variant duplicate {prefix} tag name",
            rationale=(
                "One org tag catalogue: 'VIP' and 'vip' as two tags would split "
                "every filter and count by an invisible difference."
            ),
            migrations=_IGIG_CARD_HUB_MIGRATIONS,
        ),
    )


_IGIG_PROBES: tuple[GuardProbe, ...] = (
    _igig_probe(
        probe_id="igig.produto_servico.nome.unique_per_secao",
        guard_name="idx_igig_produto_servico_nome",
        setup_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.produto_servico (org_id, secao, nome) "
            "VALUES (v_org, 'criacao_conteudo', 'NOC probe');",
        ),
        attack_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.produto_servico (org_id, secao, nome) "
            "VALUES (v_org, 'criacao_conteudo', 'NOC probe');"
        ),
        what="the same catalogue name twice in one section",
        rationale=(
            "The lazy first-read catalogue seed upserts on (org_id, secao, nome) "
            "with ignore_duplicates — without the index two concurrent first "
            "reads would each seed the whole catalogue."
        ),
        migrations=_IGIG_ORCAMENTOS_MIGRATIONS,
    ),
    _igig_probe(
        probe_id="igig.produto_servico.formato.closed_vocabulary",
        guard_name="produto_servico_formato_check",
        setup_sql=(),
        attack_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.produto_servico (org_id, secao, nome, formato) "
            "VALUES (v_org, 'criacao_conteudo', 'NOC probe', 'noc_probe_invalido');"
        ),
        what="a catalogue product with a formato outside the pauta formats",
        rationale=(
            "An accepted orçamento copies the product's formato onto every "
            "generated pauta, whose own CHECK would then reject the whole "
            "aceite — the catalogue must refuse it at write time."
        ),
        migrations=_IGIG_ORCAMENTOS_MIGRATIONS,
    ),
    _igig_probe(
        probe_id="igig.pipeline_stages.one_stage_per_role",
        guard_name="idx_igig_pipeline_stages_papel",
        setup_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.pipeline_stages (org_id, pipeline, slug, label, papel) "
            "VALUES (v_org, 'comercial', 'noc_a', 'A', 'fechado');",
        ),
        attack_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.pipeline_stages (org_id, pipeline, slug, label, papel) "
            "VALUES (v_org, 'comercial', 'noc_b', 'B', 'fechado');"
        ),
        what="a second 'fechado' stage on one board",
        rationale=(
            "Closing a deal keys on THE stage with role `fechado` (orçamento "
            "required); two such stages make the rule pick one arbitrarily."
        ),
        migrations=_IGIG_PIPELINE_MIGRATIONS,
    ),
    _igig_probe(
        probe_id="igig.lead.origem.closed_vocabulary",
        guard_name="lead_origem_check",
        setup_sql=(),
        attack_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.lead (org_id, nome, origem) "
            "VALUES (v_org, 'NOC probe', 'noc_probe_invalida');"
        ),
        what="a lead with an origem outside formulario|manual|whatsapp|meta_ads",
        rationale="Source statistics and the dedupe paths branch on the channel set.",
        migrations=_IGIG_CRM_MIGRATIONS,
    ),
    _igig_probe(
        probe_id="igig.lead.meta_lead_id.unique_per_org",
        guard_name="idx_igig_lead_meta",
        setup_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.lead (org_id, nome, meta_lead_id) VALUES (v_org, 'A', 'noc-meta');",
        ),
        attack_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.lead (org_id, nome, meta_lead_id) VALUES (v_org, 'B', 'noc-meta');"
        ),
        what="the same Meta lead id twice in one org",
        rationale="A re-delivered Meta Lead Ads webhook must not create a second lead + card.",
        migrations=_IGIG_CRM_MIGRATIONS,
    ),
    _igig_probe(
        probe_id="igig.lead.waha_chat_id.unique_per_org",
        guard_name="idx_igig_lead_waha",
        setup_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.lead (org_id, nome, waha_chat_id) VALUES (v_org, 'A', 'noc@c.us');",
        ),
        attack_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.lead (org_id, nome, waha_chat_id) VALUES (v_org, 'B', 'noc@c.us');"
        ),
        what="the same WhatsApp chat twice in one org",
        rationale="One WhatsApp conversation is one lead; a second row would split its history.",
        migrations=_IGIG_CRM_MIGRATIONS,
    ),
    _igig_probe(
        probe_id="igig.negocio.perdido_requires_reason",
        guard_name="negocio_perdido_com_motivo",
        setup_sql=(_IGIG_STAGE, _IGIG_LEAD),
        attack_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.negocio (org_id, lead_id, titulo, etapa_id, status) "
            "VALUES (v_org, v_lead, 'NOC probe', v_stage, 'perdido');"
        ),
        what="a lost negócio without motivo_perda/perdido_em",
        rationale="Loss statistics by reason are the point of archiving a lost deal (owner, 2026-09-22).",
        migrations=_IGIG_CRM_MIGRATIONS,
    ),
    _igig_probe(
        probe_id="igig.orcamento.status.closed_vocabulary",
        guard_name="orcamento_status_check",
        setup_sql=(),
        attack_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.orcamento (org_id, titulo, status) "
            "VALUES (v_org, 'NOC probe', 'noc_probe_invalida');"
        ),
        what="an orçamento status outside the six the funnel branches on",
        rationale="Closing a deal refuses recusado/expirado/substituido by status; an unknown one would slip through.",
        migrations=_IGIG_CRM_MIGRATIONS,
    ),
    _igig_probe(
        probe_id="igig.orcamento.one_aceito_per_negocio",
        guard_name="idx_igig_orcamento_um_aceito",
        setup_sql=(
            _IGIG_STAGE, _IGIG_LEAD, _IGIG_NEGOCIO,
            f"INSERT INTO {_IGIG_SCHEMA}.orcamento (org_id, negocio_id, titulo, versao, status) "
            "VALUES (v_org, v_negocio, 'v1', 1, 'aceito');",
        ),
        attack_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.orcamento (org_id, negocio_id, titulo, versao, status) "
            "VALUES (v_org, v_negocio, 'v2', 2, 'aceito');"
        ),
        what="a second accepted orçamento on one negócio",
        rationale="Only one version is acceptable (owner, 2026-09-22) — two would bill two scopes.",
        migrations=_IGIG_CRM_MIGRATIONS,
    ),
    _igig_probe(
        probe_id="igig.orcamento.versao.unique_per_negocio",
        guard_name="idx_igig_orcamento_versao",
        setup_sql=(
            _IGIG_STAGE, _IGIG_LEAD, _IGIG_NEGOCIO,
            f"INSERT INTO {_IGIG_SCHEMA}.orcamento (org_id, negocio_id, titulo, versao) "
            "VALUES (v_org, v_negocio, 'a', 1);",
        ),
        attack_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.orcamento (org_id, negocio_id, titulo, versao) "
            "VALUES (v_org, v_negocio, 'b', 1);"
        ),
        what="two orçamentos with the same versao on one negócio",
        rationale="'v2' must name exactly one proposal when the lead replies to it.",
        migrations=_IGIG_CRM_MIGRATIONS,
    ),
    _igig_probe(
        probe_id="igig.orcamento_item.recurring_needs_days_and_qty",
        guard_name="orcamento_item_recorrencia",
        setup_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.orcamento (org_id, titulo) VALUES (v_org, 'NOC probe') "
            "RETURNING id INTO v_orcamento;",
        ),
        attack_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.orcamento_item "
            "(org_id, orcamento_id, secao, descricao, recorrente, dias_semana, qtd_por_dia) "
            "VALUES (v_org, v_orcamento, 'criacao_conteudo', 'Reels', true, 0, 0);"
        ),
        what="a recurring item with no weekday",
        rationale="A recurring item that never occurs would price and schedule nothing, silently.",
        migrations=_IGIG_CRM_MIGRATIONS,
    ),
    _igig_probe(
        probe_id="igig.cliente.one_per_lead",
        guard_name="idx_igig_cliente_lead",
        setup_sql=(
            _IGIG_LEAD,
            f"INSERT INTO {_IGIG_SCHEMA}.cliente (org_id, nome, lead_id) VALUES (v_org, 'A', v_lead);",
        ),
        attack_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.cliente (org_id, nome, lead_id) VALUES (v_org, 'B', v_lead);"
        ),
        what="a second cliente for one lead",
        rationale="Closing a deal creates the Cliente idempotently; this index is the database half of that.",
        migrations=_IGIG_CRM_MIGRATIONS,
    ),
    _igig_probe(
        probe_id="igig.contrato.modalidade_assinatura.closed_vocabulary",
        guard_name="contrato_modalidade_assinatura_check",
        setup_sql=(_IGIG_CLIENTE,),
        attack_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.contrato (org_id, cliente_id, modalidade_assinatura) "
            "VALUES (v_org, v_cliente, 'noc_probe');"
        ),
        what="a contract signing modality outside digital|fisica",
        rationale="The modality gates the e-signature flow vs manual signature lines (R12).",
        migrations=_IGIG_CRM_MIGRATIONS,
    ),
    _igig_probe(
        probe_id="igig.integracao.canal.closed_vocabulary",
        guard_name="integracao_canal_check",
        setup_sql=(),
        attack_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.integracao (org_id, canal) VALUES (v_org, 'noc_probe');"
        ),
        what="an integration channel outside the supported set",
        rationale="Each channel decrypts and uses its credential differently; an unknown one has no reader.",
        migrations=_IGIG_CRM_MIGRATIONS,
    ),
    _igig_probe(
        probe_id="igig.integracao.one_per_canal",
        guard_name="idx_igig_integracao_canal",
        setup_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.integracao (org_id, canal) VALUES (v_org, 'smtp');",
        ),
        attack_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.integracao (org_id, canal) VALUES (v_org, 'smtp');"
        ),
        what="a second credential row for one channel in one org",
        rationale="`por_canal` reads ONE row per channel; a second would make which token is used arbitrary.",
        migrations=("010_igig_integracoes.sql",),
    ),
    _igig_probe(
        probe_id="igig.automacao.sla_requires_hours",
        guard_name="automacao_sla_com_horas",
        setup_sql=(_IGIG_STAGE,),
        attack_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.automacao (org_id, pipeline, etapa_id, gatilho) "
            "VALUES (v_org, 'comercial', v_stage, 'sla');"
        ),
        what="an SLA automation with no sla_horas",
        rationale="An SLA with no duration can never fire — a configured alert that silently never alerts.",
        migrations=_IGIG_CRM_MIGRATIONS,
    ),
    _igig_probe(
        probe_id="igig.apontamento.one_open_segment_per_user",
        guard_name="idx_igig_apontamento_aberto",
        setup_sql=(
            _IGIG_ESTEIRA_STAGE, _IGIG_CLIENTE,
            f"INSERT INTO {_IGIG_SCHEMA}.pauta (org_id, cliente_id, titulo) "
            "VALUES (v_org, v_cliente, 'NOC probe') RETURNING id INTO v_pauta;",
            f"INSERT INTO {_IGIG_SCHEMA}.tarefa (org_id, pauta_id, titulo, etapa_id) "
            "VALUES (v_org, v_pauta, 'NOC probe', v_stage) RETURNING id INTO v_tarefa;",
            f"INSERT INTO {_IGIG_SCHEMA}.apontamento (org_id, tarefa_id, usuario_id) "
            "VALUES (v_org, v_tarefa, v_org);",
        ),
        attack_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.apontamento (org_id, tarefa_id, usuario_id) "
            "VALUES (v_org, v_tarefa, v_org);"
        ),
        what="a second running timer for one user",
        rationale="Play pauses whatever else was running; two open segments double-count the hours billed as cost.",
        migrations=("006_igig_dominio.sql",),
    ),
    # 023 — Automações v1: the execution log's closed status set (incl. the
    # `executando` claim state) and one execution per (rule, card, entry).
    _igig_probe(
        probe_id="igig.automacao_execucao.status_closed_set",
        guard_name="automacao_execucao_status_check",
        setup_sql=(_IGIG_STAGE, _IGIG_AUTOMACAO),
        attack_sql=(
            f"INSERT INTO {_IGIG_SCHEMA}.automacao_execucao (org_id, automacao_id, entidade_id, status) "
            f"SELECT v_org, a.id, v_org, 'pendente' FROM {_IGIG_SCHEMA}.automacao a WHERE a.org_id = v_org;"
        ),
        what="an automation execution with a status outside the closed set",
        rationale="The Automações log and the engine's claim both key on the status set; an unknown "
                  "status is a row neither the log nor a retry can interpret.",
        migrations=_IGIG_AUTOMACOES_MIGRATIONS,
    ),
    _igig_probe(
        probe_id="igig.automacao_execucao.one_per_entry",
        guard_name="idx_igig_automacao_execucao_entrada",
        setup_sql=(
            _IGIG_STAGE, _IGIG_AUTOMACAO,
            f"INSERT INTO {_IGIG_SCHEMA}.pipeline_movimentos (org_id, pipeline, entidade_id, para_etapa_id) "
            "VALUES (v_org, 'comercial', v_org, v_stage);",
            _IGIG_EXECUCAO_DA_ENTRADA,
        ),
        attack_sql=_IGIG_EXECUCAO_DA_ENTRADA,
        what="a second execution of one automation for the same stage entry",
        rationale="The engine claims (rule, card, entry) before acting; without the unique index a move "
                  "racing the SLA sweep (or a retried request) runs the action — an e-mail, a WhatsApp — twice.",
        migrations=_IGIG_AUTOMACOES_MIGRATIONS,
    ),
    *_igig_card_hub_probes("cliente", (_IGIG_CLIENTE,), "v_cliente"),
    *_igig_card_hub_probes("negocio", (_IGIG_STAGE, _IGIG_LEAD, _IGIG_NEGOCIO), "v_negocio"),
)


# ---------------------------------------------------------------------------
# Registry — core.audit_logs append-only guard (migration 053).
# ---------------------------------------------------------------------------
#
# Fully self-provisioning: `audit_logs.user_id`/`.org_id` are nullable (no
# FK dependency to satisfy), so each probe inserts its own throwaway row —
# no production row is borrowed or touched. The `no_fixture` branch below
# only guards against `public.audit_logs` itself not existing (core's base
# migrations not applied) — a pre-053 database with the table already
# present correctly reports `permitted` (the trigger genuinely doesn't
# exist yet), the real finding, not a skip.

_CORE_AUDIT_LOGS_GUARD = "guard_audit_logs_append_only"
_CORE_AUDIT_LOGS_MIGRATIONS = ("053_audit_trail_expansion.sql",)


def _core_audit_log_probe(*, probe_id: str, op_sql: str, what: str) -> GuardProbe:
    fragment_lit = _sql_lit("audit_logs_append_only")
    what_lit = _sql_lit(what)
    sql = _do_block(f"""
DECLARE
  v_id uuid;
BEGIN
  IF to_regclass('public.audit_logs') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: public.audit_logs does not exist (core base migrations not applied)';
  END IF;
  BEGIN
    INSERT INTO public.audit_logs (action, resource_type, resource_id)
    VALUES ('noc_probe', 'noc_probe', 'noc-probe')
    RETURNING id INTO v_id;
{op_sql}
    RAISE EXCEPTION 'NOC_PROBE:permitted: {what_lit} succeeded — the append-only guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{fragment_lit}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
""")
    return GuardProbe(
        id=probe_id,
        product="core",
        schema="public",
        guard_name=_CORE_AUDIT_LOGS_GUARD,
        kind="write_refusal",
        migrations=_CORE_AUDIT_LOGS_MIGRATIONS,
        sql=sql,
        rationale=(
            "audit_logs is the platform action-history trail (migration 053, "
            "owner directive 2026-09-23) — a rewritable or deletable row "
            "proves nothing happened the way the trail says it did. UPDATE is "
            "refused unconditionally; DELETE is refused outside "
            "`public.purge_expired_audit_logs()`, the only sanctioned "
            "(400-day) retention door."
        ),
    )


_CORE_AUDIT_LOGS_PROBES: tuple[GuardProbe, ...] = (
    _core_audit_log_probe(
        probe_id="audit_logs.update_refused",
        op_sql="    UPDATE public.audit_logs SET action = 'tampered' WHERE id = v_id;",
        what="UPDATE of an audit_logs row",
    ),
    _core_audit_log_probe(
        probe_id="audit_logs.delete_refused_outside_purge",
        op_sql="    DELETE FROM public.audit_logs WHERE id = v_id;",
        what="DELETE of an audit_logs row outside purge_expired_audit_logs",
    ),
)


# ---------------------------------------------------------------------------
# Registry — public.ai_usage append-only guard (core migration 091, D25).
# ---------------------------------------------------------------------------
#
# Self-provisioning: org_id/user_id are nullable, so each probe inserts its
# own throwaway row inside the rollback-only wrapper. The ONE allowed write
# (charged_credits NULL -> value, the wallet's debit stamp) is exercised as
# setup in the re-stamp probe; the refusal under test is the SECOND stamp.

_CORE_AI_USAGE_GUARD = "guard_ai_usage_append_only"
_CORE_AI_USAGE_MIGRATIONS = ("091_ai_usage.sql",)


def _core_ai_usage_probe(*, probe_id: str, op_sql: str, what: str) -> GuardProbe:
    fragment_lit = _sql_lit("ai_usage_append_only")
    what_lit = _sql_lit(what)
    sql = _do_block(f"""
DECLARE
  v_id bigint;
BEGIN
  IF to_regclass('public.ai_usage') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: public.ai_usage does not exist (core migration 091 not applied)';
  END IF;
  BEGIN
    INSERT INTO public.ai_usage (product, provider, model, operation, fx_rate, price_version)
    VALUES ('noc-probe', 'noc-probe', 'noc-probe', 'chat', 5, 'noc-probe')
    RETURNING id INTO v_id;
{op_sql}
    RAISE EXCEPTION 'NOC_PROBE:permitted: {what_lit} succeeded — the append-only guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{fragment_lit}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
""")
    return GuardProbe(
        id=probe_id,
        product="core",
        schema="public",
        guard_name=_CORE_AI_USAGE_GUARD,
        kind="write_refusal",
        migrations=_CORE_AI_USAGE_MIGRATIONS,
        sql=sql,
        rationale=(
            "ai_usage is the central LLM billing ledger (D25) — every per-org / "
            "per-product charge is derived from it. A rewritable or deletable "
            "row is a rewritable bill. UPDATE / DELETE are refused for every "
            "role except the wallet's single charged_credits NULL -> value stamp."
        ),
    )


_CORE_AI_USAGE_PROBES: tuple[GuardProbe, ...] = (
    _core_ai_usage_probe(
        probe_id="ai_usage.update_refused",
        op_sql="    UPDATE public.ai_usage SET model = 'tampered' WHERE id = v_id;",
        what="UPDATE of an ai_usage row",
    ),
    _core_ai_usage_probe(
        probe_id="ai_usage.delete_refused",
        op_sql="    DELETE FROM public.ai_usage WHERE id = v_id;",
        what="DELETE of an ai_usage row",
    ),
    _core_ai_usage_probe(
        probe_id="ai_usage.charged_credits_restamp_refused",
        op_sql=(
            "    UPDATE public.ai_usage SET charged_credits = 1 WHERE id = v_id;\n"
            "    UPDATE public.ai_usage SET charged_credits = 2 WHERE id = v_id;"
        ),
        what="a second charged_credits stamp on an ai_usage row",
    ),
)


# ---------------------------------------------------------------------------
# Registry -- public.platform_templates (migration 092, admin > Templates).
# Self-provisioning: every probe inserts its own throwaway rows inside the rollback-only wrapper
# (a probe-only template key; nothing real is touched). (1) one version number per scope,
# (2) at most one ACTIVE version per scope, (3) the append-only trigger: a non-draft version is
# content-frozen and no row is ever deleted.
# ---------------------------------------------------------------------------

_PLATFORM_TEMPLATES_MIGRATIONS = ("092_platform_templates.sql",)


def _platform_templates_probe(*, probe_id: str, guard_name: str, setup_sql: str, what: str, fragment: str, rationale: str) -> GuardProbe:
    what_lit = _sql_lit(what)
    fragment_lit = _sql_lit(fragment)
    return GuardProbe(
        id=probe_id,
        product="core",
        schema="public",
        guard_name=guard_name,
        kind="write_refusal",
        migrations=_PLATFORM_TEMPLATES_MIGRATIONS,
        sql=_do_block(f"""
BEGIN
  IF to_regclass('public.platform_templates') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: public.platform_templates does not exist (migration 092 not applied)';
  END IF;
  BEGIN
{setup_sql}
    RAISE EXCEPTION 'NOC_PROBE:permitted: {what_lit} succeeded -- the guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{fragment_lit}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
        rationale=rationale,
    )


def _pt_insert(version: int, status: str) -> str:
    return (
        "    INSERT INTO public.platform_templates (kind, key, title, format, body, version, status)\n"
        f"    VALUES ('message', 'noc-probe', 'probe', 'text', 'x', {version}, '{status}');"
    )


_PLATFORM_TEMPLATES_PROBES: tuple[GuardProbe, ...] = (
    _platform_templates_probe(
        probe_id="platform_templates.duplicate_version_refused",
        guard_name="ux_platform_templates_version",
        setup_sql=_pt_insert(1, "draft") + "\n" + _pt_insert(1, "draft"),
        what="a second row with the same (product, kind, key, version)",
        fragment="ux_platform_templates_version",
        rationale="Version numbers are the audit trail of a template: two rows with the same number would make 'version N' ambiguous.",
    ),
    _platform_templates_probe(
        probe_id="platform_templates.two_active_refused",
        guard_name="ux_platform_templates_active",
        setup_sql=_pt_insert(1, "active") + "\n" + _pt_insert(2, "active"),
        what="two ACTIVE versions of the same template",
        fragment="ux_platform_templates_active",
        rationale="Consumers read THE active version; two would make the answer depend on row order.",
    ),
    _platform_templates_probe(
        probe_id="platform_templates.frozen_body_refused",
        guard_name="platform_templates_guard",
        setup_sql=_pt_insert(1, "active") + "\n    UPDATE public.platform_templates SET body = 'tampered' WHERE key = 'noc-probe';",
        what="editing the body of a non-draft version",
        fragment="is frozen",
        rationale="History is append-only: an edit is a NEW version, never a rewrite of one that was (or could have been) in use.",
    ),
    _platform_templates_probe(
        probe_id="platform_templates.delete_refused",
        guard_name="platform_templates_guard",
        setup_sql=_pt_insert(1, "draft") + "\n    DELETE FROM public.platform_templates WHERE key = 'noc-probe';",
        what="deleting a template version",
        fragment="append-only",
        rationale="Versions are archived, never deleted: the history must stay complete.",
    ),
)


# ---------------------------------------------------------------------------
# Registry — public.mfa_policy (migration 060, platform-admin-mfa).
# (1) mode CHECK refuses an unknown mode; (2) the table is SERVICE-ROLE-ONLY:
# `authenticated` (and `anon`) must not be able to write it — an admin who
# could would switch MFA off for themselves. Self-provisioning: each probe
# writes a throwaway scope inside the rollback-only wrapper.
# ---------------------------------------------------------------------------

_MFA_POLICY_MIGRATIONS = ("060_mfa_policy.sql",)


def _mfa_policy_probe(*, probe_id: str, guard_name: str, setup_sql: str, what: str, refused_test: str) -> GuardProbe:
    what_lit = _sql_lit(what)
    return GuardProbe(
        id=probe_id,
        product="core",
        schema="public",
        guard_name=guard_name,
        kind="write_refusal",
        migrations=_MFA_POLICY_MIGRATIONS,
        sql=_do_block(f"""
BEGIN
  IF to_regclass('public.mfa_policy') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: public.mfa_policy does not exist (migration 060 not applied)';
  END IF;
  BEGIN
{setup_sql}
    RAISE EXCEPTION 'NOC_PROBE:permitted: {what_lit} succeeded — the guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF {refused_test} THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
        rationale=(
            "mfa_policy is the admin-MFA off-switch/enforce switch. The mode "
            "CHECK keeps a typo from reading as a mode; service-role-only "
            "access keeps an admin from lowering their own assurance bar."
        ),
    )


_MFA_POLICY_PROBES: tuple[GuardProbe, ...] = (
    _mfa_policy_probe(
        probe_id="mfa_policy.mode_check_refuses_unknown",
        guard_name="mfa_policy_mode_check",
        setup_sql="    INSERT INTO public.mfa_policy (scope, mode) VALUES ('noc-probe', 'bogus');",
        what="INSERT of mfa_policy.mode='bogus'",
        refused_test=f"SQLERRM LIKE '%{_sql_lit('mfa_policy_mode_check')}%'",
    ),
    _mfa_policy_probe(
        probe_id="mfa_policy.authenticated_cannot_write",
        guard_name="mfa_policy_service_role_only",
        setup_sql=(
            "    SET LOCAL ROLE authenticated;\n"
            "    INSERT INTO public.mfa_policy (scope, mode) VALUES ('noc-probe', 'off');"
        ),
        what="INSERT into mfa_policy as role authenticated",
        refused_test="SQLSTATE = '42501'",
    ),
    _mfa_policy_probe(
        probe_id="mfa_policy.anon_cannot_write",
        guard_name="mfa_policy_service_role_only",
        setup_sql=(
            "    SET LOCAL ROLE anon;\n"
            "    INSERT INTO public.mfa_policy (scope, mode) VALUES ('noc-probe', 'off');"
        ),
        what="INSERT into mfa_policy as role anon",
        refused_test="SQLSTATE = '42501'",
    ),
)


# ---------------------------------------------------------------------------
# Registry — the 2026-10-10 ledger-checksum audit gaps: seed's anon table
# grants (seed 010) and erp.current_org_id()'s customer-role exclusion (SW 234).
# Both intents had been edited INTO already-applied files, so prod never got
# them; these probes pin that prod now holds them.
# ---------------------------------------------------------------------------

_SEED_ANON_LOCKDOWN_MIGRATIONS = ("010_anon_grant_lockdown.sql",)

_SEED_ANON_LOCKDOWN_PROBES: tuple[GuardProbe, ...] = (
    GuardProbe(
        id="seed.anon_insert_refused_by_privilege",
        product="seed",
        schema="seed",
        guard_name="seed_anon_grant_lockdown",
        kind="write_refusal",
        migrations=_SEED_ANON_LOCKDOWN_MIGRATIONS,
        sql=_do_block("""
BEGIN
  IF to_regclass('seed.examples') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: seed.examples does not exist';
  END IF;
  BEGIN
    SET LOCAL ROLE anon;
    INSERT INTO seed.examples DEFAULT VALUES;
    RAISE EXCEPTION 'NOC_PROBE:permitted: INSERT into seed.examples as role anon succeeded — the guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLSTATE = '42501' AND SQLERRM LIKE 'permission denied%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      -- an RLS refusal ("new row violates row-level security policy") is ALSO
      -- 42501, but it means the GRANT is still there: not this guard.
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: refused by something other than the missing grant: %', SQLERRM;
    END IF;
  END;
END;
"""),
        rationale=(
            "anon must hold no write privilege in the seed schema: RLS alone stood "
            "between the public anon key and seed's tables until 010 (2026-10-10)."
        ),
    ),
    GuardProbe(
        id="seed.anon_only_reads_status_pagina",
        product="seed",
        schema="seed",
        guard_name="seed_anon_grant_lockdown",
        kind="state_assertion",
        migrations=_SEED_ANON_LOCKDOWN_MIGRATIONS,
        sql=_state_assertion_probe(
            select_count_sql=(
                "SELECT (SELECT count(*) FROM information_schema.role_table_grants"
                " WHERE grantee = 'anon' AND table_schema = 'seed'"
                " AND NOT (table_name = 'status_pagina' AND privilege_type = 'SELECT'))"
                " + (SELECT count(*) FROM pg_default_acl d JOIN pg_namespace n ON n.oid = d.defaclnamespace"
                " WHERE n.nspname = 'seed' AND d.defaclacl::text LIKE '%anon=%')"
                " INTO v_count;"
            ),
            clean_message="anon holds only SELECT on seed.status_pagina; no anon default privileges in seed",
            violation_message_prefix="anon table privilege(s) / default ACL entries LIVE in seed —",
        ),
        rationale=(
            "The public route map is the only seed table anon may read; any other "
            "grant (or a default ACL re-granting future tables) reopens the gap."
        ),
    ),
)

def _anon_sequence_probe(product: str, schema: str, migration: str) -> GuardProbe:
    """anon holds no privilege on any sequence in ``schema``, now or by default
    (the template 001's sequence grant to anon, cleared fleet-wide 2026-10-10)."""
    return GuardProbe(
        id=f"{schema}.anon_holds_no_sequence_privilege",
        product=product,
        schema=schema,
        guard_name=f"{schema}_anon_sequence_lockdown",
        kind="state_assertion",
        migrations=(migration,),
        sql=_state_assertion_probe(
            select_count_sql=(
                "SELECT (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                f" WHERE n.nspname = '{schema}' AND c.relkind = 'S' AND c.relacl::text LIKE '%anon=%')"
                " + (SELECT count(*) FROM pg_default_acl d JOIN pg_namespace n ON n.oid = d.defaclnamespace"
                f" WHERE n.nspname = '{schema}' AND d.defaclobjtype = 'S' AND d.defaclacl::text LIKE '%anon=%')"
                " INTO v_count;"
            ),
            clean_message=f"anon holds no sequence privilege in {schema} (existing or default)",
            violation_message_prefix=f"anon sequence privilege(s) / default ACL entries LIVE in {schema} —",
        ),
        rationale=(
            "anon writes no product table, so it never needs nextval(); a sequence grant "
            "only lets the public anon key burn values and read last_value."
        ),
    )


_ANON_SEQUENCE_PROBES: tuple[GuardProbe, ...] = (
    _anon_sequence_probe("seed", "seed", "011_anon_sequence_lockdown.sql"),
    _anon_sequence_probe("social-wiring", "social_wiring", "235_anon_sequence_lockdown.sql"),
    _anon_sequence_probe("agents", "agents", "023_anon_sequence_lockdown.sql"),
    _anon_sequence_probe("igig", "igig", "041_anon_sequence_lockdown.sql"),
    _anon_sequence_probe("academia-de-reciclagem", "academia_de_reciclagem", "018_anon_sequence_lockdown.sql"),
)

def _ai_tables_probe(product: str, schema: str, migration: str, guard: str, table: str,
                     insert_sql: str, sqlstate: str, rationale: str | None = None) -> GuardProbe:
    """Self-provisioning write-refusal probe: ``insert_sql`` (which may use the
    throwaway ``v_org`` / ``v_user`` uuids) must be refused by ``guard`` with
    ``sqlstate``. Born for the canonical seed AI tables
    (``sql_templates.ai_outputs_table_sql`` / ``ai_feedback_table_sql``); any
    single-row CHECK / UNIQUE guard reuses it."""
    return GuardProbe(
        id=f"{schema}.{guard}",
        product=product,
        schema=schema,
        guard_name=guard,
        kind="write_refusal",
        migrations=(migration,),
        sql=_do_block(f"""
DECLARE
  v_org uuid := gen_random_uuid();
  v_user uuid := gen_random_uuid();
BEGIN
  IF to_regclass('{schema}.{table}') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: {schema}.{table} does not exist';
  END IF;
  BEGIN
    {insert_sql};
    RAISE EXCEPTION 'NOC_PROBE:permitted: {guard} did not refuse the write';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLSTATE = '{sqlstate}' AND SQLERRM LIKE '%{guard}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
        rationale=rationale or f"{schema}.{table}: {guard} keeps an out-of-contract AI output / feedback row out.",
    )


def _ai_tables_probes(product: str, schema: str, migration: str) -> tuple[GuardProbe, ...]:
    o, f = f"{schema}.ai_outputs", f"{schema}.ai_feedback"
    return (
        _ai_tables_probe(product, schema, migration, "ai_outputs_kind_check", "ai_outputs",
            f"INSERT INTO {o} (org_id, ref_type, ref_id, kind, label) VALUES (v_org, 'noc-probe', gen_random_uuid(), 'bogus', 'x')", "23514"),
        _ai_tables_probe(product, schema, migration, "ai_outputs_confidence_range", "ai_outputs",
            f"INSERT INTO {o} (org_id, ref_type, ref_id, kind, label, confidence) VALUES (v_org, 'noc-probe', gen_random_uuid(), 'score', 'x', 2)", "23514"),
        _ai_tables_probe(product, schema, migration, "ai_feedback_rating_check", "ai_feedback",
            f"INSERT INTO {f} (org_id, user_id, output_ref, rating) VALUES (v_org, v_user, 'noc-probe', 5)", "23514"),
        _ai_tables_probe(product, schema, migration, "ai_feedback_user_ref_unique", "ai_feedback",
            f"INSERT INTO {f} (org_id, user_id, output_ref, rating) VALUES (v_org, v_user, 'noc-probe', 1), (v_org, v_user, 'noc-probe', -1)", "23505"),
    )


_SW_AI_TABLES_PROBES = _ai_tables_probes("social-wiring", "social_wiring", "239_ai_outputs_ai_feedback.sql")

# Migration 244 (email-marketing P1b(d), double opt-in): an out-of-contract
# opt-in state would bypass the send gate (only 'not_required' / 'confirmed'
# receive marketing email). Same self-provisioning write-refusal shape.
_SW_CONTACTS_EMAIL_OPTIN_PROBE = _ai_tables_probe(
    "social-wiring", "social_wiring", "244_contacts_email_optin.sql",
    "contacts_email_optin_check", "contacts",
    "INSERT INTO social_wiring.contacts (org_id, email, email_optin) "
    "VALUES (v_org, 'noc-probe@example.invalid', 'bogus')",
    "23514",
    rationale="social_wiring.contacts: an email_optin outside not_required|pending|confirmed would slip past the double opt-in send gate.",
)

# Migration 249 (P6): resultado_origem gains 'texto' (verdict read from the
# issuer's printed sentence). The widened CHECK must still refuse anything
# outside api|texto|ia|manual — an unknown origin would hide who decided a
# certidão's verdict.
_SW_CERTIDAO_RESULTADO_ORIGEM_PROBE = _ai_tables_probe(
    "social-wiring", "social_wiring", "249_certidao_resultado_origem_texto.sql",
    "certidao_resultados_resultado_origem_check", "certidao_resultados",
    "INSERT INTO social_wiring.certidao_resultados (consulta_id, org_id, tipo, nome_display, resultado_origem) "
    "VALUES (gen_random_uuid(), v_org, 'trf3', 'noc-probe', 'bogus')",
    "23514",
    rationale="social_wiring.certidao_resultados: a resultado_origem outside api|texto|ia|manual would hide who decided the verdict.",
)

# Migration 250 (Roteiro Avançado, owner decision 2026-10-11): a roteiro's
# beat order is cta_inicio | cta_final (values renamed by 253). An unknown structure would make the
# worker pick no prompt (the row fails) and the UI show a structure that does
# not exist. The CHECK fires before the (fabricated) org/marca FKs, which are
# deferred to the end of the statement.
_SW_250_ESTRUTURA_PROBE = _ai_tables_probe(
    "social-wiring", "social_wiring", "250_cs_roteiros_estrutura.sql",
    "cs_roteiros_estrutura_check", "cs_roteiros",
    "INSERT INTO social_wiring.cs_roteiros (org_id, marca_id, nome, headline_texto, estrutura) "
    "VALUES (v_org, gen_random_uuid(), 'noc-probe', 'noc-probe', 'bogus')",
    "23514",
    rationale="social_wiring.cs_roteiros: an estrutura outside cta_inicio|cta_final has no prompt and no UI label.",
)

# Migration 251 (org-level favorecidos registry): one ACTIVE payee per document
# per org (alphanumeric-normalized). Two rows differing only in punctuation must
# collide — a duplicate payee splits one person's bank account across entries.
_SW_251_FAVORECIDOS_UNIQUE_PROBE = _ai_tables_probe(
    "social-wiring", "social_wiring", "251_favorecidos_registry.sql",
    "uq_sw_favorecidos_org_documento", "favorecidos",
    "INSERT INTO social_wiring.favorecidos (org_id, nome, tipo_pessoa, cpf_cnpj, pix) "
    "VALUES (v_org, 'noc-probe-a', 'PF', '529.982.247-25', 'x'), "
    "(v_org, 'noc-probe-b', 'PF', '52998224725', 'y')",
    "23505",
    rationale="social_wiring.favorecidos: two active entries for the same CPF/CNPJ in one org must be refused.",
)

_ERP_CURRENT_ORG_ID_PROBE = GuardProbe(
    id="erp.current_org_id_excludes_customer",
    product="social-wiring",
    schema="erp",
    guard_name="erp_current_org_id_customer_exclusion",
    kind="state_assertion",
    migrations=("234_erp_current_org_id_customer_roles.sql",),
    sql=_state_assertion_probe(
        select_count_sql=(
            "SELECT count(*) INTO v_count FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace"
            " WHERE n.nspname = 'erp' AND p.proname = 'current_org_id'"
            " AND pg_get_functiondef(p.oid) NOT LIKE '%membro%';"
        ),
        clean_message="erp.current_org_id() excludes customer roles (or erp is absent)",
        violation_message_prefix="erp.current_org_id() still returns a customer's org —",
    ),
    rationale=(
        "183 erp policies call erp.current_org_id(); without the 'membro' exclusion "
        "a customer user reads their org's erp rows through PostgREST."
    ),
)


# ---------------------------------------------------------------------------
# Registry — public.erase_test_org_audit_logs's own org-category guard
# (migration 054). Companion to _CORE_AUDIT_LOGS_PROBES above: that pair
# proves the append-only TRIGGER still refuses a plain UPDATE/DELETE
# (unchanged by 054); this probe proves the new erasure FUNCTION refuses to
# even attempt the delete for anything that isn't a
# `category = 'test' AND slug LIKE 'test-realdb-%'` organization — a
# real ('normal'-category) org, in this case. Self-provisioning: the probe
# INSERTs its own throwaway `organizations` row (inside the same
# rollback-only wrapper every probe runs under — never a real org, never
# committed) rather than borrowing one from `tests/realdb`.

_ERASE_TEST_ORG_AUDIT_LOGS_GUARD = "erase_test_org_audit_logs"
_ERASE_TEST_ORG_AUDIT_LOGS_MIGRATIONS = ("054_erase_test_org_audit_logs.sql",)

_ERASE_TEST_ORG_AUDIT_LOGS_PROBE = GuardProbe(
    id="erase_test_org_audit_logs.refuses_non_test_org",
    product="core",
    schema="public",
    guard_name=_ERASE_TEST_ORG_AUDIT_LOGS_GUARD,
    kind="write_refusal",
    migrations=_ERASE_TEST_ORG_AUDIT_LOGS_MIGRATIONS,
    sql=_do_block(f"""
DECLARE
  v_org uuid;
BEGIN
  IF to_regprocedure('public.erase_test_org_audit_logs(uuid)') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: public.erase_test_org_audit_logs does not exist (migration 054 not applied)';
  END IF;
  BEGIN
    INSERT INTO public.organizations (nome, slug, category)
    VALUES ('NOC probe org (not a test-realdb fixture)', 'noc-probe-' || gen_random_uuid()::text, 'normal')
    RETURNING id INTO v_org;
    PERFORM public.erase_test_org_audit_logs(v_org);
    RAISE EXCEPTION 'NOC_PROBE:permitted: erase_test_org_audit_logs erased a normal-category org — the org-category guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{_sql_lit("org_not_erasable_test_org")}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
    rationale=(
        "erase_test_org_audit_logs (migration 054) is the second sanctioned "
        "audit_logs deletion door, opened specifically so the realdb test "
        "suite can tear down its own throwaway orgs (053 made audit_logs "
        "append-only, and the org<->audit_logs FK is NO ACTION, so a "
        "category='test' org that had ever logged an action could never be "
        "deleted). It must refuse anything that isn't a "
        "`category = 'test' AND slug LIKE 'test-realdb-%'` org — a real org "
        "reaching this function would otherwise have its entire audit trail "
        "erased through what is nominally a test-fixture cleanup path."
    ),
)


# ---------------------------------------------------------------------------
# Registry — SEC-2 customer-role isolation (2026-09-28): the shared
# `public.current_org_id()` family + the fleet-wide invitations.token lockdown
# (core 055 + every product's *_customer_role_isolation.sql).
# ---------------------------------------------------------------------------
#
# Not a trigger/CHECK — the "guard" is a FUNCTION every org-scoped RLS policy
# in every schema calls, so its behaviour IS the fleet's customer isolation.
# Self-provisioning: the probe inserts a throwaway org + one staff + one
# customer `noctus_users` row inside the rollback-only wrapper, impersonates
# each through the same JWT settings auth.uid() reads, and asserts the answers.
# Structure-green (the function exists) is not behaviour-green (it returns NULL
# for a customer) — a stale re-declaration from ANY chain would still "exist".

_CUSTOMER_ISOLATION_MIGRATIONS = ("055_customer_role_isolation.sql",)

_CUSTOMER_GETS_NO_ORG_PROBE = GuardProbe(
    id="org_identity.customer_gets_no_org",
    product="core",
    schema="public",
    guard_name="current_org_id",
    kind="state_assertion",
    migrations=_CUSTOMER_ISOLATION_MIGRATIONS,
    sql=_do_block("""
DECLARE
  v_org uuid;
  v_staff uuid := gen_random_uuid();
  v_cust uuid := gen_random_uuid();
  v_staff_org uuid;
  v_cust_org uuid;
  v_cust_is boolean;
  v_cust_customer_org uuid;
BEGIN
  IF to_regprocedure('public.is_customer()') IS NULL
     OR to_regprocedure('public.current_customer_org_id()') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: public.is_customer()/current_customer_org_id() missing — customer-role isolation (core 055) not applied';
  END IF;
  BEGIN
    INSERT INTO public.organizations (nome, slug)
    VALUES ('NOC probe org (customer isolation)', 'noc-probe-' || gen_random_uuid()::text)
    RETURNING id INTO v_org;
    -- Real profiles always follow their auth user; core 079's membership mirror
    -- (org_memberships.user_id → auth.users) refuses a profile without one.
    INSERT INTO auth.users (id, email) VALUES
      (v_staff, 'noc-probe-staff@invalid'),
      (v_cust,  'noc-probe-cust@invalid');
    INSERT INTO public.noctus_users (id, email, nome, org_id, role, org_role) VALUES
      (v_staff, 'noc-probe-staff@invalid', 'noc probe staff', v_org, 'user', 'member'),
      (v_cust,  'noc-probe-cust@invalid',  'noc probe customer', v_org, 'user', 'membro');
  EXCEPTION WHEN OTHERS THEN
    RAISE EXCEPTION 'NOC_PROBE:ambiguous: could not self-provision the probe org/users: %', SQLERRM;
  END;

  PERFORM set_config('request.jwt.claim.sub', v_staff::text, true);
  PERFORM set_config('request.jwt.claims', json_build_object('sub', v_staff, 'role', 'authenticated')::text, true);
  v_staff_org := public.current_org_id();

  PERFORM set_config('request.jwt.claim.sub', v_cust::text, true);
  PERFORM set_config('request.jwt.claims', json_build_object('sub', v_cust, 'role', 'authenticated')::text, true);
  v_cust_org := public.current_org_id();
  v_cust_is := public.is_customer();
  v_cust_customer_org := public.current_customer_org_id();

  IF v_staff_org IS DISTINCT FROM v_org THEN
    RAISE EXCEPTION 'NOC_PROBE:ambiguous: staff current_org_id() = % (expected %) — the probe cannot impersonate through auth.uid()', v_staff_org, v_org;
  END IF;
  IF v_cust_org IS NOT NULL OR NOT v_cust_is OR v_cust_customer_org IS DISTINCT FROM v_org THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: customer current_org_id()=% is_customer()=% current_customer_org_id()=% — a customer inherits org-member RLS fleet-wide', v_cust_org, v_cust_is, v_cust_customer_org;
  END IF;
  RAISE EXCEPTION 'NOC_PROBE:clean: customer gets NULL from current_org_id(), staff gets their org';
END;
"""),
    rationale=(
        "End customers (org_role in CUSTOMER_ORG_ROLES) self-register into the "
        "platform's own org, which is licensed to most products. Every org-scoped "
        "RLS policy fleet-wide keys on public.current_org_id(); if it answers a "
        "customer's org, the customer reads/writes every licensed product's back "
        "office. The function is re-declared by many migration chains — a stale "
        "copy applied last re-opens it while still 'existing', so only a behaviour "
        "probe proves the exclusion holds (SEC-2, 2026-09-28)."
    ),
)

# ---------------------------------------------------------------------------
# Registry — pre-existing guards in chains SEC-2 re-rendered in place
# (core 001, social-wiring 001). Touching those files put these long-standing,
# never-probed guards in the diff-scoped `migration-guard-has-probe` gate;
# fix-on-contact: prove they refuse. Self-provisioning (a throwaway org per
# probe, inside the rollback-only wrapper) and classified by SQLSTATE +
# constraint name via GET STACKED DIAGNOSTICS, not by message text.
# ---------------------------------------------------------------------------


def _constraint_refusal_probe(
    *,
    setup_sql: str,
    op_sql: str,
    sqlstate_condition: str,
    constraint_names: tuple[str, ...],
    what: str,
) -> str:
    what_lit = _sql_lit(what)
    names = ", ".join("'" + _sql_lit(n) + "'" for n in constraint_names)
    return _do_block(f"""
DECLARE
  v_org uuid;
  v_prod uuid;
  v_constraint text;
BEGIN
{setup_sql}
  BEGIN
{op_sql}
    RAISE EXCEPTION 'NOC_PROBE:permitted: {what_lit} succeeded — the guard did not fire';
  EXCEPTION
    WHEN {sqlstate_condition} THEN
      GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
      IF v_constraint = ANY (ARRAY[{names}]) THEN
        RAISE EXCEPTION 'NOC_PROBE:refused: % refused by %', '{what_lit}', v_constraint;
      END IF;
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: refused by an unexpected constraint %', v_constraint;
    WHEN OTHERS THEN
      IF SQLERRM LIKE 'NOC_PROBE:%' THEN
        RAISE;
      END IF;
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
  END;
END;
""")


def _table_fixture_check(qualified: str) -> str:
    return (
        f"  IF to_regclass('{qualified}') IS NULL THEN\n"
        f"    RAISE EXCEPTION 'NOC_PROBE:no_fixture: {_sql_lit(qualified)} does not exist (migrations not applied)';\n"
        "  END IF;\n"
    )


_PROBE_ORG_SETUP = _table_fixture_check("public.organizations") + """
  INSERT INTO public.organizations (nome, slug)
  VALUES ('NOC probe org (guard)', 'noc-probe-' || gen_random_uuid()::text)
  RETURNING id INTO v_org;
"""

_LICENSES_ONE_ACTIVE_PROBE = GuardProbe(
    id="licenses.one_active_per_org_product",
    product="core",
    schema="public",
    guard_name="idx_licenses_one_active_per_org_product",
    kind="write_refusal",
    migrations=("001_noctusai_core.sql",),
    sql=_constraint_refusal_probe(
        setup_sql="""
  SELECT id INTO v_prod FROM public.products LIMIT 1;
  IF v_prod IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no public.products row to license';
  END IF;
""" + _PROBE_ORG_SETUP,
        op_sql="""
    INSERT INTO public.licenses (org_id, product_id, status) VALUES (v_org, v_prod, 'active');
    INSERT INTO public.licenses (org_id, product_id, status) VALUES (v_org, v_prod, 'active');
""",
        sqlstate_condition="unique_violation",
        constraint_names=("idx_licenses_one_active_per_org_product",),
        what="a second ACTIVE license for the same org+product",
    ),
    rationale=(
        "Licensing is the gate core's SSO bridge checks before minting a "
        "product token; two active rows for one org+product make expiry and "
        "revocation ambiguous (which row wins?). Historical revoked/expired "
        "rows stay unrestricted by design (partial index)."
    ),
)

_SW_API_TOKEN_HASH_PROBE = GuardProbe(
    id="social_wiring.api_tokens.active_hash_unique",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="idx_sw_api_tokens_hash_active",
    kind="write_refusal",
    migrations=("001_social-wiring.sql",),
    sql=_constraint_refusal_probe(
        setup_sql=_table_fixture_check("social_wiring.api_tokens") + _PROBE_ORG_SETUP,
        op_sql="""
    INSERT INTO social_wiring.api_tokens (org_id, label, token_hash, token_prefix)
    VALUES (v_org, 'noc probe a', 'noc-probe-hash', 'noc_'),
           (v_org, 'noc probe b', 'noc-probe-hash', 'noc_');
""",
        sqlstate_condition="unique_violation",
        # The column-level UNIQUE(token_hash) from the same CREATE TABLE is
        # strictly stronger and is checked first — either index refusing
        # proves the claim "two live tokens never share a hash".
        constraint_names=("idx_sw_api_tokens_hash_active", "api_tokens_token_hash_key"),
        what="two live api_tokens with the same token_hash",
    ),
    rationale=(
        "api_tokens authenticate machine callers by token_hash; a duplicate "
        "live hash would make one token resolve to two orgs' principals."
    ),
)

_SW_ONE_PRIMARY_MARCA_PROBE = GuardProbe(
    id="social_wiring.marcas.one_primary_per_org",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="uq_marcas_one_primary_per_org",
    kind="write_refusal",
    migrations=("210_marca_primary_per_org.sql",),
    sql=_constraint_refusal_probe(
        setup_sql=_table_fixture_check("social_wiring.marcas") + _PROBE_ORG_SETUP,
        op_sql="""
    INSERT INTO social_wiring.marcas (org_id, slug, name, is_primary)
    VALUES (v_org, 'noc-probe-a', 'NOC probe a', true),
           (v_org, 'noc-probe-b', 'NOC probe b', true);
""",
        sqlstate_condition="unique_violation",
        constraint_names=("uq_marcas_one_primary_per_org",),
        what="a second primary marca in the same org",
    ),
    rationale=(
        "An org owns ONE brand identity that its products inherit (owner "
        "2026-10-07); two primaries make which identity a product renders "
        "ambiguous."
    ),
)

_SW_ONE_PRIMARY_KIT_PROBE = GuardProbe(
    id="social_wiring.mc_brand_kits.one_primary_per_marca",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="uq_mc_brand_kits_one_primary_per_marca",
    kind="write_refusal",
    migrations=("210_marca_primary_per_org.sql",),
    sql=_constraint_refusal_probe(
        # `v_prod` is the helper's spare uuid slot — here it holds the probe marca.
        setup_sql=_table_fixture_check("social_wiring.mc_brand_kits") + _PROBE_ORG_SETUP + """
  INSERT INTO social_wiring.marcas (org_id, slug, name)
  VALUES (v_org, 'noc-probe-marca', 'NOC probe marca')
  RETURNING id INTO v_prod;
""",
        op_sql="""
    INSERT INTO social_wiring.mc_brand_kits (org_id, marca_id, name, is_primary)
    VALUES (v_org, v_prod, 'NOC probe kit a', true),
           (v_org, v_prod, 'NOC probe kit b', true);
""",
        sqlstate_condition="unique_violation",
        constraint_names=("uq_mc_brand_kits_one_primary_per_marca",),
        what="a second primary brand kit for the same marca",
    ),
    rationale=(
        "The marca's primary kit is the identity its products render; two "
        "primaries make the rendered identity ambiguous."
    ),
)

_SW_RECIPIENT_CHANNEL_PROBE = GuardProbe(
    id="social_wiring.notification_recipients.has_channel",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="recipient_has_at_least_one_channel",
    kind="write_refusal",
    migrations=("001_social-wiring.sql",),
    sql=_constraint_refusal_probe(
        setup_sql=_table_fixture_check("social_wiring.notification_recipients") + _PROBE_ORG_SETUP,
        op_sql="""
    INSERT INTO social_wiring.notification_recipients (org_id, name, email, whatsapp_number)
    VALUES (v_org, 'noc probe', NULL, NULL);
""",
        sqlstate_condition="check_violation",
        constraint_names=("recipient_has_at_least_one_channel",),
        what="a notification recipient with neither email nor whatsapp",
    ),
    rationale=(
        "A recipient with no channel silently swallows every notification "
        "routed to it — the dispatcher has nowhere to send and reports nothing."
    ),
)


_INVITATION_TOKEN_PROBE = GuardProbe(
    id="invitations.token_not_api_readable",
    product="<platform>",
    schema="*",
    guard_name="invitations.token",
    kind="state_assertion",
    # 055 + every product's *_customer_role_isolation.sql cover the awake
    # chains; core 056 sweeps every remaining schema (asleep/legacy included).
    migrations=(*_CUSTOMER_ISOLATION_MIGRATIONS, "056_invitation_token_lockdown_all_schemas.sql"),
    rationale=(
        "An invitations.token read through the API roles lets any org member "
        "(and, before SEC-2, a self-registered customer) accept a pending invite "
        "meant for someone else — at the invited role. The invite flow reads and "
        "validates tokens with the service role only. A later `GRANT ... ON ALL "
        "TABLES IN SCHEMA` silently re-opens the column, so this is asserted on "
        "live privileges, platform-wide (every schema's invitations table)."
    ),
    sql=_state_assertion_probe(
        select_count_sql=(
            "SELECT count(*) INTO v_count FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relname = 'invitations' AND c.relkind = 'r' "
            "AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attname = 'token' AND NOT a.attisdropped) "
            "AND (has_column_privilege('authenticated', c.oid, 'token', 'SELECT') "
            "OR has_column_privilege('anon', c.oid, 'token', 'SELECT'));"
        ),
        clean_message="0 invitations tables expose token to anon/authenticated",
        violation_message_prefix="invitations table(s) expose token to anon/authenticated —",
    ),
)


# ---------------------------------------------------------------------------
# Registry — community, migration 013 (Ninho Vazio). Fresh-org probes: every
# community `org_id` is FK-less, so each probe builds its own chain.
# ---------------------------------------------------------------------------

_COMMUNITY_SCHEMA = "community"
_COMMUNITY_013 = ("013_ninho_vazio.sql",)
_C = _COMMUNITY_SCHEMA
_COMMUNITY_PLANO = (
    f"INSERT INTO {_C}.planos (org_id, nome, preco_centavos, ciclo) "
    "VALUES (v_org, 'NOC probe', 700, 'mensal') RETURNING id INTO v_plano;"
)
_COMMUNITY_MEMBRO = (
    f"INSERT INTO {_C}.membros (org_id, nome, email, status, origem) "
    "VALUES (v_org, 'NOC probe', 'noc-probe@example.invalid', 'ativo', 'cadastro') RETURNING id INTO v_membro;"
)
_COMMUNITY_PAGAMENTO_CHAIN = (
    _COMMUNITY_PLANO,
    _COMMUNITY_MEMBRO,
    f"INSERT INTO {_C}.assinaturas (org_id, membro_id, plano_id, gateway, estado, metodo, ciclo) "
    "VALUES (v_org, v_membro, v_plano, 'asaas', 'ativa', 'pix', 'mensal') RETURNING id INTO v_assinatura;",
    f"INSERT INTO {_C}.pagamentos (org_id, assinatura_id, membro_id, gateway, cobranca_externa_id, valor_centavos, metodo, estado) "
    "VALUES (v_org, v_assinatura, v_membro, 'asaas', 'noc-probe-' || gen_random_uuid()::text, 700, 'pix', 'pago') RETURNING id INTO v_pagamento;",
)
_COMMUNITY_VARS = ("v_plano uuid", "v_membro uuid", "v_assinatura uuid", "v_pagamento uuid")


def _community_probe(**kw: Any) -> GuardProbe:
    return _fresh_org_write_refusal_probe(
        product="community", schema=_C, exists_table="grupoterapia_reservas",
        exists_migration="013", declare_vars=_COMMUNITY_VARS, migrations=_COMMUNITY_013, **kw,
    )


_COMMUNITY_PROBES: tuple[GuardProbe, ...] = (
    _community_probe(
        probe_id="community.membros.origem_check",
        guard_name="membros_origem_check",
        setup_sql=(),
        attack_sql=(
            f"INSERT INTO {_C}.membros (org_id, nome, email, status, origem) "
            "VALUES (v_org, 'NOC probe', 'noc-probe@example.invalid', 'ativo', 'inventada');"
        ),
        what="a membro with an unknown origem",
        rationale=(
            "origem drives the dashboard's members-by-origin series; an "
            "unlisted value would silently fall out of every breakdown."
        ),
    ),
    _community_probe(
        probe_id="community.membros.one_login_per_membro",
        guard_name="membros_org_user_unique",
        setup_sql=(
            f"INSERT INTO {_C}.membros (org_id, nome, email, status, origem, user_id) "
            "VALUES (v_org, 'A', 'a@example.invalid', 'ativo', 'cadastro', v_org);",
        ),
        attack_sql=(
            f"INSERT INTO {_C}.membros (org_id, nome, email, status, origem, user_id) "
            "VALUES (v_org, 'B', 'b@example.invalid', 'ativo', 'cadastro', v_org);"
        ),
        what="two membros linked to the same login in one org",
        rationale=(
            "get_membro_context resolves the caller's membro by user_id; two "
            "rows would make which plan, payments and grupoterapia seat a "
            "member sees depend on read order."
        ),
    ),
    _community_probe(
        probe_id="community.assinaturas.estado_check",
        guard_name="assinaturas_estado_check",
        setup_sql=(_COMMUNITY_PLANO, _COMMUNITY_MEMBRO),
        attack_sql=(
            f"INSERT INTO {_C}.assinaturas (org_id, membro_id, plano_id, gateway, estado, metodo, ciclo) "
            "VALUES (v_org, v_membro, v_plano, 'asaas', 'suspensa', 'pix', 'mensal');"
        ),
        what="an assinatura in an unknown estado",
        rationale=(
            "Every lifecycle move is validated against the seed "
            "SubscriptionState machine through a fixed pt-BR mapping; a state "
            "outside it could never be moved again, nor be counted in MRR or churn."
        ),
    ),
    _community_probe(
        probe_id="community.lancamentos.one_entrada_per_pagamento",
        guard_name="lancamentos_pagamento_unique",
        setup_sql=(
            *_COMMUNITY_PAGAMENTO_CHAIN,
            f"INSERT INTO {_C}.lancamentos (org_id, tipo, categoria, valor_centavos, data, origem, pagamento_id) "
            "VALUES (v_org, 'entrada', 'assinatura', 700, current_date, 'pagamento', v_pagamento);",
        ),
        attack_sql=(
            f"INSERT INTO {_C}.lancamentos (org_id, tipo, categoria, valor_centavos, data, origem, pagamento_id) "
            "VALUES (v_org, 'entrada', 'assinatura', 700, current_date, 'pagamento', v_pagamento);"
        ),
        what="a second cashflow entrada for one paid charge",
        rationale=(
            "Gateways redeliver webhooks; the unique index is what makes a "
            "replayed charge_paid book revenue once instead of twice."
        ),
    ),
    _community_probe(
        probe_id="community.lancamentos.one_estorno_per_pagamento",
        guard_name="lancamentos_estorno_unique",
        setup_sql=(
            *_COMMUNITY_PAGAMENTO_CHAIN,
            f"INSERT INTO {_C}.lancamentos (org_id, tipo, categoria, valor_centavos, data, origem, estorno_de) "
            "VALUES (v_org, 'saida', 'estorno', 700, current_date, 'estorno', v_pagamento);",
        ),
        attack_sql=(
            f"INSERT INTO {_C}.lancamentos (org_id, tipo, categoria, valor_centavos, data, origem, estorno_de) "
            "VALUES (v_org, 'saida', 'estorno', 700, current_date, 'estorno', v_pagamento);"
        ),
        what="a second cashflow saida for one refund",
        rationale=(
            "Same replay protection on the refund side: one estorno per "
            "refunded charge, however many times the webhook arrives."
        ),
    ),
)


# ---------------------------------------------------------------------------
# Registry — migrations 179-183 (social-wiring, project atendimento-partes-
# imoveis): the CHECK / partial-UNIQUE guards of the atendimento-parties and
# imóvel-junction tables. Each probe borrows deterministic existing rows
# (fail-closed `no_fixture` when absent), runs the forbidden write, and
# classifies by the violated CONSTRAINT_NAME (a CHECK raises
# `check_violation`, a unique index `unique_violation`; both carry the
# constraint/index name). FK columns are filled from real rows because the
# FKs are checked at statement end — after the CHECK / unique guards fire.
# ---------------------------------------------------------------------------

_SW_FIXTURES: dict[str, tuple[str, str]] = {
    "registry": (
        "SELECT org_id, codigo_canonical FROM social_wiring.imovel_registry LIMIT 1",
        "v_org, v_codigo",
    ),
    # `atendimento` supplies the id only (org comes from `registry`, which the
    # (org_id, codigo) FK needs); `atendimento_org` also supplies the org, for
    # the probes that carry no registry fixture.
    "atendimento": (
        "SELECT id FROM social_wiring.atendimentos LIMIT 1",
        "v_atendimento",
    ),
    "atendimento_org": (
        "SELECT org_id, id FROM social_wiring.atendimentos LIMIT 1",
        "v_org, v_atendimento",
    ),
    "cliente": (
        "SELECT id FROM social_wiring.clientes LIMIT 1",
        "v_cliente",
    ),
    "empresa": (
        "SELECT id FROM social_wiring.empresas LIMIT 1",
        "v_empresa",
    ),
}


def _sw_junction_probe(
    *,
    probe_id: str,
    guard_name: str,
    migration: str,
    rationale: str,
    fixtures: tuple[str, ...],
    ops_sql: str,
    sqlstate_condition: str,
    what: str,
    tabelas: tuple[str, ...] = (),
) -> GuardProbe:
    """Build a probe over the 179-183 (and 190) guards. `tabelas` names
    schema-qualified tables the probe writes to that a not-yet-applied
    migration creates — each is `no_fixture` when absent, never an
    `ambiguous` "relation does not exist". `fixtures` names entries of
    `_SW_FIXTURES` (every one is `no_fixture` if its source has no row —
    never a silent pass). `ops_sql` is the forbidden write(s); the guard is
    proven only when the violated constraint's NAME is exactly `guard_name`."""
    # Each probe uses at most one org source (`registry` or `atendimento_org`).
    declares = (
        "  v_org uuid;\n  v_codigo text;\n  v_atendimento uuid;\n"
        "  v_cliente uuid;\n  v_empresa uuid;\n  v_constraint text;\n"
    )
    setup = "".join(_table_fixture_check(t) for t in tabelas)
    for name in fixtures:
        select_sql, into_vars = _SW_FIXTURES[name]
        last_var = into_vars.split(",")[-1].strip()
        setup += (
            f"  {select_sql.replace(' FROM ', ' INTO ' + into_vars + ' FROM ', 1)};\n"
            f"  IF {last_var} IS NULL THEN\n"
            f"    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no row for the {name} fixture ({_sql_lit(select_sql)})';\n"
            f"  END IF;\n"
        )
    what_lit = _sql_lit(what)
    guard_lit = _sql_lit(guard_name)
    return GuardProbe(
        id=probe_id,
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name=guard_name,
        kind="write_refusal",
        migrations=(migration,),
        rationale=rationale,
        sql=_do_block(f"""
DECLARE
{declares}BEGIN
{setup}  BEGIN
{ops_sql}
    RAISE EXCEPTION 'NOC_PROBE:permitted: {what_lit} succeeded — the guard did not fire';
  EXCEPTION
    WHEN {sqlstate_condition} THEN
      GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
      IF v_constraint = '{guard_lit}' THEN
        RAISE EXCEPTION 'NOC_PROBE:refused: % refused by %', '{what_lit}', v_constraint;
      END IF;
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: refused by an unexpected constraint %', v_constraint;
    WHEN OTHERS THEN
      IF SQLERRM LIKE 'NOC_PROBE:%' THEN
        RAISE;
      END IF;
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
  END;
END;
"""),
    )


_M179 = "179_atendimento_partes_pj_e_certidoes_por_parte.sql"
_M181 = "181_atendimento_imoveis.sql"
_M182 = "182_cliente_imovel_interesses.sql"
_M183 = "183_imovel_proprietarios.sql"
_S = _SW_SCHEMA
_CHECK = "check_violation"
_UNIQ = "unique_violation"

_ATD_IMOVEL_INS = (
    f"    INSERT INTO {_S}.atendimento_imoveis (org_id, atendimento_id, codigo{{extra_cols}})\n"
    "    VALUES (v_org, v_atendimento, v_codigo{extra_vals});"
)
_CLI_INT_INS = (
    f"    INSERT INTO {_S}.cliente_imovel_interesses (org_id, cliente_id, codigo{{extra_cols}})\n"
    "    VALUES (v_org, v_cliente, v_codigo{extra_vals});"
)


def _ins(template: str, extra_cols: str = "", extra_vals: str = "") -> str:
    return template.format(extra_cols=extra_cols, extra_vals=extra_vals)


_ATD_IMOVEL_FX = ("registry", "atendimento")
_CLI_INT_FX = ("registry", "cliente")

_SW_179_183_PROBES: tuple[GuardProbe, ...] = (
    _sw_junction_probe(
        probe_id="atendimento_partes.pessoa_xor_empresa",
        guard_name="atendimento_partes_pessoa_xor_empresa",
        migration=_M179,
        rationale="A party is exactly one of cliente_id / empresa_id; a row with both (or neither) has no defined identity.",
        fixtures=("atendimento_org", "cliente", "empresa"),
        ops_sql=(
            f"    INSERT INTO {_S}.atendimento_partes (org_id, atendimento_id, cliente_id, empresa_id)\n"
            "    VALUES (v_org, v_atendimento, v_cliente, v_empresa);"
        ),
        sqlstate_condition=_CHECK,
        what="an atendimento_partes row with BOTH cliente_id and empresa_id",
    ),
    _sw_junction_probe(
        probe_id="atendimento_partes.one_empresa_per_atendimento",
        guard_name="uq_sw_atendimento_partes_empresa",
        migration=_M179,
        rationale="The same empresa must not be added twice as a party of one atendimento (a double-click, not an intent).",
        fixtures=("atendimento_org", "empresa"),
        ops_sql=(
            f"    INSERT INTO {_S}.atendimento_partes (org_id, atendimento_id, empresa_id)\n"
            "    VALUES (v_org, v_atendimento, v_empresa);\n"
            f"    INSERT INTO {_S}.atendimento_partes (org_id, atendimento_id, empresa_id)\n"
            "    VALUES (v_org, v_atendimento, v_empresa);"
        ),
        sqlstate_condition=_UNIQ,
        what="a second atendimento_partes row for the same (atendimento, empresa)",
    ),
    _sw_junction_probe(
        probe_id="atendimento_imoveis.origem_valida",
        guard_name="atendimento_imoveis_origem_valida",
        migration=_M181,
        rationale="origem drives how the junction row is explained to the user; an unknown value would render as nothing.",
        fixtures=_ATD_IMOVEL_FX,
        ops_sql=_ins(_ATD_IMOVEL_INS, ", origem", ", 'noc_probe_bogus'"),
        sqlstate_condition=_CHECK,
        what="an atendimento_imoveis row with an out-of-vocabulary origem",
    ),
    _sw_junction_probe(
        probe_id="atendimento_imoveis.one_live_per_codigo",
        guard_name="uq_sw_atendimento_imoveis_vivo",
        migration=_M181,
        rationale="One live junction row per (atendimento, código); a duplicate would double-count the imóvel.",
        fixtures=_ATD_IMOVEL_FX,
        ops_sql=_ins(_ATD_IMOVEL_INS) + "\n" + _ins(_ATD_IMOVEL_INS),
        sqlstate_condition=_UNIQ,
        what="two live atendimento_imoveis rows for the same (atendimento, codigo)",
    ),
    _sw_junction_probe(
        probe_id="atendimento_imoveis.one_live_principal",
        guard_name="uq_sw_atendimento_imoveis_principal",
        migration=_M181,
        rationale="At most one live principal imóvel per atendimento; two would make 'the' imóvel ambiguous.",
        fixtures=_ATD_IMOVEL_FX,
        ops_sql=(
            f"    INSERT INTO {_S}.atendimento_imoveis (org_id, atendimento_id, codigo, principal)\n"
            "    VALUES (v_org, v_atendimento, v_codigo, true);\n"
            f"    INSERT INTO {_S}.atendimento_imoveis (org_id, atendimento_id, codigo, principal)\n"
            "    VALUES (v_org, v_atendimento, v_codigo || '-noc-probe', true);"
        ),
        sqlstate_condition=_UNIQ,
        what="two live principal atendimento_imoveis rows for one atendimento",
    ),
    _sw_junction_probe(
        probe_id="cliente_imovel_interesses.origem_valida",
        guard_name="cliente_imovel_interesses_origem_valida",
        migration=_M182,
        rationale="origem drives how the interest is explained; an unknown value would render as nothing.",
        fixtures=_CLI_INT_FX,
        ops_sql=_ins(_CLI_INT_INS, ", origem", ", 'noc_probe_bogus'"),
        sqlstate_condition=_CHECK,
        what="a cliente_imovel_interesses row with an out-of-vocabulary origem",
    ),
    _sw_junction_probe(
        probe_id="cliente_imovel_interesses.lead_unico",
        guard_name="cliente_imovel_interesses_lead_unico",
        migration=_M182,
        rationale="An interest comes from at most one lead source (lead_id XOR meta_ads_lead_id).",
        fixtures=_CLI_INT_FX,
        ops_sql=(
            f"    INSERT INTO {_S}.cliente_imovel_interesses (org_id, cliente_id, codigo, lead_id, meta_ads_lead_id)\n"
            "    VALUES (v_org, v_cliente, v_codigo, gen_random_uuid(), 'noc_probe_meta_lead');"
        ),
        sqlstate_condition=_CHECK,
        what="a cliente_imovel_interesses row with BOTH lead_id and meta_ads_lead_id",
    ),
    _sw_junction_probe(
        probe_id="cliente_imovel_interesses.one_live_per_codigo",
        guard_name="uq_sw_cliente_imovel_interesses_vivo",
        migration=_M182,
        rationale="One live interest per (cliente, código); a duplicate would double-count the lead.",
        fixtures=_CLI_INT_FX,
        ops_sql=_ins(_CLI_INT_INS) + "\n" + _ins(_CLI_INT_INS),
        sqlstate_condition=_UNIQ,
        what="two live cliente_imovel_interesses rows for the same (cliente, codigo)",
    ),
    _sw_junction_probe(
        probe_id="imovel_proprietarios.origem_valida",
        guard_name="imovel_proprietarios_origem_valida",
        migration=_M183,
        rationale="origem records where the ownership claim came from; an unknown value breaks provenance display.",
        fixtures=("registry", "cliente"),
        ops_sql=(
            f"    INSERT INTO {_S}.imovel_proprietarios (org_id, codigo, cliente_id, origem)\n"
            "    VALUES (v_org, v_codigo, v_cliente, 'noc_probe_bogus');"
        ),
        sqlstate_condition=_CHECK,
        what="an imovel_proprietarios row with an out-of-vocabulary origem",
    ),
    _sw_junction_probe(
        probe_id="imovel_proprietarios.pessoa_xor_empresa",
        guard_name="imovel_proprietarios_pessoa_xor_empresa",
        migration=_M183,
        rationale="An owner is exactly one of cliente / empresa; both-or-neither has no defined identity.",
        fixtures=("registry", "cliente", "empresa"),
        ops_sql=(
            f"    INSERT INTO {_S}.imovel_proprietarios (org_id, codigo, cliente_id, empresa_id)\n"
            "    VALUES (v_org, v_codigo, v_cliente, v_empresa);"
        ),
        sqlstate_condition=_CHECK,
        what="an imovel_proprietarios row with BOTH cliente_id and empresa_id",
    ),
    _sw_junction_probe(
        probe_id="imovel_proprietarios.one_live_cliente_per_codigo",
        guard_name="uq_sw_imovel_proprietarios_cliente_vivo",
        migration=_M183,
        rationale="One live ownership row per (imóvel, cliente) within an org.",
        fixtures=("registry", "cliente"),
        ops_sql=(
            f"    INSERT INTO {_S}.imovel_proprietarios (org_id, codigo, cliente_id)\n"
            "    VALUES (v_org, v_codigo, v_cliente);\n"
            f"    INSERT INTO {_S}.imovel_proprietarios (org_id, codigo, cliente_id)\n"
            "    VALUES (v_org, v_codigo, v_cliente);"
        ),
        sqlstate_condition=_UNIQ,
        what="two live imovel_proprietarios rows for the same (codigo, cliente)",
    ),
    _sw_junction_probe(
        probe_id="imovel_proprietarios.one_live_empresa_per_codigo",
        guard_name="uq_sw_imovel_proprietarios_empresa_vivo",
        migration=_M183,
        rationale="One live ownership row per (imóvel, empresa) within an org.",
        fixtures=("registry", "empresa"),
        ops_sql=(
            f"    INSERT INTO {_S}.imovel_proprietarios (org_id, codigo, empresa_id)\n"
            "    VALUES (v_org, v_codigo, v_empresa);\n"
            f"    INSERT INTO {_S}.imovel_proprietarios (org_id, codigo, empresa_id)\n"
            "    VALUES (v_org, v_codigo, v_empresa);"
        ),
        sqlstate_condition=_UNIQ,
        what="two live imovel_proprietarios rows for the same (codigo, empresa)",
    ),
)


# ---------------------------------------------------------------------------
# Migration 190 — aditivos (amendments to a signed contract). Every probe
# self-provisions its own contract → aditivo chain inside the rolled-back
# transaction through data-modifying CTEs (one statement each), borrowing
# only an existing atendimento (and its org).
# ---------------------------------------------------------------------------

_M190 = "190_contrato_aditivos.sql"
_M190_TABELAS = (
    f"{_S}.atendimento_contrato_aditivos",
    f"{_S}.atendimento_contrato_aditivo_parcelas",
    f"{_S}.atendimento_contrato_aditivo_versoes",
)
_M190_CONTRATO_CTE = (
    f"    WITH c AS (INSERT INTO {_S}.atendimento_contratos (org_id, atendimento_id, titulo)\n"
    "               VALUES (v_org, v_atendimento, 'noc probe aditivo') RETURNING id)"
)
_M190_ADITIVO_CTE = (
    _M190_CONTRATO_CTE + ",\n"
    f"    a AS (INSERT INTO {_S}.atendimento_contrato_aditivos (org_id, atendimento_id, contrato_id, ordinal)\n"
    "          SELECT v_org, v_atendimento, c.id, 1 FROM c RETURNING id)"
)
_M190_VERSAO_COLS = (
    f"    INSERT INTO {_S}.atendimento_contrato_aditivo_versoes\n"
    "      (org_id, aditivo_id, storage_path, nome_original, mime_type, tamanho_bytes, tipo_documento,\n"
    "       numero, origem, contexto_sha256, docx_storage_path, docx_tamanho_bytes, revisado_por, revisado_em)\n"
)

_SW_190_PROBES: tuple[GuardProbe, ...] = (
    _sw_junction_probe(
        probe_id="contrato_aditivos.ordinal_never_reused",
        guard_name="uq_sw_contrato_aditivos_ordinal",
        migration=_M190,
        rationale="'o Segundo Termo Aditivo' must keep naming one instrument: an ordinal is never reused within a contract, deleted rows included.",
        fixtures=("atendimento_org",),
        tabelas=_M190_TABELAS,
        ops_sql=(
            _M190_CONTRATO_CTE + "\n"
            f"    INSERT INTO {_S}.atendimento_contrato_aditivos (org_id, atendimento_id, contrato_id, ordinal)\n"
            "    SELECT v_org, v_atendimento, c.id, 1 FROM c UNION ALL SELECT v_org, v_atendimento, c.id, 1 FROM c;"
        ),
        sqlstate_condition=_UNIQ,
        what="two aditivos of one contract with the same ordinal",
    ),
    _sw_junction_probe(
        probe_id="contrato_aditivo_parcelas.ordem_unique",
        guard_name="uq_sw_contrato_aditivo_parcelas_ordem",
        migration=_M190,
        rationale="The printed 'Parcela NN' numbering rests on a distinct ordem per parcela of the restated schedule.",
        fixtures=("atendimento_org",),
        tabelas=_M190_TABELAS,
        ops_sql=(
            _M190_ADITIVO_CTE + "\n"
            f"    INSERT INTO {_S}.atendimento_contrato_aditivo_parcelas (org_id, aditivo_id, tipo, valor, ordem)\n"
            "    SELECT v_org, a.id, 'sinal', 1, 0 FROM a UNION ALL SELECT v_org, a.id, 'direta', 1, 0 FROM a;"
        ),
        sqlstate_condition=_UNIQ,
        what="two parcelas of one aditivo with the same ordem",
    ),
    _sw_junction_probe(
        probe_id="contrato_aditivo_versoes.numero_never_reused",
        guard_name="uq_sw_contrato_aditivo_versoes_numero",
        migration=_M190,
        rationale="'versão 2' of an aditivo must keep naming the same bytes; numero is never reused.",
        fixtures=("atendimento_org",),
        tabelas=_M190_TABELAS,
        ops_sql=(
            _M190_ADITIVO_CTE + "\n" + _M190_VERSAO_COLS
            + "    SELECT v_org, a.id, 'noc/probe', 'p.pdf', 'application/pdf', 1, 'aditivo', 1, 'upload', NULL::text, NULL::text, NULL::bigint, NULL::uuid, NULL::timestamptz FROM a\n"
            "    UNION ALL SELECT v_org, a.id, 'noc/probe2', 'p.pdf', 'application/pdf', 1, 'aditivo', 1, 'upload', NULL::text, NULL::text, NULL::bigint, NULL::uuid, NULL::timestamptz FROM a;"
        ),
        sqlstate_condition=_UNIQ,
        what="two versions of one aditivo with the same numero",
    ),
    _sw_junction_probe(
        probe_id="contrato_aditivo_versoes.gerado_born_complete",
        guard_name="atendimento_contrato_aditivo_versoes_gerado_completo",
        migration=_M190,
        rationale="A generated aditivo version is born with its PDF, its .docx sibling and the snapshot hash in ONE insert — never completed later.",
        fixtures=("atendimento_org",),
        tabelas=_M190_TABELAS,
        ops_sql=(
            _M190_ADITIVO_CTE + "\n" + _M190_VERSAO_COLS
            + "    SELECT v_org, a.id, 'noc/probe', 'p.pdf', 'application/pdf', 1, 'aditivo', 1, 'gerado', NULL::text, NULL::text, NULL::bigint, NULL::uuid, NULL::timestamptz FROM a;"
        ),
        sqlstate_condition=_CHECK,
        what="a gerado aditivo version without its snapshot hash and .docx",
    ),
    _sw_junction_probe(
        probe_id="contrato_aditivo_versoes.revisado_par",
        guard_name="atendimento_contrato_aditivo_versoes_revisado_par",
        migration=_M190,
        rationale="A legal-review approval names WHO and WHEN together; a reviewer without a timestamp is not an approval.",
        fixtures=("atendimento_org",),
        tabelas=_M190_TABELAS,
        ops_sql=(
            _M190_ADITIVO_CTE + "\n" + _M190_VERSAO_COLS
            + "    SELECT v_org, a.id, 'noc/probe', 'p.pdf', 'application/pdf', 1, 'aditivo', 1, 'upload', NULL::text, NULL::text, NULL::bigint, gen_random_uuid(), NULL::timestamptz FROM a;"
        ),
        sqlstate_condition=_CHECK,
        what="an aditivo version with revisado_por but no revisado_em",
    ),
)


_M192 = "192_parcela_divisao_fgts_quitacao_boleto.sql"

#: Migration 192 — the contract payment shapes (social-wiring). Each probe
#: writes the forbidden row inside the rolled-back transaction, against a
#: borrowed atendimento (`atendimento_org` fixture).
_SW_192_PROBES: tuple[GuardProbe, ...] = (
    _sw_junction_probe(
        probe_id="atendimento_parcela_favorecidos.valor_ou_percentual",
        guard_name="atendimento_parcela_favorecidos_valor_ou_percentual",
        migration=_M192,
        rationale=(
            "A share of a divided parcela is a valor OR a percentual of it; with both, "
            "the contract would print two possibly-contradictory amounts for one payee."
        ),
        fixtures=("atendimento_org",),
        tabelas=(f"{_S}.atendimento_parcela_favorecidos",),
        ops_sql=(
            f"    WITH p AS (\n"
            f"      INSERT INTO {_S}.atendimento_negociacao_parcelas (org_id, atendimento_id, tipo, valor)\n"
            "      VALUES (v_org, v_atendimento, 'sinal', 1) RETURNING id\n"
            "    )\n"
            f"    INSERT INTO {_S}.atendimento_parcela_favorecidos (org_id, parcela_id, valor, percentual)\n"
            "    SELECT v_org, p.id, 1, 50 FROM p;"
        ),
        sqlstate_condition=_CHECK,
        what="a parcela share carrying both valor and percentual",
    ),
    _sw_junction_probe(
        probe_id="atendimento_negociacao_parcelas.valor_fgts_so_no_financiamento",
        guard_name="atendimento_negociacao_parcelas_valor_fgts_check",
        migration=_M192,
        rationale=(
            "valor_fgts is the FGTS portion of the FINANCING parcela; on any other tipo the "
            "generator would have no line to print it in."
        ),
        fixtures=("atendimento_org",),
        ops_sql=(
            f"    INSERT INTO {_S}.atendimento_negociacao_parcelas (org_id, atendimento_id, tipo, valor, valor_fgts)\n"
            "    VALUES (v_org, v_atendimento, 'sinal', 100, 10);"
        ),
        sqlstate_condition=_CHECK,
        what="a non-financiamento parcela with valor_fgts",
    ),
    _sw_junction_probe(
        probe_id="atendimento_negociacao_termos.onus_quitacao_vocabulario",
        guard_name="atendimento_negociacao_termos_onus_quitacao_check",
        migration=_M192,
        rationale=(
            "onus_quitacao picks the ÔNUS clause wording; an unknown value has no wording "
            "and the generator would refuse every contract of the deal."
        ),
        fixtures=("atendimento_org",),
        ops_sql=(
            f"    INSERT INTO {_S}.atendimento_negociacao_termos (atendimento_id, org_id, onus_quitacao)\n"
            "    VALUES (v_atendimento, v_org, 'noc_probe_bogus');"
        ),
        sqlstate_condition=_CHECK,
        what="an out-of-vocabulary onus_quitacao",
    ),
)



_M201 = "201_termos_posse_data_fixa.sql"

#: Migration 201 — the imóvel's posse on a fixed calendar date.
_SW_201_PROBES: tuple[GuardProbe, ...] = (
    _sw_junction_probe(
        probe_id="atendimento_negociacao_termos.posse_marco_vocabulario",
        guard_name="atendimento_negociacao_termos_posse_marco_check",
        migration=_M201,
        rationale=(
            "posse_marco picks the posse clause wording; an unknown value has no wording "
            "and the generator would refuse every contract of the deal."
        ),
        fixtures=("atendimento_org",),
        ops_sql=(
            f"    INSERT INTO {_S}.atendimento_negociacao_termos (atendimento_id, org_id, posse_marco)\n"
            "    VALUES (v_atendimento, v_org, 'noc_probe_bogus');"
        ),
        sqlstate_condition=_CHECK,
        what="an out-of-vocabulary posse_marco",
    ),
    _sw_junction_probe(
        probe_id="atendimento_negociacao_termos.posse_marco_data_pareados",
        guard_name="atendimento_negociacao_termos_posse_marco_data",
        migration=_M201,
        rationale=(
            "A fixed-date posse prints its date; a data_fixa marco without posse_data (or a "
            "posse_data under another marco) would print a clause the operator never wrote."
        ),
        fixtures=("atendimento_org",),
        ops_sql=(
            f"    INSERT INTO {_S}.atendimento_negociacao_termos (atendimento_id, org_id, posse_marco)\n"
            "    VALUES (v_atendimento, v_org, 'data_fixa');"
        ),
        sqlstate_condition=_CHECK,
        what="a data_fixa posse_marco without posse_data",
    ),
)


_M207 = "207_termos_clausulas_extras.sql"

#: Migration 207 — per-clause special conditions + per-deal posse multa override.
_SW_207_PROBES: tuple[GuardProbe, ...] = (
    _sw_junction_probe(
        probe_id="atendimento_negociacao_termos.clausulas_extras_objeto_json",
        guard_name="atendimento_negociacao_termos_clausulas_extras_objeto",
        migration=_M207,
        rationale=(
            "clausulas_extras is a map clause-key -> {texto, modo}; a JSON array or scalar has "
            "no clause keys and the generator would read garbage as bespoke contract text."
        ),
        fixtures=("atendimento_org",),
        ops_sql=(
            f"    INSERT INTO {_S}.atendimento_negociacao_termos (atendimento_id, org_id, clausulas_extras)\n"
            "    VALUES (v_atendimento, v_org, '[]'::jsonb);"
        ),
        sqlstate_condition=_CHECK,
        what="a clausulas_extras that is a JSON array instead of an object",
    ),
    _sw_junction_probe(
        probe_id="atendimento_negociacao_termos.posse_multa_diaria_positiva",
        guard_name="atendimento_negociacao_termos_posse_multa_diaria_positiva",
        migration=_M207,
        rationale=(
            "A per-deal daily posse fine is NULL (office default) or a positive amount; "
            "zero or negative would print a contractual penalty of nothing."
        ),
        fixtures=("atendimento_org",),
        ops_sql=(
            f"    INSERT INTO {_S}.atendimento_negociacao_termos (atendimento_id, org_id, posse_multa_diaria)\n"
            "    VALUES (v_atendimento, v_org, 0);"
        ),
        sqlstate_condition=_CHECK,
        what="a zero per-deal posse_multa_diaria",
    ),
)


_M_PROPOSTAS = "222_atendimento_propostas.sql"  # rename with the migration file at integrate


def _proposta_ins(extra_cols: str = "", extra_vals: str = "") -> str:
    return (
        f"    INSERT INTO {_S}.atendimento_propostas "
        f"(org_id, atendimento_id, cliente_id, imovel_codigo{extra_cols})\n"
        f"    VALUES (v_org, v_atendimento, gen_random_uuid(), 'NOC_PROBE'{extra_vals});"
    )


#: atendimento_propostas (sw-lead-to-contract CONTRACT §4.1).
_SW_PROPOSTAS_PROBES: tuple[GuardProbe, ...] = (
    _sw_junction_probe(
        probe_id="atendimento_propostas.status_valido",
        guard_name="atendimento_propostas_status_valido",
        migration=_M_PROPOSTAS,
        rationale="status drives which edits/transitions a proposta allows; an unknown value would be neither open nor closed.",
        fixtures=("atendimento_org",),
        ops_sql=_proposta_ins(", status", ", 'noc_probe_bogus'"),
        sqlstate_condition=_CHECK,
        what="an atendimento_propostas row with an out-of-vocabulary status",
        tabelas=(f"{_S}.atendimento_propostas",),
    ),
    _sw_junction_probe(
        probe_id="atendimento_propostas.valor_positivo",
        guard_name="atendimento_propostas_valor_positivo",
        migration=_M_PROPOSTAS,
        rationale="An offer of zero or less is not an offer; the contract's price would print as nothing.",
        fixtures=("atendimento_org",),
        ops_sql=_proposta_ins(", valor_proposto", ", 0"),
        sqlstate_condition=_CHECK,
        what="a zero valor_proposto",
        tabelas=(f"{_S}.atendimento_propostas",),
    ),
    _sw_junction_probe(
        probe_id="atendimento_propostas.one_aceita_per_atendimento",
        guard_name="uq_sw_atendimento_propostas_uma_aceita",
        migration=_M_PROPOSTAS,
        rationale="The live negotiation set holds one imóvel and one set of terms; two accepted propostas would be two answers to what is being sold.",
        fixtures=("atendimento_org",),
        ops_sql=_proposta_ins(", status", ", 'aceita'") + "\n" + _proposta_ins(", status", ", 'aceita'"),
        sqlstate_condition=_UNIQ,
        what="two accepted atendimento_propostas for one atendimento",
        tabelas=(f"{_S}.atendimento_propostas",),
    ),
)


# ---------------------------------------------------------------------------
# Registry — sw-lead-to-contract S6 (CONTRACT §8 / §8.6 / §8.7): manual
# captação (226) and possível duplicado + the manual<->Vista link (228).
# Each probe borrows one existing `imovel_registry` row for (org, código) and
# lists a table its OWN migration creates in `tabelas`, so a not-yet-applied
# migration is `no_fixture` (never `ambiguous`) — including the two registry
# probes, whose `vinculado_a` column ships in 228 alongside
# `imovel_vinculo_eventos`. CHECKs fire before the statement-end FK checks;
# the two UNIQUE probes self-provision registry rows so their FKs hold.
# ---------------------------------------------------------------------------

_M_CAPTACAO = "226_imovel_captacao_manual.sql"
_M_DUPLICATAS = "228_imovel_duplicatas.sql"
_T_CAPTACAO = f"{_S}.imovel_captacao"
_T_DUPLICATAS = f"{_S}.imovel_duplicata_candidatos"
_T_VINCULO_EVENTOS = f"{_S}.imovel_vinculo_eventos"


def _captacao_ins(col: str, val: str) -> str:
    return (
        f"    INSERT INTO {_S}.imovel_captacao (org_id, codigo_canonical, {col})\n"
        f"    VALUES (v_org, v_codigo, {val});"
    )


def _duplicata_ins(cols: str, vals: str) -> str:
    return (
        f"    INSERT INTO {_S}.imovel_duplicata_candidatos (org_id, codigo_manual, {cols})\n"
        f"    VALUES (v_org, v_codigo, {vals});"
    )


def _registry_ins(codigo: str, vinculado_a_sql: str = "NULL") -> str:
    return (
        f"    INSERT INTO {_S}.imovel_registry (org_id, codigo_canonical, vinculado_a)\n"
        f"    VALUES (v_org, '{codigo}', {vinculado_a_sql});"
    )


_REG_PROBE_TARGET = (
    f"(SELECT id FROM {_S}.imovel_registry "
    "WHERE org_id = v_org AND codigo_canonical = 'NOC_PROBE_T')"
)

_M231 = "231_intermediario_documento_canonico.sql"


def _intermediario_ins(cols: str, vals: str) -> str:
    return (
        f"    INSERT INTO {_S}.atendimento_intermediarios (org_id, atendimento_id, nome, tipo, {cols})\n"
        f"    VALUES (v_org, v_atendimento, 'NOC_PROBE', 'percentual', {vals});"
    )


#: Migration 231 — the intermediary document CHECKs on the CANONICAL
#: (punctuated) form. Before 231 they demanded bare digits while the service
#: wrote punctuated ones (canonical identifiers, 2026-10-01), so every save
#: of an intermediary with a document was refused in production. Each probe
#: writes the OLD bare shape and must now be refused.
_SW_231_PROBES: tuple[GuardProbe, ...] = (
    _sw_junction_probe(
        probe_id="atendimento_intermediarios.documento_formato",
        guard_name="atendimento_intermediarios_documento_formato",
        migration=_M231,
        rationale=(
            "The intermediary's CPF/CNPJ is printed into the contract; only the canonical "
            "punctuated form the service writes may be stored, never a bare digit string."
        ),
        fixtures=("atendimento_org",),
        tabelas=(f"{_S}.atendimento_intermediarios",),
        ops_sql=_intermediario_ins("pessoa_tipo, documento", "'pf', '11144477735'"),
        sqlstate_condition=_CHECK,
        what="a pf intermediary whose documento is bare digits",
    ),
    _sw_junction_probe(
        probe_id="atendimento_intermediarios.representante_cpf_formato",
        guard_name="atendimento_intermediarios_representante_cpf_formato",
        migration=_M231,
        rationale=(
            "The PJ representative's CPF is printed into the contract; only the canonical "
            "punctuated form may be stored."
        ),
        fixtures=("atendimento_org",),
        tabelas=(f"{_S}.atendimento_intermediarios",),
        ops_sql=_intermediario_ins("representante_cpf", "'11144477735'"),
        sqlstate_condition=_CHECK,
        what="an intermediary whose representante_cpf is bare digits",
    ),
)


_M_TRANSACOES = "266_imovel_transacoes.sql"
_T_TRANSACOES = f"{_S}.imovel_transacoes"


def _transacao_ins(**over: str) -> str:
    """A valid imovel_transacoes row with the named columns overridden by SQL literals."""
    cols = {"valor_transacao": "1", "fonte": "'manual'", "fonte_ref": "'NOC_PROBE'", **over}
    return (
        f"    INSERT INTO {_S}.imovel_transacoes (org_id, {', '.join(cols)})\n"
        f"    VALUES (v_org, {', '.join(cols.values())});"
    )


def _transacao_probe(probe_id: str, guard: str, rationale: str, ops_sql: str, what: str,
                     sqlstate: str = _CHECK) -> GuardProbe:
    return _sw_junction_probe(
        probe_id=f"imovel_transacoes.{probe_id}", guard_name=guard, migration=_M_TRANSACOES,
        rationale=rationale, fixtures=("registry",), ops_sql=ops_sql, sqlstate_condition=sqlstate,
        what=what, tabelas=(_T_TRANSACOES,),
    )


#: Migration 266 -- the closing-price ledger the price evaluator trains/validates on. A bad row here
#: would silently poison every comparable, so each guard is proven by writing the forbidden row.
_SW_TRANSACOES_PROBES: tuple[GuardProbe, ...] = (
    _transacao_probe("tipo_valido", "imovel_transacoes_tipo_valido",
                     "Only venda is modelled; another tipo would mix rentals into sale comparables.",
                     _transacao_ins(tipo="'noc_probe_bogus'"), "a transacao with an unknown tipo"),
    _transacao_probe("fonte_valida", "imovel_transacoes_fonte_valida",
                     "The source decides how far a price is trusted; an unknown one has no trust level.",
                     _transacao_ins(fonte="'noc_probe_bogus'"), "a transacao with an unknown fonte"),
    _transacao_probe("vinculo_valido", "imovel_transacoes_vinculo_valido",
                     "Only pendente/confirmado/rejeitado exist; another value is neither reviewed nor used.",
                     _transacao_ins(vinculo_status="'noc_probe_bogus'"), "a transacao with an unknown vinculo_status"),
    _transacao_probe("valor_positivo", "imovel_transacoes_valor_positivo",
                     "A zero or negative closing price would drag every comparable median.",
                     _transacao_ins(valor_transacao="0"), "a transacao with valor_transacao = 0"),
    _transacao_probe("anunciado_positivo", "imovel_transacoes_anunciado_positivo",
                     "A non-positive asking price would make every sale look like a discount of infinity.",
                     _transacao_ins(valor_anunciado_ultimo="0"), "a transacao with valor_anunciado_ultimo = 0"),
    _transacao_probe("parcelas_validas", "imovel_transacoes_parcelas_validas",
                     "A negative instalment count is a parsing error that must not reach the evaluator.",
                     _transacao_ins(n_parcelas="-1"), "a transacao with n_parcelas = -1"),
    _transacao_probe("confirmado_exige_codigo", "imovel_transacoes_confirmado_exige_codigo",
                     "A confirmed link without an imóvel would be counted as ground truth for nothing.",
                     _transacao_ins(vinculo_status="'confirmado'"), "a confirmed transacao with no codigo_canonical"),
    _transacao_probe("fonte_ref_unica", "uq_imovel_transacoes_org_fonte_ref",
                     "One row per (org, fonte, fonte_ref) is what makes the importer's re-run idempotent.",
                     _transacao_ins() + "\n" + _transacao_ins(), "two transacoes for the same (fonte, fonte_ref)",
                     sqlstate=_UNIQ),
)


_M_JULIA = "267_lais_fundacao.sql"
_T_JULIA = (f"{_S}.julia_contatos", f"{_S}.julia_interacoes", f"{_S}.julia_acoes_aplicadas", f"{_S}.julia_eventos")
_JULIA_CONEXAO = "'00000000-0000-4000-8000-000000000267'"


def _julia_contato_ins(extra_cols: str = "", extra_vals: str = "") -> str:
    cols = f", {extra_cols}" if extra_cols else ""
    vals = f", {extra_vals}" if extra_vals else ""
    return (
        f"    INSERT INTO {_S}.julia_contatos (org_id, connection_id, chat_id{cols})\n"
        f"    VALUES (v_org, {_JULIA_CONEXAO}, 'noc_probe'{vals});"
    )


def _julia_child_ins(table: str, cols: str, vals: str) -> str:
    """Insert a probe contato, then a child row pointing at it (all rolled back)."""
    return (
        f"    INSERT INTO {_S}.{table} (org_id, contato_id, {cols})\n"
        f"    SELECT v_org, id, {vals} FROM {_S}.julia_contatos\n"
        f"    WHERE org_id = v_org AND connection_id = {_JULIA_CONEXAO} AND chat_id = 'noc_probe';"
    )


def _julia_probe(probe_id: str, guard: str, rationale: str, ops_sql: str, cond: str, what: str) -> GuardProbe:
    return _sw_junction_probe(
        probe_id=f"julia.{probe_id}", guard_name=guard, migration=_M_JULIA, rationale=rationale,
        fixtures=("registry",), ops_sql=ops_sql, sqlstate_condition=cond, what=what, tabelas=_T_JULIA,
    )


#: Migration 267 -- the Julia foundation (contatos / interacoes / acoes aplicadas / eventos). Unapplied
#: guards read `no_fixture` (the tables do not exist yet) and must read `refused` once applied.
_SW_JULIA_PROBES: tuple[GuardProbe, ...] = (
    _julia_probe(
        "contatos.status_envio_valido", "julia_contatos_status_envio_valido",
        "status_envio drives the 'Enviado ao SW' column and the retry button; a free-text value would be "
        "neither shown nor retried.",
        _julia_contato_ins("status_envio", "'noc_probe_bogus'"), _CHECK, "a julia_contato with an unknown status_envio",
    ),
    _julia_probe(
        "contatos.um_por_chat", "julia_contatos_org_conexao_chat_uq",
        "One contato per (org, connection, chat): a second row would fork the person's slots, gen and "
        "episodes, and the stale guard would read the wrong gen.",
        _julia_contato_ins() + "\n" + _julia_contato_ins(), _UNIQ, "two julia_contatos for the same chat",
    ),
    _julia_probe(
        "interacoes.uma_aberta", "julia_interacoes_uma_aberta_uq",
        "At most one OPEN episode per contato: two concurrent inbound turns must not open two, or the "
        "summary would be written to an arbitrary one.",
        _julia_contato_ins() + "\n" + _julia_child_ins("julia_interacoes", "iniciada_at", "now()") + "\n"
        + _julia_child_ins("julia_interacoes", "iniciada_at", "now()"),
        _UNIQ, "two open julia_interacoes for one contato",
    ),
    _julia_probe(
        "acoes.lote_seq_unico", "julia_acoes_aplicadas_lote_seq_uq",
        "The idempotency ledger: (org, lote_hash, seq) unique is what makes a replayed batch apply "
        "nothing twice (a duplicated qualificar_lead would create two leads).",
        _julia_contato_ins() + "\n" + _julia_child_ins("julia_acoes_aplicadas", "lote_hash, seq, tipo", "'noc_probe', 1, 'salvar_slots'")
        + "\n" + _julia_child_ins("julia_acoes_aplicadas", "lote_hash, seq, tipo", "'noc_probe', 1, 'salvar_slots'"),
        _UNIQ, "the same action applied twice for one (lote_hash, seq)",
    ),
    _julia_probe(
        "eventos.tipo_valido", "julia_eventos_tipo_valido",
        "The event type becomes a notification kind ('julia_' || tipo); a malformed token would mint an "
        "unroutable category.",
        f"    INSERT INTO {_S}.julia_eventos (org_id, tipo)\n    VALUES (v_org, 'NOC PROBE BOGUS');",
        _CHECK, "a julia_evento with a malformed tipo",
    ),
    # Migration 268 -- wave 1 Conhecimento: the closed set of knowledge sections.
    _sw_junction_probe(
        probe_id="julia.conhecimento.secao_valida", guard_name="julia_conhecimento_secao_valida",
        migration="268_lais_conhecimento.sql",
        rationale="`secao` selects the pydantic model that validates `dados` and the render block; an unknown "
        "one would be stored unvalidated and never rendered.",
        fixtures=("registry",),
        ops_sql=f"    INSERT INTO {_S}.julia_conhecimento_secoes (org_id, secao)\n    VALUES (v_org, 'noc_probe_bogus');",
        sqlstate_condition=_CHECK, what="a julia_conhecimento_secoes row with an unknown secao",
        tabelas=(f"{_S}.julia_conhecimento_secoes",),
    ),
)


_M_PERGUNTAS = "269_lais_perguntas.sql"
_T_PERGUNTAS = (f"{_S}.julia_perguntas_org", f"{_S}.julia_perguntas_catalogo")
_PERGUNTAS_ORG = "'00000000-0000-4000-8000-000000000269'"


def _perguntas_ins(limit: int, offset: int, qualificatoria: bool) -> str:
    """Insert `limit` catalogue questions for the synthetic probe org, starting at catalogue position
    `offset` (all rolled back). `objetivo` sorts first, so it rides in the first batch."""
    return (
        f"    INSERT INTO {_S}.julia_perguntas_org (org_id, chave, qualificatoria)\n"
        f"    SELECT {_PERGUNTAS_ORG}, chave, {'true' if qualificatoria else 'false'}\n"
        f"    FROM {_S}.julia_perguntas_catalogo ORDER BY ordem LIMIT {limit} OFFSET {offset};"
    )


def _perguntas_probe(probe_id: str, guard: str, rationale: str, ops_sql: str, what: str) -> GuardProbe:
    return _sw_junction_probe(
        probe_id=f"julia.perguntas.{probe_id}", guard_name=guard, migration=_M_PERGUNTAS, rationale=rationale,
        fixtures=(), ops_sql=ops_sql, sqlstate_condition=_CHECK, what=what, tabelas=_T_PERGUNTAS,
    )


#: Migration 269 -- the limits trigger on julia_perguntas_org (<= 8 active, <= 5 qualifying, `objetivo`
#: locked). The probe org is synthetic (no FK on org_id), so nothing depends on a real tenant row.
_SW_PERGUNTAS_PROBES: tuple[GuardProbe, ...] = (
    _perguntas_probe(
        "limite_ativas", "julia_perguntas_org_limites",
        "More than 8 active questions bloat every turn's prompt and break the 'max 8' contract the "
        "Perguntas page promises.",
        _perguntas_ins(8, 0, False) + "\n" + _perguntas_ins(1, 8, False), "a 9th active pergunta for one org",
    ),
    _perguntas_probe(
        "limite_qualificatorias", "julia_perguntas_org_limites",
        "A 6th qualifying question would make 'ready to send' unreachable for most leads.",
        _perguntas_ins(5, 0, True) + "\n" + _perguntas_ins(1, 5, True), "a 6th qualifying pergunta for one org",
    ),
    _perguntas_probe(
        "objetivo_obrigatorio", "julia_perguntas_org_objetivo_obrigatorio",
        "`objetivo` decides compra vs aluguel; without it Julia cannot route the conversation.",
        _perguntas_ins(1, 0, False) + "\n"
        + f"    DELETE FROM {_S}.julia_perguntas_org WHERE org_id = {_PERGUNTAS_ORG} AND chave = 'objetivo';",
        "removing the objetivo pergunta from an org",
    ),
    _perguntas_probe(
        "qualificatoria_exige_ativa", "julia_perguntas_org_qualificatoria_ativa",
        "A qualifying question that is switched off would still gate 'ready to send' on a slot Julia never asks.",
        f"    INSERT INTO {_S}.julia_perguntas_org (org_id, chave, ativa, qualificatoria)\n"
        f"    VALUES ({_PERGUNTAS_ORG}, 'nome', false, true);",
        "a qualifying pergunta that is not active",
    ),
    *(
        _perguntas_probe(
            f"catalogo.{pid}", guard,
            f"The catalogue drives the Perguntas page and the contexto sent to the model; {why}",
            f"    INSERT INTO {_S}.julia_perguntas_catalogo (chave, label, categoria, ordem{extra_cols})\n"
            f"    VALUES ('{chave}', 'x', '{cat}', 9999{extra_vals});",
            what,
        )
        for pid, guard, why, chave, cat, extra_cols, extra_vals, what in (
            ("chave_valida", "julia_perguntas_catalogo_chave_valida", "a key that is not snake_case cannot be a slot key.",
             "Noc Probe", "lead", "", "", "a catalogue question with a malformed chave"),
            ("categoria_valida", "julia_perguntas_catalogo_categoria_valida", "an unknown category has no filter tab.",
             "noc_probe", "bogus", "", "", "a catalogue question in an unknown categoria"),
            ("operacao_valida", "julia_perguntas_catalogo_operacao_valida", "an unknown operation never matches a contato.",
             "noc_probe", "lead", ", operacao", ", 'bogus'", "a catalogue question scoped to an unknown operacao"),
            ("sensivel_valido", "julia_perguntas_catalogo_sensivel_valido", "an unknown protection mode would store the value raw.",
             "noc_probe", "lead", ", sensivel", ", 'bogus'", "a catalogue question with an unknown sensivel mode"),
        )
    ),
)


_M_JULIA_NOTIF = "273_lais_notificacoes.sql"

#: Migration 273 -- Julia wave 6 (notificacoes prefs). Unapplied guard reads `no_fixture`, `refused` once applied.
_SW_JULIA_NOTIF_PROBES: tuple[GuardProbe, ...] = (
    _sw_junction_probe(
        probe_id="julia_notif.prefs.tipo_valido", guard_name="julia_notificacao_prefs_tipo_valido",
        migration=_M_JULIA_NOTIF,
        rationale="The type is a token the service maps to a notification kind; a free-text value would be a preference no event can ever match.",
        fixtures=("registry",),
        ops_sql=f"    INSERT INTO {_S}.julia_notificacao_prefs (org_id, user_id, tipo)\n    VALUES (v_org, gen_random_uuid(), 'Noc Probe Bogus');",
        sqlstate_condition=_CHECK, what="a notification preference with a malformed type token",
        tabelas=(f"{_S}.julia_notificacao_prefs",),
    ),
)


_M_JULIA_VIS = "272_lais_visitas.sql"
_T_JULIA_VIS = (f"{_S}.julia_contatos", f"{_S}.julia_visitas", f"{_S}.julia_visitas_config")


def _julia_vis_probe(probe_id: str, guard: str, rationale: str, ops_sql: str, cond: str, what: str) -> GuardProbe:
    return _sw_junction_probe(
        probe_id=f"julia.{probe_id}", guard_name=guard, migration=_M_JULIA_VIS, rationale=rationale,
        fixtures=("registry",), ops_sql=ops_sql, sqlstate_condition=cond, what=what, tabelas=_T_JULIA_VIS,
    )


def _julia_visita_ins(cols: str = "", vals: str = "") -> str:
    extra_c = f", {cols}" if cols else ""
    extra_v = f", {vals}" if vals else ""
    return _julia_child_ins(
        "julia_visitas", f"inicio, fim{extra_c}", f"'2099-01-01T12:00:00Z'::timestamptz, '2099-01-01T12:30:00Z'::timestamptz{extra_v}"
    )


#: Migration 272 -- Julia wave 5 (visitas). Unapplied guards read `no_fixture`, `refused` once applied.
_SW_JULIA_VISITAS_PROBES: tuple[GuardProbe, ...] = (
    _julia_vis_probe(
        "visitas.status_valido", "julia_visitas_status_valido",
        "The visit status drives which transitions are legal; a free-text value would escape the state machine.",
        _julia_contato_ins() + "\n" + _julia_visita_ins("status", "'noc_probe_bogus'"), _CHECK,
        "a julia_visita with an unknown status",
    ),
    _julia_vis_probe(
        "visitas.fim_apos_inicio", "julia_visitas_fim_apos_inicio",
        "A visit that ends before it starts would corrupt the calendar and the slot-conflict check.",
        _julia_contato_ins() + "\n" + _julia_child_ins(
            "julia_visitas", "inicio, fim",
            "'2099-01-01T12:30:00Z'::timestamptz, '2099-01-01T12:00:00Z'::timestamptz"),
        _CHECK, "a julia_visita whose fim is not after inicio",
    ),
    _julia_vis_probe(
        "visitas.cpf_formato", "julia_visitas_cpf_formato",
        "LGPD (contract 17): only a sha256 hash + last 3 digits may be stored; a clear CPF in cpf_hash "
        "would defeat the whole point.",
        _julia_contato_ins() + "\n" + _julia_visita_ins("cpf_hash, cpf_final", "'noc_probe_clear', '123'"), _CHECK,
        "a julia_visita whose cpf_hash is not a sha256 hex",
    ),
    _julia_vis_probe(
        "visitas.slot_vivo_unico", "julia_visitas_slot_vivo_uq",
        "One live visit per (org, inicio): two concurrent requests must not book the same slot.",
        _julia_contato_ins() + "\n" + _julia_visita_ins() + "\n" + _julia_visita_ins(), _UNIQ,
        "two live julia_visitas at the same inicio",
    ),
    _julia_vis_probe(
        "visitas_config.objeto", "julia_visitas_config_objeto",
        "The drawer config is read as a mapping profile->rules; an array/scalar would crash every slot computation.",
        f"    INSERT INTO {_S}.julia_visitas_config (org_id, config)\n    VALUES (v_org, '[]'::jsonb);",
        _CHECK, "a julia_visitas_config whose config is not a JSON object",
    ),
)


def _julia_contato_etiqueta_ins() -> str:
    return (
        f"    INSERT INTO {_S}.julia_contato_etiquetas (org_id, contato_id, etiqueta_id)\n"
        f"    SELECT v_org, c.id, e.id FROM {_S}.julia_contatos c, {_S}.julia_etiquetas e\n"
        f"    WHERE c.org_id = v_org AND c.connection_id = {_JULIA_CONEXAO} AND c.chat_id = 'noc_probe'\n"
        f"      AND e.org_id = v_org AND lower(e.nome) = 'noc_probe';"
    )


_M_JULIA_CONV = "274_lais_conversas_v2.sql"
_T_JULIA_CONV = (
    f"{_S}.julia_contatos", f"{_S}.julia_etiquetas", f"{_S}.julia_contato_etiquetas",
    f"{_S}.julia_notas", f"{_S}.julia_feedback",
)


def _julia_conv_probe(probe_id: str, guard: str, rationale: str, ops_sql: str, cond: str, what: str) -> GuardProbe:
    return _sw_junction_probe(
        probe_id=f"julia_conv.{probe_id}", guard_name=guard, migration=_M_JULIA_CONV, rationale=rationale,
        fixtures=("registry",), ops_sql=ops_sql, sqlstate_condition=cond, what=what, tabelas=_T_JULIA_CONV,
    )


def _julia_etiqueta_ins(nome: str = "noc_probe", cor: str = "#112233") -> str:
    return f"    INSERT INTO {_S}.julia_etiquetas (org_id, nome, cor) VALUES (v_org, '{nome}', '{cor}');"


#: Migration 274 -- Julia wave 7 (Conversas v2). Unapplied guards read `no_fixture`, `refused` once applied.
_SW_JULIA_CONV_PROBES: tuple[GuardProbe, ...] = (
    _julia_conv_probe(
        "etiquetas.nome_valido", "julia_etiquetas_nome_valido",
        "A blank tag name is an unselectable kanban column.",
        _julia_etiqueta_ins(nome="   "), _CHECK, "a julia_etiqueta with a blank name",
    ),
    _julia_conv_probe(
        "etiquetas.cor_valida", "julia_etiquetas_cor_valida",
        "The tag colour is rendered straight into CSS; only #rrggbb is accepted.",
        _julia_etiqueta_ins(cor="red"), _CHECK, "a julia_etiqueta whose cor is not #rrggbb",
    ),
    _julia_conv_probe(
        "etiquetas.nome_unico", "julia_etiquetas_org_nome_uq",
        "Two tags with the same name in an org would be two indistinguishable kanban columns.",
        _julia_etiqueta_ins() + "\n" + _julia_etiqueta_ins(nome="NOC_PROBE"), _UNIQ,
        "two julia_etiquetas with the same name (case-insensitive) in one org",
    ),
    _julia_conv_probe(
        "contato_etiquetas.pk", "julia_contato_etiquetas_pk",
        "A contato carries a given tag at most once; a duplicate would render the lead twice in the column.",
        _julia_contato_ins() + "\n" + _julia_etiqueta_ins() + "\n"
        + _julia_contato_etiqueta_ins() + "\n" + _julia_contato_etiqueta_ins(), _UNIQ,
        "the same etiqueta attached twice to one julia_contato",
    ),
    _julia_conv_probe(
        "notas.texto_valido", "julia_notas_texto_valido",
        "A note is 1..4000 chars; an empty or unbounded note breaks the Notas internas card.",
        _julia_contato_ins() + "\n" + _julia_child_ins("julia_notas", "texto", "'   '"), _CHECK,
        "a julia_nota with a blank text",
    ),
    _julia_conv_probe(
        "feedback.nota_valida", "julia_feedback_nota_valida",
        "Feedback feeds the evals; only like|dislike is a defined signal.",
        _julia_contato_ins() + "\n" + _julia_child_ins("julia_feedback", "nota", "'noc_probe_bogus'"), _CHECK,
        "a julia_feedback with an unknown nota",
    ),
    _julia_conv_probe(
        "feedback.comentario_tamanho", "julia_feedback_comentario_tamanho",
        "The feedback comment is capped at 1000 chars so one row cannot bloat the eval export.",
        _julia_contato_ins() + "\n" + _julia_child_ins("julia_feedback", "nota, comentario", "'like', repeat('x', 1001)"),
        _CHECK, "a julia_feedback with a 1001-char comment",
    ),
)


_M_JULIA_REENG = "271_lais_reengajamento.sql"
_T_JULIA_REENG = (f"{_S}.julia_reengajamento_config", f"{_S}.julia_reguas", f"{_S}.julia_regua_tentativas")


def _reeng_regua_ins(extra_cols: str = "", extra_vals: str = "") -> str:
    cols = f", {extra_cols}" if extra_cols else ""
    vals = f", {extra_vals}" if extra_vals else ""
    return f"    INSERT INTO {_S}.julia_reguas (org_id, nome{cols})\n    VALUES (v_org, 'noc_probe'{vals});"


def _reeng_tent_ins(cols: str, vals: str) -> str:
    """A tentativa under the probe regua (the regua is inserted first in the same rolled-back block)."""
    return (
        f"    INSERT INTO {_S}.julia_regua_tentativas (org_id, regua_id, {cols})\n"
        f"    SELECT v_org, id, {vals} FROM {_S}.julia_reguas WHERE org_id = v_org AND nome = 'noc_probe';"
    )


def _reeng_probe(probe_id: str, guard: str, rationale: str, ops_sql: str, cond: str, what: str) -> GuardProbe:
    return _sw_junction_probe(
        probe_id=f"julia_reeng.{probe_id}", guard_name=guard, migration=_M_JULIA_REENG, rationale=rationale,
        fixtures=("registry",), ops_sql=ops_sql, sqlstate_condition=cond, what=what, tabelas=_T_JULIA_REENG,
    )


_REENG_TENT_OK = "1, 1, 'dias', 'noc probe', true"
_REENG_TENT_COLS = "ordem, espera_valor, espera_unidade, texto, ativa"

#: Migration 271 -- Julia wave 4 (reengajamento). Unapplied guards read `no_fixture` (tables absent) and
#: must read `refused` once applied.
_SW_JULIA_REENG_PROBES: tuple[GuardProbe, ...] = (
    _reeng_probe(
        "config.minutos_intervalo", "julia_reeng_minutos_intervalo_valido",
        "The minutes tier is 5..60 in steps of 5; a 7-minute value would fire the default re-engagement off-grid.",
        f"    INSERT INTO {_S}.julia_reengajamento_config (org_id, minutos_intervalo) VALUES (v_org, 7);",
        _CHECK, "a re-engagement config with a 7-minute interval",
    ),
    _reeng_probe(
        "config.horas_intervalo", "julia_reeng_horas_intervalo_valido",
        "The hours tier is 1..11; 12 h or more would collide with the next business window.",
        f"    INSERT INTO {_S}.julia_reengajamento_config (org_id, horas_intervalo) VALUES (v_org, 12);",
        _CHECK, "a re-engagement config with a 12-hour interval",
    ),
    _reeng_probe(
        "reguas.nome_valido", "julia_reguas_nome_valido",
        "A regua with a blank name is unselectable in the UI.",
        _reeng_regua_ins().replace("'noc_probe'", "'   '"), _CHECK, "a regua with a blank name",
    ),
    _reeng_probe(
        "tentativas.ordem_1_a_3", "julia_regua_tentativas_ordem_1_a_3",
        "At most 3 attempts per regua is structural: ordem is 1..3 (and unique), so a 4th cannot exist.",
        _reeng_regua_ins() + "\n" + _reeng_tent_ins(_REENG_TENT_COLS, "4, 1, 'dias', 'noc probe', true"),
        _CHECK, "a 4th regua tentativa (ordem 4)",
    ),
    _reeng_probe(
        "tentativas.ordem_unica", "julia_regua_tentativas_ordem_uq",
        "Two attempts with the same ordem would both fire at the same step of the regua.",
        _reeng_regua_ins() + "\n" + _reeng_tent_ins(_REENG_TENT_COLS, _REENG_TENT_OK) + "\n"
        + _reeng_tent_ins(_REENG_TENT_COLS, _REENG_TENT_OK),
        _UNIQ, "two tentativas with the same ordem in one regua",
    ),
    _reeng_probe(
        "tentativas.espera_valida", "julia_regua_tentativas_espera_valida",
        "A zero or negative wait would fire the attempt immediately, ignoring the lead's silence window.",
        _reeng_regua_ins() + "\n" + _reeng_tent_ins(_REENG_TENT_COLS, "1, 0, 'dias', 'noc probe', true"),
        _CHECK, "a tentativa with a zero wait",
    ),
    _reeng_probe(
        "tentativas.unidade_valida", "julia_regua_tentativas_unidade_valida",
        "The wait unit is minutos|horas|dias; anything else cannot be turned into a schedule.",
        _reeng_regua_ins() + "\n" + _reeng_tent_ins(_REENG_TENT_COLS, "1, 1, 'semanas', 'noc probe', true"),
        _CHECK, "a tentativa with an unknown wait unit",
    ),
    _reeng_probe(
        "tentativas.texto_ou_template", "julia_regua_tentativas_texto_ou_template",
        "An attempt carries free text XOR a Cloud template: neither has nothing to send, both is ambiguous "
        "(a template needs the Cloud transport, free text must not go out as a mass send).",
        _reeng_regua_ins() + "\n"
        + _reeng_tent_ins("ordem, espera_valor, espera_unidade, ativa", "1, 1, 'dias', true"),
        _CHECK, "a tentativa with neither texto nor template_id",
    ),
    _reeng_probe(
        "reguas.ativa_exige_tentativa", "julia_regua_ativa_exige_tentativa_fn",
        "An active regua with no active attempt would be 'on' and do nothing; the live UI refuses to turn it on.",
        _reeng_regua_ins("ativa", "true"), _CHECK, "an active regua with no active tentativa",
    ),
    _reeng_probe(
        "tentativas.ultima_ativa", "julia_regua_ultima_tentativa_ativa_fn",
        "Removing the last active attempt of an active regua would silently turn it into a no-op.",
        _reeng_regua_ins() + "\n" + _reeng_tent_ins(_REENG_TENT_COLS, _REENG_TENT_OK) + "\n"
        f"    UPDATE {_S}.julia_reguas SET ativa = true WHERE org_id = v_org AND nome = 'noc_probe';\n"
        f"    DELETE FROM {_S}.julia_regua_tentativas WHERE org_id = v_org "
        f"AND regua_id IN (SELECT id FROM {_S}.julia_reguas WHERE org_id = v_org AND nome = 'noc_probe');",
        _CHECK, "deleting the last active tentativa of an active regua",
    ),
)


_M_JULIA_EQUIPES = "276_lais_equipes.sql"
_T_JULIA_EQUIPES = (f"{_S}.julia_equipes", f"{_S}.julia_equipe_membros", f"{_S}.julia_atribuicoes", f"{_S}.julia_contatos")


def _equipes_probe(probe_id: str, guard: str, rationale: str, ops_sql: str, cond: str, what: str) -> GuardProbe:
    return _sw_junction_probe(
        probe_id=f"julia_equipes.{probe_id}", guard_name=guard, migration=_M_JULIA_EQUIPES, rationale=rationale,
        fixtures=("registry",), ops_sql=ops_sql, sqlstate_condition=cond, what=what, tabelas=_T_JULIA_EQUIPES,
    )


def _equipe_ins(cols: str = "", vals: str = "") -> str:
    extra_c = f", {cols}" if cols else ""
    extra_v = f", {vals}" if vals else ""
    return f"    INSERT INTO {_S}.julia_equipes (org_id, nome{extra_c})\n    VALUES (v_org, 'noc_probe'{extra_v});"


#: Migration 276 -- Julia wave 11 (Equipes). Unapplied guards read `no_fixture` (tables absent), `refused` once applied.
_SW_JULIA_EQUIPES_PROBES: tuple[GuardProbe, ...] = (
    _equipes_probe(
        "nome_valido", "julia_equipes_nome_valido",
        "A team with a blank name is unselectable in the page and in the Conversas filter.",
        _equipe_ins().replace("'noc_probe'", "'   '"), _CHECK, "a team with a blank name",
    ),
    _equipes_probe(
        "modo_valido", "julia_equipes_modo_valido",
        "The mode picks who assigns the attendant (SW funnel or Julia); an unknown value would assign nobody, silently.",
        _equipe_ins("modo", "'bogus'"), _CHECK, "a team with an unknown assignment mode",
    ),
    _equipes_probe(
        "nome_unico", "julia_equipes_org_nome_uq",
        "Two teams with the same name in one org are indistinguishable in the picker.",
        _equipe_ins() + "\n" + _equipe_ins().replace("'noc_probe'", "'NOC_PROBE'"), _UNIQ,
        "two teams with the same name (case-insensitive) in one org",
    ),
    _equipes_probe(
        "membro_ordem_nao_negativa", "julia_equipe_membros_ordem_nao_negativa",
        "The order is the round-robin sequence; a negative position would sort ahead of every real member.",
        _equipe_ins() + "\n"
        f"    INSERT INTO {_S}.julia_equipe_membros (equipe_id, org_id, user_id, ordem)\n"
        f"    SELECT id, v_org, gen_random_uuid(), -1 FROM {_S}.julia_equipes WHERE org_id = v_org AND nome = 'noc_probe';",
        _CHECK, "a team member with a negative ordem",
    ),
    _equipes_probe(
        "atribuicao_criterio_valido", "julia_atribuicoes_criterio_valido",
        "The criterion says WHY the attendant was picked (keep-last vs round-robin); free text breaks the audit.",
        _julia_contato_ins() + "\n" + _julia_child_ins("julia_atribuicoes", "user_id, criterio", "gen_random_uuid(), 'bogus'"),
        _CHECK, "an attribution with an unknown criterio",
    ),
    _equipes_probe(
        "atribuicao_motivo_valido", "julia_atribuicoes_motivo_valido",
        "The motivo is the audit trail of why an attendant was picked; free text would break the metrics grouping.",
        _julia_contato_ins() + "\n" + _julia_child_ins("julia_atribuicoes", "user_id, motivo", "gen_random_uuid(), 'bogus'"),
        _CHECK,
        "an attribution with an unknown motivo",
    ),
)


_M_JULIA_CLOUD = "275_lais_cloud.sql"
_T_JULIA_CLOUD = (
    f"{_S}.julia_contatos", f"{_S}.julia_modelos", f"{_S}.julia_disparos", f"{_S}.julia_disparo_alvos",
    f"{_S}.julia_proprietarios_contatos",
)
_CLOUD_TEL = "'5511999990000'"


def _cloud_probe(probe_id: str, guard: str, rationale: str, ops_sql: str, cond: str, what: str) -> GuardProbe:
    return _sw_junction_probe(
        probe_id=f"julia_cloud.{probe_id}", guard_name=guard, migration=_M_JULIA_CLOUD, rationale=rationale,
        fixtures=("registry",), ops_sql=ops_sql, sqlstate_condition=cond, what=what, tabelas=_T_JULIA_CLOUD,
    )


def _cloud_modelo_ins(cols: str = "", vals: str = "") -> str:
    extra_c = f", {cols}" if cols else ""
    extra_v = f", {vals}" if vals else ""
    return f"    INSERT INTO {_S}.julia_modelos (org_id, nome, corpo{extra_c})\n    VALUES (v_org, 'noc_probe', 'Oi'{extra_v});"


def _cloud_disparo_ins(cols: str = "", vals: str = "") -> str:
    """A probe modelo, then a disparo pointing at it (all rolled back)."""
    extra_c = f", {cols}" if cols else ""
    extra_v = f", {vals}" if vals else ""
    return (
        _cloud_modelo_ins() + "\n"
        f"    INSERT INTO {_S}.julia_disparos (org_id, nome, segmento, modelo_id{extra_c})\n"
        f"    SELECT v_org, 'noc_probe', 'leads_3_15', id{extra_v} FROM {_S}.julia_modelos\n"
        "    WHERE org_id = v_org AND nome = 'noc_probe';"
    )


def _cloud_alvo_ins(cols: str = "", vals: str = "") -> str:
    extra_c = f", {cols}" if cols else ""
    extra_v = f", {vals}" if vals else ""
    return (
        f"    INSERT INTO {_S}.julia_disparo_alvos (org_id, disparo_id, telefone{extra_c})\n"
        f"    SELECT v_org, id, {_CLOUD_TEL}{extra_v} FROM {_S}.julia_disparos\n"
        "    WHERE org_id = v_org AND nome = 'noc_probe';"
    )


def _cloud_prop_ins(cols: str = "", vals: str = "") -> str:
    extra_c = f", {cols}" if cols else ""
    extra_v = f", {vals}" if vals else ""
    return (
        f"    INSERT INTO {_S}.julia_proprietarios_contatos (org_id, telefone, imovel_codigo{extra_c})\n"
        f"    VALUES (v_org, {_CLOUD_TEL}, 'NOC1'{extra_v});"
    )


#: Migration 275 -- Julia wave 12 (Cloud-API pages). Unapplied guards read `no_fixture` (tables absent) and must
#: read `refused` once applied. (`whatsapp_connections_transporte_valido` is a column CHECK on a table other
#: migrations own -- covered structurally by tests/test_migration_julia_cloud.py.)
_SW_JULIA_CLOUD_PROBES: tuple[GuardProbe, ...] = (
    _cloud_probe(
        "modelos.nome_valido", "julia_modelos_nome_valido",
        "A template with a blank name is unselectable in the UI and has no Meta template name.",
        _cloud_modelo_ins().replace("'noc_probe'", "'   '"), _CHECK, "a modelo with a blank name",
    ),
    _cloud_probe(
        "modelos.categoria_valida", "julia_modelos_categoria_valida",
        "The 8 categories are the page's tabs and drive the Meta category mapping; anything else has no tab.",
        _cloud_modelo_ins("categoria", "'bogus'"), _CHECK, "a modelo in an unknown categoria",
    ),
    _cloud_probe(
        "modelos.corpo_valido", "julia_modelos_corpo_valido",
        "Meta refuses a template body over 1024 characters (and an empty one has nothing to send).",
        _cloud_modelo_ins().replace("'Oi'", "'   '"), _CHECK, "a modelo with an empty body",
    ),
    _cloud_probe(
        "modelos.parametros_lista", "julia_modelos_parametros_lista",
        "`parametros` is read as the ordered list of registry keys; an object would crash every send.",
        _cloud_modelo_ins("parametros", "'{}'::jsonb"), _CHECK, "a modelo whose parametros is not a JSON array",
    ),
    _cloud_probe(
        "modelos.status_valido", "julia_modelos_status_valido",
        "The status drives whether a disparo may use the modelo; a free-text value would escape the Meta lifecycle.",
        _cloud_modelo_ins("status", "'bogus'"), _CHECK, "a modelo with an unknown status",
    ),
    _cloud_probe(
        "modelos.nome_unico", "julia_modelos_org_nome_uq",
        "Two templates with the same name in one org would be indistinguishable in the picker.",
        _cloud_modelo_ins() + "\n" + _cloud_modelo_ins().replace("'noc_probe'", "'NOC_PROBE'"), _UNIQ,
        "two modelos with the same name (case-insensitive) in one org",
    ),
    _cloud_probe(
        "disparos.nome_valido", "julia_disparos_nome_valido",
        "A disparo with a blank name is unselectable in the list.",
        _cloud_disparo_ins().replace("SELECT v_org, 'noc_probe', 'leads_3_15'", "SELECT v_org, '   ', 'leads_3_15'"),
        _CHECK, "a disparo with a blank name",
    ),
    _cloud_probe(
        "disparos.tipo_valido", "julia_disparos_tipo_valido",
        "Only remarketing and atualizacao_anuncios have a send path.",
        _cloud_disparo_ins("tipo", "'bogus'"), _CHECK, "a disparo of an unknown tipo",
    ),
    _cloud_probe(
        "disparos.segmento_valido", "julia_disparos_segmento_valido",
        "An unknown segment selects no targets and bypasses the day-window logic.",
        _cloud_disparo_ins().replace("'leads_3_15'", "'bogus'"), _CHECK, "a disparo with an unknown segmento",
    ),
    _cloud_probe(
        "disparos.status_valido", "julia_disparos_status_valido",
        "The status drives the tabs and the dispatch preconditions; a free-text value would escape both.",
        _cloud_disparo_ins("status", "'bogus'"), _CHECK, "a disparo with an unknown status",
    ),
    _cloud_probe(
        "disparos.tipo_segmento", "julia_disparos_tipo_segmento",
        "Owner updates (atualizacao_anuncios) only ever target owners, and remarketing only leads: a mismatched "
        "pair would message a lead about a listing update or an owner about a remarketing offer.",
        _cloud_disparo_ins("tipo", "'atualizacao_anuncios'"), _CHECK,
        "an atualizacao_anuncios disparo aimed at a lead segment",
    ),
    _cloud_probe(
        "disparos.agendado_exige_data", "julia_disparos_agendado_exige_data",
        "A scheduled disparo with no instant would never fire and never be cancelled by the clock.",
        _cloud_disparo_ins("status", "'agendado'"), _CHECK, "a scheduled disparo without agendado_para",
    ),
    _cloud_probe(
        "disparos.total_nao_negativo", "julia_disparos_total_nao_negativo",
        "A negative target count corrupts the cap arithmetic.",
        _cloud_disparo_ins("total_alvos", "-1"), _CHECK, "a disparo with a negative total_alvos",
    ),
    _cloud_probe(
        "alvos.status_valido", "julia_alvos_status_valido",
        "The target flow pendente -> enviado -> respondido -> enviado_sw | erro is the audit trail of a send.",
        _cloud_disparo_ins() + "\n" + _cloud_alvo_ins("status", "'bogus'"), _CHECK, "a disparo target with an unknown status",
    ),
    _cloud_probe(
        "alvos.telefone_valido", "julia_alvos_telefone_valido",
        "Meta addresses a recipient by 10..15 digits; a formatted number would be rejected per target.",
        _cloud_disparo_ins() + "\n" + _cloud_alvo_ins().replace(_CLOUD_TEL, "'+55 (11) 9'"), _CHECK,
        "a disparo target with a non-digit phone",
    ),
    _cloud_probe(
        "alvos.um_destino", "julia_alvos_um_destino",
        "A target is a lead XOR an owner; both would double-count and cross the opt-out rule.",
        _julia_contato_ins() + "\n" + _cloud_prop_ins() + "\n" + _cloud_disparo_ins() + "\n"
        f"    INSERT INTO {_S}.julia_disparo_alvos (org_id, disparo_id, contato_id, proprietario_id, telefone)\n"
        f"    SELECT v_org, d.id, c.id, p.id, {_CLOUD_TEL}\n"
        f"      FROM {_S}.julia_disparos d, {_S}.julia_contatos c, {_S}.julia_proprietarios_contatos p\n"
        "     WHERE d.org_id = v_org AND d.nome = 'noc_probe'\n"
        f"       AND c.org_id = v_org AND c.connection_id = {_JULIA_CONEXAO} AND c.chat_id = 'noc_probe'\n"
        f"       AND p.org_id = v_org AND p.telefone = {_CLOUD_TEL};",
        _CHECK, "a disparo target pointing at both a contato and a proprietario",
    ),
    _cloud_probe(
        "alvos.unico_por_telefone", "julia_alvos_disparo_telefone_uq",
        "One message per phone per disparo: a duplicate target double-sends and burns the per-chat template cap.",
        _cloud_disparo_ins() + "\n" + _cloud_alvo_ins() + "\n" + _cloud_alvo_ins(), _UNIQ,
        "two targets with the same phone in one disparo",
    ),
    _cloud_probe(
        "proprietarios.telefone_valido", "julia_proprietarios_telefone_valido",
        "An owner is contacted by digits only; a malformed phone can never be opted out by number.",
        _cloud_prop_ins().replace(_CLOUD_TEL, "'abc'"), _CHECK, "an owner with a non-digit phone",
    ),
    _cloud_probe(
        "proprietarios.codigo_valido", "julia_proprietarios_codigo_valido",
        "Without an imovel codigo the confirmed status/price has no listing to update.",
        _cloud_prop_ins().replace("'NOC1'", "'   '"), _CHECK, "an owner with a blank imovel codigo",
    ),
    _cloud_probe(
        "proprietarios.opt_out_coerente", "julia_proprietarios_opt_out_coerente",
        "LGPD (contract 17): an opt-out without its instant (or the reverse) cannot be audited or honoured.",
        _cloud_prop_ins("opt_out", "true"), _CHECK, "an owner flagged opt_out without opt_out_at",
    ),
    _cloud_probe(
        "proprietarios.preco_positivo", "julia_proprietarios_preco_positivo",
        "A confirmed price of zero or less would blank the listing price on the next apply.",
        _cloud_prop_ins("preco_confirmado", "0"), _CHECK, "an owner with a non-positive confirmed price",
    ),
    _cloud_probe(
        "proprietarios.unico", "julia_proprietarios_org_tel_imovel_uq",
        "One owner row per (phone, listing): a duplicate would double-message the owner about the same listing.",
        _cloud_prop_ins() + "\n" + _cloud_prop_ins(), _UNIQ, "two owner rows for the same phone and imovel",
    ),
)


_M_JULIA_PREC_TIPO = "283_lais_proprietarios_preco_tipo.sql"

#: Migration 283 -- owner-confirmed price kind. Unapplied the guard reads `no_fixture` (column absent), `refused` once applied.
_SW_JULIA_PROPRIETARIOS_TIPO_PROBES: tuple[GuardProbe, ...] = (
    _sw_junction_probe(
        probe_id="julia_proprietarios.preco_tipo_valido", guard_name="julia_proprietarios_preco_tipo_valido",
        migration=_M_JULIA_PREC_TIPO,
        rationale="The overlay picks valor_venda vs valor_locacao from this value; free text would apply the confirmed price to neither (or the wrong) column.",
        fixtures=("registry",), ops_sql=_cloud_prop_ins("preco_confirmado, preco_tipo_confirmado", "1000, 'bogus'"),
        sqlstate_condition=_CHECK, what="an owner confirmation whose price kind is neither venda nor locacao",
        tabelas=_T_JULIA_CLOUD,
    ),
)


_M_CONDOMINIOS = "265_condominios.sql"
_T_COND = (f"{_S}.condominios", f"{_S}.condominio_aliases", f"{_S}.condominio_eventos")


def _cond_ins(cols: str = "", vals: str = "") -> str:
    extra_c = f", {cols}" if cols else ""
    extra_v = f", {vals}" if vals else ""
    return (
        f"    INSERT INTO {_S}.condominios (org_id, nome, nome_normalizado{extra_c})\n"
        f"    VALUES (v_org, 'NOC_PROBE', 'NOC_PROBE'{extra_v});"
    )


def _cond_child_ins(table: str, cols: str, vals: str) -> str:
    """Insert a condominio, then a child row pointing at it (rolled back)."""
    return (
        _cond_ins() + "\n"
        + f"    INSERT INTO {_S}.{table} (org_id, condominio_id, {cols})\n"
        f"    SELECT v_org, id, {vals} FROM {_S}.condominios\n"
        "    WHERE org_id = v_org AND nome_normalizado = 'NOC_PROBE';"
    )


def _cond_probe(probe_id: str, guard_name: str, rationale: str, ops_sql: str, cond: str, what: str) -> GuardProbe:
    return _sw_junction_probe(
        probe_id=probe_id, guard_name=guard_name, migration=_M_CONDOMINIOS, rationale=rationale,
        fixtures=("registry",), ops_sql=ops_sql, sqlstate_condition=cond, what=what, tabelas=_T_COND,
    )


#: Migration 265 -- condomínios master list. Unapplied guards read `no_fixture`
#: (the tables do not exist yet) and must read `refused` once applied.
_SW_CONDOMINIOS_PROBES: tuple[GuardProbe, ...] = (
    _cond_probe(
        "condominios.tipo_valido", "condominios_tipo_check",
        "tipo feeds the price evaluator's location driver; an out-of-vocabulary value would be a silent miss.",
        _cond_ins("tipo", "'castelo'"), _CHECK, "a condomínio with an unknown tipo",
    ),
    _cond_probe(
        "condominios.status_valido", "condominios_status_check",
        "Only sugerido/validado/descartado exist; another value would escape the validation workflow.",
        _cond_ins("status_validacao", "'noc_probe_bogus'"), _CHECK, "a condomínio with an unknown status_validacao",
    ),
    _cond_probe(
        "condominios.seguranca_faixa", "condominios_seguranca_check",
        "The security level is a 1-5 scale; outside it the evaluator's feature is meaningless.",
        _cond_ins("seguranca_nivel", "9"), _CHECK, "a condomínio with seguranca_nivel 9",
    ),
    _cond_probe(
        "condominios.distancia_nao_negativa", "condominios_distancia_check",
        "A negative distance to Raposo is a typing error that would corrupt the location feature.",
        _cond_ins("distancia_raposo_km", "-1"), _CHECK, "a condomínio with a negative distancia_raposo_km",
    ),
    _cond_probe(
        "condominios.nome_unico_por_cidade", "uq_sw_condominios_org_nome_cidade",
        "One condomínio per (org, name, cidade): a duplicate would split one place's imóveis across two rows.",
        _cond_ins() + "\n" + _cond_ins(), _UNIQ, "two condomínios with the same normalized name and cidade",
    ),
    _cond_probe(
        "condominio_aliases.origem_valida", "condominio_aliases_origem_check",
        "origem tells the owner where a spelling came from; an unknown value breaks the merge-undo logic.",
        _cond_child_ins("condominio_aliases", "alias, alias_normalizado, origem", "'X', 'X', 'noc_probe_bogus'"),
        _CHECK, "an alias with an unknown origem",
    ),
    _cond_probe(
        "condominio_eventos.tipo_valido", "condominio_eventos_tipo_check",
        "The audit trail is a closed vocabulary; an unknown event type would be unreadable history.",
        _cond_child_ins("condominio_eventos", "tipo", "'noc_probe_bogus'"),
        _CHECK, "an audit event with an unknown tipo",
    ),
    GuardProbe(
        id="condominio_eventos.append_only",
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name="condominio_eventos_append_only",
        kind="write_refusal",
        migrations=(_M_CONDOMINIOS,),
        rationale="The merge/validate audit trail must be immutable; a rewritable log proves nothing.",
        sql=_do_block(
            "DECLARE\n  v_org uuid;\n  v_codigo text;\nBEGIN\n"
            + "".join(_table_fixture_check(t) for t in _T_COND)
            + "".join(
                f"  {select_sql.replace(' FROM ', ' INTO ' + into_vars + ' FROM ', 1)};\n"
                f"  IF {into_vars.split(',')[-1].strip()} IS NULL THEN\n"
                "    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no row for the registry fixture';\n"
                "  END IF;\n"
                for select_sql, into_vars in (_SW_FIXTURES["registry"],)
            )
            + "  BEGIN\n"
            + _cond_child_ins("condominio_eventos", "tipo", "'sugerido'") + "\n"
            + f"    UPDATE {_S}.condominio_eventos SET tipo = 'merge' WHERE org_id = v_org;\n"
            "    RAISE EXCEPTION 'NOC_PROBE:permitted: rewriting an audit event succeeded -- the trigger did not fire';\n"
            "  EXCEPTION WHEN OTHERS THEN\n"
            "    IF SQLERRM LIKE 'NOC_PROBE:%' THEN\n      RAISE;\n"
            "    ELSIF SQLERRM LIKE '%condominio_eventos is append-only%' THEN\n"
            "      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;\n"
            "    ELSE\n"
            "      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;\n"
            "    END IF;\n  END;\nEND;\n"
        ),
    ),
)


_SW_IMOVEL_MANUAL_PROBES: tuple[GuardProbe, ...] = (
    _sw_junction_probe(
        probe_id="imovel_captacao.valores_positivos",
        guard_name="imovel_captacao_valores_positivos",
        migration=_M_CAPTACAO,
        rationale="A manual listing priced at zero or less would print and filter as a real price.",
        fixtures=("registry",),
        ops_sql=_captacao_ins("valor_venda", "0"),
        sqlstate_condition=_CHECK,
        what="an imovel_captacao row with valor_venda = 0",
        tabelas=(_T_CAPTACAO,),
    ),
    _sw_junction_probe(
        probe_id="imovel_captacao.comodos_nao_negativos",
        guard_name="imovel_captacao_comodos_nao_negativos",
        migration=_M_CAPTACAO,
        rationale="A negative room count is a typing error that would corrupt the catalog's filters.",
        fixtures=("registry",),
        ops_sql=_captacao_ins("dormitorios", "-1"),
        sqlstate_condition=_CHECK,
        what="an imovel_captacao row with dormitorios = -1",
        tabelas=(_T_CAPTACAO,),
    ),
    _sw_junction_probe(
        probe_id="imovel_dados.drive_folder_url_drive",
        guard_name="imovel_dados_drive_folder_url_drive",
        migration=_M_CAPTACAO,
        rationale="The deal's Drive link is opened by agents; only a Google Drive URL may be stored there.",
        fixtures=("registry",),
        ops_sql=(
            f"    INSERT INTO {_S}.imovel_dados (org_id, codigo, drive_folder_url)\n"
            "    VALUES (v_org, v_codigo, 'http://example.com/not-drive');"
        ),
        sqlstate_condition=_CHECK,
        what="an imovel_dados row with a non-Drive drive_folder_url",
        tabelas=(_T_CAPTACAO,),
    ),
    _sw_junction_probe(
        probe_id="imovel_duplicata_candidatos.score_faixa",
        guard_name="imovel_duplicata_score_faixa",
        migration=_M_DUPLICATAS,
        rationale="The duplicate score is a 0..1 confidence; outside it the review ordering is meaningless.",
        fixtures=("registry",),
        ops_sql=_duplicata_ins("codigo_vista, score", "'NOC_PROBE_V', 2"),
        sqlstate_condition=_CHECK,
        what="a duplicate candidate with score 2",
        tabelas=(_T_DUPLICATAS,),
    ),
    _sw_junction_probe(
        probe_id="imovel_duplicata_candidatos.status_valido",
        guard_name="imovel_duplicata_status_valido",
        migration=_M_DUPLICATAS,
        rationale="Only pendente/descartado/confirmado exist; another value would be neither shown nor resolved.",
        fixtures=("registry",),
        ops_sql=_duplicata_ins("codigo_vista, score, status", "'NOC_PROBE_V', 0.5, 'noc_probe_bogus'"),
        sqlstate_condition=_CHECK,
        what="a duplicate candidate with an out-of-vocabulary status",
        tabelas=(_T_DUPLICATAS,),
    ),
    _sw_junction_probe(
        probe_id="imovel_duplicata_candidatos.lados_distintos",
        guard_name="imovel_duplicata_lados_distintos",
        migration=_M_DUPLICATAS,
        rationale="An imóvel cannot be its own duplicate; such a pair could only be confirmed into a self-link.",
        fixtures=("registry",),
        ops_sql=_duplicata_ins("codigo_vista, score", "v_codigo, 0.5"),
        sqlstate_condition=_CHECK,
        what="a duplicate candidate pairing a código with itself",
        tabelas=(_T_DUPLICATAS,),
    ),
    _sw_junction_probe(
        probe_id="imovel_duplicata_candidatos.par_unico",
        guard_name="uq_imovel_duplicata_par",
        migration=_M_DUPLICATAS,
        rationale="One row per (manual, Vista) pair is what makes 'Não é o mesmo' permanent — a second row would re-suggest a dismissed pair.",
        fixtures=("registry",),
        ops_sql=(
            _registry_ins("NOC_PROBE_V") + "\n"
            + _duplicata_ins("codigo_vista, score", "'NOC_PROBE_V', 0.5") + "\n"
            + _duplicata_ins("codigo_vista, score", "'NOC_PROBE_V', 0.6")
        ),
        sqlstate_condition=_UNIQ,
        what="two candidate rows for the same (manual, Vista) pair",
        tabelas=(_T_DUPLICATAS,),
    ),
    _sw_junction_probe(
        probe_id="imovel_registry.vinculo_nao_a_si_mesmo",
        guard_name="imovel_registry_vinculo_nao_a_si_mesmo",
        migration=_M_DUPLICATAS,
        rationale="A registry row linked to itself would make the link resolver loop or resolve an imóvel to itself.",
        fixtures=("registry",),
        ops_sql=(
            f"    UPDATE {_S}.imovel_registry SET vinculado_a = id\n"
            "    WHERE org_id = v_org AND codigo_canonical = v_codigo;"
        ),
        sqlstate_condition=_CHECK,
        what="a registry row linked to itself",
        tabelas=(_T_VINCULO_EVENTOS,),
    ),
    _sw_junction_probe(
        probe_id="imovel_registry.um_manual_por_vista",
        guard_name="uq_imovel_registry_vinculado_a",
        migration=_M_DUPLICATAS,
        rationale="One manual record per Vista listing: two would make property-level legal data follow two sources at once.",
        fixtures=("registry",),
        ops_sql=(
            _registry_ins("NOC_PROBE_T") + "\n"
            + _registry_ins("NOC_PROBE_A", _REG_PROBE_TARGET) + "\n"
            + _registry_ins("NOC_PROBE_B", _REG_PROBE_TARGET)
        ),
        sqlstate_condition=_UNIQ,
        what="two manual registry rows linked to the same Vista row",
        tabelas=(_T_VINCULO_EVENTOS,),
    ),
    _sw_junction_probe(
        probe_id="imovel_vinculo_eventos.acao_valida",
        guard_name="imovel_vinculo_eventos_acao_valida",
        migration=_M_DUPLICATAS,
        rationale="The link audit trail only knows vincular/desvincular; any other action is an unreadable audit row.",
        fixtures=("registry",),
        ops_sql=(
            f"    INSERT INTO {_S}.imovel_vinculo_eventos (org_id, codigo_manual, codigo_vista, acao)\n"
            "    VALUES (v_org, v_codigo, 'NOC_PROBE_V', 'noc_probe_bogus');"
        ),
        sqlstate_condition=_CHECK,
        what="a link audit event with an unknown acao",
        tabelas=(_T_VINCULO_EVENTOS,),
    ),
)


# ---------------------------------------------------------------------------
# Registry — seed editorial workflow (`noctusai_lib.domain.sql_templates.
# editorial_tables`; project `seed-editorial-workflow`, slice E2).
#
# THE TEMPLATE IS NOT APPLIED ANYWHERE YET, so these probes cannot depend on a
# product schema: every probe CREATEs a scratch schema (`noc_probe_editorial`)
# and EXECUTEs the template's own DDL inside the rolled-back probe transaction
# (Postgres DDL is transactional), then attacks it. They therefore prove the
# TEMPLATE — write-once versions, append-only events, write-via-transition-only,
# the separation-of-duties re-check, the CHECK/UNIQUE guards — and keep proving
# whatever migration renders it later (a consumer's migration is `editorial_
# tables("<schema>")` output; same text, same behaviour). Nothing is borrowed
# from production, and a `no_fixture` only means the DDL itself failed to build.
# ---------------------------------------------------------------------------

_EDITORIAL_SCHEMA = "noc_probe_editorial"
_EDITORIAL_PRODUCT = "seed-editorial"
_EDITORIAL_PROVENANCE = ("seed:noctusai_lib.domain.sql_templates.editorial_tables",)
_E = _EDITORIAL_SCHEMA
_EDITORIAL_FN_SIG = f"{_E}.editorial_transition(uuid,uuid,text,uuid,text[],text,jsonb,text)"
_EDITORIAL_GUC = "editorial.in_transition"


def _e_create() -> str:
    return (
        f"v_item := {_E}.editorial_create_item(v_org, 'doc', 'probe', v_a, "
        "ARRAY['editorial:editar'], '{\"t\":1}'::jsonb, repeat('a', 64));"
    )


def _e_step(action: str, actor: str, grant: str, motivo: str | None = None) -> str:
    m = "NULL" if motivo is None else f"'{motivo}'"
    return f"PERFORM {_E}.editorial_transition(v_org, v_item, '{action}', {actor}, ARRAY['editorial:{grant}'], {m});"


_E_SUBMIT = _e_step("submit", "v_a", "editar")
_E_APPROVE_ED = _e_step("approve_editorial", "v_b", "revisar")
_E_SIGNOFF = _e_step("approve_security", "v_c", "revisar_seguranca")
_E_FLAG_ON = f"PERFORM set_config('{_EDITORIAL_GUC}', 'on', true);"


def _editorial_probe(
    *, probe_id: str, guard_name: str, steps: tuple[str, ...], guard_fragment: str, what: str,
    rationale: str, allowed: bool = False, ddl: str | None = None, schema: str = _E,
    product: str = _EDITORIAL_PRODUCT, provenance: tuple[str, ...] = _EDITORIAL_PROVENANCE,
) -> GuardProbe:
    """One probe against the template as built in a rolled-back scratch schema.
    `allowed=True` is the inverse polarity (the sanctioned path must succeed).
    `ddl`/`schema`/`product`/`provenance` let a CONSUMER migration that renders the
    template (agents 018) reuse the same attack harness against its own build."""
    from noctusai_lib.domain.sql_templates import editorial_tables

    if ddl is None:
        ddl = editorial_tables(schema)
    fn_sig = _EDITORIAL_FN_SIG.replace(_E, schema)
    assert "$tpl$" not in ddl and _PROBE_TAG not in ddl, "editorial DDL collides with a probe dollar-tag"
    fragment_lit = _sql_lit(guard_fragment)
    what_lit = _sql_lit(what)
    body = "\n    ".join(steps)
    ok_word, bad_word = ("allowed", "blocked") if allowed else ("permitted", "refused")
    if allowed:
        tail = (
            f"RAISE EXCEPTION 'NOC_PROBE:allowed: {what_lit} succeeded — the sanctioned path is not blocked';"
        )
        handler = f"""    IF SQLERRM LIKE 'NOC_PROBE:allowed:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{fragment_lit}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:blocked: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;"""
    else:
        tail = f"RAISE EXCEPTION 'NOC_PROBE:permitted: {what_lit} succeeded — the guard under test did not fire';"
        handler = f"""    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{fragment_lit}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;"""
    sql = _do_block(f"""
DECLARE
  v_org uuid := gen_random_uuid();
  v_a uuid := gen_random_uuid();
  v_b uuid := gen_random_uuid();
  v_c uuid := gen_random_uuid();
  v_d uuid := gen_random_uuid();
  v_agent uuid := gen_random_uuid();
  v_col uuid := gen_random_uuid();
  v_item uuid;
BEGIN
  EXECUTE 'CREATE SCHEMA {schema}';
  EXECUTE $tpl$
{ddl}
  $tpl$;
  IF to_regprocedure('{fn_sig}') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: {schema}.editorial_transition was not built from the editorial_tables DDL';
  END IF;
  BEGIN
    {body}
    {tail}
  EXCEPTION WHEN OTHERS THEN
{handler}
  END;
END;
""")
    return GuardProbe(
        id=probe_id,
        product=product,
        schema=schema,
        guard_name=guard_name,
        kind="write_allowed" if allowed else "write_refusal",
        migrations=provenance,
        rationale=rationale,
        sql=sql,
    )


_E_VER = f"{_E}.editorial_versions"
_E_EVT = f"{_E}.editorial_events"
_E_ITM = f"{_E}.editorial_items"

_EDITORIAL_PROBES: tuple[GuardProbe, ...] = (
    _editorial_probe(
        probe_id="editorial_versions.update_refused", guard_name="editorial_guard_immutable",
        steps=(_e_create(), f"UPDATE {_E_VER} SET content = '{{\"t\":2}}'::jsonb WHERE item_id = v_item;"),
        guard_fragment="editorial_version_immutable", what="UPDATE of an editorial version's content",
        rationale="A version is write-once: the approval trail points at exactly what was approved.",
    ),
    _editorial_probe(
        probe_id="editorial_versions.delete_refused", guard_name="editorial_guard_immutable",
        steps=(_e_create(), f"DELETE FROM {_E_VER} WHERE item_id = v_item;"),
        guard_fragment="editorial_version_immutable", what="DELETE of an editorial version",
        rationale="Deleting a version would erase what a reviewer approved.",
    ),
    _editorial_probe(
        probe_id="editorial_events.update_refused", guard_name="editorial_guard_immutable",
        steps=(_e_create(), f"UPDATE {_E_EVT} SET actor_id = v_b WHERE item_id = v_item;"),
        guard_fragment="editorial_event_append_only", what="UPDATE of an editorial event's actor",
        rationale="The event log records who approved; rewriting an actor falsifies the audit trail.",
    ),
    _editorial_probe(
        probe_id="editorial_events.delete_refused", guard_name="editorial_guard_immutable",
        steps=(_e_create(), f"DELETE FROM {_E_EVT} WHERE item_id = v_item;"),
        guard_fragment="editorial_event_append_only", what="DELETE of an editorial event",
        rationale="Append-only: an event can never be removed.",
    ),
    _editorial_probe(
        probe_id="editorial_items.direct_state_write_refused", guard_name="editorial_guard_via_transition",
        steps=(_e_create(), f"UPDATE {_E_ITM} SET state = 'publicado', published_version_n = 1 WHERE id = v_item;"),
        guard_fragment="editorial_write_via_transition_only", what="a direct UPDATE of editorial_items.state",
        rationale="State moves only through editorial_transition — a direct write would skip legality and separation of duties.",
    ),
    _editorial_probe(
        probe_id="editorial_items.direct_delete_refused", guard_name="editorial_guard_via_transition",
        steps=(_e_create(), f"DELETE FROM {_E_ITM} WHERE id = v_item;"),
        guard_fragment="editorial_write_via_transition_only", what="a direct DELETE of an editorial item",
        rationale="Items are archived through the workflow, never deleted around it.",
    ),
    _editorial_probe(
        probe_id="editorial_events.forged_insert_refused", guard_name="editorial_guard_via_transition",
        steps=(
            _e_create(),
            f"INSERT INTO {_E_EVT} (item_id, version_n, action, from_state, to_state, actor_id) "
            "VALUES (v_item, 1, 'publish', 'revisao_seguranca', 'publicado', v_d);",
        ),
        guard_fragment="editorial_write_via_transition_only", what="a forged 'publish' event inserted directly",
        rationale="An event can only be written by a transition that passed the checks.",
    ),
    _editorial_probe(
        probe_id="editorial_versions.forged_insert_refused", guard_name="editorial_guard_via_transition",
        steps=(
            _e_create(),
            f"INSERT INTO {_E_VER} (item_id, n, content, content_sha, author_id) "
            "VALUES (v_item, 2, '{\"t\":2}'::jsonb, repeat('b', 64), v_b);",
        ),
        guard_fragment="editorial_write_via_transition_only", what="a version inserted directly",
        rationale="A new version is minted only by an `edit` transition that passed the grant check.",
    ),
    _editorial_probe(
        probe_id="editorial_transition.self_approval_refused", guard_name="editorial_transition",
        steps=(_e_create(), _E_SUBMIT, _e_step("approve_editorial", "v_a", "revisar")),
        guard_fragment="editorial_self_approval", what="the author approving their own version",
        rationale="Separation of duties: the approver of a version is never its author.",
    ),
    _editorial_probe(
        probe_id="editorial_transition.same_approver_refused", guard_name="editorial_transition",
        steps=(_e_create(), _E_SUBMIT, _E_APPROVE_ED, _e_step("approve_security", "v_b", "revisar_seguranca")),
        guard_fragment="editorial_same_approver", what="the editorial approver also giving the security sign-off",
        rationale="Two different people must look at a version before it can publish.",
    ),
    _editorial_probe(
        probe_id="editorial_transition.publish_without_signoff_refused", guard_name="editorial_transition",
        steps=(_e_create(), _E_SUBMIT, _E_APPROVE_ED, _e_step("publish", "v_d", "publicar")),
        guard_fragment="editorial_security_signoff_missing", what="publishing before the security sign-off",
        rationale="No publish without this round's security/source sign-off.",
    ),
    _editorial_probe(
        probe_id="editorial_transition.missing_grant_refused", guard_name="editorial_transition",
        steps=(_e_create(), _e_step("submit", "v_a", "revisar")),
        guard_fragment="editorial_missing_grant", what="a submit by a caller holding the wrong grant",
        rationale="Each transition names the grant it needs; the DB re-checks the grants it is handed.",
    ),
    _editorial_probe(
        probe_id="editorial_transition.illegal_transition_refused", guard_name="editorial_transition",
        steps=(_e_create(), _e_step("publish", "v_d", "publicar")),
        guard_fragment="editorial_illegal_transition", what="publishing a draft straight from rascunho",
        rationale="The state machine is fixed: rascunho cannot jump to publicado.",
    ),
    _editorial_probe(
        probe_id="editorial_transition.edit_during_review_refused", guard_name="editorial_transition",
        steps=(
            _e_create(), _E_SUBMIT,
            f"PERFORM {_E}.editorial_transition(v_org, v_item, 'edit', v_a, ARRAY['editorial:editar'], NULL, "
            "'{\"t\":2}'::jsonb, repeat('c', 64));",
        ),
        guard_fragment="editorial_illegal_transition", what="editing a version that is under review",
        rationale="One working draft at a time: a version under review cannot be replaced silently.",
    ),
    _editorial_probe(
        probe_id="editorial_transition.send_back_needs_motivo", guard_name="editorial_transition",
        steps=(_e_create(), _E_SUBMIT, _e_step("send_back", "v_b", "revisar")),
        guard_fragment="editorial_motivo_required", what="a send-back with no motivo",
        rationale="A send-back must say why.",
    ),
    _editorial_probe(
        probe_id="editorial_transition.other_org_item_not_found", guard_name="editorial_transition",
        steps=(
            _e_create(),
            f"PERFORM {_E}.editorial_transition(gen_random_uuid(), v_item, 'submit', v_a, ARRAY['editorial:editar']);",
        ),
        guard_fragment="editorial_item_not_found", what="a transition on another org's item",
        rationale="The org filter is part of the function, not only of the API above it.",
    ),
    _editorial_probe(
        probe_id="editorial_create_item.missing_grant_refused", guard_name="editorial_create_item",
        steps=(
            f"v_item := {_E}.editorial_create_item(v_org, 'doc', 'probe', v_a, ARRAY['editorial:revisar'], "
            "'{\"t\":1}'::jsonb, repeat('a', 64));",
        ),
        guard_fragment="editorial_missing_grant", what="creating an item without editorial:editar",
        rationale="Drafting needs editorial:editar like every other step.",
    ),
    _editorial_probe(
        probe_id="editorial_items.state_vocabulary", guard_name="editorial_items_state_check",
        steps=(
            _E_FLAG_ON,
            f"INSERT INTO {_E_ITM} (org_id, kind, ref, state) VALUES (v_org, 'doc', 'probe', 'bogus');",
        ),
        guard_fragment="editorial_items_state_check", what="an out-of-vocabulary item state",
        rationale="States are the fixed five; the CHECK is the last line if a function is ever edited.",
    ),
    _editorial_probe(
        probe_id="editorial_items.published_not_after_current", guard_name="editorial_items_version_order_check",
        steps=(
            _E_FLAG_ON,
            f"INSERT INTO {_E_ITM} (org_id, kind, ref, state, published_version_n, current_version_n) "
            "VALUES (v_org, 'doc', 'probe', 'publicado', 3, 1);",
        ),
        guard_fragment="editorial_items_version_order_check", what="a published version newer than the current one",
        rationale="published_version_n can never point past the newest version.",
    ),
    _editorial_probe(
        probe_id="editorial_items.org_kind_ref_unique", guard_name="editorial_items_org_kind_ref_key",
        steps=(_e_create(), _e_create()),
        guard_fragment="editorial_items_org_kind_ref_key", what="a second item with the same (org, kind, ref)",
        rationale="One governed item per (org, kind, ref) — the consumer's natural key.",
    ),
    _editorial_probe(
        probe_id="editorial_versions.sha_shape", guard_name="editorial_versions_sha_check",
        steps=(
            _e_create(), _E_FLAG_ON,
            f"INSERT INTO {_E_VER} (item_id, n, content, content_sha, author_id) "
            "VALUES (v_item, 2, '{}'::jsonb, 'not-a-sha', v_a);",
        ),
        guard_fragment="editorial_versions_sha_check", what="a version with a malformed content_sha",
        rationale="content_sha is the integrity witness; it must be a sha256 hex digest.",
    ),
    _editorial_probe(
        probe_id="editorial_events.motivo_required_for_send_back_and_archive", guard_name="editorial_events_motivo_check",
        steps=(
            _e_create(), _E_FLAG_ON,
            f"INSERT INTO {_E_EVT} (item_id, version_n, action, from_state, to_state, actor_id) "
            "VALUES (v_item, 1, 'archive', 'rascunho', 'arquivado', v_a);",
        ),
        guard_fragment="editorial_events_motivo_check", what="an archive event with no motivo",
        rationale="Even a function bug cannot log an unexplained send-back/archive.",
    ),
    _editorial_probe(
        probe_id="editorial_transition.full_round_allowed", guard_name="editorial_transition", allowed=True,
        steps=(
            _e_create(), _E_SUBMIT, _E_APPROVE_ED, _E_SIGNOFF, _e_step("publish", "v_d", "publicar"),
            f"IF (SELECT published_version_n FROM {_E_ITM} WHERE id = v_item) IS DISTINCT FROM 1 THEN "
            "RAISE EXCEPTION 'editorial_publish_did_not_set_published_version_n'; END IF;",
        ),
        guard_fragment="editorial_", what="a full create/submit/approve/sign-off/publish round",
        rationale="The guards must not block the sanctioned path (the transition flag must work, "
        "three different people + the right grants must publish).",
    ),
)


# ---------------------------------------------------------------------------
# Registry — agents adopts the editorial workflow (migration 018; project
# `seed-editorial-workflow`, slice E5). Same scratch-schema technique as above,
# but the DDL is the REAL `018_editorial_workflow.sql` (schema `agents` rewritten
# to the scratch schema) on top of a minimal copy of 013's knowledge tables — so
# the probes prove the migration BEFORE it is applied anywhere, and keep proving
# it after. The headline probe is the backfill proof: governing a collection must
# change nothing `search_knowledge` returns (the #1 risk of E5 is hiding docs).
# ---------------------------------------------------------------------------

_AGENTS_ED_SCHEMA = "noc_probe_agents_ed"
_AE = _AGENTS_ED_SCHEMA
_AGENTS_ED_MIGRATION = "products/agents/backend/migrations/018_editorial_workflow.sql"

_AGENTS_ED_FIXTURE = """
CREATE TABLE __S__.knowledge_collections (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL, agent_id uuid NOT NULL,
  slug text NOT NULL, nome text NOT NULL DEFAULT 'c', tag text NULL, descricao text NOT NULL DEFAULT '',
  ordem int NOT NULL DEFAULT 0, created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE (agent_id, slug));
CREATE TABLE __S__.knowledge_documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL,
  collection_id uuid NOT NULL REFERENCES __S__.knowledge_collections(id) ON DELETE CASCADE,
  agent_id uuid NOT NULL, slug text NOT NULL, titulo text NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('fonte','sintese','card','template','indice','outro')),
  proveniencia jsonb NOT NULL DEFAULT '{}', resumo text NULL, conteudo text NOT NULL,
  source_sha text NOT NULL, ativo boolean NOT NULL DEFAULT true,
  busca tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('portuguese', coalesce(titulo, '')), 'A') ||
    setweight(to_tsvector('portuguese', coalesce(resumo, '')), 'B') ||
    setweight(to_tsvector('portuguese', left(coalesce(conteudo, ''), 900000)), 'C')) STORED,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agent_id, slug));
CREATE TABLE __S__.knowledge_revisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL,
  document_id uuid NOT NULL REFERENCES __S__.knowledge_documents(id) ON DELETE CASCADE,
  op text NOT NULL CHECK (op IN ('create','update','archive','import')), snapshot jsonb NOT NULL,
  author_id uuid NULL, motivo text NULL, created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now());
"""


def _agents_ed_ddl() -> str:
    """013-shaped knowledge tables + the real 018 file, `agents` → scratch schema."""
    from settings import REPO_ROOT

    text = (REPO_ROOT / _AGENTS_ED_MIGRATION).read_text(encoding="utf-8")
    text = re.sub(r"\bagents\.", f"{_AE}.", text)
    text = text.replace("search_path = agents, public", f"search_path = {_AE}, public")
    # the dollar tags the harness reserves must not appear in the migration text
    return _AGENTS_ED_FIXTURE.replace("__S__", _AE) + text


_AE_FIXTURE_STEPS = (
    f"INSERT INTO {_AE}.knowledge_collections (id, org_id, agent_id, slug) VALUES (v_col, v_org, v_agent, 'c');",
    f"INSERT INTO {_AE}.knowledge_documents (org_id, collection_id, agent_id, slug, titulo, tipo, conteudo, "
    "source_sha, ativo) VALUES "
    "(v_org, v_col, v_agent, 'viva-a', 'Viva A', 'fonte', 'limiar alfa viva', 'sha-a', true), "
    "(v_org, v_col, v_agent, 'viva-b', 'Viva B', 'card', 'limiar beta viva', 'sha-b', true), "
    "(v_org, v_col, v_agent, 'arq', 'Arquivada', 'fonte', 'limiar arquivada', 'sha-z', false);",
)
_AE_GOVERN = f"PERFORM {_AE}.govern_collection(v_org, v_col, v_a);"
_AE_DOC = f"(SELECT id FROM {_AE}.knowledge_documents WHERE slug = 'viva-a')"
_AE_ITEM_OF_DOC = f"v_item := (SELECT editorial_item_id FROM {_AE}.knowledge_documents WHERE slug = 'viva-a');"


def _ae_probe(**kw) -> GuardProbe:
    steps = kw.pop("steps")
    return _editorial_probe(
        steps=(*_AE_FIXTURE_STEPS, *steps), ddl=_agents_ed_ddl(), schema=_AE, product="agents",
        provenance=(_AGENTS_ED_MIGRATION,), **kw,
    )


def _ae_count(where: str = "TRUE") -> str:
    return f"(SELECT count(*) FROM {_AE}.search_knowledge(v_org, v_agent, 'limiar', NULL, 20) WHERE {where})"


def _ae_publish_steps() -> tuple[str, ...]:
    """Governed doc `viva-a` is published v1; edit → v2 draft → full round → publish v2."""
    new = "'{\"titulo\":\"Viva A\",\"tipo\":\"fonte\",\"resumo\":null,\"conteudo\":\"limiar alfa NOVA\",\"proveniencia\":{},\"source_sha\":\"sha-a2\"}'::jsonb"
    return (
        _AE_GOVERN, _AE_ITEM_OF_DOC,
        f"PERFORM {_AE}.editorial_transition(v_org, v_item, 'edit', v_a, ARRAY['editorial:editar'], NULL, {new}, repeat('d', 64));",
        f"PERFORM {_AE}.editorial_transition(v_org, v_item, 'submit', v_a, ARRAY['editorial:editar']);",
        f"PERFORM {_AE}.editorial_transition(v_org, v_item, 'approve_editorial', v_b, ARRAY['editorial:revisar']);",
        f"PERFORM {_AE}.editorial_transition(v_org, v_item, 'approve_security', v_c, ARRAY['editorial:revisar_seguranca']);",
        f"PERFORM {_AE}.editorial_transition(v_org, v_item, 'publish', v_d, ARRAY['editorial:publicar']);",
    )


_AGENTS_EDITORIAL_PROBES: tuple[GuardProbe, ...] = (
    _ae_probe(
        probe_id="agents_editorial.backfill_keeps_retrieval", guard_name="govern_collection", allowed=True,
        steps=(
            "IF " + _ae_count() + " <> 2 THEN RAISE EXCEPTION 'agents_editorial_fixture_miscount'; END IF;",
            _AE_GOVERN,
            "IF " + _ae_count() + " <> 2 THEN RAISE EXCEPTION 'agents_editorial_backfill_hides_documents: search_knowledge changed'; END IF;",
            f"IF (SELECT count(*) FROM {_AE}.knowledge_documents WHERE ativo) <> 2 "
            f"OR (SELECT count(*) FROM {_AE}.knowledge_documents WHERE editorial_item_id IS NULL) <> 0 "
            f"OR (SELECT count(*) FROM {_AE}.editorial_items WHERE state = 'publicado' AND published_version_n = 1) <> 2 "
            f"OR (SELECT count(*) FROM {_AE}.editorial_items WHERE state = 'arquivado') <> 1 THEN "
            "RAISE EXCEPTION 'agents_editorial_backfill_wrong_state'; END IF;",
            # idempotent: a second call links nothing new and still hides nothing
            _AE_GOVERN,
            "IF " + _ae_count() + " <> 2 THEN RAISE EXCEPTION 'agents_editorial_backfill_hides_documents: second call'; END IF;",
        ),
        guard_fragment="agents_editorial_", what="governing a collection that already holds live documents",
        rationale="Backfill must make every live document the PUBLISHED v1 — retrieval returns exactly what it "
        "returned before (the E5 #1 risk: hiding documents).",
    ),
    _ae_probe(
        probe_id="agents_editorial.direct_content_edit_refused", guard_name="knowledge_guard_governed",
        steps=(_AE_GOVERN, f"UPDATE {_AE}.knowledge_documents SET conteudo = 'adulterado' WHERE slug = 'viva-a';"),
        guard_fragment="knowledge_governed_write_via_editorial", what="a direct UPDATE of a governed document's content",
        rationale="Live governed content changes only through the review (publish sync), never around it.",
    ),
    _ae_probe(
        probe_id="agents_editorial.direct_deactivate_refused", guard_name="knowledge_guard_governed",
        steps=(_AE_GOVERN, f"UPDATE {_AE}.knowledge_documents SET ativo = false WHERE slug = 'viva-a';"),
        guard_fragment="knowledge_governed_write_via_editorial", what="a direct deactivation of a governed document",
        rationale="Archiving a governed document goes through the editorial archive transition (with a motivo).",
    ),
    _ae_probe(
        probe_id="agents_editorial.unpublished_cannot_be_active", guard_name="knowledge_guard_governed",
        steps=(
            f"v_item := {_AE}.editorial_create_item(v_org, 'knowledge_document', v_agent::text || '/novo', v_a, "
            "ARRAY['editorial:editar'], '{\"titulo\":\"N\",\"tipo\":\"fonte\",\"conteudo\":\"x\",\"source_sha\":\"s\"}'::jsonb, "
            "repeat('e', 64));",
            f"INSERT INTO {_AE}.knowledge_documents (org_id, collection_id, agent_id, slug, titulo, tipo, conteudo, "
            "source_sha, ativo, editorial_item_id) VALUES (v_org, v_col, v_agent, 'novo', 'N', 'fonte', 'x', 's', true, v_item);",
        ),
        guard_fragment="knowledge_unpublished_cannot_be_active", what="activating a document whose item was never published",
        rationale="A draft must be invisible to retrieval until its first publish.",
    ),
    _ae_probe(
        probe_id="agents_editorial.one_document_per_item", guard_name="idx_agents_knowledge_documents_editorial_item",
        steps=(
            _AE_GOVERN,
            f"INSERT INTO {_AE}.knowledge_documents (org_id, collection_id, agent_id, slug, titulo, tipo, conteudo, "
            "source_sha, ativo, editorial_item_id) SELECT v_org, v_col, v_agent, 'dup', 'Dup', 'fonte', 'x', 's', false, "
            f"editorial_item_id FROM {_AE}.knowledge_documents WHERE slug = 'viva-a';",
        ),
        guard_fragment="idx_agents_knowledge_documents_editorial_item",
        what="pointing two documents at the same editorial item",
        rationale="One item governs exactly one document row; two rows sharing an item would publish into both.",
    ),
    _ae_probe(
        probe_id="agents_editorial.draft_is_invisible_published_keeps_serving", guard_name="knowledge_sync_published",
        allowed=True,
        steps=(
            _AE_GOVERN, _AE_ITEM_OF_DOC,
            f"PERFORM {_AE}.editorial_transition(v_org, v_item, 'edit', v_a, ARRAY['editorial:editar'], NULL, "
            "'{\"titulo\":\"Viva A\",\"tipo\":\"fonte\",\"resumo\":null,\"conteudo\":\"limiar alfa NOVA\","
            "\"proveniencia\":{},\"source_sha\":\"sha-a2\"}'::jsonb, repeat('d', 64));",
            f"IF (SELECT conteudo FROM {_AE}.knowledge_documents WHERE slug = 'viva-a') <> 'limiar alfa viva' "
            "OR " + _ae_count("slug = 'viva-a'") + " <> 1 THEN "
            "RAISE EXCEPTION 'agents_editorial_draft_leaked_or_published_stopped_serving'; END IF;",
        ),
        guard_fragment="agents_editorial_", what="minting a draft version of a published governed document",
        rationale="Edit-after-publish: the published version keeps serving, the draft is invisible.",
    ),
    _ae_probe(
        probe_id="agents_editorial.publish_syncs_the_row", guard_name="knowledge_sync_published", allowed=True,
        steps=(
            *_ae_publish_steps(),
            f"IF (SELECT conteudo FROM {_AE}.knowledge_documents WHERE slug = 'viva-a') <> 'limiar alfa NOVA' "
            f"OR (SELECT source_sha FROM {_AE}.knowledge_documents WHERE slug = 'viva-a') <> 'sha-a2' "
            f"OR NOT (SELECT ativo FROM {_AE}.knowledge_documents WHERE slug = 'viva-a') "
            f"OR (SELECT count(*) FROM {_AE}.knowledge_revisions WHERE op = 'update' AND motivo = 'editorial:publish') <> 1 THEN "
            "RAISE EXCEPTION 'agents_editorial_publish_did_not_sync'; END IF;",
        ),
        guard_fragment="agents_editorial_", what="publishing a new version of a governed document",
        rationale="Publish copies the published version onto the row in the same transaction, and writes the revision.",
    ),
    _ae_probe(
        probe_id="agents_editorial.archive_deactivates_the_row", guard_name="knowledge_sync_published", allowed=True,
        steps=(
            _AE_GOVERN, _AE_ITEM_OF_DOC,
            f"PERFORM {_AE}.editorial_transition(v_org, v_item, 'archive', v_d, ARRAY['editorial:publicar'], 'obsoleto');",
            f"IF (SELECT ativo FROM {_AE}.knowledge_documents WHERE slug = 'viva-a') "
            "OR " + _ae_count("slug = 'viva-a'") + " <> 0 THEN "
            "RAISE EXCEPTION 'agents_editorial_archive_did_not_deactivate'; END IF;",
        ),
        guard_fragment="agents_editorial_", what="archiving a governed document",
        rationale="Archive removes the document from retrieval atomically with the transition.",
    ),
    _ae_probe(
        probe_id="agents_editorial.ungoverned_documents_unaffected", guard_name="knowledge_guard_governed", allowed=True,
        steps=(
            f"UPDATE {_AE}.knowledge_documents SET conteudo = 'limiar alfa editada' WHERE slug = 'viva-a';",
            "IF " + _ae_count() + " <> 2 THEN RAISE EXCEPTION 'agents_editorial_ungoverned_write_blocked'; END IF;",
        ),
        guard_fragment="agents_editorial_", what="editing a document of a collection nobody governed",
        rationale="Package-sync collections stay ungoverned: the guard only bites linked (governed) documents.",
    ),
)

# ---------------------------------------------------------------------------
# Registry — social_wiring branding model (migration 204)
# ---------------------------------------------------------------------------
#
# Three partial unique indexes. Self-provisioning: mc_brand_kits has no FK on
# org_id (a fresh gen_random_uuid() org is enough) and mc_brand_references
# only references the probe's own kit, so no fixture row is needed. Every
# insert sits in the sub-block that always ends in RAISE — nothing persists.

_BRANDING_MIGRATIONS = ("204_branding_model.sql",)


def _branding_unique_probe(*, probe_id: str, guard_name: str, steps: str, what: str, rationale: str) -> GuardProbe:
    what_lit = _sql_lit(what)
    return GuardProbe(
        id=probe_id,
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name=guard_name,
        kind="write_refusal",
        migrations=_BRANDING_MIGRATIONS,
        rationale=rationale,
        sql=_do_block(f"""
DECLARE
  v_org uuid := gen_random_uuid();
  v_kit uuid;
BEGIN
  IF to_regclass('{_SW_SCHEMA}.mc_brand_kits') IS NULL
     OR to_regclass('{_SW_SCHEMA}.mc_brand_references') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: branding tables do not exist (migration 204 not applied)';
  END IF;
  BEGIN
{steps}
    RAISE EXCEPTION 'NOC_PROBE:permitted: {what_lit} succeeded — the unique guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{guard_name}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
    )


_BRANDING_PROBES: tuple[GuardProbe, ...] = (
    _branding_unique_probe(
        probe_id="branding.one_template_per_org",
        guard_name="mc_brand_kits_one_template_per_org",
        steps=(
            f"    INSERT INTO {_SW_SCHEMA}.mc_brand_kits (org_id, name, is_template) VALUES (v_org, 'NOC probe A', true);\n"
            f"    INSERT INTO {_SW_SCHEMA}.mc_brand_kits (org_id, name, is_template) VALUES (v_org, 'NOC probe B', true);"
        ),
        what="a second Branding Template in the same org",
        rationale="One Branding Template per org: the clone-from-template flow reads 'the' template.",
    ),
    _branding_unique_probe(
        probe_id="branding.unowned_slug_unique",
        guard_name="mc_brand_kits_unowned_slug_uniq",
        steps=(
            f"    INSERT INTO {_SW_SCHEMA}.mc_brand_kits (org_id, name, slug) VALUES (v_org, 'NOC probe A', 'noc-probe');\n"
            f"    INSERT INTO {_SW_SCHEMA}.mc_brand_kits (org_id, name, slug) VALUES (v_org, 'NOC probe B', 'noc-probe');"
        ),
        what="two marca-less brandings with the same (org, slug)",
        rationale="NULL marca_id rows are distinct in the 007 index, so a slug-keyed import would duplicate them.",
    ),
    _branding_unique_probe(
        probe_id="branding.reference_asset_unique",
        guard_name="mc_brand_references_asset_uniq",
        steps=(
            f"    INSERT INTO {_SW_SCHEMA}.mc_brand_kits (org_id, name) VALUES (v_org, 'NOC probe') RETURNING id INTO v_kit;\n"
            f"    INSERT INTO {_SW_SCHEMA}.mc_brand_references (org_id, brand_kit_id, kind, label, storage_path) "
            "VALUES (v_org, v_kit, 'logo', 'noc-probe', 'noc/probe/a');\n"
            f"    INSERT INTO {_SW_SCHEMA}.mc_brand_references (org_id, brand_kit_id, kind, label, storage_path) "
            "VALUES (v_org, v_kit, 'logo', 'noc-probe', 'noc/probe/b');"
        ),
        what="a second uploaded asset with the same (branding, kind, label)",
        rationale="Re-importing a design system must replace, never duplicate, an uploaded asset.",
    ),
)


# ─── SW 218 — campanha intake (sw-lead-to-contract S1) ─────────────────────
_SW_218_SETUP = (
    _table_fixture_check("social_wiring.campanha_veiculacoes")
    + _PROBE_ORG_SETUP
    + """
  INSERT INTO social_wiring.campanhas (org_id, nome) VALUES (v_org, 'noc probe campanha')
  RETURNING id INTO v_prod;  -- v_prod reused as the campanha id
"""
)

_SW_218_PROBES: tuple[GuardProbe, ...] = (
    GuardProbe(
        id="social_wiring.campanha_veiculacoes.meta_ref_unique",
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name="campanha_veiculacoes_meta_ref_unico",
        kind="write_refusal",
        migrations=("218_campanha_intake.sql",),
        sql=_constraint_refusal_probe(
            setup_sql=_SW_218_SETUP,
            op_sql="""
    INSERT INTO social_wiring.campanha_veiculacoes (org_id, campanha_id, canal, nivel, ref_tabela, ref_codigo)
    VALUES (v_org, v_prod, 'meta_ads', 'ad', 'ads_objects', 'noc-probe-ad'),
           (v_org, v_prod, 'meta_ads', 'ad', 'ads_objects', 'noc-probe-ad');
""",
            sqlstate_condition="unique_violation",
            constraint_names=("campanha_veiculacoes_meta_ref_unico",),
            what="the same Meta ad registered twice in one org",
        ),
        rationale=(
            "Lead intake resolves ad/adset/campaign/form ids to ONE campanha (CONTRACT §1.2); "
            "a duplicate row would make the imóvel link a guess."
        ),
    ),
    GuardProbe(
        id="social_wiring.campanha_veiculacoes.meta_requires_nivel",
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name="campanha_veiculacoes_nivel_valido",
        kind="write_refusal",
        migrations=("218_campanha_intake.sql", "227_campanha_veiculacoes_nivel_not_null.sql"),
        sql=_constraint_refusal_probe(
            setup_sql=_SW_218_SETUP,
            op_sql="""
    INSERT INTO social_wiring.campanha_veiculacoes (org_id, campanha_id, canal, nivel, ref_tabela, ref_codigo)
    VALUES (v_org, v_prod, 'meta_ads', NULL, 'ads_objects', 'noc-probe-no-level');
""",
            sqlstate_condition="check_violation",
            constraint_names=("campanha_veiculacoes_nivel_valido",),
            what="a Meta veiculação without a nivel",
        ),
        rationale=(
            "Without the level, an id could match the wrong Meta object kind at intake "
            "(ad vs adset vs campaign vs form)."
        ),
    ),
)

# ---------------------------------------------------------------------------
# Registry — social_wiring.transcricoes (225): the shared voice-transcription layer.
# ---------------------------------------------------------------------------

_TRANSCRICOES_MIGRATION = "225_transcricoes.sql"
_TRANSCRICOES_SETUP = (
    _table_fixture_check("social_wiring.transcricoes")
    + _PROBE_ORG_SETUP
)

_TRANSCRICOES_PROBES: tuple[GuardProbe, ...] = (
    GuardProbe(
        id="social_wiring.transcricoes.reembolso_so_terminal",
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name="transcricoes_reembolso_so_terminal",
        kind="write_refusal",
        migrations=(_TRANSCRICOES_MIGRATION,),
        sql=_constraint_refusal_probe(
            setup_sql=_TRANSCRICOES_SETUP,
            op_sql="""
    INSERT INTO social_wiring.transcricoes
        (org_id, user_id, contexto_tipo, contexto_ref, storage_path, bytes, duracao_s, formato,
         status, minutos_reembolsados)
    VALUES (v_org, gen_random_uuid(), 'noc_probe', 'noc-probe', 'noc/probe.webm', 1, 5, 'webm',
            'concluida', true);
""",
            sqlstate_condition="check_violation",
            constraint_names=("transcricoes_reembolso_so_terminal",),
            what="a refund recorded on a transcription that succeeded",
        ),
        rationale=(
            "Refunded minutes stop counting toward every quota window; a refund on a "
            "finished transcription would hand back minutes that were really used."
        ),
    ),
    GuardProbe(
        id="social_wiring.reservar_transcricao.limite_usuario",
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name="reservar_transcricao",
        kind="write_refusal",
        migrations=(_TRANSCRICOES_MIGRATION,),
        sql=_do_block(f"""
DECLARE
  v_org uuid;
  v_user uuid := gen_random_uuid();
  v_res jsonb;
BEGIN
{_TRANSCRICOES_SETUP}
  PERFORM social_wiring.reservar_transcricao(
    gen_random_uuid(), v_org, v_user, 5, 100, 'webm', 'noc_probe', 'a', 'noc/a.webm');
  PERFORM social_wiring.reservar_transcricao(
    gen_random_uuid(), v_org, v_user, 5, 100, 'webm', 'noc_probe', 'b', 'noc/b.webm');
  v_res := social_wiring.reservar_transcricao(
    gen_random_uuid(), v_org, v_user, 5, 100, 'webm', 'noc_probe', 'c', 'noc/c.webm');
  IF (v_res->>'ok')::boolean THEN
    RAISE EXCEPTION 'NOC_PROBE:permitted: a third in-flight transcription for one user succeeded — the quota gate did not fire';
  ELSIF v_res->>'codigo' = 'limite_usuario' THEN
    RAISE EXCEPTION 'NOC_PROBE:refused: third in-flight transcription refused with %', v_res->>'codigo';
  ELSE
    RAISE EXCEPTION 'NOC_PROBE:ambiguous: refused with an unexpected code %', v_res->>'codigo';
  END IF;
END;
"""),
        rationale=(
            "The per-user in-flight cap (2) is what keeps one person from filling the "
            "single-lane transcriber queue; it lives in SQL so it is atomic under the advisory lock."
        ),
    ),
)


_CEREBRO_MIGRATION = "224_cs_cerebro.sql"


def _cerebro_unique_probe(
    *, probe_id: str, guard_name: str, rationale: str, setup_and_dupes: str, detail: str,
) -> GuardProbe:
    """Segundo Cérebro unique-index probe: borrow one real org, fabricate a probe
    marca (rolled back with everything else), run the duplicate-producing
    statements in `setup_and_dupes` (v_org / v_marca are in scope), expect the
    named index to refuse."""
    return GuardProbe(
        id=probe_id,
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name=guard_name,
        kind="write_refusal",
        migrations=(_CEREBRO_MIGRATION,),
        rationale=rationale,
        sql=_do_block(f"""
DECLARE
  v_org uuid;
  v_marca uuid;
  v_brain uuid;
BEGIN
  SELECT id INTO v_org FROM public.organizations LIMIT 1;
  IF v_org IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no public.organizations row to own a probe marca';
  END IF;
  INSERT INTO {_SW_SCHEMA}.marcas (org_id, slug, name)
  VALUES (v_org, 'noc-probe-cerebro', 'noc-probe-cerebro')
  RETURNING id INTO v_marca;
  BEGIN
{setup_and_dupes}
    RAISE EXCEPTION 'NOC_PROBE:permitted: {detail} succeeded — the unique guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{guard_name}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
    )


_CEREBRO_PROBES: tuple[GuardProbe, ...] = (
    _cerebro_unique_probe(
        probe_id="cs_brains.marca_sistema.unique",
        guard_name="cs_brains_marca_sistema_uq",
        rationale=(
            "A marca has exactly one Sistema brain per template: the lazy "
            "`GET /brains` creation is idempotent only because this index turns a "
            "concurrent double-create into a conflict the service re-reads."
        ),
        setup_and_dupes=f"""    INSERT INTO {_SW_SCHEMA}.cs_brains (org_id, marca_id, kind, template_slug, name)
    VALUES (v_org, v_marca, 'sistema', 'nucleo-de-influencia', 'noc-probe-a');
    INSERT INTO {_SW_SCHEMA}.cs_brains (org_id, marca_id, kind, template_slug, name)
    VALUES (v_org, v_marca, 'sistema', 'nucleo-de-influencia', 'noc-probe-b');""",
        detail="second Sistema brain of the same template",
    ),
    _cerebro_unique_probe(
        probe_id="cs_brains.marca_name.unique",
        guard_name="cs_brains_marca_name_uq",
        rationale=(
            "Brain names are unique per marca, case-insensitively; the API "
            "pre-checks and answers 409, this index is the backstop under a race."
        ),
        setup_and_dupes=f"""    INSERT INTO {_SW_SCHEMA}.cs_brains (org_id, marca_id, kind, name)
    VALUES (v_org, v_marca, 'custom', 'noc probe brain');
    INSERT INTO {_SW_SCHEMA}.cs_brains (org_id, marca_id, kind, name)
    VALUES (v_org, v_marca, 'custom', 'NOC PROBE BRAIN');""",
        detail="case-variant duplicate brain name",
    ),
    _cerebro_unique_probe(
        probe_id="cs_brain_answers.brain_question.unique",
        guard_name="cs_brain_answers_brain_question_uq",
        rationale=(
            "One answer per (brain, question): autosave upserts by this key, so a "
            "second row would make 'the answer' ambiguous for review and synthesis."
        ),
        setup_and_dupes=f"""    INSERT INTO {_SW_SCHEMA}.cs_brains (org_id, marca_id, kind, template_slug, name)
    VALUES (v_org, v_marca, 'sistema', 'nucleo-de-influencia', 'noc-probe-a')
    RETURNING id INTO v_brain;
    INSERT INTO {_SW_SCHEMA}.cs_brain_answers (org_id, brain_id, question_id, text)
    VALUES (v_org, v_brain, 'nucleo-de-influencia.01', 'a');
    INSERT INTO {_SW_SCHEMA}.cs_brain_answers (org_id, brain_id, question_id, text)
    VALUES (v_org, v_brain, 'nucleo-de-influencia.01', 'b');""",
        detail="duplicate (brain, question) answer",
    ),
)


_CORE_JOBS_DEDUPE_UNIQUE_PROBE = GuardProbe(
    id="core.jobs.dedupe_key.unique",
    product="core",
    schema="public",
    guard_name="ux_jobs_dedupe_key",
    kind="write_refusal",
    migrations=("074_transcription_api.sql",),
    rationale=(
        "Core's job queue (seed jobs template; first consumer: the platform "
        "transcription API) dedupes enqueues on dedupe_key — without the "
        "unique index a retried submit enqueues the same transcription twice "
        "and the one-job-at-a-time worker burns its capacity on duplicates."
    ),
    sql=_do_block("""
DECLARE
  v_key text := 'noc_probe_dedupe_' || gen_random_uuid()::text;
BEGIN
  IF to_regclass('public.jobs') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: public.jobs does not exist (core migration transcription_api not applied)';
  END IF;
  BEGIN
    INSERT INTO public.jobs (type, payload, dedupe_key) VALUES ('noc_probe', '{}'::jsonb, v_key);
    INSERT INTO public.jobs (type, payload, dedupe_key) VALUES ('noc_probe', '{}'::jsonb, v_key);
    RAISE EXCEPTION 'NOC_PROBE:permitted: duplicate dedupe_key insert succeeded — the unique guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%ux_jobs_dedupe_key%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
)


# ---------------------------------------------------------------------------
# Registry — public.products SSO promotion guard (core migration 075).
# A transition INTO deploy_scope='live' without sso_callback_verified_at is
# refused (the probe verdict is recorded by POST /deploy-scope). Borrows an
# existing ativo dev product inside the rollback-only wrapper; nothing persists.
# ---------------------------------------------------------------------------

_SSO_PROMOTION_PROBE = GuardProbe(
    id="products.sso_promotion_requires_probe",
    product="core",
    schema="public",
    guard_name="enforce_sso_promotion_probe",
    kind="write_refusal",
    migrations=("075_sso_promotion_probe_guard.sql",),
    rationale=(
        "Promoting a product to live makes its SSO regime strict; only the API "
        "probes the served bundle. The trigger refuses a hand-written promotion "
        "that lacks the recorded probe verdict (SSO P2.1)."
    ),
    sql=_do_block("""
DECLARE
  v_id uuid;
  v_path text := 'INSERT';
BEGIN
  IF to_regprocedure('public.enforce_sso_promotion_probe()') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: enforce_sso_promotion_probe() missing — core 075 not applied';
  END IF;
  -- Path 1 (always runs, catalog-independent): INSERT a synthetic live row.
  BEGIN
    INSERT INTO public.products (nome, slug, url_base, ativo, deploy_scope, sso_callback_verified_at)
    VALUES ('noc-probe', 'noc-probe-sso-promotion', 'https://noc-probe.invalid', true, 'live', NULL);
    RAISE EXCEPTION 'NOC_PROBE:permitted: INSERT of a live product without a probe verdict succeeded — the guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM NOT LIKE '%without a passing SSO callback probe%' THEN
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected INSERT error (not the guard under test): %', SQLERRM;
    END IF;
  END;
  -- Path 2 (only when a dev product happens to exist): UPDATE transition.
  SELECT id INTO v_id FROM public.products WHERE ativo IS TRUE AND deploy_scope = 'dev' LIMIT 1;
  IF v_id IS NOT NULL THEN
    v_path := 'INSERT+UPDATE';
    BEGIN
      UPDATE public.products SET deploy_scope = 'live', sso_callback_verified_at = NULL WHERE id = v_id;
      RAISE EXCEPTION 'NOC_PROBE:permitted: UPDATE promotion to live without a probe verdict succeeded — the guard did not fire';
    EXCEPTION WHEN OTHERS THEN
      IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
        RAISE;
      ELSIF SQLERRM NOT LIKE '%without a passing SSO callback probe%' THEN
        RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected UPDATE error (not the guard under test): %', SQLERRM;
      END IF;
    END;
  END IF;
  RAISE EXCEPTION 'NOC_PROBE:refused: % path(s) refused by enforce_sso_promotion_probe', v_path;
END;
"""),
)


# ---------------------------------------------------------------------------
# Registry — social-wiring migration 239 (spawn_funil_card no silent drop).
# Incident 2026-10-10: the funil card was silently dropped by ON CONFLICT DO
# NOTHING against a GLOBAL unique on atendimentos.meta_ads_lead_id. Both probes
# are fully self-provisioning (fabricated orgs, a fabricated meta lead whose
# INSERT fires the real spawn trigger) inside the rolled-back transaction; the
# only `no_fixture` path is "migration 239 is not applied" — until then
# predeploy's db_guards leg is blocked, the same apply-before-deploy contract
# APPLIED.md states for schema_drift.
# ---------------------------------------------------------------------------

_SW_240_MIGRATIONS = ("240_spawn_funil_card_sem_descarte_silencioso.sql",)

_SW_240_META_UNIQUE_PROBE = GuardProbe(
    id="social-wiring.atendimentos.org_meta_lead.unique",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="uq_sw_atendimentos_org_meta_lead",
    kind="write_refusal",
    migrations=_SW_240_MIGRATIONS,
    rationale=(
        "One card per (org, meta lead) — scoped by ORG so a card another org "
        "holds can never block this org's card (the 2026-10-10 loss of 6 real "
        "cards). Proves both halves: a second card for the same meta lead in "
        "the same org is refused (23505 on this index), and the same meta "
        "lead in a DIFFERENT org is accepted (the old global unique refused "
        "that and is reported as `blocked`)."
    ),
    sql=_do_block("""
DECLARE
  v_a     uuid := gen_random_uuid();
  v_b     uuid := gen_random_uuid();
  v_m     text := 'noc_probe_' || gen_random_uuid()::text;
  v_stage uuid;
  v_phase text := 'setup';
BEGIN
  IF to_regclass('social_wiring.uq_sw_atendimentos_org_meta_lead') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: uq_sw_atendimentos_org_meta_lead does not exist (migration 239 not applied)';
  END IF;
  BEGIN
    -- The real spawn trigger creates the first card for (v_a, v_m).
    INSERT INTO social_wiring.meta_ads_leads (id, org_id) VALUES (v_m, v_a);
    SELECT id INTO v_stage FROM social_wiring.pipeline_stages
     WHERE org_id = v_a AND pipeline = 'funil' LIMIT 1;
    IF v_stage IS NULL THEN
      RAISE EXCEPTION 'NOC_PROBE:no_fixture: spawn trigger did not provision a funil stage/card for the fabricated org';
    END IF;
    v_phase := 'cross_org';
    INSERT INTO social_wiring.atendimentos (org_id, meta_ads_lead_id, etapa_id, titulo)
    VALUES (v_b, v_m, v_stage, 'noc_probe_other_org');
    v_phase := 'same_org';
    INSERT INTO social_wiring.atendimentos (org_id, meta_ads_lead_id, etapa_id, titulo)
    VALUES (v_a, v_m, v_stage, 'noc_probe_same_org_dup');
    RAISE EXCEPTION 'NOC_PROBE:permitted: a second card for the same (org, meta lead) was accepted — the unique guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:%' THEN
      RAISE;
    ELSIF v_phase = 'same_org' AND SQLERRM LIKE '%uq_sw_atendimentos_org_meta_lead%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSIF v_phase = 'cross_org' THEN
      RAISE EXCEPTION 'NOC_PROBE:blocked: the same meta lead in a DIFFERENT org was refused (global unique?): %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error in phase %: %', v_phase, SQLERRM;
    END IF;
  END;
END;
"""),
)

_SW_240_SPAWN_NO_SILENT_DROP_PROBE = GuardProbe(
    id="social-wiring.spawn_funil_card.no_silent_drop",
    product="social-wiring",
    schema=_SW_SCHEMA,
    guard_name="spawn_funil_card",
    kind="write_allowed",
    migrations=_SW_240_MIGRATIONS,
    rationale=(
        "The same-org collision: the meta lead's card is already linked to "
        "ANOTHER lead, then a new lead claims that meta lead. The lead's card "
        "must still exist (no silent drop) and the collision must be visible "
        "as a funil_card_anomalias row. A missing card or missing anomaly is "
        "reported as `violation`. Scope: the same-org shape only — the "
        "cross-org shape is proven by the org-scoped unique probe above "
        "(the card is created because no other org's row can conflict)."
    ),
    sql=_do_block("""
DECLARE
  v_a     uuid := gen_random_uuid();
  v_m     text := 'noc_probe_' || gen_random_uuid()::text;
  v_l0    uuid := gen_random_uuid();
  v_l2    uuid := gen_random_uuid();
  v_card  uuid;
  v_n_card int;
  v_n_anom int;
  v_phase text := 'setup';
BEGIN
  IF to_regclass('social_wiring.funil_card_anomalias') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: social_wiring.funil_card_anomalias does not exist (migration 239 not applied)';
  END IF;
  BEGIN
    -- Card C1 for the meta lead (made by the real trigger), then hand it to
    -- another lead L0 so the "lead_id IS NULL" merge lookup cannot find it.
    INSERT INTO social_wiring.meta_ads_leads (id, org_id) VALUES (v_m, v_a);
    INSERT INTO social_wiring.leads (id, org_id, data_entrada) VALUES (v_l0, v_a, CURRENT_DATE);
    DELETE FROM social_wiring.atendimentos WHERE lead_id = v_l0;
    UPDATE social_wiring.atendimentos SET lead_id = v_l0
     WHERE org_id = v_a AND meta_ads_lead_id = v_m
     RETURNING id INTO v_card;
    IF v_card IS NULL THEN
      RAISE EXCEPTION 'NOC_PROBE:no_fixture: spawn trigger did not create the meta lead card for the fabricated org';
    END IF;
    v_phase := 'collision';
    INSERT INTO social_wiring.leads (id, org_id, data_entrada, meta_lead_id)
    VALUES (v_l2, v_a, CURRENT_DATE, v_m);
    SELECT count(*) INTO v_n_card FROM social_wiring.atendimentos WHERE lead_id = v_l2;
    SELECT count(*) INTO v_n_anom FROM social_wiring.funil_card_anomalias
     WHERE org_id = v_a AND lead_id = v_l2 AND atendimento_existente_id = v_card;
    IF v_n_card = 1 AND v_n_anom = 1 THEN
      RAISE EXCEPTION 'NOC_PROBE:allowed: card kept for the colliding lead and the collision recorded (cards=%, anomalias=%)', v_n_card, v_n_anom;
    END IF;
    RAISE EXCEPTION 'NOC_PROBE:violation: silent drop — cards for the lead=% (want 1), anomaly rows=% (want 1)', v_n_card, v_n_anom;
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:%' THEN
      RAISE;
    ELSIF v_phase = 'collision' THEN
      RAISE EXCEPTION 'NOC_PROBE:blocked: lead insert with a colliding meta lead was refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error in phase %: %', v_phase, SQLERRM;
    END IF;
  END;
END;
"""),
)

_SW_240_PROBES: tuple[GuardProbe, ...] = (
    _SW_240_META_UNIQUE_PROBE,
    _SW_240_SPAWN_NO_SILENT_DROP_PROBE,
)


# ---------------------------------------------------------------------------
# Registry — social_wiring Esteira de reels guards (migration 241,
# esteira-contract.md 2.6). Every probe self-provisions its own fixture (two
# marcas, a headline + roteiro on marca B, a stage) inside the probe
# transaction and rolls back; nothing is borrowed from existing rows except
# the owning org id.
# ---------------------------------------------------------------------------

_SW_241_MIGRATION = "241_cs_esteira.sql"

_SW_241_DECLARE = """
DECLARE
  v_org uuid;
  v_marca_a uuid;
  v_marca_b uuid;
  v_etapa uuid;
  v_head_b uuid;
  v_rot_b uuid;
  v_post uuid;
  v_n bigint;
  v_marca_after uuid;
  v_head_after uuid;
"""

_SW_241_FIXTURE = f"""
  SELECT id INTO v_org FROM public.organizations LIMIT 1;
  IF v_org IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no public.organizations row to own a probe marca';
  END IF;
  INSERT INTO {_SW_SCHEMA}.marcas (org_id, slug, name)
  VALUES (v_org, 'noc-probe-esteira-a', 'noc-probe-esteira-a') RETURNING id INTO v_marca_a;
  INSERT INTO {_SW_SCHEMA}.marcas (org_id, slug, name)
  VALUES (v_org, 'noc-probe-esteira-b', 'noc-probe-esteira-b') RETURNING id INTO v_marca_b;
  INSERT INTO {_SW_SCHEMA}.pipeline_stages (org_id, pipeline, slug, label, posicao)
  VALUES (v_org, 'esteira', 'noc_probe_esteira', 'noc probe', 9999) RETURNING id INTO v_etapa;
  INSERT INTO {_SW_SCHEMA}.cs_headlines (org_id, marca_id, texto)
  VALUES (v_org, v_marca_b, 'noc probe headline') RETURNING id INTO v_head_b;
  INSERT INTO {_SW_SCHEMA}.cs_roteiros (org_id, marca_id, nome, headline_texto)
  VALUES (v_org, v_marca_b, 'noc probe roteiro', 'noc probe headline') RETURNING id INTO v_rot_b;
"""


def _sw241_post_ins(marca: str = "v_marca_a", *, cols: str = "", vals: str = "", titulo: str = "'noc probe post'") -> str:
    """One `cs_posts` insert (statement text, no trailing `;`) on the fixture stage."""
    return (
        f"INSERT INTO {_SW_SCHEMA}.cs_posts (org_id, marca_id, titulo, etapa_id{cols}) "
        f"VALUES (v_org, {marca}, {titulo}, v_etapa{vals})"
    )


def _sw241_refusal_probe(
    *, probe_id: str, guard_name: str, statements: str, permitted_msg: str, rationale: str
) -> GuardProbe:
    """Refusal probe for a migration-241 guard. `statements` run in the inner block;
    the LAST one must be the refused write. Anything other than the named guard's
    error is `ambiguous`, never a silent pass."""
    return GuardProbe(
        id=probe_id,
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name=guard_name,
        kind="write_refusal",
        migrations=(_SW_241_MIGRATION,),
        rationale=rationale,
        sql=_do_block(f"""
{_SW_241_DECLARE}
BEGIN
{_SW_241_FIXTURE}
  BEGIN
{statements}
    RAISE EXCEPTION 'NOC_PROBE:permitted: {_sql_lit(permitted_msg)} - the guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{guard_name}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
    )


def _sw241_stmt(sql: str) -> str:
    return f"    {sql};"


_SW_241_PROBES: tuple[GuardProbe, ...] = (
    _sw241_refusal_probe(
        probe_id="sw241_post_headline_outra_marca",
        guard_name="cs_posts_headline_marca_fk",
        statements=_sw241_stmt(_sw241_post_ins("v_marca_a", cols=", headline_id", vals=", v_head_b")),
        permitted_msg="post on marca A bound to a headline of marca B",
        rationale="The post->headline FK is composite on (id, marca_id): a post can never bind another marca's headline, even through a service-role bug.",
    ),
    _sw241_refusal_probe(
        probe_id="sw241_post_roteiro_outra_marca",
        guard_name="cs_posts_roteiro_marca_fk",
        statements=_sw241_stmt(_sw241_post_ins("v_marca_a", cols=", roteiro_id", vals=", v_rot_b")),
        permitted_msg="post on marca A bound to a roteiro of marca B",
        rationale="The post->roteiro FK is composite on (id, marca_id): a post can never bind another marca's roteiro.",
    ),
    _sw241_refusal_probe(
        probe_id="sw241_headline_unico_por_post",
        guard_name="cs_posts_headline_uq",
        statements=(
            _sw241_stmt(_sw241_post_ins("v_marca_b", cols=", headline_id", vals=", v_head_b"))
            + "\n"
            + _sw241_stmt(_sw241_post_ins("v_marca_b", cols=", headline_id", vals=", v_head_b", titulo="'noc probe post 2'"))
        ),
        permitted_msg="second post bound to the same headline",
        rationale="A headline belongs to at most one post.",
    ),
    _sw241_refusal_probe(
        probe_id="sw241_roteiro_unico_por_post",
        guard_name="cs_posts_roteiro_uq",
        statements=(
            _sw241_stmt(_sw241_post_ins("v_marca_b", cols=", roteiro_id", vals=", v_rot_b"))
            + "\n"
            + _sw241_stmt(_sw241_post_ins("v_marca_b", cols=", roteiro_id", vals=", v_rot_b", titulo="'noc probe post 2'"))
        ),
        permitted_msg="second post bound to the same roteiro",
        rationale="A roteiro belongs to at most one post.",
    ),
    _sw241_refusal_probe(
        probe_id="sw241_post_formato",
        guard_name="cs_posts_formato_check",
        statements=_sw241_stmt(_sw241_post_ins(cols=", formato", vals=", 'story'")),
        permitted_msg="post with formato=story",
        rationale="v1 of the Esteira is reels only; a new format is a deliberate migration, not a free-text value.",
    ),
    _sw241_refusal_probe(
        probe_id="sw241_post_titulo_vazio",
        guard_name="cs_posts_titulo_check",
        statements=_sw241_stmt(_sw241_post_ins(titulo="'  '")),
        permitted_msg="post with a blank titulo",
        rationale="A post needs a trimmed, non-empty working title (1..200).",
    ),
    _sw241_refusal_probe(
        probe_id="sw241_post_hashtags_max",
        guard_name="cs_posts_hashtags_max",
        statements=_sw241_stmt(
            _sw241_post_ins(cols=", hashtags", vals=", ARRAY(SELECT 'h' || g FROM generate_series(1, 31) g)")
        ),
        permitted_msg="post with 31 hashtags",
        rationale="Instagram allows at most 30 hashtags; the database refuses the 31st.",
    ),
    _sw241_refusal_probe(
        probe_id="sw241_post_permalink",
        guard_name="cs_posts_permalink_check",
        statements=_sw241_stmt(_sw241_post_ins(cols=", permalink", vals=", 'http://evil'")),
        permitted_msg="post with a non-instagram http permalink",
        rationale="The permalink is rendered as a link: https instagram.com only (no SSRF / open-redirect surface).",
    ),
    GuardProbe(
        id="sw241_stage_esteira_ok",
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name="pipeline_stages_papel_check",
        kind="write_allowed",
        migrations=(_SW_241_MIGRATION,),
        rationale=(
            "The widened pipeline/papel CHECKs must accept the Esteira board: a stage with "
            "pipeline='esteira' and papel='postado' (a fabricated org, so no real board collides)."
        ),
        sql=_do_block(f"""
BEGIN
  -- no_fixture: none needed (a fabricated org id owns the stage; nothing real is borrowed)
  BEGIN
    INSERT INTO {_SW_SCHEMA}.pipeline_stages (org_id, pipeline, slug, label, posicao, papel)
    VALUES (gen_random_uuid(), 'esteira', 'noc_probe_postado', 'noc probe', 0, 'postado');
    RAISE EXCEPTION 'NOC_PROBE:allowed: esteira/postado stage insert succeeded - the widened CHECKs accept the board';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:allowed:%' THEN
      RAISE;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:blocked: esteira/postado stage insert was refused: %', SQLERRM;
    END IF;
  END;
END;
"""),
    ),
    GuardProbe(
        id="sw241_stage_pipeline_invalido",
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name="pipeline_stages_pipeline_check",
        kind="write_refusal",
        migrations=(_SW_241_MIGRATION,),
        rationale="Widening the pipeline CHECK must not open it: an unknown pipeline key is still refused.",
        sql=_do_block(f"""
BEGIN
  -- no_fixture: none needed (a fabricated org id owns the stage; nothing real is borrowed)
  BEGIN
    INSERT INTO {_SW_SCHEMA}.pipeline_stages (org_id, pipeline, slug, label, posicao)
    VALUES (gen_random_uuid(), 'xyz', 'noc_probe_xyz', 'noc probe', 0);
    RAISE EXCEPTION 'NOC_PROBE:permitted: stage with pipeline=xyz inserted - the guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%pipeline_stages_pipeline_check%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
    ),
    GuardProbe(
        id="sw241_equipe_nome_unico",
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name="cs_equipe_nome_uq",
        kind="write_refusal",
        migrations=(_SW_241_MIGRATION,),
        rationale="One team member per (org, lower(nome)): a case-variant re-add is refused, never a second person.",
        sql=_do_block(f"""
DECLARE
  v_org uuid;
BEGIN
  SELECT id INTO v_org FROM public.organizations LIMIT 1;
  IF v_org IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no public.organizations row to own a probe team member';
  END IF;
  BEGIN
    INSERT INTO {_SW_SCHEMA}.cs_equipe (org_id, nome) VALUES (v_org, 'noc probe equipe');
    INSERT INTO {_SW_SCHEMA}.cs_equipe (org_id, nome) VALUES (v_org, 'NOC PROBE EQUIPE');
    RAISE EXCEPTION 'NOC_PROBE:permitted: case-variant duplicate team member inserted - the guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%cs_equipe_nome_uq%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
    ),
    GuardProbe(
        id="sw241_headline_delete_nulls_only_fk",
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name="cs_posts_headline_marca_fk",
        kind="state_assertion",
        migrations=(_SW_241_MIGRATION,),
        rationale=(
            "Deleting a bound headline must null ONLY cs_posts.headline_id (column-list SET NULL): "
            "marca_id is NOT NULL, so a plain SET NULL would make the delete fail or orphan the post."
        ),
        sql=_do_block(f"""
{_SW_241_DECLARE}
BEGIN
{_SW_241_FIXTURE}
  {_sw241_post_ins("v_marca_b", cols=", headline_id", vals=", v_head_b")} RETURNING id INTO v_post;
  BEGIN
    DELETE FROM {_SW_SCHEMA}.cs_headlines WHERE id = v_head_b;
  EXCEPTION WHEN OTHERS THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: deleting a bound headline failed instead of nulling the FK: %', SQLERRM;
  END;
  SELECT marca_id, headline_id INTO v_marca_after, v_head_after
    FROM {_SW_SCHEMA}.cs_posts WHERE id = v_post;
  IF v_marca_after IS DISTINCT FROM v_marca_b OR v_head_after IS NOT NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:violation: after the headline delete marca_id=% headline_id=% (want marca intact, headline NULL)', v_marca_after, v_head_after;
  END IF;
  RAISE EXCEPTION 'NOC_PROBE:clean: headline delete nulled headline_id and left marca_id intact';
END;
"""),
    ),
    GuardProbe(
        id="sw241_status_pagina",
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name="status_pagina_241",
        kind="state_assertion",
        migrations=(_SW_241_MIGRATION,),
        rationale=(
            "The nav rows 241 owns: branding/carrosseis are producao and the Esteira is desenvolvimento "
            "-- or producao once the owner promotes it (a promotion must not turn this probe red)."
        ),
        sql=_state_assertion_probe(
            select_count_sql=(
                f"SELECT (SELECT count(*) FROM (VALUES ('media-creation-branding'), ('media-creation-carrosseis')) AS e(n) "
                f"WHERE NOT EXISTS (SELECT 1 FROM {_SW_SCHEMA}.status_pagina p WHERE p.nome_pagina = e.n AND p.status = 'producao')) "
                f"+ (SELECT CASE WHEN EXISTS (SELECT 1 FROM {_SW_SCHEMA}.status_pagina WHERE nome_pagina = 'media-creation-esteira' "
                f"AND status IN ('desenvolvimento', 'producao')) THEN 0 ELSE 1 END) "
                "INTO v_count;"
            ),
            clean_message="status_pagina rows match migration 241",
            violation_message_prefix="status_pagina rows diverge from migration 241:",
        ),
    ),
    # --- remaining declared guards of 241 (the migration-guard-has-probe keeper wants every one) ---
    _sw241_refusal_probe(
        probe_id="sw241_movimento_pipeline_invalido",
        guard_name="pipeline_movimentos_pipeline_check",
        statements=_sw241_stmt(
            f"INSERT INTO {_SW_SCHEMA}.pipeline_movimentos (org_id, pipeline, entidade_id, para_etapa_id, responsavel_id) "
            "VALUES (v_org, 'xyz', gen_random_uuid(), v_etapa, gen_random_uuid())"
        ),
        permitted_msg="stage move recorded for pipeline=xyz",
        rationale="Widening the history table's pipeline CHECK for 'esteira' must not open it: an unknown pipeline key is still refused.",
    ),
    _sw241_refusal_probe(
        probe_id="sw241_post_legenda_max",
        guard_name="cs_posts_legenda_check",
        statements=_sw241_stmt(_sw241_post_ins(cols=", legenda", vals=", repeat('x', 2201)")),
        permitted_msg="post with a 2201-char legenda",
        rationale="Instagram captions are capped at 2 200 characters.",
    ),
    _sw241_refusal_probe(
        probe_id="sw241_post_primeiro_comentario_max",
        guard_name="cs_posts_primeiro_comentario_check",
        statements=_sw241_stmt(_sw241_post_ins(cols=", primeiro_comentario", vals=", repeat('x', 2201)")),
        permitted_msg="post with a 2201-char primeiro_comentario",
        rationale="The first comment is an Instagram comment: capped at 2 200 characters.",
    ),
    _sw241_refusal_probe(
        probe_id="sw241_post_links_producao_array",
        guard_name="cs_posts_links_producao_check",
        statements=_sw241_stmt(_sw241_post_ins(cols=", links_producao", vals=", '{}'::jsonb")),
        permitted_msg="post whose links_producao is a JSON object",
        rationale="links_producao is a list of {rotulo, url}; a non-array would break every reader.",
    ),
    _sw241_refusal_probe(
        probe_id="sw241_post_motivo_bloqueio_max",
        guard_name="cs_posts_motivo_bloqueio_check",
        statements=_sw241_stmt(_sw241_post_ins(cols=", motivo_bloqueio", vals=", repeat('x', 1001)")),
        permitted_msg="post with a 1001-char motivo_bloqueio",
        rationale="The block/cancel reason is capped at 1 000 characters.",
    ),
    _sw241_refusal_probe(
        probe_id="sw241_post_nota_descricao_unica",
        guard_name="uq_cs_post_notas_one_descricao",
        statements=(
            _sw241_stmt(_sw241_post_ins("v_marca_a") + " RETURNING id INTO v_post")
            + "\n"
            + _sw241_stmt(
                f"INSERT INTO {_SW_SCHEMA}.cs_post_notas (org_id, post_id, tipo, corpo) "
                "VALUES (v_org, v_post, 'descricao', 'noc probe a')"
            )
            + "\n"
            + _sw241_stmt(
                f"INSERT INTO {_SW_SCHEMA}.cs_post_notas (org_id, post_id, tipo, corpo) "
                "VALUES (v_org, v_post, 'descricao', 'noc probe b')"
            )
        ),
        permitted_msg="second live descricao note on one post",
        rationale="One live `descricao` note per post: the card has a single description.",
    ),
    _sw241_refusal_probe(
        probe_id="sw241_post_tag_nome_unico",
        guard_name="uq_cs_post_tags_org_nome",
        statements=(
            _sw241_stmt(f"INSERT INTO {_SW_SCHEMA}.cs_post_tags (org_id, nome, cor) VALUES (v_org, 'noc probe tag', '#aabbcc')")
            + "\n"
            + _sw241_stmt(f"INSERT INTO {_SW_SCHEMA}.cs_post_tags (org_id, nome, cor) VALUES (v_org, 'NOC PROBE TAG', '#aabbcc')")
        ),
        permitted_msg="case-variant duplicate post tag",
        rationale="One label per (org, lower(nome)): a case-variant re-add is refused, never a second tag.",
    ),
)


# ---------------------------------------------------------------------------
# Registry -- commerce.commerce_coupons guards (commerce 012, generated by the
# commerce organ). Self-contained: a coupon needs only a fresh org_id, no fixture row.
# ---------------------------------------------------------------------------

_COMMERCE_SCHEMA = "commerce"


def _commerce_coupon_probe(*, probe_id: str, guard_name: str, kind: str, rationale: str, rows_sql: str, permitted: str) -> GuardProbe:
    return GuardProbe(
        id=probe_id,
        product="commerce",
        schema=_COMMERCE_SCHEMA,
        guard_name=guard_name,
        kind="write_refusal",
        migrations=("012_commerce.sql",),
        rationale=rationale,
        sql=_do_block(f"""
DECLARE
  v_org uuid := gen_random_uuid();
BEGIN
  IF to_regclass('{_COMMERCE_SCHEMA}.commerce_coupons') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: {_COMMERCE_SCHEMA}.commerce_coupons does not exist (commerce 012 not applied)';
  END IF;
  BEGIN
    {rows_sql}
    RAISE EXCEPTION 'NOC_PROBE:permitted: {permitted} -- the {kind} guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{guard_name}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
    )


_COMMERCE_COUPON_PERCENT_PROBE = _commerce_coupon_probe(
    probe_id="commerce_coupons.percent_range",
    guard_name="commerce_coupons_percent_range",
    kind="check",
    rationale=(
        "A percent coupon above 100 would price an order below zero; the quote recomputes "
        "server-side, but the table must still refuse the row."
    ),
    rows_sql=f"INSERT INTO {_COMMERCE_SCHEMA}.commerce_coupons (org_id, code, kind, value) VALUES (v_org, 'PROBE', 'percent', 101);",
    permitted="a 101 percent coupon insert succeeded"  # no bare % -- it is a RAISE placeholder,
)

_COMMERCE_COUPON_CODE_UNIQUE_PROBE = _commerce_coupon_probe(
    probe_id="commerce_coupons.code.unique_per_org",
    guard_name="uq_commerce_coupons_org_code",
    kind="unique",
    rationale=(
        "Coupon codes are unique per org, case-insensitively: two 'PROMO'/'promo' rows would "
        "make the redeemed discount depend on read order."
    ),
    rows_sql=(
        f"INSERT INTO {_COMMERCE_SCHEMA}.commerce_coupons (org_id, code, kind, value) VALUES (v_org, 'PROMO', 'fixed', 100);\n"
        f"    INSERT INTO {_COMMERCE_SCHEMA}.commerce_coupons (org_id, code, kind, value) VALUES (v_org, 'promo', 'fixed', 100);"
    ),
    permitted="a case-variant duplicate coupon code insert succeeded",
)


# ---------------------------------------------------------------------------
# Orbity migration 018 (automation live) -- idempotency key, subject CHECKs,
# claim status vocabulary, WhatsApp connection webhook token uniqueness.
# Each probe provisions its own flow/step/execution specimen inside the
# rollback-only wrapper (nothing persists).
# ---------------------------------------------------------------------------

_ORBITY_SCHEMA = "orbity"

_ORBITY_FLOW_FIXTURE = (
    f"INSERT INTO {_ORBITY_SCHEMA}.automation_flows (id, org_id, name, trigger_type) "
    "VALUES (v_flow, v_org, 'noc_probe', 'task_created');"
)


def _orbity_018_probe(*, probe_id: str, guard_name: str, kind: str, rationale: str, setup_sql: str, rows_sql: str, permitted: str, table: str) -> GuardProbe:
    return GuardProbe(
        id=probe_id,
        product="orbity",
        schema=_ORBITY_SCHEMA,
        guard_name=guard_name,
        kind="write_refusal",
        migrations=("018_automation_live.sql",),
        rationale=rationale,
        sql=_do_block(f"""
DECLARE
  v_org uuid := gen_random_uuid();
  v_flow uuid := gen_random_uuid();
  v_step uuid := gen_random_uuid();
  v_exec uuid := gen_random_uuid();
BEGIN
  IF to_regclass('{_ORBITY_SCHEMA}.{table}') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: {_ORBITY_SCHEMA}.{table} does not exist (orbity 018 not applied)';
  END IF;
  {setup_sql}
  BEGIN
    {rows_sql}
    RAISE EXCEPTION 'NOC_PROBE:permitted: {permitted} -- the {kind} guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{guard_name}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
    )


_ORBITY_EXEC_INS = (
    f"INSERT INTO {_ORBITY_SCHEMA}.automation_executions (org_id, flow_id, subject_type, subject_id{{extra_cols}}) "
    "VALUES (v_org, v_flow, {subject_type}, {subject_id}{extra_vals});"
)

_ORBITY_018_PROBES: tuple[GuardProbe, ...] = (
    _orbity_018_probe(
        probe_id="orbity.whatsapp_connections.webhook_token_unique",
        guard_name="idx_orbity_whatsapp_connections_webhook_token",
        kind="unique",
        table="whatsapp_connections",
        rationale="The webhook token routes an unauthenticated inbound call to an org; two connections sharing one would cross-deliver messages between orgs.",
        setup_sql="",
        rows_sql=(
            f"INSERT INTO {_ORBITY_SCHEMA}.whatsapp_connections (org_id, user_id, label, base_url, encrypted_api_key, webhook_token) "
            "VALUES (v_org, gen_random_uuid(), 'a', 'http://x', 'k', 'noc_probe_tok');\n"
            f"    INSERT INTO {_ORBITY_SCHEMA}.whatsapp_connections (org_id, user_id, label, base_url, encrypted_api_key, webhook_token) "
            "VALUES (v_org, gen_random_uuid(), 'b', 'http://x', 'k', 'noc_probe_tok');"
        ),
        permitted="two connections with the same webhook_token were inserted",
    ),
    _orbity_018_probe(
        probe_id="orbity.automation_executions.subject_type_vocab",
        guard_name="automation_executions_subject_type_check",
        kind="check",
        table="automation_executions",
        rationale="subject_type selects how the engine loads the run's contact; an unknown value would resolve to no subject.",
        setup_sql=_ORBITY_FLOW_FIXTURE,
        rows_sql=_ORBITY_EXEC_INS.format(extra_cols="", extra_vals="", subject_type="'noc_probe_bogus'", subject_id="gen_random_uuid()"),
        permitted="an execution with an out-of-vocabulary subject_type was inserted",
    ),
    _orbity_018_probe(
        probe_id="orbity.automation_executions.one_resolvable_subject",
        guard_name="automation_executions_subject_check",
        kind="check",
        table="automation_executions",
        rationale="Every run needs a resolvable subject: a non-lead run without subject_id (or a lead run without lead_id) can never load its contact and would orphan.",
        setup_sql=_ORBITY_FLOW_FIXTURE,
        rows_sql=_ORBITY_EXEC_INS.format(extra_cols="", extra_vals="", subject_type="'task'", subject_id="NULL"),
        permitted="a task-subject execution without subject_id was inserted",
    ),
    _orbity_018_probe(
        probe_id="orbity.automation_executions.trigger_key_unique_per_flow",
        guard_name="automation_executions_flow_trigger_key_ux",
        kind="unique",
        table="automation_executions",
        rationale="The per-occurrence key is the idempotency guarantee: a re-delivered event must never start the same flow twice (a client would get the message twice).",
        setup_sql=_ORBITY_FLOW_FIXTURE,
        rows_sql=(
            _ORBITY_EXEC_INS.format(extra_cols=", trigger_key", extra_vals=", 'noc_probe_key'", subject_type="'task'", subject_id="gen_random_uuid()")
            + "\n    "
            + _ORBITY_EXEC_INS.format(extra_cols=", trigger_key", extra_vals=", 'noc_probe_key'", subject_type="'task'", subject_id="gen_random_uuid()")
        ),
        permitted="a second execution with the same (flow_id, trigger_key) was inserted",
    ),
    _orbity_018_probe(
        probe_id="orbity.automation_pending_actions.status_vocab",
        guard_name="automation_pending_actions_status_check",
        kind="check",
        table="automation_pending_actions",
        rationale="The drain's claim protocol depends on the closed status vocabulary (pending/processing/sent/skipped/failed); an unknown status would never be picked up nor recovered.",
        setup_sql=(
            _ORBITY_FLOW_FIXTURE
            + f"\n  INSERT INTO {_ORBITY_SCHEMA}.automation_steps (id, org_id, flow_id, ord, step_type) VALUES (v_step, v_org, v_flow, 0, 'end');"
            + "\n  " + _ORBITY_EXEC_INS.format(extra_cols="", extra_vals="", subject_type="'task'", subject_id="gen_random_uuid()").replace("(org_id, flow_id,", "(id, org_id, flow_id,").replace("VALUES (v_org,", "VALUES (v_exec, v_org,")
        ),
        rows_sql=(
            f"INSERT INTO {_ORBITY_SCHEMA}.automation_pending_actions (org_id, execution_id, step_id, scheduled_for, status) "
            "VALUES (v_org, v_exec, v_step, now(), 'noc_probe_bogus');"
        ),
        permitted="a pending action with an out-of-vocabulary status was inserted",
    ),
)


# ---------------------------------------------------------------------------
# Monica migration 015 (WhatsApp connections + inbox) -- the webhook token is the routing credential of the
# PUBLIC inbound webhook: two connections sharing one would cross-deliver messages between orgs.
# ---------------------------------------------------------------------------

_MONICA_SCHEMA = "monica"

_MONICA_WA_WEBHOOK_TOKEN_UNIQUE_PROBE = GuardProbe(
    id="monica.whatsapp_connections.webhook_token_unique",
    product="monica",
    schema=_MONICA_SCHEMA,
    guard_name="idx_monica_whatsapp_connections_webhook_token",
    kind="write_refusal",
    migrations=("015_whatsapp.sql",),
    rationale="The webhook token routes an unauthenticated inbound call to an org; two connections sharing one would cross-deliver conversations between orgs.",
    sql=_do_block(f"""
DECLARE
  v_org uuid := gen_random_uuid();
BEGIN
  IF to_regclass('{_MONICA_SCHEMA}.whatsapp_connections') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: {_MONICA_SCHEMA}.whatsapp_connections does not exist (monica 015 not applied)';
  END IF;
  BEGIN
    INSERT INTO {_MONICA_SCHEMA}.whatsapp_connections (org_id, user_id, label, base_url, encrypted_api_key, webhook_token)
    VALUES (v_org, gen_random_uuid(), 'a', 'http://x', 'k', 'noc_probe_tok');
    INSERT INTO {_MONICA_SCHEMA}.whatsapp_connections (org_id, user_id, label, base_url, encrypted_api_key, webhook_token)
    VALUES (v_org, gen_random_uuid(), 'b', 'http://x', 'k', 'noc_probe_tok');
    RAISE EXCEPTION 'NOC_PROBE:permitted: two connections with the same webhook_token were inserted -- the unique guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%idx_monica_whatsapp_connections_webhook_token%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
)


_M_JULIA_ENVIO = "270_lais_envio.sql"
_T_JULIA_ENVIO = (
    f"{_S}.julia_contatos", f"{_S}.julia_envio_regras", f"{_S}.julia_envio_politicas", f"{_S}.julia_envio_entregas",
)


def _envio_probe(probe_id: str, guard: str, rationale: str, ops_sql: str, cond: str, what: str) -> GuardProbe:
    return _sw_junction_probe(
        probe_id=f"julia_envio.{probe_id}", guard_name=guard, migration=_M_JULIA_ENVIO, rationale=rationale,
        fixtures=("registry",), ops_sql=ops_sql, sqlstate_condition=cond, what=what, tabelas=_T_JULIA_ENVIO,
    )


def _envio_regra_ins(cols: str = "operacao", vals: str = "'compra'") -> str:
    return f"    INSERT INTO {_S}.julia_envio_regras (org_id, {cols})\n    VALUES (v_org, {vals});"


def _envio_entrega_ins(gatilho: str = "'manual'", status: str = "'ok'", erro: str = "NULL") -> str:
    return _julia_contato_ins() + "\n" + _julia_child_ins("julia_envio_entregas", "gatilho, status, erro", f"{gatilho}, {status}, {erro}")


#: Migration 270 -- Julia wave 3 (envio ao SW). Unapplied guards read `no_fixture`, `refused` once applied.
_SW_JULIA_ENVIO_PROBES: tuple[GuardProbe, ...] = (
    _envio_probe(
        "regras.operacao_valida", "julia_envio_regras_operacao_valida",
        "The rule is looked up by the contato's operacao; an unknown value would never match any contato.",
        _envio_regra_ins("operacao", "'noc_probe_bogus'"), _CHECK, "a send rule for an unknown operacao",
    ),
    _envio_probe(
        "regras.grupos_array", "julia_envio_regras_grupos_array",
        "The evaluator iterates groups of criteria; an object/scalar would crash every qualification.",
        _envio_regra_ins("operacao, grupos", "'compra', '{}'::jsonb"), _CHECK, "a send rule whose grupos is not a JSON array",
    ),
    _envio_probe(
        "regras.operacao_unica", "julia_envio_regras_operacao_uq",
        "Two rules for the same (org, operacao) would make the send decision depend on row order.",
        _envio_regra_ins() + "\n" + _envio_regra_ins(), _UNIQ, "two send rules for the same operacao",
    ),
    _envio_probe(
        "politicas.frios_objeto", "julia_envio_politicas_frios_objeto",
        "The cold-lead policy is read as a mapping (ativo / modo / intervalo); a scalar would crash the timer.",
        f"    INSERT INTO {_S}.julia_envio_politicas (org_id, frios)\n    VALUES (v_org, '[]'::jsonb);",
        _CHECK, "a cold-lead policy that is not a JSON object",
    ),
    _envio_probe(
        "politicas.captacoes_valida", "julia_envio_politicas_captacoes_valida",
        "The captacao policy is enviar|notificar; anything else would silently behave as one of the two.",
        f"    INSERT INTO {_S}.julia_envio_politicas (org_id, captacoes)\n    VALUES (v_org, 'noc_probe_bogus');",
        _CHECK, "a captacao policy outside enviar|notificar",
    ),
    _envio_probe(
        "entregas.gatilho_valido", "julia_envio_entregas_gatilho_valido",
        "The delivery ledger is grouped by trigger in the Leads list; a free-text trigger escapes the vocabulary.",
        _envio_entrega_ins("'noc_probe_bogus'"), _CHECK, "a delivery with an unknown gatilho",
    ),
    _envio_probe(
        "entregas.status_valido", "julia_envio_entregas_status_valido",
        "A delivery is ok or erro; any other status is neither a success nor a retryable failure.",
        _envio_entrega_ins(status="'noc_probe_bogus'", erro="'x'"), _CHECK, "a delivery with an unknown status",
    ),
    _envio_probe(
        "entregas.erro_exige_mensagem", "julia_envio_entregas_erro_exige_mensagem",
        "A failed delivery without its error text cannot be diagnosed from the Leads list.",
        _envio_entrega_ins(status="'erro'"), _CHECK, "an erro delivery with no erro text",
    ),
)



_M_JULIA_CAPT = "278_lais_captacoes.sql"
_T_JULIA_CAPT = (f"{_S}.julia_contatos", f"{_S}.julia_captacoes")


def _capt_probe(probe_id: str, guard: str, rationale: str, ops_sql: str, cond: str, what: str) -> GuardProbe:
    return _sw_junction_probe(
        probe_id=f"julia_captacao.{probe_id}", guard_name=guard, migration=_M_JULIA_CAPT, rationale=rationale,
        fixtures=("registry",), ops_sql=ops_sql, sqlstate_condition=cond, what=what, tabelas=_T_JULIA_CAPT,
    )


def _capt_ins(cols: str = "status", vals: str = "'nova'") -> str:
    return _julia_contato_ins() + "\n" + _julia_child_ins("julia_captacoes", cols, vals)


#: Migration 278 -- Julia wave 8 (captacao). Unapplied guards read `no_fixture`, `refused` once applied.
_SW_JULIA_CAPTACAO_PROBES: tuple[GuardProbe, ...] = (
    _capt_probe(
        "status_valido", "julia_captacoes_status_valido",
        "The status drives which feed actions exist (registrar/descartar only on `nova`); free text escapes it.",
        _capt_ins("status", "'noc_probe_bogus'"), _CHECK, "a julia_captacao with an unknown status",
    ),
    _capt_probe(
        "operacao_valida", "julia_captacoes_operacao_valida",
        "The operacao prefills the imovel finalidades (venda|aluguel); any other token would fail the imovel write later.",
        _capt_ins("operacao", "'noc_probe_bogus'"), _CHECK, "a julia_captacao with an unknown operacao",
    ),
    _capt_probe(
        "registrada_exige_imovel", "julia_captacoes_registrada_exige_imovel",
        "A registrada capture must name the imovel it produced; otherwise the feed links to nothing.",
        _capt_ins("status", "'registrada'"), _CHECK, "a registrada julia_captacao with no imovel_id",
    ),
)


_M_JULIA_CRED = "281_lais_credito.sql"
_T_JULIA_CRED = (
    f"{_S}.julia_contatos", f"{_S}.julia_credito_config", f"{_S}.julia_credito_consentimentos", f"{_S}.julia_credito_analises",
)
_FK = "foreign_key_violation"


def _cred_probe(probe_id: str, guard: str, rationale: str, ops_sql: str, cond: str, what: str) -> GuardProbe:
    return _sw_junction_probe(
        probe_id=f"julia_credito.{probe_id}", guard_name=guard, migration=_M_JULIA_CRED, rationale=rationale,
        fixtures=("registry",), ops_sql=ops_sql, sqlstate_condition=cond, what=what, tabelas=_T_JULIA_CRED,
    )


def _cred_consent_ins(aceito: str = "true", versao: str = "'v1'") -> str:
    return _julia_contato_ins() + "\n" + _julia_child_ins("julia_credito_consentimentos", "aceito, texto_versao", f"{aceito}, {versao}")


def _cred_analise_ins(consent_aceito: str, cols: str = "", vals: str = "") -> str:
    """A probe contato + a consent row (aceito per arg) + an analysis pointing at it (all rolled back)."""
    extra_c = f", {cols}" if cols else ""
    extra_v = f", {vals}" if vals else ""
    return (
        _cred_consent_ins(consent_aceito)
        + f"\n    INSERT INTO {_S}.julia_credito_analises (org_id, contato_id, consentimento_id, provider{extra_c})\n"
        f"    SELECT org_id, contato_id, id, 'noc_probe'{extra_v} FROM {_S}.julia_credito_consentimentos\n"
        "    WHERE org_id = v_org;"
    )


def _cred_config_ins(cols: str, vals: str) -> str:
    return f"    INSERT INTO {_S}.julia_credito_config (org_id, {cols}) VALUES (v_org, {vals});"


#: Migration 281 -- Julia wave 13 (analise de credito). Unapplied guards read `no_fixture`, `refused` once applied.
_SW_JULIA_CREDITO_PROBES: tuple[GuardProbe, ...] = (
    _cred_probe(
        "config_provider_valido", "julia_credito_config_provider_valido",
        "The provider names a factory entry; free text would silently select nothing.",
        _cred_config_ins("provider", "'Not A Token!'"), _CHECK, "a julia_credito_config with a malformed provider",
    ),
    _cred_probe(
        "config_ativo_exige_provider", "julia_credito_config_ativo_exige_provider",
        "An org cannot switch the analysis on with no provider chosen: every run would die at the factory.",
        _cred_config_ins("ativo", "true"), _CHECK, "an active julia_credito_config with no provider",
    ),
    _cred_probe(
        "consent_texto_versao", "julia_credito_consentimentos_texto_versao_nao_vazia",
        "A consent must name the wording the lead agreed to (LGPD evidence); a blank version proves nothing.",
        _cred_consent_ins("true", "'  '"), _CHECK, "a credit consent with a blank texto_versao",
    ),
    _cred_probe(
        "analise_status_valido", "julia_credito_analises_status_valido",
        "The status drives the Interacoes badge and the reprocess rule; free text escapes both.",
        _cred_analise_ins("true", "status", "'noc_probe_bogus'"), _CHECK, "a credit analysis with an unknown status",
    ),
    _cred_probe(
        "analise_consentimento_aceito", "julia_credito_analises_consentimento_aceito",
        "An analysis row asserts it rests on an ACCEPTED consent (contract 17); false is never a valid state.",
        _cred_analise_ins("true", "consentimento_aceito", "false"), _CHECK, "a credit analysis flagged as resting on a refused consent",
    ),
    _cred_probe(
        "analise_consentimento_fk", "julia_credito_analises_consentimento_fk",
        "No financial query may exist behind a REFUSED consent: the composite FK only resolves to aceito = true rows.",
        _cred_analise_ins("false"), _FK, "a credit analysis pointing at a refused consent",
    ),
)


_M_JULIA_STAFF_PROT = "298_julia_staff_protecao_bloqueio.sql"
_T_JULIA_STAFF_PROT = (f"{_S}.julia_staff", f"{_S}.julia_numeros_bloqueados")


def _staff_prot_probe(probe_id: str, guard: str, rationale: str, ops_sql: str, cond: str, what: str) -> GuardProbe:
    return _sw_junction_probe(
        probe_id=f"julia_staff_protecao.{probe_id}", guard_name=guard, migration=_M_JULIA_STAFF_PROT, rationale=rationale,
        fixtures=("registry",), ops_sql=ops_sql, sqlstate_condition=cond, what=what, tabelas=_T_JULIA_STAFF_PROT,
    )


def _staff_ins(cols: str = "", vals: str = "") -> str:
    extra_c = f", {cols}" if cols else ""
    extra_v = f", {vals}" if vals else ""
    return f"    INSERT INTO {_S}.julia_staff (org_id, nome, papel{extra_c})\n    VALUES (v_org, 'noc_probe', 'operador'{extra_v});"


def _bloq_ins(cols: str, vals: str, numero: str = "'5511999990000'") -> str:
    return (
        f"    INSERT INTO {_S}.julia_numeros_bloqueados (org_id, numero, motivo, {cols})\n"
        f"    VALUES (v_org, {numero}, 'noc_probe', {vals});"
    )


#: Migration 298 -- Julia on a public number: org staff list + blocklist. Unapplied guards read `no_fixture`, `refused` once applied.
_SW_JULIA_STAFF_PROT_PROBES: tuple[GuardProbe, ...] = (
    _staff_prot_probe(
        "staff_identificavel", "julia_staff_identificavel",
        "A staff entry with neither a number nor a user identifies no one: it could never match an inbound nor author a human line.",
        _staff_ins(), _CHECK, "a julia_staff row with neither telefone nor user_id",
    ),
    _staff_prot_probe(
        "staff_telefone_unico", "julia_staff_org_telefone_uk",
        "One staff row per WhatsApp number per org: two rows would give one sender two roles.",
        _staff_ins("telefone", "'5511999990000'") + "\n" + _staff_ins("telefone", "'5511999990000'"), _UNIQ,
        "two julia_staff rows for the same (org, telefone)",
    ),
    _staff_prot_probe(
        "bloqueio_auto_expira", "julia_numeros_bloqueados_auto_expira",
        "An automatic block is always TEMPORARY; one with no expiry would lock a number out forever with nobody having decided it.",
        _bloq_ins("origem, gatilho, expira_em", "'automatico', 'limite_taxa', NULL"), _CHECK,
        "an automatic block with no expira_em",
    ),
    _staff_prot_probe(
        "bloqueio_origem_gatilho", "julia_numeros_bloqueados_origem_gatilho",
        "A manual block is by a user (gatilho manual) and an automatic one has a trigger: the mix would misreport why a number is blocked.",
        _bloq_ins("origem, gatilho", "'manual', 'limite_taxa'"), _CHECK, "a manual block carrying an automatic trigger",
    ),
    _staff_prot_probe(
        "bloqueio_desbloqueio", "julia_numeros_bloqueados_desbloqueio",
        "A lifted block must record when it was lifted: the rows are the audit history.",
        _bloq_ins("origem, ativo", "'manual', false"), _CHECK, "an inactive block with no desbloqueado_em",
    ),
    _staff_prot_probe(
        "bloqueio_ativo_unico", "julia_numeros_bloqueados_ativo_uk",
        "One ACTIVE block per number per org: a duplicate would make the unblock leave the number blocked.",
        _bloq_ins("origem, ativo", "'manual', true") + "\n" + _bloq_ins("origem, ativo", "'manual', true"), _UNIQ, "two active blocks for the same (org, numero)",
    ),
)


_M_JULIA_AVAL = "280_lais_avaliacoes_capi.sql"
_T_JULIA_AVAL = (
    f"{_S}.julia_contatos", f"{_S}.julia_avaliacao_config", f"{_S}.julia_avaliacao_pedidos",
    f"{_S}.julia_avaliacoes_cache", f"{_S}.julia_capi_eventos",
)


def _aval_probe(probe_id: str, guard: str, rationale: str, ops_sql: str, cond: str, what: str) -> GuardProbe:
    return _sw_junction_probe(
        probe_id=f"julia_avaliacoes.{probe_id}", guard_name=guard, migration=_M_JULIA_AVAL, rationale=rationale,
        fixtures=("registry",), ops_sql=ops_sql, sqlstate_condition=cond, what=what, tabelas=_T_JULIA_AVAL,
    )


def _aval_cfg_ins(cols: str, vals: str) -> str:
    return f"    INSERT INTO {_S}.julia_avaliacao_config (org_id, {cols})\n    VALUES (v_org, {vals});"


def _aval_cache_ins(nota: str = "5", externo: str = "'noc_probe'") -> str:
    return f"    INSERT INTO {_S}.julia_avaliacoes_cache (org_id, external_id, nota)\n    VALUES (v_org, {externo}, {nota});"


def _aval_pedido_ins(cols: str, vals: str) -> str:
    return _julia_contato_ins() + "\n" + _julia_child_ins("julia_avaliacao_pedidos", cols, vals)


def _capi_ins(cols: str = "evento, dedupe_key", vals: str = "'lead_qualificado', 'noc_probe'") -> str:
    return _julia_contato_ins() + "\n" + _julia_child_ins("julia_capi_eventos", cols, vals)


#: Migration 280 -- Julia wave 13 (avaliacoes + CAPI). Unapplied guards read `no_fixture`, `refused` once applied.
_SW_JULIA_AVALIACOES_PROBES: tuple[GuardProbe, ...] = (
    _aval_probe(
        "config.review_url_https", "julia_avaliacao_config_review_url_https",
        "The review link is sent to leads verbatim; a non-https (or whitespace-bearing) value would be a broken or unsafe link.",
        _aval_cfg_ins("google_review_url", "'ftp://noc_probe'"), _CHECK, "a review link that is not https",
    ),
    _aval_probe(
        "config.pixel_valido", "julia_avaliacao_config_pixel_valido",
        "The pixel id is the CAPI endpoint path segment; a non-numeric value would be an injection into the Graph URL.",
        _aval_cfg_ins("capi_pixel_id", "'noc_probe_bogus'"), _CHECK, "a CAPI pixel id that is not numeric",
    ),
    _aval_probe(
        "pedidos.status_valido", "julia_avaliacao_pedidos_status_valido",
        "The KPI 'pedidos enviados' counts status=enviado; free text would be counted as neither sent nor failed.",
        _aval_pedido_ins("status", "'noc_probe_bogus'"), _CHECK, "a review ask with an unknown status",
    ),
    _aval_probe(
        "pedidos.erro_exige_mensagem", "julia_avaliacao_pedidos_erro_exige_mensagem",
        "A failed review ask without its error text cannot be diagnosed.",
        _aval_pedido_ins("status", "'erro'"), _CHECK, "an erro review ask with no erro text",
    ),
    _aval_probe(
        "cache.nota_valida", "julia_avaliacoes_cache_nota_valida",
        "The distribution chart has five buckets (1-5 stars); any other value falls out of the average and the chart.",
        _aval_cache_ins("9"), _CHECK, "a review with a rating outside 1..5",
    ),
    _aval_probe(
        "cache.externo_unico", "julia_avaliacoes_cache_org_externo_uq",
        "The sync is idempotent on the Google review id; a duplicate would double-count the review in total and average.",
        _aval_cache_ins() + "\n" + _aval_cache_ins(), _UNIQ, "the same Google review cached twice for one org",
    ),
    _aval_probe(
        "capi.evento_valido", "julia_capi_eventos_evento_valido",
        "The event name maps 1:1 to a Meta event; an unknown one would be sent as an undefined signal.",
        _capi_ins("evento, dedupe_key", "'noc_probe_bogus', 'noc_probe'"), _CHECK, "a CAPI signal with an unknown evento",
    ),
    _aval_probe(
        "capi.status_valido", "julia_capi_eventos_status_valido",
        "The status decides whether the sender retries or stops; free text is neither.",
        _capi_ins("evento, dedupe_key, status", "'lead_qualificado', 'noc_probe', 'noc_probe_bogus'"), _CHECK,
        "a CAPI signal with an unknown status",
    ),
    _aval_probe(
        "capi.erro_exige_mensagem", "julia_capi_eventos_erro_exige_mensagem",
        "A failed CAPI signal without its error text cannot be diagnosed.",
        _capi_ins("evento, dedupe_key, status", "'lead_qualificado', 'noc_probe', 'erro'"), _CHECK,
        "an erro CAPI signal with no erro text",
    ),
    _aval_probe(
        "capi.enviado_exige_data", "julia_capi_eventos_enviado_exige_data",
        "A signal marked enviado without its send time lies about when Meta received it.",
        _capi_ins("evento, dedupe_key, status", "'lead_qualificado', 'noc_probe', 'enviado'"), _CHECK,
        "an enviado CAPI signal with no enviado_at",
    ),
    _aval_probe(
        "capi.dedupe_unico", "julia_capi_eventos_dedupe_uq",
        "(org, dedupe_key) unique is what makes a replayed hook send one signal, not two (double-counted conversions).",
        _capi_ins() + "\n" + _julia_child_ins("julia_capi_eventos", "evento, dedupe_key", "'lead_qualificado', 'noc_probe'"),
        _UNIQ, "the same CAPI signal recorded twice",
    ),
)


_M_SIMEC = "284_simec.sql"
_T_SIMEC = (
    f"{_S}.simec_configs", f"{_S}.simec_config_historico", f"{_S}.simec_readouts", f"{_S}.simec_leituras",
)
#: A throwaway Instagram connection (rolled back with the probe) — readouts/profile
#: layers hang off integration_accounts and prod has no Instagram row to borrow.
_SIMEC_ACC_INS = (
    f"    INSERT INTO {_S}.integration_accounts (org_id, provider, account_label, encrypted_credential)\n"
    "    VALUES (v_org, 'instagram', 'noc_probe_simec', '\\x00'::bytea);"
)
_SIMEC_ACC = (
    f"(SELECT id FROM {_S}.integration_accounts WHERE org_id = v_org AND account_label = 'noc_probe_simec')"
)
_SIMEC_FP = "'" + "0" * 64 + "'"


def _simec_probe(probe_id: str, guard: str, rationale: str, ops_sql: str, cond: str, what: str) -> GuardProbe:
    return _sw_junction_probe(
        probe_id=f"simec.{probe_id}", guard_name=guard, migration=_M_SIMEC, rationale=rationale,
        fixtures=("registry",), ops_sql=ops_sql, sqlstate_condition=cond, what=what, tabelas=_T_SIMEC,
    )


def _simec_cfg_ins(platform: str = "'instagram'", overrides: str = "'{}'::jsonb",
                   version: str = "1", account: str = "NULL") -> str:
    return (
        f"    INSERT INTO {_S}.simec_configs (org_id, platform, account_id, overrides, version)\n"
        f"    VALUES (v_org, {platform}, {account}, {overrides}, {version});"
    )


def _simec_readout_ins(platform: str = "'instagram'", start: str = "DATE '2026-10-01'",
                       end: str = "DATE '2026-10-07'", fingerprint: str = _SIMEC_FP) -> str:
    return (
        _SIMEC_ACC_INS
        + f"\n    INSERT INTO {_S}.simec_readouts (org_id, account_id, platform, source, period_start,"
        " period_end, history_start, config_version, config_fingerprint, config)\n"
        f"    VALUES (v_org, {_SIMEC_ACC}, {platform}, 'noc_probe', {start}, {end}, DATE '2026-07-03',"
        f" 'noc_probe', {fingerprint}, '{{}}'::jsonb);"
    )


def _simec_leitura_ins(status: str) -> str:
    return (
        _simec_readout_ins()
        + f"\n    INSERT INTO {_S}.simec_leituras (readout_id, org_id, account_id, status)\n"
        f"    SELECT id, org_id, account_id, {status} FROM {_S}.simec_readouts\n"
        "    WHERE org_id = v_org AND source = 'noc_probe';"
    )


#: Migration 284 -- SIMEC (marketing-intelligence P1). Unapplied guards read `no_fixture`, `refused` once applied.
_SW_SIMEC_PROBES: tuple[GuardProbe, ...] = (
    _simec_probe(
        "configs.platform_valida", "simec_configs_platform_valida",
        "Each platform has its own defaults and denominators (never compared across); an unknown platform has no defaults to layer on.",
        _simec_cfg_ins(platform="'noc_probe_bogus'"), _CHECK, "a SIMEC config layer for an unknown platform",
    ),
    _simec_probe(
        "configs.overrides_objeto", "simec_configs_overrides_objeto",
        "Overrides are a partial config OBJECT deep-merged onto the defaults; an array or scalar cannot be merged.",
        _simec_cfg_ins(overrides="'[]'::jsonb"), _CHECK, "a SIMEC config layer whose overrides is not an object",
    ),
    _simec_probe(
        "configs.version_positiva", "simec_configs_version_positiva",
        "The layer version is stamped on every readout's config label (org.vN); 0 or negative breaks traceability.",
        _simec_cfg_ins(version="0"), _CHECK, "a SIMEC config layer with version 0",
    ),
    _simec_probe(
        "configs.uma_camada_org", "uq_simec_configs_org",
        "Exactly one org layer per platform, else which overrides apply is ambiguous.",
        _simec_cfg_ins() + "\n" + _simec_cfg_ins(), _UNIQ, "two org-level SIMEC config layers for one platform",
    ),
    _simec_probe(
        "configs.uma_camada_conta", "uq_simec_configs_conta",
        "Exactly one profile layer per (platform, account), else which overrides apply is ambiguous.",
        _SIMEC_ACC_INS + "\n" + _simec_cfg_ins(account=_SIMEC_ACC) + "\n" + _simec_cfg_ins(account=_SIMEC_ACC),
        _UNIQ, "two profile-level SIMEC config layers for one account",
    ),
    _simec_probe(
        "historico.versao_unica", "simec_config_historico_versao_uq",
        "The history explains a readout's org.vN/perfil.vN label; two rows for one version make it ambiguous.",
        _simec_cfg_ins()
        + f"\n    INSERT INTO {_S}.simec_config_historico (config_id, org_id, platform, version, overrides)\n"
        f"    SELECT id, org_id, platform, 1, '{{}}'::jsonb FROM {_S}.simec_configs WHERE org_id = v_org AND account_id IS NULL;"
        + f"\n    INSERT INTO {_S}.simec_config_historico (config_id, org_id, platform, version, overrides)\n"
        f"    SELECT id, org_id, platform, 1, '{{}}'::jsonb FROM {_S}.simec_configs WHERE org_id = v_org AND account_id IS NULL;",
        _UNIQ, "two SIMEC config history rows for the same layer version",
    ),
    _simec_probe(
        "readouts.platform_valida", "simec_readouts_platform_valida",
        "A readout belongs to exactly one platform (Instagram and TikTok are never mixed).",
        _simec_readout_ins(platform="'noc_probe_bogus'"), _CHECK, "a SIMEC readout for an unknown platform",
    ),
    _simec_probe(
        "readouts.periodo_valido", "simec_readouts_periodo_valido",
        "An inverted period would place every reading in neither the period nor the baseline history.",
        _simec_readout_ins(start="DATE '2026-10-07'", end="DATE '2026-10-01'"), _CHECK,
        "a SIMEC readout whose period ends before it starts",
    ),
    _simec_probe(
        "readouts.fingerprint_sha256", "simec_readouts_fingerprint_sha256",
        "The fingerprint is the unforgeable identity of the config that produced the numbers (reliability rule 1).",
        _simec_readout_ins(fingerprint="'noc_probe'"), _CHECK, "a SIMEC readout with a non-sha256 config fingerprint",
    ),
    _simec_probe(
        "leituras.status_valido", "simec_leituras_status_valido",
        "The status is the seed calculator's validation verdict; the panel only counts 'ok' — free text escapes it.",
        _simec_leitura_ins("'noc_probe_bogus'"), _CHECK, "a SIMEC reading with an unknown status",
    ),
)


_M_MAYA = "286_atendimento_blocos_supervisao.sql"
_T_MAYA = (
    f"{_S}.atendimento_blocos", f"{_S}.atendimento_handoffs", f"{_S}.agente_scorecards", f"{_S}.supervisao_config",
)
#: Every maya-blocks probe writes under a throwaway org id (no table here has an org FK), so a real
#: org's own block config can never make a probe ambiguous -- and the rollback removes it anyway.
_MAYA_ORG = "    v_org := gen_random_uuid();\n"


def _maya_probe(probe_id: str, guard: str, rationale: str, ops_sql: str, cond: str, what: str) -> GuardProbe:
    return _sw_junction_probe(
        probe_id=f"maya.{probe_id}", guard_name=guard, migration=_M_MAYA, rationale=rationale,
        fixtures=(), ops_sql=_MAYA_ORG + ops_sql, sqlstate_condition=cond, what=what, tabelas=_T_MAYA,
    )


def _maya_bloco_ins(bloco: str = "'atendimento'", pipeline: str = "'funil'", etapas: str = "ARRAY['qualificacao']::text[]",
                    agent_key: str = "NULL") -> str:
    return (
        f"    INSERT INTO {_S}.atendimento_blocos (org_id, bloco, agent_key, pipeline, etapas)\n"
        f"    VALUES (v_org, {bloco}, {agent_key}, {pipeline}, {etapas});"
    )


def _maya_handoff_ins(de: str = "'sdr'", para: str = "'atendimento'", gatilho: str = "'novo_lead'",
                      status: str = "'emitido'", assumido: str = "NULL", origem: str = "gen_random_uuid()") -> str:
    return (
        f"    INSERT INTO {_S}.atendimento_handoffs (org_id, de_bloco, para_bloco, gatilho, origem_evento, status, assumido_at)\n"
        f"    VALUES (v_org, {de}, {para}, {gatilho}, {origem}, {status}, {assumido});"
    )


def _maya_scorecard_ins(bloco: str = "'sdr'", agent_key: str = "'lead-imob'", metricas: str = "'{}'::jsonb",
                        rubrica: str = "'sdr.v1'") -> str:
    return (
        f"    INSERT INTO {_S}.agente_scorecards (org_id, bloco, agent_key, dia, metricas, rubrica_versao)\n"
        f"    VALUES (v_org, {bloco}, {agent_key}, DATE '2026-10-19', {metricas}, {rubrica});"
    )


#: Migration 286 -- maya-blocks S1 (atendimento blocks, handoffs, Maya scorecards). Unapplied guards
#: read `no_fixture`, `refused` once applied. Contract: products/social-wiring/projects/maya-blocks/CONTRACT.md.
_SW_MAYA_BLOCOS_PROBES: tuple[GuardProbe, ...] = (
    _maya_probe(
        "blocos.bloco_valido", "atendimento_blocos_bloco_valido",
        "The block list is closed (sdr, atendimento, negociacao, juridico, financeiro, contador); a free-text block "
        "would own stages no supervisor rubric or handoff rule knows about.",
        _maya_bloco_ins(bloco="'noc_probe_bogus'"), _CHECK, "a block outside the closed list",
    ),
    _maya_probe(
        "blocos.pipeline_do_bloco", "atendimento_blocos_pipeline_do_bloco",
        "sdr owns the pre-card phase and therefore no stage; giving it stages would make the derived current block "
        "of a card ambiguous between sdr and the card-stage owner.",
        _maya_bloco_ins(bloco="'sdr'"), _CHECK, "an sdr block that owns pipeline stages",
    ),
    _maya_probe(
        "blocos.agent_key_formato", "atendimento_blocos_agent_key_formato",
        "agent_key names a studio agent key (e.g. lead-imob); a malformed key can never resolve to an agent.",
        _maya_bloco_ins(agent_key="'Noc Probe!'"), _CHECK, "a block whose agent_key is not a studio key",
    ),
    _maya_probe(
        "blocos.um_por_bloco", "atendimento_blocos_um_por_bloco",
        "One config row per (org, block), else which agent runs the block is ambiguous.",
        _maya_bloco_ins() + "\n" + _maya_bloco_ins(etapas="ARRAY['visitas']::text[]"),
        _UNIQ, "two config rows for one block in one org",
    ),
    _maya_probe(
        "blocos.etapas_validas", "atendimento_blocos_etapas_validas",
        "Stage slugs are matched against pipeline_stages.slug (^[a-z0-9_]+$); a malformed slug never matches a card.",
        _maya_bloco_ins(etapas="ARRAY['Noc Probe']::text[]"), _CHECK, "a block owning a malformed stage slug",
    ),
    _maya_probe(
        "blocos.etapas_disjuntas", "atendimento_blocos_etapas_disjuntas",
        "The current block is DERIVED from the card's stage: one stage owned by two blocks makes it ambiguous "
        "and every handoff on that boundary undefined.",
        _maya_bloco_ins() + "\n" + _maya_bloco_ins(bloco="'negociacao'"),
        _CHECK, "one stage owned by two blocks of the same pipeline",
    ),
    _maya_probe(
        "handoffs.blocos_validos", "atendimento_handoffs_blocos_validos",
        "A handoff names two blocks of the closed list; anything else cannot be scored by Maya.",
        _maya_handoff_ins(para="'noc_probe_bogus'"), _CHECK, "a handoff to a block outside the closed list",
    ),
    _maya_probe(
        "handoffs.blocos_distintos", "atendimento_handoffs_blocos_distintos",
        "A handoff is a block BOUNDARY crossing; a block handing to itself is a stage move, not a handoff.",
        _maya_handoff_ins(de="'atendimento'"), _CHECK, "a handoff from a block to itself",
    ),
    _maya_probe(
        "handoffs.gatilho_valido", "atendimento_handoffs_gatilho_valido",
        "gatilho says which table origem_evento points into (julia_eventos | pipeline_movimentos); a free-text "
        "trigger makes the reference unresolvable.",
        _maya_handoff_ins(gatilho="'noc_probe_bogus'"), _CHECK, "a handoff with an unknown trigger",
    ),
    _maya_probe(
        "handoffs.status_valido", "atendimento_handoffs_status_valido",
        "The status machine is emitido -> assumido | expirado; a free-text status escapes the not-assumido metric.",
        _maya_handoff_ins(status="'noc_probe_bogus'"), _CHECK, "a handoff with an unknown status",
    ),
    _maya_probe(
        "handoffs.status_coerente", "atendimento_handoffs_status_coerente",
        "assumido without assumido_at would count as taken-over with no time-to-assume; the timestamps are the "
        "evidence behind the status.",
        _maya_handoff_ins(status="'assumido'"), _CHECK, "an assumido handoff without assumido_at",
    ),
    _maya_probe(
        "handoffs.uma_por_origem", "atendimento_handoffs_uma_por_origem",
        "Sinks and hooks replay: one event emits at most one handoff, else Maya double-counts the transfer.",
        "    v_atendimento := gen_random_uuid();\n"
        + _maya_handoff_ins(origem="v_atendimento") + "\n" + _maya_handoff_ins(origem="v_atendimento"),
        _UNIQ, "two handoffs from one originating event",
    ),
    _maya_probe(
        "scorecards.bloco_valido", "agente_scorecards_bloco_valido",
        "A scorecard belongs to a block of the closed list.",
        _maya_scorecard_ins(bloco="'noc_probe_bogus'"), _CHECK, "a scorecard for a block outside the closed list",
    ),
    _maya_probe(
        "scorecards.metricas_objeto", "agente_scorecards_metricas_objeto",
        "metricas is a name -> value object read by the contract's metric names; an array or scalar has no names.",
        _maya_scorecard_ins(metricas="'[]'::jsonb"), _CHECK, "a scorecard whose metricas is not an object",
    ),
    _maya_probe(
        "scorecards.rubrica_formato", "agente_scorecards_rubrica_formato",
        "rubrica_versao (<bloco>.vN) names the formulas that produced the numbers; free text breaks comparability.",
        _maya_scorecard_ins(rubrica="'noc probe'"), _CHECK, "a scorecard with a malformed rubric version",
    ),
    _maya_probe(
        "scorecards.um_por_dia", "agente_scorecards_um_por_dia",
        "One scorecard per (org, block, agent, day) -- including human blocks (agent_key NULL, NULLS NOT DISTINCT); "
        "two rows for one day make the report ambiguous.",
        _maya_scorecard_ins(agent_key="NULL") + "\n" + _maya_scorecard_ins(agent_key="NULL"),
        _UNIQ, "two scorecards for one human block on one day",
    ),
    _maya_probe(
        "supervisao.horas_validas", "supervisao_config_horas_validas",
        "The not-assumido threshold is 1..168 hours; 0 would expire every handoff at birth.",
        f"    INSERT INTO {_S}.supervisao_config (org_id, horas_para_assumir) VALUES (v_org, 0);",
        _CHECK, "a supervision config with a 0-hour threshold",
    ),
    _maya_probe(
        "interacoes.primeira_resposta_coerente", "julia_interacoes_primeira_resposta_coerente",
        "First-response time = primeira_resposta_at - iniciada_at; a reply before the episode began is a negative "
        "time that would drag p50/p90 below zero.",
        f"    INSERT INTO {_S}.julia_contatos (id, org_id, connection_id, chat_id)\n"
        "    VALUES (v_org, v_org, gen_random_uuid(), 'noc_probe_maya');\n"
        f"    INSERT INTO {_S}.julia_interacoes (org_id, contato_id, iniciada_at, primeira_resposta_at)\n"
        "    VALUES (v_org, v_org, now(), now() - interval '1 minute');",
        _CHECK, "an episode whose first reply precedes its start",
    ),
)


_M_JULIA_V2_SUP = "288_julia_v2_supervisao.sql"


def _julia_v2_probe(probe_id: str, guard: str, rationale: str, ops_sql: str, cond: str, what: str) -> GuardProbe:
    return _sw_junction_probe(
        probe_id=f"julia_v2.{probe_id}", guard_name=guard, migration=_M_JULIA_V2_SUP, rationale=rationale,
        fixtures=(), ops_sql=_MAYA_ORG + ops_sql, sqlstate_condition=cond, what=what, tabelas=_T_MAYA,
    )


def _julia_v2_interacao(coluna: str) -> str:
    return (
        f"    INSERT INTO {_S}.julia_contatos (id, org_id, connection_id, chat_id)\n"
        "    VALUES (v_org, v_org, gen_random_uuid(), 'noc_probe_julia_v2');\n"
        f"    INSERT INTO {_S}.julia_interacoes (org_id, contato_id, iniciada_at, {coluna})\n"
        "    VALUES (v_org, v_org, now(), now() - interval '1 minute');"
    )


#: Migration 288 -- julia-v2 SW-G (first-response agent/human split, the accept's handoff trigger). Unapplied guards
#: read `no_fixture`, `refused` once applied. Contract: products/agents/projects/julia-v2/CONTRACT.md section 7.
_SW_JULIA_V2_SUPERVISAO_PROBES: tuple[GuardProbe, ...] = (
    _julia_v2_probe(
        "interacoes.primeira_resposta_agente_coerente", "julia_interacoes_primeira_resposta_agente_coerente",
        "Julia's first-response time = primeira_resposta_agente_at - iniciada_at; a reply before the episode began is "
        "a negative time that would drag the sdr.v2 p50/p90 below zero.",
        _julia_v2_interacao("primeira_resposta_agente_at"), _CHECK, "an episode whose agent reply precedes its start",
    ),
    _julia_v2_probe(
        "interacoes.primeira_resposta_humana_coerente", "julia_interacoes_primeira_resposta_humana_coerente",
        "The human first-response time (tpr_humano_*) is reported beside Julia's; a negative one is as wrong.",
        _julia_v2_interacao("primeira_resposta_humana_at"), _CHECK, "an episode whose human reply precedes its start",
    ),
    _julia_v2_probe(
        "handoffs.gatilho_valido", "atendimento_handoffs_gatilho_valido",
        "288 REPLACED this CHECK (adding aceite_proposta): the replacement must still refuse a free-text trigger, or a "
        "typo'd hook writes handoffs no rubric counts.",
        _maya_handoff_ins(gatilho="'noc_probe_bogus'"), _CHECK, "a handoff with an unknown trigger",
    ),
)


# ---------------------------------------------------------------------------
# Registry — agents browser-read lockdown (agents migration 036, security
# finding C2, 2026-10-19). The agents schema is exposed to PostgREST and every
# logged-in member of ANY org holds a session, so an agents table granting
# anything to anon/authenticated (or carrying a policy naming them) is readable
# from the browser. Every agents table except the allowlist (`status_pagina`,
# read by the frontend's `usePageStatus`) is service-role only. State
# assertions over the catalog -- no fixture, no write; `has_table_privilege`
# ignores RLS on purpose (a policy is not a grant, a grant is the exposure).
# ---------------------------------------------------------------------------

_AGENTS_BROWSER_LOCKDOWN_MIGRATIONS = ("036_revoke_authenticated_content.sql",)
_AGENTS_BROWSER_READABLE = "ARRAY['status_pagina']"
_AGENTS_BROWSER_TABLES_SQL = (
    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'agents' AND c.relkind IN ('r', 'p') "
    f"AND NOT (c.relname = ANY ({_AGENTS_BROWSER_READABLE}))"
)

_AGENTS_BROWSER_LOCKDOWN_PROBES: tuple[GuardProbe, ...] = (
    GuardProbe(
        id="agents.content_tables.no_browser_privileges",
        product="agents",
        schema=_AGENTS_SCHEMA,
        guard_name="agents_content_tables_no_browser_privileges",
        kind="state_assertion",
        migrations=_AGENTS_BROWSER_LOCKDOWN_MIGRATIONS,
        rationale=(
            "Julia's prompt, transcripts, leads and finance live in agents.* and the schema is exposed to "
            "PostgREST: a table-level OR column-level privilege for anon/authenticated lets any logged-in "
            "member of ANY org read it with the publishable key. Only the allowlist (status_pagina) may."
        ),
        sql=_state_assertion_probe(
            select_count_sql=(
                "SELECT count(*) INTO v_count " + _AGENTS_BROWSER_TABLES_SQL + " AND ("
                "has_table_privilege('authenticated', c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER') "
                "OR has_any_column_privilege('authenticated', c.oid, 'SELECT, INSERT, UPDATE, REFERENCES') "
                "OR has_table_privilege('anon', c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER') "
                "OR has_any_column_privilege('anon', c.oid, 'SELECT, INSERT, UPDATE, REFERENCES'));"
            ),
            clean_message="no agents table outside the allowlist grants anything to anon/authenticated",
            violation_message_prefix="agents table(s) readable/writable by anon/authenticated outside the allowlist:",
        ),
    ),
    GuardProbe(
        id="agents.content_tables.no_browser_policies",
        product="agents",
        schema=_AGENTS_SCHEMA,
        guard_name="agents_content_tables_no_browser_policies",
        kind="state_assertion",
        migrations=_AGENTS_BROWSER_LOCKDOWN_MIGRATIONS,
        rationale=(
            "A `*_select_own_org` policy TO authenticated is the second half of the exposure (the grant is the "
            "first): drop both so a stray re-grant cannot silently reopen the table."
        ),
        sql=_state_assertion_probe(
            select_count_sql=(
                "SELECT count(*) INTO v_count FROM pg_policies p WHERE p.schemaname = 'agents' "
                f"AND NOT (p.tablename = ANY ({_AGENTS_BROWSER_READABLE})) "
                "AND p.roles && ARRAY['public', 'anon', 'authenticated']::name[];"
            ),
            clean_message="no agents policy outside the allowlist names anon/authenticated/public",
            violation_message_prefix="agents policy(ies) naming anon/authenticated/public outside the allowlist:",
        ),
    ),
    GuardProbe(
        id="agents.status_pagina.browser_read_only",
        product="agents",
        schema=_AGENTS_SCHEMA,
        guard_name="agents_status_pagina_browser_read_only",
        kind="state_assertion",
        migrations=_AGENTS_BROWSER_LOCKDOWN_MIGRATIONS,
        rationale=(
            "status_pagina is the one browser-readable agents table (page-visibility flags). 001's GRANT ALL "
            "left write privileges that only the missing write policy held back: they are revoked so the "
            "table is read-only for the browser by grant, not by the absence of a policy."
        ),
        sql=_state_assertion_probe(
            select_count_sql=(
                "SELECT count(*) INTO v_count FROM (VALUES ('authenticated'), ('anon')) r(role) "
                "WHERE has_table_privilege(r.role, 'agents.status_pagina', 'INSERT, UPDATE, DELETE, TRUNCATE');"
            ),
            clean_message="anon/authenticated cannot write agents.status_pagina",
            violation_message_prefix="browser role(s) can write agents.status_pagina:",
        ),
    ),
)

# ---------------------------------------------------------------------------
# Registry -- core secrets tables (core 086) + igig schema (igig 044) browser
# lockdown, security findings #1/#2/#3/#5 (2026-10-19). Same shape as the agents
# probes above: catalog state assertions, no fixture, no write;
# `has_table_privilege` ignores RLS on purpose (a policy is not a grant, a grant
# is the exposure). core: org_settings / webhook_endpoints / webhook_deliveries /
# api_keys (vendor credentials, webhook secrets, key hashes). igig: every
# relation except the allowlisted `status_pagina`.
# ---------------------------------------------------------------------------

_CORE_BROWSER_LOCKDOWN_MIGRATIONS = ("086_revoke_browser_secrets_tables.sql",)
_IGIG_BROWSER_LOCKDOWN_MIGRATIONS = ("044_revoke_authenticated_content.sql",)
_CORE_SECRET_TABLES = "ARRAY['org_settings', 'webhook_endpoints', 'webhook_deliveries', 'api_keys']"


def _browser_lockdown_probes(
    *, product: str, schema: str, migrations: tuple[str, ...], scope_sql: str, policy_scope_sql: str, label: str,
    what: str,
) -> tuple[GuardProbe, GuardProbe]:
    """Grant probe + policy probe for one browser-closed schema slice (scope_sql filters pg_class `c`/`n`;
    policy_scope_sql filters pg_policies `p`)."""
    grants = GuardProbe(
        id=f"{product}.{label}.no_browser_privileges",
        product=product,
        schema=schema,
        guard_name=f"{product}_{label}_no_browser_privileges",
        kind="state_assertion",
        migrations=migrations,
        rationale=(
            f"{what} The schema is exposed to PostgREST and every logged-in user holds a session: a table- or "
            "column-level privilege for anon/authenticated is readable/writable from the browser with the "
            "publishable key."
        ),
        sql=_state_assertion_probe(
            select_count_sql=(
                "SELECT count(*) INTO v_count FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                f"WHERE {scope_sql} AND ("
                "has_table_privilege('authenticated', c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER') "
                "OR has_any_column_privilege('authenticated', c.oid, 'SELECT, INSERT, UPDATE, REFERENCES') "
                "OR has_table_privilege('anon', c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER') "
                "OR has_any_column_privilege('anon', c.oid, 'SELECT, INSERT, UPDATE, REFERENCES'));"
            ),
            clean_message=f"{product} {label}: nothing grants anything to anon/authenticated",
            violation_message_prefix=f"{product} {label} relation(s) readable/writable by anon/authenticated:",
        ),
    )
    policies = GuardProbe(
        id=f"{product}.{label}.no_browser_policies",
        product=product,
        schema=schema,
        guard_name=f"{product}_{label}_no_browser_policies",
        kind="state_assertion",
        migrations=migrations,
        rationale=(
            "An org-isolation policy TO authenticated is the second half of the exposure (the grant is the "
            "first): drop both so a stray re-grant cannot silently reopen the table."
        ),
        sql=_state_assertion_probe(
            select_count_sql=(
                f"SELECT count(*) INTO v_count FROM pg_policies p WHERE {policy_scope_sql} "
                "AND p.roles && ARRAY['public', 'anon', 'authenticated']::name[];"
            ),
            clean_message=f"no {product} {label} policy names anon/authenticated/public",
            violation_message_prefix=f"{product} {label} policy(ies) naming anon/authenticated/public:",
        ),
    )
    return grants, policies


_CORE_BROWSER_LOCKDOWN_PROBES: tuple[GuardProbe, ...] = _browser_lockdown_probes(
    product="core", schema="public", migrations=_CORE_BROWSER_LOCKDOWN_MIGRATIONS, label="secret_tables",
    scope_sql=f"n.nspname = 'public' AND c.relkind IN ('r', 'p') AND c.relname = ANY ({_CORE_SECRET_TABLES})",
    policy_scope_sql=f"p.schemaname = 'public' AND p.tablename = ANY ({_CORE_SECRET_TABLES})",
    what="org_settings (vendor credentials, tier 1 of resolve_credential), webhook_endpoints/deliveries (url + "
         "signing secret) and api_keys (key hashes) are service-role only.",
)

_IGIG_BROWSER_LOCKDOWN_PROBES: tuple[GuardProbe, ...] = _browser_lockdown_probes(
    product="igig", schema="igig", migrations=_IGIG_BROWSER_LOCKDOWN_MIGRATIONS, label="content_tables",
    scope_sql="n.nspname = 'igig' AND c.relkind IN ('r', 'p', 'v', 'm', 'f') AND c.relname <> 'status_pagina'",
    policy_scope_sql="p.schemaname = 'igig' AND p.tablename <> 'status_pagina'",
    what="igig clients, leads, contracts, invoices, quotes and the credential vault (acesso.senha_cifrada, "
         "integracao.token_cifrado) are service-role only; only status_pagina is browser-readable.",
)


#: Migration 289 -- julia_* / lais_* are backend-only (security audit 2026-10-19 H1/H2). Unapplied: `violation`
#: (state) / `permitted` (write) -- exactly what the predeploy db_guards leg must block on until 289 is applied.
_M_JULIA_LOCKDOWN = "289_julia_db_lockdown.sql"
_JULIA_REL_PRED = r"c.relkind IN ('r', 'p', 'v', 'm') AND (c.relname LIKE 'julia\_%' OR c.relname LIKE 'lais\_%')"

_SW_JULIA_LOCKDOWN_PROBES: tuple[GuardProbe, ...] = (
    GuardProbe(
        id="julia_lockdown.no_caller_grants",
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name="julia_db_lockdown",
        kind="state_assertion",
        migrations=(_M_JULIA_LOCKDOWN,),
        rationale=(
            "Lead PII lives in julia_*; the API enforces the per-lead A7 rule, so any anon/authenticated/PUBLIC grant "
            "on a julia_* table or lais_* compat view lets every org member read it over PostgREST, bypassing A7."
        ),
        sql=_state_assertion_probe(
            select_count_sql=(
                "SELECT count(*) INTO v_count FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace, "
                "LATERAL aclexplode(COALESCE(c.relacl, acldefault('r', c.relowner))) a "
                f"WHERE n.nspname = 'social_wiring' AND {_JULIA_REL_PRED} "
                "AND (a.grantee = 0 OR a.grantee IN (SELECT oid FROM pg_roles WHERE rolname IN ('anon', 'authenticated')));"
            ),
            clean_message="no julia_/lais_ relation grants to PUBLIC/anon/authenticated",
            violation_message_prefix="julia_/lais_ grant(s) to a caller role --",
        ),
    ),
    GuardProbe(
        id="julia_lockdown.no_caller_policies",
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name="julia_db_lockdown",
        kind="state_assertion",
        migrations=(_M_JULIA_LOCKDOWN,),
        rationale="A caller-facing RLS policy on a julia_* table is a read path that skips A7 the day a grant returns.",
        sql=_state_assertion_probe(
            select_count_sql=(
                "SELECT count(*) INTO v_count FROM pg_policies p WHERE p.schemaname = 'social_wiring' "
                r"AND (p.tablename LIKE 'julia\_%' OR p.tablename LIKE 'lais\_%') "
                "AND p.roles && ARRAY['public', 'anon', 'authenticated']::name[];"
            ),
            clean_message="no caller-facing julia_ policy",
            violation_message_prefix="caller-facing julia_ RLS policy(ies) --",
        ),
    ),
    GuardProbe(
        id="julia_lockdown.no_definer_view_readable",
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name="julia_db_lockdown",
        kind="state_assertion",
        migrations=(_M_JULIA_LOCKDOWN,),
        rationale=(
            "vw_portal_roi (081) was a definer-rights view with no org filter, SELECT-able by authenticated: any user of "
            "any org read every org's investment/leads/sales. No social_wiring view may be readable by a browser role "
            "unless it is security_invoker (the caller's RLS applies); vw_portal_roi is closed to them outright."
        ),
        sql=_state_assertion_probe(
            select_count_sql=(
                "SELECT count(*) INTO v_count FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace, "
                "LATERAL aclexplode(COALESCE(c.relacl, acldefault('r', c.relowner))) a "
                "WHERE n.nspname = 'social_wiring' AND c.relkind = 'v' "
                "AND (a.grantee = 0 OR a.grantee IN (SELECT oid FROM pg_roles WHERE rolname IN ('anon', 'authenticated'))) "
                "AND (c.relname = 'vw_portal_roi' "
                "OR NOT COALESCE('security_invoker=true' = ANY (c.reloptions), false));"
            ),
            clean_message="no definer-rights social_wiring view readable by a browser role; vw_portal_roi closed",
            violation_message_prefix="definer-rights view(s) readable by a browser role --",
        ),
    ),
    GuardProbe(
        id="julia_lockdown.authenticated_select_refused",
        product="social-wiring",
        schema=_SW_SCHEMA,
        guard_name="julia_db_lockdown",
        kind="write_refusal",
        migrations=(_M_JULIA_LOCKDOWN,),
        rationale="Behavioural proof: an authenticated caller selecting julia_contatos is refused by privilege (42501).",
        sql=_do_block("""
BEGIN
  IF to_regclass('social_wiring.julia_contatos') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: social_wiring.julia_contatos does not exist';
  END IF;
  BEGIN
    SET LOCAL ROLE authenticated;
    PERFORM 1 FROM social_wiring.julia_contatos LIMIT 1;
    RAISE EXCEPTION 'NOC_PROBE:permitted: authenticated SELECT on julia_contatos succeeded -- the lockdown did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLSTATE = '42501' AND SQLERRM LIKE 'permission denied%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: refused by something other than the missing grant: %', SQLERRM;
    END IF;
  END;
END;
"""),
    ),
)



# ── core 089 — org brand identities (CONTRACT projects/org-brand-identity §1) ──
_BRAND_TABLE = "public.org_brand_identities"
_BRAND_TOKENS = "'{\"schema\": \"noctus.brand-tokens/v1\"}'::jsonb"


def _brand_double_insert_probe(*, id: str, guard_name: str, rationale: str, first_sql: str,
                               second_sql: str) -> GuardProbe:
    """Two inserts where the SECOND must trip ``guard_name`` (if the FIRST already
    trips it — an existing row occupies the slot — the guard refused too)."""
    fixture = (
        "  SELECT id INTO v_org FROM public.organizations LIMIT 1;\n"
        "  IF v_org IS NULL THEN\n"
        "    RAISE EXCEPTION 'NOC_PROBE:no_fixture: no row in public.organizations to borrow an org from';\n"
        "  END IF;\n"
    )
    return GuardProbe(
        id=id, product="core", schema="public", guard_name=guard_name, kind="write_refusal",
        migrations=("089_org_brand_identities.sql",), rationale=rationale,
        sql=_do_block(f"""
DECLARE
  v_org uuid;
BEGIN
{fixture}  BEGIN
    {first_sql}
    {second_sql}
    RAISE EXCEPTION 'NOC_PROBE:permitted: second insert succeeded — {guard_name} did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{guard_name}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
"""),
    )


_CORE_BRAND_PROBES: tuple[GuardProbe, ...] = (
    GuardProbe(
        id="org_brand_identities.tokens.schema_check",
        product="core", schema="public", guard_name="org_brand_identities_tokens_schema",
        kind="write_refusal", migrations=("089_org_brand_identities.sql",),
        rationale=(
            "Every stored identity carries a noctus.brand-tokens/v1 document; a row "
            "with another (or no) schema would reach BrandProvider unvalidated."
        ),
        sql=_insert_check_probe(
            schema="public", table="org_brand_identities",
            columns_sql="org_id, version, status, tokens",
            values_sql="id, 900001, 'draft', '{}'::jsonb",
            fixture_from="public.organizations",
            fixture_description="no row in public.organizations to borrow an org from",
            guard_fragment="org_brand_identities_tokens_schema",
        ),
    ),
    _brand_double_insert_probe(
        id="org_brand_identities.active_org.unique",
        guard_name="ux_org_brand_identities_active_org",
        rationale="One ACTIVE identity per org — two would make /api/brand/current ambiguous.",
        first_sql=f"INSERT INTO {_BRAND_TABLE} (org_id, version, status, tokens) VALUES (v_org, 900001, 'active', {_BRAND_TOKENS});",
        second_sql=f"INSERT INTO {_BRAND_TABLE} (org_id, version, status, tokens) VALUES (v_org, 900002, 'active', {_BRAND_TOKENS});",
    ),
    _brand_double_insert_probe(
        id="org_brand_identities.active_platform.unique",
        guard_name="ux_org_brand_identities_active_platform",
        rationale="One ACTIVE platform (NOC standard) row — the fallback every org without an identity wears.",
        first_sql=f"INSERT INTO {_BRAND_TABLE} (org_id, version, status, tokens) VALUES (NULL, 900001, 'active', {_BRAND_TOKENS});",
        second_sql=f"INSERT INTO {_BRAND_TABLE} (org_id, version, status, tokens) VALUES (NULL, 900002, 'active', {_BRAND_TOKENS});",
    ),
    _brand_double_insert_probe(
        id="org_brand_identities.org_version.unique",
        guard_name="ux_org_brand_identities_org_version",
        rationale="Versions are unique per org (rollback addresses a version); a duplicate would make history ambiguous.",
        first_sql=f"INSERT INTO {_BRAND_TABLE} (org_id, version, status, tokens) VALUES (v_org, 900001, 'draft', {_BRAND_TOKENS});",
        second_sql=f"INSERT INTO {_BRAND_TABLE} (org_id, version, status, tokens) VALUES (v_org, 900001, 'draft', {_BRAND_TOKENS});",
    ),
)


DEFAULT_REGISTRY: tuple[GuardProbe, ...] = (
    *_MATRICULA_PROBES,
    _RUIDO_SHAPE_PROBE,
    _TITULO_PAREADO_PROBE,
    _ONUS_CREDOR_PAREADO_PROBE,
    _ACAO_CHECK_PROBE,
    _CERTIDAO_ACAO_CHECK_PROBE,
    *_ABERTURA_PROBES,
    _ABERTURA_UNIQUE_PROBE,
    _IMOBILIARIA_CNPJ_UNIQUE_PROBE,
    _CLIENTE_ORIGEM_EXCLUIDA_UNIQUE_PROBE,
    _CS_RESEARCH_ITEM_UNIQUE_PROBE,
    *_CS_WAVE2_PROBES,
    *_CS_GERACAO_PROBES,
    _VISITA_MOTIVO_CHECK_PROBE,
    _ORG_MEMBERSHIP_ENDED_IFF_REMOVED_PROBE,
    _JULIA_AGENTE_EXIGE_AUTORIZADOS_PROBE,
    _JULIA_AGENTE_EXIGE_ATIVADO_EM_PROBE,
    _JULIA_CONEXAO_TRANSPORTE_PROBE,
    _ROTEIRO_FEEDBACK_STATUS_CHECK_PROBE,
    _ENDERECO_REGISTRO_PROBE,
    _ULTIMA_TRANSFERENCIA_MANUAL_PROBE,
    _ULTIMA_TRANSFERENCIA_MANUAL_NATUREZA_PROBE,
    _ULTIMA_TRANSFERENCIA_MANUAL_NATUREZA_REQUER_DATA_PROBE,
    _ULTIMA_TRANSFERENCIA_MANUAL_EXCLUSIVA_PROBE,
    *_SW_CAMPOS_MANUAIS_PROBES,
    _EMPREENDIMENTO_MANUAL_PROBE,
    _IMOVEL_CONDOMINIO_OU_CASA_DE_RUA_PROBE,
    _IMOVEL_CONDOMINIO_MESMA_ORG_PROBE,
    _STORAGE_BUCKETS_PROBE,
    _SECDEF_EXECUTE_PROBE,
    _INTERESSADOS_EMAIL_UNIQUE_PROBE,
    *_ORG_PICKER_PROBES,
    _PLATFORM_ORG_REVOKE_REFUSED_PROBE,
    _PLATFORM_ORG_HOLDS_EVERY_PRODUCT_PROBE,
    _PLATFORM_ORG_NEW_PRODUCT_PROBE,
    _SW_ONE_PRIMARY_MARCA_PROBE,
    _SW_ONE_PRIMARY_KIT_PROBE,
    _CERTIDAO_CONSULTA_ORIGEM_PROBE,
    _CERTIDAO_CONSULTA_DOCUMENTO_PROBE,
    *_AGENTS_STUDIO_PROBES,
    *_AGENTS_JULIA_V2_PROBES,
    *_AGENTS_GERACAO_PROBES,
    *_AGENTS_ISOLATION_PROBES,
    _ESTRUTURA_STATUS_PROBE,
    _IMOVEL_CONFLITO_ABERTO_PROBE,
    _CLIENTE_CONFLITO_STATUS_PROBE,
    _EMPRESA_CONFLITO_STATUS_PROBE,
    _ATENDIMENTO_CONFLITO_STATUS_PROBE,
    *_IGIG_PROBES,
    *_CORE_AUDIT_LOGS_PROBES,
    *_CORE_AI_USAGE_PROBES,
    *_PLATFORM_TEMPLATES_PROBES,
    _SSO_PROMOTION_PROBE,
    *_MFA_POLICY_PROBES,
    *_SEED_ANON_LOCKDOWN_PROBES,
    *_ANON_SEQUENCE_PROBES,
    _ERP_CURRENT_ORG_ID_PROBE,
    *_SW_AI_TABLES_PROBES,
    _SW_CONTACTS_EMAIL_OPTIN_PROBE,
    _SW_CERTIDAO_RESULTADO_ORIGEM_PROBE,
    _SW_250_ESTRUTURA_PROBE,
    _SW_251_FAVORECIDOS_UNIQUE_PROBE,
    _ERASE_TEST_ORG_AUDIT_LOGS_PROBE,
    _CUSTOMER_GETS_NO_ORG_PROBE,
    _INVITATION_TOKEN_PROBE,
    _LICENSES_ONE_ACTIVE_PROBE,
    _SW_API_TOKEN_HASH_PROBE,
    _SW_RECIPIENT_CHANNEL_PROBE,
    *_COMMUNITY_PROBES,
    *_SW_179_183_PROBES,
    *_SW_190_PROBES,
    *_SW_192_PROBES,
    *_SW_201_PROBES,
    *_SW_207_PROBES,
    *_SW_218_PROBES,
    *_SW_PROPOSTAS_PROBES,
    *_SW_IMOVEL_MANUAL_PROBES,
    *_SW_TRANSACOES_PROBES,
    *_SW_CONDOMINIOS_PROBES,
    *_SW_JULIA_PROBES,
    *_SW_PERGUNTAS_PROBES,
    *_SW_JULIA_VISITAS_PROBES,
    *_SW_JULIA_NOTIF_PROBES,
    *_SW_JULIA_REENG_PROBES,
    *_SW_JULIA_CONV_PROBES,
    *_SW_JULIA_CLOUD_PROBES,
    *_SW_JULIA_PROPRIETARIOS_TIPO_PROBES,
    *_SW_JULIA_EQUIPES_PROBES,
    *_SW_231_PROBES,
    *_SW_240_PROBES,
    *_SW_241_PROBES,
    *_SW_JULIA_ENVIO_PROBES,
    *_SW_JULIA_CAPTACAO_PROBES,
    *_SW_JULIA_CREDITO_PROBES,
    *_SW_JULIA_STAFF_PROT_PROBES,
    *_SW_JULIA_AVALIACOES_PROBES,
    *_SW_SIMEC_PROBES,
    *_SW_MAYA_BLOCOS_PROBES,
    *_SW_JULIA_V2_SUPERVISAO_PROBES,
    *_SW_JULIA_LOCKDOWN_PROBES,
    *_EDITORIAL_PROBES,
    *_AGENTS_EDITORIAL_PROBES,
    *_BRANDING_PROBES,
    *_CEREBRO_PROBES,
    *_TRANSCRICOES_PROBES,
    _CORE_JOBS_DEDUPE_UNIQUE_PROBE,
    _COMMERCE_COUPON_PERCENT_PROBE,
    _COMMERCE_COUPON_CODE_UNIQUE_PROBE,
    *_ORBITY_018_PROBES,
    _MONICA_WA_WEBHOOK_TOKEN_UNIQUE_PROBE,
    *_AGENTS_BROWSER_LOCKDOWN_PROBES,
    *_CORE_BROWSER_LOCKDOWN_PROBES,
    *_IGIG_BROWSER_LOCKDOWN_PROBES,
    *_CORE_BRAND_PROBES,
)

#: Every `guard_name` the registry proves at least one probe for — the
#: membership set `check_migration_guard_has_probe` (compliance.py)
#: checks a newly-staged migration's guard objects against.
REGISTERED_GUARD_NAMES: frozenset[str] = frozenset(p.guard_name for p in DEFAULT_REGISTRY)


# ---------------------------------------------------------------------------
# Organ-derived probes -- a seed organ declares its guards ONCE
# (`noctusai_seed.organs.ORGAN_REGISTRY[...].guard_probes`, next to the generator); every product that rendered
# the organ's migration (found by the organ's header line, never by number) gets the organ's probes bound to
# ITS schema. A render therefore never needs a hand-written probe or `_GUARD_PROBE_ALLOWLIST` entry.
# A probe whose table is not in the target DB yet (migration pending) reports `pending` -- never a false green.
# ---------------------------------------------------------------------------

_ORGAN_PROBE_PREFIX = "organ"


def _organ_probe_sql(schema: str, probe: Any) -> str:
    """One `OrganGuardProbe` -> the standard probe body (pending guard, classified sub-block, sentinels)."""
    pending = "\n".join(
        f"  IF to_regclass('{_sql_lit(schema)}.{_sql_lit(t)}') IS NULL THEN\n"
        f"    RAISE EXCEPTION 'NOC_PROBE:pending: {_sql_lit(schema)}.{_sql_lit(t)} does not exist (organ migration not applied)';\n"
        "  END IF;"
        for t in probe.requires
    )
    body = probe.body.strip()
    if _PROBE_TAG in body or _PROBE_TAG in probe.declare:
        raise ValueError(f"organ guard {probe.guard_name!r}: probe text may not contain {_PROBE_TAG}")
    declare = probe.declare.strip()
    return _do_block(f"""
DECLARE
  v_org uuid := gen_random_uuid();
  {declare}
BEGIN
{pending}
  BEGIN
{body}
    RAISE EXCEPTION 'NOC_PROBE:permitted: {_sql_lit(probe.permitted)} succeeded -- the {probe.kind} guard did not fire';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE 'NOC_PROBE:permitted:%' THEN
      RAISE;
    ELSIF SQLERRM LIKE '%{_sql_lit(probe.refusal_fragment)}%' THEN
      RAISE EXCEPTION 'NOC_PROBE:refused: %', SQLERRM;
    ELSE
      RAISE EXCEPTION 'NOC_PROBE:ambiguous: unexpected error (not the guard under test): %', SQLERRM;
    END IF;
  END;
END;
""")


def _unverifiable_probe(probe_id: str, product: str, schema: str, why: str) -> GuardProbe:
    """A deliberately failing probe: what could not be derived is reported, never skipped."""
    return GuardProbe(
        id=probe_id, product=product, schema=schema, guard_name=probe_id, kind="write_refusal",
        rationale="organ-derived probes must be derivable for every product that rendered an organ migration",
        sql=_do_block(f"""
BEGIN
  RAISE EXCEPTION 'NOC_PROBE:no_fixture: {_sql_lit(why)}';
END;
"""),
    )


def derive_organ_probes(*, products_dir: Any = None, registry: Any = None) -> tuple[GuardProbe, ...]:
    """The probes of every organ guard, for every product with a rendered organ migration.

    Fail-closed: an organ registry that cannot be imported, or a product whose schema cannot be derived, yields a
    failing probe naming the cause instead of silently deriving nothing.
    """
    from settings import PRODUCTS_DIR

    root = products_dir or PRODUCTS_DIR
    if registry is None:
        try:
            from noctusai_seed.organs import ORGAN_REGISTRY as registry  # type: ignore[no-redef]
        except ImportError as exc:
            return (_unverifiable_probe(
                f"{_ORGAN_PROBE_PREFIX}.registry_unavailable", "<platform>", "public",
                f"cannot import noctusai_seed.organs ({exc}): organ-derived guard probes cannot be derived",
            ),)
    headers = {name: spec.migration_header for name, spec in registry.items() if getattr(spec, "guard_probes", None)}
    undeclared = {name: spec.migration_header for name, spec in registry.items() if not getattr(spec, "guard_probes", None)}
    longest = max((len(h) for h in {**headers, **undeclared}.values()), default=0)

    rendered: dict[tuple[str, str], list[str]] = {}
    for sql_file in sorted(root.glob("*/backend/migrations/*.sql")):
        try:
            with open(sql_file, encoding="utf-8") as fh:
                head = fh.read(longest + 1)
        except (OSError, UnicodeDecodeError):
            continue
        product = sql_file.parents[2].name
        for name, header in {**headers, **undeclared}.items():
            if head.startswith(header):
                rendered.setdefault((product, name), []).append(sql_file.name)

    probes: list[GuardProbe] = []
    for (product, organ), files in sorted(rendered.items()):
        if organ in undeclared:
            probes.append(_unverifiable_probe(
                f"{_ORGAN_PROBE_PREFIX}.{organ}.{product}.undeclared", product, "public",
                f"organ {organ!r} rendered into {product} declares no guard_probes",
            ))
            continue
        schema, source = _mp._resolve_schema(product, None, root)
        if source == "slug_fallback":
            probes.append(_unverifiable_probe(
                f"{_ORGAN_PROBE_PREFIX}.{organ}.{product}.schema", product, schema,
                f"cannot derive the DB schema of {product} from its create_product_app(schema=...) declaration",
            ))
            continue
        latest = sorted(files)[-1]
        for op in registry[organ].guard_probes(schema):
            probes.append(GuardProbe(
                id=f"{_ORGAN_PROBE_PREFIX}.{organ}.{product}.{op.probe_key}",
                product=product,
                schema=schema,
                guard_name=op.guard_name,
                kind="write_refusal",
                migrations=(latest,),
                rationale=op.rationale,
                sql=_organ_probe_sql(schema, op),
            ))
    return tuple(probes)


def full_registry(*, products_dir: Any = None, registry: Any = None) -> tuple[GuardProbe, ...]:
    """`DEFAULT_REGISTRY` (hand-written, per-product) + the organ-derived probes: what a run actually executes."""
    return (*DEFAULT_REGISTRY, *derive_organ_probes(products_dir=products_dir, registry=registry))



# ---------------------------------------------------------------------------
# Top-level runner
# ---------------------------------------------------------------------------


def _migration_declared(product: str, filename: str) -> bool:
    """True when ``filename`` is a real migration file of ``product`` in this tree
    — only a DECLARED migration can be "pending"; a stale or misspelled name in a
    probe's ``migrations`` never parks the probe (it runs as usual)."""
    from settings import PRODUCTS_DIR

    return (PRODUCTS_DIR / product / "backend" / "migrations" / filename).is_file()


def _ledger_reader(executor: Any):
    """``product -> set(applied filenames) | None`` over the product's own
    ``schema_migrations`` (the ledger ``migrate_product`` writes). ``None`` =
    unknowable (no ledger / query failed / schema unresolved): the caller then
    runs the probe normally — an unknown ledger never parks a probe."""
    cache: dict[str, Any] = {}

    def lookup(product: str):
        if product in cache:
            return cache[product]
        applied = None
        try:
            from settings import PRODUCTS_DIR

            schema = _mp._resolve_schema(product, None, PRODUCTS_DIR)[0]
            q = '"' + schema.replace('"', '""') + '"'
            r = executor.execute(f"SELECT filename FROM {q}.schema_migrations;")
            if r.get("ok"):
                applied = {row.get("filename") for row in (r.get("rows") or []) if isinstance(row, dict)}
        except Exception as exc:  # noqa: BLE001 — unknowable ledger ⇒ run the probe; never park it
            logger.debug("verify_db_guards: ledger for %s unreadable (%s)", product, exc)
        cache[product] = applied
        return applied

    return lookup


def _pending_migrations(probe: GuardProbe, lookup, declared) -> list[str]:
    candidates = [m for m in probe.migrations if declared(probe.product, m)]
    if not candidates:
        return []  # nothing declared to wait for — no ledger round-trip at all
    applied = lookup(probe.product)
    if applied is None:
        return []
    return [m for m in candidates if m not in applied]


def verify_db_guards(
    *,
    executor: "_mp.SqlExecutor | None" = None,
    project_ref: str = DEFAULT_PROJECT_REF,
    registry: tuple[GuardProbe, ...] | None = None,
    ledger_lookup: Any = None,
    migration_declared: Any = None,
    probe_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Run every probe in `registry` (default `DEFAULT_REGISTRY`) against
    the live database, inside its own rollback-only transaction. Never
    raises. A probe whose declared migration is not yet in its product's
    ledger is NOT run: it reports `status='pending_migration'` (named,
    non-blocking — collected under `pending`, never a failure and never a silent
    skip). Once the ledger shows the migration applied, the probe runs and a
    missing fixture is a failure again (2026-10-10: probes written ahead of
    SW 239 blocked every SW release from the dev tip).
    `status`: `'clean'` (every probe `pass`) | `'violations_found'`
    (>=1 `finding` — a guard did not fire) | `'unverified'` (>=1 `failure`,
    no findings) | `'not_configured'` (no credentials) | `'error'` (empty
    registry / bad input) | `'unverified_transient'` (no findings/failures, but >=1 probe hit a transport
    failure that survived the automatic paced retries -- re-run ONLY `retry_probe_ids` via `probe_ids=`).
    `probe_ids` restricts the run to those probe ids (unknown ids -> `status='error'`).
    """

    def _result(status: str, **overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "ok": status == "clean",
            "status": status,
            "checked": 0,
            "results": [],
            "findings": [],
            "failures": [],
            "pending": [],
            "transient": [],
            "retry_probe_ids": [],
            "error": None,
        }
        base.update(overrides)
        return base

    reg = registry if registry is not None else full_registry()
    if not reg:
        return _result("error", error="verify_db_guards: empty probe registry")
    if probe_ids is not None:
        wanted = list(dict.fromkeys(probe_ids))
        known = {p.id for p in reg}
        unknown = [i for i in wanted if i not in known]
        if unknown:
            return _result("error", error=f"verify_db_guards: unknown probe_ids {unknown[:10]}")
        reg = tuple(p for p in reg if p.id in set(wanted))

    if executor is None:
        executor = _mp.make_sql_executor(project_ref=project_ref)
    if executor is None:
        return _result(
            "not_configured",
            error=(
                "NOC-REMEDIATE[credentials]: no supabase_access_token resolved. "
                "Same DB-first resolution path as noctus.dev.migrate_product / "
                "noctus.dev.schema_drift. A guard you cannot connect to verify "
                "is not a guard you verified — this is a FAILURE for "
                "predeploy_check, not a skip."
            ),
        )

    lookup = ledger_lookup or _ledger_reader(executor)
    declared = migration_declared or _migration_declared
    results: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    transient: list[dict[str, Any]] = []
    for probe in reg:
        waiting = _pending_migrations(probe, lookup, declared)
        if waiting:
            r = {
                "id": probe.id, "probe_id": probe.id, "product": probe.product,
                "schema": probe.schema, "guard_name": probe.guard_name, "kind": probe.kind,
                "status": "pending_migration", "outcome": None, "severity": "info",
                "pending_migrations": waiting,
                "detail": (f"not run: {', '.join(waiting)} not yet in {probe.product}'s "
                           "schema_migrations ledger — the guard does not exist in this "
                           "database yet; it is probed once the migration is applied"),
            }
            results.append(r)
            pending.append(r)
            continue
        r = run_probe(probe, executor)
        results.append(r)
        if r["status"] == "pending_migration":
            pending.append(r)
        elif r["status"] == "finding":
            findings.append(r)
        elif r["status"] == "failure":
            failures.append(r)
        elif r["status"] == "unverified_transient":
            transient.append(r)

    if findings:
        status = "violations_found"
    elif failures:
        status = "unverified"
    elif transient:
        status = "unverified_transient"
    else:
        status = "clean"

    return _result(
        status,
        checked=len(reg) - len(pending),
        results=results,
        findings=findings,
        failures=failures,
        pending=pending,
        transient=transient,
        retry_probe_ids=[r["probe_id"] for r in transient],
    )


def register(server) -> None:
    @server.tool(
        name="noctus.dev.verify_db_guards",
        description=(
            "Executable proof that a declared database guard (trigger/CHECK/"
            "UNIQUE constraint) actually refuses what it claims to refuse — "
            "runs the exact forbidden operation against PRODUCTION inside a "
            "transaction that is rolled back by construction (see "
            "wrap_rollback_only), never by convention. The refusal IS the "
            "pass; an operation that SUCCEEDS is the finding. Fail-closed: a "
            "probe with no fixture row, an unclassifiable executor error, or "
            "no credentials is a FAILURE, never a silent skip. Wired into "
            "noctus.dev.predeploy_check as the db_guards leg. Seeded with the "
            "social_wiring.matricula_extracoes write-once trigger (6 frozen "
            "columns), its ruido shape CHECK, matricula_abertura_blocos's 3 "
            "CHECK constraints + its (extracao_id, campo) UNIQUE index, the "
            "platform-wide zero-public-storage-buckets state assertion, and "
            "core.audit_logs's append-only guard (UPDATE always refused, "
            "DELETE refused outside purge_expired_audit_logs). "
            "Transport failures (DNS/timeout/reset/429/502-504) are retried automatically (paced 1s/3s/9s); "
            "any that still fail come back status='unverified_transient' with `retry_probe_ids` -- pass them as "
            "`probe_ids` to re-run ONLY those probes. "
            "Returns {status, checked, results, findings, failures, transient, retry_probe_ids, error}. "
            "KB § PATTERNS/common/methodology-execution-discipline.md § 8."
        ),
    )
    def _verify_db_guards(project_ref: str = DEFAULT_PROJECT_REF, probe_ids: list[str] | None = None) -> dict:
        return verify_db_guards(project_ref=project_ref, probe_ids=probe_ids)


__all__ = [
    "GuardProbe",
    "DEFAULT_REGISTRY",
    "REGISTERED_GUARD_NAMES",
    "derive_organ_probes",
    "full_registry",
    "wrap_rollback_only",
    "run_probe",
    "verify_db_guards",
    "register",
]
