"""Estruturas library endpoints (estruturas-contract.md sections 4.1, 6.0-6.2): reads (tier org) + admin writes (tier platform).

Mounted through the real ``register()`` seam on the MockSupabaseClient. The platform-admin check is the production DI
seam (``get_platform_admin_check``) overridden, never patched. The RPCs run in SQL (``test_migration_cs_estruturas.py``
exercises them on PGlite); here a recording stub stands in for ``client.rpc`` so the service's parameter names, its
error mapping and its read-after-write are pinned. Auth tests assert STRICT ``== 401`` / ``== 403``.
"""
import json
import uuid

import pytest

from noctusai_lib.integrations.storage import FakeStorageBackend

from app.dependencies import get_platform_admin_check
from app.modules.media_creation.routers.estruturas import get_estruturas_storage
from app.modules.media_creation.services import estruturas_service as svc

BASE = "/api/media-creation/estruturas"
ORG = "test-org-123"
MARCA = str(uuid.uuid4())
FOREIGN_MARCA = str(uuid.uuid4())
P1 = str(uuid.uuid4())
P2 = str(uuid.uuid4())
V1 = str(uuid.uuid4())
V_P2 = str(uuid.uuid4())
T_HEAD = str(uuid.uuid4())
T_REV = str(uuid.uuid4())
T_OFF = str(uuid.uuid4())
T_OUTRO = str(uuid.uuid4())
E1, E2, E_DRAFT, E_ARCH = (str(uuid.uuid4()) for _ in range(4))
B1, B2, B3 = (str(uuid.uuid4()) for _ in range(3))
ADMIN_FORBIDDEN = {
    "proveniencia", "ref_externa", "referencia_rotulo", "formula_herdada_de", "pendente_revisao", "origem",
    "fonte_externa", "fonte_hash", "formula_origem", "formato_origem", "objetivos_origem", "nome_origem",
    "tipo_origem", "tempo_origem", "instrucao_origem", "campos_pendentes", "created_by", "updated_by", "sistema",
    "revisao_por_desuso", "revisao_desuso_em", "foto_url", "foto_path",
}


class FakeApiError(Exception):
    """A PostgREST ``APIError`` double (the attributes ``mapear_erro_rpc`` reads)."""

    def __init__(self, message: str, details: str = "", code: str = "P0001"):
        super().__init__({"message": message, "details": details, "code": code})
        self.message, self.details, self.code = message, details, code


class _Exec:
    def __init__(self, data=None, exc=None):
        self.data, self._exc = data, exc

    def execute(self):
        if self._exc:
            raise self._exc
        return self

    count = None


class RpcStub:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.results: dict[str, dict] = {}
        self.errors: dict[str, Exception] = {}

    def __call__(self, name, params=None):
        self.calls.append((name, dict(params or {})))
        if name in self.errors:
            return _Exec(exc=self.errors[name])
        return _Exec(data=self.results.get(name, {}))

    def last(self, name):
        return [p for n, p in self.calls if n == name][-1]


class State:
    def __init__(self, client):
        self.client = client
        self.storage = FakeStorageBackend()
        self.admin = False
        self.rpc = RpcStub()
        app = client._tc.app
        app.dependency_overrides[get_estruturas_storage] = lambda: self.storage
        app.dependency_overrides[get_platform_admin_check] = lambda: (lambda uid: self.admin)
        client.mock_supabase.rpc = self.rpc  # a recording double for the SQL RPCs (their SQL is run on PGlite)

    @property
    def db(self):
        return self.client.mock_supabase


def _estrutura(db, eid, *, perfil, codigo, status="ativa", formula="Como [x] faz y", formato="reels", objetivos=("alcance",),
               viral=None, blocos=(), origem="import_corestudio", versao=1, origins=None, updated_at="2026-11-15T10:00:00+00:00"):
    o = {"formula": "admin", "formato": "admin", "objetivos": "admin", **(origins or {})}
    db.from_("cs_estruturas").insert({
        "id": eid, "codigo": codigo, "perfil_id": perfil, "viral_id": viral, "formula_headline": formula, "formato": formato,
        "objetivos": list(objetivos), "status": status, "origem": origem, "fonte_externa": "corestudio", "ref_externa": str(codigo),
        "fonte_hash": "h", "formula_herdada_de": "9", "referencia_rotulo": "ref-2026", "formula_origem": o["formula"],
        "formato_origem": o["formato"], "objetivos_origem": o["objetivos"], "versao": versao, "created_by": "u1", "updated_by": "u1",
        "created_at": updated_at, "updated_at": updated_at,
    }).execute()
    pend = sum(1 for v in o.values() if v in ("referencia", "ia_sugerido"))
    for i, b in enumerate(blocos, start=1):
        row = {
            "id": b["id"], "estrutura_id": eid, "ordem": i, "tipo_id": b["tipo"], "nome": b["nome"], "tempo": b.get("tempo"),
            "instrucao": b.get("instrucao"), "nota": b.get("nota"), "repeticoes": b.get("repeticoes", 1),
            "nome_origem": "fonte", "tipo_origem": b.get("tipo_origem", "admin"), "tempo_origem": "admin", "instrucao_origem": "admin",
        }
        db.from_("cs_estrutura_blocos").insert(row).execute()
        pend += sum(1 for k in ("nome_origem", "tipo_origem", "tempo_origem", "instrucao_origem") if row[k] in ("referencia", "ia_sugerido"))
    # the derived view (never stored in SQL; a table in the mock)
    db.from_("cs_estruturas_resumo").insert({
        "id": eid, "codigo": codigo, "perfil_id": perfil, "viral_id": viral, "formula_headline": formula, "formato": formato,
        "objetivos": list(objetivos), "status": status, "updated_at": updated_at, "blocos_total": len(blocos),
        "campos_pendentes": pend,
    }).execute()


