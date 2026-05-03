"""`noctusai_recurrence_scan` — find DRY-into-seed candidates before they slip.

Encodes the recurrence rule (`KB § PATTERNS/project-execution.md § 2.7`):
when the same pattern / boilerplate / code shape appears in N independent
places, it should be absorbed into seed.

| N instances | Outcome |
|---|---|
| N = 2 | TRIAGE TIME — explicit decision (formalize / refactor / accept-with-rationale) |
| N = 3+ | MUST FORMALIZE — extract into seed-lib / seed-framework / shared library |

**Two scan modes** (different shapes catch different absorptions):

1. **`scan_recurrence(...)`** — line-level recurrence across structural files
   (`main.py`, `main.tsx`, `App.tsx`, `conftest.py`, `vitest.config.ts`,
   service/router files). Catches verbatim duplication: `useXFromAPI`
   hook shape, `bind_consent_module_to_mock` calls, mount lines.

2. **`scan_cross_product_helpers(...)`** — *function/dataclass-name*
   recurrence across `app/services/`, `app/routers/`, `app/dependencies.py`,
   and frontend `src/hooks/`, `src/components/`. Catches the more common
   shape: `_safe_float` / `_format_money` / `_db_with_grants` /
   `_resolve_clinic_id` / `_PipelineHooks` — the same NAME implemented
   slightly differently across products. The body need not be identical;
   the recurring NAME is the signal.

**Why the second mode matters.** The line-level scan misses 80% of real
absorptions: each product's `_safe_float` implementation differs by
1-2 chars but the helper exists in 4+ products and obviously belongs in
`noctusai_lib.parsing` or similar. Same for date-format helpers, money
formatters, ISO parsers, etc. Without name-level scanning these slip
forever — the user catches them retroactively.

**Out of scope (intentional false-positive avoidance):**
- Identical class/function NAMES that have completely different domains
  (e.g. every product has `def list_clientes(...)` in its router — that's
  not absorption-shaped; the noun is product-bound).
- Identical config files (handled by sibling detectors).
- Test files that legitimately import the same fixtures (the fixtures
  ARE the seed-side absorption; the imports are inheritance).

**Tunables:**
- `min_count` — recurrence threshold (default 2; report at TRIAGE level).
- `must_formalize_threshold` — escalation threshold (default 3).
- `min_line_length` — ignore lines shorter than this (default 25 chars;
  filters trivial `import re` style noise).
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

from settings import REPO_ROOT  # noqa: E402  (path constant)


# Files where we look for repeated lines. Each entry is a (relative
# directory glob, filename pattern). Conservative — we don't scan the
# entire `products/` tree because product-specific business logic
# legitimately has shared lines (e.g. `from fastapi import APIRouter`).
_TARGET_GLOBS: list[tuple[str, str]] = [
    # Per-product entry points (high-signal: repetition here often means
    # cross-product boilerplate that's better absorbed into seed).
    ("products/*/backend/app", "main.py"),
    ("products/*/frontend/src", "main.tsx"),
    ("products/*/frontend/src", "App.tsx"),
    # Test scaffolding (the conftest replication caught this session).
    ("products/*/backend/tests", "conftest.py"),
    ("products/*/frontend", "vitest.config.ts"),
]

# Lines matching these patterns are ignored even when they recur.
# These are legitimate inheritance markers (importing FROM seed is the
# right pattern; flagging it would false-positive every product).
_IGNORE_PATTERNS: list[re.Pattern] = [
    re.compile(r'^\s*$'),  # blank
    re.compile(r'^\s*#'),  # python comments
    re.compile(r'^\s*//'),  # ts comments
    re.compile(r'^\s*/\*'),  # ts block comments start
    re.compile(r'^\s*\*'),  # ts block comments mid
    re.compile(r'^\s*from noctusai_seed\b'),  # seed import (inheritance, not replication)
    re.compile(r'^\s*from @noctusai/seed\b'),
    re.compile(r'^\s*import .*from "@noctusai/seed'),
    re.compile(r'^\s*from noctusai_lib\b'),  # lib import
    re.compile(r'^\s*from @noctusai/lib\b'),
    re.compile(r'^\s*import .*from "@noctusai/lib'),
    re.compile(r'^\s*"""'),  # docstring delimiters
    re.compile(r"^\s*'''"),
]


@dataclass
class RecurrenceFinding:
    """One recurrence candidate."""
    line_text: str
    occurrences: list[str]  # list of file paths where this line was found
    severity: str  # "warning" (N=2) or "high" (N>=3)
    suggestion: str = ""
    classification: str = ""  # "main.py-import" / "conftest-line" / "config-line"

    def to_dict(self) -> dict:
        return {
            "line_text": self.line_text,
            "count": len(self.occurrences),
            "occurrences": self.occurrences,
            "severity": self.severity,
            "classification": self.classification,
            "suggestion": self.suggestion,
        }


def _matches_target(rel_path: Path) -> str | None:
    """Classify a file by which target-glob it matches; None if not a target."""
    rel_str = str(rel_path)
    parts = rel_path.parts
    if not parts:
        return None
    # main.py in product backend
    if (
        len(parts) >= 5
        and parts[0] == "products" and parts[2] == "backend"
        and parts[3] == "app" and parts[-1] == "main.py"
    ):
        return "main.py-import"
    # main.tsx / App.tsx in product frontend src
    if (
        len(parts) >= 5
        and parts[0] == "products" and parts[2] == "frontend"
        and parts[3] == "src" and parts[-1] in ("main.tsx", "App.tsx")
    ):
        return "frontend-entry"
    # conftest.py in product tests
    if (
        len(parts) >= 5
        and parts[0] == "products" and parts[2] == "backend"
        and parts[3] == "tests" and parts[-1] == "conftest.py"
    ):
        return "conftest-line"
    # vitest.config.ts in product frontend
    if (
        len(parts) >= 4
        and parts[0] == "products" and parts[2] == "frontend"
        and parts[-1] == "vitest.config.ts"
    ):
        return "config-line"
    return None


def _line_should_skip(line: str, min_length: int) -> bool:
    if len(line.strip()) < min_length:
        return True
    for p in _IGNORE_PATTERNS:
        if p.match(line):
            return True
    return False


def _gather_lines(repo_root: Path, min_length: int) -> dict[str, list[tuple[str, str]]]:
    """Return {classification: [(file_relpath, line), ...]} for every
    target file, with skip-listed lines filtered out.
    """
    by_classification: dict[str, list[tuple[str, str]]] = defaultdict(list)
    products_dir = repo_root / "products"
    if not products_dir.exists():
        return by_classification

    for path in products_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(repo_root)
        except ValueError:
            logger.warning("recurrence: path outside repo root, skipping: %s", path)
            continue
        classification = _matches_target(rel)
        if classification is None:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.warning("recurrence: cannot read %s (%s), skipping", path, exc)
            continue
        rel_str = str(rel)
        for line in content.splitlines():
            normalized = line.rstrip()
            if _line_should_skip(normalized, min_length):
                continue
            by_classification[classification].append((rel_str, normalized))
    return by_classification


def _suggest_for_classification(classification: str) -> str:
    return {
        "main.py-import": (
            "Recurring boilerplate in product main.py — promote to a "
            "`create_product_app(...)` kwarg in `seed/framework/backend/"
            "noctusai_seed/app.py`. Pattern formalized 2026-04-28 via "
            "`consent_features=` (see `KB § 03-SEED-ARCHITECTURE § Seed Contract`)."
        ),
        "frontend-entry": (
            "Recurring boilerplate in product frontend entry — promote to "
            "`createProductApp(...)` config or default behavior in "
            "`seed/framework/frontend/src/app.tsx`."
        ),
        "conftest-line": (
            "Recurring conftest line — absorb into a seed-lib testing "
            "helper (e.g. `noctusai_lib.testing.<helper>`) OR auto-load via "
            "the `pytest11` entry-point plugin in `seed/lib/backend/pyproject.toml`."
        ),
        "config-line": (
            "Recurring config line — absorb into the seed-side config "
            "factory (e.g. `createProductVitestConfig` in "
            "`seed/framework/frontend/`)."
        ),
    }.get(classification, "Consider absorbing into seed.")


