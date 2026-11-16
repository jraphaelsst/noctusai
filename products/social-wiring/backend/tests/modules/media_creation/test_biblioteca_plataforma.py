"""Biblioteca ingestion under the PLATFORM scope (migration 351, estruturas-contract 4.3 #2-#4): the ingestion org / system
user, the visible ``ingestao_sem_org_plataforma`` failure, the ``depois_de_classificar`` seam, the display-name override and
the one row builder shared by the sync and the admin add-by-link. Real ports + Fakes; nothing is monkeypatched."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import anyio
import pytest

from noctusai_lib.domain.jobs import FakeJobRepository

from app.modules.media_creation.services import biblioteca_fonte as bf
from app.modules.media_creation.services import biblioteca_ingestao as ing

from .test_geracao_biblioteca_ingestao import (
    CDN,
    MP4,
    ORG,
    PID,
    SYS_USER,
    FakeTranscricao,
    _adapter,
    _classificar,
    _db,
    _fetcher,
    _media,
    _page,
    _perfil,
    _ports,
    _reply,
    _rows,
    _sync,
    _transcrever,
    _viral,
    _vstatus,
)


class TestIngestionOrg:
    def test_sync_without_the_platform_org_is_a_visible_coded_failure_not_a_silent_skip(self):
        db = _db()
        adapter = _adapter(_page([_media(1)]))
        _sync(_ports(db, adapter=adapter, org=None))
        p = _perfil(db)
        assert p["status"] == "erro" and p["erro_codigo"] == "ingestao_sem_org_plataforma" and p["erro_mensagem"]
        assert adapter.business_discovery_calls == [] and _rows(db) == []  # nothing was fetched or stored

    def test_classify_without_the_platform_org_marks_the_video_falhou_with_the_code(self):
        db = _db()
        _viral(db, status="nao_aplicavel")
        _classificar(_ports(db, org=None))  # the default LLM raises if called: no spend
        v = _vstatus(db)
        assert v["classificacao_status"] == "falhou" and v["classificacao_erro"] == "ingestao_sem_org_plataforma"

    def test_transcribe_without_the_org_or_the_system_user_fails_visibly_and_still_routes_to_classify(self):
        for org, user, code in ((None, SYS_USER, "ingestao_sem_org_plataforma"), (ORG, None, "ingestao_sem_usuario_plataforma")):
            db = _db()
            _viral(db)
            tr = FakeTranscricao()
            ports = _ports(db, transcricao=tr, org=org, user=user)
            _transcrever(ports)
            v = _vstatus(db)
            assert v["transcricao_status"] == "falhou" and v["classificacao_erro"] == code and tr.calls == []

    def test_the_meta_adapter_is_built_for_the_ingestion_org_not_the_profiles(self):
        medias = [_media(i) for i in range(3)]
        db = _db()
        orgs: list[str] = []
        base = _ports(db, adapter=_adapter(_page(medias)), fetcher=_fetcher(medias))
        make = base.adapter_factory
        base.adapter_factory = lambda acc, org: (orgs.append(org), make(acc, org))[1]
        _sync(base)
        assert orgs == [ORG]

    def test_the_org_readers_are_uuid_validated_and_fail_closed(self):
        good = "11111111-2222-4333-8444-555555555555"
        assert bf.read_ingestao_org(lambda k: good) == good
        assert bf.read_ingestao_org(lambda k: None, default=good) == good  # settings leg
        assert bf.read_ingestao_org(lambda k: "") is None
        assert bf.read_ingestao_org(lambda k: "not-a-uuid") is None
        assert bf.read_ingestao_user(lambda k: good) == good and bf.read_ingestao_user(lambda k: None) is None

        def boom(key):
            raise RuntimeError("db down")

        assert bf.read_ingestao_org(boom) is None  # an unreadable setting is "not configured", never a default org

    def test_a_sync_stores_the_shortcode_and_the_platform_blob_path_and_keeps_a_legacy_orgs_prefix(self):
        medias = [_media(i) for i in range(2)]
        db = _db(org_id=ORG)  # a LEGACY per-org profile (written before 351) keeps its own prefix
        _sync(_ports(db, adapter=_adapter(_page(medias)), fetcher=_fetcher(medias)))
        rows = _rows(db)
        assert all(r["org_id"] == ORG and r["thumbnail_path"].startswith(f"{ORG}/{PID}/") for r in rows)


class TestNomeOverride:
    def test_an_admins_display_name_survives_the_next_sync(self):
        medias = [_media(i) for i in range(2)]
        db = _db(nome="Nome do Admin", nome_editado=True)
        _sync(_ports(db, adapter=_adapter(_page(medias)), fetcher=_fetcher(medias)))
        assert _perfil(db)["nome"] == "Nome do Admin"

    def test_without_an_override_the_source_name_wins(self):
        medias = [_media(i) for i in range(2)]
        db = _db(nome="Velho", nome_editado=False)
        _sync(_ports(db, adapter=_adapter(_page(medias)), fetcher=_fetcher(medias)))
        assert _perfil(db)["nome"] == "Alvo"


class TestOneRowBuilder:
    def test_campos_midia_is_the_shared_normaliser(self):
        m = bf.Midia(
            id="9", permalink="https://www.instagram.com/reel/CODE12345/", media_type="VIDEO", media_product_type="REELS",
            caption="x" * 6000, timestamp=datetime(2026, 10, 1, tzinfo=timezone.utc), like_count=1, comments_count=2, views=3,
            thumbnail_url=None, media_url=f"{CDN}/v.mp4", duracao_s=12.0, shortcode="CODE12345",
        )
        c = bf.campos_midia(m, "2026-11-15T00:00:00+00:00")
        assert len(c["caption"]) == 5000 and c["ig_shortcode"] == "CODE12345" and c["video_url"] == f"{CDN}/v.mp4"
        assert c["duracao_s"] == 12.0 and c["views"] == 3 and c["publicado_em"].startswith("2026-10-01")
        img = bf.Midia(id="1", permalink="p", media_type="IMAGE", media_product_type="FEED", caption=None, timestamp=None,
                       like_count=None, comments_count=None, views=None, thumbnail_url=None, media_url=f"{CDN}/i.jpg")
        c2 = bf.campos_midia(img, "t")
        assert "video_url" not in c2 and "ig_shortcode" not in c2 and c2["publicado_em"] is None and c2["caption"] is None


def _classify(db, callbacks=(), llm=None):
    """Run ``biblioteca.classificar`` with exactly ``callbacks`` registered on the seam."""
    for cb in ing.callbacks_depois_de_classificar():
        ing._DEPOIS_DE_CLASSIFICAR.remove(cb)
    try:
        for cb in callbacks:
            ing.registrar_depois_de_classificar(cb)

        async def default_llm(system, user, org):
            return _reply()

        _classificar(_ports(db, llm=llm or default_llm))
    finally:
        for cb in ing.callbacks_depois_de_classificar():
            ing._DEPOIS_DE_CLASSIFICAR.remove(cb)


class TestDepoisDeClassificar:
    def _seed(self):
        db = _db()
        _viral(db, status="concluida", transcricao_texto="Eu perdi 8 quilos sem passar fome, fala do video")
        return db

    def test_fires_once_per_classification_with_the_viral_id_after_the_result_is_stored(self):
        db, calls = self._seed(), []

        async def cb(ports, viral_id):
            calls.append((viral_id, _vstatus(db)["classificacao_status"]))  # the result is already stored when it runs

        _classify(db, [cb])
        assert calls == [("v1", "concluida")]

    def test_a_retried_job_after_success_does_not_fire_again(self):
        db, calls = self._seed(), []

        async def cb(ports, viral_id):
            calls.append(viral_id)

        _classify(db, [cb])
        _classify(db, [cb])  # status is `concluida`: the handler returns before the seam
        assert calls == ["v1"]

    def test_does_not_fire_when_the_classification_fails(self):
        db, calls = self._seed(), []

        async def cb(ports, viral_id):
            calls.append(viral_id)

        async def bad_llm(system, user, org):
            return "desculpe, não posso"

        _classify(db, [cb], llm=bad_llm)
        assert calls == [] and _vstatus(db)["classificacao_status"] == "falhou"

    def test_registration_is_idempotent_by_identity(self):
        async def cb(ports, viral_id):
            return None

        try:
            ing.registrar_depois_de_classificar(cb)
            ing.registrar_depois_de_classificar(cb)
            assert ing.callbacks_depois_de_classificar().count(cb) == 1
        finally:
            ing._DEPOIS_DE_CLASSIFICAR.remove(cb)

    def test_a_failing_callback_never_fails_the_job_is_recorded_and_the_others_still_run(self):
        db, calls = self._seed(), []

        async def broken(ports, viral_id):
            raise RuntimeError("model quota SEGREDO")

        async def fine(ports, viral_id):
            calls.append(viral_id)

        _classify(db, [broken, fine])  # does not raise
        v = _vstatus(db)
        assert v["classificacao_status"] == "concluida" and v["gancho"]  # the classification stands
        assert calls == ["v1"]
        ev = db.from_("cs_perfil_eventos").select("*").execute().data
        assert [(e["tipo"], e["perfil_id"], e["viral_id"], e["ator_tipo"], e["handle"]) for e in ev] == [
            ("pos_classificacao_falhou", PID, "v1", "sistema", "alvo")]
        assert "SEGREDO" not in json.dumps(ev)  # the event is content-free: no exception text
