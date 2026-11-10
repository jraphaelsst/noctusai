"""Every prod compose call carries the Redis-auth override (security review round 2, P1-1).

Hazard: a recreate with only `-f docker-compose.prod.yml` silently returns a locked product to the old,
unauthenticated Redis. deploy_image (deploy + rollback), vps.recreate and ensure_product_url_roster
must add the override when it exists, and refuse loudly when a listed service lacks its generated env.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import _redis_auth_compose as RC  # noqa: E402
from tools.noctus.dev import deploy_image as DI  # noqa: E402
from tools.noctus.dev import vps as V  # noqa: E402

FLEET = "/opt/noctus/noctusai/deploy/fleet"
BASE = f"{FLEET}/docker-compose.prod.yml"
OVERRIDE = f"{FLEET}/compose.redis-auth.prod.yml"


class Host:
    """Minimal deploy host: files present, listed services, redis container state."""

    def __init__(self, override=True, listed=("core",), env_files=("core",), redis_running=True, test_rc=None):
        self.override, self.listed, self.env_files = override, set(listed), set(env_files)
        self.redis_running, self.test_rc = redis_running, test_rc
        self.calls: list[list[str]] = []

    def __call__(self, cmd):
        self.calls.append(cmd)
        if cmd[:2] == ["test", "-f"]:
            return (self.test_rc if self.test_rc is not None else (0 if self.override else 1), "", "")
        if cmd[0] == "grep":
            return (0 if cmd[2].strip("^ :$") in self.listed else 1, "", "")
        if cmd[:2] == ["test", "-s"]:
            return (0 if Path(cmd[2]).stem in self.env_files else 1, "", "")
        if cmd[:3] == ["docker", "inspect", "-f"] and cmd[-1] == RC.REDIS_ACL_CONTAINER:
            return (0, "true\n" if self.redis_running else "false\n", "")
        return (0, "", "")

    def compose_calls(self):
        return [c for c in self.calls if c[:2] == ["docker", "compose"]]


class TestPlan:
    def test_no_override_file_means_no_extra_files(self):
        p = RC.plan(Host(override=False), BASE, "core")
        assert p["files"] == [] and p["error"] is None

    def test_override_present_is_always_added(self):
        p = RC.plan(Host(), BASE, "core")
        assert p["files"] == [OVERRIDE] and p["error"] is None and p["listed"]

    def test_unlisted_service_still_gets_the_file_without_env_demands(self):
        p = RC.plan(Host(listed=("core",), env_files=()), BASE, "transcriber")
        assert p["files"] == [OVERRIDE] and p["error"] is None and not p["listed"]

    def test_listed_service_without_generated_env_refuses_loudly(self):
        p = RC.plan(Host(env_files=()), BASE, "core")
        assert p["error"] and "env file" in p["error"] and "silently" in p["error"]

    def test_refuses_when_acl_redis_not_running(self):
        p = RC.plan(Host(redis_running=False), BASE, "core")
        assert p["error"] and RC.REDIS_ACL_CONTAINER in p["error"]

    def test_unverifiable_probe_is_not_treated_as_absent(self):
        p = RC.plan(Host(test_rc=255), BASE, "core")
        assert p["error"] and "unverifiable" in p["error"]

    def test_explicit_off_is_the_only_escape(self):
        p = RC.plan(Host(env_files=()), BASE, "core", mode="off")
        assert p["files"] == [] and p["error"] is None and p["mode"] == "off"
        assert RC.plan(Host(), BASE, "core", mode="bogus")["error"]


class TestVpsRecreate:
    def test_recreate_adds_override(self):
        h = Host()
        r = V.recreate("core", confirm=True, run_remote=h)
        assert r["status"] == "recreated"
        assert h.compose_calls()[0][:6] == ["docker", "compose", "-f", BASE, "-f", OVERRIDE]

    def test_recreate_refuses_without_env_and_runs_no_compose(self):
        h = Host(env_files=())
        r = V.recreate("core", confirm=True, run_remote=h)
        assert not r["ok"] and not h.compose_calls()


class TestDeployImage:
    def test_cmd_builder_shape(self):
        assert RC.compose_cmd(BASE, [OVERRIDE], "up", "-d", "x") == [
            "docker", "compose", "-f", BASE, "-f", OVERRIDE, "up", "-d", "x"]

    def test_deploy_image_refuses_before_touching_the_container(self):
        h = Host(env_files=())
        r = DI.deploy_image("core", run_remote=h, confirm=True, sleep=lambda s: None, live_products_fn=lambda: [],
                            local_diff=lambda o, n: (True, [], ""))
        assert r["status"] == "error" and "env file" in r["error"]
        assert not h.compose_calls() and not any(c[:2] == ["docker", "commit"] for c in h.calls)
