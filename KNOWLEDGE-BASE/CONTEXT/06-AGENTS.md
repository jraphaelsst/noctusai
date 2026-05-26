# 06 — MCP Dev Toolkit

> Platform development tools exposed as an MCP server at `mcp/noctusai/`.
> Tool count is derived from `_tool(` invocations in `mcp/noctusai/server.py::list_tools()`.

## Tools

<!-- kb-counts:start:mcp_tools -->
**169 tools total** (auto-counted from `mcp/noctusai/tools/`).
<!-- kb-counts:end:mcp_tools -->

### Context
- noctus.dev.agent_context — full platform overview
- noctus.dev.product_context — product structure + docs

### Products
- noctus.dev.list_products, noctus.dev.get_product, noctus.dev.platform_metrics

### Scaffold
- noctus.dev.scaffold_product, noctus.dev.available_ports

### Compliance
- noctus.dev.validate, noctus.dev.validate_product
- **Detectors in `tools/compliance.py`** (deterministic, zero-AI):
  - `check_seed_compliance` — verifies `create_product_app()` usage, `-e seed/{lib,framework}/backend` in requirements, no boilerplate routers, `createProductApp/Layout` on frontend. **Tuned by the control-plane classification set `CONTROL_PLANE_PRODUCTS = {"core"}`**: control-plane products legitimately OWN `team` / `notifications` / custom `Layout` (they ARE the identity/team authority), so the "has own team.py / Layout.tsx" warnings are suppressed for them. Consumer products still get flagged. Introduced 2026-04-23 (originating project archived after close) (fold of `keeper-control-plane-classification` backlog).
  - `check_path_references` — catches stale `shared/*` paths that should be `seed/*`.
  - `check_standard_routers_audit` — cross-audits a product's `standard_routers=[...]` opt-in list against real frontend consumption via a curated signal map (`NotificationBell` → `notificacoes`, `/api/team` → `team`, `useLLM*` → `llm`). Flags under-grant (frontend uses → backend opts out → runtime 404s) at `critical` severity; over-grant (backend opts in → no frontend signal → dead router) at `warning`. **Self-provision v2**: AST-parses the `routers=[<mod>.router, ...]` kwarg in `main.py` to detect what the product actually wires, not what files exist in `routers/`. A `team.py` file that isn't wired no longer counts as self-provision — the frontend would still 404. Falls back to filename-based detection when the kwarg is unparseable (variable reference, dynamic). Introduced 2026-04-22; v2 AST upgrade 2026-04-23 (originating projects archived after close).
  - `check_frontend_entrypoint` — verifies the product's frontend actually CALLS `createProductApp(...)`. Two valid shapes: (a) `main.tsx` calls it directly (core pattern); (b) `main.tsx` delegates to `./App.tsx` whose default export calls it (therapy pattern). Rendering a raw `<BrowserRouter>` / `<QueryClientProvider>` tree without routing through the framework is flagged `critical` — the Suspense, error boundary, routing, providers, and auth paths are bypassed. Closes the gap where the App.tsx-scoped check in `check_seed_compliance` never fired on core (core has no App.tsx). Introduced 2026-04-23 (originating project archived after close).
  - `check_out_of_contract_trees` — global repo-root sweep (not per-product). Scans the repo root for directories that look like product trees (have `backend/app/main.py` OR `frontend/src/main.tsx`) but live outside `products/*/`. Excludes known platform dirs (`seed/`, `templates/`, `mcp/`, `KNOWLEDGE-BASE/`, `projects/`, `scripts/`, `venv/`, `.*`). Flags `critical` with a remediation pointer to either migrate to `products/<name>/` via a `<name>-seed-wiring` project or delete if legacy. Guards against future `/adconnect/`-style stray trees. Introduced 2026-04-23 (originating project archived after close).
  - `check_phase_state_consistency` — global walk (not per-product) over every `PROJECT.md` across `projects/`, `products/*/projects/`, `core/projects/`. Flags four §6 ↔ §11 drift classes: (1) §11 says shipped but §6 header lacks `✅`; (2) header has `✅` but sub-tasks remain `- [ ]`; (3) header has `✅` but no `**Improvements:**` block; (4) §11 says shipped + §6 has both unflipped header AND unticked sub-tasks (the dashboard-lying case). Severity `high`. `⏳`/`❌`/`🅿️` icons recognized as legitimate non-shipped states. Also exposed as `python mcp/noctusai/cli.py --check-phase-state` (exit 1 on mismatch); pre-commit hook runs it ONLY when `**/PROJECT.md` is staged. Introduced 2026-04-28 by `keeper-phase-state-consistency-detector` (folder deleted per clean-folder rule). Closes the slip pattern where agents wrote rich §11 entries but forgot to flip §6 checkboxes — documentation alone wasn't sufficient (caught 5+ times in two days); deterministic enforcement now blocks the slip from shipping.
  - `check_no_self_monkeypatch` — AST-walks test files, flags `monkeypatch.setattr(<our_module>, ...)` and `unittest.mock.patch.object(<our_module>, ...)` patterns that neuter our own logic instead of testing it. Resolves local-bound names against the file's import map (so `from app.services import ai_pipeline` + `monkeypatch.setattr(ai_pipeline, "require", ...)` resolves to `app.services.ai_pipeline.require` for classification). Allowlists boundary accessors (`get_client`, `chat_completion`, audit `log_action`, `resolve_credential`/`check_required_credentials`, env-config getters, JWT `__from_token__`) + suffix patterns `_get_<x>_token` / `_get_<x>_client` / `_get_<x>_config` via `_BOUNDARY_ACCESSOR_REGEXES` + external libs re-exported through our modules (`httpx.AsyncClient` via `app.routers.X`) + inline `# self-patch-ok: <reason>` comments. Severity `warning` (so legitimate-historical patterns don't tank the score; user tightens over time). Introduced 2026-04-28 by `mcp-tooling-expansion`; allowlist extended 2026-04-28 by `keeper-warning-triage` after first-run surfaced 420 hits across 7 products (the 105 boundary-helper hits collapsed at allowlist time). Per memory `feedback_no_monkeypatching_in_tests.md` + CLAUDE.md "No workarounds — and no monkey-patching, in production OR tests".
  - `check_silent_errors` — AST-walks production Python (excludes tests + migrations + vendored deps), flags `try / except:` handlers whose body neither raises, logs, nor surfaces the error in any way. Specifically catches `except: pass`, `except Exception: return None`, and similar swallow patterns. **No `# silent-ok` escape hatch** — retired 2026-04-28 per user directive ("i dont want any silent-ok sign accross the platform"). Every handler MUST log via `logger.<level>(...)`, `raise`, or surface via a return value. Bootstrap-time code (e.g. `noctusai_seed._version` resolving the SHA before `configure_logging` runs) uses `logger.debug(...)` — root logger drops debug by default but the call is in the code, the detector recognizes it, and `NOCTUSAI_DEBUG=1` reveals it during troubleshooting. Severity `warning`. Introduced 2026-04-28 by `mcp-tooling-expansion`; escape hatch retired same day by `platform-logging-standardization`. Per memory `feedback_no_silent_errors.md` + `feedback_silent_ok_is_not_a_substitute_for_logging.md` + CLAUDE.md "No silent errors — always explicit fix opportunities".
  - `check_clean_folder_violations` — walks every PROJECT.md, flags ✅-closed projects whose folders still exist (the apply-inline-then-delete + clean-folder rule violation). Parses the **leading** status icon only — narrative like `📋 READY TO RESUME ... Phase 0 ✅ executed` is not a closed-project signal (false-positive caught + fixed 2026-04-28 against `repo-state-consolidation`). Distinguishes mixed-status states (`✅` leading but `⏳`/`❌`/`🅿️` also present — transitional close) from pure ✅. Severity `warning`. Introduced 2026-04-28 by `mcp-tooling-expansion`; leading-icon refinement 2026-04-28 by `keeper-warning-triage`. Per CLAUDE.md "Clean folder — every artifact has a home".
  - `check_detector_has_regression_test` — meta-detector enforcing the platform-wide testing methodology: every other `check_*` keeper detector MUST ship colocated with a regression test. Self-parses `mcp/noctusai/tools/compliance.py` to enumerate all `check_*` functions, then verifies each has a matching `Test<CamelCase>` class somewhere under `mcp/noctusai/tests/` (case-insensitive matcher accepts `TestCheckSilentErrors`, `TestSilentErrors`, and acronym-preserving forms like `TestAIFeatureCompleteness`). Detectors whose tests live under non-matching names register an explicit override in `_DETECTOR_TEST_OVERRIDES`. Severity `high` — a missing detector test is the kind of gap that lets a real-world miss ship without being noticed. Introduced 2026-04-29 by `platform-logging-standardization` Phase 6 (user directive: regression-test-the-detector becomes platform-wide methodology, integrated into the code validation system). Convention + worked examples at `KB § PATTERNS/compliance/testing.md § Regression-test-the-detector`.
  - `check_seed_export_membership` — global sweep. For each symbol a product imports from a seed *package* surface — `from noctusai_lib.x.y import sym` where `x/y/` is a package with a literal `__all__`, OR a `@noctusai/lib` / `@noctusai/seed` frontend import — asserts the symbol is in that package's published surface (`__all__` backend, per-specifier `index.ts` re-exports frontend; `@noctusai/lib`→`seed/lib/frontend/src/index.ts`, `@noctusai/seed`→`seed/framework/frontend/src/index.ts`). Catches the "reconciled-but-invisible" half-ship (code lifted into a seed module but never published, so the seam is offered only via a deep import one consumer happens to use). Calibrated to exempt: `from <pkg> import <submodule>` (module import — `__all__` does not govern submodule importability; was a real N=4 FP class), `export *` / computed-`__all__` (non-enumerable). Severity `warning`. Introduced 2026-05-16 by `social-wiring-absorption` W5.7a (N=2: W1.E2 `lid_auth` + W2.4/DEP-B frontend WA hooks). Extends the verify-the-seed-ships-it rule from file-presence to export-surface membership. Per memory `feedback_seed_export_membership_keeper`.
  - `check_hardcoded_product_slug_set` — global sweep over `seed/lib/backend/tests/`. Flags any literal list/tuple/set containing ≥3 live product slugs (recognizer corpus derived from the live `products/` tree at scan time, so the detector itself does not freeze a slug literal). A frozen product-slug literal goes stale when the fleet changes and misattributes assertion failures. Remediation: derive from `parse_products_registry()` (`noctusai_lib.config.cors_registry`). Opt-out: a `slug-literal-ok` / `registry-exempt` / `not-a-product-set` rationale keyword (mirrors `check_mock_schema_validation`). Severity `warning`. Introduced 2026-05-16 by `social-wiring-absorption` W5.9a (N=2: W3.5 `test_cors_registry` + `test_per_product_cors_sentinel` both froze slug tuples that staled on `media-scheduling` consolidation). Per memory `feedback_hardcoded_product_slug_set_keeper`.

