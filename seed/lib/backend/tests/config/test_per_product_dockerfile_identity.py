"""Every product's Dockerfile must name ITS OWN slug and port.

``products/<slug>/backend/Dockerfile`` is generated from
``products/seed/backend/Dockerfile``, where the identity strings
(``PRODUCT_SLUG=seed``, ``8004``, ``products/seed/...``) are LITERALS —
correct for the seed, whose slug really is ``seed``, and therefore
impossible to author as ``{{PLACEHOLDER}}``. Nothing substitutes them on
the way out: ``sync_seed_template._apply_placeholders`` has a Dockerfile
branch but marks it PARITY-DEAD and defers to a ``propagate-dockerfiles.sh``
that does not exist in ``scripts/``, and ``scaffold_product`` skips
Dockerfiles because they carry no placeholders to replace.

igig (2026-08-09) was the first product scaffolded after that gap opened.
It shipped ``ENV PRODUCT_SLUG=seed PRODUCT_PORT=8004`` and ``products/seed/``
build paths throughout. The failure was total but silent until runtime:
``local-watch`` resolved ``FE=/app/products/seed/frontend``, ran ``vite
build`` against a directory with no ``index.html``, and the container
exited 1 on every start. Nothing in CI looked at the Dockerfile.

This keeper closes that hole for the whole fleet at once. It is a text
assertion rather than a build: reading the file is what CI can afford, and
it pins exactly the strings that were wrong.

Slugs are DERIVED from ``start.sh PRODUCTS`` (the single source of truth
for slug↔port), so a new product is covered the moment it is registered —
no manual edit here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.config.cors_registry import parse_products_registry

# parents[0]=config, [1]=tests, [2]=backend, [3]=lib, [4]=seed, [5]=repo-root.
_REPO_ROOT = Path(__file__).resolve().parents[5]
_PRODUCTS_DIR = _REPO_ROOT / "products"


def _derive_products() -> tuple[tuple[str, int], ...]:
    """``(slug, backend_port)`` for every registered product that has a
    Dockerfile on disk. A registry row mid-teardown is skipped rather than
    failing the suite."""
    rows: list[tuple[str, int]] = []
    for entry in parse_products_registry():
        slug = entry["slug"]
        if (_PRODUCTS_DIR / slug / "backend" / "Dockerfile").is_file():
            rows.append((slug, entry["backend_port"]))
    return tuple(sorted(rows))


PRODUCTS: tuple[tuple[str, int], ...] = _derive_products()


def _dockerfile(slug: str) -> str:
    return (_PRODUCTS_DIR / slug / "backend" / "Dockerfile").read_text(encoding="utf-8")


@pytest.mark.parametrize(("slug", "port"), PRODUCTS)
def test_runtime_env_names_own_slug_and_port(slug: str, port: int) -> None:
    """``ENV PRODUCT_SLUG=<slug> PRODUCT_PORT=<port>``.

    ``seed/docker/local-watch.sh`` reads both. A wrong slug sends the
    container's SPA build at another product's frontend directory; a wrong
    port makes uvicorn listen where the healthcheck is not looking.
    """
    assert f"ENV PRODUCT_SLUG={slug} PRODUCT_PORT={port}" in _dockerfile(slug), (
        f"{slug}: runtime-watch ENV does not declare "
        f"PRODUCT_SLUG={slug} PRODUCT_PORT={port}. The template ships the "
        "seed's literals (PRODUCT_SLUG=seed PRODUCT_PORT=8004) and nothing "
        "rewrites them — see this module's docstring."
    )


@pytest.mark.parametrize(("slug", "port"), PRODUCTS)
def test_every_declared_port_is_the_products_own(slug: str, port: int) -> None:
    """``EXPOSE`` / healthcheck / ``uvicorn --port`` all agree on ``port``.

    Checked together because they only mean anything in agreement: an
    EXPOSE that disagrees with the uvicorn port publishes a closed socket,
    and a healthcheck that disagrees marks a healthy container unhealthy.
    """
    text = _dockerfile(slug)
    ports = {int(p) for p in re.findall(r"^EXPOSE\s+(\d+)", text, flags=re.MULTILINE)}
    ports |= {int(p) for p in re.findall(r"localhost:(\d+)/api/health", text)}
    ports |= {int(p) for p in re.findall(r'"--port",\s*"(\d+)"', text)}
    assert ports == {port}, (
        f"{slug}: Dockerfile declares ports {sorted(ports)}, expected only "
        f"{port} (its backend port in start.sh PRODUCTS)."
    )


@pytest.mark.parametrize(("slug", "port"), PRODUCTS)
def test_build_paths_point_at_own_product_dir(slug: str, port: int) -> None:
    """No ``products/seed/`` in a non-seed product's build instructions.

    Only executable lines are inspected: the generated header comment
    legitimately cites ``products/seed/backend/Dockerfile`` as its
    provenance, and forbidding that would push products to drop the one
    line that says where to edit.
    """
    if slug == "seed":
        pytest.skip("the seed's own build paths are correctly products/seed/")
    offenders = [
        line
        for line in _dockerfile(slug).splitlines()
        if "products/seed/" in line and not line.lstrip().startswith("#")
    ]
    assert not offenders, (
        f"{slug}: {len(offenders)} build instruction(s) still reference the "
        f"seed's directory instead of products/{slug}/:\n  "
        + "\n  ".join(offenders)
    )
