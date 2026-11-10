# Product roles research: `product-architect`, `product-engineer`, and other product professions

Date: 2026-11-09. Tree: `.claude/worktrees/assistant-chatbot` (origin/dev tip). This was a read-only research pass. Nothing in the repo was edited.

Source labels used below:
- **[read]** I fetched the page and read the cited passage.
- **[snippet]** The claim comes from a search-result summary only. The page was not opened, so the claim is unverified.
- **[paywall]** The normative text was not available.

---

## Part A — dev_team extraction

### A.0 The key fact before extracting anything

`dev_team/MASTER-PROMPT.md:27` says: "Role charters are derived from the refined Claude-side specialists, `.claude/agents/*.md` … (refinement of 2026-11-05)." `dev_team/src/dev_team/charters/shared.md:3` says the same: it was "Resynced 2026-11-05 against `CLAUDE.md` v4.0 and the refined `.claude/agents/*.md`".

So for 9 of the 12 charters, knowledge flowed **from** our tree **into** dev_team. Copying those charters back would recreate the same content in a second place (the anti-pattern in `KB § PATTERNS/common/agent-context-architecture.md` "Anti-patterns" and "A fat charter drifts"). Only three kinds of item are worth extracting:
1. roles with no Claude-side counterpart;
2. items that exist in a charter but nowhere in our KB or agents;
3. drift, where a charter now disagrees with our KB.

`products/dev-team/` is only the control surface: a FastAPI proxy plus a React dashboard of agents, metrics and a run-task page. It defines no agents. **Nothing to extract from it.**

### A.1 Agents defined in dev_team

The 11 specialists plus the Leader are listed in `KB § PATTERNS/architect/dev-team.md` §6. Tools come from `dev_team/src/dev_team/tools/allowlists.py:21-125`. Models come from `configs/default.yaml`.

| agno role | Charter (lines) | Mission (charter §1) | Tools | Model | Our counterpart |
|---|---|---|---|---|---|
| `leader` | leader.md (85) | Orchestrate, route, pause on stuck-triggers, be the single voice | read_kb, read/write_memory, delegate, invoke_subteam | Opus | the tech-lead orchestrator (no agent file; `orchestration-craft-canon.md` §3.4) |
| `product_manager` | product_manager.md (85) | "Own the *what* and the *why*" (:5) | read_kb, read/write_memory, web_search, read_files | Opus | **none** (see A.2) |
| `ux_designer` | ux_designer.md (82) | Mockup-first spec | read_kb, memory, web_search, read_files | Sonnet | `product-designer` (the charter is derived from it) |
| `solution_architect` | solution_architect.md (87) | "Own the *how* at the system level" (:5) | read_kb, memory, read_files, recurrence_scan, keeper_validate, ast_* | Opus | `architect` |
| `backend_engineer` | backend_engineer.md (112) | Server-side slices to the Architect's contracts | + write/edit_files, shell, ast_python | Sonnet | `backend-engineer` (also carries integrations-engineer and ai-engineer, per MASTER-PROMPT.md:33-34) |
| `frontend_engineer` | frontend_engineer.md (96) | Validated mockup → product UI via seed factories | + write/edit, shell, ast_typescript | Sonnet | `frontend-engineer` |
| `devops_engineer` | devops_engineer.md (93) | Containers, CI, fleet; "holds the SRE seat" | + write/edit, shell, ast_* | Sonnet | `devops-engineer` (and `tooling-engineer`) |
| `security_engineer` | security_engineer.md (98) | Adversarial AppSec | read_files, keeper_validate/review, web_search, recurrence_scan | Opus | `security` and `agents-security` |
| `qa_engineer` | qa_engineer.md (87) | "Make the suites tell the truth" | + write/edit, shell (pytest/vitest/playwright), ast_* | Sonnet | `test-engineer` |
| `code_reviewer` | code_reviewer.md (91) | Review plus the bundled phase proposal | read_files, recurrence_scan, keeper_validate, file_proposal | Opus | `compliance-reviewer` |
| `technical_writer` | technical_writer.md (93) | Docs, §11 entries, KB depth | read_files, write/edit_files (*.md + KB only) | Sonnet | **none** (doc work is done by the tech-lead under eight-way sync plus the `kb_sync` hooks) |

The three sub-teams are in `dev_team/src/dev_team/teams/*.py` and all run in `mode="collaborate"`:
- `design_review_team`: Architect (lead), Backend, Frontend, DevOps, Security. Our equivalent is ATAM-lite in `architecture-craft-canon.md` §5.
- `code_review_team`: Code Reviewer (lead), Security, QA. Our equivalents are `compliance-reviewer` and the `noc-security-audit` skill.
- `incident_response_team`: led by DevOps. Our equivalents are `ops-steward` and `devops-engineer`.

