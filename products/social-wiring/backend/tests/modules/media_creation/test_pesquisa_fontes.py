"""Pesquisa wave 2 — extraction sources (``pesquisa_fontes``).

Runs the real source classes (and the real ``IgInsightsRepository`` keyset
logic) against an in-memory PostgREST double that evaluates the filters the
sources depend on: ``eq`` / ``in_`` / ``not_.is_`` / keyset ``or_`` / ordering /
``range`` / exact counts. Test-only double; nothing of ours is patched.
"""
from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from app.modules.media_creation.pesquisa_fontes import (
    FONTES,
    MIN_TEXTO_CHARS,
    InstagramFonte,
    McPostFonte,
    YoutubeFonte,
)
from app.modules.media_creation.pesquisa_wave2_constants import FONTE_KINDS
from tests.modules.instagram.fakes import _compile, _norm

ORG, OTHER_ORG = "00000000-0000-4000-8000-0000000000a0", "00000000-0000-4000-8000-0000000000b0"
MARCA, OTHER_MARCA = "marca-a", "marca-b"
IG, IG_OTHER_MARCA, IG_OTHER_ORG = "ig-1", "ig-2", "ig-3"
YT = "yt-1"
KIT, KIT_OTHER = "kit-1", "kit-2"
LONG = "Um texto de legenda com mais de vinte caracteres."


class _Q:
    def __init__(self, store, table):
        self.store, self.table = store, table
        self.preds, self.orders, self.lim, self.rng = [], [], None, None
        self.want_count, self._neg = False, False

    def select(self, *_a, count=None, **_k):
        self.want_count = count == "exact"
        return self

    def eq(self, col, val):
        self.preds.append(lambda r: r.get(col) == val)
        return self

    def in_(self, col, vals):
        vals = list(vals)
        self.preds.append(lambda r: r.get(col) in vals)
        return self

    @property
    def not_(self):
        self._neg = True
        return self

    def is_(self, col, val):
        neg, self._neg = self._neg, False
        want_null = val == "null"
        self.preds.append(lambda r: (r.get(col) is None) == want_null if not neg else (r.get(col) is None) != want_null)
        return self

    def or_(self, expr):
        self.preds.append(_compile(expr))
        return self

    def order(self, col, desc=False, **_k):
        self.orders.append((col, desc))
        return self

    def limit(self, n):
        self.lim = n
        return self

    def range(self, a, b):
        self.rng = (a, b)
        return self

    def execute(self):
        rows = [r for r in self.store.tables.get(self.table, []) if all(p(r) for p in self.preds)]
        for col, desc in reversed(self.orders):
            rows.sort(key=lambda r: _norm(r.get(col)) if r.get(col) is not None else "", reverse=desc)
        total = len(rows)
        if self.rng:
            rows = rows[self.rng[0] : self.rng[1] + 1]
        if self.lim is not None:
            rows = rows[: self.lim]
        return SimpleNamespace(data=copy.deepcopy(rows), count=total if self.want_count else None)


class Db:
    def __init__(self):
        self.tables = {}

    def schema(self, _n):
        return self

    def table(self, name):
        return _Q(self, name)


def _uuid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


A_IG, A_IG_B, A_IG_C, A_YT = _uuid(1), _uuid(2), _uuid(3), _uuid(4)


def _acct(id_, org, marca, provider="instagram", status="validated", label="acme"):
    return {"id": id_, "org_id": org, "marca_id": marca, "provider": provider, "status": status,
            "account_label": label, "last_synced_at": "2026-10-08T00:00:00+00:00"}


def _media(mid, ts, account=A_IG, org=ORG, caption=LONG, views=None, **kw):
    return {"org_id": org, "account_id": account, "ig_media_id": mid, "published_at": ts,
            "caption": caption, "permalink": f"https://ig/{mid}", "thumbnail_url": f"t{mid}",
            "media_url": None, "media_type": "VIDEO", "media_product_type": "REELS",
            "like_count": 3, "comments_count": 1,
            "latest_metrics": {"views": views} if views is not None else {"reach": 5},
            "latest_snapshot_date": "2026-10-08", **kw}


