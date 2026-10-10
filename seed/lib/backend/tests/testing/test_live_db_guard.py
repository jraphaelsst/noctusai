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


# --- .env-file residual gap (2026-10-09 follow-up) -------------------------

_FAKE_ENV = f"SUPABASE_URL=https://{PROD_PROJECT_REF}.supabase.co\nSUPABASE_SERVICE_ROLE_KEY=dummy-key\n"


def _settings_cls(env_path):
    from pydantic_settings import SettingsConfigDict
    from noctusai_lib.config.settings import BaseAppSettings

    class _S(BaseAppSettings):
        model_config = SettingsConfigDict(env_file=str(env_path), extra="ignore")

    return _S


def test_seam_drops_env_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(_FAKE_ENV)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("NOCTUS_SETTINGS_NO_ENV_FILE", raising=False)
    assert PROD_PROJECT_REF in _settings_cls(env)().supabase_url  # seam off: file is read
    monkeypatch.setenv("NOCTUS_SETTINGS_NO_ENV_FILE", "1")
    assert _settings_cls(env)().supabase_url == ""
    # an explicit _env_file is a deliberate act and is kept
    assert PROD_PROJECT_REF in _settings_cls(tmp_path / "other")(_env_file=str(env)).supabase_url


def test_plugin_sets_seam_for_this_session():
    import os
    assert os.environ.get("NOCTUS_SETTINGS_NO_ENV_FILE") == "1"


def test_guard_refuses_when_settings_resolve_prod(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(_FAKE_ENV)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("NOCTUS_SETTINGS_NO_ENV_FILE", raising=False)  # seam off => leak
    with pytest.raises(RuntimeError, match=r"settings\.supabase_url") as ei:
        assert_hermetic([_item(False)], settings_cls=_settings_cls(env))
    assert "dummy-key" not in str(ei.value)
    monkeypatch.setenv("NOCTUS_SETTINGS_NO_ENV_FILE", "1")  # seam on => clean
    assert_hermetic([_item(False)], settings_cls=_settings_cls(env))
