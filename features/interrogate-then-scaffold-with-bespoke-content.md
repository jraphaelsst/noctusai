# Feature — interrogate-then-scaffold with bespoke content

> **What this is.** Two-phase product scaffolding. Phase 1 (`noctus.dev.scaffold_interrogate`) returns the canonical question set the agent walks the user through. Phase 2 (`noctus.dev.scaffold_product` with `brief={...}`) writes the brief to disk FIRST, runs mechanical placeholder substitution, then LLM-rewrites every prose surface so the new product's content is bespoke — never inheriting the seed's narrative DNA. Closes the methodology gap surfaced by AdConnect: scaffolded products were carrying the seed's voice into production prose.

- **Created:** 2026-05-05
- **Owner:** rapha
- **Trigger:** User directives 2026-05-05:
  - *"Whenever a new product gets created, the placeholders from the seed also gets modified to fit the new product's scope."*
  - *"When i ask a new product, the ai must question me about the product so it gets the right idea. Then it produces the content needed."*
  - *"Both. Make the brief durable BEFORE the prose update. First create products/<slug>/.scaffold-brief.md, THEN you edit files. If questions skipped: LLM prose without mechanical. Don't silent-error."*
  - *"New products are not to use nothing belonged to the seed. All should be created specifically to each product."*

## Two-phase flow

### Phase 1 — Interrogate (`noctus.dev.scaffold_interrogate(name, slug, schema)`)

Returns the canonical question set:

| Key | Required | Purpose |
|---|---|---|
| `domain` | ✅ | Real-world domain — anchors LLM rewrite |
| `primary_users` | ✅ | Who uses this — drives README's audience |
| `core_entities` | ✅ | 3-5 core domain entities — anchors MASTER-PROMPT |
| `primary_workflows` | ✅ | 1-3 end-to-end workflows |
| `key_integrations` | ⏤ | External services |
| `success_criteria` | ⏤ | Outcome metrics |
| `naming_conventions` | ⏤ | Domain-specific conventions |

The agent (Claude) walks the user through these. No LLM call happens in Phase 1 — pure data return.

### Phase 2 — Scaffold (`noctus.dev.scaffold_product(... brief={...})`)

Strict ordering, per the brief-durable-before-prose rule:

1. **Copy template skeleton** (`shutil.copytree`) — structural files only.
2. **Write brief FIRST** to `products/<slug>/.scaffold-brief.md`. The user's intent is the most valuable on-disk artifact and survives any later failure. With `brief=None`, writes a SKIPPED stub explaining the gap and how to recover.
3. **Mechanical placeholder substitution** — `{{PRODUCT_NAME}}` / `{{PRODUCT_SLUG}}` / `{{SCHEMA_NAME}}` / `{{BACKEND_PORT}}` / `{{FRONTEND_PORT}}` / `{{PRODUCT_ICON}}` replaced across all non-binary files. **Skipped entirely when `brief=None`** (per user rule "if questions skipped: LLM prose without mechanical").
4. **LLM prose rewrite** of `README.md` and `MASTER-PROMPT.md` via `noctusai_lib.integrations.llm.chat_completion(provider="anthropic")`. The system prompt explicitly forbids echoing seed/template framing — output speaks specifically about the new product's domain. Always runs, even on the skip path (with `brief=None` the LLM gets name+slug+schema only and is instructed to flag uncertainty).
5. **Seed-row migration** + **`start.sh` registration** (existing behavior — unchanged).

### Skip path (when `brief=None`)