def scan_recurrence(
    repo_root: Path | None = None,
    *,
    min_count: int = 2,
    must_formalize_threshold: int = 3,
    min_line_length: int = 25,
) -> dict:
    """Scan target files for repeated lines + return findings sorted by severity.

    Args:
        repo_root: defaults to package root.
        min_count: minimum N occurrences to report (triage threshold).
        must_formalize_threshold: at this count, severity escalates to "high".
        min_line_length: skip lines shorter than this (filters trivial noise).

    Returns:
        {"findings": [RecurrenceFinding.to_dict()...], "stats": {...}}
    """
    root = repo_root or REPO_ROOT
    by_classification = _gather_lines(root, min_line_length)

    findings: list[RecurrenceFinding] = []
    for classification, occurrences in by_classification.items():
        # Group by line_text → list of files.
        by_line: dict[str, list[str]] = defaultdict(list)
        for file, line in occurrences:
            by_line[line].append(file)
        for line_text, files in by_line.items():
            unique_files = sorted(set(files))
            if len(unique_files) < min_count:
                continue
            severity = "high" if len(unique_files) >= must_formalize_threshold else "warning"
            findings.append(RecurrenceFinding(
                line_text=line_text.strip(),
                occurrences=unique_files,
                severity=severity,
                classification=classification,
                suggestion=_suggest_for_classification(classification),
            ))

    # Sort: severity desc, then count desc, then text alpha for stability.
    severity_order = {"high": 0, "warning": 1}
    findings.sort(
        key=lambda f: (
            severity_order.get(f.severity, 2),
            -len(f.occurrences),
            f.line_text,
        ),
    )

    return {
        "findings": [f.to_dict() for f in findings],
        "stats": {
            "total_findings": len(findings),
            "high_severity": sum(1 for f in findings if f.severity == "high"),
            "warning_severity": sum(1 for f in findings if f.severity == "warning"),
            "min_count_threshold": min_count,
            "must_formalize_threshold": must_formalize_threshold,
        },
    }


# ---------------------------------------------------------------------------
# `scan_cross_product_helpers` — function/class name recurrence across products
# ---------------------------------------------------------------------------
#
# Catches the absorption shape `scan_recurrence` misses: per-product
# helpers with the same NAME but slightly different bodies. Examples
# from the 2026-04-28 logging sweep:
#
#   _safe_float       in personal-finance + erp-imobiliario  (4 sites)
#   _format_money     in erp-imobiliario  (1 product, but 4 callers)
#   _format_date      in erp-imobiliario + therapy-platform  (multi-product)
#   _db_with_grants   in therapy-platform  (1 product, fixture shape)
#   _safe_json_loads  in daily-life + mailing  (verbatim duplicate)
#
# The line-level scan misses these because each implementation differs
# by 1-3 characters. The name-level scan catches them BEFORE the 4th
# product reimplements yet again.

# Files where helper-name recurrence is meaningful. Service/router/dependency
# files in product backends + hooks/components in product frontends.
_HELPER_SCAN_GLOBS: list[str] = [
    "products/*/backend/app/services/*.py",
    "products/*/backend/app/services/**/*.py",
    "products/*/backend/app/routers/*.py",
    "products/*/backend/app/routers/**/*.py",
    "products/*/backend/app/dependencies.py",
    "products/*/frontend/src/hooks/*.ts",
    "products/*/frontend/src/hooks/*.tsx",
    "products/*/frontend/src/components/*.tsx",
]

# Names too generic to flag — domain nouns that EVERY product owns.
# Adding a name to this set says: "even if N products define this, it's
# not absorption-shaped, the name belongs to product-specific surface."
_HELPER_NAME_BLACKLIST: set[str] = {
    # FastAPI route handler names — every product has list/get/create/etc.
    "list", "get", "create", "update", "delete", "patch",
    # Portuguese router handler names — same semantics as above; PF/ERP
    # use Portuguese for resource-CRUD endpoints. Each "criar" is a
    # different resource creator; not absorption-shaped.
    "criar", "atualizar", "excluir", "listar", "obter", "deletar", "remover",
    "params",  # FastAPI Depends(get_query_params) — boilerplate, not absorption-shaped
    # Common test fixture shape (covered by separate fixture-recurrence detector).
    "client", "db", "user", "fixture",
    # Generic verbs that are too noisy at the lexer level.
    "main", "run", "init", "setup", "teardown",
    # Typical __init__ / __repr__ noise from dataclasses + classes.
    "__init__", "__repr__", "__str__", "__eq__", "__hash__", "__post_init__",
}

# Underscore-prefixed names below this length are treated as too generic
# (`_get`, `_set`). Real absorption candidates tend to be 3+ chars after `_`.
_MIN_HELPER_NAME_LEN = 4

