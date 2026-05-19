"""Tests for the n8n.credential.* tools.

No network: every test either exercises pure validation (the confirm
gate) or `unittest.mock.patch`-es the external HTTP seam
(`n8n.api.request_json`). Patching an external service is sanctioned by
CLAUDE.md §1; our own code is never patched. Mirrors the seam +
sys.path trick of `mcp/n8n/tests/test_smoke.py`.

Pins, per the connector contract:
- the confirm gate (create/delete refuse + perform NO side-effect),
- happy create returns id/name/type (n8n never echoes the secret),
- happy delete issues DELETE /credentials/{id},
- schema is READ-ONLY (no confirm) and surfaces the raw schema,
- API failure ⇒ typed-error envelope (never a fabricated success),
- the n8n no-list/get design omission is intentional (no such tool).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

# Put `mcp/` on sys.path so `from n8n.X import ...` + `from _kit.X
# import ...` resolve — same trick mcp/n8n/tests/test_smoke.py uses.
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "mcp"))

# `noctusai_lib` (transitively pulled by `_kit`) MUST resolve against
# THIS worktree's seed — same editable-finder eviction test_smoke does.
_SEED = _REPO_ROOT / "seed" / "lib" / "backend"
_seed_lib = _SEED / "noctusai_lib"


def _resolves_to_this_worktree() -> bool:
    try:
        import noctusai_lib  # noqa
    except ModuleNotFoundError:
        return False
    f = getattr(noctusai_lib, "__file__", "") or ""
    return str(_seed_lib) in f


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


# ─── Confirm gate — writes refuse + perform NO side-effect ───────────────


def test_credential_create_without_confirm_blocks_no_side_effect():
    from n8n.tools.credential import credential_create

    with patch("n8n.api.request_json") as req:
        out = asyncio.run(
            credential_create(
                {"name": "hdr", "type": "httpHeaderAuth", "data": {"a": "b"}}
            )
        )
    req.assert_not_called()  # NO HTTP — the gate fired first
    assert out["created"] is False
    assert out["error"]["error_class"] == "ConfirmationRequiredError"
    assert out["error"]["status"] == 412


def test_credential_create_confirm_false_explicit_also_blocks():
    from n8n.tools.credential import credential_create

    with patch("n8n.api.request_json") as req:
        out = asyncio.run(
            credential_create(
                {
                    "name": "hdr",
                    "type": "httpHeaderAuth",
                    "data": {"a": "b"},
                    "confirm": False,
                }
            )
        )
    req.assert_not_called()
    assert out["created"] is False
    assert out["error"]["status"] == 412


def test_credential_delete_without_confirm_blocks_no_side_effect():
    from n8n.tools.credential import credential_delete

    with patch("n8n.api.request_json") as req:
        out = asyncio.run(credential_delete({"id": "cred1"}))
    req.assert_not_called()
    assert out["deleted"] is False
    assert out["error"]["error_class"] == "ConfirmationRequiredError"
    assert out["error"]["status"] == 412


# ─── Happy paths (external HTTP seam patched) ────────────────────────────


def test_credential_create_confirmed_posts_and_returns_id_no_secret():
    """POST /credentials with {name,type,data}; n8n echoes id/name/type
    but NEVER the secret `data` — output carries no `data` key."""
    from n8n.tools.credential import credential_create

    captured = {}

    def _cap(method, path, **kw):
        captured.update(method=method, path=path, body=kw.get("body"))
        # n8n's real create response shape — note: no `data`.
        return {"id": "9xZ", "name": "hdr", "type": "httpHeaderAuth"}

    with patch("n8n.api.request_json", side_effect=_cap):
        out = asyncio.run(
            credential_create(
                {
                    "name": "hdr",
                    "type": "httpHeaderAuth",
                    "data": {"name": "X-Api-Key", "value": "s3cr3t"},
                    "confirm": True,
                }
            )
        )
    assert captured["method"] == "POST"
    assert captured["path"] == "/credentials"
    assert captured["body"] == {
        "name": "hdr",
        "type": "httpHeaderAuth",
        "data": {"name": "X-Api-Key", "value": "s3cr3t"},
    }
    assert out["created"] is True
    assert out["id"] == "9xZ"
    assert out["name"] == "hdr"
    assert out["type"] == "httpHeaderAuth"
    assert "data" not in out  # secret never round-trips back
    assert out["error"] is None


def test_credential_delete_confirmed_calls_delete_verb():
    from n8n.tools.credential import credential_delete

    captured = {}

    def _cap(method, path, **kw):
        captured.update(method=method, path=path)
        return {}

    with patch("n8n.api.request_json", side_effect=_cap):
        out = asyncio.run(
            credential_delete({"id": "cred1", "confirm": True})
        )
    assert captured["method"] == "DELETE"
    assert captured["path"] == "/credentials/cred1"
    assert out["deleted"] is True
    assert out["id"] == "cred1"
    assert out["error"] is None


def test_credential_schema_is_read_only_no_confirm_needed():
    """schema takes no confirm and GETs /credentials/schema/{type}."""
    from n8n.tools.credential import credential_schema

    captured = {}
    schema_payload = {
        "type": "object",
        "required": ["name", "value"],
        "properties": {"name": {"type": "string"}, "value": {"type": "string"}},
    }

    def _cap(method, path, **kw):
        captured.update(method=method, path=path)
        return schema_payload

    with patch("n8n.api.request_json", side_effect=_cap):
        out = asyncio.run(
            credential_schema({"credential_type_name": "httpHeaderAuth"})
        )
    assert captured["method"] == "GET"
    assert captured["path"] == "/credentials/schema/httpHeaderAuth"
    assert out["credential_type_name"] == "httpHeaderAuth"
    assert out["schema"] == schema_payload
    assert out["error"] is None


# ─── Typed-error on API failure (never a fabricated success) ─────────────


def test_credential_create_api_failure_returns_typed_error():
    from n8n.tools.credential import credential_create
    from n8n import api

    def _boom(*a, **kw):
        raise api.N8nApiError("n8n API POST /credentials → HTTP 400", status=400)

    with patch("n8n.api.request_json", side_effect=_boom):
        out = asyncio.run(
            credential_create(
                {
                    "name": "hdr",
                    "type": "httpHeaderAuth",
                    "data": {"a": "b"},
                    "confirm": True,
                }
            )
        )
    assert out["created"] is False
    assert out["error"]["status"] == 400
    assert out["error"]["error_class"] == "N8nApiError"


def test_credential_delete_api_failure_returns_typed_error_with_id():
    from n8n.tools.credential import credential_delete
    from n8n import api

    def _boom(*a, **kw):
        raise api.N8nApiError("not found", status=404)

    with patch("n8n.api.request_json", side_effect=_boom):
        out = asyncio.run(
            credential_delete({"id": "ghost", "confirm": True})
        )
    assert out["deleted"] is False
    assert out["id"] == "ghost"
    assert out["error"]["status"] == 404


def test_credential_schema_api_failure_returns_typed_error():
    from n8n.tools.credential import credential_schema
    from n8n import api

    def _boom(*a, **kw):
        raise api.N8nApiError("not configured", status=424)

    with patch("n8n.api.request_json", side_effect=_boom):
        out = asyncio.run(
            credential_schema({"credential_type_name": "httpHeaderAuth"})
        )
    assert out["schema"] is None
    assert out["error"]["status"] == 424


# ─── Gated-capability honesty — the no-list/get omission is intentional ──


def test_no_list_or_get_credential_tool_exists():
    """n8n stores credential secrets write-only by design; we do NOT
    invent a list/get tool that would either lie or leak. The credential
    leaf exposes exactly create/delete/schema."""
    from n8n.tools import credential

    assert set(credential.HANDLERS) == {
        "n8n.credential.create",
        "n8n.credential.delete",
        "n8n.credential.schema",
    }
    for bad in ("list", "get", "read"):
        assert f"n8n.credential.{bad}" not in credential.HANDLERS
