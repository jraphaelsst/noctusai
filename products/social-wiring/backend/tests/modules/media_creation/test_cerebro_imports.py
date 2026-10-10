"""Segundo Cérebro — file import (endpoint 14) and YouTube stub (15), contract §4/§10.

Storage via ``FakeStorageBackend`` through ``get_cerebro_storage``; the PDF
transcriber is faked through its real DI seam (``get_cerebro_transcriber``).
BackgroundTasks run after the response inside the TestClient, so the final
state is observable right after the POST.
"""
from __future__ import annotations

import io
import uuid

import anyio
import pytest

from noctusai_lib.integrations.documents.transcription import (
    FakeDocumentTranscriber,
    Transcription,
)
from noctusai_lib.integrations.storage import FakeStorageBackend

from app.modules.media_creation.deps import CEREBRO_BUCKET, get_cerebro_storage
from app.modules.media_creation.routers.cerebro_fontes import (
    MAX_BODY_PATH_OVERRIDES,
    get_cerebro_transcriber,
)
from app.modules.media_creation.services import cerebro_fontes_service as fontes
from app.modules.media_creation.services.cerebro_ai import get_cerebro_llm

BASE = "/api/media-creation/cerebro"
ORG = "test-org-123"
MARCA = str(uuid.uuid4())
OTHER_MARCA = str(uuid.uuid4())


class _FailingTranscriber:
    async def transcribe(self, content, **kw):
        return Transcription(error="unreadable", error_message="boom")


class _BrokenStorage(FakeStorageBackend):
    async def put(self, **kw):
        raise RuntimeError("storage down")


@pytest.fixture
def cc(client):
    sb = client.mock_supabase
    sb.from_("marcas").insert({"id": MARCA, "org_id": ORG, "name": "Marca A"}).execute()
    sb.from_("marcas").insert({"id": OTHER_MARCA, "org_id": "other-org", "name": "Marca B"}).execute()
    client.storage = FakeStorageBackend()

    async def fake_llm(system, user, org_id):  # never called here; the seam must not hit a real LLM
        raise AssertionError("LLM must not be used by imports")

    overrides = client._tc.app.dependency_overrides
    overrides[get_cerebro_llm] = lambda: fake_llm
    overrides[get_cerebro_storage] = lambda: client.storage
    overrides[get_cerebro_transcriber] = lambda: FakeDocumentTranscriber()
    return client


def _brain(cc, *, org=ORG, marca=MARCA, content=""):
    bid = str(uuid.uuid4())
    cc.mock_supabase.from_("cs_brains").insert({
        "id": bid, "org_id": org, "marca_id": marca, "kind": "custom", "template_slug": None,
        "name": f"B{bid[:4]}", "content": content, "content_version": 0, "synthesis_status": "idle",
    }).execute()
    return bid


def _content(cc, bid):
    return next(r for r in cc.mock_supabase.from_("cs_brains").select("*").execute().data if r["id"] == bid)


def _imports(cc):
    return cc.mock_supabase.from_("cs_brain_imports").select("*").execute().data


def _post(cc, bid, name, data):
    return cc.post(f"{BASE}/brains/{bid}/imports/file", files={"file": (name, io.BytesIO(data))})


def _docx(text="Olá docx") -> bytes:
    import docx

    d = docx.Document()
    d.add_paragraph(text)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


