# portal-roi — ROI por portal · PROJECT

> **Status:** ⏳ contract authored, FE + BE dispatched in parallel.
> **Product:** `social-wiring`. **Fires:** T5 of
> `project-history/roadmaps/social-wiring-imoveis-vista-2026-08.md`.
> **Origin (user, 2026-08-03):** *"the origem is for me to create statistics
> based on my marketing portals to evaluate their performances against
> investments x results"*.

---

## 1 · Why this project exists

`043_lead_campanhas_vendas.sql` shipped **schema only** and was applied live on
2026-08-03. `lead_campanhas`, `lead_vendas` and `vw_portal_roi` all exist and
work. What was never built is everything above them: no service, no router, no
page, no way for the operator to enter a single number.

The consequence is measurable right now:

| Measure (live, 2026-08-13) | Value |
|---|---|
| portais in `vw_portal_roi` | 24 |
| portais with ≥1 lead | 23 |
| portais with any spend recorded | **0** |
| rows in `lead_campanhas` | **0** |
| rows in `lead_vendas` | **0** |

23 portals have real lead volume (Senseys 3 728, ZAP 2 769, Imóvel Web 1 481,
Tempo Real 1 314, Meta Ads 1 151, …) and not one of them has a cost attached.
The view is a correct answer to a question nobody can yet ask.

## 2 · 🔴 The lying-number bug — fix this BEFORE any UI renders it

`vw_portal_roi` currently returns **`cpl = 0.00` for 23 of 24 portals.**

```sql
COALESCE(c.investimento, 0) / NULLIF(COALESCE(l.total_leads, 0), 0) AS cpl
```

The `NULLIF` guards the **denominator** — "no leads yet" correctly reads as
unknown. But the **numerator** is `COALESCE(investimento, 0)`, so a portal with
3 728 leads and no recorded spend computes `0 / 3728 = 0.00` and renders as
**"this portal costs R$ 0,00 per lead"**. The truth is "we have never recorded
what it costs".

This is the exact failure mode `043`'s own header warns about, one level up:

> *"a stored copy is a copy that can disagree with its inputs … the number that
> drives a spend decision is exactly the wrong number to let drift."*

A CPL of zero on the highest-volume portal is the most decision-distorting
number this page could possibly show — it says "spend more here, it's free".

**Required fix (BE slice, migration `047`):** guard the numerator too. Absent
spend is `NULL`, not `0`.

```sql
NULLIF(COALESCE(c.investimento, 0), 0) / NULLIF(COALESCE(l.total_leads, 0), 0) AS cpl
```

Apply the same reasoning to the other two derived columns and **state the
verdict for each in the migration header** rather than copying the change:

- `roi` — already `NULLIF`s investimento in the denominator. ✅ correct today.
- `taxa_conversao` — `total_vendas / total_leads`. A genuine 0 (leads that
  closed nothing) and an unrecorded 0 (`lead_vendas` empty) are **different
  facts** and this column cannot currently tell them apart. Decide and record
  which one it reports; do not leave the ambiguity undocumented.

`investimento`, `total_leads`, `total_vendas`, `valor_vendas` stay
`COALESCE(...,0)` — those are counts of things, and zero really is zero.

## 3 · The FE↔BE contract (authored once; both sides build to THIS)

Base path `/api/portal-roi`. Every route is org-scoped from the auth context —
**`org_id` is never a client-supplied parameter.** Auth boundary asserts strict
`== 401` (`KB § PATTERNS/compliance/auth-boundary-false-green.md`).

### 3.1 `GET /api/portal-roi/resumo`

Query: `?periodo_inicio=YYYY-MM-DD&periodo_fim=YYYY-MM-DD` (both optional; absent
⇒ all time).

```jsonc
{
  "periodo": { "inicio": "2026-01-01", "fim": "2026-08-13" },  // null when all-time
  "totais": {
    "investimento": 12500.00,
    "total_leads": 13329,
    "total_vendas": 0,
    "valor_vendas": 0,
    "cpl": 0.94,          // null when investimento is unrecorded
    "roi": null,          // null when investimento is 0/unrecorded
    "taxa_conversao": null
  },
  "portais": [
    {
      "origem_id": "uuid",
      "slug": "senseys",
      "label": "Senseys",
      "categoria": "portal",          // portal | social | direto | outro
      "investimento": null,           // null = NOT RECORDED (never 0-as-unknown)
      "total_leads": 3728,
      "total_vendas": 0,
      "valor_vendas": 0,
      "cpl": null,
      "roi": null,
      "taxa_conversao": null
    }
  ]
}
```

