# Dev toolkit — codegen scaffolders + orchestration tools

> **TL;DR.** A 7-tool `noctus.dev.*` program (built 2026-05-18, evidence = lived session friction) that turns the platform's *recurring code shapes* and *recurring rituals* into one-call tools. Two families: **codegen scaffolders** emit consumable canonical boilerplate so the agent fills only the unique logic (token + consistency + AST-correct-by-construction); **orchestration tools** operationalize the codified methodology (R6 / R2 / findings) so it's tool-enforced, not discipline-enforced. Design contract: scaffolders **return code, never write files** (no worktree-path / overlay-divergence exposure); every scaffolder is gated by an *emitted-code-must-`ast.parse`* test (a codegen tool that emits broken code is worse than none).

---

## 1 · Why this exists

Our codification reflex is strong (rules → memory → KB → keeper), but many rules stayed **judgment-enforced**, and several code shapes were **hand-rewritten every time**. One session measured the tax: ~5 near-identical connector-MCP leaves, a full Protocol+Fake+Real+factory adapter, a Stage-4 keeper, ~12 memory entries, and the ~10×-repeated salvage ritual — all by hand. Each is a fixed shape; hand-regeneration burns tokens, drifts from convention, and (for the salvage ritual) caused real lost work + a stash-entanglement bug. The fix is to make the shape a tool.

## 2 · Codegen scaffolders (emit consumable boilerplate)

| Tool | Emits | Reach for it when |
|---|---|---|
| `noctus.dev.scaffold_seed_adapter(name, methods)` | the CLAUDE.md §1 IO-module shape — `types/protocol/fake/real/factory/__init__` + canonical test (6 files) | ANY new `noctusai_lib/integrations/<x>` (highest single token+correctness win — the Fake+Real+factory rule made physical) |
| `noctus.dev.scaffold_mcp_tool(vendor, service, action, kind)` | a connector-MCP leaf: `register/HANDLERS/tool_descriptors` + Pydantic In/Out + (`kind=write`) confirm-gate+audit + test skeleton | ANY new `<vendor>.<service>.<action>` connector tool |
| `noctus.dev.scaffold_keeper(name, flag, severity)` | a Stage-4 keeper: `check_<name>` detector + colocated `Test<CamelCase>` + cli `--check-<flag>` argparse+dispatch + pre-commit gate block | codifying a rule to Stage-4 (makes the codification pipeline's Stage-4 a tool, not a ritual) |
| `noctus.dev.scaffold_memory(name, description, body, mtype, index_section)` | a memory entry with canonical frontmatter + atomic `MEMORY.md` index-line sync | recording any durable user/feedback/project/reference fact |

**Design rule — return code, do not write files.** Scaffolders return `{*_code, note}` (or `{files: {...}}`); the agent places the output. This is deliberate: writing into worktrees re-introduces the worktree-path / harness-overlay-divergence risk class the orchestration tools exist to kill, and "consumable code the agent places" is exactly the token-save asked for. `scaffold_memory` is the one exception (writes the memory entry + index — the memory dir is outside any worktree, divergence-free).

**Quality gate.** Each scaffolder's colocated test `ast.parse`s the *emitted* skeleton. A codegen tool that can emit non-parsing code is a net negative — the test is the contract, not decoration.

## 3 · Orchestration tools (operationalize the methodology)

| Tool | Operationalizes | Replaces |
|---|---|---|
| `noctus.dev.salvage_worktree(agent_worktree, message, expect_markers, onto_worktree)` | **R6** (harness-overlay-vs-worktree divergence) | the ~10×/session manual verify→scoped-commit→cherry-pick→landed-verify ritual. On-disk-verifies from the server's true-disk context; `expect_markers=[[relpath,substring],…]` greps the actual file; **refuses loudly** on a divergence-clean worktree (`divergence_suspected`) — the contract is *do NOT loop-redispatch; re-author via Bash or apply architect-inline* |
| `noctus.dev.dispatch_preflight(target_paths, wrap_paths, base_ref)` | **R2** (verify-seed-on-fork-base) + R4 (merge-debt) + collision | the skip-able pre-dispatch checks. Verifies `wrap_paths` exist on the engineers' fork base (`git ls-tree origin/main` — unmerged lifts are invisible to worktrees), `target_paths` aren't dirty in a live agent worktree, + reports merge-debt severity. Returns `ok` + a BLOCK/CLEAR recommendation |
| `noctus.dev.findings(project_slug, category, entry, provenance)` | the durable findings-file discipline | hand-transcription of engineers' returned-as-text findings (fragmented across worktrees). Appends under one of the 5 canonical sections; drops the `_(none)_` placeholder on first real entry; resolves the slug across `projects/` + `products/*/projects/` + `core/projects/` |

## 4 · Relationship to the codification pipeline

These are the **Stage-4-as-tooling** layer for *process* shapes, the analogue of keeper `check_*` detectors for *code* shapes. `scaffold_keeper` is self-referential — it scaffolds the very Stage-4 artifact the pipeline (`KB § PATTERNS/common/methodology-codification-pipeline.md`) describes. Reach for a scaffolder/orchestration tool **before** hand-writing the shape or re-running the ritual; that reflex is the day-to-day token + consistency win the program was built for. MCP-first (`KB § 01-PHILOSOPHY.md § MCP-first`); registered under `noctus.dev.*` in `mcp/noctusai/tools/noctus/dev/`; durable index = memory `feedback_dev_orchestration_codegen_toolkit`.

---

## When this was added

Built 2026-05-18 (project `mcp-connector-expansion` tail), evidence-driven from that session's measured rewrite/ritual tax. Two verified increments: orchestration trio first (bounded git/subprocess wrappers), then the 4 codegen scaffolders; 21 colocated tests; all 7 register cleanly.
