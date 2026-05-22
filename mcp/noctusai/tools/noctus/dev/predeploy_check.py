"""noctus.dev.predeploy_check — the pre-deploy verification + learning gate (P5).

Only code that BUILDS the slim deploy image + passes tests should reach prod
("always-only functional code online", `KB § GUIDES/production-deploy.md § 2a`
safety-net P5). This tool is that gate for a product: it runs the deploy-
relevant checks, then — the "learning" half of the user's ask ("create
mechanisms that learn from pre-deploy issues to auto-fix them … if not
executable via code, generate reports") — it:

  • CLASSIFIES each failure against the known boundary-contract classes
    (`KB § PATTERNS/boundary-contract-tests.md`): npm root-hoist (TS2307),
    pip framework-implicit (Django fieldsE/Pillow), VITE-baked-localhost,
    bare missing-module imports;
  • AUTO-FIXES the one class that is safely code-fixable today — framework
    dep drift — by composing the existing `check_framework_deps` fixer
    (only when `auto_fix=True`); source-mutating fixes (TS2307/Pillow) are
    SUGGESTED, never blind-applied (they need AST edits — deferred);
  • for an UNKNOWN failure, writes `predeploy-reports/<utc>-<product>.md` +
    logs a `phase_learnings` row (s1 of the codification pipeline) so a
    recurring unknown class can graduate to a detector. The taxonomy is
    OPEN — a non-matching failure becomes `unknown` + a report, never a
    force-fit into a wrong class.

IO is injectable (`run_check`, `write_report`, `log_fn`, `now`) so the
colocated test exercises every path with zero real builds (the smoke_fleet
pattern). The default `run_check` shells out (mirrors `noctus.dev.vite_build`
/ `noctus.dev.pytest`); `framework_deps` composes `check_framework_deps`.
"""
from __future__ import annotations

import datetime as _dt
import pathlib
import re
import subprocess
from typing import Any, Callable

from deploy_state import DEPLOY_LOCAL_FILES
from settings import REPO_ROOT, resolve_test_python
from workspace import resolve_caller_root

from . import check_framework_deps as _cfd
from . import phase_learnings as _pl

# Default deploy-relevant checks, in run order. Each is (name, kind).
DEFAULT_CHECKS: list[str] = [
    "framework_deps",
    "frontend_build",
    "backend_tests",
    "deploy_local_gitignored",  # D3 — every deploy_state.DEPLOY_LOCAL_FILES pattern is gitignored
]

PROJECT_SLUG = "deploy-hardening-and-dev-isolation"


