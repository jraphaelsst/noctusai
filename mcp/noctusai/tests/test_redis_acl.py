"""noctus.dev.redis_acl -- derivation, rendering, and BEHAVIOUR against a real redis-server.

Born from security review F3 (2026-11-10): prod Redis had no auth on the shared network and is about to
hold the fleet breaker key. The pure tests pin the rendered aclfile (default off, hashes only, fleet key
read-only for products, ops/trip scoping); the live class boots a real `redis-server` (>=7.0) with the
rendered file and proves the refusals actually fire -- a structure-green aclfile is not a behaviour-green one.
"""
from __future__ import annotations

import hashlib
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import redis_acl as ra  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
MASTER = "m" * 48

COMPOSE = """
services:
  core:      {env_file: ['../../.env'], networks: [noctus-net]}
  agents:    {env_file: ['../../.env']}
  igig:      {env_file: ['../../.env']}
  transcriber: {networks: [transcribe-net]}
"""
SCOPE = "# live\nagents\ncore\ntranscriber\n"


class TestRoster:
    def test_live_and_env_file_only(self):
        # igig loads .env but is asleep (not in scope); transcriber is live but has no .env => no Redis user.
        assert ra.derive_roster(COMPOSE, SCOPE) == ["agents", "core"]

    def test_empty_roster_refused(self):
        with pytest.raises(ValueError):
            ra.derive_roster(COMPOSE, "# nothing live\n")

    def test_unsafe_slug_refused(self):
        bad = "services:\n  'Bad Name': {env_file: ['../../.env']}\n"
        with pytest.raises(ValueError):
            ra.derive_roster(bad, "Bad Name\n")

    def test_real_roster_matches_build_scope(self):
        roster = ra.derive_roster((REPO / ra.COMPOSE_REL).read_text(), (REPO / ra.SCOPE_REL).read_text())
        live = {ln.strip() for ln in (REPO / ra.SCOPE_REL).read_text().splitlines() if ln.strip() and not ln.startswith("#")}
        assert set(roster) <= live and "core" in roster


class TestPasswords:
    def test_deterministic_and_per_user(self):
        a, b = ra.derive_password(MASTER, "core"), ra.derive_password(MASTER, "agents")
        assert a == ra.derive_password(MASTER, "core") and a != b and len(a) == 64

    def test_generation_rotates(self):
        assert ra.derive_password(MASTER, "core", "1") != ra.derive_password(MASTER, "core", "2")

    @pytest.mark.parametrize("bad", ["", "short"])
    def test_weak_master_refused(self, bad):
        with pytest.raises(ValueError):
            ra.derive_password(bad, "core")


class TestAclfile:
    ROSTER = ["agents", "core", "social-wiring"]

    def _acl(self):
        return ra.render_aclfile(self.ROSTER, MASTER)

    def _line(self, user):
        return next(ln for ln in self._acl().splitlines() if ln.startswith(f"user {user} "))

    def test_default_user_off(self):
        assert "user default off" in self._acl().splitlines()

    def test_no_plaintext_password_only_hashes(self):
        acl = self._acl()
        for u in (*self.ROSTER, "ops", "trip"):
            pw = ra.derive_password(MASTER, u)
            assert pw not in acl
            assert f"#{hashlib.sha256(pw.encode()).hexdigest()}" in acl
        assert MASTER not in acl

    def test_product_fleet_key_read_only_and_own_breaker_rw(self):
        ln = self._line("core")
        assert f"%R~{ra.FLEET_KEY}" in ln and f"%RW~{ra.FLEET_KEY}" not in ln
        assert "%RW~noctus:breaker:core:*" in ln
        assert "noctus:breaker:agents" not in ln  # never a peer's breaker keys
        assert "~noctus:breaker:*" not in ln

    def test_product_commands_exclude_dangerous_admin(self):
        ln = self._line("core")
        assert "+@all -@dangerous -@admin -@scripting" in ln
        assert "+keys" not in ln
        assert "+keys" in self._line("social-wiring")  # declared exception (NOC-REMEDIATE[redis-keys-scan])

    def test_trip_can_set_fleet_only_never_del(self):
        ln = self._line("trip")
        assert f"%RW~{ra.FLEET_KEY}" in ln and "+set" in ln and "+del" not in ln and "+@" not in ln.replace("-@all", "")

    def test_ops_scoped_to_breaker_keys_and_owns_del(self):
        ln = self._line("ops")
        assert "~noctus:breaker:*" in ln and "+del" in ln and "+rpush" in ln
        assert "+flushall" not in ln and "+config" not in ln

    def test_every_key_family_is_listed_for_products(self):
        ln = self._line("agents")
        for pat, _src in ra.APP_KEY_FAMILIES:
            assert f"~{pat}" in ln

    def test_healthcheck_ping_only(self):
        ln = next(x for x in self._acl().splitlines() if x.startswith("user healthcheck "))
        assert "nopass" in ln and "-@all +ping" in ln and "~" not in ln


