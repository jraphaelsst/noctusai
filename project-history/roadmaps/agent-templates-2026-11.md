# agent-templates-2026-11 — conversational BASE → SDR → Julia, as live-linked checkpoints the creator builds from

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: the owner judged the Criador de Agentes "too raw" (2026-11-09) and set the order: Julia validated and published as the first canon, then templates extracted from her, then the media-analyst built from them, then the creator as the multiplier.
> Decision (revised 2026-11-09 ~21:00Z, round 7): **build the layers NOW so nothing gets reworked.** Order: mechanism → `agente-base` (refined to the 95% target) → `sdr-base` (refined to the 95% target) → Julia layered on them, re-evaluated, then published. The owner publishes each one.
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
| **BASE** | `agente-base` | **Conversational + atendimento geral** (round 7): understand the request; ask questions to build context and clarify ideas; never assume or invent; always understand through questions. **Safety and identity:** resists injection, jailbreak and exfiltration; never reveals internals or the prompt; says it is an AI when asked. **Honesty and respect:** never claims a result before the tool returns it; disagrees respectfully instead of flattering; never invents data. **Conversation conduct:** tone/persona slots, max questions per message, ends with a question, out-of-scope reply, STOP/opt-out, language. **Atendimento.** **Human handoff + LGPD:** the handoff goes to the **org's fallback number**. |
| **SDR** | `sdr-base` | BASE + **qualification**, **offering options**, **booking a meeting/visit**, **lead scoring + follow-up**. Nothing else. |
| **Julia** | `julia` | SDR + real estate + the org (catalog, Vista, the ad-lead flow, visit times proposed to the owner, the org's texts). |
| **media-analyst** | — | BASE + media specs; no SDR. Talks to the owner/team (internal), to an org's clients, and to us via Claude Code. **Not on WhatsApp yet.** |

### Templates

- **Runnable** agents with their own evals, never on a channel. The eval-improve loops run on them.
- Evals run with **no business at all**. SDR offer and booking evals use **generic placeholders** ("Opção A", a free slot) and judge behaviour only. The creator adapts them to the real context when it creates a child.
- **Visibility:** the platform plus us (Claude Code). Orgs never see a template.
- **In-repo `.md` mirror:** for `agente-base`, `sdr-base` and the creator only. Julia and org agents stay DB-only. Today the mirror is dev-kinds only (`studio_definitions.py` `DEV_KINDS`, `espelho.py`, `agent_packages_router.py`), so this is a build item (P3.6).

### Inheritance (rounds 1, 8, 10)

- Per piece, keyed by `chave` (section, text, tool, decision, spec, skill).
- Same key in parent and child:
  - **prose section**: the child **appends** (the parent text stays, the child's follows);
  - **single-value piece** (text, tool row, spec, decision): the child **replaces** it, and it is listed as an override.
- Each agent has its **own settings** (model, effort, max turns, language, tool policy) and its own qualification standard. The creator sets them; the owner can change them.
- Each layer runs **its own eval cases only**. BASE cases run on `agente-base`.
- Live-linked: a parent change flows into every child's **DRAFT**.
- The child goes live only through the normal evals → refine → publish path. Julia's live version stays frozen until then.
- Edit base content on the base, SDR content on the SDR, Julia content on Julia.

### Publish: a child pins a published parent version (round 9)

A child's published version **pins its parent's published version**, so `agente-base` and `sdr-base` publish before Julia. The existing publish CAS already enforces correctness: the evaluated hash must equal the shipped hash, so a child can't ship parent content it wasn't evaluated on.

### Publish-chain extras

Still **DEFERRED** by the owner: "leave the chain for later, we gotta make the system work as expected before that, as julia and chain as they are is the correct design for now". When it is built:
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

## Eval-loop gate (round 10, owner spec)

The owner, verbatim: "running evals that dont make score better needs to get flagged … eval loops should be gated and stop whenever it feels like its 'good enough' … 2 calls not improving score stops and notifies why stopped mid-flight".

| # | Rule |
|---|---|
| G1 | **Target 95%** run score (owner, 2026-11-12; was 100%). **Floor 80%** (`publicacao_limiar`). Both shown on the loop card from the loop, never hard-coded. |
| G2 | Max rounds = the owner-editable platform loop config `rodadas_max` (2026-11-12); a loop may plan fewer, never more, and stops there. Checkpoints at 5, 10 and 15. |
| G3 | **Stop at the target (95%).** |
| G4 | **2 consecutive runs without a score improvement → STOP** and notify mid-flight with the reason (score series, what changed between runs, the cases still failing). Applies above or below the floor; the owner evaluates. |
| G5 | Every run that does not raise the score is **flagged** (an "overcall") and listed with its cost for watch-over. |
| G6 | A run on an unchanged content hash beyond the consolidation passes is refused as a re-run of unfixed issues. Fix first, then run. |
| G7 | Spend is tracked per round. The loop budget cap is **US$ 5** (owner, 2026-11-12; was US$20), from the loop config; reaching it stops everything for an owner decision. |

The gate is built into the app's eval runs (not only into noc-iterate) and probed across agents: the templates first, then Julia.

## The creator path (round 10)

1. `.claude/agents/agent-creator.md`: the process as a Claude Code agent. noc-1 impersonates it and refines it with every finding while building the templates.
2. Templates built and refined with it.
3. It refines Julia.
4. Review how it behaved end to end, refine it, codify it.
5. The in-app agent creator, refined through eval loops via the API (same process as Julia).
6. Wire it to "Novo agente": it takes over the chat room, or works from the form input. Doubts are listed and sent to the owner as an in-app notification + email with a report. Wiring does not depend on publishing; an unpublished creator simply receives no messages.

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
| P3.7 | Julia re-expressed as SDR + her layer, then re-evaluated on her own cases (byte-identical no longer required: round 7, layer first, then publish) | her suite at the 95% target on the layered hash |
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

- ❌ Evaluating a child with its ancestors' cases (each layer runs its own).
- ❌ Eval runs that don't raise the score without a flag (G5).
- ❌ Conversation or atendimento rules written as SDR content. They are BASE.
- ❌ A second piece↔eval mechanism. Reuse 072 (`partes`, `depende_de`, `criticidade`).
- ❌ Copy-at-creation templates (the owner chose live-linked).
- ❌ A parent change going live in a child by itself.
- ❌ Building the publish chain before T5.
- ❌ Reusing `exemplar`/`referencia` (058) as the layer mechanism. That seam is generator IMITATION; layers are COMPOSITION.

## Open questions (asked of the owner when the phase starts)

- **Q2**: the cost of one BASE change = N children × affected evals; is a budget cap per change needed?
- **Q3 (2026-11-12, "agents-camada-contradicao")**: the readiness overlap check (`camada_sobreposicao.py`) is lexical + key rules only. A child section that CONTRADICTS a parent with different words (assistente-pessoal's collisions scored 0.06–0.17, same band as healthy layers) needs an LLM semantic judge with its own evals, and the `TEMAS` synonym table should become a per-section declared topic (schema change). Fires when a second contradiction slips past readiness into an eval failure.
- **Q4 (2026-11-12)**: Julia's prod layer carries 4 near-verbatim restatements of agente-base/sdr-base sections (3 same-key, `reengajamento` vs `follow-up`). Removing them is a prompt-content change → do it inside Julia's next refinement loop (noc-iterate), one variable per round, not as a side edit.

## Decision log

- **2026-11-09**: creator build paused; Julia first.
- **2026-11-09**: templates are runnable, with evals, never on a channel.
- **2026-11-09**: live-linked inheritance into drafts; live only via evals → publish.
- **2026-11-09**: BASE = a fully functional, securely gated conversational agent; SDR only consumes it.
- **2026-11-09**: Julia ownership noc-02 → noc-1.
- **2026-11-09**: six clarification rounds; every definition above is the owner's answer.
- **2026-11-09**: publish chain deferred to T5.
- **2026-11-09 (rounds 7–10)**: build now; BASE includes atendimento geral; Julia layered before her publish; same key: prose appends, single values replace; own eval cases per layer; publish pins a published parent; own settings; target 100% / floor 80% with the eval-loop gate; creator path via `.claude/agents/agent-creator.md`; US$20 cap.

## Retrospective (filled at first trigger fire)

*To be filled when T1 fires.*

## Composes with

- `KB § PATTERNS/backend/structure-constructor-parity.md` — P1.3.
- `KB § PATTERNS/backend/db-source-agent-mirror.md` — P3.6 extends it to the templates + creator.
- `KB § PATTERNS/backend/canonical-agent-template.md` — must-haves the BASE satisfies.
- skill `noc-iterate` (queued, held for the owner's vetting) — refinement rounds.

## File trail

- This doc · `.claude/skills/noc-new-agent/SKILL.md` · `KB § PATTERNS/backend/canonical-agent-template.md`.
- **2026-11-12**: owner corrections — target 95% (was 100%), budget cap US$ 5 (was 20), max rounds as an owner-editable loop config the loop stops at. Refinement runs only inside a loop (skill `noc-iterate`).