@pytest.fixture
def est(client):
    st = State(client)
    db = st.db
    db.from_("marcas").insert({"id": MARCA, "org_id": ORG, "name": "Marca A"}).execute()
    db.from_("marcas").insert({"id": FOREIGN_MARCA, "org_id": "other-org", "name": "Marca B"}).execute()
    for pid, handle, nome in ((P1, "psifernandosegredo", "Fernando Segredo"), (P2, "outra.criadora", None)):
        db.from_("cs_perfis_monitorados").insert({"id": pid, "org_id": None, "handle": handle, "nome": nome, "foto_path": f"platform/{pid}/foto.jpg"}).execute()
    db.from_("cs_virais").insert({"id": V1, "org_id": None, "perfil_id": P1, "codigo": 77, "permalink": "https://www.instagram.com/reel/AAA/", "thumbnail_path": f"platform/{P1}/AAA.jpg"}).execute()
    db.from_("cs_virais").insert({"id": V_P2, "org_id": None, "perfil_id": P2, "codigo": 78, "permalink": "https://www.instagram.com/reel/BBB/"}).execute()
    for tid, nome, ordem, ativo, sistema in ((T_HEAD, "Headline", 1, True, False), (T_REV, "Revelação", 2, True, False),
                                             (T_OFF, "CTA Curtir", 3, False, False), (T_OUTRO, "Outro", 4, True, True)):
        db.from_("cs_estrutura_tipos_bloco").insert({
            "id": tid, "nome": nome, "ordem": ordem, "tempo_tipico": "0–3s", "instrucao_referencia": f"instrução {nome}",
            "ativo": ativo, "sistema": sistema, "versao": 3,
        }).execute()
    _estrutura(db, E1, perfil=P1, codigo=101, viral=V1, origins={"formato": "referencia"}, blocos=[
        {"id": B1, "tipo": T_HEAD, "nome": "Abertura", "tempo": "0–3s", "instrucao": "Fale a promessa", "nota": "sobre o vídeo original", "repeticoes": 1, "tipo_origem": "referencia"},
        {"id": B2, "tipo": T_REV, "nome": "Virada", "repeticoes": 2},
    ])
    _estrutura(db, E2, perfil=P2, codigo=102, formato="carrossel", objetivos=("autoridade", "venda"),
               blocos=[{"id": B3, "tipo": T_OUTRO, "nome": "Slide"}], updated_at="2026-11-14T10:00:00+00:00")
    _estrutura(db, E_DRAFT, perfil=P1, codigo=103, status="rascunho", origem="viral_auto", origins={"formula": "ia_sugerido"})
    _estrutura(db, E_ARCH, perfil=P2, codigo=104, status="arquivada")
    db.from_("cs_biblioteca_referencias").insert({"id": str(uuid.uuid4()), "org_id": ORG, "marca_id": MARCA, "modo": "perfil", "perfil_id": P1}).execute()
    return st


# ── auth: strict 401 / 403 on EVERY route ─────────────────────────────────────────────────────────────────

_ID = str(uuid.uuid4())
READS = [
    ("get", ""), ("get", "/admin"), ("get", "/tipos-bloco"), ("get", f"/{_ID}"),
]
WRITES = [
    ("post", "", {"json": {"perfil_id": P1, "formula_headline": "x", "formato": "reels", "objetivos": ["alcance"], "blocos": [{"nome": "a", "tipo_id": T_HEAD}]}}),
    ("patch", f"/{_ID}", {"json": {"expected_versao": 1, "formato": "post"}}),
    ("put", f"/{_ID}/blocos", {"json": {"expected_versao": 1, "blocos": [{"nome": "a", "tipo_id": T_HEAD}]}}),
    ("post", f"/{_ID}/confirmar", {"json": {"expected_versao": 1, "todos": True}}),
    ("post", f"/{_ID}/publicar", {"json": {"expected_versao": 1}}),
    ("post", f"/{_ID}/arquivar", {}),
    ("post", f"/{_ID}/restaurar", {}),
    ("delete", f"/{_ID}", {}),
    ("post", "/tipos-bloco", {"json": {"nome": "N", "instrucao_referencia": "i"}}),
    ("put", f"/tipos-bloco/{_ID}", {"json": {"expected_versao": 1, "ativo": False}}),
    ("delete", f"/tipos-bloco/{_ID}", {}),
]


class TestAuth:
    @pytest.mark.parametrize("method,path", READS)
    def test_reads_unauthenticated_is_401(self, client, method, path):
        r = getattr(client._tc, method)(BASE + path)
        assert r.status_code == 401, (path, r.status_code, r.text)

    @pytest.mark.parametrize("method,path,kw", WRITES)
    def test_writes_unauthenticated_is_401(self, client, method, path, kw):
        r = getattr(client._tc, method)(BASE + path, **kw)
        assert r.status_code == 401, (method, path, r.status_code, r.text)

    @pytest.mark.parametrize("method,path,kw", WRITES)
    def test_writes_by_an_org_member_who_is_not_a_platform_admin_are_403(self, est, client, method, path, kw):
        est.admin = False
        r = getattr(client, method)(BASE + path, **kw)
        assert r.status_code == 403, (method, path, r.status_code, r.text)
        # a plain-string detail goes through the seed's legacy envelope (contract 0.2 says {"detail": ...}: it is not)
        assert r.json()["error"]["code"] == "FORBIDDEN"
        assert r.json()["error"]["message"] == "Restrito a administradores da plataforma NoctusAI."
        assert est.rpc.calls == []  # refused BEFORE any write

    @pytest.mark.parametrize("method,path", READS)
    def test_reads_are_open_to_every_authenticated_member(self, est, client, method, path):
        est.admin = False
        r = getattr(client, method)(BASE + path)
        assert r.status_code in (200, 404), (path, r.status_code)  # 404 only for the random id; never 401/403
        assert r.status_code != 403

    def test_admin_probe_reports_the_callers_own_flag(self, est, client):
        assert client.get(f"{BASE}/admin").json() == {"data": {"is_admin": False}}
        est.admin = True
        assert client.get(f"{BASE}/admin").json() == {"data": {"is_admin": True}}


