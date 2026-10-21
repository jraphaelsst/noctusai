"""Julia v2 SW ferramentas over HTTP: structured `buscar_imoveis`, `similar_a`, `excluir_codigos`,
`imovel_campanha`, IP hygiene, the CONTRACT with what agents sends, and the stage proxy.

Reuses the fixtures of the router test module (auth matrix lives there)."""
from __future__ import annotations

import ast
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from tests.routers.test_julia_ferramentas_router import _ORG, _OTHER, _product, _row, catalogo, ok, tools  # noqa: F401

# Provider paths this test reads (gate_sweep runs it when one changes; KB self-branching-mode, CONTRACT_OF).
CONTRACT_OF = ("products/agents/backend/app/channels/tool_registry.py",)
REPO = Path(__file__).resolve().parents[5]
AGENTS_REGISTRY = REPO / "products/agents/backend/app/channels/tool_registry.py"


def _buscar(ok, **body):
    r = ok.post("buscar_imoveis", {"operacao": "compra", **body})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def vitrine(tools, catalogo):  # noqa: F811
    catalogo.set_table_data("imoveis", [
        _row("CAMP", empreendimento="Cond Alfa", valor_venda=1_000_000, caracteristicas=["piscina", "aceita pets"]),
        _row("IRMA", empreendimento="Cond Alfa", valor_venda=1_050_000, caracteristicas=["piscina"]),
        _row("VIZ", bairro="Granja Viana", valor_venda=950_000, caracteristicas=["sauna", "churrasqueira", "piscina", "quadra"]),
        _row("APT", categoria="Apartamento", valor_venda=980_000),
        _row("CARO", valor_venda=3_000_000),
        _row("OTH", org=_OTHER),
    ])
    tools.as_ctx(_product())
    return tools


