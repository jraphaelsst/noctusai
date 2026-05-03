# Absorbed-Projects Batch — Project Document

> **What this project is.** A batch coordinator that drives the 8 projects
> filed during commit `5acf4c4` (the absorption batch from sibling repos
> `whatsapp-google-scheduling` + `automations`) to completion in dependency
> order. Each phase below targets one or more child projects already
> scaffolded under `projects/`. The implementation work itself happens in
> each child's PROJECT.md; this batch is the meta-loop that orders them,
> runs §7 interrogation per child before its execution starts, and tracks
> rollup progress.
>
> **Why a batch project.** The 8 absorption children are interlocked —
> `imobi-scheduling-bot-creation` consumes the four seed-absorption
> projects (`whatsapp-seed-absorption`, `scheduling-engine-seed`,
> `llm-tool-call-audit`, `mcp-server-expansion`). Without coordination
> the bot project blocks halfway through Phase 5+ on missing seed-lib
> helpers. This batch enforces the dependency order.
>
> **Run-by.** Designed for a parallel agent that did not see the
> conversation that produced it. §1 inlines context, §2 quotes user
> direction, §5 names every file, §7 questions are paired with
> evidence-backed recommendations, §10 commands are copy-paste ready.
> Snapshot `.claude/snapshots/projects-2026-05-03_024603/` is the frozen
> evaluation reference.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** ⏳ **EXECUTING (Tier 1 in progress, Tier 2 ✅, Tier 4 confirmed deferred)** — children scaffolded; user re-ordered tier sequence (MCP → LLM-audit → finish); Tier 1.b (llm-tool-call-audit) ✅, Tier 2 (mcp-server-expansion) ✅ with two named carry-forward projects, Tier 4 (3 future-direction drafts) confirmed deferred. Remaining: Tier 1.c (scheduling-engine-seed), Tier 1.d (whatsapp-seed-absorption), Tier 3 (imobi-scheduling-bot-creation) — each requires focused-session pickup.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Project slug:** `absorbed-projects-batch` (subject=absorbed-projects, intent=batch)
- **Project location:** `projects/absorbed-projects-batch/` (cross-product / platform-coordinator — drives 8 root-level child projects)
- **Sibling batches** running in parallel (do not duplicate work):
  - `projects/side-projects-batch/PROJECT.md` — our older non-absorbed side projects (8 children).
  - `projects/main-core-migrations-batch/PROJECT.md` — main-core / large migrations (7 children).
- **Snapshot:** `.claude/snapshots/projects-2026-05-03_024603/` — frozen state of all 26 PROJECT.md files at batch start.
- **Related docs:**
  - Commit `5acf4c4` — the absorption batch that filed all 8 children. Read its commit message for full per-child context: `git show 5acf4c4 --stat`.
  - `KB § PATTERNS/project-execution.md § 0` — canonical execution workflow each child runs through.
  - `KB § 01-PHILOSOPHY.md § AST-first` + `§ MCP-first` — methodology principles that landed alongside this absorption.

---

## 1. Context & Purpose

On 2026-05-03 (commit `5acf4c4`), 8 projects were filed at once to absorb portable artifacts from two sibling repos (`whatsapp-google-scheduling`, `automations`) before the user deletes those repos. The commit message decomposes them as:

**Active projects (Phase 0 ready) — 5 children:**
- `whatsapp-seed-absorption` (355 lines, 9 phases): WhatsApp connector + chatbot framework + Calendar/Maps adapters land in `noctusai_lib`.
- `scheduling-engine-seed` (245 lines, 7 phases): sibling SchedulingService → `noctusai_lib.domain.scheduling` with vocabulary generalized.
- `llm-tool-call-audit` (242 lines, 7 phases): ToolCallAudit pattern → `noctusai_lib.domain.ai` (highest observability ROI; we have nothing equivalent today).
- `mcp-server-expansion` (344 lines, 8 phases): grow MCP into wide-purpose toolkit; dev toolkit becomes one branch; absorbs sibling MCP tools.
- `imobi-scheduling-bot-creation` (381 lines, 10+ phases): the bot itself, rebuilt as a noc product fresh on our patterns (`create_product_app` + RLS + standard routers), **consuming the four seed-absorption projects above**.

