# Tooling craft canon — building the platform's own toolkit (MCP tools, keepers, caches, hooks)

> Owner: agent `tooling-engineer`. Born 2026-11-05 (agent-refinement W2-S4), the slice that hired a platform/devtools engineer for `mcp/`. Before this doc, the toolkit's design rules were spread across architect docs (`mcp-tool-conventions.md`, `mcp-first-scripts.md`, `dev-toolkit-scaffolders.md`), devops cache docs and a dozen unowned commons. All of them were born from incidents. None of them cited the profession: the MCP spec, the agent-tool guidance, CLI guidelines, static-analysis research, SQLite's own concurrency docs.

## 0 · What this is, and how to use it

**What.** The profession's canon for internal developer tooling, mapped onto the toolkit this platform actually runs:
- `mcp/noctusai/` is a FastMCP stdio server. At this writing it has 198 modules under `tools/noctus/dev/` and a `cli.py` with 395 `--flag`s.
- `compliance.py` holds the keepers: 178 `check_*` / `_check_*` functions in 26 079 lines. Counting the other tool modules, there are 190 distinct `check_*` names.
- Around them sit 9 SQLite caches, the git hooks in `scripts/hooks/`, the Claude Code guard hooks and the harness mod `noc-harness`.

Each section runs principle → how it applies HERE (file:line) → checklist → anti-patterns.

**Why.** The house already turns every incident into a keeper, a guard or a docstring. That loop is reactive: it only knows what has already hurt. The canon is the proactive half. It says what a tool, a check or a cache needs before the incident that teaches it.

**How to use it.**
- **The house mechanism wins.** Where a house doc already decides something, this canon points at it and does not re-decide it. That covers naming in `mcp-tool-conventions.md` §1, the shell carve-outs in `mcp-first-scripts.md` §1, gate + mechanism in `gate-methodology-sync.md`, and the cache tiers in `cache-auto-freshness.md`. The canon fills gaps and names the standard behind each house rule.
- **Merge flow is out of scope.** `task_branch`, the merge queue, CI workflows, `noc-ship` / `noc-self-branch` / `noc-branch-dispatch`, `self-branching-mode.md`, `dev-main-ci-gates.md` and `hardware-admission-budget.md` belong to the git/CI redesign. This doc points at them and never edits their rules.
- **Read the section, not the doc.** Each § stands alone. §12 holds the one-page checklists to use while you work.

**Standard term ↔ house term.**

| Standard term | House term / mechanism |
|---|---|
| Static-analysis check / lint rule | **keeper**: a `check_*` function in `mcp/noctusai/tools/noctus/dev/compliance.py` returning `list[{product, file, issue, severity}]` |
| Architectural fitness function | a keeper that guards an architecture property (seed-first, organ consumption, owns_kb alignment) |
| Lint suppression (`# noqa: CODE`) | an escape marker with a reason on the flagged line, e.g. `// noc-allow: invalidate-only — why` (`compliance.py:8701`) |
| Baseline / ratchet (Betterer) | a per-file baseline JSON that may only shrink, e.g. `mcp/noctusai/tests/mutation_invalidate_only_baseline.json` |
| Pre-commit framework | `scripts/hooks/pre-commit` (1 556 lines), a thin dispatcher into `cli.py --<flag>` (`mcp-first-scripts.md` §1 `[carve:hook]`) |
| Agent tool / ACI (agent-computer interface) | an MCP tool `noctus.dev.<action>` registered through `register(server)` |
| Tool annotations (`readOnlyHint`…) | not used yet (§2.7). The house uses `confirm=False` dry-run defaults and the `refuse_gate` / `warn_gate` posture instead |
| Materialized view / derived cache | **keeper-mirror cache**: a SQLite file derived from tracked sources, never hand-edited (`cache_backend._CACHE_FILES`, `cache_backend.py:97`) |
| Cache key / content address | `source_sha` / `bundle_sha`: a sha256 of the source bytes |
| Cache invalidation policy | the **3-leg mirror contract**: eager pre-commit refresh + lazy query-time rebuild + loud freshness keeper (`agent-context-architecture.md` § Agent-context cache) |
| Platform team (Team Topologies) | the tooling engineer + the tech-lead. The stream-aligned "teams" are the dispatched engineers and the owner |
| Golden path | a scaffolder (`noctus.dev.scaffold_*`) + its skill (`noc-mcp-tool`, `skill-creator`) |
| Feature flag kill switch | a harness-mod `userConfig` UX switch. **Never** a gate switch (`harness-mods.md` § Invariants (d)) |
| Stale deployment detection | `toolkit_freshness` (a stale MCP server process) |
| Flaky / unmeasurable result | `inconclusive` / `harness_invalid` in `gate_sweep._verdict` (`gate_sweep.py:2039`) |

---

## 1 · Platform as a product — who the toolkit serves

**Principle.** A platform exists to reduce the cognitive load of the teams that use it. Standardization and cost are side effects, not the goal (Fowler, *Team Topologies*). Build the **thinnest viable platform**: the smallest thing that meets the need, never thicker than necessary (Team Topologies, TVP). Treat the platform as a product with users, user experience, documentation and onboarding (golden paths), self-service, optional and composable parts, and secure defaults. Measure it by user satisfaction, efficiency and delivery (CNCF Platforms White Paper).

**Here — the users, in order of call volume.**
1. **Dispatched engineer agents** (Sonnet by default). They arrive cold and know only the brief, CLAUDE.md and their L1 file. They discover tools through the deferred-tool list, which shows **names only** until `ToolSearch` loads a schema. So the tool name and its first description sentence are the whole storefront.
2. **The tech-lead session.** It is the orchestrator and calls the high-stakes tools: `task_branch`, `release`, `deploy_image`, `gate_sweep`.
3. **Git and the harness.** `scripts/hooks/*` call `cli.py --<flag>`. The Claude Code guards call stdlib library code by path (`mcp-first-scripts.md` §3 rows `claude-guard-*`).
4. **The owner.** Reads `noc-harness` panels and `/slash` commands, and pays for every embedding call (`vector-cost-tracking.md`).

**Thinnest viable platform, applied.**
- **Extend before you spawn.** A new cache is a new `chunk_kind` on an existing cache unless the storage shape truly differs (`vectorize-embed-cache-framework.md` leg 1). A new tool is a new action on an existing module when the inputs overlap.
- **Fewer, consolidated tools beat many thin ones** (Anthropic, *Writing effective tools*: "More tools don't always lead to better outcomes"). The toolkit has 300+ tools. Every new tool costs a line in every session's deferred list. That is real, recurring context cost (`agent-context-architecture.md` § Why, force 1).
- **Prefer removing to adding.** `gate-methodology-sync.md` § Walls already says it for gates: "Prefer removing a gate to adding one." The same holds for tools that nobody calls (§7 tells you how to know).

**Docs are part of the product.** A tool's description is its man page. A keeper's `issue` string is its error message. A KB pattern is its tutorial. A tool that works but whose description is wrong fails as a product. Example: `server.py:268` still tells every client that "Legacy flat names (`noctusai_<action>`) are registered as aliases until consumers migrate". `mcp-tool-conventions.md` §1 says they were retired on 2026-05-03. Agents read the first claim at every session start.

**Checklist — before building anything in `mcp/`.**
- [ ] Who calls it, and how often? Agent, tech-lead, hook or owner?
- [ ] Does an existing tool or cache already answer it? Grep `tools/noctus/dev/__init__.py` and the deferred tool list, and ask `noctus.dev.kb_search`.
- [ ] Is it the thinnest version? Could it be a parameter on an existing tool?
- [ ] Where is the doc, and is it the same commit (`doc-staleness-gate.md`)?

