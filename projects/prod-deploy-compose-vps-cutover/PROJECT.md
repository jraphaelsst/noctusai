# prod-deploy-compose-vps-cutover — Project Document

> **Zero-context handoff.** You did not see the session that produced this. Everything you need is inlined below. This is the **VPS-side tail** of `prod-deploy-compose-durable-relocate` (that project's Phase A relocated the deploy tree in the repo; this project finishes the cutover on the live VPS). Read §1 → §2 → §6 in order.

- **Created:** 2026-05-25
- **Last updated:** 2026-05-25 (session 2 — MCP restarted; executing Path A)
- **Status:** 🚧 OPEN (Phase 1 ✅, fleet shipped) — Phases 0 ✅ + 1 ✅ done: durable tree reconciled (`998e7b6e`, blessed+promoted+deploy_pull'd to prod/VPS), all 4 products re-pointed to `deploy/fleet/` on the `18dce993` images (44 commits live), migration 038 applied, 8 hosts probed 200/401-ok. **Remaining (deferred, §7 4–6):** tunnel+services cutover off the stopgap, `legacy/` relocation, full stopgap-dir deletion, then archive both projects. Project stays OPEN — do NOT archive (success criteria §9 not fully met).
- **Owner / stakeholders:** joaoraphaelsst · architect
- **Related docs:** `projects/prod-deploy-compose-durable-relocate/PROJECT.md` (parent — Phase A + the original gated-tail enumeration), `KB § GUIDES/production-deploy.md` (§2a safe-pull drill, §4 tunnel cutover), `KB § PATTERNS/containerization-operations.md` (§1 source-of-truth chain, §2a `noctus.vps.*`), `KB § PATTERNS/branching-and-merging.md § 0.2` (release gates)
- **Project slug:** `prod-deploy-compose-vps-cutover` (platform-infra → lives at `projects/`)

---

## 1. Context & Purpose

The whole prod deploy tree (fleet + infra + tunnel composes) used to live under `projects/production-deploy-migration/deploy/`. When that project was archived, the path that the deploy tooling (`DEFAULT_COMPOSE` constant in `deploy_image.py` / `vps.py`) and the running VPS compose project pointed at moved into `archive/` and broke. A deploy-local **stopgap** copy was dropped at the old path to keep `deploy_image`/`vps.*` working.

**Parent project Phase A (already SHIPPED, commit `18dce993`)** relocated the tree to a durable repo home — **`deploy/fleet/` + `deploy/services/` + `deploy/tunnel/`** — and re-pointed **both** `DEFAULT_COMPOSE` constants to `deploy/fleet/docker-compose.prod.yml`.

**This session (already DONE):**
- ✅ `noctus.dev.release bless` — `main` fast-forwarded to `dev` tip `18dce993` (13 commits).
- ✅ `noctus.dev.release promote` — `prod` fast-forwarded to `18dce993` (**44 commits**; `prod-backup` snapshot = previous prod `c3c22eee`, the rollback pointer).
- ✅ `noctus.dev.deploy_pull confirm=True` — the **VPS git checkout** fast-forwarded to `18dce993`, so `deploy/` now physically exists on the VPS. The stopgap + `.env`/creds were **preserved** (`deploy_local_preserved: true`). Pre-pull backup: tag `backup/predeploy-20260525-152343` + tar `/opt/noctus/backups/20260525-152343.tgz`.

**What's still TRUE / load-bearing right now:**
- The **running containers are unchanged** — `deploy_pull` only moved the git HEAD; it did NOT recreate any container. The fleet still serves its pre-existing images via the **old stopgap compose file**.
- The **stopgap is still load-bearing**: until the MCP server is restarted, the running `deploy_image`/`vps.*` tools still resolve the OLD `DEFAULT_COMPOSE` path (the constant change only takes effect on a fresh MCP process). So nothing breaks in the meantime.

**The win:** re-point the running compose project to the durable `deploy/` path, delete the stopgap, reconcile the durable tunnel source from the live VPS file, live-probe, and archive both this project and the parent **with learnings absorbed**.

---

## 1a. Session-2 findings (grounded against the live VPS — these REVISE §4/§6/§9)

The handoff's "remove the stopgap" premise was that the stopgap = the fleet compose. Live `docker inspect` proved it feeds **4 compose projects**:

| Stopgap subdir | Compose project | Containers | Durable home in git? |
|---|---|---|---|
| `fleet/docker-compose.prod.yml` | `noctusai-products-prod` | core·social-wiring·erp·**seed** | ✅ `deploy/fleet/` |
| `tunnel/` (compose+`config.yml`+creds JSON) | `noctusai-tunnel` | cloudflared | ✅ `deploy/tunnel/` (data files deploy-local) |
| `services/` (compose+`.env.services`) | `noctus-services` | n8n·waha·postgres | ✅ `deploy/services/` (data file deploy-local) |
| `legacy/` (`.env`) | (legacy) | legacy | ❌ **none** (blocked on archived source) |

Consequences:
1. **`seed` was running but absent from the durable `deploy/fleet/docker-compose.prod.yml`** — a deploy-local edit during the seed canary never flowed back to git. Re-pointing as-is would orphan the live seed container. ⇒ FIXED this commit (seed service added back, port-ordered 8004).
2. **Tunnel-mount coupling** — `noctus-tunnel` bind-mounts its config from *inside* the stopgap (`projects/production-deploy-migration/deploy/tunnel/`). Deleting the stopgap before re-pointing the tunnel = all 8 hosts down on the next cloudflared recreate. The handoff marked this "optional/low-priority"; it is actually the **gating dependency** for stopgap removal.
3. **`legacy/` has no durable home** (parent project deferred it; build context → archived `reference/one-permutas`). ⇒ **full stopgap-dir deletion is NOT achievable this pass** regardless of effort.
4. **Migration state on prod** (`nyplttplcoyiiqjrvtiw`): **037 already applied** (all `url_base` = house ports), **038 NOT applied** (no `seed` row → seed served but no dashboard tile). ⇒ apply 038 with the core rollout.

**Revised scope this pass:** Path A fleet rollout (ship 44 commits + 038) + durable git-tree reconcile (compose+tunnel). **Deferred with destination** (§4 follow-up): tunnel + services cutover off the stopgap, `legacy/` relocation, and therefore full stopgap-dir deletion.

---

## 2. Confirmed constraints

- **MCP restart is a hard precondition** — the `DEFAULT_COMPOSE` constant now = `deploy/fleet/docker-compose.prod.yml`, but the *running* MCP process loaded the old value. The user is restarting the session/MCP specifically so the next agent inherits the new constant. *(Do NOT attempt step 4 before confirming the restart happened — verify with the §6 Phase 0 check.)*
- **The VPS checkout is PRODUCTION** — `KB § GUIDES/production-deploy.md § 2a`: inspect → decide → `git merge --ff-only` → verify; preserve deploy-local files (`config.yml`, creds, `.env`, `.env.bak*`); 🔴 NEVER `git reset --hard` / `checkout-over` / dev on the VPS. Operate via `noctus.vps.*` (read-free: `ps`/`health`/`logs`/`inspect`/`images`/`disk`/`stats`; confirm-gated: `restart`/`recreate`/`prune`) and `noctus.dev.deploy_image` (atomic GHCR redeploy). *(Why: the stopgap + tunnel `config.yml` are deploy-local; a hard reset would nuke them.)*
- **Compose project name is stable** — the running containers belong to project `noctusai-products-prod`. Re-pointing to the new compose file under the **same project name** migrates containers cleanly (Compose recognizes them by name+labels). *(Why: avoids orphaning / double-running containers.)*
- **Only 3 products are live** — `core`, `social-wiring`, `erp-imobiliario`. The other 7 are never-deployed (out of scope; bringing them up needs edge/DNS/env/migrations — a separate effort). *(Why: scope the re-point + any rollout to these 3.)*
- **Caddy is already retired** — `deploy/` has NO `caddy/` subdir; the fleet edge is 100% the CF named tunnel. *(Why: don't re-introduce a caddy host or expect a caddy container.)*

---

## 3. Design principles

1. **Re-point, don't rebuild-the-world.** The relocate's own job is to move the compose-file association + delete the stopgap. The 44-commit code rollout is a *separate, coordinated decision* (see §4 ⚠) — don't silently conflate them, but the cleanest mechanism happens to do both at once (deploy_image post-restart). Decide explicitly.
2. **Source-of-truth is the LIVE VPS file** for the tunnel reconcile — author the durable `config.yml.template`/`ingress.yml` from the running `config.yml`, never from the stale archive snapshot (`KB § PATTERNS/containerization-operations.md § 1`).
3. **Learn before archive.** The parent project + this one only archive AFTER the durable facts are absorbed into KB/memory (the learn-before-archive gate; `noctus.dev.archive` enforces durable-refs).

---

## 3a. Seed-first analysis

Not a per-product concern — a single platform deploy-infra surface. The fix is one durable relocation already done in the repo (parent Phase A) + the VPS-side cutover here. Per-product code count: **0**. Correctly platform-bounded; §6 phases work on platform infra, not product-by-product.

---

## 4. Scope

**In scope (the relocate tail):**
1. Re-point the running `noctusai-products-prod` compose project from the stopgap path to `deploy/fleet/docker-compose.prod.yml` (per the §4 ⚠ decision), for the 3 live products.
2. Remove the §2 deploy-local **stopgap** at `/opt/noctus/noctusai/projects/production-deploy-migration/deploy/` once the re-point is verified.
3. Reconcile the durable `deploy/tunnel/config.yml.template` + `deploy/tunnel/ingress.yml` from the **live** VPS `config.yml` (§5 has the exact diffs to capture).
4. Live-probe all 8 tunnel hosts (200 end-to-end), then **archive both this project AND the parent `prod-deploy-compose-durable-relocate` with learnings absorbed.**

**⚠ Coordination — the 44-commit promote (decide explicitly, don't skip):**
The promote shipped 44 commits to `prod`, including **live-product fixes** the 3 deployed products do not yet run: core (SSO/core-URL routing `5021ce0c`/`c3a8d352`/`531e6b53`, migrations `037`+`038`, deployment-status probe, `lib/api.ts` same-origin), social-wiring (`meta_router`/`dependencies`/FE pages), erp (FE `Configuracoes`/`LLMPreferences`/`Landing`/`Login`). So the VPS git is now *ahead of the running images* — the normal decoupled `deploy_pull ≠ rollout` state (`20c4c86b`).
- **Path A — re-point + ship the new code together (recommended if GHCR has `18dce993` images):** `noctus.dev.deploy_image <product> confirm=True` per live product. Post-restart it uses the new `DEFAULT_COMPOSE` (→ re-points to `deploy/`) AND pulls the fresh GHCR image (→ ships the 44 commits) AND health-probes with atomic rollback. One move does both. **Precondition:** GHCR images built from `18dce993` must exist — check the `build-and-push.yml` Actions run for the prod promote, or `noctus.vps.images`. If absent, trigger/await the build first. Also apply core migrations `037`+`038` to the prod Supabase before/with the core redeploy (`migrations/037_fix_product_dev_url_house_port.sql`, `038_add_seed_reference_product.sql`).
- **Path B — pure re-point now, rollout later (if you want zero code change in this pass):** `noctus.vps.recreate <product> confirm=True` per live product — post-restart it recreates from the new `DEFAULT_COMPOSE` path using the **current** local images (no code change, just the compose-file association moves). File the 44-commit rollout as its own follow-up.

**Out of scope:**
- Bringing up the 7 never-deployed products — separate effort (edge/DNS/env/migrations).
- `legacy/` deploy relocation — its `compose.legacy.yml` build context points at `reference/one-permutas` (an archived source dir); relocating cleanly needs that source relocated too. Deferred in the parent project; not a tooling-fix blocker.

---

## 5. Architecture / key facts (paths, names, IDs)

**VPS** (`ssh noctus-vps`, repo at `/opt/noctus/noctusai`):
- New durable compose (now on the VPS via deploy_pull): `/opt/noctus/noctusai/deploy/fleet/docker-compose.prod.yml` — `env_file: ../../.env` resolves to repo-root `.env` ✓.
- Stopgap to DELETE after re-point: `/opt/noctus/noctusai/projects/production-deploy-migration/deploy/` (untracked, deploy-local).
- Live tunnel config (deploy-local, the source-of-truth for the reconcile): `/opt/noctus/noctusai/projects/production-deploy-migration/deploy/tunnel/config.yml` + a pre-reconcile backup `config.yml.bak.20260525-140022` next to it.
- Durable tunnel files to AUTHOR from the live config: `deploy/tunnel/config.yml.template` + `deploy/tunnel/ingress.yml`.
- Compose project name: **`noctusai-products-prod`** (stable across the re-point).
- Rollback nets: `prod-backup` git ref = `c3c22eee` · pre-pull tag `backup/predeploy-20260525-152343` + tar `/opt/noctus/backups/20260525-152343.tgz`.

**CF tunnel** (zone `068b91fa2b2dea115c5dc589137a3279`): tunnel id `6e9ccdc5-4d99-4d5e-b9f9-1da2fe99f56c`; all 8 hosts are proxied CNAME → `6e9ccdc5-4d99-4d5e-b9f9-1da2fe99f56c.cfargotunnel.com`.

**Tunnel ingress — the 3 diffs the durable source MUST capture** (live `config.yml` differs from the stale archive snapshot; copy from LIVE):
1. **Short-name rules** — `erp.noctusai.com → http://erp-imobiliario:8001`, `social.noctusai.com → http://social-wiring:8011` (archive only had full-slug `{slug}.noctusai.com`).
2. **Infra hosts** — `n8n.noctusai.com → http://n8n:5678`, `waha.noctusai.com → http://waha:3000` (absent from the archived ingress).
3. **`seed.noctusai.com → http://seed:8004`** (added during the seed canary).
Keep the dormant full-slug `{slug}.noctusai.com` rules (they support the future `PRODUCT_URL_PATTERN={slug}.noctusai.com` scheme — harmless, no DNS points at them).

The 8 hosts: `noctusai.com` (apex/core), `core`, `erp`, `social`, `seed`, `n8n`, `waha`, `legacy`.

---

## 6. Implementation phases

### Phase 0 — Confirm the MCP restart precondition (gate) ✅
- [x] MCP restart confirmed — `noctus.vps.ps`/`health` respond; `DEFAULT_COMPOSE` now resolves to `deploy/fleet/docker-compose.prod.yml` in both `deploy_image.py:50` + `vps.py:25`. Fleet 6/6 healthy.
- [x] VPS git HEAD = `18dce993` (`deploy_pull target=origin/prod` → `up_to_date`, deploy-local files preserved).

**Improvements:** The handoff's Phase 0 step 2 told the agent to read `com.docker.compose.project.config_files` via `noctus.vps.inspect`, but that tool only returns image/state/health/ports — not labels. Had to fall back to a read-only SSH `docker inspect --format`. **Destination:** filed as a tool-gap follow-up in §7 (add a labels/compose-association field to `noctus.vps.inspect`) — a real bystander MCP-improvement, surfaced not silently worked-around.

### Phase 1 — Re-point the compose project to `deploy/` (+ 44-commit rollout) ✅
- [x] **Path A** (user-chosen). GHCR `18dce993` images confirmed (build `26407749239`). Migration 037 already on prod; **038 applied** this session (seed dashboard tile; `PRODUCT_URL_SEED` already set → tile links to https://seed.noctusai.com).
- [x] `noctus.dev.deploy_image <p> confirm=True` for ALL FOUR (`core`→`891537d2`, `social-wiring`→`229eff55`, `erp-imobiliario`→`34d9f48a`, `seed`→`b162088c`) — each snapshot→pull→up→health-probe→healthy (no rollback fired). Re-point includes `seed` because the durable compose now carries it (998e7b6e).
- [x] All four containers verified on `deploy/fleet/docker-compose.prod.yml`; `noctus.vps.health` 6/6 healthy; 8 tunnel hosts live (waha=401 is its own API-key gate, correctly routed).

**Improvements:** (1) `noctus.vps.inspect` lacks compose labels — used a raw SSH `docker inspect` fallback to verify `config_files`; filed §7 item 6. (2) **Methodology improvement spotted** — `build-and-push.yml` triggers on `main` pushes but NOT on the `prod` promote; the `bless` push to `main` is what actually built the images. A reader could assume "promote → images built." Worth a one-line note in the release/deploy docs that *images are built at bless (main), not promote (prod)* so Path-A pre-checks look at the bless build, not the promote. → noted here as a doc-clarity follow-up (KB § GUIDES/production-deploy.md), to absorb at archive time.

### Phase 2 — Remove the stopgap
- [ ] Only after Phase 1 verified green: delete the deploy-local stopgap dir `/opt/noctus/noctusai/projects/production-deploy-migration/deploy/` (and the now-empty parent if nothing else lives there — `ls` first; the `.env.bak*` files are elsewhere at repo root, don't touch those).
- [ ] Re-verify `noctus.vps.health` — nothing depends on the old path anymore.

**Improvements:** _NOC-FILL-IMPROVEMENTS — REQUIRED before this phase flips `✅`: replace with the methodology improvements spotted this phase, or write "none identified." Never ship this placeholder (keeper Rule 5 blocks it)._

### Phase 3 — Reconcile the durable tunnel source
- [ ] Read the LIVE `/opt/noctus/noctusai/projects/production-deploy-migration/deploy/tunnel/config.yml` (or wherever the running cloudflared mounts it from — verify the actual mount via `noctus.vps.inspect noctus-tunnel`).
- [ ] Author `deploy/tunnel/config.yml.template` + `deploy/tunnel/ingress.yml` (in the repo, on a self-branch off `origin/dev`) to match the live ingress, capturing the §5 three diffs + keeping the dormant full-slug rules. Commit → bless → promote → `deploy_pull` so the durable source reaches the VPS.
- [ ] (Optional) Point the running cloudflared at the durable `deploy/tunnel/config.yml` instead of the deploy-local one, so the tunnel config is also de-stopgapped. Verify tunnel stays up (`noctus.vps.logs noctus-tunnel`).

**Improvements:** _NOC-FILL-IMPROVEMENTS — REQUIRED before this phase flips `✅`: replace with the methodology improvements spotted this phase, or write "none identified." Never ship this placeholder (keeper Rule 5 blocks it)._

### Phase 4 — Live-probe + archive both projects with learnings
- [ ] Live-probe all 8 hosts end-to-end through the CF edge (200). Bypass local resolver cache with `curl --resolve <host>:443:<CF-IP>` if needed.
- [ ] Absorb durable learnings into KB/memory BEFORE archiving (learn-before-archive): the durable `deploy/` home, the re-point procedure, the tunnel-source reconcile, any new bump for `KB § PATTERNS/containerization-operations.md`.
- [ ] `noctus.dev.archive` this project AND the parent `prod-deploy-compose-durable-relocate` (durable-refs gate must pass — no `mcp/`/`scripts/` ref resolves into `projects/`/`archive/` for deploy config).

**Improvements:** _NOC-FILL-IMPROVEMENTS — REQUIRED before this phase flips `✅`: replace with the methodology improvements spotted this phase, or write "none identified." Never ship this placeholder (keeper Rule 5 blocks it)._

---

## 7. Open questions

1. ✅ **Path A or Path B?** — **DECIDED Path A** by the user (session 2). Ship the 44 commits + 038 via `deploy_image`.
2. ✅ **Does GHCR have `18dce993` images?** — **YES**, build run `26407749239` (`feat(deploy): relocate prod deploy tree`) completed success 15:22Z 2026-05-25 (triggered by the `bless` push to `main`, which carries the `products/**` paths). Path A precondition met.
3. **Re-point cloudflared at a durable `config.yml`?** — REQUIRED (not optional) to remove the stopgap, because `noctus-tunnel` mounts its config from inside the stopgap (§1a finding 2). **Deferred** this pass with destination below.

**Deferred follow-ups (named destinations — surfaced, not dropped):**
4. **Tunnel + services cutover off the stopgap** — relocate the deploy-local data files (`tunnel/config.yml` + creds JSON → `deploy/tunnel/`; `services/.env.services` → `deploy/services/`) on the VPS, re-point the `noctusai-tunnel` + `noctus-services` compose projects, recreate, verify. Higher risk (tunnel = SPOF for all 8 hosts). → its own follow-up project.
5. **`legacy/` relocation** — no durable home; build context → archived `reference/one-permutas`. Blocked on relocating that source. → carried by the parent `prod-deploy-compose-durable-relocate` (was already its deferred item).
6. **Tool gap — `noctus.vps.inspect` should expose compose labels** (`com.docker.compose.project[.config_files]`) so the Phase-1 association check doesn't need a raw SSH fallback. → small `noctus.dev`/`noctus.vps` MCP follow-up.

---

## 8. Dependencies & blockers

- **🅿️ HARD BLOCKER — MCP server restart (USER action).** The whole project waits on it (§2). Until then the running tooling resolves the old `DEFAULT_COMPOSE`; the stopgap covers that, so the fleet stays healthy — but you cannot re-point to `deploy/` via the tools until they reload the new constant.
- **GHCR images for `18dce993`** (Path A only) — see §7 Q2.
- **Core migrations `037`+`038`** must be applied to the prod Supabase if/when core is rolled out (Path A) — `products/core/backend/migrations/{037_fix_product_dev_url_house_port.sql,038_add_seed_reference_product.sql}`.

---

## 9. Success criteria (REVISED per §1a — full stopgap deletion split out)

**This pass (Path A fleet rollout + reconcile):**
- The `noctusai-products-prod` containers (incl. `seed`) are associated with `deploy/fleet/docker-compose.prod.yml` (verified via compose label).
- The 4 product containers run the `18dce993` images (44 commits shipped); `noctus.vps.health` green; migration 038 applied (seed dashboard tile live).
- Durable `deploy/fleet/docker-compose.prod.yml` carries the `seed` service; `deploy/tunnel/config.yml.template` + `ingress.yml` match the live ingress (seed + erp/social short-names + n8n/waha infra captured).
- All 8 tunnel hosts return 200 end-to-end.

**Deferred (NOT this pass — §7 items 4–6):** full stopgap-dir deletion (blocked on `legacy/` + tunnel/services cutover); archiving both projects (gated on the stopgap actually being gone). This project stays **open** with the §7 follow-ups; do NOT archive on a false "done."

---

## 10. How to use this plan

- **Do NOT start before Phase 0 confirms the MCP restart.** That is the entire reason this is a separate, handed-off project.
- Operate the VPS only through `noctus.vps.*` + `noctus.dev.deploy_image`/`deploy_pull` (the safe allowlists). Never raw `git reset`/`checkout`/`clean` on the VPS.
- Dry-run every confirm-gated tool first; read the plan; then `confirm=True`.
- Tick `- [ ]` → `- [x]` live; fill each phase's `**Improvements:**` block before flipping its header to `✅` (keeper Rule 5).
- Repo-side edits (Phase 3 durable tunnel files) go on a self-branch off `origin/dev` → bless → promote → `deploy_pull`, same as Phase A.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-25 | Filed as the VPS-side handoff of `prod-deploy-compose-durable-relocate` after this session shipped Phase A + ran bless/promote/deploy_pull (steps 1–2 of the parent gated tail). Blocked on the user's MCP restart. | claude-opus-4-7 · architect |
| 2026-05-25 (s2) | MCP restart verified (Phase 0 ✅). Path A chosen by user. §1a findings added (stopgap feeds 4 compose projects; `legacy/` no durable home; tunnel-mount coupling; 037 applied/038 not). Durable git tree reconciled: `seed` service re-added to `deploy/fleet/docker-compose.prod.yml`, `seed`+short-names+infra hosts reconciled into `deploy/tunnel/{ingress.yml,config.yml.template}`. Scope revised: full stopgap deletion deferred (§7 4–6). Branch `feat/deploy-durable-reconcile-seed-tunnel`. | claude-opus-4-7 · architect |
| 2026-05-25 (s2) | **Phase 1 ✅** — bless `main`→`998e7b6e` + promote `prod`→`998e7b6e` (prod-backup=`18dce993`) + deploy_pull to VPS; migration 038 applied to prod; `deploy_image` re-pointed + shipped all 4 products (core/social-wiring/erp/seed) onto `18dce993` images on `deploy/fleet/`; 6/6 healthy; 8 hosts live-probed. Fleet de-stopgapped. | claude-opus-4-7 · architect |
