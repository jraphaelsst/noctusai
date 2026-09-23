"""`check_stand_in_conformance` — a stand-in must satisfy the same CONTRACT
as the thing it replaces.

WHY THIS EXISTS — three production failures in ONE day (2026-09-22), all the
same shape: a TEST DOUBLE more permissive than the real thing, so the suite
stayed green while production could not work.

  1. `imovel_dados` — a service handed PostgREST a `datetime.date`.
     `MockSupabaseClient` stored it happily; httpx's stdlib JSON encoder
     refuses it -> 500 on every save, since migration 099. Fixed by
     `noctusai_lib.testing.mocks._validate_json_serializable` — LEG B(iii)
     below pins that the mock's write path still calls it.
  2. `_SchemaPinnedAdminClient` (`noctusai_seed.database`) — a `__slots__`
     wrapper with no `__weakref__`. Its own unit tests passed (constructed
     directly); products cache schema-scoped clients in a
     `weakref.WeakKeyDictionary`, so the moment it ran live every route
     taking that dependency raised `TypeError: cannot create weak
     reference` BEFORE any route code — CI green, predeploy_check clean.
     LEG A + LEG B(i)/B(ii) below are what would have caught this: resolve
     the product's own FastAPI dependency graph against a REAL client
     object (not the mock) and actually CALL it.
  3. `atendimento_contrato_versoes` — a cross-column CHECK
     (`docx_storage_path`/`docx_tamanho_bytes` required only for
     `origem='gerado'`) that `CheckManifest`'s single-column shape cannot
     express. The table was EMPTY in production while the suite stayed
     green. LEG B(iv) below inventories migration-declared cross-column
     CHECK constraints against the mock's `ConditionalPresenceManifest`
     coverage — an unlisted one is a finding, not a silent pass.

Two legs, four checks, one entry point:

  LEG A   — dependency resolution against a REAL object (catches #2's
            resolution-time TypeError before any request happens).
  LEG B   — double-vs-real contract conformance:
    B(i)    any object a product may use as a `WeakKeyDictionary` key is
            weak-referenceable (folded into leg A's subprocess — the
            SAME resolved objects are probed with `weakref.ref`).
    B(ii)   an object production caches by identity keeps a stable
            identity across the calls production makes (folded into leg
            A's subprocess — re-resolve and compare `is`).
    B(iii)  write payloads the double accepts are payloads the real
            client could encode — STATIC: confirms
            `MockRequestBuilder.insert/update/upsert` still call the
            EXISTING `_validate_json_serializable` (extended, never
            re-implemented, per the brief this shipped against).
    B(iv)   a migration-declared cross-column CHECK the mock cannot
            express is either covered by a `ConditionalPresenceManifest`
            entry or NAMED in `_KNOWN_UNENFORCEABLE_CROSS_COLUMN_CHECKS`
            with a reason — an unlisted one is a finding.

NEVER a false green. A product whose dependency graph cannot be resolved
against a real client (missing venv, import failure, timeout) is reported
`status="inconclusive"` with the reason — never silently `ok`. Mirrors
`noctus.dev.gate_sweep`'s posture.

SCOPE. Leg A/B(i)/B(ii) run one short-lived subprocess PER ACTIVE product
(`_active_product_dirs` — `ativo=true` only, the same scope every other
per-product compliance walk uses), in parallel (bounded worker pool),
against the product's OWN backend + the seed's `noctusai_lib`/
`noctusai_seed` on `sys.path` — construction only, no supabase credentials
are read from `.env`; dummy values are injected so no real secret is ever
touched. No network call happens (`supabase.create_client` builds an httpx
client lazily; the FIRST real request would come from the ROUTE handler,
never from resolving the dependency itself).
"""
from __future__ import annotations

import ast
import json
import logging
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logger = logging.getLogger(__name__)

from settings import REPO_ROOT  # noqa: E402  (path constants)

try:  # pragma: no cover — defensive only; compliance.py always defines this.
    from tools.noctus.dev.compliance import _active_product_dirs
