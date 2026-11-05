# Reverse-engineering craft — the legal frame, the notations and the value lens of a study

> **Owner:** agent `reverse-engineer`. **Consumers:** skill `noc-reverse-engineer` (procedure), skill `noc-contract-first` (build stage), the owner deciding what to rebuild.
> **Status:** craft canon, 2026-11-05 (agent-refinement W1-S6). Sources verified 2026-11-05 (§11). Not legal advice: where §2 says "owner / legal", a lawyer decides.

**What this is.** The craft half of studying an external app: the legal and ethical frame, how evidence is kept, the standard notations a study emits so a build contract can cite it, how APIs are inferred, and how features are judged by the job they do for the customer.

**Why it exists.** `KB § PATTERNS/common/app-reverse-engineering.md` is the *technique* doc (stages, safety classes, browser tricks, gotchas) and stays the procedure's depth. The 2026-11-05 audit found what it lacks: no legal frame (the line between mapping behaviour and copying expression), free-form outputs that a contract cannot cite precisely, and no lens for *why* customers use a feature. It also found the agent file contradicting the technique doc on where study material goes; this doc and the agent now say the same thing.

**How to use it.** The technique doc's rules win wherever both speak (safety classes, own-ids-only, the two folder homes). Use this doc at S0 (§2 legal check), while writing S1/S3 outputs (§4 notations, §5 API inference), and at S4 (§6 value lens, §7 mapping). Copy the §8 checklist for the stage you are in.

## Contents
0. Standard term ↔ house term · 1. Purpose · 2. Legal and ethical frame · 3. Evidence discipline · 4. Output notations · 5. API discovery · 6. Feature-value lens · 7. Mapping onto noc · 8. Stage checklists · 9. Worked examples · 10. Anti-patterns · 11. Sources

## 0 · Standard term ↔ house term

| Standard term | House term |
|---|---|
| Black-box / clean-room study | read-only study from the owner's own account; our version re-authored from specs, never from their code |
| Safe vs unsafe HTTP method | safety class READ · SIDE-EFFECT-GET · WRITE · SEND (`app-reverse-engineering.md §2`) |
| Confidence level | evidence tag **C** (seen) · **I** (inferred) · **U** (unknown) |
| System context / container diagram (C4 L1–L2) | `analysis/c4-context.md` in the private study |
| Inferred API description (OpenAPI) | `analysis/openapi-inferred.yaml` with `x-safety-class` |
| Domain event timeline (EventStorming) | `specs/mechanisms.md` §events |
| Jobs-to-be-done | S4 JTBD table → seed organ → gap |
| Clean-room handoff | the build contract under `products/<slug>/projects/<module>-build/specs/` |
| Study vault | `~/Documents/repository/NoctusAI/_private-studies/<target>/` (outside every git tree) |

## 1 · Purpose — technique vs craft; when a study is worth it

A study is worth running when the owner is deciding whether and what to build, and a working app already embodies answers we would otherwise interview for (data model, states, plan gates, pricing unit). It is not worth running to copy a look, a prompt or a text. Every study ends in **our** decisions (`DECISIONS.md`), not in a replica.

## 2 · Legal and ethical frame

