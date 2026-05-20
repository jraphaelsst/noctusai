"""FakeImageGenAdapter — deterministic + records calls."""

from noctusai_lib.integrations.image_gen import (
    FakeImageGenAdapter,
    ImagePromptInput,
)


def test_fake_returns_deterministic_url_per_prompt() -> None:
    adapter = FakeImageGenAdapter()
    a = adapter.generate(ImagePromptInput(prompt="A photo of a cat"))
    b = adapter.generate(ImagePromptInput(prompt="A photo of a cat"))
    assert a.image_url == b.image_url
    assert a.image_url.startswith("https://fake-image-gen.noctusai.local/")
    assert a.image_url.endswith(".png?renderer=nano_banana&aspect=1:1")


def test_fake_returns_different_url_for_different_prompt() -> None:
    adapter = FakeImageGenAdapter()
    a = adapter.generate(ImagePromptInput(prompt="A photo of a cat"))
    b = adapter.generate(ImagePromptInput(prompt="A photo of a dog"))
    assert a.image_url != b.image_url


def test_fake_records_calls() -> None:
    adapter = FakeImageGenAdapter()
    adapter.generate(
        ImagePromptInput(prompt="A", renderer="galilai", aspect_ratio="9:16"),
        org_id="org-1",
    )
    adapter.generate(
        ImagePromptInput(prompt="B", renderer="midjourney", aspect_ratio="16:9"),
        org_id="org-2",
    )
    assert len(adapter.calls) == 2
    assert adapter.calls[0]["renderer"] == "galilai"
    assert adapter.calls[0]["org_id"] == "org-1"
    assert adapter.calls[1]["aspect_ratio"] == "16:9"


def test_fake_carries_renderer_label_through_to_result() -> None:
    adapter = FakeImageGenAdapter()
    image = adapter.generate(
        ImagePromptInput(prompt="X", renderer="midjourney"),
    )
    assert image.renderer == "midjourney"
    assert image.model == "fake-image-gen"
    assert image.raw["request_id"] is None


def test_fake_carries_request_id_through() -> None:
    adapter = FakeImageGenAdapter()
    image = adapter.generate(
        ImagePromptInput(prompt="X", request_id="req-abc"),
    )
    assert image.raw["request_id"] == "req-abc"
