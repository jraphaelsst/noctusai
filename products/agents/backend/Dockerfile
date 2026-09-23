# syntax=docker/dockerfile:1.7
# agents — thin product image (generated from products/seed/backend/Dockerfile; edit there + re-propagate).
#
# Project: containerization-single-container. Single container: uvicorn
# serves the API AND the built SPA on ONE port (the seed factory's
# `serve_spa` seam, fed by SERVE_SPA_DIR). The common heavy layers live in
# the shared bases (seed/docker/Dockerfile.{backend,frontend}-base) — this
# file only adds THIS product's specificities. `FROM noctus-seed-*-base`
# IS the named seam (inherit-and-extend, never fork).
#
# Prereq: the base images exist (scripts/infra/build-base-images.sh; start.sh
# orders this before product images). Build context: repo root.
#
# Per-product variance lives ONLY here (kept tiny, product-owned):
#   • the VITE_* build-arg block (public browser config bridged from .env)
#   • the product port (EXPOSE / uvicorn --port / healthcheck)
#   • any product extras (e.g. dev-team adds /opt/dev_team — see its file)

ARG GIT_SHA=dev

# ── frontend-build: this product's SPA bundle ───────────────────────────
FROM noctus-seed-frontend-base:dev AS frontend-build
WORKDIR /app
# Single-container ⇒ same-origin: the vite factory injects
# window.location.origin as the API base (tunnel/deploy-correct, zero
# per-file changes). Native/two-port dev leaves this unset.
ENV VITE_SAME_ORIGIN=1
# VITE_* build-arg contract — public browser config only; bridged from
# .env via compose `args:`. VITE_BACKEND_API_URL + VITE_PRODUCT_SCHEMA are
# factory-injected (no arg). {{VITE_ARGS}}
# VITE_SUPABASE_* are BOOT-CRITICAL and BAKED at build: the seed FE
# `createProductSupabase`/`assertSupabaseBuildEnv` hard-throw (blank
# page) when empty in the bundle. Vite inlines `import.meta.env.VITE_*`
# at `vite build`, so they MUST be present as ARG/ENV before the build.
# Distinct from VITE_BACKEND_API_URL, which stays runtime-detected
# (one image serves direct/tunnel/proxy) — do NOT bake the backend URL.
ARG VITE_SUPABASE_URL=
ENV VITE_SUPABASE_URL=${VITE_SUPABASE_URL}
ARG VITE_SUPABASE_PUBLISHABLE_KEY=
ENV VITE_SUPABASE_PUBLISHABLE_KEY=${VITE_SUPABASE_PUBLISHABLE_KEY}
ARG VITE_CORE_URL=
ENV VITE_CORE_URL=${VITE_CORE_URL}
COPY products/agents/frontend/package*.json ./products/agents/frontend/
WORKDIR /app/products/agents/frontend
# Drop the host lockfile before install: package-lock.json is generated on
# the dev's machine (darwin-arm64) and PINS the platform-optional native
# binaries (rollup/esbuild/lightningcss/@swc) to that os/cpu. npm honours
# the lockfile and SKIPS the linux binary → `vite build` crashes with
# "Cannot find module '@rollup/rollup-linux-*'" (npm/cli#4828). Removing it
# lets npm re-resolve optionals for THIS build platform/libc.
RUN --mount=type=cache,target=/root/.npm \
    rm -f package-lock.json \
    && npm install --no-audit --no-fund
COPY products/agents/frontend ./
# The vite factory derives VITE_PRODUCT_SCHEMA from this product's
# backend/app/database.py (seed resolveProductSchema) — ship it into the
# build stage or `npm run build` throws.
COPY products/agents/backend/app/database.py ../backend/app/database.py
RUN npm run build   # → /app/products/agents/frontend/dist

# ── runtime: API + SPA on one port ──────────────────────────────────────
FROM noctus-seed-backend-base:dev AS runtime
ARG GIT_SHA
LABEL org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.title="noctus-agents"
WORKDIR /app

# Product-specific Python deps (seed lib/framework already in the base
# venv; strip the `-e seed/` editable lines — they're inherited).
COPY products/agents/backend/requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    grep -v '^-e seed/' /tmp/requirements.txt > /tmp/req.clean.txt \
    && pip install -r /tmp/req.clean.txt
