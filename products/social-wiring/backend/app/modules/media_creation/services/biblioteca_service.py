"""Biblioteca de Virais + Minha Biblioteca -- the request-path service (endpoints 7-19).

Contract: ``projects/core-studio-build/specs/geracao-contract.md`` sections 2.3, 4.3, 9.2, 9.3. The
ingestion pipeline (sync / transcribe / classify) lives in :mod:`.biblioteca_ingestao`; this module
only reads, edits the allow-list and ENQUEUES jobs.

Since migration 351 the library (profiles, videos) is PLATFORM-WIDE (``estruturas-contract.md`` sections 3.2 / 4):
the library tables carry no org filter; only ``cs_biblioteca_referencias`` (a brand's selection) and the marca ownership
check stay org-scoped. Profile writes are admin-only (the routers gate them with ``require_platform_admin``) and every
one writes a content-free ``cs_perfil_eventos`` row.

Rules every method keeps:

* a foreign / unknown marca or reference is a 404 (ids are not enumerable); library ids are platform-wide;
* thumbnails live in the PRIVATE ``sw-biblioteca`` bucket and are only ever served as short-TTL signed
  URLs minted per request;
* a Graph / vendor error text never reaches a client -- the stored ``erro_mensagem`` is OUR pt-BR copy.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional, Sequence

from noctusai_lib.domain.jobs import JobRepository
from noctusai_lib.integrations.apify import ActorRunner, ApifyNotConfigured, ApifyRateLimited, ApifyRunFailed
from noctusai_lib.integrations.media.safe_fetch import SafeFetcher
from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.persistence.table_reads import batched
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from app.modules.media_creation.geracao_taxonomias import FORMATOS_VIDEO, NICHOS, PROFISSOES
from app.modules.media_creation.services import biblioteca_fonte, biblioteca_optout
from app.modules.media_creation.services.estruturas_service import formula_trecho
from app.modules.media_creation.schemas.biblioteca import (
    MAX_REFERENCIAS_MARCA,
    PAGE_SIZE,
    HandleInvalido,
    LinkInvalido,
    extrair_shortcode,
    normalizar_handle,
)

logger = logging.getLogger(__name__)

PERFIS = "cs_perfis_monitorados"
VIRAIS = "cs_virais"
REFS = "cs_biblioteca_referencias"
EVENTOS = "cs_perfil_eventos"
ESTRUTURAS = "cs_estruturas"
MARCA_PERFIL = "cs_marca_perfil"
ACCOUNTS = "integration_accounts"
TRANSCRICOES = "transcricoes"
CONTEXTO_TIPO = "biblioteca_viral"
#: PRIVATE bucket (migration 229): library thumbnails, never public.
BUCKET = "sw-biblioteca"
SIGNED_TTL_SECONDS = 600
SYNC_MIN_INTERVAL = timedelta(hours=1)
TRECHO_CHARS = 200

PERFIL_COLS = (
    "id,org_id,handle,conta_descoberta_id,ig_user_id,nome,foto_path,seguidores,media_count,status,"
    "erro_codigo,erro_mensagem,ultima_sync_em,proxima_sync_em,metrica_base,mediana_metrica,created_by,monitorar"
)
CARD_COLS = (
    "id,codigo,perfil_id,permalink,publicado_em,views,likes,comments,duracao_s,score_viral,e_viral,"
    "thumbnail_path,gancho,caption"
)
DETALHE_COLS = (
    CARD_COLS + ",transcricao_texto,transcricao_status,classificacao_status,formato_ids,nicho_ids,"
    "profissao_ids,gatilho,blueprint,video_url,video_url_em,origem_inclusao"
)
#: How long a scraper video URL is served to the FE (Instagram CDN URLs carry a signed expiry; ~24 h is
#: the conservative window). Past it ``video_url`` is null and the FE falls back to the Instagram embed.
#: Also the window the transcription job may reuse the stored URL (``biblioteca_ingestao.VIDEO_URL_TTL``).
VIDEO_URL_FRESCA = timedelta(hours=24)

_NICHO = dict(NICHOS)
_PROFISSAO = dict(PROFISSOES)
_FORMATO = {i: nome for i, nome, _ in FORMATOS_VIDEO}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_KW_STRIP = re.compile(r"[,()%*\\\":;]")
MAX_KEYWORDS = 8
MAX_KEYWORD_CHARS = 40

#: Every stored add-by-link permalink starts with this (the canonical Instagram post URL, F10).
PERMALINK_PREFIXO = "https://www.instagram.com/"

MSG_SEM_CONTA = (
    "Conecte uma conta do Instagram pelo login do Facebook (Meta) para monitorar perfis."
)


class BibliotecaError(Exception):
    def __init__(
        self, status: int, detail: str, *, retry_after_s: Optional[int] = None, code: Optional[str] = None,
        extra: Optional[dict[str, Any]] = None,
    ):
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.code = code
        self.retry_after_s = retry_after_s
        #: Extra keys of a coded refusal (``{"estruturas_total": n}``): the client receives them flat next to ``code``.
        self.extra = dict(extra or {})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass
class ViralFiltros:
    """The decoded query of endpoint 7 (the router validates the raw params)."""

    marca_id: str
    nichos: list[int] = field(default_factory=list)
    profissoes: list[int] = field(default_factory=list)
    ver_todos: bool = False
    ordem: str = "mais_vistos"
    q: Optional[str] = None
    buscar_em: str = "gancho"
    data_de: Optional[str] = None
    data_ate: Optional[str] = None
    views_min: Optional[int] = None
    likes_min: Optional[int] = None
    comments_min: Optional[int] = None
    perfil_id: Optional[str] = None
    formato_id: Optional[int] = None
    codigo: Optional[int] = None
    somente_virais: bool = True
    pool: Optional[str] = None
    page: int = 1


def keywords(q: Optional[str]) -> list[str]:
    """``q`` is comma-separated keywords. Filter-syntax characters are stripped (the value is
    interpolated into a PostgREST ``or`` expression); at most 8 keywords of 40 chars."""
    out: list[str] = []
    for raw in (q or "").split(","):
        kw = _KW_STRIP.sub(" ", raw).strip()[:MAX_KEYWORD_CHARS]
        if kw and kw not in out:
            out.append(kw)
        if len(out) == MAX_KEYWORDS:
            break
    return out


def _array_literal(ids: list[int]) -> str:
    return "{" + ",".join(str(int(i)) for i in ids) + "}"


def aplicar_filtros(
    query: Any,
    f: ViralFiltros,
    *,
    auto: Optional[tuple[list[int], list[int]]] = None,
    pool_expr: Optional[str] = None,
) -> Any:
    """Add every ``cs_virais`` filter of ``f`` to a select builder (the library is platform-wide: no org filter). Pure over the builder, so a test can
    read back the recorded predicates (the array-overlap / ``or`` operators are match-all in the mock
    client and are therefore asserted by predicate, not by behaviour). ``auto`` is the marca's
    ``(nichos, profissoes)`` for the automatic filter; ``pool_expr`` the ``Minha Biblioteca`` allow-list."""
    if f.somente_virais:
        # A video an admin added by link was chosen by hand: it is part of the library whatever its viral score is.
        query = query.or_("e_viral.eq.true,origem_inclusao.eq.link_manual")
    if f.perfil_id:
        query = query.eq("perfil_id", f.perfil_id)
    if f.codigo is not None:
        query = query.eq("codigo", f.codigo)
    if f.formato_id is not None:
        query = query.contains("formato_ids", [f.formato_id])
    if f.nichos:
        query = query.overlaps("nicho_ids", f.nichos)
    if f.profissoes:
        query = query.overlaps("profissao_ids", f.profissoes)
    if auto is not None:
        nichos, profissoes = auto
        parts = []
        if nichos:
            parts.append(f"nicho_ids.ov.{_array_literal(nichos)}")
        if profissoes:
            parts.append(f"profissao_ids.ov.{_array_literal(profissoes)}")
        if parts:
            query = query.or_(",".join(parts))
    if f.data_de:
        query = query.gte("publicado_em", f"{f.data_de}T00:00:00+00:00")
    if f.data_ate:
        query = query.lte("publicado_em", f"{f.data_ate}T23:59:59.999999+00:00")
    if f.views_min is not None:
        query = query.gte("views", f.views_min)
    if f.likes_min is not None:
        query = query.gte("likes", f.likes_min)
    if f.comments_min is not None:
        query = query.gte("comments", f.comments_min)
    kws = keywords(f.q)
    if kws:
        col = "transcricao_texto" if f.buscar_em == "transcricao" else "gancho"
        query = query.or_(",".join(f"{col}.ilike.*{kw}*" for kw in kws))
    if pool_expr:
        query = query.or_(pool_expr)
    if f.ordem == "mais_recentes":
        query = query.order("publicado_em", desc=True)
    else:
        query = query.order("score_viral", desc=True, nullsfirst=False).order("publicado_em", desc=True)
    return query


def pool_expression(refs: list[dict[str, Any]]) -> Optional[str]:
    """The PostgREST ``or`` expression of a marca's allow-list (``None`` = empty allow-list). Only UUIDs
    and a validated ``YYYY-MM-DD`` are interpolated."""
    parts: list[str] = []
    open_perfis: list[str] = []
    videos: list[str] = []
    for r in refs:
        if r.get("modo") == "perfil" and r.get("perfil_id"):
            pid = str(uuid.UUID(str(r["perfil_id"])))
            ate = r.get("posts_ate")
            if ate:
                ate = str(ate)[:10]
                if not _DATE_RE.match(ate):
                    continue
                parts.append(f"and(perfil_id.eq.{pid},publicado_em.lte.{ate}T23:59:59.999999+00:00)")
            else:
                open_perfis.append(pid)
        elif r.get("modo") == "video" and r.get("viral_id"):
            videos.append(str(uuid.UUID(str(r["viral_id"]))))
    if open_perfis:
        parts.append(f"perfil_id.in.({','.join(open_perfis)})")
    if videos:
        parts.append(f"id.in.({','.join(videos)})")
    return ",".join(parts) or None


def registrar_evento(
    db: Any, *, perfil_id: Any, tipo: str, ator_id: Optional[str], ator_tipo: str = "admin",
    viral_id: Optional[str] = None,
) -> None:
    """Append ONE content-free ``cs_perfil_eventos`` row (who / when / what) for an admin write on a library profile or video.
    The row carries NO handle (owner decision 2026-11-15): it outlives the profile, and an opt-out purge must not leave who
    the creator was in its own history.

    A failed insert is LOUD (logged, re-raised -- never swallowed): the audit row is part of the write.
    NOC-REMEDIATE[cs-service-role-writes]: the profile / video state writes and this event are separate service-role
    PostgREST calls, not one transaction, and the service role holds table INSERT/UPDATE (security review F7: revoke the
    table writes and wrap every library write in a SECURITY DEFINER RPC, as ``cs_perfil_plataforma_criar`` /
    ``cs_perfil_purgar`` already are). Destination: EST-RO (wave 3) -- 2026-11-15."""
    try:
        db.table(EVENTOS).insert({
            "perfil_id": str(perfil_id), "viral_id": str(viral_id) if viral_id else None,
            "tipo": tipo, "ator_id": ator_id or None, "ator_tipo": ator_tipo,
        }).execute()
    except Exception:
        logger.exception("biblioteca: evento %s do perfil %s não gravado", tipo, perfil_id)
        raise


def prefixo_blobs(perfil: dict[str, Any]) -> str:
    """``platform`` for a platform profile, the org id for a row written before migration 351."""
    return str(perfil.get("org_id") or biblioteca_fonte.PREFIXO_PLATAFORMA)


def _rpc_mensagem(exc: BaseException) -> tuple[str, str]:
    """``(message, details)`` of a PostgREST ``APIError`` (the coded ``RAISE EXCEPTION '<code>'`` of an RPC)."""
    payload = exc.args[0] if exc.args and isinstance(exc.args[0], dict) else {}
    message = str(getattr(exc, "message", None) or payload.get("message") or "").strip()
    details = str(getattr(exc, "details", None) or payload.get("details") or "").strip()
    return message, details


def _rpc_estruturas_total(exc: BaseException) -> Optional[int]:
    """The ``DETAIL`` count of a ``perfil_com_estruturas`` refusal of ``cs_perfil_purgar`` (``None`` = not that refusal)."""
    message, details = _rpc_mensagem(exc)
    if message != "perfil_com_estruturas":
        return None
    return int(details) if details.isdigit() else 0


def erro_optout() -> "BibliotecaError":
    return BibliotecaError(409, biblioteca_optout.MSG_OPTOUT, code=biblioteca_optout.CODIGO_OPTOUT)


def criar_perfil_plataforma(
    db: Any, *, handle: str, nome: Optional[str] = None, origem: str = "manual", ator_tipo: str = "admin",
    ator_id: Optional[str] = None, importacao_id: Optional[str] = None, monitorar: bool = False,
    status: str = "aguardando", conta: Optional[str] = None, erro_codigo: Optional[str] = None,
    erro_mensagem: Optional[str] = None,
) -> dict[str, Any]:
    """Create a platform library profile through the ONE door: the ``cs_perfil_plataforma_criar`` RPC (security review F3).

    The profile and its ``criado`` (+ ``importado``) events are written in one transaction, and the opt-out registry is
    checked INSIDE it (a creator who opted out is refused ``perfil_optout`` -> :class:`BibliotecaError` 409 whatever the
    caller checked before). Idempotent on the handle: ``criado=False`` returns the existing profile. ``{id, handle, criado}``."""
    try:
        res = db.rpc("cs_perfil_plataforma_criar", {
            "p_handle": handle, "p_nome": nome, "p_origem": origem, "p_ator_tipo": ator_tipo, "p_ator": ator_id,
            "p_importacao": importacao_id, "p_monitorar": bool(monitorar), "p_status": status, "p_conta": conta,
            "p_erro_codigo": erro_codigo, "p_erro_mensagem": erro_mensagem,
        }).execute()
    except Exception as exc:  # noqa: BLE001 - the one coded refusal is mapped; anything else is re-raised, never swallowed
        if _rpc_mensagem(exc)[0] == biblioteca_optout.CODIGO_OPTOUT:
            raise erro_optout() from exc
        raise
    data = getattr(res, "data", None)
    data = data[0] if isinstance(data, list) and data else data
    if not isinstance(data, dict) or not data.get("id"):
        raise RuntimeError("cs_perfil_plataforma_criar: resposta sem id")
    return {"id": str(data["id"]), "handle": data.get("handle", handle), "criado": bool(data.get("criado"))}


def erro_perfil_com_estruturas(total: int) -> BibliotecaError:
    return BibliotecaError(
        409, "Este perfil tem estruturas na biblioteca. Apague-as junto ou arquive-as antes de excluir o perfil.",
        code="perfil_com_estruturas", extra={"estruturas_total": int(total)},
    )


async def apagar_transcricoes(db: Any, storage: StorageBackend, viral_ids: Sequence[str]) -> dict[str, int]:
    """Erase the transcriptions of library videos THROUGH the transcription organ (security review F2).

    Every ``biblioteca_viral`` row of the given videos goes -- including a job still ``na_fila`` / ``processando``: the
    organ's ``marcar_falha`` first closes it (the worker's conditional finish can no longer fill it), then its own
    ``apagar_audio`` deletes the recording (``sw-transcricoes``) and only then is the row (transcript text) deleted. A
    recording that cannot be deleted keeps its row (text nulled) so the organ's retention sweep, which owns the audio
    bucket, retries it -- never an orphaned blob nobody points at. Returns ``{transcricoes, audios_falhos}``."""
    from app.modules.transcricoes.service import IN_FLIGHT, apagar_audio, marcar_falha

    out = {"transcricoes": 0, "audios_falhos": 0}
    for chunk in batched(sorted({str(v) for v in viral_ids})):
        rows = (
            db.table(TRANSCRICOES).select("id,status,storage_path,audio_apagado_em").eq("contexto_tipo", CONTEXTO_TIPO)
            .in_("contexto_ref", chunk).execute().data or []
        )
        for r in rows:
            if r.get("status") in IN_FLIGHT:
                marcar_falha(db, r["id"], "contexto_apagado", reembolsar=True)
            if await apagar_audio(db, storage, r):
                db.table(TRANSCRICOES).delete().eq("id", str(r["id"])).execute()
                out["transcricoes"] += 1
            else:
                db.table(TRANSCRICOES).update({"texto": None}).eq("id", str(r["id"])).execute()
                out["audios_falhos"] += 1
    return out


async def minimizar_perfil(
    db: Any, storage: StorageBackend, perfil_id: str, *, ator_id: Optional[str] = None, ator_tipo: str = "sistema",
) -> bool:
    """Owner decision 2026-11-15 (#4): a profile RETAINED only because a non-archived Estrutura references it drops its
    photo + follower count (``cs_perfil_minimizar``: one transaction, one ``minimizado`` event, idempotent), then the photo
    blob is deleted (a failed delete is logged; the orphan sweep retries the prefix). ``True`` when something was dropped."""
    res = db.rpc("cs_perfil_minimizar", {"p_perfil": str(perfil_id), "p_ator": ator_id, "p_ator_tipo": ator_tipo}).execute()
    data = getattr(res, "data", None)
    data = data[0] if isinstance(data, list) and data else data
    if not isinstance(data, dict) or not data.get("minimizado"):
        return False
    if data.get("foto_path"):
        try:
            await storage.delete(bucket=BUCKET, key=data["foto_path"])
        except Exception:  # noqa: BLE001 - the row is already minimised; the orphan sweep retries the blob
            logger.warning("biblioteca: foto do perfil minimizado não apagada perfil=%s", perfil_id, exc_info=True)
    return True


async def purgar_perfil(
    db: Any, storage: StorageBackend, perfil: dict[str, Any], *, ator_id: Optional[str] = None,
    ator_tipo: str = "admin", tipo_evento: str = "excluido", apagar_estruturas: bool = False,
) -> dict[str, int]:
    """Erase a library profile and EVERYTHING derived from it (LGPD, contract 9.3 / estruturas-contract 4.3 #7).

    ONE database transaction (the ``cs_perfil_purgar`` RPC of migration 351) deletes the profile; its videos, brand
    selections and -- with ``apagar_estruturas`` -- its Estruturas and their uses go through the FK cascades, and the
    content-free events (``cs_estrutura_eventos.excluida`` per Estrutura, ``cs_perfil_eventos``) are written in the same
    transaction. A profile that still owns Estruturas is REFUSED (``perfil_com_estruturas``) unless the flag is set: the
    database is touched FIRST, so a refusal destroys nothing. Only then are the blobs (thumbnails, picture, the profile's
    whole ``{org|platform}/{perfil}/`` prefix) and the library ``transcricoes`` rows removed.

    A blob that cannot be deleted never keeps the row alive -- it is logged and counted and the orphan-prefix sweep
    (``biblioteca_scheduler.varrer_blobs_orfaos``) retries it: once the row is gone the prefix has no owner, which is
    exactly what that sweep deletes. Used by the delete endpoint, the opt-out purge and the retention purge.
    Returns ``{blobs_falhos, estruturas, virais}``."""
    pid = str(perfil["id"])
    virais = list(
        iter_paged_rows(
            lambda s, e: db.table(VIRAIS).select("id,thumbnail_path").eq("perfil_id", pid)
            .order("id").range(s, e).execute().data
        )
    )
    keys = {v["thumbnail_path"] for v in virais if v.get("thumbnail_path")}
    if perfil.get("foto_path"):
        keys.add(perfil["foto_path"])
    try:
        res = db.rpc("cs_perfil_purgar", {
            "p_perfil": pid, "p_ator": ator_id, "p_ator_tipo": ator_tipo, "p_tipo": tipo_evento,
            "p_apagar_estruturas": bool(apagar_estruturas),
        }).execute()
    except Exception as exc:  # noqa: BLE001 - the one coded refusal is mapped; anything else is re-raised, never swallowed
        total = _rpc_estruturas_total(exc)
        if total is None:
            logger.exception("biblioteca: cs_perfil_purgar falhou perfil=%s", pid)
            raise
        raise erro_perfil_com_estruturas(total) from exc
    data = getattr(res, "data", None)
    data = data[0] if isinstance(data, list) and data else data
    out = {"blobs_falhos": 0, "estruturas": int((data or {}).get("estruturas") or 0), "virais": len(virais)}
    try:
        keys.update(await storage.list_keys(bucket=BUCKET, prefix=f"{prefixo_blobs(perfil)}/{pid}/", limit=1000))
    except Exception:  # noqa: BLE001 - the row-path keys above still go; the sweep covers the rest
        logger.warning("biblioteca: list_keys falhou perfil=%s", pid, exc_info=True)
    for key in sorted(keys):
        try:
            await storage.delete(bucket=BUCKET, key=key)
        except Exception:  # noqa: BLE001 - never leave the row alive because a blob delete failed
            out["blobs_falhos"] += 1
            logger.warning("biblioteca: blob delete failed key=%s (a varredura de órfãos repete)", key, exc_info=True)
    t = await apagar_transcricoes(db, storage, [str(v["id"]) for v in virais])
    out["blobs_falhos"] += t["audios_falhos"]
    return out


async def purgar_handle(
    db: Any, storage: StorageBackend, handle: str, *, ator_id: Optional[str] = None
) -> dict[str, int]:
    """Erase EVERY library profile for ``handle`` (an opt-out is platform-wide, and legacy per-org rows are covered too):
    its videos, brand selections, Estruturas, transcripts and blobs via :func:`purgar_perfil`, with the opt-out events.
    Idempotent -- no rows left is a ``{0, 0, 0, 0}`` no-op. Returns ``{perfis, virais, estruturas, blobs_falhos}``."""
    out = {"perfis": 0, "virais": 0, "estruturas": 0, "blobs_falhos": 0}
    perfis = list(
        iter_paged_rows(
            lambda s, e: db.table(PERFIS).select("id,org_id,foto_path").eq("handle", handle)
            .order("id").range(s, e).execute().data
        )
    )
    for p in perfis:
        r = await purgar_perfil(
            db, storage, p, ator_id=ator_id, ator_tipo="admin", tipo_evento="optout_purgado", apagar_estruturas=True,
        )
        out["perfis"] += 1
        out["virais"] += r["virais"]
        out["estruturas"] += r["estruturas"]
        out["blobs_falhos"] += r["blobs_falhos"]
    return out


class BibliotecaService:
    def __init__(
        self,
        db: Any,
        org_id: str,
        user_id: Optional[str],
        *,
        storage: StorageBackend,
        jobs: JobRepository,
        switch: Callable[[], bool],
        contato: Optional[Callable[[], str]] = None,
        max_perfis_org: int = 30,
        max_perfis_plataforma: int = 1000,
        sync_manual_dia_org: int = 20,
        fonte: Optional[Callable[[], str]] = None,
        is_admin: bool = False,
        ingestao_org: Optional[Callable[[], Optional[str]]] = None,
        runner_factory: Optional[Callable[[str], ActorRunner]] = None,
        fetcher: Optional[SafeFetcher] = None,
        ledger_factory: Optional[Callable[[], Any]] = None,
        apify_resultados_dia: int = 0,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self.db = db
        #: The CALLER's org: used ONLY for the brand's own selection (``cs_biblioteca_referencias``), the marca ownership
        #: check and the manual-sync cap. The library itself is platform-wide.
        self.org_id = str(org_id)
        self.user_id = user_id
        self.storage = storage
        self.jobs = jobs
        self._switch = switch
        self._contato = contato
        #: Per-BRAND ceiling of SELECTED profiles (``biblioteca_max_perfis_org``).
        self.max_perfis_org = max_perfis_org
        #: Library-wide ceiling of profiles (``biblioteca_max_perfis_plataforma``; an admin write).
        self.max_perfis_plataforma = max_perfis_plataforma
        self.sync_manual_dia_org = sync_manual_dia_org
        #: ``biblioteca_fonte`` reader; ``None`` = Business Discovery (the service's original behaviour).
        self._fonte = fonte
        #: True for a platform admin: sees profile errors / draft Estrutura counts; the routers gate every write.
        self.is_admin = bool(is_admin)
        #: The platform ingestion org (the NoctusAI org); ``None`` reads as "not configured".
        self._ingestao_org = ingestao_org or (lambda: None)
        self._runner_factory = runner_factory
        self._fetcher = fetcher
        self._ledger_factory = ledger_factory
        self._apify_dia = int(apify_resultados_dia)
        self._clock = clock

    # ── guards ──────────────────────────────────────────────────────────

    def usa_apify(self) -> bool:
        """True when profiles are read through Apify -- no connected Meta account is needed then."""
        return self._fonte is not None and self._fonte() == "apify"

    def ingestao_ativa(self) -> bool:
        return bool(self._switch())

    def optout_contato(self) -> str:
        if self._contato is not None:
            return self._contato()
        from app.modules.media_creation.services.geracao_jobs import read_optout_contato

        return read_optout_contato()

    def assert_marca(self, marca_id: str) -> None:
        rows = (
            self.db.table("marcas").select("id").eq("id", str(marca_id)).eq("org_id", self.org_id)
            .execute().data
        )
        if not rows:
            raise BibliotecaError(404, "Marca não encontrada")

    def _perfil_row(self, perfil_id: str) -> dict[str, Any]:
        rows = self.db.table(PERFIS).select(PERFIL_COLS).eq("id", str(perfil_id)).execute().data
        if not rows:
            raise BibliotecaError(404, "Perfil não encontrado")
        return rows[0]

    def _viral_row(self, viral_id: str, cols: str = DETALHE_COLS) -> dict[str, Any]:
        rows = self.db.table(VIRAIS).select(cols).eq("id", str(viral_id)).execute().data
        if not rows:
            raise BibliotecaError(404, "Vídeo não encontrado")
        return rows[0]

    # ── presentation ────────────────────────────────────────────────────

    async def _signed(self, path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        try:
            return await self.storage.signed_url(bucket=BUCKET, key=path, expires_in_seconds=SIGNED_TTL_SECONDS)
        except Exception:  # noqa: BLE001 - a missing thumbnail must not fail the whole page
            logger.warning("biblioteca: signed url failed for %s", path, exc_info=True)
            return None

    def _counts(self, perfil_ids: list[str]) -> dict[str, tuple[int, int]]:
        """``{perfil_id: (virais, posts)}``."""
        out: dict[str, list[int]] = {p: [0, 0] for p in perfil_ids}
        for chunk in batched(perfil_ids):
            rows = iter_paged_rows(
                lambda s, e, chunk=chunk: self.db.table(VIRAIS).select("id,perfil_id,e_viral")
                .in_("perfil_id", chunk).order("id").range(s, e).execute().data
            )
            for r in rows:
                c = out.get(str(r["perfil_id"]))
                if c is not None:
                    c[1] += 1
                    c[0] += 1 if r.get("e_viral") else 0
        return {k: (v[0], v[1]) for k, v in out.items()}

    async def _perfil_out(self, row: dict[str, Any], counts: tuple[int, int], ativa: bool) -> dict[str, Any]:
        """A client org sees a creator as handle + name ONLY (owner decision 2026-11-15, LGPD): no photo, no follower
        count, no ingestion status / ``monitorar`` / sync metrics (security review F9). Admins keep the whole row."""
        out: dict[str, Any] = {
            "id": row["id"],
            "handle": row["handle"],
            "nome": row.get("nome"),
            "virais": counts[0],
            "posts": counts[1],
            "ingestao_ativa": ativa,
            "optout_contato": self.optout_contato(),
        }
        if self.is_admin:
            out.update({
                "foto_url": await self._signed(row.get("foto_path")),
                "seguidores": row.get("seguidores"),
                "status": row["status"],
                "monitorar": bool(row.get("monitorar", True)),
                # An ingestion error names credentials / budgets of the platform: it is the admin's, not a member's.
                "erro_mensagem": row.get("erro_mensagem"),
                "ultima_sync_em": row.get("ultima_sync_em"),
                "metrica_base": row.get("metrica_base"),
                "mediana_metrica": float(row["mediana_metrica"]) if row.get("mediana_metrica") is not None else None,
            })
        return out

    async def perfis_out(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts = self._counts([str(r["id"]) for r in rows])
        ativa = self.ingestao_ativa()
        return [await self._perfil_out(r, counts.get(str(r["id"]), (0, 0)), ativa) for r in rows]

    def _perfis_by_id(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for chunk in batched(sorted(set(ids))):
            for r in self.db.table(PERFIS).select(PERFIL_COLS).in_("id", chunk).execute().data or []:
                out[str(r["id"])] = r
        return out

    @staticmethod
    def _trecho(row: dict[str, Any], f: Optional[ViralFiltros] = None) -> Optional[str]:
        texto = row.get("gancho") or ""
        if f is not None and f.buscar_em == "transcricao" and keywords(f.q):
            full = row.get("transcricao_texto") or ""
            low = full.lower()
            for kw in keywords(f.q):
                at = low.find(kw.lower())
                if at >= 0:
                    start = max(0, at - TRECHO_CHARS // 4)
                    texto = full[start : start + TRECHO_CHARS]
                    break
        if not texto:
            texto = (row.get("caption") or "").strip()
        texto = " ".join(texto.split())
        return texto[:TRECHO_CHARS] or None

    async def _card(self, row: dict[str, Any], handles: dict[str, str], f: Optional[ViralFiltros] = None) -> dict[str, Any]:
        return {
            "id": row["id"],
            "codigo": row.get("codigo"),  # an identity column: always set by the database
            "perfil": {"id": str(row["perfil_id"]), "handle": handles.get(str(row["perfil_id"]), "")},
            "thumbnail_url": await self._signed(row.get("thumbnail_path")),
            "permalink": row.get("permalink") or "",
            "publicado_em": row.get("publicado_em"),
            "views": row.get("views"),
            "likes": row.get("likes"),
            "comments": row.get("comments"),
            "duracao_s": float(row["duracao_s"]) if row.get("duracao_s") is not None else None,
            "score_viral": float(row["score_viral"]) if row.get("score_viral") is not None else None,
            "e_viral": bool(row.get("e_viral")),
            "trecho": self._trecho(row, f),
        }

    # ── virais ──────────────────────────────────────────────────────────

    def _marca_taxons(self, marca_id: str) -> tuple[list[int], list[int]]:
        rows = (
            self.db.table(MARCA_PERFIL).select("nichos,profissoes").eq("marca_id", str(marca_id))
            .eq("org_id", self.org_id).execute().data
        )
        if not rows:
            return [], []
        return list(rows[0].get("nichos") or []), list(rows[0].get("profissoes") or [])

    def _refs(self, marca_id: str) -> list[dict[str, Any]]:
        return list(
            iter_paged_rows(
                lambda s, e: self.db.table(REFS)
                .select("id,modo,perfil_id,viral_id,auto_atualizar,posts_ate,updated_at")
                .eq("org_id", self.org_id).eq("marca_id", str(marca_id)).order("id").range(s, e).execute().data
            )
        )

    async def list_virais(self, f: ViralFiltros) -> dict[str, Any]:
        self.assert_marca(f.marca_id)
        pool_expr = None
        auto = None
        filtro_automatico = False
        if f.pool == "minha_biblioteca":
            pool_expr = pool_expression(self._refs(f.marca_id))
            if pool_expr is None:
                return {"items": [], "total": 0, "page": f.page, "filtro_automatico": False}
        elif not f.ver_todos and not f.nichos and not f.profissoes and not f.perfil_id and f.codigo is None:
            nichos, profissoes = self._marca_taxons(f.marca_id)
            if nichos or profissoes:
                auto = (nichos, profissoes)
                filtro_automatico = True
        cols = CARD_COLS + (",transcricao_texto" if f.buscar_em == "transcricao" and keywords(f.q) else "")
        query = self.db.table(VIRAIS).select(cols, count="exact")
        query = aplicar_filtros(query, f, auto=auto, pool_expr=pool_expr)
        start = (f.page - 1) * PAGE_SIZE
        res = query.range(start, start + PAGE_SIZE - 1).execute()
        rows = res.data or []
        total = res.count if getattr(res, "count", None) is not None else len(rows)
        handles = {k: v["handle"] for k, v in self._perfis_by_id([str(r["perfil_id"]) for r in rows]).items()}
        items = [await self._card(r, handles, f) for r in rows]
        return {"items": items, "total": total, "page": f.page, "filtro_automatico": filtro_automatico}

    async def get_viral(self, viral_id: str, marca_id: str, *, incluir_blueprint: bool = False) -> dict[str, Any]:
        self.assert_marca(marca_id)
        row = self._viral_row(viral_id)
        handles = {k: v["handle"] for k, v in self._perfis_by_id([str(row["perfil_id"])]).items()}
        out = await self._card(row, handles)
        out["trecho"] = self._trecho(row)
        out.update(
            caption=row.get("caption"),
            gancho=row.get("gancho"),
            transcricao_texto=row.get("transcricao_texto"),
            transcricao_status=row["transcricao_status"],
            classificacao_status=row["classificacao_status"],
            nichos=[{"id": i, "nome": _NICHO[i]} for i in row.get("nicho_ids") or [] if i in _NICHO],
            profissoes=[{"id": i, "nome": _PROFISSAO[i]} for i in row.get("profissao_ids") or [] if i in _PROFISSAO],
            formatos=[{"id": i, "nome": _FORMATO[i]} for i in row.get("formato_ids") or [] if i in _FORMATO],
            gatilho=row.get("gatilho"),
            estrutura_utilizavel=bool(row.get("blueprint")) and row["classificacao_status"] == "concluida",
            estruturas=self._estruturas_do_viral(str(row["id"])),
        )
        if self.is_admin:  # how the video entered the library is an admin fact (F9)
            out["origem_inclusao"] = row.get("origem_inclusao") or "sync"
        em = _parse_dt(row.get("video_url_em"))
        out["video_url"] = (
            row["video_url"] if row.get("video_url") and em is not None and _now() - em < VIDEO_URL_FRESCA else None
        )
        if incluir_blueprint:
            out["blueprint"] = row.get("blueprint")
        return out

    def _estruturas_do_viral(self, viral_id: str) -> list[dict[str, Any]]:
        """``EstruturaRef[]`` of the Estruturas derived from this video (members: ``ativa`` only; admins: every status)."""
        q = self.db.table(ESTRUTURAS).select("id,codigo,perfil_id,formula_headline,status").eq("viral_id", str(viral_id))
        if not self.is_admin:
            q = q.eq("status", "ativa")
        rows = q.order("codigo").execute().data or []
        perfis = self._perfis_by_id([str(r["perfil_id"]) for r in rows])
        return [
            {
                "id": str(r["id"]), "codigo": r["codigo"],
                "perfil": {
                    "id": str(r["perfil_id"]), "handle": perfis.get(str(r["perfil_id"]), {}).get("handle", ""),
                    "nome": perfis.get(str(r["perfil_id"]), {}).get("nome"),
                },
                "formula_trecho": formula_trecho(r.get("formula_headline") or ""),
            }
            for r in rows
        ]

    def _estruturas_total(self, perfil_id: str) -> int:
        """Estruturas of a profile: members count the ``ativa`` ones (what they can use), admins every status."""
        q = self.db.table(ESTRUTURAS).select("id", count="exact").eq("perfil_id", str(perfil_id))
        if not self.is_admin:
            q = q.eq("status", "ativa")
        res = q.limit(1).execute()
        return int(res.count) if getattr(res, "count", None) is not None else len(res.data or [])

    # ── perfis ──────────────────────────────────────────────────────────

    def _todos_perfis(self) -> list[dict[str, Any]]:
        """Every library profile (bounded by ``biblioteca_max_perfis_plataforma``, so one in-memory pass is safe)."""
        return list(
            iter_paged_rows(
                lambda s, e: self.db.table(PERFIS).select(PERFIL_COLS).order("id").range(s, e).execute().data
            )
        )

    def _selecionados(self, marca_id: str) -> set[str]:
        return {str(r["perfil_id"]) for r in self._refs(marca_id) if r.get("modo") == "perfil" and r.get("perfil_id")}

    async def list_perfis(
        self, q: Optional[str] = None, marca_id: Optional[str] = None, limit: int = 30, offset: int = 0
    ) -> dict[str, Any]:
        """Library-wide, PAGED (``{items, total}``): search ``q`` over handle / name; ``marca_id`` adds
        ``selecionado_pela_marca`` (the brand's own selection). Never an unbounded array."""
        selecionados: Optional[set[str]] = None
        if marca_id:
            self.assert_marca(marca_id)
            selecionados = self._selecionados(marca_id)
        rows = self._todos_perfis()
        term = (q or "").strip().lower().lstrip("@")
        if term:
            rows = [r for r in rows if term in (r["handle"] or "") or term in (r.get("nome") or "").lower()]
        rows.sort(key=lambda r: r["handle"])
        total = len(rows)
        page = rows[offset: offset + limit]
        items = await self.perfis_out(page)
        if selecionados is not None:
            for item in items:
                item["selecionado_pela_marca"] = str(item["id"]) in selecionados
        return {"items": items, "total": total}

    async def get_perfil(self, perfil_id: str) -> dict[str, Any]:
        row = self._perfil_row(perfil_id)
        out = (await self.perfis_out([row]))[0]
        out["estruturas_total"] = self._estruturas_total(str(row["id"]))
        return out

    def contas_descoberta(self) -> list[dict[str, Any]]:
        """The Meta (Facebook Login) accounts of the platform INGESTION org: the credentials discovery runs on."""
        ingestao = self._ingestao_org()
        if not ingestao:
            return []
        rows = (
            self.db.table(ACCOUNTS)
            .select("id,account_label,metadata,status,is_default")
            .eq("org_id", str(ingestao)).eq("provider", "meta").eq("status", "validated")
            .execute().data or []
        )
        rows.sort(key=lambda r: (not r.get("is_default"), str(r.get("account_label") or "")))
        return [
            {
                "id": r["id"],
                "nome": r.get("account_label") or "Conta Meta",
                "ig_username": (r.get("metadata") or {}).get("channel_title"),
            }
            for r in rows
        ]

    def _conta_valida(self, conta_id: Optional[str]) -> Optional[str]:
        contas = self.contas_descoberta()
        if conta_id is None:
            return str(contas[0]["id"]) if contas else None
        if not any(str(c["id"]) == str(conta_id) for c in contas):
            raise BibliotecaError(422, "Conta de descoberta inválida: use uma conta Meta conectada.")
        return str(conta_id)

    def _find_perfil(self, handle: str) -> Optional[dict[str, Any]]:
        rows = (
            self.db.table(PERFIS).select(PERFIL_COLS).eq("rede", "instagram").eq("handle", handle)
            .execute().data or []
        )
        rows.sort(key=lambda r: r.get("org_id") is not None)  # the platform row first (legacy per-org rows after)
        return rows[0] if rows else None

    def _marca_ref_perfil(self, marca_id: str, perfil_id: str) -> bool:
        rows = (
            self.db.table(REFS).select("id").eq("org_id", self.org_id).eq("marca_id", str(marca_id))
            .eq("modo", "perfil").eq("perfil_id", str(perfil_id)).execute().data
        )
        return bool(rows)

    async def verificar(self, handle_bruto: str, marca_id: Optional[str] = None) -> dict[str, Any]:
        try:
            handle = normalizar_handle(handle_bruto)
        except HandleInvalido as exc:
            raise BibliotecaError(422, str(exc)) from None
        self._assert_sem_optout(handle)
        if marca_id:
            self.assert_marca(marca_id)
        row = self._find_perfil(handle)
        if row is not None:
            perfil = (await self.perfis_out([row]))[0]
            if marca_id and self._marca_ref_perfil(marca_id, str(row["id"])):
                return {"status": "na_minha_biblioteca", "perfil": perfil}
            return {"status": "ja_monitorado", "perfil": perfil}
        if not self.usa_apify() and not self.contas_descoberta():
            return {"status": "sem_conta_descoberta"}
        return {"status": "disponivel"}

    async def _enqueue_sync(self, perfil_id: str, *, suffix: str = "") -> Any:
        today = _now().strftime("%Y%m%d")
        return await self.jobs.enqueue(
            type="biblioteca.sync_perfil",
            payload={"perfil_id": str(perfil_id)},
            max_retries=2,
            dedupe_key=f"sync:{perfil_id}:{today}{suffix}",
        )

    def _add_ref_perfil(self, marca_id: str, perfil_id: str, auto: bool) -> bool:
        if self._marca_ref_perfil(marca_id, perfil_id):
            return False
        self._assert_ref_capacity(marca_id, 1)
        self._assert_perfis_da_marca(marca_id, 1)
        self.db.table(REFS).insert({
            "org_id": self.org_id, "marca_id": str(marca_id), "modo": "perfil", "perfil_id": str(perfil_id),
            "auto_atualizar": auto, "created_by": self.user_id,
        }).execute()
        return True

    def _assert_ref_capacity(self, marca_id: str, adding: int) -> None:
        rows = self.db.table(REFS).select("id", count="exact").eq("org_id", self.org_id).eq("marca_id", str(marca_id)).limit(1).execute()
        have = rows.count if getattr(rows, "count", None) is not None else len(rows.data or [])
        if have + adding > MAX_REFERENCIAS_MARCA:
            raise BibliotecaError(409, f"Limite de {MAX_REFERENCIAS_MARCA} itens na Minha Biblioteca atingido.")

    def _assert_perfis_da_marca(self, marca_id: str, adding: int) -> None:
        """``biblioteca_max_perfis_org`` now caps the SELECTED profiles of ONE brand (the library itself is platform-wide)."""
        if len(self._selecionados(marca_id)) + adding > self.max_perfis_org:
            raise BibliotecaError(409, f"Sua organização já monitora {self.max_perfis_org} perfis (limite).")

    def _assert_sem_optout(self, handle: str) -> None:
        if biblioteca_optout.esta_bloqueado(self.db, handle):
            raise erro_optout()

    def _total_perfis(self) -> int:
        res = self.db.table(PERFIS).select("id", count="exact").limit(1).execute()
        return int(res.count) if getattr(res, "count", None) is not None else len(res.data or [])

    def _evento(self, perfil_id: Any, tipo: str, *, viral_id: Optional[str] = None) -> None:
        registrar_evento(self.db, perfil_id=perfil_id, tipo=tipo, ator_id=self.user_id, viral_id=viral_id)

    async def criar_perfil(
        self, handle: str, conta_descoberta_id: Optional[str] = None, monitorar: bool = True
    ) -> dict[str, Any]:
        """ADMIN. Add a profile to the platform library (``org_id`` NULL). ``monitorar=False`` = library-only (no scrape)."""
        self._assert_sem_optout(handle)
        existing = self._find_perfil(handle)
        if existing is not None:
            raise BibliotecaError(
                409, "Este perfil já está na biblioteca.", code="perfil_ja_existe",
                extra={"perfil_id": str(existing["id"])},
            )
        if self._total_perfis() >= self.max_perfis_plataforma:
            raise BibliotecaError(
                409, f"A biblioteca já tem {self.max_perfis_plataforma} perfis (limite).", code="limite_perfis",
            )
        apify = self.usa_apify()
        conta = None if (apify or not monitorar) else self._conta_valida(conta_descoberta_id)
        pronto = bool(conta) or apify
        if not monitorar:
            status = "ativo"  # library-only: nothing to wait for (never scraped)
        else:
            status = "aguardando" if pronto else "sem_conta"
        erro_codigo = erro_mensagem = None
        if monitorar and not pronto:
            erro_codigo, erro_mensagem = "sem_conta", MSG_SEM_CONTA
        try:
            criado = criar_perfil_plataforma(
                self.db, handle=handle, origem="manual", ator_tipo="admin", ator_id=self.user_id, monitorar=bool(monitorar),
                status=status, conta=conta, erro_codigo=erro_codigo, erro_mensagem=erro_mensagem,
            )
        except Exception as exc:  # noqa: BLE001 - a concurrent admin won the UNIQUE (rede, handle): coded 409; else re-raise
            if not is_unique_violation(exc):
                raise
            raise BibliotecaError(409, "Este perfil já está na biblioteca.", code="perfil_ja_existe") from exc
        if not criado["criado"]:
            raise BibliotecaError(
                409, "Este perfil já está na biblioteca.", code="perfil_ja_existe", extra={"perfil_id": criado["id"]},
            )
        row = self._perfil_row(criado["id"])
        if monitorar and pronto:
            await self._enqueue_sync(str(row["id"]))
        return (await self.perfis_out([row]))[0]

    async def sincronizar(self, perfil_id: str) -> dict[str, Any]:
        row = self._perfil_row(perfil_id)
        if row["status"] == "pausado":
            raise BibliotecaError(409, "Perfil pausado: reative-o antes de atualizar.")
        now = _now()
        last = _parse_dt(row.get("ultima_sync_em"))
        if last is not None and now - last < SYNC_MIN_INTERVAL:
            wait = int((SYNC_MIN_INTERVAL - (now - last)).total_seconds()) + 1
            raise BibliotecaError(429, "Este perfil foi atualizado há pouco. Tente novamente mais tarde.", retry_after_s=wait)
        # A manual request stamps `proxima_sync_em = now` (the profile is due now); until the sync
        # that answers it lands (`ultima_sync_em` moves past it) a second click inside the hour is a 429.
        requested = _parse_dt(row.get("proxima_sync_em"))
        if requested is not None and requested <= now and now - requested < SYNC_MIN_INTERVAL and (
            last is None or last < requested
        ):
            wait = int((SYNC_MIN_INTERVAL - (now - requested)).total_seconds()) + 1
            raise BibliotecaError(429, "Já há uma atualização solicitada para este perfil.", retry_after_s=wait)
        # Spend/abuse cap: manual syncs per admin org per day. The org rides in the dedupe key so the count
        # needs no join (`sync:{perfil}:{YYYYMMDD}:manual:{HH}:{org}`).
        hoje = now.strftime("%Y%m%d")
        feitos = (
            self.db.table("jobs").select("id", count="exact")
            .eq("type", "biblioteca.sync_perfil").like("dedupe_key", f"sync:%:{hoje}:manual:%:{self.org_id}")
            .limit(1).execute()
        )
        n = feitos.count if getattr(feitos, "count", None) is not None else len(feitos.data or [])
        if n >= self.sync_manual_dia_org:
            raise BibliotecaError(
                429, "Limite diário de atualizações manuais da organização atingido. Tente amanhã.",
                retry_after_s=3600,
            )
        await self._enqueue_sync(str(row["id"]), suffix=f":manual:{now.strftime('%H')}:{self.org_id}")
        self.db.table(PERFIS).update({"proxima_sync_em": now.isoformat()}).eq("id", row["id"]).execute()
        if row["status"] in ("sem_conta", "erro", "nao_encontrado", "sem_credencial", "sem_orcamento"):
            self.db.table(PERFIS).update({"status": "aguardando", "erro_codigo": None, "erro_mensagem": None}).eq(
                "id", row["id"]).execute()
        self._evento(row["id"], "sincronizacao_solicitada")
        return {"perfil_id": row["id"], "enfileirado": True, "ingestao_ativa": self.ingestao_ativa()}

    async def patch_perfil(
        self, perfil_id: str, status: Optional[str], conta_id: Optional[str],
        monitorar: Optional[bool] = None, nome: Optional[str] = None,
    ) -> dict[str, Any]:
        row = self._perfil_row(perfil_id)
        patch: dict[str, Any] = {}
        eventos: list[str] = []
        if conta_id is not None:
            patch["conta_descoberta_id"] = self._conta_valida(conta_id)
            eventos.append("editado")
            if row["status"] == "sem_conta":
                patch.update(status="aguardando", erro_codigo=None, erro_mensagem=None)
        enqueue = "status" in patch
        if status == "pausado":
            if row["status"] != "pausado":
                eventos.append("pausado")
            patch["status"] = "pausado"
            enqueue = False
        elif status == "ativo" and row["status"] == "pausado":
            patch.update(status="aguardando", erro_codigo=None, erro_mensagem=None)
            eventos.append("retomado")
            enqueue = True
        if monitorar is not None and bool(monitorar) != bool(row.get("monitorar", True)):
            patch["monitorar"] = bool(monitorar)
            eventos.append("monitorar_ligado" if monitorar else "monitorar_desligado")
        if nome is not None and nome.strip() != (row.get("nome") or ""):
            patch["nome"], patch["nome_editado"] = nome.strip(), True
            eventos.append("editado")
        if patch:
            patch["updated_at"] = _now().isoformat()
            self.db.table(PERFIS).update(patch).eq("id", row["id"]).execute()
            for tipo in dict.fromkeys(eventos):
                self._evento(row["id"], tipo)
            row = self._perfil_row(perfil_id)
        if enqueue and row["status"] == "aguardando":
            await self._enqueue_sync(str(row["id"]), suffix=":ativar")
        return (await self.perfis_out([row]))[0]

    async def delete_perfil(self, perfil_id: str, apagar_estruturas: bool = False) -> None:
        """ADMIN. 409 ``perfil_com_estruturas`` (+ ``estruturas_total``) unless ``apagar_estruturas``; the refusal is
        decided BEFORE anything is erased. The profile's thumbnails, picture, videos, brand selections and (with the flag)
        Estruturas go with it (LGPD, contract 9.3)."""
        row = self._perfil_row(perfil_id)
        pid = str(row["id"])
        if not apagar_estruturas:
            total = self._total_estruturas_todas(pid)
            if total:
                raise erro_perfil_com_estruturas(total)
        await purgar_perfil(
            self.db, self.storage, row, ator_id=self.user_id, ator_tipo="admin", tipo_evento="excluido",
            apagar_estruturas=bool(apagar_estruturas),
        )

    def _total_estruturas_todas(self, perfil_id: str) -> int:
        res = self.db.table(ESTRUTURAS).select("id", count="exact").eq("perfil_id", str(perfil_id)).limit(1).execute()
        return int(res.count) if getattr(res, "count", None) is not None else len(res.data or [])

    # ── admin: add one video by its Instagram link ──────────────────────

    def _ingestao_org_ou_503(self) -> str:
        org = self._ingestao_org()
        if not org:
            raise BibliotecaError(503, biblioteca_fonte.MSG_SEM_ORG, code=biblioteca_fonte.CODIGO_SEM_ORG)
        return str(org)

    def _viral_card_por_id(self, viral_id: str) -> Optional[dict[str, Any]]:
        rows = self.db.table(VIRAIS).select(CARD_COLS).eq("id", str(viral_id)).execute().data
        return rows[0] if rows else None

    async def _card_de(self, viral_row: dict[str, Any]) -> dict[str, Any]:
        handles = {k: v["handle"] for k, v in self._perfis_by_id([str(viral_row["perfil_id"])]).items()}
        return await self._card(viral_row, handles)

    async def adicionar_por_link(self, url: str) -> dict[str, Any]:
        """ADMIN. Add ONE Instagram video by its post link (contract 4.2). Returns ``{viral, perfil_criado, ja_existia}``.

        Order of refusals: bad link (422 ``link_invalido``) -> already in the library by shortcode (200, nothing else
        happens) -> source cannot fetch a post (409 ``fonte_nao_suporta_link``) -> ingestion switch off (503) -> no ingestion
        org (503 ``ingestao_sem_org_plataforma``) -> daily Apify cap (429) -> fetch (404 ``post_nao_encontrado`` / 503
        ``sem_credencial`` / 429 / 503 ``fonte_indisponivel``) -> opted-out owner (409 ``perfil_optout``) -> profile cap (409). The video goes in
        through the SAME row builder as the sync and is analysed regardless of the viral threshold (an admin chose it)."""
        try:
            shortcode, canonico = extrair_shortcode(url)
        except LinkInvalido as exc:
            raise BibliotecaError(422, str(exc), code="link_invalido") from None
        existente = self._viral_por_shortcode(shortcode)
        if existente is not None:
            return {"viral": await self._card_de(existente), "perfil_criado": False, "ja_existia": True}
        if not self.usa_apify() or self._runner_factory is None:
            raise BibliotecaError(
                409, "A fonte de dados atual não consegue buscar um post por link.", code="fonte_nao_suporta_link",
            )
        if not self.ingestao_ativa():
            raise BibliotecaError(503, "A ingestão da biblioteca está desligada.", code="ingestao_desligada")
        org = self._ingestao_org_ou_503()
        agora = self._clock()
        if self._apify_dia and biblioteca_fonte.resultados_hoje(self.db, org, agora) >= self._apify_dia:
            raise BibliotecaError(429, biblioteca_fonte.MSG_SEM_ORCAMENTO, code="sem_orcamento", retry_after_s=3600)
        try:
            runner = self._runner_factory(org)
            post = await asyncio.to_thread(biblioteca_fonte.buscar_post, runner, shortcode=shortcode, url=canonico)
        except ApifyNotConfigured:
            raise BibliotecaError(503, biblioteca_fonte.MSG_SEM_CREDENCIAL, code="sem_credencial") from None
        except ApifyRateLimited as exc:
            raise BibliotecaError(
                429, "O serviço de leitura está ocupado. Tente novamente em instantes.", code="fonte_ocupada",
                retry_after_s=int(exc.retry_after_s or 60),
            ) from None
        except biblioteca_fonte.PostNaoEncontrado:
            raise BibliotecaError(404, "Post não encontrado. Confira o link — só posts públicos são lidos.",
                                  code="post_nao_encontrado") from None
        except ApifyRunFailed as exc:
            logger.error("biblioteca: leitura do post por link falhou (%s)", exc)  # the message carries no token / body
            raise BibliotecaError(503, "Não foi possível ler o post agora. Tente novamente mais tarde.",
                                  code="fonte_indisponivel") from None
        self._registrar_uso_post(org, post, agora)
        try:
            handle = normalizar_handle(post.owner)
        except HandleInvalido:
            raise BibliotecaError(404, "Post não encontrado. Confira o link — só posts públicos são lidos.",
                                  code="post_nao_encontrado") from None
        self._assert_sem_optout(handle)
        perfil = self._find_perfil(handle)
        perfil_criado = False
        if perfil is None:
            if self._total_perfis() >= self.max_perfis_plataforma:
                raise BibliotecaError(
                    409, f"A biblioteca já tem {self.max_perfis_plataforma} perfis (limite).", code="limite_perfis",
                )
            perfil = self._criar_perfil_so_biblioteca(handle)
            perfil_criado = True
        m = post.midia
        dup = self._viral_por_media(str(perfil["id"]), str(m.id))
        if dup is not None:  # same post under another key (a synced row without shortcode): backfill it, add nothing
            self.db.table(VIRAIS).update({"ig_shortcode": shortcode}).eq("id", dup["id"]).execute()
            return {"viral": await self._card_de(dup), "perfil_criado": perfil_criado, "ja_existia": True}
        stamp = agora.isoformat()
        # F10: the stored permalink is the CANONICAL one re-composed from the validated shortcode (``extrair_shortcode``
        # only ever yields https://www.instagram.com/{p|reel|tv}/<code>/) -- never the string the scraper returned.
        if not canonico.startswith(PERMALINK_PREFIXO):
            raise BibliotecaError(422, "Link inválido.", code="link_invalido")
        linha = {
            **biblioteca_fonte.campos_midia(m, stamp), "permalink": canonico,
            "ig_shortcode": shortcode, "perfil_id": str(perfil["id"]),
            "ig_media_id": str(m.id), "org_id": None, "origem_inclusao": "link_manual", "incluido_por": self.user_id,
            "transcricao_status": "nao_aplicavel", "classificacao_status": "pendente", "e_viral": False,
        }
        try:
            row = self.db.table(VIRAIS).insert(linha).execute().data[0]
        except Exception as exc:  # noqa: BLE001 - a concurrent paste won the UNIQUE: re-read it; else re-raise
            if not is_unique_violation(exc):
                raise
            vivo = self._viral_por_shortcode(shortcode)
            if vivo is None:
                raise
            return {"viral": await self._card_de(vivo), "perfil_criado": perfil_criado, "ja_existia": True}
        vid = str(row["id"])
        thumb = m.thumbnail_url or (m.media_url if not biblioteca_fonte.e_video(m) else None)
        if thumb and self._fetcher is not None:
            path = await biblioteca_fonte.espelhar_imagem(
                self._fetcher, self.storage, BUCKET, thumb,
                f"{prefixo_blobs(perfil)}/{perfil['id']}/{m.id}",
            )
            if path:
                self.db.table(VIRAIS).update({"thumbnail_path": path}).eq("id", vid).execute()
        self._evento(perfil["id"], "video_adicionado_por_link", viral_id=vid)
        await self._enfileirar_analise(vid, m, agora)
        row = self._viral_card_por_id(vid) or row
        return {"viral": await self._card_de(row), "perfil_criado": perfil_criado, "ja_existia": False}

    def _viral_por_shortcode(self, shortcode: str) -> Optional[dict[str, Any]]:
        rows = self.db.table(VIRAIS).select(CARD_COLS).eq("ig_shortcode", shortcode).execute().data
        return rows[0] if rows else None

    def _viral_por_media(self, perfil_id: str, ig_media_id: str) -> Optional[dict[str, Any]]:
        rows = (
            self.db.table(VIRAIS).select(CARD_COLS).eq("perfil_id", str(perfil_id)).eq("ig_media_id", str(ig_media_id))
            .execute().data
        )
        return rows[0] if rows else None

    def _criar_perfil_so_biblioteca(self, handle: str) -> dict[str, Any]:
        """The profile of a video added by link: a library-only row (``monitorar=false``, never scraped), created through
        the RPC (the opt-out registry is checked in its transaction)."""
        try:
            criado = criar_perfil_plataforma(
                self.db, handle=handle, origem="manual", ator_tipo="admin", ator_id=self.user_id, monitorar=False,
                status="ativo",
            )
        except Exception as exc:  # noqa: BLE001 - a concurrent admin created it: use theirs; else re-raise
            if not is_unique_violation(exc):
                raise
            vivo = self._find_perfil(handle)
            if vivo is None:
                raise
            return vivo
        return self._perfil_row(criado["id"])

    def _registrar_uso_post(self, org: str, post: biblioteca_fonte.PostBuscado, now: datetime) -> None:
        ledger_db = None
        if self._ledger_factory is not None:
            try:
                ledger_db = self._ledger_factory()
            except Exception as exc:  # noqa: BLE001 - booking is best-effort
                logger.warning("biblioteca: cliente do cost_ledger indisponível (%s)", type(exc).__name__)
        biblioteca_fonte.registrar_uso(
            self.db, ledger_db, org_id=org, perfil_id=None, results=post.results, usd=post.usd, run_id=post.run_id,
            now=now, step="biblioteca.por_link", reference_type=biblioteca_fonte.LEDGER_REFERENCE_POST,
        )

    async def _enfileirar_analise(self, viral_id: str, m: Any, now: datetime) -> None:
        """The SAME analysis a synced viral video gets (transcribe a reel, then classify; classify straight away otherwise)
        -- enqueued unconditionally: the viral threshold gates the SYNC, never an admin's explicit choice."""
        dia = now.strftime("%Y%m%d")
        if biblioteca_fonte.e_video(m) and m.media_url:
            self.db.table(VIRAIS).update({"transcricao_status": "pendente"}).eq("id", viral_id).execute()
            await self.jobs.enqueue(
                type="biblioteca.transcrever", payload={"viral_id": viral_id, "media_url": m.media_url},
                max_retries=2, dedupe_key=f"transcrever:{viral_id}:{dia}",
            )
        else:
            await self.jobs.enqueue(
                type="biblioteca.classificar", payload={"viral_id": viral_id}, max_retries=2,
                dedupe_key=f"classificar:{viral_id}:{dia}",
            )

    # ── Minha Biblioteca ────────────────────────────────────────────────

    async def list_referencias(self, marca_id: str, q: Optional[str] = None) -> list[dict[str, Any]]:
        self.assert_marca(marca_id)
        refs = self._refs(marca_id)
        perfis = self._perfis_by_id([str(r["perfil_id"]) for r in refs if r.get("perfil_id")])
        viral_ids = [str(r["viral_id"]) for r in refs if r.get("viral_id")]
        virais: dict[str, dict[str, Any]] = {}
        for chunk in batched(sorted(set(viral_ids))):
            for v in self.db.table(VIRAIS).select(CARD_COLS).in_("id", chunk).execute().data or []:
                virais[str(v["id"])] = v
        vperfis = self._perfis_by_id([str(v["perfil_id"]) for v in virais.values()])
        handles = {k: v["handle"] for k, v in {**vperfis, **perfis}.items()}
        counts = self._counts(list(perfis))
        ativa = self.ingestao_ativa()
        term = (q or "").strip().lower().lstrip("@")
        out: list[dict[str, Any]] = []
        for r in refs:
            perfil = viral = None
            hay = ""
            if r["modo"] == "perfil":
                prow = perfis.get(str(r["perfil_id"]))
                if prow is None:
                    continue
                perfil = await self._perfil_out(prow, counts.get(str(prow["id"]), (0, 0)), ativa)
                hay = f"{prow['handle']} {prow.get('nome') or ''}".lower()
            else:
                vrow = virais.get(str(r["viral_id"]))
                if vrow is None:
                    continue
                viral = await self._card(vrow, handles)
                hay = f"{handles.get(str(vrow['perfil_id']), '')} {vrow.get('gancho') or ''}".lower()
            if term and term not in hay:
                continue
            out.append({
                "id": r["id"], "modo": r["modo"], "perfil": perfil, "viral": viral,
                "auto_atualizar": bool(r["auto_atualizar"]), "posts_ate": r.get("posts_ate"),
                "updated_at": r.get("updated_at"),
            })
        return out

    async def criar_referencias_perfil(self, marca_id: str, perfil_ids: list[str], auto: bool) -> dict[str, int]:
        self.assert_marca(marca_id)
        ids = list(dict.fromkeys(str(p) for p in perfil_ids))
        found = self._perfis_by_id(ids)
        if len(found) != len(ids):
            raise BibliotecaError(404, "Perfil não encontrado")
        criadas = 0
        for pid in ids:
            if self._add_ref_perfil(marca_id, pid, auto):
                criadas += 1
        return {"criadas": criadas, "ja_existentes": len(ids) - criadas}

    async def criar_referencias_video(self, marca_id: str, viral_ids: list[str]) -> dict[str, int]:
        self.assert_marca(marca_id)
        ids = list(dict.fromkeys(str(v) for v in viral_ids))
        found = {
            str(r["id"]) for chunk in batched(ids) for r in (
                self.db.table(VIRAIS).select("id").in_("id", chunk).execute().data or []
            )
        }
        if len(found) != len(ids):
            raise BibliotecaError(404, "Vídeo não encontrado")
        have = {
            str(r["viral_id"]) for r in (
                self.db.table(REFS).select("viral_id").eq("org_id", self.org_id).eq("marca_id", str(marca_id))
                .eq("modo", "video").execute().data or []
            )
        }
        novos = [v for v in ids if v not in have]
        self._assert_ref_capacity(marca_id, len(novos))
        for vid in novos:
            self.db.table(REFS).insert({
                "org_id": self.org_id, "marca_id": str(marca_id), "modo": "video", "viral_id": vid,
                "auto_atualizar": False, "created_by": self.user_id,
            }).execute()
        return {"criadas": len(novos), "ja_existentes": len(ids) - len(novos)}

    def _ref_row(self, ref_id: str) -> dict[str, Any]:
        rows = (
            self.db.table(REFS).select("id,marca_id,modo,perfil_id,viral_id,auto_atualizar,posts_ate,updated_at")
            .eq("id", str(ref_id)).eq("org_id", self.org_id).execute().data
        )
        if not rows:
            raise BibliotecaError(404, "Referência não encontrada")
        return rows[0]

    async def patch_referencia(self, ref_id: str, auto: Optional[bool], posts_ate: Optional[str]) -> dict[str, Any]:
        row = self._ref_row(ref_id)
        patch: dict[str, Any] = {}
        if auto is not None:
            patch["auto_atualizar"] = auto
        if posts_ate is not None:
            if row["modo"] != "perfil":
                raise BibliotecaError(422, "A data limite só vale para perfis.")
            try:
                datetime.strptime(posts_ate, "%Y-%m-%d")
            except ValueError:
                raise BibliotecaError(422, "Data inválida.") from None
            patch["posts_ate"] = posts_ate
        if patch:
            patch["updated_at"] = _now().isoformat()
            self.db.table(REFS).update(patch).eq("id", row["id"]).eq("org_id", self.org_id).execute()
        refs = await self.list_referencias(str(row["marca_id"]))
        for r in refs:
            if str(r["id"]) == str(row["id"]):
                return r
        raise BibliotecaError(404, "Referência não encontrada")

    def delete_referencia(self, ref_id: str) -> None:
        row = self._ref_row(ref_id)
        self.db.table(REFS).delete().eq("id", row["id"]).eq("org_id", self.org_id).execute()


__all__ = [
    "BUCKET",
    "PERMALINK_PREFIXO",
    "apagar_transcricoes",
    "criar_perfil_plataforma",
    "minimizar_perfil",
    "EVENTOS",
    "prefixo_blobs",
    "purgar_handle",
    "purgar_perfil",
    "registrar_evento",
    "erro_perfil_com_estruturas",
    "BibliotecaError",
    "BibliotecaService",
    "CONTEXTO_TIPO",
    "PERFIS",
    "REFS",
    "VIRAIS",
    "ViralFiltros",
    "aplicar_filtros",
    "keywords",
    "pool_expression",
]
