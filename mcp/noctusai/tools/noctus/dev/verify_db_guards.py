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
or `"state_assertion"` — read live state, expect it to be clean), and
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
  refused / clean        -> "pass"      (the guard did what it claims)
  permitted / violation  -> "finding"   (the guard did NOT fire — the bug)
  no_fixture / ambiguous -> "failure"   (could not verify at all)
  (executor ok=True, or no sentinel found in the error text) -> "failure"

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
    r"NOC_PROBE:(?P<outcome>refused|permitted|clean|violation|no_fixture|ambiguous):"
    r"\s*(?P<detail>.*)",
    re.DOTALL,
)

_OUTCOME_STATUS: dict[str, str] = {
    "refused": "pass",
    "clean": "pass",
    "permitted": "finding",
    "violation": "finding",
    "no_fixture": "failure",
    "ambiguous": "failure",
}
_OUTCOME_SEVERITY: dict[str, str] = {
    "permitted": "high",
    "violation": "critical",
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
    kind: str  # "write_refusal" | "state_assertion"
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

def _igig_probe(
    *, probe_id: str, guard_name: str, setup_sql: tuple[str, ...], attack_sql: str, what: str,
    rationale: str, migrations: tuple[str, ...],
) -> GuardProbe:
    """One self-provisioned igig write-refusal probe. The expected refusal is
    classified on `guard_name` itself appearing in SQLERRM — Postgres names the
    violated constraint/index in both the CHECK and the UNIQUE message."""
    name_lit = _sql_lit(guard_name)
    what_lit = _sql_lit(what)
    setup = "\n".join(f"    {stmt}" for stmt in setup_sql)
    sql = _do_block(f"""
DECLARE
  v_org uuid := gen_random_uuid();
  v_stage uuid;
  v_lead uuid;
  v_negocio uuid;
  v_cliente uuid;
  v_pauta uuid;
  v_tarefa uuid;
  v_orcamento uuid;
BEGIN
  IF to_regclass('{_IGIG_SCHEMA}.negocio') IS NULL THEN
    RAISE EXCEPTION 'NOC_PROBE:no_fixture: {_IGIG_SCHEMA}.negocio does not exist (migration 018 not applied)';
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
        product="igig",
        schema=_IGIG_SCHEMA,
        guard_name=guard_name,
        kind="write_refusal",
        migrations=migrations,
        sql=sql,
        rationale=rationale,
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


DEFAULT_REGISTRY: tuple[GuardProbe, ...] = (
    *_MATRICULA_PROBES,
    _RUIDO_SHAPE_PROBE,
    _ACAO_CHECK_PROBE,
    *_ABERTURA_PROBES,
    _ABERTURA_UNIQUE_PROBE,
    _ENDERECO_REGISTRO_PROBE,
    _ULTIMA_TRANSFERENCIA_MANUAL_PROBE,
    _ULTIMA_TRANSFERENCIA_MANUAL_NATUREZA_PROBE,
    _ULTIMA_TRANSFERENCIA_MANUAL_NATUREZA_REQUER_DATA_PROBE,
    _ULTIMA_TRANSFERENCIA_MANUAL_EXCLUSIVA_PROBE,
    _EMPREENDIMENTO_MANUAL_PROBE,
    _STORAGE_BUCKETS_PROBE,
    _INTERESSADOS_EMAIL_UNIQUE_PROBE,
    _CERTIDAO_CONSULTA_ORIGEM_PROBE,
    *_AGENTS_STUDIO_PROBES,
    _ESTRUTURA_STATUS_PROBE,
    _IMOVEL_CONFLITO_ABERTO_PROBE,
    *_IGIG_PROBES,
    *_CORE_AUDIT_LOGS_PROBES,
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
