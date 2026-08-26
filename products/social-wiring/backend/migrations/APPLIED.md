# social-wiring — applied-migration state

> **Why this file exists.** This repo has **no applied-migrations ledger**, and the
> migration file headers have been wrong *in both directions*: `048` and `050` both
> carried "not applied" notes long after they were applied, and a 2026-08-18 audit
> could only infer their state from commit messages. A header is written once, at
> authoring time, and nothing updates it when the migration actually runs — so it
> records an *intention*, not a fact.
>
> 🔴 **The live database is the only source of truth.** This file is a convenience
> record, not an authority. Verify with a query before you rely on it — the snippet
> at the bottom is there so nobody has to invent one.
>
> `social-wiring` runs against the **prod Supabase project, which dev shares**.
> Applying anything here is a production change and therefore the user's decision,
> never an agent's.

## State as of 2026-08-18

| Migration | Applied | Verified how |
|---|---|---|
| `001`–`047` | ✅ (assumed; predates this record) | not re-verified |
| `048_clientes_person_layer.sql` | ✅ | live: `clientes`, `cliente_touches`, `cliente_merges` all exist |
| `049_imoveis_place_name_collision_fix.sql` | ❓ not verified | — |
| `050_cliente_revisao_rejeitadas.sql` | ✅ | live: `cliente_revisao_rejeitadas` exists |
| `051_olx_portal_leads.sql` | ✅ | live: `olx_leads`, `olx_lead_events`, `leads.external_lead_id` all exist |
| `054_negociacoes_venda_collapse.sql` | ✅ **2026-08-18** | probe + apply + post-verify (below) |
| `056_card_hub_core.sql` | ✅ **2026-08-18** | probe + apply + post-verify (below) |
| `057_card_hub_documentos.sql` | ✅ **2026-08-18** | probe + apply + post-verify (below) |
| `058_clientes_inactivity_sweep.sql` | ✅ **2026-08-18** | probe + apply + post-verify (below) |

`052` and `053` are claimed by branches not yet on `dev` (`feat/imovelweb-portal-leads`,
`feat/grupo-olx-multitenant-receiver`) — **the numbers are taken, the migrations are not
applied.** This is exactly why `noctus.dev.next_migration_number` checks every local branch
and not just the directory.

## The 2026-08-18 apply

