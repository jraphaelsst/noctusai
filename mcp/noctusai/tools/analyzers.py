"""Code analyzers — migrated from agents/keeper/analyzers/.

Discovers patterns, dependency issues, structure gaps, and test coverage.
"""
import re
import json
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parents[3]
PRODUCTS_DIR = REPO_ROOT / "products"


def _list_products():
    results = []
    for d in sorted(PRODUCTS_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            results.append({"name": d.name, "path": d})
    return results


def _read(path):
    try:
        return path.read_text(encoding="utf-8")
    except:
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
        match = re.match(r'^([a-zA-Z0-9_-]+(?:\[[a-zA-Z0-9_,-]+\])?)\s*([>=<!=~]+.+)?$', line)
        if match:
            pkgs[match.group(1).split("[")[0].lower()] = match.group(2) or "any"
    return pkgs


# ── Test Coverage ──────────────────────────────────────

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
            matrix.append({"product": name, "routers": 0, "services": 0, "integration": 0, "e2e": False, "auth": False})
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

        matrix.append({"product": name, "routers": rc, "services": sc, "integration": ic, "e2e": has_e2e, "auth": has_auth})

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
