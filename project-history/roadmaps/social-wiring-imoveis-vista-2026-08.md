# social-wiring-imoveis-vista-2026-08 — Imóveis sidebar section for social-wiring, modeled on live Vista CRM data

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: user asked for a new "Imóveis" sidebar toggle in social-wiring to store "my actual products", modeled from what the Vista CRM actually returns.
> Decision: **Phase 1 ships the Vista MCP registration + this design record only. No product code — the canonical `Imovel` model is designed here and built in Phase 2, after the user ratifies the field set.**

## Origin

On 2026-08-03 the user asked to plan a new `Imóveis` sidebar toggle where their
real-estate listings ("my actual products") would live, explicitly stating there
was no data model yet and that the model should be derived from a live Vista
fetch rather than invented. They asked to start by fetching `ONE10107` and to
review the wire shape before building anything.

The seed-first check changed the plan materially: Vista is **already** integrated
across three surfaces (MCP server, seed IO module, ERP consumer), so this is a
*consume* slice, not a *build* slice. The one thing genuinely missing is an
in-home canonical `Imovel` model — the existing `PropertyData` is an 8-field
YouTube-metadata carrier, not a property model.

## What already exists (verified against the tree 2026-08-03, not from memory)

| Surface | Path | State |
|---|---|---|
| MCP server | `mcp/vista/` | 10 tools, per-tenant field calibration. **Was unregistered** — fixed in P1.1. |
| Seed IO module | `noctusai_lib/integrations/vista/` | Full Fake+Real+factory+protocol+normalizers. Ships-it gates pass. |
| Seed domain | `noctusai_lib/domain/real_estate/` | `PropertyData` (8 fields) + `build_youtube_metadata` + `validate_product_code` (`^ONE\d{3,6}$`). **Not a property model.** |
| ERP consumer | `products/erp-imobiliario` | Own `/imoveis` page backed by `erp.ativos` (`natureza='imovel'`). **Independent of Vista** — do not conflate. |
| social-wiring | `products/social-wiring` | Threads `product_code` (ONE-codes) through WhatsApp intake, YouTube upload jobs, settings. **Stores no imóveis.** ← the gap this roadmap closes |

**Consequence for scoping:** `noc-verify-seed` passes for the Vista adapter. The
Phase-2 work is a product-side consume + a new canonical domain model, NOT a new
seed integration.

## The live wire shape (`ONE10107`, fetched 2026-08-03, tenant `oneconsu-rest`)

`/imoveis/detalhes` returns 30 keys; `/imoveis/listar` returns 27. **They are not
the same set** — this asymmetry is the single most important modeling fact.

- **listar-only:** `FotoDestaque`, `BanheiroSocial`, `CodigoImobiliaria`, `Corretor_Codigo`
- **detalhes-only:** `Caracteristicas`, `Numero`, `Complemento`, `Empreendimento`, `Construtora`, `FinalidadeStatus`, `DataAtualizacaoDias`

Any complete `Imovel` requires **both** calls. `vista.imoveis.get` already does
this (it prefetches the listing row for `FotoDestaque`).

### Wire quirks the model must encode

| # | Quirk | Observed on ONE10107 | Modeling consequence |
|---|---|---|---|
| W1 | Every scalar is a **string** | `ValorVenda: "4980000"`, `Dormitorios: "4"` | Coerce at the adapter boundary; never let strings reach the app layer. |
| W2 | Empty is `""`, never `null` | `Finalidade`, `Latitude`, `Longitude`, `Construtora` all `""` | `"" → None` before validation. |
| W3 | `"0"` is **overloaded** | `ValorLocacao: "0"` = *not for rent*; `AreaConstruida: "0"` = *unknown* | Both → `None`. Current seed `_to_float` returns `0.0` for `"0"` — would render "R$ 0". |
| W4 | `Finalidade` is empty; `FinalidadeStatus` carries the signal | `Finalidade: ""` but `FinalidadeStatus: {"VENDA": true}` | Derive `finalidade` from `FinalidadeStatus` keys. Keying off `Finalidade` yields nothing. |
| W5 | `Caracteristicas` keys are de-camelized with inserted spaces | `"Sala T V"`, `"T V Cabo"`, `"W C Empregada"` | Slug normalization must collapse inserted spaces. |
| W6 | `Caracteristicas` carries a **real collision** | `"Dependenciade Empregada"` AND `"Dependencia De Empregada"` both present in the same 76-key dict | Naive `.replace(" ","").lower()` slugging maps both to one key. Handle explicitly; do not silently drop. |
| W7 | `Corretor` is a **dict keyed by code**, not a list | `{"16": {Codigo, Nome, Email, Fone}}` | Normalizer already walks both shapes (`_first_corretor_nome`) but returns only the FIRST — multi-corretor imóveis lose data. |
| W8 | `Empreendimento` may duplicate `Bairro` | both `"São Fernando Golf Club - Km 28"` | Don't render both blindly. |
| W9 | `DataAtualizacaoDias` is the only **int** on the wire | `9` | Derived — compute from `DataAtualizacao`, don't store. |
| W10 | Address is split and unprefixed | `Endereco: "Fernando Nobre"` (no "Rua"), `Numero: "4000"`, `Complemento: "389"` | Store parts; compose for display. |

