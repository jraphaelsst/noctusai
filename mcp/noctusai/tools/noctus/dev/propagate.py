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
_C_HARDENING_AGENTS = (
    "    # D1 hardening (roadmap julia-agents-academia-2026-09, row D1).\n"
    "    # Prod is first contact for this image (dev fleet dormant — KB §\n"
    "    # PATTERNS/devops/dev-fleet-dormant.md).\n"
    "    cap_drop:\n"
    "      - ALL\n"
    "    # SETUID/SETGID ONLY: contract §E.5 spawns the Julia CLI subprocess\n"
    "    # under a DIFFERENT, dedicated uid (`user=\"julia-cli\"` on\n"
    "    # ClaudeAgentOptions). Verified live against the installed SDK:\n"
    "    # subprocess_cli.py passes `user=` through to `anyio.open_process`\n"
    "    # -> `subprocess.Popen(user=...)`, whose POSIX exec path needs\n"
    "    # CAP_SETUID (+ CAP_SETGID for the implicit initgroups() call when\n"
    "    # no explicit `group=` is given) in the PARENT app process's\n"
    "    # capability set to drop from `noctus` into `julia-cli`. Dropping\n"
    "    # ALL caps without adding these back would silently break every\n"
    "    # Julia turn the first time the SDK tries to spawn the CLI\n"
    "    # (PermissionError) — exactly the silent-regression shape this\n"
    "    # hardening slice must not introduce.\n"
    "    cap_add:\n"
    "      - SETUID\n"
    "      - SETGID\n"
    "    security_opt:\n"
    "      - no-new-privileges:true\n"
    "    read_only: true\n"
    "    # /tmp only: the julia-cli-exec wrapper (contract §E.5) sets\n"
    "    # HOME=/tmp/julia-home for the CLI subprocess. mode=1777 (standard\n"
    "    # /tmp semantics) lets the `julia-cli` uid create that directory\n"
    "    # itself on first use, without granting it — or `noctus` — any\n"
    "    # broader writable root.\n"
    "    tmpfs:\n"
    "      - /tmp:mode=1777,size=64m\n"
    "    mem_limit: 1g\n"
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
# roadmap D1). Injected as root, before the non-root-user step below.
_D_AGENTS_EXTRA = (
    "# agents: Julia's dedicated non-login uid + the CLI she is launched\n"
    "# through (contract §E.5, SEC-A/SEC-C; roadmap D1). `--no-create-home`:\n"
    "# there is no home dir to protect (nothing is ever baked there) — the\n"
    "# wrapper points HOME at an ephemeral tmpfs path instead (compose\n"
    "# `tmpfs: [/tmp]`). A distinct uid from `noctus` is what lets the\n"
    "# container drop capabilities down to CAP_SETUID/CAP_SETGID only\n"
    "# (compose `cap_add`) while still giving the SDK's `user=\"julia-cli\"`\n"
    "# subprocess spawn a real uid boundary — /proc/<julia-cli-pid>/environ\n"
    "# is unreadable to any other uid in the container, kernel-enforced,\n"
    "# never app code.\n"
    "RUN useradd --system --no-create-home --shell /usr/sbin/nologin \\\n"
    "        --uid 1001 --user-group julia-cli\n"
    "\n"
    "# Native Claude Code CLI install — deliberately NOT\n"
    "# `npm install -g @anthropic-ai/claude-code`: the slim deploy\n"
    "# `runtime` target ships no Node (node is `runtime-watch`-only, see\n"
    "# below), and the native installer is a self-contained binary with no\n"
    "# Node runtime dependency. UNVERIFIED against a real network build —\n"
    "# this worktree has no docker daemon (see the D1 report); confirm this\n"
    "# exact invocation the first time this image is actually built, before\n"
    "# it ships (NOC-REMEDIATE[cli-install-verify], closed by SEC-C's\n"
    "# real-image proof).\n"
    "RUN curl -fsSL https://claude.ai/install.sh | bash \\\n"
    "    && install -o root -g root -m 0755 \\\n"
    "         \"$(find /root/.local/bin /root/.claude/local -maxdepth 1 -name claude -print -quit)\" \\\n"
    "         /usr/local/bin/claude\n"
    "ENV JULIA_CLAUDE_BIN=/usr/local/bin/claude\n"
    "\n"
    "# The env -i wrapper itself (contract §E.5) — placed here (root context,\n"
    "# before USER noctus below) so a plain COPY lands it root:root by\n"
    "# Docker's default. Its FINAL ownership/mode is reasserted after the\n"
    "# canonical `chown -R noctus:noctus /app` a few lines down — that\n"
    "# recursive chown would otherwise flip this one file to `noctus`,\n"
    "# silently undoing \"root-owned, not app-writable\" (see the\n"
    "# `_D_POST_CHOWN_EXTRA` hook below).\n"
    "COPY products/agents/backend/bin/julia-cli-exec /app/bin/julia-cli-exec\n"
)
# slug → backend-stage extra injected at the seed's {{BACKEND_EXTRA}} marker.
_D_EXTRA: dict[str, str] = {
    "dev-team": _D_DEVTEAM_EXTRA,
    "knowledge-extractor": _D_KE_EXTRA,
    "agents": _D_AGENTS_EXTRA,
}
# slug → CMD extra arg pair appended to the seed's plain-uvicorn CMD list.
# agents ONLY: contract §E.9 approval wake-up is in-process (a pending
# `approvals` row is resolved by the SAME worker that is awaiting it); a
# second uvicorn worker would split conversations across processes with no
# shared wake-up channel, silently orphaning approvals (roadmap trigger T6
# tracks lifting this). Roadmap D1.
_D_WORKERS_1: frozenset[str] = frozenset({"agents"})

# The canonical non-root-user step (`useradd -m -u 1000 noctus && chown -R
# noctus:noctus /app`) is a RECURSIVE chown that runs AFTER `_D_EXTRA`'s
# injection point — so it silently flips ANY file `_D_EXTRA` placed under
# /app back to `noctus`. agents needs one exception (the julia-cli-exec
# wrapper must end up root-owned, not noctus-owned), so this hook appends
# a re-assertion to the SAME `RUN` as the canonical chown, immediately
# after it, in the SAME layer (no extra layer, no window where the wrapper
# is transiently noctus-owned).
_D_POST_CHOWN_ANCHOR = "RUN useradd -m -u 1000 noctus && chown -R noctus:noctus /app\nUSER noctus\n"
_D_AGENTS_POST_CHOWN = (
    "RUN useradd -m -u 1000 noctus && chown -R noctus:noctus /app \\\n"
    "    && chown root:root /app/bin/julia-cli-exec \\\n"
    "    && chmod 0755 /app/bin/julia-cli-exec\n"
    "USER noctus\n"
)
_D_POST_CHOWN_EXTRA: dict[str, str] = {"agents": _D_AGENTS_POST_CHOWN}
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
    # per-product deploy-CMD extras (roadmap D1) — `--workers 1`, built
    # against the ALREADY-substituted port/slug (every earlier substitution
    # has run by this point).
    if slug in _D_WORKERS_1:
        anchor = (
            'CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", \\\n'
            f'     "--port", "{port}", "--app-dir", "products/{slug}/backend"]\n'
        )
        replacement = (
            'CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", \\\n'
            f'     "--port", "{port}", "--app-dir", "products/{slug}/backend", \\\n'
            '     "--workers", "1"]\n'
        )
        s = s.replace(anchor, replacement, 1)
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
