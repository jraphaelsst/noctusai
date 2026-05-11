"""
Pytest configuration and shared fixtures for Imobi Scheduling backend tests.

The seed product uses the framework (noctusai_seed), so patches target
the framework's database module rather than product-level modules.

Phase 6 (conversation framework) adds an `OpenAI` patch + a
`ConversationWorker` poll-loop short-circuit so the FastAPI lifespan
can wire the conversation module without hitting the real OpenAI SDK
and without spawning a long-running worker thread inside TestClient.

Phase 9 (cancel/reschedule audit columns) adds a session-scoped schema-cache
override so the MockSupabaseClient sees the worktree's migrations rather
than the canonical noc migrations (the seed lib is installed in the shared
venv, so its `_find_repo_root` walks up to canonical noc by default — see
`projects/imobi-scheduling-bot-creation/findings.md` §1).
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.testing import (  # noqa: F401 — re-exported for test imports
    AuthClient,
    MockFilterBuilder,
    MockQueryBuilder,
    MockRequestBuilder,
    MockSelectBuilder,
    MockSupabaseClient,
    MockSupabaseResponse,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
)
from noctusai_lib.testing._schema_cache import reset_cache, set_cache_for_tests
from noctusai_lib.testing.migration_parser import parse_files


def _prime_schema_cache_from_worktree() -> None:
    """Rebuild the schema cache against THIS worktree's migrations.

    Walks up from this conftest file to the worktree root (the dir with
    `CLAUDE.md` + `products/`), then discovers every `products/*/backend/
    migrations/*.sql` under it. Bypasses `_find_repo_root` because the seed
    lib is installed in a shared venv whose `__file__` resolves to canonical
    noc, not the worktree.
    """
    here = Path(__file__).resolve()
    worktree_root: Path | None = None
    for parent in here.parents:
        if (parent / "CLAUDE.md").is_file() and (parent / "products").is_dir():
            worktree_root = parent
            break
    if worktree_root is None:
        # Defensive: leave default cache untouched if walk fails.
        return
    files: list[Path] = []
    for product in sorted((worktree_root / "products").iterdir()):
        md = product / "backend" / "migrations"
        if md.is_dir():
            files.extend(sorted(md.glob("*.sql")))
    if not files:
        return
    parsed = parse_files(files)
    # parse_files returns {qualified_table: TableSchema} — convert to
    # {qualified_table: set[columns]} shape that set_cache_for_tests expects.
    cache_payload: dict[str, set[str]] = {}
    for qualified, schema in parsed.items():
        cols = getattr(schema, "columns", schema)
        cache_payload[qualified] = set(cols)
    reset_cache()
    set_cache_for_tests(cache_payload)


# Prime the schema cache at import time — pytest imports conftests before
# collecting tests, so this fires before any `MockSupabaseClient(...)` runs.
_prime_schema_cache_from_worktree()


def pytest_configure(config):
    config.addinivalue_line("markers", "realdb: tests that require a live Supabase instance")


class _StubOpenAIClient:
    """No-op stand-in for `openai.OpenAI` used by the conversation
    module's `LLMDispatcher`. Tests that exercise the dispatcher patch
    `app.services.conversation.OpenAI` themselves; this stub keeps the
    *lifespan startup* path from raising when `OPENAI_API_KEY` is unset.

    Per the no-monkey-patching-of-our-own-code rule, the patch point is
    the **external SDK** (`OpenAI`), not our own dispatcher. The stub
    surface (`chat.completions.create`) is the OpenAI SDK's, not ours.
    """

    def __init__(self, *_args, **_kwargs):
        self.chat = MagicMock()
        self.chat.completions = MagicMock()
        self.chat.completions.create = MagicMock()


def _inert_schedule_coro(coro, **_kwargs):
    """Replacement for `schedule_coro` that closes the coroutine + returns
    a Future-like stand-in. Closing the coro suppresses the
    "coroutine '_run_worker_in_thread' was never awaited" RuntimeWarning
    that fires when the test bypasses the real scheduler."""
    try:
        coro.close()
    except (AttributeError, RuntimeError):
        # AttributeError → caller passed something other than a coro.
        # RuntimeError → already-closed; benign.
        pass
    fake_task = MagicMock(name="inert_task")
    fake_task.done.return_value = False
    fake_task.cancel = MagicMock()
    return fake_task


@pytest.fixture(autouse=True)
def _patch_conversation_module():
    """Auto-patch the conversation module so FastAPI lifespan startup
    succeeds without an OpenAI key + without a real polling worker.

    - Replaces `app.services.conversation.OpenAI` with a stub class.
    - Patches `noctusai_lib.primitives.tasks.schedule_coro` (re-exported
      into the conversation module) with `_inert_schedule_coro`, which
      closes the passed coroutine so Python doesn't emit a
      "coroutine was never awaited" RuntimeWarning.

    Tests that exercise the conversation module directly (e.g.
    `tests/services/test_conversation.py`) re-patch within their own
    fixtures with stricter mocks.
    """
    with patch("app.services.conversation.OpenAI", _StubOpenAIClient), \
         patch("app.services.conversation.schedule_coro", side_effect=_inert_schedule_coro):
        yield


@pytest.fixture
def client():
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(
        MockUser(org_id="test-org-123")
    ))

    with patch("app.database._db.get_client", return_value=mock_sb), \
         patch("app.database._db.get_core_client", return_value=mock_sb), \
         patch("app.database._db.get_admin_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb):

        from app.main import app
        # Per-fixture re-bind of the seed's consent module to THIS test's
        # mock_sb. Idempotent — safe even if no consent features registered.
        # See KB § PATTERNS/testing.md § Consent-guard product conftest pattern.
        bind_consent_module_to_mock(mock_sb)

        tc = TestClient(app)
        yield AuthClient(tc, mock_sb)
