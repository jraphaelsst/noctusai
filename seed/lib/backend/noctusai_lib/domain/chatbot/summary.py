"""Optional conversation summarizer — calls OpenAI's structured-output
API to produce a Pydantic-typed summary of the conversation memory.

Ported from
`whatsapp-google-scheduling/app/services/openai/summary.py:ConversationSummaryService`
2026-05-03 via `projects/whatsapp-seed-absorption/` Phase 6.

The seed lifts ONLY the runner shape — the system prompt + the
`output_schema` Pydantic class are 100% product-specific (sibling's
schema had real-estate fields like `properties_requested`,
`requested_services`; therapy would use entirely different labels).
Per project §7 Q4, idle-summary is OPT-IN at the consumer (default
off), so this module is dormant until a consumer wires it.

Typical wiring (consumer side):

    from pydantic import BaseModel
    from noctusai_lib.domain.chatbot.summary import summarize_conversation


    class TherapySessionSummary(BaseModel):
        topics: list[str]
        risk_flags: list[str]
        next_step_suggested: str | None


    summary = summarize_conversation(
        client=openai_client,
        model="gpt-4o-mini",
        memory=memory,
        output_schema=TherapySessionSummary,
        system_prompt=THERAPY_SUMMARY_SYSTEM_PROMPT,
        user_system_block=therapy_user_context_block(user),
    )
"""

from __future__ import annotations

from typing import Any, TypeVar

from noctusai_lib.domain.chatbot.mappers import format_conversation_for_transcript

T = TypeVar("T")


def summarize_conversation(
    client: Any,
    model: str,
    memory: list[dict[str, Any]],
    output_schema: type[T],
    system_prompt: str,
    user_system_block: str | None = None,
    *,
    assistant_label: str = "ASSISTANT",
    user_label: str = "USER",
) -> T:
    """Run OpenAI structured-output (`client.responses.parse`) over the
    conversation transcript and return a parsed instance of
    `output_schema`.

    `system_prompt` is the analyzer-task prompt. `user_system_block` is
    an optional second system message for per-user context (e.g.,
    authorization status). The transcript is rendered via
    `format_conversation_for_transcript` with the supplied labels.
    """
    transcript = format_conversation_for_transcript(
        memory, assistant_label=assistant_label, user_label=user_label
    )

    input_blocks: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt}
    ]
    if user_system_block is not None:
        input_blocks.append({"role": "system", "content": user_system_block})
    input_blocks.append({"role": "user", "content": transcript})

    response = client.responses.parse(
        model=model,
        input=input_blocks,
        text_format=output_schema,
    )
    return response.output_parsed