# agents: Julia's dedicated per-conversation slot uids/gids + the CLI
# she is launched through (contract §E.11, supersedes §E.5's single
# shared uid 1001). `--no-create-home`: there is no home dir to
# protect (nothing is ever baked there) — the slot script points
# HOME/TMPDIR at a dedicated per-slot tmpfs instead (compose `tmpfs:
# [/run/julia-0, /run/julia-1, /run/julia-2]`, each uid/gid-owned by
# its own slot uid — this product's `/tmp` belongs to `noctus` only).
# Fixed at 3 slots (uid/gid 2000-2002), matching `ENV JULIA_CLI_SLOTS`
# below — I3: nothing from one conversation is readable by another
# slot's uid, so each slot gets its OWN dedicated uid/gid, never a
# shared one (that was §E.5's whole problem: one compromised turn
# could read every other conversation's transcript under the same
# shared uid 1001/HOME=/run/julia).
# `--user-group` (tried first, real-image check 2026-09-15) auto-
# assigns the GROUP an arbitrary next-free SYSTEM gid (999, 998, 997
# on the real image) and ignores `--uid` for it entirely — `useradd`
# only ever pins the uid it was given to the USER, never to the group
# `--user-group` creates alongside it. Explicit `groupadd --gid`
# FIRST, then `useradd --gid` to join that exact group, is what
# actually makes gid == uid == 2000+K for every slot (contract §E.11
# requires BOTH, not uid alone).
RUN for _slot in 0 1 2; do \
        _uid=$((2000 + _slot)); \
        groupadd --system --gid "$_uid" "julia-cli-$_slot"; \
        useradd --system --no-create-home --shell /usr/sbin/nologin \
            --uid "$_uid" --gid "$_uid" "julia-cli-$_slot"; \
    done
ENV JULIA_CLI_SLOTS=3
# The SDK's one-off version-check spawn (`_internal/transport/
# subprocess_cli.py:799`, `[cli_path, "-v"]`) runs WITHOUT `user=` at
# all — it would launch as whatever uid called it (`noctus`), which
# `bin/julia-cli-exec` would then refuse with exit 126 (uid 1000 is
# outside the [2000, 2000+JULIA_CLI_SLOTS) slot range). Skipping the
# version check entirely avoids that spawn altogether; the CLI
# version is already pinned by the wheel (contract §E.11).
ENV CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK=1

# Bundled Claude Code CLI — NOT a `curl .../install.sh | bash` step
# (tech-lead review 2026-09-14: unpinned, pulled at build time, drifts
# from the SDK pin) and NOT `npm install -g @anthropic-ai/claude-code`
# (the slim deploy `runtime` target ships no Node — see `runtime-watch`
# below). `claude-agent-sdk==0.2.152`'s manylinux wheels (x86_64 AND
# aarch64) already ship a version-matched, self-contained binary at
# `claude_agent_sdk/_bundled/claude` (~200MB, already mode 0755
# root:root from `pip install` running as root, before the non-root
# step below — verified live). Resolved via python, not a second
# hardcoded path literal, and `test -x` fails the BUILD (not a live
# Julia turn) the day a future SDK bump relocates or drops it. The
# symlink is what makes the wrapper's own hardcoded exec target a
# stable literal that never needs to track the exact venv/
# site-packages path (no `JULIA_CLAUDE_BIN` env seam — dropped
# deliberately, see `bin/julia-cli-exec`'s own header comment).
RUN CLAUDE_BUNDLED="$(python3 -c 'import claude_agent_sdk, pathlib; print(pathlib.Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude")')" \
    && test -x "$CLAUDE_BUNDLED" || { echo "bundled claude CLI not found/executable at $CLAUDE_BUNDLED (claude-agent-sdk version drift?)" >&2; exit 1; } \
    && ln -s "$CLAUDE_BUNDLED" /usr/local/bin/claude-bundled

