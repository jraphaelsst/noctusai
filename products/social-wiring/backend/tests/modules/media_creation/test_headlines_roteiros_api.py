"""HR-1: ``GET /headlines-roteiros`` (contract 6.9) and ``GET /esteira/posts/{id}/origem`` (contract 6.8)."""
import hashlib
import json
import uuid

from noctusai_lib.testing import TEST_ORG_ID, TEST_USER_ID

LISTA = "/api/media-creation/headlines-roteiros"
ORIGEM = "/api/media-creation/esteira/posts/{}/origem"
MARCA = str(uuid.uuid4())
OUTRA_MARCA = str(uuid.uuid4())
OUTRA_ORG = "other-org"


def _u() -> str:
    return str(uuid.uuid4())


def _seed(client):
    db = client.mock_supabase
    db.from_("marcas").insert({"id": MARCA, "org_id": TEST_ORG_ID, "name": "A"}).execute()
    db.from_("marcas").insert({"id": OUTRA_MARCA, "org_id": OUTRA_ORG, "name": "B"}).execute()
    db.from_("cs_perfis_monitorados").insert({"id": "p1", "handle": "fernando", "nome": "Fernando"}).execute()
    db.from_("cs_estruturas").insert({"id": "e1", "codigo": 7, "perfil_id": "p1", "formula_headline": "Pare de " + "x" * 200}).execute()
    db.from_("cs_estrutura_blocos").insert([
        {"id": "b1", "estrutura_id": "e1", "ordem": 1, "nome": "Gancho"},
        {"id": "b2", "estrutura_id": "e1", "ordem": 2, "nome": "Prova"},
    ]).execute()
    db.from_("cs_chat_conversas").insert([
        {"id": "c-mine", "org_id": TEST_ORG_ID, "marca_id": MARCA, "user_id": TEST_USER_ID, "titulo": "Minha conversa"},
        {"id": "c-other", "org_id": TEST_ORG_ID, "marca_id": MARCA, "user_id": "someone-else", "titulo": "Alheia"},
    ]).execute()
    return db


def _headline(db, hid, texto, *, favorita=False, conversa=None, created="2026-11-10T10:00:00+00:00", marca=MARCA, org=TEST_ORG_ID):
    db.from_("cs_headlines").insert({
        "id": hid, "org_id": org, "marca_id": marca, "texto": texto, "favorita": favorita,
        "conversa_id": conversa, "created_at": created,
    }).execute()


def _roteiro(db, rid, *, headline=None, texto="livre", status="completo", formato="reels", conversa=None,
             created="2026-11-11T10:00:00+00:00", marca=MARCA, org=TEST_ORG_ID, estrutura="cta_final"):
    db.from_("cs_roteiros").insert({
        "id": rid, "org_id": org, "marca_id": marca, "nome": f"Roteiro {rid}", "headline_id": headline,
        "headline_texto": texto, "status": status, "formato": formato, "conversa_id": conversa, "created_at": created,
        "duracao": "2", "estrutura": estrutura, "versao": 3,
    }).execute()


def _uso(db, *, headline=None, roteiro=None, papel="principal", ordem=1, blocos=(), org=TEST_ORG_ID, estrutura="e1"):
    db.from_("cs_estrutura_usos").insert({
        "id": _u(), "org_id": org, "marca_id": MARCA, "estrutura_id": estrutura, "contexto": "chat", "papel": papel,
        "ordem": ordem, "bloco_ids": list(blocos), "headline_id": headline, "roteiro_id": roteiro,
    }).execute()


def _get(client, **params):
    return client.get(LISTA, params={"marca_id": MARCA, **params})


# -- auth / marca scope -------------------------------------------------------------------------------------------


def test_unauthenticated_list_is_a_strict_401(anon_client):
    r = anon_client.get(LISTA, params={"marca_id": MARCA})
    assert r.status_code == 401, r.text


def test_unauthenticated_origem_is_a_strict_401(anon_client):
    r = anon_client.get(ORIGEM.format(_u()))
    assert r.status_code == 401, r.text


def test_marca_id_is_required_and_foreign_marca_is_404(client):
    _seed(client)
    assert client.get(LISTA).status_code == 422
    for outra in (OUTRA_MARCA, _u()):
        r = client.get(LISTA, params={"marca_id": outra})
        assert r.status_code == 404, r.text


# -- the list -----------------------------------------------------------------------------------------------------


