"""Shared fixtures + row builders for `empresas` module tests.

Rows are seeded against the scoped mock THIS module's DI seam resolves
(`app.modules.empresas.deps.get_empresas_client`), which delegates to the
canonical `app.dependencies.get_scoped_admin_client` — same shape
`imovel_hub`'s own conftest documents.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.dependencies import coerce_org_uuid
from app.modules.empresas.deps import (
    get_cartao_extractor_factory,
    get_empresas_client,
    get_storage_backend,
)
from noctusai_lib.integrations.storage import FakeStorageBackend
from tests.conftest import (  # type: ignore[attr-defined]
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
)

ORG_RAW = "test-org-123"
ORG_ID = str(coerce_org_uuid(ORG_RAW))


def auth() -> dict:
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def anon_client():
    """A TestClient sending NO Authorization header — see `imovel_hub`'s
    identical fixture for why the shared `client` fixture can never
    produce a 401."""
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_RAW)))
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
    ):
        from app.main import app

        bind_consent_module_to_mock(mock_sb)
        tc = TestClient(app)
        yield tc
        app.dependency_overrides.clear()


@pytest.fixture
def scoped(client):
    """The scoped mock `get_empresas_client()` resolves and caches —
    seeding through THIS instance is what makes rows visible to a later
    request in the same test."""
    return get_empresas_client()


@pytest.fixture
def fake_storage(client):
    """Installs a `FakeStorageBackend` via the DI seam — never relies on
    `MockSupabaseClient.storage` (a bare `MagicMock()` that would silently
    "succeed" with garbage signed URLs instead of failing loudly). Per
    `KB § PATTERNS/backend/di-test-seam.md` Class-B."""
    from app.main import app

    backend = FakeStorageBackend()
    prev = app.dependency_overrides.get(get_storage_backend)
    app.dependency_overrides[get_storage_backend] = lambda: backend
    yield backend
    if prev is None:
        app.dependency_overrides.pop(get_storage_backend, None)
    else:
        app.dependency_overrides[get_storage_backend] = prev


@pytest.fixture
def fake_cartao_extractor(client):
    """Installs ONE scripted `FakeCartaoCnpjExtractor` via `get_cartao_
    extractor_factory` — mandatory rather than optional: the real factory
    resolves an org's vision credentials and can reach a provider, neither
    of which is the behaviour under test. Yields the extractor so a test
    can override `.extract()`'s canned result via `result=`."""
    from app.main import app
    from noctusai_lib.integrations.documents.cartao_cnpj import FakeCartaoCnpjExtractor

    extractor = FakeCartaoCnpjExtractor()
    prev = app.dependency_overrides.get(get_cartao_extractor_factory)
    app.dependency_overrides[get_cartao_extractor_factory] = (
        lambda: (lambda org_id, tipo_documento=None: extractor)
    )
    yield extractor
    if prev is None:
        app.dependency_overrides.pop(get_cartao_extractor_factory, None)
    else:
        app.dependency_overrides[get_cartao_extractor_factory] = prev


def empresa_row(id_=None, *, cnpj="11222333000181", razao_social="Empresa Exemplo LTDA", **extra) -> dict:
    row = {
        "id": id_ or str(uuid4()),
        "org_id": ORG_ID,
        "cnpj": cnpj,
        "razao_social": razao_social,
        "nome_fantasia": None,
        "natureza_juridica": None,
        "data_abertura": None,
        "situacao_cadastral": None,
        "data_situacao_cadastral": None,
        "motivo_situacao": None,
        "dados_origem": None,
        "dados_documento_id": None,
        "dados_em": None,
        "dados_confirmado_por": None,
        "dados_confirmado_em": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": None,
    }
    row.update(extra)
    return row


def documento_row(id_=None, empresa_id=None, **extra) -> dict:
    row = {
        "id": id_ or str(uuid4()),
        "org_id": ORG_ID,
        "empresa_id": empresa_id,
        "storage_path": f"{ORG_ID}/empresas/{empresa_id}/{id_ or 'doc'}",
        "nome_original": "cartao.pdf",
        "mime_type": "application/pdf",
        "tamanho_bytes": 1024,
        "tipo_documento": "cartao_cnpj",
        "retencao_ate": None,
        "enviado_por": None,
        "deleted_at": None,
        "delete_motivo": None,
        "delete_solicitado_por": None,
        "extracao_status": "pendente",
        "extracao_em": None,
        "extracao_fonte": None,
        "extracao_erro": None,
        "extracao_tentativas": 0,
        "extracao_descartada_em": None,
        "extracao_descartada_por": None,
        "extracao_dados": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    row.update(extra)
    return row


__all__ = [
    "ORG_ID",
    "auth",
    "documento_row",
    "empresa_row",
]