# The wrapper + entrypoint + slot script (contract §E.11) — placed
# here (root context, BEFORE the non-root-user step below) so a plain
# COPY lands them root:root by Docker's default. Their FINAL
# ownership/mode is reasserted after the canonical `chown -R
# noctus:noctus /app` a few lines down — that recursive chown would
# otherwise flip them to `noctus`, silently undoing "root-owned, not
# app-writable" (see the ownership reassertion a few lines down —
# that same block also drops the canonical `USER noctus` for this
# product only; see the ENTRYPOINT at the bottom). `julia-cli-slot`
# is root-owned for the same reason as the other two: it runs the
# per-conversation sweep + handoff-copy + CLI exec AS the slot uid
# (no capabilities), so it must never be writable by that uid or by
# `noctus`.
COPY products/agents/backend/bin/julia-cli-exec /app/bin/julia-cli-exec
COPY products/agents/backend/bin/entrypoint.sh /app/bin/entrypoint.sh
COPY products/agents/backend/bin/julia-cli-slot /app/bin/julia-cli-slot

# Strip every setuid/setgid bit in the image (roadmap D1) — defence in
# depth ORTHOGONAL to the capability model above: a setuid/setgid file
# (Debian ships several by default, e.g. `su`/`mount`/`passwd`) grants
# privilege via the FILE's own bits, independent of the calling
# process's capability set — our `cap_drop`/`cap_add` restrictions say
# nothing about what a setuid-root binary could still do if exec'd.
# None of these binaries are used by this product at runtime (uvicorn/
# python + the three scripts above only).
RUN find / -xdev -perm /6000 -type f -exec chmod a-s {} + || true

# Product backend code + the built SPA.
COPY products/agents/backend/ ./products/agents/backend/
COPY --from=frontend-build /app/products/agents/frontend/dist ./products/agents/frontend/dist
ENV SERVE_SPA_DIR=/app/products/agents/frontend/dist

# Non-root user — created LAST (pip install above ran as root, before this).
# chown ONLY /app — NOT /opt/venv. /opt/venv (~276MB) comes from the SHARED
# backend base layer and is read-only at runtime (no runtime pip; editable
# seed installs resolve via .pth → bind-mounted /app/seed). `chown -R
# /opt/venv` would rewrite every file into a NEW unshared ~311MB per-product
# layer (measured 2026-05-19) — defeating base sharing for zero benefit
# (venv is world-readable from `python -m venv`; noctus only needs read+exec).
# Anti-pattern: never `chown -R` a large inherited base path. ~2.5GB fleet.
RUN useradd -m -u 1000 -G julia-cli-0,julia-cli-1,julia-cli-2 noctus \
    && chown -R noctus:noctus /app \
    && chown root:root /app/bin/julia-cli-exec /app/bin/entrypoint.sh /app/bin/julia-cli-slot \
    && chmod 0755 /app/bin/julia-cli-exec /app/bin/entrypoint.sh /app/bin/julia-cli-slot
# `noctus` is a supplementary member of exactly the 3 slot groups
# (contract §E.11) — `--init-groups` in `bin/entrypoint.sh`'s own
# `setpriv` call picks them up at the root->noctus drop. This is what
# lets `noctus` (writing the durable-transcript handoff file as part
# of a future slice's turn setup) set that file's GROUP to
# `julia-cli-K` with a plain chown(path, -1, gid) — Linux only requires
# the calling process to be a MEMBER of the target group for a
# group-only chown, never CAP_CHOWN, so this membership is what makes
# "no CHOWN capability is ever needed" literally true, not just
# asserted.
# No `USER noctus` here (deviates from the canonical shape, agents-only,
# roadmap D1): the ENTRYPOINT below does the uid switch AT EXEC via
# `setpriv` instead, which is what actually populates AMBIENT caps for
# the SDK's `Popen(user="julia-cli")` subprocess spawn — a plain
# `USER noctus` directive here does not (verified empirically,
# moby#45491/PR#36587).

EXPOSE 8016
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8016/api/health || exit 1
# ENTRYPOINT replaces the canonical plain-uvicorn CMD (roadmap D1)
# — a root:root, fail-closed script; see `bin/entrypoint.sh`'s own
# header for exactly what it refuses to boot without, and why the
# container stays root through this line (no `USER noctus` above)
# so its own `setpriv` can populate AMBIENT caps as it drops to
# `noctus`.
ENTRYPOINT ["/app/bin/entrypoint.sh"]

