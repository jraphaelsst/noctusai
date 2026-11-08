"""Orchestrator inline cutoff gate (build triad, D19): construction (release_steward request),
backstop keeper, telemetry. Every collaborator is an injected seam; nothing patches a guard.
KB § CONTEXT/PATTERNS/architect/parallelization-first-orchestration.md (Enforcement)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.noctus.dev import orchestrator_inline_cutoff as oic  # noqa: E402
from tools.noctus.dev.compliance import check_orchestrator_inline_over_cutoff  # noqa: E402

_spec = importlib.util.spec_from_file_location("rs_under_test", ROOT / "tools/noctus/dev/release_steward.py")
rs = importlib.util.module_from_spec(_spec)
sys.modules["rs_under_test"] = rs
_spec.loader.exec_module(rs)


def numstat(*items):
    return "\n".join(f"{a}\t{d}\t{p}" for a, d, p in items) + "\n"


def ptr(branch="feat/x", agent="tech-lead", role="orchestrator", status="shipped", ts="2026-11-08T10:00:00+00:00", **kw):
    return {"ts": ts, "branch": branch, "base": "origin/dev@abc1234", "commit": "def5678", "agent": agent,
            "role": role, "status": status, "session": "s1", **kw}


# ---- measurement -------------------------------------------------------------------------------
class TestMeasure:
    def test_counts_authored_paths_only(self):
        m = oic.measure(numstat((50, 10, "mcp/a.py"), (900, 0, "x/package-lock.json"), (5, 5, "project-history/l.ndjson"),
                                (3, 0, "templates/product-seed/b.py")))
        assert (m["loc"], m["files"], m["paths"]) == (60, 1, ["mcp/a.py"])

    def test_binary_numstat_dash_counts_as_file_zero_loc(self):
        m = oic.measure("-\t-\tassets/logo.png\n")
        assert (m["loc"], m["files"]) == (0, 1)

    @pytest.mark.parametrize("loc,files,over", [(99, 2, False), (100, 1, True), (10, 3, True), (0, 0, False), (99, 3, True)])
    def test_cutoff_boundaries(self, loc, files, over):
        assert oic.is_over(loc, files) is over


# ---- reasons -----------------------------------------------------------------------------------
class TestReason:
    def test_closed_set(self):
        assert set(oic.REASONS) == {"orchestrator_owned", "single_coherent_voice", "shared_state", "owner_directed"}

    @pytest.mark.parametrize("reason,note,ok", [
        ("orchestrator_owned", "merge conflict between two engineers", True),
        ("because", "long enough note here", False),
        (None, "long enough note here", False),
        ("owner_directed", "short", False),
        ("shared_state", None, False),
    ])
    def test_validate(self, reason, note, ok):
        assert (oic.validate_reason(reason, note) is None) is ok


# ---- scope -------------------------------------------------------------------------------------
class TestScope:
    @pytest.mark.parametrize("row,inline", [
        (ptr(agent="self-branch"), True), (ptr(agent="tech-lead"), True), (ptr(agent="tech-lead-inline"), True),
        (ptr(agent="backend-engineer"), False), (ptr(agent="self-branch", role="engineer"), False),
        (ptr(branch="feat/train-wave9"), False), (ptr(branch="feat/applied-record-core-2026"), False),
    ])
    def test_is_inline_pointer(self, row, inline):
        assert oic.is_inline_pointer(row) is inline

    def test_slice_scored_keeper_shares_the_agent_set(self):
        from tools.noctus.dev import compliance
        assert compliance._SLICE_INLINE_AGENTS is oic.INLINE_AGENTS


# ---- scan / keeper -----------------------------------------------------------------------------
BIG = {"loc": 400, "files": 9, "paths": ["mcp/noctusai/tools/x.py", "KNOWLEDGE-BASE/a.md"]}
SMALL = {"loc": 20, "files": 1, "paths": ["mcp/a.py"]}


class TestOrchestratorInlineOverCutoff:
    def run(self, rows, size, since=None):
        return check_orchestrator_inline_over_cutoff(repo_root=Path("/nonexistent"), rows=rows, since=since,
                                                     size_fn=lambda r: size(r) if callable(size) else size)

    def test_flags_over_cutoff_without_reason_as_warning_naming_specialists(self):
        out = self.run([ptr()], BIG)
        assert len(out) == 1 and out[0]["severity"] == "warning"
        assert "tooling-engineer" in out[0]["issue"] and "architect" in out[0]["issue"]
        assert "parallelization-first-orchestration.md" in out[0]["issue"]

    def test_valid_reason_clears(self):
        row = ptr(inline_reason="orchestrator_owned", inline_note="resolving a cross-engineer conflict")
        assert self.run([row], BIG) == []

    def test_invalid_reason_still_flagged(self):
        assert len(self.run([ptr(inline_reason="meh", inline_note="whatever long note")], BIG)) == 1

    def test_under_cutoff_clean(self):
        assert self.run([ptr()], SMALL) == []

    def test_unmeasurable_is_never_a_finding(self):
        assert self.run([ptr()], None) == []

    def test_before_shadow_start_ignored(self):
        assert self.run([ptr(ts="2026-11-06T23:59:00+00:00")], BIG) == []

    def test_replay_since_widens_window(self):
        assert len(self.run([ptr(ts="2026-10-20T00:00:00+00:00")], BIG, since="2026-10-08")) == 1

    def test_not_landed_ignored(self):
        assert self.run([ptr(status="on_going")], BIG) == []

    def test_dispatched_engineer_ignored(self):
        assert self.run([ptr(agent="backend-engineer")], BIG) == []

    def test_latest_row_per_branch_wins(self):
        rows = [ptr(ts="2026-11-08T10:00:00+00:00"),
                ptr(ts="2026-11-08T11:00:00+00:00", inline_reason="single_coherent_voice", inline_note="one voice for the doc")]
        assert self.run(rows, BIG) == []

    def test_real_numstat_runner_seam(self):
        calls = []

        def runner(args):
            calls.append(args)
            class P:  # minimal CompletedProcess stand-in
                returncode, stdout = 0, numstat((200, 0, "mcp/a.py"))
            return P()
        out = check_orchestrator_inline_over_cutoff(repo_root=Path("/x"), rows=[ptr()], runner=runner)
        assert len(out) == 1 and calls == [["diff", "--numstat", "abc1234", "def5678"]]

    def test_unresolved_ref_is_unmeasured(self):
        class P:
            returncode, stdout = 128, ""
        assert check_orchestrator_inline_over_cutoff(repo_root=Path("/x"), rows=[ptr()], runner=lambda a: P()) == []


# ---- construction: gate_delivery ----------------------------------------------------------------
class P:
    def __init__(self, text, rc=0):
        self.stdout, self.returncode = text, rc


class TestGateDelivery:
    def gate(self, pointer, reason=None, note=None, text=None, rc=0, record=None, log=None):
        text = text if text is not None else numstat((300, 0, "mcp/a.py"), (10, 0, "mcp/b.py"), (10, 0, "mcp/c.py"))
        return oic.gate_delivery("feat/x", pointer=pointer, inline_reason=reason, inline_note=note, root=Path("/x"),
                                 runner=lambda a: P(text, rc), record=record or (lambda *a: {"ok": True}),
                                 log=log or (lambda f: {"logged": [x["branch"] for x in f]}))

    def test_dispatched_engineer_not_applicable(self):
        assert self.gate(ptr(agent="backend-engineer")) == {"applicable": False}

    def test_no_pointer_not_applicable(self):
        assert self.gate(None) == {"applicable": False}

    def test_over_without_reason_warns_logs_and_does_not_refuse(self):
        logged = []
        out = self.gate(ptr(), log=lambda f: logged.extend(f) or {"logged": ["feat/x"]})
        assert out["over"] is True and "ok" not in out
        assert "tooling-engineer" in out["warnings"][0] and "inline_reason" in out["warnings"][0]
        assert logged and logged[0]["branch"] == "feat/x" and out["telemetry"] == {"logged": ["feat/x"]}

    def test_valid_reason_records_on_pointer(self):
        rec = []
        out = self.gate(ptr(), "single_coherent_voice", "methodology doc needing a single voice",
                        record=lambda b, r, n: rec.append((b, r, n)) or {"ok": True})
        assert rec == [("feat/x", "single_coherent_voice", "methodology doc needing a single voice")]
        assert out["recorded"] == {"ok": True} and "warnings" not in out

    def test_invalid_reason_warns_with_the_error_and_records_nothing(self):
        rec = []
        out = self.gate(ptr(), "lazy", "a note that is long enough", record=lambda *a: rec.append(a) or {})
        assert not rec and "inline_reason must be one of" in out["warnings"][0]

    def test_under_cutoff_is_quiet(self):
        out = self.gate(ptr(), text=numstat((5, 0, "mcp/a.py")))
        assert out["over"] is False and "warnings" not in out

    def test_unresolvable_refs_warn_unmeasured_not_over(self):
        out = self.gate(ptr(), rc=128)
        assert out["over"] is None and "unmeasured" in out["warnings"][0]


# ---- release_steward request wiring ------------------------------------------------------------
class TestStewardRequest:
    def store(self, tmp_path, gate):
        return rs.StewardStore(tmp_path, resolve_head=lambda b: "cafe123", inline_gate=gate)

    def test_request_surfaces_gate_warning_and_still_queues(self, tmp_path):
        seen = []

        def gate(branch, reason, note):
            seen.append((branch, reason, note))
            return {"applicable": True, "over": True, "loc": 400, "files": 9, "warnings": ["inline over the cutoff: dispatch X"]}
        out = self.store(tmp_path, gate).request("s1", "alpha", inline_reason="owner_directed", inline_note="owner asked for it")
        assert out["ok"] and out["status"] == "queued_for_steward"
        assert "inline over the cutoff" in out["warnings"][0]
        assert out["inline_cutoff"] == {"applicable": True, "over": True, "loc": 400, "files": 9}
        assert seen == [("feat/alpha", "owner_directed", "owner asked for it")]

    def test_not_applicable_adds_nothing(self, tmp_path):
        out = self.store(tmp_path, lambda b, r, n: {"applicable": False}).request("s1", "alpha")
        assert "inline_cutoff" not in out and "warnings" not in out

    def test_explicit_root_without_seam_skips_the_real_gate(self, tmp_path):
        out = rs.StewardStore(tmp_path, resolve_head=lambda b: "cafe123").request("s1", "alpha")
        assert out["ok"] and "inline_cutoff" not in out

    def test_run_action_passes_reason_through(self, tmp_path):
        seen = []
        s = self.store(tmp_path, lambda b, r, n: seen.append((r, n)) or {"applicable": False})
        rs.run_action("request", "s1", store=s, slug="alpha", inline_reason="shared_state", inline_note="cannot split state")
        assert seen == [("shared_state", "cannot split state")]
