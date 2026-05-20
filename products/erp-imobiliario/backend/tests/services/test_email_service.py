"""
Unit tests for EmailService — template rendering, email stats, history.
"""
import pytest
from unittest.mock import MagicMock, patch

from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db_with_table_data(table_data_map):
    """Build a MockSupabaseClient with per-table data."""
    db = MockSupabaseClient()
    for table_name, data in table_data_map.items():
        db.set_table_data(table_name, data)
    return db


# ---------------------------------------------------------------------------
# aplicar_template
# ---------------------------------------------------------------------------

class TestAplicarTemplate:

    def test_basic_substitution(self):
        template_record = {
            "id": "t1",
            "assunto": "Ola {{nome}}, seu contrato",
            "corpo": "Prezado {{nome}}, o valor e R$ {{valor}}. Atenciosamente, {{empresa}}.",
            "ativo": True,
        }
        db = MockSupabaseClient(data=template_record)

        from app.services.email_service import EmailService
        svc = EmailService(db, "user-1")

        result = svc.aplicar_template("t1", {
            "nome": "Joao",
            "valor": "50.000",
            "empresa": "Imob LTDA",
        })

        assert result is not None
        assert result["assunto"] == "Ola Joao, seu contrato"
        assert "Prezado Joao" in result["corpo"]
        assert "R$ 50.000" in result["corpo"]
        assert "Imob LTDA" in result["corpo"]

    def test_missing_variable_keeps_placeholder(self):
        template_record = {
            "id": "t1",
            "assunto": "Ola {{nome}}",
            "corpo": "Valor: {{valor}}, Empresa: {{empresa}}",
            "ativo": True,
        }
        db = MockSupabaseClient(data=template_record)

        from app.services.email_service import EmailService
        svc = EmailService(db, "user-1")

        result = svc.aplicar_template("t1", {"nome": "Maria"})

        assert result is not None
        assert result["assunto"] == "Ola Maria"
        # valor and empresa not provided, so placeholders remain
        assert "{{valor}}" in result["corpo"]
        assert "{{empresa}}" in result["corpo"]

    def test_template_not_found_returns_none(self):
        db = MockSupabaseClient(data=None)

        from app.services.email_service import EmailService
        svc = EmailService(db, "user-1")

        result = svc.aplicar_template("nonexistent", {"nome": "X"})

        assert result is None

    def test_no_variables_in_template(self):
        template_record = {
            "id": "t1",
            "assunto": "Aviso importante",
            "corpo": "Sem variaveis aqui.",
            "ativo": True,
        }
        db = MockSupabaseClient(data=template_record)

        from app.services.email_service import EmailService
        svc = EmailService(db, "user-1")

        result = svc.aplicar_template("t1", {"nome": "X"})

        assert result["assunto"] == "Aviso importante"
        assert result["corpo"] == "Sem variaveis aqui."

    def test_empty_variables_dict(self):
        template_record = {
            "id": "t1",
            "assunto": "Ola {{nome}}",
            "corpo": "Corpo com {{variavel}}",
            "ativo": True,
        }
        db = MockSupabaseClient(data=template_record)

        from app.services.email_service import EmailService
        svc = EmailService(db, "user-1")

        result = svc.aplicar_template("t1", {})

        assert result["assunto"] == "Ola {{nome}}"
        assert result["corpo"] == "Corpo com {{variavel}}"


# ---------------------------------------------------------------------------
# enviar
# ---------------------------------------------------------------------------

