# maya-blocks — CONTRACT (v1: S0 contract + S1 schema)

Status: S0 + S1 authored on `feat/sw-maya-blocks-contract` (2026-10-19). Schema = migration
`products/social-wiring/backend/migrations/286_atendimento_blocos_supervisao.sql` (NOT applied —
the tech-lead applies it with `noctus.dev.migrate_product`). Everything below S1 (services,
routes, sinks, jobs, pages) is the contract later slices build TO; nothing is implemented yet.

Owner model (memory `project_maya_julia_agent_architecture`): the real-estate atendimento runs
as a closed list of **blocks**, each with one accountable specialist (an agent or humans). A
**handoff** is the explicit, recorded moment a lead/card leaves one block for the next. **Maya**
watches every block, scores each block's specialist and **reports to the owner**. **Julia** is
block `sdr` — the studio agent key `lead-imob` (`products/agents/backend/app/studio/lead_imob.py`),
NOT the `julia` key (that is the academia agent).

---

## 1. Blocks (closed list, in code + in the DB CHECKs)

| order | `bloco` | role | pipeline it owns | default `agent_key` |
|---|---|---|---|---|
| 1 | `sdr` | first contact + qualification (Julia) | none — the pre-card phase | `lead-imob` |
| 2 | `atendimento` | the broker: visits, proposals | `funil` | `null` (humans) |
| 3 | `negociacao` | negotiation up to accept/reject | `funil` | `null` |
| 4 | `juridico` | contract, parties, signature | `processos_venda` | `null` |
| 5 | `financeiro` | financing, deed, settlement, keys | `processos_venda` | `null` |
| 6 | `contador` | invoice / accounting close | `processos_venda` | `null` |

- The list lives in ONE backend constant (`BLOCOS`, S2: `app/services/atendimento_blocos_service.py`)
  and is mirrored by four DB CHECKs in 286 (`atendimento_blocos_bloco_valido`,
  `atendimento_handoffs_blocos_validos` ×2, `agente_scorecards_bloco_valido`). Adding a block =
  a migration widening the CHECKs + the constant, same commit.
- `agent_key = null` means humans run the block. A non-null key must be in the code allowlist
  `AGENTES_POR_BLOCO` (v1: `{"sdr": {"lead-imob"}}`; every other block has no agent yet).
- `ativo` (DEFAULT `false`) means **Maya supervises and scores this block**. In v1 it switches
  nothing lead-facing — Julia's own on/off stays where it is today (the WhatsApp connection's
  agent config). A later slice that lets a block agent act will gate on `ativo` too.

### 1.1 The current block is DERIVED, never stored on the card

```
bloco_atual(contato | lead):
  contato with lead_id IS NULL                      -> "sdr"
  lead with a processos_venda card (via atendimento) -> dono(processos_venda, processo.etapa.slug)
  lead with an atendimentos card                     -> dono(funil, atendimento.etapa.slug)
  lead with no card (spawn failed)                   -> null  ("sem_card", logged)
dono(pipeline, slug) = the block whose (pipeline, etapas) contains slug, else null ("sem_bloco")
```

A stage owned by no block yields `null`: no handoff is emitted across it and it is listed in
`GET /api/atendimento-blocos` → `etapas_sem_bloco` so the owner can assign it.

### 1.2 Default stage → block map (from the real defaults)

Derived from `ensure_default_pipeline_stages` as last redefined in migration 060 (the canonical
defaults every org gets; 034/037 are superseded). The `esteira` pipeline (241, content
production) is not an atendimento pipeline and is never mapped.

| pipeline | slug (label) | block |
|---|---|---|
| funil | `qualificacao` (Qualificação) | atendimento |
| funil | `visitas` (Visitas) | atendimento |
| funil | `proposta_recebida` (Proposta Recebida) | atendimento |
| funil | `negociacao` (Negociação) | negociacao |
| funil | `proposta_decisao` (Proposta Aceita/Rejeitada, papel `proposta_aceite`) | negociacao |
| processos_venda | `elaboracao_contrato` (Elaboração do Contrato) | juridico |
| processos_venda | `analise_partes` (Análise das Partes) | juridico |
| processos_venda | `revisao_contrato` (Revisão do Contrato) | juridico |
| processos_venda | `assinatura` (Assinatura) | juridico |
| processos_venda | `financiamento_escritura` (Financiamento & Escritura) | financeiro |
| processos_venda | `finalizacao` (Finalização) | financeiro |
| processos_venda | `entrega_chaves` (Entrega das Chaves) | financeiro |
| processos_venda | `nota_fiscal` (Nota Fiscal, papel `final`) | contador |

