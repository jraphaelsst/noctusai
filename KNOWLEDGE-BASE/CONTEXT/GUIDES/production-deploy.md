# GUIDE — Production deploy of the noc fleet to a VPS

> **What this is.** The fleet-grade, evidence-tested runbook for putting noc products **live on a real domain on a single VPS**. Distilled from the 2026-05-21 `noctusai.com` migration (Replit/Coolify → Cloudflare/Hostinger). Self-contained: the durable procedure + lessons live here, not in the (archivable) project folder.
>
> **NOT** the local "put X online" drill (`KB § GUIDES/deploy-workspace-online.md` = `./start.sh` + quick-tunnel on your machine). This is the *external server* deploy.

---

## 0 · Topology (the end state)

```
Cloudflare (DNS + edge TLS + named tunnel) ──┐
                                              ├─→ ONE VPS (Hostinger/any)
your registrar (NS → Cloudflare)             │      docker, external `noctus-net`
                                              │      ├─ product containers (one each, runtime image)
                                              │      ├─ infra: redis (+ optional waha)
                                              │      └─ cloudflared (named tunnel)  ← edge option B
```

- **Compute = ONE box.** The fleet is a docker-compose Python stack — it cannot run on Workers/Pages. CF owns the *edge* (DNS/TLS/tunnel/WAF); the VPS owns the *compute*. (`KB § PATTERNS/containerization.md`.)
- **`noctus-net`** is the external shared bridge every layer joins (products + infra + edge), so containers reach each other by service name with **no published host ports**.
- **Two edge options** (pick by what the registrar lets you do — see §4):
  - **A · Caddy on real subdomains** — works with only DNS-*record* editing (no nameserver control). Auto-TLS via Let's Encrypt. Interim/standalone.
  - **B · Cloudflare named tunnel** — needs the **zone on Cloudflare** (nameservers delegated). No open ports, CF edge in front. The target end state.

---

## 1 · Code delivery = git (never rsync)

The VPS gets code by **cloning from GitHub via a read-only deploy key** — not file-copy. Redeploy = `git pull` + rebuild.

```bash
# ON THE VPS — generate a deploy key
ssh-keygen -t ed25519 -f /root/.ssh/github_deploy -N "" -C "vps-deploy-readonly"
cat /root/.ssh/github_deploy.pub        # → add as a READ-ONLY Deploy Key on the repo
ssh-keyscan -t ed25519 github.com >> /root/.ssh/known_hosts
# clone
GIT_SSH_COMMAND="ssh -i /root/.ssh/github_deploy" git clone git@github.com:<org>/<repo>.git /opt/noctus/<repo>
```

- **Push local `main` first** — `origin/main` must be current (a clone gets `origin`, not your local unpushed commits). Verify `git log origin/main..HEAD` is empty before relying on the clone.
- **Secrets do NOT travel via git.** The root `.env` is gitignored → deliver out-of-band (one-time `scp` of the file). `.env.services`/connector `.env`s likewise.

## 2 · Image delivery — build-on-VPS ∨ GHCR-pull (both live)

Product images are the slim `--target runtime` shape (baked dist, node-absent). Two models can deliver them, and **as of 2026-05-22 BOTH are live**: the repo was made **public** (→ free unlimited Actions) and the CI workflow built+pushed **all 8 products to GHCR** (public, `:sha`+`:latest`). So `--source pull` works (images exist; anonymous pull, no token) AND `--source local` works (build-on-VPS). *(History: earlier on 2026-05-22 GHCR was empty and only build-on-VPS worked — the `image: ghcr.io/...` refs were local-only names. The public-repo CI push populated it.)* The running fleet may mix the two (a product runs whatever image was last deployed to it, via either source).