class TestEnviar:

    @pytest.mark.asyncio
    async def test_creates_email_record(self):
        # `enviar` calls `_get_resend_config` → `resolve_credential`. Without
        # configured Tier 1/2 the seed module tries to materialize a real
        # Supabase client (configure_credentials had empty URL at boot). Patch
        # the seed boundary `_get_public_client` to a mock so credential
        # lookups fall through (no resend key → dry-run path, what these
        # service-level tests pin).
        record = {"id": "e1", "status": "enviado", "destinatario": "test@x.com"}
        db = MockSupabaseClient(data=record)

        from app.services.email_service import EmailService
        svc = EmailService(db, "user-1")

        with patch("noctusai_lib.config.credentials._get_public_client", return_value=db):
            result = await svc.enviar(
                destinatario="test@x.com",
                assunto="Teste",
                corpo="Corpo do email",
            )

        assert result is not None

    @pytest.mark.asyncio
    async def test_optional_fields(self):
        # Same seed-boundary patch as test_creates_email_record above.
        record = {"id": "e1", "status": "enviado"}
        db = MockSupabaseClient(data=record)

        from app.services.email_service import EmailService
        svc = EmailService(db, "user-1")

        with patch("noctusai_lib.config.credentials._get_public_client", return_value=db):
            result = await svc.enviar(
                destinatario="test@x.com",
                assunto="Teste",
                corpo="Corpo",
                cliente_id="c1",
                corpo_html="<p>Corpo</p>",
                template_id="t1",
            )

        assert result is not None


# ---------------------------------------------------------------------------
# get_historico_cliente
# ---------------------------------------------------------------------------

class TestGetHistoricoCliente:

    def test_returns_list(self):
        # `cliente_id` required on seed: production filters by
        # `.eq("cliente_id", cliente_id)`. Pre-MOCK-SELECT-PREDICATE-FIX
        # predicates were tracked-but-unevaluated; once SELECT obeys them,
        # missing `cliente_id` silently strips rows.
        db = MockSupabaseClient(data=[
            {"id": "e1", "cliente_id": "client-1"},
            {"id": "e2", "cliente_id": "client-1"},
        ])

        from app.services.email_service import EmailService
        svc = EmailService(db, "user-1")

        result = svc.get_historico_cliente("client-1")

        assert isinstance(result, list)
        assert len(result) == 2

    def test_empty_returns_empty_list(self):
        db = MockSupabaseClient(data=[])

        from app.services.email_service import EmailService
        svc = EmailService(db, "user-1")

        result = svc.get_historico_cliente("client-1")

        assert result == []


# ---------------------------------------------------------------------------
# get_estatisticas
# ---------------------------------------------------------------------------

class TestGetEstatisticas:

    def test_basic_stats(self):
        db = _make_db_with_table_data({
            "emails": [
                {"status": "enviado"},
                {"status": "enviado"},
                {"status": "aberto"},
                {"status": "aberto"},
                {"status": "aberto"},
            ],
            "email_templates": [{"id": "t1"}, {"id": "t2"}],
        })

        from app.services.email_service import EmailService
        svc = EmailService(db, "user-1")

        stats = svc.get_estatisticas()

        assert stats["total_enviados"] == 5
        assert stats["total_abertos"] == 3
        assert stats["taxa_abertura"] == 60.0
        assert stats["total_templates"] == 2

    def test_no_emails(self):
        db = _make_db_with_table_data({
            "emails": [],
            "email_templates": [],
        })

        from app.services.email_service import EmailService
        svc = EmailService(db, "user-1")

        stats = svc.get_estatisticas()

        assert stats["total_enviados"] == 0
        assert stats["total_abertos"] == 0
        assert stats["taxa_abertura"] == 0.0
        assert stats["total_templates"] == 0

    def test_all_opened(self):
        db = _make_db_with_table_data({
            "emails": [
                {"status": "aberto"},
                {"status": "aberto"},
            ],
            "email_templates": [],
        })

        from app.services.email_service import EmailService
        svc = EmailService(db, "user-1")

        stats = svc.get_estatisticas()

        assert stats["taxa_abertura"] == 100.0

    def test_none_opened(self):
        db = _make_db_with_table_data({
            "emails": [
                {"status": "enviado"},
                {"status": "enviado"},
            ],
            "email_templates": [],
        })

        from app.services.email_service import EmailService
        svc = EmailService(db, "user-1")

        stats = svc.get_estatisticas()

        assert stats["taxa_abertura"] == 0.0
