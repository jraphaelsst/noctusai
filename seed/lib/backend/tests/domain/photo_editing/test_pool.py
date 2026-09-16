"""Reference pool + manual guide rebuild (contract §5–§6).

Pair limit counted in pairs (None/0 = unlimited, archived never count),
archive-not-delete, normalization before storage, cleanup on a refused
insert, the debounced rebuild on every pool change, and the manual rebuild
that skips the debounce. DI only — ports built from fakes."""

from __future__ import annotations

import dataclasses

import pytest

from noctusai_lib.domain.photo_editing import (
    GuideStatus,
    InMemoryPhotoEditingRepository,
    InMemoryPhotoStorage,
    JobType,
    PoolEmptyError,
    PoolFullError,
    ReferenceImageError,
    ReferenceNotFoundError,
    ReferenceStorageNotConfigured,
    Room,
    add_reference_pair,
    archive_reference_pair,
    handle_regen_guia,
    pool_status,
    request_guide_regen,
)
from noctusai_lib.domain.photo_editing.guide import generate_draft_from_pool, reference_images
from noctusai_lib.integrations.imaging import UnsupportedImageFormatError

from .conftest import USER, run

JPEG = b"\xff\xd8\xff\xe0jpeg"


@pytest.fixture
def pool_ports(ports):
    return dataclasses.replace(ports, reference_storage=InMemoryPhotoStorage())


async def _add(ports, **overrides):
    kwargs = dict(
        antes=JPEG, depois=JPEG, comodo="sala", tipos_edicao=["ceu", "ceu", "cor_luz"],
        nota="  céu limpo  ", criado_por=USER,
    )
    kwargs.update(overrides)
    return await add_reference_pair(ports, **kwargs)


def _regen_jobs(ports):
    return [j for j in ports.jobs._jobs.values() if j.type == JobType.REGEN_GUIA]


