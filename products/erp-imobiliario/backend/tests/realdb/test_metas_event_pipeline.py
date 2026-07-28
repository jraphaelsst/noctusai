"""
Real-DB verification that the Phase 5 event-pipeline triggers fire and
produce correctly-shaped `erp.meta_eventos` rows.

Skips when SUPABASE creds are absent. Uses the service-role client
(bypasses RLS) so the test can read the auto-inserted rows.

Covers the three triggers defined in 017_metas_event_pipeline.sql:
  - trg_meta_eventos_captacao (on erp.ativos)
  - trg_meta_eventos_evento   (on erp.eventos — visita + reuniao)
  - trg_meta_eventos_split    (on erp.comissoes_splits — venda)

Deferred for micro-phase 5b: exclusividade, multi-participant visitas,
locação detection, backfill.
"""
from __future__ import annotations

import uuid
import pytest

import pytest

pytestmark = pytest.mark.realdb


# ── Helpers ──────────────────────────────────────────────────────────

def _latest_meta_evento(erp_db, *, ref_tipo: str, ref_id: str) -> dict | None:
    resp = (
        erp_db.table("meta_eventos")
        .select("*")
        .eq("referencia_tipo", ref_tipo)
        .eq("referencia_id", ref_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return (resp.data or [None])[0]


# ── Helper functions present ────────────────────────────────────────

def test_helper_functions_installed(core_db):
    pytest.skip(
        "needs a `public.exec_sql(query)` RPC to introspect pg_catalog. No migration\n"
        "defines one, and adding a generic arbitrary-SQL RPC reachable through\n"
        "PostgREST is a security decision, not a test fix. The functions/triggers\n"
        "this asserts were verified present out-of-band on 2026-07-28."
    )
    rows = core_db.rpc("exec_sql", {
        "query": (
            "SELECT proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='erp' AND p.proname IN "
            "('fn_resolve_pontos','fn_current_equipe','fn_org_for_user','fn_meta_eventos_from_ativo',"
            "'fn_meta_eventos_from_evento','fn_meta_eventos_from_split')"
        )
    }).execute().data or []
    names = {r["proname"] for r in rows}
    for expected in [
        "fn_resolve_pontos", "fn_current_equipe", "fn_org_for_user",
        "fn_meta_eventos_from_ativo", "fn_meta_eventos_from_evento",
        "fn_meta_eventos_from_split",
    ]:
        assert expected in names, f"Missing function erp.{expected}"


# ── Triggers attached ────────────────────────────────────────────────

def test_triggers_are_attached(core_db):
    pytest.skip(
        "needs a `public.exec_sql(query)` RPC to introspect pg_catalog. No migration\n"
        "defines one, and adding a generic arbitrary-SQL RPC reachable through\n"
        "PostgREST is a security decision, not a test fix. The functions/triggers\n"
        "this asserts were verified present out-of-band on 2026-07-28."
    )
    rows = core_db.rpc("exec_sql", {
        "query": (
            "SELECT tgname, tgrelid::regclass::text AS tbl FROM pg_trigger "
            "WHERE tgname IN ('trg_meta_eventos_captacao','trg_meta_eventos_evento','trg_meta_eventos_split')"
        )
    }).execute().data or []
    by_name = {r["tgname"]: r["tbl"] for r in rows}
    assert by_name.get("trg_meta_eventos_captacao") == "erp.ativos"
    assert by_name.get("trg_meta_eventos_evento")   == "erp.eventos"
    assert by_name.get("trg_meta_eventos_split")    == "erp.comissoes_splits"


# ── Trigger behavior: captação ──────────────────────────────────────

def test_ativo_with_captador_creates_meta_evento(erp_db, test_user, cleanup):
    ativo_id = str(uuid.uuid4())
    erp_db.table("ativos").insert({
        "id": ativo_id,
        "owner_id": test_user["id"],
        "captador_id": test_user["id"],
        "natureza": "imovel",
        "valor": 500000,
        "status": "disponivel",
    }).execute()
    cleanup.append(("ativos", ativo_id))

    evt = _latest_meta_evento(erp_db, ref_tipo="ativo", ref_id=ativo_id)
    assert evt is not None, "captação trigger did not fire"
    assert evt["evento_tipo"] == "captacao"
    assert evt["modalidade"] == "padrao"
    assert evt["corretor_id"] == test_user["id"]
    # Platform default for captação/padrão is 1.0
    assert float(evt["pontos"]) == 1.0


def test_ativo_without_captador_skips_trigger(erp_db, test_user, cleanup):
    ativo_id = str(uuid.uuid4())
    erp_db.table("ativos").insert({
        "id": ativo_id,
        "owner_id": test_user["id"],
        "natureza": "imovel",
        "valor": 500000,
        "status": "disponivel",
    }).execute()
    cleanup.append(("ativos", ativo_id))

    evt = _latest_meta_evento(erp_db, ref_tipo="ativo", ref_id=ativo_id)
    assert evt is None, "captação trigger should not fire when captador_id is NULL"


# ── Trigger behavior: visita ────────────────────────────────────────

def test_evento_visita_creates_meta_evento(erp_db, test_user, test_org, cleanup):
    evento_id = str(uuid.uuid4())
    erp_db.table("eventos").insert({
        "titulo": "Evento de teste",
        "id": evento_id,
        "org_id": test_org["id"],
        "corretor_id": test_user["id"],
        "tipo": "visita",
        "data_inicio": "2026-04-15T10:00:00Z",
        "data_fim": "2026-04-15T11:00:00Z",
    }).execute()
    cleanup.append(("eventos", evento_id))

    evt = _latest_meta_evento(erp_db, ref_tipo="evento", ref_id=evento_id)
    assert evt is not None, "visita trigger did not fire"
    assert evt["evento_tipo"] == "visita"
    assert evt["modalidade"] == "padrao"
    assert float(evt["pontos"]) == 1.0


def test_evento_outro_tipo_skips_trigger(erp_db, test_user, test_org, cleanup):
    evento_id = str(uuid.uuid4())
    erp_db.table("eventos").insert({
        "titulo": "Evento de teste",
        "id": evento_id,
        "org_id": test_org["id"],
        "corretor_id": test_user["id"],
        "tipo": "ligacao",  # not visita or reuniao — trigger should be a no-op
        "data_inicio": "2026-04-15T10:00:00Z",
        "data_fim": "2026-04-15T11:00:00Z",
    }).execute()
    cleanup.append(("eventos", evento_id))

    evt = _latest_meta_evento(erp_db, ref_tipo="evento", ref_id=evento_id)
    assert evt is None


# ── Trigger behavior: venda split ───────────────────────────────────

def test_single_split_is_venda_padrao(erp_db, test_user, test_org, cleanup):
    com_id = str(uuid.uuid4())
    erp_db.table("comissoes").insert({
        "id": com_id,
        "org_id": test_org["id"],
        "valor_venda": 800000,
        "percentual_comissao": 6,
        "valor_comissao": 48000,
        "data_venda": "2026-04-10",
    }).execute()
    cleanup.append(("comissoes", com_id))

    split_id = str(uuid.uuid4())
    erp_db.table("comissoes_splits").insert({
        "percentual": 100,
        "id": split_id,
        "org_id": test_org["id"],
        "comissao_id": com_id,
        "corretor_id": test_user["id"],
        "corretor_nome": "Test User",
        "valor": 48000,
    }).execute()
    cleanup.append(("comissoes_splits", split_id))

    evt = _latest_meta_evento(erp_db, ref_tipo="comissoes_split", ref_id=split_id)
    assert evt is not None
    assert evt["evento_tipo"] == "venda"
    assert evt["modalidade"] == "padrao"
    assert float(evt["valor_vgv"]) == 800000.0
    assert float(evt["fracao"]) == 1.0
    assert float(evt["pontos"]) == 50.0
