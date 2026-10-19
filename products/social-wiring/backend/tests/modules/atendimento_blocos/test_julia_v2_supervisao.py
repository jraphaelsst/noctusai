"""julia-v2 SW-G (CONTRACT §7 G2/G3/G4): only HUMAN acts take a handoff over; an accept with no actor keeps its
juridico handoff (T3) and raises an alert; every swallowed supervision error becomes a visible alert (a
`supervisao_falha` event + an owner-only in-app notification) without breaking the observed flow.
Seams: the mock DB, `tests.support.falha_injetada.ClienteQueFalha` (a failing DB double), the notification
service's own core-provider seam -- nothing of ours is patched."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest

from app.modules.atendimento_blocos import handoffs as h
from app.modules.pipeline.aceite import aceitar_proposta
from app.modules.supervisao.alertas import alertar

from tests.support.falha_injetada import ClienteQueFalha
from tests.support.julia_world import ADMIN_ID, ORG_ID, OTHER_ORG_ID, OWNER_ID
from .conftest import atendimento, handoffs, movimento, processo, stage_id, supervisao_on
from .test_handoffs import CONTATO, T0, _handoff, _novo_lead, _status

SERVICO = "00000000-0000-4000-8000-0000000000ff"  # a service principal: no noctus_users row at all
FORASTEIRO = "00000000-0000-4000-8000-0000000000ee"  # a member of ANOTHER org


@pytest.fixture(autouse=True)
def _sink_de_notificacoes(world):
    world.notificar_via_sink()
    world.core.set_table_data("noctus_users", [
        {"id": OWNER_ID, "org_id": ORG_ID, "org_role": "owner"},
        {"id": ADMIN_ID, "org_id": ORG_ID, "org_role": "admin"},
        {"id": FORASTEIRO, "org_id": OTHER_ORG_ID, "org_role": "member"},
    ])


def _mov(world, mid, card, de, para, *, motivo=None, responsavel=OWNER_ID, created_at="2026-10-19T13:00:00+00:00",
         pipeline="funil"):
    row = {"id": mid, "org_id": ORG_ID, "pipeline": pipeline, "entidade_id": card,
           "de_etapa_id": stage_id(de, pipeline) if de else None, "para_etapa_id": stage_id(para, pipeline),
           "responsavel_id": responsavel, "motivo": motivo, "created_at": created_at}
    world.sw.table("pipeline_movimentos").insert(row).execute()
    return row


def _alertas(world, codigo=None):
    rows = world.rows("julia_eventos", tipo="supervisao_falha")
    return [r for r in rows if codigo is None or r["payload"]["codigo"] == codigo]


def _notificados(world):
    return sorted(n["user_id"] for n in world.notifications())


# ── G2: only human acts take a handoff over ─────────────────────────────────
NAO_HUMANOS = [
    pytest.param("etapa_auto:visita_agendada", OWNER_ID, id="etapa_auto-move"),
    pytest.param("aceite_proposta", OWNER_ID, id="aceite-entry-move"),
    pytest.param(None, SERVICO, id="service-principal-move"),
    pytest.param(None, FORASTEIRO, id="member-of-another-org"),
    pytest.param(None, None, id="move-without-actor"),
]


class TestApenasAtosHumanos:
    @pytest.mark.parametrize("motivo,responsavel", NAO_HUMANOS)
    def test_a_non_human_move_does_not_take_over_inline(self, world, motivo, responsavel):
        supervisao_on(world)
        atendimento(world, etapa="visitas")
        _handoff(world)
        h.ao_movimento(world.sw, ORG_ID, _mov(world, "m2", "a1", "qualificacao", "visitas", motivo=motivo, responsavel=responsavel))
        assert _status(world)["status"] == "emitido"

    @pytest.mark.parametrize("motivo,responsavel", NAO_HUMANOS)
    def test_a_non_human_move_does_not_take_over_in_the_sweep(self, world, motivo, responsavel):
        supervisao_on(world)
        atendimento(world, etapa="visitas")
        _handoff(world)
        _mov(world, "m2", "a1", "qualificacao", "visitas", motivo=motivo, responsavel=responsavel)
        assert h.varrer(world.sw, ORG_ID, agora=datetime(2026, 10, 19, 14, tzinfo=timezone.utc))["assumidos"] == 0
        assert _status(world)["status"] == "emitido"

    def test_a_human_move_takes_over_inline_and_in_the_sweep(self, world):
        supervisao_on(world)
        atendimento(world, etapa="visitas")
        _handoff(world, "h1")
        h.ao_movimento(world.sw, ORG_ID, _mov(world, "m2", "a1", "qualificacao", "visitas", responsavel=ADMIN_ID))
        assert _status(world, "h1")["status"] == "assumido"
        _handoff(world, "h2", created_at="2026-10-19T12:30:00+00:00")
        assert h.varrer(world.sw, ORG_ID, agora=datetime(2026, 10, 19, 14, tzinfo=timezone.utc))["assumidos"] == 1
        assert _status(world, "h2")["assumido_at"] == "2026-10-19T13:00:00+00:00"

    def test_a_non_human_move_before_a_human_one_is_skipped_not_final(self, world):
        supervisao_on(world)
        atendimento(world, etapa="visitas")
        _handoff(world)
        _mov(world, "m1", "a1", "qualificacao", "visitas", motivo="etapa_auto:x", created_at="2026-10-19T12:10:00+00:00")
        _mov(world, "m2", "a1", "visitas", "negociacao", responsavel=OWNER_ID, created_at="2026-10-19T12:40:00+00:00")
        h.varrer(world.sw, ORG_ID, agora=datetime(2026, 10, 19, 14, tzinfo=timezone.utc))
        assert _status(world)["assumido_at"] == "2026-10-19T12:40:00+00:00"

    def test_a_note_counts_only_when_its_author_is_a_human_member(self, world):
        supervisao_on(world)
        atendimento(world)
        _handoff(world)
        for nid, autor in (("n0", SERVICO), ("n1", FORASTEIRO)):
            world.sw.table("cliente_notas").insert({"id": nid, "org_id": ORG_ID, "cliente_id": "cli-a1", "autor_id": autor,
                                                     "tipo": "comentario", "corpo": "x", "created_at": "2026-10-19T12:30:00+00:00"}).execute()
        assert h.detectar_assumidos(world.sw, ORG_ID) == 0
        world.sw.table("cliente_notas").insert({"id": "n2", "org_id": ORG_ID, "cliente_id": "cli-a1", "autor_id": ADMIN_ID,
                                                 "tipo": "comentario", "corpo": "liguei", "created_at": "2026-10-19T14:00:00+00:00"}).execute()
        assert h.detectar_assumidos(world.sw, ORG_ID) == 1

    def test_the_accept_entry_move_is_not_a_take_over_of_the_negociacao_handoff(self, world):
        """The accept's own movement (motivo aceite_proposta, by the user who clicked) is the boundary, not a
        take-over of an earlier open handoff on the same deal."""
        supervisao_on(world)
        atendimento(world, etapa="proposta_decisao")
        _handoff(world, "h0", created_at="2026-10-19T09:00:00+00:00")
        aceitar_proposta(world.sw, ORG_ID, "a1", OWNER_ID)
        assert _status(world, "h0")["status"] == "emitido"

    def test_a_failing_membership_lookup_is_not_a_take_over_and_alerts(self, world, caplog):
        supervisao_on(world)
        atendimento(world, etapa="visitas")
        _handoff(world)
        world.core = ClienteQueFalha(world.core, {"noctus_users"})
        h.registrar_core_provider(lambda: world.core)
        with caplog.at_level(logging.ERROR):
            h.ao_movimento(world.sw, ORG_ID, _mov(world, "m2", "a1", "qualificacao", "visitas"))
        assert _status(world)["status"] == "emitido"
        assert len(_alertas(world, "membership_lookup")) == 1 and "membership lookup failed" in caplog.text


# ── G3: an accept with no actor keeps its juridico handoff ──────────────────
class TestAceiteSemAtor:
    def test_no_actor_records_the_handoff_and_raises_a_visible_alert(self, world, caplog):
        supervisao_on(world)
        atendimento(world, etapa="proposta_decisao")
        with caplog.at_level(logging.ERROR):
            out = aceitar_proposta(world.sw, ORG_ID, "a1", None)
        assert out["already_accepted"] is False
        assert world.sw.table("pipeline_movimentos").inserted_payloads == []  # responsavel_id NOT NULL: no movement
        (row,) = handoffs(world)
        assert (row["gatilho"], row["de_bloco"], row["para_bloco"], row["origem_evento"]) == (
            "aceite_proposta", "negociacao", "juridico", out["processo"]["id"])
        assert row["atendimento_id"] == "a1" and row["status"] == "emitido"
        (alerta,) = _alertas(world, "aceite_sem_ator")
        assert alerta["payload"]["ids"] == {"processo_id": out["processo"]["id"], "atendimento_id": "a1"}
        assert _notificados(world) == [OWNER_ID]  # owners only, never the admin
        assert "without an actor" in caplog.text

    def test_with_an_actor_there_is_still_exactly_one_handoff(self, world):
        supervisao_on(world)
        atendimento(world, etapa="proposta_decisao")
        out = aceitar_proposta(world.sw, ORG_ID, "a1", OWNER_ID)
        (row,) = handoffs(world)  # T3 recorded it; T2 skipped the processo entry move
        assert row["gatilho"] == "aceite_proposta" and row["origem_evento"] == out["processo"]["id"]
        assert len(world.sw.table("pipeline_movimentos").inserted_payloads) == 1  # the movement is still written
        assert _alertas(world) == []

    def test_t3_is_idempotent_on_the_processo(self, world):
        supervisao_on(world)
        atendimento(world, etapa="proposta_decisao")
        p = processo(world, "p1", atendimento_id="a1")
        assert h.ao_aceite(world.sw, ORG_ID, p) is not None
        assert h.ao_aceite(world.sw, ORG_ID, p) is None
        assert len(handoffs(world)) == 1

    def test_t3_writes_nothing_with_supervision_off(self, world):
        atendimento(world, etapa="proposta_decisao")
        aceitar_proposta(world.sw, ORG_ID, "a1", None)
        assert handoffs(world) == [] and _alertas(world, "aceite_sem_ator")  # the missing movement is still reported

    def test_t2_still_records_the_entry_move_when_t3_did_not(self, world):
        """T3 failed or never ran for this processo: the entry move's own hook is the fallback (no handoff is lost)."""
        supervisao_on(world)
        atendimento(world, etapa="proposta_decisao")
        processo(world, "p1", atendimento_id="a1")
        row = h.ao_movimento(world.sw, ORG_ID, _mov(world, "m1", "p1", None, "elaboracao_contrato",
                                                    motivo="aceite_proposta", pipeline="processos_venda"))
        assert row is not None and row["gatilho"] == "movimento_etapa" and (row["de_bloco"], row["para_bloco"]) == ("negociacao", "juridico")


