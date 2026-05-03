# CLAUDE/frontend.md — frontend behavioral rules

> **Loading discipline.** This file is not auto-loaded. Read it when starting frontend code work — the §3 routing table in `CLAUDE.md` is the canonical signal. Sibling of `CLAUDE.md`, NOT depth (depth lives in `KNOWLEDGE-BASE/`).

## Rules

- **Componentize everything.** Check `KB § 04-SHARED-LIBRARY.md` before writing anything new. If another product will need it, build it shared from day one — don't fork. → `KB § 04-SHARED-LIBRARY.md`
- **Gamification is subtle.** Rankings, points, progress bars — discrete; with a ⓘ icon explaining the formula; tied to real business activity (never "logged in today"-style rewards). → `KB § 07-GAMIFICATION.md`

## Pointers (depth)

- Frontend patterns (TanStack Query, hooks-per-entity, mobile-first) → `KB § PATTERNS/frontend.md`
- Per-product frontend specs → `KB § frontend/{01-CORE, 02-ERP, 03-PF, 04-THERAPY}.md`
- Shared component catalog (check before writing anything) → `KB § 04-SHARED-LIBRARY.md`
- Notifications (shared `NotificationBell`, proxy shape) → `KB § PATTERNS/notifications.md`
- Environment / `.env` (VITE_ security boundary) → `KB § PATTERNS/environment.md`