class TestTiers:
    def test_writes_live_in_a_platform_router_and_reads_in_an_org_router(self):
        from app.modules.media_creation.routers import estruturas, estruturas_admin

        assert estruturas.router.access_tier == "org"
        assert estruturas_admin.router.access_tier == "platform"
        assert not any(r.methods - {"GET"} for r in estruturas.router.routes), "a read router must never carry a write"
        assert all(r.methods - {"GET"} for r in estruturas_admin.router.routes), "a write router must carry no read"

    def test_the_admin_writes_are_left_out_of_the_public_openapi_schema(self, client):
        paths = client._tc.app.openapi()["paths"]
        assert set(paths[BASE]) == {"get"}
        assert f"{BASE}/{{estrutura_id}}" in paths and set(paths[f"{BASE}/{{estrutura_id}}"]) == {"get"}
        assert not any("publicar" in p or "arquivar" in p or "confirmar" in p for p in paths)
        assert set(paths[f"{BASE}/tipos-bloco"]) == {"get"}


# ── reads ─────────────────────────────────────────────────────────────────────────────────────────────────


def _items(r):
    assert r.status_code == 200, r.text
    return r.json()["data"]["items"]


class TestList:
    def test_member_sees_only_ativa_rows_in_the_documented_shape(self, est, client):
        r = client.get(BASE)
        d = r.json()["data"]
        assert set(d) == {"items", "total"} and d["total"] == 2
        assert [i["id"] for i in d["items"]] == [E1, E2]  # newest update first
        item = d["items"][0]
        assert set(item) == {"id", "codigo", "perfil", "formula_headline", "formato", "objetivos", "blocos_total", "viral", "status", "updated_at"}
        assert item["codigo"] == 101 and item["formato"] == "reels" and item["blocos_total"] == 2 and item["status"] == "ativa"
        # a client org sees the creator as handle + name ONLY: no photo key at all (owner decision 2026-11-15)
        assert item["perfil"] == {"id": P1, "handle": "psifernandosegredo", "nome": "Fernando Segredo"}
        assert item["viral"]["codigo"] == 77 and item["viral"]["permalink"].endswith("AAA/")
        assert item["viral"]["thumbnail_url"].startswith(f"fake://storage/sw-biblioteca/platform/{P1}/AAA.jpg")
        assert d["items"][1]["viral"] is None and d["items"][1]["perfil"]["nome"] is None

    def test_a_member_can_never_widen_the_status_filter(self, est, client):
        for q in ("status=todas", "status=rascunho", "status=arquivada", "somente_pendentes_revisao=true"):
            ids = {i["id"] for i in _items(client.get(f"{BASE}?{q}"))}
            assert ids == {E1, E2}, q

    def test_admin_default_is_ativa_and_status_widens_it(self, est, client):
        est.admin = True
        assert {i["id"] for i in _items(client.get(BASE))} == {E1, E2}
        assert {i["id"] for i in _items(client.get(f"{BASE}?status=todas"))} == {E1, E2, E_DRAFT, E_ARCH}
        assert [i["id"] for i in _items(client.get(f"{BASE}?status=rascunho"))] == [E_DRAFT]
        assert [i["id"] for i in _items(client.get(f"{BASE}?status=arquivada"))] == [E_ARCH]

    def test_admin_items_carry_pendente_revisao_and_members_never_do(self, est, client):
        assert all("pendente_revisao" not in i for i in _items(client.get(BASE)))
        est.admin = True
        by_id = {i["id"]: i for i in _items(client.get(f"{BASE}?status=todas"))}
        assert by_id[E1]["pendente_revisao"] is True and by_id[E2]["pendente_revisao"] is False and by_id[E_DRAFT]["pendente_revisao"] is True
        pend = {i["id"] for i in _items(client.get(f"{BASE}?somente_pendentes_revisao=true&status=todas"))}
        assert pend == {E1, E_DRAFT}

    def test_filters_perfil_formato_objetivo_and_paging(self, est, client):
        assert [i["id"] for i in _items(client.get(f"{BASE}?perfil_id={P2}"))] == [E2]
        assert [i["id"] for i in _items(client.get(f"{BASE}?formato=carrossel"))] == [E2]
        assert {i["id"] for i in _items(client.get(f"{BASE}?formato=carrossel&formato=reels"))} == {E1, E2}
        assert _items(client.get(f"{BASE}?objetivo=venda&objetivo=autoridade"))  # `overlaps` is match-all in the mock: the predicate is pinned in TestPredicates
        page = client.get(f"{BASE}?limit=1&offset=1").json()["data"]
        assert [i["id"] for i in page["items"]] == [E2] and page["total"] == 2

    @pytest.mark.parametrize("qs", ["limit=0", "limit=51", "offset=-1", "formato=video", "objetivo=fama", "status=publicada",
                                    "q=" + "x" * 201, "marca_id=nao-uuid", "perfil_id=nao-uuid"])
    def test_invalid_query_is_422(self, est, client, qs):
        assert client.get(f"{BASE}?{qs}").status_code == 422

    def test_marca_adds_selecionada_pela_marca_and_a_foreign_marca_is_404(self, est, client):
        items = {i["id"]: i for i in _items(client.get(f"{BASE}?marca_id={MARCA}"))}
        assert items[E1]["selecionada_pela_marca"] is True and items[E2]["selecionada_pela_marca"] is False
        assert all("selecionada_pela_marca" not in i for i in _items(client.get(BASE)))
        assert client.get(f"{BASE}?marca_id={FOREIGN_MARCA}").status_code == 404
        assert client.get(f"{BASE}?marca_id={uuid.uuid4()}").status_code == 404

    def test_a_video_reference_selects_the_videos_profile(self, est, client):
        est.db.from_("cs_biblioteca_referencias").insert({"id": str(uuid.uuid4()), "org_id": ORG, "marca_id": MARCA, "modo": "video", "viral_id": V_P2}).execute()
        items = {i["id"]: i for i in _items(client.get(f"{BASE}?marca_id={MARCA}"))}
        assert items[E2]["selecionada_pela_marca"] is True

    def test_a_missing_photo_never_fails_the_admin_page_and_a_member_has_none_to_miss(self, est, client):
        est.db.from_("cs_perfis_monitorados").update({"foto_path": None}).eq("id", P1).execute()
        assert "foto_url" not in next(i for i in _items(client.get(BASE)) if i["id"] == E1)["perfil"]
        est.admin = True
        assert next(i for i in _items(client.get(BASE)) if i["id"] == E1)["perfil"]["foto_url"] is None

    def test_an_admin_still_gets_the_signed_photo_and_the_review_flag_a_member_never_does(self, est, client):
        item = next(i for i in _items(client.get(BASE)) if i["id"] == E1)
        assert "revisao_por_desuso" not in item
        est.admin = True
        item = next(i for i in _items(client.get(BASE)) if i["id"] == E1)
        assert item["perfil"]["foto_url"].startswith(f"fake://storage/sw-biblioteca/platform/{P1}/foto.jpg")
        assert "revisao_por_desuso" in item

    def test_the_unused_review_filter_is_admin_only_and_lists_the_flagged(self, est, client):
        est.db.from_("cs_estruturas_resumo").update({"revisao_desuso_em": "2026-11-15T00:00:00+00:00"}).eq("id", E2).execute()
        assert {i["id"] for i in _items(client.get(f"{BASE}?revisao=pendente"))} == {E1, E2}  # ignored for a member
        est.admin = True
        assert [i["id"] for i in _items(client.get(f"{BASE}?revisao=pendente"))] == [E2]
        assert client.get(f"{BASE}?revisao=outra").status_code == 422


