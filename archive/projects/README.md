# archive/projects/ — Off-Cycle Project Documents

Projects that are **explicitly out of every active batch** but that we want to
preserve so the design + reasoning isn't lost. Two reasons a project lands
here, not deleted:

1. **PARKED by user directive** — design is complete and signed off, but
   execution is held until the user un-parks. Reactivating means moving
   the folder back to its product-scoped location and following the
   project's own §7 "resume" gate.
2. **INFEASIBLE today** — concept-stage work that depends on an unblock
   trigger we don't have yet (a tool, a spec, a precondition). Re-check
   when the project's own §7 unblock-trigger conditions fire.

Everything in here is **not running**. No tier, no batch, no agent should
pick these up unless the user explicitly reactivates them.

## Current contents

| Folder | Origin | Why archived | Reactivation trigger |
|---|---|---|---|
| `pf-org-scoping-migration/` | `products/personal-finance/projects/` | PARKED 2026-04-27 by user directive ("leave for later"). | User explicitly resumes; then move back to `products/personal-finance/projects/`. |
| `narrow-read-compliance-detector/` | `projects/` (cross-product) | Concept stub marked INFEASIBLE — the detection problem requires AST-level cross-symbol reasoning we don't have a tool for today. | One of the §7 unblock triggers in the file fires (e.g., `noctusai_outline_python` ships symbol-graph traversal). |

## Reactivation protocol

1. Read the archived folder's `PROJECT.md` end-to-end.
2. Re-run any §7 audit / sign-off the project requires.
3. Move the folder back to its scope-correct location (`projects/<slug>/`,
   `products/<x>/projects/<slug>/`, or `core/projects/<slug>/`) — never
   execute work from inside `archive/`.
4. Log the reactivation in the project's §11 Change Log.
5. Resume per the canonical execution workflow.

## What does NOT live here

- **Closed projects** — those get the apply-inline-then-delete close
  protocol (`KB § PATTERNS/project-execution.md § 0`); their folder is
  deleted on close, audit trail lives in commit history + project §11
  while it existed + `KB § PATTERNS/accept-with-rationale.md` for any
  durable accept entries.
- **Active follow-up projects** — those live in `projects/<slug>/` (root
  cross-cutting), `products/<x>/projects/`, or `core/projects/` per the
  three-location rule.
- **Failed experiments** — if a concept failed cleanly, document it in
  `KB § PATTERNS/accept-with-rationale.md` § Active decisions and let
  the folder go.

This archive exists for ambiguity-resolved-but-execution-deferred
projects only. It is intentionally narrow.
