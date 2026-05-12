"""
Unit tests for relatorios_service — agent ranking, funnel conversion, monthly activity, CSV export.
"""
import pytest
from datetime import date, timedelta

from noctusai_lib.primitives.timeutil import current_month_ref, today_utc

from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# Relative date helpers (UTC — matches production; avoids local-vs-UTC drift)
# ---------------------------------------------------------------------------
today = today_utc()
this_month_prefix = current_month_ref()
last_month_date = today.replace(day=1) - timedelta(days=1)
last_month_prefix = last_month_date.strftime("%Y-%m")


# ---------------------------------------------------------------------------
# ranking_corretores
# ---------------------------------------------------------------------------

class TestRankingCorretores:

    def test_basic_ranking(self):
        db = MockSupabaseClient()

        profiles = [
            {"id": "u-1", "nome": "Alice", "email": "alice@test.com"},
            {"id": "u-2", "nome": "Bob", "email": "bob@test.com"},
        ]
        clientes = [
            {"id": "c-1", "usuario_id": "u-1", "etapa_atual": "fechado", "valor_estimado": 500000, "created_at": f"{this_month_prefix}-01"},
            {"id": "c-2", "usuario_id": "u-1", "etapa_atual": "visitas", "valor_estimado": 200000, "created_at": f"{this_month_prefix}-02"},
            {"id": "c-3", "usuario_id": "u-2", "etapa_atual": "fechado", "valor_estimado": 300000, "created_at": f"{this_month_prefix}-05"},
        ]
        atividades = [
            {"id": "a-1", "usuario_id": "u-1", "created_at": f"{this_month_prefix}-01T10:00:00"},
            {"id": "a-2", "usuario_id": "u-1", "created_at": f"{this_month_prefix}-02T10:00:00"},
            {"id": "a-3", "usuario_id": "u-2", "created_at": f"{this_month_prefix}-03T10:00:00"},
        ]

        db.set_table_data("profiles", profiles)
        db.set_table_data("clientes", clientes)
        db.set_table_data("atividades", atividades)

        from app.services.relatorios_service import ranking_corretores
        result = ranking_corretores("org-1", db)

        assert len(result) == 2
        # Alice has 500k closed, Bob has 300k — Alice should be first
        assert result[0]["nome"] == "Alice"
        assert result[0]["total_clientes"] == 2
        assert result[0]["clientes_fechados"] == 1
        assert result[0]["valor_total_fechados"] == 500000.0
        assert result[0]["total_atividades"] == 2

        assert result[1]["nome"] == "Bob"
        assert result[1]["total_clientes"] == 1
        assert result[1]["clientes_fechados"] == 1
        assert result[1]["valor_total_fechados"] == 300000.0
        assert result[1]["total_atividades"] == 1

    def test_no_profiles_returns_empty(self):
        db = MockSupabaseClient(data=[])

        from app.services.relatorios_service import ranking_corretores
        result = ranking_corretores("org-1", db)

        assert result == []

    def test_agent_with_no_clients(self):
        db = MockSupabaseClient()

        db.set_table_data("profiles", [
            {"id": "u-1", "nome": "Carlos", "email": "carlos@test.com"},
        ])
        db.set_table_data("clientes", [])
        db.set_table_data("atividades", [])

        from app.services.relatorios_service import ranking_corretores
        result = ranking_corretores("org-1", db)

        assert len(result) == 1
        assert result[0]["total_clientes"] == 0
        assert result[0]["clientes_fechados"] == 0
        assert result[0]["valor_total_fechados"] == 0.0
        assert result[0]["total_atividades"] == 0

    def test_null_valor_estimado_treated_as_zero(self):
        db = MockSupabaseClient()

        db.set_table_data("profiles", [
            {"id": "u-1", "nome": "Dana", "email": "dana@test.com"},
        ])
        db.set_table_data("clientes", [
            {"id": "c-1", "usuario_id": "u-1", "etapa_atual": "fechado", "valor_estimado": None, "created_at": f"{this_month_prefix}-01"},
        ])
        db.set_table_data("atividades", [])

        from app.services.relatorios_service import ranking_corretores
        result = ranking_corretores("org-1", db)

        assert result[0]["clientes_fechados"] == 1
        assert result[0]["valor_total_fechados"] == 0.0

    def test_sort_by_value_then_count(self):
        """When two agents have same closed value, sort by closed count desc."""
        db = MockSupabaseClient()

        db.set_table_data("profiles", [
            {"id": "u-1", "nome": "Elisa", "email": "e@t.com"},
            {"id": "u-2", "nome": "Fabio", "email": "f@t.com"},
        ])
        db.set_table_data("clientes", [
            {"id": "c-1", "usuario_id": "u-1", "etapa_atual": "fechado", "valor_estimado": 100000, "created_at": f"{this_month_prefix}-01"},
            {"id": "c-2", "usuario_id": "u-2", "etapa_atual": "fechado", "valor_estimado": 50000, "created_at": f"{this_month_prefix}-01"},
            {"id": "c-3", "usuario_id": "u-2", "etapa_atual": "fechado", "valor_estimado": 50000, "created_at": f"{this_month_prefix}-02"},
        ])
        db.set_table_data("atividades", [])

        from app.services.relatorios_service import ranking_corretores
        result = ranking_corretores("org-1", db)

        # Both have 100k total, but Fabio has 2 closes vs Elisa's 1
        assert result[0]["nome"] == "Fabio"
        assert result[1]["nome"] == "Elisa"


