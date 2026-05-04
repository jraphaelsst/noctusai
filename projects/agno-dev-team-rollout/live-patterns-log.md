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
