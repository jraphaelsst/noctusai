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

import re
from dataclasses import dataclass, field
from typing import Any

from . import migrate_product as _mp

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
    r"no_fixture|ambiguous):"
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
}
_OUTCOME_SEVERITY: dict[str, str] = {
    "permitted": "high",
    "violation": "critical",
    "blocked": "high",
    "no_fixture": "high",
    "ambiguous": "high",
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
    migrations=("152_ultima_transferencia_manual.sql",),
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

_ORG_PICKER_DECLARE = """
DECLARE
  v_staff uuid; v_home uuid; v_plain uuid; v_plain_home uuid;
  v_pid uuid; v_slug text; v_schema text; v_target uuid; v_unlic uuid;
  v_sid uuid := gen_random_uuid();
  v_other_sid uuid := gen_random_uuid();
  v_got uuid; v_sel uuid;
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


def _org_picker_probe(*, probe_id: str, guard_name: str, kind: str, rationale: str, steps: str) -> GuardProbe:
    return GuardProbe(
        id=probe_id,
        product="core",
        schema="public",
        guard_name=guard_name,
        kind=kind,
        migrations=_ORG_PICKER_MIGRATIONS,
        rationale=rationale,
        sql=_do_block(_ORG_PICKER_DECLARE + "BEGIN\n" + _ORG_PICKER_FIXTURE + steps + "\nEND;\n"),
    )


def _picker_rpc_refusal_probe(*, probe_id: str, code: str, setup: str, call: str, rationale: str) -> GuardProbe:
    return _org_picker_probe(
        probe_id=probe_id, guard_name="platform_org_selection_set", kind="write_refusal",
        rationale=rationale,
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


def _picker_helper_probe(*, probe_id: str, rationale: str, steps: str, expect: str, what: str) -> GuardProbe:
    """State assertion on ``current_org_id_for(v_schema)``: after ``steps`` forge a caller,
    `v_got` is compared with `expect` (a SQL uuid expression)."""
    return _org_picker_probe(
        probe_id=probe_id, guard_name="current_org_id_for", kind="state_assertion", rationale=rationale,
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

_ORG_PICKER_SET_NOT_STAFF_PROBE = _picker_rpc_refusal_probe(
    probe_id="platform_org_selection_set.refuses_non_staff",
    code="not_platform_staff",
    setup="",
    call="PERFORM public.platform_org_selection_set(v_plain, v_slug, v_target, v_sid);",
    rationale=(
        "Only platform staff (role=admin AND home org is_platform) may enter another org; "
        "the RPC re-checks it itself, so a compromised or buggy API caller cannot grant it."
    ),
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
        "A non-staff caller never acts: even with a (forged, table-level) selection row naming "
        "another org, the helper answers their HOME org."
    ),
    steps="""
  INSERT INTO public.platform_org_selections (user_id, product_id, target_org_id, home_org_id, auth_session_id)
  VALUES (v_plain, v_pid, v_target, v_plain_home, v_sid);
""" + _caller_sql("v_plain::text"),
    expect="v_plain_home",
    what="a non-staff caller resolves to their home org",
)

_ORG_PICKER_HELPER_SESSION_PROBE = _picker_helper_probe(
    probe_id="current_org_id_for.home_on_session_mismatch",
    rationale="A selection is bound to ONE login: another session_id (a new login) resolves home.",
    steps="""
  PERFORM public.platform_org_selection_set(v_staff, v_slug, v_target, v_sid);
""" + _caller_sql("v_staff::text", sid="v_other_sid"),
    expect="v_home",
    what="another login session_id resolves to the home org",
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
    probe_id="current_org_id_for.home_when_target_unlicensed",
    rationale=(
        "The helper re-checks the license itself: a selection whose target holds no active "
        "license (inserted at table level, bypassing the RPC and the revocation trigger) "
        "resolves home."
    ),
    steps="""
  IF v_unlic IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: every organization is licensed for the product — no unlicensed target to forge';
  END IF;
  INSERT INTO public.platform_org_selections (user_id, product_id, target_org_id, home_org_id, auth_session_id)
  VALUES (v_staff, v_pid, v_unlic, v_home, v_sid);
""" + _caller_sql("v_staff::text"),
    expect="v_home",
    what="an unlicensed target resolves to the home org",
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
    probe_id="current_org_id_for.home_when_auth_session_gone",
    rationale="A selection dies with its login: once the auth.sessions row is gone the helper resolves home.",
    steps="""
  PERFORM public.platform_org_selection_set(v_staff, v_slug, v_target, v_sid);
  DELETE FROM auth.sessions WHERE id = v_sid;
""" + _caller_sql("v_staff::text"),
    expect="v_home",
    what="a selection whose auth session is gone resolves to the home org",
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
    _ORG_PICKER_SET_NOT_STAFF_PROBE,
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
    _ORG_PICKER_PRODUCT_REVOKE_PROBE,
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
        what="a Julia persona whose model is outside the allowlist",
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
        migrations=("218_campanha_intake.sql",),
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
    _ENDERECO_REGISTRO_PROBE,
    _ULTIMA_TRANSFERENCIA_MANUAL_PROBE,
    _ULTIMA_TRANSFERENCIA_MANUAL_NATUREZA_PROBE,
    _ULTIMA_TRANSFERENCIA_MANUAL_NATUREZA_REQUER_DATA_PROBE,
    _ULTIMA_TRANSFERENCIA_MANUAL_EXCLUSIVA_PROBE,
    _EMPREENDIMENTO_MANUAL_PROBE,
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
    *_AGENTS_STUDIO_PROBES,
    _ESTRUTURA_STATUS_PROBE,
    _IMOVEL_CONFLITO_ABERTO_PROBE,
    _CLIENTE_CONFLITO_STATUS_PROBE,
    _EMPRESA_CONFLITO_STATUS_PROBE,
    _ATENDIMENTO_CONFLITO_STATUS_PROBE,
    *_IGIG_PROBES,
    *_CORE_AUDIT_LOGS_PROBES,
    *_MFA_POLICY_PROBES,
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
    *_EDITORIAL_PROBES,
    *_AGENTS_EDITORIAL_PROBES,
    *_BRANDING_PROBES,
)

#: Every `guard_name` the registry proves at least one probe for — the
#: membership set `check_migration_guard_has_probe` (compliance.py)
#: checks a newly-staged migration's guard objects against.
REGISTERED_GUARD_NAMES: frozenset[str] = frozenset(p.guard_name for p in DEFAULT_REGISTRY)


# ---------------------------------------------------------------------------
# Top-level runner
# ---------------------------------------------------------------------------


def verify_db_guards(
    *,
    executor: "_mp.SqlExecutor | None" = None,
    project_ref: str = DEFAULT_PROJECT_REF,
    registry: tuple[GuardProbe, ...] | None = None,
) -> dict[str, Any]:
    """Run every probe in `registry` (default `DEFAULT_REGISTRY`) against
    the live database, inside its own rollback-only transaction. Never
    raises. `status`: `'clean'` (every probe `pass`) | `'violations_found'`
    (>=1 `finding` — a guard did not fire) | `'unverified'` (>=1 `failure`,
    no findings) | `'not_configured'` (no credentials) | `'error'` (empty
    registry / bad input).
    """

    def _result(status: str, **overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "ok": status == "clean",
            "status": status,
            "checked": 0,
            "results": [],
            "findings": [],
            "failures": [],
            "error": None,
        }
        base.update(overrides)
        return base

    reg = registry if registry is not None else DEFAULT_REGISTRY
    if not reg:
        return _result("error", error="verify_db_guards: empty probe registry")

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

    results: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for probe in reg:
        r = run_probe(probe, executor)
        results.append(r)
        if r["status"] == "finding":
            findings.append(r)
        elif r["status"] == "failure":
            failures.append(r)

    if findings:
        status = "violations_found"
    elif failures:
        status = "unverified"
    else:
        status = "clean"

    return _result(
        status,
        checked=len(reg),
        results=results,
        findings=findings,
        failures=failures,
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
            "Returns {status, checked, results, findings, failures, error}. "
            "KB § PATTERNS/common/methodology-execution-discipline.md § 8."
        ),
    )
    def _verify_db_guards(project_ref: str = DEFAULT_PROJECT_REF) -> dict:
        return verify_db_guards(project_ref=project_ref)


__all__ = [
    "GuardProbe",
    "DEFAULT_REGISTRY",
    "REGISTERED_GUARD_NAMES",
    "wrap_rollback_only",
    "run_probe",
    "verify_db_guards",
    "register",
]
