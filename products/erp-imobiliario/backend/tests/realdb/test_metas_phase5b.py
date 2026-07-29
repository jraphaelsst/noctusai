"""Phase 5b real-DB trigger verification.

Migration `018_metas_phase5b.sql` extended the Phase-5 trigger set with:
  - `exclusividade` flag on ativos + contratos → drives modalidade on captacao
  - `comissoes.contrato_id` FK for venda/locação detection
  - `evento_participantes` bridge to mirror visita/reuniao to multiple corretores
  - venda-vs-locação split detection on `comissoes_splits`

These tests fire INSERTs that should exercise each new branch and verify the
resulting `erp.meta_eventos` rows. Service-role fixtures bypass RLS so we can
read what the triggers wrote. Skips cleanly without Supabase creds.
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.realdb


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


def _all_meta_eventos(erp_db, *, ref_tipo: str, ref_id: str) -> list[dict]:
    resp = (
        erp_db.table("meta_eventos")
        .select("*")
        .eq("referencia_tipo", ref_tipo)
        .eq("referencia_id", ref_id)
        .execute()
    )
    return resp.data or []


# ── Exclusividade on captação ──────────────────────────────────────

def test_ativo_with_exclusividade_captacao_is_exclusividade(erp_db, test_user, cleanup):
    """Inserting an ativo with exclusividade=true should produce a
    meta_evento of modalidade='exclusividade' (higher pontos)."""
    ativo_id = str(uuid.uuid4())
    erp_db.table("ativos").insert({
        "id": ativo_id,
        "owner_id": test_user["id"],
        "captador_id": test_user["id"],
        "natureza": "imovel",
        "valor": 500000,
        "status": "disponivel",
        "exclusividade": True,
    }).execute()
    cleanup.append(("ativos", ativo_id))

    evt = _latest_meta_evento(erp_db, ref_tipo="ativo", ref_id=ativo_id)
    assert evt is not None
    assert evt["evento_tipo"] == "captacao"
    assert evt["modalidade"] == "exclusividade"
    # Platform default for captacao/exclusividade is 2.0
    assert float(evt["pontos"]) == 2.0


def test_ativo_without_exclusividade_captacao_is_padrao(erp_db, test_user, cleanup):
    """Control — default captação still produces modalidade='padrao'."""
    ativo_id = str(uuid.uuid4())
    erp_db.table("ativos").insert({
        "id": ativo_id,
        "owner_id": test_user["id"],
        "captador_id": test_user["id"],
        "natureza": "imovel",
        "valor": 500000,
        "status": "disponivel",
        "exclusividade": False,
    }).execute()
    cleanup.append(("ativos", ativo_id))

    evt = _latest_meta_evento(erp_db, ref_tipo="ativo", ref_id=ativo_id)
    assert evt is not None
    assert evt["modalidade"] == "padrao"


# ── Multi-participant propagation on visita ───────────────────────

def test_visita_multi_participantes_mirrors_meta_evento_per_participant(
    erp_db, test_org, test_user, segundo_user, cleanup,
):
    """An evento with N entries in `evento_participantes` should produce
    one meta_evento per participant, each carrying fracao=1/N."""
    # Main evento — the creator-corretor.
    evento_id = str(uuid.uuid4())
    erp_db.table("eventos").insert({
        "titulo": "Evento de teste",
        "id": evento_id,
        # org_id is explicit because this harness writes through the
        # SERVICE-ROLE client: `eventos.org_id` is NOT NULL DEFAULT
        # `erp.current_org_id()` (org-SoT migrations 038/039), and
        # `current_org_id()` resolves from `auth.uid()` — which is NULL for
        # service-role. The DEFAULT therefore yields NULL and the insert trips
        # 23502. Prod is unaffected (real callers are authenticated users);
        # only the admin-client test path has to name the org itself.
        "org_id": test_org["id"],
        "corretor_id": test_user["id"],
        "tipo": "visita",
        "data_inicio": "2026-04-15T10:00:00Z",
        "data_fim": "2026-04-15T11:00:00Z",
    }).execute()
    cleanup.append(("eventos", evento_id))

    # Add a second participant via the bridge table.
    # A REAL user is required all the way down: `evento_participantes.
    # corretor_id` FKs `erp.profiles`, whose `id` in turn FKs `auth.users`.
    # The previous "dummy UUID is fine — trigger only needs corretor_id"
    # assumption became a 23503 once those FKs landed, hence the
    # `segundo_user` fixture.
    segundo_user_id = segundo_user["id"]

    part_id = str(uuid.uuid4())
    erp_db.table("evento_participantes").insert({
        "id": part_id,
        "evento_id": evento_id,
        "corretor_id": segundo_user_id,
    }).execute()
    cleanup.append(("evento_participantes", part_id))

    # The two triggers file into SEPARATE reference namespaces — verified
    # against the live functions:
    #   fn_meta_eventos_from_evento       → ('evento',              evento.id)
    #   fn_meta_eventos_from_participante → ('evento_participante', participante.id)
    # The previous assertion counted `>= 2` rows under ('evento', evento_id)
    # alone, which CANNOT hold by design — exactly one row ever lands there.
    # It read as a missing-trigger regression; the trigger was correct all along
    # and the query was looking in the wrong place.
    principal = _all_meta_eventos(erp_db, ref_tipo="evento", ref_id=evento_id)
    assert len(principal) == 1, "the evento trigger files exactly one meta_evento"
    assert principal[0]["corretor_id"] == test_user["id"]

    adicional = _all_meta_eventos(
        erp_db, ref_tipo="evento_participante", ref_id=part_id
    )
    assert len(adicional) == 1, (
        "the participante trigger must mirror the visita to the bridge corretor"
    )
    assert adicional[0]["corretor_id"] == segundo_user_id
    # Both corretores scored for the same visita — the property the test exists
    # to protect, now asserted across both namespaces instead of one.
    assert {principal[0]["corretor_id"], adicional[0]["corretor_id"]} == {
        test_user["id"],
        segundo_user_id,
    }


# ── Locação detection via comissao.contrato_id ──────────────────

def test_comissao_linked_to_locacao_contrato_produces_locacao_evento(
    erp_db, test_user, test_org, test_cliente, test_imovel, cleanup,
):
    """When `comissoes.contrato_id` points at a contract with `tipo_contrato=
    'locacao'`, the split trigger should emit evento_tipo='locacao'
    instead of 'venda'."""
    # Create a contrato marked locação
    contrato_id = str(uuid.uuid4())
    erp_db.table("contratos").insert({
        "id": contrato_id,
        # Explicit org_id — service-role writes get NULL from the
        # `current_org_id()` DEFAULT (see the eventos insert above).
        "org_id": test_org["id"],
        # cliente_id is NOT NULL on contratos.
        "cliente_id": test_cliente["id"],
        # imovel_id is NOT NULL too.
        "imovel_id": test_imovel["id"],
        "tipo": "locacao",
        "valor_total": 50000,
        # data_inicio is NOT NULL as well.
        "data_inicio": "2026-04-01",
    }).execute()
    cleanup.append(("contratos", contrato_id))

    com_id = str(uuid.uuid4())
    erp_db.table("comissoes").insert({
        "id": com_id,
        # Explicit org_id — service-role writes get NULL from the
        # `current_org_id()` DEFAULT (see the eventos insert above).
        "org_id": test_org["id"],
        "contrato_id": contrato_id,
        "valor_venda": 50000,
        "percentual_comissao": 10,
        "valor_comissao": 5000,
        "data_venda": "2026-04-10",
    }).execute()
    cleanup.append(("comissoes", com_id))

    split_id = str(uuid.uuid4())
    erp_db.table("comissoes_splits").insert({
        "percentual": 100,
        # Explicit org_id — service-role writes get NULL from the
        # `current_org_id()` DEFAULT (see the eventos insert above).
        "org_id": test_org["id"],
        "id": split_id,
        "comissao_id": com_id,
        "corretor_id": test_user["id"],
        "corretor_nome": "Test User",
        "valor": 5000,
    }).execute()
    cleanup.append(("comissoes_splits", split_id))

    evt = _latest_meta_evento(erp_db, ref_tipo="comissoes_split", ref_id=split_id)
    assert evt is not None
    # Phase 5b routes locação contracts to locacao evento_tipo
    assert evt["evento_tipo"] == "locacao"


def test_backfill_helper_is_installed(core_db):
    pytest.skip(
        "needs a `public.exec_sql(query)` RPC to introspect pg_catalog. No migration\n"
        "defines one, and adding a generic arbitrary-SQL RPC reachable through\n"
        "PostgREST is a security decision, not a test fix. The functions/triggers\n"
        "this asserts were verified present out-of-band on 2026-07-28."
    )
    """Phase 5b ships `fn_backfill_meta_eventos()` — a one-time data
    migration helper. Verify it's installed (we don't exercise it here
    because backfill is long-running)."""
    rows = core_db.rpc("exec_sql", {
        "query": (
            "SELECT proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='erp' AND p.proname='fn_backfill_meta_eventos'"
        )
    }).execute().data or []
    assert any(r["proname"] == "fn_backfill_meta_eventos" for r in rows), (
        "Phase 5b backfill helper missing — migration 018 may not be applied"
    )


def test_evento_participantes_has_rls():
    """RLS sanity check deferred until we have a non-service-role client
    in the realdb fixtures. Recorded here as a placeholder so the test
    suite enumerates it explicitly."""
    pytest.skip("RLS sanity with a non-service-role client — add when fixtures support it")
