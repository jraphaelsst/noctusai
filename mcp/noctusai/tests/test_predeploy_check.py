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
# The manifest is now a code constant (deploy_state.DEPLOY_LOCAL_FILES); the
# audit takes `entries` for injection and run_git for zero-real-git tests.
_E = [{"pattern": ".env"}, {"pattern": "**/tunnel/config.yml"}, {"pattern": "**/tunnel/*.json"}]


def test_deploy_local_in_default_checks():
    assert "deploy_local_gitignored" in PC.DEFAULT_CHECKS


def test_audit_uses_the_constant_by_default():
    from deploy_state import DEPLOY_LOCAL_FILES  # noqa: E402

    audit = PC.audit_deploy_local(
        Path("/tmp"), run_git=lambda root, args: (0, "")
    )  # all clean
    assert audit["source"] == "deploy_state.DEPLOY_LOCAL_FILES"
    assert audit["checked"] == len(DEPLOY_LOCAL_FILES) and audit["violations"] == []


def test_audit_deploy_local_clean():
    # not tracked (ls-files empty) + ignored (check-ignore rc 0)
    audit = PC.audit_deploy_local(
        Path("/tmp"), run_git=lambda root, args: (0, ""), entries=_E
    )
    assert audit["checked"] == 3 and audit["violations"] == []


def test_audit_deploy_local_tracked_is_violation():
    def run_git(root, args):
        if args[0] == "ls-files":
            return (0, ".env\n")  # tracked!
        return (0, "")

    audit = PC.audit_deploy_local(Path("/tmp"), run_git=run_git, entries=[{"pattern": ".env"}])
    assert audit["violations"] and "TRACKED" in audit["violations"][0]


def test_audit_deploy_local_not_ignored_is_violation():
    def run_git(root, args):
        if args[0] == "ls-files":
            return (0, "")  # not tracked
        return (1, "")  # check-ignore MISS → not gitignored

    audit = PC.audit_deploy_local(Path("/tmp"), run_git=run_git, entries=[{"pattern": ".env"}])
    assert audit["violations"] and "NOT gitignored" in audit["violations"][0]


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
    """Read-only smoke against the live tree with the REAL constant: the repo's
    own deploy-local files are gitignored, so the audit must show zero
    violations (the gate would block a real deploy otherwise)."""
    from settings import REPO_ROOT  # noqa: E402

    audit = PC.audit_deploy_local(Path(REPO_ROOT))
    assert audit["violations"] == [], audit["violations"]


# ── prod_config_parity (value-correctness, 3rd leg of deploy-config-contract) ──
# Pure auditor + .env parser + snapshot resolution + runner integration +
# classification. The deterministic core takes a provided env mapping → no real
# environment needed (deploy-config-contract option b).
def test_prod_config_parity_in_default_checks():
    assert "prod_config_parity" in PC.DEFAULT_CHECKS


def test_prod_config_parity_clean_per_product():
    a = PC.audit_prod_config_parity(
        ["core", "erp-imobiliario"],
        {
            "PRODUCT_URL_CORE": "https://noctusai.com",
            "PRODUCT_URL_ERP_IMOBILIARIO": "https://erp.noctusai.com",
        },
    )
    assert a["violations"] == [] and a["checked"] == 2
    assert a["source"] == "prod-env-snapshot"


def test_prod_config_parity_clean_with_pattern_covers_fleet():
    a = PC.audit_prod_config_parity(
        ["core", "x", "y"], {"PRODUCT_URL_PATTERN": "https://{slug}.noctusai.com"}
    )
    assert a["violations"] == []  # one pattern resolves the whole roster


def test_prod_config_parity_missing_override_flags_each_slug():
    a = PC.audit_prod_config_parity(["core", "erp-imobiliario"], {})
    assert len(a["violations"]) == 2
    assert any("'core'" in v for v in a["violations"])
    assert any("erp-imobiliario" in v for v in a["violations"])


def test_prod_config_parity_localhost_value_flagged_even_with_pattern():
    # PRESENCE passes (pattern set), but the explicit value is localhost — the
    # exact present-but-wrong shape the boot guard can't catch.
    a = PC.audit_prod_config_parity(
        ["core"],
        {
            "PRODUCT_URL_PATTERN": "https://{slug}.noctusai.com",
            "PRODUCT_URL_CORE": "http://localhost:8000",
        },
    )
    assert any("loopback" in v and "PRODUCT_URL_CORE" in v for v in a["violations"])


def test_prod_config_parity_flags_loopback_in_cors_origins():
    a = PC.audit_prod_config_parity(
        ["core"],
        {
            "PRODUCT_URL_PATTERN": "https://{slug}.noctusai.com",
            "CORS_ORIGINS": "https://a.com,http://127.0.0.1:3000",
        },
    )
    assert any("CORS_ORIGINS" in v and "loopback" in v for v in a["violations"])


def test_classify_prod_config_localhost_unresolved_is_known():
    c = PC.classify_failure(
        "prod-config parity VIOLATED: prod URL unresolved for 'erp-imobiliario': "
        "neither PRODUCT_URL_ERP_IMOBILIARIO nor PRODUCT_URL_PATTERN set"
    )
    assert c is not None and c["class_id"] == "prod_config_localhost"
    assert c["auto_fixable"] is False


