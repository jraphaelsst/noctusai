# social-wiring-imoveis-vista-2026-08 — Imóveis sidebar section for social-wiring, modeled on live Vista CRM data

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: user asked for a new "Imóveis" sidebar toggle in social-wiring to store "my actual products", modeled from what the Vista CRM actually returns.
> Decision: **Phase 1 ships the Vista MCP registration + this design record only. No product code — the canonical `Imovel` model is designed here and built in Phase 2, after the user ratifies the field set.**
>
> **Status 2026-08-03 (census pass).** Phase 1 shipped and merged. The session was
> reset so the MCP would connect — it does (`vista.diagnostics.probe` → `configured:
> true`). T1 has **not** fired: the user declined to ratify off a single imóvel, so
> this pass censused the whole 1919-imóvel catalog instead of building. Design
> constraints **D1/D2/D3** are now user-ratified (see Decision log); **P2.0** was
> inserted because Phase 2 as written could not be built; and a **blocking live bug**
> unrelated to this feature was found (the ONE-code validator — 🔴 below).
> Next gate is still T1.

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

## The live wire shape — catalog-wide census (2026-08-03, tenant `oneconsu-rest`)

> **Provenance.** Phase 1 characterized the wire from a single imóvel (`ONE10107`).
> The user declined to ratify off n=1, so a second pass censused the **whole
> catalog**: all 1919 rows via `/imoveis/listar` (39 pages, 7.2s, 0 failures) plus a
> stratified `/imoveis/detalhes` sample of 75 covering **all 20 `Categoria` values
> and all 3 `Status` values** (0 failures). Every figure below is a measured count
> over one of those two populations — the denominator is always stated.
>
> Two of the ten Phase-1 quirks did **not** survive the larger sample. They are
> struck through rather than deleted, because the corrected claim is the load-bearing
> one and a silently-edited doc hides that the model nearly baked in a wrong premise.

`/imoveis/detalhes` returns 30 keys; `/imoveis/listar` returns 27. **They are not
the same set** — this asymmetry is the single most important modeling fact, and it
held on **75/75** sampled imóveis.

- **listar-only:** `FotoDestaque`, `BanheiroSocial`, `CodigoImobiliaria`, `Corretor_Codigo`
- **detalhes-only:** `Caracteristicas`, `Numero`, `Complemento`, `Empreendimento`, `Construtora`, `FinalidadeStatus`, `DataAtualizacaoDias`

Any complete `Imovel` requires **both** calls. `vista.imoveis.get` already does
this (it prefetches the listing row for `FotoDestaque`).

### Catalog shape (n=1919)

| Dimension | Measured |
|---|---|
| Total imóveis | **1919** (39 pages @ 50) |
| `Status` | `Venda` 1715 (89.4%) · `Venda e Aluguel` 138 (7.2%) · `Aluguel` 66 (3.4%) |
| `Categoria` | 20 distinct. Long tail: `Casa em Condomínio` 1308 + `Terreno em Condomínio` 294 + `Apartamento` 101 = 89% of catalog; 9 categorias have ≤6 imóveis |
| `Cidade` | 18 distinct — incl. the casing duplicate `Embu das Artes` / `Embu Das Artes` (both live, not just in the filter enum) |
| `Bairro` | 428 distinct |
| `DataCadastro` | spans 2012 → 2026; 58% cadastrado in 2025–26 |
| Duplicate `Codigo` | **0** — `codigo` is a safe natural key within the tenant |

### Wire quirks the model must encode