class StalePreCheckRepository(InMemoryPhotoEditingRepository):
    """The pre-check count reads 0 once — what a concurrent writer that
    filled the pool between the check and the insert looks like. The
    insert itself still enforces the limit (as migration 129 does)."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.stale_reads = 0

    async def count_active_references(self) -> int:
        if self.stale_reads:
            self.stale_reads -= 1
            return 0
        return await super().count_active_references()


def test_add_stores_normalized_bytes_under_keys_and_schedules_rebuild(pool_ports) -> None:
    async def scenario() -> None:
        pair = await _add(pool_ports)
        assert pair.comodo is Room.SALA
        assert [t.value for t in pair.tipos_edicao] == ["ceu", "cor_luz"]  # deduped, ordered
        assert pair.nota == "céu limpo"
        storage = pool_ports.reference_storage
        for key in (pair.antes_url, pair.depois_url):
            assert key.startswith("referencias/") and key.endswith(".jpg")
            data, content_type = storage.objects[key]
            assert content_type == "image/jpeg" and data
        assert storage.objects[pair.antes_url][0] != JPEG  # the normalized copy, not the raw upload
        jobs = _regen_jobs(pool_ports)
        assert len(jobs) == 1 and jobs[0].scheduled_for is not None  # debounced

    run(scenario())


def test_limit_counts_active_pairs_only_and_zero_is_unlimited(pool_ports) -> None:
    async def scenario() -> None:
        repo = pool_ports.repo
        await repo.update_platform_settings(limite_pares_referencia=2)
        first = await _add(pool_ports)
        await _add(pool_ports)
        assert (await pool_status(pool_ports)).cheio
        with pytest.raises(PoolFullError) as exc:
            await _add(pool_ports)
        assert exc.value.code == "pool_cheio"
        await archive_reference_pair(pool_ports, first.id)
        status = await pool_status(pool_ports)
        assert (status.pares_ativos, status.limite_pares, status.cheio) == (1, 2, False)
        await _add(pool_ports)  # the archived pair freed a slot
        for unlimited in (0, None):
            await repo.update_platform_settings(limite_pares_referencia=unlimited)
            assert (await pool_status(pool_ports)).limite_pares is None
            await _add(pool_ports)

    run(scenario())


def test_refused_write_leaves_no_objects_behind(pool_ports, clock) -> None:
    async def scenario() -> None:
        repo = StalePreCheckRepository(now=clock)
        ports = dataclasses.replace(pool_ports, repo=repo)
        await _add(ports)
        await repo.update_platform_settings(limite_pares_referencia=1)
        before = dict(ports.reference_storage.objects)
        repo.stale_reads = 1
        with pytest.raises(PoolFullError):
            await _add(ports)
        assert ports.reference_storage.objects == before

    run(scenario())


def test_input_validation(pool_ports, ports) -> None:
    async def scenario() -> None:
        with pytest.raises(ReferenceStorageNotConfigured):
            await _add(ports)  # no reference_storage wired
        with pytest.raises(ReferenceImageError) as empty:
            await _add(pool_ports, depois=b"")
        assert empty.value.code == "arquivo_vazio"
        with pytest.raises(ReferenceImageError) as big:
            await _add(pool_ports, antes=b"x" * 11, max_bytes=10)
        assert big.value.code == "arquivo_grande_demais"
        with pytest.raises(ValueError):
            await _add(pool_ports, comodo="garagem")  # not in the fixed room list
        assert pool_ports.reference_storage.objects == {}

    run(scenario())


def test_undecodable_image_is_refused_before_storage(pool_ports) -> None:
    class RefusingImaging:
        backend = "refusing"

        def normalize_for_edit(self, image_bytes: bytes):
            raise UnsupportedImageFormatError("not an image")

    ports = dataclasses.replace(pool_ports, imaging=RefusingImaging())
    with pytest.raises(UnsupportedImageFormatError):
        run(_add(ports))
    assert pool_ports.reference_storage.objects == {}


def test_archive_is_idempotent_and_404s_unknown(pool_ports) -> None:
    async def scenario() -> None:
        pair = await _add(pool_ports)
        archived = await archive_reference_pair(pool_ports, pair.id)
        assert archived.arquivado_em is not None
        jobs_after_first = len(pool_ports.jobs._jobs)
        again = await archive_reference_pair(pool_ports, pair.id)
        assert again.arquivado_em == archived.arquivado_em
        assert len(pool_ports.jobs._jobs) == jobs_after_first  # nothing rescheduled
        with pytest.raises(ReferenceNotFoundError):
            await archive_reference_pair(pool_ports, "nope")
        # History is kept: listed with the archived ones, gone from the active list.
        page, total = await pool_ports.repo.list_references(include_archived=True)
        assert total == 1 and page[0].id == pair.id
        assert (await pool_ports.repo.list_references())[1] == 0

    run(scenario())


def test_guide_builder_sends_the_stored_bytes(pool_ports) -> None:
    async def scenario() -> None:
        pair = await _add(pool_ports)
        images = await reference_images(pool_ports, [pair])
        assert len(images) == 2 and all(isinstance(i, bytes) and i for i in images)
        draft = await generate_draft_from_pool(pool_ports)
        assert draft.status is GuideStatus.RASCUNHO
        assert pool_ports.llm.calls[-1]["images"] == images
        pool_ports.reference_storage.objects.pop(pair.antes_url)
        with pytest.raises(FileNotFoundError):
            await reference_images(pool_ports, [pair])  # never a partial pool

    run(scenario())


def test_manual_rebuild_runs_now_and_refuses_an_empty_pool(pool_ports) -> None:
    async def scenario() -> None:
        with pytest.raises(PoolEmptyError) as exc:
            await request_guide_regen(pool_ports, requested_by=USER)
        assert exc.value.code == "pool_vazio"
        await _add(pool_ports)  # pool changed JUST now: the automatic run would wait
        job = await request_guide_regen(pool_ports, requested_by=USER)
        twice = await request_guide_regen(pool_ports, requested_by=USER)
        assert twice.id == job.id  # double click = one job
        assert job.payload == {"manual": True, "por": USER} and job.scheduled_for is None
        await handle_regen_guia(pool_ports, job)
        guide = await pool_ports.repo.get_guide(1)
        assert guide is not None and guide.status is GuideStatus.RASCUNHO  # a draft, never auto-active

    run(scenario())


def test_list_guides_is_newest_first_and_paged(pool_ports) -> None:
    from noctusai_lib.domain.photo_editing import create_draft

    async def scenario() -> None:
        for n in range(3):
            await create_draft(pool_ports, texto=f"v{n}", gerado_de_versao=None, criado_por=USER)
        page, total = await pool_ports.repo.list_guides(limit=2, offset=0)
        assert total == 3 and [g.versao for g in page] == [3, 2]
        rest, _ = await pool_ports.repo.list_guides(limit=2, offset=2)
        assert [g.versao for g in rest] == [1]

    run(scenario())
