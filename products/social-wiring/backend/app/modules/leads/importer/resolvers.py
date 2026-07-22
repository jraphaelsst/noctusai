"""Resolve a raw ORIGEM/CORRETOR spelling to its canonical dimension row
via the org's alias map (``services.dimensions_service.
build_resolution_maps``), splitting composite multi-value cells
(``"ZAP, IMOVEL WEB"``, ``"GOOGLE/ WHATS"``, ``"REJANE/MÔNICA"``) and
taking the FIRST recognizable token — per the brief's own worked
examples for composite origem cells, applied symmetrically to composite
corretor cells (the same data-entry pattern: two values crammed into one
column).
"""
from __future__ import annotations

from typing import Optional

from app.modules.leads.seed_data import COMPOSITE_SEPARATORS, normalize_alias


def _candidate_tokens(raw: str) -> list[str]:
    """The raw value itself first (whole-string match takes priority),
    then each comma/slash-separated token."""
    tokens = [raw]
    tokens.extend(t for t in COMPOSITE_SEPARATORS.split(raw) if t.strip())
    return tokens


def resolve_origem(
    origem_raw: Optional[str], source_map: dict[str, tuple[str, bool]]
) -> tuple[Optional[str], bool]:
    """Returns ``(source_id, needs_review)``. A blank/missing origem or an
    origem with no recognizable token at all -> ``(None, True)`` —
    "unmapped origem" per the ``needs_review`` contract."""
    if not origem_raw or not origem_raw.strip():
        return None, True
    for token in _candidate_tokens(origem_raw):
        hit = source_map.get(normalize_alias(token))
        if hit is not None:
            return hit
    return None, True


def resolve_corretor(corretor_raw: Optional[str], corretor_map: dict[str, str]) -> Optional[str]:
    """Returns the resolved ``corretor_id``, or ``None`` when unmapped
    (no ``needs_review`` dimension for corretor per the contract — the
    row is still inserted, just with ``corretor_id IS NULL``)."""
    if not corretor_raw or not corretor_raw.strip():
        return None
    for token in _candidate_tokens(corretor_raw):
        hit = corretor_map.get(normalize_alias(token))
        if hit is not None:
            return hit
    return None


__all__ = ["resolve_origem", "resolve_corretor"]
