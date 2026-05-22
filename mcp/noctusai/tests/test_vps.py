"""Colocated tests for noctus.vps.* (VPS/container fleet ops over SSH).

Zero real SSH — run_remote is injected. Covers parsing of each read op, the
confirm-gating of every mutation, and the invariant that no op emits a
destructive docker token (rm / rmi / kill / down / prune -a / exec).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import vps as V  # noqa: E402


class FakeRemote:
    def __init__(self, rc=0, **outs):
        self.rc = rc
        self.outs = outs
        self.calls: list[list[str]] = []

    def __call__(self, cmd):
        self.calls.append(cmd)
        if cmd[:2] == ["docker", "ps"]:
            return (self.rc, self.outs.get("ps", ""), "")
        if cmd[:2] == ["docker", "logs"]:
            return (self.rc, self.outs.get("logs", ""), "")
        if cmd[:2] == ["docker", "inspect"]:
            return (self.rc, self.outs.get("inspect", ""), "")
        if cmd[:2] == ["docker", "images"]:
            return (self.rc, self.outs.get("images", ""), "")
        if cmd[:1] == ["sh"]:
            return (self.rc, self.outs.get("df", ""), "")
        if cmd[:3] == ["docker", "system", "df"]:
            return (self.rc, self.outs.get("dsd", ""), "")
        if cmd[:2] == ["docker", "stats"]:
            return (self.rc, self.outs.get("stats", ""), "")
        if cmd[:3] == ["docker", "image", "prune"]:
            return (self.rc, "Total reclaimed space: 1.2GB", "")
        return (self.rc, "", "")

    def flat(self):
        return " ".join(" ".join(c) for c in self.calls)


_PS = (
    "noctus-core\tghcr.io/jraphaelsst/noctus-core:latest\tUp 2 hours (healthy)\n"
    "noctus-social-wiring\tghcr.io/jraphaelsst/noctus-social-wiring:latest\tUp 1 hour (unhealthy)\n"
    "noctus-erp-imobiliario\tghcr.io/jraphaelsst/noctus-erp-imobiliario:latest\tUp 3 hours (health: starting)\n"
    "some-other\tredis:7\tUp 5 hours\n"  # non-noctus → filtered out
)


def test_ps_parses_and_filters():
    f = FakeRemote(ps=_PS)
    r = V.ps(run_remote=f)
    assert r["ok"] and r["count"] == 3  # the non-noctus row filtered
    names = {c["name"]: c["health"] for c in r["containers"]}
    assert names["noctus-core"] == "healthy"
    assert names["noctus-social-wiring"] == "unhealthy"
    assert names["noctus-erp-imobiliario"] == "starting"


def test_health_rollup_degraded():
    f = FakeRemote(ps=_PS)
    r = V.health(run_remote=f)
    assert r["status"] == "degraded" and r["exit_code"] == 1
    assert r["unhealthy"] == ["noctus-social-wiring"]
    assert "noctus-core" in r["healthy"]


def test_health_all_healthy():
    f = FakeRemote(ps="noctus-core\timg\tUp 2 hours (healthy)\n")
    r = V.health(run_remote=f)
    assert r["status"] == "healthy" and r["exit_code"] == 0


def test_logs_tail_and_grep():
    f = FakeRemote(logs="line a\nERROR boom\nline c\n")
    r = V.logs("noctus-core", lines=10, grep="ERROR", run_remote=f)
    assert r["ok"] and r["lines"] == ["ERROR boom"]
    assert ["docker", "logs", "--tail", "10", "noctus-core"] in f.calls


def test_inspect_parses_template():
    f = FakeRemote(inspect="sha256:abc|running|healthy|2026-05-22T10:00:00Z|8000/tcp ")
    r = V.inspect("noctus-core", run_remote=f)
    assert r["image_id"] == "sha256:abc" and r["state"] == "running"
    assert r["health"] == "healthy" and r["ports"] == "8000/tcp"


def test_images_filters_noctus():
    f = FakeRemote(images="ghcr.io/jraphaelsst/noctus-core:latest\tabc\t200MB\t2 hours ago\nredis:7\txyz\t30MB\t1 day ago\n")
    r = V.images(run_remote=f)
    assert r["count"] == 1 and r["images"][0]["image"].endswith("noctus-core:latest")


def test_disk_parses_use_pct():
    f = FakeRemote(df="/dev/sda1  40G  18G  22G  45% /", dsd="Images 5 2GB")
    r = V.disk(run_remote=f)
    assert r["ok"] and r["root_use_pct"] == "45%"


def test_stats_parses():
    f = FakeRemote(stats="noctus-core\t2.5%\t180MiB / 2GiB\t9%\n")
    r = V.stats(run_remote=f)
    assert r["count"] == 1 and r["stats"][0]["cpu"] == "2.5%"


# ── mutations: confirm-gating ─────────────────────────────────────
def test_restart_needs_confirm():
    f = FakeRemote()
    r = V.restart("noctus-core", run_remote=f)
    assert r["status"] == "needs_confirm"
    assert not any(c[:2] == ["docker", "restart"] for c in f.calls)


def test_restart_with_confirm():
    f = FakeRemote()
    r = V.restart("noctus-core", confirm=True, run_remote=f)
    assert r["status"] == "restarted"
    assert ["docker", "restart", "noctus-core"] in f.calls


def test_recreate_needs_confirm_then_force_recreate():
    f = FakeRemote()
    assert V.recreate("social-wiring", run_remote=f)["status"] == "needs_confirm"
    r = V.recreate("social-wiring", confirm=True, run_remote=f)
    assert r["status"] == "recreated" and "--force-recreate" in f.flat()


def test_prune_needs_confirm_and_is_dangling_only():
    f = FakeRemote()
    assert V.prune(run_remote=f)["status"] == "needs_confirm"
    r = V.prune(confirm=True, run_remote=f)
    assert r["status"] == "pruned"
    # dangling only — never -a / --all
    assert ["docker", "image", "prune", "-f"] in f.calls
    assert "-a" not in f.flat() and "--all" not in f.flat()


# ── safety invariant ──────────────────────────────────────────────
def test_no_op_emits_a_destructive_token():
    f = FakeRemote(ps=_PS)
    V.ps(run_remote=f); V.health(run_remote=f); V.logs("c", run_remote=f)
    V.inspect("c", run_remote=f); V.images(run_remote=f); V.disk(run_remote=f); V.stats(run_remote=f)
    V.restart("c", confirm=True, run_remote=f)
    V.recreate("p", confirm=True, run_remote=f)
    V.prune(confirm=True, run_remote=f)
    flat = f.flat()
    for banned in V._BANNED_TOKENS:
        assert banned not in flat, f"vps op emitted a banned token: {banned!r} in {flat!r}"


def test_register_exposes_ten_vps_tools():
    names = []

    class _Srv:
        def tool(self, name, description):
            names.append(name)
            return lambda fn: fn

    V.register(_Srv())
    assert len(names) == 10
    assert {"noctus.vps.ps", "noctus.vps.health", "noctus.vps.restart",
            "noctus.vps.prune", "noctus.vps.logs"}.issubset(set(names))
    assert all(n.startswith("noctus.vps.") for n in names)
