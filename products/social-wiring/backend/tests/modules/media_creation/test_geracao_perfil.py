"""Geração BE-1 — Meu Perfil, taxonomias, Treinamentos and Dashboard
(geracao-contract.md §4.1, §4.2, §4.7, §8).

Mounted through the real ``register()`` seam on the MockSupabaseClient; the platform-admin
check is the production DI seam (``get_platform_admin_check``) overridden, never patched.
"""
import uuid

import pytest

from app.dependencies import get_platform_admin_check
from app.modules.media_creation.geracao_taxonomias import (
    FORMATOS_VIDEO, GATILHOS, NICHOS, PROFISSOES, TONS,
)

BASE = "/api/media-creation"
ORG = "test-org-123"
MARCA = str(uuid.uuid4())
OTHER_MARCA = str(uuid.uuid4())  # another org's


@pytest.fixture
def gc(client):
    sb = client.mock_supabase
    sb.from_("marcas").insert({"id": MARCA, "org_id": ORG, "name": "Marca A"}).execute()
    sb.from_("marcas").insert({"id": OTHER_MARCA, "org_id": "other-org", "name": "Marca B"}).execute()
    client.admin = False
    client._tc.app.dependency_overrides[get_platform_admin_check] = lambda: (lambda _uid: client.admin)
    return client


def _rows(c, table):
    return c.mock_supabase.from_(table).select("*").execute().data


# ── taxonomias ───────────────────────────────────────────────────────────


class TestTaxonomias:
    def test_shape_and_counts(self, gc):
        r = gc.get(f"{BASE}/taxonomias")
        assert r.status_code == 200
        d = r.json()["data"]
        assert len(d["nichos"]) == len(NICHOS) == 28
        assert len(d["profissoes"]) == len(PROFISSOES) == 102
        assert len(d["formatos"]) == len(FORMATOS_VIDEO) == 15
        assert [g["slug"] for g in d["gatilhos"]] == [s for s, _ in GATILHOS]
        assert all(g["formula"] and "[" in g["formula"] for g in d["gatilhos"])
        assert [t["id"] for t in d["tons"]] == list(range(10, 10 + len(TONS)))
        assert all(isinstance(t["slug"], str) for t in d["tons"])
        assert {"id", "nome", "definicao"} <= set(d["formatos"][0])

    def test_profissoes_sorted_alphabetically(self, gc):
        nomes = [p["nome"] for p in gc.get(f"{BASE}/taxonomias").json()["data"]["profissoes"]]
        assert nomes == sorted(nomes, key=str.casefold)


# ── perfil ───────────────────────────────────────────────────────────────


