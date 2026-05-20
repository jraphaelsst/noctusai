# media-creator-w2-4 — Project Document

> Living doc. Phase plan suggestive, not strict. Phase status icons: `✅` shipped · `⏳` in-progress · `❌` failed · `🔒` blocked.

- **Created:** 2026-05-20
- **Last updated:** 2026-05-20 (close-out)
- **Status:** Phases 1–4 ✅ shipped — Phase 5 (eval loop) genuinely blocked (media-creator/evals/ is empty; nothing to port)
- **Owner / stakeholders:** USER · architect (this session)
- **Related docs:**
  - `products/social-wiring/MASTER-PROMPT.md` — host product scope
  - `../../media-creator/` (sibling repo) — design reference (agent-driven file-based prototype)
  - `KB § PATTERNS/seed-fake-real-adapter.md` — adapter shape for image-gen gap
  - `KB § PATTERNS/methodology-codification-pipeline.md` — for the image-gen seed gap surfaced below
- **Project slug:** `media-creator-w2-4` — single-product (social-wiring), so lives under `products/social-wiring/projects/`. Intent: `expansion` (adds a new module to social-wiring).

---

## 1. Context & Purpose

`social-wiring` today is a media-wiring CMS — it ingests media (audio/image/PDF/video into the chatbot), uploads to YouTube, runs email campaigns, schedules real-estate appointments. It is the **distribution** arm of a social-media automation product.

What it lacks: **the creation arm** — the system that *produces* the media that gets distributed. Today an operator must hand-author posts in Canva / Figma / Photoshop and feed them to the upload pipeline.

The sibling `media-creator/` repo is a 5-skill agent-driven prototype that proves the abstraction: turn an idea + a brand kit (PERSONA + DESIGN-SYSTEM + REFERENCES) into a publish-ready package (storyboard + image prompts + caption + hashtags + alt text). It already produced one complete Instagram carousel (`post1-3-condominios-cotia/`). It is **agent-driven, file-based, single-tenant** — exactly the wrong shape for a multi-tenant SaaS product.

This project ports the *abstraction* (skill-decomposed, reference-fidelity-first, artifact-first output) into social-wiring as **module W2.4 `media_creation`**, persisted to Supabase under `social_wiring` schema with org-scoped RLS — making it multi-tenant, API-driven, and FE-composable.

**The win:** a social-wiring operator clicks "New post" → picks a brand → types an idea → an LLM walks the 5-stage pipeline → operator reviews + tweaks the brief / storyboard / prompts / copy → operator copies the prompts to GalilAI / Nano Banana / Midjourney (or hits "Generate" once we ship the image adapter in phase 2) → the finished post lands in their library, ready for the existing upload pipeline.

---

## 2. Confirmed constraints

User-provided context (this conversation, 2026-05-20):

- **Goal** — *"design a new set of functionalities learned from [media-creator] and implement back and frontend to the social-wiring product."* *(Social-wiring already exists; media-creation is an extension, not a fork.)*
- **Ecosystem framing** — *"social-wiring is an automation on social media, the media creator is gonna be the media creation part of this automated ecosystem."* *(Creation feeds distribution; this is the upstream half of the pipeline.)*
- **Scope evolution** — *"only images so far, we'll expand."* *(Phase 1 stays image-focused; video deferred to a later phase but the schema is video-ready.)*
- **Auto mode** — proceed without per-decision check-ins; make reasonable calls and ship. *(Drives the inline-architect-implements posture rather than dispatching engineers.)*

---

## 3. Design principles

