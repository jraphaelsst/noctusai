"""Julia business hours per org + the portal opener's own text (migration 359).

Pure window maths (hours parsing, closed weekday, no window across midnight, next opening), the config save
(validation, one `configuracao_alterada` event, clearing the text), and the portal opener through the real intake
(deferral to the org's next opening, the org text vs the `mensagem_inicial` fallback, the `{link}` refusal).
Seams only: the mock DB and the seed fakes. No personal data."""
from __future__ import annotations

import asyncio
from datetime import datetime, time as dtime, timedelta, timezone

import pytest
from noctusai_lib.primitives.exceptions import AppException

from app.services import julia_agente_service as agente
from app.services import julia_portal_primeiro_contato_service as portal
from app.services import julia_reengajamento_service as svc
from tests.services.test_julia_portal_primeiro_contato import Cena, _Repo, _lead
from tests.support.julia_world import ORG_ID as ORG, OTHER_ORG_ID, World

SP = svc.FUSO
SEG_A_SEX = frozenset({1, 2, 3, 4, 5})
H = svc.Horario(dtime(9, 0), dtime(18, 30), SEG_A_SEX)


def _sp(dia: int, hora: int, minuto: int = 0) -> datetime:
    """2026-11-<dia> in Sao Paulo. 2026-11-16 is a Monday; 14 = Saturday; 15 = Sunday."""
    return datetime(2026, 11, dia, hora, minuto, tzinfo=SP).astimezone(timezone.utc)


@pytest.fixture
def world() -> World:
    w = World()
    w.seed_connection()
    w.sw.set_table_data(svc.T_CONFIG, [])
    return w


class TestJanela:
    def test_default_window_is_the_former_fixed_08_to_20_every_day(self):
        assert svc.dentro_do_horario(_sp(15, 8)) and svc.dentro_do_horario(_sp(15, 19, 59))
        assert not svc.dentro_do_horario(_sp(15, 7, 59)) and not svc.dentro_do_horario(_sp(15, 20))

    @pytest.mark.parametrize("dia,hora,minuto,dentro", [
        (16, 9, 0, True), (16, 8, 59, False), (16, 18, 29, True), (16, 18, 30, False),  # Monday, 09:00 inclusive .. 18:30 exclusive
        (14, 12, 0, False), (15, 12, 0, False),                                          # Saturday / Sunday are closed
    ])
    def test_org_window_and_closed_weekdays(self, dia, hora, minuto, dentro):
        assert svc.dentro_do_horario(_sp(dia, hora, minuto), H) is dentro

    def test_next_opening_skips_closed_weekdays(self):
        assert svc.proxima_abertura(_sp(14, 12), H) == _sp(16, 9)                   # Saturday noon -> Monday 09:00
        assert svc.proxima_abertura(_sp(16, 7), H) == _sp(16, 9)                    # Monday before opening -> same day
        assert svc.proxima_abertura(_sp(16, 19), H) == _sp(17, 9)                   # Monday evening -> Tuesday
        assert svc.segundos_ate_abertura(_sp(14, 12), H) == (_sp(16, 9) - _sp(14, 12)).total_seconds()

    def test_next_opening_at_the_exact_opening_is_the_next_one(self):
        assert svc.proxima_abertura(_sp(16, 9), H) == _sp(17, 9)

    def test_only_one_weekday_served_waits_up_to_a_week(self):
        so_segunda = svc.Horario(dtime(9, 0), dtime(12, 0), frozenset({1}))
        assert svc.proxima_abertura(_sp(16, 13), so_segunda) == _sp(23, 9)

    def test_no_weekday_is_an_error_not_a_hang(self):
        with pytest.raises(ValueError):
            svc.proxima_abertura(_sp(16, 9), svc.Horario(dtime(9, 0), dtime(12, 0), frozenset()))


