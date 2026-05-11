# Product Conftest Shadow-Purge — PROJECT.md

## 1 · Context (zero-context reader)

Parallel-worktree development shares one host venv. That venv carries an
editable-install of `noctusai_lib` pointing at ONE worktree's
`seed/lib/backend/` path. When sibling worktrees run tests, pip's
`__editable___noctusai_lib_<version>_finder.py` meta-path finder shadows
the local source tree — `from noctusai_lib.X import Y` resolves to the
wrong worktree (potentially missing seed surfaces added on this branch).

The seed-lib (`noctusai_lib.testing.conftest_helpers`) ships the
canonical `purge_shadowing_editable_finders(local_lib_root)` helper that
drops shadowing finders + clears stale `sys.modules` entries.
**daily-life / erp-imobiliario / personal-finance** product conftests
already invoke it via an `importlib.util` bootstrap prelude (the helper
must be loaded BEFORE any `from noctusai_lib...` import to avoid
chicken-and-egg shadowing of the helper itself).

**Gap (surfaced by SEED-RATELIMIT-FIXTURE absorption batch):** the 9
remaining product conftests do NOT run the purge. Adding new seed
surfaces on a branch + running tests in a parallel worktree → silent
import drift to the wrong worktree's seed-lib.

## 2 · Goal

Lift the canonical shadow-purge prelude to all 9 remaining product
conftests (adconnect, core, dev-team, imobi-scheduling, mailing,
media-scheduling, seed, therapy-platform, youtube-crawler) using the
existing seed helper. Zero behavior change on green baselines; closes
the parallel-worktree drift vector platform-wide.

## 3 · Inventory (Phase 0 audit, 2026-05-11)

| Product | conftest has purge? |
|---|---|
| adconnect | NO |
| core | NO |
| daily-life | YES (canonical reference) |
| dev-team | NO |
| erp-imobiliario | YES |
| imobi-scheduling | NO |
| mailing | NO |
| media-scheduling | NO |
| personal-finance | YES |
| seed | NO |
| therapy-platform | NO |
| youtube-crawler | NO |

Plus seed-lib's own `seed/lib/backend/tests/conftest.py` — already YES.

**Count**: 9 conftests to edit. (Brief estimated 10 by counting from 11;
recount confirms 3 already have it, not 1.)

## 3a · Seed-first analysis

`purge_shadowing_editable_finders` lives in `noctusai_lib.testing.conftest_helpers`. The seed already ships the helper + an `importlib.util` bootstrap pattern (necessary because at conftest load time, the seed lib itself may be shadowed — so we can't `from noctusai_lib.testing import purge_shadowing_editable_finders` until AFTER the purge runs).

The canonical bootstrap pattern (used by daily-life / erp / PF / seed-lib) is the right thing to replicate verbatim. No new seed surface needed.

## 5 · Files touched

- `products/adconnect/backend/tests/conftest.py`
- `products/core/backend/tests/conftest.py`
- `products/dev-team/backend/tests/conftest.py`
- `products/imobi-scheduling/backend/tests/conftest.py`
- `products/mailing/backend/tests/conftest.py`
- `products/media-scheduling/backend/tests/conftest.py`
- `products/seed/backend/tests/conftest.py`
- `products/therapy-platform/backend/tests/conftest.py`
- `products/youtube-crawler/backend/tests/conftest.py`

## 6 · Phases

- **Phase 0** — Audit (DONE)
- **Phase 1** — Insert shadow-purge prelude at top of each of 9 conftests
- **Phase 2** — Per-product `pytest -q` to confirm no regression
- **Phase 3** — `noctus.dev.review` per product → 0 NEW
- **Phase 4** — Commit + branch rename per KB §20

## 11 · Change log

- 2026-05-11 — project filed; Phase 0 audit done (3 already had it, 9 needed).