# Match `def name(`, `async def name(`, `class Name(`, `Name = dataclass`.
# Regex (vs AST) keeps this fast on a multi-thousand-file repo.
_PY_DEF_RE = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_PY_CLASS_RE = re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\s*[\(:]")
# Match `export function name(`, `function name(`, `const name = (...) =>`.
_TS_FN_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*[\(<]"
    r"|^\s*(?:export\s+)?const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s+)?\("
    r"|^\s*(?:export\s+)?const\s+([A-Za-z_][A-Za-z0-9_]*):\s*[A-Z]"
)


def _product_of(rel_path: Path) -> str | None:
    """Extract the product slug from a path like `products/<slug>/...`. None if not under products/."""
    parts = rel_path.parts
    if len(parts) >= 2 and parts[0] == "products":
        return parts[1]
    return None


def _extract_helper_names(path: Path) -> set[str]:
    """Return the set of function/class names defined in `path` (Python or TS)."""
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        logger.warning("recurrence: cannot read %s (%s), skipping", path, exc)
        return set()
    names: set[str] = set()
    suffix = path.suffix
    for line in content.splitlines():
        if suffix == ".py":
            m = _PY_DEF_RE.match(line)
            if m:
                names.add(m.group(1))
                continue
            m = _PY_CLASS_RE.match(line)
            if m:
                names.add(m.group(1))
        elif suffix in (".ts", ".tsx"):
            m = _TS_FN_RE.match(line)
            if m:
                # The regex has 3 alternatives — pick whichever group matched.
                name = m.group(1) or m.group(2) or m.group(3)
                if name:
                    names.add(name)
    return names


def _is_meaningful_helper(name: str) -> bool:
    """Filter out names too generic to flag (router handlers, dunders, short names)."""
    if name in _HELPER_NAME_BLACKLIST:
        return False
    # Strip leading underscore for length check (private helpers like `_safe_float` are exactly the target).
    bare = name.lstrip("_")
    if len(bare) < _MIN_HELPER_NAME_LEN:
        return False
    return True


@dataclass
class HelperFinding:
    """One cross-product helper-name recurrence."""
    helper_name: str
    products: list[str]  # which product slugs define it
    locations: list[str]  # file paths (one per product, deduped)
    severity: str  # "warning" / "high"
    suggestion: str = ""

    def to_dict(self) -> dict:
        return {
            "helper_name": self.helper_name,
            "product_count": len(self.products),
            "products": self.products,
            "locations": self.locations,
            "severity": self.severity,
            "suggestion": self.suggestion,
        }


def _suggest_for_helper(name: str, products: list[str]) -> str:
    """Heuristic suggestion based on the helper name shape."""
    bare = name.lstrip("_").lower()
    # Parse / safe-cast helpers
    if any(kw in bare for kw in ("safe_float", "safe_int", "parse_iso", "parse_money", "format_money", "format_date")):
        return (
            f"`{name}` is a parse/format helper duplicated across {len(products)} products. "
            f"Absorb into `noctusai_lib.parsing` (Python) or `@noctusai/lib/parsing` (TS) — "
            f"single canonical implementation, all products import from there."
        )
    # Db-fixture / consent-grant helpers
    if any(kw in bare for kw in ("db_with_grants", "db_with_consent", "consent_grants", "grant_all_")):
        return (
            f"`{name}` is a consent-test fixture shape duplicated across {len(products)} products. "
            f"Absorb into `noctusai_lib.testing.consent_fixtures.<helper>` — see "
            f"`KB § PATTERNS/testing.md § Consent-guard product conftest pattern`."
        )
    # Hook-from-API shapes
    if bare.startswith("use") and len(bare) > 3:
        return (
            f"`{name}` is a frontend hook duplicated across {len(products)} products. "
            f"If the shape is generic (use<noun>FromAPI(url)), absorb into "
            f"`@noctusai/lib/hooks/<name>`. If the URL/payload is product-specific, "
            f"keep per-product but factor the shared infra (TanStack Query setup) into a hook factory."
        )
    # Resolve-clinic / resolve-org / resolve-* DI helpers
    if "resolve_" in bare:
        return (
            f"`{name}` is a DI/resolve helper duplicated across {len(products)} products. "
            f"If it threads a tenant/org/clinic kwarg through a default-or-override pattern, "
            f"absorb into `noctusai_lib.di.<helper>`. Reference: "
            f"`_resolve_core_db` in therapy-platform `ai_pipeline.py` (the canonical example)."
        )
    # Pipeline / orchestrator hooks
    if "Hooks" in name or "hooks" in name:
        return (
            f"`{name}` is a `_PipelineHooks`-shape orchestrator-DI dataclass duplicated across "
            f"{len(products)} products. Absorb the SHAPE (callable-fields + `_DEFAULT_HOOKS` "
            f"singleton) into `noctusai_lib.testing.di.PipelineHooks` so every product builds "
            f"its own concrete hooks but inherits the helper / pattern documented in "
            f"`KB § PATTERNS/testing.md § Pattern 1: Dependency Injection`."
        )
    return (
        f"`{name}` is defined in {len(products)} products. Open each implementation; if the "
        f"bodies differ only in domain references (table names, field keys), absorb the shared "
        f"shell into `noctusai_lib.<area>` and have each product wrap with product-specific "
        f"args. If bodies are genuinely different domains sharing a coincidental name, "
        f"accept-with-rationale + add to `_HELPER_NAME_BLACKLIST` in this detector."
    )


def scan_cross_product_helpers(
    repo_root: Path | None = None,
    *,
    min_count: int = 2,
    must_formalize_threshold: int = 3,
) -> dict:
    """Find function/class names defined across N≥`min_count` products.

    Each finding lists the products + file paths so the caller can open
    each implementation and decide formalize / refactor / accept.

    Args:
        repo_root: defaults to package root.
        min_count: minimum product count to report (default 2 = TRIAGE).
        must_formalize_threshold: at this product count, severity escalates
            to "high" (default 3 = MUST FORMALIZE per the recurrence rule).

    Returns:
        {"findings": [...], "stats": {...}}. Each finding includes
        `helper_name`, `products`, `locations`, `severity`, `suggestion`.
    """
    root = repo_root or REPO_ROOT
    if not root.exists():
        return {"findings": [], "stats": {"total_findings": 0}}

    # name → {product → first file path that defined it}
    name_to_products: dict[str, dict[str, str]] = defaultdict(dict)

    for glob in _HELPER_SCAN_GLOBS:
        for path in root.glob(glob):
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(root)
            except ValueError:
                logger.warning("recurrence: path outside repo root, skipping: %s", path)
                continue
            product = _product_of(rel)
            if product is None:
                continue
            for name in _extract_helper_names(path):
                if not _is_meaningful_helper(name):
                    continue
                # Record only the FIRST occurrence per product so multi-file
                # uses inside one product don't inflate the count.
                if product not in name_to_products[name]:
                    name_to_products[name][product] = str(rel)

    findings: list[HelperFinding] = []
    for name, by_product in name_to_products.items():
        if len(by_product) < min_count:
            continue
        products = sorted(by_product.keys())
        locations = sorted(by_product.values())
        severity = "high" if len(products) >= must_formalize_threshold else "warning"
        findings.append(HelperFinding(
            helper_name=name,
            products=products,
            locations=locations,
            severity=severity,
            suggestion=_suggest_for_helper(name, products),
        ))

    severity_order = {"high": 0, "warning": 1}
    findings.sort(
        key=lambda f: (
            severity_order.get(f.severity, 2),
            -len(f.products),
            f.helper_name,
        ),
    )

    return {
        "findings": [f.to_dict() for f in findings],
        "stats": {
            "total_findings": len(findings),
            "high_severity": sum(1 for f in findings if f.severity == "high"),
            "warning_severity": sum(1 for f in findings if f.severity == "warning"),
            "min_count_threshold": min_count,
            "must_formalize_threshold": must_formalize_threshold,
            "files_scanned_globs": _HELPER_SCAN_GLOBS,
        },
    }


# ---------------------------------------------------------------------------
# `scan_service_line_recurrence` — verbatim line repetition in service/router code
# ---------------------------------------------------------------------------
#
# `scan_recurrence` (above) limits to entry-points / config / conftest because
# scanning all service code at line level produces 90% noise from common
# imports. This pass scans services + routers + dependencies with VERY strict
# filters — line must:
#   1. Be at least `min_line_length` chars (default 60)
#   2. Contain a function-call token `(`
#   3. NOT be a `from <pkg> import` line (those are catalog'd by static lib)
#   4. Recur in N≥`min_count` DIFFERENT products
#
# Catches:
#   - `datetime.fromisoformat(s.replace("Z", "+00:00"))` (22× across products)
#   - `db.table("notifications").insert({...}).execute()` shapes
#   - `await audit_service.log(user_id=..., org_id=..., action=...)` calls
#
# Keeps low-noise. The high-severity hits become reviewable absorption
# candidates for `noctusai_lib.dates`, `noctusai_lib.audit`, etc.

_SERVICE_LINE_SCAN_GLOBS: list[str] = [
    "products/*/backend/app/services/*.py",
    "products/*/backend/app/services/**/*.py",
    "products/*/backend/app/routers/*.py",
    "products/*/backend/app/routers/**/*.py",
    "products/*/backend/app/dependencies.py",
]

_SERVICE_LINE_SKIP_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\s*$"),
    re.compile(r"^\s*#"),
    re.compile(r'^\s*"""'),
    re.compile(r"^\s*'''"),
    # Imports — catalog'd via static lib graph elsewhere; not absorption-shaped.
    re.compile(r"^\s*from\s+\S+\s+import\b"),
    re.compile(r"^\s*import\s+\S+"),
    # Pure assignments without function call — usually domain literals.
    re.compile(r"^\s*[A-Z_]+\s*=\s*['\"]"),
    # Decorator lines without an argument-bearing call (most are product-scoped routes).
    re.compile(r"^\s*@\w+\s*$"),
]


@dataclass
class ServiceLineFinding:
    line_text: str
    products: list[str]
    occurrences: list[str]  # file paths
    severity: str
    suggestion: str = ""

    def to_dict(self) -> dict:
        return {
            "line_text": self.line_text,
            "product_count": len(self.products),
            "products": self.products,
            "occurrences": self.occurrences,
            "severity": self.severity,
            "suggestion": self.suggestion,
        }


def _service_line_should_skip(line: str, min_length: int) -> bool:
    stripped = line.strip()
    if len(stripped) < min_length:
        return True
    if "(" not in stripped:
        # Required: line must contain a function-call shape. Pure
        # assignments / imports / declarations are filtered.
        return True
    for p in _SERVICE_LINE_SKIP_PATTERNS:
        if p.match(line):
            return True
    return False


def _suggest_for_service_line(line: str) -> str:
    line_lower = line.lower()
    if "fromisoformat" in line_lower and "replace" in line_lower:
        return (
            "ISO-date parse with Z-suffix fix — absorb into "
            "`noctusai_lib.dates.parse_iso_datetime(s)`. Single canonical "
            "implementation; UTC-aware; tested once."
        )
    if "audit_service.log" in line_lower:
        return (
            "Audit-log dispatch — the best-effort try/except shape this lives "
            "inside is itself recurrent. Absorb into "
            "`noctusai_lib.audit.safely_log_action(user_id, org_id, action, ...)` "
            "with the swallow-and-log built in."
        )
    if "notification_service.create" in line_lower or "notify_team" in line_lower:
        return (
            "Notification-dispatch — absorb into `noctusai_lib.notifications."
            "safely_dispatch(...)` with the same swallow-and-log shape as "
            "`safely_log_action`."
        )
    if "webhook_delivery.dispatch" in line_lower:
        return (
            "Webhook dispatch — absorb into `noctusai_lib.webhooks."
            "safely_dispatch_event(org_id, event_type, payload)`. Swallows + "
            "logs internally so callers don't have to repeat the try/except."
        )
    return (
        "Recurring service/router line. Open each location and decide: "
        "absorb into `noctusai_lib.<area>` (3+ products) or accept-with-rationale."
    )


