"""DocumentoStore: an extension-less upload (browser sends octet-stream) is
resolved from its bytes; executable bytes under a document type are refused."""
from __future__ import annotations

from uuid import uuid4

import pytest
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.primitives.exceptions import ValidationError_

from app.modules.empresas.documentos_service import STORE

TIPO = next(iter(STORE.tipos))


class _Table:
    def __init__(self, sink):
        self.sink = sink

    def insert(self, row):
        self.sink.append(row)
        return self

    def execute(self):
        return self


class _Client:
    def __init__(self):
        self.rows = []

    def table(self, name):
        return _Table(self.rows)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data,mime,ext",
    [(b"\xff\xd8\xff\xe0\x00\x10JFIF", "image/jpeg", ".jpg"), (b"%PDF-1.4\n", "application/pdf", ".pdf")],
)
async def test_octet_stream_resolved_from_bytes(data, mime, ext):
    client = _Client()
    await STORE.guardar(
        client, FakeStorageBackend(), uuid4(), uuid4(),
        filename="Espelho IPTU 2026", content_type="application/octet-stream",
        data=data, tipo_documento=TIPO, enviado_por=None,
    )
    row = client.rows[0]
    assert row["mime_type"] == mime
    assert row["nome_original"] == "Espelho IPTU 2026" + ext


@pytest.mark.asyncio
async def test_declared_pdf_with_executable_bytes_refused():
    with pytest.raises(ValidationError_):
        await STORE.guardar(
            _Client(), FakeStorageBackend(), uuid4(), uuid4(),
            filename="x.pdf", content_type="application/pdf",
            data=b"MZ\x90\x00\x03", tipo_documento=TIPO, enviado_por=None,
        )


@pytest.mark.asyncio
async def test_unrecognised_octet_stream_refused():
    with pytest.raises(ValidationError_):
        await STORE.guardar(
            _Client(), FakeStorageBackend(), uuid4(), uuid4(),
            filename="x", content_type="application/octet-stream",
            data=b"hello", tipo_documento=TIPO, enviado_por=None,
        )
