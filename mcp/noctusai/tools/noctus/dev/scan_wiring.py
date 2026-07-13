"""`noctus.dev.scan_wiring` — the STATIC wiring-check for one product.

Implements the *static* legs of the product-internal-wiring audit
(`KB § PATTERNS/product-internal-wiring.md` — legs 2, 4, 5). A product UI
surface is "wired" only when it shows REAL data via a real endpoint that
actually returns real data — **route-exists ≠ wired**. The runtime leg (3)
and the page-scoped-CRUD leg (7) are out of scope for this tool (the
runtime leg is a live auth-gated probe; CRUD-completeness needs judgment).

Scans `products/<product>/frontend/` + `products/<product>/backend/` for
three static failure shapes:

**Leg A — FE-endpoint → backend-route existence** (catches 404s /
route-exists-but-missing). Every literal `api.<method>('<path>')` call in
the FE is matched against the set of registered backend routes
(`@router.<method>("<path>")` + the router's `include_router(..., prefix=)`
mount). Dynamic segments (`${id}` / `{id}` / `:id`) normalize to a single
placeholder on BOTH sides; matching is by segment-count + literal segments.
A FE call with no backend match is FLAGGED.

**Leg B — name-on-`nome` column lint** (the recurring 500 class). The
platform schema is Portuguese: tables `plans` / `products` / `organizations`
use `nome` (NOT `name`). A PostgREST `.select("plans(name)")` /
`plans!inner(name)` selecting `name` on a nome-table is FLAGGED — that's the
exact 500 that zeroed the core admin dashboard.

**Leg C — `Promise.all` shared-catch** (the fast-fail aggregation
anti-pattern). A `Promise.all([ api.get(...), api.get(...) ])` whose
elements ALL lack a per-element `.catch(...)`, inside a single shared
`try { ... } catch`, turns ONE failure into all-zeros. FLAGGED. We flag
ONLY the PURE shared-catch shape — if ≥1 element already has its own
`.catch(() => fallback)` the array is a deliberate "primary + degrading
aux" pattern, NOT the all-zeros bug, so it is NOT flagged (leg-4
precision). A `Promise.all` whose elements each have `.catch()` degrades
independently and is CORRECT — not flagged.

Provenance: born 2026-05-25 from the core admin-panel wiring session (the
`plans.name`/`nome` 500 + `Promise.all` fast-fail → all-zeros dashboard).
This tool is the automated mechanism named in the rule doc § 2a.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from settings import REPO_ROOT  # noqa: E402  (path constant)


# ---------------------------------------------------------------------------
# Module constants — explicit + configurable so they're easy to extend.
# ---------------------------------------------------------------------------

# Tables whose canonical "display name" column is the Portuguese `nome`,
# NOT the English `name`. Selecting `name` on one of these is the recurring
# 500 class. Keep this set explicit so a future schema addition is one line.
_NOME_TABLES: frozenset[str] = frozenset({
    "plans",
    "products",
    "organizations",
})

# FE source file extensions to scan.
_FE_EXTS: tuple[str, ...] = (".ts", ".tsx")
# Backend router file extension.
_BE_EXT: str = ".py"

# Test / mock files are NOT shipped production surfaces — they use fake or
# placeholder API paths (`api.get('/api/x')`), fixture table selects, etc. by
# design. The product-internal-wiring checks (route-exists, name-on-nome,
# promise-all) target PRODUCTION code, so every wiring walk must skip these or
# a test fixture reads as a real route-missing / name-on-nome regression
# (surfaced 2026-07-13: core's new `src/lib/api.test.ts` tripped
# check_fe_route_missing with its deliberate `/api/x` stub paths).
_TEST_FILE_NAME_RE = re.compile(r"\.(test|spec)\.[jt]sx?$|^test_.*\.py$|_test\.py$")
_TEST_DIR_PARTS: frozenset[str] = frozenset({"__tests__", "__mocks__", "tests"})


def _is_test_file(path: Path) -> bool:
    """True for FE (`*.test.ts(x)`/`*.spec.*`) or Python (`test_*.py`/`*_test.py`)
    test files, or any file under a `__tests__`/`__mocks__`/`tests` directory."""
    if _TEST_FILE_NAME_RE.search(path.name):
        return True
    return any(part in _TEST_DIR_PARTS for part in path.parts)

# HTTP methods we recognise on both sides.
_HTTP_METHODS: tuple[str, ...] = ("get", "post", "patch", "put", "delete")

# A single normalized placeholder token for dynamic path segments.
_PLACEHOLDER = "{*}"


# ---------------------------------------------------------------------------
# Pydantic In / Out (per `KB § PATTERNS/mcp-tool-conventions.md § 2`).
# ---------------------------------------------------------------------------

class ScanWiringInput(BaseModel):
    product: str = Field(description="Product slug to scan (e.g. 'core').")
    worktree_path: str | None = Field(
        default=None,
        description=(
            "Repo/worktree root override. When None, scans the MCP "
            "server's REPO_ROOT. Pass this when calling from inside an "
            "isolated git worktree (the server's CWD is NOT the caller's)."
        ),
    )


class WiringFinding(BaseModel):
    file: str = Field(description="Repo-relative file path of the occurrence.")
    line: int = Field(description="1-based line number.")
    detail: str = Field(description="Human-readable description of the wiring defect.")


class ScanWiringOutput(BaseModel):
    ok: bool = Field(default=True, description="True when the scan ran (findings may be non-empty).")
    product: str = Field(description="The scanned product slug.")
    missing_routes: list[WiringFinding] = Field(
        default_factory=list,
        description="Leg A — FE api-calls with no matching backend route.",
    )
    name_on_nome: list[WiringFinding] = Field(
        default_factory=list,
        description="Leg B — selecting `name` on a `nome`-table (the 500 class).",
    )
    shared_catch_promise_all: list[WiringFinding] = Field(
        default_factory=list,
        description="Leg C — `Promise.all` of bare fetches under one shared catch.",
    )
    totals: dict[str, int] = Field(
        default_factory=dict,
        description="Per-leg + grand-total finding counts.",
    )
    backend_routes_found: int = Field(
        default=0,
        description="How many (method, path) backend routes were extracted (Leg A diagnostic).",
    )
    fe_calls_found: int = Field(
        default=0,
        description="How many FE api-calls were extracted (Leg A diagnostic).",
    )
    next_action: str = Field(description="What the caller should do next.")


# ---------------------------------------------------------------------------
# Path normalization (shared by Leg A FE + BE extraction)
# ---------------------------------------------------------------------------

def _normalize_path(path: str) -> str:
    """Collapse a URL path into a comparable canonical form.

    - Strips query strings + trailing slashes.
    - Replaces dynamic segments — `${id}` / `{id}` / `:id` / a segment that
      is purely a `${...}` / `{...}` template — with `_PLACEHOLDER`.
    - Leaves literal segments intact.

    `/api/plans/${planId}` and `/api/plans/{plan_id}` both normalize to
    `/api/plans/{*}`. Segment count + literal segments are preserved so
    matching is structural, not string-equality.
    """
    # Drop query string + hash.
    path = path.split("?", 1)[0].split("#", 1)[0]
    # Drop trailing slash (but keep a lone "/").
    if len(path) > 1:
        path = path.rstrip("/")
    segments = path.split("/")
    out: list[str] = []
    for seg in segments:
        if not seg:
            out.append(seg)  # preserve leading "" so "/api/x" stays anchored
            continue
        if _is_dynamic_segment(seg):
            out.append(_PLACEHOLDER)
        else:
            out.append(seg)
    return "/".join(out)


def _is_dynamic_segment(seg: str) -> bool:
    """True if a path segment is a dynamic placeholder of any flavor."""
    # FastAPI: {id} / {plan_id}  — whole segment wrapped in braces.
    if seg.startswith("{") and seg.endswith("}"):
        return True
    # JS template: ${id} / ${planId} — whole segment is one interpolation.
    if seg.startswith("${") and seg.endswith("}"):
        return True
    # Express-style :id.
    if seg.startswith(":"):
        return True
    # A segment containing a `${...}` interpolation anywhere (e.g. the path
    # was built `/api/plans/${id}` with no surrounding literal) — treat the
    # whole segment as dynamic. If it has BOTH a literal prefix and an
    # interpolation (`prefix-${id}`) it's effectively dynamic too.
    if "${" in seg:
        return True
    return False


# ---------------------------------------------------------------------------
# Leg A — FE api-call extraction
# ---------------------------------------------------------------------------

# Matches `api.get('<path>')`, `api.post("<path>")`, and template-literal
# `api.get(`<path>`)`. The path capture stops at the matching quote/backtick.
_FE_API_CALL_RE = re.compile(
    r"\bapi\.(?P<method>" + "|".join(_HTTP_METHODS) + r")\s*\(\s*"
    r"""(?P<q>['"`])(?P<path>[^'"`]*?)(?P=q)""",
)


@dataclass
class _FeCall:
    method: str
    raw_path: str
    norm_path: str
    file: str
    line: int


def _extract_fe_calls(fe_root: Path, repo_root: Path) -> list[_FeCall]:
    """Extract every literal `api.<method>('<path>')` call in the FE src tree."""
    calls: list[_FeCall] = []
    src = fe_root / "src"
    scan_root = src if src.exists() else fe_root
    for path in scan_root.rglob("*"):
        if not path.is_file() or path.suffix not in _FE_EXTS:
            continue
        if _is_test_file(path):
            continue  # test fixtures use stub /api paths by design
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.warning("scan_wiring: cannot read %s (%s), skipping", path, exc)
            continue
        try:
            rel = str(path.relative_to(repo_root))
        except ValueError:
            rel = str(path)
        for lineno, line in enumerate(content.splitlines(), start=1):
            for m in _FE_API_CALL_RE.finditer(line):
                method = m.group("method").lower()
                raw_path = m.group("path")
                # Skip fully-dynamic paths we can't normalize: a path that
                # is ONLY a `${...}` with no leading literal `/api/...` slug
                # (we can't tell which backend route it targets).
                if not raw_path.startswith("/"):
                    continue
                calls.append(_FeCall(
                    method=method,
                    raw_path=raw_path,
                    norm_path=_normalize_path(raw_path),
                    file=rel,
                    line=lineno,
                ))
    return calls


# ---------------------------------------------------------------------------
# Leg A — backend route extraction (decorator path + mount prefix)
# ---------------------------------------------------------------------------

# `@router.get("/foo")`, `@router.post('/{id}')`, with an optional alias
# (`@some_router.patch(...)`); we capture the method + the literal path arg.
_BE_ROUTE_RE = re.compile(
    r"@\s*(?P<obj>[A-Za-z_][A-Za-z0-9_]*)\s*\.\s*"
    r"(?P<method>" + "|".join(_HTTP_METHODS) + r")\s*\(\s*"
    r"""(?P<q>['"])(?P<path>[^'"]*?)(?P=q)""",
)

# `APIRouter(prefix="/api/x")` — the canonical noc pattern: each router file
# declares its prefix on the constructor, and the decorators inside that file
# hang off it. We extract this PER FILE so each file's decorators are joined
# to that file's own prefix (accurate, not over-generated).
_APIROUTER_PREFIX_RE = re.compile(
    r"APIRouter\s*\([^)]*?prefix\s*=\s*['\"](?P<prefix>[^'\"]*)['\"]",
    re.DOTALL,
)
# `include_router(<name>, prefix="/api/x")` — the secondary mount form (the
# prefix can also be applied at mount time). We harvest these prefixes
# repo-wide as a fallback prefix pool (used as candidate prefixes for
# decorator paths that had no file-local APIRouter prefix).
_INCLUDE_ROUTER_PREFIX_RE = re.compile(
    r"include_router\s*\([^)]*?prefix\s*=\s*['\"](?P<prefix>[^'\"]*)['\"]",
    re.DOTALL,
)

# Seed-framework router files — `standard_routers=[...]` mounts these via
# `create_product_app`. Their prefixes live in the seed, not in product code,
# so we scan the seed framework tree too (per-file, same as product routers).
_SEED_ROUTER_GLOB = "seed/framework/backend/noctusai_seed/**/*.py"


@dataclass
class _BeRouteScan:
    routes: set[tuple[str, str]] = field(default_factory=set)  # (method, norm_full_path)
    prefixes: set[str] = field(default_factory=set)
    raw_decorator_paths: list[tuple[str, str]] = field(default_factory=list)  # (method, raw_path)


def _routes_from_file(content: str) -> tuple[list[tuple[str, str]], set[str]]:
    """Return (per-file full routes, prefixes-found) for one Python file.

    Each file is treated as a unit: the file's `APIRouter(prefix=...)`
    declarations form the file's prefix set; every `@router.<method>` decorator
    in the file is joined to EACH file-local prefix (a file usually has one).
    A file with NO APIRouter prefix contributes its bare decorator paths so
    a same-origin / prefix-at-mount-time route still resolves.
    """
    file_prefixes = {m.group("prefix") for m in _APIROUTER_PREFIX_RE.finditer(content)}
    include_prefixes = {m.group("prefix") for m in _INCLUDE_ROUTER_PREFIX_RE.finditer(content)}
    decorators = [
        (m.group("method").lower(), m.group("path") or "/")
        for m in _BE_ROUTE_RE.finditer(content)
    ]
    full_routes: list[tuple[str, str]] = []
    join_prefixes = file_prefixes or {""}
    for method, raw in decorators:
        for prefix in join_prefixes:
            full_routes.append((method, _join_route(prefix, raw)))
    return full_routes, (file_prefixes | include_prefixes)


def _join_route(prefix: str, raw: str) -> str:
    if raw in ("", "/"):
        full = prefix or "/"
    else:
        full = prefix.rstrip("/") + "/" + raw.lstrip("/")
    if not full.startswith("/"):
        full = "/" + full
    return _normalize_path(full)


def _scan_backend_routes(be_root: Path, repo_root: Path | None = None) -> _BeRouteScan:
    """Build the set of (method, normalized full path) backend routes.

    Strategy (per-file accurate): for each backend `.py` under `app/`, join
    that file's own `APIRouter(prefix=...)` to its `@router.<method>`
    decorators. ALSO scan the seed framework (`seed/framework/backend/
    noctusai_seed/`) — products mount seed routers (health, notificacoes,
    ai_feedback, …) via `create_product_app(standard_routers=[...])` and those
    prefixes (`/api/notificacoes`, `/api/ai`, …) live in the seed, not in
    product code. Finally, decorator paths whose file had no local prefix are
    ALSO offered under every discovered prefix (covers prefix-at-mount-time).
    """
    scan = _BeRouteScan()
    routers_root = be_root / "app"
    scan_root = routers_root if routers_root.exists() else be_root

    bare_decorators: list[tuple[str, str]] = []

    def _ingest(content: str) -> None:
        full_routes, prefixes = _routes_from_file(content)
        scan.prefixes |= prefixes
        for r in full_routes:
            scan.routes.add(r)
        # Track decorator paths that had no file-local prefix (their joined
        # route is the bare path) so we can re-offer them under seed prefixes.
        if not prefixes:
            for m in _BE_ROUTE_RE.finditer(content):
                bare_decorators.append((m.group("method").lower(), m.group("path") or "/"))

    if scan_root.exists():
        for path in scan_root.rglob("*"):
            if not path.is_file() or path.suffix != _BE_EXT:
                continue
            try:
                _ingest(path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, OSError) as exc:
                logger.warning("scan_wiring: cannot read %s (%s), skipping", path, exc)

    # Seed framework routers (mounted via standard_routers).
    seed_root = repo_root or REPO_ROOT
    for path in seed_root.glob(_SEED_ROUTER_GLOB):
        if not path.is_file():
            continue
        try:
            _ingest(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, OSError) as exc:
            logger.warning("scan_wiring: cannot read seed router %s (%s), skipping", path, exc)

    # Re-offer prefix-less decorator paths under every discovered prefix
    # (covers the prefix-at-mount-time / include_router(prefix=) form).
    for method, raw in bare_decorators:
        for prefix in scan.prefixes:
            scan.routes.add((method, _join_route(prefix, raw)))

    return scan


def _route_matches(method: str, norm_path: str, routes: set[tuple[str, str]]) -> bool:
    """Structural match: same method + same segment count + literal segments
    equal, placeholders matching anything.
    """
    want_segs = norm_path.split("/")
    for r_method, r_path in routes:
        if r_method != method:
            continue
        have_segs = r_path.split("/")
        if len(have_segs) != len(want_segs):
            continue
        if all(_seg_match(a, b) for a, b in zip(want_segs, have_segs)):
            return True
    return False


def _seg_match(want: str, have: str) -> bool:
    """One placeholder matches any literal; otherwise literal equality."""
    if want == _PLACEHOLDER or have == _PLACEHOLDER:
        return True
    return want == have


# ---------------------------------------------------------------------------
# Leg B — name-on-`nome` column lint
# ---------------------------------------------------------------------------

# For each nome-table, match a PostgREST embed/select that pulls `name`:
#   plans(name)            plans!inner(name)       plans ( id, name )
#   products(name,price)   organizations(...,name)
# We build one regex per table covering `<table>` optionally followed by an
# `!inner`/`!left`/alias modifier, then a paren-group that contains `name`
# as a bare column (word-boundaried, not `nome`, not `*_name`).
def _nome_table_regexes() -> list[tuple[str, re.Pattern]]:
    pats: list[tuple[str, re.Pattern]] = []
    for table in sorted(_NOME_TABLES):
        # <table>  [ !modifier ]  ( ... name ... )
        pat = re.compile(
            r"\b" + re.escape(table) + r"\b"
            r"(?:![A-Za-z_]+)?"          # optional !inner / !left
            r"\s*\("                      # opening paren of the embed/select
            r"(?P<cols>[^()]*)"           # column list (no nested parens)
            r"\)",
        )
        pats.append((table, pat))
    return pats


_NOME_TABLE_REGEXES = _nome_table_regexes()
# Within a captured column list, a bare `name` column (word boundary on both
# sides, so `nome` / `first_name` / `display_name` do NOT match).
_BARE_NAME_RE = re.compile(r"(?<![A-Za-z0-9_])name(?![A-Za-z0-9_])")


def _scan_name_on_nome(roots: list[tuple[Path, tuple[str, ...]]], repo_root: Path) -> list[WiringFinding]:
    """Scan the given (root, extensions) pairs for `name`-on-nome-table selects."""
    findings: list[WiringFinding] = []
    for root, exts in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in exts:
                continue
            if _is_test_file(path):
                continue  # test fixtures may select `name` in stub data by design
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError) as exc:
                logger.warning("scan_wiring: cannot read %s (%s), skipping", path, exc)
                continue
            try:
                rel = str(path.relative_to(repo_root))
            except ValueError:
                rel = str(path)
            for lineno, line in enumerate(content.splitlines(), start=1):
                for table, pat in _NOME_TABLE_REGEXES:
                    for m in pat.finditer(line):
                        cols = m.group("cols")
                        if _BARE_NAME_RE.search(cols):
                            findings.append(WiringFinding(
                                file=rel,
                                line=lineno,
                                detail=(
                                    f"selects `name` on `{table}` — that column "
                                    f"is `nome` (Portuguese schema); this is the "
                                    f"recurring 500 class. Read `nome`, not `name`."
                                ),
                            ))
    return findings


