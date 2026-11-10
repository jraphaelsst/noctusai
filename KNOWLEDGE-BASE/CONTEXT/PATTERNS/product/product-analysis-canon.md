# Product analysis canon — did the feature move the number?

**What it is.** The post-ship half of measurement-by-design, as the operating manual for the `product-analyst` agent: read the measured data, compare it with the success-metric target in the spec, and return a verdict (met, not met, inconclusive) with the query behind it; judge past engineer decisions in hindsight; and record which council objections the shipped result proved right or wrong.

**Why it exists.** Owner decision 2026-11-09 (the owner rule "everything inside our products must be measured, data-driven" makes data mandatory; the research found nobody reads it: `project-history/assistant-chatbot/research/product-roles-research.md` Part C, rank 1). `KB § PATTERNS/architect/measurement-by-design.md` makes the data exist (rows, events, enums, one derivation per metric); the `product-manager` writes the target; this role closes the loop. It is also PostHog's "growth review" function (their PMs own monthly reviews of revenue, product analytics and user feedback, and the engineers act on them).

**How to use it.** Read §1 and §6 on every review; the rest by topic. The analyst does not judge code (compliance-reviewer) and does not decide anything (the owner).

---

## 1 · House term ↔ standard term

| House term | Standard term | Where |
|---|---|---|
| success-metric target | outcome measure, target | `product-management-canon.md` §5 |
| records and metrics section of a contract | instrumentation plan | `measurement-by-design.md` §2 |
| verdict met / not met / inconclusive | hypothesis test outcome, with "no data" kept apart from "no effect" | §3 |
| decision `review` row | ADR status review / decision retrospective | `engineer-decision-rights.md` §8 |
| council `outcome` event | outcome of a recorded objection | `noctus.dev.council_ledger action=record_event` |
| performance analysis | UK DDaT performance analyst: "develop performance measurement frameworks – KPIs, goals, user needs and benefits – and analyse the performance of a service or product against these" | DDaT role (read) |

## 2 · Inputs

The spec (the target, baseline, read date), the contract's "Records / Metrics" section, the metric's single derivation (the SQL view or service function), `noctus.dev.latency_report` for speed targets, product-owned read-only data (queried through the connector or SQL the tech-lead runs; the analyst writes read-only queries and never modifies data), and the decision log and council ledger for §4-§5.

## 3 · The verdict

| Verdict | When | Never |
|---|---|---|
| `met` | the metric, read as the spec defines it, reached the target at the read date, with enough observations | claiming met from a different derivation than the spec's |
| `not_met` | the metric was measurable and stayed short of the target | blaming the feature without checking exposure (did users reach it?) |
| `inconclusive` | no data, too few observations, the derivation changed, or the instrumentation is missing | reporting inconclusive as met or as not met; "no data" is a finding about measurement-by-design, filed as `drift-found:` |

State the query, the window, the counts (n) and the denominator. Report the number and the target side by side; never a bare "it worked". A mismatch between the spec's metric and what the data supports is returned to the `product-manager` and `architect`, not repaired in the analysis. Correlation is not causation: name confounders you can see (a release, a campaign, seasonality) and say so.

## 4 · Judging decisions in hindsight

For each `autonomous` or `notify` decision of a shipped slice that the data touches, append a `review` row (`noctus.dev.decision_log action=review`, `reviewer_kind=product_analyst`) with `outcome` `accepted`, `reclassified` or `vetoed`, and a one-line note citing the evidence. This is the evidence the promotion and demotion rule uses (`engineer-decision-rights.md` §4): a class with 10 clean accepted uses may be proposed for promotion, a vetoed class is demoted.

## 5 · Council outcomes

A council session records objections (`KB § PATTERNS/common/council.md`). When a shipped result proves an objection right or wrong, write an `outcome` event with `noctus.dev.council_ledger action=record_event` (`event_kind=outcome`, `outcome` one of `vindicated`, `refuted`, `untested`, plus `objection_id` and `evidence_kind`). Never invent an outcome the data does not show; `untested` is a valid answer.

## 6 · Checklist (copyable)

- [ ] Metric defined as in the spec; one derivation; query, window and n stated.
- [ ] Target and baseline beside the measured value; verdict one of met / not met / inconclusive.
- [ ] Exposure checked (users reached the feature) before judging effect.
- [ ] Confounders named; no causal claim the data cannot carry.
- [ ] Missing instrumentation filed as a finding, not worked around.
- [ ] Decision `review` rows and council `outcome` events written through the tools, with evidence.
- [ ] No code judged, no data changed, no decision made.

## Sources

PostHog handbook, product engineer and product teams (posthog.com/product-engineer, read 2026-11-09) · UK DDaT performance analyst and data analyst roles (understand-digital-data-roles-skills.service.gov.uk, read) · `KB § PATTERNS/architect/measurement-by-design.md`. **Unverified here:** statistical-power guidance for small samples is not in this doc; when n is small the verdict is `inconclusive` rather than a significance test claimed without a source.

## Composes with

`.claude/agents/product-analyst.md` · agent `product-manager` (the target) · agent `architect` (the data side) · agent `compliance-reviewer` (code judgement stays there) · `KB § PATTERNS/common/engineer-decision-rights.md` · `KB § PATTERNS/common/council.md` · `KB § PATTERNS/devops/owner-operations.md`.
