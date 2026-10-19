"""``/api/qualificacao/*`` (platform-admin writes, member reads) and
``GET /api/channels/leads/{ref}/qualificacao`` (channel token)."""
from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from app.dependencies import get_auth_context
from app.qualificacao.lead_store import FakeLeadQualificacaoStore
from app.qualificacao.service import ItemPerfil, QualificacaoService
from app.qualificacao.store import FakePadraoStore
from app.routers.qualificacao_router import get_lead_qualificacao_store_dep, get_padrao_store_dep
from noctusai_lib.api.auth.session import AuthContext
from tests.qualificacao.fixture_v1 import versao_v1
from tests.qualificacao.harness import AGENTE, LEAD, publicar_v1
from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID

BASE = "/api/qualificacao"


def _role(client, role: str, org_role: str = "owner") -> None:
    client.mock_supabase.set_table_data(
        "noctus_users",
        [{"id": str(DEFAULT_USER_ID), "org_id": str(DEFAULT_ORG_ID), "role": role, "org_role": org_role}],
    )


@pytest.fixture
def qc(agents_client):
    from app.main import app

    padroes, leads = FakePadraoStore(), FakeLeadQualificacaoStore()
    app.dependency_overrides[get_padrao_store_dep] = lambda: padroes
    app.dependency_overrides[get_lead_qualificacao_store_dep] = lambda: leads
    agents_client.padroes, agents_client.leads = padroes, leads
    _role(agents_client, "admin")
    try:
        yield agents_client
    finally:
        app.dependency_overrides.pop(get_padrao_store_dep, None)
        app.dependency_overrides.pop(get_lead_qualificacao_store_dep, None)


def _criterio_body(**over):
    body = {"grupo": "prontidao", "rotulo": "Operacao", "descricao_modelo": "compra ou aluguel", "tipo": "enum",
            "opcoes": [{"valor": "compra", "rotulo": "Compra"}, {"valor": "aluguel"}],
            "pontuacao": {"opcoes": {"compra": 10}}, "ordem": 10}
    body.update(over)
    return body


def _v1_body(v):
    return {
        "criterios": {c.chave: {
            "grupo": c.grupo, "rotulo": c.rotulo, "descricao_modelo": c.descricao_modelo, "tipo": c.tipo,
            "opcoes": [{"valor": o.valor, "rotulo": o.rotulo, "descricao_modelo": o.descricao_modelo, "sinonimos": list(o.sinonimos)} for o in c.opcoes],
            "unidade": c.unidade, "sensivel": c.sensivel, "pontuacao": c.pontuacao, "ordem": c.ordem, "ativo": c.ativo,
        } for c in v.criterios},
        "estagios": {e.chave: {"rotulo": e.rotulo, "descricao": e.descricao, "ordem": e.ordem, "regra": e.regra,
                               "conclusivo": e.conclusivo, "terminal": e.terminal} for e in v.estagios},
        "parametros": {"minimo_para_ofertar": v.parametros.minimo_para_ofertar, "lote_ofertas": v.parametros.lote_ofertas,
                       "score_max": v.parametros.score_max},
    }


def _fill_over_http(c, vid, v=None):
    body = _v1_body(v or versao_v1())
    for k, b in body["criterios"].items():
        assert c.put(f"{BASE}/versoes/{vid}/criterios/{k}", json=b).status_code == 200, k
    for k, b in body["estagios"].items():
        assert c.put(f"{BASE}/versoes/{vid}/estagios/{k}", json=b).status_code == 200, k
    assert c.put(f"{BASE}/versoes/{vid}/parametros", json=body["parametros"]).status_code == 200


# ── auth ────────────────────────────────────────────────────────────────────

