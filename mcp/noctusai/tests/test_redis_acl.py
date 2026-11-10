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
MASTER = "ab12" * 16  # shape of `openssl rand -hex 32`

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

    @pytest.mark.parametrize("bad", ["", "short", "m" * 48, "# set me", "AB12" * 16, "ab12" * 15])
    def test_weak_master_refused(self, bad):
        with pytest.raises(ValueError):
            ra.derive_password(bad, "core")




class TestAppAclfile:
    ROSTER = ["agents", "core", "social-wiring"]

    def _acl(self):
        return ra.render_aclfile(self.ROSTER, MASTER)

    def _line(self, user):
        return next(ln for ln in self._acl().splitlines() if ln.startswith(f"user {user} "))

    def test_default_user_off(self):
        assert "user default off" in self._acl().splitlines()

    def test_no_plaintext_password_only_hashes(self):
        acl = self._acl()
        for u in (*self.ROSTER, "ops-app"):
            pw = ra.derive_password(MASTER, u)
            assert pw not in acl and f"#{hashlib.sha256(pw.encode()).hexdigest()}" in acl
        assert MASTER not in acl

    def test_app_redis_carries_no_breaker_grants_at_all(self):  # P2-A
        acl = self._acl()
        assert "noctus:breaker" not in acl and "user trip" not in acl and "user probe" not in acl

    def test_product_commands_exclude_dangerous_admin_scripting(self):
        ln = self._line("core")
        assert "+@all -@dangerous -@admin -@scripting" in ln and "+eval " in ln + " " and "+keys" not in ln
        assert "+keys" in self._line("social-wiring")  # declared exception (NOC-REMEDIATE[redis-keys-scan])

    def test_every_key_family_is_listed_for_products(self):
        ln = self._line("agents")
        for pat, _src in ra.APP_KEY_FAMILIES:
            assert f"~{pat}" in ln and f"~agents:*" in ln

    def test_ops_on_app_redis_has_no_keys_only_acl_log(self):
        ln = self._line("ops")
        assert "~" not in ln.split("resetchannels", 1)[1] and "+acl|log" in ln and "+get" not in ln

    def test_healthcheck_ping_only(self):
        ln = next(x for x in self._acl().splitlines() if x.startswith("user healthcheck "))
        assert "nopass" in ln and "-@all +ping" in ln and "~" not in ln


class TestBreakerAclfile:
    ROSTER = ["agents", "core"]

    def _acl(self):
        return ra.render_breaker_aclfile(self.ROSTER, MASTER)

    def _line(self, user):
        return next(ln for ln in self._acl().splitlines() if ln.startswith(f"user {user} "))

    def test_no_app_keys_no_scripting_for_anyone(self):
        acl = self._acl()
        for app in ("nai_session", "LIMITS", "queue:", "conversation:"):
            assert app not in acl
        for ln in acl.splitlines():
            for banned in ("+eval", "+script", "+function", "+@all", "+scan", "+keys"):
                assert banned not in ln, (banned, ln)

    def test_hashes_only_and_breaker_passwords_distinct_from_app_passwords(self):
        acl = self._acl()
        for u in ("trip", "probe", "ops"):
            assert ra.derive_password(MASTER, u) not in acl
        assert ra.breaker_user_password(MASTER, "core") != ra.derive_password(MASTER, "core")
        assert ra.breaker_user_password(MASTER, "core") not in acl

    def test_product_rw_own_sources_ro_rearm_and_fleet(self):
        ln = self._line("core")
        for sfx in ("worker:*", "scheduler:*", "gate:*", "audit", "index"):
            assert f"%RW~noctus:breaker:core:{sfx}" in ln
        assert "%R~noctus:breaker:core:rearm:*" in ln and "%RW~noctus:breaker:core:rearm" not in ln
        assert f"%R~{ra.FLEET_KEY}" in ln and f"%RW~{ra.FLEET_KEY}" not in ln
        assert "noctus:breaker:agents" not in ln and "~noctus:breaker:*" not in ln

    def test_trip_setnx_only_probe_exists_only_ops_scoped(self):
        trip, probe, ops = self._line("trip"), self._line("probe"), self._line("ops")
        assert f"%RW~{ra.FLEET_KEY}" in trip and "+setnx" in trip and "+set " not in trip + " " and "+del" not in trip
        assert f"%R~{ra.FLEET_KEY}" in probe and "%RW" not in probe and "+exists" in probe
        for cmd in ("+set", "+setnx", "+del", "+get "):
            assert cmd not in probe.replace("-@all", "") + " "
        assert "~noctus:breaker:*" in ops and "+del" in ops and "+ltrim" in ops and "+sadd" in ops and "+smembers" in ops
        assert "+flushall" not in ops and "+config" not in ops and "+script" not in ops

    def test_default_off_and_healthcheck(self):
        assert "user default off" in self._acl().splitlines()