**Anti-patterns.** A tool per incident with no consolidation pass. A cache per question. Docs as an afterthought. A gate as the only "user interface" of a rule (`gate-methodology-sync.md` § Anti-patterns, "Gate-only").

---

## 2 · MCP tool design

### 2.1 Naming and discovery

**Principle.** The MCP spec allows 1-128 characters from `A-Z a-z 0-9 _ - .`. Names are case-sensitive, and aggregating clients SHOULD disambiguate by prefixing a server identifier (MCP spec 2026-07-28, *Tools* § Tool Names). Namespacing groups related tools and draws boundaries between them. Whether a prefix or a suffix works better is an empirical question (Anthropic, *Writing effective tools*).

**Here.** `<umbrella>.<service>.<action>`, three dotted segments with no exceptions (`mcp-tool-conventions.md` §1). Claude Code rewrites the dots: the agent sees `mcp__noctusai__noctus_dev_gate_sweep`, so **the action segment must be greppable and self-describing on its own**. Registration is one `register(server)` per module, called from `tools/noctus/dev/__init__.py::register_all`. Example: `gate_sweep` is imported at `__init__.py:65` and registered at `:225`.

**Rules.**
- Name after the user's intent, not the implementation: `search_*` over `list_*` (Anthropic). The house's `kb_search` / `code_search` / `memory_search` / `corpus_search` follow this.
- A family shares a stem (`agent_context`, `agent_context_list`, `agent_context_refresh`), so the deferred list sorts them together.
- Verb last for actions on a noun (`vector_costs_report`), never a catch-all `run` / `do` (clig.dev, "Don't have a catch-all subcommand").

### 2.2 Inputs: schema, strictness and poka-yoke

**Principle.** `inputSchema` MUST be a valid JSON Schema object, and a tool with no parameters is recommended to declare `{"type":"object","additionalProperties":false}` (MCP spec, *Tools*). Servers MUST validate all tool inputs (MCP spec, *Tools* § Security Considerations). *Poka-yoke* your tools: change the arguments so mistakes are harder to make (Anthropic, *Building effective agents*, Appendix 2). Use unambiguous parameter names, `user_id` not `user` (Anthropic, *Writing effective tools*).

**Here — the house closed a real silent-error.** FastMCP registers its handler with `validate_input=False`, so pydantic **drops** undeclared arguments and every parameter falls back to its default. `task_branch`'s default is `action="status"`: read-only, `ok: true`. Four failed `start` / `integrate` calls therefore "succeeded" (2026-09-19). The fix is `install_strict_tool_arguments` (`server.py:203`), installed after `register_all` (`server.py:297`). It refuses any unknown argument with a `ToolError` that names the accepted set. Setting `additionalProperties: false` on the schema was measured and is **not** enforced server-side, so it stays a client hint only. Keeper `check_mcp_tools_reject_unknown_args` (`compliance.py:25892`) asserts the gate stays installed.

**Rules.**
- **The default must be the safe, cheap action**, and a mutation must be named explicitly. Never make a mutating action the default value of an `action` parameter.
- **Absolute paths, explicit trees.** The server runs in a fixed CWD (the primary checkout). A tool that reads or writes tree-dependent state takes `worktree_path: str | None` and resolves it with `workspace.resolve_caller_root`. Reads are included (`mcp-tool-conventions.md` §5 and §5a). Keeper `check_mcp_write_tool_worktree_arg` (`compliance.py:4425`, `warning`) is the backstop.
- Paths and ids from the caller are validated against traversal before they touch disk. Example: `surface_id` is restricted to alphanumerics + `-._@` (`surface-and-resume-tooling.md`).
- Enumerations are `Literal[...]`, not free strings, so the schema itself carries the allowlist.

### 2.3 Write tools: dry-run, confirm and refuse-by-default

**Principle.** A dangerous action takes `--dry-run`, prompts when interactive, and requires `--force` (or `--confirm=<name>` for severe actions) when not (clig.dev, *Arguments and flags*). Clients SHOULD confirm sensitive operations, and there SHOULD always be a human in the loop who can deny an invocation (MCP spec, *Tools* § Security Considerations).

**Here.**
- `confirm: bool = False` is the house write gate. With `False`, the call returns the plan. With `True`, it acts and writes an audit line. `scaffold_mcp_tool(kind="write")` emits the gate and the audit logger by construction (`scaffold_mcp_tool.py:34-45`). `migrate_product`, `release` and `deploy_image` all default to preview.
- **Stale-code refusal.** `toolkit_freshness.refuse_gate` (`toolkit_freshness.py:801`) wraps `deploy_image` (`deploy_image.py:458`), `migrate_product` (`migrate_product.py:1103`) and `release` (`release.py:606`). `warn_gate` (`:335`) wraps `deploy_verify` and `spa_smoke`. The line between the two: **can a stale version silently produce a plausible-looking wrong result?** If yes, refuse. Touching prod is not the test (`toolkit_freshness.py:811-818`).

### 2.4 Output: structured, concise, high signal

**Principle.**
- If a tool declares an `outputSchema`, servers MUST return conforming `structuredContent`. They SHOULD also return the serialized JSON in a text block for backwards compatibility (MCP spec, *Tools* § Structured Content).
- Return only high-signal information, prefer human-readable identifiers, and offer a `response_format` of concise vs detailed (Anthropic, *Writing effective tools*).
- Paginate, filter and truncate with sensible defaults. Claude Code caps tool responses at 25 000 tokens by default (same source).

**Here.**
- `build_server` defaults `structured_output=False` fleet-wide (`server.py:285`). Most tools return plain dicts and unions, and newer mcp/pydantic aborted `register_all` (zero tools) on any non-BaseModel return annotation. A tool that wants structured output opts in explicitly. **Gap:** almost no tool declares an `outputSchema`, so clients cannot validate results. `mcp-tool-conventions.md` §2 already asks new tools for a Pydantic `XxxOutput`. Pass it with `structured_output=True` when the shape has stabilised.
- Verdict fields are **enumerated states, never booleans that conflate**. `gate_sweep._verdict` (`gate_sweep.py:2039-2071`) returns `red` / `inconclusive` / `incomplete` / `green`, and "not run" is never green. That is the toolkit's model output shape.
- Filter-proxy tools exist to fit under the 25k cap (`mcp-tool-conventions.md` §9). Default to the summary and make the detail opt-in.

### 2.5 Errors the model can act on

**Principle.** MCP has two error channels:
- **Protocol errors** (JSON-RPC errors: unknown tool, malformed request). Models are "less likely to be able to fix" these.
- **Tool execution errors** (`isError: true`). These "contain actionable feedback that language models can use to self-correct and retry" (MCP spec, *Tools* § Error Handling).

The schema says errors that originate in the tool SHOULD be reported inside the result with `isError: true`, "Otherwise, the LLM would not be able to see that an error occurred and self-correct" (MCP schema 2025-11-25, `CallToolResult.isError`). Prompt-engineer error responses so they say what to change (Anthropic, *Writing effective tools*). On a CLI, put the most important information last and suggest the fix (clig.dev, *Errors*).

**Here.**
- Connector servers return the typed-error triple `{error_class, message, status}` (`mcp/_kit/errors.py:18-29`).
- `noctus.dev.*` tools return `{"ok": False, "error": "..."}` dicts (e.g. `scaffold_mcp_tool.py:27`). FastMCP raises `ToolError` for refusals such as unknown arguments.