# ── Known failure classes — OPEN taxonomy (non-match ⇒ `unknown` + report) ──
# Each: (class_id, compiled regex over the check output, human explanation,
# suggested fix, auto_fixable). Patterns drawn from the deploy GUIDE §6
# table + KB § PATTERNS/boundary-contract-tests.md.
_KNOWN: list[dict[str, Any]] = [
    {
        "class_id": "npm_root_hoist",
        "rx": re.compile(r"TS2307: Cannot find module '([^']+)'|Cannot find module '([^']+)'"),
        "boundary": "B1 build-injection",
        "explanation": (
            "A frontend dependency resolves in dev (root-hoisted node_modules) "
            "but is absent from the product's own package.json, so a clean "
            "Docker build can't find it."
        ),
        "suggested_fix": (
            "Add the missing module to products/<product>/frontend/package.json "
            "dependencies (pinned), then `npm install` in that dir."
        ),
        "auto_fixable": False,
    },
    {
        "class_id": "pip_framework_implicit",
        "rx": re.compile(r"fields\.E210|Cannot use ImageField because Pillow|ModuleNotFoundError: No module named 'PIL'"),
        "boundary": "B4 container env",
        "explanation": (
            "A framework-implicit Python dep (e.g. Pillow for a Django "
            "ImageField) is installed in the working env but missing from the "
            "manifest the Dockerfile installs → fails only in a clean build."
        ),
        "suggested_fix": "Add the implicit dep (e.g. Pillow) to requirements.txt, pinned.",
        "auto_fixable": False,
    },
    {
        "class_id": "vite_baked_localhost",
        "rx": re.compile(r"http://localhost:\d+"),
        "boundary": "B1 build-injection",
        "explanation": (
            "A built bundle contains a hardcoded http://localhost:<port> API "
            "base — the seed's same-origin contract (window.location.origin) "
            "was bypassed; the deployed SPA will call localhost, not the host."
        ),
        "suggested_fix": (
            "Use the seed vite factory's window.location.origin define-injection; "
            "never hardcode the API base. See KB § PATTERNS/containerization.md § same-origin."
        ),
        "auto_fixable": False,
    },
    {
        "class_id": "framework_dep_drift",
        "rx": re.compile(r"framework[- ]dep|package\.json .*drift|missing framework dep", re.I),
        "boundary": "B1 build-injection",
        "explanation": "Product frontend package.json is missing a seed-framework dep.",
        "suggested_fix": "Run check_framework_deps with fix=True (or predeploy_check auto_fix=True).",
        "auto_fixable": True,
    },
    {
        "class_id": "deploy_local_tracked",
        "rx": re.compile(
            r"D3 deploy-local invariant VIOLATED|is TRACKED — must be gitignored|NOT gitignored — a future write"
        ),
        "boundary": "D3 deploy-state manifest",
        "explanation": (
            "A deploy-local file (filled-in-place on the VPS — tunnel config.yml, "
            "creds *.json, root .env) is git-tracked or not gitignored, so a "
            "`git pull` on the production box could clobber it (the §2a P4/D3 net). "
            "The manifest lives in deploy_state.DEPLOY_LOCAL_FILES."
        ),
        "suggested_fix": (
            "git rm --cached <path> + add the path (or its **/ glob) to .gitignore, "
            "then re-render the file in-place on the box. See deploy_state.py + "
            "KB § GUIDES/production-deploy.md § 2a (P4/D3)."
        ),
        "auto_fixable": False,
    },
]


def classify_failure(output: str) -> dict[str, Any] | None:
    """Pure classifier: first known class whose regex matches, else None
    (unknown — caller writes a report + logs s1). OPEN taxonomy."""
    text = output or ""
    for cls in _KNOWN:
        m = cls["rx"].search(text)
        if m:
            hit = next((g for g in (m.groups() or ()) if g), m.group(0))
            return {
                "class_id": cls["class_id"],
                "boundary": cls["boundary"],
                "explanation": cls["explanation"],
                "suggested_fix": cls["suggested_fix"],
                "auto_fixable": cls["auto_fixable"],
                "matched": hit,
            }
    return None


# ── D3 deploy-state manifest assertion (deploy_state.DEPLOY_LOCAL_FILES) ──
# The §2a safety-net D3: every deploy-local file (filled-in-place on the VPS)
# MUST be gitignored so a pull cannot touch it BY CONSTRUCTION. The manifest is
# a code constant (deploy_state.py) — durable, can't be lost to an archive — so
# this gate ALWAYS runs (it cannot silently skip on a missing file).
def _default_run_git(root: pathlib.Path, args: list[str]) -> tuple[int, str]:
    """(returncode, stdout) for `git -C <root> <args>`. Injectable in
    audit_deploy_local so the test exercises every branch with zero real git."""
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return r.returncode, (r.stdout or "")


