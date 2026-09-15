"""noctus.dev.propagate — MCP exposure of the containerization codegen.

MCP-first: `scripts/propagate-composes.sh` + `scripts/propagate-dockerfiles.sh`
were bash one-offs wrapping a Python heredoc. This is a behaviour-preserving
port — byte-identical regenerated output vs the scripts — of the
containerization-single-container codegen: `products/seed/` is the canonical
single-container shape, every product's `docker-compose.yml` /
`backend/Dockerfile` is REGENERATED from it via TARGETED substitution
(slug / port / per-product VITE / dev-team extras / erp pip toolchain only —
the literal "seed" in `seed/lib`, `@noctusai/seed` is the SHARED seed tree
and must NOT change).

Two functions:
  • `propagate_composes(dry=False, ...)` — seed compose → N product composes.
  • `propagate_dockerfiles(dry=False, ...)` — seed backend Dockerfile → N
    thin product Dockerfiles.

Modes (mirrors the scripts' `[--check]`):
  • default (`dry=False, check=False`) — the parity-faithful path: WRITE
    every regenerated file. Returns the written set + ports.
  • `dry=True` — report planned writes (which files WOULD change), write
    NOTHING. The safe MCP default semantic; the scripts had no `--dry`.
  • `check=True` — the scripts' `--check`: report STALE files (missing or
    content-divergent vs canonical), write nothing, `status="stale"` if any.

`check=True` implies no writes regardless of `dry`.
"""
from __future__ import annotations

import pathlib
from typing import Any

from settings import REPO_ROOT
from workspace import resolve_caller_root

# slug → backend port, DERIVED from the `start.sh` PRODUCTS registry.
#
# This was a hardcoded literal list, justified by a comment reading "Frozen
# verbatim from scripts/propagate-{composes,dockerfiles}.sh — the scripts
# hardcode this identical list; parity requires the same set/order." Those
# scripts no longer exist, so the parity constraint that froze the list is
# gone — what remained was a hand-maintained slug set, the exact shape
# `KB § PATTERNS/devops/product-lockfile-and-slug-drift.md` says drifts.
#
# It had already drifted silently: a product registered in `start.sh` but
# absent here gets NO Dockerfile and NO compose from `--propagate`, and the
# command still exits 0 with a cheerful "written" list that simply omits it.
# Found 2026-08-13 absorbing p-studio, which propagate skipped without a word.
#
# `seed` is excluded deliberately — `products/seed/` is the canonical SOURCE
# both generators read from, never a generated target. It is the only
# registry row that must not appear here, and dropping it preserves the old
# list's exact order.
def _load_products() -> list[tuple[str, str]]:
    from noctusai_lib.config.cors_registry import parse_products_registry

    entries = parse_products_registry(REPO_ROOT / "start.sh")
    if not entries:
        raise RuntimeError(
            "start.sh PRODUCTS registry parsed empty — refusing to propagate "
            "against an unknown product set. A silent empty list here would "
            "regenerate nothing and report success."
        )
    return [(e["slug"], str(e["backend_port"])) for e in entries if e["slug"] != "seed"]


PRODUCTS: list[tuple[str, str]] = _load_products()

# ── compose substitution constants (verbatim from propagate-composes.sh) ──
_C_VITE_SUPABASE = (
    "      args:\n"
    "        # Boot-critical Supabase vars — baked at build (Vite inlines\n"
    "        # them; empty ⇒ blank-page throw). Backend URL stays runtime.\n"
    "        VITE_SUPABASE_URL: ${VITE_SUPABASE_URL:-}\n"
    "        VITE_SUPABASE_PUBLISHABLE_KEY: ${VITE_SUPABASE_PUBLISHABLE_KEY:-}\n"
)
_C_VITE_SEED = _C_VITE_SUPABASE + "        VITE_CORE_URL: ${VITE_CORE_URL:-}\n"
_C_VITE: dict[str, str] = {
    "core": _C_VITE_SUPABASE + "        VITE_CORE_API_URL: ${VITE_CORE_API_URL:-}\n",
    "erp-imobiliario": (
        _C_VITE_SUPABASE
        + "        VITE_CORE_API_URL: ${VITE_CORE_API_URL:-}\n"
        "        VITE_CORE_URL: ${VITE_CORE_URL:-}\n"
    ),
    "knowledge-extractor": (
        _C_VITE_SUPABASE
        + "        VITE_CORE_API_URL: ${VITE_CORE_API_URL:-}\n"
        "        VITE_CORE_URL: ${VITE_CORE_URL:-}\n"
    ),
}


# ── per-product compose volume extras (injected after the seed-lib FE
# node_modules anchor) ─────────────────────────────────────────────────────
# core is the control-plane product: its admin-only Fleet Control panel needs
# the host docker socket. The seed compose has no socket (correctly — no other
# product gets one), so without this hook core's compose would perpetually
# read as `stale` vs seed and a blanket re-propagate would STRIP the mount.
# Formalized 2026-05-24 (was accept-with-rationale): the pre-commit propagate
# gate fires on any staged seed-docker change, so the hand-restore workaround
# couldn't survive a seed Dockerfile commit. Mirrors the Dockerfile `_D_EXTRA`.
_C_VOLUME_ANCHOR = "      - /app/seed/lib/frontend/node_modules\n"
_C_CORE_DOCKER_SOCK = (
    "      # CONTROL-PLANE: core's admin-only \"Fleet Control\" panel switches sibling\n"
    "      # product containers ON/OFF via the seed primitive\n"
    "      # noctusai_lib.domain.fleet_control (the same shape in dev + prod). It\n"
    "      # talks to THIS host's docker via the socket. Mounted read-only (:ro) —\n"
    "      # the seed controller only ever runs `docker ps` + `docker\n"
    "      # {start|stop|restart} noctus-<slug>` against a HARD allowlist, and every\n"
    "      # endpoint is gated by core's get_current_admin. Core ONLY (control-plane\n"
    "      # product) — do NOT propagate this mount to other products.\n"
    "      - /var/run/docker.sock:/var/run/docker.sock:ro\n"
)
_C_VOLUME_EXTRA: dict[str, str] = {"core": _C_CORE_DOCKER_SOCK}