**Rules.**
- One error shape per server, and the message names the fix. Model it on the keeper messages that end with the remedy command, e.g. `--lower-mutation-invalidate-only-baseline` (`compliance.py:8816`).
- A refusal is never `ok: True`. "Did nothing" and "succeeded" are different results (the `task_branch` incident, §2.2).
- Never return a stack trace as the only content. Return the cause, the input that caused it and the next action.

### 2.6 Idempotency and concurrency

**Principle.** `idempotentHint: true` means repeated calls with the same arguments have no additional effect (MCP schema, `ToolAnnotations`). An agent will retry, and a session will be compacted and resumed mid-call. So every write tool must be safe to call twice.

**Here.**
- Embeddings are content-addressed: re-embedding the same `source_sha` is a no-op at no cost (`vectorize-embed-cache-framework.md` leg 2).
- `lower_mutation_invalidate_only_baseline` only ever lowers (`compliance.py:8763`). Run it twice and you get the same file.
- `toolkit_freshness.capture_baseline` is idempotent unless `force=True` (`toolkit_freshness.py:180`).

**Rules.**
- Writes derive their result from current state ("set to X", "min(baseline, current)"). They never apply a delta ("add 1").
- An append-only ledger write carries a dedup key or tolerates duplicates on read.
- Long sync work is offloaded. FastMCP runs a sync tool **inline on the event loop**, which makes the stdio server deaf for the whole call. `offload_blocking` (`server.py:93`) runs every sync tool in a worker thread. Do not undo it, and do not hold a lock across an `await`.

### 2.7 Annotations: hints, never a boundary

**Principle.** `ToolAnnotations` has `title`, `readOnlyHint` (default false), `destructiveHint` (default true, meaningful only when not read-only), `idempotentHint` (default false) and `openWorldHint` (default true). All are **hints**, "not guaranteed to provide a faithful description of tool behavior". Clients "should never make tool use decisions based on ToolAnnotations received from untrusted servers" (MCP schema 2025-11-25).

**Here.** No `noctus.*` tool declares annotations (grep `annotations=` / `readOnlyHint` under `mcp/noctusai/` → 0 hits). Adding them is cheap UX: clients can auto-approve read-only tools and warn on destructive ones. It must never replace `confirm=` or `refuse_gate`, because a hint is not a gate (`harness-mods.md` § Why).

### 2.8 Security of tools

**Principle.** Servers MUST validate inputs, implement access controls, rate-limit invocations and sanitize outputs (MCP spec, *Tools* § Security Considerations). MCP servers MUST NOT accept tokens that were not issued for them (no token passthrough). For local servers, clients show the exact command, servers run sandboxed, and stdio is preferred (MCP spec 2025-11-25, *Security Best Practices*).

**Here and rules.**
- **No shell strings.** Pass `subprocess.run([...], shell=False)` an argv list, always. Under `mcp/noctusai/tools/` the only `shell=True` match is a keeper's detection text in `compliance.py`, not a call. Keep it that way. A caller's string never reaches a shell, an SQL text or a path join unvalidated.
- **Allowlists, not denylists**, for anything that picks a target: product slugs come from the catalog / `deploy/fleet/active-scope.txt`, cache names from `cache_backend._CACHE_FILES`, umbrella paths from settings.
- **Secrets stay in the environment.** `server.py:44-81` loads `.env` once via `env_bootstrap.load_repo_env` and logs only presence booleans. Never echo a secret in a result: tool results enter transcripts.
- **stdout is the protocol.** Anything printed to stdout corrupts JSON-RPC. Logs go to stderr (`server.py:24-41`), and `stdio_guard.isolate_stdio_channel` isolates the channel (`server.py` `run`).
- **Rate-limit what fans out.** `_vps_ssh` throttles to stay under fail2ban (`server.py:112-114`). Heavy local work goes through `hw_admission` (`hardware-admission-budget.md`).
- Tools that touch prod, consent or money are the tech-lead's or the owner's call: `prod-exposure-consent.md`, `ship-consent-riders.md`.

**Checklist — MCP tool design.** It's in §12.1.

**Anti-patterns.** An `action` parameter whose default is a no-op `ok: true` (the 2026-09-19 incident). Write tools without `worktree_path`. Free-string enums. `shell=True`. Annotations used as a security boundary. Returning 50k tokens "for completeness". Errors that say only "failed".

---

## 3 · CLI design (`cli.py`, the second entrypoint)

**Principle (clig.dev).**
- Human-first design.
- Primary output and machine-readable data go to **stdout**; logs and errors go to **stderr**. Offer `--json`.
- Exit **0 on success, non-zero on failure**, and map distinct codes to the most important failure modes.
- Validate early and print something within about 100 ms.
- Keep changes **additive** and warn before breaking. No catch-all subcommand, no automatic prefix abbreviations.
- Configuration precedence: flags > env > project config > user config > system config.

**Here.**
- `cli.py` is the **dual entrypoint** (`mcp-tool-conventions.md` §6): the MCP tool and the CLI flag share the tool function, not the dispatch map. Hooks and humans use the flag; agents use the tool.
- 395 flags in one argparse parser. The help text is the documentation, and some help strings are full design rationales (`cli.py:307`). That keeps the docs near the code but makes `--help` unreadable. Prefer one sentence + `KB § …` in help, with the rationale in the KB or the module docstring.
- Every keeper is reachable as `--check-<name>`, and every cache as `--refresh-<name>` / `--check-<name>-freshness`.
- `--worktree-path` (`cli.py:498`) rebinds `settings.REPO_ROOT` / `PRODUCTS_DIR` only. `LEDGER_ROOT` is not rebound, and that difference caused the auto-improvement cross-tree bug (`cache-auto-freshness.md` § Cross-tree, instance 2). A new flag that resolves a path states which root it follows.

**Rules.**
- A keeper flag exits non-zero **only** for findings at blocking severity, and prints them. "Could not measure" gets its own exit path and message. It is never red (verdict-channel integrity, `methodology-execution-discipline.md` §6).
- Hooks read the flag's **own** exit code. Never `cmd | tail` and then `$?` (keeper `check_piped_exit_code_pattern`).
- A machine consumer gets `--json` or the MCP tool, never a parse of human prose.

**Anti-patterns.** Exit 0 with "ERROR" printed. Automatic prefix abbreviation: `cli.py:169` builds `argparse.ArgumentParser` without `allow_abbrev=False`, so any unique prefix of a long flag silently binds to it, and a later flag that shares the prefix changes what an old abbreviation means (clig.dev forbids automatic abbreviations). Set `allow_abbrev=False` when you next touch the parser. Breaking a flag name without an alias period (§9).

---

## 4 · Keeper design (static analysis as fitness functions)

**Principle.**
- A **fitness function** "objectively assesses" whether an architectural characteristic still holds, using tests, metrics and monitors (Thoughtworks Radar, *Architectural fitness function*). A keeper is one, run on every commit.
- Google's experience (Sadowski et al., CACM 2018):
  - An **effective false positive** is an issue on which "developers did not take positive action after seeing the issue". Developers, not tool authors, decide what is a false positive.
  - Compiler checks (the analogue of a blocking keeper) must produce **no** effective false positives. Code-review checks may include up to **10 %**. Analyzers whose "Not useful" ratio goes above 10 % are disabled until fixed.
  - Checks must be understandable and actionable, and include a suggested fix when one is possible.
  - Teams that block commits do so with "highly specific custom checks with no false positives".
  - Lessons: "Finding bugs is easy"; "Developer happiness is key".
