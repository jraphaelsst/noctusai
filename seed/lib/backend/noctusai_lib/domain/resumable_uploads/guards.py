"""The resumable-uploads migration emits no UNIQUE index or trigger guard the completeness gate detects (its
inline CHECKs bound sizes/status and its indexes are non-unique lookups), so there is nothing to probe; declared
explicitly so the organ-completeness gate reads it as a decision."""
from __future__ import annotations

from noctusai_lib.domain._organ_common.guards import OrganGuardProbe

__all__ = ["resumable_uploads_guard_probes"]


def resumable_uploads_guard_probes(schema: str) -> tuple[OrganGuardProbe, ...]:
    return ()
