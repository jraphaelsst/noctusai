"""Editorial workflow organ — draft → editorial review → security/source review →
published → archived, with per-transition grants, separation of duties (in code AND
in the DB), immutable versions and an append-only event log.

- ``workflow``       — fixed state machine + pure ``decide_transition``.
- ``store``          — value objects, ``EditorialStore`` Protocol, ``FakeEditorialStore``,
                       ``make_editorial_store`` factory.
- ``store_supabase`` — ``SupabaseEditorialStore`` (Real; imported lazily by the factory).
- DDL               — ``noctusai_lib.domain.sql_templates.editorial_tables(schema)``.

Not wired to any product yet (router factory + FE organs + first consumer are later
slices). See ``projects/seed-editorial-workflow/PROJECT.md``.
"""
from noctusai_lib.domain.editorial.store import (
    EditorialConflict,
    EditorialDenied,
    EditorialError,
    EditorialEvent,
    EditorialItem,
    EditorialNotFound,
    EditorialStore,
    EditorialVersion,
    FakeEditorialStore,
    TransitionResult,
    content_sha_of,
    make_editorial_store,
    round_approvals,
)
from noctusai_lib.domain.editorial.router import EditorialContext, diff_content, editorial_router
from noctusai_lib.domain.editorial.workflow import (
    DEFAULT_WORKFLOW,
    Action,
    Code,
    EditorialWorkflow,
    Grant,
    State,
    Transition,
    TransitionDecision,
    decide_transition,
)

__all__ = [
    "EditorialContext", "diff_content", "editorial_router",
    "Action", "Code", "DEFAULT_WORKFLOW", "EditorialConflict", "EditorialDenied", "EditorialError",
    "EditorialEvent", "EditorialItem", "EditorialNotFound", "EditorialStore", "EditorialVersion",
    "EditorialWorkflow", "FakeEditorialStore", "Grant", "State", "Transition", "TransitionDecision",
    "TransitionResult", "content_sha_of", "decide_transition", "make_editorial_store", "round_approvals",
]
