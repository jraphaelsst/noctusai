"""Plumbing shared by the seed ORGANS (finance, items, parties, inventory, commerce).

One home for what every organ used to copy: the org-scoped `Scope`, row helpers, PostgREST-safe
search terms, CSV/document masking, the org-RLS + definer `search_path` SQL generators and the
`AppException` error base. An organ's own `_common.py` / `errors.py` keep only what is theirs
(config type, domain error codes, domain helpers) and import the rest from here.
"""
from .errors import OrganError, error_factories, not_found
from .guards import GuardProbeFactory, OrganGuardProbe
from .ratelimit import RateLimit, apply_rate_limit
from .scope import OrganScope, digits, first, new_id, now, now_iso
from .sqlgen import definer_search_path, org_rls
from .text import csv_safe, like_term, like_term_wildcard, mask_doc

__all__ = [
    "GuardProbeFactory",
    "OrganGuardProbe",
    "OrganError",
    "RateLimit",
    "apply_rate_limit",
    "OrganScope",
    "csv_safe",
    "definer_search_path",
    "digits",
    "error_factories",
    "first",
    "like_term",
    "like_term_wildcard",
    "mask_doc",
    "new_id",
    "not_found",
    "now",
    "now_iso",
    "org_rls",
]
