# Agent Packages — PROJECT

- **Created:** 2026-10-03
- **Status:** 🟡 wave 1 shipped (limiar-app consumes 0.2.0); wave 2 BE-API in progress
- **Owner / stakeholders:** João (owner) · orchestrator session (tech-lead) · engineers per slice
- **Contract:** `CONTRACT.md` (same folder) — binding
- **Related:** `../agent-studio-isaia/CONTRACT.md` (Studio, extended not changed) · consumer `jraphaelsst/limiar-app`
- **Decision record:** owner decisions taken 2026-10-03 on the Decision Board (claude.ai artifact) — mirrored in CONTRACT §A

## 1. Purpose
Agents usable in two places with identical context: Claude Code (primary, owner's plan) and Agent Studio
(secondary). One git package → one build → two surfaces; consumer projects sync their context and learnings
back on every push. First agents: `mobile-dev`, `nos-no-limiar`.

## 2. Seed-first analysis
1. Contract identical for every product? YES — any repo can consume packages (`agents.lock.json`).
2. Data source product-specific? NO — packages are generic; project context is a per-consumer collection.
3. Placement product-specific? It lives in `products/agents` (the agents registry is that product's job) +
   `noctus.dev.*` tools (MCP-first scripts).
4. Seam already exists? PARTLY — Studio import (§F), compiler, knowledge, evals exist; export, scopes,
   learnings, kind do not.
5. Default-on or opt-in? Opt-in per consumer (`agents.lock.json`).

## 3. Waves
| Wave | Slices | Exit criteria |
|---|---|---|
| 1 | **PKG-BUILD** (local build + pull from noc tree, no network) · **CONTENT** (both packages, IsaIA-style, with evals) | `agent_package_build mobile-dev` and `nos-no-limiar` produce Claude Code files identical in behaviour to the hand-written v0.1.0 in limiar-app; limiar-app switches to pulled files |
| 2 | **BE-API** (migration, importer additions, §I routes, scopes) · **HOOKS** (noc pre-push §F) | packages import + eval + publish to prod Studio on push; pull via API works with a scoped token |
| 3 | **FE-STUDIO** · consumer hook (§G, §H) | limiar-app push syncs docs/src/board/learnings; Studio chat answers with project context; Aprendizados tab reviews rows |

## 4. Implementation phases
### Phase 1 — Contract ✅
- [x] Owner decisions captured (Decision Board, 2026-10-03) and mirrored in CONTRACT §A
- [x] Studio facts verified in code: `compile_prompt` is pure over `CompileInput`; importer is strict Pydantic; product callers refused (403 `user_required`)
- [x] Contract v1 + slices + waves written

**Improvements:**
- Studio §A1 ("definitions never in git") had to be amended for a new kind — contracts that pin a storage
  decision should state its scope (which agent kinds) so later kinds can opt out explicitly.

### Phase 2 — Wave 1 ✅
- [x] PKG-BUILD: `noctus.dev.agent_package_build` + `noctus.dev.agent_pull` (local build; real `compile_prompt`; 22 fixture tests) — dev 46f591777
- [x] CONTENT: `mobile-dev` + `nos-no-limiar` 0.2.0 (sections · skills · knowledge · 10 evals each) — dev 38d498b30, fixes 3a6241973
- [x] limiar-app consumes both via `agent_pull` (pinned `agents.lock.json`); `check=` passes — limiar-app 2248a67

**Improvements:**
- The real-package smoke caught 3 content violations (doc `tipo`, provenance keys, learnings status annotations) that fixture tests could not — every build slice must smoke against real packages before closing.
- `agent_pull` does not remove consumer files outside the generated set (old hand-written `AGENT.md` was removed by hand) — acceptable for v1; a `--prune` list in the lock would make migrations clean.
- The mcp suite gate timed out at 89 s at integrate — not a measured green for the whole suite (fixture tests were green).

### Phase 3 — Wave 2
### Phase 4 — Wave 3 + live end-to-end (Studio chat with `nos-no-limiar` answering a question that requires limiar-app source)

## 5. Open questions
- Eval threshold for dev-advisors (Studio default `publicacao_limiar` or lower?) — decide when the first eval run exists.

## 6. Change log
| Date | Change | By |
|---|---|---|
| 2026-10-03 | Contract v1 + project created | orchestrator |
| 2026-10-03 | Wave 1 shipped; limiar-app on 0.2.0; BE-API (wave 2) dispatched | orchestrator |
