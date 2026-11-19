"""Staff-only sections of a platform-definition agent page (route-exists != wired regression)."""
from __future__ import annotations

import pytest

from app.studio.modelo import FatosAgente, secoes_para

STAFF = ("especificacoes-empresas", "onboarding")


@pytest.mark.parametrize("sid", STAFF)
class TestStaffSections:
    def test_platform_admin_sees_on_platform_agent(self, sid):
        assert sid in secoes_para(FatosAgente(origem="plataforma", conteudo_modo="linhas"), "plataforma")

    @pytest.mark.parametrize("tier", ["org_admin", "membro"])
    def test_org_tiers_never_see(self, sid, tier):
        assert sid not in secoes_para(FatosAgente(origem="plataforma", conteudo_modo="linhas"), tier)

    @pytest.mark.parametrize("origem", ["org", "instancia", "legado"])
    def test_only_platform_origin(self, sid, origem):
        assert sid not in secoes_para(FatosAgente(origem=origem), "plataforma")
