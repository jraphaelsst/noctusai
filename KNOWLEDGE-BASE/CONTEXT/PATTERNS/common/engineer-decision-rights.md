# Engineer decision rights — what an executor may decide inside a slice, and how it is logged

**Status: opt-in pilot (D32), active for `product-engineer` only.** The other six executors reference this doc marked "pilot: inactive until the pilot review" (2026-11-23); activation criterion and decision lookup: `project-history/assistant-chatbot/PROJECT.md` sections 1-2.

**What it is.** The decision-rights layer of the executor standing protocol, with `product-engineer` as the reference (`.claude/agents/product-engineer.md` §6-§7) and every other executor (backend, frontend, devops, integrations, ai, test, tooling) referencing it by owner decision D32 (2026-11-09), inactive until the pilot review: which decisions an executor makes alone, which it makes and flags for review before the merge, which it must stop and escalate; the product-minded traits that go with that autonomy; the append-only log that makes every decision checkable; and the audit that blocks a merge when the log and the diff disagree.

**Why it exists.** Owner decision 2026-11-09: the engineer "decides small things in scope" so the owner is not flooded with questions about edge cases, error wording and naming, and the owner stays in control of everything that is not small. The risk is the one the sources name: many small decisions add up to a large one, and a log nobody reads decays. So the autonomy is designed per decision (not per agent), with a closed list of pre-approved classes, caps, an independent audit before merge, and an outcome review after ship.

**How to use it.** `.claude/agents/product-engineer.md` §6-§7 carries one line per rule and points here (the reference); each of the 7 other executor files carries one rule line and the same pointer. The executor classifies before acting (§3), logs (§5), and reads the audit blockers (§7) before returning. compliance-reviewer runs the audit (§7) on every executor slice, not only product-engineer's. product-analyst judges outcomes (§8). The house mechanism wins over the general sources: where this doc and `KB § PATTERNS/devops/owner-operations.md` §2 disagree on the ladder, that doc is the rule and this one is wrong — fix it on contact.

Origin: the v1 contract `project-history/assistant-chatbot/contracts/decision-log.md` and the research `project-history/assistant-chatbot/research/decision-rights-research.md` (both 2026-11-09). This doc carries their conclusions so it stays valid when those folders are archived.

---

## 1 · House term ↔ standard term

| House term | Standard term | Where it lives |
|---|---|---|
| `autonomous` tier | Delegation Poker level 6 "Inquire: I will inquire after they decide"; ITIL standard change | §3 · owner-operations §2 L3 |
| `notify` tier | Delegation Poker level 5 "Advise: I will advise but they decide", with a pre-merge veto; DACI "Informed" before the merge | §3 · owner-operations §2 L3 + veto |
| `escalate` tier | Bain RAPID: the engineer is R (recommend) and P (perform), the owner is D (decide); Bezos Type 1 decision | §3 · owner-operations §2 L2 |
| closed `class` list | ITIL change model for recurring standard changes | §4 |
| decision-log row | ADR (Nygard 2011): numbered, never reused, superseded not edited | §5 |
| `Decisions:` commit trailer | the join key between the diff and the log | §5 |
| caps (5 / 3) and check-in | stopping conditions on an agent loop (Anthropic, *Building effective agents*) | §6 |
| pre-merge audit | the independent reviewer, so the agent never grades itself | §7 |

---

## 2 · The product-minded engineer (the traits, and the one divergence)

**Sources.** Orosz, *The Product-Minded Engineer* (blog.pragmaticengineer.com/the-product-minded-engineer/): "Product-minded engineers are developers with lots of interest in the product itself", nine traits: proactive with product ideas, interest in the business and user data, curiosity about "why?", strong communicators with non-engineers, **offering product/engineering trade-offs upfront**, **pragmatic handling of edge cases**, **quick product validation cycles**, **end-to-end feature ownership**, product instincts through repeated learning cycles. PostHog handbook (posthog.com/product-engineer/what-is-a-product-engineer): "Builds products for *real users*", "Writes full stack code", and "They decide what to build. They own pricing, revenue, and user experience." (read 2026-11-09.)

