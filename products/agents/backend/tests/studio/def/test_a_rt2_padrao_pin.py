"""Julia v2 A-RT2: publish pins the qualification standard; the draft inherits; the platform admin moves it; the
hash covers it; a "new standard version available" indicator."""
from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

from app.qualificacao.models import EstagioDef
from tests.channels.julia_v2 import publicar_padrao, versao_com_identidade
from tests.routers.conftest import DEFAULT_ORG_ID
import importlib

# the package is named `def` (a keyword): shared helpers load by name
_base = importlib.import_module("tests.studio.def.test_studio_conteudo_router")
BASE, PLAT, _fill, _platform_admin, _publish = _base.BASE, _base.PLAT, _base._fill, _base._platform_admin, _base._publish


def _plat(studio):
    studio.store.mark_platform_org(DEFAULT_ORG_ID)
    _platform_admin(studio)
    assert studio.post(f"{PLAT}/agents", json={"key": "julia"}).status_code == 201
    studio.as_role("owner")
    _fill(studio)
    # with the standard in the compile, its block's headings are required texts too
    extra = [
        {"chave": c, "conteudo": "texto de teste"}
        for c in _base.TEXTOS_REGISTRO_CHAVES_QUALIFICACAO
    ]
    assert studio.put(f"{BASE}/julia/draft/textos", json={"itens": _base.TEXTOS + extra}).status_code == 200
    return studio


def _julia(studio):
    return studio.store.get_agent(DEFAULT_ORG_ID, "julia")


def _nova_versao_do_padrao(studio) -> UUID:
    v = versao_com_identidade()
    estagios = tuple(replace(e, rotulo=e.rotulo + " 2") if isinstance(e, EstagioDef) else e for e in v.estagios)
    return publicar_padrao_v2(studio, replace(v, estagios=estagios))


def publicar_padrao_v2(studio, versao) -> UUID:
    padrao = studio.padroes.obter_padrao("imob-lead")
    vid = studio.padroes.criar_rascunho(padrao.id, "v2", None)
    for c in versao.criterios:
        studio.padroes.salvar_criterio(vid, c)
    for e in versao.estagios:
        studio.padroes.salvar_estagio(vid, e)
    studio.padroes.salvar_parametros(vid, versao.parametros)
    from tests.qualificacao.harness import ADMIN

    studio.padroes.publicar(vid, ADMIN)
    return vid


class TestPublishStampsThePin:
    def test_an_unpinned_draft_is_stamped_with_the_newest_published_standard(self, studio_com_padrao):
        studio = _plat(studio_com_padrao)
        draft = studio.store.get_draft(DEFAULT_ORG_ID, _julia(studio).id)
        assert draft.qualificacao_versao_id is None
        out = _publish(studio)
        published = studio.store.get_version(DEFAULT_ORG_ID, UUID(out["id"]))
        assert published.qualificacao_versao_id == studio.padrao_versao_id

    def test_without_a_published_standard_publish_is_refused(self, studio_com_padrao):
        studio = _plat(studio_com_padrao)
        from app.qualificacao.store import FakePadraoStore
        from app.routers.qualificacao_router import get_padrao_store_dep as dep

        studio.raw.app.dependency_overrides[dep] = lambda: FakePadraoStore()
        resp = studio.post(f"{BASE}/julia/draft/publish", json={"override_reason": "primeira publicação dos testes do conteúdo"})
        assert resp.status_code == 409 and resp.json()["code"] == "qualificacao_indisponivel"

    def test_the_pin_is_part_of_what_the_hash_covers(self, studio_com_padrao):
        studio = _plat(studio_com_padrao)
        agent = _julia(studio)
        h1 = studio.get(f"{BASE}/julia/versions/{studio.store.get_draft(DEFAULT_ORG_ID, agent.id).id}/compiled").json()["hash"]
        v2 = _nova_versao_do_padrao(studio)
        draft = studio.store.get_draft(DEFAULT_ORG_ID, agent.id)
        # unpinned: the draft follows the newest published standard, so a new standard version moves the hash
        h2 = studio.get(f"{BASE}/julia/versions/{draft.id}/compiled").json()["hash"]
        assert h1 != h2
        # pinned back to v1: the original hash returns
        r = studio.put(f"{BASE}/julia/draft/qualificacao", json={"versao_id": str(studio.padrao_versao_id)})
        assert r.status_code == 200, r.text
        h3 = studio.get(f"{BASE}/julia/versions/{draft.id}/compiled").json()["hash"]
        assert h3 == h1 and v2 != studio.padrao_versao_id


