---
name: noc-council
description: Use to challenge a plan, decision, contract, agent definition, refine or product before it is locked — triggers "council", "convene the council", "run the council", "conselho", "llm council", "five lenses", "challenge this plan", "anti-sycophancy review", "chairman". Independent, blind council as background subagents (five lenses plus the stage's advisors), an Opus chair that dispositions every objection, every row written through noctus.dev.council_ledger, outcomes recorded later so the stage map is retuned from evidence.
version: 1.0.0
---

# noc-council — independent, blind, measured review

The author of a plan leans toward agreeing with itself (sycophancy, self-enhancement bias). A
council gives separate contexts, different priors and domain evidence, then a chair that must
answer every objection. Depth: `KB § PATTERNS/common/council.md`. Ledger contract:
`project-history/assistant-chatbot/contracts/council-ledger.md`.

## Workflow

1. **Open the session.** `noctus.dev.council_ledger action=open_session` with stage, subject_kind,
   subject_ref, trigger, mode, seats (from the stage map below), project.
2. **Compose the blind brief.** Subject, constraints, evidence paths, the question to challenge.
   NEVER the author's recommendation or preferred option. Hash it (`brief_sha256`).
3. **Dispatch seats in parallel** (Agent tool, `run_in_background`): `subagent_type=councillor`
   once per lens (the lens name goes in the prompt, see Lenses) and each advisor by its own name
   (`architect`, `security`, ...). Same brief to all. Seats never see each other.
4. **Collect and anonymise.** Each seat returns objections (claim in 3 sentences max, severity
   `blocker|major|minor|note`). Record each via `action=record_objection` with an `anon_label`
   (A, B, C, ...); the chair sees labels, never seat names.
5. **Dispatch `council-chair`** (Opus, background) with the anonymised objections. It returns
   decision, biggest risk, first step, and a disposition (`accepted|rejected|deferred` + reason,
   `unique` flag) for EVERY objection. Record via `action=record_verdict` (`chair_kind=chair_agent`).
6. **Surface.** The tech-lead receives the chair report and ratifies or overrules
   (`action=record_event` `ratified|overruled`); owner-gated decisions go to the owner with the
   chair report attached. The council informs; it never decides prod exposure.
7. **Later: outcomes.** At wrap-up, post-deploy or on an incident/revert, record per objection
   `outcome` = `vindicated|refuted|untested` with `evidence_kind` + `evidence_ref`
   (`action=record_event event_kind=outcome`). `action=report` computes the metrics.
8. **Retune.** The report's retune signal PROPOSES stage-map changes (M to O or O to M). The owner
   ratifies; this skill never edits the map by itself.

## Stage map (owner-approved matrix)

Seats = all five lenses (C F E O X) plus every advisor marked M or O on the stage's row. M = must,
O = optional on its stated condition, `-` = no.

| Stage | C | F | E | O | X | Arch | Sec | AgS | Cmp | Leg | Acc | PD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| idealize (classify, market spec, interview) | M | M | M | M | O | O | - | O | - | O | O | M |
| phase0 / seed-first | M | M | O | - | M | M | O | - | - | - | - | - |
| verify_seed | - | O | - | - | M | O | - | - | - | - | - | - |
| mockup | O | - | O | M | - | - | - | - | - | O | - | M |
| contract | M | O | - | - | M | M if stateful/cross-product else O | M if auth/public route/new table tier | O | - | O | O | - |
| build (scaffold + build) | - | - | - | - | M | O | O | O | - | - | - | - |
| wire | - | - | - | O | M | - | - | - | - | - | - | O |
| test_review (pre-merge) | M | - | - | - | - | - | O | O | M | - | - | - |
| security_pass | - | - | - | - | - | - | M | M if LLM exposed | - | O | - | - |
| evaluate (UX + a11y) | O | - | M | M | - | - | - | - | - | - | - | M |
| ship (routine) | - | - | - | - | M | - | - | - | - | - | - | - |
| go_live (first) | all lenses + every relevant advisor (full council) |
| iterate (step 4) | M | M | M | M | M | O by target (agent: AgS; UI: PD) | | | | | | |
| owner_question | M | M | M | M | M | - | - | - | - | - | - | - |

Columns: Arch architect, Sec security, AgS agents-security, Cmp compliance-reviewer, Leg
legal-advisor, Acc accountant, PD product-designer. Each advisor runs as its own subagent with its
own configured model.

**When the council meets.** Project `assistant-chatbot` (D13): the full council at EVERY stage.
Other runs: only on a trigger (`new_product`, `irreversible`, `trust_boundary`, `prod_exposure`,
`money_legal_lgpd`, `seed_fanout`, `large_estimate`, `unrebutted_objection`); elsewhere a
single-chat pass is allowed and MUST be labelled "not independent" (`mode=single_chat`).

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
- Every row goes through `noctus.dev.council_ledger`; never hand-edit ledger files.
- Cost: independent seats cost roughly 4-15x a single chat; spend them on the stage map, not by habit.
- Claude only for now; lens councillors Sonnet, advisors their own model, chair Opus.
- A lens that finds nothing says so; never invent an objection to look useful.

## In-app (future, not built here)
Lens and chair prompts become rows in the core prompt registry
(`noctusai_lib.integrations.prompt_registry`, edited on Studio "Agentes da plataforma"); the chair
is an Opus API call; the tech-lead that called the council tool ratifies or overrules. Until then
every seat is a Claude Code background subagent.

## Depth
`KB § PATTERNS/common/council.md` · `project-history/assistant-chatbot/contracts/council-ledger.md`
· `noc-questionnaire` (runs this first on high-stakes questions) · agents `councillor`, `council-chair`.
