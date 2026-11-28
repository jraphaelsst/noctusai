"""Fill `imovel_video_youtube` from the videos that ALREADY exist in Vista (project `julia-videos-prontos-youtube`, slice S3).

Vista keeps a listing's videos in the `Video` relation of `/imoveis/detalhes` (never in the root fields, so the imóveis sync and the
`social_wiring.imoveis` mirror have none). This walks the org's `imovel_registry` (the permanent identity, the FK target of the
field), asks Vista for each code's `Video` relation (seed `VistaCRMAdapter.list_imovel_videos` -- paced + retried by the org's own
`vista:<org>` bucket, the same chokepoint the imóveis sync uses) and records the chosen video with `origem='vista'` through S1's
`definir` (which NEVER writes back to Vista for that origem; this module additionally hands it a Vista provider that refuses).

    svc = build_imovel_videos_vista_import_service(client, adapter)   # client = the social_wiring-scoped admin client
    relatorio = await svc.importar(org_id, dry_run=True, codigos=None, limite=None)   -> Relatorio

SELECTION (owner-approved 2026-11-27):
  1. Eligible = `Tipo` "youtube" (bare id or URL), or any other `Tipo` whose value is a YouTube URL. A `/shorts/` link or a `Tipo`
     naming a short is NOT eligible (`short_ignorado`); anything else is `nao_youtube`.
  2. Several eligible -> the one with `Destaque == "Sim"`; otherwise the FIRST by `VideoCodigo` ascending (numeric; ties keep Vista's
     arrival order) -- the order `parse_imovel_videos` returns.
  3. NEVER overwrite a row whose origem is `julia` or `manual` (`mantido_julia_manual`). Only create a missing row (`criaria` /
     `criados`) or update an `origem='vista'` row whose id differs (`atualizaria` / `atualizados`). The same id = `ja_igual`.

`dry_run=True` (the default) makes ZERO writes. A re-run is idempotent (an applied row is `ja_igual` next time). Before a real write
the row is re-read, so a Julia/manual value set while the run was going is never overwritten (`definir` itself is a no-op on the
same id).

Vista outcomes per code: `VistaRecordUnpublished` with the `Corretor` stub = a hidden listing (`nao_publicado`); with an empty body or
an HTTP 404 = no such code in Vista (`nao_encontrado`; a registry code that came from a lead, or was deleted). Any other failure is
`erros` (class name only: a Vista 401 body embeds the key); `MAX_ERROS_SEGUIDOS` in a row aborts the run (`abortada`) instead of
burning the org's whole Vista budget on a revoked key.

RUN REGISTRY: a long run (2,283 codes at the 5 req/s budget is ~8 min) is started in the background by the router; its live
`Relatorio` lives in the in-process `EXECUCOES` (the product runs ONE uvicorn process; the cross-process single flight is the
`imovel_videos_vista_import:<org>` lease). NOC-REMEDIATE[videos-vista-import-run-table]: persist runs in a table (like
`imoveis_sync_execucoes`, migration 316) if the report must outlive a container restart -- today a restart loses the report (the
writes themselves are durable in `imovel_video_youtube` + `imovel_historico`); a re-run reproduces it -- 2026-11-27
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.domain.real_estate import ImovelVideo
from noctusai_lib.integrations.vista import VistaNotFound, VistaRecordUnpublished

from app.modules.imovel_hub import busca_service
from app.services import imovel_video_youtube_service as video_mod

logger = logging.getLogger(__name__)

T_REGISTRY = "imovel_registry"
PAGINA = 1000  # PostgREST's default max-rows: read the registry / the field in pages, never trust one select to be complete
MAX_ERROS_SEGUIDOS = 10
REGRA_ESCOLHA = "Destaque=Sim; senão o primeiro por VideoCodigo crescente (empate: ordem do Vista)"
MOTIVO = "Importado do Vista (relação Video, VideoCodigo {video_codigo})."
LEASE_TTL_S = 3600

#: Every count of a report (always present, 0 when nothing happened). `criaria`/`atualizaria` belong to a dry run,
#: `criados`/`atualizados` to a real one.
CONTAGENS = (
    "consultados", "sem_video", "nao_publicado", "nao_encontrado", "nao_cadastrado", "short_ignorado", "nao_youtube",
    "criaria", "criados", "atualizaria", "atualizados", "mantido_julia_manual", "ja_igual", "erros",
)
#: The per-code results that ask the owner for a look (the default filter of the status endpoint / the MCP tool).
RESULTADOS_ACIONAVEIS = ("criaria", "criados", "atualizaria", "atualizados", "mantido_julia_manual", "short_ignorado", "nao_youtube", "erros")


def lease_name(org_id: Any) -> str:
    return f"imovel_videos_vista_import:{org_id}"


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Selection (pure) ────────────────────────────────────────────────────


@dataclass(frozen=True)
class Escolha:
    """The outcome of the selection rules over one listing's `Video` relation."""

    resultado: str  # "elegivel" | "sem_video" | "short_ignorado" | "nao_youtube"
    youtube_video_id: Optional[str] = None
    video_codigo: Optional[str] = None


