"""Media-production engine -- job graphs of render steps as a seed organ.

A graph = ordered steps with ``depende_de``, executed as seed ``domain.jobs``
jobs (lease, heartbeat, retry). The product implements four ports
(``LedgerPort`` = measured ledger + graph state, ``ProgressPort``,
``QuotaPort``, ``MoverPort``) and registers step handlers; vendor adapters
and product wiring live elsewhere. No product import here.

    runner = MediaGraphRunner(jobs=repo, ledger=..., progress=BusProgress(bus),
                              quota=..., mover=...)
    register_step("tts", handle_tts)
    worker = Worker(repo, worker_id="criacao-1", handlers=runner.handlers)
    await runner.enqueue_graph(GraphSpec(org, post, (StepSpec(...), ...)))
"""

from noctusai_lib.domain.media_production.costs import (
    CATEGORY_VENDOR_CREDITS,
    llm_leg_usd,
    vendor_cost_row,
    vendor_credit_usd,
)
from noctusai_lib.domain.media_production.fakes import (
    FakeLedger,
    FakeMover,
    FakeProgress,
    FakeQuota,
)
from noctusai_lib.domain.media_production.ports import (
    BusProgress,
    LedgerPort,
    MoverPort,
    ProgressPort,
    QuotaPort,
)
from noctusai_lib.domain.media_production.registry import (
    StepRegistry,
    default_registry,
    register_step,
)
from noctusai_lib.domain.media_production.runner import JOB_TYPE, MediaGraphRunner
from noctusai_lib.domain.media_production.types import (
    CancelToken,
    GraphSpec,
    PassoRow,
    QuotaExceeded,
    StepContext,
    StepError,
    StepResult,
    StepSpec,
)

__all__ = [
    "BusProgress", "CATEGORY_VENDOR_CREDITS", "CancelToken", "FakeLedger", "FakeMover",
    "FakeProgress", "FakeQuota", "GraphSpec", "JOB_TYPE", "LedgerPort", "MediaGraphRunner",
    "MoverPort", "PassoRow", "ProgressPort", "QuotaExceeded", "QuotaPort", "StepContext",
    "StepError", "StepRegistry", "StepResult", "StepSpec", "default_registry",
    "llm_leg_usd", "register_step", "vendor_cost_row", "vendor_credit_usd",
]
