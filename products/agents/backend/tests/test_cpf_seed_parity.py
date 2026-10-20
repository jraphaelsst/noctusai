"""The three CPF check-digit call sites agree with the seed primitive on the seed's shared case table."""
import json
import re
from pathlib import Path

import pytest
from noctusai_lib.primitives.identificador import cpf_dv_valido

from app.qualificacao.identificacao import validar_cpf
from app.studio.eval_pii import _cpf_valido
from app.studio.eval_sinteticos import gerar_cpf_sintetico

_CASES = Path(__file__).resolve().parents[4] / "seed" / "lib" / "shared" / "identificador.cases.json"
_CPF = [c["entrada"] for c in json.loads(_CASES.read_text())["ler"] if c["tipo"] == "cpf"]


def _digits(v: str) -> str:
    return re.sub(r"\D", "", v)


def test_case_table_has_cpf_cases():
    assert len(_CPF) >= 10


@pytest.mark.parametrize("entrada", _CPF)
def test_validar_cpf_agrees_with_seed(entrada):
    d = _digits(entrada)
    assert validar_cpf(entrada) == ((True, d) if cpf_dv_valido(d) else (False, ""))


@pytest.mark.parametrize("entrada", _CPF)
def test_eval_pii_agrees_with_seed(entrada):
    assert _cpf_valido(entrada) == cpf_dv_valido(_digits(entrada))


def test_generator_output_is_seed_valid():
    for _ in range(200):
        assert cpf_dv_valido(_digits(gerar_cpf_sintetico()))
