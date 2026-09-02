"""Tests for the Matrículas router — upload, list, get, delete.

Ported from `erp-imobiliario`'s `tests/routers/test_matriculas_router.py`
as ERP is retired, minus the two `log_action` assertions (this product has
no audit-log helper — see `app/modules/matriculas/router.py`) and plus the
three things the port introduced: the org-omitting INSERT, the transcriber
DI seam, and a real auth boundary.

MOUNTING
────────
`app/main.py` deliberately does NOT register the matriculas module yet
(peer branches are live in that file concurrently; the tech-lead wires
`MODULES` at integration time — see `app/modules/matriculas/__init__.py`).
This module mounts the router onto the shared `app.main.app` object
IN-MEMORY at collection time, exactly as `tests/modules/n8n/conftest.py`
does and for the same reason: it touches nothing on disk and is precisely
what the real wiring step will do.
"""
import pytest
from unittest.mock import patch

from noctusai_lib.integrations.documents import TextSource
from noctusai_lib.integrations.documents.transcription import (
    TranscribedPage,
    Transcription,
)

from app.main import app as _app
from app.modules.matriculas import router as _router_mod
from app.modules.matriculas.deps import (
    get_background_client,
    get_transcriber_factory,
)

# Idempotent by construction (a module is imported once per pytest process),
# and guarded anyway so a future re-import cannot double-mount.
if not any(
    getattr(r, "path", "") == "/api/matriculas/extrair" for r in _app.routes
):
    _app.include_router(_router_mod.router)


SAMPLE_EXTRACAO = {
    "id": "ext-001",
    "org_id": "test-org-123",
    "user_id": "test-user-123",
    "nome_arquivo": "matricula.pdf",
    "tamanho_bytes": 1024,
    "num_paginas": 3,
    "texto_extraido": "Texto extraído da matrícula",
    "status": "concluida",
    "erro_mensagem": None,
    "created_at": "2026-03-13T12:00:00Z",
}

_PDF = {"file": ("matricula.pdf", b"%PDF-1.0 fake", "application/pdf")}


class _StubTranscriber:
    async def transcribe(self, content, *, mimetype=None, filename=None):
        return Transcription(
            pages=(TranscribedPage(number=1, text="P1", source=TextSource.OCR),),
            num_paginas=1,
        )


@pytest.fixture
def stub_transcriber():
    """Override the transcriber DI seam.

    MANDATORY for any test that reaches the upload route: the real factory
    builds a transcriber that can call a vision model, so an un-overridden
    test would either hit a provider or fail on a missing key — neither is
    the behaviour under test.
    """
    stub = _StubTranscriber()
    _app.dependency_overrides[get_transcriber_factory] = lambda: (lambda _org: stub)
    yield stub
    _app.dependency_overrides.pop(get_transcriber_factory, None)


class _RecordingDB:
    """Records the detached half's writes AND their predicates.

    `MockSupabaseClient` swallows both: it has no column DEFAULTs (so the
    stored row has no `org_id` for the org-scoped UPDATE to match) and it
    keeps no update history. These tests are about the OUTCOME the
    background task wrote and the SCOPE it wrote it with, so the double has
    to keep both.
    """

    def __init__(self):
        self.updates: list[dict] = []
        self.predicates: list[list[tuple]] = []
        self._current: list[tuple] = []

    def table(self, _name):
        self._current = []
        return self

    def update(self, payload):
        self.updates.append(payload)
        self.predicates.append(self._current)
        return self

    def eq(self, col, val):
        self._current.append((col, val))
        return self

    def execute(self):
        return type("_R", (), {"data": []})()


@pytest.fixture
def background_db():
    """Override the background-write seam (`get_background_client`)."""
    db = _RecordingDB()
    _app.dependency_overrides[get_background_client] = lambda: db
    yield db
    _app.dependency_overrides.pop(get_background_client, None)


@pytest.fixture
def com_credencial():
    """The org has an OpenAI key. Patches the CREDENTIAL RESOLVER (an
    external config source), not our own guard — `check_required_credentials`
    still runs for real."""
    with patch(
        "app.modules.matriculas.service.resolve_credential", return_value="sk-test"
    ):
        yield


