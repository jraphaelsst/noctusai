"""
Test Coverage Analyzer — checks that products meet the testing standard.

Every product needs: unit (routers), unit (services), integration, E2E,
and auth boundary tests.
"""
from pathlib import Path

from agents.shared.config import list_products
from agents.shared.repo import read_file, find_files


def analyze_test_coverage() -> list[dict]:
    """Check each product against the testing standard."""
    products = list_products()
    issues = []

    for product in products:
        name = product["name"]
        tests_dir = product["path"] / "backend" / "tests"

        if not tests_dir.exists():
            if product["has_backend"]:
                issues.append({
                    "product": name,
                    "issue": "No tests directory at all",
                    "severity": "critical",
                })
            continue

        # Check router tests
        router_tests = list(find_files(tests_dir / "routers", "test_*.py"))
        if not router_tests:
            issues.append({
                "product": name,
                "layer": "unit/routers",
                "issue": "No router unit tests",
                "severity": "high",
            })

        # Check service tests
        service_tests = list(find_files(tests_dir / "services", "test_*.py"))
        services_dir = product["path"] / "backend" / "app" / "services"
        service_files = list(find_files(services_dir, "*.py")) if services_dir.exists() else []
        service_files = [f for f in service_files if f.stem != "__init__"]

        if service_files and not service_tests:
            issues.append({
                "product": name,
                "layer": "unit/services",
                "issue": f"Has {len(service_files)} services but no service tests",
                "severity": "high",
            })

        # Check integration tests
        integration_tests = list(find_files(tests_dir / "integration", "test_*.py"))
        if not integration_tests:
            issues.append({
                "product": name,
                "layer": "integration",
                "issue": "No integration tests",
                "severity": "medium",
            })

        # Check E2E tests
        e2e_file = tests_dir / "integration" / "test_e2e_flows.py"
        if not e2e_file.exists():
            issues.append({
                "product": name,
                "layer": "e2e",
                "issue": "No E2E test file (test_e2e_flows.py)",
                "severity": "medium",
            })

        # Check auth boundary tests
        has_auth_boundary = False
        for test_file in find_files(tests_dir, "test_*.py"):
            content = read_file(test_file) or ""
            if "AuthBoundary" in content or "test_" in content and "_401" in content:
                has_auth_boundary = True
                break
        if not has_auth_boundary:
            issues.append({
                "product": name,
                "layer": "auth_boundary",
                "issue": "No auth boundary tests (401 validation)",
                "severity": "medium",
            })

    return issues


def get_test_matrix() -> list[dict]:
    """Generate a test coverage matrix for all products."""
    products = list_products()
    matrix = []

    for product in products:
        tests_dir = product["path"] / "backend" / "tests"
        if not tests_dir.exists():
            matrix.append({
                "product": product["name"],
                "routers": 0, "services": 0, "integration": 0,
                "e2e": False, "auth_boundary": False, "edge_cases": 0,
            })
            continue

        router_count = len(list(find_files(tests_dir / "routers", "test_*.py")))
        service_count = len(list(find_files(tests_dir / "services", "test_*.py")))
        integration_count = len(list(find_files(tests_dir / "integration", "test_*.py")))
        edge_count = len(list(find_files(tests_dir / "edge_cases", "test_*.py")))
        has_e2e = (tests_dir / "integration" / "test_e2e_flows.py").exists()

        has_auth = False
        for tf in find_files(tests_dir, "test_*.py"):
            content = read_file(tf) or ""
            if "AuthBoundary" in content or "_401" in content or "_no_auth" in content:
                has_auth = True
                break

        matrix.append({
            "product": product["name"],
            "routers": router_count,
            "services": service_count,
            "integration": integration_count,
            "e2e": has_e2e,
            "auth_boundary": has_auth,
            "edge_cases": edge_count,
        })

    return matrix


def run_all() -> dict:
    return {
        "test_issues": analyze_test_coverage(),
        "test_matrix": get_test_matrix(),
    }