def test_classify_prod_config_localhost_value_wins_over_vite_class():
    # message quotes http://localhost:8000 — prod_config_localhost must still win
    # the first-match (it is ordered BEFORE vite_baked_localhost).
    c = PC.classify_failure(
        "prod-config parity VIOLATED: PRODUCT_URL_CORE carries a localhost/"
        "loopback host ('http://localhost:8000') — not prod-safe"
    )
    assert c is not None and c["class_id"] == "prod_config_localhost"


def test_parse_env_file_handles_comments_quotes_export():
    text = (
        "# comment\n"
        "\n"
        'export PRODUCT_URL_CORE="https://noctusai.com"\n'
        "FOO = bar \n"
        "QUOTED='x y'\n"
        "NOEQUALS\n"
    )
    parsed = PC._parse_env_file(text)
    assert parsed["PRODUCT_URL_CORE"] == "https://noctusai.com"
    assert parsed["FOO"] == "bar"
    assert parsed["QUOTED"] == "x y"
    assert "NOEQUALS" not in parsed


def test_resolve_prod_env_path_priority(tmp_path, monkeypatch):
    monkeypatch.delenv("NOCTUS_PROD_ENV_FILE", raising=False)
    assert PC._resolve_prod_env_path(tmp_path) is None  # none present

    conv = tmp_path / ".env.prod"
    conv.write_text("X=1")
    assert PC._resolve_prod_env_path(tmp_path) == conv  # conventional

    other = tmp_path / "snap.env"
    other.write_text("Y=2")
    monkeypatch.setenv("NOCTUS_PROD_ENV_FILE", str(other))
    assert PC._resolve_prod_env_path(tmp_path) == other  # env var beats conventional

    expl = tmp_path / "explicit.env"
    expl.write_text("Z=3")
    assert PC._resolve_prod_env_path(tmp_path, str(expl)) == expl  # explicit wins

    # explicit-but-missing → None (never a silent fallthrough to a weaker source)
    assert PC._resolve_prod_env_path(tmp_path, str(tmp_path / "nope.env")) is None


def test_prod_config_parity_runner_skips_without_snapshot(tmp_path, monkeypatch):
    monkeypatch.delenv("NOCTUS_PROD_ENV_FILE", raising=False)
    ok, out = PC._default_run_check("prod_config_parity", "core", tmp_path)
    assert ok is True and "SKIPPED" in out  # loud skip, not a silent pass


def test_prod_config_parity_runner_skips_on_empty_roster(tmp_path, monkeypatch):
    monkeypatch.delenv("NOCTUS_PROD_ENV_FILE", raising=False)
    (tmp_path / ".env.prod").write_text("PRODUCT_URL_PATTERN=https://{slug}.x.com")
    monkeypatch.setattr(PC, "_load_roster_slugs", lambda root: [])
    ok, out = PC._default_run_check("prod_config_parity", "core", tmp_path)
    assert ok is True and "empty product roster" in out


def test_prod_config_parity_runner_clean_with_pattern(tmp_path, monkeypatch):
    monkeypatch.delenv("NOCTUS_PROD_ENV_FILE", raising=False)
    (tmp_path / ".env.production").write_text(
        "PRODUCT_URL_PATTERN=https://{slug}.noctusai.com\n"
    )
    monkeypatch.setattr(
        PC, "_load_roster_slugs", lambda root: ["core", "erp-imobiliario", "social-wiring"]
    )
    ok, out = PC._default_run_check("prod_config_parity", "core", tmp_path)
    assert ok is True and "parity ok" in out


def test_prod_config_parity_runner_audits_snapshot_and_blocks(tmp_path, monkeypatch):
    monkeypatch.delenv("NOCTUS_PROD_ENV_FILE", raising=False)
    # core resolves; erp-imobiliario has no matching key → violation
    (tmp_path / ".env.prod").write_text(
        "PRODUCT_URL_CORE=https://noctusai.com\nPRODUCT_URL_ERP=https://erp.x\n"
    )
    monkeypatch.setattr(PC, "_load_roster_slugs", lambda root: ["core", "erp-imobiliario"])
    ok, out = PC._default_run_check("prod_config_parity", "core", tmp_path)
    assert ok is False and "erp-imobiliario" in out and "VIOLATED" in out


def test_prod_config_parity_blocks_and_classifies_via_injected_run_check():
    r = PC.predeploy_check(
        "core",
        run_check=lambda c, p, root: (
            False,
            "prod-config parity VIOLATED: prod URL unresolved for "
            "'erp-imobiliario': neither PRODUCT_URL_ERP_IMOBILIARIO nor "
            "PRODUCT_URL_PATTERN set",
        )
        if c == "prod_config_parity"
        else (True, "ok"),
        repo_root="/tmp",
        now=_now,
    )
    assert r["status"] == "blocked" and r["exit_code"] == 1
    assert any(x["class_id"] == "prod_config_localhost" for x in r["classified"])
    assert r["unknown_count"] == 0  # classified, not a spurious unknown