Each migration got a `BEGIN … <migration> … probe … ROLLBACK` dry run against the **live**
schema first, then a real apply, then a post-apply verification query. In order:
`054` → `056` → `057` (all depend on `048`'s `clientes`).

**`054` — collapse.** The dry run predicted 451 rows collapsing into 1 010 visible cards
out of 1 461 total, with `open_hidden_behind_closed = 0`. The real apply matched exactly,
and a post-check confirmed `chained_survivors = 0` (no survivor is itself collapsed) and
that the row total was **unchanged at 1 461** — nothing was deleted, which is the whole
design.

Worth recording because it contradicts the roadmap's headline number: the roadmap measured
**125** duplicate pairs on 2026-08-07; the real collapse was **451 rows across 322 groups**.
Not a defect — identity resolution has since attached ~10 200 clientes, so repeat-contact
people now share a `cliente_id`. Checked before applying: **0 groups span more than 30 days**
(206 of 322 collapse within one hour; 232 are the classic mixed lead+campaign double-trigger).
So no genuinely separate, months-apart negotiation was folded. **A future one could be** —
see the D17 note below.

**`056` — card core.** 7 tables, RLS enabled on every one, 2 policies each. Probe confirmed
the dependencies (`public.current_org_id()`, `lead_corretores`, `pipeline_stages`) all resolve.

**`057` — documents, LGPD.** 3 tables + the private storage bucket. Post-verify: bucket
`public = false`, 5 object-level storage policies, 9 document types of which **7 active** —
`rg` and `cpf` are seeded `ativo = false` and refused by construction until the LGPD
data-category intake in `LGPD-WARNINGS.md` is resolved by a human.

**`058` — D16 inactivity.** Two nullable columns on `clientes` + the per-org
`clientes_inactivity_config` table. Schema-only: **the migration changes no data.**

🔴 **But the SWEEP it enables will, and the number is large.** Measured on the live data at
apply time, against the ratified 180-day threshold:

| Threshold | Clientes still active | Swept inactive | % swept |
|---:|---:|---:|---:|
| 30 days | 381 | 9 823 | 96 % |
| 90 days | 1 515 | 8 689 | 85 % |
| **180 days (D16, ratified)** | **3 072** | **7 132** | **70 %** |
| 365 days | 5 498 | 4 706 | 46 % |
| 730 days | 9 086 | 1 118 | 11 % |

Total 10 204 clientes; contact history spans 2024-03-19 → 2026-08-18. Today **0** are
inactive and **0** are manually archived, so the first sweep tick is a step change from
nothing to 7 132.

**Nothing has happened yet** — the scheduler runs inside the deployed container and this
code is not deployed. The window to change the threshold (via `PUT /api/settings/
clientes-inactivity`, or by seeding a `clientes_inactivity_config` row) is **before the
first deploy**. Raised with the user 2026-08-18; 180 stays the ratified default until they
say otherwise. Recorded here because "70 % of the board disappears on first tick" is not
something anyone should discover from the UI.

## 🔴 Open item this apply surfaced

**D17 vs. the collapse rule.** `054` collapses on `cliente_id` alone, with no time or
deal-identity dimension. Today that is safe (no group spans >30 days). But D17 says a person
*accumulates* negotiations over time and closed ones stay as history — so a customer who
bought in 2024 and negotiates again now would have two legitimately distinct deals folded
into one board card. The card dialog does list every negotiation (`CardResumo.negociacoes`),
so nothing is lost or invisible; but the **board face** shows one card, and a second *open*
deal for the same person currently renders nowhere on the board. Revisit when the first
multi-month group appears — the query under "Verify" will find it.

## Verify (do this rather than trusting the table above)

```sql
SELECT
  (SELECT count(*) FROM information_schema.columns
     WHERE table_schema='social_wiring' AND table_name='negociacoes_venda'
       AND column_name IN ('substituida_por','colapsada_em'))            AS mig054,
  (SELECT count(*) FROM information_schema.tables
     WHERE table_schema='social_wiring'
       AND table_name IN ('cliente_notas','cliente_tags','cliente_tag_links',
                          'cliente_membros','cliente_lembretes',
                          'cliente_checklists','cliente_checklist_itens'))AS mig056,
  (SELECT count(*) FROM information_schema.tables
     WHERE table_schema='social_wiring'
       AND table_name IN ('cliente_documento_tipos','cliente_documentos',
                          'cliente_documento_acessos'))                  AS mig057;
-- expect 2 / 7 / 3

-- Has a multi-month collapse group appeared? (the D17 watch item)
SELECT cliente_id, count(*) AS n, max(created_at) - min(created_at) AS span
FROM social_wiring.negociacoes_venda
WHERE cliente_id IS NOT NULL
GROUP BY cliente_id HAVING count(*) > 1 AND max(created_at) - min(created_at) > INTERVAL '30 days'
ORDER BY span DESC;
```

**Keep this file updated in the same commit that applies a migration.** If that ever feels
like a chore worth automating, it is — a `noctus.dev.*` tool that diffs `migrations/` against
the live `information_schema` would remove the guesswork permanently.

## 061_atendimento_agendamentos.sql — APPLIED 2026-08-19

Verified against the live database before and after.

**Before:** table absent, `cliente_lembretes.agendamento_id` absent, 1 cliente
with a `data_entrega`.
**After:** table + 2 partial indexes + RLS (org-scoped SELECT for
`authenticated`, ALL for `service_role`); `cliente_lembretes.agendamento_id`
added; backfill produced exactly 1 agendamento
(`4d4abc19…`, 2026-08-20 15:00Z, lembrete 60min) with its pending reminder
re-pointed at it (`dispara_em` 14:00Z). Confirmed by query, not inferred.

**`clientes.data_inicio` / `data_entrega` / `lembrete_minutos_antes` /
`entrega_concluida` / `recorrencia` are now DEPRECATED as inputs.** Nothing
reads them to decide anything: `PATCH /api/clientes/{id}/datas` and
`services.patch_datas` were removed in the same commit, so the ONLY writer is
`agendamentos_service._sync_mirror`, which keeps `data_entrega` +
`lembrete_minutos_antes` as a derived cache of the soonest UPCOMING appointment.
That cache exists solely so the Clientes board's due pill (drawn from the
clientes LIST endpoint, not the card) stays correct without repointing that
query at a join across atendimentos → agendamentos for a thousand-row board.

