"""Derive the per-migration status in ``migrations/APPLIED.md`` from ``migrations-applied.json``.

Two hand-kept records of one fact (a migration is applied in prod) drifted: the recorder
(``noctus.dev.record_applied_migrations``) writes the ledger and never touched APPLIED.md, so a
heading kept saying ``NOT APPLIED`` until someone edited it by hand (SW 367, 2026-11-19; 31 more
found when this was first run). The LEDGER is the source of truth; this module is the one place
that reads APPLIED.md's headings (``## NNN — title — STATUS``, line-structured, fenced code
skipped, the prose body never touched):

* :func:`sync_applied_md` -- rewrites ``NOT APPLIED`` -> ``APPLIED`` for every heading whose
  migration number is in the ledger (called by the recorder in the same commit as the ledger).
* :func:`parity_findings` -- the keeper's predicate: a ``NOT APPLIED`` heading whose number is in
  the ledger, or an ``APPLIED`` heading inside the ledger's covered range that the ledger lacks.

Numbers below the ledger's lowest entry predate the ledger and are never judged.

KB § PATTERNS/backend/migrate-product-mcp-tool.md
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

APPLIED_MD = "APPLIED.md"
LEDGER = "migrations-applied.json"
_HEADING = re.compile(r"^## (\d+) — (.*)$")
_NOT = " — NOT APPLIED"
_APP = " — APPLIED"
RECORDED = "APPLIED (recorded in migrations-applied.json)"


def ledger_numbers(applied: Iterable[str]) -> set[int]:
    out: set[int] = set()
    for name in applied:
        head = name.split("_", 1)[0]
        if head.isdigit():
            out.add(int(head))
    return out


def _headings(text: str):
    """Yield ``(line_index, number, rest)`` for real headings (outside fenced blocks)."""
    fenced = False
    for i, line in enumerate(text.split("\n")):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        m = _HEADING.match(line)
        if m:
            yield i, int(m.group(1)), m.group(2)


def _status(rest: str) -> str | None:
    """'not' | 'applied' | None -- the LAST status segment of the heading."""
    n, a = rest.rfind(_NOT), rest.rfind(_APP)
    if n < 0 and a < 0:
        return None
    return "not" if n > a else "applied"


def sync_applied_md(text: str, applied: Iterable[str]) -> tuple[str, list[int]]:
    """Return ``(new_text, changed_numbers)``; only ``NOT APPLIED`` headings in the ledger move."""
    nums = ledger_numbers(applied)
    lines = text.split("\n")
    changed: list[int] = []
    for i, n, rest in _headings(text):
        if n not in nums or _status(rest) != "not":
            continue
        at = rest.rfind(_NOT)
        tail = rest[at + len(_NOT):]
        new_tail = f" — {RECORDED}" if not tail.strip() else f" — APPLIED{tail}"
        lines[i] = lines[i][: lines[i].rfind(_NOT)] + new_tail
        changed.append(n)
    return "\n".join(lines), changed


def parity_findings(text: str, applied: Iterable[str]) -> list[tuple[int, str]]:
    """``[(number, message)]`` for every heading that disagrees with the ledger."""
    applied = list(applied)
    nums = ledger_numbers(applied)
    if not nums:
        return []
    floor = min(nums)
    out: list[tuple[int, str]] = []
    for _i, n, rest in _headings(text):
        st = _status(rest)
        if st == "not" and n in nums:
            out.append((n, f"heading {n} says NOT APPLIED but the ledger has it"))
        elif st == "applied" and n >= floor and n not in nums:
            out.append((n, f"heading {n} says APPLIED but the ledger (covering {floor}+) lacks it"))
    return out


def read_ledger_names(backend: Path) -> list[str] | None:
    import json

    p = backend / LEDGER
    if not p.is_file():
        return None
    applied = json.loads(p.read_text(encoding="utf-8")).get("applied")
    return sorted(applied) if isinstance(applied, dict) else None


def sync_backend(backend: Path) -> list[int]:
    """Rewrite ``backend/migrations/APPLIED.md`` from the ledger in place; returns changed numbers."""
    md = backend / "migrations" / APPLIED_MD
    names = read_ledger_names(backend)
    if names is None or not md.is_file():
        return []
    new, changed = sync_applied_md(md.read_text(encoding="utf-8"), names)
    if changed:
        md.write_text(new, encoding="utf-8")
    return changed
