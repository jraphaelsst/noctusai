"""noctus.dev.supabase_breaker — status / rearm / trip over the prod Redis keys, via the Redis seam (a Fake)."""
from __future__ import annotations

import json
import sys
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import supabase_breaker as mod  # noqa: E402
from tools.noctus.dev.supabase_breaker import FakeRedisOps, VpsRedisOps  # noqa: E402

KEY = "noctus:breaker:social-wiring:worker:transcricao"


def _call(ops, action, **kw):
    ex = partial(mod._default_executor, ops=ops)
    return mod.supabase_breaker(action, executor=lambda **a: ex(**a), **kw)


def test_status_lists_held_keys_and_fleet():
    ops = FakeRedisOps({KEY: json.dumps({"reason": "runaway", "by": "auto"}),
                        mod.FLEET_KEY: json.dumps({"reason": "402"})})
    out = _call(ops, "status", product="social-wiring")
    assert out["ok"] and out["count"] == 2 and out["fleet_held"] is True and out["held"][KEY]["by"] == "auto"


def test_rearm_requires_reason_and_is_dry_run_by_default():
    ops = FakeRedisOps({KEY: "{}"})
    assert _call(ops, "rearm", source="worker:transcricao", product="social-wiring")["ok"] is False
    plan = _call(ops, "rearm", source="worker:transcricao", product="social-wiring", reason="fixed")
    assert plan["status"] == "planned" and KEY in ops.data
    done = _call(ops, "rearm", source="worker:transcricao", product="social-wiring", reason="fixed", by="ana", confirm=True)
    assert done["rearmed"] and KEY not in ops.data
    audit = json.loads(ops.audit[0])
    assert audit["by"] == "ana" and audit["reason"] == "fixed" and audit["op"] == "rearm"


def test_trip_fleet_and_source_validation():
    ops = FakeRedisOps()
    out = _call(ops, "trip", source="fleet", reason="402 storm", by="ana", confirm=True)
    assert out["tripped"] and json.loads(ops.data[mod.FLEET_KEY])["by"] == "manual:ana"
    assert _call(ops, "trip", source="http", reason="x")["ok"] is False
    assert _call(ops, "trip", source="worker:a", reason="x")["ok"] is False  # product missing
    assert _call(ops, "trip", source="rm -rf /", product="p", reason="x")["ok"] is False


def test_vps_redis_ops_quotes_every_argument_and_surfaces_failures():
    sent: list[str] = []

    def runner(host, cmd):
        sent.append(cmd)
        return (1, "", "") if cmd.startswith("test -r") else (0, "", "")  # no ops.pass -> plain redis

    ops = VpsRedisOps("h", runner=runner)
    ops.set("k;rm", '{"a": "b c"}')
    assert sent[-1] == "docker exec noctus-redis redis-cli set 'k;rm' '{\"a\": \"b c\"}'"
    bad = VpsRedisOps("h", runner=lambda h, c: (255, "", "ssh: connect failed"))
    try:
        bad.smembers("k")
    except mod.RedisOpsError as exc:
        assert "connect failed" in str(exc)
    else:
        raise AssertionError("a failed redis-cli must raise, never read as an empty fleet")


def test_registered_under_the_dev_namespace():
    seen = {}

    class _Server:
        def tool(self, *, name, description):
            seen["name"], seen["description"] = name, description
            return lambda fn: fn

    mod.register(_Server())
    assert seen["name"] == "noctus.dev.supabase_breaker" and "rearm" in seen["description"]


def test_F9_source_regex_is_in_parity_with_the_seed_primitive():
    from noctusai_lib.primitives.supabase_breaker import BREAKER_SOURCE_RE

    assert mod._SOURCE_RE.pattern == BREAKER_SOURCE_RE.pattern


def test_F10_audit_list_is_capped():
    ops = FakeRedisOps()
    for i in range(1300):
        ops.append_audit(mod.AUDIT_KEY, str(i), mod.AUDIT_CAP)
    assert len(ops.audit) == 1000
    sent: list[str] = []
    VpsRedisOps("h", runner=lambda h, c: (sent.append(c), (0, "", ""))[1]).append_audit(mod.AUDIT_KEY, "{}", 1000)
    assert any(" ltrim " in c and "-1000" in c for c in sent), "the real path must LTRIM too"


