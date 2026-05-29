# Repetitive procedure → skill (N≥2 recurrence)

> **The rule.** When the same multi-step **procedure** runs on the platform a second time — same orient→act sequence, same trigger phrasing, regardless of the surface it's applied to — it becomes a **skill candidate** at N=2 and **MUST be codified as a `.claude/skills/noc-<verb-noun>/SKILL.md` skill at N=3**. Shipping the 4th hand-performance of the same procedure is forbidden, by the same logic as the code-DRY rule.

This is the **DRY rule for procedures**. It sits as a sibling of two adjacent rules, with a precise division of labor:

| Surface that recurs | Rule | Codified form | Anchor |
|---|---|---|---|
| **Code** (function / module / shape) | DRY — the recurrence rule | extract function / class / seed primitive | `KB § PATTERNS/architect/project-execution.md § 2.7` |
| **Methodology / doc / prose** (rule / discipline / lesson) | Methodology codification pipeline | KB pattern + CLAUDE.md §1 line + optional keeper | `KB § PATTERNS/common/methodology-codification-pipeline.md` |
| **Procedure** (orient→act sequence the orchestrator runs by hand) | **Repetitive procedure → skill at N≥2** *(this doc)* | `.claude/skills/noc-<verb-noun>/SKILL.md` | here |

The three rules cover three distinct kinds of repetition — and overlap by design (a procedure that mechanizes a methodology rule is exactly what a noc-skill is). The point of this doc is to name the third leg, so it stops being silently improvised.

---

## 1 · Why this rule exists

The platform already has 14 procedure skills under `.claude/skills/noc-*` plus `skill-creator`. Each one was authored after the orchestrator had performed the same multi-step procedure several times by hand — wrap-up surveys, seed-verify gates, triage bookkeeping, container debugging, dispatch waves. The codification was right; the *trigger* was inconsistent. Sometimes a skill landed after N=2 (good); sometimes after N=5 with a "we keep doing this manually, let's make it a skill" remark (late). Without an explicit recurrence threshold, the skill layer **could** grow but didn't **have to** grow — so each new agent inherited the cost of re-improvising procedures that had already been performed.

Naming the threshold (N=2 = candidate, N≥3 = mandatory) removes the judgment call. The orchestrator (or any agent) recognizes the second instance, checks the cache to confirm no sibling skill already covers it, dispatches `skill-creator`. The cost of the skill is paid once; every future invocation auto-triggers on the phrase the human would have typed anyway.

---

## 2 · What qualifies as a "procedure" (gate)

Not every repeated action is a procedure. A skill is the right home only when **all four** hold:

