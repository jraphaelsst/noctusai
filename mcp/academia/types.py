"""Pydantic schemas — MCP tool INPUT only (CONTRACT §C).

Field names are PT-BR, exactly as the sibling's tools defined them and
as the CONTRACT §C "Change" column specifies — Julia's skills and tool
calls are already written against these names.

Every tool's OUTPUT is the bare HTTP-response envelope the client
returns (`{"ok": true, ...body}` / `{"ok": false, "error": {...}}}`,
CONTRACT §C) — this connector is a thin passthrough, so there are no
per-tool Output models to keep in lockstep with the server's response
shapes; the server owns those.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ─── academia.kb.* (CONTRACT §B.1 / §C) ──────────────────────────────────


class KbBuscarInput(BaseModel):
    """LEITURA — `GET /api/kb`. `pasta` (sibling) becomes
    `categoria[/subcategoria]` (CONTRACT §C)."""

    consulta: Optional[str] = Field(None, description="Full-text search over titulo/resumo/corpo_md.")
    categoria: Optional[str] = Field(None, description="Filter by categoria (replaces the sibling's `pasta`).")
    subcategoria: Optional[str] = Field(None, description="Filter by subcategoria.")
    tag: Optional[str] = Field(None, description="Filter by a single tag.")
    limite: int = Field(20, ge=1, le=200, description="Page size, max 200.")
    offset: int = Field(0, ge=0, description="Page offset.")


class KbLerInput(BaseModel):
    """LEITURA — `GET /api/kb/{slug}`. `caminho` (sibling) becomes `slug`."""

    slug: str = Field(..., description="The kb_entries.slug to fetch.")


class KbEscreverInput(BaseModel):
    """ESCRITA — `POST /api/kb` (modo=criar) or `PUT /api/kb/{slug}`
    (modo=atualizar). Never probes to decide which — `modo` is
    explicit."""

    modo: Literal["criar", "atualizar"] = Field(..., description="'criar' -> POST /api/kb; 'atualizar' -> PUT /api/kb/{slug}.")
    slug: Optional[str] = Field(None, description="Required when modo='atualizar'. Optional on 'criar' (server derives from titulo when omitted).")
    categoria: Optional[str] = Field(None, description="Required when modo='criar'.")
    subcategoria: Optional[str] = Field(None, description="Optional sub-folder within categoria.")
    titulo: Optional[str] = Field(None, description="Required when modo='criar'.")
    resumo: Optional[str] = Field(None, description="Short summary.")
    tags: Optional[list[str]] = Field(None, description="Free-form tags.")
    corpo_md: Optional[str] = Field(None, description="Required when modo='criar'.")
    motivo: str = Field(..., description="Required on every write (CONTRACT §B.1).")

    @model_validator(mode="after")
    def _check_mode_required_fields(self) -> "KbEscreverInput":
        if self.modo == "criar":
            missing = [f for f in ("categoria", "titulo", "corpo_md") if getattr(self, f) is None]
            if missing:
                raise ValueError(f"modo='criar' requires: {', '.join(missing)}")
        else:  # atualizar
            if self.slug is None:
                raise ValueError("modo='atualizar' requires: slug")
        return self


class KbMoverInput(BaseModel):
    """ESCRITA — `PUT /api/kb/{origem}` with `novo_slug=destino`."""

    origem: str = Field(..., description="Current slug.")
    destino: str = Field(..., description="New slug (sent as novo_slug).")
    motivo: str = Field(..., description="Required on every write.")


# ─── academia.decisao.* (CONTRACT §B.2 / §C) ─────────────────────────────


class DecisaoRegistrarInput(BaseModel):
    """ESCRITA — `POST /api/decisions`."""

    titulo: str
    contexto: Optional[str] = None
    decisao: str
    motivo: str
    alternativas_rejeitadas: Optional[str] = None
    relacionadas: Optional[list[str]] = Field(None, description="Related decision codes, e.g. ['D-10'].")


class DecisaoListarInput(BaseModel):
    """LEITURA — `GET /api/decisions?estado=`."""

    estado: Optional[str] = Field(None, description="Filter: 'vigente' or 'superseded'.")


class DecisaoSubstituirInput(BaseModel):
    """ESCRITA — `POST /api/decisions/{substitui}/supersede`. Body is the
    same shape as `decisao.registrar`; `substitui` is the path param
    (the decision code being superseded), not a body field."""

    substitui: str = Field(..., description="Code of the decision being superseded, e.g. 'D-10'.")
    titulo: str
    contexto: Optional[str] = None
    decisao: str
    motivo: str
    alternativas_rejeitadas: Optional[str] = None
    relacionadas: Optional[list[str]] = None


# ─── academia.pergunta.* (CONTRACT §B.3 / §C) ────────────────────────────


class PerguntaAdicionarInput(BaseModel):
    """ESCRITA — `POST /api/questions`."""

    pergunta: str
    por_que_importa: str
    bloqueia: str = Field(..., description="What this open question blocks, free text.")
    destino_kb: Optional[str] = Field(None, description="A kb_entries.slug the eventual answer should land in.")


class PerguntaListarInput(BaseModel):
    """LEITURA — `GET /api/questions?estado=`."""

    estado: Literal["aberta", "respondida", "todas"] = Field("aberta", description="Defaults to 'aberta'.")


class PerguntaResponderInput(BaseModel):
    """ESCRITA — `POST /api/questions/{codigo}/answer`."""

    codigo: str
    resposta: str


# ─── academia.historico.* (CONTRACT §B.5 / §C) ───────────────────────────


class HistoricoAppendInput(BaseModel):
    """ESCRITA — `POST /api/timeline`."""

    titulo: str
    descricao: str
    data: Optional[str] = Field(None, description="ISO date YYYY-MM-DD; defaults to today server-side when omitted.")


class HistoricoTimelineInput(BaseModel):
    """LEITURA — `GET /api/timeline?limite=`."""

    limite: int = Field(20, ge=1, le=500, description="Max 500.")


# ─── academia.roadmap.* / academia.tarefa.* (CONTRACT §B.4 / §C) ────────


class RoadmapLerInput(BaseModel):
    """LEITURA — `GET /api/roadmap`. No parameters."""


class RoadmapAtualizarInput(BaseModel):
    """ESCRITA — `PATCH /api/roadmap/{codigo}`."""

    codigo: str
    estado: Optional[str] = Field(None, description="'pendente' | 'em-andamento' | 'concluida' | 'cancelada'.")
    titulo: Optional[str] = None
    objetivo: Optional[str] = None
    concluida_quando: Optional[str] = None


class TarefaCriarInput(BaseModel):
    """ESCRITA — `POST /api/tasks`."""

    titulo: str
    fase: str = Field(..., description="A roadmap_phases.codigo. 422 if unknown.")
    detalhe: Optional[str] = None
    bloqueada_por: Optional[str] = None


class TarefaAtualizarInput(BaseModel):
    """ESCRITA — `PATCH /api/tasks/{codigo}`."""

    codigo: str
    estado: Optional[str] = Field(None, description="'pendente' | 'em-andamento' | 'concluida' | 'cancelada'.")
    detalhe: Optional[str] = None
    bloqueada_por: Optional[str] = None


class TarefaListarInput(BaseModel):
    """LEITURA — `GET /api/tasks?fase=&estado=`."""

    fase: Optional[str] = None
    estado: Optional[str] = None


class TarefaPrepararSessaoInput(BaseModel):
    """LEITURA — `GET /api/session-prep`. No parameters."""


# ─── academia.conteudo.* (CONTRACT §B.5 / §C) ────────────────────────────


class ConteudoSalvarInput(BaseModel):
    """ESCRITA — `POST /api/content`."""

    tipo: Literal["roteiro", "trilha", "quiz", "copy", "proposta", "outro"]
    titulo: str
    corpo_md: str
    referencia: Optional[str] = None
    fontes: Optional[list[str]] = Field(None, description="kb slugs the draft is sourced from.")


class ConteudoListarInput(BaseModel):
    """LEITURA — `GET /api/content?tipo=`."""

    tipo: Optional[str] = None


class ConteudoLerInput(BaseModel):
    """LEITURA — `GET /api/content/{codigo}`. `ler` takes `codigo`
    instead of the sibling's `caminho` (CONTRACT §C)."""

    codigo: str


