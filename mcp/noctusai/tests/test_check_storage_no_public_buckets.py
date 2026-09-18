"""Tests for ``noctus.dev.check_storage_no_public_buckets`` — the LIVE
half of the zero-public-bucket gate.

All tests are fully hermetic — they use ``migrate_product.FakeSqlExecutor``
(injected), so zero real Supabase calls are made. No monkey-patching of our
own code (per KB § PATTERNS/compliance/testing.md); the one carve-out
(neutralizing the DB-first credential tier, an external seed-library seam)
mirrors ``test_ensure_schema_exposure.py``'s own carve-out.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "seed" / "lib" / "backend"))

from tools.noctus.dev.check_storage_no_public_buckets import (  # noqa: E402
    _PUBLIC_BUCKETS_SQL,
    check_storage_no_public_buckets,
)
from tools.noctus.dev.migrate_product import FakeSqlExecutor  # noqa: E402


class TestCleanState:
    def test_no_public_buckets_returns_clean(self):
        fake = FakeSqlExecutor(preset_rows={_PUBLIC_BUCKETS_SQL: []})

        result = check_storage_no_public_buckets(executor=fake)

        assert result["status"] == "clean"
        assert result["ok"] is True
        assert result["public_buckets"] == []
        assert result["error"] is None
        assert fake.executed == [_PUBLIC_BUCKETS_SQL]


class TestViolation:
    def test_public_bucket_found_fails_and_names_it(self):
        """THE INCIDENT shape: erp-certidoes / erp-geral live public=true."""
        fake = FakeSqlExecutor(
            preset_rows={
                _PUBLIC_BUCKETS_SQL: [
                    {"id": "erp-certidoes", "name": "erp-certidoes", "public": True},
                    {"id": "erp-geral", "name": "erp-geral", "public": True},
                ],
            }
        )

        result = check_storage_no_public_buckets(executor=fake)

        assert result["status"] == "violation"
        assert result["ok"] is False
        assert {"id": "erp-certidoes", "name": "erp-certidoes"} in result["public_buckets"]
        assert {"id": "erp-geral", "name": "erp-geral"} in result["public_buckets"]
        assert "erp-certidoes" in result["error"]
        # The failure message must name the sanctioned alternative — a
        # refusal that doesn't name the correct fix just gets bypassed.
        assert "signed URL" in result["error"]
        assert "get_signed_url" in result["error"]

    def test_single_public_bucket_still_violates(self):
        fake = FakeSqlExecutor(
            preset_rows={
                _PUBLIC_BUCKETS_SQL: [
                    {"id": "some-bucket", "name": "some-bucket", "public": True},
                ],
            }
        )

        result = check_storage_no_public_buckets(executor=fake)

        assert result["status"] == "violation"
        assert len(result["public_buckets"]) == 1


class TestFailClosedPosture:
    """Every non-'clean' status is a FAILURE, never a silent skip — this
    is the ONE leg in predeploy_check with no write/override path at all."""

    def test_query_failure_is_error_not_skip(self):
        fake = FakeSqlExecutor(fail_on={"storage.buckets"})

        result = check_storage_no_public_buckets(executor=fake)

        assert result["status"] == "error"
        assert result["ok"] is False
        assert result["error"]

    def test_not_configured_when_no_token(self, monkeypatch):
        """When SUPABASE_ACCESS_TOKEN is absent and no executor injected,
        returns not_configured — NEVER a silent skip (predeploy_check's
        storage_bucket_public leg depends on this to fail loud, mirroring
        schema_exposure's identical posture)."""
        monkeypatch.delenv("SUPABASE_ACCESS_TOKEN", raising=False)
        # Neutralize the DB-first tier so this stays hermetic (no real DB
        # read) — same external-seam carve-out test_ensure_schema_exposure.py
        # / test_migrate_product.py use.
        monkeypatch.setattr(
            "noctusai_lib.config.credentials.resolve_credential",
            lambda *a, **k: None,
        )

        result = check_storage_no_public_buckets()

        assert result["status"] == "not_configured"
        assert result["ok"] is False
        assert "SUPABASE_ACCESS_TOKEN" in result["error"]
        assert "NOC-REMEDIATE" in result["error"]


class TestNoOverridePath:
    """This module ships NO apply/confirm/allow parameter of any kind —
    the fix is a manual ALTER/dashboard toggle the operator runs directly,
    never something this tool can be asked to do (or undo) for them."""

    def test_function_has_no_confirm_or_apply_kwarg(self):
        import inspect

        sig = inspect.signature(check_storage_no_public_buckets)
        assert "confirm" not in sig.parameters
        assert "apply" not in sig.parameters
        assert "action" not in sig.parameters
        assert "allow_public_bucket" not in sig.parameters
        assert "force" not in sig.parameters
