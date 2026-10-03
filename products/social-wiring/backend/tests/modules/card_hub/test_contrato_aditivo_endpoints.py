"""Aditivo routes (migration 190) over the mock DB, real loaders.

WHAT THESE PIN
--------------
- an aditivo can only be created on a signed (or dated) contract — 409
  `CONTRATO_ORIGINAL_NAO_ASSINADO`, nothing written, otherwise;
- create assigns ordinal 1, 2, … and stores the structured amendments + the
  restated schedule; a PATCH replaces either list; content is frozen once
  the aditivo is assinado (409 `ADITIVO_CONGELADO`);
- GET .../geracao on the fully-seeded V1 card is `pronto`; POST .../gerar
  saves a version: origem 'gerado', real PDF + .docx sibling on ONE row,
  contexto_sha256, and — always — awaiting the legal review;
- an incomplete aditivo is refused with 400 `ADITIVO_INCOMPLETO` carrying
  the same faltando/bloqueios the GET reported (nothing saved);
- "Baixar para impressão" and a jump to a final status are refused while
  the version awaits review; the admin-only approval stamps it and lifts
  both;
- the request bodies are strict (an unknown key is a 422).

All data is synthetic (`test_contrato_gerador_endpoints._seed_completo`).
"""
from __future__ import annotations

import asyncio
import re

from noctusai_lib.testing import TEST_USER_ID

from app.modules.card_hub.contrato_gerador.service import hoje
from app.modules.card_hub.deps import BUCKET
from tests.modules.card_hub.conftest import ORG_ID
from tests.modules.card_hub.test_contrato_gerador_endpoints import (
    _auth,
    _contrato_over,
    _rows,
    _seed_completo,
)

_TABELAS_ADITIVO = (
    "atendimento_contrato_aditivos",
    "atendimento_contrato_aditivo_parcelas",
    "atendimento_contrato_aditivo_versoes",
    "atendimento_contrato_aditivo_versao_acessos",
)

POSSE = {"tipo": "posse", "clausula_alvo": 5, "data": "2026-12-15", "precaria": False}
PAGAMENTO = {"tipo": "pagamento", "clausula_alvo": 2}


def _seed(scoped, *, assinado: bool = True) -> dict:
    ids = _seed_completo(scoped)
    for tabela in _TABELAS_ADITIVO:
        scoped.set_table_data(tabela, [])
    if assinado:
        _contrato_over(scoped, ids, status="assinado", assinatura_data="2026-03-10")
    return ids


def _base(ids: dict) -> str:
    return f"/api/clientes/{ids['cliente']}/contratos/{ids['contrato']}/aditivos"


def _criar(client, ids, **body):
    payload = {"alteracoes": [POSSE], **body}
    return client.post(_base(ids), json=payload, headers=_auth())


def _parcelas(ids: dict) -> list[dict]:
    """The V1 price (500 000) re-split — same favorecido as the original."""
    return [
        {"tipo": "sinal", "valor": "50000.00", "evento": "quitada anteriormente",
         "forma_pagamento": "PIX", "favorecido_id": ids["fav_vendedor"]},
        {"tipo": "direta", "valor": "50000.00", "evento": "na assinatura do presente aditivo",
         "forma_pagamento": "PIX", "favorecido_id": ids["fav_vendedor"]},
        {"tipo": "financiamento", "valor": "400000.00",
         "evento": "com prazo máximo de 90 (noventa) dias corridos, a contar da assinatura deste aditivo"},
    ]


def _make_admin(client) -> None:
    client.mock_supabase.set_table_data(
        "noctus_users", [{"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": "owner"}]
    )


