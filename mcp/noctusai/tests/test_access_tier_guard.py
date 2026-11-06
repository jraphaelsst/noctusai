"""Red + green fixtures for the WRITE-time access-tier guard (`access_tier_guard.decide`, PreToolUse)."""
from __future__ import annotations

from tools.noctus.dev.access_tier_guard import decide

ROUTE = "products/agents/backend/app/routers/x_router.py"
MIG = "products/agents/backend/migrations/090_x.sql"


def _write(path, content):
    return decide("Write", {"file_path": f"/nonexistent/{path}", "content": content}, allow_override=False)


class TestRoutes:
    def test_undeclared_route_denied(self):
        out = _write(ROUTE, "@router.get('/x')\ndef x():\n    return 1\n")
        assert out and "without a declared access tier" in out["reason"]

    def test_gated_route_allowed(self):
        assert _write(ROUTE, "@router.get('/x')\ndef x(ctx=Depends(require_platform_admin)):\n    return 1\n") is None

    def test_public_needs_category(self):
        bad = "@router.get('/x')\n@access_tier('public', reason='y')\ndef x(): ...\n"
        assert _write(ROUTE, bad)
        ok = "@router.get('/x')\n@access_tier('public', reason='y', category='landing')\ndef x(): ...\n"
        assert _write(ROUTE, ok) is None

    def test_escape_with_reason(self):
        assert _write(ROUTE, "# access-tier-ok: internal probe\n@router.get('/x')\ndef x(): ...\n") is None

    def test_tests_and_non_backend_files_ignored(self):
        assert _write("products/agents/backend/tests/test_x.py", "@router.get('/x')\ndef x(): ...\n") is None
        assert _write("products/agents/frontend/src/x.py", "@router.get('/x')\ndef x(): ...\n") is None

    def test_only_added_routes_are_judged(self, tmp_path):
        f = tmp_path / "products/agents/backend/app/r.py"
        f.parent.mkdir(parents=True)
        f.write_text("@router.get('/old')\ndef old(): ...\n", encoding="utf-8")
        edit = {"file_path": str(f), "old_string": "x", "new_string": "# comment only\n"}
        assert decide("Edit", edit, allow_override=False) is None

    def test_override_env_flag(self):
        assert decide("Write", {"file_path": "/n/" + ROUTE, "content": "@router.get('/x')\ndef x(): ..."}, allow_override=True) is None


class TestMigrations:
    def test_table_without_tier_or_grants_denied(self):
        out = _write(MIG, "CREATE TABLE agents.w (id int);\n")
        assert out and "COMMENT ON TABLE" in out["reason"] and "GRANT/REVOKE" in out["reason"]

    def test_declared_table_allowed(self):
        sql = "CREATE TABLE agents.w (id int);\nCOMMENT ON TABLE agents.w IS 'tier:platform';\nREVOKE ALL ON agents.w FROM authenticated, anon;\n"
        assert _write(MIG, sql) is None

    def test_escape(self):
        assert _write(MIG, "-- noc-allow: access-tier-table — scratch\nCREATE TABLE agents.w (id int);\n") is None