### Confirmed latent bug (fix-on-contact candidate)

`noctusai_lib/integrations/vista/normalizers.py:104`:

```python
banheiros=_to_int(payload.get("Banheiros") or payload.get("BanheiroSocial")),
```

On `oneconsu-rest`, `Banheiros` is permission-denied and `BanheiroSocial` is
`"Sim"`. `_to_int("Sim")` raises `ValueError` internally and returns `None`. So
**`ShowcaseImovel.banheiros` is always `None` on this tenant, silently.**
Verified live 2026-08-03 via a clean-env call to `vista.imoveis.get`.

`BanheiroSocial` is a yes/no flag, not a count — the `or` fallback conflates two
different types. This is a no-silent-errors violation (`KB § 01-PHILOSOPHY.md`).
Fix belongs with P2.1, since the canonical model splits the two fields anyway.

## Proposed canonical `Imovel` model (Phase 2 — NOT yet ratified)

Three layers so the wire never leaks upward:

```
1. Vista wire payload   — verbatim, all strings, preserved as JSONB (audit + re-migration)
2. Imovel               — canonical typed domain model    ← the new artifact
3. social_wiring.imoveis — persistence
```

| Group | Fields |
|---|---|
| **Identidade** | `codigo` (PK, `^ONE\d{3,6}$`), `codigo_imobiliaria`, `origem` (`vista`\|`manual`), `sincronizado_em` |
| **Classificação** | `titulo`, `categoria`, `status`, `finalidade` ← derived from `FinalidadeStatus` (W4) |
| **Localização** | `cep`, `logradouro`, `numero`, `complemento`, `bairro`, `cidade`, `uf`, `empreendimento`, `latitude`, `longitude` |
| **Comercial** | `valor_venda`, `valor_locacao` (`None` when `"0"` — W3) |
| **Dimensões** | `area_total`, `area_privativa`, `area_construida` (`None` when `"0"` — W3) |
| **Cômodos** | `dormitorios`, `suites`, `vagas`, `banheiro_social: bool` ← **bool, not int** (fixes the W-bug above) |
| **Mídia** | `foto_destaque`, `fotos[]` |
| **Atribuição** | `corretores[]` ← **list**, not first-only (W7); `construtora` |
| **Datas** | `data_cadastro: date`, `data_atualizacao: date` (`DataAtualizacaoDias` derived — W9) |
| **Características** | `caracteristicas: set[slug]` — only the `"Sim"` ones (14 of 76 on ONE10107) + raw dict preserved |
| **Auditoria** | `vista_raw: JSONB` |

**Design call — `caracteristicas` as a slug set, not 76 boolean columns.** The key
set is tenant-defined and drifts, so columns would need a migration per new
amenity. A set also makes "quais imóveis têm piscina" a containment query.

## Trigger conditions (the "when")

| # | Trigger | Detection signal | Why it tips the balance |
|---|---|---|---|
| T1 | User ratifies the field set above | Explicit "yes, build it" on the `Imovel` table | The whole point of Phase 1 was to review the shape first; building before ratification inverts that. |
| T2 | Multi-tenant Vista need appears | A second tenant key beyond `oneconsu-rest` | Field calibration is per-tenant; the model must not bake `oneconsu` assumptions. |
| T3 | ERP + social-wiring both need the same `Imovel` | Second consumer of the canonical model | Promotes `Imovel` from product-local to `noctusai_lib.domain.real_estate` (replication-to-seed symmetry). |
| T4 | Write-back to Vista requested | User asks to edit an imóvel and push to CRM | `mcp/vista` is read-only v1; POST tooling is unbuilt. |

**Today's status**: none fired. T1 is the immediate next gate.

## Phase 1 — Vista MCP registration + this design record (SHIPPED)

