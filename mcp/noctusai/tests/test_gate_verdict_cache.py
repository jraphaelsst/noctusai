"""Gate verdict cache (2026-11-04, noctusai-04 ask A): an integrate retry
re-ran ALL ~30 gates from zero, including ones already green on identical
inputs - every retry a fresh lottery against load on a moving dev."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.noctus.dev import gate_sweep as GS  # noqa: E402
from tools.noctus.dev import gate_verdict_cache as GVC  # noqa: E402

GREEN = {"gate": "pytest:alpha", "ran": True, "exit_code": 0, "summary": "12 passed", "duration_s": 40.0}


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _commit(root: Path, msg: str) -> None:
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", msg)


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "repo"
    for rel, body in {
        "products/alpha/backend/app.py": "a = 1\n",
        "products/beta/backend/app.py": "b = 1\n",
        "seed/lib/x.py": "s = 1\n",
        "mcp/noctusai/t.py": "m = 1\n",
        "package-lock.json": "{}\n",
        "KNOWLEDGE-BASE/doc.md": "d\n",
    }.items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body)
    _git(root, "init", "-q")
    _commit(root, "init")
    return root


def _spec(root: Path, gate: str = "pytest:alpha") -> GS.GateSpec:
    return GS.GateSpec(gate, ["python3", "-m", "pytest", "-q"], root / "products" / "alpha" / "backend")


def _cache(root: Path, tmp_path: Path) -> GVC.GateVerdictCache:
    return GVC.GateVerdictCache(root, path=tmp_path / "verdicts.ndjson", runner_fingerprint="fp1")


def test_green_on_identical_inputs_is_reused(repo, tmp_path):
    c = _cache(repo, tmp_path)
    assert c.store(_spec(repo), GREEN)
    hit = _cache(repo, tmp_path).lookup(_spec(repo))
    assert hit["exit_code"] == 0 and hit["ran"] is True and hit["cached_from"]["duration_s"] == 40.0
    assert GS._verdict([hit]) == "green"


def test_unrelated_paths_do_not_invalidate(repo, tmp_path):
    _cache(repo, tmp_path).store(_spec(repo), GREEN)
    (repo / "products/beta/backend/app.py").write_text("b = 2\n")
    (repo / "mcp/noctusai/t.py").write_text("m = 2\n")
    (repo / "KNOWLEDGE-BASE/doc.md").write_text("d2\n")
    _commit(repo, "moving dev")
    assert _cache(repo, tmp_path).lookup(_spec(repo)) is not None


@pytest.mark.parametrize("rel", ["products/alpha/backend/app.py", "seed/lib/x.py", "package-lock.json"])
def test_a_change_in_the_closure_or_root_files_misses(repo, tmp_path, rel):
    _cache(repo, tmp_path).store(_spec(repo), GREEN)
    (repo / rel).write_text("changed\n")
    _commit(repo, "touch closure")
    assert _cache(repo, tmp_path).lookup(_spec(repo)) is None


def test_runner_fingerprint_change_misses(repo, tmp_path):
    _cache(repo, tmp_path).store(_spec(repo), GREEN)
    c2 = GVC.GateVerdictCache(repo, path=tmp_path / "verdicts.ndjson", runner_fingerprint="fp2")
    assert c2.lookup(_spec(repo)) is None


def test_dirty_closure_is_never_looked_up_or_stored(repo, tmp_path):
    (repo / "products/alpha/backend/app.py").write_text("dirty\n")
    c = _cache(repo, tmp_path)
    assert c.key(_spec(repo)) is None and not c.store(_spec(repo), GREEN)


@pytest.mark.parametrize("extra", [{"exit_code": 1}, {"harness_suspect": {"x": 1}}, {"timed_out": True},
                                   {"waiting_for_slot": {}}, {"false_red": True}, {"ran": False}])
def test_only_unambiguous_greens_are_stored(repo, tmp_path, extra):
    assert not _cache(repo, tmp_path).store(_spec(repo), {**GREEN, **extra})


def test_whole_repo_gates_are_never_cached(repo, tmp_path):
    spec = GS.GateSpec("mcp_toolkit_tests:scoped", ["python3"], repo)
    assert _cache(repo, tmp_path).key(spec) is None
    assert GVC.input_closure("pytest:seed/lib/backend") == ["seed", "templates"]


def test_kill_switch(monkeypatch, repo):
    monkeypatch.setenv("NOCTUS_GATE_VERDICT_CACHE", "off")
    assert GVC.make_cache(repo) is None


def test_run_gates_skips_the_run_on_a_hit(repo, tmp_path):
    calls = []

    def run_gate(spec):
        calls.append(spec.gate)
        return 0, "12 passed", 3.0, "12 passed"
    c = _cache(repo, tmp_path)
    first = GS._run_gates([_spec(repo)], run_gate, verdict_cache=c)
    second = GS._run_gates([_spec(repo)], run_gate, verdict_cache=_cache(repo, tmp_path))
    assert calls == ["pytest:alpha"]
    assert "cached_from" not in first[0] and second[0]["cached_from"]["tip"]
