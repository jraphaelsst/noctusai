"""Pydantic schemas for email templates."""
from typing import Optional
from pydantic import Field
from noctusai_lib.api import StrictHttpModel


class TemplateCreate(StrictHttpModel):
    nome: str = Field(..., min_length=1, max_length=200)
    assunto: str = Field(..., min_length=1, max_length=500)
    corpo_html: str
    corpo_text: Optional[str] = None
    variaveis: list[str] = Field(default_factory=list)
    categoria: str = "marketing"


class TemplateUpdate(StrictHttpModel):
    nome: Optional[str] = None
    assunto: Optional[str] = None
    corpo_html: Optional[str] = None
    corpo_text: Optional[str] = None
    variaveis: Optional[list[str]] = None
    categoria: Optional[str] = None
    ativo: Optional[bool] = None


class TemplatePreviewRequest(StrictHttpModel):
    """Sample variables for preview rendering."""
    variaveis: dict = Field(default_factory=lambda: {
        "nome": "Joao Silva",
        "email": "joao@exemplo.com",
        "empresa": "Empresa Exemplo",
    })


class TemplateSendTestRequest(StrictHttpModel):
    """Send a test email with the template."""
    to: str
    variaveis: dict = Field(default_factory=dict)
