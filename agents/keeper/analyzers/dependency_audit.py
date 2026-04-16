"""
Dependency Audit — checks for outdated or inconsistent dependencies.

Scans all requirements.txt and package.json files for:
- Version inconsistencies across products (e.g. FastAPI 0.115.0 in one, 0.114.0 in another)
- Packages missing from the root requirements.txt
- Frontend packages with mismatched versions
"""
import re
from pathlib import Path
from collections import defaultdict

from agents.shared.config import REPO_ROOT, list_products
from agents.shared.repo import read_file


def parse_requirements(content: str) -> dict[str, str]:
    """Parse a requirements.txt into {package: version_spec}."""
    packages = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-e"):
            continue
        match = re.match(r'^([a-zA-Z0-9_-]+(?:\[[a-zA-Z0-9_,-]+\])?)\s*([>=<!=~]+.+)?$', line)
        if match:
            name = match.group(1).split("[")[0].lower()
            version = match.group(2) or "any"
            packages[name] = version
    return packages


def audit_python_deps() -> list[dict]:
    """Check Python dependency consistency across all products."""
    products = list_products()
    all_versions = defaultdict(list)
    issues = []

    # Root requirements
    root_req = read_file(REPO_ROOT / "requirements.txt")
    if root_req:
        root_packages = parse_requirements(root_req)
        for pkg, ver in root_packages.items():
            all_versions[pkg].append({"source": "root", "version": ver})

    # Product requirements
    for product in products:
        req_file = product["path"] / "backend" / "requirements.txt"
        content = read_file(req_file)
        if not content:
            continue
        packages = parse_requirements(content)
        for pkg, ver in packages.items():
            all_versions[pkg].append({"source": product["name"], "version": ver})

    # Find inconsistencies
    for pkg, versions in all_versions.items():
        unique_versions = set(v["version"] for v in versions)
        if len(unique_versions) > 1:
            issues.append({
                "package": pkg,
                "type": "version_mismatch",
                "versions": versions,
                "suggestion": f"'{pkg}' has {len(unique_versions)} different version specs — standardize in root requirements.txt",
                "severity": "warning",
            })

    return issues


def audit_frontend_deps() -> list[dict]:
    """Check frontend dependency consistency across products."""
    products = list_products()
    all_versions = defaultdict(list)
    issues = []

    for product in products:
        pkg_json = product["path"] / "frontend" / "package.json"
        content = read_file(pkg_json)
        if not content:
            continue

        import json
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            continue

        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        for pkg, ver in deps.items():
            all_versions[pkg].append({"source": product["name"], "version": ver})

    for pkg, versions in all_versions.items():
        unique_versions = set(v["version"] for v in versions)
        if len(unique_versions) > 1:
            issues.append({
                "package": pkg,
                "type": "version_mismatch",
                "versions": versions,
                "suggestion": f"Frontend '{pkg}' has {len(unique_versions)} different versions — standardize",
                "severity": "warning",
            })

    return issues


def check_missing_seed_deps() -> list[dict]:
    """Check if products reference seed packages correctly."""
    products = list_products()
    issues = []

    for product in products:
        req_file = product["path"] / "backend" / "requirements.txt"
        content = read_file(req_file)
        if not content:
            continue

        if "seed/backend/lib" not in content:
            issues.append({
                "product": product["name"],
                "type": "missing_seed_lib",
                "suggestion": "Missing -e seed/backend/lib in requirements.txt",
                "severity": "high",
            })
        if "seed/backend/framework" not in content:
            issues.append({
                "product": product["name"],
                "type": "missing_seed_framework",
                "suggestion": "Missing -e seed/backend/framework in requirements.txt",
                "severity": "high",
            })

    return issues


def run_all() -> dict:
    return {
        "python_inconsistencies": audit_python_deps(),
        "frontend_inconsistencies": audit_frontend_deps(),
        "missing_seed_deps": check_missing_seed_deps(),
    }
