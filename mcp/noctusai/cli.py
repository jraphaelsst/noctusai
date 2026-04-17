"""
NoctusAI CLI — human-friendly interface to the same MCP tools.

Usage:
  python mcp/noctusai/cli.py --validate              # Check compliance
  python mcp/noctusai/cli.py --heal                   # Auto-fix loop
  python mcp/noctusai/cli.py --heal --product mailing # Heal one product
  python mcp/noctusai/cli.py --analyze                # Run all analyzers
  python mcp/noctusai/cli.py --discover               # AI-powered discovery
  python mcp/noctusai/cli.py --metrics                # Code metrics
  python mcp/noctusai/cli.py --sync-prompts           # Sync all MASTER-PROMPTs
  python mcp/noctusai/cli.py --test                   # Run all tests
  python mcp/noctusai/cli.py --build                  # Build all frontends
  python mcp/noctusai/cli.py --proposals              # List proposals
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def main():
    parser = argparse.ArgumentParser(description="NoctusAI — platform dev toolkit")
    parser.add_argument("--validate", action="store_true", help="Check seed compliance")
    parser.add_argument("--heal", action="store_true", help="Auto-fix loop until clean")
    parser.add_argument("--analyze", action="store_true", help="Run all analyzers")
    parser.add_argument("--discover", action="store_true", help="AI-powered discovery")
    parser.add_argument("--metrics", action="store_true", help="Code metrics")
    parser.add_argument("--sync-prompts", action="store_true", help="Sync all MASTER-PROMPTs")
    parser.add_argument("--test", action="store_true", help="Run all backend tests")
    parser.add_argument("--build", action="store_true", help="Build all frontends")
    parser.add_argument("--proposals", action="store_true", help="List proposals")
    parser.add_argument("--product", help="Scope to one product")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    print(f"\n{BOLD}╔══════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}║                NoctusAI Dev Toolkit                      ║{RESET}")
    print(f"{BOLD}╚══════════════════════════════════════════════════════════╝{RESET}\n")

    if args.validate:
        from tools.compliance import check_all_products
        score, issues = check_all_products()
        color = GREEN if score == 100 else RED
        print(f"  {BOLD}Score: {color}{score}/100{RESET}  |  Issues: {len(issues)}")
        for i in issues:
            print(f"    {RED}[{i['severity']}]{RESET} {i['product']}: {i['issue']}")

    elif args.heal:
        from tools.fixes import heal_product
        result = heal_product(args.product)
        color = GREEN if result["final_score"] == 100 else RED
        print(f"  {BOLD}Score: {color}{result['final_score']}/100{RESET}")
        print(f"  Fixed: {result['auto_fixed']}  |  Proposals: {result['proposals_created']}")

    elif args.analyze:
        from tools.analyzers import run_all_analyzers
        results = run_all_analyzers()
        print(f"  Duplicated functions: {len(results['duplicated_functions'])}")
        print(f"  Inline hooks: {len(results['inline_hooks'])}")
        print(f"  Python dep mismatches: {len(results['python_dep_mismatches'])}")
        tc = results['test_coverage']
        print(f"  Test gaps: {len(tc['issues'])}")
        if args.json:
            print(json.dumps(results, indent=2, default=str))

    elif args.discover:
        from tools.analyzers import run_all_analyzers
        from tools.ai_brain import analyze_findings, is_ai_available
        if not is_ai_available():
            print(f"  {YELLOW}AI disabled — set OPENAI_API_KEY{RESET}")
        else:
            findings = run_all_analyzers()
            proposals = analyze_findings(findings)
            for p in proposals:
                if p.get("type") == "proposal":
                    print(f"  {GREEN}→{RESET} {p['title']}")
                elif p.get("type") == "healthy":
                    print(f"  {GREEN}Platform healthy{RESET}")

    elif args.metrics:
        from tools.analyzers import get_code_metrics
        metrics = get_code_metrics()
        print(f"  {'Product':<20} {'BE':<8} {'FE':<8} {'R':<4} {'S':<4} {'P':<4} {'H':<4}")
        print(f"  {'─'*20} {'─'*8} {'─'*8} {'─'*4} {'─'*4} {'─'*4} {'─'*4}")
        for m in metrics:
            print(f"  {m['product']:<20} {m['backend_lines']:<8} {m['frontend_lines']:<8} {m['routers']:<4} {m['services']:<4} {m['pages']:<4} {m['hooks']:<4}")

    elif args.sync_prompts:
        from tools.master_prompts import sync_all_master_prompts
        results = sync_all_master_prompts()
        for r in results:
            status = f"{GREEN}synced{RESET}" if r.get("updated") else "up to date"
            print(f"  {r.get('product', '?')}: {status}")

    elif args.test:
        from tools.testing import run_all_tests
        results = run_all_tests()
        for r in results["products"]:
            color = GREEN if r.get("success") else RED
            print(f"  {r['product']:<20} {color}{r.get('passed', 0)} passed, {r.get('failed', 0)} failed{RESET}")
        print(f"\n  Total: {results['total_passed']} passed, {results['total_failed']} failed")

    elif args.build:
        from tools.testing import build_all_frontends
        results = build_all_frontends()
        for r in results["products"]:
            color = GREEN if r.get("success") else RED
            print(f"  {r['product']:<20} {color}{'OK' if r.get('success') else 'FAIL'}{RESET}")

    elif args.proposals:
        from tools.proposals import list_proposals
        for p in list_proposals():
            color = GREEN if p["status"] == "accepted" else YELLOW if p["status"] == "pending" else RED
            print(f"  {color}[{p['status']}]{RESET} {p['title']} ({p['agent']})")

    else:
        # Default: validate + analyze
        from tools.compliance import check_all_products
        from tools.analyzers import run_all_analyzers
        score, issues = check_all_products()
        color = GREEN if score == 100 else RED
        print(f"  {BOLD}Compliance: {color}{score}/100{RESET}")
        results = run_all_analyzers()
        print(f"  Patterns: {len(results['duplicated_functions'])} duplicates, {len(results['inline_hooks'])} inline hooks")
        print(f"  Deps: {len(results['python_dep_mismatches'])} mismatches")
        tc = results['test_coverage']
        print(f"  Tests: {len(tc['issues'])} gaps")

    print()


if __name__ == "__main__":
    main()
