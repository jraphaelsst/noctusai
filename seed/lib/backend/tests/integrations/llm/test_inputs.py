"""LLM input-shape helper tests."""

import base64
from io import BytesIO

from noctusai_lib.integrations.llm import (
    audio_bytes_to_named_buffer,
    image_bytes_to_data_url,
)


def test_image_bytes_to_data_url_round_trips_via_base64() -> None:
    raw = b"\x89PNG\r\n\x1a\n"
    url = image_bytes_to_data_url(raw, "image/png")

    assert url.startswith("data:image/png;base64,")
    decoded = base64.b64decode(url.split(",", 1)[1])
    assert decoded == raw


def test_image_bytes_to_data_url_handles_jpeg_mimetype() -> None:
    url = image_bytes_to_data_url(b"\xff\xd8\xff\xe0", "image/jpeg")
    assert url.startswith("data:image/jpeg;base64,")


def test_image_bytes_to_data_url_empty_bytes() -> None:
    url = image_bytes_to_data_url(b"", "image/png")
    assert url == "data:image/png;base64,"


def test_audio_bytes_to_named_buffer_sets_name_attribute() -> None:
    buffer = audio_bytes_to_named_buffer(b"OGGdata", "voice.ogg")
    assert isinstance(buffer, BytesIO)
    assert buffer.name == "voice.ogg"
    assert buffer.read() == b"OGGdata"


def test_audio_bytes_to_named_buffer_preserves_position_at_zero() -> None:
    buffer = audio_bytes_to_named_buffer(b"raw audio bytes", "clip.mp3")
    # OpenAI SDK reads from current position; must start at 0.
    assert buffer.tell() == 0


def test_audio_bytes_to_named_buffer_supports_multiple_reads_via_seek() -> None:
    buffer = audio_bytes_to_named_buffer(b"twice", "x.wav")
    first = buffer.read()
    buffer.seek(0)
    second = buffer.read()
    assert first == second == b"twice"
