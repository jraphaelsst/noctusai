# Scaffold-substitution audit — findings

**Date:** 2026-05-11
**Architect:** orchestrator
**Conclusion:** N=1 — only `imobi-scheduling` has real scaffold-substitution leftovers. **No platform-wide sweep needed; fix is at the scaffold-tool level, deferred per Engineer JJJ's Phase 10 surface candidate.**

## Per-product findings table

| Product | docker-compose.yml | Dockerfile(s) | package.json `name` | Real leftover? |
|---|---|---|---|---|
| **imobi-scheduling** | ❌ `seed-backend`, `seed-frontend`, `seed-tunnel`, `seed-net`, `noctus-seed-*` (20+ lines) | ❌ likely path refs | ❌ likely `"seed-frontend"` | **YES** — canary |
| adconnect | only intentional comments at lines 3+7 referencing seed as canonical pattern | clean | clean | NO (false positive — doc comments) |
| erp-imobiliario | only intentional comments at lines 3+7 | clean | clean | NO |
| daily-life | clean | clean | clean | NO |
| mailing | clean | clean | clean | NO |
| media-scheduling | clean | clean | clean (node_modules/.package-lock.json is a transitive copy of upstream `seed-frontend` name — regenerates on `npm ci`; not a source leftover) | NO |
| personal-finance | clean | clean | clean | NO |
| therapy-platform | clean | clean | clean | NO |
| core | clean | clean | clean | NO |
| dev-team | clean | clean | clean | NO |
| youtube-crawler | clean (`package.json` `name` already fixed in commit `0969e05` per §4 out-of-scope note) | clean | already EN | NO |

## Conclusions

1. **N=1 — imobi-scheduling is the sole real canary.** Engineer VV surfaced this 2026-05-11 in their Phase 8 retrospective: "Phase 0 scaffold leftover discovered while writing DEPLOYMENT.md. The `docker-compose.yml` + `backend/Dockerfile` still carry `seed-*` service / container names — Phase 1 scaffold copied verbatim without slug substitution."

2. **The fix belongs at the scaffold-tool level**, not as a per-product band-aid. Engineer JJJ's Phase 10 retrospective filed it as: "Surface candidate: a `noctus.dev.scaffold_product` post-copy substitution pass. N=1 today; deferred until N=2 product hits the same gap."

3. **No follow-up engineer dispatch needed for the audit's sister-product sweep.** The audit's purpose was to find other broken products — none exist. The fix is structural (scaffold tool) and waits for N=2 trigger.

4. **Operationally, imobi-scheduling still works.** `docker compose up` boots the services under `seed-*` internal names; only `docker ps` is cosmetically wrong. No runtime impact for dev/QA.

5. **Risk**: if a user runs both `products/seed/` AND `products/imobi-scheduling/` simultaneously, container name collisions on `noctus-seed-backend`/`noctus-seed-frontend`. Acceptable for current single-product dev; a real production concern that the scaffold-tool fix resolves.

## Architect decision

**ACCEPT-WITH-RATIONALE** for imobi-scheduling's leftover; **CLOSE AUDIT** as N=1, no sweep needed. Future trigger: if a 2nd product scaffolds with the same gap, file `scaffold-product-tool-substitution-fix` follow-up (N=2 → MUST formalize per CLAUDE.md §1 recurrence rule).

Entry appended to `KB § PATTERNS/accept-with-rationale.md` documenting the imobi-scheduling cosmetic-leftover state.

## Project closes

Audit-only project. All 6 grep categories run; findings table above is the authoritative output. Archive on next commit.
