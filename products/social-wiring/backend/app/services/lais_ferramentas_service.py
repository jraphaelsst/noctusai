"""The four read tools agents calls back during a Lais turn (contract A3 / 2.2).

Registry of tool implementations (waves 1 / 5 / 12 replace one line each, the router never changes):

    FERRAMENTAS: dict[str, Ferramenta]
    Ferramenta = Callable[[Any, UUID, dict], Any]      # (scoped client, org_id, validated args) -> JSON data
    ARGS[nome]  -> the StrictHttpModel the router validates the body with

  buscar_imoveis           F      Vista mirror `imoveis`, at most 5 results
  detalhes_imovel          F      wave 1 switches (lais_conhecimento_service.politica_endereco_iptu) ON `iptu` and the full `endereco`
  horarios_visita          wave 5 (config + SchedulingEngine); until then `[]`
  consultar_empreendimento wave 12; until then `[]`

PRIVACY (contract, binding): a tool NEVER returns owner/proprietario personal data. The row is read
with an explicit column allow-list and rebuilt field by field -- `corretores`, `vista_raw`,
`observacoes`, `chave`, matricula/inscricao and every owner column are unreachable by construction,
not filtered after the fact. Without the wave-1 switch the address is neighbourhood + city only.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

from app.services import lais_conhecimento_service

logger = logging.getLogger(__name__)

TABLE = "imoveis"
LIMITE_MAX = 5
#: Rows fetched before the unpublished ones are dropped in Python (`exibir_no_site` is nullable, so
#: a SQL `<> false` would also drop the NULLs). Bounded; the answer is still capped at `limite`.
OVERFETCH = 60
#: The ONLY columns a tool may read from `imoveis` (no owner / agent / internal columns).
COLUNAS = (
    "codigo, titulo, categoria, status, finalidades, bairro, cidade, uf, valor_venda, valor_locacao, "
    "valor_condominio, valor_iptu, dormitorios, suites, vagas, area_total, area_privativa, "
    "descricao_web, caracteristicas, exibir_no_site, logradouro, numero"
)


# ── request bodies (extra="forbid" via StrictHttpModel -> 422 invalid_field) ──
class BuscarImoveisArgs(StrictHttpModel):
    operacao: str = Field(pattern="^(compra|aluguel)$")
    bairro: Optional[str] = Field(default=None, max_length=120)
    cidade: Optional[str] = Field(default=None, max_length=120)
    tipo: Optional[str] = Field(default=None, max_length=80)
    preco_max: Optional[float] = Field(default=None, gt=0)
    quartos_min: Optional[int] = Field(default=None, ge=0, le=20)
    limite: int = Field(default=LIMITE_MAX, ge=1, le=LIMITE_MAX)


class DetalhesImovelArgs(StrictHttpModel):
    codigo: str = Field(min_length=1, max_length=40)


class HorariosVisitaArgs(StrictHttpModel):
    codigo: Optional[str] = Field(default=None, max_length=40)
    dias: int = Field(default=7, ge=1, le=7)


class ConsultarEmpreendimentoArgs(StrictHttpModel):
    nome: str = Field(min_length=1, max_length=120)


def _num(v: Any) -> Optional[float]:
    return float(v) if v is not None else None


def _titulo(row: dict[str, Any]) -> str:
    return (row.get("titulo") or row.get("categoria") or "Imóvel").strip()


def _publicado(row: dict[str, Any]) -> bool:
    """Julia never offers a listing the agency hides from its own site."""
    return row.get("exibir_no_site") is not False


def _preco(row: dict[str, Any], operacao: Optional[str]) -> Optional[float]:
    if operacao == "aluguel":
        return _num(row.get("valor_locacao"))
    if operacao == "compra":
        return _num(row.get("valor_venda"))
    return _num(row.get("valor_venda") if row.get("valor_venda") is not None else row.get("valor_locacao"))


def buscar_imoveis(client: Any, org_id: UUID, args: dict[str, Any]) -> list[dict[str, Any]]:
    a = BuscarImoveisArgs(**args)
    q = client.table(TABLE).select(COLUNAS).eq("org_id", str(org_id))
    q = q.contains("finalidades", ["venda" if a.operacao == "compra" else "aluguel"])
    if a.bairro:
        q = q.ilike("bairro", f"%{a.bairro}%")
    if a.cidade:
        q = q.ilike("cidade", f"%{a.cidade}%")
    if a.tipo:
        q = q.ilike("categoria", f"%{a.tipo}%")
    if a.quartos_min is not None:
        q = q.gte("dormitorios", a.quartos_min)
    if a.preco_max is not None:
        q = q.lte("valor_venda" if a.operacao == "compra" else "valor_locacao", a.preco_max)
    # Over-fetch: unpublished rows are dropped after the query, and the cap is on what Julia sees.
    rows = q.order("data_atualizacao", desc=True).limit(OVERFETCH).execute().data or []
    return [
        {
            "codigo": r["codigo"], "titulo": _titulo(r), "tipo": r.get("categoria"), "bairro": r.get("bairro"),
            "cidade": r.get("cidade"), "preco": _preco(r, a.operacao), "quartos": r.get("dormitorios"),
            # NOC-REMEDIATE[lais-imovel-link]: the public listing URL needs the org's site base URL, which wave 1 ("Meu negócio") stores; null until then — 2026-10-15
            "link": None,
        }
        for r in rows if _publicado(r)
    ][: a.limite]


def detalhes_imovel(client: Any, org_id: UUID, args: dict[str, Any]) -> dict[str, Any]:
    a = DetalhesImovelArgs(**args)
    rows = (
        client.table(TABLE).select(COLUNAS).eq("org_id", str(org_id)).eq("codigo_norm", a.codigo.strip().upper())
        .limit(1).execute().data or []
    )
    if not rows or not _publicado(rows[0]):
        return {"codigo": a.codigo.strip(), "encontrado": False}
    r = rows[0]
    # Wave 1 ("Meu negócio › Endereço e IPTU"): both default to withheld until the org opts in.
    politica = lais_conhecimento_service.politica_endereco_iptu(client, org_id)
    mostrar_iptu = politica["usar_iptu"]
    mostrar_endereco_completo = politica["endereco_completo"]
    endereco = ", ".join(p for p in (r.get("bairro"), r.get("cidade")) if p)
    if mostrar_endereco_completo:
        rua = " ".join(p for p in (r.get("logradouro"), r.get("numero")) if p)
        endereco = ", ".join(p for p in (rua, endereco) if p)
    return {
        "codigo": r["codigo"], "titulo": _titulo(r), "descricao": r.get("descricao_web"),
        "preco": _preco(r, None), "condominio": _num(r.get("valor_condominio")),
        "iptu": _num(r.get("valor_iptu")) if mostrar_iptu else None,
        "endereco": endereco, "caracteristicas": list(r.get("caracteristicas") or []),
        "encontrado": True,
    }


def horarios_visita(_client: Any, _org_id: UUID, args: dict[str, Any]) -> list[dict[str, Any]]:
    HorariosVisitaArgs(**args)
    # NOC-REMEDIATE[lais-horarios-visita]: wave 5 wires the visit-scheduling config + SchedulingEngine slots here — 2026-10-15
    return []


def consultar_empreendimento(_client: Any, _org_id: UUID, args: dict[str, Any]) -> list[dict[str, Any]]:
    ConsultarEmpreendimentoArgs(**args)
    # NOC-REMEDIATE[lais-empreendimentos]: wave 12 serves the empreendimento catalogue here — 2026-10-15
    return []


Ferramenta = Callable[[Any, UUID, dict[str, Any]], Any]

#: THE registry (nome -> implementation). The router validates `nome` against it, then calls it.
FERRAMENTAS: dict[str, Ferramenta] = {
    "buscar_imoveis": buscar_imoveis,
    "detalhes_imovel": detalhes_imovel,
    "horarios_visita": horarios_visita,
    "consultar_empreendimento": consultar_empreendimento,
}

#: nome -> the body model (so a wave that changes a tool's args changes it here, with the tool).
ARGS: dict[str, type[StrictHttpModel]] = {
    "buscar_imoveis": BuscarImoveisArgs,
    "detalhes_imovel": DetalhesImovelArgs,
    "horarios_visita": HorariosVisitaArgs,
    "consultar_empreendimento": ConsultarEmpreendimentoArgs,
}

__all__ = ["ARGS", "FERRAMENTAS", "Ferramenta", "COLUNAS"]
