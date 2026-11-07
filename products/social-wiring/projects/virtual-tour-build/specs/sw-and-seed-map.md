# Mapping to social-wiring and the seed (verified against the tree, 2026-11-07, base `origin/dev` 7c47982b7)

Every row was opened, not assumed. "Ships" = Protocol + Fake + Real + factory exported (skill `noc-verify-seed`, leg B).

## 1 · social-wiring today

| Need | What exists | Use |
|---|---|---|
| Imóvel entity | `social_wiring.imoveis` (migration 040) is the Vista mirror, PK `(org_id, codigo)`, and shrinks when a listing leaves the catalog. `social_wiring.imovel_registry` (063) is the permanent identity, unique `(org_id, codigo_canonical)`; `registrar_imovel` (`app/modules/imovel_hub/dados_service.py`) registers a code idempotently. `atendimento_imoveis` (181) is the FK precedent | FK `tours_virtuais (org_id, codigo_imovel)` → `imovel_registry (org_id, codigo_canonical)`; title/address/price for the viewer read from `imoveis` when present (never copied into the tour) |
| Lead pipeline | `leads` (025) + `lead_sources` dimensions (`app/modules/leads/seed_data.py` `CANONICAL_SOURCES`, provisioned by `dimensions_service.ensure_default_dimensions`). Single-lead path, as in `portal_leads/services/olx_ingest_service.py::ingest_olx_lead`: `registrar_imovel` → `leads_service.create_lead` (fires `lead_notice.avisar_lead_novo`) → `atendimento_imoveis_service.vincular_lead_seguro` | Same three calls; add source slug `tour-virtual` to `CANONICAL_SOURCES` (data, no migration) |
| WhatsApp origin | `app/services/julia_origem_service.py` resolves a Julia contact's origin; a direct message falls to `whatsapp` | v1: the button only pre-fills text. Attribution of a click to `tour-virtual` = a new precedence rule there (P5) |
| Org / roles | `get_current_user_org` (`app/dependencies.py`) + trusted role read `resolve_org_role`; agency admin roles `owner/admin/manager`, corretor roles `member/corretor` (`noctusai_lib.domain.photo_editing.types`); `app/modules/edicao_fotos/deps.py` is the role-guard precedent (`require_member`, `require_org_admin`) | Same deps; a tour module `deps.py` mirrors it (Q6 decides the edit rule) |
| Storage | Seed `StorageBackend` (`noctusai_lib.integrations.storage`: put/get/delete/list_keys/signed_url/exists; Fake, Local, Supabase; `make_storage_backend`). Edição de Fotos uses private buckets `edicao-fotos*` (migration 127) via `BucketPhotoStorage` | New private bucket `tours-virtuais`; read via `signed_url`; **upload needs `signed_upload_url` (missing, §2)** |
| Jobs | Seed `noctusai_lib.domain.jobs` (Job, `RetryPolicy`, `Worker`, `make_job_repository`); social-wiring's `jobs` table + RPCs (migration 121) already run the Edição de Fotos worker | New job type `tour_foto_ingest` (and `tour_foto_thumb` when the start view changes) on the same table and worker loop |
| Image processing | Seed `noctusai_lib.integrations.imaging` (`ImagingAdapter`: `normalize_for_edit`, `resize`, `apply_watermark`; Fake + Real Pillow + `get_imaging_adapter`) | `resize` is reused; crop, blur and XMP read are missing (§2) |
| Rate limit / abuse | `app/rate_limit.py` → `noctusai_seed.rate_limit.create_product_limiter`; seed `noctusai_lib.integrations.turnstile` (Protocol, Fake, Real, factory) — social-wiring has no consumer yet | Viewer routes rate-limited; lead form verified with Turnstile + honeypot |
| Public FE routes | `App.tsx` `publicRoutes` (`/privacidade/:slug`, `/confirmar-email/:token`, `/descadastro/:token`); backend precedent `GET /api/public/julia/privacidade/{slug}` (`@access_tier('public', category='legal-consent')`) and token links `email_marketing/routers/confirm.py` (`@access_tier('service', reason='HMAC-signed ... link token')`) | `/t/:token` joins `publicRoutes`; backend `/api/public/tours/{token}/…` (tier per Q1) |
| Navigation | `frontend/src/nav/navGroups.ts` group "Imóveis" (`/imoveis`) | New leaf "Tours virtuais" `/tours` in "Imóveis"; a "Tour virtual" panel on `ImovelDetalhes` |
| Branding | Branding / brand kits in `marcas` (046, 205) | Viewer logo + colours (Q7) |
| Upload UI helpers | Seed FE `api.upload` (timeout `UPLOAD_TIMEOUT_MS`), `upload-refusal`, `UploadErro` organ, `job-polling` (the one way to poll a job), `imageUpload.prepareImageForUpload` | Reuse `job-polling`, `UploadErro`, `upload-refusal`; **never** `prepareImageForUpload` on panoramas |
| Drag-to-reorder | `@dnd-kit` already in seed FE (`components/kanban/SortableKanbanColumn.tsx`) | Photo grid reorder |
| 360 viewer | **None** in the repo (no `photo-sphere-viewer`, `pannellum`, `marzipano`, `aframe` in any `package.json`) | New seed FE organ, D-T6 |