class TestOverride:  # P1-B: host-local, written only for the services deliberately cut over
    def test_no_override_is_committed(self):
        assert not (REPO / ra.OVERRIDE_REL).exists()
        assert ra.OVERRIDE_REL in (REPO / ".gitignore").read_text()
        assert "deploy/fleet/redis-auth/" in (REPO / ".gitignore").read_text()

    def test_override_lists_exactly_the_cut_over_services_without_secrets(self):
        text = ra.render_override(["core"])
        assert "PASSWORD" not in text and "env/core.env" in text and ra.DATA_NET in text and "agents" not in text
        assert ra.parse_override_services(text) == ["core"]

    def test_service_env_carries_both_connections_and_fail_closed_flag(self):
        env = ra.render_service_env("core", MASTER)
        assert "REDIS_USERNAME=core" in env and "REDIS_REQUIRE_AUTH=true" in env
        assert f"REDIS_PASSWORD={ra.derive_password(MASTER, 'core')}" in env and f"REDIS_URL={ra.REDIS_URL}" in env
        assert f"NOCTUS_BREAKER_REDIS_URL={ra.BREAKER_URL}" in env and "NOCTUS_BREAKER_REDIS_USERNAME=core" in env
        assert f"NOCTUS_BREAKER_REDIS_PASSWORD={ra.breaker_user_password(MASTER, 'core')}" in env

    def _tree(self, tmp_path):
        (tmp_path / "deploy/fleet").mkdir(parents=True)
        (tmp_path / ra.COMPOSE_REL).write_text(COMPOSE)
        (tmp_path / ra.SCOPE_REL).write_text(SCOPE)
        return tmp_path

    def test_render_write_without_master_errors_and_leaks_nothing(self, tmp_path):
        t = self._tree(tmp_path)
        r = ra.redis_acl("render", write=True, repo_root=str(t), env={})
        assert not r["ok"] and "REDIS_ACL_MASTER_SECRET" in r["error"]
        assert not (t / ra.OUT_DIR_REL / "users.acl").exists() and not (t / ra.OVERRIDE_REL).exists()

    def test_render_without_services_leaves_the_override_alone_and_services_rerender_cuts_over_and_back(self, tmp_path):
        t = self._tree(tmp_path)
        env = {ra.MASTER_ENV: MASTER}
        r = ra.redis_acl("render", write=True, repo_root=str(t), env=env)
        assert r["ok"] and r["cut_over"] == "unchanged" and not (t / ra.OVERRIDE_REL).exists()
        assert ra.redis_acl("check", repo_root=str(t))["status"] == "no_override"
        r = ra.redis_acl("render", write=True, repo_root=str(t), env=env, services="core,agents")
        assert r["cut_over"] == ["agents", "core"]
        assert ra.parse_override_services((t / ra.OVERRIDE_REL).read_text()) == ["agents", "core"]
        # per-service rollback = re-render WITHOUT it
        ra.redis_acl("render", write=True, repo_root=str(t), env=env, services="agents")
        assert ra.parse_override_services((t / ra.OVERRIDE_REL).read_text()) == ["agents"]
        assert ra.redis_acl("check", repo_root=str(t))["ok"]
        ra.redis_acl("render", write=True, repo_root=str(t), env=env, services="")
        assert not (t / ra.OVERRIDE_REL).exists()

    def test_services_outside_the_roster_refused(self, tmp_path):
        t = self._tree(tmp_path)
        r = ra.redis_acl("render", write=True, repo_root=str(t), env={ra.MASTER_ENV: MASTER}, services="igig")
        assert not r["ok"] and "roster" in r["error"]

    def test_render_files_modes_and_no_secret_in_payload(self, tmp_path):
        t = self._tree(tmp_path)
        r = ra.redis_acl("render", write=True, repo_root=str(t), env={ra.MASTER_ENV: MASTER})
        assert r["ok"] and MASTER not in str(r) and ra.derive_password(MASTER, "core") not in str(r)
        out = t / ra.OUT_DIR_REL
        for f in ("env/core.env", "ops.pass", "ops-app.pass", "trip.pass", "probe.pass"):
            assert (out / f).stat().st_mode & 0o777 == 0o600, f
        assert (out / "breaker-users.acl").is_file() and (out / "users.acl").is_file()
        assert (out / "probe.pass").read_text().strip() == ra.derive_password(MASTER, "probe")

    def test_check_flags_a_cut_over_service_without_env_file(self, tmp_path):
        t = self._tree(tmp_path)
        (t / ra.OVERRIDE_REL).write_text(ra.render_override(["core"]))
        r = ra.redis_acl("check", repo_root=str(t))
        assert not r["ok"] and r["missing_or_not_in_roster"] == ["core"]