# ── secc-proof: PROOF-ONLY stage, NEVER tagged/pushed/deployed ──────────
# Roadmap julia-agents-academia-2026-09, row SEC-C
# (`products/agents/backend/secc/run_proof.py`). CI has no real
# `ANTHROPIC_API_KEY` to exercise the Julia CLI subprocess with, so this
# stage re-points ONLY `/usr/local/bin/claude-bundled` at a root-owned
# probe script (`secc/probe.py`) that dumps its own uid/gid/groups/caps/
# env + an EACCES/EPERM access-check battery instead of talking to
# Anthropic. `bin/julia-cli-exec` and `bin/entrypoint.sh` are otherwise
# BYTE-IDENTICAL to `runtime` (asserted by `run_proof.py` via sha256) —
# only the one symlink target changes. `bin/julia-cli-slot` (contract
# §E.11, roadmap D1) is a third root-owned script in this same image;
# extending the sha256 proof to cover it too is roadmap D2's row, not
# yet done here (D1 declares it, does not fix the harness).
# 🔴 This stage must NEVER be tagged, pushed, or deployed:
# `scripts/infra/build-and-push.sh` / `.github/workflows/build-and-push.yml`
# build + push `--target runtime` only, never `secc-proof`
# (`run_proof.py`'s `check_build_and_push_never_builds_secc_proof` asserts
# this statically on every proof run).
FROM runtime AS secc-proof
USER root
RUN rm -f /usr/local/bin/claude-bundled
COPY products/agents/backend/secc/probe.py /usr/local/bin/claude-bundled
# probe.py's `#!/usr/bin/env python3` shebang resolves through `env`'s OWN
# PATH lookup — and the `env -i PATH=/usr/bin:/bin ...` handoff (now in
# `bin/julia-cli-slot`, contract §E.11 — `bin/julia-cli-exec` only
# switches identity and hands off to it) deliberately does NOT include
# `/opt/venv/bin` (the real bundled CLI is a native binary, not a python
# script, so it never needed it). Symlinking the venv's python3 onto that
# same restricted PATH is proof-harness-only plumbing, not a change to
# the allowlist the slot script actually enforces for the real CLI.
RUN ln -sf "$(command -v python3)" /usr/bin/python3 \
    && chown root:root /usr/local/bin/claude-bundled \
    && chmod 0755 /usr/local/bin/claude-bundled

