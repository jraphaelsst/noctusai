---
name: noc-container-debug
description: Use for ANY container failure or operational change — triggers "container won't go healthy", "the build is broken", "my fix isn't applied", "rebuild", "containers out of sync", "the container isn't picking up my edit". Reach here BEFORE grepping — most re-diagnoses skip the source-of-truth chain.
version: 1.1.0
---

# noc-container-debug — source-of-truth chain first

Most container time-sinks are the §1 chain skipped. Docker Desktop is NEVER truth.

## Workflow

1. **Source-of-truth chain** (in order): git → file on disk → manifest → history → inspect mounts → exec into container → logs. DD UI is never authoritative.
2. **Freshness probe** (fix-not-applied class): bind-mount source == edited repo? uvicorn watch set covers the changed dir? `vite build --watch` running? Live-probe the fixed endpoint. "Tests green" ≠ "running container reflects the fix."
3. **Operational primitives:** `--force-recreate` after compose-volume edits · build vs runtime verify · disk diagnostics · multi-arch check (amd64 emulation).
   - **Stale-container class — recreate ≠ rebuild (2026-05-29 drift):** dead host port (`curl localhost:<port>` → `000` not-reachable/flapping · `52` empty-reply, port-forward up but app silent on the external iface or mid-reload · `503` up-but-warming · `200` ready) while `/api/health` answers INSIDE (`docker exec <c> wget -qO- localhost:<port>/api/health`) = stale CONTAINER STATE, not an image fault. Causes: Docker auto-resurrected the container after a host sleep (seed compose ships `restart: unless-stopped`), and/or repo-wide git/cache ops rewrote bind-mounted `seed/**` mtimes → `uvicorn --reload` storm. **Fix: `docker compose -f docker-compose.yml up -d --force-recreate --no-build <svc>`** (seconds, cached image). NEVER `./start.sh build` (that's `--no-cache --pull`, the slow full IMAGE rebuild) for a state problem. `./start.sh` now self-heals: it force-recreates any TARGETED product that is `unhealthy`/`restarting` before the boot-wave (memory `feedback_dev_container_stale_reuse_drift`).
4. **Diagnostic flowchart A–G** + the 8-step safe-change methodology in the ops doc.
5. **Operate the live fleet** via `noctus.vps.*` — `ps`/`health`/`logs`/`inspect`/`images`/`disk`/`stats` (read-free) · `restart`/`recreate`/`prune` (confirm-gated).

## Guardrails
- ONE container per product (uvicorn serves API + built SPA via `serve_spa`); `noctus-net` is external. NO dev/prod split — one image, two targets (`runtime-watch` local / slim `runtime` deploy).
- alpine-vs-glibc FE deps, lockfile platform optionals, base-cascade rebuild, SPA-race, QUIC-tunnel-needs-http2 — see the codified bumps catalog.

## Depth
`KB § PATTERNS/devops/containerization-operations.md` (§1 chain, §4 flowchart, §3 bumps) · architecture: `KB § PATTERNS/devops/containerization.md` (§5c sync runbook, §12b freshness).
