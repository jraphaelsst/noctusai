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


def _reexec_under_venv() -> None:
    """Self-heal the interpreter: re-exec under the project venv when needed.

    The CLI's tools import `pydantic` / `noctusai_lib`, which live ONLY in the
    project venv (``mcp/noctusai/.venv`` — the same interpreter the MCP server
    runs under, per ``.mcp.json``). When the documented ``python
    mcp/noctusai/cli.py …`` resolves to a bare host interpreter without those
    deps, the CLI used to crash with ``ModuleNotFoundError: No module named
    'pydantic'``. This guard transparently re-execs under the venv so the
    documented command works regardless of which ``python`` is first on PATH.

    No-op when the deps are already importable (we're under the venv, or a host
    env that happens to have them). A sentinel env var prevents an exec loop if
    even the venv is missing deps (fresh clone before ``pip install``), letting
    the original import error surface honestly rather than spinning.
    """
    import os

    if os.environ.get("_NOCTUS_CLI_REEXEC") == "1":
        return  # already re-execed once — don't loop; let the real error show
    try:
        import pydantic  # noqa: F401 — canonical "real env is active" probe
        return
    except ImportError:
        pass
    venv_py = Path(__file__).resolve().parent / ".venv" / "bin" / "python"
    if not venv_py.exists():
        return  # fresh clone before `pip install` — fall through to import error
    os.environ["_NOCTUS_CLI_REEXEC"] = "1"
    os.execv(str(venv_py), [str(venv_py), str(Path(__file__).resolve()), *sys.argv[1:]])


_reexec_under_venv()

# Configure platform-standard logging BEFORE importing any tools/* module —
# imports may attach loggers; the formatter must be in place when they fire.
# Falls back to `logging.basicConfig` if `noctusai_lib` is not installed in
# this venv (e.g. fresh clone before `pip install -r requirements.txt`).
try:
    from noctusai_lib.logging_config import auto_configure_for_cli
    auto_configure_for_cli("noctusai-mcp-cli")
except ImportError as exc:
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    # Selective severity: when `noctusai_lib` itself is missing (the
    # expected case for a fresh clone or a one-shot CLI invocation
    # outside the venv), emit DEBUG — it's noise. When some OTHER dep
    # is missing (anthropic, supabase, redis, …), keep WARNING so the
    # operator sees a real broken state instead of a misleading "all
    # good" run.
    _missing = str(exc)
    _level = logging.DEBUG if "'noctusai_lib'" in _missing else logging.WARNING
    logging.getLogger(__name__).log(
        _level,
        "cli: noctusai_lib import failed (%s); using basicConfig fallback. "
        "If the message names a missing dep OTHER than noctusai_lib, run "
        "`pip install -r mcp/noctusai/requirements.txt` from %s.",
        exc, Path(__file__).parents[2],
    )

GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


_LLM_CONFIGURED = False


def _ensure_llm_configured() -> bool:
    """Lazily call `noctusai_lib.configure_llm()` with an env-driven key_provider.

    Idempotent — only fires once per process. Returns True if config landed,
    False if the LLM lib isn't importable (graceful-degrade for fresh clones
    or no-key environments). Reads /repo/.env if `OPENAI_API_KEY` isn't
    already in the process env so the operator doesn't have to `source .env`
    before every CLI invocation.
    """
    global _LLM_CONFIGURED
    if _LLM_CONFIGURED:
        return True
    import os
    import subprocess
    # Auto-source .env so OPENAI_API_KEY lands in os.environ. Two candidates:
    # 1. The current repo root (parents[2] of this file).
    # 2. The PRIMARY git worktree's repo root (when this is a linked worktree,
    #    .env is gitignored and doesn't replicate — must read primary's copy).
    if not os.environ.get("OPENAI_API_KEY"):
        candidates: list[Path] = [Path(__file__).resolve().parents[2] / ".env"]
        try:
            wt_out = subprocess.run(
                ["git", "worktree", "list", "--porcelain"],
                capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2],
            )
            for line in wt_out.stdout.splitlines():
                if line.startswith("worktree "):
                    primary = Path(line[len("worktree "):]) / ".env"
                    if primary not in candidates:
                        candidates.append(primary)
                    break  # first line = primary
        except (OSError, subprocess.SubprocessError):
            pass
        for env_file in candidates:
            if not env_file.exists():
                continue
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
            if os.environ.get("OPENAI_API_KEY"):
                break
    try:
        from noctusai_lib import LLMConfig
        from noctusai_lib.integrations.llm.client import configure_llm, get_llm_config
        try:
            get_llm_config()  # already configured?
            _LLM_CONFIGURED = True
            return True
        except RuntimeError:
            pass
        config = LLMConfig(
            key_provider=lambda provider, org_id=None: os.environ.get(
                f"{provider.upper()}_API_KEY"
            ),
        )
        configure_llm(config)
        _LLM_CONFIGURED = True
        return True
    except ImportError:
        return False


