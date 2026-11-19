"""The agents half of the ``### Publicação <n>`` golden contract.

The table (``seed/lib/shared/criacao_publicacao.cases.json``) is read by BOTH sides of the contract: this suite pins what
the agent's output checks extract and flag; social-wiring's ``publicacoes.py`` suite pins what SW accepts from the very
same texts. Add a case to the file and to both suites, or to neither."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.criacao.saida import checar_publicacao, extrair_publicacoes

CASOS_PATH = Path(__file__).resolve().parents[5] / "seed" / "lib" / "shared" / "criacao_publicacao.cases.json"
TABELA = json.loads(CASOS_PATH.read_text(encoding="utf-8"))


def test_the_table_is_the_shared_one_and_not_empty():
    assert TABELA["versao"] == 1
    assert len(TABELA["casos"]) >= 9
    assert len({c["nome"] for c in TABELA["casos"]}) == len(TABELA["casos"])


@pytest.mark.parametrize("caso", TABELA["casos"], ids=lambda c: c["nome"])
def test_agent_extracts_and_flags_exactly_what_the_table_says(caso):
    pubs = extrair_publicacoes(caso["texto"])
    assert [p.numero for p in pubs] == caso["agents"]["numeros"]
    assert [f for p in pubs for f in checar_publicacao(p)] == caso["agents"]["falhas"]
