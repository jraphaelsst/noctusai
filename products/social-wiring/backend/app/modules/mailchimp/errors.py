"""Mailchimp error taxonomy — single context manager implementing §1.

Every router wraps its adapter calls in ``translate_mailchimp_errors()`` so
the error taxonomy lives in exactly one place. The error codes are the
normative §1 codes from the plan contract.

Local error class names mirror the §2 Protocol error hierarchy; these are
the exact classes the conftest ``ContractFakeMailchimpClient`` raises.

NOTE: Raises AppException (not HTTPException) so the seed's
``app_exception_handler`` preserves the per-error ``code`` field in the
response body as ``{"error": {"code": ..., "message": ...}}``.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from noctusai_lib.primitives.exceptions import AppException


# ── Local error classes (normative Protocol §2 hierarchy) ────────────────────
# These mirror the noctusai_lib.integrations.mailchimp error hierarchy.
# Once slice A lands, the product can import those directly; until then
# these local definitions keep the router layer working.

class MailchimpError(Exception):
    """Base for all Mailchimp adapter errors."""


class MailchimpAuthError(MailchimpError):
    """Mailchimp returned 401 or 403."""


class MailchimpNotFoundError(MailchimpError):
    """Mailchimp returned 404."""


class MailchimpRateLimitedError(MailchimpError):
    """Mailchimp returned 429."""


class MailchimpRejectedError(MailchimpError):
    """Mailchimp returned 400/422 — ``args[0]`` carries the MC detail message."""


class MailchimpUnreachableError(MailchimpError):
    """Network / timeout / 5xx from Mailchimp."""


# ── Translation context manager ──────────────────────────────────────────────

@asynccontextmanager
async def translate_mailchimp_errors():
    """Async context manager that maps Mailchimp adapter errors → §1 taxonomy.

    Raises AppException (not HTTPException) so the seed's exception handler
    preserves the per-error ``code`` field in the response body.

    Usage::

        async with translate_mailchimp_errors():
            result = await client.list_audiences()

    Error mapping (§1 contract):

    | Exception                   | HTTP | code                      |
    |-----------------------------|------|---------------------------|
    | MailchimpAuthError          | 502  | mailchimp_auth_failed     |
    | MailchimpNotFoundError      | 404  | not_found                 |
    | MailchimpRateLimitedError   | 503  | mailchimp_rate_limited    |
    | MailchimpRejectedError      | 400  | mailchimp_rejected        |
    | MailchimpUnreachableError   | 502  | mailchimp_unreachable     |
    """
    try:
        yield
    except MailchimpAuthError as exc:
        raise AppException(
            code="mailchimp_auth_failed",
            message=str(exc),
            status_code=502,
        ) from exc
    except MailchimpNotFoundError as exc:
        raise AppException(
            code="not_found",
            message=str(exc),
            status_code=404,
        ) from exc
    except MailchimpRateLimitedError as exc:
        raise AppException(
            code="mailchimp_rate_limited",
            message=str(exc),
            status_code=503,
        ) from exc
    except MailchimpRejectedError as exc:
        raise AppException(
            code="mailchimp_rejected",
            message=str(exc),
            status_code=400,
        ) from exc
    except MailchimpUnreachableError as exc:
        raise AppException(
            code="mailchimp_unreachable",
            message=str(exc),
            status_code=502,
        ) from exc
