"""Sizing math for OpenAI image-edit calls — pure functions, no IO.

Built for real-estate photo virtual-staging/enhancement (contract
`edicao-fotos-contract`, Slice S3): every photo an org sends through an
OpenAI image-edit call must land on a size the API actually accepts,
and — separately — the size we WANT to target so results never fall
into the API's experimental quality tier.

OpenAI image-edit size constraints (verified 2026-09-15):

- both edges must be multiples of 16px
- aspect ratio between 1:3 and 3:1 (inclusive)
- max edge length 3,840px
- total pixel count between 655,360 and 8,294,400 (inclusive)
- above a 2,560x1,440 (3,686,400px) pixel area the API still accepts
  the request, but treats it as EXPERIMENTAL (lower, less predictable
  quality) — `compute_edit_size` never targets that region; it caps
  its own output at that ceiling so every caller gets a stable,
  production-safe size.

`validate_size` enforces ONLY the four hard API constraints above — a
size inside the experimental zone (e.g. 3840x2160) is still a VALID
size per `validate_size` (the API accepts it), it is simply not one
`compute_edit_size` will ever hand back. That split — "acceptable to
the API" vs. "the size we deliberately target" — is the reason these
are two separate functions rather than one.

Typical real-estate inputs are 720x1080 (vertical) and 1620x1080
(horizontal). Both get scaled UP substantially — a 720x1080 photo is
enlarged roughly 2.15-2.2x per edge (to ~1568x2336) before the edit
call, because its native pixel area (777,600px) is far below the
non-experimental ceiling `compute_edit_size` targets. This is
deliberate, not incidental: see the exact figures pinned in
`tests/test_image_sizing.py`.
"""

from __future__ import annotations

import math

#: Both output edges must be a multiple of this.
EDGE_MULTIPLE = 16

#: Longest edge the API accepts, in pixels.
MAX_EDGE_PX = 3840

#: Total pixel count (width * height) the API accepts, inclusive bounds.
MIN_TOTAL_PIXELS = 655_360
MAX_TOTAL_PIXELS = 8_294_400

#: Aspect ratio (width / height) the API accepts, inclusive bounds.
MIN_ASPECT_RATIO = 1.0 / 3.0
MAX_ASPECT_RATIO = 3.0 / 1.0

#: `compute_edit_size`'s own conservative ceiling — the largest total
#: pixel count it will ever target, deliberately staying OUT of the
#: EXPERIMENTAL zone (anything above a 2,560x1,440 pixel area). This is
#: a policy choice layered on top of `validate_size`'s API-acceptance
#: check, not itself an API constraint.
NON_EXPERIMENTAL_MAX_TOTAL_PIXELS = 2560 * 1440  # 3,686,400

#: Floating-point slack for the aspect-ratio boundary comparisons below
#: — 1/3 and 3/1 are not exactly representable, and inputs pinned to
#: the exact boundary (e.g. 16x48) must still validate as in-bounds.
_ASPECT_EPSILON = 1e-9


def _check_positive_ints(width: object, height: object) -> None:
    if not isinstance(width, int) or isinstance(width, bool):
        raise ValueError(f"width must be an int, got {type(width).__name__}: {width!r}")
    if not isinstance(height, int) or isinstance(height, bool):
        raise ValueError(f"height must be an int, got {type(height).__name__}: {height!r}")
    if width <= 0 or height <= 0:
        raise ValueError(f"width/height must be positive, got {width}x{height}")


def _check_aspect_ratio(width: int, height: int) -> float:
    aspect = width / height
    if not (MIN_ASPECT_RATIO - _ASPECT_EPSILON <= aspect <= MAX_ASPECT_RATIO + _ASPECT_EPSILON):
        raise ValueError(
            f"{width}x{height}: aspect ratio {aspect:.6f} is outside the "
            f"allowed [{MIN_ASPECT_RATIO:.6f}, {MAX_ASPECT_RATIO:.6f}] range "
            "(1:3 to 3:1)"
        )
    return aspect


