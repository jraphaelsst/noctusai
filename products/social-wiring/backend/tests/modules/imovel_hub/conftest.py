"""Shared fixtures + row builders for `imovel_hub` module tests.

Rows are seeded against the scoped mock THIS module's DI seam resolves
(`app.modules.imovel_hub.deps.get_imovel_hub_client`). That seam delegates
to the canonical `app.dependencies.get_scoped_admin_client`, whose cache is
keyed by `(admin client, schema)` — so unlike `card_hub`'s independent
weakref cache, seeding here IS visible to any other consumer of the
canonical helper in the same test. That is a property worth knowing rather
than discovering: it means a fixture cannot accidentally seed a store the
route under test can never read.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.integrations.documents import FakeMatriculaExtractor
from noctusai_lib.integrations.storage import FakeStorageBackend

from app.dependencies import coerce_org_uuid
from app.modules.imovel_hub.deps import (
    get_imovel_hub_client,
    get_matricula_extractor_factory,
    get_storage_backend,
)
from tests.conftest import (  # type: ignore[attr-defined]
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
)

ORG_RAW = "test-org-123"
ORG_ID = str(coerce_org_uuid(ORG_RAW))

CODIGO = "AP1234"


def auth() -> dict:
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def anon_client():
    """A TestClient sending NO Authorization header.

    The shared `client` fixture attaches a bearer token to every request, so
    it can never produce a 401 — useless for an auth boundary.
    """
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(
        return_value=MockUserResponse(MockUser(org_id=ORG_RAW))
    )
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch(
            "noctusai_seed.database.DatabaseModule.get_core_client",
            return_value=mock_sb,
        ),
        patch(
            "noctusai_seed.database.DatabaseModule.get_admin_client",
            return_value=mock_sb,
        ),
    ):
        from app.main import app

        bind_consent_module_to_mock(mock_sb)
        tc = TestClient(app)
        yield tc
        app.dependency_overrides.clear()


@pytest.fixture
def scoped(client):
    """The scoped mock this module's DI seam resolves and caches — seeding
    through THIS instance is what makes rows visible to a later request in
    the same test."""
    return get_imovel_hub_client()


@pytest.fixture
def fake_storage(client):
    """Installs a `FakeStorageBackend` via the DI seam.

    Never relies on `MockSupabaseClient.storage` — a bare `MagicMock()` that
    answers ANY call with another MagicMock, so an un-overridden test would
    silently "succeed" against garbage signed URLs instead of failing loudly.
    """
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
def fake_extractor(client):
    """Installs a `FakeMatriculaExtractor` via the DI seam.

    Mandatory rather than optional: the real factory builds an extractor that
    can reach a vision model, so an un-overridden test would either hit a
    provider or fail on a missing key — neither is the behaviour under test.
    """
    from app.main import app

    extractor = FakeMatriculaExtractor()
    prev = app.dependency_overrides.get(get_matricula_extractor_factory)
    app.dependency_overrides[get_matricula_extractor_factory] = (
        lambda: lambda org_id: extractor
    )
    yield extractor
    if prev is None:
        app.dependency_overrides.pop(get_matricula_extractor_factory, None)
    else:
        app.dependency_overrides[get_matricula_extractor_factory] = prev


# ─── row builders ────────────────────────────────────────────────────────


def imovel_row(codigo=CODIGO, **extra) -> dict:
    """A row of the Vista sync MIRROR.

    Kept so a test can assert this module NEVER writes it. This module does
    not read it either — see `registry_row`.
    """
    row = {
        "org_id": ORG_ID,
        "codigo": codigo,
        "codigo_norm": codigo.lower(),
        "status": "disponivel",
        "categoria": "Apartamento",
        "cidade": "Sao Paulo",
        "bairro": "Pinheiros",
        "sincronizado_em": "2026-01-01T00:00:00+00:00",
    }
    row.update(extra)
    return row


def registry_row(codigo=CODIGO, *, ativo_no_vista=True, **extra) -> dict:
    """A row of `imovel_registry` — our PERMANENT imóvel identity.

    This is what `ensure_imovel` checks (migration 076). `ativo_no_vista=False`
    is a property that has left the Vista catalog, i.e. one that was sold —
    and it must still accept cartório data.
    """
    row = {
        "id": str(uuid4()),
        "org_id": ORG_ID,
        "codigo_canonical": codigo,
        "codigo_display": codigo,
        "primeiro_visto_em": "2026-01-01T00:00:00+00:00",
        "ultimo_visto_no_vista_em": "2026-01-01T00:00:00+00:00",
        "ativo_no_vista": ativo_no_vista,
        "delistado_em": None if ativo_no_vista else "2026-02-01T00:00:00+00:00",
        "origem_descoberta": "sync",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    row.update(extra)
    return row


def dados_row(codigo=CODIGO, **extra) -> dict:
    row = {
        "org_id": ORG_ID,
        "codigo": codigo,
        "numero_matricula": None,
        "numero_matricula_origem": None,
        "numero_matricula_documento_id": None,
        "numero_matricula_em": None,
        "numero_matricula_confirmado_por": None,
        "numero_matricula_confirmado_em": None,
        "numero_registro_imoveis": None,
        "prefeitura_cadastro_imobiliario": None,
        "captador_user_id": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": None,
    }
    row.update(extra)
    return row


def documento_row(id_=None, codigo=CODIGO, *, tipo_documento="matricula", **extra) -> dict:
    row = {
        "id": id_ or str(uuid4()),
        "org_id": ORG_ID,
        "codigo": codigo,
        "storage_path": f"{ORG_ID}/imoveis/{codigo}/{id_ or 'x'}",
        "nome_original": "matricula.pdf",
        "mime_type": "application/pdf",
        "tamanho_bytes": 1234,
        "tipo_documento": tipo_documento,
        "extracao_status": None,
        "extracao_em": None,
        "extracao_matricula": None,
        "extracao_confianca": None,
        "extracao_fonte": None,
        "extracao_rotulo": None,
        "extracao_erro": None,
        "extracao_tentativas": 0,
        "enviado_por": None,
        "deleted_at": None,
        "delete_motivo": None,
        "created_at": "2026-01-02T00:00:00+00:00",
    }
    row.update(extra)
    return row


def seed(scoped, *, registry=None, imoveis=None, dados=None, documentos=None) -> None:
    # The REGISTRY is what this module reads. The mirror is seeded too, so a
    # test can assert it is never written.
    scoped.set_table_data(
        "imovel_registry", registry if registry is not None else [registry_row()]
    )
    scoped.set_table_data("imoveis", imoveis if imoveis is not None else [imovel_row()])
    scoped.set_table_data("imovel_dados", dados or [])
    scoped.set_table_data("imovel_documentos", documentos or [])
