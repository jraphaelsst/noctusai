"""Render digest bodies with the standard narrative scaffolding.

Every narrative-using product digest service merges the same three keys
into its Jinja context — `narrative` (the LLM string), `narrative_paragraphs`
(the `\\n\\n` split), and `prompt_version` (the model-prompt version
identifier). This helper does it once + delegates rendering to the
existing `noctusai_lib.integrations.email.digest.render(...)`.

Caller's `context` dict wins on key collision — passing your own
`narrative_paragraphs` (e.g. for a custom split rule) is supported.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from noctusai_lib.integrations.email.digest import render as render_digest


def render_with_narrative(
    *,
    html_template: str,
    text_template: str,
    narrative: str,
    context: dict[str, Any],
    search_paths: Sequence[Path | str],
    prompt_version: str,
) -> tuple[str, str]:
    """Render `(html, text)` digest bodies with narrative scaffolding.

    Parameters:
        html_template: HTML template filename (resolved via search_paths
            then the lib's shared template dir).
        text_template: Plain-text template filename.
        narrative: The LLM-generated narrative string.
        context: Per-product Jinja context. Caller's keys win on
            collision with the auto-merged scaffolding keys.
        search_paths: Product template dirs (searched first).
        prompt_version: Identifier like "core-audit-digest@v1" — threaded
            into the rendered context for traceability.

    Returns:
        `(html, text)` rendered bodies.
    """
    full_context = {
        "narrative": narrative,
        "narrative_paragraphs": [p for p in narrative.split("\n\n") if p.strip()],
        "prompt_version": prompt_version,
        **context,
    }
    return render_digest(
        html_template=html_template,
        text_template=text_template,
        context=full_context,
        search_paths=search_paths,
    )
