"""Product-agnostic named-permission grants — the `photo_curator` seam.

**What ships (this slice):**

- `PermissionGrantRepository` Protocol + `FakePermissionGrantRepository`
  (in-memory, dev/tests) + `RealSupabasePermissionGrantRepository`
  (shape-only — consumer ships the `public.user_permission_grants`
  table + `has_permission()` RPC migration).
- `make_permission_grant_repository(*, use_fake=False, ...)` factory
  mirroring the canonical Protocol+Fake+Real+factory pattern per
  `KB § PATTERNS/backend/seed-fake-real-adapter.md`.

**What does NOT ship here (a later slice):**

- The Core migration creating `public.user_permission_grants` +
  `has_permission()` — applying a migration needs owner consent.
- Any grant-issuance UI/router — WHO may grant/revoke is the consumer's
  route-level decision; the repository's `list_grants` / `add_grant` /
  `remove_grant` only record it.

**Product-agnostic by construction.** This module never mentions a
product, a feature, or a resource shape — `permission` is an opaque
string the caller defines. See `noctusai_lib.api.auth.platform.
require_permission` for the FastAPI dependency built on top of this
repository.
"""

from noctusai_lib.domain.permissions.repo import (
    FakePermissionGrantRepository,
    PermissionGrant,
    PermissionGrantRepository,
    RealSupabasePermissionGrantRepository,
    make_permission_grant_repository,
)

__all__ = [
    "FakePermissionGrantRepository",
    "PermissionGrant",
    "PermissionGrantRepository",
    "RealSupabasePermissionGrantRepository",
    "make_permission_grant_repository",
]