class _Spy:
    """A chainable PostgREST query double that RECORDS every call (the mock evaluates some ops as match-all)."""

    def __init__(self, calls):
        self.calls = calls

    @property
    def not_(self):
        self.calls.append(("not_", (), {}))
        return self

    def __getattr__(self, name):
        def _record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self
        return _record

    def execute(self):
        class R:
            data, count = [], 0
        return R()


class _SpyDB:
    def __init__(self):
        self.calls: list = []

    def table(self, name):
        self.calls.append(("table", (name,), {}))
        return _Spy(self.calls)


class TestPredicates:
    """The PostgREST filters the list builds (`overlaps` / `text_search` / `gt` have no evaluator in the mock)."""

    def _calls(self, **kw):
        db = _SpyDB()
        args = dict(marca_id=None, perfil_id=None, q=None, formatos=[], objetivos=[], status=None,
                    somente_pendentes_revisao=False, limit=20, offset=0)
        args.update(kw)
        svc.EstruturasService(db, org_id=ORG, user_id="u", is_admin=kw.pop("admin", False)).listar(**{k: v for k, v in args.items() if k != "admin"})
        return db.calls

    def test_objetivo_is_an_overlap_formato_an_in_and_q_a_portuguese_websearch(self):
        calls = self._calls(objetivos=["venda", "autoridade"], formatos=["reels", "post"], q="  prova social ")
        assert ("table", (svc.RESUMO,), {}) in calls
        assert ("overlaps", ("objetivos", ["venda", "autoridade"]), {}) in calls
        assert ("in_", ("formato", ["reels", "post"]), {}) in calls
        assert ("text_search", ("busca", "prova social"), {"options": {"config": "portuguese", "type": "websearch"}}) in calls
        assert ("eq", ("status", "ativa"), {}) in calls
        assert ("range", (0, 19), {}) in calls

    def test_pending_filter_and_status_are_admin_only(self):
        member = self._calls(somente_pendentes_revisao=True, status="todas")
        assert not any(c[0] == "gt" for c in member) and ("eq", ("status", "ativa"), {}) in member
        admin = [c for c in self._admin_calls(somente_pendentes_revisao=True, status="todas")]
        assert ("gt", ("campos_pendentes", 0), {}) in admin and not any(c[0] == "eq" and c[1][0] == "status" for c in admin)

    def test_the_unused_review_filter_is_a_not_null_on_the_flag_and_admin_only(self):
        admin = self._admin_calls(revisao="pendente")
        assert admin.index(("not_", (), {})) + 1 == admin.index(("is_", ("revisao_desuso_em", "null"), {}))
        member = self._calls(revisao="pendente")
        assert not any(c[0] == "is_" for c in member)

    def _admin_calls(self, **kw):
        db = _SpyDB()
        args = dict(marca_id=None, perfil_id=None, q=None, formatos=[], objetivos=[], status=None,
                    somente_pendentes_revisao=False, limit=20, offset=0)
        args.update(kw)
        svc.EstruturasService(db, org_id=ORG, user_id="u", is_admin=True).listar(**args)
        return db.calls

    def test_the_list_orders_newest_first_with_a_stable_tiebreak(self):
        calls = self._calls()
        orders = [c for c in calls if c[0] == "order"]
        assert [(c[1][0], c[2]) for c in orders] == [("updated_at", {"desc": True}), ("codigo", {"desc": True})]


