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
    extrator` instead of `make_identity_extractor` — S1's seed module is
    merged into this worktree, so routing resolves to a REAL instance of
    the tipo's own factory-built extractor, never the identity extractor."""

    @pytest.mark.parametrize(
        "tipo,klass_path",
        [
            (
                "serasa_crednet",
                "noctusai_lib.integrations.documents.serasa_crednet.LadderCrednetExtractor",
            ),
            (
                "cartao_cnpj",
                "noctusai_lib.integrations.documents.cartao_cnpj.LadderCartaoCnpjExtractor",
            ),
        ],
    )
    def test_routes_to_its_own_fonte_extrator(self, tipo, klass_path):
        from noctusai_lib.integrations.documents.real import LadderIdentityExtractor

        extractor = deps._build_identity_extractor(
            "org-1", tipo, resolve_provider=_fake_provider
        )

        assert not isinstance(extractor, LadderIdentityExtractor)
        modulo, _, klass_nome = klass_path.rpartition(".")
        assert type(extractor).__module__ == modulo
        assert type(extractor).__name__ == klass_nome

    def test_fonte_extrator_is_registered_as_factory_shaped(self):
        for tipo in ("serasa_crednet", "cartao_cnpj"):
            assert fontes.FONTES[tipo].extrator in deps._FACTORY_SHAPED_EXTRATORES

    def test_comprovante_endereco_extrator_is_not_registered_as_factory_shaped(self):
        assert (
            fontes.FONTES["comprovante_endereco"].extrator
            not in deps._FACTORY_SHAPED_EXTRATORES
        )