- Prefer a **lossless CST** (libcst) when you rewrite code. `ast` cannot reprint the original source (*Why LibCST*). `ast.parse` does no scoping checks, and `ast.unparse` output "will not necessarily be equal to the original code" (Python `ast` docs).
- Suppressions are per-code and per-line, and unused suppressions are themselves flagged (Ruff `RUF100`). New rules ship in **preview** first (Ruff, *Contributing* `preview_since`).
- A **ratchet** records the current state so new problems cannot be introduced while the old ones are paid down (Betterer).

### 4.1 Precision over recall, and severity as the false-positive budget

**Here.** House severities are `critical` / `high` (block) and `warning` (surface). `check_all_products` turns them into a score: penalties 25 / 10 / 3 (`compliance.py:18473`). A new keeper starts at `warning` ("Stage-4 calibration: warn first, ratchet later", `compliance.py:3958`) and promotes to `high` once its observed effective false-positive rate is ~0. That is Google's compiler-check bar for anything that blocks a commit.

**Rules.**
- **Blocking ⇒ ~0 effective false positives.** If agents keep adding escape markers or baseline bumps to get past it, it is a wall (`gate-methodology-sync.md` § Walls). Narrow it, fix the mechanism or demote it.
- **Measure, don't predict.** A guard that parses intent turns into an arms race. Prefer measuring the effect (`gate-methodology-sync.md` § Walls, rule 1).
- **Judge the change, not the file.** Write-time guards judge only the added lines (`test_seam_guard`). Pre-existing debt belongs to a ratchet.
- **Unmeasurable is not red.** A keeper whose input is unreadable reports it as unmeasurable, with severity chosen deliberately. Example: `check_mcp_tools_reject_unknown_args` reports an unreadable `server.py` as `high` because the guarantee cannot be verified (`compliance.py:25900-25905`). Pick that on purpose; never fall through silently.

### 4.2 AST first, and the regex exception

**Here.** Python keepers parse with `ast`. `keeper_pattern_cache` itself is populated by pure `ast.walk` (`keeper-pattern-cache.md` § Population), and the code-rewriting tools use libcst / ts-morph (`ast.md`). TS/TSX keepers often scan with regex. `check_mutation_invalidate_only` finds `useMutation({` with a regex and brace-balances the options object, without treating strings specially (`compliance.py:8706-8721`).

**Rule.** Regex over source is acceptable for a **detector** only when the construct is lexically unambiguous and the fixtures pin the edge cases (strings, comments, generics). It is never acceptable for a **rewrite** (`ast.md`). When a regex detector gathers escape markers for "the regex misread it", port it to `tree-sitter` / ts-morph.

### 4.3 Suppression with a reason, and ratchets

**Rules.**
- An escape marker sits on the flagged line, names the rule and carries a reason. Example: `// noc-allow: invalidate-only — why` (`compliance.py:8701`). A marker without a reason is itself a finding. There are no blanket file-level suppressions.
- A ratchet is a committed JSON baseline. A file may carry fewer findings, never more. A lowered count must lower the baseline in the same change, and the derive-down tool is the only writer. Parallel slices that conflict on the baseline take either side and re-derive; they never hand-merge (`compliance.py:8763-8780`).
- Every ratchet names its end state and owner, like a release toggle that gets a removal task the day it is created (Hodgson, *Feature Toggles*). A ratchet with no path to zero is permanent debt dressed up as progress.

### 4.4 Messages are the product

**Rule.** An `issue` string says what was found, where (`file` + line), why it matters in one clause, the exact fix (a command or an API) and the `KB § …` pointer. Model: `compliance.py:8803-8817`. The most important part goes last (clig.dev).

### 4.5 A gate ships its mechanism

**Rule.** House law: `gate-methodology-sync.md`. Ship the keeper together with the code path that makes compliance automatic, backfill the legacy state, and prove the loop (the gate fires on the pre-fix state, then passes). The mechanism for keepers themselves is `scaffold_keeper` (`dev-toolkit-scaffolders.md` §2). It emits the detector + `Test<CamelCase>` + the CLI flag + the pre-commit block, so `check_detector_has_regression_test` (`compliance.py:17919`) rarely fires.

### 4.6 Performance budget

**Rules.**
- A keeper on the commit path scans **staged** or scoped files where it can; the pre-commit hook filters by path first. Example: `STAGED_MIO=$(git diff --cached --name-only | grep -E …)` at `scripts/hooks/pre-commit:996`.
- Whole-tree scans belong to `--validate` / CI.
- Guards on the harness pre-tool path are **stdlib-only**, are imported by path and must fit about 60 ms. Importing `compliance.py` alone costs 0.27 s (`mcp-first-scripts.md` §3, `claude-guard-primary-write.py` row). When the first `test_seam_guard` imported pydantic, it failed open (same table).
- A keeper that shells out per product runs the products in parallel and is scoped to active products (`_active_product_dirs`).

### 4.7 Testing keepers: red and green fixtures

**Rule.** Every detector has a `Test<Detector>` with **both** a true-positive (red) fixture and a near-miss (green) fixture, plus the escape and the scope edges. Model: `tests/test_check_mutation_invalidate_only.py:68-118` has 10 tests:
- the flagged shape;
- the two compliant shapes;
- the seed primitive, which must not be flagged;
- baseline at the limit passes, one more blocks;
- a lowered count must lower the baseline;
- derive-down never raises;
- the escape marker;
- test files out of scope;
- the reported line number;
- the committed baseline equals the tree.

Fixtures live in `tmp_path`, never in the real tree. Never monkeypatch the guard under test (`check_no_self_monkeypatch`, CLAUDE.md §1).

**Checklist — new keeper.** It's in §12.2.

**Anti-patterns.**
- A blocking keeper with a known false-positive class.
- A suppression without a reason.
- A hand-merged baseline.
- A keeper whose message has no fix.
- Shipping the gate without the mechanism.
- A keeper whose only test is the green path, which passes even when the detector matches nothing.
- Regex rewrites.

---

## 5 · Caches (keeper-mirrors and embeddings)

**Principle.**
- A derived cache must be keyed by its source content, refreshed when the source changes, and observable when stale.
- SQLite WAL: "readers do not block writers and a writer does not block readers", but "there can only be one writer at a time". WAL "does not work over a network filesystem", and the `-wal` file must travel with the database (*Write-Ahead Logging*).
- Lock states go UNLOCKED → SHARED → RESERVED → PENDING → EXCLUSIVE (*File Locking And Concurrency In SQLite Version 3*). A contended writer gets `SQLITE_BUSY` unless a busy handler waits. `busy_timeout` sleeps until the given milliseconds have accumulated (`sqlite3_busy_timeout`, `PRAGMA busy_timeout`).
- Python's `sqlite3.connect(timeout=5.0)` is the same wait. `check_same_thread=True` by default, and with it off, writes "may need to be serialized by the user" (Python `sqlite3` docs).

### 5.1 The house cache catalog

`cache_backend._CACHE_FILES` (`cache_backend.py:97-107`) lists 9 caches:
- **4 structural mirrors**: keeper-patterns, agent-context, auto-improvement, absorptions. They are **per-tree** (`_PER_TREE_CACHES`, `cache_backend.py:168`).
- **4 content-addressed embedding caches**: kb, code, memory, corpus. They are **repo-shared** under `<git-common-dir>/noctusai/cache/`.
- **noc-graph**: single-slot but shared, because a rebuild costs about 13 s and its keeper is advisory.