class TestPerfil:
    def test_empty_defaults_without_row(self, gc):
        d = gc.get(f"{BASE}/perfil", params={"marca_id": MARCA}).json()["data"]
        assert d == {
            "marca_id": MARCA, "bio": "", "nichos": [], "profissoes": [],
            "apresentacao_magnetica": "", "ctas": "", "updated_at": None,
        }

    def test_put_creates_then_patches(self, gc):
        r = gc.put(f"{BASE}/perfil", json={"marca_id": MARCA, "bio": "minha bio", "nichos": [1, 2]})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["bio"] == "minha bio" and d["nichos"] == [1, 2] and d["updated_at"]
        # PATCH semantics: untouched fields survive
        r = gc.put(f"{BASE}/perfil", json={"marca_id": MARCA, "ctas": "assine"})
        d = r.json()["data"]
        assert d["bio"] == "minha bio" and d["nichos"] == [1, 2] and d["ctas"] == "assine"
        assert len(_rows(gc, "cs_marca_perfil")) == 1

    def test_all_fields_round_trip(self, gc):
        prof = PROFISSOES[0][0]
        gc.put(f"{BASE}/perfil", json={
            "marca_id": MARCA, "bio": "b", "nichos": [3], "profissoes": [prof],
            "apresentacao_magnetica": "ap", "ctas": "cta",
        })
        d = gc.get(f"{BASE}/perfil", params={"marca_id": MARCA}).json()["data"]
        assert (d["nichos"], d["profissoes"], d["apresentacao_magnetica"], d["ctas"]) == ([3], [prof], "ap", "cta")

    def test_more_than_three_nichos_is_422(self, gc):
        r = gc.put(f"{BASE}/perfil", json={"marca_id": MARCA, "nichos": [1, 2, 3, 4]})
        assert r.status_code == 422 and "Selecione até 3 nichos" in r.json()["error"]["message"]
        assert _rows(gc, "cs_marca_perfil") == []

    def test_more_than_three_profissoes_is_422(self, gc):
        ids = [p[0] for p in PROFISSOES[:4]]
        r = gc.put(f"{BASE}/perfil", json={"marca_id": MARCA, "profissoes": ids})
        assert r.status_code == 422 and "Selecione até 3 profissões" in r.json()["error"]["message"]

    def test_unknown_taxonomy_id_is_422(self, gc):
        assert gc.put(f"{BASE}/perfil", json={"marca_id": MARCA, "nichos": [10]}).status_code == 422
        assert gc.put(f"{BASE}/perfil", json={"marca_id": MARCA, "profissoes": [99999]}).status_code == 422

    def test_duplicate_ids_is_422(self, gc):
        assert gc.put(f"{BASE}/perfil", json={"marca_id": MARCA, "nichos": [1, 1]}).status_code == 422

    def test_unknown_field_is_422(self, gc):
        assert gc.put(f"{BASE}/perfil", json={"marca_id": MARCA, "bogus": 1}).status_code == 422

    def test_oversize_texts_are_422(self, gc):
        assert gc.put(f"{BASE}/perfil", json={"marca_id": MARCA, "bio": "x" * 5001}).status_code == 422
        assert gc.put(f"{BASE}/perfil", json={"marca_id": MARCA, "ctas": "x" * 3001}).status_code == 422

    def test_foreign_marca_is_404(self, gc):
        assert gc.get(f"{BASE}/perfil", params={"marca_id": OTHER_MARCA}).status_code == 404
        assert gc.put(f"{BASE}/perfil", json={"marca_id": OTHER_MARCA, "bio": "x"}).status_code == 404
        assert gc.get(f"{BASE}/perfil", params={"marca_id": str(uuid.uuid4())}).status_code == 404
        assert _rows(gc, "cs_marca_perfil") == []

    def test_cerebro_perfil_shares_the_same_bio(self, gc):
        r = gc.put(f"{BASE}/cerebro/perfil", json={"marca_id": MARCA, "bio": "via cérebro"})
        assert r.status_code == 200
        assert set(r.json()["data"]) == {"marca_id", "bio", "updated_at"}
        assert gc.get(f"{BASE}/perfil", params={"marca_id": MARCA}).json()["data"]["bio"] == "via cérebro"
        gc.put(f"{BASE}/perfil", json={"marca_id": MARCA, "bio": "via perfil", "nichos": [2]})
        d = gc.get(f"{BASE}/cerebro/perfil", params={"marca_id": MARCA}).json()["data"]
        assert d["bio"] == "via perfil"
        # the cérebro write must not wipe the Meu Perfil-only columns
        gc.put(f"{BASE}/cerebro/perfil", json={"marca_id": MARCA, "bio": "outra"})
        assert gc.get(f"{BASE}/perfil", params={"marca_id": MARCA}).json()["data"]["nichos"] == [2]
        assert len(_rows(gc, "cs_marca_perfil")) == 1


# ── treinamentos ─────────────────────────────────────────────────────────


def _seed_aula(c, ordem=1, titulo="Aula", ativo=True, video_url=None):
    tid = str(uuid.uuid4())
    c.mock_supabase.from_("cs_treinamentos").insert({
        "id": tid, "ordem": ordem, "titulo": titulo, "descricao": "d", "video_url": video_url, "ativo": ativo,
    }).execute()
    return tid