class TestCriar:
    def test_an_unsigned_contract_refuses_an_aditivo_and_writes_nothing(self, client, scoped):
        ids = _seed(scoped, assinado=False)
        r = _criar(client, ids)
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "CONTRATO_ORIGINAL_NAO_ASSINADO"
        assert _rows(scoped, "atendimento_contrato_aditivos") == []

    def test_a_dated_contract_admits_an_aditivo(self, client, scoped):
        ids = _seed(scoped, assinado=False)
        _contrato_over(scoped, ids, assinatura_data="2026-03-10")
        assert _criar(client, ids).status_code == 201

    def test_ordinals_are_assigned_in_sequence_and_listed(self, client, scoped):
        ids = _seed(scoped)
        a = _criar(client, ids).json()
        b = _criar(client, ids, estilo="formal").json()
        assert (a["ordinal"], b["ordinal"]) == (1, 2)
        assert b["estilo"] == "formal" and a["status"] == "rascunho"
        lista = client.get(_base(ids), headers=_auth()).json()["aditivos"]
        assert [x["ordinal"] for x in lista] == [1, 2]
        assert lista[0]["alteracoes"][0]["tipo"] == "posse"

    def test_the_restated_schedule_is_stored_structured(self, client, scoped):
        ids = _seed(scoped)
        r = _criar(client, ids, alteracoes=[PAGAMENTO], parcelas=_parcelas(ids))
        assert r.status_code == 201, r.text
        corpo = r.json()
        assert [p["tipo"] for p in corpo["parcelas"]] == ["sinal", "direta", "financiamento"]
        assert [p["ordem"] for p in corpo["parcelas"]] == [0, 1, 2]
        assert len(_rows(scoped, "atendimento_contrato_aditivo_parcelas")) == 3

    def test_an_unknown_key_is_a_422(self, client, scoped):
        ids = _seed(scoped)
        assert _criar(client, ids, inventado=True).status_code == 422

    def test_a_precarious_posse_without_a_purpose_is_a_422(self, client, scoped):
        ids = _seed(scoped)
        r = _criar(client, ids, alteracoes=[{**POSSE, "precaria": True}])
        assert r.status_code == 422

    def test_a_permuta_parcela_is_not_accepted(self, client, scoped):
        ids = _seed(scoped)
        r = _criar(client, ids, alteracoes=[PAGAMENTO], parcelas=[{"tipo": "permuta", "valor": "1.00"}])
        assert r.status_code == 422


class TestAtualizar:
    def test_a_patch_replaces_the_lists(self, client, scoped):
        ids = _seed(scoped)
        ad = _criar(client, ids).json()
        r = client.patch(
            f"{_base(ids)}/{ad['id']}",
            json={"alteracoes": [PAGAMENTO], "parcelas": _parcelas(ids)},
            headers=_auth(),
        )
        assert r.status_code == 200, r.text
        assert [a["tipo"] for a in r.json()["alteracoes"]] == ["pagamento"]
        assert len(r.json()["parcelas"]) == 3
        r = client.patch(f"{_base(ids)}/{ad['id']}", json={"parcelas": []}, headers=_auth())
        assert r.json()["parcelas"] == []

    def test_a_signed_aditivo_is_frozen(self, client, scoped):
        ids = _seed(scoped)
        ad = _criar(client, ids).json()
        scoped.set_table_data(
            "atendimento_contrato_aditivos",
            [{**_rows(scoped, "atendimento_contrato_aditivos")[0], "status": "assinado"}],
        )
        r = client.patch(f"{_base(ids)}/{ad['id']}", json={"estilo": "formal"}, headers=_auth())
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "ADITIVO_CONGELADO"

    def test_another_contracts_aditivo_is_404(self, client, scoped):
        ids = _seed(scoped)
        ad = _criar(client, ids).json()
        outro = {**ids, "contrato": "00000000-0000-0000-0000-000000000000"}
        assert client.patch(f"{_base(outro)}/{ad['id']}", json={}, headers=_auth()).status_code == 404


