"""Tests for `noctusai_lib.primitives.image_sizing` — pure math, no IO."""

from __future__ import annotations

import random

import pytest

from noctusai_lib.primitives.image_sizing import (
    EDGE_MULTIPLE,
    MAX_EDGE_PX,
    MAX_TOTAL_PIXELS,
    MIN_TOTAL_PIXELS,
    NON_EXPERIMENTAL_MAX_TOTAL_PIXELS,
    compute_edit_size,
    validate_size,
)


# ---------------------------------------------------------------------------
# validate_size — the four hard API constraints
# ---------------------------------------------------------------------------

class TestValidateSizeAccepts:
    def test_a_mid_range_multiple_of_16_size_passes(self):
        assert validate_size(1568, 2336) is None

    def test_square_at_the_non_experimental_ceiling_passes(self):
        assert validate_size(1920, 1920) is None

    def test_the_experimental_zone_is_still_api_valid(self):
        # 3840x2160 = 8,294,400px = MAX_TOTAL_PIXELS exactly, and well
        # above the 2560x1440 non-experimental ceiling — the API still
        # ACCEPTS it (validate_size only enforces the four hard
        # constraints; the non-experimental cap is compute_edit_size's
        # own policy, not an API rejection).
        assert validate_size(3840, 2160) is None

    def test_min_total_pixels_boundary_passes(self):
        # 640x1024 = 655,360 = MIN_TOTAL_PIXELS exactly.
        assert validate_size(640, 1024) is None

    def test_max_total_pixels_boundary_passes(self):
        assert validate_size(3840, 2160) is None

    def test_aspect_ratio_exactly_one_to_three_passes(self):
        # 1104x3312: 1104/3312 == 1/3 exactly.
        assert validate_size(1104, 3312) is None

    def test_aspect_ratio_exactly_three_to_one_passes(self):
        assert validate_size(3312, 1104) is None

    def test_max_edge_exactly_at_the_limit_passes(self):
        # 3840 wide, keep the other edge inside every other bound.
        assert validate_size(3840, 1600) is None


class TestValidateSizeRejects:
    @pytest.mark.parametrize("width,height", [(0, 100), (100, 0), (-16, 100), (100, -16)])
    def test_non_positive_raises(self, width, height):
        with pytest.raises(ValueError, match="positive"):
            validate_size(width, height)

    @pytest.mark.parametrize("width,height", [(10.5, 100), (100, 10.5), ("100", 100)])
    def test_non_int_raises(self, width, height):
        with pytest.raises(ValueError, match="int"):
            validate_size(width, height)

    def test_bool_is_rejected_even_though_bool_is_an_int_subclass(self):
        with pytest.raises(ValueError, match="int"):
            validate_size(True, 1024)

    @pytest.mark.parametrize("width,height", [(1000, 1001), (1001, 1000), (17, 1024)])
    def test_non_multiple_of_16_raises(self, width, height):
        with pytest.raises(ValueError, match="multiples of 16"):
            validate_size(width, height)

    def test_max_edge_exceeded_raises(self):
        # 3856 is a multiple of 16 and would otherwise be in-range.
        with pytest.raises(ValueError, match="longest edge"):
            validate_size(3856, 1024)

    def test_aspect_ratio_just_past_one_to_three_raises(self):
        # 1024/3088 = 0.3316... just under 1/3.
        with pytest.raises(ValueError, match="aspect ratio"):
            validate_size(1024, 3088)

    def test_aspect_ratio_just_past_three_to_one_raises(self):
        with pytest.raises(ValueError, match="aspect ratio"):
            validate_size(3088, 1024)

    def test_total_pixels_below_minimum_raises(self):
        # 512x1024 = 524,288 < MIN_TOTAL_PIXELS, both multiples of 16,
        # aspect 0.5 is in-range — isolates the total-pixel check.
        with pytest.raises(ValueError, match="total pixel count"):
            validate_size(512, 1024)

    def test_total_pixels_above_maximum_raises(self):
        # 3840x2176 = 8,355,840 > MAX_TOTAL_PIXELS, both multiples of
        # 16, aspect ~1.77 in-range, longest edge 3840 (at the limit,
        # not over it) — isolates the total-pixel-ceiling check.
        with pytest.raises(ValueError, match="total pixel count"):
            validate_size(3840, 2176)


# ---------------------------------------------------------------------------
# compute_edit_size — pinned real-estate-photo cases
# ---------------------------------------------------------------------------

