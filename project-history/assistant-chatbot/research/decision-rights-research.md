# Decision rights for `product-engineer`: research and design

Research date: 2026-11-09. Read-only on the repo. Every quote below was read on the cited page during this session; where a primary text could not be reached, that is stated and the source is marked weak.

---

## Part A. Sources (URL + exact quote)

### A1. Bezos, 2015 shareholder letter (Type 1 / Type 2): PRIMARY, verified
URL: https://www.sec.gov/Archives/edgar/data/1018724/000119312516530910/d168744dex991.htm (Amazon 8-K Ex. 99.1, April 2016, the 2015 letter)
- "Some decisions are consequential and irreversible or nearly irreversible – one-way doors – and these decisions must be made methodically, carefully, slowly, with great deliberation and consultation."
- "We can call these Type 1 decisions."
- "But most decisions aren't like that – they are changeable, reversible – they're two-way doors."
- "Type 2 decisions can and should be made quickly by high judgment individuals or small groups."
Use: the base axis. Reversible = can be delegated; irreversible = deliberate + consult the owner.

### A2. Bain RAPID: PRIMARY (Bain), verified
URL: https://www.bain.com/insights/rapid-decision-making/
- "The recommend (R) role drives the process, gathering relevant input and developing a recommendation for the decider."
- "The decide (D) role makes the final decision and commits the organization to action."
- "The perform (P) role identifies those accountable for implementing the decision once it is made."
- "When the roles involved in decisions are clearly delineated, teams and organizations make the right choices."
Use: on ESCALATE items the agent is R (and P), the owner is D. On AUTONOMOUS items the agent is D for a narrow class.

### A3. Atlassian DACI playbook: PRIMARY, verified
URL: https://www.atlassian.com/team-playbook/plays/daci
- Approver: "The one person (yes: one!) who makes the decision."
- Contributors: "People who have subject-area knowledge and can make recommendations – i.e., they have a voice, but not a vote."
- Informed: "People whose work may be affected by the decision, and should be informed once it's been made – i.e., no vote, no voice."
- "document the final decision in your collaboration document."
Use: every decision has exactly one Approver; DECIDE-AND-NOTIFY = tech-lead is "Informed" before merge with a veto.

### A4. Management 3.0 Delegation Poker (7 levels): PRIMARY, verified
URL: https://management30.com/practice/delegation-poker/
1. "Tell: I will tell them" 2. "Sell: I will try and sell it to them" 3. "Consult: I will consult and then decide" 4. "Agree: We will agree together" 5. "Advise: I will advise but they decide" 6. "Inquire: I will inquire after they decide" 7. "Delegate: I will fully delegate"
Use: AUTONOMOUS ≈ level 6 "Inquire" (not 7: the log keeps the owner able to inquire). DECIDE-AND-NOTIFY ≈ level 5/6 with a pre-merge veto. ESCALATE ≈ levels 1-3 (owner decides).

### A5. Mission command / commander's intent (ADP 6-0): SECONDARY-OFFICIAL (primary PDF unreachable)
URL: https://www.army.mil/article/106872/Understanding_mission_command/ (official Army site, discussing ADP 6-0, 2012 edition)
- Mission command is used "to enable disciplined initiative within the commander's intent."
- Six principles include "provide clear commander's intent", "exercise disciplined initiative", "accept prudent risk".
- Leaders must trust subordinates to "act decisively within the operational intent."
- Historical root quoted there: "if an execution of an order was rendered impossible, an officer should seek to act in line with the intention behind it."
Weakness: armypubs.army.mil PDFs (2019 ADP 6-0) returned 404/HTML; FAS and UNT mirrors returned empty bodies. Standalone definitions of "commander's intent" / "disciplined initiative" were NOT verified in the primary text and are not quoted here.
Use: the approved acceptance criteria + plan route = the "intent"; initiative is allowed only inside it.

