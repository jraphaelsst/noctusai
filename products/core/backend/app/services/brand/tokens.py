"""`noctus.brand-tokens/v1` — derivation, validation, dark derivation, contrast.

CONTRACT projects/org-brand-identity/CONTRACT.md §2.

**Key set is DERIVED, never hand-listed.** The token keys are exactly the CSS
variables of `seed/lib/frontend/src/design-system/tokens.css` whose value is an
HSL triplet (radius + gradients are not palette tokens). The backend container
does not ship the seed frontend tree, so the derivation is materialised once
into `platform_tokens.json` (next to this module) by :func:`render_artifact`, and
`tests/services/test_brand_tokens.py` fails the moment that artifact and
`tokens.css` disagree — derive, don't sync by hand. Regenerate with::

    python -c "from app.services.brand.tokens import write_artifact; write_artifact()"

(run from `products/core/backend` inside a full checkout). Migration 089 seeds
the platform row from the SAME values (its own test compares them).

**CSS-injection guard.** Every value that can reach the browser is matched
against a closed regex (HSL triplet / rem|px radius / font family charset) and
range-checked. Anything else is refused (HTTP) or dropped + reported (LLM
output). Values are applied client-side via `style.setProperty`, never
interpolated into a stylesheet string — this module is the server half.
"""
from __future__ import annotations

import colorsys
import copy
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

SCHEMA_ID = "noctus.brand-tokens/v1"

HSL_RE = re.compile(r"^\d{1,3}(\.\d+)? \d{1,3}(\.\d+)?% \d{1,3}(\.\d+)?%$")
RADIUS_RE = re.compile(r"^\d+(\.\d+)?(rem|px)$")
FONT_FAMILY_RE = re.compile(r"^[A-Za-z0-9 \-]{1,64}$")

FONT_ROLES = ("heading", "body", "ui")
FONT_SOURCES = ("google", "asset", "system")
FONT_WEIGHTS = frozenset(range(100, 1000, 100))
MAX_FONT_WEIGHTS = 9
#: Radius upper bounds (a 900px radius is not a brand, it is an attack on layout).
MAX_RADIUS = {"rem": 4.0, "px": 64.0}

WCAG_AA = 4.5
_TOP_LEVEL_KEYS = frozenset({"schema", "light", "dark", "radius", "fonts"})
_FONT_KEYS = frozenset({"family", "weights", "source"})

ARTIFACT_PATH = Path(__file__).with_name("platform_tokens.json")
#: Repo-relative source of truth (only present in a full checkout, never in the image).
TOKENS_CSS_REL = "seed/lib/frontend/src/design-system/tokens.css"


