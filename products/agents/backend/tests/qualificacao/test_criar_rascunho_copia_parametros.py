"""The LAST re-declaration of agents.criar_rascunho_qualificacao copies every column of qualificacao_parametros.

Each migration that adds a parameter column re-declares the clone function (CREATE OR REPLACE), and the newest one
wins. 080 (max_retomadas_seguidas) and 081 (catalogo) were written on parallel branches: 081's re-declaration copied
only its own column, so once both applied, a new draft would have reset the follow-up cap to its default without any
error. This test reads the whole migration chain, so the next parallel pair fails here instead of in prod.
"""
from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"

_ADD = re.compile(r"ALTER TABLE agents\.qualificacao_parametros\s+ADD COLUMN(?: IF NOT EXISTS)?\s+(\w+)", re.I)
_CREATE = re.compile(r"CREATE TABLE(?: IF NOT EXISTS)? agents\.qualificacao_parametros\s*\((.*?)\n\);", re.I | re.S)
_FN = "CREATE OR REPLACE FUNCTION agents.criar_rascunho_qualificacao("
_INSERT = re.compile(r"INSERT INTO agents\.qualificacao_parametros\s*\(([^)]*)\)", re.I)


def _chain() -> list[Path]:
    return sorted(p for p in MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql"))


def _columns() -> set[str]:
    cols: set[str] = set()
    for p in _chain():
        sql = p.read_text()
        for body in _CREATE.findall(sql):
            for line in body.splitlines():
                m = re.match(r"\s*(\w+)\s+\w", line)
                if m and m.group(1).upper() not in {"PRIMARY", "CONSTRAINT", "UNIQUE", "CHECK", "FOREIGN"}:
                    cols.add(m.group(1))
        cols.update(_ADD.findall(sql))
    return cols - {"created_at", "updated_at"}


def _last_clone_insert() -> tuple[str, set[str]]:
    last = [p for p in _chain() if _FN in p.read_text()][-1]
    sql = last.read_text()
    inserts = _INSERT.findall(sql[sql.index(_FN):])
    assert inserts, f"{last.name}: the clone function no longer copies qualificacao_parametros"
    return last.name, {c.strip() for c in inserts[0].split(",")}


def test_the_newest_clone_function_copies_every_parameter_column():
    cols = _columns()
    assert {"minimo_para_ofertar", "max_retomadas_seguidas", "catalogo"} <= cols  # the parser still sees the chain
    name, copied = _last_clone_insert()
    missing = cols - copied - {"versao_id"}
    assert not missing, f"{name} re-declares criar_rascunho_qualificacao without copying {sorted(missing)}"