def audit_deploy_local(
    root: pathlib.Path,
    run_git: Callable[[pathlib.Path, list[str]], tuple[int, str]] | None = None,
    entries: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Assert every `deploy_state.DEPLOY_LOCAL_FILES` pattern is (a) NOT tracked
    and (b) covered by a gitignore rule. Patterns are gitignore-style globs
    (e.g. `**/tunnel/*.json`) — `git ls-files` pathspec finds any tracked match,
    and the ignore probe substitutes a placeholder for `*`. Returns
    {source, checked, violations}. `entries` is injectable for the test."""
    run = run_git or _default_run_git
    manifest = entries if entries is not None else DEPLOY_LOCAL_FILES
    violations: list[str] = []
    for e in manifest:
        pattern = (e.get("pattern") or "").strip()
        if not pattern:
            continue
        _rc_ls, out_ls = run(root, ["ls-files", "--", pattern])
        if out_ls.strip():
            violations.append(f"{pattern} is TRACKED — must be gitignored (D3)")
            continue
        probe = pattern.replace("*", "__probe__")
        rc_ci, _ = run(root, ["check-ignore", "-q", "--", probe])
        if rc_ci != 0:
            violations.append(f"{pattern} is NOT gitignored — a future write could be committed (D3)")
    return {"source": "deploy_state.DEPLOY_LOCAL_FILES", "checked": len(manifest), "violations": violations}


def _default_run_check(check: str, product: str, root: pathlib.Path) -> tuple[bool, str]:
    """Real runner — shells the deploy-relevant build/test (mirrors
    noctus.dev.vite_build / pytest); framework_deps composes the existing
    audit. Returns (ok, combined_output)."""
    if check == "framework_deps":
        drift, _missing, _ok = _cfd._audit(root)
        prod_drift = {p: deps for p, deps in (drift or {}).items() if p == product and deps}
        if prod_drift:
            return False, f"framework-dep drift for {product}: {prod_drift}"
        return True, "framework deps OK"
    if check == "frontend_build":
        fe = root / "products" / product / "frontend"
        if not fe.exists():
            return True, f"no frontend dir for {product} (skipped)"
        r = subprocess.run(["npx", "vite", "build"], cwd=fe, capture_output=True, text=True)
        return r.returncode == 0, (r.stdout + r.stderr)
    if check == "backend_tests":
        be = root / "products" / product / "backend"
        if not be.exists():
            return True, f"no backend dir for {product} (skipped)"
        r = subprocess.run([resolve_test_python(), "-m", "pytest", "-q"], cwd=be, capture_output=True, text=True)
        return r.returncode == 0, (r.stdout + r.stderr)
    if check == "deploy_local_gitignored":
        # Platform-wide invariant (product arg unused): D3 manifest assertion.
        # The manifest is a code constant, so this always runs (never skips).
        audit = audit_deploy_local(root)
        if audit["violations"]:
            return False, "D3 deploy-local invariant VIOLATED: " + "; ".join(audit["violations"])
        return True, f"D3 ok — {audit['checked']} deploy-local pattern(s) gitignored (deploy_state.py)"
    return False, f"unknown check '{check}'"


def _default_fix_framework_deps(root: pathlib.Path, product: str) -> bool:
    """Compose the existing check_framework_deps fixer for the one safely
    code-fixable class. Returns True iff a fix was applied. Injectable in
    predeploy_check so the orchestration is testable without touching disk."""
    drift, _m, _o = _cfd._audit(root)
    prod_drift = {p: d for p, d in (drift or {}).items() if p == product and d}
    if not prod_drift:
        return False
    _cfd._fix(root, prod_drift)
    return True


def _render_report(product: str, unknowns: list[dict], when: str) -> str:
    lines = [
        f"# pre-deploy report — {product} — {when}",
        "",
        "Unknown pre-deploy failure(s) — no known boundary-contract class matched.",
        "Logged to phase_learnings (s1). If this recurs, graduate it to a keeper",
        "detector (`KB § PATTERNS/methodology-codification-pipeline.md`).",
        "",
    ]
    for u in unknowns:
        lines += [f"## check: {u['check']}", "", "```", u["output"].strip()[:4000], "```", ""]
    return "\n".join(lines)


def predeploy_check(
    product: str,
    checks: list[str] | None = None,
    auto_fix: bool = False,
    run_check: Callable[[str, str, pathlib.Path], tuple[bool, str]] | None = None,
    write_report: Callable[[str, str], str] | None = None,
    log_fn: Callable[..., int] | None = None,
    fix_framework_deps: Callable[[pathlib.Path, str], bool] | None = None,
    repo_root: str | None = None,
    worktree_path: str | None = None,
    now: Callable[[], _dt.datetime] | None = None,
) -> dict[str, Any]:
    """Run the deploy-relevant checks for `product`; classify + (auto_fix the
    safe class) + report/learn unknowns. status='ready' (all pass) |
    'blocked' (≥1 fail). Never raises on a check failure — it returns it."""
    if not product or not product.strip():
        return {"ok": False, "status": "error", "error": "product required", "exit_code": 1}
    runner = run_check or _default_run_check
    logger = log_fn or _pl.log_learning
    fixer = fix_framework_deps or _default_fix_framework_deps
    clock = now or _dt.datetime.utcnow
    if repo_root is not None:
        root = pathlib.Path(repo_root)
    elif worktree_path:
        root = pathlib.Path(resolve_caller_root(worktree_path))
    else:
        root = pathlib.Path(REPO_ROOT)

    check_set = checks or DEFAULT_CHECKS
    results: list[dict[str, Any]] = []
    classified: list[dict[str, Any]] = []
    unknowns: list[dict[str, Any]] = []
    auto_fixed: list[str] = []

    for check in check_set:
        ok, output = runner(check, product, root)
        entry: dict[str, Any] = {"check": check, "ok": ok}
        if not ok:
            cls = classify_failure(output)
            if cls:
                entry["classified"] = cls
                classified.append({"check": check, **cls})
                # auto-fix only the safe, code-fixable class (framework deps)
                if auto_fix and cls["auto_fixable"] and check == "framework_deps":
                    fixed = fixer(root, product)
                    entry["fix_attempted"] = fixed
                    if fixed:
                        ok2, _out2 = runner(check, product, root)
                        entry["auto_fixed"] = ok2
                        if ok2:
                            entry["ok"] = True
                            auto_fixed.append(check)
            else:
                entry["classified"] = None
                unknowns.append({"check": check, "output": output})
            entry["output_tail"] = (output or "").strip()[-600:]
        results.append(entry)

    report_path: str | None = None
    if unknowns:
        when = clock().strftime("%Y%m%dT%H%M%SZ")
        report_md = _render_report(product, unknowns, when)
        if write_report is not None:
            report_path = write_report(f"{when}-{product}.md", report_md)
        else:
            rdir = root / "predeploy-reports"
            rdir.mkdir(exist_ok=True)
            rp = rdir / f"{when}-{product}.md"
            rp.write_text(report_md)
            report_path = str(rp.relative_to(root))
        for u in unknowns:
            logger(
                PROJECT_SLUG, 4, "predeploy unknown failure", "technical",
                f"[{product}/{u['check']}] unhandled pre-deploy failure (see {report_path}): "
                f"{u['output'].strip()[:200]}",
            )

    failed = [r for r in results if not r["ok"]]
    healthy = not failed
    return {
        "ok": True,
        "product": product,
        "status": "ready" if healthy else "blocked",
        "exit_code": 0 if healthy else 1,
        "checks": results,
        "classified": classified,
        "auto_fixed": auto_fixed,
        "unknown_count": len(unknowns),
        "report_path": report_path,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.predeploy_check",
        description=(
            "Pre-deploy verification + learning gate (deploy-hardening P5). "
            "For a product, runs the deploy-relevant checks (framework-dep "
            "parity, frontend vite build, backend pytest, and the D3 "
            "deploy-local-gitignored manifest assertion), CLASSIFIES any "
            "failure against the known boundary-contract classes, AUTO-FIXES "
            "the framework-dep class when auto_fix=True (composes "
            "check_framework_deps), and for an UNKNOWN failure writes "
            "predeploy-reports/<utc>-<product>.md + logs phase_learnings (s1). "
            "status='ready' (all pass, exit 0) | 'blocked' (≥1 fail, exit 1). "
            "Pass worktree_path when called from inside a git worktree. "
            "See KB § GUIDES/production-deploy.md § 2a + "
            "KB § PATTERNS/boundary-contract-tests.md."
        ),
    )
    def _predeploy_check(
        product: str,
        auto_fix: bool = False,
        worktree_path: str | None = None,
    ) -> dict:
        return predeploy_check(product, auto_fix=auto_fix, worktree_path=worktree_path)


__all__ = [
    "predeploy_check",
    "classify_failure",
    "audit_deploy_local",
    "DEFAULT_CHECKS",
    "PROJECT_SLUG",
    "register",
]
