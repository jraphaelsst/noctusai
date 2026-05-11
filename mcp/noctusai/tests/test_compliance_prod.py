"""Regression tests for the production-correctness keeper detector trio.

Surfaced by Engineer GG's therapy P4 audit (commit a56a39e, 2026-05-10).
Each detector pins a known-bad fixture and a known-good fixture so future
refactors can't silently regress the catch.

Per KB § PATTERNS/testing.md § Production-correctness keeper detectors +
KB § PATTERNS/testing.md § Regression-test-the-detector.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_unknown_table_references,
    check_function_search_path_pinned,
    check_admin_endpoint_service_role_bypass,
)


def _mk_product(
    *,
    migrations: dict[str, str] | None = None,
    app_files: dict[str, str] | None = None,
) -> Path:
    """Build a fake product tree under a temp dir.

    `migrations` maps `<file_name>.sql` → contents.
    `app_files` maps `<relative path under backend/app/>` → contents.

    Both default to empty mappings. The fixture mirrors the real shape:
        <tmp>/backend/migrations/*.sql
        <tmp>/backend/app/**/*.py
    """
    root = Path(tempfile.mkdtemp(prefix="compliance_prod_test_"))
    (root / "backend" / "migrations").mkdir(parents=True)
    (root / "backend" / "app").mkdir(parents=True)
    for fname, body in (migrations or {}).items():
        (root / "backend" / "migrations" / fname).write_text(body)
    for rel, body in (app_files or {}).items():
        target = root / "backend" / "app" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    return root


class TestCheckUnknownTableReferences:
    """Detector for `.table("X")` callsites where X is not declared by any
    `CREATE TABLE` in the product's migrations.

    Pins the Engineer GG therapy P4 N=12 drift shape.
    """

    def test_known_table_is_clean(self):
        """Reference to a table that IS declared → no issue."""
        product = _mk_product(
            migrations={
                "001_init.sql": (
                    "CREATE TABLE IF NOT EXISTS therapy.patient_profiles ("
                    "  id UUID PRIMARY KEY"
                    ");\n"
                )
            },
            app_files={
                "services/auth_service.py": (
                    "def register():\n"
                    "    admin_db.table('patient_profiles').insert({}).execute()\n"
                )
            },
        )
        assert check_unknown_table_references(product) == []

    def test_unknown_table_is_flagged(self):
        """Reference to a table NOT declared → warning."""
        product = _mk_product(
            migrations={
                "001_init.sql": (
                    "CREATE TABLE IF NOT EXISTS therapy.platform_commission_overrides ("
                    "  id UUID PRIMARY KEY"
                    ");\n"
                )
            },
            app_files={
                # The therapy P4 drift: code says `commission_overrides`,
                # migration says `platform_commission_overrides`.
                "services/admin_service.py": (
                    "def list_overrides(db):\n"
                    "    return db.table('commission_overrides').select('*').execute()\n"
                )
            },
        )
        issues = check_unknown_table_references(product)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert issues[0]["table"] == "commission_overrides"
        assert "services/admin_service.py" in issues[0]["file"]

    def test_external_tables_allowlisted(self):
        """`auth.users` style external tables → not flagged."""
        product = _mk_product(
            migrations={"001_init.sql": "CREATE TABLE therapy.x ( id UUID );"},
            app_files={
                "deps.py": (
                    "def lookup(db):\n"
                    "    return db.table('users').select('*').execute()\n"
                )
            },
        )
        assert check_unknown_table_references(product) == []

    def test_no_migrations_short_circuits(self):
        """Product with no migrations → no false flags."""
        root = Path(tempfile.mkdtemp(prefix="compliance_prod_no_mig_"))
        (root / "backend" / "app").mkdir(parents=True)
        (root / "backend" / "app" / "x.py").write_text(
            "db.table('anything').select('*').execute()\n"
        )
        assert check_unknown_table_references(root) == []

    def test_non_constant_arg_skipped(self):
        """`.table(f'{x}_foo')` or `.table(var)` → silently skipped (can't
        resolve statically; false-positive avoidance)."""
        product = _mk_product(
            migrations={"001_init.sql": "CREATE TABLE therapy.t ( id UUID );"},
            app_files={
                "x.py": (
                    "def f(db, tname):\n"
                    "    db.table(tname).select('*').execute()\n"
                    "    db.table(f'{tname}_log').select('*').execute()\n"
                )
            },
        )
        assert check_unknown_table_references(product) == []

    def test_schema_chained_table_call_is_skipped(self):
        """`db.schema("erp").table("X")` → not flagged even if X is not in
        local migrations (X lives in a foreign product's migration tree).

        Canonical site: `core/admin_llm_usage.py:92` where the platform-admin
        endpoint iterates `_PRODUCT_SCHEMAS` and calls
        `db.schema(schema).table("llm_usage")`. See `_has_schema_in_chain`
        for the heuristic-limit rationale.
        """
        product = _mk_product(
            migrations={
                "001_init.sql": (
                    "CREATE TABLE IF NOT EXISTS core.noctus_users ( id UUID );\n"
                )
            },
            app_files={
                "routers/admin_llm_usage.py": (
                    "def aggregate(db):\n"
                    "    rows = db.schema('erp').table('llm_usage').select('*').execute()\n"
                    "    return rows\n"
                )
            },
        )
        assert check_unknown_table_references(product) == []

    def test_dynamic_schema_chain_is_skipped(self):
        """`db.schema(var).table("X")` → not flagged. Detector cannot
        resolve `var` to a product slug at AST time; the chain itself
        signals cross-schema intent, so skip.
        """
        product = _mk_product(
            migrations={
                "001_init.sql": (
                    "CREATE TABLE IF NOT EXISTS core.noctus_users ( id UUID );\n"
                )
            },
            app_files={
                "routers/admin_llm_usage.py": (
                    "def aggregate(db):\n"
                    "    for slug, schema in [('erp', 'erp'), ('therapy', 'therapy')]:\n"
                    "        rows = db.schema(schema).table('llm_usage').select('*').execute()\n"
                    "    return rows\n"
                )
            },
        )
        assert check_unknown_table_references(product) == []

    def test_no_schema_chain_still_flags_unknown(self):
        """Regression guard — the schema-chain skip MUST NOT mask bare
        `db.table('unknown_table')` calls (the original detector intent).
        """
        product = _mk_product(
            migrations={
                "001_init.sql": (
                    "CREATE TABLE IF NOT EXISTS core.noctus_users ( id UUID );\n"
                )
            },
            app_files={
                "routers/foo.py": (
                    "def bad(db):\n"
                    "    db.table('totally_made_up_table').select('*').execute()\n"
                )
            },
        )
        issues = check_unknown_table_references(product)
        assert len(issues) == 1
        assert issues[0]["table"] == "totally_made_up_table"


class TestCheckFunctionSearchPathPinned:
    """Detector for `CREATE FUNCTION` blocks missing `SET search_path`.

    Pins the Engineer GG therapy P4 `gcal_authorization_is_fresh` slip.
    """

    def test_pinned_search_path_is_clean(self):
        """Function with SET search_path = ... → no issue."""
        product = _mk_product(
            migrations={
                "001.sql": (
                    "CREATE OR REPLACE FUNCTION therapy.set_updated_at()\n"
                    "RETURNS TRIGGER\n"
                    "LANGUAGE plpgsql SECURITY DEFINER "
                    "SET search_path = therapy, public\n"
                    "AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;\n"
                )
            }
        )
        assert check_function_search_path_pinned(product) == []

    def test_missing_search_path_is_flagged(self):
        """Function without SET search_path → warning."""
        product = _mk_product(
            migrations={
                "011_scheduling.sql": (
                    "CREATE OR REPLACE FUNCTION therapy.gcal_authorization_is_fresh("
                    "authorized_at TIMESTAMPTZ)\n"
                    "RETURNS BOOLEAN\n"
                    "LANGUAGE sql\n"
                    "IMMUTABLE\n"
                    "AS $$\n"
                    "  SELECT authorized_at IS NOT NULL\n"
                    "     AND authorized_at > now() - INTERVAL '7 days';\n"
                    "$$;\n"
                )
            }
        )
        issues = check_function_search_path_pinned(product)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert "gcal_authorization_is_fresh" in issues[0]["function"]
        assert "011_scheduling.sql" in issues[0]["file"]

    def test_search_path_inside_body_is_accepted(self):
        """Function with SET search_path in the body (e.g. PERFORM
        set_config('search_path'...)) — only `SET search_path = ...`
        clause counts. We match the clause anywhere; placing it inside
        the body header (after AS) is legal and accepted."""
        product = _mk_product(
            migrations={
                "001.sql": (
                    "CREATE FUNCTION therapy.f() RETURNS void AS $$\n"
                    "BEGIN\n"
                    "  -- SET search_path = therapy, public;\n"
                    "  PERFORM 1;\n"
                    "END;\n"
                    "$$ LANGUAGE plpgsql SET search_path = therapy, public;\n"
                )
            }
        )
        assert check_function_search_path_pinned(product) == []

    def test_multiple_functions_independent(self):
        """A clean function and a broken function in same file → only
        the broken one flagged."""
        product = _mk_product(
            migrations={
                "001.sql": (
                    "CREATE FUNCTION therapy.clean()\n"
                    "RETURNS int LANGUAGE sql\n"
                    "SET search_path = therapy, public\n"
                    "AS $$ SELECT 1; $$;\n"
                    "\n"
                    "CREATE FUNCTION therapy.broken()\n"
                    "RETURNS int LANGUAGE sql\n"
                    "AS $$ SELECT 2; $$;\n"
                )
            }
        )
        issues = check_function_search_path_pinned(product)
        assert len(issues) == 1
        assert "broken" in issues[0]["function"]

    def test_no_migrations_short_circuits(self):
        """Product with no migrations → no issues."""
        root = Path(tempfile.mkdtemp(prefix="compliance_prod_fn_nomig_"))
        (root / "backend").mkdir(parents=True)
        assert check_function_search_path_pinned(root) == []


class TestCheckAdminEndpointServiceRoleBypass:
    """Detector for admin-client `.table("T")` callsites where T lacks a
    `service_role_bypass` policy in migrations.

    Pins the Engineer GG therapy P4 admin-RLS-hole shape.
    """

    def test_admin_client_with_bypass_policy_is_clean(self):
        """`get_admin_client().table('T')` + T has bypass policy → clean."""
        product = _mk_product(
            migrations={
                "001.sql": (
                    "CREATE TABLE IF NOT EXISTS therapy.patient_profiles ( id UUID );\n"
                    "ALTER TABLE therapy.patient_profiles ENABLE ROW LEVEL SECURITY;\n"
                    "CREATE POLICY \"service_role_bypass\" ON therapy.patient_profiles "
                    "FOR ALL TO service_role USING (true) WITH CHECK (true);\n"
                )
            },
            app_files={
                "routers/auth.py": (
                    "def register():\n"
                    "    admin_db = get_admin_client()\n"
                    "    admin_db.table('patient_profiles').insert({}).execute()\n"
                )
            },
        )
        assert check_admin_endpoint_service_role_bypass(product) == []

    def test_admin_client_without_bypass_is_flagged(self):
        """Admin client touches T but T has no service_role_bypass → warning."""
        product = _mk_product(
            migrations={
                "001.sql": (
                    "CREATE TABLE IF NOT EXISTS therapy.exposed_table ( id UUID );\n"
                    "ALTER TABLE therapy.exposed_table ENABLE ROW LEVEL SECURITY;\n"
                    "CREATE POLICY \"authenticated_access\" ON therapy.exposed_table "
                    "FOR ALL TO authenticated USING (true);\n"
                )
            },
            app_files={
                "services/admin_service.py": (
                    "def f():\n"
                    "    db = get_admin_client()\n"
                    "    db.table('exposed_table').select('*').execute()\n"
                )
            },
        )
        issues = check_admin_endpoint_service_role_bypass(product)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert issues[0]["table"] == "exposed_table"

    def test_chained_admin_call_detected(self):
        """`get_admin_client().table('T')` (no intermediate binding) → also caught."""
        product = _mk_product(
            migrations={
                "001.sql": (
                    "CREATE TABLE IF NOT EXISTS therapy.exposed ( id UUID );\n"
                )
            },
            app_files={
                "router.py": (
                    "def f():\n"
                    "    return get_admin_client().table('exposed').select('*').execute()\n"
                )
            },
        )
        issues = check_admin_endpoint_service_role_bypass(product)
        assert len(issues) == 1
        assert issues[0]["table"] == "exposed"

    def test_non_admin_table_call_not_flagged(self):
        """`db.table('T')` where `db` is NOT bound to `get_admin_client()` →
        not the admin-bypass detector's business (covered by
        `check_unknown_table_references` if T is unknown)."""
        product = _mk_product(
            migrations={"001.sql": "CREATE TABLE therapy.t ( id UUID );"},
            app_files={
                "router.py": (
                    "def f(db):\n"
                    "    db.table('t').select('*').execute()\n"
                )
            },
        )
        assert check_admin_endpoint_service_role_bypass(product) == []

    def test_external_tables_not_flagged(self):
        """`auth.users` style external tables → not flagged."""
        product = _mk_product(
            migrations={"001.sql": "CREATE TABLE therapy.t ( id UUID );"},
            app_files={
                "router.py": (
                    "def f():\n"
                    "    admin = get_admin_client()\n"
                    "    admin.table('users').select('*').execute()\n"
                )
            },
        )
        assert check_admin_endpoint_service_role_bypass(product) == []

    def test_no_migrations_short_circuits(self):
        """Product with no migrations → no issues."""
        root = Path(tempfile.mkdtemp(prefix="compliance_prod_admin_nomig_"))
        (root / "backend" / "app").mkdir(parents=True)
        assert check_admin_endpoint_service_role_bypass(root) == []

    def test_schema_chained_admin_call_is_skipped(self):
        """`admin_db.schema(X).table('T')` → not flagged. The bypass policy
        must live in X's migration tree, not this product's.

        Today the receiver-shape check (`Name`/`get_admin_client()`)
        already silently misses this site (receiver is a `Call`), but the
        explicit `_has_schema_in_chain` gate closes the gap structurally
        so a future receiver-shape refactor doesn't reintroduce the
        false positive.
        """
        product = _mk_product(
            migrations={
                "001.sql": (
                    "CREATE TABLE IF NOT EXISTS core.noctus_users ( id UUID );\n"
                )
            },
            app_files={
                "routers/admin_llm_usage.py": (
                    "def aggregate():\n"
                    "    admin_db = get_admin_client()\n"
                    "    for schema in ['erp', 'therapy']:\n"
                    "        admin_db.schema(schema).table('llm_usage').select('*').execute()\n"
                )
            },
        )
        assert check_admin_endpoint_service_role_bypass(product) == []

    def test_dashed_schema_bypass_policy_is_recognized(self):
        """`CREATE POLICY "service_role_bypass" ON "personal-finance".T`
        → counts as a bypass policy on table T. Dashed schemas MUST be
        double-quoted at DDL time per Postgres identifier rules.

        Pins the keeper-trio-pf finding (Engineer BBB, 2026-05-11):
        migration 009 applied live + `pg_policies` confirmed the policy
        but the detector kept flagging the callsite because the schema
        regex only matched unquoted identifiers
        (`[A-Za-z_][A-Za-z0-9_]*\\.`) — `"personal-finance".` failed.
        Without this test the regression silently reopens for every
        dashed-schema adopter (personal-finance, mailing).
        """
        product = _mk_product(
            migrations={
                "001.sql": (
                    "CREATE TABLE IF NOT EXISTS \"personal-finance\".recorrentes "
                    "( id UUID );\n"
                    "ALTER TABLE \"personal-finance\".recorrentes "
                    "ENABLE ROW LEVEL SECURITY;\n"
                    "CREATE POLICY \"service_role_bypass\" "
                    "ON \"personal-finance\".recorrentes "
                    "FOR ALL TO service_role USING (true) WITH CHECK (true);\n"
                )
            },
            app_files={
                "scheduler.py": (
                    "def run():\n"
                    "    db = get_admin_client()\n"
                    "    db.table('recorrentes').select('org_id').execute()\n"
                )
            },
        )
        assert check_admin_endpoint_service_role_bypass(product) == []
