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

## Synthesis (at project close — 2026-05-04)

> Curated distillation. The 4 lessons (L1-L4), 5 interesting findings (F1-F5), and 8 knowledge pieces (K1-K8) above are the durable signal. This synthesis arranges them around the three highest-leverage takeaways for future agents.

### Takeaway 1: The architect-engineer split is the right primitive for non-trivial projects with parallelism axes

L4 + F4 + the live execution pattern across 5 engineers prove this. The rule (formalized 2026-05-04 mid-project) says: architect plans + dispatches + evaluates + stays-with-user; engineers execute in dedicated worktrees. The corollary that this project surfaced: **engineers MUST be self-contained at brief-time** — they don't see the conversation, don't see prior phases' implicit decisions, don't share a memory pool with the architect. The brief is the contract. Get the brief right and the engineer ships clean; get it wrong and you spend the savings on integration debugging.

The five engineers ran with prompts of ~700-1000 words each. That's the tax. Wall-clock saved on Phases 2/3/4/5/6 vs serial: probably >50%. Architect context budget: stayed clean enough to handle the model-file merge resolution + Phase 7 close in a single session.

**For future agents.** When a project has ≥2 file-disjoint chunks, dispatch parallel engineers. The brief template should pin: worktree path, branch name, integration contracts (signatures), exit criteria, do-not lists, report-back length cap. See `KB § PATTERNS/master-tree-parallel-batches.md` for the multi-product variant.

### Takeaway 2: Methodology rules earn trust by being explicit-about-stopping

F5 captures this. The collision protocol said STOP after the second revert + don't loop-fight + don't file a collision-report-project. When it fired in real use, the user's reaction wasn't "huh, OK" — it was *"i loved this stop per collision protocol <3"*. That's affective trust, not just functional trust. The rule felt good in real use because it removed ambiguity at the moment ambiguity costs the most.

Sibling protocols (parallel-agent collision, the safety-nets-become-learnings rule, the worktree-per-engineer rule) all share this shape: explicit halt conditions + named next-actions + no loop-fight. The pattern: future protocols benefit from being similarly named-and-stopping rather than action-defaulting.

**For future methodology authoring.** When writing a rule that fires under failure conditions, name the STOP condition precisely + name the named-next-action precisely + forbid the loop-fight default. The user's affective response to the rule is a signal — methodology that feels right is methodology that survives.

### Takeaway 3: Seed-first investment compounds; verify-the-seed-ships-it before locking

L1 + L2 + the Phase 0 audit prove this. Eight seed modules were runtime-ready by the time the port started; that's why the port was 8 phases instead of 24. The `whatsapp-seed-absorption` project that ran before this one was the leverage: it pre-shipped everything `media-scheduling` needed to consume. Seed work pays compound interest.

The verify-the-seed-ships-it sub-rule sharpened during this project: it's not just "does the runtime adapter exist?" but "does it exist in the canonical Protocol+Fake+Real+factory shape?" Half-shipped (Protocol+Real or Protocol+Fake only) generates consumer-side forks. Phase 0.5 backfilled three modules to canonical shape; the gold-standard Fake+Real adapter pattern shipped to KB as the durable byproduct.

The corollary surfacing during Phase 0: the recurrence rule fires *inside* the seed too. `domain.chatbot` ↔ `domain.conversation` was N=2 inside seed; only visible because the audit listed both `__init__.py` files. Future audits should default to listing-then-reading every sibling alongside the target.

**For future agents.** Run Phase 0 against the canonical shape, not just against runtime existence. List sibling modules every time. When you find a gap, fix at seed (with the Fake+Real shape) before consuming downstream.

### What didn't generalize

The hybrid SQLAlchemy + Pydantic models pattern (forced by the seed audit-writer contract requiring SQLAlchemy + the product being Supabase-client-native) is product-specific. Don't copy it elsewhere unless the same tension exists.

The LID-aware first-inbound capture is real-estate-WhatsApp-specific. If a second WhatsApp product ships, recurrence-rule fires and the abstraction belongs in seed. Until N=2, accept-with-rationale (entry filed).

### Open follow-up projects filed at close

- `worktree-aware-pre-commit-hook` — hook scans `noctusai_home` not the committing worktree
- `mcp-review-session-worktree-aware` — same shape, MCP tool side
- `mcp-workspace-per-call-override` — scaffold_product needs per-call workspace target
- `vite-config-factory-framework-deps` — `FRAMEWORK_DEPS` missing `clsx`/`tailwind-merge`/`class-variance-authority`
- `mcp-corpus-baseline-refresh` — corpus-tolerance tests need to absorb incremental product additions
- `seed-protocol-runtime-checkable-sweep` — sweep all seed Protocols for missing `@runtime_checkable`
- `worktree-venv-isolation` — each worktree should have its own venv (or symlink)
- `media-scheduling-real-data-migration` — port the real production WhatsApp ↔ OpenAI conversations from source DB
- `media-scheduling-travel-cache` — `route_groups` is route-plan, not generic origin/dest cache

