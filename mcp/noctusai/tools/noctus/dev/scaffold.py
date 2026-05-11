"""Product scaffolding — create new products from the seed framework.

Migrations emitted by the scaffolded product MUST keep the canonical SQL
DDL conventions used elsewhere in the platform. Helpers live at
`noctusai_lib.domain.sql_templates` (`set_search_path`, `updated_at_function`,
`updated_at_trigger`, `rls_subquery_policy`). The bundled `001_seed.sql`
template uses placeholders that resolve to schema-correct SQL on scaffold;
the regression tests at `tests/test_scaffold.py` (TestSqlTemplatesIntegration)
assert the scaffolded migration's `SET search_path` line + RLS policy line
match the helpers' output, so future drift is caught at CI rather than
discovered via a broken migration.

**Two-phase scaffold (post-2026-05-05):**

The platform rule "seed CONTENT does not inherit; every new product's prose
is bespoke" requires that mechanical placeholder substitution alone is
insufficient — left unattended, scaffolded products carry the seed's
narrative DNA in their READMEs and MASTER-PROMPTs. The fix is a two-phase
flow:

1. **Interrogation** (``noctus.dev.scaffold_interrogate``) — returns the
   canonical question set. The agent carries them to the user; the user's
   answers form a ``brief`` dict.
2. **Scaffold with brief** (``noctus.dev.scaffold_product`` with
   ``brief={...}``) — copies the template, writes the brief to disk
   FIRST (durable record, survives any subsequent failure), runs
   mechanical placeholder substitution, then LLM-rewrites every prose
   surface (``README.md``, ``MASTER-PROMPT.md``) so the file speaks
   SPECIFICALLY about the new product, never echoing seed/template
   framing. The system prompt instructs the LLM accordingly.

Skip path — when ``brief=None``: write a stub brief that surfaces the
gap loudly, skip mechanical substitution (per user rule "if questions
skipped: LLM prose without mechanical"), still attempt LLM rewrite using
name+slug context only. Never silent-error.
"""
import asyncio
import concurrent.futures
import logging
import re
import shutil
import subprocess
from pathlib import Path

from workspace import get_noctusai_home, get_workspace_root

logger = logging.getLogger(__name__)


# ─── Interrogation flow ────────────────────────────────────────────────────
#
# Canonical question set the agent walks the user through before scaffolding.
# Stable structure: {key, prompt, required}. Required questions block the
# scaffold UNLESS the user explicitly opts into the skip path (brief=None).
# Edits here ripple to: the .scaffold-brief.md template format, the LLM
# system prompt's brief section, every test that asserts question count.
INTERROGATION_QUESTIONS: list[dict] = [
    {
        "key": "domain",
        "prompt": (
            "What real-world domain does this product serve? "
            "(e.g. 'B2B real estate analytics', 'social media post scheduling', "
            "'mental health therapy sessions')"
        ),
        "required": True,
    },
    {
        "key": "primary_users",
        "prompt": (
            "Who is the primary user? (e.g. 'real estate brokers', "
            "'small business marketing teams', 'licensed therapists')"
        ),
        "required": True,
    },
    {
        "key": "core_entities",
        "prompt": (
            "What are the 3-5 core entities/concepts? "
            "(e.g. for ERP: 'Imovel, Cliente, Negocio, Equipe')"
        ),
        "required": True,
    },
    {
        "key": "primary_workflows",
        "prompt": "Describe 1-3 primary workflows the product enables, end-to-end.",
        "required": True,
    },
    {
        "key": "key_integrations",
        "prompt": (
            "External services this product integrates with "
            "(LLMs, APIs, webhooks, etc.). 'none' is fine."
        ),
        "required": False,
    },
    {
        "key": "success_criteria",
        "prompt": (
            "How will we know the product is doing its job? "
            "(key metrics, user outcomes)"
        ),
        "required": False,
    },
    {
        "key": "naming_conventions",
        "prompt": (
            "Naming conventions specific to this product's domain? "
            "(e.g. 'use Portuguese for entities, English for code')"
        ),
        "required": False,
    },
]

# Prose surfaces — files that get FULL LLM rewrite (not just placeholder
# substitution). Adding a new file here makes it part of the bespoke-rewrite
# contract — the LLM will be invoked once per surface per scaffold call.
PROSE_SURFACES: tuple[str, ...] = ("README.md", "MASTER-PROMPT.md")


def scaffold_interrogate(name: str, slug: str, schema: str) -> dict:
    """Return the canonical question set for a new product scaffold.

    The agent walks the user through these questions before calling
    :func:`scaffold_product` with the captured answers as ``brief={...}``.
    No LLM calls happen here — pure data return; the agent is the
    interrogator (matches project-execution methodology where the planner
    interrogates before designing).

    Returns:
        ``{name, slug, schema, questions: [...], next_step: str}``
    """
    return {
        "name": name,
        "slug": slug,
        "schema": schema,
        "questions": list(INTERROGATION_QUESTIONS),
        "next_step": (
            f"Collect each answer from the user (required questions block "
            f"scaffold; optional ones may be empty). Then call "
            f"scaffold_product(name={name!r}, slug={slug!r}, schema={schema!r}, "
            f"backend_port=..., frontend_port=..., brief={{<key>: <answer>, ...}}). "
            f"Skip path: pass brief=None — surfaces the gap loudly, runs LLM "
            f"prose only on name+slug context, no mechanical substitution."
        ),
    }


def _write_scaffold_brief(target: Path, brief: dict | None) -> dict:
    """Write the brief to ``products/<slug>/.scaffold-brief.md`` BEFORE any
    other file edit. The brief is the durable record of why the product
    exists — future agents inheriting the product read it to recover the
    user's original intent.

    Per user rule (2026-05-05): brief writes happen FIRST; if a later step
    fails, the brief still survives. ``brief=None`` writes a SKIPPED stub
    that surfaces the gap loudly — silent fallback to "no record" is
    forbidden.
    """
    brief_path = target / ".scaffold-brief.md"
    if brief is None:
        body = (
            "# Scaffold brief — SKIPPED\n\n"
            "Interrogation was skipped at scaffold time. Future agents have "
            "no record of the user's original intent for this product. "
            "Prose surfaces (README, MASTER-PROMPT) were generated by LLM "
            "with name + slug + schema context only — they may not reflect "
            "the actual product domain accurately.\n\n"
            "**To recover:** ask the user to fill out the canonical question "
            "set (`noctus.dev.scaffold_interrogate`) retroactively, save the "
            "answers here, then rerun LLM rewrite on prose surfaces with the "
            "captured brief.\n"
        )
    else:
        lines = ["# Scaffold brief\n\n"]
        lines.append(
            "Captured at scaffold time. The LLM-rewritten prose surfaces "
            "(README.md, MASTER-PROMPT.md) reference these answers — "
            "edits here should be propagated to those files manually or via "
            "a re-rewrite pass.\n\n"
        )
        for question in INTERROGATION_QUESTIONS:
            key = question["key"]
            prompt = question["prompt"]
            answer = brief.get(key, "").strip() if isinstance(brief.get(key), str) else brief.get(key)
            lines.append(f"## {prompt}\n\n")
            if answer:
                lines.append(f"{answer}\n\n")
            else:
                lines.append("_(not answered)_\n\n")
        body = "".join(lines)

    try:
        brief_path.write_text(body, encoding="utf-8")
    except OSError as exc:
        return {"skipped": f"OSError writing {brief_path}: {exc}"}
    return {"path": str(brief_path), "skipped_brief": brief is None}


