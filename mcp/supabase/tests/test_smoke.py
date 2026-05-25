"""Smoke tests for the Supabase connector MCP.

No network: pure validation (confirm gate, settings, SQL read/write
classification) or `unittest.mock.patch` on the external HTTP seam
(`supabase.api.request_json` / `urlopen`). Patching an external service
is sanctioned by CLAUDE.md §1; our own code is never patched. Mirrors
`mcp/cloudflare/tests/test_smoke.py`.

NOTE — live validation deferred. There is no live Supabase token at build
(`mcp/supabase/.env` `SUPABASE_ACCESS_TOKEN` is empty, pasted by the user
later). Shapes here were verified against the live Supabase Management
API v1 OpenAPI spec (`https://api.supabase.com/api/v1-json` —
codebase-is-source-of-truth applied to an external API: shapes verified,
not assumed); end-to-end live probing is deferred until the user adds a
token.

Pins: the exact registered tool-name set, 3-segment dotted naming under
`supabase.*`, the confirm gate (db.query write + migration.apply refuse +
NO side-effect; db.query read runs free), the best-effort SQL read/write
heuristic, gated-capability honesty (not-configured ⇒ typed 424; the
connection_status tri-state), the Bearer + plain-UA header, project-ref
resolution (arg wins over default; missing ⇒ 424), registry coherence.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "mcp"))

# `noctusai_lib` (transitively via `_kit`) must resolve to THIS
# worktree's seed — same editable-finder eviction mcp/cloudflare/tests does.
_SEED = _REPO_ROOT / "seed" / "lib" / "backend"
_seed_lib = _SEED / "noctusai_lib"


def _resolves_to_this_worktree() -> bool:
    try:
        import noctusai_lib  # noqa
    except ModuleNotFoundError:
        return False
    return str(_seed_lib) in (getattr(noctusai_lib, "__file__", "") or "")


if not _resolves_to_this_worktree():
    def _is_noctus_editable_finder(mp) -> bool:
        mod = getattr(mp, "__module__", "") or ""
        nm = getattr(mp, "__name__", "") or ""
        return "__editable__" in mod and nm == "_EditableFinder"

    sys.meta_path = [
        mp for mp in sys.meta_path if not _is_noctus_editable_finder(mp)
    ]
    for _name in list(sys.modules):
        if _name == "noctusai_lib" or _name.startswith("noctusai_lib."):
            del sys.modules[_name]

sys.path.insert(0, str(_SEED))

import pytest

_EXPECTED_TOOLS = {
    "supabase.project.list",
    "supabase.project.get",
    "supabase.db.query",
    "supabase.db.list_tables",
    "supabase.db.list_schemas",
    "supabase.migration.list",
    "supabase.migration.apply",
    "supabase.diagnostics.connection_status",
}

_WRITE_GATES = {
    "supabase.db.query",  # only when SQL is non-read
    "supabase.migration.apply",
}


def _configured_settings(**over):
    from supabase.settings import SupabaseConnectorSettings

    base = dict(access_token="tok", project_ref="ref123")
    base.update(over)
    return SupabaseConnectorSettings(**base)


# ─── Composition / registry coherence ────────────────────────────────────


def test_package_imports():
    from supabase import api, settings, types  # noqa: F401
    from supabase.tools import db, diagnostics, migration, project  # noqa: F401
    from _kit import build_registry, typed_error  # noqa: F401

    assert hasattr(api, "request_json")
    assert hasattr(db, "is_read_only_sql")


def test_registered_tool_name_set_is_pinned():
    from supabase.tools import all_handlers

    assert set(all_handlers().keys()) == _EXPECTED_TOOLS


def test_descriptors_match_handlers():
    from supabase.tools import all_descriptors, all_handlers

    assert {d.name for d in all_descriptors()} == set(all_handlers())


def test_dotted_naming_convention():
    from supabase.tools import all_handlers

    for name in all_handlers():
        parts = name.split(".")
        assert len(parts) == 3, f"{name!r} not 3-segment dotted"
        assert parts[0] == "supabase", f"{name!r} not under supabase.*"


# ─── Settings ────────────────────────────────────────────────────────────


def test_settings_lenient_no_config():
    from supabase.settings import SupabaseConnectorSettings

    s = SupabaseConnectorSettings()
    assert s.configured is False
    # base_url defaults to the canonical Supabase Management base.
    assert s.root == "https://api.supabase.com"


def test_normalize_base_url_defaults_to_canonical_base():
    from supabase.api import DEFAULT_BASE_URL, normalize_base_url

    assert normalize_base_url("") == DEFAULT_BASE_URL
    assert normalize_base_url("https://x.test/") == "https://x.test"


# ─── Bearer + plain UA (no WAF trick) ────────────────────────────────────


def test_request_json_sends_bearer_and_plain_user_agent():
    """request_json MUST send Bearer auth + a plain (non-browser) UA — the
    Supabase Management API is not WAF-gated, so no browser impersonation.
    We patch urlopen (the stdlib boundary, an external service) and inspect
    the Request — our own code is never patched."""
    from supabase import api

    captured = {}

    class _Resp:
        status = 200

        def read(self):
            return b'[{"id": "p1", "ref": "ref123"}]'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=None):
        captured["headers"] = dict(req.headers)
        captured["url"] = req.full_url
        return _Resp()

    # urlopen now lives in the shared `_kit.transport` seam (the connector
    # delegates its urllib mechanics there); patch it at the boundary.
    with patch("_kit.transport.urlopen", side_effect=_fake_urlopen):
        out = api.request_json("GET", "/v1/projects", access_token="tok")
    assert out == [{"id": "p1", "ref": "ref123"}]
    # urllib title-cases header keys.
    assert captured["headers"]["Authorization"] == "Bearer tok"
    ua = captured["headers"]["User-agent"]
    assert "Mozilla/5.0" not in ua  # NOT a browser impersonation UA
    assert "supabase" in ua.lower()
    assert captured["url"].startswith("https://api.supabase.com")


def test_request_json_no_token_is_typed_424():
    from supabase import api

    with pytest.raises(api.SupabaseApiError) as ei:
        api.request_json("GET", "/v1/projects", access_token="")
    assert ei.value.status == 424


def test_request_json_http_error_passes_status_and_message():
    """A non-2xx is surfaced as a typed SupabaseApiError carrying the
    upstream status + the Management API's `{"message": ...}` detail."""
    import io
    import urllib.error

    from supabase import api

    err = urllib.error.HTTPError(
        url="https://api.supabase.com/v1/projects",
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=io.BytesIO(b'{"message": "Invalid access token"}'),
    )
    with patch("_kit.transport.urlopen", side_effect=err):
        with pytest.raises(api.SupabaseApiError) as ei:
            api.request_json("GET", "/v1/projects", access_token="tok")
    assert ei.value.status == 401
    assert "Invalid access token" in str(ei.value)


