# 11 · Admin: the Website section in the logged app

## Sidebar

- A new group **Website** appears in the core sidebar.
- **All sidebar groups start collapsed.** The seed `Sidebar` collapses every group by construction (commit `e3ebde374`, `seed/lib/frontend/src/design-system/components/Sidebar.tsx`); `NavGroup.defaultOpen` is ignored. The group containing the current page opens automatically so users see where they are. Manual open/close choices persist per browser.
- **Items, added slice by slice.** A nav item appears only when its page is real (no placeholder items):

| Item | Route | Status |
|---|---|---|
| **Documentação** | `/admin/website/docs` (→ `/app/admin/website/docs` after the `/app` move) | Built with this documentation |
| Configurações | `/admin/website/settings` | ✅ v1 |
| Blog | `/admin/website/blog` | v1.1 (deferred) |
| Leads | `/admin/website/leads` | ✅ v1 |

## Roles & access

| Surface | admin | marketing (new) | others |
|---|---|---|---|
| Documentação | read | read | — |
| Configurações | edit | edit, except `site_enabled` and `signup_enabled`, which are **admin-only** | — |
| Blog | edit + publish | edit + publish | — |
| Leads | full + export | full, **no export** | — |

**Implementation:**
- `noctus_users.role` gains `marketing`.
- A SQL helper `is_website_editor()` backs the RLS policies, with a matching backend dependency.
- A **role-aware shell** lets a marketing user reach the Website group. Today the admin shell gates `/admin/*` on `isAdmin` only (`CoreLayout.tsx:32-33`), so this is a real change, not a menu tweak.

## Documentação

- Renders `products/core/frontend/src/website/docs/**/*.md` with the seed `MarkdownRenderer` organ:
  - a left index grouped by folder, with the content pane on the right;
  - deep links per document;
  - relative `.md` links work in-app;
  - images resolve from `docs/assets/`.
- **Editing happens in git** (docs are code-reviewed and versioned). The page is read-only.
- The docs version and change log live in [00 · index](00-index.md#change-log).

## Configurações

One form per area. Every save is audit-logged (who, when, diff) and **takes effect without a deploy** (cache purge; [08 §4](08-technical-architecture.md#4-prerendering)).

| Area | Controls |
|---|---|
| **Site** | `site_enabled` (kill switch → legacy landing) · canonical host (read-only info) · maintenance banner (optional) |
| **Conversion** | `signup_enabled` (admin-only; also enforced by the backend) · WhatsApp number (E.164) · default prefill message pt/EN · floating-button on/off |
| **Home sections** | One switch per section key ([07](07-page-specs.md#home)): `audiences`, `products`, `custom_builds`, `trust`, `social_proof` (refuses to turn on with 0 items), `pricing`, `news`, `faq`, `hero_update_card`, `assistant` (v1.1). A drag handle orders the sections where the order is flexible (products → pricing) |
| **Products (curated)** | Pick from the product catalog, set order, state (`disponível` / `lista de espera` / `em breve`), pt/EN copy, panel asset, CTA override |
| **Trust statements** | Items with an icon, pt/EN text, **`verified_by` + `verified_at` required** (P7) |
| **Social proof** | Logos / testimonials / metrics, each with a **consent reference** (who approved, when, document link) |
| **Copy** | Hero, section intros, FAQ, closing band: pt/EN fields side by side, a "tradução pendente" badge, preview link |
| **SEO** | Per-page title/description overrides (with length counters), OG image regenerate, `llms.txt` preview |
| **Tracking** | Plausible/Umami site id · GA4 id · Meta Pixel id (all loaded **only after consent**; [12](12-privacy-lgpd-tracking.md)) |

**Storage.** A dedicated `website_settings` table, versioned: every save is a new row, with rollback to any previous version. There's a **public read endpoint** that exposes only the public subset. It never touches `platform_settings` (which holds secrets).

## Blog

- **Posts:**
  - `slug` per language;
  - pt/EN title, dek and body (markdown via the same `MarkdownRenderer`);
  - category, tags, author, cover (generated or uploaded; uploads go to a **private** bucket served by signed URL, per the zero-public-bucket rule);
  - status `rascunho → revisão → publicado`, a scheduled publish time, and SEO fields.
- Publishing triggers the meta cache purge, sitemap and RSS refresh and OG generation.
- Categories include `novidade`, which feeds `/novidades`.
- A preview renders the real website template.

## Leads

- **Board:** kanban columns = stages ([10](10-conversion-and-leads.md#lead-model-core-db)); drag to change stage (writes an activity).
- **Table:** sortable, with filters (source, product, profile, stage, owner, date, consent) and saved views.
- **Lead detail:**
  - contact card;
  - consent state and version;
  - the timeline of activities: form submits, WhatsApp clicks, notes, stage changes, agent actions;
  - quick actions: **Abrir WhatsApp** (WAHA chat or `wa.me`), e-mail, note, assign, next action + date;
  - a mark-lost reason.
- **Dashboard strip:** new leads today/week, by source, stage conversion, and median time to first contact.
- **Export:** CSV, admin only, audit-logged. It includes consent fields, so data can be shown to have been collected lawfully.
- **Agent readiness:** an "Atribuir ao agente" action and an agent badge on activities ([10 §Agent-ready](10-conversion-and-leads.md#agent-ready-design)). Disabled until the agent exists.
- **Every UI state is honest:** skeleton only while pending with no data, a real empty state, a real error state (`KB § PATTERNS/frontend/lying-loading-state.md`).
