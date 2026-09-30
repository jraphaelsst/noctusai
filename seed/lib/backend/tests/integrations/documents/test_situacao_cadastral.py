"""`documents.situacao_cadastral.normalizar` — the closed vocabulary shared
by `cartao_cnpj.py` and `cnpj_registry`'s mappers."""
from __future__ import annotations

from noctusai_lib.integrations.documents.situacao_cadastral import (
    VOCABULARIO,
    VOCABULARIO_RE,
    normalizar,
)


def test_normalizar_maps_every_vocabulary_word():
    for bruto, esperado in VOCABULARIO.items():
        assert normalizar(bruto) == esperado
        assert normalizar(bruto.lower()) == esperado


def test_normalizar_finds_the_word_inside_a_longer_string():
    assert normalizar("SITUACAO: BAIXADA") == "baixada"


def test_normalizar_none_for_blank():
    assert normalizar(None) is None
    assert normalizar("") is None


def test_normalizar_none_for_unrecognized_text():
    assert normalizar("algo desconhecido") is None


def test_vocabulario_re_matches_whole_word_only():
    assert VOCABULARIO_RE.search("EMPRESA ATIVA HOJE") is not None
    assert VOCABULARIO_RE.search("INATIVADA") is None
