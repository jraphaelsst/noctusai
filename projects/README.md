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

## Current root-level projects

| Slug | Title | Status |
|---|---|---|
| `multi-provider-llm` | Multi-Provider LLM Platform (seed/platform-infra) | ✅ Phases 1–16 shipped |
| `ai-expansion` | Cross-product AI opportunity atlas | ⏳ Phase 1 done · Phase 2 user triage pending |
| `adconnect-migration` | AdConnect B2B marketplace migration into the seed framework | ⏳ Scaffolded, not yet migrated |
| `strict-mode-migration` | TypeScript strict mode across all frontends | ⏳ Deferred |

## Product-scoped projects (not here)

| Slug | Lives at | Status |
|---|---|---|
| `erp-metas` | `products/erp-imobiliario/projects/erp-metas/` | ✅ All 11 phases shipped |
| `therapy-platform-wiring` | `products/therapy-platform/projects/therapy-platform-wiring/` | Design drafted — Phase 0 pending |

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
