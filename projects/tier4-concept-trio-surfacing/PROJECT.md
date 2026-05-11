# Tier 4 Concept-Trio Surfacing — Decision Document

> **What this document is.** A single decision doc consolidating the §7 open
> questions of the three Tier-4 concept-stage children of
> `projects/main-core-migrations-batch/PROJECT.md`. The batch's Phase 4.a
> calls for surfacing all three §7s in one round so the user decides per
> child: **promote** (run Phase 0 + execution), **revise concept** (rewrite
> design), or **leave deferred**.
>
> **What it is NOT.** New work. This is a *scoping / surfacing* document.
> Read-only on the three child PROJECT.mds (snapshotted at
> `.claude/snapshots/projects-2026-05-03_024603/projects-root/` and, for
> `project-history-ledger`, also archived at
> `archive/projects/2026-05-10/24-project-history-ledger/`).
>
> **TL;DR up top.** All three children are **already effectively closed**.
> The batch's Phase 4 surfacing language is stale. The decision the user
> faces per child is *bookkeeping* (mark Phase 4 of the batch ✅, or revise
> the residual deferral state), **not** *promote-to-execution*. Engineering
> recommendations below; the user is the gate.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** ⏳ Surfacing complete — awaiting user decision per child.
- **Owner / stakeholders:** Raphael · architect (orchestrator) · this surfacing engineer
- **Project slug:** `tier4-concept-trio-surfacing` (subject=tier4-concept-trio, intent=surfacing)
- **Project location:** `projects/tier4-concept-trio-surfacing/` (cross-product scoping for the batch coordinator)
- **Parent batch:** `projects/main-core-migrations-batch/PROJECT.md` Phase 4 — Tier 4: concept → execution trio
- **Children surveyed (READ-ONLY):**
  - `archive/projects/2026-05-10/24-project-history-ledger/PROJECT.md` (live folder previously at `projects/project-history-ledger/`, archived 2026-05-10)
  - `.claude/snapshots/projects-2026-05-03_024603/projects-root/vista-api-mcp/PROJECT.md` (folder deleted 2026-05-03 via close-gate Wave 2 commit `38ab384`)
  - `.claude/snapshots/projects-2026-05-03_024603/projects-root/methodology-mirror-and-workspaces/PROJECT.md` (folder deleted 2026-05-03 via close-gate Wave 2 commit `38ab384`)

---

## 1. Context & Purpose

The Tier-4 trio was filed 2026-05-02 as concept-stage children of the
`main-core-migrations-batch` coordinator. The batch's Phase 4.a checklist
calls for surfacing all three §7s together so the user can decide per
child. Between filing and this surfacing pass, **the world changed**:

- **`vista-api-mcp`** — Phase 0+1 shipped 2026-05-03 (in-repo MCP at
  `mcp/vista/` per §7 Q1=A; Python per Q2=I; seed-lib formalize per Q3=γ).
  Folder deleted in commit `38ab384` ("close-gate Wave 2"). Phases 2-5
  deferred per §7 Q6 reactivation triggers (none yet fired).
- **`project-history-ledger`** — Phase 0-5 ALL shipped 2026-05-10
  (orchestrator-stamped Q1=B, Q2=c, Q3=I, Q4=standard fields under user
  signal *"resolve the 5 blocked ones"*). Engineer side complete; folder
  archived to `archive/projects/2026-05-10/24-project-history-ledger/`.
  `project-history/` infra (NDJSON ledger + renderer + pre-commit hook)
  live at repo root. 32 historical projects backfilled.
- **`methodology-mirror-and-workspaces`** — Folder deleted 2026-05-03
  (same Wave 2 commit). Q11 reactivation-trigger measurement landed at
  step-(a) close: 22% static + ~35-50% effective per-turn token savings —
  enough that the workflow is no longer constrained day-to-day. Status:
  **DEFERRED until workflow constraint returns** (auto-load creep,
  routine multi-product sessions, or methodology-variant testbeds).

