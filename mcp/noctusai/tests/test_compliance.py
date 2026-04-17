"""Tests for compliance checks."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.compliance import check_seed_compliance, check_path_references, check_all_products

REPO_ROOT = Path(__file__).resolve().parents[3]
PRODUCTS_DIR = REPO_ROOT / "products"


class TestSeedCompliance:
    def test_seed_product_is_compliant(self):
        issues = check_seed_compliance(PRODUCTS_DIR / "seed")
        assert len(issues) == 0, f"Seed has issues: {issues}"

    def test_mailing_is_compliant(self):
        issues = check_seed_compliance(PRODUCTS_DIR / "mailing")
        assert len(issues) == 0, f"Mailing has issues: {issues}"

    def test_all_products_compliant(self):
        score, issues = check_all_products()
        assert score == 100, f"Platform score {score}/100, issues: {issues}"

    def test_detects_boilerplate_router(self):
        """If a product had its own health.py, compliance would flag it."""
        # Create a temporary health.py
        health_file = PRODUCTS_DIR / "seed" / "backend" / "app" / "routers" / "health.py"
        health_file.write_text("# test")
        try:
            issues = check_seed_compliance(PRODUCTS_DIR / "seed")
            health_issues = [i for i in issues if "health.py" in i.get("file", "")]
            assert len(health_issues) > 0, "Should detect boilerplate health.py"
        finally:
            health_file.unlink()  # cleanup


class TestPathReferences:
    def test_no_old_shared_paths(self):
        for d in sorted(PRODUCTS_DIR.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            issues = check_path_references(d)
            assert len(issues) == 0, f"{d.name} has old paths: {issues}"
