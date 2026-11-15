"""The ImobShotAI card history is the seed transition_log primitive (migration 345), and the API keeps its shape.

The in-memory repository runs the primitive's own Fake; the Supabase one reads the primitive's events table. The
mapping from an event to the `Evento` the FE already reads is the only place the old `imobshot_eventos` vocabulary
(card_criado | lote_vinculado | etapa_mudou | card_arquivado, etapa_de/etapa_para) survives."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from noctusai_lib.domain.transition_log import configs_in_migration
from noctusai_lib.testing.migrations import migration_path

from app.modules.imobshotai.repository import (
    CARD_LOG,
    EVENTOS,
    InMemoryImobshotRepository,
    _evento_from_event,
)

_MIGRATION = migration_path(Path(__file__).resolve().parents[3], "imobshot_card_transition_log")
ORG = str(uuid4())
USER = str(uuid4())


def _repo(*batches: str) -> InMemoryImobshotRepository:
    return InMemoryImobshotRepository(SimpleNamespace(batches={b: SimpleNamespace(org_id=ORG, criado_por=USER) for b in batches}))


def test_the_runtime_config_is_the_one_migration_345_rendered():
    (cfg,) = configs_in_migration(_MIGRATION.read_text(encoding="utf-8"))
    assert cfg == CARD_LOG
    assert EVENTOS == cfg.events_table


def test_the_card_history_reads_back_in_the_api_shape():
    repo = _repo("L1")
    card, created = repo.obter_ou_criar_card(ORG, "ONE1", USER)
    assert created
    assert repo.vincular_lote(card.id, "L1", USER)
    assert repo.aplicar_etapa(card.id, "fotos_em_edicao", None, None)
    assert not repo.aplicar_etapa(card.id, "fotos_em_edicao", None, None)

    newest_first = repo.eventos(card.id, 10)
    assert [e.tipo for e in newest_first] == ["etapa_mudou", "lote_vinculado", "card_criado"]
    moved, linked, born = newest_first
    assert (moved.etapa_de, moved.etapa_para, moved.actor_id) == ("fotos_enviadas", "fotos_em_edicao", None)
    assert (linked.etapa_de, linked.etapa_para, linked.detalhe) == (None, None, {"lote_id": "L1"})
    assert (born.etapa_de, born.etapa_para, born.actor_id) == (None, "fotos_enviadas", USER)
    assert [e.tipo for e in repo.eventos(card.id, 2)] == ["etapa_mudou", "lote_vinculado"]


def test_every_state_change_is_an_event_of_the_primitive():
    repo = _repo("L1")
    card, _ = repo.obter_ou_criar_card(ORG, "ONE2", USER)
    repo.vincular_lote(card.id, "L1", USER)
    repo.aplicar_etapa(card.id, "fotos_aprovadas", None, USER)
    history = repo._log.history(ORG, card.id)
    assert [(e["seq"], e["event_type"]) for e in history] == [(1, "created"), (2, "lote_vinculado"), (3, "etapa_mudou")]
    assert [e["actor_kind"] for e in history] == ["user", "user", "user"]


def test_a_legacy_or_synthetic_event_reads_as_the_old_vocabulary():
    legacy = {"event_type": "created", "from_state": None, "to_state": "fotos_enviadas", "actor_id": None,
              "occurred_at": "2026-11-01T10:00:00+00:00", "data": {"legacy_tipo": "card_criado", "migrated_from": "imobshot_eventos"}}
    ev = _evento_from_event(legacy)
    assert (ev.tipo, ev.etapa_de, ev.etapa_para, ev.actor_id, ev.detalhe) == ("card_criado", None, "fotos_enviadas", None, {})
    synthetic = {**legacy, "event_type": "imported_initial_state", "data": {"synthetic": True}}
    assert _evento_from_event(synthetic).tipo == "card_criado"
    archived = {**legacy, "event_type": "card_arquivado", "from_state": "concluido", "to_state": "arquivado"}
    assert (_evento_from_event(archived).etapa_de, _evento_from_event(archived).etapa_para) == ("concluido", "arquivado")