WRITES = [
    ("post", f"{BASE}/padroes", {"chave": "x1", "nome": "X"}),
    ("post", f"{BASE}/padroes/imob-lead/versoes", {}),
    ("patch", f"{BASE}/versoes/{uuid4()}", {"notas": "n"}),
    ("delete", f"{BASE}/versoes/{uuid4()}", None),
    ("put", f"{BASE}/versoes/{uuid4()}/criterios/operacao", _criterio_body()),
    ("delete", f"{BASE}/versoes/{uuid4()}/criterios/operacao", None),
    ("put", f"{BASE}/versoes/{uuid4()}/estagios/novo", {"rotulo": "N", "ordem": 0, "regra": {"todos": []}}),
    ("delete", f"{BASE}/versoes/{uuid4()}/estagios/novo", None),
    ("put", f"{BASE}/versoes/{uuid4()}/parametros", {"minimo_para_ofertar": {"todos": []}}),
    ("post", f"{BASE}/versoes/{uuid4()}/validar", None),
    ("post", f"{BASE}/versoes/{uuid4()}/publicar", None),
]
READS = [
    ("get", f"{BASE}/padroes"), ("get", f"{BASE}/padroes/imob-lead/versoes"), ("get", f"{BASE}/versoes/{uuid4()}"),
    ("get", f"/api/channels/leads/{LEAD}/qualificacao"),
]


def _call(c, method, path, body=None):
    return getattr(c, method)(path, **({"json": body} if body is not None else {}))


@pytest.mark.parametrize("method,path,body", WRITES)
def test_writes_without_credential_are_401(qc, method, path, body):
    assert _call(qc.raw(), method, path, body).status_code == 401


@pytest.mark.parametrize("method,path,body", WRITES)
def test_org_owner_cannot_write_the_platform_standard(qc, method, path, body):
    _role(qc, "user", "owner")
    r = _call(qc, method, path, body)
    assert r.status_code == 403 and r.json()["code"] == "platform_admin_required"


@pytest.mark.parametrize("method,path", READS[:3])
def test_reads_without_credential_are_401(qc, method, path):
    assert _call(qc.raw(), method, path).status_code == 401


def test_a_plain_org_member_reads_the_same_standard(qc):
    publicar_v1(qc.padroes)
    _role(qc, "user", "viewer")
    r = qc.get(f"{BASE}/padroes")
    assert r.status_code == 200 and [p["chave"] for p in r.json()["items"]] == ["imob-lead"]
    assert "org_id" not in r.json()["items"][0]


# ── CRUD + publish ──────────────────────────────────────────────────────────

def test_full_authoring_flow_over_http_and_publish_v1(qc):
    r = qc.post(f"{BASE}/padroes", json={"chave": "imob-lead", "nome": "Imobiliaria"})
    assert r.status_code == 201
    assert qc.post(f"{BASE}/padroes", json={"chave": "imob-lead", "nome": "X"}).json()["code"] == "chave_taken"
    r = qc.post(f"{BASE}/padroes/imob-lead/versoes", json={"notas": "primeira"})
    assert r.status_code == 201
    vid = r.json()["id"]
    assert qc.post(f"{BASE}/padroes/imob-lead/versoes", json={}).json()["code"] == "draft_exists"
    # incomplete draft: nothing to publish yet
    assert qc.post(f"{BASE}/versoes/{vid}/publicar").status_code == 422
    _fill_over_http(qc, vid)
    assert qc.post(f"{BASE}/versoes/{vid}/validar").json() == {"ok": True, "erros": []}
    r = qc.post(f"{BASE}/versoes/{vid}/publicar")
    assert r.status_code == 200 and r.json()["status"] == "publicada" and r.json()["publicada_em"]
    assert qc.padroes.obter_versao(UUID(vid)).status == "publicada"
    listed = qc.get(f"{BASE}/padroes/imob-lead/versoes").json()["items"]
    assert [(v["versao"], v["status"]) for v in listed] == [(1, "publicada")]
    # a published version is immutable over HTTP too
    assert qc.put(f"{BASE}/versoes/{vid}/criterios/operacao", json=_criterio_body()).json()["code"] == "version_immutable"
    assert qc.post(f"{BASE}/versoes/{vid}/publicar").json()["code"] == "version_immutable"
    assert qc.delete(f"{BASE}/versoes/{vid}").json()["code"] == "version_immutable"
    got = qc.get(f"{BASE}/versoes/{vid}").json()
    assert len(got["criterios"]) == len(versao_v1().criterios) and len(got["estagios"]) == 7


