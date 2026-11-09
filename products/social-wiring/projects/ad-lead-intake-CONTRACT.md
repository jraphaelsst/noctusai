# CONTRACT — ad-lead intake (Meta form lead -> property, both ways)

Status: backend built on `feat/sw-ad-lead-intake` (migration 331). Not deployed. Scope = Meta lead-form leads only
(NOT click-to-WhatsApp). Roteiros and corretor performance are a LATER slice; this contract only lays their base
(`imovel_corretores`, `lead_corretor_divergencias`).

Owner goal: for every new Meta lead-form lead — lead created -> the ad's property code (REF) fetched on Vista -> OUR property row
created OR updated (fetched and compared even when it already exists) -> lead <-> property linked both ways (many-to-many) ->
corretor recorded and warned on divergence. Notification of the new lead itself is out of scope (the existing `lead_novo` notice
stays as is).

## 1. Pipeline (one lead)

`ingest_meta_lead` (existing) creates `leads` + card + cliente, then calls `ad_lead_intake_service.tentar_intake(client, org_id, lead_id)`
(never raises). The public function is `intake_imovel_do_lead(client, org_id, lead_id, codigo=None, *, adapter=None, adapter_factory=None)`
(`..._async` twin). Steps, in order, each idempotent (read-then-write or NULL-only):

| # | Step | Writes |
|---|------|--------|
| 0 | Code = `codigo` arg, else `leads.codigo_imovel`, else the Meta row's `codigo_imovel` / answer `REF`; canonical = trim+upper. None => status `sem_codigo` (qualification still mapped). | — |
| 1 | `dados_service.registrar_imovel(origem='lead')` — the registry identity exists before anything links to it. | `imovel_registry` (insert if new) |
| 2 | `ImovelSyncService.refresh_codigo` — ALWAYS fetches `/imoveis/detalhes` (no `data_atualizacao` short-circuit), upserts the Vista columns, reactivates the registry row, runs `vista_divergencias` (flag per org), returns `mudancas` (`{coluna: {antes, depois}}`, mirror vs Vista) and the divergence rows opened. Per-org credential only (`vista_credenciais.adapter_da_org`). Shared internals with `sync_detalhes`: `buscar_detalhe`, `gravar_imoveis`, `_mesclar_com_espelho`. | `imoveis`, `imovel_registry`, `imovel_campo_conflitos` |
| 3 | `leads.imovel_ref_id := imovel_registry.id` (G1); `leads.qualificacao_form := mapped answers` (G5, § 2). | `leads` |
| 4 | `atendimento_imoveis_service.vincular_lead(codigo=canonical)`: card link `origem='lead'` + cliente interesse carrying `lead_id` AND `meta_ads_lead_id` (G2); an interesse written earlier by the old ingest gets its NULL `lead_id` filled (`interesses_service.preencher_ids_do_lead`). A soft-deleted interesse stays removed. | `atendimento_imoveis`, `cliente_imovel_interesses` |
| 5 | Property corretores -> `imovel_corretores` (key = Vista corretor `Codigo`); the lead's corretor vs the property's -> `lead_corretor_divergencias` + ONE in-app warning to the org owners/admins (`lead_notice.avisar_corretor_divergente`, kind `lead_corretor_divergente`). | `imovel_corretores`, `lead_corretor_divergencias`, `lead_corretores.vista_codigo` |
| 6 | Outcome persisted. | `lead_imovel_intakes` |

