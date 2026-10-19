"""The Lais -> Julia rename keeps the pre-rename surface alive for one release (owner order 2026-10-19).

NOC-REMEDIATE[drop-lais-route-alias] / [drop-lead-imob-alias] / [drop-nome-lais-alias]: delete the matching
assertions together with the shims they pin.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import LegacyLaisPathAlias
from app.modules.atendimento_blocos.blocos import agentes_permitidos, normalizar_agent_key
from app.services import julia_modelos_service as modelos


def _app() -> TestClient:
    app = FastAPI()

    @app.post("/api/julia/ferramentas/{nome}")
    def ferramenta(nome: str):
        return {"nome": nome}

    @app.get("/api/public/julia/privacidade/{slug}")
    def aviso(slug: str):
        return {"slug": slug}

    @app.get("/api/lais-parecido")
    def parecido():
        return {"ok": True}

    app.add_middleware(LegacyLaisPathAlias)
    return TestClient(app)


def test_the_old_lais_paths_reach_the_julia_routes():
    c = _app()
    assert c.post("/api/lais/ferramentas/buscar_imoveis").json() == {"nome": "buscar_imoveis"}
    assert c.post("/api/julia/ferramentas/buscar_imoveis").json() == {"nome": "buscar_imoveis"}
    assert c.get("/api/public/lais/privacidade/acme").json() == {"slug": "acme"}


def test_the_alias_matches_whole_segments_only():
    assert _app().get("/api/lais-parecido").json() == {"ok": True}


def test_the_old_studio_key_is_read_as_julia_and_is_allowed_on_sdr():
    assert normalizar_agent_key("lead-imob") == "julia" and normalizar_agent_key("julia") == "julia"
    assert normalizar_agent_key(None) is None
    assert "julia" in agentes_permitidos("sdr") and "lead-imob" not in agentes_permitidos("sdr")


def test_the_old_nome_lais_placeholder_still_renders_and_numbers_as_nome_julia():
    corpo = "Oi {{nome_pessoa}}, sou a {{nome_lais}} e a {{nome_julia}}."
    assert modelos.extrair_parametros(corpo) == ["nome_pessoa", "nome_julia"]
    assert modelos.renderizar(corpo, {"nome_pessoa": "Ana", "nome_lais": "Aurora"}) == "Oi Ana, sou a Aurora e a Aurora."
    posicional, chaves = modelos.corpo_posicional(corpo)
    assert posicional == "Oi {{1}}, sou a {{2}} e a {{2}}." and chaves == ["nome_pessoa", "nome_julia"]
