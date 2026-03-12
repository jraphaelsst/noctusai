"""
Unit tests for vistorias_service — checklist templates, validation, and summary.
"""
import pytest


# ---------------------------------------------------------------------------
# get_default_checklist
# ---------------------------------------------------------------------------

class TestGetDefaultChecklist:

    def test_returns_list(self):
        from app.services.vistorias_service import get_default_checklist

        checklist = get_default_checklist()

        assert isinstance(checklist, list)
        assert len(checklist) > 0

    def test_each_item_has_required_keys(self):
        from app.services.vistorias_service import get_default_checklist

        checklist = get_default_checklist()

        for entry in checklist:
            assert "item" in entry
            assert "estado" in entry
            assert "observacao" in entry

    def test_returns_deep_copy(self):
        """Mutating the returned checklist should not affect the template."""
        from app.services.vistorias_service import get_default_checklist

        checklist1 = get_default_checklist()
        checklist1[0]["estado"] = "ruim"

        checklist2 = get_default_checklist()
        assert checklist2[0]["estado"] == "bom"

    def test_known_items_present(self):
        from app.services.vistorias_service import get_default_checklist

        checklist = get_default_checklist()
        item_names = [e["item"] for e in checklist]

        assert "Paredes" in item_names
        assert "Piso" in item_names
        assert "Portas" in item_names
        assert "Limpeza Geral" in item_names


# ---------------------------------------------------------------------------
# validate_checklist
# ---------------------------------------------------------------------------

class TestValidateChecklist:

    def test_valid_items_pass_through(self):
        from app.services.vistorias_service import validate_checklist

        items = [
            {"item": "Paredes", "estado": "bom", "observacao": "OK"},
            {"item": "Piso", "estado": "ruim", "observacao": "Trincado"},
        ]

        result = validate_checklist(items)

        assert len(result) == 2
        assert result[0]["item"] == "Paredes"
        assert result[1]["estado"] == "ruim"

    def test_invalid_estado_defaults_to_bom(self):
        from app.services.vistorias_service import validate_checklist

        items = [{"item": "Janelas", "estado": "inexistente"}]

        result = validate_checklist(items)

        assert result[0]["estado"] == "bom"

    def test_missing_item_key_skipped(self):
        from app.services.vistorias_service import validate_checklist

        items = [
            {"item": "Paredes", "estado": "bom"},
            {"estado": "ruim"},  # missing 'item' key
            "not a dict",       # not a dict
        ]

        result = validate_checklist(items)

        assert len(result) == 1
        assert result[0]["item"] == "Paredes"

    def test_missing_estado_defaults_to_bom(self):
        from app.services.vistorias_service import validate_checklist

        items = [{"item": "Teto / Forro"}]

        result = validate_checklist(items)

        assert result[0]["estado"] == "bom"

    def test_observacao_default_empty_string(self):
        from app.services.vistorias_service import validate_checklist

        items = [{"item": "Vidros", "estado": "regular"}]

        result = validate_checklist(items)

        assert result[0]["observacao"] == ""


# ---------------------------------------------------------------------------
# summarise_checklist
# ---------------------------------------------------------------------------

class TestSummariseChecklist:

    def test_basic_summary(self):
        from app.services.vistorias_service import summarise_checklist

        items = [
            {"item": "Paredes", "estado": "bom"},
            {"item": "Piso", "estado": "bom"},
            {"item": "Portas", "estado": "regular"},
            {"item": "Janelas", "estado": "ruim"},
            {"item": "Ar Condicionado", "estado": "NA"},
        ]

        summary = summarise_checklist(items)

        assert summary["bom"] == 2
        assert summary["regular"] == 1
        assert summary["ruim"] == 1
        assert summary["NA"] == 1

    def test_empty_checklist(self):
        from app.services.vistorias_service import summarise_checklist

        summary = summarise_checklist([])

        assert summary == {"bom": 0, "regular": 0, "ruim": 0, "NA": 0}

    def test_all_same_estado(self):
        from app.services.vistorias_service import summarise_checklist

        items = [
            {"item": "A", "estado": "ruim"},
            {"item": "B", "estado": "ruim"},
            {"item": "C", "estado": "ruim"},
        ]

        summary = summarise_checklist(items)

        assert summary["ruim"] == 3
        assert summary["bom"] == 0


# ---------------------------------------------------------------------------
# VALID_ESTADOS constant
# ---------------------------------------------------------------------------

class TestValidEstados:

    def test_expected_estados(self):
        from app.services.vistorias_service import VALID_ESTADOS

        assert VALID_ESTADOS == {"bom", "regular", "ruim", "NA"}
