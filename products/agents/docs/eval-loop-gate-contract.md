# Eval-loop gate — contract (G1–G7)

Owner spec (2026-11-09), verbatim: "running evals that dont make score better needs to get flagged … eval loops should be gated and stop whenever it feels like its 'good enough' … 2 calls not improving score stops and notifies why stopped mid-flight". Migration `076_eval_loops.sql`; target / budget cap / max rounds became a platform-admin config on 2026-11-12 (migration `086_eval_loop_config.sql`, "Target 95% · Cap at U$5" + "set the number of rounds ... as a config"). Backend slice only; a UI slice follows from this document.

Platform IP tier: every table is `agents.eval_*` (service role only, `COMMENT … 'tier:platform'`). Every route below is platform-admin or the platform-issued `studio:evals-run` token (a `studio:publish` token on a dev-advisor agent also reads/starts, exactly like the run routes). No new public surface.

## The rules and where each lives

| # | Rule | Enforced by |
|---|---|---|
| G1 | target = the config's `alvo` (default 95%), floor = the agent's `publicacao_limiar` (`piso`); both frozen on the loop at start | `eval_loops.alvo/piso`; read in the state (`acima_do_piso`) and in the stop message |
| G2 | planned rounds N (omitted → the config's `rodadas_max`, default 10; never above it), checkpoints at 5, 10, 15 (those ≤ N) | `rodadas_planejadas` (1..100, ≤ config `rodadas_max`); a checkpoint is an in-app notice + `checkpoints[]` in the state; at N the loop concludes `rodadas_esgotadas` |
| G3 | stop at the target (`score >= alvo`, default 95%) | run close hook: `score >= alvo` → `concluido` / `alvo_atingido` |
| G4 | 2 consecutive scored rounds without improvement → STOP + notify mid-flight, above or below the floor | run close hook → `parado` / `sem_melhora` + notification (payload below) |
| G5 | every round that did not raise the score is an "overcall", listed with its cost | `serie[].overcall`, `overcalls[]`, `custo_overcalls_usd`; a `WARNING agents.eval_loop.overcall` log |
| G6 | a round on an unchanged content hash beyond the consolidation passes is refused: fix first, then run | run start → 409 `hash_inalterado` |
| G7 | spend per round against the loop budget (the config's cap, default US$ 5, never exceeded); reaching it stops the loop for an owner decision | run close hook → `parado` / `orcamento_atingido`; run start clamps the run cap to what is left |

Definitions. A **round** is one run started with the loop's id. A round **improved** when its score is strictly above the best score of the earlier scored rounds; the first scored round is the baseline (neither an improvement nor an overcall). A round with no score (the run failed before measuring: harness error, spec refused, cancelled) is **neutral** for G4/G5, but its cost still counts for G7. Stop order when a round closes: G3 → G7 → G4 → rounds exhausted.

### G6 reuses the consolidation, not a new counter

A re-run on the hash of an earlier closed round of the same loop is refused when (a) that earlier round still had failing cases (re-measuring a failure nobody fixed), or (b) the loop already has as many rounds on that hash as the longest clean streak any active case of the suite needs to consolidate (`ConfigConsolidacao.limite("em_validacao", criticidade)`, migration 072: 5 normal / 10 critico). Clean re-runs on an unchanged hash stay allowed up to that count because that is exactly how a case consolidates. The existing 409 `todos_consolidados` (everything consolidated and unaffected) is unchanged and still comes first for a default run.

### G7 reuses the run costs, not a second tracker

A round's cost is the run's own recorded `custo_usd` (`eval_runs` / `eval_mecanismo_runs`, the same number behind `limite_usd`), copied onto the round when it closes; the loop's `gasto_usd` is their sum. The seed shared daily ceiling (`noctusai_lib.integrations.llm.spend_ceiling`, key `automacao-avaliacoes`, public.ai_usage) is untouched and keeps bounding token-started runs per org per 24h; the loop budget is the narrower, per-refinement bound on top of it.

## Suites

Both suites are covered, one loop per `(agent, suite)`:

| suite | run table | start | round score | failing cases |
|---|---|---|---|---|
| `comportamento` | `eval_runs` | `POST …/evals/runs` body `loop_id` | `eval_runs.score` | slugs of results `reprovado`/`erro` |
| `mecanismo` | `eval_mecanismo_runs` | `POST …/draft/mecanismo-runs?loop_id=` | `casos_aprovados / total_casos` (pass^k per case) | slugs of cases with a non-`aprovado` execution |

A looped run is a whole-suite run (default selection, consolidation still skips consolidated cases). Excluded inside a loop: `case_ids` / `repetir_falhas_de` (a partial score is not comparable with the series) and `modelo_geracao` (another model's score is not the version's own). Runs started without `loop_id` are unchanged.

## Endpoints (prefix `/api/studio/agents/{key}/evals/loops`)

### `POST /{key}/evals/loops` → 201 `LoopOut`
Body (strict): `{ "suite": "comportamento" | "mecanismo", "rodadas_planejadas"?: 1..100, "orcamento_usd"?: number > 0, ≤ 500 }`. Both optional: `rodadas_planejadas` omitted → the config's `rodadas_max`; `orcamento_usd` omitted → the config's `orcamento_usd`. `alvo` is the config's `alvo` at the moment the loop starts and `piso` the agent's `publicacao_limiar`, both stored (frozen) on the loop: a later config edit never moves an open loop.
Errors: 409 `loop_ativo_existente` (the agent already has an active loop on this suite); 422 `rodadas_acima_do_maximo` (rounds above the config's max); 422 `orcamento_acima_do_teto` (budget above the config's cap, for EVERY caller, a platform admin included: change the config instead); 422 validation (suite, bounds, unknown field); 404 `agent_not_found`; 403 `user_required`.

### `GET` / `PUT /api/studio/plataforma/eval-loop-config` (platform admin only)
The platform-level loop config (loops run on platform agents): one set of values, stored in `agents.runtime_settings` (keys `eval_loop_alvo`, `eval_loop_orcamento_usd`, `eval_loop_rodadas_max`; service role only, tier platform). Until first edited it reads the code defaults. `GET` → `{alvo: 0.95, orcamento_usd: 5.0, rodadas_max: 10, alterado_por: uuid|null, alterado_em: iso|null}`. `PUT` body (strict, full replace, all three required): `{alvo: 0 < x ≤ 1, orcamento_usd: 0 < x ≤ 500, rodadas_max: 1..100}` → the same shape; 422 on an out-of-range, missing or unknown field; 403 `platform_admin_required`; 401 unauthenticated. A change that alters a value records one immutable `loop_config_alterada` event (`agents.eval_loop_config_eventos`: before, after, actor) in the same transaction (RPC `agents.set_eval_loop_config`); an unchanged PUT records nothing.

### `GET /{key}/evals/loops[?suite=&status=]` → `{items: LoopOut[]}` (newest first)
### `GET /{key}/evals/loops/{loop_id}` → `LoopOut`; 404 `loop_not_found`
### `POST /{key}/evals/loops/{loop_id}/stop` body `{ "motivo"?: string ≤ 300 }` → `LoopOut`
Manual stop (`parado_manualmente`). A round in flight finishes on its own and is still recorded. 409 `loop_ja_encerrado`; 404 `loop_not_found`. Gate: `require_evals_run_cancel` (platform admin or the evals-run token).

### `LoopOut`
```
id, agente_chave, suite, status: ativo|parado|concluido,
motivo_parada: alvo_atingido|sem_melhora|orcamento_atingido|rodadas_esgotadas|parado_manualmente|null,
detalhe_parada: object|null,            # sem_melhora: {seguidas, hash_anterior, hash_atual, conteudo_mudou, partes_alteradas}
rodadas_planejadas, rodadas_feitas, alvo, piso, orcamento_usd, gasto_usd, restante_usd,
melhor_score, score_atual, acima_do_piso, started_at, stopped_at,
serie:       [{rodada, run_id, status: executando|concluida|falhou|cancelada, score|null, custo_usd,
               compiled_hash, melhorou: true|false|null, overcall, falhas: [case slug]}],
overcalls:   [{rodada, run_id, score, custo_usd}], custo_overcalls_usd,
checkpoints: [{rodada: 5|10|15, atingido, score|null, gasto_usd|null}]
```

## Run start with a loop (both suites)

Checked in this order; every refusal is a 409 `{detail (pt-BR), code}` unless noted, and **no run is booked** when it refuses.

| code | when | pt-BR message |
|---|---|---|
| 404 `loop_not_found` | the id is not a loop of this agent/org | Loop de avaliação não encontrado. |
| 422 `loop_suite_invalida` | the loop belongs to the other suite | Este loop é da suíte de X, não de Y. |
| 422 `loop_run_parcial` | `case_ids` / `repetir_falhas_de` with a loop (behaviour) | Uma run de loop cobre a suíte inteira: não aceita case_ids nem repetir_falhas_de. |
| 422 `loop_modelo_geracao_nao_permitido` | `modelo_geracao` with a loop (behaviour) | Uma run de loop usa o modelo da própria versão. |
| 409 `loop_encerrado` | the loop is not `ativo` | O loop foi encerrado (<motivo>). Inicie um novo loop. |
| 409 `rodada_em_andamento` | a round of the loop is still open | Já há uma rodada deste loop em andamento. Aguarde terminar ou cancele a run. |
| 409 `orcamento_do_loop_atingido` | `gasto_usd >= orcamento_usd` | O orçamento do loop (US$ N) foi atingido. A decisão de continuar é do dono. |
| 409 `rodadas_esgotadas` | the planned rounds are done | As N rodadas planejadas do loop acabaram. |
| 409 `hash_inalterado` | G6 | O conteúdo do agente não mudou desde a rodada N, que ainda tinha casos falhando (a, b). Corrija o conteúdo e rode de novo: rodar sem corrigir só repete o mesmo resultado. — or, beyond the consolidation passes: … não mudou em N rodadas seguidas, que já cobrem as passagens de consolidação (M). Altere o conteúdo ou encerre o loop. |

Then the existing per-suite refusals apply unchanged (`todos_consolidados`, `no_eval_cases`, `compile_blocked`, `driver_indisponivel`, 429/503 daily ceiling…). The run's `limite_usd` is `min(requested or default, restante_usd)`; the clamped value is on the run (`EvalRunOut.limite_usd`), never hidden. A looped run is stamped `loop_id` (nullable column on both run tables) and has one `eval_loop_rodadas` row opened at booking.

A round whose run already ended but whose close hook never ran (process crash, a run cancelled before it was claimed) is **reconciled at the next admission** (closed from the run's stored state) so a stuck round never blocks a loop forever. Cancelling a run (`POST …/evals/runs/{id}/cancel`) closes its round as neutral at once.

## Run completion (the hook)

When a run ends — concluded, budget-cut, failed, cancelled — its round closes: score, cost and failing cases are read from the run stores (never from the caller), the G3/G4/G5/G7 verdict is computed, the round and the loop's spend/stop are written (the conditional UPDATE on `status='executando'` makes the close idempotent), then the owner is notified. The hook never raises into a finished run (its verdict is already stored): a failure is logged with the exception and the next admission reconciles.

## Notification (in-app, `public.notifications` via the agents `NotificationSink`)

Recipients: every platform admin (the owner is one). Dedup keys `eval_loop:<loop_id>:parada` and `eval_loop:<loop_id>:cp<N>`. `metadata.link` is `/agentes` (the UI slice may refine it). A delivery failure is logged and never undoes the stop; no platform admin is logged as an error, not skipped silently.

- **Stop, no improvement** (kind `agents.eval_loop_parado`):
  title `Loop de avaliação parado: <chave> (<suite>)`;
  message `Parou na rodada 4 de 30: 2 rodadas seguidas sem melhora da nota (piso 80%, alvo 95%; melhor nota abaixo do piso). Notas: 60% → 70% → 70% → 69%. <Mudou entre as duas últimas rodadas: secao:x, texto:y. | O conteúdo não mudou entre as duas últimas rodadas (mesmo hash): a rodada foi repetida sem correção. | O conteúdo mudou … (hash diferente), sem melhora na nota.> Casos ainda falhando (3): a, b, c. Gasto US$ 4.50 de US$ 5.00.`
  metadata `{motivo, loop_id, agente_chave, suite, serie[], hashes[], casos_falhando[], gasto_usd, orcamento_usd, rodadas_feitas, rodadas_planejadas, overcalls[{rodada, custo_usd}], detalhe}`.
- **Target reached** (same kind): title `Loop concluído: <chave> (<suite>)`.
- **Budget** (same kind): `O orçamento do loop foi atingido na rodada N: US$ X de US$ Y. Notas: … Decisão do dono: aumentar o orçamento em um novo loop ou encerrar.` + failing cases.
- **Planned rounds exhausted** (same kind): `As N rodadas planejadas acabaram sem chegar a <alvo>% (95% by default). Notas: … Gasto …`.
- **Checkpoint** (kind `agents.eval_loop_checkpoint`, rounds 5/10/15 ≤ N): `Rodada N de M. Notas: … Gasto … Rodadas sem melhora: K (US$ …).`

## Not in this slice

The frontend (loop card "95% / 80%", series chart, overcall list, stop button); a "resume a stopped loop" action (the owner decides by opening a new loop, with a new budget if wanted); email delivery of the stop notice (in-app only, per the spec); an automatic per-loop budget for Julia (the same default applies, the owner sets `orcamento_usd` per loop).