🔴 **`investimento: null` and `investimento: 0` mean different things** and both
occur. `null` = no `lead_campanhas` row covers this portal/period. `0` = a row
exists and says the spend was zero. The FE MUST render them differently
(§3.5). Serialising `null` as `0` anywhere in this stack re-creates the bug in
§2 one layer higher.

### 3.2 `GET /api/portal-roi/campanhas`

Query: `?origem_id=<uuid>` (optional), `?periodo_inicio=`, `?periodo_fim=`.
Returns the spend rows themselves, newest period first.

```jsonc
{
  "campanhas": [
    {
      "id": "uuid",
      "origem_id": "uuid",
      "origem_label": "ZAP",
      "periodo_inicio": "2026-07-01",
      "periodo_fim": "2026-07-31",
      "investimento": 3200.00,
      "impressoes": 120000, "cliques": 4300, "leads": 812,
      "visitas_perfil": null, "engajamento": null,
      "cpc": 0.74, "cpl": 3.94, "custo_visita": null,   // GENERATED — read-only
      "observacoes": null,
      "created_at": "...", "updated_at": "..."
    }
  ]
}
```

### 3.3 `POST /api/portal-roi/campanhas` · `PATCH /…/{id}` · `DELETE /…/{id}`

The spend-entry surface. **There is no portal API** — the operator reads these
numbers off each portal's own dashboard and types them in. That is the whole
reason this CRUD exists, and it is why the page owns its data
(`KB § PATTERNS/frontend/product-internal-wiring.md`: read-only ≠ managed).

Writable fields: `origem_id`, `periodo_inicio`, `periodo_fim`, `investimento`,
`impressoes`, `cliques`, `leads`, `visitas_perfil`, `engajamento`,
`observacoes`. `cpc` / `cpl` / `custo_visita` are GENERATED — reject a write
that names them (`422`), never silently drop it.

Errors, all with an actionable `detail` (no bare 500s):

| Case | Status |
|---|---|
| `periodo_fim < periodo_inicio` | `422` |
| `investimento < 0` | `422` |
| duplicate `(origem_id, periodo_inicio, periodo_fim)` | `409` — the UNIQUE is deliberate; re-importing a month must UPDATE, not duplicate, or spend doubles and every ROI halves |
| `origem_id` not in this org's `lead_sources` | `404` |
| unauthenticated | `401` |

A `409` MUST return the conflicting row's `id` so the FE can offer "update the
existing period" instead of dead-ending the operator.

### 3.4 `GET /api/portal-roi/origens`

`lead_sources` for this org (`id`, `slug`, `label`, `categoria`) — the picker
feed for the spend form. Do not make the FE derive it from `/resumo`.

### 3.5 FE rendering rules (non-negotiable — these ARE the feature)

- **`investimento: null` renders "não informado"**, never "R$ 0,00". Same for
  `cpl` / `roi` / `taxa_conversao`. A dash or muted "—" with a tooltip is fine;
  a zero is not.
- A portal with leads and no spend gets a **visible "registrar investimento"
  affordance** on its row. That is the page's primary call to action on day one,
  because on day one that is 23 of 24 rows.
- Loading gates on `isPending || isFetching`, **never `isLoading`**
  (`KB § PATTERNS/frontend/lying-loading-state.md`, keeper
  `check_lying_loading_state`).
- All four states ship: loading, empty, error, success. "Empty" here means *no
  `lead_sources`*, which is different from *sources with no spend* — the latter
  is the normal state and must render the table, not an empty state.
- Currency + dates in pt-BR (`R$ 1.234,56`, `13/08/2026`).

## 4 · Slices (file-disjoint; dispatched in parallel)

| Slice | Owner | Files |
|---|---|---|
| **B1** migration `047` (§2 fix) + service + router + tests | backend-engineer | `backend/migrations/047_*.sql`, `backend/app/services/portal_roi_service.py`, `backend/app/routers/portal_roi_router.py`, `backend/app/main.py` (register only), `backend/tests/**` |
| **F1** page + hooks + nav | frontend-engineer | `frontend/src/pages/PortalRoi.tsx`, `frontend/src/hooks/usePortalRoi.ts`, `frontend/src/components/portal-roi/**`, nav registration, `frontend/src/**/*.test.tsx` |

The only shared surface is the contract above. Neither slice edits the other's
files; `main.py` is touched by B1 only.

## 5 · Checkpoint

The page lists 24 portals with real lead counts, shows "não informado" (not
R$ 0,00) wherever spend is absent, the operator can enter a July spend for ZAP
and see CPL and ROI populate on that row, and re-entering the same period
offers an update instead of duplicating. `status_pagina.portal_roi` stays
`'desenvolvimento'` until that has been seen in a browser.
