"""Unit tests for TemplateService."""
from noctusai_lib.testing import MockSupabaseClient, MockSupabaseResponse

from app.services.template_service import TemplateService

ORG = "org-test-001"


# ---------------------------------------------------------------------------
# extract_variables()
# ---------------------------------------------------------------------------

class TestExtractVariables:
    def test_extracts_single_variable(self):
        result = TemplateService.extract_variables("<p>{{nome}}</p>")
        assert result == ["nome"]

    def test_extracts_multiple_variables(self):
        html = "<p>Ola {{nome}}, sua empresa {{empresa}} foi selecionada.</p>"
        result = TemplateService.extract_variables(html)
        assert set(result) == {"nome", "empresa"}

    def test_deduplicates_repeated_variables(self):
        html = "{{nome}} e {{nome}} novamente"
        result = TemplateService.extract_variables(html)
        assert result == ["nome"]

    def test_empty_html_returns_empty_list(self):
        assert TemplateService.extract_variables("") == []

    def test_no_variables_returns_empty_list(self):
        assert TemplateService.extract_variables("<p>Texto puro</p>") == []

    def test_ignores_nested_braces(self):
        # triple braces — inner pair is a valid variable
        html = "{{{nome}}}"
        result = TemplateService.extract_variables(html)
        assert "nome" in result

    def test_ignores_single_braces(self):
        assert TemplateService.extract_variables("{nome}") == []

    def test_multiple_variables_in_attributes(self):
        html = '<a href="{{link}}">{{texto}}</a>'
        result = TemplateService.extract_variables(html)
        assert set(result) == {"link", "texto"}


# ---------------------------------------------------------------------------
# render()
# ---------------------------------------------------------------------------

class TestRender:
    def test_replaces_known_variables(self):
        result = TemplateService.render("Ola {{nome}}", {"nome": "Maria"})
        assert result == "Ola Maria"

    def test_leaves_unknown_variables_as_is(self):
        result = TemplateService.render("{{nome}} {{cargo}}", {"nome": "Joao"})
        assert result == "Joao {{cargo}}"

    def test_empty_html(self):
        assert TemplateService.render("", {"nome": "X"}) == ""

    def test_no_variables_in_html(self):
        assert TemplateService.render("Texto puro", {"nome": "X"}) == "Texto puro"

    def test_renders_multiple_occurrences(self):
        result = TemplateService.render("{{x}} e {{x}}", {"x": "1"})
        assert result == "1 e 1"

    def test_variable_value_coerced_to_string(self):
        result = TemplateService.render("Total: {{valor}}", {"valor": 42})
        assert result == "Total: 42"

    def test_empty_variables_dict(self):
        result = TemplateService.render("{{nome}}", {})
        assert result == "{{nome}}"


# ---------------------------------------------------------------------------
# preview()
# ---------------------------------------------------------------------------

class TestPreview:
    def _make_service(self, template_data):
        db = MockSupabaseClient()
        db.set_table_data("templates", [template_data] if template_data else [])
        return TemplateService(db, ORG)

    def test_returns_rendered_subject_and_body(self):
        tmpl = {
            "id": "t1",
            "org_id": ORG,
            "assunto": "Ola {{nome}}",
            "corpo_html": "<p>Bem-vindo, {{nome}} de {{empresa}}</p>",
            "variaveis": ["nome", "empresa"],
        }
        svc = self._make_service(tmpl)
        result = svc.preview("t1", {"nome": "Ana", "empresa": "Acme"})

        assert result["assunto"] == "Ola Ana"
        assert "Ana" in result["corpo_html"]
        assert "Acme" in result["corpo_html"]
        assert set(result["variaveis_usadas"]) == {"nome", "empresa"}

    def test_returns_none_for_missing_template(self):
        svc = self._make_service(None)
        assert svc.preview("nonexistent", {}) is None

    def test_preview_with_no_sample_variables(self):
        tmpl = {
            "id": "t1",
            "org_id": ORG,
            "assunto": "Ola {{nome}}",
            "corpo_html": "<p>{{nome}}</p>",
            "variaveis": ["nome"],
        }
        svc = self._make_service(tmpl)
        result = svc.preview("t1", {})
        assert result["assunto"] == "Ola {{nome}}"
        assert result["corpo_html"] == "<p>{{nome}}</p>"


# ---------------------------------------------------------------------------
# create_template() — auto-extracts variables
# ---------------------------------------------------------------------------

class TestCreateTemplate:
    def test_sets_org_id(self):
        db = MockSupabaseClient()
        created = {"id": "t1", "org_id": ORG, "corpo_html": "<p>hi</p>", "variaveis": []}
        db.set_table_data("templates", [created])
        svc = TemplateService(db, ORG)

        data = {"nome": "Meu template", "corpo_html": "<p>hi</p>"}
        result = svc.create_template(data)
        assert result is not None
        assert data["org_id"] == ORG

    def test_auto_extracts_variables_when_missing(self):
        db = MockSupabaseClient()
        db.set_table_data("templates", [{"id": "t1"}])
        svc = TemplateService(db, ORG)

        data = {"corpo_html": "<p>{{nome}} {{email}}</p>"}
        svc.create_template(data)
        assert set(data["variaveis"]) == {"nome", "email"}

    def test_preserves_explicit_variables(self):
        db = MockSupabaseClient()
        db.set_table_data("templates", [{"id": "t1"}])
        svc = TemplateService(db, ORG)

        data = {"corpo_html": "<p>{{nome}}</p>", "variaveis": ["custom"]}
        svc.create_template(data)
        assert data["variaveis"] == ["custom"]


# ---------------------------------------------------------------------------
# update_template() — auto-extracts on body change
# ---------------------------------------------------------------------------

class TestUpdateTemplate:
    def test_auto_extracts_when_body_changes(self):
        db = MockSupabaseClient()
        db.set_table_data("templates", [{"id": "t1"}])
        svc = TemplateService(db, ORG)

        data = {"corpo_html": "<p>{{novo_var}}</p>"}
        svc.update_template("t1", data)
        assert data["variaveis"] == ["novo_var"]

    def test_does_not_extract_when_body_unchanged(self):
        db = MockSupabaseClient()
        db.set_table_data("templates", [{"id": "t1"}])
        svc = TemplateService(db, ORG)

        data = {"assunto": "Novo assunto"}
        svc.update_template("t1", data)
        assert "variaveis" not in data
