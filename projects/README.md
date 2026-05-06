# projects/ — Cross-Product & Platform Project Workspace

> **Root `projects/` is for cross-cutting work.** Single-scope projects live under `products/<product>/projects/<slug>/` or `core/projects/<slug>/`. See `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md §1` for the three-location rule.

## Layout

```
projects/                                   ← THIS FOLDER (cross-product / platform-infra)
  <project-slug>/
    PROJECT.md          ← living document (plan + execution log)
    improvements.md     ← auto-generated retrospective (regenerate via MCP CLI)
    proposals/          ← ONE bundled proposal per completed phase
      <agent>-<ts>-<slug>.md

products/<product>/projects/                ← single-product projects live here
  <project-slug>/
    PROJECT.md
    improvements.md
    proposals/

core/projects/                              ← core-platform-control-plane projects live here
  <project-slug>/
    PROJECT.md
    improvements.md
    proposals/
```

Every product has its own `projects/` folder (even when empty, pinned with `.gitkeep`) — including core. Slugs are globally unique: a slug exists in exactly one of the three locations. The MCP tool (`noctus.dev.file_proposal`) resolves slugs by walking all three and picking the match — callers pass only the slug.

## What belongs at the root (here)

A project lives in root `projects/` when its scope is:

- **Cross-product** — touches two or more products (`ai-expansion`, `strict-mode-migration`).
- **Seed / platform infrastructure** — the shared lib, the framework, tooling (`multi-provider-llm`).
- **Migrating something not yet a product** into the platform (`adconnect-migration`).

If the project is scoped to a single product, move it under that product. If it is scoped to `core/` (auth, SSO, billing, orgs, entitlements), move it under `core/projects/`.

## Current root-level projects (snapshot 2026-05-04)

> **Sweep this session (2026-05-04):** archived 6 projects to `archive/projects/2026-05-04/` —
> `metas-domain-seed-absorption` (NN 03; 27/27 ✅ closed 2026-05-03),
> `daily-life-goals-seed-wiring` (NN 04; 13/13 ✅),
> `erp-metas-seed-wiring` (NN 05; 25/25 ✅),
> `session-review-baseline` (NN 06; 5 phases ✅; harness live at `cli.py --review-session`),
> `dev-observability-bot-future-direction` (NN 07; design preserved in archive),
> `user-context-bot-future-direction` (NN 08; design preserved in archive).
>
> **Earlier closes (2026-05-03 + 2026-05-04 prior to this sweep):** `methodology-extraction`, `llm-tool-call-audit`, `mcp-server-expansion`, `vista-api-mcp` (Phase 1; Phases 2-5 deferred per §7 Q6 reactivation triggers), `scheduling-engine-seed` (lib at `noctusai_lib.domain.scheduling`; KB at `KB § PATTERNS/scheduling-seed.md`), `mcp-server-fastmcp-switch` (commits `dc5de6a` + `cf87f1d`), `mcp-tool-name-deprecation` (53 dotted dev tools; 0 flat `noctusai_<x>` remain), `whatsapp-seed-absorption`, `products-wiring-rollout`, `agno-dev-team-future-direction`, `erp-schema-drift-deep-audit`, `repo-state-consolidation`, `make-get-current-user-org-factory`, `media-scheduling-port`. See `git log` + `archive/projects/` for full history.

### 🟢 DONE — awaits orchestrator FF-merge to main (HIGH-LEVERAGE ACTIONABLE)

These projects are committed but on local branches; archive after the FF-merge lands.

| Slug | Branch | What's pending |
|---|---|---|
| `pf-metas-seed-wiring` | `pf-metas-seed-wiring` | Phase 0+1+2(collapsed)+3 ✅; branch awaits orchestrator fast-forward into `main` per [orchestrator-merges-to-main role](feedback_orchestrator_role.md). 16/19 sub-tasks (3 unchecked are §3a N/A litmus). |
| `seed-shadow-purge-helper-lift` | committed onto `findings-close-batch-1d` | Phases 1–5 ✅; helper lifted, 4 conftests rewired, 665+584+235+1819 tests green; final-commit + branch-push step un-ticked at line 254. |

### ⏳ Active in-flight (work underway; next step well-defined)

| Slug | Title | Next concrete step |
|---|---|---|
| `agno-dev-team-rollout` | Agno-based dev-team agent rollout | B0 + B1 ✅; engineer dispatch (8 parallel) imminent for B2. Most active root project. |
| `absorbed-projects-batch` | Cross-cutting absorption batch coordinator | Tier 1 in progress (22/65); Tier 2 ✅; Tier 4 confirmed deferred. |
| `main-core-migrations-batch` | Core migrations batch coordinator | Phase 0+1+2.a+3.a ✅ (Phase 1 Path B subsumed; Phase 2.a child re-scoped + filed standalone); Phase 3.a child §-progress in progress (19/57). |
| `in-flight-execution-rollout` | In-flight execution batch dispatcher | Phase 0 ✅ (filed); Phases 1+ orchestrator-driven (batch dispatch + sync-gates). Activates only when batches dispatch. |

