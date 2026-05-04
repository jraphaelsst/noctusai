"""Memory IO tests — round-trip per scope + snapshot shape.

All tests use ``tmp_path`` so the real
``dev_team/src/dev_team/memory/store/`` directory is never touched.
The ``shared.set_store_root`` call also propagates the override into
``craft.set_store_root`` so both halves of the memory live under the
isolated tmp dir.
"""
from __future__ import annotations

import pytest

from dev_team.memory.shared import MemoryStore, set_store_root, get_store_root


@pytest.fixture(autouse=True)
def isolate_store(tmp_path, request):
    """Every test gets a clean store rooted at ``tmp_path``."""
    set_store_root(tmp_path)
    yield
    # Reset to module default so suite-wide state doesn't leak.
    from pathlib import Path

    default = Path(__file__).resolve().parent.parent / "src" / "dev_team" / "memory" / "store"
    set_store_root(default)


def test_snapshot_returns_required_keys():
    store = MemoryStore(project="example")
    snap = store.snapshot()

    assert set(snap.keys()) == {"project", "current_phase", "last_verification"}
    assert snap["project"] == "example"
    # Fresh store — neither key has been written yet.
    assert snap["current_phase"] is None
    assert snap["last_verification"] is None


def test_state_scope_round_trip():
    store = MemoryStore(project="proj-a")

    store.write("state", "current_phase", "Phase 2")
    store.write("state", "last_verification", "green at 12:34Z")

    assert store.read("state", "current_phase") == "Phase 2"
    assert store.read("state", "last_verification") == "green at 12:34Z"

    snap = store.snapshot()
    assert snap["current_phase"] == "Phase 2"
    assert snap["last_verification"] == "green at 12:34Z"


def test_state_scope_handles_complex_values():
    store = MemoryStore(project="proj-b")

    payload = {"phase": 3, "tasks": ["a", "b"], "meta": {"owner": "leader"}}
    store.write("state", "phase_meta", payload)

    assert store.read("state", "phase_meta") == payload


def test_state_scope_overwrites_existing_key():
    store = MemoryStore(project="proj-c")

    store.write("state", "current_phase", "Phase 1")
    store.write("state", "current_phase", "Phase 2")

    assert store.read("state", "current_phase") == "Phase 2"


def test_decisions_scope_round_trip():
    store = MemoryStore(project="proj-d")

    store.write("decisions", "ADR-001 pick SQLite", "Decided SQLite over Postgres for engine memory.")
    store.write("decisions", "ADR-002 src layout", "Adopt src layout per noctusai_lib convention.")

    body = store.read("decisions", "")
    assert "ADR-001 pick SQLite" in body
    assert "Decided SQLite over Postgres" in body
    assert "ADR-002 src layout" in body


def test_changelog_scope_round_trip():
    store = MemoryStore(project="proj-e")

    store.write("changelog", "B0 audit ✅", "agno 2.6.4 confirmed; noctusai_lib mapped.")
    body = store.read("changelog", "")
    assert "B0 audit ✅" in body


def test_self_scope_round_trip():
    store = MemoryStore(project="proj-f")

    store.write("self", "leader", "Prefer 1-line summaries when delegating.")
    store.write("self", "leader", "Always echo the §11 row before closing.")

    body = store.read("self", "leader")
    assert "Prefer 1-line summaries" in body
    assert "Always echo the §11 row" in body


def test_self_scope_isolated_per_agent():
    store = MemoryStore(project="proj-g")

    store.write("self", "leader", "leader-only craft note")
    store.write("self", "architect", "architect-only craft note")

    assert "leader-only" in store.read("self", "leader")
    assert "leader-only" not in store.read("self", "architect")
    assert "architect-only" in store.read("self", "architect")


def test_invalid_scope_raises():
    store = MemoryStore(project="proj-h")

    with pytest.raises(ValueError, match="unknown scope"):
        store.write("garbage", "k", "v")
    with pytest.raises(ValueError, match="unknown scope"):
        store.read("garbage", "k")


def test_self_scope_requires_agent_name():
    store = MemoryStore(project="proj-i")

    with pytest.raises(ValueError, match="agent name is required"):
        store.write("self", "", "body")


def test_store_root_isolation(tmp_path):
    # Sanity check the fixture: store root is the tmp_path.
    assert get_store_root() == tmp_path


def test_project_isolation():
    a = MemoryStore(project="proj-a")
    b = MemoryStore(project="proj-b")

    a.write("state", "current_phase", "Phase 1")
    b.write("state", "current_phase", "Phase 9")

    assert a.read("state", "current_phase") == "Phase 1"
    assert b.read("state", "current_phase") == "Phase 9"


def test_default_project_when_none():
    """A store with project=None still functions (uses _default slug)."""
    store = MemoryStore(project=None)

    store.write("state", "k", "v")
    assert store.read("state", "k") == "v"
    snap = store.snapshot()
    assert snap["project"] is None
