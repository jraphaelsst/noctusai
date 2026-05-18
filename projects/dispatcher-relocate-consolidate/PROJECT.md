# PROJECT — dispatcher-relocate-consolidate

## §1 · Context (zero-context-reader framing — prose)

The two-session architect/operator pattern coordinates via `dispatcher-inbox.md` + `dispatcher-outbox.md` **at the repo root**. Repo-root placement violates the clean-folder principle, and the two-file split is heavier than needed. This project relocates them off-root into one consolidated file. It is filed (not done inline) because the change ripples through a **codified keeper detector** + its tests — a rushed wrap-up edit would silently break `check_dispatcher_staleness` (no-quick-fixes / doc-code-coherence).

## §2 · User ask (verbatim — prose, NOT symbol-compressed)

> "place these on their appropriate path, it's not on the root. And maybe we could have 1 file stating both inbox and outbox. then commit and push so we can wrap up this session"

(Raised 2026-05-18 while extending symbol-first scope to AI scaffolding; the dispatcher coord-file is one of those classes.)

## §3a · Seed-first analysis

N/A — not product code; pure platform/methodology + MCP-detector change. No seed seam involved.

## §4 · Design decision

- New single file: **`.claude/dispatcher.md`** (`.claude/` already holds Claude-local state — worktrees, agents; keeps repo root narrow). Two H2 sections: `## Inbox (architect → operator)` ∧ `## Outbox (operator → architect)`. Inbox = `## <task-id>` task entries (unchanged shape); Outbox = append-only audit entries (unchanged shape).
- Gitignore: `.claude/dispatcher.md` gitignored whole (currently only `dispatcher-outbox.md` is — inbox was effectively tracked; consolidating ⇒ ignore the unified file; confirm operator-outcome audit need vs git-history).
- Symbol-first: the new file is AI-scaffolding ⇒ authored symbol-first per `KB § PATTERNS/doc-symbology.md §2`.

## §5 · Files to touch (doc-code-coherence — ALL in one commit)

**Code + tests (the risk surface — do first, test green before docs):**
- `mcp/noctusai/tools/noctus/dev/compliance.py` — `_DISPATCHER_INBOX_FILENAME` const → new path; the untracked-hygiene list entry `dispatcher-outbox.md`; `check_dispatcher_staleness` `## Pending` parse (now a section *within* the unified file, not a whole file).
- `mcp/noctusai/tests/test_compliance_hygiene.py` — all `dispatcher-inbox.md`/`dispatcher-outbox.md` fixtures → unified path + section-scoped parse.

**Config:** `.gitignore` (L67-71 block — replace `dispatcher-outbox.md` with `.claude/dispatcher.md`).

**Docs (three-way + coherence):** `.claude/agents/orchestrator-operator.md` (≥6 refs: read inbox / append outbox / edit-in-place — now section-scoped) · `CLAUDE.md` §3 two routing rows (L163, L174) · `KB § PATTERNS/two-session-architect-operator.md` · `KB § PATTERNS/autonomous-operator-via-subagent.md` (flow diagram + steps) · `KNOWLEDGE-BASE/INDEX.md` (2 tree + 2 table lines) · `products/erp-imobiliario/MASTER-PROMPT.md` L127 (`check_dispatcher_staleness` ref) · `KB § PATTERNS/doc-symbology.md` §2 (drop the "filed follow-up" parenthetical, set final path) · memory `feedback_symbol_first_authoring` + `feedback_doc_symbology` (same).

**Live files:** `git mv`/relocate current `dispatcher-inbox.md` (1.4KB, has content) + `dispatcher-outbox.md` (14KB, gitignored) → merged into `.claude/dispatcher.md` under the two sections (preserve outbox history).

## §6 · Phases

- [x] **P1** ✅ — detector + tests (compliance.py + test_compliance_hygiene.py); 19/19 green.
- [x] **P2** ✅ — unified gitignored `.claude/dispatcher.md` (Pending/Completed/Outbox, 14KB history preserved) + `.gitignore` + `templates/dispatcher.md` bootstrap.
- [x] **P3** ✅ — doc-coherence sweep (9 surfaces — 2 beyond §10 inventory, fix-on-contact); residual grep zero-actionable; verify-kb-sync ✓; symbology-drift 0.
- [x] **P4** ✅ — doc-symbology §2 path finalized (filed-follow-up parenthetical resolved); memory; project archived.

