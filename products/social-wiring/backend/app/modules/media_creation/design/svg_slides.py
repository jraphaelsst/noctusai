"""Deterministic SVG slide builders — one per layout role.

The in-home locked structural skeleton (canvas 1080×1350, safe-area margins,
the base layout roles cover/develop/insight/cta with the Método Audience
roles aliased onto them, gold accent rules, brand handle) as token-driven
Python builders. The palette / typography are NOT baked here — they come
from :class:`DesignTokens` (preset or per-brand ``design_tokens``). Only the
*structure* is fixed.

Output is a complete self-contained ``<svg>`` string. Fonts are referenced
by family name (``Cormorant Garamond`` / ``Inter``) matching the seed
``svg_render`` bundled faces — NO Google-fonts ``@import`` (it would not
resolve under server-side rasterization). All caller-supplied text is
XML-escaped (:func:`_esc`) — the slide engine is an injection boundary.
"""

from __future__ import annotations

from typing import Any

from app.modules.media_creation.design.tokens import DesignTokens

ROLES = ("cover", "develop", "insight", "cta")


def _esc(value: Any) -> str:
    """XML-escape caller text for safe embedding in SVG."""
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _wrap(text: str, max_chars: int) -> list[str]:
    """Greedy word-wrap into lines of ≤ ``max_chars`` (best-effort)."""
    words = (text or "").split()
    if not words:
        return []
    lines: list[str] = []
    cur = words[0]
    for w in words[1:]:
        if len(cur) + 1 + len(w) <= max_chars:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def _lines_svg(
    lines: list[str],
    *,
    x: int,
    y: int,
    line_height: int,
    family: str,
    size: int,
    fill: str,
    weight: int = 400,
    letter: str = "0",
    anchor: str = "start",
) -> str:
    out: list[str] = []
    cy = y
    for ln in lines:
        out.append(
            f'<text x="{x}" y="{cy}" font-family="{_esc(family)}" '
            f'font-size="{size}" fill="{fill}" font-weight="{weight}" '
            f'letter-spacing="{letter}" text-anchor="{anchor}">{_esc(ln)}</text>'
        )
        cy += line_height
    return "\n".join(out)


def _handle_and_pin(t: DesignTokens) -> str:
    parts: list[str] = []
    if t.handle:
        parts.append(
            f'<text x="{t.margin}" y="{t.canvas_h - t.margin + 30}" '
            f'font-family="{_esc(t.sans_family)}" font-size="16" '
            f'fill="{t.text_muted}" opacity="0.75">{_esc(t.handle)}</text>'
        )
    if t.location_pin:
        # A small drawn gold pin glyph (teardrop) + the location text. NOT an
        # emoji — no emoji font is bundled, so 📍 would rasterize as tofu.
        pin_x = t.canvas_w - t.margin - 8 * len(t.location_pin) - 28
        pin_cy = t.canvas_h - t.margin + 24
        parts.append(
            f'<path d="M {pin_x} {pin_cy - 14} '
            f'a 7 7 0 1 1 14 0 c 0 6 -7 14 -7 14 c 0 0 -7 -8 -7 -14 z" '
            f'fill="{t.accent_gold}"/>'
        )
        parts.append(
            f'<text x="{t.canvas_w - t.margin}" y="{t.canvas_h - t.margin + 30}" '
            f'font-family="{_esc(t.sans_family)}" font-size="18" font-weight="500" '
            f'fill="{t.accent_gold}" letter-spacing="2" text-anchor="end">'
            f'{_esc(t.location_pin)}</text>'
        )
    return "\n".join(parts)


def _open_svg(t: DesignTokens, *, bg: str, comment: str, extra_defs: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {t.canvas_w} {t.canvas_h}" '
        f'width="{t.canvas_w}" height="{t.canvas_h}">\n'
        f"<!-- {comment} -->\n"
        f"<defs>{extra_defs}</defs>\n"
        f'<rect width="{t.canvas_w}" height="{t.canvas_h}" fill="{bg}"/>'
    )


