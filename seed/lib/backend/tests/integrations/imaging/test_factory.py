"""get_imaging_adapter — picks Fake vs Real(Pillow) per the factory shape."""

from __future__ import annotations

from noctusai_lib.integrations.imaging import (
    FakeImagingAdapter,
    RealImagingAdapter,
    get_imaging_adapter,
)


def test_real_false_returns_fake() -> None:
    adapter = get_imaging_adapter(real=False)
    assert isinstance(adapter, FakeImagingAdapter)
    assert adapter.backend == "fake"


def test_real_true_returns_real() -> None:
    adapter = get_imaging_adapter(real=True)
    assert isinstance(adapter, RealImagingAdapter)
    assert adapter.backend == "pillow"


def test_default_is_real() -> None:
    assert isinstance(get_imaging_adapter(), RealImagingAdapter)
