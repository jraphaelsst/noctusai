# seed-sqlite-dev-backend — Project Document

> Living document. Filed 2026-05-16 as the **named destination** for the SQLite dev-backend gap surfaced by the social-wiring absorption Wave-1.E7 (dev-auth + sqlite). Self-contained — no dependency on the originating project folder surviving.

- **Created:** 2026-05-16
- **Status:** Filed / not started — **gated** on user intent (see §2)
- **Owner:** Raphael · architect: Claude Opus 4.7
- **Slug:** `seed-sqlite-dev-backend` (cross-product / seed-infra → `projects/seed-sqlite-dev-backend/`)

## 1. Context & Purpose

During the social-wiring absorption, Wave-1.E7 discovered noc seed has **no SQLite dev-backend infrastructure** — contrary to `SEED-NEEDS-DEV-AUTH-AND-SQLITE.md`, which described the *workspace's* SQLite bootstrap, not noc's. The dev-auth capability was therefore shipped gated on explicit `SEED_DEV_AUTH` + `debug` (hard-off in prod) **without** a SQLite-backed local datastore. A seed SQLite dev-backend (a local, dependency-free datastore for offline product dev without a live Supabase) is the named follow-up if the team wants that bootstrap.

## 2. Prerequisites / gate

- **User intent gate.** This is not auto-justified — dev-auth currently works flag-gated against the real backend. Build the SQLite dev-backend only if the user wants dependency-free offline product dev (no Supabase). Surface the trade-off (SQLite ≠ Postgres RLS semantics; tests already use `MockSupabaseClient`) before starting.

## 3. Scope (if greenlit)

- A seed `noctusai_seed` SQLite dev-backend: Protocol+Fake+Real+factory shape, opt-in, hard-off in prod (same gating as `SEED_DEV_AUTH`).
- Schema bootstrap from the product's numbered migrations (or a documented divergence policy if SQLite cannot express a migration construct).
- Wiring recipe + KB pattern doc + the dev-auth gate composition.

## 4. Success criteria

A product can boot + exercise its routers offline against the seed SQLite dev-backend with no live Supabase; the prod path is provably unaffected.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-16 | Filed as the named destination for the Wave-1.E7 SQLite-dev-backend gap (SEED-NEEDS doc described the workspace, not noc). Gated on user intent. | Claude Opus 4.7 |