# ---------------------------------------------------------------------------
# Leg C — Promise.all shared-catch
# ---------------------------------------------------------------------------

_PROMISE_ALL_RE = re.compile(r"Promise\.all\s*\(\s*\[")


def _scan_promise_all_shared_catch(fe_root: Path, repo_root: Path) -> list[WiringFinding]:
    """Flag `Promise.all([ bare fetches ])` under one shared try/catch.

    Heuristic (line-aware, brace-balanced):
      1. Find `Promise.all([`. Capture the bracket-balanced array body.
      2. Flag ONLY the PURE shared-catch shape — i.e. NONE of the array
         elements has a per-element `.catch(`. That is the real
         one-failure-zeros-everything bug. If ≥1 element already has its own
         `.catch()`, the shape is "one deliberate primary (drives auth/error/
         logout) + degrading aux" — NOT the all-zeros bug — so it is NOT
         flagged (leg-4 precision, 2026-05-25).
      3. Confirm the call is inside a `try {` whose nearest enclosing
         `catch` is shared. We approximate "inside a shared try/catch" by
         checking that a `try {` opened earlier in the function body precedes
         the Promise.all on a prior or same line and a `catch` follows the
         Promise.all — the all-zeros bug shape.
    """
    findings: list[WiringFinding] = []
    src = fe_root / "src"
    scan_root = src if src.exists() else fe_root
    if not scan_root.exists():
        return findings

    for path in scan_root.rglob("*"):
        if not path.is_file() or path.suffix not in _FE_EXTS:
            continue
        if _is_test_file(path):
            continue  # test fixtures aren't shipped surfaces
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.warning("scan_wiring: cannot read %s (%s), skipping", path, exc)
            continue
        try:
            rel = str(path.relative_to(repo_root))
        except ValueError:
            rel = str(path)
        findings.extend(_scan_promise_all_in_text(content, rel))
    return findings


