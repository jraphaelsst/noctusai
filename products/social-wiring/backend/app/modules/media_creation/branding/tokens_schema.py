"""Server-side validation of a branding's ``tokens`` object.

The shape mirrors a design system's ``tokens.json`` (the Branding Template):

    {
      "name": str, "version": int, "meta": {"source": str},
      "color":   {"themes": [{"id","name"}],
                  "tokens": [{"name", "value": str | {themeId: str}, "usage"}]},
      "type":    {"fonts": [{"family","file","weight"}],
                  "families": {key: css-font-family},
                  "groups": [{"name","family","styles":[{name,fontSize,
                              lineHeight,fontWeight,letterSpacing?,sample,usage}]}]},
      "spacing": {"tokens": [{"name","value","usage"}]},
      "radius":  {...}, "opacity": {...}     # any other scale: {"tokens": [...]}
    }

Why it is strict: token values flow into CSS custom properties that the UI
injects into a sandboxed preview. A value that could close its declaration
(``;`` ``{`` ``}``), open a tag (``<``), or fetch a URL is rejected at the
boundary — the UI also re-checks, but the database must not hold such a row.

A colour value is a literal, a per-theme map of literals, or a REFERENCE to
another colour token written ``{token-name}`` (resolved by the UI per theme).
A reference to a token that does not exist is an error — never a silent blank.
"""
from __future__ import annotations

import json
import re
from typing import Any, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

MAX_TOKENS_BYTES = 300_000
MAX_ENTRIES = 400

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_REF = re.compile(r"^\{([A-Za-z0-9][A-Za-z0-9_.-]{0,63})\}$")
_FORBIDDEN_CHARS = set(";{}<>\\")
_FORBIDDEN_FRAGMENTS = ("url(", "expression(", "javascript:", "@import", "/*", "*/")

_BASE_KEYS = {"name", "version", "meta", "color", "type"}


class TokensValidationError(ValueError):
    """The ``tokens`` object failed validation (message is user-presentable)."""


def is_reference(value: str) -> str | None:
    """Return the referenced token name when ``value`` is a whole ``{ref}``."""
    m = _REF.match(value)
    return m.group(1) if m else None


