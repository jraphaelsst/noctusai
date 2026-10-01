"""Community's `TeamPolicy` on the seed `/api/team` router (app/main.py).

The community org is the shared platform org, so the Equipe roster must be
the community STAFF only (never another product's `corretor`, never a
`membro` customer), and an admin must be able to invite a `moderador` — the
role the pre-seam router could not grant.

Also pins `COMMUNITY_STAFF_ORG_ROLES` (the single Python source) to its SQL
twin, the role literal in the LATEST `community.eh_equipe()` definition.
"""
import re
from pathlib import Path

from app.dependencies import COMMUNITY_STAFF_ORG_ROLES
from tests.conftest import TEST_ORG_ID, TEST_USER_ID


def _row(uid: str, org_role, *, org_id: str = TEST_ORG_ID, role: str = "user") -> dict:
    return {
        "id": uid, "nome": uid, "email": f"{uid}@x.com", "org_id": org_id,
        "org_role": org_role, "role": role, "avatar_url": None,
        "created_at": "2026-01-01T00:00:00Z",
    }


class TestTeamPolicyContract:
    def test_policy_invites_admin_and_moderador_with_labels(self, client):
        resp = client.get("/api/team/policy")
        assert resp.status_code == 200
        body = resp.json()
        assert body["invitable_roles"] == ["admin", "moderador"]
        assert set(body["staff_roles"]) == set(COMMUNITY_STAFF_ORG_ROLES)
        assert body["labels"]["moderador"] == "Moderador"

    def test_policy_requires_auth_strict_401(self, client):
        assert client.raw().get("/api/team/policy").status_code == 401


class TestTeamRosterIsStaffOnly:
    def test_roster_excludes_non_staff_roles(self, client):
        client.mock_supabase.set_table_data("noctus_users", [
            _row(TEST_USER_ID, "admin"),
            _row("mod", "moderador"),
            _row("dev", "dev"),
            _row("corretor", "corretor"),   # another product's staff
            _row("cliente", "membro"),      # a community customer
            _row("member", "member"),       # a plain platform member
            _row("other-org", "admin", org_id="some-other-org"),
        ])
        resp = client.get("/api/team")
        assert resp.status_code == 200
        ids = {m["id"] for m in resp.json()["data"]}
        assert ids == {TEST_USER_ID, "mod", "dev"}

    def test_roster_requires_auth_strict_401(self, client):
        assert client.raw().get("/api/team").status_code == 401


class TestTeamInviteFollowsPolicy:
    def test_platform_member_role_is_not_invitable(self, client):
        client.mock_supabase.set_table_data("noctus_users", [_row(TEST_USER_ID, "admin")])
        resp = client.post("/api/team/invite", json={"email": "a@x.com", "role": "member"})
        assert resp.status_code == 400

    def test_invite_requires_auth_strict_401(self, client):
        resp = client.raw().post("/api/team/invite", json={"email": "a@x.com", "role": "moderador"})
        assert resp.status_code == 401


def _latest_eh_equipe_roles() -> set[str]:
    migrations = sorted(
        (Path(__file__).resolve().parents[1] / "migrations").glob("*.sql")
    )
    found = None
    for path in migrations:
        for m in re.finditer(
            r"FUNCTION\s+community\.eh_equipe\(\).*?org_role\s+IN\s*\(([^)]*)\)",
            path.read_text(),
            flags=re.S | re.I,
        ):
            found = m.group(1)
    assert found is not None, "community.eh_equipe() not found in migrations/"
    return set(re.findall(r"'([^']+)'", found))


def test_staff_roles_match_sql_eh_equipe():
    """`COMMUNITY_STAFF_ORG_ROLES` and `community.eh_equipe()` are one rule in
    two languages — the API gate, the Equipe roster and RLS must agree."""
    assert _latest_eh_equipe_roles() == set(COMMUNITY_STAFF_ORG_ROLES)
