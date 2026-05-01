# 06 — MCP Dev Toolkit

> Platform development tools exposed as an MCP server at `mcp/noctusai/`.
> Tool count is derived from `_tool(` invocations in `mcp/noctusai/server.py::list_tools()`.

## Tools

<!-- kb-counts:start:mcp_tools -->
**47 tools total** (auto-counted from `mcp/noctusai/server.py`).
<!-- kb-counts:end:mcp_tools -->

### Context
- noctusai_agent_context — full platform overview
- noctusai_product_context — product structure + docs

### Products
- noctusai_list_products, noctusai_get_product, noctusai_platform_metrics

### Scaffold
- noctusai_scaffold_product, noctusai_available_ports

### Compliance
- noctusai_validate, noctusai_validate_product
- **Detectors in `tools/compliance.py`** (deterministic, zero-AI):
  - `check_seed_compliance` — verifies `create_product_app()` usage, `-e seed/backend/*` in requirements, no boilerplate routers, `createProductApp/Layout` on frontend. **Tuned by the control-plane classification set `CONTROL_PLANE_PRODUCTS = {"core"}`**: control-plane products legitimately OWN `team` / `notifications` / custom `Layout` (they ARE the identity/team authority), so the "has own team.py / Layout.tsx" warnings are suppressed for them. Consumer products still get flagged. Introduced 2026-04-23 (originating project archived after close) (fold of `keeper-control-plane-classification` backlog).
  - `check_path_references` — catches stale `shared/*` paths that should be `seed/*`.
  - `check_standard_routers_audit` — cross-audits a product's `standard_routers=[...]` opt-in list against real frontend consumption via a curated signal map (`NotificationBell` → `notificacoes`, `/api/team` → `team`, `useLLM*` → `llm`). Flags under-grant (frontend uses → backend opts out → runtime 404s) at `critical` severity; over-grant (backend opts in → no frontend signal → dead router) at `warning`. **Self-provision v2**: AST-parses the `routers=[<mod>.router, ...]` kwarg in `main.py` to detect what the product actually wires, not what files exist in `routers/`. A `team.py` file that isn't wired no longer counts as self-provision — the frontend would still 404. Falls back to filename-based detection when the kwarg is unparseable (variable reference, dynamic). Introduced 2026-04-22; v2 AST upgrade 2026-04-23 (originating projects archived after close).
  - `check_frontend_entrypoint` — verifies the product's frontend actually CALLS `createProductApp(...)`. Two valid shapes: (a) `main.tsx` calls it directly (core pattern); (b) `main.tsx` delegates to `./App.tsx` whose default export calls it (therapy pattern). Rendering a raw `<BrowserRouter>` / `<QueryClientProvider>` tree without routing through the framework is flagged `critical` — the Suspense, error boundary, routing, providers, and auth paths are bypassed. Closes the gap where the App.tsx-scoped check in `check_seed_compliance` never fired on core (core has no App.tsx). Introduced 2026-04-23 (originating project archived after close).
  - `check_out_of_contract_trees` — global repo-root sweep (not per-product). Scans the repo root for directories that look like product trees (have `backend/app/main.py` OR `frontend/src/main.tsx`) but live outside `products/*/`. Excludes known platform dirs (`seed/`, `templates/`, `mcp/`, `KNOWLEDGE-BASE/`, `projects/`, `scripts/`, `venv/`, `.*`). Flags `critical` with a remediation pointer to either migrate to `products/<name>/` via a `<name>-seed-wiring` project or delete if legacy. Guards against future `/adconnect/`-style stray trees. Introduced 2026-04-23 (originating project archived after close).
  - `check_phase_state_consistency` — global walk (not per-product) over every `PROJECT.md` across `projects/`, `products/*/projects/`, `core/projects/`. Flags four §6 ↔ §11 drift classes: (1) §11 says shipped but §6 header lacks `✅`; (2) header has `✅` but sub-tasks remain `- [ ]`; (3) header has `✅` but no `**Improvements:**` block; (4) §11 says shipped + §6 has both unflipped header AND unticked sub-tasks (the dashboard-lying case). Severity `high`. `⏳`/`❌`/`🅿️` icons recognized as legitimate non-shipped states. Also exposed as `python mcp/noctusai/cli.py --check-phase-state` (exit 1 on mismatch); pre-commit hook runs it ONLY when `**/PROJECT.md` is staged. Introduced 2026-04-28 by `keeper-phase-state-consistency-detector` (folder deleted per clean-folder rule). Closes the slip pattern where agents wrote rich §11 entries but forgot to flip §6 checkboxes — documentation alone wasn't sufficient (caught 5+ times in two days); deterministic enforcement now blocks the slip from shipping.
  - `check_no_self_monkeypatch` — AST-walks test files, flags `monkeypatch.setattr(<our_module>, ...)` and `unittest.mock.patch.object(<our_module>, ...)` patterns that neuter our own logic instead of testing it. Resolves local-bound names against the file's import map (so `from app.services import ai_pipeline` + `monkeypatch.setattr(ai_pipeline, "require", ...)` resolves to `app.services.ai_pipeline.require` for classification). Allowlists boundary accessors (`get_client`, `chat_completion`, audit `log_action`, `resolve_credential`/`check_required_credentials`, env-config getters, JWT `__from_token__`) + suffix patterns `_get_<x>_token` / `_get_<x>_client` / `_get_<x>_config` via `_BOUNDARY_ACCESSOR_REGEXES` + external libs re-exported through our modules (`httpx.AsyncClient` via `app.routers.X`) + inline `# self-patch-ok: <reason>` comments. Severity `warning` (so legitimate-historical patterns don't tank the score; user tightens over time). Introduced 2026-04-28 by `mcp-tooling-expansion`; allowlist extended 2026-04-28 by `keeper-warning-triage` after first-run surfaced 420 hits across 7 products (the 105 boundary-helper hits collapsed at allowlist time). Per memory `feedback_no_monkeypatching_in_tests.md` + CLAUDE.md "No workarounds — and no monkey-patching, in production OR tests".
  - `check_silent_errors` — AST-walks production Python (excludes tests + migrations + vendored deps), flags `try / except:` handlers whose body neither raises, logs, nor surfaces the error in any way. Specifically catches `except: pass`, `except Exception: return None`, and similar swallow patterns. **No `# silent-ok` escape hatch** — retired 2026-04-28 per user directive ("i dont want any silent-ok sign accross the platform"). Every handler MUST log via `logger.<level>(...)`, `raise`, or surface via a return value. Bootstrap-time code (e.g. `noctusai_seed._version` resolving the SHA before `configure_logging` runs) uses `logger.debug(...)` — root logger drops debug by default but the call is in the code, the detector recognizes it, and `NOCTUSAI_DEBUG=1` reveals it during troubleshooting. Severity `warning`. Introduced 2026-04-28 by `mcp-tooling-expansion`; escape hatch retired same day by `platform-logging-standardization`. Per memory `feedback_no_silent_errors.md` + `feedback_silent_ok_is_not_a_substitute_for_logging.md` + CLAUDE.md "No silent errors — always explicit fix opportunities".
  - `check_clean_folder_violations` — walks every PROJECT.md, flags ✅-closed projects whose folders still exist (the apply-inline-then-delete + clean-folder rule violation). Parses the **leading** status icon only — narrative like `📋 READY TO RESUME ... Phase 0 ✅ executed` is not a closed-project signal (false-positive caught + fixed 2026-04-28 against `repo-state-consolidation`). Distinguishes mixed-status states (`✅` leading but `⏳`/`❌`/`🅿️` also present — transitional close) from pure ✅. Severity `warning`. Introduced 2026-04-28 by `mcp-tooling-expansion`; leading-icon refinement 2026-04-28 by `keeper-warning-triage`. Per CLAUDE.md "Clean folder — every artifact has a home".
  - `check_detector_has_regression_test` — meta-detector enforcing the platform-wide testing methodology: every other `check_*` keeper detector MUST ship colocated with a regression test. Self-parses `mcp/noctusai/tools/compliance.py` to enumerate all `check_*` functions, then verifies each has a matching `Test<CamelCase>` class somewhere under `mcp/noctusai/tests/` (case-insensitive matcher accepts `TestCheckSilentErrors`, `TestSilentErrors`, and acronym-preserving forms like `TestAIFeatureCompleteness`). Detectors whose tests live under non-matching names register an explicit override in `_DETECTOR_TEST_OVERRIDES`. Severity `high` — a missing detector test is the kind of gap that lets a real-world miss ship without being noticed. Introduced 2026-04-29 by `platform-logging-standardization` Phase 6 (user directive: regression-test-the-detector becomes platform-wide methodology, integrated into the code validation system). Convention + worked examples at `KB § PATTERNS/testing.md § Regression-test-the-detector`.