class TestGerar:
    def test_an_incomplete_aditivo_is_refused_with_the_same_lists(self, client, scoped, fake_storage):
        ids = _seed(scoped)
        ad = _criar(client, ids, alteracoes=[PAGAMENTO]).json()  # no parcelas
        geracao = client.get(f"{_base(ids)}/{ad['id']}/geracao", headers=_auth()).json()
        assert geracao["pronto"] is False
        r = client.post(f"{_base(ids)}/{ad['id']}/gerar", json={}, headers=_auth())
        assert r.status_code == 400, r.text
        erro = r.json()["error"]
        assert erro["code"] == "ADITIVO_INCOMPLETO"
        assert [f["campo"] for f in erro["details"]["faltando"]] == [f["campo"] for f in geracao["faltando"]]
        assert _rows(scoped, "atendimento_contrato_aditivo_versoes") == []

    def test_the_sum_gate_refuses_a_schedule_off_the_price(self, client, scoped, fake_storage):
        ids = _seed(scoped)
        parcelas = _parcelas(ids)
        parcelas[1]["valor"] = "1000.00"
        ad = _criar(client, ids, alteracoes=[PAGAMENTO], parcelas=parcelas).json()
        geracao = client.get(f"{_base(ids)}/{ad['id']}/geracao", headers=_auth()).json()
        assert "SOMA_PARCELAS_DIFERENTE_DO_PRECO" in {b["codigo"] for b in geracao["bloqueios"]}

    def test_a_ready_aditivo_is_saved_as_a_generated_version_awaiting_review(
        self, client, scoped, fake_storage
    ):
        ids = _seed(scoped)
        ad = _criar(client, ids, alteracoes=[PAGAMENTO, POSSE], parcelas=_parcelas(ids)).json()
        geracao = client.get(f"{_base(ids)}/{ad['id']}/geracao", headers=_auth()).json()
        assert geracao["pronto"] is True, (geracao["faltando"], geracao["bloqueios"])
        assert geracao["revisao_juridica_exigida"] is True

        r = client.post(
            f"{_base(ids)}/{ad['id']}/gerar",
            json={"assinatura_data": hoje().isoformat()},
            headers=_auth(),
        )
        assert r.status_code == 201, r.text
        versao = r.json()["versao"]
        assert versao["origem"] == "gerado" and versao["numero"] == 1
        assert versao["docx_disponivel"] is True
        assert versao["revisao_juridica"]["status"] == "aguardando"

        linhas = _rows(scoped, "atendimento_contrato_aditivo_versoes")
        assert len(linhas) == 1
        assert re.fullmatch(r"[0-9a-f]{64}", linhas[0]["contexto_sha256"])
        assert linhas[0]["docx_storage_path"] == f"{linhas[0]['storage_path']}.docx"
        pdf = asyncio.run(fake_storage.get(bucket=BUCKET, key=linhas[0]["storage_path"]))
        docx = asyncio.run(fake_storage.get(bucket=BUCKET, key=linhas[0]["docx_storage_path"]))
        assert pdf.data[:5] == b"%PDF-" and docx.data[:4] == b"PK\x03\x04"

        versoes = client.get(f"{_base(ids)}/{ad['id']}/versoes", headers=_auth()).json()["versoes"]
        assert [v["numero"] for v in versoes] == [1]


class TestRevisaoJuridica:
    def _gerado(self, client, scoped) -> tuple[dict, dict, dict]:
        ids = _seed(scoped)
        ad = _criar(client, ids).json()
        r = client.post(f"{_base(ids)}/{ad['id']}/gerar", json={"assinatura_data": hoje().isoformat()}, headers=_auth())
        assert r.status_code == 201, r.text
        return ids, ad, r.json()["versao"]

    def test_print_and_final_status_wait_for_the_review_then_the_admin_approves(
        self, client, scoped, fake_storage
    ):
        ids, ad, versao = self._gerado(client, scoped)
        url = f"{_base(ids)}/{ad['id']}/versoes/{versao['id']}"

        assert client.get(f"{url}/url?impressao=true", headers=_auth()).status_code == 409
        assert client.get(f"{url}/url", headers=_auth()).status_code == 200
        assert client.get(f"{url}/url?formato=docx", headers=_auth()).status_code == 200
        r = client.patch(f"{_base(ids)}/{ad['id']}", json={"status": "enviado_assinatura"}, headers=_auth())
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "CONTRATO_AGUARDANDO_REVISAO_JURIDICA"

        # A member is not enough — the trusted DB role decides.
        assert client.post(f"{url}/revisao-juridica", headers=_auth()).status_code == 403
        _make_admin(client)
        r = client.post(f"{url}/revisao-juridica", headers=_auth())
        assert r.status_code == 200, r.text
        assert r.json()["versao_atual"]["revisao_juridica"]["status"] == "aprovada"
        assert client.post(f"{url}/revisao-juridica", headers=_auth()).status_code == 409

        assert client.get(f"{url}/url?impressao=true", headers=_auth()).status_code == 200
        r = client.patch(f"{_base(ids)}/{ad['id']}", json={"status": "enviado_assinatura"}, headers=_auth())
        assert r.status_code == 200 and r.json()["status"] == "enviado_assinatura"
        assert len(_rows(scoped, "atendimento_contrato_aditivo_versao_acessos")) >= 3