**① Build-on-VPS.** Product Dockerfiles `FROM noctus-seed-*-base:dev` (built by `scripts/infra/build-base-images.sh`); each image is built on the box and tagged `ghcr.io/jraphaelsst/noctus-<slug>:latest` (the ref is just a name — nothing is pushed). `docker compose -f deploy/fleet/docker-compose.prod.yml up -d --force-recreate <slug>` then runs the freshly-built local image. **C2 (`noctus.dev.deploy_image --source local`) wraps this** with a `docker commit` snapshot → active health-probe → rollback-on-failure (commit-snapshot because tagging the container's image id is unreliable on the containerd manifest-list store — it bit us 2026-05-22). `build-and-push.sh --no-push` builds the whole set; for one product by hand:

```bash
cd /opt/noctus/<repo>
bash scripts/infra/build-base-images.sh dev          # seed bases — product Dockerfiles FROM :dev (hardcoded)
set -a; source .env; set +a                           # VITE_SUPABASE_* from .env
docker build --target runtime -f products/<slug>/backend/Dockerfile \
  -t ghcr.io/<org>/noctus-<slug>:latest \
  --build-arg VITE_SUPABASE_URL="$VITE_SUPABASE_URL" \
  --build-arg VITE_SUPABASE_PUBLISHABLE_KEY="$VITE_SUPABASE_PUBLISHABLE_KEY" \
  --build-arg VITE_CORE_URL="https://core.<domain>" \
  --build-arg VITE_CORE_API_URL="https://core.<domain>" .
```

> ⚠️ **`VITE_*` are BAKED at build time** (Vite inlines `import.meta.env.VITE_*`). `VITE_CORE_URL`/`VITE_CORE_API_URL` MUST be the **public** URL where `core` is served — `core`'s own FE reads `VITE_CORE_API_URL` for its API (`products/core/frontend/src/lib/api.ts`); other products' own API is same-origin (`VITE_BACKEND_API_URL` define-injected to `window.location.origin`). Bake `localhost` → broken public app; rebuild to fix. (`KB § PATTERNS/boundary-contract-tests.md` B1.)

> 🧭 **Cross-product NAV is a SEPARATE, RUNTIME layer (not baked) — easy to miss at deploy time.** The Core dashboard's product-launcher tiles resolve each product's URL **per-request** via `noctusai_lib.api.product_urls.resolve_product_url` (order: `PRODUCT_URL_<UPPER_SLUG>` → `PRODUCT_URL_PATTERN` → DB `public.products.url_base`). The DB column **stays at its `localhost` dev default by design**; production sets the URLs in the **VPS root `.env`** — no rebuild, just `--force-recreate core`. Miss this and every dashboard tile links to `localhost` (the 2026-05-22 nav-remap bug). The noctusai.com scheme is **hybrid**: `PRODUCT_URL_PATTERN=https://{slug}.noctusai.com` + per-product overrides for the live short names (`PRODUCT_URL_ERP_IMOBILIARIO=https://erp.noctusai.com`, `PRODUCT_URL_SOCIAL_WIRING=https://social.noctusai.com`). Also **seed each product's `public.products` row** — the launcher only renders rows it finds, so a missing row = no tile even when the product is live (social-wiring's `032` seed was never mirrored to prod → it had no tile until 2026-05-22). Full var docs: `.env.example` → "Cross-product navigation URLs". The FE back-link/SSO-callback (`VITE_CORE_URL`/`VITE_CORE_API_URL`) are the *baked* sibling above — change those = rebuild.

**② GHCR-pull — the CI delivery layer (`.github/workflows/build-and-push.yml`; LIVE).** The workflow runs on push to `main` (path-filtered to `products/**`/`seed/**`/the build script) + `workflow_dispatch` (with a `products` input for a fast targeted/test build); it runs `build-and-push.sh` and pushes `ghcr.io/jraphaelsst/noctus-<slug>:<sha>` (immutable) **+ `:latest`**. GHCR auth = the built-in `GITHUB_TOKEN` (no PAT). **Repo secrets:** `VITE_SUPABASE_URL` + `VITE_SUPABASE_PUBLISHABLE_KEY` (baked into the FE bundle — the step is **fail-closed** if absent, so it never pushes a broken-FE image; set 2026-05-22). Packages are **public** (repo is public) → the VPS pulls anonymously, **no token**. Deploy with `noctus.dev.deploy_image <product> --source pull`. **This is the DELIVER layer; C2 (`deploy_image`) is the deploy/rollback-safety layer — they compose, neither supersedes the other.** Building on `main` does NOT auto-deploy to prod (the `prod` promote-gate stands); the immutable `:<sha>` tags also give durable rollback/DR (pull an old sha). Pros/cons (minutes/storage; for one VPS build-on-VPS is cheaper): `[[reference_production_deploy_runbook]]`. Full runbook: `deploy/fleet/README.md`.

## 2a · Safe ongoing code-sync — the "pull" drill (the VPS checkout is PRODUCTION)

The VPS clone is a **production artifact, not a workspace.** Code reaches it ONLY by `git pull` of *pushed* commits; secrets + runtime-config live in **deploy-local files** that are gitignored or filled in-place on the box (`deploy/tunnel/config.yml`, the tunnel creds `<id>.json`, the root `.env`, `.env.services`) — a sync MUST always preserve them. **The VPS tracks `origin/prod`, NOT `origin/main`** (the prod promote-branch cutover landed 2026-05-22 — see §2b): you push work to `main`, *promote* a blessed `main` sha to `prod`, and only then does the VPS pull it. SSH is `ssh noctus-vps` (`~/.ssh/config`, `root@72.61.28.36`). Two invariants make it safe: **ff-only** (the merge refuses anything that isn't a clean fast-forward — that refusal IS the safety net) ∧ **inspect → decide → act → verify** (never move HEAD blind). 🔴 NEVER `git reset --hard origin/main` ∨ `git checkout -- <deploy-local-file>` on the VPS — those silently nuke deploy-local state. NEVER edit code on the VPS (it's not a dev box; deploy-local files are the *only* sanctioned divergence).

