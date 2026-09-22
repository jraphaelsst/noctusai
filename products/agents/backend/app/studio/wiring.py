"""Production bindings of the Agent Studio seams (contract §J2; slice BE-RT).

The wave-1 routers declare three FAIL-CLOSED dependencies (503 until bound):
``get_eval_gate_dep`` / ``get_knowledge_catalog_dep`` (BE-DEF,
``studio_agents_router``) and ``get_eval_scheduler_dep`` (BE-KE,
``studio_evals_router``). :func:`install_studio_seams` binds them on the
product app through ``app.dependency_overrides`` — the seam those modules
document for exactly this — to:

* the gate → BE-KE's ``SupabaseEvalGate`` (``FakeEvalGate`` when no Supabase
  service-role key is configured, like every other Fake/Real factory here);
* the catalog → :class:`~app.studio.catalog.StoreKnowledgeCatalog` over the
  SAME knowledge-store dependency the knowledge routes use;
* the scheduler → a closure that starts :class:`~app.studio.evals.EvalRunner`
  for the caller's org, built from the same dependency instances the route
  resolved, with its task strongly referenced on ``app.state``.

Every binding is itself a dependency graph over the product's other seams, so
a test that overrides a store/runtime/judge dependency reaches the bound
implementation too.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import Depends, Request

from app.config import settings
from app.dependencies import (
    get_agent_runtime_dep,
    get_approval_broker_dep,
    require_admin,
)
from app.routers.studio_agents_router import (
    get_eval_gate_dep,
    get_knowledge_catalog_dep,
    get_studio_definition_store_dep,
)
from app.routers.studio_evals_router import get_eval_scheduler_dep, get_eval_store_dep
from app.routers.studio_knowledge_router import get_studio_knowledge_store_dep
from app.studio.catalog import StoreKnowledgeCatalog
from noctusai_lib.api.auth.session import AuthContext

__all__ = [
    "get_eval_run_writer_dep",
    "get_eval_judge_dep",
    "studio_eval_gate",
    "studio_knowledge_catalog",
    "studio_eval_scheduler",
    "studio_seam_bindings",
    "install_studio_seams",
    "register_anthropic_credential_override",
]


def get_eval_run_writer_dep():
    """Seam over the eval-run writer (``app.stores.studio_eval_runs``)."""
    from app.stores.studio_eval_runs import get_eval_run_writer

    return get_eval_run_writer(settings)


def get_eval_judge_dep():
    """Seam over the eval judge — tests bind a deterministic fake."""
    from app.studio.evals import LlmJudge

    return LlmJudge()


def studio_eval_gate():
    from app.stores.studio_evals import get_eval_gate
    from app.studio.models import FakeEvalGate

    gate = get_eval_gate(settings)
    return gate if gate is not None else FakeEvalGate()


def studio_knowledge_catalog(knowledge=Depends(get_studio_knowledge_store_dep)) -> StoreKnowledgeCatalog:
    return StoreKnowledgeCatalog(knowledge)


def studio_eval_scheduler(
    request: Request,
    ctx: AuthContext = Depends(require_admin),
    evals=Depends(get_eval_store_dep),
    runs=Depends(get_eval_run_writer_dep),
    definitions=Depends(get_studio_definition_store_dep),
    catalog=Depends(get_knowledge_catalog_dep),
    runtime=Depends(get_agent_runtime_dep),
    broker=Depends(get_approval_broker_dep),
    judge=Depends(get_eval_judge_dep),
):
    """``scheduler(run_id)`` for ``POST .../evals/runs`` (§J2.2): starts the
    runner for the CALLER's org in the background. The run row was created
    by that same request, in that org, so the org scope is never taken from
    anything but the authenticated context."""
    from app.routers.conversations_router import INSTANCE_ID, _track_background_task
    from app.studio.evals import EvalRunner

    runner = EvalRunner(
        evals=evals,
        runs=runs,
        definitions=definitions,
        catalog=catalog,
        runtime=runtime,
        broker=broker,
        judge=judge,
        instance_id=INSTANCE_ID,
        turn_timeout_seconds=float(settings.turn_timeout_seconds),
    )
    app_state = request.app.state

    def _schedule(run_id: UUID) -> None:
        task = runner.schedule(ctx.org_id, run_id)
        _track_background_task(app_state, task)

    return _schedule


def studio_seam_bindings() -> dict[Any, Any]:
    return {
        get_eval_gate_dep: studio_eval_gate,
        get_knowledge_catalog_dep: studio_knowledge_catalog,
        get_eval_scheduler_dep: studio_eval_scheduler,
    }


def register_anthropic_credential_override() -> None:
    """The eval judge calls ``noctusai_lib``'s ``chat_completion``, whose key
    resolves through the seed credential chain (``org_settings`` →
    ``platform_settings`` → env). This product's Anthropic key is DB-first on
    its own Credenciais store — without this tier-0 override the judge would
    read a stale env value (or none) while the runtime uses the rotated one:
    the split ``register_credential_override`` exists to close. Only
    ``anthropic_api_key`` is answered; everything else falls through."""
    from app.credentials.resolver import get_credential_resolver
    from noctusai_lib.config.credentials import register_credential_override

    def _agents_credentials(key: str, org_id: Any) -> str | None:
        if key != "anthropic_api_key":
            return None
        return get_credential_resolver(settings).anthropic_api_key()

    register_credential_override(_agents_credentials)


def install_studio_seams(app: Any) -> None:
    app.dependency_overrides.update(studio_seam_bindings())
