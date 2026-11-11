"""Public (unauthenticated) endpoints are rate limited per client IP.

Token-gated / org-id-addressed endpoints have no auth to throttle abuse
(lead-spam into any org, token guessing), so slowapi limits apply.
Bodies must still bind as bodies (422 on bad payload, not a Query fallback).
"""
from uuid import uuid4

TOKEN = str(uuid4())
ORG = "00000000-0000-0000-0000-000000000001"


def _hammer(send, limit_plus):
    codes = [send().status_code for _ in range(limit_plus)]
    return codes


class TestPublicRateLimits:
    def test_capture_is_rate_limited(self, client):
        codes = _hammer(
            lambda: client.raw().post(f"/api/capture/{ORG}", json={"name": "x"}), 25
        )
        assert 429 in codes
        assert codes[0] != 429

    def test_capture_is_rate_limited_per_org_across_many_ips(self, client):
        """A botnet of distinct IPs stays under the per-IP limit; the per-ORG limit still stops the flood."""
        org = "00000000-0000-0000-0000-0000000000f1"
        codes = [
            client.raw().post(f"/api/capture/{org}", json={"name": "x"}, headers={"CF-Connecting-IP": f"10.9.{i // 250}.{i % 250 + 1}"}).status_code
            for i in range(125)
        ]
        assert 429 in codes
        assert codes[0] != 429

    def test_capture_limiter_shares_one_bucket_across_spellings_of_one_org_id(self, client):
        """Case-varied / un-hyphenated spellings of ONE org id (the ones the path parser accepts) are one per-org bucket
        (distinct IPs, so only the per-org limit can trip); brace/urn spellings are covered by the key unit test below."""
        org = "00000000-0000-0000-0000-0000000000f2"
        spellings = [org, org.upper(), org.replace("-", "")]
        codes = []
        for i in range(125):
            codes.append(client.raw().post(
                f"/api/capture/{spellings[i % len(spellings)]}", json={"name": "x"},
                headers={"CF-Connecting-IP": f"10.8.{i // 250}.{i % 250 + 1}"}).status_code)
        assert 429 in codes

    def test_capture_org_key_is_canonical(self):
        """The limiter key is built from the canonical UUID: every spelling is ONE bucket; junk keeps its raw value."""
        from types import SimpleNamespace

        from app.routers.crm_router import _capture_org_key

        org = "00000000-0000-0000-0000-0000000000f3"
        key = lambda raw: _capture_org_key(SimpleNamespace(path_params={"org_id": raw}))  # noqa: E731
        assert {key(org), key(org.upper()), key("{" + org + "}"), key(org.replace("-", "")), key("urn:uuid:" + org)} == {f"capture-org:{org}"}
        assert key("not-a-uuid") == "capture-org:not-a-uuid"

    def test_capture_for_an_org_without_orbity_is_404_and_writes_nothing(self, client):
        from noctusai_lib.domain.licensing import FakeLicenseChecker, configure_license_gate, get_license_gate, restore_license_gate

        before = get_license_gate()
        configure_license_gate("orbity", FakeLicenseChecker(allow_all=False, licensed=set()))
        try:
            client.mock_supabase.set_table_data("leads", [])
            r = client.raw().post(f"/api/capture/{ORG}", json={"name": "x"})
            assert r.status_code == 404
            assert client.mock_supabase.table("leads").inserted_payloads == []
            configure_license_gate("orbity", FakeLicenseChecker(allow_all=False, licensed={(ORG, "orbity")}))
            client.mock_supabase.set_table_data("lead_stages", [])
            assert client.raw().post(f"/api/capture/{ORG}", json={"name": "x"}).status_code == 201
        finally:
            restore_license_gate(before)

    def test_capture_is_503_when_no_license_gate_is_configured(self, client):
        """enforce_license is a silent no-op without a gate; a public write must fail CLOSED instead (P3-2)."""
        from noctusai_lib.domain.licensing import configure_license_gate, get_license_gate, restore_license_gate

        before = get_license_gate()
        configure_license_gate(None)  # removes the gate
        try:
            client.mock_supabase.set_table_data("leads", [])
            assert client.raw().post(f"/api/capture/{ORG}", json={"name": "x"}).status_code == 503
            assert client.mock_supabase.table("leads").inserted_payloads == []
        finally:
            restore_license_gate(before)

    # --- hidden honeypot (owner decision 2026-11-10) -------------------------------------------------------------------

    def test_an_empty_honeypot_captures_as_before_and_is_not_stored_as_a_field(self, client):
        mock = client.mock_supabase
        mock.set_table_data("leads", [])
        mock.set_table_data("lead_stages", [])
        r = client.raw().post(f"/api/capture/{ORG}", json={"name": "Ana", "hp_website": ""})
        assert r.status_code == 201
        inserted = mock.table("leads").inserted_payloads
        assert len(inserted) == 1 and inserted[0]["name"] == "Ana"
        assert "hp_website" not in inserted[0]["custom_fields"]

    def test_a_filled_honeypot_for_an_org_without_orbity_is_still_404(self, client):
        from noctusai_lib.domain.licensing import FakeLicenseChecker, configure_license_gate, get_license_gate, restore_license_gate

        before = get_license_gate()
        configure_license_gate("orbity", FakeLicenseChecker(allow_all=False, licensed=set()))
        try:
            assert client.raw().post(f"/api/capture/{ORG}", json={"name": "x", "hp_website": "spam"}).status_code == 404
        finally:
            restore_license_gate(before)

    def test_capture_is_503_when_the_license_check_is_down(self, client):
        from noctusai_lib.domain.licensing import FakeLicenseChecker, configure_license_gate, get_license_gate, restore_license_gate

        before = get_license_gate()
        configure_license_gate("orbity", FakeLicenseChecker(allow_all=False, unavailable=True))
        try:
            assert client.raw().post(f"/api/capture/{ORG}", json={"name": "x"}).status_code == 503
        finally:
            restore_license_gate(before)

    def test_capture_custom_fields_are_capped_by_count(self, client):
        body = {"name": "x", **{f"k{i}": "v" for i in range(21)}}
        assert client.raw().post(f"/api/capture/{ORG}", json=body).status_code == 422

    def test_capture_custom_fields_are_capped_by_bytes(self, client):
        assert client.raw().post(f"/api/capture/{ORG}", json={"name": "x", "blob": "a" * 9000}).status_code == 422

    def test_capture_within_the_caps_is_accepted(self, client):
        client.mock_supabase.set_table_data("lead_stages", [])
        assert client.raw().post(f"/api/capture/{ORG}", json={"name": "x", "utm": "a", "campanha": "b"}).status_code == 201

    def test_capture_stage_of_another_org_is_refused(self, client):
        other_stage = str(uuid4())
        client.mock_supabase.set_table_data("lead_stages", [
            {"id": other_stage, "org_id": "00000000-0000-0000-0000-0000000000aa", "name": "N", "position": 0}])
        r = client.raw().post(f"/api/capture/{ORG}", json={"name": "x", "stage_id": other_stage})
        assert r.status_code == 422

    def test_capture_stage_of_this_org_is_accepted(self, client):
        mine = str(uuid4())
        client.mock_supabase.set_table_data("lead_stages", [{"id": mine, "org_id": ORG, "name": "N", "position": 0}])
        r = client.raw().post(f"/api/capture/{ORG}", json={"name": "x", "stage_id": mine})
        assert r.status_code == 201

    def test_token_guessing_cannot_dodge_the_limit_with_a_fresh_path(self, client):
        """slowapi's default scope is the request PATH; a token-link path carries the token, so without a pinned scope each
        guess would be a fresh bucket. 35 DIFFERENT tokens from one IP must trip the 30/minute limit."""
        codes = [client.raw().get(f"/api/reports/public/{uuid4()}").status_code for _ in range(35)]
        assert 429 in codes
        codes = [client.raw().get(f"/api/content/approve/{uuid4()}").status_code for _ in range(35)]
        assert 429 in codes

    def test_capture_body_still_validated_as_body(self, client):
        resp = client.raw().post(f"/api/capture/{ORG}", json={"email": "not-an-email"})
        assert resp.status_code == 422

    def test_public_report_is_rate_limited(self, client):
        codes = _hammer(lambda: client.raw().get(f"/api/reports/public/{TOKEN}"), 35)
        assert 429 in codes
        assert codes[0] != 429

    def test_approval_get_is_rate_limited(self, client):
        codes = _hammer(lambda: client.raw().get(f"/api/content/approve/{TOKEN}"), 35)
        assert 429 in codes
        assert codes[0] != 429

    def test_approval_post_is_rate_limited_and_body_validated(self, client):
        bad = client.raw().post(f"/api/content/approve/{TOKEN}", json={"decision": "nope"})
        assert bad.status_code == 422
        codes = _hammer(
            lambda: client.raw().post(f"/api/content/approve/{TOKEN}", json={"decision": "approved"}),
            15,
        )
        assert 429 in codes