def _llm_system_prompt() -> str:
    """The system prompt instructs the LLM to NEVER echo seed/template
    framing. This is the load-bearing part of the bespoke-content rule."""
    return (
        "You are rewriting a product documentation file (README.md or "
        "MASTER-PROMPT.md) for a new product on the NoctusAI platform.\n\n"
        "The file you are given is a generic seed template. Your job is to "
        "rewrite it so the file speaks SPECIFICALLY about the new product, "
        "as if the new product was conceived standalone.\n\n"
        "HARD RULES:\n"
        "- NEVER mention 'seed', 'template', 'scaffold', 'placeholder', or "
        "any meta-framing that hints the file came from a generator. The new "
        "product was conceived standalone.\n"
        "- Preserve the structural sections (top-level headings) where they "
        "still make sense for the new product's domain. Drop sections that "
        "are seed-only.\n"
        "- Preserve all code references, file paths, env var names, and "
        "command names as-is — only rewrite PROSE.\n"
        "- Ground every prose paragraph in the new product's actual domain "
        "from the brief. Make the README a real README for the new product, "
        "not a generic boilerplate with the slug swapped in.\n"
        "- Output the COMPLETE rewritten file content, ready to write to "
        "disk. No preamble, no explanation, no markdown fence around the "
        "output."
    )


def _llm_user_prompt(
    *,
    name: str,
    slug: str,
    schema: str,
    brief: dict | None,
    template_content: str,
    surface_filename: str,
) -> str:
    """Build the user message: product identity + brief + original template."""
    if brief is None:
        brief_section = (
            "**No brief was provided** (interrogation skipped). Generate "
            "prose using only the name + slug + schema. Make reasonable "
            "domain assumptions from the slug and mark uncertainty "
            "explicitly with 'TODO: confirm with product owner'."
        )
    else:
        brief_lines = []
        for q in INTERROGATION_QUESTIONS:
            answer = brief.get(q["key"]) or "(not answered)"
            brief_lines.append(f"**{q['prompt']}**\n{answer}")
        brief_section = "\n\n".join(brief_lines)

    return (
        f"# New product\n"
        f"Name: {name}\n"
        f"Slug: {slug}\n"
        f"Schema: {schema}\n\n"
        f"# File you're rewriting\n{surface_filename}\n\n"
        f"# Brief (user's answers)\n{brief_section}\n\n"
        f"# Original template content (REWRITE THIS — return only the new content)\n"
        f"```\n{template_content}\n```"
    )


async def llm_rewrite_file_content(
    template_content: str,
    *,
    name: str,
    slug: str,
    schema: str,
    brief: dict | None,
    surface_filename: str,
    provider: str = "anthropic",
    model: str | None = None,
) -> str | None:
    """Call the LLM to rewrite a single prose surface for the new product.

    Returns the rewritten content on success; returns ``None`` (caller
    surfaces) when the LLM call fails. Public seam — tests
    monkey-patch this function directly.

    Provider defaults to ``"anthropic"`` (Claude is the recommended choice
    for prose rewrite; the platform's default is ``"openai"`` per
    ``noctusai_seed.llm_defaults`` but this is a per-call override).
    """
    try:
        # Imported lazily so tests that monkey-patch this function never
        # touch the LLM module's import-time configuration check.
        from noctusai_lib.integrations.llm import chat_completion
    except ImportError as exc:
        logger.warning("LLM module unavailable for scaffold rewrite: %s", exc)
        return None

    try:
        result = await chat_completion(
            messages=[
                {"role": "system", "content": _llm_system_prompt()},
                {
                    "role": "user",
                    "content": _llm_user_prompt(
                        name=name,
                        slug=slug,
                        schema=schema,
                        brief=brief,
                        template_content=template_content,
                        surface_filename=surface_filename,
                    ),
                },
            ],
            provider=provider,
            model=model,
            temperature=0.4,
            max_tokens=4000,
            cache=False,
        )
    except Exception as exc:  # noqa: BLE001 — surface every LLM failure
        logger.warning(
            "LLM rewrite failed for %s (slug=%s): %s",
            surface_filename, slug, exc,
        )
        return None

    return result


