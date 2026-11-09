# agent-templates-2026-11 — conversational base → SDR → Julia, as live-linked checkpoints the creator builds from

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: the owner judged the Criador de Agentes "too raw" (2026-11-09) and set the order: Julia validated and published as the first canon, then templates extracted from her, then the media-analyst built from them, then the creator as the multiplier.
> Decision: **ship the plan, the definitions and the creation gates today. The template build waits for Julia's publish (T1).**

## Origin

On 2026-11-09 the owner stopped the agent-creator build, saying the creator is "too raw". The new plan:
- Julia's validated, published version becomes the first canonical reference.
- From her we extract three layers:
  - a BASE that is a fully functional, securely gated **conversational** agent;
  - an SDR layer that consumes the base and adds atendimento + qualificação;
  - what is Julia/real-estate/org-only.
- Each layer is its own runnable agent with its own evals: a **checkpoint**.
- Children are **live-linked**, so a change to a layer flows into every child's draft.
- The creator starts from a checkpoint and never reasons about the base again.
- "Gerar com IA" becomes a chat with the creator.

The owner, verbatim:
- "the minimal agent i mean is a fully functional and securely gated CONVERSATIONAL agent … the conversation is also a basis to agents, sdr only consumes conversations and specs atendimentos e qualificacoes".
- "i dont want to reason on basis everytime, so we save templates (checkpoints) that get reused by the creator to create from a checked-point, not from scratch".
- "if i change the agent template, julia automatically gets those changes. but only run and goes live after evals, refinement, publishing".

## Definitions (owner-ratified 2026-11-09)

| Layer | Is | Owns | Never contains |
|---|---|---|---|
| **BASE** (conversational) | a fully functional, securely gated conversational agent with no domain | conversation conduct, persona slots, opt-out, handoff to a human, injection/jailbreak/exfiltration gates, anti-flattery ("discordar com respeito"), no-internals-narration, truthfulness (never claim a result before the tool returns it), LGPD floor | anything SDR (qualification, offers), any market, any org |
| **SDR** | BASE + atendimento + qualificação | qualification criteria slots, offer/visit/handoff flows, lead state, the SDR eval families | real estate, Vista, a specific org |
| **Julia** | SDR + real estate + the org | catalog search, ad-lead flow, visit-time proposal to the owner, the org's texts | — |
| **media-analyst** | BASE + media specs (not SDR) | media analysis | SDR content |

## Trigger conditions (the "when")

| # | Trigger | Detection signal | Why it tips the balance |
|---|---|---|---|
| T1 | **Julia published and validated** | `agents.agent_versions` row for agent e9cd6743 with `status='ativa'`, plus the owner's publish | the layers are extracted from her VALIDATED content, never from a moving draft |
| T2 | **BASE checkpoint passes its own evals** | readiness green on the BASE agent | SDR and the media-analyst build on it; a broken base would spread to every child |
| T3 | **SDR checkpoint passes its own evals** | readiness green on the SDR agent | the creator's SDR interview path needs a proven SDR layer |
| T4 | **media-analyst published** | readiness green + the owner's publish | the second creation run is what the creator learns from (Julia + media) |
| T5 | **piece taxonomy ratified by the owner** | owner message with the categories | the owner defines the categories first (decision 2026-11-09) |

**Today's status:** none fired. Julia is in refinement (handover noc-02 → noc-1, 2026-11-09). 072 (eval consolidation) is queued.

## Phase 1 — plan, definitions and creation gates (SHIPPED)

| # | Title | Files | Status | Verify recipe |
|---|---|---|---|---|
| P1.1 | This roadmap + the layer definitions | NEW `project-history/roadmaps/agent-templates-2026-11.md` | **shipped** | none needed (doc) |
| P1.2 | Structure↔constructor check extended to the whole creation path: Studio "Novo agente" route, draft and sections, `.md` mirror render and export, and the "Novo agente" form (TS) | `products/agents/backend/app/stores/structure_parity.py`, keeper | **in flight** (separate branch) | add a field to `StudioAgentRecord` on a scratch branch and see the keeper name every surface that doesn't carry it |
| P1.3 | "Gerar com IA" chat mockup (product-designer) | mockup artifact | **in flight** | the owner approves the mockup |

## Phase 2 — Julia to canon (DEFERRED: T1 closes it)

Owner order (handover 2026-11-09). Detail: `~/.noctusai/private/julia/HANDOVER-noc02-to-noc1-2026-11-09.md`.