# ─── academia.pesquisa.* (CONTRACT §B.5 / §C) ────────────────────────────


class PesquisaCapturarFonteInput(BaseModel):
    """ESCRITA — `POST /api/sources`. The sibling's `destino` path
    becomes `kb_slug` (CONTRACT §C)."""

    url: str
    titulo: str
    trecho_citado: str
    resumo: str
    kb_slug: str = Field(..., description="The kb_entries.slug this source is attached to. 404 if unknown.")
    vigencia_confirmada: bool
    exige_da_empresa: Optional[str] = None


__all__ = [
    "KbBuscarInput",
    "KbLerInput",
    "KbEscreverInput",
    "KbMoverInput",
    "DecisaoRegistrarInput",
    "DecisaoListarInput",
    "DecisaoSubstituirInput",
    "PerguntaAdicionarInput",
    "PerguntaListarInput",
    "PerguntaResponderInput",
    "HistoricoAppendInput",
    "HistoricoTimelineInput",
    "RoadmapLerInput",
    "RoadmapAtualizarInput",
    "TarefaCriarInput",
    "TarefaAtualizarInput",
    "TarefaListarInput",
    "TarefaPrepararSessaoInput",
    "ConteudoSalvarInput",
    "ConteudoListarInput",
    "ConteudoLerInput",
    "PesquisaCapturarFonteInput",
]