MASTER-PROMPT.md:29-41 maps the Claude-only roles to the agno charter that carries their lens. legal-advisor and accountant are carried by `product_manager`; ops-steward by leader and devops; reverse-engineer by solution_architect; skill-scout by technical_writer; agents-security by security_engineer.

### A.2 `product_manager`: what it does, and who does PM work today

**What the charter does** (`dev_team/src/dev_team/charters/product_manager.md`):
- **Mission (:5):** translate fuzzy requests into requirements, user stories and acceptance criteria; push back on scope creep; define success metrics.
- **Responsibilities (:9-14):**
  - Connextra stories;
  - flag ambiguity at intake;
  - surface scope creep for an explicit user OK;
  - a success metric per feature;
  - the "data-protection five questions" at intake, split with Security;
  - the prioritized backlog.
- **Outputs (:18-22):** requirements doc, stories with acceptance criteria, prioritized backlog, data-protection intake, success metrics.
- **Handoffs (:32-34):** to the Architect (requirements, acceptance criteria, data intake), to UX (stories and flows), and back to the Leader when stuck.
- **Boundary (:54-56):** does not specify implementation ("If you find yourself naming libraries or DB columns, hand it to the Architect"); does not design UI; never skips the data questions.
- **Tools (:42-50):** spec-side only, with no write, edit or shell.
- **Model:** Opus (`default.yaml`; the rationale is that PM is a "high-leverage decision agent").
- **Craft canon (:72-85):**
  - discovery and spec: interview, never assume (≤4 questions); JTBD before the story; testable acceptance; product working scope; mockup-first hand-off;
  - a legal/consumer lens (escalate to OAB);
  - a unit-economics lens (escalate to CRC).

**Is it covered in `.claude/agents/`?** No. A grep of `.claude/agents/` for `acceptance criteria|success metric|Connextra|five questions` returns nothing, and no agent mentions "product manager" or "product owner". Today PM work is spread over five places, and nobody owns it:

| PM duty | Who does it today | Evidence | Gap |
|---|---|---|---|
| Decide what to build, priority, value and viability | **The owner (human)** | `orchestration-craft-canon.md` §6.2 table: the owner holds "permissions, consent, priority between sessions"; prod exposure is "the user's" (CLAUDE.md §1) | None. This is correctly the owner's. An agent can only draft. |
| Discovery: interview, JTBD, user needs | `product-designer` | `design-craft-canon.md` §2.1-§2.4; product-designer.md "Interview, never assume a spec" | Covered, but only for screen work. A non-UI feature (an API, a job, an agent behaviour) gets no discovery owner. |
| Requirements doc, stories, acceptance criteria in user terms | Nobody. The tech-lead writes a brief whose "Acceptance" is a **command**. | `orchestration-craft-canon.md` §5.3; `dispatch-engineer-tuning.md` §4d | **Gap.** A command proves "the code does X". Nothing states "the user can do Y" (Given/When/Then). |
| Success metric per feature | Partly: `architect` via measurement-by-design §2.7, a "Records / Metrics" section in the contract | `KB § PATTERNS/architect/measurement-by-design.md` §2 | **Half-gap.** The data side ("what does it record") is owned. The target side ("which number, moving how far, proves it worked") is not, and neither is any post-ship check against it. |
| Scope-creep surfacing; backlog ordering | Tech-lead plus PROJECT.md §6; roadmaps via `noc-roadmap` | CLAUDE/projects.md | Partial. No product-level backlog per product exists. |
| Data intake at spec time | `security` (LGPD intake) and `KB § PATTERNS/security/lgpd.md` §3 | — | Owned by security, but at review time, not intake time. |
| Legal and finance lenses | `legal-advisor`, `accountant` | MASTER-PROMPT.md:36-37 (folded into PM only because agno lacks those roles) | Covered. Do **not** extract. |

**Drift found (fix-on-contact candidate; I am read-only, so it is reported here with a destination).** product_manager.md:13 claims its five questions follow "`KB § PATTERNS/security/lgpd.md § 3`", and :63 lists them "verbatim" as:
1. categories
2. storage location
3. who can read
4. consent
5. retention deadline

The KB's actual §3 (lgpd.md:38-51) lists different questions:
1. Basis
2. Minimization
3. Destination
4. Retention
5. Tenant isolation

The charter has drifted from the KB it cites. Destination: a one-line fix in `dev_team/src/dev_team/charters/product_manager.md:13,:63` on a self-branch, making the charter point at the KB list instead of restating it.

### A.3 Extraction list, per dev_team agent

Verdicts: **EXTRACT** (worth moving), **ALREADY** (already in our tree), **NO** (not worth it).