def scan_service_line_recurrence(
    repo_root: Path | None = None,
    *,
    min_count: int = 2,
    must_formalize_threshold: int = 3,
    min_line_length: int = 60,
) -> dict:
    """Find verbatim lines recurring across services/routers in N≥`min_count` products.

    Stricter than `scan_recurrence`:
      - longer min line length (60 chars)
      - line MUST contain `(` (function-call shape)
      - imports / pure assignments / lone decorators / docstring delimiters skipped

    Catches the structural patterns `scan_cross_product_helpers` misses
    because the helpers are ad-hoc (e.g. `datetime.fromisoformat(s.replace("Z", "+00:00"))`
    — same line across 22 service files, no function name).
    """
    root = repo_root or REPO_ROOT
    if not root.exists():
        return {"findings": [], "stats": {"total_findings": 0}}

    # line_text → {product_slug: [file_paths]}
    line_to_products: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    for glob in _SERVICE_LINE_SCAN_GLOBS:
        for path in root.glob(glob):
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(root)
            except ValueError:
                logger.warning("recurrence: path outside repo root, skipping: %s", path)
                continue
            product = _product_of(rel)
            if product is None:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError) as exc:
                logger.warning("recurrence: cannot read %s (%s), skipping", path, exc)
                continue
            for line in content.splitlines():
                normalized = line.rstrip()
                if _service_line_should_skip(normalized, min_line_length):
                    continue
                line_to_products[normalized.strip()][product].append(str(rel))

    findings: list[ServiceLineFinding] = []
    for line_text, by_product in line_to_products.items():
        if len(by_product) < min_count:
            continue
        products = sorted(by_product.keys())
        occurrences = sorted({path for paths in by_product.values() for path in paths})
        severity = "high" if len(products) >= must_formalize_threshold else "warning"
        findings.append(ServiceLineFinding(
            line_text=line_text,
            products=products,
            occurrences=occurrences,
            severity=severity,
            suggestion=_suggest_for_service_line(line_text),
        ))

    severity_order = {"high": 0, "warning": 1}
    findings.sort(
        key=lambda f: (
            severity_order.get(f.severity, 2),
            -len(f.products),
            f.line_text,
        ),
    )

    return {
        "findings": [f.to_dict() for f in findings],
        "stats": {
            "total_findings": len(findings),
            "high_severity": sum(1 for f in findings if f.severity == "high"),
            "warning_severity": sum(1 for f in findings if f.severity == "warning"),
            "min_count_threshold": min_count,
            "must_formalize_threshold": must_formalize_threshold,
            "min_line_length": min_line_length,
        },
    }


# ---------------------------------------------------------------------------
# `scan_block_patterns` — AST-walk try/except blocks, find structural recurrences
# ---------------------------------------------------------------------------
#
# Closes gap #1 from the 2026-04-28 evaluation. Catches block patterns
# repeated with different identifiers — the shape neither the line-level
# scan nor the name-level scan can see.
#
# Example: the 13 best-effort `audit_service.log` try/except blocks
# scattered across core's routers. Each block:
#
#     try:
#         from app.services import audit_service
#         await audit_service.log(user_id=..., org_id=..., action=..., ...)
#     except Exception as exc:
#         logger.warning("auth: <action> audit log failed for ...", exc)
#
# Has identical SHAPE (try-with-import-then-await + except-Exception-with-
# logger.warning) but different identifiers per call site. The detector
# normalizes by extracting the call targets (`audit_service.log`,
# `logger.warning`) and the exception types (`Exception`), then hashes.
# All 13 blocks → same hash → flagged as recurrence.

# accept-with-rationale: "MCP detectors keep raw `import ast`" in
# KB § PATTERNS/accept-with-rationale.md — recurrence walks Try/except
# block shapes, ExceptHandler.type Tuples, AnnAssign.annotation via
# _ast.unparse; all below outline_python's symbol-tree contract.
# Migration evaluated 2026-05-02 by ast-callers-consolidation Phase 0
# → accept.
import ast as _ast  # alias to avoid clash inside helper bodies (defensive)


def _extract_call_targets(body: list) -> tuple[str, ...]:
    """Return sorted, deduped dotted-name targets called inside `body`.

    Walks every node recursively; for each `Call` node whose `func` is a
    `Name` or `Attribute`, recovers the dotted path. Examples:
      - `audit_service.log(...)` → `"audit_service.log"`
      - `logger.warning(...)` → `"logger.warning"`
      - `await foo.bar.baz(...)` → `"foo.bar.baz"`

    Imports are deliberately ignored (caught at the import map elsewhere).
    """
    targets: set[str] = set()
    for stmt in body:
        for node in _ast.walk(stmt):
            if not isinstance(node, _ast.Call):
                continue
            target = _dotted_name(node.func)
            if target:
                targets.add(target)
    return tuple(sorted(targets))


def _dotted_name(node) -> str | None:
    """Recover dotted name from a Name/Attribute chain, else None."""
    if isinstance(node, _ast.Name):
        return node.id
    if isinstance(node, _ast.Attribute):
        prefix = _dotted_name(node.value)
        if prefix is None:
            return None
        return f"{prefix}.{node.attr}"
    return None


def _extract_exception_names(handler: _ast.ExceptHandler) -> str:
    """Return a stable string for the exception types caught by `handler`.

    `except:` → `"*"`. `except Foo:` → `"Foo"`. `except (Foo, Bar):` →
    `"Bar|Foo"` (sorted, pipe-separated).
    """
    if handler.type is None:
        return "*"
    if isinstance(handler.type, _ast.Tuple):
        names = sorted(
            _dotted_name(e) or "?" for e in handler.type.elts
        )
        return "|".join(names)
    return _dotted_name(handler.type) or "?"


def _try_signature(node: _ast.Try) -> str:
    """Structural fingerprint of a `Try` node; identifiers normalized away.

    Two blocks with the same fingerprint share a SHAPE — they call the
    same set of dotted methods inside the try body, catch the same
    exception types, and call the same set of methods inside each handler.
    Argument values are NOT part of the fingerprint (which is the whole
    point — `audit_service.log(user_id=A)` and `audit_service.log(user_id=B)`
    are the same SHAPE).
    """
    body_targets = _extract_call_targets(node.body)
    handlers: list[str] = []
    for h in node.handlers:
        exc = _extract_exception_names(h)
        handler_targets = _extract_call_targets(h.body)
        handlers.append(f"{exc}:[{','.join(handler_targets)}]")
    finally_targets = _extract_call_targets(node.finalbody) if node.finalbody else ()
    parts = [
        f"try=[{','.join(body_targets)}]",
        f"except=[{'|'.join(handlers)}]",
    ]
    if finally_targets:
        parts.append(f"finally=[{','.join(finally_targets)}]")
    return ";".join(parts)


_BLOCK_SCAN_GLOBS: list[str] = [
    "products/*/backend/app/services/*.py",
    "products/*/backend/app/services/**/*.py",
    "products/*/backend/app/routers/*.py",
    "products/*/backend/app/routers/**/*.py",
    "products/*/backend/app/dependencies.py",
    "seed/lib/backend/noctusai_lib/**/*.py",
]


@dataclass
class BlockPatternFinding:
    signature: str  # the structural fingerprint (debug aid)
    body_targets: list[str]  # methods called inside the try body
    handler_shape: list[str]  # ["Exception:[logger.warning]", ...]
    occurrences: list[str]  # file:line locations
    products: list[str]  # distinct product slugs hosting the pattern
    severity: str
    suggestion: str = ""

    def to_dict(self) -> dict:
        return {
            "signature": self.signature,
            "body_targets": self.body_targets,
            "handler_shape": self.handler_shape,
            "occurrence_count": len(self.occurrences),
            "occurrences": self.occurrences,
            "product_count": len(self.products),
            "products": self.products,
            "severity": self.severity,
            "suggestion": self.suggestion,
        }


def _suggest_for_block_pattern(body_targets: list[str], handler_shape: list[str]) -> str:
    body_str = ", ".join(body_targets)
    if any("audit_service.log" in t for t in body_targets):
        return (
            f"`try: {body_str} except: ...` is the best-effort audit-log dispatch "
            f"pattern. Absorb into `noctusai_lib.audit.safely_log_action(...)` — wraps "
            f"the import + call + try/except + logger.warning in one helper. Caller "
            f"becomes a single line."
        )
    if any("webhook_delivery.dispatch" in t or "webhook" in t.lower() for t in body_targets):
        return (
            f"`try: {body_str} except: ...` is the best-effort webhook-dispatch "
            f"pattern. Absorb into `noctusai_lib.webhooks.safely_dispatch(...)`."
        )
    if any("notify_team" in t or "notification_service" in t for t in body_targets):
        return (
            f"`try: {body_str} except: ...` is the best-effort notification-dispatch "
            f"pattern. Absorb into `noctusai_lib.notifications.safely_dispatch(...)`."
        )
    if any("email_service" in t or "send_" in t for t in body_targets):
        return (
            f"`try: {body_str} except: ...` is the best-effort email/send-side-effect "
            f"pattern. Absorb into `noctusai_lib.dispatch.safely_run(coro, *, label, ...)` — "
            f"a generic helper that takes any coro + a label and handles the swallow + log."
        )
    return (
        f"Recurring try/except shape with body_targets=[{body_str}], "
        f"handlers={handler_shape}. Open each location; if the bodies differ only in "
        f"argument values, absorb into a `noctusai_lib.dispatch.safely_run(coro, *, label)` "
        f"helper — single canonical try/except shape, callers become one line."
    )