1. **Multi-step.** A single MCP call (`noctus.dev.review` / `kb_search` / a one-shot tool) is not a procedure — it is just the tool. Procedures are sequences (`orient → check → act → verify → surface`).
2. **Orient → act shape.** The agent reaches for context first (cache, ndjson, recent commits, file state) **before** taking the action. A purely mechanical action with no orient step belongs in a Stage-4 keeper (auto-fires) or a single MCP tool, not a skill.
3. **Auto-triggerable on phrases.** A skill is loaded by the harness when the user (or the agent's own narration) says the right thing. If the procedure has no recognizable trigger phrase — if the orchestrator just "remembers to do it" — it's not a skill yet. Often the right move is to **name the trigger first**, observe whether the name actually fires, *then* codify.
4. **Generalizable beyond one instance.** "The procedure I run to deploy *this specific product*" is not a skill — it's a Makefile target. The procedure has to apply across products / contexts / sessions.

A repetition that fails any of those four gates is **not** a procedure under this rule. The right destination is one of: a Stage-4 keeper (mechanical + auto-firing), a single new MCP tool (one-shot action), a KB pattern (judgment-dependent guidance), an `accept-with-rationale` entry (one-off divergence).

---

## 3 · The recipe (N=2 recognition → skill ship)

The procedure for **codifying a procedure** (this rule applies to itself):

### 3.1 Recognize at N=2

Surfaces where N=2 typically shows up:
- A session in which the orchestrator narrates "we just did this last week" or "I'm doing the same thing I did in the previous session."
- A wrap-up survey (`noc-wrap-up` skill) catches the second instance — wrap-up itself catches recurrence proactively.
- The auto-improvement ndjson contains two recent s2-memory entries whose `description` reads as the same procedure applied to different surfaces.
- A dispatch brief that copy-pastes 80% of a prior dispatch brief.

When N=2 hits, the orchestrator **announces it loudly** ("this is the second time we're running orient → check → act for X") — silent-handling forbidden (silent-skip = silent-error shape). The announcement is the trigger for the next step.

### 3.2 Decide: procedure or incidental?

Run the four-gate check from §2. If any gate fails, the right home is **not** a skill — file the alt-destination (keeper / tool / KB pattern / accept-with-rationale) instead. Skip steps 3.3-3.4.

### 3.3 Author via `skill-creator`

The `skill-creator` skill (`.claude/skills/skill-creator/SKILL.md`) encodes the authoring conventions: `noc-<verb-noun>` naming, description as verbatim trigger phrases, body as thin WORKFLOW + Guardrails + Depth pointer. The new skill ALWAYS points its `## Depth` line at a KB pattern (often this doc, when the procedure mechanizes a methodology rule). The skill carries the **procedure**; the KB carries the **depth** — do not copy-paste KB body into the skill (drift generator).

Per `skill-creator` rule 5 (user mandate): when a procedure moves INTO a skill, **delete it from its old home** (CLAUDE.md §2/§3 routing rows, duplicated memory entries, inline narration patterns). Re-home, do not duplicate.

### 3.4 Verify via 8-way sync

The skill landing goes through the standard 8-way-sync (`check_eight_way_sync`):
- New skill listed in CLAUDE.md §2 "Procedure skills" line (one-line update; pointer-only).
- New skill listed in CONTEXTUALIZE.md §4 procedure-skills bullet (mirrors §2).
- A KB depth pointer the skill's `## Depth` line resolves to (this is the doc, typically).
- `.claude/cache/agent-context.sqlite` mirrored next refresh; `noc-graph` rebuild surfaces the new harness_skill node.
- Memory index updated if the procedure was previously narrated there.

Run `python mcp/noctusai/cli.py --check-eight-way-sync` (or pre-commit's automatic invocation) before shipping.

---

## 4 · Anti-patterns (what NOT to do)

1. **Skill-blooming** — codifying a near-duplicate of an existing skill because the orchestrator didn't search first. The cure is the same Leg A discovery gate `noc-verify-seed` uses: `noctus.dev.code_similar_to_text` / `kb_neighbors` / `noctus.graph.query kinds=["harness_skill"]` BEFORE authoring. A score ≥0.85 against an existing skill means **extend the existing skill's trigger phrases**, not author a sibling.

2. **Skill-scope creep** — an existing skill that grew past its description's trigger phrases (e.g. `noc-wrap-up` slowly accumulating dispatch-tuning advice). The fix is **split, not bloat**: extract the drifted concern into a new sibling skill, rewrite the original's body to its original scope. Same logic as the §2.7 DRY rule applied to skills themselves.

3. **Inline-only convenience** — codifying a procedure that's specific to one session ("the steps I run when this particular bug appears"). If gate 4 (generalizable) fails, the convenience belongs in a `findings.md` or a project's `PROJECT.md`, not in the always-loaded skill layer (which costs router budget per session).

4. **Procedure-without-trigger** — authoring a skill whose description is "Use when working on X" rather than verbatim trigger phrases. The skill never fires; it adds to the router noise without ever paying back. Per `skill-creator` rule 2, the description IS the router — pack it with the literal phrases a user/agent would say.

5. **Codifying a single MCP call as a skill.** If the procedure reduces to one tool invocation, the right destination is documenting the tool better (or composing it into an existing skill), not authoring a new skill. Skills carry sequences.

---

## 5 · Worked example (the worked example)

The recent (and recurring) worked example: **noc-wrap-up + noc-verify-seed + noc-triage**, codified together 2026-05-28 (auto-improvement ndjson entry `2026-05-28T14:20:01.531684+00:00`, target `.claude/skills/noc-wrap-up + noc-verify-seed + noc-triage`, status `s3-codified`).

All three procedures had been run by hand multiple times in prior sessions:

- **`noc-wrap-up`** — the "honest 3-5 polish-item survey at wrap moments" procedure. Sources: `feedback_honest_wrap_up_assessment` memory entry (2026-05-26 evening, caught 11 silent test failures via this exact discipline) — N=2 by the next "anything else?" moment.
- **`noc-verify-seed`** — the "two-leg gate (discovery + existence) before dispatching a consume-seed slice" procedure. Sources: `feedback_verify_seed_ships_it{,_at_dispatch_time,_on_fork_base}` (THREE pre-existing memory entries, so already N≥3 at codification time — late by this rule's threshold).
- **`noc-triage`** — the "mechanized accept-with-rationale (auto-count + propose verdict + human ratifies)" procedure. Sources: `accept-with-rationale.md` KB pattern + every F/R/A divergence decision the orchestrator narrated.

The 2026-05-28 codification was a same-commit `s2→s3` compression (logged with `force=True` since the s2 prerequisites lived in pre-existing memory entries rather than fresh s2-memory ndjson entries). This sequence — **multiple memory entries describing the same procedure across surfaces → recognize at recurrence → author three skills in one slice → verify 8-way sync** — is exactly the recipe in §3 applied at scale.

**Generalization:** any time the auto-improvement ndjson contains ≥2 s2-memory entries whose `description` fields read as the same orient→act shape applied to different surfaces, this rule fires. The 2026-05-28 ship was overdue by months for each of the three procedures; making the threshold explicit (N=2 candidate, N≥3 mandatory) prevents that drift in future passes.

---

## 6 · Composes with

- `KB § PATTERNS/architect/project-execution.md § 2.7` — the DRY rule for **code**. This doc is its **procedure** sibling.
- `KB § PATTERNS/common/methodology-codification-pipeline.md` — the s1-s4 lifecycle. A skill is one form of s3 (skill = codified procedure, KB doc = codified rule, keeper = codified detector). All three can land for the same underlying rule; they reinforce, not replace.
- `KB § PATTERNS/architect/parallelization-first-orchestration.md` — the orchestrator's default mindset. Skills make parallelization cheap because the default behaviors are mechanized (each `noc-*` skill is one less thing the orchestrator has to reinvent per task).
- `.claude/skills/skill-creator/SKILL.md` — the procedure for authoring a procedure. Always invoked when this rule fires at N=3.
- `KB § PATTERNS/common/accept-with-rationale.md` — the right destination for a one-off (gate 4 fails). When the repetition is genuinely incidental, file `[A]` there instead of authoring a skill.
- `KB § PATTERNS/common/eight-way-sync.md` — the 8-surface sync rule that gates skill landings.
- `KB § PATTERNS/common/claude-md-router-discipline.md` — the keeper that gates CLAUDE.md §1's pointer-only invariant when this rule's one-line bullet lands.

---

## 7 · Stage status

- **Stage 1** (emergent) — surfaced by user 2026-05-29 ("have we talked about the repetitive-tasks-becomes-skill rule N>=2 recurrence?").
- **Stage 2** (memory) — `feedback_repetitive_task_skill_codification.md`.
- **Stage 3** (KB + CLAUDE.md + CONTEXTUALIZE.md) — **this doc** + the §1 one-liner + the §2 mirror.
- **Stage 4** (keeper detector) — **deferred** to the next pass. Candidate `check_recent_skills_have_index_provenance` (advisory; audits new `.claude/skills/noc-*` directories for an explicit "Born from N≥2 recurrence at <source>" provenance line). Logged as auto-improvement for next slice.

The 8-way-sync (`check_eight_way_sync`) already gates the skill-router-mirror invariants this rule depends on. The dedicated sub-keeper is value-additive (forces every new skill to declare provenance), not a precondition.
