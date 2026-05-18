"""Unit tests for `mcp/_kit` — the shared connector-MCP boilerplate.

Covers: settings env-vs-dotenv precedence + caching, registry trio
aggregation, typed_error shape, and bootstrap importability (without
requiring the PyPI `mcp` package to be installed — that import is
deferred inside `run_stdio_server`).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Put `mcp/` on sys.path so `from _kit.X import Y` resolves — same trick
# `mcp/vista/tests/*.py` uses.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from _kit.errors import typed_error
from _kit.registry import build_registry
from _kit.settings import ConnectorSettings, _load_dotenv, make_get_settings


# ─── errors.typed_error ──────────────────────────────────────────────────


def test_typed_error_three_key_shape_plain_exception():
    err = typed_error(ValueError("boom"))
    assert err == {"error_class": "ValueError", "message": "boom", "status": None}


def test_typed_error_reads_status_attr_when_present():
    class UpstreamError(Exception):
        status = 401

    err = typed_error(UpstreamError("denied"))
    assert err["error_class"] == "UpstreamError"
    assert err["message"] == "denied"
    assert err["status"] == 401


# ─── settings: dotenv parse + env/dotenv precedence + cache ──────────────


def _write_dotenv(tmp_path: Path, body: str) -> Path:
    (tmp_path / ".env").write_text(body, encoding="utf-8")
    return tmp_path


def test_load_dotenv_skips_blank_comment_and_no_eq_lines(tmp_path):
    _write_dotenv(
        tmp_path,
        "\n# a comment\nNOEQUALS\nVISTA_BASE_URL=https://api.example.com\n"
        'VISTA_API_KEY="quoted-secret"\n',
    )
    parsed = _load_dotenv(tmp_path / ".env")
    assert parsed == {
        "VISTA_BASE_URL": "https://api.example.com",
        "VISTA_API_KEY": "quoted-secret",
    }


def test_load_dotenv_missing_file_returns_empty(tmp_path):
    assert _load_dotenv(tmp_path / "nonexistent.env") == {}


@dataclass(frozen=True)
class _Demo(ConnectorSettings):
    base_url: Optional[str] = None
    api_key: Optional[str] = None

    @property
    def configured(self) -> bool:
        return bool(self.base_url) and bool(self.api_key)


def test_settings_dotenv_used_when_env_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("DEMO_BASE_URL", raising=False)
    monkeypatch.delenv("DEMO_API_KEY", raising=False)
    _write_dotenv(tmp_path, "DEMO_BASE_URL=https://dot.example\nDEMO_API_KEY=dotkey\n")
    get_settings = make_get_settings(
        _Demo,
        dotenv_dir=tmp_path,
        env_map={"base_url": "DEMO_BASE_URL", "api_key": "DEMO_API_KEY"},
    )
    s = get_settings()
    assert s.base_url == "https://dot.example"
    assert s.api_key == "dotkey"
    assert s.configured is True


def test_settings_env_wins_over_dotenv(tmp_path, monkeypatch):
    _write_dotenv(tmp_path, "DEMO_BASE_URL=https://dot.example\nDEMO_API_KEY=dotkey\n")
    monkeypatch.setenv("DEMO_BASE_URL", "https://env.example")
    monkeypatch.setenv("DEMO_API_KEY", "envkey")
    get_settings = make_get_settings(
        _Demo,
        dotenv_dir=tmp_path,
        env_map={"base_url": "DEMO_BASE_URL", "api_key": "DEMO_API_KEY"},
    )
    s = get_settings()
    assert s.base_url == "https://env.example"
    assert s.api_key == "envkey"


def test_settings_is_cached_and_clearable(tmp_path, monkeypatch):
    monkeypatch.delenv("DEMO_BASE_URL", raising=False)
    monkeypatch.delenv("DEMO_API_KEY", raising=False)
    _write_dotenv(tmp_path, "DEMO_BASE_URL=v1\n")
    get_settings = make_get_settings(
        _Demo, dotenv_dir=tmp_path, env_map={"base_url": "DEMO_BASE_URL"}
    )
    first = get_settings()
    # Re-write the dotfile; cached call must still return the old value.
    _write_dotenv(tmp_path, "DEMO_BASE_URL=v2\n")
    assert get_settings() is first
    assert get_settings().base_url == "v1"
    get_settings.cache_clear()
    assert get_settings().base_url == "v2"


def test_settings_missing_keys_resolve_to_none(tmp_path, monkeypatch):
    monkeypatch.delenv("DEMO_BASE_URL", raising=False)
    monkeypatch.delenv("DEMO_API_KEY", raising=False)
    get_settings = make_get_settings(
        _Demo,
        dotenv_dir=tmp_path,  # no .env present
        env_map={"base_url": "DEMO_BASE_URL", "api_key": "DEMO_API_KEY"},
    )
    s = get_settings()
    assert s.base_url is None
    assert s.api_key is None
    assert s.configured is False


# ─── registry.build_registry trio aggregation ────────────────────────────


class _FakeMod:
    def __init__(self, handlers, descriptors):
        self.HANDLERS = handlers
        self._descriptors = descriptors
        self.registered = False

    def tool_descriptors(self):
        return list(self._descriptors)

    def register(self, server):
        self.registered = True


def test_build_registry_aggregates_handlers_and_descriptors():
    async def h_a(args):
        return {}

    async def h_b(args):
        return {}

    m1 = _FakeMod({"v.a.list": h_a}, ["desc-a"])
    m2 = _FakeMod({"v.b.list": h_b}, ["desc-b1", "desc-b2"])
    all_handlers, all_descriptors, register_all = build_registry((m1, m2))

    assert set(all_handlers().keys()) == {"v.a.list", "v.b.list"}
    assert all_descriptors() == ["desc-a", "desc-b1", "desc-b2"]

    class _Srv:
        pass

    register_all(_Srv())
    assert m1.registered and m2.registered


def test_build_registry_empty_modules_returns_empty_trio():
    all_handlers, all_descriptors, _ = build_registry(())
    assert all_handlers() == {}
    assert all_descriptors() == []


# ─── bootstrap importability (no PyPI `mcp` required) ─────────────────────


def test_bootstrap_imports_without_mcp_package():
    """Importing `_kit.bootstrap` must NOT require the PyPI `mcp` package
    (the `mcp.server` import is deferred inside `run_stdio_server`)."""
    import importlib

    mod = importlib.import_module("_kit.bootstrap")
    assert hasattr(mod, "prepare_sys_path")
    assert hasattr(mod, "configure_stderr_logging")
    assert hasattr(mod, "run_stdio_server")


def test_prepare_sys_path_inserts_mcp_dir(tmp_path):
    from _kit.bootstrap import prepare_sys_path

    fake_server = tmp_path / "somevendor" / "server.py"
    fake_server.parent.mkdir(parents=True)
    fake_server.write_text("# stub", encoding="utf-8")
    before = list(sys.path)
    try:
        prepare_sys_path(fake_server)
        # parents[1] of .../somevendor/server.py == tmp_path
        assert str(tmp_path.resolve()) == sys.path[0]
    finally:
        sys.path[:] = before


def test_public_exports_surface():
    import _kit

    for name in (
        "ConnectorSettings",
        "make_get_settings",
        "build_registry",
        "typed_error",
        "prepare_sys_path",
        "configure_stderr_logging",
        "run_stdio_server",
    ):
        assert hasattr(_kit, name), f"{name} missing from _kit public surface"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
