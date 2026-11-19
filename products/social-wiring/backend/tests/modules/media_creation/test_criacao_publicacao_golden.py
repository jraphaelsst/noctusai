"""The social-wiring half of the ``### Publicação <n>`` golden contract.

The table (``seed/lib/shared/criacao_publicacao.cases.json``) is read by BOTH sides: this suite pins what SW's
``publicacoes.py`` accepts and counts from the very same texts the agent suite
(``products/agents/backend/tests/criacao/test_publicacao_golden.py``) pins on its side. Add a case to the file and to both
suites, or to neither. The sides differ BY DESIGN on ``link_preenchido`` (documented in the file)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.modules.media_creation.services.publicacoes import extrair_publicacoes

CASOS_PATH = Path(__file__).resolve().parents[6] / "seed" / "lib" / "shared" / "criacao_publicacao.cases.json"
CASOS = json.loads(CASOS_PATH.read_text(encoding="utf-8"))


def test_the_table_is_the_shared_one_and_not_empty():
    assert CASOS["versao"] == 1 and len(CASOS["casos"]) >= 10
    assert len({c["nome"] for c in CASOS["casos"]}) == len(CASOS["casos"])


@pytest.mark.parametrize("caso", CASOS["casos"], ids=lambda c: c["nome"])
def test_sw_accepts_and_counts_exactly_what_the_table_says(caso):
    res = extrair_publicacoes(caso["texto"])
    obtido = {n: (v.cta_objetivo, v.cta, list(v.hashtags), list(v.fontes)) for n, v in res.por_numero.items()}
    esperado = {
        v["numero"]: (v["cta_objetivo"], v["cta"], v["hashtags"], v["fontes"]) for v in caso["sw"]["validas"]
    }
    assert obtido == esperado
    assert res.invalidas == caso["sw"]["invalidas"]
