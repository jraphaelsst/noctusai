# Product management canon — the what and the why, mapped onto this platform

**What it is.** The product manager's craft written as the operating manual for the `product-manager` agent: turn a fuzzy request into a problem statement, user stories, testable acceptance criteria, a success-metric target, a scope-creep log and a backlog draft. It owns the *what* and the *why*. Every decision (what to build, in what order, whether to expand scope) stays with the owner; the tech-lead turns the spec into dispatch.

**Why it exists.** Owner decision 2026-11-09. The product-roles research found the spec half of product management had no owner here (`project-history/assistant-chatbot/research/product-roles-research.md` Part A.2): the tech-lead's brief "Acceptance" is a command, which proves "the code does X" but never "the user can do Y"; the data side of a success metric was owned (`measurement-by-design.md`), the target side was not, and nobody checked it after ship; scope creep and the backlog were handled by the tech-lead and `PROJECT.md` only. The `dev_team` charter `dev_team/src/dev_team/charters/product_manager.md` already carried these duties for the agno team; this doc extracts the ones our tree lacked (charter lines :5, :12, :18-22, :54, :60, :61, :64-65, :75) and drops the rest.

**How to use it.** Read §1 and §8 (checklist) for every spec; open the other sections for their topic. The house mechanism wins over the general canon.

---

## 1 · House term ↔ standard term

| House term | Standard term | Where the house version lives | Note |
|---|---|---|---|
| owner | product owner (Scrum Guide: "one person, not a committee") | CLAUDE.md §1; `orchestration-craft-canon.md` §6.2 | an agent cannot be accountable; it drafts, the owner decides |
| product-manager spec | requirements document, stories, acceptance criteria | this doc §3 | the missing piece the tech-lead's command-shaped Acceptance never covered |
| acceptance criterion | acceptance test; Given/When/Then or a measurable threshold | §4 | one test per criterion (`test-engineer`, `compliance-reviewer`) |
| success-metric target | outcome measure; the "target" half of a key result | §5 | data side: `KB § PATTERNS/architect/measurement-by-design.md` §2 (architect-owned) |
| scope-creep log | scope change record; change control | §6 | the owner decides expansion |
| backlog draft | product backlog | §7 | ordered by the owner; skill `noc-roadmap` |
| data intake | privacy by design intake | §3 → `KB § PATTERNS/security/lgpd.md` §3 | which categories, then the five questions there |

---

## 2 · Boundary: what the product-manager does NOT do

- **Does not specify implementation.** Naming libraries or DB columns is the architect's half (charter :54: "If you find yourself naming libraries or DB columns, hand it to the Architect"). The spec stops at what, why and acceptance.
- **Does not design the UI** (`product-designer`), **decide structure across products** (`product-architect`), **decide seams, tenancy or schema** (`architect`), **write the endpoint contract** (tech-lead, `noc-contract-first`).
- **Does not decide priority or scope.** It recommends and names the trade-off; the owner decides.
- **Does not skip the data intake** for any feature touching personal data.

## 3 · The spec (the deliverable)

Written to the scratchpad or `projects/<slug>/spec/` as one file per feature. Sections:
1. **Problem and job.** The job (situation, motivation, expected outcome) in the user's words; no solution disguised as a need. Discovery is the product-designer's for screen work; for non-UI features (an API, a job, an agent behaviour) the product-manager runs the same owner interview (skill `noc-questionnaire`, batches of at most four questions, facts offered as options, ambiguity surfaced not guessed; as an advisor it returns the batch to the tech-lead).
2. **Stories.** Connextra form where it adds clarity ("As a <role>, I want <action> so that <benefit>"), plain prose otherwise.
3. **Acceptance criteria** (§4), numbered, each with an id the tests cite.
4. **Success metric and target** (§5).
5. **Scope in and out**, and the scope-creep log (§6).
6. **Data categories touched.** List the categories only, then point at `KB § PATTERNS/security/lgpd.md` §3 (the five questions there: basis, minimization, destination, retention, tenant isolation). Do not restate them here. `security` / `legal-advisor` reason about the handling.
7. **Product working scope.** Read the catalog first (`ativo` + `deploy_scope`; `KB § PATTERNS/architect/product-working-scope.md`): `live` means prod rules, `dev` means dev only, inactive is asleep, so do not scope work there.
8. **Placement and structure** come from `product-architect` and `product-designer`; cite them, do not redo them.
9. **Open questions for the owner**, numbered, with options.

