"""The module-enablement migration emits no UNIQUE/CHECK/trigger guard (the primary key is its only constraint),
so there is nothing to probe; declared explicitly so the organ-completeness gate reads it as a decision."""
from __future__ import annotations

from noctusai_lib.domain._organ_common.guards import OrganGuardProbe

__all__ = ["module_enablement_guard_probes"]


def module_enablement_guard_probes(schema: str) -> tuple[OrganGuardProbe, ...]:
    return ()