**The drill** (run in `/opt/noctus/<repo>`; deploy key pinned per §6 `core.sshCommand`):

```bash
# 0) PUSH+PROMOTE FIRST (on your machine): push to main, then promote the blessed
#    sha to prod (§2b): git checkout prod && git merge --ff-only <sha> && git push origin prod
ssh noctus-vps    # the VPS checkout is /opt/noctus/noctusai, on branch `prod`
# 1) INSPECT — before moving HEAD
git log  --oneline -1                       # current deployed HEAD
git fetch origin                            # refs only — does NOT move HEAD
git status --short                          # ⭐ RECORD the deploy-local state to preserve (M / ??)
git log  --oneline HEAD..origin/prod        # incoming commits
git diff --name-only HEAD..origin/prod      # incoming files (any product runtime / compose / Caddyfile?)
# 2) DECIDE — cross-check incoming files vs the M/?? set from `status`:
#    no overlap → clean FF (safe).   overlap → STOP, resolve deliberately (never reset / checkout-over).
git tag -f backup/predeploy-$(date +%Y%m%d-%H%M%S) HEAD   # C1 backup ref before the move
# 3) ACT — ff-only (refuses a non-fast-forward; never plain `git pull`, which can merge-commit)
git merge --ff-only origin/prod
# 4) VERIFY
git log  --oneline -1                       # == the promoted sha
git status --short                          # SAME deploy-local files still M / ?? (preserved)
grep -c "<marker-from-new-commit>" <a-changed-file>   # the change actually landed on disk
```

**Then rebuild ONLY if the running container serves what changed** (validation-freshness, §6 + `KB § PATTERNS/containerization.md § 12b`):
- **docs / project files only** → nothing to do; the running fleet is untouched (the 2026-05-21 doc syncs were exactly this — pull, no rebuild).
- **product code / Dockerfile / compose changed** → rebuild the slim `runtime` image on the VPS (§2) + restart that product, then live-probe the endpoint. Single-file bind-mounts (`config.yml`, `Caddyfile`) need `docker restart` (stale-inode, §6), not `reload`.

> **⚠ Two-step deploy contract — `deploy_pull` does NOT roll out the new code.** `noctus.dev.deploy_pull confirm=True` advances the VPS **code checkout only** (ff-only) + takes the C1 backup — it **never builds, recreates, or restarts a container**, so the running fleet keeps serving the OLD images until you act. The container rollout is the **separate** `noctus.dev.deploy_image <product>` step (C2 below: snapshot→acquire image→`up -d`→health-probe→auto-rollback), run **once per product** in the returned `rebuild_products`. `deploy_image --source pull` consumes the GHCR `:<sha>`/`:latest` images (§2 ②) — so it requires the `build-and-push.yml` run for that sha to have **succeeded** (a red GHCR build ⇒ no fresh image ⇒ a pull-deploy would silently roll out stale code; gate the rollout on the build going green). **Full prod deploy = bless (§0.2/§2b) → promote (§2b) → `deploy_pull confirm=True` → [GHCR build green] → `deploy_image <slug>` per rebuilt product → live-probe.** Future agents: do not conflate "the pull succeeded" with "the deploy is live."

Why `--ff-only` over `git pull`: a plain pull can create a merge commit (diverging the VPS from `origin/main`) or fail confusingly against deploy-local edits; `--ff-only` either advances cleanly or **refuses and leaves you to decide** — never a surprise mutation of production.

**Codified as `noctus.dev.deploy_pull`** (CLI `--deploy-pull` *(2026-05-22)*) — the drill as a tool that runs it over SSH: INSPECT → DECIDE (the overlap-check and the rebuild decision become **deterministic predicates**, not a human eyeball) → BACKUP (`git tag` + `tar` the deploy-local files to `/opt/noctus/backups`, outside the repo) → `merge --ff-only` → VERIFY. **DRY-RUN by default** (returns the plan: incoming commits/files, FF-ability, deploy-local overlap, derived rebuild decision); pass `confirm=True` (CLI `--deploy-confirm`) to actually fast-forward — the 412-style production write gate. It **refuses** a non-FF or a deploy-local overlap, and **by construction can only run a safe git allowlist + a tar backup** — it can *never* emit `reset`/`checkout`/`clean`/`push` (a colocated test asserts this). Prefer the tool over hand-typing the drill: the dangerous commands are unreachable, not merely avoided.

### Safety-net stack — defense in depth (the production code is a diamond)

The drill is the *procedure*; these are the *structural* nets that make it hard to get wrong. Layered **preventive → detective → corrective** so no single human/agent mistake can damage, reverse, or half-deploy production. Status: ✅ live · ⏳ to-implement (tracked in `projects/deploy-hardening-and-dev-isolation/PROJECT.md`).

