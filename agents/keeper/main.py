"""
Keeper — the platform's fixer and improver.

One agent, three capabilities:
  --validate   Check compliance (deterministic, fast, CI-safe)
  --heal       Fix loop: detect → auto-fix → verify → repeat until clean
  --discover   Find improvements, generate proposals (AI-powered)

Default (no flags): full pipeline — validate → heal → discover.

Usage:
  python -m agents.keeper                          # Full pipeline
  python -m agents.keeper --heal                   # Fix loop + discover
  python -m agents.keeper --heal --product mailing # Heal one product
  python -m agents.keeper --validate               # CI mode (fast, exit 1 on fail)
  python -m agents.keeper --discover               # Proposals only
  python -m agents.keeper --advisory               # Include AI advisory
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.shared.config import list_products
from agents.shared.models import is_ai_available
from agents.keeper.checks.seed_compliance import check_product
from agents.keeper.checks.path_references import check_path_references
from agents.keeper.checks.ai_advisory import run_advisory
from agents.keeper.fixes import fix_issue
from agents.keeper.analyzers import pattern_finder, dependency_audit, structure_analyzer, test_coverage
from agents.keeper.ai_brain import analyze_findings
from agents.keeper.proposer import generate_proposal, list_proposals

GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RED = "\033[91m"
MAGENTA = "\033[95m"
RESET = "\033[0m"
BOLD = "\033[1m"

MAX_HEAL_ITERATIONS = 10


# ── Validate ──────────────────────────────────────────────

def validate(products: list, include_advisory: bool = False) -> dict:
    """Check platform compliance. Returns {score, issues, advisory}."""
    all_issues = []
    scores = []

    print()
    print(f"  {BOLD}VALIDATE — compliance check{RESET}")
    print()

    for product in products:
        issues = []
        issues.extend(check_product(product["path"]))
        issues.extend(check_path_references(product["path"]))
        all_issues.extend(issues)

        penalties = {"critical": 25, "high": 10, "warning": 3}
        penalty = sum(penalties.get(i["severity"], 5) for i in issues)
        score = max(0, 100 - penalty)
        scores.append(score)

        status = f"{GREEN}PASS{RESET}" if score == 100 else f"{RED}FAIL{RESET}"
        print(f"    {product['name']:30s} {status}  {score}/100")
        for issue in issues:
            color = RED if issue["severity"] == "critical" else YELLOW
            print(f"      {color}[{issue['severity']}]{RESET} {issue['file']}: {issue['issue']}")

    platform_score = round(sum(scores) / len(scores)) if scores else 100
    print()
    print(f"    Score: {platform_score}/100  |  Issues: {len(all_issues)}")

    # AI advisory — non-deterministic → proposals
    advisory = []
    if include_advisory and is_ai_available():
        print()
        print(f"    {BOLD}AI Advisory{RESET}")
        advisory = run_advisory()
        for f in advisory:
            if f.get("type") == "compliant":
                print(f"    {GREEN}✓{RESET} {f['product']}")
            elif f.get("type") == "advisory":
                print(f"    {MAGENTA}→ Proposal:{RESET} {f.get('product', '')}: {f.get('issue', '')}")
                generate_proposal(
                    title=f"Advisory: {f.get('issue', '')[:60]}",
                    problem=f.get("issue", ""),
                    solution=f"Review per rule: {f.get('rule', 'unknown')}",
                    affected_products=[f.get("product", "unknown")],
                    severity="low", effort="low",
                )

    return {"score": platform_score, "issues": all_issues, "advisory": advisory}


# ── Heal ──────────────────────────────────────────────────

def heal(products: list, include_advisory: bool = False) -> dict:
    """Fix loop: detect → auto-fix deterministic → propose non-deterministic → repeat."""
    print()
    print(f"  {BOLD}HEAL — detect → fix → verify → repeat{RESET}")

    total_fixed = 0
    total_proposals = 0
    iteration = 0

    while iteration < MAX_HEAL_ITERATIONS:
        iteration += 1
        print()
        print(f"    {BLUE}── Iteration {iteration} ──{RESET}")
        print()

        all_issues = []
        for product in products:
            issues = []
            issues.extend(check_product(product["path"]))
            issues.extend(check_path_references(product["path"]))
            all_issues.extend(issues)

            penalties = {"critical": 25, "high": 10, "warning": 3}
            penalty = sum(penalties.get(i["severity"], 5) for i in issues)
            score = max(0, 100 - penalty)

            status = f"{GREEN}PASS{RESET}" if score == 100 else f"{RED}FAIL{RESET}"
            print(f"    {product['name']:30s} {status}  {score}/100")
            for issue in issues:
                color = RED if issue["severity"] == "critical" else YELLOW
                print(f"      {color}[{issue['severity']}]{RESET} {issue['file']}: {issue['issue']}")

        if not all_issues:
            print()
            print(f"    {GREEN}Clean — no issues.{RESET}")
            break

        fixed_this_round = 0
        for issue in all_issues:
            result = fix_issue(issue)
            if result["fixed"]:
                fixed_this_round += 1
                total_fixed += 1
                print(f"    {GREEN}✓ Fixed:{RESET} {issue['product']}/{issue['file']} — {result['action']}")
            else:
                print(f"    {YELLOW}→ Proposal:{RESET} {issue['product']}/{issue['file']} — {result['action']}")
                generate_proposal(
                    title=f"Fix: {issue.get('issue', '')[:60]}",
                    problem=issue.get("issue", ""),
                    solution="Requires manual review.",
                    affected_products=[issue.get("product", "unknown")],
                    severity=issue.get("severity", "medium"), effort="medium",
                )
                total_proposals += 1

        if fixed_this_round == 0:
            print()
            print(f"    {YELLOW}No more auto-fixes. Remaining issues → proposals.{RESET}")
            break

        print()
        print(f"    {BLUE}Re-verifying...{RESET}")

    # Final check
    print()
    print(f"    {BLUE}── Final ──{RESET}")
    print()
    final_issues = []
    final_scores = []
    for product in products:
        issues = []
        issues.extend(check_product(product["path"]))
        issues.extend(check_path_references(product["path"]))
        final_issues.extend(issues)
        penalties = {"critical": 25, "high": 10, "warning": 3}
        penalty = sum(penalties.get(i["severity"], 5) for i in issues)
        s = max(0, 100 - penalty)
        final_scores.append(s)
        status = f"{GREEN}PASS{RESET}" if s == 100 else f"{RED}FAIL{RESET}"
        print(f"    {product['name']:30s} {status}  {s}/100")

    final_score = round(sum(final_scores) / len(final_scores)) if final_scores else 100

    # AI advisory
    if include_advisory and is_ai_available():
        print()
        print(f"    {BOLD}AI Advisory (proposals){RESET}")
        for f in run_advisory():
            if f.get("type") == "advisory":
                print(f"    {MAGENTA}→{RESET} {f.get('product', '')}: {f.get('issue', '')}")
                generate_proposal(
                    title=f"Advisory: {f.get('issue', '')[:60]}",
                    problem=f.get("issue", ""),
                    solution=f"Review per rule: {f.get('rule', 'unknown')}",
                    affected_products=[f.get("product", "unknown")],
                    severity="low", effort="low",
                )
                total_proposals += 1

    print()
    print(f"    Healed: {total_fixed} auto-fixed, {total_proposals} proposals")
    print(f"    Final score: {final_score}/100")

    return {"score": final_score, "auto_fixed": total_fixed, "proposals_created": total_proposals}


# ── Discover ──────────────────────────────────────────────

def discover() -> dict:
    """Find improvements. All findings → proposals."""
    print()
    print(f"  {BOLD}DISCOVER — improvement analysis{RESET}")
    print()

    results = {}

    print(f"    {BLUE}Patterns...{RESET}", end=" ")
    results["patterns"] = pattern_finder.run_all()
    print(f"{len(results['patterns']['duplicated_functions'])} duplicates, {len(results['patterns']['inline_hooks'])} inline hooks")

    print(f"    {BLUE}Dependencies...{RESET}", end=" ")
    results["deps"] = dependency_audit.run_all()
    print(f"{len(results['deps']['python_inconsistencies'])} Python, {len(results['deps']['frontend_inconsistencies'])} frontend")

    print(f"    {BLUE}Structure...{RESET}", end=" ")
    results["structure"] = structure_analyzer.run_all()
    print(f"{len(results['structure']['structure_issues'])} issues")

    print(f"    {BLUE}Tests...{RESET}", end=" ")
    results["tests"] = test_coverage.run_all()
    print(f"{len(results['tests']['test_issues'])} gaps")

    # Metrics
    print()
    print(f"    {BOLD}Code:{RESET}")
    for m in results["structure"]["code_metrics"]:
        print(f"      {m['product']:<18} BE:{m['backend_lines']:<7} FE:{m['frontend_lines']:<7} R:{m['routers']:<3} S:{m['services']:<3} P:{m['pages']:<3} H:{m['hooks']}")

    # AI brain
    if is_ai_available():
        print()
        print(f"    {BLUE}AI analyzing...{RESET}")
        for p in analyze_findings(results):
            if p.get("type") == "proposal":
                print(f"    {GREEN}→{RESET} {p['title']} [{p['severity']}/{p['effort']}]")
            elif p.get("type") == "healthy":
                print(f"    {GREEN}Platform healthy{RESET}")

    pending = len([p for p in list_proposals() if p["status"] == "pending"])
    print()
    print(f"    Proposals: {pending} pending")

    return {"findings": results, "proposals": pending}


# ── Main ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Keeper — platform fixer and improver")
    parser.add_argument("--validate", action="store_true", help="Check compliance (CI mode)")
    parser.add_argument("--heal", action="store_true", help="Fix loop until clean, then discover")
    parser.add_argument("--discover", action="store_true", help="Find improvements, generate proposals")
    parser.add_argument("--advisory", action="store_true", help="Include AI advisory")
    parser.add_argument("--product", help="Scope to one product")
    args = parser.parse_args()

    products = list_products()
    if args.product:
        products = [p for p in products if p["name"] == args.product]
        if not products:
            print(f"Product '{args.product}' not found")
            sys.exit(1)

    # Default: full pipeline
    run_all = not args.validate and not args.heal and not args.discover

    print()
    print(f"{BOLD}╔══════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}║                    Keeper                               ║{RESET}")
    print(f"{BOLD}╚══════════════════════════════════════════════════════════╝{RESET}")

    result = {}

    if args.validate:
        result = validate(products, include_advisory=args.advisory)
    elif args.heal:
        result = heal(products, include_advisory=args.advisory)
        if result["score"] == 100:
            discover()
    elif args.discover:
        result = {"score": 100}
        discover()
    elif run_all:
        result = validate(products, include_advisory=args.advisory)
        if result["score"] == 100:
            discover()
        else:
            print(f"\n  {YELLOW}Run: python -m agents.keeper --heal{RESET}")

    # Summary
    print()
    print(f"{BOLD}{'─'*58}{RESET}")
    score = result.get("score", 100)
    color = GREEN if score == 100 else RED
    print(f"  Score:     {color}{score}/100{RESET}")
    if "auto_fixed" in result:
        print(f"  Healed:    {result['auto_fixed']} fixed, {result['proposals_created']} proposals")
    pending = len([p for p in list_proposals() if p["status"] == "pending"])
    print(f"  Proposals: {pending} pending")
    ai = f"{GREEN}active{RESET}" if is_ai_available() else f"{YELLOW}disabled (set OPENAI_API_KEY){RESET}"
    print(f"  AI:        {ai}")
    print(f"{BOLD}{'─'*58}{RESET}")
    print()

    sys.exit(0 if score == 100 else 1)


if __name__ == "__main__":
    main()