The comment at `cache_backend.py:151-166` is the design rule:
- **Content-addressed rows can share one file across worktrees**: every tree's chunks coexist.
- **A single-slot mirror keyed by one aggregate sha cannot be shared**: it matches only one tree at a time, and a high-severity freshness keeper then blocked every other tree's commits (2026-09-21/22).

### 5.2 Freshness legs — eager, lazy, loud

Every mirror ships three legs (`agent-context-architecture.md` § Agent-context cache; `cache-auto-freshness.md`):

| Leg | Mechanism | Property |
|---|---|---|
| Eager | pre-commit / pre-push / post-merge / post-checkout refresh | catches the common case at the boundary |
| Lazy | `lookup()` compares the stored `source_sha` with the live sha and rebuilds on mismatch | heals where no event fired (fast-forward merges skip `post-merge`) |
| Loud | `check_<cache>_cache_freshness` keeper | the backstop that makes staleness visible |

Structural caches also **heal on contact** (`refresh_all_caches.settle_structural_caches`, `refresh_all_caches.py:373`). Embedding caches stay warn-only, because a rebuild costs OpenAI money and spend is the owner's call (`cache-auto-freshness.md` § Heal-on-contact).

### 5.3 Cross-tree parity (the rule that cost two incidents)

**Rule.** For one call, the freshness **check's live side** and the **refresh's source read** must resolve off the **same tree**. Otherwise the check is structurally unsatisfiable: no number of refreshes can make two different questions agree (`cache-auto-freshness.md` § Cross-tree refresh/check source-parity). Worked example B (§13) walks through the fix. Corollaries:
- Every function that hashes a source takes `repo_root` / `worktree_path`. A module-level path constant is only a default, because it is frozen at the long-lived server's boot CWD.
- The write slot and the read slot come from **one** resolver (`agent_context_cache._cache_file`, `agent_context_cache.py:102-115`).
- The regression test asserts on the **SQLite row** directly, not only on a passing refresh call (`test_agent_context_cache.py:233-335`).

### 5.4 SQLite practice

**Rules.**
- Every connection goes through `cache_backend.apply_locking_pragmas` (`cache_backend.py:71-93`): `journal_mode=WAL` + `busy_timeout=5000` (`CACHE_BUSY_TIMEOUT_MS`, `:68`). A raw `sqlite3.connect` on a read path skips `busy_timeout` and raises `database is locked` under writer contention. The comment at `agent_context_cache.py:492-494` exists because of exactly that.
- Keep write transactions short. Build the rows in memory, then write them in one transaction. Never hold a write transaction across network calls (embeddings).
- Caches live on local disk only. Never put one on a network or synced folder (WAL limitation).
- Copy or back up the database together with its `-wal` file, or checkpoint first.
- Schema changes are `CREATE … IF NOT EXISTS` plus a version key in `cache_meta`. A cache is derived, so the safe migration is "drop and rebuild".
- ⚠️ `apply_locking_pragmas` swallows a failed `journal_mode=WAL` with `except sqlite3.OperationalError: pass` (`cache_backend.py:89-92`). The comment says "tmpfs / readonly fallback — non-fatal". It is deliberate but silent. A fix-on-contact candidate is a `logger.debug` naming the fallback (see the return report).

### 5.5 Cost and telemetry for embedding caches

Every embedding round-trip is cost-logged (`vector-cost-tracking.md`). Calibration thresholds are decided from logged signals, not guessed (`vector-calibration.md`). `cache_telemetry.record` is opt-in and logs hit / miss / latency so cache sizing is evidence-based (`cache_telemetry.py:1-24`). Semantic search **degrades gracefully to empty** when the provider is unreachable (`kb-vector-search.md`). Treat an empty semantic result as "unknown", not "nothing exists", and fall back to grep.

**Checklist — new cache.** It's in §12.3.

**Anti-patterns.**
- A ninth cache without the extend-first decision.
- A single-slot mirror in the shared tier.
- A hash function without a `repo_root`.
- A raw `sqlite3.connect`.
- A long write transaction around an API call.
- Treating an empty vector result as proof of absence.

---

## 6 · Hooks and harness mods

**Principle.**
- Git: `core.hooksPath` relocates hooks. A non-zero pre-commit exit aborts the commit. pre-commit and commit-msg can be bypassed with `--no-verify`. pre-push receives one ref line per ref on stdin, and a non-zero exit aborts the push (*githooks*).
- Claude Code: a PreToolUse hook exiting **2** blocks the tool call, and stderr becomes the message. With exit 2, JSON output cannot override the block. `hookSpecificOutput.permissionDecision` ∈ `allow | deny | ask | defer`. Exit 0 with no output means no decision (Claude Code *Hooks reference*).

**Here.**
- **Git hooks are thin dispatchers** (`[carve:hook]`, `mcp-first-scripts.md` §1). `scripts/hooks/pre-commit` calls `cli.py --<flag>` per step. The logic lives in tested toolkit code.
- **Claude Code guards** are wired in `.claude/settings.json`:
  - PreToolUse: `claude-guard-primary-write.py`, `-test-seams`, `-heavy-run`, `-executor-dispatch`.
  - PostToolUse: `-harness-signature`, `-primary-write-post`.
  - SessionStart: the worktree sweep.

  They import stdlib-only library code by path and **fail closed** through `_guard_failclosed.run_guard`: an exception, an 8 s internal deadline (`DEFAULT_DEADLINE_S`, `_guard_failclosed.py:33`, kept under the 10 s settings timeout) or a malformed payload becomes a `[noc-guard:<name>]` deny. Claude Code itself fails **open** on a crashed hook. That is why the wrapper exists.
- **Harness mods are UX, never a gate** (`harness-mods.md`). The mod observes `[noc-guard:<name>]` markers and renders `cli.py --harness-*` answers. A gate inside a mod could be switched off by a `userConfig` toggle. Keeper `check_harness_mod_integrity` (`compliance.py:6184`) enforces that the mod spawns only `cli.py --harness-*` and that no `userConfig` key names a guard.
- `check_guard_hooks_registered` (`compliance.py:23767`) asserts the guards stay wired in settings.

**Rules.**
- One decision per hook. The decision lives in importable library code that the hook adapter, the keeper and `gate_sweep` share. Example: `harness_signatures.py` is shared by the PostToolUse adapter and `gate_sweep`'s harness-suspect classifier.
- Every deny starts with `[noc-guard:<name>]`, says why and names the remedy.
- A new guard adds its row to `mcp-first-scripts.md` §3 and to `accept-with-rationale.md`, the same commit.
- Never `--no-verify`, and never bypass hooks silently (CLAUDE.md §1).

**Checklist — new hook / guard.** It's in §12.4.

**Anti-patterns.** Logic in the shell hook. A guard importing heavy modules (it fails open). A gate that lives in a mod. A hook that reads `$?` off a pipe. A deny without the marker.

---

## 7 · Telemetry: measuring whether a tool is useful

**Principle.** Measure the platform as a product (CNCF: user satisfaction and productivity, organizational efficiency, delivery). Google's Tricorder computes each analyzer's "Please fix" vs "Not useful" ratio and disables analyzers above 10 % (Sadowski et al.). Evaluate tools with realistic multi-step tasks and held-out sets (Anthropic, *Writing effective tools*).

**Here — the signals that already exist.**