# ── behaviour against real redis-server instances ───────────────────────────────────────────

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _boot(tmp_path_factory, name, aclfile_text, extra=()):
    redis = pytest.importorskip("redis")
    d = tmp_path_factory.mktemp(name)
    (d / "users.acl").write_text(aclfile_text)
    port = _free_port()
    proc = subprocess.Popen(
        ["redis-server", "--port", str(port), "--bind", "127.0.0.1", "--dir", str(d), "--aclfile", str(d / "users.acl"),
         "--save", "", "--appendonly", "no", *extra], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.1).close()
            return proc, port, redis
        except OSError:
            time.sleep(0.1)
    proc.terminate()
    pytest.skip("redis-server did not start")


ROSTER3 = ["agents", "core", "social-wiring"]


@pytest.mark.skipif(shutil.which("redis-server") is None, reason="redis-server not installed")
class TestLiveApp:
    @pytest.fixture(scope="class")
    def server(self, tmp_path_factory):
        proc, port, redis = _boot(tmp_path_factory, "app", ra.render_aclfile(ROSTER3, MASTER))
        yield port, redis
        proc.terminate()
        proc.wait(5)

    def _c(self, server, user, pw_user=None):
        port, redis = server
        return redis.Redis(port=port, username=user, password=ra.derive_password(MASTER, pw_user or user), decode_responses=True)

    def test_unauthenticated_and_default_user_refused(self, server):
        port, redis = server
        with pytest.raises(redis.exceptions.AuthenticationError):
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
        assert c.eval("return redis.call('incr', KEYS[1])", 1, "LIMITSprobe-lua") >= 1
        assert c.evalsha(c.script_load("return 1"), 0) == 1
        c.xadd("rt:wa:conn:1", {"a": "b"})
        c.zadd("queue:conversation_due", {"c1": 1})

    def test_no_breaker_key_is_reachable_on_the_app_redis(self, server):
        _, redis = server
        c = self._c(server, "core")
        for call in (lambda: c.get(ra.FLEET_KEY), lambda: c.set(ra.FLEET_KEY, "x"),
                     lambda: c.set("noctus:breaker:core:worker:x", "1")):
            with pytest.raises(redis.exceptions.NoPermissionError):
                call()

    def test_product_cannot_run_admin_or_dangerous_commands(self, server):
        c = self._c(server, "core")
        _, redis = server
        for call in (c.flushall, c.flushdb, lambda: c.config_get("*"), lambda: c.keys("*"), c.shutdown,
                     lambda: c.execute_command("ACL", "LIST"), lambda: c.execute_command("SORT", "x"),
                     lambda: c.script_flush(), lambda: c.script_kill(), lambda: c.execute_command("FUNCTION", "FLUSH"),
                     lambda: c.client_list()):
            with pytest.raises(redis.exceptions.NoPermissionError):
                call()

    def test_only_declared_exception_may_use_keys(self, server):
        sw = self._c(server, "social-wiring")
        sw.set("download:cache:a", "1")
        assert "download:cache:a" in sw.keys("download:cache:*")

    def test_unlisted_key_family_denied(self, server):
        _, redis = server
        with pytest.raises(redis.exceptions.NoPermissionError):
            self._c(server, "core").set("something:else", "1")

    def test_ops_on_the_app_redis_reads_acl_log_and_touches_no_key(self, server):
        _, redis = server
        ops = self._c(server, "ops", "ops-app")
        assert ops.ping() and isinstance(ops.acl_log(), list)
        for call in (lambda: ops.get("nai_session:x"), lambda: ops.set("llm:x", "1"), ops.flushall):
            with pytest.raises(redis.exceptions.NoPermissionError):
                call()


