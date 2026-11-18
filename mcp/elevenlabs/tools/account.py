"""elevenlabs.user.usage + elevenlabs.model.list — account-level reads."""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api
from ..types import ModelListInput, ModelListOutput, UsageInput, UsageOutput
from ._common import ctx


async def user_usage(args: dict) -> dict:
    UsageInput(**args)
    try:
        d = api.request_json("GET", "/v1/user/subscription", **ctx())
    except api.ElevenLabsApiError as e:
        return UsageOutput(error=typed_error(e)).model_dump()
    d = d if isinstance(d, dict) else {}
    used, limit = d.get("character_count"), d.get("character_limit")
    return UsageOutput(
        tier=d.get("tier"), status=d.get("status"),
        character_count=used, character_limit=limit,
        remaining=(limit - used) if isinstance(used, int) and isinstance(limit, int) else None,
        next_reset_unix=d.get("next_character_count_reset_unix"),
        voice_slots_used=d.get("voice_slots_used"), voice_limit=d.get("voice_limit"),
        can_use_instant_voice_cloning=d.get("can_use_instant_voice_cloning"),
    ).model_dump()


def _slim_model(m: dict) -> dict:
    rates = m.get("model_rates") or {}
    return {
        "model_id": m.get("model_id"), "name": m.get("name"),
        "can_do_text_to_speech": m.get("can_do_text_to_speech"),
        "character_cost_multiplier": rates.get("character_cost_multiplier"),
        "cost_discount_multiplier": rates.get("cost_discount_multiplier", 1),
        "maximum_text_length_per_request": m.get("maximum_text_length_per_request"),
        "languages": [x.get("language_id") for x in (m.get("languages") or []) if isinstance(x, dict)],
    }


async def model_list(args: dict) -> dict:
    inp = ModelListInput(**args)
    try:
        d = api.request_json("GET", "/v1/models", **ctx())
    except api.ElevenLabsApiError as e:
        return ModelListOutput(error=typed_error(e)).model_dump()
    models = [_slim_model(m) for m in (d if isinstance(d, list) else []) if isinstance(m, dict)]
    if inp.tts_only:
        models = [m for m in models if m["can_do_text_to_speech"]]
    if inp.language:
        models = [m for m in models if inp.language in m["languages"]]
    return ModelListOutput(models=models).model_dump()


HANDLERS = {"elevenlabs.user.usage": user_usage, "elevenlabs.model.list": model_list}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(name="elevenlabs.user.usage",
             description="Subscription tier + character/credit balance and limits. READ-ONLY.",
             inputSchema=UsageInput.model_json_schema()),
        Tool(name="elevenlabs.model.list",
             description="Models with per-character cost multiplier, max text length and languages "
             "(filter language='pt' for pt-BR). READ-ONLY.",
             inputSchema=ModelListInput.model_json_schema()),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
