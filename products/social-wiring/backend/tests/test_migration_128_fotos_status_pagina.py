"""Structural (parse-based) tests for `128_fotos_status_pagina.sql`.

Pins: ten pages seeded 'desenvolvimento', ON CONFLICT DO NOTHING
idempotency, and — critically — that this file does NOT declare a new
`dev_veem_desenvolvimento`-shaped policy (it relies entirely on the one
`036_status_pagina_dev_visibility.sql` already shipped, and its filename
must not match `*status_pagina_dev_visibility.sql` or
`check_status_pagina_role_parity` would scan it for a role array it
never declares).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "128_fotos_status_pagina.sql"

PAGES = (
    "edicao-fotos",
    "edicao-fotos-novo-lote",
    "edicao-fotos-revisao",
    "edicao-fotos-configuracoes",
    "edicao-fotos-referencias",
    "edicao-fotos-guias",
    "edicao-fotos-modelos",
    "edicao-fotos-regras",
    "edicao-fotos-curadores",
    "edicao-fotos-painel",
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"Migration file missing at {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


@pytest.fixture(scope="module")
def flat(code: str) -> str:
    collapsed = " ".join(code.split())
    return re.sub(r"\s+\)", ")", re.sub(r"\(\s+", "(", collapsed))


def test_migration_parses(sql: str):
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(sql)) > 0


def test_sets_search_path(flat: str):
    assert "SET search_path = social_wiring, public;" in flat


def test_is_forward_only(code: str):
    assert "DROP TABLE" not in code
    assert "DELETE FROM" not in code


def test_filename_does_not_match_the_dev_visibility_glob():
    """`check_status_pagina_role_parity` globs `*status_pagina_dev_
    visibility.sql` for role-array comparisons — this file inserts rows
    only and must not be swept into that check."""
    assert not MIGRATION.name.endswith("status_pagina_dev_visibility.sql")


def test_declares_no_new_rls_policy(code: str):
    """Visibility comes entirely from the existing
    dev_veem_desenvolvimento policy (036) — this file must not declare
    its own."""
    assert "CREATE POLICY" not in code
    assert "ALTER TABLE" not in code


@pytest.mark.parametrize("page", PAGES)
def test_every_page_seeded_as_desenvolvimento(flat: str, page: str):
    assert f"('{page}'," in flat


def test_all_ten_pages_are_desenvolvimento_not_producao(sql: str):
    insert_block = sql.split("INSERT INTO social_wiring.status_pagina")[1]
    insert_block = insert_block.split("ON CONFLICT", 1)[0]
    assert insert_block.count("'desenvolvimento'") == len(PAGES)
    assert "'producao'" not in insert_block


def test_insert_is_idempotent(flat: str):
    assert "ON CONFLICT (nome_pagina) DO NOTHING;" in flat
