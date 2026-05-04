# Findings — Media Scheduling Port

> Curated knowledge artifact. Per `feedback_knowledge_tracking.md` (2026-05-03), every non-trivial project maintains `findings.md` at root with five categories: errors / mistakes-slips / lessons / interesting-findings / knowledge-pieces. Synthesized at close.
>
> Distinct from sibling artifacts:
> - `MEDIA-SCHEDULING-PORT-LOG.md` (worktree root) — live narrative + collision case study + reflections.
> - `phase_learnings.db` (gitignored) — atomic per-phase records.
> - `PROJECT.md §11` — what-we-did chronicle.
> - **This file** — what-we-LEARNED, curated, the durable transferable signal.

---

## Errors

> Things that broke or returned wrong results. Concrete failures, with what fixed them.

### E1 — Phase 0.5 work lost during parallel-agent collision (2026-05-03 → 2026-05-04)

**What broke.** Original Phase 0.5 executed in the main worktree at `/Users/rapha/Documents/repository/NoctusAI/noctusai`. In parallel, a different session was doing methodology-formalization work on `architect-engineer-roles` branch in the SAME worktree. A branch-switch in the main worktree (reflog: `checkout: moving from progressive-refinement-archive to architect-engineer-roles`) discarded my uncommitted Phase 0.5 seed changes (untracked new files vanished; modified tracked files reverted to origin/main).

**What fixed it.** The parallel-agent collision protocol fired — STOP, do NOT loop-fight, surface to user. The user confirmed the parallel work was done. Re-executed in a dedicated worktree at `noctusai-worktrees/media-scheduling-port-resume/` per the just-shipped *worktree-per-engineer* rule. Per-phase commit cadence adopted to reduce future collision blast radius.

