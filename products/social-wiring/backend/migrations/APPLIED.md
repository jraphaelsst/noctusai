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
