# Community

Online community management center for a single paid online community for women, run by
client Mônica Tangerino (the community's theme is not defined yet). Managers run the community
from a back office; members use their own portal. pt-BR only, responsive web.

Status: **scaffolded (2026-09-16)**. The domain modules below are planned, not built yet.
Design brief: `.scaffold-brief.md`.

## Stack

- **Backend**: FastAPI via `create_product_app()` from `noctusai_seed` (port 8017)
- **Frontend**: React via `createProductApp()` + `createProductLayout()` from `@noctusai/seed` (port 8210)
- **Build**: `createViteConfig()` from seed framework (3-line vite.config.ts)
- **Database**: Supabase (schema: `community`)
- **Auth**: SSO + direct login

## Users

- **Managers** (back office): `admin` (everything) and `moderador` (moderation + content).
- **Members** (portal): access is governed by their paid tier.

## Planned modules

| Module | Scope |
|---|---|
| Membros & CRM | profiles, tags, segments, lifecycle; applications (approve/reject); invites |
| Planos & acesso | manager-configurable paid tiers → entitlements (spaces, groups, content, events) |
| Pagamentos | member picks card (Stripe) or Pix/boleto (Asaas); webhooks → subscription state → access |
| WhatsApp | tier ↔ group mapping; **semi-automatic** add/remove batches a manager confirms; broadcasts; message ingest |
| Feed & fórum | posts, comments, reactions; forum categories/topics |
| Chat | DMs + rooms over the seed realtime SSE bus |
| Conteúdos | tier-gated library: embeds, Supabase-stored MP4 (signed URL; HLS later), live-room recordings |
| Eventos | external link / built-in live room (LiveKit) / in-person with check-in; RSVP, reminders |
| Engajamento | points from platform, WhatsApp and events/content; rankings |
| Moderação | AI flags platform + WhatsApp content; a manager approves every action |
| Painel | growth, revenue, churn, engagement |

## Integrations

Stripe · Asaas · WAHA (WhatsApp, incl. group operations) · LiveKit · Supabase Storage ·
LLM via `noctusai_lib.integrations.llm`. Development runs on NoctusAI's own accounts, and
Mônica's accounts are swapped in later through configuration only.

## Running

```bash
./start.sh   # house container model; community on 8017 (API + SPA)
```

## Tests

```bash
cd products/community/backend && pytest
cd products/community/frontend && npx vite build
```
