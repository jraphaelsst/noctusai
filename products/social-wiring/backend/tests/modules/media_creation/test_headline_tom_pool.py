"""Tom accepted as id or slug; the canonical structure pool function."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.media_creation.schemas.headlines import LoteViral
from app.modules.media_creation.services import headline_pipeline as hp

M = "00000000-0000-0000-0000-000000000001"


def _lote(tom):
    return LoteViral(marca_id=M, origem="form_viral", assunto_livre="x", tom=tom)


@pytest.mark.parametrize("given,stored", [
    (10, 10), ("12", 12), ("chocante-disruptiva", 10), ("reflexao-profundidade", 15), (None, None),
])
def test_tom_accepts_id_or_slug_and_stores_the_id(given, stored):
    assert _lote(given).tom == stored


@pytest.mark.parametrize("bad", [9, 16, "nada", True, ""])
def test_tom_rejects_the_rest(bad):
    with pytest.raises(ValidationError):
        _lote(bad)


def test_pool_de_estruturas_is_the_first_non_empty_tier():
    a = {"id": "a", "perfil_id": "p1", "nicho_ids": [], "publicado_em": "2026-10-01T00:00:00+00:00"}
    b = {"id": "b", "perfil_id": "p2", "nicho_ids": [3], "publicado_em": "2026-10-01T00:00:00+00:00"}
    ref = [{"modo": "perfil", "perfil_id": "p1", "posts_ate": None}]
    assert [c["id"] for c in hp.pool_de_estruturas([a, b], ref, [3])] == ["a"]
    assert [c["id"] for c in hp.pool_de_estruturas([a, b], [], [3])] == ["b"]
    assert [c["id"] for c in hp.pool_de_estruturas([a, b], [], [9])] == ["a", "b"]
    assert hp.pool_de_estruturas([], [], [3]) == []
