"""Shared base for automation failures whose message is safe to show the user."""
from __future__ import annotations


class AutomationUserError(RuntimeError):
    """A failure whose message is pt-BR, secret-free and stored on the failed
    action / execution (`error_detail`). Anything NOT deriving from this gets a
    generic message — the traceback goes to the log, never to the user."""
