# Diretor de Edição — approval → Reel production: technical contract (v0, 2026-11-27)

> Companion of `PROJECT.md` (diagnosis, alternatives, decisions). This file is the **contract of what was built** (structure only) and of what Phase C must add. Code: `products/social-wiring/backend/app/modules/media_creation/direcao/`. Nothing here decides storytelling, a generator vendor or a render mechanism.

## 1. Shape

```
headline approved ┐                                   (apr_events, seed approvals organ)
                  ├─► gatilho.avaliar_post ─► cs_direcao_evento('direcao_solicitada', chave) ─► CriacaoService.enfileirar
roteiro  approved ┘        (idempotent, switch off by default)                                      │
                                                                                                   ▼
   recepcao ─► estilo ─► plano ─► midia ─► montagem ─► checagens ─► pacote   (7 seed StepSpecs, one cs_criacao_jobs row each)
                 ▲          ▲        ▲         ▲
            ResolvedorDeEstilo  PlanejadorDeCenas  GeradorDeMidia  Montador      ← the four seams (Protocol + Fake; Real = open decision)
                                                                                                   │
   criacao_concluida ─► stage Aprovação final (human) ─► midia_aprovada → Pronto | midia_reprovada → re-run only the rejected stage
```

## 2. Route

`reel_dirigido` (`criacao_rotas.py`): `passos = PASSOS_DIRECAO`, skips the Edição stage like `reel_narrado`, `gatilho_automatico=True`. It is **selected only by an explicit `cs_posts.criacao_rota`** (migration 373 admits the key); `ROTA_POR_FORMATO` never resolves to it. It is **not runnable**: `criacao_passos.PASSOS` has no entry for its steps, so `implementada()` is False and any enqueue is refused with the coded `rota_nao_implementada` (recorded as `direcao_recusada`). Activation = §8.

## 3. The trigger (`direcao/gatilho.py`)

`GatilhoDirecao.avaliar_post(org, post)` → `Resultado{resultado, post_id, chave, codigo}`; outcome enum (closed): `disparado | ja_solicitado | desligado | sem_gatilho_na_rota | aprovacoes_pendentes | recusado | post_nao_encontrado`.

Order of evaluation (cheapest first): post exists → route has `gatilho_automatico` → switch on → `headline_aprovada ∧ roteiro_aprovado` (the same functions the Criação gate uses; the roteiro approval is of its CURRENT versao) → idempotency.

- **Key** `chave = direcao:<post_id>:h<headline_id>:r<roteiro_id>:v<roteiro_versao>`. Same approval pair ⇒ same key ⇒ no second run. An edited, re-approved roteiro (new versao) ⇒ new key ⇒ new run.
- **Event** `direcao_solicitada` (intent: "the approvals completed; production was asked for") written by `cs_direcao_evento` (373) — `ON CONFLICT DO NOTHING` on the partial unique index `(post_id, dados->>'chave') WHERE tipo='direcao_solicitada'`; returns false when the key was already requested. `dados = {rota, headline_id, roteiro_id, roteiro_versao, chave}`. **No PII, no script text.**
- **Crash healing**: if the key already exists but the step ledger has no row for the post, the enqueue is repeated (`CriacaoService.enfileirar` is itself idempotent: an active graph is returned as `ja_em_andamento`). So "event written, enqueue lost" is repaired by the next trigger or by `reconciliar(org)`.
- **Refusals** (route not runnable, quota, consent, gate…): the coded error becomes `direcao_recusada(dados.codigo)` and `Resultado(recusado, codigo)`. Never an exception into the approval; unknown errors get `codigo=erro_interno` + a logged traceback.
- **Call sites** (after the decision is durable; no-op and no DB read while the switch is off): `esteira.aprovar_headline`, `esteira.decidir_aprovacao` (headline/roteiro, approve only), `roteiros.aprovar_roteiro`. Any other approval path is covered by `reconciliar`. The actor is the approving user.
- **Switch** `settings.direcao_gatilho_ativo` (default False). Per-org scoping = owner decision D1.

## 4. Stages (`direcao/passos.py`, data)

| Stage | Reads | Decides via | Guard (deterministic) | Records (ledger `medicoes`) | Cost |
|---|---|---|---|---|---|
| `direcao_recepcao` | frozen input (job payload) | — | non-empty speech; ids `w0..wN`; org/post match | `palavras`, `roteiro_versao`, `roteiro_sha256` | 0 (local) |
| `direcao_estilo` | recepcao | `ResolvedorDeEstilo` | — | `estilo_id/versao/origem` | 0 |
| `direcao_plano` | recepcao, estilo | `PlanejadorDeCenas` | `validar_plano`: anchors are known word ids, `inicio<=fim`, unique scene ids, on-screen text = literal span of the speech or approved label | `planejador`, `versao`, `n_cenas`, coverage (`palavras_sem_cena`, `sobreposicoes`) | port-reported or `nao_medido` |
| `direcao_midia` | recepcao, plano | `GeradorDeMidia` (`estimar_usd` = quota pre-flight) | — | vendor/model/request id/units from the port | port-reported or `nao_medido` |
| `direcao_montagem` | recepcao, plano, midia | `Montador` | — | measurements taken on the ENCODED file | port-reported or `nao_medido` |
| `direcao_checagens` | plano, midia, montagem | — | refuse synthetic output; `avaliar_medicoes` (LUFS −14±1, true peak ≤ −1.5, safe-zone empty, 1080×1920, duration; missing core measurement ⇒ `nao_medido` failure; hook/sync advisory unless measured false) | `avisos_nao_medidos` | 0 |
| `direcao_pacote` | all | — | registers the asset through the injected `registrar_asset` | `asset_id` | 0 |

