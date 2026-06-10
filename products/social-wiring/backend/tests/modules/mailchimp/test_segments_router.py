"""Tests for the Mailchimp segments router — /api/mailchimp/segments."""
from __future__ import annotations


class TestAuthRequired:
    def test_list_requires_auth(self, client):
        assert client.raw().get("/api/mailchimp/segments").status_code == 401

    def test_create_requires_auth(self, client):
        resp = client.raw().post("/api/mailchimp/segments", json={"name": "x"})
        assert resp.status_code == 401

    def test_patch_requires_auth(self, client):
        resp = client.raw().patch("/api/mailchimp/segments/1", json={"name": "x"})
        assert resp.status_code == 401

    def test_delete_requires_auth(self, client):
        assert client.raw().delete("/api/mailchimp/segments/1").status_code == 401

    def test_list_members_requires_auth(self, client):
        assert client.raw().get("/api/mailchimp/segments/1/members").status_code == 401

    def test_add_member_requires_auth(self, client):
        resp = client.raw().post(
            "/api/mailchimp/segments/1/members", json={"email": "x@x.com"}
        )
        assert resp.status_code == 401

    def test_remove_member_requires_auth(self, client):
        assert (
            client.raw().delete("/api/mailchimp/segments/1/members/x@x.com").status_code
            == 401
        )


class TestNotConfigured:
    def test_503_when_not_connected(self, mailchimp_client):
        c, store, fake = mailchimp_client
        resp = c.get("/api/mailchimp/segments")
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "mailchimp_not_configured"


class TestSegmentCrud:
    def test_create_segment(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        resp = c.post("/api/mailchimp/segments", json={"name": "VIP"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "VIP"
        assert "id" in data

    def test_list_segments_envelope(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        c.post("/api/mailchimp/segments", json={"name": "Seg1"})
        resp = c.get("/api/mailchimp/segments")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data and "total" in data
        assert data["total"] >= 1

    def test_patch_segment_name(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        seg_id = c.post("/api/mailchimp/segments", json={"name": "Old"}).json()["id"]
        resp = c.patch(f"/api/mailchimp/segments/{seg_id}", json={"name": "New"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New"

    def test_delete_segment(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        seg_id = c.post("/api/mailchimp/segments", json={"name": "Del"}).json()["id"]
        resp = c.delete(f"/api/mailchimp/segments/{seg_id}")
        assert resp.status_code == 204

    def test_delete_missing_segment_returns_404(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        resp = c.delete("/api/mailchimp/segments/99999")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"


class TestSegmentMembers:
    def _setup_segment_with_contact(self, c):
        """Create a segment + a contact, return (segment_id, email)."""
        seg_id = c.post("/api/mailchimp/segments", json={"name": "MemSeg"}).json()["id"]
        email = "member@example.com"
        c.put(f"/api/mailchimp/contacts/{email}", json={"status": "subscribed"})
        return seg_id, email

    def test_add_member_returns_201(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        seg_id, email = self._setup_segment_with_contact(c)
        resp = c.post(f"/api/mailchimp/segments/{seg_id}/members", json={"email": email})
        assert resp.status_code == 201
        assert resp.json()["email"] == email

    def test_add_member_not_in_audience_returns_400(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        seg_id = c.post("/api/mailchimp/segments", json={"name": "Empty"}).json()["id"]
        resp = c.post(
            f"/api/mailchimp/segments/{seg_id}/members",
            json={"email": "notacontact@example.com"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "mailchimp_rejected"

    def test_list_segment_members_returns_envelope(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        seg_id, email = self._setup_segment_with_contact(c)
        c.post(f"/api/mailchimp/segments/{seg_id}/members", json={"email": email})
        resp = c.get(f"/api/mailchimp/segments/{seg_id}/members")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["email"] == email

    def test_remove_segment_member_returns_204(self, connected_mailchimp_client):
        c, store, fake = connected_mailchimp_client
        seg_id, email = self._setup_segment_with_contact(c)
        c.post(f"/api/mailchimp/segments/{seg_id}/members", json={"email": email})
        resp = c.delete(f"/api/mailchimp/segments/{seg_id}/members/{email}")
        assert resp.status_code == 204