class TestDetail:
    def test_member_detail_shape_blocks_and_no_admin_field(self, est, client):
        r = client.get(f"{BASE}/{E1}")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["versao"] == 1 and d["blocos_total"] == 2 and d["codigo"] == 101
        assert [b["ordem"] for b in d["blocos"]] == [1, 2]
        assert d["blocos"][0] == {
            "id": B1, "ordem": 1, "nome": "Abertura", "tipo": {"id": T_HEAD, "nome": "Headline"}, "tempo": "0–3s",
            "instrucao": "Fale a promessa", "nota": "sobre o vídeo original", "repeticoes": 1,
        }
        assert d["blocos"][1]["repeticoes"] == 2 and d["blocos"][1]["nota"] is None

    def test_a_draft_or_archived_Estrutura_is_404_to_a_member_never_403(self, est, client):
        assert client.get(f"{BASE}/{E_DRAFT}").status_code == 404
        assert client.get(f"{BASE}/{E_ARCH}").status_code == 404
        assert client.get(f"{BASE}/{uuid.uuid4()}").status_code == 404
        assert client.get(f"{BASE}/nao-e-uuid").status_code == 422

    def test_admin_sees_drafts_and_the_provenance(self, est, client):
        est.admin = True
        d = client.get(f"{BASE}/{E_DRAFT}").json()["data"]
        assert d["status"] == "rascunho" and d["origem"] == "viral_auto" and d["pendente_revisao"] is True
        assert d["proveniencia"] == {"formula_headline": "ia_sugerido", "formato": "admin", "objetivos": "admin"}
        full = client.get(f"{BASE}/{E1}").json()["data"]
        assert full["ref_externa"] == "101" and full["referencia_rotulo"] == "ref-2026" and full["formula_herdada_de"] == "9"
        assert full["proveniencia"]["formato"] == "referencia"
        assert full["blocos"][0]["proveniencia"] == {"nome": "fonte", "tipo": "referencia", "tempo": "admin", "instrucao": "admin"}

    def test_a_non_admin_response_never_carries_an_admin_field(self, est, client):
        """Serialise EVERY non-admin response and grep it for the admin-only keys (contract section 12.1)."""
        blobs = [
            client.get(BASE).text, client.get(f"{BASE}?marca_id={MARCA}").text, client.get(f"{BASE}/{E1}").text,
            client.get(f"{BASE}/{E2}").text, client.get(f"{BASE}/tipos-bloco").text, client.get(f"{BASE}/admin").text,
        ]
        for blob in blobs:
            keys = _all_keys(json.loads(blob))
            assert not (keys & ADMIN_FORBIDDEN), keys & ADMIN_FORBIDDEN
        joined = "".join(blobs)
        assert '"ia_sugerido"' not in joined and '"referencia"' not in joined and '"fonte"' not in joined
        # positive control: the same Estrutura DOES carry them for an admin (the grep is not vacuous)
        est.admin = True
        assert _all_keys(client.get(f"{BASE}/{E1}").json()) & ADMIN_FORBIDDEN


def _all_keys(node) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in _all_keys(v)}
    if isinstance(node, list):
        return {k for v in node for k in _all_keys(v)}
    return set()


class TestTiposBloco:
    def test_member_gets_active_types_in_the_contract_shape(self, est, client):
        d = client.get(f"{BASE}/tipos-bloco").json()["data"]
        assert [t["nome"] for t in d] == ["Headline", "Revelação", "Outro"]
        assert set(d[0]) == {"id", "nome", "ordem", "tempo_tipico", "instrucao_referencia", "ativo"}

    def test_admin_also_gets_inactive_types_with_versao_and_sistema(self, est, client):
        est.admin = True
        d = client.get(f"{BASE}/tipos-bloco").json()["data"]
        assert [t["nome"] for t in d] == ["Headline", "Revelação", "CTA Curtir", "Outro"]
        assert d[2]["ativo"] is False and d[0]["versao"] == 3 and d[3]["sistema"] is True and d[0]["sistema"] is False

    def test_the_static_path_is_not_swallowed_by_the_id_route(self, est, client):
        assert client.get(f"{BASE}/tipos-bloco").status_code == 200
        assert client.get(f"{BASE}/admin").status_code == 200


# ── admin writes ──────────────────────────────────────────────────────────────────────────────────────────

NEW_BODY = {
    "perfil_id": P1, "formula_headline": "  Como [x] faz y  ", "formato": "reels", "objetivos": ["alcance", "venda"],
    "blocos": [{"nome": "Abertura", "tipo_id": T_HEAD, "tempo": "0–3s", "repeticoes": 2}, {"nome": "Virada", "tipo_id": T_REV}],
}


@pytest.fixture
def adm(est):
    est.admin = True
    return est


