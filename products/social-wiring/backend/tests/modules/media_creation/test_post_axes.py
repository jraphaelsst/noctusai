"""CoreStudio post axes (S1): the rede x formato x assets matrix, assets read from the file, publication targets, 401s.

Real seams only: the module ``client`` fixture's mock Supabase, a ``FakeStorageBackend`` and a deterministic probe
injected through the router's DI seams (no patching of our own code). The event rows are written by the migration's
AFTER triggers (same transaction by construction), so they are asserted on the migration SQL, not on the mock.
"""
from __future__ import annotations

import asyncio
import shutil
import struct
import uuid
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.testing.migrations import migration_path

from app.dependencies import coerce_org_uuid
from app.modules.media_creation import post_formatos as pf
from app.modules.media_creation.post_formatos import AssetFato, validar_alvo
from app.modules.media_creation.routers import post_assets as pa_router
from app.modules.media_creation.services.post_assets_service import (
    MAX_BYTES,
    MIDIA_BUCKET,
    MidiaFato,
    PostAssetError,
    probe_midia,
)

ORG = str(coerce_org_uuid("test-org-123"))
BASE = "/api/media-creation/cs-posts"
_BACKEND = Path(__file__).resolve().parents[3]
SQL = migration_path(_BACKEND, "cs_post_axes").read_text(encoding="utf-8")


def _id() -> str:
    return str(uuid.uuid4())


def _codes(motivos):
    return [m.code for m in motivos]


V916 = AssetFato("video", "9:16", 30.0)
I11 = AssetFato("imagem", "1:1")


class TestMatrix:
    #: every (rede, formato) row of CORESTUDIO-STRUCTURE.md section 1.2
    VALIDOS = [
        ("instagram", "feed"), ("instagram", "carrossel"), ("instagram", "reel"), ("instagram", "story"),
        ("facebook", "feed"), ("facebook", "reel"), ("facebook", "story"),
        ("youtube", "short"), ("youtube", "video_longo"),
    ]
    INVALIDOS = [("youtube", "feed"), ("youtube", "carrossel"), ("youtube", "reel"), ("youtube", "story")]

    def test_matrix_covers_every_spec_row_and_nothing_else(self):
        assert sorted((r.rede, r.formato) for r in pf.MATRIZ) == sorted(self.VALIDOS)

    @pytest.mark.parametrize("rede,formato", INVALIDOS)
    def test_unlisted_pairs_are_invalid_for_the_network(self, rede, formato):
        assert _codes(validar_alvo(rede, formato, [V916])) == ["formato_invalido_para_rede"]

    def test_every_row_declares_verification_and_a_source(self):
        for r in pf.MATRIZ:
            assert r.verificacao in ("verified", "unverified") and r.fonte.startswith("https://"), r

    def test_unknown_axes_are_coded(self):
        assert _codes(validar_alvo("tiktok", "feed", [I11])) == ["rede_desconhecida"]
        assert _codes(validar_alvo("instagram", "live", [I11])) == ["formato_desconhecido"]

    def test_no_assets(self):
        assert _codes(validar_alvo("instagram", "reel", [])) == ["sem_assets"]

    def test_reel_needs_one_vertical_video(self):
        assert validar_alvo("instagram", "reel", [V916]) == []
        assert _codes(validar_alvo("instagram", "reel", [I11])) == ["tipo_midia_invalido", "proporcao_invalida"]
        assert _codes(validar_alvo("instagram", "reel", [V916, V916])) == ["composicao_invalida"]
        assert _codes(validar_alvo("instagram", "reel", [AssetFato("video", "9:16", 1000.0)])) == ["duracao_excedida"]

    def test_carousel_is_a_mixed_sequence_with_one_ratio(self):
        mix = [I11, AssetFato("video", "1:1", 10.0)]
        assert validar_alvo("instagram", "carrossel", mix) == []
        assert _codes(validar_alvo("instagram", "carrossel", [I11])) == ["composicao_invalida"]
        assert _codes(validar_alvo("instagram", "carrossel", [I11, AssetFato("imagem", "4:5")])) == ["proporcoes_mistas"]
        assert _codes(validar_alvo("instagram", "carrossel", [I11] * 11)) == ["composicao_invalida"]

    def test_feed_is_a_single_asset_but_facebook_feed_takes_a_sequence(self):
        assert validar_alvo("instagram", "feed", [I11]) == []
        assert _codes(validar_alvo("instagram", "feed", [I11, I11])) == ["composicao_invalida"]
        assert validar_alvo("facebook", "feed", [I11, AssetFato("video", "16:9", 5.0)]) == []

    def test_youtube_short_vs_long(self):
        assert validar_alvo("youtube", "short", [V916]) == []
        assert _codes(validar_alvo("youtube", "short", [AssetFato("video", "16:9", 30.0)])) == ["proporcao_invalida"]
        assert validar_alvo("youtube", "video_longo", [AssetFato("video", "16:9", 3000.0)]) == []
        assert _codes(validar_alvo("youtube", "video_longo", [V916])) == ["proporcao_invalida"]

    def test_aspect_buckets(self):
        c = pf.classificar_proporcao
        assert (c(1080, 1080), c(1080, 1350), c(1080, 1920), c(1920, 1080), c(1000, 700)) == ("1:1", "4:5", "9:16", "16:9", "outra")

    def test_public_matrix_has_every_row(self):
        assert len(pf.matriz_publica()) == len(pf.MATRIZ)


