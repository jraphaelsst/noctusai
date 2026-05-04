"""Keeper tools — `keeper_validate` + `keeper_review`.

Wraps `noctus.dev.validate` and `noctus.dev.review`. Per `feedback_keeper_observation_only`,
keeper is observation-only — these tools detect + (in review) author proposal
drafts; they NEVER modify product code.
"""

from __future__ import annotations

from typing import Any, Callable, Literal

from dev_team.tools._mcp_path import ensure_mcp_path


def _import_compliance_module():
    ensure_mcp_path()
    # noinspection PyUnresolvedReferences
    from tools.noctus.dev import compliance as _c  # type: ignore[import-not-found]

    return _c


def _import_review_module():
    ensure_mcp_path()
    # noinspection PyUnresolvedReferences
    from tools.noctus.dev import review as _r  # type: ignore[import-not-found]

    return _r


def keeper_validate(slug: str | None = None) -> dict:
    """Run keeper compliance check.

    Args:
        slug: Optional product slug. If omitted, scores every product +
            returns the platform rollup.

    Returns:
        ``{"score": int, "issues": [...]}`` (all-products) or
        ``{"product": str, "score": int, "issues": [...]}`` (single product).
    """
    compliance = _import_compliance_module()
    if slug:
        return compliance.validate_one_product(slug)
    score, issues = compliance.check_all_products()
    return {"score": score, "issues": issues}


def keeper_review(
    product_slug: str | None = None,
    mode: Literal["agent", "headless", "evaluate"] = "agent",
    model: str = "gpt-4o-mini",
) -> dict:
    """Run keeper review.

    Args:
        product_slug: Optional — scope to one product.
        mode: ``agent`` (default — issues + review_prompt only, no write),
            ``headless`` (author proposals via OpenAI), or ``evaluate``
            (write to scratch subfolder).
        model: OpenAI model for headless/evaluate modes.
    """
    review = _import_review_module()
    return review.run_review(product_slug=product_slug, mode=mode, model=model)


def build_keeper_validate_tool(**kwargs) -> Callable:
    return keeper_validate


def build_keeper_review_tool(**kwargs) -> Callable:
    return keeper_review


__all__ = [
    "keeper_validate",
    "keeper_review",
    "build_keeper_validate_tool",
    "build_keeper_review_tool",
]
