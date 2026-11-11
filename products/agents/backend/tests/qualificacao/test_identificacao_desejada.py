"""The standard declares its desired identity fields (owner decision 2026-11-10); absent key = logged legacy."""
from __future__ import annotations

import logging
from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.qualificacao import engine
from app.qualificacao.identificacao import DESEJADOS_PADRAO, validar_desejados
from app.qualificacao.models import LeadSinais, ParametrosDef
from app.qualificacao.schemas import ParametrosIn
from datetime import datetime, timezone

from tests.qualificacao.fixture_v1 import versao_v1

AGORA = datetime(2026, 10, 19, tzinfo=timezone.utc)


def _desejada(**params):
    v = versao_v1()
    v = replace(v, parametros=replace(v.parametros, **params))
    return engine.calcular(v, [], [], AGORA, sinais=LeadSinais()).identificacao_desejada


def test_julias_current_standard_unchanged_via_logged_legacy_branch(caplog):
    with caplog.at_level(logging.INFO, logger="app.qualificacao.engine"):
        assert _desejada() == ("rg", "email", "nome") == DESEJADOS_PADRAO
    assert any("identificacao_desejada.legado" in r.getMessage() for r in caplog.records)


def test_declared_empty_asks_nothing_and_does_not_log_legacy(caplog):
    with caplog.at_level(logging.INFO, logger="app.qualificacao.engine"):
        assert _desejada(identificacao_desejada=()) == ()
    assert not any("legado" in r.getMessage() for r in caplog.records)


def test_declared_email_only():
    assert _desejada(identificacao_desejada=("email",)) == ("email",)


def test_collected_fields_are_not_asked_again():
    v = replace(versao_v1(), parametros=replace(versao_v1().parametros, identificacao_desejada=("rg", "email")))
    r = engine.calcular(v, [], [], AGORA, sinais=LeadSinais(identificacao=frozenset({"email"})))
    assert r.identificacao_desejada == ("rg",)


def test_unknown_key_refused_loudly():
    with pytest.raises(ValueError, match="desconhecido"):
        validar_desejados(["rg", "passaporte"])
    with pytest.raises(ValueError):
        ParametrosDef({"todos": []}, identificacao_desejada=("passaporte",))
    with pytest.raises(ValidationError):
        ParametrosIn(minimo_para_ofertar={"todos": []}, identificacao_desejada=["passaporte"])


def test_parametros_in_round_trip_keeps_none_distinct_from_empty():
    assert ParametrosIn(minimo_para_ofertar={}).to_def().identificacao_desejada is None
    assert ParametrosIn(minimo_para_ofertar={}, identificacao_desejada=[]).to_def().identificacao_desejada == ()
