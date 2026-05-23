"""Colocated regression test for `check_product_container_shape`.

Pins the true-positive (a product missing the house single-container shape)
and false-positive (a correctly-containerized product, the `seed` source, and
a backend-only product) shapes so a future refactor can't silently regress the
container-first keeper. Builds synthetic `products/<slug>/` trees under
`tmp_path` — no real Docker, no real fleet.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import compliance as C  # noqa: E402

# A minimal Dockerfile carrying every house marker (universal + SPA).
_HOUSE_DOCKERFILE = """\
FROM noctus-seed-frontend-base:dev AS frontend-build
RUN npm run build
FROM noctus-seed-backend-base:dev AS runtime
ENV SERVE_SPA_DIR=/app/products/x/frontend/dist
CMD ["uvicorn", "app.main:app"]
FROM runtime AS runtime-watch
ENTRYPOINT ["/usr/local/bin/local-watch"]
"""

# Backend-only house Dockerfile (no SPA stage — legit for a frontend-less product).
_HOUSE_DOCKERFILE_BACKEND_ONLY = """\
FROM noctus-seed-backend-base:dev AS runtime
CMD ["uvicorn", "app.main:app"]
FROM runtime AS runtime-watch
ENTRYPOINT ["/usr/local/bin/local-watch"]
"""


def _house_compose(slug: str) -> str:
    return f"""\
services:
  {slug}:
    build:
      target: runtime-watch
  {slug}-tunnel:
    profiles: [tunnel-{slug}]
networks:
  noctus-net:
    external: true
"""


def _make_product(
    root: Path, slug: str, *, dockerfile: str | None, compose: str | None, frontend: bool
) -> None:
    backend = root / "products" / slug / "backend"
    backend.mkdir(parents=True, exist_ok=True)
    if frontend:
        (root / "products" / slug / "frontend").mkdir(parents=True, exist_ok=True)
    if dockerfile is not None:
        (backend / "Dockerfile").write_text(dockerfile)
    if compose is not None:
        (root / "products" / slug / "docker-compose.yml").write_text(compose)


class TestCheckProductContainerShape:
    # ── false positives (must stay clean) ──────────────────────────────
    def test_full_house_product_passes(self, tmp_path: Path) -> None:
        _make_product(
            tmp_path, "alpha",
            dockerfile=_HOUSE_DOCKERFILE, compose=_house_compose("alpha"), frontend=True,
        )
        assert C.check_product_container_shape(repo_root=tmp_path) == []

    def test_backend_only_product_passes_without_spa_markers(self, tmp_path: Path) -> None:
        # No frontend/ dir → SERVE_SPA_DIR + frontend-base are NOT required.
        _make_product(
            tmp_path, "beta",
            dockerfile=_HOUSE_DOCKERFILE_BACKEND_ONLY,
            compose=_house_compose("beta"), frontend=False,
        )
        assert C.check_product_container_shape(repo_root=tmp_path) == []

    def test_seed_is_skipped(self, tmp_path: Path) -> None:
        # `seed` is the canonical source — never flagged even if shapeless.
        _make_product(tmp_path, "seed", dockerfile="FROM scratch", compose="services: {}", frontend=False)
        assert C.check_product_container_shape(repo_root=tmp_path) == []

    def test_non_backend_dir_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "products" / "notaprod").mkdir(parents=True)
        (tmp_path / "products" / "notaprod" / "README.md").write_text("x")
        assert C.check_product_container_shape(repo_root=tmp_path) == []

    # ── true positives (must flag) ─────────────────────────────────────
    def test_missing_dockerfile_is_flagged(self, tmp_path: Path) -> None:
        # The freshly-absorbed-but-uncontainerized case (the KE pilot).
        _make_product(tmp_path, "gamma", dockerfile=None, compose=_house_compose("gamma"), frontend=False)
        issues = C.check_product_container_shape(repo_root=tmp_path)
        assert any("has no" in i["issue"] and i["file"].endswith("Dockerfile") for i in issues)
        assert all(i["severity"] == "warning" for i in issues)

    def test_missing_runtime_watch_target_is_flagged(self, tmp_path: Path) -> None:
        df = "FROM noctus-seed-backend-base:dev AS runtime\nCMD [\"uvicorn\"]\n"  # no runtime-watch
        _make_product(tmp_path, "delta", dockerfile=df, compose=_house_compose("delta"), frontend=False)
        issues = C.check_product_container_shape(repo_root=tmp_path)
        assert any("runtime-watch" in i["issue"] for i in issues)

    def test_custom_base_instead_of_seed_is_flagged(self, tmp_path: Path) -> None:
        df = "FROM python:3.12 AS runtime\nFROM runtime AS runtime-watch\n"  # not FROM noctus-seed base
        _make_product(tmp_path, "epsilon", dockerfile=df, compose=_house_compose("epsilon"), frontend=False)
        issues = C.check_product_container_shape(repo_root=tmp_path)
        assert any("noctus-seed-backend-base" in i["issue"] for i in issues)

    def test_frontend_product_missing_serve_spa_is_flagged(self, tmp_path: Path) -> None:
        # has frontend/ but Dockerfile omits SERVE_SPA_DIR + frontend-base
        df = "FROM noctus-seed-backend-base:dev AS runtime\nFROM runtime AS runtime-watch\n"
        _make_product(tmp_path, "zeta", dockerfile=df, compose=_house_compose("zeta"), frontend=True)
        issues = C.check_product_container_shape(repo_root=tmp_path)
        assert any("SERVE_SPA_DIR" in i["issue"] for i in issues)
        assert any("frontend-base" in i["issue"] for i in issues)

    def test_missing_compose_and_tunnel_flagged(self, tmp_path: Path) -> None:
        _make_product(
            tmp_path, "eta",
            dockerfile=_HOUSE_DOCKERFILE_BACKEND_ONLY, compose=None, frontend=False,
        )
        issues = C.check_product_container_shape(repo_root=tmp_path)
        assert any(i["file"].endswith("docker-compose.yml") for i in issues)

    def test_compose_missing_external_net_and_tunnel_flagged(self, tmp_path: Path) -> None:
        bad_compose = "services:\n  theta:\n    build:\n      target: runtime-watch\n"  # no external, no tunnel
        _make_product(
            tmp_path, "theta",
            dockerfile=_HOUSE_DOCKERFILE_BACKEND_ONLY, compose=bad_compose, frontend=False,
        )
        issues = C.check_product_container_shape(repo_root=tmp_path)
        assert any("external" in i["issue"] for i in issues)
        assert any("theta-tunnel" in i["issue"] for i in issues)

    # ── real-tree smoke: the live fleet is house-conformant ────────────
    def test_live_fleet_is_clean(self) -> None:
        from settings import REPO_ROOT  # noqa: E402

        issues = C.check_product_container_shape(Path(REPO_ROOT))
        assert issues == [], [i["product"] + ":" + i["file"] for i in issues]