class TestBuscarV2:
    def test_similar_a_anchors_type_region_price_and_ranks_the_same_condominio_first(self, vitrine):
        r = _buscar(vitrine, similar_a="camp", limite=2)
        got = [d["codigo"] for d in r["data"]]
        assert got == ["IRMA", "VIZ"] and r["relaxado"] == []  # CAMP itself is never "similar"  # the campaign listing itself is never "similar"
        assert "APT" not in got and "CARO" not in got and r["similar_a_encontrado"] is True

    def test_similar_a_unknown_is_reported_not_guessed(self, vitrine):
        r = _buscar(vitrine, similar_a="NADA", limite=2)
        assert r["similar_a_encontrado"] is False and len(r["data"]) == 2

    def test_excluir_codigos_and_limite(self, vitrine):
        r = _buscar(vitrine, excluir_codigos=["irma", "VIZ"], limite=5)
        assert not {d["codigo"] for d in r["data"]} & {"IRMA", "VIZ"}
        assert len(_buscar(vitrine, limite=2)["data"]) == 2

    def test_restantes_estimados_and_relaxado(self, vitrine):
        r = _buscar(vitrine, tipo="casa", limite=1)
        assert r["relaxado"] == [] and r["restantes_estimados"] == 3  # CAMP, IRMA, VIZ, CARO minus the one returned
        r = _buscar(vitrine, preco_max=900_000, tipo="casa", limite=3)
        assert r["relaxado"] and "preco" in r["relaxado"]

    def test_essential_items_and_nice_to_haves(self, vitrine):
        r = _buscar(vitrine, itens_essenciais=["churrasqueira"], limite=3)
        assert [d["codigo"] for d in r["data"]] == ["VIZ"]
        # the catalogue has no pet field: a pets must-have never empties the result, it is reported instead
        r = _buscar(vitrine, itens_essenciais=["pets"], limite=3)
        assert len(r["data"]) == 3 and r["itens_nao_verificaveis"] == ["pets"]
        r = _buscar(vitrine, tipo="casa", itens_desejaveis=["sauna"], limite=1)
        assert r["data"][0]["codigo"] == "VIZ"  # the nice-to-have ranks first

    def test_the_card_has_only_what_the_listing_has_and_factual_highlights(self, vitrine, catalogo):
        catalogo.set_table_data("imoveis", [_row("Z1", suites=None, valor_condominio=None, valor_iptu=None, vagas=None,
                                                  caracteristicas=["a", "b", "c", "d"], empreendimento=None)])
        d = _buscar(vitrine)["data"][0]
        assert d["destaques"] == ["a", "b", "c"]
        for ausente in ("suites", "valor_condominio", "valor_iptu", "vagas", "condominio", "link", "preco_aluguel"):
            assert ausente not in d

    def test_condominio_and_iptu_are_returned_when_known_and_omitted_when_not(self, vitrine, catalogo):
        d = _buscar(vitrine)["data"][0]
        assert d["valor_condominio"] == 1200.0 and d["valor_iptu"] == 450.0  # no org opt-in needed in a search result
        catalogo.set_table_data("imoveis", [_row("SEM", valor_iptu=None, valor_condominio=None)])
        d = _buscar(vitrine)["data"][0]
        assert "valor_iptu" not in d and "valor_condominio" not in d

    @pytest.mark.parametrize("tipo,categorias", [
        ("casa", {"Casa", "Casa em Condomínio"}), ("casa_condominio", {"Casa em Condomínio"}),
        ("apartamento", {"Apartamento", "Cobertura"}), ("terreno", {"Terreno"}), ("comercial", {"Sala Comercial"}),
    ])
    def test_the_standard_tipo_values_map_to_the_catalogue_categories(self, vitrine, catalogo, tipo, categorias):
        todas = ["Casa", "Casa em Condomínio", "Apartamento", "Cobertura", "Terreno", "Sala Comercial"]
        catalogo.set_table_data("imoveis", [_row(f"C{i}", categoria=c) for i, c in enumerate(todas)])
        r = _buscar(vitrine, tipo=tipo, limite=len(categorias))
        assert {d["tipo"] for d in r["data"]} == categorias and r["relaxado"] == []

    @pytest.mark.parametrize("corpo", [
        {"preco_min": 2, "preco_max": 1}, {"limite": 0}, {"excluir_codigos": ["x"] * 201}, {"itens_essenciais": ["y" * 121]},
        {"prompt": "x"}, {"regras": []},
    ])
    def test_bad_bodies_are_typed_422(self, vitrine, corpo):
        r = vitrine.post("buscar_imoveis", {"operacao": "compra", **corpo})
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_field"

    def test_no_prompt_rule_or_owner_text_in_the_response(self, vitrine):
        body = vitrine.post("buscar_imoveis", {"operacao": "compra", "similar_a": "CAMP"}).text.lower()
        assert not any(w in body for w in ("prompt", "regra", "instru", "proprietario"))


class TestImovelCampanha:
    def test_by_codigo(self, vitrine):
        data = vitrine.post("imovel_campanha", {"codigo": "camp"}).json()["data"]
        assert [d["codigo"] for d in data] == ["CAMP"] and data[0]["preco"] == 1_000_000.0

    def test_unknown_unpublished_or_foreign_is_an_empty_list(self, vitrine):
        for c in ("NADA", "OTH"):
            assert vitrine.post("imovel_campanha", {"codigo": c}).json()["data"] == []

    def test_resolved_from_the_contato_through_the_interacao(self, vitrine, catalogo):
        iid, cid = uuid4(), uuid4()
        catalogo.set_table_data("julia_interacoes", [{"id": str(iid), "org_id": str(_ORG), "contato_id": str(cid)}])
        catalogo.set_table_data("julia_contatos", [{"id": str(cid), "org_id": str(_ORG), "codigo_imovel_campanha": "irma"}])
        data = vitrine.post("imovel_campanha", {"interacao_id": str(iid)}).json()["data"]
        assert [d["codigo"] for d in data] == ["IRMA"]

    def test_another_orgs_interacao_resolves_nothing(self, vitrine, catalogo):
        iid, cid = uuid4(), uuid4()
        catalogo.set_table_data("julia_interacoes", [{"id": str(iid), "org_id": str(_OTHER), "contato_id": str(cid)}])
        catalogo.set_table_data("julia_contatos", [{"id": str(cid), "org_id": str(_OTHER), "codigo_imovel_campanha": "CAMP"}])
        assert vitrine.post("imovel_campanha", {"interacao_id": str(iid)}).json()["data"] == []

    def test_needs_a_codigo_or_an_interacao(self, vitrine):
        r = vitrine.post("imovel_campanha", {})
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_field"