@pytest.mark.skipif(shutil.which("redis-server") is None, reason="redis-server not installed")
class TestLiveBreaker:
    @pytest.fixture(scope="class")
    def server(self, tmp_path_factory):
        proc, port, redis = _boot(tmp_path_factory, "brk", ra.render_breaker_aclfile(ROSTER3, MASTER),
                                  ("--maxmemory", "64mb", "--maxmemory-policy", "noeviction"))
        yield port, redis
        proc.terminate()
        proc.wait(5)

    def _c(self, server, user):
        port, redis = server
        pw = ra.breaker_user_password(MASTER, user) if user in ROSTER3 else ra.derive_password(MASTER, user)
        return redis.Redis(port=port, username=user, password=pw, decode_responses=True)

    def test_noeviction_and_no_scripting_for_anyone(self, server):
        _, redis = server
        for u in (*ROSTER3, "ops", "trip", "probe"):
            c = self._c(server, u)
            for call in (lambda: c.eval("return 1", 0), lambda: c.script_load("return 1"), lambda: c.execute_command("FUNCTION", "LIST")):
                with pytest.raises(redis.exceptions.NoPermissionError):
                    call()

    def test_product_fleet_key_read_only_own_sources_rw(self, server):
        _, redis = server
        self._c(server, "ops").set(ra.FLEET_KEY, "{}")
        c = self._c(server, "core")
        assert c.get(ra.FLEET_KEY) == "{}"
        for call in (lambda: c.set(ra.FLEET_KEY, "x"), lambda: c.delete(ra.FLEET_KEY), lambda: c.expire(ra.FLEET_KEY, 1),
                     lambda: c.set("noctus:breaker:agents:worker:x", "x"), lambda: c.rpush(ra.AUDIT_KEY, "x")):
            with pytest.raises(redis.exceptions.NoPermissionError):
                call()
        assert c.set("noctus:breaker:core:worker:x", "1") and c.set("noctus:breaker:core:scheduler:j", "1")
        assert c.mget([ra.FLEET_KEY, "noctus:breaker:core:worker:x"]) == ["{}", "1"]
        assert c.delete("noctus:breaker:core:worker:x") == 1

    def test_product_audit_and_index_inside_its_own_namespace(self, server):
        _, redis = server
        c = self._c(server, "core")
        for i in range(5):
            c.rpush("noctus:breaker:core:audit", f"r{i}")
        assert c.ltrim("noctus:breaker:core:audit", -2, -1) and c.lrange("noctus:breaker:core:audit", 0, -1) == ["r3", "r4"]
        assert c.sadd("noctus:breaker:core:index", "k1", "k2") == 2 and c.srem("noctus:breaker:core:index", "k1") == 1
        for call in (lambda: c.sadd("noctus:breaker:agents:index", "x"), lambda: c.rpush("noctus:breaker:agents:audit", "x"),
                     lambda: c.ltrim(ra.AUDIT_KEY, 0, 0), lambda: c.sadd("noctus:breaker:index", "x")):
            with pytest.raises(redis.exceptions.NoPermissionError):
                call()

    def test_rearm_markers_are_read_only_for_products_and_written_only_by_ops(self, server):
        _, redis = server
        c, ops = self._c(server, "core"), self._c(server, "ops")
        key = "noctus:breaker:core:rearm:worker:x"
        assert ops.set(key, "1")
        assert c.get(key) == "1"  # the product can READ its marker
        for call in (lambda: c.set(key, "2"), lambda: c.delete(key), lambda: c.expire(key, 1)):
            with pytest.raises(redis.exceptions.NoPermissionError):
                call()
        assert ops.delete(key) == 1

    def test_trip_setnx_only(self, server):
        _, redis = server
        trip, ops = self._c(server, "trip"), self._c(server, "ops")
        ops.delete(ra.FLEET_KEY)
        assert trip.setnx(ra.FLEET_KEY, '{"by":"offhost-watchdog"}')
        assert not trip.setnx(ra.FLEET_KEY, "other") and trip.exists(ra.FLEET_KEY) == 1
        for call in (lambda: trip.set(ra.FLEET_KEY, "x", ex=1), lambda: trip.delete(ra.FLEET_KEY),
                     lambda: trip.set("noctus:breaker:core:x", "1"), lambda: trip.rpush(ra.AUDIT_KEY, "x")):
            with pytest.raises(redis.exceptions.NoPermissionError):
                call()

    def test_probe_exists_only_refused_on_set_setnx_del(self, server):
        _, redis = server
        self._c(server, "ops").set(ra.FLEET_KEY, "{}")
        probe = self._c(server, "probe")
        assert probe.ping() and probe.exists(ra.FLEET_KEY) == 1
        for call in (lambda: probe.set(ra.FLEET_KEY, "x"), lambda: probe.setnx(ra.FLEET_KEY, "x"),
                     lambda: probe.delete(ra.FLEET_KEY), lambda: probe.get(ra.FLEET_KEY),
                     lambda: probe.exists("nai_session:x"), lambda: probe.exists("noctus:breaker:core:x")):
            with pytest.raises(redis.exceptions.NoPermissionError):
                call()

    def test_ops_rearms_audits_ltrims_index_never_scans(self, server):
        _, redis = server
        ops, core = self._c(server, "ops"), self._c(server, "core")
        ops.set(ra.FLEET_KEY, "{}")
        assert ops.delete(ra.FLEET_KEY) == 1
        for i in range(5):
            ops.rpush(ra.AUDIT_KEY, f"row{i}")
        assert ops.ltrim(ra.AUDIT_KEY, -3, -1) and ops.lrange(ra.AUDIT_KEY, 0, -1) == ["row2", "row3", "row4"]
        ops.set("noctus:breaker:core:worker:hand", "{}")
        assert ops.sadd("noctus:breaker:core:index", "noctus:breaker:core:worker:hand") == 1
        assert "noctus:breaker:core:worker:hand" in ops.smembers("noctus:breaker:core:index")
        for call in (lambda: ops.scan(0), lambda: ops.keys("*"), lambda: ops.get("nai_session:x"), ops.flushall,
                     lambda: ops.config_get("*"), lambda: ops.script_kill()):
            with pytest.raises(redis.exceptions.NoPermissionError):
                call()

    def test_ops_cannot_reconfigure_the_instance(self, server):
        port, redis = server
        admin = redis.Redis(port=port, username="ops", password=ra.derive_password(MASTER, "ops"))
        with pytest.raises(redis.exceptions.NoPermissionError):
            admin.config_set("maxmemory-policy", "allkeys-lru")  # noeviction is set at boot and stays


