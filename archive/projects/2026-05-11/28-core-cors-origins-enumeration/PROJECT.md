# core-cors-origins-enumeration — Project Document

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 1 in progress — enumeration shipped
- **Owner / stakeholders:** Architect / Engineer CORE-ORIGINS
- **Related docs:** `projects/cors-hardening-audit-2026-05-11/PROJECT.md` (Phase 0 audit), `KB § PATTERNS/backend.md`
- **Project slug:** core-cors-origins-enumeration (location: `projects/` — cross-product implication since core is the SSO bridge for every product frontend)

---

## 1. Context & Purpose

The CORS audit (commit `9754871`, 2026-05-11) flagged `products/core/backend/app/config.py:21` as the **CRITICAL** finding: it ships `cors_origins = "*"` while the seed factory (`seed/lib/backend/noctusai_lib/api/app_factory.py:127`) unconditionally wires `allow_credentials=True` into FastAPI's `CORSMiddleware`. Per [MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS/Errors/CORSNotSupportingCredentials), browsers reject the `Access-Control-Allow-Origin: *` + `Access-Control-Allow-Credentials: true` combo — but the server still echoes the request `Origin` back when middleware variants permit, opening an auth-replay vector. Core hosts the SSO bridge (`/api/sso/*`) consumed by every product frontend, so its CORS policy is the broadest legitimate origin set in the platform.

The win: replace `"*"` with the enumerated union of frontend origins that legitimately need to talk to core. A parallel engineer (SEED-GUARD) is adding the wildcard-plus-credentials guard at the seed factory. Once SEED-GUARD lands, core's `"*"` would fail to boot — this project prevents that boot failure.

---

## 2. Confirmed constraints

- **Coordination with SEED-GUARD** — runs in parallel. Architect sequences cherry-pick: CORE-ORIGINS first, then SEED-GUARD. *(Prevents the merge-window boot failure where seed guard rejects core's wildcard.)*
- **Core hosts SSO** — `/api/sso/{token,validate,launch/{slug},session}` is consumed by every product frontend. *(Drives the union-of-all-frontends shape.)*
- **AST-first** — Python edit must go through libcst per universal rule. *(Even a one-line constant change.)*
- **No monkey-patching** — none required; this is a pure config value edit.

---

## 3. Goals

- Replace `cors_origins = "*"` with the enumerated comma-separated list of legitimate frontend origins.
- Match the canonical shape seen in `products/seed/backend/app/config.py` and the existing per-product configs.
- Keep existing core tests green (SSO + auth + health + integration).

---

## 3a. Seed-first analysis

The seed already ships the canonical shape (`cors_origins: str = "..."` comma-separated, with the `cors_origins_list` property in `noctusai_lib.config.settings`). This project consumes that shape. **No per-product fork** — every product (seed, daily-life, erp-imobiliario, personal-finance, therapy-platform, mailing, adconnect, media-scheduling, imobi-scheduling, youtube-crawler, dev-team) already ships its enumerated list against the same property; core is the last `"*"` holdout. The seed-side wildcard-plus-credentials guard (SEED-GUARD, parallel project) is the structural fix that prevents recurrence at the seed layer.

---

## 4. Non-goals

- Adding the seed-side guard (that is SEED-GUARD's scope).
- Touching other products' `cors_origins` (covered by the audit's full triage queue).
- Production-domain origins — none in scope today; revisit when production frontends ship.

---

## 5. Files touched

- `products/core/backend/app/config.py` — replace line 21's `"*"` with enumerated list.
- `projects/core-cors-origins-enumeration/PROJECT.md` — this file.
- `projects/core-cors-origins-enumeration/findings.md` — engineer findings.

---

## 6. Phases

### Phase 1 — Enumerate (this phase)

Replace `cors_origins = "*"` with the comma-separated union of:

| Origin | Justification |
|---|---|
| `http://localhost:5173` | Core frontend (port 5173 per `start.sh` registry line `core:Core:8000:5173`). Also the default vite port for unbranded dev sessions. |
| `http://localhost:3000` | Common alternate vite/next dev port; appears in every other product's `cors_origins` list (N=11 occurrences in `products/*/backend/app/config.py`). Including for symmetry + zero-config browser dev sessions. |
| `http://localhost:8080` | ERP Imobiliario frontend (`erp-imobiliario:8001:8080`) — agents inside ERP UI may invoke core SSO. |
| `http://localhost:8090` | Personal Finance frontend (`personal-finance:8002:8090`). |
| `http://localhost:8095` | Therapy Platform frontend (`therapy-platform:8003:8095`). |
| `http://localhost:8100` | Seed product frontend (`seed:8004:8100`). |
| `http://localhost:8110` | Daily Life frontend (`daily-life:8005:8110`). |
| `http://localhost:8120` | Mailing frontend (`mailing:8006:8120`). |
| `http://localhost:8123` | Dev Team frontend (`dev-team:8009:8123`). |
| `http://localhost:8130` | AdConnect frontend (`adconnect:8007:8130`). |
| `http://localhost:8140` | Media Scheduling frontend (`media-scheduling:8096:8140`). |
| `http://localhost:8150` | YouTube Crawler frontend (`youtube-crawler:8008:8150`). |
| `http://localhost:8160` | Imobi Scheduling frontend (`imobi-scheduling:8011:8160`). |

Total: 13 enumerated origins. No `*`. No production domains (placeholder for future revisit).

### Phase 2 — Verify (this phase)

- `pytest products/core/backend/ -q` → green; SSO tests pass.
- `python -c "from app.config import settings; print(settings.cors_origins_list)"` from `products/core/backend/` → returns the 13-element list, no `*`.

---

## 7. Open Questions

- **Production domains** — none enumerated today. **Recommendation:** add `https://app.noctusai.com` (and any sibling production hosts) when production frontends ship. Track in `core` MASTER-PROMPT once decided.

---

## 8. Dependencies

- **SEED-GUARD** (parallel) — must merge AFTER CORE-ORIGINS to avoid a boot-failure window on `main`.

---

## 9. Risk / rollback

- **Rollback:** revert `products/core/backend/app/config.py:21` to `"*"`. Single-line revert.
- **Risk:** an unenumerated frontend port that legitimately needs SSO will get a CORS error. Mitigation: every product frontend port in `start.sh`'s `PRODUCTS` registry is enumerated; new products inheriting from `scaffold_product` will need to update this list or (better) move enumeration to a shared seed-lib helper that derives from `start.sh` (deferred — flag in findings).

---

## 10. Verification commands (copy-paste)

```bash
# From worktree root
cd products/core/backend && pytest -q
cd products/core/backend && python -c "from app.config import settings; print(settings.cors_origins_list)"
python mcp/noctusai/cli.py --review --product core --worktree-path "$(git rev-parse --show-toplevel)"
```

---

## 11. Change log

- 2026-05-11 — Engineer CORE-ORIGINS: replaced `cors_origins = "*"` with enumerated 13-origin list via libcst AST edit. Verified core tests green; verified `cors_origins_list` returns the enumerated list. Coordinated with parallel SEED-GUARD via architect-managed sequence (CORE-ORIGINS first, then SEED-GUARD).
