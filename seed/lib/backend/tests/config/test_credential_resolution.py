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
from noctusai_lib.testing.credentials import patch_credentials_to_mock


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


class TestResolveOrgCredential:
    """`resolve_org_credential` — org_settings only, never override/platform/env."""

    class _Table:
        def __init__(self, rows):
            self._rows, self._f = rows, {}

        def select(self, *_):
            return self

        def eq(self, col, val):
            self._f[col] = val
            return self

        def execute(self):
            class R:  # noqa: D401
                data = None

            r = R()
            r.data = [
                {"value": row["value"]}
                for row in self._rows
                if all(row.get(c) == v for c, v in self._f.items())
            ]
            return r

    class _Db:
        def __init__(self, rows):
            self._rows = rows

        def table(self, name):
            assert name == "org_settings"
            return TestResolveOrgCredential._Table(self._rows)

    def _install(self, rows):
        cred._config = {"url": "x", "anon_key": "", "service_role_key": ""}
        cred._public_client = self._Db(rows)

    def test_reads_only_the_callers_org_row(self):
        self._install([
            {"org_id": "org-a", "key": "openai_api_key", "value": "sk-a"},
            {"org_id": "org-b", "key": "openai_api_key", "value": "sk-b"},
        ])
        assert cred.resolve_org_credential("openai_api_key", "org-b") == "sk-b"
        assert cred.resolve_org_credential("openai_api_key", "org-c") is None

    def test_never_falls_back_to_env_override_or_platform(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
        cred.register_credential_override(lambda key, org_id: "sk-override")
        self._install([])
        assert cred.resolve_org_credential("openai_api_key", "org-a") is None

    def test_no_org_is_a_miss(self):
        self._install([{"org_id": "org-a", "key": "k", "value": "v"}])
        assert cred.resolve_org_credential("k", None) is None


class _CountingDb:
    """A public-schema client that serves `org_settings` / `platform_settings` rows and COUNTS reads: a fake
    that makes calls free is exactly why the per-call read was invisible (KB § polling-request-budget.md)."""

    def __init__(self, org=None, platform=None):
        self.org = org or {}
        self.platform = platform or {}
        self.reads = 0

    def table(self, name):
        db = self
        data = db.org if name == "org_settings" else db.platform

        class _Q:
            def __init__(self):
                self._f = {}

            def select(self, *_a, **_k):
                return self

            def eq(self, col, val):
                self._f[col] = val
                return self

            def execute(self):
                db.reads += 1
                row = data.get((self._f.get("org_id"), self._f.get("key")) if name == "org_settings" else self._f.get("key"))
                return type("R", (), {"data": [{"value": row}] if row else []})()

        return _Q()


class TestResolutionIsCached:
    @pytest.fixture
    def db(self):
        db = _CountingDb(platform={"resend_api_key": "re-platform"})
        with patch_credentials_to_mock(db):  # the seed's sanctioned external-boundary seam
            yield db

    def test_a_hot_key_costs_one_read_per_tier_per_ttl_not_one_per_call(self, db):
        for _ in range(500):
            assert cred.resolve_credential("resend_api_key", "org-1") == "re-platform"
        assert db.reads == 2  # org_settings (miss) + platform_settings (hit): once, not 1,000

    def test_a_write_through_this_process_is_live_at_once(self, db):
        assert cred.resolve_credential("resend_api_key", "org-1") == "re-platform"
        db.org[("org-1", "resend_api_key")] = "re-org"
        cred.invalidate_credential_cache()
        assert cred.resolve_credential("resend_api_key", "org-1") == "re-org"

    def test_a_failed_read_is_not_remembered_as_unset(self, monkeypatch):
        class _Boom:
            reads = 0

            def table(self, _n):
                self.reads += 1
                raise RuntimeError("PostgREST 502")

        boom = _Boom()
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        with patch_credentials_to_mock(boom):
            assert cred.resolve_credential("resend_api_key", "org-1") is None
            assert cred.resolve_credential("resend_api_key", "org-1") is None
        assert boom.reads == 4  # retried both times (2 tiers x 2 calls)

    def test_env_is_read_live_never_cached(self, db, monkeypatch):
        monkeypatch.delenv("OTHER_KEY", raising=False)
        assert cred.resolve_credential("other_key", "org-1") is None
        monkeypatch.setenv("OTHER_KEY", "from-env")
        assert cred.resolve_credential("other_key", "org-1") == "from-env"