class TestTreinamentos:
    def test_list_active_ordered(self, gc):
        _seed_aula(gc, 2, "B")
        _seed_aula(gc, 1, "A")
        _seed_aula(gc, 3, "C", ativo=False)
        d = gc.get(f"{BASE}/treinamentos").json()["data"]
        assert [a["titulo"] for a in d] == ["A", "B"]
        assert set(d[0]) == {"id", "ordem", "titulo", "descricao", "video_url", "ativo"}

    def test_admin_flag_envelope(self, gc):
        r = gc.get(f"{BASE}/treinamentos/admin")
        assert r.status_code == 200 and r.json()["data"] == {"is_admin": False}
        gc.admin = True
        assert gc.get(f"{BASE}/treinamentos/admin").json()["data"] == {"is_admin": True}

    def test_non_admin_writes_are_403(self, gc):
        tid = _seed_aula(gc)
        assert gc.put(f"{BASE}/treinamentos/{tid}", json={"titulo": "x"}).status_code == 403
        assert gc.post(f"{BASE}/treinamentos", json={"titulo": "x"}).status_code == 403
        assert gc.delete(f"{BASE}/treinamentos/{tid}").status_code == 403
        assert _rows(gc, "cs_treinamentos")[0]["titulo"] == "Aula"

    def test_admin_updates(self, gc):
        gc.admin = True
        tid = _seed_aula(gc)
        r = gc.put(f"{BASE}/treinamentos/{tid}", json={
            "titulo": "Novo", "video_url": "https://player.vimeo.com/video/1", "ativo": True,
        })
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["titulo"] == "Novo" and d["video_url"] == "https://player.vimeo.com/video/1"

    def test_explicit_null_clears_video(self, gc):
        gc.admin = True
        tid = _seed_aula(gc, video_url="https://player.vimeo.com/video/1")
        r = gc.put(f"{BASE}/treinamentos/{tid}", json={"video_url": None})
        assert r.status_code == 200 and r.json()["data"]["video_url"] is None

    def test_null_on_required_field_is_422(self, gc):
        gc.admin = True
        tid = _seed_aula(gc)
        assert gc.put(f"{BASE}/treinamentos/{tid}", json={"titulo": None}).status_code == 422

    @pytest.mark.parametrize("url", [
        "https://evil.example.com/v.mp4",
        "http://player.vimeo.com/video/1",
        "https://player.vimeo.com.evil.com/x",
        "javascript:alert(1)",
        "//player.vimeo.com/x",
    ])
    def test_video_host_outside_allow_list_is_422(self, gc, url):
        gc.admin = True
        tid = _seed_aula(gc)
        assert gc.put(f"{BASE}/treinamentos/{tid}", json={"video_url": url}).status_code == 422
        assert gc.post(f"{BASE}/treinamentos", json={"titulo": "x", "video_url": url}).status_code == 422
        assert _rows(gc, "cs_treinamentos")[0]["video_url"] is None

    @pytest.mark.parametrize("host", [
        "iframe.mediadelivery.net", "player.vimeo.com", "www.youtube.com", "www.youtube-nocookie.com",
    ])
    def test_allowed_hosts(self, gc, host):
        gc.admin = True
        tid = _seed_aula(gc)
        assert gc.put(f"{BASE}/treinamentos/{tid}", json={"video_url": f"https://{host}/embed/1"}).status_code == 200

    def test_create_appends_order_and_201(self, gc):
        gc.admin = True
        _seed_aula(gc, 5)
        r = gc.post(f"{BASE}/treinamentos", json={"titulo": "  Nova  "})
        assert r.status_code == 201
        d = r.json()["data"]
        assert d["ordem"] == 6 and d["titulo"] == "Nova" and d["ativo"] is True

    def test_delete_204_then_404(self, gc):
        gc.admin = True
        tid = _seed_aula(gc)
        assert gc.delete(f"{BASE}/treinamentos/{tid}").status_code == 204
        assert gc.delete(f"{BASE}/treinamentos/{tid}").status_code == 404
        assert gc.put(f"{BASE}/treinamentos/{tid}", json={"titulo": "x"}).status_code == 404


# ── dashboard ────────────────────────────────────────────────────────────


def _ins(c, table, **row):
    c.mock_supabase.from_(table).insert(row).execute()


