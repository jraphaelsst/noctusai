"""Duration-balanced shard splitter for the "MCP Toolkit Tests" CI job.

Stdlib only, deterministic: greedy longest-processing-time (LPT) bin packing
of ``mcp/noctusai/tests/**/test_*.py`` over N shards, weighted by the measured
per-file seconds in ``scripts/ci/mcp-test-durations.json``. A file absent from
the table weighs the table's median, so a new test still lands somewhere
deterministic. ``test_compliance.py`` stays isolated in its own job (it is not
part of the numbered shards).

Workflow call::

    python3 mcp/noctusai/tools/noctus/dev/ci_shards.py --shard $SHARD --total 4

Refresh the table: for each shard job log of a CI run, take the pytest
progress lines (``....  [ 12%]``) with their log timestamps, map test index to
time by interpolation, and attribute time to files by their collected test
count (``pytest --collect-only -q``). Rewrite ``seconds`` in the JSON; the
guard test only demands that every split is a complete partition.
KB § PATTERNS/architect/mcp-first-scripts.md.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

ISOLATED = "mcp/noctusai/tests/test_compliance.py"
FLOOR = 99
GLOBS = ("mcp/noctusai/tests/*test_*.py", "mcp/noctusai/tests/**/test_*.py")
DEFAULT_TABLE = "scripts/ci/mcp-test-durations.json"


def median_duration(durations: dict[str, float]) -> float:
    vals = [float(v) for v in durations.values()]
    return statistics.median(vals) if vals else 1.0


def split(files: list[str], durations: dict[str, float], total: int) -> list[list[str]]:
    """LPT bin packing. Deterministic: ties break on (weight desc, name asc),
    and the least-loaded shard wins ties by lowest index."""
    if total < 1:
        raise ValueError("total must be >= 1")
    med = median_duration(durations)
    weighted = sorted(
        ((float(durations.get(f, med)), f) for f in set(files) if f != ISOLATED),
        key=lambda wf: (-wf[0], wf[1]),
    )
    loads = [0.0] * total
    shards: list[list[str]] = [[] for _ in range(total)]
    for w, f in weighted:
        k = min(range(total), key=lambda i: (loads[i], i))
        shards[k].append(f)
        loads[k] += w
    return [sorted(s) for s in shards]


def shard_loads(shards: list[list[str]], durations: dict[str, float]) -> list[float]:
    med = median_duration(durations)
    return [sum(float(durations.get(f, med)) for f in s) for s in shards]


def list_test_files(repo_root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", *GLOBS], cwd=repo_root, check=True, capture_output=True, text=True
    ).stdout
    return sorted({ln for ln in out.splitlines() if ln})


def load_table(path: Path) -> dict[str, float]:
    data = json.loads(path.read_text())
    return {k: float(v) for k, v in data["seconds"].items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--shard", required=True, help="0..total-1 or 'compliance'")
    ap.add_argument("--total", type=int, default=4)
    ap.add_argument("--table", default=DEFAULT_TABLE)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--out", default="/tmp/mcp-shard-files.txt")
    ap.add_argument("--list", action="store_true", help="print the shard's files instead of writing --out")
    a = ap.parse_args(argv)
    root = Path(a.repo_root)
    files = list_test_files(root)
    if ISOLATED not in files:
        print(f"::error::the named isolate '{ISOLATED}' no longer exists", file=sys.stderr)
        return 1
    rest = [f for f in files if f != ISOLATED]
    if len(rest) < FLOOR:
        print(f"::error::only {len(rest)} test file(s) discovered (minus the isolate) - refusing to shard over nothing", file=sys.stderr)
        return 1
    if a.shard == "compliance":
        mine, note = [ISOLATED], "shard compliance: 1 file (isolated)"
    else:
        k = int(a.shard)
        if not 0 <= k < a.total:
            print(f"::error::shard {k} outside 0..{a.total - 1}", file=sys.stderr)
            return 1
        durations = load_table(root / a.table)
        shards = split(rest, durations, a.total)
        mine = shards[k]
        est = shard_loads(shards, durations)
        note = f"shard {k}/{a.total}: {len(mine)} of {len(rest)} non-isolated file(s), est {est[k]:.0f}s (max {max(est):.0f}s)"
    print(note)
    body = "\n".join(mine) + "\n"
    if a.list:
        sys.stdout.write(body)
    else:
        Path(a.out).write_text(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
