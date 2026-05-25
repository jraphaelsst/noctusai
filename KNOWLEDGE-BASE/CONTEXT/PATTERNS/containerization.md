# Containerization — single container per product

> **What this is.** How every product becomes ONE portable container,
> how the fleet wires together, and how to operate it. Built around a
> shared seed base image + thin per-product Dockerfiles + two compose
> projects on an external shared network.
>
> **Why native still exists.** `./start.sh native` (uvicorn + vite on
> the host) is the legacy hot-reload path. The container path is the
> reproducible/deployable twin. They coexist.

---

## 1 · Mental model

A **fleet of single-container siblings on a shared network**, split
into **two compose projects**:

```
┌───────────── noctus-net (external shared fabric) ──────────────┐
│                                                                 │
│  project noctusai-products                                      │
│   ┌─core──┐ ┌─erp───┐ ┌─pf────┐ ┌─… one container per product ┐ │
│   │ :8000 │ │ :8001 │ │ :8002 │ │  uvicorn serves API + SPA   │ │
│   └───────┘ └───────┘ └───────┘ └─────────────────────────────┘ │
│   (+ profile-gated <slug>-tunnel per product)                   │
│                                                                 │
│  project noctusai-infra  (profile-gated)                        │
│   ┌─redis─┐ ┌─waha──┐ ┌─postgres─┐                              │
│   └───────┘ └───────┘ └──────────┘                              │
└─────────────────────────────────────────────────────────────────┘
```

**One container per product.** uvicorn serves the API **and** the built
SPA on a single port — the seed factory's `serve_spa` / `SERVE_SPA_DIR`
seam mounts the bundle after all API routes (`/api/*`, `/_health`,
`/_ready`, `/docs` keep priority; unknown extension-less path → SPA
`index.html`; unknown asset → real 404). No nginx, no separate frontend
container, no per-product private network.

**`FROM noctus-seed-*-base` IS the seam.** The Docker analog of
`create_product_app()`: common heavy layers live once in shared base
images; each product's Dockerfile is ~70 lines that inherit and add
only its specifics. Inherit-and-extend, never fork — same rule as the
rest of the seed.

**Container-first — develop INSIDE the container, not on the host (§1a).** The default loop is `./start.sh` → edit → see it live in the container. There is no separate dev environment: the SAME image has two build targets — `runtime-watch` (local: source bind-mounted, `vite build --watch` + `uvicorn --reload`) and the slim `runtime` (deploy: baked dist, node absent). You **develop in the `runtime-watch` shape and ship the `runtime` shape** — ONE container, ONE shape. *Why* not containerize-last: "works on my host" `≠` "works in the slim image" (structurally different — no `start.sh`/registry/node, baked dist, env-only config); containerize-last is the exact anti-pattern behind the platform's #1 drift class ([[dev-prod-parity]], N≥3: `infra.tsx`-localhost · CORS-empty-in-slim). Developing in the container shape surfaces a parity bug at **dev time**, not after a cutover — and the bind-mount + watch trick means **no** iteration tax (host-speed editing `∧` container-shape fidelity, not a choice). The **DB is NOT in the container** (managed Supabase, external; the container gets `SUPABASE_URL`/keys as env). **Applies at product BIRTH**: `scaffold_product` copies the canonical `products/seed/` template by construction; an **absorption** refactors the incoming product to the house model at its container gate (§12a; `KB § GUIDES/absorb-seed-workspace.md` Gate 9) BEFORE further development continues. Enforced by the **`check_product_container_shape`** keeper (an in-noc product missing the house Dockerfile/compose — freshly-absorbed-but-uncontainerized, or hand-edit drift — is flagged). → `KB § PATTERNS/dev-prod-parity.md`

**Two projects = the Docker-Desktop UX.** `name: noctusai-products`
groups every product under one collapsible header (project-level switch
= whole fleet); each product is a single container = one row toggled in
one click. `noctusai-infra` is a separate group toggled independently.

**`noctus-net` is `external: true`.** The two-project split means no
single compose project may own the shared fabric, so it is created once
(by `start.sh`, or `docker network create noctus-net`). This **inverts**
the older "NOT external:true" rule that applied to the single-root design.

---

## 2 · File layout

```
noctusai/
├── docker-compose.yml          ← name: noctusai-products; include:s 10 products
├── docker-compose.infra.yml    ← name: noctusai-infra; redis/waha/postgres
├── .dockerignore               ← excludes venv, node_modules, .env, .git, dist…
├── start.sh / stop.sh          ← Docker-default; `native` legacy preserved
│
├── seed/
│   ├── lib/backend             ← noctusai_lib (editable into the backend base)
│   ├── lib/frontend            ← @noctusai/lib (Vite alias target)
│   ├── framework/backend       ← noctusai_seed (factory + serve_spa seam)
│   ├── framework/frontend      ← @noctusai/seed (Vite alias target)
│   └── docker/
│       ├── Dockerfile.backend-base   ← noctus-seed-backend-base (shared)
│       ├── Dockerfile.frontend-base  ← noctus-seed-frontend-base (shared)
│       └── local-watch.sh            ← runtime-watch entrypoint (build --watch + --reload)
│
├── scripts/
│   ├── build-base-images.sh    ← builds the two seed base images (start.sh runs it)
│   ├── propagate-dockerfiles.sh ← seed → 10 thin product Dockerfiles (--check)
│   └── propagate-composes.sh    ← seed → 10 product composes (--check)
│
└── products/
    ├── seed/                   ← CANONICAL (edit here, then propagate)
    │   ├── backend/Dockerfile  ← thin: FROM noctus-seed-*-base + serve_spa
    │   └── docker-compose.yml  ← single `seed` service + seed-tunnel
    ├── core/             (8000)   erp-imobiliario/ (8001)
    ├── personal-finance/ (8002)   therapy-platform/(8003)
    ├── seed/             (8004)   daily-life/      (8005)
    ├── mailing/          (8006)   adconnect/       (8007)
    ├── youtube-crawler/  (8008)   dev-team/        (8009, + /opt/dev_team)
    └── imobi-scheduling/ (8011)
```

**`products/seed/` is canonical.** Pattern change → edit the seed
Dockerfile/compose → `bash scripts/propagate-{dockerfiles,composes}.sh`
→ 10 products regenerate. The pre-commit hook's `--check` blocks drift.

---

## 3 · The image pattern

### 3.1 — Shared seed base images

`seed/docker/Dockerfile.backend-base` → **`noctus-seed-backend-base`**:
`python:3.11-slim` + system libs (cairo/pango/libffi/libpq…) + an
isolated `/opt/venv` with `noctusai_lib` + `noctusai_seed`
editable-installed + `/app/seed` (the egg-link source). Runtime-shaped
(no build-essential/headers in the final stage).

`seed/docker/Dockerfile.frontend-base` → **`noctus-seed-frontend-base`**:
`node:20-alpine` with the seed Vite alias targets
(`seed/framework/frontend`, `seed/lib/frontend`) and their deps
installed.

