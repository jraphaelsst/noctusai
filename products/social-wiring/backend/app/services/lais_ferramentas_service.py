"""The four read tools agents calls back during a Lais turn (contract A3 / 2.2).

Registry of tool implementations (waves 1 / 5 / 12 replace one line each, the router never changes):

    FERRAMENTAS: dict[str, Ferramenta]
    Ferramenta = Callable[[Any, UUID, dict], Any]      # (scoped client, org_id, validated args) -> JSON data
    ARGS[nome]  -> the StrictHttpModel the router validates the body with

  buscar_imoveis           F      Vista mirror `imoveis`, at most 5 results
  detalhes_imovel          F      wave 1 switches (lais_conhecimento_service.politica_endereco_iptu) ON `iptu` and the full `endereco`
  horarios_visita          wave 5 (config + SchedulingEngine), `lais_visitas_service`
  consultar_empreendimento development catalogue derived from `imoveis.empreendimento` / `construtora`

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

from app.services import lais_conhecimento_service, lais_eventos_service, lais_imovel_confirmado

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
    "descricao_web, caracteristicas, exibir_no_site, logradouro, numero, data_atualizacao"
)
#: Allow-list for the empreendimento tool (a subset of `COLUNAS` + the two development columns).
COLUNAS_EMPREENDIMENTO = (
    "codigo, titulo, categoria, empreendimento, construtora, bairro, cidade, valor_venda, valor_locacao, "
    "dormitorios, area_privativa, exibir_no_site"
)
OVERFETCH_EMPREENDIMENTO = 200
EMPREENDIMENTOS_MAX = 3
EXEMPLOS_MAX = 5


# ── request bodies (extra="forbid" via StrictHttpModel -> 422 invalid_field) ──
class BuscarImoveisArgs(StrictHttpModel):
    #: Optional: the turn's interacao (the agent has it in `estado.interacao_id`). Lets the lookup be tied to the
    #: lead for Relatorios "top imoveis"; never used for scoping (the org is the token's).
    interacao_id: Optional[UUID] = None
    operacao: str = Field(pattern="^(compra|aluguel)$")
    bairro: Optional[str] = Field(default=None, max_length=120)
    cidade: Optional[str] = Field(default=None, max_length=120)
    tipo: Optional[str] = Field(default=None, max_length=80)
    preco_max: Optional[float] = Field(default=None, gt=0)
    quartos_min: Optional[int] = Field(default=None, ge=0, le=20)
    limite: int = Field(default=LIMITE_MAX, ge=1, le=LIMITE_MAX)


class DetalhesImovelArgs(StrictHttpModel):
    interacao_id: Optional[UUID] = None
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


def _sobrepor_confirmacao(item: dict[str, Any], confirmacoes: list[dict[str, Any]], row: dict[str, Any],
                          preco_tipo: Optional[str]) -> None:
    """Owner-confirmed status/price newer than Vista's value wins, ALWAYS with its provenance (additive key
    `confirmacao_proprietario`, present only when a confirmation applies)."""
    conf = lais_imovel_confirmado.aplicar(confirmacoes, data_atualizacao=row.get("data_atualizacao"), preco_tipo=preco_tipo)
    if conf is None:
        return
    if "preco" in conf:
        item["preco"] = conf["preco"]
    item["confirmacao_proprietario"] = conf


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
    publicados = [r for r in rows if _publicado(r)][: a.limite]
    confirmados = lais_imovel_confirmado.carregar(client, org_id, (r["codigo"] for r in publicados))
    out = [
        {
            "codigo": r["codigo"], "titulo": _titulo(r), "tipo": r.get("categoria"), "bairro": r.get("bairro"),
            "cidade": r.get("cidade"), "preco": _preco(r, a.operacao), "quartos": r.get("dormitorios"),
            # NOC-REMEDIATE[lais-imovel-link]: OWNER QUESTION -- `imoveis` (Vista mirror, migrations 040/093) has NO per-listing URL column (only foto_destaque/fotos/video_destaque/tour_360) and Vista's `Imovel` payload the sync normalises carries no site URL, so the public listing path is not derivable from data. What is the public URL pattern of the imobiliaria site for a listing (e.g. `<site>/imovel/<codigo>`; per org or a single Vista site template)? Once answered: store the path template next to `site` in "Meu negócio" and build `link` from it here -- 2026-10-16
            "link": None,
        }
        for r in publicados
    ]
    for item, r in zip(out, publicados):
        _sobrepor_confirmacao(item, confirmados.get(str(r["codigo"]).strip().upper(), []), r,
                              "venda" if a.operacao == "compra" else "locacao")
    return out


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
    resultado = {
        "codigo": r["codigo"], "titulo": _titulo(r), "descricao": r.get("descricao_web"),
        "preco": _preco(r, None), "condominio": _num(r.get("valor_condominio")),
        "iptu": _num(r.get("valor_iptu")) if mostrar_iptu else None,
        "endereco": endereco, "caracteristicas": list(r.get("caracteristicas") or []),
        "encontrado": True,
    }
    confirmacoes = lais_imovel_confirmado.carregar(client, org_id, [r["codigo"]]).get(str(r["codigo"]).strip().upper(), [])
    _sobrepor_confirmacao(resultado, confirmacoes, r, "venda" if r.get("valor_venda") is not None else "locacao")
    return resultado


def horarios_visita(client: Any, org_id: UUID, args: dict[str, Any]) -> list[dict[str, Any]]:
    """Free 30-min slots from the wave-5 config + the seed SchedulingEngine (`lais_visitas_service`)."""
    from app.services import lais_visitas_service

    parsed = HorariosVisitaArgs(**args)
    return lais_visitas_service.horarios_para_ferramenta(client, org_id, parsed.dias)


def _faixa(valores: list[float]) -> Optional[dict[str, float]]:
    return {"min": min(valores), "max": max(valores)} if valores else None


def consultar_empreendimento(client: Any, org_id: UUID, args: dict[str, Any]) -> list[dict[str, Any]]:
    """Empreendimentos (building / development) matching `nome`, built from the Vista mirror.

    SW has no separate catalogue: Vista sends `Empreendimento` + `Construtora` per listing and the sync
    stores them on `imoveis` (migration 040), so a development IS the set of published listings sharing
    that name. Same allow-list + published-only rules as `buscar_imoveis` (no owner data, ever)."""
    a = ConsultarEmpreendimentoArgs(**args)
    rows = (
        client.table(TABLE).select(COLUNAS_EMPREENDIMENTO).eq("org_id", str(org_id))
        .ilike("empreendimento", f"%{a.nome.strip()}%").order("data_atualizacao", desc=True)
        .limit(OVERFETCH_EMPREENDIMENTO).execute().data or []
    )
    grupos: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        nome = (r.get("empreendimento") or "").strip()
        if nome and _publicado(r):
            grupos.setdefault(nome.casefold(), []).append(r)
    out: list[dict[str, Any]] = []
    for unidades in sorted(grupos.values(), key=lambda g: (-len(g), g[0]["empreendimento"]))[:EMPREENDIMENTOS_MAX]:
        def nums(campo: str, _u: list[dict[str, Any]] = unidades) -> list[float]:
            return [float(r[campo]) for r in _u if r.get(campo) is not None]

        construtora = next((r["construtora"].strip() for r in unidades if (r.get("construtora") or "").strip()), None)
        out.append({
            "nome": unidades[0]["empreendimento"].strip(), "construtora": construtora,
            "bairro": unidades[0].get("bairro"), "cidade": unidades[0].get("cidade"),
            "unidades": len(unidades),
            "tipos": sorted({(r.get("categoria") or "").strip() for r in unidades if (r.get("categoria") or "").strip()}),
            "quartos": _faixa(nums("dormitorios")), "area_privativa": _faixa(nums("area_privativa")),
            "preco_venda": _faixa(nums("valor_venda")), "preco_locacao": _faixa(nums("valor_locacao")),
            "exemplos": [
                {"codigo": r["codigo"], "titulo": _titulo(r), "tipo": r.get("categoria"), "quartos": r.get("dormitorios"),
                 "preco": _preco(r, None)}
                for r in unidades[:EXEMPLOS_MAX]
            ],
        })
    return out


#: Tools whose successful lookups feed Relatorios "top imoveis".
CONSULTAS_REGISTRADAS = ("buscar_imoveis", "detalhes_imovel")


def _codigos_consultados(nome: str, data: Any) -> list[str]:
    if nome == "buscar_imoveis":
        return [str(d["codigo"]) for d in (data or []) if d.get("codigo")]
    if nome == "detalhes_imovel" and isinstance(data, dict) and data.get("encontrado"):
        return [str(data["codigo"])]
    return []


def registrar_consulta(client: Any, org_id: UUID, nome: str, args: dict[str, Any], data: Any) -> None:
    """Record one `imovel_consultado` event for a successful lookup (codes returned / code viewed).

    Best-effort and org-scoped: the contato is resolved from `interacao_id` only inside the caller's org, and a
    failure here never reaches the tool response (emitir never raises; the lookup below is guarded)."""
    if nome not in CONSULTAS_REGISTRADAS:
        return
    codigos = _codigos_consultados(nome, data)
    if not codigos:
        return
    interacao_id = args.get("interacao_id")
    contato_id = None
    if interacao_id:
        try:
            rows = (
                client.table("lais_interacoes").select("contato_id").eq("org_id", str(org_id))
                .eq("id", str(interacao_id)).limit(1).execute().data or []
            )
            contato_id = rows[0]["contato_id"] if rows else None
        except Exception:
            logger.exception("lais: could not resolve the contato of interacao for a lookup event (org=%s)", org_id)
    lais_eventos_service.emitir(
        client, org_id, "imovel_consultado", contato_id,
        {"ferramenta": nome, "codigos": codigos, "interacao_id": str(interacao_id) if interacao_id else None},
    )


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

__all__ = ["ARGS", "FERRAMENTAS", "Ferramenta", "COLUNAS", "registrar_consulta"]
