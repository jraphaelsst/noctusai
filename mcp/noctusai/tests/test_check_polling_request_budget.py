"""`check_polling_request_budget` — every loop/poll declares what it costs per day (2026-11-10 Supabase egress incident).

R1 while+sleep/timed-wait, R2 periodic registrations (scheduler register/add_job, Worker poll kwargs),
R3 `select("*")` / limit>1000 in a tick-reachable function, R4 TS refetchInterval / setInterval.
Each rule: a violating AND a clean fixture, plus the declaration-without-a-number case and the live tree.

-> KB § PATTERNS/backend/polling-request-budget.md
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.polling_request_budget import (  # noqa: E402
    SCRIPT_REL,
    check_polling_request_budget,
)
from tools.noctus.dev.compliance import REPO_ROOT  # noqa: E402

PY = "products/demo/backend/app/services/loop.py"
SEED_PY = "seed/lib/backend/noctusai_lib/domain/x/w.py"
TS = "products/demo/frontend/src/Page.tsx"
GOOD = "poll-budget: every 30s; 1 calls/tick; worst 2880/day; idle=backoff"
GOOD_TS = "poll-budget: 5s; 1 calls/tick; worst 17280/day per open tab; hidden=paused"

_TS_OK = (
    shutil.which("node") is not None
    and REPO_ROOT.joinpath(*SCRIPT_REL).exists()
    and (REPO_ROOT.joinpath(*SCRIPT_REL).parent / "node_modules" / "ts-morph").exists()
)
needs_ts = pytest.mark.skipif(not _TS_OK, reason="node / ts-morph unavailable")


def _run(tmp: Path, files: dict[str, str], paths=None) -> list[dict]:
    for rel, text in files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return check_polling_request_budget(repo_root=tmp, paths=paths)


def _rules(issues):
    return sorted((i["rule"], i["line"]) for i in issues)


LOOP = "import asyncio\nasync def run():\n    while True:\n        await asyncio.sleep(1)\n"


class TestR1WhileSleep:
    def test_while_sleep_flagged(self, tmp_path):
        assert _rules(_run(tmp_path, {PY: LOOP})) == [("py_while_sleep", 3)]

    @pytest.mark.parametrize("body", [
        "        time.sleep(2)\n",
        "        await asyncio.wait_for(ev.wait(), timeout=5)\n",
        "        await asyncio.wait({t}, timeout=5)\n",
        "        ev.wait(3)\n",
    ])
    def test_every_timed_shape_flagged(self, tmp_path, body):
        src = f"import asyncio, time\nasync def run(ev, t):\n    while True:\n{body}"
        assert [r for r, _ in _rules(_run(tmp_path, {PY: src}))] == ["py_while_sleep"]

    def test_declared_above_is_clean(self, tmp_path):
        src = f"import asyncio\nasync def run():\n    # {GOOD}\n    while True:\n        await asyncio.sleep(1)\n"
        assert _run(tmp_path, {PY: src}) == []

    def test_declared_same_line_is_clean(self, tmp_path):
        src = f"import asyncio\nasync def run():\n    while True:  # {GOOD}\n        await asyncio.sleep(1)\n"
        assert _run(tmp_path, {PY: src}) == []

    def test_declaration_four_lines_up_is_too_far(self, tmp_path):
        src = f"import asyncio\n# {GOOD}\n\n\nasync def run():\n    while True:\n        await asyncio.sleep(1)\n"
        assert len(_run(tmp_path, {PY: src})) == 1

    @pytest.mark.parametrize("decl", [
        "# poll-budget:", "# poll-budget: every 30s; idle=backoff", "# poll-budget: worst lots/day",
    ])
    def test_declaration_without_a_number_is_a_finding(self, tmp_path, decl):
        src = f"import asyncio\nasync def run():\n    {decl}\n    while True:\n        await asyncio.sleep(1)\n"
        issues = _run(tmp_path, {PY: src})
        assert len(issues) == 1 and "/day" in issues[0]["issue"]

    @pytest.mark.parametrize("n", ["2880/day", "2,880 /day", "1.2k/day", "4M/day"])
    def test_number_forms_accepted(self, tmp_path, n):
        src = f"import asyncio\nasync def run():\n    # poll-budget: 30s; 1 calls/tick; worst {n}; idle=fixed\n    while True:\n        await asyncio.sleep(1)\n"
        assert _run(tmp_path, {PY: src}) == []

    def test_declaration_in_a_string_does_not_count(self, tmp_path):
        src = 'import asyncio\nX = "poll-budget: 1s; worst 9/day"\nasync def run():\n    while True:\n        await asyncio.sleep(1)\n'
        assert len(_run(tmp_path, {PY: src})) == 1

    def test_while_without_sleep_is_clean(self, tmp_path):
        assert _run(tmp_path, {PY: "def f(q):\n    while q:\n        q.pop()\n"}) == []

    def test_sleep_outside_a_loop_is_clean(self, tmp_path):
        assert _run(tmp_path, {PY: "import time\ndef f():\n    time.sleep(1)\n"}) == []

    def test_tests_and_archive_and_testing_excluded(self, tmp_path):
        files = {
            "products/demo/backend/app/tests/test_x.py": LOOP,
            "products/demo/backend/app/_archive/old.py": LOOP,
            "seed/lib/backend/noctusai_lib/testing/h.py": LOOP,
            "products/demo/backend/app/test_y.py": LOOP,
        }
        assert _run(tmp_path, files) == []

    def test_seed_lib_scanned(self, tmp_path):
        assert len(_run(tmp_path, {SEED_PY: LOOP})) == 1

    def test_paths_scopes_the_report(self, tmp_path):
        files = {PY: LOOP, "products/demo/backend/app/services/other.py": LOOP}
        issues = _run(tmp_path, files, paths=[PY])
        assert [i["file"] for i in issues] == [PY]


class TestR2PeriodicRegistration:
    @pytest.mark.parametrize("call", [
        'register("j", fn, minutes=1)',
        'seed_scheduler.register("j", fn, seconds=30)',
        'scheduler.add_job(fn, "interval", seconds=5)',
        'sched.add_job(fn, trigger="interval", minutes=2)',
        'scheduler.add_job(fn, seconds=5)',
        'Worker(repo, handlers={}, poll_interval_seconds=1.0)',
        'noctusai_lib.domain.jobs.Worker(repo, max_idle_interval_seconds=30)',
        'build(repo, poll_interval_seconds=2)',
    ])
    def test_flagged(self, tmp_path, call):
        src = f"def wire(register, scheduler, sched, repo, fn, Worker=None, build=None, seed_scheduler=None):\n    {call}\n"
        issues = _run(tmp_path, {PY: src})
        assert [i["rule"] for i in issues] == ["py_periodic_registration"], call

    def test_declared_is_clean(self, tmp_path):
        src = f'def wire(register, fn):\n    # {GOOD}\n    register("j", fn, minutes=1)\n'
        assert _run(tmp_path, {PY: src}) == []

    def test_cron_registration_not_flagged(self, tmp_path):
        src = 'def wire(register, fn):\n    register("j", fn, cron="0 3 * * *")\n'
        assert _run(tmp_path, {PY: src}) == []

    def test_definition_with_the_kwarg_is_not_a_call(self, tmp_path):
        src = "def build(repo, poll_interval_seconds: float = 1.0):\n    return repo\n"
        assert _run(tmp_path, {PY: src}) == []

    def test_unrelated_register_is_clean(self, tmp_path):
        assert _run(tmp_path, {PY: "def f(registry, h):\n    registry.register(h)\n"}) == []


class TestR3UnboundedReadInTick:
    def test_select_star_in_a_loop_function_flagged_even_declared(self, tmp_path):
        src = (
            "import asyncio\nasync def run(db):\n"
            f"    # {GOOD}\n    while True:\n"
            '        db.table("t").select("*").execute()\n        await asyncio.sleep(1)\n'
        )
        assert _rules(_run(tmp_path, {PY: src})) == [("py_unbounded_tick_read", 5)]

    @pytest.mark.parametrize("name", ["claim_gate", "my_gate", "tick", "do_tick_now", "run_once", "poll_queue", "pollers", "queue_stats"])
    def test_gate_named_functions(self, tmp_path, name):
        src = f'def {name}(db):\n    return db.table("t").select("*").execute()\n'
        assert [i["rule"] for i in _run(tmp_path, {PY: src})] == ["py_unbounded_tick_read"]

    def test_big_limit_flagged_and_constant_resolved(self, tmp_path):
        src = "CAP = 5000\ndef run_once(db):\n    db.table('t').select('id').limit(CAP).execute()\n    db.table('t').select('id').limit(2000).execute()\n"
        assert len(_run(tmp_path, {PY: src})) == 2

    def test_columns_and_small_limit_and_count_are_clean(self, tmp_path):
        src = (
            "def run_once(db):\n"
            "    db.table('t').select('id,status').limit(50).execute()\n"
            "    db.table('t').select('id', count='exact').limit(0).execute()\n"
            "    db.table('t').select('id').limit(1000).execute()\n"
        )
        assert _run(tmp_path, {PY: src}) == []

    def test_select_star_in_an_ordinary_function_is_clean(self, tmp_path):
        src = 'def get_user(db, i):\n    return db.table("t").select("*").eq("id", i).execute()\n'
        assert _run(tmp_path, {PY: src}) == []

    def test_escape_with_reason(self, tmp_path):
        src = 'def run_once(db):\n    # poll-budget-ok: tiny config table, 3 rows, read once a day\n    return db.table("t").select("*").execute()\n'
        assert _run(tmp_path, {PY: src}) == []

    def test_escape_without_reason_is_not_an_escape(self, tmp_path):
        src = 'def run_once(db):\n    # poll-budget-ok: ok\n    return db.table("t").select("*").execute()\n'
        assert len(_run(tmp_path, {PY: src})) == 1


class TestR4Frontend:
    @needs_ts
    @pytest.mark.parametrize("src", [
        "useQuery({ queryKey: ['a'], queryFn: f, refetchInterval: 5000 });",
        "useQuery({ queryKey: ['a'], queryFn: f, refetchInterval: (q) => (q.state.data ? false : 2000) });",
        "const refetchInterval = 3000; useQuery({ queryKey: ['a'], queryFn: f, refetchInterval });",
        "useEffect(() => { const t = setInterval(tick, 1000); return () => clearInterval(t); }, []);",
        "useEffect(() => { const t = window.setInterval(tick, 1000); return () => clearInterval(t); }, []);",
    ])
    def test_flagged(self, tmp_path, src):
        issues = _run(tmp_path, {TS: f"export function P() {{\n  {src}\n  return null;\n}}\n"})
        assert len(issues) == 1 and issues[0]["file"] == TS and issues[0]["severity"] == "high"

    @needs_ts
    @pytest.mark.parametrize("val", ["false", "undefined", "0"])
    def test_off_values_clean(self, tmp_path, val):
        src = f"export const q = {{ queryKey: ['a'], queryFn: f, refetchInterval: {val} }};\n"
        assert _run(tmp_path, {TS: src}) == []

    @needs_ts
    def test_declared_clean(self, tmp_path):
        src = f"export const q = {{\n  // {GOOD_TS}\n  refetchInterval: 5000,\n}};\n"
        assert _run(tmp_path, {TS: src}) == []

    @needs_ts
    def test_declaration_without_a_number_is_a_finding(self, tmp_path):
        src = "export const q = {\n  // poll-budget: 5s; hidden=paused\n  refetchInterval: 5000,\n};\n"
        assert len(_run(tmp_path, {TS: src})) == 1

    @needs_ts
    def test_background_true_needs_hidden_runs(self, tmp_path):
        base = "export const q = {\n  // %s\n  refetchInterval: false,\n  refetchIntervalInBackground: true,\n};\n"
        assert len(_run(tmp_path, {TS: base % GOOD_TS})) == 1
        assert _run(tmp_path, {TS: base % GOOD_TS.replace("hidden=paused", "hidden=runs")}) == []

    @needs_ts
    def test_test_files_excluded(self, tmp_path):
        src = "setInterval(f, 10);\n"
        assert _run(tmp_path, {"products/demo/frontend/src/a.test.tsx": src, "seed/lib/frontend/src/__tests__/b.ts": src}) == []

    @needs_ts
    def test_seed_frontend_scanned(self, tmp_path):
        assert len(_run(tmp_path, {"seed/lib/frontend/src/h.ts": "setInterval(f, 10);\n"})) == 1


class TestSelf:
    def test_message_cites_the_doc_and_the_fix(self, tmp_path):
        msg = _run(tmp_path, {PY: LOOP})[0]["issue"]
        assert "KB § PATTERNS/backend/polling-request-budget.md" in msg and "poll-budget:" in msg and "/day" in msg
