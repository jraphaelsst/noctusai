"""Proposal management — template-driven authoring, generate/list/accept/reject.

All proposals follow the canonical shape in `templates/PROPOSAL-TEMPLATE.md`.
Two entry points:

  - `fill_proposal_template(...)` — substitute template placeholders with
    structured fields. Used by the OpenAI path (LLM returns JSON → Python
    fills) and by any programmatic caller.
  - `file_proposal(title, body, agent)` — write a fully-rendered proposal to
    disk with dedup. Agents operating in-session Read the template, fill it
    in their own voice, then call `file_proposal` with the rendered body.

The legacy `generate_proposal(title, problem, solution, ...)` shim remains
for callers that pre-date the template workflow (e.g. `tools/review.py` when
the LLM is unavailable and we need a bare-bones skeleton proposal).
"""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from noctusai_lib.primitives.timeutil import now_utc
from workspace import get_noctusai_home, get_workspace_root, resolve_caller_root

# Workspace-aware: projects/products live under the workspace's own root
# (so file_proposal from a template lands in template's projects, not
# noc's). The proposal TEMPLATE itself lives only in noc — fetched via
# get_noctusai_home(). See mcp/noctusai/workspace.py + KB § PATTERNS/seed-workspace.md.
REPO_ROOT = get_workspace_root()
# Two valid locations for project folders — see
# `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md §1` for the rule:
#
#   1. Root `projects/<slug>/` — cross-product, seed/platform-infra, or
#      migrations-of-something-not-yet-a-product (e.g. `adconnect-migration`,
#      `ai-expansion`, `multi-provider-llm`, `strict-mode-migration`).
#   2. `products/<product>/projects/<slug>/` — single-product scope. Every
#      product (including `products/core/`, the platform control plane)
#      carries its own `projects/` folder under this pattern.
#
# Slugs are globally unique: a slug exists in *exactly one* of the two
# locations. The resolver below walks both and returns the match.
PROJECTS_DIR = REPO_ROOT / "projects"
PRODUCTS_DIR = REPO_ROOT / "products"
# Template lives only in noc — read from canonical home regardless of workspace.
TEMPLATE_PATH = get_noctusai_home() / "templates" / "PROPOSAL-TEMPLATE.md"


def _resolve_dirs(worktree_path: str | Path | None) -> tuple[Path, Path]:
    """Resolve (projects_dir, products_dir) for the active call.

    When ``worktree_path`` is None, returns the module-level defaults
    (server-startup workspace). When set, returns the caller's worktree's
    ``projects/`` and ``products/`` — caller-aware path resolution per
    ``projects/mcp-worktree-path-resolution/``.
    """
    if worktree_path is None:
        return PROJECTS_DIR, PRODUCTS_DIR
    root = resolve_caller_root(worktree_path)
    return root / "projects", root / "products"


def _find_project_dir(
    slug: str,
    *,
    projects_dir: Path | None = None,
    products_dir: Path | None = None,
) -> Optional[Path]:
    """Locate the project folder for ``slug`` across both valid locations.

    Returns the absolute path to the folder if found, else None. Callers that
    need a definitive path for *new* projects should fall back to
    ``PROJECTS_DIR / slug`` — root is the default home for projects whose
    scope hasn't been decided.

    Args:
        projects_dir / products_dir: Override defaults (caller-aware path
            resolution). Both default to the module-level constants
            (server-startup workspace).
    """
    base_projects = projects_dir if projects_dir is not None else PROJECTS_DIR
    base_products = products_dir if products_dir is not None else PRODUCTS_DIR
    root_candidate = base_projects / slug
    if root_candidate.is_dir():
        return root_candidate
    if base_products.is_dir():
        for product in sorted(base_products.iterdir()):
            if not product.is_dir():
                continue
            candidate = product / "projects" / slug
            if candidate.is_dir():
                return candidate
    return None


