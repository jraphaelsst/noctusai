# Social Wiring

A media-wiring-into-one-place CMS. Consolidates four previously-separate
concerns into one seed-factory, single-container noc product: a
surface-agnostic OpenAI chatbot (WhatsApp via WAHA **and** an in-app
`/chat` page), multimodal media intake + YouTube upload/catalog,
email-marketing (absorbed from the retired `mailing` product), and
real-estate scheduling (absorbed from the retired `imobi-scheduling`
product). The cross-product capabilities themselves (chatbot, Google
Calendar/Maps/Drive, Meta FB/IG read, multimodal, credential vault)
live in `noctusai_lib`/`noctusai_seed` so every other product can
consume them — this product is the CMS that wires them together.

## Stack

- **Backend**: FastAPI via `create_product_app()` from `noctusai_seed` (port 8011)
- **Frontend**: React via `createProductApp()` + `createProductLayout()` from `@noctusai/seed` (port 8160)
- **Build**: `createViteConfig()` from the seed framework (3-line `vite.config.ts`)
- **Database**: Supabase (schema: `social_wiring`)
- **Auth**: SSO + direct login (seed factory). `/chat` is a public route by current product direction.
- **Container**: ONE container — uvicorn serves the built SPA + API on one port via the seed `serve_spa` seam (noc house single-container model).

## Frontend scope (nav)

| Group | Pages |
|---|---|
| **Principal** | Dashboard · Agente (`/chat`) · Vídeos · Upload |
| **WhatsApp** | Conexão · Monitor |
| **Configuração** | Configurações · Equipe |

pt-BR copy preserved verbatim from the live-validated source.

## Running

```bash
# Backend
uvicorn app.main:app --reload --port 8011 --app-dir products/social-wiring/backend

# Frontend (bare Vite dev — talks to a separately-run :8011 backend)
cd products/social-wiring/frontend && npm run dev
```

Under the house single-container model the SPA is served same-origin
with the API — `VITE_BACKEND_API_URL` is runtime-detected (see
`src/lib/apiBase.ts`) and intentionally **not baked** into the image.
The two boot-critical `VITE_SUPABASE_*` vars **are** Vite-inlined at
`vite build` and asserted in `main.tsx` via `assertSupabaseBuildEnv()`.

## Modules

- **media_wiring** — chatbot (OpenAI tool-calling, multichannel) · intake (audio→Whisper, image/video→vision, PDF→PyMuPDF) · YouTube upload/catalog · Vista CRM lookup.
- **email_marketing** — campaigns / automations / segmentation / analytics / debrief (absorbed from `mailing`).
- **scheduling** — SchedulingEngine / appointment lifecycle / LID-auth (absorbed from `imobi-scheduling`).

## Tests

```bash
cd products/social-wiring/backend && pytest
cd products/social-wiring/frontend && npx tsc --noEmit
```

## Dependencies

- Backend: `noctusai_lib` (code library) + `noctusai_seed` (framework)
- Frontend: `@noctusai/lib` (code library) + `@noctusai/seed` (framework)