def _run_coro_blocking(coro):
    """Run an awaitable to completion from sync code, regardless of whether
    the caller is itself inside a running event loop. Uses a fresh loop in a
    worker thread when the current thread already has one (the MCP server
    case), and ``asyncio.run`` directly otherwise (CLI / direct-import case).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _run_llm_rewrites(
    target: Path,
    *,
    name: str,
    slug: str,
    schema: str,
    brief: dict | None,
    provider: str = "anthropic",
) -> dict[str, dict]:
    """Sync wrapper that calls :func:`llm_rewrite_file_content` for each
    prose surface and writes the result back to disk. LLM failures surface
    in the per-file result dict; never silent-fallback to seed content.
    """
    results: dict[str, dict] = {}
    for surface_name in PROSE_SURFACES:
        surface_path = target / surface_name
        if not surface_path.is_file():
            results[surface_name] = {"skipped": "file not present in template"}
            continue

        try:
            template_content = surface_path.read_text(encoding="utf-8")
        except OSError as exc:
            results[surface_name] = {"failed": f"OSError reading: {exc}"}
            continue

        rewritten = _run_coro_blocking(
            llm_rewrite_file_content(
                template_content,
                name=name,
                slug=slug,
                schema=schema,
                brief=brief,
                surface_filename=surface_name,
                provider=provider,
            )
        )
        if rewritten is None:
            results[surface_name] = {
                "failed": "LLM call returned None — file left as-is (seed content remains)"
            }
            continue

        try:
            surface_path.write_text(rewritten, encoding="utf-8")
        except OSError as exc:
            results[surface_name] = {"failed": f"OSError writing: {exc}"}
            continue

        results[surface_name] = {
            "rewritten": True,
            "bytes": len(rewritten),
            "provider": provider,
        }
    return results

# Workspace-aware: products/ created under the workspace's own root (so
# scaffold_product from a template lands in template's products/, not
# noc's). The seed template lives only in noc — fetched via get_noctusai_home().
# See mcp/noctusai/workspace.py + KB § PATTERNS/seed-workspace.md.
REPO_ROOT = get_workspace_root()
PRODUCTS_DIR = REPO_ROOT / "products"
TEMPLATE_DIR = get_noctusai_home() / "templates" / "product-seed"


# Reserved port ranges — derived from `start.sh` per-product allocations.
# Each entry is (port, product_owner). When extending, also update start.sh
# AND `KB § CONTEXT/02-LANDSCAPE.md` Products table. The `reserve_port_range`
# function uses this list to skip occupied blocks; `list_available_ports`
# uses it to compute the next free port.
RESERVED_RANGES: list[tuple[int, str]] = [
    # Backend ports (8000-range)
    (8000, "core"),
    (8001, "erp-imobiliario"),
    (8002, "personal-finance"),
    (8003, "therapy-platform"),
    (8004, "seed"),
    (8005, "daily-life"),
    (8006, "mailing"),
    (8007, "adconnect"),
    (8009, "dev-team"),
    (8010, "youtube-crawler"),
    (8096, "media-scheduling"),
    # Frontend ports (5173 + 8080-range)
    (5173, "core"),                # Core frontend (Vite default)
    (8080, "erp-imobiliario"),     # ERP frontend
    (8090, "personal-finance"),    # PF frontend
    (8095, "therapy-platform"),    # Therapy frontend
    (8100, "seed"),                # Seed frontend
    (8110, "daily-life"),          # Daily Life frontend
    (8120, "mailing"),             # Mailing frontend
    (8123, "dev-team"),            # Dev Team frontend (off-pattern: see vite.config.ts)
    (8130, "adconnect"),           # AdConnect frontend
    (8140, "media-scheduling"),    # Media Scheduling frontend
    (8150, "youtube-crawler"),     # YouTube Crawler frontend
]


# Known binary file extensions — skipped from text substitution. Anything
# else is treated as text; UnicodeDecodeError caught at read time keeps the
# whitelist short and forward-compatible (previously a positive whitelist of
# code suffixes excluded `.env.example`, `.yaml`, `.toml` etc. — silently
# leaving placeholders un-substituted).
_BINARY_SUFFIXES: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svgz",
    ".pdf", ".zip", ".gz", ".tar", ".bz2", ".xz", ".7z",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".mp4", ".webm", ".mov", ".wav", ".ogg",
    ".so", ".dylib", ".dll", ".exe", ".class", ".pyc",
})


def scaffold_product(
    name: str,
    slug: str,
    schema: str,
    backend_port: int,
    frontend_port: int,
    icon: str = "Box",
    color: str = "#6366f1",
    description: str | None = None,
    *,
    brief: dict | None = None,
    llm_provider: str = "anthropic",
    products_dir: Path | None = None,
    template_dir: Path | None = None,
) -> dict:
    """Create a new product from the seed template.

    Replaces {{PLACEHOLDERS}} with actual values AND emits a numbered
    seed-row migration at ``products/core/backend/migrations/NNN_seed_<slug>_product.sql``
    so the new product auto-registers in the noc dashboard's `products`
    table on next migration apply. Mirror the migration to the live DB
    via `mcp__claude_ai_Supabase__apply_migration` (per "MCP migrations
    mirror the file" rule).
    Returns {created: bool, path: str, files: int, seed_row_migration: str}.

    Args:
        products_dir: Override for the ``products/`` root (test seam).
            Defaults to module-level :data:`PRODUCTS_DIR`. Tests pass
            tmp_path-based dirs; production callers leave it as None.
        template_dir: Override for the seed template root (test seam).
            Defaults to :data:`TEMPLATE_DIR` (noc's
            ``templates/product-seed/``). Tests targeting an in-worktree
            template variant pass an explicit path.
    """
    base_products_dir = products_dir if products_dir is not None else PRODUCTS_DIR
    base_template_dir = template_dir if template_dir is not None else TEMPLATE_DIR
    target = base_products_dir / slug
    if target.exists():
        return {"error": f"Product '{slug}' already exists at {target}"}

    if not base_template_dir.exists():
        return {"error": f"Template not found at {base_template_dir}"}

    # ─── 1. Copy template (skeleton, not content) ───────────────────────
    shutil.copytree(base_template_dir, target, ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".backup", "*.egg-info"))

    # ─── 2. Write the brief FIRST (durable record before any prose edit)
    # Per user rule (2026-05-05): the brief survives any subsequent failure
    # — the user's intent is the most important piece of state on disk.
    brief_write = _write_scaffold_brief(target, brief)

    # ─── 3. Mechanical placeholder substitution ─────────────────────────
    # Per user rule "if questions skipped: LLM prose without mechanical":
    # when brief is absent we SKIP the mechanical pass entirely and let the
    # LLM produce content from name/slug/schema alone. The skip surfaces
    # explicitly in the return — no silent-error.
    file_count = 0
    skipped: list[str] = []
    mechanical_status: dict
    if brief is not None:
        replacements = {
            "{{PRODUCT_NAME}}": name,
            "{{PRODUCT_SLUG}}": slug,
            "{{SCHEMA_NAME}}": schema,
            "{{BACKEND_PORT}}": str(backend_port),
            "{{FRONTEND_PORT}}": str(frontend_port),
            "{{PRODUCT_ICON}}": icon,
        }

        for f in target.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix.lower() in _BINARY_SUFFIXES:
                continue
            try:
                content = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                logger.warning("scaffold: %s is not utf-8 text, skipping substitution", f)
                skipped.append(str(f.relative_to(target)))
                continue
            except OSError as exc:
                logger.warning("scaffold: cannot read %s (%s), skipping", f, exc)
                skipped.append(str(f.relative_to(target)))
                continue
            new_content = content
            for placeholder, value in replacements.items():
                new_content = new_content.replace(placeholder, value)
            if new_content != content:
                try:
                    f.write_text(new_content, encoding="utf-8")
                except OSError as exc:
                    logger.warning("scaffold: cannot write %s (%s)", f, exc)
                    skipped.append(str(f.relative_to(target)))
                    continue
            file_count += 1
        mechanical_status = {"applied": True, "files_processed": file_count}
    else:
        mechanical_status = {
            "applied": False,
            "reason": (
                "brief=None — skipped mechanical placeholder substitution per "
                "the 'questions-skipped' rule. LLM rewrite still runs over "
                "prose surfaces using name+slug+schema only."
            ),
        }

    # ─── 4. LLM rewrite of prose surfaces ───────────────────────────────
    # README.md + MASTER-PROMPT.md get rewritten by the LLM so the new
    # product never inherits the seed's narrative DNA. System prompt
    # explicitly forbids echoing seed/template framing. Always runs,
    # whether brief is present or not — the seed-content-never-leaks rule
    # applies even on the skip path.
    llm_rewrite = _run_llm_rewrites(
        target,
        name=name,
        slug=slug,
        schema=schema,
        brief=brief,
        provider=llm_provider,
    )

    seed_row_migration = _emit_products_seed_row_migration(
        slug=slug,
        name=name,
        description=description,
        icon=icon,
        color=color,
        frontend_port=frontend_port,
        products_dir=base_products_dir,
    )

    start_sh_registration = _register_in_start_sh(
        slug=slug,
        name=name,
        backend_port=backend_port,
        frontend_port=frontend_port,
        repo_root=base_products_dir.parent,
    )

    docker_patch = _patch_workspace_docker_files(
        workspace_root=base_products_dir.parent,
        slug=slug,
        name=name,
        backend_port=backend_port,
        frontend_port=frontend_port,
    )

    # In-noc compose registration — appends include: line to root
    # docker-compose.yml so `docker compose up` brings the new product up
    # alongside the others. No-op for sibling-workspace scaffolds (they
    # have a single workspace-root compose, not a per-product include
    # orchestrator).
    root_compose_registration = _register_in_root_compose(
        slug=slug,
        repo_root=base_products_dir.parent,
    )

    next_steps = [
        f"Add to CLAUDE.md product table",
        f"Run migration: mcp/noctusai tools → noctusai_apply_migration",
        f"Add to PRODUCT_MAP in vite.config.factory.ts",
    ]
    if seed_row_migration.get("path"):
        next_steps.insert(
            0,
            f"Apply seed-row migration to live DB: {seed_row_migration['path']}",
        )
    elif seed_row_migration.get("skipped"):
        next_steps.append(
            "Manually emit products-seed-row migration in noc (this workspace "
            f"has no products/core/backend/migrations/): {seed_row_migration['skipped']}"
        )
    if start_sh_registration.get("skipped"):
        next_steps.append(
            f"Manually add to start.sh (backend {backend_port}, "
            f"frontend {frontend_port}): {start_sh_registration['skipped']}"
        )
    if brief is None:
        next_steps.append(
            "Brief was SKIPPED — interrogation step bypassed. Mechanical "
            "placeholder substitution did not run; LLM prose surfaces "
            "produced from name+slug only. Recover by asking the user the "
            "canonical question set (`noctus.dev.scaffold_interrogate`) "
            "and re-running the scaffold OR re-running just the LLM rewrite."
        )
    failed_surfaces = [
        name for name, result in llm_rewrite.items() if "failed" in result
    ]
    if failed_surfaces:
        next_steps.append(
            "LLM rewrite FAILED for: "
            + ", ".join(failed_surfaces)
            + ". The files still contain seed-template content — fix manually "
            "or rerun the rewrite once the LLM call succeeds."
        )

    return {
        "created": True,
        "path": str(target),
        "files_processed": file_count,
        "skipped_files": skipped,
        "brief_write": brief_write,
        "mechanical_substitution": mechanical_status,
        "llm_rewrite": llm_rewrite,
        "seed_row_migration": seed_row_migration,
        "start_sh_registration": start_sh_registration,
        "docker_patch": docker_patch,
        "root_compose_registration": root_compose_registration,
        "next_steps": next_steps,
    }


def delete_product(
    slug: str,
    *,
    remove_directory: bool = False,
    products_dir: Path | None = None,
) -> dict:
    """Cascading delete — inverse of :func:`scaffold_product`.

    Side-effects (mirroring scaffold_product, in reverse):

    1. **Deactivate row migration.** Emits a numbered migration at
       ``products/core/backend/migrations/NNN_deactivate_<slug>_product.sql``
       that flips ``public.products.ativo = false``. We DEACTIVATE rather than
       DELETE so audit trails / FK references survive — flipping ``ativo``
       hides the product from the dashboard with the same row in place.
       Re-scaffolding later is a no-op against ``ON CONFLICT (slug) DO NOTHING``;
       a deliberate REACTIVATE migration is required to bring the row back
       (intentional friction).
    2. **start.sh unregistration.** Removes the slug's entry from the
       ``PRODUCTS=()`` array between the sentinels. Idempotent on missing slug.
    3. **Optional directory removal.** Default ``remove_directory=False`` —
       caller must opt in. Safety default: a typo'd slug should NOT nuke
       shipped product code.

    ``RESERVED_RANGES`` is intentionally NOT touched — deleted-product ports
    stay reserved as historical record so the same port isn't accidentally
    re-issued. Manual edit of the table is required to free the slot.

    Args:
        slug: Product slug to delete.
        remove_directory: When True, ``shutil.rmtree(products/<slug>/)``.
            Default False — caller opts in explicitly.
        products_dir: Test seam mirroring :func:`scaffold_product`'s. When
            provided, all writes route through it (no real-file writes).

    Returns:
        ``{"deactivate_migration": {...}, "start_sh_unregistration": {...},
            "directory_removal": {...}, "next_steps": [...]}``
    """
    base_products_dir = products_dir if products_dir is not None else PRODUCTS_DIR
    repo_root = base_products_dir.parent

    deactivate_migration = _emit_products_deactivate_migration(
        slug=slug, products_dir=base_products_dir,
    )
    start_sh_unregistration = _unregister_from_start_sh(
        slug=slug, repo_root=repo_root,
    )
    root_compose_unregistration = _unregister_from_root_compose(
        slug=slug, repo_root=repo_root,
    )
    if remove_directory:
        directory_removal = _remove_product_directory(
            slug=slug, products_dir=base_products_dir,
        )
    else:
        directory_removal = {
            "skipped": "remove_directory=False (opt in to physically delete the folder)"
        }

    next_steps: list[str] = []
    if deactivate_migration.get("path"):
        next_steps.append(
            f"Apply deactivate migration to live DB via Supabase MCP "
            f"apply_migration: {deactivate_migration['path']}"
        )
    elif deactivate_migration.get("skipped"):
        next_steps.append(
            f"Manually deactivate row in public.products: "
            f"{deactivate_migration['skipped']}"
        )
    if start_sh_unregistration.get("skipped"):
        next_steps.append(
            f"start.sh unchanged: {start_sh_unregistration['skipped']}"
        )
    if root_compose_unregistration.get("skipped"):
        next_steps.append(
            f"docker-compose.yml unchanged: {root_compose_unregistration['skipped']}"
        )
    if not remove_directory and directory_removal.get("skipped"):
        # Only surface this hint when the directory actually exists — when it
        # doesn't, suggesting "re-run with remove_directory=True" is noise.
        if (base_products_dir / slug).is_dir():
            next_steps.append(
                f"Re-run with remove_directory=True to remove products/{slug}/ "
                "(disabled by default for safety)."
            )
    next_steps.append(
        f"RESERVED_RANGES still reserves the slug's ports for historical "
        "record. Edit mcp/noctusai/tools/noctus/dev/scaffold.py manually to "
        "free the slot if you want to reuse it."
    )

    return {
        "deactivate_migration": deactivate_migration,
        "start_sh_unregistration": start_sh_unregistration,
        "root_compose_unregistration": root_compose_unregistration,
        "directory_removal": directory_removal,
        "next_steps": next_steps,
    }


def _emit_products_deactivate_migration(
    *,
    slug: str,
    products_dir: Path,
) -> dict:
    """Emit a numbered migration that flips ``public.products.ativo`` to
    ``false`` for the given slug. Mirrors :func:`_emit_products_seed_row_migration`'s
    placement / numbering / skip semantics.
    """
    core_migrations = products_dir / "core" / "backend" / "migrations"
    if not core_migrations.is_dir():
        return {"skipped": f"{core_migrations} does not exist"}

    next_number = _next_migration_number(core_migrations)
    slug_for_filename = slug.replace("-", "_")
    filename = f"{next_number:03d}_deactivate_{slug_for_filename}_product.sql"
    path = core_migrations / filename

    body = f"""\
-- ============================================================
-- {next_number:03d} — Deactivate {slug} product row
-- ============================================================
-- Auto-emitted by delete_product. Flips ativo = false so the row stops
-- surfacing on the noc dashboard while preserving the row for audit trails
-- and any FK references. Re-scaffolding later WILL NOT reactivate the row
-- (the seed-row insert uses ON CONFLICT DO NOTHING). To bring it back,
-- author an explicit reactivate migration. Apply via Supabase MCP
-- apply_migration ("MCP migrations mirror the file" rule).
-- ============================================================

UPDATE public.products SET ativo = false WHERE slug = {_sql_text(slug)};
"""
    try:
        path.write_text(body, encoding="utf-8")
    except OSError as exc:
        return {"skipped": f"OSError writing {path}: {exc}"}

    return {"path": str(path), "number": next_number}


def _remove_product_directory(
    *,
    slug: str,
    products_dir: Path,
) -> dict:
    """Physically remove the product's folder. Returns ``{"skipped": ...}``
    if the folder doesn't exist (already gone — treated as no-op for
    idempotency, not an error)."""
    target = products_dir / slug
    if not target.exists():
        return {"skipped": f"{target} does not exist"}
    if not target.is_dir():
        return {"skipped": f"{target} is not a directory"}

    try:
        shutil.rmtree(target)
    except OSError as exc:
        return {"skipped": f"OSError removing {target}: {exc}"}

    return {"path": str(target)}


def _emit_products_seed_row_migration(
    *,
    slug: str,
    name: str,
    description: str | None,
    icon: str,
    color: str,
    frontend_port: int,
    products_dir: Path,
) -> dict:
    """Emit a numbered migration that seeds the new product into `public.products`.

    Lives at `products/core/backend/migrations/NNN_seed_<slug>_product.sql` where
    NNN is `max(existing) + 1`. Returns `{path, number}` on success, or
    `{skipped: <reason>}` when the workspace has no core migrations directory
    (e.g., template workspaces — "templates can't modify noc" rule).

    The file is idempotent (`ON CONFLICT (slug) DO NOTHING`) so re-running the
    migration on a DB that already has the row is a no-op. Operator still
    applies via Supabase MCP — the file is the durable record, the apply is
    the runtime effect.
    """
    core_migrations = products_dir / "core" / "backend" / "migrations"
    if not core_migrations.is_dir():
        return {"skipped": f"{core_migrations} does not exist"}

    next_number = _next_migration_number(core_migrations)
    slug_for_filename = slug.replace("-", "_")
    filename = f"{next_number:03d}_seed_{slug_for_filename}_product.sql"
    path = core_migrations / filename

    desc_sql = _sql_text_or_null(description)
    body = f"""\
