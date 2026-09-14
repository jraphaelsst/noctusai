"""``TurnContext`` — G1b's own copy of the contract §E.9 dataclass
(``projects/julia-agents-academia-CONTRACT.md``).

The canonical definition lives at ``app/runtime/types.py`` (G2's slice,
which does not exist on this branch's base — see
``KB § PATTERNS/backend/seed-fake-real-adapter.md`` for why a consumer
never guesses a not-yet-shipped seam). G1b needs to CONSTRUCT a
``TurnContext`` to pass into ``AgentRuntime.run_turn(spec, ctx, prompt,
broker)`` — duck-typed, field-for-field identical to the contract's
definition, so it satisfies both the E.9 test stand-in AND (once merged)
the real ``app.runtime`` implementation without an import-time dependency
on a package this slice must not touch.

**Coordination note for the tech-lead / G2**: this dataclass MUST stay
field-identical to ``app/runtime/types.py::TurnContext`` once that lands.
Either G2 re-exports this module's ``TurnContext`` from
``app.runtime.types``, or the two are kept in sync by hand — flagged as a
contract coordination point in this slice's delivery note, not a silent
assumption.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class TurnContext:
    org_id: UUID
    conversation_id: UUID
    requested_by: UUID
    instance_id: str
    sdk_session_id: str | None


__all__ = ["TurnContext"]