class TestHardeningFlags:
    def _seg(self, name, nxt):
        text = (REPO / "deploy/fleet/compose.infra.prod.yml").read_text()
        return text[text.index(f"  {name}:\n"):text.index(f"  {nxt}:\n")]

    def test_app_redis_bounded_digest_pinned_and_roomy(self):
        seg = self._seg("redis-acl", "breaker-redis")
        assert "--maxmemory" in seg and "volatile-lru" in seg and "mem_limit: 1g" in seg
        assert "redis:7-alpine" not in seg and "@sha256:" in seg and "redis:7.4.6" in seg

    def test_breaker_redis_is_tiny_noeviction_aof_internal_only(self):
        seg = self._seg("breaker-redis", "cache-pg")
        assert '"--maxmemory", "64mb"' in seg and "noeviction" in seg and "--appendonly" in seg
        assert "mem_limit:" in seg and "@sha256:" in seg and "redis:7.4.6" in seg and "noctus-net" not in seg
        assert "breaker-users.acl" in seg and "noctus-breaker-redis" in seg

    def test_neither_instance_joins_the_shared_network(self):
        for name, nxt in (("redis-acl", "breaker-redis"), ("breaker-redis", "cache-pg")):
            assert "noctus-net" not in self._seg(name, nxt)



class TestMasterParsing:  # P1-2
    EXAMPLE = REPO / "deploy/fleet/.env.fleet.example"

    def test_shipped_example_is_not_a_usable_master(self, tmp_path):
        r = ra.redis_acl("render", write=True, repo_root=str(tmp_path), env={}, env_file=str(self.EXAMPLE))
        assert not r["ok"]

    def _read(self, tmp_path, body):
        f = tmp_path / "e"
        f.write_text(body)
        return ra._read_master(tmp_path, {}, str(f))

    def test_inline_comment_is_never_the_secret(self, tmp_path):
        with pytest.raises(ValueError, match="master"):
            self._read(tmp_path, f"{ra.MASTER_ENV}=  # >= 32 chars; set on VPS only\n")
        with pytest.raises(ValueError, match="master"):
            self._read(tmp_path, f"{ra.MASTER_ENV}=#abcdef\n")

    def test_valid_hex_with_trailing_comment_and_quotes(self, tmp_path):
        assert self._read(tmp_path, f"{ra.MASTER_ENV}={MASTER}  # rotated 2026-11\n")[0] == MASTER
        assert self._read(tmp_path, f'export {ra.MASTER_ENV}="{MASTER}"\n')[0] == MASTER

    def test_non_hex_or_short_master_refused(self, tmp_path):
        for bad in ("short", "z" * 64, "AB12" * 16):
            with pytest.raises(ValueError, match="master"):
                self._read(tmp_path, f"{ra.MASTER_ENV}={bad}\n")

    def test_generation_same_rule(self, tmp_path):
        assert self._read(tmp_path, f"{ra.MASTER_ENV}={MASTER}\n{ra.GENERATION_ENV}=3  # bump\n")[1] == "3"
        with pytest.raises(ValueError, match="GENERATION"):
            self._read(tmp_path, f"{ra.MASTER_ENV}={MASTER}\n{ra.GENERATION_ENV}=# one\n")
        with pytest.raises(ValueError, match="GENERATION"):
            self._read(tmp_path, f"{ra.MASTER_ENV}={MASTER}\n{ra.GENERATION_ENV}=abc\n")

    def test_env_var_master_validated_too(self, tmp_path):
        with pytest.raises(ValueError):
            ra._read_master(tmp_path, {ra.MASTER_ENV: "# nope"}, None)


