"""Valuation characteristics on `imovel_dados` (migration 264) via
`PATCH/GET /api/imoveis/{codigo}/dados`."""
from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest
from noctusai_lib.testing.migrations import migration_path

from app.modules.imovel_hub import dados_service
from app.modules.imovel_hub.schemas import (
    EstadoConservacao,
    PadraoConstrutivo,
    PosicaoLote,
    Topografia,
)
from tests.modules.imovel_hub.conftest import CODIGO, auth, registry_row, seed

URL = f"/api/imoveis/{CODIGO}/dados"

COMPLETO = {
    "padrao_construtivo": "superior",
    "estado_conservacao": "regular",
    "area_terreno_m2": 250.5,
    "area_construida_m2": 180,
    "testada_m": 10,
    "profundidade_m": 25.05,
    "topografia": "plano",
    "posicao_lote": "esquina",
}


class TestRoundTrip:
    def test_patch_then_get_returns_every_field_and_stamps_who_when(self, client, scoped):
        seed(scoped, registry=[registry_row()])
        r = client.patch(URL, json=COMPLETO, headers=auth())
        assert r.status_code == 200, r.text
        body = client.get(URL, headers=auth()).json()
        for k, v in COMPLETO.items():
            assert body[k] == v
        assert body["avaliacao_campos_atualizado_em"] is not None
        assert "avaliacao_campos_atualizado_por" in body

    def test_null_clears_and_absent_leaves_alone(self, client, scoped):
        seed(scoped, registry=[registry_row()])
        client.patch(URL, json=COMPLETO, headers=auth())
        r = client.patch(URL, json={"topografia": None}, headers=auth()).json()
        assert r["topografia"] is None
        assert r["padrao_construtivo"] == "superior"

    def test_unrelated_patch_does_not_restamp(self, client, scoped):
        seed(scoped, registry=[registry_row()])
        client.patch(URL, json={"em_condominio": True}, headers=auth())
        body = client.get(URL, headers=auth()).json()
        assert body["avaliacao_campos_atualizado_em"] is None


class TestValidation:
    @pytest.mark.parametrize(
        "payload",
        [
            {"padrao_construtivo": "luxuoso"},
            {"estado_conservacao": "ruim"},
            {"topografia": "montanha"},
            {"posicao_lote": "fundo"},
            {"area_terreno_m2": 0},
            {"testada_m": -1},
        ],
    )
    def test_invalid_value_is_422(self, client, scoped, payload):
        seed(scoped, registry=[registry_row()])
        assert client.patch(URL, json=payload, headers=auth()).status_code == 422

    def test_no_auth_is_401(self, anon_client):
        assert anon_client.patch(URL, json=COMPLETO).status_code == 401


class TestMigration264:
    @pytest.fixture(scope="class")
    def code(self) -> str:
        path = migration_path(Path(__file__).resolve().parents[3], "imovel_dados_avaliacao")
        return "\n".join(
            ln for ln in path.read_text().splitlines() if not ln.strip().startswith("--")
        )

    @pytest.mark.parametrize(
        "coluna,literal",
        [
            ("padrao_construtivo", PadraoConstrutivo),
            ("estado_conservacao", EstadoConservacao),
            ("topografia", Topografia),
            ("posicao_lote", PosicaoLote),
        ],
    )
    def test_check_set_equals_literal_set(self, code, coluna, literal):
        m = re.search(rf"{coluna} IN \((.*?)\)\)", code, re.S)
        assert m, f"CHECK for {coluna} not found"
        assert set(re.findall(r"'([a-z_]+)'", m.group(1))) == set(get_args(literal))

    def test_every_editable_column_is_added(self, code):
        for campo in dados_service.CAMPOS_AVALIACAO:
            assert f"ADD COLUMN IF NOT EXISTS {campo} " in code
