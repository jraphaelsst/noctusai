# Social Wiring — MASTER-PROMPT

> Authoritative development guide for the `social-wiring` product.

## Purpose

A media-wiring-into-one-place **CMS**. It consolidates four formerly
separate concerns into ONE seed-factory, single-container noc product
and wires them together for an operator: a surface-agnostic OpenAI
chatbot (WhatsApp via WAHA **and** an in-app `/chat` page), multimodal
media intake + YouTube upload/catalog, email-marketing (absorbed from
the retired `mailing` product), and real-estate scheduling (absorbed
from the retired `imobi-scheduling` product).

The cross-product capabilities are NOT product-local: chatbot, Google
Calendar/Maps/Drive, Meta FB/IG (read), multimodal media, the Fernet
credential vault and the WhatsApp connector all live in
`noctusai_lib`/`noctusai_seed` (reconciled to the live-validated source
in Wave 1). This product is the CMS skin + the three domain modules
that compose those seed capabilities.

## Architecture

**Born from the seed framework.** App shell, auth, layout, routing,
notifications, health, team and LLM access all come from the factory —
the product owns only its three domain modules + the CMS frontend.

### Backend

```
products/social-wiring/backend/app/
  main.py          → create_product_app("Social Wiring", "social_wiring", settings)
  config.py        → ProductSettings subclass
  database.py      → create_database_module(settings, "social_wiring")
  dependencies.py  → create_dependencies(db)
  routers/         → media_wiring · email_marketing · scheduling domain routers
                     (chat / dashboard / videos / upload / whatsapp / settings / meta / calendar)
```

### Frontend (App.tsx uses framework factories)

```
products/social-wiring/frontend/src/
  App.tsx          → createProductApp() + createProductLayout() — CMS nav below
  main.tsx         → validateEnv() + assertSupabaseBuildEnv() before render
  vite.config.ts   → createViteConfig({ port: 8160 }) — 3 lines
  lib/apiBase.ts   → runtime-detected same-origin base (house single-container)
  lib/api.ts       → re-export seed `api` client (test seam)
  pages/           → Dashboard · Chat · Videos · Upload · Conexao · Monitor · Settings · Equipe + auth pages
  hooks/           → useDashboard/useVideos/useSettings/useChat/useUpload (api or fetch)
                     useWhatsAppConnection/useWhatsAppIntake (bind seed @noctusai/lib factories)
  components/       → ui/ shadcn primitives + MetricCard/UploadZone/VideoCard/ViewsChart
```

**Nav (pt-BR, verbatim from validated source):**

| Group | Pages |
|---|---|
| Principal | Dashboard · Agente (`/chat`, public) · Vídeos · Upload |
| WhatsApp | Conexão · Monitor |
| Configuração | Configurações · Equipe |

### Database

Schema: `social_wiring`. Domain tables for the video catalog,
upload jobs, chatbot conversations/messages (dedup via
`UNIQUE(provider_message_id)`), email campaigns/automations, and
scheduling appointments. RLS scoped to the product.

## Seed seams consumed (do NOT re-implement product-locally)

> **⚠️ DOC⊥CODE DRIFT (2026-05-19, codebase-is-source-of-truth).** The
> **Google stack** rows below are **aspirational, not yet true**: the code
> hand-rolls youtube / Calendar / Drive / OAuth-lifecycle / the Fernet vault
> product-locally (~2,357 LoC against `googleapiclient` + raw OAuth) instead of
> consuming `noctusai_lib.integrations.{youtube,google_calendar,google_drive}` +
> `noctusai_lib.security.{oauth,token_store}`. Tracked + scoped:
> `products/social-wiring/projects/social-wiring-google-seed-consume/`. These
> rows become TRUE (and this marker is removed) when that project closes. The
> non-Google rows (chatbot, whatsapp, meta, media, frontend hooks) are
> unverified by this pass — do not assume. *(What·why·source-now per
> always-doc-the-trim: future agents must not act on the false "consumed" claim.)*

- Chatbot orchestrator + message_store + response_registry — `noctusai_lib.domain.chatbot`
- WhatsApp WAHA connector + @lid auth + SETNX dedup — `noctusai_lib.integrations.whatsapp`
- Google Calendar/Maps/Drive + scope-discovery — `noctusai_lib.integrations.google_*`
- Meta FB/IG read adapter — `noctusai_lib.integrations.meta`
- Multimodal media (audio/vision/PDF/keyframe) — `noctusai_lib.integrations.{media,llm}`
- YouTube upload + Vista CRM client — `noctusai_lib.integrations.{youtube,vista}`
- Fernet credential vault — `noctusai_lib.security.token_store`
- Frontend WhatsApp hooks — `createWhatsAppConnectionHooks` / `createWhatsAppIntakeHooks` from `@noctusai/lib`
- `assertSupabaseBuildEnv` — `@noctusai/lib` (boot-critical VITE_SUPABASE_* build-arg contract)

## What the framework provides automatically

- `/api/health` · `/api/team` · `/api/notificacoes` · `/api/llm/*`
- Multi-provider LLM access auto-wired in lifespan (`chat_completion` / `generate_embedding` / `transcribe_audio` / `analyze_image`)
- CORS, Sentry, exception handlers, middleware, rate limiting, structured logging
- Sidebar, Header, AppShell, page-status filtering, SSO context, trial/license warnings
- TooltipProvider, QueryClientProvider, AuthProvider, ErrorBoundary, Suspense

## Rules

- Cross-product capabilities live in seed; the product is the CMS + domain modules only. Per-product code count for a cross-cutting concern is **0** (factory inheritance).
- Sibling-validated wins conflicts during the absorption (Wave 1 reconcile precedent).
- House single-container model — ONE container; no `Dockerfile.frontend`, no 2-container proxy. `serve_spa` serves SPA + API on one port.
- Do NOT bake `VITE_BACKEND_API_URL` (runtime-detected). DO pass `VITE_SUPABASE_*` as Docker build-args in the image stage that runs `vite build`.
- pt-BR UI copy preserved; integrations stay independent seed modules — cross-integration workflows compose at the chatbot-tool / product layer.

## Testing

```bash
cd products/social-wiring/backend && pytest
cd products/social-wiring/frontend && npx tsc --noEmit
cd products/social-wiring/frontend && npx vite build   # must build clean
```

## Dependencies

- Backend: `noctusai_lib` (code library) + `noctusai_seed` (framework)
- Frontend: `@noctusai/lib` (code library) + `@noctusai/seed` (framework)
