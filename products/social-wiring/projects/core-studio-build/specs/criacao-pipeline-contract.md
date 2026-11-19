# Criação pipeline + Diretor de Criação — contract (v1, 2026-11-19)

> Extends `estruturas-contract.md` §9/§16, `esteira-contract.md`, `CORESTUDIO-STRUCTURE.md` §3. Basis: origin/dev 2026-11-19 (architect review; file:line verified there). Owner decisions in §10 are binding.
>
> **Goal.** One headline or roteiro → final media on the Esteira, end to end, by construction: chat batching → counterpart generation → approval loop → card → automatic generation (visual + audio + merge) with measured cost/perf → final media approval. Cards move by themselves, live. No posting yet; approval is mandatory.

## 0 · Facts this rests on

- Stages are seed `pipeline` data: `ESTEIRA_PADRAO` (`mc/esteira_config.py:52-60`), roles (`:42-47`). Moves go through seed `move_card` (`seed/lib/backend/noctusai_lib/domain/pipeline/moves.py:27`) → `pipeline_movimentos`.
- Gate today: target ≥ role `gravacao` requires an approved roteiro (`esteira_service.py:353-378`); no headline approval.
- Realtime organ (Redis Streams + SSE): `RealtimeBus` (`seed/lib/backend/noctusai_lib/realtime/bus.py:60,154`), `JobProgress` (`job_progress.py:72-93`), `create_job_progress_router` (`:166`); FE `useJobProgress`/`useRealtimeStream` (`seed/lib/frontend/src/index.ts:252,268`). SW precedent: `routers/headlines.py:117`, `hooks/geracao/useHeadlines.ts:109-118`. The seed prefers SSE over Supabase Realtime (`realtime/__init__.py:1-4`).
- Jobs: seed `domain.jobs` worker (lease/heartbeat/retry); SW uses it (`services/geracao_jobs.py:214,235`).
- Cost precedent: `seed/.../domain/photo_editing/costs.py:1-20` (priced at call time, never a silent $0).
- Kanban FE organ: `seed/lib/frontend/src/components/kanban/KanbanBoard.tsx`.
- SW image already the seed MEDIA flavour with ffmpeg (`backend/Dockerfile:64-66`).
- `cs_posts.formato` ∈ `reel|carrossel|story|feed` (`352:66-69`); `cs_post_eventos` type CHECK last widened in `353:13-14`.
- No seed TTS/avatar adapter; ElevenLabs only as MCP (`mcp/elevenlabs/`, confirm-gated TTS, `consent_reference` required to clone).
- Julia's tool path: agents → SW `POST /api/julia/ferramentas/{nome}` (`routers/julia_ferramentas_router.py:3-11,86-103`), client `products/agents/backend/app/clients/social_wiring.py:94-176`. Agents turn API `POST /api/channels/turns` (`channels_router.py:264`) is not streaming.
- Chat context (`services/chat_contexto.py:388-424`): perfil, memórias, headline brains; roteiro brains, treinamentos, brand kit, virais, performance NOT wired; estruturas pool ≤12 in `auto` only.
- Pilot marca "Nós no Limiar": all 4 brains have empty `content`, never synthesized (Núcleo has 10 unsynthesized answers) — measured 2026-11-19.
- Migration 360 (RP-3 saga) is on dev, not applied in prod. Next free number at writing: 362.

## 1 · Stage model

| # | key | label | role |
|---|---|---|---|
| 1 | ideacao | Ideação | — |
| 2 | headline_roteiro | Roteiro | `roteiro` (new) |
| 3 | criacao | Criação | `criacao` (renames `gravacao`; alias kept one release) |
| 4 | edicao | Edição | `edicao` (new) |
| 5 | aprovacao_final | Aprovação final | `aprovacao_midia` (new) |
| 6 | pronto | Pronto | `pronto` (new) |
| 7 | postado | Postado | `postado` |
| 8 | bloqueado_cancelado | Bloqueado/cancelado | `cancelado` |

Routes are data (`mc/criacao_rotas.py`), keyed `(formato, modo_producao)`. Skipped stages are traversed with `motivo='rota:pulado'`.