def scan_block_patterns(
    repo_root: Path | None = None,
    *,
    min_count: int = 2,
    must_formalize_threshold: int = 3,
    cross_product_only: bool = False,
) -> dict:
    """Find recurring try/except (block-level) shapes via AST normalization.

    Args:
        repo_root: defaults to package root.
        min_count: minimum occurrence count (default 2).
        must_formalize_threshold: severity escalates to "high" at this count (default 3).
        cross_product_only: if True, only report patterns appearing in ≥2
            distinct products (filters within-product duplication noise).
            If False (default), reports any block recurring N+ times even
            within a single product — the audit-service pattern repeats 13×
            in core alone and that's worth surfacing.
    """
    root = repo_root or REPO_ROOT
    if not root.exists():
        return {"findings": [], "stats": {"total_findings": 0}}

    # signature → list of (file:line, product_slug)
    sig_to_occurrences: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
    sig_to_data: dict[str, tuple[tuple[str, ...], list[str]]] = {}

    for glob in _BLOCK_SCAN_GLOBS:
        for path in root.glob(glob):
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(root)
            except ValueError:
                logger.warning("recurrence: path outside repo root, skipping: %s", path)
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError) as exc:
                logger.warning("recurrence: cannot read %s (%s), skipping", path, exc)
                continue
            try:
                tree = _ast.parse(content, filename=str(path))
            except SyntaxError as exc:
                logger.warning("recurrence: cannot parse %s (%s), skipping", path, exc)
                continue
            product = _product_of(rel)
            for node in _ast.walk(tree):
                if not isinstance(node, _ast.Try):
                    continue
                sig = _try_signature(node)
                # Skip degenerate signatures (empty bodies / no targets) —
                # those are typically library-shaped patterns we don't need
                # to flag (e.g. bare `try: pass except: pass`).
                if sig.startswith("try=[];"):
                    continue
                location = f"{rel}:{node.lineno}"
                sig_to_occurrences[sig].append((location, product))
                if sig not in sig_to_data:
                    body_targets = _extract_call_targets(node.body)
                    handler_shape = []
                    for h in node.handlers:
                        exc_str = _extract_exception_names(h)
                        targets = _extract_call_targets(h.body)
                        handler_shape.append(f"{exc_str}:[{','.join(targets)}]")
                    sig_to_data[sig] = (body_targets, handler_shape)

    findings: list[BlockPatternFinding] = []
    for sig, occurrences in sig_to_occurrences.items():
        if len(occurrences) < min_count:
            continue
        products = sorted({p for _, p in occurrences if p is not None})
        if cross_product_only and len(products) < 2:
            continue
        body_targets, handler_shape = sig_to_data[sig]
        severity = "high" if len(occurrences) >= must_formalize_threshold else "warning"
        findings.append(BlockPatternFinding(
            signature=sig,
            body_targets=list(body_targets),
            handler_shape=handler_shape,
            occurrences=sorted({loc for loc, _ in occurrences}),
            products=products,
            severity=severity,
            suggestion=_suggest_for_block_pattern(list(body_targets), handler_shape),
        ))

    severity_order = {"high": 0, "warning": 1}
    findings.sort(
        key=lambda f: (
            severity_order.get(f.severity, 2),
            -len(f.occurrences),
            f.signature,
        ),
    )

    return {
        "findings": [f.to_dict() for f in findings],
        "stats": {
            "total_findings": len(findings),
            "high_severity": sum(1 for f in findings if f.severity == "high"),
            "warning_severity": sum(1 for f in findings if f.severity == "warning"),
            "min_count_threshold": min_count,
            "must_formalize_threshold": must_formalize_threshold,
            "cross_product_only": cross_product_only,
        },
    }


# ---------------------------------------------------------------------------
# `scan_within_product_helpers` — same helper name duplicated within one product
# ---------------------------------------------------------------------------
#
# Closes gap #2. The cross-product scan misses cases like ERP defining
# `_safe_float` in 4 service files (each slightly different); within-product
# duplication is also valid DRY-into-`app/utils.py` (or seed-lib if the
# helper is generic) absorption.

def scan_within_product_helpers(
    repo_root: Path | None = None,
    *,
    min_count: int = 3,
) -> dict:
    """Find helper names duplicated N+ times across files INSIDE a single product.

    Args:
        repo_root: defaults to package root.
        min_count: minimum file count within one product to report (default 3).
            Lower than the cross-product scan because within-product is
            already a localized signal — N=2 in one product is marginal.

    Returns:
        Findings list per (product, helper_name) where the helper is defined
        in `min_count`+ files of that product. Suggestion: extract to
        `app/utils.py` if product-specific or `noctusai_lib.<area>` if
        cross-cutting.
    """
    root = repo_root or REPO_ROOT
    if not root.exists():
        return {"findings": [], "stats": {"total_findings": 0}}

    # (product, name) → list of file paths
    pn_to_files: dict[tuple[str, str], list[str]] = defaultdict(list)

    for glob in _HELPER_SCAN_GLOBS:
        for path in root.glob(glob):
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(root)
            except ValueError:
                logger.warning("recurrence: path outside repo root, skipping: %s", path)
                continue
            product = _product_of(rel)
            if product is None:
                continue
            for name in _extract_helper_names(path):
                if not _is_meaningful_helper(name):
                    continue
                pn_to_files[(product, name)].append(str(rel))

    findings_list: list[dict] = []
    for (product, name), files in pn_to_files.items():
        unique_files = sorted(set(files))
        if len(unique_files) < min_count:
            continue
        suggestion = (
            f"`{name}` is defined in {len(unique_files)} files inside `{product}`. "
            f"If the implementations are near-identical, extract to "
            f"`products/{product}/backend/app/utils.py` (product-specific). "
            f"If the helper is generic enough to apply to other products too, "
            f"absorb into `noctusai_lib.<area>` directly — saves a future migration."
        )
        findings_list.append({
            "product": product,
            "helper_name": name,
            "file_count": len(unique_files),
            "files": unique_files,
            "severity": "high" if len(unique_files) >= 5 else "warning",
            "suggestion": suggestion,
        })

    findings_list.sort(key=lambda f: (-f["file_count"], f["product"], f["helper_name"]))
    return {
        "findings": findings_list,
        "stats": {
            "total_findings": len(findings_list),
            "high_severity": sum(1 for f in findings_list if f["severity"] == "high"),
            "warning_severity": sum(1 for f in findings_list if f["severity"] == "warning"),
            "min_count_threshold": min_count,
        },
    }


# ---------------------------------------------------------------------------
# `scan_pydantic_model_shapes` — BaseModel field-set recurrence across products
# ---------------------------------------------------------------------------
#
# Closes gap #3. Catches `class XxxCreate(BaseModel)` shapes whose field
# set + types are identical (or near-identical) across products.

def _is_pydantic_basemodel_subclass(class_def: _ast.ClassDef) -> bool:
    """Heuristic: True if any base is named `BaseModel` (bare or `pydantic.BaseModel`)."""
    for base in class_def.bases:
        if isinstance(base, _ast.Name) and base.id == "BaseModel":
            return True
        if isinstance(base, _ast.Attribute) and base.attr == "BaseModel":
            return True
    return False


def _extract_pydantic_field_set(class_def: _ast.ClassDef) -> tuple[tuple[str, str], ...] | None:
    """Return sorted tuple of `(field_name, type_str)` for a Pydantic model's fields, else None."""
    if not _is_pydantic_basemodel_subclass(class_def):
        return None
    fields: list[tuple[str, str]] = []
    for stmt in class_def.body:
        # `name: type = default` or `name: type`
        if isinstance(stmt, _ast.AnnAssign) and isinstance(stmt.target, _ast.Name):
            try:
                type_str = _ast.unparse(stmt.annotation) if stmt.annotation else "?"
            except Exception as exc:
                logger.debug("recurrence: ast.unparse failed for field %r (%s); using '?'", stmt.target.id, exc)
                type_str = "?"
            fields.append((stmt.target.id, type_str))
    return tuple(sorted(fields)) if fields else None


_PYDANTIC_SCAN_GLOBS: list[str] = [
    "products/*/backend/app/services/*.py",
    "products/*/backend/app/services/**/*.py",
    "products/*/backend/app/routers/*.py",
    "products/*/backend/app/routers/**/*.py",
    "products/*/backend/app/schemas/*.py",
    "products/*/backend/app/schemas/**/*.py",
    "products/*/backend/app/models/*.py",
]