| # | Quirk | Measured over the census | Modeling consequence |
|---|---|---|---|
| W1 | Every scalar is a **string** | Holds on 1919/1919 for all listar fields. Exactly **three** non-string types exist: `Caracteristicas` (dict), `FinalidadeStatus` (dict), `DataAtualizacaoDias` (int) — plus `Corretor`, see W7 | Coerce at the adapter boundary; never let strings reach the app layer. |
| W2 | ~~Empty is `""`, never `null`~~ **WRONG — `null` does occur** | `CodigoImobiliaria` is JSON `null` on **38/1919** rows (e.g. `ONE5375`, `ONE6397`). Every other field uses `""` | Normalizers must handle `None` **and** `""`. A `"" → None` rule alone is not enough; a `.strip()` on a `null` raises. |
| W3 | `"0"` is **overloaded** — and far more widespread than n=1 suggested | `AreaConstruida` is `"0"` on **1918/1919 (99.9%)** — the field is effectively dead on this tenant. `ValorLocacao` `"0"` on 1488 (77.5%, all `Venda`). `Vagas` 512 · `Suites` 477 · `Dormitorios` 405 · `AreaPrivativa` 354. `ValorVenda` `"0"` on 64 — **63 of them are the `Aluguel` rows** (the inversion), 1 is a `Venda` data-quality defect | `"0" → None` for money + area. For `Dormitorios`/`Suites`/`Vagas`, `"0"` is genuinely *zero* on a Terreno — do **not** blanket-null those. Current seed `_to_float` returns `0.0`, so "R$ 0" / "0 m²" renders on ~78% / ~100% of the catalog today. |
| W3b | `ValorLocacao` has **three** states, not two | `"0"` 1488 · real value 232 · `""` 199 | `""` (unknown) and `"0"` (not for rent) both → `None`, but they are not the same fact. |
| W4 | ~~`Finalidade` is always empty~~ **PARTLY WRONG** | `Finalidade` is non-empty on **287/1919 (15.0%)** — not 0%. `FinalidadeStatus` (detalhes-only) is present on 75/75 and is a clean 2-key enum: `VENDA` (70) · `ALUGUEL` (15). `Finalidade` empty *while* `FinalidadeStatus` populated on 35/75 | `FinalidadeStatus` is still the right source — but it is **detalhes-only**, so a listar-only sync cannot derive `finalidade` at all. Falling back to `Status` (100% populated, 3 values) is the list-view answer. |
| W5 | `Caracteristicas` keys are de-camelized with inserted spaces | `"Sala T V"`, `"T V Cabo"`, `"W C Empregada"` — confirmed across the 76-key set | Slug normalization must collapse inserted spaces. |
| W6 | `Caracteristicas` carries a real collision — **exactly one** | Full slug census over the 76-key space: **1** collision pair, `"Dependenciade Empregada"` (Sim on 6/75) + `"Dependencia De Empregada"` (Sim on 7/75) → both slug to `dependenciadeempregada` | One pair, obviously the same amenity with a tenant typo. Merge with OR is safe and is the answer to Q4. |
| W7 | `Corretor` is **polymorphic**, and multi-corretor is common | dict on 1903/1919, **`[]` (empty list) on 16**. Among the dicts: 1 corretor 1651 (86.0%) · **2 corretores 246** · **3 corretores 6**. So **252 imóveis (13.1%) have >1 corretor** | `_first_corretor_nome` silently drops the 2nd/3rd for 13% of the catalog. `corretores[]` as a list is **not** speculative generality — it is required. Also handle the `[]` shape. |
| W8 | `Empreendimento` may duplicate `Bairro` | `Empreendimento` non-empty on 67/75 (89.3%); `Construtora` on only 7/75 (9.3%) | Don't render both blindly. `Construtora` is too sparse to surface prominently. |
| W9 | `DataAtualizacaoDias` is the only **int** on the wire | present + int on 75/75 | Derived — compute from `DataAtualizacao`, don't store. |
| W10 | Address is split and unprefixed | `Numero` non-empty on 75/75, `Complemento` on 62/75 (82.7%) | Store parts; compose for display. |
| **W11** | **`Codigo` is not ONE-prefixed** ← new | 6 prefixes live: `ONE` 1634 (85.1%) · `CA` 177 · `TE` 84 · `AR` 10 · `AP` 7 · `GA` 6 · `PR` 1. Digit width is 4 or 5 | See the blocking bug below. |
| **W12** | **`Caracteristicas` is a fixed tenant-wide schema** ← new | **Exactly 76 keys on all 75/75** sampled imóveis, across all 20 categorias. Value vocabulary is exactly `{"Sim", "Nao"}` — 462 Sim / 5238 Nao, no third value, no empties. 48 keys are `Sim` somewhere; **28 are never `Sim`** on any sampled imóvel | The key set does not vary per imóvel — only per tenant. `set[slug]` stays the right design (per-tenant drift is still real), but the "76 booleans" fear is a per-tenant concern, not per-row. Clean bool coercion: `== "Sim"`. |