Not dropped, deliberately: a dropped column is the one migration that cannot be
undone by re-running anything, and these still hold real values.

**Follow-up, still open:** repoint the clientes list query at
`atendimento_agendamentos` and retire the mirror. And
`NOC-REMEDIATE[reminder-delivery]` — reminders are scheduled correctly and
NOTHING DELIVERS THEM; the marker moved from `patch_datas` into
`agendamentos_service._sync_lembrete` when the former was removed.

---

## 067_documento_checklist.sql — applied 2026-08-21

> Applied to the live DB as `065_documento_checklist` before a parallel
> session's `065_campanhas.sql` reached `dev`. The FILE was renumbered to
> 067 (`check_migration_number_collision` caught the clash at integrate);
> the recorded Supabase migration keeps its original name, which is
> harmless — the DDL is `IF NOT EXISTS` and the table already exists.

`social_wiring.cliente_documento_checklist` created on the live database; RLS
enabled with both policies (org-scoped SELECT for `authenticated`, full access
for `service_role`), plus the unique `(cliente_id, item_key)` the upsert relies
on. Verified by querying `pg_class`/`pg_policies`, not assumed from a clean exit.

**The table stores TICKS, not the checklist.** The six required fields (Nome
Completo, Email, Data de Nascimento, Gênero, RG, CPF) are identical for every
client by definition, so the list lives in
`card_hub/documento_checklist_service.ITENS` and every card renders the same
one. Only "has this client provided it yet" is per-client data.

Materialising the six as rows per client was the obvious alternative and was
rejected: it turns the DEFINITION into data, so adding a seventh field would
need a backfill across every existing client, and until it finished, cards
created before and after would show different checklists.

Consequences worth knowing:

* `item_key` is identity, the label is presentation — renaming an item is a
  one-word code edit that every card picks up with ticks intact.
* No backfill was needed or run; a client with zero rows correctly reads as six
  unticked items.
* Retiring a key leaves its rows inert rather than deleting them, so an
  accidental retirement is reversible.

---

## 068 + 069 — found ALREADY APPLIED on 2026-08-24

> 🔴 **This file said nothing about them, and they were live.** They were
> authored on 2026-08-22 and reported as "file only, not applied". A direct
> query of the live database on 2026-08-24 found every object present. This
> is precisely the drift the header at the top warns about, caught by doing
> what the header says: verify against the database, never against a note.

They also do **not** appear in `supabase_migrations.schema_migrations`, so
they were applied as raw SQL rather than through `migration.apply` — the same
thing that happened to `067` (recorded there under its old name `065`). The
recorded history is therefore not a reliable index of what has run; the
catalog queries below are.

Verified present by querying `information_schema.columns`, `pg_constraint`
and `pg_indexes` — not inferred from a clean exit:

* `clientes`: `nome_completo`, `email`, `data_nascimento`, `genero`, plus
  `data_nascimento_origem` / `_documento_id` / `_em` / `_confirmado_por` /
  `_confirmado_em`.
* `cliente_documento_checklist.concluido` renamed to `concluido_manual`,
  nullable, no default — the derived-checklist shape.
* `cliente_documentos`: all seven `extracao_*` columns from 068 plus
  `extracao_descartada_em` / `_por` from 069.
* `cliente_documentos_extracao_status_check` covering
  `pendente|processando|ok|sem_dados|erro`.
