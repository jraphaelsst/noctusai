# Doc-staleness gate — stale docs fail CI

**What it is.** A deterministic, CI-blocking gate (`noctus.dev.doc_staleness`, keeper `check_doc_staleness`, CLI `--check-doc-staleness`) that makes "update the docs" a mechanical consequence of changing code, for ALL living docs — product READMEs/MASTER-PROMPTs, `CONTRACT.md`/`PROJECT.md`, the KB, `CLAUDE/`. Owner order 2026-10-19: *"Gate stale docs, so CI lets us know and we update docs and don't leave them stale never."*

## Why

Found stale the same day, all invisible to line-diffs and to `doc_to_code_drift` (embedding cosine, advisory): `products/agents/README.md` + `MASTER-PROMPT.md` ("scaffold only / PLANNED" over a live studio + 86 routes), the `02-LANDSCAPE.md` agents row (missing the SDR agent), `maya-blocks/CONTRACT.md` ("nothing implemented yet", migration "NOT applied" after S2–S4 shipped). Docs drift because only ONE side changes at a time — so the gate couples the sides.

## The four legs (extended, not parallel)

| Leg | Scope | Fails when |
|---|---|---|
| **Coupling** | a commit RANGE (`--doc-range BASE..TIP`; pre-push on a push to `dev`, CI `commit-range-keepers`) | code a doc covers changed **materially** (file added/removed, or a changed line adds/removes a route decorator / public `def`/`class`/`export` / `CREATE|ALTER TABLE`; arg churn and body edits do not count) and none of its covering docs changed |
| **Claims** | the tree | a living (non-`projects/`) doc cites a repo path that does not exist; a product README/MASTER-PROMPT says "scaffold only / planned, not built" while `backend/app` declares ≥3 routes; a `CONTRACT.md`/`PROJECT.md` says "nothing implemented" while ≥3 of its cited code paths exist (or ≥2 code commits name the project); a doc says migration `N_x.sql` is "NOT applied" while `migrations-applied.json` records it |
| **Ratchet** | the tree | a claim finding is NOT in `mcp/noctusai/tests/doc_staleness_baseline.json`. The baseline is the stale set that existed on 2026-10-19; it may only **shrink** (`--doc-baseline shrink` after fixing docs; `init` refuses when a baseline exists) |
| **Age** | the tree | never fails — warning list (covered code moved ≥40 commits AND ≥14 days past the doc's last touch) in the CI step summary |

Asleep products (`deploy/fleet/active-scope.txt`) are not checked — no gate checks an asleep product.

## Coverage is declared, never guessed

- Frontmatter `covers: [globs]` on any living doc (inline or `- item` list).
- Derived: `products/<slug>/README.md` and `MASTER-PROMPT.md` cover `backend/app/**`, `frontend/src/**`, `backend/migrations/*.sql`; a `CONTRACT.md` covers the code paths it cites.
- `STRUCTURAL_RULES` in `doc_staleness.py` for cross-cutting inventories (today: `02-LANDSCAPE.md` ← a router/studio/channel module **added or removed**). Add a rule when a roster-style doc needs its own coupling.

## Escape hatch (auditable, never silent)

A commit trailer in any commit of the range: `Docs-Reviewed: <doc path or glob> — <reason>` (reason mandatory; sibling of `Guide-Unaffected:`). `Docs-Reviewed` also resets the **age** clock for that doc.

## Compliance by construction

`--check-doc-staleness [--doc-range …] [--doc-suggest]` / MCP `noctus.dev.doc_staleness` print the exact docs to update and the false claims — fix-list, not just a red. Do not add to the baseline; fix the doc.

## Composes with

`doc_to_code_drift` (semantic advisory), `check_product_guide_cochange` (same trailer idiom, help-chat guide), `scan_live_state_claims` (live Supabase/prod facts), `kb_sync` (KB pointer resolution). → `KB § PATTERNS/common/doc-discipline-family-index.md`