@pytest.fixture
def dash(gc):
    c = gc
    for i, ts in enumerate(("2026-10-01T10:00:00+00:00", "2026-10-03T10:00:00+00:00")):
        _ins(c, "cs_headline_lotes", id=str(uuid.uuid4()), org_id=ORG, marca_id=MARCA,
             origem="form_me", created_at=ts)
    _ins(c, "cs_headline_lotes", id=str(uuid.uuid4()), org_id=ORG, marca_id=OTHER_MARCA,
         origem="form_me", created_at="2026-10-09T10:00:00+00:00")
    for i in range(3):
        _ins(c, "cs_headlines", id=str(uuid.uuid4()), org_id=ORG, marca_id=MARCA, texto=f"h{i}",
             modo="manual", created_at="2026-10-01T10:00:00+00:00")
    _ins(c, "cs_headlines", id=str(uuid.uuid4()), org_id="other-org", marca_id=OTHER_MARCA, texto="x",
         modo="manual", created_at="2026-10-01T10:00:00+00:00")
    _ins(c, "cs_roteiros", id=str(uuid.uuid4()), org_id=ORG, marca_id=MARCA, nome="R1", status="completo",
         finished_at="2026-10-02T10:00:00+00:00", created_at="2026-10-02T09:00:00+00:00")
    _ins(c, "cs_roteiros", id=str(uuid.uuid4()), org_id=ORG, marca_id=MARCA, nome="R2", status="falha",
         finished_at=None, created_at="2026-10-02T09:00:00+00:00")
    _ins(c, "cs_brains", id=str(uuid.uuid4()), org_id=ORG, marca_id=MARCA, name="Núcleo",
         synthesized_at="2026-10-04T10:00:00+00:00")
    _ins(c, "cs_brains", id=str(uuid.uuid4()), org_id=ORG, marca_id=MARCA, name="Nunca", synthesized_at=None)
    _ins(c, "cs_marca_perfil", marca_id=MARCA, org_id=ORG, bio="b", updated_at="2026-10-05T10:00:00+00:00")
    for st, ts in (("approved", "2026-10-06T08:00:00+00:00"), ("approved", "2026-10-06T09:00:00+00:00"),
                   ("pending", "2026-10-06T09:30:00+00:00"), ("pending", "2026-10-06T09:40:00+00:00"),
                   ("rejected", "2026-10-06T09:50:00+00:00")):
        _ins(c, "cs_research_items", id=str(uuid.uuid4()), org_id=ORG, marca_id=MARCA, status=st,
             updated_at=ts, created_at=ts)
    return c


