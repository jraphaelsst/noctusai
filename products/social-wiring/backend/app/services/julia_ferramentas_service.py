"""The four read tools agents calls back during a Julia turn (contract A3 / 2.2).

Registry of tool implementations (waves 1 / 5 / 12 replace one line each, the router never changes):

    FERRAMENTAS: dict[str, Ferramenta]
    Ferramenta = Callable[[Any, UUID, dict], Any]      # (scoped client, org_id, validated args) -> JSON data
    ARGS[nome]  -> the StrictHttpModel the router validates the body with

  buscar_imoveis           F      Vista mirror `imoveis`, at most 5 results; v2: structured query, similar_a,
                                  excluir_codigos, one-axis-at-a-time widening (`julia_busca_imoveis`)
  imovel_campanha          v2     the lead's campaign listing (explicit `codigo`, or the contato's
                                  `codigo_imovel_campanha` via `interacao_id`)
  detalhes_imovel          F      wave 1 switches (julia_conhecimento_service.politica_endereco_iptu) ON `iptu` and the full `endereco`
  horarios_visita          wave 5 (config + SchedulingEngine), `julia_visitas_service`
  consultar_empreendimento development catalogue derived from `imoveis.empreendimento` / `construtora`

PRIVACY (contract, binding): a tool NEVER returns owner/proprietario personal data. The row is read
with an explicit column allow-list and rebuilt field by field -- `corretores`, `vista_raw`,
`observacoes`, `chave`, matricula/inscricao and every owner column are unreachable by construction,
not filtered after the fact. Without the wave-1 switch the address is neighbourhood + city only.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, NamedTuple, Optional
from uuid import UUID

from pydantic import Field, model_validator

from noctusai_lib.api import StrictHttpModel

from app.services import julia_busca_imoveis as busca
from app.services import julia_conhecimento_service, julia_eventos_service, julia_imovel_confirmado

logger = logging.getLogger(__name__)

TABLE = "imoveis"
LIMITE_MAX = 5
LIMITE_PADRAO = 3
#: Rows read for one search (PostgREST caps at 1000 anyway); `restantes_estimados` is a lower bound past this.
FETCH_BUSCA = 500
DESTAQUES_MAX = 3
#: Rows fetched before the unpublished ones are dropped in Python (`exibir_no_site` is nullable, so
#: a SQL `<> false` would also drop the NULLs). Bounded; the answer is still capped at `limite`.
OVERFETCH = 60
#: The ONLY columns a tool may read from `imoveis` (no owner / agent / internal columns).
COLUNAS = (
    "codigo, titulo, categoria, status, finalidades, bairro, cidade, uf, valor_venda, valor_locacao, "
    "valor_condominio, valor_iptu, dormitorios, suites, vagas, area_total, area_privativa, "
    "descricao_web, caracteristicas, exibir_no_site, logradouro, numero, data_atualizacao, empreendimento"
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
    """The structured query agents builds from the lead's COMPUTED values (`oferecer_imoveis`), field for field."""

    #: Optional: the turn's interacao (the agent has it in `estado.interacao_id`). Lets the lookup be tied to the
    #: lead for Relatorios "top imoveis"; never used for scoping (the org is the token's).
    interacao_id: Optional[UUID] = None
    operacao: str = Field(pattern="^(compra|aluguel)$")
    bairro: Optional[str] = Field(default=None, max_length=120)  # pre-v2 single region; merged into `bairros`
    bairros: list[str] = Field(default_factory=list, max_length=10)
    cidade: Optional[str] = Field(default=None, max_length=120)
    tipo: Optional[str] = Field(default=None, max_length=80)
    preco_min: Optional[float] = Field(default=None, gt=0)
    preco_max: Optional[float] = Field(default=None, gt=0)
    quartos_min: Optional[int] = Field(default=None, ge=0, le=20)
    vagas_min: Optional[int] = Field(default=None, ge=0, le=20)
    #: Must-haves (hard filters; mapped onto `imoveis.caracteristicas`, `pets` included).
    itens_essenciais: list[str] = Field(default_factory=list, max_length=20)
    #: Nice-to-haves (rank first, relaxed first). `caracteristicas` is what agents sends today: nice-to-have.
    itens_desejaveis: list[str] = Field(default_factory=list, max_length=20)
    caracteristicas: list[str] = Field(default_factory=list, max_length=20)
    similar_a: Optional[str] = Field(default=None, max_length=40)
    excluir_codigos: list[str] = Field(default_factory=list, max_length=200)
    limite: int = Field(default=LIMITE_PADRAO, ge=1, le=LIMITE_MAX)

    @model_validator(mode="after")
    def _faixa_coerente(self) -> "BuscarImoveisArgs":
        if self.preco_min is not None and self.preco_max is not None and self.preco_min > self.preco_max:
            raise ValueError("preco_min > preco_max")
        for lista in (self.bairros, self.itens_essenciais, self.itens_desejaveis, self.caracteristicas, self.excluir_codigos):
            if any(not isinstance(i, str) or len(i) > 120 for i in lista):
                raise ValueError("item too long")
        return self