except ImportError:  # pragma: no cover
    def _active_product_dirs(products_dir: Path) -> list[Path]:
        if not products_dir.exists():
            return []
        return sorted(
            p for p in products_dir.iterdir()  # product-scope: active (fallback mirrors compliance._active_product_dirs's choke point)
            if p.is_dir() and not p.name.startswith(".")
        )


_SUBPROCESS_TIMEOUT_S = 30
_MAX_WORKERS = 4

#: Constraints a human has explicitly reviewed and confirmed the mock CANNOT
#: express (and said WHY / where it's pinned instead) — the honest escape
#: hatch the brief calls for. Key: "<product_slug>/<table>/<constraint_name>".
#: Empty by construction: every cross-column CHECK found today either has a
#: `ConditionalPresenceManifest` entry or is a genuine gap this gate should
#: flag. Add an entry here ONLY with a reviewed reason — never to silence a
#: finding nobody looked at.
_KNOWN_UNENFORCEABLE_CROSS_COLUMN_CHECKS: dict[str, str] = {}


# ---------------------------------------------------------------------------
# LEG A + B(i) + B(ii) — dependency resolution against a real object
# ---------------------------------------------------------------------------

_TESTS_EXCLUDE_PARTS = {"tests", "migrations", "__pycache__"}


def _iter_backend_py_files(backend_app: Path):
    for p in sorted(backend_app.rglob("*.py")):
        rel_parts = p.relative_to(backend_app).parts
        if any(
            part in _TESTS_EXCLUDE_PARTS or part.startswith("test_")
            for part in rel_parts
        ):
            continue
        yield p


def _collect_depends_target_names(backend_app: Path) -> set[str]:
    """AST-walk every non-test `.py` file under `backend_app` for
    `Depends(<expr>)` call arguments and collect the bare callable NAME
    each resolves to (`ast.Name.id` or `ast.Attribute.attr`). This is the
    "enumerate the FastAPI dependency callables its routers actually
    declare" step — real router/deps source, not a guess."""
    names: set[str] = set()
    for py_file in _iter_backend_py_files(backend_app):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            logger.debug("stand_in_conformance: cannot parse %s (%s)", py_file, exc)
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_depends = (
                (isinstance(func, ast.Name) and func.id == "Depends")
                or (isinstance(func, ast.Attribute) and func.attr == "Depends")
            )
            if not is_depends or not node.args:
                continue
            target = node.args[0]
            if isinstance(target, ast.Name):
                names.add(target.id)
            elif isinstance(target, ast.Attribute):
                names.add(target.attr)
    return names


def _discover_deps_modules(backend_dir: Path) -> list[str]:
    """Dotted module names for `app/dependencies.py` + every `app/**/deps.py`
    — the DI-seam files per `KB § PATTERNS/backend/di-test-seam.md` — as
    importable dotted paths relative to `backend_dir` (which sits on
    `sys.path` in the harness subprocess)."""
    app_dir = backend_dir / "app"
    if not app_dir.is_dir():
        return []
    candidates: list[Path] = []
    dependencies_py = app_dir / "dependencies.py"
    if dependencies_py.is_file():
        candidates.append(dependencies_py)
    candidates.extend(
        p for p in sorted(app_dir.rglob("deps.py"))
        if "tests" not in p.relative_to(app_dir).parts
    )
    modules = []
    for c in candidates:
        rel = c.relative_to(backend_dir).with_suffix("")
        modules.append(".".join(rel.parts))
    return modules


