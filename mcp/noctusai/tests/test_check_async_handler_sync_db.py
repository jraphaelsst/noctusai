"""`check_async_handler_sync_db` — an `async def` route handler must not call the sync supabase client
directly (it parks the event loop for the whole round-trip). Per-file RATCHET baseline; only NEW ones
block, a lowered count must lower the baseline. Plus the libcst codemod that fixes the awaitless ones.

→ KB § PATTERNS/backend/request-path-latency.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.async_handlers_to_def import async_handlers_to_def  # noqa: E402
from tools.noctus.dev.compliance import (  # noqa: E402
    REPO_ROOT,
    async_handler_sync_db_counts,
    async_handler_sync_db_handlers,
    check_async_handler_sync_db,
    lower_async_handler_sync_db_baseline,
)

ROUTER = "products/demo/backend/app/routers/things.py"
BASELINE = "mcp/noctusai/tests/async_handler_sync_db_baseline.json"

BLOCKING = '''
from fastapi import APIRouter
router = APIRouter()

@router.get("/api/things")
async def list_things(db):
    return db.table("things").select("*").execute().data
'''

THREADED = '''
import anyio.to_thread
from fastapi import APIRouter
router = APIRouter()

@router.get("/api/things")
async def list_things(db):
    return await anyio.to_thread.run_sync(lambda: db.table("things").select("*").execute().data)
'''

PLAIN_DEF = '''
from fastapi import APIRouter
router = APIRouter()

@router.get("/api/things")
def list_things(db):
    return db.table("things").select("*").execute().data
'''

AUTH_CALL = '''
@router.post("/api/x")
async def x(client):
    return client.auth.get_user("t")
'''

NOT_A_HANDLER = '''
async def helper(db):
    return db.table("t").select("*").execute()
'''

ESCAPED = '''
@router.get("/api/things")
async def list_things(db):  # noc-allow: sync-in-async — streams a tiny constant row
    return db.table("things").select("*").execute().data
'''


def _tree(root: Path, files: dict[str, str], baseline: dict[str, int] | None = None) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    b = root / BASELINE
    b.parent.mkdir(parents=True, exist_ok=True)
    b.write_text(json.dumps({"arquivos": baseline or {}}), encoding="utf-8")
    return root


class TestCheckAsyncHandlerSyncDb:
    def test_async_handler_with_direct_execute_is_flagged(self):
        assert async_handler_sync_db_handlers(BLOCKING) == [(6, "list_things")]

    def test_to_thread_wrapped_call_is_not_flagged(self):
        assert async_handler_sync_db_handlers(THREADED) == []

    def test_plain_def_is_not_flagged(self):
        assert async_handler_sync_db_handlers(PLAIN_DEF) == []

    def test_auth_call_is_flagged(self):
        assert [n for _l, n in async_handler_sync_db_handlers(AUTH_CALL)] == ["x"]

    def test_non_route_async_function_is_not_a_handler(self):
        assert async_handler_sync_db_handlers(NOT_A_HANDLER) == []

    def test_escape_hatch_on_the_def_line(self):
        assert async_handler_sync_db_handlers(ESCAPED) == []

    def test_awaited_call_is_an_async_client_not_flagged(self):
        src = 'from fastapi import APIRouter\nrouter=APIRouter()\n@router.get("/x")\nasync def h(db):\n    return await db.table("t").select("*").execute()\n'
        assert async_handler_sync_db_handlers(src) == []


class TestRatchet:
    def test_new_blocking_handler_is_flagged(self, tmp_path):
        _tree(tmp_path, {ROUTER: BLOCKING})
        issues = check_async_handler_sync_db(tmp_path)
        assert len(issues) == 1 and issues[0]["severity"] == "high" and issues[0]["product"] == "demo"
        assert "plain `def`" in issues[0]["issue"]

    def test_baselined_handler_passes(self, tmp_path):
        _tree(tmp_path, {ROUTER: BLOCKING}, {ROUTER: 1})
        assert check_async_handler_sync_db(tmp_path) == []

    def test_second_handler_above_baseline_is_flagged(self, tmp_path):
        _tree(tmp_path, {ROUTER: BLOCKING + BLOCKING.replace("list_things", "list_more")}, {ROUTER: 1})
        assert len(check_async_handler_sync_db(tmp_path)) == 1

    def test_lowered_count_must_lower_the_baseline(self, tmp_path):
        _tree(tmp_path, {ROUTER: PLAIN_DEF}, {ROUTER: 1})
        issues = check_async_handler_sync_db(tmp_path)
        assert len(issues) == 1 and "lower" in issues[0]["issue"]

    def test_lower_helper_never_raises_a_count(self, tmp_path):
        _tree(tmp_path, {ROUTER: BLOCKING + BLOCKING.replace("list_things", "list_more")}, {ROUTER: 1})
        assert lower_async_handler_sync_db_baseline(tmp_path) == {ROUTER: 1}
        _tree(tmp_path, {ROUTER: PLAIN_DEF}, {ROUTER: 1})
        assert lower_async_handler_sync_db_baseline(tmp_path) == {}
        assert check_async_handler_sync_db(tmp_path) == []

    def test_test_files_are_not_scanned(self, tmp_path):
        _tree(tmp_path, {"products/demo/backend/tests/test_x.py": BLOCKING})
        assert check_async_handler_sync_db(tmp_path) == []


class TestTheRealRepo:
    def test_baseline_matches_the_tree(self):
        """The committed baseline equals the live counts (the ratchet is tight, neither stale nor exceeded)."""
        baseline = json.loads((REPO_ROOT / BASELINE).read_text(encoding="utf-8"))["arquivos"]
        assert baseline == async_handler_sync_db_counts(REPO_ROOT)


CODEMOD_MIXED = '''
from fastapi import APIRouter
import asyncio
router = APIRouter()

@router.get("/a")
async def plain(db):
    return db.table("t").select("*").execute().data

@router.get("/b")
async def awaits(db, request):
    return await request.json()

@router.get("/c")
async def loop_bound(db):
    asyncio.get_running_loop()
    return 1

@router.get("/d")
async def called_in_test(db):
    return 1

@router.websocket("/ws")
async def sock(ws):
    return None

@router.get("/e")
async def with_decorators_and_doc(db):
    """doc"""
    return [x for x in db.rows()]
'''


class TestCodemod:
    def _product(self, root: Path) -> Path:
        _tree(root, {
            "products/demo/backend/app/routers/r.py": CODEMOD_MIXED,
            "products/demo/backend/tests/test_r.py": "async def test_x():\n    from app.routers.r import called_in_test\n    assert await called_in_test(1) == 1\n",
        })
        return root

    def test_dry_run_plans_without_writing(self, tmp_path):
        self._product(tmp_path)
        before = (tmp_path / "products/demo/backend/app/routers/r.py").read_text()
        r = async_handlers_to_def("demo", repo_root=tmp_path)
        assert r["status"] == "planned" and r["dry_run"] is True
        assert {c["name"] for c in r["converted"]} == {"plain", "with_decorators_and_doc"}
        assert (tmp_path / "products/demo/backend/app/routers/r.py").read_text() == before

    def test_skips_say_why_and_websocket_is_never_touched(self, tmp_path):
        self._product(tmp_path)
        r = async_handlers_to_def("demo", repo_root=tmp_path)
        reasons = {s["name"]: s["reason"] for s in r["skipped"]}
        assert reasons["awaits"] == "awaits"
        assert reasons["loop_bound"] == "references asyncio"
        assert "awaited elsewhere" in reasons["called_in_test"]
        assert "sock" not in reasons and "sock" not in {c["name"] for c in r["converted"]}

    def test_apply_rewrites_only_the_async_keyword(self, tmp_path):
        self._product(tmp_path)
        path = tmp_path / "products/demo/backend/app/routers/r.py"
        before = path.read_text()
        r = async_handlers_to_def("demo", apply=True, repo_root=tmp_path)
        after = path.read_text()
        assert r["status"] == "applied"
        assert "def plain(db):" in after and "async def plain" not in after
        assert "async def awaits" in after and "async def sock" in after
        # nothing else moved
        assert after.replace("async def plain", "def plain").replace("async def with_decorators_and_doc", "def with_decorators_and_doc") == before.replace("async def plain", "def plain").replace("async def with_decorators_and_doc", "def with_decorators_and_doc")
        compile(after, str(path), "exec")

    def test_unknown_product_is_an_honest_error(self, tmp_path):
        assert async_handlers_to_def("nope", repo_root=tmp_path)["ok"] is False


# -- indirect + dependency detection (organ_auth staircase, 2026-10-22) -------------------------------

ORGAN_PATH = "seed/framework/backend/noctusai_seed/organ_auth.py"

INDIRECT_DEP = '''
from fastapi import Depends

def make(auth_dependency, get_core_client):
    def _is_admin(request, user):
        return resolve_org_membership(get_core_client(), user.id)

    async def auth(request, base=Depends(auth_dependency)):
        return _is_admin(request, base[0])

    return auth
'''

INDIRECT_DEP_OFFLOADED = INDIRECT_DEP.replace("return _is_admin(request, base[0])", "return await run_blocking(_is_admin, request, base[0])")

TRANSITIVE_DEP = '''
from fastapi import Depends

def _inner(db):
    return db.table("t").select("*").execute().data

def _outer(db):
    return _inner(db)

async def dep(db, x=Depends(other)):
    return _outer(db)
'''


def test_async_dependency_calling_a_sync_helper_that_reaches_the_client_is_counted():
    assert [n for _l, n in async_handler_sync_db_handlers(INDIRECT_DEP, ORGAN_PATH)] == ["auth"]


def test_offloading_the_helper_to_a_worker_thread_is_clean():
    assert async_handler_sync_db_handlers(INDIRECT_DEP_OFFLOADED, ORGAN_PATH) == []


def test_transitive_same_module_helpers_and_depends_targets_are_followed():
    # not a seed auth/organ file: it is a dependency because `Depends(...)` is used on it? no -- because it is
    # referenced as a Depends target in another declaration
    text = TRANSITIVE_DEP + "\nfrom fastapi import APIRouter\nr = APIRouter()\nr.add_api_route('/x', lambda d=Depends(dep): 1)\n"
    assert [n for _l, n in async_handler_sync_db_handlers(text, "products/demo/backend/app/deps.py")] == ["dep"]


def test_plain_async_helper_outside_dependency_scope_is_not_counted():
    text = "def _read(db):\n    return db.table('t').select('*').execute().data\n\nasync def util(db):\n    return _read(db)\n"
    assert async_handler_sync_db_handlers(text, "products/demo/backend/app/services/x.py") == []


def test_indirect_hit_flows_into_the_ratchet(tmp_path):
    rel = ORGAN_PATH
    f = tmp_path / rel
    f.parent.mkdir(parents=True)
    f.write_text(INDIRECT_DEP)
    base = tmp_path / BASELINE
    base.parent.mkdir(parents=True)
    base.write_text(json.dumps({"arquivos": {}}))
    assert async_handler_sync_db_counts(tmp_path) == {rel: 1}
    assert any("auth" in i["issue"] for i in check_async_handler_sync_db(tmp_path))
    f.write_text(INDIRECT_DEP_OFFLOADED)
    assert check_async_handler_sync_db(tmp_path) == []


def test_real_organ_auth_and_seed_auth_modules_are_clean():
    for rel in (ORGAN_PATH, "seed/lib/backend/noctusai_lib/api/auth/session/scopes.py",
                "seed/lib/backend/noctusai_lib/api/auth/platform.py"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert async_handler_sync_db_handlers(text, rel) == [], rel
