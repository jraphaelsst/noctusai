# Audit — `architect` + `engineer-seed` (read-only, 2026-11-05)

Repo: /Users/rapha/Documents/repository/NoctusAI/noctusai. Nothing edited. Paths: `KB § X` = KNOWLEDGE-BASE/CONTEXT/X.

---

# A · architect (`.claude/agents/architect.md`, 76 lines; target 45-65)

## Verdict
A strong in-house **seed/organ/duplication** advisor, but not yet a software architect. It judges *where code goes* (bone or organ, seam or fork, N=2/3 recurrence). It has no tools for *which quality attributes a design trades off*. It has no record format for an affirmative decision. Its KB territory is overloaded at 32 `owns_kb` entries, ~9,000 lines and 4 distinct domains.

## Leanness issues (L1)
- **6 of 13 domain rules restate CLAUDE.md §1.** The agent-context-architecture anti-pattern calls this "Inline universal-rules duplication". The lines are:
  - :51 cache-first, a 5-sentence paragraph
  - :54 verify-the-seed-ships-it
  - :55 the DRY recurrence rule
  - :56 replication-to-seed
  - :61 MCP-first
  - :71 product working scope

  Keep only the architect-specific *application*, e.g. "at PLAN time" or "at LANGUAGE time". Otherwise delete them.
- **3 pointers send the reader to the wrong doc (verified by grep):**
  - :53 says the 4-question test is in `PATTERNS/architect/seed-canonical-defaults.md`. That doc does not contain it. It lives in `KB § 03-SEED-ARCHITECTURE.md` §"Practical decision test", line 51.
  - :54 says verify-the-seed-ships-it is in `seed-absorption.md`. That doc does not contain it. It lives in `03-SEED-ARCHITECTURE.md` line 62.
  - :56 points replication-to-seed at `parallelization-first-orchestration.md`, which only mentions it in a table row. The depth is in `project-execution.md` §298, which is where CLAUDE.md §1 points.
- **:68 is an inline-depth paragraph.** It carries explanatory parentheticals about branch-tree-tracking and ledger-store. It is also merge-flow (see below).
- **Owned-KB pointer block :66-73 is 8 dense lines.** After the ownership split proposed below, it shrinks naturally.

## Strengths to KEEP (hard-won, house-specific)
- **The 4-question bone/organ test** and the canonical-default test (`seed-canonical-defaults.md` §3), meaning "the default is the canonical answer, not consumer #1's coincidence". In practice this is a sharper version of DDD's generic-vs-core subdomain distinction.
- **Isolation ladder: tenant, then pack, then dedicated instance, then fork** (`vertical-seed.md` §4). The placement test runs L0→L3 and recurrence moves things *up*. This is the AWS pool/bridge/silo spectrum, ordered by cost.
- **Named seams over structural forks.** Seams are declared before market #1 (vertical-seed §2). These are good published extension points.
- **Approved-cutover** (both adapters early, owner-approved switch, validation window, retire). This is parallel change / branch by abstraction applied to external dates.
- **Frozen applied organ migrations plus revision files**, and guards declared with the generator (vertical-seed, "Mounting an organ").
- **Phase-0 audit plus "estimate off evidence"**, and pilot-products-first (3 pilots before fan-out). This is a canary for structural change.
- **accept-with-rationale register with revisit triggers** (`PATTERNS/common/accept-with-rationale.md`). It is effectively an ADR log for divergences.
- **Keepers as mechanical gates.** Hundreds of `check_*` gates are, in canon terms, atomic triggered **fitness functions**. The house already practises evolutionary architecture without the name.
- `[F]/[R]/[A]` triage output with file:line evidence, read-only posture, model `opus`.

## Gaps (ranked)
1. **No affirmative decision record.**
   - `:63-64` output shape is a triage verdict only. It has no context, drivers, options, chosen option or consequences.
   - Design decisions live in `projects/<slug>/PROJECT.md`, and project folders are deleted on archive (accept-with-rationale.md opening paragraph admits this leak).
   - accept-with-rationale covers *divergences*, not *choices*. Example: "one shared Supabase, schema-per-product + RLS org_id pooling" is a load-bearing choice with no decision record.
   - grep for ADR/MADR across the KB returns nothing.
