"""``noctus.dev.council_ledger`` + the keeper ``check_council_ledger_schema``.

Contract: project-history/assistant-chatbot/contracts/council-ledger.md. Hermetic: ``tmp_path`` trees (no network, no patching of our own guards), real ``git`` in a tmp repo for append-only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "seed" / "lib" / "backend"))

from tools.noctus.dev import council_ledger as cl  # noqa: E402
from tools.noctus.dev.compliance import check_council_ledger_schema  # noqa: E402

SHA = "a" * 64
T0 = "2026-11-09T10:00:00Z"


def u() -> str:
    return str(uuid.uuid4())


def open_s(root, *, stage="build", project="p1", seats=("lens:a", "lens:b"), at=T0, **kw):
    out = cl.open_session(root, stage=stage, subject_kind="plan", subject_ref="ref", trigger="stage_map", mode="subagents",
                          seats=list(seats), brief_sha256=SHA, project=project, recorded_by="t", recorded_at=at,
                          **kw)
    assert out["ok"], out
    return out["session_id"]


def obj(root, sid, seat, label, tokens=None, claim="It breaks.", severity="major", at=T0):
    out = cl.record_objection(root, session_id=sid, seat=seat, severity=severity, claim=claim,
                              model="sonnet", tokens=tokens, recorded_by="t", recorded_at=at)
    assert out["ok"], out
    return out["objection_id"]


def outcome(root, sid, oid, o, at=T0):
    out = cl.record_event(root, session_id=sid, event_kind="outcome", objection_id=oid, outcome=o,
                          evidence_kind="test", recorded_by="t", recorded_at=at)
    assert out["ok"], out


def verdict(root, sid, disp, at=T0):
    out = cl.record_verdict(root, session_id=sid, chair_kind="chair_agent", decision="d", biggest_risk="r",
                            first_step="f", dispositions=[{"objection_id": o, "disposition": d, "reason": why}
                                                          for o, d, why in disp],
                            recorded_by="t", recorded_at=at)
    assert out["ok"], out


class TestValidation:
    def test_every_enum_is_enforced_with_a_precise_message(self, tmp_path):
        out = cl.open_session(tmp_path, stage="nope", subject_kind="plan", subject_ref="r", trigger="stage_map",
                              mode="subagents", seats=["lens:a"], brief_sha256=SHA, recorded_by="t")
        assert not out["ok"] and out["refused"] and "session.stage must be one of" in out["error"]
        assert not list((tmp_path / "project-history").rglob("*.ndjson")) if (tmp_path / "project-history").exists() else True

    def test_unknown_field_is_refused_not_dropped(self):
        row = {"record": "session", "recorded_by": "t", "recorded_at": T0, "session_id": u(), "stage": "build",
               "subject_kind": "plan", "subject_ref": "r", "trigger": "stage_map", "mode": "api", "seats": ["lens:a"],
               "brief_sha256": SHA, "project": None, "extra": 1}
        assert any("unknown field 'extra'" in e for e in cl.validate_row(row))

    def test_bad_seat_label_uuid_sha_tokens_and_timestamp(self, tmp_path):
        sid = open_s(tmp_path)
        for kw, frag in (({"seat": "alice"}, "objection.seat"),
                         ({"tokens": -1}, "tokens"), ({"claim": "One. Two. Three. Four."}, "at most 3 sentences"),
                         ({"severity": "huge"}, "severity")):
            args = {"session_id": sid, "seat": "lens:a", "severity": "major", "claim": "x",
                    "model": "m", **kw}
            out = cl.record_objection(tmp_path, recorded_by="t", **args)
            assert not out["ok"] and frag in out["error"], (kw, out)
        out = cl.record_objection(tmp_path, session_id="not-a-uuid", seat="lens:a", severity="major",
                                  claim="x", model="m", recorded_by="t")
        assert "UUIDv4" in out["error"]
        assert any("recorded_at" in e for e in cl.validate_row(
            {"record": "event", "recorded_by": "t", "recorded_at": "yesterday", "event_id": u(), "session_id": u(),
             "event_kind": "ratified"}))

    def test_outcome_event_requires_its_fields_and_others_forbid_them(self, tmp_path):
        sid = open_s(tmp_path)
        out = cl.record_event(tmp_path, session_id=sid, event_kind="outcome", recorded_by="t")
        assert "required when event_kind=outcome" in out["error"]
        out = cl.record_event(tmp_path, session_id=sid, event_kind="ratified", outcome="vindicated", recorded_by="t",
                              )
        assert "only allowed when event_kind=outcome" in out["error"]

    def test_references_must_resolve(self, tmp_path):
        sid = open_s(tmp_path)
        assert "unknown session" in cl.record_objection(
            tmp_path, session_id=u(), seat="lens:a", severity="note", claim="x", model="m",
            recorded_by="t")["error"]
        assert "not one of the session's seats" in cl.record_objection(
            tmp_path, session_id=sid, seat="lens:zzz", severity="note", claim="x", model="m",
            recorded_by="t")["error"]
        obj(tmp_path, sid, "lens:a", "A")
        assert "unknown objection" in cl.record_event(
            tmp_path, session_id=sid, event_kind="outcome", objection_id=u(), outcome="refuted", evidence_kind="test",
            recorded_by="t")["error"]
        assert "needs a verdict first" in cl.record_event(
            tmp_path, session_id=sid, event_kind="ratified", recorded_by="t")["error"]

    def test_verdict_needs_every_objection_disposed_and_only_one_verdict(self, tmp_path):
        sid = open_s(tmp_path)
        o1, o2 = obj(tmp_path, sid, "lens:a", "A"), obj(tmp_path, sid, "lens:b", "B")
        bad = cl.record_verdict(tmp_path, session_id=sid, chair_kind="tech_lead", decision="d", biggest_risk="r",
                                first_step="f", dispositions=[{"objection_id": o1, "disposition": "accepted", "reason": "x"}],
                                recorded_by="t")
        assert f"no disposition to objection {o2}" in bad["error"]
        verdict(tmp_path, sid, [(o1, "accepted", "x"), (o2, "rejected", "y")])
        again = cl.record_verdict(tmp_path, session_id=sid, chair_kind="tech_lead", decision="d", biggest_risk="r",
                                  first_step="f", dispositions=[{"objection_id": o1, "disposition": "accepted", "reason": "x"},
                                                                {"objection_id": o2, "disposition": "accepted", "reason": "x"}],
                                  recorded_by="t")
        assert "one verdict" in again["error"]
        late = cl.record_objection(tmp_path, session_id=sid, seat="lens:a", severity="note", claim="x",
                                   model="m", recorded_by="t")
        assert "after the verdict" in late["error"]

    def test_recorded_by_falls_back_to_env_or_is_required(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
        out = cl.open_session(tmp_path, stage="build", subject_kind="plan", subject_ref="r", trigger="stage_map",
                              mode="api", seats=["lens:a"], brief_sha256=SHA)
        assert not out["ok"] and "recorded_by is required" in out["error"]
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-1")
        out = cl.open_session(tmp_path, stage="build", subject_kind="plan", subject_ref="r", trigger="stage_map",
                              mode="api", seats=["lens:a"], brief_sha256=SHA)
        assert out["ok"]


class TestStorage:
    def test_one_file_per_session_under_the_month_directory_append_only(self, tmp_path):
        s1, s2 = open_s(tmp_path), open_s(tmp_path, at="2026-12-01T00:00:00Z")
        obj(tmp_path, s1, "lens:a", "A")
        f1 = cl.session_file(tmp_path, s1)
        assert f1 == tmp_path / "project-history/council/2026-11" / f"{s1}.ndjson"
        assert cl.session_file(tmp_path, s2) == tmp_path / "project-history/council/2026-12" / f"{s2}.ndjson"
        assert [r["record"] for r in cl.read_rows(f1)] == ["session", "objection"]
        assert cl.open_session(tmp_path, session_id=s1, stage="build", subject_kind="plan", subject_ref="r",
                               trigger="stage_map", mode="api", seats=["lens:a"], brief_sha256=SHA, recorded_by="t",
                               )["error"].startswith(f"session {s1} already exists")


class TestMetrics:
    """Hand-computed expected values (contract §3). One session, two seats, a re-resolved outcome."""

    def fixture(self, tmp_path):
        sid = open_s(tmp_path)
        o1 = obj(tmp_path, sid, "lens:a", "A", tokens=100)
        o2 = obj(tmp_path, sid, "lens:a", "B", tokens=50)
        o3 = obj(tmp_path, sid, "lens:a", "C", tokens=50)
        o4 = obj(tmp_path, sid, "lens:b", "D", tokens=None)
        o5 = obj(tmp_path, sid, "lens:b", "E", tokens=200)
        verdict(tmp_path, sid, [(o1, "accepted", "unique"), (o2, "rejected", "wrong"), (o3, "deferred", "later"),
                                (o4, "accepted", "shared with A"), (o5, "rejected", "n/a")])
        outcome(tmp_path, sid, o1, "refuted", at="2026-11-10T00:00:00Z")
        outcome(tmp_path, sid, o1, "vindicated", at="2026-11-11T00:00:00Z")  # latest wins -> vindicated
        outcome(tmp_path, sid, o2, "refuted", at="2026-11-10T00:00:00Z")
        outcome(tmp_path, sid, o3, "untested", at="2026-11-10T00:00:00Z")
        outcome(tmp_path, sid, o4, "vindicated", at="2026-11-10T00:00:00Z")
        return sid

    def test_per_seat_rates(self, tmp_path):
        self.fixture(tmp_path)
        seats = cl.report(tmp_path)["seats"]
        a, b = seats["lens:a"], seats["lens:b"]
        # a: 3 objections; latest outcomes vindicated(o1) refuted(o2) untested(o3)
        assert (a["objections"], a["vindicated"], a["refuted"], a["with_outcome"]) == (3, 1, 1, 3)
        assert a["hit_rate"] == 0.5                  # 1 / (1+1)
        assert a["unique_hit_rate"] == 1.0           # o1 vindicated + marked unique / 1 vindicated
        assert a["false_alarm_rate"] == 0.3333       # 1 refuted / 3 with an outcome (untested counts as an outcome)
        assert a["acceptance_rate"] == 0.3333        # 1 accepted / 3 dispositions
        assert a["cost_per_hit"] == 200.0            # (100+50+50) / 1 vindicated
        # b: o4 vindicated (tokens null = 0), o5 no outcome
        assert b["hit_rate"] == 1.0
        assert b["unique_hit_rate"] == 0.0           # 'shared with A' is not 'unique'
        assert b["false_alarm_rate"] == 0.0          # 0 / 1
        assert b["acceptance_rate"] == 0.5           # 1 / 2
        assert b["cost_per_hit"] == 200.0            # (0+200) / 1

    def test_rates_are_none_when_the_denominator_is_zero(self, tmp_path):
        sid = open_s(tmp_path)
        o = obj(tmp_path, sid, "lens:a", "A", tokens=5)
        verdict(tmp_path, sid, [(o, "deferred", "later")])
        a = cl.report(tmp_path)["seats"]["lens:a"]
        assert (a["hit_rate"], a["unique_hit_rate"], a["false_alarm_rate"], a["cost_per_hit"]) == (None,) * 4
        assert a["acceptance_rate"] == 0.0  # 0 accepted / 1 disposition

    def test_filters_stage_project_since(self, tmp_path):
        self.fixture(tmp_path)  # build / p1 / 2026-11-09
        s2 = open_s(tmp_path, stage="ship", project="p2", seats=("lens:a",), at="2026-11-20T00:00:00Z")
        o = obj(tmp_path, s2, "lens:a", "A", tokens=10, at="2026-11-20T00:00:00Z")
        verdict(tmp_path, s2, [(o, "accepted", "unique")], at="2026-11-20T00:00:00Z")
        outcome(tmp_path, s2, o, "vindicated", at="2026-11-21T00:00:00Z")
        assert cl.report(tmp_path, stage="ship")["seats"]["lens:a"]["objections"] == 1
        assert cl.report(tmp_path, stage="ship")["seats"]["lens:a"]["hit_rate"] == 1.0
        assert cl.report(tmp_path, project="p1")["sessions"] == 1
        assert cl.report(tmp_path, since="2026-11-15")["sessions"] == 1
        assert cl.report(tmp_path, since="2026-11-15")["filters"]["since"] == "2026-11-15"
        assert cl.report(tmp_path, stage="idealize")["seats"] == {}

    def bulk(self, tmp_path, seat, stage, vind, ref):
        sid = open_s(tmp_path, stage=stage, seats=(seat,))
        ids = []
        for n in range(vind + ref):
            o = obj(tmp_path, sid, seat, chr(65 + n % 26) + (chr(65 + n // 26) if n >= 26 else ""))
            outcome(tmp_path, sid, o, "vindicated" if n < vind else "refuted")
            ids.append(o)
        verdict(tmp_path, sid, [(o, "accepted", "x") for o in ids])

    def test_retune_signals(self, tmp_path):
        self.bulk(tmp_path, "lens:low", "build", 1, 9)       # 10 resolved, hit 0.1  -> demote
        self.bulk(tmp_path, "lens:high", "ship", 7, 3)       # 10 resolved, hit 0.7  -> promote
        self.bulk(tmp_path, "lens:mid", "build", 5, 5)       # 0.5 -> nothing
        self.bulk(tmp_path, "lens:few", "wire", 0, 9)        # 9 resolved -> below the floor
        props = {(p["seat"], p["stage"]): p for p in cl.report(tmp_path)["retune_proposals"]}
        assert set(props) == {("lens:low", "build"), ("lens:high", "ship")}
        assert props[("lens:low", "build")]["proposal"] == "demote M->O" and props[("lens:low", "build")]["hit_rate"] == 0.1
        assert props[("lens:high", "ship")]["proposal"] == "promote O->M"
        assert all(p["auto_apply"] is False and p["applies_if"] for p in props.values())
        # with the stage map the contract condition is exact: low is already O -> no demote; high is already M -> no promote
        rep = cl.report(tmp_path, stage_map={"build": {"lens:low": "O"}, "ship": {"lens:high": "M"}})
        assert rep["retune_proposals"] == []
        rep = cl.report(tmp_path, stage_map={"build": {"lens:low": "M"}, "ship": {"lens:high": "O"}})
        assert {p["proposal"] for p in rep["retune_proposals"]} == {"demote M->O", "promote O->M"}
        assert all(p["applies_if"] is None for p in rep["retune_proposals"])


class TestModeSplit:
    def mode_session(self, root, mode, seat, vind, ref):
        sid = cl.open_session(root, stage="build", subject_kind="plan", subject_ref="ref", trigger="stage_map",
                              mode=mode, seats=[seat], brief_sha256=SHA, project="p1", recorded_by="t",
                              recorded_at=T0)["session_id"]
        oids = [obj(root, sid, seat, str(i)) for i in range(10)]
        verdict(root, sid, [(o, "accepted", "x") for o in oids])
        for i, o in enumerate(oids):
            outcome(root, sid, o, "vindicated" if i < vind else "refuted")

    def test_split_independent_aggregate_and_retune_ignore_single_chat(self, tmp_path):
        self.mode_session(tmp_path, "subagents", "lens:a", 5, 0)
        self.mode_session(tmp_path, "single_chat", "lens:sc", 0, 0)   # would demote if it counted
        rep = cl.report(tmp_path)
        assert set(rep["by_mode"]) == {"subagents", "api", "single_chat"}
        assert rep["by_mode"]["single_chat"]["independent"] is False
        assert rep["by_mode"]["subagents"]["independent"] is True
        assert "lens:sc" in rep["by_mode"]["single_chat"]["seats"]
        assert set(rep["seats"]) == {"lens:a"} and rep["independent"] is True and rep["sessions"] == 1
        assert rep["retune_proposals"] == []  # single_chat's 0/10 never drives a demote
        assert "only subagents/api" in rep["note"]

    def test_mode_filter(self, tmp_path):
        self.mode_session(tmp_path, "subagents", "lens:a", 5, 0)
        self.mode_session(tmp_path, "single_chat", "lens:sc", 0, 0)
        sc = cl.report(tmp_path, mode="single_chat")
        assert sc["independent"] is False and set(sc["seats"]) == {"lens:sc"}
        assert sc["retune_proposals"] == [] and "not independent" in sc["note"]
        assert set(cl.report(tmp_path, mode="subagents")["seats"]) == {"lens:a"}
        assert cl.report(tmp_path, mode="bogus")["ok"] is False


class TestStatusAndDispatch:
    def test_status_reports_sessions_without_verdict_and_stale_objections(self, tmp_path):
        s = open_s(tmp_path)
        old = obj(tmp_path, s, "lens:a", "A", at="2026-10-01T00:00:00Z")
        fresh = obj(tmp_path, s, "lens:b", "B", at="2026-11-08T00:00:00Z")
        decided = obj(tmp_path, s, "lens:a", "C", at="2026-10-01T00:00:00Z")
        outcome(tmp_path, s, decided, "vindicated")
        st = cl.status(tmp_path, now=datetime(2026, 11, 9, tzinfo=timezone.utc))
        assert st["sessions_without_verdict"] == [s]
        assert all("seat" not in x for x in st["objections_without_outcome"])  # hidden pre-verdict
        assert [x["objection_id"] for x in st["objections_without_outcome"]] == [old]
        assert fresh not in [x["objection_id"] for x in st["objections_without_outcome"]]

    def test_run_dispatch_validates_arguments_and_action(self, tmp_path):
        assert "missing required" in cl.run("open_session", root=tmp_path, stage="build")["error"]
        assert "action must be one of" in cl.run("nope", root=tmp_path)["error"]
        out = cl.run("open_session", root=tmp_path, stage="build", subject_kind="plan", subject_ref="r",
                     trigger="stage_map", mode="api", seats=["lens:a"], brief_sha256=SHA, recorded_by="t")
        assert out["ok"] and cl.run("status", root=tmp_path)["sessions"] == 1


class TestCouncilLedgerSchema:
    """Keeper ``check_council_ledger_schema``: red + green fixtures, then append-only on a real git index."""

    def test_green_ledger_is_clean(self, tmp_path):
        s = open_s(tmp_path)
        o = obj(tmp_path, s, "lens:a", "A")
        verdict(tmp_path, s, [(o, "accepted", "x")])
        assert check_council_ledger_schema(tmp_path) == []

    def test_red_bad_enum_hand_edited_row(self, tmp_path):
        s = open_s(tmp_path)
        f = cl.session_file(tmp_path, s)
        row = json.loads(f.read_text().splitlines()[0])
        row["stage"] = "whenever"
        f.write_text(json.dumps(row) + "\n")
        issues = check_council_ledger_schema(tmp_path)
        assert issues and "session.stage must be one of" in issues[0]["issue"]

    def test_red_file_name_and_month_must_match_the_session(self, tmp_path):
        s = open_s(tmp_path)
        f = cl.session_file(tmp_path, s)
        moved = tmp_path / "project-history/council/2025-01" / f.name
        moved.parent.mkdir(parents=True)
        f.rename(moved)
        assert any("lives in 2025-01/" in i["issue"] for i in check_council_ledger_schema(tmp_path))
        other = moved.with_name(f"{u()}.ndjson")
        moved.rename(other)
        assert any("does not match its session_id" in i["issue"] for i in check_council_ledger_schema(tmp_path))

    def test_paths_scopes_and_ignores_non_ledger_files(self, tmp_path):
        s = open_s(tmp_path)
        f = cl.session_file(tmp_path, s)
        f.write_text("not json\n")
        assert check_council_ledger_schema(tmp_path, ["README.md"]) == []
        assert check_council_ledger_schema(tmp_path, [str(f.relative_to(tmp_path))])

    def test_append_only_pure_rules(self):
        rel = "project-history/council/2026-11/x.ndjson"
        assert cl.append_only_violations(rel, "A", "", 0) == []
        assert cl.append_only_violations(rel, "D", "", 3)
        assert cl.append_only_violations(rel, "M", "@@ -3,0 +4,1 @@\n+row\n", 3) == []
        assert cl.append_only_violations(rel, "M", "@@ -1,0 +2,1 @@\n+row\n", 3)  # inserted mid-file
        assert cl.append_only_violations(rel, "M", "@@ -2 +2 @@\n-old\n+new\n", 3)  # edited line

    def _git(self, root, *a):
        subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True,
                       capture_output=True)

    def test_append_only_on_a_real_index(self, tmp_path):
        self._git(tmp_path, "init", "-q")
        s = open_s(tmp_path)
        f = cl.session_file(tmp_path, s)
        rel = str(f.relative_to(tmp_path))
        self._git(tmp_path, "add", "-A")
        assert check_council_ledger_schema(tmp_path, [rel], staged=True) == []  # new file
        self._git(tmp_path, "commit", "-qm", "ledger")
        obj(tmp_path, s, "lens:a", "A")  # pure append
        self._git(tmp_path, "add", "-A")
        assert check_council_ledger_schema(tmp_path, [rel], staged=True) == []
        self._git(tmp_path, "commit", "-qm", "append")
        rows = f.read_text().splitlines()
        rows[0] = rows[0].replace('"project": "p1"', '"project": "p9"')  # rewrite a committed line (still valid JSON)
        f.write_text("\n".join(rows) + "\n")
        self._git(tmp_path, "add", "-A")
        assert any("append-only" in i["issue"] or "modified or deleted" in i["issue"]
                   for i in check_council_ledger_schema(tmp_path, [rel], staged=True))
        self._git(tmp_path, "reset", "-q", "--hard")
        f.unlink()
        self._git(tmp_path, "add", "-A")
        assert any("staged status D" in i["issue"] for i in check_council_ledger_schema(tmp_path, [rel], staged=True))


@pytest.mark.parametrize("name,expect", [("stage", 14), ("subject_kind", 9), ("trigger", 9), ("mode", 3), ("severity", 4),
                                         ("chair_kind", 3), ("disposition", 3), ("event_kind", 3), ("outcome", 3),
                                         ("evidence_kind", 7)])
def test_enums_match_contract_section_2(name, expect):
    assert len(cl.ENUMS[name]) == expect


class TestNeutralRecorder:
    """Owner decision 2026-11-09: the tool is the neutral recorder; blindness is construction, not discipline."""

    def test_label_assigned_by_tool_unique_and_not_in_the_result(self, tmp_path):
        sid = open_s(tmp_path, seats=("lens:a", "lens:b"))
        outs = [cl.record_objection(tmp_path, session_id=sid, seat=st, severity="major", claim="x", model="m",
                                    recorded_by="t") for st in ("lens:a", "lens:b") * 15]
        assert all(set(o) == {"ok", "objection_id", "status"} and o["status"] == "submitted" for o in outs)
        labels = [r["anon_label"] for r in cl.read_rows(cl.session_file(tmp_path, sid)) if r["record"] == "objection"]
        assert len(labels) == 30 and len(set(labels)) == 30
        assert all(cl._LABEL_RE.match(x) for x in labels)

    def test_caller_label_is_refused(self, tmp_path):
        sid = open_s(tmp_path)
        out = cl.run("record_objection", root=tmp_path, session_id=sid, seat="lens:a", anon_label="A",
                     severity="major", claim="x", model="m", recorded_by="t")
        assert not out["ok"] and "assigned by the tool" in out["error"]
        with pytest.raises(TypeError):
            cl.record_objection(tmp_path, session_id=sid, seat="lens:a", anon_label="A", severity="major", claim="x",
                                model="m", recorded_by="t")

    def test_blind_view_has_no_seat_or_model(self, tmp_path):
        sid = open_s(tmp_path)
        obj(tmp_path, sid, "lens:a", None, claim="One.")
        obj(tmp_path, sid, "lens:b", None, claim="Two.")
        view = cl.run("blind_view", root=tmp_path, session_id=sid)
        assert view["ok"] and len(view["objections"]) == 2
        for o in view["objections"]:
            assert set(o) == {"anon_label", "severity", "claim"}
        text = json.dumps(view)
        assert "lens:" not in text and "sonnet" not in text

    def test_seat_hidden_pre_verdict_visible_post_verdict(self, tmp_path):
        sid = open_s(tmp_path)
        o = obj(tmp_path, sid, "lens:a", None, at="2026-10-01T00:00:00Z")
        pre = cl.status(tmp_path, now=datetime(2026, 11, 9, tzinfo=timezone.utc))
        assert "lens:a" not in json.dumps(pre)
        assert "hidden until the verdict" in cl.run("full_view", root=tmp_path, session_id=sid)["error"]
        assert cl.report(tmp_path)["seats"] == {} and cl.report(tmp_path)["sessions"] == 0
        verdict(tmp_path, sid, [(o, "accepted", "x")])
        post = cl.status(tmp_path, now=datetime(2026, 11, 9, tzinfo=timezone.utc))
        assert post["objections_without_outcome"][0]["seat"] == "lens:a"
        assert any(r.get("seat") == "lens:a" for r in cl.run("full_view", root=tmp_path, session_id=sid)["rows"])
        assert "lens:a" in cl.report(tmp_path)["seats"]

    def test_dispositions_by_label_are_translated(self, tmp_path):
        sid = open_s(tmp_path)
        o1, o2 = obj(tmp_path, sid, "lens:a", None), obj(tmp_path, sid, "lens:b", None)
        view = cl.blind_view(tmp_path, sid)["objections"]
        disp = [{"anon_label": v["anon_label"], "disposition": "accepted", "reason": "ok"} for v in view]
        out = cl.record_verdict(tmp_path, session_id=sid, chair_kind="chair_agent", decision="d", biggest_risk="r",
                                first_step="f", dispositions=disp, recorded_by="t")
        assert out["ok"], out
        v = next(r for r in cl.read_rows(cl.session_file(tmp_path, sid)) if r["record"] == "verdict")
        assert {d["objection_id"] for d in v["dispositions"]} == {o1, o2}
        bad = cl.record_verdict(tmp_path, session_id=open_s(tmp_path), chair_kind="chair_agent", decision="d",
                                biggest_risk="r", first_step="f", recorded_by="t",
                                dispositions=[{"anon_label": "Z", "disposition": "accepted", "reason": "x"}])
        assert "unknown anon_label" in bad["error"]


def _objector(args):
    root, sid, i = args
    return cl.record_objection(Path(root), session_id=sid, seat="lens:a", severity="minor", claim=f"c{i}.",
                               model="m", recorded_by="t", recorded_at=T0)


def test_concurrent_seats_get_unique_labels_and_no_refusal(tmp_path):
    """Live bug: parallel seats read the same used-label set, both got 'S', and validation then refused every later write."""
    import multiprocessing as mp
    sid = open_s(tmp_path)
    n = 24
    with mp.get_context("fork").Pool(8) as pool:
        res = pool.map(_objector, [(str(tmp_path), sid, i) for i in range(n)])
    assert all(r.get("ok") for r in res), [r for r in res if not r.get("ok")]
    labels = [r["anon_label"] for r in cl.read_rows(cl.session_file(tmp_path, sid)) if r["record"] == "objection"]
    assert len(labels) == n and len(set(labels)) == n
    assert cl.run("record_objection", root=tmp_path, session_id=sid, seat="lens:b", severity="note", claim="after.",
                  model="m", recorded_by="t")["ok"]


class TestProductField:
    """Council must-fix Q (contract v1.3): optional `product` slug, filterable in report."""

    def _open(self, root, product, **kw):
        return cl.run("open_session", root=root, stage="build", subject_kind="plan", subject_ref="x", trigger="stage_map",
                      mode="subagents", seats=["lens:a"], brief_sha256=SHA, product=product, **{"recorded_by": "t", **kw})

    def test_product_stored(self, tmp_path):
        r = self._open(tmp_path, "social-wiring")
        assert r["ok"]
        assert cl.read_rows(cl.session_file(tmp_path, r["session_id"]))[0]["product"] == "social-wiring"

    @pytest.mark.parametrize("bad", ["Social Wiring", "", "-x", "a/b"])
    def test_bad_product_refused(self, tmp_path, bad):
        r = self._open(tmp_path, bad)
        assert r["ok"] is False and "product" in r["error"]

    def test_old_rows_without_product_stay_valid(self, tmp_path):
        s = open_s(tmp_path)
        assert cl.read_rows(cl.session_file(tmp_path, s))[0].get("product") is None

    def test_report_filters_by_product(self, tmp_path):
        for prod in ("p-a", "p-b"):
            r = self._open(tmp_path, prod, recorded_by="t", recorded_at=T0)
            cl.run("record_verdict", root=tmp_path, session_id=r["session_id"], chair_kind="tech_lead", decision="d",
                   biggest_risk="r", first_step="f", dispositions=[], recorded_by="t", recorded_at=T0)
        assert cl.report(tmp_path)["sessions"] == 2
        rep = cl.report(tmp_path, product="p-a")
        assert rep["sessions"] == 1 and rep["filters"]["product"] == "p-a"
