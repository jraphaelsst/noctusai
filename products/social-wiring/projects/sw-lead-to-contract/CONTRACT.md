# SW lead → proposta → contrato — FE↔BE contract

Status: AUTHORED 2026-10-09 by noc-2 (tech-lead). Every slice builds TO this file. A change goes through noc-2 and is announced to every slice owner, never edited unilaterally.
Plan, slices and live-test script: [`PROJECT.md`](PROJECT.md). Paths are relative to `products/social-wiring/`.

Conventions, for every route below:
- Seed envelope `{"data": …}`; auth = the card_hub org-scoped user (same dependency as the existing `/api/clientes/{cliente_id}/…` routes).
- Errors: `400` for a WRONG value, `404` for an unknown/other-org id, `409` for a state conflict (with `{"detail", "code"}`).
- Strict `== 401` without a token (auth tests assert exactly 401).
- New tables get the org-picker RLS shape (mig 211: `_select_own_org` / `_write_own_org` / `_service_role`) and `SELECT public.attach_acting_audit_triggers('social_wiring')` (mig 214).
- No silent fallbacks: a missing input is a reported `faltando`, never a guessed default.

---

## §1 · S1 Intake — the imóvel comes from the campaign

### 1.1 Campaign → imóvel registry (reuse mig 065, do not create new tables)
`campanha_veiculacoes` (`canal='meta_ads'`, `ref_codigo` = the Meta object id) and `campanha_imoveis` already exist and are empty. S1 adds the service, router and UI that fill them:
- `GET /api/campanhas` → `[Campanha]`; `POST /api/campanhas` `{nome, imovel_codigos: [str], veiculacoes: [{canal:'meta_ads', nivel:'campaign'|'adset'|'ad'|'form', ref_codigo}]}`; `PATCH /api/campanhas/{id}`; `DELETE /api/campanhas/{id}` (soft delete).
- `Campanha = {id, nome, imoveis: [{codigo, titulo}], veiculacoes: [{id, canal, nivel, ref_codigo}], created_at}`.
- FE: a "Campanhas" page under Leads (new route `/campanhas`) with CRUD; the imóvel picker reuses the existing imóvel search.

### 1.2 Resolution at intake (`meta_ingest_service`)
Resolution order for a Meta lead, using the first hit:
1. `ad_id` → `campanha_veiculacoes(nivel='ad')`
2. `adset_id` → `nivel='adset'`
3. `campaign_id` → `nivel='campaign'`
4. `form_id` → `nivel='form'`
5. the form's `REF` answer (today's path, kept as the fallback)

A hit links every imóvel of that campanha to the atendimento with `atendimento_imoveis.origem='campanha'` (the `REF` path keeps `origem='lead'`). No hit ⇒ today's `imovel_pendente`. Never guess.

### 1.3 Cliente attached at intake
`ingest_meta_lead` calls `clientes_service.attach_lead_now(client, org_id, lead_row)`, the same synchronous attach the manual "Novo lead" uses, so the card's titular exists before the response returns. The sweep stays as the safety net. The 06:00 `sync_all` path also calls `ingest_meta_lead` for each new row (fixes the "card without a leads row" gap).

### 1.4 Simulation (for the live test, platform staff only)
`POST /api/meta/leadgen/simular` with body `{ad_id?, adset_id?, campaign_id?, form_id?, nome, telefone?, email?, respostas?: {REF?: str, …}}`. It runs the SAME `upsert_lead` → `ingest_meta_lead` path as the webhook after signature verification, skipping only the Graph fetch. The stored row is marked `meta_ads_leads.simulado = true` (new boolean, default false) and the timeline shows "Lead simulado".

- Guard: `require_platform_staff`, else `403` `code="not_platform_staff"`.
- Response: `{meta_lead_id, lead_id, atendimento_id, cliente_id, imoveis: [{codigo, origem}]}`.
- Mirror as MCP tool `meta.leadgen.simulate` (like `imovelweb.webhook.simulate`).

---

## §2 · S2 Conversation + documents

### 2.1 Chat ↔ card link
`whatsapp_chats.cliente_id uuid NULL` (FK `clientes` ON DELETE SET NULL). It is resolved and stored on the inbound webhook (the phone matched against `clientes.chave_canonica`, same rule as `_nomear_pelos_clientes`) and also when a cliente is created or merged.