| # | Title | Files | Status | Verify recipe (live-state proof, not unit tests) |
|---|---|---|---|---|
| P1.1 | Register `vista` MCP server | `.mcp.json` (gitignored, primary checkout only) | **shipped** | `python3 -c "import json;print('vista' in json.load(open('.mcp.json'))['mcpServers'])"` → `True`; stdio boot probe logs `10 tools registered`. Both run 2026-08-03. |
| P1.2 | Supply per-tenant creds to the MCP | `mcp/vista/.env` (gitignored) | **shipped** | `env -u VISTA_BASE_URL -u VISTA_API_KEY` + direct call to `vista.imoveis.get({"codigo":"ONE10107"})` returned the real listing — proves creds resolve from `mcp/vista/.env` alone, not the ambient shell. Run 2026-08-03. |
| P1.3 | Live-fetch ONE10107 + document the wire shape | This doc, §"The live wire shape" | **shipped** | Raw payload captured; 30-vs-27 key asymmetry + 10 quirks + the `banheiros` bug recorded above. |
| P1.4 | This roadmap | `project-history/roadmaps/social-wiring-imoveis-vista-2026-08.md` | **shipped** | File exists on `feat/social-wiring-imoveis-vista`. |

**Behavior guarantee**: nothing changes at runtime for any product. `.mcp.json`
and `mcp/vista/.env` are gitignored local config; the only tracked file is this
doc. No product code, no migration, no nav change.

**Why ship now**: the MCP registration was pure drift (server built, never wired
— `KB § PATTERNS/common/drift-fix-on-contact.md`), and the wire analysis is the
perishable part. A context reset loses the ONE10107 findings otherwise.

**Why P1.2 was not optional**: `mcp/vista/settings.py` reads `mcp/vista/.env`,
NOT the root `.env`. Registering without the creds file would have produced a
server that boots cleanly and then returns `VistaConfigError` on every call —
exactly the half-shipped shape `KB § 03-SEED-ARCHITECTURE.md` forbids.

## Phase 2 — the canonical `Imovel` model + Imóveis section (DEFERRED — fires on T1)

| # | Title | Files | Trigger | Verify recipe (write it now, run it when it ships) |
|---|---|---|---|---|
| P2.1 | `Imovel` Pydantic model + `vista_imovel_to_imovel` normalizer; fix the `banheiros`/`banheiro_social` type conflation | `noctusai_lib/domain/real_estate/` (NEW `imovel.py`), `integrations/vista/normalizers.py` (EDIT) | T1 | Round-trip the captured ONE10107 payload through the normalizer; assert `banheiro_social is True`, `valor_locacao is None`, `finalidade == "venda"`, `len(caracteristicas) == 14`. |
| P2.2 | Migration `040_imoveis.sql` — `social_wiring.imoveis` + RLS + `status_pagina` row | `products/social-wiring/backend/migrations/040_imoveis.sql` (NEW) | T1 | Apply to dev; `SELECT` as a non-owner role returns only own-org rows; confirm the `status_pagina` row exists (see the §Gotcha below). |
| P2.3 | Backend router `imoveis_router.py` — list/get/sync-from-Vista | `products/social-wiring/backend/app/routers/imoveis_router.py` (NEW), `main.py` (EDIT) | T1 | `curl` the route authenticated → real rows; unauthenticated → strict `== 401`. |
| P2.4 | Sidebar item + `Imoveis.tsx` / `ImovelDetalhes.tsx` | `products/social-wiring/frontend/src/App.tsx` (EDIT — **both** `NAV_GROUPS` and `NAV_FALLBACK`), `src/pages/imoveis/` (NEW) | T1 | Load the page in the running container; see real Vista-sourced rows, not fixtures. Nav item actually visible. |
| P2.5 | Wire `product_code` consumers to the new store | `intake_monitor_router.py`, `settings_router.py`, youtube dashboard (EDIT) | T1 | An ONE-code arriving via WhatsApp intake resolves against `social_wiring.imoveis` instead of a live Vista call. |

**Trigger**: T1 — user ratifies the field set.

**Why not now**: the user explicitly asked to see the data before continuing.
Building the table before the field set is ratified would make P2.2 a rewrite.

### ⚠️ Gotcha that will silently break P2.4 if skipped

A new sidebar item needs a matching `status_pagina` row or the seed's
`filterNavByPageStatus` gate **hides it with no error anywhere** — the page and
route work if you type the URL, but the link never appears. Precedent:
`039_n8n_nav_route.sql`, and migrations 018/021/023 exist to close the same
silent failure. Seed as `'desenvolvimento'` first, flip to `'producao'` once
proven end-to-end. → `KB § PATTERNS/frontend/status-pagina-dev-visibility.md`

