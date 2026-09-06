"""Code analyzers — migrated from agents/keeper/analyzers/.

Discovers patterns, dependency issues, structure gaps, and test coverage.
"""
import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from settings import REPO_ROOT, PRODUCTS_DIR  # noqa: E402  (path constants)


class AnalyzePatternsInput(BaseModel):
    """No inputs — runs duplicated-functions + inline-hooks scans together."""


class DuplicatedFunction(BaseModel):
    function: str
    products: list[str]
    locations: list[dict[str, Any]]


class InlineHookIssue(BaseModel):
    product: str
    file: str
    severity: str


class AnalyzePatternsOutput(BaseModel):
    duplicated: list[DuplicatedFunction] = Field(default_factory=list)
    inline_hooks: list[InlineHookIssue] = Field(default_factory=list)


def _list_products():
    results = []
    for d in sorted(PRODUCTS_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            results.append({"name": d.name, "path": d})
    return results


def _read(path):
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("analyzers: cannot read %s (%s), skipping", path, exc)
        return None


def _find_files(directory, pattern):
    if not directory.exists():
        return []
    return sorted([f for f in directory.rglob(pattern) if "node_modules" not in str(f) and "__pycache__" not in str(f) and ".backup" not in str(f)])


# ── Pattern Finder ─────────────────────────────────────

def find_duplicated_functions(min_lines=5):
    products = _list_products()
    func_map = defaultdict(list)
    for product in products:
        backend = product["path"] / "backend" / "app"
        if not backend.exists():
            continue
        for py_file in _find_files(backend, "*.py"):
            content = _read(py_file)
            if not content:
                continue
            lines = content.splitlines()
            i = 0
            while i < len(lines):
                match = re.match(r'^(async )?def (\w+)\(', lines[i].strip())
                if match:
                    func_name = match.group(2)
                    if not func_name.startswith("_"):
                        body_end = i + 1
                        indent = len(lines[i]) - len(lines[i].lstrip())
                        while body_end < len(lines):
                            line = lines[body_end]
                            if line.strip() and (len(line) - len(line.lstrip())) <= indent:
                                break
                            body_end += 1
                        if body_end - i - 1 >= min_lines:
                            func_map[func_name].append({"product": product["name"], "file": str(py_file.relative_to(product["path"])), "line": i + 1})
                i += 1
    return [{"function": k, "products": list(set(l["product"] for l in v)), "locations": v} for k, v in func_map.items() if len(set(l["product"] for l in v)) >= 2]


def find_inline_hooks():
    products = _list_products()
    issues = []
    for product in products:
        pages_dir = product["path"] / "frontend" / "src" / "pages"
        if not pages_dir.exists():
            continue
        for tsx in _find_files(pages_dir, "*.tsx"):
            content = _read(tsx)
            if content and ("useQuery(" in content or "useMutation(" in content):
                issues.append({"product": product["name"], "file": str(tsx.relative_to(product["path"])), "severity": "warning"})
    return issues


# ── Dependency Audit ───────────────────────────────────

def audit_python_deps():
    products = _list_products()
    all_versions = defaultdict(list)
    root_req = _read(REPO_ROOT / "requirements.txt")
    if root_req:
        for pkg, ver in _parse_requirements(root_req).items():
            all_versions[pkg].append({"source": "root", "version": ver})
    for product in products:
        content = _read(product["path"] / "backend" / "requirements.txt")
        if content:
            for pkg, ver in _parse_requirements(content).items():
                all_versions[pkg].append({"source": product["name"], "version": ver})
    return [{"package": k, "versions": v} for k, v in all_versions.items() if len(set(x["version"] for x in v)) > 1]


def _parse_requirements(content):
    pkgs = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-e"):
            continue
        # Strip an INLINE comment (`pkg>=1.0  # why`) before parsing — pip does
        # the same. Without this the trailing comment was swallowed into the
        # version spec, so `anthropic>=0.40.0  # therapy` "mismatched" the clean
        # `anthropic>=0.40.0` in a product file (false dep-audit failure, 2026-05-31).
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.match(r'^([a-zA-Z0-9_-]+(?:\[[a-zA-Z0-9_,-]+\])?)\s*([>=<!=~]+.+)?$', line)
        if match:
            pkgs[match.group(1).split("[")[0].lower()] = match.group(2) or "any"
    return pkgs


# ── Test Coverage ──────────────────────────────────────

# ── Seed-architecture detection ─────────────────────────
#
# 🔴 THE ONE PLACE THAT ANSWERS "IS THIS A SEED-ARCHITECTURE PRODUCT?"
#
# Most fleet gates assume every product is built on the seed: a FastAPI backend
# installing `-e seed/*/backend`, a Vite frontend depending on `@noctusai/seed`.
# That held for 13 products and then stopped holding. `permutas` was absorbed
# 2026-09-04 as the legacy Permutas platform — Django 4.2 + DRF + Celery +
# create-react-app — consuming neither.
#
# The absorption was deliberate and CI knew it: `.github/workflows/test.yml`
# installed that product's requirements in its own step ("NOT the seed FastAPI
# stack, so its deps are deliberately absent from the root superset"), and the
# e2e jobs cover only `core` and `erp`. What was missing was telling the
# KEEPERS what CI had already decided — the gate↔methodology desync that
# reddened the whole matrix.
#
# 🔴 permutas itself was REVERTED off `dev` on 2026-09-06 (100 open
# HIGH/CRITICAL CVEs, 4 of them critical), so this predicate currently exempts
# NOTHING — every product is seed-architecture and `skipped_non_consumers` is
# empty. It is kept deliberately: it is correct on its own terms, it fails
# CLOSED, its negative cases are covered by tests, and the absorption is
# expected to return remediated. Deleting it would mean re-deriving the same
# rule under the same time pressure. Verify with
# `--check-framework-deps` — an empty skip list is the healthy state.
#
# 🔴 DERIVED, NEVER A SLUG LIST. A hand-listed exemption is the drift shape
# `check_hardcoded_product_slug_set` exists to catch, and it would go stale the
# day permutas migrates. This predicate flips on its own, because migrating IS
# the act of adding those dependencies.
SEED_FRONTEND_PACKAGE = "@noctusai/seed"
SEED_BACKEND_EDITABLES = ("seed/framework/backend", "seed/lib/backend")


def is_seed_architecture_product(product_path: Path) -> bool:
    """Does this product build on the noc seed (either half)?

    EITHER surface counts, deliberately: a product mid-migration may have
    adopted the seed on one side only, and a gate that demanded both would
    fire through the whole transition — exactly when it is least useful.

    Unknown/unreadable → True (fail-closed). A product this cannot classify
    keeps its full gate coverage; the exemption is never granted by accident.
    """
    pkg = product_path / "frontend" / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            if SEED_FRONTEND_PACKAGE in deps:
                return True
        except Exception:  # noqa: BLE001 — unreadable manifest: fail closed below
            return True

    req = product_path / "backend" / "requirements.txt"
    if req.exists():
        try:
            text = req.read_text(encoding="utf-8")
            if any(e in text for e in SEED_BACKEND_EDITABLES):
                return True
        except Exception:  # noqa: BLE001 — unreadable manifest: fail closed
            return True
        return False

    # No frontend manifest AND no backend requirements — cannot classify.
    return not pkg.exists()


def analyze_test_coverage():
    products = _list_products()
    issues = []
    matrix = []
    for product in products:
        tests_dir = product["path"] / "backend" / "tests"
        name = product["name"]
        if not tests_dir.exists():
            if (product["path"] / "backend" / "app" / "main.py").exists():
                issues.append({"product": name, "issue": "No tests directory", "severity": "critical"})
            matrix.append({"product": name, "routers": 0, "services": 0, "integration": 0, "e2e": False, "auth": False,
                       "seed_architecture": is_seed_architecture_product(product["path"])})
            continue

        rc = len(list(_find_files(tests_dir / "routers", "test_*.py")))
        sc = len(list(_find_files(tests_dir / "services", "test_*.py")))
        ic = len(list(_find_files(tests_dir / "integration", "test_*.py")))
        has_e2e = (tests_dir / "integration" / "test_e2e_flows.py").exists()
        has_auth = any("AuthBoundary" in (_read(f) or "") or "_401" in (_read(f) or "") for f in _find_files(tests_dir, "test_*.py"))

        services_dir = product["path"] / "backend" / "app" / "services"
        service_files = [f for f in _find_files(services_dir, "*.py") if f.stem != "__init__"] if services_dir.exists() else []
        if service_files and not sc:
            issues.append({"product": name, "issue": f"Has {len(service_files)} services but no service tests", "severity": "high"})
        if not ic:
            issues.append({"product": name, "issue": "No integration tests", "severity": "medium"})
        if not has_e2e:
            issues.append({"product": name, "issue": "No E2E tests", "severity": "medium"})

        matrix.append({"product": name, "routers": rc, "services": sc, "integration": ic, "e2e": has_e2e, "auth": has_auth,
                       # Reported, never used to hide a row — the gate that
                       # consumes this decides what to require of a
                       # non-seed-architecture product.
                       "seed_architecture": is_seed_architecture_product(product["path"])})

    return {"issues": issues, "matrix": matrix}


# ── Code Metrics ───────────────────────────────────────

def get_code_metrics():
    products = _list_products()
    metrics = []
    for product in products:
        backend = product["path"] / "backend" / "app"
        frontend = product["path"] / "frontend" / "src"
        bl = sum(len((_read(f) or "").splitlines()) for f in _find_files(backend, "*.py")) if backend.exists() else 0
        fl = sum(len((_read(f) or "").splitlines()) for f in _find_files(frontend, "*.tsx")) + sum(len((_read(f) or "").splitlines()) for f in _find_files(frontend, "*.ts")) if frontend.exists() else 0
        routers = [f.stem for f in (backend / "routers").glob("*.py") if f.stem != "__init__"] if (backend / "routers").exists() else []
        services = [f.stem for f in (backend / "services").glob("*.py") if f.stem != "__init__"] if (backend / "services").exists() else []
        pages = [f.stem for f in frontend.rglob("*.tsx") if "node_modules" not in str(f)] if (frontend / "pages").exists() else []
        hooks = [f.stem for f in (frontend / "hooks").glob("*.ts") if f.stem != "index"] if (frontend / "hooks").exists() else []
        metrics.append({"product": product["name"], "backend_lines": bl, "frontend_lines": fl, "routers": len(routers), "services": len(services), "pages": len(pages), "hooks": len(hooks)})
    return metrics


# ── Run All ────────────────────────────────────────────

def run_all_analyzers():
    return {
        "duplicated_functions": find_duplicated_functions(),
        "inline_hooks": find_inline_hooks(),
        "python_dep_mismatches": audit_python_deps(),
        "test_coverage": analyze_test_coverage(),
        "code_metrics": get_code_metrics(),
    }


_ANALYZE_KINDS: dict[str, callable] = {
    "patterns": lambda: {
        "duplicated": find_duplicated_functions(),
        "inline_hooks": find_inline_hooks(),
    },
    "deps": audit_python_deps,
    "tests": analyze_test_coverage,
    "all": run_all_analyzers,
}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.platform_metrics",
        description="Code metrics for all products: lines, routers, services, pages",
    )
    def _platform_metrics() -> dict:
        return get_code_metrics()

    @server.tool(
        name="noctus.dev.analyze",
        description="Run an analyzer. kind='all' / 'patterns' / 'deps' / 'tests'.",
    )
    def _analyze(kind: str = "all") -> dict:
        impl = _ANALYZE_KINDS.get(kind)
        if impl is None:
            return {"error": f"invalid kind {kind!r}; valid: {sorted(_ANALYZE_KINDS)}"}
        return impl()