| Question | Signal |
|---|---|
| Is a cache used? | `cache_telemetry` → `project-history/cache-telemetry.ndjson` (opt-in) · `noctus.dev.cache_telemetry_summary` |
| What did a dispatch cost? | `dispatch-token-log.md`, `dispatch-budget-telemetry.md` |
| Which gate is a wall? | auto-improvement rows naming a gate, plus commits that exist only to satisfy one (`gate-methodology-sync.md` § Walls) |
| Did a guard refuse, and was that right? | harness-mod friction ledger (`noctus.dev.harness_event`) |
| What does embedding cost? | `vector-costs.ndjson` · `noctus.dev.vector_costs_report` |
| Do agents use the toolkit at all? | `noctus.dev.usage_eval` (`usage-evaluation.md`) |

**Rules.**
- A keeper's "Not useful" signal is an escape marker, a baseline bump or a `Docs-Reviewed:` trailer that a gate forced. Count them per keeper. A rising count is a precision bug.
- A tool that nobody called in N sessions is a deprecation candidate (§9).
- Telemetry never blocks the tool it measures. It degrades gracefully (`cache_telemetry.py:16-18`).
- Never log secrets or PII in telemetry. Telemetry ledgers are append-only ndjson.

---

## 8 · Testing the toolkit

**Principle.** Test against the real thing wherever a fake can hide the bug. Fakes stay honest only when a contract pins them (`stand_in_conformance`). Codemods are tested as before/after pairs (libcst `CodemodTest.assertCodemod`).

**Here.**
- **Real git against a bare remote.** `conftest.py::ledger_repo` (`tests/conftest.py:137-182`) builds `origin.git` (bare) + a clone + a real `ledgers` branch. `tests/test_ledger_push_realgit.py` exists because a scripted fake runner could not model "git rebase refuses on a dirty tree", and every fake-based test passed for four sessions while the bug was live (`test_ledger_push_realgit.py:1-24`).
- **Safety nets inside the suite.** An autouse fixture makes any test that reaches a real `git push` fail loudly (`conftest.py:216-248`). Another isolates every ledger path per test (`conftest.py:185-213`). Never widen these to make a test pass.
- **No self-monkeypatch.** Patch external services only, never the guard under test. This is gated at write time (`test_seam_guard`) and at commit (`check_no_self_monkeypatch`, `compliance.py:1807`).
- **Scaffolders are tested by parsing what they emit.** A codegen tool that emits non-parsing code is worse than none (`dev-toolkit-scaffolders.md` § Quality gate).
- Heavy suites run through `hw_admission` (engineer-seed §2). The toolkit suite is `mcp/noctusai/tests/` (395 files).

**Rules.**
- Every bug fix ships a test that failed before the fix.
- A test for a cross-tree or stale-process bug runs two trees or two processes. A single-tree test cannot see the bug.
- Tests that need the network are marked and skipped with a reason. They never silently pass.

---

## 9 · Deprecation and aliases

**Principle.** Keep changes additive. Warn before a breaking change, and avoid time bombs (clig.dev, *Future-proofing*). Treat toggles and aliases as inventory: keep the count low, and attach a removal task when you create one (Hodgson, *Feature Toggles*).

**Here.** The house retired the `noctusai_<x>` flat aliases on 2026-05-03 after migrating every consumer surface (`mcp-tool-conventions.md` §1, Backward-compat aliases). The server's own `instructions` string still advertises them (`server.py:268`). Drift: the description is part of the product (§1).

**Rules.**
- To rename a tool: register the new name, keep the old one as an alias that returns a deprecation note, migrate every consumer (KB, skills, agent files, tests, hooks), then remove the alias. Each step is its own commit, and the alias carries a named removal destination (`NOC-REMEDIATE[...]`, `remediation-markers.md`).
- Grep the consumers before you remove anything. `check_doc_tool_reference_drift` is the net.
- A deprecated keeper is deleted together with its test and its pre-commit block, never left as dead code that always returns `[]`.

---

## 10 · Performance

**Rules.**
- **Import time is UX.** Umbrellas import children lazily inside `register_all` (`tools/__init__.py:1-21`). Heavy dependencies load inside the function, not at module top.
- **Never block the event loop.** Sync tools are offloaded (`offload_blocking`, `server.py:93`). An `async def` tool that calls sync IO is worse than a `def` tool.
- **TTL-cache cheap checks.** `toolkit_freshness.check` stats every loaded file, cached for 5 s (`toolkit_freshness.py:256`), so a burst of calls costs one pass.
- **Scope before you scan** (§4.6). Scope `gate_sweep` from the diff (`gate_sweep.py:1-50`). Don't scan the fleet.
- Budgets come from measurement: `hardware-budget.json` profiles, cache rebuild times quoted in comments (`cache_backend.py:164-166`). Re-measure before you tighten.

---

## 11 · Anti-patterns (the whole canon on one list)

1. A tool per incident, never consolidated. A cache per question.
2. A mutating default, or an ignored argument that turns a failure into `ok: true`.
3. A tool that resolves paths off the server's boot CWD (no `worktree_path`).
4. Output that floods the context. Errors without a fix.
5. Annotations or a mod used as a gate.
6. `shell=True`, string-built SQL, unvalidated path joins.
7. A blocking keeper with a known false-positive class. A suppression without a reason. A hand-merged baseline.
8. A gate without its mechanism (`gate-methodology-sync.md`).
9. A regex rewrite of source.
10. A single-slot cache in the shared tier. A hash without `repo_root`. A raw `sqlite3.connect`.
11. Logic inside a shell hook. A heavy import in a pre-tool guard.
12. A fake-only test of git, subprocess or SQLite behaviour.
13. Removing a name without an alias period. Stale descriptions.
14. Unmeasurable reported as red, or not-run reported as green.

---

## 12 · Checklists

### 12.1 New MCP tool
- [ ] Searched for an existing tool or module (`__init__.py`, deferred list, `kb_search`). Extend before you add.
- [ ] Name `noctus.dev.<intent_noun_verb>`; description = first sentence states WHEN to call it, then inputs, outputs, failure modes, `KB § …`.
- [ ] Inputs: typed, `Literal` enums, safe default action, `worktree_path` if tree-dependent, validated paths/ids.
- [ ] Writes: `confirm=False` default ⇒ plan; `True` ⇒ act + audit line; `refuse_gate` if a stale answer could look right.
- [ ] Output: concise default, detail opt-in, enumerated status, under the 25k-token cap; `XxxOutput` model (consider `structured_output=True`).
- [ ] Errors: `ok: False` + cause + fix; never `ok: True` on no-op.
- [ ] Idempotent on retry; long sync work tolerated by `offload_blocking`.
- [ ] `register(server)` + import in `tools/noctus/dev/__init__.py` + `cli.py --<flag>` sharing the function.
- [ ] `Test<CamelCase>`: happy path, refusal, unknown-arg rejection, worktree resolution.
- [ ] KB doc / pointer + INDEX row the same commit; `/mcp` reconnect after merge (the running server is stale until restarted, `toolkit_freshness.py:1-30`).

### 12.2 New keeper
- [ ] `noctus.dev.keeper_pattern_lookup` first. Is the rule already a keeper?
- [ ] `scaffold_keeper(name, flag, severity="warning")` emits the detector, test, CLI flag and pre-commit block.
- [ ] AST for Python, a parser for TS where possible. Regex only for lexically unambiguous detection, pinned by fixtures.
- [ ] Scope: staged / active products / declared roots. Measured runtime on the commit path.
- [ ] Message: what, where, why, exact fix, `KB § …`.
- [ ] Escape marker with a reason, or a ratchet baseline with a derive-down tool and a named end state.
- [ ] Red + green + edge fixtures in `tmp_path`. Never patch the guard itself.
- [ ] The mechanism in the producing code path, the backfill, and the loop proved (`gate-methodology-sync.md` § How to apply).
- [ ] Wired into `check_all_products` (global or per-product), plus `--validate` and pre-commit.
- [ ] Promote `warning` → `high` only after an observed false-positive rate of ~0.