1. **Skill decomposition over monolith.** Mirror media-creator's 5 stages as 5 service methods (`storyboard`, `visual_style`, `image_prompts`, `copy`, `optional_render`), composable in any order. A user can regenerate one stage without re-running upstream.
2. **Reference fidelity > novelty.** Brand kit (persona + design system + references) is the source of truth. The LLM is told to cite which reference informed each choice (matches media-creator's CLAUDE.md rule).
3. **Artifact-first.** Output is human-readable structured artifacts (markdown / YAML / JSON), not opaque IDs. A user can copy a prompt straight into GalilAI without our renderer being present.
4. **Multi-tenant from day one.** Every row carries `org_id`; every endpoint is gated by `Depends(get_current_user_org)`; brand kits are per-org.
5. **Renderer-agnostic.** Prompts are emitted in multiple renderer styles (Nano Banana / GalilAI / Midjourney) so the operator picks. Our own image gen (phase 2) becomes one more option.
6. **No quick fixes in the seed.** Image generation is missing in `noctusai_lib.integrations` — that gap is filed as a follow-up seed project (see §8 Dependencies). Phase 1 ships prompts only, with a typed `gate=image_generation_not_configured` signal on the relevant endpoint per gated-capability honesty (`feedback_gated_capability_honesty`).

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every product?** **MIXED.** The skill decomposition + brand-kit + artifact shape *is* cross-cutting (a therapy-platform that wants to generate clinic posts, a PF product that wants to generate finance carousels, would all consume the same abstraction). **But for this slice, only social-wiring needs it (N=1)** — so we ship it as a product module per the `N=1 → ship in product, watch for N=2 to trigger seed` rule (DRY recurrence).
2. **Is the data source product-specific?** YES — the brand kit + post library are social-wiring tenant data.
3. **Is the placement product-specific?** YES — domain-bound to social-wiring's UI for now.
4. **Is the visibility / permission rule the same?** YES — uniform org-scoped RLS.
5. **Does the seam already exist in seed?** PARTIAL. `noctusai_lib.integrations.llm.chat_completion` covers prose generation. `noctusai_lib.integrations.storage.make_storage_backend` covers reference-asset blob storage. **GAP:** no outbound image-generation integration (`noctusai_lib.integrations.image_gen` does not exist). Phase 1 doesn't need it (prompts are text); phase 2 needs a Fake+Real+factory adapter shipped in seed. Filed as `[A] accept-with-rationale` for phase 1 + a follow-up seed project (`image-gen-seed-adapter`) for phase 2.
6. **Default-on or opt-in?** OPT-IN — operator decides per-post when to engage it.

**Litmus — per-product code count this design requires:**
- [x] **A small section** — product-specific module (`app/modules/media_creation/`) consumes seed primitives (LLM, storage). When N=2 surfaces (another product wants it), refactor the orchestration into `noctusai_lib.domain.media_creation` with the same Protocol+Fake+Real shape.

**Phase plan implications:** §6 phases work **inside the social-wiring module** (correct for N=1). When a second product asks for the same shape, file `media-creation-seed-extraction` to lift the domain layer to seed and migrate.

---

## 4. Scope

**In scope (Phase 1 — this session):**
- Backend module `app/modules/media_creation/` mirroring email_marketing / scheduling shape.
- Migration extension (W2.4 section in `001_social-wiring.sql`) — 5 tables: `mc_brand_kits`, `mc_brand_references`, `mc_posts`, `mc_post_slides`, `mc_post_copy`.
- Brand kit endpoints — CRUD for persona text + design system text per org; CRUD for reference assets (URL + label + tags, blob stored via `noctusai_lib.integrations.storage`).
- Post lifecycle endpoints — create post (idea + brand kit + format), regenerate any of {storyboard / image_prompts / copy} via LLM, list / get / delete.
- Frontend page `MediaCreation.tsx` + hook `useMediaCreation.ts` + nav entry under "Principal" group.
- Backend tests — auth gate, schema validation, status-code assertions per `check_test_status_assertion`.

**Out of scope (deferred — with named EXTERNAL blocker per no-defer-mid-flight §2.13a):**
- **Image rendering** — ~~deferred to `image-gen-seed-adapter`~~ → **NOW SHIPPED** (Phase 4 ✅). `noctusai_lib.integrations.image_gen` Protocol+Fake+Real(Gemini)+factory live; `/render` flips Fake/Real automatically from per-org `gemini_api_key` resolution.
- **Video generation** — user-directed scope freeze: *"only images so far, we'll expand."* Schema includes `format` enum with `video` as a forward-compatible value; the no-defer rule does NOT apply (user IS the external blocker = explicit scope gate).
- **Direct publish to Instagram / Facebook** — external structural blocker: Meta API write is out of scope of the current `noctusai_lib.integrations.meta` adapter (read-only-v1 per `KB § INTEGRATIONS/meta.md`). Operator pastes finished posts into the existing upload pipeline. Sanctioned per §2.13a class-1 (external).
- **Scheduling generated posts** — fully covered by the existing `app/modules/scheduling/` lifecycle; not duplicated (DRY recurrence rule, not a deferral).
- **Eval / quality-check loop** — external structural blocker: media-creator's `evals/cases/` is empty; no input data to harness. Phase 5 ❌ — sanctioned per §2.13a class-1.

---

## 5. Architecture / Data Model

### 5.1 Database (Supabase `social_wiring` schema, RLS by `org_id`)

```sql
-- W2.4 media_creation ─────────────────────────────────────────────────

create table social_wiring.mc_brand_kits (
    id            uuid primary key default gen_random_uuid(),
    org_id        uuid not null,
    name          text not null,             -- e.g. "Granja Premium"
    persona       text not null default '',  -- big PERSONA.md-equivalent
    design_system text not null default '',  -- big DESIGN-SYSTEM.md-equivalent
    default_lang  text not null default 'pt-BR',
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

create table social_wiring.mc_brand_references (
    id          uuid primary key default gen_random_uuid(),
    org_id      uuid not null,
    brand_kit_id uuid not null references social_wiring.mc_brand_kits(id) on delete cascade,
    kind        text not null,    -- 'model' | 'prompt' | 'palette' | 'typography'
    label       text not null,
    asset_url   text,             -- supabase storage URL (signed at fetch)
    notes       text,
    created_at  timestamptz not null default now()
);

create table social_wiring.mc_posts (
    id            uuid primary key default gen_random_uuid(),
    org_id        uuid not null,
    brand_kit_id  uuid not null references social_wiring.mc_brand_kits(id) on delete restrict,
    title         text not null,
    idea          text not null,             -- the raw user idea
    format        text not null default 'carousel',  -- 'carousel' | 'single' | 'video' (forward-compat)
    variant       text not null default 'premium',   -- DESIGN-SYSTEM variant
    slide_count   int  not null default 5,
    cta           text,
    audience      text,
    key_message   text,
    status        text not null default 'draft',      -- 'draft' | 'ready' | 'published'
    storyboard    jsonb,                              -- LLM output: arc, slides[]
    copy_caption  text,                               -- LLM output
    copy_hashtags text[],                             -- LLM output
    copy_alt_text text,                               -- LLM output
    copy_first_comment text,                          -- LLM output
    created_by    uuid,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

create table social_wiring.mc_post_slides (
    id          uuid primary key default gen_random_uuid(),
    org_id      uuid not null,
    post_id     uuid not null references social_wiring.mc_posts(id) on delete cascade,
    slide_n     int  not null,
    role        text not null,         -- 'cover' | 'develop' | 'insight' | 'cta'
    headline    text,
    body        text,
    visual_brief text,
    -- Renderer-ready prompts (one row, multiple flavors)
    prompt_nano_banana text,
    prompt_galilai     text,
    prompt_midjourney  text,
    -- Image rendering (phase 2 — gated)
    image_url   text,
    image_renderer text,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    unique (post_id, slide_n)
);

-- All tables: enable RLS, policies on org_id, updated_at triggers, indexes
-- on (org_id), (org_id, brand_kit_id), (org_id, status).
```

### 5.2 Backend module layout

```
products/social-wiring/backend/app/modules/media_creation/
├── __init__.py              # register() → ModuleRegistration
├── routers/
│   ├── __init__.py
│   ├── brand_kits.py        # /api/media-creation/brand-kits/*
│   ├── references.py        # /api/media-creation/brand-kits/{id}/references/*
│   ├── posts.py             # /api/media-creation/posts/*
│   └── generation.py        # /api/media-creation/posts/{id}/{generate-storyboard|prompts|copy}
├── services/
│   ├── __init__.py
│   ├── brand_kit_service.py     # CRUD persona + design system
│   ├── reference_service.py     # CRUD references + storage upload
│   ├── post_service.py          # CRUD posts + slides
│   └── generation_service.py    # LLM-driven 3-stage pipeline (storyboard/prompts/copy)
├── schemas/
│   ├── __init__.py
│   ├── brand_kits.py
│   ├── references.py
│   └── posts.py
└── prompts/                     # System prompts for each LLM stage (text constants)
    ├── __init__.py
    ├── storyboard.py            # The carousel-storyboard skill, ported
    ├── image_prompts.py         # The image-prompt-generator skill, ported
    └── copy.py                  # The instagram-copywriting skill, ported
```

### 5.3 API surface (Phase 1)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/media-creation/brand-kits` | List brand kits for org |
| POST | `/api/media-creation/brand-kits` | Create kit |
| GET | `/api/media-creation/brand-kits/{id}` | Get one |
| PATCH | `/api/media-creation/brand-kits/{id}` | Update persona / design system |
| DELETE | `/api/media-creation/brand-kits/{id}` | Delete (only if no posts) |
| GET | `/api/media-creation/brand-kits/{id}/references` | List references |
| POST | `/api/media-creation/brand-kits/{id}/references` | Add reference |
| DELETE | `/api/media-creation/references/{id}` | Delete reference |
| GET | `/api/media-creation/posts` | List posts (filter by status / brand_kit_id) |
| POST | `/api/media-creation/posts` | Create draft post (idea + brand_kit_id + format) |
| GET | `/api/media-creation/posts/{id}` | Get post w/ slides + copy aggregated |
| PATCH | `/api/media-creation/posts/{id}` | Update post metadata |
| DELETE | `/api/media-creation/posts/{id}` | Delete draft |
| POST | `/api/media-creation/posts/{id}/generate/storyboard` | LLM: idea → storyboard JSON (writes slides) |
| POST | `/api/media-creation/posts/{id}/generate/prompts` | LLM: storyboard → 3-flavor prompts per slide |
| POST | `/api/media-creation/posts/{id}/generate/copy` | LLM: storyboard → caption+hashtags+alt+first-comment |
| POST | `/api/media-creation/posts/{id}/render` | (phase 2) — returns `{gate: "image_generation_not_configured"}` typed signal |

### 5.4 Frontend

```
products/social-wiring/frontend/src/
├── pages/MediaCreation.tsx          # 3-tab page: Library · New Post · Brand Kit
├── hooks/useMediaCreation.ts        # all queries + mutations
└── components/media_creation/        # subdomain components
    ├── BrandKitEditor.tsx           # persona + design system text editors + references panel
    ├── PostComposer.tsx             # idea input → 3 stage actions → live preview
    ├── SlidePreview.tsx             # per-slide card showing role / headline / visual brief / prompts
    └── PostLibrary.tsx              # post list w/ status badges
```

Nav entry: under existing "Principal" group, between "Vídeos" and "Upload".

### 5.5 Generation pipeline (the heart of the value)

Three idempotent LLM calls, each consuming `brand_kit + post_input + (previous stage output if exists)`:

1. **`generate_storyboard(post)`** → `storyboard` JSON `{title, idea, audience, key_message, cta, slides: [{n, role, headline, body, visual_brief}]}` → persists to `mc_posts.storyboard` + creates/updates `mc_post_slides` rows. **Prompt port:** `media-creator/skills/carousel-storyboard/SKILL.md`.

2. **`generate_image_prompts(post)`** → for each slide, generates 3 renderer-flavored prompts (Nano Banana, GalilAI, Midjourney) → updates `mc_post_slides.prompt_*` columns. **Prompt port:** `media-creator/skills/image-prompt-generator/SKILL.md`.

3. **`generate_copy(post)`** → `{caption, hashtags[], alt_text, first_comment}` → updates `mc_posts.copy_*` columns. **Prompt port:** `media-creator/skills/instagram-copywriting/SKILL.md`.

All three call `noctusai_lib.integrations.llm.chat_completion` with `org_id` propagated for per-org key resolution + budget accounting. System prompts live in `app/modules/media_creation/prompts/`. User-tunable knobs (slide count, variant, language) flow through.

---

## 6. Implementation phases

### Phase 1 — Backend module + migration + endpoints ✅

- [x] Migration: add `-- W2.4 media_creation` block to `001_social-wiring.sql` (5 tables incl. triggers + RLS + service_role bypass)
- [x] `modules/media_creation/__init__.py` with `register()`
- [x] Schemas (Pydantic) for brand kits / references / posts (StrictHttpModel)
- [x] Services: brand_kit, reference, post, generation (LLM pipeline)
- [x] Routers: brand_kits, references, posts, generation (4 routers, all under `/api/media-creation/...`)
- [x] Wire `_register_media_creation` into `main.py` MODULES list
- [x] Backend tests covering all endpoints w/ status assertions (22 tests, all green)

**Improvements:**
- The `/render` endpoint ships as a typed-gate response (`gate=image_generation_not_configured`) rather than 503 / hidden — per `feedback_gated_capability_honesty`. When the seed adapter lands in phase 4, the contract flips to real URLs without a FE change.
- The 3 LLM prompts (storyboard / image_prompts / copy) live in `prompts/*.py` as text constants — versioning + per-stage iteration trivial. When N=2 product adopts, they lift to `noctusai_lib.domain.media_creation.prompts`.
- Service-side explicit `status="draft"` on insert is belt-and-suspenders to the SQL default — guarantees identical shape mock vs real (caught in test).

### Phase 2 — Frontend page + hook + components ✅

- [x] `useMediaCreation.ts` — 5 hooks (`useBrandKits`, `useBrandReferences`, `usePosts`, `usePost`, `usePostGeneration`) using the existing `api`-+-`useState` pattern (matches `useVideos.ts`)
- [x] `MediaCreation.tsx` — 3-tab page (Biblioteca / Novo post / Kits de marca) with inline sub-components (PostDetail, ComposeTab, BrandTab, KitEditor, ReferencesPanel)
- [x] Nav entry in `App.tsx` (Principal group, between Agente and Vídeos)

**Improvements:**
- Inlined sub-components instead of separate files — only one component (`MediaCreation.tsx`) is enough at this volume; split when growth justifies.
- Hooks return `{items, loading, create, update, remove, refresh}` shape — once N=2 page wants the same surface, lift the pattern to a generic `useResource<T>` in seed-lib-frontend.
- The "Renderizar (em breve)" button always renders; clicking shows the typed gate as a toast — operator gets gate-honesty rather than a missing button.

### Phase 3 — Verification ✅

- [x] Backend `pytest tests/` → 406 passed (22 new + 384 existing, no regressions)
- [x] Frontend `npx vite build` → green (MediaCreation chunk 23.3 kB / 6.4 kB gz, lazy-loaded)
- [x] `npx tsc --noEmit` — 2 pre-existing TS errors confirmed via `git stash` to exist on `main` (seed-side `supabase` type clash in `infra.appConfig`); NOT caused by this project. Surfaced + deferred — that's a cross-product seed-typing issue, out of this project's safe scope.

**Improvements:** none identified in this phase — verification was clean. Cross-product TS seed-typing surfaced + deferred per §3a scope-test (genuinely out-of-domain for media-creation, in-scope for a future seed-typing project).

### Phase 4 — Image generation seed adapter ✅ (no-defer-mid-flight, 2026-05-20)

User intervened on close-out: *"dont file nothing for later, please implement all mid-flight."* The `image-gen-seed-adapter` follow-up stub was DELETED; the full adapter shipped inline same session.

- [x] `seed/lib/backend/noctusai_lib/integrations/image_gen/` — `ImageGenAdapter` Protocol + `ImagePromptInput`/`GeneratedImage` value objects + `FakeImageGenAdapter` (deterministic SHA-prefix URL) + `GeminiImageGenAdapter` (lazy `google-genai` SDK import; default `imagen-3.0-generate-001`) + `get_image_gen_adapter` factory (Fake when no key resolves, Real when configured).
- [x] Seed tests: 12 passing (`test_fake_adapter.py` + `test_factory.py`).
- [x] `GenerationService.render_post(post, renderer)` — iterates slides, picks `prompt_<renderer>`, calls adapter, persists `image_url` + `image_renderer` onto `mc_post_slides`. Returns `{configured, backend, renderer, slides[]}`.
- [x] `POST /api/media-creation/posts/{id}/render` flipped from gate-only to real call (with `RenderRequest{renderer}` body). 422 on unsupported renderer / missing slides; 404 on missing post.
- [x] FE `useMediaCreation.render(renderer)` updated to new shape; toast surfaces "not configured" vs "N/M imagens renderizadas"; slides display `<img src={image_url}>` when populated + `image_renderer` badge.
- [x] Tests: 6 new render tests (404 / no-key-Fake / 422-slides-missing / 422-unsupported-renderer / persists-to-slides / skips-missing-prompt) — all 411 social-wiring tests + 12 seed image_gen tests green.
- [x] `KB § INTEGRATIONS/image-gen.md` consume-side doc + CLAUDE.md §2/§3 pointer + INDEX.md layout entry.

**Improvements:**
- Per-call adapter resolution (vs module-singleton): `get_image_gen_adapter` is called per `render_post` invocation so the `org_id` flows in for per-tenant keys. Mirrors `google_calendar.get_calendar_adapter(resolver, tenant_id=...)`.
- Lazy `google-genai` SDK import: adapter construction does NOT require the SDK installed; only `.generate(...)` does. Slim test environments stay green; the seed import surface is decoupled from the heavy ML SDK.
- `upload_url_resolver` seam shipped but not wired in this slice: the adapter falls back to inline `data:` URLs when Gemini returns bytes-only. Production should pass a Supabase Storage uploader. Documented in `KB § INTEGRATIONS/image-gen.md § 5`.

### Phase 5 — Eval loop ❌ genuinely blocked

The sibling `media-creator/` repo's `evals/cases/` directory is empty. There is no golden-case fixture set to port. Without that, building an eval harness now would be inventing a curation we don't yet have — pre-emptive over-engineering.

When fixtures land in the upstream prototype OR a second-product consumer surfaces (N=2 trigger to lift to `noctusai_lib.domain.media_creation`), the eval-loop work files as `media-creation-evals` with the now-existing fixtures as input. Distinct from the no-defer-mid-flight rule: this IS an external structural blocker (no input data to harness), not "we haven't decided."

---

## 7. Open questions

1. **Persona / design system input shape** — store as one big text blob (matching media-creator's markdown files) or structured JSON? *Recommendation: text blob for v1 (operator pastes markdown). Structured ingestion is a later improvement.* — answered: text blob.
2. **Reference assets — store bytes or just URLs?** — *Recommendation: just URLs for v1 (operator uploads to Supabase Storage via `noctusai_lib.integrations.storage` and we hold the URL + label). Direct multipart upload through this module is a phase 2/3 ergonomic improvement.* — answered: URLs only for v1.
3. **LLM model choice for generation** — Use the platform default (`gpt-4o-mini`) or push to `gpt-4o`? *Recommendation: default. Per-stage override is a knob a future phase can add.* — answered: platform default.

---

## 8. Dependencies & blockers

- **Migration application** — User runs `001_social-wiring.sql` against Supabase OR the test setup auto-runs it. Since we're extending the existing file, anyone reapplying the migration on a fresh DB gets the new tables; for already-applied DBs, the new section must be applied incrementally (Supabase MCP or manual SQL). Surfaced to user in the end-of-session summary.
- **~~No image-gen integration in seed~~** — RESOLVED IN-FLIGHT. `noctusai_lib.integrations.image_gen` shipped as Phase 4 same session per the no-defer-mid-flight refinement.

---

## 9. Success criteria

- All migrations apply cleanly on a fresh `social_wiring` schema.
- Backend `pytest products/social-wiring/backend/tests/` passes (baseline + new tests for media_creation).
- Frontend `npx vite build` succeeds with the new page lazy-loaded.
- An authenticated operator can:
  1. Create a brand kit with persona + design system text + at least one reference URL.
  2. Create a draft post (idea + brand kit + format).
  3. Run "generate storyboard" → see slides populated.
  4. Run "generate prompts" → see 3-flavor prompts per slide.
  5. Run "generate copy" → see caption + hashtags + alt + first comment.
  6. See the post listed in the library.

---

## 10. How to use this plan

- Live-tick tasks as they complete. The user reads this file as a dashboard.
- Phase headers flip to `✅` only when every sub-task inside is ticked.
- Phase proposals — file ONE bundled `proposals/*.md` per phase at end of phase (per `KB § PATTERNS/proposals-and-improvements.md`).

---

## 11. Change Log

- **2026-05-20** — Project filed. Design locked after parallel Explore-agent recon of media-creator + social-wiring. Architect implementing Phase 1 + 2 inline (single coherent module, dispatch cost > coherence win).
- **2026-05-20** — Phases 1–3 ✅. Backend: 5-table migration, 4 routers + 4 services + 3 LLM-prompt modules, 22 new tests (406 total, no regression). Frontend: 5 hooks + 1 page + nav entry, `vite build` green. Pre-existing TS errors confirmed unrelated (same on `main`). Image rendering deferred to follow-up project `image-gen-seed-adapter` (gate signal already wired). Migration extension to `001_social-wiring.sql` must be applied to any DB already on the previous version — surfaced in end-of-session note.
- **2026-05-20 (close-out)** — User intervened on the about-to-be-filed `image-gen-seed-adapter` stub: *"dont file nothing for later, please implement all mid-flight. Also doc this to our methodology."* The stub was deleted and Phase 4 ✅ shipped inline: `noctusai_lib.integrations.image_gen` (Protocol + Fake + GeminiImageGenAdapter + factory + 12 seed tests), `GenerationService.render_post`, `/render` endpoint flipped, FE hook + page updated, 6 new product tests (411 total, no regression). Methodology change three-way-synced same session: `KB § PATTERNS/project-execution.md § 2.13a` (no-defer-mid-flight refinement) + `CLAUDE/projects.md` new bullet + memory `feedback_in_flight_resolution.md` amended. Live migration applied to Supabase `social_wiring` schema (4 W2.4 tables). Live container probed on port 8011 (401 = auth-gated, contract live).
