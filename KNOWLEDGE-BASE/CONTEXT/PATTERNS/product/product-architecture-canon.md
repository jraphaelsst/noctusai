# Product architecture canon — the product architect's textbook, mapped onto this platform

**What it is.** Product architecture in the sense of Ulrich (1995): how a product's *functions* are allocated to *components*, and which *interfaces* sit between them, so that product change, product variety and component standardization are cheap. Translated here to the platform's own ladder (seed, vertical seed, market product, client) and written as the operating manual for the `product-architect` agent and for anyone reviewing "which product carries this function?".

**Why it exists.** Owner decision 2026-11-09, after the product-roles research (`project-history/assistant-chatbot/research/product-roles-research.md`, Part B.1-B.2). The word "architect" names two different jobs. The *software* sense (system structure, quality attributes, ADRs) is the `architect` agent's and a second agent there would duplicate it. The non-overlapping sense is the *product* sense: nobody owned the function-to-organ allocation per product, the variant matrix across market products, client packs and tiers, or the capability-level interfaces between products. The pieces existed (`vertical-seed.md`, the organ catalog) but were reached only through seam and placement questions, never as "what is this product made of and what does it share?".

**How to use it.** Read §1 (the term map) and §9 (checklist) for every product-structure question; open the other sections for their topic. The house mechanism wins over the general canon: where this doc and `KB § PATTERNS/architect/vertical-seed.md` disagree, the house pattern is the rule. This doc recommends; the owner decides scope, variety and priority.

---

## 1 · House term ↔ standard term

| House term | Standard term | Where the house version lives | Note |
|---|---|---|---|
| function structure of a product | Ulrich "arrangement of functional elements" | this doc §3 | the product's jobs and capabilities, before any module |
| organ / module / vertical capability | component; chunk (Ulrich-Eppinger) | `KB § 04-SHARED-LIBRARY.md` · `noctus.dev.component_list` · `noctus.seed.search_capabilities` | the "physical component" side of the mapping |
| function-to-organ allocation | Ulrich "mapping from functional elements to physical components" | §3 | the central deliverable |
| four layers (seed, vertical seed, market product, client) | product platform / product family hierarchy | `KB § PATTERNS/architect/vertical-seed.md` §1 | the family structure already exists; this doc adds the allocation and variety view |
| named seam | modular interface | `KB § PATTERNS/architect/vertical-seed.md` §2 | declared by the architect; product-architect names the capability that needs one |
| client extension pack, settings | planned variety (product line variability) | `vertical-seed.md` §3 | variety bought with packs and settings, never with forks |
| `if org == …` in shared code | variety bought with a fork | `KB § 03-SEED-ARCHITECTURE.md` § Named seams vs structural forks | the failure mode of §7 |
| product catalog (`ativo` + `deploy_scope`) | product portfolio inventory | `KB § PATTERNS/architect/product-working-scope.md` (product-manager-owned) | read before any allocation; this agent cites it, never edits it |
| replication-to-seed symmetry | commonality analysis | `KB § PATTERNS/architect/project-execution.md` | "per-product X" in a spec is the trigger |

---

## 2 · The two senses of "product architect"

**Sense U (engineering and management science).** Ulrich, "The role of product architecture in the manufacturing firm", *Research Policy* 24(3):419-440, 1995 (read, pages 419-421): "Product architecture is the scheme by which the function of a product is allocated to physical components", defined as "(1) the arrangement of *functional elements*; (2) the mapping from *functional elements* to *physical components*; (3) the specification of the *interfaces* among interacting physical components". The abstract ties it to five managerial areas: product change, product variety, component standardization, product performance, product development management. Ulrich allows a software subroutine to count as a component (p.421) and types architectures as modular or integral. Architectural decisions "are made during the early phases of the innovation process".

**Sense S (software).** SAFe's Solution Architect "defin[es] and communicat[es] a shared technical and architectural vision" (framework.scaledagile.com/solution-architect, public summary read); the UK DDaT framework's Solution Architect "designs solutions for problems that affect the organisation" and its role index has no "product architect" at all (understand-digital-data-roles-skills.service.gov.uk, read). ISO/IEC/IEEE 42010:2022 separates an architecture from its description (normative text paywalled; summary only).

**The house decision.** Sense S is `architect` (`.claude/agents/architect.md`). `product-architect` is Sense U only. No reliable source was found for a practitioner "product architect" job-ladder meaning; do not cite vendor pages as a definition.

Adjacent, unverified here: the SEI software-product-line framework (Clements and Northrop) is the closest software analogue of Ulrich's variety and standardization, and maps onto our four layers. The SEI framework text could not be retrieved (DTIC returned HTML); treat commonality/variability vocabulary as borrowed, not verified. Eppinger's method (schematic, cluster into chunks, rough layout, interactions) was read only through teaching slides; the exact book wording is unverified. Muller (gaudisite.nl, read) supplies the architect's deliverables (needs, system specification, design specification, verification, feasibility, roadmap) and the warning that titles are not standardized.

---

## 3 · The function-to-organ allocation (the central deliverable)

