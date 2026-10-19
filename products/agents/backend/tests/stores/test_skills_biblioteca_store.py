"""Shared skill library store (migration 039): the Fake reproduces the database's immutability and
pin rules; the Real half's query shapes + error mapping run through a scripted client double.

Skill text is TEST DATA only (D3)."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from postgrest.exceptions import APIError

from app.stores._db_errors import StudioConflict, VersionImmutable
from app.stores.errors import NotFound
from app.stores.skills_biblioteca import (
    FakeSkillsBibliotecaStore,
    SupabaseSkillsBibliotecaStore,
    get_skills_store,
    validar_obrigatoria_para,
)
from app.studio.skills_contract import SkillAberta, SkillRef, SkillsRuntime

ORG, ADMIN, AV = uuid4(), uuid4(), uuid4()


def _publicada(store, chave="s1", corpo="corpo", desc="desc"):
    s = store.criar_skill(chave, chave.upper(), None)
    vid = store.criar_rascunho(s.id, None, None)
    store.salvar_rascunho(vid, {"descricao_modelo": desc, "corpo": corpo})
    store.publicar(vid, ADMIN)
    return s, vid


def test_published_version_and_its_files_are_immutable():
    st = FakeSkillsBibliotecaStore()
    s = st.criar_skill("s1", "S1", None)
    vid = st.criar_rascunho(s.id, None, None)
    st.salvar_rascunho(vid, {"descricao_modelo": "d", "corpo": "c"})
    st.salvar_arquivo(vid, "ref/a.md", "A", "x")
    st.publicar(vid, ADMIN)
    for call in (
        lambda: st.salvar_rascunho(vid, {"corpo": "z"}),
        lambda: st.salvar_arquivo(vid, "b.md", None, "x"),
        lambda: st.remover_arquivo(vid, "ref/a.md"),
        lambda: st.publicar(vid, ADMIN),
        lambda: st.descartar_rascunho(vid),
    ):
        with pytest.raises(VersionImmutable):
            call()


def test_one_draft_per_skill_copy_and_publish_archives_the_previous():
    st = FakeSkillsBibliotecaStore()
    s, v1 = _publicada(st)
    v2 = st.criar_rascunho(s.id, "n", v1)
    with pytest.raises(StudioConflict) as e:
        st.criar_rascunho(s.id, None, None)
    assert e.value.code == "draft_exists"
    assert st.obter_versao(v2).corpo == "corpo" and st.obter_versao(v2).meta.versao == 2
    st.salvar_rascunho(v2, {"corpo": "novo"})
    assert st.obter_versao(v1).corpo == "corpo"  # the published one is untouched
    st.publicar(v2, ADMIN)
    assert st.obter_versao(v1).meta.status == "arquivada"
    assert st.obter_versao_publicada("s1").meta.id == v2


def test_publish_needs_real_text():
    st = FakeSkillsBibliotecaStore()
    s = st.criar_skill("s1", "S1", None)
    vid = st.criar_rascunho(s.id, None, None)
    with pytest.raises(ValueError):
        st.publicar(vid, ADMIN)
    with pytest.raises(NotFound):
        st.obter_versao_publicada("s1")


def test_pins_one_version_per_skill_and_the_new_version_signal():
    st = FakeSkillsBibliotecaStore()
    s, v1 = _publicada(st)
    r = st.fixar_ref(ORG, AV, v1, ["handoff"], 0)
    assert r.versao == 1 and r.nova_versao is None and r.obrigatoria_para == ("handoff",)
    v2 = st.criar_rascunho(s.id, None, v1)
    st.publicar(v2, ADMIN)
    (r,) = st.listar_refs(AV)
    assert r.versao == 1 and r.nova_versao == 2 and r.nova_versao_id == v2
    r2 = st.fixar_ref(ORG, AV, v2, [], 0)  # re-pin REPLACES (unique per version+skill)
    assert r2.id == r.id and len(st.listar_refs(AV)) == 1 and r2.nova_versao is None


def test_a_draft_cannot_be_pinned_and_unpin_missing_is_not_found():
    st = FakeSkillsBibliotecaStore()
    s = st.criar_skill("s1", "S1", None)
    vid = st.criar_rascunho(s.id, None, None)
    with pytest.raises(ValueError):
        st.fixar_ref(ORG, AV, vid, [], 0)
    with pytest.raises(NotFound):
        st.remover_ref(AV, "s1")


def test_obrigatoria_para_validation():
    assert validar_obrigatoria_para(["a_b", "a_b", "c1"]) == ("a_b", "c1")
    for bad in (["A"], ["a-b"], ["x"], [""], ["a"] * 0 + ["z" * 70], [f"t{i}" for i in range(33)]):
        with pytest.raises(ValueError):
            validar_obrigatoria_para(bad)


def test_new_draft_inherits_the_pins_like_the_after_insert_trigger():
    st = FakeSkillsBibliotecaStore()
    _, v1 = _publicada(st)
    st.fixar_ref(ORG, AV, v1, ["x_y"], 3)
    novo = uuid4()
    st.copiar_refs(AV, novo, ORG)
    (a,), (b,) = st.listar_refs(AV), st.listar_refs(novo)
    assert (b.skill_versao_id, b.obrigatoria_para, b.ordem) == (a.skill_versao_id, a.obrigatoria_para, 3)
    assert b.id != a.id


def test_runtime_interface_serves_the_pinned_version_not_the_latest():
    st = FakeSkillsBibliotecaStore()
    s = st.criar_skill("s1", "S1", None)
    v1 = st.criar_rascunho(s.id, None, None)
    st.salvar_rascunho(v1, {"descricao_modelo": "quando abrir", "corpo": "corpo um"})
    st.salvar_arquivo(v1, "ref/a.md", "A", "12345")
    st.publicar(v1, ADMIN)
    st.fixar_ref(ORG, AV, v1, ["handoff"], 0)
    v2 = st.criar_rascunho(s.id, None, v1)
    st.salvar_rascunho(v2, {"corpo": "corpo dois"})
    st.publicar(v2, ADMIN)

    runtime: SkillsRuntime = st
    (ref,) = runtime.skill_refs_for(AV)
    assert isinstance(ref, SkillRef)
    assert (ref.skill_key, ref.skill_versao_id, ref.obrigatoria_para) == ("s1", v1, ("handoff",))
    assert ref.descricao == "quando abrir" and ref.corpo_chars == len("corpo um") and ref.arquivos == (("ref/a.md", 5),)
    aberta = runtime.abrir("s1", ref.skill_versao_id)
    assert isinstance(aberta, SkillAberta) and aberta.corpo == "corpo um"
    assert [(a.caminho, a.conteudo) for a in aberta.arquivos] == [("ref/a.md", "12345")]
    assert runtime.abrir("outra", v1) is None and runtime.abrir("s1", uuid4()) is None
    assert runtime.skill_refs_for(uuid4()) == []


def test_a_draft_skill_version_is_never_opened_by_the_runtime():
    st = FakeSkillsBibliotecaStore()
    s = st.criar_skill("s1", "S1", None)
    vid = st.criar_rascunho(s.id, None, None)
    assert st.abrir("s1", vid) is None


def test_factory_returns_the_fake_without_a_service_key():
    assert isinstance(get_skills_store(SimpleNamespace(supabase_service_role_key=None)), FakeSkillsBibliotecaStore)


# ── Real, through a scripted client ─────────────────────────────────────────

class _Builder:
    def __init__(self, client, table):
        self.client, self.table, self.calls = client, table, []

    def __getattr__(self, name):
        def _chain(*a, **k):
            self.calls.append((name, a, k))
            return self
        return _chain

    def execute(self):
        self.client.log.append((self.table, self.calls))
        answer = self.client.script.pop(0) if self.client.script else SimpleNamespace(data=[])
        if isinstance(answer, Exception):
            raise answer
        return answer


class Scripted:
    def __init__(self, *answers):
        self.script, self.log = list(answers), []

    def schema(self, name):
        assert name == "agents"
        return self

    def table(self, name):
        return _Builder(self, name)

    def rpc(self, fn, params):
        return _Builder(self, f"rpc:{fn}:{sorted(params)}")


def _ans(data):
    return SimpleNamespace(data=data)


def test_real_draft_and_publish_go_through_the_atomic_rpcs():
    vid = uuid4()
    c = Scripted(_ans(str(vid)), _ans(None))
    s = SupabaseSkillsBibliotecaStore(c)
    assert s.criar_rascunho(uuid4(), "n", None) == vid
    s.publicar(vid, ADMIN)
    assert c.log[0][0].startswith("rpc:criar_rascunho_skill")
    assert c.log[1][0].startswith("rpc:publicar_skill_versao")


def test_real_maps_db_refusals_to_typed_errors():
    dup = APIError({"code": "23505", "message": "duplicate key", "details": "", "hint": ""})
    with pytest.raises(StudioConflict) as e:
        SupabaseSkillsBibliotecaStore(Scripted(dup)).criar_skill("a", "A", None)
    assert e.value.code == "chave_taken"
    boom = APIError({"code": "P0001", "message": "version_immutable", "details": "", "hint": ""})
    with pytest.raises(VersionImmutable):
        SupabaseSkillsBibliotecaStore(Scripted(boom)).salvar_rascunho(uuid4(), {"corpo": "x"})
    pin = APIError({"code": "P0001", "message": "invalid_payload", "details": "", "hint": ""})
    sv = {"skill_id": str(uuid4())}
    with pytest.raises(ValueError):
        SupabaseSkillsBibliotecaStore(Scripted(_ans([sv]), pin)).fixar_ref(ORG, AV, uuid4(), [], 0)


def test_real_pin_is_one_upsert_keyed_by_version_and_skill():
    skill_id, sv_id, ref_id = uuid4(), uuid4(), uuid4()
    ref = {"id": str(ref_id), "version_id": str(AV), "skill_id": str(skill_id), "skill_versao_id": str(sv_id),
           "obrigatoria_para": ["handoff"], "ordem": 2}
    c = Scripted(
        _ans([{"skill_id": str(skill_id)}]),            # which skill is this version of
        _ans([ref]),                                    # upsert
        _ans([ref]),                                    # listar_refs: pins
        _ans([{"id": str(skill_id), "chave": "s1"}]),   # skill keys
        _ans([{"id": str(sv_id), "versao": 1}]),        # pinned version numbers
        _ans([{"id": str(uuid4()), "skill_id": str(skill_id), "versao": 3}]),  # current published
    )
    out = SupabaseSkillsBibliotecaStore(c).fixar_ref(ORG, AV, sv_id, ["handoff"], 2)
    assert (out.skill_chave, out.versao, out.nova_versao) == ("s1", 1, 3)
    (_, args, kw), = [x for x in c.log[1][1] if x[0] == "upsert"]
    assert kw == {"on_conflict": "version_id,skill_id"}
    assert args[0]["org_id"] == str(ORG) and args[0]["version_id"] == str(AV) and args[0]["obrigatoria_para"] == ["handoff"]


def test_real_abrir_refuses_a_wrong_key_or_a_draft():
    skill_id, vid = uuid4(), uuid4()
    row = {"id": str(vid), "skill_id": str(skill_id), "versao": 1, "status": "publicada", "notas": None,
           "publicada_em": None, "publicada_por": None, "descricao_modelo": "d", "corpo": "c"}

    def answers(status):
        return [_ans([{**row, "status": status}]), _ans([{"chave": "s1"}]), _ans([{"caminho": "a.md", "titulo": None, "conteudo": "x"}])]

    ok = SupabaseSkillsBibliotecaStore(Scripted(*answers("publicada"))).abrir("s1", vid)
    assert ok.corpo == "c" and ok.arquivos[0].caminho == "a.md"
    assert SupabaseSkillsBibliotecaStore(Scripted(*answers("publicada"))).abrir("outra", vid) is None
    assert SupabaseSkillsBibliotecaStore(Scripted(*answers("rascunho"))).abrir("s1", vid) is None
    assert SupabaseSkillsBibliotecaStore(Scripted(_ans([]))).abrir("s1", vid) is None
