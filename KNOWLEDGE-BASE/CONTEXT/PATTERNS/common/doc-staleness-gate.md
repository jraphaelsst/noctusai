# Doc-staleness gate — stale docs fail CI

**What it is.** A deterministic, CI-blocking gate (`noctus.dev.doc_staleness`, keeper `check_doc_staleness`, CLI `--check-doc-staleness`) that makes "update the docs" a mechanical consequence of changing code, for ALL living docs — product READMEs/MASTER-PROMPTs, `CONTRACT.md`/`PROJECT.md`, the KB, `CLAUDE/`. Owner order 2026-10-19: *"Gate stale docs, so CI lets us know and we update docs and don't leave them stale never."*

## Why

Found stale the same day, all invisible to line-diffs and to `doc_to_code_drift` (embedding cosine, advisory): `products/agents/README.md` + `MASTER-PROMPT.md` ("scaffold only / PLANNED" over a live studio + 86 routes), the `02-LANDSCAPE.md` agents row (missing the SDR agent), `maya-blocks/CONTRACT.md` ("nothing implemented yet", migration "NOT applied" after S2–S4 shipped). Docs drift because only ONE side changes at a time — so the gate couples the sides.

## The legs (extended, not parallel)

| Leg | Scope | Fails when |
|---|---|---|
| **Coupling** | a commit RANGE (`--doc-range BASE..TIP`; pre-push on a push to `dev`, CI `commit-range-keepers`) | code a doc covers changed **materially** (file added/removed, or a changed line adds/removes a route decorator / public `def`/`class`/`export` / `CREATE|ALTER TABLE`; arg churn and body edits do not count) and none of its covering docs changed |
| **Commit** | the STAGED diff (`--doc-staged`; `scripts/hooks/commit-msg` BLOCKS, `pre-commit` prints the same fix-list early) | the same materiality + coverage rules as Coupling, evaluated on the commit being made: code a doc covers is staged materially and that doc is not staged. A `Docs-Reviewed: <doc> — <reason>` trailer in the message satisfies it (only commit-msg can read the message, so the block lives there). Skips merges and detached HEAD (rebase/cherry-pick replays). A worktree whose own `cli.py` predates `--doc-staged` is checked with the primary checkout's CLI (said on stderr), never aborted for a missing flag |
| **Claims** | the tree | a living (non-`projects/`) doc cites a repo path that does not exist; a product README/MASTER-PROMPT says "scaffold only / planned, not built" while `backend/app` declares ≥3 routes; a `CONTRACT.md`/`PROJECT.md` says "nothing implemented" while ≥3 of its cited code paths exist (or ≥2 code commits name the project); a doc says migration `N_x.sql` is "NOT applied" while `migrations-applied.json` records it |
| **Ratchet** | the tree | a claim finding is NOT in `mcp/noctusai/tests/doc_staleness_baseline.json`. The baseline is the stale set that existed on 2026-10-19; it may only **shrink** (`--doc-baseline shrink` after fixing docs; `init` refuses when a baseline exists) |
| **Age** | the tree | never fails — warning list (covered code moved ≥40 commits AND ≥14 days past the doc's last touch) in the CI step summary |

Asleep products (`deploy/fleet/active-scope.txt`) are not checked — no gate checks an asleep product.

## The rule: docs follow code, in the same commit, unprompted

Owner order 2026-11-04: *"make sure all documentations referring to anything in repo is updated upon code change, so I don't have to keep asking for docs update."* The agent updates every covering doc **in the commit that changes the code** (the Commit leg lists them the moment the commit is attempted), never waiting to be asked and never deferring to push time. Pre-push and CI (Coupling over the range) remain the backstop for commits made with hooks absent or `NOCTUS_SKIP_DOC_STALENESS` set. A doc the change genuinely does not affect gets the `Docs-Reviewed:` trailer instead.

## Coverage is declared, never guessed

- Frontmatter `covers: [globs]` on any living doc (inline or `- item` list).
- Derived: `products/<slug>/README.md` and `MASTER-PROMPT.md` cover `backend/app/**`, `frontend/src/**`, `backend/migrations/*.sql`; a `CONTRACT.md` covers the code paths it cites. Paths written relative to a base the contract declares ("Paths are relative to `products/<slug>/`") resolve against it, and only the ones that exist count. A bare product root (`products/<slug>`) is never a contract cover, because the README/MASTER-PROMPT already cover it. As a citation it coupled `sw-lead-to-contract/CONTRACT.md` to every SW change, so three unrelated Julia v2 branches each needed a `Docs-Reviewed:` trailer (fixed 2026-10-20). A contract that is mostly routes and cites few files declares its real scope as `covers:`.
- `STRUCTURAL_RULES` in `doc_staleness.py` for cross-cutting inventories (today: `02-LANDSCAPE.md` ← a router/studio/channel module **added or removed**). Add a rule when a roster-style doc needs its own coupling.

## Commit-time new-citation check (2026-11-05)

`check_staged` also runs `check_staged_new_missing_paths`: a staged living doc (not under `projects/`) that ADDS a backticked repo path which does not exist is refused at commit, with the fix. Only citations new in the staged text are judged; pre-existing debt in a doc you touch stays with CI's shrink-only tree ratchet. Before this, the claim check ran only in CI, so a typo'd citation surfaced ~25 min later as a queue ejection. The first catch was its own author's KB line citing a runtime-only file.

## Escape hatch (auditable, never silent)

A commit trailer in any commit of the range: `Docs-Reviewed: <doc path or glob> — <reason>` (reason mandatory; sibling of `Guide-Unaffected:`). `Docs-Reviewed` also resets the **age** clock for that doc.

## Compliance by construction

`--check-doc-staleness [--doc-staged [--commit-msg-file F] | --doc-range …] [--doc-suggest]` / MCP `noctus.dev.doc_staleness` print the exact docs to update and the false claims — fix-list, not just a red. Do not add to the baseline; fix the doc.

## Composes with

`doc_to_code_drift` (semantic advisory), `check_product_guide_cochange` (same trailer idiom, help-chat guide), `scan_live_state_claims` (live Supabase/prod facts), `kb_sync` (KB pointer resolution). → `KB § PATTERNS/common/doc-discipline-family-index.md`
