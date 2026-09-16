"""Consumer-surface additions the first consumer's routes need (SW W2):
batch listing, settings writes, and the bucket-backed ``PhotoStorage``.

In-memory semantics plus the Supabase implementation against
``MockSupabaseClient(validate_schema=True)`` — every column is checked
against the real social-wiring migrations."""

from __future__ import annotations

from decimal import Decimal

import pytest

from noctusai_lib.domain.photo_editing import (
    BucketPhotoStorage,
    InMemoryPhotoEditingRepository,
    PhotoStorage,
    RepositoryError,
    Speed,
    SupabasePhotoEditingRepository,
)
from noctusai_lib.domain.photo_editing.types import EditType, OrgSettings
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.testing import MockSupabaseResponse

from .conftest import ORG, USER, Clock, run
from .test_repository import SchemaStableClient

OTHER_ORG = "00000000-0000-4000-8000-00000000beef"
OTHER_USER = "00000000-0000-4000-8000-00000000cafe"


async def _three_batches(repo) -> list:
    made = []
    for nome, org, who in (("a", ORG, USER), ("b", ORG, OTHER_USER), ("c", OTHER_ORG, USER)):
        made.append(
            await repo.create_batch(
                org_id=org, nome=nome, criado_por=who, origem="upload", velocidade=Speed.URGENTE
            )
        )
    return made


def test_in_memory_list_batches_scopes_and_pages() -> None:
    async def scenario() -> None:
        repo = InMemoryPhotoEditingRepository(now=Clock())
        a, b, _c = await _three_batches(repo)
        page, total = await repo.list_batches(org_id=ORG)
        assert total == 2 and [x.id for x in page] == [b.id, a.id]  # newest first
        own, total_own = await repo.list_batches(org_id=ORG, criado_por=USER)
        assert total_own == 1 and [x.id for x in own] == [a.id]
        second, total = await repo.list_batches(org_id=ORG, limit=1, offset=1)
        assert total == 2 and [x.id for x in second] == [a.id]

    run(scenario())


def test_in_memory_settings_writes() -> None:
    async def scenario() -> None:
        repo = InMemoryPhotoEditingRepository()
        saved = await repo.save_org_settings(
            OrgSettings(org_id=ORG, tipos_edicao_ativos=(EditType.CEU,), modelo_editor_id="m")
        )
        assert (await repo.get_org_settings(ORG)) == saved
        platform = await repo.update_platform_settings(notificacoes_globais_ativas=False)
        assert platform.notificacoes_globais_ativas is False
        with pytest.raises(ValueError, match="not updatable"):
            await repo.update_platform_settings(id=2)

    run(scenario())


def test_supabase_list_batches_filters_rows() -> None:
    async def scenario() -> None:
        client = SchemaStableClient()
        repo = SupabasePhotoEditingRepository(client, now=Clock())
        await _three_batches(repo)
        page, _total = await repo.list_batches(org_id=ORG, criado_por=USER, limit=10)
        assert [(b.org_id, b.criado_por, b.nome) for b in page] == [(ORG, USER, "a")]

    run(scenario())


def test_supabase_list_batches_reads_exact_count() -> None:
    """``total`` is PostgREST's exact count, not the page length. (The mock's
    own ``count="exact"`` ignores filters, so the response is queued.)"""

    async def scenario() -> None:
        client = SchemaStableClient()
        client.sw("fotos_lotes").set_responses(
            [MockSupabaseResponse(
                data=[{"id": "l-9", "org_id": ORG, "nome": "z", "criado_por": USER,
                       "origem": "vista", "velocidade": "urgente", "status": "pronto",
                       "created_at": "2026-09-16T10:00:00Z"}],
                count=37,
            )]
        )
        repo = SupabasePhotoEditingRepository(client, now=Clock())
        page, total = await repo.list_batches(org_id=ORG, limit=1, offset=5)
        assert total == 37
        assert [b.id for b in page] == ["l-9"] and page[0].created_at is not None

    run(scenario())


