# Prod fleet container swap — handoff to the final merge+deploy agent

> 🔴 **CLOSED 2026-08-26 — the final merge+deploy agent ran, and everything this
> file was waiting on is done. Kept for its procedure and its gotchas, which are
> still the right reading; nothing in it is outstanding work any more.**
>
> What the closing session actually did, beyond this file's scope:
> - Merged the three branches that were still unmerged on 2026-08-25:
>   `feat/imovelweb-portal-leads` (15 commits, rebased across 178 commits of
>   drift, 4 conflicts resolved by union), `feat/kb-env-template-debug-not-prod`,
>   and `feat/sw-roteiros-visitas` (roteiros + visitas). The fourth,
>   `chore/salvage-ledger-20260825`, was DELETED rather than merged: its ledger
>   content was already a subset of `dev`, verified line by line.
> - Fixed two gates that were red for reasons unrelated to what they measure —
>   a fleet-scope smoke test that asserted the opposite of its own name after
>   `3f5c2d69`, and a retention test comparing a UTC-derived value against a
>   local `date.today()`, which turned CI red for three hours every night.
> - Applied migrations **082** (roteiros/visitas) and **052** (imovelweb) to
>   prod, each verified against the live schema afterwards.
> - Landed the 7 stranded `worktree-salvage` pointers (§7), so the primary
>   checkout can be reset without discarding anything.
>
> **§7's structural finding still stands and is NOT fixed:** `task_branch
> action=cleanup` writes its recovery pointer into the primary checkout and
> returns `salvage_pushed: false`, so the drift regrows on every teardown. It
> was drained again today; it will accumulate again. The fix candidates in §7
> are still the fix candidates.
>
> **§5's live-test checklist is still the owner's to run** — it is the one
> thing here no agent can close.

- **Status:** ✅ SWAP COMPLETE + VERIFIED — refs promoted, images built, **all 7 containers swapped**
- **Owner:** Rapha · orchestrating agent
- **Slug:** `prod-fleet-swap-handoff` (root `projects/`)
- **Authority for the procedure:** skill `noc-ship` steps 4–6a + `KB § GUIDES/production-deploy.md § 2a`.
  Do NOT re-derive the chain — follow the skill.

---

## 1. Context (zero-context reader)

`main` is the blessed release line; `prod` is what the VPS tracks. On 2026-08-25 eight commits went
`dev → main → prod`, moving prod from `149fdbf4` to `eb648b2b`. Everything upstream of the container
swap completed and was verified. The swap itself did not run for most of the fleet.

**Do not re-run bless/promote. They are done.** The remaining work is `deploy_image` + verification.

## 2. State as verified 2026-08-25 ~20:50 UTC

| Ref | SHA |
|---|---|
| `origin/dev` | `eb648b2b` |
| `origin/main` | `eb648b2b` |
| `origin/prod` | `eb648b2b` |
| `origin/prod-backup` | `149fdbf4` ← **rollback pointer, valid** |

- **CI:** green on `eb648b2b` — every job, zero failures (run `32894294626`).
- **GHCR build:** `Build & Push Images (GHCR)` on `prod` completed **success** 20:39:26Z. `:latest` has moved.
- **VPS checkout:** `deploy_pull` reports `up_to_date` at `eb648b2b`. Nothing to pull.
- **Fleet health:** 11/11 healthy, every health probe OK, no `startup_hook_error` anywhere.
- **`predeploy_check`:** `ready` (exit 0, all 7 legs) for **all 7 live products** — verified against a
  clean worktree at `eb648b2b`, not the stale primary checkout.

### Running revisions — RESOLVED, table kept for the record

As filed at ~20:50 UTC (the gap this note was written about):

| Product | Running revision @ 20:50 | Needed swap? | Running revision @ 21:15 |
|---|---|---|---|
| `erp-imobiliario` | `eb648b2b` | ✅ no — already at prod tip | `eb648b2b` ✅ |
| `social-wiring` | `149fdbf4` | ⚠️ yes (64 files behind) | `eb648b2b` ✅ swapped |
| `core` | `126086ca` | ⚠️ yes (159 files behind) | `eb648b2b` ✅ swapped |
| `igig` | `126086ca` | ⚠️ yes | `eb648b2b` ✅ swapped |
| `orbity` | `126086ca` | ⚠️ yes | `eb648b2b` ✅ swapped |
| `p-studio` | `126086ca` | ⚠️ yes | `eb648b2b` ✅ swapped |
| `seed` | `126086ca` | ⚠️ yes | `eb648b2b` ✅ swapped |

The `126086ca` cohort was drift that **predated** this release — a prior deploy swapped one product
and left the rest behind. All six were swapped at ~21:00–21:10 UTC, each reporting `status: deployed`
+ `health: healthy` + a matching `landed_revision`, and `deploy_verify` then returned `verified` with
zero drift. Nothing on this table is outstanding.

**Why it mattered beyond tidiness:** the `eb648b2b` release contains a fleet-wide pure-ASGI middleware
rewrite. The five `126086ca` products carried the latent 502 bug (see §3) — harmless only because none
of them ships a service worker to trigger it. Leaving them behind would have kept a known-bad
`BaseHTTPMiddleware` in prod on five services.

## 3. What is in the 8 commits (blast radius)

```
eb648b2b fix(seed): pure-ASGI middleware — the erp.noctusai.com 502, and retire the long hostnames
fb85b83f feat(seed): absorb whole-document transcription from erp-imobiliario
c5cdd6a3 fix(documents): a signature stamp must not claim TextSource.TEXT_LAYER
234cd5d0 fix(pdf): classify PDF text layers as content vs. scan-stamp noise
f77ce8bb fix(social-wiring): stop patching our own service in the painel test
0ad691bb fix(social-wiring): the eight open defects from the field report
4791704b feat(social-wiring): the first screen is about the agency, not a YouTube channel
68c7075a feat(social-wiring): the ROI screen reads the funnel, and the funil counts money
```

Two things make this **fleet-wide**, not a social-wiring release:

1. **`seed/lib/backend/noctusai_lib/api/middleware.py`** — all three seed middlewares (CorrelationId,
   RequestLogging, MaxBodySize) rewritten from `BaseHTTPMiddleware` to pure ASGI. This removes a
   latent `RuntimeError: Response content shorter than Content-Length` → CF 502 bug class from
   **every** product. Today it only fires on `erp` (the only product shipping a service worker, whose
   prefetch/abort traffic produces the disconnects). The other five carry the latent bug until swapped.
2. **`seed/framework/frontend/src/infra.tsx`** + `seed/lib/frontend/` (PipelineBoard, design-system
   hooks) — shared frontend build inputs for the whole fleet.

**Already applied to prod, outside git:** the CF tunnel hostname retirement.
`erp-imobiliario.noctusai.com` and `social-wiring.noctusai.com` now return **404**; the short names
`erp.` / `social.` are canonical and serving 200. `ingress.yml` gained a machine-readable `retired:`
list so `tunnel_config action=apply` permits exactly those drops. **Do not "restore" them.**

## 4. Remaining procedure

> ⚠️ **DONE — see the banner at the top of this file.** All 7 containers were swapped and
> `deploy_verify` returned `verified` (0 drifted). This section is retained as the procedure
> to follow for the NEXT delta on `dev`, not as outstanding work. Re-running it now against
> the current fleet is a no-op (`up_to_date`), not a fix.

Per `noc-ship` steps 4–6a. Everything before step 4 is done.

1. **`noctus.dev.deploy_image <product>`** for each of: `social-wiring`, `core`, `igig`, `orbity`,
   `p-studio`, `seed`. Dry-run first (default), then `confirm=True`.
   - The **PROD-PIN ancestry guard** verifies the pulled image's baked revision is an ancestor of
     `origin/prod` — do NOT pass `skip_ancestry_check` to get past a refusal.
   - Health probe + **auto-rollback** on failure; **SWAP-VERIFY** re-inspects the *running* container's
     own image id + revision label and returns `swap_unverified` rather than a false `deployed`.
   - 🔴 If a call **times out or the MCP session drops mid-swap, that is NOT success.** Treat it as
     `unverified` and run `deploy_verify` immediately for ground truth. This exact hole produced the
     2026-08-13 phantom deploy.
2. **`noctus.dev.deploy_verify`** → the only pass is `status='verified'` (exit 0).
3. **`noctus.vps.health`** → all healthy; read `startup_hook_error` in each `/api/health` payload
   (a product whose lifespan hook failed still serves 200 and reports it there).
4. **`noctus.dev.spa_smoke`** → the frontend leg. Every check in step 3 passes while the JS bundle is
   missing (blank page, all gates green). This is mandatory, not optional.
5. On drift or health failure → **roll back**, do not debug forward in prod. Code rollback pointer is
   `origin/prod-backup` = `149fdbf4`.

## 5. Live-test checklist the owner is waiting on (social-wiring)

From the original field report — verify against production after the swap:

- the **ROI screen** (reads the funnel)
- the **funil totals** (counts money)
- the **duplicate queue**: bulk button + keyboard
- the **new panel**
- the **Negociação money field**

## 6. Gotchas found the hard way (do not re-derive)

- **`predeploy_check` in a fresh worktree fails `frontend_build` for a bogus reason.**
  `seed/framework/frontend/tailwind.config.factory.ts:120` does `require("tailwindcss-animate")`,
  which resolves relative to **the factory's own directory**, not the product's. A fresh worktree has
  no `seed/framework/frontend/node_modules`, so it fails; the primary checkout and the Docker build
  both have it (`seed/docker/Dockerfile.frontend-base` does `COPY seed/framework/frontend` +
  `WORKDIR` + `npm ci` there). The tool mis-classifies this as `npm_root_hoist` / B1 build-injection
  pointing at `tailwindcss-animate` — but the dep **is** correctly declared in both
  `products/seed/frontend/package.json` and `seed/framework/frontend/package.json`.
  **Fix:** `npm ci` in `seed/framework/frontend`, `seed/lib/frontend`, and each
  `products/<slug>/frontend` inside the worktree. Then all 7 products return `ready`.
  (`task_branch action='start' wire_env=True` does this wiring for you on a new worktree.)
- **`deploy_verify` reports `catalog_source: build_scope_fallback`** because the MCP server process has
  no `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`. The fallback snapshot is **correct** as of
  2026-08-25 — verified directly against Supabase: live set is `erp-imobiliario, igig, orbity,
  p-studio, seed, social-wiring` + `core`, exactly matching `deploy/fleet/build-scope.txt`. A new row
  `pilates` exists but is `ativo=false`/`dev`, correctly excluded. Not a blocker; don't chase it.
- **CI has no `seed` frontend build job** (only ERP, Core, PF `*-frontend-build`). The seed frontend
  build is covered by `predeploy_check`, not by CI. Worth a follow-up.
- **The MCP toolkit is fine.** An earlier session reported being "blocked at the permission layer" from
  moving `main`/`prod` and proposed pasting raw
  `NOCTUS_ALLOW_MAIN_PUSH=1 git push origin origin/dev:main` lines. Those blocks were **transient
  stage-2 classifier errors** that succeed on retry. Prefer `noctus.dev.release` — the raw push skips
  the CI-green probe on the dev tip, which is exactly how `1c83232f` reached prod red.

## 7. Related drift left open (not blocking)

- **Primary checkout `dev` is diverged** → the part that mattered is RESOLVED (2026-08-25 ~21:30 UTC):
  the original 6 stranded ledger commits are landed on `origin/dev` as `1f0ae93b`, together with 3
  more the session's own cleanups had appended. Landed as a UNION over dev's committed ledger + the
  preservation branch `chore/salvage-ledger-20260825` + the primary's live working copy — append-only
  NDJSON ledgers of independent facts, so a union cannot drop one, whereas rebasing six successive
  appends onto a moved base invites a conflict resolution that silently can.
  **Not "lossless", precisely:** later teardowns keep appending pointers to the primary's local `dev`,
  so `git reset --hard origin/dev` will discard whatever has accrued since. That is safe **when every
  pointer names a branch already merged to `dev`** — which is the normal case, because a pointer
  exists to find work that is NOT in `dev`. Verify with `git branch --no-merged origin/dev` before
  resetting. See the housekeeping section of
  `project-history/roadmaps/product-slug-rename-2026-08.md` for the full statement.
- 🔴 **`task_branch action=cleanup` grows this drift by construction.** It writes its recovery pointer
  into the PRIMARY checkout's working tree and returns `salvage_pushed: false`, because the
  primary-write guard correctly forbids it from committing there. So every teardown adds an
  uncommitted ledger line, and the `false` is easy to miss in a large result payload — which is how
  9 pointers accumulated unlanded. Fix candidates: write the pointer from a short-lived worktree it
  can commit from, or surface the drift as a first-class warning rather than one field.
  > **Correction (2026-08-31, root-caused):** the bolded diagnosis above is wrong on two counts, kept
  > here unedited (see the standing rule) rather than silently rewritten. **The primary-write guard is
  > not involved at all** — `task_branch._push_salvage_ledger_from_primary` commits the recovery
  > pointer on the primary *deliberately* (that is the documented 2026-06-30 fix for rebase-integrated
  > slugs), and that commit **succeeds**. The actual cause: `commit_and_ff_push_ledger`'s commit leg
  > (`git commit -- rel_paths`) does not truly restrict the resulting commit to `rel_paths` — a
  > pre-commit hook that stages a second file mid-commit (our own vector-costs drain, step 10c, by
  > design) rides into the SAME commit, and the divergence guard used to treat that rider as
  > "non-ledger" and refuse to push, **permanently** (the stranded commit never disappears, so every
  > subsequent teardown hits the same refusal — a self-latching loop, not a one-shot guard). Fixed in
  > `mcp/noctusai/tools/noctus/dev/_ledger_push.py` (the guard now tolerates a known-benign rider via
  > the same `is_benign()` predicate the stash pre-check uses) + the bare `salvage_pushed: false` now
  > carries a `salvage_push_reason`. Full account: `KB § PATTERNS/common/self-branching-mode.md` §12a.
- ~~**`126086ca` cohort drift predates this release**~~ → **CLOSED** (all six swapped; see the banner).
  The underlying question is still worth answering: why did a prior deploy swap one product and leave
  the rest behind, and what stops that recurring?

## 8. Done when

- All 7 live products report the prod tip in `deploy_verify` → `status='verified'` (exit 0).
- `noctus.vps.health` all-healthy, no `startup_hook_error`.
- `noctus.dev.spa_smoke` passes for every active product.
- The §5 social-wiring checklist is confirmed live by the owner.