| Route | Criação jobs | Edição | Final |
|---|---|---|---|
| `reel_narrado` | tts → render_motion → mux | skipped | aprovação final |
| `carrossel` | layout(LLM) → render_slides | skipped | aprovação final |
| `estatico` | layout(LLM) → render_estatico | skipped | aprovação final |
| `avatar` | tts (clone) → heygen_avatar (audio-driven) → poll | **legendas** (captions burn-in) | aprovação final |
| `gravado` | none (human upload) | edição | aprovação final |

Sub-state `cs_posts.criacao_estado` (projection, written in the same tx as its event): `aguardando_aprovacao → refinando → aprovado → na_fila → gerando → aguardando_edicao → aguardando_aprovacao_midia → midia_aprovada | midia_reprovada → (re-queue) | falhou(falha_codigo) | cancelado`.

Movers:
- Human approves headline AND roteiro (approval organ) → system moves Roteiro → Criação. Gate gains `headline_nao_aprovado`.
- Worker on terminal job → Edição (avatar) or Aprovação final.
- Human final approval → Pronto; rejection → back to Criação with reason; only the rejected step re-runs.
- System moves: `move_card(user_id=<cs_sistema actor>, motivo='auto:<evento>')`; every move writes `pipeline_movimentos` + `cs_post_eventos` in one tx.

## 2 · Data and events

Migrations (scaffold via `noctus.dev.scaffold_migration`; numbers from `next_migration_number`):
- **M-A** `cs_posts`: `criacao_estado`, `criacao_rota`, `falha_codigo`, `aprovado_em`, `cta_objetivo` enum (`alcance|salvamentos|conversa|seguidores|autoridade|reflexao|nenhum`), `cta_justificativa`, `fontes jsonb`. New stage defaults + roles CHECK; per-org rename "Gravação" → "Criação". `hashtags` CHECK `cardinality ≤ 5` (generator writes exactly 5). **No new link column** — the post link is the existing `permalink` (§10).
- **M-B** `cs_criacao_jobs`: one row per step of a post's job graph = the measured ledger (`script-to-media-production.md` §5): `id, org_id, post_id, rodada, passo, depende_de uuid[], status, job_id, iniciado_em, terminado_em, duracao_s, cpu_s, vendor, modelo, request_id, unidades jsonb {caracteres, audio_s, video_s, creditos_cobrados}, custo_usd, custo_brl, fx_status, velocidade_render_x, medicoes jsonb (LUFS, true peak, safe-zone), resultado, erro_codigo`. Unmeasured = `null` + `nao_medido`, never an estimate. Status advances only via definer RPC `cs_criacao_passo_registrar`. LLM legs reuse the seed cost recorder; vendor-unit rows (ElevenLabs/HeyGen credits) go into the same `cost_ledger` shape — extend the seed recorder if a non-token unit is missing.
- **M-C** widen `cs_post_eventos` type CHECK with §2.2 names.
- **M-D** `cs_consentimentos_voz` (org, marca, pessoa, vendor, voice_id, documento path + sha256, escopo, fase, valido_ate, revogado_em); append-only; LGPD flag (`noctus.dev.lgpd_flag`, biometric).
- **M-E** `cs_criacao_cotas` per org: `limite_usd_mes` (default **US$15**), editable in the UI by org admins; every change is an event.

### 2.2 Events (intent-named)
Roteiro: `opcoes_geradas`, `opcoes_selecionadas`, `contraparte_gerada`, `refinamento_pedido`, `headline_aprovada`, `roteiro_aprovado`, `publicacao_gerada`. Criação: `criacao_enfileirada`, `passo_iniciado`, `passo_concluido`, `passo_falhou`, `criacao_concluida`. Final: `midia_aprovada`, `midia_reprovada`. Opt-in only: `verificacao_transcricao_pedida/_concluida` (never gates a move). Moves: `card_movido_automaticamente`. Quota: `cota_alterada`, `cota_excedida`.

Metrics enabled: time to approval, refinement rounds/post, cost and wall time per format and step, render speed, rejection rate per step, CTA objective mix.

### 2.3 Card fields generated by construction
headline, roteiro, `legenda`, `hashtags[5]`, `primeiro_comentario`, `cta_objetivo` + `cta_justificativa`, `fontes`, `permalink` (empty; filled by hand now, by the IG automation later). The "Gerar legenda com IA" button is removed (`PublicacaoSecao.tsx:85-100`); fields stay editable.