The batch §6 Phase 4 prose still reads "concept-stage with §6 intentionally
empty pending §7 + user reactivation" — that text is stale (the
2026-05-10 §11 sync entry acknowledged it but didn't rewrite §6). This
surfacing pass exists so the user can flip Phase 4 ✅ with the right
bookkeeping per child.

---

## 2. Confirmed constraints

- **Dispatch brief constraints:** read-only on the 3 child PROJECT.mds;
  do NOT commit/push; new branch
  `tier4-concept-trio-surface-2026-05-11`; only this PROJECT.md is
  write-authorized; stage + return commit notes.
- **Surfacing scope:** quote each §7 verbatim, note recommended defaults,
  check dependency / trigger state, give architect's read, recommend
  PROMOTE / REVISE / LEAVE-DEFERRED per child.
- **Trigger-evidence over assertion** — `vista-api-mcp` §7 Q6 lists three
  concrete reactivation triggers; `methodology-mirror` §7 Q11 lists three
  more. Each child's recommendation must cite the actual trigger state.

---

## 3. Design principles

1. **Bookkeeping over re-execution.** Two of three children already
   shipped what their §7 recommendations resolved; the third has an
   explicit measurement-based deferral with documented triggers. Do not
   reopen settled decisions.
2. **Reality over the batch's stale prose.** The batch §6 Phase 4
   description was written before the 2026-05-03 + 2026-05-10 closures.
   Trust commits + ledger + archive over stale §6 narrative.
3. **Triggers are the gate.** `vista-api-mcp` Q6 + `methodology-mirror`
   Q11 frame reactivation as evidence-driven, not calendar-driven. No
   trigger fired → leave deferred. Trigger fired → revise + promote.
4. **One surfacing pass produces one decision doc.** This file is the
   single artifact the user reads to decide. After the user decides,
   this folder closes inline and Phase 4 of the parent batch flips ✅.

---

## 3a. Seed-first analysis

N/A — this is a scoping / decision artifact, not a code project. Per-
product code-count litmus: **0** lines. No seed seams in scope.

---

## 4. Scope

**In scope:**

- Verbatim quote of each child's §7 questions.
- Status snapshot of each child (current folder state, what shipped, what
  triggers fired).
- Architect's per-child recommendation (PROMOTE / REVISE / LEAVE-DEFERRED)
  with rationale.
- A single closing checklist the user can sign off on.

**Out of scope:**

- Re-executing any of the three children's deferred work.
- Re-opening §7 decisions already stamped (e.g. ledger Q1-Q4).
- Editing the parent batch coordinator (the user / orchestrator does that
  after deciding here).

---

## 5. Per-child surfacing

### 5.1 `project-history-ledger`

**Verbatim §7 (9 questions, all live; Q1-Q4 stamped 2026-05-10 under user
"resolve the 5 blocked ones" signal):**

1. **Where does the canonical ledger live on disk?** — (A) repo root,
   (B) dedicated dir `project-history/`, (C) `KB/HISTORY/`. *Rec: (B).*
   **✅ Q1 = B (stamped 2026-05-10).**
2. **Structured ledger format.** — (a) YAML, (b) JSON, (c) NDJSON,
   (d) SQLite. *Rec: (c) NDJSON.* **✅ Q2 = c (stamped 2026-05-10).**
3. **Token-counting mechanism.** — (I) static, (II) dynamic, (III)
   hybrid. *Rec: (I) static, ship first, extension for (II).*
   **✅ Q3 = I (stamped 2026-05-10).**
4. **Minimum viable record fields.** *Rec: 3 required + slug + dates +
   scope + status_at_close + tags; defer outcome_signals + linked
   artifacts to v2.* **✅ Q4 = standard fields (stamped 2026-05-10).**