# ── the contract with what agents really sends ───────────────────────────────
def _agents_sw_keys() -> dict[str, set[str]]:
    """Statically read agents' `tool_registry.py`: the keys it puts in each SW tool call. No cross-product import."""
    tree = ast.parse(AGENTS_REGISTRY.read_text())
    keys: dict[str, set[str]] = {"buscar_imoveis": set(), "imovel_campanha": set()}
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name == "_consulta_sw":
            for n in ast.walk(fn):
                if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id == "q" and isinstance(n.slice, ast.Constant):
                    keys["buscar_imoveis"].add(n.slice.value)
                if isinstance(n, ast.Tuple):  # the (src, dst) tables: every dst is a key sent to SW
                    for e in n.elts:
                        if (isinstance(e, ast.Tuple) and len(e.elts) == 2
                                and all(isinstance(x, ast.Constant) and isinstance(x.value, str) for x in e.elts)):
                            keys["buscar_imoveis"].add(e.elts[1].value)
        if isinstance(fn, ast.AsyncFunctionDef) and fn.name == "_oferecer":
            for n in ast.walk(fn):
                if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id == "args" and isinstance(n.slice, ast.Constant):
                    keys["buscar_imoveis"].add(n.slice.value)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_sw" and n.args:
                    nome, corpo = n.args[0], n.args[1] if len(n.args) > 1 else None
                    if isinstance(nome, ast.Constant) and nome.value == "imovel_campanha" and isinstance(corpo, ast.Dict):
                        keys["imovel_campanha"] |= {k.value for k in corpo.keys if isinstance(k, ast.Constant)}
    return keys


class TestContractWithAgents:
    def test_every_key_agents_sends_is_accepted_by_the_sw_schema(self):
        from app.services.julia_ferramentas_service import ARGS

        sent = _agents_sw_keys()
        assert {"operacao", "tipo", "preco_max", "quartos_min", "vagas_min", "bairros", "caracteristicas",
                "similar_a", "excluir_codigos", "limite"} <= sent["buscar_imoveis"], sent
        assert sent["imovel_campanha"] == {"codigo"}
        for nome, chaves in sent.items():
            assert chaves <= set(ARGS[nome].model_fields), (nome, chaves - set(ARGS[nome].model_fields))

    def test_a_query_shaped_exactly_like_agents_sends_it_round_trips(self, vitrine):
        corpo = {"operacao": "compra", "tipo": "Casa", "preco_min": 900000, "preco_max": 1000000, "quartos_min": 3,
                 "vagas_min": 2, "bairros": ["Granja Viana"], "caracteristicas": ["piscina"], "similar_a": "CAMP",
                 "excluir_codigos": ["IRMA"], "limite": 3, "interacao_id": str(uuid4())}
        r = vitrine.post("buscar_imoveis", corpo)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["data"], list) and "restantes_estimados" in body  # what agents reads from the body

    def test_agents_reads_data_and_forwards_every_sw_meta_key_from_the_body(self):
        src = AGENTS_REGISTRY.read_text()
        assert 'body.get("data")' in src
        [meta] = [n.value for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "_BUSCA_META" for t in n.targets)]
        forwarded = {e.value for e in meta.elts}  # the explicit allowlist agents forwards to the model
        assert {"restantes_estimados", "relaxado", "similar_a_encontrado", "itens_nao_verificaveis"} <= forwarded