def _project_proposals_dir(
    slug: str,
    *,
    projects_dir: Path | None = None,
    products_dir: Path | None = None,
) -> Path:
    """Return the ``proposals/`` folder for ``slug``, searching both valid
    project locations. Falls back to root ``projects/<slug>/proposals/`` when
    the project folder does not yet exist — new projects default to root
    unless the caller has already created the folder under a product."""
    base_projects = projects_dir if projects_dir is not None else PROJECTS_DIR
    found = _find_project_dir(
        slug, projects_dir=base_projects, products_dir=products_dir,
    )
    if found is not None:
        return found / "proposals"
    return base_projects / slug / "proposals"


def _product_proposals_dir(
    product_slug: str, *, products_dir: Path | None = None,
) -> Path:
    """Return the ``proposals/`` folder for a product (keeper/compliance proposals).

    Keeper proposals are always product-scoped — the detector tells us which
    product the issue belongs to, and the proposal lands next to that product.
    """
    base_products = products_dir if products_dir is not None else PRODUCTS_DIR
    return base_products / product_slug / "proposals"


def _slug(title):
    return title.lower().replace(" ", "-").replace("'", "").replace("/", "-")[:50]


def _project_slug(project: str) -> str:
    """Normalize a project name / filename into a folder-safe slug.

    Accepts either a bare slug ("metas"), a filename ("METAS-PROJECT.md",
    "METAS-PLAN.md"), or a full path. Returns a lowercase dash-separated slug
    suitable for `projects/<slug>/` (the canonical projects layout).
    """
    base = Path(project).name if "/" in project or project.endswith(".md") else project
    if base.endswith(".md"):
        base = base[:-3]
    # Strip common suffixes so `METAS-PROJECT` → `metas` and `METAS-PLAN` → `metas`.
    for suffix in ("-PROJECT", "-PLAN", "_PROJECT", "_PLAN"):
        if base.upper().endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base.lower().replace("_", "-").replace(" ", "-")


def _extract_key_entity(title):
    match = re.search(r"['\"]?(\w+_\w+)['\"]?", title)
    return match.group(1).lower() if match else _slug(title)[:30]


def _proposal_exists(
    title,
    product: Optional[str] = None,
    *,
    products_dir: Path | None = None,
):
    """Check whether a proposal with a similar title already exists.

    When ``product`` is given, searches ``products/<product>/proposals/``.
    Otherwise searches all ``products/*/proposals/`` roots.

    Args:
        products_dir: Override (caller-aware). Defaults to module-level
            :data:`PRODUCTS_DIR`.
    """
    slug = _slug(title)
    key = _extract_key_entity(title)

    base_products = products_dir if products_dir is not None else PRODUCTS_DIR

    if product:
        dirs = [_product_proposals_dir(product, products_dir=base_products)]
    else:
        dirs = sorted(base_products.glob("*/proposals")) if base_products.exists() else []

    for d in dirs:
        if not d.exists():
            continue
        for f in d.glob("*.md"):
            if f.name == "README.md":
                continue
            fname = f.stem.lower()
            if slug in fname:
                return True
            if key and len(key) > 5 and key in fname:
                return True
    return False


def get_proposal_template() -> str:
    """Return the raw proposal template. Agents fill placeholders, then call `file_proposal`.

    Placeholders follow `{{UPPER_SNAKE}}` convention — `{{TITLE}}`, `{{AGENT}}`,
    `{{YYYY-MM-DD HH:MM}}`, etc. See `templates/PROPOSAL-TEMPLATE.md` for the
    full list and filling guidance.
    """
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Proposal template missing: {TEMPLATE_PATH}")
    return TEMPLATE_PATH.read_text()


