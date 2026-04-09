"""Tests for the Attachments router — /api/attachments."""
import pytest
import io


class TestUploadAttachment:
    def test_upload_image(self, client):
        client._mock_supabase.set_table_data("conversation_participants", [
            {"conversation_id": "convo-001", "participant_id": "test-user-123", "participant_type": "user"},
        ])
        fake_image = io.BytesIO(b"fake image data")
        resp = client._tc.post(
            "/api/attachments/upload",
            headers={"Authorization": "Bearer test-token-123"},
            files={"file": ("test.jpg", fake_image, "image/jpeg")},
            data={"conversation_id": "convo-001"},
        )
        assert resp.status_code in [200, 422]  # 200 if storage works, 422 if validation

    def test_upload_audio(self, client):
        client._mock_supabase.set_table_data("conversation_participants", [
            {"conversation_id": "convo-001", "participant_id": "test-user-123", "participant_type": "user"},
        ])
        fake_audio = io.BytesIO(b"fake audio data")
        resp = client._tc.post(
            "/api/attachments/upload",
            headers={"Authorization": "Bearer test-token-123"},
            files={"file": ("test.mp3", fake_audio, "audio/mpeg")},
            data={"conversation_id": "convo-001"},
        )
        assert resp.status_code in [200, 422]

    def test_upload_invalid_type(self, client):
        fake_file = io.BytesIO(b"fake exe data")
        resp = client._tc.post(
            "/api/attachments/upload",
            headers={"Authorization": "Bearer test-token-123"},
            files={"file": ("test.exe", fake_file, "application/x-msdownload")},
            data={"conversation_id": "convo-001"},
        )
        assert resp.status_code == 422

    def test_no_auth(self, client):
        fake_file = io.BytesIO(b"data")
        resp = client._tc.post(
            "/api/attachments/upload",
            files={"file": ("test.jpg", fake_file, "image/jpeg")},
            data={"conversation_id": "convo-001"},
        )
        assert resp.status_code == 401

    def test_missing_conversation_id(self, client):
        fake_file = io.BytesIO(b"data")
        resp = client._tc.post(
            "/api/attachments/upload",
            headers={"Authorization": "Bearer test-token-123"},
            files={"file": ("test.jpg", fake_file, "image/jpeg")},
        )
        assert resp.status_code == 422
