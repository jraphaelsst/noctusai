"""Where Julia's listing tools read the property catalog from (julia-v3, CONTRACT 12.7).

`CatalogoImoveis` is the seam `julia_ferramentas_service` reads through. Two implementations, picked PER ORG by
`julia_catalogo_config.fonte` (migration 314; a missing row = `espelho`, i.e. nothing changes until an admin flips it):

  EspelhoCatalogo  the `imoveis` table (the Vista mirror) -- the behaviour Julia has always had
  VistaCatalogo    Vista LIVE through the seed `VistaCRMAdapter` (`search_imoveis` / `get_imovel`)

Both hand the tools the SAME row shape (the mirror's column names), so `julia_busca_imoveis` (ranking / widening),
`_item` (the card) and the owner-confirmed price override are untouched by the source. PRIVACY: a Vista row is rebuilt
field by field from the allow-list below -- `corretores`, `vista_raw`, `observacoes`, `chave`, matricula/inscricao and
every owner column are unreachable by construction, same as the mirror's `COLUNAS`.

A Vista failure is `catalogo_indisponivel` (503) -- never a silent fallback to the mirror (a stale answer that looks
fresh is worse than an honest "unavailable").

TOOL ARG -> VISTA `filter` (server-side narrowing; `julia_busca_imoveis` still applies every rule in Python on the rows):

  operacao compra|aluguel     Status in [Venda|Aluguel, "Venda e Aluguel"]
  (always)                    ExibirNoSite = "Sim"  (+ the Python published check: a listing the agency hides is never offered)
  preco_min/preco_max         ValorVenda|ValorLocacao: the WIDEST band any widening step can reach (-15% / +20%), as a
                              range, or [">=", lo] / ["<=", hi] when one-sided
  quartos_min                 Dormitorios [">=", quartos_min - 1]  (the tipologia widening lowers it by one)
  vagas_min                   Vagas [">=", n]
  cidade                      Cidade ["like", "%cidade%"]
  bairro(s)                   Bairro ["like", "%bairro%"], one query per region (<= MAX_REGIOES_SERVIDOR); the Python
                              match (bairro OR empreendimento, accent/case folded) decides what passes
  tipo                        NOT sent: `tipo` is a catalogue-vocabulary stem match and the tipologia widening drops it
  excluir_codigos             NOT sent: applied in Python (a `!=` filter holds one value)
  similar_a                   `um(codigo)` (detalhes); bairro / price band derived exactly as for the mirror
  ordering                    DataAtualizacao desc; at most FETCH_BUSCA candidates (DETALHES_MAX when features were asked)

Features (`caracteristicas`) exist only on `detalhes`, one call each: they are fetched for the candidates only when the
lead asked for items (essenciais / desejaveis), capped at DETALHES_MAX; otherwise just for the <= 5 returned listings.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable, Optional, Protocol, TypeVar
from uuid import UUID

from noctusai_lib.domain.real_estate import Imovel
from noctusai_lib.primitives.exceptions import AppException

from app.services import julia_busca_imoveis as busca

logger = logging.getLogger(__name__)

T = TypeVar("T")

T_CONFIG = "julia_catalogo_config"
FONTES = ("vista", "espelho")
FONTE_PADRAO = "espelho"

TABLE = "imoveis"
#: Rows read for one search (PostgREST caps at 1000 anyway); `restantes_estimados` is a lower bound past this.
FETCH_BUSCA = 500
#: The ONLY columns a tool may read from `imoveis` (no owner / agent / internal columns).
COLUNAS = (
    "codigo, titulo, categoria, status, finalidades, bairro, cidade, uf, valor_venda, valor_locacao, "
    "valor_condominio, valor_iptu, dormitorios, suites, vagas, area_total, area_privativa, "
    "descricao_web, caracteristicas, exibir_no_site, logradouro, numero, data_atualizacao, empreendimento, "
    "pavimentos"
)
#: Candidates enriched with `detalhes` (one HTTP call each) when the lead asked for features.
DETALHES_MAX = 60
MAX_REGIOES_SERVIDOR = 3


def publicado(row: dict[str, Any]) -> bool:
    """Julia never offers a listing the agency hides from its own site (`exibir_no_site` is nullable: NULL = shown)."""
    return row.get("exibir_no_site") is not False


class CatalogoImoveis(Protocol):
    """What the listing tools need from a catalog. Rows use the mirror's column names (see COLUNAS)."""

    def um(self, codigo: str) -> Optional[dict[str, Any]]:
        """One PUBLISHED listing by code, or None (unknown / unpublished)."""
        ...

    def candidatos(self, q: busca.Consulta) -> list[dict[str, Any]]:
        """Published listings that may satisfy `q` after the widest widening (a superset: `busca.buscar` decides)."""
        ...

    def completar(self, linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """The returned listings with every field the card needs (features need a second read on Vista)."""
        ...


class EspelhoCatalogo:
    """The `imoveis` mirror -- exactly what Julia read before the live catalog existed."""

    def __init__(self, client: Any, org_id: UUID):
        self._client, self._org = client, org_id

    def um(self, codigo: str) -> Optional[dict[str, Any]]:
        rows = (
            self._client.table(TABLE).select(COLUNAS).eq("org_id", str(self._org)).eq("codigo_norm", codigo.strip().upper())
            .limit(1).execute().data or []
        )
        return rows[0] if rows and publicado(rows[0]) else None

    def candidatos(self, q: busca.Consulta) -> list[dict[str, Any]]:
        col = "valor_venda" if q.operacao == "compra" else "valor_locacao"
        qb = (
            self._client.table(TABLE).select(COLUNAS).eq("org_id", str(self._org))
            .contains("finalidades", ["venda" if q.operacao == "compra" else "aluguel"])
        )
        if busca.piso(q) is not None:
            qb = qb.gte(col, busca.piso(q))
        if busca.teto_largo(q) is not None:
            qb = qb.lte(col, busca.teto_largo(q))
        if busca.quartos_minimos_largos(q) is not None:
            qb = qb.gte("dormitorios", busca.quartos_minimos_largos(q))
        if q.vagas_min is not None:
            qb = qb.gte("vagas", q.vagas_min)
        return [r for r in (qb.order("data_atualizacao", desc=True).limit(FETCH_BUSCA).execute().data or []) if publicado(r)]

    def completar(self, linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return linhas


# ── Vista live ───────────────────────────────────────────────────────────────
def linha_de_imovel(i: Imovel) -> dict[str, Any]:
    """Vista `Imovel` -> the mirror's row shape, field by field (the privacy allow-list: nothing else is copied)."""
    return {
        "codigo": i.codigo, "titulo": i.titulo, "categoria": i.categoria, "status": i.status,
        "finalidades": sorted(i.finalidades), "bairro": i.bairro, "cidade": i.cidade, "uf": i.uf,
        "valor_venda": i.valor_venda, "valor_locacao": i.valor_locacao, "valor_condominio": i.valor_condominio,
        "valor_iptu": i.valor_iptu, "dormitorios": i.dormitorios, "suites": i.suites, "vagas": i.vagas,
        "area_total": i.area_total, "area_privativa": i.area_privativa, "descricao_web": i.descricao_web,
        "caracteristicas": sorted(i.caracteristicas), "exibir_no_site": i.exibir_no_site,
        "logradouro": i.logradouro, "numero": i.numero,
        "data_atualizacao": i.data_atualizacao.isoformat() if isinstance(i.data_atualizacao, date) else None,
        "empreendimento": i.empreendimento, "pavimentos": i.pavimentos,
    }


def _faixa(lo: Optional[float], hi: Optional[float]) -> Any:
    if lo is not None and hi is not None:
        return [lo, hi]
    return [">=", lo] if lo is not None else ["<=", hi]


def filtros_vista(q: busca.Consulta) -> list[dict[str, Any]]:
    """The Vista `filter` dict(s) for a query (more than one when several regions are queried one by one)."""
    base: dict[str, Any] = {
        "Status": ["Venda", "Venda e Aluguel"] if q.operacao == "compra" else ["Aluguel", "Venda e Aluguel"],
        "ExibirNoSite": "Sim",
    }
    lo, hi = busca.piso(q), busca.teto_largo(q)
    if lo is not None or hi is not None:
        base["ValorVenda" if q.operacao == "compra" else "ValorLocacao"] = _faixa(lo, hi)
    quartos = busca.quartos_minimos_largos(q)
    if quartos:
        base["Dormitorios"] = [">=", quartos]
    if q.vagas_min:
        base["Vagas"] = [">=", q.vagas_min]
    if q.cidade:
        base["Cidade"] = ["like", f"%{q.cidade.strip()}%"]
    regioes = [r.strip() for r in q.regioes if r and r.strip()]
    if regioes and len(regioes) <= MAX_REGIOES_SERVIDOR:
        return [{**base, "Bairro": ["like", f"%{r}%"]} for r in regioes]
    return [base]


def indisponivel(exc: BaseException) -> AppException:
    logger.error("julia: Vista catalog unavailable (%s)", type(exc).__name__)
    return AppException("catalogo_indisponivel", "O catálogo de imóveis está indisponível agora.", status_code=503)


class VistaCatalogo:
    """Vista LIVE through the seed `VistaCRMAdapter` (a Fake in tests, the REST adapter in prod)."""

    def __init__(self, adapter: Any):
        self._adapter = adapter
        self._com_detalhes: set[str] = set()

    def _run(self, coro: Awaitable[T]) -> T:
        # The tools are sync (FastAPI worker thread, no running loop); the seed adapter is async.
        try:
            return asyncio.run(coro)  # type: ignore[arg-type]
        except AppException:
            raise
        except Exception as exc:  # noqa: BLE001 -- every upstream/transport/parse failure is ONE typed, logged error
            raise indisponivel(exc) from exc

    def um(self, codigo: str) -> Optional[dict[str, Any]]:
        imovel = self._run(self._adapter.get_imovel(codigo.strip().upper()))
        if imovel is None:
            return None
        row = linha_de_imovel(imovel)
        self._com_detalhes.add(imovel.codigo)
        return row if publicado(row) else None

    def candidatos(self, q: busca.Consulta) -> list[dict[str, Any]]:
        com_itens = bool(q.essenciais or q.desejaveis)
        limite = DETALHES_MAX if com_itens else FETCH_BUSCA

        async def varrer() -> list[dict[str, Any]]:
            vistos: dict[str, dict[str, Any]] = {}
            for filtro in filtros_vista(q):
                pagina = await self._adapter.search_imoveis(
                    filter_=filtro, order={"DataAtualizacao": "desc"}, max_results=limite, with_detalhes=com_itens,
                )
                for imovel in pagina.items:
                    vistos.setdefault(imovel.codigo, linha_de_imovel(imovel))
                    if com_itens:
                        self._com_detalhes.add(imovel.codigo)
            return list(vistos.values())

        alvo = "venda" if q.operacao == "compra" else "aluguel"
        rows = self._run(varrer())
        # `finalidades` comes from Vista's Status; a listing of the other operation never passes.
        return [r for r in rows if publicado(r) and alvo in (r.get("finalidades") or [])]

    def completar(self, linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        faltam = [r["codigo"] for r in linhas if r["codigo"] not in self._com_detalhes]
        if not faltam:
            return linhas

        async def detalhar() -> dict[str, dict[str, Any]]:
            pagina = await self._adapter.search_imoveis(
                filter_={"Codigo": faltam, "ExibirNoSite": "Sim"}, max_results=len(faltam), with_detalhes=True,
            )
            return {i.codigo: linha_de_imovel(i) for i in pagina.items}

        completos = self._run(detalhar())
        self._com_detalhes.update(completos)
        return [completos.get(r["codigo"], r) for r in linhas]


# ── per-org selection ────────────────────────────────────────────────────────
#: DI slot: a zero-arg factory returning the `VistaCRMAdapter` (tests configure a Fake; None = build the real adapter).
_adapter_factory: Optional[Callable[[], Any]] = None


def configure_vista_adapter(factory: Optional[Callable[[], Any]]) -> None:
    """Install (or, with None, clear) the adapter factory used by `VistaCatalogo`."""
    global _adapter_factory
    _adapter_factory = factory


def _adapter_vista() -> Any:
    from noctusai_lib.integrations.vista import VistaError, VistaNotConfigured, VistaRESTAdapter

    from app.config import settings

    if _adapter_factory is not None:
        try:
            return _adapter_factory()
        except VistaError as exc:
            raise indisponivel(exc) from exc
    # NOC-REMEDIATE[vista-key-per-org]: the Vista key is env-level (`VISTA_API_KEY`) -- one tenant for every org. Per-org
    # keys (`integration_accounts`) are needed before a second org can pick `vista` for ITS own Vista account -- 2026-11-03
    try:
        return VistaRESTAdapter(base_url=settings.crm_base_url, api_key=settings.crm_api_key)
    except VistaNotConfigured as exc:
        raise indisponivel(exc) from exc


def fonte_da_org(client: Any, org_id: UUID | str) -> str:
    rows = client.table(T_CONFIG).select("fonte").eq("org_id", str(org_id)).limit(1).execute().data or []
    fonte = rows[0].get("fonte") if rows else None
    return fonte if fonte in FONTES else FONTE_PADRAO


def catalogo_da_org(client: Any, org_id: UUID) -> CatalogoImoveis:
    """The catalog this org's Julia reads. An unreadable config is an error, never a silent default."""
    if fonte_da_org(client, org_id) == "vista":
        return VistaCatalogo(_adapter_vista())
    return EspelhoCatalogo(client, org_id)


def obter_config(client: Any, org_id: UUID | str) -> dict[str, Any]:
    rows = client.table(T_CONFIG).select("fonte, updated_by, updated_at").eq("org_id", str(org_id)).limit(1).execute().data or []
    row = rows[0] if rows else {}
    return {"fonte": fonte_da_org(client, org_id), "fontes": list(FONTES), "padrao": FONTE_PADRAO,
            "updated_by": row.get("updated_by"), "updated_at": row.get("updated_at")}


def salvar_fonte(client: Any, org_id: UUID | str, fonte: str, user_id: Optional[str]) -> dict[str, Any]:
    if fonte not in FONTES:
        raise AppException("fonte_invalida", "Use 'vista' ou 'espelho'.", status_code=422)
    agora = datetime.now(timezone.utc).isoformat()
    patch = {"fonte": fonte, "updated_by": str(user_id) if user_id else None, "updated_at": agora}
    existe = client.table(T_CONFIG).select("org_id").eq("org_id", str(org_id)).limit(1).execute().data or []
    if existe:
        client.table(T_CONFIG).update(patch).eq("org_id", str(org_id)).execute()
    else:
        client.table(T_CONFIG).insert({"org_id": str(org_id), **patch}).execute()
    return obter_config(client, org_id)


__all__ = [
    "COLUNAS", "CatalogoImoveis", "EspelhoCatalogo", "FETCH_BUSCA", "FONTES", "VistaCatalogo", "catalogo_da_org",
    "configure_vista_adapter", "filtros_vista", "fonte_da_org", "linha_de_imovel", "obter_config", "publicado", "salvar_fonte",
]