**Preventive — a bad state can't even be created**
- **P1 · `--ff-only` only** ✅ — the VPS HEAD can only ADVANCE along pushed history; never diverges, rewinds, or merge-commits. A non-FF is *refused*, not forced.
- **P2 · read-only deploy key** ✅ — the VPS key pulls, never pushes ⇒ the VPS can never mutate the remote (no broken local state escaping upward). Verify write-access is OFF on the GitHub deploy key.
- **P3 · protected `prod` promote-branch** ✅ *(cutover 2026-05-22 — see §2b)* — the VPS tracks `origin/prod` (advanced only via the promote ritual; the live remote is the source of truth for its current sha — don't hardcode it here, it drifts), never `main`; code reaches prod only by a *deliberate* FF of `prod` from a blessed `main` sha. Branch-protection is **client-side** (`scripts/hooks/pre-push` refuses force-push+deletion of `main`/`prod`) because server-side GitHub protection needs Pro on a private repo; combined with P2 (read-only deploy key — the VPS can't push at all) the prod history is guarded. Promote ritual + cutover steps in §2b.
- **P4 · deploy-local files GITIGNORED, never tracked** ✅ *(repo-side + VPS migration DONE 2026-05-22)* — the rendered `deploy/tunnel/config.yml` AND the tunnel creds `*.json` are gitignored (`**/tunnel/config.yml`, `**/tunnel/*.json`); the only tracked artifact is `config.yml.template` (placeholders, no secrets). A pull cannot touch deploy-local state *by construction*. The one-time VPS migration ran 2026-05-22 (back-up → move-aside → ff-only → restore → verify-ignored — `deploy/tunnel/README.md`): post-migration the live box's working tree is **clean** (`git status` shows neither file), so no future pull dances around a tracked deploy-local file. Verified: `git check-ignore` HIT for config.yml + .env + the creds JSON (the `deploy_state.py` D3 set).
- **P5 · pre-deploy verification gate** ✅ *(2026-05-22)* — `noctus.dev.predeploy_check <product>` (CLI `--predeploy-check <product> [--fix]`): runs framework-dep parity + frontend `vite build` + backend `pytest` + the **D3 deploy-local-gitignored assertion** (`deploy_local_gitignored` — fails on any tracked/un-ignored deploy-local file in `deploy_state.DEPLOY_LOCAL_FILES`); `status='ready'` (all pass) only then is code fit to promote/restart ("always-only functional code online"). It also **classifies** failures against the boundary-contract classes, **auto-fixes** the framework-dep class (`--fix`), and **reports+learns** unknowns (`predeploy-reports/` + `phase_learnings` s1). Run it before the promote ritual (§2b). C1/C2 (below) are the VPS-runtime corrective companions.