### Review (observation-only — never modifies code)
- noctusai_review — detect seed-compliance issues + surface them for authoring. Three modes:
  - `mode=agent` (default): returns the issue list + a review prompt the in-session agent uses. The agent fills `templates/PROPOSAL-TEMPLATE.md` per issue using session context and files via `noctusai_file_proposal`. Zero LLM cost at this layer.
  - `mode=headless`: OpenAI `gpt-4o-mini` authors proposals (for CI / cron / solo CLI without an agent).
  - `mode=evaluate`: writes OpenAI + agent proposals side-by-side to `products/<product>/proposals/evaluations/<ts>/` for comparison.
  - Replaces the retired `noctusai_heal`. See `KNOWLEDGE-BASE/CONTEXT/PATTERNS/proposals-and-improvements.md` for the full protocol (two capture triggers, phase → proposal flow, promote boundary).
- noctusai_proposal_template — return `templates/PROPOSAL-TEMPLATE.md` content so agents get a consistent starting point.
- noctusai_file_proposal — write a filled-template proposal to `products/<product>/proposals/` (keeper, via `product=`) or `projects/<slug>/proposals/` (project-phase, via `project=`).

### Analyzers
- noctusai_analyze, noctusai_analyze_patterns, noctusai_analyze_deps, noctusai_analyze_tests

