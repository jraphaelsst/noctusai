# CLAUDE/frontend.md — frontend behavioral rules

> **Loading discipline.** This file is not auto-loaded. Read it when starting frontend code work — the §3 routing table in `CLAUDE.md` is the canonical signal. Sibling of `CLAUDE.md`, NOT depth (depth lives in `KNOWLEDGE-BASE/`).

## Rules

- **Componentize everything.** Check `KB § 04-SHARED-LIBRARY.md` before writing anything new. If another product will need it, build it shared from day one — don't fork. → `KB § 04-SHARED-LIBRARY.md`
- **Gamification is subtle.** Rankings, points, progress bars — discrete; with a ⓘ icon explaining the formula; tied to real business activity (never "logged in today"-style rewards). → `KB § 07-GAMIFICATION.md`
- **Core-URL routing is MANDATORY via the seed getter.** Any product→core link (SSO callback, "back to dashboard" nav, product→core XHR) resolves core's URL through `env.CORE_URL` / `env.CORE_API_URL` (`import { env } from "@noctusai/lib"`). **Never** hand-roll `import.meta.env.VITE_CORE_* || "<literal>"` — the bare-`localhost` default is the SSO "Failed to fetch" / stale-`5173`-nav recurrence (N≥3, prod outage). The `check_handrolled_core_url` keeper blocks it (carve-out: core's own same-origin `lib/api.ts`). → `KB § PATTERNS/frontend/core-url-routing.md`
- **A product always ships a REAL icon — never render an icon NAME as text.** Render a product's `icone` through the `ProductIcon` component (`core/frontend/src/lib/product-icon.tsx`), never inline as `{product.icone}` text. `ICONS` there is the single allowlist of values that render as an SVG; an unregistered ASCII name renders as bare TEXT (the "Sprout" bug, 2026-05-25) — `ProductIcon` falls back to the `Box` icon, and a NEW product icon must be added to `ICONS` (import from lucide-react). `icone` is required + non-empty at the create API (`ProductCreate.icone: Field(min_length=1)`). The `check_product_icon_registered` keeper folds the core product-catalog migrations and flags any live product whose seeded `icone` is empty or not in `ICONS` (emoji allowed). → `KB § PATTERNS/frontend/product-icon-registry.md`

## Pointers (depth)

- Frontend patterns (TanStack Query, hooks-per-entity, mobile-first) → `KB § PATTERNS/frontend/frontend.md`
- Per-product frontend specs → `KB § frontend/{01-CORE, 02-ERP, 03-PF, 04-THERAPY}.md`
- Shared component catalog (check before writing anything) → `KB § 04-SHARED-LIBRARY.md`
- Notifications (shared `NotificationBell`, proxy shape) → `KB § PATTERNS/backend/notifications.md`
- Environment / `.env` (VITE_ security boundary) → `KB § PATTERNS/devops/environment.md`
