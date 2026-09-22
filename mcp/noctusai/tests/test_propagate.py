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


def _write_registry_start_sh(root: Path, entries: list[tuple[str, str]]) -> None:
    """Write a synthetic start.sh carrying a BEGIN/END_PRODUCTS_REGISTRY
    block for the given (slug, backend_port) rows — the same shape
    `noctusai_lib.config.cors_registry.parse_products_registry` parses.
    Frontend ports are synthesized (backend + 10000); `_load_products`
    only reads `backend_port`, so their exact value is irrelevant here."""
    lines = ["# BEGIN_PRODUCTS_REGISTRY", "PRODUCTS=("]
    for slug, backend_port in entries:
        frontend_port = int(backend_port) + 10000
        lines.append(f'  "{slug}:{slug.title()}:{backend_port}:{frontend_port}"')
    lines += [")", "# END_PRODUCTS_REGISTRY"]
    (root / "start.sh").write_text("\n".join(lines) + "\n")


def _make_temp_repo(tmp_path: Path, kind: str) -> Path:
    """Copy the real canonical seed file into a throwaway repo root so the
    native propagate fn sees real input. (scripts/propagate-*.sh was
    absorbed into noctus.dev.propagate + deleted — scripts-mcp-absorption
    2026-05-18; byte-parity vs the .sh was proven green at port time, the
    durable check is native idempotency below.)

    Also stamps a synthetic start.sh registry mirroring `P.PRODUCTS`
    (BUG 2 fix, 2026-09-16): `_propagate()` now re-derives its product set
    from the EFFECTIVE root's start.sh on every call rather than the
    module-import-time `P.PRODUCTS` snapshot, so the temp repo needs its
    own registry for that derivation to find anything."""
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
    _write_registry_start_sh(root, P.PRODUCTS)
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


# ── BUG 2 regression (2026-09-16): product set must derive from the
# EFFECTIVE root, not a module-import-time snapshot ────────────────────────
@pytest.mark.parametrize(
    "kind,fn,out_tpl",
    [
        ("composes", P.propagate_composes, "products/{slug}/docker-compose.yml"),
        ("dockerfiles", P.propagate_dockerfiles, "products/{slug}/backend/Dockerfile"),
    ],
)
def test_propagate_derives_products_from_effective_root(tmp_path, kind, fn, out_tpl):
    """Before the fix: `PRODUCTS` was computed ONCE at module import from
    the MCP server's own `REPO_ROOT` (the primary checkout); `_propagate()`
    iterated that frozen snapshot regardless of any `repo_root`/
    `worktree_path` the caller passed. A product registered ONLY in the
    override root's start.sh (e.g. a fresh worktree-only scaffold like
    `community`) was silently omitted from `wrote` while the call still
    reported `status="written"` — a silent-omission shape, not a crash.

    Simulates that scenario: a temp repo whose start.sh registers an EXTRA
    product `P.PRODUCTS` (the module-level snapshot) does not know about.
    A correct fix regenerates + reports that product; the old code would
    silently drop it from `wrote`/`products` yet still report success."""
    root = _make_temp_repo(tmp_path, kind)
    extra_slug = "worktree-only-product"
    assert extra_slug not in {slug for slug, _ in P.PRODUCTS}, (
        "test fixture must pick a slug the module-level snapshot does NOT carry"
    )
    registry_path = root / "start.sh"
    text = registry_path.read_text()
    text = text.replace(
        "# END_PRODUCTS_REGISTRY",
        f'  "{extra_slug}:Worktree Only:8999:18999"\n# END_PRODUCTS_REGISTRY',
    )
    registry_path.write_text(text)
    (root / "products" / extra_slug / "backend").mkdir(parents=True, exist_ok=True)

    res = fn(repo_root=str(root))
    assert res["ok"] is True
    assert res["status"] == "written"
    assert extra_slug in res["products"], (
        "propagate must derive its product set from the EFFECTIVE root's "
        "start.sh — a registry-only product must not be silently omitted"
    )
    rel = out_tpl.format(slug=extra_slug)
    assert rel in res["wrote"]
    assert (root / rel).exists()


def test_load_products_raises_on_empty_registry(tmp_path):
    """No start.sh (or an empty/missing registry block) at the effective
    root must raise loudly, never silently regenerate an empty set while
    reporting success (mirrors the module-import-time guard, now exercised
    per-call against an arbitrary root)."""
    root = tmp_path / "no-start-sh"
    root.mkdir()
    with pytest.raises(RuntimeError, match="PRODUCTS registry parsed empty"):
        P._load_products(root)


# ── active-scope filtering (2026-09-22) ─────────────────────────────────────
def test_load_products_skips_asleep_keeps_active(tmp_path):
    """`_load_products` must drop a slug absent from `active-scope.txt` and
    keep one present in it — the choke point `--propagate both --check`
    (pre-commit) relies on so an asleep product's compose/Dockerfile is
    never regenerated or flagged as drift."""
    root = tmp_path / "repo"
    root.mkdir()
    _write_registry_start_sh(
        root, [("awake-product", "8100"), ("asleep-product", "8200")]
    )
    scope_path = root / "deploy" / "fleet" / "active-scope.txt"
    scope_path.parent.mkdir(parents=True, exist_ok=True)
    scope_path.write_text("awake-product\n")

    products = P._load_products(root)

    assert products == [("awake-product", "8100")]


def test_load_products_missing_scope_file_keeps_everything(tmp_path):
    """No `active-scope.txt` at the effective root (every synthetic temp
    repo this suite's other tests build) fails toward coverage — every
    registry row survives, unfiltered."""
    root = tmp_path / "repo"
    root.mkdir()
    _write_registry_start_sh(
        root, [("awake-product", "8100"), ("asleep-product", "8200")]
    )

    products = P._load_products(root)

    assert {slug for slug, _ in products} == {"awake-product", "asleep-product"}
