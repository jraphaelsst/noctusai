---
name: noc-archive-absorb
description: Use at EVERY teardown / archive / close-out moment — triggers "archive this project", "close out findings.md", "delete the worktree", "we're done with this project", "clean up the project folder", "absorb the findings". The two-leg gate — absorption (learnings → durable homes) + recovery pointer — BEFORE anything is archived or deleted.
version: 1.0.0
---

# noc-archive-absorb — nothing durable dies in an archive

🔴 **The loss this kills:** findings.md / PROJECT.md decisions / proposals vanish into `archive/` unread; a worktree with un-salvaged learnings gets deleted; six weeks later the same lesson is re-learned at full price. Archive is a MOVE of the residue, never the FATE of the knowledge.

## Workflow

1. **Absorb-on-contact first (the cheap path)** — the discipline is absorb AS insights surface, not at teardown: a findings.md entry naming a pattern → KB the same commit; a "we should always X" decision → memory entry or KB pattern now; a new agent/skill/tool the project shipped → registered in its harness home BEFORE archive. If this ran all project, step 2 is a no-op checklist.
2. **At-teardown checklist (the safety net)** — before `noctus.dev.archive <slug>` or ANY worktree removal:
   - `findings.md`: every slip/error/lesson/knowledge entry codified to a durable home (mark IN-FLIGHT-PROCESSED) or surfaced as a follow-up with a named destination.
   - `PROJECT.md` §11 live-patterns-log: every concrete decision absorbed OR cataloged in accept-with-rationale.
   - `proposals/*.md`: same rule.
3. **Record the recovery pointer** — `project-history/worktree-salvage.ndjson` or `ledger.ndjson` row (branch + SHA + one-line what-was-there). For worktrees, `noctus.dev.salvage_before_delete` / `task_branch action=cleanup` carry this leg mechanically.
4. **Only then archive/delete** — `noctus.dev.archive <slug>` / worktree removal.
5. **Memory index discipline** — a new memory entry from the absorption is one line appended to the matching `MEMORY-<topic>.md`, **never to `MEMORY.md`**. `MEMORY.md` is a router of TOPICS: it is auto-loaded AND read-capped (~24.4 KB), and past the cap the read returns *nothing*, so a pointer added there can silently cost you the whole index. → `KB § PATTERNS/common/memory-index-topic-split.md`

## Guardrails
- ⚠️ "Archive now, absorb later" is the anti-pattern this skill exists for — later never comes; the archive IS the absorb deadline.
- ⚠️ Deleting a worktree without the salvage leg trips learn-before-archive; the tools carry the pointer leg mechanically — use them instead of raw `rm`/`git worktree remove`.
- Both legs are required: absorption without a recovery pointer loses the trail; a pointer without absorption preserves residue nobody will re-read.

## Depth
`KB § PATTERNS/common/persistent-files-absorption.md` (canonical home — durable destinations, triggers, checklist) · `KB § PATTERNS/common/learn-before-archive.md` (the salvage gate + 5 preserve-categories + enforcement ladder) · `KB § PATTERNS/common/methodology-gc.md` (the retirement sibling — same learn-before-archive invariant applied to MEMORY.md) · `KB § PATTERNS/common/storage-hygiene.md` §2.3 (recovery-pointer mechanics).

Born from N≥2 recurrence: two §1 rules + a tool existed but the close-out procedure had no skill; `noc-hygiene` step 4 covered only the salvage half (2026-07 harness audit, landed 2026-08-03).
