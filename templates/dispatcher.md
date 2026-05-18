# Dispatcher — two-session architect↔operator coordination

> **Canonical template.** This committed file is the single source of structure for the live `.claude/dispatcher.md` (which is **gitignored** — transient coordination state, ¬ history). Bootstrap: `mkdir -p .claude && cp templates/dispatcher.md .claude/dispatcher.md`. Evolve the pattern by editing THIS file. Durable record = PROJECT.md / findings.md / §11 / `project-history/ledger.ndjson`. See `KB § PATTERNS/two-session-architect-operator.md`. Symbol-first per `KB § PATTERNS/doc-symbology.md` (AI-scaffolding).
>
> **Inbox** = architect→operator (`## Pending` / `## Completed`). **Outbox** = operator→architect (`## Outbox`, append-only). The `check_dispatcher_staleness` keeper parses `## Pending` (level-3 entries >24h → flagged).
>
> **Pending entry format (level-3 — detector-parsed):**
> ```
> ### YYYY-MM-DDTHH:MM — <SHORT-NAME>
> - Type: dispatch | cherry-pick | merge | push | archive | hound-scan | mole-sweep | kb-verify | other
> - Brief / SHA / path · Worktree / Branch / Target · Acceptance (verifiable) · Auto-execute (default ask-first for destructive ops)
> ```

---

## Pending

<!-- Architect appends here. Operator consumes top-down; appends ` ✅` / ` ❌ <reason>` then moves to ## Completed. -->

---

## Completed (last 24h)

<!-- Operator moves done entries here. >24h: delete or roll to `.claude/dispatcher-archive/<date>.md` at architect discretion. -->

---

## Outbox (operator → architect — append-only audit)

<!-- Operator appends one structured entry per drained task; architect reads top-down next turn. -->