# ---------------------------------------------------------------------------
# POST /api/matriculas/extrair
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("com_credencial", "stub_transcriber")
class TestExtrairMatricula:
    def test_upload_pdf_sucesso(self, client):
        client.mock_supabase.set_table_data("matricula_extracoes", [])
        resp = client.post("/api/matriculas/extrair", files=_PDF)
        assert resp.status_code == 200
        assert resp.json()["data"]["nome_arquivo"] == "matricula.pdf"

    def test_o_insert_nao_manda_org_id(self, client):
        """🔴 The org-source-of-truth hardening, asserted where it lives.

        Migration 090 defaults `org_id` to `public.current_org_id()` — the
        same trusted table RLS reads. If this handler ever starts sending an
        org again it is sourcing it from the request, which is the exact
        drift that 500'd ERP's uploader for freshly-provisioned users
        (erp incident 2026-07-07 → migration 038)."""
        client.mock_supabase.set_table_data("matricula_extracoes", [])
        client.post("/api/matriculas/extrair", files=_PDF)

        payloads = client.mock_supabase.table("matricula_extracoes").inserted_payloads
        assert payloads, "the upload must insert a row"
        assert "org_id" not in payloads[-1], (
            "org must come from the DB default, never from the request"
        )
        assert payloads[-1]["status"] == "pendente"
        assert payloads[-1]["tamanho_bytes"] == len(b"%PDF-1.0 fake")

    def test_a_extracao_roda_e_grava_o_texto(self, client, background_db):
        """🔴 The route's job is a SIDE EFFECT, so a 200 proves nothing.

        `TestClient` drains background tasks before returning, so by the time
        this assertion runs the detached half must already have moved the row
        `processando → concluida` and written the transcription. Asserted
        through the `get_background_client` seam rather than by re-reading
        `MockSupabaseClient`: the mock has no column DEFAULTs, so the row it
        stores carries no `org_id` and the (correctly) org-scoped UPDATE
        would match nothing — the mock's gap, not the code's."""
        client.mock_supabase.set_table_data("matricula_extracoes", [])
        resp = client.post("/api/matriculas/extrair", files=_PDF)
        extracao_id = resp.json()["data"]["id"]

        assert [u["status"] for u in background_db.updates] == [
            "processando", "concluida",
        ]
        assert background_db.updates[-1]["texto_extraido"] == "P1"
        assert background_db.updates[-1]["num_paginas"] == 1
        for preds in background_db.predicates:
            assert ("id", extracao_id) in preds
            assert any(col == "org_id" and val for col, val in preds), (
                "a service-role write must be scoped to an org"
            )

    def test_uma_falha_na_extracao_vira_erro_na_linha(self, client, background_db):
        """The failure path is the one that matters: nobody is listening when
        it happens, so an outcome that is not written is an outcome nobody
        will ever see."""

        class _Explode:
            async def transcribe(self, content, **kw):
                raise RuntimeError("vision indisponível")

        _app.dependency_overrides[get_transcriber_factory] = (
            lambda: (lambda _org: _Explode())
        )
        try:
            client.mock_supabase.set_table_data("matricula_extracoes", [])
            resp = client.post("/api/matriculas/extrair", files=_PDF)
        finally:
            _app.dependency_overrides.pop(get_transcriber_factory, None)

        assert resp.status_code == 200, "the upload itself still succeeded"
        assert background_db.updates[-1]["status"] == "erro"
        assert "vision indisponível" in background_db.updates[-1]["erro_mensagem"]

    def test_rejeita_arquivo_nao_pdf(self, client):
        resp = client.post(
            "/api/matriculas/extrair",
            files={"file": ("doc.txt", b"plain text", "text/plain")},
        )
        assert resp.status_code == 400
        assert "PDF" in resp.json()["error"]["message"]

    def test_rejeita_arquivo_vazio(self, client):
        resp = client.post(
            "/api/matriculas/extrair",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert resp.status_code == 400
        assert "vazio" in resp.json()["error"]["message"].lower()

    def test_insert_falha_retorna_500(self, client):
        from noctusai_lib.testing import MockSupabaseResponse

        client.mock_supabase.set_sequential_responses(
            "matricula_extracoes", [MockSupabaseResponse(data=[])]
        )
        resp = client.post("/api/matriculas/extrair", files=_PDF)
        assert resp.status_code == 500


class TestExtrairSemCredencial:
    def test_rejeita_sem_credenciais(self, client, stub_transcriber):
        """422 up front rather than a row that fails 40 seconds later with
        nobody watching."""
        with patch(
            "app.modules.matriculas.service.resolve_credential", return_value=None
        ):
            resp = client.post("/api/matriculas/extrair", files=_PDF)

        assert resp.status_code == 422
        mensagem = resp.json()["error"]["message"]
        assert "OpenAI" in mensagem
        assert "Chaves de API" in mensagem, (
            "the 422 must name the page the user has to go to"
        )


# ---------------------------------------------------------------------------
# GET /api/matriculas/extracoes
# ---------------------------------------------------------------------------

class TestListarExtracoes:
    def test_lista_vazia(self, client):
        client.mock_supabase.set_table_data("matricula_extracoes", [])
        resp = client.get("/api/matriculas/extracoes")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_lista_com_dados(self, client):
        client.mock_supabase.set_table_data("matricula_extracoes", [
            SAMPLE_EXTRACAO,
            {**SAMPLE_EXTRACAO, "id": "ext-002", "nome_arquivo": "mat2.pdf"},
        ])
        resp = client.get("/api/matriculas/extracoes")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    def test_busca_por_nome(self, client):
        client.mock_supabase.set_table_data("matricula_extracoes", [SAMPLE_EXTRACAO])
        resp = client.get("/api/matriculas/extracoes?busca=matricula")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    def test_busca_que_nao_casa_devolve_vazio(self, client):
        client.mock_supabase.set_table_data("matricula_extracoes", [SAMPLE_EXTRACAO])
        resp = client.get("/api/matriculas/extracoes?busca=nada-com-esse-nome")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_paginacao_params(self, client):
        client.mock_supabase.set_table_data("matricula_extracoes", [SAMPLE_EXTRACAO])
        resp = client.get("/api/matriculas/extracoes?page=1&page_size=10")
        assert resp.status_code == 200
        assert "pagination" in resp.json()

    def test_a_lista_nao_seleciona_o_texto_extraido(self):
        """A full transcription is tens of KB; 50 of them is megabytes nobody
        on a history screen reads. `MockSupabaseClient` does not project
        columns, so the contract is asserted on the projection itself."""
        assert "texto_extraido" not in _router_mod._COLUNAS_LISTA
        assert "nome_arquivo" in _router_mod._COLUNAS_LISTA
        assert "status" in _router_mod._COLUNAS_LISTA


# ---------------------------------------------------------------------------
# GET /api/matriculas/extracoes/{id}
# ---------------------------------------------------------------------------

class TestObterExtracao:
    def test_extracao_encontrada(self, client):
        client.mock_supabase.set_table_data("matricula_extracoes", [SAMPLE_EXTRACAO])
        resp = client.get("/api/matriculas/extracoes/ext-001")
        assert resp.status_code == 200
        assert resp.json()["data"]["texto_extraido"] == "Texto extraído da matrícula"

    def test_extracao_nao_encontrada(self, client):
        client.mock_supabase.set_table_data("matricula_extracoes", [])
        resp = client.get("/api/matriculas/extracoes/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/matriculas/extracoes/{id}
# ---------------------------------------------------------------------------

class TestExcluirExtracao:
    def test_exclui_com_sucesso(self, client):
        client.mock_supabase.set_table_data("matricula_extracoes", [SAMPLE_EXTRACAO])
        resp = client.delete("/api/matriculas/extracoes/ext-001")
        assert resp.status_code == 200
        assert "sucesso" in resp.json()["message"].lower()

    def test_exclui_nao_encontrada(self, client):
        client.mock_supabase.set_table_data("matricula_extracoes", [])
        resp = client.delete("/api/matriculas/extracoes/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Auth boundary
# ---------------------------------------------------------------------------

class TestAuthBoundary:
    """🔴 Strict `== 401`, never `in (401, 404)`.

    The non-401 branch of a tolerant assertion passes when the route does not
    exist at all — which is exactly the state this module was in before it
    was mounted. → KB § PATTERNS/compliance/auth-boundary-false-green.md
    """

    def test_extrair_exige_autenticacao(self, anon_client):
        resp = anon_client.post("/api/matriculas/extrair", files=_PDF)
        assert resp.status_code == 401

    def test_listar_exige_autenticacao(self, anon_client):
        assert anon_client.get("/api/matriculas/extracoes").status_code == 401

    def test_obter_exige_autenticacao(self, anon_client):
        assert anon_client.get("/api/matriculas/extracoes/ext-001").status_code == 401

    def test_excluir_exige_autenticacao(self, anon_client):
        assert (
            anon_client.delete("/api/matriculas/extracoes/ext-001").status_code == 401
        )


# ---------------------------------------------------------------------------
# The wiring contract the tech-lead has to honour
# ---------------------------------------------------------------------------

class TestTheUploadBodyCeiling:
    """🔴 `create_product_app` REFUSES TO BOOT when a mounted `UploadFile`
    route has no `max_body_path_overrides` entry, and the platform default
    (1 MB, a webhook DoS guard) would 413 every realistic matrícula. The
    module publishes the entry next to the number it mirrors so the
    `MODULES` append and the override cannot drift apart."""

    def test_the_published_override_matches_the_handler_ceiling(self):
        assert _router_mod.MAX_BODY_PATH_OVERRIDES == {
            "/api/matriculas/extrair": _router_mod.MAX_FILE_SIZE
        }

    def test_it_covers_the_route_that_actually_takes_an_upload(self):
        caminhos = {
            getattr(r, "path", "")
            for r in _router_mod.router.routes
            if "POST" in (getattr(r, "methods", None) or set())
        }
        assert set(_router_mod.MAX_BODY_PATH_OVERRIDES) <= caminhos
