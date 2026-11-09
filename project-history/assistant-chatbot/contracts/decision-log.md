# Contract — product-engineer decision log (v1, 2026-11-09)

> Owner decisions (2026-11-09, in the live spec doc):
> - product-engineer "decides small things in scope", designed safely.
> - Starting caps are 5 autonomous and 3 notify decisions per slice, a 1-in-5 audit sample, and a repeat of 3 escalating a decision. Data retunes these; the owner ratifies each change.
> - compliance-reviewer audits BEFORE merge. product-analyst judges outcomes AFTER ship.
>
> Research: `research/decision-rights-research.md`. It builds on the existing L0–L3 ladder in
> `KB § PATTERNS/devops/owner-operations.md` §2. The shape rule is measurement-by-design: rows are append-only,
> closed sets are enums, and a status changes only through a new row that supersedes the old one.

## 1 · Tiers (a decision takes the HIGHEST tier any criterion gives it)
- `autonomous` (= L3): decide and log. Allowed ONLY for the closed `class` list in §3.
- `notify` (= L3 with a pre-merge veto): decide, log, and have compliance-reviewer confirm before merge.
- `escalate` (= L2): stop and ask the tech-lead, who asks the owner through noc-questionnaire.

## 2 · Criteria (C1–C9) → minimum tier
| | criterion | autonomous | notify | escalate |
|---|---|---|---|---|
| C1 | scope | implements an acceptance criterion as written | fills a gap the criteria don't cover | changes, adds or drops a criterion, or changes the plan route |
| C2 | reversibility | one `git revert`, nothing outside git | shared or seed code | migration, backfill or external effect |
| C3 | blast radius | inside the slice's declared paths | same product outside those paths, or seed internals | another product, seed public API, CI or keepers |
| C4 | contract | — | — | any new or changed endpoint, schema, table, RLS, access tier or event shape |
| C5 | user-visible | internal text only | non-customer detail inside an approved mockup | new screen, or customer-facing wording |
| C6 | security / LGPD / money | — | tightening only | any loosening, new personal data, or any money path |
| C7 | irreversible ops | — | — | prod exposure, deploy, deletion, sending to customers |
| C8 | cost | — | — | a new runtime dependency or a new paid call path |
| C9 | novelty | a §3 class | — | anything not in §3 |

**Surprise test.** Answer each question; any yes or unsure moves the decision up one tier.
1. Would the owner be surprised to read this?
2. Does it change an acceptance criterion or the next plan step?
3. Would one revert fail to undo it?
4. Will a customer see, receive or pay something different?
5. Does another product, contract, table or tier see a different shape?
6. Is this the third small step in the same direction?
7. Would a mistake compound before anyone looks?
8. Am I stretching a pre-approved class to fit?

## 3 · Enums
- `tier`: `autonomous` · `notify` · `escalate`
- `class` (the pre-approved autonomous list, closed): `edge_case` · `internal_error_text` · `internal_naming` · `test_added` · `in_file_refactor` · `log_line` · `validation_tightened` · `null_handling` · `typo` · `other` (`other` is never autonomous)
- `criteria_hit[]`: `C1`…`C9`
- `reversibility`: `one_commit` · `shared_code` · `needs_migration` · `external_effect`
- `blast_radius`: `slice_paths` · `same_product` · `seed_internal` · `cross_product` · `seed_api` · `ci_keepers`
- `surprise_test`: `all_no` · `escalated_by_test`
- `outcome`: `pending_review` · `accepted` · `vetoed` · `reclassified` · `superseded`
- `reviewer_kind`: `compliance_reviewer` · `tech_lead` · `owner` · `product_analyst`

## 4 · Row (`record`) — one decision
`id` (`D-<slice>-<NNN>`, sequential, never reused), `ts`, `agent`, `slice_id`, `branch`, `commit_sha`†, `ac_ref`†,
`tier`, `class`, `criteria_hit[]`, `reversibility`, `blast_radius`, `surprise_test`, `paths[]`,
`decision` (free text, ≤200 characters, "We will …"), `options_considered`†, `revert_hint`†, `supersedes`†.
A `review` row is a separate append: `{id_ref, outcome, reviewer_kind, reviewer, note†}`.
Commits carry a `Decisions: D-…, D-…` trailer, so the diff and the log join.

## 5 · Bounds (starting values, retuned by data, the owner ratifies)
- Per slice: ≤ 5 `autonomous` and ≤ 3 `notify` rows. The next decision forces a check-in with the tech-lead.
- The same `class` on the same file 3 times becomes ONE decision, reclassified up.
- Classification runs against the whole slice diff vs its base, not commit by commit (anti-salami).
- Loosening a check is never pre-approved. A class that gets vetoed or reclassified is demoted from autonomous until it has 10 clean uses (owner-operations §2 promotion rule).

## 6 · Audit (compliance-reviewer, pre-merge — blocks the merge)
The merge is blocked when any of these holds:
- the diff touches migrations, RLS, access tiers or contract files with no owner-accepted `escalate` row;
- a route or page is added, or customer-facing text changes, under an `autonomous` row;
- billing, secrets or auth are loosened;
- paths outside the declared slice paths change while a row says `slice_paths`;
- a runtime dependency is added without a `notify`-or-higher row;
- a changed file has no row and no `ac_ref`;
- a row says `one_commit` but the diff has a migration;
- a cap is exceeded.

compliance-reviewer also re-runs the surprise test on 1 in 5 `autonomous` rows and on every `class=other` row.
Each acceptance criterion needs ≥ 1 test.

## 7 · Outcome (product-analyst, post-ship)
- `review` rows with `reviewer_kind=product_analyst` judge decisions in hindsight.
- The analyst also writes council-ledger `outcome` events for the objections that the shipped feature proved right or wrong.

## 8 · Storage
- Through `noctus.dev.ledger_store`, whose schema is registered there: `project-history/decisions/<YYYY-MM>/<slice_id>.ndjson`, append-only.
- An offline keeper validates staged rows.
- The audit runs as `noctus.dev.decision_log action=audit slice=<id> base=<ref>` and returns the §6 findings.