### 12.3 New cache
- [ ] Extend-first decision written down (`vectorize-embed-cache-framework.md` leg 1).
- [ ] Registered in `_CACHE_FILES`. Per-tree if single-slot, shared if content-addressed.
- [ ] `source_sha` per row or bundle. Hash and slot both resolve off the caller's tree.
- [ ] `_connect` → `apply_locking_pragmas`. Short write transactions.
- [ ] 3 legs: eager hook refresh, lazy sha-mismatch rebuild, loud freshness keeper (severity matches cost).
- [ ] Added to `refresh_all_caches` / `settle_structural_caches` if structural. Cost-logged if embedding.
- [ ] Cross-tree regression test asserting the SQLite row.

### 12.4 New hook / guard
- [ ] Is it really a gate (an expensive silent breakage)? Otherwise it is UX for the mod.
- [ ] The logic goes in stdlib-only library code, shared with the keeper. The adapter goes in `scripts/hooks/`.
- [ ] Fail closed via `_guard_failclosed.run_guard`. The deadline stays under the settings timeout.
- [ ] Deny text starts with `[noc-guard:<name>]` and includes the remedy.
- [ ] Wired in `.claude/settings.json`. `check_guard_hooks_registered` covers it.
- [ ] Rows in `mcp-first-scripts.md` §3 and `accept-with-rationale.md`.
- [ ] Measured per-call latency.

---

## 13 · Worked examples (from this codebase)

### A · A ratchet keeper: `check_mutation_invalidate_only`

**The rule.** A TanStack `useMutation({...})` that neither draws optimistically (`onMutate`) nor writes the server's answer (`setQueryData`) makes the screen wait for the write and a refetch. On the day the rule was written, 982 of the fleet's 1 049 blocks had that shape (`compliance.py:8690`). A blocking keeper would have gone red on day one. A warning nobody acts on would have changed nothing.

**The shape.**
1. **Detector** `mutation_invalidate_only_hits` (`compliance.py:8724`): a regex finds the call, a brace-balancer extracts the options object, and an escape marker on the line skips it (`:8730`).
2. **Ratchet** `check_mutation_invalidate_only` (`compliance.py:8782`):
   - It counts per file and compares with `mcp/noctusai/tests/mutation_invalidate_only_baseline.json`.
   - **more ⇒ block**: the message gives the line numbers and the API to use.
   - **fewer ⇒ also block**, until the baseline is lowered.

   So the baseline always equals the truth, and progress cannot be silently given back.
3. **Mechanism.** The seed primitive `useCacheWriteMutation` makes the compliant path the easy one (`gate-methodology-sync.md`). `lower_mutation_invalidate_only_baseline` (`compliance.py:8763`) is the only baseline writer. It derives `min(baseline, current)` and never raises, which is how parallel slices resolve a baseline conflict. CLI: `--lower-mutation-invalidate-only-baseline` (`cli.py:297`, dispatch `:2452`).
4. **Wiring.** Registered in `check_all_products` (`compliance.py:18729`). The pre-commit gate filters staged TS/TSX + the baseline first (`scripts/hooks/pre-commit:993-1001`).
5. **Tests.** Ten tests, red and green (`tests/test_check_mutation_invalidate_only.py:68-118`), including "the committed baseline matches the tree".

**What a tooling engineer improves next.**
- The detector is regex over TSX and does not skip strings or comments (`compliance.py:8710`). If escape markers keep appearing for misreads, port it to a TS parser.
- The baseline has no named end state. Give it one, plus an owner.

### B · The agent-context cache cross-tree parity fix

**Symptom (2026-09-17).** From inside a worktree, `check_agent_context_cache_freshness` stayed stale no matter how often `noctus.dev.agent_context_refresh(worktree_path=W)` ran.

**Root cause.** The refresh's write side was correct: it wrote `cache_meta['bundle_sha:<agent>']` from `W`'s files. The check's live side called `get_bundle_sha(agent)`, which had **no** `repo_root` parameter. It always hashed the module-level `AGENTS_DIR`, which was frozen at the long-running MCP server's boot CWD (the primary checkout). Two different trees were compared forever. `lookup()` had the same gap on its self-heal path and would **overwrite** a correct scoped write.

**Fix** (`agent_context_cache.py`):
- `get_bundle_sha(agent_name, repo_root=None)` (`:457`) hashes `repo_root`'s agents and KB when one is given (`:486-487`).
- It reads the cached value from the **same** tree's slot through `_cache_file(repo_root=…)` (`:491`).
- `_cache_file` (`:102-115`) is the single resolver for write and read.
- `_connect` (`:118-125`) always applies the locking pragmas, so the read path cannot hit `database is locked` (`:492-494`).

**Regression test.** `TestScopedRefreshCrossTreeParity` (`tests/test_agent_context_cache.py:233`) asserts the SQLite row directly (`:261`). It checks that `get_bundle_sha` agrees after a scoped refresh (`:288`), that the default path is unchanged (`:316`) and that `lookup(worktree_path=…)` does not clobber (`:332`).

**Generalisation.**
- `cache-auto-freshness.md` § Cross-tree records a second instance with a different cause: `LEDGER_ROOT` not rebound by `--worktree-path`.
- `cache_backend._PER_TREE_CACHES` (`cache_backend.py:168`) moved single-slot mirrors out of the shared tier.

The canon rule (§5.3) is the result. Note the profession's term: this is a **cache key that omitted part of the input**. The key was `(agent)`, but the content depended on `(agent, tree)`.

### C · A `noctus.dev.*` tool end to end: `gate_sweep`

1. **Design intent in the module docstring.** Two incidents: a claimed green over a suite never run, and `$?` read off `tail` (`gate_sweep.py:1-26`). The tool turns both into structure. The gate set is **derived** from the diff, every gate runs as its own subprocess, and its own return code is read directly.
2. **Output contract.** `_verdict` (`gate_sweep.py:2039-2071`) is an enumerated status with an explicit precedence: `red` > `inconclusive` > `incomplete` > `green`. A timed-out gate, or one that never got a hardware slot, is unmeasured, never red or green. This is §2.4 and §4.1 made concrete.
3. **Registration.** `register(server)` (`gate_sweep.py:2260`) declares `name="noctus.dev.gate_sweep"` and a description that states when to call it, what it derives, every status and the `worktree_path` semantics. The parameters are typed with safe defaults (`base_ref="origin/dev"`, `allow_stale_tree=False`). It is imported and registered in `tools/noctus/dev/__init__.py:65,225`.
4. **Server wrapping, applied uniformly by `build_server`** (`server.py:262-298`):
   - `structured_output=False` default (`:285`);
   - `offload_blocking`: the sweep runs for minutes in a worker thread, so stdio stays responsive;
   - `install_strict_tool_arguments`: a typo such as `base=` is refused, not ignored.
5. **Staleness.** `toolkit_freshness.capture_baseline()` runs last in `register_all` (`tools/__init__.py:41-48`). After any edit to `gate_sweep.py`, the running server answers with old code until `/mcp` reconnects. `warn_gate` / `refuse_gate` exist for tools where that matters.
6. **Tests.** `test_gate_sweep.py`, `test_gate_sweep_isolated_rerun.py`, `test_gate_sweep_load_timeouts.py`.
7. **Gap to know.** `gate_sweep` has **no** `cli.py --gate-sweep` flag (grep `cli.py`), so it is MCP-only, against the dual-entrypoint convention (`mcp-tool-conventions.md` §6). A hook cannot call it directly. Decide per tool and record the decision.

