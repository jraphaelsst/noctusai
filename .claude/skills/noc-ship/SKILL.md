---
name: noc-ship
description: Use for the in-repo release/deploy gates — triggers "ship to main", "bless this", "merge to main", "promote to prod", "release", "deploy these changes", "deploy the latest", "redeploy", "pull the code to the VPS". `main` is production; everyday work lands on `dev`.
version: 1.2.0
---

# noc-ship — release · bless · promote · deploy

`main` = the blessed/shippable release line; production is the further `main → prod` promote the VPS tracks. NEVER push/merge to `main`/`prod` without explicit per-action consent. `dev` = integration branch (push your own work freely).

## Workflow

0. **🔴 PROD-ONLY — the dev FLEET is DORMANT (2026-08-11, owner's decision).** There is no `./start.sh` step and no dev-container smoke; **do not re-add one**. Prod is now first-contact for the running image, so the gate MOVED and TIGHTENED — all three are MANDATORY before bless: (a) `noctus.dev.predeploy_check <slug>` for **every active product** — host-side, runs a REAL `vite build` + the backend suite + prod-config value parity, and is now the primary functional evidence; (b) **CI GREEN on the exact sha** — no longer advisory, because a dev-fleet smoke can no longer stand in for it (sole exception: a diff that is entirely `project-history/`/docs — prove it with `git diff --name-only` and say so out loud); (c) `--check-prod-exposure-consent` clean. The 🔴 `dev` **BRANCH is UNAFFECTED** — worktree off `origin/dev` → integrate → bless is unchanged; only the CONTAINERS are dormant. Still FF the PRIMARY checkout to `origin/dev` after integrating so hooks + tooling read the shipped tree. → `KB § PATTERNS/devops/dev-fleet-dormant.md`.
1. **Status first** — `noctus.dev.release stage=status` (read-only chain view: dev → main → prod).
2. **Bless** — `noctus.dev.release stage=bless` FFs `main` → `dev` tip. DRY-RUN by default; `confirm=true` to push. FF-only by construction; it is the ONLY sanctioned setter of `NOCTUS_ALLOW_MAIN_PUSH`.
3. **Promote** — `noctus.dev.release stage=promote` snapshots `prod` → `prod-backup` (rollback pointer) then FFs `prod` → a blessed `main` sha. `confirm=true` to push.
4. **Deliver to VPS** — code: `noctus.dev.deploy_pull` (§2a safe pull: inspect → ff-only → verify; never reset/checkout/clean on the VPS). Image model: `noctus.dev.deploy_image` (atomic GHCR pull + health-probe + auto-rollback + SWAP-VERIFY: after a healthy probe it re-inspects the RUNNING container's own image id + revision label and refuses `status='deployed'` — reports `swap_unverified` instead, no auto-rollback — unless the swap verifiably landed; 2026-08-13, a healthy OLD container had silently never been recreated).
5. **Pre-deploy gate** — `noctus.dev.predeploy_check` (D3 manifest + prod-config parity: catches present-but-localhost values the boot guard can't).
6. **🔴 Post-deploy PROD verification — MANDATORY, two legs, same weight, was optional.** With the dev fleet dormant this is the ONLY runtime evidence the platform gets, so a deploy is not "done" until BOTH pass:
   - **(a) REVISION-DRIFT — `noctus.dev.deploy_verify`** (or `--deploy-verify`). The INDEPENDENT witness: it has zero dependency on `deploy_image` having run, succeeded, or even existed in this process — for every ACTIVE product it reads the RUNNING container's `org.opencontainers.image.revision` and compares it to a FRESHLY-resolved `prod` branch tip. `status='verified'` (exit 0) is the only pass. **If `deploy_image` times out, or the MCP session disconnects mid-call, that is NOT success by default** — treat it as `status=unverified` and run `deploy_verify` immediately to get ground truth; never assume the swap landed because the call went quiet (2026-08-13: exactly this — `deploy_image` timed out, the MCP server disconnected before reporting anything, and only a manual `docker inspect` caught prod still serving the old image).
   - **(b) HEALTH/CONTENT** — `noctus.vps.health` all-healthy, then each ACTIVE product's `/api/health` answering 200 both internally (`noctus.vps.exec --container`) and through the public edge (browser UA — CF WAF 1010). Read `startup_hook_error` in that payload too: a product whose lifespan hook failed still serves 200 and reports it there, so `status: "ok"` alone is not the answer (`KB § PATTERNS/backend/startup-hook-must-not-be-fatal.md`).

   On a `deploy_verify` drift OR a health failure, ROLL BACK (`deploy_image` auto-rolls a failed health probe; code rolls back to `prod-backup`) — do not debug forward in prod.

6a. **🔴 Then `noctus.dev.spa_smoke` — the FRONTEND leg (step 6 is backend-only).** Every check in step 6 passes while the JS bundle is missing: the container is up, `/api/health` answers, and the edge returns 200 for the HTML **shell** — a blank page for every user, all gates green. `spa_smoke` asserts, per active product, that the shell carries a mount point + bundle tag, that the bundle is real JS (**not** the SPA HTML fallback, which also 200s), and that a deep link resolves (client routing wired). After a UI-library change, pin what shipped with markers: `expect_absent=["@remix-run/router"]` proves a react-router v7 bundle. It does NOT execute JS, so an in-component render crash is still uncovered — that limit is deliberate. → `KB § PATTERNS/devops/prod-deploy-safety-gates.md`.

## Guardrails
- R4 human-gated: PRESENT {push cmd + range + evidence} → explicit user go → execute. Never auto-push `main`/`prod`.
- 🔴 **The dev FLEET is dormant — prod-only (2026-08-11).** Never `./start.sh` as part of shipping, never re-add a dev-container gate, never "restore" the fleet as a side effect. The `dev` BRANCH is untouched. Raising the fleet again is the owner's cost decision. → `KB § PATTERNS/devops/dev-fleet-dormant.md`.
- The slim prod image is structurally different (no start.sh/registry/node, baked dist, env-only config) — and it is now the FIRST shape any change runs in, which is exactly why `deploy_image`'s health-probe + auto-rollback is the load-bearing net (`noc` highest-recurrence drift class).
- Prod services sit behind the CF tunnel ⇒ any programmatic caller needs a browser User-Agent (1010 WAF). SSO verify: `noctus.dev.sso_smoke`.
- **Prod-exposure precheck** — before promote, `python mcp/noctusai/cli.py --check-prod-exposure-consent` (should already be clean; the pre-commit gate refuses an un-consented product registration at commit time). Bless/promote is a whole-repo-state decision — it is NEVER a per-product "should this be public" decision. An agent may RECORD the user's decision but never invent one: ask them to type the canonical phrase (`prod_consent action=challenge slug=<slug>`), then `action=author`, which REFUSES unless that phrase is verified against the session transcript. → `KB § PATTERNS/devops/prod-exposure-consent.md`.

## Depth
`KB § PATTERNS/architect/branching-and-merging.md §0.2` · `KB § GUIDES/production-deploy.md` (+ §2a safe pull) · `KB § PATTERNS/devops/dev-prod-parity.md` · `KB § PATTERNS/devops/prod-exposure-consent.md`.
