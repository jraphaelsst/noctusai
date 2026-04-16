"""
Seed Guardian — validates seed compliance across all products.

Usage:
  python -m agents.guardian                          # Full check
  python -m agents.guardian --product mailing        # Single product
  python -m agents.guardian --check seed_compliance  # Single check

Exit code 0 = all clear, 1 = issues found.
"""
import argparse
import json
import sys
from pathlib import Path

# Add repo root to path so we can import agents.shared
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.shared.config import list_products, PRODUCTS_DIR
from agents.guardian.checks.seed_compliance import check_product
from agents.guardian.checks.path_references import check_path_references

SEVERITY_COLORS = {
    "critical": "\033[91m",  # red
    "high": "\033[93m",      # yellow
    "warning": "\033[94m",   # blue
}
RESET = "\033[0m"
GREEN = "\033[92m"


def run_checks(product_path: Path, checks: list[str] = None) -> list[dict]:
    """Run selected checks on a product."""
    issues = []
    all_checks = checks or ["seed_compliance", "path_references"]

    if "seed_compliance" in all_checks:
        issues.extend(check_product(product_path))
    if "path_references" in all_checks:
        issues.extend(check_path_references(product_path))

    return issues


def calculate_score(issues: list[dict]) -> int:
    """Calculate health score 0-100 based on issues."""
    if not issues:
        return 100
    penalties = {"critical": 25, "high": 10, "warning": 3}
    penalty = sum(penalties.get(i["severity"], 5) for i in issues)
    return max(0, 100 - penalty)


def main():
    parser = argparse.ArgumentParser(description="Seed Guardian — validate seed compliance")
    parser.add_argument("--product", help="Check a single product")
    parser.add_argument("--check", help="Run a specific check only")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    args = parser.parse_args()

    products = list_products()
    if args.product:
        products = [p for p in products if p["name"] == args.product]
        if not products:
            print(f"Product '{args.product}' not found")
            sys.exit(1)

    checks = [args.check] if args.check else None
    report = {"products": [], "total_issues": 0, "platform_score": 0}
    all_issues = []

    print()
    print("=" * 60)
    print("  Seed Guardian — Platform Health Check")
    print("=" * 60)
    print()

    for product in products:
        issues = run_checks(product["path"], checks)
        score = calculate_score(issues)
        all_issues.extend(issues)

        report["products"].append({
            "name": product["name"],
            "score": score,
            "issues": issues,
        })

        # Console output
        status = f"{GREEN}PASS{RESET}" if score == 100 else f"{SEVERITY_COLORS['critical']}FAIL{RESET}"
        print(f"  {product['name']:30s} {status}  score: {score}/100")

        for issue in issues:
            color = SEVERITY_COLORS.get(issue["severity"], "")
            print(f"    {color}[{issue['severity']:8s}]{RESET} {issue['file']}: {issue['issue']}")

    report["total_issues"] = len(all_issues)
    scores = [p["score"] for p in report["products"]]
    report["platform_score"] = round(sum(scores) / len(scores)) if scores else 100

    print()
    print("-" * 60)
    print(f"  Platform score: {report['platform_score']}/100  |  Issues: {len(all_issues)}")
    print("-" * 60)
    print()

    if args.json:
        print(json.dumps(report, indent=2, default=str))

    sys.exit(0 if len(all_issues) == 0 else 1)


if __name__ == "__main__":
    main()