class TestCriar:
    def test_creates_through_the_rpc_and_returns_the_fresh_detail_with_admin_fields(self, adm, client):
        adm.rpc.results["cs_estrutura_criar"] = {"id": E1, "codigo": 101, "versao": 1}
        r = client.post(BASE, json=NEW_BODY)
        assert r.status_code == 201, r.text
        assert r.json()["data"]["id"] == E1 and "proveniencia" in r.json()["data"]
        p = adm.rpc.last("cs_estrutura_criar")["p"]
        assert p["perfil_id"] == P1 and p["formula_headline"] == "Como [x] faz y" and p["origem"] == "manual"
        assert p["ator_tipo"] == "admin" and p["status"] == "ativa" and p["viral_id"] is None and p["objetivos"] == ["alcance", "venda"]
        assert [b["tipo_id"] for b in p["blocos"]] == [T_HEAD, T_REV] and p["blocos"][0]["repeticoes"] == 2
        assert set(adm.rpc.last("cs_estrutura_criar")) == {"p"}

    def test_unknown_perfil_viral_and_tipo_are_404(self, adm, client):
        assert client.post(BASE, json={**NEW_BODY, "perfil_id": str(uuid.uuid4())}).status_code == 404
        assert client.post(BASE, json={**NEW_BODY, "viral_id": str(uuid.uuid4())}).status_code == 404
        assert client.post(BASE, json={**NEW_BODY, "blocos": [{"nome": "x", "tipo_id": str(uuid.uuid4())}]}).status_code == 404
        assert adm.rpc.calls == []

    def test_a_video_of_another_perfil_is_422(self, adm, client):
        r = client.post(BASE, json={**NEW_BODY, "viral_id": V_P2})
        assert r.status_code == 422, r.text

    def test_an_opted_out_creator_is_409(self, adm, client):
        adm.db.from_("cs_biblioteca_optouts").insert({"id": str(uuid.uuid4()), "handle": "psifernandosegredo", "origem": "admin"}).execute()
        r = client.post(BASE, json=NEW_BODY)
        assert r.status_code == 409 and r.json()["code"] == "perfil_optout"
        assert adm.rpc.calls == []

    @pytest.mark.parametrize("patch", [
        {"formato": "video"}, {"objetivos": []}, {"objetivos": ["alcance", "alcance"]}, {"objetivos": ["fama"]},
        {"blocos": []}, {"formula_headline": "   "}, {"formula_headline": "x" * 1001}, {"status": "arquivada"},
        {"bogus": 1}, {"blocos": [{"nome": "x", "tipo_id": T_HEAD, "repeticoes": 21}]},
        {"blocos": [{"nome": "x", "tipo_id": T_HEAD, "origem": "admin"}]},
        {"blocos": [{"nome": "x" * 121, "tipo_id": T_HEAD}]}, {"blocos": [{"nome": "x", "tipo_id": "nao-uuid"}]},
    ])
    def test_a_malformed_body_is_422_and_writes_nothing(self, adm, client, patch):
        assert client.post(BASE, json={**NEW_BODY, **patch}).status_code == 422
        assert adm.rpc.calls == []

    def test_more_than_60_blocks_is_422(self, adm, client):
        assert client.post(BASE, json={**NEW_BODY, "blocos": [{"nome": f"b{i}", "tipo_id": T_HEAD} for i in range(61)]}).status_code == 422

    def test_an_rpc_incompleteness_is_422_with_the_missing_list(self, adm, client):
        adm.rpc.errors["cs_estrutura_criar"] = FakeApiError("estrutura_incompleta", "formato,objetivos")
        r = client.post(BASE, json={**NEW_BODY, "status": "rascunho"})
        assert r.status_code == 422 and r.json()["code"] == "estrutura_incompleta"
        assert r.json()["faltando"] == ["formato", "objetivos"]


class TestAtualizar:
    def test_patch_sends_only_the_given_fields_with_the_version_and_the_actor(self, adm, client):
        adm.rpc.results["cs_estrutura_atualizar"] = {"id": E1, "versao": 2}
        r = client.patch(f"{BASE}/{E1}", json={"expected_versao": 1, "formato": "post", "viral_id": None})
        assert r.status_code == 200, r.text
        c = adm.rpc.last("cs_estrutura_atualizar")
        assert c["p_id"] == E1 and c["p_expected_versao"] == 1 and c["p_patch"] == {"formato": "post", "viral_id": None}
        assert c["p_ator"]

    @pytest.mark.parametrize("body", [
        {"expected_versao": 1}, {"formato": "post"}, {"expected_versao": 0, "formato": "post"},
        {"expected_versao": 1, "status": "arquivada"}, {"expected_versao": 1, "formato": None},
        {"expected_versao": 1, "formula_headline": None}, {"expected_versao": 1, "objetivos": None},
        {"expected_versao": 1, "objetivos": []}, {"expected_versao": 1, "bogus": 1},
    ])
    def test_status_never_changes_here_and_a_patch_needs_a_field_and_a_version(self, adm, client, body):
        assert client.patch(f"{BASE}/{E1}", json=body).status_code == 422
        assert adm.rpc.calls == []

    @pytest.mark.parametrize("code,status,extra_code", [
        ("versao_desatualizada", 409, "versao_desatualizada"), ("estrutura_inativa", 409, "estrutura_inativa"),
        ("estrutura_incompleta", 422, "estrutura_incompleta"), ("formula_invalida", 422, "formula_invalida"),
    ])
    def test_rpc_refusals_map_to_their_status(self, adm, client, code, status, extra_code):
        adm.rpc.errors["cs_estrutura_atualizar"] = FakeApiError(code)
        r = client.patch(f"{BASE}/{E1}", json={"expected_versao": 1, "formato": "post"})
        assert r.status_code == status and r.json()["code"] == extra_code

    def test_an_unknown_estrutura_is_404(self, adm, client):
        adm.rpc.errors["cs_estrutura_atualizar"] = FakeApiError("estrutura_nao_encontrada")
        assert client.patch(f"{BASE}/{E1}", json={"expected_versao": 1, "formato": "post"}).status_code == 404

    def test_an_unclassified_rpc_failure_is_never_swallowed(self, adm, client):
        adm.rpc.errors["cs_estrutura_atualizar"] = RuntimeError("connection reset")
        with pytest.raises(RuntimeError):
            client.patch(f"{BASE}/{E1}", json={"expected_versao": 1, "formato": "post"})


