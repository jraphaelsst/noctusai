"""
Tests for Storage router — /api/storage
Covers file upload and delete endpoints.
"""
import pytest
import io


class TestUploadFile:
    def test_upload_single(self, client):
        resp = client._tc.post(
            "/api/storage/upload",
            headers=client._headers,
            files={"file": ("test.jpg", b"fake-image-data", "image/jpeg")},
            data={"categoria": "imoveis"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "url" in data["data"]

    def test_upload_invalid_type(self, client):
        resp = client._tc.post(
            "/api/storage/upload",
            headers=client._headers,
            files={"file": ("test.exe", b"fake-data", "application/x-executable")},
            data={"categoria": "imoveis"},
        )
        assert resp.status_code == 400

    def test_upload_default_categoria(self, client):
        resp = client._tc.post(
            "/api/storage/upload",
            headers=client._headers,
            files={"file": ("doc.pdf", b"fake-pdf", "application/pdf")},
        )
        assert resp.status_code == 200


class TestUploadMultiple:
    def test_upload_two_files(self, client):
        files = [
            ("files", ("a.jpg", b"data-a", "image/jpeg")),
            ("files", ("b.png", b"data-b", "image/png")),
        ]
        resp = client._tc.post(
            "/api/storage/upload-multiple",
            headers=client._headers,
            files=files,
            data={"categoria": "geral"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2


class TestDeleteFile:
    def test_delete_file(self, client):
        resp = client._tc.delete(
            "/api/storage/delete?path=test-org/geral/file.jpg&categoria=geral",
            headers=client._headers,
        )
        assert resp.status_code == 200
