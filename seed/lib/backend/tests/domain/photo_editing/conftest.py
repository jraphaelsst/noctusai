"""Fixtures for the photo-editing engine tests.

Everything is wired through ``PhotoEditingPorts`` (the engine's DI seam):
in-memory repo + job repo + storage, the seed's Fake imaging / image-edit /
fx adapters, a scripted structured-LLM fake and a recording notifier. No
monkeypatching anywhere.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from noctusai_lib.domain.jobs import FakeJobRepository
from noctusai_lib.domain.photo_editing import (
    EditType,
    FakeStructuredLlm,
    InMemoryPhotoEditingRepository,
    InMemoryPhotoStorage,
    OrgSettings,
    PhotoEditingConfig,
    PhotoEditingPorts,
    RecordingNotifier,
)
from noctusai_lib.integrations.fx import FakeFxRateAdapter
from noctusai_lib.integrations.image_edit import FakeImageEditAdapter
from noctusai_lib.integrations.imaging import FakeImagingAdapter

ORG = "org-1"
USER = "user-1"
EDIT_MODEL = "gpt-image-2.5-sunburst"
# Wednesday 2026-09-16 15:00 UTC == 12:00 America/Sao_Paulo.
T0 = datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc)
PTAX = Decimal("5.43210")


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class Clock:
    def __init__(self, start: datetime = T0) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now = self.now + timedelta(**kwargs)


class EditFactory:
    """``ImageEditFactory`` test double — records (org, model) and hands out
    one shared adapter (the seed Fake unless a test supplies another)."""

    def __init__(self, adapter: Any | None = None) -> None:
        self.adapter = adapter or FakeImageEditAdapter()
        self.requests: list[tuple[str, str]] = []

    def __call__(self, org_id: str, model_id: str) -> Any:
        self.requests.append((org_id, model_id))
        return self.adapter


def good_evaluation(_call: dict | None = None) -> dict:
    return {
        "recomendacao": "aprovar",
        "score": 8.5,
        "motivo": "Cores naturais e céu coerente.",
        "fidelidade_estrutural": True,
    }


def default_llm() -> FakeStructuredLlm:
    return FakeStructuredLlm(
        {
            "avaliacao_foto": good_evaluation,
            "guia_estilo": {"guia": "- Luz natural\n- Céu azul limpo"},
            "propor_regras": {"regras": []},
        }
    )


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def ports(clock: Clock) -> PhotoEditingPorts:
    repo = InMemoryPhotoEditingRepository(now=clock)
    repo.seed_org_settings(
        OrgSettings(
            org_id=ORG,
            tipos_edicao_ativos=(EditType.COR_LUZ, EditType.CEU),
            modelo_editor_id=EDIT_MODEL,
        )
    )
    return PhotoEditingPorts(
        repo=repo,
        jobs=FakeJobRepository(),
        storage=InMemoryPhotoStorage(),
        imaging=FakeImagingAdapter(),
        image_edit=EditFactory(),
        llm=default_llm(),
        fx=FakeFxRateAdapter({date(2026, 9, 16): PTAX}),
        notifier=RecordingNotifier(),
        config=PhotoEditingConfig(retry_backoff_seconds=0.0),
        clock=clock,
    )


async def activate_guide(ports: PhotoEditingPorts, texto: str = "- Luz natural") -> None:
    from noctusai_lib.domain.photo_editing import activate_version, create_draft

    draft = await create_draft(ports, texto=texto, gerado_de_versao=None, criado_por=USER)
    await activate_version(ports, draft.versao, ativado_por=USER)
