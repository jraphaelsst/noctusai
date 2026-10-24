"""Migration 306 — imóvel fields typed by hand, never upload-only
(owner directive 2026-10-24).

WHAT THESE PIN
--------------
- `GET/PUT /imoveis/{codigo}/descricao-imovel`: the read carries the
  DERIVED abertura block and the typed override; the override lands on
  `imovel_dados.descricao_imovel_texto`, `efetivo` prefers it, `null` clears;
  the body key is required (a PUT, not a PATCH);
- `PUT /imoveis/{codigo}/ultima-transferencia` carries `transmitentes`: the
  typed names WIN over the names read off the act (`transmitentes_origem`
  says which), a names-only override is valid, names next to `sem_registro`
  are refused, and clearing the whole override clears them too.

Auth: `test_matriculas_auth_boundary.py` (strict 401 over every mounted route).
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from app.modules.matriculas import titulo_service
from tests.modules.matriculas.conftest import (
    CODIGO,
    ORG_ID,
    extracao_row,
    registry_row,
    seed,
)

ORG = UUID(ORG_ID)
_DESC = f"/api/matriculas/imoveis/{CODIGO}/descricao-imovel"
_ULT = f"/api/matriculas/imoveis/{CODIGO}/ultima-transferencia"

DESCRICAO_TIPADA = "Apartamento ficticio nº 99, com área privativa de 50,00 m²."


def _data(resp):
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _texto_venda() -> str:
    return (
        "MATRÍCULA Nº 777\nTerreno ficticio.\n"
        "R-1/777 - Em 01/02/2024. COMPRA E VENDA. Transmitente: ANTIGO DONO FICTICIO, "
        "CPF 246.813.579-28; adquirente: ATUAL DONA FICTICIA, CPF 314.159.265-90.\n"
    )


class TestDescricaoImovel:
    def test_the_derived_block_is_read_and_the_typed_override_wins(self, client, scoped):
        seed(scoped, registry=[registry_row()], extracoes=[extracao_row()])

        lido = _data(client.get(_DESC))
        assert lido["confirmado"] is None
        assert lido["derivado"] and lido["derivado"].startswith("Apartamento nº 12")
        assert (lido["efetivo"], lido["origem"]) == (lido["derivado"], "matricula")

        put = _data(client.put(_DESC, json={"texto": f"  {DESCRICAO_TIPADA}  "}))
        assert put["confirmado"]["texto"] == DESCRICAO_TIPADA
        assert put["confirmado"]["confirmado_por"]
        assert (put["efetivo"], put["origem"]) == (DESCRICAO_TIPADA, "manual")
        # The derived reading is still reported — the human sees both.
        assert put["derivado"] == lido["derivado"]

        dados = client.get(f"/api/imoveis/{CODIGO}/dados").json()
        assert dados["descricao_imovel_texto"] == DESCRICAO_TIPADA

        limpo = _data(client.put(_DESC, json={"texto": None}))
        assert limpo["confirmado"] is None
        assert limpo["efetivo"] == lido["derivado"]
        assert client.get(f"/api/imoveis/{CODIGO}/dados").json()["descricao_imovel_texto"] is None

    def test_with_no_transcription_the_override_is_the_only_answer(self, client, scoped):
        seed(scoped, registry=[registry_row()])
        assert _data(client.get(_DESC))["derivado"] is None
        put = _data(client.put(_DESC, json={"texto": DESCRICAO_TIPADA}))
        assert (put["efetivo"], put["origem"]) == (DESCRICAO_TIPADA, "manual")

    def test_the_body_key_is_required(self, client, scoped):
        seed(scoped, registry=[registry_row()])
        assert client.put(_DESC, json={}).status_code == 422

    def test_an_unknown_imovel_is_a_404(self, client, scoped):
        seed(scoped)
        assert client.get("/api/matriculas/imoveis/NOPE9/descricao-imovel").status_code == 404


class TestUltimaTransferenciaTransmitentes:
    def test_typed_names_win_over_the_act_and_clear_with_the_override(self, client, scoped):
        hoje = date(2026, 10, 24)
        seed(scoped, registry=[registry_row()], extracoes=[extracao_row(texto=_texto_venda())])
        derivado = titulo_service.antigos_proprietarios(scoped, ORG, CODIGO, hoje=hoje)
        assert [t["nome"] for t in derivado["transmitentes"]] == ["ANTIGO DONO FICTICIO"]
        assert derivado["transmitentes_origem"] == "matricula"

        put = _data(
            client.put(
                _ULT,
                json={
                    "data": None,
                    "sem_registro": False,
                    "transmitentes": ["  Fulano   Ficticio ", "", "Beltrana Ficticia", "Fulano Ficticio"],
                },
            )
        )
        assert put["transmitentes"] == [
            {"nome": "Fulano Ficticio", "cpf_cnpj": None},
            {"nome": "Beltrana Ficticia", "cpf_cnpj": None},
        ]
        assert put["transmitentes_origem"] == "manual"
        assert put["manual"]["transmitentes"] == ["Fulano Ficticio", "Beltrana Ficticia"]
        # The act still answers WHEN — only WHO was typed.
        assert put["origem"] == "extracao"
        assert put["ultima_transferencia"]["data_registro"] == "2024-02-01"

        limpo = _data(client.put(_ULT, json={"data": None, "sem_registro": False}))
        assert limpo["manual"] is None
        assert limpo["transmitentes_origem"] == "matricula"
        rows = scoped.table("imovel_dados").select("*").execute().data
        assert rows[0]["ultima_transferencia_manual_transmitentes"] == []
        assert rows[0]["ultima_transferencia_manual_confirmado_em"] is None

    def test_names_with_a_date_ride_the_same_override(self, client, scoped):
        seed(scoped, registry=[registry_row()])
        put = _data(
            client.put(
                _ULT,
                json={"data": "2023-07-11", "natureza": "permuta", "sem_registro": False,
                      "transmitentes": ["Ciclano Ficticio"]},
            )
        )
        assert put["origem"] == "manual"
        assert put["transmitentes"] == [{"nome": "Ciclano Ficticio", "cpf_cnpj": None}]

    def test_names_next_to_sem_registro_are_refused(self, client, scoped):
        seed(scoped, registry=[registry_row()])
        resp = client.put(
            _ULT, json={"data": None, "sem_registro": True, "transmitentes": ["Fulano Ficticio"]}
        )
        assert resp.status_code == 400
        assert "transmitentes" in resp.text
