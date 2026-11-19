"""Ports the product implements (Protocols) + the default progress impl."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from noctusai_lib.domain.media_production.types import PassoRow
from noctusai_lib.realtime.bus import RealtimeBus
from noctusai_lib.realtime.job_progress import JobProgress, publish_job_progress


@runtime_checkable
class LedgerPort(Protocol):
    """The measured ledger AND the graph state (one row per step per rodada)."""

    async def registrar(self, row: PassoRow) -> None:
        """Upsert by (org_id, post_id, rodada, passo)."""

    async def carregar(self, org_id: str, post_id: str) -> list[PassoRow]:
        """Every row of the post, all rodadas."""


@runtime_checkable
class ProgressPort(Protocol):
    async def publicar(
        self,
        org_id: str,
        post_id: str,
        rodada: int,
        stage: str,
        progress: float,
        message: str,
        terminal: bool,
    ) -> None: ...


@runtime_checkable
class QuotaPort(Protocol):
    async def verificar(self, org_id: str, estimativa_usd: Decimal) -> None:
        """Return when within quota; raise ``QuotaExceeded`` otherwise."""


@runtime_checkable
class MoverPort(Protocol):
    async def mover(self, post_id: str, evento: str) -> None:
        """Product moves the card on ``criacao_concluida`` / ``passo_falhou``."""


def progress_scope_id(post_id: str, rodada: int) -> str:
    return f"{post_id}:{rodada}"


class BusProgress:
    """Default ProgressPort over ``realtime.job_progress`` (job id ``{post}:{rodada}``)."""

    def __init__(self, bus: RealtimeBus) -> None:
        self._bus = bus

    async def publicar(self, org_id, post_id, rodada, stage, progress, message, terminal) -> None:
        await publish_job_progress(
            self._bus,
            org_id,
            progress_scope_id(post_id, rodada),
            JobProgress(
                status="concluido" if terminal else "executando",
                progress=progress,
                stage=stage,
                message=message,
                terminal=terminal,
            ),
        )
