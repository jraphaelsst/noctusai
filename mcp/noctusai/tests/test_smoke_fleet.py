"""Colocated tests for noctus.dev.smoke_fleet.

No real network — a stub fetcher is injected. Registry is parsed from the
real start.sh (single source of truth, as the script does).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import smoke_fleet as SF  # noqa: E402

REPO = Path(__file__).resolve().parents[3]


def test_parse_registry_matches_start_sh():
    reg = SF.parse_registry((REPO / "start.sh").read_text())
    slugs = [r[0] for r in reg]
    assert "core" in slugs and "seed" in slugs
    # each entry is (slug, name, bport, fport)
    core = next(r for r in reg if r[0] == "core")
    assert core == ("core", "Core", "8000", "5173")


def test_parse_registry_empty_block():
    assert SF.parse_registry("no registry here") == []


def test_all_healthy_exit_0():
    res = SF.smoke_fleet(fetch_status=lambda url: "200", repo_root=str(REPO))
    assert res["ok"] is True
    assert res["status"] == "healthy"
    assert res["exit_code"] == 0
    assert res["failed"] == 0
    assert res["passed"] == res["total"]
    assert all(b["ok"] for b in res["backends"])
    # frontend sample reported, not counted toward pass/fail
    assert {f["slug"] for f in res["frontends"]} == {"core", "seed"}


def test_one_backend_down_exit_1():
    # port 8013 = igig, an ACTIVE product (deploy/fleet/active-scope.txt) —
    # an asleep product's port would never be checked at all (see the
    # skipped_asleep tests below), so it cannot stand in as "the one down".
    def fetcher(url: str) -> str:
        return "FAIL" if ":8013/" in url else "200"

    res = SF.smoke_fleet(fetch_status=fetcher, repo_root=str(REPO))
    assert res["status"] == "degraded"
    assert res["exit_code"] == 1
    assert res["failed"] == 1
    assert res["passed"] == res["total"] - 1
    down = [b for b in res["backends"] if not b["ok"]]
    assert len(down) == 1 and down[0]["port"] == "8013"


def test_non_200_counts_as_fail():
    res = SF.smoke_fleet(fetch_status=lambda url: "503", repo_root=str(REPO))
    assert res["status"] == "degraded"
    assert res["exit_code"] == 1
    assert res["failed"] == res["total"]


def test_frontend_not_counted_toward_fail():
    # frontends never serve 200 here, backends all 200 → still healthy
    def fetcher(url: str) -> str:
        return "200" if "/api/health" in url else "FAIL"

    res = SF.smoke_fleet(fetch_status=fetcher, repo_root=str(REPO))
    assert res["status"] == "healthy"
    assert res["exit_code"] == 0
    assert all(not f["ok"] for f in res["frontends"])


def test_missing_start_sh(tmp_path):
    res = SF.smoke_fleet(fetch_status=lambda u: "200", repo_root=str(tmp_path))
    assert res["ok"] is False
    assert res["status"] == "error"
    assert res["exit_code"] == 1


# ── ASLEEP-product skip (deploy/fleet/active-scope.txt) ────────────


def _make_fleet(tmp_path: Path, active: list[str]) -> Path:
    """A synthetic repo_root with a 3-slug start.sh registry (two of which
    are asleep) + an explicit active-scope.txt — hermetic, so this suite
    never depends on the real fleet's current awake/asleep split."""
    (tmp_path / "start.sh").write_text(
        "#!/bin/bash\n"
        "# BEGIN_PRODUCTS_REGISTRY\n"
        "PRODUCTS=(\n"
        '  "core:Core:8000:5173"\n'
        '  "awake-one:Awake One:8001:5174"\n'
        '  "asleep-one:Asleep One:8002:5175"\n'
        ")\n"
        "# END_PRODUCTS_REGISTRY\n"
    )
    fleet_dir = tmp_path / "deploy" / "fleet"
    fleet_dir.mkdir(parents=True)
    (fleet_dir / "active-scope.txt").write_text("\n".join(active) + "\n")
    return tmp_path


def test_asleep_backend_skipped_never_fetched(tmp_path):
    root = _make_fleet(tmp_path, ["core", "awake-one"])  # asleep-one omitted
    fetched: list[str] = []

    def fetcher(url: str) -> str:
        fetched.append(url)
        return "200"

    res = SF.smoke_fleet(fetch_status=fetcher, repo_root=str(root))
    assert res["ok"] is True
    assert {b["slug"] for b in res["backends"]} == {"core", "awake-one"}
    assert res["skipped_asleep"] == ["asleep-one"]
    assert not any(":8002/" in u for u in fetched)  # never even hit
    assert res["total"] == 2


def test_asleep_backend_down_does_not_degrade_the_sweep(tmp_path):
    root = _make_fleet(tmp_path, ["core", "awake-one"])

    def fetcher(url: str) -> str:
        return "FAIL" if ":8002/" in url else "200"  # asleep-one's port down

    res = SF.smoke_fleet(fetch_status=fetcher, repo_root=str(root))
    assert res["status"] == "healthy"
    assert res["exit_code"] == 0
    assert res["skipped_asleep"] == ["asleep-one"]


def test_all_active_reports_empty_skipped_asleep(tmp_path):
    root = _make_fleet(tmp_path, ["core", "awake-one", "asleep-one"])
    res = SF.smoke_fleet(fetch_status=lambda u: "200", repo_root=str(root))
    assert res["skipped_asleep"] == []
    assert {b["slug"] for b in res["backends"]} == {"core", "awake-one", "asleep-one"}