This map is the code default (`ETAPAS_PADRAO`, S2). An org without a row for a block uses it; a
saved row replaces it for that block. Orgs that renamed/added stages see the unmatched slugs in
`etapas_sem_bloco`. (Owner-refinable: `finalizacao`/`entrega_chaves` → financeiro is a default
pick, not a rule.)

### 1.3 Table `atendimento_blocos` (286)

`id, org_id, bloco, agent_key NULL, ativo bool DEFAULT false, pipeline NULL, etapas text[] DEFAULT '{}', updated_by, created_at, updated_at`

Guards: bloco in the list · `sdr` ⇔ `pipeline IS NULL AND etapas = '{}'`, every other block has
`pipeline IN ('funil','processos_venda')` · `agent_key ~ '^[a-z][a-z0-9-]{1,39}$'` · UNIQUE
(org_id, bloco) · trigger `atendimento_blocos_etapas_disjuntas`: slugs `^[a-z0-9_]+$`, no repeats, and
**disjoint across blocks of the same (org, pipeline)** (constraint names
`atendimento_blocos_etapas_validas` / `atendimento_blocos_etapas_disjuntas`). The pipeline of
each block is fixed by the table in §1 — the API never accepts it from the client.

---

## 2. Handoffs

### 2.1 Table `atendimento_handoffs` (286) — references only, no copied PII

| column | meaning |
|---|---|
| `de_bloco`, `para_bloco` | blocks of the closed list, different (`blocos_distintos`) |
| `de_agent_key`, `para_agent_key` | snapshot of who ran each block at emission (null = humans) |
| `gatilho` | `novo_lead` \| `movimento_etapa` — says which table `origem_evento` points into |
| `origem_evento` | `lais_eventos.id` (novo_lead) or `pipeline_movimentos.id` (movimento_etapa) |
| `contato_id` → lais_contatos, `lead_id` → leads, `atendimento_id` → atendimentos, `atribuicao_id` → lais_atribuicoes, `entrega_id` → lais_envio_entregas | all nullable, `ON DELETE SET NULL` (an LGPD erasure of the contato never blocks on a handoff) |
| `status` | `emitido` → `assumido` \| `expirado` (both terminal) |
| `created_at`, `assumido_at`, `expirado_at` | the evidence behind the status (`status_coerente`) |

UNIQUE (org_id, gatilho, origem_evento): a replayed sink/hook is a no-op (S2 writes with
`upsert(..., on_conflict="org_id,gatilho,origem_evento", ignore_duplicates=True)`).

### 2.2 When a handoff is recorded

Master switch: a handoff row is written **only when `supervisao_config.supervisao_ativa` is
true** for the org (absent row = false). With supervision off nothing is written, nothing is
read, nothing changes. Recording never sends anything to anyone.

**T1 — `novo_lead` sink** (S2). Registered with `lais_eventos_service.registrar_sink`. Fires on
the `novo_lead` event `lais_envio_service.enviar` emits after a successful send
(`{lead_id, gatilho, criado}`, `services/lais_envio_service.py` ~line 399). Writes:
`de_bloco='sdr'`, `para_bloco=bloco_atual(lead)` (usually `atendimento`: the spawn trigger
placed the card in `qualificacao`; for an existing lead `criado=false` it is wherever that card
already is), `contato_id=event.contato_id`, `lead_id=payload.lead_id`, `atendimento_id` = the
lead's card, `atribuicao_id` = the latest `lais_atribuicoes` row of the contato (written just
before the event by `_atribuir_antes_de_notificar`), `entrega_id` = the latest
`lais_envio_entregas` row of the contato with `status='ok'`, `origem_evento=event.id`.
`para_bloco` resolving to `null` or `sdr` ⇒ no row, logged at warning with the reason.
A sink failure is logged by `emitir` and never reaches the send (existing seam behaviour).

