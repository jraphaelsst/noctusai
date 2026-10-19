"""Lais wave 4 -- Reengajamento (contract 6): the stale guard, the business-hours reschedule, the
<= 3 / active-needs-attempt rules, the never-replied path, the regua chain + cold-lead hook, and the
whole thing through the real lead turn (`process_lead_batch` arms the timers, `run_reengajamento_turn`
sends the message).

Seams are the Fakes the seed and the product ship: mock DB, `FakeJobRepository`, `FakeAgentsClient`,
`FakeWahaClient`. The turn runner of the pure job tests is the handler's own injection seam
(`run_turn=`), a recorder -- nothing of ours is patched. No personal data in fixtures.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from noctusai_lib.domain.jobs import FakeJobRepository
from noctusai_lib.domain.jobs.repo import RescheduleLater
from noctusai_lib.primitives.exceptions import AppException

from app.services import lais_contatos_service as contatos
from app.services import lais_reengajamento_service as svc
from app.services.lais_lead_turn_service import process_lead_batch, run_reengajamento_turn

from tests.support.lais_world import CONNECTION_ID, LEAD_CHAT, ORG_ID as ORG, OTHER_ORG_ID, World, buffer_lead

SP = svc.FUSO
# 2026-10-15 is a Thursday; every instant below is explicit so no test depends on the clock.
MANHA = datetime(2026, 10, 15, 10, 0, tzinfo=SP).astimezone(timezone.utc)      # 10:00 SP, inside 08-20
NOITE = datetime(2026, 10, 15, 22, 30, tzinfo=SP).astimezone(timezone.utc)     # 22:30 SP, outside
MADRUGADA = datetime(2026, 10, 15, 3, 0, tzinfo=SP).astimezone(timezone.utc)   # 03:00 SP, outside
FIM = datetime(2026, 10, 15, 20, 0, tzinfo=SP).astimezone(timezone.utc)        # 20:00 SP sharp, outside


@pytest.fixture(autouse=True)
def _public_url(monkeypatch):
    monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://sw.example.test")


@pytest.fixture
def world() -> World:
    w = World()
    w.seed_connection()
    w.seed_chat()
    for t in (svc.T_CONFIG, svc.T_REGUAS, svc.T_TENTATIVAS):
        w.sw.set_table_data(t, [])
    return w


class Turnos:
    """The `run_turn` injection seam: records every re-engagement turn, answers `enviou`."""

    def __init__(self, enviou: bool = True):
        self.enviou = enviou
        self.chamadas: list[tuple[str, dict, str]] = []

    async def __call__(self, deps, connection, chat_id, contato, estado_extra, marker_id) -> bool:
        self.chamadas.append((chat_id, dict(estado_extra), marker_id))
        return self.enviou


def _contato(world: World, *, interagiu: bool = True, **over) -> dict:
    c = contatos.obter_ou_criar_contato(world.sw, org_id=ORG, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT)
    if interagiu:
        c, _ = contatos.registrar_inbound(world.sw, c)
    contatos.atualizar_contato(world.sw, c["id"], over)
    return world.contato()


async def _armar(world: World, repo: FakeJobRepository, contato: dict, agora=MANHA) -> list[str]:
    return await svc.agendar_apos_outbound(world.sw, repo, ORG, contato, agora=agora)


def _cfg(world: World, **valores):
    svc.salvar_config(world.sw, ORG, valores)


def _regua(world: World, *, ativa=True, compra=True, aluguel=True, tentativas=((1, 1, "dias"),)) -> dict:
    r = svc.criar_regua(world.sw, ORG, nome="Régua padrão", compra=compra, aluguel=aluguel)
    for ordem, valor, unidade in tentativas:
        svc.criar_tentativa(world.sw, ORG, r["id"], {"ordem": ordem, "espera_valor": valor, "espera_unidade": unidade,
                                                      "texto": f"Oi, tudo bem? ({ordem})"})
    if ativa:
        svc.ativar_regua(world.sw, ORG, r["id"])
    return svc.obter_regua(world.sw, ORG, r["id"])


def _jobs(repo: FakeJobRepository, tipo: str | None = None):
    todos = list(repo._jobs.values())
    return [j for j in todos if tipo is None or j.type == tipo]


def _handlers(world: World, repo, turnos):
    return svc.handlers(deps_factory=lambda: world.deps(), repo=repo, run_turn=turnos)


@pytest.mark.asyncio
class TestAgendamento:
    async def test_each_enabled_tier_is_enqueued_with_the_current_gen_and_its_own_delay(self, world):
        _cfg(world, minutos_ativo=True, minutos_intervalo=15, horas_ativo=True, horas_intervalo=3)
        c = _contato(world)
        repo = FakeJobRepository()
        assert await _armar(world, repo, c) == [svc.JOB_MINUTOS, svc.JOB_HORAS]
        mins, horas = _jobs(repo, svc.JOB_MINUTOS)[0], _jobs(repo, svc.JOB_HORAS)[0]
        assert mins.payload["gen"] == horas.payload["gen"] == c["gen"] == 1
        assert mins.payload["chat_key"] == f"lead:{CONNECTION_ID}:{LEAD_CHAT}" and mins.payload["org_id"] == ORG
        assert mins.scheduled_for == MANHA + timedelta(minutes=15) and horas.scheduled_for == MANHA + timedelta(hours=3)

    async def test_nothing_is_enqueued_when_both_tiers_are_off_and_no_regua_serves(self, world):
        assert await _armar(world, FakeJobRepository(), _contato(world)) == []

    async def test_no_default_tier_starts_the_regua_straight_after_the_outbound(self, world):
        _regua(world, tentativas=((1, 2, "horas"),))
        repo = FakeJobRepository()
        assert await _armar(world, repo, _contato(world)) == [svc.JOB_REGUA]
        assert _jobs(repo)[0].scheduled_for == MANHA + timedelta(hours=2)

    async def test_an_encerrado_contato_never_arms_a_timer(self, world):
        _cfg(world, minutos_ativo=True, horas_ativo=True)
        c = _contato(world, encerrado_at=MANHA.isoformat())
        repo = FakeJobRepository()
        assert await _armar(world, repo, c) == [] and _jobs(repo) == []

    async def test_the_same_outbound_twice_does_not_double_the_timers_but_a_new_gen_does(self, world):
        _cfg(world, minutos_ativo=True)
        c = _contato(world)
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        await _armar(world, repo, c)
        assert len(_jobs(repo)) == 1
        c2, _ = contatos.registrar_inbound(world.sw, c)
        await _armar(world, repo, c2)
        assert len(_jobs(repo)) == 2

    async def test_a_regua_serves_only_the_operacao_it_is_flagged_for(self, world):
        _regua(world, compra=False, aluguel=True)
        assert svc.escolher_regua(world.sw, ORG, _contato(world, operacao="compra")) is None
        assert svc.escolher_regua(world.sw, ORG, _contato(world, operacao="aluguel")) is not None
        assert svc.escolher_regua(world.sw, ORG, _contato(world, operacao=None)) is not None  # unknown: any


@pytest.mark.asyncio
class TestStaleGuard:
    async def test_an_inbound_after_the_enqueue_makes_every_pending_job_obsolete(self, world):
        _cfg(world, minutos_ativo=True, horas_ativo=True)
        c = _contato(world)
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        contatos.registrar_inbound(world.sw, world.contato())  # the lead answered
        turnos = Turnos()
        for j in _jobs(repo):
            assert await _executar(world, repo, turnos, j, MANHA) == "obsoleto"
        assert turnos.chamadas == []

    @pytest.mark.parametrize("como", ["encerrar", "pausa_ou_handoff"])
    async def test_never_after_encerrar_pause_or_handoff(self, world, como):
        _cfg(world, minutos_ativo=True)
        c = _contato(world)
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        if como == "encerrar":
            contatos.bump_gen(world.sw, c["id"], encerrado_at=MANHA.isoformat())
        else:
            contatos.bump_gen(world.sw, c["id"])  # pause / handoff bump gen (foundation)
        turnos = Turnos()
        assert await _executar(world, repo, turnos, _jobs(repo)[0], MANHA) == "obsoleto"
        assert turnos.chamadas == []

    async def test_encerrado_without_a_gen_bump_is_still_refused(self, world):
        _cfg(world, minutos_ativo=True)
        c = _contato(world)
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        contatos.atualizar_contato(world.sw, c["id"], {"encerrado_at": MANHA.isoformat()})
        turnos = Turnos()
        assert await _executar(world, repo, turnos, _jobs(repo)[0], MANHA) == "encerrado"
        assert turnos.chamadas == []

    async def test_a_chat_paused_by_a_human_is_refused_even_with_the_same_gen(self, world):
        _cfg(world, minutos_ativo=True)
        c = _contato(world)
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        world.sw.table("whatsapp_chats").update({"agente_pausado": True}).eq("connection_id", CONNECTION_ID).execute()
        turnos = Turnos()
        assert await _executar(world, repo, turnos, _jobs(repo)[0], MANHA) == "pausado"
        assert turnos.chamadas == []

    async def test_julia_switched_off_for_the_connection_is_refused(self, world):
        _cfg(world, minutos_ativo=True)
        c = _contato(world)
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        world.sw.table("whatsapp_connections").update({"agente_leads_ativo": False}).eq("id", CONNECTION_ID).execute()
        turnos = Turnos()
        assert await _executar(world, repo, turnos, _jobs(repo)[0], MANHA) == "sem_conexao"

    async def test_a_live_job_sends_and_writes_the_timeline_event(self, world):
        _cfg(world, minutos_ativo=True)
        c = _contato(world)
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        turnos = Turnos()
        assert await _executar(world, repo, turnos, _jobs(repo)[0], MANHA) == "enviado"
        assert turnos.chamadas[0][1] == {"reengajamento": "minutos"}
        ev = world.rows("lais_eventos", tipo="reengajamento")
        assert len(ev) == 1 and ev[0]["payload"]["texto"] == "Lead não respondeu mais. Julia reativou a conversa"
        assert ev[0]["contato_id"] == c["id"]

    async def test_a_silent_turn_writes_no_timeline_event(self, world):
        _cfg(world, minutos_ativo=True)
        c = _contato(world)
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        assert await _executar(world, repo, Turnos(enviou=False), _jobs(repo)[0], MANHA) == "silencio"
        assert world.rows("lais_eventos", tipo="reengajamento") == []


async def _executar(world: World, repo, turnos, job, agora) -> str:
    fn = svc.executar_tentativa if job.type == svc.JOB_REGUA else svc.executar_default
    return await fn(job, deps=world.deps(), repo=repo, run_turn=turnos, agora=agora)


@pytest.mark.asyncio
class TestHorarioComercial:
    @pytest.mark.parametrize("quando", [NOITE, MADRUGADA, FIM])
    async def test_the_hours_tier_outside_08_20_reschedules_to_the_next_0800(self, world, quando):
        _cfg(world, horas_ativo=True)
        c = _contato(world)
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        turnos = Turnos()
        with pytest.raises(RescheduleLater) as exc:
            await _executar(world, repo, turnos, _jobs(repo)[0], quando)
        alvo = quando + timedelta(seconds=exc.value.delay_s)
        local = alvo.astimezone(SP)
        assert (local.hour, local.minute) == (8, 0) and local > quando.astimezone(SP)
        assert turnos.chamadas == []

    async def test_before_0800_reschedules_to_the_same_day_and_after_1959_to_the_next(self, world):
        assert svc.segundos_ate_abertura(MADRUGADA) == 5 * 3600
        assert svc.segundos_ate_abertura(NOITE) == (9 * 3600 + 30 * 60)

    @pytest.mark.parametrize("hora,dentro", [(7, False), (8, True), (19, True), (20, False)])
    async def test_the_window_is_0800_inclusive_to_2000_exclusive(self, hora, dentro):
        assert svc.dentro_do_horario(datetime(2026, 10, 15, hora, 0, tzinfo=SP).astimezone(timezone.utc)) is dentro

    async def test_the_hours_tier_inside_the_window_runs(self, world):
        _cfg(world, horas_ativo=True)
        c = _contato(world)
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        turnos = Turnos()
        assert await _executar(world, repo, turnos, _jobs(repo)[0], MANHA) == "enviado"
        assert turnos.chamadas[0][1] == {"reengajamento": "horas"}

    async def test_the_minutes_tier_runs_at_any_hour(self, world):
        _cfg(world, minutos_ativo=True)
        c = _contato(world)
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        turnos = Turnos()
        assert await _executar(world, repo, turnos, _jobs(repo)[0], MADRUGADA) == "enviado"


@pytest.mark.asyncio
class TestNuncaRespondeu:
    async def test_the_hours_tier_also_covers_a_lead_who_never_replied(self, world):
        _cfg(world, horas_ativo=True)
        c = _contato(world, interagiu=False)
        assert c["ultimo_inbound_at"] is None
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        turnos = Turnos()
        assert await _executar(world, repo, turnos, _jobs(repo)[0], MANHA) == "enviado"
        assert len(turnos.chamadas) == 1

    async def test_the_minutes_tier_and_the_regua_do_not(self, world):
        _cfg(world, minutos_ativo=True)
        c = _contato(world, interagiu=False)
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        turnos = Turnos()
        assert await _executar(world, repo, turnos, _jobs(repo, svc.JOB_MINUTOS)[0], MANHA) == "sem_interacao"
        _regua(world)
        repo2 = FakeJobRepository()
        c2 = world.contato()
        r = svc.escolher_regua(world.sw, ORG, c2)
        await svc._enfileirar_tentativa(repo2, world.sw, ORG, c2, r, r["tentativas"][0], base=MANHA)
        assert await _executar(world, repo2, turnos, _jobs(repo2)[0], MANHA) == "sem_interacao"
        assert turnos.chamadas == []


@pytest.mark.asyncio
class TestReguaHorario:
    @pytest.mark.parametrize("quando", [NOITE, MADRUGADA])
    async def test_a_regua_attempt_outside_08_20_reschedules_to_the_next_0800(self, world, quando):
        _regua(world)
        c = _contato(world)
        r = svc.escolher_regua(world.sw, ORG, c)
        repo = FakeJobRepository()
        await svc._enfileirar_tentativa(repo, world.sw, ORG, c, r, r["tentativas"][0], base=quando)
        turnos = Turnos()
        with pytest.raises(RescheduleLater) as exc:
            await _executar(world, repo, turnos, _jobs(repo)[0], quando)
        local = (quando + timedelta(seconds=exc.value.delay_s)).astimezone(SP)
        assert (local.hour, local.minute) == (8, 0)
        assert turnos.chamadas == []


@pytest.fixture
def frio():
    chamadas: list[tuple[str, str]] = []
    svc.registrar_lead_frio(lambda client, org, contato: chamadas.append((str(org), str(contato["id"]))))
    yield chamadas
    svc.registrar_lead_frio(svc.lead_frio_padrao)


@pytest.mark.asyncio
class TestReguaChain:
    async def test_the_regua_starts_after_the_last_default_tier(self, world, frio):
        _cfg(world, minutos_ativo=True, horas_ativo=True)
        _regua(world, tentativas=((1, 1, "dias"),))
        c = _contato(world)
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        turnos = Turnos()
        await _executar(world, repo, turnos, _jobs(repo, svc.JOB_MINUTOS)[0], MANHA)
        assert _jobs(repo, svc.JOB_REGUA) == []  # minutes is not the last default tier
        await _executar(world, repo, turnos, _jobs(repo, svc.JOB_HORAS)[0], MANHA)
        reg = _jobs(repo, svc.JOB_REGUA)
        assert len(reg) == 1 and reg[0].scheduled_for == MANHA + timedelta(days=1) and reg[0].payload["ordem"] == 1

    async def test_minutes_only_makes_minutes_the_last_default_tier(self, world, frio):
        _cfg(world, minutos_ativo=True)
        _regua(world)
        c = _contato(world)
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        await _executar(world, repo, Turnos(), _jobs(repo, svc.JOB_MINUTOS)[0], MANHA)
        assert len(_jobs(repo, svc.JOB_REGUA)) == 1

    async def test_attempts_chain_in_order_with_their_own_waits_and_the_text_is_flagged_for_rewrite(self, world, frio):
        _regua(world, tentativas=((1, 1, "dias"), (2, 3, "horas"), (3, 30, "minutos")))
        c = _contato(world)
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        turnos = Turnos()
        j1 = _jobs(repo, svc.JOB_REGUA)[0]
        assert await _executar(world, repo, turnos, j1, MANHA) == "enviado"
        estado = turnos.chamadas[0][1]
        assert estado["reengajamento"] == "regua" and estado["reescrever"] is True and estado["texto_base"] == "Oi, tudo bem? (1)"
        j2 = [j for j in _jobs(repo, svc.JOB_REGUA) if j.payload["ordem"] == 2][0]
        assert j2.scheduled_for == MANHA + timedelta(hours=3)
        await _executar(world, repo, turnos, j2, MANHA)
        j3 = [j for j in _jobs(repo, svc.JOB_REGUA) if j.payload["ordem"] == 3][0]
        assert j3.scheduled_for == MANHA + timedelta(minutes=30)
        assert frio == []
        await _executar(world, repo, turnos, j3, MANHA)
        assert frio == [(ORG, c["id"])]  # after the LAST attempt: the cold-lead hook
        assert len(_jobs(repo, svc.JOB_REGUA)) == 3

    async def test_an_inactive_attempt_is_skipped_in_the_chain(self, world, frio):
        r = _regua(world, tentativas=((1, 1, "dias"), (2, 1, "dias"), (3, 1, "dias")))
        svc.atualizar_tentativa(world.sw, ORG, r["id"], r["tentativas"][1]["id"], {"ativa": False})
        c = _contato(world)
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        await _executar(world, repo, Turnos(), _jobs(repo, svc.JOB_REGUA)[0], MANHA)
        assert sorted(j.payload["ordem"] for j in _jobs(repo, svc.JOB_REGUA)) == [1, 3]

    async def test_a_template_attempt_is_skipped_with_regua_sem_transporte_and_the_chain_continues(self, world, frio):
        r = svc.criar_regua(world.sw, ORG, nome="Com template", compra=True, aluguel=True)
        t1 = svc.criar_tentativa(world.sw, ORG, r["id"], {"espera_valor": 1, "espera_unidade": "dias",
                                                           "template_id": "00000000-0000-4000-8000-0000000000d1"})
        svc.criar_tentativa(world.sw, ORG, r["id"], {"espera_valor": 1, "espera_unidade": "dias", "texto": "Olá!"})
        svc.ativar_regua(world.sw, ORG, r["id"])
        c = _contato(world)
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        turnos = Turnos()
        assert await _executar(world, repo, turnos, _jobs(repo, svc.JOB_REGUA)[0], MANHA) == "regua_sem_transporte"
        assert turnos.chamadas == []
        ev = world.rows("lais_eventos", tipo="regua_sem_transporte")
        assert len(ev) == 1 and ev[0]["payload"]["template_id"] == t1["template_id"]
        assert [j.payload["ordem"] for j in _jobs(repo, svc.JOB_REGUA)] == [1, 2]

    async def test_a_deactivated_or_deleted_regua_stops_its_pending_attempt(self, world, frio):
        r = _regua(world)
        c = _contato(world)
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        turnos = Turnos()
        svc.desativar_regua(world.sw, ORG, r["id"])
        assert await _executar(world, repo, turnos, _jobs(repo)[0], MANHA) == "regua_inativa"
        svc.apagar_regua(world.sw, ORG, r["id"])
        assert await _executar(world, repo, turnos, _jobs(repo)[0], MANHA) == "regua_removida"
        assert turnos.chamadas == [] and frio == []

    async def test_no_regua_after_the_default_tiers_means_a_cold_lead(self, world, frio):
        _cfg(world, horas_ativo=True)
        c = _contato(world)
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        await _executar(world, repo, Turnos(), _jobs(repo)[0], MANHA)
        assert frio == [(ORG, c["id"])] and _jobs(repo, svc.JOB_REGUA) == []

    async def test_the_default_cold_lead_hook_is_a_harmless_noop(self, world):
        _cfg(world, horas_ativo=True)
        c = _contato(world)
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        assert await _executar(world, repo, Turnos(), _jobs(repo)[0], MANHA) == "enviado"

    async def test_a_failing_cold_lead_hook_is_logged_and_never_raised(self, world, caplog):
        svc.registrar_lead_frio(lambda *_a: (_ for _ in ()).throw(RuntimeError("boom")))
        try:
            _cfg(world, horas_ativo=True)
            c = _contato(world)
            repo = FakeJobRepository()
            await _armar(world, repo, c)
            with caplog.at_level("ERROR"):
                assert await _executar(world, repo, Turnos(), _jobs(repo)[0], MANHA) == "enviado"
            assert "cold-lead hook failed" in caplog.text
        finally:
            svc.registrar_lead_frio(svc.lead_frio_padrao)


class TestRegrasDaRegua:
    def test_at_most_three_attempts_and_the_fourth_is_a_409(self, world):
        r = svc.criar_regua(world.sw, ORG, nome="R", compra=True, aluguel=False)
        for i in range(3):
            svc.criar_tentativa(world.sw, ORG, r["id"], {"espera_valor": 1, "texto": f"t{i}"})
        with pytest.raises(AppException) as exc:
            svc.criar_tentativa(world.sw, ORG, r["id"], {"espera_valor": 1, "texto": "t4"})
        assert exc.value.status_code == 409 and exc.value.code == "limite_tentativas"
        assert sorted(t["ordem"] for t in svc.obter_regua(world.sw, ORG, r["id"])["tentativas"]) == [1, 2, 3]

    def test_ordem_is_the_next_free_slot_and_a_taken_one_is_refused(self, world):
        r = svc.criar_regua(world.sw, ORG, nome="R", compra=True, aluguel=False)
        svc.criar_tentativa(world.sw, ORG, r["id"], {"ordem": 2, "espera_valor": 1, "texto": "a"})
        assert svc.criar_tentativa(world.sw, ORG, r["id"], {"espera_valor": 1, "texto": "b"})["ordem"] == 1
        with pytest.raises(AppException) as exc:
            svc.criar_tentativa(world.sw, ORG, r["id"], {"ordem": 2, "espera_valor": 1, "texto": "c"})
        assert exc.value.code == "ordem_ocupada"

    def test_activating_a_regua_without_an_active_attempt_is_a_409(self, world):
        r = svc.criar_regua(world.sw, ORG, nome="R", compra=True, aluguel=False)
        with pytest.raises(AppException) as exc:
            svc.ativar_regua(world.sw, ORG, r["id"])
        assert exc.value.status_code == 409 and exc.value.code == "regua_sem_tentativa"
        # an INACTIVE attempt does not count either
        svc.criar_tentativa(world.sw, ORG, r["id"], {"espera_valor": 1, "texto": "x", "ativa": False})
        with pytest.raises(AppException) as exc:
            svc.ativar_regua(world.sw, ORG, r["id"])
        assert exc.value.code == "regua_sem_tentativa"
        assert svc.obter_regua(world.sw, ORG, r["id"])["ativa"] is False

    def test_a_new_regua_is_inactive_and_activates_once_it_has_an_active_attempt(self, world):
        r = svc.criar_regua(world.sw, ORG, nome="R", compra=True, aluguel=False)
        assert r["ativa"] is False
        svc.criar_tentativa(world.sw, ORG, r["id"], {"espera_valor": 1, "texto": "x"})
        assert svc.ativar_regua(world.sw, ORG, r["id"])["ativa"] is True
        assert svc.desativar_regua(world.sw, ORG, r["id"])["ativa"] is False

    def test_the_last_active_attempt_of_an_active_regua_cannot_be_deactivated_or_deleted(self, world):
        r = _regua(world)
        tid = r["tentativas"][0]["id"]
        for acao in (lambda: svc.atualizar_tentativa(world.sw, ORG, r["id"], tid, {"ativa": False}),
                     lambda: svc.apagar_tentativa(world.sw, ORG, r["id"], tid)):
            with pytest.raises(AppException) as exc:
                acao()
            assert exc.value.status_code == 409 and exc.value.code == "ultima_tentativa_ativa"
        assert len(svc.obter_regua(world.sw, ORG, r["id"])["tentativas"]) == 1

    def test_with_a_second_active_attempt_or_an_inactive_regua_it_is_allowed(self, world):
        r = _regua(world, tentativas=((1, 1, "dias"), (2, 1, "dias")))
        svc.apagar_tentativa(world.sw, ORG, r["id"], r["tentativas"][0]["id"])
        svc.desativar_regua(world.sw, ORG, r["id"])
        svc.apagar_tentativa(world.sw, ORG, r["id"], r["tentativas"][1]["id"])
        assert svc.obter_regua(world.sw, ORG, r["id"])["tentativas"] == []

    def test_setting_texto_clears_the_template_and_vice_versa(self, world):
        r = svc.criar_regua(world.sw, ORG, nome="R", compra=True, aluguel=False)
        t = svc.criar_tentativa(world.sw, ORG, r["id"], {"espera_valor": 1, "texto": "x"})
        out = svc.atualizar_tentativa(world.sw, ORG, r["id"], t["id"], {"template_id": "00000000-0000-4000-8000-0000000000d1"})
        assert out["texto"] is None and out["template_id"]
        out = svc.atualizar_tentativa(world.sw, ORG, r["id"], t["id"], {"texto": "de novo"})
        assert out["texto"] == "de novo" and out["template_id"] is None

    def test_another_orgs_regua_is_a_404_and_its_attempts_are_untouched(self, world):
        r = _regua(world)
        for acao in (lambda: svc.obter_regua(world.sw, OTHER_ORG_ID, r["id"]),
                     lambda: svc.ativar_regua(world.sw, OTHER_ORG_ID, r["id"]),
                     lambda: svc.apagar_regua(world.sw, OTHER_ORG_ID, r["id"]),
                     lambda: svc.criar_tentativa(world.sw, OTHER_ORG_ID, r["id"], {"espera_valor": 1, "texto": "x"})):
            with pytest.raises(AppException) as exc:
                acao()
            assert exc.value.status_code == 404
        assert svc.listar_reguas(world.sw, OTHER_ORG_ID) == [] and len(svc.listar_reguas(world.sw, ORG)) == 1

    def test_config_defaults_then_upserts_only_what_is_sent(self, world):
        assert svc.obter_config(world.sw, ORG) == svc.CONFIG_PADRAO
        svc.salvar_config(world.sw, ORG, {"minutos_ativo": True, "minutos_intervalo": 20})
        out = svc.salvar_config(world.sw, ORG, {"horas_ativo": True})
        assert out == {"minutos_ativo": True, "minutos_intervalo": 20, "horas_ativo": True, "horas_intervalo": 1}
        assert svc.obter_config(world.sw, OTHER_ORG_ID) == svc.CONFIG_PADRAO


@pytest.mark.asyncio
class TestPeloTurnoReal:
    """The wiring: the lead turn arms the timers, the re-engagement turn sends through the same path."""

    async def test_a_julia_reply_arms_the_timers_against_the_post_turn_gen(self, world):
        _cfg(world, minutos_ativo=True, minutos_intervalo=10, horas_ativo=True, horas_intervalo=2)
        repo = FakeJobRepository()
        k = buffer_lead(world, LEAD_CHAT, ["Oi"])
        await process_lead_batch(k, world.buffer.memory_for(k), deps=world.deps(jobs=repo))
        assert world.sent_texts()
        c = world.contato()
        tipos = sorted(j.type for j in _jobs(repo))
        assert tipos == [svc.JOB_HORAS, svc.JOB_MINUTOS]
        assert {j.payload["gen"] for j in _jobs(repo)} == {c["gen"]}

    async def test_an_encerrar_in_the_same_turn_arms_nothing(self, world):
        from app.clients.agents import FakeAgentsClient, LaisAction, TurnResult

        _cfg(world, minutos_ativo=True)
        world.agents = FakeAgentsClient([TurnResult(
            conversation_id="11111111-1111-4111-8111-111111111111", partes=("Tudo bem, até mais!",),
            status="respondido", actions=(LaisAction("encerrar", 1, {"motivo": "sem_interesse"}),))])
        repo = FakeJobRepository()
        k = buffer_lead(world, LEAD_CHAT, ["não tenho interesse"])
        await process_lead_batch(k, world.buffer.memory_for(k), deps=world.deps(jobs=repo))
        assert world.contato()["encerrado_at"] and _jobs(repo) == []

    async def test_a_silent_turn_arms_nothing_and_a_missing_queue_never_breaks_the_reply(self, world):
        _cfg(world, minutos_ativo=True)
        k = buffer_lead(world, LEAD_CHAT, ["Oi"])
        await process_lead_batch(k, world.buffer.memory_for(k), deps=world.deps(jobs=None))
        assert world.sent_texts()

    async def test_the_reengagement_turn_sends_carries_the_estado_and_never_bumps_gen(self, world):
        _cfg(world, minutos_ativo=True)
        repo = FakeJobRepository()
        k = buffer_lead(world, LEAD_CHAT, ["Oi"])
        await process_lead_batch(k, world.buffer.memory_for(k), deps=world.deps(jobs=repo))
        enviados = len(world.sent_texts())
        gen = world.contato()["gen"]
        job = _jobs(repo, svc.JOB_MINUTOS)[0]
        out = await svc.executar_default(job, deps=world.deps(jobs=repo), repo=repo, run_turn=run_reengajamento_turn, agora=MANHA)
        assert out == "enviado" and len(world.sent_texts()) == enviados + 1
        req = world.agents.turns[-1]
        assert req.contexto["estado"]["reengajamento"] == "minutos"
        assert req.messages[0].provider_message_id == f"reeng:{job.id}"
        assert world.contato()["gen"] == gen
        # the re-engagement's own outbound does not re-arm the same tier (same gen => same dedupe key)
        assert len(_jobs(repo, svc.JOB_MINUTOS)) == 1

    async def test_a_regua_attempt_through_the_real_turn_flags_the_rewrite(self, world, frio):
        _regua(world)
        k = buffer_lead(world, LEAD_CHAT, ["Oi"])
        repo = FakeJobRepository()
        await process_lead_batch(k, world.buffer.memory_for(k), deps=world.deps(jobs=repo))
        job = _jobs(repo, svc.JOB_REGUA)[0]
        out = await svc.executar_tentativa(job, deps=world.deps(jobs=repo), repo=repo, run_turn=run_reengajamento_turn, agora=MANHA)
        assert out == "enviado"
        estado = world.agents.turns[-1].contexto["estado"]
        assert estado["reescrever"] is True and estado["texto_base"].startswith("Oi, tudo bem?")
        assert frio  # it was the last attempt

    async def test_an_agents_failure_is_a_silent_false_not_a_crash(self, world, caplog):
        from app.clients.agents import AgentsUpstreamError, FakeAgentsClient

        _cfg(world, minutos_ativo=True)
        repo = FakeJobRepository()
        k = buffer_lead(world, LEAD_CHAT, ["Oi"])
        await process_lead_batch(k, world.buffer.memory_for(k), deps=world.deps(jobs=repo))
        world.agents = FakeAgentsClient([AgentsUpstreamError("down")])
        with caplog.at_level("ERROR"):
            out = await svc.executar_default(_jobs(repo)[0], deps=world.deps(jobs=repo), repo=repo,
                                             run_turn=run_reengajamento_turn, agora=MANHA)
        assert out == "silencio" and "re-engagement turn failed" in caplog.text


@pytest.mark.asyncio
class TestHandlersDoWorker:
    async def test_one_handler_per_job_type_and_a_missing_conversation_module_reschedules_without_a_retry(self, world):
        repo = FakeJobRepository()
        hs = svc.handlers(deps_factory=lambda: None, repo=repo, run_turn=Turnos())
        assert set(hs) == set(svc.JOB_TYPES)
        job = await repo.enqueue(type=svc.JOB_MINUTOS, payload={})
        with pytest.raises(RescheduleLater):
            await hs[svc.JOB_MINUTOS](job)

    async def test_the_handler_runs_a_live_job_end_to_end(self, world):
        _cfg(world, minutos_ativo=True)
        c = _contato(world)
        repo = FakeJobRepository()
        await _armar(world, repo, c)
        turnos = Turnos()
        hs = _handlers(world, repo, turnos)
        await hs[svc.JOB_MINUTOS](_jobs(repo)[0])
        assert len(turnos.chamadas) == 1
