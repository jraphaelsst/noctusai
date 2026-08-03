# Methodology GC — retirement as a first-class leg

> **Rule:** every capture pipeline needs an exhaust. Promotion to an always-on surface (CLAUDE.md §1 · a keeper · `CLAUDE/<topic>.md`) RETIRES the memory index line that spawned it, same commit; `/gc` sweeps the strays on a monthly cadence and keeps the always-on surfaces inside their budgets.

## Why this exists

The methodology accumulated capture mechanisms for years — triage, auto-memory, `/codify`, the auto-improvement ledger, keepers — and zero decay mechanisms. The consequences were measured twice, a fortnight apart, and the second measurement is the interesting one.

**2026-07 audit.** `MEMORY.md` had reached 419 lines / 56 KB against a harness read that truncates; ~55% of the index — including `Active Project Decisions` — was silently invisible every session. 20/20 sampled §1 rules were *also* still indexed in `MEMORY.md`, so every promoted rule paid context twice, forever. §1 stood at 72 always-on rules.

**2026-08-03 re-audit.** `MEMORY.md` had been fixed by a different mechanism (the topic split — see `KB § PATTERNS/common/memory-index-topic-split.md`) and was down to 4 KB. But **§1 had grown from 72 to 79** in the same period, and the router keeper was green the whole time. The word budget had even been raised 2500→3500 to accommodate it, with a comment naming the real fix as a deferred follow-up.

That is the lesson, stated precisely:

> **A green gate on SHAPE does not bound ACCUMULATION.** Every §1 rule was individually well-formed — one line, a `→` pointer, under the word cap — and the file still grew past what a session can actually apply. Growth needs its own budget and its own exhaust, or the budget gets raised instead of the content getting consolidated.

## The mechanism (two legs, gate-methodology-sync compliant)

1. **By-construction leg** — `/codify` ends with retirement: a promoted entry's `MEMORY.md` pointer is retired rather than left to double-load.
2. **Backstop leg** — `/gc` (`.claude/commands/gc.md`) measures the budgets, retires strays, and proposes §1 family consolidations. The forcing function is `check_claude_md_router`'s rule-COUNT ceiling (hard cap 55, target 50): tripping it is a *consolidation* trigger, explicitly not an invitation to trim words or raise the cap.

## Family consolidation — the §1 exhaust

When ≥4 §1 rules share one framework, they collapse to **one family line** in §1 pointing at a **family-index KB doc** that holds the members **verbatim**.

Three invariants make this safe:

- **Verbatim move, never a summary.** The bytes in the family doc are the bytes that were in §1. A summary is lossy and forbidden — the whole point is that nothing is rewritten, only relocated.
- **Mechanically proven, not asserted.** The consolidation asserts that every original rule survives exactly once (still in §1, or verbatim in exactly one family doc). Per `KB § PATTERNS/common/lossless-doc-refactor.md`, a doc-set change is methodology surgery: prove it.
- **Only genuine families.** The test is "would a session that needs one member need the rest?" Rules that merely share a topic word do not qualify — and load-bearing standalone rules (seed-first, no-silent-errors, self-branching) stay standalone regardless of family size.

The 2026-08-03 pass consolidated five families — cache platform (6), orchestration & dispatch (9), knowledge lifecycle (5), doc discipline (8), learning posture (4) — taking §1 from **79 → 52 rules** and CLAUDE.md from **2727 → 2005 words**, which let the word cap be *restored* from the 3500 stopgap to its original 2500 rather than left ratcheted.

## Invariants

- **Learn-before-archive:** GC moves index lines, never deletes body files.
- **Verify-then-archive:** an entry is retired because the tree proves it resolved/promoted — never because it *looks* old.
- **GC ≠ codify:** GC never promotes; ripe candidates surfaced mid-sweep route to `/codify`.
- **Budgets are restored, not ratcheted.** After a consolidation, tighten the cap back to what the content now supports. A cap that only ever rises is not a budget.

## Consumers

`/gc` · `/codify` · `check_claude_md_router` (rule-count ceiling) · `check_memory_md_index` (advisory) · the family-index docs in `KB § PATTERNS/common/*-family-index.md`.