def check_css_value(value: str, *, where: str) -> str:
    """Reject a value that could escape a CSS declaration or fetch a URL."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: value must be a non-empty string")
    if len(value) > 200:
        raise ValueError(f"{where}: value is longer than 200 characters")
    if is_reference(value):
        return value
    if any(c in _FORBIDDEN_CHARS for c in value):
        raise ValueError(f"{where}: value contains a forbidden character ({value[:40]!r})")
    low = value.lower()
    for frag in _FORBIDDEN_FRAGMENTS:
        if frag in low:
            raise ValueError(f"{where}: value contains {frag!r}")
    return value


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Theme(_Model):
    id: str = Field(pattern=_NAME.pattern)
    name: str = Field(min_length=1, max_length=80)


class TokenEntry(_Model):
    name: str = Field(pattern=_NAME.pattern)
    value: Union[str, dict[str, str]]
    usage: str = Field(default="", max_length=2000)


class FontFace(_Model):
    family: str = Field(min_length=1, max_length=80)
    file: str = Field(min_length=1, max_length=200)
    weight: Union[str, int] = "400"


class TypeStyle(_Model):
    name: str = Field(min_length=1, max_length=64)
    fontSize: str = Field(max_length=32)
    lineHeight: Union[str, int, float]
    fontWeight: Union[str, int]
    letterSpacing: str | None = Field(default=None, max_length=32)
    sample: str = Field(default="", max_length=500)
    usage: str = Field(default="", max_length=2000)


class TypeGroup(_Model):
    name: str = Field(min_length=1, max_length=120)
    family: str = Field(min_length=1, max_length=64)
    styles: list[TypeStyle] = Field(max_length=MAX_ENTRIES)


class ColorSection(_Model):
    themes: list[Theme] = Field(min_length=1, max_length=12)
    tokens: list[TokenEntry] = Field(max_length=MAX_ENTRIES)


class TypeSection(_Model):
    fonts: list[FontFace] = Field(default_factory=list, max_length=64)
    families: dict[str, str] = Field(default_factory=dict)
    groups: list[TypeGroup] = Field(default_factory=list, max_length=64)


class Scale(_Model):
    tokens: list[TokenEntry] = Field(max_length=MAX_ENTRIES)


class TokensMeta(_Model):
    source: str = Field(default="", max_length=4000)


class BrandingTokens(_Model):
    name: str = Field(min_length=1, max_length=120)
    version: int = 1
    meta: TokensMeta = Field(default_factory=TokensMeta)
    color: ColorSection
    type: TypeSection

    @model_validator(mode="after")
    def _cross_checks(self) -> "BrandingTokens":
        themes = {t.id for t in self.color.themes}
        names = [t.name for t in self.color.tokens]
        if len(set(names)) != len(names):
            dup = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(f"color: duplicate token names {dup}")
        known = set(names)
        for tok in self.color.tokens:
            values: dict[str, str] = (
                {"*": tok.value} if isinstance(tok.value, str) else dict(tok.value)
            )
            if not values:
                raise ValueError(f"color.{tok.name}: empty theme map")
            for theme_id, raw in values.items():
                if theme_id != "*" and theme_id not in themes:
                    raise ValueError(
                        f"color.{tok.name}: unknown theme {theme_id!r} (themes: {sorted(themes)})"
                    )
                check_css_value(raw, where=f"color.{tok.name}")
                ref = is_reference(raw)
                if ref and ref not in known:
                    raise ValueError(
                        f"color.{tok.name}: reference {{{ref}}} points to no colour token"
                    )
        for key, fam in self.type.families.items():
            if not _NAME.match(key):
                raise ValueError(f"type.families: invalid key {key!r}")
            check_css_value(fam, where=f"type.families.{key}")
        for group in self.type.groups:
            if group.family not in self.type.families:
                raise ValueError(
                    f"type.groups[{group.name!r}]: family {group.family!r} is not in type.families"
                )
            for style in group.styles:
                check_css_value(style.fontSize, where=f"type style {style.name}.fontSize")
                if style.letterSpacing is not None:
                    check_css_value(style.letterSpacing, where=f"type style {style.name}.letterSpacing")
        for face in self.type.fonts:
            if ".." in face.file or face.file.startswith("/"):
                raise ValueError(f"type.fonts: unsafe file path {face.file!r}")
        return self


def _validate_scale(key: str, raw: Any) -> dict[str, Any]:
    if not _NAME.match(key):
        raise TokensValidationError(f"{key}: invalid scale name")
    try:
        scale = Scale.model_validate(raw)
    except ValidationError as exc:
        raise TokensValidationError(f"{key}: {_first_error(exc)}") from exc
    seen: set[str] = set()
    for tok in scale.tokens:
        if tok.name in seen:
            raise TokensValidationError(f"{key}: duplicate token name {tok.name!r}")
        seen.add(tok.name)
        if not isinstance(tok.value, str):
            raise TokensValidationError(f"{key}.{tok.name}: value must be a string")
        try:
            check_css_value(tok.value, where=f"{key}.{tok.name}")
        except ValueError as exc:
            raise TokensValidationError(str(exc)) from exc
    return scale.model_dump(mode="json", exclude_none=True)


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    loc = ".".join(str(p) for p in err["loc"])
    return f"{loc}: {err['msg']}" if loc else err["msg"]


def validate_tokens(raw: Any) -> dict[str, Any]:
    """Validate and normalise a ``tokens`` object; raise
    :class:`TokensValidationError` with a precise message otherwise."""
    if not isinstance(raw, dict):
        raise TokensValidationError("tokens must be a JSON object")
    try:
        size = len(json.dumps(raw, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise TokensValidationError(f"tokens is not JSON-serialisable: {exc}") from exc
    if size > MAX_TOKENS_BYTES:
        raise TokensValidationError(f"tokens is larger than {MAX_TOKENS_BYTES} bytes")

    base = {k: v for k, v in raw.items() if k in _BASE_KEYS}
    scales = {k: v for k, v in raw.items() if k not in _BASE_KEYS}
    try:
        parsed = BrandingTokens.model_validate(base)
    except ValidationError as exc:
        raise TokensValidationError(_first_error(exc)) from exc
    out = parsed.model_dump(mode="json", exclude_none=True)
    for key, value in scales.items():
        out[key] = _validate_scale(key, value)
    return out
