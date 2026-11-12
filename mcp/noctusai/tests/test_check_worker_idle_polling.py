"""`check_worker_idle_polling` — a worker's idle poll is a per-tick RPC (W1-C, 2026-11-12)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_worker_idle_polling  # noqa: E402

WORKER_REL = "seed/lib/backend/noctusai_lib/domain/jobs/worker.py"
PROD_REL = "products/demo/backend/app/worker.py"


def _write(tmp: Path, rel: str, body: str) -> None:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)


class TestCheckWorkerIdlePolling:
    def test_short_cap_is_flagged(self, tmp_path):
        _write(tmp_path, PROD_REL, "w = Worker(repo, worker_id='x', handlers={}, max_idle_interval_seconds=30.0)\n")
        issues = check_worker_idle_polling(repo_root=tmp_path)
        assert len(issues) == 1 and "30" in issues[0]["issue"]

    def test_fixed_one_second_idle_is_flagged(self, tmp_path):
        _write(tmp_path, PROD_REL,
               "w = Worker(repo, worker_id='x', handlers={}, poll_interval_seconds=1.0, max_idle_interval_seconds=1.0)\n")
        assert len(check_worker_idle_polling(repo_root=tmp_path)) == 1

    def test_default_or_long_cap_is_clean(self, tmp_path):
        _write(tmp_path, PROD_REL,
               "a = Worker(repo, worker_id='x', handlers={})\n"
               "b = Worker(repo, worker_id='y', handlers={}, poll_interval_seconds=2.0, max_idle_interval_seconds=300.0)\n")
        assert check_worker_idle_polling(repo_root=tmp_path) == []

    def test_poll_ok_waiver(self, tmp_path):
        _write(tmp_path, PROD_REL,
               "w = Worker(repo, worker_id='x', handlers={}, max_idle_interval_seconds=10.0)  # poll-ok: latency SLO\n")
        assert check_worker_idle_polling(repo_root=tmp_path) == []

    def test_default_constant_below_300_is_flagged(self, tmp_path):
        _write(tmp_path, WORKER_REL, "DEFAULT_MAX_IDLE_INTERVAL_SECONDS = 30.0\n")
        assert len(check_worker_idle_polling(repo_root=tmp_path)) == 1
        _write(tmp_path, WORKER_REL, "DEFAULT_MAX_IDLE_INTERVAL_SECONDS = 300.0\n")
        assert check_worker_idle_polling(repo_root=tmp_path) == []

    def test_fixed_sleep_in_run_forever_is_flagged(self, tmp_path):
        _write(tmp_path, PROD_REL,
               "class W:\n    async def run_forever(self):\n        while True:\n            await asyncio.sleep(1)\n")
        assert len(check_worker_idle_polling(repo_root=tmp_path)) == 1

    def test_unbounded_select_in_claim_gate_is_flagged(self, tmp_path):
        _write(tmp_path, PROD_REL,
               "def make():\n    async def claim_gate():\n        r = db.table('s').select('*').eq('k', 1).execute()\n        return bool(r.data)\n")
        assert len(check_worker_idle_polling(repo_root=tmp_path)) == 1

    def test_bounded_select_in_claim_gate_is_clean(self, tmp_path):
        _write(tmp_path, PROD_REL,
               "def make():\n    async def claim_gate():\n        r = db.table('s').select('v').eq('k', 1).limit(1).execute()\n        return bool(r.data)\n")
        assert check_worker_idle_polling(repo_root=tmp_path) == []

    def test_tests_dir_is_ignored(self, tmp_path):
        _write(tmp_path, "products/demo/backend/tests/test_w.py",
               "w = Worker(r, worker_id='x', handlers={}, max_idle_interval_seconds=1.0)\n")
        assert check_worker_idle_polling(repo_root=tmp_path) == []

    def test_fleet_is_clean(self):
        issues = check_worker_idle_polling()
        assert issues == [], "\n".join(f"{i['file']}: {i['issue'][:110]}" for i in issues)
