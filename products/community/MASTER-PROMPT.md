# Community — MASTER-PROMPT

> Authoritative development guide for the `community` product. The design rationale lives
> in `.scaffold-brief.md`. Read it before changing scope.

## Purpose

This product runs ONE paid online community for women (client: Mônica Tangerino; theme TBD).
It replaces the manual work of managing members, access, payments, WhatsApp groups and
moderation, and gives members a native space: feed, forum, chat, content library and events.

**Success =** active paying members and MRR grow · churn stays low · members stay engaged
(weekly actives, posts, event attendance) · managers do less manual work.

## Decisions (from the planning session, 2026-09-16)

- Single community (no multi-tenancy beyond the seed's org scoping).
- Entry: public tier checkout, application + manager approval, and invite-only all coexist.
  No eligibility verification.
- Tiers: several paid tiers, created and configured by managers (nothing is hardcoded).
- Payments: at checkout the member picks card (Stripe) or Pix/boleto (Asaas).
- WhatsApp groups: sync membership, broadcast, track engagement, moderate. Add/remove is
  **semi-automatic**: the system builds batches and a manager confirms each one (this
  mitigates WAHA ban risk).
- Video: Supabase Storage, played as MP4 via signed URLs. HLS is a later step, tracked with a
  `NOC-REMEDIATE` marker in code. YouTube/Vimeo embeds cannot be truly tier-gated, and the
  UI must say so.
- Events: external link, built-in LiveKit room, or in-person with check-in.
- Moderation: an LLM flags content, and a human manager approves every action.
- Roles: `admin` and `moderador`.
- Development and the soft launch run on NoctusAI's Stripe/Asaas/WhatsApp accounts. Credentials
  are configuration only, so the swap to Mônica's accounts needs no code change.
- Everything ships in one release (user decision).

## Architecture

**Seed-first.** Backend `main.py` uses `create_product_app()`; frontend `App.tsx` uses
`createProductApp()`. Domain code only: `routers/` · `services/` · `schemas/` · `pages/` · `hooks/`.

Reuse before building (verified 2026-09-16):
- **Shared (consume):** `noctusai_lib.integrations.{whatsapp,storage,llm,google_calendar}`,
  `noctusai_lib.realtime`, `noctusai_lib.domain.invitations`, `noctusai_lib.domain.metas`, and the
  FE organs ChatWindow, gamification badges, ResourceManager, EntityDetailDialog.
- **Promote to seed first (product-local today):**
  - Asaas (`products/p-studio/backend/app/providers/`)
  - Stripe (`products/core/.../stripe_service.py`)
  - LiveKit (`products/therapy-platform/.../livekit_service.py`)
  - points engine (`products/erp-imobiliario/.../gamificacao_service.py`)
- **New in seed:** WAHA group operations (client + Fake).
- **New in product:** feed/forum, RSVP/check-in, checkout + applications, moderation queue,
  member CRM.

Every connected feature is contract-first (skill `noc-contract-first`).

## Naming

Portuguese for DB tables, entities and routes (`membros`, `planos`, `eventos`); English for
code structure; all UI copy in pt-BR.

## Database

Schema `community`. RLS on every table. Migrations use `noctusai_lib.sql.prelude`.

## Compliance

- LGPD: AI reads members' messages, and live rooms may be recorded, so both need consent and
  disclosure. The deletion flow must remove stored media too. Run an intake with the
  `security` agent before building these modules.
- Auth tests assert strict `== 401`.

## Testing

```bash
cd products/community/backend && pytest
cd products/community/frontend && npx vite build
```

## Dependencies

- Backend: `noctusai_lib` + `noctusai_seed`
- Frontend: `@noctusai/lib` + `@noctusai/seed`
