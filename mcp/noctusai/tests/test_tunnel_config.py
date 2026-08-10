"""Regression tests for noctus.dev.tunnel_config + check_tunnel_ingress_snapshot_sync.

Born 2026-08-10 while publishing igig: `deploy/tunnel/ingress.yml` declared
itself SINGLE SOURCE OF TRUTH but nothing derived from it. The live
cloudflared config was a gitignored copy under projects/, so adding a route
to the canonical file changed nothing live — silently — and the committed
config.yml.template snapshot had drifted 2 routes behind (igig, orbity).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.tunnel_config import (  # noqa: E402
    parse_ingress, render_ingress_block, render_config, parse_config_hostmap,
)
from tools.noctus.dev.compliance import (  # noqa: E402
    check_tunnel_ingress_snapshot_sync,
)

INGRESS = """routes:
  - hostname: noctusai.com
    service:  http://core:8000
    note:     apex
  - hostname: igig.noctusai.com
    service:  http://igig:8013
"""

LIVE = """tunnel: abc-123
credentials-file: /etc/cloudflared/abc-123.json
protocol: http2

ingress:
  - hostname: noctusai.com
    service: http://core:8000
  - service: http_status:404
"""


class TestRender:
    def test_parses_routes_in_order(self):
        routes = parse_ingress(INGRESS)
        assert [r["hostname"] for r in routes] == ["noctusai.com", "igig.noctusai.com"]

    def test_catch_all_is_last_by_construction(self):
        block = render_ingress_block(parse_ingress(INGRESS))
        assert block.rstrip().endswith("- service: http_status:404")
        # ...and appears exactly once, however the input was ordered
        assert block.count("http_status:404") == 1

    def test_render_preserves_tunnel_identity_lines(self):
        out = render_config(LIVE, parse_ingress(INGRESS))
        assert "tunnel: abc-123" in out
        assert "credentials-file: /etc/cloudflared/abc-123.json" in out
        assert "protocol: http2" in out
        # and the new route is now present
        assert "igig.noctusai.com" in out

    def test_render_is_idempotent(self):
        once = render_config(LIVE, parse_ingress(INGRESS))
        twice = render_config(once, parse_ingress(INGRESS))
        assert once == twice

    @pytest.mark.parametrize("bad", [
        "routes: []",
        "routes:\n  - hostname: x\n",              # no service
        "routes:\n  - service: http://x:1\n",      # no hostname
        "nothing: here",
    ])
    def test_malformed_ingress_raises_never_silently_drops(self, bad):
        """A dropped route is an outage — never a silent no-op."""
        with pytest.raises(ValueError):
            parse_ingress(bad)

    def test_hostmap_ignores_catch_all(self):
        assert parse_config_hostmap(LIVE) == {"noctusai.com": "http://core:8000"}


def _tree(tmp_path: Path, ingress: str, template: str) -> Path:
    d = tmp_path / "deploy" / "tunnel"
    d.mkdir(parents=True)
    (d / "ingress.yml").write_text(ingress, encoding="utf-8")
    (d / "config.yml.template").write_text(template, encoding="utf-8")
    return tmp_path


class TestCheckTunnelIngressSnapshotSync:
    def test_fires_when_template_is_behind(self, tmp_path):
        """The real 2026-08-10 shape: igig declared, template stale."""
        root = _tree(tmp_path, INGRESS, LIVE)
        issues = check_tunnel_ingress_snapshot_sync(repo_root=root)
        assert len(issues) == 1
        assert issues[0]["symbol"] == "tunnel-ingress-snapshot-drift"
        assert issues[0]["severity"] == "high"
        assert "igig.noctusai.com" in issues[0]["issue"]

    def test_silent_when_derived(self, tmp_path):
        routes = parse_ingress(INGRESS)
        root = _tree(tmp_path, INGRESS, render_config(LIVE, routes))
        assert check_tunnel_ingress_snapshot_sync(repo_root=root) == []

    def test_fires_when_service_target_differs(self, tmp_path):
        moved = INGRESS.replace("http://igig:8013", "http://igig:9999")
        root = _tree(tmp_path, moved, render_config(LIVE, parse_ingress(INGRESS)))
        issues = check_tunnel_ingress_snapshot_sync(repo_root=root)
        assert issues and "service target differs" in issues[0]["issue"]

    def test_silent_skip_on_non_noc_tree(self, tmp_path):
        assert check_tunnel_ingress_snapshot_sync(repo_root=tmp_path) == []

    def test_unparseable_ingress_is_a_loud_finding(self, tmp_path):
        root = _tree(tmp_path, "routes:\n  - hostname: x\n", LIVE)
        issues = check_tunnel_ingress_snapshot_sync(repo_root=root)
        assert issues and issues[0]["symbol"] == "tunnel-ingress-unparseable"


class TestTunnelSecretsAreGitignored:
    """deploy/tunnel/ is a TRACKED directory that holds three secrets-or-live
    artifacts. All must be ignored, or a routine `git add -A` commits them.

    `cert.pem` was NOT covered until 2026-08-10 — caught before
    `cloudflared tunnel login` was run, not after. It is strictly more
    powerful than the per-tunnel credentials JSON: it can create or modify
    DNS for the entire zone.
    """

    @pytest.mark.parametrize("name", [
        "config.yml",                                   # live config
        "6e9ccdc5-4d99-4d5e-b9f9-1da2fe99f56c.json",    # tunnel credentials
        "cert.pem",                                     # ZONE credential
    ])
    def test_tunnel_secret_is_gitignored(self, name):
        import subprocess
        repo = Path(__file__).resolve().parents[3]
        r = subprocess.run(
            ["git", "-C", str(repo), "check-ignore", "-q", f"deploy/tunnel/{name}"],
            capture_output=True,
        )
        assert r.returncode == 0, (
            f"deploy/tunnel/{name} is NOT gitignored — it would be committable "
            "from a tracked directory"
        )