def _classificar(video: ImovelVideo) -> tuple[str, Optional[str]]:
    """("youtube", id) | ("short", None) | ("nao_youtube", None) for one entry. Parsing is S1's `extrair_video_id` -- one parser."""
    tipo = (video.tipo or "").strip().lower()
    valor = (video.video or "").strip()
    if "short" in tipo:
        return "short", None
    if tipo != "youtube" and "youtu" not in valor.lower():
        return "nao_youtube", None  # another vendor's id must never be read as a YouTube id just because it has 11 chars
    try:
        return "youtube", video_mod.extrair_video_id(valor)
    except video_mod.VideoYoutubeShort:
        return "short", None
    except video_mod.VideoYoutubeInvalido:
        return "nao_youtube", None


def escolher(videos: list[ImovelVideo]) -> Escolha:
    """Rules 1 + 2. `videos` in `parse_imovel_videos` order (VideoCodigo ascending)."""
    if not videos:
        return Escolha("sem_video")
    elegiveis: list[tuple[ImovelVideo, str]] = []
    viu_short = False
    for video in videos:
        classe, vid = _classificar(video)
        if classe == "youtube" and vid:
            elegiveis.append((video, vid))
        viu_short = viu_short or classe == "short"
    if not elegiveis:
        return Escolha("short_ignorado" if viu_short else "nao_youtube")
    video, vid = next(((v, i) for v, i in elegiveis if v.destaque), elegiveis[0])
    return Escolha("elegivel", vid, video.codigo)


def decidir(atual: Optional[dict], youtube_video_id: str) -> str:
    """Rule 3 against the field's current row: "criar" | "atualizar" | "ja_igual" | "mantido_julia_manual"."""
    if not atual:
        return "criar"
    if str(atual.get("youtube_video_id")) == youtube_video_id:
        return "ja_igual"
    if atual.get("origem") != "vista":
        return "mantido_julia_manual"
    return "atualizar"


# ─── Report ──────────────────────────────────────────────────────────────


@dataclass
class LinhaRelatorio:
    codigo: str
    resultado: str
    youtube_video_id: Optional[str] = None
    youtube_url: Optional[str] = None
    video_codigo: Optional[str] = None
    atual_youtube_video_id: Optional[str] = None
    atual_origem: Optional[str] = None
    motivo: Optional[str] = None