#: The subprocess harness. Runs in a FRESH interpreter per product (products
#: all define a top-level `app` package — importing two in one process would
#: silently reuse the first's `sys.modules["app"]`). Tokens are substituted
#: via `.replace()`, never `%`/`.format()` — the harness body is full of `{`
#: `}` `%` characters of its own.
_HARNESS_TEMPLATE = r'''
import inspect
import json
import sys
import weakref

sys.path[0:0] = __SYS_PATHS_JSON__

DEPENDS_TARGET_NAMES = set(__TARGET_NAMES_JSON__)
MODULE_NAMES = __MODULE_NAMES_JSON__

try:
    from fastapi.params import (
        Depends as _Depends,
        Header as _Header,
        Query as _Query,
        Path as _Path,
        Cookie as _Cookie,
        Body as _Body,
        Form as _Form,
        File as _File,
    )
except Exception as exc:
    print(json.dumps({"status": "inconclusive", "reason": "cannot import fastapi.params: " + repr(exc)}))
    sys.exit(0)

_REQUEST_PARAM_TYPES = (_Header, _Query, _Path, _Cookie, _Body, _Form, _File)

#: See the comment at the identity-check call site below for why this is a
#: narrow, documented allowlist rather than a broad heuristic.
_IDENTITY_CONTRACT_NAMES = {"get_admin_client", "get_scoped_admin_client"}


class _NeedsRequest(Exception):
    pass


#: A dependency that goes FURTHER than construction — makes an actual
#: network call (a live key-ring fetch, an outbound health probe) — is out
#: of THIS gate's contract ("construction only, never a request"; per the
#: brief). That failure mode is a live-infra concern, not a double-vs-real
#: conformance defect, and reporting it as an "error" would make the gate
#: network-dependent (a CI runner with no egress would light up red on
#: code that is not broken). Detected by TYPE (never by string-matching a
#: message, which drifts) — the socket/httpx exception hierarchy every
#: outbound call in this codebase eventually raises through.
def _is_network_error(exc):
    import socket
    try:
        import httpx
        network_types = (socket.gaierror, ConnectionError, httpx.TransportError)
    except ImportError:
        network_types = (socket.gaierror, ConnectionError)
    return isinstance(exc, network_types)


def _resolve(fn, cache):
    if fn in cache:
        return cache[fn]
    sig = inspect.signature(fn)
    kwargs = {}
    for name, param in sig.parameters.items():
        default = param.default
        if isinstance(default, _Depends):
            target = default.dependency
            if target is None:
                raise _NeedsRequest("Depends() with no explicit dependency")
            kwargs[name] = _resolve(target, cache)
        elif isinstance(default, _REQUEST_PARAM_TYPES):
            raise _NeedsRequest("needs live request data (" + type(default).__name__ + ")")
        elif default is inspect.Parameter.empty:
            raise _NeedsRequest("required parameter with no default")
        else:
            kwargs[name] = default
    result = fn(**kwargs)
    cache[fn] = result
    return result


imported_modules = []
import_errors = {}
for mod_name in MODULE_NAMES:
    try:
        mod = __import__(mod_name, fromlist=["__name__"])
        imported_modules.append(mod)
    except Exception as exc:
        import_errors[mod_name] = repr(exc)

if not imported_modules:
    print(json.dumps({
        "status": "inconclusive",
        "reason": "no DI-seam module could be imported: " + repr(import_errors),
    }))
    sys.exit(0)

candidates = {}
for mod in imported_modules:
    for name, obj in inspect.getmembers(mod, inspect.isfunction):
        if name.startswith("_"):
            continue
        if obj.__module__ != mod.__name__:
            continue
        if name not in DEPENDS_TARGET_NAMES:
            continue
        candidates[(mod.__name__, name)] = obj

results = []
for (mod_name, name), fn in candidates.items():
    try:
        obj = _resolve(fn, {})
    except _NeedsRequest as exc:
        results.append({"module": mod_name, "name": name, "status": "skipped", "reason": str(exc)})
        continue
    except Exception as exc:
        if _is_network_error(exc):
            results.append({
                "module": mod_name, "name": name, "status": "skipped",
                "reason": "requires a live network call (" + type(exc).__name__ + ") — out of scope for construction-only resolution",
            })
            continue
        results.append({
            "module": mod_name, "name": name, "status": "error", "leg": "A",
            "exc_type": type(exc).__name__, "exc_msg": str(exc),
        })
        continue

    try:
        weakref.ref(obj)
    except TypeError as exc:
        results.append({
            "module": mod_name, "name": name, "status": "error", "leg": "B(i)",
            "exc_type": "TypeError", "exc_msg": str(exc),
        })
        continue

    try:
        obj2 = _resolve(fn, {})
    except Exception as exc:
        if _is_network_error(exc):
            results.append({
                "module": mod_name, "name": name, "status": "skipped",
                "reason": "requires a live network call (" + type(exc).__name__ + ") — out of scope for construction-only resolution",
            })
            continue
        results.append({
            "module": mod_name, "name": name, "status": "error", "leg": "A",
            "exc_type": type(exc).__name__, "exc_msg": str(exc),
        })
        continue

    # Identity-stability only matters where the DI seam ITSELF documents a
    # caching contract — `DatabaseModule.get_admin_client()` / the product
    # `get_admin_client()`/`get_scoped_admin_client()` accessors are the
    # ONLY names in this fleet whose own docstrings promise "same object
    # every caller" (the exact `_SchemaPinnedAdminClient` shape this leg
    # exists for). Checking EVERY resolvable zero-arg dependency floods the
    # signal: most product DI seams are DELIBERATELY fresh-per-call
    # factories (a per-request adapter, a notification service) with no
    # caching contract at all — measured against the live fleet
    # (2026-09-23), scoping to all `noctusai_seed`/`noctusai_lib` return
    # types alone still produced 2 false positives
    # (`get_contrato_docx_adapter`, `get_credit_probe` — both explicitly
    # documented factory "Seam:"s). An honest, narrow allowlist beats a
    # broad heuristic that trains reviewers to ignore the leg.
    if name in _IDENTITY_CONTRACT_NAMES and obj2 is not obj:
        results.append({"module": mod_name, "name": name, "status": "identity_unstable", "leg": "B(ii)"})
    else:
        results.append({"module": mod_name, "name": name, "status": "ok"})

print(json.dumps({"status": "ok", "results": results, "import_errors": import_errors}))
'''


