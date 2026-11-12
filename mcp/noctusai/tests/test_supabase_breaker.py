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
    assert audit["claimed_by"] == "ana" and audit["reason"] == "fixed" and audit["op"] == "rearm"


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
        return (0, "", "") if cmd.startswith("if docker ps") else (0, "", "")  # nothing up, no ops.pass -> plain redis

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


def _runner(*, has_pass: bool, out: str = "", sent=None, rc_probe: int | None = None, acl_up: bool | None = None):
    sent = sent if sent is not None else []

    def run(host, cmd):
        sent.append(cmd)
        if cmd.startswith("if docker ps"):
            up = has_pass if acl_up is None else acl_up
            return (rc_probe if rc_probe is not None else 0, ("ACL_UP\n" if up else "") + ("PASS_OK\n" if has_pass else ""), "")
        return (0, out, "")

    return run, sent


def test_acl_branch_authenticates_as_ops_with_the_secret_read_on_the_vps_never_on_argv():
    run, sent = _runner(has_pass=True)
    VpsRedisOps("h", runner=run).set("noctus:breaker:p:worker:a", "{}")
    cmd = sent[-1]
    assert cmd.startswith(f'REDISCLI_AUTH="$(cat {OPS_PASS})" docker exec -e REDISCLI_AUTH noctus-breaker-redis '
                          "redis-cli --no-auth-warning --user ops set ")
    assert "-a " not in cmd and "--pass" not in cmd.replace("--no-auth-warning", ""), "the secret is never an argument"
    assert sent[0].startswith("if docker ps") and OPS_PASS in sent[0]


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
    assert sum(1 for c in sent if c.startswith("if docker ps")) == 1
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
        if cmd.startswith("if docker ps"):
            return (0, "ACL_UP\nPASS_OK\n", "")
        if " ltrim " in cmd:
            return (0, "NOPERM this user has no permissions to run the 'ltrim' command\n", "")
        return (0, "", "")

    ops = VpsRedisOps("h", runner=run)
    ops.append_audit(mod.AUDIT_KEY, "{}", 1000)
    assert ops.warnings and "ltrim" in ops.warnings[0].lower()


# --- round 4: P3-2 probe the running containers, P3-3 single MGET + filtered/sanitised index, P3-4 identity, P3-5 ----


def test_P3_2_a_running_acl_redis_without_a_readable_ops_pass_never_falls_back_to_the_plain_one():
    run, sent = _runner(has_pass=False, acl_up=True)
    try:
        VpsRedisOps("h", runner=run).delete("k")
    except mod.RedisOpsError as exc:
        assert "refusing to fall back" in str(exc)
    else:
        raise AssertionError("a running noctus-breaker-redis must force the ACL path")
    assert not any("redis-cli" in c for c in sent), "no redis command may have been sent unauthenticated"


def test_P3_3_status_uses_one_mget_and_filters_and_sanitises_what_a_product_wrote():
    slug = "social-wiring"
    good = f"noctus:breaker:{slug}:worker:transcricao"
    members = [good, f"noctus:breaker:other:worker:x", f"noctus:breaker:{slug}:worker:a b", "nope",
               f"noctus:breaker:{slug}:http"] + [f"noctus:breaker:{slug}:worker:t{i}" for i in range(500)]
    ops = FakeRedisOps({good: json.dumps({"reason": "bad\x1b[31mred\nline" + "x" * 900, "by": "auto"})})
    ops.smembers = lambda key: members  # a hostile / buggy index
    calls = []
    orig = ops.mget
    ops.mget = lambda keys: (calls.append(keys), orig(keys))[1]
    out = mod._default_executor(action="status", source="", product=slug, reason="", by="", confirm=False,
                                ssh_host="h", ops=ops)
    assert len(calls) == 1, "ONE mget for every key"
    assert len(calls[0]) <= 1 + mod.MAX_INDEX_MEMBERS and all(k == mod.FLEET_KEY or k.startswith(f"noctus:breaker:{slug}:")
                                                              for k in calls[0])
    reason = out["held"][good]["reason"]
    assert "\x1b" not in reason and "\n" not in reason and len(reason) <= mod.MAX_VALUE_CHARS


def test_P3_4_audit_rows_carry_unspoofable_identity_and_a_claimed_by():
    ops = FakeRedisOps({"noctus:breaker:p:worker:a": json.dumps({"tripped_at": "T1"})})
    out = mod._default_executor(action="rearm", source="worker:a", product="p", reason="fixed", by="ana", confirm=True,
                                ssh_host="h", ops=ops)
    row = json.loads(ops.audit[-1])
    assert out["rearmed"] and row["claimed_by"] == "ana" and "by" not in row
    assert {"session", "os_user", "host"} <= set(row)
    marker = json.loads(ops.data["noctus:breaker:p:rearm:worker:a"])
    assert marker["tripped_at"] == "T1", "the marker lets the product release exactly this trip"


def test_P3_5_reason_with_control_characters_is_refused_in_the_tool():
    for bad in ("a\nb", "a\x1b[0m", "tab\t", "x" * 301, "   "):
        out = mod.supabase_breaker("trip", source="worker:a", product="p", reason=bad, confirm=False,
                                   executor=lambda **kw: {"x": 1})
        assert out["ok"] is False and out["status"] == "invalid", bad


def test_audit_action_reads_both_lists():
    ops = FakeRedisOps()
    ops.audit.append(json.dumps({"op": "rearm", "claimed_by": "ana"}))
    out = mod._default_executor(action="audit", source="", product="p", reason="", by="", confirm=False, ssh_host="h",
                                ops=ops)
    assert out["rows"][mod.AUDIT_KEY][0]["claimed_by"] == "ana"


