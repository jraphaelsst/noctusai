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