# ── per-product compose hardening extras (roadmap julia-agents-academia-
# 2026-09, row D1) — injected after the healthcheck's `start_period` line,
# before the tunnel service. Scoped to the two D1 slugs deliberately (N=2,
# triage-not-formalize per KB § PATTERNS/architect/project-execution.md):
# `read_only`+`tmpfs` need a per-product proof of every genuine write path
# (§B.6's multipart import spool for academia; the Julia CLI's HOME for
# agents), which the rest of the fleet has not been individually audited
# for yet. Fleet-wide hardening is a separate, larger decision (architect),
# not something this slice extends to by default. Mirrors the `_C_VOLUME_EXTRA`
# hook shape exactly — a blanket re-propagate can never silently strip this.
_C_HARDENING_ANCHOR_TPL = "      start_period: 20s\n\n  {slug}-tunnel:\n"
_C_HARDENING_ACADEMIA = (
    "    # D1 hardening (roadmap julia-agents-academia-2026-09, row D1).\n"
    "    # Prod is first contact for this image (dev fleet dormant — KB §\n"
    "    # PATTERNS/devops/dev-fleet-dormant.md), so the deploy shape carries\n"
    "    # this from day one rather than bolting it on at cutover.\n"
    "    cap_drop:\n"
    "      - ALL\n"
    "    security_opt:\n"
    "      - no-new-privileges:true\n"
    "    read_only: true\n"
    "    # /tmp only, and only because it is genuinely needed: Starlette's\n"
    "    # multipart parser (POST /api/import, contract §B.6) spools any\n"
    "    # part over 1MB to a tempfile.SpooledTemporaryFile under the\n"
    "    # process's tmp dir (verified live against the installed starlette\n"
    "    # 0.49.3: formparsers.MultiPartParser.spool_max_size == 1024*1024),\n"
    "    # and the contract caps a bundle at 20MB — every real import\n"
    "    # spills to disk. mode=1777 mirrors standard /tmp semantics\n"
    "    # (world-writable + sticky bit) so the `noctus` app user can\n"
    "    # create its own spill files without a broader writable root.\n"
    "    tmpfs:\n"
    "      - /tmp:mode=1777,size=64m\n"
    "    mem_limit: 512m\n"
)
# agents' D1 hardening (roadmap julia-agents-academia-2026-09, row D1) —
# revised 2026-09-14 (tech-lead + security-advisor review, ACCEPT-WITH-
# CHANGES over the first cut) against a REAL container reproducing these
# exact flags. Kept as ONE block so a future prod compose entry at cutover
# reuses it verbatim (never hand-copied) — see `_C_HARDENING_EXTRA` above.
_C_HARDENING_AGENTS = (
    "    # D1 hardening (roadmap julia-agents-academia-2026-09, row D1;\n"
    "    # tech-lead + security-advisor review 2026-09-14). Prod is first\n"
    "    # contact for this image (dev fleet dormant — KB § PATTERNS/devops/\n"
    "    # dev-fleet-dormant.md). `bin/entrypoint.sh` FAILS CLOSED if any of\n"
    "    # these three are missing — verified empirically, not asserted.\n"
    "    cap_drop:\n"
    "      - ALL\n"
    "    # SETUID/SETGID/KILL — nothing else. contract §E.5 spawns the Julia\n"
    "    # CLI subprocess under a DIFFERENT, dedicated uid\n"
    "    # (`user=\"julia-cli\"` on ClaudeAgentOptions); dropping to that uid\n"
    "    # AT EXEC (`bin/entrypoint.sh`'s own `setpriv`, not a bare `USER`\n"
    "    # directive — verified empirically that `USER` alone never\n"
    "    # populates AMBIENT caps for a non-root process, moby#45491) needs\n"
    "    # CAP_SETUID + CAP_SETGID effective on the process making that\n"
    "    # switch. CAP_KILL: `noctus` must be able to signal the Julia CLI\n"
    "    # subprocess (uid 1001, a DIFFERENT uid) on turn-timeout/SDK-close —\n"
    "    # verified empirically that signalling a different uid without it\n"
    "    # is denied (EPERM), leaking a hung CLI process for the container's\n"
    "    # whole lifetime. NOT CAP_SETPCAP: every `setpriv --bounding-set=`\n"
    "    # clause was removed from every script in this image (wrapper +\n"
    "    # entrypoint) — verified empirically that it needs CAP_SETPCAP\n"
    "    # (`setpriv: apply bounding set: Operation not permitted`), and\n"
    "    # `cap_drop`/`cap_add` already fix the bounding-set ceiling with\n"
    "    # zero in-container action needed; `no-new-privileges` keeps the\n"
    "    # leftover bounding bits inert regardless.\n"
    "    cap_add:\n"
    "      - SETUID\n"
    "      - SETGID\n"
    "      - KILL\n"
    "    security_opt:\n"
    "      - no-new-privileges:true\n"
    "    read_only: true\n"
    "    # A dedicated tmpfs for the Julia CLI's own HOME/TMPDIR — owned by\n"
    "    # `julia-cli` (uid/gid 1001) alone, mode 0700: `noctus` cannot read\n"
    "    # or write into it, and `julia-cli` cannot read or write this\n"
    "    # product's `/tmp` (below) — verified empirically both ways.\n"
    "    # size-capped; the CLI's own scratch needs are small.\n"
    "    #\n"
    "    # This product's `/tmp` belongs to `noctus` ONLY —\n"
    "    # uid=0,gid=1000,mode=1770 (owner root rwx, group `noctus` rwx +\n"
    "    # sticky, other/`julia-cli` NO access at all). agents has no\n"
    "    # multipart-upload route (unlike academia's `/tmp:mode=1777`, kept\n"
    "    # as-is there — see `_C_HARDENING_ACADEMIA`'s own comment), so\n"
    "    # nothing needs `/tmp` to be world-writable here, and locking it to\n"
    "    # `noctus` closes the one path `julia-cli` could otherwise have\n"
    "    # used to leave a file `noctus` might later trust.\n"
    "    tmpfs:\n"
    "      - /run/julia:uid=1001,gid=1001,mode=0700,size=32m\n"
    "      - /tmp:mode=1770,uid=0,gid=1000,size=64m\n"
    "    # A small explicit /dev/shm — python/uvicorn have no real shared-\n"
    "    # memory need here; explicit + small beats an unexamined default.\n"
    "    shm_size: 64m\n"
    "    mem_limit: 1g\n"
    "    # `init: true` — a minimal PID-1 init (tini) reaps zombies from the\n"
    "    # Julia CLI subprocess tree so a killed-but-unreaped child (see\n"
    "    # `bin/entrypoint.sh`'s CAP_KILL comment above) never accumulates;\n"
    "    # without it `noctus` (not PID 1 here — the entrypoint execs INTO\n"
    "    # it, so it IS PID 1) would have to reap its own children, which\n"
    "    # the SDK's client-close path already does on the happy path but\n"
    "    # should not be the ONLY thing standing between a hung turn and a\n"
    "    # zombie leak.\n"
    "    init: true\n"
    "    # AGENTS_INSTANCE_ID (contract §E.9, roadmap D1) is deliberately\n"
    "    # left UNSET here, not baked as a fixed literal: `app/runtime/\n"
    "    # __init__.py::_resolve_instance_id` already prefers an explicit\n"
    "    # env override and falls back to `HOSTNAME`, which Docker sets to\n"
    "    # this container's own id. That id is stable across a `docker\n"
    "    # restart` of THIS container (satisfying \"stable across restarts\n"
    "    # of the same container\") and changes only when a genuinely NEW\n"
    "    # container is created on redeploy — which is correctly a new\n"
    "    # instance for the startup orphan-sweep (contract §E.2 security\n"
    "    # finding 5), not a bug. Set AGENTS_INSTANCE_ID explicitly only if\n"
    "    # a future orchestrator stops giving the container a stable\n"
    "    # hostname (e.g. Swarm/K8s pod churn).\n"
)
_C_HARDENING_EXTRA: dict[str, str] = {
    "academia-de-reciclagem": _C_HARDENING_ACADEMIA,
    "agents": _C_HARDENING_AGENTS,
}