@pytest.fixture
def storage():
    return FakeStorageBackend()


class _Probe:
    """Deterministic media reader keyed by the stored key (a seam, not a patch)."""

    def __init__(self):
        self.fatos = {}

    def __call__(self, dados: bytes, filename: str) -> MidiaFato:
        if filename not in self.fatos:
            raise PostAssetError(422, {"code": "arquivo_ilegivel", "detail": "x"})
        return self.fatos[filename]


@pytest.fixture
def probe():
    return _Probe()


@pytest.fixture
def ax(client, storage, probe):
    app = client._tc.app
    app.dependency_overrides[pa_router.get_midia_storage] = lambda: storage
    app.dependency_overrides[pa_router.get_midia_probe] = lambda: probe
    app.dependency_overrides[pa_router.get_midia_stat] = lambda: (
        lambda bucket, key: len(storage._blobs[bucket][key][1]) if key in storage._blobs.get(bucket, {}) else None
    )
    sb = client.mock_supabase
    marca = _id()
    sb.from_("marcas").insert({"id": marca, "org_id": ORG, "name": "M"}).execute()
    client.post_id = _id()
    sb.from_("cs_posts").insert({"id": client.post_id, "org_id": ORG, "marca_id": marca, "titulo": "P"}).execute()
    client.conta_meta = _id()
    sb.from_("integration_accounts").insert({"id": client.conta_meta, "org_id": ORG, "provider": "meta"}).execute()
    client.conta_yt = _id()
    sb.from_("integration_accounts").insert({"id": client.conta_yt, "org_id": ORG, "provider": "youtube"}).execute()
    return client




def _put(client, storage, probe, name, fato, post_id=None):
    key = f"org/{ORG}/posts/{post_id or client.post_id}/saidas/{name}"
    cab = b"\x89PNG\r\n\x1a\n" if name.endswith(".png") else b"\x00\x00\x00\x18ftypmp42"
    asyncio.run(storage.put(bucket=MIDIA_BUCKET, key=key, data=cab + b"x" * 10, content_type="video/mp4"))
    probe.fatos[key] = fato
    return key


def _registrar(client, key, **extra):
    return client.post(f"{BASE}/{client.post_id}/assets", json={"storage_path": key, **extra})