class TestComputeEditSizePinnedCases:
    def test_720x1080_vertical_upscales_roughly_2_15x(self):
        # The task's own headline example: a 720x1080 vertical photo
        # gets upscaled ~2.15x per edge before editing, not left as-is.
        w, h = compute_edit_size(720, 1080)
        assert (w, h) == (1568, 2336)
        assert 2.0 < w / 720 < 2.3
        assert 2.0 < h / 1080 < 2.3

    def test_1620x1080_horizontal(self):
        w, h = compute_edit_size(1620, 1080)
        assert (w, h) == (2336, 1568)

    def test_transposition_symmetry_1080x720_is_the_transpose_of_720x1080(self):
        # Swapping the input edges must swap the output edges exactly —
        # the sizing math has no privileged axis.
        w1, h1 = compute_edit_size(720, 1080)
        w2, h2 = compute_edit_size(1080, 720)
        assert (w2, h2) == (h1, w1)

    def test_transposition_symmetry_1620x1080_vs_1080x1620(self):
        w1, h1 = compute_edit_size(1620, 1080)
        w2, h2 = compute_edit_size(1080, 1620)
        assert (w2, h2) == (h1, w1)

    def test_square_input_stays_square(self):
        w, h = compute_edit_size(1000, 1000)
        assert w == h
        assert (w, h) == (1920, 1920)

    def test_a_much_smaller_square_reaches_the_same_ceiling(self):
        # compute_edit_size targets the largest ACCEPTABLE size for the
        # aspect ratio, independent of how small the input actually is.
        assert compute_edit_size(100, 100) == (1920, 1920)
        assert compute_edit_size(16, 16) == (1920, 1920)

    def test_exact_one_to_three_aspect_boundary_converges_and_is_exact(self):
        w, h = compute_edit_size(16, 48)
        assert h / w == pytest.approx(3.0)
        validate_size(w, h)

    def test_exact_three_to_one_aspect_boundary_converges_and_is_exact(self):
        w, h = compute_edit_size(48, 16)
        assert w / h == pytest.approx(3.0)
        validate_size(w, h)

    def test_input_already_at_the_boundary_and_larger_than_the_cap(self):
        # 3840x1280 is already an exact 3:1 image LARGER than the
        # non-experimental cap — compute_edit_size must scale it DOWN,
        # not just up.
        w, h = compute_edit_size(3840, 1280)
        assert w / h == pytest.approx(3.0)
        assert w * h <= NON_EXPERIMENTAL_MAX_TOTAL_PIXELS


class TestComputeEditSizeInvariants:
    """Every output must be a valid, non-experimental, sane size."""

    @pytest.mark.parametrize(
        "width,height",
        [
            (720, 1080), (1080, 720),
            (1620, 1080), (1080, 1620),
            (1000, 1000), (100, 100), (16, 16),
            (16, 48), (48, 16),
            (3840, 1280), (1280, 3840),
            (300, 300), (4000, 3000), (3000, 4000),
        ],
    )
    def test_output_always_passes_validate_size(self, width, height):
        w, h = compute_edit_size(width, height)
        validate_size(w, h)  # must not raise

    @pytest.mark.parametrize(
        "width,height",
        [
            (720, 1080), (1620, 1080), (1000, 1000),
            (16, 48), (48, 16), (3840, 1280),
        ],
    )
    def test_output_never_enters_the_experimental_zone(self, width, height):
        w, h = compute_edit_size(width, height)
        assert w * h <= NON_EXPERIMENTAL_MAX_TOTAL_PIXELS

    @pytest.mark.parametrize(
        "width,height",
        [(720, 1080), (1620, 1080), (1000, 1000), (16, 48), (3840, 1280)],
    )
    def test_output_edges_are_multiples_of_16(self, width, height):
        w, h = compute_edit_size(width, height)
        assert w % EDGE_MULTIPLE == 0
        assert h % EDGE_MULTIPLE == 0

    def test_output_aspect_ratio_stays_close_to_the_input(self):
        # Multiple-of-16 rounding can drift the ratio slightly, but not
        # by much for a realistic photo aspect ratio.
        w, h = compute_edit_size(720, 1080)
        in_aspect = 720 / 1080
        out_aspect = w / h
        assert abs(out_aspect - in_aspect) < 0.02

    def test_fuzz_random_realistic_aspect_ratios_always_produce_valid_output(self):
        rng = random.Random(20260916)
        checked = 0
        for _ in range(500):
            width = rng.randint(1, 6000)
            height = rng.randint(1, 6000)
            aspect = width / height
            if not (1 / 3 - 1e-9 <= aspect <= 3 + 1e-9):
                continue
            w, h = compute_edit_size(width, height)
            validate_size(w, h)
            assert w * h <= NON_EXPERIMENTAL_MAX_TOTAL_PIXELS
            checked += 1
        assert checked > 200  # sanity: the aspect filter didn't eat the whole run


class TestComputeEditSizeRejects:
    @pytest.mark.parametrize("width,height", [(0, 100), (100, 0), (-16, 100)])
    def test_non_positive_raises(self, width, height):
        with pytest.raises(ValueError, match="positive"):
            compute_edit_size(width, height)

    @pytest.mark.parametrize("width,height", [(10.5, 100), (100, 10.5)])
    def test_non_int_raises(self, width, height):
        with pytest.raises(ValueError, match="int"):
            compute_edit_size(width, height)

    def test_aspect_ratio_outside_one_to_three_raises(self):
        with pytest.raises(ValueError, match="aspect ratio"):
            compute_edit_size(100, 500)

    def test_aspect_ratio_outside_three_to_one_raises(self):
        with pytest.raises(ValueError, match="aspect ratio"):
            compute_edit_size(500, 100)