def _resolve_product_venv_python(root: Path) -> "Path | None":
    """The interpreter product-backend tests actually run under — NOT the
    MCP toolkit's own `.venv` (no `fastapi`/`supabase` there). Tries
    `<root>/venv/bin/python` first (the primary checkout shape); a
    worktree has no `venv/` of its own, so falls back to the PRIMARY
    checkout's venv via `git rev-parse --git-common-dir` (a worktree's
    common dir is `<primary>/.git`)."""
    candidate = root / "venv" / "bin" / "python"
    if candidate.is_file():
        return candidate
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=root, capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    primary_root = Path(out.stdout.strip()).parent
    candidate = primary_root / "venv" / "bin" / "python"
    return candidate if candidate.is_file() else None


def _leg_a_check_product(
    slug: str, product_dir: Path, root: Path, python_exe: Path,
) -> list[dict]:
    backend_dir = product_dir / "backend"
    app_dir = backend_dir / "app"
    if not app_dir.is_dir():
        return []  # no backend at all — out of scope, not a finding

    target_names = _collect_depends_target_names(app_dir)
    module_names = _discover_deps_modules(backend_dir)
    if not module_names:
        return []  # nothing DI-seam-shaped to resolve — legitimate scope

    seed_lib = root / "seed" / "lib" / "backend"
    seed_framework = root / "seed" / "framework" / "backend"
    sys_paths = [str(backend_dir), str(seed_lib), str(seed_framework)]

    harness_src = (
        _HARNESS_TEMPLATE
        .replace("__SYS_PATHS_JSON__", json.dumps(sys_paths))
        .replace("__MODULE_NAMES_JSON__", json.dumps(module_names))
        .replace("__TARGET_NAMES_JSON__", json.dumps(sorted(target_names)))
    )

    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", ""),
        "PYTHONPATH": ":".join(sys_paths),
        "PYTHONDONTWRITEBYTECODE": "1",
        # Dummy, obviously-fake credentials — construction-only, never a
        # request; no real secret from the repo's `.env` is ever read by
        # this subprocess (env vars win over pydantic-settings' `env_file`).
        # MUST be JWT-shaped (header.payload.signature) — supabase-py
        # validates the key's STRUCTURE synchronously at `create_client()`
        # (`SupabaseException: Invalid API key`, no network involved) even
        # though it never verifies the signature; a plain string trips
        # that check and reads as a leg-A finding that is actually a
        # harness artifact, not a real dependency-resolution failure.
        "SUPABASE_URL": "https://stand-in-conformance-gate.invalid",
        "SUPABASE_ANON_KEY": "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.stand-in-conformance-gate-dummy",
        "SUPABASE_SERVICE_ROLE_KEY": "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.stand-in-conformance-gate-dummy",
    }

    try:
        proc = subprocess.run(
            [str(python_exe), "-c", harness_src],
            capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_S,
            env=env, cwd=str(backend_dir), check=False,
        )
    except subprocess.TimeoutExpired:
        return [{
            "product": slug, "file": f"{slug}/backend/app",
            "issue": (
                f"stand-in-conformance leg A timed out resolving dependencies "
                f"against a real client (> {_SUBPROCESS_TIMEOUT_S}s) — "
                "INCONCLUSIVE, not ok."
            ),
            "severity": "warning", "leg": "A", "status": "inconclusive",
        }]

    out = (proc.stdout or "").strip()
    if not out:
        return [{
            "product": slug, "file": f"{slug}/backend/app",
            "issue": (
                f"stand-in-conformance leg A produced no output (exit "
                f"{proc.returncode}); stderr: {(proc.stderr or '').strip()[-800:]!r} "
                "— INCONCLUSIVE, not ok."
            ),
            "severity": "warning", "leg": "A", "status": "inconclusive",
        }]

    try:
        payload = json.loads(out.splitlines()[-1])
    except (ValueError, IndexError) as exc:
        return [{
            "product": slug, "file": f"{slug}/backend/app",
            "issue": (
                f"stand-in-conformance leg A harness produced unparseable "
                f"output ({exc}); raw tail: {out[-800:]!r} — INCONCLUSIVE, not ok."
            ),
            "severity": "warning", "leg": "A", "status": "inconclusive",
        }]

    if payload.get("status") == "inconclusive":
        return [{
            "product": slug, "file": f"{slug}/backend/app/dependencies.py",
            "issue": (
                "stand-in-conformance leg A could not resolve this product's "
                f"dependency graph against a real client: {payload.get('reason')} "
                "— INCONCLUSIVE, not ok."
            ),
            "severity": "warning", "leg": "A", "status": "inconclusive",
        }]

    issues: list[dict] = []
    for r in payload.get("results", []):
        loc = f"{slug}/backend/{r['module'].replace('.', '/')}.py::{r['name']}"
        if r.get("status") == "error" and r.get("leg") == "A":
            issues.append({
                "product": slug, "file": loc,
                "issue": (
                    f"Dependency `{r['name']}` raised {r['exc_type']}: "
                    f"{r['exc_msg']} when resolved against a REAL client "
                    "object (not the mock) — this is exactly the class of "
                    "failure that fires at dependency-resolution time in "
                    "production, before any route handler runs."
                ),
                "severity": "high", "leg": "A", "status": "finding",
            })
        elif r.get("status") == "error" and r.get("leg") == "B(i)":
            issues.append({
                "product": slug, "file": loc,
                "issue": (
                    f"`{r['name']}` returns an object that is NOT "
                    f"weak-referenceable ({r['exc_msg']}) — any product code "
                    "that keys a `weakref.WeakKeyDictionary` on this value "
                    "will raise `TypeError: cannot create weak reference` at "
                    "request time. A stand-in class must keep every "
                    "capability of what it replaces, weak-referenceability "
                    "included."
                ),
                "severity": "high", "leg": "B(i)", "status": "finding",
            })
        elif r.get("status") == "identity_unstable":
            issues.append({
                "product": slug, "file": loc,
                "issue": (
                    f"`{r['name']}` returned a DIFFERENT object identity on "
                    "a second call in the same process — if any product code "
                    "caches by identity (a `WeakKeyDictionary` keyed on this "
                    "value, or an `is`-comparison cache), a fresh object "
                    "every call makes that cache never hit."
                ),
                "severity": "warning", "leg": "B(ii)", "status": "finding",
            })
    return issues