2. **No quality-attribute reasoning.**
   - No QA scenarios (source, stimulus, artifact, environment, response, response measure).
   - No utility tree, and no naming of sensitivity points, trade-off points or risks (ATAM).
   - Performance lives in skill `noc-fast-responses`, security in another agent and tenancy in backend. The architect never forces the explicit trade-off between them.
   - grep for "quality attribute" / ATAM / arc42 returns nothing.
3. **No architecture views.**
   - There is no C4 system-context or container view of the platform anywhere: ~20 product containers, 19 schemas in one Supabase, seed/lib packages, tunnel, MCP toolkit, n8n/WAHA.
   - grep for mermaid / "system context" in 02/03/05 returns nothing.
   - A fresh architect re-derives the topology every dispatch.
4. **Fitness functions exist but are unmapped.**
   - Nothing says which keeper protects which architectural characteristic, e.g. tenant isolation → `check_status_pagina_role_parity` and `verify_db_guards`; seed purity → `check_canonical_organ_consumption`; dev/prod parity.
   - So "is quality X guarded?" cannot be answered, and new decisions do not ship with their fitness function.
   - This is the architecture-level form of §1 "gate↔methodology sync".
5. **Bounded contexts and context mapping are implicit.**
   - ERP `party_role` vs commerce `commerce_customers` is decided as "link, never merge (E4)" (vertical-seed ERP table). That is a context-map relationship decided ad hoc.
   - No context map exists per vertical, and no ubiquitous-language glossary exists (pt-BR domain terms such as `negocios`, `captacoes` and `producoes` cross products).
6. **Shared-database integration risk is unnamed.**
   - Independently deployed containers share one Postgres, so there is no rule for cross-schema reads.
   - There is no **expand/contract (parallel change) rule for schema changes** that several containers or the seed see during a rolling deploy. grep in backend/devops patterns found none.
   - Organ frozen-migrations cover only organs.
7. **Multi-tenancy is partial.**
   - The ladder plus RLS plus license gate exist.
   - Missing: noisy-neighbour/denial-of-wallet per tenant, per-tenant metering and cost attribution, tenant-aware observability, tenant data export/erasure (LGPD), and a tenant-isolation test as an explicit fitness function.
8. **No reversibility classification or scaled rigor.**
   - Decisions are not classified as two-way vs one-way door, and there is no "last responsible moment". Everything gets the same ceremony.
   - A cheap reversible choice should be inline. A one-way choice (schema, tenancy, public contract, seed default) should get a decision record, a QA scenario and a fitness function.
9. **No architecture-review rubric** (risk-storming / ATAM-lite checklist) for reviewing a plan. There is a seed-first checklist (`GUIDES/seed-first-design.md`) but nothing broader.
10. **No Conway / Team Topologies lens.** The agent fleet *is* a team topology:
    - stream-aligned: product engineers
    - platform: seed and engineer-seed
    - enabling: architect
    - complicated-subsystem: security, agents-security, accountant

    Cognitive-load limits are exactly why the architect's ownership should split.

## Overload and ownership split
- **Overloaded: yes.** 32 entries, ~9k lines. `project-execution.md` alone is 1,236 lines and `branching-and-merging.md` is 1,931. The 4 domains are:
  - (a) seed and system architecture: seed-canonical-defaults, vertical-seed, approved-cutover, seed-lib-layout, seed-workspace, seed-absorption, absorbed-product-seed-shape-seam, shared-library-conventions, product-working-scope, project-execution, 4 GUIDES
  - (b) orchestration, git and dispatch: git-branch-model, branching-and-merging, branching-dispatch, branch-tree-tracking, ledger-store, dispatch-engineer-tuning, master-tree-parallel-batches, two-session-architect-operator, autonomous-operator-via-subagent, parallelization-first-orchestration, fe-be-contract-first-dispatch
  - (c) MCP toolkit and tooling: mcp-tool-conventions, mcp-first-scripts, dev-toolkit-scaffolders, noc-graph, component-bundle-tool, component-list-and-validation
  - (d) a product engine: `dev-team.md`, the agno multi-agent dev team engine and product. This is a product doc, not architecture.
