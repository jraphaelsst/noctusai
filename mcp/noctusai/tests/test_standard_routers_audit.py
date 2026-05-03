"""Tests for the standard_routers opt-in-vs-frontend-signal audit check.

Covers the two-directional drift detector introduced by the
`keeper-standard-routers-audit` project (2026-04-22).

Uses synthetic product trees in pytest's `tmp_path` — no dependency on the
live `products/` state. Tests are self-contained; each one builds the
exact shape it asserts against.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_standard_routers_audit,
    _parse_standard_routers,
)


# --- Helpers ----------------------------------------------------------------

def _mk_product(
    root: Path,
    name: str,
    main_content: str,
    frontend_files: dict[str, str] | None = None,
    router_files: list[str] | None = None,
) -> Path:
    """Build a minimal product tree under `root/<name>/`.

    `main_content` is the full text of `backend/app/main.py`.
    `frontend_files` maps relative paths under `frontend/src/` to file content.
    `router_files` is a list of bare filenames to create under
    `backend/app/routers/` (touched with empty content — only existence matters
    for self-provided detection).
    """
    product = root / name
    (product / "backend" / "app" / "routers").mkdir(parents=True, exist_ok=True)
    (product / "frontend" / "src").mkdir(parents=True, exist_ok=True)
    (product / "backend" / "app" / "main.py").write_text(main_content)
    for filename in router_files or []:
        (product / "backend" / "app" / "routers" / filename).write_text("# stub\n")
    for rel_path, content in (frontend_files or {}).items():
        target = product / "frontend" / "src" / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return product


_MAIN_TEMPLATE = '''\
from noctusai_seed import create_product_app
from app.config import settings
app = create_product_app(
    name="Test",
    schema="test",
    settings=settings,
    standard_routers={routers_literal},
)
'''


_MAIN_TEMPLATE_WITH_SELF_ROUTERS = '''\
from noctusai_seed import create_product_app
from app.config import settings
from app.routers import notifications, team
app = create_product_app(
    name="Test",
    schema="test",
    settings=settings,
    standard_routers={standard_literal},
    routers=[
        notifications.router,
        team.router,
    ],
)
'''


# --- _parse_standard_routers -------------------------------------------------

class TestParseStandardRouters:
    def test_found_simple_list(self):
        state, parsed = _parse_standard_routers(
            'create_product_app(standard_routers=["health", "team", "llm"])'
        )
        assert state == "found"
        assert parsed == {"health", "team", "llm"}

    def test_found_empty_list(self):
        state, parsed = _parse_standard_routers(
            'create_product_app(standard_routers=[])'
        )
        assert state == "found"
        assert parsed == set()

    def test_found_multiline(self):
        content = '''
        create_product_app(
            standard_routers=[
                "health",
                "notificacoes",
            ],
        )
        '''
        state, parsed = _parse_standard_routers(content)
        assert state == "found"
        assert parsed == {"health", "notificacoes"}

    def test_absent_when_not_mentioned(self):
        state, parsed = _parse_standard_routers(
            'create_product_app(name="X")'
        )
        assert state == "absent"
        assert parsed is None

    def test_unparseable_variable_reference(self):
        state, parsed = _parse_standard_routers(
            'ROUTERS = ["health"]\n'
            'create_product_app(standard_routers=ROUTERS)'
        )
        assert state == "unparseable"
        assert parsed is None


# --- check_standard_routers_audit -------------------------------------------

class TestStandardRoutersAudit:
    def test_matching_opt_in_and_signals_is_green(self, tmp_path: Path):
        """A product whose opt-in list matches its frontend signals produces
        zero findings — the happy path."""
        main = _MAIN_TEMPLATE.format(routers_literal='["health", "notificacoes", "team"]')
        product = _mk_product(
            tmp_path, "good",
            main_content=main,
            frontend_files={
                "App.tsx": 'import { NotificationBell } from "@noctusai/lib";',
                "pages/Equipe.tsx": 'api.get("/api/team")',
            },
        )
        assert check_standard_routers_audit(product) == []

    def test_under_grant_frontend_uses_but_backend_does_not_opt_in(self, tmp_path: Path):
        """Under-grant = critical. Frontend signal present, not in opt-in, not self-provided."""
        main = _MAIN_TEMPLATE.format(routers_literal='["health", "team"]')
        product = _mk_product(
            tmp_path, "under",
            main_content=main,
            frontend_files={
                "App.tsx": 'const Bell = NotificationBell;',  # signal present
                "pages/Equipe.tsx": 'api.get("/api/team")',
            },
        )
        issues = check_standard_routers_audit(product)
        assert len(issues) == 1
        assert issues[0]["severity"] == "critical"
        assert "notificacoes" in issues[0]["issue"]
        assert "404" in issues[0]["issue"]

    def test_over_grant_opted_in_without_frontend_signal(self, tmp_path: Path):
        """Over-grant = warning. In opt-in, no frontend signal found."""
        main = _MAIN_TEMPLATE.format(routers_literal='["health", "llm"]')
        product = _mk_product(
            tmp_path, "over",
            main_content=main,
            frontend_files={"App.tsx": "// no llm usage"},
        )
        issues = check_standard_routers_audit(product)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert "llm" in issues[0]["issue"]
        assert "dead router" in issues[0]["issue"].lower()

    def test_self_provided_suppresses_under_grant(self, tmp_path: Path):
        """Products that self-serve the router (wire their own via
        `routers=[<mod>.router]`) should NOT be flagged as under-grant —
        they provide the endpoint themselves. v2 AST-based detection requires
        the router to be wired, not just the file to exist (a stray file that
        isn't wired would 404 anyway)."""
        main = _MAIN_TEMPLATE_WITH_SELF_ROUTERS.format(standard_literal='["health"]')
        product = _mk_product(
            tmp_path, "self-provides",
            main_content=main,
            frontend_files={
                "App.tsx": 'const Bell = NotificationBell;',
                "pages/Team.tsx": 'api.get("/api/team")',
            },
            router_files=["notifications.py", "team.py"],  # core-style self-provision
        )
        assert check_standard_routers_audit(product) == []

    def test_self_provision_v2_requires_router_to_be_wired(self, tmp_path: Path):
        """v2 AST detection: a `team.py` file that exists but is NOT listed in
        `routers=[...]` does NOT count as self-provision. The frontend would
        still hit a runtime 404 because nothing is wired into the app."""
        # Has `routers=[]` (kwarg present, empty) — file exists but not wired.
        main = '''\
from noctusai_seed import create_product_app
app = create_product_app(name="X", schema="x", settings=None,
                         standard_routers=["health"], routers=[])
'''
        product = _mk_product(
            tmp_path, "unwired",
            main_content=main,
            frontend_files={"pages/Team.tsx": 'api.get("/api/team")'},
            router_files=["team.py"],  # file exists but NOT wired in routers=[]
        )
        issues = check_standard_routers_audit(product)
        assert len(issues) == 1
        assert issues[0]["severity"] == "critical"
        assert "team" in issues[0]["issue"]

    def test_self_provision_v2_falls_back_to_filename_when_unparseable(self, tmp_path: Path):
        """If `routers=...` is a variable reference (unparseable), the detector
        falls back to filename-based self-provision so it doesn't over-flag
        under-grants while the kwarg is already surfaced separately."""
        main = '''\
from noctusai_seed import create_product_app
from app.routers import team, notifications
PRODUCT_ROUTERS = [team.router, notifications.router]
app = create_product_app(name="X", schema="x", settings=None,
                         standard_routers=["health"], routers=PRODUCT_ROUTERS)
'''
        product = _mk_product(
            tmp_path, "variable-routers",
            main_content=main,
            frontend_files={
                "App.tsx": 'const Bell = NotificationBell;',
                "pages/Team.tsx": 'api.get("/api/team")',
            },
            router_files=["team.py", "notifications.py"],  # files on disk
        )
        # Filename-based fallback suppresses under-grant; empty issues.
        assert check_standard_routers_audit(product) == []

    def test_absent_standard_routers_flagged(self, tmp_path: Path):
        """A product calling create_product_app without standard_routers=[...]
        silently inherits `()` — opts out of everything. Flag explicitly."""
        main = '''
from noctusai_seed import create_product_app
app = create_product_app(name="X", schema="x", settings=None)
'''
        product = _mk_product(tmp_path, "absent", main_content=main)
        issues = check_standard_routers_audit(product)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"
        assert "without explicit standard_routers" in issues[0]["issue"]

    def test_unparseable_standard_routers_flagged(self, tmp_path: Path):
        """Variable-reference standard_routers emit a clear "manual audit"
        finding — NOT silently skipped (no-silent-errors rule)."""
        main = '''
from noctusai_seed import create_product_app
ROUTERS = ["health"]
app = create_product_app(name="X", schema="x", settings=None, standard_routers=ROUTERS)
'''
        product = _mk_product(tmp_path, "unparseable", main_content=main)
        issues = check_standard_routers_audit(product)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert "manual" in issues[0]["issue"].lower() or "cannot" in issues[0]["issue"].lower()

    def test_missing_main_py_returns_empty(self, tmp_path: Path):
        """No main.py → not in scope for this check. Empty list."""
        product = tmp_path / "nothing"
        product.mkdir()
        assert check_standard_routers_audit(product) == []

    def test_pre_migration_product_skipped(self, tmp_path: Path):
        """Products not yet migrated to create_product_app are handled by
        other checks. Skip silently (return []) — NOT an under-grant."""
        main = 'from fastapi import FastAPI\napp = FastAPI()\n'
        product = _mk_product(tmp_path, "legacy", main_content=main)
        assert check_standard_routers_audit(product) == []

    def test_health_only_opt_in_is_green_even_without_signal(self, tmp_path: Path):
        """`health` has no frontend signal pattern (it's universal / infra).
        Opting in without a signal must NOT trigger over-grant."""
        main = _MAIN_TEMPLATE.format(routers_literal='["health"]')
        product = _mk_product(
            tmp_path, "health-only",
            main_content=main,
            frontend_files={"App.tsx": "// minimal"},
        )
        assert check_standard_routers_audit(product) == []

    def test_llm_signal_matches_all_three_hook_variants(self, tmp_path: Path):
        """useLLMProviders / useLLMModels / useLLMPreferences all count."""
        for hook in ("useLLMProviders", "useLLMModels", "useLLMPreferences"):
            main = _MAIN_TEMPLATE.format(routers_literal='["health", "llm"]')
            product = _mk_product(
                tmp_path, f"llm-{hook}",
                main_content=main,
                frontend_files={"pages/LLM.tsx": f"const x = {hook}()"},
            )
            issues = check_standard_routers_audit(product)
            assert issues == [], f"Hook {hook} did not match: {issues}"

    def test_team_signal_requires_api_team_path(self, tmp_path: Path):
        """The team signal is the literal `/api/team` path in strings,
        not just the word "team" appearing somewhere."""
        main = _MAIN_TEMPLATE.format(routers_literal='["health"]')
        # Frontend uses the word "team" but not /api/team — should NOT match.
        product = _mk_product(
            tmp_path, "team-word-only",
            main_content=main,
            frontend_files={"App.tsx": "// the team dashboard (no api call)"},
        )
        assert check_standard_routers_audit(product) == []

    def test_multiple_findings_aggregate(self, tmp_path: Path):
        """Under-grant and over-grant can both fire in the same product."""
        # Opts into llm (no frontend signal) but is missing notificacoes
        # (frontend signal present) — should flag BOTH.
        main = _MAIN_TEMPLATE.format(routers_literal='["health", "llm"]')
        product = _mk_product(
            tmp_path, "mixed",
            main_content=main,
            frontend_files={
                "App.tsx": 'const Bell = NotificationBell;',  # under-grant
            },
        )
        issues = check_standard_routers_audit(product)
        assert len(issues) == 2
        severities = {i["severity"] for i in issues}
        assert severities == {"critical", "warning"}