def main():
    parser = argparse.ArgumentParser(description="NoctusAI — platform dev toolkit")
    parser.add_argument("--validate", action="store_true", help="Check seed compliance")
    parser.add_argument("--check-phase-state", action="store_true", help="Check §6 ↔ §11 phase-state consistency across PROJECT.md files. Exits 1 on any high-severity issue. Used by the pre-commit hook to block commits that ship mismatch.")
    parser.add_argument("--refs", metavar="PATTERN", help="Find every reference to PATTERN (literal string) across CLAUDE.md / KB / projects / mcp / seed / products. Replaces the manual `grep -rln` ritual.")
    parser.add_argument("--graph-build", nargs="?", const="repo", metavar="SCOPE", help="Build the noc knowledge graph and write `.noc-graph/{graph.json,graph.html,REPORT.md}`. Scope: `repo` (default), `product:<slug>`, `seed`, `kb`. Materializes the implicit relational index (AST + authored prose; no LLM). Backed by noctusai_lib.graph + the noctus.graph.* MCP umbrella.")
    parser.add_argument("--graph-output", metavar="DIR", help="With --graph-build: write artifacts to DIR (default `<repo>/.noc-graph`).")
    parser.add_argument("--graph-memory-root", metavar="DIR", help="With --graph-build: include agent memory dir (e.g. `~/.claude/projects/<workspace>/memory`).")
    parser.add_argument("--build", action="store_true", help="Run `npx vite build` across product frontends in parallel. Combine with `--changed` to scope to git-changed products + `--product P` to scope to one.")
    parser.add_argument("--changed", action="store_true", help="With --build / --test: scope to products with changes since HEAD (uses `git diff --name-only HEAD`).")
    parser.add_argument("--status", action="store_true", help="Cross-project state digest. Walks every PROJECT.md + reports status / sub-task progress / last-updated / flags.")
    parser.add_argument("--check-three-way-sync", action="store_true", help="Verify KB ↔ CLAUDE.md ↔ memory parity. Closes the gap that `verify-kb-sync.sh` cannot cover (memory lives outside the repo).")
    parser.add_argument("--scan-recurrence", action="store_true", help="Scan target files (product main.py / conftest.py / config) for repeated lines that should be absorbed into seed. N=2 → triage; N=3+ → MUST formalize per `KB § PATTERNS/project-execution.md § 2.7`.")
    parser.add_argument("--scan-helpers", action="store_true", help="Scan service/router/hook files for function/class NAMES recurring across products. Catches the absorption shape `--scan-recurrence` misses (`_safe_float`, `useMetas`, `_PipelineHooks`, etc.). Use BEFORE writing a new helper — if the name shows up here, absorb into `noctusai_lib` instead of reimplementing.")
    parser.add_argument("--scan-service-lines", action="store_true", help="Scan service/router lines for verbatim repetition across products. Catches ad-hoc patterns the helper-name scan misses (`datetime.fromisoformat(s.replace(\"Z\", \"+00:00\"))`, `raise HTTPException(...)` shapes, pagination expressions). Strict filter: line must be ≥60 chars + contain a function call.")
    parser.add_argument("--scan-blocks", action="store_true", help="AST-walk service/router files; find recurring try/except SHAPES (identifiers normalized away). Catches multi-line block patterns the line/name scans miss — e.g. 7 best-effort `audit_service.log` try/except blocks in core. Pair with `--scan-helpers` and `--scan-service-lines` for full absorption coverage.")
    parser.add_argument("--scan-within-product", action="store_true", help="Find helper names duplicated N+ times INSIDE one product (across files). Closes the gap that cross-product scans require N≥2 products. Use `--min-count` to tune (default 3).")
    parser.add_argument("--scan-pydantic", action="store_true", help="Find Pydantic BaseModel field-set shapes that recur across products. Catches the absorption signal the class-name scan misses — same field set under different class names. Each finding suggests `noctusai_lib.schemas.<canonical>`.")
    parser.add_argument("--scan-test-fixtures", action="store_true", help="Find pytest fixtures + test helpers recurring across products' test trees (conftest.py, tests/services, tests/routers, tests/integration). Stricter blacklist than `--scan-helpers` — excludes test_* methods + ALL_CAPS sample-data names. Catches `_db_with_grants`, `pytest_configure`, mock-builder shapes.")
    parser.add_argument("--scan-migrations", action="store_true", help="Scan SQL migration files for RLS policy / FK index / trigger / search_path patterns recurring across products. 5 known shapes probed; reports which products write each shape and how many times. RLS/trigger templates are absorption candidates for `noctusai_lib.sql.<helper>`.")
    parser.add_argument("--check-outlined", action="store_true", help="Keeper: every STAGED .py/.ts/.tsx must be AST-outline-able (no SyntaxError / parse failure). Exits 1 on any un-outline-able staged file. Used by the pre-commit hook so the platform stays AST-readable + narrow-read/AST-first tooling always functional.")
    parser.add_argument("--check-claude-md-router", action="store_true", help="Keeper: CLAUDE.md router discipline — §1 rules are ONE line (rule + `→` pointer, no inlined bodies) and the whole file stays under the word budget. Exits 1 on any violation. Pre-commit gate when CLAUDE.md is staged. MCP keeper check_claude_md_router; KB § PATTERNS/claude-md-router-discipline.md.")
    parser.add_argument("--check-memory-md-index", action="store_true", help="Keeper: MEMORY.md auto-loaded-index discipline (sibling of --check-claude-md-router) — every `- [Title](file.md)` entry stays under the per-line cap and the whole file under the KB budget. MEMORY.md is OUT-OF-REPO (Claude-Code per-project store), so this gates at `validate` + this CLI flag, NOT at git commit. Silent skip if the per-project memory dir isn't configured. MCP keeper check_memory_md_index; sibling KB § PATTERNS/claude-md-router-discipline.md.")
    parser.add_argument("--check-skill-format", action="store_true", help="Keeper: every .claude/skills/<name>/SKILL.md has valid required frontmatter (name: matching dir + non-empty description: with trigger phrases). Harness-layer authoring discipline.")
    parser.add_argument("--check-agent-format", action="store_true", help="Keeper: every .claude/agents/<name>.md has valid required frontmatter (name: matching filename + description: + EXPLICIT tools:). Omitting `tools:` inherits ~400 deferred tool names (KB § PATTERNS/dispatch-engineer-tuning.md).")
    parser.add_argument("--check-agent-archetype-contract", action="store_true", help="Keeper: advisor agents (architect/security/compliance-reviewer) declare NO Edit/Write in tools: (read-only contract enforced at the tool layer). Executor agents (backend-engineer/frontend-engineer/devops-engineer/engineer-seed) body references `engineer-seed` protocol.")
    parser.add_argument("--refresh-keeper-cache", action="store_true", help="Refresh the local keeper-pattern cache (.claude/cache/keeper-patterns.sqlite) from compliance.py + tests. Mirrors the keepers so doc-authoring agents can lookup patterns BEFORE authoring (avoid gated rework). Pair --force to bypass the in-sync short-circuit. Auto-run by pre-commit on compliance.py change; lazy-rebuilt on query-time source_sha mismatch. KB § PATTERNS/keeper-pattern-cache.md.")
    parser.add_argument("--keeper-pattern-lookup", metavar="KEEPER_OR_FILE", help="Query the keeper-pattern cache by keeper-name substring OR file path (e.g. .claude/agents/devops-engineer.md → agent-format + agent-archetype). Print matching pattern rows. The keeper-check-before-doc'ing discipline starts here.")
    parser.add_argument("--check-keeper-cache-freshness", action="store_true", help="Keeper: the local cache must mirror compliance.py — cache_meta.source_sha must equal sha256(compliance.py). Severity high. Pre-commit gate (auto-refresh) + standalone CLI check. Run --refresh-keeper-cache to fix. (Pair --force with --refresh-keeper-cache to rebuild even when in-sync; the existing --force flag is shared.)")
    parser.add_argument("--refresh-agent-context-cache", action="store_true", help="Refresh the local agent-context cache (.claude/cache/agent-context.sqlite) from .claude/agents/*.md + each agent's owns_kb-declared KB paths. At dispatch, an agent's compact bundle (frontmatter + body + per-owned-KB extract) replaces N Reads. Per-agent bundle_sha guards in-sync agents; --force rebuilds anyway. Pair with --agent <name> to limit scope. Auto-run by pre-commit on agent.md OR owned-KB change. KB § PATTERNS/agent-context-architecture.md.")
    parser.add_argument("--agent-context", metavar="AGENT_NAME", help="Print the compact agent-context bundle for an agent — frontmatter + body + per-owned-KB compact extract. Lazy-rebuilds on bundle_sha mismatch.")
    parser.add_argument("--agent", metavar="AGENT_NAME", help="(scope flag) Limit --refresh-agent-context-cache to a single agent. No-op without --refresh-agent-context-cache.")
    parser.add_argument("--check-agent-context-cache-freshness", action="store_true", help="Keeper: the agent-context cache must mirror each agent's bundle_sha = sha256(agent.md ∪ owned_kb files). Severity high. Pre-commit gate (auto-refresh) + standalone CLI check. Run --refresh-agent-context-cache to fix.")
    parser.add_argument("--refresh-auto-improvement-cache", action="store_true", help="Refresh the local auto-improvement cache (.claude/cache/auto-improvement.sqlite) from project-history/auto-improvement.ndjson. The scoped-auto-improvement system's mirror leg. Tech-leads / agents consult this cache BEFORE editing a doc/agent to surface relevant past observations. Auto-run by pre-commit on ndjson change. KB § PATTERNS/scoped-auto-improvement.md.")
    parser.add_argument("--auto-improvement-query", metavar="TARGET", help="Consult the auto-improvement cache for a target (path substring) — the consult-before-editing discipline. Returns most-recent-first list of surfaced drift/improvement observations relevant to that doc/agent.")
    parser.add_argument("--check-auto-improvement-cache-freshness", action="store_true", help="Keeper: the auto-improvement cache must mirror the ndjson ledger. Severity high. Pre-commit gate (auto-refresh) + standalone CLI check. Run --refresh-auto-improvement-cache to fix.")
    parser.add_argument("--check-codification-pipeline-health", action="store_true", help="Meta-keeper: verify the codification pipeline (s1→s2→s3→s4) is FLOWING. Surfaces warning when no s2/s3/s4 entries have landed within configured silence thresholds. Severity warning (advisory). KB § PATTERNS/common/scoped-auto-improvement.md.")
    parser.add_argument("--check-project-has-dispatch-routing", action="store_true", help="Stage-4 keeper: every PROJECT.md with §6 phases must carry §4a Dispatch routing (slice→lens · codification expectations s1-s4 · routes-not-taken · notes contract). Projects whose PROJECT.md first-commit predates 2026-05-26 are grandfathered automatically. Severity warning. KB § PATTERNS/common/dispatch-with-project-and-notes.md.")
    parser.add_argument("--codify-log", nargs=3, metavar=("STAGE", "TARGET", "DESCRIPTION"), help="Log a codification event with s-stage progression enforcement. STAGE ∈ {s1-emergent, s2-memory, s3-codified, s4-keeper}. TARGET = KB path / agent / keeper name. DESCRIPTION = what+why (min 20 chars). Enforces invariants: s4 requires preceding s3 for same target; s3 requires preceding s1|s2. Pass --force to bypass for backfill / same-commit compression. Solves the 5×-backfill slip from 2026-05-26. KB § PATTERNS/common/methodology-codification-pipeline.md.")
    parser.add_argument("--codify-source-ref", help="Optional provenance for --codify-log (commit SHA / session ID / project slug).")
    parser.add_argument("--vps-exec-sql", nargs=3, metavar=("SQL_FILE", "CONTAINER", "DB"), help="Execute a SQL script inside a containerized DB on the VPS. SQL_FILE = path to local .sql file (contents are streamed). Wraps the docker-cp+docker-exec-psql idiom (the working alternative to the silent-fail `ssh docker exec psql <<EOF` heredoc path). MCP: noctus.vps.exec_sql. KB § PATTERNS/devops/containerization-operations.md.")
    parser.add_argument("--vps-exec-sql-user", help="Override Postgres user for --vps-exec-sql (default = DB name).")
    parser.add_argument("--vps-exec-sql-host", default="noctus-vps", help="SSH host alias for --vps-exec-sql (default noctus-vps).")
    parser.add_argument("--vps-exec-sql-no-cleanup", action="store_true", help="Skip the tmp-file cleanup for --vps-exec-sql (debug only — leaves /tmp/<file>.sql in place on host + container).")
    parser.add_argument("--check-prod-cache-reachable", action="store_true", help="Safety gate: when NOCTUS_CACHE_BACKEND=postgres, verify the prod cache is reachable + pgvector extension installed. NO-OP for sqlite default. Severity high. KB § PATTERNS/devops/prod-deploy-safety-gates.md.")
    parser.add_argument("--check-cache-backend-env-matches-environment", action="store_true", help="Advisory: NOCTUS_CACHE_BACKEND env should match the detected environment (CI=postgres / container=postgres / local=sqlite). Severity warning. KB § PATTERNS/devops/prod-deploy-safety-gates.md.")
    parser.add_argument("--check-drift-shield", action="store_true", help="Pre-deploy DRIFT-SHIELD: surface OPEN auto-improvement entries touching files changed in origin/prod..origin/main. Severity warning. KB § PATTERNS/devops/prod-deploy-safety-gates.md.")
    parser.add_argument("--check-slip-shield", action="store_true", help="Pre-deploy SLIP-SHIELD: surface s2-memory codification slip candidates touching files in this deploy. Severity warning. KB § PATTERNS/devops/prod-deploy-safety-gates.md.")
    parser.add_argument("--check-pre-deploy-gate", action="store_true", help="Composite pre-deploy gate: runs reachable + backend-env + drift-shield + slip-shield in sequence. Use in CI / pre-deploy automation. KB § PATTERNS/devops/prod-deploy-safety-gates.md.")
    parser.add_argument("--check-contextualize-alignment", action="store_true", help="Keeper: CONTEXTUALIZE.md is the fresh-agent read map and must remain pointer-only (sibling discipline to check_claude_md_router). Enforces (a) file exists at repo root, (b) line cap, (c) every canonical-cores entry is referenced. Severity high.")
    parser.add_argument("--check-canonical-organ-consumption", action="store_true", help="Keeper: products must consume canonical cached organs from @noctusai/lib — no local re-implementations. Named-seam extensions allowed when declared. Severity high. KB § PATTERNS/architect/products-consume-canonical-organs.md.")
    parser.add_argument("--check-auth-boundary-false-green", action="store_true", help="Keeper: auth-boundary test assertions must NOT pair 401 with a maskable code — `status_code in (401, 404)` or `in (401, 422)` is a false-green escape hatch (route-absent ⇒ 404, or body-validation-before-auth ⇒ 422; test passes even when auth never fired). Only static AST analysis catches this class. Severity warning (advisory). KB § PATTERNS/compliance/auth-boundary-false-green.md.")
    parser.add_argument("--check-dangling-remote-branches", action="store_true", help="Keeper: flag origin/* branches with unique content older than 7 days. Squash-aware (git-cherry + subject-on-dev). Advisory-only (severity warning); never a commit-blocker. Surfaces in review + session-end sweep. KB § CONTEXT/PATTERNS/common/learn-before-archive.md.")
    parser.add_argument("--check-eight-way-sync", action="store_true", help="Keeper: the 8-way methodology surface sync (CLAUDE.md / MEMORY.md / .claude/agents/ / KB / CONTEXTUALIZE.md / .claude/skills/ / .claude/commands/ / .claude/cache/). Composition gate — re-runs kb_sync + contextualize + agent_kb + skills_listed + commands_listed + memory_md_index + all_cache_freshness sub-keepers. Severity high. KB § PATTERNS/common/eight-way-sync.md.")
    parser.add_argument("--check-seven-way-sync", action="store_true", help="DEPRECATED: back-compat alias for --check-eight-way-sync. Prints a one-line deprecation warning and dispatches to the new flag. Target removal: ~1 cycle.")
    parser.add_argument("--check-six-way-sync", action="store_true", help="DEPRECATED: back-compat alias for --check-eight-way-sync (two promotions back). Will be removed once external callers migrate.")
    parser.add_argument("--check-all-cache-freshness", action="store_true", help="Keeper: composes the 8 per-cache freshness keepers (keeper-patterns / agent-context / auto-improvement / code-embeddings / noc-graph / kb-embeddings / corpus-embeddings / memory-embeddings) into one named gate — the 8th methodology surface (.claude/cache/, live agent read path). Severity per-sub-keeper. KB § PATTERNS/common/eight-way-sync.md.")
    parser.add_argument("--check-skills-listed-in-router", action="store_true", help="Keeper sub-leg of check_eight_way_sync: every .claude/skills/<name>/ MUST be referenced in CLAUDE.md §2 'Procedure skills' line; every skill named in CLAUDE.md MUST exist on disk. Severity high.")
    parser.add_argument("--check-commands-listed-in-router", action="store_true", help="Keeper sub-leg of check_eight_way_sync: every .claude/commands/<name>.md MUST be referenced in CLAUDE.md §2 'Slash commands' line; every command named in CLAUDE.md MUST exist on disk. Severity high.")
    parser.add_argument("--refresh-kb-embeddings", action="store_true", help="Re-populate the local KB embeddings cache (.claude/cache/kb-embeddings.sqlite) from KNOWLEDGE-BASE/**/*.md. Embeds via OpenAI text-embedding-3-small through noctusai_lib.integrations.llm (no new external dep). ADDITIVE discovery layer — does not replace owns_kb / INDEX.md / grep. KB § PATTERNS/common/kb-vector-search.md.")
    parser.add_argument("--refresh-memory-embeddings", action="store_true", help="Re-populate the local memory-embeddings cache (.claude/cache/memory-embeddings.sqlite) from the out-of-repo agent memory dir (`~/.claude/projects/<workspace>/memory/`). Per-file source_sha skip. KB § PATTERNS/common/memory-embeddings.md.")
    parser.add_argument("--memory-search", metavar="QUERY", help="Semantic search over agent memory. Returns top-K chunks by cosine similarity. Pair --top-k N.")
    parser.add_argument("--refresh-corpus-embeddings", action="store_true", help="Re-populate the local corpus-embeddings cache (.claude/cache/corpus-embeddings.sqlite) from CHANGELOG.md + templates/ + .claude/agents/*.md FULL body + .claude/skills/**/SKILL.md + PROJECT-HISTORY.md. KB § PATTERNS/common/corpus-embeddings.md.")
    parser.add_argument("--corpus-search", metavar="QUERY", help="Semantic search over the in-repo corpus (heterogeneous; pair --source-type to scope to changelog/template/agent/skill/history).")
    parser.add_argument("--source-type", metavar="TYPE", help="With --corpus-search: scope to one source type (changelog/template/agent/skill/history).")
    parser.add_argument("--check-memory-embeddings-cache-freshness", action="store_true", help="Keeper: memory-embeddings cache source_sha matches the on-disk memory dir. KB § PATTERNS/common/memory-embeddings.md.")
    parser.add_argument("--check-corpus-embeddings-cache-freshness", action="store_true", help="Keeper: corpus-embeddings cache source_sha matches the in-repo corpus files. KB § PATTERNS/common/corpus-embeddings.md.")
    parser.add_argument("--kb-search", metavar="QUERY", help="Semantic search over the KB — embeds the query, returns top-K KB chunks by cosine similarity. Use for fuzzy-intent queries where exact terminology is unknown. For named patterns, use grep + INDEX.md.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results to return for --kb-search (default 5).")
    parser.add_argument("--check-kb-embeddings-cache-freshness", action="store_true", help="Keeper: KB embeddings cache should mirror each KB doc's sha256. Severity WARNING (not high) — vector search is advisory; stale cache degrades discovery but never breaks correctness. Auto-refresh in pre-commit on KB doc change.")
    parser.add_argument("--refresh-code-embeddings", action="store_true", help="Re-populate the local code embeddings cache (.claude/cache/code-embeddings.sqlite) from the tracked source roots (mcp/, noctusai_lib/, products/seed/). Python files chunked at module-level FunctionDef/AsyncFunctionDef/ClassDef via stdlib ast; TS/TSX one chunk per file. ADDITIVE discovery layer — does not replace grep / scan_recurrence. KB § CONTEXT/PATTERNS/common/code-embeddings.md.")
    parser.add_argument("--refresh-noc-graph", action="store_true", help="Rebuild the noc-graph cache (.claude/cache/noc-graph.sqlite) — the 8th keeper-mirror cache. Aggregates code (AST) + KB + harness (.claude/agents+skills+commands) + landscape (CLAUDE.md+CLAUDE/+CONTEXTUALIZE.md) + memory + cli flags + auto-improvement events into a structured graph. Per-aggregate-source-sha skip when in-sync. Also re-derives .noc-graph/{graph.json,graph.html,REPORT.md}. KB § PATTERNS/architect/noc-graph.md.")
    parser.add_argument("--check-noc-graph-cache-freshness", action="store_true", help="Keeper: noc-graph cache aggregate_source_sha matches the live aggregate over (code corpus + KB + harness + landscape + memory + cli + history). KB § PATTERNS/architect/noc-graph.md.")
    parser.add_argument("--check-graph-extractor-corpus-sanity", action="store_true", help="Keeper (warning severity): light corpus floor-checks on the noc-graph cache content — node/edge kind floors that catch a buggy extractor producing a fresh-but-wrong cache. Paired with test_graph_extractor_correctness.py (full regression). KB § PATTERNS/common/extractor-correctness-vs-mirror.md.")
    parser.add_argument("--code-search", metavar="QUERY", help="Semantic search over the code corpus — embeds the query, returns top-K matching code symbols by cosine similarity. Use for fuzzy-intent queries ('find helpers that extract a phone number') where exact identifiers are unknown.")
    parser.add_argument("--check-code-embeddings-cache-freshness", action="store_true", help="Keeper: code embeddings cache should mirror each source file's sha256. Severity WARNING (advisory layer). Auto-refresh in pre-commit on staged .py/.ts/.tsx change.")
    parser.add_argument("--kb-ratify", metavar="REASON", help="Snapshot the current kb_validate_owns_kb findings as approved-canonical baseline. REQUIRED reason explains why (future-us reads it). Persists durably to project-history/kb-baselines/. KB § CONTEXT/PATTERNS/common/vector-baseline.md.")
    parser.add_argument("--kb-baseline-diff", metavar="AGAINST", nargs="?", const="latest", help="Compare current owns_kb validation against a ratified baseline (default: latest). Shows new_findings + resolved_findings + corpus-drift flag — the signal-vs-noise differentiator.")
    parser.add_argument("--kb-baseline-list", action="store_true", help="Chronological summary of every ratified baseline — id, ratified_at, reason, finding_count.")
    parser.add_argument("--check-kb-semantic-drift", action="store_true", help="Keeper: surfaces when live owns_kb validation diverges from latest ratified baseline by > threshold. Severity WARNING. Suggests ratification when no baseline exists yet.")
    parser.add_argument("--code-ratify", metavar="REASON", help="Snapshot the current code_recurrence_scan output as approved-canonical baseline. REQUIRED reason explains why. Persists durably to project-history/code-baselines/. Sister of --kb-ratify.")
    parser.add_argument("--code-baseline-diff", metavar="AGAINST", nargs="?", const="latest", help="Compare current code recurrence matches against a ratified baseline (default: latest). Shows new_matches + resolved_matches + corpus-drift flag.")
    parser.add_argument("--code-baseline-list", action="store_true", help="Chronological summary of every ratified code-recurrence baseline.")
    parser.add_argument("--check-code-recurrence-drift", action="store_true", help="Keeper: surfaces when live code recurrence scan diverges from latest ratified baseline by > threshold. Severity WARNING.")
    parser.add_argument("--scan-outlined", action="store_true", help="Audit: scan the WHOLE platform (products/seed/mcp/scripts/noctusai_lib) for files the AST/outline tooling cannot read. Read-only — surfaces the un-outline-able pattern so it can be fixed. MCP-exposed as noctus.dev.scan_outlined.")
    parser.add_argument("--scan-remediation-markers", action="store_true", help="Batch-sweep + triage the NOC-REMEDIATE deferral markers (KB § PATTERNS/remediation-markers.md): parse class + age, group by class, flag malformed (no class/date) + FORBIDDEN on-`except` markers, surface classes at N≥3 (promote to project/seed lift). MCP-exposed as noctus.dev.scan_remediation_markers; exit 1 on defects. Pass --worktree-path to scan an isolated worktree.")
    parser.add_argument("--scan-wiring", metavar="PRODUCT", help="Static wiring-check for ONE product (the product-internal-wiring rule, legs 2/4/5). Scans products/<PRODUCT>/frontend + /backend for: (A) FE api.<method>('<path>') calls with no matching backend route (404 class); (B) selecting `name` on a nome-table (plans/products/organizations — the 500 class); (C) Promise.all([bare fetches]) under one shared try/catch (all-zeros class). Route-exists != wired. MCP-exposed as noctus.dev.scan_wiring; pass --worktree-path to scan an isolated worktree.")
    parser.add_argument("--min-count", type=int, default=None, help="Override min_count threshold for any --scan-* (default varies per scan).")
    parser.add_argument("--review", action="store_true", help="Observation-only review. Default: return issues + prompt for the in-session agent. --headless fires OpenAI gpt-4o-mini. --evaluate writes both paths side-by-side to proposals/evaluations/. NEVER modifies code.")
    parser.add_argument("--headless", action="store_true", help="With --review: author proposals via OpenAI (no in-session agent required).")
    parser.add_argument("--evaluate", action="store_true", help="With --review: write OpenAI proposals to proposals/evaluations/ for side-by-side comparison with agent-authored versions.")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model for --headless / --evaluate. Default: gpt-4o-mini.")
    parser.add_argument("--analyze", action="store_true", help="Run all analyzers")
    parser.add_argument("--discover", action="store_true", help="AI-powered discovery")
    parser.add_argument("--metrics", action="store_true", help="Code metrics")
    parser.add_argument("--sync-prompts", action="store_true", help="Sync all MASTER-PROMPTs")
    parser.add_argument("--test", action="store_true", help="Run all backend tests")
    # `--build` is defined above (parallel + scoped version supersedes the
    # legacy sequential build-all wrapper).
    parser.add_argument("--proposals", action="store_true", help="List proposals")
    parser.add_argument("--verify-kb-sync", action="store_true", help="Verify CLAUDE.md pointers + KB INDEX.md are in sync")
    # ── Absorbed-script flags (scripts-mcp-absorption: every former
    # scripts/*.sh|*.py is now a noctus.dev.* tool; these flags are the
    # muscle-memory CLI surface + the pre-commit thin-dispatcher entry). ──
    parser.add_argument("--mole", metavar="MODE", choices=["scan", "sweep"], help="Storage-hygiene mole (absorbed scripts/mole.sh). MODE=scan|sweep. Pair --force for a destructive sweep. MCP: noctus.dev.mole.")
    parser.add_argument("--update-kb-counts", action="store_true", help="Regenerate KB derived count blocks (absorbed scripts/update-kb-counts.py). Pair --check for drift-only (exit 1 on drift). MCP: noctus.dev.kb_sync.")
    parser.add_argument("--check", action="store_true", help="Drift-check mode for --update-kb-counts / --render-project-history / --gen-promotions-index / --propagate (report only, exit 1 on drift; no write).")
    parser.add_argument("--force", action="store_true", help="Authorize the destructive path for --mole sweep / --archive-clean / --cleanup-stale-worktrees (default = dry-run/report).")
    parser.add_argument("--sync-seed-template", action="store_true", help="Sync products/seed → templates/product-seed (absorbed scripts/sync-seed-template.sh). Pair --dry for preview. MCP: noctus.dev.sync_seed_template.")
    parser.add_argument("--dry", action="store_true", help="Preview mode for --sync-seed-template / --propagate (no write).")
    parser.add_argument("--stamp-seed-version", action="store_true", help="Stamp short SHA + /VERSION SemVer into seed _version_static.py. MCP: noctus.dev.stamp_seed_version.")
    parser.add_argument("--check-version-bump", action="store_true", help="Gate MAJOR-bump authorization: refuse working-tree VERSION whose MAJOR exceeds HEAD's unless .major-bump-authorized marker exists. Autonomous PATCH/MINOR pass. KB § PATTERNS/common/versioning.md. MCP: noctus.dev.version_guard.")
    parser.add_argument("--render-project-history", action="store_true", help="Render project-history/ledger.ndjson → PROJECT-HISTORY.md (absorbed scripts/render-project-history.py). Pair --check for drift gate. MCP: noctus.dev.render_project_history.")
    parser.add_argument("--backfill-project-history", action="store_true", help="Stamp historical ledger rows from archive/ (absorbed scripts/backfill-project-history.py). Pair --dry. MCP: noctus.dev.backfill_project_history.")
    parser.add_argument("--gen-promotions-index", action="store_true", help="Regenerate a seed-workspace's derived PROMOTIONS.md (absorbed scripts/gen-promotions-index.py). Pair --check for the drift gate. MCP: noctus.dev.gen_promotions_index.")
    parser.add_argument("--archive-clean", action="store_true", help="Keep today+yesterday archive folders, classify D-2+ stale (absorbed scripts/archive-clean.sh). USER-INVOKED; pair --force to delete. MCP: noctus.dev.archive_clean.")
    parser.add_argument("--check-disk-usage", action="store_true", help="Disk-pressure monitor 70/80/90 bands (absorbed scripts/disk-usage-monitor.sh). MCP: noctus.dev.check_disk_usage.")
    parser.add_argument("--check-framework-deps", action="store_true", help="Audit product frontend package.json framework-dep parity (absorbed scripts/check-framework-deps.py). MCP: noctus.dev.check_framework_deps.")
    parser.add_argument("--cleanup-stale-worktrees", action="store_true", help="Remove worktrees merged to origin/main (absorbed scripts/cleanup-stale-worktrees.sh). Dry-run unless --force. MCP: noctus.dev.cleanup_stale_worktrees.")
    parser.add_argument("--tmp-cleanup", action="store_true", help="Sweep retired engineer-dispatch patch artifacts from /tmp (patch-id-on-dev OR aged-out OR malformed). DRY-RUN unless --force. MCP: noctus.dev.tmp_cleanup.")
    parser.add_argument("--tmp-cleanup-max-age-days", type=int, default=14, help="With --tmp-cleanup: age threshold beyond which unmatched patches are retired (default 14).")
    parser.add_argument("--cache-pull", action="store_true", help="Pull remote prod pgvector cache → local SQLite (inverse of cache_deploy_mirror). Bootstrap a fresh-clone / new-machine without paying ~30 min OpenAI re-embed. Pair --cache-pull-only to scope. MCP: noctus.dev.cache_pull. KB § PATTERNS/common/cache-portable-architecture.md.")
    parser.add_argument("--cache-pull-only", metavar="NAMES", help="With --cache-pull: comma-separated subset (e.g. 'kb-embeddings,code-embeddings'). Default = all.")
    parser.add_argument("--check-merge-debt", action="store_true", help="Unmerged-to-origin/main backlog monitor (absorbed scripts/merge-debt-monitor.sh, read-only). MCP: noctus.dev.check_merge_debt.")
    parser.add_argument("--propagate", metavar="TARGET", choices=["composes", "dockerfiles", "both"], nargs="?", const="both", help="Containerization codegen from products/seed/ (absorbed scripts/propagate-{composes,dockerfiles}.sh). Pair --check (drift gate) or --dry. MCP: noctus.dev.propagate.")
    parser.add_argument("--smoke-fleet", action="store_true", help="Post-fleet-up /api/health smoke (absorbed scripts/smoke-fleet.sh). Exit 0 healthy / 1 degraded. MCP: noctus.dev.smoke_fleet.")
    parser.add_argument("--predeploy-check", metavar="PRODUCT", help="Pre-deploy gate for a product: framework-dep parity + frontend build + backend pytest; classify failures, auto-fix the framework-dep class (with --fix), report+learn unknowns. Exit 0 ready / 1 blocked. MCP: noctus.dev.predeploy_check.")
    parser.add_argument("--fix", action="store_true", help="With --predeploy-check: auto-fix the safe (framework-dep) failure class in-process.")
    parser.add_argument("--deploy-pull", action="store_true", help="Run the §2a safe-pull drill on the deploy target over SSH (inspect→decide→backup→ff-only→verify). DRY-RUN unless --deploy-confirm; refuses non-FF / deploy-local overlap; never emits reset/checkout/clean/push. MCP: noctus.dev.deploy_pull.")
    parser.add_argument("--deploy-confirm", action="store_true", help="With --deploy-pull: actually perform the ff-only merge (a production action). Without it, plan/dry-run only.")
    parser.add_argument("--deploy-target", default="origin/prod", help="With --deploy-pull: the ref the VPS fast-forwards to (default origin/prod).")
    parser.add_argument("--deploy-host", default="noctus-vps", help="With --deploy-pull/--deploy-image: the SSH host alias for the deploy target (default noctus-vps).")
    parser.add_argument("--deploy-image", metavar="PRODUCT", help="Atomic product-image redeploy with rollback (§2a C2): snapshot :previous → compose pull → up -d → health-probe → roll back on health failure. DRY-RUN unless --deploy-image-confirm; never emits rmi/prune/down. MCP: noctus.dev.deploy_image.")
    parser.add_argument("--deploy-image-confirm", action="store_true", help="With --deploy-image: actually perform the image swap (a production action). Without it, plan/dry-run only.")
    parser.add_argument("--deploy-image-source", default="pull", choices=["pull", "local"], help="With --deploy-image: 'pull' (GHCR model, default) compose-pulls the image; 'local' (build-on-VPS model) swaps an already-built local tag.")
    parser.add_argument("--catalog", action="store_true", help="Regenerate shared-library catalog (symbols, importers, orphans, duplicates)")
    parser.add_argument("--component-bundle", metavar="NAME", help="Return the structured organ bundle for a seed-lib frontend component (source, types, tests, deps, consumers, wiring_snippet, validation_status, last_touched). KB § PATTERNS/architect/component-bundle-tool.md")
    parser.add_argument("--component-list", action="store_true", help="List all seed organs (reusable components) with derived validation status. Sort with --sort (consumers_desc|name|last_touched); filter with --filter-status (validated|emerging|shelfware|unknown, comma-separated). MCP: noctus.dev.component_list. KB § PATTERNS/architect/component-list-and-validation.md.")
    parser.add_argument("--find-reusable-component", metavar="QUERY", help="Find reusable seed organs by semantic intent query. Embeds the query → cosine-top-K search over organ chunks in code-embeddings cache. Use --top-k N to control result count (default 5). Use --filter-status to narrow by validation_status. Falls back to keyword search when embedding provider unreachable. MCP: noctus.dev.find_reusable_component. KB § PATTERNS/architect/seed-organ-canonical-set.md")
    parser.add_argument("--register-organ", metavar="NAME", help="Embed a named seed organ into the code-embeddings cache (chunk_kind='organ'). Idempotent. MCP: noctus.dev.register_organ.")
    parser.add_argument("--register-all-canonical-organs", action="store_true", help="Register all 5 Phase-1 canonical seed organs (LoginForm/ForgotPasswordPage/AcceptInvitePage/ResourceManager/DigestCard). Idempotent. MCP: noctus.dev.register_all_canonical_organs.")
    parser.add_argument("--organ-knowledge-append", metavar="NAME", help="Append a knowledge entry to an organ's journey then re-embed inline. Requires --organ-field + --organ-entry; --organ-entry-json parses the entry as JSON (for manual_validation_log / e2e_test). --no-organ-re-embed to batch. MCP: noctus.dev.organ_knowledge_append. KB § PATTERNS/common/build-learn-cache-mindset.md")
    parser.add_argument("--organ-knowledge-query", metavar="NAME", help="Return an organ's accumulated build-learn-cache journey (8 knowledge fields + metadata). MCP: noctus.dev.organ_knowledge_query.")
    parser.add_argument("--organ-field", help="Knowledge field for --organ-knowledge-append (known_facts|errors_encountered|drifts_surfaced|alternatives_considered|manual_validation_log|integration_test_status|e2e_test|bugs_fixed_during_dev).")
    parser.add_argument("--organ-entry", help="Knowledge entry value for --organ-knowledge-append (a string, or JSON when --organ-entry-json is set).")
    parser.add_argument("--organ-entry-json", action="store_true", help="Parse --organ-entry as JSON before appending (for structured fields like manual_validation_log / e2e_test).")
    parser.add_argument("--no-organ-re-embed", action="store_true", help="Skip the inline re-embed after --organ-knowledge-append (batch mode).")
    parser.add_argument("--sort", default="consumers_desc", choices=["consumers_desc", "name", "last_touched"], help="Sort order for --component-list (default: consumers_desc).")
    parser.add_argument("--filter-status", metavar="STATUSES", help="Comma-separated status filter for --component-list or --find-reusable-component (e.g. 'shelfware' or 'validated,emerging').")
    parser.add_argument("--improvements", metavar="PROJECT", help="Regenerate improvements.md next to the project file (run after ticking a phase header to [x]). Captures improvement opportunities discovered during each completed phase — NOT a preview of upcoming phases.")
    parser.add_argument("--lgpd-flag", action="store_true", help="Record an LGPD concern in LGPD-WARNINGS.md. Requires --lgpd-concern, --lgpd-path, --lgpd-reason; --lgpd-mitigation optional. Does NOT block.")
    parser.add_argument("--lgpd-concern", help="Short label for the concern (e.g. 'patient-text-in-cache')")
    parser.add_argument("--lgpd-path", help="Code location (file:line or brief locator)")
    parser.add_argument("--lgpd-reason", help="One-to-three sentences on how this breaks or approaches LGPD")
    parser.add_argument("--lgpd-mitigation", help="Optional suggested fix")
    parser.add_argument("--lgpd-list", action="store_true", help="List all LGPD concerns and their resolved state")
    parser.add_argument("--count-tokens", metavar="PATH", help="Count tokens for a file, directory, or glob. Tokenizer cascade: tiktoken (if installed) → chars/4 approximation. Reports `tokenizer_used` so callers know the precision. Used by methodology-extraction Phase 5 measurement and project-history-ledger.")
    parser.add_argument("--count-tokens-text", metavar="TEXT", help="Count tokens for an inline string (skip filesystem). Use with --count-tokens for both at once.")
    parser.add_argument("--count-tokens-ext", metavar="EXTS", help="Comma-separated file extensions to include when --count-tokens points at a directory. Default: '.md'. Use '*' to include everything.")
    parser.add_argument("--outline-python", metavar="PATH", help="Return a Python file's symbol tree (classes / functions / methods / constants / imports) without bodies. Makes the narrow-read rule ergonomic — read structure first, fetch bodies on demand. Stdlib `ast` (no extra deps).")
    parser.add_argument("--outline-typescript", metavar="PATH", help="Return a TS / TSX file's symbol tree (classes, interfaces, types, functions, arrow-fn consts, methods, constants, imports). Same shape as --outline-python. Regex-based (no Node spawn, no npm install) — see `mcp/noctusai/tools/outline_typescript.py` for the design tradeoff.")
    parser.add_argument("--product", help="Scope to one product")
    parser.add_argument(
        "--worktree-path",
        "--root",
        dest="worktree_path",
        metavar="PATH",
        default=None,
        help=(
            "Override the repo root the CLI walks. Use from inside a git worktree "
            "(e.g. `.claude/worktrees/agent-<hex>/`) so --review / --validate / scan / "
            "improvements / status / etc. read the worktree's products/ tree instead of "
            "the canonical noc clone the file-relative resolver would pick. Defaults to "
            "the marker-resolved workspace (`get_noctusai_home()`)."
        ),
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--compose-brief", action="store_true", help="Auto-compose an engineer dispatch brief by querying kb-embeddings, auto-improvement, and agent-context keeper-mirror caches. Requires --files (comma-sep target files) and --description. Optionally --agent to pin agent; omit for auto-routing. Graceful-degrade when caches are empty. MCP: noctus.dev.engineer_brief_compose. KB § PATTERNS/common/agent-context-architecture.md.")
    parser.add_argument("--files", metavar="FILES", help="Comma-separated target file paths for --compose-brief (e.g. mcp/noctusai/tools/noctus/dev/foo.py,mcp/noctusai/cli.py).")
    parser.add_argument("--description", metavar="TEXT", help="Task description text for --compose-brief.")
    parser.add_argument("--vector-costs-report", action="store_true", help="Aggregate the vector embedding cost ledger by day/week/month. Filter with --namespace and --since; granularity with --group-by. MCP: noctus.dev.vector_costs_report. KB § PATTERNS/common/vector-cost-tracking.md.")
    parser.add_argument("--vector-costs-total", action="store_true", help="Quick total aggregate of the vector embedding cost ledger. Filter with --namespace and --since. MCP: noctus.dev.vector_costs_total.")
    parser.add_argument("--dispatch-budget-log", action="store_true", help="Append one dispatch token-budget row to project-history/dispatch-budget.ndjson. Requires --agent (existing flag), --budget-slug, --input-tokens, --output-tokens, --budget-model. Optional: --source-ref. MCP: noctus.dev.dispatch_budget_log. KB § PATTERNS/common/dispatch-budget-telemetry.md.")
    parser.add_argument("--dispatch-budget-report", action="store_true", help="Aggregate the dispatch-budget ledger by (agent, model) within a rolling window. Optional --agent (existing flag), --budget-model, --window-days (default 7; 0=all-time). MCP: noctus.dev.dispatch_budget_report. KB § PATTERNS/common/dispatch-budget-telemetry.md.")
    parser.add_argument("--dispatch-budget-summary", action="store_true", help="One-shot totals of the dispatch-budget ledger. Optional --agent (existing flag), --budget-model, --window-days (default 0=all-time). MCP: noctus.dev.dispatch_budget_summary. KB § PATTERNS/common/dispatch-budget-telemetry.md.")
    parser.add_argument("--surface-to-tech-lead", action="store_true", help="File a structured surface note when blocked. Requires --surface-reason, --surface-proposal, --surface-state, --surface-attempted. Optional --worktree-path for explicit wt. MCP: noctus.dev.surface_to_tech_lead. KB § PATTERNS/common/surface-and-resume-tooling.md.")
    parser.add_argument("--surface-reason", metavar="REASON", help="With --surface-to-tech-lead: one-line summary of the blocker.")
    parser.add_argument("--surface-proposal", metavar="MD", help="With --surface-to-tech-lead: proposal markdown (≤200 lines).")
    parser.add_argument("--surface-state", metavar="MD", help="With --surface-to-tech-lead: current state markdown.")
    parser.add_argument("--surface-attempted", metavar="MD", help="With --surface-to-tech-lead: attempted resolution markdown.")
    parser.add_argument("--list-pending-surfaces", action="store_true", help="List surface notes awaiting tech-lead response. Pass --include-responded to see all. MCP: noctus.dev.list_pending_surfaces. KB § PATTERNS/common/surface-and-resume-tooling.md.")
    parser.add_argument("--include-responded", action="store_true", help="With --list-pending-surfaces: include already-responded surfaces.")
    parser.add_argument("--respond-and-resume", metavar="SURFACE_ID", dest="respond_and_resume_id", help="Respond to a pending surface and compose ResumeBundle. Requires --surface-decision, --surface-rationale. Optional --surface-updated-brief. MCP: noctus.dev.respond_and_resume. KB § PATTERNS/common/surface-and-resume-tooling.md.")
    parser.add_argument("--surface-decision", metavar="DECISION", choices=["approve", "reject", "adapt"], help="With --respond-and-resume: approve | reject | adapt.")
    parser.add_argument("--surface-rationale", metavar="MD", help="With --respond-and-resume: tech-lead rationale (required, durable knowledge).")
    parser.add_argument("--surface-updated-brief", metavar="MD", help="With --respond-and-resume --surface-decision=adapt: the revised brief text.")
    parser.add_argument("--dispatch-resume-brief", metavar="SURFACE_ID", dest="dispatch_resume_brief_id", help="Compose the full dispatch-ready brief for a responded surface. Pass verbatim to Agent() brief. MCP: noctus.dev.dispatch_resume_brief. KB § PATTERNS/common/surface-and-resume-tooling.md.")
    parser.add_argument("--budget-slug", metavar="SLUG", dest="budget_slug", help="With --dispatch-budget-log: branch/task slug (e.g. 'feat/r1-f11').")
    parser.add_argument("--input-tokens", metavar="N", type=int, dest="input_tokens", help="With --dispatch-budget-log: input token count.")
    parser.add_argument("--output-tokens", metavar="N", type=int, dest="output_tokens", help="With --dispatch-budget-log: output token count.")
    parser.add_argument("--budget-model", metavar="MODEL", dest="budget_model", help="With --dispatch-budget-log/report/summary: model name (e.g. 'claude-sonnet-4-6').")
    parser.add_argument("--source-ref", metavar="REF", dest="source_ref", help="With --dispatch-budget-log: optional source ref (e.g. 'session:2026-05-28').")
    parser.add_argument("--window-days", metavar="DAYS", type=int, default=0, dest="window_days", help="With --dispatch-budget-report/--dispatch-budget-summary: rolling window in days (0=all-time).")
    parser.add_argument("--namespace", metavar="NS", help="With --vector-costs-report / --vector-costs-total: filter to one namespace (e.g. 'kb-embeddings').")
    parser.add_argument("--since", metavar="DATE", help="With --vector-costs-report / --vector-costs-total: only rows with ts >= DATE (ISO YYYY-MM-DD).")
    parser.add_argument("--group-by", metavar="GRANULARITY", default="day", choices=["day", "week", "month"], help="With --vector-costs-report: aggregation granularity (default: day).")
    args = parser.parse_args()

    # If the caller passed an explicit worktree path, override the module-level
    # `settings.REPO_ROOT` / `settings.PRODUCTS_DIR` BEFORE any `tools.*` module
    # is lazily imported. Every tool that does `from settings import REPO_ROOT,
    # PRODUCTS_DIR` snapshots the value at import time — so the override has to
    # land before those imports fire. Tool imports are guarded by the
    # `elif args.<flag>:` branches below, so they happen after this block.
    #
    # Engineers calling from a worktree (`python mcp/noctusai/cli.py --review
    # --product P --worktree-path /path/to/worktree`) used to need to symlink
    # or shell out to `run_review(products_dir=...)` directly. This closes the
    # gap surfaced by Engineers AAA + BBB + ZZ during keeper-trio Wave 1.
    if args.worktree_path:
        wt = Path(args.worktree_path).expanduser().resolve()
        if not wt.is_dir():
            print(f"  {RED}Error:{RESET} --worktree-path is not a directory: {wt}")
            sys.exit(2)
        import settings as _settings_mod
        _settings_mod.REPO_ROOT = wt
        _settings_mod.PRODUCTS_DIR = wt / "products"
        # Surface the override loudly — every later command reports against the
        # worktree, not noc; the operator should see exactly what was rebound.
        print(f"  {YELLOW}worktree override:{RESET} REPO_ROOT={wt}")

    print(f"\n{BOLD}╔══════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}║                NoctusAI Dev Toolkit                      ║{RESET}")
    print(f"{BOLD}╚══════════════════════════════════════════════════════════╝{RESET}\n")

    if args.validate:
        from tools.noctus.dev.compliance import check_all_products
        score, issues = check_all_products()
        color = GREEN if score == 100 else RED
        print(f"  {BOLD}Score: {color}{score}/100{RESET}  |  Issues: {len(issues)}")
        for i in issues:
            print(f"    {RED}[{i['severity']}]{RESET} {i['product']}: {i['issue']}")

    elif args.check_phase_state:
        from tools.noctus.dev.compliance import check_phase_state_consistency
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

    elif args.check_outlined:
        import subprocess as _sp
        from tools.noctus.dev.compliance import check_files_outlined
        from settings import REPO_ROOT  # honours the line-144 worktree override
        staged = [
            ln for ln in _sp.run(
                ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                capture_output=True, text=True,
            ).stdout.splitlines()
            if ln.strip()
        ]
        src = [REPO_ROOT / f for f in staged
               if f.rsplit(".", 1)[-1] in {"py", "pyi", "ts", "tsx", "js", "jsx", "mjs", "cjs"}]
        issues = check_files_outlined(paths=src) if src else []
        if not issues:
            print(f"  {GREEN}✓ All staged source files are AST-outline-able.{RESET}")
            sys.exit(0)
        print(f"  {RED}✗ {len(issues)} staged file(s) NOT AST-outline-able:{RESET}")
        for i in issues:
            print(f"    {RED}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        print(
            f"\n  {BOLD}Fix the parse error before committing.{RESET}\n"
            f"  Per `KB § PATTERNS/ast.md § Always-outline-able platform`."
        )
        sys.exit(1)

    elif args.scan_outlined:
        from tools.noctus.dev.compliance import check_files_outlined
        issues = check_files_outlined()
        if not issues:
            print(f"  {GREEN}✓ Whole platform is AST-outline-able (zero un-outline-able files).{RESET}")
            sys.exit(0)
        print(f"  {RED}✗ {len(issues)} un-outline-able file(s) platform-wide:{RESET}")
        for i in issues:
            print(f"    {RED}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        sys.exit(1)

    elif args.check_claude_md_router:
        from tools.noctus.dev.compliance import check_claude_md_router
        issues = check_claude_md_router()
        if not issues:
            print(f"  {GREEN}✓ CLAUDE.md router discipline clean.{RESET}")
            sys.exit(0)
        print(f"  {RED}✗ {len(issues)} CLAUDE.md router issue(s):{RESET}")
        for i in issues:
            print(f"    {RED}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        print(
            f"\n  {BOLD}Keep CLAUDE.md pointer-only: §1 = rule + `→` pointer (one line); bodies in KB / a skill.{RESET}\n"
            f"  Per `KB § PATTERNS/claude-md-router-discipline.md`."
        )
        sys.exit(1)

    elif args.check_memory_md_index:
        from tools.noctus.dev.compliance import check_memory_md_index
        issues = check_memory_md_index()
        if not issues:
            print(f"  {GREEN}✓ MEMORY.md index discipline clean.{RESET}")
            sys.exit(0)
        print(f"  {RED}✗ {len(issues)} MEMORY.md index issue(s):{RESET}")
        for i in issues:
            print(f"    {RED}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        print(
            f"\n  {BOLD}Keep MEMORY.md entries tight: title + pointer + one recall hook (+ wikilinks).{RESET}\n"
            f"  Per `KB § PATTERNS/claude-md-router-discipline.md` (sibling pattern)."
        )
        sys.exit(1)

    elif args.refresh_keeper_cache:
        from tools.noctus.dev.cache_backend import acquire_refresh_lock
        with acquire_refresh_lock("keeper-patterns") as _ok:
            if not _ok:
                print(f"  {GREEN}✓ keeper-pattern refresh skipped — another process holds the lock.{RESET}")
                sys.exit(0)
            from tools.noctus.dev import keeper_pattern_cache as kpc
            r = kpc.refresh(force=args.force)
        if r["status"] == "in-sync":
            print(f"  {GREEN}✓ keeper-pattern cache in-sync (source_sha={r['source_sha'][:12]}; --force to rebuild).{RESET}")
        else:
            print(f"  {GREEN}✓ keeper-pattern cache rebuilt — {r['rows_written']} rows (source_sha={r['source_sha'][:12]}).{RESET}")
        sys.exit(0)
    elif args.keeper_pattern_lookup:
        from tools.noctus.dev import keeper_pattern_cache as kpc
        arg = args.keeper_pattern_lookup
        # File-path heuristic vs keeper-name: a path-shaped arg gets file_path, else keeper_name.
        rows = kpc.lookup(file_path=arg) if "/" in arg or arg.endswith(".md") else kpc.lookup(keeper_name=arg)
        if not rows:
            print(f"  {YELLOW}(no patterns matched '{arg}'){RESET}")
            sys.exit(0)
        print(f"  {GREEN}✓ {len(rows)} pattern row(s) for '{arg}':{RESET}")
        for r in rows[:30]:
            sev = r.get("severity") or "—"
            print(f"    [{sev}] {r['keeper_name']} ({r['pattern_kind']}) — {r['source_file']}:{r['source_line']}")
            if r.get("pattern_value"):
                preview = r["pattern_value"][:120].replace("\n", " ⏎ ")
                print(f"        {preview}{'…' if len(r['pattern_value']) > 120 else ''}")
        if len(rows) > 30:
            print(f"    … and {len(rows) - 30} more")
        sys.exit(0)
    elif args.check_keeper_cache_freshness:
        from tools.noctus.dev.compliance import check_keeper_cache_freshness
        issues = check_keeper_cache_freshness()
        if not issues:
            print(f"  {GREEN}✓ keeper-pattern cache fresh (mirrors compliance.py).{RESET}")
            sys.exit(0)
        print(f"  {RED}✗ {len(issues)} keeper-cache-freshness issue(s):{RESET}")
        for i in issues:
            print(f"    {RED}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        sys.exit(1)
    elif args.refresh_agent_context_cache:
        from tools.noctus.dev.cache_backend import acquire_refresh_lock
        with acquire_refresh_lock("agent-context") as _ok:
            if not _ok:
                print(f"  {GREEN}✓ agent-context refresh skipped — another process holds the lock.{RESET}")
                sys.exit(0)
            from tools.noctus.dev import agent_context_cache as acc
            r = acc.refresh(force=args.force, agent_name=args.agent)
        scope = f" (agent={args.agent})" if args.agent else ""
        if r["status"] == "in-sync":
            print(f"  {GREEN}✓ agent-context cache in-sync{scope} ({len(r['skipped'])} agent(s) skipped; --force to rebuild).{RESET}")
        else:
            print(f"  {GREEN}✓ agent-context cache rebuilt{scope} — refreshed {len(r['refreshed'])} agent(s), {r['rows_written']} rows.{RESET}")
            if r["refreshed"]:
                print(f"    refreshed: {', '.join(r['refreshed'])}")
        sys.exit(0)
    elif args.agent_context:
        from tools.noctus.dev import agent_context_cache as acc
        b = acc.lookup(args.agent_context)
        if not b.get("ok"):
            print(f"  {RED}✗ {b.get('error', 'lookup failed')}{RESET}")
            sys.exit(1)
        print(f"  {GREEN}✓ agent `{b['agent_name']}` bundle (bundle_sha={b['bundle_sha'][:12]}, cached_at={b['cached_at']}):{RESET}")
        print(f"    body: {len(b['body'])} chars")
        print(f"    owned_kb: {len(b['owned_kb'])} doc(s)")
        for o in b["owned_kb"][:5]:
            extract_first_line = (o["extract"].splitlines()[0] if o["extract"] else "(empty)")[:80]
            print(f"      · {o['path']} → {extract_first_line}")
        if len(b["owned_kb"]) > 5:
            print(f"      … and {len(b['owned_kb']) - 5} more")
        sys.exit(0)
    elif args.check_agent_context_cache_freshness:
        from tools.noctus.dev.compliance import check_agent_context_cache_freshness
        issues = check_agent_context_cache_freshness()
        if not issues:
            print(f"  {GREEN}✓ agent-context cache fresh (each agent's bundle_sha matches live).{RESET}")
            sys.exit(0)
        print(f"  {RED}✗ {len(issues)} agent-context-cache-freshness issue(s):{RESET}")
        for i in issues:
            print(f"    {RED}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        sys.exit(1)
    elif args.refresh_auto_improvement_cache:
        from tools.noctus.dev.cache_backend import acquire_refresh_lock
        with acquire_refresh_lock("auto-improvement") as _ok:
            if not _ok:
                print(f"  {GREEN}✓ auto-improvement refresh skipped — another process holds the lock.{RESET}")
                sys.exit(0)
            from tools.noctus.dev import auto_improvement as ai
            r = ai.refresh(force=args.force)
        if r["status"] == "in-sync":
            print(f"  {GREEN}✓ auto-improvement cache in-sync (source_sha={r['source_sha'][:12]}; --force to rebuild).{RESET}")
        else:
            print(f"  {GREEN}✓ auto-improvement cache rebuilt — {r['rows_written']} rows (source_sha={r['source_sha'][:12]}).{RESET}")
        sys.exit(0)
    elif args.auto_improvement_query:
        from tools.noctus.dev import auto_improvement as ai
        rows = ai.query(target=args.auto_improvement_query, open_only=True, limit=50)
        if not rows:
            print(f"  {YELLOW}(no open auto-improvement entries for '{args.auto_improvement_query}'){RESET}")
            sys.exit(0)
        print(f"  {GREEN}✓ {len(rows)} open entr(ies) for '{args.auto_improvement_query}':{RESET}")
        for r in rows:
            short = r["description"][:120].replace("\n", " ")
            print(f"    [{r['status']}] {r['kind']:11s} {r['scope']:6s} {r['target']}")
            print(f"        {short}{'…' if len(r['description']) > 120 else ''}")
            print(f"        ts={r['ts']} agent={r['agent']} source_ref={r['source_ref']}")
        sys.exit(0)
    elif args.check_auto_improvement_cache_freshness:
        from tools.noctus.dev.compliance import check_auto_improvement_cache_freshness
        issues = check_auto_improvement_cache_freshness()
        if not issues:
            print(f"  {GREEN}✓ auto-improvement cache fresh (mirrors ndjson).{RESET}")
            sys.exit(0)
        print(f"  {RED}✗ {len(issues)} auto-improvement-cache-freshness issue(s):{RESET}")
        for i in issues:
            print(f"    {RED}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        sys.exit(1)
    elif args.check_codification_pipeline_health:
        from tools.noctus.dev.compliance import check_codification_pipeline_health
        issues = check_codification_pipeline_health()
        if not issues:
            print(f"  {GREEN}✓ codification pipeline alive (s2 + s3 + s4 entries within thresholds).{RESET}")
            sys.exit(0)
        print(f"  {YELLOW}⚠ {len(issues)} codification-pipeline-health issue(s):{RESET}")
        for i in issues:
            print(f"    {YELLOW}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        sys.exit(0)  # advisory — don't fail CI on pipeline silence
    elif args.check_project_has_dispatch_routing:
        from tools.noctus.dev.compliance import check_project_has_dispatch_routing
        issues = check_project_has_dispatch_routing()
        if not issues:
            print(f"  {GREEN}✓ every PROJECT.md with §6 phases carries §4a Dispatch routing (or is grandfathered).{RESET}")
            sys.exit(0)
        print(f"  {YELLOW}⚠ {len(issues)} project-missing-dispatch-routing issue(s):{RESET}")
        for i in issues:
            print(f"    {YELLOW}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        sys.exit(0)  # advisory
    elif args.codify_log:
        from tools.noctus.dev.codify import codify_log
        stage, target, description = args.codify_log
        result = codify_log(
            stage=stage,
            target=target,
            description=description,
            source_ref=args.codify_source_ref,
            force=getattr(args, 'force', False),
        )
        if result.get("ok"):
            entry = result["entry"]
            print(f"  {GREEN}✓ codify_log wrote {stage} entry for target {target!r}.{RESET}")
            print(f"  ledger: {result['ledger_path']}")
            print(f"  source_ref: {entry.get('source_ref')}")
            sys.exit(0)
        print(f"  {RED}✗ codify_log refused: {result.get('error')}{RESET}")
        if result.get("missing_prereq"):
            print(f"  {RED}missing prereq: {result['missing_prereq']}{RESET}")
            print(f"  {YELLOW}override: re-run with --force (and --codify-source-ref <rationale>){RESET}")
        sys.exit(1)
    elif args.vps_exec_sql:
        from tools.noctus.dev.vps_exec_sql import exec_sql
        sql_file, container, db = args.vps_exec_sql
        from pathlib import Path as _P
        sql_path = _P(sql_file)
        if not sql_path.exists():
            print(f"  {RED}✗ SQL file not found: {sql_file}{RESET}")
            sys.exit(1)
        sql_content = sql_path.read_text(encoding="utf-8")
        result = exec_sql(
            sql=sql_content,
            container=container,
            db=db,
            user=args.vps_exec_sql_user,
            host=args.vps_exec_sql_host,
            cleanup=not args.vps_exec_sql_no_cleanup,
        )
        if result.get("ok"):
            print(f"  {GREEN}✓ exec_sql succeeded on {result['container']} / {result['db']}.{RESET}")
            if result.get("stdout"):
                print(f"  {GREEN}stdout:{RESET}")
                for line in result["stdout"].splitlines():
                    print(f"    {line}")
            if not result.get("cleanup_ok", True):
                print(f"  {YELLOW}⚠ cleanup left tmp file: {result.get('cleanup_err', '')}{RESET}")
            sys.exit(0)
        print(f"  {RED}✗ exec_sql failed at step '{result.get('step')}': {result.get('error') or result.get('stderr', '').strip()}{RESET}")
        if result.get("stderr"):
            for line in (result["stderr"] or "").splitlines():
                print(f"    {line}")
        sys.exit(result.get("returncode", 1) or 1)
    elif args.check_prod_cache_reachable:
        from tools.noctus.dev.compliance import check_prod_cache_reachable
        issues = check_prod_cache_reachable()
        if not issues:
            print(f"  {GREEN}✓ prod cache reachable (or sqlite NO-OP).{RESET}")
            sys.exit(0)
        print(f"  {RED}✗ {len(issues)} prod-cache-reachable issue(s):{RESET}")
        for i in issues:
            print(f"    {RED}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        sys.exit(1)
    elif args.check_cache_backend_env_matches_environment:
        from tools.noctus.dev.compliance import check_cache_backend_env_matches_environment
        issues = check_cache_backend_env_matches_environment()
        if not issues:
            print(f"  {GREEN}✓ cache backend env matches environment.{RESET}")
            sys.exit(0)
        print(f"  {YELLOW}⚠ {len(issues)} cache-backend-env issue(s):{RESET}")
        for i in issues:
            print(f"    {YELLOW}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        sys.exit(0)  # advisory
    elif args.check_drift_shield:
        from tools.noctus.dev.compliance import check_drift_shield
        issues = check_drift_shield()
        if not issues:
            print(f"  {GREEN}✓ drift-shield clean (no open entries touch this deploy).{RESET}")
            sys.exit(0)
        print(f"  {YELLOW}⚠ {len(issues)} drift-shield issue(s):{RESET}")
        for i in issues:
            print(f"    {YELLOW}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        sys.exit(0)  # advisory
    elif args.check_slip_shield:
        from tools.noctus.dev.compliance import check_slip_shield
        issues = check_slip_shield()
        if not issues:
            print(f"  {GREEN}✓ slip-shield clean (no codification slips touch this deploy).{RESET}")
            sys.exit(0)
        print(f"  {YELLOW}⚠ {len(issues)} slip-shield issue(s):{RESET}")
        for i in issues:
            print(f"    {YELLOW}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        sys.exit(0)  # advisory
    elif args.check_pre_deploy_gate:
        from tools.noctus.dev.compliance import check_pre_deploy_gate
        issues = check_pre_deploy_gate()
        if not issues:
            print(f"  {GREEN}✓ pre-deploy gate clean (all 4 safety keepers green).{RESET}")
            sys.exit(0)
        highs = [i for i in issues if i.get("severity") == "high"]
        warns = [i for i in issues if i.get("severity") != "high"]
        if highs:
            print(f"  {RED}✗ {len(highs)} HIGH-severity pre-deploy issue(s):{RESET}")
            for i in highs:
                print(f"    {RED}[high]{RESET} {i['file']} — {i['issue']}")
        if warns:
            print(f"  {YELLOW}⚠ {len(warns)} advisory pre-deploy issue(s):{RESET}")
            for i in warns:
                print(f"    {YELLOW}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        sys.exit(1 if highs else 0)
    elif args.check_contextualize_alignment:
        from tools.noctus.dev.compliance import check_contextualize_alignment
        issues = check_contextualize_alignment()
        if not issues:
            print(f"  {GREEN}✓ CONTEXTUALIZE.md aligned (pointer-only + canonical cores covered).{RESET}")
            sys.exit(0)
        print(f"  {RED}✗ {len(issues)} contextualize-alignment issue(s):{RESET}")
        for i in issues:
            print(f"    {RED}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        sys.exit(1)
    elif args.check_eight_way_sync or args.check_seven_way_sync or args.check_six_way_sync:
        # --check-seven-way-sync and --check-six-way-sync are back-compat
        # aliases; all three routes call the same composition keeper
        # (which now covers 8 surfaces after the 7→8 promotion).
        if args.check_seven_way_sync:
            print(f"  {YELLOW}⚠ --check-seven-way-sync is deprecated → use --check-eight-way-sync.{RESET}")
        if args.check_six_way_sync:
            print(f"  {YELLOW}⚠ --check-six-way-sync is deprecated → use --check-eight-way-sync.{RESET}")
        from tools.noctus.dev.compliance import check_eight_way_sync
        issues = check_eight_way_sync()
        if not issues:
            print(f"  {GREEN}✓ 8-way sync clean (CLAUDE.md / MEMORY.md / agents / KB / CONTEXTUALIZE.md / skills / commands / cache all aligned).{RESET}")
            sys.exit(0)
        # Split by severity: warning-only issues print but don't block;
        # any high issue blocks. Preserves the pre-promotion blocking
        # behavior while honoring per-sub-keeper severities (e.g.
        # noc-graph-cache-stale is auto-recoverable, severity=warning).
        any_high = any(i.get("severity") == "high" for i in issues)
        prefix_char = "✗" if any_high else "⚠"
        prefix_color = RED if any_high else YELLOW
        print(f"  {prefix_color}{prefix_char} {len(issues)} eight-way-sync issue(s):{RESET}")
        for i in issues:
            sev_color = RED if i.get("severity") == "high" else YELLOW
            print(f"    {sev_color}[{i['severity']}]{RESET} {i.get('file', '?')} — {i['issue']} ({i.get('symbol', '?')})")
        sys.exit(1 if any_high else 0)
    elif args.check_all_cache_freshness:
        from tools.noctus.dev.compliance import check_all_cache_freshness
        issues = check_all_cache_freshness()
        if not issues:
            print(f"  {GREEN}✓ all 8 keeper-mirror caches fresh (keeper-patterns / agent-context / auto-improvement / code-embeddings / noc-graph / kb-embeddings / corpus-embeddings / memory-embeddings).{RESET}")
            sys.exit(0)
        # Mixed severities; report all then exit non-zero if any HIGH.
        any_high = any(i.get("severity") == "high" for i in issues)
        prefix = RED if any_high else YELLOW
        print(f"  {prefix}{'✗' if any_high else '⚠'} {len(issues)} all-cache-freshness issue(s):{RESET}")
        for i in issues:
            sev_color = RED if i.get("severity") == "high" else YELLOW
            print(f"    {sev_color}[{i['severity']}]{RESET} {i.get('file', '?')} — {i['issue']} ({i.get('symbol', '?')})")
        sys.exit(1 if any_high else 0)
    elif args.check_skills_listed_in_router:
        from tools.noctus.dev.compliance import check_skills_listed_in_router
        issues = check_skills_listed_in_router()
        if not issues:
            print(f"  {GREEN}✓ skills ↔ CLAUDE.md §2 router in sync.{RESET}")
            sys.exit(0)
        print(f"  {RED}✗ {len(issues)} skills-router-sync issue(s):{RESET}")
        for i in issues:
            print(f"    {RED}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        sys.exit(1)
    elif args.check_commands_listed_in_router:
        from tools.noctus.dev.compliance import check_commands_listed_in_router
        issues = check_commands_listed_in_router()
        if not issues:
            print(f"  {GREEN}✓ commands ↔ CLAUDE.md §2 router in sync.{RESET}")
            sys.exit(0)
        print(f"  {RED}✗ {len(issues)} commands-router-sync issue(s):{RESET}")
        for i in issues:
            print(f"    {RED}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        sys.exit(1)
    elif args.check_memory_embeddings_cache_freshness:
        from tools.noctus.dev import memory_embeddings as mee
        import sqlite3
        if mee._resolve_memory_dir() is None:
            print(f"  {YELLOW}⚠ no memory dir resolvable — gate is no-op.{RESET}")
            sys.exit(0)
        live_sha = mee.cache_source_sha()
        if not mee.CACHE_PATH.exists():
            print(f"  {YELLOW}⚠ memory-embeddings cache absent — run --refresh-memory-embeddings.{RESET}")
            sys.exit(1)
        try:
            conn = sqlite3.connect(str(mee.CACHE_PATH))
            cur = conn.execute("SELECT value FROM cache_meta WHERE key='source_sha'")
            row = cur.fetchone()
            conn.close()
            cached = row[0] if row else None
        except sqlite3.Error:
            cached = None
        if cached != live_sha:
            print(f"  {YELLOW}⚠ memory-embeddings stale (cached={cached!r}, live={live_sha!r}) — refresh recommended.{RESET}")
            sys.exit(1)
        print(f"  {GREEN}✓ memory-embeddings cache fresh (sha={live_sha}).{RESET}")
        sys.exit(0)
    elif args.check_corpus_embeddings_cache_freshness:
        from tools.noctus.dev import corpus_embeddings as cee
        import sqlite3
        live_sha = cee.cache_source_sha()
        if not cee.CACHE_PATH.exists():
            print(f"  {YELLOW}⚠ corpus-embeddings cache absent — run --refresh-corpus-embeddings.{RESET}")
            sys.exit(1)
        try:
            conn = sqlite3.connect(str(cee.CACHE_PATH))
            cur = conn.execute("SELECT value FROM cache_meta WHERE key='source_sha'")
            row = cur.fetchone()
            conn.close()
            cached = row[0] if row else None
        except sqlite3.Error:
            cached = None
        if cached != live_sha:
            print(f"  {YELLOW}⚠ corpus-embeddings stale (cached={cached!r}, live={live_sha!r}) — refresh recommended.{RESET}")
            sys.exit(1)
        print(f"  {GREEN}✓ corpus-embeddings cache fresh (sha={live_sha}).{RESET}")
        sys.exit(0)
    elif args.refresh_memory_embeddings:
        from tools.noctus.dev.cache_backend import acquire_refresh_lock
        with acquire_refresh_lock("memory-embeddings") as _ok:
            if not _ok:
                print(f"  {GREEN}✓ memory embeddings refresh skipped — another process holds the lock.{RESET}")
                sys.exit(0)
            _ensure_llm_configured()
            from tools.noctus.dev import memory_embeddings as mee
        r = mee.refresh(force=args.force)
        if r.get("status") == "no-memory-dir":
            print(f"  {YELLOW}⚠ {r.get('message', 'memory dir not found')}{RESET}")
        elif r["status"] == "in-sync":
            print(f"  {GREEN}✓ memory embeddings cache in-sync ({len(r['skipped'])} doc(s); --force to rebuild).{RESET}")
        else:
            print(f"  {GREEN}✓ memory embeddings cache rebuilt — {r['rows_written']} chunks across {len(r['refreshed'])} doc(s).{RESET}")
            if r["errors"]:
                print(f"  {YELLOW}⚠ {len(r['errors'])} error(s):{RESET}")
                for e in r["errors"][:5]:
                    print(f"    {e}")
        sys.exit(0 if r["ok"] else 1)
    elif args.memory_search:
        _ensure_llm_configured()
        from tools.noctus.dev import memory_embeddings as mee
        hits = mee.search(args.memory_search, top_k=args.top_k)
        if not hits:
            print(f"  {YELLOW}(no hits for {args.memory_search!r} — cache empty or provider unreachable){RESET}")
            sys.exit(0)
        print(f"  {GREEN}✓ Top {len(hits)} hits for {args.memory_search!r}:{RESET}")
        for h in hits:
            print(f"  [{h['score']:.3f}] {h['path']}#{h['chunk_idx']}")
            print(f"    {h['chunk_text'][:200]!r}")
        sys.exit(0)
    elif args.refresh_corpus_embeddings:
        from tools.noctus.dev.cache_backend import acquire_refresh_lock
        with acquire_refresh_lock("corpus-embeddings") as _ok:
            if not _ok:
                print(f"  {GREEN}✓ corpus embeddings refresh skipped — another process holds the lock.{RESET}")
                sys.exit(0)
            _ensure_llm_configured()
            from tools.noctus.dev import corpus_embeddings as cee
        r = cee.refresh(force=args.force)
        if r["status"] == "in-sync":
            print(f"  {GREEN}✓ corpus embeddings cache in-sync ({len(r['skipped'])} doc(s); --force to rebuild).{RESET}")
        else:
            print(f"  {GREEN}✓ corpus embeddings cache rebuilt — {r['rows_written']} chunks across {len(r['refreshed'])} doc(s).{RESET}")
            if r["errors"]:
                print(f"  {YELLOW}⚠ {len(r['errors'])} error(s):{RESET}")
                for e in r["errors"][:5]:
                    print(f"    {e}")
        sys.exit(0 if r["ok"] else 1)
    elif args.corpus_search:
        _ensure_llm_configured()
        from tools.noctus.dev import corpus_embeddings as cee
        hits = cee.search(args.corpus_search, top_k=args.top_k, source_type=getattr(args, 'source_type', None))
        if not hits:
            print(f"  {YELLOW}(no hits for {args.corpus_search!r}){RESET}")
            sys.exit(0)
        print(f"  {GREEN}✓ Top {len(hits)} hits for {args.corpus_search!r}:{RESET}")
        for h in hits:
            print(f"  [{h['score']:.3f}] [{h['source_type']}] {h['path']}#{h['chunk_idx']}")
            print(f"    {h['chunk_text'][:200]!r}")
        sys.exit(0)
    elif args.refresh_kb_embeddings:
        from tools.noctus.dev.cache_backend import acquire_refresh_lock
        with acquire_refresh_lock("kb-embeddings") as _ok:
            if not _ok:
                print(f"  {GREEN}✓ kb embeddings refresh skipped — another process holds the lock.{RESET}")
                sys.exit(0)
            _ensure_llm_configured()
            from tools.noctus.dev import kb_embeddings as kbe
        r = kbe.refresh(force=args.force)
        if r["status"] == "in-sync":
            print(f"  {GREEN}✓ kb embeddings cache in-sync ({len(r['skipped'])} doc(s); --force to rebuild).{RESET}")
        else:
            print(f"  {GREEN}✓ kb embeddings cache rebuilt — {r['rows_written']} chunks across {len(r['refreshed'])} doc(s).{RESET}")
            if r["errors"]:
                print(f"  {YELLOW}⚠ {len(r['errors'])} error(s):{RESET}")
                for e in r["errors"][:5]:
                    print(f"    {e}")
        sys.exit(0 if r["ok"] else 1)
    elif args.kb_search:
        _ensure_llm_configured()
        from tools.noctus.dev import kb_embeddings as kbe
        hits = kbe.search(args.kb_search, top_k=args.top_k)
        if not hits:
            print(f"  {YELLOW}(no hits for {args.kb_search!r} — cache empty or embedding provider unreachable){RESET}")
            sys.exit(0)
        print(f"  {GREEN}✓ Top {len(hits)} hits for {args.kb_search!r}:{RESET}")
        for h in hits:
            preview = h["chunk_text"].splitlines()[0][:80] if h["chunk_text"] else ""
            print(f"    [{h['score']:.3f}] {h['path']}#chunk{h['chunk_idx']}")
            print(f"        {preview}…")
        sys.exit(0)
    elif args.check_kb_embeddings_cache_freshness:
        # NOTE: drift-found — CLI flag historically pointed at a name that
        # never existed; the actual keeper is `check_kb_vector_canonical`.
        # Fixed in-flight as part of W2-E3' (sibling code-embeddings keeper
        # arrived; surfaced the bug). Pre-existing debt → fix on contact.
        from tools.noctus.dev.compliance import check_kb_vector_canonical
        issues = check_kb_vector_canonical()
        if not issues:
            print(f"  {GREEN}✓ kb embeddings cache fresh.{RESET}")
            sys.exit(0)
        # Warning-severity keeper — surface but don't exit non-zero (advisory layer).
        print(f"  {YELLOW}⚠ {len(issues)} kb-embeddings-cache-freshness issue(s) (warnings, not blockers):{RESET}")
        for i in issues:
            print(f"    {YELLOW}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        sys.exit(0)
    elif args.refresh_code_embeddings:
        from tools.noctus.dev.cache_backend import acquire_refresh_lock
        with acquire_refresh_lock("code-embeddings") as _ok:
            if not _ok:
                print(f"  {GREEN}✓ code embeddings refresh skipped — another process holds the lock.{RESET}")
                sys.exit(0)
            _ensure_llm_configured()
            from tools.noctus.dev import code_embeddings as ce
        r = ce.refresh(force=args.force)
        if r["status"] == "in-sync":
            print(f"  {GREEN}✓ code embeddings cache in-sync ({len(r['skipped'])} file(s); --force to rebuild).{RESET}")
        else:
            print(f"  {GREEN}✓ code embeddings cache rebuilt — {r['rows_written']} chunks across {len(r['refreshed'])} file(s).{RESET}")
            if r["errors"]:
                print(f"  {YELLOW}⚠ {len(r['errors'])} error(s):{RESET}")
                for e in r["errors"][:5]:
                    print(f"    {e}")
        sys.exit(0 if r["ok"] else 1)
    elif args.code_search:
        _ensure_llm_configured()
        from tools.noctus.dev import code_embeddings as ce
        hits = ce.search(args.code_search, top_k=args.top_k)
        if not hits:
            print(f"  {YELLOW}(no hits for {args.code_search!r} — cache empty or embedding provider unreachable){RESET}")
            sys.exit(0)
        print(f"  {GREEN}✓ Top {len(hits)} hits for {args.code_search!r}:{RESET}")
        for h in hits:
            preview = h["chunk_text"].splitlines()[0][:80] if h["chunk_text"] else ""
            label = f"{h['symbol_name']} ({h['kind']})" if h["symbol_name"] else f"({h['kind']})"
            print(f"    [{h['score']:.3f}] {h['path']} :: {label}")
            print(f"        {preview}…")
        sys.exit(0)
    elif args.check_code_embeddings_cache_freshness:
        from tools.noctus.dev.compliance import check_code_embeddings_cache_freshness
        issues = check_code_embeddings_cache_freshness()
        if not issues:
            print(f"  {GREEN}✓ code embeddings cache fresh.{RESET}")
            sys.exit(0)
        print(f"  {YELLOW}⚠ {len(issues)} code-embeddings-cache-freshness issue(s) (warnings, not blockers):{RESET}")
        for i in issues:
            print(f"    {YELLOW}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        sys.exit(0)
    elif args.refresh_noc_graph:
        from tools.noctus.dev.cache_backend import acquire_refresh_lock
        with acquire_refresh_lock("noc-graph") as _ok:
            if not _ok:
                print(f"  {GREEN}✓ noc-graph refresh skipped — another process holds the lock.{RESET}")
                sys.exit(0)
            from tools.noctus.dev import noc_graph_cache as ng
            r = ng.refresh(force=args.force)
        if r["status"] == "in-sync":
            print(f"  {GREEN}✓ noc-graph cache in-sync (sha={r['source_sha']}; --force to rebuild).{RESET}")
        else:
            print(f"  {GREEN}✓ noc-graph cache rebuilt — {r.get('nodes', 0)} nodes / {r.get('edges', 0)} edges in {r.get('build_seconds')}s (sha={r['source_sha']}).{RESET}")
        sys.exit(0 if r["ok"] else 1)
    elif args.check_noc_graph_cache_freshness:
        from tools.noctus.dev.compliance import check_noc_graph_cache_freshness
        issues = check_noc_graph_cache_freshness()
        if not issues:
            print(f"  {GREEN}✓ noc-graph cache fresh.{RESET}")
            sys.exit(0)
        print(f"  {YELLOW}⚠ {len(issues)} noc-graph-cache-freshness issue(s) (warnings, not blockers):{RESET}")
        for i in issues:
            print(f"    {YELLOW}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        sys.exit(0)
    elif args.check_graph_extractor_corpus_sanity:
        from tools.noctus.dev.compliance import check_graph_extractor_corpus_sanity
        issues = check_graph_extractor_corpus_sanity()
        if not issues:
            print(f"  {GREEN}✓ graph-extractor corpus sanity clean (all node/edge kind floors met).{RESET}")
            sys.exit(0)
        print(f"  {YELLOW}⚠ {len(issues)} graph-extractor-corpus-sanity issue(s) (warnings, not blockers):{RESET}")
        for i in issues:
            print(f"    {YELLOW}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        sys.exit(0)
    elif args.kb_ratify:
        from tools.noctus.dev import kb_baseline as kbb
        result = kbb.ratify(args.kb_ratify)
        if not result["ok"]:
            print(f"  {RED}✗ {result['error']}{RESET}")
            sys.exit(1)
        print(f"  {GREEN}✓ baseline ratified: {result['baseline_id']} ({result['finding_count']} finding(s)).{RESET}")
        print(f"    path: {result['path']}")
        sys.exit(0)
    elif args.kb_baseline_diff:
        from tools.noctus.dev import kb_baseline as kbb
        result = kbb.diff(against=args.kb_baseline_diff)
        if not result["ok"]:
            print(f"  {RED}✗ {result.get('error', 'diff failed')}{RESET}")
            sys.exit(1)
        bid = result.get("baseline_id") or "(none)"
        print(f"  {GREEN}✓ diff vs baseline {bid}: "
              f"new={len(result['new_findings'])} resolved={len(result['resolved_findings'])} "
              f"unchanged={result['unchanged_count']}{RESET}")
        if result.get("kb_corpus_drifted"):
            print(f"  {YELLOW}⚠ KB corpus shifted since baseline — resolved may be artifacts.{RESET}")
        sys.exit(0)
    elif args.kb_baseline_list:
        from tools.noctus.dev import kb_baseline as kbb
        baselines = kbb.list_baselines()
        if not baselines:
            print(f"  {YELLOW}(no baselines ratified yet — call --kb-ratify <reason>){RESET}")
            sys.exit(0)
        print(f"  {GREEN}✓ {len(baselines)} ratified baseline(s):{RESET}")
        for b in baselines:
            print(f"    [{b['baseline_id']}] {b['ratified_at']} — {b['finding_count']} finding(s) — {b['reason']}")
        sys.exit(0)
    elif args.check_kb_semantic_drift:
        from tools.noctus.dev.compliance import check_kb_semantic_drift
        issues = check_kb_semantic_drift()
        if not issues:
            print(f"  {GREEN}✓ kb semantic drift within threshold.{RESET}")
            sys.exit(0)
        print(f"  {YELLOW}⚠ {len(issues)} kb-semantic-drift issue(s) (warnings, not blockers):{RESET}")
        for i in issues:
            print(f"    {YELLOW}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        sys.exit(0)
    elif args.code_ratify:
        from tools.noctus.dev import code_baseline as cb
        result = cb.ratify(args.code_ratify)
        if not result["ok"]:
            print(f"  {RED}✗ {result['error']}{RESET}")
            sys.exit(1)
        print(f"  {GREEN}✓ code baseline ratified: {result['baseline_id']} ({result['pair_count']} pair(s)).{RESET}")
        print(f"    path: {result['path']}")
        sys.exit(0)
    elif args.code_baseline_diff:
        from tools.noctus.dev import code_baseline as cb
        result = cb.diff(against=args.code_baseline_diff)
        if not result["ok"]:
            print(f"  {RED}✗ {result.get('error', 'diff failed')}{RESET}")
            sys.exit(1)
        bid = result.get("baseline_id") or "(none)"
        print(f"  {GREEN}✓ diff vs code-baseline {bid}: "
              f"new={len(result['new_matches'])} resolved={len(result['resolved_matches'])} "
              f"unchanged={result['unchanged_count']}{RESET}")
        if result.get("code_corpus_drifted"):
            print(f"  {YELLOW}⚠ Code corpus shifted since baseline — resolved may be artifacts.{RESET}")
        sys.exit(0)
    elif args.code_baseline_list:
        from tools.noctus.dev import code_baseline as cb
        baselines = cb.list_baselines()
        if not baselines:
            print(f"  {YELLOW}(no code baselines ratified yet — call --code-ratify <reason>){RESET}")
            sys.exit(0)
        print(f"  {GREEN}✓ {len(baselines)} ratified code-baseline(s):{RESET}")
        for b in baselines:
            print(f"    [{b['baseline_id']}] {b['ratified_at']} — {b['pair_count']} pair(s) — {b['reason']}")
        sys.exit(0)
    elif args.check_code_recurrence_drift:
        from tools.noctus.dev.compliance import check_code_recurrence_drift
        issues = check_code_recurrence_drift()
        if not issues:
            print(f"  {GREEN}✓ code recurrence drift within threshold.{RESET}")
            sys.exit(0)
        print(f"  {YELLOW}⚠ {len(issues)} code-recurrence-drift issue(s) (warnings, not blockers):{RESET}")
        for i in issues:
            print(f"    {YELLOW}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        sys.exit(0)
    elif args.check_canonical_organ_consumption:
        from tools.noctus.dev.compliance import check_canonical_organ_consumption
        issues = check_canonical_organ_consumption()
        if not issues:
            print(f"  {GREEN}✓ canonical-organ-consumption: clean.{RESET}")
            sys.exit(0)
        print(f"  {RED}✗ {len(issues)} canonical-organ-consumption issue(s):{RESET}")
        for i in issues:
            print(f"    {RED}[{i['severity']}]{RESET} {i.get('product','?')} {i.get('file','?')} — {i['issue']}")
        blocking = any(i.get("severity") in ("high", "critical") for i in issues)
        sys.exit(1 if blocking else 0)

    elif args.check_auth_boundary_false_green:
        from tools.noctus.dev.compliance import check_auth_boundary_false_green
        issues = check_auth_boundary_false_green()
        if not issues:
            print(f"  {GREEN}✓ auth-boundary-false-green: clean.{RESET}")
            sys.exit(0)
        print(f"  {YELLOW}⚠ {len(issues)} auth-boundary-false-green issue(s) (warnings):{RESET}")
        for i in issues:
            print(f"    {YELLOW}[{i['severity']}]{RESET} {i.get('product','?')} {i.get('file','?')} — {i['issue']}")
        # severity=warning only — do NOT block commits (informational gate).
        sys.exit(0)

    elif args.check_dangling_remote_branches:
        from tools.noctus.dev.compliance import check_dangling_remote_branches
        issues = check_dangling_remote_branches()
        if not issues:
            print(f"  {GREEN}✓ dangling-remote-branches: 0 unique-aged remote branches.{RESET}")
            sys.exit(0)
        print(f"  {YELLOW}⚠ {len(issues)} dangling-remote-branch finding(s) (advisory):{RESET}")
        for i in issues:
            print(f"    {YELLOW}[{i['severity']}]{RESET} {i.get('file','?')} — {i['issue'][:120]}")
        # severity=warning only — advisory, never blocks commits.
        sys.exit(0)

    elif args.check_skill_format or args.check_agent_format or args.check_agent_archetype_contract:
        from tools.noctus.dev.compliance import (
            check_skill_format, check_agent_format, check_agent_archetype_contract,
        )
        issues: list = []
        which = []
        if args.check_skill_format:
            issues += check_skill_format(); which.append("skill-format")
        if args.check_agent_format:
            issues += check_agent_format(); which.append("agent-format")
        if args.check_agent_archetype_contract:
            issues += check_agent_archetype_contract(); which.append("agent-archetype-contract")
        label = " + ".join(which)
        if not issues:
            print(f"  {GREEN}✓ harness-layer {label}: clean.{RESET}")
            sys.exit(0)
        print(f"  {RED}✗ {len(issues)} harness-layer {label} issue(s):{RESET}")
        for i in issues:
            print(f"    {RED}[{i['severity']}]{RESET} {i['file']} — {i['issue']}")
        # Exit 1 only if any HIGH/CRITICAL (warnings don't block).
        blocking = any(i.get("severity") in ("high", "critical") for i in issues)
        sys.exit(1 if blocking else 0)

    elif args.refs:
        from tools.noctus.dev.refs import find_refs
        result = find_refs(args.refs)
        print(f"  {BOLD}Pattern:{RESET} {result.pattern}")
        print(f"  {BOLD}Files scanned:{RESET} {result.total_files}")
        print(f"  {BOLD}Total matches:{RESET} {result.total_matches}\n")
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            grouped = {}
            for m in result.matches:
                grouped.setdefault(m.file, []).append((m.line, m.text))
            for file in sorted(grouped):
                print(f"  {BOLD}{file}{RESET}")
                for ln, text in grouped[file][:8]:
                    print(f"    {ln}: {text[:140]}")
                if len(grouped[file]) > 8:
                    print(f"    … {len(grouped[file]) - 8} more matches")

    elif args.graph_build:
        from tools.noctus.graph.build import build_and_write
        result = build_and_write(
            scope=args.graph_build,
            output_dir=args.graph_output,
            memory_root=args.graph_memory_root,
        )
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"  {BOLD}Scope:{RESET} {result['scope']}")
            print(f"  {BOLD}Nodes:{RESET} {result['nodes_count']}")
            print(f"  {BOLD}Edges:{RESET} {result['edges_count']}")
            print(f"  {BOLD}Clustering:{RESET} {result['clustering']}")
            print(f"  {BOLD}Took:{RESET} {result['took_seconds']}s")
            print(f"  {BOLD}Output:{RESET} {result['output_dir']}")
            print(f"    {GREEN}graph.json{RESET}  {result['paths']['json']}")
            print(f"    {GREEN}graph.html{RESET}  {result['paths']['html']}")
            print(f"    {GREEN}REPORT.md{RESET}   {result['paths']['report']}")
            print(f"\n  Open `{result['paths']['html']}` in a browser. Or query via MCP: `noctus.graph.query`.")

    elif args.build:
        from tools.noctus.dev.build import build_products
        slugs = [args.product] if args.product else None
        result = build_products(slugs=slugs, changed_only=args.changed)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            color = GREEN if result["all_green"] else RED
            print(f"  {BOLD}Total:{RESET} {result['total_duration_seconds']}s  |  All green: {color}{result['all_green']}{RESET}")
            for r in result["results"]:
                color = GREEN if r["success"] else RED
                print(f"    {color}{'✓' if r['success'] else '✗'}{RESET} {r['product']:<20} {r['duration_seconds']:>6.2f}s  {r['summary'][:80]}")

    elif args.status:
        from tools.noctus.dev.status import project_status_digest
        result = project_status_digest()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"  {BOLD}Total projects:{RESET} {result['total']}")
            for bucket, count in result["buckets"].items():
                if count > 0:
                    print(f"    {bucket}: {count}")
            print()
            for p in result["projects"]:
                icon = p["status_icon"] if p["status_icon"] != "none" else "·"
                progress = p["subtask_progress"]
                flags = f" {RED}[{len(p['flags'])} flags]{RESET}" if p["flags"] else ""
                print(f"  {icon} {p['slug']:<40} {p['location']:<25} {progress:>10}{flags}")

    elif args.check_three_way_sync:
        from tools.noctus.dev.three_way_sync import check_three_way_sync
        result = check_three_way_sync()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"  {BOLD}Memory dir:{RESET} {result['memory_dir']}")
            print(f"  {BOLD}Memory files checked:{RESET} {result['checked']}")
            stats = result.get("stats") or {}
            for k, v in stats.items():
                print(f"    {k}: {v}")
            issues = result.get("issues") or []
            if not issues:
                print(f"  {GREEN}✓ three-way sync clean.{RESET}")
            else:
                color = RED if any(i["severity"] == "high" for i in issues) else YELLOW
                print(f"  {color}{len(issues)} issue(s):{RESET}")
                for i in issues[:30]:
                    sev_color = RED if i["severity"] == "high" else YELLOW
                    print(f"    {sev_color}[{i['severity']}]{RESET} {i['file']}: {i['issue'][:160]}")
                if len(issues) > 30:
                    print(f"    … {len(issues) - 30} more")

    elif args.scan_recurrence:
        from tools.noctus.dev.recurrence import scan_recurrence
        result = scan_recurrence()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            stats = result["stats"]
            print(f"  {BOLD}Findings:{RESET} {stats['total_findings']} (high: {stats['high_severity']}, warning: {stats['warning_severity']})")
            for f in result["findings"][:30]:
                color = RED if f["severity"] == "high" else YELLOW
                print(f"  {color}[{f['severity']}]{RESET} {f['classification']} ×{f['count']}: {f['line_text'][:90]}")
                for o in f["occurrences"][:5]:
                    print(f"      • {o}")
                if len(f["occurrences"]) > 5:
                    print(f"      … {len(f['occurrences']) - 5} more")

    elif args.scan_helpers:
        from tools.noctus.dev.recurrence import scan_cross_product_helpers
        result = scan_cross_product_helpers()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            stats = result["stats"]
            print(f"  {BOLD}Cross-product helpers:{RESET} {stats['total_findings']} names recur (high N>=3: {stats['high_severity']}, warning N=2: {stats['warning_severity']})")
            print()
            for f in result["findings"][:40]:
                color = RED if f["severity"] == "high" else YELLOW
                print(f"  {color}[{f['severity']}]{RESET} {BOLD}{f['helper_name']}{RESET}  in {f['product_count']} products: {', '.join(f['products'])}")
                # Suggestion text — wrap at 100 chars for readability
                sugg = f["suggestion"]
                while sugg:
                    print(f"      → {sugg[:96]}")
                    sugg = sugg[96:]

    elif args.scan_blocks:
        from tools.noctus.dev.recurrence import scan_block_patterns
        kw = {"min_count": args.min_count} if args.min_count else {}
        result = scan_block_patterns(**kw)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            stats = result["stats"]
            print(f"  {BOLD}Block-pattern recurrence:{RESET} {stats['total_findings']} (high N>={stats.get('must_formalize_threshold', 3)}: {stats['high_severity']}, warning: {stats['warning_severity']})")
            print()
            for f in result["findings"][:20]:
                color = RED if f["severity"] == "high" else YELLOW
                body = ", ".join(f["body_targets"][:3])
                exc = f["handler_shape"][0] if f["handler_shape"] else ""
                print(f"  {color}[{f['severity']}]{RESET} ×{f['occurrence_count']} ({f['product_count']}p)  body=[{body}]  except=[{exc[:60]}]")
                for o in f["occurrences"][:5]:
                    print(f"      • {o}")
                if len(f["occurrences"]) > 5:
                    print(f"      … {len(f['occurrences']) - 5} more")
                sugg = f["suggestion"]
                while sugg:
                    print(f"      → {sugg[:96]}")
                    sugg = sugg[96:]

    elif args.scan_within_product:
        from tools.noctus.dev.recurrence import scan_within_product_helpers
        kw = {"min_count": args.min_count} if args.min_count else {}
        result = scan_within_product_helpers(**kw)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            stats = result["stats"]
            print(f"  {BOLD}Within-product recurrence:{RESET} {stats['total_findings']} (high N>=5: {stats['high_severity']}, warning: {stats['warning_severity']})")
            print()
            for f in result["findings"][:25]:
                color = RED if f["severity"] == "high" else YELLOW
                print(f"  {color}[{f['severity']}]{RESET} {BOLD}{f['product']}/{f['helper_name']}{RESET} ×{f['file_count']} files")
                for fp in f["files"][:4]:
                    print(f"      • {fp}")
                if len(f["files"]) > 4:
                    print(f"      … {len(f['files']) - 4} more")

    elif args.scan_test_fixtures:
        from tools.noctus.dev.recurrence import scan_test_fixture_recurrence
        kw = {"min_count": args.min_count} if args.min_count else {}
        result = scan_test_fixture_recurrence(**kw)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            stats = result["stats"]
            print(f"  {BOLD}Test fixture recurrence:{RESET} {stats['total_findings']} (high N>=3: {stats['high_severity']}, warning: {stats['warning_severity']})")
            print()
            for f in result["findings"][:30]:
                color = RED if f["severity"] == "high" else YELLOW
                print(f"  {color}[{f['severity']}]{RESET} {BOLD}{f['helper_name']}{RESET}  in {f['product_count']} products: {', '.join(f['products'])}")

    elif args.scan_migrations:
        from tools.noctus.dev.recurrence import scan_migration_patterns
        kw = {"min_count": args.min_count} if args.min_count else {}
        result = scan_migration_patterns(**kw)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            stats = result["stats"]
            print(f"  {BOLD}SQL migration patterns:{RESET} {stats['total_findings']} (high N>=3: {stats['high_severity']}, warning: {stats['warning_severity']})  ({stats['patterns_probed']} probes)")
            print()
            for f in result["findings"]:
                color = RED if f["severity"] == "high" else YELLOW
                print(f"  {color}[{f['severity']}]{RESET} {BOLD}{f['pattern_name']}{RESET}  in {f['product_count']}p ({f['total_occurrences']} occurrences)")
                for p, n in sorted(f["occurrences_by_product"].items(), key=lambda x: -x[1]):
                    print(f"      • {p}: {n}×")
                sugg = f["suggestion"]
                while sugg:
                    print(f"      → {sugg[:96]}")
                    sugg = sugg[96:]

    elif args.scan_pydantic:
        from tools.noctus.dev.recurrence import scan_pydantic_model_shapes
        kw = {"min_count": args.min_count} if args.min_count else {}
        result = scan_pydantic_model_shapes(**kw)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            stats = result["stats"]
            print(f"  {BOLD}Pydantic shape recurrence:{RESET} {stats['total_findings']} (high N>=3: {stats['high_severity']}, warning: {stats['warning_severity']})")
            print()
            for f in result["findings"][:20]:
                color = RED if f["severity"] == "high" else YELLOW
                cn = sorted({o["class_name"] for o in f["occurrences"]})
                fields = ", ".join(f"{n}: {t}" for n, t in f["field_set"][:5])
                print(f"  {color}[{f['severity']}]{RESET} ×{f['product_count']}p  classes={cn}  fields=({fields})")
                for o in f["occurrences"][:5]:
                    print(f"      • {o['class_name']} @ {o['file']}")

    elif args.scan_service_lines:
        from tools.noctus.dev.recurrence import scan_service_line_recurrence
        result = scan_service_line_recurrence()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            stats = result["stats"]
            print(f"  {BOLD}Service-line recurrence:{RESET} {stats['total_findings']} lines recur (high N>=3: {stats['high_severity']}, warning N=2: {stats['warning_severity']})")
            print()
            for f in result["findings"][:30]:
                color = RED if f["severity"] == "high" else YELLOW
                print(f"  {color}[{f['severity']}]{RESET} ×{f['product_count']}p: {f['line_text'][:100]}")
                print(f"      products: {', '.join(f['products'])}")
                sugg = f["suggestion"]
                if sugg:
                    while sugg:
                        print(f"      → {sugg[:96]}")
                        sugg = sugg[96:]

    elif args.scan_wiring:
        from tools.noctus.dev.scan_wiring import scan_wiring
        # Honour the line-170 worktree override: scan_wiring defaults to
        # `REPO_ROOT` when `repo_root=None`, and that import-time snapshot
        # predates the rebind — so pass the (possibly overridden) value.
        from settings import REPO_ROOT
        result = scan_wiring(args.scan_wiring, repo_root=REPO_ROOT)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if not result.get("ok", False):
                print(f"  {RED}✗ {result.get('error', 'scan failed')}{RESET}")
            else:
                t = result["totals"]
                color = GREEN if t["total"] == 0 else RED
                print(f"  {BOLD}Wiring scan ({result['product']}):{RESET} {color}{t['total']} finding(s){RESET}  "
                      f"(routes: {t['missing_routes']}, name-on-nome: {t['name_on_nome']}, "
                      f"shared-catch: {t['shared_catch_promise_all']})")
                print(f"  {BOLD}Diagnostics:{RESET} {result['fe_calls_found']} FE api-calls, "
                      f"{result['backend_routes_found']} backend routes")
                for leg, key in (("Leg A — missing routes", "missing_routes"),
                                 ("Leg B — name-on-nome", "name_on_nome"),
                                 ("Leg C — shared-catch Promise.all", "shared_catch_promise_all")):
                    for f in result[key][:20]:
                        print(f"    {RED}[{key}]{RESET} {f['file']}:{f['line']} — {f['detail'][:110]}")
                print(f"  {YELLOW}Next:{RESET} {result['next_action']}")
        sys.exit(1 if (result.get("ok", False) and result["totals"]["total"] > 0) else (2 if not result.get("ok", False) else 0))

    elif args.scan_remediation_markers:
        from tools.noctus.dev.scan_remediation_markers import scan_remediation_markers
        from settings import REPO_ROOT
        result = scan_remediation_markers(repo_root=REPO_ROOT)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            color = GREEN if result["exit_code"] == 0 else RED
            print(f"  {BOLD}NOC-REMEDIATE markers:{RESET} {result['total']} total  "
                  f"{color}({len(result['malformed'])} malformed, {len(result['on_except'])} on-except){RESET}")
            if result["by_class"]:
                print(f"  {BOLD}By class:{RESET} " + ", ".join(f"{c}={n}" for c, n in result["by_class"].items()))
            if result["promote_candidates"]:
                print(f"  {YELLOW}Promote (N≥3):{RESET} {', '.join(result['promote_candidates'])}")
            for label, key in (("FORBIDDEN on-except", "on_except"), ("malformed", "malformed")):
                for f in result[key][:20]:
                    print(f"    {RED}[{label}]{RESET} {f['path']}:{f['line']} — {f['text'][:90]}")
        sys.exit(result["exit_code"])

    elif args.review:
        from tools.noctus.dev.review import run_review
        mode = "evaluate" if args.evaluate else ("headless" if args.headless else "agent")
        # When --worktree-path is given the settings rebind above already
        # routes PRODUCTS_DIR; we also pass `products_dir=` explicitly to
        # `run_review` so the override is REDUNDANT-but-explicit (closes the
        # gap if a future refactor relinks review.py to anything that isn't
        # `from settings import PRODUCTS_DIR`).
        run_kwargs = {
            "product_slug": args.product,
            "mode": mode,
            "model": args.model,
        }
        if args.worktree_path:
            run_kwargs["products_dir"] = Path(args.worktree_path).expanduser().resolve() / "products"
        result = run_review(**run_kwargs)
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
        from tools.noctus.dev.analyzers import run_all_analyzers
        results = run_all_analyzers()
        print(f"  Duplicated functions: {len(results['duplicated_functions'])}")
        print(f"  Inline hooks: {len(results['inline_hooks'])}")
        print(f"  Python dep mismatches: {len(results['python_dep_mismatches'])}")
        tc = results['test_coverage']
        print(f"  Test gaps: {len(tc['issues'])}")
        if args.json:
            print(json.dumps(results, indent=2, default=str))

    elif args.discover:
        from tools.noctus.dev.analyzers import run_all_analyzers
        from tools.noctus.dev.ai_brain import analyze_findings, is_ai_available
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
        from tools.noctus.dev.analyzers import get_code_metrics
        metrics = get_code_metrics()
        print(f"  {'Product':<20} {'BE':<8} {'FE':<8} {'R':<4} {'S':<4} {'P':<4} {'H':<4}")
        print(f"  {'─'*20} {'─'*8} {'─'*8} {'─'*4} {'─'*4} {'─'*4} {'─'*4}")
        for m in metrics:
            print(f"  {m['product']:<20} {m['backend_lines']:<8} {m['frontend_lines']:<8} {m['routers']:<4} {m['services']:<4} {m['pages']:<4} {m['hooks']:<4}")

    elif args.sync_prompts:
        from tools.noctus.dev.master_prompts import verify_master_prompt
        bundle = verify_master_prompt(all_products=True, write=True)
        for r in bundle["products"]:
            status = f"{GREEN}synced{RESET}" if r.get("synced") else "up to date"
            print(f"  {r.get('slug', '?')}: {status}")

    elif args.test:
        from tools.noctus.dev.testing import run_all_tests
        results = run_all_tests()
        for r in results["products"]:
            color = GREEN if r.get("success") else RED
            print(f"  {r['product']:<20} {color}{r.get('passed', 0)} passed, {r.get('failed', 0)} failed{RESET}")
        print(f"\n  Total: {results['total_passed']} passed, {results['total_failed']} failed")

    # NOTE: `args.build` is handled earlier (parallel + scoped version with
    # `--changed` / `--product` support). The legacy `tools.testing.
    # build_all_frontends()` is kept available for direct callers but no
    # longer routed through the CLI.

    elif args.proposals:
        from tools.noctus.dev.proposals import list_proposals
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
        from tools.noctus.dev.catalog import generate_catalog
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

    elif args.component_bundle:
        from tools.noctus.dev.component_bundle import bundle_component
        bundle = bundle_component(args.component_bundle)
        if bundle is None:
            print(f"  {RED}component not found:{RESET} {args.component_bundle!r}")
            sys.exit(1)
        data = bundle.model_dump()
        if args.json:
            print(json.dumps(data, indent=2, default=str))
        else:
            status_color = GREEN if data["validation_status"] == "validated" else YELLOW
            print(f"  {BOLD}component_bundle:{RESET} {args.component_bundle}")
            print(f"    validation_status: {status_color}{data['validation_status']}{RESET}")
            print(f"    last_touched:      {data['last_touched'] or '(untracked)'}")
            print(f"    types ({len(data['types'])}): {', '.join(data['types'][:3])}{'...' if len(data['types']) > 3 else ''}")
            print(f"    deps  ({len(data['deps'])}): {', '.join(data['deps'][:3])}{'...' if len(data['deps']) > 3 else ''}")
            print(f"    consumers ({len(data['consumers'])}): {', '.join(data['consumers'][:2])}{'...' if len(data['consumers']) > 2 else ''}")
            print(f"    tests: {'yes' if data['tests'] else 'none'}")
            print(f"    wiring_snippet:")
            for line in data["wiring_snippet"].splitlines()[:5]:
                print(f"      {line}")

    elif getattr(args, "component_list", False):
        from tools.noctus.dev.component_list import list_components
        filter_statuses = (
            [s.strip() for s in args.filter_status.split(",")]
            if getattr(args, "filter_status", None)
            else None
        )
        sort_order = getattr(args, "sort", "consumers_desc")
        entries = list_components(sort=sort_order, filter_status=filter_statuses)
        if args.json:
            print(json.dumps([e.model_dump() for e in entries], indent=2, default=str))
        else:
            total = len(entries)
            status_counts: dict[str, int] = {}
            for e in entries:
                status_counts[e.validation_status] = status_counts.get(e.validation_status, 0) + 1
            print(f"  {BOLD}Component catalog{RESET} ({total} organs)")
            parts = []
            for s, n in sorted(status_counts.items()):
                color = GREEN if s == "validated" else (YELLOW if s == "emerging" else (RED if s == "shelfware" else RESET))
                parts.append(f"{color}{n} {s}{RESET}")
            if parts:
                print(f"    " + " · ".join(parts))
            print("")
            print(f"  {'Name':<32} {'Consumers':>10}  {'Status':<12}")
            print(f"  {'-' * 32} {'-' * 10}  {'-' * 12}")
            for entry in entries:
                color = GREEN if entry.validation_status == "validated" else (
                    YELLOW if entry.validation_status == "emerging" else (
                    RED if entry.validation_status == "shelfware" else RESET))
                print(
                    f"  {entry.name:<32} {entry.consumers_count:>10}  "
                    f"{color}{entry.validation_status:<12}{RESET}"
                )

    elif getattr(args, "find_reusable_component", None):
        from tools.noctus.dev.find_reusable_component import find_reusable_component as _frc
        filter_statuses = (
            [s.strip() for s in args.filter_status.split(",")]
            if getattr(args, "filter_status", None)
            else None
        )
        top_k = getattr(args, "top_k", 5)
        matches = _frc(args.find_reusable_component, top_k=top_k, filter_status=filter_statuses)
        if args.json:
            print(json.dumps([m.model_dump() for m in matches], indent=2, default=str))
        else:
            print(f"  {BOLD}find_reusable_component:{RESET} {args.find_reusable_component!r}")
            print(f"  {top_k} requested · {len(matches)} returned")
            print("")
            if not matches:
                print(f"  {YELLOW}No matches found.{RESET} Register organs first: --register-all-canonical-organs")
            for m in matches:
                color = GREEN if m.validation_status == "validated" else (
                    YELLOW if m.validation_status == "emerging" else (
                    RED if m.validation_status == "shelfware" else RESET))
                print(f"  {BOLD}{m.name}{RESET} (score={m.score:.3f})")
                print(f"    {color}{m.validation_status}{RESET} · {m.consumers_count} consumers · {m.path or 'path unknown'}")
                print(f"    snippet: {m.snippet[:80].strip()!r}")

    elif getattr(args, "register_organ", None):
        _ensure_llm_configured()
        from tools.noctus.dev.find_reusable_component import register_organ as _ro
        result = _ro(args.register_organ)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            status_color = GREEN if result.get("ok") else RED
            print(f"  {BOLD}register_organ:{RESET} {args.register_organ!r}")
            print(f"    {status_color}{result.get('status', 'unknown')}{RESET} · sha={result.get('source_sha', '')[:12]} · rows={result.get('rows_written', 0)}")

    elif getattr(args, "register_all_canonical_organs", False):
        _ensure_llm_configured()
        from tools.noctus.dev.find_reusable_component import register_all_canonical_organs as _raco
        results = _raco()
        if args.json:
            print(json.dumps(results, indent=2, default=str))
        else:
            print(f"  {BOLD}register_all_canonical_organs{RESET}")
            for r in results:
                status_color = GREEN if r.get("ok") else RED
                print(f"    {status_color}{r['name']:<28}{RESET} {r.get('status', 'unknown'):<20} sha={r.get('source_sha', '')[:12]}")

    elif getattr(args, "organ_knowledge_append", None):
        from tools.noctus.dev.organ_knowledge import organ_knowledge_append as _oka
        field = getattr(args, "organ_field", None)
        raw_entry = getattr(args, "organ_entry", None)
        if not field or raw_entry is None:
            print(f"  {RED}--organ-knowledge-append requires --organ-field and --organ-entry.{RESET}")
            return
        entry: object = raw_entry
        if getattr(args, "organ_entry_json", False):
            entry = json.loads(raw_entry)
        # The re-embed leg touches OpenAI; ensure LLM is configured unless batching.
        re_embed = not getattr(args, "no_organ_re_embed", False)
        if re_embed:
            _ensure_llm_configured()
        result = _oka(args.organ_knowledge_append, field, entry, re_embed=re_embed)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            status_color = GREEN if result.get("ok") else RED
            print(f"  {BOLD}organ_knowledge_append:{RESET} {args.organ_knowledge_append!r}.{field}")
            print(f"    {status_color}{result.get('status', 'unknown')}{RESET} · action={result.get('action', '-')} · re_embedded={result.get('re_embedded', False)} · sha={result.get('source_sha', '')[:12]}")

    elif getattr(args, "organ_knowledge_query", None):
        from tools.noctus.dev.organ_knowledge import organ_knowledge_query as _okq, LIST_FIELDS, SCALAR_FIELDS, OBJECT_FIELDS
        result = _okq(args.organ_knowledge_query)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            if not result.get("ok"):
                print(f"  {RED}organ_knowledge_query: {result.get('status')}{RESET} — {args.organ_knowledge_query!r}")
            else:
                print(f"  {BOLD}{result['name']}{RESET} · {result.get('validation_status', 'unknown')} · {result.get('path', 'path unknown')}")
                for k in sorted(LIST_FIELDS):
                    vals = result.get(k) or []
                    print(f"    {BOLD}{k}{RESET} ({len(vals)})")
                    for v in vals:
                        print(f"      - {str(v)[:100]}")
                for k in sorted(SCALAR_FIELDS):
                    print(f"    {BOLD}{k}{RESET}: {result.get(k)}")
                for k in sorted(OBJECT_FIELDS):
                    print(f"    {BOLD}{k}{RESET}: {result.get(k)}")

    elif args.lgpd_list:
        from tools.noctus.dev.lgpd import list_warnings
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
        from tools.noctus.dev.lgpd import flag
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
        from tools.noctus.dev.improvements import generate_improvements
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

    elif args.outline_python or args.outline_typescript:
        if args.outline_python:
            from tools.noctus.dev.outline_python import outline_python
            result = outline_python(args.outline_python)
        else:
            from tools.noctus.dev.outline_typescript import outline_typescript
            result = outline_typescript(args.outline_typescript)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        elif result.parse_error:
            print(f"  {RED}Parse error:{RESET} {result.parse_error}")
            sys.exit(1)
        else:
            print(f"  {BOLD}File:{RESET} {result.path}  ({result.total_lines} lines, {result.symbol_count} symbols)")
            if result.imports:
                print(f"\n  {BOLD}Imports:{RESET}")
                for s in result.imports:
                    print(f"    L{s.line:>4}  {s.name[:80]}")
            if result.constants:
                print(f"\n  {BOLD}Constants:{RESET}")
                for s in result.constants:
                    print(f"    L{s.line:>4}  {s.name}")
            if result.classes:
                print(f"\n  {BOLD}Classes / interfaces / types:{RESET}")
                for s in result.classes:
                    deco = (" @" + " @".join(s.decorators)) if s.decorators else ""
                    doc = f"  — {s.docstring_first_line[:60]}" if s.docstring_first_line else ""
                    # Use the actual kind as the keyword prefix (class / interface / type)
                    prefix = s.kind if s.kind in {"class", "interface", "type"} else "class"
                    print(f"    L{s.line:>4}-{s.end_line:<4}  {prefix} {s.name}{deco}{doc}")
                    cls_methods = [m for m in result.methods if m.parent == s.name]
                    for m in cls_methods:
                        async_marker = " (async)" if m.kind.startswith("async") else ""
                        m_doc = f"  — {m.docstring_first_line[:60]}" if m.docstring_first_line else ""
                        print(f"      L{m.line:>4}-{m.end_line:<4}  {m.name}{async_marker}{m_doc}")
            if result.functions:
                print(f"\n  {BOLD}Functions:{RESET}")
                for s in result.functions:
                    async_marker = " (async)" if s.kind.startswith("async") else ""
                    deco = (" @" + " @".join(s.decorators)) if s.decorators else ""
                    doc = f"  — {s.docstring_first_line[:60]}" if s.docstring_first_line else ""
                    print(f"    L{s.line:>4}-{s.end_line:<4}  {s.name}{async_marker}{deco}{doc}")

    elif args.count_tokens or args.count_tokens_text:
        from tools.noctus.dev.cost_evaluation import count_tokens
        exts = DEFAULT_EXTENSIONS = (".md",)
        if args.count_tokens_ext:
            raw = [e.strip() for e in args.count_tokens_ext.split(",") if e.strip()]
            exts = tuple("*" if e == "*" else (e if e.startswith(".") else f".{e}") for e in raw)
        result = count_tokens(
            path=args.count_tokens,
            text=args.count_tokens_text,
            extensions=exts,
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            tok_label = result.tokenizer_used
            tok_color = GREEN if tok_label.startswith("tiktoken") else YELLOW
            print(f"  {BOLD}Tokenizer:{RESET} {tok_color}{tok_label}{RESET}")
            if tok_label.startswith("approximate"):
                print(f"  {YELLOW}(install `tiktoken` in the venv for ~5-10% precision vs ~25% on the approximation){RESET}")
            print(f"  {BOLD}Total tokens:{RESET} {result.total_tokens:,}")
            print(f"  {BOLD}Total chars:{RESET}  {result.total_chars:,}")
            print(f"  {BOLD}Total words:{RESET}  {result.total_words:,}")
            print(f"  {BOLD}Total lines:{RESET}  {result.total_lines:,}")
            print(f"  {BOLD}Files:{RESET}        {result.file_count}")
            if result.inline_text_tokens:
                print(f"  {BOLD}Inline text tokens:{RESET} {result.inline_text_tokens:,}")
            if result.per_file and len(result.per_file) <= 30:
                print()
                for fc in result.per_file:
                    print(f"    {fc.tokens:>8,} tok  {fc.lines:>6,} lines  {fc.path}")
            elif result.per_file:
                print(f"\n  ({len(result.per_file)} files — pass --json for full breakdown)")

    elif args.mole:
        from tools.noctus.dev.mole import run_mole
        r = run_mole(mode=args.mole, force=args.force)
        print(json.dumps(r, indent=2, default=str))
        sys.exit(int(r.get("exit_code", 0)))

    elif args.update_kb_counts:
        from tools.kb_sync import update_kb_counts
        r = update_kb_counts(check=args.check)
        print(r.get("message", json.dumps(r, default=str)))
        sys.exit(int(r.get("exit_code", 1 if r.get("drift") else 0)))

    elif args.sync_seed_template:
        from tools.noctus.dev.sync_seed_template import sync_seed_template
        r = sync_seed_template(dry=args.dry)
        print(r.get("message", json.dumps(r, default=str)))
        sys.exit(0 if r.get("ok", False) else 1)

    elif args.stamp_seed_version:
        from tools.noctus.dev.stamp_seed_version import stamp_seed_version
        r = stamp_seed_version()
        print(r.get("message", json.dumps(r, default=str)))
        sys.exit(0 if r.get("ok", False) else 1)

    elif args.check_version_bump:
        from tools.noctus.dev.version_guard import check_version_bump
        from settings import REPO_ROOT
        r = check_version_bump(repo_root=REPO_ROOT)
        print(r.get("message", json.dumps(r, default=str)))
        sys.exit(0 if r.get("ok", False) else 1)

    elif args.render_project_history:
        from tools.noctus.dev.history import render_project_history
        r = render_project_history(check=args.check)
        print(json.dumps(r, default=str))
        sys.exit(1 if (args.check and r.get("drift")) else 0)

    elif args.backfill_project_history:
        from tools.noctus.dev.history import backfill_project_history
        r = backfill_project_history(dry_run=args.dry)
        print(json.dumps(r, default=str))
        sys.exit(0)

    elif args.gen_promotions_index:
        from tools.noctus.dev.promotion import gen_promotions_index
        r = gen_promotions_index(check=args.check)
        print(json.dumps(r, default=str))
        sys.exit(1 if (args.check and r.get("drift")) else 0)

    elif args.archive_clean:
        from tools.noctus.dev.archive import archive_clean
        r = archive_clean(force=args.force)
        print(json.dumps(r, indent=2, default=str))
        sys.exit(0)

    elif args.check_disk_usage:
        from tools.noctus.dev.disk_usage import check_disk_usage
        r = check_disk_usage()
        print(json.dumps(r, indent=2, default=str))
        sys.exit(int(r.get("exit_code", 0)))

    elif args.check_framework_deps:
        from tools.noctus.dev.check_framework_deps import check_framework_deps
        r = check_framework_deps()
        print(json.dumps(r, indent=2, default=str))
        sys.exit(int(r.get("exit_code", 1 if r.get("drift") else 0)))

    elif args.cleanup_stale_worktrees:
        from tools.noctus.dev.cleanup_worktrees import cleanup_stale_worktrees
        r = cleanup_stale_worktrees(force=args.force)
        print(json.dumps(r, indent=2, default=str))
        sys.exit(0)

    elif args.tmp_cleanup:
        from tools.noctus.dev.tmp_cleanup import tmp_cleanup
        r = tmp_cleanup(dry_run=not args.force, max_age_days=args.tmp_cleanup_max_age_days)
        print(json.dumps(r, indent=2, default=str))
        sys.exit(0 if r.get("ok") else 1)

    elif args.cache_pull:
        from tools.noctus.dev.cache_deploy_mirror import pull_all
        only = [s.strip() for s in args.cache_pull_only.split(",")] if args.cache_pull_only else None
        r = pull_all(only=only)
        print(json.dumps(r, indent=2, default=str))
        sys.exit(0 if r.get("ok") else 1)

    elif args.check_merge_debt:
        from tools.noctus.dev.merge_debt import check_merge_debt
        r = check_merge_debt()
        print(json.dumps(r, indent=2, default=str))
        sys.exit(int(r.get("exit_code", 0)))

    elif args.propagate:
        from tools.noctus.dev.propagate import propagate_composes, propagate_dockerfiles
        codes = []
        if args.propagate in ("composes", "both"):
            rc = propagate_composes(dry=args.dry, check=args.check)
            print(json.dumps(rc, default=str)); codes.append(int(rc.get("exit_code", 0)))
        if args.propagate in ("dockerfiles", "both"):
            rd = propagate_dockerfiles(dry=args.dry, check=args.check)
            print(json.dumps(rd, default=str)); codes.append(int(rd.get("exit_code", 0)))
        sys.exit(max(codes) if codes else 0)

    elif args.smoke_fleet:
        from tools.noctus.dev.smoke_fleet import smoke_fleet
        r = smoke_fleet()
        print(json.dumps(r, indent=2, default=str))
        sys.exit(int(r.get("exit_code", 0)))

    elif args.predeploy_check:
        from tools.noctus.dev.predeploy_check import predeploy_check
        r = predeploy_check(args.predeploy_check, auto_fix=bool(getattr(args, "fix", False)))
        print(json.dumps(r, indent=2, default=str))
        sys.exit(int(r.get("exit_code", 0)))

    elif args.deploy_pull:
        from tools.noctus.dev.deploy_pull import deploy_pull
        r = deploy_pull(
            target=args.deploy_target,
            ssh_host=args.deploy_host,
            confirm=bool(getattr(args, "deploy_confirm", False)),
        )
        print(json.dumps(r, indent=2, default=str))
        sys.exit(int(r.get("exit_code", 0)))

    elif args.deploy_image:
        from tools.noctus.dev.deploy_image import deploy_image
        r = deploy_image(
            args.deploy_image,
            ssh_host=args.deploy_host,
            source=getattr(args, "deploy_image_source", "pull"),
            confirm=bool(getattr(args, "deploy_image_confirm", False)),
        )
        print(json.dumps(r, indent=2, default=str))
        sys.exit(int(r.get("exit_code", 0)))

    elif getattr(args, "compose_brief", False):
        if not getattr(args, "files", None) or not getattr(args, "description", None):
            print(f"  {RED}Error:{RESET} --compose-brief requires both --files and --description.")
            sys.exit(2)
        from tools.noctus.dev.engineer_brief_compose import compose_brief
        target_files = [f.strip() for f in args.files.split(",") if f.strip()]
        result = compose_brief(
            target_files=target_files,
            description=args.description,
            agent=getattr(args, "agent", None),
        )
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"  {BOLD}Suggested agent:{RESET} {result['suggested_agent']}")
            print(f"  {BOLD}KB references:{RESET} {len(result['kb_references'])}")
            print(f"  {BOLD}Auto-improvement context:{RESET} {len(result['auto_improvement_context'])} entry(ies)\n")
            print(result["brief"])
        sys.exit(0)

    elif args.vector_costs_report:
        from tools.noctus.dev.vector_costs import report as _vc_report
        rows = _vc_report(
            namespace=getattr(args, "namespace", None),
            since=getattr(args, "since", None),
            group_by=getattr(args, "group_by", "day"),
        )
        if not rows:
            print(f"  {YELLOW}(no vector cost rows — ledger empty or no match for given filters){RESET}")
            sys.exit(0)
        print(f"  {GREEN}✓ Vector cost report ({len(rows)} period(s)):{RESET}")
        print(json.dumps(rows, indent=2, default=str))
        sys.exit(0)

    elif args.vector_costs_total:
        from tools.noctus.dev.vector_costs import total as _vc_total
        result = _vc_total(
            namespace=getattr(args, "namespace", None),
            since=getattr(args, "since", None),
        )
        print(f"  {GREEN}✓ Vector cost total:{RESET}")
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0)

    elif args.dispatch_budget_log:
        from tools.noctus.dev.dispatch_budget import log_dispatch as _db_log
        agent = getattr(args, "agent", None)
        slug = getattr(args, "budget_slug", None)
        input_tokens = getattr(args, "input_tokens", None)
        output_tokens = getattr(args, "output_tokens", None)
        model = getattr(args, "budget_model", None)
        missing = [f for f, v in [("--agent", agent), ("--budget-slug", slug),
                                   ("--input-tokens", input_tokens),
                                   ("--output-tokens", output_tokens),
                                   ("--budget-model", model)] if v is None]
        if missing:
            print(f"  {RED}Error:{RESET} --dispatch-budget-log requires: {', '.join(missing)}")
            sys.exit(2)
        result = _db_log(
            agent=agent,
            slug=slug,
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            model=model,
            source_ref=getattr(args, "source_ref", None),
        )
        if result["ok"]:
            print(f"  {GREEN}✓ Dispatch budget row logged:{RESET}")
            print(json.dumps(result["row"], indent=2, default=str))
        else:
            print(f"  {RED}✗ Failed to log dispatch budget row: {result.get('error')}{RESET}")
            sys.exit(1)
        sys.exit(0)

    elif args.dispatch_budget_report:
        from tools.noctus.dev.dispatch_budget import report as _db_report
        rows = _db_report(
            agent=getattr(args, "agent", None),
            model=getattr(args, "budget_model", None),
            window_days=getattr(args, "window_days", 7) or 7,
        )
        if not rows:
            print(f"  {YELLOW}(no dispatch budget rows — ledger empty or no match for given filters){RESET}")
            sys.exit(0)
        print(f"  {GREEN}✓ Dispatch budget report ({len(rows)} group(s)):{RESET}")
        print(json.dumps(rows, indent=2, default=str))
        sys.exit(0)

    elif args.dispatch_budget_summary:
        from tools.noctus.dev.dispatch_budget import summary as _db_summary
        result = _db_summary(
            agent=getattr(args, "agent", None),
            model=getattr(args, "budget_model", None),
            window_days=getattr(args, "window_days", 0),
        )
        count = result["dispatch_count"]
        if count == 0:
            print(f"  {YELLOW}(0 entries — dispatch-budget ledger empty){RESET}")
        else:
            print(f"  {GREEN}✓ Dispatch budget summary ({count} dispatch(es)):{RESET}")
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0)

    elif args.surface_to_tech_lead:
        from tools.noctus.dev.surface_to_tech_lead import surface_to_tech_lead as _stl
        reason = getattr(args, "surface_reason", None) or ""
        proposal = getattr(args, "surface_proposal", None) or ""
        state = getattr(args, "surface_state", None) or ""
        attempted = getattr(args, "surface_attempted", None) or ""
        if not reason:
            print(f"  {RED}Error:{RESET} --surface-reason is required with --surface-to-tech-lead")
            sys.exit(2)
        result = _stl(
            reason=reason,
            proposal_md=proposal,
            current_state_md=state,
            attempted_resolution_md=attempted,
            worktree_path=getattr(args, "worktree_path", None),
        )
        if result.get("ok"):
            print(f"  {GREEN}Surface filed:{RESET} {result['surface_id']}")
            print(f"  Path: {result['surface_path']}")
            print(f"  Exit marker: {result['exit_marker_msg']}")
        else:
            print(f"  {RED}Error:{RESET} {result.get('error')}")
            sys.exit(1)
        sys.exit(0)

    elif args.list_pending_surfaces:
        from tools.noctus.dev.list_pending_surfaces import list_pending_surfaces as _lps
        include = getattr(args, "include_responded", False)
        surfaces = _lps(include_responded=include)
        if not surfaces:
            print(f"  {YELLOW}(0 pending surfaces){RESET}")
        else:
            print(f"  {GREEN}{len(surfaces)} surface(s):{RESET}")
            print(json.dumps(surfaces, indent=2, default=str))
        sys.exit(0)

    elif getattr(args, "respond_and_resume_id", None):
        from tools.noctus.dev.respond_and_resume import respond_and_resume as _rar
        surface_id = args.respond_and_resume_id
        decision = getattr(args, "surface_decision", None)
        rationale = getattr(args, "surface_rationale", None) or ""
        updated_brief = getattr(args, "surface_updated_brief", None)
        if not decision:
            print(f"  {RED}Error:{RESET} --surface-decision (approve|reject|adapt) is required")
            sys.exit(2)
        if not rationale:
            print(f"  {RED}Error:{RESET} --surface-rationale is required")
            sys.exit(2)
        result = _rar(
            surface_id=surface_id,
            decision=decision,
            rationale_md=rationale,
            updated_brief_md=updated_brief,
        )
        if result.get("ok"):
            print(f"  {GREEN}Responded to surface:{RESET} {surface_id}")
            print(f"  Decision: {result['decision']}")
            print(f"  Response at: {result['response_path']}")
            print(f"  Next: --dispatch-resume-brief {surface_id}")
        else:
            print(f"  {RED}Error:{RESET} {result.get('error')}")
            sys.exit(1)
        sys.exit(0)

    elif getattr(args, "dispatch_resume_brief_id", None):
        from tools.noctus.dev.dispatch_resume import dispatch_resume_brief as _drb
        surface_id = args.dispatch_resume_brief_id
        result = _drb(surface_id=surface_id)
        if result.get("ok"):
            print(f"  {GREEN}Resume brief composed:{RESET} surface_id={surface_id}")
            print(f"  Worktree: {result['worktree_path']}")
            print(f"  Decision: {result['decision']}")
            print(f"\n--- BRIEF TEXT (pass verbatim to Agent() dispatch) ---")
            print(result["brief_text"])
        else:
            print(f"  {RED}Error:{RESET} {result.get('error')}")
            sys.exit(1)
        sys.exit(0)

    else:
        # Default: validate + analyze
        from tools.noctus.dev.compliance import check_all_products
        from tools.noctus.dev.analyzers import run_all_analyzers
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