def _run_leg_a(root: Path, active_dirs: list[Path]) -> list[dict]:
    python_exe = _resolve_product_venv_python(root)
    if python_exe is None:
        return [{
            "product": "<fleet>", "file": "venv/bin/python",
            "issue": (
                "stand-in-conformance leg A could not find a product-backend "
                "Python venv (checked <repo_root>/venv and the primary "
                "checkout's venv via git-common-dir) — INCONCLUSIVE for "
                "every product's dependency-resolution leg, not ok."
            ),
            "severity": "warning", "leg": "A", "status": "inconclusive",
        }]

    backend_products = [d for d in active_dirs if (d / "backend" / "app").is_dir()]
    if not backend_products:
        return []

    issues: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(backend_products))) as pool:
        futures = {
            pool.submit(_leg_a_check_product, d.name, d, root, python_exe): d.name
            for d in backend_products
        }
        for fut in as_completed(futures):
            slug = futures[fut]
            try:
                issues.extend(fut.result())
            except Exception as exc:  # pragma: no cover — defensive
                issues.append({
                    "product": slug, "file": f"{slug}/backend/app",
                    "issue": (
                        f"stand-in-conformance leg A crashed unexpectedly: "
                        f"{exc!r} — INCONCLUSIVE, not ok."
                    ),
                    "severity": "warning", "leg": "A", "status": "inconclusive",
                })
    return issues