def _render_compose(canon: str, slug: str, port: str) -> str:
    """Reproduce propagate-composes.sh substitutions EXACTLY, in order."""
    s = canon
    # tunnel target first (carries both slug + port)
    s = s.replace("http://seed:8004", f"http://{slug}:{port}")
    # container/image/tunnel-container names
    s = s.replace("noctus-seed", f"noctus-{slug}")
    # build dockerfile path
    s = s.replace("products/seed/", f"products/{slug}/")
    # tunnel profile
    s = s.replace("tunnel-seed", f"tunnel-{slug}")
    # tunnel SERVICE KEY (2-space indent) — before the bare seed: rule
    s = s.replace("\n  seed-tunnel:\n", f"\n  {slug}-tunnel:\n")
    # service key (2-space indent) + depends_on ref (6-space indent)
    s = s.replace("\n  seed:\n", f"\n  {slug}:\n")
    s = s.replace("\n      seed:\n", f"\n      {slug}:\n")
    # ports + healthcheck port
    s = s.replace("8004", port)
    # per-product VITE args
    s = s.replace(_C_VITE_SEED, _C_VITE.get(slug, _C_VITE_SEED))
    # header note
    s = s.replace(
        "Canonical per-product compose fragment — SINGLE CONTAINER.",
        f"{slug} compose — SINGLE CONTAINER (generated from "
        f"products/seed/docker-compose.yml; edit there + re-propagate).",
    )
    # per-product compose volume extras (e.g. core's control-plane docker.sock)
    extra = _C_VOLUME_EXTRA.get(slug)
    if extra:
        s = s.replace(_C_VOLUME_ANCHOR, _C_VOLUME_ANCHOR + extra, 1)
    # per-product compose hardening extras (roadmap D1) — anchor built with
    # the ALREADY-substituted slug since the seed/{slug}-tunnel rename above
    # has already run by this point.
    hardening = _C_HARDENING_EXTRA.get(slug)
    if hardening:
        anchor = _C_HARDENING_ANCHOR_TPL.format(slug=slug)
        s = s.replace(anchor, f"      start_period: 20s\n{hardening}\n  {slug}-tunnel:\n", 1)
    return s