def fill_proposal_template(
    *,
    title: str,
    agent: str,
    origin: str,
    severity: str,
    effort: str,
    affected_products: list[str],
    context: str,
    situation: str,
    linkage: str,
    application_steps: list[str],
    seed_apis: Optional[list[dict]] = None,
    risks: str = "Low risk — additive change, no overwrite.",
    alternatives: Optional[list[dict]] = None,
    effects: Optional[list[dict]] = None,
    related_files: Optional[list[dict]] = None,
    extra_acceptance: Optional[list[str]] = None,
    status: str = "pending",
) -> str:
    """Render a filled proposal matching `templates/PROPOSAL-TEMPLATE.md` structure.

    The template file carries verbose authoring guidance (guiding prose,
    examples, HTML-comment instructions) meant for human / agent authors who
    fill it by hand. Programmatic filling emits the structure directly from
    here — mirroring the template's sections 1-6 — which avoids fragile regex
    substitution against that guidance prose.

    **If the template's section structure changes, update this function in
    the same commit.** The doc link in each section comment below names the
    anchor the template uses.

    Args:
        title: Short action-oriented title (< 80 chars).
        agent: Authoring agent tag — `claude-opus-4-7`, `keeper-openai-gpt-4o-mini`, etc.
        origin: Source tag — `plan:<name>:<phase>`, `keeper:noctus.dev.validate`, `lgpd:noctus.dev.lgpd_flag`, etc.
        severity: high | medium | low.
        effort: high | medium | low.
        affected_products: Product slugs the fix must touch.
        context: §1 — 2-5 sentences on what produced this proposal (phase built, detector run).
        situation: §2 — 3-6 sentences of facts describing the current state.
        linkage: §3.1 — 1-2 sentences linking the solution to the situation.
        application_steps: §3.2 — concrete unambiguous actions for the receiving agent.
        seed_apis: §3.3 — list of `{"symbol": "...", "why": "..."}`. None → `N/A`.
        risks: §3.4 — specific warnings. Default assumes additive change.
        alternatives: §3.5 — list of `{"approach": "...", "why_not": "..."}`. None → `N/A`.
        effects: §4 — list of `{"dimension": "Behavior|Risk profile|Ergonomics|Coverage", "change": "..."}`. None → empty section.
        related_files: §6 — list of `{"path": "...", "note": "..."}`. None → section omitted.
        extra_acceptance: §5 — additional checklist items beyond the standard five.
        status: Usually `pending`.

    Returns the filled markdown string — ready for `file_proposal`.
    """
    now = now_utc().strftime("%Y-%m-%d %H:%M")
    products_line = ", ".join(affected_products) if affected_products else "none"
    primary = affected_products[0] if affected_products else "<product>"

    # Section 3.3 seed APIs
    if seed_apis:
        apis_lines = "\n".join(f"- `{a['symbol']}` — {a['why']}" for a in seed_apis)
    else:
        apis_lines = "N/A — change is local to the product."

    # Section 3.5 alternatives
    if alternatives:
        alt_lines = "\n".join(f"- **{a['approach']}** — {a['why_not']}" for a in alternatives)
    else:
        alt_lines = "N/A — the situation dictates the fix."

    # Section 3.2 application steps.
    # Each item may be a plain string (simple step, keeper-style proposals)
    # or a dict representing one bundled improvement (project-phase proposals):
    #   {"title": "...", "steps": ["...", "..."], "linkage": "...", "risks": "...", "independent": True|False, "depends_on": [1, 2]}
    # For a dict item we render a numbered sub-heading with linkage / steps /
    # risks / independence, so the reviewer sees each bundled improvement as
    # its own triageable unit while the proposal remains a single file.
    _step_parts: list[str] = []
    for i, step in enumerate(application_steps, start=1):
        if isinstance(step, str):
            _step_parts.append(f"{i}. {step}")
            continue
        if not isinstance(step, dict):
            _step_parts.append(f"{i}. {step!r}")
            continue
        item_title = step.get("title") or f"Improvement {i}"
        item_linkage = step.get("linkage", "")
        item_steps = step.get("steps", [])
        item_risks = step.get("risks", "")
        independent = step.get("independent", True)
        depends_on = step.get("depends_on") or []
        if depends_on:
            independence_line = f"*Depends on:* improvement(s) {', '.join(f'#{d}' for d in depends_on)}."
        elif independent:
            independence_line = "*Independent:* can be applied without other bundled improvements."
        else:
            independence_line = "*Independent:* no — see linkage / risks for ordering constraints."

        sub_lines = [f"#### {i}. {item_title}", ""]
        if item_linkage:
            sub_lines.append(f"**Linkage:** {item_linkage}")
            sub_lines.append("")
        if item_steps:
            sub_lines.append("**Steps:**")
            for j, s in enumerate(item_steps, start=1):
                sub_lines.append(f"{j}. {s}")
            sub_lines.append("")
        if item_risks:
            sub_lines.append(f"**Risks:** {item_risks}")
            sub_lines.append("")
        sub_lines.append(independence_line)
        _step_parts.append("\n".join(sub_lines))
    steps_block = "\n\n".join(_step_parts)

    # Section 4 effects
    if effects:
        effect_lines = "\n".join(f"- **{e['dimension']}:** {e['change']}" for e in effects)
    else:
        effect_lines = "- **Behavior:** unchanged — fix is structural."

    # Section 5 acceptance criteria (standard five + any extras)
    acceptance_lines = [
        "- [ ] Fix applied to every affected product (not just the one that triggered detection)",
        f"- [ ] `python mcp/noctusai/cli.py --validate` shows 100/100 for the affected product(s)",
        f"- [ ] `python mcp/noctusai/cli.py --review --product {primary}` files no new proposals for this issue",
        "- [ ] Backend tests still pass for the affected product(s)",
        "- [ ] If the change touched shared code, `python mcp/noctusai/cli.py --catalog` shows no new orphans or duplicate candidates",
        "- [ ] Documentation updated KB-first, CLAUDE.md second (per `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md → Docs stay in sync`)",
    ]
    if extra_acceptance:
        for item in extra_acceptance:
            acceptance_lines.append(f"- [ ] {item}")
    acceptance_block = "\n".join(acceptance_lines)

    # Section 6 related files
    related_section = ""
    if related_files:
        rel_lines = "\n".join(f"- `{r['path']}` — {r['note']}" for r in related_files)
        related_section = f"""---

## 6. Related files

{rel_lines}

"""

    body = f"""# Proposal: {title}

**Agent:** {agent}
**Origin:** {origin}
**Generated:** {now}
**Severity:** {severity}
**Effort:** {effort}
**Affected products:** {products_line}
**Status:** {status}

---

## 1. Context

{context}

---

## 2. Situation

{situation}

---

## 3. Proposed Solution

### 3.1 Linkage — why this solution fits this situation

{linkage}

### 3.2 Application instructions

{steps_block}

### 3.3 Seed APIs / shared lib involved

{apis_lines}

### 3.4 Risks before applying

{risks}

### 3.5 Alternatives considered

{alt_lines}

---

## 4. Effects

When this is applied, these change:

{effect_lines}

---

## 5. Acceptance Criteria

{acceptance_block}

{related_section}"""
    return body.rstrip() + "\n"