* `cliente_documento_acessos_acao_check` widened to include `extract`.
* `idx_sw_cliente_documentos_sugestao_pendente`.

`cliente_documento_tipos` confirms `rg` and `cpf` at
`categoria_lgpd='identidade'`, `retencao_dias=1825`, `identidade=true`.

**Data shape at the time (10.255 clientes):** `nome` populated on 10.150 rows;
`nome_completo`, `email`, `data_nascimento` and `genero` populated on **zero**.
The four columns 068 added were empty across the board — which is why the
"Nome Completo" checklist item could never tick for anybody, and why 071
changed the derivation to read a name-shaped `nome` as well.

## 071 + 072 — applied 2026-08-24

`071_cliente_nome_oficial.sql`

* `clientes.nome_oficial` + `_origem` / `_documento_id` / `_em` /
  `_confirmado_por` / `_confirmado_em`.
* `cliente_documentos.extracao_nome` / `_confianca` / `_rotulo`, and COMMENTs
  on 068's unprefixed `extracao_confianca` / `extracao_rotulo` recording that
  they describe the BIRTHDATE (they cannot be renamed — 068 is applied).
* `idx_sw_cliente_documentos_sugestao_nome_pendente`.
* `social_wiring.normalizar_nome(text)` — IMMUTABLE, so it can be indexed;
  `unaccent` is not marked immutable and would have foreclosed that.
* `social_wiring.vw_nome_conferencia` with `security_invoker = true`, so the
  caller's RLS applies. Without it the view runs as its owner and hands every
  org's names to any authenticated reader.

🔴 **The document's name is held BESIDE the registration's, never merged into
it.** An earlier draft overwrote `nome_completo` and kept the displaced value
in a `_anterior` column. Rejected: overwriting answers "how accurate is our
registration data?" exactly once, destructively, per row. Two columns keep the
question answerable across the whole base at any time, and
`vw_nome_conferencia` is that surface.

`072_extracao_retry.sql`

* `cliente_documentos.extracao_tentativas` (NOT NULL DEFAULT 0), backfilled to
  1 for rows already in a terminal state so the sweep does not read them as
  never-attempted. Rows stranded in `pendente`/`processando` stay at 0 on
  purpose — they get their full retry budget, which is the recovery this is
  for.
* `idx_sw_cliente_documentos_extracao_pendente`, partial on the two
  non-terminal states.

Backfill touched 0 rows: only 1 document existed and it had no extraction.

---

## 073–078 — backfilled 2026-08-25

These landed on the live database between 2026-08-24 and 2026-08-25 and were
recorded in `social_wiring.schema_migrations` (the machine ledger) but not
here. Backfilled on contact rather than left silent; row counts below were
read from the live database at backfill time, not reconstructed.

`073_atendimento_compradores_e_checklist.sql` · `074_cliente_vinculo.sql`
— a second buyer on a deal, modelled as an edge table onto `clientes` rather
than a person table of its own, plus the checklist fields that gate the move.

`075_imovel_dados_cartorio.sql` — `imovel_dados` (matrícula number, registry
number, prefeitura) + `imovel_documentos` (matrícula, guia IPTU). Deliberately
NO access log and no retention clock: a matrícula is a public registry
document about a property, not personal data. 0 rows at backfill.

`076_imovel_dados_para_registry.sql` — corrective. 075 FK'd `imovel_dados` to
`imoveis`, the disposable Vista mirror, so a delisted property would have
taken its authored cartório data with it. Measured before the fix: 1062 of
3017 registry imóveis (35%) were already absent from the mirror, and they were
the SOLD ones. Repointed to `imovel_registry`, which is permanent.

`077_atendimento_negociacao.sql` — `negociacao_defaults` (org-level split) +
`atendimento_negociacao` (PK = atendimento_id, CHECK that the internal split
sums to 100). Named `atendimento_negociacao`, not `negociacoes`: migration 060
records the owner's own decision to rename away from that word after it
collided with a funnel stage name. 0 rows at backfill.

