"""Tests for `noctusai_lib.testing.get_realdb_credentials`.

Three scenarios per the module's contract:

(a) opt-in absent (`NOCTUS_REALDB_TESTS` unset/not "1") -> skip, regardless
    of what SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are set to;
(b) opt-in set AND SUPABASE_URL resolves to the production project ref
    -> skip, even with the opt-in;
(c) opt-in set AND SUPABASE_URL resolves to a non-production ref -> the
    (url, key) pair is returned.

Plus the `_project_ref_from_url` extraction helper directly, since it's
the piece that decides (b) vs (c).
"""
from __future__ import annotations

import pytest

from noctusai_lib.testing.realdb import (
    _PROD_PROJECT_REF,
    _project_ref_from_url,
    get_realdb_credentials,
)


@pytest.fixture(autouse=True)
def _clear_realdb_env(monkeypatch):
    """Every test starts from a clean slate — no leftover real .env creds."""
    monkeypatch.delenv("NOCTUS_REALDB_TESTS", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)


def test_project_ref_from_url_extracts_subdomain():
    assert _project_ref_from_url("https://abcd1234efgh.supabase.co") == "abcd1234efgh"


def test_project_ref_from_url_returns_empty_for_non_supabase_host():
    # Local / self-hosted stacks never collide with the prod ref.
    assert _project_ref_from_url("http://localhost:54321") == ""
    assert _project_ref_from_url("https://example.com") == ""


def test_opt_in_absent_skips_even_with_credentials_set(monkeypatch):
    """The core bug this module fixes: creds being *present* must never be
    sufficient on its own — the explicit opt-in is mandatory."""
    monkeypatch.setenv("SUPABASE_URL", "https://some-nonprod-ref.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-key")
    with pytest.raises(pytest.skip.Exception) as exc_info:
        get_realdb_credentials()
    assert "NOCTUS_REALDB_TESTS" in str(exc_info.value)


def test_opt_in_set_but_wrong_value_still_skips(monkeypatch):
    monkeypatch.setenv("NOCTUS_REALDB_TESTS", "true")  # not the literal "1"
    monkeypatch.setenv("SUPABASE_URL", "https://some-nonprod-ref.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-key")
    with pytest.raises(pytest.skip.Exception):
        get_realdb_credentials()


def test_opt_in_set_without_credentials_skips(monkeypatch):
    monkeypatch.setenv("NOCTUS_REALDB_TESTS", "1")
    with pytest.raises(pytest.skip.Exception) as exc_info:
        get_realdb_credentials()
    assert "SUPABASE_URL" in str(exc_info.value)


def test_prod_ref_skips_even_with_opt_in(monkeypatch):
    """The second, independent gate: opt-in alone is not enough either."""
    monkeypatch.setenv("NOCTUS_REALDB_TESTS", "1")
    monkeypatch.setenv("SUPABASE_URL", f"https://{_PROD_PROJECT_REF}.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-key")
    with pytest.raises(pytest.skip.Exception) as exc_info:
        get_realdb_credentials()
    assert "PRODUCTION" in str(exc_info.value)


def test_non_prod_ref_with_opt_in_returns_credentials(monkeypatch):
    monkeypatch.setenv("NOCTUS_REALDB_TESTS", "1")
    monkeypatch.setenv("SUPABASE_URL", "https://disposable-branch-ref.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-key")
    url, key = get_realdb_credentials()
    assert url == "https://disposable-branch-ref.supabase.co"
    assert key == "fake-key"


def test_non_supabase_host_with_opt_in_returns_credentials(monkeypatch):
    """A local/self-hosted URL never matches the prod ref pattern, so it's
    treated as safe (can't collide with `_PROD_PROJECT_REF`)."""
    monkeypatch.setenv("NOCTUS_REALDB_TESTS", "1")
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-key")
    url, key = get_realdb_credentials()
    assert url == "http://localhost:54321"
    assert key == "fake-key"
