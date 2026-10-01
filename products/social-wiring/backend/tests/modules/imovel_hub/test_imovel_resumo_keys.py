"""Contract §0.1 — `ImovelResumo` additive keys on `busca_service`.

Additive only: every key the existing consumers (picker, roteiros, negociação)
read is still present and unchanged.
"""
from __future__ import annotations

from uuid import UUID

from app.modules.imovel_hub import busca_service
from tests.modules.imovel_hub.conftest import ORG_ID
from tests.modules.imovel_hub.relacionamentos_rows import espelho, registro, seed_tabelas

EXISTING = {
    "codigo", "titulo", "empreendimento", "logradouro", "numero", "complemento",
    "bairro", "cidade", "uf", "cep", "foto_destaque", "corretores", "captacao",
    "ativo_no_vista", "origem", "registrado", "fonte",
}
ADDED = {
    "categoria", "valor_venda", "valor_locacao", "dormitorios", "suites", "vagas",
    "area_total", "area_privativa", "area_construida", "endereco", "valor", "valor_tipo",
}


def enriquecer(scoped, *codigos):
    return busca_service.enriquecer(scoped, UUID(ORG_ID), list(codigos))


def test_mirror_backed_resumo_has_existing_and_additive_keys(client, scoped):
    seed_tabelas(scoped, imovel_registry=[registro("ONE1")], imoveis=[espelho("ONE1")], imovel_dados=[])
    r = enriquecer(scoped, "ONE1")["ONE1"]
    assert set(r) == EXISTING | ADDED
    assert r["fonte"] == "imoveis" and r["complemento"] == "apto 91"
    assert (r["categoria"], r["dormitorios"], r["suites"], r["vagas"]) == ("Apartamento", 3, 1, 2)
    # money/areas are JSON numbers, never the driver's Decimal/str
    assert r["valor_venda"] == 850000.0 and isinstance(r["valor_venda"], float)
    assert r["area_total"] == 120.0 and r["area_privativa"] == 98.0 and r["area_construida"] is None
    assert r["valor"] == 850000.0 and r["valor_tipo"] == "venda"
    assert r["endereco"] == "Rua das Palmeiras, 320 — Pinheiros, São Paulo/SP"


def test_locacao_is_the_valor_fallback(client, scoped):
    seed_tabelas(scoped, imovel_registry=[registro("L1")],
                 imoveis=[espelho("L1", valor_venda=None, valor_locacao="4500.00")], imovel_dados=[])
    r = enriquecer(scoped, "L1")["L1"]
    assert (r["valor"], r["valor_tipo"], r["valor_venda"], r["valor_locacao"]) == (4500.0, "locacao", None, 4500.0)


def test_endereco_drops_missing_parts_with_their_separators(client, scoped):
    seed_tabelas(scoped, imovel_registry=[registro("E1"), registro("E2")], imovel_dados=[],
                 imoveis=[espelho("E1", logradouro=None, numero=None, uf=None),
                          espelho("E2", logradouro="Rua A", numero=None, bairro=None, cidade=None, uf=None)])
    out = enriquecer(scoped, "E1", "E2")
    assert out["E1"]["endereco"] == "Pinheiros, São Paulo"
    assert out["E2"]["endereco"] == "Rua A"


def test_registry_only_imovel_falls_back_to_the_snapshot_and_nulls(client, scoped):
    seed_tabelas(
        scoped, imoveis=[], imovel_dados=[],
        imovel_registry=[registro(
            "OLD1", ativo_no_vista=False, snap_titulo="Casa vendida", snap_bairro="Mooca",
            snap_cidade="São Paulo", snap_uf="SP", snap_categoria="Casa",
            snap_valor_venda="500000.00", snap_dormitorios=2, snap_area_total="80.00",
        )],
    )
    r = enriquecer(scoped, "OLD1")["OLD1"]
    assert set(r) == EXISTING | ADDED  # never a missing key
    assert r["fonte"] == "registry"
    assert (r["categoria"], r["valor"], r["valor_tipo"], r["dormitorios"], r["area_total"]) == ("Casa", 500000.0, "venda", 2, 80.0)
    assert r["suites"] is None and r["vagas"] is None and r["area_privativa"] is None
    assert r["endereco"] == "Mooca, São Paulo/SP"  # no logradouro/numero for a delisted imóvel


def test_unregistered_codigo_still_carries_every_key_as_null(client, scoped):
    seed_tabelas(scoped, imovel_registry=[], imoveis=[], imovel_dados=[])
    # `enriquecer` only answers for what it is asked about
    r = busca_service._imovel_out("X1", None, None, None, {})
    assert set(r) == EXISTING | ADDED and r["fonte"] == "nenhuma"
    assert r["endereco"] is None and r["valor"] is None and r["valor_tipo"] is None
