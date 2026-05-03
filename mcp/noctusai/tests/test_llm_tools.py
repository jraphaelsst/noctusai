"""Tests for ``llm.audio.transcribe`` + ``llm.vision.analyze`` MCP tools.

Mocks the underlying ``noctusai_lib.integrations.llm.{audio,vision}``
entry points (external integration → mock allowed per rule). Validates
Pydantic in/out shape + payload routing without making real API calls.
"""

from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

MCP_ROOT = Path(__file__).resolve().parents[1]
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))


def test_transcribe_decodes_base64_and_returns_text():
    from tools.llm.audio.transcribe import TranscribeInput, transcribe

    audio_bytes = b"fake-ogg-payload"
    payload = TranscribeInput(
        audio_base64=base64.b64encode(audio_bytes).decode(),
        filename="audio.ogg",
        language="pt",
    )

    with patch(
        "noctusai_lib.integrations.llm.audio.transcribe_audio",
        new=AsyncMock(return_value="olá mundo"),
    ) as mock_transcribe:
        out = asyncio.run(transcribe(payload))

    assert out.text == "olá mundo"
    mock_transcribe.assert_awaited_once()
    call_kwargs = mock_transcribe.call_args
    assert call_kwargs.args[0] == audio_bytes
    assert call_kwargs.kwargs["filename"] == "audio.ogg"
    assert call_kwargs.kwargs["language"] == "pt"


def test_analyze_with_base64_image():
    from tools.llm.vision.analyze import AnalyzeInput, analyze

    img_bytes = b"\x89PNG\r\n"
    payload = AnalyzeInput(
        prompt="What's in this image?",
        image_base64=base64.b64encode(img_bytes).decode(),
    )

    with patch(
        "noctusai_lib.integrations.llm.vision.analyze_image",
        new=AsyncMock(return_value="A pixel."),
    ) as mock_analyze:
        out = asyncio.run(analyze(payload))

    assert out.description == "A pixel."
    mock_analyze.assert_awaited_once()
    assert mock_analyze.call_args.args[0] == img_bytes
    assert mock_analyze.call_args.args[1] == "What's in this image?"


def test_analyze_with_image_url():
    from tools.llm.vision.analyze import AnalyzeInput, analyze

    payload = AnalyzeInput(
        prompt="Describe.",
        image_url="https://example.com/img.jpg",
    )

    with patch(
        "noctusai_lib.integrations.llm.vision.analyze_image",
        new=AsyncMock(return_value="cat"),
    ) as mock_analyze:
        out = asyncio.run(analyze(payload))

    assert out.description == "cat"
    assert mock_analyze.call_args.args[0] == "https://example.com/img.jpg"


def test_analyze_rejects_both_image_sources():
    from tools.llm.vision.analyze import AnalyzeInput

    with pytest.raises(ValueError, match="Exactly one of"):
        AnalyzeInput(
            prompt="x", image_base64="aGk=", image_url="https://example.com/img.jpg"
        )


def test_analyze_rejects_neither_image_source():
    from tools.llm.vision.analyze import AnalyzeInput

    with pytest.raises(ValueError, match="Exactly one of"):
        AnalyzeInput(prompt="x")