def test_publish_with_an_invalid_rule_is_422_with_every_problem(qc):
    r = qc.post(f"{BASE}/padroes", json={"chave": "imob-lead", "nome": "I"})
    vid = qc.post(f"{BASE}/padroes/imob-lead/versoes", json={}).json()["id"]
    qc.put(f"{BASE}/versoes/{vid}/criterios/operacao", json=_criterio_body())
    qc.put(f"{BASE}/versoes/{vid}/estagios/novo", json={"rotulo": "Novo", "ordem": 0, "regra": {"criterio": "operacao", "op": "preenchido"}})
    qc.put(f"{BASE}/versoes/{vid}/estagios/xx", json={"rotulo": "X", "ordem": 1, "regra": {"criterio": "fantasma", "op": "parece"}})
    qc.put(f"{BASE}/versoes/{vid}/parametros", json={"minimo_para_ofertar": {"todos": []}})
    r = qc.post(f"{BASE}/versoes/{vid}/publicar")
    assert r.status_code == 422 and r.json()["code"] == "regras_invalidas"
    codes = {e["code"] for e in r.json()["erros"]}
    assert {"sem_estagio_base", "criterio_desconhecido", "op_desconhecido"} <= codes
    assert qc.padroes.obter_versao(UUID(vid)).status == "rascunho"  # nothing half-published


def test_publish_without_parameters_is_refused(qc):
    qc.post(f"{BASE}/padroes", json={"chave": "imob-lead", "nome": "I"})
    vid = qc.post(f"{BASE}/padroes/imob-lead/versoes", json={}).json()["id"]
    qc.put(f"{BASE}/versoes/{vid}/estagios/novo", json={"rotulo": "Novo", "ordem": 0, "regra": {"todos": []}})
    r = qc.post(f"{BASE}/versoes/{vid}/publicar")
    assert r.status_code == 422 and "parametros_ausentes" in {e["code"] for e in r.json()["erros"]}


def test_new_version_copies_and_publishing_archives_the_old_one(qc):
    _, v1 = publicar_v1(qc.padroes)
    r = qc.post(f"{BASE}/padroes/imob-lead/versoes", json={"copiar_de": str(v1), "notas": "ajuste"})
    v2 = r.json()["id"]
    assert r.json()["versao"] == 2 and len(r.json()["criterios"]) == len(versao_v1().criterios)
    assert qc.patch(f"{BASE}/versoes/{v2}", json={"notas": "novo texto"}).json()["notas"] == "novo texto"
    assert qc.post(f"{BASE}/versoes/{v2}/publicar").status_code == 200
    statuses = {v["versao"]: v["status"] for v in qc.get(f"{BASE}/padroes/imob-lead/versoes").json()["items"]}
    assert statuses == {1: "arquivada", 2: "publicada"}


def test_discard_draft_and_remove_children(qc):
    _, v1 = publicar_v1(qc.padroes)
    v2 = qc.post(f"{BASE}/padroes/imob-lead/versoes", json={"copiar_de": str(v1)}).json()["id"]
    assert qc.delete(f"{BASE}/versoes/{v2}/criterios/email").status_code == 200
    assert qc.delete(f"{BASE}/versoes/{v2}/criterios/email").status_code == 404
    assert qc.delete(f"{BASE}/versoes/{v2}/estagios/descartado").status_code == 200
    assert qc.delete(f"{BASE}/versoes/{v2}").status_code == 204
    assert qc.get(f"{BASE}/versoes/{v2}").status_code == 404


