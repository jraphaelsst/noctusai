# Wave 1 phase proposal — social-wiring-absorption

One bundled proposal for the Wave-1 (full seed reconcile) phase. Each item is independently triageable/schedulable; dependencies named.

## Context
7 file-disjoint engineers reconciled the validated workspace stack into seed (master-tree parallel). 1430 lib + 75 framework tests green. The improvement-scout produced a collision-aware queue; engineers surfaced cross-cutting methodology items.

## Bundled items

1. **`safely_run` dispatch helper (N=6)** — `audit_hook` create_engine/sessionmaker + try/except shape recurs across core/daily-life/erp-imobiliario/personal-finance/therapy-platform (exclude mailing/imobi — deleted W4). Extract `noctusai_lib.dispatch.safely_run`. *Independently executable; dispatch Wave 3, file-disjoint one chunk per surviving product. Gates on W1 (done).*
2. **`dependencies.py` client/auth boilerplate (N=7-8)** — `get_user_client`/`get_admin_client`/`coerce_org_uuid`/`make_get_current_user` recur across ~8 products. Consolidate into a seed factory. *Depends on W1 reconcile (done) + social-wiring landing (W2); dispatch Wave 3, exclude products an active engineer holds + the 4 doomed.*
3. **Stale `reference/PROMOTIONS.md` index (7-of-14)** → evidence for W5.2: the auto-generated promotion map MUST derive the index from the manifest dir (single source of truth), never hand-maintain. *Routes to W5.2. Independently executable.*
4. **Scaffold emits `docker-compose.override.yml` registration** = drift vs single-env containerization (override files removed). *Doc-code-coherence; fix in `mcp/noctusai/.../scaffold` + `KB § PATTERNS/containerization.md`; W2+ after social-wiring stabilizes. Independent.*
5. **verify-the-seed-ships-it → assert `__all__` membership** — E2 found `lid_auth.py` shipped with zero exports/tests (reconciled-but-invisible half-ship). s4 keeper candidate (`check_*`). *W5.7a. Independent.*
6. **`check_dockerfile_vite_supabase_args` keeper** — E7; deterministic + recurrence-backed. s4. *W5.7b. Independent.*
7. **`seed-sqlite-dev-backend` follow-up project** — E7: noc seed has NO SQLite dev-backend infra (SEED-NEEDS §1 described the workspace, not noc). dev-auth shipped flag-gated; SQLite bootstrap is a separate scoped project. *Needs user decision: in-scope this absorption or deferred. Default: deferred follow-up.*
8. **`VistaClientProtocol` follow-up** — E6: `integrations/vista/` is Real-only (no Protocol). Adding it touches ERP showcase + `mcp/vista` consumers — out of W1 scope. *Deferred; file follow-up.*
9. **`compute_content_stats` N=2 dedup** — exists in `domain/chatbot` (generic) + `google_drive` (Drive-scoped). *Reconcile at W2 (product consumes generic; google_drive imports it). accept-with-rationale until then.*
10. **Manifest path-drift** — manifests target `integrations/<vendor>/<x>/`; noc ships flat `<vendor>_<x>`. *W5.2 promotion-map-automation must emit host-correct paths. Independent.*

## Do-NOT-action this wave
Hound's literal "absorb 6 scaffold P1s into seed/framework/" — collides with W1 surfaces + is exactly what W1 reconcile rewrites. Re-run `noctus.seed.report` after W1 to re-baseline (now done — re-scan scheduled W2).

## Recommended scheduling
W5.2: items 3,10. Doc-code-coherence: 4. Wave 3 disjoint: 1,2. W5.7 keepers: 5,6. Follow-up projects: 7,8. Wave 2 inline: 9 + the W0.3-scaffold CORS side-effect (`localhost:8140` dropped) + WAHA_RESPONSE_FORMATS carry.
