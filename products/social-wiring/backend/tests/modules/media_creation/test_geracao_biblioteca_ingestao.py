"""Biblioteca ingestion: sync / transcrever / classificar handlers, the transcription context hook,
dead-letter reconcilers and the scheduler sweeps -- all through the real ports with Fakes."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import anyio
import pytest

from noctusai_lib.domain.jobs import DeadLetterError, FakeJobRepository
from noctusai_lib.domain.jobs.repo import RescheduleLater
from noctusai_lib.integrations.media.safe_fetch import FakeSafeFetcher, FetchResult, SafeFetchError
from noctusai_lib.integrations.meta import (
    BusinessDiscoveryMedia,
    BusinessDiscoveryNotFound,
    BusinessDiscoveryPage,
    FakeMetaAdapter,
    MetaGraphError,
)
from noctusai_lib.integrations.meta.types import InstagramAccount
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.testing import MockSupabaseClient

from app.modules.media_creation import biblioteca_scheduler as sched
from app.modules.media_creation.services import biblioteca_ingestao as ing
from app.modules.media_creation.services import biblioteca_transcricao as bt
from app.modules.transcricoes import hooks
from app.modules.transcricoes.errors import TranscricaoErro

ORG = "test-org-123"
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"0" * 64
CDN = "https://scontent.cdninstagram.com"
PID = "perfil-1"
CFG = SimpleNamespace(biblioteca_viral_ratio=3.0, biblioteca_classificacoes_dia_org=300, biblioteca_llm_model="claude-haiku-4-5")


class FakeTranscricao:
    def __init__(self, *, error: TranscricaoErro | None = None):
        self.error = error
        self.calls: list[tuple[int, str, str]] = []

    async def submit_sistema(self, data, contexto_ref, *, user_id):
        self.calls.append((len(data), contexto_ref, user_id))
        if self.error:
            raise self.error
        return {"id": "tr-1", "status": "na_fila", "posicao": 1, "estimativa_s": 30, "duracao_s": 42.5}


def _media(i: int, *, likes: int = 100, days: int = 10, video: bool = False) -> BusinessDiscoveryMedia:
    return BusinessDiscoveryMedia(
        id=f"m{i}", caption=f"legenda {i}", media_type="VIDEO" if video else "IMAGE",
        media_product_type="REELS" if video else "FEED",
        media_url=f"{CDN}/v{i}.mp4" if video else f"{CDN}/i{i}.jpg",
        thumbnail_url=f"{CDN}/t{i}.jpg" if video else None, permalink=f"https://instagram.com/p/{i}",
        timestamp=NOW - timedelta(days=days, minutes=i), like_count=likes, comments_count=0,
    )


def _page(medias, **kw) -> BusinessDiscoveryPage:
    return BusinessDiscoveryPage(
        username="alvo", ig_user_id="999", name="Alvo", followers_count=1234, media_count=len(medias),
        profile_picture_url=f"{CDN}/pic.jpg", media=list(medias), **kw,
    )


def _fetcher(medias=()) -> FakeSafeFetcher:
    res: dict[str, Any] = {f"{CDN}/pic.jpg": FetchResult(f"{CDN}/pic.jpg", 200, "image/jpeg", JPEG)}
    for m in medias:
        for u in (m.thumbnail_url, m.media_url):
            if u and u.endswith(".jpg"):
                res[u] = FetchResult(u, 200, "image/jpeg", JPEG)
            elif u:
                res[u] = FetchResult(u, 200, "video/mp4", MP4)
    return FakeSafeFetcher(res)


def _db(*, conta: bool = True, perfil_status: str = "aguardando", **perfil_extra) -> MockSupabaseClient:
    db = MockSupabaseClient()
    if conta:
        db.from_("integration_accounts").insert({
            "id": "acc-1", "org_id": ORG, "provider": "meta", "status": "validated", "is_default": True,
            "account_label": "Minha conta", "metadata": {"channel_title": "eu"},
        }).execute()
    db.from_("cs_perfis_monitorados").insert({
        "id": PID, "org_id": ORG, "rede": "instagram", "handle": "alvo", "status": perfil_status,
        "created_by": "user-1", "conta_descoberta_id": None, **perfil_extra,
    }).execute()
    return db


def _adapter(page=None, error=None, accounts=True):
    ad = FakeMetaAdapter()
    ad.seed(
        ig_accounts=[InstagramAccount(id="111", username="eu")] if accounts else [],
        business_discovery={"alvo": page} if page else {},
        business_discovery_errors={"alvo": error} if error else {},
    )
    return ad


def _ports(db, *, adapter=None, fetcher=None, llm=None, transcricao=None, jobs=None, storage=None, cfg=CFG):
    async def no_llm(system, user, org):
        raise AssertionError("LLM not expected")

    def make_adapter(account_id, org_id):
        assert org_id == ORG
        return adapter

    return ing.IngestaoPorts(
        db=db, jobs=jobs or FakeJobRepository(), storage=storage or FakeStorageBackend(),
        fetcher=fetcher or FakeSafeFetcher(), llm=llm or no_llm, adapter_factory=make_adapter,
        transcricao_factory=lambda org, user: transcricao or FakeTranscricao(), cfg=cfg, clock=lambda: NOW,
    )


async def _job(ports, type_, payload):
    return await ports.jobs.enqueue(type=type_, payload=payload, max_retries=2)


def run(coro):
    return anyio.run(lambda: coro)


def _rows(db, table="cs_virais"):
    return db.from_(table).select("*").execute().data


def _perfil(db):
    return db.from_("cs_perfis_monitorados").select("*").eq("id", PID).execute().data[0]


def _queued(ports, type_):
    return [j for j in ports.jobs._jobs.values() if j.type == type_]


def _sync(ports):
    async def go():
        await ing.sync_perfil(ports, await _job(ports, "biblioteca.sync_perfil", {"perfil_id": PID}))

    anyio.run(go)


class TestSync:
    def test_first_sync_upserts_flags_virals_and_routes_the_pipeline(self):
        medias = [_media(i) for i in range(10)] + [_media(20, likes=500, video=True), _media(21, likes=450)]
        db, jobs = _db(), FakeJobRepository()
        ports = _ports(db, adapter=_adapter(_page(medias)), fetcher=_fetcher(medias), jobs=jobs)
        _sync(ports)

        rows = {r["ig_media_id"]: r for r in _rows(db)}
        assert len(rows) == 12
        assert rows["m20"]["e_viral"] and rows["m21"]["e_viral"] and not rows["m0"]["e_viral"]
        assert rows["m20"]["score_viral"] == 5.0
        # thumbnails mirrored into the private bucket; the video's poster (not the mp4) was fetched
        assert rows["m0"]["thumbnail_path"].startswith(f"{ORG}/{PID}/") and rows["m0"]["thumbnail_path"].endswith(".jpg")
        assert rows["m20"]["thumbnail_path"]
        assert not any(u.endswith(".mp4") for u in ports.fetcher.calls)
        # a viral Reel goes to transcription; a viral image straight to classification
        assert rows["m20"]["transcricao_status"] == "pendente"
        assert rows["m21"]["transcricao_status"] == "nao_aplicavel"
        t = _queued(ports, "biblioteca.transcrever")
        c = _queued(ports, "biblioteca.classificar")
        assert [j.payload["viral_id"] for j in t] == [rows["m20"]["id"]]
        assert t[0].payload["media_url"].endswith("v20.mp4")
        assert [j.payload["viral_id"] for j in c] == [rows["m21"]["id"]]
        p = _perfil(db)
        assert p["status"] == "ativo" and p["metrica_base"] == "engajamento" and p["mediana_metrica"] == 100.0
        assert p["nome"] == "Alvo" and p["seguidores"] == 1234 and p["foto_path"]
        assert p["conta_descoberta_id"] == "acc-1" and p["ultima_sync_em"] and p["proxima_sync_em"]

    def test_resync_updates_metrics_without_duplicating_or_requeueing(self):
        medias = [_media(i) for i in range(11)] + [_media(21, likes=450)]
        db = _db()
        ports = _ports(db, adapter=_adapter(_page(medias)), fetcher=_fetcher(medias))
        _sync(ports)
        first_n = len(_queued(ports, "biblioteca.classificar"))
        medias2 = [_media(i) for i in range(11)] + [_media(21, likes=900)]
        ports2 = _ports(db, adapter=_adapter(_page(medias2)), fetcher=_fetcher(medias2), jobs=ports.jobs)
        _sync(ports2)
        rows = _rows(db)
        assert len(rows) == 12
        assert next(r for r in rows if r["ig_media_id"] == "m21")["likes"] == 900
        assert len(_queued(ports, "biblioteca.classificar")) == first_n  # same viral: no second job

    def test_first_sync_reads_at_most_50_posts_in_pages_of_25(self):
        medias = [_media(i) for i in range(80)]
        adapter = _adapter(_page(medias))
        ports = _ports(_db(), adapter=adapter, fetcher=_fetcher(medias))
        _sync(ports)
        assert len(_rows(ports.db)) == 50
        assert [c["limit"] for c in adapter.business_discovery_calls] == [25, 25]
        assert all(c["ig_user_id"] == "111" for c in adapter.business_discovery_calls)

    def test_fewer_than_ten_posts_means_no_virals(self):
        medias = [_media(i) for i in range(5)] + [_media(9, likes=9999)]
        db = _db()
        _sync(_ports(db, adapter=_adapter(_page(medias)), fetcher=_fetcher(medias)))
        assert not any(r["e_viral"] for r in _rows(db))
        assert _perfil(db)["mediana_metrica"] is None and _perfil(db)["status"] == "ativo"

    def test_young_post_is_not_viral_yet(self):
        medias = [_media(i) for i in range(11)] + [_media(30, likes=900, days=0)]
        db = _db()
        _sync(_ports(db, adapter=_adapter(_page(medias)), fetcher=_fetcher(medias)))
        young = next(r for r in _rows(db) if r["ig_media_id"] == "m30")
        assert young["score_viral"] >= 3.0 and young["e_viral"] is False

    def test_unknown_handle_is_nao_encontrado(self):
        db = _db()
        _sync(_ports(db, adapter=_adapter(error=BusinessDiscoveryNotFound("x", code=110))))
        p = _perfil(db)
        assert p["status"] == "nao_encontrado" and "profissionais" in p["erro_mensagem"]

    def test_no_meta_account_is_sem_conta(self):
        db = _db(conta=False)
        _sync(_ports(db))
        assert _perfil(db)["status"] == "sem_conta"

    def test_account_without_instagram_is_sem_conta(self):
        db = _db()
        _sync(_ports(db, adapter=_adapter(accounts=False)))
        assert _perfil(db)["status"] == "sem_conta"

    def test_permission_refusal_is_sem_conta_with_our_copy_not_graphs(self):
        db = _db()
        err = MetaGraphError("(#10) secret graph text", code=10)
        _sync(_ports(db, adapter=_adapter(error=err)))
        p = _perfil(db)
        assert p["status"] == "sem_conta"
        assert "secret graph text" not in (p["erro_mensagem"] or "") and "permissão" in p["erro_mensagem"]

    def test_rate_limit_reschedules_without_failing(self):
        db = _db()
        ports = _ports(db, adapter=_adapter(error=MetaGraphError("slow down", code=4)))
        with pytest.raises(RescheduleLater) as ei:
            _sync(ports)
        assert ei.value.delay_s == 900
        assert _perfil(db)["status"] == "aguardando"

    def test_transient_graph_error_is_raised_for_retry(self):
        ports = _ports(_db(), adapter=_adapter(error=MetaGraphError("boom", code=1)))
        with pytest.raises(MetaGraphError):
            _sync(ports)

    def test_paused_profile_is_skipped(self):
        db = _db(perfil_status="pausado")
        adapter = _adapter(_page([_media(1)]))
        _sync(_ports(db, adapter=adapter))
        assert adapter.business_discovery_calls == [] and _rows(db) == []

    def test_missing_profile_is_dead_lettered(self):
        ports = _ports(_db())
        with pytest.raises(DeadLetterError):
            anyio.run(lambda: ing.sync_perfil(ports, SimpleNamespace(payload={"perfil_id": "nope"})))

    def test_a_broken_thumbnail_never_fails_the_sync(self):
        medias = [_media(i) for i in range(11)]
        fetcher = _fetcher(medias)
        fetcher.responses[f"{CDN}/i3.jpg"] = SafeFetchError("http_status", "404")
        db = _db()
        _sync(_ports(db, adapter=_adapter(_page(medias)), fetcher=fetcher))
        rows = {r["ig_media_id"]: r for r in _rows(db)}
        assert len(rows) == 11 and not rows["m3"].get("thumbnail_path") and rows["m4"]["thumbnail_path"]

    def test_media_is_only_ever_fetched_from_the_cdn_allowlist(self):
        m = _media(1)
        evil = BusinessDiscoveryMedia(**{**m.__dict__, "id": "m2", "media_url": "https://evil.example/x.jpg", "thumbnail_url": None})
        fetcher = _fetcher([m])
        db = _db()
        _sync(_ports(db, adapter=_adapter(_page([m, evil])), fetcher=fetcher))
        assert "https://evil.example/x.jpg" not in fetcher.calls  # refused by host validation, never requested
        row = next(r for r in _rows(db) if r["ig_media_id"] == "m2")
        assert not row.get("thumbnail_path")  # host_not_allowed -> skipped, sync still completed
        assert _perfil(db)["status"] == "ativo"

    def test_sem_orcamento_viral_is_retried_with_a_fresh_url(self):
        medias = [_media(i) for i in range(11)] + [_media(20, likes=500, video=True)]
        db = _db()
        ports = _ports(db, adapter=_adapter(_page(medias)), fetcher=_fetcher(medias))
        _sync(ports)
        vid = next(r["id"] for r in _rows(db) if r["ig_media_id"] == "m20")
        db.from_("cs_virais").update({"transcricao_status": "sem_orcamento"}).eq("id", vid).execute()
        ports2 = _ports(db, adapter=_adapter(_page(medias)), fetcher=_fetcher(medias), jobs=FakeJobRepository())
        _sync(ports2)
        assert next(r for r in _rows(db) if r["id"] == vid)["transcricao_status"] == "pendente"
        assert len(_queued(ports2, "biblioteca.transcrever")) == 1


def _viral(db, *, status="pendente", **extra):
    row = {
        "id": "v1", "org_id": ORG, "perfil_id": PID, "ig_media_id": "m1", "caption": "legenda",
        "e_viral": True, "transcricao_status": status, "classificacao_status": "pendente", **extra,
    }
    db.from_("cs_virais").insert(row).execute()
    return row


def _transcrever(ports, url=f"{CDN}/v1.mp4"):
    async def go():
        await ing.transcrever(ports, await _job(ports, "biblioteca.transcrever", {"viral_id": "v1", "media_url": url}))

    anyio.run(go)


def _vstatus(db):
    return next(r for r in _rows(db) if r["id"] == "v1")


class TestTranscrever:
    def _fetch(self, **kw):
        return FakeSafeFetcher({f"{CDN}/v1.mp4": kw.get("res") or FetchResult(f"{CDN}/v1.mp4", 200, "video/mp4", MP4)})

    def test_success_submits_as_the_system_for_the_profile_owner(self):
        db = _db()
        _viral(db)
        tr = FakeTranscricao()
        ports = _ports(db, fetcher=self._fetch(), transcricao=tr)
        _transcrever(ports)
        v = _vstatus(db)
        assert v["transcricao_status"] == "na_fila" and v["transcricao_id"] == "tr-1" and v["duracao_s"] == 42.5
        assert tr.calls == [(len(MP4), "v1", "user-1")]
        assert _queued(ports, "biblioteca.classificar") == []  # classification waits for the hook

    @pytest.mark.parametrize("codigo,expected", [
        ("arquivo_grande", "grande_demais"),
        ("duracao_excedida", "longa_demais"),
        ("cota_diaria_org", "sem_orcamento"),
        ("capacidade_diaria", "sem_orcamento"),
        ("fila_cheia", "sem_orcamento"),
        ("reel_longo", "longa_demais"),
        ("fila_biblioteca_cheia", "sem_orcamento"),
        ("cota_diaria_biblioteca_org", "sem_orcamento"),
        ("capacidade_diaria_biblioteca", "sem_orcamento"),
        ("audio_corrompido", "falhou"),
    ])
    def test_terminal_states_still_classify(self, codigo, expected):
        db = _db()
        _viral(db)
        ports = _ports(db, fetcher=self._fetch(), transcricao=FakeTranscricao(error=TranscricaoErro(codigo)))
        _transcrever(ports)
        assert _vstatus(db)["transcricao_status"] == expected
        assert [j.payload for j in _queued(ports, "biblioteca.classificar")] == [{"viral_id": "v1"}]

    def test_over_the_byte_cap_is_grande_demais_and_never_submitted(self):
        db = _db()
        _viral(db)
        tr = FakeTranscricao()
        fetcher = FakeSafeFetcher({f"{CDN}/v1.mp4": SafeFetchError("too_large", "x")})
        ports = _ports(db, fetcher=fetcher, transcricao=tr)
        _transcrever(ports)
        assert _vstatus(db)["transcricao_status"] == "grande_demais" and tr.calls == []
        assert len(_queued(ports, "biblioteca.classificar")) == 1

    def test_refused_host_is_falhou_without_a_request(self):
        db = _db()
        _viral(db)
        tr = FakeTranscricao()
        ports = _ports(db, fetcher=FakeSafeFetcher(), transcricao=tr)
        _transcrever(ports, url="https://169.254.169.254/latest/meta-data")
        assert _vstatus(db)["transcricao_status"] == "falhou" and tr.calls == []

    def test_transient_network_error_is_raised_for_retry(self):
        db = _db()
        _viral(db)
        ports = _ports(db, fetcher=FakeSafeFetcher({f"{CDN}/v1.mp4": SafeFetchError("timeout", "x")}))
        with pytest.raises(SafeFetchError):
            _transcrever(ports)
        assert _vstatus(db)["transcricao_status"] == "pendente"

    def test_switch_off_or_unavailable_transcriber_reschedules_without_a_retry(self):
        db = _db()
        _viral(db)
        err = TranscricaoErro("transcricao_desativada")
        ports = _ports(db, fetcher=self._fetch(), transcricao=FakeTranscricao(error=err))
        with pytest.raises(RescheduleLater):
            _transcrever(ports)
        assert _vstatus(db)["transcricao_status"] == "pendente"

    def test_already_settled_viral_is_a_noop(self):
        db = _db()
        _viral(db, status="concluida")
        tr = FakeTranscricao()
        _transcrever(_ports(db, fetcher=self._fetch(), transcricao=tr))
        assert tr.calls == [] and _vstatus(db)["transcricao_status"] == "concluida"

    def test_missing_viral_is_dead_lettered(self):
        ports = _ports(_db())
        with pytest.raises(DeadLetterError):
            anyio.run(lambda: ing.transcrever(ports, SimpleNamespace(payload={"viral_id": "ghost"})))


def _reply(**over):
    d = {
        "gancho": "Eu perdi 8 quilos sem passar fome", "formato_ids": [8], "nicho_ids": [1], "profissao_ids": [2],
        "gatilho": "recompensa", "blueprint": "Eu {{DESEJOS-ALCANCADOS-PELO-ESPECIALISTA}} sem passar fome",
        "substituicoes": [], "slots": [],
    }
    d.update(over)
    return json.dumps(d)


def _classificar(ports):
    async def go():
        await ing.classificar(ports, await _job(ports, "biblioteca.classificar", {"viral_id": "v1"}))

    anyio.run(go)


class TestClassificar:
    def _llm(self, reply, seen=None):
        async def llm(system, user, org_id):
            if seen is not None:
                seen.append((system, user, org_id))
            return reply

        return llm

    def test_success_writes_the_structure(self):
        db = _db()
        _viral(db, status="concluida", transcricao_texto="fala do video")
        seen: list = []
        _classificar(_ports(db, llm=self._llm(_reply(), seen)))
        v = _vstatus(db)
        assert v["classificacao_status"] == "concluida" and v["gancho"].startswith("Eu perdi")
        assert v["nicho_ids"] == [1] and v["gatilho"] == "recompensa"
        assert v["blueprint_slots"] == ["DESEJOS-ALCANCADOS-PELO-ESPECIALISTA"] and v["blueprint"]
        assert v["classificacao_modelo"].startswith("claude-haiku-4-5|biblioteca-classificador")
        assert seen[0][2] == ORG and "fala do video" in seen[0][1] and "<legenda>" in seen[0][1]

    def test_rejected_blueprint_keeps_taxonomy_and_records_why(self):
        db = _db()
        _viral(db, status="nao_aplicavel")
        _classificar(_ports(db, llm=self._llm(_reply(blueprint="Eu {{INVENTADO}} sem passar fome"))))
        v = _vstatus(db)
        assert v["classificacao_status"] == "concluida" and v["blueprint"] is None
        assert "slot desconhecido" in v["classificacao_erro"] and v["nicho_ids"] == [1]

    def test_unparseable_reply_is_falhou(self):
        db = _db()
        _viral(db, status="nao_aplicavel")
        _classificar(_ports(db, llm=self._llm("desculpe, não posso")))
        assert _vstatus(db)["classificacao_status"] == "falhou"

    def test_waits_for_a_transcription_in_flight(self):
        db = _db()
        _viral(db, status="na_fila")
        with pytest.raises(RescheduleLater):
            _classificar(_ports(db))
        assert _vstatus(db)["classificacao_status"] == "pendente"

    def test_concluida_is_idempotent_and_spends_nothing(self):
        db = _db()
        _viral(db, status="nao_aplicavel")
        db.from_("cs_virais").update({"classificacao_status": "concluida"}).eq("id", "v1").execute()
        _classificar(_ports(db))  # the default LLM raises if called

    def test_org_daily_cap_defers(self):
        db = _db()
        _viral(db, status="nao_aplicavel")
        db.from_("cs_virais").insert({
            "id": "v2", "org_id": ORG, "perfil_id": PID, "ig_media_id": "m2", "classificado_em": NOW.isoformat(),
            "classificacao_status": "concluida", "transcricao_status": "nao_aplicavel",
        }).execute()
        cfg = SimpleNamespace(**{**CFG.__dict__, "biblioteca_classificacoes_dia_org": 1})
        with pytest.raises(RescheduleLater):
            _classificar(_ports(db, cfg=cfg))


class TestTranscricaoHook:
    def test_registered_with_the_shared_layer(self):
        bt.register_contexto()
        assert hooks.get_contexto("biblioteca_viral") is not None

    def test_validar_scopes_to_the_org(self):
        db = _db()
        _viral(db)
        bt.validar(db, ORG, "u", "v1")
        with pytest.raises(TranscricaoErro) as ei:
            bt.validar(db, "other-org", "u", "v1")
        assert ei.value.status == 404
        with pytest.raises(TranscricaoErro):
            bt.validar(db, ORG, "u", "ghost")

    def test_aplicar_writes_transcript_and_is_idempotent(self):
        db = _db()
        _viral(db, status="na_fila")
        row = {"id": "tr-1", "org_id": ORG, "contexto_ref": "v1", "texto": "  olá mundo  ", "duracao_s": 30}
        bt.aplicar(db, row)
        bt.aplicar(db, row)
        v = _vstatus(db)
        assert v["transcricao_texto"] == "olá mundo" and v["transcricao_status"] == "concluida"
        assert v["transcricao_id"] == "tr-1" and v["duracao_s"] == 30.0

    def test_aplicar_clips_to_the_column_cap(self):
        db = _db()
        _viral(db, status="na_fila")
        bt.aplicar(db, {"id": "t", "org_id": ORG, "contexto_ref": "v1", "texto": "a" * 60_000})
        assert len(_vstatus(db)["transcricao_texto"]) == 50_000

    def test_aplicar_for_a_deleted_viral_is_a_logged_noop(self):
        bt.aplicar(_db(), {"id": "t", "org_id": ORG, "contexto_ref": "gone", "texto": "x"})

    def test_aplicar_never_writes_into_another_orgs_viral(self):
        db = _db()
        _viral(db, status="na_fila")
        bt.aplicar(db, {"id": "t", "org_id": "other-org", "contexto_ref": "v1", "texto": "invadido"})
        assert _vstatus(db).get("transcricao_texto") is None


class TestReconcilers:
    def test_sync_dead_letter_marks_erro_with_our_copy(self):
        db = _db(perfil_status="ativo")
        ing.reconcile_sync(db, SimpleNamespace(payload={"perfil_id": PID}))
        assert _perfil(db)["status"] == "erro" and _perfil(db)["erro_mensagem"] == ing.MSG_ERRO

    def test_sync_dead_letter_leaves_paused_and_terminal_states(self):
        for status in ("pausado", "sem_conta", "nao_encontrado"):
            db = _db(perfil_status=status)
            ing.reconcile_sync(db, SimpleNamespace(payload={"perfil_id": PID}))
            assert _perfil(db)["status"] == status

    def test_classificar_and_transcrever_dead_letters(self):
        db = _db()
        _viral(db, status="pendente")
        ing.reconcile_classificar(db, SimpleNamespace(payload={"viral_id": "v1"}))
        ing.reconcile_transcrever(db, SimpleNamespace(payload={"viral_id": "v1"}))
        v = _vstatus(db)
        assert v["classificacao_status"] == "falhou" and v["transcricao_status"] == "falhou"

    def test_reconcilers_leave_settled_rows_alone(self):
        db = _db()
        _viral(db, status="concluida")
        db.from_("cs_virais").update({"classificacao_status": "concluida"}).eq("id", "v1").execute()
        ing.reconcile_classificar(db, SimpleNamespace(payload={"viral_id": "v1"}))
        ing.reconcile_transcrever(db, SimpleNamespace(payload={"viral_id": "v1"}))
        v = _vstatus(db)
        assert v["classificacao_status"] == "concluida" and v["transcricao_status"] == "concluida"

    def test_handlers_and_reconcilers_are_registered_on_the_biblioteca_types(self):
        from app.modules.media_creation.services import geracao_jobs as gj

        ing.register_handlers()
        for t in gj.BIBLIOTECA_JOB_TYPES:
            assert gj.get_handler(t) is not None and gj.get_reconciler(t) is not None


class TestScheduler:
    def test_daily_sync_targets_only_active_auto_updated_profiles(self):
        db = _db(perfil_status="ativo")
        for pid, status in (("p2", "pausado"), ("p3", "ativo"), ("p4", "sem_conta")):
            db.from_("cs_perfis_monitorados").insert({"id": pid, "org_id": ORG, "handle": pid, "status": status}).execute()
        for rid, pid, auto in (("r1", PID, True), ("r2", "p2", True), ("r3", "p3", False), ("r4", "p4", True)):
            db.from_("cs_biblioteca_referencias").insert(
                {"id": rid, "org_id": ORG, "marca_id": "m", "modo": "perfil", "perfil_id": pid, "auto_atualizar": auto}
            ).execute()
        jobs = FakeJobRepository()
        n = anyio.run(lambda: sched.enqueue_daily_syncs(db, jobs, now=NOW))
        assert n == 1
        assert [j.payload for j in jobs._jobs.values()] == [{"perfil_id": PID}]
        assert anyio.run(lambda: sched.enqueue_daily_syncs(db, jobs, now=NOW)) == 1
        assert len(jobs._jobs) == 1  # same day: deduped

    def test_sweep_enqueues_classification_for_settled_transcriptions_only(self):
        db = _db()
        for vid, status in (("a", "concluida"), ("b", "na_fila"), ("c", "pendente"), ("d", "nao_aplicavel")):
            db.from_("cs_virais").insert({
                "id": vid, "org_id": ORG, "perfil_id": PID, "ig_media_id": vid, "e_viral": True,
                "transcricao_status": status, "classificacao_status": "pendente",
            }).execute()
        db.from_("cs_virais").insert({  # not viral: never classified
            "id": "e", "org_id": ORG, "perfil_id": PID, "ig_media_id": "e", "e_viral": False,
            "transcricao_status": "nao_aplicavel", "classificacao_status": "pendente",
        }).execute()
        jobs = FakeJobRepository()
        out = anyio.run(lambda: sched.sweep_pendentes(db, jobs, now=NOW))
        assert sorted(j.payload["viral_id"] for j in jobs._jobs.values()) == ["a", "d"]
        assert out["classificar"] == 2

    def test_sweep_settles_a_transcription_that_failed_without_the_hook(self):
        db = _db()
        for vid, tid in (("a", "t-failed"), ("b", "t-cancelled"), ("c", "t-live")):
            db.from_("cs_virais").insert({
                "id": vid, "org_id": ORG, "perfil_id": PID, "ig_media_id": vid, "e_viral": True,
                "transcricao_status": "na_fila", "transcricao_id": tid, "classificacao_status": "pendente",
            }).execute()
        for tid, st in (("t-failed", "falhou"), ("t-cancelled", "cancelada"), ("t-live", "na_fila")):
            db.from_("transcricoes").insert({"id": tid, "status": st}).execute()
        jobs = FakeJobRepository()
        out = anyio.run(lambda: sched.sweep_pendentes(db, jobs, now=NOW))
        by = {r["id"]: r["transcricao_status"] for r in _rows(db)}
        assert by == {"a": "falhou", "b": "falhou", "c": "na_fila"}
        assert out["transcricoes_falhas"] == 2

    def test_jobs_are_registered_at_import_time(self):
        sched.configure()  # idempotent
        assert sched.SYNC_CRON == "20 3 * * *"