Surfaced loudly in `next_steps`. Specific consequences:
- `.scaffold-brief.md` is a SKIPPED stub.
- Mechanical substitution does NOT run — placeholders survive in code files (which the LLM doesn't touch).
- LLM rewrite STILL runs over prose surfaces; the system prompt instructs uncertainty-marking.
- `mechanical_substitution.applied = False` in the return.
- `next_steps` instructs the agent to recover the brief retroactively.

This is non-silent: the gap is on disk in three places (brief stub, missing mechanical content, next_steps).

## Hard rule the LLM follows

> NEVER mention 'seed', 'template', 'scaffold', 'placeholder', or any meta-framing that hints the file came from a generator. The new product was conceived standalone. Use the brief to ground every prose paragraph in the new product's actual domain.

This is the load-bearing instruction in `_llm_system_prompt()` at `mcp/noctusai/tools/noctus/dev/scaffold.py`.

## LLM provider choice

Default `provider="anthropic"` (Claude). Rationale: Claude excels at coherent prose rewrite from a structured brief. The platform's overall default is `"openai"` per `noctusai_seed.llm_defaults` — the scaffold tool overrides per-call. The override is the per-call mechanism `chat_completion` already supports (no new infrastructure).

Override path: pass `llm_provider="openai"` to `scaffold_product` to fall back to the platform default.

## Files touched

- `mcp/noctusai/tools/noctus/dev/scaffold.py`:
  - New constants: `INTERROGATION_QUESTIONS`, `PROSE_SURFACES`.
  - New: `scaffold_interrogate(name, slug, schema)`.
  - New: `_write_scaffold_brief(target, brief)` (with skip-stub branch).
  - New: `_llm_system_prompt()`, `_llm_user_prompt(...)`.
  - New: `llm_rewrite_file_content(...)` async (public seam — tests monkey-patch).
  - New: `_run_llm_rewrites(...)` sync wrapper using `asyncio.run`.
  - Updated: `scaffold_product(... brief=None, llm_provider="anthropic")` integrates the new flow with brief-first ordering and skip-path semantics. New return keys: `brief_write`, `mechanical_substitution`, `llm_rewrite`.
  - MCP tool: new `noctus.dev.scaffold_interrogate`. Updated `noctus.dev.scaffold_product` signature.
- `mcp/noctusai/tests/test_scaffold.py`:
  - Autouse fixture stubs `llm_rewrite_file_content` to return None by default (no real LLM call in tests).
  - New: `TestScaffoldInterrogate` (2 tests).
  - New: `TestScaffoldBriefFirstOrdering` (3 tests).
  - New: `TestScaffoldLLMRewrite` (3 tests — brief-passthrough, failure-surfacing, skip-path-still-calls-LLM).
  - Updated: existing tests that depend on mechanical substitution now pass `brief={}` to opt into the mechanical path.

## Test coverage (8 new tests, 42/42 pass)

- **Interrogate**: returns canonical question set, surfaces required keys, `next_step` describes skip path.
- **Brief-first**: dict written with all questions rendered (answered + unanswered visible); `brief=None` writes SKIPPED stub; skip path surfaced in `next_steps`.
- **Mechanical-skipped on no-brief**: `applied=False`, `files_processed=0`, placeholders survive in files.
- **LLM rewrite happy path**: called once per prose surface, brief passed through, files contain LLM output.
- **LLM failure**: per-surface failure surfaced in `llm_rewrite[surface]["failed"]`, global failure in `next_steps`. No silent fallback to seed content.
- **Skip-path LLM still runs**: brief=None passed through to LLM; LLM call happens for every prose surface.
- **Hygiene regression guard**: tmp_path seam contains all writes (existing `TestScaffoldRespectsTestSeam` still green).

## Methodology rule (durable)

> **No new product inherits the seed's prose.** Every scaffold writes the brief BEFORE any prose edit, runs mechanical substitution + LLM rewrite, and surfaces every gap explicitly. Silent fallback to seed-template content is forbidden. The skip path (no brief) is loud, not silent: stub brief on disk, mechanical disabled, LLM still runs with marked uncertainty, all surfaced in `next_steps`.

## Sub-tasks

- [x] `INTERROGATION_QUESTIONS` constant + `scaffold_interrogate` function.
- [x] `_write_scaffold_brief` helper with brief-first ordering + skip stub.
- [x] `llm_rewrite_file_content` async seam + `_run_llm_rewrites` sync wrapper.
- [x] `scaffold_product` integration with brief-first + LLM rewrite + skip-path semantics.
- [x] MCP tool registrations: `noctus.dev.scaffold_interrogate` + updated `scaffold_product`.
- [x] Autouse LLM-stub fixture in test_scaffold.py.
- [x] Updated existing mechanical-substitution tests to pass `brief={}`.
- [x] New test classes: `TestScaffoldInterrogate`, `TestScaffoldBriefFirstOrdering`, `TestScaffoldLLMRewrite`.
- [x] All 42 scaffold tests pass; no real-file pollution under tmp_path seam.
- [ ] Memory entry updated to cover interrogate-then-scaffold + bespoke-content rule.

## Out of scope (deferred)

- **Re-rewrite tool** — `noctus.dev.scaffold_rerewrite(slug, surfaces=[...])` — for when the user fills in the brief retroactively after a skip-path scaffold. Not built yet; the manual recovery path (delete + re-scaffold) works for now.
- **More prose surfaces** — currently only `README.md` and `MASTER-PROMPT.md`. Migration headers (`001_seed.sql` comments), inline docstrings, and example-data fixtures are still seed-derived. Future expansion: include them in `PROSE_SURFACES`.
- **Live-DB url_base sync** when scaffold output changes a port — separate from this feature; covered by the dynamic-sso-redirect-resolver work.
- **AdConnect re-scaffold** — user said they will delete + recreate AdConnect with this flow. They drive that; the tooling is ready.