### 🔴 Blocking bug — the ONE-code validator rejects 15% of the catalog

`noctusai_lib/domain/real_estate/validators.py:13`:

```python
PRODUCT_CODE_PATTERN = re.compile(r"^ONE\d{3,6}$")
```

Measured against the live catalog: **285 of 1919 imóveis (14.9%) fail this
pattern** — every `CA`, `TE`, `AR`, `AP`, `GA` and `PR` code.

This is not a Phase-2 modeling concern. `validate_product_code` is enforced at
**9 live call sites**, including `integrations/vista/real.py:77`, which guards
`get_property` itself:

| Call site | Effect on the 285 |
|---|---|
| `integrations/vista/real.py:77` + `:250` | `get_property` / `update_property_video_url` refuse the code before any HTTP call — the imóvel is unfetchable through the seed adapter |
| `whatsapp_intake_service.py` `:485` `:569` `:642` `:983` | a `CA…`/`TE…` code sent over WhatsApp is silently not recognized |
| `youtube/routers/upload.py:231` | cannot attach a video to those imóveis |
| `whatsapp_intake_service.py:59` `:191` + `conversation_module.py:79` | the *extraction* regexes `\bONE\d{3,6}\b` never even find a non-ONE code in message text |

**Fix-on-contact candidate, ahead of P2.1** — this is a live silent-drop today,
independent of whether the Imóveis section is ever built. The regex encodes a
premise ("all product codes start with ONE") that the tenant's own catalog
contradicts. Suggested shape: `^[A-Z]{2,4}\d{3,6}$`, tenant-configurable rather
than hardcoded — the same lesson as the calibrated field set.

### Confirmed latent bug (folded into P2.1)

`noctusai_lib/integrations/vista/normalizers.py:104`:

```python
banheiros=_to_int(payload.get("Banheiros") or payload.get("BanheiroSocial")),
```

On `oneconsu-rest`, `Banheiros` is permission-denied (calibration drops it from
both the listar and detalhes field sets) and `BanheiroSocial` carries `"Sim"`/`"Nao"`.
`_to_int("Sim")` raises `ValueError` internally and returns `None`. So
**`ShowcaseImovel.banheiros` is `None` on 1919/1919 rows — the entire catalog**,
silently. Confirmed across the full census, not just `ONE10107`.

`BanheiroSocial` is a yes/no flag, not a count — the `or` fallback conflates two
different types. This is a no-silent-errors violation (`KB § 01-PHILOSOPHY.md`).
Fix belongs with P2.1, since the canonical model splits the two fields anyway.

### Sync feasibility (measured, drives D2)

Timed `/imoveis/detalhes` batches against the live tenant, 24 calls each, 0 errors
at every level:

| Concurrency | Wall (24 calls) | p50 latency | Projected for 1919 |
|---|---|---|---|
| 1 | 20.1s | 663 ms | **~26.7 min** |
| 4 | 4.3s | 691 ms | **~5.7 min** |
| 8 | 3.1s | 852 ms | **~4.1 min** |

No 429s, no throttling, latency degrades only mildly at 8. **D2 (full detalhes for
all 1919) is viable** — roughly 4–6 minutes per full sync at concurrency 4–8.

⚠️ `client.py:147` already carries `NOC-REMEDIATE[rate-limit]` naming this exact
scenario: *"a property-list sync loop should be paced before it grows."* The sync
job is that loop. Pacing via `rate_limit.acquire_async("vista")` should land
**with** P2.3, not after it.

### `DataAtualizacao` — the staleness question, settled

Phase 1's page-1 observation (every row dated today) was a **recency-ordering
artifact**, not a property of the field. Over all 1919 rows: **36 distinct dates**
spanning `2026-06-23` → `2026-08-03`. It is a genuine per-imóvel change marker.

But the oldest value is only ~6 weeks back while `DataCadastro` reaches 2012 —
so the tenant touches every listing within a ~6-week window regardless. An
incremental sync keyed on `DataAtualizacao` would therefore re-fetch the whole
catalog every ~6 weeks anyway. **D1 (full pull) stands, now on evidence rather
than on a wrong premise.** `DataAtualizacaoDias` remains useful as a per-imóvel
"last touched" display value.

## Proposed canonical `Imovel` model (Phase 2 — NOT yet ratified)

Three layers so the wire never leaks upward:

