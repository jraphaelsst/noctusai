"""`get_platform_settings` is read by every job step / gate / admin request: it must cost one read per TTL,
not one per caller (2026-11-09 egress incident: ~7.7k `fotos_platform_settings` reads in 22 h)."""
from __future__ import annotations

from typing import Any

from noctusai_lib.domain.photo_editing import SupabasePhotoEditingRepository

from .conftest import run
from .test_repository import SchemaStableClient


class _CountingClient(SchemaStableClient):
    def __init__(self) -> None:
        super().__init__()
        self.platform_reads = 0

    def schema(self, name: str) -> Any:
        scoped = super().schema(name)
        outer = self

        class _S:
            def from_(self, table: str) -> Any:
                if table == "fotos_platform_settings":
                    outer.platform_reads += 1
                return scoped.from_(table)

            def __getattr__(self, attr: str) -> Any:
                return getattr(scoped, attr)

        return _S()


class _Mono:
    t = 0.0

    def __call__(self) -> float:
        return self.t


def test_500_callers_cost_one_read_and_a_write_is_live_at_once() -> None:
    async def scenario() -> None:
        client = _CountingClient()
        client.sw("fotos_platform_settings")._data.append(
            {"id": 1, "velocidade_default": "urgente", "notificacoes_globais_ativas": True}
        )
        client.platform_reads = 0  # the seeding above is not a repository read
        mono = _Mono()
        repo = SupabasePhotoEditingRepository(client, monotonic=mono)
        for _ in range(500):
            await repo.get_platform_settings()
        reads_after_500 = client.platform_reads
        assert reads_after_500 == 1

        await repo.update_platform_settings(limite_pares_referencia=3)
        before = client.platform_reads
        assert (await repo.get_platform_settings()).limite_pares_referencia == 3  # no stale read after our own write
        assert client.platform_reads == before + 1

        mono.t += 11  # the TTL elapsed: another worker's change becomes visible
        await repo.get_platform_settings()
        assert client.platform_reads == before + 2

    run(scenario())