class ImovelCampanhaArgs(StrictHttpModel):
    interacao_id: Optional[UUID] = None
    codigo: Optional[str] = Field(default=None, min_length=1, max_length=40)
    operacao: Optional[str] = Field(default=None, pattern="^(compra|aluguel)$")

    @model_validator(mode="after")
    def _algum(self) -> "ImovelCampanhaArgs":
        if not self.codigo and self.interacao_id is None:
            raise ValueError("codigo or interacao_id required")
        return self


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
    conf = julia_imovel_confirmado.aplicar(confirmacoes, data_atualizacao=row.get("data_atualizacao"), preco_tipo=preco_tipo)
    if conf is None:
        return
    if "preco" in conf:
        item["preco"] = conf["preco"]
    item["confirmacao_proprietario"] = conf


class ComMeta(NamedTuple):
    """A tool result with sibling keys next to `data` (`restantes_estimados`, `relaxado`)."""

    data: Any
    meta: dict[str, Any]


def regioes_adjacentes(client: Any, org_id: UUID) -> dict[str, tuple[str, ...]]:
    """normalised region -> normalised adjacent regions, org-configured.

    NOC-REMEDIATE[julia-v2-regioes-adjacentes]: no org-level adjacency map exists yet (RESEARCH 3: "adjacency map"
    in the org-specs template, filled in the app); until it does, the `regiao_adjacente` widening step has
    nothing to widen with and is skipped -- 2026-10-20
    """
    return {}


def _um(client: Any, org_id: UUID, codigo: str) -> Optional[dict[str, Any]]:
    rows = (
        client.table(TABLE).select(COLUNAS).eq("org_id", str(org_id)).eq("codigo_norm", codigo.strip().upper())
        .limit(1).execute().data or []
    )
    return rows[0] if rows and _publicado(rows[0]) else None


def _destaques(r: dict[str, Any], prioritarios: tuple[str, ...]) -> list[str]:
    """2-3 factual highlights, straight from the listing's own feature list (never invented): the lead's
    own items first."""
    carac = [c.strip() for c in (r.get("caracteristicas") or []) if isinstance(c, str) and c.strip()]
    pri = [c for c in carac if any(busca.norm(p) and busca.norm(p) in busca.norm(c) for p in prioritarios)]
    return (pri + [c for c in carac if c not in pri])[:DESTAQUES_MAX]


def _item(r: dict[str, Any], operacao: Optional[str], link: Callable[[str], Optional[str]],
          prioritarios: tuple[str, ...] = ()) -> dict[str, Any]:
    """One property for Julia's card. Fields the listing does not have are OMITTED, never estimated."""
    item = {
        "codigo": r["codigo"], "titulo": _titulo(r), "tipo": r.get("categoria"), "bairro": r.get("bairro"),
        "condominio": (r.get("empreendimento") or "").strip() or None, "cidade": r.get("cidade"),
        "preco": _preco(r, operacao), "preco_venda": _num(r.get("valor_venda")), "preco_aluguel": _num(r.get("valor_locacao")),
        "valor_condominio": _num(r.get("valor_condominio")),
        # Owner rule: a price is always shown with condominio + IPTU. Known => returned, unknown => omitted (never estimated).
        # (The wave-1 `usar_iptu` switch still governs `detalhes_imovel`.)
        "valor_iptu": _num(r.get("valor_iptu")),
        "area_m2": _num(r.get("area_privativa") if r.get("area_privativa") is not None else r.get("area_total")),
        "quartos": r.get("dormitorios"), "suites": r.get("suites"), "vagas": r.get("vagas"),
        "destaques": _destaques(r, prioritarios),
        # Owner, 2026-10-19: "Meu negócio › Perfil do WhatsApp" `link_imovel` template (default `{site}/imovel/{codigo}`).
        "link": link(r["codigo"]),
    }
    return {k: v for k, v in item.items() if v not in (None, "", [])}


