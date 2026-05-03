"""Render digest bodies with the standard narrative scaffolding.

Every narrative-using product digest service merges the same three keys
into its Jinja context — `narrative` (the LLM string), `narrative_paragraphs`
(the `\\n\\n` split), and `prompt_version` (the model-prompt version
identifier). This helper does it once + delegates rendering to the
existing `noctusai_lib.integrations.email.digest.render(...)`.

Caller's `context` dict wins on key collision — passing your own
`narrative_paragraphs` (e.g. for a custom split rule) is supported.

Helper trio:
- `email_template_dir(service_file)` — replaces the recurring
  `Path(__file__).resolve().parent.parent / "email_templates"` expression
  (5 products had it verbatim before formalization).
- `render_with_narrative(html_template, text_template, ...)` — the
  full-control shape. Use when html + text template names diverge.
- `render_digest_pair(template_basename, ...)` — convenience shape that
  derives `<basename>.html.j2` + `<basename>.txt.j2` (the convention every
  adopter follows). Reduces the per-product `_render_bodies` wrapper to
  a one-liner.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from noctusai_lib.integrations.email.digest import render as render_digest


def email_template_dir(service_file: str) -> Path:
    """Resolve the per-product `app/email_templates/` directory.

    Adopters call `email_template_dir(__file__)` from inside
    `app/services/<digest>_service.py` and the helper returns
    `app/email_templates/`.

    Replaces the recurring expression
    `Path(__file__).resolve().parent.parent / "email_templates"` that
    appeared verbatim in 5 products (formalized 2026-05-03).
    """
    return Path(service_file).resolve().parent.parent / "email_templates"


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


def render_digest_pair(
    template_basename: str,
    *,
    narrative: str,
    context: dict[str, Any],
    search_paths: Sequence[Path | str],
    prompt_version: str,
) -> tuple[str, str]:
    """Render `(html, text)` from `<basename>.html.j2` + `<basename>.txt.j2`.

    Convenience over `render_with_narrative` for the common case where
    the html + text templates share a basename — the convention every
    digest adopter follows. Reduces a per-product `_render_bodies`
    wrapper from a 15-line function to a one-liner.

    Use `render_with_narrative` directly when basenames diverge.

    Example:
        render_digest_pair(
            "audit_digest",
            narrative=narrative,
            context={"org_name": ...},
            search_paths=[email_template_dir(__file__)],
            prompt_version="core-audit-digest@v1",
        )
    """
    return render_with_narrative(
        html_template=f"{template_basename}.html.j2",
        text_template=f"{template_basename}.txt.j2",
        narrative=narrative,
        context=context,
        search_paths=search_paths,
        prompt_version=prompt_version,
    )
