"""Store contracts: the Fake reproduces the DB's immutability; the Real half's
query shapes + error mapping through a scripted client double."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from postgrest.exceptions import APIError

from app.qualificacao.lead_store import (
    EstadoCache,
    FakeLeadQualificacaoStore,
    SupabaseLeadQualificacaoStore,
    get_lead_qualificacao_store,
)
from app.qualificacao.models import EventoImovel, Registro
from app.qualificacao.store import FakePadraoStore, SupabasePadraoStore, get_padrao_store
from app.stores._db_errors import StudioConflict, VersionImmutable
from app.stores.errors import NotFound
from tests.qualificacao.fixture_v1 import versao_v1
from tests.qualificacao.harness import ADMIN, AGENTE, LEAD, ORG, preencher_rascunho, publicar_v1


# ── Fake library store ──────────────────────────────────────────────────────

def test_published_version_is_immutable_in_every_child():
    store, vid = publicar_v1()
    v = versao_v1()
    with pytest.raises(VersionImmutable):
        store.salvar_criterio(vid, v.criterios[0])
    with pytest.raises(VersionImmutable):
        store.remover_criterio(vid, "operacao")
    with pytest.raises(VersionImmutable):
        store.salvar_estagio(vid, v.estagios[0])
    with pytest.raises(VersionImmutable):
        store.salvar_parametros(vid, v.parametros)
    with pytest.raises(VersionImmutable):
        store.atualizar_notas(vid, "x")
    with pytest.raises(VersionImmutable):
        store.publicar(vid, ADMIN)
    with pytest.raises(VersionImmutable):
        store.descartar_rascunho(vid)


def test_one_draft_per_standard_and_copy_from_published():
    store, vid = publicar_v1()
    padrao = store.obter_padrao("imob-lead")
    novo = store.criar_rascunho(padrao.id, "v2", vid)
    with pytest.raises(StudioConflict) as e:
        store.criar_rascunho(padrao.id, None, None)
    assert e.value.code == "draft_exists"
    copia, original = store.obter_versao(novo), store.obter_versao(vid)
    assert copia.versao == 2 and copia.status == "rascunho"
    assert [c.chave for c in copia.criterios] == [c.chave for c in original.criterios]
    assert [c.id for c in copia.criterios] != [c.id for c in original.criterios]
    assert copia.parametros == original.parametros
    store.salvar_criterio(novo, copia.criterios[0].__class__(**{**copia.criterios[0].__dict__, "rotulo": "Outro"}))
    assert store.obter_versao(vid).criterios[0].rotulo != "Outro"  # the published one is untouched


def test_publish_archives_the_previous_and_serves_the_latest():
    store, v1 = publicar_v1()
    padrao = store.obter_padrao("imob-lead")
    v2 = store.criar_rascunho(padrao.id, None, v1)
    store.publicar(v2, ADMIN)
    assert store.obter_versao(v1).status == "arquivada"
    assert store.obter_versao_publicada("imob-lead").id == v2
    assert [m.versao for m in store.listar_versoes(padrao.id)] == [2, 1]
    with pytest.raises(VersionImmutable):
        store.atualizar_notas(v1, "x")


def test_publish_needs_parameters_and_discard_removes_the_draft():
    store = FakePadraoStore()
    padrao = store.criar_padrao("outro", "Outro", None)
    vid = store.criar_rascunho(padrao.id, None, None)
    assert store.tem_parametros(vid) is False
    with pytest.raises(ValueError):
        store.publicar(vid, ADMIN)
    store.descartar_rascunho(vid)
    with pytest.raises(NotFound):
        store.obter_versao(vid)
    with pytest.raises(NotFound):
        store.obter_versao_publicada("outro")


def test_duplicate_standard_key_and_missing_rows():
    store, _ = publicar_v1()
    with pytest.raises(StudioConflict) as e:
        store.criar_padrao("imob-lead", "x", None)
    assert e.value.code == "chave_taken"
    with pytest.raises(NotFound):
        store.obter_padrao("nada")
    rasc = store.criar_rascunho(store.obter_padrao("imob-lead").id, None, None)
    with pytest.raises(NotFound):
        store.remover_criterio(rasc, "nada")
    assert not hasattr(store, "org_id")  # no org on the standard (owner decision Q2)


# ── Fake lead store ─────────────────────────────────────────────────────────

def test_records_are_returned_oldest_first_and_org_scoped():
    s = FakeLeadQualificacaoStore()
    vid = uuid4()
    s.adicionar_registros(ORG, LEAD, agent_id=AGENTE, versao_id=vid, thread_id=None, message_id=None,
                          registros=[Registro("operacao", "compra", trecho="a"), Registro("nome", "Ana", trecho="b")])
    assert [r.criterio_chave for r in s.listar_registros(ORG, LEAD)] == ["operacao", "nome"]
    assert s.listar_registros(uuid4(), LEAD) == []
    assert not hasattr(s, "atualizar_registro") and not hasattr(s, "remover_registro")  # append-only API


# ── Real stores through a scripted client ───────────────────────────────────

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


def _calls(client, i=-1):
    return [c[0] for c in client.log[i][1]]


def test_real_apagar_por_lead_is_one_rpc():
    c = Scripted(_ans(7))
    n = SupabaseLeadQualificacaoStore(c).apagar_por_lead(ORG, LEAD)
    assert n == 7
    assert c.log[0][0] == "rpc:apagar_qualificacao_lead:['p_lead_ref_id', 'p_org_id']"


def test_real_purge_is_one_rpc():
    c = Scripted(_ans(3))
    assert SupabaseLeadQualificacaoStore(c).purgar_inativos(datetime(2026, 1, 1, tzinfo=timezone.utc)) == 3
    assert c.log[0][0].startswith("rpc:purgar_qualificacao_inativos")


def test_real_append_is_one_org_scoped_insert_and_maps_rows():
    vid, now = uuid4(), datetime.now(timezone.utc).isoformat()
    row = {"id": str(uuid4()), "criterio_chave": "operacao", "valor": "compra", "fonte": "lead_informou",
           "trecho": "q", "created_at": now, "versao_id": str(vid), "agent_id": str(AGENTE), "thread_id": None, "message_id": None}
    c = Scripted(_ans([row]))
    out = SupabaseLeadQualificacaoStore(c).adicionar_registros(
        ORG, LEAD, agent_id=AGENTE, versao_id=vid, thread_id=None, message_id=None,
        registros=[Registro("operacao", "compra", trecho="q")])
    assert out[0].criterio_chave == "operacao" and out[0].agent_id == AGENTE
    (name, args, _), = [x for x in c.log[0][1] if x[0] == "insert"]
    assert args[0][0]["org_id"] == str(ORG) and args[0][0]["lead_ref_id"] == str(LEAD)


def test_real_listing_pages_and_filters_by_org_and_lead():
    c = Scripted(_ans([]))
    assert SupabaseLeadQualificacaoStore(c).listar_registros(ORG, LEAD) == []
    names = [x[0] for x in c.log[0][1]]
    assert "eq" in names and "range" in names and "order" in names
    eqs = {a[0]: a[1] for n, a, _ in c.log[0][1] if n == "eq"}
    assert eqs == {"org_id": str(ORG), "lead_ref_id": str(LEAD)}


def test_real_estado_roundtrip_and_upsert_key():
    now = datetime.now(timezone.utc)
    vid = uuid4()
    row = {"org_id": str(ORG), "lead_ref_id": str(LEAD), "versao_id": str(vid), "valores": {"a": 1}, "score": 5,
           "estagio": "novo", "faltando": ["x"], "hash": "h", "calculado_em": now.isoformat()}
    c = Scripted(_ans([row]), _ans([row]))
    s = SupabaseLeadQualificacaoStore(c)
    got = s.obter_estado(ORG, LEAD)
    assert (got.estagio, got.faltando, got.valores) == ("novo", ("x",), {"a": 1})
    s.salvar_estado(EstadoCache(ORG, LEAD, vid, {"a": 1}, 5, "novo", ("x",), "h", now))
    (_, args, kw), = [x for x in c.log[1][1] if x[0] == "upsert"]
    assert kw == {"on_conflict": "lead_ref_id"} and args[0]["faltando"] == ["x"]


def test_real_estado_absent_is_none():
    assert SupabaseLeadQualificacaoStore(Scripted(_ans([]))).obter_estado(ORG, LEAD) is None


def test_real_library_maps_unique_violation_to_chave_taken():
    dup = APIError({"code": "23505", "message": "duplicate key", "details": "", "hint": ""})
    with pytest.raises(StudioConflict) as e:
        SupabasePadraoStore(Scripted(dup)).criar_padrao("imob-lead", "x", None)
    assert e.value.code == "chave_taken"


def test_real_library_maps_trigger_refusal_to_version_immutable():
    boom = APIError({"code": "P0001", "message": "version_immutable", "details": "", "hint": ""})
    with pytest.raises(VersionImmutable):
        SupabasePadraoStore(Scripted(boom)).salvar_criterio(uuid4(), versao_v1().criterios[0])


def test_real_draft_and_publish_go_through_the_atomic_rpcs():
    vid = uuid4()
    c = Scripted(_ans(str(vid)), _ans(None))
    s = SupabasePadraoStore(c)
    assert s.criar_rascunho(uuid4(), "n", None) == vid
    s.publicar(vid, ADMIN)
    assert c.log[0][0].startswith("rpc:criar_rascunho_qualificacao")
    assert c.log[1][0].startswith("rpc:publicar_qualificacao_versao")


def test_real_discard_and_delete_child():
    c = Scripted(_ans([{"x": 1}]), _ans([]))
    s = SupabasePadraoStore(c)
    s.descartar_rascunho(uuid4())
    with pytest.raises(NotFound):
        s.remover_criterio(uuid4(), "nada")


def test_real_upsert_criterio_is_keyed_on_version_and_key():
    c = Scripted(_ans([]))
    SupabasePadraoStore(c).salvar_criterio(uuid4(), versao_v1().criterios[0])
    (_, args, kw), = [x for x in c.log[0][1] if x[0] == "upsert"]
    assert kw == {"on_conflict": "versao_id,chave"}
    assert "org_id" not in args[0]  # the standard has no org


def test_factories_return_fakes_without_a_service_key():
    s = SimpleNamespace(supabase_service_role_key=None)
    assert isinstance(get_padrao_store(s), FakePadraoStore)
    assert isinstance(get_lead_qualificacao_store(s), FakeLeadQualificacaoStore)
