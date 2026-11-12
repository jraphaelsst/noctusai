"""Guard for the duration-balanced MCP test shard splitter."""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "mcp" / "noctusai" / "tools" / "noctus" / "dev"))
import ci_shards  # noqa: E402

TABLE = REPO / ci_shards.DEFAULT_TABLE
TOTAL = 4


def _files() -> list[str]:
    return [f for f in ci_shards.list_test_files(REPO) if f != ci_shards.ISOLATED]


def _table() -> dict[str, float]:
    return ci_shards.load_table(TABLE)


def test_partition_complete_and_disjoint():
    files = _files()
    shards = ci_shards.split(files, _table(), TOTAL)
    flat = [f for s in shards for f in s]
    assert sorted(flat) == sorted(files)
    assert len(flat) == len(set(flat))
    assert ci_shards.ISOLATED not in flat


def test_split_is_deterministic():
    files = _files()
    a = ci_shards.split(files, _table(), TOTAL)
    b = ci_shards.split(list(reversed(files)), _table(), TOTAL)
    assert a == b


def test_balances_better_than_round_robin_on_real_table():
    files = sorted(_files())
    table = _table()
    rr = [files[i::TOTAL] for i in range(TOTAL)]
    lpt = ci_shards.split(files, table, TOTAL)
    lpt_max, rr_max = max(ci_shards.shard_loads(lpt, table)), max(ci_shards.shard_loads(rr, table))
    # The invariant is "near the ideal split", not "beats round-robin by X%": how well round-robin does depends on
    # file-name order (dev's set at 2026-11-12 gave rr 622s vs lpt 541s, so a 0.7x ratio failed on luck alone).
    ideal = sum(ci_shards.shard_loads([files], table)) / TOTAL
    biggest = max(ci_shards.shard_loads([[f] for f in files], table))
    assert lpt_max <= max(1.05 * ideal, biggest)
    assert lpt_max <= rr_max


def test_unknown_files_get_the_median():
    table = {"a/test_x.py": 10.0, "a/test_y.py": 20.0, "a/test_z.py": 90.0}
    assert ci_shards.median_duration(table) == statistics.median(table.values())
    loads = ci_shards.shard_loads([["a/test_new.py"]], table)
    assert loads == [20.0]
    shards = ci_shards.split(list(table) + ["a/test_new.py"], table, 2)
    assert sorted(f for s in shards for f in s) == sorted([*table, "a/test_new.py"])


def test_table_covers_most_files():
    # not a hard requirement (unknown files are fine) but a rotted table should be refreshed
    files = set(_files())
    known = files & set(_table())
    assert len(known) >= 0.8 * len(files), "mcp-test-durations.json is stale; refresh it"


def test_cli_lists_every_shard_exactly_once():
    got: list[str] = []
    for k in list(range(TOTAL)):
        out = subprocess.run(
            [sys.executable, str(REPO / "mcp/noctusai/tools/noctus/dev/ci_shards.py"),
             "--shard", str(k), "--total", str(TOTAL), "--list", "--repo-root", str(REPO)],
            check=True, capture_output=True, text=True,
        ).stdout
        got += [ln for ln in out.splitlines() if ln.startswith("mcp/")]
    assert sorted(got) == sorted(_files())


def test_workflow_calls_the_splitter():
    wf = (REPO / ".github/workflows/test.yml").read_text()
    call = "python3 mcp/noctusai/tools/noctus/dev/ci_shards.py --shard"
    assert wf.count(call) >= 2  # shard step + coverage proof
    assert '--shard "$SHARD" --total "$MCP_TEST_TOTAL_SHARDS"' in wf
    assert "i % MCP_TEST_TOTAL_SHARDS" not in wf
    assert json.loads(TABLE.read_text())["seconds"]
