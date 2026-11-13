"""Analyze an image against a text prompt via the active LLM provider.

Routes through ``noctusai_lib.integrations.llm.vision.analyze_image``.
Accepts either base64-encoded image bytes or a public URL the provider
can fetch directly.
"""

from __future__ import annotations

import base64

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, model_validator


class AnalyzeInput(BaseModel):
    prompt: str = Field(
        description=(
            "Text prompt describing what to extract / analyze from the image."
        )
    )
    image_base64: str | None = Field(
        default=None,
        description=(
            "Image bytes encoded as base64. Set this OR ``image_url``, not both."
        ),
    )
    image_url: str | None = Field(
        default=None,
        description=(
            "Public image URL the provider fetches directly. Set this OR "
            "``image_base64``, not both."
        ),
    )
    model: str | None = Field(
        default=None,
        description="Override the provider's default vision model for this call.",
    )
    provider: str | None = Field(
        default=None,
        description="Override the active LLM provider (default: configured provider).",
    )
    org_id: str | None = Field(
        default=None,
        description="Scope API-key resolution to a specific org.",
    )

    @model_validator(mode="after")
    def _check_one_image_source(self) -> "AnalyzeInput":
        if (self.image_base64 is None) == (self.image_url is None):
            raise ValueError(
                "Exactly one of image_base64 or image_url must be provided."
            )
        return self


class AnalyzeOutput(BaseModel):
    description: str


#: Vendors the toolkit's vision tool can route to (all three implement analyze_image).
VISION_PROVIDERS: tuple[str, ...] = ("anthropic", "openai", "gemini")
#: Owner decision 2026-11-13: the toolkit's vision runs on Anthropic unless the
#: `llm_vision_provider` switch (platform_settings → env) says otherwise.
DEFAULT_VISION_PROVIDER = "anthropic"


def resolve_vision_provider(explicit: str | None, org_id: str | None, resolver=None) -> str:
    """An explicit ``provider`` wins; otherwise the shared manual switch
    (`resolve_llm_provider("vision")`), defaulting to Anthropic.

    ``resolver`` is the DI seam `resolve_llm_provider` already exposes (tests pass
    a lambda instead of the org_settings → platform_settings → env chain)."""
    if explicit:
        return explicit
    from noctusai_lib.integrations.llm.provider_choice import resolve_llm_provider

    kwargs = {"resolver": resolver} if resolver is not None else {}
    return resolve_llm_provider(
        "vision", org_id, allowed=VISION_PROVIDERS, default=DEFAULT_VISION_PROVIDER, **kwargs
    )


async def analyze(payload: AnalyzeInput) -> AnalyzeOutput:
    """Analyze / describe an image via the LLM vision provider (Anthropic by default)."""
    from noctusai_lib.integrations.llm.vision import analyze_image
    from tools.noctus.dev._llm_bootstrap import ensure_llm_configured

    # The MCP server never calls configure_llm itself; the funnel satisfies its
    # own precondition (KB § PATTERNS/common/funnel-self-satisfies-preconditions.md).
    ensure_llm_configured()

    image: bytes | str
    if payload.image_base64 is not None:
        image = base64.b64decode(payload.image_base64)
    else:
        assert payload.image_url is not None
        image = payload.image_url

    description = await analyze_image(
        image,
        payload.prompt,
        model=payload.model,
        provider=resolve_vision_provider(payload.provider, payload.org_id),
        org_id=payload.org_id,
    )
    return AnalyzeOutput(description=description.strip())


def register(server: FastMCP) -> None:
    server.tool(
        name="llm.vision.analyze",
        description=analyze.__doc__,
    )(analyze)