Intake `status` (`lead_imovel_intakes.status`): `ok` · `imovel_nao_encontrado` (Vista answered not-found/unpublished; links still written,
nothing invented) · `sem_codigo` · `pendente_retry` (Vista not configured / down / transport error / a step failed; retryable) · `falhou`
(`pendente_retry` after 5 attempts; still retryable by hand). Vista unavailable NEVER blocks the lead and is never a silent skip: the row
carries `ultimo_erro`, and `retomar` = `POST /api/leads/ad-intake/lead/{id}/retry` or the backfill with `modo=pendentes`.
Steps 3–5 run even when Vista failed (corretores then come from the mirror's `imoveis.corretores`, `resultado.corretores.fonte='espelho'`).

## 2. Field mapping

### 2.1 Form -> lead (`meta_form_aliases`, `meta_ingest_service.map_meta_lead_to_lead_payload`, `leads_sync_service.upsert_lead`)

| Form answer (as seen) | Goes to |
|---|---|
| `REF` | `leads.codigo_imovel` / `meta_ads_leads.codigo_imovel` (existing, owner decision D1) |
| `Nome completo` \| `full_name` \| `nome` | `leads.cliente_nome` (typed promotion first, alias only fills a gap) |
| `Email` \| `email` | `leads.contato` fallback |
| `Telefone` \| `phone_number` \| `phone` \| `celular` \| `whatsapp` \| `fone` (form drift) | `meta_ads_leads.phone` (E.164) -> `leads.contato`. **Fix:** `phone_number` with no PHONE type in the form schema used to leave the phone NULL. |
| "Até qual valor você pretende investir?" (budget; keywords investir/orçamento/faixa) | `leads.qualificacao_form.orcamento_texto` + `orcamento_max` (largest BRL amount in the text: `R$ 1.500.000`, `1,5 milhão`, `500 mil a 800 mil`; numbers < 1000 without a suffix are not money) |
| "…em qual fase da compra você se encontra?" (fase/momento/estágio) | `qualificacao_form.fase_compra_texto` |
| "Você está buscando um imóvel na Granja Viana?" (região/bairro/…) | `qualificacao_form.regiao_interesse = {pergunta, resposta, confirmou: true\|false\|null}` |

`qualificacao_form` (jsonb on `leads`) is the SW-side structured store. Julia's store (`agents.lead_qualificacao_estado.valores`) is NOT
written (no existing cross-product seam; the owner can add one later). `leads.regiao` (spreadsheet legacy) is left alone. The raw answers
remain in `meta_ads_leads.answers` and `leads.observacoes`.

### 2.2 Vista -> `imoveis` -> contract (`DadosContrato` / `Imovel`, `card_hub/contrato_gerador/dados.py`)

The Vista columns of `imoveis` are written ONLY by the sync (`_assert_so_vista`); what WE own (captação, dados, owner confirmation) lives in
`imovel_captacao` / `imovel_dados` / `julia_proprietarios_contatos` and wins over the mirror.

| Vista field (`/imoveis/detalhes`) | `imoveis` column | Meaning in the contract (`Imovel`) |
|---|---|---|
| `Codigo` | `codigo` (PK with org) | the property identifier on the instrument/card |
| `ValorVenda` | `valor_venda` | price; the divergence check compares it with OUR owned value |
| `Categoria`, `Dormitorios`, `Suites`, `Vagas`, `AreaTotal`, `AreaPrivativa` | same names | description of the object |
| address fields (logradouro, número, complemento, bairro, cidade, UF, CEP) | same-named columns | address of the object; `imovel_dados` manual address wins |
| `Empreendimento` | `empreendimento` | condomínio name (`imovel_dados.condominio_id` wins) |
| `Corretor` `{Codigo, Nome, Email, Fone}` (dict keyed by code, or `[]`) | `corretores` jsonb (kept) **+ `imovel_corretores`** | the corretor/intermediary side of the deal; NOT a party of the sale |
| (owner / proprietário) | not read by the intake | the seller `Pessoa` comes from the cliente/atendimento parts (`card_hub`), never from this refresh |

### 2.3 Corretor

`imovel_corretores(org_id, codigo_canonical, chave, vista_corretor_codigo, nome, email, fone, ordem, corretor_id, ativo, visto_em)`, unique
`(org_id, codigo_canonical, chave)` (`chave` = the Vista `Codigo`, else `nome:<folded name>`). `corretor_id` -> `lead_corretores` (SW's corretor
dimension, which is NAME-keyed through `lead_corretor_aliases`): resolved first by `lead_corretores.vista_codigo` (new, nullable, unique per org),
else by the same alias map the lead's corretor uses; a name match with no `vista_codigo` yet STAMPS it (so the Vista `Codigo` is the key from then
on). Unmatched => `corretor_id NULL` (never a guess). A corretor that left the property flips `ativo=false`, never deleted. Multi-corretor
properties (13%) keep every row (`ordem`).