# ---------------------------------------------------------------------------
# LEG B(iii) — write payloads the double accepts must be encodable by the
# real client. STATIC: pins that the wiring survives, never re-implements
# `_validate_json_serializable` (which already ships + has its own tests).
# ---------------------------------------------------------------------------

def _leg_b_iii_mock_write_validator_wired(root: Path) -> list[dict]:
    mocks_path = root / "seed" / "lib" / "backend" / "noctusai_lib" / "testing" / "mocks.py"
    if not mocks_path.is_file():
        return [{
            "product": "<seed>", "file": "seed/lib/backend/noctusai_lib/testing/mocks.py",
            "issue": "mocks.py not found — INCONCLUSIVE for the write-payload conformance leg, not ok.",
            "severity": "warning", "leg": "B(iii)", "status": "inconclusive",
        }]
    try:
        tree = ast.parse(mocks_path.read_text(encoding="utf-8"), filename=str(mocks_path))
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        return [{
            "product": "<seed>", "file": "seed/lib/backend/noctusai_lib/testing/mocks.py",
            "issue": f"cannot parse mocks.py ({exc}) — INCONCLUSIVE, not ok.",
            "severity": "warning", "leg": "B(iii)", "status": "inconclusive",
        }]

    target_methods = {"insert", "update", "upsert"}
    found_methods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MockRequestBuilder":
            for item in node.body:
                if (
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name in target_methods
                ):
                    calls_validator = any(
                        isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Name)
                        and n.func.id == "_validate_json_serializable"
                        for n in ast.walk(item)
                    )
                    if calls_validator:
                        found_methods.add(item.name)

    missing = target_methods - found_methods
    if not missing:
        return []
    return [{
        "product": "<seed>",
        "file": "seed/lib/backend/noctusai_lib/testing/mocks.py::MockRequestBuilder",
        "issue": (
            f"`MockRequestBuilder.{'/'.join(sorted(missing))}` no longer "
            "calls `_validate_json_serializable` — the mock would once "
            "again accept a write payload (e.g. a bare `datetime.date`) the "
            "REAL PostgREST client cannot JSON-encode, exactly the "
            "`imovel_dados` failure class (2026-09-22). Restore the call — "
            "do not re-implement the check inline."
        ),
        "severity": "high", "leg": "B(iii)", "status": "finding",
    }]


# ---------------------------------------------------------------------------
# LEG B(iv) — a migration-declared cross-column CHECK the mock cannot
# express must be covered by a `ConditionalPresenceManifest` entry, or
# explicitly named as unenforceable. An unlisted one is a finding.
# ---------------------------------------------------------------------------

_CHECK_CONSTRAINT_NAME_RE = re.compile(
    r"ADD\s+CONSTRAINT\s+(?P<name>\w+)\s+CHECK\s*\(", re.IGNORECASE,
)
_ALTER_TABLE_RE = re.compile(
    r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:\w+\.)?(?P<table>\w+)", re.IGNORECASE,
)
_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:\w+\.)?(?P<table>\w+)", re.IGNORECASE,
)
_BARE_CHECK_RE = re.compile(r"\bCHECK\s*\(", re.IGNORECASE)
_SQL_STOPWORDS = {
    "and", "or", "not", "null", "is", "in", "true", "false", "exists",
    "between", "like", "ilike", "any", "all", "select", "from", "where",
    "distinct", "case", "when", "then", "else", "end", "now",
}


