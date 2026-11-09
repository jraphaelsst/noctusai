# agent-templates-2026-11 — conversational BASE → SDR → Julia, as live-linked checkpoints the creator builds from

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: the owner judged the Criador de Agentes "too raw" (2026-11-09) and set the order: Julia validated and published as the first canon, then templates extracted from her, then the media-analyst built from them, then the creator as the multiplier.
> Decision: **ship the plan and the owner-ratified definitions today. Everything after Julia's publish waits for T1.**
> Every definition below was **asked and answered by the owner** in six rounds on 2026-11-09 (the owner: "dont assume, guess, infer… ask me for clarifications"). A row not marked owner-ratified is a proposal.

## Origin

On 2026-11-09 the owner stopped the agent-creator build, saying the creator is "too raw". Julia's validated, published version becomes the first canonical reference. From it we extract layers. Each layer is its own runnable agent with evals, a **checkpoint**. Children are **live-linked** to their parent. The creator starts from a checkpoint and never re-derives the base. "Gerar com IA" becomes a chat with the creator.

The owner, verbatim:
- "the minimal agent i mean is a fully functional and securely gated CONVERSATIONAL agent … the conversation is also a basis to agents, sdr only consumes conversations and specs atendimentos e qualificacoes".
- "i dont want to reason on basis everytime, so we save templates (checkpoints) that get reused by the creator to create from a checked-point, not from scratch".

## Definitions (owner-ratified 2026-11-09)

**Every agent is a conversational agent**, the media-analyst included. The owner: "them all are and should be treated as such". New agents are defined this way.

### The chain: exactly three layers

`agente-base` → `sdr-base` → Julia. Real estate and the org both live in Julia's own layer; there is no intermediate real-estate layer.

