"""The intermediary document CHECKs accept what the service WRITES.

Production bug (found 2026-10-10 by the seed mock's new cross-column CHECK
enforcement): migration `termos_negocio` pinned `documento` /
`representante_cpf` to BARE digits, but since the canonical-identifiers
change (2026-10-01) `_normalizar_documento` and the `representante_cpf` path
store the PUNCTUATED canonical form, so every save of an intermediary with a
document was refused (23514). Migration `intermediario_documento_canonico`
backfills the old bare rows and moves both CHECKs to the canonical shapes.

The load-bearing test: the patterns are read OUT OF THE MIGRATION and the
values come FROM THE SERVICE'S OWN NORMALIZER — so the two can never drift
apart again unnoticed.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from noctusai_lib.testing.migrations import migration_sql

from app.modules.card_hub.negociacao_estruturada_service import _normalizar_documento
from noctusai_lib.primitives import identificador as ident

PRODUCT = Path(__file__).resolve().parents[4]
SQL = migration_sql(PRODUCT, "intermediario_documento_canonico.sql")
CODE = "\n".join(l for l in SQL.splitlines() if not l.strip().startswith("--"))
#: Only the CHECKs — the backfill's WHERE clauses use `~` too.
CHECKS = CODE[CODE.index("ADD CONSTRAINT"):]


def _pattern(after: str) -> re.Pattern[str]:
    """The `~ '...'` literal following `after` in the migration's CHECKs."""
    m = re.search(re.escape(after) + r"\s*~\s*'([^']+)'", CHECKS)
    assert m, f"no pattern after {after!r}"
    return re.compile(m.group(1))


PF = _pattern("pessoa_tipo = 'pf' AND documento")
PJ = _pattern("pessoa_tipo = 'pj' AND documento")
REP = _pattern("representante_cpf IS NULL OR representante_cpf")


@pytest.mark.parametrize("bruto", ["111.444.777-35", "11144477735", " 111 444 777 35 "])
def test_a_pf_document_as_the_service_stores_it_satisfies_the_check(bruto):
    documento, tipo = _normalizar_documento(bruto)
    assert tipo == "pf" and PF.fullmatch(documento) and not PJ.fullmatch(documento)


@pytest.mark.parametrize("bruto", ["11.222.333/0001-81", "11222333000181", "12.abc.345/01de-35"])
def test_a_pj_document_as_the_service_stores_it_satisfies_the_check(bruto):
    documento, tipo = _normalizar_documento(bruto)
    assert tipo == "pj" and PJ.fullmatch(documento) and not PF.fullmatch(documento)


def test_the_representante_cpf_as_the_service_stores_it_satisfies_the_check():
    assert REP.fullmatch(ident.canonico("cpf", "11144477735"))


@pytest.mark.parametrize("bare", ["11144477735", "11222333000181"])
def test_the_old_bare_shape_is_refused(bare):
    assert not PF.fullmatch(bare) and not PJ.fullmatch(bare) and not REP.fullmatch(bare)


def test_old_checks_are_dropped_before_the_backfill_and_new_ones_added_after():
    """The first version rewrote rows UNDER 114's digits-only CHECK and its
    prod apply failed with 23514 (2026-10-10). Order: DROP both → UPDATE →
    ADD both."""
    drops = [m.start() for m in re.finditer(r"DROP CONSTRAINT IF EXISTS atendimento_intermediarios_\w+_formato", CODE)]
    updates = [m.start() for m in re.finditer(r"UPDATE social_wiring\.atendimento_intermediarios", CODE)]
    adds = [m.start() for m in re.finditer(r"ADD CONSTRAINT atendimento_intermediarios_\w+_formato", CODE)]
    assert len(drops) == 2 and len(adds) == 2 and updates
    assert max(drops) < min(updates) and max(updates) < min(adds)


@pytest.mark.parametrize("bare,canonical", [
    ("11144477735", "111.444.777-35"),
    ("11222333000181", "11.222.333/0001-81"),
    ("12ABC34501DE35", "12.ABC.345/01DE-35"),
])
def test_the_backfill_produces_the_canonical_form(bare, canonical):
    """The backfill's regexp_replace, run in Python (plain ERE patterns and
    `\\N` back-references mean the same in `re`), yields exactly the
    canonical identifier."""
    for m in re.finditer(r"regexp_replace\(\s*\w+,\s*'([^']+)',\s*'([^']+)'\)", CODE):
        pattern, repl = m.group(1), m.group(2)
        if re.fullmatch(pattern, bare):
            assert re.sub(pattern, repl, bare) == canonical
            assert canonical == ident.canonico("cnpj" if len(bare) == 14 else "cpf", bare)
            return
    pytest.fail(f"no backfill rewrites {bare!r}")