class TestOverride:
    def test_committed_override_in_sync_with_derived_roster(self):
        r = ra.redis_acl("check", repo_root=str(REPO))
        assert r["ok"], r  # fix: python mcp/noctusai/cli.py --redis-acl render

    def test_no_secrets_in_override(self):
        text = ra.render_override(["core"])
        assert "PASSWORD" not in text and "env/core.env" in text and ra.DATA_NET in text

    def test_service_env_carries_creds_and_fail_closed_flag(self):
        env = ra.render_service_env("core", MASTER)
        assert "REDIS_USERNAME=core" in env and "REDIS_REQUIRE_AUTH=true" in env
        assert f"REDIS_PASSWORD={ra.derive_password(MASTER, 'core')}" in env
        assert f"REDIS_URL={ra.REDIS_URL}" in env

    def test_render_write_without_master_errors_and_leaks_nothing(self, tmp_path):
        (tmp_path / "deploy/fleet").mkdir(parents=True)
        (tmp_path / ra.COMPOSE_REL).write_text(COMPOSE)
        (tmp_path / ra.SCOPE_REL).write_text(SCOPE)
        r = ra.redis_acl("render", write=True, repo_root=str(tmp_path), env={})
        assert not r["ok"] and "REDIS_ACL_MASTER_SECRET" in r["error"]
        assert not (tmp_path / ra.OUT_DIR_REL / "users.acl").exists()

    def test_render_write_files_modes_and_no_secret_in_payload(self, tmp_path):
        (tmp_path / "deploy/fleet").mkdir(parents=True)
        (tmp_path / ra.COMPOSE_REL).write_text(COMPOSE)
        (tmp_path / ra.SCOPE_REL).write_text(SCOPE)
        r = ra.redis_acl("render", write=True, repo_root=str(tmp_path), env={ra.MASTER_ENV: MASTER})
        assert r["ok"] and MASTER not in str(r) and ra.derive_password(MASTER, "core") not in str(r)
        out = tmp_path / ra.OUT_DIR_REL
        assert (out / "env/core.env").stat().st_mode & 0o777 == 0o600
        assert (out / "ops.pass").stat().st_mode & 0o777 == 0o600
        assert ra.redis_acl("check", repo_root=str(tmp_path))["ok"]


