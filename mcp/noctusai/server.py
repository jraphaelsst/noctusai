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

        # Heal
        _tool("noctusai_heal", "Auto-fix loop: detect → fix → verify → repeat until clean", {
            "product": {"type": "string", "description": "Optional: scope to one product"},
        }),

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

        # Proposals
        _tool("noctusai_list_proposals", "List pending improvement proposals", {
            "agent": {"type": "string", "description": "Optional: filter by agent name"},
        }),
        _tool("noctusai_accept_proposal", "Accept a proposal", {"filename": {"type": "string"}}, ["filename"]),
        _tool("noctusai_reject_proposal", "Reject a proposal", {
            "filename": {"type": "string"}, "reason": {"type": "string"},
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
    from tools import products, context, compliance, analyzers, fixes, proposals, master_prompts, testing, diff, ai_brain, scaffold

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
        "noctusai_heal": lambda: fixes.heal_product(args.get("product")),
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
        "noctusai_list_proposals": lambda: proposals.list_proposals(args.get("agent")),
        "noctusai_accept_proposal": lambda: proposals.update_proposal_status(args["filename"], "accepted"),
        "noctusai_reject_proposal": lambda: proposals.update_proposal_status(args["filename"], "rejected", args.get("reason", "")),
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
