"""Seed compliance checks — migrated from agents/keeper/checks/.

Validates that products follow the seed framework pattern.
All checks are deterministic, fast, zero AI.

──────────────────────────────────────────────────────────────────────
ADDING A NEW DETECTOR — read this first.
──────────────────────────────────────────────────────────────────────
1. Add the `check_<name>(product_path: Path) -> list[dict]` function
   in this file (NOT a sibling module). The meta-detector
   `check_detector_has_regression_test` self-parses
   `compliance.py` via `Path(__file__)` to enumerate detectors;
   placing the function in a sibling silently drops it from the
   meta-check + leads to "regression test missing" false negatives.
2. Plumb it into BOTH:
     - `check_all_products()` here
     - `tools/noctus/dev/review.py::_detect()`
   Updating only one is a silent drop — `noctus.dev.review` will not
   surface the findings. (Knowledge contributed by
   `keeper-test-status-assertion` Phase 1 retro, 2026-05-06.)
3. Ship a colocated `Test<CamelCase>` regression suite in
   `mcp/noctusai/tests/` per `KB § PATTERNS/compliance/testing.md
   § Regression-test-the-detector`.
──────────────────────────────────────────────────────────────────────
"""
# accept-with-rationale: "MCP detectors keep raw `import ast`" in
# KB § PATTERNS/common/accept-with-rationale.md — compliance walks
# create_product_app(...) Call.keywords + List literals + monkeypatch
# Call.args[0/1] Constants + ImportFrom mapping; all node-level
# surfaces outline_python deliberately omits. Migration evaluated
# 2026-05-02 by ast-callers-consolidation Phase 0 → accept.
import ast
import hashlib
import logging
import re
import sqlite3
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from settings import REPO_ROOT, PRODUCTS_DIR  # noqa: E402  (path constants)


# Control-plane products OWN the identity/team/notifications/... routes — they
# ARE the provider, not consumers. Warnings about "has own team.py — framework
# provides this" are noise for them. Folded in by `seed-inheritance-hardening`
# Phase 5 (was the `keeper-control-plane-classification` backlog item).
#
# Any divergence across three or more products in this set would signal the
# classification is under-specified — re-open the decision.
CONTROL_PLANE_PRODUCTS: set[str] = {"core"}


# Synonyms: a standard-router name the framework ships (key) vs. the router
# module names a product may use when self-providing the same surface.
# Used by the AST-based self-provision detector below.
SELF_PROVIDED_ROUTER_MODULES: dict[str, set[str]] = {
    "notificacoes": {"notificacoes", "notifications"},
    "team": {"team"},
    "llm": {"llm", "llm_router"},
}


# Repo-root directories that are NOT products and must NOT be flagged as
# out-of-contract product trees. Extend only when a new non-product layer
# earns a home at the repo root (platform-wide infra).
_KNOWN_NON_PRODUCT_ROOT_DIRS: set[str] = {
    "products",
    "seed",
    "templates",
    "mcp",
    "KNOWLEDGE-BASE",
    "projects",
    "scripts",
    "venv",
    ".git",
    ".github",
    ".claude",
    ".venv",
    "node_modules",
    "docs",
    "tests",
}


def _parse_self_provided_routers(main_content: str) -> tuple[str, set[str] | None]:
    """AST-parse the `routers=[...]` kwarg on `create_product_app(...)` and
    return the set of router module names (e.g., `{"team", "notifications"}`).

    Returns:
      ("found", {names})  — parsed a list of `<Name>.router` Attributes
      ("absent", None)    — no `create_product_app(...)` call in the file
      ("unparseable", None) — call present but kwarg missing or not a simple
                              list of `<module>.router` attribute accesses

    Never silently returns an empty set for an unparseable value — callers
    must distinguish the three cases so the keeper doesn't quietly pretend
    a product self-provides nothing when the real answer is "can't tell."
    """
    try:
        tree = ast.parse(main_content)
    except SyntaxError as exc:
        logger.warning("compliance: cannot parse main.py (%s); marking as unparseable", exc)
        return "unparseable", None

    call = None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "create_product_app"
        ):
            call = node
            break

    if call is None:
        return "absent", None

    routers_kwarg = next((k for k in call.keywords if k.arg == "routers"), None)
    if routers_kwarg is None:
        return "found", set()

    if not isinstance(routers_kwarg.value, ast.List):
        return "unparseable", None

    names: set[str] = set()
    for elt in routers_kwarg.value.elts:
        if (
            isinstance(elt, ast.Attribute)
            and elt.attr == "router"
            and isinstance(elt.value, ast.Name)
        ):
            names.add(elt.value.id)
        else:
            return "unparseable", None

    return "found", names


def check_seed_compliance(product_path: Path) -> list[dict]:
    """Check a product's seed framework compliance."""
    issues = []
    name = product_path.name
    main_py = product_path / "backend" / "app" / "main.py"
    req_txt = product_path / "backend" / "requirements.txt"
    vite_config = product_path / "frontend" / "vite.config.ts"
    app_tsx = product_path / "frontend" / "src" / "App.tsx"

    # Backend checks
    if main_py.exists():
        content = main_py.read_text()
        if "create_product_app" not in content:
            issues.append({"product": name, "file": "backend/app/main.py", "issue": "Does not use create_product_app()", "severity": "critical"})
        if "noctusai_seed" not in content:
            issues.append({"product": name, "file": "backend/app/main.py", "issue": "Does not import from noctusai_seed", "severity": "critical"})

    if req_txt.exists():
        req_content = req_txt.read_text()
        if "seed/framework/backend" not in req_content:
            issues.append({"product": name, "file": "backend/requirements.txt", "issue": "Missing -e seed/framework/backend", "severity": "high"})
        if "seed/lib/backend" not in req_content:
            issues.append({"product": name, "file": "backend/requirements.txt", "issue": "Missing -e seed/lib/backend", "severity": "high"})

    # "Has own <router>.py — framework provides this" — suppress for control-plane
    # products that legitimately OWN the route (e.g., core owns team + notifications
    # because it's the identity source; seed would collide with its version).
    if name not in CONTROL_PLANE_PRODUCTS:
        for router_name in ["health.py", "notificacoes.py", "team.py"]:
            if (product_path / "backend" / "app" / "routers" / router_name).exists():
                issues.append({"product": name, "file": f"backend/app/routers/{router_name}", "issue": f"Has own {router_name} — framework provides this", "severity": "warning"})

    # Frontend checks
    if vite_config.exists():
        content = vite_config.read_text()
        if "createViteConfig" not in content:
            issues.append({"product": name, "file": "frontend/vite.config.ts", "issue": "Does not use createViteConfig()", "severity": "critical"})

    if app_tsx.exists():
        app_content = app_tsx.read_text()
        uses_fw = "createProductApp" in app_content or "createProductLayout" in app_content or "@noctusai/seed" in app_content
        if not uses_fw and "QueryClientProvider" in app_content and "BrowserRouter" in app_content:
            issues.append({"product": name, "file": "frontend/src/App.tsx", "issue": "Manual App structure — should use createProductApp()", "severity": "high"})

        src_dir = product_path / "frontend" / "src"
        layout_file = product_path / "frontend" / "src" / "components" / "layout" / "Layout.tsx"
        if layout_file.exists():
            uses_fw_layout = any("createProductLayout" in f.read_text() for f in src_dir.rglob("*.ts") if f.is_file()) or any("createProductLayout" in f.read_text() for f in src_dir.rglob("*.tsx") if f.is_file())
            # Skip for control-plane products that provide a custom Layout via the
            # `createProductApp({ Layout })` named seam — not a divergence, an
            # approved extension point.
            if not uses_fw_layout and name not in CONTROL_PLANE_PRODUCTS:
                issues.append({"product": name, "file": "frontend/src/components/layout/Layout.tsx", "issue": "Has own Layout.tsx — should use createProductLayout()", "severity": "high"})

    return issues


def check_path_references(product_path: Path) -> list[dict]:
    """Check that seed path references are correct."""
    issues = []
    name = product_path.name

    for rel, old, label in [
        ("backend/requirements.txt", "shared/backend", "old shared/backend path"),
        ("frontend/tsconfig.json", "shared/frontend", "old shared/frontend path"),
        ("frontend/tailwind.config.ts", "shared/frontend", "old shared/frontend path"),
    ]:
        target = product_path / rel
        if target.exists():
            content = target.read_text()
            if old in content and "seed/" not in content:
                issues.append({"product": name, "file": rel, "issue": f"References {label} — should be seed/", "severity": "critical"})

    return issues


# Signal map: each standard-router name → regex patterns whose presence in a
# product's frontend source indicates the product consumes that router.
# Keep narrow and curated — grep-based, not AST. Extend as new signals emerge.
# "health" is universal — every product should opt in; no frontend signal needed.
STANDARD_ROUTER_FRONTEND_SIGNALS: dict[str, list[str]] = {
    "notificacoes": [
        r"NotificationBell",  # direct import or alias via infra.NotificationBell
    ],
    "team": [
        r"['\"`]/api/team\b",  # literal path string in hooks / components
    ],
    "llm": [
        r"useLLM(?:Providers|Models|Preferences)\b",  # shared LLM preference hooks
    ],
}

# Fallback filename-based self-provision table — used only when the AST
# parser returns `unparseable` (v1 compatibility). AST parse of the actual
# `routers=[...]` list is the preferred path (set by self-provision v2, folded
# in by `seed-inheritance-hardening` Phase 5).
SELF_PROVIDED_ROUTER_FILES: dict[str, list[str]] = {
    "notificacoes": ["notificacoes.py", "notifications.py"],
    "team": ["team.py"],
    "llm": ["llm.py", "llm_router.py"],
}


def _parse_standard_routers(main_content: str) -> tuple[str, set[str] | None]:
    """Parse the `standard_routers=[...]` kwarg from a product's main.py.

    Returns:
      ("found", {"health", "team", ...})  — parsed a simple list literal
      ("absent", None)                    — no `standard_routers` kwarg at all
      ("unparseable", None)               — kwarg present but not a simple list
                                            literal (e.g., variable reference)

    Never silently returns an empty set for an unparseable value — per the
    "no silent errors" rule, the caller must distinguish these three cases.
    """
    match = re.search(r"standard_routers\s*=\s*\[([^\]]*)\]", main_content, re.DOTALL)
    if match:
        items = [
            s.strip().strip("'\"")
            for s in match.group(1).split(",")
            if s.strip() and s.strip() not in {"'", '"'}
        ]
        return "found", {r for r in items if r}
    if "standard_routers" in main_content:
        return "unparseable", None
    return "absent", None


def check_standard_routers_audit(product_path: Path) -> list[dict]:
    """Verify a product's `standard_routers=[...]` opt-in list matches
    the routers its frontend actually consumes.

    Two directions:
      - **Under-grant** (severity=critical): frontend uses router X but
        backend does not opt into it AND does not self-provide it.
        Runtime 404 risk — this is what the Phase 2 manual audit of
        `core-seed-wiring` missed for adconnect (NotificationBell
        rendered; `notificacoes` opt-out caused silent 404s).
      - **Over-grant** (severity=warning): backend opts into router X
        but no frontend signal found. Dead router registered at boot.

    `health` is universal — skipped (every product should opt in).

    Never silent: if `main.py` exists but `standard_routers` can't be
    parsed as a simple list literal, emits a `warning` finding asking
    for manual audit instead of pretending there is no kwarg.

    Self-provision detection (v2): primary path is AST-parse of
    `routers=[...]` in `main.py` (exact — knows what's wired, not what
    files exist). Falls back to filename-based detection when AST parse
    returns `unparseable`. Closes the gap `keeper-standard-routers-audit`
    Phase 1 noted: a product naming its router file oddly (`my_team_router.py`)
    would previously evade self-provision detection.
    """
    issues: list[dict] = []
    name = product_path.name
    main_py = product_path / "backend" / "app" / "main.py"
    frontend_src = product_path / "frontend" / "src"
    routers_dir = product_path / "backend" / "app" / "routers"

    if not main_py.exists():
        return []  # product has no backend/main.py — not in scope

    main_content = main_py.read_text()
    if "create_product_app" not in main_content:
        # Pre-migration product; other checks handle that. Nothing to audit here.
        return []

    state, opt_in = _parse_standard_routers(main_content)

    if state == "absent":
        issues.append({
            "product": name,
            "file": "backend/app/main.py",
            "issue": (
                "create_product_app() called without explicit standard_routers=[...]. "
                "Defaults to () — opts out of every bundled router. If intentional, "
                "add `standard_routers=[]` for explicit clarity; if not, add the "
                "routers the product needs."
            ),
            "severity": "high",
        })
        return issues

    if state == "unparseable":
        issues.append({
            "product": name,
            "file": "backend/app/main.py",
            "issue": (
                "standard_routers kwarg is present but not a simple list literal "
                "(likely a variable reference or dynamic). Keeper cannot audit; "
                "review manually or inline the list."
            ),
            "severity": "warning",
        })
        return issues

    # state == "found" — opt_in is a real set
    assert opt_in is not None  # narrowing for type-checkers

    if not frontend_src.exists():
        # Backend-only product (e.g., webhooks-only service). Audit complete
        # with what we have — no frontend signals to compare.
        return []

    # Self-provision set: AST-parse the `routers=[...]` list first (v2). Fall
    # back to filename-based detection if the file can't be parsed as a simple
    # list of `<module>.router` attribute accesses.
    sp_state, sp_modules = _parse_self_provided_routers(main_content)

    def _self_provides(router: str) -> bool:
        if sp_state == "found":
            assert sp_modules is not None
            synonyms = SELF_PROVIDED_ROUTER_MODULES.get(router, {router})
            return bool(sp_modules & synonyms)
        # Fallback — filename-based. Kept for unparseable `routers=...`
        # (variable reference, dynamic list, SyntaxError). One-line rationale
        # on the "no silent errors" front: the standard_routers parse above
        # already surfaces the `unparseable` state to the user; here we do
        # best-effort self-provision detection so we don't over-flag under-grants.
        for filename in SELF_PROVIDED_ROUTER_FILES.get(router, []):
            if (routers_dir / filename).exists():
                return True
        return False

    # Collect frontend signals.
    signals_found: set[str] = set()
    frontend_files: list[Path] = []
    for ext in ("*.ts", "*.tsx"):
        frontend_files.extend(f for f in frontend_src.rglob(ext) if f.is_file())

    # Concatenate is fine for a small-ish frontend; keeps the scan simple.
    corpus = "\n".join(f.read_text(errors="ignore") for f in frontend_files)

    for router, patterns in STANDARD_ROUTER_FRONTEND_SIGNALS.items():
        if any(re.search(p, corpus) for p in patterns):
            signals_found.add(router)

    # Under-grant: signal exists, NOT in opt-in, NOT self-provided.
    for router in sorted(signals_found - opt_in):
        if _self_provides(router):
            continue  # product serves it from its own router file
        patterns_str = " | ".join(STANDARD_ROUTER_FRONTEND_SIGNALS[router])
        issues.append({
            "product": name,
            "file": "backend/app/main.py",
            "issue": (
                f"Frontend uses '{router}' router (matched pattern: {patterns_str}) "
                f"but backend does not opt into it via standard_routers=[...] and does "
                f"not self-provide it. Runtime requests to /api/{router}* will 404. "
                f"Fix by adding '{router}' to the opt-in list."
            ),
            "severity": "critical",
        })

    # Over-grant: in opt-in, no signal (and we actually look for one — skip health).
    for router in sorted(opt_in - signals_found):
        if router not in STANDARD_ROUTER_FRONTEND_SIGNALS:
            continue  # health or future-added router without a signal — skip
        patterns_str = " | ".join(STANDARD_ROUTER_FRONTEND_SIGNALS[router])
        issues.append({
            "product": name,
            "file": "backend/app/main.py",
            "issue": (
                f"Backend opts into '{router}' via standard_routers=[...] but no "
                f"frontend signal found (searched: {patterns_str}). Likely a dead "
                f"router — remove from the list, OR add the missing frontend feature, "
                f"OR extend STANDARD_ROUTER_FRONTEND_SIGNALS if the consumption "
                f"pattern is new."
            ),
            "severity": "warning",
        })

    return issues


def check_frontend_entrypoint(product_path: Path) -> list[dict]:
    """Verify the product's frontend entrypoint actually CALLS `createProductApp()`
    rather than just importing from `@noctusai/seed` or rendering a raw React tree.

    Two valid shapes:
      1. `main.tsx` calls `createProductApp(...)` directly (core pattern).
      2. `main.tsx` delegates to `./App` and `App.tsx` calls `createProductApp(...)`
         (therapy pattern).

    Rendering `<BrowserRouter>` / `<QueryClientProvider>` / `ReactDOM.createRoot(<...>)`
    without routing through `createProductApp` is a structural fork — the framework's
    Suspense, error boundary, routing, providers, and auth path are bypassed.

    Folded in by `seed-inheritance-hardening` Phase 5 — closes the "main.tsx
    bypasses createProductApp" gap that the existing App.tsx-scoped check missed
    (core has no App.tsx; the old detector never fires on core).
    """
    issues: list[dict] = []
    name = product_path.name
    main_tsx = product_path / "frontend" / "src" / "main.tsx"
    app_tsx = product_path / "frontend" / "src" / "App.tsx"

    if not main_tsx.exists():
        return []  # backend-only product

    main_content = main_tsx.read_text()

    # Path 1 — direct call in main.tsx.
    if re.search(r"createProductApp\s*\(", main_content):
        return []

    # Path 2 — delegates to ./App whose default export uses createProductApp.
    imports_app = bool(re.search(r"""from\s+['"]\./App(?:\.tsx)?['"]""", main_content))
    if imports_app and app_tsx.exists():
        app_content = app_tsx.read_text()
        if re.search(r"createProductApp\s*\(", app_content):
            return []

    # Neither path matched — entrypoint is not wired through the framework.
    issues.append({
        "product": name,
        "file": "frontend/src/main.tsx",
        "issue": (
            "Frontend entrypoint does not call createProductApp() — not in main.tsx "
            "and not in an imported ./App. Consumer products must construct the app "
            "via createProductApp() from @noctusai/seed (named seam). Rendering a raw "
            "React tree bypasses the framework's routing, providers, error boundary, "
            "and Suspense fallback."
        ),
        "severity": "critical",
    })
    return issues


def check_handrolled_core_url(product_path: Path) -> list[dict]:
    """Flag hand-rolled core-URL resolution in a product frontend.

    Mandatory routing rule: the SSO callback + every cross-product nav site
    MUST resolve core's URL through the canonical seed getter `env.CORE_URL` /
    `env.CORE_API_URL` (`@noctusai/lib`, source `seed/lib/frontend/src/env.ts`)
    — NEVER hand-roll `import.meta.env.VITE_CORE_URL || "<literal>"`. The getter
    encodes the same-origin fallback (VITE_CORE_API_URL ‖ VITE_CORE_URL) + the
    house-port dev default ONCE, for every consumer.

    The recurrence this closes (N≥3, prod outage 2026-05-25): a bare
    `localhost:8000` default broke `/sso` ("Failed to fetch") for every product
    whose bundle bakes only VITE_CORE_URL; a stale `localhost:5173` default (the
    dead pre-house vite port) broke cross-product nav. See
    `KB § PATTERNS/frontend/core-url-routing.md` + `KB § PATTERNS/backend/boundary-contract-tests.md` B1.

    Carve-out: `core/frontend/src/lib/api.ts` — core is same-origin to ITSELF,
    so its api client legitimately reads VITE_CORE_API_URL with a
    `window.location.origin` fallback (NOT VITE_CORE_URL). That is the one
    correct hand-roll; every other `import.meta.env.VITE_CORE_*` in a product
    frontend is the bug.
    """
    issues: list[dict] = []
    name = product_path.name
    src = product_path / "frontend" / "src"
    if not src.is_dir():
        return []  # backend-only product

    # The single legitimate same-origin self-reference (core IS core).
    core_api_carveout = product_path / "frontend" / "src" / "lib" / "api.ts"

    pattern = re.compile(r"import\.meta\.env\.VITE_CORE_(?:API_)?URL")
    for f in sorted(list(src.rglob("*.ts")) + list(src.rglob("*.tsx"))):
        if not f.is_file():
            continue
        if name == "core" and f == core_api_carveout:
            continue
        try:
            content = f.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(content.splitlines(), start=1):
            if line.lstrip().startswith(("//", "*")):
                continue  # comment line (e.g. a breadcrumb referencing the var)
            if pattern.search(line):
                issues.append({
                    "product": name,
                    "file": f.relative_to(product_path).as_posix(),
                    "issue": (
                        f"Hand-rolled `import.meta.env.VITE_CORE_*` at line {lineno} — "
                        "resolve core's URL through the canonical seed getter "
                        "`env.CORE_URL` / `env.CORE_API_URL` (@noctusai/lib) instead. A "
                        "hand-rolled `|| <literal>` default is the SSO 'Failed to fetch' / "
                        "stale-5173-nav recurrence (KB core-url-routing; boundary B1)."
                    ),
                    "severity": "high",
                })
    return issues


# ---------------------------------------------------------------------------
# Product-internal-wiring — the STATIC legs (KB § PATTERNS/frontend/product-internal-wiring.md
# legs 2/4/5), codified as Stage-4 keeper detectors. Each reuses the EXACT
# shared predicate already shipped in `tools/noctus/dev/scan_wiring.py`
# (`analyze_missing_routes` / `analyze_name_on_nome` /
# `analyze_promise_all_shared_catch`) — one predicate, two surfaces (the
# `noctus.dev.scan_wiring` MCP tool + these keepers), no copy-paste (DRY).
#
# The runtime leg (3 — live auth-gated endpoint probe) + the page-scoped-CRUD
# leg (7 — needs judgment) are NOT deterministic and STAY advisory; they are
# deliberately NOT codified here.
#
# Severities follow the failure class: a missing route is a 404 / wrong-route
# (high), a `name`-on-`nome` select is the recurring 500 class (high), a
# shared-catch `Promise.all` is degraded UX / all-zeros (warning — not a hard
# failure, so it does not enter the high/critical regression baseline).
# ---------------------------------------------------------------------------


def _wiring_repo_root(product_path: Path) -> Path:
    """Resolve the repo root for the shared scan_wiring predicates.

    The real tree is `<repo>/products/<slug>` so `parent.parent` is the repo
    root (where the seed-framework routers live, needed by Leg A). Test
    fixtures mirror the sibling-keeper layout (`tmp_path/<slug>`, no `products/`
    layer) — there `parent.parent` simply has no `seed/` glob match, which is
    correct (the fixture supplies its own backend routes).
    """
    parent = product_path.parent
    if parent.name == "products":
        return parent.parent
    return parent


def check_fe_route_missing(product_path: Path) -> list[dict]:
    """Leg A — FE `api.<method>('<path>')` calls with no matching backend route.

    Product-internal-wiring rule (`KB § PATTERNS/frontend/product-internal-wiring.md`
    leg 2): every FE backend call must hit a real registered route. A FE call
    whose (method, normalized-path) matches no `@router.<method>` decorator +
    mount prefix (product routers + seed-framework standard routers) is the
    404/route-missing class — **route-exists ≠ wired**. Dynamic segments
    (`${id}` / `{id}` / `:id`) normalize on both sides.

    Reuses `scan_wiring.analyze_missing_routes` (the shared predicate the
    `noctus.dev.scan_wiring` tool also calls — one source of truth). Severity
    `high` (a 404 breaks the surface).
    """
    from tools.noctus.dev.scan_wiring import analyze_missing_routes

    fe_root = product_path / "frontend"
    be_root = product_path / "backend"
    if not fe_root.is_dir():
        return []  # backend-only product (no FE surfaces to wire)
    repo_root = _wiring_repo_root(product_path)
    name = product_path.name
    return [
        {
            "product": name,
            "file": f.file,
            "issue": f"line {f.line}: {f.detail}",
            "severity": "high",
        }
        for f in analyze_missing_routes(fe_root, be_root, repo_root)
    ]


def check_name_on_nome_select(product_path: Path) -> list[dict]:
    """Leg B — PostgREST selecting `name` on a `nome`-table (the 500 class).

    Product-internal-wiring rule (`KB § PATTERNS/frontend/product-internal-wiring.md`
    leg 5): the platform schema is Portuguese — `plans` / `products` /
    `organizations` carry `nome`, NOT `name`. A `.select("plans(name)")` /
    `plans!inner(name)` is the recurring 500 that zeroed the core admin
    dashboard. Scans backend `.py` + FE `.ts/.tsx`.

    Reuses `scan_wiring.analyze_name_on_nome` (the shared predicate). Severity
    `high` (a 500 breaks the surface).
    """
    from tools.noctus.dev.scan_wiring import analyze_name_on_nome

    fe_root = product_path / "frontend"
    be_root = product_path / "backend"
    repo_root = _wiring_repo_root(product_path)
    name = product_path.name
    return [
        {
            "product": name,
            "file": f.file,
            "issue": f"line {f.line}: {f.detail}",
            "severity": "high",
        }
        for f in analyze_name_on_nome(be_root, fe_root, repo_root)
    ]


def check_promise_all_shared_catch(product_path: Path) -> list[dict]:
    """Leg C — `Promise.all([bare fetches])` under one shared try/catch.

    Product-internal-wiring rule (`KB § PATTERNS/frontend/product-internal-wiring.md`
    leg 4): a surface fetching N endpoints under one shared `try { ... } catch`
    turns ONE failure into all-zeros (the all-zeros dashboard bug). Per-element
    `.catch(() => fallback)` degrades independently and is CORRECT (not
    flagged).

    Reuses `scan_wiring.analyze_promise_all_shared_catch` (the shared
    predicate). Severity `warning` — degraded UX, not a hard failure, so it
    does NOT enter the high/critical regression baseline.
    """
    from tools.noctus.dev.scan_wiring import analyze_promise_all_shared_catch

    fe_root = product_path / "frontend"
    if not fe_root.is_dir():
        return []  # backend-only product
    repo_root = _wiring_repo_root(product_path)
    name = product_path.name
    return [
        {
            "product": name,
            "file": f.file,
            "issue": f"line {f.line}: {f.detail}",
            "severity": "warning",
        }
        for f in analyze_promise_all_shared_catch(fe_root, repo_root)
    ]


def check_out_of_contract_trees(repo_root: Path | None = None) -> list[dict]:
    """Detect product-shaped directories living outside `products/*/`.

    A directory "looks like a product" when it has `backend/app/main.py` OR
    `frontend/src/main.tsx`. `templates/product-seed/` is the scaffolding
    template — not a product; excluded by the known-non-product allow-list.

    Folded in by `seed-inheritance-hardening` Phase 5 — catches future
    `/adconnect/`-style strays before they drift. Returns issues with
    `product="<root>"` so the review pipeline can attribute them at the
    platform level.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        if d.name.startswith(".") or d.name in _KNOWN_NON_PRODUCT_ROOT_DIRS:
            continue
        has_backend_main = (d / "backend" / "app" / "main.py").exists()
        has_frontend_main = (d / "frontend" / "src" / "main.tsx").exists()
        if has_backend_main or has_frontend_main:
            shapes = []
            if has_backend_main:
                shapes.append("backend/app/main.py")
            if has_frontend_main:
                shapes.append("frontend/src/main.tsx")
            issues.append({
                "product": "<root>",
                "file": f"{d.name}/",
                "issue": (
                    f"Directory `{d.name}/` at repo root looks like a product tree "
                    f"(has {', '.join(shapes)}) but lives outside `products/*/`. "
                    f"Either migrate to `products/{d.name}/` (filing a `{d.name}-seed-wiring` "
                    f"project per CLAUDE.md rule 1) or delete the directory if it's "
                    f"legacy / migrational reference with no unique content."
                ),
                "severity": "critical",
            })
    return issues


def check_seed_version_propagation(repo_root: Path | None = None) -> list[dict]:
    """Detect seed-install drift: stale `__seed_version__` / `__lib_version__`.

    Shipped by `seed-inheritance-hardening` Phase 3 via `seed-core-consolidation` §7.1
    (user decision: git-tag/SHA-derived at install time).

    Logic:
    1. Read the current git short SHA from the repo HEAD.
    2. Import `noctusai_seed.__seed_version__` + `noctusai_lib.__lib_version__`
       from the currently-installed packages.
    3. If either reports a SHA different from git HEAD — flag. Actionable
       remediation: `python mcp/noctusai/cli.py --stamp-seed-version` (or restart via
       `./start.sh` which does it automatically).
    4. If either reports a `runtime:<sha>` tag (fallback path, no install
       stamp yet) — flag as warning so a never-stamped environment gets
       noticed.
    5. If either reports "unknown" — flag as critical (import failed, or
       no git + no stamp — detector is blind).

    Returns a list of issue dicts compatible with the existing detector
    protocol. `product="<platform>"` because this is a single-pointed
    platform-wide check, not per-product.
    """
    import subprocess

    issues: list[dict] = []
    root = repo_root or REPO_ROOT

    try:
        git_result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if git_result.returncode != 0 or not git_result.stdout.strip():
            # Can't determine current HEAD — skip check rather than error noisily.
            return issues
        current_sha = git_result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("compliance: git unavailable for version-propagation check (%s); skipping", exc)
        return issues

    for package_name, attr_name, stamp_hint in (
        ("noctusai_seed", "__seed_version__", "seed/framework/backend"),
        ("noctusai_lib", "__lib_version__", "seed/lib/backend"),
    ):
        # Prefer reading `_version_static.py` from the filesystem — this
        # avoids requiring `pip install -e` of the seed packages in the venv
        # that runs `--validate` (e.g. the MCP toolkit's own venv). The
        # static stamp IS the propagation source of truth; importing the
        # package only adds the live-git fallback path which we can apply
        # ourselves below if the static stamp is missing.
        static_path = root / stamp_hint / package_name / "_version_static.py"
        reported: str | None = None
        if static_path.exists():
            try:
                static_content = static_path.read_text(encoding="utf-8")
                m = re.search(
                    r'^__version__\s*=\s*[\'"]([^\'"]+)[\'"]',
                    static_content,
                    re.MULTILINE,
                )
                if m:
                    reported = m.group(1)
            except OSError as exc:
                logger.warning("compliance: cannot read %s (%s); falling through to import", static_path, exc)
                reported = None
        if reported is None:
            # Static stamp missing or unreadable. Try importing as a last
            # resort — only fires if the package happens to be installed.
            try:
                module = __import__(package_name)
                reported = getattr(module, attr_name, None)
            except ImportError as exc:
                logger.warning("compliance: cannot import %s (%s); will surface as critical issue", package_name, exc)
                issues.append({
                    "product": "<platform>",
                    "file": f"{stamp_hint}/{package_name}/_version_static.py",
                    "issue": (
                        f"`{package_name}` has no `_version_static.py` stamp "
                        f"AND is not installed in this venv. Run "
                        f"`python mcp/noctusai/cli.py --stamp-seed-version` to write the "
                        f"stamp, or `pip install -e {stamp_hint}` to install "
                        f"the package."
                    ),
                    "severity": "critical",
                })
                continue

        if not isinstance(reported, str) or not reported:
            issues.append({
                "product": "<platform>",
                "file": f"{stamp_hint}/{package_name}/_version_static.py",
                "issue": (
                    f"`{package_name}.{attr_name}` is missing or empty — "
                    f"propagation detector is blind. Expected a git short SHA."
                ),
                "severity": "critical",
            })
            continue

        if reported == "unknown":
            issues.append({
                "product": "<platform>",
                "file": f"{stamp_hint}/{package_name}/_version_static.py",
                "issue": (
                    f"`{package_name}.{attr_name}` reports 'unknown' — "
                    f"neither install-time stamp nor live git succeeded. "
                    f"Run `python mcp/noctusai/cli.py --stamp-seed-version` from a git clone."
                ),
                "severity": "critical",
            })
            continue

        if reported.startswith("runtime:"):
            live_sha = reported.split(":", 1)[1]
            if live_sha != current_sha:
                # This should be impossible (runtime read happens in-process
                # from the same git tree), but catch it defensively.
                issues.append({
                    "product": "<platform>",
                    "file": f"{stamp_hint}/",
                    "issue": (
                        f"`{package_name}.{attr_name}` reports live-git SHA "
                        f"{live_sha!r} but current `git rev-parse --short HEAD` "
                        f"is {current_sha!r}. Filesystem inconsistency — "
                        f"investigate."
                    ),
                    "severity": "high",
                })
            else:
                # Runtime-fallback path took over. Flag as warning so the
                # developer stamps explicitly and shifts to the install-time path.
                issues.append({
                    "product": "<platform>",
                    "file": f"{stamp_hint}/{package_name}/_version_static.py",
                    "issue": (
                        f"`{package_name}.{attr_name}` falls back to live git "
                        f"(reports {reported!r}) — no install-time stamp exists. "
                        f"Run `python mcp/noctusai/cli.py --stamp-seed-version` once to "
                        f"enable drift detection across future pulls."
                    ),
                    "severity": "warning",
                })
            continue

        if reported != current_sha:
            issues.append({
                "product": "<platform>",
                "file": f"{stamp_hint}/{package_name}/_version_static.py",
                "issue": (
                    f"Seed drift: installed `{package_name}.{attr_name}` is "
                    f"{reported!r} but current `git rev-parse --short HEAD` "
                    f"is {current_sha!r}. The running Python sees stale seed "
                    f"code. Remediate: `python mcp/noctusai/cli.py --stamp-seed-version` "
                    f"(or restart via `./start.sh` which does it automatically)."
                ),
                "severity": "high",
            })

    return issues


def _resolve_base_name(node: ast.expr) -> str | None:
    """Resolve a class-base AST node to its terminal name.

    Handles `Name` (`ProductSettings`) and `Attribute` (`pkg.ProductSettings`).
    Returns None for unrecognized shapes — caller treats that as 'doesn't match
    a known seed base', which is the safe default.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def check_config_extends_product_settings(product_path: Path) -> list[dict]:
    """Every product config class must extend `noctusai_seed.ProductSettings`.

    Direct extension of `BaseAppSettings` is a structural fork: the product
    duplicates env_file resolution and loses the seed's `parents[4] / .env`
    math. This was the root cause of the 2026-04-25 core login regression
    (path resolved to `products/.env`, supabase_url loaded as ""). Filed
    after `core-seed-wiring` Phase 6 closed the symptom — this detector
    closes the recurrence path.

    Detection: AST-walks `app/config.py`, finds every `ClassDef`, and checks
    that any class extending `BaseAppSettings` also extends `ProductSettings`.
    Returns severity=critical findings (silent prod failure class).

    Skips products without `app/config.py` (returns empty).

    Opt-out: a `# noctusai-keeper: allow-base-app-settings` comment on or
    immediately above the offending `class` line suppresses the finding.
    Build the recognizer when the first legitimate case appears (YAGNI).
    """
    issues: list[dict] = []
    name = product_path.name
    config_file = product_path / "backend" / "app" / "config.py"
    if not config_file.exists():
        return issues

    try:
        tree = ast.parse(config_file.read_text())
    except SyntaxError as e:
        logger.warning("compliance: cannot parse %s (%s); will surface as critical issue", config_file, e)
        issues.append({
            "product": name,
            "file": "backend/app/config.py",
            "issue": f"Failed to parse config.py: {e.msg} at line {e.lineno}",
            "severity": "critical",
        })
        return issues

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        base_names = {_resolve_base_name(b) for b in node.bases}
        base_names.discard(None)
        if "BaseAppSettings" in base_names and "ProductSettings" not in base_names:
            issues.append({
                "product": name,
                "file": "backend/app/config.py",
                "issue": (
                    f"Class {node.name!r} extends BaseAppSettings directly. "
                    f"Should extend noctusai_seed.ProductSettings to inherit "
                    f"env_file resolution (parents[4] / .env). Hand-rolling the "
                    f"env_file path silently breaks env loading — see the "
                    f"2026-04-25 core login regression."
                ),
                "severity": "critical",
            })

    return issues


# Matches a quoted relative path that targets the seed directory.
# - Must start with `.` or `..` (relative path marker) inside the quote
# - Must contain `seed` followed by either `/` (path continues) or a terminal quote
# - No quote characters inside the captured path
# Rejects non-paths like "seed-loader" (no leading dot) or "docs/seed.md"
# (terminal `seed.md`, not `seed/...` or terminal `seed`). Programmatic
# path construction (`path.resolve(__dirname, "..", "seed")`) is out of
# scope per Q1 (YAGNI — extend if a programmatic-form bug surfaces).
_SEED_RELATIVE_PATH_PATTERN = re.compile(
    r"""['"](\.{1,2}[^'"]*?seed(?:/[^'"]*)?)['"]"""
)

# Module-resolution extensions tried by vite/typescript when an import omits
# the file extension. Order matches typical bundler probe order.
_TS_MODULE_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts")
_TS_INDEX_FILES = ("index.ts", "index.tsx", "index.js", "index.jsx")


def _resolves_via_module_resolution(resolved: Path) -> bool:
    """True if a TS/JS import path resolves to something that exists.

    Mimics vite/typescript probe order:
      1. literal path as-is
      2. literal path + .ts / .tsx / .js / .jsx / .mts / .cts
      3. literal path / index.ts (etc.)
    """
    if resolved.exists():
        return True
    for ext in _TS_MODULE_EXTENSIONS:
        if Path(f"{resolved}{ext}").exists():
            return True
    for idx in _TS_INDEX_FILES:
        if (resolved / idx).exists():
            return True
    return False


def _glob_prefix_resolves(resolved_str: str) -> bool:
    """True if a glob pattern's literal prefix points to an existing directory.

    Tailwind `content` arrays use globs like `<dir>/**/*.{ts,tsx}`. The bug
    class we're catching is "the directory before the glob doesn't exist",
    not "the glob matches zero files" (which is a runtime concern).
    """
    glob_chars = "*?[{"
    first_glob = next((i for i, c in enumerate(resolved_str) if c in glob_chars), None)
    if first_glob is None:
        return False  # caller should not have called this for non-glob paths
    prefix = resolved_str[:first_glob].rsplit("/", 1)[0]
    return Path(prefix).is_dir()


def check_frontend_config_paths(product_path: Path) -> list[dict]:
    """Verify relative paths to `seed/` in frontend config files actually resolve.

    Reads `frontend/vite.config.ts`, `frontend/tailwind.config.ts`, and
    `frontend/postcss.config.js`. Extracts every relative path containing
    `seed/`, resolves it against the config file's location, and flags
    paths whose resolution targets nothing.

    Resolution mimics vite/typescript:
      - Literal imports without extensions probe `.ts` / `.tsx` / `.js` /
        etc., and `/index.ts` directory-indexes (handled by
        `_resolves_via_module_resolution`).
      - Glob patterns (containing `*`, `?`, `[`, or `{`) verify the
        literal-prefix directory exists (handled by `_glob_prefix_resolves`).

    Skips silently when a config file doesn't exist (postcss is optional;
    the missing-vite-config case is already covered by `check_seed_compliance`).

    Filed by `projects/keeper-frontend-config-paths-audit/` after the
    2026-04-20 seed-relocation broke core's frontend (`../../seed/` →
    `../../../seed/`). The bug class is "stale relative path = unbuildable
    frontend"; severity matches the inheritance-bypass class.
    """
    issues: list[dict] = []
    name = product_path.name
    config_files = [
        product_path / "frontend" / "vite.config.ts",
        product_path / "frontend" / "tailwind.config.ts",
        product_path / "frontend" / "postcss.config.js",
    ]
    glob_chars = "*?[{"
    for config_file in config_files:
        if not config_file.exists():
            continue
        content = config_file.read_text()
        for match in _SEED_RELATIVE_PATH_PATTERN.finditer(content):
            rel_path = match.group(1)
            resolved = (config_file.parent / rel_path).resolve()
            if any(c in str(resolved) for c in glob_chars):
                ok = _glob_prefix_resolves(str(resolved))
            else:
                ok = _resolves_via_module_resolution(resolved)
            if not ok:
                issues.append({
                    "product": name,
                    "file": str(config_file.relative_to(product_path)),
                    "issue": (
                        f"Stale relative path {rel_path!r} resolves to "
                        f"{resolved} which does not exist (tried TS module "
                        f"resolution + glob prefix). Frontend will fail to build."
                    ),
                    "severity": "critical",
                })
    return issues


def check_mock_schema_validation(product_path: Path) -> list[dict]:
    """Verify the product's test conftest does not opt OUT of MockSupabaseClient
    schema validation without an explicit rationale comment.

    Default as of `mock-supabase-schema-validation` Phase 4 (2026-04-24) is
    `validate_schema=True`. A conftest that passes `validate_schema=False`
    must include a nearby comment explaining WHY (pointing at the follow-up
    reconciliation project that will flip it back).

    Detection rules:
      - If conftest passes `validate_schema=False` literally AND the file
        contains no comment mentioning `schema-drift` / `reconciliation` /
        `follow-up` → warning with severity=high.
      - If conftest uses the shared `MockSupabaseClient()` with no flag →
        fine (the default is now True).
      - If conftest doesn't instantiate `MockSupabaseClient` at all → skip.

    This closes the "silent opt-out" loophole: a product CAN drop validation
    if the drift is too big to fix in-session, but the next agent inherits
    the rationale and the pointer to the remediation project.
    """
    issues: list[dict] = []
    name = product_path.name
    conftest = product_path / "backend" / "tests" / "conftest.py"
    if not conftest.exists():
        return issues
    content = conftest.read_text()

    # Opt-out detector — string-match `validate_schema=False` anywhere in file.
    if "validate_schema=False" not in content:
        return issues

    # Rationale detector — look for any explanatory keyword.
    rationale_keywords = (
        "schema-drift",
        "schema drift",
        "reconciliation",
        "follow-up",
        "follow up",
        "TODO",
    )
    has_rationale = any(kw.lower() in content.lower() for kw in rationale_keywords)
    if has_rationale:
        return issues

    issues.append({
        "product": name,
        "file": "backend/tests/conftest.py",
        "issue": (
            "MockSupabaseClient is constructed with `validate_schema=False` but "
            "the conftest has no rationale comment. Silent opt-out from schema "
            "validation re-opens the silent-fail class closed by the "
            "`mock-supabase-schema-validation` project. Either flip back to "
            "`validate_schema=True` (default) or add a comment block naming the "
            "drift points + the follow-up reconciliation project that will "
            "resolve them (see `products/therapy-platform/projects/"
            "therapy-audio-lifecycle-schema-reconciliation/` for the reference "
            "shape)."
        ),
        "severity": "high",
    })
    return issues


def check_ai_feature_completeness(product_path: Path) -> list[dict]:
    """Verify a product's AI-feature wiring is complete.

    Tier 1.5 G3 hardening (ai-expansion, 2026-04-24). For each product that
    has `app/services/ai_service.py`, verify:

      1. The `app/routers/ai.py` (or any `app/routers/<x>.py` containing AI
         endpoints) is registered in `main.py`'s `routers=[...]` list.
      2. The product's `MASTER-PROMPT.md` has an "AI" section mentioning
         the service file (otherwise an agent can't discover it).
      3. Every `chat_completion(..., cache=True, ...)` call in the service
         passes `org_id=` (cross-org cache-leak guard — pairs with the cache
         key isolation shipped by G5).

    Skips products without an `ai_service.py` (no AI features → nothing to check).
    """
    issues: list[dict] = []
    name = product_path.name
    ai_service = product_path / "backend" / "app" / "services" / "ai_service.py"
    if not ai_service.exists():
        return issues

    # ── Check 1: ai.py router (if present) is in main.py's routers list ──
    main_py = product_path / "backend" / "app" / "main.py"
    ai_router = product_path / "backend" / "app" / "routers" / "ai.py"
    if ai_router.exists() and main_py.exists():
        main_content = main_py.read_text()
        # Look for any of: `ai.router`, `ai_router.router`, or import-form.
        wired = bool(
            re.search(r"\bai\.router\b", main_content)
            or re.search(r"\bai_router\.router\b", main_content)
            or re.search(r"from\s+app\.routers(?:\.|\s+import\s+\(?[^)]*?\b)ai\b", main_content)
        )
        if not wired:
            issues.append({
                "product": name,
                "file": "backend/app/main.py",
                "issue": (
                    f"{name} has `app/services/ai_service.py` and `app/routers/ai.py` "
                    f"but the router is NOT registered in `main.py`'s `routers=[...]`. "
                    f"AI endpoints will 404 in production. Add the import + the router "
                    f"to the create_product_app(routers=[...]) list."
                ),
                "severity": "high",
            })

    # ── Check 2: MASTER-PROMPT.md mentions AI ──
    master_prompt = product_path / "MASTER-PROMPT.md"
    if master_prompt.exists():
        mp_content = master_prompt.read_text()
        # Heuristic: any-level Markdown heading mentioning AI, OR an explicit
        # `ai_service` mention in the prose.
        has_ai_section = bool(
            re.search(r"^#{2,}\s+.*\bAI\b", mp_content, re.MULTILINE)
            or "ai_service" in mp_content
        )
        if not has_ai_section:
            issues.append({
                "product": name,
                "file": "MASTER-PROMPT.md",
                "issue": (
                    f"{name} ships `app/services/ai_service.py` but `MASTER-PROMPT.md` "
                    f"has no AI section. An agent reading the master prompt cannot "
                    f"discover the AI surface. Add an `## AI Features` section listing "
                    f"the service functions + endpoints + hooks."
                ),
                "severity": "warning",
            })

    # ── Check 3: cache=True calls thread org_id ──
    service_content = ai_service.read_text()
    # Find every `chat_completion(...)` call block — naive but works for our
    # call style (multi-line with kwargs on separate lines).
    # Pattern: `chat_completion(` ... `)` matching balanced parens at top level.
    for match in re.finditer(r"chat_completion\s*\(", service_content):
        start = match.end()
        # Walk forward to find the matching close paren at depth 0.
        depth = 1
        i = start
        while i < len(service_content) and depth > 0:
            if service_content[i] == "(":
                depth += 1
            elif service_content[i] == ")":
                depth -= 1
            i += 1
        block = service_content[start : i - 1]
        # Only check if cache=True is in this call block.
        if not re.search(r"\bcache\s*=\s*True\b", block):
            continue
        if not re.search(r"\borg_id\s*=", block):
            line_num = service_content[:match.start()].count("\n") + 1
            issues.append({
                "product": name,
                "file": f"backend/app/services/ai_service.py:{line_num}",
                "issue": (
                    f"{name} has a `chat_completion(..., cache=True, ...)` call without "
                    f"`org_id=`. The cache key includes org_id (since 2026-04-24 G5 fix); "
                    f"omitting it puts the call into the platform-wide cache pool. Pass "
                    f"`org_id=org_id` to isolate per-org cache entries."
                ),
                "severity": "high",
            })

    return issues


def _find_all_project_md(repo_root: Path) -> list[Path]:
    """Find every PROJECT.md across the repo's three valid locations.

    Per `KB § PATTERNS/architect/project-execution.md §1` (the three-location project
    rule): root `projects/<slug>/`, `products/<product>/projects/<slug>/`,
    and `core/projects/<slug>/`. Returns sorted paths so iteration is
    deterministic across runs.
    """
    candidates: list[Path] = []
    root_projects = repo_root / "projects"
    if root_projects.exists():
        for d in sorted(root_projects.iterdir()):
            if d.is_dir() and (d / "PROJECT.md").exists():
                candidates.append(d / "PROJECT.md")
    products_dir = repo_root / "products"
    if products_dir.exists():
        for product_dir in sorted(products_dir.iterdir()):
            projects_dir = product_dir / "projects"
            if not projects_dir.exists():
                continue
            for d in sorted(projects_dir.iterdir()):
                if d.is_dir() and (d / "PROJECT.md").exists():
                    candidates.append(d / "PROJECT.md")
    core_projects = repo_root / "core" / "projects"
    if core_projects.exists():
        for d in sorted(core_projects.iterdir()):
            if d.is_dir() and (d / "PROJECT.md").exists():
                candidates.append(d / "PROJECT.md")
    return candidates


# `### Phase N` (numeric only — skips illustrative `### Phase X` placeholders
# in §5 architecture sections that aren't actual phases).
_PHASE_HEADER_RE = re.compile(r'^### Phase\s+(\d+)\b(.*)$', re.MULTILINE)
_SUBTASK_RE = re.compile(r'^[ \t]*-\s*\[([ x])\]\s', re.MULTILINE)
_IMPROVEMENTS_BLOCK_RE = re.compile(r'\*\*Improvements\b[^*]*\*\*', re.MULTILINE)
_NON_SHIPPED_ICONS = {"⏳", "❌", "🅿️"}
_SHIPPED_ICON = "✅"

# Greppable sentinel that `templates/PROJECT-TEMPLATE.md` ships INSIDE every
# phase's `**Improvements:**` block, so agents can never silently SKIP the
# (obligatory) block. Rule 5 fails a `✅` phase whose block still carries it —
# forcing a real fill ("none identified." counts; the placeholder does not).
# Find unfilled blocks with `grep -rn NOC-FILL-IMPROVEMENTS`.
_IMPROVEMENTS_PLACEHOLDER = "NOC-FILL-IMPROVEMENTS"


def _icon_in_line(line: str) -> str | None:
    """Return the first phase-status icon found in a line, or None."""
    for icon in (_SHIPPED_ICON, "⏳", "❌", "🅿️"):
        if icon in line:
            return icon
    return None


def _split_phase_blocks(content: str) -> list[tuple[int, str, int]]:
    """Split a PROJECT.md into phase blocks.

    Returns list of `(phase_number, block_text, header_line_number)`. The
    block_text spans from one `### Phase N` header up to the next `###`
    header, `## ` section boundary, or end of file.
    """
    headers: list[tuple[int, int, int]] = []  # (number, start_offset, line_number)
    for m in _PHASE_HEADER_RE.finditer(content):
        try:
            phase_num = int(m.group(1))
        except (ValueError, TypeError) as exc:
            logger.warning("compliance: cannot parse phase number from %r (%s), skipping", m.group(0), exc)
            continue
        line_num = content.count("\n", 0, m.start()) + 1
        headers.append((phase_num, m.start(), line_num))
    blocks: list[tuple[int, str, int]] = []
    for i, (num, start, ln) in enumerate(headers):
        # Block ends at next phase header OR next ## section boundary (whichever
        # comes first). Anchor the section search AFTER this header's own line —
        # otherwise the `^## ` pattern matches the `### Phase` header itself.
        next_start = len(content)
        if i + 1 < len(headers):
            next_start = headers[i + 1][1]
        newline_after_header = content.find("\n", start)
        body_start = newline_after_header + 1 if newline_after_header >= 0 else len(content)
        section_match = re.search(
            r'^##\s', content[body_start:next_start], re.MULTILINE,
        )
        if section_match:
            next_start = min(next_start, body_start + section_match.start())
        blocks.append((num, content[start:next_start], ln))
    return blocks


def _extract_changelog_section(content: str) -> str:
    """Return the §11 Change log section text (table rows + prose), or ''."""
    m = re.search(r'^##\s*11\.\s*Change\s*log\b', content, re.MULTILINE | re.IGNORECASE)
    if not m:
        return ""
    return content[m.start():]


_CHANGELOG_PHASE_SHIPPED_RE = re.compile(
    r'Phase\s+(\d+)\s*(?:[—:✅\-]|.{0,40}?(?:shipped|closed|complete))',
    re.IGNORECASE,
)

# Inline code spans — single-line backtick-delimited content. Markdown
# convention: backticks mark "this is a code/identifier/reference, not
# prose." We strip them before phase-shipped detection so a §11 entry
# describing ANOTHER file's state (e.g. `Phase 0 ✅` of erp-imobiliario-
# wiring while authoring repo-state-consolidation-wave-2's §11) does NOT
# false-positive as a self-claim. Single-source convention: backtick a
# phrase = "reference, not self-claim." No new syntax; markdown already
# has it.
_INLINE_CODE_SPAN_RE = re.compile(r'`[^`\n]*`')


def _strip_code_spans(text: str) -> str:
    """Strip inline code spans (backtick-delimited, single-line) from markdown.

    Used to normalize §11 changelog text before phase-shipped detection so
    cross-file references (like ``Phase 0 ✅`` describing another project's
    state) don't trigger self-claim heuristics. Preserves all other text;
    code spans become single spaces (preserves word boundaries for downstream
    regexes).
    """
    return _INLINE_CODE_SPAN_RE.sub(" ", text)


def _shipped_phases_in_changelog(changelog: str) -> set[int]:
    """Find phase numbers THIS file's §11 changelog claims as shipped/closed.

    Heuristic: look for "Phase N ✅", "Phase N shipped", "Phase N closed",
    "Phase N complete". Only counts phases that appear with explicit
    shipped/closed markers — bare "Phase N" mentions in passing don't
    qualify (e.g. "Phase 0 audit found...").

    Cross-file references should be wrapped in backticks per the markdown
    convention; backticked spans are stripped before matching so that a §11
    entry describing another project's `Phase 0 ✅` does not false-positive
    as a self-claim. See `_strip_code_spans`.
    """
    shipped: set[int] = set()
    # Strip inline code spans first — backticked references describe other
    # files' state, not this file's claims.
    sanitized = _strip_code_spans(changelog)
    # Look for "Phase N ✅" anywhere in changelog
    for m in re.finditer(r'Phase\s+(\d+)\s*✅', sanitized):
        try:
            shipped.add(int(m.group(1)))
        except ValueError as exc:
            logger.warning("compliance: cannot parse phase number from %r (%s)", m.group(0), exc)
            continue
    # Look for "Phase N shipped" / "Phase N closed" with small lookahead
    for m in re.finditer(
        r'Phase\s+(\d+)\b[^.]{0,80}?(?:shipped|closed|complete)',
        sanitized,
        re.IGNORECASE,
    ):
        try:
            shipped.add(int(m.group(1)))
        except ValueError as exc:
            logger.warning("compliance: cannot parse phase number from %r (%s)", m.group(0), exc)
            continue
    return shipped


def check_phase_state_consistency(repo_root: Path | None = None) -> list[dict]:
    """Validate §6 ↔ §11 consistency in every PROJECT.md.

    The slip pattern this catches: an agent writes a §11 Change-Log entry
    saying "Phase N ✅ shipped" but leaves §6's checkboxes / phase header
    in their pre-close state. The user reads §6 as a real-time dashboard;
    the mismatch is functionally a lie about progress.

    Detection rules (per `KB § PATTERNS/architect/project-execution.md § 2 Self-check
    before claiming a phase is done`):

    1. Phase header lacks ✅ icon BUT §11 says "Phase N shipped" → drift.
    2. Phase header has ✅ icon BUT some sub-tasks are `- [ ]` → drift.
    3. Phase header has ✅ icon BUT no `**Improvements:**` block → drift.
    4. §11 says "Phase N shipped" BUT sub-tasks are `- [ ]` → drift.

    Phases marked `⏳`, `❌`, or `🅿️` (partial / blocked / parked) are
    legitimate non-shipped states; not flagged.

    Per `KB § 06-AGENTS.md` (observation-only keeper rule): the detector
    REPORTS, never modifies. The fix is the agent's discipline.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    for project_md in _find_all_project_md(root):
        content = project_md.read_text(encoding="utf-8")
        try:
            relative = project_md.relative_to(root)
        except ValueError:
            logger.warning("compliance: PROJECT.md outside repo root, using absolute: %s", project_md)
            relative = project_md
        product_label = "<projects>"
        # Resolve product attribution for nicer issue grouping.
        rel_str = str(relative)
        if rel_str.startswith("products/"):
            product_label = rel_str.split("/", 2)[1]
        elif rel_str.startswith("core/"):
            product_label = "core"

        phase_blocks = _split_phase_blocks(content)
        changelog = _extract_changelog_section(content)
        shipped_in_changelog = _shipped_phases_in_changelog(changelog)

        for phase_num, block, header_ln in phase_blocks:
            # First line is the header; the rest is the body.
            header_line = block.split("\n", 1)[0]
            body = block[len(header_line):]
            icon = _icon_in_line(header_line)

            # Skip non-shipped legitimate states.
            if icon in _NON_SHIPPED_ICONS:
                continue

            subtasks = _SUBTASK_RE.findall(body)
            unticked_count = sum(1 for s in subtasks if s == " ")
            has_improvements = bool(_IMPROVEMENTS_BLOCK_RE.search(body))

            is_shipped_per_changelog = phase_num in shipped_in_changelog
            header_has_check = icon == _SHIPPED_ICON

            # Rule 1: header missing ✅ but §11 says shipped.
            if is_shipped_per_changelog and not header_has_check:
                issues.append({
                    "product": product_label,
                    "file": rel_str,
                    "issue": (
                        f"Phase {phase_num} of `{rel_str}` (line {header_ln}) lacks the "
                        f"`✅` icon in §6 header, but §11 Change Log says it shipped. "
                        f"Either flip the header to `✅` (if truly shipped) or remove the "
                        f"shipped claim from §11 (if not). Per `KB § PATTERNS/project-"
                        f"execution.md § 2 Self-check before claiming a phase is done`."
                    ),
                    "severity": "high",
                })

            # Rule 2: header has ✅ but some sub-tasks unticked.
            if header_has_check and unticked_count > 0:
                issues.append({
                    "product": product_label,
                    "file": rel_str,
                    "issue": (
                        f"Phase {phase_num} of `{rel_str}` (line {header_ln}) header carries "
                        f"`✅` but {unticked_count} sub-task(s) remain `- [ ]`. Tick the "
                        f"checkboxes or revert the header to `⏳` until done."
                    ),
                    "severity": "high",
                })

            # Rule 3: header has ✅ but no Improvements block.
            if header_has_check and not has_improvements:
                issues.append({
                    "product": product_label,
                    "file": rel_str,
                    "issue": (
                        f"Phase {phase_num} of `{rel_str}` (line {header_ln}) header carries "
                        f"`✅` but lacks an `**Improvements:**` block. Add the block (or "
                        f"`**Improvements:** none identified.`) before flipping `✅` per the "
                        f"5-point self-check."
                    ),
                    "severity": "high",
                })

            # Rule 5: header has ✅ AND an Improvements block, but the block
            # still carries the template's unfilled placeholder — i.e. the
            # obligatory block shipped but was never actually filled. A real
            # fill is required ("none identified." counts; the placeholder does
            # not). Greppable: `grep -rn NOC-FILL-IMPROVEMENTS`.
            if header_has_check and has_improvements and _IMPROVEMENTS_PLACEHOLDER in body:
                issues.append({
                    "product": product_label,
                    "file": rel_str,
                    "issue": (
                        f"Phase {phase_num} of `{rel_str}` (line {header_ln}) header carries "
                        f"`✅` but its `**Improvements:**` block still contains the unfilled "
                        f"template placeholder (`{_IMPROVEMENTS_PLACEHOLDER}`). FILL it — list the "
                        f"methodology improvements spotted this phase, or write "
                        f"`**Improvements:** none identified.` — before flipping `✅`. The block is "
                        f"obligatory AND must not remain the default placeholder."
                    ),
                    "severity": "high",
                })

            # Rule 4: §11 says shipped but sub-tasks are unticked (covers cases
            # where header was unflipped AND tasks unticked AND §11 already claims shipped —
            # this is the dashboard-lying case, distinct from rule 1).
            if is_shipped_per_changelog and not header_has_check and unticked_count > 0:
                issues.append({
                    "product": product_label,
                    "file": rel_str,
                    "issue": (
                        f"Phase {phase_num} of `{rel_str}` (line {header_ln}) is claimed shipped "
                        f"in §11 but has {unticked_count} unticked sub-task(s) AND no `✅` icon "
                        f"on the header. Live state lags the narrative — fix §6 before §11 lands."
                    ),
                    "severity": "high",
                })

    return issues


# ---------------------------------------------------------------------------
# `check_no_self_monkeypatch` — enforces the no-self-monkeypatching rule
# (memory `feedback_no_monkeypatching_in_tests.md`, CLAUDE.md). Caught
# 2× this session writing `monkeypatch.setattr(ai_pipeline, "require",
# _noop)`. Documentation alone wasn't sufficient; deterministic
# enforcement closes the loop.
# ---------------------------------------------------------------------------

# Module prefixes that are "ours" (production code in this repo). Patching
# any of these in tests neuters our own logic — UNLESS the target attribute
# is a known boundary accessor (see _BOUNDARY_ACCESSOR_NAMES).
_OUR_MODULE_PREFIXES: tuple[str, ...] = (
    "app.",
    "noctusai_lib.",
    "noctusai_seed.",
)
# Boundary-accessor attribute names — patching these returns external
# resources (Supabase client, LLM SDK, network) that legitimately need
# mocking in tests. Allowed even when the module prefix is "ours".
_BOUNDARY_ACCESSOR_NAMES: set[str] = {
    # Supabase / DB client boundary
    "get_client",
    "get_admin_client",
    "get_core_client",
    "get_db_client",
    "get_supabase",
    "get_supabase_client",
    "get_session",
    "get_user",
    "get_current_user",
    "make_supabase_client",
    "create_client",
    # LLM call boundary
    "chat_completion",
    "chat_completion_stream",
    "stream_chat_completion",
    "transcribe_audio",
    "generate_embedding",
    # Audit-log boundary — `log_action` writes to the `audit_log` table.
    # Patching it in tests is the standard "skip side-effect" pattern
    # used everywhere; the alternative would require seeding RLS-coupled
    # audit-log rows for every test. Triaged 2026-04-28 from 27 hits.
    "log_action",
    # Credential/secrets boundary — `resolve_credential` /
    # `check_required_credentials` read from the secrets store; private
    # `_get_*_token` helpers wrap external auth fetches. Triaged 2026-04-28
    # from 22+6+5 hits.
    "resolve_credential",
    "check_required_credentials",
    "_get_infosimples_token",
    # External SDK getters (return Resend/etc clients).
    "_get_resend",
    "_get_resend_config",
    "_resolve_resend_config",
    # Env-config readers — return cached env state, no business logic.
    "get_whatsapp_config_from_env",
    "check_openai_configured",
    "_openai_configured",
    "YFINANCE_AVAILABLE",
    # JWT decoder boundary — wraps cryptographic verification of an
    # external token; patching skips a real signing key in tests.
    "__from_token__",
}
# Boundary-accessor patterns by suffix (for `_get_<x>_token`,
# `_get_<x>_client`, `_get_<x>_config`-style getters that wrap external
# resource access). Caught at run-time by `_is_boundary_accessor_target`.
_BOUNDARY_ACCESSOR_REGEXES: tuple[re.Pattern[str], ...] = (
    re.compile(r"^_get_[a-z][a-z0-9_]*_(?:token|client|config|key|secret|sdk)$"),
    re.compile(r"^get_[a-z][a-z0-9_]*_(?:client|config|sdk)$"),
    # `_lib_*` — convention for in-product wrappers around `noctusai_lib.*`
    # external integrations (e.g. `_lib_generate_embedding` proxies
    # `noctusai_lib.integrations.llm.generate_embedding`). Patching these mocks the
    # boundary, not our own logic.
    re.compile(r"^_lib_[a-z][a-z0-9_]*$"),
    # `send_*_email` — Resend / SMTP email boundary helpers. Mocking the
    # outbound email is the standard test pattern; the alternative is a
    # network call to a real provider.
    re.compile(r"^send_[a-z][a-z0-9_]*_email$"),
)
# External library names — when an external symbol is re-imported through
# our module (e.g. `app.routers.X.httpx.AsyncClient`), the test is
# legitimately patching the EXTERNAL lib's behavior at the import site.
# Detected by checking if any segment of the dotted path matches.
_EXTERNAL_LIB_NAMES: set[str] = {
    "httpx", "requests", "urllib", "urllib3", "openai", "anthropic",
    "google", "supabase", "redis", "stripe", "resend", "boto3",
    "smtplib", "sendgrid", "twilio", "celery", "kombu", "asyncpg",
    "psycopg2", "psycopg", "sqlalchemy", "pymongo", "elasticsearch",
    "fakeredis", "moto",
}
# Allowlist: bypass via inline comment `# self-patch-ok: <reason>` on the
# patching line itself. For genuinely-rare legitimate cases that don't
# fit the boundary-accessor pattern.
_SELF_PATCH_OK_COMMENT_RE = re.compile(r"#\s*self-patch-ok\b", re.IGNORECASE)

# Severity ratchet: products that have reached 0 self-monkeypatches get the
# detector at severity `high` so new violations block CI; the rest stay at
# `warning` while their historical debt drains. Per `KB § PATTERNS/compliance/testing.md
# § Severity ratchet`. When this set covers every product, the per-product
# carve-out is dropped and the detector goes `high` repo-wide.
_NO_SELF_MONKEYPATCH_HIGH_SEVERITY_PRODUCTS: frozenset[str] = frozenset({
    "therapy-platform",  # ratcheted 2026-05-01 (closed `therapy-tests-no-self-patch`)
    "social-wiring",  # ratcheted 2026-05-24 (closed `social-wiring-settings-di-rewrite`: 43→0)
})


def _is_boundary_accessor_target(full_target: str) -> bool:
    """True if the patched target's last component is a known boundary
    accessor (e.g. `noctusai_seed.database.DatabaseModule.get_client`).
    """
    if not full_target:
        return False
    last = full_target.rstrip(".").rsplit(".", 1)[-1]
    if last in _BOUNDARY_ACCESSOR_NAMES:
        return True
    return any(rx.match(last) for rx in _BOUNDARY_ACCESSOR_REGEXES)


def _has_external_lib_segment(full_target: str) -> bool:
    """True if any dotted segment is a known external lib name. Handles
    the `app.routers.X.httpx.AsyncClient` case (httpx re-imported via
    our module — the test is patching httpx's behavior at the import site,
    which is the standard mock pattern for external network/SDK clients).
    """
    if not full_target:
        return False
    segments = full_target.rstrip(".").split(".")
    return any(seg in _EXTERNAL_LIB_NAMES for seg in segments)


def _classify_patch_target(target: str) -> str:
    """Return 'ours' / 'boundary' / 'external' / 'external-via-ours' / 'unknown'."""
    if not any(target.startswith(p) for p in _OUR_MODULE_PREFIXES):
        return "external"
    if _is_boundary_accessor_target(target):
        return "boundary"
    if _has_external_lib_segment(target):
        return "external-via-ours"
    return "ours"


def _walk_test_files(root: Path):
    """Yield all `tests/**/*.py` files across products + seed-lib + mcp.

    Excludes vendored dependencies (`node_modules/`, `.venv/`, `venv/`,
    `dist/`) — those contain test code that's not ours and would
    false-positive every check.
    """
    excluded_parts: set[str] = {
        "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
        ".git", ".pytest_cache", ".mypy_cache",
    }
    for base in (
        root / "products",
        root / "seed" / "lib" / "backend",
        root / "seed" / "framework" / "backend",
        root / "mcp",
    ):
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            # Only test files.
            parts = path.parts
            if "tests" not in parts and "test_" not in path.name:
                continue
            if any(part in excluded_parts for part in parts):
                continue
            yield path


def _build_import_map(tree: ast.Module) -> dict[str, str]:
    """Map local-bound names to their full import paths.

    Examples:
    - `from app.services import ai_pipeline` → {"ai_pipeline": "app.services.ai_pipeline"}
    - `from app.services.ai_pipeline import require` → {"require": "app.services.ai_pipeline.require"}
    - `import noctusai_lib.domain.ai.consent as consent` → {"consent": "noctusai_lib.domain.ai.consent"}
    - `from app import services` → {"services": "app.services"}

    Used by `check_no_self_monkeypatch` to resolve `monkeypatch.setattr(X, ...)`
    where X is a local name back to its dotted module path, so we can
    classify it against `_OUR_MODULE_PREFIXES`.
    """
    mapping: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                local_name = alias.asname or alias.name
                full_path = f"{module}.{alias.name}" if module else alias.name
                mapping[local_name] = full_path
        elif isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname or alias.name.split(".")[0]
                mapping[local_name] = alias.asname or alias.name
    return mapping


def _resolve_target_via_imports(target: str, import_map: dict[str, str]) -> str:
    """Resolve a `Name.attr.attr` target against the file's import map.

    `target` is expected to be the dotted path returned by `_extract_patch_target`
    (already includes the attr name when known). The first segment is the
    locally-bound name; if it's in `import_map`, prepend the resolved path.
    """
    if not target:
        return target
    segments = target.split(".")
    head = segments[0]
    if head in import_map:
        # Replace the local name with its resolved full path.
        resolved_head = import_map[head]
        return ".".join([resolved_head] + segments[1:]) if len(segments) > 1 else resolved_head
    return target


def check_no_self_monkeypatch(repo_root: Path | None = None) -> list[dict]:
    """Detect `monkeypatch.setattr(<our_module>, ...)` and
    `unittest.mock.patch.object(<our_module>, ...)` in test files —
    patterns that neuter our own logic instead of testing it.

    Per memory `feedback_no_monkeypatching_in_tests.md` + CLAUDE.md "No
    workarounds — and no monkey-patching, in production OR tests".

    Resolves local-bound names against the file's import map so that
    `from app.services import ai_pipeline` + `monkeypatch.setattr(
    ai_pipeline, "require", ...)` correctly resolves to
    `app.services.ai_pipeline.require` for classification.

    Allowlist via inline comment `# self-patch-ok: <reason>` on the
    patching line. For genuinely-rare legitimate cases (rare enough that
    they should be documented at the call site).
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    for path in _walk_test_files(root):
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.warning("compliance: cannot read test file %s (%s), skipping", path, exc)
            continue
        try:
            tree = ast.parse(content, filename=str(path))
        except SyntaxError as exc:
            logger.warning("compliance: cannot parse test file %s (%s), skipping", path, exc)
            continue
        import_map = _build_import_map(tree)
        try:
            relative = str(path.relative_to(root))
        except ValueError:
            logger.warning("compliance: test file outside repo root, using absolute: %s", path)
            relative = str(path)
        product_label = "<seed-lib>" if "/seed/" in relative else (
            relative.split("/", 2)[1] if relative.startswith("products/") else "<mcp>"
        )

        for node in ast.walk(tree):
            raw_target = _extract_patch_target(node)
            if raw_target is None:
                continue
            target_str = _resolve_target_via_imports(raw_target, import_map)
            classification = _classify_patch_target(target_str)
            if classification != "ours":
                continue
            line_no = getattr(node, "lineno", 0) or 0
            line_text = (
                content.splitlines()[line_no - 1] if 0 < line_no <= len(content.splitlines()) else ""
            )
            if _SELF_PATCH_OK_COMMENT_RE.search(line_text):
                continue
            severity = (
                "high"
                if product_label in _NO_SELF_MONKEYPATCH_HIGH_SEVERITY_PRODUCTS
                else "warning"
            )
            issues.append({
                "product": product_label,
                "file": relative,
                "issue": (
                    f"`{relative}:{line_no}` patches our own symbol "
                    f"`{target_str}`. Per CLAUDE.md \"No workarounds — and no "
                    f"monkey-patching, in production OR tests\": neutering our "
                    f"own logic in tests doesn't test it. Seed real data + use "
                    f"DI; patch only external boundaries (LLM SDKs, network). "
                    f"If genuinely needed, add `# self-patch-ok: <reason>` to "
                    f"the line."
                ),
                # Severity ratchets to `high` once a product reaches 0; until
                # then, `warning` so historical debt doesn't tank score. See
                # `_NO_SELF_MONKEYPATCH_HIGH_SEVERITY_PRODUCTS` above + `KB §
                # PATTERNS/compliance/testing.md § Severity ratchet`.
                "severity": severity,
            })
    return issues


def _extract_patch_target(node: ast.AST) -> str | None:
    """If `node` is a self-patching call, return the FULL dotted-path target
    (module.path + attribute name). Else None.

    Examples returned:
    - `monkeypatch.setattr(ai_pipeline, "require", _noop)` → `"ai_pipeline.require"`
    - `patch.object(DatabaseModule, "get_client", ...)` → `"DatabaseModule.get_client"`
    - `patch("noctusai_seed.database.DatabaseModule.get_client", ...)` →
      `"noctusai_seed.database.DatabaseModule.get_client"`
    """
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    target_arg: ast.expr | None = None
    attr_name: str | None = None

    # Pattern 1: monkeypatch.setattr(<target>, "attr", ...)
    if isinstance(func, ast.Attribute) and func.attr == "setattr":
        if isinstance(func.value, ast.Name) and func.value.id == "monkeypatch":
            if len(node.args) >= 1:
                target_arg = node.args[0]
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                v = node.args[1].value
                if isinstance(v, str):
                    attr_name = v
    # Pattern 2: mock.patch.object(<target>, "attr", ...) / patch.object(...)
    if isinstance(func, ast.Attribute) and func.attr == "object":
        is_patch_object = False
        if isinstance(func.value, ast.Name) and func.value.id == "patch":
            is_patch_object = True
        elif (
            isinstance(func.value, ast.Attribute)
            and func.value.attr == "patch"
        ):
            is_patch_object = True
        if is_patch_object:
            if len(node.args) >= 1:
                target_arg = node.args[0]
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                v = node.args[1].value
                if isinstance(v, str):
                    attr_name = v
    # Pattern 3: mock.patch("<dotted.string>", ...) / patch("<dotted.string>", ...)
    if isinstance(func, ast.Attribute) and func.attr == "patch":
        if node.args and isinstance(node.args[0], ast.Constant):
            val = node.args[0].value
            if isinstance(val, str):
                return val
    if isinstance(func, ast.Name) and func.id == "patch":
        if node.args and isinstance(node.args[0], ast.Constant):
            val = node.args[0].value
            if isinstance(val, str):
                return val

    if target_arg is None:
        return None
    base = _flatten_attr(target_arg)
    if base is None:
        return None
    # `_flatten_attr` returns the dotted path with a trailing `.`; append
    # the attr name when known.
    if attr_name:
        return base + attr_name
    return base.rstrip(".")


def _flatten_attr(node: ast.expr) -> str | None:
    """Convert `a.b.c` AST to `'a.b.c'`. Returns None for non-attribute exprs."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts)) + "."
    return None


# ---------------------------------------------------------------------------
# `check_silent_errors` — enforces the no-silent-errors rule
# (memory `feedback_no_silent_errors.md`, CLAUDE.md). Catches `except: pass`,
# `except Exception: return None`, and similar patterns that swallow
# errors without surfacing them.
# ---------------------------------------------------------------------------

# NOTE — there is intentionally NO escape-hatch comment for this detector.
# The previous `# silent-ok: <reason>` allowlist was retired 2026-04-28
# per user directive: "i dont want any silent-ok sign accross the
# platform". Every except handler MUST log via `logger.<level>(...)`,
# raise, or surface the error through a return value. Even bootstrap-
# time code (e.g. `noctusai_seed._version`) uses `logger.debug(...)` —
# the root logger silently drops debug by default but the call is in
# the code, the detector recognizes it, and operators can flip
# `NOCTUSAI_DEBUG=1` to see what fired during a fresh boot.


def _walk_python_files(root: Path):
    """Yield all `.py` files in product backends + seed-lib + framework + mcp.

    Excludes tests (test code legitimately uses `try/except` for assertions
    on the error paths) + vendored deps (`node_modules/`, `.venv/`, `venv/`,
    `dist/`, `__pycache__/`) + migration files (raw SQL hand-written by
    domain experts; silent-error semantics differ).
    """
    excluded_parts: set[str] = {
        "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
        ".git", ".pytest_cache", ".mypy_cache", "tests", "migrations",
    }
    bases = [
        root / "products",
        root / "seed" / "lib" / "backend",
        root / "seed" / "framework" / "backend",
        root / "mcp" / "noctusai",
    ]
    for base in bases:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            parts = path.parts
            if any(part in excluded_parts for part in parts):
                continue
            yield path


def _is_silent_except(handler: ast.ExceptHandler) -> tuple[bool, str]:
    """Return (is_silent, reason). A handler is "silent" if its body:
       - is just `pass`
       - is just `return None` / `return`
       - has no `raise`, no `logger.<level>`, no `log.<level>`, no `print` for the error.
    """
    body = handler.body
    if not body:
        return True, "empty body"
    # All-pass / all-return cases:
    if all(isinstance(stmt, ast.Pass) for stmt in body):
        return True, "body is just `pass`"
    if all(
        isinstance(stmt, ast.Return)
        and (stmt.value is None or (
            isinstance(stmt.value, ast.Constant) and stmt.value.value is None
        ))
        for stmt in body
    ):
        return True, "body is just `return` / `return None`"
    # Look for any signal of error-handling: raise, logger call, print.
    # Bare-name allowlist is deliberately TIGHT — only `print(...)` qualifies
    # because anything else (`warn(exc)`, `warning(exc)`) is too easy to
    # accidentally satisfy with a domain function of the same name. Logger
    # calls are recognised via the attribute-suffix pattern (`.warning`,
    # `.warn` legacy, etc.), which requires a method-call shape.
    has_signal = False
    for stmt in ast.walk(handler):
        if isinstance(stmt, ast.Raise):
            has_signal = True
            break
        if isinstance(stmt, ast.Call):
            func_name = _call_name(stmt.func)
            if func_name == "print":
                has_signal = True
                break
            if any(
                func_name.endswith(suffix) for suffix in (
                    ".warning", ".warn",  # `.warn` is the deprecated stdlib alias; some callers still use it
                    ".error", ".exception", ".critical",
                    ".info", ".debug", ".log",
                )
            ):
                has_signal = True
                break
    if not has_signal:
        return True, "no `raise` / `log` / `print` in handler body"
    return False, ""


def _call_name(func_node: ast.expr) -> str:
    if isinstance(func_node, ast.Name):
        return func_node.id
    if isinstance(func_node, ast.Attribute):
        return f".{func_node.attr}"
    return ""


def check_silent_errors(repo_root: Path | None = None) -> list[dict]:
    """Detect silent-error patterns in production Python code.

    Flags `try / except:` handlers whose body neither raises, logs, nor
    surfaces the error in any way. **No escape hatch** — every handler
    must log via `logger.<level>(...)`, `raise`, or surface through a
    return value. Even bootstrap-time code uses `logger.debug(...)` so
    the call is statically present (root logger drops it by default;
    `NOCTUSAI_DEBUG=1` reveals it).

    Per memory `feedback_no_silent_errors.md` + CLAUDE.md "No silent
    errors — always explicit fix opportunities".
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    for path in _walk_python_files(root):
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.warning("compliance: cannot read %s (%s), skipping", path, exc)
            continue
        try:
            tree = ast.parse(content, filename=str(path))
        except SyntaxError as exc:
            logger.warning("compliance: cannot parse %s (%s), skipping", path, exc)
            continue
        try:
            relative = str(path.relative_to(root))
        except ValueError:
            logger.warning("compliance: file outside repo root, using absolute: %s", path)
            relative = str(path)
        product_label = "<seed>" if relative.startswith("seed/") else (
            relative.split("/", 2)[1] if relative.startswith("products/") else "<mcp>"
        )
        lines = content.splitlines()

        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            silent, reason = _is_silent_except(node)
            if not silent:
                continue
            line_no = node.lineno
            issues.append({
                "product": product_label,
                "file": relative,
                "issue": (
                    f"`{relative}:{line_no}` swallows errors silently ({reason}). "
                    f"Per CLAUDE.md \"No silent errors\": every failure mode "
                    f"surfaces loudly. Add `logger.warning(...)` / `logger.debug(...)`, "
                    f"`raise`, or surface via a return value. Bootstrap-time code "
                    f"uses `logger.debug(...)` (silent by default; `NOCTUSAI_DEBUG=1` "
                    f"reveals it). There is no `# silent-ok` escape hatch."
                ),
                # `warning` (not `high`) so legitimate-but-historically-flagged
                # patterns don't tank the per-product score; the user can
                # tighten over time as violations are addressed.
                "severity": "warning",
            })
    return issues


# ---------------------------------------------------------------------------
# `check_clean_folder_violations` — enforces the clean-folder rule
# (CLAUDE.md). ✅-closed projects must have their folders deleted.
# ---------------------------------------------------------------------------


def check_clean_folder_violations(repo_root: Path | None = None) -> list[dict]:
    """Detect closed projects (✅ status) whose folders still exist.

    Per CLAUDE.md "Clean folder — every artifact has a home" + the
    apply-inline-then-delete rule (closed projects get deleted at close,
    audit history lives in git). Surfaced 8 violations during the
    2026-04-28 closed-folder cleanup; this check makes future drift
    visible at `--validate` time.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    for project_md in _find_all_project_md(root):
        try:
            content = project_md.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.warning("compliance: cannot read PROJECT.md %s (%s), skipping", project_md, exc)
            continue
        # Look at the first `- **Status:**` line.
        m = re.search(r"^- \*\*Status:\*\*\s*(.*)$", content, re.MULTILINE)
        if not m:
            continue
        status_line = m.group(1)
        # The status icon is whatever comes FIRST on the line. A trailing
        # `Phase 0 ✅` inside narrative ("READY TO RESUME ... Phase 0 ✅
        # executed") is not the project's own status — that's drift inside
        # the prose. Only flag when ✅ is the leading icon.
        leading = re.match(r"\s*([📋⏳❌🅿️📝✅⚠️🚧🔄])", status_line)
        if not leading or leading.group(1) != "✅":
            continue
        # Mixed-status close (✅ leading but ⏳/❌/🅿️ also present) signals
        # in-flight close — don't flag.
        if any(icon in status_line for icon in ("⏳", "❌", "🅿️")):
            continue
        # Closed + folder still exists → flag.
        try:
            relative = str(project_md.relative_to(root))
        except ValueError:
            logger.warning("compliance: PROJECT.md outside repo root, using absolute: %s", project_md)
            relative = str(project_md)
        product_label = "<projects>"
        if relative.startswith("products/"):
            product_label = relative.split("/", 2)[1]
        elif relative.startswith("core/"):
            product_label = "core"
        issues.append({
            "product": product_label,
            "file": relative,
            "issue": (
                f"`{relative}` is closed (✅) but its folder still exists. "
                f"Per the clean-folder rule (CLAUDE.md): closed projects "
                f"get deleted at close — audit history lives in git + the "
                f"shipped code + KB cross-references. Run `rm -rf "
                f"{project_md.parent.relative_to(root) if project_md.parent.is_relative_to(root) else project_md.parent}/` "
                f"after confirming references are updated."
            ),
            "severity": "warning",
        })
    return issues


# ---------------------------------------------------------------------------
# `check_test_status_assertion` — every pytest test method that asserts on
# response BODY (`.text`, `.json()`, `.content`) must also assert on response
# STATUS CODE (`.status_code`) in the same method. Defends against the
# YouTube Crawler Phase 1 "false-green" slip where a substring-on-`.text`
# assertion matched the wrong of two error entries (broken `Depends(get_org_id)`
# chain) and the test went green even though the endpoint was unusable.
# Project: keeper-test-status-assertion. Per KB § PATTERNS/compliance/testing.md
# § Status-code-assertion rule.
# ---------------------------------------------------------------------------


# Attribute names that, when accessed on a response variable, indicate the
# test is asserting on the response body. Match by attribute name, not
# variable name (the test author's variable name doesn't matter).
_RESPONSE_BODY_ATTRS: frozenset[str] = frozenset({"text", "content"})
# Method names that, when called on a response variable, indicate body access.
_RESPONSE_BODY_METHODS: frozenset[str] = frozenset({"json"})
# The status-code attribute. Any comparison op against this (==, in, !=, <, >)
# satisfies the rule.
_STATUS_CODE_ATTR: str = "status_code"


# HTTP method names — any of these called as `<var>.method(...)` (or
# `await <var>.method(...)`) on the right-hand side of an assignment binds
# `<var name on left>` to a "response variable" for the rest of the method.
# Used to gate body-attr matches so non-response objects (`digest.text`,
# `result.content`) don't false-positive.
_HTTP_METHOD_NAMES: frozenset[str] = frozenset({
    "get", "post", "put", "patch", "delete", "head", "options",
    "request",  # generic httpx/TestClient `client.request("GET", ...)`
})


def _collect_response_vars(fn: ast.AST) -> set[str]:
    """Walk a test method body and collect names that were assigned from
    an HTTP-client call.

    Examples that bind:
      - ``resp = client.get("/x")``
      - ``resp = await client.post("/x", json={})``
      - ``response = self.client.delete("/x/1")``
      - ``r = test_client.request("GET", "/x")``

    Examples that DO NOT bind (intentional false-negative bias):
      - ``digest = audit_digest_service.build_digest(...)`` — non-HTTP call
      - ``result = handler(...)`` — non-HTTP call
      - ``resp = some_helper(client)`` — opaque helper return

    Conservative on purpose: a body-attr match against a name NOT in this
    set is silently skipped, dropping false positives like `digest.text` /
    `result.content`. Cost: a test that uses a helper-returned response
    won't be flagged. PROJECT.md § 3 design principle 3 accepts that miss.
    """
    response_vars: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign):
            continue
        # Only single-target assignments — `resp = client.get(...)`.
        # Tuple-unpack / chained assignments left as future work.
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        target_name = node.targets[0].id
        # Unwrap `await client.get(...)`.
        value = node.value
        if isinstance(value, ast.Await):
            value = value.value
        if not isinstance(value, ast.Call):
            continue
        # Inspect the call's func — must be an Attribute access whose
        # method name is one of the HTTP verbs.
        func = value.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr not in _HTTP_METHOD_NAMES:
            continue
        response_vars.add(target_name)
    return response_vars


def _expr_root_name(node: ast.AST) -> str | None:
    """For an attribute / subscript / call chain, walk down to the root
    Name node and return its identifier.

    ``resp.text.lower()`` → ``"resp"``
    ``resp.json()["x"]`` → ``"resp"``
    ``self.client.get(...).text`` → ``None`` (root is `self`, but the
    walker only treats top-level local Names as response candidates).
    ``some_func().text`` → ``None``
    """
    cur = node
    while True:
        if isinstance(cur, ast.Name):
            return cur.id
        if isinstance(cur, ast.Attribute):
            cur = cur.value
        elif isinstance(cur, ast.Subscript):
            cur = cur.value
        elif isinstance(cur, ast.Call):
            cur = cur.func
        else:
            return None


def _is_body_text_assertion(node: ast.Assert, response_vars: set[str]) -> bool:
    """True iff this assert reads response BODY on a known response var.

    Catches:
      - ``assert "x" in resp.text``
      - ``assert "x" in resp.text.lower()``
      - ``assert "x" in resp.json()["error"]``
      - ``assert resp.text == "..."``
      - ``assert "..." == resp.json()["msg"]``
      - ``assert resp.content``  (truthy check on body)

    Gated by `response_vars` (names assigned from `client.<verb>(...)` in
    the same method): only flags when the body-attr access's root Name is
    in the response set. Drops false positives like `digest.text` /
    `result.content` on non-HTTP objects.

    Conservative: when the root expression isn't a simple local Name (e.g.
    `self.client.get(...).text` — fluent style), we silently skip.
    """
    test = node.test
    for sub in ast.walk(test):
        if isinstance(sub, ast.Attribute) and sub.attr in _RESPONSE_BODY_ATTRS:
            root = _expr_root_name(sub.value)
            if root is not None and root in response_vars:
                return True
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            if sub.func.attr in _RESPONSE_BODY_METHODS:
                root = _expr_root_name(sub.func.value)
                if root is not None and root in response_vars:
                    return True
    return False


def _is_status_code_assertion(node: ast.Assert) -> bool:
    """True iff this assert reads ``.status_code`` on something.

    Catches every comparison shape:
      - ``assert resp.status_code == 200``
      - ``assert resp.status_code in (401, 403)``
      - ``assert resp.status_code != 500``
      - ``assert 400 <= resp.status_code < 500``
      - ``assert resp.status_code``  (truthy — rare but counted)

    Note: status_code attr name is specific enough to HTTP responses that
    we don't gate it on response_vars (a non-response object asserting
    `.status_code` is exotic and we'd rather count it than miss).
    """
    for sub in ast.walk(node.test):
        if isinstance(sub, ast.Attribute) and sub.attr == _STATUS_CODE_ATTR:
            return True
    return False


def _iter_test_methods(tree: ast.Module):
    """Yield every ``def test_*`` function — module-level or class-nested.

    Only synchronous + async function defs whose name starts with ``test_``
    are returned. Helper functions (any other name) are not scanned per
    PROJECT.md § 3 design principle 1 (method-scope detection).
    """
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                yield node


def _walk_test_files_in_dir(tests_dir: Path):
    """Yield every ``test_*.py`` / ``*_test.py`` file under tests_dir.

    Excludes vendored / cache / build directories (same exclusion list as
    `_walk_test_files`). conftest.py is included — it contains fixtures
    that may inadvertently mask response semantics, but no `test_*` methods
    so the detector skips them naturally.
    """
    excluded_parts: set[str] = {
        "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
        ".git", ".pytest_cache", ".mypy_cache",
    }
    if not tests_dir.exists():
        return
    for path in tests_dir.rglob("*.py"):
        if any(part in excluded_parts for part in path.parts):
            continue
        # Match pytest's default test-file discovery pattern.
        if path.name.startswith("test_") or path.name.endswith("_test.py"):
            yield path


def check_test_status_assertion(product_path: Path) -> list[dict]:
    """Flag pytest test methods that assert on response BODY without a
    sibling assertion on response STATUS CODE in the same method.

    The slip this defends against (YouTube Crawler Phase 1):

        def test_recipient_without_channel_rejected(self, client):
            resp = client.post("/api/settings/recipients", json={"name": "x"})
            assert "at least one of" in resp.text.lower()
            # ↑ went green because 422 contained TWO error entries; the
            #   substring matched the schema-validation entry but the
            #   endpoint was actually unusable due to a broken
            #   Depends(get_org_id) chain demanding ?user= / ?token=.

    The structural fix: any test asserting on body text/JSON/content also
    pins the status code in the same method. Without that pin, a 422 / 500
    / 401 / 403 false-green is structurally possible.

    Conservative: false negatives over false positives. We do NOT walk into
    helper functions (test author's `_assert_ok(resp)` may handle status
    code there — we trust that and don't flag the test). We do NOT track
    response-variable identity — both assertions must merely exist in the
    same method body.

    Per KB § PATTERNS/compliance/testing.md § Status-code-assertion rule.
    """
    issues: list[dict] = []
    name = product_path.name
    tests_dir = product_path / "backend" / "tests"
    if not tests_dir.exists():
        return issues

    for py_file in _walk_test_files_in_dir(tests_dir):
        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("compliance: cannot read %s (%s)", py_file, exc)
            continue
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError as exc:
            logger.debug("compliance: cannot parse %s (%s)", py_file, exc)
            continue

        try:
            rel = str(py_file.relative_to(product_path))
        except ValueError:
            rel = str(py_file)

        for fn in _iter_test_methods(tree):
            response_vars = _collect_response_vars(fn)
            if not response_vars:
                # No HTTP-client call assigned to a local name — skip.
                # Tests using helper-returned responses miss intentionally
                # (PROJECT.md § 3 design principle 3 — conservative).
                continue
            has_body = False
            has_status = False
            first_body_line = 0
            for sub in ast.walk(fn):
                if isinstance(sub, ast.Assert):
                    if not has_body and _is_body_text_assertion(sub, response_vars):
                        has_body = True
                        first_body_line = sub.lineno
                    if not has_status and _is_status_code_assertion(sub):
                        has_status = True
                if has_body and has_status:
                    break
            if has_body and not has_status:
                issues.append({
                    "product": name,
                    "file": rel,
                    "method": fn.name,
                    "line": first_body_line,
                    "issue": (
                        f"{rel}:{first_body_line} `{fn.name}` asserts on "
                        f"response body (`.text` / `.json()` / `.content`) "
                        f"without a sibling `assert <resp>.status_code == "
                        f"...` in the same method. Body-only assertions can "
                        f"go green for the wrong reason — see KB § "
                        f"PATTERNS/compliance/testing.md § Status-code-assertion rule "
                        f"(YouTube Crawler Phase 1 false-green case study)."
                    ),
                    "severity": "warning",
                })
    return issues


# ---------------------------------------------------------------------------
# Production-correctness trio — surfaced by Engineer GG's therapy P4 audit
# (commit a56a39e, 2026-05-10). MockSupabase WARN+skip masked N=12 migration
# drift cases for 7+ days because tests passed silently against unknown tables.
# Two siblings — function search_path drift + admin-endpoint service_role
# bypass — are the same shape (real DB fails, tests pass). All three are
# AST-driven, observation-only, deterministic.
#
# Per KB § PATTERNS/compliance/testing.md § Production-correctness keeper detectors.
# ---------------------------------------------------------------------------


# Tables that MAY appear as `.table("X")` callsites but live OUTSIDE the
# product's own migrations — `auth.users` is Supabase-managed, `products` is
# part of core's bootstrap. Allowlist suppresses false positives at the
# unknown-table detector without weakening cross-product coverage.
_KNOWN_EXTERNAL_TABLES: set[str] = {
    "users",            # auth.users (Supabase auth)
    "products",         # core/bootstrap products registry
    "organizations",    # core/bootstrap org registry (multi-tenancy)
    "user_org_roles",   # core bootstrap RBAC pivot
}


# Files MAY hold a `.table(...)` call that is intentionally a runtime-built
# string concatenated from a variable. The detector ignores non-Constant
# arguments (it CAN'T resolve them statically); this comment is just to
# document the design choice — see `_extract_table_string_arg`.


def _extract_table_string_arg(call: ast.Call) -> str | None:
    """Return the literal string argument to a `.table("X")` call.

    Returns None when the call has no positional args or the first arg is
    not a `Constant[str]` (e.g. an f-string or a name reference — the
    detector silently skips those because it can't resolve them statically).
    """
    if not call.args:
        return None
    first = call.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _walk_product_backend_python(product_path: Path):
    """Yield every `.py` under `product/backend/app/`, excluding tests + caches.

    Mirrors `_walk_python_files` exclusion set but scoped to one product's
    backend (the unknown-table + admin-bypass detectors are per-product).
    """
    backend_app = product_path / "backend" / "app"
    if not backend_app.exists():
        return
    excluded_parts: set[str] = {
        "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
        ".git", ".pytest_cache", ".mypy_cache", "tests", "migrations",
    }
    for path in backend_app.rglob("*.py"):
        if any(part in excluded_parts for part in path.parts):
            continue
        yield path


# Pattern shared by the three production-correctness detectors. The migration
# files are raw SQL; we use regex with the `re.IGNORECASE | re.DOTALL` flags
# and document each regex's anchor strategy near its definition so future
# maintainers can verify the matched shape against real CREATE statements.

# Matches `CREATE TABLE [IF NOT EXISTS] [<schema>.]<name>` and captures the
# unqualified name. Anchored on the `(` opening the column list so we never
# false-match prose mentions of "create table foo" in a comment.
_CREATE_TABLE_RE = re.compile(
    r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?:[A-Za-z_][A-Za-z0-9_]*\.)?"   # optional schema
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"\s*\(",
    re.IGNORECASE,
)


# Matches every `CREATE [OR REPLACE] FUNCTION [<schema>.]<name>` start. We
# don't try to capture the function BODY with one regex (Postgres function
# bodies can use any dollar-quoted delimiter `$tag$ ... $tag$` plus optional
# `SET` clauses outside the body). Instead the detector walks each match and
# finds the body terminator by locating the closing dollar quote — see
# `_function_block_text`.
#
# `or_replace` capture: distinguishes `CREATE FUNCTION ...` (no replace —
# duplicate name would error at apply time, so this is always the FIRST and
# ONLY block for that name) vs `CREATE OR REPLACE FUNCTION ...` (supersedes
# prior blocks of the same name). Used by
# `check_function_search_path_pinned` to flag only the LATEST surviving
# block when a function is redefined across migrations.
_CREATE_FUNCTION_START_RE = re.compile(
    r"\bCREATE\s+(?P<or_replace>OR\s+REPLACE\s+)?FUNCTION\s+"
    r"(?P<qualified>(?:[A-Za-z_][A-Za-z0-9_]*\.)?"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*))"
    r"\s*\(",
    re.IGNORECASE,
)


# Matches `CREATE POLICY "service_role_bypass" ... ON [<schema>.]<table>`
# (DOTALL so the policy clause may span lines between POLICY and ON). We
# match on the literal name `service_role_bypass` because that's the
# convention every product follows (single keeper-enforced shape — drift
# in the name itself is a separate concern and would be its own detector).
#
# Schema prefix accepts both the unquoted form (`therapy.clinics`) and the
# double-quoted form (`"personal-finance".recorrentes`) — dashed schemas
# MUST be double-quoted at DDL time per Postgres identifier rules. Before
# this teach (2026-05-11), only the unquoted prefix matched, causing the
# detector to mis-report PF / mailing / any dashed-schema product as still
# missing the policy even after it was applied. Surfaced by keeper-trio-pf
# (Engineer BBB, Wave 1) when migration 009 applied live + `pg_policies`
# confirmed the policy but the detector kept flagging the callsite.
# Table-name segment continues to be unquoted: every adopter's table name
# is a plain identifier (`recorrentes`, `clinics`, ...), never dashed.
_SERVICE_ROLE_BYPASS_POLICY_RE = re.compile(
    r'\bCREATE\s+POLICY\s+"?service_role_bypass"?\s+ON\s+'
    r'(?:(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_]*)\.)?'
    r"(?P<table>[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE | re.DOTALL,
)


def _collect_known_tables(product_path: Path) -> set[str]:
    """Return unqualified table names declared by `CREATE TABLE` in any of
    the product's migrations. Includes both `IF NOT EXISTS` and bare forms.

    Returns the empty set when `backend/migrations/` is missing (the
    detectors short-circuit upstream in that case).
    """
    names: set[str] = set()
    migrations_dir = product_path / "backend" / "migrations"
    if not migrations_dir.exists():
        return names
    for sql_file in migrations_dir.glob("*.sql"):
        try:
            content = sql_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("compliance: cannot read %s (%s), skipping", sql_file, exc)
            continue
        for m in _CREATE_TABLE_RE.finditer(content):
            names.add(m.group("name").lower())
    return names


def _collect_service_role_bypass_tables(product_path: Path) -> set[str]:
    """Return unqualified table names that have a `service_role_bypass`
    policy in any of the product's migrations.
    """
    names: set[str] = set()
    migrations_dir = product_path / "backend" / "migrations"
    if not migrations_dir.exists():
        return names
    for sql_file in migrations_dir.glob("*.sql"):
        try:
            content = sql_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("compliance: cannot read %s (%s), skipping", sql_file, exc)
            continue
        for m in _SERVICE_ROLE_BYPASS_POLICY_RE.finditer(content):
            names.add(m.group("table").lower())
    return names


def _iter_table_callsites(tree: ast.AST):
    """Yield every `.table("X")` Call node within `tree`.

    Matches any attribute access named `table` regardless of receiver —
    `db.table(...)`, `admin_db.table(...)`, `get_admin_client().table(...)`,
    `self.client.table(...)`. Receiver discrimination happens at the caller
    (the admin-bypass detector uses receiver shape; the unknown-table
    detector flags any `.table(...)`).
    """
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "table"
        ):
            yield node


def _has_schema_in_chain(call: ast.Call) -> bool:
    """True if `call` is `<receiver>.schema(...).…table(...)` — i.e. the
    `.table(...)` invocation is preceded by a `.schema(...)` call anywhere
    in the receiver chain.

    Walks backward from the `.table(...)` call's receiver looking for an
    `ast.Call` whose `.func.attr == "schema"`. Stops at the first non-Call
    receiver (`Name`/`Attribute`/`Subscript`).

    Why this matters — cross-schema lookups (canonical site:
    `products/core/backend/app/routers/admin_llm_usage.py:92`,
    `db.schema(schema).table("llm_usage")` iterating `_PRODUCT_SCHEMAS`)
    target tables in another product's migration tree. The local-schema
    detectors can't verify those without resolving `schema → product slug
    → migrations dir`, which is impossible when the `schema` arg is a
    runtime variable. **Heuristic limit (documented):** we detect the
    *presence* of the `.schema(...)` call regardless of whether its arg
    is a literal or a runtime expression, and skip the local-schema
    check. False-negative trade is acceptable — cross-schema runtime
    failures are loud (Postgres raises on missing schema), unlike the
    silent MockSupabase WARN+skip that the original detector defends
    against.

    Both production-correctness detectors (`check_unknown_table_references`
    + `check_admin_endpoint_service_role_bypass`) gate on this helper.
    The admin-bypass detector also fails its receiver-shape check on
    `db.schema(Y).table(...)` (receiver is a `Call`, not a `Name`/
    `get_admin_client()`), but the explicit skip closes the gap
    structurally so a future receiver-shape refactor doesn't reintroduce
    the false positive.
    """
    if not isinstance(call.func, ast.Attribute):
        return False
    receiver: ast.AST | None = call.func.value
    # Walk backward through call chains: `<x>.schema(...).table(...)`,
    # `<x>.schema(...).foo().table(...)` (rare but legal), etc.
    while isinstance(receiver, ast.Call):
        if (
            isinstance(receiver.func, ast.Attribute)
            and receiver.func.attr == "schema"
        ):
            return True
        # Step further back: descend into the receiver's own receiver.
        if isinstance(receiver.func, ast.Attribute):
            receiver = receiver.func.value
        else:
            # `foo()` style — no further chain.
            receiver = None
    return False


def check_unknown_table_references(product_path: Path) -> list[dict]:
    """Flag `<X>.table("name")` callsites where `name` is not declared by a
    `CREATE TABLE` in the product's migrations.

    The slip this defends against (Engineer GG therapy P4, commit a56a39e):

        # In services/admin_service.py
        db.table("commission_overrides").select(...)
        #          ^^^^^^^^^^^^^^^^^^^^
        # Real schema has `platform_commission_overrides`. MockSupabase
        # WARN+skip returns empty results silently; tests pass; production
        # fails.

    Conservative shape — false negatives over false positives:
      - Skips `.table(<non-string>)` (f-strings, names, attributes — we
        can't resolve them statically without dataflow).
      - Skips tables in :data:`_KNOWN_EXTERNAL_TABLES` (Supabase-managed
        `auth.users`, core-bootstrap `products`/`organizations`).
      - Short-circuits if the product has no `backend/migrations/` —
        scaffold-time products are not yet expected to have a schema.

    Severity `warning` (not `high`) because the cross-cutting drift cases
    surfaced by GG were genuine bugs but the false-positive risk on a
    table that lives in another product's migration tree (cross-product
    schema reference, rare but legitimate) is non-zero. Triage in
    `--review` covers the rest.
    """
    issues: list[dict] = []
    name = product_path.name
    backend_app = product_path / "backend" / "app"
    migrations = product_path / "backend" / "migrations"
    if not backend_app.exists() or not migrations.exists():
        return issues

    known = _collect_known_tables(product_path)
    if not known:
        # No CREATE TABLE found — likely a scaffold or a product whose
        # migrations live elsewhere. Avoid flagging every callsite.
        return issues

    seen_pairs: set[tuple[str, str, int, str]] = set()
    for py_file in _walk_product_backend_python(product_path):
        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("compliance: cannot read %s (%s)", py_file, exc)
            continue
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError as exc:
            logger.debug("compliance: cannot parse %s (%s)", py_file, exc)
            continue

        try:
            rel = str(py_file.relative_to(product_path))
        except ValueError:
            rel = str(py_file)

        for call in _iter_table_callsites(tree):
            # Cross-schema lookup (`db.schema(X).table(Y)`) — Y lives in a
            # foreign product's migration tree. Heuristic limit: we don't
            # resolve `schema → product slug → migrations`. See
            # `_has_schema_in_chain` docstring.
            if _has_schema_in_chain(call):
                continue
            table_name = _extract_table_string_arg(call)
            if table_name is None:
                continue
            lower = table_name.lower()
            if lower in known or lower in _KNOWN_EXTERNAL_TABLES:
                continue
            key = (name, rel, call.lineno, lower)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            issues.append({
                "product": name,
                "file": rel,
                "line": call.lineno,
                "table": table_name,
                "issue": (
                    f"{rel}:{call.lineno} `.table({table_name!r})` references "
                    f"a table not declared by any `CREATE TABLE` in "
                    f"`products/{name}/backend/migrations/*.sql`. "
                    f"MockSupabase WARN+skip masks this — production fails. "
                    f"See KB § PATTERNS/compliance/testing.md § Production-correctness "
                    f"keeper detectors."
                ),
                "severity": "warning",
            })
    return issues


def _function_block_text(content: str, start: int) -> tuple[str, int]:
    """Return the text of the CREATE FUNCTION block that begins at `start`,
    plus the index where the block ends.

    The block runs from the CREATE FUNCTION match's start through the first
    statement terminator (`;`) that follows the matching dollar-quoted body
    delimiter. Supports any `$tag$ ... $tag$` form (tag may be empty).

    Falls back to "everything until the next `CREATE` keyword OR end of
    file" if no dollar quote is found (some functions use AS 'SQL_LITERAL'
    form — rare but legal).
    """
    # Find the first dollar-quote opener after `start`.
    dq_open = re.search(r"\$(?P<tag>[A-Za-z_][A-Za-z0-9_]*)?\$", content[start:])
    if dq_open is not None:
        tag = dq_open.group("tag") or ""
        opener_idx = start + dq_open.start()
        # Find the matching closer.
        closer_pat = re.compile(rf"\${re.escape(tag)}\$")
        closer_match = closer_pat.search(content, opener_idx + len(dq_open.group(0)))
        if closer_match is not None:
            end = closer_match.end()
            # Walk forward to the next `;` to include the statement terminator.
            semi = content.find(";", end)
            if semi != -1:
                end = semi + 1
            return content[start:end], end
        # Unbalanced dollar quote — skip forward to the next CREATE/EOF.
    # Fallback: take until next CREATE keyword or EOF.
    next_create = re.search(r"\bCREATE\b", content[start + 1:], re.IGNORECASE)
    end = start + 1 + next_create.start() if next_create else len(content)
    return content[start:end], end


def check_function_search_path_pinned(product_path: Path) -> list[dict]:
    """Flag `CREATE [OR REPLACE] FUNCTION` blocks in product migrations
    that do NOT pin `SET search_path = ...`.

    The slip this defends against (Engineer GG therapy P4 / Supabase
    advisor 0011): SECURITY DEFINER functions without a pinned search_path
    can be hijacked by a caller's `search_path` settings — a public-facing
    schema can shadow the intended schema. Pin every function.

    Supabase guidance is to ALWAYS set `search_path` on SECURITY DEFINER
    functions and as a defense-in-depth on STABLE / IMMUTABLE functions
    too. The detector flags EVERY CREATE FUNCTION block missing the clause
    — calibration based on advisor 0011 catching `gcal_authorization_is_fresh`
    even though it was IMMUTABLE (no caller-search_path risk in theory; the
    advisor flags it anyway because the static guarantee is weaker than the
    pinned-clause guarantee).

    **Supersession tuning (2026-05-11):** when a function is redefined
    across migrations via `CREATE OR REPLACE FUNCTION foo()`, only the
    LATEST definition is what Postgres actually runs — earlier blocks are
    overwritten at apply time. The detector accumulates all blocks per
    qualified-name in lexical-file order and reports against the LAST one
    only, eliminating false positives on superseded earlier blocks (N=2
    therapy GG 2026-05-10 + ZZ 2026-05-11; cleared 9 residual ERP findings
    that were accept-with-rationale because of this).

    Heuristic for "superseded":
      - A later `CREATE OR REPLACE FUNCTION <same_name>` supersedes an
        earlier block (any earlier shape — `CREATE FUNCTION` or
        `CREATE OR REPLACE`). Postgres would reject a later bare
        `CREATE FUNCTION` of an existing name (duplicate-object error)
        AND the migration apply would fail, so that shape is treated as a
        non-supersession (each `CREATE FUNCTION` is the only definition).
      - When no later block exists, the block is the LATEST by definition
        and is flagged if it lacks `SET search_path`.

    Severity `warning`. False-positive shape: a function legitimately
    relying on caller search_path (very rare in our codebase, none in any
    existing migration). Accept-with-rationale + comment would shut the
    detector up; we leave that to the product owner if the case arises.
    """
    issues: list[dict] = []
    name = product_path.name
    migrations_dir = product_path / "backend" / "migrations"
    if not migrations_dir.exists():
        return issues

    # Pass 1: collect every CREATE FUNCTION block across all migrations in
    # lexical filename order. The list per qualified-name preserves order,
    # so the LAST entry is the one Postgres actually executes after the
    # full migration sweep applies.
    blocks_by_fn: dict[str, list[dict]] = {}
    for sql_file in sorted(migrations_dir.glob("*.sql")):
        try:
            content = sql_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("compliance: cannot read %s (%s), skipping", sql_file, exc)
            continue
        try:
            rel = str(sql_file.relative_to(product_path))
        except ValueError:
            rel = str(sql_file)

        for m in _CREATE_FUNCTION_START_RE.finditer(content):
            fn_qualified = m.group("qualified")
            is_or_replace = bool(m.group("or_replace"))
            block_text, _end = _function_block_text(content, m.start())
            has_search_path = bool(re.search(
                r"\bSET\s+search_path\b",
                block_text,
                re.IGNORECASE,
            ))
            lineno = content[:m.start()].count("\n") + 1
            blocks_by_fn.setdefault(fn_qualified, []).append({
                "file": rel,
                "line": lineno,
                "is_or_replace": is_or_replace,
                "has_search_path": has_search_path,
            })

    # Pass 2: for each function, evaluate the LATEST definition. We walk
    # the per-fn list and find the last block that survives supersession.
    # A later `CREATE OR REPLACE` supersedes any earlier block. A bare
    # `CREATE FUNCTION` after an earlier definition would be a Postgres
    # apply error (not our problem here — flag the latest block as-is).
    for fn_qualified, blocks in blocks_by_fn.items():
        latest = blocks[-1]
        if latest["has_search_path"]:
            continue
        issues.append({
            "product": name,
            "file": latest["file"],
            "line": latest["line"],
            "function": fn_qualified,
            "issue": (
                f"{latest['file']}:{latest['line']} `CREATE FUNCTION "
                f"{fn_qualified}` does not pin `SET search_path = ...`. "
                f"Supabase advisor 0011 flags this. See KB § PATTERNS/"
                f"testing.md § Production-correctness keeper detectors."
            ),
            "severity": "warning",
        })
    return issues


# ---------------------------------------------------------------------------
# `check_rls_policy_self_reference` — an RLS policy whose USING / WITH CHECK
# clause subqueries the SAME table the policy is ON recurses at evaluation
# time → Postgres 42P17 "infinite recursion detected in policy". N=2:
# erp.equipe_membros (026) + public.noctus_users (035) both shipped this and
# both broke prod. The fix in both was a SECURITY DEFINER helper (BYPASSRLS)
# that resolves the scope WITHOUT re-reading the policy's own table. This
# keeper is the PREVENTION layer — not the fix; it flags the next instance.
#
# Migration-supersession aware (mirrors check_function_search_path_pinned):
# migrations are append-only, so the original recursive policy still lives in
# its first migration (e.g. 001) even after a later one DROPs + recreates it
# non-recursively (035). The detector evaluates only the LAST surviving
# operation per (table, policy-name) in lexical-file order — so a fixed
# policy yields a clean baseline (0 on the live fleet: 026 + 035 both fixed).
#
# Predicate is prose-class (SQL, not Python AST): the policy's own table must
# not appear in a FROM / JOIN inside its USING / WITH CHECK body. Severity
# `error` (a recursive policy is a hard prod 42P17 outage).
# ---------------------------------------------------------------------------

_CREATE_POLICY_RE = re.compile(
    r'CREATE\s+POLICY\s+"?(?P<name>[a-zA-Z0-9_]+)"?\s+ON\s+'
    r'"?(?P<table>(?:[a-zA-Z0-9_]+\.)?[a-zA-Z0-9_]+)"?',
    re.IGNORECASE,
)
_DROP_POLICY_RE = re.compile(
    r'DROP\s+POLICY\s+(?:IF\s+EXISTS\s+)?"?(?P<name>[a-zA-Z0-9_]+)"?\s+ON\s+'
    r'"?(?P<table>(?:[a-zA-Z0-9_]+\.)?[a-zA-Z0-9_]+)"?',
    re.IGNORECASE,
)


def check_rls_policy_self_reference(product_path: Path) -> list[dict]:
    """Flag RLS policies whose body subqueries the table the policy is ON.

    A `CREATE POLICY ... ON foo USING (... SELECT ... FROM foo ...)` recurses:
    evaluating `foo`'s policy requires reading `foo`, which re-applies the
    policy → Postgres 42P17. N=2 in the fleet — `erp.equipe_membros` (026)
    and `public.noctus_users` (035), each a prod login/auth outage; both
    fixed with a SECURITY DEFINER (BYPASSRLS) helper. This detector is the
    prevention layer (it does NOT re-implement the fix — it stops the next
    self-referencing policy from shipping).

    Supersession-aware: only the LAST operation per (table, policy-name) in
    lexical migration order is evaluated, so the original recursive policy
    that a later migration DROPs + recreates non-recursively does NOT
    false-flag (live baseline 0: 026 + 035 are both fixed).

    Self-reference = the policy's own (bare) table name appears after a
    `FROM` / `JOIN` inside the statement body (the `ON <table>` clause uses
    `ON`, not `FROM`, so it is not a false hit; a column-qualifier like
    `foo.col` is not a FROM/JOIN either).

    Severity `error` (baseline 0 since 2026-05-23 — therapy migration `015`
    DROP+recreated `conversation_participants_access` through a SECURITY DEFINER
    helper, clearing the last fleet finding; live-apply of 015 is the gated
    prod-DB step, separate from this code-level guard).
    """
    issues: list[dict] = []
    name = product_path.name
    migrations_dir = product_path / "backend" / "migrations"
    if not migrations_dir.exists():
        return issues

    # Pass 1: collect every CREATE/DROP POLICY op per (table, policy) across
    # all migrations in lexical filename order, then within-file by position.
    ops_by_policy: dict[tuple[str, str], list[dict]] = {}
    for sql_file in sorted(migrations_dir.glob("*.sql")):
        try:
            content = sql_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("compliance: cannot read %s (%s), skipping", sql_file, exc)
            continue
        try:
            rel = str(sql_file.relative_to(product_path))
        except ValueError:
            rel = str(sql_file)

        events: list[tuple[int, str, re.Match]] = []
        for m in _CREATE_POLICY_RE.finditer(content):
            events.append((m.start(), "create", m))
        for m in _DROP_POLICY_RE.finditer(content):
            events.append((m.start(), "drop", m))
        events.sort(key=lambda e: e[0])

        for pos, kind, m in events:
            bare_table = m.group("table").split(".")[-1].lower()
            key = (bare_table, m.group("name").lower())
            if kind == "drop":
                ops_by_policy.setdefault(key, []).append({"kind": "drop"})
                continue
            # CREATE — capture the statement body (up to the terminating `;`)
            semi = content.find(";", m.start())
            body = content[m.start(): semi if semi != -1 else len(content)]
            self_ref = bool(re.search(
                rf"\b(?:FROM|JOIN)\s+(?:[a-zA-Z0-9_]+\.)?{re.escape(bare_table)}\b",
                body,
                re.IGNORECASE,
            ))
            ops_by_policy.setdefault(key, []).append({
                "kind": "create",
                "file": rel,
                "line": content[:m.start()].count("\n") + 1,
                "self_ref": self_ref,
            })

    # Pass 2: evaluate only the LAST surviving op per policy.
    for (bare_table, policy), ops in ops_by_policy.items():
        last = ops[-1]
        if last["kind"] != "create" or not last["self_ref"]:
            continue
        issues.append({
            "product": name,
            "file": last["file"],
            "line": last["line"],
            "issue": (
                f"{last['file']}:{last['line']} RLS policy `{policy}` ON "
                f"`{bare_table}` subqueries `{bare_table}` in its own "
                f"USING/WITH CHECK body → Postgres 42P17 infinite recursion "
                f"at evaluation (broke prod on equipe_membros/026 + "
                f"noctus_users/035). Resolve the scope via a SECURITY DEFINER "
                f"(BYPASSRLS) helper instead of self-querying — see "
                f"`KB § PATTERNS/backend/database-rls.md` (RLS self-reference)."
            ),
            "severity": "error",
        })
    return issues


def _admin_client_bindings(tree: ast.Module) -> set[str]:
    """Return the set of local variable names that hold a `get_admin_client()`
    return value within `tree`.

    Detects two assignment shapes:
        admin_db = get_admin_client()
        client: SomeType = get_admin_client()

    Plus the chained shape (`get_admin_client().table(...)`) which yields
    no binding but is matched directly by the receiver-shape walker.
    """
    bindings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            if value is None:
                continue
            if not (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "get_admin_client"
            ):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for tgt in targets:
                if isinstance(tgt, ast.Name):
                    bindings.add(tgt.id)
    return bindings


def _is_chained_admin_table_call(call: ast.Call) -> bool:
    """True if `call` is `get_admin_client().table(...)` (chained, no
    intermediate binding).
    """
    if not (isinstance(call.func, ast.Attribute) and call.func.attr == "table"):
        return False
    receiver = call.func.value
    return (
        isinstance(receiver, ast.Call)
        and isinstance(receiver.func, ast.Name)
        and receiver.func.id == "get_admin_client"
    )


def _is_bound_admin_table_call(call: ast.Call, bindings: set[str]) -> bool:
    """True if `call` is `<bound>.table(...)` where `<bound>` is in
    `bindings` (an admin-client variable).
    """
    if not (isinstance(call.func, ast.Attribute) and call.func.attr == "table"):
        return False
    receiver = call.func.value
    return isinstance(receiver, ast.Name) and receiver.id in bindings


def check_admin_endpoint_service_role_bypass(product_path: Path) -> list[dict]:
    """Flag admin-client `.table("T")` callsites where the target table T
    has no `service_role_bypass` policy in the product's migrations.

    The slip this defends against (Engineer GG therapy P4): an admin
    endpoint reaches for `get_admin_client()` to bypass authenticated-user
    RLS, but the target table only has `authenticated_access` policies —
    so the service_role bypass silently fails (returns empty result sets,
    or worse, succeeds against a real row by coincidence). The detector
    enforces the platform convention: every admin-accessed table ships a
    matching `CREATE POLICY "service_role_bypass" ... FOR ALL TO
    service_role USING (true)`.

    Detection shape (AST):
      - Find `admin_db = get_admin_client()` style bindings + chained
        `get_admin_client().table(...)` calls.
      - For each, extract the table-name literal arg.
      - Cross-check against `_collect_service_role_bypass_tables`.

    Severity `warning`. False-positive shape (rare): a table that's
    accessed via admin client purely for cross-tenant reads where RLS is
    intentionally not bypassed because the row visibility is enforced by
    a different mechanism (foreign-key chain to a tenant-id column the
    admin client already has). Accept-with-rationale handles those.
    """
    issues: list[dict] = []
    name = product_path.name
    backend_app = product_path / "backend" / "app"
    migrations = product_path / "backend" / "migrations"
    if not backend_app.exists() or not migrations.exists():
        return issues

    bypass_tables = _collect_service_role_bypass_tables(product_path)

    seen: set[tuple[str, str, int, str]] = set()
    for py_file in _walk_product_backend_python(product_path):
        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("compliance: cannot read %s (%s)", py_file, exc)
            continue
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError as exc:
            logger.debug("compliance: cannot parse %s (%s)", py_file, exc)
            continue

        bindings = _admin_client_bindings(tree)
        if not bindings:
            # Still scan for chained `get_admin_client().table(...)`.
            pass

        try:
            rel = str(py_file.relative_to(product_path))
        except ValueError:
            rel = str(py_file)

        for call in _iter_table_callsites(tree):
            # Cross-schema lookup (`admin_db.schema(X).table(Y)`) — bypass
            # policy must live in X's migration tree, not this product's.
            # Skip explicitly so a future receiver-shape refactor (e.g.
            # extending `_is_*_admin_table_call` to follow chains) doesn't
            # reintroduce the false positive. See `_has_schema_in_chain`
            # docstring for the heuristic-limit rationale.
            if _has_schema_in_chain(call):
                continue
            is_admin = (
                _is_chained_admin_table_call(call)
                or _is_bound_admin_table_call(call, bindings)
            )
            if not is_admin:
                continue
            table_name = _extract_table_string_arg(call)
            if table_name is None:
                continue
            lower = table_name.lower()
            if lower in _KNOWN_EXTERNAL_TABLES:
                # External (auth.users etc.) — RLS not under our control.
                continue
            if lower in bypass_tables:
                continue
            key = (name, rel, call.lineno, lower)
            if key in seen:
                continue
            seen.add(key)
            issues.append({
                "product": name,
                "file": rel,
                "line": call.lineno,
                "table": table_name,
                "issue": (
                    f"{rel}:{call.lineno} admin client calls "
                    f"`.table({table_name!r})` but table `{table_name}` "
                    f"has no `CREATE POLICY \"service_role_bypass\" ... ON "
                    f"<schema>.{table_name}` in "
                    f"`products/{name}/backend/migrations/*.sql`. "
                    f"Admin bypass will silently fail. See KB § "
                    f"PATTERNS/compliance/testing.md § Production-correctness keeper "
                    f"detectors."
                ),
                "severity": "warning",
            })
    return issues


# ---------------------------------------------------------------------------
# `check_slowapi_with_pep563` — flags the slowapi `@limiter.limit` +
# `from __future__ import annotations` (PEP 563) combination that crashes
# products at app import via `PydanticUndefinedAnnotation`.
#
# Background — N=3 recurrence formalization (2026-05-11):
#   slowapi wraps the decorated function via `@functools.wraps`, which copies
#   `__module__`/`__name__`/`__qualname__`/`__doc__` but NOT `__globals__`.
#   Under PEP 563, all annotations are strings; when FastAPI/Pydantic later
#   `eval()`s them to inspect the route signature, the name lookup happens in
#   slowapi's module namespace — not the route module's. Any locally-declared
#   model (e.g. `RunRequest`, `SSOTokenRequest`, `SubjectsRequest`) becomes
#   unresolvable → `PydanticUndefinedAnnotation` at import time → product
#   fails to boot. Three prior incidents this session: AUTH-RL (core/sso.py +
#   media-scheduling/oauth.py), LLM-RL-TRIO (mailing/routers/ai.py),
#   DT-FORWARD-REF (dev-team/api/run.py).
# ---------------------------------------------------------------------------


def _file_has_pep563_future_import(tree: ast.Module) -> bool:
    """True iff the module has `from __future__ import annotations` at top.

    PEP 563 is a *module-level* opt-in; `__future__` imports MUST be at the
    top of the file (Python enforces this — they're not legal mid-module),
    so we only need to inspect top-level `ImportFrom` nodes.
    """
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            for alias in node.names:
                if alias.name == "annotations":
                    return True
    return False


def _file_has_limiter_limit_decorator(tree: ast.Module) -> tuple[bool, int]:
    """Return (found, first_decorator_lineno). Walks every Function/AsyncFunction
    in the tree and inspects its decorator list for `@limiter.limit(...)`.

    Accepts the canonical shape `@limiter.limit("10/minute")` (an `ast.Call`
    whose `func` is `ast.Attribute(value=ast.Name(id="limiter"), attr="limit")`)
    and the rare bare `@limiter.limit` shape (an `ast.Attribute` without a
    surrounding Call) — defensive coverage; slowapi requires the call form.
    """
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            # @limiter.limit(...)  — the canonical shape
            if isinstance(deco, ast.Call):
                func = deco.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "limit"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "limiter"
                ):
                    return True, deco.lineno
            # @limiter.limit  — bare attribute (uncommon but defensive)
            elif isinstance(deco, ast.Attribute):
                if (
                    deco.attr == "limit"
                    and isinstance(deco.value, ast.Name)
                    and deco.value.id == "limiter"
                ):
                    return True, deco.lineno
    return False, 0


def check_slowapi_with_pep563(product_path: Path) -> list[dict]:
    """Detect files that combine `@limiter.limit` (slowapi) with
    `from __future__ import annotations` (PEP 563).

    This combination crashes the product at app import time:
      * PEP 563 makes every function/class annotation a string.
      * slowapi's `@limiter.limit` wraps the route via `@functools.wraps`,
        which copies `__module__`/`__name__`/`__qualname__`/`__doc__` but
        NOT `__globals__`.
      * FastAPI/Pydantic resolves annotations via `eval()` — the lookup
        happens in slowapi's module namespace, where the route's local
        models (`RunRequest`, `SSOTokenRequest`, ...) don't exist.
      * Result: `PydanticUndefinedAnnotation` at import → product fails
        to boot.

    Scope: `<product>/backend/app/routers/*.py` + `<product>/backend/app/api/*.py`.
    All four known incidents (AUTH-RL × 2, LLM-RL-TRIO, DT-FORWARD-REF) fall
    in this surface — no other backend directory hosts decorated FastAPI
    routes in the platform.

    Severity: high — app fails to boot, no graceful degradation.

    N=3 recurrence formalization, 2026-05-11. Per CLAUDE.md "DRY — the
    recurrence rule" + KB § PATTERNS/compliance/testing.md § Regression-test-the-detector.
    """
    issues: list[dict] = []
    if not product_path.exists():
        return issues

    product_slug = product_path.name
    candidate_dirs = [
        product_path / "backend" / "app" / "routers",
        product_path / "backend" / "app" / "api",
    ]

    for base in candidate_dirs:
        if not base.exists():
            continue
        for path in base.glob("*.py"):
            if path.name == "__init__.py":
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError) as exc:
                logger.warning(
                    "compliance: cannot read %s (%s), skipping", path, exc,
                )
                continue
            try:
                tree = ast.parse(content, filename=str(path))
            except SyntaxError as exc:
                logger.warning(
                    "compliance: cannot parse %s (%s), skipping", path, exc,
                )
                continue

            if not _file_has_pep563_future_import(tree):
                continue
            has_limiter, line_no = _file_has_limiter_limit_decorator(tree)
            if not has_limiter:
                continue

            try:
                relative = str(path.relative_to(product_path.parent.parent))
            except ValueError:
                relative = str(path)

            issues.append({
                "product": product_slug,
                "file": relative,
                "issue": (
                    f"`{relative}` combines `from __future__ import annotations` "
                    f"with `@limiter.limit` (first occurrence at line {line_no}). "
                    f"PEP 563 turns all annotations into strings; slowapi's "
                    f"`@functools.wraps` copies `__module__`/`__name__` but NOT "
                    f"`__globals__`, so FastAPI/Pydantic `eval()` of forward-refs "
                    f"(e.g. `RunRequest`, `SSOTokenRequest`) resolves in slowapi's "
                    f"module namespace → `PydanticUndefinedAnnotation` at app "
                    f"import time → product fails to boot. FIX: drop "
                    f"`from __future__ import annotations` from this file "
                    f"(safe if no PEP 604 `X | Y` annotations are used) OR "
                    f"move the rate-limited endpoint(s) to a sibling module "
                    f"without the future import. Three prior incidents this "
                    f"session: AUTH-RL (core/sso.py + media-scheduling/oauth.py), "
                    f"LLM-RL-TRIO (mailing/routers/ai.py), DT-FORWARD-REF "
                    f"(dev-team/api/run.py). N=3 formalized 2026-05-11."
                ),
                "severity": "high",
            })

    return issues


# ---------------------------------------------------------------------------
# Hygiene-compliance detectors — shipped 2026-05-11 by
# `keeper-housekeeping-upgrade` Phase 1. The keeper trio (keeper/hound/mole)
# already covers compliance/curatorial/storage; these four detectors close
# the residual housekeeping gap where transient coordination state, archive
# residue, dead branches, and gitignore drift accumulate silently and only
# get caught by ad-hoc user requests ("clean the archive", "kill old
# branches"). Per the `feedback_archive_clean_trigger` + the dispatcher-
# inbox/outbox + mole-last-sweep gitignore decisions logged 2026-05-11.
#
# All four are `<platform>` / `<root>` scoped and emit at `warning` severity
# by default — they are housekeeping, not contract violations. Escalation
# rules (e.g. archive entries >7d → high) live inline.
# ---------------------------------------------------------------------------


_ARCHIVE_DIR_NAME = "archive"
_ARCHIVE_DATE_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Unified two-session coordination file (consolidated 2026-05-18 from the
# root dispatcher-inbox.md + dispatcher-outbox.md). `## Pending` /
# `## Completed` = Inbox (architect→operator); trailing `## Outbox` =
# operator→architect audit. The Pending/heading regexes are unchanged —
# only the path moved off repo-root into gitignored `.claude/`.
_DISPATCHER_FILE_RELPATH = ".claude/dispatcher.md"
_DISPATCHER_HEADING_RE = re.compile(
    r"^###\s+(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})\s+[—-]\s+(.+?)\s*$",
    re.MULTILINE,
)
_DISPATCHER_PENDING_RE = re.compile(
    r"^##\s+Pending\s*$.*?(?=^##\s+|\Z)",
    re.MULTILINE | re.DOTALL,
)

# Paths that should be in .gitignore — transient coordination artifacts,
# log files, and `.claude/dispatcher.md` (the unified two-session
# coordination file, see KB § PATTERNS/architect/two-session-architect-operator.md).
# Extend when new transient surfaces land; the detector flags missing
# entries, not extra entries.
_EXPECTED_GITIGNORE_PATHS: tuple[str, ...] = (
    ".claude/dispatcher.md",
    "scripts/mole-last-sweep.log",
    "scripts/archive-clean-last-sweep.log",
)


def _parse_iso_date(s: str):
    """Parse `YYYY-MM-DD` → date object, returning None on failure.

    Kept local + tiny rather than reaching for `dateutil` — these detectors
    only ever see the ISO date format the archive + dispatcher conventions
    pin.
    """
    import datetime as _dt

    try:
        return _dt.date.fromisoformat(s)
    except ValueError:
        return None


def check_archive_staleness(repo_root: Path | None = None) -> list[dict]:
    """Detect date-stamped folders under `archive/<bucket>/YYYY-MM-DD/` that
    are older than D-2 (D = today, D-1 = yesterday).

    Why: per `feedback_archive_clean_trigger` (memory 2026-05-XX), the
    convention is "keep today + yesterday, delete D-2+". Users currently
    invoke `bash scripts/archive-clean.sh --force` manually; this detector
    surfaces accumulation so the keeper can recommend the sweep.

    Folder shape recognized: `archive/<bucket>/YYYY-MM-DD/` where `<bucket>`
    is any subdir (projects/, features/, seed-absorption/, …). Folders
    whose name doesn't match the ISO-date pattern are ignored — they're
    typically README.md siblings or non-date-stamped buckets.

    Severity:
      - `warning` for stale entries within the first week (D-2 to D-7).
      - `high` past 7 days (a long-overlooked accumulation).
    """
    import datetime as _dt

    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    archive_dir = root / _ARCHIVE_DIR_NAME
    if not archive_dir.exists() or not archive_dir.is_dir():
        return issues

    today = _dt.date.today()
    # Keep today + yesterday only. Any folder dated < yesterday → flag.
    # I.e. threshold is yesterday (today - 1d); folders with date < threshold
    # are stale.
    threshold = today - _dt.timedelta(days=1)

    for bucket in sorted(archive_dir.iterdir()):
        if not bucket.is_dir() or bucket.name.startswith("."):
            continue
        for dated in sorted(bucket.iterdir()):
            if not dated.is_dir():
                continue
            if not _ARCHIVE_DATE_NAME_RE.match(dated.name):
                continue
            d = _parse_iso_date(dated.name)
            if d is None:
                continue
            if d >= threshold:
                continue
            age_days = (today - d).days
            try:
                rel = str(dated.relative_to(root))
            except ValueError:
                rel = str(dated)
            severity = "high" if age_days > 7 else "warning"
            issues.append({
                "product": "<root>",
                "file": rel,
                "issue": (
                    f"Archive entry `{rel}` is {age_days} days old "
                    f"(threshold: keep today + yesterday only). Run "
                    f"`bash scripts/archive-clean.sh --force` to trim "
                    f"entries older than D-1. Per "
                    f"`feedback_archive_clean_trigger`."
                ),
                "severity": severity,
            })
    return issues


def check_methodology_doc_refs(repo_root: Path | None = None) -> list[dict]:
    """Detect broken KB-doc references across all methodology surfaces.

    Reuses the pure predicate ``methodology_reference_gaps`` from
    ``tools.kb_sync`` (NO copy-paste of logic — one predicate, two
    surfaces: pre-commit + compliance gate).

    Surfaces scanned: ``CLAUDE.md`` + ``CLAUDE/**/*.md`` +
    ``.claude/agents/*.md`` + every ``KNOWLEDGE-BASE/**/*.md``.

    Reference forms: (a) literal ``KNOWLEDGE-BASE/<path>.md``; (b)
    shorthand ``KB § <ref>``. Placeholders (``<x>``, ``X.md``, ``**``)
    excluded; wikilinks (``[[…]]``) advisory-only (forward-refs allowed
    per CLAUDE.md).

    Severity: ``high`` — a broken KB pointer in a methodology surface
    blocks the pre-commit gate and silently misdirects agents.

    Codified 2026-05-25: the original ``verify_kb_sync`` only validated
    literal ``KNOWLEDGE-BASE/...md`` pointers in CLAUDE.md — it missed
    the dominant ``KB §`` shorthand (214 in CLAUDE.md), all of
    ``.claude/agents/*.md``, and KB→KB cross-refs.
    """
    from tools.kb_sync import methodology_reference_gaps

    root = repo_root or REPO_ROOT
    issues: list[dict] = []
    for gap_str in methodology_reference_gaps(root):
        # gap_str shape: "<surface-relpath>: `<bad-ref>`"
        surface, _, ref = gap_str.partition(": ")
        issues.append({
            "product": "<methodology>",
            "file": surface,
            "issue": (
                f"Broken KB doc reference {ref} in methodology surface "
                f"`{surface}` — the target does not exist in "
                f"KNOWLEDGE-BASE/. Fix the ref or create the missing file. "
                f"(check_methodology_doc_refs, 2026-05-25)"
            ),
            "severity": "high",
        })
    return issues


def check_codification_debt(repo_root: Path | None = None) -> list[dict]:
    """Surface deferred codifications (``NOC-REMEDIATE[codify]`` markers) in the gate.

    The **mechanical, always-on half of the ``/codify`` command** (the DECISION
    — apply / defer / stays-prose — stays with ``/codify``; *detection* is now
    codified). A codification evaluated as ripe-but-deferred (N<3, or
    design-first) leaves a structured ``NOC-REMEDIATE[codify]: <rule> — <date>``
    marker instead of burying the deferral in free prose where no sweep can see
    it (the gap this keeper closes: ``branching.md`` "the *filed* worktree-
    sensitivity guard follow-up" + the C2 "filed design-first" keeper were both
    invisible to any mechanical sweep). Every compliance run now reads those
    markers so a deferred codification can never go silent:

      - well-formed ``[codify]`` marker → ``warning`` (a sanctioned deferral —
        surfaced + baseline-trackable, never blocks; defer-with-destination is
        legitimate per the remediation-marker contract);
      - malformed (missing ``— <YYYY-MM-DD>``) or on an ``except`` line →
        ``high`` (a real defect; mirrors ``scan_remediation_markers`` exit 1);
      - codify backlog ≥3 → one extra ``warning`` ("run ``/codify`` sweep").

    Reuses ``markers_of_class`` — one parser, two surfaces
    (KB § PATTERNS/common/methodology-codification-pipeline.md +
    KB § PATTERNS/common/remediation-markers.md). Codified 2026-05-25 via ``/codify``.
    """
    from tools.noctus.dev.scan_remediation_markers import markers_of_class

    root = repo_root or REPO_ROOT
    issues: list[dict] = []
    markers = markers_of_class(root, "codify")
    for m in markers:
        loc = f"{m['path']}:{m['line']}"
        if m["on_except"] or not m["date"]:
            reason = (
                "on an `except` line (a marker must never suppress an error)"
                if m["on_except"] else "missing the `— <YYYY-MM-DD>` date"
            )
            issues.append({
                "product": "<methodology>",
                "file": m["path"],
                "issue": (
                    f"Malformed/forbidden NOC-REMEDIATE[codify] marker at {loc}: "
                    f"{reason}. Fix the marker or build the keeper. "
                    f"(check_codification_debt, 2026-05-25)"
                ),
                "severity": "high",
            })
        else:
            age = f"{m['age_days']}d" if m["age_days"] is not None else "?"
            issues.append({
                "product": "<methodology>",
                "file": m["path"],
                "issue": (
                    f"Deferred codification pending at {loc} ({age}): {m['text']}. "
                    f"Evaluate via /codify — build the keeper when ripe (N≥3 + "
                    f"deterministic + clear remediation) or accept-with-rationale. "
                    f"(check_codification_debt, 2026-05-25)"
                ),
                "severity": "warning",
            })
    if len(markers) >= 3:
        issues.append({
            "product": "<methodology>",
            "file": "<codify-backlog>",
            "issue": (
                f"{len(markers)} deferred codifications pending "
                f"(NOC-REMEDIATE[codify]) — run `/codify sweep` to drain the "
                f"backlog. (check_codification_debt, 2026-05-25)"
            ),
            "severity": "warning",
        })
    return issues


def check_dispatcher_staleness(repo_root: Path | None = None) -> list[dict]:
    """Detect entries in `.claude/dispatcher.md` `## Pending` section that
    were appended >24h ago and never moved to `## Completed`.

    Why: per `KB § PATTERNS/architect/two-session-architect-operator.md`, the
    inbox is a coordination channel — entries that sit there past 24h
    indicate the operator session is offline or the entry got missed.
    The keeper surfaces accumulation so the architect notices.

    Entry shape recognized: `### YYYY-MM-DDTHH:MM — <SHORT-NAME>` per
    the inbox-format scaffold. Entries inside `## Completed` are ignored.

    Severity:
      - `warning` for 24h–72h-old pending entries.
      - `high` past 7 days (operator session likely abandoned).
    """
    import datetime as _dt

    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    inbox = root / _DISPATCHER_FILE_RELPATH
    if not inbox.exists() or not inbox.is_file():
        return issues

    try:
        content = inbox.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("compliance: cannot read %s (%s)", inbox, exc)
        return issues

    pending_match = _DISPATCHER_PENDING_RE.search(content)
    if pending_match is None:
        return issues
    pending_block = pending_match.group(0)

    now = _dt.datetime.now()

    for m in _DISPATCHER_HEADING_RE.finditer(pending_block):
        date_str, hour_str, min_str, label = m.groups()
        d = _parse_iso_date(date_str)
        if d is None:
            continue
        try:
            ts = _dt.datetime.combine(
                d,
                _dt.time(hour=int(hour_str), minute=int(min_str)),
            )
        except ValueError:
            continue
        age = now - ts
        age_hours = age.total_seconds() / 3600.0
        if age_hours < 24:
            continue
        severity = "high" if age.days > 7 else "warning"
        issues.append({
            "product": "<platform>",
            "file": _DISPATCHER_FILE_RELPATH,
            "issue": (
                f"Dispatcher pending entry `{date_str}T{hour_str}:{min_str} "
                f"— {label}` is {age_hours:.0f}h old. The architect/operator "
                f"split expects pending entries to drain within 24h. Either "
                f"resume operator session and consume the entry, or move it "
                f"to `## Completed` with a `❌ stale` marker. Per "
                f"`KB § PATTERNS/architect/two-session-architect-operator.md`."
            ),
            "severity": severity,
        })
    return issues


def check_branch_orphan(repo_root: Path | None = None) -> list[dict]:
    """Detect local branches whose last commit is >30 days old AND that
    are either merged to `origin/main` or otherwise abandonable.

    Why: in practice the platform accumulates hundreds of branches from
    per-engineer worktrees. Merged branches >30d are pure clutter; deleting
    them keeps `git branch` output legible and lets `bootstrap-worktree.sh`
    find a clean tree faster.

    Implementation:
      - `git for-each-ref --format='%(refname:short)|%(committerdate:iso8601)' refs/heads/`
        to enumerate local branches + last-commit date.
      - For each, check merged-to-`origin/main` via `git merge-base --is-ancestor`.
      - Flag with appropriate severity. NEVER deletes — observation-only
        per the keeper-observation-only methodology.

    Severity:
      - `warning` per merged branch >30d old.
      - `high` only if the merged-orphan count surpasses 50 (signals
        bulk cleanup needed).
    """
    import subprocess
    import datetime as _dt

    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not (root / ".git").exists() and not (root / ".git").is_file():
        # Not a git repo (or detached working tree without .git pointer) — skip.
        return issues

    try:
        result = subprocess.run(
            [
                "git", "-C", str(root),
                "for-each-ref",
                "--format=%(refname:short)|%(committerdate:iso8601)",
                "refs/heads/",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("compliance: git unavailable for branch-orphan check (%s); skipping", exc)
        return issues

    if result.returncode != 0:
        return issues

    today = _dt.date.today()
    stale_threshold_days = 30
    orphans: list[tuple[str, int]] = []

    for line in result.stdout.splitlines():
        if "|" not in line:
            continue
        name, date_str = line.split("|", 1)
        name = name.strip()
        date_str = date_str.strip()
        if not name or name in {"main", "master"}:
            continue
        # Parse the date portion only — committerdate:iso8601 looks like
        # `2026-04-12 18:23:11 +0000`. Ignoring the time + tz is fine for
        # day-granularity staleness checks.
        date_only = date_str.split(" ", 1)[0]
        d = _parse_iso_date(date_only)
        if d is None:
            continue
        age_days = (today - d).days
        if age_days < stale_threshold_days:
            continue

        # Check merged-to-origin/main. If origin/main isn't fetched, skip
        # the merged-check (don't flag everything as orphan in that case).
        try:
            merged = subprocess.run(
                ["git", "-C", str(root), "merge-base", "--is-ancestor", name, "origin/main"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue
        if merged.returncode != 0:
            # Not merged — leave alone; this branch may still hold WIP.
            continue
        orphans.append((name, age_days))

    if not orphans:
        return issues

    # Emit individual entries up to a small cap to keep keeper output legible,
    # plus one summary line at higher severity if the count breaches 50.
    cap = 10
    for name, age_days in orphans[:cap]:
        issues.append({
            "product": "<platform>",
            "file": f".git/refs/heads/{name}",
            "issue": (
                f"Branch `{name}` is {age_days} days stale AND merged to "
                f"`origin/main`. Safe to delete: "
                f"`git branch -d {name}` (or `-D` if local-only commits "
                f"are reflog-recoverable). Bulk cleanup: "
                f"`bash scripts/cleanup-stale-worktrees.sh` cleans "
                f"merged-branch worktrees + their dirs."
            ),
            "severity": "warning",
        })
    remaining = len(orphans) - cap
    if remaining > 0:
        issues.append({
            "product": "<platform>",
            "file": ".git/refs/heads/",
            "issue": (
                f"+{remaining} more stale-merged branches not listed "
                f"(total: {len(orphans)}). Bulk cleanup: "
                f"`git for-each-ref --merged origin/main --format='%(refname:short)' refs/heads/ "
                f"| xargs -n1 git branch -d`."
            ),
            "severity": "high" if len(orphans) > 50 else "warning",
        })
    return issues


def check_gitignore_drift(repo_root: Path | None = None) -> list[dict]:
    """Detect expected transient-coordination paths missing from `.gitignore`.

    Why: the platform has a small set of transient artifacts that MUST
    stay untracked (`.claude/dispatcher.md`, `scripts/mole-last-sweep.log`,
    `scripts/archive-clean-last-sweep.log`). Without explicit gitignore
    entries an absent-minded `git add .` commits them, polluting history
    with operator-only state.

    The expected-paths list is the source of truth (`_EXPECTED_GITIGNORE_PATHS`).
    When a new transient artifact lands, extend the tuple + amend this
    detector's regression test — the detector then catches the drift
    automatically across every checkout.

    Severity:
      - `warning` per missing entry — drift, not a contract violation.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    gitignore = root / ".gitignore"
    if not gitignore.exists() or not gitignore.is_file():
        # No .gitignore at all is a separate (much louder) problem;
        # surface as a single high-severity entry.
        issues.append({
            "product": "<root>",
            "file": ".gitignore",
            "issue": (
                "Repository has no `.gitignore` at root — every transient "
                "artifact path is at risk of being tracked. Create one with "
                "the standard NoctusAI exclusions."
            ),
            "severity": "high",
        })
        return issues

    try:
        content = gitignore.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("compliance: cannot read %s (%s)", gitignore, exc)
        return issues

    # Strip comments + blank lines; normalize each pattern.
    patterns: set[str] = set()
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        patterns.add(line)

    for expected in _EXPECTED_GITIGNORE_PATHS:
        # Accept both exact match + leading-slash anchored form.
        if expected in patterns or f"/{expected}" in patterns:
            continue
        issues.append({
            "product": "<root>",
            "file": ".gitignore",
            "issue": (
                f"Expected transient path `{expected}` is missing from "
                f"`.gitignore`. Append the literal pattern to keep "
                f"operator-only state from being tracked. The expected-paths "
                f"list lives in `_EXPECTED_GITIGNORE_PATHS` in "
                f"`mcp/noctusai/tools/noctus/dev/compliance.py` — extend when "
                f"new transient surfaces land."
            ),
            "severity": "warning",
        })
    return issues


# ---------------------------------------------------------------------------
# Stage-4 codification batch (2026-05-11) — 6 detectors promoting Stage-3
# methodology rules. Filed by `projects/keeper-stage4-codification-batch/`.
#
# The seventh table entry in §4 of the project doc (`check_no_self_monkeypatch`)
# was already codified earlier; this batch lands the remaining six.
#
# Each detector:
#   - takes `repo_root: Path | None = None` and falls back to module-level REPO_ROOT,
#   - emits the standard {product, file, issue, severity} finding shape,
#   - severity defaults to `warning` (Stage-4 calibration: warn first, ratchet later),
#   - ships a colocated `Test<CamelCase>` class in
#     `mcp/noctusai/tests/test_compliance_codification_batch.py`.
# ---------------------------------------------------------------------------


# Production code roots scanned for the literal `# silent-ok` comment.
# Tests are excluded — test files may carry the literal inside a docstring
# describing the rule (negative regression). The "production code" framing
# matches `check_silent_errors`'s `_walk_python_files` helper but the
# silent-ok check is broader (any file type, not just .py).
_SILENT_OK_SCAN_ROOTS: tuple[str, ...] = (
    "products",
    "seed",
    "mcp",
    "noctusai_lib",
    "scripts",
)

# Exclude tests directories at every depth + vendored deps + cache dirs.
_SILENT_OK_EXCLUDED_PARTS: frozenset[str] = frozenset({
    "tests", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".git", ".pytest_cache", ".mypy_cache",
})

# File extensions worth scanning for the literal — keep narrow to code files.
_SILENT_OK_SCAN_EXTS: frozenset[str] = frozenset({
    ".py", ".sh", ".ts", ".tsx", ".js", ".jsx",
})

# Files that legitimately reference the literal in docstrings / regex / prose
# describing the rule itself. Each one is the file that *defines or
# documents* the silent-ok rule; the literal there is a citation, not a
# silenced exception. Keep this list tight — every entry is reviewed.
_SILENT_OK_FILE_ALLOWLIST: frozenset[str] = frozenset({
    "mcp/noctusai/tools/noctus/dev/compliance.py",  # defines the detector + check_silent_errors
})

# The literal pattern. Inline form `# silent-ok` or `# silent-ok: reason`.
# Must appear as an actual line-comment (the `#` starts a comment, not
# inside a string). Approximate via "stripped line starts with `#` OR a
# `#` is preceded by whitespace AND the rest matches".
_SILENT_OK_LITERAL_RE = re.compile(r"#\s*silent-ok\b", re.IGNORECASE)


def check_no_silent_ok_comment(repo_root: Path | None = None) -> list[dict]:
    """Detect the literal `# silent-ok` annotation in production code.

    The `# silent-ok: <reason>` escape hatch was retired platform-wide
    2026-04-28 per user directive ("i dont want any silent-ok sign accross
    the platform"). Per `feedback_silent_ok_is_not_a_substitute_for_logging`,
    every `except` handler must log via `logger.<level>(...)`, raise, or
    surface the error through a return value — no exceptions.

    This detector is narrower than `check_silent_errors` (which scans
    handler bodies via AST): it pins the LITERAL `# silent-ok` comment so
    that any reappearance — even on a line that does the right thing —
    surfaces loudly. The marker is a signal that someone thought the
    escape hatch still existed.

    Scope: production code roots (`products/`, `seed/`, `mcp/`,
    `noctusai_lib/`, `scripts/`). Test files are excluded — they may
    legitimately quote the literal inside a docstring describing the
    rule (the existing `Test<...>` regression suites do this).

    Severity: `warning`.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    for scan_root in _SILENT_OK_SCAN_ROOTS:
        base = root / scan_root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            parts = path.parts
            if any(part in _SILENT_OK_EXCLUDED_PARTS for part in parts):
                continue
            if path.suffix not in _SILENT_OK_SCAN_EXTS:
                continue
            try:
                relative = str(path.relative_to(root))
            except ValueError:
                relative = str(path)
            if relative in _SILENT_OK_FILE_ALLOWLIST:
                # The detector + docstrings of the rule reference the literal
                # legitimately; this allowlist keeps the citation-in-the-rule
                # file from flagging itself.
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError) as exc:
                logger.debug("compliance: cannot read %s (%s)", path, exc)
                continue
            for line_no, line in enumerate(content.splitlines(), start=1):
                if not _SILENT_OK_LITERAL_RE.search(line):
                    continue
                product_label = (
                    relative.split("/", 2)[1]
                    if relative.startswith("products/")
                    else "<root>"
                )
                issues.append({
                    "product": product_label,
                    "file": relative,
                    "issue": (
                        f"`{relative}:{line_no}` carries `# silent-ok` "
                        f"annotation. The escape hatch was retired 2026-04-28: "
                        f"every except must `logger.<level>(...)`, `raise`, or "
                        f"surface the error via a return value. Replace with "
                        f"`logger.debug(...)` (silent unless `NOCTUSAI_DEBUG=1`) "
                        f"or the appropriate `logger.warning(...)`. Per "
                        f"`feedback_silent_ok_is_not_a_substitute_for_logging`."
                    ),
                    "severity": "warning",
                })
    return issues


# ---------------------------------------------------------------------------
# `check_auth_dep_anti_pattern` — flags the 422-trap shape that wires
# `ProductDependencies.{get_org_id,get_user_role,get_user_client}` through
# `Depends(...)`. Per `feedback_auth_factory_pattern`, the canonical wiring
# is `Depends(get_current_user_org)` from `make_get_current_user_org`.
# `ProductDependencies.{...}` instance methods take positional args and
# turn into FastAPI query-param requirements when wired via `Depends(...)`
# — the route then returns 422 unless `?user=...&token=...` is supplied.
# ---------------------------------------------------------------------------


# Attribute names whose use inside `Depends(...)` is the 422-trap shape.
_AUTH_DEP_ANTIPATTERN_ATTRS: frozenset[str] = frozenset({
    "get_org_id",
    "get_user_role",
    "get_user_client",
})


def _walk_router_python_files(root: Path):
    """Yield every `*.py` file under `products/*/backend/app/routers/` —
    the population where the auth-dep antipattern can land.
    """
    products = root / "products"
    if not products.exists():
        return
    excluded_parts: set[str] = {
        "__pycache__", ".venv", "venv", "node_modules", ".git",
        ".pytest_cache", "tests", "migrations",
    }
    for product_dir in products.iterdir():
        if not product_dir.is_dir() or product_dir.name.startswith("."):
            continue
        routers_dir = product_dir / "backend" / "app" / "routers"
        if not routers_dir.exists():
            continue
        for path in routers_dir.rglob("*.py"):
            if any(part in excluded_parts for part in path.parts):
                continue
            yield path


def _is_depends_call_on_product_deps(call: ast.Call) -> tuple[bool, str | None]:
    """Return (matches, attr_name).

    True iff `call` is `Depends(<X>.<attr>)` where `attr` is one of
    `_AUTH_DEP_ANTIPATTERN_ATTRS`. Bare-attribute case (`Depends(get_org_id)`)
    is NOT matched — the AST would need an import-map walk to know if it's
    `ProductDependencies.get_org_id`, and the antipattern in the wild
    always uses the dotted form. Conservative: false negatives over noise.
    """
    func = call.func
    if not isinstance(func, ast.Name) or func.id != "Depends":
        return False, None
    if not call.args:
        return False, None
    arg = call.args[0]
    if isinstance(arg, ast.Attribute) and arg.attr in _AUTH_DEP_ANTIPATTERN_ATTRS:
        return True, arg.attr
    return False, None


def check_auth_dep_anti_pattern(repo_root: Path | None = None) -> list[dict]:
    """Detect `Depends(ProductDependencies.get_org_id)` / `get_user_role` /
    `get_user_client` — the 422-trap auth-wiring shape.

    Per `feedback_auth_factory_pattern`: every product wires auth via the
    `make_get_current_user_org` factory, exposed as `get_current_user_org`
    and consumed as `Depends(get_current_user_org)`. The
    `ProductDependencies.{get_org_id, get_user_role, get_user_client}`
    instance methods take positional args; wiring them through `Depends(...)`
    turns those positionals into FastAPI query parameters and the route
    422s unless `?user=...&token=...` is supplied.

    Imperative use (no `Depends(...)` wrapper) is permitted — callers can
    invoke these methods directly inside a handler body. The detector
    only flags the `Depends(...)` shape.

    Severity: `warning`.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    for path in _walk_router_python_files(root):
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.debug("compliance: cannot read %s (%s)", path, exc)
            continue
        try:
            tree = ast.parse(content, filename=str(path))
        except SyntaxError as exc:
            logger.debug("compliance: cannot parse %s (%s)", path, exc)
            continue

        try:
            relative = str(path.relative_to(root))
        except ValueError:
            relative = str(path)
        product_label = (
            relative.split("/", 2)[1]
            if relative.startswith("products/")
            else "<unknown>"
        )

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            matches, attr = _is_depends_call_on_product_deps(node)
            if not matches:
                continue
            line_no = getattr(node, "lineno", 0) or 0
            issues.append({
                "product": product_label,
                "file": relative,
                "issue": (
                    f"`{relative}:{line_no}` wires "
                    f"`Depends(ProductDependencies.{attr})` — the 422-trap "
                    f"shape (positional args become query params). Use "
                    f"`Depends(get_current_user_org)` from the "
                    f"`make_get_current_user_org` factory instead. Per "
                    f"`feedback_auth_factory_pattern` + `KB § PATTERNS/backend/backend.md "
                    f"§ Auth — canonical pattern`. Imperative use of "
                    f"`ProductDependencies.{attr}(...)` (without `Depends`) "
                    f"is fine."
                ),
                "severity": "warning",
            })
    return issues


# ---------------------------------------------------------------------------
# `check_mcp_path_via_settings` — flags `Path(__file__).parents[N]` in MCP
# tool modules. Per `feedback_mcp_path_constants_from_settings`, MCP tools
# must import `REPO_ROOT` / `PRODUCTS_DIR` from `settings` rather than
# recompute the root via `parents[N]` — the latter is brittle across
# directory moves and was the recurrence Phase 3 surfaced in 18 of 24
# modules.
# ---------------------------------------------------------------------------


def _walk_mcp_tool_files(root: Path):
    """Yield every `*.py` file under `mcp/noctusai/tools/` — the population
    where the parents[N] anti-pattern lives.

    Exclude `__pycache__` + the MCP server entrypoint (`server.py` is at a
    higher level; tools is the boundary).
    """
    base = root / "mcp" / "noctusai" / "tools"
    if not base.exists():
        return
    excluded_parts: set[str] = {"__pycache__", ".venv", "venv"}
    for path in base.rglob("*.py"):
        if any(part in excluded_parts for part in path.parts):
            continue
        yield path


def _is_path_parents_n_call(node: ast.AST) -> bool:
    """True iff `node` is the `Path(__file__).parents[N]` subscript shape.

    The shape: `Subscript(value=Attribute(value=Call(func=Name('Path'),
    args=[Name('__file__')]), attr='parents'), slice=<Constant int>)`.
    """
    if not isinstance(node, ast.Subscript):
        return False
    value = node.value
    if not isinstance(value, ast.Attribute) or value.attr != "parents":
        return False
    call = value.value
    if not isinstance(call, ast.Call):
        return False
    if not isinstance(call.func, ast.Name) or call.func.id != "Path":
        return False
    if not call.args:
        return False
    arg = call.args[0]
    if not isinstance(arg, ast.Name) or arg.id != "__file__":
        return False
    return True


def check_mcp_path_via_settings(repo_root: Path | None = None) -> list[dict]:
    """Detect `Path(__file__).parents[N]` in MCP tool modules.

    Per `feedback_mcp_path_constants_from_settings`: MCP tools must import
    `REPO_ROOT` / `PRODUCTS_DIR` from `settings` rather than recompute the
    root via `parents[N]`. The latter is brittle — a directory move silently
    shifts the depth and a `parents[3]` becomes `parents[4]`. Phase 3 of
    `mcp-path-centralization` (2026-05-XX) surfaced the recurrence in
    18 of 24 modules.

    Scope: `mcp/noctusai/tools/**/*.py`. The shape detected:
    `Path(__file__).parents[N]` (any integer subscript). The fix is always
    the same — `from settings import REPO_ROOT, PRODUCTS_DIR` at module top
    and use those constants.

    Severity: `warning`.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    for path in _walk_mcp_tool_files(root):
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.debug("compliance: cannot read %s (%s)", path, exc)
            continue
        try:
            tree = ast.parse(content, filename=str(path))
        except SyntaxError as exc:
            logger.debug("compliance: cannot parse %s (%s)", path, exc)
            continue

        try:
            relative = str(path.relative_to(root))
        except ValueError:
            relative = str(path)

        for node in ast.walk(tree):
            if not _is_path_parents_n_call(node):
                continue
            line_no = getattr(node, "lineno", 0) or 0
            issues.append({
                "product": "<mcp>",
                "file": relative,
                "issue": (
                    f"`{relative}:{line_no}` uses "
                    f"`Path(__file__).parents[N]` to compute a root path. "
                    f"Import `REPO_ROOT` / `PRODUCTS_DIR` from `settings` "
                    f"instead — `parents[N]` is brittle across directory "
                    f"moves and was the recurrence in 18 of 24 tool modules "
                    f"surfaced by `mcp-path-centralization` Phase 3. Per "
                    f"`feedback_mcp_path_constants_from_settings`."
                ),
                "severity": "warning",
            })
    return issues


# ---------------------------------------------------------------------------
# `check_mcp_write_tool_worktree_arg` — flags MCP tool defs whose name
# implies write-side semantics but the function signature omits a
# `worktree_path: str | None = None` parameter. Per
# `feedback_mcp_write_tools_resolve_caller_root`, MCP stdio is fixed-CWD;
# write tools called from an engineer's worktree must take an explicit
# `worktree_path` argument or the side effect lands in the wrong tree.
# ---------------------------------------------------------------------------


# Function-name PREFIXES that imply write-side semantics on filesystem
# state (or repository state that mole-style worktree path matters for).
# Heuristic — false negatives over noise. The prefix must START the name
# (after any leading underscore strip); a verb buried mid-name does NOT
# count. This calibration deliberately drops `delete`, `archive`-as-prefix
# (covers `archive(...)` but not `archive_staleness`) — see calibration
# notes in the project doc §11.
_MCP_WRITE_TOOL_NAME_PREFIXES: tuple[str, ...] = (
    "archive",
    "scaffold",
    "absorb",
    "set_proposal_status",
    "file_proposal",
    "promote",
    "build_parallel",
    "vite_build",
    "phase_learning_log",
    "phase_learning_consume",
    "batch_speed_gain_log",
    "batch_speed_gain_update",
)

# Function-name prefixes that mean "this is read-side; do NOT flag" even
# if the rest of the name happens to contain a write-verb token. Reserved
# for namespaced families like `check_archive_staleness` where the verb
# is the SCOPE, not the action.
_MCP_READ_PREFIX_GUARDS: tuple[str, ...] = (
    "check_",   # `check_archive_staleness` is a detector, not a writer
    "get_",     # `get_proposal_template` reads a template
    "list_",    # `list_proposals` lists, doesn't write
    "read_",
    "fetch_",
    "find_",
    "scan_",
    "outline_", # `outline_python` reads source
)

# Explicit, name-keyed exceptions. Used when:
#   (a) the tool's name pattern collides with a legitimate write-prefix
#       but the tool itself is read-side (e.g. `scaffold_interrogate`
#       returns design questions — collides with the `scaffold` prefix
#       that catches `scaffold_product` / `scaffold_migration`); OR
#   (b) the tool DOES write, but its destination is fixed by design and
#       NOT a caller-resolved worktree (e.g. `reserve_port_range` writes
#       to the centralized port registry; `create_testing_ground`
#       provisions a NEW sibling workspace outside any existing worktree
#       via `bootstrap-seed-workspace.sh`).
# Calibrated 2026-05-11 from a 4-false-positive sweep against the
# detector Engineer P shipped in commit `e6893e9`. Names are matched
# against the bare function name (stripped of leading underscores).
# Reasoning: prefix-only calibration cannot disambiguate
# `scaffold_interrogate` (read) from `scaffold_product` (write); an
# explicit exception set keeps the heuristic clean and documents
# each carve-out at the source.
_MCP_WRITE_TOOL_NAME_EXCEPTIONS: frozenset[str] = frozenset({
    # Read-side tools whose name collides with a write-prefix:
    "scaffold_interrogate",  # returns design questions; read-side
    "review_session",        # dev review report; read-side
    # Write-side tools whose destination is fixed-by-design, not a
    # caller-resolved worktree:
    "reserve_port_range",    # writes the central port registry
    "create_testing_ground", # provisions a NEW sibling workspace
})


def _function_name_implies_write(name: str) -> bool:
    """Heuristic: True iff `name` starts with a write-verb prefix and is
    not gated by a read-prefix guard or an explicit name exception.

    Stripped of any single leading underscore so private helpers like
    `_archive_internal` are recognized.
    """
    bare = name.lstrip("_")
    if bare in _MCP_WRITE_TOOL_NAME_EXCEPTIONS:
        return False
    if any(bare.startswith(guard) for guard in _MCP_READ_PREFIX_GUARDS):
        return False
    return any(bare.startswith(prefix) for prefix in _MCP_WRITE_TOOL_NAME_PREFIXES)


def _signature_has_param(fn: ast.FunctionDef | ast.AsyncFunctionDef, param: str) -> bool:
    """True if `fn`'s signature declares a parameter named `param`
    (positional, kw-only, or vararg-skipped). Conservative: scans all of
    args / posonlyargs / kwonlyargs.
    """
    args = fn.args
    all_args = list(args.args) + list(args.posonlyargs) + list(args.kwonlyargs)
    return any(a.arg == param for a in all_args)


def check_mcp_write_tool_worktree_arg(repo_root: Path | None = None) -> list[dict]:
    """Detect MCP tool functions whose name implies write-side semantics
    but the signature omits a `worktree_path` parameter.

    Per `feedback_mcp_write_tools_resolve_caller_root`: MCP stdio runs in
    a fixed CWD (the MCP server's startup workspace). Write tools called
    from an engineer's worktree MUST accept `worktree_path: str | None`
    so the caller can route the side effect to the right tree. Without
    the parameter, the side effect either lands in the wrong workspace
    or the tool resolves a stale root.

    Scope: every top-level `def` / `async def` under `mcp/noctusai/tools/`
    whose name contains a write-verb (archive / scaffold / absorb /
    set_proposal_status / etc). Public helpers and private (`_*`) names
    are not exempt — both paths can be reached as MCP tools.

    Severity: `warning`.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    for path in _walk_mcp_tool_files(root):
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.debug("compliance: cannot read %s (%s)", path, exc)
            continue
        try:
            tree = ast.parse(content, filename=str(path))
        except SyntaxError as exc:
            logger.debug("compliance: cannot parse %s (%s)", path, exc)
            continue

        try:
            relative = str(path.relative_to(root))
        except ValueError:
            relative = str(path)

        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not _function_name_implies_write(node.name):
                continue
            if _signature_has_param(node, "worktree_path"):
                continue
            line_no = getattr(node, "lineno", 0) or 0
            issues.append({
                "product": "<mcp>",
                "file": relative,
                "issue": (
                    f"`{relative}:{line_no}` defines `{node.name}(...)` — "
                    f"a write-side MCP tool name — but the signature has no "
                    f"`worktree_path: str | None = None` parameter. MCP stdio "
                    f"is fixed-CWD; engineers calling this tool from a "
                    f"worktree need an explicit path arg to route the side "
                    f"effect. Add `worktree_path: str | None = None` and "
                    f"resolve writes relative to it. Per "
                    f"`feedback_mcp_write_tools_resolve_caller_root`."
                ),
                "severity": "warning",
            })
    return issues


# ---------------------------------------------------------------------------
# `check_pipefail_grep_q` — flags `cmd | grep -q ...` patterns in shell
# scripts that ALSO have `set -[eo].*pipefail`. Discovered 2026-05-11 by
# Engineer M during mole.sh enumeration fix: `grep -q` exits immediately
# on first match, the upstream pipeline's writer gets SIGPIPE (exit 141),
# and `pipefail` propagates the 141 — silently breaking the script.
# Use `if cmd | grep -qx 'X' >/dev/null` with an output-consuming wrapper,
# or split the pipeline (capture output to var, test the var).
# ---------------------------------------------------------------------------


_PIPEFAIL_RE = re.compile(r"set\s+-[eu]*o\s+pipefail|set\s+-[eu]*opipefail|set\s+-o\s+pipefail")
_GREP_Q_PIPE_RE = re.compile(r"\|\s*grep\s+(?:-[a-zA-Z]*q|-q[a-zA-Z]*)\b")


def check_pipefail_grep_q(repo_root: Path | None = None) -> list[dict]:
    """Detect the SIGPIPE-141 footgun: `cmd | grep -q ...` under
    `set -o pipefail`.

    Why this fires: `grep -q` exits 0 immediately on the first match and
    closes its stdin. The upstream `cmd` writer gets SIGPIPE (exit 141)
    when it next writes. With `pipefail` active, that 141 bubbles up as
    the pipeline's exit code — the surrounding `if` / `&&` short-circuits
    or aborts the script. Surfaced 2026-05-11 by Engineer M's
    `mole.sh` enumeration fix.

    Mitigations:
      - Split the pipeline: `out=$(cmd); echo "$out" | grep -q ...`.
      - Consume the full stream: `cmd | grep -q ... | cat >/dev/null`.
      - Use `grep` without `-q` and rely on `grep`'s normal exit code.

    Scope: `scripts/*.sh`. Same-file co-occurrence: both `pipefail` and
    a `| grep -q` pattern must appear in the same script (otherwise the
    footgun doesn't fire). Each `| grep -q` occurrence becomes a finding.

    Severity: `warning`.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    scripts_dir = root / "scripts"
    if not scripts_dir.exists():
        return issues

    for path in scripts_dir.glob("*.sh"):
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.debug("compliance: cannot read %s (%s)", path, exc)
            continue
        if not _PIPEFAIL_RE.search(content):
            continue
        try:
            relative = str(path.relative_to(root))
        except ValueError:
            relative = str(path)

        for line_no, raw in enumerate(content.splitlines(), start=1):
            # Skip comment-only lines (a comment showing the antipattern as
            # an example shouldn't fire). Lines that put a `#` AFTER code
            # still count — strip trailing comments.
            stripped = raw.lstrip()
            if stripped.startswith("#"):
                continue
            # Snap off trailing `#...` comments so an inline example in a
            # comment can't fire — but only when the `#` is whitespace-
            # preceded (avoid eating `--option` flags that include `#`).
            comment_match = re.search(r"(?<=\s)#", raw)
            scan_line = raw[: comment_match.start()] if comment_match else raw
            if not _GREP_Q_PIPE_RE.search(scan_line):
                continue
            issues.append({
                "product": "<scripts>",
                "file": relative,
                "issue": (
                    f"`{relative}:{line_no}` runs `... | grep -q ...` under "
                    f"`set -o pipefail`. `grep -q` exits 0 on first match "
                    f"and SIGPIPEs the upstream writer (exit 141); pipefail "
                    f"propagates 141 and silently breaks the script. Split "
                    f"the pipeline (`out=$(cmd); echo \"$out\" | grep -q`), "
                    f"consume the full stream (`| cat >/dev/null`), or drop "
                    f"`-q` and use grep's normal exit. Surfaced 2026-05-11 "
                    f"by Engineer M's `mole.sh` enumeration fix."
                ),
                "severity": "warning",
            })
    return issues


# ---------------------------------------------------------------------------
# `check_new_script_lacks_mcp_analog` — enforces the MCP-first-scripts rule
# (`KB § PATTERNS/architect/mcp-first-scripts.md`): every top-level `scripts/*.sh` /
# `scripts/*.py` MUST have a row in the classification manifest (§3 of that
# doc). A file on disk with no manifest row = an undecided new script that
# skipped the absorb-or-carve-out decision — the exact slip the rule
# prevents. The keeper asserts *presence of a bucket decision*, not
# disposition fidelity (disposition stays human-curated).
# ---------------------------------------------------------------------------

_MCP_FIRST_SCRIPTS_DOC = "KNOWLEDGE-BASE/CONTEXT/PATTERNS/architect/mcp-first-scripts.md"
# First backticked cell of a markdown table row: `| \`name.sh\` | ... |`.
_MANIFEST_ROW_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|", re.MULTILINE)


def check_new_script_lacks_mcp_analog(repo_root: Path | None = None) -> list[dict]:
    """Flag a top-level `scripts/*.sh|*.py` with no classification-manifest
    row in `KB § PATTERNS/architect/mcp-first-scripts.md` §3.

    Rule: a new automation script IS an agent-exposable capability → it
    defaults to a `noctus.dev.*` MCP tool, OR it is one of three named
    structural carve-outs. Either way the decision is recorded as a
    manifest row. A disk file with NO row means the absorb-vs-carve-out
    decision was skipped — surface it so it gets a bucket.

    Scope: top-level `scripts/*.sh` and `scripts/*.py` only (the doc's
    own keeper-scope note). Extensionless hook entries (`pre-commit`),
    `codemods/` lib, `init-local-db/*.sql` data, `*.log`, `README.md`
    are out of scope by construction. Absorb-backlog rows (bucket A/B/C)
    are removed as scripts are deleted — the invariant is row-per-disk-
    file, so removal stays consistent.

    Severity: `warning`.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    scripts_dir = root / "scripts"
    doc_path = root / _MCP_FIRST_SCRIPTS_DOC
    if not scripts_dir.exists() or not doc_path.exists():
        # No doc ⇒ rule not yet codified in this tree (e.g. a worktree off
        # an older base). Don't false-fire; the keeper-on-fork-base
        # discipline expects graceful absence.
        return issues

    try:
        doc = doc_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        logger.debug("compliance: cannot read %s (%s)", doc_path, exc)
        return issues

    # Slice the §3 manifest section so unrelated backticked tables elsewhere
    # in the doc can't widen the allow-set.
    start = doc.find("## 3.")
    if start == -1:
        return issues
    nxt = doc.find("\n## ", start + 1)
    section = doc[start : nxt if nxt != -1 else len(doc)]
    manifest = {m.group(1).strip() for m in _MANIFEST_ROW_RE.finditer(section)}

    # Recurse one+ levels (scripts/ is intent-foldered: hooks/ bootstrap/
    # infra/ — scripts-mcp-absorption Phase 6). Match by BASENAME so the
    # manifest rows are path-stable across folder moves. Exclude the
    # non-script subtrees the rule's scope-note already carves out.
    _EXCLUDE = {"codemods", "__pycache__", "init-local-db"}
    on_disk = sorted({
        p.name
        for p in list(scripts_dir.rglob("*.sh")) + list(scripts_dir.rglob("*.py"))
        if p.is_file()
        and not (_EXCLUDE & set(p.relative_to(scripts_dir).parts))
    })
    for name in on_disk:
        if name in manifest:
            continue
        issues.append({
            "product": "<scripts>",
            "file": f"scripts/{name}",
            "issue": (
                f"`scripts/{name}` has no classification-manifest row in "
                f"`{_MCP_FIRST_SCRIPTS_DOC}` §3. New automation defaults to "
                f"a `noctus.dev.*` MCP tool (+ `cli.py` flag + colocated "
                f"`Test*`), NOT a `scripts/` one-off. If it must stay shell "
                f"it is one of three named carve-outs (git-hook entry / "
                f"pre-venv bootstrap / thin docker-orchestration) — add the "
                f"manifest row AND a `KB § PATTERNS/common/accept-with-rationale.md` "
                f"entry. An undecided script is the slip this rule prevents."
            ),
            "severity": "warning",
        })
    return issues


# ---------------------------------------------------------------------------
# `check_doc_tool_reference_drift` — flags `bash scripts/<name>.sh <mode>`
# references in KB docs that point at a `<mode>` no longer recognized by
# the script. Per the doc-code coherence rule (`feedback_doc_code_coherence_rule`):
# updating a tool means updating its docs in the SAME change.
# ---------------------------------------------------------------------------


# Reference shape recognized in KB doc tables / prose:
#   `bash scripts/<name>.sh <mode>` where `<mode>` is a POSITIONAL token
# (not a flag — flags like `--force` are not the rename surface we worry
# about). Skip captures that begin with `-`; downstream flags are
# tolerated as drift-free.
#
# The detector confirms `<script>.sh` exists at `scripts/<name>.sh` and
# that the script body contains the literal token `<mode>`. False
# positives are acceptable only when the script dispatches `<mode>` via
# a variable lookup the detector can't follow; we keep the heuristic
# simple (literal token search) and accept that.
_DOC_TOOL_REF_RE = re.compile(
    r"bash\s+(scripts/(?P<script>[\w\-]+\.sh))\s+(?P<mode>[A-Za-z_][\w\-]*)\b",
)

# Docs in scope. Initial calibration: the most-stale-prone surface per the
# doc-code coherence rule. The list is intentionally small — adding to it
# is part of formalizing new doc surfaces, not a flag-the-world default.
_DOC_TOOL_REF_SCOPE: tuple[str, ...] = (
    "KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/methodology-codification-pipeline.md",
)


def check_doc_tool_reference_drift(repo_root: Path | None = None) -> list[dict]:
    """Detect KB doc references to `bash scripts/<name>.sh <mode>` where
    `<mode>` is not recognized by the script.

    Why: the doc-code coherence rule (`feedback_doc_code_coherence_rule`)
    requires KB pattern docs + Situation→Tool maps to stay in lockstep
    with tool-code. The most-stale-prone surface is the Situation→Tool
    map in `KB § PATTERNS/common/methodology-codification-pipeline.md § 8` —
    that's the initial calibration scope. Add to `_DOC_TOOL_REF_SCOPE`
    as additional doc surfaces become stale-prone.

    Heuristic: literal `bash scripts/<name>.sh <mode>` match. The detector
    confirms `<name>.sh` exists at `scripts/<name>.sh` and that the script
    body contains the token `<mode>`. A mismatch on either is drift.

    Severity: `warning`.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    scripts_dir = root / "scripts"
    script_cache: dict[str, str] = {}

    def _script_body(script_name: str) -> str | None:
        if script_name in script_cache:
            return script_cache[script_name]
        path = scripts_dir / script_name
        if not path.exists() or not path.is_file():
            script_cache[script_name] = ""
            return None
        try:
            body = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.debug("compliance: cannot read %s (%s)", path, exc)
            script_cache[script_name] = ""
            return None
        script_cache[script_name] = body
        return body

    for doc_rel in _DOC_TOOL_REF_SCOPE:
        doc_path = root / doc_rel
        if not doc_path.exists() or not doc_path.is_file():
            continue
        try:
            doc_content = doc_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.debug("compliance: cannot read %s (%s)", doc_path, exc)
            continue

        lines = doc_content.splitlines()
        for line_no, line in enumerate(lines, start=1):
            for m in _DOC_TOOL_REF_RE.finditer(line):
                script = m.group("script")            # "scripts/foo.sh"
                script_name = m.group(2)              # "foo.sh"
                mode = m.group("mode")
                body = _script_body(script_name)
                if body is None:
                    issues.append({
                        "product": "<docs>",
                        "file": doc_rel,
                        "issue": (
                            f"`{doc_rel}:{line_no}` references "
                            f"`bash {script} {mode}` but `{script}` does "
                            f"not exist. Either the script was renamed/"
                            f"deleted or the doc references a stale name. "
                            f"Per `feedback_doc_code_coherence_rule`."
                        ),
                        "severity": "warning",
                    })
                    continue
                # Look for the mode as a standalone token. Use word-boundary
                # match so `scan` isn't satisfied by `scanner` in the script.
                if re.search(rf"\b{re.escape(mode)}\b", body):
                    continue
                issues.append({
                    "product": "<docs>",
                    "file": doc_rel,
                    "issue": (
                        f"`{doc_rel}:{line_no}` references "
                        f"`bash {script} {mode}` but `{script_name}` does "
                        f"not mention the token `{mode}`. Either the mode "
                        f"was renamed in the script or the doc is stale. "
                        f"Per `feedback_doc_code_coherence_rule` — updating "
                        f"a tool means updating its docs in the SAME change."
                    ),
                    "severity": "warning",
                })

    return issues


# ---------------------------------------------------------------------------
# `check_seed_export_membership` — a symbol a validated product imports from
# the seed package surface (`noctusai_lib`/`noctusai_seed` backend,
# `@noctusai/lib`/`@noctusai/seed` frontend) MUST be in that package's
# public export surface (`__all__` for the backend package `__init__.py`,
# the re-export list in `seed/lib/frontend/src/index.ts`). A symbol that
# resolves to a module FILE but is absent from the public surface is a
# "reconciled-but-invisible" half-ship: the consumer happens to work via a
# deep import, but the seam is not actually published.
#
# N=2 evidence (social-wiring-absorption):
#   (a) W1.E2 — `lid_auth.py` shipped to `noctusai_lib.integrations.whatsapp`
#       with code present but ZERO `__all__` membership + no colocated tests.
#   (b) W2.4/DEP-B — `createWhatsApp{Connection,Intake}Hooks` + 6 types
#       consumed by validated product hooks but absent from
#       `seed/lib/frontend/src/index.ts`.
#
# Extends the verify-the-seed-ships-it rule (`feedback_verify_seed_ships_it`)
# from "file presence" to "public export-surface membership".
#
# Severity: `warning` (the consumer works via deep import today; the gap is
# a missed seam publication, not a runtime break).
# ---------------------------------------------------------------------------


# Backend: a `from <pkg-path> import <name>` is checked ONLY when
# <pkg-path> resolves to a PACKAGE (`<dir>/__init__.py`) that declares a
# literal `__all__`. That package's `__all__` IS its published public
# surface; a symbol a product pulls from it that is absent from `__all__`
# is the reconciled-but-invisible half-ship (lid_auth shape: the package
# `__init__.py` re-imports nothing / forgets the symbol, the consumer
# works only via a deeper path). A `from <pkg>.<module> import <name>`
# where `<module>.py` is a plain module is a *legitimate deep import*
# (the symbol is a top-level def there) and is NOT flagged — only the
# package-surface omission is the rule.
#
# import-root → that package's source root dir (relative to repo root).
_SEED_BACKEND_PACKAGE_ROOTS: dict[str, str] = {
    "noctusai_lib": "seed/lib/backend/noctusai_lib",
    "noctusai_seed": "seed/framework/backend/noctusai_seed",
}

# Frontend: each seed specifier resolves to its OWN package index; a
# `import { ... } from '<spec>'` is checked against THAT index's
# re-export surface. `@noctusai/seed` is the framework frontend (it
# publishes `createProductApp`/`createProductLayout`/...); `@noctusai/lib`
# is the lib frontend — distinct surfaces, distinct index.ts files.
_SEED_FRONTEND_INDEX_BY_SPEC: dict[str, str] = {
    "@noctusai/lib": "seed/lib/frontend/src/index.ts",
    "@noctusai/seed": "seed/framework/frontend/src/index.ts",
}

_SEED_EXPORT_SCAN_EXCLUDED_PARTS: frozenset[str] = frozenset({
    "__pycache__", ".venv", "venv", "node_modules", ".git",
    ".pytest_cache", "dist", "build", "tests", "__tests__",
})


def _parse_dunder_all(init_path: Path) -> set[str] | None:
    """Return the set of names in a package `__init__.py`'s top-level
    `__all__`, or None if the file can't be parsed / has no `__all__`.

    Only a literal list/tuple/set of string constants is understood — a
    computed `__all__` returns None (the detector then conservatively
    skips: false negatives over noise).
    """
    try:
        tree = ast.parse(init_path.read_text(encoding="utf-8"), filename=str(init_path))
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        logger.debug("compliance: cannot parse %s for __all__ (%s)", init_path, exc)
        return None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        targets = [t for t in node.targets if isinstance(t, ast.Name) and t.id == "__all__"]
        if not targets:
            continue
        value = node.value
        if not isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            return None
        names: set[str] = set()
        for elt in value.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                names.add(elt.value)
            else:
                # Non-literal element (splat, name, f-string) → can't
                # reason statically; skip this package.
                return None
        return names
    return None


def _imported_seed_symbols_backend(
    py_path: Path,
) -> list[tuple[str, str, str, int]]:
    """Yield `(pkg_root, module_dotted, symbol, lineno)` for every
    `from <module_dotted> import <sym>` where the top component of
    <module_dotted> is a tracked seed backend package.

    `import *` is skipped (no single symbol). The caller decides whether
    <module_dotted> resolves to a *package* (then `__all__` membership is
    the rule) or a plain module (legitimate deep import — not flagged).
    """
    out: list[tuple[str, str, str, int]] = []
    try:
        tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        logger.debug("compliance: cannot parse %s (%s)", py_path, exc)
        return out
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        pkg_root = node.module.split(".", 1)[0]
        if pkg_root not in _SEED_BACKEND_PACKAGE_ROOTS:
            continue
        for alias in node.names:
            if alias.name == "*":
                continue
            out.append((pkg_root, node.module, alias.name, node.lineno))
    return out


_FRONTEND_IMPORT_RE = re.compile(
    r"import\s+(?:type\s+)?\{(?P<names>[^}]*)\}\s+from\s+['\"](?P<spec>[^'\"]+)['\"]",
    re.DOTALL,
)
# Re-export / export surface lines in index.ts:
#   export { a, b as c } from './x';   export type { T } from './y';
#   export { foo };                     export const bar = ...
_FRONTEND_EXPORT_BRACE_RE = re.compile(
    r"export\s+(?:type\s+)?\{(?P<names>[^}]*)\}",
)
_FRONTEND_EXPORT_DECL_RE = re.compile(
    r"export\s+(?:default\s+)?"
    r"(?:const|let|var|function|class|interface|type|enum)\s+"
    r"(?P<name>[A-Za-z_$][\w$]*)",
)
_FRONTEND_EXPORT_STAR_RE = re.compile(r"export\s+\*\s+from")


def _frontend_index_export_surface(index_path: Path) -> set[str] | None:
    """Parse `seed/lib/frontend/src/index.ts` and return the set of
    publicly re-exported identifiers. Returns None if the file has a bare
    `export * from ...` (the surface is then non-enumerable statically →
    conservatively skip to avoid false positives).
    """
    try:
        content = index_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("compliance: cannot read %s (%s)", index_path, exc)
        return None
    if _FRONTEND_EXPORT_STAR_RE.search(content):
        return None
    surface: set[str] = set()
    for m in _FRONTEND_EXPORT_BRACE_RE.finditer(content):
        for raw in m.group("names").split(","):
            tok = raw.strip()
            if not tok:
                continue
            # `a as b` exposes `b`; `a` exposes `a`.
            exposed = tok.split(" as ")[-1].strip() if " as " in tok else tok
            if exposed:
                surface.add(exposed)
    for m in _FRONTEND_EXPORT_DECL_RE.finditer(content):
        surface.add(m.group("name"))
    return surface


def _imported_frontend_seed_symbols(
    ts_path: Path,
) -> list[tuple[str, str, int]]:
    """Yield `(specifier, symbol, lineno)` for every
    `import { ... } from '<spec>'` where <spec> is a tracked seed frontend
    specifier. A bare-specifier subpath import
    (`@noctusai/lib/something`) is skipped — only the package root
    specifier publishes via `index.ts`.
    """
    out: list[tuple[str, str, int]] = []
    try:
        content = ts_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("compliance: cannot read %s (%s)", ts_path, exc)
        return out
    for m in _FRONTEND_IMPORT_RE.finditer(content):
        spec = m.group("spec")
        if spec not in _SEED_FRONTEND_INDEX_BY_SPEC:
            continue
        lineno = content.count("\n", 0, m.start()) + 1
        for raw in m.group("names").split(","):
            tok = raw.strip()
            if not tok:
                continue
            # `import { a as b }` consumes the exported name `a`.
            consumed = tok.split(" as ")[0].strip()
            if consumed:
                out.append((spec, consumed, lineno))
    return out


def check_seed_export_membership(repo_root: Path | None = None) -> list[dict]:
    """A symbol a product imports from the seed package surface must be in
    that package's public export surface (`__all__` backend / `index.ts`
    re-exports frontend).

    Catches the "reconciled-but-invisible" half-ship: code lifted into a
    seed module file but never published in the package's `__all__` /
    `index.ts`, so the seam is not actually offered to other products even
    though one deep-importing consumer happens to work.

    Per `feedback_seed_export_membership_keeper` — extends the
    verify-the-seed-ships-it rule from file-presence to export-surface
    membership. N=2 evidenced by social-wiring-absorption W1.E2 (lid_auth)
    + W2.4/DEP-B (frontend WA hooks).

    Severity: `warning`.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    products_dir = root / "products"

    # ---- Backend: resolve `<pkg>.<a>.<b>` → that package's `__init__.py`
    # `__all__`. Only flag when the imported module path is a PACKAGE that
    # declares a literal `__all__` and the symbol is absent from it (the
    # reconciled-but-invisible half-ship). A path that resolves to a plain
    # `<module>.py` is a legitimate deep import and is never flagged.
    _all_cache: dict[str, set[str] | None] = {}

    def _package_dir_and_all(
        pkg_root: str, module_dotted: str,
    ) -> tuple[Path | None, set[str] | None]:
        """Return `(package_dir, __all__set)` where `package_dir` is the
        on-disk dir for the imported PACKAGE path (or None if it does not
        resolve to a package-with-literal-`__all__`), and `__all__set` is
        that package's literal `__all__` (or None).
        """
        if module_dotted in _all_cache:
            return _all_cache[module_dotted]
        src_root = root / _SEED_BACKEND_PACKAGE_ROOTS[pkg_root]
        # Map `noctusai_lib.integrations.whatsapp` → src_root/integrations/whatsapp
        rest = module_dotted.split(".")[1:]
        target_dir = src_root.joinpath(*rest) if rest else src_root
        init_path = target_dir / "__init__.py"
        result: tuple[Path | None, set[str] | None]
        if target_dir.is_dir() and init_path.exists():
            result = (target_dir, _parse_dunder_all(init_path))
        else:
            # Plain module (`<...>.py`) or unresolvable — not a package
            # public-surface; legitimate deep import. Skip.
            result = (None, None)
        _all_cache[module_dotted] = result
        return result

    def _is_submodule_name(pkg_dir: Path, name: str) -> bool:
        """True iff `name` is itself a submodule/subpackage of `pkg_dir`
        (`pkg_dir/<name>.py` or `pkg_dir/<name>/__init__.py`). Such a
        `from <pkg> import <name>` is a *module import*, NOT a symbol
        re-export — Python imports submodules regardless of `__all__`, so
        the half-ship rule does not apply.
        """
        return (pkg_dir / f"{name}.py").exists() or (
            pkg_dir / name / "__init__.py"
        ).exists()

    # ---- Frontend: per-specifier index surface. `@noctusai/lib` and
    # `@noctusai/seed` resolve to DIFFERENT index.ts files. ----
    frontend_surface_by_spec: dict[str, set[str] | None] = {}
    for spec, idx_rel in _SEED_FRONTEND_INDEX_BY_SPEC.items():
        idx_path = root / idx_rel
        frontend_surface_by_spec[spec] = (
            _frontend_index_export_surface(idx_path)
            if idx_path.exists() else None
        )

    if not products_dir.exists():
        return issues

    for product_dir in sorted(products_dir.iterdir()):
        if not product_dir.is_dir() or product_dir.name.startswith("."):
            continue
        slug = product_dir.name

        # Backend product source.
        backend_app = product_dir / "backend" / "app"
        if backend_app.exists():
            for py_path in backend_app.rglob("*.py"):
                if any(p in _SEED_EXPORT_SCAN_EXCLUDED_PARTS for p in py_path.parts):
                    continue
                for pkg_root, mod_dotted, sym, lineno in (
                    _imported_seed_symbols_backend(py_path)
                ):
                    pkg_dir, surface = _package_dir_and_all(pkg_root, mod_dotted)
                    if surface is None or pkg_dir is None:
                        # Not a package-with-literal-`__all__` (plain
                        # module deep import / computed __all__ / missing)
                        # → can't / shouldn't assert; skip.
                        continue
                    if sym in surface:
                        continue
                    if _is_submodule_name(pkg_dir, sym):
                        # `from <pkg> import <submodule>` — a module
                        # import, governed by import machinery not
                        # `__all__`. Not the half-ship rule.
                        continue
                    try:
                        rel = str(py_path.relative_to(root))
                    except ValueError:
                        rel = str(py_path)
                    issues.append({
                        "product": slug,
                        "file": rel,
                        "issue": (
                            f"`{rel}:{lineno}` imports `{sym}` from package "
                            f"`{mod_dotted}` but `{sym}` is NOT in that "
                            f"package's `__all__`. Reconciled-but-invisible "
                            f"half-ship: the import resolves via the package "
                            f"but the symbol is not in its published "
                            f"surface. Add `{sym}` to "
                            f"`{mod_dotted}.__all__` (or re-export it from "
                            f"the package `__init__.py`). Per "
                            f"`feedback_seed_export_membership_keeper`."
                        ),
                        "severity": "warning",
                    })

        # Frontend product source.
        frontend_src = product_dir / "frontend" / "src"
        if frontend_src.exists():
            for ts_path in frontend_src.rglob("*"):
                if not ts_path.is_file():
                    continue
                if ts_path.suffix not in {".ts", ".tsx"}:
                    continue
                if any(
                    p in _SEED_EXPORT_SCAN_EXCLUDED_PARTS
                    for p in ts_path.parts
                ):
                    continue
                for spec, sym, lineno in _imported_frontend_seed_symbols(ts_path):
                    surface = frontend_surface_by_spec.get(spec)
                    if surface is None:
                        # That specifier's index is missing / non-enumerable
                        # (`export *`) → conservatively skip.
                        continue
                    if sym in surface:
                        continue
                    try:
                        rel = str(ts_path.relative_to(root))
                    except ValueError:
                        rel = str(ts_path)
                    idx_rel = _SEED_FRONTEND_INDEX_BY_SPEC[spec]
                    issues.append({
                        "product": slug,
                        "file": rel,
                        "issue": (
                            f"`{rel}:{lineno}` imports `{sym}` from "
                            f"`{spec}` but `{sym}` is NOT re-exported from "
                            f"`{idx_rel}`. Reconciled-but-invisible "
                            f"half-ship: the import works but the seam is "
                            f"not published. Add `{sym}` to the `index.ts` "
                            f"re-export surface. Per "
                            f"`feedback_seed_export_membership_keeper`."
                        ),
                        "severity": "warning",
                    })

    return issues


# ---------------------------------------------------------------------------
# `check_hardcoded_product_slug_set` — a seed test
# (`seed/lib/backend/tests/`) must NOT freeze a literal tuple/set/list of
# product slugs; it must derive the product set from
# `parse_products_registry()` (the single source of truth). A frozen literal
# goes stale the moment a product is added/removed/consolidated.
#
# N=2 evidence (social-wiring-absorption W3.5): `test_cors_registry` +
# `test_per_product_cors_sentinel` both froze product-slug tuples/sets that
# went stale when `media-scheduling` was consolidated — surfacing as CORS
# assertion failures attributed (twice) to the wrong commit before git-`-S`
# settled it.
#
# Severity: `warning`.
# ---------------------------------------------------------------------------


# Known product slugs the detector recognizes as the "product set" marker.
# A literal collection containing ≥ this many of these is a frozen slug set.
# Derived from the live products/ tree at scan time so the detector itself
# does NOT freeze a literal (it would otherwise violate its own rule).
_SLUG_LITERAL_MIN_HITS: int = 3

# Test files that legitimately enumerate slugs for a non-registry reason
# (e.g. a fixture mapping slug→schema) can carry a rationale keyword in a
# nearby comment / docstring; mirrors the `check_mock_schema_validation`
# opt-out guardrail.
_SLUG_LITERAL_RATIONALE_RE = re.compile(
    r"slug-literal-ok|registry-exempt|not-a-product-set",
    re.IGNORECASE,
)


def _live_product_slugs(root: Path) -> set[str]:
    """Set of product directory names under `products/` — the live fleet.
    Used as the recognizer corpus so the detector does not itself freeze a
    product-slug literal (which would violate the rule it enforces).
    """
    products = root / "products"
    if not products.exists():
        return set()
    return {
        d.name for d in products.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    }


def _string_constants_in_collection(node: ast.AST) -> list[str] | None:
    """If `node` is a List/Tuple/Set literal of string constants, return
    the strings; else None.
    """
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return None
    out: list[str] = []
    for elt in node.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            out.append(elt.value)
        else:
            return None
    return out


def check_hardcoded_product_slug_set(repo_root: Path | None = None) -> list[dict]:
    """Seed tests must derive product sets from `parse_products_registry()`,
    never freeze a product-slug literal.

    A literal tuple/set/list under `seed/lib/backend/tests/` that contains
    ≥3 live product slugs is a frozen product-slug set: it goes stale the
    moment the fleet changes (product added / removed / consolidated) and
    produces misattributed assertion failures.

    Opt-out: a `slug-literal-ok` / `registry-exempt` / `not-a-product-set`
    rationale keyword in a nearby comment or docstring (mirrors the
    `check_mock_schema_validation` guardrail) — for the rare legitimate
    slug→x fixture mapping.

    Per `feedback_hardcoded_product_slug_set_keeper`. N=2 evidenced by
    social-wiring-absorption W3.5 (cors_registry + per_product_cors_sentinel).

    Severity: `warning`.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    seed_tests = root / "seed" / "lib" / "backend" / "tests"
    if not seed_tests.exists():
        return issues

    live_slugs = _live_product_slugs(root)
    if not live_slugs:
        # No fleet to compare against — cannot reason; skip.
        return issues

    # NB: `_SEED_EXPORT_SCAN_EXCLUDED_PARTS` includes "tests" — but this
    # detector scans *inside* `seed/lib/backend/tests/` deliberately, so we
    # only exclude transient/build dirs here, never the tests tree itself.
    _slug_excluded = _SEED_EXPORT_SCAN_EXCLUDED_PARTS - {"tests", "__tests__"}
    for py_path in seed_tests.rglob("*.py"):
        if any(p in _slug_excluded for p in py_path.parts):
            continue
        try:
            content = py_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("compliance: cannot read %s (%s)", py_path, exc)
            continue
        if _SLUG_LITERAL_RATIONALE_RE.search(content):
            continue
        try:
            tree = ast.parse(content, filename=str(py_path))
        except SyntaxError as exc:
            logger.debug("compliance: cannot parse %s (%s)", py_path, exc)
            continue

        try:
            rel = str(py_path.relative_to(root))
        except ValueError:
            rel = str(py_path)

        for node in ast.walk(tree):
            collection: ast.AST | None = None
            if isinstance(node, ast.Assign):
                collection = node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                collection = node.value
            else:
                continue
            strings = _string_constants_in_collection(collection)
            if strings is None:
                continue
            hits = sorted(set(strings) & live_slugs)
            if len(hits) < _SLUG_LITERAL_MIN_HITS:
                continue
            lineno = getattr(collection, "lineno", node.lineno)
            issues.append({
                "product": "<seed-tests>",
                "file": rel,
                "issue": (
                    f"`{rel}:{lineno}` freezes a literal collection of "
                    f"product slugs ({len(hits)} live slugs: "
                    f"{', '.join(hits[:5])}{'…' if len(hits) > 5 else ''}). "
                    f"A frozen product-slug literal goes stale when the "
                    f"fleet changes (product added/removed/consolidated) "
                    f"and misattributes assertion failures. Derive from "
                    f"`parse_products_registry()` "
                    f"(`noctusai_lib.config.cors_registry`) — the single "
                    f"source of truth — instead. If this is a legitimate "
                    f"non-product-set mapping, add a `slug-literal-ok` "
                    f"rationale comment. Per "
                    f"`feedback_hardcoded_product_slug_set_keeper`."
                ),
                "severity": "warning",
            })

    return issues


# ---------------------------------------------------------------------------
# `check_hardcoded_fleet_size_literal` — a seed test
# (`seed/lib/backend/tests/`) must NOT assert a frozen *fleet-size* numeric
# literal (`len(...) >= 10`, `== 12`, `> 8`, …) against a registry-derived
# collection. A frozen count goes stale the moment a product is added /
# removed / consolidated — exactly the same failure class as a frozen
# product-slug set (`check_hardcoded_product_slug_set`), but on the numeric
# axis rather than the string-collection axis.
#
# N=3 evidence (social-wiring-absorption W3.5/W4):
#   - `test_per_product_cors_sentinel.py` `PRODUCT_SLUGS` (slug axis →
#     covered by `check_hardcoded_product_slug_set`; the *count* it implies
#     is the same staleness vector).
#   - `test_cors_registry.py:130` `assert len(entries) >= 8` and `:247`
#     `assert len(origins) >= 10` — frozen fleet-size floors that needed
#     hand-editing when `media-scheduling`/`youtube-crawler`/`mailing`/
#     `imobi-scheduling` were consolidated into `social-wiring`.
#   - `test_scaffold.py` `RESERVED_RANGES` / used-ports expectations —
#     frozen fleet-derived numeric expectations with the same drift vector.
#
# Predicate (deterministic): inside `seed/lib/backend/tests/`, an
# `ast.Compare` whose left operand is a `len(<call|name>)` call and whose
# comparator is an integer `ast.Constant` ≥ `_FLEET_SIZE_FLOOR` — UNLESS
# the comparison's `len()` argument is itself registry-derived in the same
# function (a comprehension/call referencing `parse_products_registry` /
# `cors_registry`) or a rationale keyword opts out. Mirrors
# `check_hardcoded_product_slug_set`'s shape exactly.
#
# Severity: `warning`.
# ---------------------------------------------------------------------------


# A `len(...) <op> N` where N ≥ this floor is treated as a fleet-size
# expectation (the noc fleet is ≈8-12 products; a smaller literal is far
# more likely an unrelated bound like a header count or retry cap and is
# left alone — false-positive suppression, mirroring `_SLUG_LITERAL_MIN_HITS`).
_FLEET_SIZE_FLOOR: int = 5

# Same opt-out family as the slug-set detector — a nearby rationale keyword
# marks a legitimate non-fleet count (mirrors `check_mock_schema_validation`
# and `check_hardcoded_product_slug_set`).
_FLEET_SIZE_RATIONALE_RE = re.compile(
    r"fleet-size-ok|registry-exempt|not-a-fleet-count",
    re.IGNORECASE,
)

# Tokens that, if they appear anywhere in the enclosing function source,
# mean the `len()` argument is registry-derived (single source of truth) —
# the count is computed, not frozen, so it does NOT stale.
_REGISTRY_DERIVED_TOKENS = ("parse_products_registry", "cors_registry")

# POSITIVE ANCHOR (false-positive suppression — the W5.9a calibration
# lesson): a bare `len(x) == 20` is almost always an unrelated bound
# (token count, buffer size, listing length). It is only a *fleet-size*
# literal if the count is semantically a count of products / CORS origins
# / registry rows. We require the enclosing-function source to mention at
# least one fleet-semantic token. This mirrors how
# `check_hardcoded_product_slug_set` requires actual live slug *strings*
# present (a positive content anchor), not merely "a numeric literal".
# Substring (not \b-anchored) — snake_case identifiers like
# `test_products_registry_populated` have `_` word-chars on both sides of
# the token, so word-boundary anchors would miss them. Plain substring
# match mirrors `_REGISTRY_DERIVED_TOKENS`'s `in`-test semantics.
_FLEET_SEMANTIC_RE = re.compile(
    r"(?:parse_products_registry|cors_registry|cors_origin|"
    r"products_registry|product_slug|fleet|start\.sh|"
    r"registry_all|registry_own|@registry)",
    re.IGNORECASE,
)


def _len_call_arg(node: ast.AST) -> ast.AST | None:
    """If `node` is a `len(<x>)` call, return `<x>`; else None."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "len"
        and len(node.args) == 1
    ):
        return node.args[0]
    return None


def check_hardcoded_fleet_size_literal(repo_root: Path | None = None) -> list[dict]:
    """Seed tests must not assert a frozen fleet-size numeric literal.

    A `len(<collection>) <op> N` (with N ≥ `_FLEET_SIZE_FLOOR`) under
    `seed/lib/backend/tests/` freezes a count that goes stale the instant
    the fleet changes (product added / removed / consolidated) — the same
    drift vector as a frozen product-slug set, on the numeric axis. Derive
    the bound from `parse_products_registry()` (the single source of truth)
    or assert a structural invariant ("populated", "non-empty") instead.

    Suppression (no false positives):
      - the `len()` argument is registry-derived within the enclosing
        function (a `parse_products_registry` / `cors_registry` reference);
      - a `fleet-size-ok` / `registry-exempt` / `not-a-fleet-count`
        rationale keyword appears nearby (mirrors the slug-set detector);
      - N < `_FLEET_SIZE_FLOOR` (small bounds are almost never fleet-size).

    Per `feedback_hardcoded_fleet_size_literal_keeper`. N=3 evidenced by
    social-wiring-absorption (cors_registry `>=8`/`>=10`, scaffold
    RESERVED_RANGES, per_product_cors_sentinel count).

    Severity: `warning`.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    seed_tests = root / "seed" / "lib" / "backend" / "tests"
    if not seed_tests.exists():
        return issues

    _excluded = _SEED_EXPORT_SCAN_EXCLUDED_PARTS - {"tests", "__tests__"}
    for py_path in seed_tests.rglob("*.py"):
        if any(p in _excluded for p in py_path.parts):
            continue
        try:
            content = py_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("compliance: cannot read %s (%s)", py_path, exc)
            continue
        if _FLEET_SIZE_RATIONALE_RE.search(content):
            continue
        try:
            tree = ast.parse(content, filename=str(py_path))
        except SyntaxError as exc:
            logger.debug("compliance: cannot parse %s (%s)", py_path, exc)
            continue

        try:
            rel = str(py_path.relative_to(root))
        except ValueError:
            rel = str(py_path)

        # Map every node to its enclosing FunctionDef so we can check
        # whether the count is registry-derived in the same function.
        func_src_by_node: dict[int, str] = {}
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                try:
                    fn_src = ast.get_source_segment(content, fn) or ""
                except (ValueError, TypeError):
                    fn_src = ""
                for child in ast.walk(fn):
                    func_src_by_node[id(child)] = fn_src

        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare) or len(node.ops) != 1:
                continue
            op = node.ops[0]
            if not isinstance(op, (ast.GtE, ast.Gt, ast.Eq, ast.LtE, ast.Lt)):
                continue
            # Identify which side is `len(...)` and which is the int const.
            len_arg = _len_call_arg(node.left)
            const_node = node.comparators[0]
            if len_arg is None:
                len_arg = _len_call_arg(node.comparators[0])
                const_node = node.left
            if len_arg is None:
                continue
            if not (
                isinstance(const_node, ast.Constant)
                and isinstance(const_node.value, int)
                and not isinstance(const_node.value, bool)
            ):
                continue
            if const_node.value < _FLEET_SIZE_FLOOR:
                continue
            fn_src = func_src_by_node.get(id(node), "")
            # Registry-derived in the enclosing function → computed, not
            # frozen → does not stale → suppress.
            if any(tok in fn_src for tok in _REGISTRY_DERIVED_TOKENS):
                continue
            # Positive anchor: only a *fleet-semantic* count can stale on a
            # fleet change. A bare `len(x) == 20` (token count, buffer
            # size, listing length) is not a fleet literal — suppress
            # unless the enclosing function references a fleet/registry
            # concept (the W5.9a live-FP-sweep calibration lesson).
            if not _FLEET_SEMANTIC_RE.search(fn_src):
                continue
            lineno = getattr(node, "lineno", 0)
            issues.append({
                "product": "<seed-tests>",
                "file": rel,
                "issue": (
                    f"`{rel}:{lineno}` asserts a frozen fleet-size literal "
                    f"(`len(...) {type(op).__name__} {const_node.value}`). "
                    f"A frozen fleet count goes stale when the fleet changes "
                    f"(product added/removed/consolidated) and misattributes "
                    f"assertion failures. Derive the bound from "
                    f"`parse_products_registry()` "
                    f"(`noctusai_lib.config.cors_registry`) — the single "
                    f"source of truth — or assert a structural invariant "
                    f"(non-empty / populated) instead. If this is a "
                    f"legitimate non-fleet count, add a `fleet-size-ok` "
                    f"rationale comment. Per "
                    f"`feedback_hardcoded_fleet_size_literal_keeper`."
                ),
                "severity": "warning",
            })

    return issues


# ---------------------------------------------------------------------------
# `check_doc_symbology_drift` — Stage-4 codification of the symbol-first
# authoring methodology (`feedback_doc_symbology` / `feedback_symbol_first_
# authoring`, KB § CONTEXT/PATTERNS/common/doc-symbology.md). N=3 drift signal
# (user 2026-05-12 "make sure future docs follow the symbology pattern")
# flips the memory "Held at Stage 3" gate.
#
# Warn-only. The rule is judgment-dependent ("swap only when lossless") and
# bimodal-yield, so a *blocking* detector would flood noise on narrative
# prose. This detector surfaces the two DETERMINISTIC drift classes the
# glossary's own Anti-patterns section names:
#
#   (1) `→` vs `⇒` conflation — the glossary's explicit convention is
#       `→` = routes/pointer, `⇒` = logical-implies. Using BOTH on a single
#       dense-doc line is the "use → to mean both" anti-pattern. We flag a
#       line that contains BOTH glyphs (the conflation is inherently
#       intra-line — one means routes, one means implies; mixing on the
#       same line is the documented smell). Lines with only one glyph are
#       NOT flagged (single-meaning use is correct).
#   (2) Out-of-glossary symbol use in a symbol-eligible doc — a glyph that
#       looks like glossary symbology (drawn from the same Unicode blocks:
#       arrows, logic/set operators, the status-icon emoji the glossary
#       defines) but is NOT in the parsed glossary. "Inventing new symbols
#       without adding them here" is the second named anti-pattern.
#
# Scope (`_SYMBOLOGY_DOC_SCOPE`): the dense-doc surfaces the glossary §2
# "Where to use" enumerates — CLAUDE.md, CLAUDE/*.md, KB CONTEXT/PATTERNS/
# *.md, products/*/MASTER-PROMPT.md. NOT README narrative / error strings /
# code (the glossary §3 "Where NOT to use" set).
#
# Glossary-driven: the symbol set is PARSED from doc-symbology.md §1
# tables (first column of every `| Symbol | … |` row). New glossary
# additions auto-propagate — no detector edit. If the glossary can't be
# parsed the detector emits a parse-surface warning, not drift noise (the
# §8 dependency contract).
#
# Severity: `warning`.
# ---------------------------------------------------------------------------


# Dense-doc surfaces in scope — the glossary §2 "Where to use" set.
# Patterns are repo-root-relative globs resolved with `Path.glob`.
# Extended 2026-05-25 (harness-agents-skills) — the new always-on harness
# surfaces (.claude/agents/*.md + .claude/skills/**/SKILL.md) are AI-intended
# docs per CLAUDE.md §1 doc-symbology rule and were previously ungated for
# symbology drift.
_SYMBOLOGY_DOC_GLOBS: tuple[str, ...] = (
    "CLAUDE.md",
    "CLAUDE/*.md",
    # FLAT pattern (pre-reorg legacy) — keeps tolerance for trees that
    # haven't migrated yet; current noc tree has no docs at this level.
    "KNOWLEDGE-BASE/CONTEXT/PATTERNS/*.md",
    # OWNERSHIP-organized pattern (post-`cec3533e` PATTERNS reorg) —
    # the live shape. Required after 2026-05-26 doc-sprint.
    "KNOWLEDGE-BASE/CONTEXT/PATTERNS/*/*.md",
    "products/*/MASTER-PROMPT.md",
    ".claude/agents/*.md",
    ".claude/skills/*/SKILL.md",
)

# The KB doc the glossary is parsed from (single source of truth).
_SYMBOLOGY_GLOSSARY_DOC = "KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/doc-symbology.md"

# A markdown table row in the glossary §1: `| <symbol> | <meaning> | … |`.
# We take the FIRST cell. Header / separator rows are skipped (they hold
# the literal word "Symbol" or only dashes/pipes/colons).
_GLOSSARY_ROW_RE = re.compile(r"^\|\s*(?P<cell>[^|]+?)\s*\|")

# A glyph "looks like symbology" if it is in the Unicode ranges the
# glossary draws from: arrows (U+2190–U+21FF), mathematical operators
# (U+2200–U+22FF — ∧ ∨ ¬ ∈ ⊂ ≡ ≠ ≈ ≥ ≤ Σ etc.), the Greek delta/sigma
# the glossary uses (Δ U+0394, Σ U+03A3), and the specific status-icon
# emoji the glossary §1 "Status" table defines. We do NOT treat ALL emoji
# as symbology (prose docs legitimately use 🚀/🎉 etc.) — only the glyphs
# whose Unicode class the glossary actually populates, so a non-glossary
# member of THOSE classes is a true "invented symbol".
_SYMBOLOGY_GLYPH_RE = re.compile(
    "["
    "←-⇿"   # arrows  (→ ↔ ⇒ …)
    "∀-⋿"   # math operators (∧ ∨ ¬ ∈ ⊂ ≡ ≠ ≈ ≥ ≤ Σ …)
    "ΔΣ"    # Δ (delta), Σ (sigma) — glossary "Counts" table
    "]"
)

# The status-icon emoji the glossary §1 "Status" table defines. These are
# the ONLY emoji the detector treats as symbology-class (so an
# out-of-glossary status-ish emoji in a forbidden context is caught
# without flagging unrelated decorative emoji). Kept as an explicit set —
# parsed-glossary membership still governs which are *allowed*; this set
# only scopes which emoji are *symbology-class at all*.
_STATUS_EMOJI: frozenset[str] = frozenset(
    "✅⏳❌🔒📋🗑⭐⚠️🟢🟡🔴"
)

# Typographic / arithmetic glyphs that fall in the symbology Unicode
# blocks but are LEGITIMATE PROSE, not invented relational/logic symbols.
# `−` (U+2212 MINUS SIGN) appears in arithmetic prose ("Net: −848 LOC");
# `×` `÷` are arithmetic; `–` `—` are en/em dashes. Excluding these is
# the live-tree calibration lesson — the count/membership-detector rule
# (a detector needs a positive content anchor, not just a Unicode-class
# net): the symbology contract governs *relational/logic/status* glyphs,
# not arithmetic or dashes. None of these carry a fixed glossary meaning,
# so a doc using them is doing arithmetic/typography, not inventing
# symbology.
_PROSE_PUNCTUATION: frozenset[str] = frozenset("−×÷–—‐‑‒―∼")

# Contexts where symbology must NOT appear even if glossary-defined — the
# glossary §3 "Where NOT to use" set, deterministic subset: a fenced code
# block. (Error strings / quoted-user / first-paragraph are
# judgment-dependent — held out of the warn-only predicate to keep FP
# rate low; the out-of-glossary check below is the deterministic core.)
#
# NOTE — `→`/`⇒` STRICT-INTERCHANGE detection is intentionally NOT
# implemented: it is the project's still-OPEN Phase-0 question Q4 ("strict
# interchange detection or accept some prose `→`?") and is NOT
# deterministic — the glossary's OWN §7 reference patterns legitimately
# carry both glyphs on one line with distinct correct meanings (e.g.
# `s1 emerges → s2 memory → … ⇒ formalize`). A "both glyphs on one line"
# heuristic flags the glossary's own canonical examples (5 live FPs on
# the calibration tree). The LOCKED core (§3/§5) — out-of-glossary
# symbology in symbol-eligible docs, glossary-driven, warn-only — ships;
# Q4 is returned to the architect as a TEXT open question.


def _parse_symbology_glossary(glossary_text: str) -> set[str]:
    """Parse the doc-symbology §1 tables → the set of defined symbol glyphs.

    Reads the first cell of every markdown table row, strips backticks,
    and splits on whitespace/slash so multi-symbol cells like
    `` `🟢` `🟡` `🔴` `` or `` `s1`/`s2`/`s3`/`s4` `` each contribute
    their atoms. Returns the set of glyph tokens that contain at least one
    symbology-class character (so prose meanings like "AND" are excluded —
    only the actual symbol is registered).

    Raises `ValueError` if no rows parse (the §8 parse-surface contract —
    the caller turns this into a parse warning, not silent drift).
    """
    symbols: set[str] = set()
    for raw_line in glossary_text.splitlines():
        line = raw_line.strip()
        m = _GLOSSARY_ROW_RE.match(line)
        if not m:
            continue
        cell = m.group("cell").strip()
        # Skip header ("Symbol") + separator (---|:--:) rows.
        if cell.lower() == "symbol" or set(cell) <= {"-", ":", " "}:
            continue
        # A cell may hold several backtick-wrapped atoms.
        for atom in re.split(r"[\s/]+", cell.replace("`", " ")):
            atom = atom.strip()
            if not atom:
                continue
            if _SYMBOLOGY_GLYPH_RE.search(atom) or atom in _STATUS_EMOJI:
                symbols.add(atom)
            else:
                # Single-glyph emoji cell (e.g. `✅`) — register the glyph.
                for ch in atom:
                    if ch in _STATUS_EMOJI:
                        symbols.add(ch)
    if not symbols:
        raise ValueError(
            "doc-symbology.md §1 tables parsed to zero symbols — the "
            "glossary format contract is broken (see §8)."
        )
    return symbols


def _iter_fenced_code_spans(lines: list[str]) -> set[int]:
    """Return the set of 1-based line numbers inside ``` fenced blocks."""
    inside: set[int] = set()
    fence_open = False
    for idx, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            fence_open = not fence_open
            inside.add(idx)  # the fence line itself is code-class
            continue
        if fence_open:
            inside.add(idx)
    return inside


# Direct backend requirements whose dependency closure includes a package
# with NO prebuilt wheel for the fleet build arch (linux/arm64), forcing a
# pip source-build the slim runtime stage cannot do without the per-slug
# PIP_RUN toolchain seam. Curated; grows as discovered (same maintenance
# model as the slug-set / fleet-size curated sets). KB § containerization §3.2a.
_SOURCE_BUILD_DEP_ROOTS = {
    # xhtml2pdf → svglib → rlpycairo → pycairo; pycairo has no arm64 wheel
    # (meson source build). erp-imobiliario, 2026-05-18 fix-on-contact.
    "xhtml2pdf",
    "pycairo",
}


def check_product_source_build_dep_pip_seam(
    repo_root: Path | None = None,
) -> list[dict]:
    """A product whose backend requirements pull a source-only (no
    arm64-wheel) dependency MUST have a per-slug ``PIP_RUN`` toolchain
    seam in ``scripts/propagate-dockerfiles.sh`` — else the fleet build
    aborts in the slim runtime stage (``meson … Unknown compiler``):
    product pip-installs run in the slim runtime (the base *builder*
    stage has the toolchain; products ``FROM …AS runtime``).

    Stage-4 codification of ``KB § PATTERNS/devops/containerization.md §3.2a``
    (that section is the remediation; this detector is the "extra layer
    of checking" ensuring every product follows it). Deterministic:
    reads each product's ``requirements.txt`` + the ``PIP_RUN = { … }``
    block of the propagate script. No network, no transitive resolution
    (``_SOURCE_BUILD_DEP_ROOTS`` encodes the known no-arm64-wheel roots).

    Green at introduction (erp-imobiliario has the seam; no other product
    carries a source-only root) — guards against (a) a new product adding
    such a dep with no seam, (b) erp's seam being removed. Severity
    ``high`` — a missing seam is a hard fleet-build blocker, not a nit.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    prop = root / "scripts" / "propagate-dockerfiles.sh"
    products_dir = root / "products"
    if not prop.exists() or not products_dir.exists():
        return issues
    try:
        prop_src = prop.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("compliance: cannot read %s (%s)", prop, exc)
        return issues

    # Deterministic extraction of the per-slug PIP_RUN dict body: a slug
    # with an entry appears as a quoted key inside `PIP_RUN = { … }`.
    if "PIP_RUN = {" in prop_src:
        seam_body = prop_src.split("PIP_RUN = {", 1)[1].split("\n}", 1)[0]
    else:
        seam_body = ""

    for d in sorted(products_dir.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        req = d / "backend" / "requirements.txt"
        if not req.exists():
            continue
        try:
            req_src = req.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("compliance: cannot read %s (%s)", req, exc)
            continue
        pkgs: set[str] = set()
        for raw in req_src.splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith(("#", "-")):
                continue
            name = re.split(r"[<>=!~;\[\s]", stripped)[0].strip().lower()
            if name:
                pkgs.add(name)
        hits = sorted(pkgs & _SOURCE_BUILD_DEP_ROOTS)
        if not hits:
            continue
        if f'"{d.name}"' in seam_body:
            continue  # seam present — correctly handled per §3.2a
        issues.append({
            "product": d.name,
            "file": f"products/{d.name}/backend/requirements.txt",
            "severity": "high",
            "issue": (
                f"{d.name} requires source-only dependency(ies) {hits} "
                f"(no linux/arm64 wheel → pip source-build) but has NO "
                f'per-slug PIP_RUN toolchain seam for "{d.name}" in '
                f"scripts/propagate-dockerfiles.sh. The fleet build will "
                f"abort in the slim runtime stage (`meson … Unknown "
                f"compiler`). Add a per-slug PIP_RUN entry (install+purge "
                f"the toolchain in the SAME layer) per "
                f"KB § PATTERNS/devops/containerization.md §3.2a; if a 2nd "
                f"product needs a source build, lift the toolchain into "
                f"the seed backend base builder instead."
            ),
        })
    return issues


def check_doc_symbology_drift(repo_root: Path | None = None) -> list[dict]:
    """Dense docs must obey the doc-symbology glossary contract.

    ONE deterministic drift class (the glossary §4 "inventing new symbols
    without adding them here" anti-pattern), warn-only: a symbology-class
    glyph (arrow / math-operator / glossary status-icon) NOT in the parsed
    glossary, used in a symbol-eligible doc. Arithmetic / typographic
    glyphs (`−` `×` `÷` `–` `—`) are excluded — they are prose, not
    invented symbology (the live-tree calibration lesson: a Unicode-class
    net needs a positive content anchor, not just block membership).

    `→`/`⇒` strict-interchange detection is the project's still-OPEN
    Phase-0 question Q4 and is NOT deterministic (the glossary's own §7
    reference patterns legitimately carry both glyphs on one line) — it
    is deliberately NOT implemented; the locked §3/§5 core ships and Q4
    is returned to the architect as a TEXT open question.

    Scope: the glossary §2 "Where to use" surfaces only
    (`_SYMBOLOGY_DOC_GLOBS`). Fenced code spans are excluded (glossary §3
    — code is not symbology-eligible). The symbol set is parsed live from
    `doc-symbology.md` §1; an unparseable glossary emits a single
    parse-surface warning (the §8 dependency contract), not drift noise.

    Per `feedback_doc_symbology` / `feedback_symbol_first_authoring`,
    KB § CONTEXT/PATTERNS/common/doc-symbology.md. Severity: `warning`.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    glossary_path = root / _SYMBOLOGY_GLOSSARY_DOC
    if not glossary_path.exists():
        # No glossary → nothing to enforce against. Not an error: a tree
        # without the KB simply has no symbology contract.
        return issues
    try:
        glossary_text = glossary_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("compliance: cannot read symbology glossary (%s)", exc)
        return issues
    try:
        allowed = _parse_symbology_glossary(glossary_text)
    except ValueError as exc:
        # §8 contract: surface the PARSE failure, not phantom drift.
        return [{
            "product": "<docs>",
            "file": _SYMBOLOGY_GLOSSARY_DOC,
            "issue": (
                f"doc-symbology glossary is unparseable: {exc} The "
                f"`check_doc_symbology_drift` keeper cannot enforce the "
                f"symbol-first rule until the §1 table format is restored. "
                f"Per `feedback_doc_symbology`."
            ),
            "severity": "warning",
        }]

    seen: set[Path] = set()
    for pattern in _SYMBOLOGY_DOC_GLOBS:
        for doc_path in sorted(root.glob(pattern)):
            if doc_path in seen or not doc_path.is_file():
                continue
            seen.add(doc_path)
            # Never scan the glossary against itself — it legitimately
            # lists every symbol (and counter-examples) in prose.
            try:
                if doc_path.resolve() == glossary_path.resolve():
                    continue
            except OSError:
                pass
            try:
                content = doc_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                logger.debug("compliance: cannot read %s (%s)", doc_path, exc)
                continue
            try:
                rel = str(doc_path.relative_to(root))
            except ValueError:
                rel = str(doc_path)

            lines = content.splitlines()
            code_lines = _iter_fenced_code_spans(lines)

            for line_no, line in enumerate(lines, start=1):
                if line_no in code_lines:
                    continue
                # Skip inline-code spans on the line (backtick-wrapped):
                # a glyph shown AS AN EXAMPLE in `→` is documentation of
                # the symbol, not a use of it.
                prose = re.sub(r"`[^`]*`", "", line)

                # Out-of-glossary symbology-class glyph (the LOCKED core
                # — glossary §4 "inventing new symbols" anti-pattern).
                # `→`/`⇒` strict-interchange (Q4, unlocked) deliberately
                # NOT done — see the module-level NOTE.
                offenders: set[str] = set()
                for ch in _SYMBOLOGY_GLYPH_RE.findall(prose):
                    if ch in _PROSE_PUNCTUATION:
                        continue
                    if ch not in allowed:
                        offenders.add(ch)
                for ch in prose:
                    if ch in _STATUS_EMOJI and ch not in allowed:
                        offenders.add(ch)
                if offenders:
                    glyphs = " ".join(sorted(offenders))
                    issues.append({
                        "product": "<docs>",
                        "file": rel,
                        "issue": (
                            f"`{rel}:{line_no}` uses symbology-class "
                            f"glyph(s) `{glyphs}` that are NOT in the "
                            f"doc-symbology glossary §1. \"Inventing new "
                            f"symbols without adding them here\" is a named "
                            f"anti-pattern (glossary §4) — drift kills the "
                            f"lossless contract. Add the symbol to "
                            f"`{_SYMBOLOGY_GLOSSARY_DOC}` §1 (if it earns a "
                            f"fixed meaning) or replace it with a defined "
                            f"glyph. Per `feedback_symbol_first_authoring`."
                        ),
                        "severity": "warning",
                    })

    return issues


# ---------------------------------------------------------------------------
# `check_dockerfile_vite_supabase_args` — every product backend Dockerfile
# whose frontend-build stage runs `vite build` / `npm run build` MUST declare
# the boot-critical `ARG VITE_SUPABASE_URL` + `ARG VITE_SUPABASE_PUBLISHABLE_
# KEY` (each with a matching `ENV …=${…}`) BEFORE the build runs, AND that
# product's `products/<slug>/docker-compose.yml` `build.args` block MUST
# carry both vars.
#
# Why error-severity (not warning): Vite inlines `import.meta.env.VITE_*`
# at `vite build`. If these two are absent from the build stage, the seed
# FE `createProductSupabase` / `assertSupabaseBuildEnv` hard-throws → a
# BLANK SPA on every route. Boot-critical = `error`.
#
# Surfaced by Engineer SEED-IMPL this session: the propagate scripts ship
# the ARG/ENV + compose-args pair structurally, so the live (already-
# propagated) tree is GREEN. The keeper guards FUTURE hand-edits and any
# out-of-propagation product — drift, not the current state.
#
# Predicate is prose-class (Dockerfile + compose are not Python AST):
# structural line/section grep, scoped to the frontend-build stage.
#
# Severity: `error`.
# ---------------------------------------------------------------------------


_VITE_BUILD_RE = re.compile(r"\b(?:vite\s+build|npm\s+run\s+build)\b")
_REQUIRED_VITE_ARGS: tuple[str, ...] = (
    "VITE_SUPABASE_URL",
    "VITE_SUPABASE_PUBLISHABLE_KEY",
)


def _strip_dockerfile_comments(dockerfile_text: str) -> str:
    """Blank out full-line ``#`` comments so a Dockerfile's own prose
    (e.g. a comment that contains the words "vite build" or
    "VITE_* build-arg contract") cannot be mistaken for the real
    build instruction / declarations.

    Line count is preserved (comment lines become empty) so offsets and
    `^…$` MULTILINE anchors stay aligned with the original. Trailing
    inline comments are left intact — Dockerfile instructions do not take
    `#` mid-line, so a `#` after content is a value, not a comment.
    """
    out: list[str] = []
    for line in dockerfile_text.splitlines():
        out.append("" if line.lstrip().startswith("#") else line)
    return "\n".join(out)


def _frontend_build_stage_block(dockerfile_text: str) -> str | None:
    """Return the text of the Dockerfile stage that runs the SPA build.

    A stage starts at a `FROM … [AS <name>]` line and runs until the next
    `FROM` (or EOF). We return the FIRST stage whose body contains a
    `vite build` / `npm run build` invocation — that's the frontend-build
    stage the VITE_* args must precede. `None` if no stage builds the SPA
    (e.g. a backend-only product) — nothing to enforce.

    Comment lines are blanked first (`_strip_dockerfile_comments`) so the
    Dockerfile's own prose -- e.g. a comment mentioning "vite build" --
    cannot be mistaken for the real `RUN npm run build` instruction (the
    live-tree calibration FP this guards against).
    """
    dockerfile_text = _strip_dockerfile_comments(dockerfile_text)
    lines = dockerfile_text.splitlines()
    stage_starts: list[int] = [
        i for i, ln in enumerate(lines)
        if re.match(r"^\s*FROM\s+", ln, re.IGNORECASE)
    ]
    if not stage_starts:
        return None
    bounds = list(zip(stage_starts, stage_starts[1:] + [len(lines)]))
    for start, end in bounds:
        block = "\n".join(lines[start:end])
        if _VITE_BUILD_RE.search(block):
            return block
    return None


def _compose_build_args(compose_text: str) -> set[str]:
    """Return the arg KEYS declared under any service's `build.args:`.

    Structural scan (no YAML dep — matches the prose-class predicate):
    locate a `build:` mapping, then its `args:` child, then collect the
    `KEY: …` lines indented beneath `args:` until indentation pops back.
    Robust to the two compose arg shapes (`KEY: ${KEY:-}` and `- KEY=…`).
    """
    keys: set[str] = set()
    lines = compose_text.splitlines()
    in_args = False
    args_indent = -1
    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if in_args:
            # Still inside the args block while indented deeper than `args:`.
            if indent <= args_indent:
                in_args = False
            else:
                m = re.match(r"-?\s*([A-Za-z_][A-Za-z0-9_]*)\s*[:=]", stripped)
                if m:
                    keys.add(m.group(1))
                continue
        if re.match(r"args\s*:\s*$", stripped):
            in_args = True
            args_indent = indent
    return keys


def check_dockerfile_vite_supabase_args(
    repo_root: Path | None = None,
) -> list[dict]:
    """Boot-critical VITE_SUPABASE_* must be baked into every SPA build.

    For each `products/*/backend/Dockerfile` whose frontend-build stage
    runs `vite build` / `npm run build`:

      - the stage MUST declare `ARG VITE_SUPABASE_URL` +
        `ARG VITE_SUPABASE_PUBLISHABLE_KEY` (each with a matching
        `ENV <name>=${<name>}`) BEFORE the build line; AND
      - that product's `products/<slug>/docker-compose.yml` `build.args:`
        MUST carry both keys.

    Vite inlines `import.meta.env.VITE_*` at build time; absent ⇒ the seed
    FE `assertSupabaseBuildEnv` hard-throws ⇒ a blank SPA on every route.
    Boot-critical → severity `error`. The structural fix ships via
    `scripts/propagate-{dockerfiles,composes}.sh`, so the current tree is
    clean; this guards future hand-edits / out-of-propagation products.

    Per the containerization single-container pattern
    (KB § CONTEXT/PATTERNS/devops/containerization.md). Severity: `error`.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues
    products_dir = root / "products"
    if not products_dir.exists():
        return issues

    remediation = (
        "add the ARG/ENV pair + compose args, or re-run "
        "scripts/propagate-{dockerfiles,composes}.sh"
    )

    for prod_dir in sorted(products_dir.iterdir()):
        if not prod_dir.is_dir() or prod_dir.name.startswith("."):
            continue
        slug = prod_dir.name
        dockerfile = prod_dir / "backend" / "Dockerfile"
        if not dockerfile.exists():
            continue
        try:
            df_text = dockerfile.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("compliance: cannot read %s (%s)", dockerfile, exc)
            continue

        stage = _frontend_build_stage_block(df_text)
        if stage is None:
            # No SPA build in this product's Dockerfile → not in scope.
            continue

        df_rel = f"products/{slug}/backend/Dockerfile"

        # The build line must come AFTER the ARG/ENV declarations. We
        # locate the FIRST build invocation and require each var's
        # `ARG <v>` + `ENV <v>=${<v>}` to appear before it within the
        # frontend-build stage block.
        bm = _VITE_BUILD_RE.search(stage)
        pre_build = stage[: bm.start()] if bm else stage

        for var in _REQUIRED_VITE_ARGS:
            has_arg = re.search(
                rf"^\s*ARG\s+{re.escape(var)}\b", pre_build, re.MULTILINE
            )
            has_env = re.search(
                rf"^\s*ENV\s+{re.escape(var)}\s*=\s*\$\{{{re.escape(var)}\}}",
                pre_build,
                re.MULTILINE,
            )
            if not has_arg or not has_env:
                missing = []
                if not has_arg:
                    missing.append(f"`ARG {var}`")
                if not has_env:
                    missing.append(f"`ENV {var}=${{{var}}}`")
                issues.append({
                    "product": slug,
                    "file": df_rel,
                    "issue": (
                        f"`{df_rel}` frontend-build stage runs the SPA "
                        f"build but is missing {' and '.join(missing)} "
                        f"BEFORE it. `{var}` is BOOT-CRITICAL — Vite "
                        f"inlines `import.meta.env.VITE_*` at build time; "
                        f"empty ⇒ the seed FE `assertSupabaseBuildEnv` "
                        f"hard-throws ⇒ a blank SPA on every route. "
                        f"Remediation: {remediation}."
                    ),
                    "severity": "error",
                })

        # Compose side: products/<slug>/docker-compose.yml build.args.
        compose = prod_dir / "docker-compose.yml"
        if not compose.exists():
            issues.append({
                "product": slug,
                "file": f"products/{slug}/docker-compose.yml",
                "issue": (
                    f"`products/{slug}/backend/Dockerfile` builds the SPA "
                    f"but `products/{slug}/docker-compose.yml` is missing — "
                    f"the boot-critical VITE_SUPABASE_* build args have no "
                    f"compose carrier. Remediation: {remediation}."
                ),
                "severity": "error",
            })
            continue
        try:
            comp_text = compose.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("compliance: cannot read %s (%s)", compose, exc)
            continue
        comp_args = _compose_build_args(comp_text)
        comp_rel = f"products/{slug}/docker-compose.yml"
        for var in _REQUIRED_VITE_ARGS:
            if var not in comp_args:
                issues.append({
                    "product": slug,
                    "file": comp_rel,
                    "issue": (
                        f"`{comp_rel}` `build.args:` does not carry "
                        f"`{var}`. The Dockerfile bakes it at build time "
                        f"but compose never passes it ⇒ it builds empty "
                        f"⇒ a blank SPA on every route (boot-critical). "
                        f"Remediation: {remediation}."
                    ),
                    "severity": "error",
                })

    return issues


# House single-container model markers — the canonical shape every in-noc
# product mirrors (products/seed/backend/Dockerfile + docker-compose.yml).
# See KB § PATTERNS/devops/containerization.md § 1a Container-first.
# Universal markers — required of every in-noc product Dockerfile.
_HOUSE_DOCKERFILE_MARKERS: tuple[tuple[str, str], ...] = (
    (
        "FROM noctus-seed-backend-base",
        "the shared backend base seam (`FROM noctus-seed-backend-base ... AS runtime`)",
    ),
    (
        "AS runtime-watch",
        "the `runtime-watch` develop-inside target (container-first dev: "
        "bind-mount + `vite build --watch` + `uvicorn --reload`)",
    ),
)
# SPA markers — required ONLY when the product ships a `frontend/` (a
# backend-only product has no SPA to serve, so these don't apply).
_HOUSE_SPA_MARKERS: tuple[tuple[str, str], ...] = (
    (
        "FROM noctus-seed-frontend-base",
        "the shared SPA-build base seam (`FROM noctus-seed-frontend-base`)",
    ),
    (
        "SERVE_SPA_DIR",
        "the single-container `SERVE_SPA_DIR` SPA-serve seam",
    ),
)


def check_product_container_shape(repo_root: Path | None = None) -> list[dict]:
    """Every in-noc product conforms to the house SINGLE-container model.

    Container-first (KB § PATTERNS/devops/containerization.md § 1a): a product is
    developed INSIDE its container via the `runtime-watch` target and ships
    the slim `runtime` target — ONE container, ONE shape. This detector flags
    an in-noc `products/<slug>/` missing the house shape:

      - `backend/Dockerfile` absent (not containerized to the house model —
        e.g. a freshly-absorbed product before its containerize phase); OR
      - the Dockerfile is missing a house marker: the
        `FROM noctus-seed-backend-base ... AS runtime` base seam, the
        `runtime-watch` develop-inside target, `SERVE_SPA_DIR`, or (when the
        product ships a `frontend/`) `FROM noctus-seed-frontend-base`; OR
      - `docker-compose.yml` absent, or not building `target: runtime-watch`,
        or `noctus-net` not `external`, or no profile-gated `<slug>-tunnel`.

    `seed` is the canonical source (skipped — it cannot drift). The structural
    fix is `noctus.dev.propagate` (re-renders from the seed); this guards
    hand-edits + freshly-absorbed products. Severity `warning` — drift, not a
    hard contract break, but loud in the report so a product can't silently
    ship without the house container.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    products_dir = root / "products"
    if not products_dir.exists():
        return issues

    fix = (
        "run `noctus.dev.propagate` (re-renders the house Dockerfile/compose "
        "from products/seed) or containerize the product to the house model "
        "(KB § PATTERNS/devops/containerization.md § 1a)"
    )

    for prod_dir in sorted(products_dir.iterdir()):
        if not prod_dir.is_dir() or prod_dir.name.startswith("."):
            continue
        slug = prod_dir.name
        if slug == "seed":
            continue  # the canonical source — it IS the shape
        if not (prod_dir / "backend").is_dir():
            continue  # not a backend product tree
        has_frontend = (prod_dir / "frontend").is_dir()

        # ── Dockerfile ──
        dockerfile = prod_dir / "backend" / "Dockerfile"
        df_rel = f"products/{slug}/backend/Dockerfile"
        if not dockerfile.exists():
            issues.append({
                "product": slug,
                "file": df_rel,
                "issue": (
                    f"In-noc product `{slug}` has no `{df_rel}` — it is not "
                    f"containerized to the house single-container model "
                    f"(container-first; KB § PATTERNS/devops/containerization.md § 1a). "
                    f"A freshly-absorbed product must add the thin house "
                    f"Dockerfile (`FROM noctus-seed-*-base`) before it can be "
                    f"developed inside its container. Remediation: {fix}."
                ),
                "severity": "warning",
            })
        else:
            try:
                df_text = dockerfile.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                logger.debug("compliance: cannot read %s (%s)", dockerfile, exc)
                df_text = ""
            checks = _HOUSE_DOCKERFILE_MARKERS + (
                _HOUSE_SPA_MARKERS if has_frontend else ()
            )
            for marker, desc in checks:
                if marker not in df_text:
                    issues.append({
                        "product": slug,
                        "file": df_rel,
                        "issue": (
                            f"`{df_rel}` is missing {desc}. The house "
                            f"single-container model (KB § PATTERNS/"
                            f"containerization.md § 1a) requires it. "
                            f"Remediation: {fix}."
                        ),
                        "severity": "warning",
                    })

        # ── docker-compose.yml ──
        compose = prod_dir / "docker-compose.yml"
        comp_rel = f"products/{slug}/docker-compose.yml"
        if not compose.exists():
            issues.append({
                "product": slug,
                "file": comp_rel,
                "issue": (
                    f"In-noc product `{slug}` has no `{comp_rel}` — the local "
                    f"single-container orchestration (builds `target: "
                    f"runtime-watch`) is missing. Remediation: {fix}."
                ),
                "severity": "warning",
            })
            continue
        try:
            comp_text = compose.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("compliance: cannot read %s (%s)", compose, exc)
            continue
        comp_checks: tuple[tuple[str, str], ...] = (
            (
                "target: runtime-watch",
                "build the `runtime-watch` target (the develop-inside "
                "container — container-first)",
            ),
            (
                "external: true",
                "declare `noctus-net` as `external: true` (the shared fabric "
                "from the two-project split)",
            ),
            (
                f"{slug}-tunnel",
                f"wire the mandatory profile-gated `{slug}-tunnel` service "
                "(Cloudflare quick-tunnel, run-on-demand)",
            ),
        )
        for marker, desc in comp_checks:
            if marker not in comp_text:
                issues.append({
                    "product": slug,
                    "file": comp_rel,
                    "issue": (
                        f"`{comp_rel}` does not {desc}. The house "
                        f"single-container model requires it. Remediation: {fix}."
                    ),
                    "severity": "warning",
                })

    return issues


# ---------------------------------------------------------------------------
# `check_seed_canonical_default` — seed fallback values must be the
# canonical-shared answer for the architectural model, never a per-product
# port literal that happens to work for consumer #1.
#
# Class: `(\|\||\?\?)\s*"http://localhost:\d+"` (URL form) +
# `\|\|\s*<known-backend-port>\b` (numeric port form). Both shapes silently
# misroute every consumer that isn't the one the literal was written for.
#
# N=3 evidence (2026-05-20):
#   1. `seed/framework/frontend/src/infra.tsx` `|| "http://localhost:8000"`
#      (core's port literal — every non-core product FE pointed at core →
#      CORS preflight kills the fetch → opaque `Servidor indisponivel`).
#   2. `KB § PATTERNS/backend/pydantic-strict-http.md` silent-drop sibling shape
#      (loose hook + strict default — same coincidence-pattern class).
#   3. `seed/framework/frontend/vite.config.factory.ts` `|| 8000` fallback
#      for unmapped FE ports (same root: core's backend port literal).
#
# Per `KB § PATTERNS/architect/seed-canonical-defaults.md` + memory
# `feedback_seed_defaults_canonical_not_one_consumer.md` (status flipped
# 2026-05-20 evening: `[A]` accept → `[F]` formalize).
#
# Severity: `warning` (Stage-4 codification posture — warn so legitimate-
# but-historically-flagged patterns don't tank the per-product score; tighten
# to `high` after a green baseline pass across the seed tree).
# ---------------------------------------------------------------------------


# Seed source roots — the rule scopes to seed code only (consumer-side
# product code legitimately hardcodes its own port). Mirrors the bases used
# by `_walk_python_files` but excludes products/* and mcp/* on purpose: the
# seed is the layer where a default propagates across all consumers, so
# that's the layer where consumer-#1-coincidence literals cause silent
# misroute. A product hardcoding its OWN backend port is local choice; the
# seed hardcoding ANY single product's port is the recurring bug.
_SEED_SOURCE_BASES: tuple[str, ...] = (
    "seed/lib/backend",
    "seed/lib/frontend",
    "seed/framework/backend",
    "seed/framework/frontend",
)

# File extensions we scan. Keep tight — every extension here gets an
# extension-aware comment-stripper. Anything else is excluded.
_SEED_CANONICAL_DEFAULT_EXTS: tuple[str, ...] = (".py", ".ts", ".tsx", ".js", ".jsx")

# Walk-exclusion list — vendored deps and build artifacts never get
# scanned (they hold third-party literals we don't author).
_SEED_CANONICAL_DEFAULT_EXCLUDED_PARTS: set[str] = {
    "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
    ".git", ".pytest_cache", ".mypy_cache",
}

# Pattern A — `||` or `??` followed by an http(s)://localhost URL literal.
# Catches the `infra.tsx` 2026-05-20 morning bit verbatim.
_PORT_URL_FALLBACK_RE = re.compile(
    r'(?:\|\||\?\?)\s*["\']https?://localhost:\d+["\']'
)

# Rationale escape hatch — a same-line / preceding-line comment carrying
# `canonical-default-ok` is accepted (mirrors the slug-set / mock-schema
# guardrails). For *test* harness fallbacks the seed legitimately wants
# `localhost:<port>` in (the test invokes a real server bound to that
# port and the literal IS the canonical truth at that scope).
_SEED_CANONICAL_RATIONALE_RE = re.compile(
    r"canonical-default-ok",
    re.IGNORECASE,
)


def _registered_backend_ports(root: Path) -> set[int]:
    """Set of backend ports from `start.sh PRODUCTS` registry.

    Imports `parse_products_registry` from the seed lib so the detector
    stays in sync with the live fleet (the "derive from the registry, never
    freeze a literal" rule the detector itself enforces — applied here).
    Returns an empty set if the seed-lib isn't importable from this
    process (the detector then degrades to URL-form-only, never crashes).
    """
    try:
        from noctusai_lib.config.cors_registry import parse_products_registry
    except ImportError as exc:
        logger.debug(
            "compliance: parse_products_registry unavailable (%s); "
            "check_seed_canonical_default falls back to URL-form-only scan",
            exc,
        )
        return set()
    try:
        entries = parse_products_registry(root / "start.sh")
    except (OSError, ValueError) as exc:
        logger.debug("compliance: registry parse failed (%s)", exc)
        return set()
    return {entry["backend_port"] for entry in entries}


def _strip_for_scan(text: str, ext: str) -> tuple[list[str], list[str]]:
    """Return per-line versions of `text` suitable for the two regex scans.

    Walks the file char-by-char tracking comment + string state so that
    multi-line constructs (block comments, multi-line template literals,
    Python triple-quoted strings) don't produce false matches.

    Returns ``(lines_no_comments, lines_code_only)``:

    - ``lines_no_comments``: comments (``//``, ``/* ... */``, ``#``,
      Python docstrings) are blanked out; STRING CONTENTS PRESERVED.
      Used for Pattern A (URL form — the URL literal lives inside a
      string and we want to match it).
    - ``lines_code_only``: comments AND string contents are blanked
      out. Used for Pattern B (numeric port-literal — must not match a
      `|| 8000` that appears inside a doc-comment or a string explaining
      the bug; only flag actual code).

    Line indices in the returned lists match `text.splitlines()`. Blank
    replacement preserves newlines (and column offsets within a line)
    so caller line numbering stays accurate.
    """
    no_comments: list[str] = []
    code_only: list[str] = []
    current_nc: list[str] = []
    current_co: list[str] = []
    i = 0
    in_quote: str | None = None  # `"`, `'`, ``` ` ``` for JS, `"""` / `'''` for Py
    in_block_comment = False
    in_line_comment = False
    in_py_triple: str | None = None  # `"""` or `'''`
    is_py = ext == ".py"
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        # Newline → flush + reset same-line state.
        if ch == "\n":
            no_comments.append("".join(current_nc))
            code_only.append("".join(current_co))
            current_nc = []
            current_co = []
            in_line_comment = False
            i += 1
            continue
        # Inside line comment → consume until newline.
        if in_line_comment:
            current_nc.append(" ")
            current_co.append(" ")
            i += 1
            continue
        # Inside block comment.
        if in_block_comment:
            if not is_py and ch == "*" and nxt == "/":
                in_block_comment = False
                current_nc.append("  ")
                current_co.append("  ")
                i += 2
                continue
            current_nc.append(" ")
            current_co.append(" ")
            i += 1
            continue
        # Inside Python triple-quoted string.
        if in_py_triple is not None:
            if text.startswith(in_py_triple, i):
                # End of triple.
                end = in_py_triple
                in_py_triple = None
                current_nc.append(end)
                # code_only: still blank string content, but echo close quotes.
                current_co.append(" " * len(end))
                i += len(end)
                continue
            current_nc.append(ch)
            current_co.append(" ")
            i += 1
            continue
        # Inside regular string.
        if in_quote is not None:
            current_nc.append(ch)
            # code_only: blank out string content, preserve quotes.
            if ch == in_quote:
                current_co.append(ch)
                in_quote = None
            else:
                # Handle escape sequences (don't terminate on \" or \\).
                if ch == "\\" and nxt:
                    current_nc.append(nxt)
                    current_co.append("  ")
                    i += 2
                    continue
                current_co.append(" ")
            i += 1
            continue
        # Outside everything — check for entry into comments / strings.
        if not is_py:
            if ch == "/" and nxt == "/":
                in_line_comment = True
                current_nc.append("  ")
                current_co.append("  ")
                i += 2
                continue
            if ch == "/" and nxt == "*":
                in_block_comment = True
                current_nc.append("  ")
                current_co.append("  ")
                i += 2
                continue
        else:
            if ch == "#":
                in_line_comment = True
                current_nc.append(" ")
                current_co.append(" ")
                i += 1
                continue
            # Python triple-quoted string entry.
            if text.startswith('"""', i):
                in_py_triple = '"""'
                current_nc.append('"""')
                current_co.append("   ")
                i += 3
                continue
            if text.startswith("'''", i):
                in_py_triple = "'''"
                current_nc.append("'''")
                current_co.append("   ")
                i += 3
                continue
        if ch in ('"', "'", "`"):
            in_quote = ch
            current_nc.append(ch)
            current_co.append(ch)
            i += 1
            continue
        # Plain code character.
        current_nc.append(ch)
        current_co.append(ch)
        i += 1
    # Flush the trailing line (no terminating newline).
    no_comments.append("".join(current_nc))
    code_only.append("".join(current_co))
    return no_comments, code_only


# Number of preceding lines the rationale-keyword window inspects (in
# addition to the same line). A small block comment fits within 5 lines;
# wider rationale blocks are unusual — keep the window tight so a stray
# `canonical-default-ok` keyword elsewhere in the file can't silently
# accept an unrelated literal.
_SEED_CANONICAL_RATIONALE_WINDOW: int = 5


def check_seed_canonical_default(repo_root: Path | None = None) -> list[dict]:
    """Detect consumer-#1-coincidence default literals in seed source.

    Two regression shapes, both flagged at `warning`:
      - `(\\|\\||\\?\\?)\\s*"http://localhost:<port>"` — a URL string
        literal as `||`/`??` fallback. The canonical answer for the
        single-container house model is same-origin (`""`); for other
        modules, the canonical answer is typed-error / `None` / `""` —
        anything but a literal that pretends to know.
      - `\\|\\|\\s*<backend-port>\\b` where `<backend-port>` is in the
        live `start.sh PRODUCTS` registry — a numeric port literal as
        fallback to a port-resolution chain. Same class: the literal is
        consumer-#1's port, every other consumer silently misroutes.

    Per `KB § PATTERNS/architect/seed-canonical-defaults.md` + memory
    `feedback_seed_defaults_canonical_not_one_consumer.md`. N=3 evidence
    (2026-05-20) — see module docstring above this detector for the
    enumerated cases.

    Rationale escape hatch: a `canonical-default-ok` token in a comment
    on the same line or the preceding line accepts the literal (mirrors
    the slug-set / mock-schema guardrails). Use for test harnesses that
    legitimately bind to a known port and where the literal IS the
    canonical truth at test scope.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    backend_ports = _registered_backend_ports(root)
    # Numeric pattern is built dynamically from the live registry so the
    # detector follows the fleet (the same "derive from registry" rule it
    # enforces).  Skip the numeric pattern entirely when the registry is
    # unreadable rather than freeze an arbitrary port set.
    if backend_ports:
        # Sort high→low so longer-prefix ports match before any shorter
        # ones (no real overlap with 4-5 digit ports, but the explicit
        # ordering documents the intent).
        ports_alt = "|".join(str(p) for p in sorted(backend_ports, reverse=True))
        port_fallback_re: re.Pattern[str] | None = re.compile(
            rf'\|\|\s*(?:{ports_alt})\b'
        )
    else:
        port_fallback_re = None

    for base_rel in _SEED_SOURCE_BASES:
        base = root / base_rel
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in _SEED_CANONICAL_DEFAULT_EXTS:
                continue
            if any(p in _SEED_CANONICAL_DEFAULT_EXCLUDED_PARTS for p in path.parts):
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                logger.debug("compliance: cannot read %s (%s)", path, exc)
                continue
            try:
                relative = str(path.relative_to(root))
            except ValueError:
                logger.debug("compliance: file outside repo root: %s", path)
                continue
            lines = content.splitlines()
            lines_no_comments, lines_code_only = _strip_for_scan(
                content, path.suffix,
            )
            for idx, raw_line in enumerate(lines, start=1):
                nc_line = lines_no_comments[idx - 1] if idx - 1 < len(lines_no_comments) else ""
                code_line = lines_code_only[idx - 1] if idx - 1 < len(lines_code_only) else ""
                if not nc_line.strip():
                    continue
                # Rationale escape hatch — search the raw line + a small
                # window of preceding raw lines for the opt-out keyword.
                # Searching raw lines (not stripped) lets the keyword sit
                # inside a comment, which is its natural carrier.
                window_start = max(0, idx - 1 - _SEED_CANONICAL_RATIONALE_WINDOW)
                window = lines[window_start:idx]  # incl. current line (idx-1)
                if any(_SEED_CANONICAL_RATIONALE_RE.search(ln) for ln in window):
                    continue
                # Pattern A — URL form. Scans the comment-stripped line
                # (string contents preserved) so the URL inside a string
                # literal still matches but a `/* ... */` doc-comment
                # mentioning the URL does not.
                if _PORT_URL_FALLBACK_RE.search(nc_line):
                    issues.append({
                        "product": "<seed>",
                        "file": relative,
                        "issue": (
                            f"`{relative}:{idx}` uses a `localhost:<port>` "
                            f"URL literal as `||`/`??` fallback. The seed "
                            f"default MUST be the canonical-shared answer "
                            f"for the architectural model (same-origin "
                            f"`\"\"` for the single-container house model; "
                            f"typed-error / `None` / `\"\"` when no "
                            f"canonical answer is known at seed-level), "
                            f"never a literal that pretends to know one "
                            f"consumer's port. Per "
                            f"`KB § PATTERNS/architect/seed-canonical-defaults.md`. "
                            f"Escape hatch: add `canonical-default-ok` to "
                            f"a same-line or preceding-line comment."
                        ),
                        "severity": "warning",
                    })
                # Pattern B — numeric port-literal fallback (registry-derived).
                # Scans the code-only line (comments + string contents
                # stripped) so a `|| 8000` mentioned inside a doc comment
                # or a throw-message string explaining the bug does not
                # re-trigger the detector.
                if port_fallback_re is not None and port_fallback_re.search(code_line):
                    issues.append({
                        "product": "<seed>",
                        "file": relative,
                        "issue": (
                            f"`{relative}:{idx}` uses a registered backend "
                            f"port number as `||` fallback. The literal is "
                            f"a per-product port from `start.sh PRODUCTS` "
                            f"— silently misroutes any consumer whose port "
                            f"isn't that one. Right shape: derive from "
                            f"`parse_products_registry()` and `throw` on "
                            f"unmapped (loud build failure), never `|| "
                            f"<port-literal>` (silent misroute at runtime). "
                            f"Per `KB § PATTERNS/architect/seed-canonical-defaults.md`. "
                            f"Escape hatch: add `canonical-default-ok` to "
                            f"a same-line or preceding-line comment."
                        ),
                        "severity": "warning",
                    })

    return issues


# ---------------------------------------------------------------------------
# `check_derives_from_dev_only_artifact` — seed code that DERIVES a runtime
# value from a dev-only artifact (the `start.sh PRODUCTS` registry / a
# `scripts/` file) WITHOUT an env fallback in the same function body silently
# serves the dev answer in prod (the slim deploy image ships NO `start.sh` ->
# the derivation collapses to empty / a localhost default).
#
# This is the executable form of `KB section PATTERNS/devops/dev-prod-parity.md` 2 (the
# dev<->prod difference checklist) — the same class bit >=3x in the
# 2026-05-22 cutover (nav SSO'd to localhost, CORS collapsed to localhost in the
# slim image, `infra.tsx` localhost default). The cure shape lives one file over
# in `cors_registry.derive_cors_origins`: it derives from the registry AND reads
# `os.environ` (the env fallback) so the slim container still resolves prod
# origins. A derivation lacking that env read is the recurring root.
#
# PROACTIVE keeper (N=1, user-directed). The user asked to "eternalize possible
# conflicts as features products consume from seed code" — this
# anticipatory detector is that contract made enforceable: a derivation from a
# dev-only artifact MUST pair with an env seam, so a product cannot silently
# ship the dev value to prod. Filed by `projects/seed-deploy-config-contract`.
#
# Severity: `warning` (proactive posture — warn so a legitimate edge
# case can waive via `dev-artifact-derivation-ok` rather than tank the score).
# ---------------------------------------------------------------------------


# Tokens that, when present in a function body, mean it DERIVES a runtime
# value from a dev-only artifact. `parse_products_registry(` is the registry
# consumer; `start.sh` / `scripts/` are the raw-artifact reads. Matched on the
# code-only (string + comment stripped) body so a docstring mentioning
# `start.sh` doesn't trigger.
_DEV_ARTIFACT_DERIVATION_TOKENS: tuple[str, ...] = (
    "parse_products_registry(",
    "start.sh",
    "scripts/",
)

# Tokens that count as an env fallback in the SAME function body. Their
# presence means the derivation has the prod-safe seam (the
# `derive_cors_origins` shape) and is NOT flagged.
_DEV_ARTIFACT_ENV_FALLBACK_TOKENS: tuple[str, ...] = (
    "os.environ",
    "os.getenv",
    "getenv(",
    "environ[",
    "environ.get",
    "resolve_config(",
)

# Escape-hatch keyword: a `dev-artifact-derivation-ok` token on the function
# line or in the preceding window waives (mirrors `canonical-default-ok`).
_DEV_ARTIFACT_RATIONALE_RE = re.compile(r"dev-artifact-derivation-ok", re.IGNORECASE)


def check_derives_from_dev_only_artifact(repo_root: Path | None = None) -> list[dict]:
    """Flag seed functions that derive a runtime value from a dev-only artifact.

    PROACTIVE keeper (N=1, user-directed -- `projects/seed-deploy-config-contract`).
    The executable form of `KB section PATTERNS/devops/dev-prod-parity.md` 2: seed code
    in `seed/{lib,framework}/**/*.py` that derives a value from the dev-only
    `start.sh PRODUCTS` registry (``parse_products_registry(``) or a
    ``scripts/``/``start.sh`` file -- WITHOUT any env fallback (``os.environ`` /
    ``os.getenv`` / ``getenv`` / ``resolve_config``) in the SAME function body --
    silently serves the dev answer in production (the slim deploy image ships no
    ``start.sh`` so the derivation collapses to empty / a localhost default).
    That gap was the recurring root of the 2026-05-22 cutover failures.

    The correct shape -- derive from the registry AND read ``os.environ`` so the
    container still resolves prod values -- lives in
    :func:`noctusai_lib.config.cors_registry.derive_cors_origins`. This detector
    MUST NOT flag it (it reads ``os.environ``); a passing ``derive_cors_origins``
    is the key correctness signal.

    Comment/string-aware: the body is scanned on its code-only projection (via
    the shared :func:`_strip_for_scan` helper) so a docstring or string literal
    mentioning ``start.sh`` does not trigger.

    Severity: ``warning``. Escape hatch: a ``dev-artifact-derivation-ok`` token
    in a comment on the ``def`` line or the 5 preceding lines waives.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    # Scope: seed lib + framework Python only (the layer where a derivation
    # propagates across all product consumers).
    seed_bases = ("seed/lib", "seed/framework")
    for base_rel in seed_bases:
        base = root / base_rel
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if not path.is_file():
                continue
            if any(p in _SEED_CANONICAL_DEFAULT_EXCLUDED_PARTS for p in path.parts):
                continue
            # Skip seed test code -- a test legitimately calls
            # `parse_products_registry` to exercise the parser; it is not
            # prod-path derivation, so it is out of scope for this keeper.
            if "tests" in path.parts:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                logger.debug("compliance: cannot read %s (%s)", path, exc)
                continue
            try:
                tree = ast.parse(content, filename=str(path))
            except SyntaxError as exc:
                logger.debug("compliance: cannot parse %s (%s)", path, exc)
                continue
            try:
                relative = str(path.relative_to(root))
            except ValueError:
                logger.debug("compliance: file outside repo root: %s", path)
                continue

            raw_lines = content.splitlines()
            # Code-only projection (comments + string contents blanked) so a
            # docstring / string mentioning `start.sh` doesn't false-trigger.
            _nc_lines, code_only_lines = _strip_for_scan(content, ".py")

            # Walk every function/method def (top-level + nested + methods).
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                start = node.lineno  # 1-based, the `def` line
                end = getattr(node, "end_lineno", None) or start
                # Code-only body slice (excludes the `def` line itself, which
                # carries no derivation logic -- just the signature).
                body_code = "\n".join(code_only_lines[start:end])

                derives = any(
                    tok in body_code for tok in _DEV_ARTIFACT_DERIVATION_TOKENS
                )
                if not derives:
                    continue
                has_env_fallback = any(
                    tok in body_code for tok in _DEV_ARTIFACT_ENV_FALLBACK_TOKENS
                )
                if has_env_fallback:
                    continue
                # Escape hatch -- scan the `def` line + 5 preceding raw lines
                # (the natural carrier for a waiving comment / decorator note).
                window_start = max(0, start - 1 - _SEED_CANONICAL_RATIONALE_WINDOW)
                window = raw_lines[window_start:start]  # incl. the `def` line
                if any(_DEV_ARTIFACT_RATIONALE_RE.search(ln) for ln in window):
                    continue

                issues.append({
                    "product": "<seed>",
                    "file": relative,
                    "issue": (
                        f"`{relative}:{start}` function `{node.name}` derives a "
                        f"runtime value from a dev-only artifact "
                        f"(`parse_products_registry` / `start.sh` / `scripts/`) "
                        f"with NO env fallback (`os.environ` / `os.getenv` / "
                        f"`getenv` / `resolve_config`) in the same body. The "
                        f"slim deploy image ships no `start.sh`, so this "
                        f"silently serves the dev value in production -- the "
                        f"2026-05-22 cutover root. Right shape: pair the "
                        f"derivation with an env seam (see "
                        f"`noctusai_lib.config.cors_registry.derive_cors_origins`, "
                        f"which derives from the registry AND reads `os.environ`). "
                        f"Per `KB section PATTERNS/devops/dev-prod-parity.md` 2. Escape "
                        f"hatch: add `dev-artifact-derivation-ok` to a comment "
                        f"on the `def` line or the 5 preceding lines."
                    ),
                    "severity": "warning",
                })

    return issues


# ---------------------------------------------------------------------------
# `check_query_fn_returns_undefined` — TanStack Query v5 contract: a
# `queryFn` MUST NOT return `undefined`. v5 surfaces "data is undefined"
# as the consumer's error — exactly the toast a 404-swallow path is
# usually trying to suppress.
#
# Class (B3 in `KB § PATTERNS/backend/boundary-contract-tests.md`): a third-party
# library contract that crosses the seed/product → React Query Provider
# boundary. Unit tests typically mock `useQuery({ data })` and miss the
# real-Provider + real-queryFn + 404-response path.
#
# N=1 evidence (2026-05-20): `seed/lib/frontend/src/design-system/ai/
# useLLMSpend.ts` returned `undefined` on 404 → `<LLMSpendBadge/>`-mounted
# layout toasted `["admin","llm-spend","<org>"] data is undefined` on
# every dashboard render. Sibling `useConsents` was already correct —
# returned `EMPTY_CATALOG` sentinel. Audit across all 297 `queryFn:`
# sites in seed+products at ship time: zero remaining instances. Keeper
# locks in the baseline.
#
# Per `KB § PATTERNS/backend/boundary-contract-tests.md` § 5 +
# `feedback_query_fn_never_returns_undefined.md`.
#
# Severity: `warning` (zero-baseline already proven; promote to `high`
# at the next platform-compliance gate refresh).
# ---------------------------------------------------------------------------


# Scope: every FE source tree. TanStack v5 may be consumed by any layer
# that imports `@tanstack/react-query`, so the predicate runs over all
# frontends rather than only seed (B3 isn't a seed-only class — any
# product hook that swallows a 404 by `return undefined` reproduces the
# bug).
_QUERY_FN_FE_BASE_PARENTS: tuple[str, ...] = (
    "seed/lib/frontend",
    "seed/framework/frontend",
)
_QUERY_FN_FE_EXTS: tuple[str, ...] = (".ts", ".tsx")
_QUERY_FN_EXCLUDED_PARTS: set[str] = {
    "node_modules", "dist", "build", ".git", ".turbo", "coverage",
}

# Opener of an arrow function body assigned to `queryFn:`. The body must
# be a brace block — expression-body forms like `queryFn: () => api.get(...)`
# can't `return undefined` literally and are out of scope.
_QUERY_FN_BODY_RE = re.compile(
    r"queryFn\s*:\s*(?:async\s+)?(?:\([^)]*\)|[a-zA-Z_$][\w$]*)\s*=>\s*\{"
)
# Inside the body: literal `return undefined` (with word boundaries so
# `return undefinedFoo` doesn't false-flag).
_RETURN_UNDEFINED_RE = re.compile(r"\breturn\s+undefined\b")
# Bare `return;` — also `undefined` per JS semantics. Anchored to line
# start (after leading whitespace) so a `return;` in a string or a
# nested `if (x) return;` on its own line is caught; but `if (x)
# return;` on a single line shared with the `if` is fine to flag too —
# the rule is conservative.
_BARE_RETURN_RE = re.compile(r"^\s*return\s*;\s*$")
# Escape hatch — `query-fn-undefined-ok` token in a same-line or 5-line
# preceding comment accepts the literal. Use only when the v5 contract
# has been read and a defensible reason exists.
_QUERY_FN_RATIONALE_RE = re.compile(r"query-fn-undefined-ok", re.IGNORECASE)
_QUERY_FN_RATIONALE_WINDOW: int = 5


def _query_fn_product_fe_bases(root: Path) -> list[str]:
    """Enumerate every `products/<slug>/frontend` base on disk.

    Walks the products dir directly rather than parsing the registry
    because every product on disk gets scanned (even pre-registration);
    the goal is "every FE source tree", not "every registered product."
    """
    products_dir = root / "products"
    if not products_dir.is_dir():
        return []
    bases: list[str] = []
    for child in sorted(products_dir.iterdir()):
        if not child.is_dir():
            continue
        if not (child / "frontend").is_dir():
            continue
        bases.append(f"products/{child.name}/frontend")
    return bases


def _find_query_fn_body_ranges(code_only_text: str) -> list[tuple[int, int]]:
    """Return ``(start_line, end_line)`` pairs for every queryFn arrow body.

    Both line indices are 1-indexed. ``start_line`` is the line of the
    `queryFn:` token; ``end_line`` is the line of the matching ``}``.
    Brace walking happens over the comment/string-stripped text so
    string-or-comment braces don't throw off the depth count.
    """
    ranges: list[tuple[int, int]] = []
    for match in _QUERY_FN_BODY_RE.finditer(code_only_text):
        body_open = match.end() - 1  # position of the opening `{`
        depth = 0
        body_close: int | None = None
        for i in range(body_open, len(code_only_text)):
            ch = code_only_text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    body_close = i
                    break
        if body_close is None:
            # Unterminated body (malformed or scan window too small) —
            # don't crash, just skip. The compiler will catch the syntax
            # error elsewhere.
            continue
        start_line = code_only_text.count("\n", 0, match.start()) + 1
        end_line = code_only_text.count("\n", 0, body_close) + 1
        ranges.append((start_line, end_line))
    return ranges


def check_query_fn_returns_undefined(repo_root: Path | None = None) -> list[dict]:
    """Detect TanStack Query v5 `queryFn` bodies that return `undefined`.

    Two patterns flagged inside each `queryFn: (...) => { ... }` arrow
    body:
      - `return undefined;` (literal — what `useLLMSpend` had before the
        2026-05-20 fix).
      - Bare `return;` (also `undefined` per JS semantics, same v5
        contract violation).

    The right shape for a "no data" path is `return null` or a sentinel
    object (e.g. `EMPTY_CATALOG`) — never `undefined`. v5 treats an
    `undefined` `queryFn` return as a developer error and surfaces
    "data is undefined" to the consumer, exactly the toast the
    404-swallow / topology-degrade path is usually trying to prevent.

    Per `KB § PATTERNS/backend/boundary-contract-tests.md` § 5 (B3 — third-party
    library contract) + memory
    `feedback_query_fn_never_returns_undefined.md`.

    Escape hatch: `query-fn-undefined-ok` on the same line or any of the
    5 preceding lines accepts the literal. Use rarely — usually the
    right answer is `return null` + `useQuery<T | null, Error>`.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    bases: list[str] = list(_QUERY_FN_FE_BASE_PARENTS) + _query_fn_product_fe_bases(root)

    for base_rel in bases:
        base = root / base_rel
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in _QUERY_FN_FE_EXTS:
                continue
            if any(p in _QUERY_FN_EXCLUDED_PARTS for p in path.parts):
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                logger.debug("compliance: cannot read %s (%s)", path, exc)
                continue
            if "queryFn" not in content:
                # Cheap pre-filter — most FE files don't touch TanStack.
                continue
            try:
                relative = str(path.relative_to(root))
            except ValueError:
                logger.debug("compliance: file outside repo root: %s", path)
                continue
            lines = content.splitlines()
            # `_strip_for_scan` returns parallel line lists with comments
            # and strings/template-literals blanked. We reconstruct a
            # code-only text (joining lines_code_only with newlines) so
            # the brace walk is reliable across multi-line bodies.
            _lines_nc, lines_code_only = _strip_for_scan(content, path.suffix)
            code_only_text = "\n".join(lines_code_only)
            ranges = _find_query_fn_body_ranges(code_only_text)
            if not ranges:
                continue
            for start_line, end_line in ranges:
                for idx in range(start_line, end_line + 1):
                    if idx - 1 >= len(lines_code_only):
                        break
                    code_line = lines_code_only[idx - 1]
                    if not code_line.strip():
                        continue
                    matched: str | None = None
                    if _RETURN_UNDEFINED_RE.search(code_line):
                        matched = "literal `return undefined`"
                    elif _BARE_RETURN_RE.search(code_line):
                        matched = "bare `return;` (implicit undefined)"
                    if matched is None:
                        continue
                    # Rationale escape hatch — search raw lines (not
                    # stripped) so the keyword can sit in a comment.
                    window_start = max(0, idx - 1 - _QUERY_FN_RATIONALE_WINDOW)
                    window = lines[window_start:idx]
                    if any(_QUERY_FN_RATIONALE_RE.search(ln) for ln in window):
                        continue
                    issues.append({
                        "product": "<seed>" if base_rel.startswith("seed/") else base_rel.split("/")[1],
                        "file": relative,
                        "issue": (
                            f"`{relative}:{idx}` queryFn body has "
                            f"{matched}. TanStack Query v5 surfaces an "
                            f"`undefined` queryFn return as `data is "
                            f"undefined` to the consumer (the toast a "
                            f"404-swallow path usually wants to "
                            f"prevent). Return `null` (and type the "
                            f"query `<T | null, Error>`) or a sentinel "
                            f"object instead. Per "
                            f"`KB § PATTERNS/backend/boundary-contract-tests.md` "
                            f"§ 5. Escape hatch: add "
                            f"`query-fn-undefined-ok` to a same-line or "
                            f"preceding-line comment."
                        ),
                        "severity": "warning",
                    })

    return issues


# ---------------------------------------------------------------------------
# `check_playwright_supabase_env` — the E2E-harness sibling of
# `check_dockerfile_vite_supabase_args`. Every product's frontend Playwright
# config whose `webServer` boots the real SPA MUST inject the boot-critical
# VITE_SUPABASE_* into `webServer.env`, or the seed supabase client
# (`@noctusai/lib` design-system) THROWS at module load → the React tree
# never mounts → every E2E spec fails "element(s) not found".
#
# The trap is a local<->CI parity gap: locally a dev's `.env` feeds the
# webServer so E2E is green; CI has no `.env`, so absent injection collapses
# the whole suite silently. Bit BOTH core + erp (N=2 → formalize). It is the
# same boot-critical-env contract as the Dockerfile keeper (B1 build-
# injection), at the E2E test-harness boundary (boundary-contract-tests B6).
#
# Predicate is prose-class (playwright.config.ts is TS but parsed
# structurally here, not via the TS AST tool — mirrors the Dockerfile keeper).
# Comments are blanked first so a config that only NAMES the var in a comment
# does not false-pass. Severity: `error` (a missing pair zeroes the product's
# entire E2E signal).
# ---------------------------------------------------------------------------


def check_playwright_supabase_env(repo_root: Path | None = None) -> list[dict]:
    """Boot-critical VITE_SUPABASE_* must be injected into the E2E webServer.

    For each `products/<slug>/frontend/playwright.config.ts` that defines a
    `webServer` (it boots the real SPA via `npm run dev`), the
    `webServer.env` block MUST set `VITE_SUPABASE_URL` +
    `VITE_SUPABASE_PUBLISHABLE_KEY`. The seed supabase client throws at
    module load when these build-time vars are absent ⇒ the React tree never
    mounts ⇒ every spec fails "element(s) not found".

    The slip is a local<->CI parity gap: locally a dev `.env` feeds the
    webServer (E2E green); CI has no `.env`, so absent injection collapses the
    suite. Bit BOTH core + erp (N=2 → formalize). The E2E-harness sibling of
    `check_dockerfile_vite_supabase_args` (the prod-build instance of the same
    contract); boundary-contract-tests B6.

    Products with no Playwright config (backend-only, e.g.
    knowledge-extractor) are out of scope. Severity: `error`.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues
    products_dir = root / "products"
    if not products_dir.exists():
        return issues

    remediation = (
        "add both keys to the `webServer.env` block (non-secret placeholders "
        "are correct — E2E mocks the backend; see "
        "products/core/frontend/playwright.config.ts)"
    )

    for prod_dir in sorted(products_dir.iterdir()):
        if not prod_dir.is_dir() or prod_dir.name.startswith("."):
            continue
        slug = prod_dir.name
        cfg = prod_dir / "frontend" / "playwright.config.ts"
        if not cfg.exists():
            # No E2E harness (backend-only product) → out of scope.
            continue
        try:
            raw = cfg.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("compliance: cannot read %s (%s)", cfg, exc)
            continue

        # Blank comments (string contents preserved) so a config that only
        # MENTIONS the var in a comment doesn't pass; the actual `env` keys
        # are code identifiers and survive the strip.
        no_comments, _ = _strip_for_scan(raw, ".ts")
        scrubbed = "\n".join(no_comments)

        # Only configs that boot the SPA via a `webServer` are in scope; a
        # config with no webServer never loads the supabase client.
        if "webServer" not in scrubbed:
            continue

        cfg_rel = f"products/{slug}/frontend/playwright.config.ts"
        for var in _REQUIRED_VITE_ARGS:
            if re.search(rf"\b{re.escape(var)}\b", scrubbed):
                continue
            issues.append({
                "product": slug,
                "file": cfg_rel,
                "issue": (
                    f"`{cfg_rel}` boots the SPA via `webServer` but does not "
                    f"inject `{var}` into `webServer.env`. It is BOOT-CRITICAL "
                    f"— the seed supabase client throws at module load when "
                    f"absent ⇒ the React tree never mounts ⇒ every E2E spec "
                    f"fails 'element(s) not found'. Passes locally (dev `.env` "
                    f"feeds the webServer) but collapses the suite in CI. "
                    f"Remediation: {remediation}."
                ),
                "severity": "error",
            })

    return issues


# ---------------------------------------------------------------------------
# `check_auth_session_mutation_on_shared_client` — a session-establishing
# supabase-py auth call (verify_otp / sign_in_* / set_session /
# refresh_session / exchange_code_for_session) run on the SHARED service-role
# client (`supabase_admin` / `get_admin_client()`) poisons the singleton's
# PostgREST token PROCESS-WIDE (service_role → authenticated until restart) →
# silent RLS breakage on unrelated requests. The 2026-05-23 core prod login
# outage. PROACTIVE (N=1) — the prod blast radius justifies a standing guard.
# This is PREVENTION, not the fix (the fix was a throwaway anon client).
# AST-based; reuses `_admin_client_bindings`. Severity `error`.
# ---------------------------------------------------------------------------

_SESSION_AUTH_METHODS = frozenset({
    "verify_otp", "sign_in_with_password", "sign_in_with_otp",
    "sign_in_with_oauth", "sign_in_with_sso", "sign_up",
    "set_session", "refresh_session", "exchange_code_for_session",
})
_SHARED_ADMIN_NAMES = frozenset({"supabase_admin"})


def _is_shared_admin_receiver(node: ast.expr, admin_bindings: set[str]) -> bool:
    """True if `node` is the shared service-role client: the module-level
    `supabase_admin` singleton, a var bound to `get_admin_client()`, or a
    direct `get_admin_client()` call (chained)."""
    if isinstance(node, ast.Name):
        return node.id in _SHARED_ADMIN_NAMES or node.id in admin_bindings
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id == "get_admin_client"
    return False


def check_auth_session_mutation_on_shared_client(product_path: Path) -> list[dict]:
    """Flag session-establishing supabase-py auth calls on a SHARED client.

    `verify_otp` / `sign_in_*` / `set_session` / `refresh_session` /
    `exchange_code_for_session` ESTABLISH a session — supabase-py then
    propagates the new user token onto the calling client's PostgREST auth
    layer. Run on the shared service-role singleton (`supabase_admin` /
    `get_admin_client()`), that downgrades EVERY later admin call from
    service_role to authenticated PROCESS-WIDE until restart → silent RLS
    breakage on unrelated requests (the 2026-05-23 core prod login outage:
    GET /api/auth/me 42P17). Fix: run session-establishing auth on a
    THROWAWAY `create_client(url, anon_key)`, never the shared singleton.

    N=2 (core sso.py verify_otp + social-wiring auth.py sign_in_with_password —
    both fixed 2026-05-23, the latter via a throwaway anon client). The blast
    radius (process-wide prod auth) justifies the guard. Prevention, not the fix.

    Severity `error` (baseline 0 since 2026-05-23 — both findings cleared;
    deploying social-wiring's fix to prod is the separate gated step).
    """
    issues: list[dict] = []
    name = product_path.name
    backend = product_path / "backend"
    if not backend.exists():
        return issues
    for py in sorted(backend.rglob("*.py")):
        norm = str(py).replace("\\", "/")
        if "/tests/" in norm or "/node_modules/" in norm or "/__pycache__/" in norm:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            logger.debug("compliance: cannot parse %s (%s)", py, exc)
            continue
        admin_bindings = _admin_client_bindings(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in _SESSION_AUTH_METHODS):
                continue
            auth_attr = node.func.value
            if not (isinstance(auth_attr, ast.Attribute) and auth_attr.attr == "auth"):
                continue
            if not _is_shared_admin_receiver(auth_attr.value, admin_bindings):
                continue
            try:
                rel = str(py.relative_to(product_path))
            except ValueError:
                rel = str(py)
            issues.append({
                "product": name,
                "file": rel,
                "line": node.lineno,
                "issue": (
                    f"{rel}:{node.lineno} `.auth.{node.func.attr}(...)` runs on "
                    f"the SHARED service-role client (supabase_admin / "
                    f"get_admin_client()). Session-establishing auth poisons the "
                    f"singleton's PostgREST token PROCESS-WIDE → service_role "
                    f"downgraded to authenticated → silent RLS breakage (core "
                    f"prod login outage 2026-05-23). Use a throwaway "
                    f"create_client(url, anon_key) — see `KB § PATTERNS/backend/backend.md` "
                    f"(admin-client poisoning)."
                ),
                "severity": "error",
            })
    return issues


# ---------------------------------------------------------------------------
# `check_limiter_conftest_import` — every product whose backend ships
# `app/rate_limit.py` (a slowapi `limiter`) MUST import the seed autouse
# fixture `reset_rate_limiter` in its `tests/conftest.py`. Without it, the
# slowapi in-memory limiter (used when Redis is down, e.g. in CI) leaks
# bucket state across tests → a rate-limit test exhausts a bucket and a
# later test on that endpoint gets a 429 under pytest-randomly ordering
# (latent order-dependent flake). The fixture (in
# `noctusai_lib.testing.fixtures`, exported via `noctusai_lib.testing`)
# clears the limiter between tests; merely importing it into the conftest
# namespace activates it (autouse). N=6 byte-identical per-product fixtures
# pre-existed → lifted to the seed → DRY recurrence ⇒ MUST formalize.
# Per KB § PATTERNS/common/methodology-codification-pipeline.md (Stage-4).
# ---------------------------------------------------------------------------


def check_limiter_conftest_import(repo_root: Path | None = None) -> list[dict]:
    """Flag products with `app/rate_limit.py` whose `tests/conftest.py`
    does NOT reference the seed `reset_rate_limiter` autouse fixture.

    Predicate (per product under ``products/``):
      - SKIP unless ``backend/app/rate_limit.py`` exists (no limiter ⇒
        the leak class cannot occur).
      - WARN if ``backend/tests/conftest.py`` is missing OR its text does
        not contain the token ``reset_rate_limiter``.

    The expected line (mirroring core/daily-life/therapy/personal-finance)::

        from noctusai_lib.testing.fixtures import reset_rate_limiter  # noqa: F401

    String containment is sufficient and robust: the only way the token
    appears in a conftest is the import (it is not a common identifier),
    and importing the name is exactly what activates the autouse fixture.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    products_dir = root / "products"
    if not products_dir.exists():
        return issues

    for product_path in sorted(products_dir.iterdir()):
        if not product_path.is_dir() or product_path.name.startswith("."):
            continue
        name = product_path.name
        rate_limit_py = product_path / "backend" / "app" / "rate_limit.py"
        if not rate_limit_py.exists():
            continue  # no limiter ⇒ the cross-test leak class can't occur

        conftest = product_path / "backend" / "tests" / "conftest.py"
        has_import = False
        if conftest.exists():
            try:
                has_import = "reset_rate_limiter" in conftest.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                logger.debug("compliance: cannot read %s (%s)", conftest, exc)
                # Cannot prove it's present → treat as missing (no silent pass).
                has_import = False

        if not has_import:
            issues.append({
                "product": name,
                "file": "backend/tests/conftest.py",
                "issue": (
                    "Has app/rate_limit.py (slowapi limiter) but tests/conftest.py "
                    "does not import the seed autouse fixture `reset_rate_limiter`. "
                    "The in-memory slowapi limiter (used when Redis is down, e.g. CI) "
                    "leaks bucket state across tests → order-dependent 429 flake under "
                    "pytest-randomly. Add "
                    "`from noctusai_lib.testing.fixtures import reset_rate_limiter  # noqa: F401` "
                    "near the other noctusai_lib.testing imports. Per "
                    "KB § PATTERNS/common/methodology-codification-pipeline.md."
                ),
                "severity": "warning",
            })

    return issues


# ---------------------------------------------------------------------------
# `check_product_icon_registered` — every product ships a REAL icon.
# A product's `icone` (core `public.products`) must render as an actual icon,
# never as the bare text of an icon name. `ProductIcon`
# (core/frontend/src/lib/product-icon.tsx) renders a value that is a key in its
# `ICONS` registry as an SVG, and any other ASCII value as raw TEXT — so a
# lucide name NOT in the registry shows up literally (the "Sprout" bug,
# 2026-05-25). Emoji values (non-ASCII) render verbatim and are allowed.
# This keeper folds the core product-catalog migrations into the final live
# catalog and flags any product whose icone is EMPTY or an unregistered ASCII
# name. See KB § PATTERNS/compliance/testing.md § Regression-test-the-detector and
# CLAUDE/frontend.md (product icons).
# ---------------------------------------------------------------------------


def _product_icon_registry(repo_root: Path) -> set[str]:
    """Parse the frontend `ICONS` registry → the set of registered icon names.

    Source of truth: ``products/core/frontend/src/lib/product-icon.tsx``. The
    registry is the allowlist of values that render as an actual SVG icon. An
    empty set (file missing / unparseable) disables the check (degrade, never
    crash) — logged so the gap is not silent.
    """
    f = repo_root / "products" / "core" / "frontend" / "src" / "lib" / "product-icon.tsx"
    try:
        content = f.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("compliance: cannot read ProductIcon registry %s (%s)", f, exc)
        return set()
    m = re.search(r"const\s+ICONS\b[^=]*=\s*\{(.*?)\n\}", content, re.DOTALL)
    if not m:
        logger.warning("compliance: cannot locate ICONS object in %s", f)
        return set()
    return set(re.findall(r"^\s*([A-Za-z][A-Za-z0-9]*)\s*[:,]", m.group(1), re.MULTILINE))


def _migration_number(name: str) -> int:
    try:
        return int(name.split("_", 1)[0])
    except (ValueError, IndexError):
        return 0


def _fold_product_catalog(migrations_dir: Path) -> dict[str, tuple[str, str, int]]:
    """Fold the core product-catalog migrations → ``{slug: (icone, file, line)}``.

    Applies INSERT/UPDATE (set icone) and DELETE (remove slug) in migration
    order (number, then in-file position), last-write-wins. Mirrors how the
    live ``public.products`` table is built from the immutable migration chain,
    so retired products (deleted by a later forward migration) and
    delete-then-re-add (`seed` → 036 delete, 038 re-add) resolve correctly.

    Parsing is anchor-based — no statement/paren/semicolon parsing (product
    `descricao` text contains both ``;`` and ``()``):
      * icone — the quoted token immediately preceding the row's
        ``'http(s)://...'`` url_base (only product rows carry a url_base).
      * slug  — the nearest preceding kebab-case quoted token (the only
        all-lowercase quoted value in a product row).
    """
    ops: list[tuple[tuple[int, int], str, str, str | None, str, int]] = []
    if not migrations_dir.is_dir():
        return {}
    for sql in sorted(migrations_dir.glob("*.sql")):
        num = _migration_number(sql.name)
        try:
            content = sql.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        slug_matches = list(re.finditer(r"'([a-z0-9]+(?:-[a-z0-9]+)*)'", content))
        # INSERT rows — pair icone (url_base anchor) with its row's slug.
        for im in re.finditer(r"'([^']*)'\s*,\s*'https?://", content):
            slug = None
            for sm in slug_matches:
                if sm.start() < im.start():
                    slug = sm.group(1)
                else:
                    break
            if slug:
                lineno = content.count("\n", 0, im.start()) + 1
                ops.append(((num, im.start()), "set", slug, im.group(1), sql.name, lineno))
        # UPDATE ... SET icone = '...' WHERE slug = '...'
        for um in re.finditer(
            r"SET\s+icone\s*=\s*'([^']*)'.*?slug\s*=\s*'([a-z0-9-]+)'",
            content, re.IGNORECASE | re.DOTALL,
        ):
            lineno = content.count("\n", 0, um.start()) + 1
            ops.append(((num, um.start()), "set", um.group(2), um.group(1), sql.name, lineno))
        # DELETE FROM products WHERE slug IN (...) | slug = '...'
        for dm in re.finditer(
            r"DELETE\s+FROM\s+(?:public\.)?products\s+WHERE\s+slug\s+IN\s*\(([^)]*)\)",
            content, re.IGNORECASE | re.DOTALL,
        ):
            for s in re.findall(r"'([a-z0-9-]+)'", dm.group(1)):
                ops.append(((num, dm.start()), "del", s, None, sql.name, 0))
        for dm in re.finditer(
            r"DELETE\s+FROM\s+(?:public\.)?products\s+WHERE\s+slug\s*=\s*'([a-z0-9-]+)'",
            content, re.IGNORECASE,
        ):
            ops.append(((num, dm.start()), "del", dm.group(1), None, sql.name, 0))

    ops.sort(key=lambda o: o[0])
    catalog: dict[str, tuple[str, str, int]] = {}
    for _, kind, slug, icone, fn, lineno in ops:
        if kind == "set":
            catalog[slug] = (icone or "", fn, lineno)
        else:
            catalog.pop(slug, None)
    return catalog


def check_product_icon_registered(repo_root: Path | None = None) -> list[dict]:
    """Flag a product whose `icone` is empty or not a renderable icon.

    Every product MUST ship a real icon — a value `ProductIcon` renders as an
    SVG (a name in its `ICONS` registry) or an emoji (non-ASCII, rendered
    verbatim). An empty icone, or an ASCII name absent from the registry,
    renders as bare TEXT on the dashboard / admin panel (the "Sprout" bug). The
    remediation is loud: add the lucide name to `ICONS` in
    `core/frontend/src/lib/product-icon.tsx`, or seed a registered name.
    """
    base = repo_root if repo_root is not None else REPO_ROOT
    registry = _product_icon_registry(base)
    if not registry:
        return []  # registry unreadable — degrade (already logged)

    catalog = _fold_product_catalog(base / "products" / "core" / "backend" / "migrations")
    issues: list[dict] = []
    for slug, (icone, fn, lineno) in sorted(catalog.items()):
        rel = f"backend/migrations/{fn}"
        if icone == "":
            issues.append({
                "product": "core",
                "file": rel,
                "issue": (
                    f"Product '{slug}' is seeded with an EMPTY icone (line {lineno}). "
                    "Every product must ship a real icon — a registered ProductIcon "
                    "name (see core/frontend/src/lib/product-icon.tsx ICONS) or an "
                    "emoji. An empty icone renders as nothing on the dashboard."
                ),
                "severity": "high",
            })
        elif any(ord(c) > 127 for c in icone):
            continue  # emoji — renders verbatim, allowed
        elif icone not in registry:
            issues.append({
                "product": "core",
                "file": rel,
                "issue": (
                    f"Product '{slug}' icone '{icone}' (line {lineno}) is not a "
                    "registered ProductIcon — it renders as raw TEXT, not an icon "
                    "(the 'Sprout' bug, 2026-05-25). Add '" + icone + "' to ICONS in "
                    "core/frontend/src/lib/product-icon.tsx (import it from "
                    "lucide-react), or seed a name already in the registry."
                ),
                "severity": "high",
            })
    return issues


# ---------------------------------------------------------------------------
# `check_detector_has_regression_test` — every keeper detector ships with a
# colocated regression test. Enforces the platform-wide testing methodology
# documented in KB § PATTERNS/compliance/testing.md § Regression-test-the-detector.
# ---------------------------------------------------------------------------


# Detector → test entry-point map. The detector is satisfied when EITHER:
#   - a `Test<CamelCase>` class exists in any `mcp/noctusai/tests/test_*.py`
#     file with a name derived from the detector (e.g. `check_silent_errors`
#     → `TestCheckSilentErrors` or `TestSilentErrors`), OR
#   - the detector is explicitly mapped here to a test file/symbol that
#     covers it (used when the natural-name heuristic doesn't hold).
#
# Adding a new detector? Add the regression test first; the test class name
# should match the detector. If the test must live somewhere else, add an
# explicit entry here so the rule stays enforced.
_DETECTOR_TEST_OVERRIDES: dict[str, str] = {
    # `check_path_references` is exercised by the underlying `find_refs`
    # tests (which the detector composes) — explicit override keeps the
    # detector classified as covered.
    "check_path_references": "tests/test_refs.py::TestFindRefs",
    "check_frontend_entrypoint": "tests/test_phase5_detectors.py",
    "check_out_of_contract_trees": "tests/test_phase5_detectors.py",
    "check_config_extends_product_settings": "tests/test_config_inheritance.py",
    "check_frontend_config_paths": "tests/test_frontend_config_paths.py",
    "check_seed_version_propagation": "tests/test_seed_version_propagation.py",
    # 2026-05-28 (7→8-way promotion): three new per-cache freshness
    # keepers extracted from cli.py inline checks. Covered by the
    # `TestAllCacheFreshness::test_composes_eight_legs` composition test.
    "check_kb_embeddings_cache_freshness": "tests/test_eight_way_sync.py::TestAllCacheFreshness",
    "check_corpus_embeddings_cache_freshness": "tests/test_eight_way_sync.py::TestAllCacheFreshness",
    "check_memory_embeddings_cache_freshness": "tests/test_eight_way_sync.py::TestAllCacheFreshness",
    "check_all_cache_freshness": "tests/test_eight_way_sync.py::TestAllCacheFreshness",
    "check_eight_way_sync": "tests/test_eight_way_sync.py::TestEightWaySync",
    # extractor-correctness keeper: full regression in test_graph_extractor_correctness.py;
    # the keeper itself is a light floor-check subset of that suite.
    "check_graph_extractor_corpus_sanity": "tests/test_graph_extractor_correctness.py::TestEdgeFloors",
    # dangling-remote-branches (2026-05-30, branch-hygiene-prevention).
    "check_dangling_remote_branches": "tests/test_dangling_remote_branches.py",
}


def _detector_function_names() -> list[str]:
    """Parse this module and return every top-level `check_*` function name.

    `check_all_products` is the dispatcher and is excluded.
    """
    here = Path(__file__).resolve()
    try:
        tree = ast.parse(here.read_text(encoding="utf-8"), filename=str(here))
    except (OSError, SyntaxError) as exc:
        logger.warning(
            "compliance: cannot self-parse %s (%s); skipping detector audit",
            here, exc,
        )
        return []
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name.startswith("check_")
        and node.name != "check_all_products"
    ]


def _camel_case(snake: str) -> str:
    return "".join(part.capitalize() for part in snake.split("_"))


def _detector_has_regression_test(detector: str, tests_dir: Path) -> bool:
    """True if a `Test<CamelCase>` class for the detector exists somewhere
    under `tests_dir`, OR an explicit override maps the detector to a test
    target.

    Class-name matching is case-insensitive on the snake_case parts so
    acronyms like `TestAIFeatureCompleteness` (matching detector
    `check_ai_feature_completeness`) are recognized without an override.
    Both `TestCheck<...>` and `Test<...>` shapes are accepted.
    """
    if detector in _DETECTOR_TEST_OVERRIDES:
        target = _DETECTOR_TEST_OVERRIDES[detector]
        # Format: "tests/<file>.py" or "tests/<file>.py::<symbol>"
        rel_file = target.split("::", 1)[0]
        return (tests_dir.parent / rel_file).exists()

    if not tests_dir.exists():
        return False

    # Build a case-insensitive regex matching `class Test<Body>` where
    # <Body> is the joined snake_case parts (with or without leading
    # `Check`). E.g. `check_ai_feature_completeness` matches both
    # `TestCheckAIFeatureCompleteness` and `TestAIFeatureCompleteness`,
    # case-insensitively.
    body_full = detector.replace("_", "")
    body_short = detector.removeprefix("check_").replace("_", "")
    pattern = re.compile(
        rf"class\s+Test(?:{body_full}|{body_short})\b",
        re.IGNORECASE,
    )

    for test_file in tests_dir.glob("test_*.py"):
        try:
            content = test_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("compliance: cannot read %s (%s)", test_file, exc)
            continue
        if pattern.search(content):
            return True
    return False


def check_detector_has_regression_test(repo_root: Path | None = None) -> list[dict]:
    """Every `check_*` keeper detector must ship with a regression test.

    The test pins the detector's true-positive and false-positive shapes so
    that a future refactor cannot silently regress it. Per KB §
    PATTERNS/compliance/testing.md § Regression-test-the-detector. Severity `high` —
    a missing detector test is the kind of gap that lets a real-world miss
    ship without being noticed.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    tests_dir = root / "mcp" / "noctusai" / "tests"

    for detector in _detector_function_names():
        if detector == "check_detector_has_regression_test":
            # Self-coverage is checked at import-time by the test file; if
            # the test doesn't import the detector, the test fails. No need
            # to flag here.
            continue
        if _detector_has_regression_test(detector, tests_dir):
            continue
        # Build hint targets so the message is actionable.
        expected = "Test" + _camel_case(detector.removeprefix("check_"))
        issues.append({
            "product": "<mcp>",
            "file": "mcp/noctusai/tools/compliance.py",
            "issue": (
                f"Keeper detector `{detector}` has no regression test. "
                f"Per KB § PATTERNS/compliance/testing.md § Regression-test-the-detector, "
                f"every detector must ship colocated with a test that pins "
                f"its true-positive and false-positive shapes. Add a "
                f"`class {expected}` (or `Test{_camel_case(detector)}`) to "
                f"`mcp/noctusai/tests/test_compliance.py` (or a dedicated "
                f"`mcp/noctusai/tests/test_<detector>.py`). If the test "
                f"covers the detector under a non-matching name, add an "
                f"override entry to `_DETECTOR_TEST_OVERRIDES` in "
                f"`mcp/noctusai/tools/compliance.py`."
            ),
            "severity": "high",
        })
    return issues


# ---------------------------------------------------------------------------


class ValidateInput(BaseModel):
    """No inputs — `validate` runs across every product unconditionally."""


class ValidateIssue(BaseModel):
    product: str | None = None
    severity: str
    issue: str
    detector: str | None = None


class ValidateOutput(BaseModel):
    score: int = Field(description="Platform-wide score 0-100. Average across products.")
    issues: list[ValidateIssue] = Field(default_factory=list)


def check_section_7_placeholder_consistency(repo_root: Path | None = None) -> list[dict]:
    """Detect PROJECT.md files where §7 says "all answered" but §2 still
    carries the unfilled `_Interrogate ..._` template placeholder.

    The bug shape this catches: a child PROJECT.md is scaffolded from
    `templates/PROJECT-TEMPLATE.md` and §7 gets filled with the template's
    default `See §2 — all answered at interrogation time.` line BEFORE
    §2 is actually filled. §7 then misleads future agents into thinking
    the §7 questions were answered, when in fact §2 is still empty.

    Surfaced 2026-05-03 by `projects/side-projects-batch/` Phase 0 audit:
    three Tier-1 children carried this exact mismatch (N=3 → triage; N≥4
    → MUST formalize). This detector formalizes the check.

    The fired rule:
      - §7 contains "See §2 — all answered" or "answered at interrogation time"
      - AND §2 still contains "_Interrogate the user before filling"
        (or similar template-default placeholder pattern)
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    answered_marker_re = re.compile(
        r"answered at interrogation time|See \xa7?2\s*[—-]\s*all answered",
        re.IGNORECASE,
    )
    placeholder_re = re.compile(
        r"_Interrogate the user before filling|"
        r"_TBD after interrogation_|"
        r"_\(filled at Phase 0 interrogation\)_",
        re.IGNORECASE,
    )
    section_2_re = re.compile(
        r"^## 2\..*?(?=^## 3\.)",
        re.MULTILINE | re.DOTALL,
    )
    section_7_re = re.compile(
        r"^## 7\..*?(?=^## 8\.)",
        re.MULTILINE | re.DOTALL,
    )

    for project_md in _find_all_project_md(root):
        try:
            content = project_md.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.warning(
                "compliance: cannot read PROJECT.md %s (%s), skipping",
                project_md, exc,
            )
            continue

        s2 = section_2_re.search(content)
        s7 = section_7_re.search(content)
        if not s2 or not s7:
            continue

        s7_says_answered = bool(answered_marker_re.search(s7.group(0)))
        s2_still_placeholder = bool(placeholder_re.search(s2.group(0)))

        if s7_says_answered and s2_still_placeholder:
            try:
                relative = str(project_md.relative_to(root))
            except ValueError:
                relative = str(project_md)
            product_label = "<projects>"
            if relative.startswith("products/"):
                product_label = relative.split("/", 2)[1]
            elif relative.startswith("core/"):
                product_label = "core"
            issues.append({
                "product": product_label,
                "file": relative,
                "issue": (
                    f"`{relative}` §7 claims questions are 'answered at "
                    f"interrogation time' but §2 still carries the "
                    f"`_Interrogate the user before filling_` template "
                    f"placeholder. Either fill §2 with the actual answers "
                    f"or restore §7 to the unanswered shape (list the "
                    f"questions explicitly with recommendations). "
                    f"Misleading template-fill artifact — future agents "
                    f"will read §7 as resolved when it isn't."
                ),
                "severity": "high",
            })
    return issues


# ── products-consume-canonical-organs (2026-05-29, Phase 2.1) ─────────────────
# Products MUST consume canonical cached organs from `@noctusai/lib/...` —
# no local re-implementations. Named-seam extensions allowed when the consumer
# file carries `// @consumes-organ <Name>@<ver> +seam=<kind>`.
# KB § PATTERNS/architect/products-consume-canonical-organs.md.
#
# Canonical organ set: Phase 1 seed pilot — LoginForm, ForgotPasswordPage,
# AcceptInvitePage, ResourceManager, DigestCard. Any organ.yaml sidecar with
# `validation_status: validated|emerging|canonical` is in scope.
_CANONICAL_ORGANS: dict[str, str] = {
    "LoginForm": "seed/lib/frontend/src/components/auth/LoginForm",
    "ForgotPasswordPage": "seed/lib/frontend/src/pages/auth/ForgotPasswordPage",
    "AcceptInvitePage": "seed/lib/frontend/src/pages/auth/AcceptInvitePage",
    "ResourceManager": "seed/lib/frontend/src/components/resource/ResourceManager",
    "DigestCard": "seed/lib/frontend/src/components/digest/DigestCard",
}

# Declaration header that exempts a local wrapper.
_CONSUMES_ORGAN_RE = re.compile(
    r"//\s*@consumes-organ\s+\S+@\S+\s+\+seam=\S+"
)


def _load_organ_registry(repo_root: Path) -> dict[str, str]:
    """Return the canonical organ name → seed path registry.

    Starts from the hard-coded Phase 1 set and EXTENDS with any
    `*.organ.yaml` sidecar found under `seed/lib/frontend/src/` that
    carries `validation_status: validated`, `emerging`, or `canonical`.

    Returns a copy of `_CANONICAL_ORGANS` augmented with sidecar entries.
    Never raises — missing sidecar dir is treated as empty extension.
    """
    registry: dict[str, str] = dict(_CANONICAL_ORGANS)
    seed_fe = repo_root / "seed" / "lib" / "frontend" / "src"
    if not seed_fe.exists():
        return registry
    # Minimal YAML parse: look for `name:` and `validation_status:` lines.
    # Simple line-scan (not PyYAML) — organ.yaml files are small; fields of
    # interest are always on their own lines without nesting.
    _ACTIVE_STATUSES = {"validated", "emerging", "canonical"}
    for yaml_file in seed_fe.rglob("*.organ.yaml"):
        try:
            lines = yaml_file.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("compliance: cannot read organ.yaml %s (%s)", yaml_file, exc)
            continue
        name_val: str | None = None
        status_val: str | None = None
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("name:"):
                name_val = stripped.split(":", 1)[1].strip().strip("'\"")
            elif stripped.startswith("validation_status:"):
                status_val = stripped.split(":", 1)[1].strip().strip("'\"")
        if name_val and status_val and status_val in _ACTIVE_STATUSES:
            if name_val not in registry:
                try:
                    parent = str(yaml_file.parent.relative_to(repo_root))
                except ValueError:
                    parent = str(yaml_file.parent)
                registry[name_val] = parent
    return registry


def check_canonical_organ_consumption(
    repo_root: Path | None = None,
) -> list[dict]:
    """Products MUST consume canonical cached organs, not re-implement them.

    Scans `products/*/frontend/src/**/*.{tsx,ts}` for declarations of canonical
    organ names. A local `function LoginForm` / `const LoginForm =` / `export
    function LoginForm` is a BLOCKING violation unless the file carries a
    `// @consumes-organ <Name>@<ver> +seam=<kind>` declaration header (which
    marks it as an approved named-seam extension).

    Severity: `high` — a silent re-fork undoes the Phase 1 canonical gain and
    splits bug-fix responsibility (canonical fixes don't reach the fork).

    Known limitation: same-shape renames (e.g., `AuthForm` that's structurally
    `LoginForm`) are not caught by name-only matching. Surface via
    `scoped-improvement:` when found manually.

    Stage-4 codification: `products-consume-canonical-organs` (2026-05-29).
    KB § PATTERNS/architect/products-consume-canonical-organs.md.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    products_dir = root / "products"
    if not products_dir.exists():
        return issues

    registry = _load_organ_registry(root)

    for product_path in sorted(products_dir.iterdir()):
        if not product_path.is_dir() or product_path.name.startswith("."):
            continue
        fe_src = product_path / "frontend" / "src"
        if not fe_src.exists():
            continue
        name = product_path.name

        for ext in ("*.tsx", "*.ts"):
            for src_file in fe_src.rglob(ext):
                try:
                    content = src_file.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as exc:
                    logger.debug(
                        "compliance: cannot read %s (%s)", src_file, exc
                    )
                    continue

                # Check each canonical organ name.
                for organ_name, seed_path in registry.items():
                    # Match: function/const declaration (not import).
                    decl_pattern = (
                        r"(?:export\s+)?(?:function|const)\s+"
                        + re.escape(organ_name)
                        + r"\s*[=(]"
                    )
                    match = re.search(decl_pattern, content)
                    if not match:
                        continue

                    # Local declaration found — check for exemption header.
                    if _CONSUMES_ORGAN_RE.search(content):
                        continue  # declared named-seam extension — ALLOWED

                    try:
                        rel = str(src_file.relative_to(root))
                    except ValueError:
                        rel = str(src_file)

                    line_no = content[: match.start()].count("\n") + 1

                    issues.append({
                        "product": name,
                        "file": rel,
                        "issue": (
                            f"line {line_no}: local declaration of canonical organ "
                            f"`{organ_name}` — import from `@noctusai/lib` "
                            f"(canonical: `{seed_path}`) instead, or add "
                            f"`// @consumes-organ {organ_name}@<ver> +seam=<kind>` "
                            "if this is an intentional named-seam extension. "
                            "KB § PATTERNS/architect/products-consume-canonical-organs.md"
                        ),
                        "severity": "high",
                    })

    return issues


def check_all_products() -> tuple[int, list]:
    """Run all compliance checks on all products. Returns (score, issues)."""
    all_issues = []
    scores = []

    for d in sorted(PRODUCTS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        issues = (
            check_seed_compliance(d)
            + check_path_references(d)
            + check_standard_routers_audit(d)
            + check_frontend_entrypoint(d)
            + check_handrolled_core_url(d)
            # product-internal-wiring static legs (Stage-4) — reuse the shared
            # scan_wiring predicates (one predicate, two surfaces — DRY).
            + check_fe_route_missing(d)
            + check_name_on_nome_select(d)
            + check_promise_all_shared_catch(d)
            + check_config_extends_product_settings(d)
            + check_frontend_config_paths(d)
            + check_mock_schema_validation(d)
            + check_ai_feature_completeness(d)
            + check_test_status_assertion(d)
            + check_unknown_table_references(d)
            + check_function_search_path_pinned(d)
            + check_rls_policy_self_reference(d)
            + check_admin_endpoint_service_role_bypass(d)
            + check_auth_session_mutation_on_shared_client(d)
            + check_slowapi_with_pep563(d)
        )
        all_issues.extend(issues)
        penalties = {"critical": 25, "high": 10, "warning": 3}
        penalty = sum(penalties.get(i["severity"], 5) for i in issues)
        scores.append(max(0, 100 - penalty))

    # Global (non-per-product) checks.
    all_issues.extend(check_out_of_contract_trees())
    all_issues.extend(check_seed_version_propagation())
    all_issues.extend(check_phase_state_consistency())
    # dispatch-with-PROJECT-and-notes (2026-05-26) — every PROJECT.md with §6
    # phases carries §4a Dispatch routing (slice→lens · codification s1-s4 ·
    # routes-not-taken · notes). Grandfathered for pre-birthday projects.
    # KB § PATTERNS/common/dispatch-with-project-and-notes.md.
    all_issues.extend(check_project_has_dispatch_routing())
    all_issues.extend(check_no_self_monkeypatch())
    all_issues.extend(check_silent_errors())
    all_issues.extend(check_clean_folder_violations())
    all_issues.extend(check_section_7_placeholder_consistency())
    # Hygiene-compliance globals — `keeper-housekeeping-upgrade` Phase 1.
    all_issues.extend(check_archive_staleness())
    # methodology doc-ref integrity gate (2026-05-25) — KB § shorthand +
    # literal KNOWLEDGE-BASE/...md + .claude/agents + KB→KB cross-refs;
    # placeholders excluded; wikilinks advisory-only.
    all_issues.extend(check_methodology_doc_refs())
    # deferred-codification visibility — the always-on gate form of /codify;
    # reads NOC-REMEDIATE[codify] markers so a deferred codification can't go
    # silent in prose (KB § PATTERNS/common/methodology-codification-pipeline.md).
    all_issues.extend(check_codification_debt())
    all_issues.extend(check_dispatcher_staleness())
    all_issues.extend(check_branch_orphan())
    all_issues.extend(check_gitignore_drift())
    # Stage-4 codification batch — `keeper-stage4-codification-batch` Phase 1.
    all_issues.extend(check_no_silent_ok_comment())
    all_issues.extend(check_auth_dep_anti_pattern())
    all_issues.extend(check_mcp_path_via_settings())
    all_issues.extend(check_mcp_write_tool_worktree_arg())
    all_issues.extend(check_pipefail_grep_q())
    all_issues.extend(check_new_script_lacks_mcp_analog())
    all_issues.extend(check_doc_tool_reference_drift())
    # social-wiring-absorption W5.7a / W5.9a Stage-4 codification.
    all_issues.extend(check_seed_export_membership())
    all_issues.extend(check_hardcoded_product_slug_set())
    # social-wiring-absorption W5.9-rest — numeric-axis twin of the
    # slug-set keeper (frozen fleet-size literals stale on consolidation).
    all_issues.extend(check_hardcoded_fleet_size_literal())
    # symbol-first-stage-4-codification — Stage-3⇒4 codification of the
    # doc-symbology / symbol-first authoring methodology (warn-only).
    all_issues.extend(check_doc_symbology_drift())
    # claude-md-router-discipline (2026-05-25) — CLAUDE.md is the always-on
    # router: §1 rules stay one-line (rule + `→` pointer), no inlined bodies,
    # whole file under the word budget. Stage-4 of the v4.0 router refactor.
    all_issues.extend(check_claude_md_router())
    # memory-md-index-discipline (2026-05-25) — sibling: MEMORY.md auto-loaded
    # index discipline. OUT-OF-REPO (Claude Code per-project store) → gates at
    # validate + --check-memory-md-index CLI only, NOT at git commit.
    all_issues.extend(check_memory_md_index())
    # harness-layer format keepers (2026-05-25, harness-agents-skills) — gate
    # authoring discipline on .claude/skills + .claude/agents so new surfaces
    # conform by construction (sibling of check_claude_md_router/check_memory_md_index).
    all_issues.extend(check_skill_format())
    all_issues.extend(check_agent_format())
    all_issues.extend(check_agent_archetype_contract())
    # agent-context-architecture (2026-05-26) — agent files declare full-domain
    # owns_kb in frontmatter; keeper enforces existence + body-pointer mirror +
    # exclusive ownership. KB § PATTERNS/common/agent-context-architecture.md.
    all_issues.extend(check_agent_kb_alignment())
    # drift-fix-on-contact (2026-05-26) — recurring git-leftovers drift class
    # (untracked-at-root + worktree-uncommitted) caught at every gate.
    # KB § PATTERNS/common/drift-fix-on-contact.md.
    all_issues.extend(check_git_leftovers())
    # 2026-05-26 — the keeper-pattern cache MUST mirror compliance.py. A stale
    # cache → doc-authoring agents author drift-prone docs from outdated
    # patterns. KB § PATTERNS/common/keeper-pattern-cache.md.
    all_issues.extend(check_keeper_cache_freshness())
    # 2026-05-26 (Phase B) — sibling cache for agents. Each agent's bundle_sha
    # = sha256(agent.md ∪ owned_kb files) must match the cached value.
    # KB § PATTERNS/common/agent-context-architecture.md § Keeper enforcement.
    all_issues.extend(check_agent_context_cache_freshness())
    # 2026-05-26 (Phase B) — third sibling: scoped-auto-improvement cache
    # mirrors project-history/auto-improvement.ndjson. Consult-before-editing
    # discipline. KB § PATTERNS/common/scoped-auto-improvement.md.
    all_issues.extend(check_auto_improvement_cache_freshness())
    # 2026-05-26 (Phase B) — CONTEXTUALIZE.md = fresh-agent read map; sibling
    # of check_claude_md_router (same pointer-only discipline, applied to the
    # onboarding ramp). KB § PATTERNS/common/claude-md-router-discipline.md.
    all_issues.extend(check_contextualize_alignment())
    # 2026-05-26 (seven-way-sync) — skills declared in CLAUDE.md §2 must
    # match the on-disk .claude/skills/ tree. Sub-keeper composed by
    # check_eight_way_sync. KB § PATTERNS/common/eight-way-sync.md.
    all_issues.extend(check_skills_listed_in_router())
    # 2026-05-26 (seven-way-sync evening) — sister of skills check,
    # applied to .claude/commands/.
    all_issues.extend(check_commands_listed_in_router())
    # 2026-05-28 (7→8-way promotion) — composition keeper validating the
    # 8-surface sync invariant. Most legs reuse existing sub-keepers
    # (kb_sync, contextualize, agent_kb_alignment, skills_listed,
    # commands_listed, memory_md_index, all_cache_freshness).
    # KB § PATTERNS/common/eight-way-sync.md.
    all_issues.extend(check_eight_way_sync())
    # 2026-05-26 (kb-vector-search) — enforces the markdown-canonical /
    # vector-DB-is-enrichment principle. Severity warning (advisory layer,
    # never blocking). KB § PATTERNS/common/kb-vector-search.md.
    all_issues.extend(check_kb_vector_canonical())
    # 2026-05-26 (W2-E3' code-embeddings) — fifth keeper-mirror cache; sibling
    # of kb-embeddings. Code source ↔ cache freshness; orphan-row + per-file
    # source_sha. Severity warning (advisory discovery layer). KB § CONTEXT/
    # PATTERNS/common/code-embeddings.md.
    all_issues.extend(check_code_embeddings_cache_freshness())
    # 2026-05-27 (noc-graph 8th-keeper-mirror) — structured graph mirror
    # (`.claude/cache/noc-graph.sqlite`) that powers fresh-agent contextualization
    # via `/contextualize` + `noctus.graph.*`. Aggregate source_sha gates the
    # full rebuild. Severity warning (advisory: orientation map degrades, not
    # blocks). KB § PATTERNS/architect/noc-graph.md.
    all_issues.extend(check_noc_graph_cache_freshness())
    # 2026-05-30 (cache-locking discipline) — every cache connection must route
    # through cache_backend.apply_locking_pragmas (WAL + busy_timeout); a raw
    # inline `PRAGMA journal_mode=WAL` re-opens the writer-contention gap fixed
    # this session. Severity high (zero violations post-centralization).
    # KB § PATTERNS/common/cache-locking-discipline.md.
    all_issues.extend(check_cache_uses_locking_helper())
    # 2026-05-28 (extractor-correctness-vs-mirror) — light corpus floor-checks
    # on the noc-graph cache content (not just freshness). Catches the case where
    # an extractor stops emitting a node/edge kind, producing a fresh-but-wrong
    # cache. Paired with test_graph_extractor_correctness.py (full regression).
    # KB § PATTERNS/common/extractor-correctness-vs-mirror.md.
    all_issues.extend(check_graph_extractor_corpus_sanity())
    # 2026-05-26 (W2-E6 kb-baseline) — ratified-canonical layer over the
    # owns_kb vector signal. Surfaces when current findings diverge from
    # the latest ratified baseline by > threshold. Severity warning
    # (advisory; ratification is human-reasoning, not auto-tuning).
    # KB § CONTEXT/PATTERNS/common/vector-baseline.md.
    all_issues.extend(check_kb_semantic_drift())
    # 2026-05-26 (post-close batch — code-baseline) — sister of kb-baseline
    # applied to code recurrence findings. Surfaces new pairs since the
    # latest ratification. Severity warning.
    # KB § CONTEXT/PATTERNS/common/code-recurrence-baseline.md.
    all_issues.extend(check_code_recurrence_drift())
    # containerization single-container — boot-critical VITE_SUPABASE_*
    # build-arg contract (error: empty ⇒ blank SPA on every route).
    all_issues.extend(check_dockerfile_vite_supabase_args())
    # boundary-contract-tests B6 (2026-05-23) — E2E-harness sibling of the
    # Dockerfile keeper above: a product's playwright.config.ts webServer must
    # inject VITE_SUPABASE_* or the seed supabase client throws at module load
    # ⇒ every E2E spec fails. local<->CI parity gap; bit core + erp (N=2).
    all_issues.extend(check_playwright_supabase_env())
    # container-first codification (2026-05-23) — every in-noc product
    # conforms to the house single-container model (FROM noctus-seed-*-base,
    # runtime-watch develop-inside target, serve_spa; compose target +
    # external net + tunnel). Flags a freshly-absorbed-but-uncontainerized
    # product (the knowledge-extractor pilot) + hand-edit drift (warning).
    all_issues.extend(check_product_container_shape())
    # containerization §3.2a — a product pulling a source-only (no
    # arm64-wheel) dep needs a per-slug PIP_RUN toolchain seam, else the
    # fleet build aborts in the slim runtime (2026-05-18 fix-on-contact).
    all_issues.extend(check_product_source_build_dep_pip_seam())
    # seed-canonical-defaults Stage-4 — N=3 (2026-05-20). Flags
    # consumer-#1-coincidence port literals as `||`/`??` fallbacks in
    # seed source (URL form + numeric-port-from-registry form).
    all_issues.extend(check_seed_canonical_default())
    # seed-deploy-config-contract (2026-05-23) — PROACTIVE (N=1,
    # user-directed). Flags seed code that derives a runtime value from a
    # dev-only artifact (`parse_products_registry` / `start.sh` / `scripts/`)
    # WITHOUT an env fallback in the same function body — the dev<->prod
    # silent-fallback class that bit >=3x in the 2026-05-22 cutover.
    all_issues.extend(check_derives_from_dev_only_artifact())
    # boundary-contract-tests B3 (2026-05-20) — TanStack Query v5
    # contract: a `queryFn` body MUST NOT return `undefined`. Catches
    # the `useLLMSpend` shape on the next instance (the toast was the
    # only signal because no unit test exercises the real Provider +
    # real queryFn + real 404 response).
    all_issues.extend(check_query_fn_returns_undefined())
    # fleet-limiter-conftest-adoption Stage-4 (2026-05-23) — products with
    # app/rate_limit.py must import the seed `reset_rate_limiter` autouse
    # fixture into tests/conftest.py, else the in-memory slowapi limiter
    # leaks bucket state across tests → order-dependent 429 flake (N=6).
    all_issues.extend(check_limiter_conftest_import())
    # product-icon-registry coupling (2026-05-25) — every product ships a REAL
    # icon: an `icone` that ProductIcon renders as an SVG (registered name) or
    # an emoji, never a bare lucide name that shows as text (the "Sprout" bug).
    all_issues.extend(check_product_icon_registered())
    # products-consume-canonical-organs (2026-05-29, Phase 2.1) — hard rule:
    # organ-shaped FE components must import from @noctusai/lib/..., not re-
    # implement locally. Named-seam extensions allowed when declared.
    # KB § PATTERNS/architect/products-consume-canonical-organs.md.
    all_issues.extend(check_canonical_organ_consumption())
    all_issues.extend(check_detector_has_regression_test())
    # auth-boundary-false-green (2026-05-29, canonical-test-runner) — static
    # AST scan for `status_code in (401, 404)` disjunctions in product test
    # files. The 404 branch is a false-green escape hatch (route absent ⇒ 404
    # ⇒ test passes, auth never exercised). Only static analysis catches this.
    # KB § PATTERNS/compliance/auth-boundary-false-green.md.
    all_issues.extend(check_auth_boundary_false_green())
    # dangling-remote-branches (2026-05-30, branch-hygiene-prevention) — advisory
    # keeper; flags origin/* branches with unique content older than threshold_days.
    # Squash-aware (subject-on-dev + git-cherry); never a commit-blocker.
    # KB § CONTEXT/PATTERNS/common/learn-before-archive.md.
    all_issues.extend(check_dangling_remote_branches())

    platform_score = round(sum(scores) / len(scores)) if scores else 100
    return platform_score, all_issues


# ── CLAUDE.md router-discipline (claude-md-router-discipline, Stage-4 2026-05-25) ──
# CLAUDE.md is the always-on auto-loaded router; its budget compounds across every
# reply. The contract: §1 carries PRINCIPLE + the MAP; PROCEDURE/bodies live in
# `.claude/skills/` + the `KB § …` pointers. Re-bloating it back toward the verbose
# v3.0 form is gated. Depth: `KB § PATTERNS/common/claude-md-router-discipline.md`.
_CLAUDE_MD_MAX_WORDS = 2500           # whole-file budget (synthesis is ~1.4k; cap blocks re-bloat)
_CLAUDE_MD_MAX_RULE_WORDS = 60        # a §1 bullet beyond this is an inlined body
_CLAUDE_MD_SECTION1_RE = re.compile(r"^##\s+1\s*[·.]")   # "## 1 · Universal rules"
_CLAUDE_MD_NEXT_SECTION_RE = re.compile(r"^##\s+\d")      # the next "## N …" header


def check_claude_md_router(repo_root: Path | None = None) -> list[dict]:
    """CLAUDE.md is the always-on router — keep it pointer-only.

    Gates three deterministic invariants of the harness-agents-skills pattern:
      1. whole-file word budget (<= _CLAUDE_MD_MAX_WORDS),
      2. every §1 rule bullet is ONE line, carries a `→` pointer, and is
         <= _CLAUDE_MD_MAX_RULE_WORDS words,
      3. §1 contains NO prose body lines (only `- ` rule bullets + the section
         header + blanks / `---` / `>`); an inlined body is the re-bloat tell.

    Stage-4 codification of the v4.0 router refactor (2026-05-25).
    Depth: `KB § PATTERNS/common/claude-md-router-discipline.md`.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    claude_md = root / "CLAUDE.md"
    if not claude_md.exists():
        return issues
    try:
        text = claude_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("compliance: cannot read CLAUDE.md (%s)", exc)
        return issues

    total_words = len(text.split())
    if total_words > _CLAUDE_MD_MAX_WORDS:
        issues.append({
            "product": "<docs>",
            "file": "CLAUDE.md",
            "issue": (
                f"CLAUDE.md is {total_words} words (cap {_CLAUDE_MD_MAX_WORDS}) — the "
                "always-on router must stay pointer-only; move bodies to a skill / the "
                "KB pointer (KB § PATTERNS/common/claude-md-router-discipline.md)."
            ),
            "severity": "high",
        })

    in_section1 = False
    for line_no, raw in enumerate(text.splitlines(), start=1):
        if _CLAUDE_MD_SECTION1_RE.match(raw):
            in_section1 = True
            continue
        if in_section1 and _CLAUDE_MD_NEXT_SECTION_RE.match(raw):
            break  # reached §2 — stop scanning §1
        if not in_section1:
            continue
        stripped = raw.strip()
        if not stripped or stripped == "---" or stripped.startswith(">"):
            continue
        if stripped.startswith("- "):
            words = len(stripped.split())
            if "→" not in stripped:
                issues.append({
                    "product": "<docs>", "file": "CLAUDE.md",
                    "issue": (
                        f"§1 rule (line {line_no}) has no `→` pointer — every always-on "
                        f"rule routes to its KB depth: {stripped[:70]}…"
                    ),
                    "severity": "high",
                })
            if words > _CLAUDE_MD_MAX_RULE_WORDS:
                issues.append({
                    "product": "<docs>", "file": "CLAUDE.md",
                    "issue": (
                        f"§1 rule (line {line_no}) is {words} words "
                        f"(cap {_CLAUDE_MD_MAX_RULE_WORDS}) — trim the body to the KB "
                        f"pointer: {stripped[:60]}…"
                    ),
                    "severity": "high",
                })
        else:
            issues.append({
                "product": "<docs>", "file": "CLAUDE.md",
                "issue": (
                    f"§1 prose body line (line {line_no}) — rules must be one-line "
                    f"bullets (rule + `→` pointer); move the body to the KB pointer: "
                    f"{stripped[:60]}…"
                ),
                "severity": "high",
            })
    return issues


# ── MEMORY.md index discipline (memory-md-index-discipline, Stage-4 2026-05-25) ──
# Sibling of check_claude_md_router. MEMORY.md is the auto-loaded agent-memory
# INDEX — its budget compounds across every session. Entries are
# `- [Title](file.md) — <recall hook>`; bloat the line and the index overflows
# (the 88 KB → 47 KB harness-agents-skills MEMORY trim was the corrective).
#
# Structural caveat: MEMORY.md lives OUT-OF-REPO at
# `~/.claude/projects/<encoded-cwd>/memory/MEMORY.md` (Claude Code per-project
# store), so this keeper CANNOT gate at git commit (pre-commit sees no memory
# edits). It gates at `validate` + the `--check-memory-md-index` CLI flag, and
# is silently skipped if the per-project memory dir isn't configured (other
# developers / forks). Optional true-auto-gate = a Claude Code Stop hook.
_MEMORY_MD_MAX_KB = 60                    # whole-file budget (live ~47 KB; cap blocks regression toward 88 KB)
_MEMORY_MD_MAX_ENTRY_CHARS = 500          # per-entry-line cap (worst pre-trim: 2,042 chars)


def _memory_md_path(repo_root: Path, home: Path | None = None) -> Path:
    """Derive the auto-loaded MEMORY.md path from the project root.

    Claude Code keys per-project state under `<home>/.claude/projects/<encoded>`
    where <encoded> = the absolute project path with `/` → `-`. `home` defaults
    to `Path.home()`; tests inject a tmp dir.
    """
    encoded = str(repo_root).replace("/", "-")
    base = home if home is not None else Path.home()
    return base / ".claude" / "projects" / encoded / "memory" / "MEMORY.md"


def check_memory_md_index(repo_root: Path | None = None, home: Path | None = None) -> list[dict]:
    """MEMORY.md is the auto-loaded memory index — keep entry lines tight.

    Gates two deterministic invariants of the harness-agents-skills MEMORY-trim
    pattern (sibling rule of `KB § PATTERNS/common/claude-md-router-discipline.md`):
      1. whole-file budget <= _MEMORY_MD_MAX_KB,
      2. every `- [Title](file.md)` entry line is <= _MEMORY_MD_MAX_ENTRY_CHARS
         and carries a valid `](X.md)` link.

    Memory is out-of-repo (Claude-Code-managed), so gates fire at `validate` and
    via `--check-memory-md-index`, NOT at git commit. Silent skip when the
    per-project memory dir isn't configured (other developers / forks).

    Born from the `harness-agents-skills` MEMORY trim (88 KB → 47 KB, 2026-05-25).
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    memory_md = _memory_md_path(root, home=home)
    if not memory_md.exists():
        return issues  # per-project memory not configured for this developer
    try:
        text = memory_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("compliance: cannot read MEMORY.md (%s)", exc)
        return issues

    total_kb = len(text.encode("utf-8")) / 1024
    if total_kb > _MEMORY_MD_MAX_KB:
        issues.append({
            "product": "<memory>",
            "file": "MEMORY.md",
            "issue": (
                f"MEMORY.md is {total_kb:.1f} KB (cap {_MEMORY_MD_MAX_KB} KB) — "
                f"the auto-loaded memory index must stay tight; trim bloated "
                f"entry lines to title + pointer + one recall hook (+ wikilinks). "
                f"Sibling rule: KB § PATTERNS/common/claude-md-router-discipline.md."
            ),
            "severity": "high",
        })

    entry_link_re = re.compile(r"^- \[[^\]]+\]\([^)]+\.md\)")
    extract_link_re = re.compile(r"\]\(([^)]+\.md)\)")
    for line_no, raw in enumerate(text.splitlines(), start=1):
        if not raw.startswith("- ["):
            continue
        if not entry_link_re.match(raw):
            issues.append({
                "product": "<memory>",
                "file": "MEMORY.md",
                "issue": (
                    f"MEMORY.md entry (line {line_no}) malformed — must start "
                    f"with `- [Title](filename.md)`: {raw[:80]}…"
                ),
                "severity": "high",
            })
            continue
        n = len(raw)
        if n > _MEMORY_MD_MAX_ENTRY_CHARS:
            m = extract_link_re.search(raw)
            link = m.group(1) if m else "<unknown>"
            issues.append({
                "product": "<memory>",
                "file": "MEMORY.md",
                "issue": (
                    f"MEMORY.md entry (line {line_no}, {n} chars, cap "
                    f"{_MEMORY_MD_MAX_ENTRY_CHARS}) is bloated — trim to title + "
                    f"pointer + one recall hook (+ wikilinks): {link}"
                ),
                "severity": "high",
            })
    return issues


# ── Harness-layer format keepers (Stage-4 2026-05-25, harness-agents-skills) ──
# .claude/skills + .claude/agents are always-on surfaces; these keepers gate
# authoring discipline so new skills/agents conform by construction.
_HARNESS_ADVISOR_AGENTS = frozenset({"architect", "security", "compliance-reviewer"})
_HARNESS_EXECUTOR_AGENTS = frozenset({"backend-engineer", "frontend-engineer", "devops-engineer", "engineer-seed"})
# Other agents (orchestrator-operator, skill-scout) have specialized contracts and
# are skipped by check_agent_archetype_contract.

# ── Agent-context architecture (Stage-4 2026-05-26, agent-context-architecture) ──
# KB § PATTERNS/common/agent-context-architecture.md — agent files declare full-domain
# `owns_kb:` in frontmatter; the keeper enforces existence + body-pointer mirror +
# exclusive ownership. The unowned-allowlist below names KB paths that are
# universal commons (no single owner) — every agent inherits via CLAUDE.md §1.
# Procedure-doc carve-out: orchestrator-operator + engineer-seed own no KB
# (they ARE protocols); skill-scout is a meta-scout (owns no KB).
_AGENT_KB_UNOWNED_ALLOWLIST = frozenset({
    "CONTEXT/01-PHILOSOPHY.md",
    "CONTEXT/02-LANDSCAPE.md",
    "CONTEXT/03-SEED-ARCHITECTURE.md",
    "CONTEXT/04-SHARED-LIBRARY.md",
    "CONTEXT/06-AGENTS.md",
    "CONTEXT/07-GAMIFICATION.md",
    "CONTEXT/PATTERNS/common/doc-symbology.md",
    "CONTEXT/PATTERNS/common/agent-reading-discipline.md",
    "CONTEXT/PATTERNS/common/ast.md",
    "CONTEXT/PATTERNS/common/accept-with-rationale.md",
    "CONTEXT/PATTERNS/common/remediation-markers.md",
    "CONTEXT/PATTERNS/common/defer-is-not-resolve.md",
    "CONTEXT/PATTERNS/common/absorption-ships-consume-docs.md",
    "CONTEXT/PATTERNS/common/storage-hygiene.md",
    "CONTEXT/PATTERNS/common/methodology-codification-pipeline.md",
    "CONTEXT/PATTERNS/common/repetitive-task-skill-codification.md",  # universal commons: DRY for procedures — sibling of methodology-codification-pipeline + project-execution recurrence rule, applies to every lens that authors procedures
    "CONTEXT/PATTERNS/common/build-learn-cache-mindset.md",  # universal commons: body-DRY for artifact knowledge — sibling of code-DRY + skill-DRY + methodology-codification-pipeline, applies to every lens that builds/refactors/bugfixes/integrates/deploys any artifact
    "CONTEXT/PATTERNS/common/surface-and-resume-tooling.md",  # universal commons: every engineer uses surface_to_tech_lead when blocked (no single-agent ownership)
    "CONTEXT/PATTERNS/common/bypass-rationalization-anti-patterns.md",  # universal commons: 5 rationalization shapes + ea7514e7 worked example + closes --no-verify commit loophole, applies to every lens that commits (engineers + tech-lead)
    "CONTEXT/PATTERNS/common/background-engineer-safety-discipline.md",  # universal commons: bg-dispatched engineers SURFACE-don't-bypass auto-mode safety (no --no-verify/--force/destructive-shared-ops); applies to every dispatched lens, no single owner
    "CONTEXT/PATTERNS/common/drift-fix-on-contact.md",
    "CONTEXT/PATTERNS/common/persistent-files-absorption.md",
    "CONTEXT/PATTERNS/common/keeper-check-before-docing.md",
    "CONTEXT/PATTERNS/common/keeper-pattern-cache.md",
    "CONTEXT/PATTERNS/common/claude-md-router-discipline.md",
    "CONTEXT/PATTERNS/common/lenses-applied-trailer.md",  # universal commons: every lens/role applies
    "CONTEXT/PATTERNS/common/dispatch-with-project-and-notes.md",  # universal commons: every dispatch + inline-lens reads PROJECT.md + files notes
    "CONTEXT/PATTERNS/common/lossless-doc-refactor.md",
    "CONTEXT/PATTERNS/common/agent-context-architecture.md",
    "CONTEXT/PATTERNS/common/self-branching-mode.md",
    "CONTEXT/PATTERNS/common/branching.md",
    "CONTEXT/PATTERNS/common/harness-overlay-worktree-divergence.md",
    "CONTEXT/PATTERNS/common/proposals-and-improvements.md",
    "CONTEXT/PATTERNS/common/verify-seed-on-fork-base.md",
    "CONTEXT/PATTERNS/common/phased-push-policy.md",
    "CONTEXT/PATTERNS/common/minimum-viable-rebuild.md",
    "CONTEXT/PATTERNS/common/scoped-auto-improvement.md",
    "CONTEXT/PATTERNS/common/kb-vector-search.md",
    "CONTEXT/PATTERNS/common/roadmap-tracking.md",
    "CONTEXT/PATTERNS/common/vector-cost-tracking.md",
    "CONTEXT/PATTERNS/common/vector-calibration.md",
    "CONTEXT/PATTERNS/common/code-embeddings.md",
    "CONTEXT/PATTERNS/common/vector-baseline.md",
    "CONTEXT/PATTERNS/common/code-recurrence-baseline.md",
    "CONTEXT/PATTERNS/common/dont-block-on-background.md",
    "CONTEXT/PATTERNS/common/eight-way-sync.md",
    "CONTEXT/PATTERNS/common/extractor-correctness-vs-mirror.md",
    "CONTEXT/PATTERNS/common/cache-locking-discipline.md",
    "CONTEXT/PATTERNS/common/versioning.md",
    "CONTEXT/PATTERNS/common/engineer-output-linter.md",
    "CONTEXT/PATTERNS/common/unified-query.md",
    "CONTEXT/PATTERNS/common/scan-repetition-semantic.md",
    "CONTEXT/PATTERNS/common/doc-to-code-drift.md",
    "CONTEXT/PATTERNS/common/orphan-branch-sweeper.md",
    "CONTEXT/PATTERNS/common/cache-telemetry.md",
    "CONTEXT/PATTERNS/common/brief-similarity-radar.md",
    "CONTEXT/PATTERNS/common/session-end-sweep.md",
    "CONTEXT/PATTERNS/common/dispatch-warmup.md",
    "CONTEXT/PATTERNS/common/product-centroid-drift.md",
    "CONTEXT/PATTERNS/common/dispatch-token-log.md",
    "CONTEXT/PATTERNS/common/dispatch-budget-telemetry.md",  # universal commons — orchestrator tool, no single-agent ownership
    "CONTEXT/PATTERNS/common/auto-author-scaffolds.md",
    "CONTEXT/PATTERNS/common/cache-auto-freshness.md",
    "CONTEXT/PATTERNS/common/kb-recurrence-radar.md",
    "CONTEXT/PATTERNS/common/learn-before-archive.md",  # universal commons — pre-delete salvage gate applies to every lens that deletes any artifact (branch/worktree/file/project); no single-agent ownership
    "CONTEXT/PATTERNS/common/methodology-execution-discipline.md",  # universal commons — close-the-loop/work-within-the-grain/gate-as-learning is an operating contract for EVERY lens; no single-agent ownership
    "CONTEXT/PATTERNS/common/product-dev-learning-ground.md",  # universal commons — learn-development-craft applies to every lens that builds products (backend/frontend/seed); no single-agent ownership
    "CONTEXT/PATTERNS/architect/seed-organ-canonical-set.md",  # universal commons — organ catalog is consumed by all agents as a reuse surface; no single-agent ownership
    "CONTEXT/PATTERNS/architect/products-consume-canonical-organs.md",  # universal commons — canonical organ consumption rule applies to every agent that builds FE components
})

# Agents that intentionally own no KB territory (meta-roles / procedure-docs).
# Their frontmatter MUST declare `owns_kb: []` explicitly (no ambiguity).
_AGENT_KB_OWNS_NOTHING = frozenset({"engineer-seed", "orchestrator-operator", "skill-scout"})

# Repo-root-relative untracked allowlist for check_git_leftovers — files that
# may legitimately appear at depth 1 untracked. Anything else trips the keeper.
# (.gitignore covers the bulk; this is for items neither gitignored nor expected.)
_GIT_LEFTOVERS_ROOT_ALLOWLIST = frozenset({
    # nothing additional — .gitignore is the canonical allowlist;
    # this set exists for tools-only carve-outs surfaced as they appear.
})


def _parse_frontmatter(text: str) -> dict[str, str] | None:
    """Parse the first `--- … ---` YAML block at the top of a markdown file.

    Returns None if frontmatter is absent or unclosed; values returned as raw
    strings (no YAML coercion — we only need top-level string keys).
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fm: dict[str, str] = {}
    for raw in lines[1:]:
        if raw.strip() == "---":
            return fm
        if ":" in raw and not raw.lstrip().startswith("#"):
            key, _, val = raw.partition(":")
            # only top-level keys (no leading whitespace) — skip nested YAML
            if key == key.lstrip():
                fm[key.strip()] = val.strip()
    return None  # no closing delimiter — malformed


def check_skill_format(repo_root: Path | None = None) -> list[dict]:
    """Every `.claude/skills/<name>/SKILL.md` has valid required frontmatter.

    Required: `name:` (matches parent dir) + non-empty `description:` (carries
    the trigger phrases the harness matches on). Sibling of check_agent_format.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    skills_dir = root / ".claude" / "skills"
    if not skills_dir.is_dir():
        return issues
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        rel = f".claude/skills/{skill_dir.name}/SKILL.md"
        if not skill_md.is_file():
            issues.append({
                "product": "<harness>", "file": rel,
                "issue": f"Skill dir `{skill_dir.name}` has no SKILL.md — every .claude/skills/<name>/ must contain SKILL.md.",
                "severity": "high",
            })
            continue
        try:
            text = skill_md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm = _parse_frontmatter(text)
        if fm is None:
            issues.append({
                "product": "<harness>", "file": rel,
                "issue": "SKILL.md missing/malformed frontmatter — must open with `---`, declare `name:` + `description:`, then close with `---`.",
                "severity": "high",
            })
            continue
        name = fm.get("name", "")
        desc = fm.get("description", "")
        if not name:
            issues.append({"product": "<harness>", "file": rel, "issue": "SKILL.md frontmatter missing `name:`.", "severity": "high"})
        elif name != skill_dir.name:
            issues.append({
                "product": "<harness>", "file": rel,
                "issue": f"SKILL.md `name: {name}` ≠ directory `{skill_dir.name}` — name and dir must agree for the harness to load the skill.",
                "severity": "high",
            })
        if not desc:
            issues.append({
                "product": "<harness>", "file": rel,
                "issue": "SKILL.md frontmatter missing `description:` — the description carries the trigger phrases the harness uses to auto-fire the skill.",
                "severity": "high",
            })
    return issues


def check_agent_format(repo_root: Path | None = None) -> list[dict]:
    """Every `.claude/agents/<name>.md` has valid required frontmatter + tools:.

    Required: `name:` (matches filename stem) + `description:` + `tools:`.
    Omitting `tools:` inherits ~400 deferred tool names (per
    `KB § PATTERNS/architect/dispatch-engineer-tuning.md`) — significant startup-token
    waste. Sibling of check_skill_format + check_agent_archetype_contract.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    agents_dir = root / ".claude" / "agents"
    if not agents_dir.is_dir():
        return issues
    for agent_md in sorted(agents_dir.glob("*.md")):
        if not agent_md.is_file():
            continue
        rel = f".claude/agents/{agent_md.name}"
        stem = agent_md.stem
        try:
            text = agent_md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm = _parse_frontmatter(text)
        if fm is None:
            issues.append({
                "product": "<harness>", "file": rel,
                "issue": "Agent file missing/malformed frontmatter — must open with `---`, declare `name:` + `description:` + `tools:`, then close with `---`.",
                "severity": "high",
            })
            continue
        name = fm.get("name", "")
        if not name:
            issues.append({"product": "<harness>", "file": rel, "issue": "Agent frontmatter missing `name:`.", "severity": "high"})
        elif name != stem:
            issues.append({
                "product": "<harness>", "file": rel,
                "issue": f"Agent `name: {name}` ≠ filename `{stem}.md` — the Agent tool dispatches by frontmatter name; mismatch = unreachable.",
                "severity": "high",
            })
        if not fm.get("description", ""):
            issues.append({"product": "<harness>", "file": rel, "issue": "Agent frontmatter missing `description:`.", "severity": "high"})
        if not fm.get("tools", ""):
            issues.append({
                "product": "<harness>", "file": rel,
                "issue": "Agent frontmatter missing `tools:` — omitting it inherits ~400 deferred tool names (KB § PATTERNS/architect/dispatch-engineer-tuning.md). Declare an explicit scoped allowlist.",
                "severity": "high",
            })
    return issues


def check_agent_archetype_contract(repo_root: Path | None = None) -> list[dict]:
    """Advisors declare no Edit/Write; executors reference engineer-seed.

    Two archetypes per the harness-agents-skills model:
      - ADVISORS (architect, security, compliance-reviewer) — read-only; their
        `tools:` MUST NOT include `Edit` or `Write` (contract enforced at the
        tool layer, not just discipline).
      - EXECUTORS (backend-engineer, frontend-engineer, engineer-seed) —
        body should reference the `engineer-seed` protocol.
    Other agents (orchestrator-operator, skill-scout) have specialized
    contracts and are skipped. Update the archetype sets when new agents land.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    agents_dir = root / ".claude" / "agents"
    if not agents_dir.is_dir():
        return issues
    for agent_md in sorted(agents_dir.glob("*.md")):
        if not agent_md.is_file():
            continue
        stem = agent_md.stem
        rel = f".claude/agents/{agent_md.name}"
        try:
            text = agent_md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm = _parse_frontmatter(text)
        if fm is None:
            continue  # check_agent_format already flagged this
        tools = fm.get("tools", "")
        if stem in _HARNESS_ADVISOR_AGENTS:
            for forbidden in ("Edit", "Write"):
                if re.search(rf"\b{forbidden}\b", tools):
                    issues.append({
                        "product": "<harness>", "file": rel,
                        "issue": (
                            f"Advisor agent `{stem}` declares `{forbidden}` in `tools:` — "
                            f"advisor archetype is read-only (surfaces a recommendation, never "
                            f"writes code). Remove `{forbidden}` from tools."
                        ),
                        "severity": "high",
                    })
        elif stem in _HARNESS_EXECUTOR_AGENTS:
            if "engineer-seed" not in text:
                issues.append({
                    "product": "<harness>", "file": rel,
                    "issue": (
                        f"Executor agent `{stem}` body does not reference `engineer-seed` — "
                        f"executors apply the standing engineer-seed protocol; the body should "
                        f"say so (e.g. \"Apply the engineer-seed protocol\")."
                    ),
                    "severity": "warning",
                })
    return issues


def _parse_frontmatter_owns_kb(text: str) -> list[str] | None:
    """Extract the `owns_kb:` list from agent frontmatter.

    Returns:
      - list[str] (possibly empty) when the key is present
      - None when the key is absent OR frontmatter is malformed.

    Recognizes both inline `owns_kb: []` and the block form

        owns_kb:
          - CONTEXT/PATTERNS/foo.md
          - CONTEXT/PATTERNS/bar.md

    Sibling of `_parse_frontmatter` (which handles top-level scalars only).
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    in_block = False
    items: list[str] = []
    saw_key = False
    for raw in lines[1:]:
        if raw.strip() == "---":
            return items if saw_key else None
        if not in_block:
            stripped = raw.lstrip()
            if stripped.startswith("owns_kb:") and raw == stripped:
                saw_key = True
                rhs = raw.partition(":")[2].strip()
                if rhs == "[]":
                    return []  # explicit empty
                if rhs:
                    # inline list `[a, b]` form — best-effort split
                    if rhs.startswith("[") and rhs.endswith("]"):
                        inner = rhs[1:-1]
                        return [p.strip().strip('"').strip("'") for p in inner.split(",") if p.strip()]
                    # unknown inline shape → treat as malformed
                    return None
                in_block = True
                continue
        else:
            if raw.startswith("  - ") or raw.startswith("- "):
                value = raw.lstrip()[2:].strip().strip('"').strip("'")
                if value:
                    items.append(value)
                continue
            # End of block: either dedented top-level key, or blank+something-else.
            if raw.strip() == "":
                continue
            if not raw.startswith(" "):
                # next top-level key — owns_kb block ends here
                in_block = False
                # don't consume this line; loop will continue and re-process
                # (we just need to NOT take it as a list item).
                # The frontmatter scanner is forward-only so we accept the
                # current items and keep scanning until --- closer.
                continue
    return None  # never closed


def check_agent_kb_alignment(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 keeper (2026-05-26, agent-context-architecture): every agent file
    declares its full-domain `owns_kb:` and every declared path exists ∧ is
    referenced in the agent body ∧ is claimed by exactly one agent.

    The agent-context-architecture (KB § PATTERNS/common/agent-context-architecture.md)
    treats `.claude/agents/<name>.md` as the SPECIALIST L1 index — bodies live
    in KB at the pointers. This keeper enforces that the routing is sound:

      (a) `owns_kb:` is declared (list, possibly empty) — explicit "owns
          nothing" required for meta-agents (`_AGENT_KB_OWNS_NOTHING`).
      (b) Every declared path EXISTS at `KNOWLEDGE-BASE/<path>` on disk.
      (c) Every declared path appears in the agent body as a `KB § <path>`
          pointer — a declaration without a body pointer is dead.
      (d) No path is double-claimed across two agents (until shared-multi-domain
          frontmatter ships — Phase B).
      (e) Every in-scope KB path (PATTERNS / GUIDES / INTEGRATIONS /
          CONTEXT/<domain>/ / top-level CONTEXT/0X) is claimed by ≥1 agent OR
          listed in `_AGENT_KB_UNOWNED_ALLOWLIST` (universal commons).

    Severity `high` (the gate keeps the methodology authority enforceable).
    KB § PATTERNS/common/agent-context-architecture.md.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    agents_dir = root / ".claude" / "agents"
    kb_dir = root / "KNOWLEDGE-BASE"
    if not agents_dir.is_dir() or not kb_dir.is_dir():
        return issues

    # Pass 1 — per-agent: parse owns_kb, verify (a)(b)(c), accumulate claims.
    claims: dict[str, list[str]] = {}  # KB path → [agent_name, ...]
    for agent_md in sorted(agents_dir.glob("*.md")):
        if not agent_md.is_file():
            continue
        rel = f".claude/agents/{agent_md.name}"
        stem = agent_md.stem
        try:
            text = agent_md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        owns = _parse_frontmatter_owns_kb(text)
        # (a) Declaration present?
        if owns is None:
            issues.append({
                "product": "<harness>", "file": rel,
                "issue": (
                    f"Agent `{stem}` missing `owns_kb:` frontmatter key — "
                    f"required by KB § PATTERNS/common/agent-context-architecture.md. "
                    f"Declare `owns_kb: []` for meta-agents (no KB territory) "
                    f"or a list of `CONTEXT/...` paths the agent curates."
                ),
                "severity": "high",
            })
            continue
        # Meta-agent must declare empty.
        if stem in _AGENT_KB_OWNS_NOTHING and owns:
            issues.append({
                "product": "<harness>", "file": rel,
                "issue": (
                    f"Meta-agent `{stem}` declares non-empty `owns_kb:` — "
                    f"meta-agents (engineer-seed, orchestrator-operator, "
                    f"skill-scout) own no KB territory. Declare `owns_kb: []`."
                ),
                "severity": "high",
            })
            continue
        # (b)(c) per-path verification.
        for path in owns:
            kb_file = kb_dir / path
            if not kb_file.is_file():
                issues.append({
                    "product": "<harness>", "file": rel,
                    "issue": (
                        f"`owns_kb:` declares `{path}` but `KNOWLEDGE-BASE/{path}` "
                        f"does NOT exist — ownership of a missing doc. Fix the "
                        f"path or remove the declaration."
                    ),
                    "severity": "high",
                })
                continue
            # Body-pointer mirror: the agent body MUST reference the path as a
            # `KB § <path>` pointer (or `KB § <path stripped of CONTEXT/>`, the
            # canonical short form the router uses).
            short = path.removeprefix("CONTEXT/")
            if (f"KB § {path}" not in text) and (f"KB § {short}" not in text):
                issues.append({
                    "product": "<harness>", "file": rel,
                    "issue": (
                        f"`owns_kb:` declares `{path}` but the agent body has no "
                        f"`KB § {short}` pointer — declaration without body "
                        f"pointer is dead routing. Add a one-line pointer."
                    ),
                    "severity": "high",
                })
            claims.setdefault(path, []).append(stem)

    # (d) double-claim across agents.
    for path, owners in claims.items():
        if len(owners) > 1:
            issues.append({
                "product": "<harness>", "file": f"KNOWLEDGE-BASE/{path}",
                "issue": (
                    f"KB path `{path}` is claimed by ≥2 agents ({', '.join(sorted(set(owners)))}) — "
                    f"exclusive ownership required until shared-multi-domain "
                    f"frontmatter ships (Phase B). Move to unowned-allowlist "
                    f"if universal, or pick one canonical owner."
                ),
                "severity": "high",
            })

    # (e) every in-scope KB path is claimed OR allowlisted.
    in_scope_dirs = ["CONTEXT/PATTERNS", "CONTEXT/GUIDES", "CONTEXT/INTEGRATIONS",
                     "CONTEXT/backend", "CONTEXT/frontend"]
    in_scope_top = [f"CONTEXT/0{i}-" for i in range(1, 8)]
    for md in sorted(kb_dir.rglob("*.md")):
        try:
            rel_to_kb = md.relative_to(kb_dir).as_posix()
        except ValueError:
            continue
        # Filter to in-scope.
        if not (
            any(rel_to_kb.startswith(d + "/") for d in in_scope_dirs)
            or any(rel_to_kb.startswith(prefix) for prefix in in_scope_top)
        ):
            continue
        if rel_to_kb in _AGENT_KB_UNOWNED_ALLOWLIST:
            continue
        if rel_to_kb in claims:
            continue
        issues.append({
            "product": "<harness>", "file": f"KNOWLEDGE-BASE/{rel_to_kb}",
            "issue": (
                f"KB doc `{rel_to_kb}` is not claimed by any agent's `owns_kb:` "
                f"and not in the unowned-commons allowlist — either add it to "
                f"an agent's `owns_kb` + body pointer, or to "
                f"`_AGENT_KB_UNOWNED_ALLOWLIST` in compliance.py with a one-line "
                f"rationale (universal commons)."
            ),
            "severity": "high",
        })
    return issues


def check_git_leftovers(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 keeper (2026-05-26, drift-fix-on-contact): scan for the git-shape
    drift class that recurred despite existing keepers (check_branch_orphan /
    check_dispatcher_staleness / check_archive_staleness). Severity `high`.

    Scans:
      (a) Untracked at repo root depth 1 (excluding allowlist + .gitignore).
          A `decision.md` paste / `notes.md` scratch / stray `.patch` ⇒ drift.
      (b) `.claude/worktrees/<x>/` with uncommitted state (`git status --porcelain`
          non-empty in the worktree).

    Remediation: apply the on-contact drill (PAUSE → resolve → surface-if-blocked
    → update docs → continue). Silent-skip is forbidden.

    KB § PATTERNS/common/drift-fix-on-contact.md.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    # Silently skip in non-git contexts (test harnesses, vendored copies).
    if not (root / ".git").exists():
        return issues
    try:
        import subprocess
        # (a) Untracked at depth 1 — `git status --porcelain` filtered for `?? `
        # entries that don't contain a `/`.
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines():
            if not line.startswith("?? "):
                continue
            path = line[3:].strip()
            # Depth-1 only (untracked dirs come as `dirname/`).
            if "/" in path.rstrip("/"):
                continue
            if path in _GIT_LEFTOVERS_ROOT_ALLOWLIST:
                continue
            issues.append({
                "product": "<harness>", "file": path,
                "issue": (
                    f"Untracked file at repo root: `{path}` — drift-shape "
                    f"covered by KB § PATTERNS/common/drift-fix-on-contact.md. "
                    f"Apply the on-contact drill (absorb / delete / move + doc), "
                    f"don't leave it for next session."
                ),
                "severity": "high",
                "symbol": "untracked-at-root",
            })
        # (b) Per-registered-worktree uncommitted state.
        wt_result = subprocess.run(
            ["git", "-C", str(root), "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        worktree_paths: list[Path] = []
        for line in wt_result.stdout.splitlines():
            if line.startswith("worktree "):
                wt_path = Path(line.split(" ", 1)[1].strip())
                if wt_path != root and wt_path.exists():
                    worktree_paths.append(wt_path)
        for wt in worktree_paths:
            wt_status = subprocess.run(
                ["git", "-C", str(wt), "status", "--porcelain"],
                capture_output=True, text=True, timeout=10,
            )
            if wt_status.stdout.strip():
                rel_wt = wt.relative_to(root).as_posix() if wt.is_relative_to(root) else str(wt)
                # Count + sample first line.
                lines = wt_status.stdout.splitlines()
                sample = lines[0][:80] if lines else ""
                issues.append({
                    "product": "<harness>", "file": rel_wt,
                    "issue": (
                        f"Worktree `{rel_wt}` has {len(lines)} uncommitted "
                        f"entries (sample: `{sample}`) — drift-shape per "
                        f"KB § PATTERNS/common/drift-fix-on-contact.md. Either commit "
                        f"+ integrate via `noctus.dev.task_branch action=integrate`, "
                        f"OR salvage + cleanup via `task_branch action=cleanup`."
                    ),
                    "severity": "high",
                    "symbol": "worktree-uncommitted",
                })
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        # If git is unreachable, silently skip (test/vendored contexts);
        # this keeper is a drift-detector, not a git-availability gate.
        return issues
    return issues


def _resolve_cache_path(name: str, root: Path) -> Path:
    """Resolve a cache file path via `cache_backend.cache_path` (honoring
    the Tier-1 shared-cache layout at `<git-common-dir>/noctusai/cache/`,
    per KB § PATTERNS/common/cache-portable-architecture.md). Falls back
    to the legacy `<root>/.claude/cache/<name>.sqlite` when the backend
    module is unavailable (test contexts, vendored copies).

    Born 2026-05-28 as drift-fix-on-contact for the 7→8-way promotion:
    the existing per-cache freshness keepers all hard-coded the legacy
    path and reported false `<name>-cache-missing` on every worktree
    using the new layout.
    """
    try:
        from .cache_backend import cache_path as _cache_path
        return _cache_path(name, repo_root=root)
    except Exception:  # noqa: BLE001 — defensive fallback
        return root / ".claude" / "cache" / f"{name}.sqlite"


def _cache_label(cache: Path, root: Path) -> str:
    """Return a relative label for a cache file in keeper-issue output.

    The Tier-1 cache may live OUTSIDE the worktree root
    (at `<git-common-dir>/noctusai/cache/`), so `relative_to(root)` would
    raise. Fall back to the absolute path string in that case.
    """
    try:
        return str(cache.relative_to(root))
    except ValueError:
        return str(cache)


def check_keeper_cache_freshness(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 keeper (2026-05-26): the local keeper-pattern cache MUST mirror
    `compliance.py` — the user mandate is *"the memory should always be the
    keeper mirror."*

    The cache (`.claude/cache/keeper-patterns.sqlite`, gitignored) is what
    doc-authoring agents query BEFORE writing a gated doc — so a stale cache
    means agents author drift-prone docs from outdated patterns.
    `keeper_pattern_cache.refresh()` is idempotent; the pre-commit hook
    auto-runs it whenever `compliance.py` is staged, and `lookup()` self-heals
    lazily on `source_sha` mismatch. This keeper is the loud freshness gate.

    Predicate: ``cache exists ∧ cache_meta.source_sha ≡ sha256(compliance.py)``.
    Severity: ``high`` (gates the gate). Silent skip when ``compliance.py``
    absent (a non-noc tree).

    Remediation: ``python mcp/noctusai/cli.py --refresh-keeper-cache``.

    KB § PATTERNS/common/keeper-pattern-cache.md.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    src = root / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "compliance.py"
    if not src.exists():
        return issues
    cache = _resolve_cache_path("keeper-patterns", root)
    cache_file_label = _cache_label(cache, root)
    if not cache.exists():
        issues.append({
            "file": cache_file_label,
            "issue": (
                "keeper-pattern cache missing — run "
                "`python mcp/noctusai/cli.py --refresh-keeper-cache` "
                "(KB § PATTERNS/common/keeper-pattern-cache.md)"
            ),
            "severity": "high",
            "symbol": "keeper-cache-missing",
        })
        return issues
    src_sha = hashlib.sha256(src.read_bytes()).hexdigest()
    try:
        conn = sqlite3.connect(str(cache))
        cur = conn.execute("SELECT value FROM cache_meta WHERE key='source_sha'")
        row = cur.fetchone()
        conn.close()
    except sqlite3.Error as e:
        issues.append({
            "file": cache_file_label,
            "issue": (
                f"keeper-pattern cache unreadable ({e}) — re-create via "
                "`--refresh-keeper-cache`"
            ),
            "severity": "high",
            "symbol": "keeper-cache-unreadable",
        })
        return issues
    if not row or row[0] != src_sha:
        cached = row[0] if row else "(none)"
        issues.append({
            "file": cache_file_label,
            "issue": (
                f"keeper-pattern cache STALE — cache.source_sha={cached[:12]} "
                f"≠ compliance.py sha={src_sha[:12]}; run `--refresh-keeper-cache`"
            ),
            "severity": "high",
            "symbol": "keeper-cache-stale",
        })
    return issues


def check_agent_context_cache_freshness(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 keeper (2026-05-26, Phase B): the agent-context cache MUST mirror
    each agent's `bundle_sha = sha256(agent.md ∪ each owned_kb)`. Sibling of
    `check_keeper_cache_freshness` — same 3-leg mirror contract (eager
    pre-commit refresh + lazy query-time rebuild + this loud freshness gate).

    The cache (`.claude/cache/agent-context.sqlite`, gitignored) holds the
    compact bundle (frontmatter + body + owned-KB compact extracts) that an
    architect / dispatched agent queries via `noctus.dev.agent_context(...)`
    in one round-trip instead of N Reads. A stale cache means agents query
    yesterday's pattern.

    Predicate: ``cache exists ∧ for each .claude/agents/<name>.md the cached
    bundle_sha matches live sha256(agent.md ∪ owned_kb)``. Severity ``high``.
    Silent skip when `.claude/agents/` absent (a non-noc tree).

    Remediation: ``python mcp/noctusai/cli.py --refresh-agent-context-cache``.

    KB § PATTERNS/common/agent-context-architecture.md § Keeper enforcement.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    agents_dir = root / ".claude" / "agents"
    if not agents_dir.is_dir():
        return issues
    cache = _resolve_cache_path("agent-context", root)
    cache_file_label = _cache_label(cache, root)
    if not cache.exists():
        issues.append({
            "file": cache_file_label,
            "issue": (
                "agent-context cache missing — run "
                "`python mcp/noctusai/cli.py --refresh-agent-context-cache` "
                "(KB § PATTERNS/common/agent-context-architecture.md)"
            ),
            "severity": "high",
            "symbol": "agent-context-cache-missing",
        })
        return issues
    # Per-agent bundle_sha check (uses the live extractor for parity).
    try:
        from .agent_context_cache import get_bundle_sha
    except Exception as e:  # noqa: BLE001  (module-load failure is loud)
        issues.append({
            "file": cache_file_label,
            "issue": (
                f"agent-context cache module unreadable ({e}) — re-create via "
                "`--refresh-agent-context-cache`"
            ),
            "severity": "high",
            "symbol": "agent-context-cache-module-error",
        })
        return issues
    for agent_md in sorted(agents_dir.glob("*.md")):
        stem = agent_md.stem
        live, cached_sha = get_bundle_sha(stem)
        if cached_sha is None:
            issues.append({
                "product": "<harness>", "file": f".claude/agents/{stem}.md",
                "issue": (
                    f"agent-context cache MISSING entry for `{stem}` — run "
                    f"`--refresh-agent-context-cache --agent {stem}`"
                ),
                "severity": "high",
                "symbol": "agent-context-cache-missing-agent",
            })
            continue
        if cached_sha != live:
            issues.append({
                "product": "<harness>", "file": f".claude/agents/{stem}.md",
                "issue": (
                    f"agent-context cache STALE for `{stem}` — "
                    f"cached.bundle_sha={cached_sha[:12]} ≠ live={live[:12]}; "
                    f"run `--refresh-agent-context-cache --agent {stem}`"
                ),
                "severity": "high",
                "symbol": "agent-context-cache-stale",
            })
    return issues


_CONTEXTUALIZE_CANONICAL_CORES = (
    # Each entry: a substring that MUST appear as a pointer in CONTEXTUALIZE.md.
    # Curated list of the docs a fresh agent MUST be routed to. Adding a new
    # canonical core = add the line here + ensure CONTEXTUALIZE.md points at
    # it; check_contextualize_alignment enforces both legs.
    "CLAUDE.md",
    "KNOWLEDGE-BASE/AGENT-CONTEXT.md",
    "CONTEXT/01-PHILOSOPHY.md",
    "CONTEXT/02-LANDSCAPE.md",
    "CONTEXT/03-SEED-ARCHITECTURE.md",
    "KB § INDEX.md",
    "MEMORY.md",
    "PATTERNS/common/agent-context-architecture.md",
    "PATTERNS/common/drift-fix-on-contact.md",
    "PATTERNS/common/self-branching-mode.md",
    "PATTERNS/common/ast.md",
    "PATTERNS/common/keeper-pattern-cache.md",
    "PATTERNS/common/scoped-auto-improvement.md",
)
# Soft cap: re-bloat above this fires the keeper (sibling of check_claude_md_router).
# Set at 75 lines to allow WIDE-REACH pointer coverage (domain map + specialists +
# universal patterns + conditional reads) without rewarding inline-body re-bloat.
# A 54-line file with duplicated CLAUDE.md §1 bodies was worse than a 64-line
# file with broad pointer-only reach. Raise via codified rationale only.
_CONTEXTUALIZE_LINE_CAP = 75


def check_kb_vector_canonical(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 keeper (2026-05-26, kb-vector-search): enforces the
    **markdown-canonical, vector-DB-is-enrichment** principle.

    The vector DB at `.claude/cache/kb-embeddings.sqlite` is an INDEX +
    enrichment over the markdown KB — never a content store. User
    mandate 2026-05-26: *"markdown stays in git as canonical … vector
    DB becomes a smarter index, not a replacement."* This keeper enforces
    that contract.

    Predicates (severity WARNING — advisory keeper, not blocker):
      (a) Every cached chunk's `path` resolves to a real `.md` under
          `KNOWLEDGE-BASE/`. Orphan rows (markdown deleted but cache row
          remains) ⇒ flag for refresh.
      (b) When the cache has rows, every chunk's `source_sha` must match
          the live file (per-doc freshness). Stale ⇒ flag.
      (c) (Optional, deferred) — no code path returns vector-DB content
          AS authoritative content; vectors index back to markdown.
          Codified as the principle, enforced by code review for now;
          can be promoted to a `noctus.dev.kb_chunks_match_markdown`
          tool when needed.

    Severity ``warning`` (NOT high): vector search is advisory; a stale
    or partially-orphaned cache degrades discovery but never breaks
    correctness. Surface, don't block.

    Silent skip when:
      - The cache file is absent (no rows to validate — fresh clone).
      - `KNOWLEDGE-BASE/` is absent (non-noc tree, e.g. test fixtures).

    KB § PATTERNS/common/kb-vector-search.md.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    kb_dir = root / "KNOWLEDGE-BASE"
    cache = _resolve_cache_path("kb-embeddings", root)
    if not kb_dir.is_dir() or not cache.exists():
        return issues
    # Query the cache directly via sqlite3 (avoid module import to keep
    # the keeper resilient to a partially-broken kb_embeddings module).
    try:
        conn = sqlite3.connect(str(cache))
        # Schema may be either the new dual-engine shape or the older
        # single-table shape — try the new first, fall back if needed.
        try:
            cur = conn.execute(
                "SELECT path, source_sha FROM kb_chunks GROUP BY path"
            )
            rows = list(cur.fetchall())
        except sqlite3.OperationalError:
            try:
                cur = conn.execute(
                    "SELECT path, source_sha FROM kb_embeddings GROUP BY path"
                )
                rows = list(cur.fetchall())
            except sqlite3.OperationalError:
                rows = []
        conn.close()
    except sqlite3.Error as e:
        issues.append({
            "product": "<harness>", "file": _cache_label(cache, root),
            "issue": f"kb-embeddings cache unreadable ({e}) — refresh via --refresh-kb-embeddings",
            "severity": "warning",
            "symbol": "kb-vector-cache-unreadable",
        })
        return issues
    for path, cached_sha in rows:
        md = kb_dir / path
        if not md.exists():
            # (a) orphan row — markdown deleted, cache still has it.
            issues.append({
                "product": "<harness>", "file": _cache_label(cache, root),
                "issue": (
                    f"kb-embeddings cache has rows for `{path}` but the "
                    f"markdown doesn't exist (orphan). Vector DB must mirror "
                    f"markdown — refresh with --refresh-kb-embeddings to drop "
                    f"orphans."
                ),
                "severity": "warning",
                "symbol": "kb-vector-orphan",
            })
            continue
        # (b) per-doc staleness.
        live_sha = hashlib.sha256(md.read_bytes()).hexdigest()
        if live_sha != cached_sha:
            issues.append({
                "product": "<harness>", "file": f"KNOWLEDGE-BASE/{path}",
                "issue": (
                    f"kb-embeddings stale for `{path}` — cached.sha="
                    f"{cached_sha[:12]} ≠ live={live_sha[:12]}; refresh via "
                    f"--refresh-kb-embeddings."
                ),
                "severity": "warning",
                "symbol": "kb-vector-stale",
            })
    return issues


def check_code_embeddings_cache_freshness(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 keeper (2026-05-26, W2-E3'): the code-embeddings cache MUST
    mirror each source file's `sha256(file)`. Fifth member of the keeper-mirror
    family — sibling of `check_kb_vector_canonical`, applied to the code
    corpus instead of the docs corpus.

    Predicates (severity WARNING — advisory keeper, not blocker):
      (a) Every cached chunk's `path` resolves to a real source file under
          the tracked roots (`mcp/`, `noctusai_lib/`, `products/seed/`).
          Orphan rows (file deleted but cache row remains) ⇒ flag for refresh.
      (b) When the cache has rows, every chunk's `source_sha` must match
          the live file. Stale ⇒ flag.

    Severity ``warning`` (NOT high) — vector code search is advisory; a
    stale or partially-orphaned cache degrades discovery but never breaks
    correctness. Surface, don't block.

    Silent skip when:
      - The cache file is absent (no rows to validate — fresh clone).
      - No tracked code roots exist under repo_root (non-noc tree).

    Remediation: ``python mcp/noctusai/cli.py --refresh-code-embeddings``.

    KB § CONTEXT/PATTERNS/common/code-embeddings.md.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    cache = _resolve_cache_path("code-embeddings", root)
    tracked_roots = ("mcp", "noctusai_lib", "products/seed")
    if not any((root / r).is_dir() for r in tracked_roots) or not cache.exists():
        return issues
    try:
        conn = sqlite3.connect(str(cache))
        try:
            # Exclude kind='organ' rows: organs (W4 seed-organs-cache) share the
            # code_chunks table but store a BUNDLE source_sha (source+tests+
            # knowledge), not the file-bytes sha this checker compares against,
            # and they have their own lifecycle (register_organ /
            # organ_knowledge_append), not --refresh-code-embeddings. Including
            # them produced permanent false `code-vector-stale` on every organ.
            cur = conn.execute(
                "SELECT path, source_sha FROM code_chunks "
                "WHERE COALESCE(kind,'') != 'organ' GROUP BY path"
            )
            rows = list(cur.fetchall())
        except sqlite3.OperationalError:
            rows = []
        conn.close()
    except sqlite3.Error as e:
        issues.append({
            "product": "<harness>", "file": _cache_label(cache, root),
            "issue": (
                f"code-embeddings cache unreadable ({e}) — refresh via "
                "--refresh-code-embeddings"
            ),
            "severity": "warning",
            "symbol": "code-vector-cache-unreadable",
        })
        return issues
    for path, cached_sha in rows:
        src = root / path
        if not src.exists():
            issues.append({
                "product": "<harness>", "file": _cache_label(cache, root),
                "issue": (
                    f"code-embeddings cache has rows for `{path}` but the "
                    f"file doesn't exist (orphan). Refresh with "
                    f"--refresh-code-embeddings to drop orphans."
                ),
                "severity": "warning",
                "symbol": "code-vector-orphan",
            })
            continue
        try:
            live_sha = hashlib.sha256(src.read_bytes()).hexdigest()
        except OSError:
            continue
        if live_sha != cached_sha:
            issues.append({
                "product": "<harness>", "file": path,
                "issue": (
                    f"code-embeddings stale for `{path}` — cached.sha="
                    f"{cached_sha[:12]} ≠ live={live_sha[:12]}; refresh via "
                    f"--refresh-code-embeddings."
                ),
                "severity": "warning",
                "symbol": "code-vector-stale",
            })
    return issues


def check_noc_graph_cache_freshness(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 keeper (2026-05-27, hardened 2026-05-28 in the 7→8-way
    promotion): the noc-graph cache MUST mirror the aggregate sha of
    every source file that feeds the graph (code corpus + KB + harness
    + landscape + memory index + cli + history). 8th member of the
    keeper-mirror family — sibling of `check_code_embeddings_cache_freshness`,
    applied to the structured graph instead of the embeddings cache.
    Composed into `check_all_cache_freshness` (the 8-way surface #8 gate).

    Severity ``warning`` (loud but auto-recoverable): cache rebuild is
    a single `--refresh-noc-graph` call, so blocking would be punitive,
    but it's louder than purely advisory because `cache-as-agent-tool`
    makes the graph the live agent read path for orientation
    (`/contextualize` + `noctus.graph.*`). When the orientation surface
    stops being honest about the codebase, agents drift back to N-tool
    composition — exactly what the cache was built to prevent.

    Lazy-rebuild note (2026-05-28): as of the lazy-on-query architecture
    (``noc_graph_cache._ensure_fresh_on_read``), the rebuild is NOT triggered
    eagerly on every commit. Instead, it fires automatically the first time a
    graph query tool (``noctus.graph.*`` / ``noctus.dev.noc_graph_status``) is
    called after the cache becomes stale. This keeper therefore surfaces
    *advisory* staleness — the graph will self-heal on the next query, not on
    the next commit. This is intentional: the ~5s rebuild cost is deferred to
    consumption time, never paid at commit time.
    (KB § PATTERNS/common/cache-as-agent-tool.md · cache-auto-freshness.md)

    Predicate:
      (a) cache exists → required for the lazy-rebuild leg to even fire.
      (b) cached `aggregate_source_sha` matches the live aggregate.

    Remediation: ``python mcp/noctusai/cli.py --refresh-noc-graph``
    (or simply run any ``noctus.graph.*`` query — lazy rebuild fires
    automatically on the next query when stale).

    Silent skip when:
      - `seed/` AND `mcp/` AND `products/` all absent (non-noc tree).
      - The `noc_graph_cache` module won't import (defensive).

    KB § PATTERNS/architect/noc-graph.md.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    # Non-noc tree?
    if not any((root / r).is_dir() for r in ("seed", "mcp", "products")):
        return issues
    cache = _resolve_cache_path("noc-graph", root)
    cache_file_label = _cache_label(cache, root)
    if not cache.exists():
        issues.append({
            "product": "<harness>", "file": cache_file_label,
            "issue": (
                "noc-graph cache missing — run "
                "`python mcp/noctusai/cli.py --refresh-noc-graph` "
                "(KB § PATTERNS/architect/noc-graph.md)"
            ),
            "severity": "warning",
            "symbol": "noc-graph-cache-missing",
        })
        return issues
    try:
        from .noc_graph_cache import compute_source_sha, get_cached_source_sha
    except Exception as e:  # noqa: BLE001
        issues.append({
            "product": "<harness>", "file": cache_file_label,
            "issue": (
                f"noc-graph cache module unreadable ({e}) — re-create via "
                "`--refresh-noc-graph`"
            ),
            "severity": "warning",
            "symbol": "noc-graph-cache-module-error",
        })
        return issues
    cached = get_cached_source_sha(root)
    live = compute_source_sha(root)
    if cached != live:
        issues.append({
            "product": "<harness>", "file": cache_file_label,
            "issue": (
                f"noc-graph cache STALE — cached={cached or '(none)'} "
                f"≠ live={live}; run `--refresh-noc-graph` "
                "(KB § PATTERNS/architect/noc-graph.md)"
            ),
            "severity": "warning",
            "symbol": "noc-graph-cache-stale",
        })
    return issues


def check_graph_extractor_corpus_sanity(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 keeper (2026-05-28): light floor-checks on the noc-graph corpus
    to surface a buggy extractor that produces a fresh-but-wrong cache.

    Closes the residual logic-correctness gap named in
    KB § PATTERNS/common/extractor-correctness-vs-mirror.md:
    the structural mirror (``check_noc_graph_cache_freshness``) guarantees
    ``source_sha`` invariant — up-to-date cache. THIS keeper checks the
    CONTENT of the cache is sane — that each extractor is still emitting
    the node/edge kinds it should. It is the always-on "did an extractor
    break?" gate; the full regression harness lives at
    ``mcp/noctusai/tests/test_graph_extractor_correctness.py``.

    Checks (all warning severity — advisory, not blocking):
      (a) Cache exists and is readable (precondition for the rest).
      (b) Node-kind floors: MODULE > 100, FUNCTION > 100, CLASS > 100,
          HARNESS_AGENT > 0, HARNESS_SKILL > 0, KB_PATTERN > 0.
      (c) Edge-kind floors: defined_in > 1000, kb_pointer > 50.
      (d) MCP-layer floors (read from live cache): semantic_neighbor > 20,
          guarded_by > 10.

    These are FLOOR-only checks — growth never fails them. Only a
    stop-emitting regression fails them (e.g. an extractor silently begins
    returning an empty list, or a kind-mapping rename breaks classification).

    Severity ``warning`` — same tier as ``check_noc_graph_cache_freshness``;
    the keeper surfaces the issue loudly but does not block a commit.

    Silent skip:
      - Non-noc tree (seed/mcp/products all absent).
      - Cache absent (freshness keeper already surfaces this; no double-warn).

    KB § PATTERNS/common/extractor-correctness-vs-mirror.md.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not any((root / r).is_dir() for r in ("seed", "mcp", "products")):
        return issues

    cache = _resolve_cache_path("noc-graph", root)
    if not cache.exists():
        # check_noc_graph_cache_freshness already fires for missing cache;
        # no double-warn from this keeper.
        return issues

    cache_file_label = _cache_label(cache, root)

    import sqlite3 as _sqlite3

    try:
        conn = _sqlite3.connect(str(cache))
        conn.row_factory = _sqlite3.Row
    except Exception as e:  # noqa: BLE001
        issues.append({
            "product": "<harness>", "file": cache_file_label,
            "issue": f"cannot open noc-graph cache for sanity check: {e}",
            "severity": "warning",
            "symbol": "graph-extractor-cache-open-error",
        })
        return issues

    def _node_count(kind: str) -> int:
        try:
            row = conn.execute(
                "SELECT count(*) FROM noc_graph_nodes WHERE kind = ?", (kind,)
            ).fetchone()
            return row[0] if row else 0
        except Exception:  # noqa: BLE001
            return 0

    def _edge_count(kind: str) -> int:
        try:
            row = conn.execute(
                "SELECT count(*) FROM noc_graph_edges WHERE kind = ?", (kind,)
            ).fetchone()
            return row[0] if row else 0
        except Exception:  # noqa: BLE001
            return 0

    try:
        # (b) Node-kind floors
        _NODE_FLOORS = [
            ("module", 100, "extract_code.py: MODULE nodes"),
            ("function", 100, "extract_code.py: FUNCTION nodes"),
            ("class", 100, "extract_code.py: CLASS nodes"),
            ("harness_agent", 1, "extract_harness.py: HARNESS_AGENT nodes"),
            ("harness_skill", 1, "extract_harness.py: HARNESS_SKILL nodes"),
            ("kb_pattern", 1, "extract_docs.py: KB_PATTERN nodes"),
        ]
        for kind, floor, label in _NODE_FLOORS:
            count = _node_count(kind)
            if count < floor:
                issues.append({
                    "product": "<harness>", "file": cache_file_label,
                    "issue": (
                        f"graph-extractor corpus sanity: {label} count {count} "
                        f"< floor {floor} — extractor may have stopped emitting "
                        f"this node kind "
                        f"(KB § PATTERNS/common/extractor-correctness-vs-mirror.md)"
                    ),
                    "severity": "warning",
                    "symbol": f"graph-extractor-node-floor-{kind}",
                })

        # (c) Edge-kind floors (build_graph layer)
        _EDGE_FLOORS = [
            ("defined_in", 1000, "extract_code.py: DEFINED_IN edges"),
            ("kb_pointer", 50, "extract_harness/docs: KB_POINTER edges"),
        ]
        for kind, floor, label in _EDGE_FLOORS:
            count = _edge_count(kind)
            if count < floor:
                issues.append({
                    "product": "<harness>", "file": cache_file_label,
                    "issue": (
                        f"graph-extractor corpus sanity: {label} count {count} "
                        f"< floor {floor} — extractor may have stopped emitting "
                        f"this edge kind "
                        f"(KB § PATTERNS/common/extractor-correctness-vs-mirror.md)"
                    ),
                    "severity": "warning",
                    "symbol": f"graph-extractor-edge-floor-{kind}",
                })

        # (d) MCP-layer edge floors
        _MCP_EDGE_FLOORS = [
            ("semantic_neighbor", 20, "MCP refresh: SEMANTIC_NEIGHBOR edges (embedding layer)"),
            ("guarded_by", 10, "MCP refresh: GUARDED_BY edges (keeper-patterns layer)"),
        ]
        for kind, floor, label in _MCP_EDGE_FLOORS:
            count = _edge_count(kind)
            if count < floor:
                issues.append({
                    "product": "<harness>", "file": cache_file_label,
                    "issue": (
                        f"graph-extractor corpus sanity: {label} count {count} "
                        f"< floor {floor} — MCP-refresh layer may have stopped "
                        f"injecting this edge kind. Run --refresh-noc-graph after "
                        f"refreshing the embedding/keeper-patterns caches "
                        f"(KB § PATTERNS/common/extractor-correctness-vs-mirror.md)"
                    ),
                    "severity": "warning",
                    "symbol": f"graph-extractor-edge-floor-{kind}",
                })
    finally:
        conn.close()

    return issues


def check_code_recurrence_drift(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 keeper (2026-05-26 post-close): surfaces when live code
    recurrence scan diverges from the latest ratified baseline by more
    than the drift threshold (default 3 NEW pairs).

    Sister of `check_kb_semantic_drift` — same advisory tier, applied to
    code recurrence findings instead of owns_kb validation findings.

    Severity ``warning``. Silent skip when:
      - `mcp/` is absent (non-noc tree).
      - The code-embeddings cache is absent (advisory layer not initialized).
      - `code_baseline` module unimportable (defensive).

    KB § CONTEXT/PATTERNS/common/code-recurrence-baseline.md.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not (root / "mcp").is_dir():
        return issues
    cache = _resolve_cache_path("code-embeddings", root)
    if not cache.exists():
        return issues
    try:
        from .code_baseline import diff as _diff, _DRIFT_THRESHOLD
    except Exception:  # noqa: BLE001 — defensive
        return issues
    try:
        d = _diff()
    except Exception:  # noqa: BLE001
        return issues
    if not d.get("ok"):
        return issues
    baseline_id = d.get("baseline_id")
    new_count = len(d.get("new_matches", []))
    if baseline_id is None:
        current = d.get("current_count", 0)
        # Only suggest ratification when the corpus actually has strong-signal
        # pairs — otherwise the noise tolerates absence of baseline.
        if current > 0:
            issues.append({
                "product": "<harness>",
                "file": "project-history/code-baselines/",
                "issue": (
                    f"code recurrence scan surfaces {current} pair(s) but "
                    f"no baseline ratified — call `noctus.dev.code_ratify` "
                    f"with a reason to baseline the current state; "
                    f"subsequent runs report only NEW pairs."
                ),
                "severity": "warning",
                "symbol": "code-baseline-missing",
            })
        return issues
    if new_count > _DRIFT_THRESHOLD:
        issues.append({
            "product": "<harness>",
            "file": "project-history/code-baselines/",
            "issue": (
                f"code recurrence scan shows {new_count} NEW pair(s) since "
                f"baseline `{baseline_id}` (threshold {_DRIFT_THRESHOLD}). "
                f"Review via `noctus.dev.code_baseline_diff`; fix or re-ratify "
                f"with `noctus.dev.code_ratify`."
            ),
            "severity": "warning",
            "symbol": "code-recurrence-drift",
        })
    if d.get("code_corpus_drifted"):
        issues.append({
            "product": "<harness>",
            "file": "project-history/code-baselines/",
            "issue": (
                f"Code corpus has shifted since baseline `{baseline_id}` was "
                f"ratified — resolved_matches in the diff may be artifacts "
                f"of changed code, not real fixes. Consider re-ratifying."
            ),
            "severity": "warning",
            "symbol": "code-baseline-corpus-drifted",
        })
    return issues


def check_skills_listed_in_router(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 keeper (2026-05-26, seven-way-sync): every skill directory
    under `.claude/skills/<name>/SKILL.md` MUST be referenced in CLAUDE.md
    §2's "Procedure skills" line. Drift class — agents query CLAUDE.md to
    discover available skills; a skill that exists but isn't listed is
    invisible to discovery.

    Predicates (severity ``high`` — methodology surface drift):
      (a) Every on-disk skill dir is mentioned in CLAUDE.md somewhere.
      (b) Every skill name in CLAUDE.md §2 has a real directory on disk.

    Silent skip when CLAUDE.md absent or .claude/skills/ absent.

    KB § PATTERNS/common/eight-way-sync.md.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    claude_md = root / "CLAUDE.md"
    skills_dir = root / ".claude" / "skills"
    if not claude_md.exists() or not skills_dir.is_dir():
        return issues
    try:
        text = claude_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return issues
    on_disk = sorted(
        p.name for p in skills_dir.iterdir()
        if p.is_dir() and (p / "SKILL.md").is_file()
    )
    # Leg (a): skill on disk not in CLAUDE.md.
    for skill in on_disk:
        if skill not in text:
            issues.append({
                "product": "<harness>", "file": f".claude/skills/{skill}/SKILL.md",
                "issue": (
                    f"skill `{skill}` exists on disk but is NOT referenced in "
                    f"CLAUDE.md (§2 'Procedure skills' line or §1 rule pointer). "
                    f"Add it to the router so agents can discover it."
                ),
                "severity": "high",
                "symbol": "skill-orphan-on-disk",
            })
    # Leg (b): name in §2 not on disk. Extract names matching `noc-<word>`
    # OR explicit ones from a known set. Heuristic: scan §2 line for
    # backtick-quoted tokens that LOOK like skills.
    import re
    # Find the §2 'Procedure skills' line, then every backtick-quoted
    # token on that line whose name looks skill-shaped (kebab-case).
    skills_listed: set[str] = set()
    for line in text.splitlines():
        if "Procedure skills" in line and ".claude/skills" in line:
            for match in re.findall(r"`([a-z][a-z0-9-]+)`", line):
                # Heuristic: kebab-case + not too short
                if "-" in match and len(match) >= 4:
                    skills_listed.add(match)
            break
    for name in sorted(skills_listed):
        # Allow non-skill helper names like "codify" (which is a command);
        # only flag if it LOOKS skill-shaped (noc-<...> OR explicit
        # skill-creator). Otherwise skip — heuristic noise tolerable.
        if not (name.startswith("noc-") or name == "skill-creator"):
            continue
        if name not in on_disk:
            issues.append({
                "product": "<harness>", "file": "CLAUDE.md",
                "issue": (
                    f"skill `{name}` listed in CLAUDE.md §2 but no "
                    f".claude/skills/{name}/ directory exists. Either "
                    f"create the skill or remove the stale reference."
                ),
                "severity": "high",
                "symbol": "skill-orphan-in-router",
            })
    return issues


def _run_composed_keeper(
    composition_name: str,
    sub_keepers: list[tuple[str, callable]],
) -> list[dict]:
    """Reusable composition-keeper runner.

    Given a list of `(sub_name, sub_callable)` tuples, runs each sub-keeper
    inside a try/except, decorates each returned issue with the
    `<composition_name>-<sub_name>::<orig-symbol>` prefix, and emits a
    warning-severity error-shaped issue if a sub-keeper raises.

    Extracted from `check_seven_way_sync` (now `check_eight_way_sync` —
    the first composition keeper) so future composition gates can reuse
    the loop + exception-tolerant decorator without copy-pasting.
    KB § PATTERNS/common/eight-way-sync.md.

    Args:
      composition_name: prefix string (e.g. "eight-way-sync", "all-cache-freshness").
      sub_keepers: list of (sub_name, no-arg callable returning list[dict]).

    Returns: list of issue dicts, every one tagged with the composition prefix.
    """
    issues: list[dict] = []
    for sub_name, sub_call in sub_keepers:
        try:
            sub_issues = sub_call() or []
        except Exception as e:  # noqa: BLE001
            sub_issues = [{
                "product": "<harness>", "file": f"<{composition_name}>",
                "issue": f"sub-keeper {sub_name!r} raised: {str(e)[:200]}",
                "severity": "warning",
                "symbol": f"{composition_name}-{sub_name}-error",
            }]
        for i in sub_issues:
            tagged = dict(i)
            tagged["symbol"] = f"{composition_name}-{sub_name}::{i.get('symbol', '?')}"
            issues.append(tagged)
    return issues


def check_commands_listed_in_router(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 keeper (2026-05-26 evening, seven-way-sync): every
    `.claude/commands/<name>.md` MUST be referenced in CLAUDE.md (§2 'Slash
    commands' line, primarily). Sister of `check_skills_listed_in_router`
    applied to the 7th first-class methodology surface.

    Predicates (severity ``high``):
      (a) Every on-disk command is mentioned in CLAUDE.md somewhere.
      (b) Every command name in CLAUDE.md §2 'Slash commands' line has a
          real `.claude/commands/<name>.md` on disk.

    Silent skip when CLAUDE.md absent or .claude/commands/ absent.

    KB § PATTERNS/common/eight-way-sync.md.
    """
    import re
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    claude_md = root / "CLAUDE.md"
    commands_dir = root / ".claude" / "commands"
    if not claude_md.exists() or not commands_dir.is_dir():
        return issues
    try:
        text = claude_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return issues
    on_disk = sorted(
        p.stem for p in commands_dir.iterdir()
        if p.is_file() and p.suffix == ".md"
    )
    # Leg (a): command on disk not in CLAUDE.md.
    for cmd in on_disk:
        if cmd not in text:
            issues.append({
                "product": "<harness>", "file": f".claude/commands/{cmd}.md",
                "issue": (
                    f"command `/{cmd}` exists on disk but is NOT referenced in "
                    f"CLAUDE.md (§2 'Slash commands' line). Add it so the "
                    f"router and agents can discover it."
                ),
                "severity": "high",
                "symbol": "command-orphan-on-disk",
            })
    # Leg (b): name in §2 'Slash commands' line not on disk.
    commands_listed: set[str] = set()
    for line in text.splitlines():
        if "Slash commands" in line and ".claude/commands" in line:
            # Match backtick-quoted `/foo` slash commands.
            for match in re.findall(r"`/([a-z][a-z0-9-]+)`", line):
                if len(match) >= 3:
                    commands_listed.add(match)
            break
    for name in sorted(commands_listed):
        if name not in on_disk:
            issues.append({
                "product": "<harness>", "file": "CLAUDE.md",
                "issue": (
                    f"command `/{name}` listed in CLAUDE.md §2 but no "
                    f".claude/commands/{name}.md file exists. Either "
                    f"create the command or remove the stale reference."
                ),
                "severity": "high",
                "symbol": "command-orphan-in-router",
            })
    return issues


def check_all_cache_freshness(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 composition keeper (2026-05-28, 7→8-way promotion):
    every keeper-mirror cache under `.claude/cache/` MUST be structurally
    in-sync with its source aggregate. Composes the 8 per-cache
    freshness keepers under one named gate so the 8th methodology
    surface (`.claude/cache/`, the live agent read path per
    `cache-as-agent-tool`) is enforced as a single block.

    Composes:
      - check_keeper_cache_freshness        (#1 keeper-patterns)
      - check_agent_context_cache_freshness (#2 agent-context)
      - check_auto_improvement_cache_freshness (#3 auto-improvement)
      - check_code_embeddings_cache_freshness (#4 code-embeddings)
      - check_noc_graph_cache_freshness     (#5 noc-graph)
      - check_kb_embeddings_cache_freshness (#6 kb-embeddings — NEW, extracted from cli.py inline)
      - check_corpus_embeddings_cache_freshness (#7 corpus-embeddings — NEW, extracted from cli.py inline)
      - check_memory_embeddings_cache_freshness (#8 memory-embeddings — NEW, extracted from cli.py inline)

    Each sub-keeper's issues are decorated with the
    `all-cache-freshness-<sub>::<orig-symbol>` prefix so the originating
    cache is traceable from the composition output.

    Severity is per-sub-keeper (warning for advisory caches; high for
    the methodology-critical ones). Structural-mirror freshness only —
    extractor-logic correctness is a separate test-surface concern
    (see KB § PATTERNS/common/extractor-correctness-vs-mirror.md).

    KB § PATTERNS/common/eight-way-sync.md.
    """
    return _run_composed_keeper("all-cache-freshness", [
        ("keeper-patterns", lambda: check_keeper_cache_freshness(repo_root)),
        ("agent-context", lambda: check_agent_context_cache_freshness(repo_root)),
        ("auto-improvement", lambda: check_auto_improvement_cache_freshness(repo_root)),
        ("code-embeddings", lambda: check_code_embeddings_cache_freshness(repo_root)),
        ("noc-graph", lambda: check_noc_graph_cache_freshness(repo_root)),
        ("kb-embeddings", lambda: check_kb_embeddings_cache_freshness(repo_root)),
        ("corpus-embeddings", lambda: check_corpus_embeddings_cache_freshness(repo_root)),
        ("memory-embeddings", lambda: check_memory_embeddings_cache_freshness(repo_root)),
    ])


# ── Cache-locking discipline gate (the helper, not raw WAL) ──────────────────
# Files exempt from the raw-WAL scan: the helper's home (defines + documents
# the pragma) and this detector's home (the needle + remediation message
# legitimately contain the literal). Neither opens a real cache connection
# that should route through the helper.
_LOCKING_PRAGMA_EXEMPT = (
    ("noctus", "dev", "cache_backend.py"),  # apply_locking_pragmas lives here
    ("noctus", "dev", "compliance.py"),     # this keeper's own source
)


def check_cache_uses_locking_helper(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 keeper (2026-05-30): every SQLite cache connection MUST apply the
    locking discipline via ``cache_backend.apply_locking_pragmas`` (WAL +
    busy_timeout), NOT a raw inline ``PRAGMA journal_mode=WAL``.

    A raw WAL pragma without the busy_timeout sibling is the writer-contention
    regression fixed 2026-05-30: WAL removes reader↔writer contention but does
    NOT serialize writer-vs-writer, so a contending writer raises
    ``database is locked``. The single helper pairs both pragmas; inlining WAL
    alone silently re-opens the gap (this is what guards the next new cache).

    Predicate: no ``journal_mode=WAL`` literal appears in
    ``mcp/noctusai/tools/**/*.py`` outside the exempt files (the helper home +
    this detector). Severity ``high`` — zero violations exist after the
    2026-05-30 centralization, so any hit is a genuine regression.

    Remediation: ``from .cache_backend import apply_locking_pragmas`` then
    ``apply_locking_pragmas(conn)`` right after ``sqlite3.connect(...)``.

    Silent skip on a non-noc tree. KB § PATTERNS/common/cache-locking-discipline.md.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    tools_dir = root / "mcp" / "noctusai" / "tools"
    if not tools_dir.is_dir():
        return issues
    exempt = {tools_dir.joinpath(*parts).resolve() for parts in _LOCKING_PRAGMA_EXEMPT}
    needle = "journal_mode=WAL"
    for py in sorted(tools_dir.rglob("*.py")):
        if py.resolve() in exempt:
            continue
        try:
            lines = py.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(lines, 1):
            if needle not in line or line.lstrip().startswith("#"):
                continue
            issues.append({
                "file": str(py.relative_to(root)),
                "line": lineno,
                "issue": (
                    f"raw `PRAGMA {needle}` at line {lineno} — call "
                    "`cache_backend.apply_locking_pragmas(conn)` instead so the "
                    "busy_timeout sibling is applied (WAL alone does not serialize "
                    "writer-vs-writer). KB § PATTERNS/common/cache-locking-discipline.md"
                ),
                "severity": "high",
                "symbol": "cache-raw-wal-without-helper",
            })
    return issues


def check_kb_embeddings_cache_freshness(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 keeper (2026-05-28, 7→8-way promotion): the kb-embeddings
    cache (`.claude/cache/kb-embeddings.sqlite`) MUST have per-doc
    `source_sha` matching the on-disk KB tree. Extracted from cli.py
    inline check into a real keeper so it can compose into
    `check_all_cache_freshness` (the 8-way surface #8 gate).

    Delegates to `check_kb_vector_canonical` which already implements the
    per-doc source_sha + orphan-row predicates. Severity warning
    (advisory discovery layer — markdown is canonical).

    KB § PATTERNS/common/kb-vector-search.md.
    """
    root = repo_root or REPO_ROOT
    if not (root / "KNOWLEDGE-BASE").is_dir():
        return []
    try:
        return check_kb_vector_canonical(root)
    except Exception as e:  # noqa: BLE001 — defensive
        return [{
            "product": "<harness>",
            "file": ".claude/cache/kb-embeddings.sqlite",
            "issue": f"kb-embeddings freshness check raised: {e}",
            "severity": "warning",
            "symbol": "kb-embeddings-cache-check-error",
        }]


def check_corpus_embeddings_cache_freshness(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 keeper (2026-05-28, 7→8-way promotion): the corpus-embeddings
    cache (`.claude/cache/corpus-embeddings.sqlite`) MUST mirror the
    aggregate sha of the heterogeneous in-repo corpus (CHANGELOG.md +
    templates/ + .claude/agents/*.md + .claude/skills/**/SKILL.md +
    PROJECT-HISTORY.md). Extracted from cli.py inline check.

    Severity warning. Silent skip when the cache is absent (corpus
    layer not initialized in this tree).

    KB § PATTERNS/common/corpus-embeddings.md.
    """
    root = repo_root or REPO_ROOT
    issues: list[dict] = []
    try:
        from .corpus_embeddings import CACHE_PATH, cache_source_sha
    except Exception:  # noqa: BLE001 — module absent / unimportable → silent skip
        return issues
    if not CACHE_PATH.exists():
        return issues  # corpus-embeddings layer not initialized — advisory silent
    try:
        live_sha = cache_source_sha()
    except Exception as e:  # noqa: BLE001
        issues.append({
            "product": "<harness>",
            "file": ".claude/cache/corpus-embeddings.sqlite",
            "issue": f"corpus-embeddings live source_sha compute failed: {e}",
            "severity": "warning",
            "symbol": "corpus-embeddings-cache-check-error",
        })
        return issues
    try:
        conn = sqlite3.connect(str(CACHE_PATH))
        cur = conn.execute("SELECT value FROM cache_meta WHERE key='source_sha'")
        row = cur.fetchone()
        conn.close()
        cached = row[0] if row else None
    except sqlite3.Error as e:
        issues.append({
            "product": "<harness>",
            "file": ".claude/cache/corpus-embeddings.sqlite",
            "issue": f"corpus-embeddings cache unreadable ({e}) — re-create via --refresh-corpus-embeddings",
            "severity": "warning",
            "symbol": "corpus-embeddings-cache-unreadable",
        })
        return issues
    if cached != live_sha:
        issues.append({
            "product": "<harness>",
            "file": ".claude/cache/corpus-embeddings.sqlite",
            "issue": (
                f"corpus-embeddings cache STALE — cached={cached or '(none)'} "
                f"≠ live={live_sha}; run `--refresh-corpus-embeddings`"
            ),
            "severity": "warning",
            "symbol": "corpus-embeddings-cache-stale",
        })
    return issues


def check_memory_embeddings_cache_freshness(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 keeper (2026-05-28, 7→8-way promotion): the memory-embeddings
    cache (`.claude/cache/memory-embeddings.sqlite`) MUST mirror the
    aggregate sha of the out-of-repo agent memory dir
    (`~/.claude/projects/<workspace>/memory/`). Extracted from cli.py
    inline check.

    Severity warning. Silent skip when:
      - the memory dir is unresolvable (no auto-memory configured yet)
      - the cache is absent (memory-embeddings layer not initialized)

    KB § PATTERNS/common/memory-embeddings.md.
    """
    issues: list[dict] = []
    try:
        from .memory_embeddings import CACHE_PATH, _resolve_memory_dir, cache_source_sha
    except Exception:  # noqa: BLE001 — module absent → silent skip
        return issues
    try:
        if _resolve_memory_dir() is None:
            return issues  # no memory dir resolvable — gate is no-op
    except Exception:  # noqa: BLE001
        return issues
    if not CACHE_PATH.exists():
        return issues  # memory-embeddings layer not initialized
    try:
        live_sha = cache_source_sha()
    except Exception as e:  # noqa: BLE001
        issues.append({
            "product": "<harness>",
            "file": ".claude/cache/memory-embeddings.sqlite",
            "issue": f"memory-embeddings live source_sha compute failed: {e}",
            "severity": "warning",
            "symbol": "memory-embeddings-cache-check-error",
        })
        return issues
    try:
        conn = sqlite3.connect(str(CACHE_PATH))
        cur = conn.execute("SELECT value FROM cache_meta WHERE key='source_sha'")
        row = cur.fetchone()
        conn.close()
        cached = row[0] if row else None
    except sqlite3.Error as e:
        issues.append({
            "product": "<harness>",
            "file": ".claude/cache/memory-embeddings.sqlite",
            "issue": f"memory-embeddings cache unreadable ({e}) — re-create via --refresh-memory-embeddings",
            "severity": "warning",
            "symbol": "memory-embeddings-cache-unreadable",
        })
        return issues
    if cached != live_sha:
        issues.append({
            "product": "<harness>",
            "file": ".claude/cache/memory-embeddings.sqlite",
            "issue": (
                f"memory-embeddings cache STALE — cached={cached or '(none)'} "
                f"≠ live={live_sha}; run `--refresh-memory-embeddings`"
            ),
            "severity": "warning",
            "symbol": "memory-embeddings-cache-stale",
        })
    return issues


def check_eight_way_sync(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 keeper (2026-05-28, promoted from check_seven_way_sync):
    the 8-way sync contract — eight first-class methodology surfaces stay
    aligned (CLAUDE.md / MEMORY.md / .claude/agents/ / KNOWLEDGE-BASE/ /
    CONTEXTUALIZE.md / .claude/skills/ / .claude/commands/ /
    .claude/cache/).

    The 8th surface (`.claude/cache/`) is the live agent read path per
    the `cache-as-agent-tool` rule — stale or wrong cache silently
    mis-answers at the consumption layer. Structural-mirror freshness
    is enforced here via `check_all_cache_freshness`; extractor-logic
    correctness is a separate test-surface concern (see KB § PATTERNS/
    common/extractor-correctness-vs-mirror.md).

    Composition keeper — re-runs the existing sub-keepers under one
    named gate via `_run_composed_keeper` so a single CLI flag surfaces
    all 8-way-sync mismatches in one pass. Severity ``high``
    (methodology drift breaks the agent-context contract).

    Composes:
      - check_kb_sync (#1 CLAUDE.md pointers + #4 KB INDEX)
      - check_contextualize_alignment (#5 fresh-agent ramp)
      - check_agent_kb_alignment (#3 agent owns_kb)
      - check_skills_listed_in_router (#6 skills ↔ router)
      - check_commands_listed_in_router (#7 commands ↔ router)
      - check_memory_md_index (#2 MEMORY.md discipline)
      - check_all_cache_freshness (#8 .claude/cache/ structural mirror, NEW)

    Each sub-keeper's issues are decorated with the
    `eight-way-sync-<sub>::<orig-symbol>` prefix so root-cause is traceable.

    KB § PATTERNS/common/eight-way-sync.md.
    """
    return _run_composed_keeper("eight-way-sync", [
        ("kb-sync", lambda: _check_kb_sync_for_six_way(repo_root)),
        ("contextualize", lambda: check_contextualize_alignment(repo_root)),
        ("agent-kb", lambda: check_agent_kb_alignment(repo_root)),
        ("skills-router", lambda: check_skills_listed_in_router(repo_root)),
        ("commands-router", lambda: check_commands_listed_in_router(repo_root)),
        ("memory-md-index", lambda: check_memory_md_index(repo_root)),
        ("cache-freshness", lambda: check_all_cache_freshness(repo_root)),
        # extractor logic-correctness leg: pairs with cache-freshness to close
        # the residual gap (fresh ≠ correct). Warning severity — same tier.
        # KB § PATTERNS/common/extractor-correctness-vs-mirror.md.
        ("extractor-sanity", lambda: check_graph_extractor_corpus_sanity(repo_root)),
    ])


# Back-compat aliases — old names retained so external callers (if any)
# keep working through the 7→8 transition. Will be removed in a future
# cleanup when no recurrence remains.
check_seven_way_sync = check_eight_way_sync
check_six_way_sync = check_eight_way_sync


def _check_kb_sync_for_six_way(repo_root: Path | None = None) -> list[dict]:
    """Adapter: invoke `tools.kb_sync.verify_kb_sync` (top-level module,
    NOT under tools.noctus.dev) and adapt its KBSyncResult into the
    standard {file, issue, severity, symbol} keeper shape.

    `verify_kb_sync` returns `{ok, exit_code, stdout, stderr}`. On
    failure, the stderr contains the diagnostic lines we surface.
    """
    issues: list[dict] = []
    try:
        from tools import kb_sync as _kbs
        result = _kbs.verify_kb_sync()
    except Exception as e:  # noqa: BLE001
        return [{
            "product": "<harness>", "file": "<kb-sync>",
            "issue": f"kb_sync.verify_kb_sync raised: {str(e)[:200]}",
            "severity": "warning",
            "symbol": "kb-sync-unavailable",
        }]
    if not result.get("ok", True):
        stderr = result.get("stderr") or result.get("stdout") or ""
        for raw_line in stderr.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            issues.append({
                "product": "<harness>", "file": "<kb-sync>",
                "issue": line,
                "severity": "high",
                "symbol": "kb-sync-issue",
            })
        if not issues:
            issues.append({
                "product": "<harness>", "file": "<kb-sync>",
                "issue": f"kb_sync verify failed (exit_code={result.get('exit_code')})",
                "severity": "high",
                "symbol": "kb-sync-failed",
            })
    return issues


def check_kb_semantic_drift(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 keeper (2026-05-26, W2-E6): surfaces when the live owns_kb
    vector validation diverges from the latest ratified baseline by more
    than the drift threshold (default 5 NEW findings).

    Sibling of `check_kb_vector_canonical` — same advisory tier, applied
    to a different layer of the signal stack:
      - `check_kb_vector_canonical` enforces the markdown-canonical contract
        (cache mirrors source-of-truth).
      - `check_kb_semantic_drift` enforces the ratified-canonical contract
        (current signal ≈ approved baseline; new drift gets reviewed, not
        silently accepted).

    Severity ``warning`` (NOT high) — ratification is human-reasoning, not
    auto-blocking. The keeper surfaces drift; the architect ratifies or
    fixes case-by-case.

    Silent skip when:
      - `KNOWLEDGE-BASE/` is absent (non-noc tree).
      - The kb-embeddings cache is absent (advisory layer not initialized).
      - No tools.noctus.dev.kb_baseline module (defensive).

    KB § CONTEXT/PATTERNS/common/vector-baseline.md.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not (root / "KNOWLEDGE-BASE").is_dir():
        return issues
    cache = _resolve_cache_path("kb-embeddings", root)
    if not cache.exists():
        return issues
    try:
        from .kb_baseline import diff as _diff, _DRIFT_THRESHOLD
    except Exception:  # noqa: BLE001 — defensive, never crash compliance
        return issues
    try:
        d = _diff()
    except Exception:  # noqa: BLE001
        return issues
    if not d.get("ok"):
        return issues
    baseline_id = d.get("baseline_id")
    new_count = len(d.get("new_findings", []))
    if baseline_id is None:
        # No baseline ratified. If there ARE current findings, suggest
        # ratification — silent skip when there are none.
        current = d.get("current_count", 0)
        if current > 0:
            issues.append({
                "product": "<harness>",
                "file": "project-history/kb-baselines/",
                "issue": (
                    f"owns_kb validation surfaces {current} finding(s) but "
                    f"no baseline ratified — call `noctus.dev.kb_ratify` "
                    f"with a reason to baseline the current state, then "
                    f"subsequent runs report only NEW drift."
                ),
                "severity": "warning",
                "symbol": "kb-baseline-missing",
            })
        return issues
    if new_count > _DRIFT_THRESHOLD:
        issues.append({
            "product": "<harness>",
            "file": "project-history/kb-baselines/",
            "issue": (
                f"owns_kb validation shows {new_count} NEW finding(s) since "
                f"baseline `{baseline_id}` (threshold {_DRIFT_THRESHOLD}). "
                f"Review via `noctus.dev.kb_baseline_diff`; fix or re-ratify "
                f"with `noctus.dev.kb_ratify`."
            ),
            "severity": "warning",
            "symbol": "kb-semantic-drift",
        })
    if d.get("kb_corpus_drifted"):
        issues.append({
            "product": "<harness>",
            "file": "project-history/kb-baselines/",
            "issue": (
                f"KB corpus has shifted since baseline `{baseline_id}` was "
                f"ratified — resolved_findings in the diff may be artifacts "
                f"of changed corpus, not real fixes. Consider re-ratifying "
                f"once the new corpus state is reviewed."
            ),
            "severity": "warning",
            "symbol": "kb-baseline-corpus-drifted",
        })
    return issues


def check_contextualize_alignment(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 keeper (2026-05-26, Phase B): CONTEXTUALIZE.md MUST remain a
    pointer-only fresh-agent read map. Sibling discipline to
    `check_claude_md_router` — same shape, applied to the fresh-agent
    onboarding ramp.

    Predicate:
      (a) File exists at repo root.
      (b) Line count ≤ `_CONTEXTUALIZE_LINE_CAP` — re-bloat is forbidden
          (the auto-loaded budget for fresh agents compounds).
      (c) Every entry in `_CONTEXTUALIZE_CANONICAL_CORES` appears as a
          pointer substring in the body — the curated list of docs a
          fresh agent MUST be routed to.

    Severity ``high`` (drift here ⇒ fresh agents arrive un-oriented and
    re-read the same docs you already trimmed; the codebase is the source
    of truth, and CONTEXTUALIZE.md is the front door).

    KB § PATTERNS/common/claude-md-router-discipline.md (sibling discipline).
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    ctx = root / "CONTEXTUALIZE.md"
    if not ctx.exists():
        issues.append({
            "product": "<harness>", "file": "CONTEXTUALIZE.md",
            "issue": (
                "CONTEXTUALIZE.md missing at repo root — fresh-agent read "
                "map is required (CLAUDE.md §0 routes here)."
            ),
            "severity": "high",
            "symbol": "contextualize-missing",
        })
        return issues
    try:
        text = ctx.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return issues
    line_count = len(text.splitlines())
    if line_count > _CONTEXTUALIZE_LINE_CAP:
        issues.append({
            "product": "<harness>", "file": "CONTEXTUALIZE.md",
            "issue": (
                f"CONTEXTUALIZE.md is {line_count} lines, cap is "
                f"{_CONTEXTUALIZE_LINE_CAP} — pointer-only discipline "
                "(CLAUDE.md §1 pattern). Trim inline bodies; push depth "
                "to the pointers."
            ),
            "severity": "high",
            "symbol": "contextualize-bloated",
        })
    for ref in _CONTEXTUALIZE_CANONICAL_CORES:
        if ref not in text:
            issues.append({
                "product": "<harness>", "file": "CONTEXTUALIZE.md",
                "issue": (
                    f"CONTEXTUALIZE.md missing a pointer to `{ref}` — "
                    "fresh agents must be routed to every canonical core. "
                    "Add a one-line pointer (rule + `→` pointer) OR remove "
                    "the entry from `_CONTEXTUALIZE_CANONICAL_CORES` in "
                    "compliance.py with a rationale."
                ),
                "severity": "high",
                "symbol": "contextualize-missing-canonical-core",
            })
    return issues


def check_auto_improvement_cache_freshness(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 keeper (2026-05-26, Phase B): the auto-improvement cache MUST
    mirror `project-history/auto-improvement.ndjson`. Third member of the
    keeper-mirror family (with keeper-pattern + agent-context). Same 3-leg
    contract — pre-commit eager refresh + lazy query-time rebuild + this
    loud freshness gate.

    The cache (`.claude/cache/auto-improvement.sqlite`, gitignored) is what
    the tech-lead / dispatched agents consult BEFORE editing a doc/agent
    (the **consult-before-editing** discipline — sibling of
    keeper-check-before-doc'ing). A stale cache means agents author from
    yesterday's surfaced patterns.

    Predicate: ``cache exists ∧ cache_meta.source_sha ≡ sha256(ndjson)``.
    Severity ``high``. Silent skip when the ndjson is absent (no surfaces
    logged yet — fresh repo).

    Remediation: ``python mcp/noctusai/cli.py --refresh-auto-improvement-cache``.

    KB § PATTERNS/common/scoped-auto-improvement.md.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    ledger = root / "project-history" / "auto-improvement.ndjson"
    if not ledger.exists():
        return issues  # nothing to mirror yet; fresh tree
    cache = _resolve_cache_path("auto-improvement", root)
    cache_file_label = _cache_label(cache, root)
    if not cache.exists():
        issues.append({
            "file": cache_file_label,
            "issue": (
                "auto-improvement cache missing — run "
                "`python mcp/noctusai/cli.py --refresh-auto-improvement-cache` "
                "(KB § PATTERNS/common/scoped-auto-improvement.md)"
            ),
            "severity": "high",
            "symbol": "auto-improvement-cache-missing",
        })
        return issues
    src_sha = hashlib.sha256(ledger.read_bytes()).hexdigest()
    try:
        conn = sqlite3.connect(str(cache))
        cur = conn.execute("SELECT value FROM cache_meta WHERE key='source_sha'")
        row = cur.fetchone()
        conn.close()
    except sqlite3.Error as e:
        issues.append({
            "file": cache_file_label,
            "issue": (
                f"auto-improvement cache unreadable ({e}) — re-create via "
                "`--refresh-auto-improvement-cache`"
            ),
            "severity": "high",
            "symbol": "auto-improvement-cache-unreadable",
        })
        return issues
    if not row or row[0] != src_sha:
        cached = row[0] if row else "(none)"
        issues.append({
            "file": cache_file_label,
            "issue": (
                f"auto-improvement cache STALE — cache.source_sha={cached[:12]} "
                f"≠ ndjson sha={src_sha[:12]}; run `--refresh-auto-improvement-cache`"
            ),
            "severity": "high",
            "symbol": "auto-improvement-cache-stale",
        })
    return issues


def check_codification_pipeline_health(
    repo_root: Path | None = None,
    *,
    s2_silence_days: int = 30,
    s3_silence_days: int = 60,
    s4_silence_days: int = 90,
) -> list[dict]:
    """Stage-4 meta-keeper (2026-05-26 evening): verify the codification
    pipeline (s1-emergent → s2-memory → s3-codified → s4-keeper) is FLOWING.

    The codification pipeline is itself an infrastructure dependency — if
    no s2/s3/s4 entries land for an extended window, drift accumulates
    quietly even though no individual keeper fires. This meta-keeper is
    the "is the inner loop alive?" check.

    Predicate: ``project-history/auto-improvement.ndjson`` contains a
    status=s2-memory entry within ``s2_silence_days`` AND a s3-codified
    within ``s3_silence_days`` AND a s4-keeper within ``s4_silence_days``.

    Severity ``warning`` (advisory — silence is a SIGNAL, not a hard
    failure; an architect may have just been on vacation).

    Remediation: review `noctus.dev.codification_radar` output for
    pending s2→s3 promotion candidates, and the s3 candidates' KB-doc
    + keeper-implementation status.

    Args:
      repo_root: optional override.
      s2_silence_days: max acceptable gap without ANY s2-memory entry.
      s3_silence_days: max acceptable gap without ANY s3-codified entry.
      s4_silence_days: max acceptable gap without ANY s4-keeper entry.

    KB § PATTERNS/common/scoped-auto-improvement.md (pipeline siblings) +
    `methodology-codification-pipeline` (the s1→s4 contract).
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    ledger = root / "project-history" / "auto-improvement.ndjson"
    if not ledger.exists():
        return issues  # fresh tree — pipeline can't be silent if it's brand-new

    import json as _json
    from datetime import date as _date, timedelta as _timedelta

    today = _date.today()
    thresholds = {
        "s2-memory": today - _timedelta(days=s2_silence_days),
        "s3-codified": today - _timedelta(days=s3_silence_days),
        "s4-keeper": today - _timedelta(days=s4_silence_days),
    }
    latest: dict[str, _date | None] = {k: None for k in thresholds}

    try:
        with ledger.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                status = entry.get("status", "")
                if status not in latest:
                    continue
                ts_str = entry.get("ts", "")
                try:
                    entry_date = _date.fromisoformat(ts_str[:10])
                except ValueError:
                    continue
                if latest[status] is None or entry_date > latest[status]:
                    latest[status] = entry_date
    except OSError as e:
        issues.append({
            "file": str(ledger.relative_to(root)),
            "issue": (
                f"codification pipeline ledger unreadable ({e}); "
                "investigate auto-improvement.ndjson permissions"
            ),
            "severity": "high",
            "symbol": "codification-pipeline-ledger-unreadable",
        })
        return issues

    for status, threshold in thresholds.items():
        last_seen = latest[status]
        days_label = {
            "s2-memory": s2_silence_days,
            "s3-codified": s3_silence_days,
            "s4-keeper": s4_silence_days,
        }[status]
        if last_seen is None:
            issues.append({
                "file": "project-history/auto-improvement.ndjson",
                "issue": (
                    f"codification pipeline: NO {status} entries ever logged "
                    f"in `auto-improvement.ndjson`. Pipeline stage may be "
                    f"silent. Review `noctus.dev.codification_radar` output. "
                    f"(KB § PATTERNS/common/scoped-auto-improvement.md)"
                ),
                "severity": "warning",
                "symbol": f"codification-pipeline-{status}-never",
            })
            continue
        if last_seen < threshold:
            gap_days = (today - last_seen).days
            issues.append({
                "file": "project-history/auto-improvement.ndjson",
                "issue": (
                    f"codification pipeline: last {status} entry was "
                    f"{gap_days} days ago ({last_seen.isoformat()}); "
                    f"threshold {days_label} days. Pipeline stage may be "
                    f"silent — review `noctus.dev.codification_radar` for "
                    f"pending promotion candidates."
                ),
                "severity": "warning",
                "symbol": f"codification-pipeline-{status}-silent",
            })
    return issues


# ─────────────────────────────────────────────────────────────────────────────
# `check_project_has_dispatch_routing` — Stage-4 keeper for the
# dispatch-with-PROJECT-and-notes rule (2026-05-26 evening). Every PROJECT.md
# with §6 phases must carry §4a Dispatch routing. Projects whose PROJECT.md
# first-commit predates the rule's birthday are grandfathered.
# KB § PATTERNS/common/dispatch-with-project-and-notes.md.
# ─────────────────────────────────────────────────────────────────────────────

DISPATCH_ROUTING_BIRTHDAY = "2026-05-26"
_DISPATCH_ROUTING_HEADER_RE = re.compile(r'^##\s+4a\b', re.MULTILINE)


def check_project_has_dispatch_routing(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 keeper (2026-05-26): every PROJECT.md with §6 phases must
    carry §4a Dispatch routing.

    Per `KB § PATTERNS/common/dispatch-with-project-and-notes.md`, every
    multi-slice project encodes its dispatch routing (slice→lens table ·
    codification expectations s1/s2/s3/s4 · routes-not-taken · notes
    contract) in §4a BEFORE any slice dispatches. Without §4a, engineers
    infer scope, surface drift-found, scope-expand silently, or skip
    codification stages — the exact "agents skip steps + get lost" pattern
    the user surfaced 2026-05-26 evening.

    Predicate: PROJECT.md contains `### Phase \\d+` (real phase) AND does
    NOT contain a `## 4a` header. Severity ``warning`` (advisory —
    grandfathered projects predating ``DISPATCH_ROUTING_BIRTHDAY`` are
    skipped via git first-commit date).

    **Grandfather rule.** A project whose PROJECT.md first-commit predates
    the birthday is skipped (it had no contract at its birthday). New
    projects (committed on/after the birthday) MUST carry §4a. If git is
    unreachable OR the file is untracked, we assume NEW and flag — better
    to surface than silently grandfather an untracked file.

    Remediation: add §4a per template (see `templates/PROJECT-TEMPLATE.md`
    §4a Dispatch routing — the canonical scaffold). Three sub-sections
    minimum: §4a.1 Slice→Lens · §4a.2 Codification expectations · §4a.3
    Routes-not-taken · §4a.4 Notes — surface + delivery.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    if not root.exists():
        return issues

    import subprocess
    from datetime import datetime as _dt

    try:
        birthday = _dt.fromisoformat(DISPATCH_ROUTING_BIRTHDAY).date()
    except ValueError:
        return issues  # config error; bail rather than half-fire

    for project_md in _find_all_project_md(root):
        content = project_md.read_text(encoding="utf-8")

        # Has real §6 Phase headers? (skip §5 architecture placeholder phases)
        if not _PHASE_HEADER_RE.search(content):
            continue

        # §4a present?
        if _DISPATCH_ROUTING_HEADER_RE.search(content):
            continue

        # Grandfather check via git first-commit date.
        try:
            relative = project_md.relative_to(root)
        except ValueError:
            continue
        try:
            result = subprocess.run(
                ["git", "log", "--diff-filter=A", "--format=%aI", "--follow",
                 "--", str(relative)],
                cwd=str(root), check=False, capture_output=True, text=True,
                timeout=5,
            )
            if result.returncode == 0:
                lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
                if lines:
                    # `--diff-filter=A` plus `--follow` should give the
                    # ADD event; the LAST line is the oldest add (renames
                    # preserved).
                    first_commit_iso = lines[-1]
                    try:
                        first_date = _dt.fromisoformat(first_commit_iso).date()
                        if first_date < birthday:
                            continue  # grandfathered
                    except ValueError:
                        pass  # unparseable date → fall through to flag
        except (subprocess.SubprocessError, OSError):
            pass  # git unreachable → fall through to flag (better signal)

        issues.append({
            "file": str(relative),
            "issue": (
                "PROJECT.md has §6 phases but no §4a Dispatch routing "
                "section. Add §4a per `templates/PROJECT-TEMPLATE.md` "
                "(slice→lens table · codification expectations s1-s4 · "
                "routes-not-taken · notes contract). "
                f"Grandfather: projects whose PROJECT.md first-commit "
                f"predates {DISPATCH_ROUTING_BIRTHDAY} are skipped "
                "automatically. "
                "KB § PATTERNS/common/dispatch-with-project-and-notes.md."
            ),
            "severity": "warning",
            "symbol": "project-missing-dispatch-routing",
        })
    return issues


# ─────────────────────────────────────────────────────────────────────────────
# Prod-deploy safety gates (added 2026-05-26 evening, cache-backend-portability
# Phase 3.4). These compose into the deploy safety net — see KB § PATTERNS/
# devops/prod-deploy-safety-gates.md.
# ─────────────────────────────────────────────────────────────────────────────


def check_prod_cache_reachable(repo_root: Path | None = None) -> list[dict]:
    """Verify the configured cache backend is reachable.

    Fires only when `NOCTUS_CACHE_BACKEND=postgres` (the prod shape).
    For sqlite (default/dev), this keeper is a NO-OP — local file is
    always 'reachable' by definition.

    Postgres reachability predicate: psycopg2 connects + simple query
    returns + pgvector extension is queryable. Severity ``high``.

    Remediation: verify `NOCTUS_CACHE_POSTGRES_DSN` is set; verify the
    pgvector container is running on the VPS; verify network reachability
    from this host.

    KB § PATTERNS/devops/prod-deploy-safety-gates.md.
    """
    import os
    backend = os.environ.get("NOCTUS_CACHE_BACKEND", "sqlite").lower()
    if backend != "postgres":
        return []  # NO-OP for sqlite default
    issues: list[dict] = []
    try:
        # Use the abstraction so this keeper composes with future backends.
        from .cache_backend_postgres import PostgresCacheBackend
    except ImportError as e:
        issues.append({
            "file": "mcp/noctusai/tools/noctus/dev/cache_backend_postgres.py",
            "issue": (
                f"NOCTUS_CACHE_BACKEND=postgres but PostgresCacheBackend "
                f"import failed: {e}. Verify psycopg2-binary + pgvector "
                "packages are installed."
            ),
            "severity": "high",
            "symbol": "prod-cache-backend-unimportable",
        })
        return issues
    try:
        backend_obj = PostgresCacheBackend()
        with backend_obj.connect("keeper-patterns") as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            row = cur.fetchone()
            if not row or row[0] != 1:
                issues.append({
                    "file": "prod-cache",
                    "issue": "SELECT 1 against prod cache returned unexpected result",
                    "severity": "high",
                    "symbol": "prod-cache-bad-response",
                })
            # Verify pgvector extension.
            try:
                cur.execute("SELECT 1 FROM pg_extension WHERE extname='vector'")
                if not cur.fetchone():
                    issues.append({
                        "file": "prod-cache",
                        "issue": (
                            "pgvector extension NOT installed in prod cache. "
                            "Run `noctus.dev.init_prod_cache_schema` to "
                            "bootstrap (requires superuser at init time)."
                        ),
                        "severity": "high",
                        "symbol": "prod-cache-pgvector-missing",
                    })
            except Exception:  # noqa: BLE001 — pg_extension query may fail in odd setups
                pass
            cur.close()
    except Exception as e:  # noqa: BLE001 — wide catch by design (connection failure modes)
        issues.append({
            "file": "prod-cache",
            "issue": (
                f"Prod cache unreachable: {str(e)[:200]}. "
                "Check NOCTUS_CACHE_POSTGRES_DSN + VPS container."
            ),
            "severity": "high",
            "symbol": "prod-cache-unreachable",
        })
    return issues


def check_cache_backend_env_matches_environment(
    repo_root: Path | None = None,
) -> list[dict]:
    """Advisory: `NOCTUS_CACHE_BACKEND` SHOULD match the environment.

    Heuristic environment detection:
      - `CI=true` env var OR `GITHUB_ACTIONS=true` ⇒ expect `postgres`
        (CI should share the prod cache; T3 of roadmap).
      - Running in a Docker container (presence of `/.dockerenv`) ⇒
        likely prod ⇒ expect `postgres`.
      - Otherwise ⇒ expect `sqlite` (local dev).

    Surfaces a WARNING (not high) when mismatch — manual override is
    legitimate (e.g., debugging prod backend locally).

    KB § PATTERNS/devops/prod-deploy-safety-gates.md.
    """
    import os
    issues: list[dict] = []
    configured = os.environ.get("NOCTUS_CACHE_BACKEND", "sqlite").lower()
    is_ci = (
        os.environ.get("CI", "").lower() == "true"
        or os.environ.get("GITHUB_ACTIONS", "").lower() == "true"
    )
    is_container = Path("/.dockerenv").exists()
    expected = "postgres" if (is_ci or is_container) else "sqlite"
    if configured != expected:
        env_label = "CI" if is_ci else ("container" if is_container else "local-dev")
        issues.append({
            "file": ".env or runtime-env",
            "issue": (
                f"NOCTUS_CACHE_BACKEND={configured} but {env_label} env "
                f"typically uses {expected}. Verify intentional override "
                "(e.g., debugging) — otherwise correct the env var."
            ),
            "severity": "warning",
            "symbol": "cache-backend-env-mismatch",
        })
    return issues


def check_drift_shield(repo_root: Path | None = None) -> list[dict]:
    """Pre-deploy DRIFT-SHIELD: surface OPEN auto-improvement entries
    touching files changed since last deploy.

    Predicate: the diff `origin/prod..origin/main` lists changed files;
    each file is matched against `auto-improvement.ndjson` entries with
    status `s1-emergent` / `s2-memory` / `s3-codified` (i.e., NOT yet
    `closed` and NOT yet `s4-keeper`). Surfacing reminds the architect
    to triage these BEFORE the deploy promotes the changes.

    Severity ``warning`` (advisory — won't block deploy; nudges review).

    KB § PATTERNS/devops/prod-deploy-safety-gates.md.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    ledger = root / "project-history" / "auto-improvement.ndjson"
    if not ledger.exists():
        return issues  # fresh tree
    # Diff prod..main; if either ref is missing locally, skip gracefully.
    import subprocess
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "origin/prod..origin/main"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return issues  # one of the refs is missing; not a deploy context
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return issues
    changed = {ln.strip() for ln in result.stdout.splitlines() if ln.strip()}
    if not changed:
        return issues
    # Walk the ledger; collect OPEN entries whose target is in changed.
    import json as _json
    open_statuses = {"s1-emergent", "s2-memory", "s3-codified"}
    hits: list[dict] = []
    try:
        with ledger.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                if entry.get("status") not in open_statuses:
                    continue
                target = entry.get("target", "")
                # target may be a path or a "code-recurrence:..." prefix.
                if target.startswith("code-recurrence:"):
                    continue
                # Match if any changed file substring-contains the target
                # OR target substring-contains any changed file.
                for f in changed:
                    if f in target or target in f:
                        hits.append({
                            "target": target,
                            "ts": entry.get("ts", ""),
                            "status": entry.get("status", ""),
                            "matched_file": f,
                        })
                        break
    except OSError:
        return issues
    if hits:
        # Compact preview — first 5 hits.
        preview = "; ".join(
            f"{h['target']}@{h['ts']}({h['status']})" for h in hits[:5]
        )
        suffix = f" (+{len(hits)-5} more)" if len(hits) > 5 else ""
        issues.append({
            "file": "project-history/auto-improvement.ndjson",
            "issue": (
                f"DRIFT-SHIELD: {len(hits)} OPEN drift/improvement "
                f"entry/entries touch files in this deploy. Review "
                f"BEFORE promoting. First 5: {preview}{suffix}"
            ),
            "severity": "warning",
            "symbol": "drift-shield-open-entries",
        })
    return issues


def check_slip_shield(repo_root: Path | None = None) -> list[dict]:
    """Pre-deploy SLIP-SHIELD: surface s2-memory entries with high
    promotion-readiness scores (codification candidates) that should be
    looked at BEFORE the deploy ships their target files.

    A "slip" = a pattern that emerged + hit memory but never got
    promoted to KB+keeper. Shipping changes touching those files
    without resolving the slip = scope-shrink slip.

    Reuses the codification_radar logic (s1/s2 → s3 promotion
    candidates) and filters to those whose target is in the
    `origin/prod..origin/main` diff.

    Severity ``warning`` (advisory).

    KB § PATTERNS/devops/prod-deploy-safety-gates.md.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    ledger = root / "project-history" / "auto-improvement.ndjson"
    if not ledger.exists():
        return issues
    import subprocess
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "origin/prod..origin/main"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return issues
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return issues
    changed = {ln.strip() for ln in result.stdout.splitlines() if ln.strip()}
    if not changed:
        return issues
    # Count s2-memory entries per target; >=2 entries on same target = slip.
    import json as _json
    from collections import Counter
    target_counts: Counter[str] = Counter()
    try:
        with ledger.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                if entry.get("status") != "s2-memory":
                    continue
                target = entry.get("target", "")
                if not target or target.startswith("code-recurrence:"):
                    continue
                target_counts[target] += 1
    except OSError:
        return issues
    slips = []
    for target, count in target_counts.items():
        if count < 2:
            continue
        for f in changed:
            if f in target or target in f:
                slips.append((target, count))
                break
    if slips:
        preview = "; ".join(f"{t}(×{c})" for t, c in slips[:3])
        suffix = f" (+{len(slips)-3} more)" if len(slips) > 3 else ""
        issues.append({
            "file": "project-history/auto-improvement.ndjson",
            "issue": (
                f"SLIP-SHIELD: {len(slips)} target(s) have ≥2 s2-memory "
                f"entries (codification slip candidates) touched by this "
                f"deploy. Consider promoting to s3/s4 before shipping. "
                f"First 3: {preview}{suffix}"
            ),
            "severity": "warning",
            "symbol": "slip-shield-codification-candidates",
        })
    return issues


def check_pre_deploy_gate(repo_root: Path | None = None) -> list[dict]:
    """Composite pre-deploy gate — runs all 4 safety keepers in sequence.

    Returns the UNION of issues from:
      - `check_prod_cache_reachable` (high — postgres-only)
      - `check_cache_backend_env_matches_environment` (warning)
      - `check_drift_shield` (warning)
      - `check_slip_shield` (warning)

    Use this as the single composite gate in CI / pre-deploy automation.

    KB § PATTERNS/devops/prod-deploy-safety-gates.md.
    """
    issues: list[dict] = []
    issues.extend(check_prod_cache_reachable(repo_root))
    issues.extend(check_cache_backend_env_matches_environment(repo_root))
    issues.extend(check_drift_shield(repo_root))
    issues.extend(check_slip_shield(repo_root))
    return issues


def _check_post_scaffold(
    slug: str,
    *,
    repo_root: Path | None = None,
    products_dir: Path | None = None,
) -> list[dict]:
    """Enforce the items currently listed in `scaffold_product`'s `next_steps`.

    Each returned dict has shape `{"check": str, "ok": bool, "error": str | None}`.
    Added 2026-05-04 (sh-yt-scaffold-polish Phase 3.4) so `validate_product`
    catches scaffolded-but-not-registered products. Mirrors the next_steps
    list in `mcp/noctusai/tools/noctus/dev/scaffold.py::scaffold_product`.

    Args:
        repo_root: Override for the repository root (test seam). Defaults
            to module-level :data:`REPO_ROOT`. Tests pass tmp_path-based
            roots so they can fixture start.sh / KB / vite factory in
            isolation.
        products_dir: Override for the ``products/`` root (test seam).
            Defaults to :data:`PRODUCTS_DIR`. Falls back to
            ``repo_root/products`` when only `repo_root` is supplied.

    Checks (4):
      1. Backend port wired in start.sh under the product's `--app-dir`.
      2. Frontend port wired in start.sh.
      3. Slug listed in `KB § CONTEXT/02-LANDSCAPE.md` Products table.
      4. INSERT INTO products row with the slug exists in any of the
         product's migration files (or core's bootstrap insert).

    (The former ``vite_factory_product_map`` check was retired 2026-05-20:
    the factory now derives its port map directly from ``start.sh PRODUCTS``
    at vite build time. Checks 1+2 already validate that registration, so
    the factory check became a redundant assertion against a literal that
    no longer exists. See KB § PATTERNS/architect/seed-canonical-defaults.md N=3.)
    """
    results: list[dict] = []

    base_repo_root = repo_root if repo_root is not None else REPO_ROOT
    if products_dir is not None:
        base_products_dir = products_dir
    elif repo_root is not None:
        base_products_dir = repo_root / "products"
    else:
        base_products_dir = PRODUCTS_DIR

    product_path = base_products_dir / slug

    # 1+2 — start.sh checks
    start_sh = base_repo_root / "start.sh"
    if not start_sh.exists():
        results.append({
            "check": "start_sh_exists",
            "ok": False,
            "error": f"start.sh missing at {start_sh}",
        })
        # Without start.sh we can't run port checks meaningfully.
        for c in ("backend_port_in_start_sh", "frontend_port_in_start_sh"):
            results.append({"check": c, "ok": False, "error": "start.sh missing"})
    else:
        sh_content = start_sh.read_text()
        # start.sh references products either via literal paths
        # (`products/<slug>/backend`) or via shell vars assigned to
        # `$ROOT_DIR/products/<slug>/backend`. Either form counts; we just
        # need to confirm a `--port N` appears within a reasonable window.
        backend_path = f"products/{slug}/backend"
        frontend_path = f"products/{slug}/frontend"

        def _has_port_near(needle: str) -> bool:
            """True iff `needle` appears in start.sh AND any `--port N`
            occurs within ±300 chars OR a shell variable assignment binds
            `needle` and that variable is referenced near a `--port`.
            """
            # Direct: literal path AND nearby --port.
            for m in re.finditer(re.escape(needle), sh_content):
                idx = m.start()
                window = sh_content[max(0, idx - 300): idx + 300]
                if re.search(r"--port\s+\d+", window):
                    return True
            # Indirect: a `VAR=...products/<slug>/(backend|frontend)`
            # assignment, then `$VAR` (or `"$VAR"`) referenced near --port.
            assign_re = re.compile(
                rf'(?P<var>[A-Z_][A-Z0-9_]*)="\$ROOT_DIR/{re.escape(needle)}"',
            )
            for m in assign_re.finditer(sh_content):
                var = m.group("var")
                # Find any usage of $var (with or without quotes) near --port.
                usage_re = re.compile(rf'"?\${re.escape(var)}"?')
                for u in usage_re.finditer(sh_content):
                    idx = u.start()
                    window = sh_content[max(0, idx - 300): idx + 300]
                    if re.search(r"--port\s+\d+", window):
                        return True
            return False

        if _has_port_near(backend_path):
            results.append({
                "check": "backend_port_in_start_sh",
                "ok": True,
                "error": None,
            })
        else:
            results.append({
                "check": "backend_port_in_start_sh",
                "ok": False,
                "error": (
                    f"start.sh has no `--port N` near `{backend_path}` — "
                    f"backend not wired into platform startup."
                ),
            })

        if _has_port_near(frontend_path):
            results.append({
                "check": "frontend_port_in_start_sh",
                "ok": True,
                "error": None,
            })
        else:
            results.append({
                "check": "frontend_port_in_start_sh",
                "ok": False,
                "error": (
                    f"start.sh has no `--port N` near `{frontend_path}` — "
                    f"frontend not wired into platform startup."
                ),
            })

    # 3 — KB § 02-LANDSCAPE.md product table
    landscape = base_repo_root / "KNOWLEDGE-BASE" / "CONTEXT" / "02-LANDSCAPE.md"
    if not landscape.exists():
        results.append({
            "check": "kb_landscape_table",
            "ok": False,
            "error": f"KB landscape file missing at {landscape}",
        })
    else:
        ls_content = landscape.read_text()
        if f"products/{slug}/" in ls_content or f"`products/{slug}/`" in ls_content:
            results.append({
                "check": "kb_landscape_table",
                "ok": True,
                "error": None,
            })
        else:
            results.append({
                "check": "kb_landscape_table",
                "ok": False,
                "error": (
                    f"KB § CONTEXT/02-LANDSCAPE.md Products table missing row "
                    f"for `products/{slug}/`."
                ),
            })

    # 4 — products-table INSERT row exists somewhere
    insert_pattern = re.compile(
        rf"INSERT\s+INTO\s+(?:public\.)?products[^\n]*\n(?:[^\n]*\n){{0,15}}[^\n]*'{re.escape(slug)}'",
        re.IGNORECASE,
    )
    found_insert = False
    insert_paths_searched = []
    for product_dir in base_products_dir.iterdir():
        if not product_dir.is_dir() or product_dir.name.startswith("."):
            continue
        migrations = product_dir / "backend" / "migrations"
        if not migrations.exists():
            continue
        for sql_file in migrations.glob("*.sql"):
            try:
                rel = str(sql_file.relative_to(base_repo_root))
            except ValueError:
                rel = str(sql_file)
            insert_paths_searched.append(rel)
            try:
                if insert_pattern.search(sql_file.read_text()):
                    found_insert = True
                    break
            except OSError:
                continue
        if found_insert:
            break
    if found_insert:
        results.append({
            "check": "products_table_insert",
            "ok": True,
            "error": None,
        })
    else:
        results.append({
            "check": "products_table_insert",
            "ok": False,
            "error": (
                f"No `INSERT INTO (public.)?products` migration row found with "
                f"slug '{slug}'. Searched {len(insert_paths_searched)} migration "
                f"file(s) under products/*/backend/migrations/."
            ),
        })

    # 5 — (retired) vite.config.factory.ts PRODUCT_MAP entry. The factory
    # now derives its frontend→backend port map from start.sh PRODUCTS at
    # build time (single source of truth, parsed by both the Python seed
    # lib and the TS factory). Checks 1+2 already validate that registration.
    # Per KB § PATTERNS/architect/seed-canonical-defaults.md (N=3 2026-05-20).

    return results


def validate_one_product(
    slug: str,
    *,
    repo_root: Path | None = None,
    products_dir: Path | None = None,
) -> dict:
    """Score one product against seed-compliance + path-reference rules.

    Migrated from `mcp/noctusai/server.py::_validate_one` during the FastMCP
    switch (mcp-server-fastmcp-switch Commit A) — was homeless dispatch-side
    logic; now lives next to the underlying detectors.

    Phase 3.4 (sh-yt-scaffold-polish, 2026-05-04) extended this with the
    `post_scaffold_checks` key: 5 binary registration checks mirroring
    `scaffold_product`'s next_steps. Existing `score`/`issues` shape preserved.
    Aggregate `post_scaffold_ok` is True only when every check passes.

    Args:
        repo_root, products_dir: Test seams forwarded to
            :func:`_check_post_scaffold`. The seed-compliance + path-reference
            checks still resolve from module-level :data:`PRODUCTS_DIR`
            (their refactor is not in scope for Phase 3.4); when callers
            supply `products_dir`, only the post-scaffold checks honor it.
    """
    base_products_dir = products_dir if products_dir is not None else (
        repo_root / "products" if repo_root is not None else PRODUCTS_DIR
    )
    path = base_products_dir / slug
    issues = check_seed_compliance(path) + check_path_references(path)
    penalties = {"critical": 25, "high": 10, "warning": 3}
    score = max(0, 100 - sum(penalties.get(i["severity"], 5) for i in issues))

    post_scaffold = _check_post_scaffold(
        slug, repo_root=repo_root, products_dir=products_dir,
    )
    post_ok = all(c["ok"] for c in post_scaffold)

    return {
        "product": slug,
        "score": score,
        "issues": issues,
        "post_scaffold_checks": post_scaffold,
        "post_scaffold_ok": post_ok,
    }


_OUTLINE_SUFFIXES = {".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
_OUTLINE_SKIP_DIRS = {
    "node_modules", ".venv", "venv", "dist", "build", "__pycache__",
    ".git", ".pytest_cache", ".mypy_cache", ".claude",
}
_OUTLINE_SCAN_ROOTS = ("products", "seed", "mcp", "scripts", "noctusai_lib")


def _iter_source_files(root: Path):
    """Yield every outline-eligible source file under the scan roots,
    skipping vendored / generated / worktree dirs."""
    for rel_root in _OUTLINE_SCAN_ROOTS:
        base = root / rel_root
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.suffix.lower() not in _OUTLINE_SUFFIXES:
                continue
            if any(part in _OUTLINE_SKIP_DIRS for part in p.parts):
                continue
            yield p


def check_files_outlined(
    paths: list[Path] | None = None, repo_root: Path | None = None
) -> list[dict]:
    """Keeper: every source file must be AST-outline-able so the
    AST-first / narrow-read tooling is always functional.

    Predicate: `noctus.dev.outline` on the file must not raise, must not
    return a dispatch `error`, and (Python) must not carry a
    `parse_error` (an `ast.parse` SyntaxError). A failing file is one
    the AST tooling cannot read — committing it degrades the platform's
    AST optimization, so the pre-commit hook blocks it.

    `paths=None` → full-platform scan (the `noctus.dev.scan_outlined`
    audit). `paths=[...]` → only those (the pre-commit staged-files
    gate). Return shape mirrors `check_phase_state_consistency`:
    `[{"file": rel, "issue": str, "severity": "high"}]`.
    """
    root = repo_root or REPO_ROOT
    from .outline import outline as _outline

    if paths is None:
        targets = list(_iter_source_files(root))
    else:
        targets = [Path(p) for p in paths]

    issues: list[dict] = []
    for fp in targets:
        if fp.suffix.lower() not in _OUTLINE_SUFFIXES or not fp.exists():
            continue
        if any(part in _OUTLINE_SKIP_DIRS for part in fp.parts):
            continue
        try:
            rel = str(fp.relative_to(root)) if fp.is_absolute() else str(fp)
        except ValueError:
            rel = str(fp)
        try:
            res = _outline(fp)
        except Exception as e:  # noqa: BLE001 — un-outline-able by definition
            issues.append({
                "file": rel,
                "issue": f"outline raised {type(e).__name__}: {e}",
                "severity": "high",
            })
            continue
        if res.get("error"):
            issues.append({
                "file": rel,
                "issue": f"not outline-able: {res['error']}",
                "severity": "high",
            })
            continue
        result = res.get("result") or {}
        pe = result.get("parse_error")
        if pe:
            issues.append({
                "file": rel,
                "issue": f"not AST-outline-able: {pe}",
                "severity": "high",
            })
    return issues


# ── auth-boundary-false-green (2026-05-29, canonical-test-runner) ──────────────
#
# Worked example that motivated this keeper:
#
#   `products/dev-team` omitted `"team"` from `standard_routers=[...]`, so the
#   seed Team-Management organ (`/api/team`) was never mounted. Four tests in
#   `TestDevTeamAPISurfaceAuthBoundary` asserted:
#
#       assert resp.status_code in (401, 404)
#
#   against paths the product never served. They PASSED via the 404 branch —
#   never exercising auth. The fix (commit 9d6bf79c) changed the assertions to
#   strict `== 401` against paths the product actually serves (e.g. `/api/run`).
#
# Why static analysis only:
#   A test-executing runner can NEVER catch this class of bug — the test is green
#   by construction. Only AST-based assertion-shape analysis can detect the
#   false-green escape hatch (the `in (401, 404)` disjunction).
#
# Predicate (tight — avoid false positives):
#   Flag ONLY tuples/sets/lists containing BOTH 401 AND 404. Disjunctions that
#   contain 401 with other codes (e.g. `in (401, 403)`) are legitimate auth
#   checks (both codes mean "unauthorized/forbidden"); `in (404, 500)` is a
#   legit resource-not-found check. The 401+404 combo is the ONLY shape that
#   confuses "auth works" with "route missing".
#
# Never silent: SyntaxError in a test file ⇒ warning finding (manual review
# needed) instead of silently ignoring the file.
#
# Self-verification: scan `products/dev-team/` on current fleet; expects 0
# findings because the fix (9d6bf79c) already tightened those assertions.


# Codes that, when disjoined with 401 in an auth-boundary assertion, form a
# false-green escape hatch — each can fire on an UNauthenticated request
# without the auth dependency running, so the test passes even if auth was
# removed:
#   404 — route absent (e.g. standard_routers omitted the router)
#   422 — request-body validation fires before/independent of the auth dep
# 403 is deliberately EXCLUDED: it is a second legitimate auth outcome
# (authenticated-but-forbidden), not a wiring/validation mask.
_AUTH_FALSE_GREEN_MASKABLE = frozenset({404, 422})


def _is_false_green_compare(node: ast.Compare) -> int | None:
    """Return the offending maskable code if `node` is a `<expr> in <collection>`
    disjunction that pairs 401 with a false-green mask (404 or 422); else None.

    The returned code lets the caller name the specific escape hatch in the
    finding message instead of hard-coding '404'.
    """
    if len(node.ops) != 1 or not isinstance(node.ops[0], ast.In):
        return None
    comparator = node.comparators[0]
    # Accepted collection forms: Tuple, Set, List of constants.
    if not isinstance(comparator, (ast.Tuple, ast.Set, ast.List)):
        return None
    constants = set()
    for elt in comparator.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, int):
            constants.add(elt.value)
    if 401 not in constants:
        return None
    masks = constants & _AUTH_FALSE_GREEN_MASKABLE
    # Prefer 404 in the message when both appear (clearest exemplar).
    if 404 in masks:
        return 404
    if 422 in masks:
        return 422
    return None


def check_auth_boundary_false_green(
    product_path: Path | None = None,
    products_dir: Path | None = None,
) -> list[dict]:
    """Keeper: auth-boundary tests must NOT pair 401 with a maskable code.

    `status_code in (401, <mask>)` is a **false-green escape hatch** — the test
    passes via the `<mask>` branch even when auth never fired, so it cannot
    detect an auth regression. Two maskable codes (see `_AUTH_FALSE_GREEN_MASKABLE`):
      - `404` — route absent (e.g. `standard_routers=[...]` omitted the router),
      - `422` — request-body validation fires before/independent of the auth dep.

    The fix in both cases is a strict `== 401`: for 404, hit a path the product
    actually serves; for 422, send a VALID body so validation passes and the
    auth dependency is what fires (worked example: `POST /api/run` with a valid
    `{"task": ...}` → strict 401, dev-team `test_e2e_flows.py`).

    `403` is deliberately NOT flagged (a second legitimate auth outcome —
    authenticated-but-forbidden), nor is a 404+500 resource-error range.

    **Scope:** `products/*/backend/tests/**/*.py`.

    **Never silent:** if a test file cannot be AST-parsed (SyntaxError or OS
    error), emits a `warning` finding requesting manual review rather than
    silently skipping the file.

    **Severity warning / advisory-only** — surfaces debt, never blocks a commit.
    Current fleet state: `dev-team` is clean (fixed in 9d6bf79c — replaced
    `in (401, 404)` with strict `== 401`); `personal-finance` carries a known
    backlog of `in (401, 422)` assertions surfaced here as warnings, tracked for
    remediation (the keeper exists precisely to make that backlog visible).

    Returns: list of `{"product": str, "file": str, "issue": str,
    "severity": "warning"}` dicts.
    """

    base = products_dir if products_dir is not None else PRODUCTS_DIR
    issues: list[dict] = []

    def _scan_product(ppath: Path) -> None:
        name = ppath.name
        tests_root = ppath / "backend" / "tests"
        if not tests_root.exists():
            return
        for test_file in sorted(tests_root.rglob("*.py")):
            try:
                source = test_file.read_text(encoding="utf-8")
            except OSError as e:
                issues.append({
                    "product": name,
                    "file": str(test_file.relative_to(base)),
                    "issue": (
                        f"Cannot read test file ({e}); "
                        "manual review needed for auth-boundary false-green check."
                    ),
                    "severity": "warning",
                })
                continue
            try:
                tree = ast.parse(source, filename=str(test_file))
            except SyntaxError as e:
                issues.append({
                    "product": name,
                    "file": str(test_file.relative_to(base)),
                    "issue": (
                        f"SyntaxError while parsing ({e}); "
                        "manual review needed for auth-boundary false-green check."
                    ),
                    "severity": "warning",
                })
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Compare):
                    continue
                mask = _is_false_green_compare(node)
                if mask is None:
                    continue
                # Build a compact snippet for the finding message.
                try:
                    snippet = ast.unparse(node)
                except Exception:  # noqa: BLE001 — unparse is best-effort
                    snippet = f"<line {node.lineno}>"
                why = {
                    404: ("the `404` alternative lets the test pass when the "
                          "route is absent (route not wired ⇒ 404 ⇒ test green, "
                          "but auth was never exercised)"),
                    422: ("the `422` alternative lets the test pass when body "
                          "validation fires before the auth dependency (invalid "
                          "body ⇒ 422 ⇒ test green even if auth was removed)"),
                }[mask]
                fix = (
                    "Fix: assert strict `== 401`"
                    + (" against a path the product actually serves"
                       if mask == 404
                       else " after sending a VALID request body so validation "
                            "passes and the auth dependency is what fires")
                    + f", or remove the `{mask}` branch."
                )
                issues.append({
                    "product": name,
                    "file": str(test_file.relative_to(base)),
                    "issue": (
                        f"Auth-boundary false-green at line {node.lineno}: "
                        f"`{snippet}` — {why}. {fix}"
                    ),
                    "severity": "warning",
                })

    if product_path is not None:
        _scan_product(product_path)
    else:
        for d in sorted(base.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                _scan_product(d)

    return issues


# ── dangling-remote-branches (branch-hygiene-prevention, P3.2, 2026-05-30) ──
# Advisory keeper: flag origin/* branches with unique content older than N days.
# Squash-aware via remote_branch_hygiene.classify_remote_branches (git-cherry +
# subject-on-dev). Never a commit-blocker (severity=warning). Surfaced in review
# + session-end so nothing hides for weeks.
# KB § CONTEXT/PATTERNS/common/learn-before-archive.md.

def check_dangling_remote_branches(
    threshold_days: float = 7.0,
    repo_root: Path | None = None,
) -> list[dict]:
    """Keeper: flag origin/* branches with unique content older than threshold_days.

    Consumes `remote_branch_hygiene.classify_remote_branches()`. Every `unique`
    remote branch whose `age_days > threshold_days` is surfaced as a warning finding
    with branch name, age, subject, and unique-commit count.

    NOT a commit-blocker — advisory, surfaced in review + session-end sweep.
    Never silent on git errors: if classification fails, emits a warning finding.

    Severity: warning for every qualifying unique-old branch.

    Returns: list of {product, file, issue, severity} dicts (keeper shape).
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    try:
        from tools.noctus.dev.remote_branch_hygiene import classify_remote_branches
        branches = classify_remote_branches(repo_root=root)
    except Exception as exc:  # noqa: BLE001
        logger.warning("check_dangling_remote_branches: classification failed: %s", exc)
        issues.append({
            "product": "<remotes>",
            "file": "origin/*",
            "issue": (
                f"remote branch classification failed ({exc!s:.200}). "
                "Run `noctus.dev.classify_remote_branches` manually to investigate."
            ),
            "severity": "warning",
        })
        return issues

    for entry in branches:
        if entry["verdict"] != "unique":
            continue
        age = entry.get("age_days")
        if age is None or age <= threshold_days:
            continue
        subject = entry.get("subject") or "<no subject>"
        unique_commits = entry.get("unique_commits")
        issues.append({
            "product": "<remotes>",
            "file": f"origin/{entry['branch']}",
            "issue": (
                f"Remote branch 'origin/{entry['branch']}' has unique content "
                f"({unique_commits} commit(s)) not on dev, aged {age:.0f} days "
                f"(subject: '{subject[:80]}'). "
                "Run `noctus.dev.salvage_before_delete` then "
                "`noctus.dev.delete_integrated_remote` after integration, "
                "OR integrate + delete. "
                "KB § CONTEXT/PATTERNS/common/learn-before-archive.md."
            ),
            "severity": "warning",
        })

    return issues


def register(server) -> None:
    desc_validate = "Check seed compliance for all products. Returns score 0-100."

    def _validate() -> dict:
        score, issues = check_all_products()
        return {"score": score, "issues": issues}

    server.tool(
        name="noctus.dev.validate",
        description=desc_validate,
    )(_validate)

    @server.tool(
        name="noctus.dev.validate_product",
        description="Check seed compliance for one product",
    )
    def _validate_product(slug: str) -> dict:
        return validate_one_product(slug)
