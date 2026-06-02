# Wrap: "orphan" schemas + un-routed-products DNS — resolution (2026-06-02)

Two items left open at the end of the branch-tree/gate-methodology session were
framed as **decisions, not pending work**. Investigated against the live tree
and prod Supabase (`nyplttplcoyiiqjrvtiw`) — codebase is source of truth.
Built on branch `chore/wrap-orphan-schemas-and-dns-resolution` (off `origin/dev`).

---

## 1 · "Orphan" schemas — NOT orphans (premise was wrong)

The "orphan" label came from schema-name ≠ product-slug. The migration headers
and code prove ownership:

| Schema | Owner | Exposed (PostgREST)? | Decision |
|---|---|---|---|
| `mailing` | social-wiring **email_marketing** module (consent keys `mailing.*`, `mailing.ai_outputs`; seed webhook lists "mailing/webhooks") | **yes** (in `authenticator.pgrst.db_schemas`) | **KEEP** |
| `imobi_scheduling` | **erp-imobiliario** — the 14-phase imobi-scheduling build; RLS codified in migration `033` | no | **KEEP** (live consolidation target) |
| `media_scheduling` | **erp-imobiliario** — but consolidated INTO `imobi_scheduling` on 2026-05-11 (`b91043fc feat(ms-merge)`); RLS in `034` was the 2026-05-31 blanket sweep, not new life | no | **DROP** (deprecated husk) |

**PostgREST exposed-schemas list** (authoritative, `authenticator` rolconfig):
`public, graphql_public, erp, personal-finance, therapy, seed, daily_life, mailing, social_wiring`.
`media_scheduling`/`imobi_scheduling` are **absent** → dropping `media_scheduling`
**cannot** trigger the PGRST002 schema-cache outage (the `automation_workflow`
incident, 2026-05-31) — that only happens for an EXPOSED schema. No
unexpose/reload dance required.

### media_scheduling drop — ready, salvaged, NOT yet applied

- Teardown migration committed: `products/erp-imobiliario/backend/migrations/036_drop_deprecated_media_scheduling_schema.sql` (idempotent `DROP SCHEMA IF EXISTS … CASCADE`, loud DESTRUCTIVE header, full salvage inline).
- **Salvage (full, recoverable):** 15 tables, all empty except — `condominiums`=4 (explicit SMOKE-TEST fixtures: Reserva One / The Square Residences / Vintage Granja / Condomínio Sem Coordenadas), `service_types`=4 (seed catalog photos/videos/reels/virtual_tour), `status_pagina`=2 (dashboard/equipe=producao). **Zero production business data.** Row values are in migration 036's header + this session transcript.
- The live equivalent `imobi_scheduling.services`/`.condominiums` is itself empty (0 rows) — the merge target carries no real data yet either.
- **Apply = deliberate.** erp-imobiliario has no startup migration auto-runner, so 036 sits inert until applied by hand / explicit deploy step. **Pre-apply check grep cannot do:** confirm no n8n workflow / external webhook reads `media_scheduling.*` via service_role before applying.

### Latent observation (not actioned — erp-imobiliario's call)
`imobi_scheduling` carries 56 `authenticated` RLS policies (migration 033) but is
**not** in the PostgREST exposed list. If the scheduling feature ever needs
direct REST access for `authenticated` users (vs server-side service_role), the
schema must be added to the exposed list. Today it's reached server-side only,
so this is dormant, not a bug. Flag for erp-imobiliario when the feature wakes.

---

## 2 · Un-routed products — 5 deployed-but-unreachable at the edge

`ingress.yml` declares all 9 fleet hostnames, but the derived **DNS CNAMEs were
created by a hand-typed list** (README step 4) that silently drifted. Live DNS
(2026-06-02): only `core` / `erp.` / `seed.` / `social.` (+ apex) resolve.

**Deployed + healthy but NO resolving DNS record (edge NXDOMAIN):**
`personal-finance`, `therapy-platform`, `daily-life`, `adconnect`, `dev-team`.
(`knowledge-extractor` is a separate case — not deployed, not in ingress.)

**Decision: route all 5** (they are declared-public in `ingress.yml`).
**Mechanism (kills the drift): `deploy/tunnel/route-dns.sh`** — reads hostnames
from `ingress.yml` and routes each idempotently; README step 4 now points at it
(manual list kept as fallback).

### DNS routing — ready, NOT yet applied
- `deploy/tunnel/route-dns.sh <TUNNEL_NAME>` creates the missing CNAMEs.
- **Apply = deliberate, outward-facing.** Mutates live Cloudflare DNS; requires
  `cloudflared` authenticated to the noctusai.com zone, run **on the VPS**. Not
  wired into any auto-deploy path. Reload the tunnel after if config changed.

---

## Status

| | Resolved | Artifact | Applied to prod? |
|---|---|---|---|
| mailing / imobi_scheduling | KEEP | this doc + schema-ownership map | n/a |
| media_scheduling | DROP | migration 036 (salvaged) | ❌ deliberate apply pending |
| 5 un-routed products | ROUTE | `route-dns.sh` + README | ❌ deliberate VPS apply pending |

Commits live on `chore/wrap-orphan-schemas-and-dns-resolution`, **not pushed**
(handed to the next agent for integration). The two "apply" legs are
intentionally left as deliberate, human/deploy-agent steps — both are
destructive/outward-facing and must not ride an unattended push.