**S0 legal check (before S1, recorded in the private study's README).**

1. **Terms of service.** Read the target's ToS / acceptable-use terms for clauses on reverse engineering, scraping, automated access and benchmarking. Record the clause (quote + URL + date) in the private study. A clause that forbids what the stage needs ⇒ STOP and tell the owner; whether the clause binds and how far is a question for a lawyer (Wave-2 `legal-advisor`), never decided by the agent. We never bypass a technical measure (auth, CSP, rate limits, plan gates) whatever the ToS says.
2. **Software copyright — behaviour vs expression (Lei 9.609/1998).** Software is protected as a literary work (art. 2). Art. 6 III says it is **not** an infringement when a program resembles a pre-existing one "por força das características funcionais de sua aplicação", by following normative/technical rules, or because alternative forms of expression are limited. Art. 12 makes violating software copyright a crime; §1 raises the penalty for reproducing a program, in whole or in part, for commerce without authorisation.
   - **House reading:** mapping *what the app does* (routes, fields, states, rules, pricing unit) and building our own version of that functionality is the art. 6 III side. Copying *their expression* (code, bundled JS, prompts, UI copy, help texts, assets) into our product is the art. 12 side.
   - So: their prompts are captured only as `prompts/*-DRAFT.md` **study notes inside the private study**; our prompts are written from our JTBD statement and our specs, never by editing theirs. Config *values* that are product content (template lists, plan names) are recorded as facts about their product, not shipped as ours.
3. **Personal data (LGPD, Lei 13.709/2018).** A study processes personal data the moment a page shows a lead, patient, staff member or commenter (art. 5 I: "informação relacionada a pessoa natural identificada ou identificável").
   - Our processing is economic, so the private-use exclusion (art. 4 I, "fins exclusivamente particulares e não econômicos") does **not** apply.
   - Data being visible to the owner's account does not give *us* a purpose. Even public data must be processed "considerando a finalidade, a boa-fé e o interesse público" that justified making it available (art. 7 §3); the "manifestly public" consent waiver (art. 7 §4) does not reach a SaaS back-office, and new purposes need "propósitos legítimos e específicos" (art. 7 §7).
   - **Sensitive data** (art. 5 II — health, sex life, genetic/biometric, religion, politics, union, race) may be processed only in the art. 11 cases. A health-adjacent target (clinic, therapy) ⇒ **zero sample capture**: shapes and field names only.
   - **House rule:** summarise structure, never retain samples; reduce responses to shapes in the tab (`app-reverse-engineering.md §3.11`) before anything leaves it. Depth on categories, retention and the ANPD side: security-owned `KB § PATTERNS/security/lgpd.md`.
4. **Own account only, read only.** The owner's account, the owner's ids, READ-class calls (technique doc §2). A suspected tenant-isolation hole is reported as **U** and never tested.

**Anti-patterns.** "It's public in the app, so we can keep it." Pasting a vendor prompt into our product and "tweaking". Testing whether a guessed id returns someone else's row.

## 3 · Evidence discipline

- Tag every non-trivial claim **C** / **I** / **U** with its citation (screenshot `NN-<page>.jpg`, file, endpoint) — technique doc §5.
- Two concepts are the same only by definition **and** real data (memory `feedback-concepts-by-definition-not-name`).
- Give each artifact a confidence line at the top: `Confidence: C 62 · I 25 · U 13 (claims)`. A build contract cites only C claims as facts; I claims become interview questions.

## 4 · Output notations

Free prose stays for the narrative. Everything a contract will cite uses a standard notation, written in Markdown/Mermaid/YAML inside the private study.

| Output (stage) | Notation | Conventions |
|---|---|---|
| System + hosts (S1) | **C4 model** levels 1–2: system context, containers (C4's four levels are system, container, component, code; the model is notation-independent) | boxes = their system, embedded legacy apps (e.g. a Bubble.io iframe app), third-party services; arrows labelled with protocol and direction |
| Domain model (S1/S3) | **ERD** (Mermaid `erDiagram`) | entity names as *they* name them + our gloss; cardinalities only when C; PK/FK inferred from payload shapes marked I |
| Endpoints (S1/S2) | **OpenAPI 3.x** (`openapi-inferred.yaml`; spec latest 3.2.1) | one path per observed route; params learned from 400 bodies; enums harvested from responses; **`x-safety-class: READ\|SIDE-EFFECT-GET\|WRITE\|SEND`** and **`x-evidence: C\|I\|U`** on every operation (OpenAPI extension fields must begin with `x-`); no real values in examples |
| State machines (S3) | **state diagram** (Mermaid `stateDiagram-v2`) | states from enum values (C), transitions from UI actions/service calls (C/I), guards from FAQ text or validators |
| Mechanisms (S3) | **EventStorming** timeline (domain events, commands, policies, read models, external systems) | past-tense events (`QuestionnaireAnswered`), command → event → policy ("whenever X then Y"), hot spots for U |
| Synthesis (S4) | JTBD table + teardown scorecard (§6) + mapping table (§7) | — |

## 5 · API discovery and inference

1. **Bundle route mining first** (technique §3.1–3.4): service classes, zod schemas, enum objects and MSW mocks give shapes without calling anything.
2. **XHR capture** of READ calls only, on the owner's ids (S2 allowlist).
3. **Schema inference from N samples:** a field is `required` only if present in every sample; type from all samples (null-union when seen null); enums only from observed values (mark the list I — more may exist).
4. **Parameter learning:** one retry per 400, adding the parameter the validator named (technique §3.10).
5. **HAR rule.** A HAR export carries cookies, auth headers and full bodies; even the abandoned W3C HAR draft warns it "may contain privacy & security sensitive data". If the owner exports a HAR: it lands only in the private study's `captures/`; before any reading pass, strip `Cookie`, `Set-Cookie`, `Authorization`, CSRF/XSRF headers, `eyJ…` tokens and query-string secrets, and reduce bodies to shapes; delete the raw HAR after the redacted copy is verified. A HAR never reaches a git tree (keeper `check_no_vendor_study_in_git` covers the capture paths).

## 6 · Feature-value lens (S4)

**Jobs to be done (Christensen, Hall, Dillon, Duncan, HBR 2016).** Customers "hire" a product to make progress in a circumstance; a feature matters only through the job it serves. S4 writes one row per job, not per screen:

| Job statement ("When I…, I want to…, so I can…") | Their feature(s) (C) | Evidence of use (C/I) | Our seed organ / product | Gap |
|---|---|---|---|---|

**Teardown scorecard.** Pricing unit (seat, conversation, credit) · plan gates and what they lock · onboarding path · time-to-first-value · integrations · observed defects **as rebuild opportunities** (technique §3.15) · what we must *not* copy (expression, dark patterns).

**Rule.** The owner chooses jobs, then we choose screens. Options are presented as options (memory `feedback-interview-never-assume-specs`).

## 7 · Mapping onto noc

Each job row lands on: an existing seed organ (consume it; `KB § PATTERNS/architect/seed-organ-canonical-set.md`), an existing product, or a gap (a new organ or seam — architect decision). The mapping table is ours and goes to the repo (`DECISIONS.md` / the build contract), citing the private study by pointer `[private study: <name>]`, never by quote. Build only on "go all the way" via skill `noc-contract-first`.

## 8 · Stage checklists

```
S0 legal      - [ ] ToS clause recorded (quote+URL+date) - [ ] health/sensitive domain? ⇒ zero samples
              - [ ] private study folder created outside git - [ ] owner logged in (never type credentials)
S1 map        - [ ] C4 L1–L2 - [ ] routes from bundle, not menu - [ ] openapi-inferred.yaml with x-safety-class + x-evidence
              - [ ] ERD draft (C/I marked) - [ ] "never call" list
S2 data       - [ ] READ only, own ids only - [ ] shapes not samples - [ ] HAR (if any) redacted + raw deleted
S3 mechanisms - [ ] state diagrams - [ ] EventStorming timeline - [ ] their prompts as *-DRAFT.md (private only)
S4 synthesis  - [ ] JTBD table - [ ] teardown scorecard - [ ] mapping onto organs - [ ] DECISIONS.md (ours, in git)
Every stage   - [ ] confidence line - [ ] open questions for the owner - [ ] what the procedure got wrong (noc-learn-refine)
```

## 9 · Worked examples

### A · CoreStudio → social-wiring

- **S1 endpoints** become `_private-studies/core-studio/analysis/openapi-inferred.yaml`. `headlines/reprocess/{id}` is tagged `x-safety-class: SIDE-EFFECT-GET` (a GET that re-runs a job — the technique doc §2 example) and goes on the "never call" list.
- **What lands in git:** only our derived specs under `products/social-wiring/projects/core-studio-build/` (e.g. `specs/geracao-contract.md`, `specs/pesquisa-contract.md`, `DECISIONS.md`), citing the private study by pointer.
- **Prompts:** their headline prompts stay `prompts/*-DRAFT.md` in the private study. Our generation prompt is authored from the job statement — "When I publish a post, I want headline variants that match my brand voice, so I can test hooks without writing each one" — and our own specs, not by editing their text (Lei 9.609 art. 6 III vs art. 12, §2).
- **Lesson carried:** guessed ids returned other customers' rows (technique doc "Why"); under §2 item 4 that is now a **U** finding reported to the owner, never a test.

### B · geizelima-clinica (single-file app, clinic)

- **S0:** a clinic ⇒ health-adjacent ⇒ patient names, answers and records are sensitive personal data (LGPD art. 5 II) ⇒ **zero sample capture**. The ERD records entity and field *shapes* only.
- **S1/S3:** the single-file branch (technique §3.12) and the content-as-code catalog (§3.14) produce an interaction-primitive taxonomy, expressed as an EventStorming timeline: `QuestionnaireStarted` → `QuestionnaireAnswered` → `ScoreComputed` → `ReportLinkSent`, with the policy "whenever a score is computed, send the report link".
- **S4:** JTBD rows map to the questionnaire / agents seed organs; the defects already observed (answers keyed by display text, no versioning, results travelling only in links) go into the teardown scorecard as rebuild opportunities, not as features to copy.

## 10 · Anti-patterns

- **Committing redacted vendor captures** "because they are redacted" — vendor material never reaches git, redacted or not (owner decision 2026-10-19; keeper `check_no_vendor_study_in_git`).
- **Copying prompts or copy verbatim into our product.**
- **Testing tenant isolation** with a guessed id.
- **Menu-only route discovery** (misses gated routes).
- **Free-prose endpoint lists** that a contract cannot cite; OpenAPI without `x-safety-class`.
- **Screen-first synthesis** (cloning screens instead of serving jobs).
- **Keeping sample records "for realism"**, worst of all in a health domain.

## 11 · Sources

| Title | URL | Supports | Accessed |
|---|---|---|---|
| Lei 9.609/1998 (Lei do Software), Planalto | https://www.planalto.gov.br/ccivil_03/leis/l9609.htm | §2 art. 2, art. 6 I–IV (III functional similarity), art. 12 caput + §1 | 2026-11-05 |
| Lei 13.709/2018 (LGPD), Planalto | https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm | §2 arts. 4 I, 5 I–II, 7 §§3, 4, 7, 11 | 2026-11-05 |
| C4 model | https://c4model.com/ | §4 four levels; notation-independent | 2026-11-05 |
| OpenAPI Specification (latest, v3.2.1) | https://spec.openapis.org/oas/latest.html | §4 specification extensions must begin with `x-` | 2026-11-05 |
| EventStorming | https://www.eventstorming.com/ | §4 workshop format for exploring complex business domains (Brandolini, author of the book) | 2026-11-05 |
| W3C HAR draft (abandoned, "DO NOT USE") | https://webperfwg.org/specs/HAR/Overview.html | §5 HAR "may contain privacy & security sensitive data" | 2026-11-05 |
| Christensen, Hall, Dillon, Duncan — Know Your Customers' "Jobs to Be Done" (HBR, 2016-09) | https://hbr.org/2016/09/know-your-customers-jobs-to-be-done | §6 JTBD (authors + premise confirmed; article body paywalled — the "hire a product" framing is the article's well-known thesis, re-read before quoting) | 2026-11-05 |

Open (not verified, do not cite as law yet): whether circumvention of technical protection measures is separately sanctioned in Brazilian copyright law (Lei 9.610/1998) — the house rule "no bypass" stands on its own.
