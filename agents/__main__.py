"""
NoctusAI Seed Agents — Orchestrated pipeline.

Single entry point: Guardian → Scientist. Guardian gates Scientist.

Heal mode (--heal): auto-fix deterministic issues in a loop until clean.
Non-deterministic findings become proposals for human review.

Usage:
  python -m agents                          # Full pipeline
  python -m agents --heal                   # Fix loop: detect → fix → verify → repeat
  python -m agents --heal --product mailing # Heal a specific product
  python -m agents --guardian               # Guardian only
  python -m agents --scientist              # Scientist only
  python -m agents --advisory               # Include AI advisory
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
from agents.guardian.fixes import fix_issue
from agents.scientist.analyzers import pattern_finder, dependency_audit, structure_analyzer, test_coverage
from agents.scientist.ai_brain import analyze_findings
from agents.scientist.proposer import generate_proposal, list_proposals

GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RED = "\033[91m"
MAGENTA = "\033[95m"
RESET = "\033[0m"
BOLD = "\033[1m"

MAX_HEAL_ITERATIONS = 10


# ── Guardian ──────────────────────────────────────────────

def run_guardian_checks(products: list) -> tuple[int, list]:
    """Run Guardian hard checks. Returns (score, issues)."""
    all_issues = []
    scores = []

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
    return platform_score, all_issues


def run_guardian(products: list, include_advisory: bool = False) -> dict:
    """Run Guardian with output formatting."""
    print()
    print(f"  {BOLD}{'='*56}{RESET}")
    print(f"  {BOLD}  GUARDIAN — Platform Health Check{RESET}")
    print(f"  {BOLD}{'='*56}{RESET}")
    print()

    score, issues = run_guardian_checks(products)
    print()
    print(f"    Platform score: {score}/100  |  Issues: {len(issues)}")

    advisory = []
    if include_advisory and is_ai_available():
        print()
        print(f"    {BOLD}AI Advisory{RESET}")
        advisory = run_advisory()
        for f in advisory:
            if f.get("type") == "compliant":
                print(f"    {GREEN}✓{RESET} {f['product']}")
            elif f.get("type") == "advisory":
                print(f"    {MAGENTA}[advisory]{RESET} {f.get('product', '')}: {f.get('issue', '')}")
                # Non-deterministic → create proposal
                generate_proposal(
                    title=f"Advisory: {f.get('issue', '')[:60]}",
                    problem=f.get("issue", ""),
                    solution=f"Review and fix per CLAUDE.md rule: {f.get('rule', 'unknown')}",
                    affected_products=[f.get("product", "unknown")],
                    severity="low",
                    effort="low",
                )

    print()
    return {"score": score, "issues": issues, "advisory": advisory}


# ── Heal Loop ─────────────────────────────────────────────

def heal(products: list, include_advisory: bool = False) -> dict:
    """Detect → fix → verify → repeat until clean.

    Deterministic issues: auto-fixed.
    Non-deterministic issues: proposals created.
    """
    print()
    print(f"  {BOLD}{'='*56}{RESET}")
    print(f"  {BOLD}  HEAL MODE — detect → fix → verify → repeat{RESET}")
    print(f"  {BOLD}{'='*56}{RESET}")

    total_fixed = 0
    total_proposals = 0
    iteration = 0

    while iteration < MAX_HEAL_ITERATIONS:
        iteration += 1
        print()
        print(f"    {BLUE}── Iteration {iteration} ──{RESET}")
        print()

        # Detect
        score, issues = run_guardian_checks(products)

        if not issues:
            print()
            print(f"    {GREEN}Clean — no issues found.{RESET}")
            break

        # Separate deterministic (fixable) from non-deterministic
        fixed_this_round = 0
        unfixable = []

        for issue in issues:
            result = fix_issue(issue)
            if result["fixed"]:
                fixed_this_round += 1
                total_fixed += 1
                print(f"    {GREEN}✓ Fixed:{RESET} {issue['product']}/{issue['file']} — {result['action']}")
            else:
                unfixable.append(issue)
                print(f"    {YELLOW}→ Proposal:{RESET} {issue['product']}/{issue['file']} — {result['action']}")

        # Create proposals for unfixable issues
        for issue in unfixable:
            generate_proposal(
                title=f"Fix: {issue.get('issue', '')[:60]}",
                problem=issue.get("issue", ""),
                solution="Requires manual review — deterministic fix not available.",
                affected_products=[issue.get("product", "unknown")],
                severity=issue.get("severity", "medium"),
                effort="medium",
            )
            total_proposals += 1

        if fixed_this_round == 0:
            # Nothing was fixed this round — remaining issues need proposals
            print()
            print(f"    {YELLOW}No more auto-fixes available. {len(unfixable)} proposals created.{RESET}")
            break

        # Re-run to verify fixes
        print()
        print(f"    {BLUE}Re-verifying after {fixed_this_round} fixes...{RESET}")

    # Final verification
    print()
    print(f"    {BLUE}── Final Check ──{RESET}")
    print()
    final_score, final_issues = run_guardian_checks(products)

    # AI advisory — non-deterministic findings become proposals
    if include_advisory and is_ai_available():
        print()
        print(f"    {BOLD}AI Advisory (proposals only){RESET}")
        advisory = run_advisory()
        for f in advisory:
            if f.get("type") == "advisory":
                print(f"    {MAGENTA}→ Proposal:{RESET} {f.get('product', '')}: {f.get('issue', '')}")
                generate_proposal(
                    title=f"Advisory: {f.get('issue', '')[:60]}",
                    problem=f.get("issue", ""),
                    solution=f"Review per CLAUDE.md rule: {f.get('rule', 'unknown')}",
                    affected_products=[f.get("product", "unknown")],
                    severity="low",
                    effort="low",
                )
                total_proposals += 1

    print()
    print(f"    {BOLD}Heal summary:{RESET}")
    print(f"      Iterations:  {iteration}")
    print(f"      Auto-fixed:  {total_fixed}")
    print(f"      Proposals:   {total_proposals}")
    print(f"      Final score: {final_score}/100")

    return {
        "score": final_score,
        "iterations": iteration,
        "auto_fixed": total_fixed,
        "proposals_created": total_proposals,
        "remaining_issues": final_issues,
    }


# ── Scientist ─────────────────────────────────────────────

def run_scientist() -> dict:
    """Run Scientist — all findings become proposals, never auto-fix."""
    print()
    print(f"  {BOLD}{'='*56}{RESET}")
    print(f"  {BOLD}  SCIENTIST — Improvement Discovery{RESET}")
    print(f"  {BOLD}{'='*56}{RESET}")
    print()

    results = {}

    print(f"    {BLUE}Patterns...{RESET}", end=" ")
    results["patterns"] = pattern_finder.run_all()
    dups = len(results["patterns"]["duplicated_functions"])
    hooks = len(results["patterns"]["inline_hooks"])
    print(f"{dups} duplicated functions, {hooks} inline hooks")

    print(f"    {BLUE}Dependencies...{RESET}", end=" ")
    results["deps"] = dependency_audit.run_all()
    py = len(results["deps"]["python_inconsistencies"])
    fe = len(results["deps"]["frontend_inconsistencies"])
    print(f"{py} Python mismatches, {fe} frontend mismatches")

    print(f"    {BLUE}Structure...{RESET}", end=" ")
    results["structure"] = structure_analyzer.run_all()
    si = len(results["structure"]["structure_issues"])
    print(f"{si} issues")

    print(f"    {BLUE}Test coverage...{RESET}", end=" ")
    results["tests"] = test_coverage.run_all()
    ti = len(results["tests"]["test_issues"])
    print(f"{ti} gaps")

    # Code metrics
    print()
    print(f"    {BOLD}Code Metrics:{RESET}")
    for m in results["structure"]["code_metrics"]:
        print(f"      {m['product']:<20} BE:{m['backend_lines']:<8} FE:{m['frontend_lines']:<8} R:{m['routers']:<4} S:{m['services']:<4} P:{m['pages']:<4} H:{m['hooks']}")

    # AI brain — findings become proposals
    if is_ai_available():
        print()
        print(f"    {BLUE}AI brain analyzing...{RESET}")
        ai_proposals = analyze_findings(results)
        for p in ai_proposals:
            if p.get("type") == "proposal":
                print(f"    {GREEN}→ Proposal:{RESET} {p['title']} [{p['severity']}/{p['effort']}]")
            elif p.get("type") == "healthy":
                print(f"    {GREEN}Platform healthy — no AI proposals{RESET}")

    proposals = list_proposals()
    pending = len([p for p in proposals if p["status"] == "pending"])
    print()
    print(f"    Proposals: {pending} pending")

    return {"findings": results, "proposal_count": pending}


# ── Main ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NoctusAI Seed Agents")
    parser.add_argument("--heal", action="store_true", help="Heal mode: detect → fix → verify → repeat until clean")
    parser.add_argument("--guardian", action="store_true", help="Guardian only")
    parser.add_argument("--scientist", action="store_true", help="Scientist only (skip Guardian gate)")
    parser.add_argument("--advisory", action="store_true", help="Include AI advisory")
    parser.add_argument("--product", help="Scope to a single product")
    args = parser.parse_args()

    products = list_products()
    if args.product:
        products = [p for p in products if p["name"] == args.product]
        if not products:
            print(f"Product '{args.product}' not found")
            sys.exit(1)

    print()
    print(f"{BOLD}╔══════════════════════════════════════════════════════════╗{RESET}")
    if args.heal:
        print(f"{BOLD}║     NoctusAI Agents — Heal Mode                        ║{RESET}")
    else:
        print(f"{BOLD}║     NoctusAI Agents — Full Pipeline                     ║{RESET}")
    print(f"{BOLD}╚══════════════════════════════════════════════════════════╝{RESET}")

    run_g = args.guardian or args.heal or (not args.guardian and not args.scientist)
    run_s = args.scientist or (not args.guardian and not args.scientist and not args.heal)

    guardian_result = None
    scientist_result = None

    if args.heal:
        # Heal mode: fix loop + scientist after
        guardian_result = heal(products, include_advisory=args.advisory)
        if guardian_result["score"] == 100:
            scientist_result = run_scientist()
    else:
        # Normal mode
        if run_g:
            guardian_result = run_guardian(products, include_advisory=args.advisory)
        if run_s:
            if guardian_result and guardian_result["score"] < 100:
                print(f"  {RED}Guardian {guardian_result['score']}/100 — fix issues first{RESET}")
                print(f"  {YELLOW}Run: python -m agents --heal{RESET}")
            else:
                scientist_result = run_scientist()

    # Summary
    print()
    print(f"{BOLD}{'─'*58}{RESET}")
    if guardian_result:
        score = guardian_result["score"]
        color = GREEN if score == 100 else RED
        print(f"  Guardian:  {color}{score}/100{RESET}")
        if args.heal:
            print(f"  Healed:    {guardian_result.get('auto_fixed', 0)} auto-fixed, {guardian_result.get('proposals_created', 0)} proposals")
    if scientist_result:
        print(f"  Scientist: {scientist_result['proposal_count']} proposals pending")
    ai = f"{GREEN}active{RESET}" if is_ai_available() else f"{YELLOW}disabled (set OPENAI_API_KEY){RESET}"
    print(f"  AI:        {ai}")
    print(f"{BOLD}{'─'*58}{RESET}")
    print()

    if guardian_result and guardian_result["score"] < 100:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
