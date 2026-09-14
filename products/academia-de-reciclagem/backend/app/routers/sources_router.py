"""Research-source routes — contract §B.5 (§A.8)."""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field, field_validator

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session.types import AuthContext

from app.auth.provenance import build_write_provenance
from app.config import settings
from app.dependencies import get_approval_assertion_keys, get_store, require_sources_write
from app.knowledge import KnowledgeStore, KnowledgeStoreError
from app.routers._common import error_response

router = APIRouter(prefix="/api/sources", tags=["sources"])


class SourceCreate(StrictHttpModel):
    url: str = Field(min_length=1)
    titulo: str = Field(min_length=1)
    trecho_citado: str = Field(min_length=1)
    resumo: str = Field(min_length=1)
    kb_slug: str = Field(min_length=1)
    vigencia_confirmada: bool
    exige_da_empresa: str | None = None

    @field_validator("url")
    @classmethod
    def _url_has_real_host(cls, v: str) -> str:
        """§B.5: "url must parse with a real host (no substring
        matching)" — a bare `urlparse` (not a regex/substring check on
        the raw string) rejects e.g. `https://` or `not-a-url`."""
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("url must be an absolute http(s) URL with a host")
        return v


class SourceOut(BaseModel):
    url: str
    titulo: str
    trecho_citado: str
    resumo: str
    kb_slug: str
    vigencia_confirmada: bool
    exige_da_empresa: str | None
    accessed_at: datetime
    aviso: str | None = None


def _out(row: dict, *, aviso: str | None = None) -> SourceOut:
    return SourceOut(
        url=row["url"],
        titulo=row["titulo"],
        trecho_citado=row["trecho_citado"],
        resumo=row["resumo"],
        kb_slug=row["kb_slug"],
        vigencia_confirmada=row["vigencia_confirmada"],
        exige_da_empresa=row.get("exige_da_empresa"),
        accessed_at=row["accessed_at"],
        aviso=aviso,
    )


@router.post("", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: SourceCreate,
    request: Request,
    ctx: AuthContext = Depends(require_sources_write),
    keys: list[str] = Depends(get_approval_assertion_keys),
    store: KnowledgeStore = Depends(get_store),
) -> SourceOut:
    prov = await build_write_provenance(ctx, request, keys=keys)
    try:
        row = await store.create_source(ctx.org_id, payload.model_dump(), prov)
    except KnowledgeStoreError as exc:
        raise error_response(exc) from exc

    host = (urlparse(row["url"]).hostname or "").lower()
    allowlist = settings.primary_source_allowlist_list
    on_allowlist = any(host == entry or host.endswith(f".{entry}") for entry in allowlist)
    aviso = None if on_allowlist else "Fonte fora da lista de domínios primários confiáveis."
    return _out(row, aviso=aviso)
