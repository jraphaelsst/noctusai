# Auto-generated content → git merge drivers (don't hand-resolve machine churn)

> **Principle.** A file region that is **deterministically (re)generated from the tree** must never be hand-resolved on merge/rebase. Two parallel branches mutate the same generated region → git's default 3-way text merge reports a conflict on pure machine churn. The fix is a `.gitattributes` merge driver matched to the region's *shape*, codified at the root — never a per-occurrence manual resolution (a recurring gate is a fix, not a chore → `KB § PATTERNS/common/methodology-execution-discipline.md`).

## Two shapes, two drivers

| Generated shape | Conflict cause | Correct driver | Why |
|---|---|---|---|
| **Append-only log** (`project-history/*.ndjson` — vector-costs, auto-improvement, absorptions, branch-tree) | each branch appends DISTINCT lines to the tail | built-in **`merge=union`** | keeps BOTH sides' lines, no markers — appends never conflict. Codified 2026-05-30. |
| **Derived block** (`<!-- kb-counts:start:X -->…:end:X -->` inventory tables in `02-LANDSCAPE.md` / `06-AGENTS.md` / `AGENT-CONTEXT.md`) | each branch bumps the SAME row/grand-total (file & line tallies) | custom **`merge=kb-counts`** → `scripts/hooks/merge-kb-counts.sh` | `union` is WRONG (duplicates table rows). Instead **re-derive** the block from the merged tree. Codified 2026-06-05. |

**The discriminator:** is the conflicting region *accumulated* (append) or *recomputed* (derive)? Union for the first; regenerate for the second.

## The regenerating driver (derived blocks)

`scripts/hooks/merge-kb-counts.sh` (git invokes `driver %O %A %B %P`):

1. write git's merge result (`%A`) to the real path (`%P`);
2. run `cli.py --update-kb-counts` → regenerates every `kb-counts` block deterministically from the tree, overwriting the churn (and any conflict markers that sat *between* the start/end markers);
3. **marker guard** — if `<<<<<<<`/`=======`/`>>>>>>>` remain (a genuine PROSE edit conflict *outside* the blocks), restore `%A` and **exit 1** so git surfaces the real conflict; else hand back the clean file and exit 0.

Counts-only churn → silently correct. Real prose conflict → still surfaced. The safety hinge: `update_kb_counts` only rewrites the **delimited block**, never the whole file (`mcp/noctusai/tools/kb_sync.py`).

## Why not `merge=ours` / why not stop stamping

- **`merge=ours` (keep one side)** is unsafe for `02-LANDSCAPE.md` / `CLAUDE.md`: they mix generated blocks with **hand-written prose** → `ours` would silently drop a real concurrent prose edit. The regenerating driver + marker-guard preserves prose conflicts.
- **Stop auto-stamping counts per-commit** would re-open the 2026-06-01 "count regen left dirty → blocks `task_branch` integrate" recurrence, and would also strand the roster-row structural sync the `check_kb_sync` keeper depends on (product-add must update the roster). The driver leaves the per-commit stamp intact and fixes only the *merge* surface.

## Wiring (driver = local git config, NOT committable)

`.gitattributes` (committed) maps the path → driver name; the driver body is per-repo git config, so `scripts/hooks/install-hooks.sh` registers it:

```sh
git config merge.kb-counts.name   "regenerate auto-derived kb-counts blocks; surface real prose conflicts"
git config merge.kb-counts.driver "$REPO_ROOT/scripts/hooks/merge-kb-counts.sh %O %A %B %P"
```

A clone that hasn't run `install-hooks.sh` degrades gracefully to the default merge (the old conflict) — never a hard break. Fresh clone: `bash scripts/install-hooks.sh`.

## When you add a new auto-generated surface

1. Decide the shape (append vs derive).
2. Add the `.gitattributes` line (`merge=union` or `merge=<regen-driver>`).
3. Append-only → done (union is built in). Derived → author/extend a regenerating driver + register it in `install-hooks.sh` + run it now.
4. Codify here + memory; keep `.gitattributes` ↔ `install-hooks.sh` ↔ this doc in sync.

Related: `KB § PATTERNS/common/branching.md` (integrate cleanly) · `KB § PATTERNS/common/methodology-execution-discipline.md` (recurring gate → root fix) · `KB § PATTERNS/architect/noc-graph.md` (committed `graph.json` + merge driver, same family).