def _scan_promise_all_in_text(content: str, rel: str) -> list[WiringFinding]:
    findings: list[WiringFinding] = []
    for m in _PROMISE_ALL_RE.finditer(content):
        open_bracket = m.end() - 1  # index of the `[`
        body, end_idx = _balanced_slice(content, open_bracket, "[", "]")
        if body is None:
            continue
        # Flag ONLY the PURE shared-catch shape (no element has its own
        # `.catch()`). A mixed shape — ≥1 element guarded by `.catch()` — is a
        # deliberate primary + degrading-aux pattern, NOT the all-zeros bug.
        if not _is_pure_shared_catch(body):
            continue
        # Determine the line number of the Promise.all.
        lineno = content.count("\n", 0, m.start()) + 1
        # Shared-catch check: a `try {` precedes this Promise.all in the
        # enclosing scope AND there's NO per-element `.catch` (already
        # ensured by _is_pure_shared_catch). We look backward for the nearest
        # unmatched `try {` and forward for a `catch`.
        if _under_shared_try_catch(content, m.start(), end_idx):
            findings.append(WiringFinding(
                file=rel,
                line=lineno,
                detail=(
                    "`Promise.all([...])` of bare `api.*` fetches under a single "
                    "shared try/catch — one failure zeros every result (the "
                    "all-zeros dashboard bug). Give each element its own "
                    "`.catch(() => fallback)` so they degrade independently."
                ),
            ))
    return findings


