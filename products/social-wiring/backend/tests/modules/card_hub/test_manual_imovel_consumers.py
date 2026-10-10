"""A MANUAL imóvel (migration 226, `SW-NNNN`) in the card_hub consumers.

Roteiros (visita creation with an SW código) and propostas (create + render)
resolve the imóvel through the REGISTRY and render it through
`busca_service.enriquecer` — a manual imóvel has no mirror row and no `snap_*`,
so these prove the title and address come from `imovel_captacao` +
`imovel_dados`, and that every Vista-only key is null/empty, never missing.
"""
from __future__ import annotations

from uuid import uuid4

from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.propostas.test_propostas import _auth, _nova, _seed
from tests.modules.card_hub.test_roteiros import _criar, registry_row


def _com_manual(scoped) -> None:
    reg = registry_row("SW-0001", ativo=False)
    reg["origem_descoberta"] = "manual"
    scoped.set_table_data(
        "imovel_registry", [*scoped.table("imovel_registry").select("*").execute().data, reg]
    )
    scoped.set_table_data(
        "imovel_captacao",
        [{"org_id": ORG_ID, "codigo_canonical": "SW-0001", "titulo": "Casa Reserva do Vianna",
          "categoria": "Casa", "valor_venda": 1500000}],
    )
    scoped.set_table_data(
        "imovel_dados",
        [{"org_id": ORG_ID, "codigo": "SW-0001", "endereco_manual_logradouro": "Alameda Liverpool",
          "endereco_manual_numero": "81", "endereco_manual_bairro": "Reserva do Vianna",
          "endereco_manual_cidade": "Cotia", "endereco_manual_uf": "SP"}],
    )


def test_roteiro_visita_com_codigo_sw_renderiza_titulo_e_endereco(client, scoped):
    cid, _ = _seed(scoped)
    _com_manual(scoped)
    roteiro = _criar(client, cid, ["sw-0001"])
    imovel = roteiro["visitas"][0]["imovel"]
    assert roteiro["visitas"][0]["codigo"] == "SW-0001"
    assert imovel["fonte"] == "manual"
    assert imovel["titulo"] == "Casa Reserva do Vianna"
    assert imovel["logradouro"] == "Alameda Liverpool" and imovel["bairro"] == "Reserva do Vianna"
    assert imovel["endereco"] == "Alameda Liverpool, 81 — Reserva do Vianna, Cotia/SP"
    assert imovel["foto_destaque"] is None and imovel["corretores"] == []


def test_proposta_para_um_imovel_manual_renderiza_titulo_e_endereco(client, scoped):
    cid, _ = _seed(scoped)
    _com_manual(scoped)
    p = _nova(client, cid, imovel_codigo="sw-0001")
    assert p["imovel_codigo"] == "SW-0001"
    assert p["imovel"]["titulo"] == "Casa Reserva do Vianna"
    assert p["imovel"]["endereco"].startswith("Alameda Liverpool 81")
    # the proposta prefill reads the manual imóvel's price like a Vista one
    assert float(p["valor_proposto"]) == 1500000