**product_manager.md**
| Item (file:line) | Verdict | Target in our tree |
|---|---|---|
| Mission "what and why" vs Architect's "how" (:5, :54 "naming libraries or DB columns → hand it to the Architect") | EXTRACT | `.claude/agents/product-architect.md` Mission plus Boundary |
| Testable acceptance: "'It feels fast' is not acceptance; 'P95 < 200ms …' is" (:64); Given/When/Then (:75) | EXTRACT | new `KB § PATTERNS/product/product-craft-canon.md` §acceptance; one L1 rule in product-architect |
| Scope-creep protocol: capture the "oh, and also…", name the trade-off (smaller scope vs longer timeline vs deferred sub-feature), let the user decide (:61, :65) | EXTRACT | product-craft-canon §scope; L1 rule |
| Success metric per feature: "what observable signal proves it works in production" (:12, :22) | EXTRACT | product-craft-canon §metrics, pointing at `measurement-by-design.md` §2.7 (architect-owned) for the data side |
| Replication-to-seed LANGUAGE trigger applied to requirements docs ("add this to ERP and PF and Therapy" → escalate) (:60) | EXTRACT (one line) | product-architect L1. It is the most likely place for the slip to be written first. |
| Outputs list: requirements doc, stories, backlog, data intake, metrics (:18-22) | EXTRACT | product-architect "Output shape" |
| Tool matrix: spec-side, no write/shell (:42-50; allowlists.py:29-35); Opus (default.yaml) | EXTRACT as a design input | product-architect frontmatter: `tools: Read, Grep, Glob, Write(spec only), WebSearch, WebFetch, mcp__noctusai__*`, `model: opus` |
| Five data questions (:13, :63) | NO. Drifted (see A.2). | Point at `lgpd.md` §3 instead |
| ≤4-question batches (:73) | ALREADY | `.claude/skills/noc-questionnaire/SKILL.md:35` |
| Legal/consumer lens (:79-81) and finance lens (:83-85) | NO | owned by `legal-advisor` and `accountant` |
| `write_memory(scope="decisions")` (:46, :66) | NO | agno-memory-specific; our equivalent is decision records and the findings ledger |

**leader.md**
| Item | Verdict | Target |
|---|---|---|
| Stuck-triggers: "agent timeout, repeated rejection from a sub-team, contradictory outputs across two agents on the same question, ambiguity that needs the user" (:14, :69) | EXTRACT (small). Our MAST table covers FM-2.2 (clarification) but has no explicit "two advisors contradict each other → pause and ask" row. | `KB § PATTERNS/architect/orchestration-craft-canon.md` §5.9 (one row) |
| One face to the user (:65), end-of-work summary (:13), phase cadence (:15) | ALREADY | orchestration-craft-canon §3.4 "single voice"; project-execution §4 |
| Coordinate vs collaborate mode cost-awareness (:70) | NO | agno-specific |

**solution_architect.md**: NO, overall (derived from `architect`). Two notes:
- **Divergence, not an extraction:** :12 and :23 make the Architect author API contracts and schemas. The house rule is that the tech-lead writes the contract and the architect advises (`orchestration-craft-canon.md` §3.4, decision-table row 2). Keep ours.
- :72 "AST-first applies to your design notes too; name the libcst/ts-morph operation" is ALREADY implied by CLAUDE.md §1 AST-first. Optional one-liner in architect.md.

**ux_designer.md**: NO (derived from `product-designer`). The known-gaps item (:60, focus reset and failing token pairs) is ALREADY in `KB § PATTERNS/design/accessibility.md` (:280 "Seed fixes (focus reset, …)").

**qa_engineer.md**
| Item | Verdict | Target |
|---|---|---|
| "Each PM criterion has at least one test asserting it (a comment in the test or plan is the traceability link)" (:11) | EXTRACT. `test-engineer.md` has no "acceptance" mention (grep returned nothing). It becomes load-bearing once product-architect writes acceptance criteria. | `.claude/agents/test-engineer.md` one L1 rule → `KB § PATTERNS/compliance/test-engineering-canon.md` |
| "Behavioural independence: the agent that wrote the feature does not write its tests" (:5, :52) | EXTRACT as a question for the owner. It conflicts with our engineer protocol (red-first tests by the implementing engineer, `engineer-seed`). Do not adopt silently. | Owner decision. If yes: `test-engineering-canon.md` |
| All the rest (strict 401, flaky quarantine, seed kit, builders) | ALREADY | test-engineer and testing canon (the charter is derived from them) |

**code_reviewer.md**: NO. Replication-to-seed cross-check, bundled proposal and Conventional Comments are ALREADY in `compliance-reviewer.md` (:26, :34, :41) and `KB § PATTERNS/compliance/code-review-craft.md`.

**technical_writer.md**
| Item | Verdict | Target |
|---|---|---|
| Diátaxis: "Every doc is exactly one of tutorial, how-to, reference, or explanation; do not blend them" (:86) | EXTRACT. A grep for `diataxis` across `KNOWLEDGE-BASE/` and `.claude/` returns nothing, so the charter is ahead of our KB. | `KB § PATTERNS/common/doc-discipline-family-index.md` (one rule) or the KB doc-craft member it routes to |
| §11 entry exemplar: "'Phase done' is not an entry; 'Phase 2 ✅ — wired ERP services …, 4 services migrated, smoke green' is" (:65) | EXTRACT (small) | `CLAUDE/projects.md` or `KB § PATTERNS/architect/project-execution.md` §11 guidance |
| Doc-staleness, eight-way sync, router discipline, lossless refactor (:71-93) | ALREADY | doc-discipline family |

