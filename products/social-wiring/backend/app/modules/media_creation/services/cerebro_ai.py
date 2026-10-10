"""Segundo Cérebro — the LLM seam and the two AI operations (review, synthesis).

``get_cerebro_llm`` is the FastAPI dependency the router resolves (tests
override it with a fake callable — same shape as ``get_pesquisa_llm``); the
resolved callable is handed to the background tasks, which never resolve
dependencies themselves.

The operations here are pure given the callable: they build the prompt, call,
parse. DB reads/writes and status transitions stay in ``cerebro_service``.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional

from noctusai_lib.integrations.llm import chat_completion

from app.modules.media_creation.prompts.cerebro_review import (
    CEREBRO_REVIEW_SYSTEM_PROMPT,
    ParsedReview,
    ReviewItem,
    build_review_user_message,
    parse_review_output,
)
from app.modules.media_creation.prompts.cerebro_synthesis import (
    build_synthesis_system_prompt,
    build_synthesis_user_message,
)

logger = logging.getLogger(__name__)

#: ``(system_prompt, user_message, org_id) -> raw model reply``.
CerebroLlm = Callable[[str, str, Optional[str]], Awaitable[str]]


async def chat_cerebro_llm(system_prompt: str, user_message: str, org_id: Optional[str]) -> str:
    return await chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        org_id=org_id,
        temperature=0.2,
    )


def get_cerebro_llm() -> CerebroLlm:
    """DI seam for the review/synthesis LLM. Tests override with a fake callable."""
    return chat_cerebro_llm


async def review_answers(
    llm: CerebroLlm, org_id: Optional[str], template_name: str, items: list[ReviewItem]
) -> ParsedReview:
    """One LLM call for the whole request. Raises on LLM failure or a reply that
    is not a JSON array (``ReviewParseError``); the caller marks every pending
    answer of the request ``error``."""
    reply = await llm(
        CEREBRO_REVIEW_SYSTEM_PROMPT,
        build_review_user_message(template_name, items),
        org_id,
    )
    return parse_review_output(reply, [it.question_id for it in items])


async def synthesize_brain(
    llm: CerebroLlm,
    org_id: Optional[str],
    template_slug: str,
    template_name: str,
    qa_pairs: list[tuple[str, Optional[str], str]],
) -> str:
    """One LLM call; returns the markdown document (stripped). An empty reply is
    a failure — never blank a brain with it."""
    reply = await llm(
        build_synthesis_system_prompt(template_slug),
        build_synthesis_user_message(template_name, qa_pairs),
        org_id,
    )
    document = (reply or "").strip()
    if not document:
        raise ValueError("a IA devolveu um cérebro vazio")
    return document