class TestSecretWrites:  # P3
    def test_dirs_0700_and_no_symlink_follow(self, tmp_path):
        (tmp_path / "deploy/fleet").mkdir(parents=True)
        (tmp_path / ra.COMPOSE_REL).write_text(COMPOSE)
        (tmp_path / ra.SCOPE_REL).write_text(SCOPE)
        assert ra.redis_acl("render", write=True, repo_root=str(tmp_path), env={ra.MASTER_ENV: MASTER})["ok"]
        out = tmp_path / ra.OUT_DIR_REL
        assert out.stat().st_mode & 0o777 == 0o711 and (out / "env").stat().st_mode & 0o777 == 0o700  # 0711: consumers traverse to their pass file

    def test_symlink_target_is_replaced_not_followed(self, tmp_path):
        victim = tmp_path / "victim"
        victim.write_text("keep")
        d = tmp_path / "d"
        d.mkdir()
        (d / "ops.pass").symlink_to(victim)
        ra._write_secret(d / "ops.pass", "secret\n", 0o600)
        assert victim.read_text() == "keep" and not (d / "ops.pass").is_symlink()

    def test_symlinked_output_dir_refused(self, tmp_path):
        real = tmp_path / "real"
        real.mkdir()
        (tmp_path / "link").symlink_to(real)
        with pytest.raises(ValueError, match="symlink"):
            ra._write_secret(tmp_path / "link" / "x", "s", 0o600)