Built once by `scripts/infra/build-base-images.sh` (start.sh runs it before
any product build — the heavy layers cache once, not per product).

### 3.2 — Per-product thin Dockerfile (two targets)

~70 lines, generated from `products/seed/backend/Dockerfile`:

```dockerfile
FROM noctus-seed-frontend-base:dev AS frontend-build
ENV VITE_SAME_ORIGIN=1                       # → window.location.origin
ARG VITE_CORE_URL=                           # per-product VITE_* block
COPY products/<slug>/frontend ...; RUN npm run build   # → dist/

FROM noctus-seed-backend-base:dev AS runtime          # ← SHIPPABLE image
COPY products/<slug>/backend/requirements.txt ...; pip install
COPY products/<slug>/backend/ ...; COPY --from=frontend-build dist
ENV SERVE_SPA_DIR=/app/products/<slug>/frontend/dist
USER noctus
CMD uvicorn app.main:app --port <bp> --app-dir products/<slug>/backend

FROM runtime AS runtime-watch                 # ← LOCAL only
# + nodejs + product frontend deps + ENTRYPOINT seed/docker/local-watch.sh
```

- **`runtime`** — slim, node absent, baked `dist`. Plain uvicorn over
  the built bundle. **This is the artifact CI/deploy build and run.**
- **`runtime-watch`** — `FROM runtime` + node + `local-watch.sh`
  (`vite build --watch` + `uvicorn --reload`). **This is what the local
  compose builds**, with source bind-mounted.

There is **no dev/prod *mode* and no `dev` command**. The user always
runs `./start.sh`; the local compose builds `runtime-watch` so editing
code reflects (a few-second rebuild + refresh / uvicorn reload) in the
*same single container*. Deploy/CI build the default `runtime`. The
split is a build target chosen by tooling, never by the operator.

Per-product variance lives only here, kept tiny: the `VITE_*` ARG block,
the port, and product extras (dev-team's `/opt/dev_team` via the
`{{BACKEND_EXTRA}}` splice seam in the propagation script).

### 3.2a — Source-only Python deps & the slim-runtime no-compiler boundary

**The boundary (intentional, not a bug).** `seed/docker/Dockerfile.backend-base`
is two-stage: the **`builder`** stage ships the full toolchain
(`build-essential` + `pkg-config` + `libcairo2-dev`/`libgirepository1.0-dev`/
`libpango1.0-dev`/… dev headers) and bakes the *seed* venv there; the
**`runtime`** stage is deliberately slim — runtime libs only, **no compiler,
no `-dev` headers**. Product thin Dockerfiles `FROM …-base AS runtime` and run
their per-product `pip install -r requirements.txt` **in that slim runtime**.
So: any product dep (direct or transitive) with **no prebuilt wheel for the
build arch** falls back to a source build and **fails — `meson … Unknown
compiler`** — because the slim runtime has no `cc`. This is the price of a
slim shippable image; it is expected, and it has a single sanctioned escape.

**The sanctioned mechanism (use this; do NOT hand-edit a generated
Dockerfile).** Product Dockerfiles are generated by
`noctus.dev.propagate` from `products/seed/backend/Dockerfile`; a
hand-edit is clobbered next propagate **and** fails the `--check` pre-commit
gate. Source-only deps are handled through the **per-slug `PIP_RUN` seam** in
that script (same shape as the `VITE` / `DEVTEAM_EXTRA` seams): the slug's
entry wraps the pip step with `apt-get install <toolchain+headers> && pip
install && apt-get purge … && autoremove && rm -rf /var/lib/apt/lists/*` — the
toolchain is installed **and purged in the same layer**, so the shipped image
stays slim. Default (no entry) = the canonical all-wheel pip step.

**Escalation by recurrence (the DRY rule applied to build toolchain).**
- **N=1** — one product needs a source build → a `PIP_RUN` per-slug entry
  (current: `erp-imobiliario`, for `xhtml2pdf → svglib → rlpycairo → pycairo`;
  pycairo has no arm64 wheel). Justified per-product, documented in the script.
- **N≥2** — a second product needs a source build → STOP repeating the seam;
  **lift the toolchain into the seed base `builder` stage** and shift product
  pip-installs to a builder-equipped stage with a venv copy into runtime. The
  per-slug seam is the N=1 affordance, not the steady state.

**Newly-scaffolded products inherit the slim default by construction** — they
get the canonical (no-toolchain) pip step. This is correct: ~all deps are
wheels. The methodology guarantee is **not** "it can never happen again" — it
is "when it does, there is exactly one documented place to handle it (the
`PIP_RUN` seam), one documented escalation (N≥2 → base builder), and an
automated check that refuses to let it slip silently."

**Enforcement (Stage-4 codification — the extra checking layer).** The keeper
detector `check_product_source_build_dep_pip_seam`
(`mcp/noctusai/tools/noctus/dev/compliance.py`, in `check_all_products()` +
colocated `TestCheckProductSourceBuildDepPipSeam`) deterministically flags
**`high`**: any product whose `backend/requirements.txt` pulls a curated
source-only (no-arm64-wheel) root (`_SOURCE_BUILD_DEP_ROOTS` — currently
`xhtml2pdf`, `pycairo`) **without** a per-slug `PIP_RUN` entry for its slug in
`propagate-dockerfiles.sh`. Green at introduction (erp has the seam; no other
product carries such a root) → it never *adds* debt, it *guards* the boundary:
a future product adding such a dep — or erp's seam being removed — turns the
fleet-build abort into a fast static `check_all_products()` failure with the
§3.2a remediation in the message. Grow `_SOURCE_BUILD_DEP_ROOTS` as new
no-wheel roots are discovered (same curated-set model as the slug-set / fleet-
size keepers).

### 3.2b — Frontend native-binary platform mismatch & the bind-mount node_modules shadow

**Two failure modes, one root: a darwin/host artifact reaching the linux container.**

