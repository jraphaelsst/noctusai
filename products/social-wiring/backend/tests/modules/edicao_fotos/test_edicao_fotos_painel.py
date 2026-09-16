"""`GET /api/edicao-fotos/painel` — contract §8, W9.

401/403 are covered by `test_edicao_fotos_auth_boundary.py`'s enumerated
sweep + role matrix; cross-org isolation (agency admin pinned to own org,
platform admin org filter vs platform-wide) lives in
`test_edicao_fotos_cross_org.py`. This file exercises the five response
categories end-to-end through a real pipeline run (`drain()`), so the RPC
simulator (`conftest.py::_simulate_fotos_painel`) is checked against
actual engine output, not hand-built fixtures.
"""
from __future__ import annotations


def _ready_batch_with_decision(edicao, decisao: str = "aprovar") -> str:
    edicao.configure_org()
    edicao.activate_guide()
    edicao.as_user("corretor")
    lote = edicao.make_batch("corretor")
    edicao.upload(lote)
    assert edicao.http.post(f"/api/edicao-fotos/lotes/{lote}/submeter", json={}).status_code == 200
    edicao.drain()
    foto = edicao.http.get(f"/api/edicao-fotos/revisao/{lote}").json()[0]["id"]
    body = {"decisao": decisao, "comentario": "ruim" if decisao == "rejeitar" else None}
    resp = edicao.http.post(f"/api/edicao-fotos/revisao/{lote}/fotos/{foto}/decisao", json=body)
    assert resp.status_code == 200, resp.text
    return lote


def test_painel_shape(edicao) -> None:
    _ready_batch_with_decision(edicao)
    body = edicao.as_user("admin").http.get("/api/edicao-fotos/painel").json()
    for key in ("periodo", "escopo", "pipeline", "fila", "atividade", "aprendizado", "custos"):
        assert key in body, body
    assert set(body["periodo"]) == {"desde", "ate"}
    assert body["pipeline"]["pontos"] and {"data", "estado", "total"} <= set(body["pipeline"]["pontos"][0])
    assert set(body["fila"]) == {"escopo", "jobs", "travados", "fotos_por_estado"}
    assert body["fila"]["escopo"] == "plataforma"
    assert set(body["atividade"]) == {
        "lotes_criados", "fotos_enviadas", "decisoes", "usuarios_ativos", "serie_diaria",
    }
    assert set(body["aprendizado"]) == {"taxa_aprovacao", "veredito_ia", "acerto_ia_pct", "regras"}
    assert set(body["custos"]) == {
        "moeda_base", "por_categoria", "total_brl", "fx_pendentes", "receita", "margem_brl",
    }


def test_pipeline_reflects_aprovada_transition(edicao) -> None:
    _ready_batch_with_decision(edicao, "aprovar")
    body = edicao.as_user("admin").http.get("/api/edicao-fotos/painel").json()
    estados = {p["estado"] for p in body["pipeline"]["pontos"]}
    assert "aprovada" in estados


def test_atividade_counts_lote_foto_and_decision(edicao) -> None:
    _ready_batch_with_decision(edicao, "aprovar")
    body = edicao.as_user("admin").http.get("/api/edicao-fotos/painel").json()
    assert body["atividade"]["lotes_criados"] == 1
    assert body["atividade"]["fotos_enviadas"] == 1
    assert body["atividade"]["decisoes"] == {"aprovar": 1, "rejeitar": 0}
    assert body["atividade"]["usuarios_ativos"] == 1


def test_aprendizado_taxa_aprovacao_and_ai_agreement(edicao) -> None:
    # good_evaluation() (conftest) always recommends "aprovar" — a human
    # "aprovar" decision is therefore a 100% AI/human agreement.
    _ready_batch_with_decision(edicao, "aprovar")
    body = edicao.as_user("admin").http.get("/api/edicao-fotos/painel").json()
    assert body["aprendizado"]["taxa_aprovacao"] == 1.0
    assert body["aprendizado"]["veredito_ia"] == {"aprovar": 1, "rejeitar": 0}
    assert body["aprendizado"]["acerto_ia_pct"] == 100.0


def test_aprendizado_ai_disagreement_on_rejection(edicao) -> None:
    _ready_batch_with_decision(edicao, "rejeitar")
    body = edicao.as_user("admin").http.get("/api/edicao-fotos/painel").json()
    assert body["aprendizado"]["taxa_aprovacao"] == 0.0
    assert body["aprendizado"]["acerto_ia_pct"] == 0.0  # AI said "aprovar", human rejected


def test_custos_revenue_is_honestly_zero(edicao) -> None:
    _ready_batch_with_decision(edicao)
    body = edicao.as_user("plataforma").http.get("/api/edicao-fotos/painel").json()
    assert body["custos"]["receita"] == {
        "disponivel": False, "total_brl": 0, "nota": "sem dados de faturamento",
    }
    assert body["custos"]["margem_brl"] == 0 - body["custos"]["total_brl"]


def test_date_range_filters_out_of_window_data(edicao) -> None:
    _ready_batch_with_decision(edicao)
    resp = edicao.as_user("admin").http.get(
        "/api/edicao-fotos/painel", params={"desde": "2020-01-01", "ate": "2020-01-02"}
    )
    body = resp.json()
    assert body["atividade"]["lotes_criados"] == 0
    assert body["periodo"] == {"desde": "2020-01-01", "ate": "2020-01-02"}


def test_org_scoped_response_has_org_id_pinned(edicao) -> None:
    edicao.make_batch("admin")
    body = edicao.as_user("admin").http.get("/api/edicao-fotos/painel").json()
    assert body["escopo"] == "organizacao"