### AI
- noctusai_ai_discover, noctusai_ai_advisory

### Master Prompts
- noctusai_sync_master_prompt, noctusai_sync_all_master_prompts, noctusai_check_master_prompt

### Testing
- noctusai_run_tests, noctusai_run_all_tests, noctusai_build_frontend, noctusai_build_all_frontends

### Diff & Quality
- noctusai_diff_against_seed, noctusai_find_orphans, noctusai_check_api_consistency

### Proposals
- noctusai_list_proposals, noctusai_accept_proposal, noctusai_reject_proposal

### Cross-cutting utilities (added 2026-04-28 by `mcp-tooling-expansion`)
- **`noctusai_refs <pattern>`** — recursive reference finder across CLAUDE.md / KB / projects / mcp / seed / products. Replaces the manual `grep -rln` ritual run before deletes / renames / closures. Excludes vendored deps + binaries. Used 8× during the 2026-04-28 closed-folder cleanup; tool absorbs the pattern.
- **`noctusai_build_parallel`** — parallel cross-product `vite build` sweep. Supersedes the legacy sequential `noctusai_build_all_frontends`. Combine with `changed_only=True` to scope to git-changed products only (perf — skips unchanged products). 4-worker default; configurable.
- **`noctusai_status`** — cross-project state digest. Walks every PROJECT.md across the three valid locations + emits status / sub-task progress / last-updated / `⏳`-`✅` icon / §3a presence / phase-state-detector flags. Sorted: executing → ready → parked → blocked → shipped (audit history at the bottom).
- **`noctusai_check_three_way_sync`** — verify KB ↔ CLAUDE.md ↔ memory parity. Closes the gap that `verify-kb-sync.sh` cannot cover (memory dir lives outside the repo at `~/.claude/.../memory/`). Reports missing index entries, dangling links, missing KB anchors, and CLAUDE.md keyword mismatches per the three-way-sync rule (`KB § 01-PHILOSOPHY § Docs stay in sync`).
- **Absorption-search sextet (use whenever working in product code — the user's standing directive 2026-04-28):**

  | Scan | What it catches | First-run calibration (2026-04-28) |
  |---|---|---|
  | **`noctusai_scan_recurrence`** | Verbatim LINES recurring in `main.py` / `main.tsx` / `App.tsx` / `conftest.py` / `vitest.config.ts`. Allowlists `from noctusai_seed` / `from @noctusai/...` (inheritance, not replication). | 216 findings, 68 high. Signal MODERATE — most hits are platform-standard inheritance markers. Use only for explicit replication cases (mount-line, fixture). |
  | **`noctusai_scan_cross_product_helpers`** | Function/class NAMES recurring across N≥2 products in services/routers/dependencies/hooks/components. Suggests seed-lib target per name shape. | 75 findings, **14 high (all real)**: digest pipeline (5 products: `_render_bodies` / `_generate_narrative` / `_aggregate` / `_fetch_window` / `_empty_output`), Metas gamification CRUD + hooks (3 products), `login` / `list_invoices`. **HIGH-SIGNAL — primary scan.** |
  | **`noctusai_scan_service_line_recurrence`** | Verbatim LINES in service/router files with strict filters (≥60 chars + has `(`). Catches `datetime.fromisoformat(s.replace("Z", "+00:00"))`, HTTPException Portuguese-error patterns, pagination expressions. | 52 findings, **9 high** including `_TEMPLATE_DIR` (5 products), pagination shape (4 products). HIGH-SIGNAL. |
  | **`noctusai_scan_block_patterns`** *(closed gap #1, 2026-04-28)* | AST-walks `try/except` blocks; normalizes identifiers; hashes structural fingerprint. Catches multi-line block recurrence the line/name scans miss — `try: from app.services import audit_service / await audit_service.log(...) except: logger.warning(...)` × 7 in one product. Suggests `safely_log_action`/`safely_dispatch`/`safely_run` helpers per body shape. | 241 findings, 28 high. Top hit: 7× `audit_service.log` block in core. **HIGH-SIGNAL for the within-core best-effort patterns.** |
  | **`noctusai_scan_within_product_helpers`** *(closed gap #2, 2026-04-28)* | Helper names duplicated N≥3 files INSIDE one product. Closes the gap that cross-product scans require N≥2 distinct products. Suggests `app/utils.py` (product-scope) or `noctusai_lib.<area>` (cross-cutting). | 12 findings, 3 high: `get_resumo` × 6 in ERP, `_get_service` × 5 in mailing, `_get_platform_setting` × 5 in therapy. |
  | **`noctusai_scan_pydantic_model_shapes`** *(closed gap #3, 2026-04-28)* | Pydantic `BaseModel` field-set recurrence across products (different class names, identical field set + types). Suggests `noctusai_lib.schemas.<canonical>`. | 1 finding (`LoginRequest`/`LoginInput` 2 fields). LOW-VOLUME — Pydantic schemas are mostly product-bound by design. |
  | **`noctusai_scan_test_fixture_recurrence`** *(closed second-wave gap #4, 2026-04-28)* | pytest fixtures + helpers across `tests/conftest.py` + `tests/services/` + `tests/routers/` + `tests/integration/`. Stricter blacklist than production helper scan (excludes `test_*` methods + ALL_CAPS sample-data names). Suggests `noctusai_lib.testing.<helper>`. | 88 findings, **17 high**: `pytest_configure` × 8 products, `_fake_build`/`_fake_fetch` × 4, `Stateful*` mock infrastructure × 2 (ERP + PF). |
  | **`noctusai_scan_migration_patterns`** *(closed second-wave gap #3, 2026-04-28)* | Regex-probes 5 known SQL pattern shapes (RLS subquery `auth.uid()`, FK-with-index, `SET search_path`, audit-log trigger, `updated_at` trigger) across product migrations. Reports per-product occurrence counts. | 3 findings, **2 high**: `search_path_lock` × 5 products / **176 occurrences** (huge template recurrence), `updated_at_trigger` × 4 products / 42 occurrences. |

  **Rule for future agents:** before writing a new helper / DTO / service shell / try-except block in a product, run `--scan-helpers` + `--scan-service-lines` + `--scan-blocks` + (if scoped to one product) `--scan-within-product`. If the name or shape recurs, absorb instead of replicate. After completing any product cleanup pass, re-run all 6 and triage anything new at N=2+ per `KB § PATTERNS/project-execution.md § 2.7`. Per `KB § 01-PHILOSOPHY § DRY` + standing user directive 2026-04-28: *"vamos aproveitar to search for absorption opportunities to the seed along the way"*.

  **Second-wave gaps (evaluated 2026-04-28 after first-batch shipped):**
  - ✅ **#3 SQL migration patterns** — BUILT. `scan_migration_patterns` ships with 5 probes (RLS, FK index, search_path, audit trigger, updated_at trigger). First run caught 176 occurrences of `SET search_path` across 5 products.
  - ✅ **#4 Test fixture recurrence** — BUILT. `scan_test_fixture_recurrence` ships, scoped to `tests/` with stricter blacklist (excludes `test_*` methods, `SAMPLE_*` literals).
  - ❌ **#1 Cross-language pattern (Python ↔ TS pairs)** — DEFERRED. Value medium, complexity high (need pairing model). Each language scan covers its side; pairs are caught by manual review during absorption work.
  - ❌ **#2 Decorator usage patterns** (`@router.get` shapes) — DEFERRED. Most decorator recurrence is FastAPI-bound boilerplate already absorbed by the framework; real absorption-shaped decorators are rare.
  - ✅ **#5 Block-level CROSS-product mode** — already in `scan_block_patterns` via `cross_product_only=True` kwarg.

  **First-batch FP rate (manual review of 28 high-severity `scan_block_patterns` findings):** 79% real absorption candidates, 21% shape-similarity FPs (generic `db.table` accesses with same try/except shape but different domain queries). Acceptable for first run.

  **Token savings (4-workflow benchmark, 2026-04-28):**
  - Cross-product helper recurrence: **93% saved** (175K → 13K tokens), 7× faster
  - Cross-project status digest: **99% saved** (112K → 1.5K tokens), 3.5× faster
  - Trivial symbol grep: ~slight cost increase (JSON wrapping overhead)
  - Full compliance scan: not directly comparable — MCP runs 12 detectors vs reading individual files
  - **Honest read:** discovery / audit / sweep workflows are big wins. Trivial lookups don't change much. Run benchmark fresh after each tool addition.

  **Tool maturity verdict (2026-04-28):** Solid — 8 scans cover layered absorption surface. Apply across the cleanup queue and re-evaluate calibration in 1-2 weeks based on absorption-vs-accept ratio.

## CLI (for humans)

```bash
python mcp/noctusai/cli.py --validate                   # all detectors aggregated
python mcp/noctusai/cli.py --review                     # observation-only; files LLM-authored proposals, NEVER edits code
python mcp/noctusai/cli.py --analyze
python mcp/noctusai/cli.py --discover
python mcp/noctusai/cli.py --metrics
python mcp/noctusai/cli.py --test
python mcp/noctusai/cli.py --build [--changed] [--product P]   # parallel; scoped via flags
python mcp/noctusai/cli.py --proposals
python mcp/noctusai/cli.py --verify-kb-sync

# Cross-cutting utilities (added 2026-04-28)
python mcp/noctusai/cli.py --refs "<pattern>"           # recursive ref finder
python mcp/noctusai/cli.py --status                     # project state digest
python mcp/noctusai/cli.py --check-three-way-sync       # KB ↔ CLAUDE.md ↔ memory parity
python mcp/noctusai/cli.py --scan-recurrence            # DRY-into-seed candidates
python mcp/noctusai/cli.py --check-phase-state          # §6 ↔ §11 drift (also runs in pre-commit)
```

## Architecture

```
mcp/noctusai/
  server.py         MCP server
  cli.py            CLI for humans
  tools/            Tool implementations
  .venv/            Separate venv for MCP deps
  README.md
```