Divergence (`lead_corretor_divergencias`, migrations 331+332): three distinct `tipo`s, each its own row, its own in-app warning (`kind = lead_corretor_<tipo>`) and one OPEN row per `(lead, código, tipo)` (unique key):
* `fora_dos_corretores` — the lead has a corretor and it is none of the property's Vista corretores.
* `nao_e_principal` — the lead's corretor is one of them but not the MAIN one (`imovel_corretores.principal` = the FIRST corretor Vista lists, `ordem` 0). Not raised when `fora_dos_corretores` holds for the same pair: "not among them" already implies "not the main one", so a second warning adds nothing (decision; the two are therefore mutually exclusive in practice).
* `lead_sem_corretor` — the lead has no corretor at all (recorded + warned, NOT assigned).
Each run re-evaluates all three: a still-`pendente` row whose condition stopped holding is auto-closed (`resolvida`, `nota` = the reason, e.g. "auto: o lead passou a ter corretor"); a human-closed row (`resolvida`/`ignorada`) is never reopened or re-notified. No property corretor => `fora`/`nao_e_principal` cannot be evaluated. The result carries `divergencia_corretor: {divergencia, tipos[], novas[], fechadas[]}`. Humans close any tipo through the same `POST /corretor-divergencias/{id}/resolver`; `GET /corretor-divergencias?status=&tipo=`.
Name-stamping of `lead_corretores.vista_codigo` is audited: every stamp is listed in `resultado.vista_codigo_stamps` (`{corretor_id, nome, vista_codigo, codigo_canonical}`) and logged.
The warning reuses core in-app notifications to org owners+admins (`notify_org_admins`, same recipients as `lead_novo`); the WhatsApp digest of the
Vista-divergence mechanism is NOT reused (it is per Vista-sync run and transitional, `NOC-REMEDIATE[transicao-vista-divergencias]`).

We do NOT assign `leads.corretor_id` from the property (owner decision: warn via `lead_sem_corretor`, never assign).

## 3. Data model (migrations 331 + 332 — forward-only, idempotent, backward-compatible)

* `lead_imovel_intakes` (tier:org) — one row per lead (`unique (org_id, lead_id)`): `status`, `tentativas`, `ultimo_erro`, `resultado` jsonb (see § 4), `concluido_em`.
* `imovel_corretores` (tier:org), `lead_corretor_divergencias` (tier:org) — above.
* `lead_corretores.vista_codigo`, `leads.qualificacao_form` — new nullable columns.
* `cliente_imovel_interesses`: CHECK `cliente_imovel_interesses_lead_unico` (at most ONE of lead_id/meta_ads_lead_id) DROPPED so a row carries both.
  The first lead keeps the interesse (one row per (cliente, código)); further leads of the same cliente for the same code are reachable through `leads.imovel_ref_id`.
* All three tables: RLS on, service-role only, `REVOKE ALL FROM PUBLIC, anon, authenticated`, `COMMENT … 'tier:org'`. No SECURITY DEFINER.

"Leads linked to a property" = `leads.imovel_ref_id = registry.id` ∪ `cliente_imovel_interesses.lead_id` (live rows) — both populated by the intake.

## 3b. Ref-divergence notices — the sync never erases our data, it warns (migration 333, owner 2026-11-09)

`imovel_ref_avisos(org_id, codigo_canonical, tipo, status, exibir_antes, notas jsonb, notificado_em, …)` — a SIBLING of `lead_corretor_divergencias`, not one generalised
table: its subject is an imóvel (no lead), its resolutions differ (`restaurar` / `confirmar_sumiu` / `ciente`), and its open-uniqueness key is `(org, código, tipo)`.

| `tipo` | When | What happens |
|---|---|---|
| `ref_sumiu_no_vista` | a ref WE HAVE (a mirror row exists) that Vista no longer has: per-code `DETALHE_SUMIU` (sync_detalhes or the intake refresh) or a listar registry sweep that delisted it | every datum kept (no delete); the imóvel is PAUSED: `imoveis.exibir_no_site=false` — the flag the site, Julia's catalog/offers (`julia_catalogo_service.publicado`) and the campaign card (`campanha_resolucao._codigos_da_campanha` now drops paused codes) already honour; notice `pendente` + ONE in-app warning per sync run to owners/admins. A transport failure is never a disappearance. A mass removal is still refused by the 20%/50 circuit breaker (`removidos_excessivos`): no pause, no notice. A code we never had (a typo'd REF) gets none. |
| `ref_nova_no_vista` | a ref Vista has that we did not (discovery, listar, intake) | created on our side as before; informational notice; ONE batched in-app warning per run; not recorded on an org's very first import (empty mirror). |

The pause is STICKY: while a `ref_sumiu_no_vista` notice is `pendente` or `confirmada_sumiu`, the sync's upserts force `exibir_no_site=false` (Vista's value is not applied). If the code reappears in Vista the notice gets a note (`tipo: reapareceu`) and stays paused; a confirmed-gone one REOPENS to `pendente` (a new fact needs a human). Nothing ever unpauses automatically.
Resolutions: `POST /ref-avisos/{id}/restaurar` (sets `exibir_no_site` back to `exibir_antes`, status `restaurada` — if Vista still lacks it, the next sync opens a new notice) · `POST /ref-avisos/{id}/resolver {acao: confirmar_sumiu}` (stays paused, `confirmada_sumiu`) · `{acao: ciente}` (a `ref_nova`). Mirror field updates stay automatic; owned-layer divergences (`vista_divergencias`) are unchanged.

