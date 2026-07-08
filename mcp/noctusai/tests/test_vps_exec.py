"""Tests for noctus.vps.exec — bounded diagnostic exec (zero real SSH).

`run_remote` is injected so no SSH happens. Pins: the 3-tier safety model
(read-allowlist runs free, hard-deny always refuses, else confirm-gated), the
docker-exec container wrapping, and origin-curl / file-read shapes.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "mcp" / "noctusai"))

from tools.noctus.dev.vps_exec import exec_cmd, _is_read_only, _hard_denied


def _fake_run(captured):
    def _run(cmd):
        captured["cmd"] = cmd
        return (0, "OUTPUT", "")
    return _run


# ── read-allowlist runs WITHOUT confirm ──────────────────────────────


def test_read_only_grep_runs_free():
    cap = {}
    out = exec_cmd("grep -c _is_service_worker /app/x.py", run_remote=_fake_run(cap))
    assert out["ok"] is True
    assert out["read_only"] is True
    assert out["stdout"] == "OUTPUT"
    assert cap["cmd"].startswith("sh -lc ")


def test_curl_origin_localhost_runs_free():
    """The key origin-direct use case (bypass CloudFlare)."""
    cap = {}
    out = exec_cmd("curl -sS -D- http://localhost:8001/sw.js", run_remote=_fake_run(cap))
    assert out["ok"] is True and out["read_only"] is True


def test_container_exec_wraps_docker_exec():
    cap = {}
    out = exec_cmd("cat /app/seed/framework/backend/noctusai_seed/app.py",
                   container="noctus-erp-imobiliario", run_remote=_fake_run(cap))
    assert out["ok"] is True
    assert cap["cmd"].startswith("docker exec noctus-erp-imobiliario sh -lc ")


def test_docker_inspect_is_read_only():
    assert _is_read_only("docker inspect noctus-core") is True
    assert _is_read_only("docker ps -a") is True
    assert _is_read_only("docker system df") is True


# ── hard-deny ALWAYS refuses (even with confirm) ─────────────────────


def test_hard_deny_rm_rf_refused_even_confirmed():
    cap = {}
    out = exec_cmd("rm -rf /opt/noctus", confirm=True, run_remote=_fake_run(cap))
    assert out["status"] == "refused"
    assert "cmd" not in cap  # NEVER reached the runner

def test_hard_deny_docker_rm_refused():
    out = exec_cmd("docker rm -f noctus-core", confirm=True, run_remote=_fake_run({}))
    assert out["status"] == "refused"

def test_hard_deny_compose_down_refused():
    out = exec_cmd("docker compose down", confirm=True, run_remote=_fake_run({}))
    assert out["status"] == "refused"

def test_hard_denied_detects_tokens():
    assert _hard_denied("mkfs.ext4 /dev/sda") is not None
    assert _hard_denied("shutdown -h now") is not None
    assert _hard_denied("cat /etc/hostname") is None


# ── confirm-gate for non-read, non-denied ────────────────────────────


def test_non_read_needs_confirm():
    cap = {}
    out = exec_cmd("pip install requests", run_remote=_fake_run(cap))
    assert out["status"] == "needs_confirm"
    assert "cmd" not in cap  # gate fired before the runner

def test_non_read_runs_with_confirm():
    cap = {}
    out = exec_cmd("pip install requests", confirm=True, run_remote=_fake_run(cap))
    assert out["ok"] is True
    assert "cmd" in cap  # ran after confirm


# ── misc ──────────────────────────────────────────────────────────────


def test_empty_command_errors():
    out = exec_cmd("   ", run_remote=_fake_run({}))
    assert out["ok"] is False and out["status"] == "error"


def test_nonzero_exit_surfaced_not_faked():
    def _run(cmd):
        return (2, "", "grep: no such file")
    out = exec_cmd("grep x /nope", run_remote=_run)
    assert out["ok"] is False
    assert out["status"] == "nonzero_exit"
    assert out["exit_code"] == 2