Failure codes are stable and visible on the card (`falhou(codigo)`): `roteiro_sem_fala`, `entrada_invalida`, `plano_invalido`, `saida_sintetica`, `checagem_reprovada`, `cota`, `passo_anterior_sem_saida`, plus whatever a port's `DirecaoError.codigo` carries. Messages never carry script text.

**Outcome enum of a run** (`resultado_da_rodada`, derived from the ledger): `entregue_para_revisao | falhou | cancelado | em_andamento`. The human outcome is the existing `midia_aprovada | midia_reprovada`.

Progress weights are provisional (`NOC-REMEDIATE[direcao-pesos-provisorios]`): replace with measured medians.

## 5. The four seams (`direcao/portas.py`) — the extension points

| Port | Method | Open decision |
|---|---|---|
| `ResolvedorDeEstilo` | `resolver(entrada) -> EstiloRef` | D8 style registry / D2 selection |
| `PlanejadorDeCenas` | `planejar(entrada, estilo) -> PlanoDeCenas` | D4 storytelling (scene composition/sequence, settings, camera, transitions, asset use, narration↔scene↔graphics) — `CenaPlanejada.dados` is an opaque payload the skeleton never reads |
| `GeradorDeMidia` | `estimar_usd(plano)`, `gerar(entrada, plano) -> MidiaGerada` | D5 vendor / mechanism, consent, quota |
| `Montador` | `montar(entrada, plano, midia) -> Montagem` | D6 assembly / render mechanism |

Rules for any implementation: anchor by word id, add no text, report cost/units MEASURED or `None`, return storage keys never local paths, never publish, never call the DB. `fabrica.make_adaptadores(allow_fake=False)` returns Fakes only on explicit opt-in and otherwise raises `DecisaoPendente` (`direcao_decisao_pendente`): a missing decision never degrades into a fake video. Fakes are flagged `sintetico=True` and cannot pass `checagens` unless `DirecaoDeps.permitir_sintetico`.

## 6. Human gates

Built: the existing final gate (Aprovação final). Extension point (not built, D7): a mid-run gate needs a runner status the seed lacks (`aguardando_humano`) and an approval subject for the plan (`("plano", id)` through the seed approvals organ, versioned by plan hash). The graph shape already supports it: a gate is a step between `plano` and `midia`.

## 7. Data (migration 373, NOT applied)

`cs_posts.criacao_rota` admits `reel_dirigido`; `cs_post_eventos.tipo` admits `direcao_solicitada`, `direcao_recusada` (364's list kept); unique index `cs_post_eventos_direcao_solicitada_uq`; definer RPC `cs_direcao_evento(p_org,p_post,p_tipo,p_chave,p_dados,p_ator) → boolean` (service_role only). Forward-only, idempotent, backward compatible (an N-1 image ignores it). Tier: org. Metrics enabled: approvals→runs vs refusals by code, time from second approval to request, runs per post, outcome per `estilo_id`/`planejador.versao`, human approval rate per style/planner version (join with 364).

## 8. Activation checklist (Phase C — after D1-D6)

1. Register the seven stage names in `criacao_passos.PASSOS` (label/weight from `direcao.passos.ESTAGIOS`) and a `specs_da_rota` branch that returns `direcao.passos.montar_grafo(entrada)` (the service freezes the entry with `entrada.congelar_entrada` from the approved headline + roteiro, computes `estimativas[direcao_midia]` from `gerador.estimar_usd`).
2. Merge `build_handlers_direcao(DirecaoDeps(adaptadores=make_adaptadores(), registrar_asset=<PostAssetsService wrapper>))` into the worker's registry (`criacao_handlers.build_handlers`), keeping `permitir_sintetico=False`.
3. Implement the Real adapters one seam at a time behind `make_adaptadores` (each with consent/quota checks, FakeX kept, contract tests shared by Fake and Real), replacing `NOC-REMEDIATE[direcao-adapters-reais]`.
4. Decide D1/D2 and add the per-org switch + the route selection UI; keep `reel_narrado` untouched.
5. Apply 373 (owner-gated), switch on for ONE org, watch `direcao_solicitada/_recusada` and the ledger, then widen.
6. Optional D7 gate; spec v0.2 for word-id scenes (G4).