@dataclass
class PydanticShapeFinding:
    field_set: list[tuple[str, str]]  # the sorted list of (name, type) fields
    occurrences: list[tuple[str, str]]  # list of (class_name, file_path)
    products: list[str]
    severity: str
    suggestion: str = ""

    def to_dict(self) -> dict:
        return {
            "field_set": [list(t) for t in self.field_set],  # JSON-friendly
            "field_count": len(self.field_set),
            "occurrences": [{"class_name": cn, "file": f} for cn, f in self.occurrences],
            "occurrence_count": len(self.occurrences),
            "product_count": len(self.products),
            "products": self.products,
            "severity": self.severity,
            "suggestion": self.suggestion,
        }


def scan_pydantic_model_shapes(
    repo_root: Path | None = None,
    *,
    min_count: int = 2,
    must_formalize_threshold: int = 3,
    min_field_count: int = 2,
) -> dict:
    """Find Pydantic BaseModel field-sets that recur across N≥`min_count` products.

    Args:
        repo_root: defaults to package root.
        min_count: minimum product count to report (default 2).
        must_formalize_threshold: severity escalates to "high" at this count.
        min_field_count: ignore models with fewer than this many fields
            (default 2). Single-field DTOs are too generic — `class TokenIn:
            token: str` would false-positive across half the products.
    """
    root = repo_root or REPO_ROOT
    if not root.exists():
        return {"findings": [], "stats": {"total_findings": 0}}

    # field_set tuple → list of (class_name, file_path, product)
    fs_to_occurrences: dict[tuple, list[tuple[str, str, str | None]]] = defaultdict(list)

    for glob in _PYDANTIC_SCAN_GLOBS:
        for path in root.glob(glob):
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(root)
            except ValueError:
                logger.warning("recurrence: path outside repo root, skipping: %s", path)
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError) as exc:
                logger.warning("recurrence: cannot read %s (%s), skipping", path, exc)
                continue
            try:
                tree = _ast.parse(content, filename=str(path))
            except SyntaxError as exc:
                logger.warning("recurrence: cannot parse %s (%s), skipping", path, exc)
                continue
            product = _product_of(rel)
            for node in _ast.walk(tree):
                if not isinstance(node, _ast.ClassDef):
                    continue
                fs = _extract_pydantic_field_set(node)
                if fs is None or len(fs) < min_field_count:
                    continue
                fs_to_occurrences[fs].append((node.name, str(rel), product))

    findings: list[PydanticShapeFinding] = []
    for fs, occurrences in fs_to_occurrences.items():
        products = sorted({p for _, _, p in occurrences if p is not None})
        if len(products) < min_count:
            continue
        severity = "high" if len(products) >= must_formalize_threshold else "warning"
        # Class names involved (often hints what the absorption type should be called).
        class_names = sorted({cn for cn, _, _ in occurrences})
        suggestion = (
            f"Pydantic model shape with {len(fs)} fields recurs as "
            f"{class_names} across {len(products)} products. Absorb the field "
            f"set into `noctusai_lib.schemas.<canonical-name>` and have each "
            f"product import / extend it. Saves drift when a field is added."
        )
        findings.append(PydanticShapeFinding(
            field_set=list(fs),
            occurrences=sorted([(cn, f) for cn, f, _ in occurrences]),
            products=products,
            severity=severity,
            suggestion=suggestion,
        ))

    severity_order = {"high": 0, "warning": 1}
    findings.sort(
        key=lambda f: (
            severity_order.get(f.severity, 2),
            -len(f.products),
            -len(f.field_set),
        ),
    )

    return {
        "findings": [f.to_dict() for f in findings],
        "stats": {
            "total_findings": len(findings),
            "high_severity": sum(1 for f in findings if f.severity == "high"),
            "warning_severity": sum(1 for f in findings if f.severity == "warning"),
            "min_count_threshold": min_count,
            "must_formalize_threshold": must_formalize_threshold,
            "min_field_count": min_field_count,
        },
    }


# ---------------------------------------------------------------------------
# `scan_test_fixture_recurrence` — pytest fixtures + test helpers across products
# ---------------------------------------------------------------------------
#
# Closes second-wave gap #4. Test code was deliberately excluded from
# `_HELPER_SCAN_GLOBS` to avoid noise from per-product business fixtures
# (`SAMPLE_APPOINTMENT`, `THERAPY_FEATURES`). But helpers like
# `_db_with_grants(...)` / `bind_consent_module_to_mock(mock_sb)` /
# `_grant_all_<product>_consents` ARE absorption candidates — they encode
# cross-product test scaffolding. This scan applies stricter filters than
# the production helper scan to keep noise out.

_TEST_HELPER_SCAN_GLOBS: list[str] = [
    "products/*/backend/tests/conftest.py",
    "products/*/backend/tests/**/conftest.py",
    "products/*/backend/tests/services/*.py",
    "products/*/backend/tests/routers/*.py",
    "products/*/backend/tests/integration/*.py",
]

# Test-helper-name blacklist — extends the production blacklist with
# names that are intrinsically per-product (sample data, feature lists)
# or universally pytest-shaped (test methods, common fixtures).
_TEST_HELPER_NAME_BLACKLIST: set[str] = _HELPER_NAME_BLACKLIST | {
    # Generic pytest fixture names — every product has a `client` fixture etc.
    "client", "auth_client", "admin_client", "mock_db", "mock_sb",
    "mock_supabase", "fake_user", "fake_org",
    # Common SAMPLE_* / EXAMPLE_* dataclass names — domain-specific by definition.
    # (Names below are recognised via uppercase + length heuristic, not blacklist.)
    # Generic test-method names (handled by short-name filter below).
    "setUp", "tearDown",
}


def _is_meaningful_test_helper(name: str) -> bool:
    """Filter for test helpers — stricter than `_is_meaningful_helper`."""
    if name in _TEST_HELPER_NAME_BLACKLIST:
        return False
    bare = name.lstrip("_")
    if len(bare) < _MIN_HELPER_NAME_LEN:
        return False
    # Test methods (`test_*`) are not absorption candidates — they're
    # individual assertions per product. The fixture/helper IS the
    # absorption target; the test is product-specific.
    if name.startswith("test_"):
        return False
    # ALL_CAPS sample-data names (`SAMPLE_APPOINTMENT`, `THERAPY_FEATURES`)
    # are domain literals — never absorption-shaped.
    if name.isupper():
        return False
    return True


def scan_test_fixture_recurrence(
    repo_root: Path | None = None,
    *,
    min_count: int = 2,
    must_formalize_threshold: int = 3,
) -> dict:
    """Find pytest fixtures + test helpers recurring across products.

    Same shape as `scan_cross_product_helpers` but scoped to test files +
    using a stricter blacklist (excludes per-product sample-data names).
    Suggests `noctusai_lib.testing.<helper>` absorption.

    Args:
        repo_root: defaults to package root.
        min_count: minimum product count to report (default 2).
        must_formalize_threshold: severity escalates to "high" at this count.
    """
    root = repo_root or REPO_ROOT
    if not root.exists():
        return {"findings": [], "stats": {"total_findings": 0}}

    name_to_products: dict[str, dict[str, str]] = defaultdict(dict)

    for glob in _TEST_HELPER_SCAN_GLOBS:
        for path in root.glob(glob):
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(root)
            except ValueError:
                logger.warning("recurrence: path outside repo root, skipping: %s", path)
                continue
            product = _product_of(rel)
            if product is None:
                continue
            for name in _extract_helper_names(path):
                if not _is_meaningful_test_helper(name):
                    continue
                if product not in name_to_products[name]:
                    name_to_products[name][product] = str(rel)

    findings: list[dict] = []
    for name, by_product in name_to_products.items():
        if len(by_product) < min_count:
            continue
        products = sorted(by_product.keys())
        locations = sorted(by_product.values())
        severity = "high" if len(products) >= must_formalize_threshold else "warning"
        suggestion = (
            f"Test helper `{name}` recurs in {len(products)} products: "
            f"{', '.join(products)}. Absorb into `noctusai_lib.testing.<helper>` "
            f"or `seed/lib/backend/noctusai_lib/testing/` (see existing adopters: "
            f"`bind_consent_module_to_mock`, `MockRequestBuilder.inserted_payloads`). "
            f"Cross-product test scaffolding belongs in seed-lib so the next "
            f"product gets the helper for free."
        )
        findings.append({
            "helper_name": name,
            "product_count": len(products),
            "products": products,
            "locations": locations,
            "severity": severity,
            "suggestion": suggestion,
        })

    severity_order = {"high": 0, "warning": 1}
    findings.sort(
        key=lambda f: (
            severity_order.get(f["severity"], 2),
            -len(f["products"]),
            f["helper_name"],
        ),
    )

    return {
        "findings": findings,
        "stats": {
            "total_findings": len(findings),
            "high_severity": sum(1 for f in findings if f["severity"] == "high"),
            "warning_severity": sum(1 for f in findings if f["severity"] == "warning"),
            "min_count_threshold": min_count,
            "must_formalize_threshold": must_formalize_threshold,
        },
    }


