# Prod fleet container swap — handoff to the final merge+deploy agent

> 🔴 **SUPERSEDED 2026-08-25 ~21:15 UTC — THE SWAP IS DONE. DO NOT RE-RUN IT.**
>
> Everything below the banner was accurate when filed (~20:50 UTC) and is kept verbatim
> because its procedure, gotchas and live-test checklist are still worth reading. But its
> headline finding — "6 of 7 live containers were never swapped" — **is no longer true.**
>
> A second agent was running the release concurrently with the agent that filed this note.
> That is also the answer to this file's open question of who moved `main`/`prod`: it was
> that agent, via `noctus.dev.release stage='bless'` then `stage='promote'` (which is why
> `prod-backup` exists and is valid). It then completed `deploy_image` for **all seven**
> live products.
>
> **Verified end state (`noctus.dev.deploy_verify`, catalog-driven):**
> `status: verified`, exit 0 — **7 actionable products checked, 0 missing, 0 drifted,
> 0 degraded, 0 unverifiable.** Every one reports *"running revision exactly matches the
> prod tip"* at `eb648b2b`. `noctus.vps.health` = 11 healthy / 0 unhealthy. All 7 SPAs pass
> `spa_smoke` on their real hostnames.
>
> The `126086ca` cohort drift this file flagged is **closed**, not deferred.
>
> **What the merge agent should actually do:** nothing from §5 of this file. Prod is current
> and green. Merge whatever is new on `dev` beyond `eb648b2b`, then run the ship chain fresh
> for that delta. Re-running `deploy_image` against the already-current fleet is harmless
> (it reports `up_to_date`) but §5's premise no longer applies.
>
> Still open and NOT superseded: §6 (the social-wiring live-test checklist) and §7 (related
> drift), plus the uncommitted salvage-ledger entries in the primary checkout.

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

- **Primary checkout `dev` is diverged:** 26 behind `origin/dev`, 6 ahead. The 6 local-only commits are
  append-only salvage-ledger records (`project-history/worktree-salvage.ndjson`,
  `vector-costs.ndjson`) — 6 `worktree-sweep` entries dated 2026-08-25. They are **preserved on branch
  `chore/salvage-ledger-20260825` (`a8de8628`)**, created 2026-08-25 so they survive any reset.
  `project-history/vector-costs.ndjson` also has uncommitted changes in the primary tree.
  Resolving means landing those 6 ledger commits and FF-ing the primary checkout to `origin/dev`
  (`noc-ship` wants the primary tree at the shipped tip so hooks + tooling read it).
- **`126086ca` cohort drift predates this release** — worth asking why a prior deploy swapped only one
  product, so it doesn't recur.

## 8. Done when

- All 7 live products report the prod tip in `deploy_verify` → `status='verified'` (exit 0).
- `noctus.vps.health` all-healthy, no `startup_hook_error`.
- `noctus.dev.spa_smoke` passes for every active product.
- The §5 social-wiring checklist is confirmed live by the owner.
