# SW lead → proposta → contrato — FE↔BE contract

Status: AUTHORED 2026-10-09 by noc-2 (tech-lead). Every slice builds TO this file. A change goes through noc-2 and is announced to every slice owner, never edited unilaterally.
Plan, slices and live-test script: [`PROJECT.md`](PROJECT.md). Paths are relative to `products/social-wiring/`.

Conventions, for every route below:
- Seed envelope `{"data": …}`; auth = the card_hub org-scoped user (same dependency as the existing `/api/clientes/{cliente_id}/…` routes).
- Errors use the SEED envelope (`AppException` → `{"error": {"code", "message", "details"}}`, read on the FE through the seed `ApiError` `code` / `details` / `extractErrorMessage`): `400` for a WRONG value, `404` for an unknown/other-org id, `409` for a state conflict. Never a flat `{detail, code}` body.
- Migrations: no pre-assigned numbers. Each slice takes `noctus.dev.next_migration_number` when it writes the file; `task_branch integrate` blocks on a collision.
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

### 3.1 Data (migration: next free number)
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

### 4.1 Data model (migration: next free number)

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
- `POST "/{id}/aceitar"`, body `{}` → see §4.4. Response `{proposta: Proposta, contrato_id, geracao: {pronto, faltando, bloqueios, avisos}, passos: [{passo: 'materializar'|'visita'|'contrato'|'status'|'funil'|'pos_aceite', status: 'ok'|'erro'|'pulado', mensagem: str|null}], pos_aceite: PosAceite}`.
- `POST "/{id}/pos-aceite"` → `PosAceite` (§7.3); re-runs §7, idempotent.
- Refusals (409 codes): `proposta_fechada`, `proposta_ja_aceita`, `imovel_divergente`, `visita_nao_realizada`, `proposta_nao_aceita`. Snapshot validation: 400 `snapshot_invalido` with `details.campos = [{path: 'parcelas.0.valor', mensagem}]`.
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
5. Emit funnel event `proposta_aceita` (§6). This step only calls `mover_por_evento`; the mover itself calls `pipeline.aceite.aceitar_proposta` (§6), so there is ONE caller.
6. `pos_aceite_service.disparar` (§7). Imported lazily: a missing module reports `status:'erro', mensagem:'módulo indisponível'` in `passos`, and the accept still stands.

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
| `proposta_aceita` | `proposta_decisao`, then `app.modules.pipeline.aceite.aceitar_proposta(client, org_id, atendimento_id, actor_id) -> {processo, already_accepted}` (§5.4; `boards.py`'s route becomes a thin wrapper over the same function) |

- Uses `mover_atendimento` internally, so `stage_gate` still applies.
- When the gate refuses, return `moveu=false` with the `pendencias` as `motivo`; the caller surfaces it, never raises.
- An org that renamed or removed a stage `chave` gets `moveu=false, motivo='etapa_inexistente'` (no silent skip).
- Every move writes a timeline event `etapa_auto` carrying the evento.

---

## §7 · S5 Post-aceite automation: certidões + matrícula (owner 2026-10-09)

Owner: "the certidões emissions and data extraction, the matrícula extraction, both automated right after the aceite de proposta. It runs for all vendedores and their companies, just like we talked about in other sessions." Standing owner rules, not re-litigated: memory `project_sw_owner_decisions_2026_10_05`, `project_contract_automation`.

New module `backend/app/modules/card_hub/pos_aceite_service.py`, entry point `disparar(client, org_id, atendimento_id, actor) -> PosAceite`. §4.4 calls it as **step 6**, after the funnel event. Its failure never undoes the accept: it is reported in the Aceitar response and is re-runnable.

### 7.1 Certidões
**Who is a vendedor (owner 2026-10-09):** the owners registered on the imóvel (`imovel_proprietarios` and the vendedor partes of the atendimento) **plus ALL their cônjuges**, whether co-owner or anuente, and whether registered now or added later as a new cliente linked by the casamento (`clientes.conjuge_cliente_id`). This SUPERSEDES the 2026-10-05 rule "anuente spouse gets no certidões". For each of them, PF and PJ, plus every derived `EMP n` company, call `certidoes_partes_service.solicitar_emissao(kind, alvo_id, tipos=None, …)`, i.e. every AUTOMATIC tipo. Manual-upload tipos (TJSP e-SAJ/e-PROC, Serasa) become checklist cells, never fake emissions.
- **Spouse added after the aceite:** linking a cônjuge to an owner of an atendimento whose proposta is `aceita` triggers `disparar` for that atendimento (hook in the cônjuge-link write path), so a late spouse is certified when added, not only at Aceitar.
- **Skip** any party that already has a non-stale certidão for every automatic tipo or a consulta still in flight (idempotent: re-running emits only what's missing or stale; staleness = the contract gate's own predicate).
- **Antigos proprietários** (seller's purchase < 5 years): already emitted automatically once the matrícula is on the card (`antigos_proprietarios_service`). S5 only makes sure that runs after 7.2, never duplicating it.
- Credentials pre-flight failure (no InfoSimples key) ⇒ `status='bloqueado', motivo='credenciais'` for the whole step, before any billed request.
- Emissions are billed InfoSimples requests. The response lists each one so the cost is visible.

### 7.2 Matrícula
For the accepted proposta's `imovel_codigo`:
- **A matrícula document on file:** ensure its extraction + autopilot ran (`matriculas` extraction → `autopiloto_service._aplicar_autopiloto`), re-running when the document is newer than the last extraction. That yields título aquisitivo, ônus, antigos proprietários (which triggers their certidões, 7.1).
- **None on file:** `status='faltando', motivo='matricula_ausente'`, plus a checklist pendência "Certidão de matrícula atualizada" on the imóvel. 🔴 The repo has **no automatic matrícula emission** today (no ARISP/ONR/InfoSimples matrícula integration): owner question Q5 in PROJECT.md. Until answered, the matrícula is uploaded, and its extraction then runs automatically on upload.

### 7.3 Response + UI
`PosAceite = {certidoes: [{parte_nome, kind, alvo_id, consulta_id|null, status:'emitindo'|'ja_valida'|'pulada'|'bloqueado'|'erro', motivo|null, tipos:[str]}], matricula: {status:'extraindo'|'ok'|'faltando'|'erro', documento_id|null, motivo|null}}`
- It is returned inside the Aceitar response (`pos_aceite`).
- `POST /api/clientes/{cliente_id}/propostas/{id}/pos-aceite` re-runs it (idempotent).
- FE: after Aceitar, a "Preparando contrato" panel lists these statuses, with links to the Certidões tab (vendedores | antigos proprietários subtabs) and the imóvel page. Each certidão result is extracted by the existing certidões readers when it lands, and the generator's `geracao` readiness reflects them.

### 7.4 Next phase seam (owner's main goal, not built now)
Every extraction here goes through ONE interface per document type (`tipo → extractor`), so each type's reader can be replaced by a dedicated, rule-based parser one at a time in the next phase, without touching the orchestration. See memory `project_sw_reliable_contract_generation_goal`. S2's inbound-media classifier routes through that SAME interface (§2.3).

---

## §8 · S6 Cadastrar imóvel — manual captação (owner 2026-10-09)

Owner: "a way to register properties, as if my agents go inside the platform to register new captações. They click a button and a modal opens with imovel data editable for new registrations." Option (b): a first-class manual imóvel, never a Vista re-listing. Plus the deal's Drive folder and process number reachable from the imóvel, "so we can access it easily without fetching from Vista". Unblocks the live test: deal 876's imóvel (Al. Liverpool 81, Reserva do Vianna) left the Vista catalog.

### 8.1 Where the data lives (and where it must NOT)
- `imoveis` is the Vista MIRROR, a disposable cache (mig 063 header). **No manual row is ever written there.** That avoids three concrete hazards: `_last_sync_at` orders `sincronizado_em DESC` with NULLs first (a NULL makes the org look overdue, forcing a perpetual re-sync); `sweep_imovel_registry` would flip a manual row's activity; and a later Vista código collision would overwrite the row through the upsert on `(org_id, codigo)`.
- `imovel_registry` is the permanent identity every table FKs to. A manual imóvel gets a registry row with `origem_descoberta='manual'`, `ativo_no_vista=false`. That row already exists today: `dados_service.registrar_imovel(origem="manual")`, `POST /api/imoveis/{codigo}/registrar`, the picker's "cadastrar novo". **Extend that path; never fork it.**
- **New table `social_wiring.imovel_captacao`** holds the listing data that only a manual imóvel has. PK `(org_id, codigo_canonical)`, FK → `imovel_registry(org_id, codigo_canonical)`. Column names are IDENTICAL to `imoveis` so one serializer serves both: `titulo text NOT NULL`, `categoria`, `status` (finalidade: "Venda" | "Aluguel" | "Venda e Aluguel", free text like the mirror), `finalidades text[]`, `valor_venda`, `valor_locacao`, `valor_condominio`, `valor_iptu` (numeric(14,2), >0 when set), `area_total`, `area_privativa`, `area_construida` (>0), `dormitorios`, `suites`, `vagas` (>=0), `descricao_web`, `observacoes`, `created_at/created_por/updated_at/updated_por`.
- **Reused on `imovel_dados`, never duplicated:** address `endereco_manual_{cep,logradouro,numero,complemento,bairro,cidade,uf}` (149/159), `empreendimento_manual` (158), `em_condominio` (202).
- **Deal refs on `imovel_dados`** (authored data, valid for ANY imóvel, Vista or manual): `drive_folder_url text` (https://drive.google.com/… folder only) and `drive_folder_id text` (derived from the URL `…/folders/<id>`, never typed). The folder belongs to the imóvel. Also `processo_atual_numero text`, named and documented as the CURRENT deal's number (architect review 2026-10-09): an imóvel can be sold or rented more than once, so this is a convenience pointer to today's deal, not the deal's identity. Deals live in `processos_venda`.
- RLS: org-picker shape (mig 211) on `imovel_captacao` + `attach_acting_audit_triggers('social_wiring')`. Migration: next free number at write time.

### 8.2 Código
- Generated, never typed, already uppercase (`busca_service.canonical` = `strip().upper()`): `SW-` + 4-digit sequence per org (`SW-0001`, …; grows past 9999 unpadded). The hyphen never appears in Vista shapes (`ONE\d+`, `CA\d+`, `AP\d+`), so no collision. Next = max existing `SW-n` in the org's registry + 1, with a retry on the registry unique `(org_id, codigo_canonical)`.
- **One write path** (architect): `dados_service.registrar_imovel(origem="manual")` is EXTENDED to also write the captação (and deal refs). `POST /manuais` is a thin route over it; there is no second registration implementation.
- The existing typed-código registration (the picker's "cadastrar novo") stays as is. The two coexist.

### 8.3 Routes (prefix `/api/imoveis`, bare JSON, seed error envelope `{"error":{code,message,details?}}`, strict `== 401`)
- `POST /manuais`, body `ImovelManualIn` → `201 Imovel`.
  - `ImovelManualIn` (StrictHttpModel): `titulo` (required), `categoria`, `status`, `finalidades`, the valores/áreas/cômodos above, `descricao_web`, `observacoes`, `endereco: {cep, logradouro*, numero*, complemento, bairro*, cidade*, uf*}` (* = required, same rule as 159), `empreendimento`, `em_condominio`, `processo_atual_numero`, `drive_folder_url`.
  - Writes registry (manual) + captação + imovel_dados in that order. A failure after the registry row is reported, never swallowed, and a retry with the returned código converges.
- `PATCH /manuais/{codigo}`, partial `ImovelManualPatch` → `200 Imovel`. `409 imovel_vista_somente_leitura` when the código is not manual; `404` unknown/other org.
- `PATCH /{codigo}/referencias`, body `{processo_atual_numero?: str|null, drive_folder_url?: str|null}` → `200 {processo_atual_numero, drive_folder_url, drive_folder_id}`. Any imóvel (Vista or manual). `400 drive_url_invalida` for a non-Drive-folder URL.
- `GET /{codigo}` (existing details): for a manual código, returns the SAME `Imovel` shape built from captação + imovel_dados (no more mirror 404 → reduced layout), with `fonte: "manual"`. Vista ones get `fonte: "vista"`. Both carry `referencias: {processo_atual_numero, drive_folder_url, drive_folder_id}`.
- `GET ""` (list): reads a new view `social_wiring.imoveis_catalogo` (`security_invoker = true`, so RLS applies) = `SELECT …, 'vista' AS fonte FROM imoveis UNION ALL SELECT …, 'manual' AS fonte FROM imovel_captacao JOIN imovel_dados` (the manual branch maps `endereco_manual_*` → the mirror's address columns, `updated_at` → `data_atualizacao`, `caracteristicas` → `'{}'`). The list stays ONE PostgREST query, so filters, `count=exact`, order and pages stay exact (architect: never merge in Python).
- `GET /busca`: manual imóveis match the same text filters (código, título, bairro, empreendimento, logradouro), with `fonte: "manual"`. `busca_service.enriquecer` falls back mirror → captação + imovel_dados → registry `snap_*`, so every consumer (lead form, campanhas, atendimento imóveis, roteiro, propostas) renders a manual imóvel's title and address.
- Sync: `ImovelSyncService.sync` and `sweep_imovel_registry` never touch a manual registry row or `imovel_captacao`. A test runs a full sync + sweep and asserts that.

### 8.4 FE
- `/imoveis`: a **"Cadastrar imóvel"** button opens `ImovelManualModal`, built from `@noctusai/lib` canonical form/modal organs (check `noctus.dev.find_reusable_component` first, no local re-implementation). Every field is editable, grouped as Identificação · Endereço · Valores · Áreas e cômodos · Descrição · Referências do negócio (processo, pasta do Drive). Creating it puts the new imóvel in the list/search immediately (invalidate `["sw","imoveis"]` AND `["sw","cardHub","imoveisBusca"]`).
- Details page: a manual imóvel renders the full layout with an **"Editar"** button opening the same modal. Vista ones stay read-only as today (EditPlaceholderButton). EVERY imóvel shows a "Referências do negócio" card (processo + "Abrir pasta no Drive" link, editable).
- Loading states per the two-signal rule.

### 8.5 First real use
noc-2 registers Al. Liverpool 81 (Reserva do Vianna), processo atual `876`, Drive https://drive.google.com/drive/folders/1vfD3HHF7jN8EiMwhcHkKYrvuxz5GDlEK, through the UI.

### 8.6 Possível duplicado (owner 2026-10-09: "build it this run please")
A manual imóvel (SW-####) and a Vista listing may be the same property. This section is **detect, surface, dismiss**. They are **never** merged automatically.

**Data.** `social_wiring.imovel_duplicata_candidatos`:

| Column | Notes |
|---|---|
| `id uuid pk`, `org_id` | |
| `codigo_manual`, `codigo_vista` | canonical códigos, each FK → `imovel_registry(org_id, codigo_canonical)`; UNIQUE `(org_id, codigo_manual, codigo_vista)` |
| `score numeric(4,3)` | 0..1 |
| `sinais jsonb` | `[{sinal, detalhe}]`, sinal ∈ `matricula_cri` \| `matricula` \| `endereco` \| `empreendimento_area_preco` |
| `status text` | `pendente` \| `descartado` \| `confirmado` (`confirmado` is reserved for the §8.7 action; nothing sets it yet) |
| `detectado_em`, `atualizado_em`, `resolvido_por`, `resolvido_em` | |

Org-picker RLS plus acting-audit, same as every table in this contract.

**Detection.** One function, `duplicatas_service.detectar(client, org_id, codigos_manuais=None)`, compares each manual imóvel against the Vista catalog (signals, strongest first):

| Signal | Match | Score |
|---|---|---|
| `matricula_cri` | same `imovel_dados.numero_matricula` (digits only) AND same `numero_registro_imoveis` | 0.95 |
| `matricula` | same matrícula, CRI unknown on one side (also against the mirror's `matricula_vista`) | 0.80 |
| `endereco` | same normalized logradouro (unaccented, lowercased, type prefix "rua/r./avenida/av./alameda/al." stripped) + same número + (same CEP digits OR same normalized bairro) | 0.70 |
| `empreendimento_area_preco` | same normalized empreendimento + área (total or privativa) within ±5% + price within ±10% | 0.50 |

- The score is the highest signal plus 0.05 for each other signal that matched, capped at 0.99. A pair is recorded at ≥ 0.50.
- Re-detection updates `score`/`sinais`/`atualizado_em` on `pendente` rows. It **never resurrects a `descartado` pair**. That pair is never suggested again, even if its signals change.
- Runs after a complete Vista sync, as a separate step whose failure is logged loudly and never fails the sync. It also runs after a manual create/edit (for that código only).

**Routes** (prefix `/api/imoveis`, bare JSON, seed error envelope, strict `== 401`):
- `GET /duplicatas?status=pendente` returns `[{id, score, sinais, status, detectado_em, manual: ImovelResumo, vista: ImovelResumo}]`, highest score first. `ImovelResumo = {codigo, titulo, endereco_resumo, valor_venda, area_total, foto_destaque}`.
- `POST /duplicatas/{id}/descartar` → `200` pair with status `descartado` (+ resolvido_por/em). `409 duplicata_ja_resolvida` if the pair is not pendente.
- `GET /{codigo}` (Imovel) gains `duplicatas_pendentes: [{id, outro_codigo, score}]`, on both the manual and the Vista side.
- List: the `imoveis_catalogo` view gains `possivel_duplicado boolean` (EXISTS a pendente pair involving the código) and `GET ""` accepts `possivel_duplicado=true`.

**FE.**
- A "Possível duplicado" badge on list cards and the details header.
- On the details page, a section listing the candidate pairs (side by side: código, título, endereço, valor, área, the matched signals) with **"Não é o mesmo"**.
- A "Possíveis duplicados" filter on /imoveis.
- "É o mesmo imóvel" is NOT shown until §8.7 is approved and built.

### 8.7 "É o mesmo imóvel" (PROPOSED, not built; for noc-2's review)
Proposed action: **LINK, don't move.**

- **Mechanism.** `imovel_registry` gains `vinculado_a uuid NULL` (FK → registry.id, the Vista row). Confirming a pair:
  - sets `vinculado_a` on the manual registry row;
  - sets the pair to `confirmado`;
  - writes a timeline/audit row.
  - The manual código stays a valid, stable identity. **No FK in the 12+ referencing tables is rewritten**, so every atendimento_imoveis / interesses / visitas / propostas / documentos / negociação row keeps pointing where it did. Nothing is re-pointed silently, and nothing can be half-moved.
- **Resolution.** `busca_service.enriquecer` and `GET /{codigo}` resolve a linked manual código to the Vista listing's catalog data (title, photos, price, specs) while keeping the manual record's OWN authored data (deal refs, Drive folder, matrícula, documents, address override), shown as "Cadastro manual vinculado a ONE1234".
- **Display.**
  - New associations: the picker hides the linked manual entry and shows the Vista one with a "vinculado a SW-0001" hint, so new leads/campaigns attach to the canonical Vista código.
  - Old rows keep the SW código, which renders the same data through the link.
  - Reports that group by imóvel group by `coalesce(vinculado_a → codigo, codigo)`.
- **Reversible.** "Desvincular" clears `vinculado_a` and returns the pair to `pendente`. Because nothing was moved, unlinking is exact.
- **Explicitly not proposed.** Re-pointing FKs from SW-#### to the Vista código is lossy (two rows can collide on per-imóvel uniques like `imovel_dados` PK and `atendimento_imoveis` uniques), not cleanly reversible, and touches every table at once without a transaction.