# ─── SQL read/write heuristic (best-effort) ──────────────────────────────


def test_is_read_only_sql_classifies_reads_and_writes():
    from supabase.tools.db import is_read_only_sql

    assert is_read_only_sql("SELECT 1") is True
    assert is_read_only_sql("  select * from t") is True
    assert is_read_only_sql("EXPLAIN SELECT 1") is True
    assert is_read_only_sql("WITH x AS (SELECT 1) SELECT * FROM x") is True
    assert is_read_only_sql("-- comment\nSELECT 1") is True
    assert is_read_only_sql("/* c */ SELECT 1") is True

    assert is_read_only_sql("INSERT INTO t VALUES (1)") is False
    assert is_read_only_sql("UPDATE t SET a=1") is False
    assert is_read_only_sql("DELETE FROM t") is False
    assert is_read_only_sql("CREATE TABLE t (id int)") is False
    assert is_read_only_sql("DROP TABLE t") is False
    assert is_read_only_sql("TRUNCATE t") is False


# ─── Confirm gate — writes refuse + perform NO side-effect ───────────────


def test_db_query_write_confirm_gated_no_side_effect():
    from supabase.tools.db import db_query

    with patch("supabase.tools.db.get_settings",
               return_value=_configured_settings()), patch(
        "supabase.api.request_json"
    ) as req:
        out = asyncio.run(db_query({"query": "DELETE FROM t"}))
    req.assert_not_called()  # gate fired before any HTTP
    assert out["error"]["error_class"] == "ConfirmationRequiredError"
    assert out["error"]["status"] == 412
    assert out["read_only"] is False