def _extract_balanced_parens(text: str, open_paren_index: int) -> str:
    """`text[open_paren_index]` must be `'('`. Returns the substring
    strictly INSIDE the matching balanced parens."""
    depth = 0
    for i in range(open_paren_index, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren_index + 1:i]
    return text[open_paren_index + 1:]  # unbalanced — best effort


def _check_body_column_count(body: str) -> int:
    """Distinct SQL-identifier-shaped tokens in a CHECK body (string
    literals stripped first, function-call NAMES stripped — `now()` /
    `current_org_id()` are not columns —, SQL keywords stripped). A
    heuristic proxy for "how many columns does this CHECK constrain" —
    >=2 flags a CROSS-COLUMN CHECK, the shape `CheckManifest`'s
    single-column allowed-value model cannot express (a
    `col IN ('a','b')` or `col >= 0` shape resolves to exactly 1 and is
    correctly excluded — that class already has a working mock model)."""
    no_strings = re.sub(r"'[^']*'", "", body)
    # A function CALL's name is not a column reference (`current_org_id()`,
    # `now()`, `length(x)`) — strip the identifier immediately preceding an
    # opening paren, keeping the paren so its ARGUMENTS still get scanned.
    no_calls = re.sub(r"\b[A-Za-z_][A-Za-z0-9_]*\s*\(", "(", no_strings)
    idents = {
        tok.lower() for tok in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", no_calls)
    }
    idents -= _SQL_STOPWORDS
    return len(idents)


#: `WITH CHECK (...)` on a `CREATE POLICY` is an RLS predicate, not a table
#: CHECK CONSTRAINT — `CheckManifest`/`ConditionalPresenceManifest` are about
#: the latter only. `re.subn` cannot use a variable-length lookbehind on
#: whitespace, so this is applied as a POST-MATCH filter instead of baking
#: it into `_BARE_CHECK_RE`.
_PRECEDED_BY_WITH_RE = re.compile(r"\bWITH\s*$", re.IGNORECASE)


def _find_cross_column_checks(sql_path: Path) -> list[tuple[str, str, str]]:
    """Return `[(table, constraint_name_or_'<inline>', check_body), ...]`
    for every table CHECK CONSTRAINT in this migration file referencing
    2+ distinct identifiers. RLS `WITH CHECK (...)` predicates and SQL
    line-comments are excluded — neither is the CHECK CONSTRAINT shape
    `CheckManifest`/`ConditionalPresenceManifest` model."""
    try:
        raw_text = sql_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    # Strip `-- ...` line comments (a comment quoting `CHECK (...)` in
    # prose must never be mistaken for a live constraint) while preserving
    # every other character's OFFSET, so match positions above stay valid.
    text = re.sub(r"--[^\n]*", lambda m: " " * len(m.group(0)), raw_text)

    events: list[tuple[int, str, object]] = []
    for m in _CREATE_TABLE_RE.finditer(text):
        events.append((m.start(), "table", m.group("table")))
    for m in _ALTER_TABLE_RE.finditer(text):
        events.append((m.start(), "table", m.group("table")))
    for m in _CHECK_CONSTRAINT_NAME_RE.finditer(text):
        events.append((m.start(), "named_check", m))
    for m in _BARE_CHECK_RE.finditer(text):
        events.append((m.start(), "check", m))
    events.sort(key=lambda e: e[0])

    findings: list[tuple[str, str, str]] = []
    current_table = "<unknown>"
    pending_name = None
    for _pos, kind, payload in events:
        if kind == "table":
            current_table = payload  # type: ignore[assignment]
        elif kind == "named_check":
            pending_name = payload.group("name")  # type: ignore[union-attr]
        elif kind == "check":
            check_kw_start = payload.start()  # type: ignore[union-attr]
            if _PRECEDED_BY_WITH_RE.search(text[max(0, check_kw_start - 12):check_kw_start]):
                continue  # RLS `WITH CHECK (...)`, not a table CHECK CONSTRAINT
            open_idx = payload.end() - 1  # type: ignore[union-attr]
            body = _extract_balanced_parens(text, open_idx)
            if _check_body_column_count(body) >= 2:
                findings.append((current_table, pending_name or "<inline>", body.strip()))
            pending_name = None
    return findings