### Review (observation-only — never modifies code)
- noctus.dev.review — detect seed-compliance issues + surface them for authoring. Three modes:
  - `mode=agent` (default): returns the issue list + a review prompt the in-session agent uses. The agent fills `templates/PROPOSAL-TEMPLATE.md` per issue using session context and files via `noctus.dev.file_proposal`. Zero LLM cost at this layer.
  - `mode=headless`: OpenAI `gpt-4o-mini` authors proposals (for CI / cron / solo CLI without an agent).
  - `mode=evaluate`: writes OpenAI + agent proposals side-by-side to `products/<product>/proposals/evaluations/<ts>/` for comparison.
  - Replaces the retired `noctusai_heal`. See `KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/proposals-and-improvements.md` for the full protocol (two capture triggers, phase → proposal flow, promote boundary).
- noctus.dev.proposal_template — return `templates/PROPOSAL-TEMPLATE.md` content so agents get a consistent starting point.
- noctus.dev.file_proposal — write a filled-template proposal to `products/<product>/proposals/` (keeper, via `product=`) or `projects/<slug>/proposals/` (project-phase, via `project=`).

### Analyzers
- noctus.dev.analyze, noctus.dev.analyze_patterns, noctus.dev.analyze_deps, noctus.dev.analyze_tests