# ---------------------------------------------------------------------------
# conversao_funil
# ---------------------------------------------------------------------------

class TestConversaoFunil:

    def test_all_stages_present(self):
        db = MockSupabaseClient()

        # `arquivado` required on each seed row: production filters by
        # `.eq("arquivado", False)`. Pre-MOCK-SELECT-PREDICATE-FIX the
        # predicate was tracked-but-unevaluated; once SELECT obeys it, rows
        # without `arquivado` are stripped and the funnel collapses to empty.
        clientes = [
            {"id": "c-1", "arquivado": False, "etapa_atual": "qualificacao"},
            {"id": "c-2", "arquivado": False, "etapa_atual": "qualificacao"},
            {"id": "c-3", "arquivado": False, "etapa_atual": "qualificacao"},
            {"id": "c-4", "arquivado": False, "etapa_atual": "qualificacao"},
            {"id": "c-5", "arquivado": False, "etapa_atual": "visitas"},
            {"id": "c-6", "arquivado": False, "etapa_atual": "visitas"},
            {"id": "c-7", "arquivado": False, "etapa_atual": "proposta"},
            {"id": "c-8", "arquivado": False, "etapa_atual": "negociacao"},
            {"id": "c-9", "arquivado": False, "etapa_atual": "fechado"},
        ]
        db.set_table_data("clientes", clientes)

        from app.services.relatorios_service import conversao_funil
        result = conversao_funil("org-1", db)

        assert len(result) == 5

        # qualificacao: 4, next is visitas: 2 -> 50%
        assert result[0]["etapa"] == "qualificacao"
        assert result[0]["total"] == 4
        assert result[0]["taxa_conversao"] == 50.0

        # visitas: 2, next is proposta: 1 -> 50%
        assert result[1]["etapa"] == "visitas"
        assert result[1]["total"] == 2
        assert result[1]["taxa_conversao"] == 50.0

        # proposta: 1, next is negociacao: 1 -> 100%
        assert result[2]["etapa"] == "proposta"
        assert result[2]["total"] == 1
        assert result[2]["taxa_conversao"] == 100.0

        # negociacao: 1, next is fechado: 1 -> 100%
        assert result[3]["etapa"] == "negociacao"
        assert result[3]["total"] == 1
        assert result[3]["taxa_conversao"] == 100.0

        # fechado: 1, no next -> None
        assert result[4]["etapa"] == "fechado"
        assert result[4]["total"] == 1
        assert result[4]["taxa_conversao"] is None

    def test_empty_pipeline(self):
        db = MockSupabaseClient(data=[])

        from app.services.relatorios_service import conversao_funil
        result = conversao_funil("org-1", db)

        assert len(result) == 5
        for entry in result:
            assert entry["total"] == 0
        # First four stages have 0% conversion (count = 0 -> 0.0)
        for i in range(4):
            assert result[i]["taxa_conversao"] == 0.0
        assert result[4]["taxa_conversao"] is None

    def test_labels_present(self):
        db = MockSupabaseClient(data=[])

        from app.services.relatorios_service import conversao_funil
        result = conversao_funil("org-1", db)

        expected_labels = ["Qualificação", "Visitas", "Proposta", "Negociação", "Fechado"]
        actual_labels = [r["label"] for r in result]
        assert actual_labels == expected_labels

    def test_zero_in_stage_yields_zero_rate(self):
        """When a stage has 0 clients, conversion rate should be 0.0, not a division error."""
        db = MockSupabaseClient()

        # Only clients at the end of the funnel
        db.set_table_data("clientes", [
            {"id": "c-1", "etapa_atual": "fechado"},
        ])

        from app.services.relatorios_service import conversao_funil
        result = conversao_funil("org-1", db)

        assert result[0]["total"] == 0  # qualificacao
        assert result[0]["taxa_conversao"] == 0.0  # no division by zero

    def test_single_stage_concentration(self):
        """All clients in one stage, none elsewhere."""
        db = MockSupabaseClient()

        # `arquivado` required on each seed row — same MOCK-SELECT shape as
        # test_all_stages_present above.
        db.set_table_data("clientes", [
            {"id": "c-1", "arquivado": False, "etapa_atual": "visitas"},
            {"id": "c-2", "arquivado": False, "etapa_atual": "visitas"},
            {"id": "c-3", "arquivado": False, "etapa_atual": "visitas"},
        ])

        from app.services.relatorios_service import conversao_funil
        result = conversao_funil("org-1", db)

        assert result[1]["etapa"] == "visitas"
        assert result[1]["total"] == 3
        # Next stage (proposta) has 0 -> 0%
        assert result[1]["taxa_conversao"] == 0.0