def test_P1_3_the_steward_backstop_lives_inside_the_tool_function_not_only_the_mcp_wrapper():
    import inspect

    assert '_steward.tool_refusal("noctus.dev.supabase_breaker"' in inspect.getsource(mod.supabase_breaker)
    # status / audit / dry-runs are never refused (an empty store + no session identity = unattributed allow)
    for action, confirm in (("status", False), ("audit", False), ("rearm", False), ("trip", False)):
        out = mod.supabase_breaker(action, source="worker:a", product="p", reason="why", confirm=confirm,
                                   executor=lambda **kw: {"x": 1})
        assert out.get("status") != "refused_not_steward"


# --- round 5: marker TTL, auth detection by rc + stderr only -------------------------------------------------------


def test_marker_is_written_with_a_ttl_and_the_persisted_keys_tripped_at():
    ops = FakeRedisOps({"noctus:breaker:p:worker:a": json.dumps({"tripped_at": "T9"})})
    mod._default_executor(action="rearm", source="worker:a", product="p", reason="fixed", by="ana", confirm=True,
                          ssh_host="h", ops=ops)
    marker_key = "noctus:breaker:p:rearm:worker:a"
    assert json.loads(ops.data[marker_key])["tripped_at"] == "T9" and ops.ttls[marker_key] == mod.MARKER_TTL_S


def test_P3_4_vps_set_with_ttl_sends_EX():
    sent: list[str] = []
    ops = VpsRedisOps("h", runner=lambda h, c: (sent.append(c), (0, "ACL_UP\nPASS_OK\n" if c.startswith("if docker ps") else "OK\n", ""))[1])
    ops.set("k", "v", ttl=86400)
    assert sent[-1].endswith("set k v EX 86400")


def test_P3_4_a_product_written_value_that_says_NOAUTH_is_data_not_an_auth_failure():
    value = json.dumps({"reason": "NOAUTH WRONGPASS NOPERM", "by": "auto"})
    run, _ = _runner(has_pass=True, out=json.dumps([value]))
    got = VpsRedisOps("h", runner=run).mget(["k"])
    assert got == [value]


def test_P3_4_auth_errors_are_read_from_rc_and_stderr():
    def make(rc, out, err):
        def run(host, cmd):
            if cmd.startswith("if docker ps"):
                return (0, "ACL_UP\nPASS_OK\n", "")
            return (rc, out, err)
        return VpsRedisOps("h", runner=run)

    for rc, out, err, marker in ((1, "", "NOAUTH Authentication required.", "NOAUTH"),
                                 (0, "[]", "WRONGPASS invalid username-password pair", "WRONGPASS"),
                                 (1, "NOPERM no permissions", "", "NOPERM")):
        try:
            make(rc, out, err).mget(["k"])
        except mod.RedisOpsError as exc:
            assert marker in str(exc)
        else:
            raise AssertionError(marker)


def test_P2_2_status_lists_services_on_fallback_with_incomplete_credentials_and_unverified():
    ops = FakeRedisOps()
    ops.fallback, ops.partial, ops.unverified = ["core", "social-wiring"], ["agents"], ["monica"]
    out = mod._default_executor(action="status", source="", product="social-wiring", reason="", by="", confirm=False,
                                ssh_host="h", ops=ops)
    assert out["on_app_redis_fallback"] == ["social-wiring"]
    ops.fallback = []
    out = mod._default_executor(action="status", source="", product="agents", reason="", by="", confirm=False,
                                ssh_host="h", ops=ops)
    assert out["breaker_credentials_incomplete"] == ["agents"] and out["unverified_services"] == []
    out = mod._default_executor(action="status", source="", product="monica", reason="", by="", confirm=False,
                                ssh_host="h", ops=ops)
    assert out["unverified_services"] == ["monica"], "a missing container is UNVERIFIED, never assumed healthy"


def test_F6_vps_classifies_fallback_partial_credentials_and_unverified_in_one_ssh():
    sent: list[str] = []

    def run(host, cmd):
        sent.append(cmd)
        return (0, "FALLBACK:core\nPARTIAL:agents\nUNVERIFIED:monica\nbogus line\nFALLBACK:bad slug\n", "")

    out = VpsRedisOps("h", runner=run).fallback_services(["core", "agents", "monica", "bad slug;rm"])
    assert out == {"fallback": ["core"], "partial_credentials": ["agents"], "unverified": ["monica"]}
    assert len(sent) == 1 and "NOCTUS_BREAKER_REDIS_URL" in sent[0] and "NOCTUS_BREAKER_REDIS_USERNAME" in sent[0] \
        and "NOCTUS_BREAKER_REDIS_PASSWORD" in sent[0] and "bad slug" not in sent[0]
    bad = VpsRedisOps("h", runner=lambda h, c: (255, "", "ssh down"))
    assert bad.fallback_services(["core"]) is None and bad.warnings


def test_P3_4_vps_redis_ops_has_every_public_method_of_the_fake():
    import inspect

    fake = {n for n, m in inspect.getmembers(FakeRedisOps, predicate=inspect.isfunction) if not n.startswith("_")}
    real = {n for n, m in inspect.getmembers(VpsRedisOps, predicate=inspect.isfunction) if not n.startswith("_")}
    assert fake <= real, f"the Fake has methods the real VpsRedisOps lacks: {sorted(fake - real)}"