def file_proposal(
    *,
    title: str,
    body: str,
    agent: str = "keeper",
    project: Optional[str] = None,
    product: Optional[str] = None,
    subdir: Optional[str] = None,
    worktree_path: str | Path | None = None,
) -> dict:
    """Write a fully-rendered proposal markdown to disk.

    Dedups by `title` slug and key entity (see `_proposal_exists`). Returns
    `{created: bool, file: str, path: str}`.

    Destination rules:
    - `project` set → `projects/<slug>/proposals/<agent>-<ts>-<slug>.md`
      (canonical project-scoped layout).
    - `product` set → `products/<product>/proposals/<agent>-<ts>-<slug>.md`
      (keeper/compliance proposals, scoped to the product the detector
      flagged). Optionally combine with `subdir` for evaluations.
    - Neither set → error (every proposal must be scoped to a project or
      product).

    Args:
        title: Used to compute the filename slug + dedup key.
        body: Fully rendered markdown (typically from `fill_proposal_template`).
        agent: Origin tag — filename prefix.
        project: Project name / slug / filename. Lands in
            `projects/<slug>/proposals/`. Mutually exclusive with `product`.
        product: Product slug. Lands in `products/<product>/proposals/`.
            Used for keeper/compliance proposals. Combine with `subdir`
            for evaluation sub-folders.
        subdir: Subdirectory under the product proposals dir (e.g.
            ``evaluations/<ts>``). Only valid when ``product`` is set.
        worktree_path: **Caller-aware path resolution.** When set, the
            proposal lands under the given worktree's ``projects/`` or
            ``products/`` tree instead of the MCP server's startup
            workspace. Engineers in a git worktree pass their worktree
            root; architects on main noc omit. See ``resolve_caller_root``.
    """
    if project and product:
        raise ValueError("Pass only one of `project` / `product` — not both.")
    if subdir and not product:
        raise ValueError("`subdir` requires `product` to be set.")

    projects_dir, products_dir = _resolve_dirs(worktree_path)

    if project:
        slug = _project_slug(project)
        target_dir = _project_proposals_dir(
            slug, projects_dir=projects_dir, products_dir=products_dir,
        )
        target_dir.mkdir(parents=True, exist_ok=True)
    elif product:
        base = _product_proposals_dir(product, products_dir=products_dir)
        target_dir = base / subdir if subdir else base
        target_dir.mkdir(parents=True, exist_ok=True)
        # Dedup only applies to the flat product proposals namespace.
        # Evaluation folders and project folders may carry near-duplicate titles.
        if not subdir and _proposal_exists(
            title, product=product, products_dir=products_dir,
        ):
            return {"created": False, "reason": "duplicate", "file": None}
    else:
        raise ValueError(
            "Every proposal must be scoped: pass `project=` (phase proposals) "
            "or `product=` (keeper/compliance proposals)."
        )

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{agent}-{timestamp}-{_slug(title)}.md"
    filepath = target_dir / filename
    filepath.write_text(body)
    return {
        "created": True,
        "file": filename,
        "path": str(filepath),
        "project": _project_slug(project) if project else None,
        "product": product,
        "subdir": subdir,
    }