# ---------------------------------------------------------------------------
# atividade_mensal
# ---------------------------------------------------------------------------

class TestAtividadeMensal:

    def test_aggregates_current_month(self):
        db = MockSupabaseClient()

        db.set_table_data("atividades", [
            {"id": "a-1", "created_at": f"{this_month_prefix}-01T10:00:00"},
            {"id": "a-2", "created_at": f"{this_month_prefix}-15T14:00:00"},
        ])
        db.set_table_data("clientes", [
            {"id": "c-1", "etapa_atual": "visitas", "created_at": f"{this_month_prefix}-02T08:00:00"},
            {"id": "c-2", "etapa_atual": "fechado", "created_at": f"{this_month_prefix}-10T09:00:00"},
        ])

        from app.services.relatorios_service import atividade_mensal
        result = atividade_mensal("org-1", db, meses=1)

        assert len(result) == 1
        entry = result[0]
        assert entry["periodo"] == this_month_prefix
        assert entry["total_atividades"] == 2
        assert entry["novos_clientes"] == 2
        assert entry["fechados"] == 1

    def test_multiple_months(self):
        db = MockSupabaseClient()

        db.set_table_data("atividades", [
            {"id": "a-1", "created_at": f"{this_month_prefix}-01T10:00:00"},
            {"id": "a-2", "created_at": f"{last_month_prefix}-15T10:00:00"},
        ])
        db.set_table_data("clientes", [
            {"id": "c-1", "etapa_atual": "qualificacao", "created_at": f"{last_month_prefix}-20T10:00:00"},
        ])

        from app.services.relatorios_service import atividade_mensal
        result = atividade_mensal("org-1", db, meses=2)

        assert len(result) == 2
        # First entry is the earlier month (last_month)
        assert result[0]["periodo"] == last_month_prefix
        assert result[0]["total_atividades"] == 1
        assert result[0]["novos_clientes"] == 1

        assert result[1]["periodo"] == this_month_prefix
        assert result[1]["total_atividades"] == 1
        assert result[1]["novos_clientes"] == 0

    def test_empty_data(self):
        db = MockSupabaseClient(data=[])

        from app.services.relatorios_service import atividade_mensal
        result = atividade_mensal("org-1", db, meses=3)

        assert len(result) == 3
        for entry in result:
            assert entry["total_atividades"] == 0
            assert entry["novos_clientes"] == 0
            assert entry["fechados"] == 0

    def test_month_label_format(self):
        """Month labels should be in MM/YYYY format."""
        db = MockSupabaseClient(data=[])

        from app.services.relatorios_service import atividade_mensal
        result = atividade_mensal("org-1", db, meses=1)

        month = today.month
        year = today.year
        expected_label = f"{month:02d}/{year}"
        assert result[0]["mes"] == expected_label

    def test_default_six_months(self):
        db = MockSupabaseClient(data=[])

        from app.services.relatorios_service import atividade_mensal
        result = atividade_mensal("org-1", db)

        assert len(result) == 6