def test_inclusion_rule_and_item_shape(client):
    db = _seed(client)
    _headline(db, "h-fav", "Favorita", favorita=True)
    _headline(db, "h-conv", "Da conversa", conversa="c-mine", created="2026-11-09T10:00:00+00:00")
    _headline(db, "h-rot", "Com roteiro", created="2026-11-08T10:00:00+00:00")
    _headline(db, "h-lote", "Solta de um lote (fora)")
    _headline(db, "h-foreign", "De outra marca", marca=OUTRA_MARCA, org=OUTRA_ORG, favorita=True)
    _roteiro(db, "r1", headline="h-rot", conversa="c-other")
    _roteiro(db, "r-livre", headline=None, texto="Roteiro avançado sem headline", created="2026-11-12T10:00:00+00:00")
    _roteiro(db, "r-foreign", marca=OUTRA_MARCA, org=OUTRA_ORG, texto="alheio")
    r = _get(client)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert set(data) == {"items", "total"} and data["total"] == 4
    ids = [(i["headline"] or {}).get("id") or i["roteiro"]["id"] for i in data["items"]]
    assert ids == ["r-livre", "h-rot", "h-fav", "h-conv"]  # newest first
    por = {(i["headline"] or {}).get("id") or i["roteiro"]["id"]: i for i in data["items"]}
    livre = por["r-livre"]
    assert livre["headline"] is None and livre["headline_texto"] == "Roteiro avançado sem headline"
    assert livre["roteiro"] == {
        "id": "r-livre", "nome": "Roteiro r-livre", "status": "completo", "formato": "reels", "duracao": "2",
        "ordem_cta": "cta_final", "versao": 3, "aprovacao": None,
    }
    assert set(livre) == {"headline", "headline_texto", "roteiro", "estruturas", "conversa", "post", "created_at"}
    com = por["h-rot"]
    assert set(com["headline"]) == {"id", "texto", "favorita", "created_at", "acima_recomendado"}
    assert com["headline"]["acima_recomendado"] is False and com["headline_texto"] == "Com roteiro"
    assert com["roteiro"]["aprovacao"] is None
    assert por["h-fav"]["roteiro"] is None and por["h-fav"]["headline"]["favorita"] is True
    assert "h-lote" not in por and "h-foreign" not in por


def test_conversation_is_only_shown_to_its_author(client):
    db = _seed(client)
    _headline(db, "h1", "Minha", favorita=True, conversa="c-mine")
    _headline(db, "h2", "De outro", favorita=True, conversa="c-other")
    por = {i["headline"]["id"]: i for i in _get(client).json()["data"]["items"]}
    assert por["h1"]["conversa"] == {"id": "c-mine", "titulo": "Minha conversa"}
    assert por["h2"]["conversa"] is None
    assert "Alheia" not in json.dumps(por)


def test_estruturas_roteiro_row_wins_and_has_blocks(client):
    db = _seed(client)
    _headline(db, "h1", "Com estrutura", favorita=True)
    _roteiro(db, "r1", headline="h1")
    _uso(db, headline="h1", blocos=())
    _uso(db, headline="h1", roteiro="r1", blocos=("b2", "b1"))
    item = _get(client).json()["data"]["items"][0]
    assert item["estruturas"] == [{
        "id": "e1", "codigo": 7, "perfil": {"id": "p1", "handle": "fernando", "nome": "Fernando"},
        "formula_trecho": item["estruturas"][0]["formula_trecho"], "papel": "principal",
        "blocos": [{"id": "b1", "nome": "Gancho"}, {"id": "b2", "nome": "Prova"}],
    }]
    assert len(item["estruturas"][0]["formula_trecho"]) <= 120


def test_filters(client):
    db = _seed(client)
    e1, p2, e2 = _u(), _u(), _u()
    db.from_("cs_perfis_monitorados").insert({"id": p2, "handle": "outro", "nome": "Outro"}).execute()
    db.from_("cs_estruturas").insert([
        {"id": e1, "codigo": 9, "perfil_id": "p1", "formula_headline": "f"},
        {"id": e2, "codigo": 8, "perfil_id": p2, "formula_headline": "f"},
    ]).execute()
    _headline(db, "h1", "Pare de procrastinar", favorita=True)
    _headline(db, "h2", "Açúcar vicia", favorita=True)
    _roteiro(db, "r2", headline="h2", status="falha")
    _roteiro(db, "r3", headline=None, texto="Livre", status="processando")
    _uso(db, headline="h1", estrutura=e1)
    _uso(db, roteiro="r2", estrutura=e2)

    def ids(**p):
        return sorted((i["headline"] or {}).get("id") or i["roteiro"]["id"] for i in _get(client, **p).json()["data"]["items"])

    assert ids(perfil_id=_u()) == []
    assert ids(q="ACUCAR") == ["h2"]
    assert ids(q="roteiro r3") == ["r3"]
    assert ids(roteiro_status="sem_roteiro") == ["h1"]
    assert ids(roteiro_status="falha") == ["h2"]
    assert ids(estrutura_id=e1) == ["h1"]
    assert ids(perfil_id=p2) == ["h2"]
    assert _get(client, roteiro_status="nope").status_code == 422
    assert _get(client, aprovacao="nope").status_code == 422
    # approval is null-valued until wave 3: no item can match a state
    assert ids(aprovacao="pendente") == []


