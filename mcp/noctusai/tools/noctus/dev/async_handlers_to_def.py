"""`noctus.dev.async_handlers_to_def` — libcst codemod: an `async def` route handler that never
awaits becomes a plain `def`, so FastAPI runs it in the threadpool instead of on the event loop.

Why
    The handlers' synchronous supabase-py calls (direct, or through a service object) park the single
    uvicorn event loop for the whole network round-trip; concurrent requests serialize (orbity,
    2026-10-21: 985 / 1,524 / 2,081 ms staircase). A handler that contains NO `await` gains nothing
    from being a coroutine, and loses the whole loop's responsiveness. Converting it is
    behaviour-preserving when the body is already purely synchronous.
    KB § PATTERNS/backend/request-path-latency.md

What it converts (ALL must hold) — a function decorated `@<router>.get|post|put|patch|delete|head|options|api_route`
    that is `async def` and whose own body (nested defs/lambdas excluded) has no:
      * `await`, `async for`, `async with`, async comprehension, `yield`;
      * reference to `asyncio` / `anyio` / `trio` (loop-bound code: `create_task`, `get_running_loop`…);
      * `global` / `nonlocal` statement (shared mutable state the loop used to serialize);
    and whose name is never `await`ed anywhere in the product's backend (a direct `await handler(...)`
    from a test or sibling module would break once it is sync). Anything else is REPORTED with the reason,
    never touched.

What it does NOT decide
    Whether the module-level state the handler's callees touch is thread-safe — that is a human review of
    the converted set (the report lists every file). A websocket route is never converted.

DRY-RUN by default; `apply=True` writes (libcst keeps formatting byte-for-byte except the removed `async `).
After applying, run `--lower-async-handler-sync-db-baseline` so the keeper ratchet follows.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import libcst as cst

from settings import PRODUCTS_DIR, REPO_ROOT

logger = logging.getLogger(__name__)

_ROUTE_VERBS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "api_route"})
_LOOP_BOUND_NAMES = frozenset({"asyncio", "anyio", "trio"})
_SKIP_PARTS = frozenset({"tests", "migrations", "node_modules", "__pycache__", "venv", ".venv"})


def _is_route_handler(fn: cst.FunctionDef) -> bool:
    for dec in fn.decorators:
        expr = dec.decorator
        if isinstance(expr, cst.Call):
            expr = expr.func
        if isinstance(expr, cst.Attribute) and expr.attr.value in _ROUTE_VERBS:
            return True
    return False


class _BodyScan(cst.CSTVisitor):
    """Finds loop-bound constructs in a function's OWN body (nested scopes are skipped)."""

    def __init__(self) -> None:
        self.reason: str | None = None

    def _flag(self, why: str) -> None:
        self.reason = self.reason or why

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:  # noqa: N802
        return False

    def visit_Lambda(self, node: cst.Lambda) -> bool:  # noqa: N802
        return False

    def visit_ClassDef(self, node: cst.ClassDef) -> bool:  # noqa: N802
        return False

    def visit_Await(self, node: cst.Await) -> None:  # noqa: N802
        self._flag("awaits")

    def visit_Yield(self, node: cst.Yield) -> None:  # noqa: N802
        self._flag("yields")

    def visit_For(self, node: cst.For) -> None:  # noqa: N802
        if node.asynchronous is not None:
            self._flag("async for")

    def visit_With(self, node: cst.With) -> None:  # noqa: N802
        if node.asynchronous is not None:
            self._flag("async with")

    def visit_CompFor(self, node: cst.CompFor) -> None:  # noqa: N802
        if node.asynchronous is not None:
            self._flag("async comprehension")

    def visit_Global(self, node: cst.Global) -> None:  # noqa: N802
        self._flag("global statement")

    def visit_Nonlocal(self, node: cst.Nonlocal) -> None:  # noqa: N802
        self._flag("nonlocal statement")

    def visit_Name(self, node: cst.Name) -> None:  # noqa: N802
        if node.value in _LOOP_BOUND_NAMES:
            self._flag(f"references {node.value}")