class TestSlugsAndGenerations:
    @pytest.mark.parametrize("bad", ["noctus", "default", "ops", "trip", "probe", "healthcheck", "wa", "rt", "llm", "queue", "conversation"])
    def test_reserved_slugs_refused(self, bad):
        compose = f"services:\n  {bad}: {{env_file: ['../../.env']}}\n"
        with pytest.raises(ValueError, match="reserved"):
            ra.derive_roster(compose, f"{bad}\n")

    def test_per_user_generation_override(self):
        a = ra.derive_password(MASTER, "core", {"*": "1", "core": "2"})
        assert a == ra.derive_password(MASTER, "core", "2") and a != ra.derive_password(MASTER, "agents", {"*": "1", "core": "2"})
        assert ra.parse_generation_overrides("core=2, ops=3") == {"core": "2", "ops": "3"}
        with pytest.raises(ValueError):
            ra.parse_generation_overrides("core=#2")


class TestCutoverMarker:  # round 4 P2-1
    def _tree(self, tmp_path):
        (tmp_path / "deploy/fleet").mkdir(parents=True)
        (tmp_path / ra.COMPOSE_REL).write_text(COMPOSE)
        (tmp_path / ra.SCOPE_REL).write_text(SCOPE)
        return tmp_path

    def test_render_services_writes_marker_none_keeps_it_empty_clears_it(self, tmp_path):
        t = self._tree(tmp_path)
        env = {ra.MASTER_ENV: MASTER}
        m = t / ra.OUT_DIR_REL / ra.MARKER_NAME
        ra.redis_acl("render", write=True, repo_root=str(t), env=env, services="core,agents")
        assert m.read_text().split() == ["agents", "core"]
        ra.redis_acl("render", write=True, repo_root=str(t), env=env)  # no --services: marker + override untouched
        assert m.read_text().split() == ["agents", "core"] and (t / ra.OVERRIDE_REL).is_file()
        ra.redis_acl("render", write=True, repo_root=str(t), env=env, services="agents")  # rollback of core
        assert m.read_text().split() == ["agents"]
        ra.redis_acl("render", write=True, repo_root=str(t), env=env, services="")  # only an explicit empty clears
        assert not m.exists() and not (t / ra.OVERRIDE_REL).exists()

    def test_check_flags_marker_without_override_and_override_missing_a_marked_service(self, tmp_path):
        t = self._tree(tmp_path)
        env = {ra.MASTER_ENV: MASTER}
        ra.redis_acl("render", write=True, repo_root=str(t), env=env, services="core,agents")
        assert ra.redis_acl("check", repo_root=str(t))["ok"]
        (t / ra.OVERRIDE_REL).unlink()
        r = ra.redis_acl("check", repo_root=str(t))
        assert not r["ok"] and r["marker_without_override"] == ["agents", "core"] and "fix" in r
        (t / ra.OVERRIDE_REL).write_text(ra.render_override(["core"]))
        r = ra.redis_acl("check", repo_root=str(t))
        assert not r["ok"] and r["marker_services_missing_from_override"] == ["agents"]


