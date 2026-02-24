"""
Document Service — Business logic for document management and template generation.

Handles variable substitution and document generation from templates.
"""
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DocumentService:
    """Service for document generation and template management."""

    # Regex for {{variable_name}} placeholders
    VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")

    def __init__(self, db_client, user_id: str):
        self.db = db_client
        self.user_id = user_id

    @staticmethod
    def substitute_variables(template_content: str, variables: Dict[str, str]) -> str:
        """
        Replace {{variable}} placeholders in template content with provided values.

        Args:
            template_content: Template text containing {{variable}} placeholders
            variables: Dict mapping variable names to their values

        Returns:
            Content with all recognized variables substituted.
            Unrecognized placeholders are left as-is.
        """
        def replacer(match):
            var_name = match.group(1)
            if var_name in variables:
                return str(variables[var_name])
            # Leave unmatched placeholders as-is
            return match.group(0)

        return DocumentService.VARIABLE_PATTERN.sub(replacer, template_content)

    @staticmethod
    def extract_variables(template_content: str) -> List[str]:
        """
        Extract all variable names from template content.

        Args:
            template_content: Template text containing {{variable}} placeholders

        Returns:
            List of unique variable names found in the template
        """
        matches = DocumentService.VARIABLE_PATTERN.findall(template_content)
        # Return unique names preserving order
        seen = set()
        result = []
        for name in matches:
            if name not in seen:
                seen.add(name)
                result.append(name)
        return result

    @staticmethod
    def validate_variables(template_variables: List[str], provided_variables: Dict[str, str]) -> List[str]:
        """
        Check which required template variables are missing from provided values.

        Args:
            template_variables: List of variable names expected by the template
            provided_variables: Dict of provided variable values

        Returns:
            List of missing variable names
        """
        return [v for v in template_variables if v not in provided_variables]

    async def generate_from_template(
        self,
        template_id: str,
        variables: Dict[str, str],
        metadata: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """
        Generate a document from a template by substituting variables.

        Args:
            template_id: ID of the template to use
            variables: Dict mapping variable names to values
            metadata: Optional additional metadata for the generated document

        Returns:
            Created document record or None if template not found
        """
        # Fetch the template
        result = self.db.table("document_templates").select("*").eq(
            "id", template_id
        ).eq("is_active", True).single().execute()

        if not result.data:
            return None

        template = result.data

        # Check for missing variables
        missing = self.validate_variables(template.get("variaveis", []), variables)
        if missing:
            logger.warning(
                f"Missing variables for template {template_id}: {missing}. "
                "They will remain as placeholders."
            )

        # Generate content
        content = self.substitute_variables(template["conteudo"], variables)

        # Create the document record
        doc_data = {
            "nome": f"{template['nome']} - Gerado",
            "tipo": template["tipo"],
            "template_id": template_id,
            "created_by": self.user_id,
            "metadata": {
                **(metadata or {}),
                "generated_from_template": template_id,
                "variables_used": variables,
                "generated_content": content,
            },
        }

        doc_result = self.db.table("documentos").insert(doc_data).select().single().execute()
        if doc_result.data:
            doc_result.data["_generated_content"] = content

        return doc_result.data