## 2 · Seed verification (skill `noc-verify-seed`)

Leg A (discovery): `noctus.dev.code_similar_to_text` and `noctus.dev.find_reusable_component` returned nothing (embedding caches answered empty this run — treated as unmeasured, then confirmed by grep): no panorama, equirect, 360-viewer or signed-upload code exists in `seed/lib` or any product.

| Seed surface | Status | Slice |
|---|---|---|
| `integrations.storage` read/write/signed read | Ships (Protocol, Fake, Local, Supabase, factory) | consume |
| `StorageBackend.signed_upload_url(bucket, key, expires_in_seconds)` | **Missing** — extend Protocol + Fake + Local + Supabase (`create_signed_upload_url`) together, never one side | S2 |
| `StorageBackend.signed_urls` (batch) | Missing; optional — a manifest of 30 photos × 3 variants = 90 signatures; loop first, measure, batch only if slow | S5 (measure) |
| `integrations.imaging` resize | Ships | consume |
| imaging `crop`, `gaussian_blur`, `read_xmp` | **Missing** — extend `ImagingAdapter` Protocol + Fake + Real together | S1 |
| `integrations.panorama` (`EquirectImage`, `PanoramaSource`, `FakePanoramaSource`, `Camera360Source`, `make_panorama_source`, `ingest_equirect`) | **New** seed module (Fake + Real + factory in one change) | S1 |
| `domain.jobs` | Ships | consume |
| `integrations.turnstile` | Ships | consume |
| FE `PanoramaViewer` organ (`@noctusai/lib/panorama`) | **New** seed FE organ + `organ.yaml` + vitest; dependency added to the seed lib frontend and checked fleet-wide with `noctus.dev.check_framework_deps` | S3 |

Why seed and not product-local: any real-estate product (erp-imobiliario when it wakes, a future captação app) needs the same viewer and ingest; "if another product will need it, build it shared from day one" (CLAUDE.md §1). Tables and routes stay product-side.

## 3 · Access tiers (`KB § PATTERNS/security/access-tiers.md`)

| Surface | Tier | Note |
|---|---|---|
| Editor routes `/api/tours…` | `org` | through `get_current_user_org` (resolves transitively, no marker) |
| Viewer routes `/api/public/tours/{token}…` | **pending Q1** | recommended `service` (capability token verified in the handler, like `confirm.py`); otherwise a new public category. Rate-limited either way |
| Lead form POST | `service` under Q1(a) / `public` `lead-capture` under Q1(b) | Turnstile + honeypot + limiter |
| Tables | `org` (`COMMENT ON TABLE … 'tier:org'`), `authenticated` SELECT by org policy, writes service role only | `tour_visitas` and `tour_links`: **no browser grant** (service role only) — visits are written by the anonymous API, links are capabilities |

## 4 · Viewer library comparison (to re-verify in S3)

| | Photo Sphere Viewer v5 | Pannellum | Marzipano |
|---|---|---|---|
| Licence | MIT | MIT | Apache-2.0 |
| Engine | three.js | own WebGL | own WebGL |
| Pins/markers, tour links, autorotate, gyroscope | plugins for each | hotspots, scenes, autorotate, orientation | hotspots, scenes; autorotate via API |
| Fit | best: editor needs click-to-place markers and programmatic rotation | good for viewer, weaker editor ergonomics | low activity |

Library activity figures gathered for the study are in `[private study: specs/phone-to-360-implementation-options.md]` § Sources; S3 re-checks them on its date.