### 🟡 Filed + ready for execution (scaffolded; awaits focused-session pickup)

| Slug | Title | Blocker |
|---|---|---|
| `ai-plumbing-seed-absorption` | AI plumbing absorption into seed | Phase 0 ✅ (12/15); Phase 1 ready — closest to a pickup-and-finish. |
| `strict-mode-migration` | TypeScript strict mode across all frontends | Phase 0 ✅ (3 findings inlined); Phases 1–4 ready for a separate agent / future session. |
| `imobi-scheduling-bot-creation` | Imobi scheduling bot creation | Design captured (15 phases planned, 0/73); Phase 0 awaits user trigger + slug confirmation. |

### 🔵 Awaits user input (cheap to unblock — minutes from you)

| Slug | Title | Gate |
|---|---|---|
| `erp-org-scoping-completion` | ERP org-scoping model completion | Phase 0 ✅ (audit landed); Phase 1+ awaits user §7 design-decision sign-off. |
| `project-history-ledger` | Long-term project ledger (audit trail across closed projects) | §1, §2, §5 (sketch), §7 populated; §6 intentionally empty — interrogation pending. |

### 🅿️ Parked on dependency

| Slug | Title | Gate |
|---|---|---|
| `send-message-consolidation` | N=2 `send_message` collision → seed-lib `send_text` consolidation | gated on `whatsapp-seed-absorption` Phase 1 (canonical `noctusai_lib.integrations.whatsapp.send_text()` must exist). 1/24. |

### 📦 Filed product migration (no execution scheduled; substantive plan exists)

| Slug | Title | Status |
|---|---|---|
| `adconnect-migration` | AdConnect B2B marketplace migration into seed framework | Full domain spec (99 sub-tasks); 1/99 done; not yet a phase-structured PROJECT.md. |

## Product-scoped projects (not here)

| Slug | Lives at | Status |
|---|---|---|
| `erp-metas` | `products/erp-imobiliario/projects/erp-metas/` | ✅ All 11 phases shipped |
| `vista-crm-wiring` | `products/erp-imobiliario/projects/vista-crm-wiring/` | ✅ All 4 phases shipped 2026-05-02 |
| `erp-imobiliario-wiring` | `products/erp-imobiliario/projects/erp-imobiliario-wiring/` | Scaffolded 2026-05-03 — Phase 0 runs in lockstep with PF P0 in master batch B0 (parent: `products-wiring-rollout` parallel-batch model; serial-gate removed 2026-05-03) |
| `therapy-platform-wiring` | `products/therapy-platform/projects/therapy-platform-wiring/` | Design re-aligned 2026-05-03 — Phase 0 ready (pilot for the wiring methodology; input to `products-wiring-rollout`) |
| `therapy-scheduling-pilot` | `products/therapy-platform/projects/therapy-scheduling-pilot/` | PARKED — second-consumer placeholder for `noctusai_lib.domain.scheduling`; scaffolded 2026-05-03 |
| `personal-finance-wiring` | `products/personal-finance/projects/personal-finance-wiring/` | Scaffolded 2026-05-03 — interrogation pending → Phase 0 ready (parent: `products-wiring-rollout`) |

## Starting a new project

1. Pick the slug per `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md §8` (`<subject>-<intent>`).
2. Pick the location per §1 — this folder for cross-cutting, `products/<product>/projects/` for single-product scope, `core/projects/` for core-control-plane scope.
3. `cp templates/PROJECT-TEMPLATE.md <chosen-location>/<slug>/PROJECT.md`.
4. Fill placeholders (name, context, phases).
5. Interrogate the user before finalizing §2 Confirmed constraints.
6. Commit with the first code change that lands under the new project.

## Finishing a phase

1. Every sub-task ticked (`- [x]`).
2. Phase's `**Improvements:**` block populated with in-flow bullets.
3. Synthesize ONE bundled proposal via `noctus.dev.file_proposal(project="<slug>", ...)` → lands in the project's own `proposals/` folder (resolver picks the correct location).
4. Flip the phase header icon to `✅`.
5. Run `python mcp/noctusai/cli.py --improvements <path-to-PROJECT.md>` to regenerate the retrospective.
6. Log the change in the project's §11 Change log.

## What lives elsewhere

- **Per-product docs** (MASTER-PROMPT, README) stay at `products/<product>/` root — product-level docs aren't projects.
- **Keeper / LGPD / evaluation proposals** go to `products/<product>/proposals/` — scoped to the product the detector flagged.
- **KB patterns / guides** stay in `KNOWLEDGE-BASE/CONTEXT/` — platform-wide reference docs, not projects.

See `KNOWLEDGE-BASE/CONTEXT/PATTERNS/proposals-and-improvements.md` for the full two-system protocol (improvements = log, proposals = queue) and `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md §1` for the two-location rule.
