"""openai.vision — image + question → text via gpt-4o vision."""
from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path
from typing import Any

from mcp.types import Tool

from _kit.errors import typed_error

from .. import openai_client
from ..settings import get_settings
from ..types import VisionInput, VisionOutput

logger = logging.getLogger(__name__)


def _image_url_from_path(path_str: str) -> str:
    """Read a local image and return a `data:` URI for the OpenAI API."""
    p = Path(path_str).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"image_path not found: {path_str}")
    mime, _ = mimetypes.guess_type(str(p))
    mime = mime or "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


async def handle_vision(args: dict) -> dict:
    try:
        inp = VisionInput(**args)
    except Exception as exc:
        return {"error": typed_error(exc, status=422)}
    if not inp.image_url and not inp.image_path:
        return {"error": typed_error(
            ValueError("either image_url or image_path is required"),
            status=422,
        )}
    if inp.image_url and inp.image_path:
        return {"error": typed_error(
            ValueError("provide image_url OR image_path, not both"),
            status=422,
        )}
    try:
        img_url = inp.image_url or _image_url_from_path(inp.image_path or "")
    except Exception as exc:
        return {"error": typed_error(exc, status=404)}
    try:
        client = openai_client.get_client()
    except Exception as exc:
        return {"error": typed_error(exc, status=503)}
    model = inp.model or get_settings().default_vision_model
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": inp.question},
                {"type": "image_url", "image_url": {"url": img_url}},
            ],
        }],
    }
    if inp.max_tokens is not None:
        kwargs["max_tokens"] = inp.max_tokens
    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception as exc:
        return {"error": typed_error(exc, status=502)}
    usage = getattr(resp, "usage", None)
    return VisionOutput(
        ok=True,
        model=model,
        content=resp.choices[0].message.content or "",
        usage=usage.model_dump() if usage and hasattr(usage, "model_dump") else None,
    ).model_dump()


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="openai.vision",
            description=(
                "Analyze an image with a natural-language question via gpt-4o "
                "vision. Accepts either `image_url` (http/https or data: URI) "
                "OR `image_path` (local file — auto-base64-encoded). Returns "
                "the assistant's text answer + usage. Use for OCR, diagram "
                "explanation, screenshot triage, chart reading, etc."
            ),
            inputSchema=VisionInput.model_json_schema(),
        ),
    ]


HANDLERS: dict[str, Any] = {"openai.vision": handle_vision}


def register(server) -> None:
    pass
