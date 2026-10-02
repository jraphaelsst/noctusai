"""Receita "positiva com efeitos de negativa" 2ª via — owner decision A
(2026-10-01) + the acknowledgment-gate amendment.

PINS
----
- gate: a PCEN 2ª via within its PRINTED validity passes the 30-day rule but is
  NOT `pronto` until the operator acknowledges it (a `confirmacao`, neither a
  bloqueio nor a plain aviso); acknowledged ⇒ pronto with the aviso kept; an
  acknowledgment given for a different validity (a replaced certidão) does not
  carry over; an expired PCEN blocks; a Negativa 40 days old and a PCEN that is
  NOT a 2ª via keep the 30-day rule;
- the per-party cell and the party summary answer with the SAME rule;
- end to end: `POST …/gerar` re-checks the gate (400 + `confirmacoes`), so
  skipping the readiness screen cannot bypass it.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from app.modules.card_hub import certidoes_partes_service as celulas
from app.modules.card_hub import partes_service
from app.modules.card_hub.contrato_gerador import certidao_pcen
from app.modules.card_hub.contrato_gerador.service import hoje
from tests.modules.card_hub import contrato_gerador_fixtures as fx
from tests.modules.card_hub.test_contrato_gerador import _avaliar, _codigos
from tests.modules.card_hub.test_contrato_gerador_endpoints import (
    _auth,
    _rows,
    _seed_completo,
    _url,
)

ASS = fx.ASSINATURA  # 2026-09-14
EMITIDA = ASS - timedelta(days=60)
VALIDADE = ASS + timedelta(days=40)
AVISO = (
    "Receita: certidão positiva com efeitos de negativa — 2ª via emitida em "
    f"{EMITIDA:%d/%m/%Y}, válida até {VALIDADE:%d/%m/%Y} "
    "(a PGFN não emite nova enquanto esta for válida)"
)


def _com_federal(**over):
    d = fx.variante(1)
    v = d.vendedores[0]
    base = dict(
        resultado="positiva_com_efeito_de_negativa", emitida_em=EMITIDA,
        validade_ate=VALIDADE, segunda_via=True, resultado_id="res-1",
    )
    base.update(over)
    certs = [replace(c, **base) if c.tipo == "cnd_federal" else c for c in v.certidoes]
    return replace(d, vendedores=[replace(v, certidoes=certs)])


def _ciente(**over):
    base = dict(pcen_ciente_em="2026-09-10T10:00:00+00:00", pcen_ciente_por="u1",
                pcen_ciente_validade=VALIDADE)
    base.update(over)
    return base


class TestGate:
    def test_pcen_2via_valida_nao_e_pronto_ate_o_operador_confirmar(self):
        _d, _p, _s, av = _avaliar(1, _com_federal())
        assert av.bloqueios == [] and av.faltando == []
        assert av.pronto is False
        (c,) = av.confirmacoes
        assert c["ciente"] is False and c["resultado_id"] == "res-1"
        assert c["codigo"] == certidao_pcen.CODIGO_CONFIRMACAO
        assert c["mensagem"] == AVISO
        assert c["acoes"] == {
            "entendi": "Entendi — seguir com esta certidão",
            "duvida": "Tenho dúvida — falar com o suporte",
        }
        assert len(c["explicacao"]) == 4 and VALIDADE.strftime("%d/%m/%Y") in c["explicacao"][2]
        assert certidao_pcen.CODIGO_CONFIRMACAO in _codigos(av.avisos)

    def test_confirmada_fica_pronta_e_o_aviso_permanece_no_registro(self):
        _d, _p, _s, av = _avaliar(1, _com_federal(**_ciente()))
        assert av.pronto is True
        assert av.confirmacoes[0]["ciente"] is True
        assert av.confirmacoes[0]["ciente_por"] == "u1"
        assert any(a["mensagem"].startswith(AVISO) for a in av.avisos)

    def test_ciencia_dada_para_outra_validade_nao_vale(self):
        """A replaced certidão (different printed validity) needs a NEW ack."""
        _d, _p, _s, av = _avaliar(1, _com_federal(**_ciente(pcen_ciente_validade=VALIDADE - timedelta(days=5))))
        assert av.pronto is False and av.confirmacoes[0]["ciente"] is False

    def test_pcen_vencida_bloqueia_e_nao_pede_ciencia(self):
        _d, _p, _s, av = _avaliar(1, _com_federal(validade_ate=ASS - timedelta(days=1)))
        assert _codigos(av.bloqueios) == ["CERTIDAO_VENCIDA"]
        assert av.confirmacoes == []

    def test_negativa_de_40_dias_continua_bloqueando(self):
        _d, _p, _s, av = _avaliar(1, _com_federal(
            resultado="negativa", segunda_via=False, emitida_em=ASS - timedelta(days=40)))
        assert _codigos(av.bloqueios) == ["CERTIDAO_EMISSAO_ANTIGA"] and av.confirmacoes == []

    def test_negativa_2via_nao_e_a_excecao(self):
        _d, _p, _s, av = _avaliar(1, _com_federal(resultado="negativa"))
        assert _codigos(av.bloqueios) == ["CERTIDAO_EMISSAO_ANTIGA"]

    def test_pcen_que_nao_e_2via_mantem_a_regra_de_30_dias(self):
        _d, _p, _s, av = _avaliar(1, _com_federal(segunda_via=False))
        assert _codigos(av.bloqueios) == ["CERTIDAO_EMISSAO_ANTIGA"]

    def test_pcen_sem_validade_lida_mantem_a_regra_de_30_dias(self):
        _d, _p, _s, av = _avaliar(1, _com_federal(validade_ate=None))
        assert _codigos(av.bloqueios) == ["CERTIDAO_EMISSAO_ANTIGA"]


class TestCelulaConcordaComOGate:
    ROW = {
        "id": "r1", "tipo": "cnd_federal", "status": "sucesso",
        "resultado": "positiva_com_efeito_de_negativa", "numero": "X",
        "emitida_em": EMITIDA.isoformat(), "validade_ate": VALIDADE.isoformat(),
        "api_response": {certidao_pcen.MARCA_SEGUNDA_VIA: {"preferencia_emissao": "2via"}},
    }

    def test_valida_nao_e_stale_e_carrega_o_bloco_educativo(self):
        c = celulas.montar_celula("cnd_federal", self.ROW, ASS, 30)
        assert c["stale_para_contrato"] is False and c["idade_dias"] == 60
        assert c["pcen"]["mensagem"] == AVISO and c["pcen"]["ciente"] is False

    def test_vencida_pela_validade_impressa_e_stale(self):
        c = celulas.montar_celula("cnd_federal", {**self.ROW, "validade_ate": (ASS - timedelta(days=1)).isoformat()}, ASS, 30)
        assert c["stale_para_contrato"] is True

    def test_ciencia_aparece_na_celula(self):
        row = {**self.ROW, "pcen_ciente_em": "2026-09-10T10:00:00+00:00",
               "pcen_ciente_validade": VALIDADE.isoformat()}
        assert celulas.montar_celula("cnd_federal", row, ASS, 30)["pcen"]["ciente"] is True

    def test_negativa_antiga_continua_stale_e_sem_bloco(self):
        c = celulas.montar_celula("cnd_federal", {**self.ROW, "resultado": "negativa"}, ASS, 30)
        assert c["stale_para_contrato"] is True and c["pcen"] is None

    def test_o_resumo_da_parte_usa_a_mesma_regra(self):
        r = {**self.ROW, "created_at": "2026-01-01", "nome_display": "CND Federal"}
        ok = partes_service.certidoes_mais_recentes([r], hoje=ASS, max_dias=30)
        assert ok["tipos_vencidos"] == []
        vencida = {**r, "validade_ate": (ASS - timedelta(days=1)).isoformat()}
        assert partes_service.certidoes_mais_recentes([vencida], hoje=ASS, max_dias=30)["tipos_vencidos"] == ["cnd_federal"]
        negativa = {**r, "resultado": "negativa"}
        assert partes_service.certidoes_mais_recentes([negativa], hoje=ASS, max_dias=30)["tipos_vencidos"] == ["cnd_federal"]

    def test_a_regra_unica_nao_diverge_do_gate(self):
        """The same predicate the gate applies, evaluated for every combination."""
        for resultado in ("negativa", "positiva_com_efeito_de_negativa"):
            for via2 in (True, False):
                for validade in (None, VALIDADE, ASS - timedelta(days=1)):
                    exc = certidao_pcen.excecao_aplica(resultado=resultado, segunda_via=via2, validade_ate=validade)
                    stale = certidao_pcen.esta_vencida(
                        emitida_em=EMITIDA, validade_ate=validade, referencia=ASS, max_dias=30, excecao=exc)
                    _d, _p, _s, av = _avaliar(1, _com_federal(resultado=resultado, segunda_via=via2, validade_ate=validade))
                    bloqueado = bool({"CERTIDAO_EMISSAO_ANTIGA", "CERTIDAO_VENCIDA"} & set(_codigos(av.bloqueios)))
                    assert stale == bloqueado, (resultado, via2, validade)


class TestGerarReverificaOPortao:
    def _pcen(self, scoped, **over):
        ids = _seed_completo(scoped)
        rows = _rows(scoped, "certidao_resultados")
        hoje_ = hoje()
        alvo = next(r for r in rows if r["tipo"] == "cnd_federal")
        alvo.update(
            resultado="positiva_com_efeito_de_negativa",
            emitida_em=(hoje_ - timedelta(days=75)).isoformat(),
            validade_ate=(hoje_ + timedelta(days=30)).isoformat(),
            api_response={certidao_pcen.MARCA_SEGUNDA_VIA: {"preferencia_emissao": "2via"}},
            **over,
        )
        scoped.set_table_data("certidao_resultados", rows)
        return ids, alvo

    def test_sem_ciencia_o_geracao_nao_esta_pronto_e_o_gerar_recusa(self, client, scoped, fake_storage):
        ids, _alvo = self._pcen(scoped)
        geracao = client.get(_url(ids, "geracao"), headers=_auth()).json()
        assert geracao["pronto"] is False and geracao["bloqueios"] == [] and geracao["faltando"] == []
        assert geracao["confirmacoes"][0]["ciente"] is False
        r = client.post(_url(ids, "gerar"), json={"assinatura_data": hoje().isoformat()}, headers=_auth())
        assert r.status_code == 400
        erro = r.json()["error"]
        assert erro["code"] == "CONTRATO_INCOMPLETO"
        assert erro["details"]["confirmacoes"][0]["codigo"] == certidao_pcen.CODIGO_CONFIRMACAO
        assert _rows(scoped, "atendimento_contrato_versoes") == []

    def test_com_ciencia_gera_e_o_registro_carrega_a_confirmacao(self, client, scoped, fake_storage):
        validade = (hoje() + timedelta(days=30)).isoformat()
        ids, _alvo = self._pcen(
            scoped, pcen_ciente_em="2026-09-10T10:00:00+00:00", pcen_ciente_por="u1",
            pcen_ciente_validade=validade,
        )
        r = client.post(_url(ids, "gerar"), json={"assinatura_data": hoje().isoformat()}, headers=_auth())
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["confirmacoes"][0]["ciente"] is True
        assert any(a["codigo"] == certidao_pcen.CODIGO_CONFIRMACAO for a in body["avisos"])

    def test_ciencia_de_uma_certidao_substituida_nao_vale(self, client, scoped, fake_storage):
        ids, _alvo = self._pcen(
            scoped, pcen_ciente_em="2026-09-10T10:00:00+00:00", pcen_ciente_por="u1",
            pcen_ciente_validade="2001-01-01",
        )
        r = client.post(_url(ids, "gerar"), json={"assinatura_data": hoje().isoformat()}, headers=_auth())
        assert r.status_code == 400
