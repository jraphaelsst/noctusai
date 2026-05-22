# Containerization Operations — Runbook & Methodology

> **Sibling, not replacement.** `containerization.md` (this doc's sibling)
> is **architecture** — single-container-per-product, shared bases, the
> propagate pipeline, the seams. THIS doc is **operations** — how to
> actually work with containers day-to-day, what bugs you'll hit, the
> diagnostic order, and the methodology for safe container changes.
>
> **Status.** Starting point — consolidates the 2026-05-19 session
> bumps into one operational reference (current count: §3.1-3.18; row
> count grows as new bumps surface — don't hand-cite a number). Bumps
> codified elsewhere (KB pattern
> docs, memory) are pointed at here so this stays the **single entry
> point** for "what does it take to operate the fleet."

---

## 0 · When to use this vs `containerization.md`

| Need to… | Read |
|---|---|
| Understand the architecture (single container, bases, propagate, seams) | `containerization.md` (sibling) |
| Operate / debug / verify containers / change container config | **THIS doc** |
| Add a new container feature / structural change | both, in this order: arch → ops |
| One specific gotcha quickly | jump to §3 (known bumps) |

---

## 1 · Source-of-truth chain (verify-don't-assume, ordered)

When something "doesn't work," walk this chain — each layer of derivation
*drifts*; verify against the most direct source. The 2-day-chaos session
was almost entirely a series of skipped steps in this chain.

1. **`git status` / `git log` / `git reflog`** — codebase first. Reflog
   names branch moves (`checkout: moving from A to B`) when commits
   appear lost — they're not, they're on the branch they were authored
   on (`git log --oneline --all --source | grep`).
2. **The file on disk in the actual checkout.** The primary tree may
   carry stray host-populated artifacts (esp. `node_modules`) that mask
   bugs visible only in a clean checkout / worktree / CI.
3. **`docker manifest inspect <ref>`** / **`docker buildx imagetools
   inspect <ref>`** — multi-arch availability before pinning `platform:`.
4. **`docker history --no-trunc <image>`** — what's *in* the image
   (layers, RUN commands actually executed, sizes).
5. **`docker run --rm --entrypoint sh <image> -- ls <path>`** — image
   filesystem **without** running container init / bind-mounts.
6. **`docker inspect <ctr> --format '{{range .Mounts}}{{.Destination}}
   {{end}}'`** — the **mount set the container actually has**. Compose
   edits to volumes don't auto-recreate; this is where stale mounts get
   caught (§3.6).
7. **`docker exec <ctr> ls <path>`** — runtime filesystem AFTER mounts
   apply (anon-volume seeded? bind-mount masked the image content?).
8. **`docker logs <ctr>` / `docker logs --since 5m <ctr>`** — the actual
   error. Restart-looping containers spam the same error per cycle.
9. **Docker Desktop UI** is **NEVER** the source of truth (§3.5). Don't
   even glance at it for verification.

---

## 2 · Operational primitives

The commands you reach for. Each pairs with a verify step.

### 2.1 Lifecycle (whole / subset / single)

```
./start.sh                       # whole fleet (staggered_up; §6a)
./start.sh <slug> [<slug>…]      # subset (staggered if > batch size)
./start.sh redis|waha|local-db|full  # +infra profile
./start.sh tunnel [slug]         # +cloudflare quick-tunnel
./stop.sh                        # graceful
./stop.sh volumes                # +remove named volumes
./stop.sh prune                  # full clean (images preserved)
```

### 2.2 Force-recreate (mandatory after compose runtime edits)

```
docker compose -f <file> up -d --force-recreate <svc> [<svc>…]
```

Plain `up -d` silently reuses stale containers when only mounts/volumes
changed (§3.6) — verify with `docker inspect … .Mounts` and recreate if
the expected mount is missing.

### 2.3 Build verify (did the fix actually land in the image?)

```
docker history --no-trunc --format '{{.Size}}\t{{.CreatedBy}}' <image>
docker run --rm --entrypoint sh <image> -- ls -la <expected-path>
docker inspect <image> --format 'id={{.Id}} created={{.Created}}'
```

### 2.4 Runtime verify (does the container actually have it?)

```
docker inspect <ctr> --format '{{range .Mounts}}{{.Type}} → {{.Destination}}{{println}}{{end}}'
docker exec <ctr> ls -la <expected-path>
docker inspect <ctr> --format 'image={{.Config.Image}} restarts={{.RestartCount}} status={{.State.Status}}'
docker logs --since 5m <ctr>
```

### 2.5 Disk diagnostics

```
docker system df -v                 # true sizes (shared vs unique)
noctus.dev.mole --scan              # repo hygiene (worktrees/artifacts)
docker builder prune -f             # unused cache only (safe regen)
docker image prune -f               # dangling tagged-image leftovers
```

**Never** `docker system prune -a` — nukes base images, costs hours to
rebuild. `docker rm -f <vol>` for stateful volumes only with explicit user
authorization (retired-product volumes are the safe-to-prune class).

### 2.6 Multi-arch check (before pinning platform)

```
docker manifest inspect <ref>                       # raw arch list
docker buildx imagetools inspect <ref>              # readable
```

Find a native arm64 tag (e.g., WAHA's `:arm`) before hard-pinning
`platform: linux/amd64` — emulation on Apple Silicon is slow and sometimes
fails (§3.4).

### 2.7 Build progress visibility

```
grep -oE '^#[0-9]+ ' /tmp/<build-log> | sort -un -k1.2 | tail   # step ceiling
tail -20 /tmp/<build-log>                                       # current step
pgrep -fl 'start.sh|compose.*build|buildx'                      # alive?
```

---

## 2a · `noctus.vps.*` — the MCP fleet-ops surface (operate over SSH)

The ad-hoc `ssh noctus-vps docker …` ops are consolidated into a tested,
confirm-gated MCP surface. **Three layers, one rule about where the SSH key
lives:**

| Layer | Tool(s) | Auth / where it runs |
|---|---|---|
| **Build / deliver** | `.github/workflows/build-and-push.yml` → GHCR | GitHub Actions, built-in `GITHUB_TOKEN` — **no SSH key in the cloud** |
| **Deploy** | `noctus.dev.deploy_pull` (git FF) · `noctus.dev.deploy_image` (image swap + C2 rollback) | **local** MCP runtime, SSH from your machine |
| **Operate** | `noctus.vps.*` (below) | **local** MCP runtime, SSH from your machine |

**🔒 The methodology rule: the production SSH key never enters CI.** CI only
builds+pushes images; everything that *touches the box* (deploy + operate) runs
from the local MCP runtime over SSH, so the key stays in `~/.ssh`. (Rejected: a
CI deploy job with the root key as a GitHub secret — too high a blast radius.
Future hardening: a dedicated unprivileged `deploy` user if CI-deploy is ever
wanted.)

**The surface** (`mcp/noctusai/tools/noctus/dev/vps.py`; default `ssh_host=noctus-vps`):
- **Read (free):** `ps` (name/image/status/health) · `health` (fleet rollup,
  `degraded` if any unhealthy) · `logs` (tail + grep) · `inspect`
  (image/state/health/port) · `images` · `disk` (root use% + `docker system df`)
  · `stats` (per-container CPU/mem).
- **Mutate (confirm-gated):** `restart` (stale single-file-mount fix / bounce) ·
  `recreate` (`compose up -d --force-recreate`) · `prune` (`image prune -f` —
  **dangling only**, never `-a`, so a tagged `:previous`/running image is never
  touched).

**Safe by construction:** each op emits a FIXED docker command; mutations are
confirm-gated; never `rm`/`rmi -a`/`kill`/`down`/`exec-arbitrary` (a colocated
test asserts no banned token). IO injectable (`run_remote`) for zero-SSH tests.
Reach for these instead of hand-typing `ssh noctus-vps docker …`.

## 3 · Known bumps (what to expect, what to do)

Eight learnings codified this session. Each row: **symptom · root · fix
· canonical KB pointer**.

### 3.1 Fleet cold-boot CPU livelock
- **Symptom:** all N products `unhealthy` after minutes, load ≫ cores, no progress.
- **Root:** N parallel first-boot `vite build`s oversubscribe CPU; uvicorn can't answer healthcheck within timeout.
- **Fix:** `staggered_up` in `start.sh` brings products up in core-sized health-gated waves. `NOCTUS_BOOT_BATCH`, `NOCTUS_BOOT_WAVE_TIMEOUT`. One-time tax; the watch loop keeps `dist/` warm.
- **Pointer:** `containerization.md § 6a` · `feedback_fleet_cold_boot_stagger`.

### 3.2 `chown -R` of an inherited base path
- **Symptom:** per-product `UNIQUE SIZE` ≈ 1 GB inflated; base layers not actually shared.
- **Root:** `RUN useradd … chown -R noctus:noctus /app /opt/venv` rewrites the 276 MB base venv into a NEW unshared 311 MB layer per product.
- **Fix:** chown ONLY product-owned paths (`/app`); never `chown -R` an inherited base path. `COPY --chown=` if non-root must own copied files.
- **Win measured:** ≈3.3 GB fleet.
- **Pointer:** `containerization.md § 12` · `feedback_docker_chown_inherited_base_antipattern`.

### 3.3 SPA boot race (local-watch.sh)
- **Symptom:** SPA `/` returns 404 even though `/api/health` is 200 and container is `healthy`.
- **Root:** `local-watch.sh` declared "dist before uvicorn" but the bg `vite --watch` initial pass briefly empties `dist/`; `exec uvicorn` raced into `serve_spa`'s startup-only check; SPA fail-soft for container's life.
- **Fix:** `local-watch.sh` blocks on `dist/index.html` stable (3 consecutive ticks) before uvicorn; bounded `LOCAL_WATCH_DIST_TIMEOUT` (proceed+⚠).
- **Deeper open:** `serve_spa` startup-only-resilience — request-time SPA-fallback would make it robust to ANY transient dist gap. Documented follow-up.

### 3.4 amd64-only image on Apple Silicon
- **Symptom:** Docker Desktop "AMD64 — may have poor performance, or fail, if run via emulation"; container slow/crash-looping.
- **Root:** `platform: linux/amd64` hard-pinned for an image with no native arm64 under the requested tag.
- **Fix:** env-driven `image: ${X_IMAGE:-…:latest}` / `platform: ${X_PLATFORM:-linux/amd64}` in compose + `start.sh` `uname -m` detection exporting native-arm64 image+platform on arm64 hosts. amd64 defaults preserved for CI/x86 servers.
- **Example:** WAHA `:arm` tag (WEBJS/Chrome arm64) / `:noweb-arm` (lighter).
- **Pointer:** `containerization.md § 8` row · `feedback_amd64_only_image_arch_aware`.

### 3.5 Docker Desktop is NOT the source of truth
- **Symptom:** DD Containers panel shows fewer products than are running; "fix is gone."
- **Root:** DD UI does not reliably live-refresh compose-project membership; also a group only renders once ≥1 of its containers exists *and* DD has polled.
- **Fix:** ALWAYS verify with `docker ps -a --filter label=com.docker.compose.project=…`. Treat DD as a lagging cache, never as ground truth.
- **Recurrence:** ≥5×. Don't re-diagnose; check `docker ps`.
- **Pointer:** `containerization.md § 8` row · `feedback_docker_desktop_not_source_of_truth`.

### 3.6 Compose volume edit + `up -d` (silent stale-container reuse)
- **Symptom:** edited compose volumes, ran `up -d`, fix appears not applied; container behaves like before.
- **Root:** `docker compose up -d` change-detection misses some compose-runtime edits (anon-volume additions, mount-list reorder). Image is new but mount-set is stale.
- **Fix:** `docker compose -f <file> up -d --force-recreate <svc>` after ANY compose volume/mount edit. Verify: `docker inspect … .Mounts` shows the added mount.
- **Compounds viciously** when the fix touches BOTH the Dockerfile (auto-recreates) and compose volumes (doesn't): new image + old mounts = original bug appears to recur.
- **Pointer:** `containerization.md § 8` row · `feedback_compose_volume_edit_requires_force_recreate`.

### 3.7 Base-image invalidation cascade
- **Symptom:** A small `seed/lib/*` change → next `./start.sh` rebuilds base + 9 product layers from scratch (~tens of minutes cold).
- **Root:** `COPY seed/lib/backend` etc. in `Dockerfile.backend-base` busts on any `seed/` content change; cascades to product layers FROM it.
- **Fix:** one-time tax (cache warms after); never `docker builder prune -a` between iterations of a seed change you're testing. Use the cache.
- **Open project:** `frontend-deps-base-consolidation` partly addresses by lifting common deps into the base (one place to invalidate, not 9).

### 3.8 Per-product pip vs base venv version drift
- **Symptom:** Heavy products' `pip install` step takes ~50 min cold (pip uninstall→reinstall→source-recompile).
- **Root:** Product `requirements.txt` pins different versions than the base venv ships → pip resolver backtracks + recompiles natives (pycairo/xhtml2pdf).
- **Fix:** **subset builds** for the products you actually need (`./start.sh <slug>`); the full-fleet cold build is multi-hour because of compounding. Real root fix is the backend-deps consolidation (sibling of frontend-deps-base-consolidation).
- **Open project:** `frontend-deps-base-consolidation` (backend-deps sibling Phase TBD).

### 3.9 The clean-checkout reproducibility defect
- **Symptom:** "It works on my machine" but fails in CI / fresh clone / `git worktree`.
- **Root:** Long-lived primary tree carries host-populated `node_modules` (especially `seed/framework/frontend/node_modules`) that get bind-mounted in and silently mask missing image-side installs. A clean checkout has none → bind-mount of an empty dir → mod resolution fails.
- **Fix:** install deps **in the image** at all paths the container needs them; pair with anon volumes on those nested paths so the bind-mount doesn't re-mask. Always **validate in a `git worktree`**, not the primary.
- **Generalization:** the §9a rule (one worktree per concurrent agent) IS the structural prevention — primary tree's stray state cannot mask defects when builds happen in isolated worktrees.

### 3.10 Glibc `runtime-watch` ≠ alpine `frontend-build`
- **Symptom:** alpine build stage works (produces `dist/`), but in-container `local-watch.sh` `vite build` fails on the same import.
- **Root:** Two node_modules environments per product container. Alpine `frontend-build` uses `noctus-seed-frontend-base` (which installs seed FE deps). Glibc `runtime-watch` is `FROM` the *backend* base (no seed FE node_modules); alpine modules aren't ABI-portable. The seed deps must be installed AGAIN in glibc.
- **Fix:** `runtime-watch` Dockerfile stage `COPY` + `npm install` the seed framework/lib FE `package*.json` in glibc; compose anon-volumes preserve those nested node_modules under the `../../seed` bind-mount.
- **Pointer:** `containerization.md § 3.2b` (extended seed-side, 2026-05-19) · `frontend-deps-base-consolidation` Phase 2.

### 3.11 JS native binaries + host lockfile pinning
- **Symptom:** `Cannot find module '@rollup/rollup-linux-*'` / `vite: not found`.
- **Root:** darwin-generated `package-lock.json` pins darwin-only optionals; npm honors it on linux and skips the linux native.
- **Fix (canonical):** `rm -f package-lock.json` immediately before each `npm install` in the Dockerfile (×2 — frontend-build + runtime-watch stages).
- **Pointer:** `containerization.md § 3.2b`.

### 3.12 Source-only Python deps in slim runtime
- **Symptom:** `meson … Unknown compiler` during product `pip install`.
- **Root:** Product dep with no prebuilt wheel for the arch (e.g., arm64 pycairo) falls back to source build; the slim runtime stage has no compiler (boundary §3.2a).
- **Fix:** per-slug `PIP_RUN` seam in `propagate-dockerfiles.sh` (N=1 affordance) wraps the product pip with apt-install-toolchain + pip-install + apt-purge in one layer. N≥2 → lift toolchain to the base builder.
- **Keeper detector:** `check_product_source_build_dep_pip_seam` flags products with source-only deps lacking the seam.
- **Pointer:** `containerization.md § 3.2a`.

### 3.13 Quick-tunnels QUIC dropout
- **Symptom:** cloudflared quick-tunnel works, dies in ~5-10 min behind a home/office NAT (`timeout: no recent network activity`); the URL DNS goes NXDOMAIN forever while the container stays "Up."
- **Root:** cloudflared's default `--protocol auto` opens QUIC/UDP; NATs kill UDP sessions; cloudflared can't re-register the same hostname.
- **Fix (canonical, mandatory):** `--protocol http2` pin in every `<slug>-tunnel` compose. `start.sh` curl-verifies at boot.
- **Pointer:** `containerization.md § 5b` · `feedback_tunnel_protocol_http2`.

### 3.14 Pre-commit hook absorbing concurrent edits (FIXED)
- **Symptom:** Your commit contains files you didn't author — concurrent agent's edits got swept in.
- **Root:** Hook's `git diff --name-only` + `xargs git add` blanket-staged every modified KB doc, not only ones you'd staged. In a shared tree, swept foreign edits.
- **Fix:** hook now restages docs ONLY if they're already in this commit; loudly SKIPs the rest (never silent).
- **Pointer:** `scripts/hooks/pre-commit` (the fix is in code).

### 3.15 MCP propagate fixed-CWD hazard
- **Symptom:** Ran `noctus.dev.propagate` from a worktree; it operated on the **primary** tree instead.
- **Root:** `mcp/noctusai/settings.py` `REPO_ROOT = get_noctusai_home()` resolves to a fixed path (primary), not the caller's `cwd`.
- **Fix:** `--worktree-path <path>` flag explicitly targets the worktree. Generalizable to other MCP write tools that touch the FS.
- **Pointer:** `feedback_mcp_write_tools_resolve_caller_root`.

### 3.16 §9a — concurrent agents NEVER share one checkout
- **Symptom:** "My commits disappeared" / "the build is using OLD code" / 2 days of compounding chaos.
- **Root:** Two+ agents shared the primary checkout; one ran `git switch` → yanked branch under a peer.
- **Fix:** each concurrently-active agent in its **own `git worktree`**; the primary tree's branch is owned by one driver. Reflog = truth; commits never lost; recover by switch-back / cherry-pick.
- **Pointer:** `branching-and-merging.md § 9a` · `feedback_concurrent_agents_never_share_checkout`.

### 3.17 Transient `ECONNRESET` aborts a 50-min npm install
- **Symptom:** Multi-product `docker compose build` dies at ~80 min with `npm error code ECONNRESET ... network request to https://registry.npmjs.org/<pkg>.tgz failed`; image never tagged; entire build wasted.
- **Root:** A single dropped TLS connection on one tarball fetch (~5% of long installs); npm's default `--fetch-retries=2` exhausts on transient registry blips, especially with multiple parallel product builds competing for network.
- **Fix:** add an `ARG NPM_RETRY="--fetch-retries=5 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000 --fetch-timeout=300000"` to the canonical `runtime-watch` Dockerfile and append it to every `npm install` call there. Cache mount (`--mount=type=cache,target=/root/.npm`) amortizes after the first successful pass, so this only stings the cold build.
- **Validated:** Phase 2 seed pilot built in ~26 min after retry args added (was failing at ~85 min before).
- **Pointer:** `containerization.md § 3.2b` (extended) · canonical `products/seed/backend/Dockerfile` `runtime-watch` block.

### 3.18 Parallel-engineer dispatch slip — architect's sibling worktree IS shared (§9a.1)
- **Symptom:** Engineer A's commit absorbs files from engineer B's parallel scope; scope check "printed leak" but commit ran anyway.
- **Root:** Even when each parallel `Agent isolation:"worktree"` engineer gets its own harness worktree, their writes manifest in the **architect's sibling worktree + index** under the patch-return model. Combined with a non-blocking print-only scope check (`grep ... && echo leak || echo clean` exits 0 either way), the architect's `git commit` absorbs the leaked files.
- **Fix:** **SERIALIZE engineer dispatches** even when scopes are file-disjoint — wait for engineer N's patch-return before dispatching N+1. **`git add` MUST be preceded by a BLOCKING scope check** (`if … ; then exit 1; fi`), never printing. **Engineer briefs say "WRITE PATCH FILE EARLY"** so the harness-watchdog kill doesn't lose the deliverable.
- **Recovery from slip:** never force-push; amend the *next* commit to carry only the missing portion (fix-on-contact at commit boundary).
- **Pointer:** `branching-and-merging.md § 9a.1` · `feedback_concurrent_agents_never_share_checkout` (refinement) · `feedback_scope_check_must_block_not_print` · `feedback_engineer_brief_patch_file_first`.

---

## 4 · Diagnostic flowchart — "container doesn't work"

Walk in order; do **not** skip steps (skipping is what caused most of the 2-day-chaos misdiagnoses).

```
┌─ A. Is the build still running?
│    pgrep -fl 'start.sh|compose.*build|buildx'
│    → yes: wait or kill; → no: image is final.
│
├─ B. Is the image NEW (has your fix)?
│    docker history --no-trunc <ref> | grep <expected RUN line>
│    docker run --rm --entrypoint sh <ref> -- ls <expected path>
│    → fix missing: build didn't use your Dockerfile (killed mid-build?
│      stale cache? wrong context? worktree-path missed?). Rebuild
│      cleanly: `docker compose build --no-cache <svc>`.
│
├─ C. Is the container running the NEW image?
│    img_id_in_ctr=$(docker inspect -f '{{.Image}}' noctus-<slug>)
│    img_id_of_tag=$(docker inspect -f '{{.Id}}' <ref>)
│    → mismatch: container stale — `--force-recreate`.
│
├─ D. Does the container have the EXPECTED mount set?
│    docker inspect <ctr> --format '{{range .Mounts}}{{.Destination}}{{println}}{{end}}'
│    → missing mount: compose edit not picked up — `--force-recreate`
│      (§3.6, the silent stale-container-reuse trap).
│
├─ E. Does the runtime FS have the expected files?
│    docker exec <ctr> ls <expected path>
│    → missing: anon volume failed to seed; or bind-mount masked; or
│      image install didn't reach this path. Trace upward: was it in
│      the image (step B)? did the anon volume mount (step D)?
│
├─ F. What's the actual error?
│    docker logs --since 5m <ctr>
│    Read it. Don't guess.
│
└─ G. Healthy required X but container Y?
     - Healthcheck endpoint not ready: check `start_period`/`interval`/`retries` in compose
     - CPU-starved: `uptime` load avg ≫ cores → §3.1 (use staggered_up; reduce subset)
     - Memory: `docker stats --no-stream` — OOM kills appear in logs
```

---

## 5 · Methodology for safe container changes

Disciplined sequence (cuts re-work by an order of magnitude vs ad-hoc):

1. **Edit canonical only** — `products/seed/backend/Dockerfile` /
   `products/seed/docker-compose.yml` / `seed/docker/Dockerfile.*-base`.
   Never per-product files (clobbered by propagate).
2. **Propagate** — `noctus.dev.propagate` (from a worktree: `--worktree-path
   <wt>` mandatory — §3.15).
3. **Verify sync** — `--propagate --check` returns `status: in-sync` for all 9.
4. **Build pilot products first** — seed + core + social-wiring is the
   standing pilot set; never start with all-9 cold.
5. **Force-recreate** containers for any compose-runtime change (§3.6).
6. **Verify runtime** — walk §4 A-G; don't claim success on healthcheck
   alone (the SPA-race lesson §3.3).
7. **Validate in a worktree**, not the primary (§3.9 — primary tree may
   carry stray state masking defects).
8. **Three-way sync** — every codified rule lands in KB + CLAUDE.md
   (or topical) + memory + MEMORY.md the **same session**.

---

## 6 · The meta-methodology — every bump follows the same arc

This session's bumps all matched a single pattern:

1. **Symptom** seemed local / superficial.
2. **First-pass fix** addressed the symptom — *appeared* to work.
3. **Deeper investigation** (forced by recurrence or by §9a worktree
   validation) revealed a structural root.
4. **Root fix** landed canonically + propagated.
5. **Three-way sync** codified the lesson.

The corollary: **a "quick fix" at the symptom layer almost always misses
the root and recurs.** When in doubt, walk §1 (source-of-truth chain) and
§4 (diagnostic flowchart); the deeper layer almost always has the answer.

---

## 7 · References (depth)

- **Architecture (sibling):** `containerization.md`
- **Branching for concurrent agents:** `branching-and-merging.md § 9a`
- **Active projects:**
  - `projects/frontend-deps-base-consolidation/PROJECT.md` (build-perf root)
  - `projects/remaining-five-fleet-mount/PROJECT.md` (5 of 9 products near-future)
- **Tooling:**
  - `start.sh` `staggered_up()` (cold-boot CPU contention)
  - `seed/docker/local-watch.sh` (SPA boot race)
  - `scripts/hooks/pre-commit` (the fixed restage-scope)
  - `mcp/noctusai/tools/noctus/dev/propagate.py` (`--worktree-path`)
