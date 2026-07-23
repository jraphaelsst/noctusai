"""Tests for the n8n.credential.* tools.

No network: every test exercises pure validation (the confirm gate) or
injects a client via `n8n.client.configure_client(...)` — the seed's
`FakeN8nClient` for happy paths, a tiny local raising stub for the
typed-error paths. Dependency injection, NOT monkeypatching — see
`mcp/n8n/tests/test_smoke.py`'s module docstring for the full
rationale. Mirrors the sys.path trick of that file.

Pins, per the connector contract:
- the confirm gate (create/delete refuse + perform NO side-effect),
- happy create returns id/name/type (n8n never echoes the secret),
- happy delete removes the credential,
- schema is READ-ONLY (no confirm) and surfaces the raw schema,
- adapter failure ⇒ typed-error envelope (never a fabricated success),
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

import pytest


class _PoisonClient:
    """An `N8nClient` stand-in that raises on ANY method call — proves
    the confirm gate fires before the client is ever touched. Same
    shape as `test_smoke.py::_PoisonClient`."""

    def __getattr__(self, name):
        async def _boom(*args, **kwargs):
            raise AssertionError(
                f"client.{name}() must not be called before confirm=true"
            )
        return _boom


def _configure(client):
    from n8n import client as n8n_client
    n8n_client.configure_client(client)
    return n8n_client


# ─── Confirm gate — writes refuse + perform NO side-effect ───────────────


def test_credential_create_without_confirm_blocks_no_side_effect():
    from n8n.tools.credential import credential_create

    n8n_client = _configure(_PoisonClient())
    try:
        out = asyncio.run(
            credential_create(
                {"name": "hdr", "type": "httpHeaderAuth", "data": {"a": "b"}}
            )
        )
    finally:
        n8n_client.configure_client(None)
    assert out["created"] is False
    assert out["error"]["error_class"] == "ConfirmationRequiredError"
    assert out["error"]["status"] == 412


def test_credential_create_confirm_false_explicit_also_blocks():
    from n8n.tools.credential import credential_create

    n8n_client = _configure(_PoisonClient())
    try:
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
    finally:
        n8n_client.configure_client(None)
    assert out["created"] is False
    assert out["error"]["status"] == 412


def test_credential_delete_without_confirm_blocks_no_side_effect():
    from n8n.tools.credential import credential_delete

    n8n_client = _configure(_PoisonClient())
    try:
        out = asyncio.run(credential_delete({"id": "cred1"}))
    finally:
        n8n_client.configure_client(None)
    assert out["deleted"] is False
    assert out["error"]["error_class"] == "ConfirmationRequiredError"
    assert out["error"]["status"] == 412


# ─── Happy paths (injected FakeN8nClient) ────────────────────────────────


def test_credential_create_confirmed_returns_id_no_secret():
    """n8n echoes id/name/type but NEVER the secret `data` — output
    carries no `data` key."""
    from n8n.tools.credential import credential_create
    from noctusai_lib.integrations.n8n import FakeN8nClient

    fake = FakeN8nClient()
    n8n_client = _configure(fake)
    try:
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
    finally:
        n8n_client.configure_client(None)
    assert out["created"] is True
    assert out["id"] == "fake-cred-1"
    assert out["name"] == "hdr"
    assert out["type"] == "httpHeaderAuth"
    assert "data" not in out  # secret never round-trips back
    assert out["error"] is None


def test_credential_delete_confirmed_removes_it():
    from n8n.tools.credential import credential_create, credential_delete
    from noctusai_lib.integrations.n8n import FakeN8nClient, N8nNotFoundError

    fake = FakeN8nClient()
    n8n_client = _configure(fake)
    try:
        created = asyncio.run(
            credential_create(
                {"name": "hdr", "type": "httpHeaderAuth", "data": {}, "confirm": True}
            )
        )
        out = asyncio.run(
            credential_delete({"id": created["id"], "confirm": True})
        )
    finally:
        n8n_client.configure_client(None)
    assert out["deleted"] is True
    assert out["id"] == created["id"]
    assert out["error"] is None
    with pytest.raises(N8nNotFoundError):
        asyncio.run(fake.delete_credential(created["id"]))


def test_credential_schema_is_read_only_no_confirm_needed():
    """schema takes no confirm and surfaces the seed's canned schema."""
    from n8n.tools.credential import credential_schema
    from noctusai_lib.integrations.n8n import FakeN8nClient

    fake = FakeN8nClient()
    n8n_client = _configure(fake)
    try:
        out = asyncio.run(
            credential_schema({"credential_type_name": "httpHeaderAuth"})
        )
    finally:
        n8n_client.configure_client(None)
    assert out["credential_type_name"] == "httpHeaderAuth"
    assert out["schema"]["required"] == ["name", "value"]
    assert out["error"] is None


# ─── Typed-error on adapter failure (never a fabricated success) ────────


def test_credential_create_api_failure_returns_typed_error():
    from n8n.tools.credential import credential_create
    from noctusai_lib.integrations.n8n import N8nRejectedError

    class _RejectingClient:
        async def create_credential(self, **kw):
            raise N8nRejectedError("n8n rejected the payload", status=400)

    n8n_client = _configure(_RejectingClient())
    try:
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
    finally:
        n8n_client.configure_client(None)
    assert out["created"] is False
    assert out["error"]["status"] == 400
    assert out["error"]["error_class"] == "N8nApiError"


def test_credential_delete_api_failure_returns_typed_error_with_id():
    from n8n.tools.credential import credential_delete
    from noctusai_lib.integrations.n8n import N8nNotFoundError

    class _NotFoundClient:
        async def delete_credential(self, credential_id):
            raise N8nNotFoundError("not found", status=404)

    n8n_client = _configure(_NotFoundClient())
    try:
        out = asyncio.run(
            credential_delete({"id": "ghost", "confirm": True})
        )
    finally:
        n8n_client.configure_client(None)
    assert out["deleted"] is False
    assert out["id"] == "ghost"
    assert out["error"]["status"] == 404


def test_credential_schema_not_configured_returns_typed_424():
    from n8n.tools.credential import credential_schema
    from n8n.settings import N8nConnectorSettings

    with patch("n8n.client.get_settings",
               return_value=N8nConnectorSettings()):
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
