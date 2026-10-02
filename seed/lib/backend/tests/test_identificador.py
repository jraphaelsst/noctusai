"""Canonical identifier contract — Python half.

Asserts the SHARED case table (`seed/lib/shared/identificador.cases.json`),
the same one the TypeScript twin and the plpgsql parity block assert. The
interesting cases are the refusals: a CPF sitting in an RG field, a
DV-invalid OCR reading, a 7-digit RG whose DV may or may not be included.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from noctusai_lib.integrations.documents import cnpj as cnpj_mod
from noctusai_lib.integrations.documents import cpf as cpf_mod
from noctusai_lib.integrations.documents import rg as rg_mod
from noctusai_lib.primitives import identificador as idf

LIB = Path(__file__).resolve().parents[2]
CASES = json.loads((LIB / "shared" / "identificador.cases.json").read_text(encoding="utf-8"))
SQL_FILE = LIB / "sql" / "identificador.sql"


def _id(c: dict, k: str = "entrada") -> str:
    return f"{c['tipo']}:{c.get(k)!r}:{c.get('opts', {})}"


@pytest.mark.parametrize("c", CASES["ler"], ids=[_id(c) for c in CASES["ler"]])
def test_ler(c: dict) -> None:
    r = idf.ler(c["tipo"], c["entrada"], **c.get("opts", {}))
    assert (r.canonico, r.cabe, r.dv_ok, r.dv_completado, r.motivo, r.tipo_detectado) == (
        c["canonico"], c["cabe"], c["dv_ok"], c["dv_completado"], c["motivo"], c["tipo_detectado"],
    )
    assert idf.canonico(c["tipo"], c["entrada"], **c.get("opts", {})) == c["canonico"]


@pytest.mark.parametrize("c", CASES["equivalentes"], ids=[f"{c['tipo']}:{c['a']}~{c['b']}" for c in CASES["equivalentes"]])
def test_equivalentes(c: dict) -> None:
    opts = c.get("opts", {})
    assert idf.equivalentes(c["tipo"], c["a"], c["b"], **opts) is c["esperado"]
    assert idf.equivalentes(c["tipo"], c["b"], c["a"], **opts) is c["esperado"]  # symmetric


@pytest.mark.parametrize("c", CASES["chave_busca"], ids=[_id(c) for c in CASES["chave_busca"]])
def test_chave_busca(c: dict) -> None:
    assert idf.chave_busca(c["tipo"], c["entrada"], **c.get("opts", {})) == c["esperado"]


@pytest.mark.parametrize("c", CASES["extrair_cns"], ids=[c["texto"][:30] for c in CASES["extrair_cns"]])
def test_extrair_cns(c: dict) -> None:
    assert idf.extrair_cns(c["texto"]) == c["esperado"]


@pytest.mark.parametrize("c", CASES["detectar_tipo"], ids=[repr(c["entrada"]) for c in CASES["detectar_tipo"]])
def test_detectar_tipo(c: dict) -> None:
    assert idf.detectar_tipo(c["entrada"]) == c["esperado"]


def test_formatar_is_canonical_or_raw_visible() -> None:
    assert idf.formatar("rg", "30128742") == "30.128.742-9"
    assert idf.formatar("rg", " 15.668.564-3 ") == "15.668.564-3"  # DV-bad: stays visible as stored
    assert idf.formatar("rg", None) == ""


def test_unknown_tipo_is_loud() -> None:
    with pytest.raises(ValueError):
        idf.ler("passaporte", "x")


def test_excel_float_numbers_are_read() -> None:
    assert idf.canonico("matricula_imovel", 79826.0) == "79.826"
    assert idf.canonico("cep", 13010110) == "13010-110"


class TestSingleImplementation:
    """integrations/documents/{cpf,cnpj,rg} delegate — one DV algorithm."""

    def test_cpf_module_backward_compatible(self) -> None:
        assert cpf_mod.is_valid("412.954.238-98") and not cpf_mod.is_valid("412.954.238-99")
        assert not cpf_mod.is_valid("111.111.111-11")
        assert cpf_mod.format_cpf("41295423898") == "412.954.238-98"
        assert cpf_mod.format_cpf("4129542389") is None

    def test_cnpj_module_backward_compatible(self) -> None:
        assert cnpj_mod.is_valid("11.222.333/0001-81") and not cnpj_mod.is_valid("11.222.333/0001-82")
        assert cnpj_mod.format_cnpj("11222333000181") == "11.222.333/0001-81"
        assert cnpj_mod.format_cnpj("123") is None

    def test_rg_module_delegates(self) -> None:
        assert rg_mod.completar_dv("30128742") == "30.128.742-9"
        assert rg_mod.completar_dv("15.668.564-3") is None
        assert rg_mod.mesmo_rg("30128742", "30.128.742-9") is True

    def test_no_second_dv_algorithm(self) -> None:
        for mod in (cpf_mod, cnpj_mod, rg_mod):
            src = Path(mod.__file__).read_text(encoding="utf-8")
            assert "_PESOS" not in src and "% 11" not in src


def gerar_bloco_sql(cases: dict) -> str:
    """The VALUES rows the SQL parity block embeds, from the case table."""

    def q(v: object) -> str:
        return "NULL" if v is None else "'" + str(v).replace("'", "''") + "'"

    rows = []
    for kind, key, esperado_key in (("canon", "ler", "canonico"), ("chave", "chave_busca", "esperado")):
        for c in cases[key]:
            if not c.get("sql"):
                continue
            o = c.get("opts", {})
            rows.append(
                f"        ({q(kind)}, {q(c['tipo'])}, {q(c['entrada'])}, {q(o.get('municipio'))}, "
                f"{q(o.get('ibge'))}, {q(o.get('uf'))}, {q(c[esperado_key])})"
            )
    return ",\n".join(rows) + "\n"


@pytest.mark.skipif(not SQL_FILE.exists(), reason="sql twin not present")
def test_sql_twin_parity_block_in_sync_with_case_table() -> None:
    """The SQL file embeds the sql=true cases between markers; they must be
    exactly what the case table says (regenerate with `gerar_bloco_sql`)."""
    sql = SQL_FILE.read_text(encoding="utf-8")
    m = re.search(r"-- BEGIN-CASES\n(.*?)-- END-CASES", sql, re.S)
    assert m, "markers missing"
    assert m.group(1) == gerar_bloco_sql(CASES)
