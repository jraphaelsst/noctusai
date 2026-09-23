"""Tests for ``noctus.dev.verify_db_guards`` — executable proof that a
declared database guard actually REFUSES what it claims to refuse.

All tests are fully hermetic — a scripted ``_CannedExecutor`` (no real
Supabase calls), matching the ``SqlExecutor`` Protocol+Fake+Real DI seam
``noctus.dev.migrate_product`` establishes. No monkey-patching of our own
code (per ``KB § PATTERNS/compliance/testing.md``).

The runner's classification is ENTIRELY driven by the sentinel text a
probe's SQL would raise INSIDE Postgres (``NOC_PROBE:<outcome>: ...``) —
so these tests exercise the runner by scripting exactly that text back
from the executor, the same way a real Management-API HTTP error would
surface it. This is what makes the negative control meaningful: it does
not require a real database at all, only a faithful stand-in for what
Postgres would have said.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "seed" / "lib" / "backend"))

from tools.noctus.dev.verify_db_guards import (  # noqa: E402
    DEFAULT_REGISTRY,
    REGISTERED_GUARD_NAMES,
    GuardProbe,
    run_probe,
    verify_db_guards,
    wrap_rollback_only,
)


class _CannedExecutor:
    """Returns a FIXED canned result for every ``execute()`` call,
    regardless of the SQL text — sufficient here because a probe's
    outcome is entirely determined by what Postgres WOULD have raised,
    which these tests script directly rather than re-deriving from SQL
    text."""

    def __init__(self, *, ok: bool, error: str | None = None, rows: list[dict] | None = None):
        self.ok = ok
        self.error = error
        self.rows = rows if rows is not None else []
        self.executed: list[str] = []

    def execute(self, sql: str) -> dict:
        self.executed.append(sql)
        return {"ok": self.ok, "rows": self.rows, "error": self.error}


_ANY_PROBE = GuardProbe(
    id="fixture.probe",
    product="fixture-product",
    schema="fixture_schema",
    guard_name="fixture_guard",
    kind="write_refusal",
    migrations=("000_fixture.sql",),
    rationale="a fixture probe for these tests",
    sql="DO $noc_probe$\nBEGIN\n  RAISE EXCEPTION 'NOC_PROBE:refused: fixture';\nEND;\n$noc_probe$;",
)


# ---------------------------------------------------------------------------
# wrap_rollback_only — the structural seam
# ---------------------------------------------------------------------------


class TestWrapRollbackOnly:
    def test_sandwiches_begin_and_rollback(self):
        wrapped = wrap_rollback_only(_ANY_PROBE.sql)
        lines = wrapped.strip().splitlines()
        assert lines[0] == "BEGIN;"
        assert lines[-1] == "ROLLBACK;"

    def test_never_emits_a_bare_commit(self):
        """No probe run through this wrapper can ever contain COMMIT —
        this is the module's own emitter, and it literally does not have
        the string 'COMMIT' anywhere in its vocabulary."""
        wrapped = wrap_rollback_only(_ANY_PROBE.sql)
        assert "COMMIT" not in wrapped.upper()

    def test_refuses_empty_sql(self):
        import pytest

        with pytest.raises(ValueError):
            wrap_rollback_only("")

    def test_refuses_a_probe_that_is_not_exactly_one_do_block(self):
        """A probe body that tries to smuggle a second top-level statement
        alongside the DO block (e.g. its own explicit COMMIT) is refused
        BEFORE it ever reaches the database — the static half of the
        rollback-only guarantee."""
        import pytest

        sneaky = _ANY_PROBE.sql + "\nCOMMIT;"
        with pytest.raises(ValueError):
            wrap_rollback_only(sneaky)

    def test_refuses_sql_missing_the_probe_tag(self):
        import pytest

        with pytest.raises(ValueError):
            wrap_rollback_only("SELECT 1;")

    def test_every_registry_probe_wraps_cleanly(self):
        """Every probe actually shipped in DEFAULT_REGISTRY is built via
        the shared `_do_block` constructor and wraps without error — this
        would fail loudly for any registry entry hand-assembled outside
        that seam."""
        for probe in DEFAULT_REGISTRY:
            wrapped = wrap_rollback_only(probe.sql)
            assert wrapped.startswith("BEGIN;\n")
            assert wrapped.rstrip().endswith("ROLLBACK;")
            assert "COMMIT" not in wrapped.upper()


# ---------------------------------------------------------------------------
# run_probe — classification from the sentinel channel
# ---------------------------------------------------------------------------


class TestRunProbeClassification:
    def test_refused_is_a_pass(self):
        ex = _CannedExecutor(ok=False, error="ERROR: NOC_PROBE:refused: guard fired as expected")
        result = run_probe(_ANY_PROBE, ex)
        assert result["status"] == "pass"
        assert result["outcome"] == "refused"
        assert result["severity"] is None

    def test_clean_state_assertion_is_a_pass(self):
        ex = _CannedExecutor(ok=False, error="NOC_PROBE:clean: 0 public buckets")
        result = run_probe(_ANY_PROBE, ex)
        assert result["status"] == "pass"
        assert result["outcome"] == "clean"

    def test_permitted_is_a_high_severity_finding(self):
        """THE core case: the guard did NOT fire. This must never read as
        a pass."""
        ex = _CannedExecutor(ok=False, error="ERROR: NOC_PROBE:permitted: UPDATE succeeded, guard did not fire")
        result = run_probe(_ANY_PROBE, ex)
        assert result["status"] == "finding"
        assert result["outcome"] == "permitted"
        assert result["severity"] == "high"

    def test_allowed_is_a_pass(self):
        """The `write_allowed` (migration 165) inverse-polarity pair:
        success is the pass."""
        ex = _CannedExecutor(ok=False, error="ERROR: NOC_PROBE:allowed: UPDATE succeeded, sanctioned edit let through")
        result = run_probe(_ANY_PROBE, ex)
        assert result["status"] == "pass"
        assert result["outcome"] == "allowed"
        assert result["severity"] is None

    def test_blocked_is_a_high_severity_finding(self):
        """THE core case for a write_allowed probe: the guard fired on a
        SANCTIONED write. This must never read as a pass."""
        ex = _CannedExecutor(ok=False, error="ERROR: NOC_PROBE:blocked: texto_extraido não pode ser alterado")
        result = run_probe(_ANY_PROBE, ex)
        assert result["status"] == "finding"
        assert result["outcome"] == "blocked"
        assert result["severity"] == "high"

    def test_violation_state_assertion_is_a_critical_finding(self):
        ex = _CannedExecutor(ok=False, error="NOC_PROBE:violation: 2 public bucket(s) found")
        result = run_probe(_ANY_PROBE, ex)
        assert result["status"] == "finding"
        assert result["outcome"] == "violation"
        assert result["severity"] == "critical"

    def test_no_fixture_is_a_failure_never_a_skip(self):
        ex = _CannedExecutor(ok=False, error="NOC_PROBE:no_fixture: no row matching predicate")
        result = run_probe(_ANY_PROBE, ex)
        assert result["status"] == "failure"
        assert result["outcome"] == "no_fixture"

    def test_ambiguous_is_a_failure(self):
        """The wrong exception fired (not the guard under test) — this
        must not be misread as a refusal."""
        ex = _CannedExecutor(ok=False, error="NOC_PROBE:ambiguous: unrelated FK violation")
        result = run_probe(_ANY_PROBE, ex)
        assert result["status"] == "failure"
        assert result["outcome"] == "ambiguous"

    def test_unclassifiable_executor_error_is_a_failure(self):
        """A connectivity/HTTP error with no NOC_PROBE sentinel at all —
        the probe never even ran. Fail-closed, never a silent pass."""
        ex = _CannedExecutor(ok=False, error="HTTP 503 Service Unavailable")
        result = run_probe(_ANY_PROBE, ex)
        assert result["status"] == "failure"
        assert result["outcome"] is None

    def test_ok_true_with_no_sentinel_is_a_failure(self):
        """Every probe body raises on every branch (see module docstring)
        — an `ok=True` response means our own classification logic never
        ran. Silence must never be treated as a pass."""
        ex = _CannedExecutor(ok=True, rows=[])
        result = run_probe(_ANY_PROBE, ex)
        assert result["status"] == "failure"

    def test_malformed_probe_sql_is_refused_before_execution(self):
        bad_probe = GuardProbe(
            id="bad.probe",
            product="fixture-product",
            schema="fixture_schema",
            guard_name="bad_guard",
            kind="write_refusal",
            migrations=(),
            rationale="malformed on purpose",
            sql="SELECT 1;",  # not a DO $noc_probe$ block
        )
        ex = _CannedExecutor(ok=True)
        result = run_probe(bad_probe, ex)
        assert result["status"] == "failure"
        assert ex.executed == []  # never even reached the executor


# ---------------------------------------------------------------------------
# 🔴 Negative control — the classifier must FAIL a stubbed-to-permit guard.
# ---------------------------------------------------------------------------


class TestNegativeControl:
    def test_a_guard_stubbed_to_permit_is_never_reported_as_pass(self):
        """The meta-test: if the underlying guard logic were broken and
        silently permitted the forbidden write, this MUST NOT come back
        as status=pass. A probe/runner pair that can't fail here is the
        exact bug this tool exists to catch."""
        stubbed_permit = _CannedExecutor(
            ok=False,
            error=(
                "ERROR: NOC_PROBE:permitted: UPDATE "
                "social_wiring.matricula_extracoes.ruido for id=<uuid> "
                "succeeded — the write-once guard did not fire"
            ),
        )
        result = run_probe(DEFAULT_REGISTRY[0], stubbed_permit)
        assert result["status"] != "pass"
        assert result["status"] == "finding"
        assert result["severity"] == "high"


# ---------------------------------------------------------------------------
# The rollback property — nothing persists regardless of outcome.
# ---------------------------------------------------------------------------


class TestRollbackProperty:
    def test_every_probe_call_is_exactly_one_execute_and_always_carries_rollback(self):
        """Whatever the outcome, run_probe never issues more than the ONE
        wrapped statement per probe — the same statement that always ends
        in ROLLBACK; — so there is no second, unguarded call where a
        commit could sneak in."""
        for outcome_error in (
            "NOC_PROBE:refused: x",
            "NOC_PROBE:permitted: x",
            "NOC_PROBE:no_fixture: x",
        ):
            ex = _CannedExecutor(ok=False, error=outcome_error)
            run_probe(_ANY_PROBE, ex)
            assert len(ex.executed) == 1
            assert ex.executed[0].strip().startswith("BEGIN;")
            assert ex.executed[0].strip().endswith("ROLLBACK;")


# ---------------------------------------------------------------------------
# verify_db_guards — top-level aggregation + fail-closed posture
# ---------------------------------------------------------------------------


class TestVerifyDbGuards:
    def test_not_configured_when_no_executor_resolves(self, monkeypatch):
        """`executor=None` with no credentials resolvable -> not_configured,
        never a silent skip. Ambient-env absence is NOT enough to assert
        this hermetically: within the full test-suite process, an earlier
        test file's `configure_credentials(...)` call (real repo `.env`
        Supabase creds, used legitimately elsewhere) can leave the DB-first
        credential tier ABLE to resolve a real PAT for THIS test too — which
        would make `make_sql_executor()` return a REAL executor and this
        test's probe SQL would run against live production. Caught live
        2026-09-18: the full `mcp/noctusai/tests/` sweep actually executed
        `_ANY_PROBE`'s trivial fixture SQL against
        nyplttplcoyiiqjrvtiw.supabase.co (harmlessly — the wrap_rollback_only
        guarantee held — but a test must never depend on that for its own
        hermeticity). Same external-seam neutralization
        `test_check_storage_no_public_buckets.py` /
        `test_ensure_schema_exposure.py` / `test_migrate_product.py` use.
        """
        monkeypatch.delenv("SUPABASE_ACCESS_TOKEN", raising=False)
        monkeypatch.setattr(
            "noctusai_lib.config.credentials.resolve_credential",
            lambda *a, **k: None,
        )
        result = verify_db_guards(executor=None, registry=(_ANY_PROBE,))
        assert result["status"] == "not_configured"
        assert result["ok"] is False

    def test_empty_registry_is_an_error_not_a_silent_clean(self):
        result = verify_db_guards(executor=_CannedExecutor(ok=False, error="NOC_PROBE:refused: x"), registry=())
        assert result["status"] == "error"

    def test_all_pass_is_clean(self):
        ex = _CannedExecutor(ok=False, error="NOC_PROBE:refused: fixture")
        result = verify_db_guards(executor=ex, registry=(_ANY_PROBE,))
        assert result["status"] == "clean"
        assert result["ok"] is True
        assert result["checked"] == 1
        assert result["findings"] == []
        assert result["failures"] == []

    def test_one_finding_blocks_even_with_others_passing(self):
        class _SequencedExecutor:
            def __init__(self, responses):
                self._responses = list(responses)
                self.executed = []

            def execute(self, sql):
                self.executed.append(sql)
                return self._responses.pop(0)

        ex = _SequencedExecutor(
            [
                {"ok": False, "rows": None, "error": "NOC_PROBE:refused: x"},
                {"ok": False, "rows": None, "error": "NOC_PROBE:permitted: x"},
            ]
        )
        second_probe = GuardProbe(
            id="fixture.probe.2",
            product="fixture-product",
            schema="fixture_schema",
            guard_name="fixture_guard_2",
            kind="write_refusal",
            migrations=(),
            rationale="a second fixture probe",
            sql=_ANY_PROBE.sql,
        )
        result = verify_db_guards(executor=ex, registry=(_ANY_PROBE, second_probe))
        assert result["status"] == "violations_found"
        assert result["ok"] is False
        assert len(result["findings"]) == 1
        assert result["findings"][0]["guard_name"] == "fixture_guard_2"

    def test_a_failure_with_no_findings_is_unverified_not_clean(self):
        ex = _CannedExecutor(ok=False, error="NOC_PROBE:no_fixture: nothing to test against")
        result = verify_db_guards(executor=ex, registry=(_ANY_PROBE,))
        assert result["status"] == "unverified"
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# Registry sanity — every seeded probe is well-formed.
# ---------------------------------------------------------------------------


class TestSelfProvisioning:
    """2026-09-19: the matricula_extracoes frozen-column probes moved from
    a dynamic-fixture design (search for an existing row matching a
    predicate) to self-provisioning (INSERT their own specimen row(s))
    after a live prod run showed `codigo`/`imovel_documento_id` reporting
    a PERMANENT `no_fixture` — zero matching rows in prod, a state that
    was never going to change, which would have made `predeploy_check`'s
    `db_guards` leg permanently red for a reason unrelated to
    correctness. These tests pin that every frozen-column probe is
    self-provisioning by construction, not by accident."""

    def _matricula_frozen_column_probes(self):
        return [
            p for p in DEFAULT_REGISTRY
            if p.guard_name == "matricula_extracoes_protege_concluida"
        ]

    def test_every_frozen_column_probe_inserts_its_own_specimen_row(self):
        probes = self._matricula_frozen_column_probes()
        # 6 pre-165 (texto_extraido, codigo, imovel_documento_id,
        # arquivo_origem_id, substituida_por, ruido) + 2 from migration 165
        # (the boilerplate-only deletion, both the allowed and the
        # still-refused directions).
        assert len(probes) == 8
        for probe in probes:
            assert "INSERT INTO social_wiring.matricula_extracoes" in probe.sql, (
                f"{probe.id} does not self-provision a matricula_extracoes row"
            )

    def test_codigo_probe_self_provisions_its_fk_target(self):
        probe = next(p for p in DEFAULT_REGISTRY if p.id == "matricula_extracoes.codigo.frozen_after_set")
        assert "INSERT INTO social_wiring.imovel_registry" in probe.sql

    def test_imovel_documento_id_probe_self_provisions_its_full_fk_chain(self):
        probe = next(
            p for p in DEFAULT_REGISTRY
            if p.id == "matricula_extracoes.imovel_documento_id.frozen_after_set"
        )
        assert "INSERT INTO social_wiring.imovel_registry" in probe.sql
        assert "INSERT INTO social_wiring.imoveis" in probe.sql
        assert "INSERT INTO social_wiring.imovel_documentos" in probe.sql

    def test_arquivo_origem_id_probe_self_provisions_its_fk_target(self):
        probe = next(
            p for p in DEFAULT_REGISTRY
            if p.id == "matricula_extracoes.arquivo_origem_id.frozen_after_set"
        )
        assert "INSERT INTO social_wiring.matricula_extracao_arquivos" in probe.sql

    def test_substituida_por_probe_self_provisions_both_of_its_own_rows(self):
        probe = next(
            p for p in DEFAULT_REGISTRY
            if p.id == "matricula_extracoes.substituida_por.frozen_after_set"
        )
        # Two INSERTs into matricula_extracoes: the superseded row, then
        # the row under test — self-referential, no other table involved.
        assert probe.sql.count("INSERT INTO social_wiring.matricula_extracoes") == 2

    def test_the_only_remaining_no_fixture_dependency_is_the_org_id_borrow(self):
        """Every frozen-column probe's `no_fixture` branch fires ONLY for
        the shared org_id borrow — never for a column-specific ambient
        predicate (the exact shape that broke live)."""
        for probe in self._matricula_frozen_column_probes():
            assert "no existing social_wiring.matricula_extracoes row to borrow an org_id from" in probe.sql


class TestRegistrySanity:
    def test_registry_is_non_empty(self):
        assert len(DEFAULT_REGISTRY) >= 10

    def test_every_probe_has_a_registered_guard_name(self):
        for probe in DEFAULT_REGISTRY:
            assert probe.guard_name in REGISTERED_GUARD_NAMES

    def test_probe_ids_are_unique(self):
        ids = [p.id for p in DEFAULT_REGISTRY]
        assert len(ids) == len(set(ids))

    def test_every_probe_sql_contains_a_no_fixture_or_needs_no_fixture(self):
        """Every write_refusal / (fixture-dependent) probe declares an
        explicit no_fixture escape hatch; the platform-wide state
        assertion needs none (nothing is fixture-dependent about reading
        storage.buckets)."""
        for probe in DEFAULT_REGISTRY:
            if probe.kind == "state_assertion":
                continue
            assert "no_fixture" in probe.sql

    def test_every_probe_ends_in_a_sentinel_raising_branch_for_permitted(self):
        """Every probe's 'the guard misbehaved' branch raises a
        recognised sentinel — `permitted`/`violation` for the
        write_refusal/state_assertion pair, or `blocked` for the
        INVERSE-polarity `write_allowed` kind (migration 165), where the
        guard misbehaving means it wrongly refused a sanctioned write."""
        for probe in DEFAULT_REGISTRY:
            assert (
                "NOC_PROBE:permitted" in probe.sql
                or "NOC_PROBE:violation" in probe.sql
                or "NOC_PROBE:blocked" in probe.sql
            )

    def test_every_probe_wrapped_sql_parses_as_exactly_three_statements(self):
        """Structural sanity check (statement-count only — see the NEXT
        test for the actual quote-escaping regression guard, and its
        docstring for why THIS check alone would not have caught that
        bug): `noctusai_lib.testing.migration_parser._walk_statements`
        (the same dollar-quote/string-aware splitter
        `check_migration_guard_has_probe` uses) must see every wrapped
        probe as exactly `BEGIN;` / one DO block / `ROLLBACK;`. This DOES
        catch a different malformation class — an unbalanced dollar-tag,
        an unclosed paren, a stray top-level `;` outside any string —
        just not a Postgres-GRAMMAR-level defect inside an otherwise
        lexically-balanced string (the walker tracks quote/paren
        NESTING, not RAISE EXCEPTION's own argument grammar)."""
        from noctusai_lib.testing.migration_parser import _walk_statements

        for probe in DEFAULT_REGISTRY:
            wrapped = wrap_rollback_only(probe.sql)
            stmts = [s for s in _walk_statements(wrapped) if s.strip()]
            assert len(stmts) == 3, (
                f"{probe.id}: expected exactly 3 statements "
                f"(BEGIN;/DO block/ROLLBACK;), got {len(stmts)}: {stmts}"
            )
            assert stmts[0].strip() == "BEGIN;", probe.id
            assert stmts[1].strip().startswith("DO $noc_probe$"), probe.id
            assert stmts[2].strip() == "ROLLBACK;", probe.id

    def test_a_predicate_containing_a_quote_round_trips_through_the_shape_helpers(self):
        """THE actual regression test for the 2026-09-18 quote-escaping
        bug (caught live against prod, not by any test before this one).

        🔴 Verified by hand that the PRECEDING test (statement-count via
        `_walk_statements`) does NOT catch this bug and must not be
        mistaken for doing so: `status = 'concluida'` contributes an
        EVEN number of embedded quotes (one open, one close) to the
        message literal, so the walker's naive quote-toggle counting
        nets back to "not in a string" at the same point regardless of
        whether the escape ran — it still sees exactly one DO block,
        because splitting on TOP-LEVEL statement boundaries doesn't need
        the walker to understand RAISE EXCEPTION's own argument grammar.
        Postgres's real parser does need that, and rejects
        `'...literal1' concluida] to probe...'literal2'` as a malformed
        argument list — a defect this offline tool structurally cannot
        see. This test instead asserts the one thing that DOES prove the
        fix: the ESCAPED form (a doubled quote) must be the literal text
        `_sql_lit` produced, landing inside the rendered SQL. That
        assertion fails against the pre-fix generator (confirmed by hand
        against the actual pre-fix source before writing this test) and
        passes against the fixed one — the negative control this
        methodology requires of every guard-shaped check.
        """
        from tools.noctus.dev.verify_db_guards import (
            _frozen_column_probe,
            _insert_check_probe,
        )

        quoted_predicate = "status = 'concluida'"
        frozen_sql = _frozen_column_probe(
            schema="s", table="t", column="c",
            fixture_predicate=quoted_predicate,
            bad_value_sql="'x'",
            guard_fragment="cannot 'change' this",
        )
        # The escaped form (doubled quote) must appear in the rendered
        # SQL — proof the predicate's text actually reached the message
        # through `_sql_lit`, not merely that no error was raised.
        assert "status = ''concluida''" in frozen_sql
        # And the RAW (single-quote) form must NOT appear inside the
        # no_fixture message — that shape is exactly the pre-fix defect.
        assert "matching [status = 'concluida']" not in frozen_sql

        insert_sql = _insert_check_probe(
            schema="s", table="t", columns_sql="a, b", values_sql="1, 2",
            fixture_from="s.t",
            fixture_description="no row matching status = 'concluida' here",
            guard_fragment='constraint "it\'s a test"',
        )
        assert "status = ''concluida''" in insert_sql
        assert "matching status = 'concluida' here" not in insert_sql

    def test_run_probe_result_carries_both_id_and_probe_id(self):
        """2026-09-18: an external runner reading a bare `id` field printed
        `?` for every probe because run_probe only ever returned
        `probe_id`. Both keys must carry the same value."""
        ex = _CannedExecutor(ok=False, error="NOC_PROBE:refused: fixture")
        result = run_probe(_ANY_PROBE, ex)
        assert result["id"] == _ANY_PROBE.id
        assert result["probe_id"] == _ANY_PROBE.id


class TestAgentsStudioProbes:
    """Migrations 012 + 013 (agents Agent Studio) — one self-provisioning
    probe per guard object `check_migration_guard_has_probe` detects in
    those files, plus the extra refusal paths the wave-1 security review
    asked to prove (published DELETE, child DELETE, substituida -> ativa,
    compiled_prompts DELETE)."""

    _GUARDS = {
        "agent_versions_one_ativa_idx",
        "agent_versions_one_rascunho_idx",
        "guard_agent_version_immutable",
        "guard_version_child_immutable",
        "guard_skill_file_immutable",
        "guard_compiled_prompt_immutable",
        "guard_audit_log_append_only",
        "guard_client_entry_cap",
        "agents_publicacao_limiar_floor",
        "agent_versions_override_reason_len",
        "eval_runs_one_active_per_version_idx",
        "eval_results_status_check",
        "eval_runs_modelo_geracao_check",
        "eval_runs_limite_usd_check",
        "agent_personas_model_check",
        "agent_versions_model_check",
    }
    _MIGRATIONS = {
        ("012_agent_studio_definitions.sql",),
        ("013_agent_studio_knowledge_evals.sql",),
        ("013_agent_studio_knowledge_evals.sql", "014_agent_studio_cost.sql"),
        ("006_agents.sql", "015_haiku_model.sql"),
        ("012_agent_studio_definitions.sql", "015_haiku_model.sql"),
    }

    @staticmethod
    def _probes():
        return [p for p in DEFAULT_REGISTRY if p.product == "agents"]

    def test_every_studio_guard_has_a_probe(self):
        assert {p.guard_name for p in self._probes()} == self._GUARDS

    def test_every_detected_guard_in_012_to_014_is_registered(self):
        from tools.noctus.dev.compliance import _detect_guard_objects

        root = Path(__file__).resolve().parents[3] / "products" / "agents" / "backend" / "migrations"
        for name in ("012_agent_studio_definitions.sql", "013_agent_studio_knowledge_evals.sql", "014_agent_studio_cost.sql"):
            detected = {g["guard_name"] for g in _detect_guard_objects((root / name).read_text())}
            assert detected <= self._GUARDS, (name, detected - self._GUARDS)

    def test_review_refusal_paths_are_probed(self):
        ids = {p.id for p in self._probes()}
        assert {
            "agent_versions.published_delete_refused",
            "agent_versions.substituida_to_ativa_refused",
            "agent_prompt_sections.child_delete_under_published_parent",
            "compiled_prompts.delete_refused",
            "agents.publicacao_limiar_floor",
            "agent_versions.override_reason_len",
        } <= ids

    def test_probes_self_provision_and_borrow_nothing(self):
        for p in self._probes():
            assert "gen_random_uuid()" in p.sql, p.id
            assert "INSERT INTO agents.agents" in p.sql, p.id
            assert "SELECT org_id" not in p.sql, p.id  # never borrows a real org
            assert "to_regclass('agents.agent_versions')" in p.sql, p.id
            assert p.migrations in self._MIGRATIONS, p.id

    def test_schema_constant_is_declared_once(self):
        src = (Path(__file__).resolve().parents[1] / "tools" / "noctus" / "dev" / "verify_db_guards.py").read_text()
        assert src.count('_AGENTS_SCHEMA = "agents"') == 1

    def test_probe_bodies_parse_as_plpgsql(self):
        parser = pytest.importorskip("pglast.parser")
        for p in self._probes():
            parser.parse_plpgsql_json(p.sql.replace("DO $noc_probe$", "CREATE FUNCTION f() RETURNS void LANGUAGE plpgsql AS $noc_probe$", 1))


class TestIgigCrmProbes:
    """igig CRM foundation (017/018/019 + the 006/010 guards whose SQLite
    mirrors that change touched): every detected guard is probed, and every
    probe fabricates its own rows (no production data borrowed)."""

    _ROOT = Path(__file__).resolve().parents[3] / "products" / "igig" / "backend" / "migrations"

    @staticmethod
    def _probes():
        return [p for p in DEFAULT_REGISTRY if p.product == "igig"]

    def test_every_detected_guard_in_017_to_020_is_registered(self):
        from tools.noctus.dev.compliance import _detect_guard_objects

        registered = {p.guard_name for p in self._probes()}
        for name in ("017_igig_pipeline.sql", "018_igig_crm.sql", "019_card_hub.sql",
                     "020_igig_orcamentos.sql"):
            detected = {g["guard_name"] for g in _detect_guard_objects((self._ROOT / name).read_text())}
            assert detected and detected <= registered, (name, detected - registered)

    def test_the_touched_pre_017_guards_are_probed_too(self):
        registered = {p.guard_name for p in self._probes()}
        assert {"idx_igig_apontamento_aberto", "idx_igig_integracao_canal"} <= registered

    def test_every_probe_migration_file_exists(self):
        for p in self._probes():
            for m in p.migrations:
                assert (self._ROOT / m).is_file(), (p.id, m)

    def test_probes_self_provision_and_borrow_nothing(self):
        for p in self._probes():
            assert "v_org uuid := gen_random_uuid()" in p.sql, p.id
            assert "SELECT org_id" not in p.sql, p.id
            assert "to_regclass('igig.negocio')" in p.sql, p.id
            assert f"'%{p.guard_name}%'" in p.sql, p.id

    def test_probe_bodies_parse_as_plpgsql(self):
        parser = pytest.importorskip("pglast.parser")
        for p in self._probes():
            parser.parse_plpgsql_json(p.sql.replace(
                "DO $noc_probe$", "CREATE FUNCTION f() RETURNS void LANGUAGE plpgsql AS $noc_probe$", 1
            ))