`078_atendimento_financiamento.sql` — `atendimento_financiamento` (three-valued
`situacao`) + `atendimento_documentos` + `atendimento_documento_acessos`.
Unlike 075, LGPD-complete: an imposto de renda is a person's declared income,
so every content read appends to the access log. `retencao_ate` shipped NULL
pending the owner's decision — answered by 079. 0 rows at backfill.

## 079 — `079_documento_retencao_politicas.sql`

* `documento_retencao_politicas`: the controller-owned retention policy,
  two-tier (`org_id IS NULL` = platform default, an org row overrides it).
  Moves retention off `cliente_documento_tipos.retencao_dias`, where only a
  migration could change it, onto a table the Settings screen edits.
* Seeded 17 platform rows: 9 for the `cliente` surface, **copied by SELECT
  from the live `cliente_documento_tipos`** rather than retyped, and 8 for the
  `atendimento` surface (the recommendation — 10y for the pacto/certidão set,
  5y for the comprovante de residência, 2y for the FGTS set; rationale on each
  row's `motivo` and in `LGPD-WARNINGS.md`).
* Verified against the live database after apply: all 9 cliente values are
  `IS NOT DISTINCT FROM` their catalogue counterparts, so this migration
  changed no effective retention for any existing document.
* `cliente_documento_tipos.retencao_dias` kept as a one-release rollback path
  and COMMENTed as superseded. No data changed on that table.

Touched 0 existing rows.

## 080 — `080_vw_lead_corretor_contagem.sql`

* `vw_lead_corretor_contagem` — lead count per broker, grouped in the
  database, `security_invoker = true` (same posture as `vw_nome_conferencia`).
* Replaces an N+1 in `dimensions_service.list_corretores_with_lead_count`:
  29 brokers meant 30 sequential PostgREST round trips. Measured in prod on
  2026-08-25, `GET /api/leads/corretores` was the slowest endpoint the
  container served — 3343ms / 2083ms / 1828ms in one 25-minute window, against
  a p50 of 6.4ms — and the app shell fetches it on every page.
* The counting was never the bottleneck: `idx_sw_leads_org_corretor` already
  covers every one of those counts. The round trips were.
* Verified against the live database after apply: 29 brokers, **0 divergences**
  between the old per-broker COUNT and the view, 12.087 leads attributed.

A view — no table created, 0 rows touched.

## 081 — `081_portal_roi_vendas_da_negociacao.sql`

* `vw_portal_roi` now counts won deals from the funnel, not only the
  manually-typed `lead_vendas` rows. Attribution runs
  `atendimento_negociacao → atendimentos.lead_id → leads.origem_id`; a sale is
  `status='aceita' AND closed_at IS NOT NULL`, which is the pair
  `pipeline/routers/boards.py` sets on accepting a proposal and the only
  definition of "won" the codebase has.
* Why it was empty: `lead_vendas` and `lead_campanhas` both held **0 rows**.
  The ROI screen showed 13.379 leads and 0 vendas because the sale had to be
  typed a second time, in a place nobody goes.
* Verified against the live database after apply: the attribution path
  resolves for **1.282 of the 1.284** atendimentos that carry a lead
  (all currently attributed to "Meta Ads (Leads)"). The 7 already-won deals
  are NOT attributable — 5 carry no `lead_id` at all and 2 have leads that
  predate `origem_id` — so the screen fills as deals close from here, not
  retroactively. Stated rather than implied: this wiring is correct and its
  history is empty.
* The two vendas sources are summed and must stay disjoint; there is no shared
  key that could detect a deal entered in both. Safe today (`lead_vendas` is
  empty) — see the migration header before building a manual-entry UI for it.

A view — no table created, 0 rows touched.

## 082 — `082_roteiros_visitas.sql`

✅ **APPLIED + VERIFIED 2026-08-26** (user go-ahead given after the row counts
were stated). Verified live immediately after: `roteiros` 6 columns, `visitas`
10, `visitas_registry_fk` → `imovel_registry` ON DELETE CASCADE, RLS enabled on
both with 4 policies, 4 indexes, and `vw_imovel_visita_contagem` queryable.
Zero existing rows touched — every statement was a CREATE.

* `roteiros` + `visitas` — the qualificação → visita funnel gets a real object.
  A visit used to be an agendamento with `tipo='visita'`: one property, no
  order, not printable, and — the reason this exists — not countable.
* `visitas.status` is three-valued (`pendente` / `realizada` / `nao_realizada`),
  never a boolean. "Hasn't happened yet" and "didn't happen" are different
  facts; merging them files every future visit under "did not".
* 🔴 **`visitas (org_id, codigo)` FKs to `imovel_registry (org_id,
  codigo_canonical)`, NOT to the `imoveis` mirror** — the same ruling 063 made
  and 076 had to re-make after 075 got it wrong. The mirror holds only ACTIVE
  Vista listings and 1062 of 3017 registered imóveis (35%, prod 2026-08-25)
  have already left it. A mirror FK would reject a third of the catalog at
  INSERT and delete visit history on delist — i.e. destroy exactly the
  2024→2028 record the FK was asked for. `test_migration_082_roteiros_visitas
  .py::TestFKTargetsTheRegistry` holds it shut.
* `vw_imovel_visita_contagem` — per-imóvel visit counts, `security_invoker =
  true` (071/080 posture), grouped on the registry código so a sold imóvel
  keeps its history. Written WITH the tables rather than after an N+1 is
  discovered (080's lesson, applied early).
* The CHECK on `atendimento_agendamentos.tipo` is deliberately NOT narrowed:
  live rows carry `'visita'`, and a migration that rejects data which already
  exists is a break, not a cutover. The Agendar button stops OFFERING it.
* No `proprietario_*` column: Vista exposes no owner data (D1, user-ratified
  2026-08-25), and a column nothing can write is a placeholder side. Its
  destination when a source exists is `imovel_dados` (075).

## 052 — `052_imovelweb_portal_leads.sql`

✅ **APPLIED + VERIFIED 2026-08-26.** Landed out of numeric order: the file was
authored 2026-08-18 on `feat/imovelweb-portal-leads` and merged today, long
after 053–082 had shipped. The slot was reserved and still free, so it kept its
number rather than being renumbered — renumbering would have broken every
reference in the project's own docs and tests.

* `imovelweb_lead_events` (the durable delivery inbox, PK = vendor eventId),
  `imovelweb_leads` (the lossless ledger) and `imovelweb_agencies` (the
  tenant-resolution key). All three created EMPTY; RLS on, 6 policies,
  8 indexes.
* Checked against prod BEFORE applying, because this migration is **not**
  purely additive — unlike 082 it touches two live tables:
  - `ALTER TABLE leads ADD COLUMN IF NOT EXISTS external_source/external_lead_id`
    — already present (051 added them), so a no-op.
  - `CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_leads_org_external_lead` — already
    existed (051), so a no-op. Had it NOT existed, a unique index over 13.478
    live leads could have failed on a duplicate; verified first rather than
    attempted.
  - `integration_accounts_provider_check` is DROPPED by dynamic lookup and
    re-ADDed one value wider (`+ imovelweb`). Verified beforehand that the
    providers actually in use are `gmail, meta, n8n, youtube` and that
    **0 rows** would violate the new list. Confirmed after: `leads` still
    13.478 rows, `integration_accounts` still 5.
* 🔴 **Applying it does NOT make the integration live**, and that separation is
  the point. The receiver 401s every delivery while no secret is configured
  (`bypass_when_unset=False`), and the MCP connector is not registered in
  `.mcp.json`. What applying it DOES buy: the two new scheduled jobs
  (`imovelweb_leads_retry` */15, `imovelweb_reconcile` hourly) find an empty
  queue and no-op cleanly. Without the tables they would have queried a missing
  relation every fifteen minutes forever — swallowed by the jobs' own
  `except`, so not fatal, but permanent error noise in prod.
* Gate 2 (live traffic) still needs vendor credentials — see
  `projects/imovelweb-portal-leads-ingestion/HANDOFF.md` §1.
