"""Absorption SOURCES are frozen (Phase 5a): registry derivation (F1), write guard (F2), commit keeper (F3),
pilot-is-canon keeper + reference lint (F4), gate-fire telemetry (F6). Red-first: every gate has a planted-violation
fixture that must refuse and a green twin that must pass."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import absorption_sources as abs_src  # noqa: E402
from tools.noctus.dev import absorption_tracking as ab  # noqa: E402
from tools.noctus.dev.compliance import (  # noqa: E402
    check_absorption_pilot_is_canon,
    check_absorption_source_frozen,
)
from tools.noctus.dev.engineer_brief_compose import compose_brief  # noqa: E402
from tools.noctus.dev.engineer_output_linter import lint_return  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCES = {"erp-imobiliario": "social-wiring", "igig": "orbity", "therapy-platform": "monica", "community": "monica"}


def _row(slug, stage, ts, canon=None, **extra):
    r = {"ts": ts, "slug": slug, "kind": "lifecycle", "stage": stage, "note": ""}
    if canon:
        r.update(canon=canon, absorption_source=True)
    r.update(extra)
    return json.dumps(r)


def _ledger(*rows):
    return "\n".join(rows) + "\n"


REGISTRY = _ledger(*[_row(s, "absorb_only", "2026-11-12T10:00:00+00:00", c) for s, c in SOURCES.items()])


# ───────────────────────────── F1: derived registry ─────────────────────────────
class TestDerive:
    def test_lists_exactly_the_registered_sources(self):
        assert abs_src.derive_sources(REGISTRY) == SOURCES

    def test_done_row_erases_a_source(self):
        text = REGISTRY + _row("igig", "done", "2026-12-01T00:00:00+00:00")
        assert "igig" not in abs_src.derive_sources(text)

    def test_other_ladder_stage_never_unfreezes(self):
        text = REGISTRY + _row("igig", "diagnosed", "2026-12-01T00:00:00+00:00")
        assert abs_src.derive_sources(text)["igig"] == "orbity"

    def test_order_is_by_ts_not_file_order(self):
        text = _ledger(_row("igig", "done", "2026-12-01T00:00:00+00:00"), _row("igig", "absorb_only", "2026-11-12T00:00:00+00:00", "orbity"))
        assert abs_src.derive_sources(text) == {}

    def test_garbage_lines_are_skipped(self):
        assert abs_src.derive_sources("not json\n" + REGISTRY) == SOURCES


class TestLogEntry:
    @pytest.fixture
    def env(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ab, "LEDGER_PATH", tmp_path / "project-history" / "absorptions.ndjson")
        monkeypatch.setattr(ab, "CACHE_PATH", tmp_path / "cache" / "absorptions.sqlite")
        monkeypatch.setattr(ab, "CACHE_DIR", tmp_path / "cache")

    def test_absorb_only_requires_canon(self, env):
        assert ab.log_entry(slug="igig", kind="lifecycle", stage="absorb_only")["ok"] is False

    def test_canon_only_valid_with_absorb_only(self, env):
        assert ab.log_entry(slug="igig", kind="lifecycle", stage="cloned", canon="orbity")["ok"] is False

    def test_canon_cannot_be_a_source(self, env):
        assert ab.log_entry(slug="igig", kind="lifecycle", stage="absorb_only", canon="orbity")["ok"]
        r = ab.log_entry(slug="community", kind="lifecycle", stage="absorb_only", canon="igig")
        assert r["ok"] is False and "never a source" in r["error"]

    def test_status_stage_absorb_only_lists_the_registry_and_survives_a_later_stage(self, env):
        for s, c in SOURCES.items():
            assert ab.log_entry(slug=s, kind="lifecycle", stage="absorb_only", canon=c)["ok"]
        ab.log_entry(slug="igig", kind="lifecycle", stage="diagnosed")
        got = ab.status(stage="absorb_only")["absorptions"]
        assert {a["slug"]: a["canon"] for a in got} == SOURCES
        ab.log_entry(slug="igig", kind="lifecycle", stage="done")
        assert "igig" not in {a["slug"] for a in ab.status(stage="absorb_only")["absorptions"]}


# ───────────────────────────── pure path / branch rules ─────────────────────────────
class TestRules:
    @pytest.mark.parametrize("branch,ok", [
        ("absorb-igig-a1-salvage", True), ("feat/absorb-igig-a6", True), ("absorb-igig", True),
        ("absorb-igigx-a1", False), ("absorb-orbity-a1", False), ("feat/misc", False), ("dev", False),
    ])
    def test_branch_may_touch(self, branch, ok):
        assert abs_src.branch_may_touch(branch, "igig") is ok

    def test_source_of_path(self):
        assert abs_src.source_of_path("/w/products/igig/backend/a.py", SOURCES) == "igig"
        assert abs_src.source_of_path("products/orbity/a.py", SOURCES) is None
        assert abs_src.source_of_path("products/igig", SOURCES) == "igig"  # `rm -rf products/igig` off-branch is a write too
        assert abs_src.source_of_path("/w/seed/products/igigx/a.py", SOURCES) is None

    def test_refusal_names_the_canon(self):
        r = abs_src.refusal_reason("erp-imobiliario", "social-wiring", "feat/x", "p")
        assert "social-wiring" in r and "absorb-erp-imobiliario-" in r


# ───────────────────────────── F2: guard decision ─────────────────────────────
class TestGuardDecide:
    def _d(self, tool, inp, branch, **kw):
        return abs_src.decide(tool, inp, "/w", SOURCES, branch_for=lambda _p: branch, **kw)

    def test_edit_denied_off_branch(self):
        v = self._d("Edit", {"file_path": "/w/products/erp-imobiliario/backend/x.py"}, "feat/other")
        assert v and v["canon"] == "social-wiring" and "social-wiring" in v["reason"]

    def test_same_write_passes_on_the_absorb_branch(self):
        assert self._d("Edit", {"file_path": "/w/products/igig/x.py"}, "feat/absorb-igig-a5") is None

    def test_canon_and_seed_untouched(self):
        assert self._d("Write", {"file_path": "/w/products/orbity/x.py"}, "feat/other") is None
        assert self._d("Write", {"file_path": "/w/seed/lib/x.py"}, "feat/other") is None

    def test_unknown_branch_is_denied(self):
        assert self._d("Write", {"file_path": "/w/products/igig/x.py"}, None)["branch"] is None

    def test_bash_targets_come_from_the_shell_parser(self):
        bt = lambda cmd, cwd: (["/w/products/community/a.sql"], False)  # noqa: E731
        assert self._d("Bash", {"command": "x"}, "feat/other", bash_targets=bt)["source"] == "community"
        assert self._d("Bash", {"command": "x"}, "feat/absorb-community-a1", bash_targets=bt) is None

    def test_empty_registry_allows(self):
        assert abs_src.decide("Edit", {"file_path": "/w/products/igig/x.py"}, "/w", {}) is None


def _git(root: Path, *a: str) -> None:
    subprocess.run(["git", *a], cwd=root, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                        "HOME": str(root.parent)})


@pytest.fixture
def scratch(tmp_path):
    """A scratch git repo carrying copies of the real hook + modules and a planted registry (the hook derives its
    REPO_ROOT from its own path, so a copy is the way to give it a registry without a test seam in production code)."""
    root = tmp_path / "repo"
    for rel in ("scripts/hooks/claude-guard-absorption-source.py", "scripts/hooks/_guard_failclosed.py",
                "mcp/noctusai/tools/noctus/dev/absorption_sources.py", "mcp/noctusai/tools/noctus/dev/primary_write_guard.py"):
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO_ROOT / rel, dst)
    (root / "project-history").mkdir()
    (root / "project-history" / "absorptions.ndjson").write_text(REGISTRY)
    (root / "products" / "igig").mkdir(parents=True)
    (root / "products" / "orbity").mkdir(parents=True)

    git = lambda *a: _git(root, *a)  # noqa: E731
    git("init", "-q", "-b", "feat/other")
    (root / "products" / "igig" / "a.py").write_text("x = 1\n")
    (root / "products" / "orbity" / "a.py").write_text("x = 1\n")
    git("add", "-A")
    git("commit", "-q", "-m", "init")
    return root


def _run_hook(root: Path, payload: dict) -> dict | None:
    p = subprocess.run([sys.executable, str(root / "scripts/hooks/claude-guard-absorption-source.py")],
                       input=json.dumps(payload), capture_output=True, text=True, cwd=root, timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout) if p.stdout.strip() else None


class TestGuardHook:
    def _edit(self, root, rel):
        return {"tool_name": "Edit", "tool_input": {"file_path": str(root / rel)}, "cwd": str(root), "session_id": "s"}

    def test_planted_write_is_denied_naming_the_canon(self, scratch):
        out = _run_hook(scratch, self._edit(scratch, "products/igig/a.py"))
        d = out["hookSpecificOutput"]
        assert d["permissionDecision"] == "deny" and "[noc-guard:absorption-source]" in d["permissionDecisionReason"]
        assert "orbity" in d["permissionDecisionReason"]

    def test_same_write_passes_on_the_absorb_branch(self, scratch):
        _git(scratch, "checkout", "-q", "-b", "absorb-igig-a5")
        assert _run_hook(scratch, self._edit(scratch, "products/igig/a.py")) is None

    def test_write_to_the_canon_passes(self, scratch):
        assert _run_hook(scratch, self._edit(scratch, "products/orbity/a.py")) is None

    def test_bash_redirect_into_a_source_is_denied(self, scratch):
        payload = {"tool_name": "Bash", "tool_input": {"command": "echo hi > products/igig/new.txt"},
                   "cwd": str(scratch), "session_id": "s"}
        out = _run_hook(scratch, payload)
        assert out and out["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_read_only_bash_is_not_judged(self, scratch):
        payload = {"tool_name": "Bash", "tool_input": {"command": "cat products/igig/a.py"}, "cwd": str(scratch), "session_id": "s"}
        assert _run_hook(scratch, payload) is None

    def test_unreadable_registry_fails_closed_on_products_paths(self, scratch):
        (scratch / "project-history" / "absorptions.ndjson").unlink()
        out = _run_hook(scratch, self._edit(scratch, "products/orbity/a.py"))
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "cannot derive the absorption-source list" in out["hookSpecificOutput"]["permissionDecisionReason"]

    def test_non_products_path_never_reads_the_registry(self, scratch):
        (scratch / "project-history" / "absorptions.ndjson").unlink()
        assert _run_hook(scratch, self._edit(scratch, "seed/x.py")) is None

    def test_deny_is_a_gate_fire_row(self, scratch, tmp_path):
        _run_hook(scratch, self._edit(scratch, "products/igig/a.py"))
        rows = [json.loads(ln) for ln in (tmp_path / "guard-events.ndjson").read_text().splitlines()]
        assert [r["outcome"] for r in rows if r["guard"] == "absorption-source"] == ["deny"]


# ───────────────────────────── F3: commit keeper ─────────────────────────────
class TestAbsorptionSourceFrozen:
    def _k(self, staged, branch="feat/other"):
        return check_absorption_source_frozen(staged=staged, branch=branch, sources=SOURCES)

    def test_red_on_a_planted_staged_edit(self):
        issues = self._k([("M", "products/erp-imobiliario/backend/app/x.py")])
        assert len(issues) == 1 and "social-wiring" in issues[0]["issue"] and issues[0]["severity"] == "high"

    def test_green_on_a_pure_deletion(self):
        assert self._k([("D", "products/erp-imobiliario/backend/app/x.py"), ("D", "products/igig/y.py")]) == []

    def test_added_file_is_a_change(self):
        assert self._k([("A", "products/igig/new.py")])

    def test_green_on_the_matching_absorb_branch(self):
        assert self._k([("M", "products/igig/x.py")], branch="feat/absorb-igig-a5") == []

    def test_other_sources_absorb_branch_does_not_cover_this_one(self):
        assert self._k([("M", "products/igig/x.py")], branch="absorb-community-a1")

    def test_canon_change_is_fine(self):
        assert self._k([("M", "products/orbity/x.py"), ("M", "seed/y.py")]) == []

    def test_unreadable_ledger_is_unmeasured_not_green_noise(self, tmp_path, capsys):
        assert check_absorption_source_frozen(repo_root=tmp_path, staged=[("M", "products/igig/x.py")], branch="x") == []
        assert "UNMEASURED" in capsys.readouterr().err

    def test_fire_is_a_gate_fire_row(self, tmp_path):
        check_absorption_source_frozen(staged=[("M", "products/igig/x.py")], branch="feat/x", sources=SOURCES)
        rows = [json.loads(ln) for ln in (tmp_path / "guard-events.ndjson").read_text().splitlines()]
        assert [(r["guard"], r["outcome"]) for r in rows] == [("keeper:check-absorption-source-frozen", "deny")]


# ───────────────────────────── F4: pilot is canon + reference lint ─────────────────────────────
TODAY_ROW = json.dumps({"ts": "2026-06-02T00:00:01+00:00", "slug": "orbity", "kind": "capability",
                        "capability": "financial-management", "target_organ": "noctusai_lib.domain.finance",
                        "status": "identified", "pilot": "erp-imobiliario", "note": ""})


class TestAbsorptionPilotIsCanon:
    def _k(self, text, sidecars=None):
        return check_absorption_pilot_is_canon(ledger_text=text, sidecars=sidecars or {}, sources=SOURCES)

    def test_red_on_the_orbity_financial_management_row(self):
        issues = self._k(TODAY_ROW)
        assert len(issues) == 1 and "social-wiring" in issues[0]["issue"] and "financial-management" in issues[0]["issue"]

    def test_green_once_repointed_append_only(self):
        repoint = json.dumps({**json.loads(TODAY_ROW), "ts": "2026-11-12T12:00:00+00:00", "pilot": "social-wiring"})
        assert self._k(TODAY_ROW + "\n" + repoint) == []

    def test_sidecar_pilot_key_naming_a_source_is_red(self):
        issues = self._k("", {"seed/x/Foo.organ.yaml": "name: Foo\nphase: pilot-seed\npilot_consumer: igig  # old\n"})
        assert len(issues) == 1 and issues[0]["file"] == "seed/x/Foo.organ.yaml" and "orbity" in issues[0]["issue"]

    def test_phase_pilot_seed_is_not_a_pilot_key(self):
        assert self._k("", {"a.organ.yaml": "phase: pilot-seed\npilot: social-wiring\n"}) == []


class TestReferenceLint:
    BRIEF = ("Build the assistant chat page. Use erp-imobiliario's inbox page as the reference "
             "(products/erp-imobiliario/frontend/src/pages/Inbox.tsx).")

    def test_flags_the_2026_11_12_chat_page_brief(self):
        w = abs_src.lint_text_for_source_reference(self.BRIEF, SOURCES)
        assert [x["source"] for x in w] == ["erp-imobiliario"] and "social-wiring" in w[0]["message"]

    def test_absorption_slice_is_exempt(self):
        assert abs_src.lint_text_for_source_reference("branch absorb-erp-imobiliario-a1: " + self.BRIEF, SOURCES) == []

    def test_plain_word_community_is_not_a_reference(self):
        assert abs_src.lint_text_for_source_reference("the community feed, a community of users", SOURCES) == []
        assert abs_src.lint_text_for_source_reference("see `community` inbox", SOURCES)

    def test_compose_brief_warns_and_renders_the_block(self):
        r = compose_brief(["products/social-wiring/frontend/x.tsx"], self.BRIEF, agent="frontend-engineer",
                          embed_text=lambda t: {"ok": False, "error": "off"}, ai_query=lambda *a, **k: [],
                          kb_search=lambda *a, **k: [], score_rows=lambda: [], sources=SOURCES)
        assert r["source_warnings"] and "Frozen absorption source named" in r["brief"]

    def test_output_lint_warns_but_does_not_fail(self):
        text = "Used products/igig/backend/x.py as a model.\n\ndrift-found:\n- none\n\nscoped-improvement:\n- none\n"
        r = lint_return(text, sources=SOURCES)
        assert r["ok"] is True and any("igig" in w for w in r["warnings"])
