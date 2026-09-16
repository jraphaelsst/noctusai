"""Typed error taxonomy for `image_edit` adapters.

Retryable vs fatal is the axis a job handler (the S8 photo-editing
engine, not yet built) branches on — the same concept
`noctusai_lib.integrations.outbound_webhook`'s `DeliveryAttempt.is_retryable`
carries, expressed here as an EXCEPTION hierarchy rather than a
result-with-flag: `OpenAIImageEditAdapter.edit` is a `Protocol` method
that returns a value object on success, so a provider failure has to
travel some other way — raising, and matching
`noctusai_lib.integrations.llm.exceptions`' shape (both are
provider-error translations at an IO boundary).

Classification (verified against the OpenAI Python SDK's exception
hierarchy — `openai.APIStatusError` subclasses carry `.status_code`; no
live account was available at S3b write time to re-verify against a real
response — see `openai_adapter.py`'s module docstring):

- retryable: 429 (`RateLimitError`), any 5xx (`InternalServerError`),
  `APITimeoutError`, `APIConnectionError`.
- fatal: content-policy rejection, invalid-size/shape rejection
  (`BadRequestError` that is not a transient capacity issue),
  authentication/configuration failure.
"""

from __future__ import annotations

from typing import Optional


class ImageEditError(Exception):
    """Base class for every `image_edit` adapter error.

    `retryable` is the classification axis a job handler branches on —
    set on the concrete subclass, never inferred at the call site.
    """

    retryable: bool = False

    def __init__(
        self, message: str, *, provider: str = "openai", details: Optional[dict] = None
    ) -> None:
        self.provider = provider
        self.details = details or {}
        super().__init__(message)


class ImageEditRetryableError(ImageEditError):
    """429 / 5xx / timeout / connection failure — safe to retry per
    `noctusai_lib.domain.jobs.retry_policy.RetryPolicy`."""

    retryable = True


class ImageEditFatalError(ImageEditError):
    """Content-policy rejection, invalid size/shape, or a configuration
    failure — retrying will not help; dead-letter immediately."""

    retryable = False


class ImageEditNotConfigured(ImageEditFatalError):
    """The resolved API key for the requested provider is empty/missing.

    Mirrors `noctusai_lib.integrations.llm.exceptions.LLMNotConfigured`.
    """

    def __init__(self, provider: str = "openai") -> None:
        super().__init__(
            f"{provider.capitalize()} API key not configured for image_edit",
            provider=provider,
        )


class ImageEditContentPolicyViolation(ImageEditFatalError):
    """OpenAI rejected the request or output on content-policy grounds."""


class ImageEditInvalidSize(ImageEditFatalError):
    """The requested/output size violates the provider's size contract.

    See `noctusai_lib.primitives.image_sizing.validate_size` — this
    module does not itself validate size before calling the provider; it
    surfaces the provider's own rejection under this type.
    """


class ImageEditRateLimited(ImageEditRetryableError):
    """429 — safe to retry with backoff."""


class ImageEditServerError(ImageEditRetryableError):
    """5xx from the provider — safe to retry with backoff."""


class ImageEditTimeout(ImageEditRetryableError):
    """Request timed out / connection failed before a response arrived —
    safe to retry with backoff."""