class TestDashboard:
    def _get(self, c, **p):
        return c.get(f"{BASE}/dashboard", params={"marca_id": MARCA, **p})

    def test_kpis_scoped_to_marca(self, dash):
        k = self._get(dash).json()["data"]["kpis"]
        assert k == {"headlines_geradas": 3, "roteiros_gerados": 1, "itens_pendentes": 2}

    def test_historico_union_desc(self, dash):
        h = self._get(dash).json()["data"]["historico"]
        assert [e["tipo"] for e in h] == ["pesquisa", "perfil", "cerebro", "headline", "roteiro", "headline"]
        assert h[0]["texto"] == "Aprovou 2 itens de pesquisa"
        assert set(h[0]) == {"tipo", "texto", "ator", "em"}
        assert all(e["em"] for e in h)

    def test_historico_asc(self, dash):
        h = self._get(dash, historico_ordem="data_asc").json()["data"]["historico"]
        assert [e["em"] for e in h] == sorted(e["em"] for e in h)

    def test_historico_por_tipo(self, dash):
        h = self._get(dash, historico_ordem="tipo").json()["data"]["historico"]
        assert [e["tipo"] for e in h] == sorted(e["tipo"] for e in h)
        heads = [e["em"] for e in h if e["tipo"] == "headline"]
        assert heads == sorted(heads, reverse=True)

    def test_invalid_order_is_422(self, dash):
        assert self._get(dash, historico_ordem="bogus").status_code == 422

    def test_historico_capped_at_30(self, gc):
        for i in range(40):
            _ins(gc, "cs_headline_lotes", id=str(uuid.uuid4()), org_id=ORG, marca_id=MARCA,
                 origem="form_me", created_at=f"2026-09-{(i % 28) + 1:02d}T10:00:00+00:00")
        assert len(self._get(gc).json()["data"]["historico"]) <= 30

    def test_sugeridas_only_automatic_ranked_by_metric(self, gc):
        perfil = str(uuid.uuid4())
        _ins(gc, "cs_perfis_monitorados", id=perfil, org_id=ORG, handle="fulano")
        v_big, v_small = str(uuid.uuid4()), str(uuid.uuid4())
        for vid, views, caption in ((v_big, 3_000_000, "c" * 300), (v_small, 10, "curta")):
            _ins(gc, "cs_virais", id=vid, org_id=ORG, perfil_id=perfil, codigo=7, permalink="https://ig/p",
                 views=views, likes=1, comments=1, e_viral=True, caption=caption)
        def head(texto, modo, vid, ts):
            hid = str(uuid.uuid4())
            _ins(gc, "cs_headlines", id=hid, org_id=ORG, marca_id=MARCA, texto=texto, modo=modo,
                 viral_id=vid, created_at=ts, favorita=False)
            return hid
        head("manual", "manual", v_big, "2026-10-09T00:00:00+00:00")
        head("pequena", "automatico", v_small, "2026-10-09T00:00:00+00:00")
        h_big = head("grande", "automatico", v_big, "2026-10-01T00:00:00+00:00")
        head("sem viral", "automatico", None, "2026-10-10T00:00:00+00:00")
        _ins(gc, "cs_roteiros", id=str(uuid.uuid4()), org_id=ORG, marca_id=MARCA, nome="R", status="criando",
             headline_id=h_big, created_at="2026-10-02T00:00:00+00:00")
        s = self._get(gc).json()["data"]["sugeridas"]
        assert [x["texto"] for x in s] == ["grande", "pequena", "sem viral"]
        assert s[0]["viral"]["perfil"] == {"id": perfil, "handle": "fulano"}
        assert s[0]["viral"]["views"] == 3_000_000 and len(s[0]["viral"]["trecho"]) == 140
        assert s[0]["roteiro_id"] and s[1]["roteiro_id"] is None and s[2]["viral"] is None
        assert s[0]["marca_id"] == MARCA

    def test_sugeridas_capped_at_20(self, gc):
        for i in range(25):
            _ins(gc, "cs_headlines", id=str(uuid.uuid4()), org_id=ORG, marca_id=MARCA, texto=f"h{i}",
                 modo="automatico", created_at=f"2026-10-{(i % 9) + 1:02d}T00:00:00+00:00")
        assert len(self._get(gc).json()["data"]["sugeridas"]) == 20

    def test_empty_marca(self, gc):
        d = self._get(gc).json()["data"]
        assert d["kpis"] == {"headlines_geradas": 0, "roteiros_gerados": 0, "itens_pendentes": 0}
        assert d["historico"] == [] and d["sugeridas"] == []
        assert isinstance(d["saudacao_nome"], str)

    def test_foreign_marca_is_404(self, gc):
        assert gc.get(f"{BASE}/dashboard", params={"marca_id": OTHER_MARCA}).status_code == 404


# ── auth ─────────────────────────────────────────────────────────────────


class TestAuth:
    @pytest.mark.parametrize("method,path,kw", [
        ("get", "/taxonomias", {}),
        ("get", f"/perfil?marca_id={MARCA}", {}),
        ("put", "/perfil", {"json": {"marca_id": MARCA, "bio": "x"}}),
        ("get", "/treinamentos", {}),
        ("get", "/treinamentos/admin", {}),
        ("post", "/treinamentos", {"json": {"titulo": "x"}}),
        ("put", f"/treinamentos/{uuid.uuid4()}", {"json": {"titulo": "x"}}),
        ("delete", f"/treinamentos/{uuid.uuid4()}", {}),
        ("get", f"/dashboard?marca_id={MARCA}", {}),
    ])
    def test_unauthenticated_is_401(self, client, method, path, kw):
        r = getattr(client._tc, method)(BASE + path, **kw)
        assert r.status_code == 401, (path, r.status_code, r.text)
