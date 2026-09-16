"""Field access that works on real Stripe SDK objects AND plain dicts.

The real SDK's `StripeObject` (stripe>=15) supports `in` and `[]` but has
no `.get()`, and `dict(obj)` raises `KeyError`; `to_dict()` is the only
safe full conversion. Code written against a plain-dict test double used
`.get()` / `dict()` and failed on first real use — this module is the one
place that knows the difference (used by `real_stripe`, `checkout` and
`webhook_events`).
"""
from __future__ import annotations

from typing import Any


def stripe_field(obj: Any, key: str, default: Any = None) -> Any:
    """`obj[key]` when present, else `default` — for StripeObject or dict."""
    if obj is None:
        return default
    try:
        return obj[key] if key in obj else default
    except TypeError:
        return default


def stripe_to_dict(obj: Any) -> dict[str, Any]:
    """A plain, recursive dict copy of a StripeObject (or a dict)."""
    if obj is None:
        return {}
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    return dict(obj)


__all__ = ["stripe_field", "stripe_to_dict"]