class TestDraftInheritsAndMoves:
    def test_a_new_draft_inherits_the_pin_of_its_source_version(self, studio_com_padrao):
        studio = _plat(studio_com_padrao)
        out = _publish(studio)
        nova = studio.post(f"{BASE}/julia/draft", json={"from_version_id": out["id"]})
        assert nova.status_code in (200, 201), nova.text
        draft = studio.store.get_draft(DEFAULT_ORG_ID, _julia(studio).id)
        assert draft.qualificacao_versao_id == studio.padrao_versao_id

    def test_indicator_reports_a_newer_standard_for_a_pinned_version_only(self, studio_com_padrao):
        studio = _plat(studio_com_padrao)
        out = _publish(studio)
        studio.post(f"{BASE}/julia/draft", json={"from_version_id": out["id"]})
        v2 = _nova_versao_do_padrao(studio)
        r = studio.get(f"{BASE}/julia/qualificacao")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["padrao"] == "imob-lead" and body["mais_nova"]["id"] == str(v2)
        assert body["ativa"]["atualizacao_disponivel"] is True and body["rascunho"]["atualizacao_disponivel"] is True
        assert body["ativa"]["versao"]["id"] == str(studio.padrao_versao_id)
        # moving the draft to the newest clears ITS indicator, not the active version's
        moved = studio.put(f"{BASE}/julia/draft/qualificacao", json={"versao_id": str(v2)}).json()
        assert moved["rascunho"]["atualizacao_disponivel"] is False and moved["ativa"]["atualizacao_disponivel"] is True

    def test_the_move_refuses_a_foreign_unknown_or_unpublished_version(self, studio_com_padrao):
        studio = _plat(studio_com_padrao)
        assert studio.put(f"{BASE}/julia/draft/qualificacao", json={"versao_id": str(uuid4())}).status_code == 404
        padrao = studio.padroes.obter_padrao("imob-lead")
        rascunho = studio.padroes.criar_rascunho(padrao.id, "draft", None)
        r = studio.put(f"{BASE}/julia/draft/qualificacao", json={"versao_id": str(rascunho)})
        assert r.status_code == 409 and r.json()["code"] == "padrao_nao_publicado"
        outro = studio.padroes.criar_padrao("outro", "Outro", None)
        vo = studio.padroes.criar_rascunho(outro.id, "x", None)
        from tests.qualificacao.harness import ADMIN

        v = versao_com_identidade()
        for c in v.criterios:
            studio.padroes.salvar_criterio(vo, c)
        for e in v.estagios:
            studio.padroes.salvar_estagio(vo, e)
        studio.padroes.salvar_parametros(vo, v.parametros)
        studio.padroes.publicar(vo, ADMIN)
        r = studio.put(f"{BASE}/julia/draft/qualificacao", json={"versao_id": str(vo)})
        assert r.status_code == 422 and r.json()["code"] == "invalid_field"

    def test_platform_admin_only_with_a_strict_401_403(self, studio_com_padrao):
        studio = _plat(studio_com_padrao)
        assert studio.raw.put(f"{BASE}/julia/draft/qualificacao", json={"versao_id": None}).status_code == 401
        studio.as_org_admin_only()
        r = studio.put(f"{BASE}/julia/draft/qualificacao", json={"versao_id": None})
        assert r.status_code == 403 and r.json()["code"] == "platform_admin_required"
        assert studio.get(f"{BASE}/julia/qualificacao").status_code == 403
