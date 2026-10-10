"""Fixtures for the shared transcription layer (``app/modules/transcricoes``) and its
Segundo Cérebro voice wiring.

Mounts BOTH modules through their own ``register()`` (the real registration seam) on a
seed-factory app. Every external seam is replaced by its production DI override —
``FakeTranscriber``, ``FakeStorageBackend``, ``FakeJobRepository``, the kill switch —
nothing is monkeypatched.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_REPO = _Path(__file__).resolve().parents[6]
for _p in (_REPO / "seed" / "framework" / "backend", _REPO / "seed" / "lib" / "backend"):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from noctusai_lib.domain.jobs import FakeJobRepository  # noqa: E402
from noctusai_lib.integrations.storage import FakeStorageBackend  # noqa: E402
from noctusai_lib.integrations.transcription import AudioProbe, FakeTranscriber  # noqa: E402
from noctusai_lib.testing import (  # noqa: E402,F401
    AuthClient,
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
    bind_user_metadata,
)

ORG = "test-org-123"
USER = "test-user-123"
#: A webm (EBML) header — the magic-byte sniffer needs only the first bytes.
AUDIO = b"\x1a\x45\xdf\xa3" + b"\x00" * 2048


class Harness(AuthClient):
    """AuthClient + the fakes behind every transcription seam."""

    storage: FakeStorageBackend
    jobs: FakeJobRepository
    transcriber: FakeTranscriber
    habilitada: bool
    admin_ids: set


@pytest.fixture
def client():
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG)))

    with patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb), patch(
        "noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb
    ), patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb):
        from noctusai_seed import create_product_app

        from app.config import settings
        from app.modules.media_creation import register as register_media_creation
        from app.modules.media_creation.routers import cerebro_fontes
        from app.modules.transcricoes import register as register_transcricoes
        from app.modules.transcricoes import router as transcricoes_router
        from app.modules.transcricoes.deps import (
            get_kill_switch,
            get_platform_admin_check,
            get_transcricao_jobs,
            get_transcricao_storage,
            get_transcriber_factory,
        )
        from app.rate_limit import limiter

        regs = [register_transcricoes(), register_media_creation()]
        app = create_product_app(
            name="Social Wiring (transcricoes test harness)",
            schema="social_wiring",
            settings=settings,
            version="0.1.0",
            limiter=limiter,
            standard_routers=[],
            routers=[r for reg in regs for r in reg.routers],
            # every mounted UploadFile route needs a body-size entry: boot refuses without it
            max_body_path_overrides={
                **cerebro_fontes.MAX_BODY_PATH_OVERRIDES,
                **transcricoes_router.MAX_BODY_PATH_OVERRIDES,
            },
        )
        bind_consent_module_to_mock(mock_sb)

        h = Harness(TestClient(app), mock_sb)
        h.storage = FakeStorageBackend()
        h.jobs = FakeJobRepository()
        h.transcriber = FakeTranscriber()
        h.habilitada = True
        h.admin_ids = set()
        app.dependency_overrides[get_transcricao_storage] = lambda: h.storage
        app.dependency_overrides[get_transcricao_jobs] = lambda: h.jobs
        app.dependency_overrides[get_transcriber_factory] = lambda: (lambda: h.transcriber)
        app.dependency_overrides[get_kill_switch] = lambda: (lambda: h.habilitada)
        app.dependency_overrides[get_platform_admin_check] = lambda: (lambda uid: uid in h.admin_ids)
        try:
            yield h
        finally:
            app.dependency_overrides.clear()


def probe(duracao_s: float = 5.0, container: str = "webm", codec: str = "opus") -> AudioProbe:
    return AudioProbe(duracao_s=duracao_s, codec=codec, container=container, sample_rate=48000, canais=1)
