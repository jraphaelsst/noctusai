"""Colocated tests for noctus.dev.predeploy_check.

No real builds / DB / disk — run_check, write_report, log_fn, fixer and the
clock are all injected (the smoke_fleet pattern). Covers: the pure classifier
(known classes + open-taxonomy unknown), all-pass → ready, a known failure →
blocked + classified (no report), an unknown failure → report + s1 log, and
the auto-fix path for the framework-dep class.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import predeploy_check as PC  # noqa: E402


# ── pure classifier ──────────────────────────────────────────────
def test_classify_known_npm_root_hoist():
    c = PC.classify_failure("error TS2307: Cannot find module '@supabase/supabase-js'")
    assert c is not None and c["class_id"] == "npm_root_hoist"
    assert c["matched"] == "@supabase/supabase-js"
    assert c["auto_fixable"] is False


def test_classify_known_pip_framework_implicit():
    c = PC.classify_failure("django.core.exceptions.fields.E210 ... ImageField")
    assert c is not None and c["class_id"] == "pip_framework_implicit"


def test_classify_known_vite_localhost():
    c = PC.classify_failure("bundle contains http://localhost:8000/api")
    assert c is not None and c["class_id"] == "vite_baked_localhost"


def test_classify_unknown_returns_none():
    assert PC.classify_failure("some entirely novel failure shape") is None


# ── orchestration (all IO injected) ──────────────────────────────
def _now():
    return dt.datetime(2026, 5, 22, 12, 0, 0)


def test_all_pass_is_ready():
    r = PC.predeploy_check(
        "core",
        run_check=lambda c, p, root: (True, "ok"),
        repo_root="/tmp",
        now=_now,
    )
    assert r["status"] == "ready" and r["exit_code"] == 0
    assert r["classified"] == [] and r["unknown_count"] == 0
    assert r["report_path"] is None


def test_known_failure_blocks_and_classifies_without_report():
    logs: list = []
    r = PC.predeploy_check(
        "core",
        run_check=lambda c, p, root: (False, "TS2307: Cannot find module 'x'") if c == "frontend_build" else (True, "ok"),
        log_fn=lambda *a, **k: logs.append(a) or 1,
        write_report=lambda name, body: (_ for _ in ()).throw(AssertionError("no report for a KNOWN class")),
        repo_root="/tmp",
        now=_now,
    )
    assert r["status"] == "blocked" and r["exit_code"] == 1
    assert any(c["class_id"] == "npm_root_hoist" for c in r["classified"])
    assert r["unknown_count"] == 0 and r["report_path"] is None
    assert logs == []  # known class is not logged as a learning


def test_unknown_failure_writes_report_and_logs_s1():
    logs: list = []
    written: dict = {}
    r = PC.predeploy_check(
        "core",
        run_check=lambda c, p, root: (False, "totally novel boom") if c == "backend_tests" else (True, "ok"),
        log_fn=lambda *a, **k: logs.append(a) or 1,
        write_report=lambda name, body: (written.update({"name": name, "body": body}) or f"predeploy-reports/{name}"),
        repo_root="/tmp",
        now=_now,
    )
    assert r["status"] == "blocked"
    assert r["unknown_count"] == 1
    assert r["report_path"] == "predeploy-reports/20260522T120000Z-core.md"
    assert "novel boom" in written["body"]
    assert len(logs) == 1
    # log_learning(project_slug, phase_number, ...) — s1 to the deploy-hardening project
    assert logs[0][0] == PC.PROJECT_SLUG and logs[0][1] == 4


def test_auto_fix_framework_deps_recovers():
    calls = {"n": 0}

    def run_check(c, p, root):
        if c == "framework_deps":
            calls["n"] += 1
            return (calls["n"] > 1, "missing framework dep" if calls["n"] == 1 else "ok")
        return (True, "ok")

    r = PC.predeploy_check(
        "core",
        run_check=run_check,
        fix_framework_deps=lambda root, product: True,  # pretend the fixer applied
        auto_fix=True,
        repo_root="/tmp",
        now=_now,
    )
    assert r["status"] == "ready" and "framework_deps" in r["auto_fixed"]


def test_missing_product_errors():
    r = PC.predeploy_check("", run_check=lambda c, p, root: (True, "ok"))
    assert r["status"] == "error"


def test_tool_registers_with_dotted_name():
    captured = {}

    class _Srv:
        def tool(self, name, description):
            captured["name"] = name

            def deco(fn):
                return fn

            return deco

    PC.register(_Srv())
    assert captured["name"] == "noctus.dev.predeploy_check"


# ── D3 deploy-local-gitignored assertion (audit_deploy_local) ─────
# run_git is injected (root, args) -> (returncode, stdout); zero real git.
import json as _json  # noqa: E402


def _manifest(tmp_path, paths):
    m = {
        "version": 1,
        "deploy_local_files": [
            {"path": p, "must_be_gitignored": True, "reason": "test"} for p in paths
        ],
    }
    f = tmp_path / "STATE.json"
    f.write_text(_json.dumps(m))
    return str(f)


def test_deploy_local_in_default_checks():
    assert "deploy_local_gitignored" in PC.DEFAULT_CHECKS


def test_audit_deploy_local_clean(tmp_path):
    sp = _manifest(tmp_path, [".env", "deploy/tunnel/config.yml", "deploy/tunnel/*.json"])
    # not tracked (ls-files empty) + ignored (check-ignore rc 0)
    audit = PC.audit_deploy_local(
        Path("/tmp"),
        run_git=lambda root, args: (0, "") if args[0] == "ls-files" else (0, ""),
        state_path=sp,
    )
    assert audit["checked"] == 3 and audit["violations"] == []


def test_audit_deploy_local_tracked_is_violation(tmp_path):
    sp = _manifest(tmp_path, [".env"])

    def run_git(root, args):
        if args[0] == "ls-files":
            return (0, ".env\n")  # tracked!
        return (0, "")

    audit = PC.audit_deploy_local(Path("/tmp"), run_git=run_git, state_path=sp)
    assert audit["violations"] and "TRACKED" in audit["violations"][0]


def test_audit_deploy_local_not_ignored_is_violation(tmp_path):
    sp = _manifest(tmp_path, [".env"])

    def run_git(root, args):
        if args[0] == "ls-files":
            return (0, "")  # not tracked
        return (1, "")  # check-ignore MISS → not gitignored

    audit = PC.audit_deploy_local(Path("/tmp"), run_git=run_git, state_path=sp)
    assert audit["violations"] and "NOT gitignored" in audit["violations"][0]


def test_audit_deploy_local_no_manifest_skips(tmp_path):
    audit = PC.audit_deploy_local(Path("/tmp"), state_path=str(tmp_path / "absent.json"))
    assert audit["manifest"] is None and audit["checked"] == 0 and audit["violations"] == []


def test_classify_deploy_local_violation_is_known():
    c = PC.classify_failure("D3 deploy-local invariant VIOLATED: .env is TRACKED — must be gitignored (D3)")
    assert c is not None and c["class_id"] == "deploy_local_tracked"
    assert c["auto_fixable"] is False


def test_d3_violation_blocks_via_injected_run_check():
    r = PC.predeploy_check(
        "core",
        run_check=lambda c, p, root: (False, "D3 deploy-local invariant VIOLATED: .env is TRACKED — must be gitignored (D3)")
        if c == "deploy_local_gitignored" else (True, "ok"),
        repo_root="/tmp",
        now=_now,
    )
    assert r["status"] == "blocked"
    assert any(x["class_id"] == "deploy_local_tracked" for x in r["classified"])
    assert r["unknown_count"] == 0  # classified, not a spurious unknown


def test_audit_deploy_local_real_repo_passes():
    """Read-only smoke against the live tree: the repo's own deploy-local
    files are gitignored, so the real manifest must show zero violations."""
    from settings import REPO_ROOT  # noqa: E402

    audit = PC.audit_deploy_local(Path(REPO_ROOT))
    if audit["manifest"] is not None:
        assert audit["violations"] == [], audit["violations"]