**T2 — `pipeline_movimentos` block-boundary hook** (S2). Called right after every stage move that
writes a `pipeline_movimentos` row (`modules/pipeline/routers/boards.py` `mover_atendimento` /
`mover_processo`, and `funil_eventos` via the same `move_card`). Writes a handoff iff
`dono(pipeline, de_etapa) != dono(pipeline, para_etapa)` and both are non-null:
`gatilho='movimento_etapa'`, `origem_evento=movimento.id`, `atendimento_id` = the card (for a
processos_venda card: its `atendimento_id`), `lead_id` from the atendimento. Moves inside one
block are not handoffs. Hook failure is logged at error; the move already succeeded and is
never undone.

**T2 prerequisite (S2):** the funil → processos boundary (negociacao → juridico) has **no
movimento today** — `modules/pipeline/aceite.py` inserts the processos_venda card without a
`pipeline_movimentos` row (its docstring says so). S2 makes `aceitar_proposta` write one
(`pipeline='processos_venda'`, `de_etapa_id=NULL`, `para_etapa_id` = the initial stage); when
`de_etapa_id IS NULL` on processos_venda the hook takes `de_bloco = dono(funil, atendimento's
accept stage)`. `pipeline_movimentos.responsavel_id` is NOT NULL, so the accept path must carry
an actor (the route has the user; the `proposta_aceita` funnel event must pass one).

### 2.3 Status machine

```
emitido --(first take-over signal after created_at)--> assumido   (assumido_at = signal time)
emitido --(now >= created_at + horas_para_assumir, sweep)--> expirado  (expirado_at = sweep time)
assumido, expirado: terminal (a late take-over after expiry is NOT back-filled)
```

Take-over signals in v1 (human-run target block), first one wins:
1. a `pipeline_movimentos` row on the same card (`entidade_id` = atendimento/processo id), any
   stage, created after the handoff;
