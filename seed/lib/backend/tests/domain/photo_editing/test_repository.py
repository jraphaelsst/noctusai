"""Repository: Protocol conformance, in-memory semantics, and the Supabase
implementation exercised against ``MockSupabaseClient`` with
``validate_schema=True`` — every column the repo reads or writes is checked
against the REAL consumer migrations (social-wiring 121-128, Core 046)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from noctusai_lib.domain.photo_editing import (
    InMemoryPhotoEditingRepository,
    PhotoEditingRepository,
    PhotoStatus,
    RepositoryError,
    Speed,
    SupabasePhotoEditingRepository,
    make_photo_editing_repository,
)
from noctusai_lib.domain.photo_editing.types import (
    CostLedgerRow,
    DatasetRecord,
    Decision,
    EditType,
    IllegalTransitionError,
    LlmUsageRow,
    ProposalCursor,
    RuleStatus,
)
from noctusai_lib.testing import MockSupabaseClient, MockSupabaseResponse

from .conftest import ORG, USER, Clock, run


class SchemaStableClient:
    """Composes the seed ``MockSupabaseClient`` so repeated
    ``.schema(name)`` calls return the SAME scoped client (the mock builds a
    fresh one per call, which would drop table state between statements)."""

    def __init__(self) -> None:
        self.base = MockSupabaseClient(validate_schema=True)
        self._scoped: dict[str, Any] = {}

    def schema(self, name: str) -> Any:
        if name not in self._scoped:
            self._scoped[name] = self.base.schema(name)
        return self._scoped[name]

    def table(self, name: str) -> Any:
        return self.base.table(name)

    def sw(self, table: str) -> Any:
        return self.schema("social_wiring").from_(table)


def test_protocol_conformance() -> None:
    assert isinstance(InMemoryPhotoEditingRepository(), PhotoEditingRepository)
    assert isinstance(SupabasePhotoEditingRepository(SchemaStableClient()), PhotoEditingRepository)


def test_factory() -> None:
    assert isinstance(make_photo_editing_repository(use_fake=True), InMemoryPhotoEditingRepository)
    assert isinstance(
        make_photo_editing_repository(supabase_client=SchemaStableClient()),
        SupabasePhotoEditingRepository,
    )
    with pytest.raises(RuntimeError, match="supabase_client is required"):
        make_photo_editing_repository()


def test_in_memory_transition_is_guarded_and_evented() -> None:
    async def scenario() -> None:
        repo = InMemoryPhotoEditingRepository(now=Clock())
        b = await repo.create_batch(org_id=ORG, nome="n", criado_por=USER, origem="upload",
                                    velocidade=Speed.URGENTE)
        p = await repo.add_photo(org_id=ORG, lote_id=b.id, ordem=1, storage_path_original="x")
        with pytest.raises(ValueError):
            await repo.add_photo(org_id=ORG, lote_id=b.id, ordem=1, storage_path_original="y")
        with pytest.raises(IllegalTransitionError):
            await repo.transition_photo(p.id, PhotoStatus.EDITANDO)
        moved = await repo.transition_photo(p.id, PhotoStatus.NORMALIZANDO, detalhe={"k": 1})
        assert moved.status is PhotoStatus.NORMALIZANDO
        ev = (await repo.list_events(b.id))[0]
        assert (ev.estado_de, ev.estado_para, ev.detalhe) == ("recebida", "normalizando", {"k": 1})
        with pytest.raises(ValueError, match="not updatable"):
            await repo.update_photo(p.id, status="pronta")
        with pytest.raises(ValueError, match="not updatable"):
            await repo.update_batch(b.id, org_id="evil")
        with pytest.raises(KeyError):
            await repo.transition_photo("missing", PhotoStatus.PRONTA)

    run(scenario())


# ---------------------------------------------------------------------------
# Supabase implementation
# ---------------------------------------------------------------------------


def test_supabase_batch_photo_roundtrip_and_cas() -> None:
    async def scenario() -> None:
        client = SchemaStableClient()
        repo = SupabasePhotoEditingRepository(client, now=Clock())
        b = await repo.create_batch(org_id=ORG, nome="Casa", criado_por=USER, origem="upload",
                                    velocidade=Speed.URGENTE)
        assert b.velocidade is Speed.URGENTE and b.org_id == ORG
        assert client.sw("fotos_lotes").inserted_payloads[0]["velocidade"] == "urgente"

        p = await repo.add_photo(org_id=ORG, lote_id=b.id, ordem=1, storage_path_original="o/l/u")
        # Mock rows carry no DB defaults; seed the ones Postgres would fill.
        client.sw("fotos_fotos")._data[0].update({"status": "recebida", "tentativas": 0})
        got = await repo.get_photo(p.id)
        assert got.status is PhotoStatus.RECEBIDA

        moved = await repo.transition_photo(p.id, PhotoStatus.NORMALIZANDO,
                                            increment_tentativas=True)
        assert moved.status is PhotoStatus.NORMALIZANDO and moved.tentativas == 1
        upd = client.sw("fotos_fotos").updated_payloads[-1]
        assert upd["status"] == "normalizando" and upd["tentativas"] == 1
        event = client.sw("fotos_eventos").inserted_payloads[-1]
        assert (event["estado_de"], event["estado_para"], event["tipo"]) == (
            "recebida", "normalizando", "transicao_estado")

        with pytest.raises(IllegalTransitionError):
            await repo.transition_photo(p.id, PhotoStatus.APROVADA)

        await repo.update_photo(p.id, largura_original=720, altura_original=1080)
        await repo.update_batch(b.id, status="processando", guia_efetivo_sha256="s")
        photos = await repo.list_photos(b.id)
        assert [x.largura_original for x in photos] == [720]

    run(scenario())


def test_supabase_cas_lost_race_returns_none() -> None:
    async def scenario() -> None:
        client = SchemaStableClient()
        repo = SupabasePhotoEditingRepository(client)
        await repo.add_photo(org_id=ORG, lote_id="l", ordem=1, storage_path_original="x")
        row = client.sw("fotos_fotos")._data[0]
        row.update({"status": "recebida", "tentativas": 0})

        class RacingUpdate:
            """Reads see 'recebida'; the conditional UPDATE matches nothing,
            as if another worker moved the row in between."""

            def __init__(self, inner):
                self.inner = inner

            def __getattr__(self, name):
                return getattr(self.inner, name)

            def schema(self, name):
                scoped = self.inner.schema(name)
                outer = self

                class Scoped:
                    def from_(self, table):
                        builder = scoped.from_(table)
                        if table != "fotos_fotos":
                            return builder

                        class B:
                            def __getattr__(self, n):
                                return getattr(builder, n)

                            def update(self, data):
                                row["status"] = "falhou"  # the concurrent writer
                                return builder.update(data)

                        return B()

                return Scoped()

        racing = SupabasePhotoEditingRepository(RacingUpdate(client))
        assert await racing.transition_photo(row["id"], PhotoStatus.NORMALIZANDO) is None
        assert client.sw("fotos_eventos").inserted_payloads == []

    run(scenario())


def test_supabase_writes_match_every_other_table() -> None:
    """Exercises one write per table; schema validation raises on any
    column that does not exist in the consumer migrations."""

    async def scenario() -> None:
        client = SchemaStableClient()
        repo = SupabasePhotoEditingRepository(client, now=Clock())
        e = await repo.create_edit(org_id=ORG, lote_id="l", foto_id="f", tentativa=1,
                                   tipos_edicao=(EditType.CEU,), modelo_id="m",
                                   velocidade=Speed.URGENTE)
        assert e.tipos_edicao == (EditType.CEU,)
        await repo.update_edit(e.id, status="concluida", llm_usage_id=7)
        ev = await repo.add_evaluation(org_id=ORG, lote_id="l", foto_id="f", edicao_id=e.id,
                                       recomendacao=Decision.APROVAR, score=Decimal("8.50"),
                                       motivo="ok", modelo_id="m", modelo_versao=None)
        assert ev.score == Decimal("8.50")
        assert client.sw("fotos_avaliacoes").inserted_payloads[0]["score"] == "8.50"
        d = await repo.add_decision(org_id=ORG, lote_id="l", foto_id="f",
                                    decisao=Decision.REJEITAR, comentario="c", decidido_por=USER)
        await repo.add_dataset_record(DatasetRecord(
            org_id=ORG, lote_id="l", foto_id="f", decisao_id=d.id, tipos_edicao=(EditType.CEU,),
            guia_efetivo_sha256="s", decisao_final=Decision.REJEITAR, storage_path_original="o"))
        assert client.sw("fotos_dataset").inserted_payloads[0]["tipos_edicao"] == ["ceu"]
        latest = await repo.latest_decisions("l")
        assert latest["f"].decisao is Decision.REJEITAR

        g = await repo.create_guide(versao=1, texto="t", sha256="s", gerado_de_versao=None,
                                    criado_por=None)
        client.sw("fotos_guias_estilo")._data[0]["status"] = "rascunho"
        active = await repo.activate_guide(1, ativado_por=USER, at=Clock()())
        assert active.ativado_por == USER
        with pytest.raises(RepositoryError):
            await repo.activate_guide(9, ativado_por=USER, at=Clock()())

        r = await repo.add_rule(org_id=ORG, texto="Não X",
                                origem_comentarios=({"decisao_id": d.id},))
        client.sw("fotos_regras_org")._data[0]["status"] = "proposta"
        upd = await repo.update_rule(r.id, status=RuleStatus.APROVADA, decidido_por=USER,
                                     decidido_em=Clock()(), override_platform_admin=False)
        assert upd.status is RuleStatus.APROVADA
        rs = await repo.create_rule_set(org_id=ORG, versao=1, regra_ids=(r.id,), sha256="h")
        assert rs.regra_ids == (r.id,)
        eg = await repo.get_or_create_effective_guide(org_id=ORG, guia_estilo_id=g.id,
                                                      conjunto_regras_id=rs.id, texto="t",
                                                      sha256="h2")
        again = await repo.get_or_create_effective_guide(org_id=ORG, guia_estilo_id=g.id,
                                                         conjunto_regras_id=rs.id, texto="t",
                                                         sha256="h2")
        assert again.id == eg.id
        assert len(client.sw("fotos_guias_efetivos").inserted_payloads) == 1

        await repo.save_cursor(ProposalCursor(org_id=ORG, ultima_decisao_id=d.id,
                                              ultima_execucao_em=Clock()()))
        # llm_usage.id is BIGSERIAL: queue the int the database would return.
        client.sw("llm_usage").set_responses([MockSupabaseResponse(data=[{"id": 7}])])
        usage_id = await repo.add_llm_usage(LlmUsageRow(
            provider="openai", model="m", operation="image_edit",
            cost_estimate_usd=Decimal("0.1"), org_id=ORG, image_output_tokens=10))
        assert usage_id == 7
        sent = client.sw("llm_usage").inserted_payloads[-1]
        assert (sent["cost_estimate_usd"], sent["image_output_tokens"], sent["batch"]) == (
            "0.1", 10, False)
        assert "at" not in sent  # DB default when the row carries no timestamp

    run(scenario())


def test_supabase_cost_ledger_targets_core_public_schema() -> None:
    async def scenario() -> None:
        client = SchemaStableClient()
        repo = SupabasePhotoEditingRepository(client)
        ledger = client.table("cost_ledger")  # public schema ⇒ client.table
        ledger.set_responses([MockSupabaseResponse(data=[{"id": 41}])])
        new_id = await repo.add_cost(CostLedgerRow(
            org_id=ORG, category="openai_edit", amount_native=Decimal("0.1"),
            currency="USD", fx_pending=True, step="fotos.edit"))
        assert new_id == 41
        sent = ledger.inserted_payloads[-1]
        assert "id" not in sent
        assert (sent["fx_pending"], sent["amount_native"], sent["amount_brl"]) == (
            True, "0.1", None)

    run(scenario())


def test_supabase_fx_pending_list_and_resolve() -> None:
    async def scenario() -> None:
        client = SchemaStableClient()
        client.base.set_table_data("cost_ledger", [{
            "id": 41, "org_id": ORG, "category": "openai_edit", "amount_native": "0.1",
            "currency": "USD", "fx_pending": True, "created_at": "2026-09-16T15:00:00+00:00",
        }])
        repo = SupabasePhotoEditingRepository(client)
        pending = await repo.list_fx_pending()
        assert [(p.id, p.amount_native, p.fx_pending) for p in pending] == [
            (41, Decimal("0.1"), True)]
        await repo.resolve_fx(41, fx_rate=Decimal("5.4"), fx_quote_date=date(2026, 9, 16),
                              amount_brl=Decimal("0.54"))
        upd = client.table("cost_ledger").updated_payloads[-1]
        assert upd == {"fx_pending": False, "fx_rate": "5.4", "fx_quote_date": "2026-09-16",
                       "amount_brl": "0.54"}
        assert await repo.list_fx_pending() == []  # guarded update applied

    run(scenario())


def test_supabase_reference_pool_and_guide_listing() -> None:
    """W6: pool writes + archive CAS + paged listings, schema-validated
    against migrations 124 + 129."""
    from noctusai_lib.domain.photo_editing import PoolFullError, Room
    from noctusai_lib.domain.photo_editing.repository import POOL_FULL_DB_MARKER

    async def scenario() -> None:
        client = SchemaStableClient()
        clock = Clock()
        repo = SupabasePhotoEditingRepository(client, now=clock)
        pair = await repo.add_reference(
            antes_url="referencias/t/antes.jpg", depois_url="referencias/t/depois.jpg",
            comodo=Room.COZINHA, tipos_edicao=(EditType.CEU,), nota="n", criado_por=USER,
        )
        sent = client.sw("fotos_referencias").inserted_payloads[0]
        assert (sent["comodo"], sent["tipos_edicao"]) == ("cozinha", ["ceu"])
        assert pair.comodo is Room.COZINHA
        client.sw("fotos_referencias")._data[0]["arquivado_em"] = None
        assert (await repo.get_reference(pair.id)).id == pair.id
        assert await repo.count_active_references() == 1

        archived = await repo.archive_reference(pair.id, at=clock())
        assert archived is not None and archived.arquivado_em == clock()
        upd = client.sw("fotos_referencias").updated_payloads[-1]
        assert set(upd) == {"arquivado_em"}
        assert await repo.archive_reference(pair.id, at=clock()) is None  # CAS: already archived

        page, total = await repo.list_references(include_archived=True, limit=10)
        assert total == 1 and page[0].id == pair.id
        active, _ = await repo.list_references(limit=10)
        assert active == []

        for v in (1, 2):
            await repo.create_guide(versao=v, texto=f"t{v}", sha256=f"s{v}",
                                    gerado_de_versao=None, criado_por=USER)
        guides, total = await repo.list_guides(limit=1)
        # The mock applies range() but not order(); ordering is pinned by
        # the in-memory test (test_pool.py::test_list_guides_is_newest_first_and_paged).
        assert total == 2 and len(guides) == 1

        # The singleton row migration 123 inserts.
        client.sw("fotos_platform_settings")._data.append(
            {"id": 1, "velocidade_default": "urgente", "notificacoes_globais_ativas": True}
        )
        settings = await repo.update_platform_settings(limite_pares_referencia=3)
        assert settings.limite_pares_referencia == 3
        assert client.sw("fotos_platform_settings").updated_payloads[-1]["limite_pares_referencia"] == 3

        # The migration-129 trigger's refusal surfaces as PoolFullError;
        # any other write failure propagates untouched.
        for message, expected in (
            (f"{POOL_FULL_DB_MARKER}: pool de referências cheio (3 pares)", PoolFullError),
            ("connection reset", ConnectionError),
        ):
            refusing = SupabasePhotoEditingRepository(_RefusingInsertClient(message, expected))
            with pytest.raises(expected):
                await refusing.add_reference(
                    antes_url="a", depois_url="d", comodo=Room.SALA, tipos_edicao=(),
                    nota=None, criado_por=USER,
                )

    run(scenario())


def test_supabase_rule_edit_and_effective_guide_listing() -> None:
    """W7: manual rule text edit + per-org effective-guide history, schema-
    validated against migration 125 (``fotos_regras_org``,
    ``fotos_guias_efetivos``)."""

    async def scenario() -> None:
        client = SchemaStableClient()
        clock = Clock()
        repo = SupabasePhotoEditingRepository(client, now=clock)

        rule = await repo.add_rule(org_id=ORG, texto="Não X", origem_comentarios=())
        edited = await repo.update_rule_text(rule.id, texto="Não X revisado")
        assert edited.texto == "Não X revisado"
        assert client.sw("fotos_regras_org").updated_payloads[-1] == {"texto": "Não X revisado"}

        first = await repo.get_or_create_effective_guide(
            org_id=ORG, guia_estilo_id="guia-1", conjunto_regras_id=None, texto="t1", sha256="s1"
        )
        clock.advance(seconds=1)
        second = await repo.get_or_create_effective_guide(
            org_id=ORG, guia_estilo_id="guia-1", conjunto_regras_id=None, texto="t2", sha256="s2"
        )
        await repo.get_or_create_effective_guide(
            org_id="org-2", guia_estilo_id="guia-1", conjunto_regras_id=None, texto="t3", sha256="s3"
        )

        # NOC-REMEDIATE[mock-count-exact-ignores-predicates] — the seed mock's
        # `count="exact"` snapshots `len(table)` at `.select()` time, before
        # any `.eq()` narrows it (`mocks.py` `count=len(self._data) if
        # count == "exact" else None`), so `total` here is the WHOLE table
        # (3), not the org-scoped count (2); `data` itself IS correctly
        # filtered. Assert on the filtered rows, not the mock's `total`.
        # 2026-09-16.
        page, _total = await repo.list_effective_guides(ORG, limit=10)
        assert {g.id for g in page} == {first.id, second.id}

    run(scenario())


class _RefusingInsertClient:
    """Minimal PostgREST-shaped client whose insert fails like a trigger
    ``RAISE EXCEPTION`` does (the seed mock cannot raise from a write)."""

    def __init__(self, message: str, exc_type: type) -> None:
        self._exc = ConnectionError(message) if exc_type is ConnectionError else RuntimeError(message)

    def schema(self, _name: str) -> "_RefusingInsertClient":
        return self

    def from_(self, _table: str) -> "_RefusingInsertClient":
        return self

    def insert(self, _row: dict) -> "_RefusingInsertClient":
        return self

    def execute(self) -> None:
        raise self._exc


def test_supabase_openai_batch_roundtrip() -> None:
    """Econômico bookkeeping (`fotos_lotes_openai`, SW migration 132) —
    every written column is validated against the real migrations."""
    from noctusai_lib.domain.photo_editing.types import OpenAIBatchStatus

    async def scenario() -> None:
        client = SchemaStableClient()
        repo = SupabasePhotoEditingRepository(client, now=Clock())
        b = await repo.create_batch(org_id=ORG, nome="Eco", criado_por=USER, origem="upload",
                                    velocidade=Speed.ECONOMICO)
        itens = ({"foto_id": "f1", "edicao_id": "e1", "custom_id": "f1:e1", "tentativas": 0},)
        rec = await repo.create_openai_batch(
            org_id=ORG, lote_id=b.id, modelo_id="gpt-image-2", itens=itens
        )
        assert rec.status is OpenAIBatchStatus.PREPARANDO and rec.itens == itens
        written = client.sw("fotos_lotes_openai").inserted_payloads[0]
        assert written["status"] == "preparando" and written["itens"] == [dict(itens[0])]

        sent = await repo.update_openai_batch(
            rec.id, status=OpenAIBatchStatus.ENVIADO, openai_batch_id="batch_1",
            openai_status="validating", submetido_at=Clock()(),
        )
        assert sent.status is OpenAIBatchStatus.ENVIADO and sent.openai_batch_id == "batch_1"
        assert client.sw("fotos_lotes_openai").updated_payloads[-1]["status"] == "enviado"
        with pytest.raises(ValueError, match="not updatable"):
            await repo.update_openai_batch(rec.id, lote_id="other")

        assert (await repo.get_openai_batch(rec.id)).openai_batch_id == "batch_1"
        assert [r.id for r in await repo.list_openai_batches(b.id)] == [rec.id]
        assert await repo.get_openai_batch("00000000-0000-4000-8000-000000000000") is None

        p = await repo.add_photo(org_id=ORG, lote_id=b.id, ordem=1, storage_path_original="x")
        await repo.update_photo(p.id, openai_batch_id="batch_1")
        assert client.sw("fotos_fotos").updated_payloads[-1]["openai_batch_id"] == "batch_1"

    run(scenario())