def _itens(client: Any, org_id: UUID, linhas: list[dict[str, Any]], operacao: Optional[str],
           prioritarios: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    confirmados = julia_imovel_confirmado.carregar(client, org_id, (r["codigo"] for r in linhas))
    link = julia_conhecimento_service.link_imovel_fn(client, org_id)
    out = [_item(r, operacao, link, prioritarios) for r in linhas]
    for item, r in zip(out, linhas):
        _sobrepor_confirmacao(item, confirmados.get(str(r["codigo"]).strip().upper(), []), r,
                              "locacao" if operacao == "aluguel" else "venda")
    return out


def buscar_imoveis(client: Any, org_id: UUID, args: dict[str, Any]) -> ComMeta:
    """Search the org's published listings for the lead; see `julia_busca_imoveis` for the rules.

    Response: `{data: [item...], restantes_estimados, relaxado: [eixo...]}` (+ `similar_a_encontrado` when
    `similar_a` was sent). `restantes_estimados` = listings that passed at the final widening level and were not
    returned (a lower bound when more than FETCH_BUSCA candidates exist)."""
    a = BuscarImoveisArgs(**args)
    ancora = _um(client, org_id, a.similar_a) if a.similar_a else None
    excluir = [*a.excluir_codigos, *([a.similar_a] if a.similar_a else [])]
    regioes = [*([a.bairro] if a.bairro else []), *a.bairros]
    tipo, preco_min, preco_max = a.tipo, a.preco_min, a.preco_max
    if ancora is not None:
        # `similar_a`: whatever the lead did not state is taken from the campaign listing.
        tipo = tipo or ancora.get("categoria")
        if not regioes and ancora.get("bairro"):
            regioes = [ancora["bairro"]]
        ref = busca.preco_da_linha(ancora, a.operacao)
        if ref and preco_min is None and preco_max is None:
            preco_min = preco_max = ref
    q = busca.Consulta(
        operacao=a.operacao, tipo=tipo, preco_min=preco_min, preco_max=preco_max, quartos_min=a.quartos_min,
        vagas_min=a.vagas_min, regioes=tuple(regioes), cidade=a.cidade, essenciais=tuple(a.itens_essenciais),
        desejaveis=tuple([*a.itens_desejaveis, *a.caracteristicas]),
        condominio=(ancora or {}).get("empreendimento"), adjacentes=regioes_adjacentes(client, org_id),
    )
    col = "valor_venda" if a.operacao == "compra" else "valor_locacao"
    qb = client.table(TABLE).select(COLUNAS).eq("org_id", str(org_id)).contains("finalidades", ["venda" if a.operacao == "compra" else "aluguel"])
    if busca.piso(q) is not None:
        qb = qb.gte(col, busca.piso(q))
    if busca.teto_largo(q) is not None:
        qb = qb.lte(col, busca.teto_largo(q))
    if busca.quartos_minimos_largos(q) is not None:
        qb = qb.gte("dormitorios", busca.quartos_minimos_largos(q))
    if q.vagas_min is not None:
        qb = qb.gte("vagas", q.vagas_min)
    rows = [r for r in (qb.order("data_atualizacao", desc=True).limit(FETCH_BUSCA).execute().data or []) if _publicado(r)]
    res = busca.buscar(rows, q, limite=a.limite, excluir=excluir)
    meta: dict[str, Any] = {"restantes_estimados": res.restantes, "relaxado": res.relaxado}
    if a.similar_a:
        meta["similar_a_encontrado"] = ancora is not None
    return ComMeta(_itens(client, org_id, res.linhas, a.operacao, (*a.itens_essenciais, *a.itens_desejaveis, *a.caracteristicas)), meta)


def imovel_campanha(client: Any, org_id: UUID, args: dict[str, Any]) -> list[dict[str, Any]]:
    """The lead's campaign listing as a 0-or-1 item list (same card shape as `buscar_imoveis`), for
    `oferecer_imoveis modo=campanha`. `codigo` wins; else it is read from the contato's
    `julia_contatos.codigo_imovel_campanha` via `interacao_id` (org-scoped). Unpublished / unknown => `[]`."""
    a = ImovelCampanhaArgs(**args)
    codigo = a.codigo
    if not codigo:
        inter = (
            client.table("julia_interacoes").select("contato_id").eq("org_id", str(org_id))
            .eq("id", str(a.interacao_id)).limit(1).execute().data or []
        )
        if inter and inter[0].get("contato_id"):
            contato = (
                client.table("julia_contatos").select("codigo_imovel_campanha").eq("org_id", str(org_id))
                .eq("id", str(inter[0]["contato_id"])).limit(1).execute().data or []
            )
            codigo = (contato[0].get("codigo_imovel_campanha") or "").strip() if contato else None
    r = _um(client, org_id, codigo) if codigo else None
    if r is None:
        return []
    operacao = a.operacao or ("compra" if r.get("valor_venda") is not None else "aluguel")
    return _itens(client, org_id, [r], operacao)


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
    politica = julia_conhecimento_service.politica_endereco_iptu(client, org_id)
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
        "link": julia_conhecimento_service.link_imovel_fn(client, org_id)(r["codigo"]),
        "encontrado": True,
    }
    confirmacoes = julia_imovel_confirmado.carregar(client, org_id, [r["codigo"]]).get(str(r["codigo"]).strip().upper(), [])
    _sobrepor_confirmacao(resultado, confirmacoes, r, "venda" if r.get("valor_venda") is not None else "locacao")
    return resultado