def test_pagination_and_limits(client):
    db = _seed(client)
    for n in range(5):
        _headline(db, f"h{n}", f"H{n}", favorita=True, created=f"2026-11-1{n}T10:00:00+00:00")
    d = _get(client, limit=2, offset=1).json()["data"]
    assert d["total"] == 5 and [i["headline"]["id"] for i in d["items"]] == ["h3", "h2"]
    assert _get(client, limit=0).status_code == 422 and _get(client, limit=51).status_code == 422


# -- esteira origem -----------------------------------------------------------------------------------------------


def _post(db, pid, *, formato="reel", legenda=None, headline=None, roteiro=None, org=TEST_ORG_ID):
    db.from_("cs_posts").insert({
        "id": pid, "org_id": org, "marca_id": MARCA, "formato": formato, "titulo": "Card", "etapa_id": _u(),
        "headline_id": headline, "roteiro_id": roteiro, "legenda": legenda,
    }).execute()


def test_origem_foreign_or_unknown_post_is_404(client):
    db = _seed(client)
    foreign = _u()
    _post(db, foreign, org=OUTRA_ORG)
    for pid in (foreign, _u()):
        r = client.get(ORIGEM.format(pid))
        assert r.status_code == 404, r.text
    assert client.get(ORIGEM.format("nao-e-uuid")).status_code == 422


def test_origem_full_composition(client):
    pid = _u()
    db = _seed(client)
    _headline(db, "h1", "A headline", favorita=True, conversa="c-mine")
    _roteiro(db, "r1", headline="h1", formato="carrossel", conversa="c-mine")
    _uso(db, headline="h1", roteiro="r1", blocos=("b1",))
    _post(db, pid, formato="carrossel", legenda="Texto da IA", headline="h1", roteiro="r1")
    db.from_("cs_fluxo_eventos").insert({
        "id": _u(), "org_id": TEST_ORG_ID, "marca_id": MARCA, "conversa_id": "c-mine", "post_id": pid,
        "tipo": "legenda_gerada", "codigo": hashlib.sha256("Texto da IA".encode()).hexdigest(),
    }).execute()
    r = client.get(ORIGEM.format(pid))
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert set(d) == {"headline", "roteiro", "estruturas", "formato", "legenda", "conversa"}
    assert d["headline"] == {"id": "h1", "texto": "A headline"}
    assert d["roteiro"] == {
        "id": "r1", "nome": "Roteiro r1", "status": "completo", "formato": "carrossel", "duracao": "2",
        "ordem_cta": "cta_final", "versao": 3,
    }
    assert d["formato"] == "carrossel"
    assert d["legenda"] == {"texto": "Texto da IA", "origem": "ia"}
    assert d["conversa"] == {"id": "c-mine", "titulo": "Minha conversa"}
    assert d["estruturas"][0]["blocos"] == [{"id": "b1", "nome": "Gancho"}] and d["estruturas"][0]["papel"] == "principal"


def test_origem_legenda_origin_rules_and_bare_card(client):
    db = _seed(client)
    bare, edited, empty = _u(), _u(), _u()
    _post(db, bare, formato="story")
    _post(db, edited, legenda="Editada pelo usuário")
    _post(db, empty, legenda=None)
    db.from_("cs_fluxo_eventos").insert({
        "id": _u(), "org_id": TEST_ORG_ID, "marca_id": MARCA, "conversa_id": "c-mine", "post_id": edited,
        "tipo": "legenda_gerada", "codigo": hashlib.sha256(b"Original da IA").hexdigest(),
    }).execute()
    d = client.get(ORIGEM.format(bare)).json()["data"]
    assert d["headline"] is None and d["roteiro"] is None and d["estruturas"] == [] and d["conversa"] is None
    assert d["formato"] == "stories" and d["legenda"] == {"texto": None, "origem": None}
    assert client.get(ORIGEM.format(edited)).json()["data"]["legenda"] == {"texto": "Editada pelo usuário", "origem": "usuario"}
    assert client.get(ORIGEM.format(empty)).json()["data"]["legenda"]["origem"] is None


def test_registration_and_tiers():
    from app.modules.media_creation import register
    from app.modules.media_creation.routers import esteira_origem, headlines_roteiros

    routers = list(register().routers)
    assert headlines_roteiros.router in routers and esteira_origem.router in routers