def validate_size(width: int, height: int) -> None:
    """Raise ``ValueError`` unless ``(width, height)`` is a size an
    OpenAI image-edit call will accept. Returns ``None`` on success —
    callers that only need the pass/fail check call this directly;
    ``compute_edit_size`` calls it internally as a self-check on every
    value it returns.

    Checks (in order, so the first violation reported is the most
    fundamental one): positive integers -> multiples of
    :data:`EDGE_MULTIPLE` -> max edge -> aspect ratio -> total pixel
    range. Does NOT enforce :data:`NON_EXPERIMENTAL_MAX_TOTAL_PIXELS` —
    that cap is ``compute_edit_size``'s own policy, not something the
    API itself rejects.
    """
    _check_positive_ints(width, height)

    if width % EDGE_MULTIPLE != 0 or height % EDGE_MULTIPLE != 0:
        raise ValueError(
            f"{width}x{height}: both edges must be multiples of {EDGE_MULTIPLE}px"
        )

    if max(width, height) > MAX_EDGE_PX:
        raise ValueError(f"{width}x{height}: longest edge exceeds max {MAX_EDGE_PX}px")

    _check_aspect_ratio(width, height)

    total = width * height
    if not (MIN_TOTAL_PIXELS <= total <= MAX_TOTAL_PIXELS):
        raise ValueError(
            f"{width}x{height}: total pixel count {total} is outside the "
            f"allowed [{MIN_TOTAL_PIXELS}, {MAX_TOTAL_PIXELS}] range"
        )


def _round_to_multiple(value: float, multiple: int) -> int:
    rounded = round(value / multiple) * multiple
    return max(multiple, int(rounded))


def compute_edit_size(width: int, height: int) -> tuple[int, int]:
    """Return the largest ``(width, height)`` an OpenAI image-edit call
    will accept for an input of this aspect ratio, while staying OUT of
    the API's EXPERIMENTAL quality tier (see module docstring).

    Preserves the input's aspect ratio as closely as the mandatory
    multiple-of-16 rounding allows. Every value this function returns
    passes :func:`validate_size` by construction (asserted before
    returning, so a bug here raises loudly rather than shipping an
    API-rejected size).

    Raises ``ValueError`` for non-positive/non-int input or an input
    aspect ratio outside the API's own 1:3-3:1 range (there is no valid
    output to compute in that case).
    """
    _check_positive_ints(width, height)
    _check_aspect_ratio(width, height)

    target_area = NON_EXPERIMENTAL_MAX_TOTAL_PIXELS
    scale = math.sqrt(target_area / (width * height))

    new_w = _round_to_multiple(width * scale, EDGE_MULTIPLE)
    new_h = _round_to_multiple(height * scale, EDGE_MULTIPLE)

    # Rounding each edge INDEPENDENTLY to the nearest multiple of 16 can
    # drift the aspect ratio just past the 1:3/3:1 boundary, push the
    # area a notch over the non-experimental cap, or (for an extreme
    # aspect ratio) exceed MAX_EDGE_PX. One combined, priority-ordered
    # correction loop — aspect first (an aspect fix also moves area/edge
    # in the right direction, since fixing "too narrow"/"too wide" means
    # shrinking the currently-larger edge), then area/edge, then the
    # min-pixel floor — converges in a handful of 16px steps for every
    # input this function is meant for. The iteration cap is a
    # fail-loud guard against a future logic bug, not a value expected
    # to bind for a real photo aspect ratio.
    for _ in range(10_000):
        if new_w <= 0 or new_h <= 0:
            raise ValueError(
                f"{width}x{height}: could not compute a valid edit size "
                "within the API's constraints"
            )
        aspect = new_w / new_h
        area = new_w * new_h
        if aspect < MIN_ASPECT_RATIO - _ASPECT_EPSILON:
            new_h -= EDGE_MULTIPLE
        elif aspect > MAX_ASPECT_RATIO + _ASPECT_EPSILON:
            new_w -= EDGE_MULTIPLE
        elif area > target_area or max(new_w, new_h) > MAX_EDGE_PX:
            if new_w >= new_h:
                new_w -= EDGE_MULTIPLE
            else:
                new_h -= EDGE_MULTIPLE
        elif area < MIN_TOTAL_PIXELS:
            if new_w <= new_h:
                new_w += EDGE_MULTIPLE
            else:
                new_h += EDGE_MULTIPLE
        else:
            break
    else:
        raise ValueError(f"{width}x{height}: edit-size search did not converge")

    validate_size(new_w, new_h)
    return new_w, new_h