- **Recommendation:** the architect keeps (a) plus the new craft canon.
  - (b) moves **after noctusai-3d lands** to the tech-lead/orchestration owner. Tech-lead has no agent file today, so the options are `orchestrator-operator` (owns 4) or a declared shared-multi-domain owner.
  - (c) moves to a tooling owner: devops-engineer, or a future toolsmith.
  - (d) moves to backend-engineer, or to that product's own doc home.
  - Do NOT move any (b) doc now: collision zone.
- Note: `PATTERNS/architect/products-consume-canonical-organs.md` and `seed-organ-canonical-set.md` sit in the architect dir but are in `_AGENT_KB_UNOWNED_ALLOWLIST` (compliance.py:19389-19390). That is fine, and intended as commons.

## Proposed new / sharpened L1 rules
- **Decisions leave a record.** A one-way-door choice (schema, tenancy, public contract, seed default, new seam) ships a MADR-shaped decision record (drivers, options, consequences, revisit trigger), not a PROJECT.md line that dies at archive. → `KB § PATTERNS/architect/architecture-craft-canon.md` §Decision records
- **Classify reversibility first; spend rigor proportionally.** Two-way door means decide inline. One-way door means record, QA scenario and fitness function. → canon §Reversibility
- **Name the quality attributes and the trade-off.** Every recommendation states which QAs it optimizes and which it spends (latency, isolation, cost, operability, evolvability), as a measurable scenario. → canon §Quality attributes
- **Every architectural decision ships its fitness function.** The keeper that would go red if the decision eroded, or a NOC-REMEDIATE destination. → canon §Fitness functions · `KB § PATTERNS/common/gate-methodology-sync.md`
- **Shared-DB schema changes are expand → migrate → contract.** Never a breaking rename in one deploy while other containers or the seed read it. → canon §Evolution patterns
- **Tenancy placement uses the isolation ladder, worded pool → bridge → silo, cheapest first.** Name the noisy-neighbour and erasure story. → `KB § PATTERNS/architect/vertical-seed.md` §4 · canon §Multi-tenancy
- **New domain cross-links declare their context-map relationship** (shared kernel / customer-supplier / ACL / separate ways). "Link, never merge" is an ACL decision and should be recorded as one. → canon §Strategic design
- **Fix the 3 pointer targets** (:53 and :54 → `KB § 03-SEED-ARCHITECTURE.md`; :56 → `KB § PATTERNS/architect/project-execution.md`) and **delete the §1 restatements**.

## Proposed craft-canon doc
`KNOWLEDGE-BASE/CONTEXT/PATTERNS/architect/architecture-craft-canon.md`, owned by architect.

1. **Purpose and house mapping.** One table maps canon terms to house terms. It respects the "methodology, not doctrine" vocabulary:
   - seam = published extension point
   - keeper = atomic fitness function
   - accept-with-rationale = divergence ADR
   - isolation ladder = pool/bridge/silo
   - approved-cutover = parallel change
   - pilot-first = canary
