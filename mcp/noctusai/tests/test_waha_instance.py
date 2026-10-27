"""noctus.dev.waha_instance + check_waha_instances_render_sync: one WAHA Core container per number, as data."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import waha_instance as wi  # noqa: E402
from tools.noctus.dev.compliance import check_waha_instances_render_sync  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
DATA = """image: devlikeapro/waha:noweb-2026.9.2
platform: linux/amd64
engine: NOWEB
mem_limit: 512m
node_heap_mb: 384
instances:
  - name: monica
    product: monica
  - name: two-b
    product: other
"""


def _tree(tmp_path, data=DATA, compose="render"):
    d = tmp_path / "deploy" / "fleet"
    d.mkdir(parents=True)
    (d / "waha-instances.yml").write_text(data)
    if compose == "render":
        (d / "compose.waha.yml").write_text(wi.render_compose(wi.parse_instances(data)))
    elif compose is not None:
        (d / "compose.waha.yml").write_text(compose)
    return tmp_path


class TestRender:
    def test_one_service_volume_and_key_set_per_instance(self):
        out = wi.render_compose(wi.parse_instances(DATA))
        for n, up in (("monica", "MONICA"), ("two-b", "TWO_B")):
            assert f"  waha-{n}:" in out and f"container_name: noctus-waha-{n}" in out
            assert f"${{WAHA_{up}_API_KEY:?" in out and f"${{WAHA_{up}_HMAC_SECRET:?" in out
        assert out.count("expose:") == 2 and "ports:" not in out
        assert "mem_limit: 512m" in out and "healthcheck:" in out and "restart: unless-stopped" in out
        # The NOWEB store is a per-session setting the product sends on start; WAHA has no env for it,
        # and an env-autostarted session would come up without it.
        assert "NOWEB_STORE" not in out and "START_SESSION" not in out

    def test_no_secret_value_is_ever_rendered(self):
        assert "openssl" not in wi.render_compose(wi.parse_instances(DATA))

    @pytest.mark.parametrize("bad", [DATA.replace("noweb-2026.9.2", "latest"), DATA.replace("monica", "Bad Name", 1),
                                     DATA + "  - name: monica\n    product: x\n"])
    def test_invalid_declarations_raise(self, bad):
        with pytest.raises(ValueError):
            wi.parse_instances(bad)


class TestWahaInstancesRenderSync:
    def test_in_sync(self, tmp_path):
        assert check_waha_instances_render_sync(repo_root=_tree(tmp_path)) == []

    def test_hand_edit_is_drift(self, tmp_path):
        root = _tree(tmp_path)
        p = root / "deploy/fleet/compose.waha.yml"
        p.write_text(p.read_text().replace("512m", "9g"))
        assert check_waha_instances_render_sync(repo_root=root)[0]["symbol"] == "waha-instances-render-drift"

    def test_missing_compose_is_drift(self, tmp_path):
        assert check_waha_instances_render_sync(repo_root=_tree(tmp_path, compose=None))

    def test_real_repo_is_in_sync(self):
        assert check_waha_instances_render_sync(repo_root=REPO) == []


class TestActions:
    def test_apply_dry_run_touches_no_ssh(self, tmp_path, monkeypatch):
        monkeypatch.setattr(wi, "run_remote", lambda *a, **k: pytest.fail("ssh in dry-run"))
        r = wi.waha_instance("apply", name="monica", repo_root=str(_tree(tmp_path)))
        assert r["status"] == "planned" and r["env_fleet_keys_to_generate_on_vps"][0] == "WAHA_MONICA_API_KEY"

    def test_apply_blocks_when_keys_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(wi, "run_remote", lambda *a, **k: (3, "MISSING:WAHA_MONICA_API_KEY", ""))
        r = wi.waha_instance("apply", name="monica", confirm=True, repo_root=str(_tree(tmp_path)))
        assert r["status"] == "blocked"

    def test_remove_refuses_working_session(self, tmp_path, monkeypatch):
        monkeypatch.setattr(wi, "_session_status", lambda *a: "WORKING")
        r = wi.waha_instance("remove", name="monica", confirm=True, repo_root=str(_tree(tmp_path)))
        assert r["status"] == "blocked"

    def test_remove_dry_run_snapshots_volume_first(self, tmp_path, monkeypatch):
        monkeypatch.setattr(wi, "_session_status", lambda *a: "STOPPED")
        r = wi.waha_instance("remove", name="monica", repo_root=str(_tree(tmp_path)))
        assert r["status"] == "planned" and "tar czf" in r["steps"][0]

    def test_unknown_instance_errors(self, tmp_path):
        assert wi.waha_instance("plan", name="nope", repo_root=str(_tree(tmp_path)))["status"] == "error"