def test_F11a_ssh_host_is_validated_and_options_are_terminated():
    import pytest as _pytest

    from tools.noctus.dev import _vps_ssh as ssh

    for bad in ("-oProxyCommand=touch /tmp/x", "-F/etc/passwd", "a b", "host;rm", "", "a" + "\n" + "b"):
        with _pytest.raises(ValueError):
            ssh.run_remote(bad, "true")
    seen: list[list[str]] = []

    class _P:
        returncode, stdout, stderr = 0, "", ""

    def fake_run(args, **kw):
        seen.append(args)
        return _P()

    import subprocess

    orig = subprocess.run
    subprocess.run = fake_run  # external boundary (the OS), not our own module
    try:
        ssh._real_ssh("noctus-vps", "true", 5, 5)
    finally:
        subprocess.run = orig
    args = seen[0]
    assert args[-3:] == ["--", "noctus-vps", "true"]


# --- Redis ACL transition (feat/redis-acl-lockdown): branch selection on the presence of ops.pass ------------------

OPS_PASS = "/opt/noctus/noctusai/deploy/fleet/redis-auth/ops.pass"


def _runner(*, has_pass: bool, out: str = "", sent=None, rc_probe: int | None = None):
    sent = sent if sent is not None else []

    def run(host, cmd):
        sent.append(cmd)
        if cmd.startswith("test -r"):
            return (rc_probe if rc_probe is not None else (0 if has_pass else 1), "", "")
        return (0, out, "")

    return run, sent


def test_acl_branch_authenticates_as_ops_with_the_secret_read_on_the_vps_never_on_argv():
    run, sent = _runner(has_pass=True)
    VpsRedisOps("h", runner=run).set("noctus:breaker:p:worker:a", "{}")
    cmd = sent[-1]
    assert cmd.startswith(f'REDISCLI_AUTH="$(cat {OPS_PASS})" docker exec -e REDISCLI_AUTH noctus-redis-acl '
                          "redis-cli --no-auth-warning --user ops set ")
    assert "-a " not in cmd and "--pass" not in cmd.replace("--no-auth-warning", ""), "the secret is never an argument"
    assert sent[0] == f"test -r {OPS_PASS}"


def test_no_ops_pass_falls_back_to_the_unauthenticated_redis_with_no_auth_flags():
    run, sent = _runner(has_pass=False)
    VpsRedisOps("h", runner=run).delete("k")
    assert sent[-1] == "docker exec noctus-redis redis-cli del k"
    assert "--user" not in sent[-1] and "REDISCLI_AUTH" not in sent[-1]


def test_probe_is_cached_per_instance_and_an_unreachable_host_fails_loud_not_as_no_auth():
    run, sent = _runner(has_pass=True)
    ops = VpsRedisOps("h", runner=run)
    ops.set("a", "1")
    ops.delete("a")
    assert sum(1 for c in sent if c.startswith("test -r")) == 1
    run2, _ = _runner(has_pass=False, rc_probe=255)
    try:
        VpsRedisOps("h", runner=run2).smembers("k")
    except mod.RedisOpsError as exc:
        assert "ops.pass" in str(exc)
    else:
        raise AssertionError("an ssh failure while probing must not silently select the unauthenticated Redis")


def test_auth_and_permission_errors_fail_loud():
    for marker in ("NOAUTH Authentication required.", "WRONGPASS invalid username-password pair", "NOPERM this user has no permissions to run the 'ltrim' command"):
        run, _ = _runner(has_pass=True, out=marker + "\n")
        try:
            VpsRedisOps("h", runner=run).get("k")
        except mod.RedisOpsError as exc:
            assert marker.split()[0] in str(exc)
        else:
            raise AssertionError(f"{marker} must raise")


def test_audit_cap_denied_by_the_ops_acl_is_a_loud_warning_not_a_lost_rearm():
    calls = []

    def run(host, cmd):
        calls.append(cmd)
        if cmd.startswith("test -r"):
            return (0, "", "")
        if " ltrim " in cmd:
            return (0, "NOPERM this user has no permissions to run the 'ltrim' command\n", "")
        return (0, "", "")

    ops = VpsRedisOps("h", runner=run)
    ops.append_audit(mod.AUDIT_KEY, "{}", 1000)
    assert ops.warnings and "ltrim" in ops.warnings[0].lower()