2. **Reversibility and rigor scaling.** One-way vs two-way doors, last responsible moment, and which artefacts each tier requires.
3. **Decision records.** Nygard's 5 fields plus MADR's options and consequences. Where they live: a proposed `KB § DECISIONS/` folder or `project-history/decisions/`, append-only, superseded-by links. Relation to accept-with-rationale: divergence vs choice.
4. **Quality attributes.** The 6-part scenario template. A starter utility tree for noc: tenant isolation, p95 latency budget, prod-only deploy safety, cost per tenant, evolvability of seed, LGPD. Sensitivity and trade-off points.
5. **Architecture evaluation (ATAM-lite / risk storming).** A 30-minute plan review checklist with outputs: risks, non-risks, trade-offs.
6. **Views (C4).** Required levels: context and container for the platform, component per organ. Kept as text or mermaid in KB, regenerated from the product registry where derivable. arc42 §§ cross-reference.
7. **Fitness functions.** Taxonomy (atomic/holistic, triggered/continual). The **characteristic → keeper map** (a table, ideally derived). The rule that a decision ships its function.
8. **Strategic design.** Subdomains (core/supporting/generic), and how they map to L0/L1/L2/L3. Bounded contexts per vertical, context-map relationships, and the ubiquitous-language glossary (pt-BR terms).
9. **Deployment-unit style.** Modular monolith vs services in noc's actual shape: per-product containers with shared libs and a shared DB. Shared-database integration risks, cross-schema read rules, and when a product earns its own DB.
10. **Evolution patterns.** Parallel change / expand-contract, branch by abstraction, strangler fig (absorptions), and Hyrum's law for seed exports (consumer-count first).
11. **Multi-tenancy.** Pool/bridge/silo mapped onto the ladder. RLS as the pool boundary and its failure modes (status_pagina lesson). Noisy neighbour and denial of wallet, per-tenant metering, tenant-aware logs, export/erasure.
12. **Team topology lens.** The agent fleet as stream-aligned / platform / enabling / complicated-subsystem. Conway's law and cognitive load as an ownership-split criterion.
13. **Anti-patterns.** Résumé-driven services, distributed monolith, shared-DB "integration", architecture by coincidence-default, an undocumented one-way door, a fitness function nobody wired.
14. **Decision checklist** (one page) plus **sources**.

**Worked examples** (all from this codebase):
- **Retro-ADR plus QA scenario: "one Supabase, schema-per-product, RLS by org_id (pool) with dedicated-instance escape (silo)."**
  - Drivers: cost, ops load and SSO.
  - Consequences: noisy neighbour and blast radius.
  - Fitness functions: RLS keepers, `verify_db_guards`, `check_status_pagina_role_parity`.
- **P Studio billing `ProvedorCobranca`, Asaas → Banco do Brasil** (02-LANDSCAPE row) as branch-by-abstraction plus approved-cutover. Written as a MADR with the validation window as the response measure.
- **Commerce ↔ ERP customers "link, never merge (E4)"** as a context map (customer-supplier / ACL), with a C4 container view of `noctusai_lib/domain/{commerce,erp}` plus the organ mount (`mount_finance`).

## Merge-flow — leave for noctusai-3d
- architect.md:58 "Tech-lead owns merge + push … `noctus.dev.release`"
- architect.md:59 parallelization-first dispatch
- architect.md:60 collision-class at dispatch (→ branching-dispatch.md)
- architect.md:68 the whole "Orchestration & dispatch" pointer block
- frontmatter :15-24 (master-tree-parallel-batches … autonomous-operator-via-subagent, including git-branch-model, branching-and-merging, branching-dispatch, branch-tree-tracking, ledger-store, dispatch-engineer-tuning)

Re-home them only after the redesign lands.

## Frontmatter
- `model: opus`: correct for judgment work.
- `tools`: add **WebFetch**. It has WebSearch but cannot open or verify a source, which conflicts with citing primary sources.
  - Bash on a read-only advisor is unenforced read-only. Acceptable, but say "Bash for read-only inspection only" in the mission.
- `description`: add triggers. Suggested: "trade-off", "design review", "ADR/decision record", "quality attributes", "multi-tenant / isolation", "should this be its own service/DB", "schema change across products", "context map".

---

# B · engineer-seed (`.claude/agents/engineer-seed.md`, 80 lines; procedure carve-out, owns no KB)

## Verdict
An excellent **safety and integration protocol**: worktree, base, commit, no-bypass, the return contract. It is thin as a **senior engineer's craft discipline**. It does not say how to understand the ask, write the test first, keep a commit reviewable, review your own diff, or know you are done. Also, its "standing protocol for ALL engineers" claim is not mechanically true: specialist engineers do not auto-load it.

## Leanness issues
- **Paragraph-rules:**
  - :31 branch pointer, 4 sentences
  - :40 scoped verification, 6 sentences, including a worktree import gotcha
  - :41 hardware gate
  - :55 before-returning, ~9 lines