**What survived (durable):** memory entries (outside git), KB pattern doc (untracked file persisted across the branch switch — likely because no source-controlled path collided), KB INDEX entry (the user's commit landed it on `origin/main` directly).

---

## Mistakes / Slips

> Methodology slips — caught and corrected. Patterns of mis-thinking worth flagging so future agents don't repeat them.

### M1 — Worked in the main worktree without isolation while parallel work was active

**The slip.** When I started Phase 0.5, I knew (from the `personal-finance-wiring` worktree visible in `git worktree list`) that parallel work was happening. I should have created a dedicated worktree from the start — but at that point the worktree-per-engineer rule wasn't yet formally shipped (it shipped during this collision, in the architect-engineer-roles work). So I worked in the main worktree, which is the default mental model from before the rule existed.

**The corrective.** The new rule (`feedback_branching_first_orchestration.md` 2026-05-04 amendment): *"`git worktree add` per engineer for true filesystem isolation when 2+ parallel."* The signal that this rule applies: presence of any other worktree in `git worktree list`, OR knowledge that another session is active.

**Future agent rule:** at session start, run `git worktree list` AND `git branch -a`. If any other worktree is active OR multiple branches show recent commits, create a dedicated worktree before any non-trivial work.

---

## Lessons

> Durable rules-of-thumb. Candidates for promotion to KB / memory.

### L1 — "Verify the seed ships it" is a SHIPPING-READINESS gate, not just a Protocol check

A seed module can have a Protocol AND a Fake AND a real adapter and STILL have a gap. The gap to look for is not "does the runtime path exist?" but "does the runtime path match the Fake+Real adapter shape with a factory?" When the shape is missing, consumer code starts forking *because* the consumer has to glue the parts together themselves.

**Promoted.** Sub-rule added to `feedback_verify_seed_ships_it.md` 2026-05-03: "verify the SHAPE not just the parts." Pattern doc shipped at `KB § PATTERNS/seed-fake-real-adapter.md`.

### L2 — Recurrence rule fires INSIDE the seed too

`domain.chatbot` and `domain.conversation` were near-identical twins, both shipped, both with their own test directories. The recurrence rule (N=2 → triage time) is normally framed as cross-products, but it applies inside seed itself.

**Promoted.** Sub-rule added to `feedback_recurrence_rule.md` 2026-05-03: "the rule fires INSIDE seed too." Practical Phase 0 hygiene: list-then-read every sibling module alongside the one being consumed.

### L3 — Per-phase local commits (not project-end-only) are required when parallel sessions are active

Original methodology said: "no auto-commit; per-phase local commit; final commit + push at project close." That cadence assumes single-session work. In parallel-session environments, uncommitted work in one session is at risk from branch-switches in another. The collision (E1) cost a full Phase 0.5's worth of seed code because nothing had been committed yet.

**Corrective adopted in Phase 0.5 redo:** commit at end of EVERY phase to the worktree's branch. The branch-tip is then a recoverable checkpoint even if the worktree gets stomped.

**Promotion candidate:** strengthen `feedback_no_auto_commit.md` with a sub-rule — "per-phase commit cadence is REQUIRED when ≥2 sessions are active (visible via `git worktree list` showing >1 worktree, or known from context)."

### L4 — Memory survives anything; project files survive only what git protects

The collision wiped seed code edits + project folder + log file. Memory updates landed and stayed (they're in `~/.claude/projects/.../memory/`, outside the git repo). The KB pattern doc survived because it was a NEW path that didn't conflict with anything on the post-switch branch.

**Implication:** when working in a contested-tree environment, prefer landing valuable artifacts in (a) memory, (b) KB-as-new-files, (c) the branch via per-phase commits. Anything that lives only as untracked-in-working-tree is at risk.

---

## Interesting findings

> Non-obvious or surprising observations. Not necessarily promotable, but worth remembering.

### F1 — Seed docstrings consistently include provenance (lifted-from + lifted-by + lifted-when)

Every seed module absorbed from the sibling `whatsapp-google-scheduling/` repo has a docstring stanza like *"Lifted from `whatsapp-google-scheduling/app/services/waha/` 2026-05-03 via `projects/whatsapp-seed-absorption/`."* Exemplary — a future audit can trace any seed module back to its origin. Convention to enforce for all future seed absorptions.

### F2 — `BlockedInterval` carries `assignee_id` "for future therapy / multi-professional use cases"

The seed `scheduling.engine.BlockedInterval` already includes a field the source repo didn't have — explicit forward-thinking about the next consumer (therapy multi-professional). Right kind of seed-side investment: speculative-but-tiny, costless to consumers that don't need it, prevents a forced refactor when the next consumer arrives.

### F3 — `webhook_signatures.webhook_endpoint(...)` ships `bypass_when_unset` AS A NAMED AFFORDANCE

The seed didn't just leave bypass to consumer code — it surfaced it as an explicit named flag with WARNING logging baked in. The "no silent errors" rule meets the "no workarounds" rule cleanly: the affordance exists and IS observable.

### F4 — The collision IS the case study for the rule that fixes it

The architect-engineer-roles formalization shipped DURING this collision, in the parallel session that caused it. The rule it adds (`git worktree add` per engineer) is the structural fix for exactly this failure mode. Two layers of methodology evolution in real time:
1. Methodology → safety net (parallel-agent-collision protocol) catches the failure
2. Failure → learning → methodology amendment (worktree-per-engineer) closes the structural gap
3. Future occurrences hit the updated rule, not the original gap

This IS the "safety nets capture failures; failures become learnings; methodology evolves" rule playing out in one continuous arc.

### F5 — User feedback "i loved this stop per collision protocol <3" — the protocol felt *good* in real use

Not just "it worked" — the user expressed positive reaction. Confirms that protocol design (STOP + factual report + no loop-fight) preserves trust in ambiguous situations. Future protocols benefit from being similarly explicit-about-stopping rather than action-defaulting.

---

## Knowledge pieces

> Concrete facts about the system worth remembering. Project-scoped references.

### K1 — Source repo location

`/Users/rapha/Documents/repository/NoctusAI/whatsapp-google-scheduling/` — the mature standalone FastAPI service this port consumes. Sibling of noc, not inside it.

### K2 — Tool-call audit lives at `noctusai_lib/domain/ai/tool_audit.py`

Not `noctusai_lib/domain/audit/` or `noctusai_lib/security/`. ai/ namespace because audits are AI-tool-call-scoped. Per-product `tool_call_audits` table; lib does NOT ship an ORM model (LGPD cross-product block). Migration template at `noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template`.

### K3 — `noctusai_lib.integrations.llm.chat.chat_completion(response_format=)` covers OpenAI structured-output

No custom structured-output path needed — source's OpenAI Responses API usage maps to `chat_completion(messages=..., response_format={"type": "json_schema", ...})`.

### K4 — Two parallel chatbot/conversation modules exist; consume `chatbot`, ignore `conversation`

Until G4 deletes the fork — production consumers must always `from noctusai_lib.domain.chatbot import ...`, never `domain.conversation`. Latter is obsolete; only its own test directory imports.

### K5 — Gold-standard Fake+Real adapter shape (the canonical pattern)

```
integrations/<name>/
├── __init__.py          # Public surface + get_<name>_adapter(...) factory
├── types.py             # Value objects + Protocol(s)
├── mappers.py           # Pure-function shape converters
├── fake_adapter.py      # Deterministic in-memory implementation
├── <vendor>_adapter.py  # Real-runtime adapter
├── credentials.py       # (when applicable) per-tenant credential resolver
└── settings.py          # (when applicable) Pydantic settings
```

Set by `integrations.google_calendar` + `integrations.google_maps`. Backfilled into `whatsapp`, `redis`, `chatbot.buffer` 2026-05-03/04 via Phase 0.5.

### K6 — Worktree location for THIS project

`/Users/rapha/Documents/repository/NoctusAI/noctusai-worktrees/media-scheduling-port-resume/` on branch `media-scheduling-port-resume` (off `origin/main`). The original branch `media-scheduling-port` was repurposed by parallel methodology work; do not use it for port code.

### K7 — Source DB conversations are REAL

Real WhatsApp ↔ OpenAI GPT exchanges via WAHA. Not test fixtures. Phase 2 schema port preserves data fidelity.

### K8 — Real conversations live IN production state

User confirmed: "this system actually works, bro. no fake mocks approvals anymore lol." Phase 2 must treat the source DB as production data, not test data.

---

## Synthesis (at project close)

*(filled at project close — distills the above into the curated artifact for future-agent consumption)*