def generate_proposal(
    title,
    problem,
    solution,
    affected_products,
    severity="medium",
    effort="medium",
    findings=None,
    agent="keeper",
    product=None,
):
    """Legacy entry point — kept for the skeleton-fallback path in `tools/review.py`.

    When the LLM is unavailable and we still want *some* proposal filed so the
    human sees the finding, this writes a minimal shape. New callers should use
    `fill_proposal_template` + `file_proposal` instead.
    """
    product = product or (affected_products[0] if affected_products else None)
    if not product:
        return {"created": False, "reason": "no product specified"}

    if _proposal_exists(title, product=product):
        return {"created": False, "reason": "duplicate"}

    target_dir = _product_proposals_dir(product)
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{agent}-{timestamp}-{_slug(title)}.md"
    filepath = target_dir / filename

    findings_section = ""
    if findings:
        findings_section = "\n## Findings\n\n" + "".join(f"- {json.dumps(f, default=str)}\n" for f in findings[:20])

    filepath.write_text(f"""# Proposal: {title}

**Agent:** {agent}
**Generated:** {now_utc().strftime("%Y-%m-%d %H:%M")}
**Severity:** {severity}
**Effort:** {effort}
**Affected products:** {', '.join(affected_products)}
**Status:** pending

> **Skeleton proposal** — filed without LLM enrichment (OpenAI unavailable or a
> legacy caller). The reviewer should treat this as a raw detector finding and
> flesh out Problem / Solution manually. See `templates/PROPOSAL-TEMPLATE.md`
> for the canonical shape.

## Problem

{problem}

## Proposed Solution

{solution}
{findings_section}
## Acceptance Criteria

- [ ] All affected products updated
- [ ] All tests pass
- [ ] `python mcp/noctusai/cli.py --validate` shows 100/100 for affected products
- [ ] Documentation updated
""")
    return {"created": True, "file": filename, "path": str(filepath)}


