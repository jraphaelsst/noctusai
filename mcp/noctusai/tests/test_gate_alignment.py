"""Build-triad telemetry + meta-gate (`noctus.dev.gate_alignment`, keeper `check_gate_triad`,
`check_new_dependency_justified`, scaffold_keeper refusal, scaffold_migration construction legs).
KB § PATTERNS/common/gate-methodology-sync.md."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import gate_alignment as ga  # noqa: E402
from tools.noctus.dev import compliance  # noqa: E402
from tools.noctus.dev.scaffold_migration import _guard_probe_stub  # noqa: E402

REAL_ROOT = Path(__file__).resolve().parents[3]


def _tree(tmp_path: Path, inventory: dict, baseline: list[str] | None = None, hook_flags=("check-x",)) -> Path:
    (tmp_path / "scripts/hooks").mkdir(parents=True)
    (tmp_path / "scripts/hooks/pre-commit").write_text("\n".join(f'"$PY" "$CLI" --{f}' for f in hook_flags))
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude/settings.json").write_text("{}")
    d = tmp_path / ga._PATTERN_DIR
    d.mkdir(parents=True)
    (tmp_path / ga.INVENTORY_REL).write_text(json.dumps(inventory))
    (tmp_path / ga.BASELINE_REL).write_text(json.dumps({"undeclared_mechanism": baseline or []}))
    return tmp_path


GOOD = {"mechanism": "scaffold: noctus.dev.scaffold_x", "owner": "tooling-engineer", "placement": "warn"}


class TestGateTriad:
    def test_green_when_declared(self, tmp_path):
        root = _tree(tmp_path, {"gates": {"keeper:check-x": GOOD}})
        assert ga.triad_issues(root) == []

    def test_red_undeclared_wired_gate(self, tmp_path):
        root = _tree(tmp_path, {"gates": {}})
        msgs = [i["issue"] for i in ga.triad_issues(root)]
        assert any("keeper:check-x" in m and "not declared" in m for m in msgs)

    def test_red_new_gate_without_mechanism_or_owner(self, tmp_path):
        root = _tree(tmp_path, {"gates": {"keeper:check-x": {"mechanism": "we will remember", "owner": ""}}})
        msgs = " ".join(i["issue"] for i in ga.triad_issues(root))
        assert "no owner" in msgs and "not a construction pointer" in msgs

    def test_legacy_baseline_passes_but_is_shrink_only(self, tmp_path):
        legacy = {"gates": {"keeper:check-x": {"mechanism": "", "owner": "o"}}}
        assert ga.triad_issues(_tree(tmp_path / "a", legacy, ["keeper:check-x"])) == []
        # once it declares a mechanism, the stale baseline row itself is flagged
        fixed = {"gates": {"keeper:check-x": GOOD}}
        msgs = [i["issue"] for i in ga.triad_issues(_tree(tmp_path / "b", fixed, ["keeper:check-x"]))]
        assert any("shrink the baseline" in m for m in msgs)

    def test_none_requires_a_real_reason(self):
        assert ga.mechanism_ok("none (an in-line choice, nothing to scaffold)")
        assert not ga.mechanism_ok("none (x)") and not ga.mechanism_ok("") and not ga.mechanism_ok("later")

    def test_new_blocking_gate_needs_shadow_and_source(self, tmp_path):
        inv = {"gates": {"keeper:check-x": {**GOOD, "placement": "blocking", "new": True}},
               "decisions": [{"id": "D1", "decision": "d", "home": "h", "construction": "c", "gate": "g",
                              "telemetry": "t", "branch": "b", "gates": ["keeper:check-x"]}]}
        msgs = " ".join(i["issue"] for i in ga.triad_issues(_tree(tmp_path, inv)))
        assert "shadow-precision" in msgs and "cites no `source`" in msgs

    def test_demoted_noisy_gate_needs_destination_and_expires(self, tmp_path):
        inv = lambda dem: {"gates": {"keeper:check-x": {**GOOD, "placement": "demoted", "demoted": dem}}}
        assert ga.triad_issues(_tree(tmp_path / "a", inv({"since": "2026-11-01", "expiry": "2999-01-01",
                                                          "destination": "research OWASP, fix detector"}))) == []
        assert "demoted-noisy without" in ga.triad_issues(_tree(tmp_path / "b", inv({"since": "2026-11-01"})))[0]["issue"]
        expired = inv({"since": "2026-01-01", "expiry": "2026-02-01", "destination": "d"})
        assert "past its expiry" in ga.triad_issues(_tree(tmp_path / "c", expired))[0]["issue"]

    def test_real_tree_is_green(self):
        assert compliance.check_gate_triad(REAL_ROOT) == []


class TestDecisionMatrix:
    ROW = {"id": "D1", "decision": "d", "home": "h", "construction": "c", "gate": "g", "telemetry": "t",
           "branch": "b", "gates": ["keeper:check-x"]}

    def test_missing_leg_fails_and_pending_is_a_finding(self, tmp_path):
        bad = {**self.ROW, "telemetry": ""}
        fails, _ = ga.matrix_issues(_tree(tmp_path / "a", {"gates": {"keeper:check-x": GOOD}, "decisions": [bad]}))
        assert any("missing leg `telemetry`" in f["issue"] for f in fails)
        pend = {**self.ROW, "construction": "pending:feat/access-tiers-gate"}
        fails, findings = ga.matrix_issues(_tree(tmp_path / "b", {"gates": {"keeper:check-x": GOOD}, "decisions": [pend]}))
        assert fails == [] and findings[0]["leg"] == "construction"

    def test_row_with_unknown_gate_and_new_gate_without_row_fail(self, tmp_path):
        inv = {"gates": {"keeper:check-x": {**GOOD, "new": True}}, "decisions": [{**self.ROW, "gates": ["keeper:check-nope"]}]}
        msgs = " ".join(f["issue"] for f in ga.matrix_issues(_tree(tmp_path, inv))[0])
        assert "check-nope is not in the inventory" in msgs and "no decision-matrix row" in msgs


class TestTelemetryAndWalls:
    def test_cli_exit_logs_one_event_per_gate_flag(self, tmp_path, monkeypatch):
        log = tmp_path / "ev.ndjson"
        monkeypatch.setenv("NOCTUS_GUARD_EVENT_LOG", str(log))
        ga.record_cli_exit(["--check-foo", "--paths", "a.py,b.py"], 1)
        ga.record_cli_exit(["--check-foo"], 0)
        ga.record_cli_exit(["--validate"], 1)  # not a gate flag -> no event
        rows = [json.loads(l) for l in log.read_text().splitlines()]
        assert [r["outcome"] for r in rows] == ["deny", "pass"]
        assert rows[0]["guard"] == "keeper:check-foo" and rows[0]["target"] == "a.py,b.py" and rows[0]["kind"] == "keeper"

    def test_effective_false_positive_is_a_refusal_never_followed_by_a_pass(self):
        ev = [{"gate": "g", "outcome": "deny", "ts": "1", "session": "s1", "target": "a"},
              {"gate": "g", "outcome": "pass", "ts": "2", "session": "s1", "target": "a"},
              {"gate": "g", "outcome": "deny", "ts": "3", "session": "s2", "target": "b"}]
        st = ga.gate_stats(ev)["g"]
        assert st["denies"] == 2 and st["fixed"] == 1 and st["effective_fp"] == 0.5

    def test_wall_ranking_threshold_and_demotion(self, tmp_path):
        inv = {"gates": {"keeper:check-x": {**GOOD, "firings": {"count": 12, "sessions": 5}},
                         "keeper:check-y": {**GOOD, "firings": {"count": 3, "sessions": 2}}}}
        root = _tree(tmp_path, inv, hook_flags=("check-x", "check-y"))
        rep = ga.walls_report(root, events=[])
        assert [w["gate"] for w in rep["walls"]] == ["keeper:check-x"]
        noisy = [{"gate": "keeper:check-y", "outcome": "deny", "ts": str(i), "session": f"s{i}", "target": str(i)} for i in range(6)]
        rep = ga.walls_report(root, events=noisy)
        assert any(w["gate"] == "keeper:check-y" and w["demote"] for w in rep["walls"])

    def test_wall_findings_are_sarif_shaped_and_deduped(self, tmp_path):
        rep = {"walls": [{"gate": "keeper:check-x", "firings": 12, "sessions": 5, "effective_fp": 0.0, "wall": True,
                          "demote": False, "mechanism": "", "owner": "o"}], "pending_matrix": []}
        assert ga.file_wall_findings(rep, tmp_path)["findings_written"] == 1
        assert ga.file_wall_findings(rep, tmp_path)["findings_written"] == 0
        row = json.loads((tmp_path / ga.WALL_FINDINGS_REL).read_text().splitlines()[0])
        assert row["ruleId"] == "keeper:check-x" and row["baselineState"] == "new" and row["suppressions"] == []


class TestDeclare:
    def test_declare_refuses_invalid_and_writes_valid(self, tmp_path):
        root = _tree(tmp_path, {"gates": {}})
        assert ga.declare_gate("keeper:check-x", "", "o", root=root)["ok"] is False
        assert ga.declare_gate("keeper:check-x", "scaffold: s", "", root=root)["ok"] is False
        assert ga.declare_gate("keeper:check-x", "scaffold: s", "o", source="KB §", root=root)["ok"] is True
        assert ga.load_inventory(root)["gates"]["keeper:check-x"]["new"] is True


class TestNewDependencyJustified:
    @pytest.fixture()
    def repo(self, tmp_path):
        def git(*a):
            subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)
        git("init", "-q"); git("config", "user.email", "t@t"); git("config", "user.name", "t")
        (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"react": "^18"}}))
        git("add", "."); git("commit", "-qm", "base")
        return tmp_path

    def _add(self, repo, name="shiny-lib"):
        (repo / "package.json").write_text(json.dumps({"dependencies": {"react": "^18", name: "^1"}}))

    def test_unrecorded_new_dependency_flagged_known_one_not(self, repo):
        self._add(repo)
        issues = compliance.check_new_dependency_justified(["package.json"], repo)
        assert len(issues) == 1 and "npm:shiny-lib" in issues[0]["issue"] and issues[0]["severity"] == "medium"

    def test_record_with_numbers_passes_without_numbers_fails(self, repo):
        self._add(repo)
        notes = repo / "mcp/noctusai"; notes.mkdir(parents=True)
        rec = {"job": "x", "in_repo_alternative": "home-grown x", "decision": "switch",
               "metrics": {"recall": "0.97 vs 0.81", "latency": "12ms vs 40ms"}}
        (notes / "dependency-additions.json").write_text(json.dumps({"npm:shiny-lib": rec}))
        assert compliance.check_new_dependency_justified(["package.json"], repo) == []
        rec["metrics"] = {"recall": "better", "latency": "faster"}  # unmeasured -> no switch
        (notes / "dependency-additions.json").write_text(json.dumps({"npm:shiny-lib": rec}))
        assert "numbers" in compliance.check_new_dependency_justified(["package.json"], repo)[0]["issue"]

    def test_never_judges_whether_the_tool_is_standard(self):
        gap = compliance._comparison_record_gap({"job": "j", "decision": "adopt", "in_repo_alternative": "none",
                                                 "reason": "nothing in-repo does X"})
        assert gap == ""


class TestConstructionLegs:
    def test_guard_probe_stub_is_ready_to_register(self):
        stub = _guard_probe_stub("acme", {"table": "audit_log", "guc": "acme.purge"})
        assert stub["guard_name"] == "guard_audit_log_append_only"
        assert 'kind="write_refusal"' in stub["probe_code"] and "NOC_PROBE:refused" in stub["probe_code"]

    def test_guard_event_log_resolves_to_primary_checkout(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("gfc", REAL_ROOT / "scripts/hooks/_guard_failclosed.py")
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        assert "worktrees" not in mod.EVENT_LOG.parts


class TestCliTelemetryWrapper:
    def test_real_cli_logs_a_gate_run_and_keeps_exit_code(self, tmp_path):
        log = tmp_path / "ev.ndjson"
        env = {**__import__("os").environ, "NOCTUS_GUARD_EVENT_LOG": str(log)}
        r = subprocess.run([sys.executable, str(REAL_ROOT / "mcp/noctusai/cli.py"), "--check-gate-triad"],
                           capture_output=True, text=True, env=env, cwd=REAL_ROOT, timeout=300)
        rows = [json.loads(l) for l in log.read_text().splitlines()]
        assert r.returncode == 0 and rows[-1]["guard"] == "keeper:check-gate-triad" and rows[-1]["outcome"] == "pass"