def test_migration_apply_confirm_gated_no_side_effect():
    from supabase.tools.migration import migration_apply

    with patch("supabase.tools.migration.get_settings",
               return_value=_configured_settings()), patch(
        "supabase.api.request_json"
    ) as req:
        out = asyncio.run(migration_apply({"query": "create table x(id int)"}))
    req.assert_not_called()
    assert out["error"]["error_class"] == "ConfirmationRequiredError"
    assert out["error"]["status"] == 412


def test_db_query_read_runs_free_no_confirm():
    """A SELECT runs WITHOUT confirm and hits POST .../database/query with
    read_only=True."""
    from supabase.tools.db import db_query

    captured = {}

    def _cap(method, path, **kw):
        captured.update(method=method, path=path, body=kw.get("body"))
        return [{"n": 1}]

    with patch("supabase.tools.db.get_settings",
               return_value=_configured_settings()), patch(
        "supabase.api.request_json", side_effect=_cap
    ):
        out = asyncio.run(db_query({"query": "SELECT 1 AS n"}))
    assert captured["method"] == "POST"
    assert captured["path"] == "/v1/projects/ref123/database/query"
    assert captured["body"]["query"] == "SELECT 1 AS n"
    assert captured["body"]["read_only"] is True
    assert out["ok"] is True
    assert out["read_only"] is True
    assert out["rows"] == [{"n": 1}]


def test_db_query_write_confirmed_posts_with_read_only_false():
    from supabase.tools.db import db_query

    captured = {}

    def _cap(method, path, **kw):
        captured.update(method=method, path=path, body=kw.get("body"))
        return None

    with patch("supabase.tools.db.get_settings",
               return_value=_configured_settings()), patch(
        "supabase.api.request_json", side_effect=_cap
    ):
        out = asyncio.run(db_query({
            "query": "INSERT INTO t VALUES (1)", "confirm": True,
        }))
    assert captured["method"] == "POST"
    assert captured["body"]["read_only"] is False
    assert out["ok"] is True
    assert out["read_only"] is False


def test_migration_apply_confirmed_posts_migration():
    from supabase.tools.migration import migration_apply

    captured = {}

    def _cap(method, path, **kw):
        captured.update(method=method, path=path, body=kw.get("body"))
        return {"version": "20260521"}

    with patch("supabase.tools.migration.get_settings",
               return_value=_configured_settings()), patch(
        "supabase.api.request_json", side_effect=_cap
    ):
        out = asyncio.run(migration_apply({
            "query": "create table x(id int)", "name": "add_x", "confirm": True,
        }))
    assert captured["method"] == "POST"
    assert captured["path"] == "/v1/projects/ref123/database/migrations"
    assert captured["body"]["query"] == "create table x(id int)"
    assert captured["body"]["name"] == "add_x"
    assert out["ok"] is True


# ─── information_schema-backed reads ─────────────────────────────────────


def test_db_list_tables_queries_information_schema():
    from supabase.tools.db import db_list_tables

    captured = {}

    def _cap(method, path, **kw):
        captured.update(path=path, body=kw.get("body"))
        return [{"table_schema": "public", "table_name": "users"}]

    with patch("supabase.tools.db.get_settings",
               return_value=_configured_settings()), patch(
        "supabase.api.request_json", side_effect=_cap
    ):
        out = asyncio.run(db_list_tables({"schema_name": "public"}))
    assert captured["path"] == "/v1/projects/ref123/database/query"
    assert "information_schema.tables" in captured["body"]["query"]
    assert "table_schema = 'public'" in captured["body"]["query"]
    assert captured["body"]["read_only"] is True
    assert out["ok"] is True


def test_db_list_schemas_excludes_internals():
    from supabase.tools.db import db_list_schemas

    captured = {}

    def _cap(method, path, **kw):
        captured.update(body=kw.get("body"))
        return [{"schema_name": "public"}]

    with patch("supabase.tools.db.get_settings",
               return_value=_configured_settings()), patch(
        "supabase.api.request_json", side_effect=_cap
    ):
        out = asyncio.run(db_list_schemas({}))
    q = captured["body"]["query"]
    assert "information_schema.schemata" in q
    assert "pg_catalog" in q
    assert out["ok"] is True