class _Convert(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    def __init__(self, awaited_names: set[str], rel: str) -> None:
        super().__init__()
        self._awaited = awaited_names
        self._rel = rel
        self.converted: list[dict[str, Any]] = []
        self.skipped: list[dict[str, Any]] = []

    def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef) -> cst.FunctionDef:  # noqa: N802
        if original_node.asynchronous is None or not _is_route_handler(original_node):
            return updated_node
        line = self.get_metadata(cst.metadata.PositionProvider, original_node).start.line
        name = original_node.name.value
        scan = _BodyScan()
        original_node.body.visit(scan)
        reason = scan.reason
        if reason is None and name in self._awaited:
            reason = "awaited elsewhere in the product backend"
        if reason is not None:
            self.skipped.append({"file": self._rel, "line": line, "name": name, "reason": reason})
            return updated_node
        self.converted.append({"file": self._rel, "line": line, "name": name})
        return updated_node.with_changes(asynchronous=None)


_AWAIT_CALL = re.compile(r"await\s+(?:[\w\.]+\.)?(\w+)\s*\(")


def _backend_files(backend: Path) -> list[Path]:
    return [
        p for p in sorted(backend.rglob("*.py"))
        if not (_SKIP_PARTS & set(p.relative_to(backend).parts[:-1]))
    ]


def _awaited_names(backend: Path) -> set[str]:
    """Every callee name that appears as `await name(` / `await x.name(` ANYWHERE in the backend, tests included."""
    names: set[str] = set()
    for p in sorted(backend.rglob("*.py")):
        if "node_modules" in p.parts or "__pycache__" in p.parts:
            continue
        try:
            names.update(_AWAIT_CALL.findall(p.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    return names


def async_handlers_to_def(product: str, *, apply: bool = False, repo_root: Path | None = None) -> dict[str, Any]:
    """Convert (or, dry-run, plan converting) the awaitless async route handlers of one product."""
    root = repo_root or REPO_ROOT
    backend = root / "products" / product / "backend"
    if not backend.is_dir():
        return {"status": "error", "ok": False, "error": f"no such product backend: products/{product}/backend"}
    awaited = _awaited_names(backend)
    converted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    changed_files: list[str] = []
    for path in _backend_files(backend):
        if path.name.startswith("test_") or path.name == "conftest.py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "async def" not in text:
            continue
        rel = path.relative_to(root).as_posix()
        try:
            wrapper = cst.metadata.MetadataWrapper(cst.parse_module(text))
        except cst.ParserSyntaxError as exc:
            skipped.append({"file": rel, "line": 0, "name": "<module>", "reason": f"unparseable: {exc}"})
            continue
        transformer = _Convert(awaited, rel)
        new_module = wrapper.visit(transformer)
        converted.extend(transformer.converted)
        skipped.extend(transformer.skipped)
        if transformer.converted:
            changed_files.append(rel)
            if apply:
                path.write_text(new_module.code, encoding="utf-8")
    return {
        "status": "applied" if apply and converted else ("planned" if converted else "nothing_to_convert"),
        "ok": True,
        "product": product,
        "dry_run": not apply,
        "converted_count": len(converted),
        "skipped_count": len(skipped),
        "files_changed": changed_files,
        "converted": converted,
        "skipped": skipped,
        "next_action": (
            "review the converted set for module-level shared state, run the product's backend tests, then "
            "`--lower-async-handler-sync-db-baseline`" if converted else "none"
        ),
    }


def register(server) -> None:
    """Register the `noctus.dev.async_handlers_to_def` MCP tool."""

    @server.tool(
        name="noctus.dev.async_handlers_to_def",
        description=(
            "libcst codemod: convert a product's `async def` route handlers that never await (no await / "
            "async for|with / yield / asyncio|anyio use / global state, and never `await`ed elsewhere) into "
            "plain `def`, so FastAPI threadpools them instead of blocking the event loop on sync supabase "
            "calls. DRY-RUN by default (returns converted + skipped-with-reason); apply=True writes. "
            "Follow with the keeper's --lower-async-handler-sync-db-baseline. "
            "KB § PATTERNS/backend/request-path-latency.md."
        ),
    )
    def _async_handlers_to_def(product: str, apply: bool = False) -> dict[str, Any]:
        return async_handlers_to_def(product, apply=apply)