def _balanced_slice(text: str, open_idx: int, open_ch: str, close_ch: str) -> tuple[str | None, int]:
    """Return (inner_text, index_after_close) for the bracket opened at open_idx.

    Bracket-balanced, quote/template/backtick-aware enough to skip brackets
    inside string literals. Returns (None, open_idx) if unbalanced.
    """
    depth = 0
    i = open_idx
    n = len(text)
    quote: str | None = None
    start_inner = open_idx + 1
    while i < n:
        ch = text[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            i += 1
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start_inner:i], i + 1
        i += 1
    return None, open_idx


# A bare fetch = `api.<method>(` that is NOT immediately followed (after its
# own bracket-balanced call) by a `.catch(`. We approximate per-element
# `.catch` by checking whether each `api.<method>(...)` occurrence in the
# array body is chained to `.catch(` within the same element.
_API_CALL_IN_BODY_RE = re.compile(r"\bapi\.(" + "|".join(_HTTP_METHODS) + r")\s*\(")


def _is_pure_shared_catch(body: str) -> bool:
    """True for the PURE shared-catch shape — ≥1 `api.<method>(...)` call AND
    NONE of them has a per-element `.catch(`.

    Leg-4 precision (2026-05-25): the all-zeros bug is the array where EVERY
    element is bare (one failure zeros every result). A MIXED array — at least
    one element already guarded by its own `.catch(() => fallback)` — is a
    deliberate "primary drives auth/error/logout + aux degrades" pattern, NOT
    the bug, so we do NOT flag it. We flag only when zero elements are guarded.
    """
    saw_api = False
    for m in _API_CALL_IN_BODY_RE.finditer(body):
        saw_api = True
        call_open = m.end() - 1
        _inner, after = _balanced_slice(body, call_open, "(", ")")
        if after <= call_open:
            # unbalanced — treat conservatively as bare (likely a real fetch);
            # keep scanning so a later guarded element can still spare the array.
            continue
        # Look at what immediately follows the call (allow chained `.then`/
        # whitespace). If a `.catch(` appears before the next element boundary
        # (a top-level comma or end of body), this element is protected — so
        # the array is NOT a pure shared-catch and must not be flagged.
        tail = body[after:]
        if _element_has_catch(tail):
            return False
    # Reached here ⇒ every api call was bare (no per-element catch). Flag only
    # if there was at least one api call (an array with none is not our shape).
    return saw_api


