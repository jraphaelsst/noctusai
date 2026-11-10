# Council map + Product-Done ladder — research report (2026-11-09)

Repo read at worktree `assistant-chatbot`, tip `24032323f` (origin/dev). Read-only. All file:line refs are to that tree unless marked `origin/feat/noc-iterate`.

---

## 1 · Our development lifecycle as it exists today

| # | Stage (as the repo names it) | Skill / doc that owns it | Mechanical gate(s) | Advisor invoked today (file:line) |
|---|---|---|---|---|
| 0 | **Classify the ask** (plain / market / client onboarding / extension pack / sellable item / sandbox) | `noc-new-product` step 0 (`.claude/skills/noc-new-product/SKILL.md:13-19`) | none (judgment) | none |
| 1 | **Learning round?** opens method trials | `noc-new-product` step 1 (`:20`) → `noc-learn-refine` | `method_trial` ledger | none |
| 2 | **Idealize / market spec** — research brief, module classification, owner interview (AskUserQuestion), decisions to roadmap | `noc-new-product` step 2 (`:21`); `GUIDES/new-product.md § Market products from a vertical seed` (`:123`); `noc-questionnaire` (council lives here: `PATTERNS/common/owner-questionnaire.md:35-42`) | none mechanical | **single-chat council** only, before owner questions (`owner-questionnaire.md:35-42`) |
| 3 | **Project scaffold + seed-first §3a + Phase 0 audit + absorption scan** | `PATTERNS/architect/project-execution.md:14-33` (§0, §2.5 at :358) | absorption sextet scans; seed-first checklist (discipline, not gated) | `architect` implied by "Phase-0 audits" in its agent description; not wired into any skill step |
| 4 | **Verify the seed ships it** (discovery + 4 existence gates) | `noc-verify-seed` (Leg A :15, Leg B :24) | deterministic existence gates | none |
| 5 | **Mockup-first** (UI) | `noc-contract-first` step 0 (`SKILL.md:13`); `PATTERNS/design/mockup-protocol.md §1` | none (owner validation) | **`product-designer`** — `CLAUDE/frontend.md:22` |
| 6 | **Contract-first** (shapes + 4 stateful legs + Records/Metrics leg) | `noc-contract-first` steps 1-6 (`:14-19`) + guardrail (`:22`) | keeper `check_measurable_by_design` (`compliance.py:17035`), `check_contract_field_provenance_map` | none |
| 7 | **Scaffold** | `noc-new-product` step 4 (`:23`) → `scaffold_product`, `reserve_port_range` | scaffold emits seed-row migration, docker, consent | none |
| 8 | **Build** (fill seams + domain only; dispatch executors) | `noc-new-product` step 5 (`:24`); `noc-branch-dispatch`; `project-execution.md §2.6` active robustness review | keepers at commit (`check_canonical_organ_consumption`, `check_access_tier_*`, `check_table_has_rls`, `check_lying_loading_state`, `check_auth_boundary_false_green`, …); slice DoD = `BEFORE_RETURNING_BLOCK` (`engine engineer_brief_compose.py:415`; `PATTERNS/common/engineer-operating-discipline.md:168-186`) | none at step level |
| 9 | **Wire** (real data + page-scoped CRUD) | `noc-wiring-audit` (`:11-23`); `PATTERNS/frontend/product-internal-wiring.md §2-§2a` | `scan_wiring`: `check_fe_route_missing` (`compliance.py:673`), `check_name_on_nome_select`, `check_promise_all_shared_catch`; runtime + CRUD legs advisory | none |
| 10 | **Register + onboard** | `noc-new-product` step 6 (`:25`) | `check_status_pagina_role_parity`, roster keepers | none |
| 11 | **Finish gates** (pytest, vite build) | `noc-new-product` step 7 (`:26`); `GUIDES/new-product.md:156-173` "Checklist for launch" (manual checkboxes) | `predeploy_check`; CI `Tests & Build`; Playwright E2E in CI for core/erp-imobiliario/social-wiring only (`.github/workflows/test.yml:~773-820`) | none |
| 12 | **Review / merge** | merge queue; `compliance-reviewer` exists for "is this ready to merge" | merge-queue CI on merged tree | `compliance-reviewer` by description only — no skill step calls it |
| 13 | **Security pass** | `noc-security-audit` (`SKILL.md:14-15`) — "after any new product, agent or route batch" | access-tier keepers | **`security` + `agents-security`** (`noc-security-audit/SKILL.md:14-15`) |
| 14 | **Wrap-up** | `noc-wrap-up` six-surface survey (`:11-33`) | `pytest`, `auto_improvement_query`, `scan_live_state_claims`, stale-cache tools | none |
| 15 | **Ship** (steward → bless → promote → deploy → verify) | `noc-ship` 00-7 (`:11-35`) | `predeploy_check`, CI qualifying green, `check_prod_exposure_consent` (`compliance.py:25681`), `deploy_verify`, `vps.health`, `spa_smoke` (no JS exec), `latency_report` | none; **owner** consent only for first prod exposure (`prod_consent`) |
| 16 | **First go-live** | `GUIDES/production-deploy.md § 5a` via `noc-ship` step 7 | flip live in core `/admin/products` last | none |
| 17 | **Iterate** (build → eval batch → split defect → council → refine → owner checkpoint) | `noc-iterate` (`origin/feat/noc-iterate:.claude/skills/noc-iterate/SKILL.md`, step 4) + `KB § PATTERNS/common/iterate-loop.md` (branch only) | `method_trial` | **single-chat council** at step 4 |
| — | Domain one-offs | `noc-tax-params` (`:20,:30`) | tax staleness | **`accountant`** |