- :55 restates the 3 items of `BEFORE_RETURNING_BLOCK` (`mcp/noctusai/tools/noctus/dev/engineer_brief_compose.py:415`) while saying the composer is the single source. That is a drift risk. Keep one line plus the pointer.
- Frontmatter :4-14 is 10 lines of YAML-comment rationale. The rationale already lives in `dispatch-engineer-tuning.md` §4/§4·1, so reduce it to a one-line pointer.
- The carve-out is legitimate (agent-context-architecture "engineer-seed exempt"), but craft depth should still go to KB.

## Strengths to KEEP
- The return contract with **mandatory clean legs** (`drift-found`, `scoped-improvement`, `codification-events`). It states plainly that "absence is a positive claim".
- **"Prove it landed"** (`git show --stat HEAD`, harness-overlay divergence tell, :52).
- **File-disjoint, then STOP and surface** rather than widening scope. Also surface-and-resume tooling, and time-box with "never silently shrink".
- Explicit `git add <paths>`. One logical change per commit. Conventional-Commits subject.
- **No `--no-verify`** plus the rationalization catalogue (:76-77).
- The hardware-admission gate for heavy runs (an 8 GB machine lesson).
- Full suite of touched packages before returning (ImovelDetalhes lesson). Docs follow code in the same commit.
- Sonnet default with **measured escalation triggers** (dispatch-engineer-tuning §4·1). Keep the frontmatter decision.

## Gaps (ranked)
1. **Not actually loaded for most engineer dispatches.**
   - backend-engineer.md:83, frontend-engineer.md:30 and devops-engineer.md:48 say "Apply the engineer-seed standing protocol" and give only a parenthetical summary. A subagent of those types gets its own file, not this one.
   - Fix: a shared KB discipline doc pointed from all four, and/or the composer inlining the protocol pointer. Not a redesign of dispatch.
   - Drift: orchestrator-operator.md:231 cites "engineer-seed.md § 10", which no longer exists (current sections are §1-§5).
2. **No "understand the ask" step.**
   - The measured Sonnet miss was **semantics hidden in one word** ("latest" was averaged over all history; dispatch-engineer-tuning §4·1).
   - Rule: restate the Acceptance and every load-bearing qualifier (latest / only / per X / ordering / window) with the chosen interpretation before coding, and echo it in the return.
3. **No test-first / red-first rule.**
   - A bug fix should start with a failing regression test. A guard should be proven by watching it REFUSE.
   - The house already has this as `methodology-execution-discipline.md` §4 ("Prove the check can FAIL") and §8, and `compliance/testing.md` "Regression tests in practice". None of it is in the engineer protocol.
4. **No "use the seam, never self-monkeypatch" rule in L1.**
   - It is the #1 measured miss (3/12 slices, §4·1) and a §1 rule gated at write time.
   - Pointer: `compliance/testing.md` §"No self-monkeypatching — refactor playbook" (line 486).
5. **No self-review of own diff before returning** (Google author guide, SWE-book ch. 9). Read `git diff origin/dev...HEAD` as a reviewer would:
   - debug leftovers
   - names
   - **re-run tests after a late rename** (measured miss)
   - dead code
   - comments that explain *why*
6. **"Wire what you add" is missing.**
   - A new keeper, tool or param is not done until it is registered (hook wiring, `toolkit_freshness._MAPPED_PARAMS`, CLI flag). Both are measured misses.
   - Pointer: `KB § PATTERNS/common/gate-methodology-sync.md`.
7. **Commit craft is subject-only.**
   - No body explaining *why*, no Conventional-Commits `!` / `BREAKING CHANGE:` footer. That footer is the input to §1 SemVer.
   - No "separate refactor/tidy commits from behaviour commits" (Google small CLs; Beck "Tidy First").
   - This also resolves the fix-on-contact vs file-disjoint tension: fix-on-contact *inside* the slice goes in its own commit; *outside* the slice it is `drift-found`.
8. **No consolidated Definition of Done.** DoD is spread over §2-§4. A single checklist should be:
   - acceptance met
   - interpretation stated
   - red-first test
   - full touched-suite
   - self-review
   - docs
   - wired/registered
   - committed and landed
   - return legs