# ── Dockerfile substitution constants (verbatim from propagate-dockerfiles.sh)
_D_VITE_SUPABASE = (
    "ARG VITE_SUPABASE_URL=\nENV VITE_SUPABASE_URL=${VITE_SUPABASE_URL}\n"
    "ARG VITE_SUPABASE_PUBLISHABLE_KEY=\n"
    "ENV VITE_SUPABASE_PUBLISHABLE_KEY=${VITE_SUPABASE_PUBLISHABLE_KEY}\n"
)
_D_VITE_SEED = (
    _D_VITE_SUPABASE + "ARG VITE_CORE_URL=\nENV VITE_CORE_URL=${VITE_CORE_URL}\n"
)
_D_VITE: dict[str, str] = {
    "core": _D_VITE_SUPABASE
    + "ARG VITE_CORE_API_URL=\nENV VITE_CORE_API_URL=${VITE_CORE_API_URL}\n",
    "erp-imobiliario": (
        _D_VITE_SUPABASE
        + "ARG VITE_CORE_API_URL=\nENV VITE_CORE_API_URL=${VITE_CORE_API_URL}\n"
        "ARG VITE_CORE_URL=\nENV VITE_CORE_URL=${VITE_CORE_URL}\n"
    ),
    "knowledge-extractor": (
        _D_VITE_SUPABASE
        + "ARG VITE_CORE_API_URL=\nENV VITE_CORE_API_URL=${VITE_CORE_API_URL}\n"
        "ARG VITE_CORE_URL=\nENV VITE_CORE_URL=${VITE_CORE_URL}\n"
    ),
}
_D_EXTRA_MARKER = (
    "# {{BACKEND_EXTRA}} — product extras (e.g. dev-team: COPY dev_team +\n"
    "# pip install -e /opt/dev_team). Seed has none.\n"
)
_D_DEVTEAM_EXTRA = (
    "# dev-team: the agno engine, editable-installed alongside the product.\n"
    "COPY dev_team /opt/dev_team\n"
    "RUN --mount=type=cache,target=/root/.cache/pip pip install -e /opt/dev_team\n"
)
_D_KE_EXTRA = (
    "# knowledge-extractor: ffmpeg — system dep for audio extraction/chunking\n"
    "# (app/integrations/media/audio.py). Not a pip package.\n"
    "RUN apt-get update \\\n"
    "    && apt-get install -y --no-install-recommends ffmpeg \\\n"
    "    && rm -rf /var/lib/apt/lists/*\n"
)
# agents: Julia's dedicated non-login uid + the CLI she is launched through
# (contract projects/julia-agents-academia-CONTRACT.md §E.5, SEC-A/SEC-C;
# roadmap D1, tech-lead + security-advisor review 2026-09-14 — the
# ACCEPT-WITH-CHANGES pass over the first cut). Injected as root, before
# the non-root-user step below.
_D_AGENTS_EXTRA = (
    "# agents: Julia's dedicated non-login uid + the CLI she is launched\n"
    "# through (contract §E.5, SEC-A/SEC-C; roadmap D1). `--no-create-home`:\n"
    "# there is no home dir to protect (nothing is ever baked there) — the\n"
    "# wrapper points HOME/TMPDIR at a dedicated tmpfs instead (compose\n"
    "# `tmpfs: [/run/julia]`, uid/gid-owned by this uid — this product's\n"
    "# `/tmp` belongs to `noctus` only).\n"
    "RUN useradd --system --no-create-home --shell /usr/sbin/nologin \\\n"
    "        --uid 1001 --user-group julia-cli\n"
    "\n"
    "# Bundled Claude Code CLI — NOT a `curl .../install.sh | bash` step\n"
    "# (tech-lead review 2026-09-14: unpinned, pulled at build time, drifts\n"
    "# from the SDK pin) and NOT `npm install -g @anthropic-ai/claude-code`\n"
    "# (the slim deploy `runtime` target ships no Node — see `runtime-watch`\n"
    "# below). `claude-agent-sdk==0.2.152`'s manylinux wheels (x86_64 AND\n"
    "# aarch64) already ship a version-matched, self-contained binary at\n"
    "# `claude_agent_sdk/_bundled/claude` (~200MB, already mode 0755\n"
    "# root:root from `pip install` running as root, before the non-root\n"
    "# step below — verified live). Resolved via python, not a second\n"
    "# hardcoded path literal, and `test -x` fails the BUILD (not a live\n"
    "# Julia turn) the day a future SDK bump relocates or drops it. The\n"
    "# symlink is what makes the wrapper's own hardcoded exec target a\n"
    "# stable literal that never needs to track the exact venv/\n"
    "# site-packages path (no `JULIA_CLAUDE_BIN` env seam — dropped\n"
    "# deliberately, see `bin/julia-cli-exec`'s own header comment).\n"
    "RUN CLAUDE_BUNDLED=\"$(python3 -c 'import claude_agent_sdk, pathlib; "
    "print(pathlib.Path(claude_agent_sdk.__file__).parent / \"_bundled\" / \"claude\")')\" \\\n"
    "    && test -x \"$CLAUDE_BUNDLED\" || { echo \"bundled claude CLI not found/executable "
    "at $CLAUDE_BUNDLED (claude-agent-sdk version drift?)\" >&2; exit 1; } \\\n"
    "    && ln -s \"$CLAUDE_BUNDLED\" /usr/local/bin/claude-bundled\n"
    "\n"
    "# The wrapper + entrypoint (contract §E.5, SEC-A/SEC-C) — placed here\n"
    "# (root context, BEFORE the non-root-user step below) so a plain COPY\n"
    "# lands them root:root by Docker's default. Their FINAL ownership/mode\n"
    "# is reasserted after the canonical `chown -R noctus:noctus /app` a\n"
    "# few lines down — that recursive chown would otherwise flip them to\n"
    "# `noctus`, silently undoing \"root-owned, not app-writable\" (see the\n"
    "# ownership reassertion a few lines down — that same block also drops\n"
    "# the canonical `USER noctus` for this product only; see the\n"
    "# ENTRYPOINT at the bottom).\n"
    "COPY products/agents/backend/bin/julia-cli-exec /app/bin/julia-cli-exec\n"
    "COPY products/agents/backend/bin/entrypoint.sh /app/bin/entrypoint.sh\n"
    "\n"
    "# Strip every setuid/setgid bit in the image (roadmap D1) — defence in\n"
    "# depth ORTHOGONAL to the capability model above: a setuid/setgid file\n"
    "# (Debian ships several by default, e.g. `su`/`mount`/`passwd`) grants\n"
    "# privilege via the FILE's own bits, independent of the calling\n"
    "# process's capability set — our `cap_drop`/`cap_add` restrictions say\n"
    "# nothing about what a setuid-root binary could still do if exec'd.\n"
    "# None of these binaries are used by this product at runtime (uvicorn/\n"
    "# python + the two scripts above only).\n"
    "RUN find / -xdev -perm /6000 -type f -exec chmod a-s {} + || true\n"
)
# slug → backend-stage extra injected at the seed's {{BACKEND_EXTRA}} marker.
_D_EXTRA: dict[str, str] = {
    "dev-team": _D_DEVTEAM_EXTRA,
    "knowledge-extractor": _D_KE_EXTRA,
    "agents": _D_AGENTS_EXTRA,
}
# The canonical non-root-user step (`useradd -m -u 1000 noctus && chown -R
# noctus:noctus /app` then `USER noctus`) is a RECURSIVE chown that runs
# AFTER `_D_EXTRA`'s injection point — so it silently flips ANY file
# `_D_EXTRA` placed under /app back to `noctus`. agents needs two
# exceptions here, both load-bearing and both verified empirically against
# a real container (tech-lead + security-advisor review 2026-09-14, not
# theorized):
#
# 1. The wrapper AND the entrypoint must end up root-owned, not
#    noctus-owned — this hook appends a re-assertion to the SAME `RUN` as
#    the canonical chown, immediately after it, in the SAME layer (no
#    extra layer, no window where either file is transiently
#    noctus-owned).
# 2. NO trailing `USER noctus` for this product. Docker only carries a
#    compose `cap_add` into a non-root process through the AMBIENT
#    capability set, and a plain `USER noctus` directive does NOT
#    populate that set — confirmed by reproducing the exact compose
#    hardening flags against a real container: `USER noctus` alone leaves
#    CapEff/CapAmb at zero, so the SDK's `Popen(user="julia-cli")`
#    subprocess spawn gets PermissionError on every Julia turn
#    (moby#45491, moby PR#36587). The container instead stays root all the
#    way to the ENTRYPOINT (see `_D_ENTRYPOINT_OVERRIDE` below), which
#    itself fails closed (refuses to drop privilege at all unless the
#    compose hardening is actually in effect) and only THEN uses `setpriv`
#    to do the root->noctus switch AT EXEC, which DOES populate ambient
#    caps as part of that one transition.
#    `check_product_container_shape` does not assert `USER noctus`
#    anywhere (only the base-seam/runtime-watch/SERVE_SPA_DIR markers),
#    so this needs no keeper change — verified against the real keeper.
_D_POST_CHOWN_ANCHOR = "RUN useradd -m -u 1000 noctus && chown -R noctus:noctus /app\nUSER noctus\n"
_D_AGENTS_POST_CHOWN = (
    "RUN useradd -m -u 1000 noctus && chown -R noctus:noctus /app \\\n"
    "    && chown root:root /app/bin/julia-cli-exec /app/bin/entrypoint.sh \\\n"
    "    && chmod 0755 /app/bin/julia-cli-exec /app/bin/entrypoint.sh\n"
    "# No `USER noctus` here (deviates from the canonical shape, agents-only,\n"
    "# roadmap D1): the ENTRYPOINT below does the uid switch AT EXEC via\n"
    "# `setpriv` instead, which is what actually populates AMBIENT caps for\n"
    "# the SDK's `Popen(user=\"julia-cli\")` subprocess spawn — a plain\n"
    "# `USER noctus` directive here does not (verified empirically,\n"
    "# moby#45491/PR#36587).\n"
)
_D_POST_CHOWN_EXTRA: dict[str, str] = {"agents": _D_AGENTS_POST_CHOWN}