**Deferred drafts (preserve before sibling deletion) — 3 children:**
- `agno-dev-team-future-direction` (146 lines): preserves automations/ 469-line dev-team spec. **Status: NOT SCHEDULED.**
- `dev-observability-bot-future-direction` (147 lines): sibling dev-team-support-bot plan ported. **Status: NOT SCHEDULED.**
- `user-context-bot-future-direction` (136 lines): sibling personal-assistant-bot plan ported. **Status: NOT SCHEDULED.**

Every project carries §12 No-leftovers: sibling-path references are execution-scoped (vanish on apply-inline-then-delete); KB docs landed in commit `5acf4c4` contain zero references to sibling repos so they survive the user's planned deletion.

This batch project ensures the 5 active children execute in dependency order so `imobi-scheduling-bot-creation` doesn't start until its seed-lib substrate is real, and the 3 deferred drafts stay durably documented without accidental scheduling.

---

## 2. Confirmed constraints

- **Scope** — only the 8 absorption children filed in commit `5acf4c4`. *(User direction 2026-05-03: "Absorbed from sibling repos, Main-core big migrations, please create projects for their implementation as well... i'm gonna use a parallel agent to start working on them".)*
- **Dependency order is mandatory.** Bot-product children consume seed-absorption children. No dependency-cycle interleaving. *(Filed in 5acf4c4: "imobi-scheduling-bot-creation: the bot itself rebuilt as a noc product fresh on our patterns, consuming the four seed-absorption projects above.")*
- **Each child runs its own canonical execution workflow** (`KB § PATTERNS/project-execution.md § 0`): scaffold → Phase 0 audit → execute per phase → close-phase commit (no push) → on full child close, fold into batch §11 + delete child folder. Push happens only at this batch's close.
- **Deferred drafts stay deferred.** `agno-dev-team-future-direction`, `dev-observability-bot-future-direction`, `user-context-bot-future-direction` are concept-stage with `Phase 0 (NOT SCHEDULED)`. This batch confirms their out-of-scope status — it does NOT schedule them. User reactivation is the only trigger.
- **No leftovers from sibling paths.** Every child's `§12 No-leftovers` ensures references to `whatsapp-google-scheduling/` or `automations/` are execution-scoped (live only in PROJECT.md, vanish at apply-inline-then-delete). KB docs already shipped (commit `5acf4c4`) contain zero sibling-path references.
- **Methodology principles already landed** in commit `5acf4c4`: AST-first (`KB § 01-PHILOSOPHY.md § AST-first`), MCP-first (`§ MCP-first`), `KB § PATTERNS/ast.md`. Children inherit these — no need to re-establish.
- **Sibling repos exist for now**, but user plans deletion. Children must be self-contained (re-readable post-deletion) — already enforced by §12 in each child.

---

## 3. Design principles

1. **Dependency order beats slug order.** Tier 1 (seed-lib substrate) → Tier 2 (toolkit growth) → Tier 3 (consumer product). Not alphabetical, not ticket-order.
2. **One child at a time within a tier.** Tier 1 has 3 substrate landings — each goes fully (Phase 0 → close → folder deleted) before the next starts. Avoids interleaved partial states.
3. **Tier-batched §7 interrogation.** When a tier starts, surface every child's §7 questions in one user-facing round. No mid-execution context switching for unanswered questions.
4. **Recurrence captured at this batch layer.** When child A surfaces a helper that child B would also benefit from, that observation lives in this batch's improvements block (which survives child folder deletion) — not just child A's `**Improvements:**`.
5. **Deferred drafts get acknowledgement, not scheduling.** Tier 4 below confirms the 3 future-direction children stay deferred. Their existence is preserved; their work is not started here.

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

