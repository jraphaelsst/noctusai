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

# slug → backend port. Mirrors vite.config.factory PRODUCT_MAP + start.sh.
# Frozen verbatim from scripts/propagate-{composes,dockerfiles}.sh — the
# scripts hardcode this identical list; parity requires the same set/order.
PRODUCTS: list[tuple[str, str]] = [
    ("core", "8000"),
    ("erp-imobiliario", "8001"),
    ("personal-finance", "8002"),
    ("therapy-platform", "8003"),
    ("daily-life", "8005"),
    ("adconnect", "8007"),
    ("dev-team", "8009"),
    ("social-wiring", "8011"),
    ("knowledge-extractor", "8012"),
]

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
# slug → backend-stage extra injected at the seed's {{BACKEND_EXTRA}} marker.
_D_EXTRA: dict[str, str] = {
    "dev-team": _D_DEVTEAM_EXTRA,
    "knowledge-extractor": _D_KE_EXTRA,
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