def horarios_visita(client: Any, org_id: UUID, args: dict[str, Any]) -> list[dict[str, Any]]:
    """Free 30-min slots from the wave-5 config + the seed SchedulingEngine (`julia_visitas_service`)."""
    from app.services import julia_visitas_service

    parsed = HorariosVisitaArgs(**args)
    return julia_visitas_service.horarios_para_ferramenta(client, org_id, parsed.dias)


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
                client.table("julia_interacoes").select("contato_id").eq("org_id", str(org_id))
                .eq("id", str(interacao_id)).limit(1).execute().data or []
            )
            contato_id = rows[0]["contato_id"] if rows else None
        except Exception:
            logger.exception("julia: could not resolve the contato of interacao for a lookup event (org=%s)", org_id)
    julia_eventos_service.emitir(
        client, org_id, "imovel_consultado", contato_id,
        {"ferramenta": nome, "codigos": codigos, "interacao_id": str(interacao_id) if interacao_id else None},
    )


Ferramenta = Callable[[Any, UUID, dict[str, Any]], Any]

#: THE registry (nome -> implementation). The router validates `nome` against it, then calls it.
FERRAMENTAS: dict[str, Ferramenta] = {
    "buscar_imoveis": buscar_imoveis,
    "imovel_campanha": imovel_campanha,
    "detalhes_imovel": detalhes_imovel,
    "horarios_visita": horarios_visita,
    "consultar_empreendimento": consultar_empreendimento,
}

#: nome -> the body model (so a wave that changes a tool's args changes it here, with the tool).
ARGS: dict[str, type[StrictHttpModel]] = {
    "buscar_imoveis": BuscarImoveisArgs,
    "imovel_campanha": ImovelCampanhaArgs,
    "detalhes_imovel": DetalhesImovelArgs,
    "horarios_visita": HorariosVisitaArgs,
    "consultar_empreendimento": ConsultarEmpreendimentoArgs,
}

__all__ = ["ARGS", "ComMeta", "FERRAMENTAS", "Ferramenta", "COLUNAS", "registrar_consulta"]