- `GET /api/clientes/{cliente_id}/conversa` → `{chat_id|null, connection_id|null, mensagens: [Mensagem] (last 50)}`
- `Mensagem = {id, direcao:'in'|'out', texto, enviada_em, anexo: {mime, nome, documento_id|null}|null}`

### 2.2 "Pedir documentos"
`POST /api/clientes/{cliente_id}/conversa/pedir-documentos` with body `{texto?: str}`. When `texto` is omitted, the text is built from the person's PENDING checklist items (`documento_checklist_service`), e.g. "Olá {primeiro_nome}, para seguirmos precisamos de: RG ou CNH ou CIN, CPF, comprovante de endereço…".

- Sends through the card's chat connection, and records an outbound `Mensagem` plus a timeline event `documentos_solicitados`.
- Response: `{mensagem_id, itens_solicitados: [str]}`.
- `409` `code="sem_conversa"` when the cliente has no chat and no phone.
- FE: a "Pedir documentos" button in the card's conversation panel and next to the checklist.

### 2.3 Inbound media → cliente_documentos
On an inbound message with `hasMedia` whose chat has a `cliente_id`, the new `documento_intake_service`:
1. downloads the media;
2. stores it like a card upload;
3. classifies the type with `identidade_extracao_service.classificar_tipo_provavel` (now used as the classifier, not only as a warning);
4. inserts `cliente_documentos` with `origem_entrada='whatsapp'`, the classified `tipo_documento` and the classifier confidence;
5. runs extraction exactly as a card upload does.

Low confidence or an unknown type ⇒ `tipo_documento='a_classificar'`. The doc shows in a triage list on the card, where the operator picks the type, and extraction then runs. Media is never dropped.

Accepted MIME types gain `image/heic` (converted to JPEG on ingest).

- Message bubble: `anexo.documento_id` links to the stored doc.
- Simulation for the live test: a real message from a test phone to the connected number. No forged webhook.

---

## §3 · S3 Roteiro, "visita aconteceu?" and metrics

### 3.1 Data (mig 219)
- `visitas.nao_realizada_motivo text NULL`, checked against `('cliente_desistiu','cliente_nao_compareceu','imovel_indisponivel','reagendada','outro')`.
- `visitas.realizada_em timestamptz NULL` (set when the status becomes `realizada`).
- `roteiros.feedback_status text NOT NULL DEFAULT 'pendente'`, checked against `('pendente','respondido')`, and `roteiros.feedback_em timestamptz`.
- `roteiros.hora_visita time NULL` (optional; `data_visita` stays the DATE).

### 3.2 The prompt
- A roteiro is **due** when `data_visita <= today` (plus `hora_visita` when set) and `feedback_status='pendente'`.
- `GET /api/roteiros/pendentes-feedback` → `[{roteiro_id, cliente_id, atendimento_id, cliente_nome, data_visita, visitas: [{visita_id, imovel_codigo, titulo}]}]`. Used for the header badge and the painel list.
- A daily scheduler job notifies the atendimento's corretor ("Visita de {cliente} aconteceu?"), deep-linking to the card's Roteiros tab.
- The card shows a `VisitaFeedbackPrompt` banner on the roteiro while it is due.

### 3.3 Answering
`POST /api/clientes/{cliente_id}/roteiros/{roteiro_id}/feedback` with body:
```json
{"aconteceu": true|false,
 "visitas": [{"visita_id": "uuid", "realizada": true|false, "motivo": "…|null", "observacao": "str|null"}]}
```
- `aconteceu=false` with empty `visitas` ⇒ every visita becomes `nao_realizada` with motivo `outro` unless one is given.
- `aconteceu=true` requires every visita to be listed. A `realizada=false` entry requires a `motivo`, else `400`.
- Sets `feedback_status='respondido'` and emits timeline events.
- Response: the updated `Roteiro`.
- The existing per-visita PATCH stays (corrections).

### 3.4 Visited list (feeds "Gerar proposta")
`GET /api/clientes/{cliente_id}/roteiros/{roteiro_id}/visitadas` → `[{visita_id, imovel_codigo, titulo, realizada_em, proposta: {id, status}|null}]`. FE: on a `respondido` roteiro, `RoteirosSection` lists these with a **"Gerar proposta"** button each. The button calls §4.2 and is disabled with "Proposta já criada" when `proposta` is set.

The old "Proposta enviada / aceita" toggle pills are REMOVED from the FE. Their columns are written only by §4's orchestration (§4.4), which keeps a single acceptance path.

