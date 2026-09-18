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
    row-level guard to raise. Dynamic fixture (`fixture_predicate`) — never
    a fabricated row — because these columns carry real FK/semantic
    weight (`codigo`, `imovel_documento_id`, ...) that a synthetic row
    cannot safely satisfy. No fixture found -> `no_fixture` (a FAILURE,
    never a skip). The guard fires inside a `BEFORE UPDATE` trigger,
    which runs BEFORE Postgres validates any FK/CHECK on the new row
    value, so `bad_value_sql` need not itself be a valid value — but
    classification still checks `guard_fragment` against the caught
    `SQLERRM`, so a value that (surprisingly) trips a DIFFERENT
    constraint first is reported `ambiguous`, never a false `refused`.

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
)


def _matricula_probe(probe_id: str, column: str, fixture_predicate: str, bad_value_sql: str) -> GuardProbe:
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
            "the earlier columns."
        ),
        sql=_frozen_column_probe(
            schema=_SW_SCHEMA,
            table=_MATRICULA_TABLE,
            column=column,
            fixture_predicate=fixture_predicate,
            bad_value_sql=bad_value_sql,
            guard_fragment=_MATRICULA_GUARD_FRAGMENT,
        ),
    )


_MATRICULA_PROBES: tuple[GuardProbe, ...] = (
    _matricula_probe(
        "matricula_extracoes.texto_extraido.frozen_after_concluida",
        "texto_extraido",
        "status = 'concluida'",
        "'NOC-PROBE-' || gen_random_uuid()::text",
    ),
    _matricula_probe(
        "matricula_extracoes.codigo.frozen_after_set",
        "codigo",
        "codigo IS NOT NULL",
        "COALESCE(codigo, '') || '-noc-probe'",
    ),
    _matricula_probe(
        "matricula_extracoes.imovel_documento_id.frozen_after_set",
        "imovel_documento_id",
        "imovel_documento_id IS NOT NULL",
        "gen_random_uuid()",
    ),
    _matricula_probe(
        "matricula_extracoes.arquivo_origem_id.frozen_after_set",
        "arquivo_origem_id",
        "arquivo_origem_id IS NOT NULL",
        "gen_random_uuid()",
    ),
    _matricula_probe(
        "matricula_extracoes.substituida_por.frozen_after_set",
        "substituida_por",
        "substituida_por IS NOT NULL",
        "gen_random_uuid()",
    ),
    _matricula_probe(
        "matricula_extracoes.ruido.frozen_after_concluida",
        "ruido",
        "status = 'concluida'",
        "'[{\"start\":0,\"end\":1,\"kind\":\"noc_probe\"}]'::jsonb",
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


DEFAULT_REGISTRY: tuple[GuardProbe, ...] = (
    *_MATRICULA_PROBES,
    _RUIDO_SHAPE_PROBE,
    *_ABERTURA_PROBES,
    _ABERTURA_UNIQUE_PROBE,
    _STORAGE_BUCKETS_PROBE,
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
            "CHECK constraints + its (extracao_id, campo) UNIQUE index, and "
            "the platform-wide zero-public-storage-buckets state assertion. "
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
