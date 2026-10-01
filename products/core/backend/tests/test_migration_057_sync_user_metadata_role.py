"""Structural tests for `057_sync_user_metadata_role.sql` (no database needed).

Load-bearing assertions: the trigger fires on INSERT and on any change to the
three columns the frontend role gates read; it writes exactly the keys Core's
`/api/sso/session` writes (`org_id`, `org_role`, `noctus_role`) with a shallow
MERGE (never a replace that would drop the SSO plan/license enrichment); the
function is SECURITY DEFINER with a pinned search_path and is not callable by
the API roles; the backfill only touches drifted rows.
"""
from __future__ import annotations

from pathlib import Path

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "057_sync_user_metadata_role.sql"
)


@pytest.fixture(scope="module")
def code() -> str:
    assert MIGRATION.is_file(), f"Migration file missing at {MIGRATION}"
    sql = MIGRATION.read_text(encoding="utf-8")
    return "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    return " ".join(code.split())


def test_migration_parses():
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(MIGRATION.read_text(encoding="utf-8"))) > 0


def test_only_number_057_in_this_file_name():
    assert [p.name for p in MIGRATION.parent.glob("057_*.sql")] == [MIGRATION.name]


def test_trigger_fires_on_insert_and_on_every_role_column(flat: str):
    assert (
        "AFTER INSERT OR UPDATE OF org_id, org_role, role ON public.noctus_users "
        "FOR EACH ROW EXECUTE FUNCTION public.sync_noctus_user_metadata()"
    ) in flat


def test_writes_the_same_keys_as_sso_session_by_merge_not_replace(flat: str):
    merge = (
        "COALESCE(raw_user_meta_data, '{}'::jsonb) || jsonb_build_object( "
        "'org_id', NEW.org_id, 'org_role', NEW.org_role, 'noctus_role', NEW.role)"
    )
    assert merge in flat
    assert "raw_user_meta_data = jsonb_build_object" not in flat, "a replace would drop SSO enrichment keys"


def test_function_is_definer_with_pinned_search_path_and_not_api_callable(flat: str):
    assert "SECURITY DEFINER SET search_path TO 'public'" in flat
    assert "REVOKE ALL ON FUNCTION public.sync_noctus_user_metadata() FROM PUBLIC, anon, authenticated" in flat


def test_backfill_only_touches_drifted_rows(flat: str):
    for key in ("org_id", "org_role", "noctus_role"):
        assert f"u.raw_user_meta_data->>'{key}'" in flat and "IS DISTINCT FROM" in flat
