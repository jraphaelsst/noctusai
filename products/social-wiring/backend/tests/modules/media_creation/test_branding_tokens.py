"""Server-side validation of a branding's ``tokens`` object."""
from __future__ import annotations

import copy
import json

import pytest

from app.modules.media_creation.branding.tokens_schema import (
    TokensValidationError,
    validate_tokens,
)

from ._branding_fixtures import DESIGN_SYSTEMS, TOKENS


@pytest.mark.parametrize(
    "system",
    ["branding-template", "nos-no-limiar-monica", "store-visual-identity-gilson", "noctusai"],
)
def test_real_design_system_tokens_validate(system):
    raw = json.loads((DESIGN_SYSTEMS / system / "tokens.json").read_text(encoding="utf-8"))
    out = validate_tokens(raw)
    assert out["color"]["tokens"], system
    # scales other than the base keys survive (spacing/radius/opacity)
    assert "spacing" in out and "radius" in out


def _bad(mutate):
    t = copy.deepcopy(TOKENS)
    mutate(t)
    with pytest.raises(TokensValidationError) as ei:
        validate_tokens(t)
    return str(ei.value)


def test_rejects_non_object():
    with pytest.raises(TokensValidationError):
        validate_tokens([])  # type: ignore[arg-type]


def test_rejects_reference_to_unknown_token():
    msg = _bad(lambda t: t["color"]["tokens"].append({"name": "x", "value": "{nope}", "usage": ""}))
    assert "nope" in msg


def test_rejects_unknown_theme_in_value_map():
    msg = _bad(
        lambda t: t["color"]["tokens"].append({"name": "x", "value": {"sepia": "#000"}, "usage": ""})
    )
    assert "sepia" in msg


@pytest.mark.parametrize(
    "value",
    ["red; } body { background: url(x)", "#fff</style><script>", "url(http://evil/x)", "expression(1)"],
)
def test_rejects_css_injection_in_values(value):
    _bad(lambda t: t["color"]["tokens"].append({"name": "x", "value": value, "usage": ""}))


def test_rejects_css_injection_in_font_family():
    _bad(lambda t: t["type"]["families"].update(display="Georgia; } x{"))


def test_rejects_group_with_unknown_family():
    msg = _bad(lambda t: t["type"]["groups"][0].update(family="missing"))
    assert "missing" in msg


def test_rejects_duplicate_color_names():
    _bad(lambda t: t["color"]["tokens"].append({"name": "ground", "value": "#000", "usage": ""}))


def test_rejects_unsafe_font_file_path():
    _bad(lambda t: t["type"]["fonts"].append({"family": "F", "file": "../../etc/passwd", "weight": "400"}))


def test_rejects_unknown_top_level_shape_for_scales():
    _bad(lambda t: t.update(weird={"not_tokens": []}))


def test_rejects_oversized_tokens():
    _bad(lambda t: t["meta"].update(source="x" * 400_000))