class BrandTokensError(ValueError):
    """Tokens refused. ``errors`` lists every problem (never only the first)."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = list(errors)


# ── derivation from tokens.css ──────────────────────────────────────────────

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_DECL_RE = re.compile(r"--([a-z0-9-]+)\s*:\s*([^;]+);")


def _block(css: str, selector: str) -> str:
    """Body of the FIRST ``<selector> { ... }`` block (no nested braces inside)."""
    m = re.search(re.escape(selector) + r"\s*\{([^{}]*)\}", css)
    if not m:
        raise ValueError(f"tokens.css: no {selector!r} block")
    return m.group(1)


def parse_tokens_css(css: str) -> dict[str, Any]:
    """``{"keys", "light", "dark", "radius"}`` derived from tokens.css text.

    A token = a custom property whose value is an HSL triplet. ``.dark`` must
    declare exactly the same token keys as ``:root`` (else the CSS itself drifted
    and we refuse to guess)."""
    css = _COMMENT_RE.sub("", css)

    def decls(sel: str) -> dict[str, str]:
        return {k: v.strip() for k, v in _DECL_RE.findall(_block(css, sel))}

    root, dark = decls(":root"), decls(".dark")
    light = {k: v for k, v in root.items() if HSL_RE.match(v)}
    dark_tokens = {k: v for k, v in dark.items() if HSL_RE.match(v)}
    if set(light) != set(dark_tokens):
        raise ValueError(
            "tokens.css: :root and .dark declare different token keys: "
            f"only-root={sorted(set(light) - set(dark_tokens))} only-dark={sorted(set(dark_tokens) - set(light))}"
        )
    radius = root.get("radius")
    if not radius or not RADIUS_RE.match(radius):
        raise ValueError("tokens.css: :root --radius missing or not rem/px")
    keys = list(light)
    return {
        "keys": keys,
        "light": light,
        "dark": {k: dark_tokens[k] for k in keys},
        "radius": radius,
    }


def render_artifact(css: str) -> str:
    """The exact text of ``platform_tokens.json`` for ``css`` (deterministic)."""
    parsed = parse_tokens_css(css)
    doc = {
        "_generated_from": TOKENS_CSS_REL,
        **parsed,
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def find_tokens_css(start: Optional[Path] = None) -> Optional[Path]:
    """``tokens.css`` in the enclosing checkout, else ``None`` (container)."""
    here = (start or Path(__file__)).resolve()
    for parent in here.parents:
        candidate = parent / TOKENS_CSS_REL
        if candidate.is_file():
            return candidate
    return None


def write_artifact() -> Path:
    css_path = find_tokens_css()
    if css_path is None:
        raise FileNotFoundError(f"{TOKENS_CSS_REL} not found above {__file__}")
    ARTIFACT_PATH.write_text(render_artifact(css_path.read_text(encoding="utf-8")), encoding="utf-8")
    return ARTIFACT_PATH


@lru_cache(maxsize=1)
def _artifact() -> dict[str, Any]:
    return json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))


def token_keys() -> tuple[str, ...]:
    return tuple(_artifact()["keys"])


def platform_tokens() -> dict[str, Any]:
    """The NOC standard as a full ``noctus.brand-tokens/v1`` document (fresh copy)."""
    a = _artifact()
    return {
        "schema": SCHEMA_ID,
        "light": dict(a["light"]),
        "dark": dict(a["dark"]),
        "radius": a["radius"],
        "fonts": {},
    }


# ── value parsing ───────────────────────────────────────────────────────────

def parse_hsl(value: Any) -> Optional[tuple[float, float, float]]:
    """``(h, s, l)`` for a valid triplet in range (h ≤ 360, s/l ≤ 100), else ``None``."""
    if not isinstance(value, str) or not HSL_RE.match(value):
        return None
    h_s, s_s, l_s = value.split(" ")
    h, s, l = float(h_s), float(s_s[:-1]), float(l_s[:-1])
    if h > 360 or s > 100 or l > 100:
        return None
    return h, s, l


def format_hsl(h: float, s: float, l: float) -> str:
    def num(x: float) -> str:
        x = round(x, 1)
        return str(int(x)) if x == int(x) else f"{x:.1f}"

    return f"{num(h)} {num(s)}% {num(l)}%"


def valid_radius(value: Any) -> bool:
    if not isinstance(value, str) or not RADIUS_RE.match(value):
        return False
    unit = "rem" if value.endswith("rem") else "px"
    return float(value[: -len(unit)]) <= MAX_RADIUS[unit]


# ── dark derivation (deterministic) ─────────────────────────────────────────

def _base_of(key: str) -> Optional[str]:
    """The surface a ``*-foreground`` token is read on (``foreground`` → ``background``)."""
    if key == "foreground":
        return "background"
    if key == "sidebar-foreground":
        return "sidebar-background"
    if key.endswith("-foreground"):
        return key[: -len("-foreground")]
    return None


def derive_dark(light: dict[str, str]) -> dict[str, str]:
    """A dark palette from a light one. Pure + deterministic; hue is preserved.

    Rules (by the token's ROLE, read from its name and its light lightness —
    never a per-key table):

    * ``*-foreground`` whose surface is light (L ≥ 50) → lightness inverted;
      a foreground that sits on a strong/dark surface (white on primary) is kept.
    * light surfaces and tints (L ≥ 80: background, card, *-light, border…) →
      ``L' = max(100 − L, 6)``, saturation halved (dark tints stay quiet).
    * already-dark surfaces (L ≤ 20, e.g. the sidebar) → ``L' = max(L − 4, 4)``.
    * mid tones (brand/status/chart colours) → ``L' = min(L + 10, 90)``.

    Contrast of the result is NOT assumed: :func:`contrast_report` checks it."""
    out: dict[str, str] = {}
    for key, value in light.items():
        hsl = parse_hsl(value)
        if hsl is None:
            continue
        h, s, l = hsl
        base = _base_of(key)
        if base is not None:
            base_hsl = parse_hsl(light.get(base))
            if base_hsl is not None and base_hsl[2] >= 50:
                out[key] = format_hsl(h, s, 100 - l)
            else:
                out[key] = format_hsl(h, s, l)
        elif l >= 80:
            out[key] = format_hsl(h, s / 2, max(100 - l, 6))
        elif l <= 20:
            out[key] = format_hsl(h, s, max(l - 4, 4))
        else:
            out[key] = format_hsl(h, s, min(l + 10, 90))
    return out


# ── WCAG contrast ───────────────────────────────────────────────────────────

def _relative_luminance(hsl: tuple[float, float, float]) -> float:
    h, s, l = hsl
    r, g, b = colorsys.hls_to_rgb(h / 360.0, l / 100.0, s / 100.0)

    def chan(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast_ratio(fg: str, bg: str) -> Optional[float]:
    a, b = parse_hsl(fg), parse_hsl(bg)
    if a is None or b is None:
        return None
    la, lb = _relative_luminance(a), _relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return round((hi + 0.05) / (lo + 0.05), 2)


def contrast_report(tokens: dict[str, Any]) -> list[dict[str, Any]]:
    """Every foreground/surface pair (derived from the key names) of both modes,
    with its WCAG ratio. Never trusts a ratio from anywhere else."""
    report: list[dict[str, Any]] = []
    for mode in ("light", "dark"):
        palette = tokens.get(mode) or {}
        for key in palette:
            base = _base_of(key)
            if base is None or base not in palette:
                continue
            ratio = contrast_ratio(palette[key], palette[base])
            if ratio is None:
                continue
            report.append({
                "mode": mode, "foreground": key, "background": base,
                "ratio": ratio, "passes_aa": ratio >= WCAG_AA,
            })
    return report


# ── validation ──────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    tokens: dict[str, Any]
    filled_from_default: list[str] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)
    dark_derived: bool = False
    contrast: list[dict[str, Any]] = field(default_factory=list)

    def as_validation(self) -> dict[str, Any]:
        warnings = [
            f"contraste {c['mode']} {c['foreground']} sobre {c['background']}: {c['ratio']}:1 (< {WCAG_AA}:1)"
            for c in self.contrast if not c["passes_aa"]
        ]
        warnings += [f"valor recusado: {r}" for r in self.refused]
        return {
            "schema": SCHEMA_ID,
            "filled_from_default": list(self.filled_from_default),
            "refused": list(self.refused),
            "dark_derived": self.dark_derived,
            "contrast": list(self.contrast),
            "warnings": warnings,
        }


def _validate_palette(
    raw: Any, mode: str, keys: tuple[str, ...], errors: list[str],
) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        errors.append(f"{mode}: deve ser um objeto")
        return {}
    out: dict[str, str] = {}
    known = set(keys)
    for k, v in raw.items():
        if k not in known:
            errors.append(f"{mode}.{str(k)[:64]}: token desconhecido")
        elif parse_hsl(v) is None:
            errors.append(f"{mode}.{k}: valor inválido (esperado 'H S% L%')")
        else:
            out[k] = v
    return out


def _validate_fonts(raw: Any, errors: list[str]) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        errors.append("fonts: deve ser um objeto")
        return {}
    out: dict[str, Any] = {}
    for role, spec in raw.items():
        if role not in FONT_ROLES:
            errors.append(f"fonts.{str(role)[:32]}: papel desconhecido")
            continue
        if not isinstance(spec, dict) or set(spec) - _FONT_KEYS or "family" not in spec:
            errors.append(f"fonts.{role}: formato inválido")
            continue
        family, weights, source = spec.get("family"), spec.get("weights", [400]), spec.get("source", "google")
        problems = []
        if not isinstance(family, str) or not FONT_FAMILY_RE.match(family):
            problems.append("family")
        if (
            not isinstance(weights, list) or not weights or len(weights) > MAX_FONT_WEIGHTS
            or any(isinstance(w, bool) or not isinstance(w, int) or w not in FONT_WEIGHTS for w in weights)
        ):
            problems.append("weights")
        if source not in FONT_SOURCES:
            problems.append("source")
        if problems:
            errors.append(f"fonts.{role}: {', '.join(problems)} inválido(s)")
            continue
        out[role] = {"family": family, "weights": sorted(set(weights)), "source": source}
    return out


def validate_tokens(
    raw: Any,
    *,
    platform: Optional[dict[str, Any]] = None,
    lenient: bool = False,
) -> ValidationResult:
    """Validate + complete a tokens document.

    ``lenient=False`` (HTTP writes): any problem raises :class:`BrandTokensError`.
    ``lenient=True`` (LLM output): invalid entries are dropped, listed in
    ``refused`` and filled from the platform row — an LLM answer can never put an
    unvalidated value in the table either way.

    Missing light/dark keys + radius are filled from ``platform`` (default: the
    NOC standard) and listed in ``filled_from_default``; a missing/empty ``dark``
    is derived from the completed light palette instead."""
    base = copy.deepcopy(platform or platform_tokens())
    keys = token_keys()
    errors: list[str] = []
    if not isinstance(raw, dict):
        raise BrandTokensError(["tokens: deve ser um objeto"])
    for k in raw:
        if k not in _TOP_LEVEL_KEYS:
            errors.append(f"{str(k)[:64]}: campo desconhecido")
    if raw.get("schema", SCHEMA_ID) != SCHEMA_ID:
        errors.append(f"schema: esperado {SCHEMA_ID!r}")

    light = _validate_palette(raw.get("light"), "light", keys, errors)
    dark_raw = raw.get("dark")
    dark = _validate_palette(dark_raw, "dark", keys, errors)

    radius = raw.get("radius")
    if radius is not None and not valid_radius(radius):
        errors.append("radius: inválido (esperado '<n>rem' ou '<n>px', dentro do limite)")
        radius = None
    fonts = _validate_fonts(raw.get("fonts"), errors)

    if errors and not lenient:
        raise BrandTokensError(errors)

    result = ValidationResult(tokens={}, refused=errors if lenient else [])
    full_light: dict[str, str] = {}
    for k in keys:
        if k in light:
            full_light[k] = light[k]
        else:
            full_light[k] = base["light"][k]
            result.filled_from_default.append(f"light.{k}")

    full_dark: dict[str, str] = {}
    if not dark and not (isinstance(dark_raw, dict) and dark_raw):
        full_dark = derive_dark(full_light)
        result.dark_derived = True
    else:
        for k in keys:
            if k in dark:
                full_dark[k] = dark[k]
            else:
                full_dark[k] = base["dark"][k]
                result.filled_from_default.append(f"dark.{k}")

    if radius is None:
        radius = base["radius"]
        result.filled_from_default.append("radius")

    result.tokens = {
        "schema": SCHEMA_ID,
        "light": full_light,
        "dark": full_dark,
        "radius": radius,
        "fonts": fonts,
    }
    result.contrast = contrast_report(result.tokens)
    return result


def assert_servable(tokens: Any) -> dict[str, Any]:
    """Re-validate a STORED document before it leaves the API (defence in depth:
    a row written by hand / an older version must still pass the same regexes).
    Raises :class:`BrandTokensError` when it does not."""
    return validate_tokens(tokens, lenient=False).tokens
