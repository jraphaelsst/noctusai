"""Colocated tests for noctus.dev.propagate.

Byte-parity is proven against the REAL scripts/propagate-*.sh, not a
re-implementation: build a temp repo (canonical products/seed/ + the real
script copied in), run the MCP function AND the script against separate
temp trees, assert the regenerated files are byte-identical.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import propagate as P  # noqa: E402

REPO = Path(__file__).resolve().parents[3]


def _make_temp_repo(tmp_path: Path, kind: str) -> Path:
    """Copy the real canonical seed file into a throwaway repo root so the
    native propagate fn sees real input. (scripts/propagate-*.sh was
    absorbed into noctus.dev.propagate + deleted — scripts-mcp-absorption
    2026-05-18; byte-parity vs the .sh was proven green at port time, the
    durable check is native idempotency below.)"""
    root = tmp_path / "repo"
    if kind == "composes":
        canon_src = REPO / "products/seed/docker-compose.yml"
        canon_dst = root / "products/seed/docker-compose.yml"
    else:
        canon_src = REPO / "products/seed/backend/Dockerfile"
        canon_dst = root / "products/seed/backend/Dockerfile"
    canon_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(canon_src, canon_dst)
    for slug, _ in P.PRODUCTS:
        (root / "products" / slug / "backend").mkdir(parents=True, exist_ok=True)
    return root


@pytest.mark.parametrize(
    "kind,fn,out_tpl,script",
    [
        (
            "composes",
            P.propagate_composes,
            "products/{slug}/docker-compose.yml",
            "propagate-composes.sh",
        ),
        (
            "dockerfiles",
            P.propagate_dockerfiles,
            "products/{slug}/backend/Dockerfile",
            "propagate-dockerfiles.sh",
        ),
    ],
)
def test_native_deterministic_and_writes(tmp_path, kind, fn, out_tpl, script):
    """Native propagate writes one regenerated file per product and is
    idempotent (regenerate twice → byte-identical). Replaces the former
    byte-parity-vs-`.sh` test (script deleted; parity was proven green at
    port time — scripts-mcp-absorption 2026-05-18)."""
    r1 = _make_temp_repo(tmp_path / "a", kind)
    res = fn(repo_root=str(r1))
    assert res["ok"] is True
    assert res["status"] == "written"
    assert res["wrote"], "expected files written"
    first = {
        slug: (r1 / out_tpl.format(slug=slug)).read_bytes()
        for slug, _ in P.PRODUCTS
    }
    assert len(first) == len(P.PRODUCTS)

    # Idempotent: a second run over a fresh tree yields byte-identical output.
    r2 = _make_temp_repo(tmp_path / "b", kind)
    fn(repo_root=str(r2))
    for slug, _ in P.PRODUCTS:
        assert (r2 / out_tpl.format(slug=slug)).read_bytes() == first[slug], (
            f"non-deterministic output for {slug} ({kind})"
        )


@pytest.mark.parametrize(
    "fn", [P.propagate_composes, P.propagate_dockerfiles]
)
def test_dry_writes_nothing(tmp_path, fn):
    kind = "composes" if fn is P.propagate_composes else "dockerfiles"
    root = _make_temp_repo(tmp_path, kind)
    res = fn(dry=True, repo_root=str(root))
    assert res["ok"] is True
    assert res["mode"] == "dry"
    assert res["status"] == "drift"  # nothing exists yet
    assert res["wrote"] == []
    assert len(res["planned_writes"]) == len(P.PRODUCTS)
    # no PRODUCT files materialized (the seed canonical is the input, not
    # a generated artifact — exclude it)
    for slug, _ in P.PRODUCTS:
        assert not (root / "products" / slug / "docker-compose.yml").exists()
        assert not (root / "products" / slug / "backend" / "Dockerfile").exists()


@pytest.mark.parametrize(
    "fn", [P.propagate_composes, P.propagate_dockerfiles]
)
def test_check_detects_stale_then_in_sync(tmp_path, fn):
    kind = "composes" if fn is P.propagate_composes else "dockerfiles"
    root = _make_temp_repo(tmp_path, kind)
    stale = fn(check=True, repo_root=str(root))
    assert stale["status"] == "stale"
    assert stale["exit_code"] == 1
    assert len(stale["stale"]) == len(P.PRODUCTS)

    fn(repo_root=str(root))  # write
    fresh = fn(check=True, repo_root=str(root))
    assert fresh["status"] == "in-sync"
    assert fresh["exit_code"] == 0
    assert fresh["stale"] == []


@pytest.mark.parametrize(
    "fn", [P.propagate_composes, P.propagate_dockerfiles]
)
def test_missing_canonical(tmp_path, fn):
    res = fn(repo_root=str(tmp_path))
    assert res["ok"] is False
    assert "not found" in res["error"]


# ── per-product extras (compose volumes + Dockerfile backend extras) ────────
# Regression guards for the slug-keyed extras maps: the seed canonical carries
# NONE of these (correctly), so they must be INJECTED for their owning product
# and ABSENT for every other — else a fleet re-propagate silently strips a
# control-plane mount / a system dep. See accept-with-rationale (formalized).
_SOCK = "/var/run/docker.sock:/var/run/docker.sock:ro"


def test_compose_core_gets_docker_sock_others_dont():
    canon = (REPO / "products/seed/docker-compose.yml").read_text()
    assert _SOCK not in canon, "seed compose must NOT carry the host socket"
    core = P._render_compose(canon, "core", "8000")
    assert _SOCK in core, "core compose MUST regenerate WITH the Fleet Control socket"
    # exactly once, anchored right after the seed-lib FE node_modules volume
    assert core.count(_SOCK) == 1
    for slug, port in P.PRODUCTS:
        if slug == "core":
            continue
        assert _SOCK not in P._render_compose(canon, slug, port), (
            f"{slug} compose must NOT get the docker socket (core-only)"
        )


def test_dockerfile_backend_extras_are_product_scoped():
    canon = (REPO / "products/seed/backend/Dockerfile").read_text()
    ke = P._render_dockerfile(canon, "knowledge-extractor", "8012")
    assert "ffmpeg" in ke, "knowledge-extractor MUST get the ffmpeg system dep"
    dt = P._render_dockerfile(canon, "dev-team", "8009")
    assert "COPY dev_team /opt/dev_team" in dt, "dev-team MUST get its editable engine install"
    # a product with no extras gets neither real extra (match the install
    # lines, not the header-comment example that mentions dev_team in all files)
    core = P._render_dockerfile(canon, "core", "8000")
    assert "ffmpeg" not in core
    assert "COPY dev_team /opt/dev_team" not in core
    assert "# (no product extras)" in core, "no-extra products get the placeholder"
