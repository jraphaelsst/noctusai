"""``noctus.dev.decision_log`` + keeper ``check_decision_log_schema``.

Contract: project-history/assistant-chatbot/contracts/decision-log.md. Hermetic: ``tmp_path`` trees; the audit runs on a
REAL tmp git repo (base commit + a slice branch) so the diff plumbing is exercised, not faked.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "seed" / "lib" / "backend"))

from tools.noctus.dev import decision_log as dl  # noqa: E402
from tools.noctus.dev.compliance import check_decision_log_schema  # noqa: E402

SLICE = "s1"
TS = "2026-11-09T10:00:00Z"


def rec(root: Path, **over):
    kw = dict(slice_id=SLICE, agent="product-engineer", branch="feat/s1", tier="autonomous", cls="typo",
              criteria_hit=[], reversibility="one_commit", blast_radius="slice_paths", surprise_test="all_no",
              paths=["products/p/a.py"], decision="We will fix the typo in the error text.", ts=TS)
    kw.update(over)
    return dl.record(root, **kw)


def fp(root: Path, slice_id: str = SLICE) -> Path:
    return root / "project-history/decisions/2026-11" / f"{slice_id}.ndjson"


# ── tier floor ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("over,floor", [
    (dict(criteria_hit=["C4"]), "escalate"), (dict(criteria_hit=["C7"]), "escalate"),
    (dict(criteria_hit=["C8"]), "escalate"), (dict(criteria_hit=["C9"]), "escalate"),
    (dict(criteria_hit=["C1"]), "notify"), (dict(criteria_hit=["C6"]), "notify"),
    (dict(reversibility="shared_code"), "notify"), (dict(reversibility="needs_migration"), "escalate"),
    (dict(blast_radius="same_product"), "notify"), (dict(blast_radius="cross_product"), "escalate"),
    (dict(cls="other"), "notify"), (dict(surprise_test="escalated_by_test"), "notify"),
    (dict(surprise_test="escalated_by_test", reversibility="shared_code"), "escalate"),
])
def test_tier_below_floor_is_refused(tmp_path, over, floor):
    r = rec(tmp_path, **over)  # tier=autonomous by default
    assert not r["ok"] and r["refused"] and "below the floor" in r["error"] and floor in r["error"]
    assert not fp(tmp_path).exists()


def test_tier_at_or_above_floor_is_written(tmp_path):
    assert rec(tmp_path, tier="notify", reversibility="shared_code")["ok"]
    assert rec(tmp_path, tier="escalate", reversibility="shared_code")["ok"]  # one tier up is allowed


def test_class_other_is_never_autonomous(tmp_path):
    r = rec(tmp_path, cls="other")
    assert not r["ok"] and "never autonomous" in r["error"]
    assert rec(tmp_path, cls="other", tier="notify")["ok"]


def test_ids_are_sequential_and_trailer_returned(tmp_path):
    a, b = rec(tmp_path), rec(tmp_path, paths=["products/p/b.py"])
    assert (a["id"], b["id"]) == ("D-s1-001", "D-s1-002") and b["trailer"] == "Decisions: D-s1-002"
    assert dl.validate_file_rows(dl.read_rows(fp(tmp_path)), file_slice=SLICE, file_month="2026-11") == []


@pytest.mark.parametrize("over,frag", [
    (dict(decision="Fix it."), "We will"), (dict(decision="We will " + "x" * 200), "1..200"),
    (dict(paths=[]), "paths"), (dict(paths=["/abs"]), "paths"), (dict(paths=["../x"]), "paths"),
    (dict(criteria_hit=["C10"]), "criteria_hit"), (dict(cls="nope"), "class"), (dict(commit_sha="zz"), "commit_sha"),
    (dict(slice_id="Bad Slice"), "slice_id"),
])
def test_field_validation(tmp_path, over, frag):
    r = rec(tmp_path, **over)
    assert not r["ok"] and frag in r["error"]


# ── caps / 3-in-a-row ────────────────────────────────────────────────────────

def test_sixth_autonomous_requires_checkin_and_writes_nothing(tmp_path):
    for i in range(5):
        assert rec(tmp_path, cls=dl.CLASSES[i], paths=[f"products/p/f{i}.py"])["ok"]
    before = fp(tmp_path).read_text()
    r = rec(tmp_path, cls="typo", paths=["products/p/new.py"])
    assert r["status"] == "checkin_required" and r["cap"] == 5 and not r["ok"]
    assert fp(tmp_path).read_text() == before


def test_fourth_notify_requires_checkin_but_escalate_is_uncapped(tmp_path):
    for i in range(3):
        assert rec(tmp_path, tier="notify", reversibility="shared_code", paths=[f"products/p/f{i}.py"])["ok"]
    assert rec(tmp_path, tier="notify", reversibility="shared_code")["status"] == "checkin_required"
    assert rec(tmp_path, tier="escalate", reversibility="needs_migration")["ok"]


def test_third_same_class_same_file_cannot_be_autonomous(tmp_path):
    assert rec(tmp_path, cls="edge_case")["ok"] and rec(tmp_path, cls="edge_case")["ok"]
    r = rec(tmp_path, cls="edge_case")
    assert r["status"] == "reclassify_required" and "tier=notify" in r["error"] and len(r["same_class_file"]) == 2
    up = rec(tmp_path, cls="edge_case", tier="notify", reversibility="shared_code", supersedes="D-s1-001")
    assert up["ok"]
    assert rec(tmp_path, cls="typo", paths=["products/p/other.py"])["ok"]  # other class/file unaffected


def test_superseded_rows_do_not_count_toward_caps(tmp_path):
    for i in range(5):
        rec(tmp_path, cls=dl.CLASSES[i], paths=[f"products/p/f{i}.py"])
    assert dl.review(tmp_path, id_ref="D-s1-001", outcome="reclassified", reviewer_kind="compliance_reviewer",
                     reviewer="cr", ts=TS)["ok"]
    assert rec(tmp_path, cls="typo", paths=["products/p/z.py"])["ok"]


# ── review / list ────────────────────────────────────────────────────────────

def test_review_and_list_filters(tmp_path):
    rec(tmp_path)
    rec(tmp_path, tier="notify", reversibility="shared_code", cls="null_handling", paths=["products/p/b.py"])
    assert dl.review(tmp_path, id_ref="D-s1-002", outcome="vetoed", reviewer_kind="compliance_reviewer",
                     reviewer="cr", note="no", ts=TS)["ok"]
    assert not dl.review(tmp_path, id_ref="D-s1-009", outcome="accepted", reviewer_kind="owner", reviewer="o")["ok"]
    assert not dl.review(tmp_path, id_ref="D-s1-001", outcome="maybe", reviewer_kind="owner", reviewer="o")["ok"]
    assert dl.list_decisions(tmp_path)["count"] == 2
    assert dl.list_decisions(tmp_path, outcome="vetoed")["decisions"][0]["id"] == "D-s1-002"
    assert dl.list_decisions(tmp_path, outcome="pending_review")["decisions"][0]["id"] == "D-s1-001"
    assert dl.list_decisions(tmp_path, tier="notify", cls="null_handling")["count"] == 1
    assert dl.list_decisions(tmp_path, slice_id="zzz")["count"] == 0


# ── audit (real git) ─────────────────────────────────────────────────────────

def git(root: Path, *a: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True,
                   capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "README.md").write_text("x\n")
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"react": "1"}}))
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    git(tmp_path, "checkout", "-q", "-b", "feat/s1")
    return tmp_path


def commit(root: Path, files: dict[str, str], msg: str = "work") -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    git(root, "add", "-A")
    git(root, "commit", "-qm", msg)


def checks(res: dict, sev: str | None = None) -> set[str]:
    return {f["check"] for f in res["findings"] if sev is None or f["severity"] == sev}


def aud(repo: Path, paths=("products/p",)) -> dict:
    return dl.audit(repo, slice_id=SLICE, base="main", slice_paths=list(paths))


def test_audit_clear_when_every_file_is_covered(repo):
    rec(repo, paths=["products/p/a.py"])
    commit(repo, {"products/p/a.py": "x = 1\n"})
    r = aud(repo)
    assert r["ok"] and r["status"] == "clear" and not checks(r, "block")


def test_audit_unknown_base_is_inconclusive_never_clear(repo):
    r = dl.audit(repo, slice_id=SLICE, base="nope")
    assert not r["ok"] and r["status"] == "inconclusive"


def test_audit_gated_surface_needs_owner_accepted_escalate_row(repo):
    rec(repo, tier="escalate", reversibility="needs_migration", paths=["products/p/backend/migrations/001_x.sql"])
    commit(repo, {"products/p/backend/migrations/001_x.sql": "create table t(i int);\n"})
    assert "gated_surface" in checks(aud(repo), "block")
    dl.review(repo, id_ref="D-s1-001", outcome="accepted", reviewer_kind="tech_lead", reviewer="tl", ts=TS)
    assert "gated_surface" in checks(aud(repo), "block")
    dl.review(repo, id_ref="D-s1-001", outcome="accepted", reviewer_kind="owner", reviewer="o", ts=TS)
    assert "gated_surface" not in checks(aud(repo))


def test_audit_rls_in_a_non_migration_file_is_gated(repo):
    rec(repo, paths=["products/p/a.sql"])
    commit(repo, {"products/p/a.sql": "alter table t enable row level security;\n"})
    assert "gated_surface" in checks(aud(repo), "block")


def test_audit_new_route_under_autonomous_row_blocks(repo):
    rec(repo, paths=["products/p/backend/app/routers/x.py"])
    commit(repo, {"products/p/backend/app/routers/x.py": "@router.get('/x')\ndef x():\n    return 1\n"})
    assert "autonomous_surface" in checks(aud(repo), "block")


def test_audit_new_page_and_customer_text_under_autonomous(repo):
    rec(repo, paths=["products/p/frontend/src/pages/New.tsx"])
    commit(repo, {"products/p/frontend/src/pages/New.tsx": "export default () => <h1>Bem-vindo ao painel</h1>\n"})
    assert "autonomous_surface" in checks(aud(repo), "block")


def test_audit_customer_text_change_is_a_warning(repo):
    commit(repo, {"products/p/frontend/src/Old.tsx": "<p>antigo</p>\n"}, "base2\n\nAC: AC-1")
    git(repo, "branch", "-f", "main", "HEAD")
    rec(repo, paths=["products/p/frontend/src/Old.tsx"], decision="We will keep the label.")
    commit(repo, {"products/p/frontend/src/Old.tsx": "<p>texto novo para clientes</p>\n"})
    r = aud(repo)
    assert any(f["check"] == "autonomous_surface" and f["severity"] == "warn" for f in r["findings"])


def test_audit_paths_outside_slice_when_row_claims_slice_paths(repo):
    rec(repo, paths=["products/p/a.py"])
    commit(repo, {"products/p/a.py": "1\n", "products/q/b.py": "2\n"}, "AC: AC-1")
    r = aud(repo)
    assert any(f["check"] == "slice_paths" and f.get("file") == "products/q/b.py" for f in r["findings"])
    r2 = dl.audit(repo, slice_id=SLICE, base="main")  # unmeasured is reported, never silently green
    assert any(f["check"] == "slice_paths" and f["severity"] == "warn" and "NOT measured" in f["message"]
               for f in r2["findings"])


def test_audit_new_runtime_dep_needs_notify(repo):
    rec(repo, paths=["package.json"])
    commit(repo, {"package.json": json.dumps({"dependencies": {"react": "1", "lodash": "4"}})}, "AC: AC-1")
    assert "runtime_dep" in checks(aud(repo, ["package.json"]), "block")
    rec(repo, paths=["package.json"], tier="escalate", criteria_hit=["C8"], decision="We will add lodash.")
    assert "runtime_dep" not in checks(aud(repo, ["package.json"]))


def test_audit_dev_dependency_is_not_a_runtime_dep(repo):
    rec(repo, paths=["package.json"])
    commit(repo, {"package.json": json.dumps({"dependencies": {"react": "1"}, "devDependencies": {"vitest": "1"}})})
    assert "runtime_dep" not in checks(aud(repo, ["package.json"]))


def test_audit_file_with_no_row_and_no_ac_trailer(repo):
    rec(repo, paths=["products/p/a.py"])
    commit(repo, {"products/p/a.py": "1\n", "products/p/loose.py": "2\n"})
    r = aud(repo)
    assert [f["file"] for f in r["findings"] if f["check"] == "unjustified_file"] == ["products/p/loose.py"]
    commit(repo, {"products/p/loose.py": "3\n"}, "tweak\n\nAC: AC-3")
    assert "unjustified_file" not in checks(aud(repo))


def test_audit_decisions_trailer_must_name_a_real_row(repo):
    rec(repo, paths=["products/p/a.py"])
    commit(repo, {"products/p/a.py": "1\n"}, "x\n\nDecisions: D-s1-001, D-s1-009")
    r = aud(repo)
    assert [f["message"] for f in r["findings"] if f["check"] == "trailer"][0].count("D-s1-009") == 1


def test_audit_one_commit_row_with_a_migration_blocks(repo):
    rec(repo, paths=["products/p/a.py"])
    rec(repo, tier="escalate", reversibility="needs_migration", paths=["products/p/backend/migrations/001_x.sql"])
    commit(repo, {"products/p/a.py": "1\n", "products/p/backend/migrations/001_x.sql": "select 1;\n"})
    r = aud(repo)
    assert [f["row"] for f in r["findings"] if f["check"] == "one_commit_migration"] == ["D-s1-001"]


def test_audit_caps_exceeded_when_rows_were_written_around_the_tool(repo):
    for i in range(5):
        rec(repo, cls=dl.CLASSES[i], paths=[f"products/p/f{i}.py"])
    p = fp(repo)
    rows = dl.read_rows(p)
    extra = {**rows[0], "id": "D-s1-006", "class": "typo", "paths": ["products/p/g.py"]}
    p.write_text(p.read_text() + json.dumps(extra) + "\n")
    commit(repo, {"products/p/f0.py": "1\n"})
    assert "caps" in checks(aud(repo), "block")


def test_sample_selection_is_deterministic_and_one_in_five_plus_every_other(tmp_path):
    for i in range(5):
        rec(tmp_path, slice_id="big", cls=dl.CLASSES[i], paths=[f"p/f{i}.py"])
    rec(tmp_path, slice_id="big", cls="other", tier="notify", paths=["p/o.py"])
    rows = dl.read_rows(fp(tmp_path, "big"))
    a, b = dl.select_recheck(rows, "seed-1"), dl.select_recheck(rows, "seed-1")
    assert a == b and len(a["sample"]) == 1 and a["autonomous_total"] == 5  # ceil(5/5)
    assert a["class_other"] == ["D-big-006"]
    assert len({dl.select_recheck(rows, f"s{i}")["sample"][0] for i in range(30)}) > 1  # the seed matters
    assert dl.select_recheck([], "x")["sample"] == []


# ── report ───────────────────────────────────────────────────────────────────

def test_report_proposes_demote_then_repromote(tmp_path):
    for i in range(3):
        rec(tmp_path, slice_id=f"a{i}", cls="typo")
    dl.review(tmp_path, id_ref="D-a0-001", outcome="vetoed", reviewer_kind="compliance_reviewer", reviewer="c", ts=TS)
    rep = dl.report(tmp_path)
    typo = next(c for c in rep["classes"] if c["class"] == "typo")
    assert typo["uses"] == 3 and typo["vetoed"] == 1 and typo["status"] == "demoted"
    assert rep["proposals"][0]["proposal"] == "demote" and "owner ratifies" in rep["note"]
    for i in range(10):
        rec(tmp_path, slice_id=f"b{i}", cls="typo", ts="2026-11-10T10:00:00Z")
    rep2 = dl.report(tmp_path)
    assert rep2["proposals"][0]["proposal"] == "promote"
    assert next(c for c in rep2["classes"] if c["class"] == "typo")["clean_since_last_bad"] >= 10


# ── keeper ───────────────────────────────────────────────────────────────────

class TestCheckDecisionLogSchema:
    def test_green_on_tool_written_ledger_and_red_on_hand_edits(self, tmp_path):
        rec(tmp_path)
        rec(tmp_path, paths=["products/p/b.py"])
        assert check_decision_log_schema(tmp_path) == []
        p = fp(tmp_path)
        rows = dl.read_rows(p)
        rows[1]["reversibility"] = "needs_migration"  # below the floor its own fields imply
        p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        assert "below the floor" in " ".join(i["issue"] for i in check_decision_log_schema(tmp_path))
        rows[1]["reversibility"] = "one_commit"
        rows[1]["id"] = "D-s1-007"  # gap in the sequence
        p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        assert "must be D-s1-002" in " ".join(i["issue"] for i in check_decision_log_schema(tmp_path))


    def test_append_only_against_the_index(self, tmp_path):
        git(tmp_path, "init", "-q", "-b", "main")
        rec(tmp_path)
        git(tmp_path, "add", "-A")
        git(tmp_path, "commit", "-qm", "first")
        rec(tmp_path, paths=["products/p/b.py"])
        git(tmp_path, "add", "-A")
        rel = "project-history/decisions/2026-11/s1.ndjson"
        assert check_decision_log_schema(tmp_path, [rel], staged=True) == []  # appended at EOF
        p = fp(tmp_path)
        lines = p.read_text().splitlines()
        lines[0] = lines[0].replace("typo in", "typo within")
        p.write_text("\n".join(lines) + "\n")
        git(tmp_path, "add", "-A")
        assert any("modified or deleted" in i["issue"] for i in check_decision_log_schema(tmp_path, [rel], staged=True))


def test_run_dispatch_and_unknown_action(tmp_path):
    out = dl.run("record", root=tmp_path, slice_id=SLICE, agent="a", branch="b", tier="autonomous",
                 decision_class="typo", criteria_hit=[], reversibility="one_commit", blast_radius="slice_paths",
                 surprise_test="all_no", paths=["x.py"], decision="We will fix.", ts=TS)
    assert out["ok"] and dl.run("list", root=tmp_path)["count"] == 1
    assert "missing required" in dl.run("record", root=tmp_path, slice_id=SLICE)["error"]
    assert "action must be one of" in dl.run("nope", root=tmp_path)["error"]