# slug → full CMD replacement, upgraded to an ENTRYPOINT override (roadmap
# D1, tech-lead + security-advisor review 2026-09-14). agents ONLY. The
# entrypoint (`bin/entrypoint.sh`, root:root) does two things the
# canonical plain-uvicorn CMD cannot:
#   1. FAILS CLOSED — refuses to even attempt the privilege drop unless
#      uid==0, NoNewPrivs==1, CapBnd is EXACTLY {SETUID,SETGID,KILL}
#      (0xE0), and a root-fs write attempt fails. A future compose edit
#      that silently drops `cap_drop`/`no-new-privileges`/`read_only`
#      must not fall back to "runs anyway, less isolated" — verified
#      empirically: each of the three flags removed individually makes
#      the container refuse to start, with a clear reason on stderr.
#   2. `setpriv --reuid=noctus --regid=noctus ... --ambient-caps=-all,
#      +setuid,+setgid,+kill -- uvicorn ... --workers 1` — the actual
#      root->noctus privilege drop, done AT EXEC so ambient caps end up
#      populated (see `_D_AGENTS_POST_CHOWN` above for why a plain `USER
#      noctus` cannot do this). `+kill`: `noctus` must be able to signal
#      the Julia CLI subprocess (uid 1001, a DIFFERENT uid) on
#      turn-timeout/SDK-close — verified empirically that this needs
#      CAP_KILL (a same-uid-only signal check otherwise denies it), and
#      that a killed different-uid child shows as a transient ZOMBIE in
#      `/proc`, not an immediate disappearance — the D1 report's kill test
#      checks `/proc/<pid>/stat` state, never bare existence. `--workers
#      1`: contract §E.9's approval wake-up is in-process (a pending
#      `approvals` row is resolved by the SAME worker that is awaiting
#      it); a second uvicorn worker would split conversations across
#      processes with no shared wake-up channel, silently orphaning
#      approvals (roadmap trigger T6 tracks lifting this). No
#      `--bounding-set=` clause anywhere in this product's setpriv calls:
#      verified empirically that it needs CAP_SETPCAP (`setpriv: apply
#      bounding set: Operation not permitted`), which is deliberately NOT
#      in `cap_add`; the compose-level `cap_drop`/`cap_add` already fixes
#      the bounding-set ceiling, and `--no-new-privs` keeps the leftover
#      bounding bits inert (nothing can ever re-raise them without
#      CAP_SETPCAP).
_D_ENTRYPOINT_OVERRIDE: dict[str, str] = {
    "agents": (
        '# ENTRYPOINT replaces the canonical plain-uvicorn CMD (roadmap D1)\n'
        "# — a root:root, fail-closed script; see `bin/entrypoint.sh`'s own\n"
        "# header for exactly what it refuses to boot without, and why the\n"
        "# container stays root through this line (no `USER noctus` above)\n"
        "# so its own `setpriv` can populate AMBIENT caps as it drops to\n"
        "# `noctus`.\n"
        'ENTRYPOINT ["/app/bin/entrypoint.sh"]\n'
    ),
}
# secc-proof (roadmap julia-agents-academia-2026-09, row SEC-C;
# `products/agents/backend/secc/run_proof.py`) — a PROOF-ONLY `FROM runtime`
# stage, inserted right after the ENTRYPOINT line and before the
# runtime-watch stage. agents ONLY: no other product has a Julia-CLI
# subprocess spawn path to prove in CI without a real API key. NEVER
# tagged/pushed/deployed — `run_proof.py`'s own
# `check_build_and_push_never_builds_secc_proof` asserts that statically.
_D_SECC_PROOF_EXTRA: dict[str, str] = {
    "agents": (
        "\n"
        "# ── secc-proof: PROOF-ONLY stage, NEVER tagged/pushed/deployed ──────────\n"
        "# Roadmap julia-agents-academia-2026-09, row SEC-C\n"
        "# (`products/agents/backend/secc/run_proof.py`). CI has no real\n"
        "# `ANTHROPIC_API_KEY` to exercise the Julia CLI subprocess with, so this\n"
        "# stage re-points ONLY `/usr/local/bin/claude-bundled` at a root-owned\n"
        "# probe script (`secc/probe.py`) that dumps its own uid/gid/groups/caps/\n"
        "# env + an EACCES/EPERM access-check battery instead of talking to\n"
        "# Anthropic. `bin/julia-cli-exec` and `bin/entrypoint.sh` are otherwise\n"
        "# BYTE-IDENTICAL to `runtime` (asserted by `run_proof.py` via sha256) —\n"
        "# only the one symlink target changes.\n"
        "# \U0001f534 This stage must NEVER be tagged, pushed, or deployed:\n"
        "# `scripts/infra/build-and-push.sh` / `.github/workflows/build-and-push.yml`\n"
        "# build + push `--target runtime` only, never `secc-proof`\n"
        "# (`run_proof.py`'s `check_build_and_push_never_builds_secc_proof` asserts\n"
        "# this statically on every proof run).\n"
        "FROM runtime AS secc-proof\n"
        "USER root\n"
        "RUN rm -f /usr/local/bin/claude-bundled\n"
        "COPY products/agents/backend/secc/probe.py /usr/local/bin/claude-bundled\n"
        "# probe.py's `#!/usr/bin/env python3` shebang resolves through `env`'s OWN\n"
        "# PATH lookup — and the wrapper's `env -i PATH=/usr/bin:/bin ...` handoff\n"
        "# (bin/julia-cli-exec, unchanged) deliberately does NOT include\n"
        "# `/opt/venv/bin` (the real bundled CLI is a native binary, not a python\n"
        "# script, so it never needed it). Symlinking the venv's python3 onto that\n"
        "# same restricted PATH is proof-harness-only plumbing, not a change to\n"
        "# the allowlist the wrapper actually enforces for the real CLI.\n"
        'RUN ln -sf "$(command -v python3)" /usr/bin/python3 \\\n'
        "    && chown root:root /usr/local/bin/claude-bundled \\\n"
        "    && chmod 0755 /usr/local/bin/claude-bundled\n"
    ),
}
# runtime-watch (LOCAL DEV ONLY — the dev fleet is dormant per
# KB § PATTERNS/devops/dev-fleet-dormant.md, and this is declared rather
# than fixed, per that rule) does NOT inherit SEC-A/SEC-C's isolation:
# this stage's OWN `chown -R noctus:noctus /app` (a few lines down, the
# canonical local-watch node-install step) flips `julia-cli-exec` +
# `entrypoint.sh` back to `noctus`-owned, and its `local-watch`
# ENTRYPOINT overrides the `runtime` stage's `entrypoint.sh` with a plain
# `USER noctus`. Not fixed here: `get_agent_runtime` only ever returns the
# real `ClaudeAgentSdkRuntime` when `ANTHROPIC_API_KEY` is configured, and
# no real key is ever set for local dev (never a live Julia turn to
# isolate in this stage today) — see the D1 report for the explicit
# call-out this comment stands in for.
_D_RUNTIME_WATCH_NOTE: dict[str, str] = {
    "agents": (
        "FROM runtime AS runtime-watch\n"
        "# SEC-A/SEC-C do NOT apply to this stage (roadmap D1, declared not\n"
        "# fixed — dev fleet is dormant): the node-install step below re-runs\n"
        "# `chown -R noctus:noctus /app`, flipping the wrapper/entrypoint back\n"
        "# to `noctus`-owned, and ends on a plain `USER noctus` + the\n"
        "# `local-watch` ENTRYPOINT, not `bin/entrypoint.sh`. Harmless only\n"
        "# because `get_agent_runtime` never returns the real SDK runtime\n"
        "# without a configured `ANTHROPIC_API_KEY`, which local dev never\n"
        "# sets — there is no live Julia turn to isolate in this stage today.\n"
    ),
}
_D_PIP_RUN_SEED = (
    "RUN --mount=type=cache,target=/root/.cache/pip \\\n"
    "    grep -v '^-e seed/' /tmp/requirements.txt > /tmp/req.clean.txt \\\n"
    "    && pip install -r /tmp/req.clean.txt"
)
_D_PIP_RUN: dict[str, str] = {
    "erp-imobiliario": (
        "RUN --mount=type=cache,target=/root/.cache/pip \\\n"
        "    apt-get update \\\n"
        "    && apt-get install -y --no-install-recommends gcc pkg-config libcairo2-dev \\\n"
        "    && grep -v '^-e seed/' /tmp/requirements.txt > /tmp/req.clean.txt \\\n"
        "    && pip install -r /tmp/req.clean.txt \\\n"
        "    && apt-get purge -y gcc pkg-config libcairo2-dev \\\n"
        "    && apt-get autoremove -y \\\n"
        "    && rm -rf /var/lib/apt/lists/*"
    ),
}