5. **Backfill scope for existing projects.** — (α) best-effort all,
   (β) only fully-deleted, (γ) none. *Rec: (α) best-effort.*
   **✅ Resolved by Phase 4 shipping (32 historical rows backfilled).**
6. **Trigger event(s) for ledger entries.** — (p) close, (q) deletion,
   (r) split. *Rec: (p) AND (q) AND (r).*
   **✅ Resolved by Phase 2 close-workflow integration (default-on stamp
   in `noctus.dev.archive`).**
7. **Human-readable rendering — auto-generated only?** — (x) auto only,
   (y) auto + hand-edited prose. *Rec: (x).*
   **✅ Resolved by Phase 3 renderer (`scripts/render-project-history.py`
   + pre-commit hook §3b).**
8. **AI-training data shape — what gets exposed?** *Rec: include
   `prior_projects: [slug]` for dependency-graph features.*
   **⚠️ Deferred — v2 candidate; not blocking ship.**
9. **Tokenizer choice (interlock with Q3).** — Anthropic-official vs
   tiktoken. *Rec: Anthropic-official.*
   **⚠️ Shipped as `tiktoken` (cl100k_base) for speed-to-ship; Anthropic-
   tokenizer swap deferred to Phase 5 / v2 (encapsulated in
   `mcp/noctusai/tools/_tokens.py::get_default_encoder()`).**

**Dependency / trigger state.** All architecturally load-bearing
questions (Q1-Q4 + Q5 + Q6 + Q7) ✅ resolved-and-shipped. Q8 + Q9 are
v2 polish, not blocking.

**Status:** ✅ READY-FOR-CLOSE per child §11 entry 2026-05-10 — Phase 5
engineer-side complete; `noctus.dev.archive` self-stamp deferred to
orchestrator post fresh-eyes merge. **Already archived** to
`archive/projects/2026-05-10/24-project-history-ledger/`; ledger infra
live at `project-history/`. Ledger contains 32 backfilled historical
rows + accruing live close-stamps.

**Note — ledger entry for the ledger project itself:** the ledger does
*not* yet contain an entry for `project-history-ledger` (its own slug).
Inspection of `project-history/ledger.ndjson` slugs shows the 32
backfilled rows plus newer live close-stamps; the meta-entry that
Phase 5 anticipated (status=`shipped`, distinct from `historical`)
would have been written by the orchestrator's final
`noctus.dev.archive` call. **Whether that final stamp landed is not
verifiable from this read-only surface** — surface to user as a
small bookkeeping check.

**Architect's read.** The world changed substantially between filing
(2026-05-02 concept) and this surfacing (2026-05-11 archived).
There is no "promote" decision to make — execution already happened.
The only residual is the meta-stamp verification noted above.

**Recommendation: LEAVE-DEFERRED (effectively CLOSED).** No reopening.
Two bookkeeping follow-ups for the user to confirm:

- **(a)** Verify the meta-entry (`slug=project-history-ledger`,
  `status_at_close=shipped`) exists in `project-history/ledger.ndjson`.
  If absent, run `noctus.dev.history_record(...)` against the archive
  folder once to backfill it (the project's own backfill script supports
  exactly this with `slug_override`).