**Detective — a bad state is caught immediately**
- **D1 · inspect-before-HEAD-move** ✅ (drill §1–2).
- **D2 · verify-after** ✅ (drill §4): HEAD == expected sha, deploy-local files still present, marker landed on disk.
- **D3 · deploy-state manifest** ✅ *(asserted by `predeploy_check` 2026-05-22; graduated to a durable code constant 2026-05-22)* — `deploy_state.DEPLOY_LOCAL_FILES` (a code constant in `mcp/noctusai/deploy_state.py` — replaced the transient `projects/.../deploy/STATE.json` so it can't be lost to an archive) enumerates the deploy-local gitignore-style patterns + the destructive-command-ban invariants; `noctus.dev.predeploy_check`'s `deploy_local_gitignored` check **enforces** it (every pattern must be NOT tracked ∧ covered by a gitignore rule — a violation classifies as `deploy_local_tracked` and blocks; the gate always runs since the manifest is code, never a missing file), and `noctus.dev.deploy_pull` reads it to know which files C1 backs up. The human-facing rule lives here (prose); the data lives in the constant. (Image-digest / per-file sha256 capture is a v2 add.)
- **D4 · health-probe after restart** ✅ (validation-freshness, §6): the container must serve the new code or it's not a successful deploy.

**Corrective — any mistake is reversible**
- **C1 · backup ref before any HEAD move** ✅ *(exercised 2026-05-22)* — `git tag -f backup/predeploy-<utc> HEAD` + `tar` the deploy-local files. Refinement: backups land **outside** the repo at `/opt/noctus/backups/<utc>.tgz` (NOT `deploy/backups/` — a backup inside the tracked tree is a footgun that a stray `git add` could commit). One ref + one tarball restore last-known-good (code via reflog/tag, deploy-local via the tarball).
- **C2 · atomic image rollback** ✅ *(2026-05-22 — `noctus.dev.deploy_image`; live-validated on social-wiring incl. a real rollback)* — a product-image redeploy is atomic + **fail-safe**: `docker commit` the running container → `:previous` (a reliable rollback target — tagging the container's image id is NOT reliable on the containerd manifest-list store) → **VERIFY the snapshot resolves, else REFUSE to deploy** (no confirmed rollback target ⇒ container untouched) → acquire the new image (`--source local` for the live build-on-VPS model §2 ①, or `--source pull` once GHCR is active §2 ②) → `up -d --force-recreate` → **active** `/api/health` probe (port from the container healthcheck; fast detection + startup grace) → on failure, retag `:previous` → `:<tag>` + `up -d --force-recreate` + re-probe + **VERIFY restored** (loud `rollback_failed` + a manual-recovery command if not — never a false `rolled_back`). Run `noctus.dev.deploy_image <product>` (CLI `--deploy-image [--deploy-image-source local] [--deploy-image-confirm]`); DRY-RUN by default. By construction it only uses a safe docker allowlist (inspect/image/tag/ps/exec/commit + compose pull/up), never rmi/prune/down (a colocated test asserts it). `deploy_pull`'s rebuild-decision points here when a pull touches product runtime. **Hardened by a live failure 2026-05-22** (an earlier version falsely reported `rolled_back` while prod stayed broken → a real social-wiring outage; the snapshot-verify + rollback-verify + commit-snapshot fixes were proven by re-validation).
- **C3 · reflog is the time machine** ✅ — commits are never lost; recovery = `git reflog` → `git reset --hard <sha>` is the **ONE** sanctioned hard-reset (recovery onto a backup, *never* as a sync step).

**🔴 The destructive-command ban (and the single exception).** As a *sync* step, NEVER run any of these on the VPS — each destroys exactly what it should preserve:
- `git reset --hard origin/*` → discards the in-place deploy-local edits (`config.yml`) ∧ can rewind HEAD below the deployed sha.
- `git checkout -- <deploy-local-file>` / `git restore <…>` → overwrites the filled deploy file with the tracked placeholder.
- `git clean -fdx` → deletes the untracked creds `.json` ∧ `.env`.
- `git push --force` → impossible with the read-only key (P2), and never from anywhere.

The ONLY sanctioned `reset --hard` is **C3 recovery** onto a `backup/` ref after a *verified* mistake — never to "make the pull work". If a pull won't fast-forward, that is the safety net doing its job: STOP and diagnose, do not force.

## 2b · Branch model — the `prod` promote gate (P3; the extra layer beyond "git = the wall")

`dev` is the everyday **integration** branch (where work lands + accumulates — `KB § PATTERNS/branching-and-merging.md § 0`). `main` is the **blessed-release** ref (a deliberate `dev → main` FF promotes a reviewed, green line). `prod` is the **promotion** branch — the *only* ref the VPS pulls. Code becomes production *exclusively* by a deliberate human FF of `prod` from a blessed `main` sha. Two walls: a push to `dev` does NOT reach `main`, and a push to `main` does NOT reach prod — someone must **bless** (`dev → main`) then **promote** (`main → prod`). Both hops are pre-push-hook-gated (`NOCTUS_ALLOW_MAIN_PUSH=1`). (The user's requirement: *"when any branch is 100% to go for main it goes to prod branch and the vps only accepts pulls from prod branch."*)

```
feat/* ──▶ dev ──(bless: dev→main FF)──▶ main ──(promote: prod FF)──▶ prod ──(VPS §2a pull)──▶ production
           ▲ integration                ▲ release                   ▲ promotion gate          ▲ live
```

**The promote ritual** — codified as `noctus.dev.release stage='promote'` (dry-run → `confirm=True`): it snapshots the current prod onto `prod-backup`, FFs `prod` to the blessed sha, and is the only sanctioned setter of `NOCTUS_ALLOW_MAIN_PUSH`. The hand-run equivalent (run on your machine when a `main` sha is 100% ready):
```bash
# 0) pick the blessed sha — green checks, predeploy_check passed (Phase 4)
git fetch origin
git push origin origin/prod:refs/heads/prod-backup            # snapshot current prod (rollback pointer)
NOCTUS_ALLOW_MAIN_PUSH=1 git push origin <blessed-main-sha>:refs/heads/prod   # FF only — prod never diverges
# 1) deploy: noctus.dev.deploy_pull confirm=True  (FFs the VPS to origin/prod; §2a)
```
`prod` only ever fast-forwards from `main` ⇒ it can never carry code that didn't pass through integration; the VPS only ever fast-forwards from `prod` (P1) ⇒ production can only advance along promoted history.

**One-time cutover — ✅ DONE 2026-05-22** (the VPS now runs on branch `prod` tracking `origin/prod`; the repoint was a clean docs/connector-only FF, deploy-local `config.yml`+creds preserved, `backup/predeploy-*` ref tagged, fleet verified healthy). The steps, for reference / re-runs on another box:
1. **Create + push `prod`** off the current deployed sha: `git branch prod <deployed-sha> && git push -u origin prod`. *(Agent stages a local `prod` branch; the push is presented for go/no-go — phased-push policy.)*
2. **Branch protection.** ⚠️ Server-side GitHub branch protection *and* rulesets need **Pro on a private repo** (free-private ⇒ HTTP 403 "Upgrade to GitHub Pro or make this repository public"). On the free-private plan the equivalent is **client-side**: the `scripts/hooks/pre-push` hook (installed by `scripts/install-hooks.sh`) refuses force-push + deletion of `main`/`prod` (the two destructive ops) — `git push --no-verify` is the deliberate-bypass. Server-side rulesets become the upgrade path *if* the repo ever goes Pro/public; until then P2 (read-only deploy key — the VPS can't push at all) + this hook + the §2a discipline carry the protection.
3. **Point the VPS at `origin/prod`**: on the box, `git fetch origin && git checkout -B prod origin/prod` then use `origin/prod` in the §2a drill from then on. *(VPS shell — a deploy action; current-state-dependent: a true no-op only if the VPS HEAD already == `origin/prod`, otherwise it's a real deploy → run the full §2a drill + rebuild decision.)* SSH is set up as a one-liner: `~/.ssh/config` `Host noctus-vps` (`root@72.61.28.36`, the `noctusai-deploy` key) ⇒ `ssh noctus-vps '<cmd>'`.
4. **Flip the §2a drill default** to `origin/prod` once 1–3 are done (until then it stays `origin/main`, to avoid asserting a state that isn't live — codebase-is-source-of-truth).

Until the cutover lands the VPS continues to track `origin/main` (the doc deliberately does not lie about which ref is live). Tracked in `projects/deploy-hardening-and-dev-isolation/PROJECT.md` Phase 3.

## 3 · Bring up (infra + products on `noctus-net`)

```bash
docker network create noctus-net 2>/dev/null || true     # one-time
docker compose -f deploy/fleet/compose.infra.prod.yml up -d        # redis (+ --profile waha if WhatsApp)
docker compose -f deploy/fleet/docker-compose.prod.yml up -d core <slug>...   # subset = a wave
# verify (ports are internal — exec curl, no host publish)
docker exec noctus-<slug> curl -fsS http://localhost:<port>/api/health
```

Products use **remote Supabase** (not local postgres) + `redis://noctus-redis:6379` over `noctus-net`. `restart: unless-stopped` survives reboots.

## 4 · Edge — pick A or B by what your registrar allows

**First check what you can do at the registrar.** Many platform-resold domains (Replit/Wix/…) only expose **DNS-record editing**, not nameserver delegation — see `KB § INTEGRATIONS/` and the domain-reseller note in memory. `whois <domain>` finds the real registrar; the platform UI ≠ the registrar.

### Option A — Caddy on real subdomains (DNS-records-only path)

Add `A <slug> → <VPS-IP>` records at the registrar. Caddy reverse-proxies + auto-issues per-host LE certs (HTTP-01). Needs ports 80/443 free (displace any prior proxy first — see §5).

```caddyfile
{ email you@domain }
core.<domain>   { reverse_proxy core:8000 }
<slug>.<domain> { reverse_proxy <service>:<port> }
```
```bash
docker compose -f deploy/caddy/compose.caddy.yml up -d   # joins noctus-net, publishes :80/:443
```

### Option B — Cloudflare named tunnel (zone-on-CF path; the target)

Needs the zone active on Cloudflare (nameservers → CF). Then:
```bash
# create the tunnel (CF API or `cloudflared tunnel create`); config_src=local for config.yml ingress
# creds JSON on the VPS, chown 65532:65532 chmod 600 (cloudflared runs nonroot)
docker compose -f deploy/tunnel/compose.tunnel.yml up -d   # cloudflared --protocol http2
# DNS routes: cloudflared tunnel route dns <name> <hostname>  (or proxied CNAME → <id>.cfargotunnel.com)
```
Ingress is a single source of truth (`deploy/tunnel/ingress.yml`) → remap a slug = 1 edit + re-apply. `--protocol http2` is pinned (QUIC dropped by NATs).

### Migrating A → B later (zero URL change)

Real subdomains chosen in A are the **final URLs**. When the domain reaches Cloudflare: bring up the tunnel (B), create the CNAMEs, verify, then stop Caddy. The `<slug>.<domain>` URLs never change — only the plumbing.

## 5 · Decommissioning a prior PaaS (e.g. Coolify) — preserve stateful data

If the box ran a PaaS managing stateful services (n8n/waha/postgres/redis), migrate them to **raw compose reusing the EXISTING named volumes** before removing the PaaS:

```yaml
# deploy/services/compose.services.yml — external volumes = the PaaS's data, untouched
volumes:
  n8n-data:      { external: true, name: <paas-prefix>_n8n-data }
  waha-sessions: { external: true, name: <paas-prefix>_waha-sessions }
  # ...
```
```bash
docker stop <paas>-n8n <paas>-waha <paas>-postgres        # brief downtime starts
docker compose --env-file .env.services -f deploy/services/compose.services.yml up -d postgres n8n waha
# VERIFY data survived (volume mounts + sizes) BEFORE touching the proxy → rollback = restart the PaaS containers
docker stop <paas>-proxy && docker compose -f deploy/caddy/compose.caddy.yml up -d   # proxy swap
# only after all green: docker rm the PaaS containers + control-plane; rm its host data dir; keep DATA volumes
```
- **WAHA resumes without QR:** auth persists in the sessions volume but WAHA doesn't auto-start saved sessions → `POST /api/sessions/<name>/start`.
- Keep PaaS containers **stopped, not deleted**, until verified green (rollback net).

## 6 · Lessons (evidence-tested 2026-05-21 — heed these)

| Gotcha | Rule |
|---|---|
| **LE DNS negative-cache** | NEVER add a host to Caddy/LE before its A-record exists — a failed ACME poisons LE's NXDOMAIN cache (SOA neg-TTL, ~1h). Sequence: A-record → then Caddy. Recover: poll `dig @1.1.1.1/@8.8.8.8/@9.9.9.9` until it resolves → `docker restart` the proxy (clears ACME backoff). |
| **compose `${VAR:?}`** | `docker compose` interpolates required vars on EVERY subcommand (`ps`/`exec`, not just `up`) → pass `--env-file` everywhere. |
| **`depends_on` over-starts** | `up -d a b c` also starts their `depends_on` services → can collide on a shared network alias. Name only what you need + drop needless deps. |
| **cloudflared nonroot (uid 65532)** | root-owned `0600` creds = unreadable → `chown 65532:65532`, keep `0600` (not world-readable). |
| **local resolver lies** | your machine's negative-cache outlives the world's → verify externally with `curl --resolve <host>:443:<ip>`, not the bare hostname. |
| **single-file bind-mount goes stale on `git pull`** | A container bind-mounting a SINGLE config file (`./Caddyfile:/etc/caddy/Caddyfile`, `./config.yml:…`) keeps the **original inode**. `git pull`/editors replace files via rename → a NEW inode → the container still sees the OLD content, so `caddy reload` (or `cloudflared` re-read) applies a **stale config silently** (e.g. a just-added vhost is missing, no cert issued). **Verify** `docker exec <c> grep <new-thing> /etc/.../file` (it'll be absent) → **`docker restart <container>`** (re-establishes the mount against the current inode), not just `reload`. Proper fix: bind-mount the **directory**, not the file. Bit the `legacy.noctusai.com` Caddy route. |
| **Django `ALLOWED_HOSTS` + healthcheck** | a strict `ALLOWED_HOSTS` (e.g. `legacy.noctusai.com`) makes a bare `curl localhost` 400 (`DisallowedHost`) → the compose healthcheck must send the real Host: `curl -fsS -H "Host: <domain>" http://localhost:<port>/`. |
| **product LLM = OpenAI/Gemini** | `noctusai_lib.integrations.llm` ships openai/gemini/fake — **no Anthropic provider**; default `openai`/`gpt-4o-mini`; key via `resolve_credential` Tier-3 env fallback (`OPENAI_API_KEY`). ANTHROPIC only for `dev-team` (agno). |
| **platform-auto-installed deps missing from the manifest (external/absorbed app)** | A Replit/PaaS packager auto-installs deps **without writing them to the committed manifest** → a clean reproducible `docker build` misses them. Hit **twice** in the legacy `one-permutas` build: ① **npm root-hoist** — `@supabase/supabase-js` lived in the MONOREPO ROOT `package.json` (resolved via hoisted parent `node_modules`), invisible to an isolated `frontend/` `npm ci` → `TS2307: Cannot find module`; ② **pip framework-implicit** — `Pillow` (Django `ImageField` requires it) wasn't in `requirements.txt` at all → `fields.E210` at the `manage.py` system check. **Fix:** diff actual imports (+ framework-implicit deps like Pillow) against the manifest the Dockerfile installs; add the missing ones to the Dockerfile (`npm install --no-save <pkg>` / `pip install … <pkg>`), pinned. **Surface them at BUILD time** — run the frontend `build` + `manage.py collectstatic`/`check` in the Dockerfile so a missing dep fails the build, not prod. (Bonus Django gotcha: a prod-settings *shim* must sit in the **config package** `backend/backend/` next to `settings.py` for `DJANGO_SETTINGS_MODULE=backend.settings_prod` to import.) |
| **VPS git deploy key must be pinned** | A read-only GitHub deploy key that *authenticates* (`ssh -i <key> -T git@github.com` → "successfully authenticated") still fails `git fetch`/`git pull` with `git@github.com: Permission denied (publickey)` from a fresh SSH session — git uses the **default** identity, not the deploy key, unless told to. The clone often worked via an inline `GIT_SSH_COMMAND=` or a loaded `ssh-agent` that **doesn't persist**. **Durable fix:** pin it on the repo — `git config core.sshCommand 'ssh -i ~/.ssh/<deploy_key> -o IdentitiesOnly=yes'` (or a `~/.ssh/config` `Host github.com` block). Without it the "redeploy = `git pull`" pipeline silently breaks on the next session. To push a single file without a full pull: `git fetch && git checkout origin/main -- <path>`. |
| **lost SSH → recover via the host console (box stays up)** | If your VPS login key stops being accepted (`Permission denied (publickey)`) — e.g. a PaaS teardown rewrote `/root/.ssh/authorized_keys` — the box is usually fine (sites still serve); you only lost the shell. Re-add your pubkey from the provider's **browser/VNC console** (Hostinger hPanel → VPS → Browser terminal): `echo '<pubkey>' >> /root/.ssh/authorized_keys`. (Gotcha: a deploy key distributed as a *folder* `~/.ssh/<name>/id_ed25519` — point `ssh -i` at the inner file; the dir needs `700`, not `600`.) |
| **apex = same-origin, no rebuild** | Serving a noc product at the bare apex (`noctusai.com` → `core:8000`) needs **no rebuild and no CORS change** — the seed FE calls its backend at `window.location.origin` (`VITE_BACKEND_API_URL` define-injection), so it just works at whatever host Caddy routes. `VITE_CORE_API_URL` is only for *other* products calling core. Add the Caddy vhost, `docker restart` the proxy, done. |
| **CF auto-import is partial + orange-by-default → rebuild + verify the zone BEFORE the NS flip** | When you add a domain to Cloudflare, CF's auto-import of the existing records is **not trustworthy**: it can **miss records** and it defaults A/CNAME to **proxied (orange)**. With a Caddy-on-the-VPS edge (each host doing its own LE HTTP-01), orange is fatal — CF grabs port 80 → cert renewal breaks; and any missed host goes dark the instant the NS delegates. "We only have to wait for the nameservers" is therefore a **per-record** check, not yes/no: before asking the registrar to flip, **rebuild the CF zone to a complete grey-cloud mirror of exactly what the edge serves** (the Caddyfile / tunnel ingress is the source-of-truth host list; drop stale PaaS-era hosts like `api`/`coolify`), then **prove it against the assigned CF nameservers directly** — `dig @<clyde>.ns.cloudflare.com / @<lina>.ns.cloudflare.com A <host>` answers authoritatively *even while the zone is `pending`*, so you validate with **zero live risk** (the registrar's NS stay authoritative until the flip). Also: a registrar reply of "here's your EPP/auth code" is a **transfer** authorization, NOT an NS change — CF Registrar won't accept the transfer until the zone is Active, so the NS repoint is the prerequisite either way. |
| **core CORS is localhost-only in prod** | core's `cors_origins="@registry:all"` resolves via `noctusai_lib.config.cors_registry.derive_cors_origins`, which emits **only** `http://localhost:<port>` → in prod **no real origin is allowed**: the apex login (`noctusai.com`→`core.noctusai.com`) and every product's SSO-token validation are browser-blocked, surfacing as the FE's "Servidor indisponível (/api/auth/login)". Fix: set `CORS_ORIGINS=<prod origins, comma-sep>` in the **VPS `.env`** + `--force-recreate core` (no rebuild). NEVER `*` — core wires `allow_credentials=True` and `*`+creds is the auth-replay anti-pattern (the seed forbids it). Verify with an OPTIONS preflight: `curl -i -X OPTIONS https://core.<domain>/api/auth/login -H 'Origin: https://<domain>' -H 'Access-Control-Request-Method: POST'` must echo `access-control-allow-origin`. **Seed-first cure** (follow-up): make `derive_cors_origins` deploy-aware so `@registry:all` auto-includes the prod origins from the `PRODUCT_URL_*` scheme + apex — then no hand-maintained `CORS_ORIGINS`. Bit 2026-05-22 (login down at apex). |

## 7 · Artifacts + graduation

The composes/Caddyfile/scripts referenced live under a project's `deploy/{fleet,services,tunnel,caddy,legacy}/` while a migration is active. **They should graduate to a durable home** (`scripts/infra/` or a `deploy/` template set, or a `noctus.dev.deploy` MCP tool) once the shape stabilizes — that is the "automate by evidence" follow-up. Until then, copy from the most recent deploy project and adapt the placeholders.

> **MCP tools that operate the deploy:** `mcp/hostinger` (VPS power/metrics), `mcp/cloudflare` (zones/DNS/tunnel — used to create the named tunnel here), `mcp/waha` (session ops), `mcp/n8n` (workflow ops). See `KB § MCP-SERVERS/`.