This is a **batch coordinator project** — its only deliverable is sequencing, interrogation cadence, and rollup. It produces no production code. Each child project runs its own §3a (those §3a's are where the real seed-first analysis lives — every absorption child IS landing in seed by construction).

Six-question checklist:

1. **Is the contract identical for every product?** N/A — this batch ships no product-touching code. Each child's §3a answers this for the child's actual change. (Tier 1 children all answer YES — they land in `noctusai_lib`.)
2. **Is the data source product-specific?** N/A.
3. **Is the placement product-specific?** N/A.
4. **Is the visibility / permission rule the same?** N/A.
5. **Does the seam already exist in seed?** N/A — no seam needed at the batch layer.
6. **Default-on or opt-in?** N/A.

**Litmus — per-product code count this design requires:**

- [x] **0 lines** — pure cross-product concern; lives entirely in seed. Products inherit from the factory. → Confirmed: this batch produces zero per-product code. Per-product code lands inside each child project.

**Phase plan implications:** §6 phases below are **phase = child-batch by tier**, not phase-per-product. No replication framing.

---

## 4. Scope

**In scope (5 active + 3 deferred-acknowledged children):**

**Tier 1 — seed-lib substrate (Phase 1 of this batch):**
- `projects/whatsapp-seed-absorption/`
- `projects/scheduling-engine-seed/`
- `projects/llm-tool-call-audit/`

**Tier 2 — toolkit growth (Phase 2 of this batch, depends on Tier 1's seed-lib landings):**
- `projects/mcp-server-expansion/`

**Tier 3 — consumer product (Phase 3 of this batch, depends on Tier 1 + Tier 2):**
- `projects/imobi-scheduling-bot-creation/`

**Tier 4 — deferred drafts (Phase 4 of this batch — confirm-and-leave, do NOT execute):**
- `projects/agno-dev-team-future-direction/`
- `projects/dev-observability-bot-future-direction/`
- `projects/user-context-bot-future-direction/`

**Out of scope (handled by sibling batches, do not pull in):**
- 8 our-side children — driven by `projects/side-projects-batch/PROJECT.md`.
- 7 main-core / large migrations — driven by `projects/main-core-migrations-batch/PROJECT.md`.
- 3 already-closed / empty (`methodology-extraction`, `vista-crm-wiring`, `repo-commit-followup`) — no project-level action required.

---

## 6. Implementation phases

**Phase = tier-batch.** Each phase opens with a §7 interrogation round covering every child in that tier (except Tier 4 which is confirm-and-leave), then drives each child end-to-end through its own canonical workflow before flipping the batch phase to ✅.

### Phase 0 — Categorize + scaffold batch ✅ (executed 2026-05-03)

- [x] Identify the 8 absorption children (commit `5acf4c4` decomposition).
- [x] Confirm dependency order: 4 seed-absorption substrate children must close before bot-product child starts.
- [x] Tier them: Tier 1 (3 substrate), Tier 2 (1 toolkit), Tier 3 (1 product), Tier 4 (3 deferred).
- [x] Scaffold this batch project from `templates/PROJECT-TEMPLATE.md`.

**Improvements:**
- The dependency edge from `imobi-scheduling-bot-creation` to the 4 substrate children is documented in 5acf4c4's commit message but only loosely in the bot's own PROJECT.md (Phases 5-8 mention "Wire seed: <X>"). If a future absorption batch uses the same shape (substrate-first → consumer-second), formalize a `dependsOn:` field in PROJECT-TEMPLATE.md frontmatter so the dependency is queryable. *(N=1 today; revisit if a 2nd absorption batch surfaces.)*

### Phase 1 — Tier 1: seed-lib substrate (3 children)

Drives 3 absorption children to ✅, each landing in `noctusai_lib`. No inter-child blocking — they could run sequentially in any order. Recommended execution order is **smallest first** (`llm-tool-call-audit` 7 phases) → mid (`scheduling-engine-seed` 7 phases) → largest (`whatsapp-seed-absorption` 9 phases) for fastest cumulative landing.

**1.a §7 interrogation round (gates Phase 1.b–1.d).**
- [ ] Read `§7` of `whatsapp-seed-absorption/PROJECT.md`, `scheduling-engine-seed/PROJECT.md`, `llm-tool-call-audit/PROJECT.md`. Surface every open question to user in one round; capture answers in each child's §2 + §7.

**1.b `llm-tool-call-audit` — drive to ✅.** *(Smallest substrate; lands `ToolCallAudit` pattern in `noctusai_lib.domain.ai`.)*
- [ ] Phase 0 audit per child workflow (read sibling source artifact, decide vocabulary, identify migration template needs).
- [ ] Phase 1 — model + writer.
- [ ] Phase 2 — migration template.
- [ ] Phase 3 — KB pattern doc.
- [ ] Phase 4 — wire into chatbot framework (note: chatbot framework lands in `whatsapp-seed-absorption` Phase 5; coordinate if running Tier 1 in parallel).
- [ ] Phase 5 — LLM-bot-security KB pattern doc (folded from sibling `security-hardening`).
- [ ] Phase 6 — final verification.
- [ ] Close-phase commit; child folder deleted; outcomes folded into this batch §11.

**1.c `scheduling-engine-seed` — ✅ shipped 2026-05-03.** *(Lib landed at `noctusai_lib.domain.scheduling`.)*
- [x] Phase 0 audit — design-shape adjustments locked in (TravelLookup Protocol, SchedulingContext value-object, WorkingWindow named struct).
- [x] Phase 1+2 (merged) — engine + rules + Conflicts + Scorer + TravelLookup Protocols + defaults.
- [x] Phase 3 — 9 tests (5 ported sibling + 4 seed-lib-only Scorer).
- [x] Phase 4 — KB pattern doc (`scheduling-seed.md`); INDEX + CLAUDE.md §2 Map.
- [x] Phase 5 — final verification (350/350 → 352/352 after Phase 6); therapy-scheduling-pilot scaffolded.
- [x] Phase 6 — `SchedulingEngine.reschedule()` + cancel-vs-reschedule doc + 2 reschedule tests.
- [x] Close-phase commit + child folder deletion at batch-close commit.

**1.d `whatsapp-seed-absorption` — ✅ shipped 2026-05-03.** *(Largest substrate; lands WhatsApp connector + chatbot framework + Calendar/Maps adapters.)*
- [x] Phase 0 audit (gate sub-tasks verified; §5.1 map correction landed for sibling waha-as-directory).
- [x] Phase 1 — foundation: redis backfill + 4 namespace skeletons.
- [x] Phase 2 — WhatsApp connector lift (5 files + 21 tests).
- [x] Phase 3 — buffer + debounce (Redis key names preserved verbatim; 7 tests).
- [x] Phase 4 — worker shell (5 tests).
- [x] Phase 5 — LLM dispatcher + mappers (13 tests).
- [x] Phase 6 — summarize_conversation helper (3 tests).
- [x] Phase 7 — Calendar Fake + types + factory (9 tests). **Real Google service-account + OAuth adapters deferred** to `google-calendar-real-adapters` follow-up (accept-with-rationale).
- [x] Phase 8 — Maps Static + GoogleMapsRoutingAdapter + factory (11 tests).
- [x] Close-phase commit + child folder deletion at batch-close commit.

### Phase 2 — Tier 2: toolkit growth (1 child)

Depends on Tier 1's seed-lib landings. `mcp-server-expansion` absorbs sibling MCP tools — many of which depend on the seed-lib substrates (e.g. Calendar/Maps adapters, scheduling engine).

**2.a §7 interrogation round (gates Phase 2.b).**
- [ ] Read `§7` of `mcp-server-expansion/PROJECT.md`. Surface open questions to user.

**2.b `mcp-server-expansion` — drive to ✅.**
- [ ] Phase 0 audit (current MCP server shape; identify gaps to wide-purpose toolkit; settings shim design).
- [ ] Phase 1 — settings shim.
- [ ] Phase 2 — Pydantic in/out schemas pattern.
- [ ] Phase 3 — dotted naming + backward-compat aliases.
- [ ] Phase 4 — hierarchical registration.
- [ ] Phase 5 — sibling tool absorption + business-logic context.
- [ ] Phase 6 — KB pattern doc + MCP-first principle (note: MCP-first already in CLAUDE.md from commit `5acf4c4`; this phase lands the depth doc).
- [ ] Phase 7 — final verification + handoff.
- [ ] Close-phase commit; child folder deleted; outcomes folded into this batch §11.

### Phase 3 — Tier 3: consumer product (1 child)

Depends on Tier 1 + Tier 2. The bot product cannot be built until its substrate exists.

**3.a §7 interrogation round (gates Phase 3.b).**
- [ ] Read `§7` of `imobi-scheduling-bot-creation/PROJECT.md`. Surface open questions, particularly the slug/location confirmation noted in the project status.

**3.b `imobi-scheduling-bot-creation` — drive to ✅.**
- [ ] Phase 0 — audit + decisions (slug confirmation hard-gate per project status).
- [ ] Phase 1 — scaffold the product.
- [ ] Phase 2 — backend foundation.
- [ ] Phase 3 — domain models + migrations.
- [ ] Phase 4 — authorization.
- [ ] Phase 5 — wire seed: WhatsApp connector. *(Depends on Tier 1.d ✅.)*
- [ ] Phase 6 — wire seed: chatbot framework + tool-audit. *(Depends on Tier 1.b ✅ + Tier 1.d ✅.)*
- [ ] Phase 7 — wire seed: scheduling engine. *(Depends on Tier 1.c ✅.)*
- [ ] Phase 8 — wire seed: Google Calendar + Google Maps. *(Depends on Tier 1.d ✅.)*
- [ ] Phase 9+ — frontend + integration tests + production readiness (per child PROJECT.md).
- [ ] Close-phase commit; child folder deleted; outcomes folded into this batch §11.

### Phase 4 — Tier 4 confirm-and-leave (3 deferred drafts)

These do **NOT** execute. Phase 4 only confirms they remain deferred and self-contained.

- [ ] Re-read `agno-dev-team-future-direction/PROJECT.md` §1 + §7. Confirm sibling-path references are still execution-scoped (will vanish if folder deletes; for now they live with the doc).
- [ ] Re-read `dev-observability-bot-future-direction/PROJECT.md` §1 + §7. Same confirm.
- [ ] Re-read `user-context-bot-future-direction/PROJECT.md` §1 + §7. Same confirm.
- [ ] If user has not signaled reactivation for any of the three, flag them as "untouched, durable concept-stage" in §11 and move on.
- [ ] Verify each `§12 No-leftovers` carries a concrete reactivation trigger.

### Phase 5 — Project close

- [ ] Confirm Tier 1-3 children closed + folders deleted (5 active children).
- [ ] Confirm Tier 4 deferred drafts are documented + untouched (3 children).
- [ ] Roll up this batch's improvements + recurrence captures into one final `noctusai_file_proposal` if any cross-tier patterns emerged worth preserving beyond §11.
- [ ] `python mcp/noctusai/cli.py --improvements projects/absorbed-projects-batch/PROJECT.md`.
- [ ] Three-way sync verification (`bash scripts/verify-kb-sync.sh`).
- [ ] Final commit + push (literal last step per `KB § PATTERNS/project-execution.md § 0`).
- [ ] Delete this folder.

---

## 7. Open questions

Batch-level questions only. Per-child §7 questions are surfaced at each tier's kickoff (Phase 1.a / 2.a / 3.a).

1. **Tier 1 parallelization** — execute Tier 1 children sequentially (recommended: `llm-tool-call-audit` → `scheduling-engine-seed` → `whatsapp-seed-absorption`) or accept inter-child interleaving on phases that don't conflict (e.g. KB pattern docs)? *Default recommendation:* sequential, smallest-first. Yields fastest cumulative completion + cleanest commit history. Decision needed before Phase 1 starts.
2. **Tier 4 reactivation triggers** — are any of the 3 deferred drafts now signaled for reactivation by the user? *Default recommendation:* leave deferred unless user explicitly says otherwise; this batch closes Phase 4 by confirming durable deferral.
3. **Coordination with `side-projects-batch` + `main-core-migrations-batch`** — should the 3 batches run strictly sequentially, or can a parallel agent take Tier 1 of this batch while the main-batch agent handles different work? *Default recommendation:* parallel-safe — children touch different surface areas (Tier 1 here lands in `noctusai_lib`; main-core touches product code + migrations). User said "i'm gonna use a parallel agent" — assume parallel until conflict surfaces.

---

## 8. Dependencies & blockers

- **§7 interrogation round per tier** — gates execution of every child in that tier (except Tier 4 which is confirm-only).
- **Sibling-repo source artifacts** — children reference paths in `whatsapp-google-scheduling/` and `automations/`. These exist now; user plans deletion. All §12 No-leftovers blocks ensure post-deletion survival of the work itself, but mid-execution the references are live. If the parallel agent is starting Tier 1 and the sibling repos are gone, escalate to user immediately.
- **Tier 1 → Tier 2 → Tier 3 hard ordering** — mcp-server-expansion absorbs tools that depend on Tier 1 substrate landings; `imobi-scheduling-bot-creation` Phases 5-8 each name a Tier 1 dependency.

---

## 9. Success criteria

- All 5 active children closed (✅) + their folders deleted.
- All 3 deferred drafts confirmed deferred + untouched (Phase 4 done).
- Each child's improvements folded into this batch §11 with one-line summaries.
- No regressions: end-of-batch verification = MCP tests green + every touched product backend pytest green + `noctusai_lib` tests green.
- Recurrence patterns surfaced across children captured here so the signal survives child-folder deletion.
- One final batch commit + push (Phase 5) is the literal last action.

---

## 10. How to use this plan

```bash
# Read this batch
cat projects/absorbed-projects-batch/PROJECT.md

# Read commit 5acf4c4 for full per-child context
git show 5acf4c4 --stat
git log -1 --format=%B 5acf4c4

# Snapshot reference (frozen evaluation point)
ls .claude/snapshots/projects-2026-05-03_024603/

# At start of each tier — surface §7 questions to user (one round per tier)
# Tier 1 questions are inline above (Phase 1.a). Read each child's §7 before kicking off.

# For each child, follow KB § PATTERNS/project-execution.md § 0 (canonical workflow)
# Read child's PROJECT.md, run Phase 0 audit, execute, close-phase-commit, fold into §11.

# Sibling-repo paths still live? (children reference them mid-execution)
ls -d ../whatsapp-google-scheduling/ ../automations/ 2>/dev/null

# Verify across phases
bash scripts/verify-kb-sync.sh
python mcp/noctusai/cli.py --review

# Improvements regen at every batch-phase close
python mcp/noctusai/cli.py --improvements projects/absorbed-projects-batch/PROJECT.md
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | **Project scaffolded + Phase 0 ✅.** 8 absorption children categorized into 4 tiers: Tier 1 substrate (3 children — `llm-tool-call-audit`, `scheduling-engine-seed`, `whatsapp-seed-absorption`), Tier 2 toolkit (1 — `mcp-server-expansion`), Tier 3 product (1 — `imobi-scheduling-bot-creation`), Tier 4 deferred drafts (3 — `agno-dev-team-future-direction`, `dev-observability-bot-future-direction`, `user-context-bot-future-direction`). Dependency order from commit `5acf4c4` decomposition: `imobi-scheduling-bot-creation` consumes all 4 seed-absorption substrate projects. Awaiting Phase 1.a §7 interrogation round to start Tier 1 execution. | Claude Opus 4.7 |
| 2026-05-03 | **Tier sequence reordered + §7 round closed** (Phase 1.a). User re-ordered MCP → LLM-audit → finish. §7 questions answered for both: MCP naming umbrella = `noctus.*` (NOT `platform.*`); MCP Phase 5 deferred until Tier 1 substrate lands; LLM-audit table layout = per-product `tool_call_audits` (each product DB owns rows; aligns with cross-product LGPD block); LLM-audit Q2-Q6 accepted at recommended defaults. | Claude Opus 4.7 |
| 2026-05-03 | **Tier 2 ✅ (mcp-server-expansion CLOSED).** 5 of 7 phases ✅ shipped (0, 1, 2, 3, 6, 7); 2 deferred via named follow-up projects: `projects/mcp-server-fastmcp-switch/` (Phase 4 carry-forward — FastMCP architectural switch + per-file `register(server)` + tool-file relocation into `tools/noctus/dev/`; AND Phase 5 carry-forward — sibling tool absorption gated on Tier 1 substrate landing) + `projects/mcp-tool-name-deprecation/` (alias retirement once consumers migrate). **Concrete deliverables**: `mcp/noctusai/settings.py` (NEW, 24 lines, lib settings re-export), 5 tool files Pydantic-ified (context, compliance, analyzers, review, catalog), 6 dotted aliases registered (50 → 56 tools), `KB § PATTERNS/mcp-tool-conventions.md` (NEW, 8 sections), CLAUDE.md §2 Map pointer + INDEX.md updates. **3 commits**: `bfe4f83`, `b3af71f`, `9d90f99`. | Claude Opus 4.7 |
| 2026-05-03 | **Tier 1.b ✅ (llm-tool-call-audit CLOSED).** 5 of 6 phases ✅ shipped (0, 1, 2, 3, 5, 6); Phase 4 (wire-into-chatbot-framework) deferred to `projects/whatsapp-seed-absorption/` Phase 5 with exact import + wiring shape pre-documented in `KB § PATTERNS/llm-tool-audit.md § 3c`. **Concrete deliverables**: `seed/backend/lib/noctusai_lib/domain/ai/tool_audit.py` (175 lines — `AuditRecord` + `AuditWriter` + `make_audit_writer(db, table_class)` + `_safe_jsonable` + `now_utc()`); migration template at `noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template` (Postgres JSONB, 5 indexes, RLS scaffold); 9 tests at `seed/backend/lib/tests/domain/ai/test_tool_audit.py`; `KB § PATTERNS/llm-tool-audit.md` (NEW, 8 sections + 4 worked SQL queries + adoption checklist); `KB § PATTERNS/llm-bot-security.md` (NEW, 6 sections folding sibling `security-hardening` artifact). **Schema improvements over sibling**: indexed `status` column, `(conversation_id, started_at)` composite index, JSONB instead of TEXT. Bundled into commit `bf0bfe3` alongside parallel agent's scheduler-primitive work. | Claude Opus 4.7 |
| 2026-05-03 | **Tier 4 confirm-and-leave ✅ (no execution needed).** Re-read all three deferred drafts (`agno-dev-team-future-direction`, `dev-observability-bot-future-direction`, `user-context-bot-future-direction`) — all carry "Deferred — implementation not scheduled" status verbatim. §12 No-leftovers reactivation triggers stay durable. No reactivation signal from user; per Phase 4 of THIS batch, they remain untouched. Sibling-path references in their PROJECT.md files are execution-scoped (vanish at apply-inline-then-delete); KB has zero residual references. | Claude Opus 4.7 |
| 2026-05-03 | **Remaining work** (carry-forward beyond this session): Tier 1.c `scheduling-engine-seed` (7 phases — `SchedulingService` lift into `noctusai_lib.domain.scheduling`); Tier 1.d `whatsapp-seed-absorption` (9 phases — WhatsApp connector + chatbot framework + Calendar/Maps adapters); Tier 3 `imobi-scheduling-bot-creation` (10+ phases — bot product, consumes all Tier 1 substrate). Each requires its own focused-session pickup; the §6 phase plans are durable in their respective PROJECT.md files. **Sibling repo `~/Documents/repository/NoctusAI/whatsapp-google-scheduling/` still alive** at session close — the §12 No-leftovers constraints in each child guarantee post-deletion survival of the work itself. | Claude Opus 4.7 |
