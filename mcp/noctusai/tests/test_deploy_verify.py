"""Colocated tests for noctus.dev.deploy_verify (the independent prod
revision-drift witness — 2026-08-13 phantom-deploy hole).

Zero real SSH / git — `run_remote` (the `vps_exec.exec_cmd` seam, a full
shell-command STRING per call, not a list) and `run_local` (the git
resolution of the prod tip) are both injected. Covers: verified / drift /
unverifiable / degraded / container-not-found / expected-sha-unresolvable,
plus the compose-roster parser and the explicit products= override.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "mcp" / "noctusai"))

from tools.noctus.dev import deploy_verify as DV  # noqa: E402

_CONTAINER_RE = re.compile(r"noctus-([a-z0-9-]+)")

_COMPOSE_YML = """\
services:
  core:
    container_name: noctus-core
    expose:
      - "8000"
  seed:
    container_name: noctus-seed
    expose:
      - "8004"
"""


class FakeVps:
    """Fakes the `run_remote` seam `vps_exec.exec_cmd` calls with — a single
    shell-command STRING per invocation (e.g. `"docker inspect -f '...' \
    noctus-core"` or `"docker exec noctus-core sh -lc 'curl ...'"`)."""

    def __init__(self, containers: dict[str, dict] | None = None):
        # slug -> {found, state, health, revision, probe_ok, health_body}
        self.containers = containers or {}
        self.calls: list[str] = []

    def __call__(self, cmd: str) -> tuple[int, str, str]:
        self.calls.append(cmd)
        m = _CONTAINER_RE.search(cmd)
        slug = m.group(1) if m else ""
        info = self.containers.get(slug, {})
        if "curl" in cmd:  # the in-container /api/health active probe
            if info.get("probe_ok", True):
                body = info.get("health_body", {"status": "ok", "startup_hook_error": None})
                return 0, json.dumps(body), ""
            return 1, "", "curl: (7) Failed to connect: Connection refused"
        # docker inspect
        if not info.get("found", True):
            return 1, "", f"Error: No such object: noctus-{slug}"
        parts = [
            info.get("state", "running"),
            info.get("health", "healthy"),
            info.get("revision", ""),
        ]
        return 0, "|".join(parts) + "\n", ""

    def flat(self) -> str:
        return " | ".join(self.calls)


def _run_local(sha="PRODSHA000000000000", fetch_rc=0, rev_rc=0):
    def _git(cmd: list[str]) -> tuple[int, str, str]:
        if cmd[:2] == ["git", "fetch"]:
            return (fetch_rc, "", "" if fetch_rc == 0 else "network unreachable")
        if cmd[:2] == ["git", "rev-parse"]:
            return (rev_rc, (sha + "\n") if rev_rc == 0 else "", "" if rev_rc == 0 else "unknown revision")
        return (0, "", "")
    return _git


def _entries(*slugs):
    return [{"slug": s, "container": f"noctus-{s}", "port": "8000"} for s in slugs]


# ── overall verdict paths ────────────────────────────────────────────
def test_verified_when_every_product_matches_and_healthy():
    sha = "PRODSHA000000000000"
    vps = FakeVps({
        "core": {"revision": sha},
        "seed": {"revision": sha},
    })
    r = DV.deploy_verify(products=["core", "seed"], run_remote=vps, run_local=_run_local(sha=sha),
                         repo_root=str(_REPO_ROOT))
    assert r["status"] == "verified" and r["exit_code"] == 0
    assert r["drifted"] == [] and r["degraded"] == [] and r["unverifiable"] == []
    assert all(p["drift"] is False for p in r["products"])


def test_drift_detected_is_the_phantom_deploy_signal():
    # exactly the 2026-08-13 shape: container still on the OLD revision even
    # though prod's tip has moved on.
    sha = "NEWSHA0000000000000"
    vps = FakeVps({"core": {"revision": "OLDSHA0000000000000"}})
    r = DV.deploy_verify(products=["core"], run_remote=vps, run_local=_run_local(sha=sha),
                         repo_root=str(_REPO_ROOT))
    assert r["status"] == "drift_detected" and r["exit_code"] == 1
    assert r["drifted"] == ["core"]
    assert r["products"][0]["revision"] == "OLDSHA0000000000000"
    assert r["products"][0]["expected_sha"] == sha


def test_container_not_found_counts_as_drift_not_a_pass():
    sha = "PRODSHA000000000000"
    vps = FakeVps({"core": {"found": False}})
    r = DV.deploy_verify(products=["core"], run_remote=vps, run_local=_run_local(sha=sha),
                         repo_root=str(_REPO_ROOT))
    assert r["status"] == "drift_detected"
    assert r["products"][0]["found"] is False and r["products"][0]["drift"] is True


def test_unlabeled_image_is_unverifiable_never_silently_clean():
    sha = "PRODSHA000000000000"
    vps = FakeVps({"core": {"revision": ""}})  # no OCI label — predates the guard
    r = DV.deploy_verify(products=["core"], run_remote=vps, run_local=_run_local(sha=sha),
                         repo_root=str(_REPO_ROOT))
    assert r["status"] == "unverifiable" and r["exit_code"] == 1
    assert r["products"][0]["drift"] is None
    assert "UNVERIFIABLE" in r["products"][0]["note"]


def test_startup_hook_error_is_degraded_even_with_matching_revision():
    sha = "PRODSHA000000000000"
    vps = FakeVps({"core": {
        "revision": sha,
        "health_body": {"status": "ok", "startup_hook_error": "ConnectionError: PostgREST unreachable"},
    }})
    r = DV.deploy_verify(products=["core"], run_remote=vps, run_local=_run_local(sha=sha),
                         repo_root=str(_REPO_ROOT))
    assert r["status"] == "degraded" and r["exit_code"] == 1
    assert r["products"][0]["drift"] is False
    assert r["products"][0]["startup_hook_error"] == "ConnectionError: PostgREST unreachable"


def test_unreachable_health_probe_is_degraded():
    sha = "PRODSHA000000000000"
    vps = FakeVps({"core": {"revision": sha, "probe_ok": False}})
    r = DV.deploy_verify(products=["core"], run_remote=vps, run_local=_run_local(sha=sha),
                         repo_root=str(_REPO_ROOT))
    assert r["status"] == "degraded"
    assert r["products"][0]["health_probe"] == "unreachable"


def test_drift_takes_priority_over_degraded():
    sha = "PRODSHA000000000000"
    vps = FakeVps({
        "core": {"revision": "OLD", "probe_ok": False},  # drifted AND unreachable
        "seed": {"revision": sha},
    })
    r = DV.deploy_verify(products=["core", "seed"], run_remote=vps, run_local=_run_local(sha=sha),
                         repo_root=str(_REPO_ROOT))
    assert r["status"] == "drift_detected"
    assert r["drifted"] == ["core"]


# ── expected-sha resolution: fail-closed, never a silent pass ────────
def test_unresolvable_prod_tip_refuses_to_verify_anything():
    vps = FakeVps({"core": {"revision": "X"}})
    r = DV.deploy_verify(products=["core"], run_remote=vps, run_local=_run_local(rev_rc=1),
                         repo_root=str(_REPO_ROOT))
    assert r["status"] == "error" and r["ok"] is False
    assert "cannot resolve" in r["error"]
    assert vps.calls == []  # never even attempted to inspect anything


def test_git_fetch_failure_also_refuses():
    vps = FakeVps({})
    r = DV.deploy_verify(products=["core"], run_remote=vps, run_local=_run_local(fetch_rc=1),
                         repo_root=str(_REPO_ROOT))
    assert r["status"] == "error"


def test_expected_sha_is_never_the_callers_parameter():
    """No `expected_sha=` / `sha=` kwarg exists on the public signature — the
    ONLY way to influence it is which prod_branch/remote to resolve, never a
    literal value. This is the structural guarantee the incident review asked
    for (a caller cannot pass the wrong answer and get a green)."""
    import inspect
    sig = inspect.signature(DV.deploy_verify)
    assert "sha" not in sig.parameters and "expected_sha" not in sig.parameters


# ── compose-roster parsing (no products= override) ───────────────────
def test_roster_derives_from_the_prod_compose_file(tmp_path):
    (tmp_path / "compose.yml").write_text(_COMPOSE_YML)
    sha = "PRODSHA000000000000"
    vps = FakeVps({"core": {"revision": sha}, "seed": {"revision": sha}})
    r = DV.deploy_verify(run_remote=vps, run_local=_run_local(sha=sha),
                         repo_root=str(tmp_path), compose_file="compose.yml")
    assert r["checked"] == 2
    assert {p["product"] for p in r["products"]} == {"core", "seed"}
    # the port came from the compose file's `expose:` — the health probe ran
    assert any("curl" in c for c in vps.calls)


def test_missing_compose_file_errors_when_no_products_override(tmp_path):
    r = DV.deploy_verify(run_remote=FakeVps({}), run_local=_run_local(),
                         repo_root=str(tmp_path), compose_file="nope.yml")
    assert r["status"] == "error" and "compose file not found" in r["error"]


def test_products_override_survives_a_missing_compose_file(tmp_path):
    """products= is explicit intent — a missing/unreadable compose file must
    degrade to no-port-probe, never block the caller's explicit request."""
    sha = "PRODSHA000000000000"
    vps = FakeVps({"core": {"revision": sha}})
    r = DV.deploy_verify(products=["core"], run_remote=vps, run_local=_run_local(sha=sha),
                         repo_root=str(tmp_path), compose_file="nope.yml")
    assert r["status"] == "verified"
    assert r["products"][0]["port"] is None
    assert r["products"][0]["health_probe"].startswith("skipped")
