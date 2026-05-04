# live-patterns-log.md — agno-dev-team-rollout

> **Purpose.** Append-only log of meaningful findings from any engineer during any batch. The shared scratchpad through which parallel engineers cross-pollinate. Per `KB § PATTERNS/master-tree-parallel-batches.md § 3.1`.
>
> **Read protocol.** Engineers read on every meaningful pause + before walking away from any file they edit. Master reads at every sync-gate.
>
> **Write protocol.** Append-only. One row per finding. Promote N≥2 entries to `cross-product-absorption-catalog.md` at sync-gates.

| Timestamp | Batch | Engineer | Finding | Suggested action |
|---|---|---|---|---|
| 2026-05-04 | B0 | orchestrator | (master init — log seeded) | — |
| 2026-05-04 | B0 | orchestrator | agno on PyPI at 2.6.4; Python 3.14.2 on system; MCP requires_python>=3.10 — compatible. | proceed with agno 2.6.4 in B1 deps. |
| 2026-05-04 | B0 | orchestrator | noctusai_lib has config/{settings,credentials}.py, primitives/{timeutil,roles,parsing,_correlation,exceptions,responses}.py, testing/{mocks,clients,assertions,...}.py — all consumption targets exist. | dev_team imports `from noctusai_lib.config.settings import …` directly; no shim needed. |
| 2026-05-04 | B0 | orchestrator | MCP server hierarchical registration: `tools/__init__.py::register_all` → `noctus.register_all` → `dev.register_all` → per-module `register(server)`. Sub-folders supported (`google/calendar/`, `google/maps/`). | mirror `google/calendar/` shape for `noctus/team/`. |
| 2026-05-04 | B0 | orchestrator | **Naming correction.** Originally planned `noctus.dev.team.{run,status,route}` (4 segments, violates `KB § PATTERNS/mcp-tool-conventions.md § 1`). Corrected to `noctus.team.{run,status,route}` — `team` becomes a new sub-service under `noctus`, parallel to `dev` and `business`. | PROJECT.md updated; tools land at `mcp/noctusai/tools/noctus/team/`. |
| 2026-05-04 | B0 | orchestrator | MCP `tools/noctus/__init__.py::register_all` will need to call `team.register_all(server)` alongside `dev.register_all(server)`. | B4 engineer touches both `tools/noctus/__init__.py` and the new `tools/noctus/team/` folder. |
| 2026-05-04 | B2 | engineer-D | `configs/__init__.py` already ships an 11-agent stub fallback — the loader's real `list_configs()` strips the stub when YAML files exist. Means consumer code can `from dev_team.configs import load_config` BEFORE D ships and still get a valid 11-agent dict — the cutover happens automatically when `loader.py` lands. | Pattern worth promoting to other engineer scopes: stub-then-cut-over via try-import in the contract `__init__.py`. Already in B1 — flag as the canonical shape for B2/B3 contract cutover. |
| 2026-05-04 | B2 | engineer-D | `_config_uses_provider()` + `ANTHROPIC_API_KEY` guard ONLY fires when the default builder is in use. With injected `team_builder`, the eval harness runs without API keys — DI doubles as the test-mode switch (no `monkeypatch` of our own code needed). | Same DI pattern is reusable for any future eval/runner that wraps `team.run`. Flag for E (team factory) + B (any agent-instantiation entrypoints): accept `team_builder` / `agent_builder` as a keyword for testability. |
| 2026-05-04 | B2 | engineer-D | Worktree `agent-a54da492b66f44cdf` was based on `85789c9` (pre-B1-scaffold). Had to `git merge --ff-only b178535` to grab the dev_team scaffold before any work could land. Suggests the dispatcher created worktrees before the scaffold commit was on the worktree base — base-branch should be `agno-dev-team-rollout` (currently at b178535) for all B2 engineers. | Worktree-creation step in master-tree dispatch should explicitly base-branch on the rollout branch, not on stale main/origin/main. Add to `KB § PATTERNS/master-tree-parallel-batches.md` as a setup-gate rule. |