class TestValidacao:
    def test_hhmm_accepts_the_db_shape_and_refuses_garbage(self):
        assert svc._hhmm("08:00:00") == dtime(8, 0) and svc._hhmm(dtime(9, 30, 15)) == dtime(9, 30)
        with pytest.raises(ValueError):
            svc._hhmm("8h")

    @pytest.mark.parametrize("a,f", [("20:00", "08:00"), ("09:00", "09:00"), ("22:00", "02:00")])
    def test_opening_must_be_before_closing_a_window_across_midnight_is_refused(self, a, f):
        with pytest.raises(AppException) as exc:
            svc.validar_horario(a, f, [1])
        assert exc.value.code == "horario_invalido" and exc.value.status_code == 422 and "meia-noite" in exc.value.message

    def test_unreadable_time_is_refused_in_pt_br(self):
        with pytest.raises(AppException) as exc:
            svc.validar_horario("manhã", "18:00", [1])
        assert exc.value.status_code == 422 and "HH:MM" in exc.value.message

    @pytest.mark.parametrize("dias", [[], [0], [8], ["1"], [True], None])
    def test_weekdays_must_be_1_to_7_and_not_empty(self, dias):
        with pytest.raises(AppException) as exc:
            svc.validar_horario("09:00", "18:00", dias)
        assert exc.value.code == "dias_invalidos"


class TestConfig:
    def test_defaults_are_todays_behaviour(self, world):
        cfg = svc.obter_config(world.sw, ORG)
        assert (cfg["horario_abertura"], cfg["horario_fechamento"], cfg["dias_atendimento"], cfg["portal_primeiro_contato_texto"]) == (
            "08:00", "20:00", [1, 2, 3, 4, 5, 6, 7], None)
        assert svc.horario_da_config(cfg) == svc.HORARIO_PADRAO

    def test_save_roundtrips_and_each_org_has_its_own_window(self, world):
        svc.salvar_config(world.sw, ORG, {"horario_abertura": "09:00", "horario_fechamento": "18:30", "dias_atendimento": [5, 1, 3]})
        assert svc.horario_da_org(world.sw, ORG) == svc.Horario(dtime(9, 0), dtime(18, 30), frozenset({1, 3, 5}))
        assert svc.horario_da_org(world.sw, OTHER_ORG_ID) == svc.HORARIO_PADRAO

    def test_a_partial_update_is_validated_against_the_stored_other_half(self, world):
        svc.salvar_config(world.sw, ORG, {"horario_abertura": "09:00", "horario_fechamento": "18:00"})
        with pytest.raises(AppException):
            svc.salvar_config(world.sw, ORG, {"horario_fechamento": "08:30"})  # closes before the stored 09:00 opening
        assert svc.obter_config(world.sw, ORG)["horario_fechamento"] == "18:00"  # nothing was written

    def test_a_save_records_one_event_with_keys_only(self, world):
        svc.salvar_config(world.sw, ORG, {"horario_abertura": "09:00", "dias_atendimento": [1, 2]}, ator="u-1")
        (ev,) = [e for e in world.sw.table("julia_eventos").select("*").execute().data if e["tipo"] == "configuracao_alterada"]
        assert ev["payload"]["area"] == "reengajamento" and ev["payload"]["chaves"] == ["dias_atendimento", "horario_abertura"]
        assert ev["payload"]["ator"] == "u-1" and "09:00" not in str(ev["payload"])

    def test_saving_an_unchanged_value_records_nothing(self, world):
        svc.salvar_config(world.sw, ORG, {"horario_abertura": "08:00"})
        assert world.sw.table("julia_eventos").select("*").execute().data == []

    def test_portal_text_needs_the_privacy_link_and_known_placeholders(self, world):
        for ruim, codigo in (("Oi, sou a Julia", "portal_texto_sem_link"), ("Oi {nome} {link}", "portal_texto_marcador_invalido"),
                             ("{link} " + "x" * 1030, "portal_texto_longo")):
            with pytest.raises(AppException) as exc:
                svc.salvar_config(world.sw, ORG, {"portal_primeiro_contato_texto": ruim})
            assert exc.value.code == codigo and exc.value.status_code == 422
        assert svc.obter_config(world.sw, ORG)["portal_primeiro_contato_texto"] is None

    def test_portal_text_saves_and_a_blank_clears_it_back_to_the_default(self, world):
        texto = "Oi, sou {agente}, assistente virtual (IA). Privacidade: {link}"
        assert svc.salvar_config(world.sw, ORG, {"portal_primeiro_contato_texto": f"  {texto}  "})["portal_primeiro_contato_texto"] == texto
        assert svc.salvar_config(world.sw, ORG, {"portal_primeiro_contato_texto": "   "})["portal_primeiro_contato_texto"] is None


