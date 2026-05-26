"""Observation-only review — detect seed-compliance issues, surface them for authoring.

CRITICAL: This module NEVER modifies product code. Every detected issue becomes
a proposal in `products/<product>/proposals/` for a human to review.

Three execution modes (see `run_review(mode=...)`):

  1. **agent** (default) — return the structured issue list + a review prompt
     the in-session agent (Claude, etc.) uses to author proposals with full
     conversation context. Zero LLM cost at this layer. The agent is expected
     to Read `templates/PROPOSAL-TEMPLATE.md`, fill it per issue, and file via
     `noctus.dev.file_proposal` (or `tools.proposals.file_proposal` directly).

  2. **headless** — no agent in the loop (CI, cron, solo CLI without a chat
     session). OpenAI `gpt-4o-mini` authors proposals, Python fills the
     template, `file_proposal` writes. Falls back to a skeleton if
     `OPENAI_API_KEY` is missing so findings are never silently dropped.

  3. **evaluate** — write BOTH paths to a scratch subfolder
     (`products/<product>/proposals/evaluations/<timestamp>/`) so the agent and the
     OpenAI model can be compared side by side. No proposal lands in the live
     proposals dir during an evaluation run.

Replaces the old `heal_product()` flow which auto-fixed deterministic issues
via text replacement — retired because `str.replace` rewrites could corrupt
unrelated code and the string-match checks rotted as the seed evolved.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from settings import REPO_ROOT, PRODUCTS_DIR  # noqa: E402  (path constants)
from workspace import resolve_caller_root  # noqa: E402


ReviewMode = Literal["agent", "headless", "evaluate"]


class ReviewInput(BaseModel):
    product: Optional[str] = Field(
        None, description="Optional: scope to one product slug. Default = all products."
    )
    mode: ReviewMode = Field(
        "agent",
        description="Review mode. agent = return findings for in-session author. headless = OpenAI files proposals. evaluate = side-by-side scratch.",
    )
    model: str = Field(
        "gpt-4o-mini",
        description="OpenAI model used in headless + evaluate modes. Ignored in agent mode.",
    )


class ReviewOutput(BaseModel):
    """Output shape varies by mode (`agent` returns review_prompt + issues; `headless`
    returns proposal-write counts; `evaluate` returns scratch dir locations). Treat
    as a discriminated bag — the `mode` field tells you which shape to expect."""

    mode: ReviewMode
    reviewed_products: list[str] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    review_prompt: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict, description="Mode-specific keys.")


def _detect(
    product_slug: str | None,
    *,
    products_dir: Path | None = None,
) -> tuple[list[Path], list[dict]]:
    from tools.noctus.dev.compliance import (
        check_seed_compliance,
        check_path_references,
        check_standard_routers_audit,
        check_frontend_entrypoint,
        check_handrolled_core_url,                     # registration-drift fix 2026-05-25
        check_fe_route_missing,
        check_name_on_nome_select,
        check_promise_all_shared_catch,
        check_config_extends_product_settings,
        check_frontend_config_paths,
        check_mock_schema_validation,                  # registration-drift fix 2026-05-25
        check_ai_feature_completeness,                 # registration-drift fix 2026-05-25
        check_out_of_contract_trees,
        check_test_status_assertion,
        check_unknown_table_references,
        check_function_search_path_pinned,
        check_rls_policy_self_reference,               # registration-drift fix 2026-05-25
        check_admin_endpoint_service_role_bypass,
        check_auth_session_mutation_on_shared_client,  # registration-drift fix 2026-05-25
        check_slowapi_with_pep563,
    )

    base = products_dir if products_dir is not None else PRODUCTS_DIR
    if product_slug:
        p = base / product_slug
        products = [p] if p.exists() else []
    else:
        products = sorted([d for d in base.iterdir() if d.is_dir() and not d.name.startswith(".")])

    issues: list[dict] = []
    for product_path in products:
        issues.extend(check_seed_compliance(product_path))
        issues.extend(check_path_references(product_path))
        issues.extend(check_standard_routers_audit(product_path))
        issues.extend(check_frontend_entrypoint(product_path))
        issues.extend(check_handrolled_core_url(product_path))               # registration-drift fix 2026-05-25
        issues.extend(check_fe_route_missing(product_path))
        issues.extend(check_name_on_nome_select(product_path))
        issues.extend(check_promise_all_shared_catch(product_path))
        issues.extend(check_config_extends_product_settings(product_path))
        issues.extend(check_frontend_config_paths(product_path))
        issues.extend(check_mock_schema_validation(product_path))            # registration-drift fix 2026-05-25
        issues.extend(check_ai_feature_completeness(product_path))           # registration-drift fix 2026-05-25
        issues.extend(check_test_status_assertion(product_path))
        issues.extend(check_unknown_table_references(product_path))
        issues.extend(check_function_search_path_pinned(product_path))
        issues.extend(check_rls_policy_self_reference(product_path))         # registration-drift fix 2026-05-25
        issues.extend(check_admin_endpoint_service_role_bypass(product_path))
        issues.extend(check_auth_session_mutation_on_shared_client(product_path))  # registration-drift fix 2026-05-25
        issues.extend(check_slowapi_with_pep563(product_path))
    # Global repo-root sweep — only when not scoped to a single product.
    if product_slug is None:
        issues.extend(check_out_of_contract_trees())
    return products, issues


def _agent_review_prompt(issues: list[dict]) -> str:
    """Return a prompt the in-session agent can follow to file proposals for each issue.

    The agent reads this, opens the template, fills one proposal per issue, and
    calls `file_proposal` — all in the same session turn, using the rich context
    (recent changes, conversation, plan) that an external LLM call would miss.
    """
    if not issues:
        return "No compliance issues detected. Nothing for the agent to author."

    lines = [
        "## Agent review task",
        "",
        "The detector flagged the issues below. Author one proposal per issue:",
        "",
        "1. Read `templates/PROPOSAL-TEMPLATE.md`.",
        "2. For each issue, fill every `{{PLACEHOLDER}}` using your session context — recent changes, conversation, related files you've already loaded.",
        "3. Call `tools.proposals.file_proposal(title=..., body=<filled markdown>, agent='claude-opus-4-7', product='<product_slug>')` to write each proposal to `products/<product>/proposals/`.",
        "4. Surface a one-line summary of each filed proposal to the user.",
        "",
        "Rules:",
        "- NEVER modify product code in this turn. This is observation-only.",
        "- NEVER propose changes inside `seed/` unless the issue clearly indicates a framework gap.",
        "- If the fix could be destructive (file deletion, mass text-replacement), flag it explicitly in the proposal's `Risks` section.",
        "",
        "Issues to review:",
        "",
    ]
    for i, issue in enumerate(issues, start=1):
        lines.append(
            f"{i}. **[{issue.get('severity', 'unknown')}]** `{issue.get('product', '?')}` "
            f"— {issue.get('file', '?')}: {issue.get('issue', '?')}"
        )
    return "\n".join(lines)


def _headless_author(issue: dict, product_path: Path, model: str, agent_tag: str, subdir: str | None = None) -> dict:
    """Author + file one proposal via OpenAI. Falls back to skeleton on failure."""
    from tools.noctus.dev.ai_brain import review_compliance_issue, is_ai_available
    from tools.noctus.dev.proposals import fill_proposal_template, file_proposal, generate_proposal

    if not is_ai_available():
        fallback = generate_proposal(
            title=f"Compliance: {issue.get('issue', '')[:60]}",
            problem=issue.get("issue", ""),
            solution=(
                "LLM review unavailable (OPENAI_API_KEY not set or `openai` not installed). "
                "Rerun with the key set, or have the in-session agent author this proposal."
            ),
            affected_products=[issue.get("product", "unknown")],
            severity=issue.get("severity", "medium"),
            agent=f"{agent_tag}-fallback",
            product=issue.get("product"),
        )
        return {"mode": "skeleton", **fallback}

    analysis = review_compliance_issue(issue, product_path, model=model)
    if not analysis:
        fallback = generate_proposal(
            title=f"Compliance: {issue.get('issue', '')[:60]}",
            problem=issue.get("issue", ""),
            solution="LLM returned an unparseable response. Rerun or escalate to agent review.",
            affected_products=[issue.get("product", "unknown")],
            severity=issue.get("severity", "medium"),
            agent=f"{agent_tag}-fallback",
            product=issue.get("product"),
        )
        return {"mode": "skeleton", **fallback}

    body = fill_proposal_template(
        title=analysis.get("title") or f"Compliance: {issue.get('issue', '')[:60]}",
        agent=agent_tag,
        origin=f"keeper:noctus.dev.validate:{issue.get('product', 'unknown')}",
        severity=issue.get("severity", "medium"),
        effort=analysis.get("effort", "medium"),
        affected_products=[issue.get("product", "unknown")],
        context=analysis.get("context") or (
            f"Keeper's deterministic compliance detector flagged this in product "
            f"`{issue.get('product', 'unknown')}` during a `noctus.dev.review` pass. "
            f"No plan phase produced it — the finding is standalone."
        ),
        situation=analysis.get("situation") or issue.get("issue", ""),
        linkage=analysis.get("linkage") or (
            "The proposed approach follows the seed contract the detector verifies against; "
            "applying it restores alignment without introducing new divergence."
        ),
        application_steps=analysis.get("application_steps") or ["Author manually — LLM returned no steps."],
        seed_apis=analysis.get("seed_apis") or [],
        risks=analysis.get("risks") or "Low risk — additive change, no overwrite.",
        alternatives=analysis.get("alternatives") or [],
        effects=analysis.get("effects") or [],
        related_files=analysis.get("related_files") or [],
    )
    result = file_proposal(
        title=analysis.get("title") or f"Compliance: {issue.get('issue', '')[:60]}",
        body=body,
        agent=agent_tag,
        product=issue.get("product"),
        subdir=subdir,
    )
    return {"mode": "llm", **result}


def run_review(
    product_slug: str | None = None,
    mode: Literal["agent", "headless", "evaluate"] = "agent",
    model: str = "gpt-4o-mini",
    *,
    worktree_path: str | Path | None = None,
    products_dir: Path | None = None,
) -> dict:
    """Run a review pass. Mode selects who authors the proposals.

    Args:
        product_slug: Optional — scope to one product. Defaults to all.
        mode:
            - `agent` (default): return `issues` + `review_prompt` for the
              in-session agent. No proposals are filed by this call.
            - `headless`: author proposals via OpenAI, file to the live
              proposals dir.
            - `evaluate`: author proposals via OpenAI to a scratch subfolder
              (`products/<product>/proposals/evaluations/<timestamp>-<slug>/`) so the
              agent can later drop its own version + `comparison.md` next to it.
        model: Override the OpenAI model (headless + evaluate modes only).
        worktree_path: **Caller-aware path resolution.** When set,
            detection + proposal writes target the caller's worktree's
            ``products/`` tree instead of the MCP server's startup
            workspace. Engineers calling from inside a ``git worktree add``
            MUST pass their worktree root. See ``resolve_caller_root``.
        products_dir: Override the module-level :data:`PRODUCTS_DIR`
            (test seam). When set, wins over ``worktree_path``.

    3-tier priority: explicit ``products_dir`` > ``worktree_path`` >
    module default :data:`PRODUCTS_DIR`.

    Returns a dict keyed by mode — see examples in `mcp/noctusai/README.md`.

    Raises:
        ValueError: ``worktree_path`` is given but does not look like a
        valid worktree root (per ``resolve_caller_root`` contract).
    """
    from tools.noctus.dev.compliance import check_all_products

    if products_dir is not None:
        base_products_dir = products_dir
    elif worktree_path is not None:
        base_products_dir = resolve_caller_root(worktree_path) / "products"
    else:
        base_products_dir = PRODUCTS_DIR

    products, issues = _detect(product_slug, products_dir=base_products_dir)
    report: dict = {
        "mode": mode,
        "reviewed_products": [p.name for p in products],
        "issues_found": len(issues),
    }

    if mode == "agent":
        report["issues"] = issues
        report["review_prompt"] = _agent_review_prompt(issues)
        report["note"] = (
            "Agent mode: this call does NOT file any proposals. "
            "The in-session agent uses `review_prompt` + `templates/PROPOSAL-TEMPLATE.md` "
            "to author one proposal per issue and file via `noctus.dev.file_proposal`."
        )
        return report

    if mode == "evaluate":
        slug = product_slug or "all-products"
        eval_subdir = f"evaluations/{datetime.now():%Y%m%d-%H%M%S}-{slug}"
        # For evaluate mode, if scoped to one product, nest under that product.
        # For all-products, use the first product that has issues (or skip).
        openai_results = []
        # Group issues by product for proper scoping
        products_with_issues = set(i.get("product", "") for i in issues)
        for p_slug in products_with_issues:
            p_proposals_dir = base_products_dir / p_slug / "proposals" / eval_subdir
            p_proposals_dir.mkdir(parents=True, exist_ok=True)
        # Persist the issue set so both paths reason about the same inputs.
        if product_slug:
            issues_dir = base_products_dir / product_slug / "proposals" / eval_subdir
        else:
            # For all-products eval, put issues.json under the first product
            first_product = next(iter(products_with_issues), "unknown")
            issues_dir = base_products_dir / first_product / "proposals" / eval_subdir
        issues_dir.mkdir(parents=True, exist_ok=True)
        (issues_dir / "issues.json").write_text(
            json.dumps(issues, indent=2, default=str)
        )
        for issue in issues:
            product_path = base_products_dir / issue.get("product", "")
            agent_tag = f"openai-{model}"
            openai_results.append(
                _headless_author(issue, product_path, model=model, agent_tag=agent_tag, subdir=eval_subdir)
            )
        report["eval_subdir"] = eval_subdir
        report["openai_results"] = openai_results
        report["next_steps"] = (
            f"OpenAI proposals written to `products/<product>/proposals/{eval_subdir}/`. "
            "Now the in-session agent should (1) author its own proposal per issue into "
            "the same folder (agent='claude-...'), (2) write `comparison.md` in the folder "
            "with an honest side-by-side review, (3) report back to the user."
        )
        return report

    if mode == "headless":
        llm_authored = 0
        skeletons = 0
        for issue in issues:
            product_path = base_products_dir / issue.get("product", "")
            agent_tag = f"keeper-openai-{model}"
            result = _headless_author(issue, product_path, model=model, agent_tag=agent_tag)
            if result.get("mode") == "llm":
                llm_authored += 1
            else:
                skeletons += 1
        final_score, final_issues = check_all_products()
        report["llm_authored"] = llm_authored
        report["skeletons"] = skeletons
        report["final_score"] = final_score
        report["remaining_issues"] = len(final_issues)
        return report

    raise ValueError(f"Unknown review mode: {mode!r}")


def register(server) -> None:
    desc = (
        "OBSERVATION-ONLY review. Detects seed-compliance issues deterministically. "
        "Three modes via `mode`: `agent` (default — returns issues + review prompt "
        "for the in-session agent to author proposals with session context, zero LLM "
        "cost), `headless` (OpenAI gpt-4o-mini authors proposals for CI/cron — set "
        "OPENAI_API_KEY), `evaluate` (writes OpenAI proposals to a scratch subfolder "
        "for side-by-side comparison with agent-authored versions). NEVER modifies code. "
        "Pass `worktree_path` when called from inside a git worktree so detection + "
        "proposal writes target the worktree's products/ tree NOT the MCP server's "
        "startup workspace. See KB § PATTERNS/mcp-tool-conventions.md."
    )

    def _review(
        product: str | None = None,
        mode: str = "agent",
        model: str = "gpt-4o-mini",
        worktree_path: str | None = None,
    ) -> dict:
        return run_review(
            product_slug=product,
            mode=mode,
            model=model,
            worktree_path=worktree_path,
        )

    server.tool(
        name="noctus.dev.review",
        description=desc,
    )(_review)
