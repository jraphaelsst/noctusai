# Dispatcher Inbox

> **Purpose.** Architect (Session A) appends task entries below; Operator (Session B) consumes top-down and clears on completion. Coordination channel for the two-session architect/operator split — see `KB § PATTERNS/two-session-architect-operator.md`.
>
> **Lifecycle.** Architect appends to `## Pending`. Operator picks the top-most entry, executes, writes outcome to `dispatcher-outbox.md`, then moves the entry from `## Pending` to `## Completed (last 24h)` with a trailing status icon (`✅` / `❌`).
>
> **File status.** Gitignored — transient coordination state, not history. Project artifacts (PROJECT.md, findings.md, §11 Change Log) remain the durable record.
>
> **Entry format (level-3 heading):**
>
> ```
> ### YYYY-MM-DDTHH:MM — <SHORT-NAME>
> - Type: dispatch | cherry-pick | merge | push | archive | hound-scan | mole-sweep | kb-verify | other
> - Brief / SHA / path: <inline OR path to brief file>
> - Worktree / Branch / Target: <when applicable>
> - Acceptance: <what "done" looks like, verifiable>
> - Auto-execute: <yes | ask-first — default ask-first for destructive ops>
> ```

---

## Pending

<!-- Architect appends here. Operator consumes top-down. -->

---

## Completed (last 24h)

<!-- Operator moves entries here on completion. Anything older than 24h: delete or roll to a per-day archive file at architect's discretion. -->
