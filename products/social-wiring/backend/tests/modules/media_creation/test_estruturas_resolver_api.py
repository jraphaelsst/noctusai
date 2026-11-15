"""EST-4a: ``GET /estruturas/resolver-perfil`` -- the same deterministic resolver the AI uses (contract 6.1 / 8.3)."""
import uuid

from noctusai_lib.testing import TEST_ORG_ID

from app.modules.media_creation.services.estruturas_retrieval import invalidar_indice

URL = "/api/media-creation/estruturas/resolver-perfil"
MARCA = str(uuid.uuid4())
OUTRA_MARCA = str(uuid.uuid4())


def _seed(client):
    invalidar_indice()
    db = client.mock_supabase
    db.from_("marcas").insert({"id": MARCA, "org_id": TEST_ORG_ID, "name": "A"}).execute()
    db.from_("marcas").insert({"id": OUTRA_MARCA, "org_id": "other-org", "name": "B"}).execute()
    db.from_("cs_perfis_monitorados").insert([
        {"id": "p1", "handle": "psifernandosegredo", "nome": "Fernando Segredo"},
        {"id": "p2", "handle": "fernando.mendes", "nome": "Fernando Mendes"},
    ]).execute()
    db.from_("cs_estruturas").insert({"id": "e1", "perfil_id": "p1", "status": "ativa"}).execute()


def test_unauthenticated_is_a_strict_401(anon_client):
    r = anon_client.get(URL, params={"texto": "estilo do Fernando"})
    assert r.status_code == 401, r.text


def test_resolved_ambiguous_and_not_found(client):
    _seed(client)
    r = client.get(URL, params={"texto": "um post no estilo do Fernando Segredo"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["resolvidos"] == [{"perfil_id": "p1", "handle": "psifernandosegredo", "nome": "Fernando Segredo",
                                "via": "nome", "confianca": d["resolvidos"][0]["confianca"]}]
    assert d["resolvidos"][0]["confianca"] >= 0.8 and d["ambiguos"] == [] and d["nao_encontrados"] == []
    d = client.get(URL, params={"texto": "no estilo do Fernando"}).json()["data"]
    assert d["resolvidos"] == [] and {c["perfil_id"] for c in d["ambiguos"][0]["candidatos"]} == {"p1", "p2"}
    d = client.get(URL, params={"texto": "estilo do Zé Ninguém"}).json()["data"]
    assert d["nao_encontrados"][0]["trecho"] == "ze ninguem"
    assert client.get(URL, params={"texto": "me escreva uma headline"}).json()["data"] == {
        "resolvidos": [], "ambiguos": [], "nao_encontrados": []}


def test_marca_is_ownership_checked_404_never_403(client):
    _seed(client)
    assert client.get(URL, params={"texto": "estilo do Fernando Segredo", "marca_id": MARCA}).status_code == 200
    for outra in (OUTRA_MARCA, str(uuid.uuid4())):
        r = client.get(URL, params={"texto": "estilo do Fernando Segredo", "marca_id": outra})
        assert r.status_code == 404, r.text


def test_validation_texto_is_required_and_bounded(client):
    _seed(client)
    assert client.get(URL).status_code == 422
    assert client.get(URL, params={"texto": ""}).status_code == 422
    assert client.get(URL, params={"texto": "x" * 301}).status_code == 422
    assert client.get(URL, params={"texto": "x" * 300}).status_code == 200


def test_the_static_path_is_not_swallowed_by_the_id_route(client):
    """/resolver-perfil is included BEFORE /{estrutura_id}: it answers a resolution, never an Estrutura 422/404."""
    _seed(client)
    r = client.get(URL, params={"texto": "estilo do Fernando Segredo"})
    assert r.status_code == 200 and set(r.json()["data"]) == {"resolvidos", "ambiguos", "nao_encontrados"}


def test_registration_order_puts_the_resolver_before_both_estruturas_routers():
    from app.modules.media_creation import register
    from app.modules.media_creation.routers import estruturas, estruturas_admin, estruturas_resolver

    routers = list(register().routers)
    assert routers.index(estruturas_resolver.router) < routers.index(estruturas_admin.router) < routers.index(estruturas.router)