### 3.5 Metrics
`GET /api/metricas/atendimentos?de=&ate=&corretor_id=` → `{leads, com_roteiro, visitas_agendadas, visitas_realizadas, visitas_nao_realizadas: {motivo: n}, propostas_criadas, propostas_aceitas, propostas_recusadas, tempo_medio_dias: {lead_a_roteiro, roteiro_a_visita, visita_a_proposta, proposta_a_aceite}}`.
- Computed from rows plus timeline timestamps; no stored counters.
- FE: a "Funil de atendimento" card on the Painel.

---

## §4 · S4 Proposta

### 4.1 Data model (mig 217)

**Reasoning.** A proposta is an **offer snapshot**. An atendimento can have several at once (competing imóveis, counter-offers), and each must keep its terms even after another one is accepted. The contract generator, on the other hand, reads ONE live negotiation set keyed by `atendimento_id` (`atendimento_negociacao` + `_termos` + `_parcelas` + `_favorecidos` + `_intermediarios`), and that set is well tested.

Duplicating those five tables per proposta would fork the negotiation model, and re-pointing the generator at propostas would rewrite its loader. So:
- each proposta stores its terms as **validated JSON snapshots**, using the SAME Pydantic shapes `negociacao_estruturada_service` already validates;
- **Aceitar materializes** the chosen snapshot into the live set through the existing writers (same validation, same FK handling).

The generator stays single-source and unchanged.