1. **Lockfile pins host-platform optionals.** `npm install` honours a
   checked-in `package-lock.json` — generated on the dev's `darwin-arm64`, so
   it pins the *platform-optional* native binaries (`@rollup/rollup-*`,
   `esbuild`, `lightningcss`, `@swc/*`) to that os/cpu and **skips** the linux
   build (npm/cli#4828) → `vite build` dies with `Cannot find module
   '@rollup/rollup-linux-*'`. **Fix (canonical, propagated):** `rm -f
   package-lock.json` immediately before each `npm install` in
   `products/seed/backend/Dockerfile` (**×2** — `frontend-build` *and*
   `runtime-watch`); npm then re-resolves optionals for the build platform.
2. **Bind-mount shadows the image node_modules.** The local compose
   bind-mounts `./frontend → /app/products/<slug>/frontend` for live-edit;
   that host dir carries darwin (or absent) `node_modules` which **masks** the
   image's linux `node_modules` → `vite: not found` / wrong-platform rollup.
   **Fix (canonical, propagated):** an **anonymous volume at the nested path**
   `- /app/products/<slug>/frontend/node_modules` listed **after** the
   `./frontend` bind-mount in `products/seed/docker-compose.yml`; Docker seeds
   it from the image layer on first create — source stays live-editable, the
   container keeps its own platform-correct `node_modules`.

Both fixes live ONLY in canonical `products/seed/` and reach the fleet via
`propagate-{dockerfiles,composes}.sh` (`--check` pre-commit gate);
newly-scaffolded products inherit both by construction. Same guarantee shape
as §3.2a — not "can't happen" but "one canonical place, propagated,
drift-gated". Sibling boundary: §3.2a = Python source deps in the slim
runtime; §3.2b = JS native binaries across the host↔linux bind-mount.

### 3.3 — Per-product `docker-compose.yml`

```yaml
services:
  <slug>:
    build:
      context: ../..
      dockerfile: products/<slug>/backend/Dockerfile
      target: runtime-watch                  # local live-rebuild
      args: { VITE_CORE_URL: ${VITE_CORE_URL:-} }
    container_name: noctus-<slug>
    image: ghcr.io/jraphaelsst/noctus-<slug>:${NOCTUS_IMAGE_TAG:-dev}
    env_file: [../../.env]
    volumes:                                  # source live → edits reflect
      - ./backend:/app/products/<slug>/backend
      - ./frontend:/app/products/<slug>/frontend
      - ../../seed:/app/seed
    ports: ["<bp>:<bp>"]
    networks: [noctus-net]
    healthcheck: { test: curl -fsS http://localhost:<bp>/api/health, ... }

  <slug>-tunnel:                              # MANDATORY in pattern, profile-gated
    image: cloudflare/cloudflared:latest
    command: tunnel --no-autoupdate --protocol http2 --url http://<slug>:<bp>
    profiles: [tunnel-<slug>, tunnel-all]

networks:
  noctus-net: { name: noctus-net, external: true }
```

`<slug>-tunnel` is **always wired** (part of the standardized pattern)
but **profile-gated** — runs only when asked. Deploy builds the slim
`runtime` target via `docker-compose.prod.yml` (image-only, no volumes).

### 3.4 — Root `docker-compose.yml` + `docker-compose.infra.yml`

`docker-compose.yml` is `name: noctusai-products` and `include:`s the 10
per-product composes (one line each, between the
`BEGIN/END_PRODUCTS_INCLUDE` sentinels — scaffolder-managed). It does
**not** path-list anything else; one product = one container = one
Docker-Desktop row.

`docker-compose.infra.yml` is `name: noctusai-infra` and carries
`redis` / `waha` / `postgres` under profiles (`redis` / `waha` /
`postgres` / `full`) + the named volumes. Both files reference the
external `noctus-net`.

---

## 4 · Networks

| Network | Members | Purpose |
|---|---|---|
| `noctus-net` (external) | all product containers + infra (when on) | cross-product calls + shared infra |

There is no `<slug>-net` — a single container has nothing to isolate
frontend-from-backend (it's in-process). Threat model: the host gets
only published ports; a compromised backend can reach siblings only at
application-layer endpoints with the same auth they'd face externally;
infra is on the shared fabric for backends that opt into it.

`noctus-net` must exist before any `up`. `start.sh` ensures it
(`docker network inspect … || docker network create noctus-net`).
Standalone / CI without start.sh: create it once by hand.

---

## 5 · Operating it — start.sh / stop.sh

Docker is the default. One script, no `dev` mode.

```bash
./start.sh                  # whole fleet (one container per product)
./start.sh erp-imobiliario  # ONLY that product (subset; compose `up <svc>`)
./start.sh core erp         # those two
./start.sh redis            # fleet + Redis (noctusai-infra)
./start.sh waha             # fleet + WAHA
./start.sh local-db         # fleet + local Postgres (offline dev — §8a)
./start.sh full             # fleet + Redis + WAHA + Postgres
./start.sh tunnel <slug>    # fleet + cloudflare tunnel for one product
./start.sh tunnel           # fleet + tunnels for ALL products
./start.sh build            # rebuild (bases --no-cache + product images) then up
./start.sh native           # legacy: uvicorn + vite on the host (hot-reload)

./stop.sh                   # down noctusai-products + noctusai-infra + standalone
./stop.sh volumes           # + remove named volumes
./stop.sh prune             # + remove images (full clean)
./stop.sh native [--venv|--node|--all]
# legacy aliases: --docker / --docker-volumes / --docker-prune
```

Every local product container builds `runtime-watch` with source
bind-mounted, so `./start.sh <anything>` already gives live feedback —
no separate command. `start.sh` calls `build_bases` before product
builds; `stop.sh` preserves the external network + the base images.
Both read the single `PRODUCTS` registry block in `start.sh`.

### 5.1 · Ephemeral-by-design — non-loss guarantee & recovery

**Containers are disposable build *outputs*, never source.** A Docker
Desktop app update, a VM restart, `stop.sh`, or `docker compose down`
removes *running containers* — this is **expected, not data loss**.
Images + named volumes survive an app update (they live in the Docker VM
disk, persisted across app upgrades). An empty Docker-Desktop *Containers*
view is the normal resting state when the stack is down, **not** an alarm.

**The reproducibility guarantee (this is `codebase-is-source-of-truth`
applied to Docker artifacts):** every product's `Dockerfile` +
`docker-compose.yml` + the house-model `noctus-seed-{backend,frontend}-base`
definitions + `start.sh` `PRODUCTS` registry are **git-tracked and pushed**.
No local Docker image/cache is ever authoritative. Therefore *any* loss of
local Docker state — even `docker system prune -a` — costs **rebuild time
only, zero engineering**. Recovery is always one idempotent command:
`./start.sh` (whole fleet) or `./start.sh <slug>…` (subset). The shared
base images + the build cache make a "full" rebuild mostly cache hits; a
genuinely cold rebuild is `./start.sh build`.

**The only thing that could destroy reproducibility** is losing the
git-tracked build definitions — which are committed/pushed, so they can't
be. `mole`'s safety contract already refuses to delete uncommitted work
(it only reclaims regenerable cache/images/stale-worktrees). Residual risk
is therefore strictly *time*, never *work*. When a teammate sees "my
containers are gone," the answer is always: nothing was lost — `./start.sh`.

**Why Docker default.** Containers are the deploy artifact and the path
to online testing (tunnel); making them the script default removes the
mental tax of a flag. Native is preserved because single-file hot
iteration on a real interpreter is still the fastest inner loop.

---

## 5c · Sync runbook — getting fixes into running containers

The agent-facing runbook for "I (or someone) edited code; how do I make sure the running container actually serves it?" Authoritative procedure — every other doc points here.

### 5c.1 · Quick decision tree

```
Did the edit touch CODE that the running container serves?
├─ No (docs, KB, memory, .md, test fixtures): nothing to do; container is unchanged.
└─ Yes:
   ├─ Is the file inside a bind-mounted dir?  ──→ check `docker inspect <c>`
   │  ├─ Yes (under /app/seed or /app/products/<slug>/{backend,frontend}):
   │  │   ├─ Is it Python?       → uvicorn --reload picks it up (sub-second). Verify with `docker logs --tail 5 <c>` (look for "Detected file change").
   │  │   ├─ Is it FE source?    → vite --watch picks it up (~1–3s). Browser auto-reloads with same-origin define.
   │  │   └─ Is it the Dockerfile / package.json / requirements.txt?
   │  │       → bind-mount can't help (build-time). `docker compose up -d --build <slug>` from the canonical clone.
   │  └─ No (e.g. base image, /app/seed/lib/.../node_modules):
   │      → `docker compose up -d --build <slug>` from the canonical clone.
   └─ Is the bind-mount source the canonical clone?
      ├─ Yes: reload as above.
      └─ No: multi-clone drift → § 12b.1 procedure (also `up -d --build`, but from the right clone).
```

### 5c.2 · The four-step container-freshness probe — what every agent runs before saying "ready to test"

```bash
# 1. Bind-mount source: must be under the canonical clone.
docker inspect <container> --format '{{range .Mounts}}{{if eq .Type "bind"}}{{.Source}}{{println}}{{end}}{{end}}'

# 2. Watched directories: confirm uvicorn reloads on the dir you edited.
docker logs <container> 2>&1 | grep "Will watch"

# 3. Trigger reload. Source bind-mounted + watched → uvicorn auto-reloads on save.
#    Otherwise:
docker restart <container>                # bind mount + new process (fast, ~3s)
# OR
docker compose up -d --build <slug>       # image rebuild (slow, ~1–2 min; only when deps/Dockerfile changed)

# 4. Live-probe the endpoint that exercises the fix.
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:<port>/<path>
```

Tests green + build green ≠ runtime green when a container is in front. Step 4 is the only one that distinguishes them. → § 12b for the philosophy.

### 5c.3 · "I see drift across products" — the consolidation drill

Symptom: `docker inspect` shows containers bind-mounting a *sibling clone* (e.g. `noctus-fleet/seed` when you're editing in `noctusai/seed`). Cure per § 12b.1:

```bash
# Repeat per slug. The three commands are atomic (each rebuild flips
# all three bind mounts and rebakes the image from the canonical source).
docker compose stop <slug>
docker compose rm -f <slug>
docker compose up -d --build <slug>
```

For the fleet you can parallelize: fire one shell per product (docker daemon handles concurrent builds; ~1–2 min total wall-clock for the typical 4-product set, vs ~5–8 min sequential). On a Mac the daemon may serialize image-export at the end — expected.

**Sanity check after.** Run the audit yourself:

```bash
docker inspect $(docker ps -q --filter "name=noctus-") \
  --format '{{.Name}} {{range .Mounts}}{{if eq .Type "bind"}}{{.Source}} {{end}}{{end}}' \
  | sed 's|/host_mnt||g'
```

Every Source containing `/NoctusAI/` must be under the canonical clone path (your repo root). `start.sh` performs this check automatically on every Docker-mode invocation (§ 12b.1 *Structural guarantee*), but running it manually is the explicit confirmation.

### 5c.4 · "I shipped a fix mid-session" — keep-in-sync during active work

You committed a seed/product code change while a container is running. Two scenarios:

| Scenario | What auto-recovers | What you do |
|---|---|---|
| Edited `.py` under `/app/seed` or `/app/products/<slug>/backend` | uvicorn `--reload` detects + restarts the process | Wait ~2s. `docker logs --tail 10 <c>` shows the reload. Probe the endpoint. |
| Edited `.ts/.tsx/.css` under `/app/products/<slug>/frontend/src` | `vite --watch` rebuilds `dist/` | Wait ~3s. Hard-refresh the browser. |
| Edited `Dockerfile` / `requirements.txt` / `package.json` / non-bind-mounted file | Nothing — those are baked at build | `docker compose up -d --build <slug>` |
| Edited `start.sh` / `docker-compose.yml` / `seed/docker/*` | Nothing — these are read at process-start by docker itself | `docker compose up -d <slug>` (no `--build` needed unless you also changed an image input) |

**Heuristic.** If in doubt, `docker compose up -d --build <slug>` — slower (~1–2 min) but covers every case.

### 5c.5 · The structural guarantee

`start.sh` runs `audit_clone_alignment` before any `compose up`. If any running `noctus-*` container has a bind-mount Source outside `$ROOT_DIR` (the canonical clone), start.sh prints the offender list with per-slug remediation commands and exits 1. This catches: post-pull drift, sibling-clone drift, stale-container-from-other-checkout drift. **No docker entry point in this repo bypasses it.** Future products inherit start.sh automatically — the guarantee extends to anything we add.

To opt out (do not, except in a real bypass scenario): invoke `docker compose` directly, not through `start.sh`. You then own the audit yourself per 5c.2.

---

## 5b · Cloudflare tunnel — online testing without deploy

For a public URL pointing at a local product — OAuth callbacks
(Google/Meta/Stripe reject `localhost`), webhook receivers, sharing a
session:

```bash
./start.sh tunnel core      # → https://<rand>.trycloudflare.com (banner at end)
./start.sh tunnel           # every product, one URL each
```

Each product compose ships a profile-gated `<slug>-tunnel`
(`cloudflare/cloudflared:latest`, command pins **`--protocol http2`**).
`start.sh` activates the `tunnel-<slug>` / `tunnel-all` profile, polls
`docker logs noctus-<slug>-tunnel` for the `*.trycloudflare.com` URL,
**curl-verifies `/api/health` through it**, and prints it (a `⚠` means
registered-but-not-serving).

**The `--protocol http2` rule (non-negotiable).** cloudflared's default
`auto` opens QUIC/UDP; home/office/tethered NATs kill the UDP session in
~5–10 min (`timeout: no recent network activity`), and cloudflared
**cannot re-register the same quick-tunnel hostname** once dropped — DNS
goes NXDOMAIN forever while the container stays "Up" (a `FROM scratch`
image Docker can't healthcheck). HTTP2-over-TCP doesn't suffer this. All
product composes pin it; never remove the pin.

Quick-mode URLs are ephemeral (change on restart) — fine for OAuth /
webhook / demo. Promotion to a named tunnel (stable URL via
`TUNNEL_TOKEN` + a Cloudflare account/DNS) is a future option.

---

## 6 · Build process & footprint

`./start.sh` →
1. ensure external `noctus-net`;
2. `build_bases` (`noctus-seed-{backend,frontend}-base`; cached after
   first build);
3. compose builds each product image `FROM` the bases (only the changed
   layer rebuilds — product code is the last layer);
4. containers start; healthcheck (`/api/health`) gates `service_healthy`.

First base build is slow (apt + cairo/weasyprint + pip wheels +
seed npm). Subsequent product builds are fast (seconds — bases cached,
only product layers rebuild). One image per product (≈600–900 MB,
python-slim + deps + baked SPA) — 10 images, not 20. `./stop.sh prune`
reclaims everything (base images preserved unless removed by hand).

---

## 6a · Cold-boot CPU contention — the staggered wave boot

**The failure mode (observed 2026-05-19, the rule's provenance).** Bringing
the **whole fleet up from cold** (`./start.sh`, or `docker compose -f
docker-compose.yml up -d` with no service list) starts all product
containers simultaneously. Each one's `runtime-watch` entrypoint
(`seed/docker/local-watch.sh`) runs an **initial `vite build` before
uvicorn answers**. A solo product builds in ~20 s; **9 rollup builds in
parallel** on an 8-core machine drove load to **~18 (≈2.3× cores)**, every
build crawled, uvicorn never came up inside the healthcheck window, and
**all 9 containers flipped `unhealthy` though nothing had failed** — they
were CPU-starved, not broken. The image build is cached and fast (§6); this
is the *runtime* first-build, which §6's "subsequent builds are seconds"
explicitly does **not** cover.

**Why it's a one-time tax (not a per-use cost).** Once a product's `dist/`
is built, the bind-mounted `vite build --watch` keeps it warm across
stop/start. So the **normal single-click workflow — toggling one product
on/off in Docker Desktop — is unaffected**; only a from-cold all-at-once
boot pays it. The single-click switch is *designed* for per-product
toggling; whole-fleet cold boot is the edge case, but it must still be
non-pathological because `./start.sh` (no args) is a documented entry.

**The structural fix — `staggered_up()` in `start.sh`.** Both fleet and
multi-slug-subset boots route through `staggered_up()`: products come up in
**core-sized waves** (`batch = max(2, cores/2)`), and each wave is **gated
on the prior wave going `healthy`** before the next starts. `healthy` ⇒
uvicorn is answering ⇒ that product's `vite build` finished ⇒ its CPU is
freed for the next wave. Aggregate load stays ≈ cores instead of 2.3× over;
convergence is wave-serialized, not thrash-serialized. The gate has a
per-wave timeout (`NOCTUS_BOOT_WAVE_TIMEOUT`, default 300 s) after which it
**proceeds with a loud `⚠` line, never silently** — a slow build is not a
failure, and blocking the fleet forever on one slow product would be its
own anti-pattern. Wave size overridable via `NOCTUS_BOOT_BATCH`.

**Boundary.** This is an *operator-layer* boot-ordering concern, not an
image or compose concern — the Dockerfiles/composes are unchanged and stay
canonical+propagated (§3). Subsets at or below one wave (`≤ batch` slugs)
skip staggering entirely (`up -d` straight through) — the contention only
exists above a wave's worth of simultaneous cold builds.

## 7 · Adding a new product

`noctus.dev.scaffold_product` does it end-to-end:
1. copies `templates/product-seed/` (thin backend `Dockerfile` +
   single-service `docker-compose.yml`, placeholder-templated);
2. substitutes `{{PRODUCT_SLUG/NAME/BACKEND_PORT}}`;
3. `_register_in_start_sh` appends to the `PRODUCTS` registry
   (`BEGIN/END_PRODUCTS_REGISTRY`);
4. `_register_in_root_compose` appends the `include:` line
   (`BEGIN/END_PRODUCTS_INCLUDE`);
5. agent runs `docker compose -f docker-compose.yml config -q` as the
   post-scaffold smoke.

`noctus.dev.delete_product` is the symmetric inverse (roundtrip
byte-verified). The pre-commit hook syncs `products/seed/` →
`templates/product-seed/`, so the scaffolder template tracks the
canonical automatically — there is no separate frontend Dockerfile to
maintain.

---

## 8 · Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `network noctus-net not found` | external net not created — `docker network create noctus-net` (or just run `./start.sh`, it does it) |
| `Conflict. container name "/noctus-<slug>" in use` | same product up under another compose project — `docker rm -f noctus-<slug>` or `./stop.sh` first (one project owns a container name at a time) |
| Backend healthcheck never green | `/api/health` missing (seed wiring) — `docker logs noctus-<slug>`; confirm native first |
| SPA `/` 404s but `/api` works | `SERVE_SPA_DIR` unset or `dist/` missing — in `runtime-watch` the initial `vite build` must finish before uvicorn (handled by `local-watch.sh`); rebuild |
| Edits not reflecting | not on `runtime-watch` / source not bind-mounted — confirm the compose `target: runtime-watch` + `volumes:` are present; check `docker logs` for `vite build --watch` "watching for file changes…" |
| `Cannot find module '@noctusai/seed'` in frontend build | seed alias dirs missing from base — rebuild `noctus-seed-frontend-base` |
| `[vite] Rollup failed to resolve "<dep>"` from `seed/.../*.ts` | a seed source import isn't in the product's `package.json` (Vite `dedupe` forces product `node_modules`) — add it; audit via `python mcp/noctusai/cli.py --check-framework-deps [--fix]` |
| `meson … Unknown compiler` / `Dependency lookup for cairo … failed` (pip, in a *product* build) | A product dep has no wheel for the build arch → source build in the **slim runtime** stage, which has no compiler (the base *builder* stage has the toolchain, but product pip runs in *runtime*). Fix via the per-slug `PIP_RUN` seam in `propagate-dockerfiles.sh` — see §3.2a. N≥2 → lift to the base builder. |
| `Cannot find module '@rollup/rollup-linux-*'` / `vite: not found` (esp. in `runtime-watch`) | host `package-lock.json` pinned darwin optionals **or** the `./frontend` bind-mount shadowed the image `node_modules` — both fixed canonically (lockfile drop ×2 + anon `node_modules` volume), see §3.2b. If seen, the product drifted from seed — re-run `propagate-{dockerfiles,composes}.sh` |
| Edited compose volumes (added anon volumes / changed mounts), `up -d` reports "Started" but the container behaves exactly like before — fix appears not to work | `docker compose up -d` **change-detection misses some compose-runtime edits** (anon-volume additions, mount-list re-ordering) and silently reuses existing containers; the image is new but the *mount set* is stale. **Verify**: `docker inspect <ctr> --format '{{range .Mounts}}{{.Destination}} {{end}}'` — if the added mount isn't there, the container is stale. **Fix**: `docker compose -f <file> up -d --force-recreate <svc>`. Symptoms compound viciously when a fix touches *both* the Dockerfile (image-level — auto-recreates) *and* the compose volumes (config-level — does NOT auto-recreate): the image lands, the volume doesn't, the new image runs without the new mount set, the original bug appears to recur (cost the `frontend-deps-base-consolidation` Phase 1 a full extra rebuild cycle, 2026-05-19). **Default rule:** any compose volume/mount edit ⇒ `--force-recreate` of the affected services; never trust plain `up -d` to pick it up |
| Docker Desktop "Containers" shows fewer products than are actually up (e.g. 1 row under `noctusai-products` when 3+ ran) | **Docker Desktop is NOT the source of truth — `docker ps` is.** Two compounding causes: (1) during a *staggered* fleet boot (`staggered_up`, §6a) products come up in health-gated waves over many minutes — the missing ones genuinely don't exist *yet* (still building / not in a started wave); (2) the DD Containers view does **not** reliably live-refresh compose-project membership — it updates on its own poll, so even after containers exist the list can stay stale until you switch views/tabs or it re-polls. Always verify with `docker ps -a --filter label=com.docker.compose.project=noctusai-products` or `docker compose ls`; treat the DD list as a lagging cache, never as ground truth. A group only renders once ≥1 of its containers exists *and* DD has polled. Recurring gotcha (≥5 occurrences) — do not re-diagnose; check `docker ps` first |
| Docker Desktop unstable after an app update: `failed to solve: frontend grpc server closed unexpectedly`, `#N CANCELED`, `--force-recreate` not applied (config-hash unchanged), `up -d` hung at "Creating" with 0 containers | BuildKit/daemon wedge — *not* a compose/Dockerfile bug (`docker compose config` parses fine). Recovery: kill hung `docker`/`compose` procs → `pkill -x "Docker Desktop"; pkill -f com.docker.backend; open -a "Docker Desktop"` → wait for `docker info` ready → re-run `./start.sh`. **Safe**: fleet is ephemeral-by-design (§5.1) — containers regenerate, volumes + `noctus-net` persist, no data loss |
| Whole fleet boots `unhealthy` simultaneously from cold, load far exceeds cores, all stuck at `vite … transforming` | Not a failure — N parallel first-boot `vite build`s oversubscribe CPU (§6a). Fixed structurally: `./start.sh` routes through `staggered_up()` (core-sized waves, health-gated). If seen via raw `docker compose up -d` (bypasses start.sh), either use `./start.sh` or wait — builds complete, just slowly; it self-accelerates as each finishes |
| Container restart-loops `ModuleNotFoundError` | product imports a pkg only in root `requirements.txt` — declare it in the product's `requirements.txt` (each image installs only its own) |
| `exec: "uvicorn": not found` | product `requirements.txt` doesn't pin uvicorn — add `uvicorn[standard]==…` |
| Tunnel worked then `NXDOMAIN`, container "Up" | QUIC dropout — all composes pin `--protocol http2`; if seen, `docker compose --profile tunnel-<slug> up -d --force-recreate <slug>-tunnel` for a fresh URL |
| First build flaky (`failed to fetch oauth token`) | tethered/captive net — pre-pull bases when stable: `docker pull python:3.11-slim node:20-alpine redis:7-alpine postgres:16-alpine cloudflare/cloudflared:latest` |
| Build context huge | `.dockerignore` gap — confirm it excludes `venv/ .venv/ node_modules/ .git/ .claude/ dist/` |
| Docker-Desktop "AMD64 — image may have poor performance, or fail, if run via emulation" on `noctus-waha` (Apple Silicon) | WAHA's free image is amd64-only under `:latest`; it ships a native arm64 build as `:arm` (also `:noweb-arm`). `docker-compose.infra.yml` `waha` is arch-aware (`image: ${WAHA_IMAGE:-…:latest}` / `platform: ${WAHA_PLATFORM:-linux/amd64}`); `start.sh` exports the `:arm`/`linux/arm64` pair when `uname -m` is `arm64`/`aarch64` → native, warning gone. amd64 hosts keep defaults. General rule: a third-party amd64-only image must be wired arch-aware (env-driven image+platform, host-detected in `start.sh`), never hard-pinned `platform: linux/amd64` |

---

## 8a · Local-postgres profile (offline dev)

By default every backend talks to remote Supabase. For offline dev /
isolated CI, `noctusai-infra` ships `postgres:16-alpine` under
`profiles: [postgres, full]`; `./start.sh local-db` activates it
alongside the fleet. Schema init runs once when the `postgres_data`
volume is empty, from `scripts/init-local-db/` in alpha order:
`00-extensions.sql` (pgcrypto/uuid-ossp/citext) → `00a-supabase-shims.sql`
(roles + `auth.jwt()`/`auth.uid()` stubs + `extensions`/`storage`
schemas + minimal `auth.users`) → `01-schemas.sql` → `02-migrations.sql`
(last two regenerated from each product's `001_*.sql` by
`scripts/bootstrap/build-init-local-db.sh`). Re-init: `./stop.sh volumes` then
`./start.sh local-db`. Caveats: RLS policies evaluate FALSE under
default Postgres settings (no `auth.jwt()` claims) — point a product at
it via its `.env` `SUPABASE_URL`; Supabase-only features are
best-effort shims.

---

## 9 · Native vs Docker — which when

| Situation | Choose |
|---|---|
| Iterating on a single hot file, want the fastest loop | Native (`./start.sh native`) |
| Demo / zero-setup / reproducing CI / cross-product traffic / deploy-shape | Docker (`./start.sh`) |
| New laptop without venv | Docker |
| Working one product, others just need to be up | Docker subset (`./start.sh <slug>`) |

Both paths share `.env` + the `PRODUCTS` registry — they agree on what
exists; they differ only in how it runs.

---

## 10 · `VITE_*` build-arg contract

Every `import.meta.env.VITE_*` referenced in product **or seed** code
must be **both** an `ARG` in the product's frontend-build stage **and**
an `args:` key in the compose `build:` block, sourced from root `.env`
via `${VITE_FOO:-}` (the `:-` so an unset var is empty, not a compose
error). `.env` stays in `.dockerignore` (secrets); build-args bridge
the public subset. **Public-by-design:** `VITE_*` ships to the browser
bundle — only public config (URLs, anon keys, flags).

**Boot-critical baked set:** `VITE_SUPABASE_URL` +
`VITE_SUPABASE_PUBLISHABLE_KEY` are **baked at `vite build`** (Vite
inlines `import.meta.env.VITE_*`) — the seed FE
`createProductSupabase`/`assertSupabaseBuildEnv`
(`seed/lib/frontend/src/supabase.ts`) hard-throw (blank page) when
either is empty in the bundle. They are the canonical-template VITE
block's first entries and the propagate-script `SEED_VITE_SUPABASE`
constant (`scripts/propagate-{dockerfiles,composes}.sh`) prefixes them
onto **every** product's ARG/`args:` block ⇒ DEFAULT-ON fleet-wide,
zero per-product code. ¬ runtime-detected: distinct from
`VITE_BACKEND_API_URL` (next paragraph) which is *never* baked — baking
the backend URL would break tunnel/proxy. Baked ⊂ build-time;
backend-URL ∈ runtime-detected — never interchange.

**Carve-out:** `VITE_BACKEND_API_URL` + `VITE_PRODUCT_SCHEMA` are
**factory-injected** by `seed/framework/frontend/vite.config.factory.ts`
(no arg). Single-container is same-origin, so the factory injects
`VITE_BACKEND_API_URL` as the raw expression **`window.location.origin`**
when `VITE_SAME_ORIGIN=1` (set by the frontend-build stage) — correct
under localhost, `*.trycloudflare.com`, and any deploy host, with zero
per-file changes. `seed/lib/frontend/src/env.ts` reads the
define-rewritten literal. Audit deps with
`python mcp/noctusai/cli.py --check-framework-deps [--fix]` (also gated in CI).

---

## 11 · Per-product healthcheck override

Default healthcheck = `curl /api/health`. A product needing a deeper
readiness probe composes seed readiness hooks rather than inventing a
path: pass `HealthEndpointConfig(readiness_hooks=[…])` to
`create_product_app(...)`; the seed aggregates them at `/_ready`. Point
the compose `healthcheck:` at `/_ready` with a longer `timeout` /
`start_period`. **Reference: dev-team** — `agno_ping`
(`products/dev-team/backend/app/services/agno_health.py`) probes
`ANTHROPIC_API_KEY` + leader-model allowlist + `dev_team` importability;
its compose targets `/_ready` (`timeout=10s`, `start_period=30s`). The
scaffolder template carries a commented healthcheck seam. Don't override
when the default suffices; never invent a new health path-shape.

---

## 11a · Image registry strategy

**Per-product registries** (locked 2026-05-10). Each product gets its
own GHCR namespace — no monorepo registry. Rationale: per-product access
control (a write PAT scoped to one product, no fleet blast radius),
independent retention, independent publication cadence, alignment with
the product-folder boundary used everywhere else.

Tag pattern — **one image per product** (no `-backend`/`-frontend` role
split anymore; it's one container):

```
ghcr.io/jraphaelsst/noctus-<slug>:<tag>
```

`<tag>` ∈ `dev` (local default — `${NOCTUS_IMAGE_TAG:-dev}`,
build-only, no push) · `<git-sha>` (CI immutable, deploys reference
these) · `latest` (most recent main build; never deploy from it) ·
`<semver>` (future tagged releases). Shared base images
(`noctus-seed-{backend,frontend}-base`) are local build inputs; if ever
published they get their own slot. `container_name: noctus-<slug>`
(no registry path) stays the friendly `docker ps` / inter-service-DNS
name; only `image:` carries the registry path.

---

## 11b · CI workflow

`.github/workflows/test.yml` job `docker-images-build` builds **one
image per product** — an 11-cell matrix (`fail-fast: false` so a heavy
product can't cancel siblings). Each cell: build the shared seed base
images (`noctus-seed-{backend,frontend}-base`, gha-cached under a
*shared* scope so the heavy layer is paid once across the matrix), then
`docker buildx build --target runtime` the product (the slim shippable
artifact — **not** `runtime-watch`), Trivy-scan `HIGH,CRITICAL`
(pinned action, `ignore-unfixed`, `exit-code: 1` so a vulnerable image
fails **before** push and never reaches the registry; SARIF → Security
tab every run), and on `main` only `docker push
ghcr.io/jraphaelsst/noctus-<slug>:<short-sha>` + `:latest` after a clean
scan. PR builds are verify-only. `docker-compose-validate` validates
both root projects + every per-product compose. There is **no prod
compose overlay** — the `runtime` image is self-contained and shippable
as-is; a server orchestration file is deliberately not carried until
there is a real deploy target (don't gold-plate speculative infra).

---

## 12 · Anti-patterns

- **Don't `COPY .env`.** Secrets → `env_file:` at runtime; public
  build vars → `args:`.
- **Don't run as root.** Every image ends `USER noctus`.
- **Don't hand-edit per-product Dockerfiles/composes.** Edit
  `products/seed/`, then `propagate-*.sh`; the pre-commit `--check`
  blocks drift.
- **Don't reintroduce a `dev` mode / second container.** One container,
  one shape; `runtime` vs `runtime-watch` is a build target chosen by
  tooling, never an operator concept.
- **Don't remove the tunnel `--protocol http2` pin.** QUIC dies behind
  NATs and can't re-register.
- **Don't make `noctus-net` non-external.** The two-project split
  requires it created once, outside any single project.
- **Don't `chown -R` a large path inherited from a shared base.**
  `RUN … chown -R noctus:noctus /app /opt/venv` rewrites every file of
  the ~276 MB base venv into a **new unshared ~311 MB per-product layer**
  — defeating base-layer sharing for zero benefit (the venv is read-only
  at runtime; a non-root user only needs read+exec, and `python -m venv`
  output is already world-readable). Measured 2026-05-19: removing
  `/opt/venv` from the chown cut ≈370–430 MB **per product** (≈3.3 GB
  fleet, unique footprint −35–40%). Rule: chown only product-owned paths
  (`/app`); never recursively re-own an inherited base path. If a
  non-root user must own copied files, use `COPY --chown=` (writes the
  ownership into the original layer) — never a follow-up `RUN chown -R`.
  Sibling: the `runtime-watch` post-`npm install` `chown -R /app`
  rewrites the fresh glibc `node_modules` the same way (Phase 2 of the
  `frontend-deps-base-consolidation` project).

---

## 12a · Divergent-architecture absorptions MUST refactor to the house model

An **incoming product whose container architecture differs from noc's
single-container house model MUST be refactored to it on absorption** —
not consumed as-is, not wrapped, not special-cased in the fleet.

The house model is one container per product: uvicorn serves API + the
built SPA on one port via the seed factory `serve_spa` / `SERVE_SPA_DIR`
seam, `FROM noctus-seed-*-base` is the named seam, two compose projects
(`noctusai-products` / `noctusai-infra`) on the external `noctus-net`.
A product that arrives as a **2-container backend+nginx+proxy** topology
(the shape the social-wiring sibling carried — separate uvicorn + nginx
SPA host + a standalone single-URL proxy, per-product `<slug>-net`, a
Vite-HMR dev sidecar) does NOT get a carve-out: it is rewritten to the
single-container shape during the absorption's container-refactor gate
(Gate 9 of `KB § GUIDES/absorb-seed-workspace.md`).

Why a rule and not just "it'll work out":

- A divergent topology in the fleet breaks the **one-container = one
  Docker-Desktop 1-click row** invariant the two-project split depends
  on, and the same-origin SPA contract (`window.location.origin` define-
  injection) — both are load-bearing for tunnel/deploy correctness.
- **Newly-scaffolded products inherit the house model by construction**
  (`noctus.dev.scaffold_product` → `templates/product-seed/`), so this
  cannot recur for noc-native products. The rule exists for the
  *absorption* case — externally-developed workspaces evolve their own
  container shape and the divergence is only discovered at absorption.
- Fold only the still-relevant bits of the divergent infra: SPA fallback
  is already covered by `serve_spa`; a separate `proxy/nginx.conf` is
  redundant under the house model and is dropped. The profile-gated
  `<slug>-tunnel` already replaces a hand-rolled single-URL proxy.

**Live doc-code-coherence note (2026-05-16):** the scaffold template was
observed emitting a `docker-compose.override.yml` registration that
drifts from the single-env house model — a real scaffold defect surfaced
by the social-wiring teardown verification. *The code fix is owned by the
scaffold-fix work; this section owns the rule* — an absorbed product's
compose must be the canonical single-service shape, override-free.

> History note: this rule was extracted from the social-wiring absorption
> (2026-05-16), where the sibling workspace's 2-container+proxy topology
> was refactored to the house model as the final absorption gate. Dated
> fact recorded in-line on purpose — do not anchor it to a `projects/` or
> `archive/` folder (not persisted long-term).

---

## 12b · Validation-freshness contract — the live container is part of "ready to test"

`pytest` green + `vite build` clean ≠ "the running container reflects the fix." A long-running container that was started before today's commits — or one whose bind-mount source points at a *parallel* repo path (a sibling worktree, a second clone, an older `noctus-fleet/` checkout while you've been editing `noctusai/`) — serves stale code. Declaring "ready to test" without confirming runtime parity sets the user up to manually exercise code from yesterday.

**Trigger.** Any time the [Finish-the-session checklist](project-execution.md) runs while a product container is up AND the session changed code that container serves (seed/, product backend, product frontend, any module imported at request time). Fix-on-contact debt fixes are the highest-risk class — a fix you applied two minutes ago is *not yet running*.

**Procedure.** Four cheap steps that catch every common drift shape:

1. **Confirm the bind-mount source.** `docker inspect <container> --format '{{json .Mounts}}'` — note the host path under `Source` for `/app/seed` and `/app/products/<slug>/{backend,frontend}`. If it's not the repo you've been editing, your fix is invisible to this container. Reconcile (copy the fix into the bind-mounted tree, or recreate the container from the right project root) before continuing.
2. **Confirm the watched directories.** `docker logs <container> | grep "Will watch"` — uvicorn `--reload` only reacts to changes inside those dirs. Touching code outside the watch set is a no-op; you need a restart.
3. **Trigger the reload.** Edits inside a watched bind-mount → uvicorn reloads on save (sub-second). Otherwise: `docker restart <container>` (bind-mount + new process), or `docker compose up -d --build <slug>` if the change is in deps or anything *not* bind-mounted (rare; the runtime-watch model bind-mounts almost everything).
4. **Live-probe the endpoint that exercises the fix.** `curl http://localhost:<port>/<path>` — confirm the new behavior end-to-end. This is the only step that distinguishes "tests green" from "user about to manually test will see the fix."

**Anti-pattern.** Reporting "ready to test" after only `pytest`/`vite build` green when a container is running. Subtypes:
- *13h-uptime drift*: container started before this session's commits, never restarted.
- *Parallel-repo drift*: bind-mount source is `noctus-fleet/` (or a worktree, or a second clone) while edits landed in `noctusai/`. The two trees have diverged commits.
- *Outside-watch drift*: code edited in a dir uvicorn doesn't watch; container ran the old code until the next manual restart.

**Bit.** 2026-05-20 social-wiring validation — 384 backend tests passed + frontend build clean, but the user opened the Dashboard and hit "Servidor indisponivel" toasts on `/api/me/consents` + `/api/admin/llm-spend/<uuid>`. Two compounding causes: (a) container was up 13h, predating commit `63b98284` which added the `is_api_or_ops` SPA guard; (b) container bind-mounted `/Users/rapha/.../noctus-fleet/seed`, not the `/noctusai/seed` we'd been editing. Fix was applied to the *wrong tree* relative to the live runtime.

**Doc anchors.** `feedback_container_freshness_on_validate` (memory) · sibling of `feedback_finish_session`.

### 12b.1 · Multi-clone drift — when "the bind-mount sits on a *second* clone of the same repo"

This is a degenerate special case of the freshness contract worth calling out because the symptom is the same ("container runs stale code") but the cure is different.

A workstation that holds two clones of the same `origin` — e.g. `~/.../NoctusAI/noctusai/` AND `~/.../NoctusAI/noctus-fleet/` — accumulates divergent local commits in each tree because nothing forces convergence. When a docker bind mount silently anchors to one of them while the operator edits the other, fixes shipped to the "active" tree are invisible to the running runtime no matter how many `pytest` runs go green. Subset of [[feedback_concurrent_agents_never_share_checkout]] for *worktrees*, but distinct: worktrees share `.git` and the divergence is explicit; second-clones share nothing and the divergence is silent.

**Detect.** Run this fleet-wide bind-mount audit before any validation:

```bash
docker inspect $(docker ps -q) --format \
  '{{.Name}} {{range .Mounts}}{{if eq .Type "bind"}}{{.Source}} {{end}}{{end}}'
```

Any `Source` outside the canonical clone is a drift hazard. Resolve immediately — do **not** patch the divergent tree to mirror the canonical one (a `feedback_no_quick_fixes` slip).

**Resolve.** From the canonical clone:

```bash
docker compose stop <slug>
docker compose rm -f <slug>
docker compose up -d --build <slug>
```

The rebuild repoints all three bind mounts (`/app/seed`, `/app/products/<slug>/backend`, `/app/products/<slug>/frontend`) at the canonical clone and rebakes the image from the right source. Verified on social-wiring 2026-05-20.

**Prevent.** One canonical checkout per machine. Sanctioned exceptions are explicit and read-only: per-agent worktrees (`KB § PATTERNS/branching-and-merging.md`), template/sibling workspaces consuming noc read-only (`KB § PATTERNS/seed-workspace.md`, with chmod -R a-w). Anything else is a second clone, and a second clone is a drift hazard.

**Bit (2026-05-20).** Session edited `noctusai/`, shipped commit `63b98284` (SPA-fallback fix). All four product containers (core/social-wiring/erp/seed) bind-mounted `noctus-fleet/seed`. The fix was invisible to every running runtime. First-attempt surgical patch to `noctus-fleet/seed/app.py` worked but tolerated the underlying drift; the right fix was `compose up -d --build social-wiring` from `noctusai/`, which flipped all mounts atomically. User then asked to consolidate the remaining three.

---

## 13 · References

- Seed factory `serve_spa` seam — `seed/framework/backend/noctusai_seed/app.py`
- Same-origin define — `seed/framework/frontend/vite.config.factory.ts` + `seed/lib/frontend/src/env.ts`
- Canonical artifacts — `products/seed/backend/Dockerfile` · `products/seed/docker-compose.yml`
- Base images — `seed/docker/Dockerfile.{backend,frontend}-base` · `seed/docker/local-watch.sh`
- Propagation — `scripts/propagate-{dockerfiles,composes}.sh` · `scripts/infra/build-base-images.sh`
- CI — `.github/workflows/test.yml` job `docker-images-build` (one image/product, slim `runtime` target, Trivy-gated GHCR push)

> History note: this architecture replaced a 2-container-per-product
> shape (separate backend uvicorn + frontend nginx, per-product
> `<slug>-net`, a Vite-HMR dev sidecar). That context is recorded here
> in-line on purpose — **do not** point at `projects/` or `archive/`
> folders for it; they are not persisted long-term (see the durable-doc
> rule in `KB § 01-PHILOSOPHY.md`).
