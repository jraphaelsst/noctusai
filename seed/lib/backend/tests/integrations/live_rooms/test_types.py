"""Pure value objects — no IO."""
from noctusai_lib.integrations.live_rooms.types import (
    DefaultOutput,
    RecordingSpec,
    S3Output,
)


def test_recording_spec_defaults_to_default_output() -> None:
    spec = RecordingSpec(file_type="ogg", filepath="x.ogg")
    assert isinstance(spec.output, DefaultOutput)
    assert spec.audio_only is False
    assert spec.layout == "grid"


def test_recording_spec_with_s3_output() -> None:
    output = S3Output(
        bucket="b", region="r", endpoint="e", access_key="ak", secret="sk"
    )
    spec = RecordingSpec(file_type="mp4", filepath="x.mp4", output=output)
    assert spec.output.bucket == "b"
    assert spec.output.force_path_style is True