```
1. Vista wire payload   — verbatim, all strings, preserved as JSONB (audit + re-migration)
2. Imovel               — canonical typed domain model    ← the new artifact
3. social_wiring.imoveis — persistence
```

| Group | Fields | Census note |
|---|---|---|
| **Identidade** | `codigo` (natural key, `^[A-Z]{2,4}\d{3,6}$` — **not** ONE-only, W11), `codigo_imobiliaria` (**nullable — JSON `null` on 38 rows**, W2), `origem` (`vista`\|`manual`), `sincronizado_em` | 0 duplicate `codigo` across 1919 |
| **Classificação** | `titulo`, `categoria`, `status`, `finalidade` ← `FinalidadeStatus` when detalhes present, else derived from `status` (W4) | `status` 100% populated, 3 values; `categoria` 20 values |
| **Localização** | `cep`, `logradouro`, `numero`, `complemento`, `bairro`, `cidade`, `uf`, `empreendimento`, `latitude`, `longitude` | lat/long **empty on 36.8%** — the map view needs a no-geo branch |
| **Comercial** | `valor_venda`, `valor_locacao` (`None` when `"0"` **or** `""` — W3/W3b) | `valor_venda` real on 96.5%; `valor_locacao` real on only **12.1%** |
| **Dimensões** | `area_total`, `area_privativa`, `area_construida` (`None` when `"0"` — W3) | `area_construida` is `"0"` on **99.9%** — consider dropping it from the UI entirely |
| **Cômodos** | `dormitorios`, `suites`, `vagas` (**`0` is a real value here, not null** — W3), `banheiro_social: bool` ← **bool, not int** (fixes the normalizer bug above) | `banheiro_social` is the *only* bathroom signal this tenant exposes; `Banheiros` is permission-denied |
| **Mídia** | `foto_destaque`, `fotos[]` | `FotoDestaque` non-empty on 1919/1919 |
| **Atribuição** | `corretores[]` ← **list**, not first-only (W7); `construtora` | **252 imóveis (13.1%) have 2–3 corretores**; `construtora` populated on only 9.3% |
| **Datas** | `data_cadastro: date`, `data_atualizacao: date` (`DataAtualizacaoDias` derived — W9) | `data_atualizacao` spans 36 distinct dates — a real change marker |
| **Características** | `caracteristicas: set[slug]` — only the `"Sim"` ones + raw dict preserved | **76 keys on every imóvel**, values exactly `{"Sim","Nao"}`; 48 keys used, 28 never `Sim` |
| **Auditoria** | `vista_raw: JSONB` | |

