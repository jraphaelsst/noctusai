"""Branding schemas — the richer brand-kit model's HTTP contract.

``tokens`` is validated by :func:`..branding.tokens_schema.validate_tokens`
(the service calls it); the request models here only fix the envelope.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

AssetKind = Literal["logo", "model", "font"]


class BrandingSection(StrictHttpModel):
    title: str = Field(min_length=1, max_length=200)
    markdown: str = Field(default="", max_length=200_000)


class BrandingCreate(StrictHttpModel):
    name: str = Field(min_length=1, max_length=120)
    marca_id: Optional[str] = None
    persona: str = Field(default="", max_length=50_000)
    default_lang: str = Field(default="pt-BR", max_length=16)
    #: Copy the org's Branding Template (tokens, brand book, sections,
    #: components, assets) into the new branding.
    from_template: bool = False


class BrandingUpdate(StrictHttpModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    persona: Optional[str] = Field(default=None, max_length=50_000)
    design_system: Optional[str] = Field(default=None, max_length=50_000)
    default_lang: Optional[str] = Field(default=None, max_length=16)
    marca_id: Optional[str] = None
    brand_book: Optional[str] = Field(default=None, max_length=200_000)
    sections: Optional[list[BrandingSection]] = Field(default=None, max_length=40)
    tokens: Optional[dict[str, Any]] = None


class ComponentUpsert(StrictHttpModel):
    name: str = Field(min_length=1, max_length=80)
    guideline_md: str = Field(default="", max_length=200_000)
    preview_html: str = Field(default="", max_length=250_000)


class AssetUpload(StrictHttpModel):
    kind: AssetKind
    label: str = Field(min_length=1, max_length=160)
    content_base64: str = Field(min_length=1, max_length=8_000_000)
    notes: Optional[str] = Field(default=None, max_length=2000)


class ImportFile(StrictHttpModel):
    #: Path relative to the design-system folder root (``tokens.json``,
    #: ``components/Button/preview.html``, ``assets/Logos/logo.png`` …).
    path: str = Field(min_length=1, max_length=300)
    content_base64: str = Field(max_length=8_000_000)


class BrandingImport(StrictHttpModel):
    #: The marca (brand) that owns the branding. Required unless
    #: ``is_template``; forbidden when ``is_template``.
    marca_id: Optional[str] = None
    #: Store the bundle as the org's Branding Template row instead.
    is_template: bool = False
    #: Overrides the name read from ``design-system.json`` / ``tokens.json``.
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    files: list[ImportFile] = Field(min_length=1, max_length=400)
