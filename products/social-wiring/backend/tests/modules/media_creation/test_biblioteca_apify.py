"""Biblioteca ingestion through the Apify source: statuses, caps, cost, persisted video URL, the
absolute viral rule (owner decision 2026-11-04). Real ports + Fakes; nothing is monkeypatched."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import anyio
import pytest

from noctusai_lib.domain.jobs import FakeJobRepository
from noctusai_lib.domain.jobs.repo import RescheduleLater
from noctusai_lib.integrations.apify import (
    ApifyNotConfigured, ApifyRateLimited, ApifyRunCost, ApifyRunFailed, FakeInstagramScraper,
    InstagramProfileScrape, InstagramPublicPost, InstagramPublicProfile,
)
from noctusai_lib.integrations.media.safe_fetch import FakeSafeFetcher, FetchResult
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.testing import MockSupabaseClient

from app.modules.media_creation.services import biblioteca_fonte as bf
from app.modules.media_creation.services import biblioteca_ingestao as ing

ORG = "test-org-123"
PID = "perfil-1"
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
CFG = SimpleNamespace(
    biblioteca_viral_ratio=3.0, biblioteca_classificacoes_dia_org=300, biblioteca_llm_model="x",
    biblioteca_transcricao_max_fila_org=2, biblioteca_apify_max_posts_primeira_sync=60,
    biblioteca_apify_max_posts_sync=24, biblioteca_apify_resultados_dia_org=600,
    biblioteca_viral_min_views=200_000, biblioteca_viral_min_er_views=0.02, biblioteca_viral_min_er_seguidores=0.03,
)


def _post(i, *, views=300_000, likes=9_000, comments=1_000, days=10, video=True):
    return InstagramPublicPost(
        id=f"m{i}", shortcode=f"S{i}", permalink=f"https://www.instagram.com/p/S{i}/",
        media_type="VIDEO" if video else "IMAGE", product_type="clips" if video else None, caption=f"c{i}",
        timestamp=NOW - timedelta(days=days, minutes=i), likes=likes, comments=comments, views=views,
        duration_s=20.0, display_url=None, video_url=f"https://scontent.cdninstagram.com/v{i}.mp4",
        owner_username="alvo",
    )


class Scraper:
    def __init__(self, posts, followers=100_000, usd=Decimal("0.01"), error=None):
        self.posts, self.followers, self.usd, self.error, self.calls = posts, followers, usd, error, []

    def scrape_profile(self, handle, *, max_posts, newer_than=None, timeout_s=240):
        self.calls.append((handle, max_posts, newer_than))
        if self.error:
            raise self.error
        return InstagramProfileScrape(
            profile=InstagramPublicProfile(username=handle, full_name="Alvo", followers_count=self.followers,
                                           posts_count=len(self.posts)),
            posts=self.posts, cost=ApifyRunCost(results=len(self.posts), usd=self.usd, run_id="r1"),
        )


class Ledger:
    def __init__(self):
        self.db = MockSupabaseClient()


def _db(**extra):
    db = MockSupabaseClient()
    db.from_("cs_perfis_monitorados").insert({
        "id": PID, "org_id": ORG, "rede": "instagram", "handle": "alvo", "status": "aguardando",
        "created_by": "u1", **extra,
    }).execute()
    return db


def _ports(db, scraper=None, factory=None, ledger=None, cfg=CFG):
    def no_adapter(a, o):
        raise AssertionError("Meta must not be touched on the Apify path")

    def default_factory(org):
        if scraper is None:
            raise ApifyNotConfigured("no token")
        return scraper

    return ing.IngestaoPorts(
        db=db, jobs=FakeJobRepository(), storage=FakeStorageBackend(), fetcher=FakeSafeFetcher(),
        llm=None, adapter_factory=no_adapter, transcricao_factory=lambda o, u: None, cfg=cfg, clock=lambda: NOW,
        scraper_factory=factory or default_factory, fonte_reader=lambda: "apify",
        ledger_factory=(lambda: ledger.db) if ledger else None,
    )


def _sync(ports):
    async def go():
        job = await ports.jobs.enqueue(type="biblioteca.sync_perfil", payload={"perfil_id": PID}, max_retries=2)
        await ing.sync_perfil(ports, job)

    anyio.run(go)


def _perfil(db):
    return db.from_("cs_perfis_monitorados").select("*").eq("id", PID).execute().data[0]


def _virais(db):
    return {r["ig_media_id"]: r for r in db.from_("cs_virais").select("*").execute().data}


def test_sync_without_meta_account_persists_views_video_url_cost_and_header():
    db, ledger = _db(), Ledger()
    sc = Scraper([_post(0), _post(1, views=199_999)])
    ports = _ports(db, sc, ledger=ledger)
    _sync(ports)
    v = _virais(db)
    assert v["m0"]["views"] == 300_000 and v["m0"]["video_url"].endswith("v0.mp4") and v["m0"]["video_url_em"]
    assert v["m0"]["duracao_s"] == 20.0 and v["m0"]["media_product_type"] == "REELS"
    p = _perfil(db)
    assert p["status"] == "ativo" and p["seguidores"] == 100_000 and p["nome"] == "Alvo"
    assert not p.get("conta_descoberta_id")
    assert sc.calls == [("alvo", 60, None)]
    led = ledger.db.from_("cost_ledger").select("*").execute().data
    assert len(led) == 1 and led[0]["category"] == "apify" and led[0]["currency"] == "USD" and led[0]["fx_pending"]
    assert db.from_("cs_apify_uso").select("*").execute().data[0]["resultados"] == 2


class TestViralAbsoluto:
    def _r(self, views, likes, comments, days=10):
        return {"views": views, "likes": likes, "comments": comments,
                "publicado_em": (NOW - timedelta(days=days)).isoformat()}

    def test_views_boundary(self):
        assert ing.avaliar_viral_absoluto(self._r(200_000, 6_000, 0), 100_000, CFG, NOW)[2] is True
        assert ing.avaliar_viral_absoluto(self._r(199_999, 6_000, 0), 100_000, CFG, NOW)[2] is False

    def test_er_views_at_threshold(self):
        # 4000/200000 = 0.02 exactly; er_seg 4000/100000 = 0.04
        assert ing.avaliar_viral_absoluto(self._r(200_000, 4_000, 0), 100_000, CFG, NOW)[2] is True
        assert ing.avaliar_viral_absoluto(self._r(200_000, 3_999, 0), 100_000, CFG, NOW)[2] is False

    def test_er_seguidores_at_threshold(self):
        # 6000/200000 = 0.03 views ER; followers 200_000 -> 0.03 exactly
        assert ing.avaliar_viral_absoluto(self._r(200_000, 6_000, 0), 200_000, CFG, NOW)[2] is True
        assert ing.avaliar_viral_absoluto(self._r(200_000, 6_000, 0), 200_001, CFG, NOW)[2] is False

    def test_hidden_likes_and_missing_data_are_not_viral_and_not_zero(self):
        assert ing.avaliar_viral_absoluto(self._r(500_000, None, 10), 100_000, CFG, NOW) == (None, None, False)
        assert ing.avaliar_viral_absoluto(self._r(None, 100, 10), 100_000, CFG, NOW) == (None, 110 / 100_000, False)
        assert ing.avaliar_viral_absoluto(self._r(500_000, 9_000, 1_000), None, CFG, NOW)[1:] == (None, False)

    def test_zero_followers_does_not_divide(self):
        assert ing.avaliar_viral_absoluto(self._r(500_000, 9_000, 1_000), 0, CFG, NOW)[1:] == (None, False)

    def test_younger_than_48h_not_viral(self):
        assert ing.avaliar_viral_absoluto(self._r(500_000, 9_000, 1_000, days=1), 100_000, CFG, NOW)[2] is False


def test_sync_flags_viral_by_absolute_rule_and_stores_inputs():
    db = _db()
    posts = [_post(0), _post(1, views=199_999), _post(2, likes=None)]
    _sync(_ports(db, Scraper(posts)))
    v = _virais(db)
    assert v["m0"]["e_viral"] is True and v["m0"]["er_views"] == pytest.approx(10_000 / 300_000)
    assert v["m0"]["er_seguidores"] == pytest.approx(0.1) and v["m0"]["seguidores_no_fetch"] == 100_000
    assert v["m1"]["e_viral"] is False
    assert v["m2"]["e_viral"] is False and v["m2"]["er_views"] is None and v["m2"]["likes"] is None


def test_no_token_parks_sem_credencial():
    db = _db()
    _sync(_ports(db, None))
    p = _perfil(db)
    assert p["status"] == "sem_credencial" and "Chaves de API" in p["erro_mensagem"]


def test_daily_cap_parks_sem_orcamento_without_calling_scraper():
    db = _db()
    db.from_("cs_apify_uso").insert({"org_id": ORG, "perfil_id": PID, "resultados": 600,
                                     "criado_em": NOW.isoformat()}).execute()
    sc = Scraper([_post(0)])
    _sync(_ports(db, sc))
    assert _perfil(db)["status"] == "sem_orcamento" and sc.calls == []


def test_not_found_private_rate_limit_and_failure():
    from noctusai_lib.integrations.apify import ApifyProfileNotFound

    db = _db()
    _sync(_ports(db, Scraper([], error=ApifyProfileNotFound("x", reason="privado"))))
    p = _perfil(db)
    assert p["status"] == "nao_encontrado" and p["erro_codigo"] == "privado"
    with pytest.raises(RescheduleLater):
        _sync(_ports(_db(), Scraper([], error=ApifyRateLimited(retry_after_s=30))))
    with pytest.raises(ApifyRunFailed):
        _sync(_ports(_db(), Scraper([], error=ApifyRunFailed("boom"))))


def test_later_sync_uses_refresh_window_and_smaller_cap():
    db = _db()
    sc = Scraper([_post(0)])
    _sync(_ports(db, sc))
    db.from_("cs_perfis_monitorados").update({"ultima_sync_em": (NOW - timedelta(hours=2)).isoformat()}).eq("id", PID).execute()
    _sync(_ports(db, sc))
    assert sc.calls[1][1] == 24 and sc.calls[1][2] == (NOW - timedelta(days=30)).date()


def test_fonte_reader_default_and_validation():
    assert bf.read_biblioteca_fonte(lambda k: None) == "apify"
    assert bf.read_biblioteca_fonte(lambda k: "Business_Discovery") == "business_discovery"
    assert bf.read_biblioteca_fonte(lambda k: "bogus") == "apify"


def test_transcrever_reuses_persisted_video_url_within_24h():
    fresh = {"video_url": "u", "video_url_em": (NOW - timedelta(hours=3)).isoformat()}
    stale = {"video_url": "u", "video_url_em": (NOW - timedelta(hours=30)).isoformat()}
    assert ing._video_url_vigente(fresh, NOW) == "u"
    assert ing._video_url_vigente(stale, NOW) is None
    assert ing._video_url_vigente({}, NOW) is None


def test_viral_detail_exposes_video_url_only_while_fresh():
    from app.modules.media_creation.services import biblioteca_service as bs

    assert bs.VIDEO_URL_FRESCA == timedelta(hours=24)
    now = datetime.now(timezone.utc)
    db = MockSupabaseClient()
    db.from_("marcas").insert({"id": "marca-1", "org_id": ORG, "nome": "m"}).execute()
    db.from_("cs_perfis_monitorados").insert({"id": PID, "org_id": ORG, "handle": "alvo", "status": "ativo"}).execute()
    for vid, hours in (("v-fresh", 3), ("v-old", 30)):
        db.from_("cs_virais").insert({
            "id": vid, "org_id": ORG, "perfil_id": PID, "codigo": 1, "ig_media_id": vid,
            "transcricao_status": "concluida", "classificacao_status": "concluida", "video_url": f"https://c/{vid}.mp4",
            "video_url_em": (now - timedelta(hours=hours)).isoformat(),
        }).execute()
    db.from_("cs_virais").insert({
        "id": "v-none", "org_id": ORG, "perfil_id": PID, "codigo": 2, "ig_media_id": "n",
        "transcricao_status": "nao_aplicavel", "classificacao_status": "pendente",
    }).execute()
    svc = bs.BibliotecaService(db, ORG, "u1", storage=FakeStorageBackend(), jobs=FakeJobRepository(), switch=lambda: True)

    async def go():
        return [(await svc.get_viral(v, "marca-1"))["video_url"] for v in ("v-fresh", "v-old", "v-none")]

    assert anyio.run(go) == ["https://c/v-fresh.mp4", None, None]