**Design call — `caracteristicas` as a slug set, not 76 boolean columns.** The key
set is tenant-defined and drifts, so columns would need a migration per new
amenity. A set also makes "quais imóveis têm piscina" a containment query.
The census strengthens this: the key set is **identical on all 75 sampled imóveis**,
so per-row variance is zero and only per-tenant drift is real — exactly the case a
slug set handles and columns do not.

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
| **P2.0a** | **Lift per-tenant calibration into the seed.** Today it lives only in `mcp/vista/calibration.py`; a product-side sync needs it, and hardcoding the field list is an explicit anti-goal below | `noctusai_lib/integrations/vista/calibration.py` (NEW — moved), `mcp/vista/calibration.py` (becomes a re-export or is deleted), `mcp/vista/tools/*.py` (EDIT imports) | T1 | `vista.diagnostics.show_calibrated_fields` still returns the same 25-field listar set after the move; MCP smoke test green. |
| **P2.0b** | **Widen the Fake+Real seam.** `VistaCRMAdapter` exposes only `get_property() -> PropertyData`; nothing list-shaped crosses it, so a sync would have to reach past the seam to `VistaClient` | `integrations/vista/protocol.py` (EDIT — add `list_properties`), `real.py` + `fake_adapter.py` + `fake.py` (EDIT — both sides ship it) | T1 | Fake and Real both implement the new method (no half-ship — `KB § PATTERNS/backend/seed-fake-real-adapter.md`); factory returns either transparently. |
| **P2.0c** | **Fix the ONE-code validator** (see 🔴 above — rejects 14.9% of the live catalog at 9 call sites) | `noctusai_lib/domain/real_estate/validators.py` (EDIT), extraction regexes in `whatsapp_intake_service.py` + `conversation_module.py` (EDIT) | **none — ship ahead of T1**; this is a live silent-drop, not a modeling concern | Assert `validate_product_code` accepts `CA0190`, `TE1234`, `AR0001`, `AP0412`, `GA0001`, `PR0001` and still rejects `FOO`, `ONE`, `ONE12`. Replay a WhatsApp body containing `CA0190` through the intake extractor and assert the code is found. |
| P2.1 | `Imovel` Pydantic model + `vista_imovel_to_imovel` normalizer; fix the `banheiros`/`banheiro_social` type conflation | `noctusai_lib/domain/real_estate/` (NEW `imovel.py`), `integrations/vista/normalizers.py` (EDIT) | T1 | Round-trip real captured payloads (census sidecars, 1919 listar + 75 detalhes) through the normalizer; assert `banheiro_social` is a bool on 1919/1919, `valor_locacao is None` on the 1488 `"0"` rows, `area_construida is None` on the 1918 `"0"` rows, `dormitorios == 0` (**not** `None`) on Terrenos, `len(corretores) > 1` on the 252 multi-corretor rows, and `codigo_imobiliaria is None` on the 38 JSON-null rows. |
| P2.2 | Migration `040_imoveis.sql` — `social_wiring.imoveis` + RLS + `status_pagina` row | `products/social-wiring/backend/migrations/040_imoveis.sql` (NEW) | T1 | Apply to dev; `SELECT` as a non-owner role returns only own-org rows; confirm the `status_pagina` row exists (see the §Gotcha below). |
| P2.3 | Backend router `imoveis_router.py` — list/get/sync-from-Vista. Sync = **full pull, listar + detalhes for all ~1919** (D1+D2), paced via `rate_limit.acquire_async("vista")` (discharges the `NOC-REMEDIATE[rate-limit]` marker at `client.py:147`) | `products/social-wiring/backend/app/routers/imoveis_router.py` (NEW), `services/imoveis_sync_service.py` (NEW), `main.py` (EDIT) | T1 | `curl` the route authenticated → real rows; unauthenticated → strict `== 401`. A full sync completes in **4–6 min** at concurrency 4–8 (measured) with 0 upstream errors, and is idempotent — running it twice leaves 1919 rows, not 3838. |
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

## Phase 3 — ~~promote `Imovel` to the seed~~ **SUPERSEDED by D3**

> **P3.1 is cancelled — folded into P2.1.** The user ratified building `Imovel`
> directly in `noctusai_lib.domain.real_estate` from day one (D3), so there is no
> product-local → seed promotion step to run. The original N=1-speculative-generality
> reasoning assumed `erp-imobiliario`'s VistaShowcase was a real consumer that might
> or might not converge; the user has since clarified it was a throwaway connection
> test. The seed already houses the Vista client, normalizers and `Showcase*` types —
> putting the canonical model anywhere else would split real-estate domain knowledge
> across two homes for no gain.

| # | Title | Files | Trigger | Verify recipe |
|---|---|---|---|---|
| ~~P3.1~~ | ~~Move `Imovel` from product-local to the seed~~ | — | **cancelled** | Folded into P2.1 by D3. |
| P3.2 | Reconcile with ERP's `erp.ativos` shape | ERP migration | T3 | Field-by-field mapping documented; no silent divergence. |

**P3.2 still deferred**: `erp.ativos` is a genuinely different model on a different
schema, and nothing needs it reconciled until ERP actually consumes `Imovel`.

## Anti-goals (explicit non-goals)

- ❌ **Not touching `erp-imobiliario`'s `/imoveis`.** It has its own model on `erp.ativos`, independent of Vista. Conflating them is a migration, not a toggle.
- ❌ **Not building a new Vista adapter.** The seed already ships Fake+Real+factory. Any new adapter is a structural fork.
- ❌ **Not writing back to Vista.** `mcp/vista` is read-only v1 (T4 gates this).
- ❌ **Not modeling `Caracteristicas` as boolean columns.** Tenant-defined and drifting — a migration per amenity.
- ❌ **Not committing `.mcp.json` or `mcp/vista/.env`.** Both gitignored by design; creds never enter git.
- ❌ **Not hardcoding the calibrated field list.** The calibrator discovers it per tenant; hardcoding re-creates the Phase-4.5 showcase incident it exists to prevent. It lives in `mcp/vista/calibration.py` today — P2.0a lifts it into the seed precisely so the product side can obey this without forking.
- ❌ **Not hardcoding the amenity display list either.** Same failure shape one level up: the 76-key `Caracteristicas` space and its used/unused split are tenant-defined (28 keys are dead on `oneconsu-rest`). Derive the display set from observed usage.

