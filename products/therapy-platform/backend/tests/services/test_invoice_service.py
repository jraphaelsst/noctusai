"""
Tests for the Invoice Service.

Covers: generation, duplicate prevention, listing by role.
"""
import pytest

from tests.conftest import MockRequestBuilder, MockSupabaseClient
from app.services import invoice_service


SAMPLE_TRANSACTION = {
    "id": "tx-001",
    "amount": 250.00,
    "description": "Sessão de terapia individual",
}

SAMPLE_INVOICE = {
    "id": "inv-001",
    "transaction_id": "tx-001",
    "therapist_id": "therapist-001",
    "patient_id": "patient-001",
    "amount": 250.00,
    "descricao": "Sessão de terapia individual",
    "status": "gerada",
    "created_at": "2026-04-01T10:00:00Z",
}


class TestGenerateInvoice:
    @pytest.mark.asyncio
    async def test_generate_invoice(self):
        """Three-phase mock: tx exists, no duplicate, insert returns data."""
        db = MockSupabaseClient()
        call_count = {"n": 0}
        original_table = db.table

        def phased_table(name):
            call_count["n"] += 1
            if name == "financial_transactions":
                return MockRequestBuilder([SAMPLE_TRANSACTION])
            if name == "invoices":
                if call_count["n"] == 2:
                    # Duplicate check: no existing invoice
                    return MockRequestBuilder([])
                else:
                    # Insert: return new invoice
                    return MockRequestBuilder([SAMPLE_INVOICE])
            return original_table(name)

        db.table = phased_table
        result = await invoice_service.generate_invoice(
            transaction_id="tx-001",
            therapist_id="therapist-001",
            patient_id="patient-001",
            db=db,
        )
        assert result is not None
        assert result["status"] == "gerada"

    @pytest.mark.asyncio
    async def test_generate_invoice_transaction_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("financial_transactions", [])
        with pytest.raises(Exception) as exc_info:
            await invoice_service.generate_invoice(
                transaction_id="nonexistent",
                therapist_id="therapist-001",
                patient_id="patient-001",
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_invoice_duplicate(self):
        """Cannot generate a second invoice for the same transaction."""
        db = MockSupabaseClient()
        db.set_table_data("financial_transactions", [SAMPLE_TRANSACTION])
        # Invoice already exists for this transaction
        db.set_table_data("invoices", [SAMPLE_INVOICE])
        with pytest.raises(Exception) as exc_info:
            await invoice_service.generate_invoice(
                transaction_id="tx-001",
                therapist_id="therapist-001",
                patient_id="patient-001",
                db=db,
            )
        assert exc_info.value.status_code == 409


class TestListInvoices:
    @pytest.mark.asyncio
    async def test_list_invoices_therapist(self):
        db = MockSupabaseClient()
        db.set_table_data("invoices", [SAMPLE_INVOICE])
        data, total = await invoice_service.list_invoices(
            user_id="therapist-001",
            role="therapist",
            db=db,
        )
        assert isinstance(data, list)
        assert len(data) == 1

    @pytest.mark.asyncio
    async def test_list_invoices_patient(self):
        db = MockSupabaseClient()
        db.set_table_data("invoices", [SAMPLE_INVOICE])
        data, total = await invoice_service.list_invoices(
            user_id="patient-001",
            role="patient",
            db=db,
        )
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_list_invoices_admin(self):
        """Admin sees all invoices (no filter)."""
        db = MockSupabaseClient()
        db.set_table_data("invoices", [SAMPLE_INVOICE])
        data, total = await invoice_service.list_invoices(
            user_id="admin-001",
            role="platform_admin",
            db=db,
        )
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_list_invoices_empty(self):
        db = MockSupabaseClient()
        db.set_table_data("invoices", [])
        data, total = await invoice_service.list_invoices(
            user_id="therapist-001",
            role="therapist",
            db=db,
        )
        assert data == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_invoices_pagination(self):
        db = MockSupabaseClient()
        db.set_table_data("invoices", [SAMPLE_INVOICE])
        data, total = await invoice_service.list_invoices(
            user_id="therapist-001",
            role="therapist",
            db=db,
            page=2,
            page_size=10,
        )
        assert isinstance(data, list)


class TestGetInvoice:
    @pytest.mark.asyncio
    async def test_get_invoice(self):
        db = MockSupabaseClient()
        db.set_table_data("invoices", [SAMPLE_INVOICE])
        result = await invoice_service.get_invoice(invoice_id="inv-001", db=db)
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_invoice_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("invoices", [])
        with pytest.raises(Exception) as exc_info:
            await invoice_service.get_invoice(invoice_id="nonexistent", db=db)
        assert exc_info.value.status_code == 404
