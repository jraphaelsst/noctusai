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

Every product has its own `projects/` folder (even when empty, pinned with `.gitkeep`) — including core. Slugs are globally unique: a slug exists in exactly one of the three locations. The MCP tool (`noctusai_file_proposal`) resolves slugs by walking all three and picking the match — callers pass only the slug.

## What belongs at the root (here)

A project lives in root `projects/` when its scope is:

- **Cross-product** — touches two or more products (`ai-expansion`, `strict-mode-migration`).
- **Seed / platform infrastructure** — the shared lib, the framework, tooling (`multi-provider-llm`).
- **Migrating something not yet a product** into the platform (`adconnect-migration`).

If the project is scoped to a single product, move it under that product. If it is scoped to `core/` (auth, SSO, billing, orgs, entitlements), move it under `core/projects/`.

## Current root-level projects (snapshot 2026-05-03)

> Recently closed + deleted (2026-05-03): `methodology-extraction`, `llm-tool-call-audit`, `mcp-server-expansion`, `vista-api-mcp` (Phase 1 close; Phases 2-5 deferred per §7 Q6 reactivation triggers — see git history for the original PROJECT.md). Carry-forward projects: `mcp-server-fastmcp-switch` (mcp-server-expansion Phase 4+5); `whatsapp-seed-absorption` Phase 5 (llm-tool-call-audit Phase 4).

### ⏳ Active in-flight (work underway; next step well-defined)

| Slug | Title | Next concrete step |
|---|---|---|
| `absorbed-projects-batch` | Cross-cutting absorption batch coordinator | Tier 1.c → execute `scheduling-engine-seed` Phase 0; Tier 1.d → execute `whatsapp-seed-absorption` Phase 0 |
| `erp-schema-drift-deep-audit` | ERP-side schema-drift remediation | Phase 1 ✅ (profiles.org_id security fix); Phase 2 (11-table audit) awaits user §7 sign-off on org-scoping model |
| `repo-state-consolidation` | Pre-commit pre-flight gate consolidation | Phase 0 ✅ 2026-04-28; paused at user direction; resume Phases 1-3 (re-run gates) |
| `main-core-migrations-batch` | Core migrations batch coordinator | Phase 0 ✅; Tier 1 staleness audit on `repo-state-consolidation` required before Tier 1 phase work |

### 🟡 Phase-0-ready (scaffolded; awaits focused-session pickup)

| Slug | Title | Blocker |
|---|---|---|
| `scheduling-engine-seed` | Scheduler primitive absorption (folded cancellation/rescheduling sibling) | none — Phase 0 ready |
| `whatsapp-seed-absorption` | WhatsApp framework absorption + idempotency-keys | none — Phase 0 ready |
| `imobi-scheduling-bot-creation` | Imobi scheduling bot creation | downstream of `scheduling-engine-seed` + `whatsapp-seed-absorption` |
| `session-review-baseline` | Session-axis review (JSONL transcript detector) | filed-only per user directive; awaits explicit reactivation |
| `mcp-server-fastmcp-switch` | FastMCP runtime swap-out (carry-forward from mcp-server-expansion Phase 4) | Phase 0 ready |
| `mcp-tool-name-deprecation` | Alias retirement after dotted-naming bedded | blocked on `mcp-server-fastmcp-switch` Phase 5 close |

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
| `therapy-platform-wiring` | `products/therapy-platform/projects/therapy-platform-wiring/` | Design drafted — Phase 0 (api-call inventory) pending |

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
3. Synthesize ONE bundled proposal via `noctusai_file_proposal(project="<slug>", ...)` → lands in the project's own `proposals/` folder (resolver picks the correct location).
4. Flip the phase header icon to `✅`.
5. Run `python mcp/noctusai/cli.py --improvements <path-to-PROJECT.md>` to regenerate the retrospective.
6. Log the change in the project's §11 Change log.

## What lives elsewhere

- **Per-product docs** (MASTER-PROMPT, README) stay at `products/<product>/` root — product-level docs aren't projects.
- **Keeper / LGPD / evaluation proposals** go to `products/<product>/proposals/` — scoped to the product the detector flagged.
- **KB patterns / guides** stay in `KNOWLEDGE-BASE/CONTEXT/` — platform-wide reference docs, not projects.

See `KNOWLEDGE-BASE/CONTEXT/PATTERNS/proposals-and-improvements.md` for the full two-system protocol (improvements = log, proposals = queue) and `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md §1` for the two-location rule.