## 4. Endpoints (`/api/leads/ad-intake`, org-tier; admin where it writes/calls Vista; registered before `/api/leads/{lead_id}`)

| Method | Path | Who | Result |
|---|---|---|---|
| POST | `/backfill?dry_run=true&limite=25&cursor=&modo=novos\|pendentes\|refazer&pausa_s=0` | org admin | batch report: `lote, sem_lead, ja_feitos, a_processar, processados, por_status, falhas[], codigos_distintos, proximo_cursor` |
| GET | `/resumo` | member | `{intakes:{status:n}, total, divergencias_corretor_pendentes}` |
| GET | `/lead/{lead_id}` | member | `{lead:{id, meta_lead_id, codigo_imovel, imovel_ref_id, corretor_id, qualificacao_form}, intake, imovel, interesses[], corretores_do_imovel[], divergencia_corretor}` |
| POST | `/lead/{lead_id}/retry` | org admin | re-runs the intake (Vista is called) |
| GET | `/imovel/{codigo}/leads?limite&offset` | member | **"Leads interessados"**: `{items:[{id, cliente_nome, contato, data_entrada, origem_raw, corretor_id, created_at, meta_lead_id}], total, codigo}` |
| GET | `/corretor-divergencias?status=pendente` | member | `{items, total}` |
| POST | `/corretor-divergencias/{id}/resolver` `{status: resolvida\|ignorada, nota?}` | org admin | the updated row |
| GET | `/ref-avisos?tipo=&status=pendente` | member | `{items, total}` of ref-divergence notices (§ 3b) |
| POST | `/ref-avisos/{id}/restaurar` `{nota?}` | org admin | unpause + clear |
| POST | `/ref-avisos/{id}/resolver` `{acao: confirmar_sumiu\|ciente, nota?}` | org admin | the updated row |

`intake.resultado` shape: `{codigo, vista: ok|sumiu|oculto|falhou|null, imovel: novo|atualizado|inalterado, mudancas:{col:{antes,depois}}, divergencias_vista:[{campo,vista,nosso}], imovel_ref_id, interesse:{cliente, atendimentos}, corretores:{fonte: vista|espelho, total, codigos[]}, divergencia_corretor:{divergencia, nova?, id?}, qualificacao, erros[]}`.

Note on "divergence": `mudancas` = our MIRROR vs Vista (what changed since the last pull, e.g. ONE10669 `valor_venda` 1.290.000 -> 1.250.000, the mirror is
then updated); `divergencias_vista` = Vista vs OUR OWNED layer (captação/dados/owner confirmation) via the existing `imovel_campo_conflitos` mechanism
(only when `vista_divergencias_config.ativa` for the org — it is ON for the One org).

## 5. Backfill (existing One `meta_ads_leads`, ~2,431)

MCP tool `noctus.sw.ad_lead_intake` (`mcp/noctusai/tools/noctus/sw/ad_lead_intake.py`, same `NOCTUS_SW_URL`/`NOCTUS_SW_TOKEN` convention as `noctus.sw.imoveis_sync`):
`action=status` | `action=backfill` — dry-run by default (server-side dry-run: classifies and counts, no writes, no Vista); a real run needs `dry_run=False`
AND `confirm=True`. Batches of `limite` (<=100) ordered by `meta_ads_leads.id`, resumable (`proximo_cursor` -> `cursor`), `max_lotes` per call, each distinct code
fetched ONCE per batch, Vista pacing = the shared `vista` rate-limit bucket (+ optional `pausa_s`). A Meta row with no mapped `leads` row is reported
(`sem_lead`), not created (`backfill_meta_ads_leads` owns that). Re-running skips finished leads (`ja_feitos`); `modo=pendentes` re-drives only the retryable ones;
`modo=refazer` re-compares everything against Vista. NOT run against prod by the build.

## 6. Post-deploy check (run for ONE new `meta_ads_leads.id`, replace `:meta_id`; org One = `fd169d29-4d0a-4b04-9a5e-25e69407614d`)