### AI
- noctus.dev.ai_discover, noctus.dev.ai_advisory

### Master Prompts
- noctus.dev.sync_master_prompt, noctus.dev.sync_all_master_prompts, noctus.dev.check_master_prompt

### Testing
- noctus.dev.run_tests, noctus.dev.run_all_tests, noctus.dev.build_frontend, noctus.dev.build_all_frontends

### Diff & Quality
- noctus.dev.diff_against_seed, noctus.dev.find_orphans, noctus.dev.check_api_consistency

### Proposals
- noctus.dev.list_proposals, noctus.dev.accept_proposal, noctus.dev.reject_proposal

### Cross-cutting utilities (added 2026-04-28 by `mcp-tooling-expansion`)
- **`noctus.dev.refs <pattern>`** — recursive reference finder across CLAUDE.md / KB / projects / mcp / seed / products. Replaces the manual `grep -rln` ritual run before deletes / renames / closures. Excludes vendored deps + binaries. Used 8× during the 2026-04-28 closed-folder cleanup; tool absorbs the pattern.
- **`noctus.dev.build_parallel`** — parallel cross-product `vite build` sweep. Supersedes the legacy sequential `noctus.dev.build_all_frontends`. Combine with `changed_only=True` to scope to git-changed products only (perf — skips unchanged products). 4-worker default; configurable.
- **`noctus.dev.status`** — cross-project state digest. Walks every PROJECT.md across the three valid locations + emits status / sub-task progress / last-updated / `⏳`-`✅` icon / §3a presence / phase-state-detector flags. Sorted: executing → ready → parked → blocked → shipped (audit history at the bottom).
- **`noctus.dev.check_three_way_sync`** — verify KB ↔ CLAUDE.md ↔ memory parity. Closes the gap that `verify-kb-sync.sh` cannot cover (memory dir lives outside the repo at `~/.claude/.../memory/`). Reports missing index entries, dangling links, missing KB anchors, and CLAUDE.md keyword mismatches per the three-way-sync rule (`KB § 01-PHILOSOPHY § Docs stay in sync`).
- **Code-hygiene trio + `noctus.hound.scan` orchestrator (added 2026-05-10).** The seed-absorption methodology operates at three orthogonal scopes; the **hound** is a single MCP entry point that runs all three and emits a `next_action` recommendation. Keeper-analog: keeper enforces compliance contracts (regulatory); hound surfaces hygiene candidates (curatorial).

  | Scope | Question | Detector | When to use |
  |---|---|---|---|
  | **Absorption** (cross-product, file-level) | Same file across N≥2 products? | `noctus.seed.report` (rolls up `scan_repetition` + `audit_drift`) | Pre-phase audit; whenever scaffolding a new product. |
  | **Fusion** (cross-tool, function-level) | Multiple tools that should collapse? | `noctus.seed.scan_fusions` (with `scope='cross_file'` / `'same_file'` / `'all'`) | When the toolkit grows; meta-tooling consolidation. |
  | **Optimization** (intra-file, line-level) | Dead code / single-use helpers / wrappers? | `noctus.seed.scan_optimizations` | End-of-phase polish. |
  | **Trio orchestrator** | Where should I look first? | `noctus.hound.scan` | Default entry point — "what cleanup is most urgent?". |

  **Hound `next_action` priority ladder:** absorption-P0 → optimization-high → absorption-P1 → fusion-subsume → optimization-warning → ad-hoc. The hound preserves each scope's full output under `scopes.<name>` and aggregates counts + LoC-savings + files-absorbable estimates under `unified`. Soft-fails per scope (errors[] populated, non-failed scopes still run).

  **Calibration learnings (2026-05-10):**
  - **Structural-duplicate filter** in `scan_repetition` (default-on): skips empty marker files (`__init__.py`, `.gitkeep`) AND already-absorbed re-export shims (any file ≤5 operative lines that mentions `seed/` / `@noctusai/seed` / `noctusai_seed` / `noctusai_lib`). Without this filter, 11 of 11 P1 candidates were false positives. Pass `skip_structural_duplicates=False` to disable.
  - **Wrapper detector** (`scan_optimizations`): requires the function to have ≥1 parameter AND the body's call's attribute receiver must be a `Name` (not a `Call`). Chained calls like `datetime.now().isoformat()` are NOT wrappers; zero-param "wrappers" are usually named-operation factories.
  - **LoC-savings heuristic** (`scan_fusions`): calibrated from `× 0.6` → `× 0.15` after a 12× overestimate against actual collapse work — see `feedback_tool_collapse_loc_lesson.md`.
  - **Real ceiling is small.** Post-filter, the live tree has 0 P0/P1 absorption candidates, ~3 fusion subsumes, ~47 small single-call helpers. Don't quote inflated savings estimates.

  Lives at `mcp/noctusai/tools/noctus/hound/`. New sub-umbrella `noctus.hound.*` parallels `noctus.dev.*` / `noctus.seed.*` / `noctus.team.*`. Detail: `KB § PATTERNS/architect/seed-absorption.md`.