Agent-specific readiness already exists in one place: agents product `prontidao` = publish gate, same predicates (`PATTERNS/ai/ai-engineering-canon.md:474-490`; `products/agents/backend/app/studio/prontidao.py`). This is the in-house model for "readiness == gate" and the template for Product-Done.

Existing "done" definitions: slice-level DoD (`engineer-operating-discipline.md:168-186`, cites Scrum Guide); older generic DoD (`KNOWLEDGE-BASE/INSTRUCTIONS/05-TESTING-EVALS.md:493-500`); per-phase DoD in design phases (`INSTRUCTIONS/04-DESIGN-PHASES.md:242`). **No product-level Done/Ready definition exists.** The launch checklist (`new-product.md:156`) is manual and mixes scaffold-time and launch-time items.

**Gaps observed:** (a) advisors are invoked at only 3 points (designer at UI, security after batches, accountant for tax); `architect`, `compliance-reviewer`, `legal-advisor` are never a named step; (b) the council is single-chat and only fires before owner questions and iterate refines, never at architecture or go-live; (c) no executed-JS UI probe at deploy (`spa_smoke` explicitly does not run JS, `noc-ship/SKILL.md` step 6a); (d) zero a11y keepers / no axe in any product (`PATTERNS/design/accessibility.md:10-11,196`); (e) no ledger of council objections, so no way to know if the council helps.

---

## 2 · Research — what the evidence says

### 2a. Multi-model councils, debate, judges, sycophancy