def test_strict_bodies_and_key_shapes(qc):
    qc.post(f"{BASE}/padroes", json={"chave": "imob-lead", "nome": "I"})
    vid = qc.post(f"{BASE}/padroes/imob-lead/versoes", json={}).json()["id"]
    assert qc.put(f"{BASE}/versoes/{vid}/criterios/operacao", json={**_criterio_body(), "org_id": str(uuid4())}).status_code == 422
    assert qc.put(f"{BASE}/versoes/{vid}/criterios/operacao", json=_criterio_body(tipo="livre")).status_code == 422
    assert qc.put(f"{BASE}/versoes/{vid}/criterios/Operacao", json=_criterio_body()).status_code == 422
    assert qc.put(f"{BASE}/versoes/{vid}/parametros", json={"minimo_para_ofertar": {}, "lote_ofertas": 9}).status_code == 422
    assert qc.post(f"{BASE}/padroes", json={"chave": "x", "nome": "N", "origem_padrao_id": str(uuid4())}).status_code == 422
    assert qc.post(f"{BASE}/padroes/nada/versoes", json={}).status_code == 404


# ── GET /api/channels/leads/{ref}/qualificacao ──────────────────────────────

def _channel_auth(scopes, org=DEFAULT_ORG_ID, issuer="social-wiring"):
    from app.main import app

    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        org_id=org, caller_kind="product", user_id=None, scopes=list(scopes), raw_token="t",
        api_token_id=UUID(int=9), issuer=issuer,
    )


@pytest.fixture
def chan_auth():
    from app.main import app

    yield _channel_auth
    app.dependency_overrides.pop(get_auth_context, None)


def _seed_lead(qc, org=DEFAULT_ORG_ID):
    padroes, vid = publicar_v1(qc.padroes)
    svc = QualificacaoService(padroes, qc.leads)
    svc.registrar_perfil(org, LEAD, agent_id=AGENTE, versao_id=vid, itens=[ItemPerfil("operacao", "compra", "comprar")],
                         mensagens_lead=["quero comprar"])
    svc.registrar_evento_imovel(org, LEAD, agent_id=AGENTE, versao_id=vid, codigo_imovel="AP1", evento="oferecido", lote=1)
    return vid


def test_lead_qualificacao_returns_state_and_events(qc, chan_auth):
    vid = _seed_lead(qc)
    chan_auth(["agents:channel-status"])
    r = qc.raw().get(f"/api/channels/leads/{LEAD}/qualificacao")
    assert r.status_code == 200
    b = r.json()
    assert (b["estagio"], b["score"], b["versao_id"]) == ("em_conversa", 10, str(vid))
    assert b["valores"]["operacao"] == "compra" and b["valores"]["imoveis_oferecidos"] == 1
    assert b["faltando"] == ["tipo_imovel", "faixa_preco", "regioes"]
    assert [e["codigo_imovel"] for e in b["eventos_imovel"]] == ["AP1"]
    assert "trecho" not in str(b)  # literal quotes never leave through the read API


def test_lead_qualificacao_404_for_unknown_and_for_another_org(qc, chan_auth):
    _seed_lead(qc)
    chan_auth(["agents:channel-status"])
    assert qc.raw().get(f"/api/channels/leads/{uuid4()}/qualificacao").json()["code"] == "lead_sem_qualificacao"
    chan_auth(["agents:channel-status"], org=uuid4())
    assert qc.raw().get(f"/api/channels/leads/{LEAD}/qualificacao").status_code == 404


def test_lead_qualificacao_auth_boundary(qc, chan_auth):
    _seed_lead(qc)
    url = f"/api/channels/leads/{LEAD}/qualificacao"
    assert qc.raw().get(url).status_code == 401
    chan_auth(["agents:channel-turn"])
    assert qc.raw().get(url).status_code == 403  # wrong scope
    chan_auth(["agents:channel-status"], issuer="outro")
    assert qc.raw().get(url).status_code == 403  # issuer not allowed