class TestBlocos:
    BODY = {"expected_versao": 1, "blocos": [{"id": B2, "nome": "Virada", "tipo_id": T_REV}, {"nome": "Novo", "tipo_id": T_OUTRO, "nota": "obs"}]}

    def test_full_replace_goes_through_the_rpc_in_order_with_ids(self, adm, client):
        adm.rpc.results["cs_estrutura_substituir_blocos"] = {"id": E1, "versao": 2}
        r = client.put(f"{BASE}/{E1}/blocos", json=self.BODY)
        assert r.status_code == 200, r.text
        c = adm.rpc.last("cs_estrutura_substituir_blocos")
        assert c["p_expected_versao"] == 1 and [b.get("id") for b in c["p_blocos"]] == [B2, None]
        assert c["p_blocos"][1]["nota"] == "obs" and c["p_blocos"][0]["repeticoes"] == 1

    def test_an_unknown_tipo_in_the_body_is_422_not_404(self, adm, client):
        r = client.put(f"{BASE}/{E1}/blocos", json={"expected_versao": 1, "blocos": [{"nome": "x", "tipo_id": str(uuid.uuid4())}]})
        assert r.status_code == 422 and adm.rpc.calls == []

    @pytest.mark.parametrize("code,status", [("bloco_nao_encontrado", 422), ("tipo_nao_encontrado", 422), ("blocos_invalidos", 422),
                                             ("versao_desatualizada", 409), ("estrutura_inativa", 409)])
    def test_rpc_refusals(self, adm, client, code, status):
        adm.rpc.errors["cs_estrutura_substituir_blocos"] = FakeApiError(code)
        assert client.put(f"{BASE}/{E1}/blocos", json=self.BODY).status_code == status

    @pytest.mark.parametrize("body", [{"expected_versao": 1, "blocos": []}, {"blocos": [{"nome": "a", "tipo_id": T_HEAD}]},
                                      {"expected_versao": 1, "blocos": [{"nome": "a", "tipo_id": T_HEAD}], "x": 1}])
    def test_malformed_is_422(self, adm, client, body):
        assert client.put(f"{BASE}/{E1}/blocos", json=body).status_code == 422


class TestConfirmarPublicarArquivar:
    def test_confirmar_campos_and_todos(self, adm, client):
        adm.rpc.results["cs_estrutura_confirmar"] = {"id": E1, "versao": 2, "confirmados": 1}
        campos = ["formato", f"bloco.{B1}.tipo"]
        assert client.post(f"{BASE}/{E1}/confirmar", json={"expected_versao": 1, "campos": campos}).status_code == 200
        c = adm.rpc.last("cs_estrutura_confirmar")
        assert c["p_campos"] == campos and c["p_expected_versao"] == 1
        assert client.post(f"{BASE}/{E1}/confirmar", json={"expected_versao": 1, "todos": True}).status_code == 200
        assert adm.rpc.last("cs_estrutura_confirmar")["p_campos"] == ["*"]

    @pytest.mark.parametrize("body", [
        {"expected_versao": 1}, {"expected_versao": 1, "campos": ["formato"], "todos": True}, {"expected_versao": 1, "todos": False},
        {"expected_versao": 1, "campos": []}, {"expected_versao": 1, "campos": ["status"]},
        {"expected_versao": 1, "campos": ["bloco.nao-uuid.tipo"]}, {"expected_versao": 1, "campos": [f"bloco.{B1}.nota"]},
        {"expected_versao": 1, "campos": [f"bloco.{B1}.repeticoes"]},
    ])
    def test_exactly_one_of_campos_or_todos_and_a_known_field(self, adm, client, body):
        assert client.post(f"{BASE}/{E1}/confirmar", json=body).status_code == 422
        assert adm.rpc.calls == []

    def test_unknown_field_from_the_rpc_is_422(self, adm, client):
        adm.rpc.errors["cs_estrutura_confirmar"] = FakeApiError("campo_desconhecido")
        r = client.post(f"{BASE}/{E1}/confirmar", json={"expected_versao": 1, "campos": [f"bloco.{uuid.uuid4()}.tipo"]})
        assert r.status_code == 422 and r.json()["code"] == "campo_desconhecido"

    def test_publicar_incomplete_draft_is_422_with_the_missing_items(self, adm, client):
        adm.db.from_("cs_estruturas").update({"formula_origem": "admin"}).eq("id", E_DRAFT).execute()  # reviewed: the AI-draft gate passes
        adm.rpc.errors["cs_estrutura_publicar"] = FakeApiError("rascunho_incompleto", "formato,blocos")
        r = client.post(f"{BASE}/{E_DRAFT}/publicar", json={"expected_versao": 1})
        assert r.status_code == 422
        assert r.json() == {"code": "rascunho_incompleto", "detail": "Para publicar, informe formato, ao menos um objetivo e ao menos um bloco.",
                                      "faltando": ["formato", "blocos"]}

    def test_publicar_ok_and_inactive(self, adm, client):
        adm.db.from_("cs_estruturas").update({"formula_origem": "admin"}).eq("id", E_DRAFT).execute()  # reviewed: the AI-draft gate passes
        adm.rpc.results["cs_estrutura_publicar"] = {"id": E_DRAFT, "versao": 2}
        assert client.post(f"{BASE}/{E_DRAFT}/publicar", json={"expected_versao": 1}).status_code == 200
        c = adm.rpc.last("cs_estrutura_publicar")
        assert c["p_id"] == E_DRAFT and c["p_expected_versao"] == 1 and c["p_ator"]
        adm.rpc.errors["cs_estrutura_publicar"] = FakeApiError("estrutura_inativa")
        assert client.post(f"{BASE}/{E1}/publicar", json={"expected_versao": 1}).status_code == 409

    def test_arquivar_and_restaurar_return_the_fresh_detail(self, adm, client):
        assert client.post(f"{BASE}/{E1}/arquivar").json()["data"]["id"] == E1
        assert adm.rpc.last("cs_estrutura_arquivar") == {"p_id": E1, "p_ator": adm.rpc.last("cs_estrutura_arquivar")["p_ator"]}
        assert client.post(f"{BASE}/{E_ARCH}/restaurar").status_code == 200
        assert adm.rpc.last("cs_estrutura_restaurar")["p_id"] == E_ARCH

    def test_delete_is_204_and_a_used_estrutura_is_409(self, adm, client):
        r = client.delete(f"{BASE}/{E1}")
        assert r.status_code == 204 and r.content == b""
        adm.rpc.errors["cs_estrutura_excluir"] = FakeApiError("estrutura_em_uso")
        r = client.delete(f"{BASE}/{E1}")
        assert r.status_code == 409 and r.json()["code"] == "estrutura_em_uso"