## §7 · Acceptance

`grep -rn "dispatcher-inbox.md\|dispatcher-outbox.md"` (excl. `archive/`, `.claude/worktrees/`) = 0 · `check_dispatcher_staleness` green on the new section-scoped path · `test_compliance_hygiene.py` green · `verify-kb-sync.sh` ✓ · `check_doc_symbology_drift` 0 · `.claude/dispatcher.md` carries both sections + prior outbox history.

## §10 · Reference inventory (copy-paste — gathered 2026-05-18, saves re-discovery)

```
compliance.py:3012  _DISPATCHER_INBOX_FILENAME = "dispatcher-inbox.md"
compliance.py:3023-3028  untracked-hygiene allowlist incl. "dispatcher-outbox.md"
compliance.py:3116  check_dispatcher_staleness (## Pending parse)
compliance.py:3315  untracked-stay note
test_compliance_hygiene.py:90,103,144,149,262,276,284,301  fixtures
.gitignore:67-71  dispatcher-outbox.md block
.claude/agents/orchestrator-operator.md:3,13,19,23,70,88  refs
CLAUDE.md:163,174  §3 routing rows
KB/INDEX.md:61,62,154,155  tree+table
KB autonomous-operator-via-subagent.md:3,35,53  refs
KB two-session-architect-operator.md  (inbox+outbox at repo root)
products/erp-imobiliario/MASTER-PROMPT.md:127  check_dispatcher_staleness
```

## §11 · Change log

- 2026-05-18 — filed (deferred from session wrap-up; out-of-safe-scope to rush — touches a codified keeper + tests; full inventory captured for a single-pass next session).
- 2026-05-18 — **executed (single pass).** P1: `_DISPATCHER_INBOX_FILENAME`→`_DISPATCHER_FILE_RELPATH=".claude/dispatcher.md"` + `_EXPECTED_GITIGNORE_PATHS` updated + docstrings; `test_compliance_hygiene.py` fixtures → `.claude/dispatcher.md` (mkdir). P2: built unified gitignored `.claude/dispatcher.md` (Pending/Completed/Outbox; 14KB outbox history preserved); `git rm` tracked inbox, `rm` outbox; `.gitignore` `dispatcher-outbox.md`→`.claude/dispatcher.md`. P3: doc-coherence sweep — orchestrator-operator.md, CLAUDE.md §3, INDEX.md, 01-PHILOSOPHY.md, methodology-codification-pipeline.md, two-session-architect-operator.md, autonomous-operator-via-subagent.md, erp MASTER-PROMPT.md. **Inventory gap found+fixed** (fix-on-contact): §10 inventory missed `01-PHILOSOPHY.md` + `methodology-codification-pipeline.md` — the full re-grep caught them; both swept.
- 2026-05-18 — **decision reversal (triaged [R], recorded):** archive `59-keeper-housekeeping-upgrade` had decided "keep `dispatcher-inbox.md` tracked so fresh clones bootstrap without an extra step." Consolidation reverses it → unified file **gitignored**; bootstrap now via the committed **`templates/dispatcher.md`** (resolves the long-dangling `templates/dispatcher-inbox-template.md` reference — user-surfaced). Net: same zero-setup property, cleaner (one file, root narrowed, no operator-churn in history).
- 2026-05-18 — surfaced (named destination, not fixed here — out of scope): the `## <task-id>` (orchestrator-operator/autonomous-operator) vs `### YYYY-MM-DDTHH:MM — NAME` (detector/two-session) entry-format divergence is **pre-existing** → future `dispatcher-format-unify` follow-up. Noted inline in both docs.
- 2026-05-18 — **verified green:** full MCP suite **1268 passed** (0 fail), `test_compliance_hygiene` 19/19, `check_dispatcher_staleness` reads new path, `check_gitignore_drift` 0, symbology-drift 0, `verify-kb-sync` ✓. Acceptance §7 met (residual grep = only frozen `archive/` + intentional provenance prose). Project closed + archived.