class TestFileImport:
    def test_txt_is_202_then_appended_with_header_and_original_retained(self, cc):
        bid = _brain(cc)
        r = _post(cc, bid, "notas.txt", "Minha voz é direta.".encode())
        assert r.status_code == 202, r.text
        data = r.json()["data"]
        assert data["kind"] == "file" and data["filename"] == "notas.txt" and data["status"] == "processing"
        # background job finished
        rows = _imports(cc)
        assert len(rows) == 1 and rows[0]["status"] == "appended"
        content = _content(cc, bid)["content"]
        assert content.startswith("### Arquivo: «notas.txt» (") and "Minha voz é direta." in content
        assert rows[0]["chars_appended"] == len(content)
        # original retained in the private bucket under the contract path
        key = rows[0]["storage_path"]
        assert key.startswith(f"{ORG}/{MARCA}/{bid}/files/") and key.endswith("-notas.txt")
        assert anyio.run(lambda: cc.storage.exists(bucket=CEREBRO_BUCKET, key=key))
        # visible through endpoint 16 (reused from brains core)
        lst = cc.get(f"{BASE}/brains/{bid}/imports").json()["data"]
        assert [i["status"] for i in lst] == ["appended"]

    def test_docx_and_cp1252_text_and_pdf_via_faked_transcriber(self, cc):
        bid = _brain(cc)
        assert _post(cc, bid, "a.docx", _docx("Conteúdo do docx")).status_code == 202
        assert _post(cc, bid, "b.csv", "ação,valor".encode("cp1252")).status_code == 202
        assert _post(cc, bid, "c.pdf", b"%PDF-1.4 fake").status_code == 202
        assert {r["status"] for r in _imports(cc)} == {"appended"}
        content = _content(cc, bid)["content"]
        assert "Conteúdo do docx" in content and "ação,valor" in content
        assert "### Arquivo: «c.pdf»" in content

    def test_pdf_transcriber_failure_is_a_visible_error_and_appends_nothing(self, cc):
        cc._tc.app.dependency_overrides[get_cerebro_transcriber] = lambda: _FailingTranscriber()
        bid = _brain(cc)
        assert _post(cc, bid, "c.pdf", b"%PDF-1.4 x").status_code == 202
        row = _imports(cc)[0]
        assert row["status"] == "error" and row["error_message"] == fontes.MSG_UNREADABLE
        assert _content(cc, bid)["content"] == ""

    def test_whitespace_only_file_is_error_not_appended(self, cc):
        bid = _brain(cc)
        assert _post(cc, bid, "v.txt", b"   \n  ").status_code == 202
        row = _imports(cc)[0]
        assert row["status"] == "error" and row["error_message"] == "Não foi possível ler texto deste arquivo."
        assert _content(cc, bid)["content"] == ""

    def test_over_limit_append_is_error_never_truncated(self, cc):
        bid = _brain(cc, content="x" * 199_990)
        assert _post(cc, bid, "g.txt", b"y" * 100).status_code == 202
        row = _imports(cc)[0]
        assert row["status"] == "error" and "200.000" in row["error_message"]
        assert _content(cc, bid)["content"] == "x" * 199_990

    def test_unsupported_extension_and_sniff_mismatch_are_415(self, cc):
        bid = _brain(cc)
        assert _post(cc, bid, "x.exe", b"MZ").status_code == 415
        assert _post(cc, bid, "x.pdf", b"not a pdf").status_code == 415
        assert _post(cc, bid, "x.txt", b"%PDF-1.4").status_code == 415
        assert _post(cc, bid, "x.docx", b"plain text").status_code == 415
        assert _imports(cc) == []

    def test_empty_422_and_oversize_413_store_nothing(self, cc):
        bid = _brain(cc)
        assert _post(cc, bid, "e.txt", b"").status_code == 422
        r = _post(cc, bid, "big.txt", b"a" * (fontes.MAX_FILE_BYTES + 1))
        assert r.status_code == 413
        assert _imports(cc) == [] and cc.storage._blobs == {}

    def test_storage_failure_is_502_and_records_no_import(self, cc):
        cc._tc.app.dependency_overrides[get_cerebro_storage] = lambda: _BrokenStorage()
        bid = _brain(cc)
        assert _post(cc, bid, "n.txt", b"oi").status_code == 502
        assert _imports(cc) == []

    def test_cross_org_brain_is_404_and_stores_nothing(self, cc):
        foreign = _brain(cc, org="other-org", marca=OTHER_MARCA)
        assert _post(cc, foreign, "n.txt", b"oi").status_code == 404
        assert _imports(cc) == [] and cc.storage._blobs == {}

    def test_unsafe_filename_is_sanitised_in_the_key_only(self, cc):
        bid = _brain(cc)
        r = _post(cc, bid, "../../etc/pa ss.txt", b"oi")
        assert r.status_code == 202 and r.json()["data"]["filename"] == "pa ss.txt"
        key = _imports(cc)[0]["storage_path"]
        assert ".." not in key and key.endswith("-pa_ss.txt")

    def test_upload_route_has_a_body_override_covering_20mb(self):
        (limit,) = MAX_BODY_PATH_OVERRIDES.values()
        assert limit > fontes.MAX_FILE_BYTES


class TestYoutubeStub:
    def test_501_with_the_owner_message_for_an_owned_brain(self, cc):
        bid = _brain(cc)
        r = cc.post(f"{BASE}/brains/{bid}/imports/youtube", json={"links": ["https://youtu.be/x"]})
        assert r.status_code == 501
        assert r.json()["error"]["message"] == "Transcrição do YouTube ainda não disponível"

    def test_foreign_brain_is_404_and_bad_body_422(self, cc):
        foreign = _brain(cc, org="other-org", marca=OTHER_MARCA)
        assert cc.post(f"{BASE}/brains/{foreign}/imports/youtube", json={"links": ["a"]}).status_code == 404
        assert cc.post(f"{BASE}/brains/{_brain(cc)}/imports/youtube", json={"links": []}).status_code == 422


class TestAuth:
    @pytest.mark.parametrize("kind", ["file", "youtube"])
    def test_unauthenticated_is_401(self, client, kind):
        bid = uuid.uuid4()
        if kind == "file":
            r = client._tc.post(
                f"{BASE}/brains/{bid}/imports/file", files={"file": ("a.txt", io.BytesIO(b"x"))}
            )
        else:
            r = client._tc.post(f"{BASE}/brains/{bid}/imports/youtube", json={"links": ["a"]})
        assert r.status_code == 401, r.text
