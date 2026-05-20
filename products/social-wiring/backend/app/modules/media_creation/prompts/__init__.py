"""System prompts for the LLM-driven generation stages.

Each constant is the system message of one stage of the 5-skill pipeline
ported from the sibling ``media-creator/`` repo. The skill→prompt mapping:

- ``STORYBOARD_SYSTEM_PROMPT``  ← ``media-creator/skills/carousel-storyboard/``
- ``IMAGE_PROMPTS_SYSTEM_PROMPT`` ← ``media-creator/skills/image-prompt-generator/``
- ``COPY_SYSTEM_PROMPT``         ← ``media-creator/skills/instagram-copywriting/``

The persona + design system + references arrive as **user-role context** at
call time (per-org tenant data), not baked into the system prompt — so one
deployment can serve many brands.
"""
from app.modules.media_creation.prompts.storyboard import STORYBOARD_SYSTEM_PROMPT
from app.modules.media_creation.prompts.image_prompts import IMAGE_PROMPTS_SYSTEM_PROMPT
from app.modules.media_creation.prompts.copy import COPY_SYSTEM_PROMPT

__all__ = [
    "STORYBOARD_SYSTEM_PROMPT",
    "IMAGE_PROMPTS_SYSTEM_PROMPT",
    "COPY_SYSTEM_PROMPT",
]