def _has_conditional_presence_coverage(tests_dir: Path, table: str) -> bool:
    """True if some test file under `tests_dir` declares a
    `ConditionalPresenceManifest`-shaped manifest (naming convention:
    a `*_PRESENCE_MANIFEST` constant, per the shipped
    `_ATENDIMENTO_CONTRATO_VERSOES_PRESENCE_MANIFEST` example) that
    mentions this table as a quoted string literal — the manifest's key."""
    if not tests_dir.is_dir():
        return False
    quoted_double = f'"{table}"'
    quoted_single = f"'{table}'"
    for py_file in tests_dir.rglob("*.py"):
        try:
            text = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "PRESENCE_MANIFEST" not in text and "ConditionalPresenceManifest" not in text:
            continue
        if quoted_double in text or quoted_single in text:
            return True
    return False


def _leg_b_iv_check_constraint_coverage(root: Path, active_dirs: list[Path]) -> list[dict]:
    issues: list[dict] = []
    for product_dir in active_dirs:
        slug = product_dir.name
        migrations_dir = product_dir / "backend" / "migrations"
        if not migrations_dir.is_dir():
            continue
        tests_dir = product_dir / "backend" / "tests"
        for sql_path in sorted(migrations_dir.glob("*.sql")):
            for table, constraint_name, body in _find_cross_column_checks(sql_path):
                key = f"{slug}/{table}/{constraint_name}"
                if key in _KNOWN_UNENFORCEABLE_CROSS_COLUMN_CHECKS:
                    continue
                if _has_conditional_presence_coverage(tests_dir, table):
                    continue
                rel = sql_path.relative_to(root)
                issues.append({
                    "product": slug,
                    "file": f"{rel}::{constraint_name}",
                    "issue": (
                        f"CHECK constraint `{constraint_name}` on `{table}` "
                        f"references 2+ columns ({body[:160]!r}) — "
                        "`CheckManifest`'s single-column allowed-value shape "
                        "cannot express it, and no `ConditionalPresenceManifest` "
                        f"entry for `{table}` was found under "
                        f"{slug}/backend/tests/. Either add a "
                        "`ConditionalPresenceManifest` entry mirroring this "
                        "CHECK (never weaken the SQL), or name this constraint "
                        "in `_KNOWN_UNENFORCEABLE_CROSS_COLUMN_CHECKS` "
                        "(`mcp/noctusai/tools/noctus/dev/stand_in_conformance.py`) "
                        "with the reason it's pinned elsewhere. An unlisted "
                        "cross-column CHECK is exactly the "
                        "`atendimento_contrato_versoes` failure class "
                        "(2026-09-22): the double can't fail on a constraint "
                        "it doesn't know about, so the suite stays green "
                        "while the real INSERT 500s."
                    ),
                    "severity": "high", "leg": "B(iv)", "status": "finding",
                })
    return issues


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def check_stand_in_conformance(repo_root: Path | None = None) -> list[dict]:
    """A stand-in (mock/wrapper) must satisfy the same CONTRACT as the real
    thing it replaces. Composes leg A (dependency resolution against a real
    client object) + leg B (i weak-referenceability, ii identity stability,
    iii write-payload encodability, iv CHECK-constraint-coverage inventory).
    Scoped to `ativo=true` products (`_active_product_dirs`) for CI speed.
    Never reports a product `ok` when it could not be measured — see the
    module docstring's `status="inconclusive"` posture.
    """
    root = repo_root or REPO_ROOT
    issues: list[dict] = []

    # Static, fast, global — no product loop needed.
    issues.extend(_leg_b_iii_mock_write_validator_wired(root))

    products_dir = root / "products"
    if not products_dir.is_dir():
        return issues

    active_dirs = _active_product_dirs(products_dir)

    # Static, fast, per-product.
    issues.extend(_leg_b_iv_check_constraint_coverage(root, active_dirs))

    # Dynamic, subprocess-per-product, parallelized.
    issues.extend(_run_leg_a(root, active_dirs))

    return issues