# ── runtime-watch: SAME single container, local live-rebuild ────────────
# ONE container, ONE shape, ONE command (`./start.sh`). The local
# per-product compose builds THIS target + bind-mounts source; the user
# never picks a mode. Adds node (so the one container can rebuild the
# SPA itself) + the watch entrypoint: `vite build --watch` keeps dist
# fresh, `uvicorn --reload` reloads .py. Deploy still uses the slim
# `runtime` above (node absent there). Source is bind-mounted at run, so
# THIS target is intentionally not a shippable artifact — `runtime` is.
FROM runtime AS runtime-watch
# SEC-A/SEC-C do NOT apply to this stage (roadmap D1, declared not
# fixed — dev fleet is dormant): the node-install step below re-runs
# `chown -R noctus:noctus /app`, flipping the wrapper/entrypoint/slot
# script back to `noctus`-owned, and ends on a plain `USER noctus` +
# the `local-watch` ENTRYPOINT, not `bin/entrypoint.sh`. Harmless only
# because `get_agent_runtime` never returns the real SDK runtime
# without a configured `ANTHROPIC_API_KEY`, which local dev never
# sets — there is no live Julia turn to isolate in this stage today.
USER root
# Node for the in-container SPA rebuild — from the OFFICIAL nodejs.org binary
# tarball (node 20 + npm 10 BUNDLED). Only the local runtime-watch image
# carries node (deploy = slim `runtime`, node absent). Two deliberate NOTs:
#  • NOT NodeSource — the Docker build VM persistently fails the TLS handshake
#    to deb.nodesource.com ("curl: (35) ...unexpected eof while reading", every
#    retry) while host + deb.debian.org + nodejs.org all work (§3.19). nodejs.org
#    is a DIFFERENT, reachable host.
#  • NOT Debian's `apt install nodejs npm` — trixie bundles npm 9.2.0, whose
#    peer-dep resolver chokes on the file:-linked @noctusai/lib
#    ("ERESOLVE ... @supabase/supabase-js@undefined"); npm 10 (the tarball's)
#    resolves it correctly. The tarball lands npm in /usr/local/bin (ahead of
#    Debian's /usr/bin in PATH) so there's no dpkg-vs-global shadowing fight.
# (Bit 2026-05-24: the §3.19 Debian swap silently downgraded npm 10→9.2.0,
# regressing the FE install — caught by a faithful repro: npm 9.2.0 ERESOLVE
# vs npm 10 EXIT=0 on the same package.json set. KB §3.19/§3.21.)
ARG NODE_VERSION=v20.19.0
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl xz-utils \
    && rm -rf /var/lib/apt/lists/* \
    && case "$(dpkg --print-architecture)" in \
         amd64) NODE_ARCH=x64 ;; \
         arm64) NODE_ARCH=arm64 ;; \
         *) echo "unsupported arch: $(dpkg --print-architecture)" >&2; exit 1 ;; \
       esac \
    && curl -fsSL --retry 5 --retry-all-errors --retry-delay 3 --connect-timeout 30 \
         "https://nodejs.org/dist/${NODE_VERSION}/node-${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz" \
         -o /tmp/node.tar.xz \
    && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \
    && rm /tmp/node.tar.xz \
    && node --version && npm --version
# Frontend deps installed HERE (glibc) — esbuild/vite ship platform
# binaries; the alpine frontend-base node_modules are not ABI-portable.
# Seed framework/lib FE deps too: local-watch's `vite build` loads the
# tailwind/vite factory at /app/seed/framework/frontend/*.factory.ts
# which `require("tailwindcss-animate")` etc. — Node resolves from THAT
# path, not the product's. runtime-watch is FROM the backend base
# (glibc, no seed FE node_modules) and the compose bind-mounts ../../seed
# (node_modules-less in any clean checkout/CI/worktree) → without this
# the factory require fails → vite build fails → local-watch restart-loop
# → never healthy. The alpine frontend-base installs these for the
# build stage; runtime-watch (glibc) must install them itself. The
# compose pairs this with anon volumes on these nested node_modules so
# the ../../seed bind-mount doesn't re-mask them (§3.2b).
COPY products/agents/frontend/package*.json ./products/agents/frontend/
COPY seed/framework/frontend/package*.json /app/seed/framework/frontend/
COPY seed/lib/frontend/package*.json /app/seed/lib/frontend/
# Same lockfile-pins-wrong-platform-optional bug as frontend-build, here on
# glibc/arm64 — drop the host lock so npm fetches the linux native binary
# (otherwise local-watch's `vite build` crash-loops the container).
# NPM fetch retries — these installs pull ~300-700 packages each from
# npmjs.org; a single ECONNRESET tarball fetch (~5% of long installs)
# aborts the whole RUN with exit 1 and loses 50+ min of work. Bumping
# `--fetch-retries` to 5 with backoff (20s..120s) absorbs transient
# blips. `--fetch-timeout=300000` extends per-request ceiling for big
# tarballs. Cache mount above amortizes after the first successful pass.
ARG NPM_RETRY="--fetch-retries=5 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000 --fetch-timeout=300000"
RUN --mount=type=cache,target=/root/.npm \
    cd products/agents/frontend \
    && rm -f package-lock.json \
    && npm install --no-audit --no-fund ${NPM_RETRY} \
    && cd /app/seed/framework/frontend \
    && rm -f package-lock.json \
    && npm install --no-audit --no-fund --include=peer ${NPM_RETRY} \
    && cd /app/seed/lib/frontend \
    && rm -f package-lock.json \
    && npm install --no-audit --no-fund --include=peer ${NPM_RETRY}
COPY seed/docker/local-watch.sh /usr/local/bin/local-watch
RUN chmod +x /usr/local/bin/local-watch \
    && chown -R noctus:noctus /app
USER noctus
ENV PRODUCT_SLUG=agents PRODUCT_PORT=8016
# Same-origin SPA, single-container — local-watch builds the SPA via
# `vite build --watch` at container-start; vite's `define` rewrites
# `import.meta.env.VITE_BACKEND_API_URL` to `window.location.origin`
# ONLY when this env is set. Without it the build falls back to a
# PRODUCT_MAP lookup → defaults to http://localhost:8000 for products
# whose FE port isn't in the map → silent cross-product CORS failures.
# The `frontend-build` stage already sets this; runtime-watch must too
# because it rebuilds the bundle on every container start. (Bit
# 2026-05-20 on social-wiring.) Placed AFTER all RUN layers so a future
# toggle invalidates only this trivial layer, not the apt+npm cache.
ENV VITE_SAME_ORIGIN=1
ENTRYPOINT ["/usr/local/bin/local-watch"]
