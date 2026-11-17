"""EST-1 collision-class C3 declarations (estruturas-contract.md section 13): the new settings, the body-size
override, the job types, and the router registration -- declared up front so later slices only read them."""
from noctusai_lib.integrations.llm.models import MODELS

from app.config import settings
from app.modules.media_creation import register
from app.modules.media_creation.services import geracao_jobs as gj


class TestSettings:
    def test_every_new_setting_exists_with_a_finite_default(self):
        assert settings.corestudio_biblioteca_org_id == "" and settings.corestudio_biblioteca_user_id == ""
        assert settings.biblioteca_max_perfis_plataforma == 1000
        assert 0 < settings.estruturas_autodraft_dia < 10_000

    def test_the_estruturas_model_is_the_biblioteca_default_and_is_priced_in_the_seed_catalog(self):
        """An unregistered model is recorded as costing 0 and silently disarms `enforce_budget` (contract 14 item 4)."""
        assert settings.estruturas_ia_model == type(settings).model_fields["biblioteca_llm_model"].default
        assert any(m.id == settings.estruturas_ia_model and m.provider == "anthropic" for m in MODELS)


class TestJobTypes:
    def test_the_three_estruturas_job_types_are_declared_and_registrable(self):
        assert set(gj.ESTRUTURAS_JOB_TYPES) == {"estruturas.importar", "fluxo.finalizar_card", "estruturas.rascunho_do_viral"}
        assert set(gj.ESTRUTURAS_JOB_TYPES) <= set(gj.ALL_JOB_TYPES)
        assert set(gj.ESTRUTURAS_JOB_TYPES) <= set(gj.GERACAO_JOB_TYPES), "they ride the geracao worker"
        assert set(gj.GERACAO_JOB_TYPES).isdisjoint(gj.BIBLIOTECA_JOB_TYPES)

    def test_a_declared_type_is_registrable_and_a_typo_is_still_refused(self):
        import pytest

        async def handler(job): ...

        gj.clear_handlers()
        try:
            for t in gj.ESTRUTURAS_JOB_TYPES:
                gj.register_handler(t, handler)
                assert gj.get_handler(t) is handler
            with pytest.raises(ValueError):
                gj.register_handler("estruturas.importa", handler)
        finally:
            gj.clear_handlers()

    def test_the_geracao_worker_dispatches_them_dead_lettering_loudly_until_a_slice_registers_one(self):
        import anyio
        from types import SimpleNamespace

        from noctusai_lib.domain.jobs import FakeJobRepository

        async def go():
            repo = FakeJobRepository()
            gj.clear_handlers()
            worker = gj.build_geracao_worker(repo, SimpleNamespace(geracao_poll_seconds=2.0, geracao_lease_seconds=600.0))
            await repo.enqueue(type="estruturas.importar", payload={"importacao_id": "x"})
            await worker.run_once()
            return await repo.list_dead_letters()

        dead = anyio.run(go)
        assert len(dead) == 1 and dead[0].type == "estruturas.importar"


class TestRegistration:
    def test_both_routers_are_mounted_admin_first_and_the_read_router_after_it(self):
        from app.modules.media_creation.routers import estruturas, estruturas_admin

        routers = list(register().routers)
        assert estruturas_admin.router in routers and estruturas.router in routers
        assert routers.index(estruturas_admin.router) < routers.index(estruturas.router)