**What the house takes.** Trade-offs offered up front, pragmatic edge cases, early validation, end-to-end ownership of the slice, measurement of what ships. These are the `tradeoffs:` · `edge-cases:` · `validated-with:` return legs.

**What the house does not take.** PostHog engineers decide what to build, own pricing and support customers. Here the owner decides what to build and in what order, pricing is the owner's with the accountant, and no agent ever sends anything to a customer (CLAUDE.md §1; `KB § PATTERNS/devops/owner-operations.md` §2 "Never L3"). The engineer proposes. PostHog's own handbook names the failure of the other model: autonomy without a growth-review feedback loop becomes directionless, which is why §8 (outcome review) exists.

**Failure modes of the trait set.** Shipping without measuring; gold-plating edge cases; spec-taker passivity (building what was written without saying a cheaper option exists).

---

## 3 · Tiers and criteria

A decision takes the HIGHEST tier any criterion gives it. The ladder reuses `owner-operations.md` §2 (L0 inform, L1 suggest, L2 act-with-approval, L3 act-and-report) rather than forking it.

- `autonomous` (= L3): decide and log. Allowed ONLY for the closed `class` list in §4.
- `notify` (= L3 with a pre-merge veto): decide, log, and have compliance-reviewer confirm before merge.
- `escalate` (= L2): stop and ask the tech-lead, who asks the owner through `noc-questionnaire`.

| | criterion | autonomous | notify | escalate |
|---|---|---|---|---|
| C1 | scope | implements an acceptance criterion as written | fills a gap the criteria don't cover | changes, adds or drops a criterion, or changes the plan route |
| C2 | reversibility | one `git revert`, nothing outside git | shared or seed code | migration, backfill or external effect |
| C3 | blast radius | inside the slice's declared paths | same product outside those paths, or seed internals | another product, seed public API, CI or keepers |
| C4 | contract | none | none | any new or changed endpoint, schema, table, RLS, access tier or event shape |
| C5 | user-visible | internal text only | non-customer detail inside an approved mockup | new screen, or customer-facing wording |
| C6 | security / LGPD / money | none | tightening only | any loosening, new personal data, or any money path |
| C7 | irreversible ops | none | none | prod exposure, deploy, deletion, sending to customers |
| C8 | cost | none | none | a new runtime dependency or a new paid call path |
| C9 | novelty | a §4 class | none | anything not in §4 |

> C5 note (owner 2026-11-11): the absence of a mockup is never an escalate reason; mockups are made only on the owner's ask and never gate a build.

**Surprise test.** Answer each; any yes or unsure moves the decision up one tier (house no-silent-errors: ambiguity means ask).
1. Would the owner be surprised to read this?
2. Does it change an acceptance criterion or the next plan step?
3. Would one revert fail to undo it?
4. Will a customer see, receive or pay something different?
5. Does another product, contract, table or tier see a different shape?
6. Is this the third small step in the same direction?
7. Would a mistake compound before anyone looks?
8. Am I stretching a pre-approved class to fit?

**Why these criteria.** Reversibility is the base axis (Bezos 2015 letter: Type 2 decisions "can and should be made quickly by high judgment individuals", Type 1 are "made methodically, carefully, slowly, with great deliberation and consultation"). Risk-rating a tool or action by write access, reversibility, permissions and financial impact, and keeping human oversight for high-risk actions "until confidence in the agent's reliability grows", is OpenAI's *A practical guide to building agents* (p.26, p.31). Initiative only inside the approved intent (the acceptance criteria and the plan route) is the mission-command reading (ADP 6-0 via army.mil; the primary PDF was not reachable, so only the secondary text is cited). Autonomy as a declared setting, here the "approver" level where the user engages only on consequential actions, is Feng, McDonald and Zhang, *Levels of Autonomy for AI Agents* (arXiv 2506.12469).

---

## 4 · Enums (closed sets; no free-text status)

