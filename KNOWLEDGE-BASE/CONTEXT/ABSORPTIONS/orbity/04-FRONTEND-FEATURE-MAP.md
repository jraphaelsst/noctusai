# 04 — Frontend Feature Map

Vite + React 18 + TS + shadcn/ui + Tailwind, Lovable-generated. **433 `.tsx`** (~365 domain + 68 ui). Product brand "Orbity – Gestão Para Agências"; runner agency "Senseys – Marketing Imobiliário" (hardcoded `MASTER_AGENCY_ID`).

## 1. App shell & routing

- **Router:** `react-router-dom` v6 `BrowserRouter` (v7 future flags), central in `src/App.tsx`. **No code-splitting** — every page statically imported.
- **Provider stack** (outer→in): `QueryClientProvider` (TanStack Query, `staleTime 5min`, `refetchOnWindowFocus:false`) → `ThemeProvider` (next-themes) → `AuthProvider` → `ProductTourProvider` → `AgencyProvider` → `SubscriptionProvider` → `MasterProvider` → `TooltipProvider` → `BrowserRouter` → `PaymentMiddlewareProvider`. Meta Pixel inits at module load; `PageViewTracker` fires on every route change.
- **Routes:**
  - **Public (no shell):** `/` (LandingPage — the marketing site IS the app root), `/auth`, `/install`, `/privacy-policy`, `/onboarding`, `/register` (invite signup), `/report/:token` (public client report), `/approve/:token` (public approval), `/subscription-success`, `/subscription-canceled`.
  - **Protected app:** `/dashboard` wraps `<PaymentMiddlewareWrapper><AppLayout/></PaymentMiddlewareWrapper>` (Outlet layout). Children: index dashboard, `clients`, `clients/:id`, `tasks`, `reminders`, `crm`, `agenda`, `traffic`, `admin`, `contracts`, `social-media`, `import`, `email-marketing`, `reports`, `settings`, `settings/notifications`, `master`. Catch-all → NotFound.
- **Nav shell** (`src/components/layout/`): `AppLayout` (sidebar+outlet), `AppSidebar` (collapsible, menu grouped Gestão&Visão Geral / Operacional / Marketing&Vendas / Administração + conditional "Sistema → Painel de Controle"), `MobileBottomNav`.
- **3-layer RBAC:** (1) `useAuth` profile `role` (super_admin/agency_admin/agency_user) + 2h idle timeout; (2) `useAgency` (`currentAgency`, `userAgencies[]`, `agencyRole` owner/admin/member, switching, invites, plan limits, Stripe link); (3) `usePermissions` (TanStack Query against `agency_users.app_permissions` JSONB → 12 `canAccess*` booleans from `rolePresets.ts`). Pages wrapped in `<RequirePermission permission="canAccessX">`. **Sidebar shows all items; the block happens in-page** (intentional). Master panel gated by `isMasterAgencyAdmin(agencyId===MASTER_AGENCY_ID && owner/admin)`.

## 2. Feature domains (~27)

| domain | what it does (agency value) | #tsx | notable |
|---|---|---|---|
| **admin** | Financial/business admin: client revenue, churn, payment history, employees, billing automation, offboarding; `CommandCenter` subdir | 43 | DRE/financial hooks; `@react-pdf/renderer` |
| **crm** | Lead/pipeline: funnel chart, sales velocity, loss-reasons, investment metrics, ad-account selector, automation logs, filters, alerts | 30 | recharts; lead temperature (`lib/leadTemperature`); FB lead sync |
| **social-media** | Content planning + publishing: calendar, weekly planning, content library, AI caption gen, campaign manager, analytics | 30 | dnd-kit drag planning; per-client plans |
| **agenda** | Meetings/calendar: day view, blocks, conflict alerts, countdowns, timeline, action items, Google Cal sync | 25 | conflict detection |
| **landing** | Public marketing site (root `/`): hero, features, AI features, FAQ, demo carousel/scheduling, CTA, application modal | 25 | full conversion funnel + Meta Pixel |
| **tasks** | General + per-client tasks: list, assignments (multi-user), status/type managers, analytics | 15 | customizable statuses/types |
| **settings** | Integrations hub: AI, Asaas, Conexa, Facebook, Google Cal, SendPulse, Stripe, WhatsApp, branding/theme/logo | 13 | per-agency white-label branding |
| **dashboard** | Home overview widgets/KPI cards | 12 | recharts aggregates |
| **email-marketing** | SendPulse campaigns: builder, lists, senders, templates, test/send, CRM sync, stats | 12 | TipTap editor; heaviest edge-fn invoker |
| **traffic** | Paid-traffic ("Controle de Tráfego"): ad-accounts, campaigns&reports, per-client optimization sheets/reminders, FB connect, PDF report | 11 | FB Marketing API; optimization workflow |
| **contracts** | Contract gen: multi-step wizard (client→services→witness), AI smart generator, templates, PDF | 10 | `@react-pdf/renderer` |
| **clients** | Client roster cards/forms/detail dialogs | 9 | feeds ClientDetail |
| **master** | Superadmin "Painel de Controle": agencies table, details, create dialog, plans manager, Orbity leads table, analytics | 8 | platform-owner view |
| **import** | Bulk import wizard: uploader, smart column mapping, sync options, progress, results | 7 | xlsx; AI smart-mapping |
| **notifications** | In-app + push center: bell, center, prefs, push banner; Discord/Slack/webhook integrations | 6 | firebase push; `notificationRouting` |
| **onboarding** | New-agency wizard: company data, admin user, plan, confirmation, checklist | 6 | `agency-onboarding` + checkout |
| **subscription** | Self-serve billing UI: pricing cards, manage, history, status | 5 | Stripe checkout/portal |
| **templates** | Reusable task templates: quick dropdown, form, manager, selector | 5 | `templateVariables` |
| **reminders** | Personal reminder lists (Lembretes) | 4 | recurrence (`lib/recurrence`) |
| **agency** | Tenant bootstrap UX: selector, no-agency screen, connection-error, create dialog | 4 | gates the app when no agency |
| **help** | Help center + AI support chat + video tutorials | 4 | `ai-support-chat` |
| **payment** | Subscription enforcement: `PaymentMiddlewareWrapper` blocks app when unpaid | 3 | gating wrapper |
| **auth** | `RequirePermission` guard | 1 | per-route gate |
| **email** | SendPulse import dialog helper | 1 | overlaps email-marketing |
| **filters** | Shared date-range filter dialog | 1 | cross-domain reuse |
| **pwa** | `InstallPrompt` | 1 | + `/install` page |
| **tour** | Product tour (`tourSteps.ts` + `TourTooltip`) | 1 | driven by ProductTourProvider |
| **ui** | shadcn/ui primitives | 68 | standard Radix set |