| Source | Finding relevant to us | Strength |
|---|---|---|
| Du et al. 2023, *Improving Factuality and Reasoning in Language Models through Multiagent Debate* — https://arxiv.org/abs/2305.14325 | Several model instances propose, then read each other over rounds; improves math/strategic reasoning and factuality, cuts hallucination. | Strong (peer-reviewed ICML 2024), but tasks are QA/reasoning, not design review. |
| Liang et al. 2023/24, *Encouraging Divergent Thinking … Multi-Agent Debate* (EMNLP 2024) — https://arxiv.org/abs/2305.19118 | "Degeneration-of-Thought": a single model self-reflecting stops producing new ideas once confident. Debate helps if "tit for tat" is **moderate** and ends adaptively; LLM judges may be unfair across different debaters. | Strong. Directly argues single-chat self-critique has a ceiling. |
| Smit et al. 2023, *Should we be going MAD?* — https://arxiv.org/abs/2311.17371 | Multi-agent debate "do[es] not reliably outperform" self-consistency; sensitive to hyperparameters; tuning agreement level helps. | Strong counter-evidence. |
| Wang et al. 2024, *Rethinking the Bounds of LLM Reasoning: Are Multi-Agent Discussions the Key?* (ACL 2024) — https://arxiv.org/abs/2402.18272 | A single agent with strong prompts nearly matches the best multi-agent discussion; multi-agent wins mainly when no demonstrations in prompt. | Strong counter-evidence for reasoning tasks. |
| Zheng et al. 2023, *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena* — https://arxiv.org/abs/2306.05685 | LLM judges show position, verbosity and **self-enhancement** bias; GPT-4 agrees with humans >80% (≈ human-human). | Strong. Self-enhancement = a model judging its own plan is biased. |
| Verga et al. 2024, *Replacing Judges with Juries (PoLL)* — https://arxiv.org/abs/2404.18796 | Panel of smaller models from **disjoint families** beats one large judge, less intra-model bias, >7× cheaper. | Strong; key lever is model-family diversity. |
| Kim et al. 2025, *Correlated Errors in Large Language Models* (ICML 2025) — https://arxiv.org/abs/2506.07962 | Errors across 350+ LLMs substantially correlated; more so for same provider/architecture and for larger, more accurate models. | Strong. Implies N copies of the same model ≠ N independent reviewers. |
| Sharma et al. 2023 (Anthropic), *Towards Understanding Sycophancy in Language Models* — https://arxiv.org/abs/2310.13548 | Sycophancy is general across 5 assistants; driven in part by human preference data favouring agreement. | Strong. Justifies the council's purpose. |
| Karpathy, *llm-council* — https://github.com/karpathy/llm-council | 3 stages: independent first answers → **anonymised** peer review + ranking → chairman synthesis. | Weak as evidence (a weekend hack repo, no evaluation); useful as protocol shape. |
| Anthropic Engineering, *How we built our multi-agent research system* (2025) — https://www.anthropic.com/engineering/multi-agent-research-system | Multi-agent ≈15× chat tokens (agents ≈4×); worth it for high-value, parallelisable, context-exceeding tasks; poor fit where all agents need the same context or for most coding. | Medium (vendor engineering blog, first-party measurement). |

**Synthesis.** (1) Sycophancy and self-enhancement are real, so some adversarial review is warranted. (2) Single-chat role-play is roughly as good as same-model debate for *reasoning* (Wang; Smit), but has a known ceiling (Liang DoT) and cannot be independent (Kim). (3) What buys real independence is **separate context + different priors/evidence**, ideally different model families (Verga). Our advisor subagents give separate context and *different evidence* (each reads its own KB/tools) but the same model family — partial independence. (4) Cost is ≈4-15× (Anthropic), so independence should be reserved for high-stakes decisions.

### 2b. Human decision-review practices