- `tier`: `autonomous` · `notify` · `escalate`
- `class` (the pre-approved autonomous list): `edge_case` · `internal_error_text` · `internal_naming` · `test_added` · `in_file_refactor` · `log_line` · `validation_tightened` · `null_handling` · `typo` · `other`. `other` is never autonomous. The list grows only by the promotion rule below.
- `criteria_hit[]`: `C1` … `C9`
- `reversibility`: `one_commit` · `shared_code` · `needs_migration` · `external_effect`
- `blast_radius`: `slice_paths` · `same_product` · `seed_internal` · `cross_product` · `seed_api` · `ci_keepers`
- `surprise_test`: `all_no` · `escalated_by_test`
- `outcome`: `pending_review` · `accepted` · `vetoed` · `reclassified` · `superseded`
- `reviewer_kind`: `compliance_reviewer` · `tech_lead` · `owner` · `product_analyst`

**Promotion and demotion** (owner-operations §2). A class with 10 clean, accepted, recorded uses may be proposed for a higher tier; the owner ratifies each change. A class that gets vetoed or reclassified is demoted from autonomous until it has 10 clean uses again. Loosening a check is never a class, never pre-approved.

---

## 5 · The log row and the commit trailer

One row per decision: `id` (`D-<slice>-<NNN>`, sequential, never reused), `ts`, `agent` (any executor: the tool accepts any non-empty name), `slice_id`, `branch`, `commit_sha`†, `ac_ref`†, `tier`, `class`, `criteria_hit[]`, `reversibility`, `blast_radius`, `surprise_test`, `paths[]`, `decision` (free text, at most 200 characters, "We will …"), `options_considered`†, `revert_hint`†, `supersedes`† († optional). A review is a separate append row: `{id_ref, outcome, reviewer_kind, reviewer, note†}`. A status changes only through a NEW row that supersedes the old one (Nygard: a reversed decision is kept and marked superseded, never deleted or edited).

Commits carry `Decisions: D-…, D-…` so the diff and the log join. `ac_ref` absent forces non-autonomous (no acceptance criterion served means the decision is not implementing the intent).

**Storage and tool.** Append-only NDJSON through `noctus.dev.ledger_store` at `project-history/decisions/<YYYY-MM>/<slice_id>.ndjson`, written with `noctus.dev.decision_log` actions `record` · `review` · `list` · `audit` (`audit slice=<id> base=<ref>` returns the §7 findings). An offline keeper validates staged rows. The shape rule is `KB § PATTERNS/architect/measurement-by-design.md`: append-only, closed sets as enums, status by superseding row.

---

## 6 · Bounds (starting values; data retunes them, the owner ratifies each change)

| Failure mode | Bound |
|---|---|
| Scope creep through many small decisions | At most 5 `autonomous` and 3 `notify` rows per slice; the next decision is a check-in with the tech-lead (a stopping condition, per Anthropic: "include stopping conditions … to maintain control"; "higher costs, and the potential for compounding errors"). |
| Salami slicing (an escalate-class change split into small pieces) | Classification runs against the WHOLE slice diff vs its base, not commit by commit. The same `class` on the same file 3 times becomes ONE decision, reclassified up. |
| Normalization of deviance (relaxations accumulate; secondary source, used only as a named failure mode) | Loosening is not a class. A vetoed class drops a tier. |
| Interpreting intent too loosely | No `ac_ref`, no autonomy. |
| Class stretching (a new screen labelled "edge case") | Closed enum; audit checks compare class with what the diff touches (§7). |
| Over-escalation (the owner flooded, the original complaint) | The promotion rule; escalations are batched through `noc-questionnaire`; escalations per slice are measured. |
| Reviewer rubber-stamp | The 1-in-5 sample (§7), independent of the agent's own tier claim. |

The caps (5 / 3), the sample rate (1 in 5) and the 3-in-a-row trigger are our judgement calls, not sourced numbers; the owner ratified them as starting values on 2026-11-09.

---

## 7 · The pre-merge audit (compliance-reviewer; blocks the merge)

The merge path (`task_branch` enqueue/integrate) runs this audit automatically in warn mode (telemetry `~/.noctus/decision-audit.ndjson`; promote-to-block criterion in contract `decision-log.md` §10); compliance-reviewer's run is additional, not the only gate. Commit trailers: `Spec: <path>`; `AC: <n>` must be a real numbered acceptance criterion of that spec; `Assigned: <n>` declares spec-assigned work on a gated surface (the criterion must name it); `Decided: <what>` + `Decisions: D-…` for anything the executor decided. Rows may carry `product: <slug>`.