- **Absorption-search sextet (use whenever working in product code — the user's standing directive 2026-04-28):**

  | Scan | What it catches | First-run calibration (2026-04-28) |
  |---|---|---|
  | **`noctus.dev.scan_recurrence`** | Verbatim LINES recurring in `main.py` / `main.tsx` / `App.tsx` / `conftest.py` / `vitest.config.ts`. Allowlists `from noctusai_seed` / `from @noctusai/...` (inheritance, not replication). | 216 findings, 68 high. Signal MODERATE — most hits are platform-standard inheritance markers. Use only for explicit replication cases (mount-line, fixture). |
  | **`noctus.dev.scan_cross_product_helpers`** | Function/class NAMES recurring across N≥2 products in services/routers/dependencies/hooks/components. Suggests seed-lib target per name shape. | 75 findings, **14 high (all real)**: digest pipeline (5 products: `_render_bodies` / `_generate_narrative` / `_aggregate` / `_fetch_window` / `_empty_output`), Metas gamification CRUD + hooks (3 products), `login` / `list_invoices`. **HIGH-SIGNAL — primary scan.** |
  | **`noctus.dev.scan_service_line_recurrence`** | Verbatim LINES in service/router files with strict filters (≥60 chars + has `(`). Catches `datetime.fromisoformat(s.replace("Z", "+00:00"))`, HTTPException Portuguese-error patterns, pagination expressions. | 52 findings, **9 high** including `_TEMPLATE_DIR` (5 products), pagination shape (4 products). HIGH-SIGNAL. |
  | **`noctus.dev.scan_block_patterns`** *(closed gap #1, 2026-04-28)* | AST-walks `try/except` blocks; normalizes identifiers; hashes structural fingerprint. Catches multi-line block recurrence the line/name scans miss — `try: from app.services import audit_service / await audit_service.log(...) except: logger.warning(...)` × 7 in one product. Suggests `safely_log_action`/`safely_dispatch`/`safely_run` helpers per body shape. | 241 findings, 28 high. Top hit: 7× `audit_service.log` block in core. **HIGH-SIGNAL for the within-core best-effort patterns.** |
  | **`noctus.dev.scan_within_product_helpers`** *(closed gap #2, 2026-04-28)* | Helper names duplicated N≥3 files INSIDE one product. Closes the gap that cross-product scans require N≥2 distinct products. Suggests `app/utils.py` (product-scope) or `noctusai_lib.<area>` (cross-cutting). | 12 findings, 3 high: `get_resumo` × 6 in ERP, `_get_service` × 5 in mailing, `_get_platform_setting` × 5 in therapy. |
  | **`noctus.dev.scan_pydantic_model_shapes`** *(closed gap #3, 2026-04-28)* | Pydantic `BaseModel` field-set recurrence across products (different class names, identical field set + types). Suggests `noctusai_lib.schemas.<canonical>`. | 1 finding (`LoginRequest`/`LoginInput` 2 fields). LOW-VOLUME — Pydantic schemas are mostly product-bound by design. |
  | **`noctus.dev.scan_test_fixture_recurrence`** *(closed second-wave gap #4, 2026-04-28)* | pytest fixtures + helpers across `tests/conftest.py` + `tests/services/` + `tests/routers/` + `tests/integration/`. Stricter blacklist than production helper scan (excludes `test_*` methods + ALL_CAPS sample-data names). Suggests `noctusai_lib.testing.<helper>`. | 88 findings, **17 high**: `pytest_configure` × 8 products, `_fake_build`/`_fake_fetch` × 4, `Stateful*` mock infrastructure × 2 (ERP + PF). |
  | **`noctus.dev.scan_migration_patterns`** *(closed second-wave gap #3, 2026-04-28)* | Regex-probes 5 known SQL pattern shapes (RLS subquery `auth.uid()`, FK-with-index, `SET search_path`, audit-log trigger, `updated_at` trigger) across product migrations. Reports per-product occurrence counts. | 3 findings, **2 high**: `search_path_lock` × 5 products / **176 occurrences** (huge template recurrence), `updated_at_trigger` × 4 products / 42 occurrences. |

  **Rule for future agents:** before writing a new helper / DTO / service shell / try-except block in a product, run `--scan-helpers` + `--scan-service-lines` + `--scan-blocks` + (if scoped to one product) `--scan-within-product`. If the name or shape recurs, absorb instead of replicate. After completing any product cleanup pass, re-run all 6 and triage anything new at N=2+ per `KB § PATTERNS/architect/project-execution.md § 2.7`. Per `KB § 01-PHILOSOPHY § DRY` + standing user directive 2026-04-28: *"vamos aproveitar to search for absorption opportunities to the seed along the way"*.

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

### Reading & cost utilities (added 2026-05-02 by `methodology-extraction`)

Companion tooling for the **narrow-read** rule (`CLAUDE.md §1` → `KB § PATTERNS/common/agent-reading-discipline.md`). The rule says: for any file >200 lines or unfamiliar shape, read structure before bodies. These three tools make that ergonomic.

| Tool | What it returns | Backed by | Source | Tests |
|---|---|---|---|---|
| **`noctus.dev.outline_python <path>`** | `OutlineResult` — every top-level `class` / `def` / `async def`, first-level methods (with `parent`), `UPPER_SNAKE_CASE` module constants, import lines. Each carries `line` / `end_line` / `decorators` / `docstring_first_line`. **No bodies.** Returns `parse_error` instead of raising on missing file / `SyntaxError` / encoding error. | stdlib `ast` (no new dep) | `mcp/noctusai/tools/outline_python.py` | `mcp/noctusai/tests/test_outline_python.py` (14 cases incl. real-world smoke against `cost_evaluation.py`) |
| **`noctus.dev.outline_typescript <path>`** | Same `OutlineResult` shape — classes (incl. `abstract`), interfaces (kind=`interface`), type aliases (kind=`type`), top-level functions (regular + async + default-export), arrow-fn consts (React components & hooks), first-level methods, constants, imports (multi-line collapsed). Block + line comments stripped before regex passes so `/* function fakeFn */` doesn't false-match. | regex (audit-driven deviation from the §7 default Compiler API — Phase 4 of `methodology-extraction` chose regex for ~5ms/call vs ~200ms+50MB; ~95% precision on prettier/eslint-formatted TS; upgrade path open) | `mcp/noctusai/tools/outline_typescript.py` | `mcp/noctusai/tests/test_outline_typescript.py` (23 cases incl. smoke against `VistaShowcase.tsx` + `useVistaShowcase.ts`) |
| **`noctus.dev.count_tokens path=… text=… extensions=…`** | `TokenCountResult` — total + per-file `tokens` / `chars` / `words` / `lines`; reports `tokenizer_used` so callers know the precision. Accepts a path, inline text, or recursive walk over a tree (with `extensions=` filter). | tiktoken cascade → `chars/4` fallback | `mcp/noctusai/tools/cost_evaluation.py` | `mcp/noctusai/tests/test_cost_evaluation.py` (15 cases) |

**When to call which.** Outline first when a file is large or unknown; then targeted `Read offset=<line> limit=N` only the symbols you need. Use `count_tokens` to budget reads / measure CLAUDE.md or MEMORY.md drift / size up generated content. The `OutlineResult` shape is **identical** across both outliners — caller code stays parser-agnostic.

**Anti-pattern guard.** Don't use the outline tools to dump whole files. The point is the structure summary; if you need bodies, follow up with a targeted `Read`. Don't mistake `count_tokens` for the precise tokenizer agents use — even with tiktoken installed, there's a ~5-10% gap to the actual model tokenizer; treat results as planning estimates.

**CLI invocation:**

```bash
python mcp/noctusai/cli.py --outline-python <path>
python mcp/noctusai/cli.py --outline-typescript <path>
python mcp/noctusai/cli.py --count-tokens <path>
python mcp/noctusai/cli.py --count-tokens-text "<inline string>"
python mcp/noctusai/cli.py --count-tokens-ext .py KNOWLEDGE-BASE/   # recursive, by extension
```

**Note on detector status.** These are not keeper detectors — they are read-utility tools — so `check_detector_has_regression_test` does not fire on them. Their unit + smoke + (forthcoming) regression tests are colocated in `mcp/noctusai/tests/` per the test taxonomy in `KB § PATTERNS/compliance/testing.md`.

### Session-axis review (added 2026-05-03 by `session-review-baseline`)

The static-axis review surface (`noctus.dev.review`) walks repo files. The **session-axis review** sibling walks one Claude Code JSONL transcript and emits keeper-shaped issues for **agent-discipline** rules — the rules in `CLAUDE.md § 1` that `noctus.dev.review` cannot enforce because they only manifest as patterns of tool calls, not as static code.

| Tool | What it returns | Backed by | Source | Tests |
|---|---|---|---|---|
| **`noctus.dev.review_session path=… latest=…`** | Body-free issue list. Each issue: `{rule, severity, message, suggestion, jsonl_line, tool_name, target_path}`. Pure-function detector logic over an event stream extracted from one JSONL. Privacy: no user/assistant message bodies ever leave the adapter. | stdlib `json` parser; pure Python detectors | `mcp/noctusai/tools/session_review.py` + adapter at `mcp/noctusai/session_loader.py` | `mcp/noctusai/tests/test_session_review.py` (26 cases) + `tests/test_session_loader.py` (14 cases) |

**Detectors live (Phase 2 + 3):**
- `ast-first` (WARNING) — `Bash` mutating `sed/awk/perl -i` / `s/.../` body / `> *.py|*.ts|*.tsx` redirect, immediately followed by `Edit/Write` on the same source file. Mutation-marker predicate scopes around the read-only `sed -n '…p'` pattern (Phase 0 calibration found this is the dominant `sed` shape — false-positive rate is 0/5 sessions when the predicate is enforced).
- `narrow-read` (INFO) — whole-file `Read` (no `offset` / `limit`) on a >200-line repo file with no preceding `outline_python` / `outline_typescript`. Severity is **INFO**, not WARNING — Phase 3 calibration found the rule fires on legitimate "user reading a file once on purpose" cases too. Bumping to WARNING is gated on a future calibration run with manual ground-truth labels.

**Default JSONL discovery is macOS-only.** The default dir is `~/.claude/projects/-Users-rapha-Documents-repository-NoctusAI-noctusai/`. On non-macOS hosts, always pass `path=<jsonl>` explicitly. The adapter (`session_loader.py`) is the **only** code that touches raw JSONL keys — when Anthropic renames a field, fix it there.

**Detector privacy posture.** Detectors only see `tool_use.name`, `tool_use.input`, `tool_result.content_size`, and `tool_result.is_error`. They never read user/assistant message text. Adding a future "language-slip" detector (e.g. catching `per-product X` phrasing) would require revisiting this posture — out of scope for the baseline.

**CLI invocation:**

```bash
python mcp/noctusai/cli.py --review-session ~/.claude/projects/<encoded-cwd>/<uuid>.jsonl
python mcp/noctusai/cli.py --review-session-latest          # newest *.jsonl in default dir (macOS)
```

**Out of scope (Phase 5+ follow-on):** Stop-hook auto-run, project-close gate, scrubbed transcript reports, additional detectors (estimate-off-evidence, replication-to-seed slip, absorption-search compliance, auto-commit gate). The harness is designed so each new detector is a one-file addition + one-line registry entry in `_DETECTORS`.

---

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

# Reading & cost utilities (added 2026-05-02 by methodology-extraction)
python mcp/noctusai/cli.py --outline-python <path>      # Python symbol tree (no bodies)
python mcp/noctusai/cli.py --outline-typescript <path>  # TS / TSX symbol tree (no bodies)
python mcp/noctusai/cli.py --count-tokens <path>        # token budget for a file
python mcp/noctusai/cli.py --count-tokens-text "<text>" # token budget for inline text
python mcp/noctusai/cli.py --count-tokens-ext .py <dir> # recursive walk, by extension

# Session-axis review (added 2026-05-03 by session-review-baseline)
python mcp/noctusai/cli.py --review-session <jsonl>          # walk one transcript; emit ast-first / narrow-read issues
python mcp/noctusai/cli.py --review-session-latest           # newest *.jsonl in macOS default dir
```

## Subagent MCP access (dispatched agents CAN use this toolkit — no extra infra)

`.mcp.json` registers `noctusai` as a **stdio, local, project-scoped** server (`command: mcp/noctusai/.venv/bin/python server.py`, `cwd: <repo>`). Claude Code spawns it as a child of the **session**.

- **Subagents (`Agent`-tool dispatches) run inside that same session runtime** — they are sub-tasks of the same process, not separate machines. They reach the **same already-running stdio server**. **No online service, no container, no tunnel** is needed for local subagents.
- **The gate is the agent's tool-allowlist, not transport.** An agent whose definition allows the MCP tools can call them; a restricted one cannot. Fix for "agent can't see MCP" = widen the allowlist / dispatch a tool-broad agent — **not** infrastructure.
- **Repo-defined agents** (`.claude/agents/`): `engineer-default` has no `tools:` line → inherits **all tools** (full `mcp__noctusai__*`); `orchestrator-operator` is pinned `tools: … mcp__noctusai__*` (full suite — 2026-05-18, was `noctus_dev_archive`-only). Built-in types: `general-purpose`/`claude` = `*` (full); `Explore`/`Plan` are **read-only by harness design** — intentionally NOT granted mutating MCP (their contract is read code, not run dev tools); honor the carve-out, don't route mutating work through them.
- **Container + tunnel is only for an out-of-runtime consumer** (remote CI, another machine, a deployed cloud agent that is NOT a subagent of this session). Then flip noctosai to HTTP/SSE (`server.py` notes this is a one-line `server.run()` change, no tool-code changes), containerize, expose via ingress/tunnel. Unnecessary for the dispatched-subagent workflow.

→ `KB § PATTERNS/branching-first-orchestration` (dispatch) · `KB § 01-PHILOSOPHY.md § Context budget discipline` (MCP keep-list) · `.claude/agents/engineer-default.md`

## Architecture

```
mcp/noctusai/
  server.py         MCP server
  cli.py            CLI for humans
  tools/            Tool implementations
  .venv/            Separate venv for MCP deps
  README.md
```
