"""The error base every organ's `<Organ>Error` extends -- renders `{"error": {"code", "message", "details"}}`."""
from __future__ import annotations

from typing import Callable, Optional

from noctusai_lib.primitives.exceptions import AppException, NotFoundError


class OrganError(AppException):
    """A refusal carrying its stable machine `code` (+ optional offending `field`)."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 422,
        *,
        field: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        merged = dict(details or {})
        if field:
            merged["field"] = field
        super().__init__(code=code, message=message, status_code=status_code, details=merged)


def not_found(what: str) -> NotFoundError:
    """The platform's 404 -- a foreign-org id is indistinguishable from a missing one."""
    return NotFoundError(what)


def error_factories(cls: type[OrganError]) -> tuple[Callable[..., OrganError], Callable[..., OrganError]]:
    """`(invalid, conflict)` constructors bound to an organ's own error class (so `isinstance` holds)."""

    def invalid(field: str, message: str, code: str = "invalid") -> OrganError:
        return cls(code, message, 422, field=field)

    def conflict(code: str, message: str, **details) -> OrganError:
        return cls(code, message, 409, details=details)

    return invalid, conflict


__all__ = ["OrganError", "error_factories", "not_found"]