def _render_dockerfile(canon: str, slug: str, port: str) -> str:
    """Reproduce propagate-dockerfiles.sh substitutions EXACTLY, in order."""
    s = canon
    s = s.replace("products/seed/", f"products/{slug}/")
    s = s.replace("PRODUCT_SLUG=seed", f"PRODUCT_SLUG={slug}")
    s = s.replace("8004", port)
    s = s.replace(_D_VITE_SEED, _D_VITE.get(slug, _D_VITE_SEED))
    s = s.replace(_D_PIP_RUN_SEED, _D_PIP_RUN.get(slug, _D_PIP_RUN_SEED))
    s = s.replace(_D_EXTRA_MARKER, _D_EXTRA.get(slug, "# (no product extras)\n"))
    s = s.replace(
        "seed — CANONICAL thin product image (the reference every product mirrors).",
        f"{slug} — thin product image (generated from "
        f"products/seed/backend/Dockerfile; edit there + re-propagate).",
    )
    s = s.replace('title="noctus-seed"', f'title="noctus-{slug}"')
    # per-product post-chown ownership fixups (roadmap D1) — see
    # `_D_POST_CHOWN_EXTRA`'s docstring for why this can't just live in
    # `_D_EXTRA` above.
    post_chown = _D_POST_CHOWN_EXTRA.get(slug)
    if post_chown:
        s = s.replace(_D_POST_CHOWN_ANCHOR, post_chown, 1)
    # per-product ENTRYPOINT override (roadmap D1) — built against the
    # ALREADY-substituted port/slug (every earlier substitution has run by
    # this point). See `_D_ENTRYPOINT_OVERRIDE`'s docstring for what/why.
    # `bin/entrypoint.sh` hardcodes this product's own port/app-dir
    # directly (it is a plain, agents-only committed file, same as
    # `bin/julia-cli-exec` — never templated), so this is a straight
    # CMD -> ENTRYPOINT line swap, no port/slug substitution needed here.
    entrypoint_override = _D_ENTRYPOINT_OVERRIDE.get(slug)
    if entrypoint_override:
        anchor = (
            "# Default CMD = plain uvicorn over the BAKED dist → this image is a\n"
            "# self-contained, shippable artifact (deploy/CI run it as-is).\n"
            'CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", \\\n'
            f'     "--port", "{port}", "--app-dir", "products/{slug}/backend"]\n'
        )
        s = s.replace(anchor, entrypoint_override, 1)
    # per-product secc-proof stage (roadmap SEC-C) — inserted right after
    # the (already-substituted) ENTRYPOINT line, before the runtime-watch
    # substitution below. See `_D_SECC_PROOF_EXTRA`'s docstring.
    secc_proof_extra = _D_SECC_PROOF_EXTRA.get(slug)
    if secc_proof_extra:
        entrypoint_anchor = 'ENTRYPOINT ["/app/bin/entrypoint.sh"]\n'
        s = s.replace(entrypoint_anchor, entrypoint_anchor + secc_proof_extra, 1)
    # runtime-watch disclosure (roadmap D1) — see `_D_RUNTIME_WATCH_NOTE`'s
    # docstring for why this is declared, not fixed.
    rw_note = _D_RUNTIME_WATCH_NOTE.get(slug)
    if rw_note:
        s = s.replace("FROM runtime AS runtime-watch\n", rw_note, 1)
    return s