@dataclass
class Relatorio:
    org_id: str
    dry_run: bool
    status: str = "em_andamento"  # em_andamento | concluida | abortada | falhou | ignorada
    contagens: dict[str, int] = field(default_factory=lambda: {k: 0 for k in CONTAGENS})
    linhas: list[LinhaRelatorio] = field(default_factory=list)
    total_codigos: int = 0
    regra_escolha: str = REGRA_ESCOLHA
    iniciado_em: str = field(default_factory=_agora)
    finalizado_em: Optional[str] = None
    erro: Optional[str] = None

    def anotar(self, linha: LinhaRelatorio, contagem: str) -> None:
        self.linhas.append(linha)
        self.contagens[contagem] += 1

    def resumo(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("linhas")
        return d

    def as_dict(self, *, resultados: Optional[tuple[str, ...]] = None, limit: Optional[int] = None, offset: int = 0) -> dict[str, Any]:
        """The summary + the per-code rows (filtered by `resultados`, paged by `limit`/`offset`; `linhas_total` = after filter)."""
        linhas = [asdict(x) for x in self.linhas if resultados is None or x.resultado in resultados]
        fim = None if limit is None else offset + limit
        return {**self.resumo(), "linhas_total": len(linhas), "linhas": linhas[offset:fim]}


# ─── The import ──────────────────────────────────────────────────────────


def _vista_proibido(_org_id: Any) -> Any:
    raise RuntimeError("the Vista videos import never writes to Vista")


class ImovelVideosVistaImportService:
    def __init__(self, client: Any, adapter: Any, *, video_service: Optional[video_mod.ImovelVideoYoutubeService] = None,
                 pagina: int = PAGINA) -> None:
        self._db = client
        self._pagina = pagina
        self._vista = adapter
        self._videos = video_service or video_mod.build_imovel_video_youtube_service(client, vista_provider=_vista_proibido)

    # ── reads (paged) ──
    def _paginado(self, tabela: str, colunas: str, org_id: str, ordem: str) -> list[dict]:
        out: list[dict] = []
        inicio = 0
        while True:
            rows = (self._db.table(tabela).select(colunas).eq("org_id", org_id).order(ordem)
                    .range(inicio, inicio + self._pagina - 1).execute().data or [])
            out.extend(rows)
            if len(rows) < self._pagina:
                return out
            inicio += self._pagina

    def _alvos(self, org: str, codigos: Optional[list[str]], limite: Optional[int], rel: Relatorio) -> list[tuple[str, str]]:
        """(canonical, the spelling Vista is asked with) for the org's registry, filtered by `codigos`, cut at `limite`."""
        registro = {r["codigo_canonical"]: (r.get("codigo_display") or r["codigo_canonical"]).strip()
                    for r in self._paginado(T_REGISTRY, "codigo_canonical,codigo_display", org, "codigo_canonical")}
        if codigos:
            alvos = []
            for bruto in dict.fromkeys(busca_service.canonical(c or "") for c in codigos):
                if bruto in registro:
                    alvos.append((bruto, registro[bruto]))
                elif bruto:
                    rel.anotar(LinhaRelatorio(bruto, "nao_cadastrado", motivo="código fora do imovel_registry da org"), "nao_cadastrado")
        else:
            alvos = sorted(registro.items())
        return alvos[:limite] if limite else alvos

    def _atuais(self, org: str) -> dict[str, dict]:
        return {r["codigo"]: r for r in self._paginado(video_mod.T_VIDEO, "codigo,youtube_video_id,origem", org, "codigo")}

    # ── run ──
    async def importar(
        self, org_id: UUID | str, *, dry_run: bool = True, codigos: Optional[list[str]] = None, limite: Optional[int] = None,
        definido_por: Optional[str] = None, relatorio: Optional[Relatorio] = None,
    ) -> Relatorio:
        """Run the import (see the module docstring). Pass `relatorio` to watch the run's progress from outside."""
        org = str(UUID(str(org_id)))
        rel = relatorio or Relatorio(org_id=org, dry_run=dry_run)
        try:
            alvos = await asyncio.to_thread(self._alvos, org, codigos, limite, rel)
            atuais = await asyncio.to_thread(self._atuais, org)
            rel.total_codigos = len(alvos)
            seguidos = 0
            for canonico, pedido in alvos:
                ok = await self._um(org, canonico, pedido, atuais.get(canonico), rel, dry_run=dry_run, definido_por=definido_por)
                seguidos = 0 if ok else seguidos + 1
                if seguidos >= MAX_ERROS_SEGUIDOS:
                    rel.status, rel.erro = "abortada", f"{MAX_ERROS_SEGUIDOS} erros seguidos do Vista"
                    break
            else:
                rel.status = "concluida"
        except Exception as exc:  # the run settles with the class name (a Vista body can carry the key), never a hung "em_andamento"
            logger.error("videos vista import failed org=%s (%s)", org, type(exc).__name__, exc_info=True)
            rel.status, rel.erro = "falhou", type(exc).__name__
        rel.finalizado_em = _agora()
        logger.info("videos vista import org=%s dry_run=%s status=%s contagens=%s", org, dry_run, rel.status, rel.contagens)
        return rel

    async def _um(self, org: str, codigo: str, pedido: str, atual: Optional[dict], rel: Relatorio, *, dry_run: bool,
                  definido_por: Optional[str]) -> bool:
        """One code. False only for an `erros` outcome (the abort counter); every outcome is one report row."""
        rel.contagens["consultados"] += 1
        try:
            videos = await self._vista.list_imovel_videos(pedido)
        except VistaRecordUnpublished as exc:
            if exc.payload_keys:
                rel.anotar(LinhaRelatorio(codigo, "nao_publicado", motivo="imóvel não publicado no Vista (ExibirNoSite=Nao)"), "nao_publicado")
            else:
                rel.anotar(LinhaRelatorio(codigo, "nao_encontrado", motivo="o Vista não tem este código"), "nao_encontrado")
            return True
        except VistaNotFound:
            rel.anotar(LinhaRelatorio(codigo, "nao_encontrado", motivo="o Vista não tem este código (404)"), "nao_encontrado")
            return True
        except Exception as exc:  # class name only: a Vista 401 body embeds the key
            rel.anotar(LinhaRelatorio(codigo, "erros", motivo=f"leitura do Vista falhou ({type(exc).__name__})"), "erros")
            return False
        escolha = escolher(videos)
        if escolha.resultado != "elegivel":
            rel.anotar(LinhaRelatorio(codigo, escolha.resultado), escolha.resultado)
            return True
        vid = escolha.youtube_video_id or ""
        if not dry_run:
            try:
                atual = await asyncio.to_thread(self._linha_atual, org, codigo)  # re-read: a Julia/manual value set meanwhile wins
            except Exception as exc:
                rel.anotar(LinhaRelatorio(codigo, "erros", vid, video_mod.url_de(vid), escolha.video_codigo,
                                          motivo=f"leitura do campo falhou ({type(exc).__name__})"), "erros")
                return False
        acao = decidir(atual, vid)
        linha = LinhaRelatorio(codigo, "", vid, video_mod.url_de(vid), escolha.video_codigo,
                               atual_youtube_video_id=(atual or {}).get("youtube_video_id"), atual_origem=(atual or {}).get("origem"))
        if acao in ("ja_igual", "mantido_julia_manual"):
            linha.resultado = acao
            rel.anotar(linha, acao)
            return True
        contagem = {("criar", True): "criaria", ("criar", False): "criados",
                    ("atualizar", True): "atualizaria", ("atualizar", False): "atualizados"}[(acao, dry_run)]
        if not dry_run:
            try:
                await asyncio.to_thread(
                    self._videos.definir, org, codigo, youtube_video_id=vid, origem="vista",
                    motivo=MOTIVO.format(video_codigo=escolha.video_codigo or "?"), definido_por=definido_por)
            except Exception as exc:
                linha.resultado, linha.motivo = "erros", f"gravação falhou ({type(exc).__name__})"
                rel.anotar(linha, "erros")
                return False
        linha.resultado = contagem
        rel.anotar(linha, contagem)
        return True

    def _linha_atual(self, org: str, codigo: str) -> Optional[dict]:
        atual = self._videos.obter(org, codigo)
        return {"youtube_video_id": atual.youtube_video_id, "origem": atual.origem} if atual else None


def build_imovel_videos_vista_import_service(client: Any, adapter: Any) -> ImovelVideosVistaImportService:
    """The import over the `social_wiring`-scoped client and the org's Vista adapter (`vista_credenciais.adapter_da_org`)."""
    return ImovelVideosVistaImportService(client, adapter)


# ─── In-process run registry (see the module docstring) ──────────────────


@dataclass
class Execucao:
    id: str
    org_id: str
    relatorio: Relatorio
    codigos: Optional[list[str]] = None
    limite: Optional[int] = None
    iniciado_por: Optional[str] = None


class Execucoes:
    """Single flight per org + the last `MANTER` finished runs. One process (see the module docstring)."""

    MANTER = 20

    def __init__(self) -> None:
        self._por_id: dict[str, Execucao] = {}

    def em_andamento(self, org_id: str) -> Optional[Execucao]:
        return next((e for e in self._por_id.values() if e.org_id == org_id and e.relatorio.status == "em_andamento"), None)

    def iniciar(self, org_id: str, *, dry_run: bool, codigos: Optional[list[str]], limite: Optional[int],
                iniciado_por: Optional[str]) -> tuple[Execucao, bool]:
        """(the run, True) for a new one; (the running one, False) while this org already has one going."""
        atual = self.em_andamento(org_id)
        if atual:
            return atual, False
        ex = Execucao(str(uuid.uuid4()), org_id, Relatorio(org_id=org_id, dry_run=dry_run), codigos, limite, iniciado_por)
        self._por_id[ex.id] = ex
        terminadas = [e for e in self._por_id.values() if e.relatorio.status != "em_andamento"]
        for velha in sorted(terminadas, key=lambda e: e.relatorio.iniciado_em)[: max(0, len(terminadas) - self.MANTER)]:
            self._por_id.pop(velha.id, None)
        return ex, True

    def obter(self, execucao_id: str) -> Optional[Execucao]:
        return self._por_id.get(execucao_id)

    def listar(self) -> list[Execucao]:
        return sorted(self._por_id.values(), key=lambda e: e.relatorio.iniciado_em, reverse=True)


EXECUCOES = Execucoes()


async def executar(execucao: Execucao, *, client: Any, admin: Any, adapter: Any, lease_fn: Callable[..., Any]) -> Relatorio:
    """The background body: cross-process lease, then `importar` into the run's own (observable) report."""
    rel = execucao.relatorio
    with lease_fn(admin, lease_name(execucao.org_id), ttl_seconds=LEASE_TTL_S) as adquirido:
        if not adquirido:
            rel.status, rel.erro, rel.finalizado_em = "ignorada", "outro processo já está importando os vídeos desta org", _agora()
            return rel
        return await build_imovel_videos_vista_import_service(client, adapter).importar(
            execucao.org_id, dry_run=rel.dry_run, codigos=execucao.codigos, limite=execucao.limite,
            definido_por=execucao.iniciado_por, relatorio=rel)


__all__ = [
    "CONTAGENS", "EXECUCOES", "Escolha", "Execucao", "Execucoes", "ImovelVideosVistaImportService", "LinhaRelatorio", "MOTIVO",
    "REGRA_ESCOLHA", "RESULTADOS_ACIONAVEIS", "Relatorio", "build_imovel_videos_vista_import_service", "decidir", "escolher",
    "executar", "lease_name",
]
