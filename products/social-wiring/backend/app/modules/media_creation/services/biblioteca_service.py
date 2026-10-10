"""Biblioteca de Virais + Minha Biblioteca -- the request-path service (endpoints 7-19).

Contract: ``projects/core-studio/specs/geracao-contract.md`` sections 2.3, 4.3, 9.2, 9.3. The
ingestion pipeline (sync / transcribe / classify) lives in :mod:`.biblioteca_ingestao`; this module
only reads, edits the allow-list and ENQUEUES jobs.

Rules every method keeps:

* every query is scoped to ``org_id``; a foreign / unknown marca, profile, viral or reference is a 404
  (ids are not enumerable);
* thumbnails live in the PRIVATE ``sw-biblioteca`` bucket and are only ever served as short-TTL signed
  URLs minted per request;
* a Graph / vendor error text never reaches a client -- the stored ``erro_mensagem`` is OUR pt-BR copy.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from noctusai_lib.domain.jobs import JobRepository
from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.persistence.table_reads import batched
from noctusai_lib.integrations.storage import StorageBackend

from app.modules.media_creation.geracao_taxonomias import FORMATOS_VIDEO, NICHOS, PROFISSOES
from app.modules.media_creation.schemas.biblioteca import (
    MAX_REFERENCIAS_MARCA,
    PAGE_SIZE,
    HandleInvalido,
    normalizar_handle,
)

logger = logging.getLogger(__name__)

PERFIS = "cs_perfis_monitorados"
VIRAIS = "cs_virais"
REFS = "cs_biblioteca_referencias"
MARCA_PERFIL = "cs_marca_perfil"
ACCOUNTS = "integration_accounts"
TRANSCRICOES = "transcricoes"
CONTEXTO_TIPO = "biblioteca_viral"
#: PRIVATE bucket (migration 229): library thumbnails, never public.
BUCKET = "sw-biblioteca"
SIGNED_TTL_SECONDS = 900
SYNC_MIN_INTERVAL = timedelta(hours=1)
TRECHO_CHARS = 200

PERFIL_COLS = (
    "id,org_id,handle,conta_descoberta_id,ig_user_id,nome,foto_path,seguidores,media_count,status,"
    "erro_codigo,erro_mensagem,ultima_sync_em,proxima_sync_em,metrica_base,mediana_metrica,created_by"
)
CARD_COLS = (
    "id,codigo,perfil_id,permalink,publicado_em,views,likes,comments,duracao_s,score_viral,e_viral,"
    "thumbnail_path,gancho,caption"
)
DETALHE_COLS = (
    CARD_COLS + ",transcricao_texto,transcricao_status,classificacao_status,formato_ids,nicho_ids,"
    "profissao_ids,gatilho,blueprint"
)

_NICHO = dict(NICHOS)
_PROFISSAO = dict(PROFISSOES)
_FORMATO = {i: nome for i, nome, _ in FORMATOS_VIDEO}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_KW_STRIP = re.compile(r"[,()%*\\\":;]")
MAX_KEYWORDS = 8
MAX_KEYWORD_CHARS = 40

MSG_SEM_CONTA = (
    "Conecte uma conta do Instagram pelo login do Facebook (Meta) para monitorar perfis."
)


class BibliotecaError(Exception):
    def __init__(self, status: int, detail: str, *, retry_after_s: Optional[int] = None):
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.retry_after_s = retry_after_s


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
    org_id: str,
    auto: Optional[tuple[list[int], list[int]]] = None,
    pool_expr: Optional[str] = None,
) -> Any:
    """Add every ``cs_virais`` filter of ``f`` to a select builder. Pure over the builder, so a test can
    read back the recorded predicates (the array-overlap / ``or`` operators are match-all in the mock
    client and are therefore asserted by predicate, not by behaviour). ``auto`` is the marca's
    ``(nichos, profissoes)`` for the automatic filter; ``pool_expr`` the ``Minha Biblioteca`` allow-list."""
    query = query.eq("org_id", org_id)
    if f.somente_virais:
        query = query.eq("e_viral", True)
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


async def purgar_perfil(db: Any, storage: StorageBackend, org_id: str, perfil: dict[str, Any]) -> int:
    """Erase a monitored profile and EVERYTHING derived from it (LGPD, contract 9.3): the thumbnails
    and the profile picture (by row path AND by the profile's whole ``{org}/{perfil}/`` prefix), the
    library ``transcricoes`` rows, then the profile row (its virais and video references cascade).

    A blob that cannot be deleted never keeps the row alive -- it is logged and counted (the return
    value) and the orphan-prefix sweep (``biblioteca_scheduler.varrer_blobs_orfaos``) retries it: once
    the row is gone the prefix has no owner, which is exactly what that sweep deletes. Used by the
    endpoint (user delete) and by the retention purge, so both erase the same set."""
    pid = str(perfil["id"])
    org_id = str(org_id)
    virais = list(
        iter_paged_rows(
            lambda s, e: db.table(VIRAIS).select("id,thumbnail_path").eq("org_id", org_id)
            .eq("perfil_id", pid).order("id").range(s, e).execute().data
        )
    )
    keys = {v["thumbnail_path"] for v in virais if v.get("thumbnail_path")}
    if perfil.get("foto_path"):
        keys.add(perfil["foto_path"])
    try:
        keys.update(await storage.list_keys(bucket=BUCKET, prefix=f"{org_id}/{pid}/", limit=1000))
    except Exception:  # noqa: BLE001 - the row-path keys above still go; the sweep covers the rest
        logger.warning("biblioteca: list_keys falhou perfil=%s", pid, exc_info=True)
    falhas = 0
    for key in sorted(keys):
        try:
            await storage.delete(bucket=BUCKET, key=key)
        except Exception:  # noqa: BLE001 - never leave the row alive because a blob delete failed
            falhas += 1
            logger.warning("biblioteca: blob delete failed key=%s (a varredura de órfãos repete)", key, exc_info=True)
    for chunk in batched([str(v["id"]) for v in virais]):
        db.table(TRANSCRICOES).delete().eq("org_id", org_id).eq("contexto_tipo", CONTEXTO_TIPO).in_(
            "contexto_ref", chunk).neq("status", "processando").execute()
    db.table(PERFIS).delete().eq("id", pid).eq("org_id", org_id).execute()
    return falhas


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
        max_perfis_org: int = 30,
        sync_manual_dia_org: int = 20,
    ) -> None:
        self.db = db
        self.org_id = str(org_id)
        self.user_id = user_id
        self.storage = storage
        self.jobs = jobs
        self._switch = switch
        self.max_perfis_org = max_perfis_org
        self.sync_manual_dia_org = sync_manual_dia_org

    # ── guards ──────────────────────────────────────────────────────────

    def ingestao_ativa(self) -> bool:
        return bool(self._switch())

    def assert_marca(self, marca_id: str) -> None:
        rows = (
            self.db.table("marcas").select("id").eq("id", str(marca_id)).eq("org_id", self.org_id)
            .execute().data
        )
        if not rows:
            raise BibliotecaError(404, "Marca não encontrada")

    def _perfil_row(self, perfil_id: str) -> dict[str, Any]:
        rows = (
            self.db.table(PERFIS).select(PERFIL_COLS).eq("id", str(perfil_id)).eq("org_id", self.org_id)
            .execute().data
        )
        if not rows:
            raise BibliotecaError(404, "Perfil não encontrado")
        return rows[0]

    def _viral_row(self, viral_id: str, cols: str = DETALHE_COLS) -> dict[str, Any]:
        rows = (
            self.db.table(VIRAIS).select(cols).eq("id", str(viral_id)).eq("org_id", self.org_id)
            .execute().data
        )
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
                .eq("org_id", self.org_id).in_("perfil_id", chunk).order("id").range(s, e).execute().data
            )
            for r in rows:
                c = out.get(str(r["perfil_id"]))
                if c is not None:
                    c[1] += 1
                    c[0] += 1 if r.get("e_viral") else 0
        return {k: (v[0], v[1]) for k, v in out.items()}

    async def _perfil_out(self, row: dict[str, Any], counts: tuple[int, int], ativa: bool) -> dict[str, Any]:
        return {
            "id": row["id"],
            "handle": row["handle"],
            "nome": row.get("nome"),
            "foto_url": await self._signed(row.get("foto_path")),
            "seguidores": row.get("seguidores"),
            "status": row["status"],
            "erro_mensagem": row.get("erro_mensagem"),
            "ultima_sync_em": row.get("ultima_sync_em"),
            "metrica_base": row.get("metrica_base"),
            "mediana_metrica": float(row["mediana_metrica"]) if row.get("mediana_metrica") is not None else None,
            "virais": counts[0],
            "posts": counts[1],
            "ingestao_ativa": ativa,
        }

    async def perfis_out(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts = self._counts([str(r["id"]) for r in rows])
        ativa = self.ingestao_ativa()
        return [await self._perfil_out(r, counts.get(str(r["id"]), (0, 0)), ativa) for r in rows]

    def _perfis_by_id(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for chunk in batched(sorted(set(ids))):
            for r in (
                self.db.table(PERFIS).select(PERFIL_COLS).eq("org_id", self.org_id).in_("id", chunk)
                .execute().data or []
            ):
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
            "codigo": row["codigo"],
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
        query = aplicar_filtros(query, f, org_id=self.org_id, auto=auto, pool_expr=pool_expr)
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
        )
        if incluir_blueprint:
            out["blueprint"] = row.get("blueprint")
        return out

    # ── perfis ──────────────────────────────────────────────────────────

    def _org_perfis(self) -> list[dict[str, Any]]:
        return list(
            iter_paged_rows(
                lambda s, e: self.db.table(PERFIS).select(PERFIL_COLS).eq("org_id", self.org_id)
                .order("id").range(s, e).execute().data
            )
        )

    async def list_perfis(self, q: Optional[str] = None) -> list[dict[str, Any]]:
        rows = self._org_perfis()
        term = (q or "").strip().lower().lstrip("@")
        if term:
            rows = [r for r in rows if term in (r["handle"] or "") or term in (r.get("nome") or "").lower()]
        rows.sort(key=lambda r: r["handle"])
        return await self.perfis_out(rows)

    def contas_descoberta(self) -> list[dict[str, Any]]:
        rows = (
            self.db.table(ACCOUNTS)
            .select("id,account_label,metadata,status,is_default")
            .eq("org_id", self.org_id).eq("provider", "meta").eq("status", "validated")
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
            self.db.table(PERFIS).select(PERFIL_COLS).eq("org_id", self.org_id).eq("rede", "instagram")
            .eq("handle", handle).execute().data
        )
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
        if marca_id:
            self.assert_marca(marca_id)
        row = self._find_perfil(handle)
        if row is not None:
            perfil = (await self.perfis_out([row]))[0]
            if marca_id and self._marca_ref_perfil(marca_id, str(row["id"])):
                return {"status": "na_minha_biblioteca", "perfil": perfil}
            return {"status": "ja_monitorado", "perfil": perfil}
        if not self.contas_descoberta():
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

    async def criar_perfil(self, marca_id: str, handle: str, conta_descoberta_id: Optional[str]) -> dict[str, Any]:
        self.assert_marca(marca_id)
        existing = self._find_perfil(handle)
        if existing is not None:
            self._add_ref_perfil(marca_id, str(existing["id"]), True)
            return (await self.perfis_out([existing]))[0]
        if len(self._org_perfis()) >= self.max_perfis_org:
            raise BibliotecaError(409, f"Sua organização já monitora {self.max_perfis_org} perfis (limite).")
        conta = self._conta_valida(conta_descoberta_id)
        payload = {
            "org_id": self.org_id, "rede": "instagram", "handle": handle, "conta_descoberta_id": conta,
            "status": "aguardando" if conta else "sem_conta", "created_by": self.user_id,
        }
        if not conta:
            payload["erro_codigo"] = "sem_conta"
            payload["erro_mensagem"] = MSG_SEM_CONTA
        row = self.db.table(PERFIS).insert(payload).execute().data[0]
        self._add_ref_perfil(marca_id, str(row["id"]), True)
        if conta:
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
        # Spend/abuse cap: manual syncs per org per day. The org rides in the dedupe key so the count
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
        self.db.table(PERFIS).update({"proxima_sync_em": now.isoformat()}).eq("id", row["id"]).eq(
            "org_id", self.org_id).execute()
        if row["status"] in ("sem_conta", "erro", "nao_encontrado"):
            self.db.table(PERFIS).update({"status": "aguardando", "erro_codigo": None, "erro_mensagem": None}).eq(
                "id", row["id"]).eq("org_id", self.org_id).execute()
        return {"perfil_id": row["id"], "enfileirado": True, "ingestao_ativa": self.ingestao_ativa()}

    async def patch_perfil(self, perfil_id: str, status: Optional[str], conta_id: Optional[str]) -> dict[str, Any]:
        row = self._perfil_row(perfil_id)
        patch: dict[str, Any] = {}
        if conta_id is not None:
            patch["conta_descoberta_id"] = self._conta_valida(conta_id)
            if row["status"] == "sem_conta":
                patch.update(status="aguardando", erro_codigo=None, erro_mensagem=None)
        enqueue = "status" in patch
        if status == "pausado":
            patch["status"] = "pausado"
            enqueue = False
        elif status == "ativo" and row["status"] == "pausado":
            patch.update(status="aguardando", erro_codigo=None, erro_mensagem=None)
            enqueue = True
        if patch:
            patch["updated_at"] = _now().isoformat()
            self.db.table(PERFIS).update(patch).eq("id", row["id"]).eq("org_id", self.org_id).execute()
            row = self._perfil_row(perfil_id)
        if enqueue and row["status"] == "aguardando":
            await self._enqueue_sync(str(row["id"]), suffix=":ativar")
        return (await self.perfis_out([row]))[0]

    async def delete_perfil(self, perfil_id: str, marca_id: Optional[str] = None) -> None:
        row = self._perfil_row(perfil_id)
        pid = str(row["id"])
        virais = list(
            iter_paged_rows(
                lambda s, e: self.db.table(VIRAIS).select("id,thumbnail_path").eq("org_id", self.org_id)
                .eq("perfil_id", pid).order("id").range(s, e).execute().data
            )
        )
        viral_ids = [str(v["id"]) for v in virais]
        marcas: set[str] = {
            str(r["marca_id"]) for r in (
                self.db.table(REFS).select("marca_id").eq("org_id", self.org_id).eq("perfil_id", pid).execute().data or []
            )
        }
        for chunk in batched(viral_ids):
            marcas |= {
                str(r["marca_id"]) for r in (
                    self.db.table(REFS).select("marca_id").eq("org_id", self.org_id).in_("viral_id", chunk)
                    .execute().data or []
                )
            }
        outras = marcas - ({str(marca_id)} if marca_id else set())
        if (marca_id and outras) or (not marca_id and len(marcas) > 1):
            raise BibliotecaError(409, "Perfil em uso por outra marca")
        # LGPD (contract 9.3): the profile's thumbnails, picture and transcripts go with it.
        await purgar_perfil(self.db, self.storage, self.org_id, row)

    # ── Minha Biblioteca ────────────────────────────────────────────────

    async def list_referencias(self, marca_id: str, q: Optional[str] = None) -> list[dict[str, Any]]:
        self.assert_marca(marca_id)
        refs = self._refs(marca_id)
        perfis = self._perfis_by_id([str(r["perfil_id"]) for r in refs if r.get("perfil_id")])
        viral_ids = [str(r["viral_id"]) for r in refs if r.get("viral_id")]
        virais: dict[str, dict[str, Any]] = {}
        for chunk in batched(sorted(set(viral_ids))):
            for v in (
                self.db.table(VIRAIS).select(CARD_COLS).eq("org_id", self.org_id).in_("id", chunk).execute().data or []
            ):
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
                self.db.table(VIRAIS).select("id").eq("org_id", self.org_id).in_("id", chunk).execute().data or []
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
    "purgar_perfil",
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