def list_proposals(agent=None, product=None):
    """List proposals across all products (or one product if specified).

    Searches ``products/*/proposals/*.md`` to aggregate keeper/compliance
    proposals. Does NOT include project-phase proposals (those live inside
    ``projects/<slug>/proposals/``) — use project-level listing for those.
    """
    if not PRODUCTS_DIR.exists():
        return []

    if product:
        search_dirs = [_product_proposals_dir(product)]
    else:
        search_dirs = sorted(PRODUCTS_DIR.glob("*/proposals"))

    results = []
    for d in search_dirs:
        if not d.exists():
            continue
        product_name = d.parent.name
        for f in sorted(d.glob("*.md")):
            if f.name in (".gitkeep", "README.md"):
                continue
            parts = f.stem.split("-", 1)
            file_agent = parts[0] if len(parts) > 1 and not parts[0].isdigit() else "unknown"
            if agent and file_agent != agent:
                continue
            content = f.read_text()
            status = "pending"
            if "**status:** accepted" in content.lower():
                status = "accepted"
            elif "**status:** rejected" in content.lower():
                status = "rejected"
            title = ""
            for line in content.splitlines():
                if line.startswith("# Proposal:"):
                    title = line.replace("# Proposal:", "").strip()
                    break
            results.append({"file": f.name, "product": product_name, "agent": file_agent, "title": title, "status": status})
    return results


def update_proposal_status(filename, status, reason="", product=None):
    """Update a proposal's status to accepted/rejected.

    When ``product`` is given, looks in ``products/<product>/proposals/``.
    Otherwise searches all ``products/*/proposals/`` for the file.
    """
    filepath = None
    if product:
        candidate = _product_proposals_dir(product) / filename
        if candidate.exists():
            filepath = candidate
    else:
        # Search across all products
        for d in sorted(PRODUCTS_DIR.glob("*/proposals")):
            candidate = d / filename
            if candidate.exists():
                filepath = candidate
                break
    if filepath is None:
        return {"error": "Proposal not found"}
    content = filepath.read_text()
    content = re.sub(r'\*\*Status:\*\* \w+', f'**Status:** {status}', content)
    if reason and status == "rejected":
        content = content.replace("**Reject** — with reason: ___", f"**Reject** — with reason: {reason}")
    filepath.write_text(content)
    return {"updated": True, "status": status}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.proposal_template",
        description=(
            "Return `templates/PROPOSAL-TEMPLATE.md` content so agents get a consistent "
            "starting point when authoring a proposal. Agents fill every "
            "`{{PLACEHOLDER}}` in the template and submit via `noctus.dev.file_proposal`."
        ),
    )
    def _template() -> dict:
        return {"template": get_proposal_template()}

    @server.tool(
        name="noctus.dev.file_proposal",
        description=(
            "Write a fully-rendered proposal markdown. For project-phase proposals "
            "pass `project=<slug>` — the file lands in `projects/<slug>/proposals/` "
            "(ONE bundled proposal per phase). For keeper/compliance proposals pass "
            "`product=<slug>` — the file lands in `products/<product>/proposals/`. "
            "Agents typically call `noctus.dev.proposal_template`, fill it, then submit "
            "via this tool. Dedups by title slug + key entity. Pass `worktree_path` "
            "when calling from inside a git worktree so the proposal lands in the "
            "worktree, not the MCP server's startup workspace."
        ),
    )
    def _file_proposal(
        title: str,
        body: str,
        agent: str = "keeper",
        project: str | None = None,
        product: str | None = None,
        subdir: str | None = None,
        worktree_path: str | None = None,
    ) -> dict:
        return file_proposal(
            title=title,
            body=body,
            agent=agent,
            project=project,
            product=product,
            subdir=subdir,
            worktree_path=worktree_path,
        )

    @server.tool(
        name="noctus.dev.list_proposals",
        description=(
            "List pending improvement proposals across all products (or one product "
            "if `product` is set)"
        ),
    )
    def _list_proposals(
        agent: str | None = None,
        product: str | None = None,
    ) -> list:
        return list_proposals(agent, product=product)

    @server.tool(
        name="noctus.dev.set_proposal_status",
        description="Accept or reject a proposal. status='accepted' or 'rejected'.",
    )
    def _set_status(
        filename: str, status: str, reason: str = "", product: str | None = None,
    ) -> dict:
        if status not in {"accepted", "rejected"}:
            return {"error": f"invalid status {status!r}; valid: accepted / rejected"}
        return update_proposal_status(filename, status, reason, product=product)
