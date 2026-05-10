"""
Structural (parse-based) tests for `migrations/027_erp_org_scoping_completion.sql`.

Filed by `projects/erp-org-scoping-completion/` Phase 2 (2026-05-10).

No database required — these tests read the SQL file and assert that the
expected RLS UPDATE policies carry both USING and WITH CHECK clauses on
``org_id``, and that the five foreign keys to ``public.organizations`` are
declared. They are the unit-test regression layer for the contract that
``027`` ships:

  * Cross-org UPDATE rejection (WITH CHECK closes the org_id-mutation gap).
  * Org-orphan rejection (FK to public.organizations).

Companion real-DB integration tests (cross-org RLS rejection at the
postgres layer) live in ``tests/realdb/test_org_scoping_realdb.py`` and
auto-skip without SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY.

Pattern lifted from ``tests/test_metas_migration.py`` (the canonical
structural-migration-test in this product). Pin every assertion to the
expected SQL contract so a typo / rename / accidental policy drop in
027 surfaces immediately.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "027_erp_org_scoping_completion.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.is_file(), f"Migration file missing at {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tables in scope
# ---------------------------------------------------------------------------

# Tables that get both UPDATE WITH CHECK and org_id FK.
TABLES_WITH_UPDATE_POLICY = [
    "eventos",
    "lancamentos",
    "site_config",
    "whatsapp_config",
]

# Tables that get the FK (incl. certidao_consultas which has its own RLS shape).
TABLES_WITH_ORG_FK = TABLES_WITH_UPDATE_POLICY + ["certidao_consultas"]


# ---------------------------------------------------------------------------
# Prelude — schema lock present
# ---------------------------------------------------------------------------

def test_schema_lock_present(sql):
    """The canonical schema-lock (per `noctusai_lib.sql.prelude`) is at the top."""
    pattern = r"SET\s+search_path\s*=\s*erp\s*,\s*public\s*;"
    assert re.search(pattern, sql), "Missing canonical schema-lock"


def test_prelude_comment_block_present(sql):
    """The canonical prelude comment block is present (catches drift from noctusai_lib.sql.prelude)."""
    assert "Schema lock — pin name resolution to erp, public" in sql, (
        "Migration missing canonical prelude comment block; "
        "should be authored via noctusai_lib.sql.prelude('erp')."
    )


# ---------------------------------------------------------------------------
# Part 1 — UPDATE policies have both USING and WITH CHECK on org_id
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("table", TABLES_WITH_UPDATE_POLICY)
def test_update_policy_dropped_then_recreated(sql, table):
    """Each UPDATE policy is dropped-if-exists then recreated (idempotent shape)."""
    drop_pattern = rf"DROP\s+POLICY\s+IF\s+EXISTS\s+{table}_update_policy\s+ON\s+erp\.{table}\s*;"
    assert re.search(drop_pattern, sql, re.IGNORECASE), (
        f"Missing DROP POLICY IF EXISTS for {table}_update_policy"
    )
    create_pattern = (
        rf"CREATE\s+POLICY\s+{table}_update_policy\s+ON\s+erp\.{table}"
        rf"[\s\S]*?FOR\s+UPDATE"
    )
    assert re.search(create_pattern, sql, re.IGNORECASE), (
        f"Missing CREATE POLICY {table}_update_policy ON erp.{table} FOR UPDATE"
    )


@pytest.mark.parametrize("table", TABLES_WITH_UPDATE_POLICY)
def test_update_policy_has_using_on_org_id(sql, table):
    """USING clause filters by org_id = JWT.org_id (cross-org SELECT-pre-image guard)."""
    # Match the policy block then the USING clause inside it.
    policy_block = re.search(
        rf"CREATE\s+POLICY\s+{table}_update_policy[\s\S]*?(?=DROP\s+POLICY|ALTER\s+TABLE|--\s*Part|$)",
        sql,
        re.IGNORECASE,
    )
    assert policy_block, f"Could not locate {table}_update_policy block"
    body = policy_block.group(0)
    assert re.search(r"USING\s*\(\s*org_id\s*=", body, re.IGNORECASE), (
        f"{table}_update_policy missing USING (org_id = ...)"
    )


@pytest.mark.parametrize("table", TABLES_WITH_UPDATE_POLICY)
def test_update_policy_has_with_check_on_org_id(sql, table):
    """WITH CHECK clause blocks org_id mutation — the core gap 027 closes."""
    policy_block = re.search(
        rf"CREATE\s+POLICY\s+{table}_update_policy[\s\S]*?(?=DROP\s+POLICY|ALTER\s+TABLE|--\s*Part|$)",
        sql,
        re.IGNORECASE,
    )
    assert policy_block, f"Could not locate {table}_update_policy block"
    body = policy_block.group(0)
    assert re.search(r"WITH\s+CHECK\s*\(\s*org_id\s*=", body, re.IGNORECASE), (
        f"{table}_update_policy missing WITH CHECK (org_id = ...) — "
        "the cross-org UPDATE-mutation gap remains open. This is the "
        "core deliverable of 027."
    )


@pytest.mark.parametrize("table", TABLES_WITH_UPDATE_POLICY)
def test_update_policy_jwt_org_id_resolution(sql, table):
    """Both clauses resolve org_id from the JWT (canonical RLS pattern)."""
    policy_block = re.search(
        rf"CREATE\s+POLICY\s+{table}_update_policy[\s\S]*?(?=DROP\s+POLICY|ALTER\s+TABLE|--\s*Part|$)",
        sql,
        re.IGNORECASE,
    )
    assert policy_block, f"Could not locate {table}_update_policy block"
    body = policy_block.group(0)
    # Both USING and WITH CHECK should resolve org_id via auth.jwt() -> 'org_id'.
    jwt_pattern = r"auth\.jwt\(\)\s*\)\s*->>\s*'org_id'"
    matches = re.findall(jwt_pattern, body)
    assert len(matches) >= 2, (
        f"{table}_update_policy expected JWT-org-id resolution in both "
        f"USING and WITH CHECK clauses; found {len(matches)} match(es)."
    )


# ---------------------------------------------------------------------------
# Part 2 — Foreign keys to public.organizations
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("table", TABLES_WITH_ORG_FK)
def test_org_fk_constraint_declared(sql, table):
    """Each table gets `<table>_org_id_fkey` FK to public.organizations(id)."""
    fk_pattern = (
        rf"ADD\s+CONSTRAINT\s+{table}_org_id_fkey\s+"
        rf"FOREIGN\s+KEY\s*\(\s*org_id\s*\)\s+"
        rf"REFERENCES\s+public\.organizations\s*\(\s*id\s*\)"
    )
    assert re.search(fk_pattern, sql, re.IGNORECASE), (
        f"Missing FK declaration {table}_org_id_fkey -> public.organizations(id)"
    )


@pytest.mark.parametrize("table", TABLES_WITH_ORG_FK)
def test_org_fk_drop_before_add(sql, table):
    """Each FK is dropped-if-exists before re-adding (idempotent shape)."""
    drop_pattern = (
        rf"DROP\s+CONSTRAINT\s+IF\s+EXISTS\s+{table}_org_id_fkey\s*;"
    )
    assert re.search(drop_pattern, sql, re.IGNORECASE), (
        f"Missing DROP CONSTRAINT IF EXISTS {table}_org_id_fkey "
        "(needed for idempotent replay)."
    )


@pytest.mark.parametrize("table", TABLES_WITH_ORG_FK)
def test_org_fk_on_delete_restrict(sql, table):
    """ON DELETE RESTRICT — deleting an org with live ERP rows must not cascade."""
    # Find the ADD CONSTRAINT block then check for ON DELETE RESTRICT inside it.
    add_block = re.search(
        rf"ADD\s+CONSTRAINT\s+{table}_org_id_fkey[\s\S]*?(?=;)",
        sql,
        re.IGNORECASE,
    )
    assert add_block, f"Could not locate ADD CONSTRAINT for {table}_org_id_fkey"
    body = add_block.group(0)
    assert re.search(r"ON\s+DELETE\s+RESTRICT", body, re.IGNORECASE), (
        f"{table}_org_id_fkey must have ON DELETE RESTRICT "
        "(cascading delete of an org would silently drop ERP rows)."
    )


@pytest.mark.parametrize("table", TABLES_WITH_ORG_FK)
def test_org_fk_validated(sql, table):
    """Constraint added NOT VALID then VALIDATE'd (lock-light path)."""
    add_pattern = rf"ADD\s+CONSTRAINT\s+{table}_org_id_fkey[\s\S]*?NOT\s+VALID"
    validate_pattern = (
        rf"VALIDATE\s+CONSTRAINT\s+{table}_org_id_fkey\s*;"
    )
    assert re.search(add_pattern, sql, re.IGNORECASE), (
        f"{table}_org_id_fkey should be added NOT VALID (lock-light path)."
    )
    assert re.search(validate_pattern, sql, re.IGNORECASE), (
        f"{table}_org_id_fkey missing VALIDATE CONSTRAINT (NOT VALID without "
        "follow-up VALIDATE leaves a stub constraint)."
    )


# ---------------------------------------------------------------------------
# Comment integrity — make sure stale brief names don't sneak back in
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "stale_name",
    ["whatsapp_etiquetas", "site_imoveis_config", "certidoes_consultas"],
)
def test_no_stale_brief_table_references(sql, stale_name):
    """The migration should reference live-schema names, not stale brief aliases.

    `whatsapp_etiquetas` doesn't exist; `site_imoveis_config` is `site_config`;
    `certidoes_consultas` (with 's' after certidao) is a brief typo of
    `certidao_consultas`. References should appear ONLY in commentary, never
    as table identifiers in DDL.
    """
    # Allow stale names to appear in comments (lines starting with `--`).
    non_comment_lines = [
        line for line in sql.splitlines()
        if not line.lstrip().startswith("--")
    ]
    non_comment_text = "\n".join(non_comment_lines)
    assert stale_name not in non_comment_text, (
        f"Stale brief alias '{stale_name}' leaked into DDL. "
        "Reference only the live-schema name."
    )
