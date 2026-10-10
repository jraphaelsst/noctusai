"""PostgREST / Postgres error classification — single source of truth.

`is_unique_violation(exc)`: did this write fail because it LOST a UNIQUE / PK
race (SQLSTATE 23505)? Replaces ~10 private `_is_unique_violation` copies that
had drifted into three different predicates (code-only, message-only, and a
bare `"unique" in msg` that also matched unrelated text).

Semantics (the safe union of the old copies, deliberately NOT broader):
  * `exc.code == "23505"`            — supabase-py / postgrest `APIError` and
                                       test doubles that duck-type `.code`;
  * `"23505"` in `str(exc)`          — the generic `APIError` renders its dict;
  * `"duplicate key"` in `str(exc)`  — Postgres' own message text.
A bare `"unique"` is NOT matched (it matches e.g. "non-unique", column names).

Call sites that need a SPECIFIC constraint must narrow explicitly on top of
this (e.g. `is_unique_violation(exc) and "my_idx" in str(exc)`) — never by
re-implementing the predicate. Pure: no HTTP, no imports from FastAPI, so it
is safe inside webhook / job-worker paths (unlike
`primitives.exceptions.postgrest_exception_handler`, which raises HTTP).
"""
from __future__ import annotations

UNIQUE_VIOLATION_SQLSTATE = "23505"


def is_unique_violation(exc: BaseException) -> bool:
    """True iff `exc` is a Postgres unique_violation (23505) from PostgREST."""
    if getattr(exc, "code", None) == UNIQUE_VIOLATION_SQLSTATE:
        return True
    text = str(exc)
    return UNIQUE_VIOLATION_SQLSTATE in text or "duplicate key" in text.lower()


__all__ = ["UNIQUE_VIOLATION_SQLSTATE", "is_unique_violation"]