9. **No consumer-awareness for seed/lib changes.**
   - Hyrum's law: before changing an exported seed symbol or default, list its consumers (`noctus.graph.*` / `refs`). Back-compat or expand/contract, and pilot-first.
   - Seed engineers touch the most-shared code with the least guidance here.

## Proposed new / sharpened L1 rules
- **Restate the ask.** Acceptance plus every load-bearing qualifier, with your interpretation, before the first edit, and again in the return (`interpretation:` line). → `KB § PATTERNS/common/engineer-operating-discipline.md` §Understand
- **Red first.** A bug gets a failing test before the fix. A guard is proven by making it refuse. → `KB § PATTERNS/common/methodology-execution-discipline.md` §4/§8
- **Test through the seam, never patch our own module.** → `KB § PATTERNS/compliance/testing.md` §No self-monkeypatching
- **Self-review the diff as its reviewer, and re-run after any rename.** → discipline §Self-review
- **Wire what you add.** Keeper→hook, tool param→`_MAPPED_PARAMS`, flag→CLI. → `KB § PATTERNS/common/gate-methodology-sync.md`
- **Tidy and behaviour in separate commits. The body says why. A breaking change carries `!`/`BREAKING CHANGE:`.** → discipline §Commits · `KB § PATTERNS/common/versioning.md`
- **Touching a seed/lib export? List consumers first. Keep it back-compatible or expand/contract.** → discipline §Shared code · `KB § PATTERNS/architect/project-execution.md` §2.12
- **Done = the DoD checklist.** It replaces the scattered :42/:55/:56 lines. → discipline §DoD

## Proposed craft-canon doc
`KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/engineer-operating-discipline.md`.