# ── G4: swallowed supervision errors are visible ────────────────────────────
class TestFalhasVisiveis:
    def _assert_alerta(self, world, codigo, ids=None):
        (a,) = _alertas(world, codigo)
        assert a["payload"]["dia"] and a["contato_id"] is None
        if ids:
            assert a["payload"]["ids"] == ids
        assert OWNER_ID in _notificados(world) and ADMIN_ID not in _notificados(world)

    def test_novo_lead_sink(self, world, caplog):
        supervisao_on(world)
        quebrado = ClienteQueFalha(world.sw, {"atendimentos"})
        with caplog.at_level(logging.ERROR):
            assert h.sink_novo_lead(quebrado, _novo_lead(world)) is None  # does not raise
        self._assert_alerta(world, "handoff_novo_lead", {"evento_id": "ev-1", "contato_id": CONTATO})
        assert "the send stands" in caplog.text

    def test_block_boundary_hook(self, world):
        supervisao_on(world)
        atendimento(world, etapa="negociacao")
        quebrado = ClienteQueFalha(world.sw, {"atendimentos"})
        assert h.ao_movimento(quebrado, ORG_ID, _mov(world, "m1", "a1", "proposta_recebida", "negociacao")) is None
        self._assert_alerta(world, "handoff_movimento", {"movimento_id": "m1"})

    def test_apos_mover_movement_read(self, world):
        supervisao_on(world)
        quebrado = ClienteQueFalha(world.sw, {"pipeline_movimentos"})
        assert h.apos_mover(quebrado, ORG_ID, "funil", "a1", "etapa-x") is None
        self._assert_alerta(world, "handoff_movimento_leitura", {"card_id": "a1"})

    def test_accept_handoff_t3(self, world):
        supervisao_on(world)
        atendimento(world, etapa="proposta_decisao")
        quebrado = ClienteQueFalha(world.sw, {"atendimento_blocos"})
        assert h.ao_aceite(quebrado, ORG_ID, {"id": "p1", "atendimento_id": "a1", "etapa_id": "e"}) is None
        self._assert_alerta(world, "handoff_aceite", {"processo_id": "p1", "atendimento_id": "a1"})

    def test_accept_entry_movement_write(self, world):
        supervisao_on(world)
        atendimento(world, etapa="proposta_decisao")
        quebrado = ClienteQueFalha(world.sw, {"pipeline_movimentos"})
        out = aceitar_proposta(quebrado, ORG_ID, "a1", OWNER_ID)  # the accept stands
        assert out["already_accepted"] is False
        self._assert_alerta(world, "aceite_movimento", {"processo_id": out["processo"]["id"]})

    def test_accept_without_actor_is_covered_above_and_dedupes_per_code_and_day(self, world):
        supervisao_on(world)
        for _ in range(3):
            alertar(world.sw, ORG_ID, "handoff_movimento", {"movimento_id": "m"})
        alertar(world.sw, ORG_ID, "aceite_sem_ator", {"processo_id": "p"})
        assert len(_alertas(world)) == 4  # every occurrence is on record...
        assert _notificados(world) == [OWNER_ID, OWNER_ID]  # ...one notification per (code, day)

    def test_the_alert_carries_ids_only_never_free_text(self, world):
        alertar(world.sw, ORG_ID, "x_falhou", {"user_id": OWNER_ID, "ausente": None})
        (a,) = _alertas(world)
        assert a["payload"]["ids"] == {"user_id": OWNER_ID}

    def test_alertar_never_raises_and_says_so_loudly_when_it_cannot_record(self, world, caplog):
        quebrado = ClienteQueFalha(world.sw, {"julia_eventos"})
        with caplog.at_level(logging.CRITICAL):
            assert alertar(quebrado, ORG_ID, "handoff_movimento", {"movimento_id": "m"}) is False
        assert "could NOT be written" in caplog.text and _alertas(world) == []
