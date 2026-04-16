"""Email template management service."""
import re
import logging

logger = logging.getLogger(__name__)

VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")


class TemplateService:
    def __init__(self, db, org_id: str):
        self.db = db
        self.org_id = org_id

    def list_templates(self, categoria: str = None, ativo: bool = None):
        query = self.db.table("templates").select("*").eq("org_id", self.org_id)
        if categoria:
            query = query.eq("categoria", categoria)
        if ativo is not None:
            query = query.eq("ativo", ativo)
        result = query.order("created_at", desc=True).execute()
        return result.data or []

    def get_template(self, template_id: str):
        result = (self.db.table("templates").select("*")
                  .eq("id", template_id).eq("org_id", self.org_id).execute())
        return result.data[0] if result.data else None

    def create_template(self, data: dict):
        data["org_id"] = self.org_id
        if not data.get("variaveis"):
            data["variaveis"] = self.extract_variables(data.get("corpo_html", ""))
        result = self.db.table("templates").insert(data).execute()
        return result.data[0] if result.data else None

    def update_template(self, template_id: str, data: dict):
        data["updated_at"] = "now()"
        if "corpo_html" in data and "variaveis" not in data:
            data["variaveis"] = self.extract_variables(data["corpo_html"])
        result = (self.db.table("templates").update(data)
                  .eq("id", template_id).eq("org_id", self.org_id).execute())
        return result.data[0] if result.data else None

    def delete_template(self, template_id: str):
        self.db.table("templates").update({"ativo": False}).eq("id", template_id).eq("org_id", self.org_id).execute()
        return True

    @staticmethod
    def extract_variables(html: str) -> list[str]:
        """Extract {{variable}} names from HTML template."""
        return list(set(VARIABLE_PATTERN.findall(html)))

    @staticmethod
    def render(html: str, variables: dict) -> str:
        """Replace {{variable}} placeholders with values."""
        def replacer(match):
            key = match.group(1)
            return str(variables.get(key, f"{{{{{key}}}}}"))
        return VARIABLE_PATTERN.sub(replacer, html)

    def preview(self, template_id: str, sample_variables: dict) -> dict:
        """Render a template with sample variables for preview."""
        template = self.get_template(template_id)
        if not template:
            return None
        rendered_subject = self.render(template["assunto"], sample_variables)
        rendered_body = self.render(template["corpo_html"], sample_variables)
        return {
            "assunto": rendered_subject,
            "corpo_html": rendered_body,
            "variaveis_usadas": template.get("variaveis", []),
        }