-- ============================================================
-- {next_number:03d} — Seed {name} product row
-- ============================================================
-- Auto-emitted by scaffold_product so the new product appears on
-- the noc dashboard (Dashboard.tsx reads /api/auth/me which joins
-- public.products). Apply via Supabase MCP apply_migration to land
-- on the live DB ("MCP migrations mirror the file" rule).
-- ============================================================

INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo)
VALUES (
    {_sql_text(name)},
    {_sql_text(slug)},
    {desc_sql},
    {_sql_text(icon)},
    {_sql_text(f"http://localhost:{frontend_port}")},
    {_sql_text(color)},
    true
)
ON CONFLICT (slug) DO NOTHING;
"""
    try:
        path.write_text(body, encoding="utf-8")
    except OSError as exc:
        logger.warning("scaffold: cannot write %s (%s)", path, exc)
        return {"skipped": f"OSError writing {path}: {exc}"}

    return {"path": str(path), "number": next_number}


_START_SH_REGISTRY_RE = re.compile(
    r"(# BEGIN_PRODUCTS_REGISTRY\n(?:.*?\n)?PRODUCTS=\(\n)(.*?)(\n\)\n# END_PRODUCTS_REGISTRY)",
    re.DOTALL,
)


def _register_in_start_sh(
    *,
    slug: str,
    name: str,
    backend_port: int,
    frontend_port: int,
    repo_root: Path,
) -> dict:
    """Append a `PRODUCTS=(...)` entry to ``start.sh`` between the
    ``BEGIN_PRODUCTS_REGISTRY`` / ``END_PRODUCTS_REGISTRY`` sentinels so the
    new product starts alongside the rest on `bash start.sh`.

    Idempotent: if an entry for ``slug`` already exists in the array, returns
    ``{"skipped": "<reason>"}`` without touching the file. Sentinel-missing
    or start.sh-missing → ``{"skipped": ...}`` (caller surfaces the manual
    step). Format mirrors the array in start.sh:
    ``"<slug>:<Display Name>:<backend_port>:<frontend_port>"``.

    Returns ``{"path": str, "entry": str}`` on success.
    """
    start_sh = repo_root / "start.sh"
    if not start_sh.is_file():
        return {"skipped": f"{start_sh} does not exist"}

    try:
        content = start_sh.read_text(encoding="utf-8")
    except OSError as exc:
        return {"skipped": f"OSError reading {start_sh}: {exc}"}

    match = _START_SH_REGISTRY_RE.search(content)
    if not match:
        return {
            "skipped": (
                f"{start_sh} missing BEGIN_PRODUCTS_REGISTRY / END_PRODUCTS_REGISTRY "
                "sentinels around the PRODUCTS=(...) array"
            )
        }

    head, body, tail = match.group(1), match.group(2), match.group(3)
    entry = f'  "{slug}:{name}:{backend_port}:{frontend_port}"'

    # Idempotency — match any line whose first colon-segment equals slug.
    slug_token = f'"{slug}:'
    for line in body.splitlines():
        if slug_token in line:
            return {"skipped": f"slug '{slug}' already registered in start.sh"}

    new_body = body.rstrip("\n") + "\n" + entry
    new_block = head + new_body + tail
    new_content = content[: match.start()] + new_block + content[match.end():]

    try:
        start_sh.write_text(new_content, encoding="utf-8")
    except OSError as exc:
        return {"skipped": f"OSError writing {start_sh}: {exc}"}

    return {"path": str(start_sh), "entry": entry.strip()}


def _unregister_from_start_sh(
    *,
    slug: str,
    repo_root: Path,
) -> dict:
    """Inverse of :func:`_register_in_start_sh`: remove a single slug's
    line from the ``PRODUCTS=()`` array between the
    ``BEGIN_PRODUCTS_REGISTRY`` / ``END_PRODUCTS_REGISTRY`` sentinels.

    Idempotent: slug-not-found returns ``{"skipped": ...}`` rather than
    raising — a deletion-of-an-unknown-product is a no-op, not an error.
    Sentinels-missing or start.sh-missing also surface as skipped.

    Returns ``{"path": str, "removed_entry": str}`` on success.
    """
    start_sh = repo_root / "start.sh"
    if not start_sh.is_file():
        return {"skipped": f"{start_sh} does not exist"}

    try:
        content = start_sh.read_text(encoding="utf-8")
    except OSError as exc:
        return {"skipped": f"OSError reading {start_sh}: {exc}"}

    match = _START_SH_REGISTRY_RE.search(content)
    if not match:
        return {
            "skipped": (
                f"{start_sh} missing BEGIN_PRODUCTS_REGISTRY / END_PRODUCTS_REGISTRY "
                "sentinels around the PRODUCTS=(...) array"
            )
        }

    head, body, tail = match.group(1), match.group(2), match.group(3)
    slug_token = f'"{slug}:'
    kept_lines: list[str] = []
    removed_entry: str | None = None
    for line in body.splitlines():
        if slug_token in line and removed_entry is None:
            removed_entry = line.strip()
            continue
        kept_lines.append(line)

    if removed_entry is None:
        return {"skipped": f"slug '{slug}' not found in start.sh PRODUCTS array"}

    new_body = "\n".join(kept_lines)
    new_block = head + new_body + tail
    new_content = content[: match.start()] + new_block + content[match.end():]

    try:
        start_sh.write_text(new_content, encoding="utf-8")
    except OSError as exc:
        return {"skipped": f"OSError writing {start_sh}: {exc}"}

    return {"path": str(start_sh), "removed_entry": removed_entry}


# ─── Root docker-compose include: list registration ─────────────────────
# Mirror of _register_in_start_sh / _unregister_from_start_sh, but for the
# root docker-compose.yml's `include:` block. New products are appended
# between BEGIN_PRODUCTS_INCLUDE / END_PRODUCTS_INCLUDE sentinels so
# `docker compose up` at the repo root brings the new product up alongside
# the others. Idempotent on re-scaffold.
_ROOT_COMPOSE_INCLUDE_RE = re.compile(
    r"(# BEGIN_PRODUCTS_INCLUDE\n)(.*?)(  # END_PRODUCTS_INCLUDE)",
    re.DOTALL,
)


def _register_in_root_compose(*, slug: str, repo_root: Path) -> dict:
    """Append a `- products/<slug>/docker-compose.yml` line to the root
    `docker-compose.yml`'s `include:` block, between
    BEGIN_PRODUCTS_INCLUDE / END_PRODUCTS_INCLUDE sentinels.

    Idempotent on re-scaffold; returns ``{"skipped": ...}`` when the slug
    is already in the list, or when the compose file / sentinels are
    missing (caller surfaces the manual step).

    Returns ``{"path": str, "entry": str}`` on success.
    """
    compose = repo_root / "docker-compose.yml"
    if not compose.is_file():
        return {"skipped": f"{compose} does not exist"}

    try:
        content = compose.read_text(encoding="utf-8")
    except OSError as exc:
        return {"skipped": f"OSError reading {compose}: {exc}"}

    match = _ROOT_COMPOSE_INCLUDE_RE.search(content)
    if not match:
        return {
            "skipped": (
                f"{compose} missing BEGIN_PRODUCTS_INCLUDE / END_PRODUCTS_INCLUDE "
                "sentinels around the include: list"
            )
        }

    head, body, tail = match.group(1), match.group(2), match.group(3)
    # Multi-line `path:` block: extended include syntax so the per-product
    # `docker-compose.override.yml` is auto-merged at root. See
    # KB § PATTERNS/containerization.md §11d "Dev override compose".
    entry = (
        f"  - path:\n"
        f"      - products/{slug}/docker-compose.yml\n"
        f"      - products/{slug}/docker-compose.override.yml"
    )

    # Idempotency — match any line whose path segment ends with /<slug>/.
    slug_token = f"/{slug}/docker-compose.yml"
    for line in body.splitlines():
        if slug_token in line:
            return {"skipped": f"slug '{slug}' already registered in root docker-compose include:"}

    new_body = body.rstrip("\n") + "\n" + entry + "\n"
    new_content = content[: match.start()] + head + new_body + tail + content[match.end():]

    try:
        compose.write_text(new_content, encoding="utf-8")
    except OSError as exc:
        return {"skipped": f"OSError writing {compose}: {exc}"}

    return {"path": str(compose), "entry": entry.strip()}


def _unregister_from_root_compose(*, slug: str, repo_root: Path) -> dict:
    """Inverse of :func:`_register_in_root_compose`: remove a single slug's
    line from the root `docker-compose.yml`'s `include:` block.

    Idempotent on missing slug. Returns ``{"path": str, "removed_entry": str}``
    on success, or ``{"skipped": ...}`` when slug not found, sentinels
    missing, or compose file missing.
    """
    compose = repo_root / "docker-compose.yml"
    if not compose.is_file():
        return {"skipped": f"{compose} does not exist"}

    try:
        content = compose.read_text(encoding="utf-8")
    except OSError as exc:
        return {"skipped": f"OSError reading {compose}: {exc}"}

    match = _ROOT_COMPOSE_INCLUDE_RE.search(content)
    if not match:
        return {
            "skipped": (
                f"{compose} missing BEGIN_PRODUCTS_INCLUDE / END_PRODUCTS_INCLUDE "
                "sentinels around the include: list"
            )
        }

    head, body, tail = match.group(1), match.group(2), match.group(3)
    slug_token = f"/{slug}/docker-compose.yml"
    slug_override_token = f"/{slug}/docker-compose.override.yml"
    # Two shapes to remove:
    #   (a) Legacy single-line:    - products/<slug>/docker-compose.yml
    #   (b) Extended path block:   - path:
    #                                  - products/<slug>/docker-compose.yml
    #                                  - products/<slug>/docker-compose.override.yml
    # Strategy: walk the body, drop the matching slug's lines + any
    # contiguous `path:` parent + sibling override line.
    lines = body.splitlines()
    kept_lines: list[str] = []
    removed_entry: str | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if slug_token in line and removed_entry is None:
            removed_entry = stripped
            # Look back: was the prior kept line `- path:`? If so, drop
            # it (the path: parent is exclusively ours).
            if kept_lines and kept_lines[-1].strip() == "- path:":
                kept_lines.pop()
            # Look ahead: is the next line our sibling override entry?
            # If so, skip it too.
            j = i + 1
            if j < len(lines) and slug_override_token in lines[j]:
                i = j + 1
                continue
            i += 1
            continue
        kept_lines.append(line)
        i += 1

    if removed_entry is None:
        return {"skipped": f"slug '{slug}' not found in root docker-compose include:"}

    new_body = "\n".join(kept_lines)
    if new_body and not new_body.endswith("\n"):
        new_body += "\n"
    new_content = content[: match.start()] + head + new_body + tail + content[match.end():]

    try:
        compose.write_text(new_content, encoding="utf-8")
    except OSError as exc:
        return {"skipped": f"OSError writing {compose}: {exc}"}

    return {"path": str(compose), "removed_entry": removed_entry}


_MIGRATION_NUMBER_RE = re.compile(r"^(\d{3})_")


def _next_migration_number(migrations_dir: Path) -> int:
    """Return the next integer number for a migration in `migrations_dir`.

    Scans `NNN_*.sql` files; returns max(NNN)+1. Empty dir → 1.
    """
    highest = 0
    for entry in migrations_dir.iterdir():
        if entry.suffix.lower() != ".sql":
            continue
        match = _MIGRATION_NUMBER_RE.match(entry.name)
        if match:
            number = int(match.group(1))
            if number > highest:
                highest = number
    return highest + 1


def _sql_text(value: str) -> str:
    """Quote a string for SQL `'...'` literal use, escaping single quotes."""
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _sql_text_or_null(value: str | None) -> str:
    """`NULL` for None, otherwise quoted SQL text."""
    if value is None:
        return "NULL"
    return _sql_text(value)


def _scan_start_sh_ports() -> tuple[set[int], set[int]]:
    """Parse start.sh for `--port <N>` occurrences. Returns (backend, frontend).

    Heuristic: ports < 8100 (and != 5173) → backend; everything else → frontend.
    Kept tolerant — start.sh missing returns empty sets, never raises.
    """
    used_backend: set[int] = set()
    used_frontend: set[int] = set()
    start_sh = REPO_ROOT / "start.sh"
    if not start_sh.exists():
        return used_backend, used_frontend
    content = start_sh.read_text()
    for match in re.finditer(r"--port (\d+)", content):
        port = int(match.group(1))
        if port == 5173 or port >= 8080 and port < 8100 or port >= 8100:
            # 5173 is the Vite default for Core frontend; 8080+ are frontends
            if port < 8080:
                used_backend.add(port)
            else:
                used_frontend.add(port)
        else:
            used_backend.add(port)
    return used_backend, used_frontend


def _patch_workspace_docker_files(
    *,
    workspace_root: Path,
    slug: str,
    name: str,
    backend_port: int,
    frontend_port: int,
) -> dict:
    """Substitute scaffold placeholders in the workspace-root docker
    artifacts emitted by ``bootstrap-seed-workspace.sh``.

    The bootstrap drops ``Dockerfile`` / ``Dockerfile.frontend`` /
    ``docker-compose.yml`` / ``.env.example`` carrying ``{{PRODUCT_SLUG}}``,
    ``{{PRODUCT_NAME}}``, ``{{BACKEND_PORT}}``, ``{{FRONTEND_PORT}}``
    placeholders. Substitute them in place when scaffold_product runs
    inside a workspace, so ``docker compose up`` works immediately after
    the first product is scaffolded.

    No-op when the docker files are missing (in-noc scaffold path: noc
    has its own per-product Dockerfile under ``products/<slug>/backend/``
    + a different compose strategy at the repo root) OR when the files
    have already been patched (idempotent — first-product wins; later
    products in the same workspace need to extend the compose file
    manually since one workspace + one set of docker files is the
    canonical N=1 shape).

    Returns ``{"patched": [files], "skipped": [files]}``.
    """
    docker_files = [
        "Dockerfile",
        "Dockerfile.frontend",
        "docker-compose.yml",
        ".env.example",
        "start.sh",
        "stop.sh",
    ]
    replacements = {
        "{{PRODUCT_NAME}}": name,
        "{{PRODUCT_SLUG}}": slug,
        "{{BACKEND_PORT}}": str(backend_port),
        "{{FRONTEND_PORT}}": str(frontend_port),
    }

    patched: list[str] = []
    skipped: list[str] = []

    for fname in docker_files:
        path = workspace_root / fname
        if not path.is_file():
            skipped.append(f"{fname} (not present — workspace pre-bootstrap or in-noc scaffold)")
            continue

        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            skipped.append(f"{fname} (read failed: {exc})")
            continue

        if "{{PRODUCT_SLUG}}" not in content and "{{BACKEND_PORT}}" not in content:
            skipped.append(f"{fname} (already patched — placeholders absent)")
            continue

        new_content = content
        for placeholder, value in replacements.items():
            new_content = new_content.replace(placeholder, value)

        try:
            path.write_text(new_content, encoding="utf-8")
        except OSError as exc:
            skipped.append(f"{fname} (write failed: {exc})")
            continue

        # start.sh / stop.sh must remain executable. write_text preserves
        # the file's existing mode on macOS / linux; bootstrap dropped them
        # +x. Re-stamp defensively so a non-+x copy (e.g., from a tarball
        # extract on Windows + WSL) still produces a runnable script.
        if fname in {"start.sh", "stop.sh"}:
            try:
                mode = path.stat().st_mode
                path.chmod(mode | 0o111)
            except OSError as exc:
                skipped.append(f"{fname} chmod (non-fatal: {exc})")

        patched.append(fname)

    return {"patched": patched, "skipped": skipped}


def list_available_ports() -> dict:
    """Find the next available backend and frontend ports.

    The set of "used" ports unions the static :data:`RESERVED_RANGES` table
    with whatever `start.sh` actually wires (defensive — methodology says the
    table IS the source of truth, but products land in start.sh first when
    docs lag).
    """
    used_backend: set[int] = {p for p, _ in RESERVED_RANGES if p < 8080 and p != 5173}
    used_frontend: set[int] = {p for p, _ in RESERVED_RANGES if p == 5173 or p >= 8080}

    sh_backend, sh_frontend = _scan_start_sh_ports()
    used_backend |= sh_backend
    used_frontend |= sh_frontend

    next_backend = max(used_backend) + 1 if used_backend else 8000
    next_frontend = max(used_frontend) + 10 if used_frontend else 8080

    return {
        "next_backend_port": next_backend,
        "next_frontend_port": next_frontend,
        "used_backend": sorted(used_backend),
        "used_frontend": sorted(used_frontend),
    }


def _find_contiguous_block(used: set[int], start: int, count: int, *, step: int = 1) -> int:
    """Return the first port `p >= start` such that `p, p+step, ..., p+(count-1)*step`
    are all absent from `used`. Pure / deterministic — used by the
    range-reservation helper.
    """
    if count <= 0:
        raise ValueError("count must be >= 1")
    candidate = start
    while True:
        block = [candidate + i * step for i in range(count)]
        if not any(b in used for b in block):
            return candidate
        # Skip past the first collision to avoid quadratic walks.
        candidate += step


def reserve_port_range(
    *,
    product_slug: str,
    count_backend: int = 1,
    count_frontend: int = 1,
) -> dict:
    """Reserve a contiguous backend block + a contiguous frontend block.

    Returns the FIRST available block of `count_backend` consecutive backend
    ports (default starts at the next free port after the highest reserved)
    and the same shape for frontend. Default `count=1` keeps back-compat with
    single-port allocations: `reserve_port_range(product_slug="x")` yields one
    backend + one frontend port equivalent to `list_available_ports()`'s
    `next_*` keys.

    Does NOT mutate :data:`RESERVED_RANGES` — caller is responsible for
    landing the allocation in start.sh + KB landscape table + this constant.
    The function's contract is "tell me the next free block"; persistence
    stays a human/architect step.

    Returns:
        {
            "product_slug": str,
            "backend_ports": [int, ...],   # length == count_backend
            "frontend_ports": [int, ...],  # length == count_frontend
            "rationale": str,              # human-readable picked-because text
        }
    """
    if count_backend < 1 or count_frontend < 1:
        return {
            "error": (
                f"count_backend ({count_backend}) and count_frontend "
                f"({count_frontend}) must each be >= 1"
            )
        }

    used_backend: set[int] = {p for p, _ in RESERVED_RANGES if p < 8080 and p != 5173}
    used_frontend: set[int] = {p for p, _ in RESERVED_RANGES if p == 5173 or p >= 8080}
    sh_backend, sh_frontend = _scan_start_sh_ports()
    used_backend |= sh_backend
    used_frontend |= sh_frontend

    # Backend search starts at the next slot above the highest used backend.
    backend_start = (max(used_backend) + 1) if used_backend else 8000
    backend_first = _find_contiguous_block(used_backend, backend_start, count_backend)
    backend_ports = [backend_first + i for i in range(count_backend)]

    # Frontend search starts at the next 10-aligned slot above the highest
    # used frontend (matches the "+10" stride convention `list_available_ports`
    # uses, so blocks stay visually grouped per-product).
    frontend_high = max(p for p in used_frontend if p >= 8080) if any(p >= 8080 for p in used_frontend) else 8070
    frontend_start = ((frontend_high // 10) + 1) * 10
    frontend_first = _find_contiguous_block(used_frontend, frontend_start, count_frontend)
    frontend_ports = [frontend_first + i for i in range(count_frontend)]

    return {
        "product_slug": product_slug,
        "backend_ports": backend_ports,
        "frontend_ports": frontend_ports,
        "rationale": (
            f"Backend block starts at {backend_first} (first free contiguous "
            f"{count_backend}-port slot after {sorted(used_backend)[-1] if used_backend else 'n/a'}). "
            f"Frontend block starts at {frontend_first} (next 10-aligned after "
            f"{frontend_high})."
        ),
    }


# ─── Testing-ground (sibling-to-noc seed workspace) ────────────────────────
#
# Wraps `scripts/bootstrap-seed-workspace.sh` so the agent can spin up an
# isolated sandbox workspace via MCP rather than asking the user to run a
# shell command. Routing rule (see memory `feedback_testing_ground_vs_in_noc.md`):
# user asks for "testing ground / sandbox / isolated workspace" → this tool;
# user asks for "create new product / absorb a product" → `scaffold_product`
# in-noc. Full design at KB § PATTERNS/seed-workspace.md.

def create_testing_ground(
    target: str,
    *,
    name: str | None = None,
    force: bool = False,
    noc_home: Path | None = None,
) -> dict:
    """Create a sibling-to-noc seed workspace for isolated experimentation.

    Wraps ``scripts/bootstrap-seed-workspace.sh`` from noc. The resulting
    workspace is a sibling folder consuming noc strictly read-only via
    symlinks (CLAUDE.md, KB, .claude/, mcp/, seed/, noctusai_lib/, templates/)
    with isolated ``projects/``, ``sandbox/``, ``products/``, and its own git
    history. Three intended use cases (per KB § PATTERNS/seed-workspace.md):
    sandbox for throwaway experiments, new-product staging, parallel-agent
    isolation.

    Use this when the user asks for a "testing ground", "sandbox", or
    "isolated workspace". For in-noc product creation/absorption, use
    :func:`scaffold_product` instead — that one lands the product at
    ``<noc>/products/<slug>/``.

    Args:
        target: Path where the workspace will be created. Relative paths
            resolve against noc's parent directory (so a target of
            ``"adconnect-sandbox"`` lands at
            ``<parent-of-noc>/adconnect-sandbox`` — matches the canonical
            ``<parent>/noctusai-template`` layout from the KB pattern).
            Absolute paths pass through unchanged.
        name: Workspace label written to the ``.noctusai-workspace`` marker.
            Defaults to the target's basename.
        force: Overwrite a non-empty target dir that lacks the marker. Use
            only when you've verified the dir is safe to clobber.
        noc_home: Override for the noc repo root. Defaults to
            :func:`get_noctusai_home` (the canonical noc path discovered via
            workspace marker walk-up; falls back to file-relative resolution).

    Returns:
        ``{"created": bool, "path": str, "stdout": str, "stderr": str,
            "returncode": int, "next_steps": [...]}``
    """
    noc_root = noc_home if noc_home is not None else get_noctusai_home()
    script = noc_root / "scripts" / "bootstrap-seed-workspace.sh"
    if not script.is_file():
        return {
            "created": False,
            "error": f"bootstrap script not found at {script}",
        }

    target_path = Path(target).expanduser()
    if not target_path.is_absolute():
        target_path = (noc_root.parent / target_path).resolve()

    cmd = ["bash", str(script), "--target", str(target_path)]
    if name:
        cmd.extend(["--name", name])
    if force:
        cmd.append("--force")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return {
            "created": False,
            "error": f"OSError running bootstrap script: {exc}",
            "command": " ".join(cmd),
        }

    created = result.returncode == 0 and target_path.is_dir()
    next_steps: list[str] = []
    if created:
        next_steps.extend([
            f"cd {target_path} to start working in the testing ground.",
            "Inside the workspace, the same MCP toolkit is available "
            "(symlinked); workspace-aware tools resolve to the workspace's "
            "own projects/ + products/ via the .noctusai-workspace marker.",
            "Throwaway scratch belongs under sandbox/ (no manifest required). "
            "Anything intended for noc lands under projects/ or products/ + "
            "an entry in .promotions/<slug>.md.",
            "Promote additions back via "
            "`noctus.dev.promote_from_seed_workspace` (refer to "
            "KB § PATTERNS/seed-workspace.md for the full workflow).",
        ])
    else:
        next_steps.append(
            "Bootstrap failed — inspect stderr below; common causes: target "
            "exists without --force, target inside noc (refused), missing "
            "noc surfaces, or insufficient permissions."
        )

    return {
        "created": created,
        "path": str(target_path),
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
        "command": " ".join(cmd),
        "next_steps": next_steps,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.scaffold_interrogate",
        description=(
            "Phase 1 of the two-phase scaffold flow: returns the canonical "
            "question set the agent walks the user through before scaffolding "
            "a new product. Captured answers form the `brief` argument to "
            "`noctus.dev.scaffold_product`. The user's intent is recorded "
            "durably in `products/<slug>/.scaffold-brief.md` so future "
            "agents inherit the design rationale."
        ),
    )
    def _interrogate(name: str, slug: str, schema: str) -> dict:
        return scaffold_interrogate(name=name, slug=slug, schema=schema)

    @server.tool(
        name="noctus.dev.scaffold_product",
        description=(
            "Phase 2 of the two-phase scaffold flow: creates a new product "
            "from the seed skeleton, writes the brief to disk FIRST, runs "
            "mechanical placeholder substitution, LLM-rewrites prose surfaces "
            "(README.md, MASTER-PROMPT.md) so the new product never inherits "
            "the seed's narrative DNA, emits the dashboard seed-row migration, "
            "and registers the product in start.sh. Pass brief=None to enter "
            "the skip path (mechanical substitution skipped; LLM rewrite "
            "uses name+slug only; surfaced loudly in next_steps)."
        ),
    )
    def _scaffold(
        name: str,
        slug: str,
        schema: str,
        backend_port: int,
        frontend_port: int,
        icon: str = "Box",
        color: str = "#6366f1",
        description: str | None = None,
        brief: dict | None = None,
        llm_provider: str = "anthropic",
    ) -> dict:
        return scaffold_product(
            name,
            slug,
            schema,
            backend_port,
            frontend_port,
            icon,
            color=color,
            description=description,
            brief=brief,
            llm_provider=llm_provider,
        )

    @server.tool(
        name="noctus.dev.delete_product",
        description=(
            "Cascading delete (inverse of scaffold_product): emits a "
            "deactivate-row migration for public.products, removes the slug "
            "from start.sh's PRODUCTS array, and optionally removes "
            "products/<slug>/ when remove_directory=True (default off for "
            "safety). Apply the emitted migration via Supabase MCP. "
            "RESERVED_RANGES is left intact — deleted ports stay reserved "
            "as historical record."
        ),
    )
    def _delete(
        slug: str,
        remove_directory: bool = False,
    ) -> dict:
        return delete_product(slug, remove_directory=remove_directory)

    @server.tool(
        name="noctus.dev.create_testing_ground",
        description=(
            "Create a sibling-to-noc seed workspace for isolated "
            "experimentation. Wraps scripts/bootstrap-seed-workspace.sh. "
            "Use when the user asks for a 'testing ground', 'sandbox', or "
            "'isolated workspace' — produces a sibling folder that consumes "
            "noc strictly read-only via symlinks, with isolated projects/, "
            "sandbox/, products/, and its own git history. For in-noc "
            "product creation/absorption use noctus.dev.scaffold_product "
            "instead. Relative `target` resolves against noc's parent dir."
        ),
    )
    def _create_testing_ground(
        target: str,
        name: str | None = None,
        force: bool = False,
    ) -> dict:
        return create_testing_ground(target, name=name, force=force)

    @server.tool(
        name="noctus.dev.available_ports",
        description="Find next available backend and frontend ports",
    )
    def _available_ports() -> dict:
        return list_available_ports()

    @server.tool(
        name="noctus.dev.reserve_port_range",
        description=(
            "Reserve a contiguous backend block + frontend block for a new "
            "product. Returns the first free contiguous N-port slot in each "
            "range. Default count=1 mirrors `available_ports`."
        ),
    )
    def _reserve_port_range(
        product_slug: str,
        count_backend: int = 1,
        count_frontend: int = 1,
    ) -> dict:
        return reserve_port_range(
            product_slug=product_slug,
            count_backend=count_backend,
            count_frontend=count_frontend,
        )