**What `scaffold_mcp_tool` gives you, and what it doesn't.** `noctus.dev.scaffold_mcp_tool` (`scaffold_mcp_tool.py:15-116`) emits a **connector-server** leaf: `mcp.server.Server` + `HANDLERS` + `tool_descriptors()` + Pydantic In/Out + the `confirm` gate + an audit logger + the `_kit.errors.typed_error` shape. It is placed at `mcp/<vendor>/tools/<service>.py` and added to `LEAF_MODULES` (`:115`). A `noctus.dev.*` FastMCP tool uses the `register(server)` + `@server.tool(...)` shape shown above instead. So for a dev tool, copy a recent sibling (like `gate_sweep`), not the scaffolder output, until a dev-tool scaffold exists. That is a scaffolder gap worth closing (gate↔mechanism: `mcp-first-scripts.md` §2 points dev tools at `scaffold_mcp_tool`).

---

## Sources

All URLs below were fetched and confirmed on 2026-11-05 for this doc. Where only part of a source could be read, the entry says so.

- Model Context Protocol, *Tools* (spec 2026-07-28, current version per the versioning page) — https://modelcontextprotocol.io/specification/2026-07-28/server/tools — tool name rules + disambiguation; `inputSchema` requirements; `outputSchema` / `structuredContent` + text fallback; protocol vs tool-execution errors; annotations untrusted; servers MUST validate / access-control / rate-limit / sanitize; human in the loop (§2.1-2.5, §2.8).
- Model Context Protocol, *Versioning* — https://modelcontextprotocol.io/specification/versioning — current protocol version 2026-07-28 (§2).
- Model Context Protocol, *Schema Reference* (2025-11-25) — https://modelcontextprotocol.io/specification/2025-11-25/schema — `ToolAnnotations` fields, defaults and "hints … never make tool use decisions … from untrusted servers"; `CallToolResult.isError` guidance (§2.5, §2.6, §2.7).
- Model Context Protocol, *Security Best Practices* (2025-11-25) — https://modelcontextprotocol.io/specification/2025-11-25/basic/security_best_practices — token passthrough forbidden; confused deputy; session hijacking; local server compromise (show exact command, sandbox, prefer stdio); scope minimization (§2.8).
- Anthropic, *Writing effective tools for agents — with agents* (K. Aizawa, 2025-09-11) — https://www.anthropic.com/engineering/writing-tools-for-agents — fewer consolidated tools; namespacing; high-signal output, `response_format`; 25 000-token default cap in Claude Code; actionable errors; descriptions for a new hire; evaluations (§1, §2.1, §2.4, §2.5, §7).
- Anthropic, *Building effective agents* — https://www.anthropic.com/engineering/building-effective-agents — agent-computer interface; "Poka-yoke your tools"; absolute paths fixed SWE-bench errors (§2.2).
- *Command Line Interface Guidelines* — https://clig.dev/ — stdout vs stderr, `--json`, exit codes; errors with fixes; `--dry-run` / `--force` / `--confirm`; robustness; future-proofing (no catch-all subcommand, no abbreviations, additive changes); config precedence (§2.3, §2.5, §3, §9).
- Martin Fowler, *Team Topologies* (bliki, 2023-07-25) — https://martinfowler.com/bliki/TeamTopologies.html — a platform's primary benefit is reduced cognitive load for stream-aligned teams; a thin layer for small organizations (§1).
- Team Topologies, *What is a Thinnest Viable Platform (TVP)?* — https://teamtopologies.com/key-concepts-content/what-is-a-thinnest-viable-platform-tvp — smallest platform that meets needs, never thicker than necessary (§1).
- CNCF TAG App Delivery, *Platforms White Paper* — https://tag-app-delivery.cncf.io/whitepapers/platforms/ — platform attributes (product, UX, docs + golden paths, self-service, reduced cognitive load, optional + composable, secure by default); measuring success (§1, §7).
- LibCST, *Why LibCST* — https://libcst.readthedocs.io/en/latest/why_libcst.html — the AST is lossy, the CST reprints exactly (§4).
- LibCST, *Working With Codemods* — https://libcst.readthedocs.io/en/latest/codemods_tutorial.html — `VisitorBasedCodemodCommand`; `CodemodTest.assertCodemod` before/after testing (§8).
- Python docs, *ast — Abstract Syntax Trees* — https://docs.python.org/3/library/ast.html — `parse` does no scoping checks; `NodeVisitor`; `unparse` not equal to the original (§4).
- Ruff, *The Ruff Linter* — https://docs.astral.sh/ruff/linter/ — per-code `noqa`; `RUF100` unused suppressions; safe vs unsafe fixes; preview (§4, §4.3).
- Ruff, *Contributing* § Adding a new lint rule — https://docs.astral.sh/ruff/contributing/ — propose first; tests; `preview_since` (§4).
- SQLite, *Write-Ahead Logging* — https://www.sqlite.org/wal.html — readers ↔ writers non-blocking; one writer; checkpoint; not over network filesystems; keep `-wal` with the db (§5, §5.4).
- SQLite, *File Locking And Concurrency In SQLite Version 3* — https://www.sqlite.org/lockingv3.html — the five lock states (§5).
- SQLite, *Set A Busy Timeout* — https://www.sqlite.org/c3ref/busy_timeout.html — busy-wait until timeout, then `SQLITE_BUSY` (§5).
- SQLite, *PRAGMA busy_timeout* — https://www.sqlite.org/pragma.html#pragma_busy_timeout — the pragma form (§5.4).
- Python docs, *sqlite3* — https://docs.python.org/3/library/sqlite3.html — `timeout=5.0` default; `check_same_thread` (§5).
- C. Sadowski, E. Aftandilian, A. Eagle, L. Miller-Cushon, C. Jaspan, *Lessons from Building Static Analysis Tools at Google*, CACM 61(4), 2018 — https://research.google/pubs/lessons-from-building-static-analysis-tools-at-google/ (full text: https://storage.googleapis.com/gweb-research2023-media/pubtools/4365.pdf) — effective false positive definition; compiler checks "no effective false positives", code-review checks under 10 %; "Please fix" / "Not useful" ratio with disable above 10 %; suggested fixes; commit-blocking only for checks with no false positives; "Finding bugs is easy"; "Developer happiness is key" (§4, §4.1, §7).
- Thoughtworks Technology Radar, *Architectural fitness function* — https://www.thoughtworks.com/radar/techniques/architectural-fitness-function — definition (objective assessment via tests, metrics, monitors) (§4).
- Pete Hodgson, *Feature Toggles (aka Feature Flags)*, martinfowler.com — https://martinfowler.com/articles/feature-toggles.html — toggles as inventory; a removal task at creation; expiry (§4.3, §9).
- Betterer, *Improve, incrementally* — https://phenomnomnominal.github.io/betterer/ — the ratchet: record the current state, block new problems, track progress (§4, §4.3).
- Git, *githooks* — https://git-scm.com/docs/githooks — `core.hooksPath`; pre-commit / commit-msg bypassable with `--no-verify`; pre-push stdin + abort (§6).
- Claude Code, *Hooks reference* — https://code.claude.com/docs/en/hooks — exit 2 blocks PreToolUse; JSON cannot override exit 2; `permissionDecision` values; exit 0 = no decision (§6).