For one product, or one new feature across products, write a table with one row per FUNCTION (a job the product does, in the owner's words):

| Function | Needs (JTBD ref) | Allocated to | Layer | Status | Carried by (products, packs, tiers) | Notes |
|---|---|---|---|---|---|---|
| e.g. "register a lead" | job line | organ / seed capability / vertical module / new | L0-L3 | `exists` · `extend via seam` · `new` | | |

Rules:
1. **Search before you allocate.** `noctus.dev.component_list`, `noctus.dev.find_reusable_component`, `noctus.seed.search_capabilities`, `noctus.dev.kb_search`. A function that already has an organ is `exists`; a function the organ nearly covers is `extend via seam` (the architect declares the seam); only the rest is `new`.
2. **One function, one home.** A function allocated to two places is integral-by-accident (§7).
3. **Placement test.** Needed by 2+ families → L0; 2+ markets of this family → L1; one market → L2 behind an L1 seam; one client → L3 setting or pack. → `vertical-seed.md` §1.
4. **`new` at L1 or L0 is an architect hand-off**, with the evidence (which products need it). The product-architect does not design the seam.

## 4 · The variant and commonality matrix

Rows are functions, columns are market products, client packs and tiers. Each cell is `common` (same organ, same behaviour), `setting` (same organ, org setting differs), `pack` (client extension code), `absent`. The matrix answers: what do the products share, where do they differ, and is each difference bought the cheap way (setting, then pack, then dedicated instance last; `vertical-seed.md` §3-§4)?

A column that is mostly `pack` is a signal to lift (N=2 triage, N=3 formalize): the second client asking for a pack feature means a setting or seam, the second market asking for an L2 feature means L1. A cell that needs `if org == …` is a fork, never an answer.

## 5 · Capability-level interfaces between products

Name the interface at the capability level only: "CRM lead becomes ERP customer", not an endpoint. For each pair of products that exchange something: the capability, the direction, the owner of the source of truth, whether it is a link (reference by id) or a merge (shared table). **Link, never merge** is the default; a merge candidate is handed to the architect with the reason. The endpoint contract is the tech-lead's (`noc-contract-first`); tenancy and schema are the architect's.

## 6 · Product structure diagram and roadmap entry

A mermaid diagram of functions, the organs that carry them and the layers, plus a roadmap entry (through skill `noc-roadmap`) that keeps the product roadmap consistent across products (Muller: consistency across boundaries). The diagram and the matrix are the artefacts the owner reacts to; the owner decides scope, variety and priority.

## 7 · Failure modes

| Failure | Standard name | House symptom | Guard |
|---|---|---|---|
| One function smeared over many organs, every change touches N products | integral-by-accident | a spec that says "add this to ERP and PF and Therapy" | replication-to-seed symmetry: the LANGUAGE is the slip |
| Variety bought with forks | variety without planning | `if org == …` in shared code | settings, then packs, then instances |
| Structure decided after the build | late architecture (Ulrich: decided early) | an allocation table written from the finished code | the allocation precedes the slice; product-architect runs at policy, planning and feasibility |
| A titled-but-not-doing architect | Muller's "impostor" quadrant | a diagram nobody builds from | every allocation row has a status and a named hand-off |
| Capability interface turned into a merge | tight coupling | two products writing the same table | link by id; architect reviews any merge |

## 8 · Where it sits in the lifecycle

Leads at policy, planning, feasibility and definition, and in variety and roadmap reviews. Consults at system design (the `architect` leads) and UI design (the `product-designer` leads). Checks after ship: does the shipped structure match the map? Inputs: owner intent (via `noc-questionnaire`), the product catalog and `02-LANDSCAPE.md`, the organ catalog, reverse-engineer studies, the product-designer's JTBD, measurement data. Outputs: structure to `architect` (for the 4-question test and seams), scope and placement to `product-designer`, slices to the tech-lead.

## 9 · Checklist (copyable)

- [ ] Catalog read: which products are `ativo` and `deploy_scope` (product-working-scope), before any allocation.
- [ ] Every function has one home, a layer and a status; the search calls are cited.
- [ ] Variant matrix shows each difference as setting, then pack, never a fork.
- [ ] No "per-product X" language; if present, escalated to the architect.
- [ ] Capability interfaces named as link, with the source-of-truth owner.
- [ ] Hand-offs written: `new` at L0/L1 to architect, screens to product-designer, slices to the tech-lead.
- [ ] Every recommendation is labelled a recommendation; scope, variety and priority are the owner's.
- [ ] Sources cited, unverified items marked.

## Sources (read 2026-11-09 unless marked)

Ulrich 1995 (me.psu.edu/simpson/courses/me546/ulrich.RP95.prod-arch.pdf, read) · Muller, *Module Role and Task* and *Systems Titles and Roles* (gaudisite.nl, read) · SAFe Solution Architect and System Architect pages (public summary) · UK DDaT roles (read) · ISO 25010 summary (quality.arc42.org/standards/iso-25010, read; ISO page 403). **Unverified:** Ulrich and Eppinger book text (slides only), SEI Framework for Software Product Line Practice v5.0 (retrieval failed), DSM method, ISO/IEC/IEEE 42010 normative text (paywall).

## Composes with

`.claude/agents/product-architect.md` · agent `architect` (seams, tenancy, schema, ADRs; owns `product-working-scope.md` and `vertical-seed.md`) · agent `product-designer` · agent `product-manager` · `KB § PATTERNS/architect/vertical-seed.md` · `KB § PATTERNS/architect/product-working-scope.md` · `KB § PATTERNS/architect/architecture-craft-canon.md` · skills `noc-roadmap` · `noc-questionnaire` · `noc-organ-consume-check`.
