"""summarize_conversation tests — mocks the OpenAI structured-output API."""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from noctusai_lib.domain.conversation.summary import summarize_conversation


class _Sample(BaseModel):
    topic: str
    items: list[str]


@dataclass
class _FakeResponse:
    output_parsed: Any


class _FakeResponses:
    def __init__(self, scripted: Any):
        self._scripted = scripted
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs) -> _FakeResponse:
        self.calls.append(kwargs)
        return _FakeResponse(output_parsed=self._scripted)


class _FakeClient:
    def __init__(self, scripted: Any):
        self.responses = _FakeResponses(scripted)


def test_summarize_returns_parsed_output() -> None:
    expected = _Sample(topic="appointments", items=["a", "b"])
    client = _FakeClient(expected)

    result = summarize_conversation(
        client=client,
        model="gpt-test",
        memory=[
            {"direction": "inbound", "text": "hi"},
            {"direction": "outbound", "text": "hello"},
        ],
        output_schema=_Sample,
        system_prompt="ANALYZE",
    )

    assert result == expected
    call = client.responses.calls[0]
    assert call["model"] == "gpt-test"
    assert call["text_format"] is _Sample
    # The transcript was rendered + sent as user message.
    assert call["input"][-1]["role"] == "user"
    assert "USER: hi" in call["input"][-1]["content"]
    assert "ASSISTANT: hello" in call["input"][-1]["content"]


def test_summarize_includes_user_system_block_when_provided() -> None:
    client = _FakeClient(_Sample(topic="t", items=[]))

    summarize_conversation(
        client=client,
        model="gpt-test",
        memory=[{"direction": "inbound", "text": "hi"}],
        output_schema=_Sample,
        system_prompt="ANALYZE",
        user_system_block="USER CONTEXT",
    )

    input_blocks = client.responses.calls[0]["input"]
    assert len(input_blocks) == 3
    assert input_blocks[0] == {"role": "system", "content": "ANALYZE"}
    assert input_blocks[1] == {"role": "system", "content": "USER CONTEXT"}
    assert input_blocks[2]["role"] == "user"


def test_summarize_uses_custom_transcript_labels() -> None:
    client = _FakeClient(_Sample(topic="t", items=[]))

    summarize_conversation(
        client=client,
        model="gpt-test",
        memory=[
            {"direction": "inbound", "text": "oi"},
            {"direction": "outbound", "text": "olá"},
        ],
        output_schema=_Sample,
        system_prompt="ANALISE",
        assistant_label="ASSISTENTE",
        user_label="CORRETOR",
    )

    transcript = client.responses.calls[0]["input"][-1]["content"]
    assert "CORRETOR: oi" in transcript
    assert "ASSISTENTE: olá" in transcript