| Practice | When reviewers convene / what it requires | Source |
|---|---|---|
| **Pre-mortem** (Klein, HBR 2007) | At planning, before commitment: team assumes the project has failed and lists why; makes dissent safe. | https://hbr.org/2007/09/performing-a-project-premortem (the oft-quoted "+30% reasons" figure from Mitchell/Russo/Pennington 1989 could **not** be confirmed from the page — omit or verify). |
| **Delphi** (RAND, Dalkey 1969) | Anonymous expert responses, iteration with controlled feedback, statistical group response; anonymous feedback beat face-to-face more often than not in early RAND experiments; critics say convergence is partly conformity. | Dalkey 1969, RAND RM-5888-PR via DTIC https://apps.dtic.mil/sti/pdfs/AD0690498.pdf (RAND topic page returned 403). Medium. |
| **ATAM** (SEI) | Architecture evaluation against prioritized quality-attribute scenarios (utility tree); outputs risks, non-risks, sensitivity points, trade-off points. Done when architecture is defined but before costly build. | SEI tech report CMU/SEI-2000-TR-004 (Kazman, Klein, Clements) — found via secondary course material, primary not opened; e.g. https://www.pst.ifi.lmu.de/Lehre/WS0102/architektur/VL9/ATAM.pdf. Medium. |
| **Design docs at Google** | Review after first stable draft, lightweight (mailing list) or formal; "a dangerous trap of overhead"; skip when the solution isn't ambiguous. | Malte Ubl, https://www.industrialempathy.com/posts/design-docs-at-google/ (practitioner blog, not official Google). Medium. |
| **Working Backwards PR/FAQ** (Amazon) | Write the press release + FAQ before budget/team/code; iterate with leadership. | Bryar & Carr, *Working Backwards* (2021); only secondary web summaries found (e.g. https://www.productplan.com/glossary/working-backward-amazon-method/). Weak-medium. |
| **Red teaming** | Adversarial team tries to break the thing before release. | Ganguli et al. 2022 (Anthropic) https://arxiv.org/abs/2209.07858 (not re-fetched in this session; well-known). |
| **Nielsen severity ratings** | Single-evaluator severity is unreliable; use mean of ~3 **independent** evaluators; severity 4 = must fix before release. | https://www.nngroup.com/articles/how-to-rate-the-severity-of-usability-problems/ ; heuristics https://www.nngroup.com/articles/ten-usability-heuristics/ |

Common pattern: **independent first judgments → share → synthesize**, review **early when change is cheap**, and **scale ceremony with risk** (Google LCE: low-risk launches get a shorter checklist; Ubl: skip docs when unambiguous).

### 2c. Readiness / Done definitions

| Source | What "done/ready" requires |
|---|---|
| **Scrum Guide 2020** — https://scrumguides.org/scrum-guide.html | DoD = "a formal description of the state of the Increment when it meets the quality measures required"; an item not meeting it "cannot be released or even presented"; org DoD is a minimum. |
| **Google SRE PRR** — https://sre.google/sre-book/evolving-sre-engagement-model/ | Before SRE takes on a service: architecture & dependencies, instrumentation/metrics/monitoring, emergency response, capacity, change management, performance (availability, latency, efficiency). Can start at any lifecycle point; early engagement at design. |
| **Google SRE launch checklist / LCE** — https://sre.google/sre-book/reliable-product-launches/ | Architecture/dependencies, integration, capacity, failure modes, client behaviour, processes/automation, development process, external deps, rollout planning; shorter checklist for low-risk launches. |
| **AWS Well-Architected** — https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html | Six pillars (operational excellence, security, reliability, performance efficiency, cost optimization, sustainability); review is "a constructive conversation… not an audit". |
| **ISO/IEC 25010:2023** — https://quality.arc42.org/standards/iso-25010 (secondary; standard paywalled, preview https://webstore.ansi.org/preview-pages/ISO/preview_ISO+IEC+25010-2023.pdf) | 9 characteristics incl. functional suitability, performance efficiency, compatibility, **interaction capability** (ex-usability, incl. inclusivity, user error protection), reliability, security, maintainability, flexibility, **safety** (new). Sub-characteristic lists only confirmed via secondary sources. |
| **DORA** — https://dora.dev/guides/dora-metrics-four-keys/ | Five delivery metrics: change lead time, deployment frequency, failed deployment recovery time, change fail rate, deployment rework rate. These measure the *process*, post-ready. |
| **WCAG 2.2** — https://www.w3.org/TR/WCAG22/ | Level AA conformance as the UX accessibility floor (our `accessibility.md` already targets 2.2 AA). axe-core finds ~57% of WCAG issues automatically (per our `accessibility.md:288`, citing Deque) → automation is necessary, not sufficient. |
| **Nielsen heuristics** — https://www.nngroup.com/articles/ten-usability-heuristics/ | Heuristic review with severity; sev-4 blocks release. |

---

## 3 · Proposal for our process

### 3a. Councillor roster

Lenses (single-chat, cheap): **C**ontrarian · **F**irst principles · **E**xpansionist · **O**utsider · **X** executor.
Advisor subagents (independent context, own evidence): **Arch** architect · **Sec** security · **AgS** agents-security · **Cmp** compliance-reviewer · **Leg** legal-advisor · **Acc** accountant · **PD** product-designer.

### 3b. Stage × councillor matrix

M = MUST · O = OPTIONAL (trigger) · – = no. Lenses run single-chat unless the stage is a full-council trigger (3c).

| Stage | C | F | E | O | X | Arch | Sec | AgS | Cmp | Leg | Acc | PD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0-2 Idealize (classify, market spec, owner interview) | M | M | M | M (would a buyer get it?) | O | O (new organ/seed implied) | – | O (product embeds an LLM agent) | – | O (personal data, contracts, consumer sale) | O (prices, tax, payments) | M (JTBD/IA questions) |
| 3 Phase 0 / seed-first | M | M | O | – | M | **M** (seed vs product, bone vs organ) | O (new trust boundary) | – | – | – | – | – |
| 4 Verify seed | – | O | – | – | M | O (missing organ ⇒ seed build) | – | – | – | – | – | – |
| 5 Mockup | O | – | O | **M** (newcomer walk-through) | – | – | – | – | – | O (consent/legal copy) | – | **M** |
| 6 Contract | M | O | – | – | M | M if stateful/cross-product; else O | **M** if auth posture / new public route / new table tier | O (agent tool surface) | – | O (LGPD category in Records leg) | O (money fields) | – |
| 7-8 Scaffold + build | – | – | – | – | M | O (design drift found) | O | O | – | – | – | – |
| 9 Wire | – | – | – | O | M | – | – | – | – | – | – | O (empty/error states) |
| 11-12 Test + review (pre-merge) | M | – | – | – | – | – | O | O | **M** (diff + test adequacy) | – | – | – |
| 13 Security pass (new product/route/agent batch) | – | – | – | – | – | – | **M** | M if LLM exposed | – | O (breach clock) | – | – |
| Evaluate (UX + a11y heuristic) | O | – | M (what's missing for the user) | **M** | – | – | – | – | – | – | – | **M** (Nielsen sev + WCAG) |
| 15 Ship routine | – | – | – | – | M | – | – | – | – | – | – | – |
| 16 First go-live | **full council** (3c) |
| 17 Iterate step 4 | M | M | M | M | M | O (by target type: agent ⇒ AgS; UI ⇒ PD) | | | | | | |
| Owner question (noc-questionnaire) | M | M | M | M | M | – | – | – | – | – | – | – |

Rule of thumb: a lens is always cheap — run all five whenever the stage has a judgment; an advisor is MUST only when its *domain evidence* changes the answer (that is what single-chat cannot provide).

### 3c. Full-council triggers (convene all lenses + every relevant advisor as independent subagents, then a chairman synthesis)

1. **New product** — at end of Idealize (before scaffold) and at first go-live (before `prod_consent`).
2. **Irreversible or expensive to reverse** — prod schema migration that drops/reshapes data, data deletion, public URL/domain commitments, vendor lock-in.
3. **New trust boundary** — new public/anonymous surface, new external integration/webhook, BYOK, a new LLM agent talking to the public, multi-tenant isolation change.
4. **Prod-exposure surface registration** (owner's call; the council informs, never decides).
5. **Money / legal exposure** — payments, pricing, tax, contracts, personal-data category added (LGPD).
6. **Seed/organ contract change fanning to ≥3 products** (the pilot-products-first threshold).
7. **Cost estimate > N engineer-days** or an agent can't state the rollback in one line.
8. **Disagreement**: single-chat council's contrarian line lands a "kills the plan" objection the chairman can't rebut → escalate to independent.

### 3d. Single-chat vs independent subagents

- **Single-chat (default):** reversible, local, ≤1 product, no new trust boundary. Evidence: single agent with strong prompts ≈ multi-agent on reasoning (Wang 2024; Smit 2023). Cost ≈1×. Must be labelled "not independent" (already required, `owner-questionnaire.md:39-40`).
- **Independent advisor subagents:** any 3c trigger. Justification is not "more voices" but **separate context + domain evidence** (each advisor reads its own KB and runs its own tools) and avoiding self-enhancement bias (Zheng 2023) and degeneration-of-thought (Liang 2023). Cost ≈4-15× (Anthropic). Protocol (Karpathy/Delphi shape): (1) each councillor gets the same brief, *not* the author's recommendation (avoid anchoring), answers independently; (2) objections are collected anonymised; (3) chairman (tech-lead) synthesises: decision, biggest risk, first step, and which objections were rejected and why.
- **Known limit:** all our advisors are the same model family ⇒ correlated errors (Kim 2025). Diversity comes from evidence/role only. Optional upgrade for the highest-stakes calls: one councillor on a different model family (PoLL, Verga 2024) — needs owner decision (cost, vendor).

### 3e. Measurable refinement loop

Extend before spawn: reuse the auto-improvement ledger the way `method_trial` already does (`mcp/noctusai/tools/noctus/dev/method_trial.py:7-12`).
- **Row `council-objection`:** `{decision_id, stage, councillor, mode: single|independent, objection, severity 0-4, accepted: bool, cost_tokens}`.
- **Row `council-outcome`** (written later, at wrap-up, post-deploy, or on an incident/revert): `{decision_id, objection_ref, proved: right|wrong|untested, evidence}` — evidence = a commit, incident, failing test, rollback, owner reversal.
- **Metrics per councillor:** hit rate = right/(right+wrong); *unique* hit rate (objection raised by nobody else); false-alarm rate; cost per right objection; miss rate = incidents traced to a stage where the councillor was eligible but silent/absent.
- **Mode comparison:** single vs independent hit rate on comparable trigger classes → tells us whether independence pays for itself.
- **Actions:** a councillor with low unique-hit-rate after N≥10 resolved objections is downgraded MUST→OPTIONAL for that stage; misses upgrade it. Surface via `noctus.team.agent_metrics` / wrap-up survey (`noc-wrap-up` already scans the ledger). Build triad: construction (council step emits rows), backstop (keeper: a 3c trigger commit without a council record), telemetry (the metrics above).

### 3f. Product-Done ladder (draft)

Each rung = exit criteria; ✅ = existing tool/keeper checks it; ◐ = partial; ❌ = gap.

**L1 Idealized**
- Problem + user + JTBD + success metric written (PR/FAQ-style one-pager) — ❌ (no artifact/keeper; `scaffold_interrogate` may partly cover — verify).
- Layer classified (step 0) and roster/catalog row intent — ◐ (manual).
- Owner decisions recorded — ◐ (`noc-questionnaire` durable record).
- Council (full, new product) record present — ❌.

**L2 Architected**
- Seed-first §3a filled; seed ships every consumed organ — ✅ `noc-verify-seed` Leg B gates; ◐ §3a not gated.
- Validated mockup for every screen — ◐ (mockup protocol; no keeper).
- Contract per endpoint incl. Records/Metrics leg — ✅ `check_measurable_by_design`, `check_contract_field_provenance_map`.
- Access tier declared for every route/table — ✅ `check_access_tier_routes`/`_tables`/`_streams`.
- Threat model when new trust boundary — ◐ (`noc-security-audit` exists, not gated per product).

**L3 Built**
- Scaffolded from seed; organs consumed canonically — ✅ `scaffold_product`, `check_canonical_organ_consumption`, `check_consent_routes_mounted`.
- RLS on every table — ✅ `check_table_has_rls`, `check_new_org_table_rls`, `verify_db_guards`.
- Every page wired to real data + page-scoped CRUD — ◐ `scan_wiring` static legs ✅; runtime/CRUD legs advisory.
- Honest loading/empty/error states, cache writes — ✅ `check_lying_loading_state`, `check_mutation_invalidate_only` family.
- Registered: catalog row, status_pagina, schema exposure, roster — ✅ `check_status_pagina_role_parity`, `ensure_schema_exposure`, `ensure_product_url_roster`, kb_sync roster check.

**L4 Tested**
- Backend suite + `vite build` green on a pinned tree — ✅ `predeploy_check` (ready/blocked/inconclusive).
- Tests are real (strict 401, no self-monkeypatch, every file gated) — ✅ `check_auth_boundary_false_green`, `check_no_self_monkeypatch`, `check_every_test_file_is_gated`, `check_ci_test_matrix_coverage`.
- **Automated UI probe proves the app works through the UI**: Playwright golden path per product (login via SSO → each nav page renders real data → one create/edit/delete → no console errors), on the merged tree in CI and against prod after deploy — ◐ Playwright exists in CI for core/erp-imobiliario/social-wiring only; `spa_smoke` does not execute JS; ❌ no fleet-wide golden-path, no "every active product has an E2E" keeper (sibling of `check_ci_test_matrix_coverage`).
- a11y automated: axe on smoke routes light+dark — ❌ (`accessibility.md:196`: none).

**L5 Evaluated**
- Heuristic review (Nielsen severity, 3 independent ratings ideal) with no sev-3/4 open — ❌ (product-designer can do it; not a step).
- WCAG 2.2 AA manual pass on key flows — ❌.
- Security pass with no open P0/P1 — ◐ `noc-security-audit`; findings ledger (`findings_ledger`) exists — keeper for "no open P0/P1 on product X before go-live" ❌.
- Performance within budget — ✅ `latency_report` vs `latency-budgets.json`; `perf_probe`.
- Legal/LGPD: privacy notice, base legal per data category — ◐ `lgpd_flag/lgpd_list`, `check_lgpd_entry_removal`.
- Success metric from L1 is measurable (data exists) — ◐ `check_measurable_by_design` at contract time; ❌ no runtime check.

**L6 Ready-to-use (go-live)**
- Owner prod-exposure consent — ✅ `check_prod_exposure_consent`, `prod_consent`.
- Deployed + verified — ✅ `deploy_image` (auto-rollback, swap-verify), `deploy_verify`, `vps.health`, `spa_smoke`, `sso_smoke`.
- UI probe passes against prod — ❌ (see L4).
- Monitoring/alerting + rollback path named — ◐ `prod_watchdog`, `prod-backup` pointer; PRR-style "emergency response" item not checked.
- Docs/live-state aligned — ✅ `scan_live_state_claims`, `check_product_guide_cochange`.
- Owner walkthrough sign-off — ❌ (owner owns "done", per `noc-iterate`).
- Post-launch: DORA-style change-fail/recovery tracked per product — ❌.

Implementation shape: mirror `prontidao` (agents) — one pure `compor` per product returning items {rung, criterion, status, refusal_code}, with the go-live flip in core `/admin/products` calling the same predicates (readiness == gate; `ai-engineering-canon.md:474-490`). Candidate tool: `noctus.dev.product_readiness <slug>`.

---

## 4 · Open questions for the owner

1. **Cost ceiling for independent councils** (≈4-15× tokens): approve the 3c trigger list as the only times subagent councils run?
2. **Different model family** as one councillor for full councils (PoLL evidence) — allowed, and which vendor?
3. **Who chairs**: tech-lead session, or a dedicated chairman that never authored the plan (avoids self-enhancement)?
4. **Product-Done owner sign-off**: is your walkthrough a required L6 criterion, or only for new products?
5. **UI probe scope**: Playwright golden path for every *ativo* product (cost: CI time + per-product fixtures), or only `deploy_scope=live` ones?
6. **a11y bar**: WCAG 2.2 AA as a blocking L5 gate, or advisory until axe keepers exist?
7. **Should the readiness ladder gate the core `/admin/products` live flip** (prontidão-style refusal), or stay advisory first (ratchet)?
8. Is a **PR/FAQ one-pager** wanted as the L1 artifact, or does the market-spec roadmap entry suffice?

## 5 · Evidence caveats
- Debate/council evidence is from QA/reasoning benchmarks; no study found measuring council value for software design review specifically — the refinement loop (3e) exists to measure it locally.
- Klein's "+30%" prospective-hindsight figure not confirmed; not used.
- ATAM, ISO 25010 sub-characteristics, Amazon PR/FAQ, Delphi: only secondary sources read this session.
- Ganguli 2022 red-teaming cited from prior knowledge, not re-fetched.