class TestTextoDoPrimeiroContato:
    ROW = {"mensagem_inicial": "Padrao {agente} da {empresa}: {link}", "empresa_nome": "Imob", "slug": "imob"}

    @pytest.fixture(autouse=True)
    def _url(self, monkeypatch):
        monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://sw.example.test")

    def test_empty_falls_back_to_the_org_mensagem_inicial(self):
        assert agente.mensagem_inicial_pronta(self.ROW, "Julia") == "Padrao Julia da Imob: https://sw.example.test/privacidade/imob"
        assert agente.mensagem_inicial_pronta(self.ROW, "Julia", texto="  ") == agente.mensagem_inicial_pronta(self.ROW, "Julia")

    def test_the_portal_text_replaces_it_and_still_fills_the_placeholders(self):
        out = agente.mensagem_inicial_pronta(self.ROW, "Julia", texto="Oi! {agente} (IA) da {empresa}. {link}")
        assert out == "Oi! Julia (IA) da Imob. https://sw.example.test/privacidade/imob"

    def test_a_text_without_the_link_is_refused_never_sent(self):
        with pytest.raises(AppException) as exc:
            agente.mensagem_inicial_pronta(self.ROW, "Julia", texto="Oi, sou assistente virtual.")
        assert exc.value.code == "aviso_incompleto"


class TestAberturaPortal:
    @pytest.fixture
    def cena(self):
        w = World()
        w.seed_connection()
        yield Cena(w)

    @pytest.fixture
    def repo(self):
        r = _Repo()
        portal.registrar_repo(r)
        yield r
        portal.registrar_repo(None)

    def _janela(self, cena, **cfg):
        cena.ligar()
        svc.salvar_config(cena.w.sw, ORG_ID_, cfg)

    def test_a_lead_on_a_closed_weekday_is_deferred_to_the_orgs_next_opening(self, cena, repo):
        self._janela(cena, horario_abertura="09:00", horario_fechamento="18:30", dias_atendimento=[1, 2, 3, 4, 5])
        sabado = _sp(14, 12)
        r = cena.rodar(agora=sabado, lead=_lead(chegou_em=(sabado - timedelta(minutes=1)).isoformat()))
        assert r == {"status": "adiado", "enviar_apos": _sp(16, 9).isoformat()} and cena.w.waha.sent_messages == []
        (j,) = repo.jobs
        assert j["scheduled_for"] == _sp(16, 9)

    def test_inside_the_orgs_window_it_sends_and_the_old_fixed_hour_no_longer_decides(self, cena):
        self._janela(cena, horario_abertura="06:00", horario_fechamento="22:00")
        sete = _sp(16, 7)  # closed under the old fixed 08:00, open for this org
        assert cena.rodar(agora=sete, lead=_lead(chegou_em=(sete - timedelta(minutes=1)).isoformat()))["status"] == "enviado"

    def test_the_24h_expiry_is_kept_for_a_deferred_lead(self, cena):
        self._janela(cena, horario_abertura="09:00", horario_fechamento="18:30", dias_atendimento=[1])
        segunda = _sp(23, 10)
        lead = _lead(chegou_em=(segunda - timedelta(hours=25)).isoformat())
        assert cena.rodar(agora=segunda, lead=lead, adiado=True)["status"] == "expirado"


ORG_ID_ = ORG