### A6. Google SRE book: PRIMARY, verified
URL: https://sre.google/sre-book/introduction/
- "SRE has found that roughly 70% of outages are due to changes in a live system."
- Best practices: "Implementing progressive rollouts", "Quickly and accurately detecting problems", "Rolling back changes safely when problems arise".
URL: https://sre.google/sre-book/reliable-product-launches/
- "Almost all updates to Google's services proceed gradually, according to a defined process."
- "If the change doesn't pass the validation period, it's automatically rolled back."
- "Independently revert each such change immediately in the event of serious bugs or side effects."
Use: the reversibility test = "can this be independently reverted with one commit, with nothing else needing to move?"

### A7. ITIL change types: SECONDARY (IT Process Maps, ITIL v3/2011 glossary-based; official AXELOS/PeopleCert ITIL 4 text is paywalled, not verified)
URL: https://wiki.en.it-processmaps.com/index.php/Change_Management
- Standard Change: "Pre-authorized, low-risk Changes that follow a well-known procedure."
- Normal Change: "All other Changes that are not Standard Changes or Emergency Changes."
- Emergency Change: "A Change that must be introduced as soon as possible - for example, to resolve a major incident or implement a security patch."
- "Change Models describe procedures for the handling of recurring Changes."
Use: AUTONOMOUS classes = a closed, pre-authorized list of "standard changes" (a change model), not open-ended judgment. Everything not on the list is "normal" by default.

### A8. ADRs / decision logs: PRIMARY, verified
URL: https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions (Michael Nygard, 2011)
- "ADRs will be numbered sequentially and monotonically. Numbers will not be reused."
- "All consequences should be listed here, not just the "positive" ones."
- Sections: Title, Context, Decision, Status (proposed/accepted/deprecated/superseded), Consequences; a reversed decision is kept and marked superseded, not deleted.
URL: https://adr.github.io/
- An ADR "captures a single AD and its rationale."
- "The collection of ADRs created and maintained in a project constitute its _decision log_."
Use: log rows are append-only, monotonic ids, supersede-don't-edit, and list consequences (including "what would need to revert").

### A9. Anthropic, "Building effective agents": PRIMARY, verified
URL: https://www.anthropic.com/engineering/building-effective-agents
- "Agents can then pause for human feedback at checkpoints or when encountering blockers."
- "...include stopping conditions (such as a maximum number of iterations) to maintain control."
- "The autonomous nature of agents means higher costs, and the potential for compounding errors."
- "We recommend extensive testing in sandboxed environments, along with the appropriate guardrails."
Use: worktree = sandbox; cap per slice = stopping condition; compounding errors = why many small decisions need a counter.

### A10. Anthropic, "Our framework for developing safe and trustworthy agents": PRIMARY, verified
URL: https://www.anthropic.com/news/our-framework-for-developing-safe-and-trustworthy-agents
- "A central tension in agent design is balancing agent autonomy with human oversight."
- "But humans should retain control over how their goals are pursued, particularly before high-stakes decisions are made."
- "Humans need visibility into agents' problem-solving processes."
- "Too little information leaves humans unable to assess whether the agent is on track to achieve its goal."

### A11. OpenAI, "A practical guide to building agents": PRIMARY, verified (PDF text extracted locally)
URL: https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf
- p.26 Tool safeguards: "Assess the risk of each tool available to your agent by assigning a rating—low, medium, or high—based on factors like read-only vs. write access, reversibility, required account permissions, and financial impact. Use these risk ratings to trigger automated actions, such as pausing for guardrail checks before executing high-risk functions or escalating to a human if needed."
- p.31: "Exceeding failure thresholds: Set limits on agent retries or actions. If the agent exceeds these limits (e.g., fails to understand customer intent after multiple attempts), escalate to human intervention."
- p.31: "High-risk actions: Actions that are sensitive, irreversible, or have high stakes should trigger human oversight until confidence in the agent's reliability grows. Examples include canceling user orders, authorizing large refunds, or making payments."
Use: the criteria list (write vs read, reversibility, permissions, money) and the "until confidence grows" promotion rule.