2. a `cliente_notas` row with `autor_id IS NOT NULL` on the card's cliente, created after the
   handoff (Julia's notes have `autor_id NULL` and never count).

Agent-run target blocks (none in v1 besides `sdr`, which is never a target) define their own
signal in the slice that introduces the agent. The sweep (S3 job, every 15 min) both detects
signals and expires; `horas_para_assumir` comes from `supervisao_config` (default 24, 1..168).

---

## 3. Scorecards (Maya)

### 3.1 Table `agente_scorecards` (286)

`id, org_id, bloco, agent_key NULL, dia date, metricas jsonb object, rubrica_versao '<bloco>.vN', calculado_at`
— UNIQUE NULLS NOT DISTINCT (org_id, bloco, agent_key, dia). Computed by an S3 job for every
`ativo` block of every org with `supervisao_ativa`; recomputing a day upserts the row (the last
7 days are recomputed nightly, so late-arriving facts land; `calculado_at` says when).

`dia` = a calendar day in **America/Sao_Paulo**: window `[dia 00:00, dia+1 00:00)` SP, converted
to UTC for queries. Every count below is `org_id`-filtered. Ratios are **fractions** (0.42), with
the numerator and denominator stored beside them; a ratio with denominator 0 is `null`, never 0.
Aggregating over a period sums numerators and denominators — never averages daily ratios.

### 3.2 Rubric `sdr.v1` — Julia (`bloco='sdr'`, `agent_key='lead-imob'`)

| metric (`metricas` key) | formula | source |
|---|---|---|
| `leads_entrada` | count `lais_contatos` with `created_at` in the window | lais_contatos (267) |
| `tpr_n` | count `lais_interacoes` with `iniciada_at` in window and `primeira_resposta_at IS NOT NULL` | lais_interacoes (267) + `primeira_resposta_at` (286) |
| `tpr_p50_s`, `tpr_p90_s` | over those episodes, `extract(epoch from primeira_resposta_at - iniciada_at)`; nearest-rank percentile: sort ascending, take element `ceil(q·n)` (1-based), q = 0.5 / 0.9; `null` when `tpr_n = 0` | same |
| `tpr_sem_resposta` | episodes started in window with `primeira_resposta_at IS NULL` at computation time | same |
| `qualificados` | distinct `contato_id` in `lais_envio_entregas` with `status='ok'`, `gatilho IN ('qualificado','visita','captacao')`, `created_at` in window | lais_envio_entregas (270) |
| `qualificacao_taxa` | `qualificados / leads_entrada` | — |
| `frios`, `frio_taxa` | same as `qualificados` with `gatilho='frio'`; `/ leads_entrada` | lais_envio_entregas |
| `invalidos`, `invalido_taxa` | `gatilho='invalido'`; `/ leads_entrada` | lais_envio_entregas |
| `entregas_manuais` | `gatilho='manual'`, `status='ok'` (a human sent it — not credited to Julia) | lais_envio_entregas |
| `envios_bloqueados` | count `lais_eventos` `tipo='envio_bloqueado'` in window | lais_eventos (`lais_envio_gate.exigir`) |
| `envios_bloqueados_por_motivo` | the same rows grouped by `payload->>'motivo'` → `{motivo: n}` | same |
| `handoffs_humanos` | count `lais_atribuicoes` with `motivo='handoff'` in window | lais_atribuicoes (276) |
| `handoffs_humanos_por_motivo` | `{motivo_codigo: n}` from `lais_eventos` `tipo='handoff'`; `null` until S2 emits that event (below) | lais_eventos |
| `handoffs_emitidos` | count `atendimento_handoffs` with `de_bloco='sdr'`, `created_at` in window | atendimento_handoffs (286) |
| `handoffs_nao_assumidos` | of those: `status='expirado'`, or `status='emitido'` and `created_at + horas_para_assumir <= calculado_at` | same + supervisao_config |
| `horas_para_assumir` | the threshold used (so the number is reproducible) | supervisao_config |

**Data gaps this contract closes (S2):**
- `primeira_resposta_at` (added by 286) — written once, in the lead-turn deliver path, on the
  first outbound of the open episode (Julia or a human from the inbox):
  `UPDATE lais_interacoes SET primeira_resposta_at = now() WHERE id = :episodio AND primeira_resposta_at IS NULL`.
  Episodes before S2 stay `null` and are reported as `tpr_sem_resposta`, never estimated.
- Human-handoff motivo is not persisted today (only inside the in-app notification text written
  by `lais_agente_service.notificar_handoff`). S2 makes `_apply_handoff` emit `lais_eventos`
  `tipo='handoff'` with payload `{motivo_codigo}` — a CLOSED code mapped from the free text
  (proposed: `pedido_do_lead`, `fora_do_escopo`, `reclamacao`, `outro`; owner-refinable), never the
  raw text. `handoff` is excluded from the notification fan-out (`TIPOS_FANOUT`), so emitting it
  cannot double-notify.

Other blocks get their rubric (`atendimento.v1`, …) in the slice that activates them; until then
an `ativo` human block gets only the handoff metrics (`handoffs_recebidos`,
`handoffs_assumidos`, `assumir_p50_s`/`assumir_p90_s` over `assumido_at - created_at`,
`handoffs_nao_assumidos`) under rubric `<bloco>.v1`.

### 3.3 Table `supervisao_config` (286)

`org_id PK, supervisao_ativa bool DEFAULT false, horas_para_assumir int DEFAULT 24 (1..168), updated_by, created_at, updated_at`.

### 3.4 Report to the owner (S3) — read-only, owner only

- **In-app:** once per day after the scorecards are computed, `lais_eventos_service.emitir(...,
  "relatorio", contato_id=None, payload={"origem": "supervisao", "dia": "YYYY-MM-DD"})`. The
  generic fan-out sends a contato-less event to owners **and admins**; S3 adds the rule
  `payload.origem == "supervisao"` ⇒ recipients = `noctus_users.org_role == 'owner'` only.
  Payload carries the day only — the notification links to `/supervisao?dia=…`.
- **Email:** a `BaseDigestService` subclass (`SupervisaoDigestService`, seed
  `noctusai_lib.domain.digest`) — same scorecards, recipients = the org's owners' emails, daily.
- Both are gated by `supervisao_ativa`. Neither ever goes to a lead or a lead-facing channel.

---

## 4. API

Conventions (same as the product's other modules): every route needs a session — no session is
a **strict 401**; the org is the session's selected org, never a parameter; bodies are
`StrictHttpModel` (unknown field ⇒ 422); dates `YYYY-MM-DD` (SP calendar); timestamps ISO-8601
UTC; ratios are fractions. Error envelope `{"error": {"code", "message", "details"?}}`.
Roles via the seed `require_org_admin_for` on the trusted `noctus_users` row (owner-only =
`admin_roles=frozenset({"owner"})`). Router mounted under the product (S2: `app/modules/supervisao/`).

### 4.1 `GET /api/atendimento-blocos` — any member of the org

200:
```json
{
  "blocos": [
    {"bloco": "sdr", "rotulo": "SDR (Julia)", "ordem": 1, "agent_key": "lead-imob", "ativo": false,
     "pipeline": null, "etapas": [], "origem": "padrao", "updated_at": null, "updated_by": null},
    {"bloco": "atendimento", "rotulo": "Atendimento (corretor)", "ordem": 2, "agent_key": null, "ativo": false,
     "pipeline": "funil", "etapas": ["qualificacao", "visitas", "proposta_recebida"], "origem": "padrao",
     "updated_at": null, "updated_by": null}
  ],
  "etapas_sem_bloco": [{"pipeline": "funil", "slug": "pos_venda", "label": "Pós-venda"}],
  "agentes_por_bloco": {"sdr": ["lead-imob"]},
  "supervisao_ativa": false
}
```
Always exactly 6 `blocos`, in `ordem`. `origem`: `padrao` (no row; §1.2 default) | `org` (saved
row). `etapas_sem_bloco` lists active `pipeline_stages` (funil + processos_venda) of the org that
no block owns; empty list when all are owned. Empty org (no rows anywhere) = all `padrao`.

### 4.2 `PUT /api/atendimento-blocos` — owner/admin

Request (partial: only the listed blocks change; omitted blocks keep their current row/default):
```json
{"blocos": [{"bloco": "atendimento", "agent_key": null, "ativo": true, "etapas": ["qualificacao", "visitas"]}]}
```
Each item: `bloco` (required, closed list, unique within the body), `agent_key` (str|null),
`ativo` (bool), `etapas` (list of slugs; must be `[]` for `sdr`). The backend validates the WHOLE
resulting configuration before writing anything, then writes rows whose `etapas` shrink first
(so a stage moving between blocks never trips the disjointness trigger). Side effect: upserts
`atendimento_blocos` rows (`updated_by` = caller); nothing else — no handoff, no send.
200 = the same body as GET (state after).

| status | `code` | cause |
|---|---|---|
| 401 | `UNAUTHORIZED` | no/expired session |
| 403 | `FORBIDDEN` | not owner/admin |
| 422 | `VALIDATION_ERROR` | unknown field / unknown `bloco` / duplicate `bloco` in body |
| 422 | `etapa_desconhecida` | slug not an active stage of the block's pipeline in this org |
| 422 | `etapa_em_dois_blocos` | resulting config has one slug in two blocks (message names slug + blocks) |
| 422 | `sdr_sem_etapas` | `etapas` non-empty for `sdr` |
| 422 | `agente_indisponivel` | `agent_key` not in `agentes_por_bloco[bloco]` |
| 409 | `conflito_concorrente` | the DB trigger refused (a concurrent save) — re-GET and retry |

### 4.3 `GET /api/supervisao/scorecards?dia=YYYY-MM-DD` — owner only

`dia` optional, default = yesterday (SP). 200:
```json
{
  "dia": "2026-10-18",
  "supervisao_ativa": true,
  "scorecards": [
    {"bloco": "sdr", "agent_key": "lead-imob", "rubrica_versao": "sdr.v1",
     "calculado_at": "2026-10-19T06:00:12Z",
     "metricas": {"leads_entrada": 31, "tpr_n": 28, "tpr_p50_s": 42.0, "tpr_p90_s": 610.0,
                  "tpr_sem_resposta": 3, "qualificados": 9, "qualificacao_taxa": 0.2903,
                  "frios": 4, "frio_taxa": 0.129, "invalidos": 2, "invalido_taxa": 0.0645,
                  "entregas_manuais": 1, "envios_bloqueados": 2,
                  "envios_bloqueados_por_motivo": {"fora_da_janela": 2},
                  "handoffs_humanos": 5, "handoffs_humanos_por_motivo": null,
                  "handoffs_emitidos": 9, "handoffs_nao_assumidos": 1, "horas_para_assumir": 24}}
  ]
}
```
Empty states: supervision off ⇒ `supervisao_ativa:false, scorecards:[]`; on but the day not
computed yet ⇒ `supervisao_ativa:true, scorecards:[]`. Errors: 401 · 403 (not owner) · 422
`dia_invalido` (malformed) · 422 `dia_futuro` (≥ today SP).

### 4.4 `GET /api/supervisao/handoffs` — owner/admin

Query: `status` (`emitido|assumido|expirado`, optional), `de_bloco`, `para_bloco` (optional,
closed list), `desde`, `ate` (`YYYY-MM-DD`, SP, inclusive; default last 7 days), `limit`
(1..100, default 50), `cursor` (opaque, from the previous page). Newest first. 200:
```json
{
  "itens": [
    {"id": "…", "de_bloco": "sdr", "para_bloco": "atendimento", "gatilho": "novo_lead",
     "status": "emitido", "atrasado": true,
     "created_at": "2026-10-18T13:02:11Z", "assumido_at": null, "expirado_at": null,
     "de_agent_key": "lead-imob", "para_agent_key": null,
     "referencias": {"contato_id": "…", "lead_id": "…", "atendimento_id": "…",
                     "atribuicao_id": "…", "entrega_id": "…"},
     "card": {"titulo": "…", "link": "/funil?card=<atendimento_id>"}}
  ],
  "proximo_cursor": null
}
```
`atrasado` = `status='emitido' AND now() >= created_at + horas_para_assumir`. `card` is joined at
read time from `atendimentos` (the board already shows that title) — never stored on the handoff;
`card` is `null` when the card is gone. Empty: `{"itens": [], "proximo_cursor": null}` (also when
supervision is off). Errors: 401 · 403 · 422 `filtro_invalido` (bad status/bloco/date/limit/cursor).

### 4.5 `GET` / `PUT /api/supervisao/config` — owner only

GET 200 `{"supervisao_ativa": false, "horas_para_assumir": 24, "updated_at": null, "updated_by": null}`
(absent row ⇒ these defaults). PUT body `{"supervisao_ativa": bool, "horas_para_assumir": int}`
(both required, 1..168) → upsert, 200 = state after. Errors 401 · 403 · 422.
Turning supervision ON starts recording handoffs from that moment (no back-fill) and the next
nightly job computes scorecards; turning it OFF stops both and keeps the history.

---

## 5. Safety rules (non-negotiable)

1. **No lead-facing sends.** Nothing in this feature calls WAHA/Cloud/email toward a lead or
   creates a send job. Handoff recording, scoring and reporting are internal; the only outputs
   are rows, an owner in-app notification and an owner email.
2. **Everything defaults OFF**: `supervisao_ativa=false`, every block `ativo=false`, no row is
   seeded by 286, and an absent row is always read as off.
3. **References, not copies**: `atendimento_handoffs` and `agente_scorecards` hold ids and
   counts only. Personal data stays in its home tables (and their RLS/LGPD erasure paths).
4. **Writes via the backend only**: RLS on every 286 table = select own org + service_role.
5. **Pages hidden** until the owner releases them: `status_pagina` rows `atendimento_blocos` and
   `supervisao` seeded `desenvolvimento` (visible to owner/dev/admin through 036's
   `dev_veem_desenvolvimento`; `DEV_ROLES` parity unchanged — no new
   `*_status_pagina_dev_visibility.sql`).
6. **Recording never blocks the flow it observes**: a sink/hook/job failure is logged and never
   undoes a send, a stage move or an accept.

## 6. Slices

| slice | scope | status |
|---|---|---|
| S0 | this contract + README | done |
| S1 | migration 286 + 18 DB guard probes (`_SW_MAYA_BLOCOS_PROBES`, `verify_db_guards.py`) + replay test + structural migration test | done (not applied) |
| S2 | backend: `BLOCOS`/`ETAPAS_PADRAO`/`AGENTES_POR_BLOCO`, derivation, T1 sink, T2 hook + the aceite movimento, `primeira_resposta_at` write, `handoff` event emission, the §4 routes | next |
| S3 | jobs: sweep (assumido/expirado), nightly scorecards, owner report (in-app recipient rule + digest) | after S2 |
| S4 | FE pages `atendimento_blocos` + `supervisao` (built to §4) | parallel with S3 |
| later | `lais_envio_gate.exigir(..., bloco=)` generalization; per-block agents; Maya's LLM review | owner-paced |
