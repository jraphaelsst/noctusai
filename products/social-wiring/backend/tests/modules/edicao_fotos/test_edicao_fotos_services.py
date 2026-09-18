"""Unit tests for the module's services: Vista ordering/extension, the
in-app notifier, the worker flag, the ports wiring and the error map."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from noctusai_lib.domain.photo_editing import (
    BatchReadyNotice,
    BucketPhotoStorage,
    InMemoryPhotoEditingRepository,
    OrgSettings,
    PhotoEditingPorts,
    SubmissionError,
)
from noctusai_lib.domain.real_estate.imovel import ImovelFoto
from noctusai_lib.integrations.quota import DefaultingQuotaTracker
from noctusai_lib.testing import MockSupabaseClient

from app.modules.edicao_fotos.errors import engine_error
from app.modules.edicao_fotos.services import ports as ports_service
from app.modules.edicao_fotos.services import worker as worker_service
from app.modules.edicao_fotos.services.notifier import InAppBatchReadyNotifier
from app.modules.edicao_fotos.services.vista_fotos import (
    RealVistaPhotoSource,
    VistaFotoDownloadError,
    extension_for,
    ordered_gallery,
)

ORG = "00000000-0000-4000-8000-00000000000a"
USER = "00000000-0000-4000-8000-00000000000b"


def _notice() -> BatchReadyNotice:
    return BatchReadyNotice(
        lote_id="l1", org_id=ORG, criado_por=USER, nome="Casa", total_fotos=3,
        aguardando_decisao=2, falhou=1,
    )


# --- vista -------------------------------------------------------------------


def test_ordered_gallery_destaque_then_numeric_code() -> None:
    fotos = [
        ImovelFoto(codigo="10", url="u10"),
        ImovelFoto(codigo="2", url="u2"),
        ImovelFoto(codigo="abc", url="uabc"),
        ImovelFoto(codigo="5", url="u5", destaque=True),
        ImovelFoto(codigo="1", url=None),
    ]
    assert [f.codigo for f in ordered_gallery(fotos)] == ["5", "2", "10", "abc"]


@pytest.mark.parametrize(
    "url,ctype,ext",
    [
        ("https://cdn/x/foto.JPG", None, "jpg"),
        ("https://cdn/x/foto?id=1", "image/png; charset=binary", "png"),
        ("https://cdn/x/foto.php", "image/webp", "webp"),
    ],
)
def test_extension_for(url, ctype, ext) -> None:
    assert extension_for(url, ctype) == ext


def test_extension_for_unknown_is_an_error() -> None:
    with pytest.raises(VistaFotoDownloadError):
        extension_for("https://cdn/x/foto", "text/html")


def _source(handler) -> RealVistaPhotoSource:
    adapter = SimpleNamespace()
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return RealVistaPhotoSource(adapter, http_client=client)


def test_real_source_fetch_ok_and_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ok.jpg":
            return httpx.Response(200, content=b"img", headers={"content-type": "image/jpeg"})
        if request.url.path == "/big.jpg":
            return httpx.Response(200, content=b"x" * (27 * 1024 * 1024))
        return httpx.Response(404)

    source = _source(handler)
    assert asyncio.run(source.fetch("https://cdn.test/ok.jpg")) == (b"img", "jpg")
    with pytest.raises(VistaFotoDownloadError, match="HTTP 404"):
        asyncio.run(source.fetch("https://cdn.test/missing.jpg"))
    with pytest.raises(VistaFotoDownloadError, match="grande"):
        asyncio.run(source.fetch("https://cdn.test/big.jpg"))
    with pytest.raises(VistaFotoDownloadError, match="inválida"):
        asyncio.run(source.fetch("file:///etc/passwd"))


def test_real_source_network_error_is_named() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(VistaFotoDownloadError, match="ConnectError"):
        asyncio.run(_source(handler).fetch("https://cdn.test/a.jpg"))


def test_real_source_lists_through_the_seed_adapter() -> None:
    async def list_imovel_fotos(codigo):
        return [ImovelFoto(codigo="1", url=f"https://cdn/{codigo}.jpg")]

    source = RealVistaPhotoSource(SimpleNamespace(list_imovel_fotos=list_imovel_fotos))
    assert asyncio.run(source.list_photos("CA1"))[0].url == "https://cdn/CA1.jpg"


# --- notifier -----------------------------------------------------------------


def _notifier(repo):
    core = MockSupabaseClient(schema="social_wiring")
    return core, InAppBatchReadyNotifier(core_client=lambda: core, repo=repo)


def test_notifier_writes_the_creators_in_app_row() -> None:
    repo = InMemoryPhotoEditingRepository()
    core, notifier = _notifier(repo)
    asyncio.run(notifier.batch_ready(_notice()))
    [row] = core.table("notifications").inserted_payloads
    assert row["user_id"] == USER and row["org_id"] == ORG and row["type"] == "system"
    assert "Casa" in row["title"] and "1 foto(s) falharam" in row["message"]
    assert row["metadata"]["link"] == "/edicao-fotos/lotes/l1/revisao"


def test_notifier_honours_both_switches() -> None:
    repo = InMemoryPhotoEditingRepository()
    core, notifier = _notifier(repo)
    repo.seed_org_settings(OrgSettings(org_id=ORG, notificacoes_ativas=False))
    asyncio.run(notifier.batch_ready(_notice()))
    asyncio.run(repo.save_org_settings(OrgSettings(org_id=ORG)))
    asyncio.run(repo.update_platform_settings(notificacoes_globais_ativas=False))
    asyncio.run(notifier.batch_ready(_notice()))
    assert core.table("notifications").inserted_payloads == []


def test_notifier_failure_propagates_for_the_retry() -> None:
    class Broken:
        def table(self, _name):
            raise RuntimeError("core down")

    notifier = InAppBatchReadyNotifier(core_client=lambda: Broken(), repo=InMemoryPhotoEditingRepository())
    with pytest.raises(RuntimeError, match="core down"):
        asyncio.run(notifier.batch_ready(_notice()))


# --- worker flag ----------------------------------------------------------------


def test_kill_switch_defaults_on_and_still_stops_the_worker() -> None:
    """W8: the env flag is the hard kill switch and defaults ON (the worker
    is built and waits on `processamento_ativo`); false keeps it from
    starting at all, and the status says why."""
    from app.config import SocialWiringSettings

    assert SocialWiringSettings.model_fields["edicao_fotos_worker_enabled"].default is True
    cfg = SimpleNamespace(edicao_fotos_worker_enabled=False)
    assert asyncio.run(worker_service.start_worker(cfg)) is False
    assert worker_service.is_running() is False
    status = worker_service.status()
    assert status.kill_switch_ativo is False and status.rodando is False
    assert "EDICAO_FOTOS_WORKER_ENABLED" in (status.motivo_parado or "")
    asyncio.run(worker_service.stop_worker())  # no-op when never started


def test_worker_id_is_process_unique() -> None:
    assert worker_service.worker_id().startswith("sw-edicao-fotos-")


# --- ports wiring ---------------------------------------------------------------


def test_build_ports_wires_real_adapters(override_settings, client) -> None:
    from app.config import settings

    ports = ports_service.build_ports(settings)
    assert isinstance(ports, PhotoEditingPorts)
    assert isinstance(ports.storage, BucketPhotoStorage)
    assert ports.storage.bucket == ports_service.BUCKET_FOTOS == "edicao-fotos"
    assert type(ports.repo).__name__ == "SupabasePhotoEditingRepository"
    assert type(ports.jobs).__name__ == "RealSupabaseJobRepository"
    assert type(ports.fx).__name__ == "BcbPtaxAdapter"
    assert type(ports.imaging).__name__ == "RealImagingAdapter"
    assert type(ports.llm).__name__ == "LlmStructuredAdapter"
    assert isinstance(ports.edit_quota, DefaultingQuotaTracker)
    assert ports.edit_quota.default.cap == settings.edicao_fotos_edicoes_por_dia
    assert type(ports.notifier).__name__ == "MultiChannelBatchReadyNotifier"


def test_image_edit_factory_refuses_without_a_key(client) -> None:
    from noctusai_lib.domain.photo_editing import openai_image_edit_factory
    from noctusai_lib.integrations.image_edit import ImageEditNotConfigured

    factory = openai_image_edit_factory(lambda _org: None)
    with pytest.raises(ImageEditNotConfigured):
        factory(ORG, "gpt-image-2.5-sunburst")


def test_memory_quota_when_no_redis_url() -> None:
    cfg = SimpleNamespace(edicao_fotos_edicoes_por_dia=2, redis_url="")
    quota = ports_service.build_edit_quota(cfg)

    async def run():
        return [(await quota.consume(key=f"fotos.edit:{ORG}")).allowed for _ in range(3)]

    assert asyncio.run(run()) == [True, True, False]


# --- error map ------------------------------------------------------------------


@pytest.mark.parametrize(
    "code,status",
    [("lote_ja_submetido", 409), ("arquivo_grande_demais", 413), ("formato_nao_suportado", 415),
     ("modelo_nao_configurado", 422)],
)
def test_submission_errors_map_to_statuses(code, status) -> None:
    exc = engine_error(SubmissionError(code, "m"))
    assert exc.status_code == status and exc.detail == {"detail": "m", "code": code}


def test_unknown_errors_are_not_relabelled() -> None:
    with pytest.raises(KeyError):
        engine_error(KeyError("x"))
