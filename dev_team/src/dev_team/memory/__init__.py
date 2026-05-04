"""dev_team memory layer — hybrid (shared project + per-agent craft).

Public surface:
    MemoryStore — facade over the SQLite + markdown stores.

The actual implementation modules (``shared.py``, ``craft.py``) are
shipped by the memory engineer; this __init__ exposes the contract so
other modules can import :class:`MemoryStore` without depending on the
implementation being wired yet.

Stub behavior (until engineer ships): :class:`MemoryStore` returns
empty snapshots and accepts writes silently. Tests for the memory
engineer assert real persistence; the smoke test (`tests/test_smoke.py`)
only asserts the contract type exists and is callable.
"""

from __future__ import annotations

from typing import Any

# Re-export the real MemoryStore once shared.py ships its class. Until
# then, the stub below is exposed.
try:  # pragma: no cover — flips to real impl when engineer ships shared.py
    from dev_team.memory.shared import MemoryStore as _RealMemoryStore  # type: ignore
    MemoryStore = _RealMemoryStore  # type: ignore[assignment,misc]
except ImportError:

    class MemoryStore:  # type: ignore[no-redef]
        """Stub MemoryStore — replaced by :class:`dev_team.memory.shared.MemoryStore`.

        Returns empty snapshots; accepts writes silently. Sufficient for
        import + cli smoke; insufficient for production use.
        """

        def __init__(self, project: str | None = None) -> None:
            self.project = project

        def snapshot(self) -> dict[str, Any]:
            return {"project": self.project, "current_phase": None, "last_verification": None}

        def read(self, scope: str, key: str) -> Any:
            return None

        def write(self, scope: str, key: str, value: Any) -> None:
            return None


__all__ = ["MemoryStore"]