## Phase 3 — promote `Imovel` to the seed (DEFERRED — fires on T3)

| # | Title | Files | Trigger | Verify recipe |
|---|---|---|---|---|
| P3.1 | Move `Imovel` from product-local to `noctusai_lib.domain.real_estate` | `noctusai_lib/domain/real_estate/imovel.py` | T3 | Both consumers import from the seed; `check_canonical_organ_consumption` passes. |
| P3.2 | Reconcile with ERP's `erp.ativos` shape | ERP migration | T3 | Field-by-field mapping documented; no silent divergence. |

**Why not now**: one consumer. Promoting at N=1 is speculative generality; the
recurrence rule says N=2 triage, N=3 formalize.

## Anti-goals (explicit non-goals)

- ❌ **Not touching `erp-imobiliario`'s `/imoveis`.** It has its own model on `erp.ativos`, independent of Vista. Conflating them is a migration, not a toggle.
- ❌ **Not building a new Vista adapter.** The seed already ships Fake+Real+factory. Any new adapter is a structural fork.
- ❌ **Not writing back to Vista.** `mcp/vista` is read-only v1 (T4 gates this).
- ❌ **Not modeling `Caracteristicas` as boolean columns.** Tenant-defined and drifting — a migration per amenity.
- ❌ **Not committing `.mcp.json` or `mcp/vista/.env`.** Both gitignored by design; creds never enter git.
- ❌ **Not hardcoding the calibrated field list.** `mcp/vista/calibration.py` discovers it per tenant; hardcoding re-creates the Phase-4.5 showcase incident the calibrator exists to prevent.

## Open questions (to revisit at trigger time)

- **Q1**: Is `codigo` (the ONE-code) a sufficient PK, or does social-wiring need a surrogate UUID + org scoping? Every other social-wiring table is org-scoped; the ONE-code is tenant-global. Likely `(org_id, codigo)`.
- **Q2**: Sync strategy — on-demand fetch, scheduled pull, or webhook? Vista offers no webhooks that we've confirmed, so likely scheduled. `DataAtualizacaoDias` gives a cheap staleness check.
- **Q3**: Which of the 76 `Caracteristicas` keys are worth surfacing in the UI? 14 are `"Sim"` on ONE10107; the useful subset is probably ~15–20 fleet-wide.
- **Q4**: How to handle the W6 duplicate-key collision — merge with OR, or preserve both and surface the tenant data-quality issue?
- **Q5**: Does the user want manual (non-Vista) imóveis in the same table (`origem='manual'`), or Vista-only?

## Decision log

- **2026-08-03**: Chose social-wiring as the target product (user-selected) over erp-imobiliario, which already has an `/imoveis` page on a different model.
- **2026-08-03**: Registered `vista` in `.mcp.json` + created `mcp/vista/.env` — the server was built but never wired, and its settings module reads its own co-located `.env`, so both legs were required for a working registration.
- **2026-08-03**: Deferred all model-building to Phase 2 behind T1. The user asked to review the wire shape before continuing; building first would invert that.
- **2026-08-03**: Chose `caracteristicas: set[slug]` over boolean columns — tenant-defined key set that drifts.
- **2026-08-03**: Recorded the `banheiros`-always-`None` normalizer bug rather than hot-fixing it, because P2.1 splits the field anyway and a standalone fix would be reverted by it.

## Retrospective (filled at first trigger fire)

*To be filled when Phase 2 fires. Capture:*
- *Was the field set above sufficient, or did the first real UI reveal gaps?*
- *Did the 10 documented quirks cover the real normalizer, or did more surface?*
- *Did a second tenant break the per-tenant calibration assumption?*

## Composes with

- `KB § INTEGRATIONS/vista.md` — the Vista API contract; §5.2 is the normalizer field-mapping spec, §6 the calibration sketch.
- `KB § PATTERNS/frontend/status-pagina-dev-visibility.md` — the P2.4 gotcha.
- `KB § PATTERNS/common/drift-fix-on-contact.md` — why P1.1/P1.2 shipped in a planning session.
- `KB § PATTERNS/backend/seed-fake-real-adapter.md` — why no new adapter is needed.
- `mcp/vista/README.md` — operations doc + Phase 1 known limitations.

## File trail

- `.mcp.json` — `vista` server entry (gitignored; primary checkout only).
- `mcp/vista/.env` — per-tenant creds (gitignored).
- This doc.