class TestTiposAdmin:
    def test_create_update_delete_go_through_the_rpcs(self, adm, client):
        adm.rpc.results["cs_estrutura_tipo_salvar"] = {"id": T_HEAD, "versao": 4}
        r = client.post(f"{BASE}/tipos-bloco", json={"nome": " Novo ", "instrucao_referencia": "faça", "ordem": 2})
        assert r.status_code == 201 and r.json()["data"]["id"] == T_HEAD and r.json()["data"]["versao"] == 3
        p = adm.rpc.last("cs_estrutura_tipo_salvar")["p"]
        assert p["nome"] == "Novo" and p["instrucao_referencia"] == "faça" and p["ordem"] == 2 and p["ativo"] is True and "id" not in p
        r = client.put(f"{BASE}/tipos-bloco/{T_HEAD}", json={"expected_versao": 3, "ativo": False, "tempo_tipico": None})
        assert r.status_code == 200, r.text
        p = adm.rpc.last("cs_estrutura_tipo_salvar")["p"]
        assert p["id"] == T_HEAD and p["expected_versao"] == 3 and p["ativo"] is False and p["tempo_tipico"] is None and "nome" not in p
        assert client.delete(f"{BASE}/tipos-bloco/{T_OFF}").status_code == 204
        assert adm.rpc.last("cs_estrutura_tipo_excluir")["p_id"] == T_OFF

    @pytest.mark.parametrize("code,status,body_code", [
        ("tipo_em_uso", 409, "tipo_em_uso"), ("tipo_protegido", 409, "tipo_protegido"), ("versao_desatualizada", 409, "versao_desatualizada"),
    ])
    def test_refusals(self, adm, client, code, status, body_code):
        adm.rpc.errors["cs_estrutura_tipo_excluir"] = FakeApiError(code)
        adm.rpc.errors["cs_estrutura_tipo_salvar"] = FakeApiError(code)
        r = client.delete(f"{BASE}/tipos-bloco/{T_OFF}")
        assert r.status_code == status and r.json()["code"] == body_code
        r = client.put(f"{BASE}/tipos-bloco/{T_OFF}", json={"expected_versao": 1, "ativo": False})
        assert r.status_code == status and r.json()["code"] == body_code

    def test_a_duplicate_name_is_422(self, adm, client):
        adm.rpc.errors["cs_estrutura_tipo_salvar"] = FakeApiError(
            "duplicate key value violates unique constraint \"cs_estrutura_tipos_bloco_nome_uq\"", code="23505")
        r = client.post(f"{BASE}/tipos-bloco", json={"nome": "Headline", "instrucao_referencia": "x"})
        assert r.status_code == 422 and r.json()["code"] == "tipo_nome_duplicado"

    @pytest.mark.parametrize("method,path,body", [
        ("post", "/tipos-bloco", {"nome": "", "instrucao_referencia": "x"}),
        ("post", "/tipos-bloco", {"nome": "x" * 81, "instrucao_referencia": "x"}),
        ("post", "/tipos-bloco", {"nome": "x", "instrucao_referencia": "x" * 601}),
        ("post", "/tipos-bloco", {"nome": "x", "instrucao_referencia": "x", "sistema": True}),
        ("put", f"/tipos-bloco/{T_HEAD}", {"ativo": False}),
        ("put", f"/tipos-bloco/{T_HEAD}", {"expected_versao": 1}),
        ("put", f"/tipos-bloco/{T_HEAD}", {"expected_versao": 1, "nome": None}),
        ("put", f"/tipos-bloco/{T_HEAD}", {"expected_versao": 1, "nome": "   "}),
    ])
    def test_malformed_is_422(self, adm, client, method, path, body):
        assert getattr(client, method)(BASE + path, json=body).status_code == 422
        assert adm.rpc.calls == []


# ── pure helpers ──────────────────────────────────────────────────────────────────────────────────────────


class TestPure:
    def test_formula_trecho_is_at_most_120_chars_cut_at_a_word(self):
        assert svc.formula_trecho("curta") == "curta"
        long = ("palavra " * 40).strip()
        t = svc.formula_trecho(long)
        assert len(t) <= 120 and t.endswith("…") and not t[:-1].endswith(" ") and t[:-1].split(" ")[-1] == "palavra"

    def test_mapear_erro_rpc_reads_message_details_and_code(self):
        e = svc.mapear_erro_rpc(FakeApiError("versao_desatualizada"))
        assert e.status == 409 and e.detail["code"] == "versao_desatualizada"
        e = svc.mapear_erro_rpc(FakeApiError("rascunho_incompleto", "formato,objetivos,blocos"))
        assert e.detail["faltando"] == ["formato", "objetivos", "blocos"]
        assert svc.mapear_erro_rpc(FakeApiError("tipo_nao_encontrado")).status == 404
        assert svc.mapear_erro_rpc(FakeApiError("tipo_nao_encontrado"), corpo=True).status == 422
        assert svc.mapear_erro_rpc(FakeApiError("algo_novo")) is None
        assert svc.mapear_erro_rpc(ValueError("x")) is None

    def test_every_error_code_of_the_migration_is_mapped(self):
        import re
        from pathlib import Path

        from noctusai_lib.testing.migrations import migration_path

        sql = migration_path(Path(__file__).resolve().parents[3], "cs_estruturas").read_text(encoding="utf-8")
        raised = set(re.findall(r"RAISE EXCEPTION '([a-z_]+)'", sql))
        raised -= {"blocos_invalidos"} | set()  # mapped below
        mapped = set(svc._RPC_ERROS) | set(svc._RPC_NAO_ENCONTRADO) | {"blocos_invalidos"}
        # strings that are not codes (messages carrying a prefix / format) never match [a-z_]+ exactly
        assert raised <= mapped, raised - mapped
