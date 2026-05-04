"""Shared project memory — the dev_team's MemoryStore facade.

Layout (per design-reference §5.1 + §5.2):

    dev_team/src/dev_team/memory/store/
    ├── project/<slug>/
    │   ├── state.sqlite       # current_phase, last_verification, arbitrary kv
    │   ├── decisions.md       # append-only ADR / PM / UX log
    │   └── change-log.md      # mirror of PROJECT.md §11 for cheap reads
    └── agents/<agent>/
        └── <agent>.md         # per-agent craft notes

The :class:`MemoryStore` exposes four scopes — `state`, `decisions`,
`changelog`, `self`. The first three target the project store; `self`
delegates to :mod:`dev_team.memory.craft` for per-agent craft files.

The store directory root can be overridden via :func:`set_store_root`;
tests use this with ``tmp_path`` so they never touch the real
``store/`` directory shipped at package root.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from noctusai_lib.primitives.timeutil import now_utc

# Import the sibling submodule directly (NOT via the package) to avoid
# the circular import shape where ``dev_team.memory.__init__`` tries
# to import :class:`MemoryStore` from this very module.
import dev_team.memory.craft as craft  # noqa: E402  (intentional sibling import)

# Module-level configurable root so tests can isolate via tmp_path
# without monkey-patching our own modules.
_DEFAULT_STORE_ROOT = Path(__file__).resolve().parent / "store"
_store_root: Path = _DEFAULT_STORE_ROOT


def set_store_root(path: Path | str) -> None:
    """Override the on-disk store root (for tests + advanced use).

    Tests pass a ``tmp_path`` so they get a clean store per test.
    Production code should NOT call this — the default
    ``dev_team/src/dev_team/memory/store/`` is the canonical location.
    """
    global _store_root
    _store_root = Path(path)
    # Keep craft module's root in sync — both halves of the memory live
    # under the same root.
    craft.set_store_root(_store_root)


def get_store_root() -> Path:
    return _store_root


_VALID_SCOPES = ("state", "decisions", "changelog", "self")


class MemoryStore:
    """Hybrid memory facade — shared project + per-agent craft.

    ``project`` is the project slug used to namespace the on-disk
    state.sqlite + decisions.md + change-log.md files. ``None`` is
    accepted (the store still works, but reads/writes against an
    explicit per-project namespace require a project name).
    """

    def __init__(self, project: str | None = None) -> None:
        self.project = project

    # -- snapshot ---------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return a small dict describing the current project state.

        Keys: ``project``, ``current_phase``, ``last_verification``.
        Reads from ``state.sqlite``'s kv table; missing values come
        back as ``None`` (not raised).
        """
        return {
            "project": self.project,
            "current_phase": self._read_state("current_phase"),
            "last_verification": self._read_state("last_verification"),
        }

    # -- public API -------------------------------------------------------

    def read(self, scope: str, key: str) -> Any:
        """Read a value from one of the four scopes.

        - ``state`` — kv read from project's ``state.sqlite``.
        - ``decisions`` — read full markdown body (``key`` ignored;
          pass ``""`` for clarity). Use grep on the return value for
          targeted lookups.
        - ``changelog`` — read full markdown body (``key`` ignored).
        - ``self`` — per-agent craft markdown read; ``key`` is the
          agent name.
        """
        self._validate_scope(scope)
        if scope == "state":
            return self._read_state(key)
        if scope == "decisions":
            return self._read_markdown("decisions.md")
        if scope == "changelog":
            return self._read_markdown("change-log.md")
        if scope == "self":
            return craft.read_craft(key)
        # Unreachable; guarded above.
        return None  # pragma: no cover

    def write(self, scope: str, key: str, value: Any) -> None:
        """Write a value into one of the four scopes.

        - ``state`` — kv write to ``state.sqlite``. JSON-serialized
          if not str/int/float/bool/None.
        - ``decisions`` — append a timestamped entry. ``key`` is the
          short title; ``value`` is the body (str).
        - ``changelog`` — append a timestamped entry. ``key`` is the
          short title; ``value`` is the body (str).
        - ``self`` — per-agent craft markdown append; ``key`` is the
          agent name; ``value`` is the body (str).
        """
        self._validate_scope(scope)
        if scope == "state":
            self._write_state(key, value)
            return
        if scope == "decisions":
            self._append_markdown("decisions.md", title=key, body=str(value))
            return
        if scope == "changelog":
            self._append_markdown("change-log.md", title=key, body=str(value))
            return
        if scope == "self":
            craft.append_craft(agent=key, body=str(value))
            return

    # -- internals --------------------------------------------------------

    def _validate_scope(self, scope: str) -> None:
        if scope not in _VALID_SCOPES:
            raise ValueError(
                f"unknown scope {scope!r}; valid scopes: {_VALID_SCOPES}"
            )

    def _project_dir(self) -> Path:
        slug = self.project or "_default"
        path = _store_root / "project" / slug
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _state_db_path(self) -> Path:
        return self._project_dir() / "state.sqlite"

    def _connect_state(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._state_db_path())
        conn.execute(
            "CREATE TABLE IF NOT EXISTS kv ("
            "  key TEXT PRIMARY KEY,"
            "  value TEXT,"
            "  updated_at TEXT NOT NULL"
            ")"
        )
        return conn

    def _read_state(self, key: str) -> Any:
        with self._connect_state() as conn:
            row = conn.execute(
                "SELECT value FROM kv WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        raw = row[0]
        if raw is None:
            return None
        # Try JSON-decode (we always JSON-encode on write); fall back
        # to the raw string if it isn't JSON (e.g. a manually-edited
        # value).
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return raw

    def _write_state(self, key: str, value: Any) -> None:
        encoded = json.dumps(value, default=str)
        ts = now_utc().isoformat()
        with self._connect_state() as conn:
            conn.execute(
                "INSERT INTO kv (key, value, updated_at) VALUES (?, ?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value,"
                " updated_at = excluded.updated_at",
                (key, encoded, ts),
            )
            conn.commit()

    def _markdown_path(self, name: str) -> Path:
        return self._project_dir() / name

    def _read_markdown(self, name: str) -> str:
        path = self._markdown_path(name)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _append_markdown(self, name: str, *, title: str, body: str) -> None:
        path = self._markdown_path(name)
        ts = now_utc().isoformat()
        header = f"\n## {ts} — {title}\n\n" if title else f"\n## {ts}\n\n"
        with path.open("a", encoding="utf-8") as fh:
            if path.stat().st_size == 0:
                # First write — no leading blank line needed.
                fh.write(f"# {name.replace('.md', '').replace('-', ' ').title()}\n")
            fh.write(header)
            fh.write(body)
            if not body.endswith("\n"):
                fh.write("\n")


__all__ = ["MemoryStore", "set_store_root", "get_store_root"]
