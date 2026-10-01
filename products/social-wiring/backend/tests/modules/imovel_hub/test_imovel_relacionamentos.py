"""Imóvel-side relationship reads: Interessados (§4.3) and Similares (§4.4)."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from tests.modules.imovel_hub.conftest import ORG_ID, auth
from tests.modules.imovel_hub.relacionamentos_rows import (
    atendimento_row,
    cliente_row,
    espelho,
    interesse,
    lead_row,
    meta_row,
    registro,
    seed_tabelas,
    touch_row,
)

ROW_KEYS = {
    "interesse_id", "cliente_id", "nome", "telefone", "email", "origem",
    "interesse_created_at", "lead_created_at", "ultima_interacao_em",
    "tem_atendimento_aberto", "atendimento_aberto_id",
}


class TestInteressados:
    @pytest.fixture
    def cenario(self, client, scoped):
        ana = cliente_row(nome="Ana", celular="+5511900000001", email="ana@x.com", nome_oficial="Ana Oficial")
        beto = cliente_row(nome="Beto", celular=None, email=None, chave_canonica="+5511900000002")
        caio = cliente_row(nome="Caio", celular="+5511900000003")
        lead = lead_row(codigo="ONE1", created_at="2026-01-10T00:00:00+00:00")
        meta = meta_row(codigo="ONE1", created_time="2026-01-20T00:00:00+00:00")
        # Ana: has an OPEN atendimento + a recent touch; Beto: only an archived one;
        # Caio: nothing but a manual interesse (no touches at all).
        aberto = atendimento_row(cliente_id=ana["id"])
        arquivado = atendimento_row(cliente_id=beto["id"], arquivado=True)
        seed_tabelas(
            scoped,
            clientes=[ana, beto, caio],
            leads=[lead],
            meta_ads_leads=[meta],
            imovel_registry=[registro("ONE1")],
            imoveis=[espelho("ONE1")],
            imovel_dados=[],
            atendimentos=[aberto, arquivado],
            atendimento_partes=[],
            cliente_touches=[
                touch_row(ana["id"], ocorreu_em="2026-03-01T00:00:00+00:00"),
                touch_row(ana["id"], ocorreu_em="2026-02-01T00:00:00+00:00"),
                touch_row(beto["id"], ocorreu_em="2026-02-15T00:00:00+00:00"),
            ],
            cliente_imovel_interesses=[
                interesse(ana["id"], "ONE1", origem="lead", lead_id=lead["id"], created_at="2026-01-10T00:00:00+00:00"),
                interesse(beto["id"], "ONE1", origem="lead", meta_ads_lead_id=meta["id"], created_at="2026-01-20T00:00:00+00:00"),
                interesse(caio["id"], "ONE1", origem="manual", created_at="2026-03-05T00:00:00+00:00"),
                interesse(uuid4(), "ONE1", deleted_at="2026-03-01T00:00:00+00:00"),
            ],
        )
        return {"ana": ana, "beto": beto, "caio": caio, "aberto": aberto, "lead": lead, "meta": meta}

    def test_exact_shape_total_and_sort(self, client, cenario):
        resp = client.get("/api/imoveis/one1/interessados", headers=auth())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body) == {"items", "total"}
        assert body["total"] == 3  # the deleted row is not counted
        assert all(set(r) == ROW_KEYS for r in body["items"])
        # last interaction DESC, NULLS LAST: Ana (03-01), Beto (02-15), Caio (never)
        assert [r["nome"] for r in body["items"]] == ["Ana Oficial", "Beto", "Caio"]

    def test_fields(self, client, cenario):
        rows = {r["nome"]: r for r in client.get("/api/imoveis/ONE1/interessados", headers=auth()).json()["items"]}
        ana, beto, caio = rows["Ana Oficial"], rows["Beto"], rows["Caio"]
        assert ana["telefone"] == "+5511900000001" and ana["email"] == "ana@x.com"
        assert beto["telefone"] == "+5511900000002"  # celular absent → chave_canonica
        assert ana["ultima_interacao_em"] == "2026-03-01T00:00:00+00:00"
        assert caio["ultima_interacao_em"] is None
        assert ana["lead_created_at"] == "2026-01-10T00:00:00+00:00"
        assert beto["lead_created_at"] == "2026-01-20T00:00:00+00:00"  # the Meta created_time
        assert caio["lead_created_at"] is None
        assert ana["origem"] == "lead" and caio["origem"] == "manual"
        assert ana["tem_atendimento_aberto"] is True
        assert ana["atendimento_aberto_id"] == cenario["aberto"]["id"]
        assert beto["tem_atendimento_aberto"] is False and beto["atendimento_aberto_id"] is None
        assert caio["tem_atendimento_aberto"] is False

    def test_collapsed_atendimento_is_not_open(self, client, cenario, scoped):
        colapsado = atendimento_row(cliente_id=cenario["caio"]["id"], substituida_por=cenario["aberto"]["id"])
        scoped.set_table_data("atendimentos", [cenario["aberto"], colapsado])
        rows = {r["nome"]: r for r in client.get("/api/imoveis/ONE1/interessados", headers=auth()).json()["items"]}
        assert rows["Caio"]["tem_atendimento_aberto"] is False

    def test_party_atendimento_counts_as_open(self, client, cenario, scoped):
        outro = atendimento_row(cliente_id=str(uuid4()))
        scoped.set_table_data("atendimentos", [cenario["aberto"], outro])
        scoped.set_table_data(
            "atendimento_partes",
            [{"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": outro["id"],
              "cliente_id": cenario["caio"]["id"], "empresa_id": None, "lado": "comprador"}],
        )
        rows = {r["nome"]: r for r in client.get("/api/imoveis/ONE1/interessados", headers=auth()).json()["items"]}
        assert rows["Caio"]["atendimento_aberto_id"] == outro["id"]

    def test_pagination(self, client, cenario):
        p1 = client.get("/api/imoveis/ONE1/interessados", params={"limit": 2}, headers=auth()).json()
        p2 = client.get("/api/imoveis/ONE1/interessados", params={"limit": 2, "offset": 2}, headers=auth()).json()
        assert p1["total"] == p2["total"] == 3
        assert [r["nome"] for r in p1["items"]] == ["Ana Oficial", "Beto"]
        assert [r["nome"] for r in p2["items"]] == ["Caio"]

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
    def test_bad_paging_is_422(self, client, cenario, params):
        assert client.get("/api/imoveis/ONE1/interessados", params=params, headers=auth()).status_code == 422

    def test_unknown_codigo_404(self, client, cenario):
        resp = client.get("/api/imoveis/NOPE/interessados", headers=auth())
        assert resp.status_code == 404 and resp.json()["error"]["code"] == "NOT_FOUND"

    def test_empty_list_for_an_imovel_nobody_asked_about(self, client, cenario, scoped):
        scoped.set_table_data("imovel_registry", [registro("ONE1"), registro("ONE9")])
        assert client.get("/api/imoveis/ONE9/interessados", headers=auth()).json() == {"items": [], "total": 0}


SIMILAR_KEYS_EXTRA = {"score", "justificativa", "reasons", "detalhes", "score_breakdown"}


class TestSimilares:
    """§4.4 — the shared permutas engine over the catalog mirror."""

    @pytest.fixture
    def cenario(self, client, scoped):
        alvo = espelho("ONE1")
        parecido = espelho("ONE2", valor_venda="820000.00", dormitorios=3, area_privativa="95.00", area_total="118.00")
        # same city, wildly different profile
        diferente = espelho("ONE3", categoria="Casa", bairro="Mooca", valor_venda="190000.00",
                            dormitorios=1, suites=0, vagas=0, area_total="35.00", area_privativa="30.00")
        # IDENTICAL profile but another city/state — outside the pool by construction
        outra_cidade = espelho("ONE4", cidade="Campinas")
        seed_tabelas(
            scoped,
            imovel_registry=[registro(c) for c in ("ONE1", "ONE2", "ONE3", "ONE4", "GONE5")],
            imoveis=[alvo, parecido, diferente, outra_cidade],
            imovel_dados=[],
        )
        return scoped

    def test_exact_shape_and_ranking_from_the_real_engine(self, client, cenario):
        resp = client.get("/api/imoveis/ONE1/similares", headers=auth())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body) == {"items", "total", "sem_semantica"}
        codigos = [i["codigo"] for i in body["items"]]
        assert codigos[0] == "ONE2"
        assert "ONE1" not in codigos          # the target is excluded
        assert "ONE4" not in codigos          # different cidade → not in the pool
        item = body["items"][0]
        assert set(item) >= SIMILAR_KEYS_EXTRA
        assert set(item) >= {"codigo", "endereco", "valor", "valor_tipo", "foto_destaque", "categoria"}
        assert item["score"] >= 45.0
        assert item["reasons"] == [p for p in item["justificativa"].split(". ") if p]
        assert body["total"] == len(body["items"])
        scores = [i["score"] for i in body["items"]]
        assert scores == sorted(scores, reverse=True)

    def test_sem_semantica_counts_pairs_without_vectors(self, client, cenario):
        body = client.get("/api/imoveis/ONE1/similares", headers=auth()).json()
        # the fixture catalog carries no embeddings at all
        assert body["sem_semantica"] == body["total"]

    def test_score_minimo_and_limit_are_honoured(self, client, cenario):
        alto = client.get("/api/imoveis/ONE1/similares", params={"score_minimo": 101}, headers=auth()).json()
        assert alto["items"] == [] and alto["total"] == 0
        um = client.get("/api/imoveis/ONE1/similares", params={"limit": 1, "score_minimo": 0}, headers=auth()).json()
        assert um["total"] == 1

    def test_imovel_fora_do_catalogo_returns_the_aviso(self, client, cenario):
        resp = client.get("/api/imoveis/GONE5/similares", headers=auth())
        assert resp.status_code == 200
        assert resp.json() == {
            "items": [], "total": 0, "sem_semantica": 0,
            "aviso": "Imóvel fora do catálogo — sem base para comparar.",
        }

    def test_unknown_codigo_404(self, client, cenario):
        assert client.get("/api/imoveis/NOPE/similares", headers=auth()).status_code == 404

    @pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 51}])
    def test_bad_limit_422(self, client, cenario, params):
        assert client.get("/api/imoveis/ONE1/similares", params=params, headers=auth()).status_code == 422

    def test_nothing_is_persisted(self, client, cenario):
        client.get("/api/imoveis/ONE1/similares", headers=auth())
        assert cenario.table("permuta_matches").select("*").execute().data == []

    def test_engine_is_reached_through_its_seam_with_the_adapter_shapes(self, client, cenario):
        """The entrypoint named by the contract is the one that runs, fed the
        `ativo_para_scorer` origin and `como_oferta`-relabelled candidates —
        asserted through the service's `motor` seam, not by patching."""
        from noctusai_lib.domain.real_estate.matching import gerar_matches_para_imovel
        from app.modules.imovel_hub import similares_service

        chamadas = []

        def espiao(origem, candidatos, score_minimo):
            chamadas.append((origem, list(candidatos), score_minimo))
            return gerar_matches_para_imovel(origem, candidatos, score_minimo)

        out = similares_service.similares(cenario, UUID(ORG_ID), "one1", limite=5, score_minimo=30.0, motor=espiao)
        assert len(chamadas) == 1
        origem, candidatos, minimo = chamadas[0]
        assert minimo == 30.0
        assert origem["id"] == "ONE1" and origem["natureza"] == "imovel"
        assert origem["tipo_imovel"] == "Apartamento" and origem["quartos"] == 3  # adapter vocabulary
        assert {c["id"] for c in candidatos} == {"ONE2", "ONE3"}  # same uf+cidade, target excluded
        assert all(c["natureza"] == "permuta_imovel" for c in candidatos)  # como_oferta
        assert out["items"][0]["codigo"] == "ONE2"
