"""Tests for `LancamentosService` — CONTRACT.md §Cashflow + dashboard,
slice BE-C business rules.

Exercises the service directly (no HTTP) against a data-seeded
`MockSupabaseClient` — no monkeypatching of our own code.
"""
import asyncio
from datetime import date
from uuid import UUID

from noctusai_lib.testing import MockSupabaseClient

from app.services.lancamentos_service import LancamentosService, LancamentosServiceError

ORG = UUID("00000000-0000-0000-0000-000000000123")
LANCAMENTO_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _row(**over) -> dict:
    base = {
        "id": LANCAMENTO_ID,
        "org_id": str(ORG),
        "tipo": "entrada",
        "categoria": "assinatura",
        "descricao": None,
        "valor_centavos": 2700,
        "data": "2026-06-10",
        "origem": "manual",
        "pagamento_id": None,
        "estorno_de": None,
        "membro_id": None,
        "criado_por": None,
        "created_at": "2026-06-10T00:00:00+00:00",
        "updated_at": "2026-06-10T00:00:00+00:00",
    }
    base.update(over)
    return base


def _svc(rows=None) -> tuple[LancamentosService, MockSupabaseClient]:
    mock = MockSupabaseClient()
    if rows is not None:
        mock.set_table_data("lancamentos", rows)
    return LancamentosService(mock, org_id=ORG), mock


class TestList:
    def test_totais_reflect_the_whole_filtered_set_not_just_the_page(self):
        rows = [
            _row(id=f"aaaaaaaa-aaaa-aaaa-aaaa-{i:012d}", tipo="entrada", valor_centavos=100, data="2026-06-10")
            for i in range(5)
        ]
        svc, _ = _svc(rows)
        result = asyncio.run(svc.list(
            de=date(2026, 6, 1), ate=date(2026, 6, 30), page=1, page_size=2,
        ))
        assert len(result["items"]) == 2
        assert result["total"] == 5
        assert result["totais"]["entradas_centavos"] == 500

    def test_date_range_excludes_rows_outside_window(self):
        svc, _ = _svc([
            _row(id="aaaaaaaa-aaaa-aaaa-aaaa-000000000001", data="2026-05-31"),
            _row(id="aaaaaaaa-aaaa-aaaa-aaaa-000000000002", data="2026-06-01"),
            _row(id="aaaaaaaa-aaaa-aaaa-aaaa-000000000003", data="2026-07-01"),
        ])
        result = asyncio.run(svc.list(de=date(2026, 6, 1), ate=date(2026, 6, 30)))
        assert result["total"] == 1


class TestWrites:
    def test_create_forces_origem_manual_even_if_supplied(self):
        svc, _ = _svc([])
        result = asyncio.run(svc.create(payload={
            "tipo": "entrada", "categoria": "outros", "descricao": None,
            "valor_centavos": 500, "data": date(2026, 6, 1),
        }))
        assert result["origem"] == "manual"

    def test_update_automatico_raises_409(self):
        svc, _ = _svc([_row(origem="pagamento")])
        try:
            asyncio.run(svc.update(lancamento_id=LANCAMENTO_ID, payload={"categoria": "outros"}))
            assert False, "expected LancamentosServiceError"
        except LancamentosServiceError as exc:
            assert exc.status_code == 409
            assert exc.detail == "Lançamentos automáticos não podem ser alterados."

    def test_update_manual_ok(self):
        svc, _ = _svc([_row(origem="manual")])
        result = asyncio.run(svc.update(lancamento_id=LANCAMENTO_ID, payload={"categoria": "marketing"}))
        assert result["categoria"] == "marketing"

    def test_delete_automatico_raises_409(self):
        svc, _ = _svc([_row(origem="estorno")])
        try:
            asyncio.run(svc.delete(lancamento_id=LANCAMENTO_ID))
            assert False, "expected LancamentosServiceError"
        except LancamentosServiceError as exc:
            assert exc.status_code == 409

    def test_delete_unknown_returns_false(self):
        svc, _ = _svc([])
        result = asyncio.run(svc.delete(lancamento_id=LANCAMENTO_ID))
        assert result is False


class TestCategorias:
    def test_merges_used_categories_with_defaults(self):
        svc, _ = _svc([_row(categoria="patrocinio")])
        items = asyncio.run(svc.categorias())
        assert "patrocinio" in items
        for default in ("assinatura", "estorno", "plataforma", "marketing", "equipe", "impostos", "outros"):
            assert default in items

    def test_no_duplicates_when_used_category_is_already_a_default(self):
        svc, _ = _svc([_row(categoria="marketing")])
        items = asyncio.run(svc.categorias())
        assert items.count("marketing") == 1