### A12. Feng, McDonald, Zhang, "Levels of Autonomy for AI Agents" (2025): PRIMARY, verified
URLs: https://arxiv.org/abs/2506.12469 · https://knightcolumbia.org/content/levels-of-autonomy-for-ai-agents-1 (Knight First Amendment Institute, 2025-07-28)
- "Autonomy is a double-edged sword for AI agents."
- "we define five levels of escalating agent autonomy" (operator, collaborator, consultant, approver, observer).
- Observer level: "The only control mechanism available to the user is an emergency off-switch".
- Autonomy can be "a deliberate design decision, separate from its capability and operational environment."
Use: product-engineer sits at "approver" (L4): the user engages only on consequential actions. Autonomy is a declared setting, not a function of how capable the model is. Their "autonomy certificate" idea = our agent file declaring its ceiling.

### A13. Normalization of deviance (Vaughan): SECONDARY ONLY
URL: https://www.flightsafetyaustralia.com/2017/05/safety-in-mind-normalisation-of-deviance (secondary). Attributed definition (not verified in Vaughan's 1996 book): the gradual process through which unacceptable practice or standards become acceptable. Used only as a named failure mode, not as a quoted authority.

### A14. In-repo precedent (codebase is source of truth)
`KNOWLEDGE-BASE/CONTEXT/PATTERNS/devops/owner-operations.md` §2 already defines "Autonomy is per ACTION, not per agent" with L0 inform / L1 suggest / L2 act-with-approval / L3 act-and-report, a promotion rule ("≥10 clean runs, recorded"; "demote immediately after an incident") and a "Never L3" list (customer sends, money, data deletion, prod schema, security/settings). The design below REUSES that ladder rather than inventing a parallel one: AUTONOMOUS = L3, DECIDE-AND-NOTIFY = L3 with a pre-merge veto, ESCALATE = L2. Ledgers go through the ledger store (`PATTERNS/common/ledger-store.md`), rows follow `PATTERNS/architect/measurement-by-design.md` (append-only, CHECK-enum outcomes, no free-text status).