def test_prod_env_path_threads_to_default_runner(tmp_path, monkeypatch):
    # an explicit prod_env_path passed to predeploy_check must reach the default
    # runner (functools.partial threading), so the parity check audits it.
    monkeypatch.delenv("NOCTUS_PROD_ENV_FILE", raising=False)
    snap = tmp_path / "prod.env"
    snap.write_text("PRODUCT_URL_PATTERN=https://{slug}.noctusai.com\n")
    monkeypatch.setattr(PC, "_load_roster_slugs", lambda root: ["core"])
    r = PC.predeploy_check(
        "core",
        checks=["prod_config_parity"],
        prod_env_path=str(snap),
        repo_root=str(tmp_path),
        now=_now,
    )
    assert r["status"] == "ready"  # pattern resolves the roster, no violations


# ── cors_roster_complete (backstop — B4 container env) ───────────────────────
# Pure auditor checks that every slug has PRODUCT_URL_<SLUG> OR PRODUCT_URL_PATTERN.

def test_cors_roster_complete_in_default_checks():
    assert "cors_roster_complete" in PC.DEFAULT_CHECKS


def test_audit_cors_roster_clean_with_pattern():
    a = PC.audit_cors_roster_complete(
        ["core", "orbity"],
        {"PRODUCT_URL_PATTERN": "https://{slug}.noctusai.com"},
    )
    assert a["violations"] == []
    assert a["checked"] == 2


def test_audit_cors_roster_clean_with_explicit_overrides():
    a = PC.audit_cors_roster_complete(
        ["core", "orbity"],
        {
            "PRODUCT_URL_CORE": "https://noctusai.com",
            "PRODUCT_URL_ORBITY": "https://orbity.noctusai.com",
        },
    )
    assert a["violations"] == []


def test_audit_cors_roster_missing_origin_flags_slug():
    """Slug with no override AND no pattern → violation (the orbity shape)."""
    a = PC.audit_cors_roster_complete(["orbity", "core"], {})
    assert len(a["violations"]) == 2
    assert any("orbity" in v for v in a["violations"])
    assert any("ensure_product_url_roster" in v for v in a["violations"])


def test_audit_cors_roster_partial_overrides_flags_only_missing():
    """core has override but orbity is missing and there's no pattern → only orbity flagged."""
    a = PC.audit_cors_roster_complete(
        ["core", "orbity"],
        {"PRODUCT_URL_CORE": "https://noctusai.com"},
    )
    assert len(a["violations"]) == 1
    assert "orbity" in a["violations"][0]


def test_classify_cors_roster_missing_is_known():
    msg = "cors_roster_complete VIOLATED: no CORS origin resolvable for 'orbity': ..."
    c = PC.classify_failure(msg)
    assert c is not None and c["class_id"] == "cors_roster_missing"
    assert "ensure_product_url_roster" in c["suggested_fix"]
    assert c["auto_fixable"] is False


def test_cors_roster_runner_skips_without_snapshot(monkeypatch, tmp_path):
    monkeypatch.delenv("NOCTUS_PROD_ENV_FILE", raising=False)
    ok, msg = PC._default_run_check("cors_roster_complete", "core", tmp_path)
    assert ok is True  # skip is not a failure
    assert "SKIPPED" in msg


def test_cors_roster_runner_skips_on_empty_roster(monkeypatch, tmp_path):
    snap = tmp_path / ".env.prod"
    snap.write_text("PRODUCT_URL_PATTERN=https://{slug}.noctusai.com\n")
    monkeypatch.setattr(PC, "_load_roster_slugs", lambda root: [])
    ok, msg = PC._default_run_check("cors_roster_complete", "core", tmp_path)
    assert ok is True
    assert "SKIPPED" in msg


def test_cors_roster_runner_clean_with_pattern(monkeypatch, tmp_path):
    snap = tmp_path / ".env.prod"
    snap.write_text("PRODUCT_URL_PATTERN=https://{slug}.noctusai.com\n")
    monkeypatch.setattr(PC, "_load_roster_slugs", lambda root: ["core", "orbity"])
    ok, msg = PC._default_run_check("cors_roster_complete", "core", tmp_path)
    assert ok is True
    assert "ok" in msg.lower()


def test_cors_roster_runner_blocks_on_missing_origin(monkeypatch, tmp_path):
    snap = tmp_path / ".env.prod"
    snap.write_text("PRODUCT_URL_CORE=https://noctusai.com\n")  # no pattern, no orbity
    monkeypatch.setattr(PC, "_load_roster_slugs", lambda root: ["core", "orbity"])
    ok, msg = PC._default_run_check("cors_roster_complete", "core", tmp_path)
    assert ok is False
    assert "orbity" in msg


def test_load_roster_slugs_returns_list_against_real_tree():
    from settings import REPO_ROOT  # noqa: E402

    slugs = PC._load_roster_slugs(Path(REPO_ROOT))
    assert isinstance(slugs, list)
    if slugs:  # seed import + start.sh reachable → core is always in the roster
        assert "core" in slugs