@pytest.fixture
def db():
    d = Db()
    d.tables["integration_accounts"] = [
        _acct(A_IG, ORG, MARCA),
        _acct(A_IG_B, ORG, OTHER_MARCA, label="outra"),
        _acct(A_IG_C, OTHER_ORG, MARCA, label="alheia"),
        _acct(A_YT, ORG, MARCA, provider="youtube", status="active", label="Canal"),
    ]
    d.tables["mc_brand_kits"] = [
        {"id": KIT, "org_id": ORG, "marca_id": MARCA},
        {"id": KIT_OTHER, "org_id": ORG, "marca_id": OTHER_MARCA},
    ]
    return d


# ── registry / protocol ──────────────────────────────────────────────────

def test_registry_matches_constants():
    assert set(FONTES) == set(FONTE_KINDS)


# ── Instagram ────────────────────────────────────────────────────────────

class TestInstagram:
    def test_marca_scoped_accounts(self, db):
        db.tables["ig_media"] = [_media("1", "2026-10-01T10:00:00+00:00")]
        contas = InstagramFonte(db).contas(ORG, MARCA)
        assert [c["account_id"] for c in contas] == [A_IG]
        assert contas[0]["label"] == "@acme" and contas[0]["total_posts"] == 1

    def test_other_marca_and_org_accounts_are_invisible(self, db):
        db.tables["ig_media"] = [
            _media("1", "2026-10-01T10:00:00+00:00", account=A_IG_B),
            _media("2", "2026-10-01T10:00:00+00:00", account=A_IG_C, org=OTHER_ORG),
        ]
        f = InstagramFonte(db)
        for acc in (A_IG_B, A_IG_C):
            assert f.listar(ORG, MARCA, account_id=acc, cursor=None, limit=10, busca=None) == ([], None)
        assert f.obter(ORG, MARCA, [(A_IG_B, "1"), (A_IG_C, "2")]) == {}

    def test_unvalidated_account_is_invisible(self, db):
        db.tables["integration_accounts"][0]["status"] = "revoked"
        assert InstagramFonte(db).contas(ORG, MARCA) == []

    def test_plays_come_from_latest_metrics_and_are_null_not_zero(self, db):
        db.tables["ig_media"] = [
            _media("1", "2026-10-02T10:00:00+00:00", views=1234),
            _media("2", "2026-10-01T10:00:00+00:00"),
            _media("3", "2026-09-30T10:00:00+00:00", views=0),
        ]
        posts, _ = InstagramFonte(db).listar(ORG, MARCA, account_id=A_IG, cursor=None, limit=10, busca=None)
        by = {p.id: p for p in posts}
        assert by["1"].plays == 1234
        assert by["2"].plays is None
        assert by["3"].plays == 0  # a REPORTED zero is kept; only absence is NULL
        assert by["1"].likes == 3 and by["1"].comments == 1
        assert by["1"].extra["media_product_type"] == "REELS"

    def test_keyset_paging_is_stable_with_ties(self, db):
        same = "2026-10-03T10:00:00+00:00"
        db.tables["ig_media"] = [
            _media("100", "2026-10-01T10:00:00+00:00"), _media("200", same),
            _media("300", same), _media("400", "2026-10-05T10:00:00+00:00"),
            _media("500", "2026-10-02T10:00:00+00:00"),
        ]
        f = InstagramFonte(db)
        seen, cursor = [], None
        for _ in range(6):
            posts, cursor = f.listar(ORG, MARCA, account_id=A_IG, cursor=cursor, limit=2, busca=None)
            seen += [p.id for p in posts]
            if not cursor:
                break
        assert seen == ["400", "300", "200", "500", "100"]

    def test_mc_post_text_is_appended_and_overlap_is_excluded_from_mc_list(self, db):
        db.tables["ig_media"] = [_media("M1", "2026-10-02T10:00:00+00:00", caption="Legenda do instagram aqui")]
        db.tables["mc_posts"] = [
            {"id": "p1", "org_id": ORG, "brand_kit_id": KIT, "title": "Titulo do post criado",
             "idea": "ideia", "key_message": None, "copy_caption": "Copy criada", "published_media_id": "M1",
             "published_permalink": None, "published_at": None, "created_at": "2026-10-01T00:00:00+00:00"},
            {"id": "p2", "org_id": ORG, "brand_kit_id": KIT, "title": "Post so criado, nao publicado",
             "idea": "ideia2", "key_message": None, "copy_caption": None, "published_media_id": None,
             "published_permalink": None, "published_at": None, "created_at": "2026-10-03T00:00:00+00:00"},
        ]
        db.tables["mc_post_slides"] = [
            {"org_id": ORG, "post_id": "p1", "slide_n": 2, "headline": "Segundo", "body": "corpo 2"},
            {"org_id": ORG, "post_id": "p1", "slide_n": 1, "headline": "Primeiro", "body": "corpo 1"},
        ]
        ig, _ = InstagramFonte(db).listar(ORG, MARCA, account_id=A_IG, cursor=None, limit=10, busca=None)
        assert "Legenda do instagram aqui" in ig[0].texto
        assert "Titulo do post criado" in ig[0].texto and "Copy criada" in ig[0].texto
        assert ig[0].texto.index("Primeiro") < ig[0].texto.index("Segundo")

        mc = McPostFonte(db)
        posts, _ = mc.listar(ORG, MARCA, account_id=None, cursor=None, limit=10, busca=None)
        assert [p.id for p in posts] == ["p2"]
        assert mc.contas(ORG, MARCA)[0]["total_posts"] == 1
        assert mc.obter(ORG, MARCA, [(None, "p1"), (None, "p2")]).keys() == {(None, "p2")}

    def test_overlap_uses_only_this_marcas_instagram(self, db):
        """Published to a media id that is NOT in the marca's IG catalog -> stays in the mc list."""
        db.tables["ig_media"] = [_media("M9", "2026-10-02T10:00:00+00:00", account=A_IG_B)]
        db.tables["mc_posts"] = [
            {"id": "p1", "org_id": ORG, "brand_kit_id": KIT, "title": "Titulo do post criado", "idea": "x",
             "key_message": None, "copy_caption": None, "published_media_id": "M9",
             "published_permalink": None, "published_at": None, "created_at": "2026-10-01T00:00:00+00:00"},
        ]
        posts, _ = McPostFonte(db).listar(ORG, MARCA, account_id=None, cursor=None, limit=10, busca=None)
        assert [p.id for p in posts] == ["p1"]

    def test_short_text_is_not_analisavel(self, db):
        db.tables["ig_media"] = [
            _media("1", "2026-10-02T10:00:00+00:00", caption="curto"),
            _media("2", "2026-10-01T10:00:00+00:00", caption="x" * MIN_TEXTO_CHARS),
            _media("3", "2026-09-30T10:00:00+00:00", caption=None),
        ]
        posts, _ = InstagramFonte(db).listar(ORG, MARCA, account_id=A_IG, cursor=None, limit=10, busca=None)
        assert {p.id: p.analisavel for p in posts} == {"1": False, "2": True, "3": False}

    def test_busca_filters_text_case_insensitively(self, db):
        db.tables["ig_media"] = [
            _media("1", "2026-10-02T10:00:00+00:00", caption="Falando de EMAGRECIMENTO saudavel"),
            _media("2", "2026-10-01T10:00:00+00:00", caption="Outro assunto totalmente diferente"),
        ]
        posts, nxt = InstagramFonte(db).listar(ORG, MARCA, account_id=A_IG, cursor=None, limit=5, busca="emagrecimento")
        assert [p.id for p in posts] == ["1"] and nxt is None

    def test_obter_returns_only_known_refs(self, db):
        db.tables["ig_media"] = [_media("1", "2026-10-02T10:00:00+00:00")]
        got = InstagramFonte(db).obter(ORG, MARCA, [(A_IG, "1"), (A_IG, "nope"), ("bad", "1")])
        assert set(got) == {(A_IG, "1")}


