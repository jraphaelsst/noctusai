"""
Seed Lab — discovers improvements and generates proposals.

Usage:
  python -m agents.lab                          # Full analysis
  python -m agents.lab --analyze patterns       # Single analyzer
  python -m agents.lab --analyze deps           # Dependency audit
  python -m agents.lab --analyze structure      # Structure analysis
  python -m agents.lab --proposals              # List proposals

Analyzers discover issues. The proposer turns them into actionable
improvement proposals saved to agents/lab/proposals/.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.lab.analyzers import pattern_finder, dependency_audit, structure_analyzer
from agents.lab.proposer import generate_proposal, list_proposals

GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"


def run_patterns():
    """Run pattern finder and generate proposals for significant findings."""
    print(f"\n{BLUE}--- Pattern Analysis ---{RESET}\n")
    results = pattern_finder.run_all()

    # Duplicated functions
    dups = results["duplicated_functions"]
    if dups:
        print(f"  {YELLOW}Duplicated functions across products:{RESET}")
        for d in dups[:10]:
            print(f"    {d['function']} — in {', '.join(d['products'])}")
        if len(dups) > 3:
            generate_proposal(
                title="Extract duplicated functions to seed lib",
                problem=f"{len(dups)} functions appear in multiple products with similar signatures.",
                solution="Review each function and extract to noctusai_lib if it's truly shared logic.",
                affected_products=list(set(p for d in dups for p in d["products"])),
                severity="medium",
                effort="medium",
                findings=dups[:10],
            )
            print(f"    {GREEN}→ Proposal generated{RESET}")
    else:
        print(f"  {GREEN}No significant duplication found{RESET}")

    # Inline hooks
    hooks = results["inline_hooks"]
    if hooks:
        print(f"\n  {YELLOW}Inline hooks in pages (should be in dedicated files):{RESET}")
        for h in hooks:
            print(f"    {h['product']}: {h['file']}")
        generate_proposal(
            title="Extract inline hooks to dedicated files",
            problem=f"{len(hooks)} pages have TanStack Query hooks inlined instead of in dedicated hook files.",
            solution="Extract useQuery/useMutation calls from page components into hooks/ directory files.",
            affected_products=list(set(h["product"] for h in hooks)),
            severity="low",
            effort="low",
            findings=hooks,
        )
        print(f"    {GREEN}→ Proposal generated{RESET}")
    else:
        print(f"  {GREEN}All hooks in dedicated files{RESET}")

    # Similar services
    services = results["similar_services"]
    if services:
        print(f"\n  {YELLOW}Common service methods across products:{RESET}")
        for s in services[:5]:
            print(f"    {s['method']} — in {s['count']} products")

    return results


def run_deps():
    """Run dependency audit and generate proposals for issues."""
    print(f"\n{BLUE}--- Dependency Audit ---{RESET}\n")
    results = dependency_audit.run_all()

    py = results["python_inconsistencies"]
    if py:
        print(f"  {YELLOW}Python version mismatches:{RESET}")
        for issue in py[:10]:
            versions = set(v["version"] for v in issue["versions"])
            print(f"    {issue['package']}: {', '.join(versions)}")
        generate_proposal(
            title="Standardize Python dependency versions",
            problem=f"{len(py)} packages have inconsistent versions across products.",
            solution="Pin all shared dependencies in root requirements.txt. Products inherit.",
            affected_products=["all"],
            severity="medium",
            effort="low",
            findings=py[:10],
        )
        print(f"    {GREEN}→ Proposal generated{RESET}")
    else:
        print(f"  {GREEN}Python deps consistent{RESET}")

    fe = results["frontend_inconsistencies"]
    if fe:
        print(f"\n  {YELLOW}Frontend version mismatches:{RESET}")
        for issue in fe[:10]:
            versions = set(v["version"] for v in issue["versions"])
            print(f"    {issue['package']}: {', '.join(versions)}")
    else:
        print(f"  {GREEN}Frontend deps consistent{RESET}")

    missing = results["missing_seed_deps"]
    if missing:
        print(f"\n  {RED}Missing seed dependencies:{RESET}")
        for m in missing:
            print(f"    {m['product']}: {m['suggestion']}")
    else:
        print(f"  {GREEN}All products reference seed packages{RESET}")

    return results


def run_structure():
    """Run structure analysis."""
    print(f"\n{BLUE}--- Structure Analysis ---{RESET}\n")
    results = structure_analyzer.run_all()

    issues = results["structure_issues"]
    if issues:
        print(f"  {YELLOW}Structure issues:{RESET}")
        for issue in issues:
            color = RED if issue["severity"] == "critical" else YELLOW
            print(f"    {color}[{issue['severity']}]{RESET} {issue['product']}: {issue['issue']}")
    else:
        print(f"  {GREEN}All products structurally compliant{RESET}")

    print(f"\n  {BOLD}Code Metrics:{RESET}")
    metrics = results["code_metrics"]
    print(f"  {'Product':<20} {'Backend':<10} {'Frontend':<10} {'Routers':<9} {'Services':<9} {'Pages':<7} {'Hooks':<7}")
    print(f"  {'─'*20} {'─'*10} {'─'*10} {'─'*9} {'─'*9} {'─'*7} {'─'*7}")
    for m in metrics:
        print(f"  {m['product']:<20} {m['backend_lines']:<10} {m['frontend_lines']:<10} {m['routers']:<9} {m['services']:<9} {m['pages']:<7} {m['hooks']:<7}")

    return results


def show_proposals():
    """List existing proposals."""
    print(f"\n{BLUE}--- Proposals ---{RESET}\n")
    proposals = list_proposals()
    if not proposals:
        print(f"  {GREEN}No proposals yet{RESET}")
        return

    for p in proposals:
        status_color = GREEN if p["status"] == "accepted" else YELLOW if p["status"] == "pending" else RED
        print(f"  {status_color}[{p['status']}]{RESET} {p['file']}")


def main():
    parser = argparse.ArgumentParser(description="Seed Lab — discover improvements")
    parser.add_argument("--analyze", choices=["patterns", "deps", "structure"], help="Run specific analyzer")
    parser.add_argument("--proposals", action="store_true", help="List proposals")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  Seed Lab — Platform Improvement Analysis")
    print("=" * 60)

    if args.proposals:
        show_proposals()
        print()
        return

    results = {}

    if args.analyze == "patterns" or not args.analyze:
        results["patterns"] = run_patterns()
    if args.analyze == "deps" or not args.analyze:
        results["deps"] = run_deps()
    if args.analyze == "structure" or not args.analyze:
        results["structure"] = run_structure()

    # Summary
    proposals = list_proposals()
    pending = len([p for p in proposals if p["status"] == "pending"])

    print()
    print("-" * 60)
    print(f"  Analysis complete  |  Proposals: {pending} pending")
    print("-" * 60)
    print()

    if args.json:
        print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