## 3. FE ↔ backend data layer

- **Single Supabase client** (`src/integrations/supabase/client.ts`): hardcoded URL + anon key, `localStorage` session, typed with generated `Database`.
- **Two call styles:** (a) direct PostgREST `supabase.from('table')…` in ~50 hooks (RLS isolates server-side); (b) `supabase.functions.invoke('<fn>')` for anything needing secrets/3rd-party APIs (66 functions invoked; heaviest: `sendpulse-api` 17, `facebook-leads` 10, `whatsapp-connect` 7).
- **Query layer:** TanStack Query v5, keyed `[feature, userId, agencyId]`, gated by `enabled` on auth+agency readiness.
- **State = React Context (5 providers) + TanStack Query cache + localStorage** (theme, session, draft forms via `useFormDraft`). No Redux/Zustand.
- **~50 hooks:** domain (`useReminders`/`useMeetings`/`useCampaigns`/`useTaskStatuses`), integrations (`useWhatsApp*` ×4, `useGoogleCalendar`, `useMarketingIntegrations`, `useSendPulse`), financial (`useFinancialMetrics`, `useDREStatement`, `useCRMInvestments`), platform (`useAuth`, `useAgency`, `useMaster`, `usePermissions`, `useSubscription`, `usePaymentMiddleware`, `useProductTour`, `usePWAInstall`, `usePushNotifications`).

## 4. Dependency highlights

`@supabase/supabase-js` 2.97, `@tanstack/react-query` 5.83, `react-router-dom` 6.30, full Radix/shadcn, `recharts` (analytics), `@dnd-kit` (drag planning/kanban), `@tiptap` (rich editor), `@react-pdf/renderer` (contracts/reports), `xlsx`+`file-saver` (import/export), `firebase` 10 (push), `framer-motion` 11, `canvas-confetti`, `react-hook-form`+`zod`, `date-fns`+`date-fns-tz`, `vite-plugin-pwa`, `sonner`, `lovable-tagger`.

## 5. Craft worth keeping (the intent to preserve)

- **Product tour** — context-driven step engine, sidebar items carry `data-tour` anchors, completion persisted (`tour_completed`).
- **Onboarding wizard** — 6-step setup + checklist + checkout; flags `onboarding_completed`/`welcome_seen`.
- **PWA** — full manifest, custom InstallPrompt, `/install` page, firebase push. Note: Supabase runtime caching deliberately removed (caused tab-switch sync bugs — a real lesson captured in config).
- **White-label branding** — per-agency themes (`brandThemes.ts`, BrandingTab/LogoUploader/ThemeSelector) so each tenant re-skins.
- **Public token links** — `/report/:token`, `/approve/:token` let agencies share reports/approvals with end-clients without login.
- **Permission presets + JSONB perms** — role presets with emoji/descriptions + back-compatible key inheritance.
- **Payment middleware gate** — hard-blocks `/dashboard` on unpaid status.
- **AI features** — assist, caption generator, support chat, smart import-mapping, smart contract generator.
- **Demo system** — `data/demoData.ts` + `setup-demo-account` for sales demos.

## 6. FE gaps / notes

- **No "client" auth tenant** — end-clients are records, not logins (token links only). Confirm no separate client portal.
- **Single hardcoded master tenant** (`MASTER_AGENCY_ID`) — must become a proper role/flag for a multi-tenant seed.
- **Hardcoded URL+anon key** in `client.ts` (not env) — parameterize on absorption.
- **`_deprecated` tables** (`post_assignments_deprecated`) + CRM legacy permission fallbacks ⇒ schema churn; data-model archaeology advisable before wiring.