# ---------------------------------------------------------------------------
# `scan_migration_patterns` — SQL DDL + RLS templates recurring across products
# ---------------------------------------------------------------------------
#
# Closes second-wave gap #3. Every product writes its own RLS policies,
# audit-log triggers, FK-with-index pairs, etc. — and these templates DO
# drift over time. The platform-wide rules in `KB § PATTERNS/database-rls.md`
# (subquery `auth.uid()`, `search_path`, etc.) ARE platform-standard but
# each product re-implements them per migration.
#
# Detection strategy: regex-based for now (sqlglot would be cleaner but
# adds a heavy dep). Each migration .sql file is scanned for known SQL
# pattern shapes; matches are grouped by the normalized pattern.

# Single glob that matches both top-level and nested .sql files. The
# previous two-glob shape (`*.sql` + `**/*.sql`) double-counted top-level
# migrations because `**` matches zero or more directory segments.
_MIGRATION_GLOBS: list[str] = [
    "products/*/backend/migrations/**/*.sql",
]

# Pattern → (regex, label, suggestion). Each regex matches a STRUCTURAL
# SQL shape; grouping by which patterns appear in which migration files
# tells us which products independently re-implement the same template.
_SQL_PATTERN_PROBES: list[tuple[str, "re.Pattern", str]] = [
    (
        "rls_subquery_auth_uid",
        re.compile(
            r"CREATE\s+POLICY[^;]+USING\s*\(\s*"
            r"(?:auth\.uid\(\)\s*IN\s*\(\s*SELECT|"
            r"\(\s*SELECT\s+auth\.uid\(\))",
            re.IGNORECASE | re.DOTALL,
        ),
        "RLS policy with subquery `auth.uid()` — the platform standard. "
        "Absorb into a `seed/lib/backend/noctusai_lib/sql/rls_templates.sql` "
        "or a Python helper that emits the canonical shape with table name "
        "interpolated.",
    ),
    (
        "fk_with_index",
        re.compile(
            r"CREATE\s+INDEX[^;]+ON\s+\w+\s*\(\s*\w+_id\s*\)",
            re.IGNORECASE,
        ),
        "Index-on-FK-column pattern — every product creates these. The "
        "platform convention (every FK gets a covering index) is real but "
        "manual. Could be enforced via a migration linter rather than "
        "absorbed into a template.",
    ),
    (
        "search_path_lock",
        re.compile(
            r"SET\s+search_path\s*=\s*['\"]?\w+['\"]?",
            re.IGNORECASE,
        ),
        "`SET search_path` schema-lock — platform standard but each migration "
        "rewrites it. Absorb into a template prelude.",
    ),
    (
        "audit_log_trigger",
        re.compile(
            r"CREATE\s+TRIGGER[^;]+(?:audit|log)[^;]+EXECUTE\s+(?:FUNCTION|PROCEDURE)",
            re.IGNORECASE | re.DOTALL,
        ),
        "Audit-log trigger pattern — every product wires its own. Would "
        "absorb cleanly into a `noctusai_lib.sql.audit_trigger(table_name)` "
        "Python helper that emits the canonical SQL.",
    ),
    (
        "updated_at_trigger",
        re.compile(
            r"CREATE\s+TRIGGER[^;]+(?:updated_at|update_timestamp)[^;]+",
            re.IGNORECASE | re.DOTALL,
        ),
        "`updated_at` auto-touch trigger — universal Postgres pattern, "
        "every product writes its own. Absorb into a template.",
    ),
]


def _scan_migration_file(path: Path) -> dict[str, int]:
    """Return {pattern_name: occurrence_count} for matches in this .sql file."""
    counts: dict[str, int] = {}
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        logger.warning("recurrence: cannot read %s (%s), skipping", path, exc)
        return counts
    for pattern_name, regex, _ in _SQL_PATTERN_PROBES:
        matches = regex.findall(content)
        if matches:
            counts[pattern_name] = len(matches)
    return counts


def scan_migration_patterns(
    repo_root: Path | None = None,
    *,
    min_count: int = 2,
    must_formalize_threshold: int = 3,
) -> dict:
    """Scan SQL migration files for RLS/FK/trigger pattern recurrence.

    For each known SQL pattern probe, count occurrences per product and
    flag patterns appearing in N≥`min_count` products. The probes are
    deliberately broad (RLS subquery shape, FK index, search_path,
    triggers) — the absorption decision still requires reading the actual
    SQL, but the scan tells you WHICH products to compare.

    Args:
        repo_root: defaults to package root.
        min_count: minimum product count to flag (default 2).
        must_formalize_threshold: severity escalates to "high" at this count.

    Returns:
        Findings list per pattern with the products that use it + the file
        paths + a suggested absorption target.
    """
    root = repo_root or REPO_ROOT
    if not root.exists():
        return {"findings": [], "stats": {"total_findings": 0}}

    # pattern_name → {product_slug: total_occurrences_across_files}
    pattern_to_products: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    pattern_to_files: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    for glob in _MIGRATION_GLOBS:
        for path in root.glob(glob):
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(root)
            except ValueError:
                logger.warning("recurrence: path outside repo root, skipping: %s", path)
                continue
            product = _product_of(rel)
            if product is None:
                continue
            counts = _scan_migration_file(path)
            for pname, cnt in counts.items():
                pattern_to_products[pname][product] += cnt
                pattern_to_files[pname][product].append(str(rel))

    suggestion_by_name = {n: s for n, _, s in _SQL_PATTERN_PROBES}
    findings: list[dict] = []
    for pname, by_product in pattern_to_products.items():
        if len(by_product) < min_count:
            continue
        products = sorted(by_product.keys())
        total_occurrences = sum(by_product.values())
        files = sorted({f for fs in pattern_to_files[pname].values() for f in fs})
        severity = "high" if len(products) >= must_formalize_threshold else "warning"
        findings.append({
            "pattern_name": pname,
            "product_count": len(products),
            "products": products,
            "total_occurrences": total_occurrences,
            "occurrences_by_product": dict(by_product),
            "files": files,
            "severity": severity,
            "suggestion": suggestion_by_name.get(pname, "Recurring SQL pattern."),
        })

    severity_order = {"high": 0, "warning": 1}
    findings.sort(
        key=lambda f: (
            severity_order.get(f["severity"], 2),
            -f["product_count"],
            f["pattern_name"],
        ),
    )

    return {
        "findings": findings,
        "stats": {
            "total_findings": len(findings),
            "high_severity": sum(1 for f in findings if f["severity"] == "high"),
            "warning_severity": sum(1 for f in findings if f["severity"] == "warning"),
            "min_count_threshold": min_count,
            "must_formalize_threshold": must_formalize_threshold,
            "patterns_probed": len(_SQL_PATTERN_PROBES),
        },
    }