**backend_engineer.md, frontend_engineer.md, devops_engineer.md, security_engineer.md**: NO. All are derived from our agents. Our devops-engineer already owns `sre-craft-canon.md` with SLO and error-budget rules (devops-engineer.md:38, :66).

**teams/*.py**: NO. They are agno wiring. Our "parallel lenses, not redundant" review is already the `noc-security-audit` plus `compliance-reviewer` composition.

---

## Part B — reliable definitions

### B.1 `product-architect`: two different things share the name

**Sense U — product architecture (engineering design and management science).**

**Ulrich (1995)** [read: the PDF pages 419-421 were rendered and read]:
- "Product architecture is the scheme by which the function of a product is allocated to physical components."
- Defined "more precisely as: (1) the arrangement of *functional elements*; (2) the mapping from *functional elements* to *physical components*; (3) the specification of the *interfaces* among interacting physical components."
- The abstract links architecture to "five areas of managerial importance: (1) product change; (2) product variety; (3) component standardization; (4) product performance; and (5) product development management".
- Ulrich says architectural decisions "are made during the early phases of the innovation process".
- **Bridge to software:** Ulrich explicitly allows "the inclusion of a software subroutine in the definition of a component" (p. 421).
- Typology: **modular vs integral** architectures.
- Source: K. Ulrich, "The role of product architecture in the manufacturing firm", *Research Policy* 24(3):419-440, 1995. https://me.psu.edu/simpson/courses/me546/ulrich.RP95.prod-arch.pdf · MIT working-paper version: https://dspace.mit.edu/bitstream/handle/1721.1/48938/roleofproductarc00ulri.pdf (not opened) · RePEc record: https://ideas.repec.org/a/eee/respol/v24y1995i3p419-440.html

**Ulrich & Eppinger**, *Product Design and Development* (McGraw-Hill; the textbook chapter "Product Architecture"):
- Method [snippet only, via teaching slides; book text not read]:
  1. create a schematic;
  2. cluster its elements into chunks;
  3. make a rough geometric layout;
  4. identify fundamental and incidental interactions.
- Outcome: an approximate layout, descriptions of the major chunks, and the documented key interactions. It is done by a cross-functional team early, in concept and system-level design.
- Slides: https://www.slideshare.net/slideshow/10productarchitectureppt/254439000 [snippet]. **Mark the exact book wording as unverified.**

**Muller (University of South-Eastern Norway)** [read]:
- System-architect **deliverables**: "Customer and Life-Cycle Needs (what is needed) · System Specification (what will be realized) · Design Specification (how …) · Verification Specification · Verification Report · Feasibility Report · Roadmap".
- Primary **responsibilities**: "Balance", "Consistency across many organizational and design boundaries", "Fitting in stakeholder needs and system context, during the entire life cycle".
- **Secondary responsibilities owned by others**: business plan → business manager; schedule → project leader; market and saleability → marketing manager; detailed designs → engineers.
- "Systems designers are 'inward' focused, where system architects connect the outward and inward perspectives."
- On titles: "No single unified standardized definition is used across companies, domains, and geographies."
- Sources:
  - https://www.gaudisite.nl/ModuleRoleAndTaskPaper.pdf
  - https://www.gaudisite.nl/SystemsTitlesAndRolesPaper.pdf
  - Muller's "Architect as Content Leader" slides list a *product architect* alongside family, portfolio, subsystem and technical architects [snippet, not opened]: https://www.gaudisite.nl/ArchitectAsContentLeaderSlides.pdf

**Sense S — the software product, solution or system architect.**

**ISO/IEC/IEEE 42010:2022** distinguishes "the architecture of an entity of interest" from "an AD [architecture description] expressing that architecture" [snippet from the ISO scope; normative text paywalled]: https://www.iso.org/standard/74393.html · summary: https://quality.arc42.org/standards/iso-42010 [snippet].

**SAFe** [read; public summary only, the full article is behind login]:
- Solution Architect: "responsible for defining and communicating a shared technical and architectural vision for a Solution Train to help ensure the solution under development will be fit for its intended purpose." https://framework.scaledagile.com/solution-architect
- System Architect: the same, "for the solutions developed by an ART"; "defining enablers, participating in solution definition, outlining non-functional requirements (NFRs)"; "work closely with Product Management, the Release Train Engineer (RTE), and Business Owners." https://framework.scaledagile.com/system-architect

**UK Government Digital and Data framework (DDaT)** [read]:
- "A solution architect designs solutions for problems that affect the organisation … ensure a problem and the desired outcomes are properly defined" https://understand-digital-data-roles-skills.service.gov.uk/role/solution-architect/
- "A technical architect provides technical leadership and architectural design." https://understand-digital-data-roles-skills.service.gov.uk/role/technical-architect/
- **DDaT has no "product architect" role** (the role index lists 66 roles in 9 families; product architect is not one of them): https://understand-digital-data-roles-skills.service.gov.uk/

**Practitioner job-ladder use of "product architect" (a software solution architect scoped to one product line).** I found **no reliable source**. Search returned only SEO and vendor pages comparing solution, enterprise and technical architects (e.g. https://www.ardoq.com/knowledge-hub/solution-architect, vendor). **Weak; do not cite as a definition.**

**Adjacent: software product lines.** SEI (Clements and Northrop) defines a product line as "a set of software-intensive systems sharing a common, managed set of features … developed … from a common set of core assets" [snippet, SEI tutorial slides https://users.exa.unicen.edu.ar/catedras/escuelapav/cursos/slidesclements.pdf]. The SEI *Framework for Software Product Line Practice v5.0* (https://apps.dtic.mil/sti/trecms/pdf/AD1147162.pdf) could not be retrieved; DTIC returned HTML. **Unverified.** This is the closest software analogue to Ulrich's "variety / standardization" concerns, and it maps onto our seed → vertical seed → market product → client pack ladder.

**How the definitions differ**
| Axis | Sense U (Ulrich, Eppinger, Muller) | Sense S (SAFe, DDaT, ISO 42010) |
|---|---|---|
| Object | the *product*: functions → chunks/components, the interfaces between them, product family and variety | the *software system*: structure, technology, NFRs, runway |
| Core question | "Which modules does this product, and its variants, consist of, and where are the interfaces, so that change, variety and standardization are cheap?" | "How is the system built so that it meets quality attributes and stays evolvable?" |
| Typical deliverables | function structure or schematic; function→component map; interface list; modular/integral choice; product-family/variant plan; roadmap (Muller) | architecture description, views (C4), ADRs, NFRs, enablers |
| Counterparts | marketing (variety), manufacturing (standardization), PM (roadmap) | Product Management (SAFe), engineers, RTE |
| In our team | **NOBODY explicitly.** The pieces are in `vertical-seed.md` and the organ catalog, both architect-owned. | **`architect` already** ("Senior solution architect", architect.md frontmatter) |

**Conclusion.** A `product-architect` defined in Sense S would duplicate `architect`. **The only non-overlapping definition is Sense U**, translated to software: the *product's* functional structure, its allocation to organs, verticals, modules and packs, and its variety.

### B.2 `product-architect`: the full profile in Sense U, adapted to software
- **Responsibilities:**
  - Write the product's function structure: its jobs and capabilities.
  - Map each function to an existing organ, vertical module or seed capability, or flag it as new.
  - Declare the variant plan: which market products, client packs and tiers carry which functions.
  - Name interfaces at the capability level ("CRM lead → ERP customer").
  - Keep variety cheap (commonality vs variability).
  - Keep the product roadmap consistent across products (Muller's "consistency across boundaries", "fitting stakeholder needs").
- **Deliverables:**
  - function→organ allocation table;
  - variant/commonality matrix;
  - capability interface list;
  - product structure diagram (mermaid);
  - per-feature product spec (if it carries PM duties: see Part C);
  - roadmap entry.
- **Inputs:**
  - owner intent (via `noc-questionnaire`);
  - product catalog (`product-working-scope.md`, `02-LANDSCAPE.md`);
  - organ catalog (`noctus.dev.component_list`, `noctus.seed.search_capabilities`);
  - reverse-engineer studies;
  - product-designer discovery (JTBD);
  - measurement data.
- **Outputs:**
  - to `architect`: the structure, for the 4-question test and seams;
  - to `product-designer`: scope and placement per screen;
  - to the tech-lead: slices and acceptance.
- **Decision rights:**
  - Recommends only. The owner decides scope, variety and priority (Scrum: the PO "is one person, not a committee"; the owner is that person).
  - The architect decides seam, tenancy and data shape.
- **Methods:**
  - Ulrich modular/integral typology;
  - Ulrich-Eppinger schematic → cluster → interactions;
  - DSM (Eppinger) [snippet: unverified];
  - product-line commonality/variability (SEI) [unverified];
  - JTBD job map (already in design canon §2.2);
  - ISO/IEC 25010 quality characteristics as the vocabulary for "fit": nine characteristics incl. Functional Suitability and Interaction Capability [read, arc42 summary: https://quality.arc42.org/standards/iso-25010; ISO page 403].
- **Quality bar / failure modes:**
  - Integral-by-accident: one function smeared over many organs, so every change touches N products. This maps to our replication-to-seed slip.
  - Variety bought with forks (`if org == …`) instead of packs.
  - Architecture decided late, after build (Ulrich: decided "during the early phases").
  - A titled-but-not-doing architect: Muller's "impostor" quadrant.
- **Lifecycle:**
  - **Leads** at policy/planning, feasibility and definition (Muller phases 0-1) and in variety/roadmap reviews.
  - **Consults** at system design (architect leads) and UI design (product-designer leads).
  - **Checks** after ship (does the shipped structure match the map?).
- **Interfaces:**
  - PM / owner: proposes, the owner decides.
  - Designer: provides scope and placement; receives JTBD.
  - Solution architect: hands over the function→organ map, receives the seam/ADR verdict.
  - Engineers: none directly, only through the tech-lead's briefs.
  - QA: acceptance criteria → test-engineer traceability (A.3).

### B.3 `product-engineer`

**Definitions by source:**
- **PostHog** [read, raw handbook markdown from https://github.com/PostHog/posthog.com/tree/master/contents/product-engineer; rendered at https://posthog.com/product-engineer/what-is-a-product-engineer and https://posthog.com/product-engineer/product-teams]:
  - "a product engineer is a software developer who: Builds products for *real users* · Writes full stack code · Cares deeply about solving the 'hair on fire' problems of their users".
  - "Product engineers talk to users. They decide what to build. They own pricing, revenue, and user experience. They support customers directly."
  - "At PostHog, PMs don't own the roadmap, make product decisions … product engineers manage product teams."
  - "Product managers are the team's compass": PMs own monthly growth reviews (revenue, product analytics, user feedback), "but it's the engineers (not the product managers) who are responsible and accountable for acting upon it."
- **Gergely Orosz, The Pragmatic Engineer** [read] https://blog.pragmaticengineer.com/the-product-minded-engineer/:
  - "Product-minded engineers are developers with lots of interest in the product itself."
  - Nine traits:
    1. proactive with product ideas/opinions;
    2. interest in the business, user behaviour and data;
    3. curiosity about "why?";
    4. strong communicators with non-engineers;
    5. **offering product/engineering trade-offs upfront**;
    6. **pragmatic handling of edge cases**;
    7. **quick product validation cycles**;
    8. **end-to-end product feature ownership**;
    9. product instincts through repeated learning cycles.
- **Others quoted inside the PostHog handbook** (second-hand quotes; originals not opened):
  - Lee Robinson: "work backwards from the desired product experience … broad understanding of the available tools and deep experience *applying* those tools".
  - incident.io: "Care more about outcomes and impact than the exact implementation".
- **O*NET** [read: search page]: no software "product engineer" occupation. The 686 fuzzy matches are mostly mechanical, manufacturing and automotive engineering (https://www.onetonline.org/find/result?s=product+engineer). In manufacturing, "product engineer" is a hardware/production-engineering title. **Weak source for a definition.** It is noted only to flag the ambiguity.

**How they differ:**
| Axis | PostHog | Orosz | Manufacturing title (O*NET hits) |
|---|---|---|---|
| Is it a role or a mindset? | a role with decision rights | a mindset inside a PM-led team | a job title |
| Who decides what to build | the engineer | the PM, challenged by the engineer | n/a |
| Scope | full stack plus support plus pricing | the feature end to end | the physical product through production |

**Responsibilities that are common across the reliable sources:**
- full-stack delivery of a user-facing feature;
- trade-offs offered up front;
- early validation;
- ownership of the outcome after ship;
- measurement.

**Failure modes:**
- shipping without measuring;
- gold-plating edge cases;
- "spec-taker" behaviour;
- and in PostHog's own framing, autonomy without the growth-review feedback loop ("autonomy can become directionless").

### B.4 Mapping onto our team

**`product-architect`: ADVISOR (read-only on code) plus spec author.** Same shape as product-designer. `Write` is limited to spec files in the scratchpad or `projects/<slug>/spec/`. Model opus.

- **Owns:**
  - the product structure: the function→organ/vertical/module allocation map per product;
  - the variant/commonality matrix (market products, client packs, tiers);
  - capability-level interfaces between products ("link, never merge" candidates are spotted here and handed to architect);
  - the per-feature product spec. If the owner chooses the "fold PM" option (Part C): problem, JTBD reference, user stories, testable acceptance criteria, success-metric target, scope-creep log, data categories touched (pointing at lgpd.md §3);
  - the product backlog/roadmap draft per product (via `noc-roadmap`);
  - the LANGUAGE trigger at spec time ("per-product X").
  - Proposed new KB: `KB § PATTERNS/product/product-architecture-canon.md`. Optional ownership transfer from architect: `product-working-scope.md`. That is an owner decision; `owns_kb` is exclusive.
- **Does not own:**
  - seams, tenancy, schema, event blocks, ADRs, fitness functions (`architect`);
  - the "Records" half of measurement-by-design (`architect`);
  - screens, flows, copy, a11y (`product-designer`);
  - the endpoint contract (tech-lead, `noc-contract-first`);
  - decomposition and dispatch (tech-lead);
  - any priority or scope *decision* (owner);
  - code, commits, merges.

**`product-engineer`: EXECUTOR** (worktree, commits its own branch only, `engineer-seed` protocol).

- **Owns:**
  - one **coupled, full-stack product slice** end to end: backend plus frontend plus the test for each acceptance criterion plus instrumentation (measurement-by-design §2). This fits `orchestration-craft-canon.md` §3.4 decision-table row 4: "one coupled piece above the cutoff → one engineer, whole brief". Today such a piece is either split FE/BE with contract overhead, or inlined by the tech-lead.
  - a validated-mockup → working-on-real-data check (`noc-wiring-audit`);
  - **post-ship outcome check**: reads the metric named in the spec plus `latency_report`, and returns "target met / not met / inconclusive" with the query;
  - the Orosz habits as return legs: a `tradeoffs:` leg (cheaper option with similar value), an `edge-cases:` leg (handled / deliberately not handled and why), a `validated-with:` leg.
- **Does not own:**
  - deciding what to build. **This is an explicit divergence from PostHog:** the owner decides; the product-engineer proposes.
  - pricing or revenue (owner plus `accountant`);
  - customer support (no channel; never sends to customers, same as the ops-steward rule);
  - design (product-designer) and the contract (tech-lead);
  - specialist-depth work (OAuth/webhooks → integrations-engineer; LLM/evals → ai-engineer; heavy RLS/migrations → backend-engineer; toolkit → tooling-engineer);
  - merge, push, deploy.
- **Overlap risk:** high with `frontend-engineer`, `backend-engineer` and `engineer-seed`. Recommended gate: **pilot on 3 features** (pilot-first cadence) under `noc-learn-refine`. Compare cycle time, integration defects and outcome-check completion against a split FE/BE dispatch. If it does not win, FOLD the Orosz traits into `engineer-seed.md` as craft and drop the agent.

---

## Part C — other product professions

Existing agents: accountant, agents-security, ai-engineer, architect, backend-engineer, compliance-reviewer, devops-engineer, engineer-seed, frontend-engineer, integrations-engineer, legal-advisor, ops-steward, product-designer, reverse-engineer, security, skill-scout, test-engineer, tooling-engineer, plus the tech-lead (no file).

| Profession | One-line definition (source) | Overlap with our agents | Verdict |
|---|---|---|---|
| Product manager | "makes sure that their products provide value and achieve the right outcomes by balancing user and business needs … make decisions on priorities" (DDaT [read] /role/product-manager/). SVPG: problem discovery plus solution discovery for value and viability (https://www.svpg.com/a-fresh-definition-of-the-product-role/ [read]); PM owns value and viability risk, designer usability, engineering feasibility (https://svpg.com/product-risk-taxonomies [snippet]) | Decision half = owner. Spec half = no one (A.2). Discovery = product-designer. | **FOLD-INTO product-architect** (spec half). The decisions stay with the owner. Alternative if the owner wants product-architect kept strictly in Sense U: ADD `product-manager` as an advisor and keep product-architect narrow. |
| Product owner | "accountable for maximizing the value of the product … Product Backlog management"; "one person, not a committee" (Scrum Guide [read] https://scrumguides.org/scrum-guide.html). SAFe PO: team-level backlog "aligned with customer and stakeholder needs" (https://framework.scaledagile.com/product-owner [read]) | The owner is literally the PO | **SKIP.** An agent cannot be accountable; the backlog draft goes to product-architect. |
| Product operations | No single meaning; Cagan counts ≥6 definitions, criticises the process/PMO variant, prefers a "force multiplier" with quantitative insights, qualitative insights, and tools (https://www.svpg.com/product-ops-overview/ and https://www.svpg.com/process-people/ [snippet]) | Quant → product analyst; tools → tooling-engineer / ops-steward | **SKIP.** It is ill-defined at the source, and its useful pieces map elsewhere. |
| UX researcher | "plan, design and carry out research activities with users … informs policy, proposition, service, content and interaction design" (DDaT [read] /role/user-researcher/) | product-designer does discovery, but through the **owner interview**, which is a proxy, not users | **ADD-when-triggered** (rank 2): when real end users (client staff, e.g. corretores) become reachable for sessions. Until then FOLD-INTO product-designer. |
| Product / data / performance analyst | Performance analyst: "develop performance measurement frameworks – KPIs, goals, user needs and benefits – and analyse the performance of a service or product against these" (DDaT [read] /role/performance-analyst/). Data analyst: "collects, manages, explores and shares data to support organisational objectives" (/role/data-analyst/) | architect owns "data must exist" (measurement-by-design); accountant owns SaaS finance metrics; ops-steward owns platform health. **Nobody owns product-outcome analysis.** | **ADD** (rank 1). The owner rule of 2026-11-09 ("everything inside our products … must be measured … data-driven") makes data mandatory, but no one reads it. Advisor that writes read-only SQL; views are built by backend-engineer. It is also the PostHog "growth review" function. |
| Product marketing manager | Positioning and messaging, go-to-market, launches, sales enablement (Pragmatic Institute https://www.pragmaticinstitute.com/resources/articles/product/what-does-a-product-marketing-manager-do/ [snippet]) | Landing copy → product-designer (content); GTM → owner | **SKIP** (no GTM function in agent scope today) |
| Content designer | "make things easier for people to understand and use … from discovery … with user researchers, service designers and interaction designers" (DDaT [read] /role/content-designer/) | product-designer's description already says "content design", plus pt-BR UX writing | **FOLD-INTO product-designer** (already there) |
| Technical writer | "user-centred approach to making complicated technical concepts easier to understand for a specialist audience" (DDaT [read] /role/technical-writer/) | Docs are kept by the tech-lead under eight-way sync and kb_sync gates | **SKIP** as an agent. EXTRACT Diátaxis (A.3) into the doc-discipline family. |
| QA / quality engineer | QA test analyst: "interprets testing needs, creating and executing appropriate tests to ensure quality and alignment with requirements". Test engineer: "designs, builds, automates and executes … test suites … exploratory testing" (DDaT [read]) | test-engineer (harness) plus compliance-reviewer (policy/verdict) | **FOLD-INTO test-engineer.** Add acceptance-criteria traceability (A.3). Exploratory testing is a gap worth one rule. |
| Growth | Growth PM focuses on acquisition, onboarding, conversion, monetization and retention metrics; "growth is part of product work, but it is not about more features" (Reforge https://www.reforge.com/blog/product-specializations [snippet]) | Would sit on the analyst's metrics | **SKIP** for now. Revisit as an analyst lens. |
| Developer relations | Relationships with developers who drive technical choices; pillars: advocacy, marketing, enablement, community (https://developerrelations.com/guides/what-is-developer-relations/ [snippet]; community/sponsored source, weak) | None. We have no external developer platform. | **SKIP** |
| Customer success | Proactive, outcome-focused: onboarding, adoption, value realization, renewals (Gainsight https://www.gainsight.com/essential-guide/customer-success-management/ [snippet]; vendor, weak) | ops-steward is platform-facing and forbidden to send to customers | **ADD-when-triggered** (rank 3): advisor producing per-org adoption/health reports from telemetry, once paying client orgs reach a count the owner sets. Never contacts customers. |
| Release manager | "lead the change advisory board … risk assessment and scheduling of technical changes and releases. They own the configuration management database" (DDaT [read] /role/change-and-release-manager/) | devops-engineer owns `release-steward.md`; skill `noc-ship`; tool `noctus.dev.release` | **FOLD-INTO devops-engineer** (already there) |
| SRE | "what happens when you ask a software engineer to design an operations team"; responsible for "availability, latency, performance, efficiency, change management, monitoring, emergency response, and capacity planning" (Google SRE book [read] https://sre.google/sre-book/introduction/) | devops-engineer owns `sre-craft-canon.md` (SLOs, error budgets: devops-engineer.md:38, :66) | **FOLD-INTO devops-engineer** (already there) |

**Top 3 ADDs:**
1. **product-analyst** (ADD now). It closes the read side of measurement-by-design.
2. **ux-researcher** (ADD when real-user access exists; until then folded into product-designer).
3. **customer-success** (ADD when the client-count trigger is met; advisor only).

Product manager is ranked separately: FOLD-INTO product-architect is recommended, but it is an owner decision.

---

## Open questions for the owner
1. **product-architect scope.** (a) Recommended: Sense U product structure **plus** the PM spec half (stories, acceptance, success metric, scope log). (b) Sense U only, plus a separate `product-manager` advisor.
2. **product-engineer decision rights.** Confirm "proposes, never decides what to build". This diverges from PostHog, where engineers own the roadmap.
3. **product-engineer gate.** Accept a 3-feature pilot vs split FE/BE dispatch, with a fold-into-engineer-seed fallback?
4. **Ownership transfer.** Move `product-working-scope.md` from architect to product-architect, or keep it with architect?
5. **QA independence.** Adopt dev_team's "the author of a feature does not write its tests" (qa_engineer.md:5)? It conflicts with our red-first-by-implementer protocol.
6. **Triggers.** Name the triggers for ux-researcher (real-user access) and customer-success (number of paying client orgs).
7. **Drift fix.** Approve the fix to `dev_team/.../product_manager.md:13,:63`, whose five questions disagree with `lgpd.md` §3.

## Not verified / weak
- Ulrich & Eppinger book wording (slides only).
- ISO 42010 normative text (paywalled).
- SAFe full role articles (login).
- SEI product-line framework v5 (DTIC fetch failed).
- Muller's "product architect" slide (snippet).
- SVPG four-risk ownership (snippet).
- Reforge, Gainsight, developerrelations.com, Pragmatic Institute (snippet; vendor or community).
- No reliable source defines the job-ladder title "product architect" in software.
