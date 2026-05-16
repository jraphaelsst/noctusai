"""social-wiring ``scheduling`` module — absorbed ``imobi-scheduling``
real-estate scheduling domain (project ``social-wiring-absorption``
Wave 2.3).

Module-registration seam (W2.1 contract): ``register()`` returns a
``ModuleRegistration`` (its routers + the seed standard-router names it
needs). ``app/main.py`` iterates ``MODULES`` and never special-cases a
module — adding this module only grows that list.

What this module contributes:

  - ``app/api/scheduling/*`` CRUD-lite + engine-backed ``propose``
    (``router.router``).
  - The scheduling tool pipeline (``tool_registry.build_tool_handler``)
    + ``engine.SchedulingService`` for the chat layer to compose into
    the seed ``LLMDispatcher`` (not auto-mounted — the W2.1 conversation
    layer owns the worker; this module owns the domain + tools).
  - LID-aware authorization, anomaly/retry/sanitization/tool-audit/
    metrics/per-conversation rate-limit support — all seed-consuming;
    NO seed primitive is vendored (engine math = seed
    ``noctusai_lib.domain.scheduling``; retry policy = seed
    ``noctusai_lib.domain.jobs.retry_policy``; audit DTO = seed
    ``noctusai_lib.domain.ai.tool_audit``; tool types = seed
    ``noctusai_lib.domain.chatbot``).

Standard routers requested: ``health`` (the module adds no notification
or team surface of its own — those come from the W2.1 base module and
are de-duplicated by the assembly loop).
"""
from __future__ import annotations

from app.modules.scheduling.engine import SchedulingService, build_rules
from app.modules.scheduling.tool_registry import (
    TOOL_DESCRIPTORS,
    build_tool_handler,
)


def register():
    """Return this module's ``ModuleRegistration`` for the W2.1 seam.

    ``ModuleRegistration`` is imported lazily from ``app.main`` to avoid
    an import cycle (``app.main`` imports this ``register``).
    """
    from app.main import ModuleRegistration
    from app.modules.scheduling.router import router as scheduling_router

    return ModuleRegistration(
        routers=[scheduling_router],
        standard_routers=("health",),
    )


__all__ = [
    "TOOL_DESCRIPTORS",
    "SchedulingService",
    "build_rules",
    "build_tool_handler",
    "register",
]
