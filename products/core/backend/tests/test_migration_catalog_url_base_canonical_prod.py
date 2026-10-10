"""Core migration ``*_catalog_url_base_canonical_prod`` + the localhost backstop.

Root cause (2026-10-10): seed-row migrations and scaffold_product wrote
``http://localhost:<port>`` into ``public.products.url_base``; prod was saved
only by env overrides. Historic migrations are immutable (already applied), so
the backstop grandfathers everything numbered <= the repair and refuses any
later products row / url_base write that is loopback. The scaffold emitter is
covered by mcp/noctusai/tests/test_scaffold.py.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from noctusai_lib.testing.migrations import migration_path, migration_sql

pglast = pytest.importorskip("pglast")
from pglast import parse_sql  # noqa: E402

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
SQL = migration_sql(MIGRATIONS, "catalog_url_base_canonical_prod")
REPAIR_NUMBER = int(migration_path(MIGRATIONS, "catalog_url_base_canonical_prod").name.split("_")[0])

# Canonical prod hosts == deploy/tunnel/ingress.yml (short names for social).
EXPECTED = {
    "igig": "https://igig.noctusai.com",
    "seed": "https://seed.noctusai.com",
    "social-wiring": "https://social.noctusai.com",
    "orbity": "https://orbity.noctusai.com",
    "p-studio": "https://p-studio.noctusai.com",
}
_LOOPBACK = re.compile(r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)", re.I)


def test_parses():
    assert len(parse_sql(SQL)) >= 3


def test_url_base_update_is_narrow_and_never_overwrites_a_real_value():
    update = SQL[SQL.rindex("UPDATE public.products SET url_base"):]
    for slug, url in EXPECTED.items():
        assert f"WHEN '{slug}'" in update and f"'{url}'" in update
    assert "url_base LIKE 'http://localhost%'" in update
    assert "slug IN ('igig','seed','social-wiring','orbity','p-studio')" in update


def test_hosts_match_tunnel_ingress():
    ingress = (Path(__file__).resolve().parents[4] / "deploy" / "tunnel" / "ingress.yml").read_text()
    for url in EXPECTED.values():
        assert f"hostname: {url.removeprefix('https://')}" in ingress


def test_house_port_is_backfilled_before_url_base_is_rewritten():
    assert SQL.index("SET house_port") < SQL.index("SET url_base")
    assert "WHERE house_port IS NULL" in SQL


def test_no_trigger_dependent_column_is_touched():
    # 051 fires on UPDATE OF ativo, deploy_scope; 075 on transitions into live.
    for col in ("ativo", "deploy_scope", "sso_callback_verified_at"):
        assert f"SET {col}" not in SQL


def _products_writes_with_loopback(text: str) -> bool:
    body = re.sub(r"--[^\n]*", "", text)
    return bool(_LOOPBACK.search(body)) and "public.products" in body


def test_no_migration_after_the_repair_writes_a_loopback_url_base():
    offenders = [
        p.name
        for p in sorted(MIGRATIONS.glob("*.sql"))
        if int(p.name.split("_")[0]) > REPAIR_NUMBER
        and _products_writes_with_loopback(p.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        f"{offenders}: url_base must be the canonical https://<host>.noctusai.com "
        "(noctusai_lib.config.product_urls.canonical_prod_url), never localhost/127.0.0.1"
    )


def test_the_backstop_catches_a_loopback_insert():
    assert _products_writes_with_loopback(
        "INSERT INTO public.products (slug,url_base) VALUES ('x','http://localhost:8099');"
    )
    assert not _products_writes_with_loopback(
        "INSERT INTO public.products (slug,url_base) VALUES ('x','https://x.noctusai.com');"
    )
