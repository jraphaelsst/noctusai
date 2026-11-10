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
    out = _call(ops, "status")
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
        return (0, "", "")

    ops = VpsRedisOps("h", runner=runner)
    ops.set("k;rm", '{"a": "b c"}')
    assert sent[0] == "docker exec noctus-redis redis-cli set 'k;rm' '{\"a\": \"b c\"}'"
    bad = VpsRedisOps("h", runner=lambda h, c: (255, "", "ssh: connect failed"))
    try:
        bad.scan()
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
