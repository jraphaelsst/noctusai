# Diretor de Edição — Reels from approved headline + roteiro — Project Document

> Living document. Written for a zero-context reader: everything needed to resume is here or in `CONTRACT.md` (same folder).
> Status keys: ✅ shipped · ⏳ in progress · 🔒 blocked on dependency · 🅿️ blocked on the owner.

- **Created:** 2026-11-27 · **Last updated:** 2026-11-27
- **Status:** Phase A (diagnosis + design) ✅ · Phase B (decision-free structure, Fakes only) ✅ on branch `worktree-agent-ad566a5fb3f8be7ea`, **not merged, not applied, not enqueued** · Phase C (activation) 🅿️ waits on owner decisions D1-D7.
- **Owner / stakeholders:** the owner (brief 2026-11-27) · tech-lead · Julia has priority (see §2).
- **Related:** agent `.claude/agents/diretor-de-edicao.md` · skills `.claude/skills/edicao-video-*` · KB `PATTERNS/media/video-edit-spec.md`, `PATTERNS/media/script-to-media-production.md` · `../core-studio-build/specs/criacao-pipeline-contract.md` · code `products/social-wiring/backend/app/modules/media_creation/direcao/` · migration `373_cs_direcao_producao.sql` (NOT applied).
- **Slug / location:** `diretor-edicao-reels`, `products/social-wiring/projects/` (single-product scope: the CoreStudio worker, routes, ledger and approvals it plugs into are social-wiring's).

---

## 1. Context & purpose

CoreStudio already turns an approved headline + roteiro into a narrated Reel through the route `reel_narrado` (tts → render_motion → mux), but (a) a human must click "iniciar" after the two approvals, and (b) every audiovisual decision (scene composition, the `papel-explainer` style, the render) is hard-wired into that one route. The owner wants the **Diretor de Edição** to be triggered by the approval itself, to orchestrate the Reel production, and to hand the result to the system's review and human approval. The **audiovisual storytelling approach is deliberately NOT decided** (scene composition and sequencing, settings, camera, transitions, asset use, narration↔scene↔graphics relationship, the generation / assembly / render mechanisms). So this project builds the **structure** such that those decisions slot in later without rebuilding the agent or the flow.

The win: approving the second of {headline, roteiro} causes exactly one production run (idempotent, measured, event-recorded); the run is a graph of named stages whose decisions sit behind four seams; the output lands in the existing Aprovação final stage; swapping a Fake for a Real adapter touches no stage, event or test of the flow.

## 2. Confirmed constraints (owner brief 2026-11-27 + standing rules)

- Build structure only; **no storytelling approach, no generator vendor, no render mechanism picked**. Anything with a live cost or external call stays Fake. Where contracts disagree with the desired behaviour: explain the gap, propose alternatives, never turn an assumption into a decision (§7).
- **Julia has priority.** Never touch Julia's content/files (`products/agents/backend/app/channels/*`, `studio/eval_driver_live.py`, the conformidade stores, her DB draft). No DB writes to any agent's content; no migration applied to prod; no publish, deploy, enqueue, release-steward request, prod eval run or paid model/generation call. If a resource/deploy/dependency conflict could hurt Julia, pause this work. (This branch touches only social-wiring backend + docs; the agents product is read-only here.)
- The brand's visual identity (Mônica, Gilson) does **not** define a Reel editing style; the Mônica experiment is a reference and a source of learnings, not the final process.
- Existing rules that bind every future implementation (already decided, encoded as guards): never publish; original is immutable; no new content (text on screen = transcript span or approved string); synthetic voice only under a signed consent term; measure then say you measured; approval is never inferred from silence (`diretor-de-edicao.md:18-28`).
- Owner decisions of 2026-11-19 stay binding (`criacao-pipeline-contract.md` §10): approval mandatory, no posting yet, quota US$15/org/month, narrated reels drawn by code (no photos, no paid image generation) — note the tension with an open generator decision in §6 (G3).

## 3. Design principles / seed-first analysis

| Need | Seed / existing | Decision |
|---|---|---|
| Job graph, lease/retry, ledger, quota, progress, mover | seed `domain.media_production` (`MediaGraphRunner`, `StepSpec`, `LedgerPort`…) | **reuse as-is**; stages are `StepSpec`s |
| Measured ledger | `cs_criacao_jobs` + RPC `cs_criacao_passo_registrar` (363) | reuse; nothing new |
| State + events in one tx | `cs_post_criacao_transicionar` (369), `cs_post_eventos` (364) | reuse; 373 adds two event names + one idempotent writer |
| Approvals | seed `domain.approvals` (`apr_events`), `headline_aprovacao`, `roteiro_aprovacao` | reuse; the trigger only READS them |
| Fake-or-refuse adapter factory | seed `integrations/fake_or_refuse.py` | reuse in `direcao/fabrica.py` |
| TTS / motion render | seed `integrations/tts`, `integrations/motion_render` (Fake+Real) | untouched: they are the `reel_narrado` implementation, one possible Real behind the seams |
| The four seams (style, planner, generator, assembler) | none | **product-level now** (`direcao/portas.py`), N=1 consumer and the shapes are exactly what the open decisions will fix; lift to `domain.media_production` when D2-D6 land and a second product needs them (recurrence rule). Putting unproven ports in the seed would freeze its API before the decisions. |

## 4. Scope

In: diagnosis, integration design, the trigger seam, the production-job skeleton (stages as data, outcome enum, events, ledger fields), the four ports + Fakes + fake-or-refuse factory, decision-free guards, tests, contract + this doc. Out: any Real adapter, activation of `reel_dirigido` (it is refused with `rota_nao_implementada` until activated), UI changes, publishing, the agent definition in the agents product.

### 4a. Dispatch routing

| Slice | Lens | Files | Done as |
|---|---|---|---|
| Phase A diagnosis + design | architect/product-engineer | this folder | this branch |
| Phase B structure | product-engineer | `media_creation/direcao/*`, `criacao_rotas.py`, 3 approval endpoints, `config.py`, migration 373, tests | this branch |
| Phase C activation (after D1-D7) | backend + ai + devops | see CONTRACT §8 | not dispatched |

Codification expectations: s1 only (this project's learnings are in §9/§11); s3 candidate once Phase C ships: a KB pattern "approval-triggered production" (the trigger/idempotency shape is reusable by the carousel and avatar routes). Routes-not-taken: §6 (alternatives).

## 5. Diagnosis — what exists, how it relates (complete / partial / missing)

Verified on `origin/dev` 4db36dc07 (2026-11-27), by reading code and running the new tests; file:line are in this checkout.

| # | Piece | State | Evidence / what is missing |
|---|---|---|---|
| 1 | Agent `diretor-de-edicao` (local Claude Code `.md`) | **partial** | `.claude/agents/diretor-de-edicao.md:1-72`. Full intake/preflight/route/plan-gate/sample/adjust flow for **footage** jobs and a one-paragraph no-footage mode (`:54`). Written to "move into the agents product later" (`:10`) but **not instantiated there**: no `diretor-de-edicao` row/definition exists in `products/agents` (grep: only `diretor-de-criacao`). Tools are Bash/Read/Write + transcription MCP: it needs a shell with ffmpeg, so it cannot run in the agents runtime as-is. Its flow is **interactive** (asks the user, waits for previews) — incompatible with an unattended approval trigger; the no-footage mode is the only part that applies. ElevenLabs tools not granted (`:68`). |
| 2 | Skills `edicao-video-*` (9) | **complete for footage, partial for no-footage** | `.claude/skills/edicao-video-*/SKILL.md` (20-30 lines each: preparo-de-midia, corte-e-legenda, legenda-por-palavra, inserts-e-broll, checagem-de-gancho, zona-segura, audio, escolha-de-estilo, referencia-para-preset). They are procedures a Claude session follows; none is executable by a worker. No skill covers scene planning for a no-footage reel (that is the open storytelling decision). `zona-segura` numbers are still `nao_verificado` (`video-edit-spec.md:137-141`). |
| 3 | KB `video-edit-spec.md` | **partial** | Schema, revisions, presets-as-data, defaults decided 2026-11-13 are solid (`:26-123`). Gaps: events in §4 are **proposals, never implemented** (`:89`); `cenas.trecho` is in **seconds** while `letreiros/insercoes` anchor by word id (`:26-75`) — inconsistent with the word-id-only rule of the no-footage path; presets (`:93`) have no storage/approval flow yet; `status: nao_testado` seeds only. |
| 4 | KB `script-to-media-production.md` | **partial (experimental)** | Pipeline table `:7-21`, retime `:23`, consent `:30`, checks `:37-44`, per-item measurement `:46`, craft lessons `:57`. Status banner: learned on ONE round, "a playbook, not a gate". Open items `:65-70`: voice-ID↔consent audit log, TTS adapter (now exists in seed), production scripts live in the client's private study folder. |
| 5 | CoreStudio criação contract | **complete as contract, partial in reality** | `.../core-studio-build/specs/criacao-pipeline-contract.md`. §1 says the system moves Roteiro→Criação when the human approves headline AND roteiro; **reality: it does not** (see row 6). §4 platform agent Diretor de Criação, §5 media worker, §10 owner decisions. |
| 6 | **Approval → trigger** | **missing** | `routers/esteira.py:294` (`aprovar_headline`), `:331` (`decidir_aprovacao`), `routers/roteiros.py:163` (`aprovar_roteiro`) only record the approval. The start is a separate human call `POST /posts/{id}/criacao/iniciar` (`esteira.py:381`) → `CriacaoMover.entrar_em_criacao` (`services/criacao_mover.py:156`) → `CriacaoService.enfileirar` (`services/criacao_service.py:176`). The gate itself exists and is correct: `esteira_service._pendencias` (`services/esteira_service.py:~375`) refuses unless `headline_aprovada` ∧ `roteiro_aprovado`. No approval event is consumed by anything. |
| 7 | Where the approvals are recorded | **complete** | Seed approvals organ: immutable `apr_events` (`submitted/approved/rejected`), subjects `("headline", id)` at versao 1 (`services/headline_aprovacao.py:21-27`) and `("roteiro", id)` at the roteiro's own `versao` (`services/roteiro_aprovacao.py:30-45`; an edit bumps the versao and invalidates the approval). The pt-BR event names `headline_aprovada` / `roteiro_aprovado` exist in the `cs_post_eventos` vocabulary (364) but are only the labels; the durable record is `apr_events`. |
| 8 | Criação state machine | **complete** | `criacao_estado.py:1-78` (11 states; `na_fila → gerando → aguardando_aprovacao_midia → midia_aprovada|midia_reprovada`), writer `cs_post_criacao_transicionar` (369) = state + event, one tx. Human final approval/rejection: `esteira.py:398` + `CriacaoMover.decidir_midia` (`:212`); a rejection re-queues only the rejected step. |
| 9 | Job graph + worker + ledger | **complete for `reel_narrado`** | Seed `domain/media_production/*` (runner `:1-278`); worker `criacao_worker.py:1-83`, **already declared in prod compose** (`deploy/fleet/docker-compose.prod.yml:308`, owner consent 2026-11-23); ledger `cs_criacao_jobs` (363) with `nao_medido` discipline; quota 366. Migrations 362-370 are in `migrations-applied.json:108-115` (⚠ `migrations/APPLIED.md:700` still says 362-366 "NOT APPLIED": drift, §8). |
| 10 | Production route today | **partial** | `criacao_rotas.py:44-52`: `reel_narrado` implemented; `carrossel`, `estatico`, `avatar`, `gravado` are **declared but not runnable** (`criacao_passos.py:32-39`: only tts/render_motion/mux have handlers → `rota_nao_implementada`). Route is chosen by `(formato, modo_producao)` but **no `modo_producao` column/field exists** — every reel resolves to `reel_narrado`. |
| 11 | Hard-wired decisions inside `reel_narrado` | **the seam to open** | style = constant `PRESET = "papel-explainer"` (`criacao_handlers.py:49`); scene planning = `montar_spec` paragraph grouping (`:116-141`); render = `RealMotionRenderer` (ImageMagick+ffmpeg). These are exactly the audiovisual decisions the owner left open. |
| 12 | Media/render organs | **partial** | Seed `integrations/tts` (Fake+Real ElevenLabs+factory, consent-gated), `integrations/motion_render` (Fake+Real, retime by word id, loudness check on the encoded mp4). No avatar/layout/captions adapters (`motion_render/__init__.py` NOC-REMEDIATE `media-adapters-phase2`). No generator for visuals beyond code-drawn shapes. |
| 13 | Publish organ (Reel) | **complete as a capability, deliberately unwired** | Seed `integrations/meta` `publish_instagram_reel` (Fake + Real, async 3-step poll, `oauth_adapter.py:819`), used by `routers/meta_content_router.py:109`. Out of scope: owner decision 2026-11-19 "no posting yet"; the Director never publishes. |
| 14 | Diretor de **Criação** (agents product) | **exists, separate, not touched** | DB platform agent `diretor-de-criacao` (`products/social-wiring/.../services/diretor_criacao.py:1-60`, `products/agents/backend/app/criacao/canais.py`), channel `app`, read-only tools to SW (`criacao/ferramentas.py`), got `escrita_humana` in de6ed1854. It **generates the headline/roteiro text**; it has no render tools and no relation to the Diretor de **Edição**. They must not be conflated: Criação = writing agent (agents runtime, conversational); Edição = production orchestrator (this project). The only coupling is data: the approved text. |
| 15 | Mônica experiment (6 reels + 3 carousels) | **learnings captured, scripts private** | Learnings: KB `script-to-media-production.md:37-64` and method trial `narrated-reel-pipeline-ivc` (verdict `refine`: word-match 6/6; LUFS pan-before-measure +3 LU; AAC true-peak headroom; transcription gate v1 false alarms 23 → opt-in; render speed 0.15-0.73x load-bound). The scripts (`produzir.py`, `lote.py`, `pecas.py`) live in the client's private study folder, **not in this checkout** → not verifiable here; the productionised part is the seed `motion_render` (`papel_engine.py`). Not the final process. |
| 16 | Review / human approval stage | **complete** | Stage `aprovacao_midia` ("Aprovação final"), `/posts/{id}/midia/aprovar|reprovar`, `cs_post_assets` registration in `mux` (`criacao_handlers.py:277-317`). The Director's output reuses it; nothing new needed. |
| 17 | Measurement-by-design | **partial** | Ledger fields exist (363); events for the criação steps exist (364). Missing for the Director: the trigger intent event, per-style / per-planner-version attribution (added: step `medicoes` carry `estilo_id`, `planejador`, `versao`), outcome enum. |

### 5.1 Contract gaps (existing docs vs the desired behaviour) — gap, alternatives, no decision

| Gap | Existing says | Desired | Options (owner decides) |
|---|---|---|---|
| G1 | criação contract §1: approval → system moves card | same | Already the intent; implemented now behind a switch (D1). |
| G2 | `diretor-de-edicao.md` flow is interactive (intake questions, preview approval, adjust loop) | unattended trigger | (a) run only the no-footage non-interactive subset, human review at Aprovação final only; (b) keep a mid-run human gate (plan/preview) as data (D7). |
| G3 | contract §10.9: "reels drawn by code, no photos, no paid image generation" | generator left open | Amend §10.9 only if the generator decision (D5) chooses otherwise; today the guard is the `GeradorDeMidia` seam + quota. |
| G4 | `video-edit-spec` `cenas.trecho` in seconds | word-id anchors only | Treat word ids as canonical for no-footage; keep seconds for footage jobs; reconcile in a spec v0.2 once D4 fixes the plan shape (the skeleton's `PlanoDeCenas` already anchors by word id and keeps `dados` opaque). |
| G5 | `video-edit-spec` §4 events are proposals | events must exist | The Director reuses 364's step events (`passo_*`, `criacao_concluida`) + 373's two; the edit-job events (`amostra_*`, `revisao_*`) bind only if/when D7 adds interactive gates. |
| G6 | Route chosen by `(formato, modo_producao)`, no `modo_producao` field | who picks Director vs narrated? | D2: per post (explicit `criacao_rota` — the only mechanism built), per marca/org setting, or by format. |

## 6. Design — recommended integration, alternatives, and where the Director runs

### 6.1 The approval → production seam (built)

`approval (apr_events) → direcao.gatilho.avaliar_post → cs_direcao_evento('direcao_solicitada', chave)  →  CriacaoService.enfileirar → job graph (7 stages) → criacao_concluida → aprovação final (human)`.
Idempotent by a DB-enforced key `direcao:<post>:h<headline>:r<roteiro>:v<versao>`; opt-in twice (route data `gatilho_automatico` + switch, default off); never fails the approval; refusals recorded as `direcao_recusada(codigo)`; a reconcile sweep heals missed paths/crashes. Detail: CONTRACT §3.

Alternatives for the trigger (recommendation: **A + sweep**):
| | How | Pros | Cons |
|---|---|---|---|
| **A (built)** | inline call after each approval endpoint (3 sites) + reconcile sweep | immediate, request-local, no polling, trivially testable | misses any new approval path until wired (the sweep covers it) |
| B | scheduler polls `apr_events` for new `approved` | one place, catches every path | polling cost (request-budget rule), latency, needs a cursor |
| C | DB trigger on `apr_events` inserting a job | atomic with the approval | business logic in SQL, hard to test/evolve, couples seed approvals organ to a product job type |

### 6.2 The production job: stages as data (built)

`recepcao → estilo → plano → midia → montagem → checagens → pacote`, each a seed `StepSpec` with explicit dependencies; four of them decide through ports (`estilo`→`ResolvedorDeEstilo`, `plano`→`PlanejadorDeCenas`, `midia`→`GeradorDeMidia`, `montagem`→`Montador`), the other three (`recepcao`, `checagens`, `pacote`) are deterministic guards. Outcome enum of a run (derived from the ledger): `entregue_para_revisao | falhou | cancelado | em_andamento`; the human outcome that follows is the existing `midia_aprovada | midia_reprovada`. Per-stage ledger row = wall/cpu time, vendor/model, units, `custo_usd` (or `nao_medido`), measurements incl. `estilo_id`/`planejador`/`versao` → approval rate per style/planner version is a join, not new instrumentation.

### 6.3 Where the Director runs — alternatives

| Option | What | Pros | Cons / risks |
|---|---|---|---|
| **R1 — CoreStudio job (worker `criacao`)** *(recommended executor)* | the 7 stages run in the existing separate worker process; the "judgement" is an adapter (`PlanejadorDeCenas`) | reuses trigger, ledger, quota, consent, progress, mover, human approval; deterministic, measurable, unattended; ffmpeg/ImageMagick already in the image; no Julia coupling | the planner's "intelligence" is an LLM call inside a step, not a conversational agent; no mid-run chat |
| R2 — agents product runtime (DB agent `diretor-de-edicao`) | instance per org, invoked per turn like Julia/Criação | versioned prompt, evals, Studio editing, white-label | runtime has no ffmpeg/Bash for agents on that path; **shares the runtime, evals, gate and DB with Julia → conflict risk while she finalises**; per-turn model has no job/lease semantics; paid evals. Fits the *planner* only (JSON out), never the render. |
| R3 — local Claude Code agent (today) | a human session runs the `.md` agent | zero build; best for studying and prototyping style | not triggerable by an approval; needs a human and a laptop; no ledger/quota unless hand-logged |
| **R1 + R2-planner (hybrid, the likely end state)** | worker executes and records; `PlanejadorDeCenas.Real` calls the agents-product agent for the scene plan (JSON per `video-edit-spec`) | judgement is a versioned, evaluable agent; execution stays deterministic; matches the spec principle "the agent emits a spec, a deterministic worker renders it" | needs the agent defined in agents (after Julia), a new channel/tool contract; cost per plan |

Recommendation: **R1 now (structure built for it), keep R2-as-planner as the option the `PlanejadorDeCenas` seam preserves, use R3 for studying styles.** Owner call (D3) — it also decides whether the `.md` agent is migrated to agents (Julia-dependent timing).

## 6.4 Human-review and approval gates

Built: the final gate only (existing Aprovação final: approve → Pronto; reject → back to Criação with a reason, only the rejected stage re-runs). A Fake/synthetic run can never reach it (`saida_sintetica`). Not built (D7, data-only extension point documented in CONTRACT §6): a mid-run gate before spend (approve the plan/style before generation), as the playbook's stage 5 ("owner previews the visuals while the voice question is open"). It needs a runner capability (`aguardando_humano` status) the seed does not have; recommended only if the owner wants it.

## 7. Open questions and owner decisions (each with options and a recommendation)

| ID | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | Trigger switch scope | (a) one global switch (today) · (b) per org (`org_settings`, like `chat_diretor_criacao`) · (c) per marca | (b) per org; today global default OFF is the safe state |
| D2 | Who selects the Director route for a post | (a) explicit per post (`criacao_rota`) · (b) per marca/org default · (c) by format only · (d) UI choice at card creation | (b) with (a) override; needs a `modo_producao`/route field and a UI |
| D3 | Where the Director runs | R1 / R2 / R3 / hybrid (§6.3) | R1 + planner via agents later; decide the agents part after Julia |
| D4 | The storytelling approach (planner) | to be defined with the owner: scene composition/sequencing, settings, camera, transitions, asset usage, narration↔scene↔graphics | out of scope by instruction; plug into `PlanejadorDeCenas`; the plan payload `dados` is opaque and versioned (`planejador`+`versao`) |
| D5 | Generator vendor/mechanism and its consent + quota | none chosen; today only code-drawn visuals + consented ElevenLabs voice exist | decide after D4; amend contract §10.9 if paid generation enters |
| D6 | Assembly/render mechanism | existing ImageMagick+ffmpeg engine (`papel_engine`) vs headless-browser overlay vs other (`video-edit-spec.md:127-135`, licence review for Remotion/HyperFrames) | decide after D4; legal-advisor review for any licensed stack |
| D7 | Mid-run human gate (plan/style preview before spend) | none (final gate only) · plan gate · plan + preview gates | none until D4 exists; add if the owner wants cost control |
| D8 | Style registry: where "estilos" live, who approves one, versioning, regression guard | `video-edit-spec.md` §5 describes presets-as-data; no storage exists | store as versioned rows in social-wiring, approved by the owner; the `ResolvedorDeEstilo` seam hides the choice |
| D9 | Carousel / avatar routes | stay declared-not-runnable | out of scope here; same trigger works once their steps exist |
| D10 | Prod gating of 373 + activation | owner-gated migration apply (predeploy_check), then switch on per org | not before Julia's finalisation window closes |

## 8. Dependencies, blockers, drift found

- 🔒 Phase C needs the owner's D1-D6 and the migration 373 applied through the sanctioned path (`predeploy_check` → `migrate_product`), **after** Julia's finalisation.
- Infrastructure already in prod: criação worker service (consent 2026-11-23), migrations 362-370 recorded applied.
- Drift found (fix-on-contact): `migrations/APPLIED.md:700` says 362-366 "NOT APPLIED" while `migrations-applied.json` records them applied → corrected in this branch (heading only; date of application not asserted). `video-edit-spec.md` §4 events are proposals (kept; G5).
- Julia: this branch changes no file under `products/agents`, does not touch her draft, evals or DB; it adds a default-off switch in social-wiring only. Running its tests uses the local hardware gate (`hw_admission`), no prod/eval/paid calls.

## 9. Success criteria

1. Approving the second of {headline, roteiro} on a `reel_dirigido` post with the switch on queues exactly one graph; repeating it queues nothing (tests `test_gatilho.py`).
2. A full run on Fakes concludes 7 ledger rows, measured or `nao_medido`, outcome `entregue_para_revisao`; a Fake cannot reach review (`test_grafo.py`).
3. A plan that adds text, an unknown anchor, or unmeasured/out-of-target measurements fails with a stable code (`test_validacao.py`).
4. Migration 373 applies twice on PGlite, the writer is idempotent per key, vocabulary only widens (`test_migration_cs_direcao.py`).
5. No existing test of the criação pipeline changes behaviour (switch off = no DB read on the approval path).

## 10. How to resume (copy-paste)

```bash
# from a worktree of this branch; W = the worktree root
cd $W/products/social-wiring/backend
PYTHONPATH=$W/seed/lib/backend:$W/seed/framework/backend:. \
  /Users/rapha/Documents/repository/NoctusAI/noctusai/mcp/noctusai/.venv/bin/python -m pytest \
  tests/modules/media_creation/direcao tests/test_migration_cs_direcao.py -q
# next number for any further migration: noctus.dev.next_migration_number product_slug=social-wiring
```
Next steps (in order): (1) owner answers D1-D4; (2) tech-lead reviews + enqueues the branch **after** Julia's window; (3) apply 373 through `predeploy_check` + `migrate_product`; (4) Phase C slices in CONTRACT §8 (activation: register the route's steps in `criacao_passos.PASSOS`, service builds the dirigido graph, deps wiring, first Real adapters one seam at a time); (5) turn the `.md` agent's no-footage mode into the planner definition (needs D3); (6) pilot on ONE marca, switch on for that org only.

## 11. Change log

- 2026-11-27 — Project opened from the owner brief; Phase A diagnosis + design written; Phase B structure built on Fakes (no Real adapter, nothing applied or enqueued). Decisions D1-D10 left open on purpose. Provisional calls made (flagged, reversible): the seams live in the product, not the seed (N=1); the plan validator requires word-id anchoring and no new text but NOT a scene partition (composition is open → coverage is measured); stage progress weights are provisional (`NOC-REMEDIATE[direcao-pesos-provisorios]`).
