"""The live-DB guard refuses hermetic sessions against prod/*.supabase.co."""
from types import SimpleNamespace

import pytest

from noctusai_lib.testing.live_db_guard import (
    PROD_PROJECT_REF, assert_hermetic, live_supabase_env_keys,
)


def _item(realdb: bool):
    return SimpleNamespace(get_closest_marker=lambda n: object() if realdb and n == "realdb" else None)


def test_clean_env_passes():
    assert_hermetic([_item(False)], {"SUPABASE_URL": "http://localhost:54321"})


def test_prod_ref_in_url_refuses():
    env = {"SUPABASE_URL": f"https://{PROD_PROJECT_REF}.supabase.co"}
    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        assert_hermetic([_item(False)], env)


def test_any_supabase_host_refuses_and_value_not_leaked():
    env = {"DATABASE_URL": "postgresql://u:secretpw@abcdef.supabase.co:5432/db"}
    with pytest.raises(RuntimeError) as ei:
        assert_hermetic([_item(False)], env)
    assert "secretpw" not in str(ei.value)


def test_only_realdb_items_allowed():
    env = {"SUPABASE_URL": "https://abcdef.supabase.co"}
    assert_hermetic([_item(True)], env)
    with pytest.raises(RuntimeError):
        assert_hermetic([_item(True), _item(False)], env)


def test_keys_listing():
    assert live_supabase_env_keys({"SUPABASE_PROJECT_REF": PROD_PROJECT_REF}) == ["SUPABASE_PROJECT_REF"]
