"""
NoctusAI Seed Agents — Orchestrated pipeline.

Single entry point that runs Guardian → Scientist in the correct order.
Guardian validates first. If the platform is healthy, Scientist discovers
improvements. If Guardian fails, Scientist is skipped — fix the
foundation before looking for improvements.

Usage:
  python -m agents                  # Full pipeline: Guardian → Scientist
  python -m agents --guardian       # Guardian only
  python -m agents --scientist      # Scientist only (skip Guardian gate)
  python -m agents --advisory       # Include Guardian AI advisory
  python -m agents --json           # JSON output
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.shared.config import list_products
from agents.shared.models import is_ai_available
from agents.guardian.checks.seed_compliance import check_product
from agents.guardian.checks.path_references import check_path_references
from agents.guardian.checks.ai_advisory import run_advisory
from agents.scientist.analyzers import pattern_finder, dependency_audit, structure_analyzer, test_coverage
from agents.scientist.ai_brain import analyze_findings
from agents.scientist.proposer import list_proposals

GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RED = "\033[91m"
MAGENTA = "\033[95m"
RESET = "\033[0m"
BOLD = "\033[1m"


def run_guardian(include_advisory: bool = False) -> dict:
    """Run Guardian — returns {score, issues, advisory}."""
    products = list_products()
    all_issues = []
    product_scores = []

    print()
    print(f"  {BOLD}{'='*56}{RESET}")
    print(f"  {BOLD}  GUARDIAN — Platform Health Check{RESET}")
    print(f"  {BOLD}{'='*56}{RESET}")
    print()

    for product in products:
        issues = []
        issues.extend(check_product(product["path"]))
        issues.extend(check_path_references(product["path"]))
        all_issues.extend(issues)

        penalties = {"critical": 25, "high": 10, "warning": 3}
        penalty = sum(penalties.get(i["severity"], 5) for i in issues)
        score = max(0, 100 - penalty)
        product_scores.append(score)

        status = f"{GREEN}PASS{RESET}" if score == 100 else f"{RED}FAIL{RESET}"
        print(f"  {product['name']:30s} {status}  {score}/100")
        for issue in issues:
            color = RED if issue["severity"] == "critical" else YELLOW
            print(f"    {color}[{issue['severity']}]{RESET} {issue['file']}: {issue['issue']}")

    platform_score = round(sum(product_scores) / len(product_scores)) if product_scores else 100
    print()
    print(f"  Platform score: {platform_score}/100  |  Issues: {len(all_issues)}")

    # AI advisory
    advisory = []
    if include_advisory and is_ai_available():
        print()
        print(f"  {BOLD}AI Advisory{RESET}")
        print()
        advisory = run_advisory()
        for f in advisory:
            if f.get("type") == "compliant":
                print(f"  {GREEN}✓{RESET} {f['product']}")
            elif f.get("type") == "advisory":
                print(f"  {MAGENTA}[advisory]{RESET} {f.get('product', '')}: {f.get('issue', '')}")

    print()
    return {"score": platform_score, "issues": all_issues, "advisory": advisory}


def run_scientist() -> dict:
    """Run Scientist — returns {findings, proposals}."""
    print(f"  {BOLD}{'='*56}{RESET}")
    print(f"  {BOLD}  SCIENTIST — Improvement Discovery{RESET}")
    print(f"  {BOLD}{'='*56}{RESET}")
    print()

    # File analyzers
    results = {}

    print(f"  {BLUE}Patterns...{RESET}", end=" ")
    results["patterns"] = pattern_finder.run_all()
    dups = len(results["patterns"]["duplicated_functions"])
    hooks = len(results["patterns"]["inline_hooks"])
    print(f"{dups} duplicated functions, {hooks} inline hooks")

    print(f"  {BLUE}Dependencies...{RESET}", end=" ")
    results["deps"] = dependency_audit.run_all()
    py_issues = len(results["deps"]["python_inconsistencies"])
    fe_issues = len(results["deps"]["frontend_inconsistencies"])
    print(f"{py_issues} Python mismatches, {fe_issues} frontend mismatches")

    print(f"  {BLUE}Structure...{RESET}", end=" ")
    results["structure"] = structure_analyzer.run_all()
    struct_issues = len(results["structure"]["structure_issues"])
    print(f"{struct_issues} issues")

    print(f"  {BLUE}Test coverage...{RESET}", end=" ")
    results["tests"] = test_coverage.run_all()
    test_issues = len(results["tests"]["test_issues"])
    print(f"{test_issues} gaps")

    # Code metrics
    print()
    print(f"  {BOLD}Code Metrics:{RESET}")
    for m in results["structure"]["code_metrics"]:
        print(f"    {m['product']:<20} BE:{m['backend_lines']:<8} FE:{m['frontend_lines']:<8} R:{m['routers']:<4} S:{m['services']:<4} P:{m['pages']:<4} H:{m['hooks']}")

    # AI brain
    ai_proposals = []
    if is_ai_available():
        print()
        print(f"  {BLUE}AI brain analyzing findings...{RESET}")
        ai_proposals = analyze_findings(results)
        for p in ai_proposals:
            if p.get("type") == "proposal":
                print(f"  {GREEN}→{RESET} {p['title']} [{p['severity']}/{p['effort']}]")
            elif p.get("type") == "healthy":
                print(f"  {GREEN}Platform healthy — no AI proposals{RESET}")

    # Proposals summary
    proposals = list_proposals()
    pending = len([p for p in proposals if p["status"] == "pending"])
    print()
    print(f"  Proposals: {pending} pending")

    return {"findings": results, "ai_proposals": ai_proposals, "proposal_count": pending}


def main():
    parser = argparse.ArgumentParser(description="NoctusAI Seed Agents — orchestrated pipeline")
    parser.add_argument("--guardian", action="store_true", help="Run Guardian only")
    parser.add_argument("--scientist", action="store_true", help="Run Scientist only (skip Guardian gate)")
    parser.add_argument("--advisory", action="store_true", help="Include Guardian AI advisory")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    print()
    print(f"{BOLD}╔══════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}║          NoctusAI Seed Agents — Full Pipeline           ║{RESET}")
    print(f"{BOLD}╚══════════════════════════════════════════════════════════╝{RESET}")

    # Determine what to run
    run_g = args.guardian or (not args.guardian and not args.scientist)
    run_s = args.scientist or (not args.guardian and not args.scientist)

    guardian_result = None
    scientist_result = None

    # Step 1: Guardian
    if run_g:
        guardian_result = run_guardian(include_advisory=args.advisory)

    # Step 2: Scientist (gated by Guardian)
    if run_s:
        if guardian_result and guardian_result["score"] < 100:
            print(f"  {RED}Guardian score {guardian_result['score']}/100 — fix issues before running Scientist{RESET}")
            print(f"  {YELLOW}Scientist skipped. Run 'python -m agents --scientist' to force.{RESET}")
            print()
        else:
            scientist_result = run_scientist()

    # Final summary
    print()
    print(f"{BOLD}{'─'*58}{RESET}")
    if guardian_result:
        score = guardian_result["score"]
        color = GREEN if score == 100 else RED
        print(f"  Guardian:  {color}{score}/100{RESET}")
    if scientist_result:
        print(f"  Scientist: {scientist_result['proposal_count']} proposals pending")
    ai_status = f"{GREEN}active{RESET}" if is_ai_available() else f"{YELLOW}disabled (set OPENAI_API_KEY){RESET}"
    print(f"  AI:        {ai_status}")
    print(f"{BOLD}{'─'*58}{RESET}")
    print()

    # Exit code: Guardian fail = exit 1
    if guardian_result and guardian_result["score"] < 100:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
