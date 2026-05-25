# prod-deploy-compose-vps-cutover — Project Document

> **Zero-context handoff.** You did not see the session that produced this. Everything you need is inlined below. This is the **VPS-side tail** of `prod-deploy-compose-durable-relocate` (that project's Phase A relocated the deploy tree in the repo; this project finishes the cutover on the live VPS). Read §1 → §2 → §6 in order.

- **Created:** 2026-05-25
- **Last updated:** 2026-05-25
- **Status:** 📋 Filed (handoff) — 🅿️ **BLOCKED until the user restarts the MCP server** (precondition, see §8). The repo-side + release + git-pull steps are DONE; only the VPS container re-point + tunnel-source reconcile + archive remain.
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

### Phase 0 — Confirm the MCP restart precondition (gate)
- [ ] Confirm the MCP server was restarted (the whole project is blocked on this — §8). Quick proof: the running `deploy_image`/`vps` tools must resolve the NEW path. `noctus.vps.ps` / `noctus.vps.health` should work; if a deploy op still references `projects/production-deploy-migration/...`, the restart did NOT take — STOP and tell the user.
- [ ] `git -C /opt/noctus/noctusai log -1 --format=%h` on the VPS = `18dce993` (already true; re-verify with `noctus.vps.*` or an SSH read).

**Improvements:** _NOC-FILL-IMPROVEMENTS — REQUIRED before this phase flips `✅`: replace with the methodology improvements spotted this phase, or write "none identified." Never ship this placeholder (keeper Rule 5 blocks it)._

### Phase 1 — Re-point the compose project to `deploy/` (+ optional 44-commit rollout)
- [ ] Decide Path A vs Path B (§4 ⚠). If A: confirm GHCR has `18dce993` images + apply core migrations `037`/`038` to prod Supabase.
- [ ] Execute per live product (`core`, `social-wiring`, `erp-imobiliario`): Path A `noctus.dev.deploy_image <product> confirm=True` (dry-run first) **or** Path B `noctus.vps.recreate <product> confirm=True`.
- [ ] Verify each container is now associated with `deploy/fleet/docker-compose.prod.yml`: `noctus.vps.inspect <container>` → `com.docker.compose.project.config_files` should point at the new path; `noctus.vps.health` green.

**Improvements:** _NOC-FILL-IMPROVEMENTS — REQUIRED before this phase flips `✅`: replace with the methodology improvements spotted this phase, or write "none identified." Never ship this placeholder (keeper Rule 5 blocks it)._

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

1. **Path A or Path B for the re-point?** (§4 ⚠) — decided at Phase 1 by the architect/user. Recommendation: **Path A** if GHCR has `18dce993` images, because the 44 commits include real live-product fixes (core SSO/URL routing) that should ship anyway, and deploy_image re-points + rolls out + health-checks atomically in one move.
2. **Does GHCR have images built from `18dce993`?** — discover at Phase 1 via `noctus.vps.images` / the `build-and-push.yml` Actions run. If not, trigger/await the build before Path A.
3. **Should the running cloudflared be re-pointed at the durable `deploy/tunnel/config.yml` (Phase 3 optional step)?** — architect's call; the deploy-local config works, this just removes the last stopgap. Low priority.

---

## 8. Dependencies & blockers

- **🅿️ HARD BLOCKER — MCP server restart (USER action).** The whole project waits on it (§2). Until then the running tooling resolves the old `DEFAULT_COMPOSE`; the stopgap covers that, so the fleet stays healthy — but you cannot re-point to `deploy/` via the tools until they reload the new constant.
- **GHCR images for `18dce993`** (Path A only) — see §7 Q2.
- **Core migrations `037`+`038`** must be applied to the prod Supabase if/when core is rolled out (Path A) — `products/core/backend/migrations/{037_fix_product_dev_url_house_port.sql,038_add_seed_reference_product.sql}`.

---

## 9. Success criteria

- The running `noctusai-products-prod` containers are associated with `deploy/fleet/docker-compose.prod.yml` (verified via `noctus.vps.inspect` → `config_files`), with the §2 stopgap **removed**.
- `noctus.dev.deploy_image <product>` + `noctus.vps.*` operate from the durable path with no stopgap present.
- Durable `deploy/tunnel/config.yml.template` + `ingress.yml` match the live ingress (3 diffs captured).
- All 8 tunnel hosts return 200 end-to-end.
- Both this project and `prod-deploy-compose-durable-relocate` archived with learnings absorbed; durable-refs gate green; grep-clean (`git grep -n "production-deploy-migration/deploy" -- mcp/ scripts/` returns only historical-narrative refs in `archive.py`/`build-and-push.sh`, no live config refs).

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