# ---------------------------------------------------------------------------
# generate_csv
# ---------------------------------------------------------------------------

class TestGenerateCsv:

    def test_basic_csv(self):
        from app.services.relatorios_service import generate_csv

        data = [
            {"nome": "Alice", "vendas": 10, "valor": 50000},
            {"nome": "Bob", "vendas": 5, "valor": 25000},
        ]
        csv_str = generate_csv(data)

        lines = csv_str.strip().split("\n")
        assert len(lines) == 3  # header + 2 rows
        assert "nome" in lines[0]
        assert "vendas" in lines[0]
        assert "valor" in lines[0]
        assert "Alice" in lines[1]
        assert "Bob" in lines[2]

    def test_empty_data_returns_empty_string(self):
        from app.services.relatorios_service import generate_csv

        result = generate_csv([])
        assert result == ""

    def test_custom_headers(self):
        from app.services.relatorios_service import generate_csv

        data = [
            {"nome": "Alice", "vendas": 10, "valor": 50000, "extra": "ignored"},
        ]
        csv_str = generate_csv(data, headers=["nome", "valor"])

        lines = csv_str.strip().split("\n")
        assert len(lines) == 2
        # Header should only have requested columns
        assert "nome" in lines[0]
        assert "valor" in lines[0]
        assert "vendas" not in lines[0]
        assert "extra" not in lines[0]
        # Data row should only have requested columns
        assert "Alice" in lines[1]
        assert "50000" in lines[1]

    def test_headers_from_first_row(self):
        """If no headers are provided, keys of the first dict are used."""
        from app.services.relatorios_service import generate_csv

        data = [
            {"a": 1, "b": 2},
            {"a": 3, "b": 4, "c": 5},
        ]
        csv_str = generate_csv(data)

        lines = csv_str.strip().split("\n")
        header = lines[0]
        assert "a" in header
        assert "b" in header
        # "c" is NOT in header because it's not in the first row's keys
        assert "c" not in header

    def test_csv_contains_values(self):
        from app.services.relatorios_service import generate_csv

        data = [
            {"etapa": "qualificacao", "total": 10, "taxa_conversao": 50.0},
            {"etapa": "visitas", "total": 5, "taxa_conversao": 40.0},
        ]
        csv_str = generate_csv(data)

        assert "qualificacao" in csv_str
        assert "50.0" in csv_str
        assert "visitas" in csv_str
