"""The report's ``temperatura`` and ``imoveis_de_interesse`` (Lais study A11): derived from the records, never the model."""
from __future__ import annotations

import pytest

from app.channels.relatorio import interesse_de, temperatura_de


def _t(**kw):
    base = {"motivo_codigo": "pedido_humano", "gostou": [], "visita": False, "oferecidos": 0, "perfil": 0}
    return temperatura_de(**{**base, **kw})


@pytest.mark.parametrize("kw,esperado", [
    ({}, "frio"),
    ({"perfil": 2}, "frio"),
    ({"perfil": 3}, "morno"),
    ({"oferecidos": 1}, "morno"),
    ({"motivo_codigo": "qualificacao_concluida"}, "morno"),
    ({"gostou": ["A1"]}, "quente"),
    ({"visita": True}, "quente"),
    ({"motivo_codigo": "pedido_visita"}, "quente"),
    ({"motivo_codigo": "proposta"}, "quente"),
])
def test_temperatura_from_the_records(kw, esperado):
    assert _t(**kw) == esperado


@pytest.mark.parametrize("motivo", ["parceria", "fora_do_escopo", "seguranca", "direito_titular"])
def test_a_non_lead_handoff_is_always_frio_even_with_activity(motivo):
    assert _t(motivo_codigo=motivo, gostou=["A1"], visita=True, oferecidos=3, perfil=5) == "frio"


def test_interesse_orders_liked_then_visits_then_campaign_without_repeats_and_caps_at_five():
    assert interesse_de(gostados=["B1"], visitas=["B1", "B2"], campanha="C0") == ["B1", "B2", "C0"]
    assert interesse_de(gostados=[], visitas=[], campanha=None) == []
    assert len(interesse_de(gostados=[f"X{i}" for i in range(9)], visitas=[], campanha="C0")) == 5
