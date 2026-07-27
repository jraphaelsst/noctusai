"""System prompts for the LLM-driven generation stages.

Each constant is the system message of one generation stage:

- ``STORYBOARD_SYSTEM_PROMPT``  — idea + kit → Método Audience storyboard.
- ``IMAGE_PROMPTS_SYSTEM_PROMPT`` — storyboard → per-renderer image prompts.
- ``COPY_SYSTEM_PROMPT``         — storyboard → caption / hashtags / alt / comment.

All three build on the in-home :data:`METODO_AUDIENCE` methodology (self-contained,
no external references). The persona + design system + references + brand name
arrive as **user-role context** at call time (per-org tenant data), not baked
into the system prompt — so one deployment can serve many brands.
"""
from app.modules.media_creation.prompts.storyboard import STORYBOARD_SYSTEM_PROMPT
from app.modules.media_creation.prompts.image_prompts import IMAGE_PROMPTS_SYSTEM_PROMPT
from app.modules.media_creation.prompts.copy import COPY_SYSTEM_PROMPT
from app.modules.media_creation.prompts.methodology import (
    METODO_AUDIENCE,
    METODO_QUALITY,
    METODO_STRUCTURE,
    METODO_TEMPLATES,
    METODO_TRIGGERS,
)

__all__ = [
    "STORYBOARD_SYSTEM_PROMPT",
    "IMAGE_PROMPTS_SYSTEM_PROMPT",
    "COPY_SYSTEM_PROMPT",
    "METODO_AUDIENCE",
    "METODO_QUALITY",
    "METODO_STRUCTURE",
    "METODO_TEMPLATES",
    "METODO_TRIGGERS",
]