### Weak / unreachable
- ADP 6-0 primary PDF (armypubs 404; FAS/UNT mirrors empty). Used army.mil article instead.
- ITIL 4 official glossary (paywalled). Used IT Process Maps (ITIL v3 terms).
- Microsoft and Google agent-autonomy levels: no first-party document found. Only secondary coverage (e.g. a report of Google Cloud's Nov-2025 "Introduction to Agents" guide). Not cited.
- Vaughan: secondary only.
- Bezos letter on aboutamazon.com not fetched; the SEC filing (stronger) was used.

---

## Part B. Design for noc

### B1. Taxonomy (per decision, not per agent: A14)

Classification is the MAX over all criteria: one ESCALATE hit makes the decision ESCALATE.

| # | Criterion (checkable) | AUTONOMOUS (decide + log) | DECIDE-AND-NOTIFY (decide, flag, tech-lead veto before merge) | ESCALATE (stop, ask the owner via tech-lead) | Source |
|---|---|---|---|---|---|
| C1 | Inside approved acceptance criteria + plan route | yes, implements an AC as written | fills a gap the AC is silent on, without changing an AC | changes, drops, adds or reinterprets an AC; changes plan route/order of phases | A5 intent, A3 |
| C2 | Reversibility | one `git revert` of one commit restores prior state; no data migration, no external side effect | one revert, but touches shared/seed code consumed by others | needs a data migration, backfill, or anything outside git (prod data, vendor state, sent messages) | A1, A6 |
| C3 | Blast radius | files inside the slice's declared paths, one product | outside declared paths but same product; or `lib/`/seed internals with no API change | another product, the seed's public API, CI/hooks/keepers config | A6, A11 (permissions) |
| C4 | Contract impact | none | additive optional field on a response that the contract already allows | new/changed endpoint, request/response shape, DB table/column, RLS, access tier, event schema | A7 normal change, house contract-first |
| C5 | User-visible impact | none, or internal error/log text, test names, internal identifiers | non-customer UI detail inside an approved mockup (spacing, internal admin label, empty-state reuse of approved copy) | new screen/route/page, customer-facing wording, new notification/message, flow change | owner rule, A10 |
| C6 | Security / LGPD / money | none | stricter-only change (adds validation, narrows a permission) | any loosening of authz, new personal-data field or purpose, any price/charge/refund/fee/billing path, secrets | A11 (financial impact, sensitive), A14 Never-L3 |
| C7 | Irreversible ops | none | none | prod exposure, deploy, deletion of data/files/branches others own, sending to customers | A1 Type 1, A11 |
| C8 | Cost | no new paid call, no new dependency | new dev dependency already used elsewhere in repo | new runtime dependency, new paid API/LLM call path, raises a budget | A11 |
| C9 | Novelty | matches a closed list of pre-authorized classes (below) | not on the list but passes C1-C8 at the left/middle column | first-of-a-kind pattern or "we've never decided this before" | A7 standard vs normal |

Pre-authorized AUTONOMOUS classes (closed enum, ITIL "change model" A7): `edge_case_handling`, `internal_error_message`, `internal_naming`, `test_addition`, `refactor_within_file`, `log_or_metric_line`, `validation_tightening`, `null_or_empty_handling`, `retry_or_timeout_param_within_contract`, `typo_fix_internal`. Anything else defaults to DECIDE-AND-NOTIFY at best. The list grows only by the owner-operations promotion rule (≥10 clean, recorded uses; demote on any incident: A14, A11 "until confidence grows").

### B2. Surprise test (answer all before AUTONOMOUS; any "yes/unsure" bumps one level)

1. Would the owner be surprised to read this decision in the review? (A10 "retain control over how their goals are pursued")
2. Does it change what an approved acceptance criterion says, or which plan step comes next? (A5)
3. Could I undo it with one `git revert`, and nothing outside git would still be different? (A1, A6) If no, ESCALATE.
4. Will a customer see, receive or be charged for something different? (C5, C6)
5. Does another product, the seed API, a contract, a table or an access tier see a different shape? (C3, C4)
6. Is this the Nth small decision pushing the same direction (e.g. the 3rd "temporarily" relaxed check, the 3rd extra field)? (A13, B5)
7. If I am wrong, does the error compound in later steps before anyone looks? (A9 "compounding errors")
8. Is my decision class on the pre-authorized list, or am I stretching a class to fit? (A7)
"Unsure" counts as "yes" (house no-silent-errors: ambiguity → ask).

### B3. Log format (append-only, enum, measurable-by-design)

One NDJSON row per decision, ledger `decision-log.ndjson` written via the ledger store (orphan `ledgers` branch, A14), plus the row ids in the slice's commit trailer `Decisions: D-<slice>-001,…` so the diff and the log join.

| Field | Type | Notes |
|---|---|---|
| `id` | string `D-<slice_id>-<seq3>` | monotonic, never reused (A8) |
| `ts` | ISO-8601 UTC | |
| `agent` | enum (`product-engineer`, …) | |
| `slice_id`, `branch`, `commit_sha` | string | `commit_sha` filled when committed; join key for audit |
| `ac_ref` | string | the acceptance criterion id it serves; `none` forces non-AUTONOMOUS |
| `class` | enum (B1 closed list + `other`) | `other` ⇒ cannot be AUTONOMOUS |
| `tier` | enum `autonomous` · `decide_notify` · `escalate` | |
| `criteria_hit` | enum[] `C1..C9` | which criteria were not at left column |
| `reversibility` | enum `one_commit` · `multi_commit` · `needs_migration` · `external_side_effect` | |
| `blast_radius` | enum `slice_paths` · `same_product` · `seed_internal` · `cross_product` · `seed_api` | |
| `paths` | string[] | files touched by this decision |
| `surprise_test` | enum `pass` · `bumped` | |
| `options_considered` | int | ≥2 for decide_notify (Nygard context/alternatives) |
| `decision` | string ≤200 chars | the only free text; "We will …" (A8) |
| `revert_hint` | string | the commit or step that undoes it |
| `outcome` | enum `pending_review` · `accepted` · `vetoed` · `reclassified` · `superseded` | set by a NEW row (`supersedes: <id>`), never by editing |
| `supersedes` | id or null | A8 supersede-not-delete |
| `reviewer` | enum `tech-lead` · `compliance-reviewer` · `owner` · null | |

No free-text status: status lives only in `tier` and `outcome` enums. Metrics enabled by GROUP BY: decisions/slice, % reclassified (misclassification rate), veto rate per class (promotion/demotion evidence).

### B4. Audit before merge (tech-lead or compliance-reviewer; mechanizable as a keeper)

Join the slice diff with its log rows. Flag (block merge) when:
1. Diff touches `**/migrations/**`, `supabase/**`, RLS/policies, or access-tier declarations, and no `escalate` row with `outcome=accepted` by `owner` covers those paths. (C4/C6)
2. Diff touches a contract file (OpenAPI/zod/pydantic schema, router signature, route table) and no escalate row. (C4)
3. Diff adds a route/page/screen file, or changes pt-BR customer-facing strings (i18n/copy files, templates, WhatsApp/email message text) with an `autonomous` row. (C5)
4. Diff touches billing/pricing/payment/refund modules, secrets, auth/permission code with loosening semantics. (C6)
5. Diff touches paths outside the slice's declared paths while every row says `blast_radius=slice_paths`. (C3)
6. Diff adds a runtime dependency (package.json/pyproject change) with no `decide_notify`+ row. (C8)
7. Any changed file not covered by any row's `paths` (undeclared decision) AND not covered by an AC → "unlogged decision".
8. Row says `reversibility=one_commit` but the slice has >1 commit touching the same file, or a migration exists. (C2)
9. Count caps exceeded (B5).
10. Spot-check: compliance-reviewer re-runs the surprise test on a sample (e.g. 1 in 5 autonomous rows, all `class=other`). Reclassification = a superseding row `outcome=reclassified`; ≥1 reclassification upward demotes that class (A14).
Every red is "reclassify + ask", never "silently merge"; misclassification rate is the agent's trust metric.

### B5. Failure modes and bounds

| Failure mode | Source | Bound |
|---|---|---|
| Scope creep through many small decisions (each Type 2, together a Type 1) | A1 (aggregation not addressed by Type 1/2), A9 compounding errors | Cap: ≤5 AUTONOMOUS + ≤3 DECIDE-AND-NOTIFY per slice; hitting either cap = stopping condition (A9) → check-in with tech-lead before continuing. |
| Salami slicing (splitting an escalate-class change into "small" pieces across commits/slices) | A13 drift; A11 failure thresholds | Classify on the cumulative diff of the slice (and of the branch vs `origin/dev`), not per commit. Same `class` + same file ≥3 times in a slice ⇒ one combined decision re-classified. |
| Normalization of deviance (vetoes ignored, "temporary" relaxations accumulate) | A13 | Any `validation_loosening` is not a class at all (ESCALATE). Veto rate per class tracked; a vetoed class drops to DECIDE-AND-NOTIFY. |
| Interpreting intent too loosely | A5 initiative within intent | `ac_ref=none` can never be AUTONOMOUS. |
| Class stretching (labelling a new screen "edge-case handling") | A7 standard change must be a well-known procedure | Closed enum + audit checks 3/7 compare class against what the diff actually touches. |
| Log rot / unlogged decisions | A8, A10 visibility | Audit check 7; commit trailer join; rows append-only. |
| Over-escalation (owner flooded, the original complaint) | A1 "Type 2 decisions can and should be made quickly" | Promotion rule: class with ≥10 clean, accepted uses moves up (A14). Measure escalations/slice; escalations go batched through noc-questionnaire. |
| Automation complacency (reviewer rubber-stamps) | A10 "too little information" | Sampling spot-check (B4.10) independent of the agent's own tier claim. |

Uncited judgement calls (owner should ratify): the specific caps (5/3), the sample rate (1 in 5), and the ≥3 same-class trigger. They follow the "set limits" guidance in A9/A11 but the numbers are ours.