# ── YouTube ──────────────────────────────────────────────────────────────

def _yt(vid, ts, title="Titulo do video de teste", org=ORG, account=A_YT, **kw):
    return {"org_id": org, "account_id": account, "youtube_video_id": vid, "title": title,
            "description": "descricao do video", "tags": ["a", "b"], "thumbnail_url": f"t{vid}",
            "published_at": ts, "view_count": 10, "like_count": 2, "comment_count": 1, **kw}


class TestYoutube:
    def test_videos_and_shorts_merge_with_shorts_winning(self, db):
        db.tables["youtube_videos"] = [
            _yt("V1", "2026-10-03T10:00:00+00:00"), _yt("S1", "2026-10-02T10:00:00+00:00", view_count=1),
        ]
        db.tables["youtube_shorts"] = [
            _yt("S1", "2026-10-02T10:00:00+00:00", view_count=99), _yt("S2", "2026-10-01T10:00:00+00:00"),
        ]
        f = YoutubeFonte(db)
        posts, _ = f.listar(ORG, MARCA, account_id=A_YT, cursor=None, limit=10, busca=None)
        assert [p.id for p in posts] == ["V1", "S1", "S2"]
        by = {p.id: p for p in posts}
        assert by["S1"].extra["is_short"] is True and by["S1"].plays == 99
        assert by["V1"].extra["is_short"] is False
        assert by["V1"].url == "https://youtube.com/watch?v=V1"
        assert by["S1"].url == "https://youtube.com/shorts/S1"
        assert f.contas(ORG, MARCA)[0]["total_posts"] == 3
        assert "Tags: a, b" in by["V1"].texto

    def test_keyset_paging_across_both_tables(self, db):
        db.tables["youtube_videos"] = [_yt(f"V{i}", f"2026-10-0{i}T10:00:00+00:00") for i in (1, 3, 5)]
        db.tables["youtube_shorts"] = [_yt(f"S{i}", f"2026-10-0{i}T10:00:00+00:00") for i in (2, 4)]
        f = YoutubeFonte(db)
        seen, cursor = [], None
        for _ in range(6):
            posts, cursor = f.listar(ORG, MARCA, account_id=A_YT, cursor=cursor, limit=2, busca=None)
            seen += [p.id for p in posts]
            if not cursor:
                break
        assert seen == ["V5", "S4", "V3", "S2", "V1"]

    def test_scoping(self, db):
        db.tables["youtube_videos"] = [_yt("V1", "2026-10-03T10:00:00+00:00")]
        f = YoutubeFonte(db)
        assert f.contas(OTHER_ORG, MARCA) == []
        assert f.contas(ORG, OTHER_MARCA) == []
        assert f.listar(ORG, OTHER_MARCA, account_id=A_YT, cursor=None, limit=5, busca=None) == ([], None)
        assert f.obter(ORG, OTHER_MARCA, [(A_YT, "V1")]) == {}
        assert set(f.obter(ORG, MARCA, [(A_YT, "V1")])) == {(A_YT, "V1")}

    def test_short_text_not_analisavel(self, db):
        db.tables["youtube_videos"] = [_yt("V1", "2026-10-03T10:00:00+00:00", title="oi", description=None, tags=[])]
        posts, _ = YoutubeFonte(db).listar(ORG, MARCA, account_id=A_YT, cursor=None, limit=5, busca=None)
        assert posts[0].analisavel is False


