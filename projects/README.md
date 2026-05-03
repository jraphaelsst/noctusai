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

## Current root-level projects (snapshot 2026-05-03)

> Recently closed + deleted (2026-05-03): `methodology-extraction`, `llm-tool-call-audit`, `mcp-server-expansion`, `vista-api-mcp` (Phase 1 close; Phases 2-5 deferred per §7 Q6 reactivation triggers — see git history for the original PROJECT.md), `scheduling-engine-seed` (lib landed at `noctusai_lib.domain.scheduling`; KB doc at `KB § PATTERNS/scheduling-seed.md`; therapy-scheduling-pilot scaffolded as second-consumer follow-up), `mcp-server-fastmcp-switch` (Phase 4 vendor ports + Phase 5 verification — commits `dc5de6a` + `cf87f1d`; carry-forward of `mcp-server-expansion` Phase 4+5 now satisfied). Carry-forward projects remaining: `whatsapp-seed-absorption` Phase 5 (llm-tool-call-audit Phase 4). Folder removed in working tree pending commit: `repo-state-consolidation` (deletions staged 2026-05-03).

### ⏳ Active in-flight (work underway; next step well-defined)

| Slug | Title | Next concrete step |
|---|---|---|
| `absorbed-projects-batch` | Cross-cutting absorption batch coordinator | Tier 1.c → execute `scheduling-engine-seed` Phase 0; Tier 1.d → execute `whatsapp-seed-absorption` Phase 0 |
| `erp-schema-drift-deep-audit` | ERP-side schema-drift remediation | Phase 1 ✅ (profiles.org_id security fix); Phase 2 (11-table audit) awaits user §7 sign-off on org-scoping model |
| `main-core-migrations-batch` | Core migrations batch coordinator | Phase 0 ✅; Tier 1 staleness audit pending (note: `repo-state-consolidation` folder retired in working tree — see top footnote; coordinator may need its blocker text updated by the project's owner agent) |

### 🟡 Phase-0-ready (scaffolded; awaits focused-session pickup)

| Slug | Title | Blocker |
|---|---|---|
| `whatsapp-seed-absorption` | WhatsApp framework absorption + idempotency-keys | none — Phase 0 ready |
| `imobi-scheduling-bot-creation` | Imobi scheduling bot creation | downstream of `scheduling-engine-seed` + `whatsapp-seed-absorption` |
| `session-review-baseline` | Session-axis review (JSONL transcript detector) | filed-only per user directive; awaits explicit reactivation |
| `mcp-tool-name-deprecation` | Alias retirement after dotted-naming bedded | **unblocked 2026-05-03** — `mcp-server-fastmcp-switch` Phase 5 closed; Phase 0 audit ✅; Phase 1 (consumer-class migration) ready |
| `send-message-consolidation` | N=2 `send_message` collision (ERP + therapy WhatsApp) → seed-lib `send_text` consolidation | blocked on `whatsapp-seed-absorption` Phase 1 (lib must exist) |
| `products-wiring-rollout` | Cross-product wiring sweep coordinator (PF + ERP in **parallel batches**; therapy = input/pilot) | scaffolded 2026-05-03 + restructured same day to parallel-batch model (`KB § PATTERNS/master-tree-parallel-batches.md`); §7 closed; B0 dispatch in flight |

### 🔵 Concept-stage / interrogation pending

| Slug | Title | Gate |
|---|---|---|
| `project-history-ledger` | Long-term project ledger (audit trail across closed projects) | §7 user interrogation pending before Phase 0 |
| `adconnect-migration` | AdConnect B2B marketplace migration into seed framework | Product description only; no PROJECT.md phase structure yet |

### ⚪ Future-direction / deferred (design only — no execution scheduled)

| Slug | Title | Status |
|---|---|---|
| `agno-dev-team-future-direction` | Agno-based dev-team agent system | Deferred; design preserved |
| `dev-observability-bot-future-direction` | Dev observability bot | Deferred; design preserved |
| `user-context-bot-future-direction` | User context bot | Deferred; design preserved |
| `strict-mode-migration` | TypeScript strict mode across all frontends | Deferred to v2.4 stabilization |

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
