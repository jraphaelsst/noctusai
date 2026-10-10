"""ModuleRegistration startup/shutdown hooks + the platform-admin dep moved to app.dependencies."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import lifespan
from app import main as app_main
from app.dependencies import get_platform_admin_check, require_platform_admin


class TestModuleRegistrationHooks:
    def test_defaults_are_empty_lists_not_shared(self):
        a, b = app_main.ModuleRegistration(), app_main.ModuleRegistration()
        assert a.startup == [] and a.shutdown == []
        a.startup.append(object())
        assert b.startup == []

    def test_the_workers_are_hooked_through_modules(self):
        names = {h.__qualname__.split(".")[-1] for h in app_main.STARTUP_HOOKS}
        assert {"start_worker_hook", "start_pesquisa_extracao_hook", "startup_hook", "start_automation_worker_hook"} <= names
        # edicao_fotos + transcricoes + pesquisa_extracao + geracao_jobs (both its workers) + email_marketing automation
        assert len(app_main.STARTUP_HOOKS) == 5 and len(app_main.SHUTDOWN_HOOKS) == 5


class TestRunHooks:
    def test_runs_in_order_and_isolates_a_failure(self, caplog):
        order: list = []

        async def one():
            order.append(1)

        async def bad():
            order.append("bad")
            raise RuntimeError("boom")

        async def three():
            order.append(3)

        asyncio.run(lifespan.run_hooks([one, bad, three], "startup"))
        assert order == [1, "bad", 3]
        assert "bad failed" in caplog.text

    def test_shutdown_runs_hooks_in_reverse_order(self):
        order: list = []

        def mk(n):
            async def h():
                order.append(n)
            return h

        asyncio.run(lifespan.run_shutdown_hooks([mk("a"), mk("b"), mk("c")]))
        assert order == ["c", "b", "a"]


class TestRequirePlatformAdmin:
    def test_admin_passes_and_returns_the_auth_tuple(self):
        auth = (SimpleNamespace(id="u1"), "tok", "org")
        assert require_platform_admin(auth=auth, is_admin=lambda uid: uid == "u1") is auth

    @pytest.mark.parametrize("user_id,is_admin", [("u2", lambda u: False), ("", lambda u: True)])
    def test_non_admin_or_no_user_is_403(self, user_id, is_admin):
        with pytest.raises(HTTPException) as exc:
            require_platform_admin(auth=(SimpleNamespace(id=user_id), "t", "o"), is_admin=is_admin)
        assert exc.value.status_code == 403

    def test_transcricoes_still_re_exports_the_seam_it_is_overridden_by(self):
        from app.modules.transcricoes import deps

        assert deps.get_platform_admin_check is get_platform_admin_check
