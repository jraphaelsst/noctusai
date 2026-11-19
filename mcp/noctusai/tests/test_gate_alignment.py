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

    def test_advisory_invocation_logs_warn_not_deny(self, tmp_path, monkeypatch):
        log = tmp_path / "ev.ndjson"
        monkeypatch.setenv("NOCTUS_GUARD_EVENT_LOG", str(log))
        monkeypatch.setenv("NOC_GATE_ADVISORY", "1")
        ga.record_cli_exit(["--check-foo"], 1)
        ga.record_cli_exit(["--check-foo"], 0)
        assert [json.loads(l)["outcome"] for l in log.read_text().splitlines()] == ["warn", "pass"]

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

    def test_gate_walls_ledger_rows_come_from_the_committed_inventory_and_reconcile(self, tmp_path):
        from tools.noctus.dev import findings_ledger as gl
        from tools.noctus.dev import gate_wall_findings as gw
        inv = {"gates": {
            "keeper:check-x": {**GOOD, "class": "wall", "firings": {"count": 50, "sessions": 9}, "remediation": "NOC-REMEDIATE[gate-wall] ship the scaffold"},
            "keeper:check-fixed": {**GOOD, "class": "wall", "firings": {"count": 20, "sessions": 9}, "remediation": "FIXED 2026-11-05"},
            "guard:kept": {**GOOD, "mechanism": "none (an in-line choice, nothing to scaffold)", "class": "wall", "firings": {"count": 20, "sessions": 9}},
            "keeper:check-dem": {**GOOD, "placement": "demoted", "demoted": {"since": "2026-01-01", "expiry": "2026-02-01", "destination": "d"}}}}
        root = _tree(tmp_path, inv, hook_flags=())
        rows = gw.current_rows(root)
        assert set(rows) == {"wall:keeper:check-x", "demoted:keeper:check-dem"}
        assert rows["wall:keeper:check-x"]["severity"] == "high" and rows["wall:keeper:check-x"]["scope"] == "tooling-engineer"
        out = gl.reconcile("gate-walls", root, found_by="test")
        assert out["ok"] if "ok" in out else True
        assert gl.check("gate-walls", root) == []
        sarif = gl.export_sarif("gate-walls", root)
        rules = {r["ruleId"] for run in sarif["runs"] for r in run["results"]}
        assert rules and rules <= {"walls", "wall", "demoted-expired", "matrix-pending"}


class TestDeclare:
    def test_declare_refuses_invalid_and_writes_valid(self, tmp_path):
        root = _tree(tmp_path, {"gates": {}})
        assert ga.declare_gate("keeper:check-x", "", "o", root=root)["ok"] is False
        assert ga.declare_gate("keeper:check-x", "scaffold: s", "", root=root)["ok"] is False
        assert ga.declare_gate("keeper:check-x", "scaffold: s", "o", source="KB §", root=root)["ok"] is True
        assert ga.load_inventory(root)["gates"]["keeper:check-x"]["new"] is True

    def test_existing_gate_skips_the_new_gate_requirements(self, tmp_path):
        root = _tree(tmp_path, {"gates": {}})
        assert ga.declare_gate("keeper:check-x", "none (hand-written yaml, nothing to scaffold)", "o",
                               placement="blocking", existing=True, root=root)["ok"]
        assert ga.triad_issues(root) == []


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


