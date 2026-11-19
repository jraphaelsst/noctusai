"""In-memory fakes of every port."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from noctusai_lib.domain.media_production.types import PassoRow, QuotaExceeded


class FakeLedger:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, int, str], PassoRow] = {}
        self.history: list[PassoRow] = []

    async def registrar(self, row: PassoRow) -> None:
        self.rows[(row.org_id, row.post_id, row.rodada, row.passo)] = row
        self.history.append(row)

    async def carregar(self, org_id: str, post_id: str) -> list[PassoRow]:
        return [r for k, r in self.rows.items() if k[0] == org_id and k[1] == post_id]


@dataclass
class ProgressEvent:
    org_id: str
    post_id: str
    rodada: int
    stage: str
    progress: float
    message: str
    terminal: bool


class FakeProgress:
    def __init__(self) -> None:
        self.events: list[ProgressEvent] = []

    async def publicar(self, org_id, post_id, rodada, stage, progress, message, terminal) -> None:
        self.events.append(ProgressEvent(org_id, post_id, rodada, stage, progress, message, terminal))


class FakeQuota:
    """Refuses when the estimate exceeds the limit."""

    def __init__(self, limite_usd: Decimal = Decimal("15")) -> None:
        self.limite_usd = limite_usd
        self.consultas: list[tuple[str, Decimal]] = []

    async def verificar(self, org_id: str, estimativa_usd: Decimal) -> None:
        self.consultas.append((org_id, estimativa_usd))
        if estimativa_usd > self.limite_usd:
            raise QuotaExceeded()


class FakeMover:
    def __init__(self) -> None:
        self.movimentos: list[tuple[str, str]] = []

    async def mover(self, post_id: str, evento: str) -> None:
        self.movimentos.append((post_id, evento))