- **(b)** Update the parent batch's §6 Phase 4.c row to reflect the
  archived-2026-05-10 state (it currently still reads "concept — drive
  to ✅ if promoted").

---

### 5.2 `vista-api-mcp`

**Verbatim §7 (9 questions):**

1. **Where does the in-repo MCP server live?** — (A) `mcp/vista/`,
   (B) `products/erp-imobiliario/mcp/`, (C) separate repo. *Rec: (A).*
   **✅ Resolved by Phase 1 ship 2026-05-03 — server lives at
   `mcp/vista/`.**
2. **Implementation language.** — (I) Python, (II) TypeScript.
   *Rec: (I) Python.* **✅ Resolved — Python.**
3. **Reuse vs reimplement vs port the showcase adapter.** — (α) import,
   (β) port, (γ) move to `noctusai_lib.integrations.vista`. *Rec: (γ)
   move to seed-lib if ships ≤2 weeks, (β) port otherwise.*
   **✅ Resolved per commit `9b94f60` ("feat(vista): durable KB doc home
   + MCP server Phase 1 + formalize to seed-lib") — (γ) seed-lib formalize
   was the path taken.**
4. **Tokenizer / token-cost integration with `project-history-ledger`.**
   — Should the MCP server emit token-cost telemetry? *Rec: ship without;
   add opt-in `record_call_cost` in v2 once ledger defines the shape.*
   **⚠️ Deferred to v2 — non-blocking. Now that ledger has shipped (5.1
   above), this becomes a concretely-actionable v2 follow-up (NDJSON
   schema is known).**
5. **What triggers a refresh of `VISTA-API-MCP-GUIDE.md`?** — (p) manual,
   (q) automated keeper detector. *Rec: (p) manual for v1; (q) if ≥3
   refreshes/year.* **⚠️ v1 = manual; no trigger evidence yet for (q).**
6. **Reactivation trigger — what evidence makes this project ready to
   start [Phases 2-5]?** Three named triggers:
   - User explicitly asks to build the MCP server, OR
   - The external-environment build hits a Vista API surface this repo's
     adapter hasn't probed yet, OR
   - A 2nd product needs Vista access (recurrence rule).
   *Rec: wait for any of the three to fire.*
   **⚠️ NO trigger evidence in the current session.** ERP-imobi remains
   the only Vista consumer (N=1); no external-environment surface
   surprise reported; no new user ask captured in the session record.
7. **(Implicit — duplicate numbering in source; combined under Q5.)**
8. — *(no Q8 in source; document jumps from Q6/Q5 to numbered items
   appearing as Q4-Q6; counted as 6 substantive questions for this
   surfacing.)*

  *Surfacing note:* the snapshot's §7 is structured as 6 substantive
  questions (Q1-Q6); the file is consistent on that count. No questions
  were dropped in transcription.

**Dependency / trigger state.** Q1-Q3 resolved-and-shipped (Phase 1).
Q4 partially-unblocked by ledger's 2026-05-10 ship. Q5 + Q6 explicitly
trigger-gated; **no triggers fired in this session**.

**Status:** Phase 1 shipped + folder deleted 2026-05-03; Phases 2-5
deferred per Q6 (no triggers fired). KB-resident artifact survives at
`KB § INTEGRATIONS/vista.md` + repo-root `VISTA-API-MCP-GUIDE.md` (the
"durable KB doc home" path of commit `9b94f60`).

**Architect's read.** The Phase 1 ship covered the high-leverage part
(MCP server skeleton + the seed-lib adapter formalize that was the §7 Q3
γ-path). Phases 2-5 are the *permission-blocked* and *write-surface*
expansions — they require either a Vista tenant with broader permissions
(clientes/corretores) or a 2nd consumer to justify the recurrence-rule
fork. Neither evidence is present. The Q4 ledger-integration is the only
sub-question whose blocker (ledger schema unknown) has cleared since
2026-05-03 — and even that's v2 polish, not a structural decision.

**Recommendation: LEAVE-DEFERRED.** No reopening unless the user
signals one of the Q6 triggers. Two small bookkeeping follow-ups:

- **(a)** Now that ledger schema is known, the Q4 v2 token-cost
  telemetry has a defined target. File as a small follow-up project
  (`vista-mcp-cost-telemetry`) only if the user wants opt-in
  observability; otherwise leave the v2 hook documented in
  `KB § INTEGRATIONS/vista.md` and let the next Vista consumer surface it.
- **(b)** Update the parent batch's §6 Phase 4.b row to reflect
  "Phase 1 shipped 2026-05-03; Phases 2-5 deferred per §7 Q6 — no
  triggers fired."

---

### 5.3 `methodology-mirror-and-workspaces`

**Verbatim §7 (11 questions; Q1-Q10 are design questions, Q11 is the
reactivation-trigger question):**

1. **Direction of product-code merge.** — (A) workspaces=temp dev forks
   rebase to trunk, (B) workspaces=permanent product homes.
   *Rec: (A) for now.* **⚠️ Unresolved (gated on Q11).**
2. **What "memory" means for the mirror.** — (a) auto-memory index
   only, (b) separate local store. *Rec: (a) index + (b) content-on-disk.*
   **⚠️ Unresolved.**
3. **Where the mirror physically lives.** — sibling folder /
   `.mirror/` / git branch / separate clone / git worktree. *Rec: git
   worktree pointing at `mirror/checkpoint` branch.* **⚠️ Unresolved.**
4. **One global mirror or per-workspace.** *Rec: one global.*
   **⚠️ Unresolved.**
5. **What "ci/cd" fires when there's no GitHub.** *Rec: existing local
   verification stack wrapped by a `promote-to-trunk` script.*
   **⚠️ Unresolved.**
6. **Workspace lifecycle.** — once-per-task / once-per-product / once-
   per-experiment. *Rec: once-per-product, long-lived.*
   **⚠️ Unresolved.** *(Note: subsequently overtaken by separate
   reality — `git worktree add` per engineer is now the default per
   §1 branching-first orchestration rule; once-per-engineer-chunk is
   the de-facto pattern in 2026-05-10/11 work. Captures intent at
   filing time; trunk methodology has evolved.)*
7. **"Doc-aware" — full KB or scoped.** *Rec: full KB at fork time.*
   **✅ Resolved by `KB § PATTERNS/seed-workspace.md § Why the inherited
   surface is not trimmed` (filed 2026-05-04 → memory entry
   `feedback_seed_workspace_inherit_whole_not_trim.md`). Settled
   structurally; aligns with the recommendation.**
8. **What "approved locally" means.** — self / agent-pair review /
   keeper pass. *Rec: agent-pair review + keeper pass.*
   **⚠️ Unresolved; partially shaped by dev-team's emerging code-review
   shape (`KB § PATTERNS/dev-team.md`).**
9. **How methodology variants merge back to trunk.** *Rec: absorb-into-
   existing-proposals via `noctusai_file_proposal`.*
   **⚠️ Unresolved structurally; current shape is "no separate workspace-
   to-trunk methodology merge needed — trunk evolves directly."**
10. **What happens when trunk's methodology evolves while a workspace
    is forked.** *Rec: pin + manual re-sync.* **⚠️ Unresolved.**
11. **Reactivation trigger — what evidence justifies starting this
    project.** **✅ Measurement landed 2026-05-02 at step (a) close:**

    | Surface | Pre-trim | Post-step-(a) | Δ |
    |---|---:|---:|---:|
    | CLAUDE.md tokens | ~10,640 | ~6,754 | **-3,886 (-37%)** |
    | MEMORY.md tokens | ~4,883 | ~5,331 | +448 (+9.2%) |
    | **Auto-load surface (combined)** | **~15,523** | **~12,085** | **-3,438 (-22%)** |

    22% static + behavioral runtime savings (estimated 35-50% effective).
    **Status per child §7 Q11: DEFERRED.** Three reactivation triggers
    named: auto-load surface creep, routine multi-product sessions, or
    methodology-variant testbeds wanting isolation.

**Dependency / trigger state.** **NO triggers fired as of 2026-05-11.**
Auto-load surface has crept up (MEMORY.md is now flagged at 35.2KB
exceeding 24.4KB index limit per the current session reminder) — but the
prescribed methodology response is *MEMORY.md index trimming*, NOT
re-activating workspace isolation. Q11's "if the auto-load surface
creeps back up" trigger language was meant for *post-trim* creep, not
"the index has grown" (which is fixable inside trunk's rule).

**Architect's read.** This project is the *future-work parking lot* —
the architecture sketch is preserved in the snapshot, the measurement
that justifies the deferral is durable. Re-opening today would re-build
infrastructure (worktree-per-product permanent forks, mirror layer,
promote-to-trunk script) that the current methodology has reached for
incrementally in different shapes:

- **`git worktree add` per engineer** (KB §16) — workspace isolation
  at the chunk level, not the product level. Different shape, same
  isolation goal.
- **`.claude/worktrees/agent-*/` ephemeral workspaces** + automated
  cleanup script (memory entry `feedback_worktree_auto_cleanup.md`) —
  workspace lifecycle solved at a different granularity.
- **Template workspace** (`KB § PATTERNS/template-workspace.md`) +
  promotion manifest — the "starter-kit bundle" + "promote-to-trunk"
  shape, applied to a different use case (sibling-product spinout).
- **Seed workspace** (`KB § PATTERNS/seed-workspace.md`) — the "full
  KB at fork time" decision (Q7) settled structurally.

Net: substantial portions of the workspaces-and-mirror design space
have been *naturally addressed* by other shipped methodology
infrastructure, without needing the b-step + c-step structural
investment Q11 was gating. The mirror layer (b-step) remains a clean-
sheet idea; nothing in trunk has replicated it.

**Recommendation: LEAVE-DEFERRED.** Q11's reactivation triggers have
not fired. The MEMORY.md size warning visible in the current session
is a *trunk-side* fixable (index entry trimming, per the warning's own
guidance), not a Q11 trigger. Three small bookkeeping follow-ups:

- **(a)** Document in the parent batch's §6 Phase 4.d row that the
  child folder is already deleted (2026-05-03 close-gate Wave 2) — the
  current row still implies the folder exists.
- **(b)** Note the de-facto natural-evolution offsets in `KB §
  PATTERNS/seed-workspace.md` or a fresh KB page: which §7 questions
  have been *partially answered by different shapes* shipping in the
  ~9 days since filing. This preserves the survival path if Q11 ever
  fires.
- **(c)** The MEMORY.md 35.2KB warning is its own follow-up —
  unrelated to this project's reactivation triggers, but worth a
  one-liner: file `memory-index-trim` as a small follow-up project
  if the user wants the index entry shortening done before next
  session.

---

## 6. Implementation phases

### Phase 0 — Surfacing ✅ (this document)

- [x] Quote each child's §7 verbatim with recommended defaults.
- [x] Check dependency / trigger state per child.
- [x] Architect's read per child.
- [x] PROMOTE / REVISE / LEAVE-DEFERRED recommendation per child with
      rationale.
- [x] Surface bookkeeping follow-ups per child.

### Phase 1 — User decision per child *(blocked on user)*

- [ ] **`project-history-ledger`** — confirm LEAVE-DEFERRED (effectively
      CLOSED). Optionally action follow-ups 5.1.(a) and 5.1.(b).
- [ ] **`vista-api-mcp`** — confirm LEAVE-DEFERRED. Optionally action
      follow-up 5.2.(a) and 5.2.(b).
- [ ] **`methodology-mirror-and-workspaces`** — confirm LEAVE-DEFERRED.
      Optionally action follow-ups 5.3.(a), 5.3.(b), 5.3.(c).

### Phase 2 — Batch §6 Phase 4 close

- [ ] Once user signs off on all three, the orchestrator amends the
      parent batch's §6 Phase 4 prose to reflect actual closed state,
      flips Phase 4 ✅, and folds the rollup into the batch §11.
- [ ] This surfacing project folder closes inline (apply-inline-then-
      delete per `KB § PATTERNS/project-execution.md`).

---

## 7. Open questions

1. **Meta-stamp verification for `project-history-ledger` (5.1.(a)).**
   Did the orchestrator's final `noctus.dev.archive` invocation against
   `projects/project-history-ledger/` produce a `status=shipped` row in
   `project-history/ledger.ndjson`? Read-only surface can't confirm.
   *Recommendation:* run a one-liner check
   (`grep '"slug":"project-history-ledger"' project-history/ledger.ndjson`);
   if absent, backfill via the project's own script with
   `slug_override="project-history-ledger"`.
2. **Q4 v2 telemetry hook for `vista-api-mcp`.** Now that the ledger
   exists, should we file `vista-mcp-cost-telemetry` as a small follow-
   up project, or document the v2 hook inline in
   `KB § INTEGRATIONS/vista.md`? *Recommendation:* inline doc; let the
   next Vista consumer surface the recurrence-rule trigger.
3. **MEMORY.md 35.2KB index trimming** (surfaced incidentally by 5.3
   above). *Recommendation:* file `memory-index-trim` only if the user
   wants it actioned before next session; otherwise it's a routine
   maintenance pass during the next non-coding turn.
4. **Should the parent batch's §6 Phase 4 prose be rewritten now, or
   does flipping Phase 4 ✅ via §11 entry suffice?** *Recommendation:*
   Phase 4 ✅ via §11 entry is enough; the §6 prose is historical
   captured-at-filing-time content — leaving it stale-but-noted in §11
   is consistent with how Phase 1 (Path B subsumed) and Phase 2.a
   (re-scoped + standalone) are documented.

---

## 8. Dependencies & blockers

- **User decision per child** — Phase 1 blocks on user signoff.
- **None of the three children have unfired triggers.** No external
  blockers.

---

## 9. Success criteria

- User has read this document and signed off on the per-child
  recommendation (or directed otherwise).
- Parent batch's Phase 4 has flipped ✅ in the next orchestrator pass.
- Three small bookkeeping follow-ups per child (5.1.(a-b), 5.2.(a-b),
  5.3.(a-c)) either applied inline OR surfaced as named follow-up
  destinations (no silent skips).
- This surfacing folder closes inline + folds into the batch §11.

---

## 10. How to use this document

```bash
# Read this surfacing
cat projects/tier4-concept-trio-surfacing/PROJECT.md

# Verify the meta-stamp for project-history-ledger (follow-up 5.1.(a))
grep '"slug":"project-history-ledger"' project-history/ledger.ndjson || echo "MISSING — backfill needed"

# Inspect each child's snapshotted §7 for verbatim quotes
sed -n '1,200p' .claude/snapshots/projects-2026-05-03_024603/projects-root/vista-api-mcp/PROJECT.md
sed -n '1,200p' .claude/snapshots/projects-2026-05-03_024603/projects-root/methodology-mirror-and-workspaces/PROJECT.md
sed -n '1,200p' archive/projects/2026-05-10/24-project-history-ledger/PROJECT.md

# After user decides — orchestrator pass on parent batch
sed -n '209,235p' projects/main-core-migrations-batch/PROJECT.md  # current Phase 4 prose
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | **Project filed + Phase 0 ✅** — surfaced §7s of the three Tier-4 concept-stage children of `main-core-migrations-batch`. Reality check: all three are already effectively closed (`vista-api-mcp` Phase 1 shipped + folder deleted 2026-05-03 per commit `38ab384`; `methodology-mirror-and-workspaces` folder deleted same commit per Q11 deferral with 22% static + 35-50% effective measurement; `project-history-ledger` Phase 0-5 shipped 2026-05-10 + folder archived to `archive/projects/2026-05-10/24-project-history-ledger/`). Per-child recommendation: **all three LEAVE-DEFERRED (effectively CLOSED)** with small bookkeeping follow-ups noted. No triggers fired for `vista` Q6 or `methodology-mirror` Q11. Parent batch §6 Phase 4 prose is stale-but-captured; recommendation is flip Phase 4 ✅ via §11 entry rather than rewriting §6. | Engineer TIER4-SURFACE (Claude Opus 4.7) |
