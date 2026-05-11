# Scaffold-substitution audit — 2026-05-11

## §1 Context

`imobi-scheduling`'s `docker-compose.yml` carries literal `seed-backend` /
`seed-frontend` / `products/seed/...` strings because slug substitution did
not run during scaffold. The dispatch surfaced this as a known canary and
asked: *is anything else broken the same way?*

This project is **audit-only**. No code is fixed here. Findings feed:
- the parallel agent's `imobi-scheduling-bot-creation` Phase 10 (canary fix), and
- a new follow-up the architect dispatches for any NEW broken sibling.

## §2 User prompt (verbatim)

> "Audit-only (no fixes). imobi-scheduling's docker-compose.yml has literal
> `seed-backend` / `seed-frontend` / `products/seed/...` references because
> slug substitution didn't run during scaffold. Find any OTHER products with
> the same gap so future fixes (Task #14, parallel agent's Phase 10) can
> sweep wider."

## §3 Scope

Grep across every NON-seed product directory for literal `seed-*` /
`products/seed/...` references that should have been slug-substituted.
Six pattern categories:

1. service-name shape (`seed-backend`/`seed-frontend`/`seed-tunnel`/`seed-net`)
2. `container_name` (`noctus-seed-*`)
3. image-name (`:seed-backend`/`:seed-frontend`/`/noctus-seed`)
4. Dockerfile path leftover (`products/seed/backend`/`products/seed/frontend`)
5. profile leftover (`tunnel-seed`/`profile.*seed`)
6. `package.json` `"name": "seed-frontend"` / `"name": "seed-backend"`

## §4 Out of scope

- Any fix application. Fixes belong to the canary-owning agent (imobi-scheduling)
  and to follow-ups the architect dispatches for NEW finds.
- `products/youtube-crawler/frontend/package.json` `name` field — already fixed
  (commit `0969e05`); not in this audit's scope to re-fix.
- `products/seed/` itself — filtered out of every grep.

## §5 Findings

See `findings.md` for the full audit table.

## §6 Phases

Single-phase audit-only project.

- **Phase 1** ✅ — Run all 6 greps; classify hits per product; write
  `findings.md` per-product table + verification quotes; commit + push.