def _photo_standin_defs(t: DesignTokens) -> str:
    return (
        f'<linearGradient id="photoStandIn" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="{t.divider}"/>'
        f'<stop offset="50%" stop-color="{t.bg_primary}"/>'
        f'<stop offset="100%" stop-color="{t.bg_deep}"/></linearGradient>'
        f'<linearGradient id="textOverlay" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0%" stop-color="{t.bg_deep}" stop-opacity="0.92"/>'
        f'<stop offset="55%" stop-color="{t.bg_deep}" stop-opacity="0.72"/>'
        f'<stop offset="100%" stop-color="{t.bg_deep}" stop-opacity="0.35"/></linearGradient>'
    )


def build_cover(slide: dict, t: DesignTokens) -> str:
    """COVER — hook headline over a photo-standin gradient. Stops the scroll."""
    head_lines = _wrap(slide.get("headline") or "", 14)
    sub_lines = _wrap(slide.get("body") or "", 34)
    x = t.margin + 32
    svg = [_open_svg(t, bg="url(#photoStandIn)", comment=f"Slide {slide.get('slide_n')} — COVER", extra_defs=_photo_standin_defs(t))]
    svg.append(f'<rect width="{t.canvas_w}" height="{t.canvas_h}" fill="url(#textOverlay)"/>')
    # gold vertical rule
    svg.append(f'<rect x="{t.margin}" y="500" width="4" height="{40 + 80 * len(head_lines)}" fill="{t.accent_gold}"/>')
    svg.append(_lines_svg(head_lines, x=x, y=560, line_height=85, family=t.serif_family, size=72, fill=t.text_primary, letter="-0.5"))
    sub_y = 560 + 85 * len(head_lines) + 20
    svg.append(f'<rect x="{x}" y="{sub_y}" width="80" height="1.5" fill="{t.accent_gold}"/>')
    svg.append(_lines_svg(sub_lines, x=x, y=sub_y + 48, line_height=42, family=t.sans_family, size=28, fill=t.text_muted))
    svg.append(_handle_and_pin(t))
    svg.append("</svg>")
    return "\n".join(p for p in svg if p)


def build_develop(slide: dict, t: DesignTokens) -> str:
    """DEVELOP — headline + bullets on the left, photo-standin arch on the right."""
    head_lines = _wrap(slide.get("headline") or "", 22)
    body = slide.get("body") or ""
    bullets = [b.strip(" •-✦\t") for b in body.replace("•", "\n").splitlines() if b.strip(" •-✦\t")]
    if not bullets:
        bullets = _wrap(body, 40)
    x = t.margin
    svg = [_open_svg(t, bg=t.bg_primary, comment=f"Slide {slide.get('slide_n')} — DEVELOP", extra_defs=_photo_standin_defs(t))]
    # right-side photo-standin panel with a curved arch mask
    panel_x = int(t.canvas_w * 0.62)
    svg.append(
        f'<path d="M {panel_x} 0 '
        f'L {t.canvas_w} 0 L {t.canvas_w} {t.canvas_h} L {panel_x} {t.canvas_h} '
        f'Q {panel_x - 160} {t.canvas_h // 2} {panel_x} 0 Z" fill="url(#photoStandIn)"/>'
    )
    svg.append(_lines_svg(head_lines, x=x, y=360, line_height=66, family=t.serif_family, size=56, fill=t.text_primary))
    rule_y = 360 + 66 * len(head_lines) + 8
    svg.append(f'<rect x="{x}" y="{rule_y}" width="80" height="1.5" fill="{t.accent_gold}"/>')
    by = rule_y + 60
    for b in bullets[:6]:
        for i, ln in enumerate(_wrap(b, 30)):
            prefix = "✦ " if i == 0 else "   "
            svg.append(
                f'<text x="{x}" y="{by}" font-family="{_esc(t.sans_family)}" font-size="26" '
                f'fill="{t.text_muted}">{_esc(prefix)}{_esc(ln)}</text>'
            )
            by += 42
        by += 10
    svg.append(_handle_and_pin(t))
    svg.append("</svg>")
    return "\n".join(p for p in svg if p)