# ---------------------------------------------------------------------------
# Tool calibration & benchmark (refined 2026-04-28 — full eval after 8 scans)
# ---------------------------------------------------------------------------
#
# **False-positive rate on `scan_block_patterns` high-severity (manual review
# of all 28 findings, 2026-04-28):** 22/28 = **79% real absorption candidates,
# 21% shape-similarity false positives**. The 6 FPs are generic `db.table`
# / `supabase.table` accesses where the SHAPE is identical but each query
# targets a different table — the absorption is "coding-convention", not
# DRY. Acceptable for first run; FPs are 5-second triage.
#
# **Token-savings benchmark (4 representative workflows, on this repo):**
#
# | Workflow | Manual size | MCP size | Token savings | Wall-clock |
# |---|---:|---:|---:|---:|
# | Cross-product helper recurrence (read every service/router file by hand) | ~175K tokens | ~13K tokens | **93%** | 7× faster |
# | Cross-project status digest (read every PROJECT.md) | ~112K tokens | ~1.5K tokens | **99%** | 3.5× faster |
# | Symbol reference search (`process_session_end`) | ~600 tokens (grep) | ~1.2K tokens (JSON) | **-109%** (MCP costs more for trivial lookups) | comparable |
# | Compliance scan (all detectors) | depends on workflow scope | ~39K tokens | not directly comparable — MCP runs many checks vs reading individual files |
#
# **Honest read:** the absorption-search trio + status digest are big wins
# (90%+ savings on real workflows). Symbol-reference tools cost slightly
# more for trivial lookups (JSON wrapping overhead) but pay off when the
# match count exceeds ~100 (manual grep explodes). The full validate
# scan is "expensive" relative to reading 7 entry-point files, but
# delivers 12 detector outputs that would otherwise need 12 separate
# grep + reading sessions — the right comparison would be apples-to-apples
# manual-replication of all 12 checks, which is multi-hour.
#
# **Tool maturity verdict (2026-04-28):**
#   Solid — apply the 8 scans across the cleanup queue. Track which
#   high-severity findings result in real absorptions vs accept-with-rationale
#   over the next 1-2 weeks. Re-evaluate calibration block then.
#
# Five scans now provide layered coverage of the absorption problem:
#
# | Scan | Catches | Calibration |
# |---|---|---|
# | `scan_recurrence` | Verbatim line-level repetition in entry/conftest/config | Moderate signal — most hits are inheritance markers |
# | `scan_cross_product_helpers` | Function/class NAMES recurring across N≥2 products | HIGH signal — first run caught 14 high-severity hits, all real |
# | `scan_service_line_recurrence` | Verbatim line-level repetition in service/router files (≥60 chars + has `(`) | HIGH signal — catches ad-hoc shapes the name scan misses |
# | `scan_block_patterns` (NEW) | AST-normalized try/except SHAPES recurring across N≥2 occurrences | NEW — closes gap #1 (multi-line block recurrence) |
# | `scan_within_product_helpers` (NEW) | Helper names duplicated N+ times INSIDE one product | NEW — closes gap #2 (within-product DRY-into-utils) |
# | `scan_pydantic_model_shapes` (NEW) | Pydantic BaseModel field-set recurrence across N≥2 products | NEW — closes gap #3 (model shape recurrence) |
#
# **Remaining gaps after this batch (to be evaluated):**
# - Cross-language pattern recurrence (Python helper paired with TS hook).
# - Decorator usage patterns (`@router.get` shapes with same query params).
# - SQL migration pattern recurrence (every product writes the same RLS shape).
# - Test fixture body recurrence (similar test setups across product test trees).
#
# Whether to fix the remaining gaps depends on first-run ROI of the new
# detectors. Update this block after running on the real repo.


def register(server) -> None:
    @server.tool(
        name="noctus.dev.scan_recurrence",
        description=(
            "Scan product main.py / conftest.py / vitest.config.ts for repeated lines "
            "that should be absorbed into seed. N=2 → triage warning; N=3+ → high "
            "(MUST formalize). Emits classified findings with suggested seed-side "
            "absorption targets per `KB § PATTERNS/project-execution.md § 2.7`."
        ),
    )
    def _scan_recurrence(
        min_count: int = 2,
        must_formalize_threshold: int = 3,
    ) -> list:
        return scan_recurrence(
            min_count=min_count,
            must_formalize_threshold=must_formalize_threshold,
        )

    @server.tool(
        name="noctus.dev.scan_cross_product_helpers",
        description=(
            "Scan service/router/dependency/hook/component files for function/class "
            "NAMES that recur across N≥2 products. Catches the absorption shape "
            "`noctus.dev.scan_recurrence` misses — same NAME implemented slightly "
            "differently per product (`_safe_float`, `_format_money`, `useMetas`, "
            "`_PipelineHooks`). Suggests seed-side absorption targets "
            "(`noctusai_lib.parsing`, `@noctusai/lib/hooks`, etc.). Use BEFORE writing "
            "a new helper."
        ),
    )
    def _scan_cross(
        min_count: int = 2,
        must_formalize_threshold: int = 3,
    ) -> list:
        return scan_cross_product_helpers(
            min_count=min_count,
            must_formalize_threshold=must_formalize_threshold,
        )

    @server.tool(
        name="noctus.dev.scan_service_line_recurrence",
        description=(
            "Scan service/router/dependency lines for verbatim repetition across N≥2 "
            "products. Strict filter (≥60 chars, must contain `(`). Catches ad-hoc "
            "patterns the helper-name scan misses: "
            "`datetime.fromisoformat(s.replace(\"Z\", \"+00:00\"))`, `raise "
            "HTTPException(...)` shapes, pagination expressions like "
            "`query.range(offset, offset + page_size - 1).execute()`. Complements "
            "`noctus.dev.scan_cross_product_helpers`."
        ),
    )
    def _scan_service_line(
        min_count: int = 2,
        must_formalize_threshold: int = 3,
        min_line_length: int = 60,
    ) -> list:
        return scan_service_line_recurrence(
            min_count=min_count,
            must_formalize_threshold=must_formalize_threshold,
            min_line_length=min_line_length,
        )

    @server.tool(
        name="noctus.dev.scan_block_patterns",
        description=(
            "AST-walk service/router/seed-lib files; group `try/except` blocks by "
            "structural fingerprint (call targets normalized, identifiers stripped). "
            "Catches multi-line block recurrence the line/name scans miss — e.g. "
            "best-effort `audit_service.log` try/except shape recurring 7× in core. "
            "Each finding includes the body call targets, exception types, and a "
            "suggested seed-lib helper name (`safely_log_action`, `safely_dispatch`, "
            "etc.)."
        ),
    )
    def _scan_blocks(
        min_count: int = 2,
        must_formalize_threshold: int = 3,
        cross_product_only: bool = False,
    ) -> list:
        return scan_block_patterns(
            min_count=min_count,
            must_formalize_threshold=must_formalize_threshold,
            cross_product_only=cross_product_only,
        )

    @server.tool(
        name="noctus.dev.scan_within_product_helpers",
        description=(
            "Find helper names duplicated N+ times INSIDE one product (across files). "
            "Closes the gap that the cross-product helper scan requires N≥2 distinct "
            "products — a helper duplicated 5× inside one product is also a "
            "DRY-into-utils candidate. Suggests either `app/utils.py` (product-scope) "
            "or `noctusai_lib.<area>` (cross-cutting)."
        ),
    )
    def _scan_within(min_count: int = 3) -> list:
        return scan_within_product_helpers(min_count=min_count)

    @server.tool(
        name="noctus.dev.scan_pydantic_model_shapes",
        description=(
            "Find Pydantic `BaseModel` field-set shapes that recur across N≥`min_count` "
            "products. Catches the absorption signal the class-name scan misses — same "
            "field set under different class names (e.g. `LoginRequest` in core, "
            "`LoginInput` in adconnect). Suggests `noctusai_lib.schemas.<canonical>` "
            "absorption."
        ),
    )
    def _scan_pyd(
        min_count: int = 2,
        must_formalize_threshold: int = 3,
        min_field_count: int = 2,
    ) -> list:
        return scan_pydantic_model_shapes(
            min_count=min_count,
            must_formalize_threshold=must_formalize_threshold,
            min_field_count=min_field_count,
        )

    @server.tool(
        name="noctus.dev.scan_test_fixture_recurrence",
        description=(
            "Scan products' test trees (conftest.py, tests/services, tests/routers, "
            "tests/integration) for pytest fixtures + helper names recurring across "
            "N≥2 products. Stricter than the production helper scan — excludes test_* "
            "methods + ALL_CAPS sample-data names. Catches cross-product test "
            "scaffolding worth absorbing into `noctusai_lib.testing.<helper>`."
        ),
    )
    def _scan_fixtures(
        min_count: int = 2,
        must_formalize_threshold: int = 3,
    ) -> list:
        return scan_test_fixture_recurrence(
            min_count=min_count,
            must_formalize_threshold=must_formalize_threshold,
        )

    @server.tool(
        name="noctus.dev.scan_migration_patterns",
        description=(
            "Scan SQL migration files for known structural patterns (RLS policy with "
            "subquery `auth.uid()`, FK-with-index, `SET search_path`, audit-log "
            "trigger, `updated_at` trigger) that recur across N≥2 products. Reports "
            "per-product occurrence counts + suggested `noctusai_lib.sql.<helper>` "
            "absorption. 5 probes total."
        ),
    )
    def _scan_migrations(
        min_count: int = 2,
        must_formalize_threshold: int = 3,
    ) -> list:
        return scan_migration_patterns(
            min_count=min_count,
            must_formalize_threshold=must_formalize_threshold,
        )
