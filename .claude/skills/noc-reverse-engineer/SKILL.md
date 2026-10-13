---
name: noc-reverse-engineer
description: Use when the owner wants to study an external app to build our own version — triggers "reverse engineer X", "map this app", "map everything in <app>", "do the same as we did for core studio", "understand how <SaaS> works", "engenharia reversa", "study <app> so we can build our own". Read-only, from the owner's own logged-in account, in owner-gated stages (map → data → mechanisms → synthesis); no build until the owner says "go all the way".
version: 1.0.0
---

# noc-reverse-engineer — study an external app, read-only, in stages

> Born from N=2: CoreStudio (2026-10-05/06, `products/social-wiring/projects/core-studio/`)
> and Lais (2026-10-13). For a long run, dispatch agent `reverse-engineer`; this skill is
> the procedure it (or you) follows.

🔴 **Two rules that end the study if broken.** (1) **Classify before you click** — READ /
SIDE-EFFECT-GET / WRITE / SEND; unknown ⇒ WRITE; only READ is exercised. (2) **Own ids only**
— never guess, increment or swap an id or tenant param (CoreStudio served other customers'
rows to a guessed id).

## Workflow

0. **Recover + place.** `noctus.dev.memory_search "<target>"` and read any prior study folder. Ask the owner which product the study belongs to → `products/<slug>/projects/<target>/` (CoreStudio's folder is the layout template). Work in a self-branched worktree (skill `noc-self-branch`) for anything committed; raw captures stay in the session scratchpad until redacted.
1. **Open + orient (S1).** Chrome: `tabs_context_mcp` → navigate to the app; if logged out, **stop and let the owner log in** (never type credentials). Record stack + hosts from `performance.getEntriesByType('resource')` and the CSP header (`curl -sI`).
2. **Routes.** Expand every menu; then grep the downloaded bundles for route strings — the bundle is the source of truth, the menu is a subset. Visit each route; record title, iframes, redirects (= gated) and the API calls it fires.
3. **Bundles (background).** Collect every chunk (per-route via a `__re_chunks` `localStorage` accumulator + the webpack runtime's async map), `curl` them into `scratchpad/<target>/js/`, then dispatch a background agent for static analysis: endpoints + method + safety class, service classes, zod/enum/MSW mocks, flags/permissions, integrations. Clean the `localStorage` key afterwards.
4. **UI layer.** Per page: screenshot (saved + copied as `NN-<page>.jpg`) + `get_page_text`; open only READ controls (tabs, accordions, filter drawers, view toggles). Persist `ui/ui-notes.md` after every batch. Embedded legacy apps: open the iframe URL top-level with the same params.
5. **Checkpoint S1** → report to the owner: page map, architecture, mechanisms seen, the "never call" list, open questions. **Wait** for the go to S2.
6. **S2 · Data** — fetch only read-only GETs on ids seen in the owner's UI (allowlist from step 3); bulk results leave the browser via an owner-approved download; redact; status table in `specs/xhr-to-fetch.md`. Checkpoint.
7. **S3 · Mechanisms** — `specs/mechanisms.md`: entities + relations, state machines, triggers, AI layer (prompts as `*-DRAFT.md`, never final), pricing unit, integrations. Checkpoint.
8. **S4 · Synthesis** — study doc + mapping to our seed/products + owner interview rounds (`AskUserQuestion`, options not decisions) → `DECISIONS.md`. Build only on "go all the way" (skill `noc-contract-first`).
9. **Learn.** Log what the procedure got wrong this run and fold it into the KB pattern (skill `noc-learn-refine`).

## Guardrails

- Never toggle, save, send, assign, archive, approve, connect OAuth, or start a test conversation on the target — even "just to see". Prefer already-read items (opening can mark read).
- Never bypass the target's CSP, auth, rate limits or plan gates. A gated route is recorded as gated.
- Downloads into the owner's machine need the owner's yes, per download.
- PII (leads, staff, chat text) and tokens never reach a committed file — summarise structure, redact samples.
- Evidence tags C / I / U on every claim; concepts are equal only by definition + real data.
- Browser JS output caps at ~1 KB; zsh doesn't word-split `$VAR`; prefer `find` refs over coordinates.

## Depth
`KB § PATTERNS/common/app-reverse-engineering.md` (stages, safety classes, techniques, gotchas, sensitivity) · template study: `products/social-wiring/projects/core-studio/README.md`.