| # | Title | Trigger | Verify recipe |
|---|---|---|---|
| P2.1 | 072 eval consolidation lands + deploys | noc-0 DEPLOYED | `GET …/evals/consolidacao` answers for Julia |
| P2.2 | Past-records analysis (no replay): normal/critical, streaks, failure patterns | — | the classification is written via `evals_consolidacao` and every case has a criticidade |
| P2.3 | Lessons + new flows into her prompt (ad lead: only-this vs other; hard-lead early handover with score; visit times to the owner) | SW 331→335 deployed (for the ad flow) | a dry-run of the content diff, then her draft hash moves |
| P2.4 | `depende_de` for her 88 cases | after P2.2 | a prompt change re-validates only the affected cases |
| P2.5 | Enrich the evals + refinement rounds (noc-iterate) | after P2.3 | both suites green on the same hash |
| P2.6 | Readiness → **the owner publishes** | — | T1 |

## Phase 3 — extraction into checkpoints (DEFERRED: fires on T1 + T5)

| # | Title | Verify recipe |
|---|---|---|
| P3.1 | Tag every Julia piece (section, text, skill, spec, eval case) with the owner's taxonomy + its layer: BASE / SDR / Julia | every piece has a layer; no orphans |
| P3.2 | **Layer mechanism**: a child pins a parent layer version; compilation = parent pieces + child pieces (child override explicit and listed); a new parent version auto-updates every child's DRAFT, which moves its hash, so evals are required before publish (consolidation re-runs only the affected cases) | change one BASE piece → Julia's draft hash moves and readiness asks only for the affected cases; her published version is unchanged |
| P3.3 | BASE checkpoint agent: the conversational + gated pieces, a neutral fake context, its own evals | T2 |
| P3.4 | SDR checkpoint agent = BASE + atendimento/qualificação, no market | T3 |
| P3.5 | Julia re-expressed as SDR + her pieces, **byte-identical compiled prompt** to her published version | compiled hash equal before/after |

## Phase 4 — media-analyst (DEFERRED: fires on T2)

| # | Title | Verify recipe |
|---|---|---|
| P4.1 | media-analyst = BASE + media specs (kind dev-executor, DB-source, `.md` mirror) | readiness green; `agent_export` mirror matches |
| P4.2 | Log every step we had to INVENT (noc-iterate method trial). This is the creator's input. | trial ledger has the round log |
| P4.3 | Route IG analysis to it (skill noc-ig-analysis) and add a CLAUDE.md §2 line | an IG analysis runs through the agent |

## Phase 5 — the creator (DEFERRED: fires on T3 + T4)

| # | Title | Verify recipe |
|---|---|---|
| P5.1 | "Gerar com IA" = chat with the Criador. It interviews the user, the minimum context is lenient, it respects "stop and create now", and it starts from a checkpoint (BASE, or SDR when an SDR is asked for) | create a test agent via chat in ≤ N turns; its draft pins the right layer |
| P5.2 | SDR-oriented interview when the user wants an SDR; agent-oriented otherwise | eval cases for both paths |
| P5.3 | The creator's own evals (it is an agent like any other) | readiness green |

## Anti-goals

- ❌ Changing Julia's published behaviour during extraction. P3.5 requires a byte-identical compiled prompt.
- ❌ Writing conversation rules as SDR content. Conversation is BASE.
- ❌ A second piece↔eval mechanism. The layers reuse 072 (`partes`, `depende_de`, `criticidade`).
- ❌ Copy-at-creation templates. The owner chose live-linked layers.
- ❌ A base change going live by itself. Every child goes through evals → publish.
- ❌ Reusing `exemplar`/`referencia` as the layer mechanism. That seam is generator IMITATION (058) and stays, while layers are COMPOSITION (P3.2).

## Open questions

- **Q1**: the owner's taxonomy for pieces (T5).
- **Q2**: the merge rule when a child overrides a parent piece. Proposal: a child override is explicit, listed in readiness, and stops that piece's updates until removed.
- **Q3**: can a BASE change be expressed in a child's language/persona without a child edit? Answer at P3.2 against real pieces.
- **Q4**: the cost of one BASE change = N children × affected evals. Is a budget cap per base change needed?

## Decision log

- **2026-11-09**: creator build paused; Julia first (owner).
- **2026-11-09**: templates are runnable agents with evals, never on a channel (owner).
- **2026-11-09**: inheritance is live-linked; changes reach children's drafts and go live only via evals → publish (owner).
- **2026-11-09**: the owner defines the piece taxonomy first, changes allowed later (owner).
- **2026-11-09**: BASE = a fully functional, securely gated CONVERSATIONAL agent; SDR only consumes it (owner).
- **2026-11-09**: Julia ownership moved noc-02 → noc-1 (owner).

## Retrospective (filled at first trigger fire)

*To be filled when T1 fires.*

## Composes with

- `KB § PATTERNS/backend/structure-constructor-parity.md` — P1.2 extends it to the whole creation path.
- `KB § PATTERNS/backend/db-source-agent-mirror.md` — the media-analyst's DB-source + mirror.
- `KB § PATTERNS/backend/canonical-agent-template.md` — the must-haves the BASE checkpoint must satisfy.
- skill `noc-iterate` (queued, held for the owner's vetting) — refinement rounds on Julia and on each checkpoint.

## File trail

- This doc.
