"""Named per-provider OAuth scope bundles — opt-in-by-name.

WHY this module
---------------
Pattern 3 (single-consent multi-scope bundling) works mechanically
today — all consuming adapters read the same credential row with a
scope list = union of every consuming adapter's needs. But the union is
**hand-assembled** per consumer. This module names the common subsets so
a product config opts in by *name* (`GOOGLE_BUNDLE_PRODUCTIVITY`)
instead of re-typing scope unions.

Single source of truth
----------------------
Every bundle is a **named subset of an already-shipped kitchen-sink
list** — `GOOGLE_KITCHEN_SINK_SCOPES` (`integrations.google_scopes`) /
`META_KITCHEN_SINK_SCOPES` (`integrations.meta`). Bundles do NOT
introduce new scope literals: the kitchen-sink constant remains the one
place a provider's scope catalog lives. Extending a bundle to a scope
not yet in the kitchen-sink means adding the literal to the kitchen-sink
first (and, for Google, to the GCP Console Consent Screen — see the
`integrations.google_scopes` operator note), then to the bundle here.
A startup assertion enforces the subset invariant so a typo or a
kitchen-sink edit that drops a scope fails loudly, not silently.

Layer placement
---------------
`noctusai_lib.integrations` (sibling of the per-provider scope modules)
so consumers have ONE import surface for bundles regardless of provider,
while the literals stay single-sourced in each provider's module.

Pure data — Fake-exempt per the seed-fake-real exemption test (a Fake
here would exercise no different code than the constants themselves).

Filed in `projects/oauth-integrations-seed-lift/` (residual gap 2 of 3).
"""

from __future__ import annotations

from noctusai_lib.integrations.google_scopes import (
    GOOGLE_KITCHEN_SINK_BASE,
    GOOGLE_KITCHEN_SINK_SCOPES,
)
from noctusai_lib.integrations.meta._meta_api import META_KITCHEN_SINK_SCOPES

_G = "https://www.googleapis.com/auth"

# ─── Google bundles (subsets of GOOGLE_KITCHEN_SINK_SCOPES) ───────────────

# Identity + file/document access. (Docs/Sheets are NOT yet in the
# kitchen-sink — when a product needs them, add the literal to
# GOOGLE_KITCHEN_SINK_SCOPES + GCP Console first, then widen here.)
GOOGLE_BUNDLE_PRODUCTIVITY: list[str] = GOOGLE_KITCHEN_SINK_BASE + [
    f"{_G}/drive.readonly",
    f"{_G}/drive.file",
    f"{_G}/drive.metadata.readonly",
]

# Identity + Calendar. (Gmail is NOT yet in the kitchen-sink — same
# extension contract as above.)
GOOGLE_BUNDLE_COMMUNICATIONS: list[str] = GOOGLE_KITCHEN_SINK_BASE + [
    f"{_G}/calendar",
    f"{_G}/calendar.events",
]

# ─── Meta bundles (subsets of META_KITCHEN_SINK_SCOPES) ───────────────────

# Read-only social presence — no write/manage scopes.
META_BUNDLE_READ_ONLY: list[str] = [
    "public_profile",
    "pages_show_list",
    "pages_read_engagement",
    "pages_read_user_content",
    "read_insights",
    "instagram_basic",
    "instagram_manage_insights",
]

# Full social surface — everything the shipped kitchen-sink grants
# (read-only v1 catalog; write scopes are App-Review-gated and not yet
# in the kitchen-sink, so FULL_SOCIAL == the kitchen-sink today).
META_BUNDLE_FULL_SOCIAL: list[str] = list(META_KITCHEN_SINK_SCOPES)


_BUNDLES: dict[str, list[str]] = {
    "google_productivity": GOOGLE_BUNDLE_PRODUCTIVITY,
    "google_communications": GOOGLE_BUNDLE_COMMUNICATIONS,
    "meta_read_only": META_BUNDLE_READ_ONLY,
    "meta_full_social": META_BUNDLE_FULL_SOCIAL,
}

# Startup-time subset invariant: every bundle MUST be a subset of its
# provider kitchen-sink. Fails loudly (not silently) if a literal drifts
# or the kitchen-sink drops a scope a bundle still names.
_GOOGLE_SINK = set(GOOGLE_KITCHEN_SINK_SCOPES)
_META_SINK = set(META_KITCHEN_SINK_SCOPES)
for _name, _scopes in _BUNDLES.items():
    _sink = _GOOGLE_SINK if _name.startswith("google_") else _META_SINK
    _stray = [s for s in _scopes if s not in _sink]
    if _stray:
        raise AssertionError(
            f"OAuth bundle {_name!r} names scope(s) not in its provider "
            f"kitchen-sink (single-source-of-truth violation): {_stray}. "
            f"Add the literal to the kitchen-sink constant first."
        )
del _name, _scopes, _sink, _stray, _GOOGLE_SINK, _META_SINK


def resolve_bundle(name: str) -> list[str]:
    """Resolve a bundle name to its concrete scope list (a fresh copy).

    Args:
        name: one of `google_productivity`, `google_communications`,
            `meta_read_only`, `meta_full_social` (case-insensitive).

    Returns:
        A new list of scope strings (mutating it does not affect the
        module constant).

    Raises:
        ValueError: unknown bundle name (lists the valid names).
    """
    key = name.strip().lower()
    if key not in _BUNDLES:
        valid = ", ".join(sorted(_BUNDLES))
        raise ValueError(
            f"unknown OAuth scope bundle: {name!r}. Valid: {valid}"
        )
    return list(_BUNDLES[key])


def bundle_names() -> list[str]:
    """Sorted list of valid bundle names (for config validation / docs)."""
    return sorted(_BUNDLES)


__all__ = [
    "GOOGLE_BUNDLE_COMMUNICATIONS",
    "GOOGLE_BUNDLE_PRODUCTIVITY",
    "META_BUNDLE_FULL_SOCIAL",
    "META_BUNDLE_READ_ONLY",
    "bundle_names",
    "resolve_bundle",
]
