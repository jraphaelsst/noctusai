"""Maya metrics engine (maya-blocks CONTRACT §3.2): every `sdr.v1` metric on fixtures, the human-block rubric,
and the missing-data cases (a missing value is `None`, never 0). Seam: the mock DB only."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.modules.supervisao import metricas as m

from tests.support.julia_world import ORG_ID, OTHER_ORG_ID, World

DIA = date(2026, 10, 18)
INICIO = datetime(2026, 10, 18, 3, 0, tzinfo=timezone.utc)  # 00:00 America/Sao_Paulo (UTC-3)
FIM = INICIO + timedelta(days=1)
CALCULADO = datetime(2026, 10, 19, 10, 0, tzinfo=timezone.utc)
ANTES = (INICIO - timedelta(days=3)).isoformat()  # supervision switched on before the window


def em(horas: float) -> str:
    return (INICIO + timedelta(hours=horas)).isoformat()


TABELAS = ("julia_contatos", "julia_interacoes", "julia_envio_entregas", "julia_eventos", "julia_atribuicoes",
           "atendimento_handoffs")


@pytest.fixture
def sw():
    w = World()
    for t in TABELAS:
        w.sw.set_table_data(t, [])
    return w.sw


def _put(sw, tabela, linhas):
    sw.set_table_data(tabela, [{"id": f"{tabela}-{i}", "org_id": ORG_ID, **r} for i, r in enumerate(linhas)])


def _sdr(sw, desde=ANTES, horas=24):
    return m.calcular_sdr(sw, ORG_ID, DIA, horas_para_assumir=horas, calculado_at=CALCULADO,
                          supervisionado_desde=m.parse_ts(desde) if desde else None)


class TestPrimitivos:
    def test_window_is_the_sao_paulo_calendar_day_in_utc(self):
        assert m.janela(DIA) == (INICIO, FIM)

    @pytest.mark.parametrize("n,q,esperado", [
        (10, m.P50, 5), (10, m.P90, 9), (1, m.P50, 1), (1, m.P90, 1), (3, m.P50, 2), (70, m.P90, 63), (2, m.P90, 2),
    ])
    def test_nearest_rank_percentile(self, n, q, esperado):
        assert m.percentil(list(range(n, 0, -1)), q) == float(esperado)

    def test_percentile_of_nothing_is_missing(self):
        assert m.percentil([], m.P50) is None

    def test_ratio_with_zero_denominator_is_missing_not_zero(self):
        assert m.razao(0, 0) is None
        assert m.razao(3, 0) is None
        assert m.razao(0, 5) == 0.0
        assert m.razao(9, 31) == 0.2903


class TestSdrV1:
    def _cenario(self, sw):
        _put(sw, "julia_contatos", [{"created_at": em(h)} for h in (1, 2, 5, 23.9)]
             + [{"created_at": em(-0.1)}, {"created_at": em(24)}, {"org_id": OTHER_ORG_ID, "created_at": em(1)}])
        _put(sw, "julia_interacoes", [
            {"iniciada_at": em(1), "primeira_resposta_at": em(1 + 10 / 3600)},
            {"iniciada_at": em(2), "primeira_resposta_at": em(2 + 20 / 3600)},
            {"iniciada_at": em(3), "primeira_resposta_at": em(3 + 600 / 3600)},
            {"iniciada_at": em(4), "primeira_resposta_at": None},
            {"iniciada_at": em(-1), "primeira_resposta_at": None},  # outside the window
        ])
        _put(sw, "julia_envio_entregas", [
            {"contato_id": "c1", "gatilho": "qualificado", "status": "ok", "created_at": em(1)},
            {"contato_id": "c1", "gatilho": "visita", "status": "ok", "created_at": em(2)},  # same contato: distinct
            {"contato_id": "c2", "gatilho": "captacao", "status": "ok", "created_at": em(3)},
            {"contato_id": "c3", "gatilho": "qualificado", "status": "erro", "created_at": em(3)},  # failed send
            {"contato_id": "c3", "gatilho": "frio", "status": "ok", "created_at": em(4)},
            {"contato_id": "c4", "gatilho": "invalido", "status": "ok", "created_at": em(4)},
            {"contato_id": "c4", "gatilho": "manual", "status": "ok", "created_at": em(5)},
            {"contato_id": "c2", "gatilho": "manual", "status": "ok", "created_at": em(6)},
            {"contato_id": "c5", "gatilho": "qualificado", "status": "ok", "created_at": em(25)},  # next day
        ])
        _put(sw, "julia_eventos", [
            {"tipo": "envio_bloqueado", "payload": {"motivo": "fora_da_janela"}, "created_at": em(1)},
            {"tipo": "envio_bloqueado", "payload": {"motivo": "fora_da_janela"}, "created_at": em(2)},
            {"tipo": "envio_bloqueado", "payload": {}, "created_at": em(3)},
            {"tipo": "handoff", "payload": {"motivo_codigo": "pedido_do_lead"}, "created_at": em(4)},
            {"tipo": "handoff", "payload": {"motivo_codigo": "reclamacao"}, "created_at": em(5)},
            {"tipo": "novo_lead", "payload": {}, "created_at": em(5)},
        ])
        _put(sw, "julia_atribuicoes", [
            {"motivo": "handoff", "created_at": em(4)}, {"motivo": "handoff", "created_at": em(5)},
            {"motivo": "qualificacao", "created_at": em(6)},
        ])
        _put(sw, "atendimento_handoffs", [
            {"de_bloco": "sdr", "para_bloco": "atendimento", "status": "emitido", "created_at": em(1)},   # late
            {"de_bloco": "sdr", "para_bloco": "atendimento", "status": "emitido", "created_at": em(23)},  # not yet
            {"de_bloco": "sdr", "para_bloco": "atendimento", "status": "expirado", "created_at": em(2)},
            {"de_bloco": "sdr", "para_bloco": "atendimento", "status": "assumido", "created_at": em(3)},
            {"de_bloco": "atendimento", "para_bloco": "negociacao", "status": "emitido", "created_at": em(1)},
        ])

    def test_every_metric_on_a_full_day(self, sw):
        self._cenario(sw)
        assert _sdr(sw) == {
            "leads_entrada": 4,
            "tpr_n": 3, "tpr_p50_s": pytest.approx(20.0), "tpr_p90_s": pytest.approx(600.0), "tpr_sem_resposta": 1,
            "qualificados": 2, "qualificacao_taxa": 0.5,
            "frios": 1, "frio_taxa": 0.25,
            "invalidos": 1, "invalido_taxa": 0.25,
            "entregas_manuais": 2,
            "envios_bloqueados": 3, "envios_bloqueados_por_motivo": {"fora_da_janela": 2, "sem_motivo": 1},
            "handoffs_humanos": 2, "handoffs_humanos_por_motivo": {"pedido_do_lead": 1, "reclamacao": 1},
            "handoffs_emitidos": 4, "handoffs_nao_assumidos": 2,
            "horas_para_assumir": 24,
        }

    def test_threshold_changes_nao_assumidos_and_is_recorded(self, sw):
        self._cenario(sw)
        out = _sdr(sw, horas=168)
        assert out["handoffs_nao_assumidos"] == 1 and out["horas_para_assumir"] == 168

    def test_empty_day_reports_missing_ratios_and_percentiles_not_zero(self, sw):
        out = _sdr(sw)
        assert out["leads_entrada"] == 0 and out["tpr_n"] == 0 and out["tpr_sem_resposta"] == 0
        for k in ("tpr_p50_s", "tpr_p90_s", "qualificacao_taxa", "frio_taxa", "invalido_taxa"):
            assert out[k] is None, k
        assert out["envios_bloqueados_por_motivo"] == {} and out["handoffs_humanos_por_motivo"] == {}
        assert out["handoffs_emitidos"] == 0 and out["handoffs_nao_assumidos"] == 0

    def test_episodes_without_primeira_resposta_are_sem_resposta_never_estimated(self, sw):
        _put(sw, "julia_interacoes", [{"iniciada_at": em(h), "primeira_resposta_at": None} for h in (1, 2)])
        out = _sdr(sw)
        assert out["tpr_n"] == 0 and out["tpr_sem_resposta"] == 2 and out["tpr_p50_s"] is None

    def test_handoff_motivo_is_missing_while_no_handoff_event_records_it(self, sw):
        _put(sw, "julia_atribuicoes", [{"motivo": "handoff", "created_at": em(4)}])
        out = _sdr(sw)
        assert out["handoffs_humanos"] == 1 and out["handoffs_humanos_por_motivo"] is None

    @pytest.mark.parametrize("desde", [None, em(2)])
    def test_handoff_metrics_are_missing_before_supervision_was_on(self, sw, desde):
        self._cenario(sw)
        out = _sdr(sw, desde=desde)
        assert out["handoffs_emitidos"] is None and out["handoffs_nao_assumidos"] is None
        assert out["leads_entrada"] == 4  # the julia metrics do not depend on supervision


class TestBlocoHumano:
    def test_handoff_metrics_of_a_human_block(self, sw):
        _put(sw, "atendimento_handoffs", [
            {"para_bloco": "atendimento", "de_bloco": "sdr", "status": "assumido", "created_at": em(1), "assumido_at": em(1.5)},
            {"para_bloco": "atendimento", "de_bloco": "sdr", "status": "assumido", "created_at": em(2), "assumido_at": em(4)},
            {"para_bloco": "atendimento", "de_bloco": "sdr", "status": "expirado", "created_at": em(3), "assumido_at": None},
            {"para_bloco": "atendimento", "de_bloco": "sdr", "status": "emitido", "created_at": em(23), "assumido_at": None},
            {"para_bloco": "juridico", "de_bloco": "negociacao", "status": "emitido", "created_at": em(1), "assumido_at": None},
        ])
        out = m.calcular_bloco_humano(sw, ORG_ID, "atendimento", DIA, horas_para_assumir=24, calculado_at=CALCULADO,
                                      supervisionado_desde=m.parse_ts(ANTES))
        assert out == {"handoffs_recebidos": 4, "handoffs_assumidos": 2, "assumir_p50_s": 1800.0,
                       "assumir_p90_s": 7200.0, "handoffs_nao_assumidos": 1, "horas_para_assumir": 24}

    def test_empty_and_unsupervised_days(self, sw):
        vazio = m.calcular_bloco_humano(sw, ORG_ID, "juridico", DIA, horas_para_assumir=24, calculado_at=CALCULADO,
                                        supervisionado_desde=m.parse_ts(ANTES))
        assert vazio["handoffs_recebidos"] == 0 and vazio["assumir_p50_s"] is None and vazio["assumir_p90_s"] is None
        antes = m.calcular_bloco_humano(sw, ORG_ID, "juridico", DIA, horas_para_assumir=24, calculado_at=CALCULADO,
                                        supervisionado_desde=None)
        assert all(antes[k] is None for k in m.CHAVES_HUMANO)

    def test_rubric_names(self):
        assert m.rubrica("sdr") == "sdr.v1" and m.rubrica("juridico") == "juridico.v1"
