"""`noctusai_lib.config.credentials` — the resolution chain itself.

There was no test file for this module, which is a large part of why the
empty-`supabase_url` defect below survived: it is reachable from every
product on every credential lookup, and nothing pinned the contract its
own docstring states.

Covered here:
  * an unusable Supabase config MISSES rather than raising (the regression);
  * the tier-0 product override — consulted first, and never able to take
    resolution down with it.
"""
from __future__ import annotations

import pytest

from noctusai_lib.config import credentials as cred


@pytest.fixture(autouse=True)
def _clean_module_state():
    """Each test starts from a module with no config and no override."""
    cred._reset_for_testing()
    yield
    cred._reset_for_testing()


class TestUnusableSupabaseConfigMisses:
    """Tiers 1+2 miss when there is nothing to build a client from.

    `create_product_app` calls `configure_credentials(...)` unconditionally
    at boot with whatever `settings.supabase_url` holds — the empty string
    when no `.env` is present. `_config` is then a dict rather than None, so
    an `is None` guard let an empty URL through to `make_supabase_client`,
    which raises `SupabaseException: supabase_url is required` straight out
    to the caller. Every `.env`-less environment (CI included) turned into a
    500 on any credential lookup.
    """

    def test_empty_url_falls_through_to_env_instead_of_raising(self, monkeypatch):
        cred.configure_credentials(
            supabase_url="", supabase_anon_key="", supabase_service_role_key=""
        )
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")

        # The whole point: this must RETURN, not raise.
        assert cred.resolve_credential("openai_api_key", "org-1") == "sk-from-env"

    def test_empty_url_with_no_env_var_is_a_plain_miss(self, monkeypatch):
        cred.configure_credentials(
            supabase_url="", supabase_anon_key="", supabase_service_role_key=""
        )
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        assert cred.resolve_credential("openai_api_key", "org-1") is None

    def test_never_configured_still_misses(self, monkeypatch):
        """The case the original `is None` guard did handle — kept so the
        fix cannot regress it while fixing the empty-URL sibling."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
        assert cred.resolve_credential("openai_api_key", "org-1") == "sk-from-env"


class TestProductOverrideTier:
    """Tier 0 — `register_credential_override`."""

    def test_override_answers_before_the_rest_of_the_chain(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
        cred.register_credential_override(
            lambda key, org_id: "sk-from-product-store" if key == "openai_api_key" else None
        )

        assert cred.resolve_credential("openai_api_key", "org-1") == "sk-from-product-store"

    def test_override_miss_falls_through(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
        cred.register_credential_override(lambda key, org_id: None)

        assert cred.resolve_credential("openai_api_key", "org-1") == "sk-from-env"

    def test_a_raising_override_does_not_take_resolution_down(self, monkeypatch, caplog):
        """A rotated/missing ENCRYPTION_KEY makes the product store raise.

        That must not become "no key configured" for the whole platform —
        the chain continues, and the failure is logged LOUDLY (WARNING, not
        DEBUG) so the real cause is not mistaken for an unset key.
        """
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")

        def _boom(key, org_id):
            raise RuntimeError("ENCRYPTION_KEY invalid")

        cred.register_credential_override(_boom)

        with caplog.at_level("WARNING"):
            assert cred.resolve_credential("openai_api_key", "org-1") == "sk-from-env"

        assert any(
            r.levelname == "WARNING" and "credential override failed" in r.message
            for r in caplog.records
        ), "the override failure must be surfaced, not swallowed"

    def test_registering_none_restores_the_plain_chain(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
        cred.register_credential_override(lambda key, org_id: "sk-from-product-store")
        cred.register_credential_override(None)

        assert cred.resolve_credential("openai_api_key", "org-1") == "sk-from-env"

    def test_reset_for_testing_clears_the_override(self, monkeypatch):
        """Otherwise one test's override leaks into every later test."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
        cred.register_credential_override(lambda key, org_id: "sk-leaked")

        cred._reset_for_testing()

        assert cred.resolve_credential("openai_api_key", "org-1") == "sk-from-env"
