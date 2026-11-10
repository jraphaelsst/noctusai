---
name: noc-council
description: Use to challenge a plan, decision, contract, agent definition, refine or product before it is locked — triggers "council", "convene the council", "run the council", "conselho", "llm council", "five lenses", "challenge this plan", "anti-sycophancy review", "chairman". Independent, blind council as background subagents (five lenses plus the stage's advisors), an Opus chair that dispositions every objection, every row written through noctus.dev.council_ledger, outcomes recorded later so the stage map is retuned from evidence.
version: 1.4.0
---

# noc-council — independent, blind, measured review

> **Opt-in pilot.** The council is an opt-in pilot (D13). A project may opt in to the full council at every stage; its rules (caps, budget, kill criterion, recorder, review date) live in that project's PROJECT.md (first: `project-history/assistant-chatbot/PROJECT.md`). Decisions D13/D31-D34: that file section 2.
>
> **Changelog.** 1.4.0 (2026-11-10): the first step names the gates it crosses (guardian council lesson). 1.3.0 (2026-11-09): stage-map legend, outsider column renamed `Ou`, pilot clause moved to PROJECT.md. 1.2.0 (2026-11-09, owner D33): the product-* advisors get seats: product-manager (PMg) M idealize, O contract + evaluate; product-architect (PAr) M idealize + phase0, O verify_seed; product-analyst (PAn) M evaluate, O iterate. 1.1.0: report splits metrics per mode. 1.0.0: first map.

The author of a plan leans toward agreeing with itself (sycophancy, self-enhancement bias). A
council gives separate contexts, different priors and domain evidence, then a chair that must
answer every objection. Depth: `KB § PATTERNS/common/council.md`. Ledger contract:
`project-history/assistant-chatbot/contracts/council-ledger.md`.

## Workflow

1. **Open the session.** `noctus.dev.council_ledger action=open_session` with stage, subject_kind,
   subject_ref, trigger, mode, seats (from the stage map below), project, and `product=<slug>`
   for market products (so `report product=<slug>` aggregates per product). Parallel seats may
   call `record_objection` concurrently; labels are assigned under a lock.
2. **Compose the blind brief.** Subject, constraints, evidence paths, the question to challenge.
   NEVER the author's recommendation or preferred option. Hash it (`brief_sha256`).
3. **Dispatch seats in parallel** (Agent tool, `run_in_background`): `subagent_type=councillor`
   once per lens (the lens name goes in the prompt, see Lenses) and each advisor by its own name
   (`architect`, `security`, ...). Same brief to all, plus the `session_id` and the seat string.
   Seats never see each other.
4. **Seats record themselves (neutral recorder).** Each seat calls `council_ledger
   action=record_objection` (session_id, seat, severity, claim <=3 sentences, model) for each point;
   the TOOL assigns the `anon_label` and returns only `{objection_id, status:"submitted"}`. The
   seat returns to the tech-lead ONLY `submitted <objection_id>[, ...]`, never the claim text. The
   tech-lead therefore never holds the label-to-seat mapping or the objection wording (owner
   decision 2026-11-09, blindness enforced by the tool). Until the verdict exists, every tool read
   that would expose a seat refuses or omits it (`report`, `status`, `full_view`).
5. **Dispatch `council-chair`** (Opus, background) with the `session_id`. It calls `action=blind_view`
   ({anon_label, severity, claim} only) and returns decision, biggest risk, first step, and a
   disposition (`accepted|rejected|deferred` + reason, `unique` flag) for EVERY label. The
   tech-lead records it via `action=record_verdict` (`chair_kind=chair_agent`), passing the
   dispositions keyed by `anon_label` (the tool translates them to objection ids). Only after that
   may it read the full view (`action=full_view`, seats revealed).
6. **Surface.** The tech-lead receives the chair report and ratifies or overrules
   (`action=record_event` `ratified|overruled`); owner-gated decisions go to the owner with the
   chair report attached. The council informs; it never decides prod exposure.
7. **Later: outcomes.** At wrap-up, post-deploy or on an incident/revert, record per objection
   `outcome` = `vindicated|refuted|untested` with `evidence_kind` + `evidence_ref`
   (`action=record_event event_kind=outcome`). `action=report` computes the metrics (split per mode; only subagents/api are independent and drive retune, single_chat is not).
8. **Retune.** The report's retune signal PROPOSES stage-map changes (M to O or O to M). The owner
   ratifies; this skill never edits the map by itself.

## Stage map (owner-approved matrix)

Seats = the lens columns plus every advisor marked M or O on the stage's row. **M** = must, **O** = optional on its stated condition, `-` = no. Lens columns: **C** contrarian, **F** first principles, **E** expansionist, **Ou** outsider, **X** executor. Advisor columns: Arch architect, Sec security, AgS agents-security, Cmp compliance-reviewer, Leg legal-advisor, Acc accountant, PD product-designer, PMg product-manager, PAr product-architect, PAn product-analyst. Each advisor runs as its own subagent with its own model. A row's cells never leave a column empty: `-` means no seat.

| Stage | C | F | E | Ou | X | Arch | Sec | AgS | Cmp | Leg | Acc | PD | PMg | PAr | PAn |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| idealize | M | M | M | M | O | O | - | O | - | O | O | M | M | M | - |
| phase0 | M | M | O | - | M | M | O | - | - | - | - | - | - | M | - |
| verify_seed | - | O | - | - | M | O | - | - | - | - | - | - | - | O | - |
| mockup | O | - | O | M | - | - | - | - | - | O | - | M | - | - | - |
| contract | M | O | - | - | M | M if stateful or cross-product, else O | M if auth, public route or new table tier, else O | O | - | O | O | - | O | - | - |
| build | - | - | - | - | M | O | O | O | - | - | - | - | - | - | - |
| wire | - | - | - | O | M | - | - | - | - | - | - | O | - | - | - |
| test_review | M | - | - | - | - | - | O | O | M | - | - | - | - | - | - |
| security_pass | - | - | - | - | - | - | M | M if LLM exposed | - | O | - | - | - | - | - |
| evaluate | O | - | M | M | - | - | - | - | - | - | - | M | O | - | M |
| ship | - | - | - | - | M | - | - | - | - | - | - | - | - | - | - |
| go_live | M | M | M | M | M | O | M | O | O | O | O | O | O | O | - |
| iterate | M | M | M | M | M | O (agent target: AgS; UI target: PD) | - | O | - | - | - | O | - | - | O |
| owner_question | M | M | M | M | M | - | - | - | - | - | - | - | - | - | - |

Stage rows in one line each: **idealize** classify the idea, market spec, interview · **phase0** seed-first check before design · **verify_seed** confirm the seed ships what the plan consumes · **mockup** clickable UI before code · **contract** FE/BE contract and tiers · **build** scaffold and build · **wire** connect UI to real data · **test_review** pre-merge test review · **security_pass** security review · **evaluate** UX and accessibility check · **ship** routine release · **go_live** first prod exposure (every lens, security M, other advisors O when relevant) · **iterate** step 4 refine of a live thing · **owner_question** high-stakes owner question.

**When the council meets.** On a trigger (`new_product`, `irreversible`, `trust_boundary`, `prod_exposure`, `money_legal_lgpd`, `seed_fanout`, `large_estimate`, `unrebutted_objection`), at the **M seats only** by default. A project may opt in to the full council at every stage; its caps, budget and review date live in its PROJECT.md. Elsewhere a single-chat pass is allowed and MUST be labelled "not independent" (`mode=single_chat`).

## Lenses (canonical definitions, until they move to the prompt registry)

Pass the lens in the dispatch prompt: "Lens: <name>". Each lens attacks the subject from one angle.

- **contrarian** — assume the plan fails; find the specific way, the hidden assumption, the
  strongest case for the option not chosen.
- **first principles** — strip the framing; what is the actual problem and the simplest thing that
  solves it? Which "requirements" are inherited habit?
- **expansionist** — what bigger or adjacent opportunity is being missed? What will this be
  needed for in six months?
- **outsider** — a smart newcomer with no context: what is confusing, jargon-heavy, or would a
  buyer/user not understand?
- **executor** — who builds this Monday morning? What is underspecified, unordered, untestable,
  or impossible to roll back in one line?

## Guardrails
- Seats NEVER get the author's recommendation or each other's output; the chair gets the
  recommendation only if the brief says so.
- Single-chat fallback is allowed only where the stage map or triggers allow it, and is labelled.
- Every row goes through `noctus.dev.council_ledger`; never hand-edit ledger files, and never read
  `project-history/council/**` before the verdict. While a session has no verdict, the
  `council-read` PreToolUse guard flags (denies once enforcing) direct reads of that path; use
  `blind_view`/`status` via `council_ledger`. Seats report failures as error text only, never claim text.
- Cost: independent seats cost roughly 4-15x a single chat; spend them on the stage map, not by habit.
- Claude only for now; lens councillors Sonnet, advisors their own model, chair Opus.
- A lens that finds nothing says so; never invent an objection to look useful.
- **The first step names the gates it crosses.** Before ratifying, the tech-lead checks the chair's first step against the existing gates it would cross: the gate inventory (`KB § PATTERNS/common/gate-alignment-inventory.json`), the git hooks and the PreToolUse guards. Each one is named in the verdict as kept, changed or retired. Born 2026-11-10: guardian council 09340534's "pure-push enqueue" collided with the pre-push "main is sacred" hook, and only a peer noticed.

## In-app (future, not built here)
Lens and chair prompts become rows in the core prompt registry
(`noctusai_lib.integrations.prompt_registry`, edited on Studio "Agentes da plataforma"), but the
seats and the chair stay **Claude Code agents/subagents**. **Owner rule, 2026-11-10: councils are run
by agents and subagents, never by API/token/credit calls.** A dev-side council never uses `mode=api`.
An in-app council for a product's end users is a separate decision the owner has not taken.

## Depth
`KB § PATTERNS/common/council.md` · `project-history/assistant-chatbot/contracts/council-ledger.md`
· `noc-questionnaire` (runs this first on high-stakes questions) · agents `councillor`, `council-chair`.
