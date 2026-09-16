"""Versioned prompts for the photo-editing engine.

Five prompts, one module each: edit, evaluator, style guide, rule
proposer, model-note writer. User-facing text is pt-BR. Every prompt is a
``PromptTemplate`` with a ``(prompt_id, version)`` identity; ``ALL_PROMPTS``
is the registry the version-pin test walks.
"""

from noctusai_lib.domain.photo_editing.prompts._base import PromptTemplate, RenderedPrompt
from noctusai_lib.domain.photo_editing.prompts.edit import (
    EDIT_INSTRUCTIONS,
    EDIT_PROMPT,
    render_edit_prompt,
)
from noctusai_lib.domain.photo_editing.prompts.evaluator import (
    EVALUATOR_PROMPT,
    EVALUATOR_SCHEMA,
    render_evaluator_prompt,
)
from noctusai_lib.domain.photo_editing.prompts.note_writer import (
    NOTE_WRITER_PROMPT,
    NOTE_WRITER_SCHEMA,
    ModelMetrics,
    render_note_writer_prompt,
)
from noctusai_lib.domain.photo_editing.prompts.rule_proposer import (
    RULE_PROPOSER_PROMPT,
    RULE_PROPOSER_SCHEMA,
    render_rule_proposer_prompt,
)
from noctusai_lib.domain.photo_editing.prompts.style_guide import (
    STYLE_GUIDE_PROMPT,
    STYLE_GUIDE_SCHEMA,
    render_style_guide_prompt,
)

ALL_PROMPTS: tuple[PromptTemplate, ...] = (
    EDIT_PROMPT,
    EVALUATOR_PROMPT,
    STYLE_GUIDE_PROMPT,
    RULE_PROPOSER_PROMPT,
    NOTE_WRITER_PROMPT,
)

__all__ = [
    "ALL_PROMPTS",
    "EDIT_INSTRUCTIONS",
    "EDIT_PROMPT",
    "EVALUATOR_PROMPT",
    "EVALUATOR_SCHEMA",
    "ModelMetrics",
    "NOTE_WRITER_PROMPT",
    "NOTE_WRITER_SCHEMA",
    "PromptTemplate",
    "RULE_PROPOSER_PROMPT",
    "RULE_PROPOSER_SCHEMA",
    "RenderedPrompt",
    "STYLE_GUIDE_PROMPT",
    "STYLE_GUIDE_SCHEMA",
    "render_edit_prompt",
    "render_evaluator_prompt",
    "render_note_writer_prompt",
    "render_rule_proposer_prompt",
    "render_style_guide_prompt",
]
