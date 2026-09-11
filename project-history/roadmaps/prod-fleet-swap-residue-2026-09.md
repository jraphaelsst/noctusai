# prod-fleet-swap residue — 2026-09

## Goal

Hold the two items that outlived `projects/prod-fleet-swap-handoff/` when it was archived
(2026-09-11). Everything else in that project is closed: the swap completed and verified,
and its §7 structural finding — `task_branch action=cleanup` returning `salvage_pushed:
false` and stranding ledger pointers in the primary — is **fixed** (`_ledger_push.py` now
tolerates the benign vector-costs rider; four cleanups on 2026-09-11 each returned
`salvage_pushed: true`).

These two are NOT fixed, and neither is derivable from the tree, so they need a durable
home rather than an `archive/` folder that does not persist.

## Open slices

### 1. Live-test checklist the owner is waiting on (social-wiring) — OWNER, not an agent

**Why this cannot be closed by an agent:** every item is a visual/behavioural check against
running production data. `deploy_verify` proves the right *revision* is running (it does:
7/7 verified at `2d56f839` on 2026-09-11); it cannot prove these five screens are *correct*.

Verify against production:

- the **ROI screen** (reads the funnel)
- the **funil totals** (counts money)
- the **duplicate queue**: bulk button + keyboard
- the **new panel**
- the **Negociação money field**

**Trigger:** next time the owner is in social-wiring prod. Unblocked — nothing gates it.

**Estimate:** ~10 minutes of clicking; zero code.

---

### 2. CI has no `seed` frontend build job

**Why:** `.github/workflows/test.yml` carries `erp-frontend-build` (:193), `core-frontend-build`
(:224) and `pf-frontend-build` (:372) — and no seed equivalent. The seed frontend build is
covered only by `predeploy_check`, which runs at deploy time, not per-PR. So a seed frontend
regression is invisible until someone ships.

Verified still true on 2026-09-11 against `origin/dev`.

**Why it matters more than a normal missing job:** the seed frontend is the thing every product
frontend inherits. A break there is fleet-wide by construction, which is exactly the class CI
is supposed to catch first, not last.

**Slice scope:** one job in `.github/workflows/test.yml` mirroring `erp-frontend-build`, pointed
at `products/seed/frontend`. Watch the `tailwindcss-animate` resolution trap documented in the
archived project's §6 — `seed/framework/frontend/tailwind.config.factory.ts:120` does a
`require()` that resolves relative to the factory's own directory, so the job needs `npm ci` in
`seed/framework/frontend` as well as in `products/seed/frontend`.

**Trigger:** fold into the next CI-coverage slice — this is the same open-world family as
`check_ci_test_matrix_coverage` / `check_seed_test_root_ci_coverage`, both of which already
gate *test* roots but not *frontend build* roots. A closed-world keeper misses the root nobody
listed (`KB § PATTERNS/devops/product-lockfile-and-slug-drift.md`).

**Estimate:** ~30 LoC of workflow + one run to confirm green.

---

## Provenance

Lifted from `projects/prod-fleet-swap-handoff/PROJECT.md` §5 and §6 at archive time
(2026-09-11), per learn-before-archive. The archived folder keeps the full procedure and the
rest of its gotchas; only these two were still open.