def _amanha():
    return (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()


class TestAssets:
    def test_kind_ratio_and_duration_come_from_the_file(self, ax, storage, probe):
        key = _put(ax, storage, probe, "a.mp4", MidiaFato("video", 1080, 1920, 12.5))
        r = _registrar(ax, key)
        assert r.status_code == 201, r.text
        d = r.json()["data"]
        assert (d["tipo_midia"], d["proporcao"], float(d["duracao_s"]), d["ordem"], d["versao"]) == ("video", "9:16", 12.5, 1, 1)
        assert d["criado_por"] and d["status"] == "pronto"

    def test_body_cannot_assert_file_facts(self, ax, storage, probe):
        key = _put(ax, storage, probe, "a.mp4", MidiaFato("video", 1080, 1920, 12.5))
        assert _registrar(ax, key, proporcao="1:1").status_code == 422

    def test_same_ordem_is_a_new_version_and_current_set_is_the_top(self, ax, storage, probe):
        k1 = _put(ax, storage, probe, "a.png", MidiaFato("imagem", 1080, 1080, None))
        k2 = _put(ax, storage, probe, "b.png", MidiaFato("imagem", 1080, 1350, None))
        assert _registrar(ax, k1, ordem=1).json()["data"]["versao"] == 1
        assert _registrar(ax, k2, ordem=1).json()["data"]["versao"] == 2
        atuais = ax.get(f"{BASE}/{ax.post_id}/assets").json()["data"]
        assert [(a["ordem"], a["versao"]) for a in atuais] == [(1, 2)]
        assert len(ax.get(f"{BASE}/{ax.post_id}/assets?historico=true").json()["data"]) == 2

    def test_foreign_path_is_refused(self, ax, storage, probe):
        key = _put(ax, storage, probe, "a.mp4", MidiaFato("video", 1080, 1920, 5.0), post_id=_id())
        r = _registrar(ax, key)
        assert r.status_code == 422 and "caminho_invalido" in r.text

    def test_oversized_object_is_413_without_reading_it(self, ax, storage, probe, monkeypatch):
        key = _put(ax, storage, probe, "a.mp4", MidiaFato("video", 1080, 1920, 5.0))
        # the stat seam reports a size over the limit (metadata only); the Fake's get must never be reached
        ax._tc.app.dependency_overrides[pa_router.get_midia_stat] = lambda: (lambda bucket, k: MAX_BYTES + 1)

        async def _nao_ler(**_):
            raise AssertionError("storage.get must not be called for an oversized object")

        monkeypatch.setattr(storage, "get", _nao_ler)
        r = _registrar(ax, key)
        assert r.status_code == 413 and "arquivo_grande_demais" in r.text

    def test_header_bytes_must_match_the_extension(self, ax, storage, probe):
        key = f"org/{ORG}/posts/{ax.post_id}/saidas/a.png"
        asyncio.run(storage.put(bucket=MIDIA_BUCKET, key=key, data=b"not a png at all", content_type="image/png"))
        probe.fatos[key] = MidiaFato("imagem", 10, 10, None)
        r = _registrar(ax, key)
        assert r.status_code == 422 and "tipo_arquivo_inconsistente" in r.text

    def test_missing_blob(self, ax):
        key = f"org/{ORG}/posts/{ax.post_id}/saidas/nada.mp4"
        r = _registrar(ax, key)
        assert r.status_code == 422 and "arquivo_nao_encontrado" in r.text

    def test_unreadable_file_is_422(self, ax, storage, probe):
        key = f"org/{ORG}/posts/{ax.post_id}/saidas/lixo.mp4"
        asyncio.run(storage.put(bucket=MIDIA_BUCKET, key=key, data=b"\x00\x00\x00\x18ftypmp42", content_type="video/mp4"))
        r = _registrar(ax, key)
        assert r.status_code == 422 and "arquivo_ilegivel" in r.text

    def test_foreign_org_post_is_404(self, ax):
        pid = _id()
        ax.mock_supabase.from_("cs_posts").insert({"id": pid, "org_id": _id(), "marca_id": _id(), "titulo": "x"}).execute()
        assert ax.get(f"{BASE}/{pid}/assets").status_code == 404

    def test_status_update_stamps_the_actor(self, ax, storage, probe):
        key = _put(ax, storage, probe, "a.mp4", MidiaFato("video", 1080, 1920, 5.0))
        aid = _registrar(ax, key).json()["data"]["id"]
        r = ax.patch(f"{BASE}/{ax.post_id}/assets/{aid}", json={"status": "aprovado"})
        assert r.status_code == 200 and r.json()["data"]["status"] == "aprovado" and r.json()["data"]["atualizado_por"]


class TestPublicacoes:
    def _reel_ready(self, ax, storage, probe):
        key = _put(ax, storage, probe, "a.mp4", MidiaFato("video", 1080, 1920, 20.0))
        assert _registrar(ax, key).status_code == 201
        return key

    def _criar(self, ax, **kw):
        body = {"rede": "instagram", "formato": "reel", "conta_id": ax.conta_meta, "publicar_em": _amanha(), **kw}
        return ax.post(f"{BASE}/{ax.post_id}/publicacoes", json=body)

    def test_valid_target_is_created_with_the_asset_set_snapshot(self, ax, storage, probe):
        self._reel_ready(ax, storage, probe)
        r = self._criar(ax)
        assert r.status_code == 201, r.text
        d = r.json()["data"]
        assert (d["rede"], d["formato"], d["status"], d["origem"]) == ("instagram", "reel", "agendado", "app")
        assert len(d["assets_ids"]) == 1 and d["criado_por"]

    def test_invalid_target_is_422_with_a_coded_reason(self, ax, storage, probe):
        self._reel_ready(ax, storage, probe)
        r = self._criar(ax, rede="youtube", formato="story", conta_id=ax.conta_yt)
        assert r.status_code == 422 and "formato_invalido_para_rede" in r.text
        r = self._criar(ax, formato="carrossel")
        assert r.status_code == 422 and "composicao_invalida" in r.text

    def test_post_without_assets_is_422_sem_assets(self, ax):
        r = self._criar(ax)
        assert r.status_code == 422 and "sem_assets" in r.text

    def test_account_must_match_the_network_provider(self, ax, storage, probe):
        self._reel_ready(ax, storage, probe)
        r = self._criar(ax, conta_id=ax.conta_yt)
        assert r.status_code == 422 and "conta_invalida" in r.text

    def test_past_schedule_and_duplicate_are_refused(self, ax, storage, probe):
        self._reel_ready(ax, storage, probe)
        passado = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        assert "publicar_em_no_passado" in self._criar(ax, publicar_em=passado).text
        assert self._criar(ax).status_code == 201
        r = self._criar(ax)
        assert r.status_code == 409 and "alvo_duplicado" in r.text

    def test_reprovada_media_blocks_scheduling(self, ax, storage, probe):
        key = _put(ax, storage, probe, "a.mp4", MidiaFato("video", 1080, 1920, 20.0))
        aid = _registrar(ax, key).json()["data"]["id"]
        ax.patch(f"{BASE}/{ax.post_id}/assets/{aid}", json={"status": "reprovado"})
        assert "midia_reprovada" in self._criar(ax).text

    def test_reschedule_and_cancel_stamp_the_actor(self, ax, storage, probe):
        self._reel_ready(ax, storage, probe)
        pid = self._criar(ax).json()["data"]["id"]
        nova = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        r = ax.patch(f"{BASE}/{ax.post_id}/publicacoes/{pid}", json={"publicar_em": nova})
        assert r.status_code == 200 and r.json()["data"]["atualizado_por"]
        r = ax.patch(f"{BASE}/{ax.post_id}/publicacoes/{pid}", json={"status": "cancelado"})
        assert r.json()["data"]["status"] == "cancelado"
        assert ax.patch(f"{BASE}/{ax.post_id}/publicacoes/{pid}", json={"status": "cancelado"}).status_code == 409

    def test_cannot_set_publicado_from_the_api(self, ax):
        r = ax.patch(f"{BASE}/{ax.post_id}/publicacoes/{_id()}", json={"status": "publicado"})
        assert r.status_code == 422


class TestMatrixEndpoint:
    def test_returns_every_row(self, client):
        r = client.get(f"{BASE}/formatos")
        assert r.status_code == 200
        assert len(r.json()["data"]) == len(pf.MATRIZ)


class TestAuth:
    @pytest.mark.parametrize(
        "method,path,kw",
        [
            ("get", f"{BASE}/formatos", {}),
            ("get", f"{BASE}/{uuid.uuid4()}/assets", {}),
            ("post", f"{BASE}/{uuid.uuid4()}/assets", {"json": {"storage_path": "x"}}),
            ("patch", f"{BASE}/{uuid.uuid4()}/assets/{uuid.uuid4()}", {"json": {"status": "pronto"}}),
            ("get", f"{BASE}/{uuid.uuid4()}/publicacoes", {}),
            ("post", f"{BASE}/{uuid.uuid4()}/publicacoes", {"json": {"rede": "instagram", "formato": "reel", "conta_id": "c", "publicar_em": "2030-01-01T00:00:00Z"}}),
            ("patch", f"{BASE}/{uuid.uuid4()}/publicacoes/{uuid.uuid4()}", {"json": {"status": "cancelado"}}),
        ],
    )
    def test_unauthenticated_is_401(self, client, method, path, kw):
        r = getattr(client._tc, method)(path, **kw)
        assert r.status_code == 401, (method, path, r.status_code, r.text)


class TestMigration:
    def test_three_tables_each_with_a_declared_tier(self):
        for t in ("cs_post_assets", "cs_post_publicacoes", "cs_post_eventos"):
            assert f"COMMENT ON TABLE social_wiring.{t} IS 'tier:org'" in SQL

    def test_events_are_written_by_triggers_in_the_same_transaction(self):
        assert "AFTER INSERT OR UPDATE ON social_wiring.cs_post_assets" in SQL
        assert "AFTER INSERT OR UPDATE ON social_wiring.cs_post_publicacoes" in SQL
        for tipo in ("midia_versao_criada", "publicacao_agendada", "publicacao_reagendada", "publicado", "publicacao_cancelada"):
            assert f"'{tipo}'" in SQL

    def test_eventos_is_append_only(self):
        assert "BEFORE UPDATE OR DELETE ON social_wiring.cs_post_eventos" in SQL
        assert "GRANT SELECT, INSERT ON TABLE social_wiring.cs_post_eventos TO service_role" in SQL

    def test_no_browser_grants_and_old_formato_is_deprecated_not_dropped(self):
        assert "FROM PUBLIC, anon, authenticated, service_role" in SQL
        assert "DEPRECATED" in SQL and "DROP COLUMN" not in SQL.upper()

    def test_the_bucket_has_size_and_mime_limits(self):
        assert "file_size_limit" in SQL and "524288000" in SQL
        for m in ("image/jpeg", "image/png", "image/webp", "image/heic", "video/mp4", "video/quicktime"):
            assert f"'{m}'" in SQL

    def test_the_bucket_is_private(self):
        assert "VALUES ('sw-posts-midia', 'sw-posts-midia', false," in SQL


def _png(w: int, h: int) -> bytes:
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\x00\x00\x00" * w for _ in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe not installed")
class TestRealProbe:
    def test_image_dimensions_are_read_from_the_bytes(self):
        f = probe_midia(_png(108, 135), "a.png")
        assert (f.tipo_midia, f.largura, f.altura, f.duracao_s) == ("imagem", 108, 135, None)
        assert pf.classificar_proporcao(f.largura, f.altura) == "4:5"

    def test_garbage_and_wrong_extension_are_422(self):
        with pytest.raises(PostAssetError) as e:
            probe_midia(b"not an image", "a.png")
        assert e.value.status == 422 and e.value.detail["code"] == "arquivo_ilegivel"
        with pytest.raises(PostAssetError) as e:
            probe_midia(b"x", "a.exe")
        assert e.value.detail["code"] == "tipo_arquivo_nao_suportado"