# ─── Project-ref resolution (arg wins; missing ⇒ 424) ────────────────────


def test_project_get_uses_arg_ref_over_default():
    from supabase.tools.project import project_get

    captured = {}

    def _cap(method, path, **kw):
        captured.update(path=path)
        return {"id": "p", "ref": "argref"}

    with patch("supabase.tools.project.get_settings",
               return_value=_configured_settings()), patch(
        "supabase.api.request_json", side_effect=_cap
    ):
        out = asyncio.run(project_get({"project_ref": "argref"}))
    assert captured["path"] == "/v1/projects/argref"
    assert out["project"]["ref"] == "argref"


def test_db_query_without_any_ref_typed_424_not_fake():
    from supabase.tools.db import db_query

    with patch("supabase.tools.db.get_settings",
               return_value=_configured_settings(project_ref=None)):
        out = asyncio.run(db_query({"query": "SELECT 1"}))
    assert out["rows"] is None
    assert out["error"]["status"] == 424


def test_migration_apply_without_ref_after_confirm_typed_424():
    from supabase.tools.migration import migration_apply

    with patch("supabase.tools.migration.get_settings",
               return_value=_configured_settings(project_ref=None)):
        out = asyncio.run(migration_apply({
            "query": "create table x(id int)", "confirm": True,
        }))
    assert out["error"]["status"] == 424


# ─── Gated-capability honesty ────────────────────────────────────────────


def test_project_list_not_configured_typed_424_not_fake():
    from supabase.tools.project import project_list
    from supabase.settings import SupabaseConnectorSettings

    with patch("supabase.tools.project.get_settings",
               return_value=SupabaseConnectorSettings()):
        out = asyncio.run(project_list({}))
    assert out["projects"] == []
    assert out["error"]["status"] == 424


def test_db_query_surfaces_upstream_error_not_fake():
    """An upstream error (e.g. SQL syntax → 4xx) reaches the tool as a
    SupabaseApiError; the tool surfaces it, never fabricated rows."""
    from supabase.tools.db import db_query
    from supabase import api

    err = api.SupabaseApiError("HTTP 400: syntax error", status=400)
    with patch("supabase.tools.db.get_settings",
               return_value=_configured_settings()), patch(
        "supabase.api.request_json", side_effect=err
    ):
        out = asyncio.run(db_query({"query": "SELECT bad syntax"}))
    assert out["rows"] is None
    assert out["error"]["status"] == 400


def test_connection_status_tri_state():
    from supabase.tools.diagnostics import connection_status
    from supabase.settings import SupabaseConnectorSettings
    from supabase import api

    s = _configured_settings()

    # not configured
    with patch("supabase.tools.diagnostics.get_settings",
               return_value=SupabaseConnectorSettings()):
        out = asyncio.run(connection_status({}))
    assert out["configured"] is False and out["error"]["status"] == 424

    # host down / unreachable (network failure → 502)
    with patch("supabase.tools.diagnostics.get_settings", return_value=s), patch(
        "supabase.api.request_json",
        side_effect=api.SupabaseApiError("unreachable", status=502),
    ):
        out = asyncio.run(connection_status({}))
    assert out["reachable"] is False and out["authenticated"] is False

    # token rejected (401 → reachable but not authenticated)
    with patch("supabase.tools.diagnostics.get_settings", return_value=s), patch(
        "supabase.api.request_json",
        side_effect=api.SupabaseApiError("HTTP 401", status=401),
    ):
        out = asyncio.run(connection_status({}))
    assert out["reachable"] is True
    assert out["authenticated"] is False
    assert out["error"]["status"] == 401

    # ok (2xx verified)
    with patch("supabase.tools.diagnostics.get_settings", return_value=s), patch(
        "supabase.api.request_json",
        return_value=[{"id": "p1", "ref": "ref123"}],
    ):
        out = asyncio.run(connection_status({}))
    assert out["reachable"] is True
    assert out["authenticated"] is True
    assert out["project_ref_present"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
