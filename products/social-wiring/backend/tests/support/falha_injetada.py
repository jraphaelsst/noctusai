"""A client test double that FAILS on demand (julia-v2 G4 tests): wraps a real (mock-DB) schema-scoped client and raises
on `table(name)` for the named tables, delegating everything else -- so the supervision alert (a write to
`julia_eventos`) lands in the same DB the assertions read. A double for the DB, never a patch of our code."""
from __future__ import annotations

from typing import Any, Iterable


class ClienteQueFalha:
    def __init__(self, real: Any, quebradas: Iterable[str]) -> None:
        self._real = real
        self._quebradas = frozenset(quebradas)

    def table(self, name: str) -> Any:
        if name in self._quebradas:
            raise RuntimeError(f"injected failure: table {name!r} is down")
        return self._real.table(name)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._real, item)