`social_wiring.atendimento_propostas`:

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid pk` | |
| `org_id` | `uuid not null` | |
| `atendimento_id` | `uuid not null` | FK `atendimentos` ON DELETE CASCADE |
| `cliente_id` | `uuid not null` | |
| `visita_id` | `uuid null` | FK `visitas` ON DELETE SET NULL |
| `imovel_codigo` | `text not null` | |
| `status` | `text not null default 'rascunho'` | check `('rascunho','enviada','aceita','recusada','cancelada')` |
| `valor_proposto` | `numeric(14,2) null` | check `>0` |
| `pct_comissao` | `numeric null` | |
| `financiamento` | `bool null` | |
| `fgts` | `bool null` | |
| `validade_ate` | `date null` | |
| `observacoes` | `text null` | |
| `parcelas` | `jsonb not null default '[]'` | `[ParcelaIn]` shape of mig 108/192 |
| `favorecidos` | `jsonb not null default '[]'` | `[FavorecidoIn]` |
| `intermediarios` | `jsonb not null default '[]'` | `[IntermediarioIn]` |
| `termos` | `jsonb not null default '{}'` | `TermosIn`: posse, ad_corpus, itens_integrantes, ônus, confissão, corretagem, clausulas_extras, posse_multa_diaria |
| `imobiliaria_id` | `uuid null` | FK `org_imobiliarias` |
| `testemunha_ids` | `uuid[] not null default '{}'` | |
| `enviada_em` | `timestamptz` | |
| `aceita_em` / `aceita_por` | | |
| `recusada_em` / `recusada_por` | | |
| `motivo_recusa` | `text` | |
| `contrato_id` | `uuid null` | FK `atendimento_contratos`, set on accept |
| `created_at` / `created_por` / `updated_at` / `updated_por` | | |

Constraints and indexes:
- Partial unique: one `status='aceita'` per `atendimento_id`.
- Index on `(atendimento_id)`.
- Parcela `favorecido_ref` inside the JSON is a client-side key (`"fav:0"`), resolved to real ids on materialize.

### 4.2 Routes (prefix `/api/clientes/{cliente_id}/propostas`)
- `GET ""` → `[Proposta]` for the card's atendimento, newest first.
- `POST ""`, body `{visita_id?: uuid, imovel_codigo?: str}` (one of the two is required).
  - Creates a `rascunho` **prefilled** with `imovel_codigo` (from the visita), `valor_proposto` = the imóvel's asking price when known, `pct_comissao` from `atendimento_negociacao` or the org default, and `imobiliaria_id` when exactly one is active.
  - With a `visita_id`, also stamps `visitas.proposta_em` (replaces the old toggle).
  - `409` `code="visita_nao_realizada"` when the visita isn't `realizada`.
  - Emits funnel event `proposta_criada` (§6).
- `GET "/{id}"` → `Proposta`.
- `PATCH "/{id}"`, partial body with any editable field. `409` `code="proposta_fechada"` when the status is `aceita`, `recusada` or `cancelada`.
- `POST "/{id}/enviar"` → status `enviada`, `enviada_em`.
- `POST "/{id}/recusar"`, body `{motivo: str}` (required) → `recusada`.
- `POST "/{id}/aceitar"`, body `{}` → see §4.4. Response `{proposta: Proposta, contrato_id, geracao: {pronto, faltando, bloqueios, avisos}}`.
- `DELETE "/{id}"`: only `rascunho` (else `409`); a hard delete is fine for a never-sent draft.

`Proposta` = every column above, plus `imovel: {codigo, titulo, endereco}`, `visita: {id, data_visita}|null`, `imobiliaria: {id, razao_social}|null`, `testemunhas: [{id, nome}]`, `saldo_nao_alocado` (= `valor_proposto` − Σ parcelas), and `completude: [str]` (what the contract would still lack: reported, never blocking a save).

### 4.3 FE
**Geral tab.** New `renderPropostas` slot right after `AtendimentoImoveisSection`. It shows `PropostaCard` items: imóvel, valor, status badge, validade. A click opens the modal.

**`PropostaModal`**, with full CRUD:
- header: imóvel, status;
- sections: Valores (valor, comissão, financiamento/FGTS, validade), Parcelas (add/edit/remove rows, live `saldo_nao_alocado`), Favorecidos, Intermediários, Termos, Contrato (imobiliária select from `/api/settings/imobiliarias`, testemunhas multi-select);
- footer: Salvar · Enviar · **Recusar** (asks for the motivo) · **Aceitar** (confirm dialog that lists `completude`) · Excluir (rascunho only).

**After Aceitar**: toast, then navigate to the Contratos tab with the new draft open.

Loading states follow the two-signal rule (`showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`).

### 4.4 Aceitar: the one acceptance path
All refusals happen BEFORE the first write (card_hub has no transactions):
1. The proposta is `rascunho` or `enviada`; no other proposta of the atendimento is `aceita`.
2. `atendimento_negociacao.imovel_codigo` is NULL or equals this one (same rule as `registrar_proposta`).
3. The snapshot validates against the live-set Pydantic models. Else `400` with the field paths.

Then, in order:
1. **Materialize.** Replace the atendimento's live negotiation set from the snapshot via `negociacao_estruturada_service` writers (parcelas, favorecidos, intermediários, termos), set `valor_negociado`, `pct_comissao` and `imovel_codigo`, and remap `favorecido_ref` and `posse_marco_parcela_ref` to the new ids.
2. If the proposta came from a visita, stamp `visitas.proposta_aceita_em`.
3. Call `contrato_gerador.service.iniciar`. Set the contract's `imobiliaria_id` and testemunhas from the proposta. Store `contrato_id`.
4. Set `status='aceita'`.
5. Emit funnel event `proposta_aceita` (§6).

On a failure after step 1, report it with the exact step and leave the proposta `enviada`. Every step is idempotent, so retrying Aceitar is safe.

---

## §5 · S4 ↔ funnel (decisions pending)
- 5.1 Other open propostas of the atendimento on accept: **unchanged** until owner Q2.
- 5.2 Recusar never moves the stage.
- 5.3 Cancelling an accepted proposta is out of scope for the skeleton (`409`).
- 5.4 Accept closes into `processos_venda` (stage `elaboracao_contrato`) using the existing `aceitar-proposta` logic, refactored into a callable `pipeline.aceitar_proposta(atendimento_id, actor)` that both the old button and §4.4 use. The stage precondition (`papel='proposta_aceite'`) is satisfied by moving there first via §6. Pending owner Q1.

---

## §6 · Funnel coherence: `pipeline/funil_eventos.py` (owned by S3, imported by S1/S4)
`mover_por_evento(client, org_id, atendimento_id, evento, actor) -> {moveu: bool, de, para, motivo}` maps events to stage `chave`s:

| Evento | Moves to (only FORWARD; never backwards, never over a later stage) |
|---|---|
| `lead_criado` | `qualificacao` (spawn already does it; no-op) |
| `roteiro_criado` | `visitas` |
| `proposta_criada` | `proposta_recebida` |
| `proposta_aceita` | `proposta_decisao`, then `pipeline.aceitar_proposta` (§5.4) |

- Uses `mover_atendimento` internally, so `stage_gate` still applies.
- When the gate refuses, return `moveu=false` with the `pendencias` as `motivo`; the caller surfaces it, never raises.
- An org that renamed or removed a stage `chave` gets `moveu=false, motivo='etapa_inexistente'` (no silent skip).
- Every move writes a timeline event `etapa_auto` carrying the evento.
