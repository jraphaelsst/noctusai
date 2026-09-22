"""Shared PostgREST-error → typed-store-error mapping for the Agent Studio
stores (``studio_definitions`` / ``studio_knowledge`` / ``studio_evals``).

Why one module: supabase-py RAISES ``postgrest.exceptions.APIError`` on a
constraint violation (``code`` = the SQLSTATE, ``message`` = the server
text) — it never returns empty ``data``. A Real store that tests
``if not resp.data`` after a duplicate insert therefore 500s in prod while
its Fake (which raises a typed error) keeps the router tests green. Every
studio write goes through :func:`exec_query` / :func:`exec_rpc` so the SAME
translation applies everywhere, and the routes map the typed errors, never a
driver exception.

Translation (first match wins):

* The 012/013 functions and triggers ``RAISE EXCEPTION '<code>'`` with the
  machine code AS the message — mapped by :data:`_P0001_CODES`.
* ``23505`` unique violation → :class:`StudioConflict` ``unique_code``.
* ``23503`` FK violation → :class:`StudioConflict` ``fk_code``.
* ``23514`` CHECK violation → :class:`ValueError` (the size caps / allowlists
  — a 422 at the router, never a 500).
* Anything else propagates unchanged (a real failure is never masked).
"""
from __future__ import annotations

from typing import Any, Callable

from app.stores.errors import Conflict, NotFound

__all__ = [
    "StudioConflict",
    "VersionImmutable",
    "map_db_error",
    "exec_query",
    "exec_rpc",
]


class StudioConflict(Conflict):
    """A write refused for a machine-readable reason — ``code`` is the §D
    409 code the router returns verbatim (``key_taken`` / ``draft_exists`` /
    ``skill_exists`` / ``client_exists`` / ``chave_conflict`` /
    ``caminho_conflict`` / ``draft_referenced`` / ``draft_changed`` /
    ``eval_required`` / ``client_entries_cap`` / ``slug_taken`` /
    ``slug_in_other_collection`` / ``run_in_progress`` / ``case_in_use`` /
    ``run_not_cancellable``)."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class VersionImmutable(StudioConflict):
    """The target version (or a child of it) is not a ``rascunho``."""

    def __init__(self, message: str = "") -> None:
        super().__init__("version_immutable", message or "version_immutable")


def _conflict(code: str) -> Callable[[str], Exception]:
    return lambda msg: StudioConflict(code, msg)


#: Machine codes raised by the 012/013 functions/triggers.
_P0001_CODES: dict[str, Callable[[str], Exception]] = {
    "version_immutable": VersionImmutable,
    "compiled_prompt_immutable": _conflict("compiled_prompt_immutable"),
    "audit_log_append_only": _conflict("audit_log_append_only"),
    "draft_exists": _conflict("draft_exists"),
    "draft_changed": _conflict("draft_changed"),
    "eval_required": _conflict("eval_required"),
    "chave_conflict": _conflict("chave_conflict"),
    "skill_exists": _conflict("skill_exists"),
    "client_entries_cap": _conflict("client_entries_cap"),
    "version_not_found": NotFound,
    "agent_not_found": NotFound,
    "eval_case_not_found": NotFound,
    "no_eval_cases": ValueError,
    "too_many_cases": ValueError,
    "query_too_long": ValueError,
    "invalid_payload": ValueError,
    "client_required": ValueError,
}


def _error_text(exc: Exception) -> tuple[str | None, str]:
    code = getattr(exc, "code", None)
    msg = getattr(exc, "message", None) or str(exc)
    return code, msg


def map_db_error(
    exc: Exception, *, unique_code: str | None = None, fk_code: str | None = None,
) -> Exception:
    """The typed error for ``exc`` — or ``exc`` itself when it is not one
    of the recognised shapes (the caller re-raises it unchanged)."""
    code, msg = _error_text(exc)
    text = msg.strip()
    factory = _P0001_CODES.get(text)
    if factory is None:
        for machine_code, candidate in _P0001_CODES.items():
            if machine_code in text:
                factory = candidate
                break
    if factory is not None:
        return factory(text)
    if code == "23505" and unique_code is not None:
        return StudioConflict(unique_code, msg)
    if code == "23503" and fk_code is not None:
        return StudioConflict(fk_code, msg)
    if code == "23514":
        return ValueError(msg)
    return exc


def exec_query(query: Any, *, unique_code: str | None = None, fk_code: str | None = None):
    """``query.execute()`` with :func:`map_db_error` applied."""
    try:
        return query.execute()
    except Exception as exc:
        mapped = map_db_error(exc, unique_code=unique_code, fk_code=fk_code)
        if mapped is exc:
            raise
        raise mapped from exc


def exec_rpc(
    client: Any, schema: str, fn: str, params: dict[str, Any], *,
    unique_code: str | None = None, fk_code: str | None = None,
):
    """``client.schema(schema).rpc(fn, params).execute()`` with
    :func:`map_db_error` applied (one RPC = one Postgres transaction)."""
    return exec_query(client.schema(schema).rpc(fn, params), unique_code=unique_code, fk_code=fk_code)