def _resolve_root(repo_root: str | None, worktree_path: str | None) -> pathlib.Path:
    """`repo_root` (explicit tree, mirrors the script's `cd $REPO_ROOT`)
    wins; else a genuine git `worktree_path`; else `REPO_ROOT`."""
    if repo_root is not None:
        return pathlib.Path(repo_root)
    if worktree_path:
        return pathlib.Path(resolve_caller_root(worktree_path))
    return pathlib.Path(REPO_ROOT)


def _propagate(
    *,
    kind: str,
    canon_rel: str,
    out_rel_tpl: str,
    renderer,
    dry: bool,
    check: bool,
    repo_root: str | None,
    worktree_path: str | None,
) -> dict[str, Any]:
    """Shared engine for both codegens. Mirrors the script loop exactly:
    `check` reports STALE (no write); `dry` reports planned writes (no
    write); default WRITES every regenerated file."""
    root = _resolve_root(repo_root, worktree_path)
    canon_path = root / canon_rel
    if not canon_path.exists():
        return {
            "ok": False,
            "kind": kind,
            "error": f"canonical {canon_rel} not found at {canon_path}",
            "executed": False,
        }
    canon = canon_path.read_text()

    stale: list[str] = []
    written: list[str] = []
    planned: list[str] = []
    for slug, port in PRODUCTS:
        rendered = renderer(canon, slug, port)
        out = root / out_rel_tpl.format(slug=slug)
        rel = out_rel_tpl.format(slug=slug)
        if check:
            if not out.exists() or out.read_text() != rendered:
                stale.append(rel)
        elif dry:
            if not out.exists() or out.read_text() != rendered:
                planned.append(rel)
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(rendered)
            written.append(rel)

    if check:
        return {
            "ok": True,
            "kind": kind,
            "mode": "check",
            "status": "stale" if stale else "in-sync",
            "stale": stale,
            "exit_code": 1 if stale else 0,
            "products": [s for s, _ in PRODUCTS],
        }
    if dry:
        return {
            "ok": True,
            "kind": kind,
            "mode": "dry",
            "status": "drift" if planned else "in-sync",
            "planned_writes": planned,
            "wrote": [],
            "products": [s for s, _ in PRODUCTS],
        }
    return {
        "ok": True,
        "kind": kind,
        "mode": "write",
        "status": "written",
        "wrote": written,
        "ports": {s: p for s, p in PRODUCTS},
        "products": [s for s, _ in PRODUCTS],
    }


