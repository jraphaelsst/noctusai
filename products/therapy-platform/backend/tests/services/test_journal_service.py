"""
Tests for the Journal Service.

Covers: CRUD operations and pagination.
"""
import pytest

from tests.conftest import MockSupabaseClient
from app.services import journal_service


SAMPLE_ENTRY = {
    "id": "journal-001",
    "patient_id": "patient-001",
    "titulo": "Reflexão do dia",
    "conteudo": "Hoje percebi que a ansiedade diminuiu.",
    "is_shared_with_therapist": False,
}


class TestCreateEntry:
    @pytest.mark.asyncio
    async def test_create_entry(self):
        db = MockSupabaseClient()
        db.set_table_data("journal_entries", [SAMPLE_ENTRY])
        result = await journal_service.create_entry(
            patient_id="patient-001",
            data={"conteudo": "Hoje percebi algo novo.", "titulo": "Reflexão"},
            db=db,
        )
        assert result is not None
        assert result["patient_id"] == "patient-001"

    @pytest.mark.asyncio
    async def test_create_entry_without_titulo(self):
        db = MockSupabaseClient()
        entry = {**SAMPLE_ENTRY, "titulo": None}
        db.set_table_data("journal_entries", [entry])
        result = await journal_service.create_entry(
            patient_id="patient-001",
            data={"conteudo": "Sem título"},
            db=db,
        )
        assert result is not None


class TestUpdateEntry:
    @pytest.mark.asyncio
    async def test_update_entry(self):
        db = MockSupabaseClient()
        db.set_table_data("journal_entries", [SAMPLE_ENTRY])
        result = await journal_service.update_entry(
            entry_id="journal-001",
            data={"conteudo": "Conteúdo atualizado"},
            db=db,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_update_entry_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("journal_entries", [])
        with pytest.raises(Exception) as exc_info:
            await journal_service.update_entry(
                entry_id="nonexistent",
                data={"conteudo": "Teste"},
                db=db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_entry_empty_data(self):
        db = MockSupabaseClient()
        db.set_table_data("journal_entries", [SAMPLE_ENTRY])
        with pytest.raises(Exception) as exc_info:
            await journal_service.update_entry(
                entry_id="journal-001",
                data={},
                db=db,
            )
        assert exc_info.value.status_code == 400


class TestDeleteEntry:
    @pytest.mark.asyncio
    async def test_delete_entry(self):
        db = MockSupabaseClient()
        db.set_table_data("journal_entries", [SAMPLE_ENTRY])
        await journal_service.delete_entry(entry_id="journal-001", db=db)

    @pytest.mark.asyncio
    async def test_delete_entry_not_found(self):
        db = MockSupabaseClient()
        db.set_table_data("journal_entries", [])
        with pytest.raises(Exception) as exc_info:
            await journal_service.delete_entry(entry_id="nonexistent", db=db)
        assert exc_info.value.status_code == 404


class TestListEntries:
    @pytest.mark.asyncio
    async def test_list_entries(self):
        db = MockSupabaseClient()
        db.set_table_data("journal_entries", [SAMPLE_ENTRY])
        data, total = await journal_service.list_entries(
            patient_id="patient-001",
            db=db,
        )
        assert isinstance(data, list)
        assert len(data) == 1

    @pytest.mark.asyncio
    async def test_list_entries_empty(self):
        db = MockSupabaseClient()
        db.set_table_data("journal_entries", [])
        data, total = await journal_service.list_entries(
            patient_id="patient-001",
            db=db,
        )
        assert data == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_entries_pagination(self):
        db = MockSupabaseClient()
        db.set_table_data("journal_entries", [SAMPLE_ENTRY])
        data, total = await journal_service.list_entries(
            patient_id="patient-001",
            db=db,
            page=2,
            page_size=10,
        )
        assert isinstance(data, list)
