# Community

Online community management center for a single paid online community for women, run by
client Mônica Tangerino (the community's theme is not defined yet). Managers run the community
from a back office; members use their own portal. pt-BR only, responsive web.

Status: **in development**. Design brief: `.scaffold-brief.md`.

## Stack

- **Backend**: FastAPI via `create_product_app()` from `noctusai_seed` (port 8017)
- **Frontend**: React via `createProductApp()` + `createProductLayout()` from `@noctusai/seed` (port 8210)
- **Build**: `createViteConfig()` from seed framework (3-line vite.config.ts)
- **Database**: Supabase (schema: `community`)
- **Auth**: SSO + direct login

## Users

- **Managers** (back office): `admin` (everything) and `moderador` (moderation + content).
- **Members** (portal): access is governed by their paid tier.

## Modules

| Module | Status |
|---|---|
| Membros & CRM (profiles, timeline) | built |
| Planos | built |
| Inscrições (applications) | built |
| Pagamentos | built (code): Asaas Pix/boleto; Stripe frozen |
| Financeiro / fluxo de caixa | built |
| Painel (Dashboard) | built |
| Grupoterapia | built |
| Portal da membra | built |
| WhatsApp | built (code), not connected (see below) |
| Feed & fórum | not built |
| Chat | not built |
| Conteúdos | not built |
| Eventos | not built |
| Engajamento / rankings | not built |
| Moderação (UI) | not built |

NOC-REMEDIATE[community-drop-examples-table]: the scaffold's `community.examples`
table (migration 003) is unused; drop it in a deliberate migration — 2026-10-01.

## Integrations

Stripe · Asaas · WAHA (WhatsApp, incl. group operations) · LiveKit · Supabase Storage ·
LLM via `noctusai_lib.integrations.llm`. Development runs on NoctusAI's own accounts, and
Mônica's accounts are swapped in later through configuration only.

## WhatsApp — não conectado por enquanto

Slice C (2026-09-17, user decision "community uses social-wiring's
mechanisms") ships the connection MECHANISM — `Configurações → WhatsApp →
Conexões` (`app/routers/whatsapp_connections_router.py`, admin-only) —
but no number is paired yet. `NOC-REMEDIATE[community-waha-pairing]`
marks the mount site.

Pairing needs a DEDICATED number + its OWN WAHA instance/session: the
live WAHA server is Core's, single-session, and its `default` session
already belongs to `social-wiring`. Sharing it here would mix
community's messages into social-wiring's inbox and risk the paired
number being banned. Until a dedicated WAHA instance exists for
community, the connections UI lets an admin save credentials, but
`GET /api/whatsapp/connections` returns an empty list and `POST` 503s
(`WAHA server not configured`) in every environment.

The org's `community_waha_*` settings stay the fallback path
(`app.dependencies.resolve_community_waha_client`) — a saved connection
row, once one exists, takes priority automatically; no code change
needed when pairing eventually happens.

## Running

```bash
./start.sh   # house container model; community on 8017 (API + SPA)
```

## Tests

```bash
cd products/community/backend && pytest
cd products/community/frontend && npx vite build
```
