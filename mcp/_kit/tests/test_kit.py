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


# ─── seed_pin.pin_in_tree_seed ───────────────────────────────────────────

from _kit.seed_pin import (  # noqa: E402
    _find_worktree_root,
    _looks_like_noctus_editable_finder,
    pin_in_tree_seed,
)


def _make_worktree(tmp_path: Path) -> Path:
    """Build a synthetic worktree root: `.git` marker + seed/lib/backend."""
    root = tmp_path / "wt"
    (root / "seed" / "lib" / "backend" / "noctusai_lib").mkdir(parents=True)
    (root / ".git").mkdir()
    return root


class _StaleEditableFinder:
    """Mimics setuptools' `_EditableFinder` pinning noctusai_lib to a
    DIFFERENT (out-of-tree) worktree via the `_mapping` dict attr."""

    def __init__(self, pinned_path: str):
        self._mapping = {"noctusai_lib": pinned_path}

    # MetaPathFinder protocol — never actually consulted in these tests
    # (we assert eviction, not import resolution).
    def find_spec(self, *a, **k):  # pragma: no cover - protocol stub
        return None


class _UnrelatedFinder:
    """A meta-path finder with no noctusai_lib mapping — must survive."""

    def __init__(self):
        self._mapping = {"some_other_pkg": "/wherever"}

    def find_spec(self, *a, **k):  # pragma: no cover - protocol stub
        return None


@pytest.fixture
def _restore_sys(monkeypatch):
    """Snapshot/restore sys.path, sys.meta_path, and noctusai_lib*
    modules so a test's synthetic pin never leaks into the suite."""
    saved_path = list(sys.path)
    saved_meta = list(sys.meta_path)
    saved_mods = {
        k: v for k, v in sys.modules.items() if k.startswith("noctusai_lib")
    }
    yield
    sys.path[:] = saved_path
    sys.meta_path[:] = saved_meta
    for k in [k for k in sys.modules if k.startswith("noctusai_lib")]:
        del sys.modules[k]
    sys.modules.update(saved_mods)


def test_find_worktree_root_walks_to_git_plus_seed_marker(tmp_path):
    root = _make_worktree(tmp_path)
    deep = root / "mcp" / "google"
    deep.mkdir(parents=True)
    assert _find_worktree_root(deep / "server.py") == root.resolve()


def test_pin_evicts_out_of_tree_editable_finder(tmp_path, _restore_sys):
    root = _make_worktree(tmp_path)
    stale = _StaleEditableFinder("/some/OTHER/agent-worktree/seed/lib/backend")
    unrelated = _UnrelatedFinder()
    sys.meta_path[:0] = [stale, unrelated]

    returned = pin_in_tree_seed(root / "mcp" / "x" / "server.py")

    assert stale not in sys.meta_path, "out-of-tree finder must be evicted"
    assert unrelated in sys.meta_path, "unrelated finder must survive"
    assert returned == (root / "seed" / "lib" / "backend").resolve()
    assert sys.path[0] == str((root / "seed" / "lib" / "backend").resolve())


def test_pin_keeps_in_tree_editable_finder(tmp_path, _restore_sys):
    root = _make_worktree(tmp_path)
    in_tree = str((root / "seed" / "lib" / "backend").resolve())
    keeper = _StaleEditableFinder(in_tree)  # already points in-tree
    sys.meta_path.insert(0, keeper)

    pin_in_tree_seed(root / "server.py")

    assert keeper in sys.meta_path, "in-tree editable finder must NOT be evicted"


def test_pin_purges_stale_cached_noctusai_lib_modules(tmp_path, _restore_sys):
    root = _make_worktree(tmp_path)
    import types as _types

    sys.modules["noctusai_lib"] = _types.ModuleType("noctusai_lib")
    sys.modules["noctusai_lib.integrations"] = _types.ModuleType(
        "noctusai_lib.integrations"
    )

    pin_in_tree_seed(root / "server.py")

    assert "noctusai_lib" not in sys.modules
    assert "noctusai_lib.integrations" not in sys.modules


def test_pin_is_idempotent_single_path_entry(tmp_path, _restore_sys):
    root = _make_worktree(tmp_path)
    target = str((root / "seed" / "lib" / "backend").resolve())

    pin_in_tree_seed(root / "server.py")
    pin_in_tree_seed(root / "server.py")
    pin_in_tree_seed(root / "server.py")

    assert sys.path[0] == target
    assert sys.path.count(target) == 1, "repeated pin must not grow sys.path"


def test_pin_evicts_no_mapping_noctus_editable_finder(tmp_path, _restore_sys):
    """A noctus editable finder exposing no readable mapping is matched
    by the name-based fallback and evicted (assumed stale)."""
    root = _make_worktree(tmp_path)

    class _NoMappingEditable:
        __module__ = "__editable___noctusai_lib_0_1_finder"
        __name__ = "_EditableFinder"

        def find_spec(self, *a, **k):  # pragma: no cover - stub
            return None

    finder = _NoMappingEditable()
    assert _looks_like_noctus_editable_finder(finder) is True
    sys.meta_path.insert(0, finder)

    pin_in_tree_seed(root / "server.py")

    assert finder not in sys.meta_path


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
