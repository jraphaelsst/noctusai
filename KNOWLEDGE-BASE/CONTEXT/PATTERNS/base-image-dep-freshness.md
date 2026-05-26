# Base-image dep freshness — built images must not drift from declared deps

**The class.** A built image's installed `node_modules` (or any baked dep set) can silently drift from the declared `package.json`: a dep is added to `package.json`, but the locally-cached base image is **not rebuilt**, so its `node_modules` lacks the dep. The product still *runs* because the container's **anonymous `node_modules` volume** was seeded earlier (when the image was current) and accumulated the dep — so the staleness is invisible **until a clean container recreate** re-seeds that anon volume from the (stale) image. Then every product's `vite build` dies on `Cannot find module '<dep>'`.

This is a special case of **dev↔prod parity** ([[dev-prod-parity]]) at the *build-artifact* layer: the running container's behavior derived from a runtime-accumulated artifact (the anon volume), not from the declared source.

**Born:** 2026-05-25 — `noctus-seed-frontend-base` lacked `tailwindcss-animate` (declared in `seed/framework/frontend/package.json`, present in the lock). A `docker rm -fv` (renaming the dev fleet, `-v` dropping anon volumes) forced an anon-volume re-seed from the stale base → all 4 local products failed their `vite build`.

## Why LOCAL is vulnerable but PROD is immune

| | Local dev | Prod (CI → GHCR) |
|---|---|---|
| Base images | built ONCE by `start.sh`/`build-base-images.sh`, then **Docker-cached + reused** | rebuilt **fresh every run** by `build-and-push.sh` (calls `build-base-images.sh`) on an **ephemeral** GitHub runner (no persistent layer cache) |
| Failure mode | base goes stale vs `package.json`; anon-volume luck hides it | n/a — fresh build always has current deps; `set -euo pipefail` + "never push a broken-FE image" is **fail-closed** (a failed `vite build` ⇒ no image pushed) |

So a healthy prod container with a baked `dist` is **proof** the dep was present at build. The drift is a local-cache artifact.

## The `docker rm -fv` footgun

`docker rm -fv <product>` removes the container's **anonymous** node_modules volumes (the arm64/glibc isolation volumes the compose layers on top of the source bind-mount). On recreate they re-seed from the **image layer** — exposing any base-image staleness. `-v` does NOT touch *named* volumes (redis/waha data survive). When recreating product containers, prefer `docker compose up -d --renew-anon-volumes` over `rm -fv` so the re-seed is explicit and from a freshly-built image.

## Codified guardrails

1. **Build-time dep-completeness gate (primary)** — `scripts/infra/build-base-images.sh` verifies, after building the frontend base, that **every** declared `dependencies`+`devDependencies` in `seed/framework/frontend` + `seed/lib/frontend` resolves in the image (`node -e` existsSync per dep). A stale/incomplete base now **fails the build loudly** instead of shipping silently. Runs in BOTH local and CI (CI inherits it via `build-and-push.sh`), so the class can't recur undetected.

2. **Lockfile↔package.json sync (the static prerequisite)** — the base Dockerfile uses `npm install` (forgiving: installs from `package.json`, mutates the lock) rather than `npm ci` (reproducible, but **fails hard** if the lock is out of sync with `package.json`). Reproducible builds want `npm ci` — but only safe once the lock is provably complete (every declared dep ∈ `package-lock.json`). Until a `check_frontend_lockfile_sync` keeper guarantees that across all FE packages, the build-time gate (#1) is the catch. Sync drift remediation: `npm install` in the package dir, commit the lock.

## Remediation when it bites

```bash
# 1. rebuild the (frontend) base so node_modules matches package.json
bash scripts/infra/build-base-images.sh dev      # cache invalidates on package.json change
#    (if a cache foot-gun reuses a stale layer: docker build --no-cache -f seed/docker/Dockerfile.frontend-base ...)
# 2. rebuild product images FROM the fresh base + renew the anon volumes
docker compose -f docker-compose.yml up -d --build --renew-anon-volumes <slug>...
```

Siblings: [[dev-prod-parity]] (the umbrella), [[containerization]] (anon-volume node_modules isolation, §3.2b), [[containerization-operations]] (the bump catalog).
