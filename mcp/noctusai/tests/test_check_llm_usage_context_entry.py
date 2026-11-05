"""`check_llm_usage_context_entry`: metered LLM calls need an llm_usage_context scope (or an allowlist reason)."""
from __future__ import annotations

import sys
from pathlib import Path
from textwrap import dedent

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import compliance
from tools.noctus.dev.compliance import check_llm_usage_context_entry


def _product(tmp_path: Path, name: str, src: str) -> None:
    app = tmp_path / "products" / "demo" / "backend" / "app"
    app.mkdir(parents=True, exist_ok=True)
    (app / name).write_text(dedent(src), encoding="utf-8")


def _issues(tmp_path):
    return check_llm_usage_context_entry(tmp_path)


def test_flags_unscoped_call(tmp_path, monkeypatch):
    monkeypatch.setattr(compliance, "_active_product_dirs", lambda d: [d / "demo"])
    _product(tmp_path, "a.py", "async def f():\n    return await chat_with_tools([], [])\n")
    assert len(_issues(tmp_path)) == 1


def test_scoped_file_is_clean(tmp_path, monkeypatch):
    monkeypatch.setattr(compliance, "_active_product_dirs", lambda d: [d / "demo"])
    _product(tmp_path, "a.py", """
        async def f():
            with llm_usage_context(agent_key="x"):
                return await chat_with_tools([], [])
        """)
    assert _issues(tmp_path) == []


def test_allowlisted_file_is_clean(tmp_path, monkeypatch):
    monkeypatch.setattr(compliance, "_active_product_dirs", lambda d: [d / "demo"])
    monkeypatch.setitem(compliance._LLM_USAGE_CONTEXT_ALLOWLIST, "demo/backend/app/a.py", "reason")
    _product(tmp_path, "a.py", "async def f():\n    return await chat_completion([])\n")
    assert _issues(tmp_path) == []