```sql
-- 1. lead created + linked to the registry (G1) + qualification
select l.id as lead_id, l.codigo_imovel, l.imovel_ref_id, r.codigo_canonical, l.corretor_id, l.qualificacao_form
from social_wiring.leads l
left join social_wiring.imovel_registry r on r.id = l.imovel_ref_id
where l.org_id = 'fd169d29-4d0a-4b04-9a5e-25e69407614d' and l.meta_lead_id = :meta_id;
-- expect: imovel_ref_id not null, codigo_canonical = upper(codigo_imovel), qualificacao_form not null when the form had budget/fase/região answers

-- 2. the intake outcome (+ what Vista changed)
select i.status, i.tentativas, i.ultimo_erro, i.resultado->>'vista' as vista, i.resultado->>'imovel' as imovel,
       i.resultado->'mudancas' as mudancas, i.resultado->'divergencias_vista' as divergencias_vista, i.concluido_em
from social_wiring.lead_imovel_intakes i join social_wiring.leads l on l.id = i.lead_id
where l.meta_lead_id = :meta_id;
-- expect: status 'ok' (or 'imovel_nao_encontrado' with ultimo_erro); vista 'ok'; imovel in (novo, atualizado, inalterado)

-- 3. property created/updated now (refresh actually happened)
select m.codigo, m.valor_venda, m.sincronizado_em, now() - m.sincronizado_em as idade
from social_wiring.imoveis m join social_wiring.leads l on m.codigo_norm = upper(l.codigo_imovel) and m.org_id = l.org_id
where l.meta_lead_id = :meta_id;
-- expect: idade of minutes, not 2026-10-23

-- 4. property -> lead link (G2): both ids on the interesse; and the card link
select c.id, c.codigo, c.lead_id, c.meta_ads_lead_id, c.origem, c.deleted_at
from social_wiring.cliente_imovel_interesses c where c.meta_ads_lead_id = :meta_id;
-- expect: lead_id not null AND meta_ads_lead_id = :meta_id (unless the cliente has an older interesse for that code: then lead_id of the first lead)
select ai.atendimento_id, ai.codigo from social_wiring.atendimento_imoveis ai
join social_wiring.atendimentos a on a.id = ai.atendimento_id where a.meta_ads_lead_id = :meta_id and ai.deleted_at is null;

-- 5. corretor recorded (G4) + divergence
select ic.vista_corretor_codigo, ic.nome, ic.corretor_id, ic.ativo
from social_wiring.imovel_corretores ic join social_wiring.leads l on ic.codigo_canonical = upper(l.codigo_imovel) and ic.org_id = l.org_id
where l.meta_lead_id = :meta_id and ic.ativo;
select d.status, d.lead_corretor_nome, d.imovel_corretores, d.notificado_em
from social_wiring.lead_corretor_divergencias d join social_wiring.leads l on l.id = d.lead_id where l.meta_lead_id = :meta_id;
-- expect: >=1 corretor row when Vista has a Corretor; a divergence row only when the lead has its own corretor that differs

-- 6. health of the whole feature
select status, count(*) from social_wiring.lead_imovel_intakes where org_id = 'fd169d29-4d0a-4b04-9a5e-25e69407614d' group by 1;
select count(*) from social_wiring.leads l left join social_wiring.lead_imovel_intakes i on i.lead_id = l.id
where l.org_id = 'fd169d29-4d0a-4b04-9a5e-25e69407614d' and l.meta_lead_id is not null and l.codigo_imovel is not null
  and l.imovel_ref_id is null;   -- leads not linked yet (pre-backfill backlog; must stay ~0 for NEW leads)
```
Same facts through HTTP: `GET /api/leads/ad-intake/lead/{lead_id}` and `GET /api/leads/ad-intake/resumo`.

## 7. For the next slices

* FE "Leads interessados" reads `GET /api/leads/ad-intake/imovel/{codigo}/leads`; pending corretor warnings from `GET /corretor-divergencias`.
* Corretor performance: `imovel_corretores` (property -> corretor, by Vista Codigo) x `leads.imovel_ref_id` (lead -> property) x `lead_corretores.vista_codigo`.
* Roteiros: not built here.
* Retry job (`ad_lead_intake_retry_job`, interval 10 min on the seed scheduler, per-org `sync_lease` `ad_lead_intake_retry:<org>`): drains `pendente_retry` rows whose backoff has passed (`updated_at + min(5min * 2^(tentativas-1), 6h)`), 25 per org per pass; `falhou` rows (after 5 attempts) are never auto-retried — backfill `modo=pendentes` or `POST /lead/{id}/retry`.
