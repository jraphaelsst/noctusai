"""
NoctusAI MCP Server — platform dev toolkit.

All development tools in one place. Agents call structured tools
instead of running shell commands.

Run: python mcp/noctusai/server.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import json

server = Server("noctusai")


def _tool(name, desc, props=None, required=None):
    schema = {"type": "object", "properties": props or {}}
    if required:
        schema["required"] = required
    return Tool(name=name, description=desc, inputSchema=schema)


@server.list_tools()
async def list_tools():
    slug_param = {"slug": {"type": "string", "description": "Product slug"}}
    return [
        # Context
        _tool("noctusai_agent_context", "Full platform context for an agent starting fresh. Call FIRST."),
        _tool("noctusai_product_context", "Everything needed to work on a product: structure + MASTER-PROMPT + README", slug_param, ["slug"]),

        # Products
        _tool("noctusai_list_products", "List all products with routers, services, pages, hooks counts"),
        _tool("noctusai_get_product", "Detailed product structure: endpoints, config, tests, migrations", slug_param, ["slug"]),
        _tool("noctusai_platform_metrics", "Code metrics for all products: lines, routers, services, pages"),

        # Scaffold
        _tool("noctusai_scaffold_product", "Create a new product from the seed template", {
            "name": {"type": "string"}, "slug": {"type": "string"}, "schema": {"type": "string"},
            "backend_port": {"type": "integer"}, "frontend_port": {"type": "integer"},
            "icon": {"type": "string", "description": "Lucide icon name"},
        }, ["name", "slug", "schema", "backend_port", "frontend_port"]),
        _tool("noctusai_available_ports", "Find next available backend and frontend ports"),

        # Compliance
        _tool("noctusai_validate", "Check seed compliance for all products. Returns score 0-100."),
        _tool("noctusai_validate_product", "Check seed compliance for one product", slug_param, ["slug"]),

        # Review (observation-only — never modifies code)
        _tool("noctusai_review", "OBSERVATION-ONLY review. Detects seed-compliance issues deterministically. Three modes via `mode`: `agent` (default — returns issues + review prompt for the in-session agent to author proposals with session context, zero LLM cost), `headless` (OpenAI gpt-4o-mini authors proposals for CI/cron — set OPENAI_API_KEY), `evaluate` (writes OpenAI proposals to a scratch subfolder for side-by-side comparison with agent-authored versions). NEVER modifies code.", {
            "product": {"type": "string", "description": "Optional: scope to one product"},
            "mode": {"type": "string", "enum": ["agent", "headless", "evaluate"], "description": "Review mode (default: agent)"},
            "model": {"type": "string", "description": "OpenAI model for headless/evaluate modes (default: gpt-4o-mini)"},
        }),
        _tool("noctusai_proposal_template", "Return `templates/PROPOSAL-TEMPLATE.md` content so agents get a consistent starting point when authoring a proposal. Agents fill every `{{PLACEHOLDER}}` in the template and submit via `noctusai_file_proposal`."),
        _tool("noctusai_file_proposal", "Write a fully-rendered proposal markdown. For project-phase proposals pass `project=<slug>` — the file lands in `projects/<slug>/proposals/` (ONE bundled proposal per phase). For keeper/compliance proposals pass `product=<slug>` — the file lands in `products/<product>/proposals/`. Agents typically call `noctusai_proposal_template`, fill it, then submit via this tool. Dedups by title slug + key entity.", {
            "title": {"type": "string", "description": "Proposal title — used for filename slug + dedup"},
            "body": {"type": "string", "description": "Fully-rendered markdown (typically a filled PROPOSAL-TEMPLATE.md)"},
            "agent": {"type": "string", "description": "Authoring agent tag — filename prefix (default: keeper)"},
            "project": {"type": "string", "description": "Project slug / name / filename. When set, proposal lands in `projects/<slug>/proposals/`. Mutually exclusive with `product`."},
            "product": {"type": "string", "description": "Product slug. When set, proposal lands in `products/<product>/proposals/`. Used for keeper/compliance proposals. Combine with `subdir` for evaluation sub-folders. Mutually exclusive with `project`."},
            "subdir": {"type": "string", "description": "Subdirectory under the product proposals dir (e.g. evaluations/<ts>). Only valid when `product` is set."},
        }, ["title", "body"]),

        # Analyzers
        _tool("noctusai_analyze", "Run all analyzers: patterns, deps, tests, metrics"),
        _tool("noctusai_analyze_patterns", "Find duplicated functions and inline hooks"),
        _tool("noctusai_analyze_deps", "Check dependency version consistency"),
        _tool("noctusai_analyze_tests", "Check test coverage per product"),

        # AI
        _tool("noctusai_ai_discover", "AI-powered improvement discovery (requires OPENAI_API_KEY)"),
        _tool("noctusai_ai_advisory", "AI reads CLAUDE.md rules and validates code (requires OPENAI_API_KEY)"),

        # Master prompts
        _tool("noctusai_sync_master_prompt", "Regenerate MASTER-PROMPT structural sections from filesystem", slug_param, ["slug"]),
        _tool("noctusai_sync_all_master_prompts", "Sync all product MASTER-PROMPTs"),
        _tool("noctusai_check_master_prompt", "Check if a MASTER-PROMPT is stale", slug_param, ["slug"]),

        # Testing
        _tool("noctusai_run_tests", "Run pytest for a product", slug_param, ["slug"]),
        _tool("noctusai_run_all_tests", "Run tests for all products"),
        _tool("noctusai_build_frontend", "Build a product's frontend (vite build)", slug_param, ["slug"]),
        _tool("noctusai_build_all_frontends", "Build all product frontends"),

        # Diff & quality
        _tool("noctusai_diff_against_seed", "Compare a product's structural files against the seed product", slug_param, ["slug"]),
        _tool("noctusai_find_orphans", "Find orphaned files not imported anywhere", slug_param, ["slug"]),
        _tool("noctusai_check_api_consistency", "Check API response pattern consistency", slug_param, ["slug"]),

        # Catalog (shared-library observation layer)
        _tool("noctusai_catalog", "Regenerate the shared-library catalog: every lib symbol, its importers, orphans (zero consumers), and duplication candidates (same name in 2+ products, not in lib). Writes mcp/noctusai/catalog.md.", {
            "write": {"type": "boolean", "description": "Write markdown artifact to disk (default: true)"},
        }),

        # Improvements log (per-phase retrospective)
        _tool("noctusai_improvements", "Regenerate `improvements.md` next to a project file. Run this after ticking a phase header to `✅`. Aggregates the `**Improvements:**` block each completed phase captures — observations, refactor candidates, edge cases, tech debt learned while implementing THAT phase. NOT a preview of upcoming phases (that's already in the project).", {
            "project_path": {"type": "string", "description": "Absolute or repo-relative path to the project .md file"},
        }, ["project_path"]),

        # LGPD concern flagger — keeper-principle enforcement
        _tool("noctusai_lgpd_flag", "Record an unresolved LGPD concern in `LGPD-WARNINGS.md`. Call whenever data-touching code raises an LGPD question (retention unclear, 3rd-party egress, cache of patient text, cross-product leak, …). DOES NOT BLOCK — appends a checklist item and notifies the user. Returns a user-facing notification string the caller should surface.", {
            "code_path": {"type": "string", "description": "Where the concern lives — file:line or brief locator"},
            "concern": {"type": "string", "description": "Short label (e.g. 'patient-text-in-llm-cache')"},
            "reason": {"type": "string", "description": "1-3 sentences on how this breaks/approaches LGPD"},
            "mitigation": {"type": "string", "description": "Optional suggested fix"},
        }, ["code_path", "concern", "reason"]),
        _tool("noctusai_lgpd_list", "List all LGPD concerns from `LGPD-WARNINGS.md` (unresolved + resolved)."),

        # Proposals
        _tool("noctusai_list_proposals", "List pending improvement proposals across all products (or one product if `product` is set)", {
            "agent": {"type": "string", "description": "Optional: filter by agent name"},
            "product": {"type": "string", "description": "Optional: scope to one product slug"},
        }),
        _tool("noctusai_accept_proposal", "Accept a proposal", {
            "filename": {"type": "string"},
            "product": {"type": "string", "description": "Optional: product slug for scoped lookup"},
        }, ["filename"]),
        _tool("noctusai_reject_proposal", "Reject a proposal", {
            "filename": {"type": "string"}, "reason": {"type": "string"},
            "product": {"type": "string", "description": "Optional: product slug for scoped lookup"},
        }, ["filename"]),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    try:
        result = _dispatch(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, default=str))]


def _dispatch(name, args):
    from tools import products, context, compliance, analyzers, review as review_tool, proposals, master_prompts, testing, diff, ai_brain, scaffold, catalog, improvements, lgpd

    dispatch_map = {
        "noctusai_agent_context": lambda: context.get_agent_context(),
        "noctusai_product_context": lambda: context.get_product_context(args["slug"]),
        "noctusai_list_products": lambda: products.list_products(),
        "noctusai_get_product": lambda: products.get_product_structure(args["slug"]),
        "noctusai_platform_metrics": lambda: analyzers.get_code_metrics(),
        "noctusai_scaffold_product": lambda: scaffold.scaffold_product(args["name"], args["slug"], args["schema"], args["backend_port"], args["frontend_port"], args.get("icon", "Box")),
        "noctusai_available_ports": lambda: scaffold.list_available_ports(),
        "noctusai_validate": lambda: dict(zip(["score", "issues"], compliance.check_all_products())),
        "noctusai_validate_product": lambda: _validate_one(args["slug"]),
        "noctusai_review": lambda: review_tool.run_review(
            product_slug=args.get("product"),
            mode=args.get("mode", "agent"),
            model=args.get("model", "gpt-4o-mini"),
        ),
        "noctusai_proposal_template": lambda: {"template": proposals.get_proposal_template()},
        "noctusai_file_proposal": lambda: proposals.file_proposal(
            title=args["title"],
            body=args["body"],
            agent=args.get("agent", "keeper"),
            project=args.get("project"),
            product=args.get("product"),
            subdir=args.get("subdir"),
        ),
        "noctusai_analyze": lambda: analyzers.run_all_analyzers(),
        "noctusai_analyze_patterns": lambda: {"duplicated": analyzers.find_duplicated_functions(), "inline_hooks": analyzers.find_inline_hooks()},
        "noctusai_analyze_deps": lambda: analyzers.audit_python_deps(),
        "noctusai_analyze_tests": lambda: analyzers.analyze_test_coverage(),
        "noctusai_ai_discover": lambda: ai_brain.analyze_findings(analyzers.run_all_analyzers()),
        "noctusai_ai_advisory": lambda: ai_brain.ai_advisory(),
        "noctusai_sync_master_prompt": lambda: master_prompts.sync_master_prompt(args["slug"]),
        "noctusai_sync_all_master_prompts": lambda: master_prompts.sync_all_master_prompts(),
        "noctusai_check_master_prompt": lambda: master_prompts.check_master_prompt_staleness(args["slug"]),
        "noctusai_run_tests": lambda: testing.run_product_tests(args["slug"]),
        "noctusai_run_all_tests": lambda: testing.run_all_tests(),
        "noctusai_build_frontend": lambda: testing.build_product_frontend(args["slug"]),
        "noctusai_build_all_frontends": lambda: testing.build_all_frontends(),
        "noctusai_diff_against_seed": lambda: diff.diff_product_against_seed(args["slug"]),
        "noctusai_find_orphans": lambda: diff.find_orphaned_files(args["slug"]),
        "noctusai_check_api_consistency": lambda: diff.check_api_consistency(args["slug"]),
        "noctusai_catalog": lambda: catalog.generate_catalog(write=args.get("write", True)),
        "noctusai_improvements": lambda: improvements.generate_improvements(args["project_path"], write=True),
        "noctusai_lgpd_flag": lambda: lgpd.flag(
            code_path=args["code_path"],
            concern=args["concern"],
            reason=args["reason"],
            mitigation=args.get("mitigation"),
        ),
        "noctusai_lgpd_list": lambda: lgpd.list_warnings(),
        "noctusai_list_proposals": lambda: proposals.list_proposals(args.get("agent"), product=args.get("product")),
        "noctusai_accept_proposal": lambda: proposals.update_proposal_status(args["filename"], "accepted", product=args.get("product")),
        "noctusai_reject_proposal": lambda: proposals.update_proposal_status(args["filename"], "rejected", args.get("reason", ""), product=args.get("product")),
    }

    handler = dispatch_map.get(name)
    if handler:
        return handler()
    return {"error": f"Unknown tool: {name}"}


def _validate_one(slug):
    from tools.compliance import check_seed_compliance, check_path_references
    path = Path(__file__).resolve().parents[2] / "products" / slug
    issues = check_seed_compliance(path) + check_path_references(path)
    penalties = {"critical": 25, "high": 10, "warning": 3}
    score = max(0, 100 - sum(penalties.get(i["severity"], 5) for i in issues))
    return {"product": slug, "score": score, "issues": issues}


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