Run `noctus.dev.decision_log action=audit slice=<id> base=<ref> spec=<spec path>`. The merge is blocked when any of these holds:
1. the diff touches migrations, RLS, access tiers or contract files and neither an owner-accepted `escalate` row nor a spec `Assigned:` criterion covers them;
2. a route or page is added, or customer-facing text changes, under an `autonomous` row;
3. billing, secrets or auth are loosened;
4. paths outside the declared slice paths change while a row says `slice_paths`;
5. a runtime dependency is added without a `notify`-or-higher row;
6. a changed file has no row and no `ac_ref` (an unlogged decision);
7. a row says `one_commit` but the diff has a migration;
8. a cap is exceeded.

compliance-reviewer also re-runs the surprise test on 1 in 5 `autonomous` rows and on every `class=other` row, and checks that every acceptance criterion has at least one test. A red is "reclassify and ask", never "merge silently": reclassification is a superseding row with `outcome=reclassified`, and an upward reclassification demotes that class (§4).

---

## 8 · The outcome review (product-analyst, post-ship)

product-analyst reads the measured data and writes `review` rows with `reviewer_kind=product_analyst` judging decisions in hindsight (accepted stands, vetoed or reclassified is the misclassification evidence the promotion rule uses). It also writes council-ledger `outcome` events (`noctus.dev.council_ledger action=record_event`) for objections the shipped result proved right or wrong. The metrics this enables: decisions per slice, misclassification rate per class, veto rate per class, escalations per slice. → agent `product-analyst` · `KB § PATTERNS/product/product-analysis-canon.md`.

---

## Checklist (copyable)

- [ ] Every decision classified against C1-C9 and the 8-question surprise test; highest tier taken.
- [ ] `autonomous` only for a §4 class with an `ac_ref`; never `other`.
- [ ] Caps respected (5 / 3); same class + same file 3 times merged and reclassified.
- [ ] Each decision recorded with `noctus.dev.decision_log record`; commits carry `Decisions:`.
- [ ] `escalate` items surfaced, not decided; trade-offs, edge cases and validation named in the return legs.
- [ ] `action=audit` run on the slice diff before returning; no blocker open.

## Sources (read 2026-11-09 unless marked)

Bezos 2015 shareholder letter (SEC 8-K Ex. 99.1) · Bain RAPID (bain.com/insights/rapid-decision-making/) · Atlassian DACI (atlassian.com/team-playbook/plays/daci) · Management 3.0 Delegation Poker (management30.com/practice/delegation-poker/) · Nygard, *Documenting Architecture Decisions* (cognitect.com, 2011) and adr.github.io · Google SRE book ch. 1 and *Reliable Product Launches* (sre.google/sre-book/) · Anthropic, *Building effective agents* and *Our framework for developing safe and trustworthy agents* · OpenAI, *A practical guide to building agents* (PDF) · Feng, McDonald, Zhang, *Levels of Autonomy for AI Agents* (arXiv 2506.12469) · Orosz, *The Product-Minded Engineer* · PostHog handbook, product engineer. **Weak or not verified:** ADP 6-0 primary text (secondary army.mil article only); ITIL 4 glossary (paywalled; IT Process Maps, ITIL v3 terms, used); Vaughan on normalization of deviance (secondary only); the Orosz and PostHog second-hand quotes of Lee Robinson and incident.io (originals not opened).

## Composes with

`.claude/agents/product-engineer.md` (reference) · the 7 other executor agents (inherit) · agent `compliance-reviewer` (the §7 audit) · agent `product-analyst` (§8) · `KB § PATTERNS/devops/owner-operations.md` §2 · `KB § PATTERNS/architect/measurement-by-design.md` · `KB § PATTERNS/common/ledger-store.md` · `KB § PATTERNS/common/engineer-operating-discipline.md` (the craft this builds on) · `KB § PATTERNS/common/drift-fix-on-contact.md`.
