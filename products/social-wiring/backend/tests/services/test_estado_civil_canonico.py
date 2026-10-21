"""estado_civil / regime_bens are stored as canonical TOKENS, never labels.

Prod incident 2026-10-21: the "Dados pessoais" form saved "Casado(a)" /
"Comunhão parcial de bens"; the contract generator (`derivacao.py`) refuses a
regime not in `frases.REGIME_EXTENSO` and compares spouses' regimes literally.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from noctusai_lib.testing.migrations import migration_sql
from noctusai_lib.primitives.exceptions import ValidationError_

from app.modules.card_hub.contrato_gerador.frases import REGIME_EXTENSO
from app.services import clientes_service as svc
from app.services.estado_civil_canonico import (
    estado_civil_canonico,
    regime_bens_canonico,
)
from tests.services.test_clientes_service import ORG, _clientes, _scoped_client


class TestMapa:
    @pytest.mark.parametrize("entrada,token", [
        ("Casado(a)", "casado"), ("casado", "casado"), ("Solteiro(a)", "solteiro"),
        ("Divorciado(a)", "divorciado"), ("Viúvo(a)", "viuvo"),
        ("Separado(a)", "separado_judicialmente"),
        ("União estável", "uniao_estavel"), ("uniao_estavel", "uniao_estavel"),
    ])
    def test_estado_civil(self, entrada, token):
        assert estado_civil_canonico(entrada) == token

    @pytest.mark.parametrize("token,rotulo", list(REGIME_EXTENSO.items()))
    def test_regime_label_and_token(self, token, rotulo):
        assert regime_bens_canonico(rotulo) == token
        assert regime_bens_canonico(rotulo.capitalize()) == token
        assert regime_bens_canonico(token) == token

    def test_clear_passes_through(self):
        assert estado_civil_canonico(None) is None
        assert regime_bens_canonico("") is None

    def test_unknown_is_refused(self):
        with pytest.raises(ValueError):
            estado_civil_canonico("complicado")
        with pytest.raises(ValueError):
            regime_bens_canonico("regime inventado")


class TestUpdateCliente:
    def test_label_is_stored_as_token(self):
        client = _scoped_client()
        cid = str(uuid4())
        client.set_table_data("clientes", [{"id": cid, "org_id": str(ORG), "nome": "A"}])
        svc.update_cliente(
            client, ORG, cid, is_admin=True,
            estado_civil="Casado(a)", regime_bens="Comunhão parcial de bens",
        )
        row = _clientes(client)[0]
        assert row["estado_civil"] == "casado"
        assert row["regime_bens"] == "comunhao_parcial"

    def test_unknown_value_is_refused_and_nothing_written(self):
        client = _scoped_client()
        cid = str(uuid4())
        client.set_table_data("clientes", [{"id": cid, "org_id": str(ORG), "nome": "A"}])
        with pytest.raises(ValidationError_):
            svc.update_cliente(client, ORG, cid, is_admin=True, regime_bens="xyz")
        assert _clientes(client)[0].get("regime_bens") is None


def test_migration_maps_every_label():
    sql = migration_sql(Path(__file__).parents[2] / "migrations", "estado_civil_regime_tokens")
    for rotulo in REGIME_EXTENSO.values():
        assert f"'{rotulo.capitalize()}'" in sql
    for token in ("casado", "divorciado", "solteiro", "viuvo", "uniao_estavel", "comunhao_parcial"):
        assert f"'{token}'" in sql
