"""Tom accepted as id or slug; the old tiered pool is replaced by the Estruturas retrieval pool."""
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


def test_the_old_org_scoped_tiered_pool_is_gone():
    """The pool is the EST-4a retrieval pool over the platform library (estruturas-contract 8.2)."""
    for nome in ("pool_de_estruturas", "pool_da_biblioteca", "tiers_de_pool", "carregar_candidatos"):
        assert not hasattr(hp, nome)
    assert callable(hp.selecionar_estruturas) and callable(hp.carregar_linhas)
