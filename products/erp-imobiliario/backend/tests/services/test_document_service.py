"""
Unit tests for document_service — template variable extraction, substitution, and generation.
"""
import pytest
from unittest.mock import MagicMock

from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# extract_variables
# ---------------------------------------------------------------------------

class TestExtractVariables:

    def test_single_variable(self):
        from app.services.document_service import DocumentService

        result = DocumentService.extract_variables("Olá, {{nome}}!")

        assert result == ["nome"]

    def test_multiple_variables(self):
        from app.services.document_service import DocumentService

        template = "Contrato de {{tipo}} para {{nome}} no valor de {{valor}}"
        result = DocumentService.extract_variables(template)

        assert result == ["tipo", "nome", "valor"]

    def test_duplicate_variables_deduplicated(self):
        from app.services.document_service import DocumentService

        template = "{{nome}} é o locatário. Assinado por {{nome}}"
        result = DocumentService.extract_variables(template)

        assert result == ["nome"]

    def test_no_variables(self):
        from app.services.document_service import DocumentService

        result = DocumentService.extract_variables("Texto sem variaveis")

        assert result == []

    def test_preserves_order(self):
        from app.services.document_service import DocumentService

        template = "{{b}} {{a}} {{c}}"
        result = DocumentService.extract_variables(template)

        assert result == ["b", "a", "c"]


# ---------------------------------------------------------------------------
# substitute_variables
# ---------------------------------------------------------------------------

class TestSubstituteVariables:

    def test_basic_substitution(self):
        from app.services.document_service import DocumentService

        template = "Olá, {{nome}}! Seu contrato é {{contrato_id}}."
        variables = {"nome": "João", "contrato_id": "C-001"}

        result = DocumentService.substitute_variables(template, variables)

        assert result == "Olá, João! Seu contrato é C-001."

    def test_unmatched_placeholders_preserved(self):
        from app.services.document_service import DocumentService

        template = "{{nome}} mora em {{cidade}}"
        variables = {"nome": "Maria"}

        result = DocumentService.substitute_variables(template, variables)

        assert result == "Maria mora em {{cidade}}"

    def test_empty_variables_no_change(self):
        from app.services.document_service import DocumentService

        template = "{{nome}} {{sobrenome}}"

        result = DocumentService.substitute_variables(template, {})

        assert result == "{{nome}} {{sobrenome}}"

    def test_no_placeholders_in_template(self):
        from app.services.document_service import DocumentService

        result = DocumentService.substitute_variables("Texto puro", {"nome": "X"})

        assert result == "Texto puro"

    def test_numeric_value_converted_to_string(self):
        from app.services.document_service import DocumentService

        template = "Valor: R$ {{valor}}"

        result = DocumentService.substitute_variables(template, {"valor": 1500})

        assert result == "Valor: R$ 1500"


# ---------------------------------------------------------------------------
# validate_variables
# ---------------------------------------------------------------------------

class TestValidateVariables:

    def test_all_provided(self):
        from app.services.document_service import DocumentService

        missing = DocumentService.validate_variables(
            ["nome", "cpf"],
            {"nome": "João", "cpf": "123"},
        )

        assert missing == []

    def test_some_missing(self):
        from app.services.document_service import DocumentService

        missing = DocumentService.validate_variables(
            ["nome", "cpf", "endereco"],
            {"nome": "João"},
        )

        assert set(missing) == {"cpf", "endereco"}

    def test_no_variables_required(self):
        from app.services.document_service import DocumentService

        missing = DocumentService.validate_variables([], {"nome": "X"})

        assert missing == []


# ---------------------------------------------------------------------------
# generate_from_template
# ---------------------------------------------------------------------------

class TestGenerateFromTemplate:

    @pytest.mark.asyncio
    async def test_generates_document(self):
        template_record = {
            "id": "t-1",
            "nome": "Contrato Locacao",
            "tipo": "contrato",
            "conteudo": "Contrato de {{nome}} no endereço {{endereco}}.",
            "variaveis": ["nome", "endereco"],
            "is_active": True,
        }
        doc_record = {
            "id": "d-1",
            "nome": "Contrato Locacao - Gerado",
            "tipo": "contrato",
            "template_id": "t-1",
        }

        db = MockSupabaseClient()
        db.set_table_data("document_templates", template_record)
        # Insert response for `documentos` — `set_sequential_responses` controls
        # exactly what `.insert(...).execute()` returns; `set_table_data` is
        # SELECT-seeding only and does not influence inserts.
        db.set_sequential_responses("documentos", [MockSupabaseResponse(data=[doc_record])])

        from app.services.document_service import DocumentService
        svc = DocumentService(db, "u-1")

        result = await svc.generate_from_template(
            template_id="t-1",
            variables={"nome": "João", "endereco": "Rua A, 100"},
        )

        assert result is not None
        assert result["id"] == "d-1"
        assert result["_generated_content"] == "Contrato de João no endereço Rua A, 100."

    @pytest.mark.asyncio
    async def test_template_not_found_returns_none(self):
        db = MockSupabaseClient(data=None)

        from app.services.document_service import DocumentService
        svc = DocumentService(db, "u-1")

        result = await svc.generate_from_template(
            template_id="nonexistent",
            variables={"nome": "X"},
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_missing_variables_still_generates(self):
        """Missing variables result in unsubstituted placeholders but no error."""
        template_record = {
            "id": "t-2",
            "nome": "Recibo",
            "tipo": "recibo",
            "conteudo": "Recibo para {{nome}} - valor {{valor}}",
            "variaveis": ["nome", "valor"],
            "is_active": True,
        }
        doc_record = {
            "id": "d-2",
            "nome": "Recibo - Gerado",
            "tipo": "recibo",
            "template_id": "t-2",
        }

        db = MockSupabaseClient()
        db.set_table_data("document_templates", template_record)
        db.set_table_data("documentos", [doc_record])

        from app.services.document_service import DocumentService
        svc = DocumentService(db, "u-1")

        result = await svc.generate_from_template(
            template_id="t-2",
            variables={"nome": "Maria"},
        )

        assert result is not None
        assert result["_generated_content"] == "Recibo para Maria - valor {{valor}}"
