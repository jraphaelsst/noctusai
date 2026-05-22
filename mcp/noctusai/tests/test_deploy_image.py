"""Colocated tests for noctus.dev.deploy_image (C2 atomic image rollback).

Zero real SSH, zero real waiting — run_remote + sleep are injected. Covers
planned (dry-run) / up_to_date / deployed / rolled_back / error / pull-failure,
the safe docker+compose allowlists, and the load-bearing safety invariant: a
confirmed deploy NEVER emits a destructive docker token (rmi/prune/down/...).
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import deploy_image as DI  # noqa: E402


def _now():
    return dt.datetime(2026, 5, 22, 12, 0, 0)


class FakeDocker:
    """Scripts remote docker/compose IO. Health is a sequence consumed across
    poll calls (so deploy→unhealthy→rollback→healthy is expressible)."""

    def __init__(self, current="sha-old", pulled="sha-new", health=("healthy",),
                 pull_rc=0, up_rc=0, container_found=True):
        self.current, self.pulled = current, pulled
        self.health = list(health)
        self.pull_rc, self.up_rc, self.container_found = pull_rc, up_rc, container_found
        self.calls: list[list[str]] = []
        self._h = 0

    def __call__(self, cmd):
        self.calls.append(cmd)
        if cmd[:2] == ["docker", "inspect"]:
            tmpl = cmd[3]
            if ".Image" in tmpl:
                if not self.container_found:
                    return (1, "", "Error: No such object")
                return (0, self.current + "\n", "")
            st = self.health[self._h] if self._h < len(self.health) else self.health[-1]
            self._h += 1
            return (0, st + "\n", "")
        if cmd[:3] == ["docker", "image", "inspect"]:
            return (0, self.pulled + "\n", "")
        if cmd[:2] == ["docker", "tag"]:
            return (0, "", "")
        if cmd[:3] == ["docker", "compose", "-f"]:
            action = cmd[4]
            if action == "pull":
                return (self.pull_rc, "", "" if self.pull_rc == 0 else "manifest unknown")
            if action == "up":
                return (self.up_rc, "", "" if self.up_rc == 0 else "no such image")
        return (0, "", "")

    def flat(self):
        return " ".join(" ".join(c) for c in self.calls)

    def count(self, action):  # compose action occurrences
        return sum(1 for c in self.calls if c[:3] == ["docker", "compose", "-f"] and c[4] == action)


def _run(fake, **kw):
    return DI.deploy_image("core", run_remote=fake, sleep=lambda s: None, now=_now, **kw)


def test_dry_run_is_read_only():
    f = FakeDocker()
    r = _run(f, confirm=False)
    assert r["status"] == "planned" and r["exit_code"] == 0
    assert r["current_image_id"] == "sha-old"
    # no mutation: no tag / pull / up
    assert "tag" not in f.flat() and f.count("pull") == 0 and f.count("up") == 0


def test_deployed_when_healthy():
    f = FakeDocker(current="sha-old", pulled="sha-new", health=("healthy",))
    r = _run(f, confirm=True)
    assert r["status"] == "deployed" and r["exit_code"] == 0
    assert r["new_image_id"] == "sha-new" and r["health"] == "healthy"
    # snapshot taken, pulled once, recreated once, no rollback (single up)
    assert ["docker", "tag", "sha-old", "ghcr.io/jraphaelsst/noctus-core:previous"] in f.calls
    assert f.count("pull") == 1 and f.count("up") == 1


def test_up_to_date_when_pulled_equals_running():
    f = FakeDocker(current="same", pulled="same")
    r = _run(f, confirm=True)
    assert r["status"] == "up_to_date" and f.count("up") == 0  # no recreate


def test_rolled_back_on_unhealthy():
    # new image unhealthy on first probe; rollback re-probe healthy.
    f = FakeDocker(current="sha-old", pulled="sha-new", health=("unhealthy", "healthy"))
    r = _run(f, confirm=True)
    assert r["status"] == "rolled_back" and r["exit_code"] == 1
    assert r["health"] == "unhealthy" and r["rollback_health"] == "healthy"
    # restored :latest to the snapshot id, recreated twice (deploy + rollback)
    assert ["docker", "tag", "sha-old", "ghcr.io/jraphaelsst/noctus-core:latest"] in f.calls
    assert f.count("up") == 2


def test_error_when_container_not_found():
    f = FakeDocker(container_found=False)
    r = _run(f, confirm=True)
    assert r["status"] == "error" and "not found" in r["error"]
    assert f.count("up") == 0  # nothing touched


def test_pull_failure_aborts_without_touching_container():
    f = FakeDocker(pull_rc=1)
    r = _run(f, confirm=True)
    assert r["status"] == "error" and "pull" in r["reason"]
    assert f.count("up") == 0  # container left running on the current image


def test_never_emits_destructive_docker_tokens():
    f = FakeDocker(current="sha-old", pulled="sha-new", health=("unhealthy", "healthy"))
    _run(f, confirm=True)  # exercise the full deploy + rollback path
    flat = f.flat()
    for banned in DI._BANNED_TOKENS:
        assert banned not in flat, f"deploy_image emitted a banned token: {banned!r}"


def test_docker_allowlist_blocks_destructive():
    calls = []
    try:
        DI._docker(lambda cmd: calls.append(cmd) or (0, "", ""), "rmi", "x")
        assert False, "expected ValueError for docker rmi"
    except ValueError as e:
        assert "allowlist" in str(e)
    assert calls == []


def test_compose_allowlist_blocks_down():
    calls = []
    try:
        DI._compose(lambda cmd: calls.append(cmd) or (0, "", ""), "cf", "down")
        assert False, "expected ValueError for compose down"
    except ValueError as e:
        assert "allowlist" in str(e)
    assert calls == []


def test_poll_health_waits_through_starting():
    f = FakeDocker(health=("starting", "starting", "healthy"))
    naps = []
    status, states = DI._poll_health(f, lambda s: naps.append(s), "noctus-core", 150, 10)
    assert status == "healthy" and states[-1] == "healthy"
    assert len(naps) == 2  # slept twice while 'starting'


def test_tool_registers_with_dotted_name():
    captured = {}

    class _Srv:
        def tool(self, name, description):
            captured["name"] = name
            return lambda fn: fn

    DI.register(_Srv())
    assert captured["name"] == "noctus.dev.deploy_image"