## Open questions — status after the census

- **Q1 — PK.** *Still open, but narrowed.* Census settles the data half: `codigo` has **0 duplicates across 1919** and is a safe natural key *within* a tenant. It is not globally unique across tenants, and every other social-wiring table is org-scoped ⇒ `(org_id, codigo)` remains the recommendation. Needs a user call only if a surrogate UUID is wanted for FK ergonomics.
- **Q2 — Sync strategy.** ✅ **Answered by D1** — scheduled full pull + manual refresh. The census also removed the premise this question leaned on: `DataAtualizacao` *is* a real per-imóvel marker (36 distinct dates), but the tenant touches every listing inside a ~6-week window, so incremental converges to full anyway. Vista webhooks remain unconfirmed.
- **Q3 — Which `Caracteristicas` to surface.** ✅ **Answered by data.** Of 76 keys, **28 are never `"Sim"`** on any sampled imóvel (`Alarme`, `Vista Mar`, `Home Theater`, the four compass directions, …) — dead weight on this tenant. The top 20 by usage: `Cozinha` (34.7%), `Churrasqueira` (32.0%), `Area Servico` (28.0%), `Sala T V` (28.0%), `Dormitorio Com Armario` (26.7%), `Piscina` (26.7%), `Lavabo` (25.3%), `Sala Jantar` (24.0%), `Banheiro Social` (22.7%), `Agua Quente` (22.7%), `Quintal` (22.7%), `Armario Embutido` (20.0%), `Cozinha Planejada` (20.0%), `Despensa` (17.3%), `T V Cabo` (17.3%), `W C Empregada` (17.3%), `Ar Condicionado` (16.0%), `Copa` (16.0%), `Hidromassagem` (16.0%), `Vista Panoramica` (16.0%). Store all 76; surface the used 48, filter on the top ~20. Derive the display set from usage — never hardcode (same lesson as the field calibration).
- **Q4 — W6 collision.** ✅ **Answered by data.** The full slug census found **exactly one** collision pair in the 76-key space: `"Dependenciade Empregada"` + `"Dependencia De Empregada"`. Both are clearly the same amenity with a tenant-side typo. **Merge with OR**, and log the merge once at sync time so the tenant data-quality issue is visible rather than silent.
- **Q5 — Manual imóveis.** *Still open — needs a user call.* The `origem` column costs nothing to include now and cannot be added later without a migration, so P2.2 should ship it regardless.

## Decision log

- **2026-08-03**: Chose social-wiring as the target product (user-selected) over erp-imobiliario, which already has an `/imoveis` page on a different model.
- **2026-08-03**: Registered `vista` in `.mcp.json` + created `mcp/vista/.env` — the server was built but never wired, and its settings module reads its own co-located `.env`, so both legs were required for a working registration.
- **2026-08-03**: Deferred all model-building to Phase 2 behind T1. The user asked to review the wire shape before continuing; building first would invert that.
- **2026-08-03**: Chose `caracteristicas: set[slug]` over boolean columns — tenant-defined key set that drifts.
- **2026-08-03**: Recorded the `banheiros`-always-`None` normalizer bug rather than hot-fixing it, because P2.1 splits the field anyway and a standalone fix would be reverted by it.
- **2026-08-03 (census session)**: User declined to ratify off n=1 and asked for more data first. Ran a catalog-wide census (1919 listar + 75 stratified detalhes) instead of building. **This was the right call** — it overturned two of the ten documented quirks (W2, W4) and surfaced a blocking live bug (W11 / the ONE-code validator) that n=1 could not have revealed.
- **2026-08-03 — D1**: **Sync = scheduled full pull + manual refresh button.** User-ratified. Reinforced by the census: incremental keyed on `DataAtualizacao` converges to a full pull inside ~6 weeks anyway.
- **2026-08-03 — D2**: **Fidelity = full `detalhes` for all ~1919.** User-ratified. Measured as viable: 4–6 min per full sync at concurrency 4–8, 0 upstream errors. Without it, `finalidade` and `caracteristicas` are unavailable in the list view, since both are detalhes-only.
- **2026-08-03 — D3**: **`Imovel` lives in `noctusai_lib.domain.real_estate` from day one.** User-ratified, superseding the roadmap's "product-local, promote at T3". Rationale: the ERP VistaShowcase was a throwaway connection test, not a real second consumer, and the seed already houses the Vista client + normalizers + types.
- **2026-08-03 — P2.0 inserted**: Phase 2 as originally written could not be built. Per-tenant calibration existed only host-side in `mcp/vista/`, and the `VistaCRMAdapter` seam exposes nothing list-shaped — so a product-side sync would have had to either hardcode the field list (an explicit anti-goal) or reach past the Fake+Real seam. Both are structural violations, so the seed work became a prerequisite rather than a follow-up.

