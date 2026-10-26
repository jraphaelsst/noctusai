"""Typed failures of a call to the `agents` product -- the base taxonomy every consumer shares.

A consumer decides from the TYPE, never from a status code or a message. Product-specific
errors (social-wiring's channel/Julia ones) subclass `AgentsClientError`.
"""
from __future__ import annotations

from typing import Optional

from noctusai_lib.primitives.not_configured import IntegrationNotConfigured


class AgentsClientError(Exception):
    """Base of every failure of a call to agents. `code` is agents' own error code."""

    def __init__(self, message: str = "", *, code: Optional[str] = None):
        super().__init__(message or code or self.__class__.__name__)
        self.code = code


class AgentsNotConfigured(AgentsClientError, IntegrationNotConfigured):
    """No token / base URL for this caller (prod): the link is simply not set up."""


class AgentsTokenInvalid(AgentsClientError):
    """401, or 403 (token refused / caller is not an org admin)."""


class AgentNotFound(AgentsClientError):
    """404 agent_not_found."""


class AgentsBadRequest(AgentsClientError):
    """422 -- a request shape or value the server refused. `fields` carries the structured body (e.g. `conflitos`)."""

    def __init__(self, message: str = "", *, code: Optional[str] = None, fields: Optional[dict] = None):
        super().__init__(message, code=code)
        self.fields = fields or {}


class AgentsUpstreamError(AgentsClientError):
    """5xx or a malformed 2xx: no usable answer."""


class AgentsTimeout(AgentsClientError):
    """No answer in time, or the network is down."""