## 3 · Live streaming
- Reuse `noctusai_lib.realtime`. No Supabase Realtime.
- Seed addition (L0, every kanban benefits): optional `publish` hook in `move_card` emitting `pipeline.card_moved` / `pipeline.card_state` on scope `pipeline:{org}:{pipeline}` (best-effort, after commit) + `create_pipeline_stream_router(cfg)` over `create_sse_router`.
- Per-job status line + bar: worker publishes `JobProgress` on `job_progress_scope(org, f"{post_id}:{rodada}")` with `stage=passo`, `progress` weighted by expected step duration, pt-BR `message` ("Sintetizando voz (2/3)"), `terminal`.
- FE: `useEsteiraStream(pipelineId)` (wraps `useRealtimeStream`, merges into the board cache, falls back to poll), `useCriacaoProgresso(postId)` (wraps `useJobProgress`), `CriacaoStatusLine` (text + bar) in the seed `KanbanCard` via a declared slot (add the slot to the organ if missing; no local fork).

## 4 · Diretor de Criação (white-label platform agent)
- Defined once in the agents product (`origem='plataforma'`, `instanciavel=true`, `owner_product='social-wiring'`, `papel='criacao'`) via Studio (`agents-unified/CONTRACT.md:135-150`); instance per org via `ensure_instancias`; versioned; eval gate before publish.
- Fleet prompt = general method only: option + counterpart generation, refinement loop, CTA by post objective (none mandatory; justify; "nenhum" commercial when the brand forbids it), humanized voice measured against the tenant's creator transcripts via a tool, source verification (cite only what a tool returned), exactly 5 hashtags, output contract parsed by `propostas.py`. No client names; evals cover a tenant with a 9-block method and one without.
- Tenant data (SW) holds the method (estruturas + a `metodo` brain), voice samples, CTAs (`perfil.ctas`), brand rules, research. The agent reads; never stores.
- Tools (agents → SW `POST /api/criacao/ferramentas/{nome}`, scope `social-wiring:criacao-tools`, issuer `agents`; generalize `julia_ferramentas_router` into a factory `make_agent_tools_router(scope, registry)`; reads only):
  `contexto_marca`, `cerebros`, `estruturas_buscar` (formato/objetivo/texto, ≤20, typed blocks incl. CTA), `estrutura_detalhe`, `pesquisas`, `virais`, `desempenho`, `voz_amostras` (transcript excerpts + measured wpm), `treinamentos`.
- Chat path: SW chat calls agents via seed `integrations/agents_channel` (`agent_key=diretor-de-criacao`); add `POST /api/channels/turns/stream` (SSE) in agents; until then a non-streaming turn with SW status frames. SW keeps parsing, multi-select and the saga as the only writer. `mc/prompts/*.py` agents become a strangler behind a per-org flag.
- Batching: `POST /chat/propostas/selecionar {ids[]}` claims N proposals; saga once per id (idempotent; 360 RPC locks per row) → N cards at `aguardando_aprovacao` → counterpart + `publicacao_gerada`.

## 5 · Media worker
- New seed domain `domain.media_production` (mirrors `photo_editing`): job-graph runner over seed jobs, per-step ledger callback, progress publishing, renderer ports. SW registers handlers (L2). Separate process (`worker criacao`, same image). ImageMagick + preset fonts added to the seed MEDIA base flavour.
- Adapters (Fake + Real + factory, seed `integrations/`):
  - `tts`: `synthesize(text, voice_id, model) -> {audio_path, timings, caracteres, creditos, request_id}`; ElevenLabs logic moves from `mcp/elevenlabs/` into the seed (the MCP becomes a thin shell). `clone_voice` refuses without a valid `cs_consentimentos_voz` row (seed port).
  - `avatar`: HeyGen `create_video(audio_url, avatar_id)` + `poll` as a `RescheduleLater` job. Audio = our ElevenLabs clone (§10).
  - `motion_render`: `papel-explainer v2` (ImageMagick + ffmpeg, word-id retime); productionize the validated scripts from the 2026-11-18/19 rounds.
  - `layout_render`: LLM layout JSON → seed `svg_render` → PNG (no image model).
  - `captions`: burn-in from TTS timings (or transcription for avatar).
