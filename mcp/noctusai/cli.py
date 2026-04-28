"""
NoctusAI CLI — human-friendly interface to the same MCP tools.

Usage:
  python mcp/noctusai/cli.py --validate                       # Check compliance
  python mcp/noctusai/cli.py --review                          # Agent-primary review — returns prompt for in-session agent
  python mcp/noctusai/cli.py --review --headless               # Headless: OpenAI gpt-4o-mini files proposals, NEVER edits code
  python mcp/noctusai/cli.py --review --evaluate --product X   # Eval mode: OpenAI writes to proposals/evaluations/, agent adds its version + comparison.md
  python mcp/noctusai/cli.py --analyze                         # Run all analyzers
  python mcp/noctusai/cli.py --discover               # AI-powered discovery
  python mcp/noctusai/cli.py --metrics                # Code metrics
  python mcp/noctusai/cli.py --sync-prompts           # Sync all MASTER-PROMPTs
  python mcp/noctusai/cli.py --test                   # Run all tests
  python mcp/noctusai/cli.py --build                  # Build all frontends
  python mcp/noctusai/cli.py --proposals              # List proposals
  python mcp/noctusai/cli.py --catalog                # Regenerate shared-library catalog
  python mcp/noctusai/cli.py --improvements <project.md> # Regenerate improvements.md next to project file
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
    parser.add_argument("--check-phase-state", action="store_true", help="Check §6 ↔ §11 phase-state consistency across PROJECT.md files. Exits 1 on any high-severity issue. Used by the pre-commit hook to block commits that ship mismatch.")
    parser.add_argument("--review", action="store_true", help="Observation-only review. Default: return issues + prompt for the in-session agent. --headless fires OpenAI gpt-4o-mini. --evaluate writes both paths side-by-side to proposals/evaluations/. NEVER modifies code.")
    parser.add_argument("--headless", action="store_true", help="With --review: author proposals via OpenAI (no in-session agent required).")
    parser.add_argument("--evaluate", action="store_true", help="With --review: write OpenAI proposals to proposals/evaluations/ for side-by-side comparison with agent-authored versions.")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model for --headless / --evaluate. Default: gpt-4o-mini.")
    parser.add_argument("--analyze", action="store_true", help="Run all analyzers")
    parser.add_argument("--discover", action="store_true", help="AI-powered discovery")
    parser.add_argument("--metrics", action="store_true", help="Code metrics")
    parser.add_argument("--sync-prompts", action="store_true", help="Sync all MASTER-PROMPTs")
    parser.add_argument("--test", action="store_true", help="Run all backend tests")
    parser.add_argument("--build", action="store_true", help="Build all frontends")
    parser.add_argument("--proposals", action="store_true", help="List proposals")
    parser.add_argument("--verify-kb-sync", action="store_true", help="Verify CLAUDE.md pointers + KB INDEX.md are in sync")
    parser.add_argument("--catalog", action="store_true", help="Regenerate shared-library catalog (symbols, importers, orphans, duplicates)")
    parser.add_argument("--improvements", metavar="PROJECT", help="Regenerate improvements.md next to the project file (run after ticking a phase header to [x]). Captures improvement opportunities discovered during each completed phase — NOT a preview of upcoming phases.")
    parser.add_argument("--lgpd-flag", action="store_true", help="Record an LGPD concern in LGPD-WARNINGS.md. Requires --lgpd-concern, --lgpd-path, --lgpd-reason; --lgpd-mitigation optional. Does NOT block.")
    parser.add_argument("--lgpd-concern", help="Short label for the concern (e.g. 'patient-text-in-cache')")
    parser.add_argument("--lgpd-path", help="Code location (file:line or brief locator)")
    parser.add_argument("--lgpd-reason", help="One-to-three sentences on how this breaks or approaches LGPD")
    parser.add_argument("--lgpd-mitigation", help="Optional suggested fix")
    parser.add_argument("--lgpd-list", action="store_true", help="List all LGPD concerns and their resolved state")
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

    elif args.check_phase_state:
        from tools.compliance import check_phase_state_consistency
        issues = check_phase_state_consistency()
        if not issues:
            print(f"  {GREEN}✓ §6 ↔ §11 phase-state consistency clean.{RESET}")
            sys.exit(0)
        print(f"  {RED}✗ {len(issues)} phase-state consistency issue(s) found:{RESET}")
        for i in issues:
            print(f"    {RED}[{i['severity']}]{RESET} {i['product']} — {i['issue']}")
        print(
            f"\n  {BOLD}Fix the §6 live state before committing.{RESET}\n"
            f"  Per `KB § PATTERNS/project-execution.md § 2 Self-check before claiming a phase is done`."
        )
        sys.exit(1)

    elif args.review:
        from tools.review import run_review
        mode = "evaluate" if args.evaluate else ("headless" if args.headless else "agent")
        result = run_review(product_slug=args.product, mode=mode, model=args.model)
        print(f"  {BOLD}Mode:{RESET} {mode}  |  Issues found: {result['issues_found']}")

        if mode == "agent":
            print(f"  {BOLD}No proposals filed by this call.{RESET} The in-session agent authors them.")
            print(f"  Agent review prompt (scroll up or pipe to a file):\n")
            print(result["review_prompt"])
        elif mode == "headless":
            color = GREEN if result["final_score"] == 100 else RED
            print(f"  Score: {color}{result['final_score']}/100{RESET}  |  Remaining: {result['remaining_issues']}")
            print(f"  LLM-authored: {result['llm_authored']}  |  Skeletons: {result['skeletons']}  |  Model: {args.model}")
            print(f"  {BOLD}No code was modified.{RESET} Review proposals in products/<product>/proposals/")
        elif mode == "evaluate":
            print(f"  {BOLD}Eval folder:{RESET} products/<product>/proposals/{result['eval_subdir']}/")
            print(f"  OpenAI proposals filed: {len([r for r in result['openai_results'] if r.get('mode') == 'llm'])}")
            print(f"  {YELLOW}Next:{RESET} in-session agent writes its own proposals + comparison.md in the same folder.")
        if args.json:
            print(json.dumps(result, indent=2, default=str))

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

    elif args.verify_kb_sync:
        from tools.kb_sync import verify_kb_sync
        result = verify_kb_sync()
        if result["stdout"]:
            print(result["stdout"], end="")
        if result["stderr"]:
            print(result["stderr"], end="", file=sys.stderr)
        sys.exit(result["exit_code"])

    elif args.catalog:
        from tools.catalog import generate_catalog
        result = generate_catalog(write=True)
        summary = result["summary"]
        print(f"  {BOLD}Catalog written:{RESET} {result['output_path']}")
        print(f"    {summary['total_symbols']} symbols · {summary['products']} products scanned")
        orph_color = YELLOW if summary['orphans'] else GREEN
        dup_color = YELLOW if summary['duplicate_candidates'] else GREEN
        print(f"    {orph_color}{summary['orphans']} orphans{RESET} · "
              f"{summary['single_consumer']} single-consumer · "
              f"{dup_color}{summary['duplicate_candidates']} duplicate candidates{RESET}")
        if args.json:
            print(json.dumps(result, indent=2, default=str))

    elif args.lgpd_list:
        from tools.lgpd import list_warnings
        result = list_warnings()
        unresolved = result.get("unresolved_count", 0)
        resolved = result.get("resolved_count", 0)
        color = YELLOW if unresolved else GREEN
        print(f"  {BOLD}LGPD warnings:{RESET} {result['file']}")
        print(f"    {color}{unresolved} unresolved{RESET} · {resolved} resolved")
        for e in result.get("entries", []):
            mark = f"{GREEN}✓{RESET}" if e["resolved"] else f"{YELLOW}◯{RESET}"
            print(f"    {mark} {e['concern']} @ {e['code_path']}")
        if args.json:
            print(json.dumps(result, indent=2, default=str))

    elif args.lgpd_flag:
        from tools.lgpd import flag
        missing = [n for n, v in [
            ("--lgpd-concern", args.lgpd_concern),
            ("--lgpd-path", args.lgpd_path),
            ("--lgpd-reason", args.lgpd_reason),
        ] if not v]
        if missing:
            print(f"  {RED}Error:{RESET} missing required args: {', '.join(missing)}")
            sys.exit(2)
        result = flag(
            code_path=args.lgpd_path,
            concern=args.lgpd_concern,
            reason=args.lgpd_reason,
            mitigation=args.lgpd_mitigation,
        )
        if result.get("error"):
            print(f"  {RED}Error:{RESET} {result['error']}")
            sys.exit(1)
        # Always print the notification prominently — even in --json mode.
        print(f"\n  {YELLOW}{result['notification']}{RESET}\n")
        if args.json:
            print(json.dumps(result, indent=2, default=str))

    elif args.improvements:
        from tools.improvements import generate_improvements
        result = generate_improvements(args.improvements, write=True)
        if result.get("error"):
            print(f"  {RED}Error:{RESET} {result['error']}")
            sys.exit(1)
        done = sum(1 for p in result["phases"] if p["done"])
        total = len(result["phases"])
        with_imp = len(result["phases_with_improvements"])
        missing = len(result["completed_without_improvements"])
        done_color = GREEN if result["all_done"] else YELLOW
        miss_color = YELLOW if missing else GREEN
        print(f"  {BOLD}Improvements written:{RESET} {result['output_path']}")
        print(f"    {done_color}{done}/{total} phases complete{RESET} · "
              f"{with_imp} with recorded improvements · "
              f"{miss_color}{missing} completed without a block{RESET}")
        if args.json:
            print(json.dumps(result, indent=2, default=str))

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
