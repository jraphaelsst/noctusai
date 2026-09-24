"""`card_hub.deps._build_identity_extractor`'s widened routing (P0c contract
§C2): `serasa_crednet` / `cartao_cnpj` resolve THEIR OWN `Fonte.extrator`
factory instead of `make_identity_extractor` — every other `dominio ==
"cliente"` tipo (including `comprovante_endereco`, whose own `Fonte.extrator`
is a pure text parser with a completely different call signature) is
UNCHANGED.
"""
from __future__ import annotations

import pytest

from app.modules.card_hub import deps
from app.modules.card_hub.proveniencia import fontes


def _fake_provider(org_id):
    return "openai"


class TestUnaffectedTipos:
    """Every tipo whose `Fonte.extrator` is NOT one of the two new
    factory-shaped ones keeps building the identity extractor exactly as
    before — this is the regression guard for §C2's widening."""

    @pytest.mark.parametrize(
        "tipo", ["rg", "cpf", "cnh", "certidao_casamento", "comprovante_endereco", None]
    )
    def test_builds_the_identity_extractor(self, tipo):
        from noctusai_lib.integrations.documents.real import LadderIdentityExtractor

        extractor = deps._build_identity_extractor(
            "org-1", tipo, resolve_provider=_fake_provider
        )
        assert isinstance(extractor, LadderIdentityExtractor)


class TestFactoryShapedRouting:
    """`serasa_crednet` / `cartao_cnpj` route through `fontes.resolver_
    extrator` instead — proven here by the fact that routing was ATTEMPTED
    (an `ImportError` naming the seed module S1 has not yet merged into
    this worktree — see `test_proveniencia_fontes.py`'s
    `_PENDING_CROSS_SLICE_TIPOS`), not by the identity extractor being
    silently built instead."""

    @pytest.mark.parametrize(
        "tipo,modulo",
        [
            ("serasa_crednet", "noctusai_lib.integrations.documents.serasa_crednet"),
            ("cartao_cnpj", "noctusai_lib.integrations.documents.cartao_cnpj"),
        ],
    )
    def test_routes_to_its_own_fonte_extrator(self, tipo, modulo):
        try:
            extractor = deps._build_identity_extractor(
                "org-1", tipo, resolve_provider=_fake_provider
            )
        except ImportError as exc:
            assert modulo in str(exc)
        else:
            # Once S1 has landed the module, this branches to a real
            # instance instead — the important assertion becomes "not the
            # identity extractor".
            from noctusai_lib.integrations.documents.real import (
                LadderIdentityExtractor,
            )

            assert not isinstance(extractor, LadderIdentityExtractor)

    def test_fonte_extrator_is_registered_as_factory_shaped(self):
        for tipo in ("serasa_crednet", "cartao_cnpj"):
            assert fontes.FONTES[tipo].extrator in deps._FACTORY_SHAPED_EXTRATORES

    def test_comprovante_endereco_extrator_is_not_registered_as_factory_shaped(self):
        assert (
            fontes.FONTES["comprovante_endereco"].extrator
            not in deps._FACTORY_SHAPED_EXTRATORES
        )
