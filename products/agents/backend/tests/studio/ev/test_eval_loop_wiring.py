"""The driver's production wiring: dependencies are resolved OUTSIDE a request through ``app.dependency_overrides`` (the product's real
seam bindings or a test's fakes), the context is the loop owner's, and the startup resume re-drives every active automatic loop."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Depends

from app.stores.studio_eval_loops import FakeLoopStore
from app.studio.eval_loop_driver import LoopDriver, get_driver, install_driver
from app.studio.eval_loop_wiring import ctx_do_dono, resolver_dep

ORG, AGENT, OWNER = uuid4(), uuid4(), uuid4()


def _app(**overrides):
    return SimpleNamespace(dependency_overrides=overrides)


def test_resolver_follows_nested_depends_and_honours_overrides():
    def base():
        return "real"

    def dependente(b=Depends(base)):
        return f"dep:{b}"

    assert resolver_dep(_app(), dependente) == "dep:real"
    assert resolver_dep(SimpleNamespace(dependency_overrides={base: lambda: "fake"}), dependente) == "dep:fake"


def test_resolver_takes_what_only_a_request_carries_from_explicit_and_refuses_what_it_cannot_resolve():
    def precisa_de_ctx(ctx, x=Depends(lambda: 1)):
        return (ctx, x)

    assert resolver_dep(_app(), precisa_de_ctx, {"ctx": "dono"}) == ("dono", 1)
    with pytest.raises(LookupError):
        resolver_dep(_app(), precisa_de_ctx)

    async def assincrona():
        return 1

    with pytest.raises(TypeError):
        resolver_dep(_app(), assincrona)


def test_the_drivers_context_is_the_loop_owners_human_user_in_the_loops_org():
    loops = FakeLoopStore()
    rec = loops.create_loop(ORG, AGENT, agente_chave="agente-base", suite="comportamento", rodadas_planejadas=3, alvo=0.9, piso=0.8,
                            orcamento_usd=5.0, started_by=OWNER, modo="automatico")
    ctx = ctx_do_dono(rec)
    assert (ctx.org_id, ctx.user_id, ctx.caller_kind, ctx.api_token_id) == (ORG, OWNER, "user", None)


def test_startup_resume_schedules_only_active_automatic_loops_and_records_the_resume():
    class Svc:
        def __init__(self, store):
            self.store = store

    loops = FakeLoopStore()
    auto = loops.create_loop(ORG, AGENT, agente_chave="a", suite="comportamento", rodadas_planejadas=3, alvo=0.9, piso=0.8,
                             orcamento_usd=5.0, started_by=OWNER, modo="automatico")
    loops.create_loop(ORG, uuid4(), agente_chave="b", suite="comportamento", rodadas_planejadas=3, alvo=0.9, piso=0.8,
                      orcamento_usd=5.0, started_by=uuid4(), modo="manual")
    abertos: list = []

    async def iniciar(rec):  # the booking seam: records which loops the driver was asked to open a round for
        abertos.append(rec.id)
        return uuid4()

    driver = LoopDriver(servico=lambda: Svc(loops), iniciar=iniciar, ler_resumo=lambda rec, rid: None)

    async def retomar():
        n = await driver.retomar_todos()
        await asyncio.gather(*list(driver._tasks))
        return n

    assert asyncio.run(retomar()) == 1
    assert abertos == [auto.id]  # only the active AUTOMATIC loop was re-driven
    assert [e["evento"] for e in loops.eventos] == ["driver_retomado"] and loops.eventos[0]["detalhe"]["motivo"] == "reinicio"


def test_the_registry_holds_the_installed_driver_and_can_be_cleared():
    install_driver(None)
    assert get_driver() is None
    d = LoopDriver(servico=lambda: None, iniciar=None, ler_resumo=None)  # type: ignore[arg-type]
    install_driver(d)
    assert get_driver() is d
    install_driver(None)
