# LGPD-WARNINGS.md — no unresolved entry is ever lost (keeper + merge driver)

> **Rule.** An unresolved `- [ ]` entry in `LGPD-WARNINGS.md` may be **ticked** (`- [x]`), **edited in place**, or left alone — never removed. Two parallel flags **merge cleanly** (an entry-aware git merge driver), and a commit that would drop an unresolved entry is **refused** (keeper), with a recorded-reason override.

## Why (incident 2026-10-10)

`noctus.dev.lgpd_flag` inserts every new entry at index 0, right after the header. Any two branches that each flag a concern insert at the **same anchor**, so git's text merge conflicts every time. Commit `7c2667c83` resolved exactly that conflict by **replacing** the core-transcription-API entry (added in `6698da2e5`) with a new biblioteca entry — two lines changed, one unresolved concern gone, nobody noticed until it was re-filed (`c12dfca47`). The file already said "Do not delete items"; nothing enforced it. Two layers fix it (by construction + backstop):

1. **Merge driver (by construction)** — parallel flags stop conflicting, so nobody hand-resolves the file.
2. **Keeper (backstop)** — a resolution that still loses an entry cannot be committed or pushed.

A third, latent bug surfaced on the way: `_ENTRY_RE` used `[^*]+` for the concern, so an entry whose concern contained a lone `*` (`pk_* tokens`) failed to parse, was swallowed into the "header", and `flag()` **dropped it on its next rewrite**. The regex is now lazy (`.+?` up to `** at `), block boundaries use a separate shape-agnostic `_ENTRY_START_RE`, and an unparseable-but-entry-shaped block is identified by its first line, so it cannot vanish either. `flag()` now shares `parse_warnings()` with the keeper and the driver — one parser.

## The keeper — `check_lgpd_entry_removal` (+ `_range`)

`mcp/noctusai/tools/noctus/dev/compliance.py`. **Identity = the `(concern, code_path)` pair** from `lgpd.py`'s own `_ENTRY_RE` (no second parser).

| Change | Verdict |
|---|---|
| tick `- [ ]` → `- [x]`; edit reason / mitigation / timestamps in place; add entries; remove an already-resolved entry | allowed |
| an unresolved base entry whose identity is absent afterwards (incl. editing its concern or path text = remove+add; deleting the file) | **refused**, every entry named in the message |

**Override** — a commit-message trailer, reason mandatory:

```
LGPD-Entry-Removed: <concern or path prefix, >= 6 chars> — <reason>
```

For a genuine duplicate or an in-place re-key. The separator is `—`, `–`, `--` or ` - `. A trailer with no reason, or a selector shorter than 6 characters (it would match everything), does not count. One trailer covers every refused entry whose concern or path starts with its selector.

**Where it runs (same rule, two legs):**

- **commit-msg** (`scripts/hooks/commit-msg`, `cli.py --check-lgpd-entry-removal --commit-msg-file …`) — the only hook that can read the message. Staged index vs `HEAD`; fires only when `LGPD-WARNINGS.md` is staged-different. Unlike the product-guide gate it also runs on a detached HEAD (a rebase conflict resolution is where an entry gets lost) and mid-merge, where it is merge-aware: against each parent, an entry absent from the merge-base is that side's *addition* and must survive; an entry present in the merge-base was the other side's own (keeper-governed) delete.
- **CI** (job `commit-range-keepers` in `.github/workflows/test.yml`, shared with the product-guide range leg; `cli.py --check-lgpd-entry-removal --lgpd-range BASE..TIP`) — every commit of the pushed / PR range vs its parent with **its own message**, so a clone without hooks cannot slip one through. Examined: non-merge commits touching the file, and every merge (a merge resolution is the incident class). A removal still present at the **range tip** is forgiven (removed then re-filed — otherwise the dev→main fast-forward carrying `7c2667c83` + `c12dfca47` would wedge the release on an already-healed incident). The incident commit itself was re-filed under a *new* concern text (`c12dfca47`), so tip-forgiveness cannot match it and commits are immutable: it sits in `_LGPD_ACCEPTED_HISTORICAL` (full sha → rationale) in `compliance.py`. An unresolvable range fails **closed**.

It is a commit-time / range keeper like `check_product_guide_cochange`, so it is not part of the whole-tree `check_all_products` aggregator (there is no "current state" violation to find — the file at HEAD is by definition consistent).

**Mutation proof** (`mcp/noctusai/tests/test_check_lgpd_entry_removal.py`): the fixtures `tests/fixtures/lgpd/{pre,post}-7c2667c83.md` are the real blobs of the incident. The keeper refuses that exact change; the same replay with the trailer passes; a tick and an in-place mitigation edit pass; the range leg refuses the replayed commit by sha and a merge commit that drops a branch's addition.

## The merge driver — `merge=lgpd-warnings`

Pure function `lgpd.merge_warnings(base, ours, theirs) -> (text, conflicted)`; CLI `cli.py --merge-lgpd-warnings BASE OURS THEIRS --out FILE` (exit 0 clean, 10 conflicted); thin shell `scripts/hooks/merge-lgpd-warnings.sh %O %A %B %P` (exit 0 clean / 1 conflicted; writes **only** `%A`, scratch file trapped on every exit — the same side-effect-free contract as `merge-kb-counts.sh`, see `KB § PATTERNS/common/auto-generated-merge-drivers.md`). `.gitattributes`: `LGPD-WARNINGS.md merge=lgpd-warnings`; registered in the per-repo git config by `scripts/hooks/install-hooks.sh` (a clone that has not run it degrades to git's default merge, never a hard break).

Semantics (entries keyed by identity + ordinal counted from the bottom, so a ticked entry and a re-flagged unresolved one with the same identity stay distinct):

- added on one side → kept; added on both → **all kept**; entries new relative to base go to the top **newest-first (flagged date desc, then identity)**, so the result does not depend on merge direction;
- changed on one side only → that side; changed identically on both → once;
- changed differently on both (or modified vs deleted) → standard conflict markers around **just that block**, `conflicted=True`;
- deleted on one side, unchanged on the other → deleted — the driver does **not** re-police deletes; the keeper does, at commit time;
- header: 3-way (a one-sided header edit is kept; both sides editing it differently conflicts around the header only).

`merge=union` is forbidden here: it duplicates or mangles multi-line blocks.

Tests: `mcp/noctusai/tests/test_lgpd_merge_driver.py` — pure cases including the exact `6698da2e5` vs biblioteca parallel add (both entries survive, direction-independent), and real-git tests where two branches each run `lgpd.flag(...)` with the driver configured (merge clean, rebase clean, a genuine conflict still surfaces markers, no scratch leftovers, missing CLI degrades to a conflict with `%A` untouched).

Related: `KB § PATTERNS/common/live-state-alignment.md` (the `Guide-Unaffected:` trailer this mirrors) · `KB § PATTERNS/security/lgpd.md` · `KB § PATTERNS/common/gate-methodology-sync.md` (a gate ships its by-construction mechanism same-commit).