def build_insight(slide: dict, t: DesignTokens) -> str:
    """INSIGHT — pure typographic statement, centered, gold icon. Use sparingly."""
    head_lines = _wrap(slide.get("headline") or "", 20)
    body_lines = _wrap(slide.get("body") or "", 36)
    cx = t.canvas_w // 2
    svg = [_open_svg(t, bg=t.bg_primary, comment=f"Slide {slide.get('slide_n')} — INSIGHT")]
    svg.append(
        f'<text x="{cx}" y="430" font-family="{_esc(t.serif_family)}" font-size="120" '
        f'fill="{t.accent_gold}" text-anchor="middle">”</text>'
    )
    svg.append(_lines_svg(head_lines, x=cx, y=560, line_height=70, family=t.serif_family, size=56, fill=t.text_primary, anchor="middle"))
    rule_y = 560 + 70 * len(head_lines) + 10
    svg.append(f'<rect x="{cx - 40}" y="{rule_y}" width="80" height="1.5" fill="{t.accent_gold}"/>')
    svg.append(_lines_svg(body_lines, x=cx, y=rule_y + 60, line_height=42, family=t.sans_family, size=28, fill=t.text_muted, anchor="middle"))
    svg.append(_handle_and_pin(t))
    svg.append("</svg>")
    return "\n".join(p for p in svg if p)


def build_cta(slide: dict, t: DesignTokens, *, cta_word: str | None = None) -> str:
    """CTA — ultra-dark, hook + gold pill action button."""
    head_lines = _wrap(slide.get("headline") or "", 22)
    lead_lines = _wrap(slide.get("body") or "", 40)
    action = (cta_word or "").strip().upper() or "SAIBA MAIS"
    x = t.margin
    svg = [_open_svg(t, bg=t.bg_deep, comment=f"Slide {slide.get('slide_n')} — CTA")]
    svg.append(_lines_svg(head_lines, x=x, y=420, line_height=66, family=t.serif_family, size=56, fill=t.text_primary))
    rule_y = 420 + 66 * len(head_lines) + 8
    svg.append(f'<rect x="{x}" y="{rule_y}" width="80" height="1.5" fill="{t.accent_gold}"/>')
    lead_y = rule_y + 56
    svg.append(_lines_svg(lead_lines, x=x, y=lead_y, line_height=38, family=t.sans_family, size=24, fill=t.text_muted))
    # gold pill button
    pill_y = lead_y + 38 * len(lead_lines) + 30
    pill_w = max(260, 28 * len(action) + 80)
    svg.append(f'<rect x="{x}" y="{pill_y}" width="{pill_w}" height="84" rx="42" fill="{t.accent_gold_bright}"/>')
    svg.append(
        f'<text x="{x + pill_w // 2}" y="{pill_y + 54}" font-family="{_esc(t.sans_family)}" '
        f'font-size="30" font-weight="500" fill="{t.bg_deep}" letter-spacing="2" '
        f'text-anchor="middle">{_esc(action)}</text>'
    )
    svg.append(_handle_and_pin(t))
    svg.append("</svg>")
    return "\n".join(p for p in svg if p)


def build_slide_svg(
    role: str,
    slide: dict,
    tokens: DesignTokens,
    *,
    cta_word: str | None = None,
) -> str:
    """Dispatch to the role builder. Unknown role → cover layout (safe default).

    Método Audience roles (capa/identificacao/virada/nome/prova/valor/cta) map
    onto the four base layouts: capa→cover, virada→insight (the reframe/
    punchline), cta→cta, and the body beats (identificacao/nome/prova/valor)→
    develop. Legacy roles (cover/develop/insight/cta) still dispatch directly.
    """
    role = (role or "cover").lower()
    _ALIAS = {
        "capa": "cover",
        "identificacao": "develop",
        "identificação": "develop",
        "nome": "develop",
        "prova": "develop",
        "valor": "develop",
        "virada": "insight",
    }
    role = _ALIAS.get(role, role)
    if role == "develop":
        return build_develop(slide, tokens)
    if role == "insight":
        return build_insight(slide, tokens)
    if role == "cta":
        return build_cta(slide, tokens, cta_word=cta_word)
    return build_cover(slide, tokens)