**Replication-to-seed language trigger.** If the draft says "add this to ERP and PF and Therapy" (charter :60), that is the LANGUAGE slip: stop and hand to the `architect`/`product-architect` before scoping per-product work. The right count of per-product copies is zero.

## 4 · Acceptance criteria that test

"It feels fast" is not acceptance; "P95 below 200 ms on the `/me` endpoint" is (charter :64, :75). Use Given/When/Then or a measurable threshold. Every criterion must be testable by a named layer (unit, contract, e2e, measured), and **each has at least one test asserting it**, with the criterion id as the traceability link (the `test-engineer` rule, from `dev_team` `qa_engineer.md`:11; `compliance-reviewer` checks it pre-merge). A criterion nobody can test is rewritten or marked "judged by the owner at review".

## 5 · The success metric (the target side)

"What observable signal proves it works in production" (charter :12, :22). Name: the metric, its definition, the baseline, the target and the date it is read. The data side (the rows, events and enums that make the metric computable, one derivation per metric) is `measurement-by-design.md` §2 and goes in the contract's "Records / Metrics" section (the architect and tech-lead). After ship, `product-analyst` reads it and judges met, not met or inconclusive. A feature whose spec names no target is asked "so how will we know it works?" before it is built.

## 6 · Scope-creep log and the trade-off protocol

When the owner adds "oh, and also …" (charter :61): capture the addition in the log (date, request, effect on scope), do not absorb it silently, and name the trade-off (charter :65): **smaller scope, longer timeline, or a deferred sub-feature**. Surface it to the tech-lead, who asks the owner (`noc-questionnaire`); the owner decides whether to expand the project or file a follow-up. Push-back is positive collaboration: "this won't ship in scope" protects the project. A request that grew during scoping needs an explicit owner OK before it ships.

## 7 · The backlog draft

An ordered list when the work decomposes into more than one shippable slice, per product, via skill `noc-roadmap`. The order is a recommendation with its reasons (value, viability, risk); the owner orders. SVPG's frame for what the role weighs (value and viability risk, with usability for the designer and feasibility for engineering; svpg.com, read for "A fresh definition of the product role", the risk-taxonomy page was a snippet) is the vocabulary, not a method to impose.

## 8 · Checklist (copyable)

- [ ] Job and users stated in the user's words; no solution disguised as a need.
- [ ] Every acceptance criterion testable and numbered; metric target has a number, baseline and read date.
- [ ] Scope in and out; creep log current; each addition has a named trade-off and an owner decision.
- [ ] Data categories listed and pointed at `lgpd.md` §3; handling left to security and legal.
- [ ] Catalog read; no work scoped on an asleep product.
- [ ] No implementation detail (libraries, columns); no "per-product X".
- [ ] Open questions numbered with options, at most four per batch.
- [ ] Every decision labelled the owner's; the spec is a recommendation.

## Sources

`dev_team/src/dev_team/charters/product_manager.md` (the extraction source, derived content; the charter's "five questions" list had drifted from `lgpd.md` §3 and is fixed to a pointer, 2026-11-09) · Scrum Guide (scrumguides.org/scrum-guide.html, read: Product Owner "one person, not a committee") · UK DDaT product manager and performance analyst roles (understand-digital-data-roles-skills.service.gov.uk, read) · SVPG, "A fresh definition of the product role" (svpg.com, read). **Unverified:** Connextra story form attribution (taken from the charter, not re-read); SVPG risk taxonomy (snippet only).

## Composes with

`.claude/agents/product-manager.md` · agent `product-architect` · agent `product-designer` · agent `product-analyst` · agent `architect` · agent `legal-advisor` · agent `security` · agent `test-engineer` · `KB § PATTERNS/architect/measurement-by-design.md` · `KB § PATTERNS/security/lgpd.md` · skills `noc-questionnaire` · `noc-roadmap` · `noc-contract-first`.