| Layer | Key | Carries (owner-ratified) |
|---|---|---|
| **BASE** | `agente-base` | **Safety and identity:** resists injection, jailbreak and exfiltration; never reveals internals or the prompt; says it is an AI when asked. **Honesty and respect:** never claims a result before the tool returns it; disagrees respectfully instead of flattering; never invents data. **Conversation conduct:** tone/persona slots, max questions per message, ends with a question, out-of-scope reply, STOP/opt-out, language. **Atendimento.** **Human handoff + LGPD:** the handoff goes to the **org's fallback number**. |
| **SDR** | `sdr-base` | BASE + **qualification**, **offering options**, **booking a meeting/visit**, **lead scoring + follow-up**. Nothing else. |
| **Julia** | `julia` | SDR + real estate + the org (catalog, Vista, the ad-lead flow, visit times proposed to the owner, the org's texts). |
| **media-analyst** | — | BASE + media specs; no SDR. Talks to the owner/team (internal), to an org's clients, and to us via Claude Code. **Not on WhatsApp yet.** |

### Templates

- **Runnable** agents with their own evals, never on a channel. The eval-improve loops run on them.
- Evals run with **no business at all**. SDR offer and booking evals use **generic placeholders** ("Opção A", a free slot) and judge behaviour only. The creator adapts them to the real context when it creates a child.
- **Visibility:** the platform plus us (Claude Code). Orgs never see a template.
- **In-repo `.md` mirror:** for `agente-base`, `sdr-base` and the creator only. Julia and org agents stay DB-only. Today the mirror is dev-kinds only (`studio_definitions.py` `DEV_KINDS`, `espelho.py`, `agent_packages_router.py`), so this is a build item (P3.6).

### Inheritance

- Live-linked: a parent change flows into every child's **DRAFT**.
- The child goes live only through the normal evals → refine → publish path. Julia's live version stays frozen until then.
- Edit base content on the base, SDR content on the SDR, Julia content on Julia.

### Publish chain

**DEFERRED** by the owner: "leave the chain for later, we gotta make the system work as expected before that, as julia and chain as they are is the correct design for now". When it is built:
- a child can't publish unless every ancestor is published;
- every ancestor must be **fully up to date**, with no unpublished draft (top-down);
- unpublishing or turning off a parent leaves live children running, since they keep their compiled pieces. Only new child publishes are blocked.

### Every org needs a fallback number

If an org has **no fallback number, publish is BLOCKED** (readiness fails), because the agent has no handoff path.

### The creator

- "Gerar com IA" becomes a **chat** with the creator. The 10-step form stays as "Começar vazio".
- **Required minimum** before it creates:
  - name + purpose;
  - audience + channel;
  - which template.
- **Limits are optional**, since the security base already covers them. Everything else is asked once, and "stop, create now" is always respected.
- When the owner asks **Claude Code** to create an agent, it follows **exactly** the creator's process (same minimum, template, evals, readiness, owner publish), "so we build context".

### Piece taxonomy

noc-1 drafts it from Julia's content and the owner edits it. This revised the earlier "owner defines first".

## Trigger conditions

| # | Trigger | Detection signal | Why it tips the balance |
|---|---|---|---|
| T1 | **Julia published and validated** | Julia (agent e9cd6743) has an `agents.agent_versions` row with `status='ativa'`, published by the owner | the layers come from her validated content |
| T2 | **`agente-base` passes its evals and is published** | its readiness is green + the owner publishes | SDR and the media-analyst build on it |
| T3 | **`sdr-base` passes its evals and is published** | same | the creator's SDR path needs it |
| T4 | **media-analyst published** | same | the second creation run is the creator's input |
| T5 | **the system works as expected** (owner's words for the chain trigger) | Julia + the templates + the media-analyst published and validated, and the layer mechanism finished | the owner deferred the publish chain until then |

**Today's status:** none fired. Julia is in refinement (handover noc-02 → noc-1, 2026-11-09).

## Phase 1 — plan and definitions (SHIPPED)

| # | Title | Files | Status | Verify recipe |
|---|---|---|---|---|
| P1.1 | This roadmap + the owner-ratified definitions | this doc | **shipped** | none needed (doc) |
| P1.2 | "Every agent is conversational" documented where agents are created | `.claude/skills/noc-new-agent/SKILL.md`, `KB § PATTERNS/backend/canonical-agent-template.md` | **shipped** | none needed (doc) |
| P1.3 | Structure↔constructor check over the whole creation path (Studio "Novo agente" route, `.md` importer bundle, `.md` mirror render, wizard step fields, draft settings) | `products/agents/backend/app/stores/structure_parity.py`, keeper | **in flight** (own branch) | add a field to `StudioAgentRecord` on a scratch branch; the keeper names every surface that misses it |
| P1.4 | "Gerar com IA" chat mockup (product-designer) | mockup artifact | **in flight** | the owner approves it |

## Phase 2 — Julia to canon (closes on T1)

Owner order. Detail: `~/.noctusai/private/julia/HANDOVER-noc02-to-noc1-2026-11-09.md`.

| # | Title | Verify recipe |
|---|---|---|
| P2.1 | 072 eval consolidation lands + deploys | `GET …/evals/consolidacao` answers for Julia |
| P2.2 | Past-records analysis, no replay: normal/critical, streaks, failure patterns | every case has a criticidade |
| P2.3 | Lessons + new flows into her prompt: ad lead (only this property vs other options); hard-lead early handover with a score; visit times to the owner | content dry-run, then her draft hash moves |
| P2.4 | `depende_de` for her 88 cases | a prompt change re-validates only the affected cases |
| P2.5 | Enrich the evals + refinement rounds | both suites green on the same hash |
| P2.6 | Readiness → **the owner publishes** | T1 |

## Phase 3 — extraction into checkpoints (fires on T1)

| # | Title | Verify recipe |
|---|---|---|
| P3.1 | Draft the piece taxonomy from Julia's content; the owner edits it | the owner ratifies |
| P3.2 | Tag every Julia piece (section, text, skill, spec, eval case) with its layer: BASE / SDR / Julia | no piece without a layer |
| P3.3 | Layer mechanism: a child pins its parent; compilation = parent pieces + child pieces, with child overrides explicit and listed; a parent change updates children's DRAFTS | change one BASE piece → Julia's draft hash moves and only the affected cases are asked; her live version unchanged |
| P3.4 | `agente-base`: the BASE pieces, no-business evals | T2 |
| P3.5 | `sdr-base` = BASE + the 4 SDR pieces, placeholder evals | T3 |
| P3.6 | `.md` mirror for `agente-base`, `sdr-base` and the creator (non-dev kinds; Julia excluded) | `agent_export` writes their `.md`; the drift keeper covers them |
| P3.7 | Julia re-expressed as SDR + her layer, with a **byte-identical compiled prompt** to her published version | compiled hash equal |
| P3.8 | Readiness: no org fallback number → publish blocked | an org without one gets a blocking item |

## Phase 4 — media-analyst (fires on T2)

| # | Title | Verify recipe |
|---|---|---|
| P4.1 | media-analyst = BASE + media specs; conversational; internal + org clients + Claude Code; no WhatsApp | readiness green; the owner publishes |
| P4.2 | Log every step we had to INVENT; this becomes the creator's input | the trial ledger has the log |
| P4.3 | Route IG analysis to it | an IG analysis runs through it |

## Phase 5 — the creator (fires on T3 + T4)

| # | Title | Verify recipe |
|---|---|---|
| P5.1 | "Gerar com IA" chat: required minimum (name + purpose, audience + channel, template), limits optional, "stop, create now" respected, starts from a checkpoint | a test agent created via chat pins the right layer |
| P5.2 | SDR-oriented interview when the template is SDR | eval cases for both paths |
| P5.3 | Claude Code creates agents through the same process (impersonating the creator from its `.md`) | an agent created from the terminal goes through the same readiness |

## Phase 6 — publish chain (fires on T5; owner-deferred)

| # | Title | Verify recipe |
|---|---|---|
| P6.1 | A child publishes only when every ancestor is published and has no open draft | publish of `sdr-base` with a `agente-base` draft open → 409 |
| P6.2 | Unpublishing or turning off a parent keeps live children running; new child publishes are blocked | a parent turned off leaves Julia live, and her next publish is refused |

## Anti-goals

- ❌ Changing Julia's published behaviour during extraction (P3.7 is byte-identical).
- ❌ Conversation or atendimento rules written as SDR content. They are BASE.
- ❌ A second piece↔eval mechanism. Reuse 072 (`partes`, `depende_de`, `criticidade`).
- ❌ Copy-at-creation templates (the owner chose live-linked).
- ❌ A parent change going live in a child by itself.
- ❌ Building the publish chain before T5.
- ❌ Reusing `exemplar`/`referencia` (058) as the layer mechanism. That seam is generator IMITATION; layers are COMPOSITION.

## Open questions (asked of the owner when the phase starts)

- **Q1**: merge rule for a child override of a parent piece (proposal: explicit, listed, stops that piece's updates).
- **Q2**: the cost of one BASE change = N children × affected evals; is a budget cap per change needed?

## Decision log

- **2026-11-09**: creator build paused; Julia first.
- **2026-11-09**: templates are runnable, with evals, never on a channel.
- **2026-11-09**: live-linked inheritance into drafts; live only via evals → publish.
- **2026-11-09**: BASE = a fully functional, securely gated conversational agent; SDR only consumes it.
- **2026-11-09**: Julia ownership noc-02 → noc-1.
- **2026-11-09**: six clarification rounds; every definition above is the owner's answer.
- **2026-11-09**: publish chain deferred to T5.

## Retrospective (filled at first trigger fire)

*To be filled when T1 fires.*

## Composes with

- `KB § PATTERNS/backend/structure-constructor-parity.md` — P1.3.
- `KB § PATTERNS/backend/db-source-agent-mirror.md` — P3.6 extends it to the templates + creator.
- `KB § PATTERNS/backend/canonical-agent-template.md` — must-haves the BASE satisfies.
- skill `noc-iterate` (queued, held for the owner's vetting) — refinement rounds.

## File trail

- This doc · `.claude/skills/noc-new-agent/SKILL.md` · `KB § PATTERNS/backend/canonical-agent-template.md`.