- Limits: one render slot per worker process; per org 1 render + 2 vendor calls; global render concurrency via env, measured first. TTS/HeyGen pre-flight estimate checked against the org quota (M-E); over the quota → `falhou(cota)` visible on the card, never a silent skip.
- Transcription check: **opt-in only** (owner, 2026-11-19); loudness, sync keyframes, safe zone, hook frame and source hash stay automatic.

## 6 · Context wiring
1. One sectioned context assembler (same reads as the agent tools) replaces `chat_contexto.montar`: roteiro brains for all agents, brand kit, treinamentos, virais, performance, each with a char budget.
2. Estruturas: retrieval-ranked top-k over the 8,610 typed blocks (`integrations/retrieval`) instead of a fixed pool of 12; `codigos_permitidos` kept.
3. Brain synthesis job `cerebro.sintetizar(marca, tipo)` (on answer change / research approval / manual) → new version + `cerebro_sintetizado`. Diagnose first why the pilot marca's brains are empty (fix-on-contact).
4. Tenant onboarding "Carregar método do criador": upload course/transcripts/examples → extraction job → proposed `metodo` brain + estruturas → approval → synthesis. Pilot: load Mônica's method/context/CTAs/reference roteiros into the Nós no Limiar marca.

## 7 · Slices

| # | Slice | Agent | Class | Depends |
|---|---|---|---|---|
| S0 | This contract + playbook §4.2 edit (transcription opt-in) | tech-lead | C1 | — |
| S1 | Seed pipeline stream hook + router + FE base hook + KanbanCard status slot | backend+frontend | C1 | S0 |
| S2 | Seed `domain.media_production` runner + ledger port | backend | C1 | S0 |
| S3 | Seed adapters tts/avatar/motion_render/layout_render/captions; MEDIA base ImageMagick+fonts | integrations+devops | C1 | S2 |
| S4 | SW migrations M-A..M-E | backend | C1 | S0 |
| S5 | SW stage model, routes, gate, system mover, events | backend | C2 | S1,S4 |
| S6 | SW criação worker + handlers + progress + cost rows + quota | backend | C1 | S2,S3,S4 |
| S7 | SW agent-tools router factory + 9 read tools | backend | C1 | S0 |
| S8 | Agents: platform agent definition, evals, `turns/stream` | ai+backend | C1 | S7 |
| S9 | SW chat → agents turn, multi-select, saga N-claims, publicação generation | backend | C2 | S8, RP-3 |
| S10 | Context assembler + brain synthesis + diagnosis | backend+ai | after S9 | S7 |
| S11 | FE: approve/reject (headline, roteiro, media), multi-select, status line/bar, board stream, quota editor, remove legenda button | frontend | C1 contract-first | S5 shapes |
| S12 | Onboarding "método do criador" | backend+frontend | C1 | S10 |

Pilot first: route `reel_narrado` end to end (S2, S3 tts+motion, S6) before carrossel, estático, avatar.

Owner-gated: (1) apply 360 in prod + ship RP-3 before S9; (2) apply new migrations (predeploy_check); (3) HeyGen account/key; (4) per-creator voice consent document before any clone; (5) publishing the agent version (eval gate).

## 8 · Risks
Streaming regression on the agents runtime (per-org flag until `turns/stream`); render CPU on the shared VPS (separate worker, concurrency 1, measure first); vendor credit runaway in batches (quota + pre-flight); hashtag CHECK on legacy rows (NOT VALID + cleanup); double maintenance during the strangler (time-boxed flag).

## 10 · Owner decisions (2026-11-19, binding)
1. Avatar voice = our ElevenLabs clone fed to HeyGen as audio (one voice across formats; consent on both vendors).
2. Link = the published post URL → existing `permalink`; the owner fills it by hand until the IG automation fills it.
3. Old cards: deleted (2 rows, 0 events/assets, done 2026-11-19); start fresh — no headline-approval backfill needed.
4. Carrossel = static slides only.
5. Vendor quota: US$15/month per org by default, editable in the UI.
6. Card created at selection with `aguardando_aprovacao`; approval gates leaving Roteiro.
7. Transcription check opt-in only; approval mandatory; no posting yet.
8. Script rules for the agent: humanized voice; CTAs chosen from the post objective (none mandatory, justified); exactly 5 hashtags; sources verified.
9. Static images: Claude designs the layout, rendered by code (no image model); narrated reels/carousels drawn by code (no photos, no paid image generation).