def _element_has_catch(tail: str) -> bool:
    """Scan `tail` (text after an api call) for a `.catch(` belonging to the
    same array element — i.e. before the next top-level comma / array end.
    """
    depth = 0
    quote: str | None = None
    i = 0
    n = len(tail)
    while i < n:
        ch = tail[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            i += 1
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                return False  # reached the array's closing bracket
            depth -= 1
        elif ch == "," and depth == 0:
            return False  # next element boundary, no catch found
        elif ch == "." and depth == 0:
            if tail[i:i + 6] == ".catch":
                return True
        i += 1
    return False


def _under_shared_try_catch(content: str, promise_start: int, promise_end: int) -> bool:
    """Heuristic: a `try {` opens before the Promise.all and a `catch` follows
    it in the enclosing block — the shared-catch shape. We look in a bounded
    window to avoid matching unrelated try/catch elsewhere in the file.
    """
    before = content[:promise_start]
    after = content[promise_end:]
    # Nearest `try` before the call (whitespace-tolerant `try {`).
    try_matches = list(re.finditer(r"\btry\s*\{", before))
    if not try_matches:
        return False
    # A `catch` after the call within a reasonable window (the enclosing
    # function); cap the window so a far-away catch doesn't false-positive.
    window = after[:4000]
    if re.search(r"\bcatch\s*(?:\([^)]*\))?\s*\{", window):
        return True
    return False


# ---------------------------------------------------------------------------
# Per-leg pure analyzers — the SHARED predicates.
#
# These three functions are the single source of truth for the static legs.
# BOTH surfaces consume them:
#   1. `scan_wiring()` (this module → the `noctus.dev.scan_wiring` MCP tool).
#   2. The keeper detectors `check_fe_route_missing` / `check_name_on_nome_select`
#      / `check_promise_all_shared_catch` in `tools/noctus/dev/compliance.py`
#      (the regulatory Stage-4 layer — compliance gate + pre-commit).
# One predicate, two surfaces — no copy-paste (DRY). Each returns the raw
# `WiringFinding` list; the keeper adapts those into the keeper dict shape.
# ---------------------------------------------------------------------------

def analyze_missing_routes(
    fe_root: Path,
    be_root: Path,
    repo_root: Path,
) -> list[WiringFinding]:
    """Leg A — FE `api.<method>('<path>')` calls with no matching backend route.

    Pure predicate: extract every literal FE api-call + the registered backend
    routes (decorator path + APIRouter/include_router prefix + seed-framework
    routers), then flag each FE call whose (method, normalized-path) matches no
    route. Route-exists ≠ wired — this is the 404/route-missing class.
    """
    if not fe_root.exists():
        return []
    fe_calls = _extract_fe_calls(fe_root, repo_root)
    be_scan = _scan_backend_routes(be_root, repo_root=repo_root) if be_root.exists() else _BeRouteScan()
    missing: list[WiringFinding] = []
    for call in fe_calls:
        if not _route_matches(call.method, call.norm_path, be_scan.routes):
            missing.append(WiringFinding(
                file=call.file,
                line=call.line,
                detail=(
                    f"FE calls `api.{call.method}('{call.raw_path}')` but no "
                    f"backend route matches (method={call.method.upper()}, "
                    f"normalized={call.norm_path}). Route-exists ≠ wired — this "
                    f"is a 404/route-missing class."
                ),
            ))
    return missing


def analyze_name_on_nome(
    be_root: Path,
    fe_root: Path,
    repo_root: Path,
) -> list[WiringFinding]:
    """Leg B — PostgREST selecting `name` on a `nome`-table (the 500 class).

    Pure predicate: scan backend `.py` + FE `.ts/.tsx` for a select/embed of
    `(plans|products|organizations)(...name...)`. The platform schema is
    Portuguese — those tables use `nome`, so selecting `name` is the recurring
    500 (it zeroed the core admin dashboard).
    """
    return _scan_name_on_nome(
        roots=[
            (be_root, (_BE_EXT,)),
            (fe_root, _FE_EXTS),
        ],
        repo_root=repo_root,
    )


def analyze_promise_all_shared_catch(
    fe_root: Path,
    repo_root: Path,
) -> list[WiringFinding]:
    """Leg C — `Promise.all([bare fetches])` under one shared try/catch.

    Pure predicate: flag a `Promise.all` whose array elements are ALL bare
    `api.*` fetches (NONE has a per-element `.catch`) inside a single shared
    `try { ... } catch` — one failure zeros every result (the all-zeros
    dashboard bug). Leg-4 precision (2026-05-25): a MIXED array — ≥1 element
    already guarded by its own `.catch(() => fallback)` — is a deliberate
    "primary + degrading aux" pattern, NOT the bug, so it is NOT flagged.
    Per-element `.catch()` on every element degrades independently and is
    CORRECT (not flagged).
    """
    if not fe_root.exists():
        return []
    return _scan_promise_all_shared_catch(fe_root, repo_root)


# ---------------------------------------------------------------------------
# The scan (pure function — testable with a tmp_path mini-product tree)
# ---------------------------------------------------------------------------

def scan_wiring(
    product: str,
    repo_root: Path | None = None,
) -> dict:
    """Static wiring-check for one product (legs A/B/C).

    Args:
        product: the product slug under `products/<product>/`.
        repo_root: repo/worktree root; defaults to the MCP `REPO_ROOT`.

    Returns:
        A `ScanWiringOutput`-shaped dict. If `products/<product>` does not
        exist, returns `{"ok": False, "error": ...}` — an honest typed
        error, never a fake empty pass.
    """
    root = repo_root or REPO_ROOT
    product_dir = root / "products" / product
    if not product_dir.exists():
        return {
            "ok": False,
            "product": product,
            "error": (
                f"product not found: products/{product} does not exist under "
                f"{root}. Pass a valid slug (and worktree_path when calling "
                f"from inside an isolated worktree)."
            ),
        }

    fe_root = product_dir / "frontend"
    be_root = product_dir / "backend"

    # All three legs delegate to the SHARED per-leg analyzers (the predicates
    # the keeper detectors also consume — single source of truth, no dup).
    # Leg A diagnostics (fe_calls_found / backend_routes_found) are recomputed
    # here cheaply for the tool's report; the keeper doesn't need them.
    fe_calls = _extract_fe_calls(fe_root, root) if fe_root.exists() else []
    be_scan = _scan_backend_routes(be_root, repo_root=root) if be_root.exists() else _BeRouteScan()

    # --- Leg A: FE calls → backend routes ---
    missing = analyze_missing_routes(fe_root, be_root, root)
    # --- Leg B: name-on-nome lint (backend .py + FE .ts/.tsx) ---
    name_on_nome = analyze_name_on_nome(be_root, fe_root, root)
    # --- Leg C: Promise.all shared-catch (FE only) ---
    shared_catch = analyze_promise_all_shared_catch(fe_root, root)

    totals = {
        "missing_routes": len(missing),
        "name_on_nome": len(name_on_nome),
        "shared_catch_promise_all": len(shared_catch),
        "total": len(missing) + len(name_on_nome) + len(shared_catch),
    }

    output = ScanWiringOutput(
        ok=True,
        product=product,
        missing_routes=missing,
        name_on_nome=name_on_nome,
        shared_catch_promise_all=shared_catch,
        totals=totals,
        backend_routes_found=len(be_scan.routes),
        fe_calls_found=len(fe_calls),
        next_action=_next_action(totals),
    )
    return output.model_dump()


def _next_action(totals: dict[str, int]) -> str:
    if totals["total"] == 0:
        return (
            "Static wiring clean (legs A/B/C). Still run the RUNTIME leg "
            "(probe each endpoint live for 200 + real rows) + the page-scoped "
            "CRUD leg — `KB § PATTERNS/product-internal-wiring.md` steps 3 + 7."
        )
    parts: list[str] = []
    if totals["missing_routes"]:
        parts.append(
            f"{totals['missing_routes']} FE call(s) hit no backend route "
            f"(404 class) — add/fix the route or correct the FE path"
        )
    if totals["name_on_nome"]:
        parts.append(
            f"{totals['name_on_nome']} `name`-on-`nome`-table select(s) "
            f"(the 500 class) — read the Portuguese `nome` column"
        )
    if totals["shared_catch_promise_all"]:
        parts.append(
            f"{totals['shared_catch_promise_all']} shared-catch `Promise.all` "
            f"(all-zeros class) — give each fetch its own `.catch()`"
        )
    return "Fix: " + "; ".join(parts) + "."


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(server) -> None:
    @server.tool(
        name="noctus.dev.scan_wiring",
        description=(
            "Static wiring-check for ONE product (the product-internal-wiring "
            "rule, `KB § PATTERNS/product-internal-wiring.md` legs 2/4/5). "
            "Scans `products/<product>/frontend` + `/backend`: (A) every FE "
            "`api.<method>('<path>')` call → must have a matching backend "
            "`@router.<method>` route + mount prefix (catches 404s / "
            "route-exists-but-missing; dynamic segments normalized on both "
            "sides); (B) selecting `name` on a `nome`-table (plans/products/"
            "organizations) — the recurring 500 class; (C) `Promise.all([bare "
            "fetches])` under one shared try/catch — the all-zeros fast-fail. "
            "Route-exists ≠ wired. Returns per-leg findings (file/line/detail) "
            "+ totals + next_action. The runtime (leg 3) + page-scoped-CRUD "
            "(leg 7) legs are out of scope (runtime = live probe). Honest "
            "typed error if the product doesn't exist."
        ),
    )
    def _scan_wiring(product: str, worktree_path: str | None = None) -> dict:
        from workspace import resolve_caller_root

        root = resolve_caller_root(worktree_path) if worktree_path else None
        return scan_wiring(product, repo_root=root)


__all__ = [
    "scan_wiring",
    # Shared per-leg analyzers — consumed by BOTH this tool and the keeper
    # detectors in compliance.py (one predicate, two surfaces — DRY).
    "analyze_missing_routes",
    "analyze_name_on_nome",
    "analyze_promise_all_shared_catch",
    "ScanWiringInput",
    "ScanWiringOutput",
    "WiringFinding",
    "register",
    "_NOME_TABLES",
]
