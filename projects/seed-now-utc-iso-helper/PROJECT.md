# seed-now-utc-iso-helper — Project Document

> Living doc. Engineer NOWUTC-LIFT dispatched 2026-05-11 to lift N≥3 byte-identical `_now_iso()` helpers into the seed.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 1 done · Phase 2 in progress
- **Owner / stakeholders:** Architect / Engineer NOWUTC-LIFT
- **Related docs:** `seed/lib/backend/noctusai_lib/primitives/timeutil.py`, `KB § PATTERNS/seed-lib-layout.md`, `KB § PATTERNS/project-execution.md § 2.7 The recurrence rule`
- **Project slug:** `seed-now-utc-iso-helper` — at `projects/` (cross-product, lives outside any single product)

---

## 1. Context & Purpose

Surveyed N=4 byte-identical `def _now_iso() -> str: return datetime.now(timezone.utc).isoformat()` helpers across products:

1. `products/adconnect/backend/app/services/sellout_service.py:52`
2. `products/adconnect/backend/app/services/orders_service.py:84`
3. `products/adconnect/backend/app/services/financial_service.py:77`
4. `products/core/backend/app/services/webhook_retention_service.py:28`

Plus a divergent 5th variant (microsecond-stripped):
5. `products/erp-imobiliario/backend/app/services/vista_showcase_service.py:397` — `.replace(microsecond=0).isoformat()`

And EXCLUDED (different timezone):
- `products/therapy-platform/backend/app/services/audio_retention_service.py:46` — uses `SP_TZ` not UTC. Divergent semantics, deferred.

DRY recurrence rule (KB § PATTERNS/project-execution.md § 2.7): N≥3 byte-identical → MUST formalize. Helper belongs in `noctusai_lib.primitives.timeutil` alongside `now_utc()` / `today_utc()` / `frozen_time(...)` — the canonical "current wallclock" module.

---

## 2. Confirmed constraints

- **Import path** — brief specified `noctusai_lib.primitives.datetime.now_utc_iso()`; engineer chose `noctusai_lib.primitives.timeutil.now_utc_iso()` to compose with the existing `_now_provider` seam (so `frozen_time(...)` pins this too) and avoid a parallel module that duplicates the seam. Surfaced as a finding for architect review. *(Re-export from `noctusai_lib.primitives.__init__` keeps `from noctusai_lib.primitives import now_utc_iso` short.)*
- **Microsecond divergence (vista)** — vista_showcase strips microseconds; not formalized in the seed helper (YAGNI — only 1 consumer). Vista's `_now_iso` left in place; deferred to follow-up. *(Avoids forcing a `strip_microseconds=False` kwarg into the seed for a single consumer.)*
- **Therapy SP_TZ variant** — explicitly excluded by brief — divergent timezone semantics.
- **AST-first** — libcst for all per-product migration edits.
- **Coordination** — THE-P10 (therapy verification) + LLM-RL-TRIO-2 (mailing/daily-life/therapy AI routers) in flight; engineer scope is disjoint (adconnect / core / erp services).

---

## 3. Design principles

1. **Compose with `frozen_time`.** The helper reads through `_now_provider` so tests automatically work via `frozen_time(...)` — no second seam to learn.
2. **No kwarg parameterization for a single divergent consumer.** Vista keeps its local `_now_iso` until N≥2 microsecond-strippers appear or follow-up decides to lift it.
3. **Defer therapy explicitly.** SP_TZ variant deserves its own design conversation (timezone semantics matter for retention windows).

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every product?** YES — `def _now_iso() -> str: return datetime.now(timezone.utc).isoformat()` is byte-identical across 4 services.
2. **Is the data source product-specific?** NO — wallclock.
3. **Is the placement product-specific?** NO — every product needs a "now ISO string" for write payloads.
4. **Is the visibility / permission rule the same?** N/A — pure utility, no auth involved.
5. **Does the seam already exist in seed?** YES — `noctusai_lib.primitives.timeutil._now_provider` (used by `now_utc`, `today_utc`, `current_month_ref`, `current_day_ref`).
6. **Default-on or opt-in?** DEFAULT-ON — straightforward replacement of product-local `_now_iso()` callsites.

**Litmus** — per-product code count: **0 lines of new helper code per product** (replacement of an existing def + AST-rename of callsites; net product LoC decreases).

**Phase plan implications:** §6 phases work in seed (Phase 1) then absorb the seed via simple import-and-callsite rename (Phase 2). No "for each product replicate" framing.

---

## 4. Scope

**In scope:**
- Add `now_utc_iso()` to `noctusai_lib.primitives.timeutil` + re-export from `primitives/__init__.py` docstring.
- Unit tests asserting format, tz-aware, `frozen_time` composition, microsecond preservation.
- Migrate 4 adopters: adconnect/sellout, adconnect/orders, adconnect/financial, core/webhook_retention.
- Pytest verification per product (baseline preserved).

**Out of scope (deferred):**
- `erp-imobiliario/vista_showcase_service.py` — microsecond-stripped variant; would need either `strip_microseconds=True` kwarg in the seed (over-engineering for N=1) or a separate helper. Filed as follow-up.
- `therapy-platform/audio_retention_service.py` — SP_TZ variant; divergent timezone semantics; brief excluded.

---

## 5. Architecture

**Seed:**
- `seed/lib/backend/noctusai_lib/primitives/timeutil.py` — adds `now_utc_iso() -> str` returning `_now_provider().isoformat()`.
- `seed/lib/backend/noctusai_lib/primitives/__init__.py` — docstring updated to list `now_utc_iso()`.
- `seed/lib/backend/tests/test_timeutil.py` — new `TestNowUtcIso` class: returns str, `+00:00` suffix, round-trips via `datetime.fromisoformat`, frozen_time pinning incl. microseconds.

**Per-product migration:**
- Replace `def _now_iso(): ...` block with `from noctusai_lib.primitives.timeutil import now_utc_iso` (or rely on existing re-export).
- AST-rename all callsites `_now_iso()` → `now_utc_iso()` via libcst.
- Remove `from datetime import datetime, timezone` if no remaining usage in file.

---

## 6. Phases

### Phase 1 — Seed helper ✓
- Added `now_utc_iso()` to `timeutil.py` + test class. 17/17 timeutil tests green.

### Phase 2 — Per-product migration (in progress)
- adconnect/sellout_service.py: 1 def removed → 5 callsites renamed
- adconnect/orders_service.py: 1 def removed → 3 callsites renamed
- adconnect/financial_service.py: 1 def removed → 12 callsites renamed (cross-checked)
- core/webhook_retention_service.py: 1 def removed → 1 callsite renamed

### Phase 3 — Verification
- pytest per product; baseline preserved.
- Branch rename per KB § 20 then push.

---

## 11. Change log

- 2026-05-11 — Phase 1 done. `now_utc_iso()` added to `timeutil.py` (composes with `_now_provider`). 17/17 timeutil tests green. Departed from brief's import path (`primitives.datetime`) in favor of `primitives.timeutil` for `frozen_time` composability — surfaced in findings.