Add it to `_AGENT_KB_UNOWNED_ALLOWLIST` as universal commons for every executor (keeps engineer-seed's no-KB exemption). Point to it from engineer-seed, backend-engineer, frontend-engineer and devops-engineer.

1. **Scope.** Executor discipline vs the integration mechanics (pointer to the git docs, which are not restated).
2. **Understand the ask.** Read the brief/PROJECT §4a, restate acceptance, list the load-bearing qualifiers, state assumptions, and know when to surface.
3. **Plan the slice.** Smallest vertical increment, file-disjoint, time-box, and cutting scope out loud.
4. **Test-first where it fits.** TDD loop. Red-first for bugs and guards. When TDD does not fit (exploratory UI, config) you still need a proof that it can fail. Test sizes and pyramid. Seams over monkeypatch. Strict-401 auth tests.
5. **Make the change.** AST-first, cache-first discovery, fix-on-contact inside the slice vs drift-found outside, Hyrum's law for shared code.
6. **Self-review.** The Google author-guide checklist adapted (design, functionality, complexity, tests, naming, comments, docs).
7. **Commits.** Small and reversible. Conventional Commits incl. breaking footer → SemVer. Subject/body rules. Tidy vs behaviour separation.
8. **Definition of Done.** One checklist, mirroring `BEFORE_RETURNING_BLOCK` by reference.
9. **Reporting.** Honest status, the interpretation line, and the 5-category block when not clean.
10. **Measured misses ledger.** Pointer to dispatch-engineer-tuning §4·1 and the brief's "Your recent misses" block.
11. **Anti-patterns.**
12. **Sources.**

**Worked examples:**
- **"latest score rows"**: the Opus vs Sonnet A/B (§4·1) rewritten as restate-the-qualifier.
- **ImovelDetalhes page harness** (2026-10-24): scoped green, full-suite red. Why DoD includes the touched package's full suite.
- **A self-monkeypatched test refactored to the DI seam**, red-first (compliance/testing.md §486 playbook; `KB § PATTERNS/backend/di-test-seam.md`).

## Merge-flow — leave for noctusai-3d (flag only)
- §1 :23-31: worktree/base check, rebase-when-behind, `WORKTREE-BASE-DIVERGE`, branch_pointer protocol.
- §3 :46-48, :50 (`feat/<slug>` ownership, add/commit mechanics), :53 (never push / never touch dev, main or prod; amend rules), :55 (`task_branch integrate` re-runs and refusals), :56.
- §4 :63 (`Commits:` from `origin/dev..HEAD`), :72 (→ branching-and-merging.md).
- :80 (`task_branch` isolation, `wire_env`, tech-lead integration).
- Adjacent, keep wording but coordinate: :51-52 (pre-commit hook as gate; harness-overlay "prove it landed").

## Frontmatter
- `tools` least-privilege allowlist: keep.
- `model: sonnet` with the escalation rule: keep, now evidence-backed.
- Shrink the YAML-comment rationale to a pointer.
- `description` is fine for a default agent. Optionally add "definition of done / commit / test-first" so it also reads as the engineer craft reference.

---

# Sources (all fetched and HTTP 200 confirmed 2026-11-05)

**Architecture**

| Source | URL | Supports |
|---|---|---|
| Nygard, Documenting Architecture Decisions | https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions | ADR origin, 5 fields |
| ADR GitHub organization | https://adr.github.io/ | ADR practice hub |
| MADR | https://adr.github.io/madr/ | options and consequences template |
| Fowler, Architecture Decision Record | https://martinfowler.com/bliki/ArchitectureDecisionRecord.html | ADR practice |
| joelparkerhenderson/architecture-decision-record | https://github.com/joelparkerhenderson/architecture-decision-record | template catalogue |
| C4 model | https://c4model.com/ · https://c4model.com/diagrams | views |
| arc42 overview | https://arc42.org/overview | doc structure |
| arc42 §9 Architecture decisions | https://docs.arc42.org/section-9/ | where decisions live |
| arc42 §10 Quality | https://docs.arc42.org/section-10/ | quality tree and scenarios |
| SEI, ATAM | https://insights.sei.cmu.edu/library/the-architecture-tradeoff-analysis-method/ | evaluation method |
| Kazman/Klein/Clements, ATAM: Method for Architecture Evaluation (SEI TR, 2000) | https://insights.sei.cmu.edu/documents/629/2000_005_001_13706.pdf | utility tree, sensitivity and trade-off points |
| Fowler, Bounded Context | https://martinfowler.com/bliki/BoundedContext.html | strategic design |
| Fowler, Domain Driven Design | https://martinfowler.com/bliki/DomainDrivenDesign.html | strategic design |
| Evans, DDD Reference | https://www.domainlanguage.com/ddd/reference/ | context-map patterns |
| Thoughtworks Radar, Architectural fitness function | https://www.thoughtworks.com/radar/techniques/architectural-fitness-function | fitness functions |
| Thoughtworks, Fitness function-driven development | https://www.thoughtworks.com/insights/articles/fitness-function-driven-development | fitness functions |
| Building Evolutionary Architectures | https://www.thoughtworks.com/insights/books/building-evolutionary-architectures | fitness functions |
| Fowler, MonolithFirst | https://martinfowler.com/bliki/MonolithFirst.html | deployment-unit style |
| Fowler, MicroservicePremium | https://martinfowler.com/bliki/MicroservicePremium.html | deployment-unit style |
| Fowler, MicroservicePrerequisites | https://martinfowler.com/bliki/MicroservicePrerequisites.html | deployment-unit style |
| Lewis and Fowler, Microservices | https://martinfowler.com/articles/microservices.html | deployment-unit style |
| Grzybek, Modular Monolith: A Primer | https://www.kamilgrzybek.com/blog/posts/modular-monolith-primer | deployment-unit style |
| Fowler, ConwaysLaw | https://martinfowler.com/bliki/ConwaysLaw.html | team lens |
| Team Topologies key concepts | https://teamtopologies.com/key-concepts | four team types, cognitive load |
| AWS SaaS Lens, Silo, Pool, and Bridge Models | https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/silo-pool-and-bridge-models.html | tenancy models |
| AWS SaaS Architecture Fundamentals | https://docs.aws.amazon.com/whitepapers/latest/saas-architecture-fundamentals/saas-architecture-fundamentals.html | tenancy models |
| Azure, Tenancy models | https://learn.microsoft.com/en-us/azure/architecture/guide/multitenant/considerations/tenancy-models | tenancy models |
| Azure, Multitenant storage and data approaches | https://learn.microsoft.com/en-us/azure/architecture/guide/multitenant/approaches/storage-data | tenancy models |
| PostgreSQL Row Security Policies | https://www.postgresql.org/docs/current/ddl-rowsecurity.html | pool boundary |
| Supabase RLS guide | https://supabase.com/docs/guides/database/postgres/row-level-security | pool boundary |
| Fowler, ParallelChange | https://martinfowler.com/bliki/ParallelChange.html | expand/contract |
| Fowler, BranchByAbstraction | https://martinfowler.com/bliki/BranchByAbstraction.html | approved-cutover analogue |
| Fowler, StranglerFigApplication | https://martinfowler.com/bliki/StranglerFigApplication.html | absorptions |
| Fowler et al., Patterns of Legacy Displacement | https://martinfowler.com/articles/patterns-legacy-displacement/ | absorptions |
| Hyrum's Law | https://www.hyrumslaw.com/ | shared-export compatibility |
| AWS Well-Architected | https://aws.amazon.com/architecture/well-architected/ | QA pillars checklist |
| Azure Well-Architected | https://learn.microsoft.com/en-us/azure/well-architected/ | QA pillars checklist |
| Google SRE book, Simplicity | https://sre.google/sre-book/simplicity/ | essential vs accidental complexity |
| Fowler, Who Needs an Architect? (IEEE Software) | https://martinfowler.com/ieeeSoftware/whoNeedsArchitect.pdf | architecture = the decisions that are hard to change, i.e. the reversibility lens |

**Engineering discipline**

| Source | URL | Supports |
|---|---|---|
| Google eng-practices, Developer guide | https://google.github.io/eng-practices/review/developer/ | author guide |
| Google eng-practices, Small CLs | https://google.github.io/eng-practices/review/developer/small-cls.html | small CLs, separate refactorings |
| Google eng-practices, CL descriptions | https://google.github.io/eng-practices/review/developer/cl-descriptions.html | why in the body |
| Google eng-practices, Reviewer standard | https://google.github.io/eng-practices/review/reviewer/standard.html | self-review bar |
| Software Engineering at Google, ch. 9 Code Review | https://abseil.io/resources/swe-book/html/ch09.html | review |
| Software Engineering at Google, ch. 11 Testing Overview | https://abseil.io/resources/swe-book/html/ch11.html | testing |
| Software Engineering at Google, ch. 12 Unit Testing | https://abseil.io/resources/swe-book/html/ch12.html | testing |
| Conventional Commits 1.0.0 | https://www.conventionalcommits.org/en/v1.0.0/ | `!`/BREAKING CHANGE → SemVer |
| Semantic Versioning | https://semver.org/ | SemVer |
| Beams, How to Write a Git Commit Message | https://cbea.ms/git-commit/ | commit message craft |
| Fowler, TestDrivenDevelopment | https://martinfowler.com/bliki/TestDrivenDevelopment.html | TDD |
| Fowler, SelfTestingCode | https://martinfowler.com/bliki/SelfTestingCode.html | self-testing code |
| Vocke, The Practical Test Pyramid | https://martinfowler.com/articles/practical-test-pyramid.html | test pyramid |
| Fowler, OpportunisticRefactoring | https://martinfowler.com/bliki/OpportunisticRefactoring.html | fix-on-contact |
| Beck, Tidy First (newsletter) | https://tidyfirst.substack.com/ | tidy vs behaviour separation |
| Scrum Guide | https://scrumguides.org/scrum-guide.html | Definition of Done |
| Fowler, Yagni | https://martinfowler.com/bliki/Yagni.html | scope |
| Fowler, TechnicalDebtQuadrant | https://martinfowler.com/bliki/TechnicalDebtQuadrant.html | deliberate vs inadvertent debt |
| Fowler, Ship / Show / Ask | https://martinfowler.com/articles/ship-show-ask.html | context only (merge-flow adjacent, for noctusai-3d) |

Not confirmed (do not cite): scrum.org DoD page (403); O'Reilly book pages for *Fundamentals of Software Architecture* and *Software Architecture: The Hard Parts* (403). Cite the books by title and ISBN only.