def test_supabase_save_org_settings_upserts_enum_literals() -> None:
    async def scenario() -> None:
        client = SchemaStableClient()
        # The mock's upsert does not persist or echo (a documented mock gap),
        # so the representation PostgREST returns is queued.
        client.sw("fotos_org_settings").set_responses(
            [MockSupabaseResponse(data=[{
                "org_id": ORG, "tipos_edicao_ativos": ["cor_luz", "ceu"],
                "modelo_editor_id": "gpt-image-2.5-sunburst", "velocidade_override": "urgente",
                "limite_fotos_por_lote": 100, "limite_bytes_por_foto": 26214400,
                "notificacoes_ativas": True,
            }])]
        )
        repo = SupabasePhotoEditingRepository(client, now=Clock())
        saved = await repo.save_org_settings(
            OrgSettings(
                org_id=ORG,
                tipos_edicao_ativos=(EditType.COR_LUZ, EditType.CEU),
                modelo_editor_id="gpt-image-2.5-sunburst",
                velocidade_override=Speed.URGENTE,
            )
        )
        assert saved.tipos_edicao_ativos == (EditType.COR_LUZ, EditType.CEU)
        assert saved.velocidade_override is Speed.URGENTE
        assert saved.modelo_editor_id == "gpt-image-2.5-sunburst"

    run(scenario())


def test_supabase_update_platform_settings() -> None:
    async def scenario() -> None:
        client = SchemaStableClient()
        client.sw("fotos_platform_settings")  # materialize the scoped table
        client.schema("social_wiring").set_table_data(
            "fotos_platform_settings",
            [{"id": 1, "velocidade_default": "urgente", "notificacoes_globais_ativas": True,
              "preco_storage_gb_mes_usd": None}],
        )
        repo = SupabasePhotoEditingRepository(client, now=Clock())
        updated = await repo.update_platform_settings(preco_storage_gb_mes_usd=Decimal("0.021"))
        assert updated.preco_storage_gb_mes_usd == Decimal("0.021")
        with pytest.raises(ValueError, match="not updatable"):
            await repo.update_platform_settings(id=2)

    run(scenario())


def test_supabase_update_platform_settings_requires_singleton() -> None:
    async def scenario() -> None:
        repo = SupabasePhotoEditingRepository(SchemaStableClient(), now=Clock())
        with pytest.raises(RepositoryError):
            await repo.update_platform_settings(notificacoes_globais_ativas=False)

    run(scenario())


def test_bucket_photo_storage_round_trip() -> None:
    async def scenario() -> None:
        backend = FakeStorageBackend()
        storage = BucketPhotoStorage(backend, bucket="fotos")
        assert isinstance(storage, PhotoStorage)
        await storage.put("o/l/f/original.jpg", b"jpeg", content_type="image/jpeg")
        assert await storage.get("o/l/f/original.jpg") == b"jpeg"
        blob = await backend.get(bucket="fotos", key="o/l/f/original.jpg")
        assert blob is not None and blob.metadata.content_type == "image/jpeg"
        assert "o/l/f/original.jpg" in await storage.signed_url("o/l/f/original.jpg")
        await storage.delete("o/l/f/original.jpg")
        with pytest.raises(FileNotFoundError, match="fotos/o/l/f/original.jpg"):
            await storage.get("o/l/f/original.jpg")

    run(scenario())


def test_bucket_photo_storage_requires_bucket() -> None:
    with pytest.raises(ValueError):
        BucketPhotoStorage(FakeStorageBackend(), bucket="")


def test_in_memory_id_factory_mints_consumer_ids() -> None:
    async def scenario() -> None:
        minted: list[str] = []

        def factory(kind: str) -> str:
            minted.append(kind)
            return f"00000000-0000-4000-8000-{len(minted):012d}"

        repo = InMemoryPhotoEditingRepository(id_factory=factory)
        batch = await repo.create_batch(
            org_id=ORG, nome="n", criado_por=USER, origem="upload", velocidade=Speed.URGENTE
        )
        photo = await repo.add_photo(org_id=ORG, lote_id=batch.id, ordem=1, storage_path_original="x")
        assert batch.id == "00000000-0000-4000-8000-000000000001"
        assert photo.id == "00000000-0000-4000-8000-000000000002"
        assert minted == ["lote", "foto"]

    run(scenario())
