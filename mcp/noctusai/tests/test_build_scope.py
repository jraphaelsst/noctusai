"""The active-set build-scope contract (2026-08-11).

WHAT THIS PINS. `build-and-push.yml` used to treat any `seed/**` change as "rebuild the
WHOLE fleet" — all 11 services in docker-compose.prod.yml, including the 7 products
that are `ativo=false` in the catalog and that we have explicitly decided not to touch.
A one-line package.json edit cost a full 11-product build.

`deploy/fleet/build-scope.txt` now narrows what a PUSH rebuilds. Two invariants matter
most, and both are failure modes that would be SILENT:
  • a live product missing from the scope file → its image silently stops being built
  • a scope slug with no fleet service      → silently never builds, looks fine

Both are made loud: `refresh_build_scope` refuses to write, and the workflow refuses to
run. → KB § PATTERNS/devops/product-lockfile-and-slug-drift.md
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import build_scope as bs  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
WORKFLOW = REPO / ".github" / "workflows" / "build-and-push.yml"

COMPOSE = """\
x-prod-defaults: &prod-defaults
  env_file:
    - ../../.env
  environment:
    FOO: bar
  networks:
    - noctus-net

services:
  core:
    image: ghcr.io/x/core:latest
    environment:
      A: b
    networks:
      - noctus-net
  erp-imobiliario:
    image: ghcr.io/x/erp:latest
  adconnect:
    image: ghcr.io/x/adconnect:latest

networks:
  noctus-net:
    external: true
"""


@pytest.fixture
def fleet(tmp_path, monkeypatch):
    c = tmp_path / "docker-compose.prod.yml"
    c.write_text(COMPOSE)
    monkeypatch.setattr(bs, "FLEET_COMPOSE", c)
    monkeypatch.setattr(bs, "SCOPE_PATH", tmp_path / "build-scope.txt")
    return c


class TestFleetSlugs:
    def test_only_service_names(self, fleet):
        """The naive '2-space indented key' match swallows anchors and networks."""
        assert bs.fleet_slugs() == ["adconnect", "core", "erp-imobiliario"]

    def test_excludes_nested_and_toplevel_keys(self, fleet):
        got = bs.fleet_slugs()
        for phantom in ("environment", "networks", "noctus-net", "env_file"):
            assert phantom not in got, f"{phantom!r} is not a service"

    def test_missing_compose_is_empty_not_crash(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bs, "FLEET_COMPOSE", tmp_path / "nope.yml")
        assert bs.fleet_slugs() == []


class TestRefresh:
    def test_writes_live_plus_core(self, fleet):
        r = bs.refresh_build_scope(_live=["erp-imobiliario"])
        assert r["ok"] and r["status"] == "written"
        assert r["slugs"] == ["core", "erp-imobiliario"]

    def test_inactive_fleet_member_is_excluded_and_named(self, fleet):
        """Excluding must be reported, never silent (no-silent-caps)."""
        r = bs.refresh_build_scope(_live=["erp-imobiliario"])
        assert r["excluded"] == ["adconnect"]
        assert "adconnect" in bs.SCOPE_PATH.read_text()

    def test_live_product_absent_from_fleet_REFUSES(self, fleet):
        """A live product with no service would silently never build."""
        r = bs.refresh_build_scope(_live=["erp-imobiliario", "ghost-product"])
        assert r["ok"] is False and r["status"] == "error"
        assert "ghost-product" in r["error"]
        assert not bs.SCOPE_PATH.exists(), "must not write a scope file that drops it"

    def test_idempotent_in_sync_does_not_rewrite(self, fleet):
        """The header carries a date — a byte-compare would dirty the tree every run."""
        bs.refresh_build_scope(_live=["erp-imobiliario"])
        before = bs.SCOPE_PATH.read_text()
        second = bs.refresh_build_scope(_live=["erp-imobiliario"])
        assert second["status"] == "in-sync" and second["changed"] is False
        assert bs.SCOPE_PATH.read_text() == before

    def test_dry_run_writes_nothing(self, fleet):
        r = bs.refresh_build_scope(write=False, _live=["erp-imobiliario"])
        assert r["status"] == "would-write"
        assert not bs.SCOPE_PATH.exists()

    def test_no_supabase_env_refuses_rather_than_guessing(self, fleet, monkeypatch):
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        r = bs.refresh_build_scope()
        assert r["ok"] is False
        assert "Refusing to guess" in r["error"]

    def test_roundtrip_read_back(self, fleet):
        bs.refresh_build_scope(_live=["erp-imobiliario"])
        monkeypatchless = bs.read_build_scope()
        assert monkeypatchless == ["core", "erp-imobiliario"]


class TestCommittedScopeFile:
    """The real file must stay coherent with the real fleet."""

    def test_exists(self):
        assert bs.SCOPE_PATH.exists(), "build-and-push.yml hard-fails without it"

    def test_every_scope_slug_is_a_real_fleet_service(self):
        fleet = set(bs.fleet_slugs())
        missing = [s for s in bs.read_build_scope() if s not in fleet]
        assert not missing, f"scope lists non-fleet slug(s): {missing}"

    def test_core_is_always_present(self):
        assert "core" in bs.read_build_scope(), "the platform shell must always build"


class TestWorkflowWiring:
    """The workflow is shell inside YAML — no suite executes it, so pin the contract."""

    def test_workflow_reads_the_scope_file(self):
        assert "deploy/fleet/build-scope.txt" in WORKFLOW.read_text()

    def test_push_paths_no_longer_build_all(self):
        """`products=` (empty) means ALL to build-and-push.sh — must not appear on a
        push path any more; only the dispatch/skip branches may emit an empty list."""
        text = WORKFLOW.read_text()
        assert 'echo "scope: seed/ or build-script changed → ALL' not in text
        assert "mode=active" in text, "the seed/** branch must resolve to the active set"

    def test_dispatch_override_survives(self):
        """The manual escape hatch must remain — it is how you force a full rebuild."""
        assert "workflow_dispatch" in WORKFLOW.read_text()
        assert "mode=dispatch" in WORKFLOW.read_text()

    def test_workflow_fails_loudly_on_missing_or_stale_scope(self):
        text = WORKFLOW.read_text()
        assert "::error::" in text
        assert "--refresh-build-scope" in text, "the error must name the fix command"

    def test_dropped_inactive_products_are_announced(self):
        """Silent truncation reads as 'covered everything'."""
        assert "skipping inactive product(s)" in WORKFLOW.read_text()


class TestCliFlagExists:
    def test_flag_is_wired(self):
        """The scope file + workflow errors both point at this flag."""
        cli = (REPO / "mcp" / "noctusai" / "cli.py").read_text()
        assert "--refresh-build-scope" in cli
        assert "refresh_build_scope" in cli

    def test_tool_is_registered(self):
        init = (REPO / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "__init__.py").read_text()
        assert "build_scope.register(server)" in init