# ── behaviour against a real redis-server ────────────────────────────────────────────────────

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.skipif(shutil.which("redis-server") is None, reason="redis-server not installed")
class TestLiveRedis:
    @pytest.fixture(scope="class")
    def server(self, tmp_path_factory):
        redis = pytest.importorskip("redis")
        d = tmp_path_factory.mktemp("redis")
        roster = ["agents", "core", "social-wiring"]
        (d / "users.acl").write_text(ra.render_aclfile(roster, MASTER))
        port = _free_port()
        proc = subprocess.Popen(
            ["redis-server", "--port", str(port), "--bind", "127.0.0.1", "--dir", str(d),
             "--aclfile", str(d / "users.acl"), "--save", "", "--appendonly", "no"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(50):
                try:
                    socket.create_connection(("127.0.0.1", port), 0.1).close()
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                pytest.skip("redis-server did not start")
            yield port, redis
        finally:
            proc.terminate()
            proc.wait(5)

    def _c(self, server, user):
        port, redis = server
        return redis.Redis(port=port, username=user, password=ra.derive_password(MASTER, user), decode_responses=True)

    def test_unauthenticated_and_default_user_refused(self, server):
        port, redis = server
        with pytest.raises(redis.exceptions.AuthenticationError if hasattr(redis.exceptions, "AuthenticationError") else Exception):
            redis.Redis(port=port).get("k")
        with pytest.raises(Exception):
            redis.Redis(port=port, username="default", password="").get("k")

    def test_healthcheck_pings_nothing_else(self, server):
        port, redis = server
        c = redis.Redis(port=port, username="healthcheck", password="x")
        assert c.ping()
        with pytest.raises(redis.exceptions.NoPermissionError):
            c.get("nai_session:x")

    def test_product_uses_every_app_family_incl_lua(self, server):
        c = self._c(server, "core")
        for pat, _ in ra.APP_KEY_FAMILIES:
            k = pat.replace("*", "probe")
            assert c.set(k, "1", ex=60), k
            assert c.get(k) == "1"
        # limits' Lua INCR+EXPIRE shape: EVAL under the caller's key permissions
        assert c.eval("return redis.call('incr', KEYS[1])", 1, "LIMITSprobe-lua") >= 1
        sha = c.script_load("return 1")
        assert c.evalsha(sha, 0) == 1
        c.xadd("rt:wa:conn:1", {"a": "b"})
        c.zadd("queue:conversation_due", {"c1": 1})

    def test_product_cannot_touch_fleet_key_or_peer_breaker(self, server):
        ops = self._c(server, "ops")
        ops.set(ra.FLEET_KEY, "{}")
        c, peer = self._c(server, "core"), self._c(server, "agents")
        _, redis = server
        assert c.get(ra.FLEET_KEY) == "{}"  # read-only is exactly what the breaker needs
        for call in (lambda: c.set(ra.FLEET_KEY, "x"), lambda: c.delete(ra.FLEET_KEY),
                     lambda: c.set("noctus:breaker:agents:worker:x", "x"), lambda: c.rpush(ra.AUDIT_KEY, "x"),
                     lambda: c.expire(ra.FLEET_KEY, 1)):
            with pytest.raises(redis.exceptions.NoPermissionError):
                call()
        assert c.set("noctus:breaker:core:worker:x", "1") and c.mget([ra.FLEET_KEY, "noctus:breaker:core:worker:x"])
        assert c.delete("noctus:breaker:core:worker:x") == 1
        with pytest.raises(redis.exceptions.NoPermissionError):
            peer.set("noctus:breaker:core:worker:x", "x")

    def test_product_cannot_run_admin_or_dangerous_commands(self, server):
        c = self._c(server, "core")
        _, redis = server
        for call in (c.flushall, c.flushdb, lambda: c.config_get("*"), lambda: c.keys("*"), c.shutdown,
                     lambda: c.execute_command("ACL", "LIST"), lambda: c.execute_command("SORT", "x"),
                     lambda: c.script_flush(), lambda: c.script_kill(), lambda: c.execute_command("FUNCTION", "FLUSH"), lambda: c.client_list()):
            with pytest.raises(redis.exceptions.NoPermissionError):
                call()

    def test_only_declared_exception_may_use_keys(self, server):
        sw = self._c(server, "social-wiring")
        sw.set("download:cache:a", "1")
        assert "download:cache:a" in sw.keys("download:cache:*")

    def test_unlisted_key_family_denied(self, server):
        c = self._c(server, "core")
        _, redis = server
        with pytest.raises(redis.exceptions.NoPermissionError):
            c.set("something:else", "1")

    def test_trip_sets_fleet_nx_but_cannot_delete_or_touch_others(self, server):
        port, redis = server
        trip = self._c(server, "trip")
        ops = self._c(server, "ops")
        ops.delete(ra.FLEET_KEY)
        assert trip.set(ra.FLEET_KEY, '{"by":"offhost-watchdog"}', nx=True)
        assert trip.set(ra.FLEET_KEY, "other", nx=True) is None  # an earlier trip stands
        assert trip.exists(ra.FLEET_KEY) == 1
        for call in (lambda: trip.delete(ra.FLEET_KEY), lambda: trip.set("noctus:breaker:core:x", "1"),
                     lambda: trip.rpush(ra.AUDIT_KEY, "x"), lambda: trip.get("nai_session:x")):
            with pytest.raises(redis.exceptions.NoPermissionError):
                call()

    def test_ops_rearms_audits_and_scans_but_nothing_else(self, server):
        _, redis = server
        ops = self._c(server, "ops")
        ops.set(ra.FLEET_KEY, "{}")
        assert ops.delete(ra.FLEET_KEY) == 1  # the ONLY identity that may re-arm
        ops.rpush(ra.AUDIT_KEY, "{}")
        assert ops.lrange(ra.AUDIT_KEY, 0, -1)
        assert list(ops.scan_iter(match="noctus:breaker:*")) is not None
        for call in (lambda: ops.get("nai_session:x"), ops.flushall, lambda: ops.config_get("*")):
            with pytest.raises(redis.exceptions.NoPermissionError):
                call()