# ── mc_post ──────────────────────────────────────────────────────────────

class TestMcPost:
    def _post(self, pid, created, kit=KIT, org=ORG, **kw):
        return {"id": pid, "org_id": org, "brand_kit_id": kit, "title": f"Titulo longo do post {pid}",
                "idea": "ideia", "key_message": None, "copy_caption": None, "published_media_id": None,
                "published_permalink": None, "published_at": None, "created_at": created, **kw}

    def test_marca_scoped_with_null_plays_and_keyset(self, db):
        db.tables["mc_posts"] = [
            self._post("a", "2026-10-01T00:00:00+00:00"), self._post("b", "2026-10-03T00:00:00+00:00"),
            self._post("c", "2026-10-02T00:00:00+00:00"),
            self._post("x", "2026-10-09T00:00:00+00:00", kit=KIT_OTHER),
            self._post("y", "2026-10-09T00:00:00+00:00", org=OTHER_ORG),
        ]
        f = McPostFonte(db)
        seen, cursor = [], None
        for _ in range(5):
            posts, cursor = f.listar(ORG, MARCA, account_id=None, cursor=cursor, limit=2, busca=None)
            assert all(p.plays is None and p.likes is None and p.account_id is None for p in posts)
            seen += [p.id for p in posts]
            if not cursor:
                break
        assert seen == ["b", "c", "a"]
        assert f.obter(ORG, MARCA, [(None, "x")]) == {}

    def test_short_text_not_analisavel(self, db):
        db.tables["mc_posts"] = [self._post("a", "2026-10-01T00:00:00+00:00", title="oi", idea="")]
        posts, _ = McPostFonte(db).listar(ORG, MARCA, account_id=None, cursor=None, limit=5, busca=None)
        assert posts[0].analisavel is False