def propagate_composes(
    dry: bool = False,
    check: bool = False,
    repo_root: str | None = None,
    worktree_path: str | None = None,
) -> dict[str, Any]:
    """Regenerate every product's `docker-compose.yml` from the canonical
    `products/seed/docker-compose.yml`. Byte-identical to
    scripts/propagate-composes.sh. `check` mirrors its `--check`; `dry`
    reports planned writes only (no `--dry` in the script — safer MCP
    default, non-dry stays parity-faithful). `repo_root` overrides the
    tree (mirrors the script's `cd $REPO_ROOT`)."""
    return _propagate(
        kind="composes",
        canon_rel="products/seed/docker-compose.yml",
        out_rel_tpl="products/{slug}/docker-compose.yml",
        renderer=_render_compose,
        dry=dry,
        check=check,
        repo_root=repo_root,
        worktree_path=worktree_path,
    )


def propagate_dockerfiles(
    dry: bool = False,
    check: bool = False,
    repo_root: str | None = None,
    worktree_path: str | None = None,
) -> dict[str, Any]:
    """Regenerate every product's `backend/Dockerfile` from the canonical
    `products/seed/backend/Dockerfile`. Byte-identical to
    scripts/propagate-dockerfiles.sh. `check` mirrors its `--check`; `dry`
    reports planned writes only (no `--dry` in the script — safer MCP
    default, non-dry stays parity-faithful). `repo_root` overrides the
    tree (mirrors the script's `cd $REPO_ROOT`)."""
    return _propagate(
        kind="dockerfiles",
        canon_rel="products/seed/backend/Dockerfile",
        out_rel_tpl="products/{slug}/backend/Dockerfile",
        renderer=_render_dockerfile,
        dry=dry,
        check=check,
        repo_root=repo_root,
        worktree_path=worktree_path,
    )


def register(server) -> None:
    @server.tool(
        name="noctus.dev.propagate",
        description=(
            "Containerization codegen — regenerate per-product "
            "docker-compose.yml / backend Dockerfile from the canonical "
            "products/seed/ single-container shape (byte-identical to the "
            "former scripts/propagate-{composes,dockerfiles}.sh). "
            "`target='composes'|'dockerfiles'|'both'` (default 'both'). "
            "`check=True` reports STALE files (status='stale', no write — "
            "the scripts' --check, used by the pre-commit drift gate). "
            "`dry=True` reports planned writes (no write). Default WRITES "
            "every regenerated file. Pass worktree_path when called from "
            "inside a git worktree. See KB § PATTERNS/containerization.md."
        ),
    )
    def _propagate_tool(
        target: str = "both",
        dry: bool = False,
        check: bool = False,
        worktree_path: str | None = None,
    ) -> dict:
        if target == "composes":
            return propagate_composes(dry=dry, check=check, worktree_path=worktree_path)
        if target == "dockerfiles":
            return propagate_dockerfiles(
                dry=dry, check=check, worktree_path=worktree_path
            )
        c = propagate_composes(dry=dry, check=check, worktree_path=worktree_path)
        d = propagate_dockerfiles(dry=dry, check=check, worktree_path=worktree_path)
        return {
            "ok": c["ok"] and d["ok"],
            "target": "both",
            "composes": c,
            "dockerfiles": d,
            "status": (
                "stale"
                if "stale" in (c.get("status"), d.get("status"))
                else "drift"
                if "drift" in (c.get("status"), d.get("status"))
                else c.get("status")
            ),
        }


__all__ = [
    "propagate_composes",
    "propagate_dockerfiles",
    "PRODUCTS",
    "register",
]