class TestRefusalClasses:
    """Refusals are counted by CLASS, so the same wall is one thing across sessions (2026-11-14)."""

    def _ev(self, key, days_ago, session, now):
        import datetime as dt
        ts = (now - dt.timedelta(days=days_ago)).isoformat(timespec="seconds")
        return {"gate": "g", "outcome": "deny", "ts": ts, "session": session, "class": key}

    def test_class_key_is_stable_and_drops_volatile_tokens(self):
        a = ga.refusal_class("deliverable", "head_pushed_clean", "stale-request-head")
        assert a == "deliverable:head_pushed_clean:stale-request-head"
        assert ga.refusal_class("deliverable", "derived_current", "kb-counts 12 files abc1234def") == \
            "deliverable:derived_current:kb-counts-files"
        assert ga.refusal_class("mq", "eject", "conflict:products/*/x") == "mq:eject:conflict:products/*/x"
        assert ga.refusal_class("guard", "primary-write", "") == "guard:primary-write"

    def test_recurrence_counts_window_sessions_and_open_fix(self, tmp_path):
        import datetime as dt
        now = dt.datetime.now(dt.timezone.utc)
        k = "deliverable:derived_current:kb-counts"
        evs = [self._ev(k, 1, "s1", now), self._ev(k, 2, "s2", now), self._ev(k, 3, "s2", now),
               self._ev(k, 20, "s9", now), self._ev("other", 1, "s1", now)]
        (r,) = ga.refusal_recurrence([k], root=tmp_path, events=evs)
        assert r == {"class": k, "n_14d": 3, "sessions": 2, "open_fix": None}

    def test_open_fix_from_a_remediation_marker(self, tmp_path):
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        k = "mq:eject:conflict:docs"
        (tmp_path / "x.py").write_text(f"# NOC-REMEDIATE[{k}]: derive it - 2026-11-14\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        (r,) = ga.refusal_recurrence([k], root=tmp_path, events=[])
        assert r["open_fix"] == "marker:x.py"

    def test_unowned_needs_n3_and_no_fix(self, tmp_path):
        import datetime as dt
        now = dt.datetime.now(dt.timezone.utc)
        evs = [self._ev("a", i, f"s{i}", now) for i in range(1, 4)] + [self._ev("b", 1, "s", now)]
        assert [r["class"] for r in ga.unowned_classes(tmp_path, events=evs)] == ["a"]

    def test_trend_compares_this_week_with_last(self):
        import datetime as dt
        now = dt.datetime.now(dt.timezone.utc)
        evs = [self._ev("a", 1, "s", now), self._ev("a", 2, "s", now), self._ev("a", 9, "s", now),
               self._ev("b", 10, "s", now)]
        t = ga.trend(events=evs, now=now)
        assert (t["this_total"], t["last_total"]) == (2, 2)
        assert t["classes"][0] == {"class": "a", "this": 2, "last": 1, "delta": 1}

    def test_gate_quiet(self):
        import datetime as dt
        now = dt.datetime.now(dt.timezone.utc)
        assert ga.gate_quiet("a", 7, events=[self._ev("a", 9, "s", now)], now=now)
        assert not ga.gate_quiet("a", 7, events=[self._ev("a", 2, "s", now)], now=now)

    def test_cli_exit_deny_names_stage_and_first_finding(self, tmp_path, monkeypatch):
        log = tmp_path / "ev.ndjson"
        monkeypatch.setenv("NOCTUS_GUARD_EVENT_LOG", str(log))
        monkeypatch.setenv("NOC_HOOK_STAGE", "pre-push")
        out = "  \x1b[91m[high]\x1b[0m products/x/a.py:3 — Missing created_at on table 42\n"
        ga.record_cli_exit(["--check-foo"], 1, finding=ga.first_finding_code(out))
        row = json.loads(log.read_text().splitlines()[0])
        assert row["reason"] == "stage=pre-push code=missing-created_at-on-table"
        assert row["target"] == "stage:pre-push"
        assert row["class"] == ga.refusal_class("keeper:check-foo", "pre-push", "missing-created_at-on-table")
        assert ga.event_class({k: v for k, v in row.items() if k != "class"} | {"gate": row["guard"]}) == row["class"]

    def test_tee_captures_first_finding_without_altering_output(self, monkeypatch, capsys):
        monkeypatch.setattr(ga, "_first_finding", [])
        monkeypatch.setattr(sys, "argv", ["cli.py", "--check-foo"])
        monkeypatch.setattr(sys, "stdout", sys.stdout)
        ga.capture_first_finding()
        print("    [high] f.py — Bad thing here")
        sys.stdout = sys.stdout._inner
        assert ga._first_finding == ["bad-thing-here"]
        assert "Bad thing here" in capsys.readouterr().out


class TestUnownedKeeper:
    def test_warns_on_unowned_recurring_class_and_is_clean_otherwise(self, tmp_path):
        import datetime as dt
        now = dt.datetime.now(dt.timezone.utc)
        mk = lambda i: {"gate": "g", "outcome": "deny", "ts": (now - dt.timedelta(days=i)).isoformat(), "session": f"s{i}", "class": "g:x"}
        issues = compliance.check_refusal_classes_owned(repo_root=tmp_path, events=[mk(1), mk(2), mk(3)])
        assert [i["severity"] for i in issues] == ["high"] and "g:x" in issues[0]["issue"] and "--file-walls" in issues[0]["issue"]
        assert compliance.check_refusal_classes_owned(repo_root=tmp_path, events=[mk(1), mk(2)]) == []


class TestScaffoldKeeperOutputPassesItsOwnTriad:
    """NOC-REMEDIATE[scaffold-keeper-triad-prefix] closed: the scaffold's own declare command used to omit the source
    and the decision-matrix row, so the triad refused the output of the tool that exists to satisfy it."""

    def _scaffold(self):
        from tools.noctus.dev.scaffold_keeper import scaffold_keeper
        return scaffold_keeper("files_xyz", "xyz", mechanism="scaffold: noctus.dev.scaffold_keeper",
                               owner="tooling-engineer", source="KB § PATTERNS/common/gate-methodology-sync.md")

    def test_unedited_scaffold_declaration_satisfies_the_triad(self, tmp_path):
        out = self._scaffold()
        root = _tree(tmp_path, {"gates": {}, "decisions": []}, hook_flags=("check-xyz",))
        assert any("not declared" in i["issue"] for i in ga.triad_issues(root))  # the premise: red before declaring
        args = dict(out["declare_args"])
        res = ga.run_action(args.pop("action"), gate=args["gate"], mechanism=args["mechanism"], owner=args["owner"],
                            placement=args["placement"], source=args["source"], decision=args["decision"],
                            branch=args["branch"], root=root)
        assert res["ok"] and res["decision_row"]["gates"] == ["keeper:check-xyz"]
        assert ga.triad_issues(root) == []

    def test_declare_command_carries_every_leg_the_triad_checks(self):
        import shlex
        toks = shlex.split(self._scaffold()["declare_command"])
        for flag in ("--gate", "--mechanism", "--owner", "--gate-source", "--decision"):
            assert flag in toks
        assert toks[toks.index("--mechanism") + 1].startswith(ga.MECHANISM_PREFIXES)

    def test_without_source_or_decision_the_triad_still_refuses(self, tmp_path):
        root = _tree(tmp_path, {"gates": {}, "decisions": []}, hook_flags=("check-xyz",))
        ga.declare_gate("keeper:check-xyz", "scaffold: t", "tooling-engineer", root=root)
        msgs = " ".join(i["issue"] for i in ga.triad_issues(root))
        assert "cites no `source`" in msgs and "no decision-matrix row" in msgs

    def test_declare_decision_is_idempotent(self, tmp_path):
        root = _tree(tmp_path, {"gates": {}, "decisions": []}, hook_flags=("check-xyz",))
        for _ in range(2):
            ga.declare_gate("keeper:check-xyz", "scaffold: t", "o", source="KB § x", decision="d", root=root)
        assert len(json.loads((root / ga.INVENTORY_REL).read_text())["decisions"]) == 1


class TestRefusalBacklogConstruction:
    """The recurrence backlog cannot build up (2026-11-19): a class that crosses N>=3 gets its finding opened by
    the system, intended refusals are declared and never counted, and per-instance tails collapse to one class."""

    def _evs(self, key, n=3):
        import datetime as dt
        now = dt.datetime.now(dt.timezone.utc)
        return [{"gate": "g", "outcome": "deny", "class": key, "session": f"s{i}",
                 "ts": (now - dt.timedelta(days=i)).isoformat(), "reason": "boom"} for i in range(1, n + 1)]

    def _policy(self, root, *entries):
        (root / ga.POLICY_REL).parent.mkdir(parents=True, exist_ok=True)
        (root / ga.POLICY_REL).write_text(json.dumps({"intended": list(entries)}))

    @staticmethod
    def _owners(monkeypatch, rows):
        def init(self, root):
            self.policy, self.pointers, self.rows, self.markers = [], [], rows, {}
        monkeypatch.setattr(ga._Owners, "__init__", init)

    def test_canonical_class_collapses_per_instance_tails(self):
        c = ga.canonical_class
        assert c("keeper:x:pre-push:no-branch-pointer-found-for-feat/some-branch-v2") == \
            "keeper:x:pre-push:no-branch-pointer-found-for-feat/*"
        assert c("keeper:y:pre-commit:products/agents/backend/migrations/-_eval_x") == \
            "keeper:y:pre-commit:products/*/backend/migrations/*"
        assert ga.event_class({"class": "k:engineer-slice-feat/abc-def"}) == "k:engineer-slice-feat/*"
        assert c("deliverable:scoped_green:unmeasured") == "deliverable:scoped_green:unmeasured"

    def test_two_branches_of_one_kind_are_one_class(self):
        a = {"outcome": "deny", "gate": "g", "reason": "stage=pre-push code=no-pointer-for-feat/a"}
        b = {"outcome": "deny", "gate": "g", "reason": "stage=pre-push code=no-pointer-for-feat/b"}
        assert ga.event_class(a) == ga.event_class(b)

    def test_declared_intended_class_is_owned_not_backlog(self, tmp_path):
        self._policy(tmp_path, {"match": "guard:primary-write:refused-", "rationale": "primary write refused by design"})
        k = "guard:primary-write:refused-this-would-write-the-primary"
        (r,) = ga.refusal_recurrence([k], root=tmp_path, events=self._evs(k))
        assert r["open_fix"] == "intended:guard:primary-write:refused-"
        assert ga.unowned_classes(tmp_path, events=self._evs(k)) == []
        # a sibling class of the same guard (a timeout) is NOT intended
        t = "guard:primary-write:guard-timed-out"
        assert [x["class"] for x in ga.unowned_classes(tmp_path, events=self._evs(t))] == [t]

    def test_policy_entry_without_a_rationale_is_ignored(self, tmp_path):
        self._policy(tmp_path, {"match": "g:", "rationale": "x"})
        assert ga.load_policy(tmp_path) == []

    @pytest.mark.parametrize("status,owned", [("open", True), ("in-progress", True), ("accepted", True), ("fixed", False)])
    def test_findings_row_states_decide_ownership(self, tmp_path, monkeypatch, status, owned):
        k = "keeper:check-x:pre-commit:y"
        self._owners(monkeypatch, {ga.FINDING_KEY_PREFIX + k: {"id": "GW-1", "status": status, "target": k}})
        assert bool(ga._Owners(tmp_path).find(k)) is owned

    def test_a_wall_finding_on_the_gate_owns_its_stage_variants(self, tmp_path, monkeypatch):
        self._owners(monkeypatch, {"wall:keeper:check-x": {"id": "GW-9", "status": "open", "target": "keeper:check-x", "kind": "wall"}})
        assert ga._Owners(tmp_path).find("keeper:check-x:pre-push:some-code") == "findings:GW-9"
        assert ga._Owners(tmp_path).find("keeper:check-z:pre-push:some-code") is None

    def test_file_missing_findings_opens_one_row_per_unowned_class_and_only_those(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NOCTUS_REFUSAL_BACKLOG_LOG", str(tmp_path / "bl.ndjson"))
        evs = self._evs("keeper:check-a:pre-commit:x") + self._evs("keeper:check-b", n=2)
        filed: list[dict] = []
        res = ga.file_missing_findings(tmp_path, events=evs, filer=lambda **kw: (filed.append(kw), {"ok": True, "id": "GW-1"})[1])
        assert [f["target"] for f in filed] == ["keeper:check-a:pre-commit:x"]
        f = filed[0]
        assert (f["status"], f["key"], f["source"], f["kind"]) == (
            "open", "refusal:keeper:check-a:pre-commit:x", ga.FINDING_SOURCE, "refusal-class")
        assert "triage by" in f["note"] and "3x across 3 session(s)" in f["note"]
        assert res["filed"][0]["id"] == "GW-1" and res["failed"] == []

    def test_file_missing_findings_reports_a_failed_write_loudly(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NOCTUS_REFUSAL_BACKLOG_LOG", str(tmp_path / "bl.ndjson"))
        res = ga.file_missing_findings(tmp_path, events=self._evs("k:x"), filer=lambda **kw: {"ok": False, "error": "offline"})
        assert res["filed"] == [] and res["failed"][0]["error"] == "offline"

    def test_live_read_auto_files_and_an_explicit_event_list_does_not(self, tmp_path, monkeypatch):
        calls: list[dict] = []
        monkeypatch.setattr(ga, "file_missing_findings", lambda *a, **kw: calls.append(kw) or {})
        ga.refusal_recurrence(["k:x"], root=tmp_path, events=self._evs("k:x"))
        assert calls == []
        monkeypatch.setattr(ga, "read_events", lambda: self._evs("k:x"))
        ga.refusal_recurrence(["k:x"], root=tmp_path, auto_file=True)
        assert len(calls) == 1

    def test_backlog_stats_counts_uncovered_and_intended(self, tmp_path):
        self._policy(tmp_path, {"match": "guard:ok:", "rationale": "intended by design"})
        evs = self._evs("guard:ok:a") + self._evs("keeper:check-q") + self._evs("keeper:check-small", n=2)
        s = ga.backlog_stats(tmp_path, events=evs)
        assert (s["recurring"], s["uncovered"], s["intended"]) == (2, 1, 1)

    def test_snapshot_is_appended_as_telemetry(self, tmp_path, monkeypatch):
        log = tmp_path / "bl.ndjson"
        monkeypatch.setenv("NOCTUS_REFUSAL_BACKLOG_LOG", str(log))
        ga.record_backlog_snapshot(tmp_path, events=self._evs("k:x"), filed=1)
        row = json.loads(log.read_text().splitlines()[-1])
        assert row["uncovered"] == 1 and row["filed"] == 1

    def test_deny_path_autofile_is_throttled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NOCTUS_REFUSAL_AUTOFILE", "1")
        calls: list[int] = []
        monkeypatch.setattr(ga, "refusal_recurrence", lambda *a, **kw: calls.append(1) or [])
        monkeypatch.setattr(ga, "all_classes", lambda **kw: [])
        stamp = tmp_path / "stamp"
        ga.maybe_autofile_on_deny(tmp_path, now=1_000_000.0, marker=stamp)
        ga.maybe_autofile_on_deny(tmp_path, now=stamp.stat().st_mtime + 5, marker=stamp)
        assert len(calls) == 1
        ga.maybe_autofile_on_deny(tmp_path, now=stamp.stat().st_mtime + ga._AUTOFILE_THROTTLE_S + 1, marker=stamp)
        assert len(calls) == 2

    def test_the_committed_policy_is_well_formed_and_carries_a_rationale_per_entry(self):
        raw = json.loads((REAL_ROOT / ga.POLICY_REL).read_text())["intended"]
        assert raw and len(ga.load_policy(REAL_ROOT)) == len(raw)

    def test_keeper_blocks_an_unowned_class_and_clears_when_owned(self, tmp_path):
        evs = self._evs("keeper:check-new:pre-push:z")
        (issue,) = compliance.check_refusal_classes_owned(repo_root=tmp_path, events=evs)
        assert issue["severity"] == "high"
        self._policy(tmp_path, {"match": "keeper:check-new", "rationale": "intended by design here"})
        assert compliance.check_refusal_classes_owned(repo_root=tmp_path, events=evs) == []