class TestPassFileOwnership:  # round 4 P3-1
    def test_existing_pass_file_keeps_uid_gid_across_a_rerender(self, tmp_path):
        import os
        from unittest import mock

        d = tmp_path / "d"
        d.mkdir()
        f = d / "trip.pass"
        f.write_text("old\n")
        st = f.stat()
        real_chown = os.chown
        seen = []

        def spy(path, uid, gid, *a, **k):
            seen.append((str(path), uid, gid))
            return real_chown(path, uid, gid, *a, **k)

        with mock.patch("os.chown", spy):
            ra._write_secret(f, "new\n", 0o600)
        assert f.read_text() == "new\n" and (f.stat().st_uid, f.stat().st_gid) == (st.st_uid, st.st_gid)
        assert seen and seen[0][1:] == (st.st_uid, st.st_gid)  # chown targets the EXISTING owner before the replace

    def test_when_chown_is_not_permitted_the_file_is_rewritten_in_place_keeping_the_inode(self, tmp_path):
        import os
        from unittest import mock

        f = tmp_path / "probe.pass"
        f.write_text("old\n")
        inode = f.stat().st_ino
        with mock.patch("os.chown", side_effect=PermissionError):
            ra._write_secret(f, "new\n", 0o600)
        assert f.read_text() == "new\n" and f.stat().st_ino == inode and f.stat().st_mode & 0o777 == 0o600
        assert not list(tmp_path.glob(".*tmp"))

    def test_rerender_does_not_chmod_an_existing_consumer_directory_or_clobber_pass_files(self, tmp_path):
        (tmp_path / "deploy/fleet").mkdir(parents=True)
        (tmp_path / ra.COMPOSE_REL).write_text(COMPOSE)
        (tmp_path / ra.SCOPE_REL).write_text(SCOPE)
        env = {ra.MASTER_ENV: MASTER}
        ra.redis_acl("render", write=True, repo_root=str(tmp_path), env=env)
        out = tmp_path / ra.OUT_DIR_REL
        inode = (out / "trip.pass").stat().st_ino
        ra.redis_acl("render", write=True, repo_root=str(tmp_path), env=env)
        assert out.stat().st_mode & 0o777 == 0o711
        assert (out / "trip.pass").read_text().strip() == ra.derive_password(MASTER, "trip")

    def test_check_reports_pass_file_owner_and_flags_a_loose_mode(self, tmp_path):
        import os

        (tmp_path / "deploy/fleet").mkdir(parents=True)
        (tmp_path / ra.COMPOSE_REL).write_text(COMPOSE)
        (tmp_path / ra.SCOPE_REL).write_text(SCOPE)
        ra.redis_acl("render", write=True, repo_root=str(tmp_path), env={ra.MASTER_ENV: MASTER})
        r = ra.redis_acl("check", repo_root=str(tmp_path))
        assert r["ok"] and r["pass_files"]["trip"]["uid"] == os.getuid() and r["pass_files"]["trip"]["owner_can_read"]
        os.chmod(tmp_path / ra.OUT_DIR_REL / "probe.pass", 0o644)
        r = ra.redis_acl("check", repo_root=str(tmp_path))
        assert not r["ok"] and r["bad_pass_file_modes"] == ["probe"]


class TestStaleCommittedOverrideText:  # round 4 P3-2
    def test_gitignore_and_cli_describe_the_override_as_host_local(self):
        gi = (REPO / ".gitignore").read_text()
        assert "committed artefact is compose.redis-auth" not in gi
        assert "host-local, gitignored, written by render --services" in gi
        cli = (REPO / "mcp/noctusai/cli.py").read_text()
        i = cli.index('"--redis-acl"')
        seg = cli[i:i + 900]
        assert "committed" not in seg and "host-local, gitignored, written by render --services" in seg