## Retrospective — census pass (2026-08-03)

Filled early, because the census *is* a trigger-fire of sorts and its lessons are
perishable:

- **n=1 is not a shape.** One imóvel produced ten quirks; the catalog overturned two of them (W2 `null` does occur, W4 `Finalidade` is populated 15% of the time) and added two more (W11 non-ONE codes, W12 the fixed 76-key schema). The user's instinct to ask for more data before ratifying was correct.
- **A recency-ordered first page is a trap.** Phase 1 read "every row updated today" off page 1 and nearly concluded `DataAtualizacao` was a useless feed timestamp. It is a real change marker; the ordering was the artifact. Any census over a sorted endpoint must sweep, not sample the head.
- **The most valuable finding was not about the model at all.** W11 (the `^ONE\d{3,6}$` validator rejecting 14.9% of the live catalog at 9 call sites) is a live silent-drop that has nothing to do with the Imóveis section. Censusing the real data surfaced it; modeling from the doc never would have.
- **Anti-goals earn their keep.** "Don't hardcode the calibrated field list" is what forced P2.0a to exist instead of a product-local field constant, which is what revealed the seam was too narrow at all.

*Still to fill when Phase 2 ships:*
- *Was the field set above sufficient, or did the first real UI reveal gaps?*
- *Did a second tenant break the per-tenant calibration assumption?*
- *Did the 76-key `Caracteristicas` schema hold, or did it drift within the tenant?*

## Composes with

- `KB § INTEGRATIONS/vista.md` — the Vista API contract; §5.2 is the normalizer field-mapping spec, §6 the calibration sketch.
- `KB § PATTERNS/frontend/status-pagina-dev-visibility.md` — the P2.4 gotcha.
- `KB § PATTERNS/common/drift-fix-on-contact.md` — why P1.1/P1.2 shipped in a planning session.
- `KB § PATTERNS/backend/seed-fake-real-adapter.md` — why P2.0b must ship Fake and Real together.
- `KB § PATTERNS/common/outbound-rate-limiting.md` — the `NOC-REMEDIATE[rate-limit]` marker P2.3 discharges.
- `mcp/vista/README.md` — operations doc + Phase 1 known limitations.

## File trail

- `.mcp.json` — `vista` server entry (gitignored; primary checkout only).
- `mcp/vista/.env` — per-tenant creds (gitignored).
- This doc.

**Census artifacts** (session scratchpad — *not* committed; regenerate with the recipe
below if needed):

- `vista_census.py` — the sweep + aggregation script. Imports `noctusai_lib.integrations.vista.VistaClient` and `mcp/vista/calibration.py`; reimplements nothing. Legs A (full listar sweep) and C (concurrency timing) are the prototype of the P2.3 sync loop and should be lifted rather than rewritten.
- `census_report.json` — all aggregated counts behind the figures above.
- `census_raw_listar.json` (1919 rows) / `census_raw_detalhes.json` (75 payloads) — the P2.1 normalizer round-trip fixtures.

> **Codification note.** A catalog census is repeatable and belongs beside
> `vista.diagnostics.probe` as a `vista.diagnostics.catalog_census` MCP tool
> (`KB § PATTERNS/architect/mcp-first-scripts.md`). Deliberately not built in the
> census session — the ask was data, not tooling — but it is the natural home when
> P2.0a moves calibration into the seed.
