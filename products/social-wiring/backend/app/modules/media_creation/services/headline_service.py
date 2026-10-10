"""Headlines -- the data service behind ``routers/headlines.py`` (Geração, BE-4).

Contract ``specs/geracao-contract.md`` section 4.4. Pure over the PostgREST client + the injected
queue repository + (optional) storage for thumbnail signing. Every read / write is org-scoped AND
marca-scoped: a foreign or unknown marca / batch / headline / viral / profile / topic is a uniform
404 (ids are not enumerable). The generation itself runs in ``headline_pipeline`` (a queue job);
this module only validates, enqueues, lists and edits.

Spend caps (contract 9.4): ``headline_lotes_dia_usuario`` batches per user per rolling 24 h
(429 + ``Retry-After``), one active manual batch per user (409; the partial unique index of
migration 229 is the last word), one automatic-suggestion batch per marca per day (the cron and the
"Gerar sugestões agora" button share it). The seed org LLM budget applies on top.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional
from zoneinfo import ZoneInfo

from noctusai_lib.domain.jobs import JobRepository
from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.persistence.table_reads import PAGE_SIZE, batched
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from app.modules.media_creation.geracao_taxonomias import FORMATO_IDS
from app.modules.media_creation.pesquisa_variables import VARIABLE_SLUGS
from app.modules.media_creation.services import headline_pipeline as pipe
from app.modules.media_creation.services.viral_card import viral_cards

logger = logging.getLogger(__name__)

BRT = ZoneInfo("America/Sao_Paulo")

FORM_ORIGENS = ("form_me", "form_public", "form_viral")
ALL_ORIGENS = FORM_ORIGENS + ("biblioteca", "sugestao_auto")
ACTIVE = ("criando", "processando")
RETRY_AFTER_SECONDS = 3600
SUGESTAO_JANELA_DIAS = 30

RESUMO_LABEL = {
    "form_me": "Headlines para mim",
    "form_public": "Headlines para o público",
    "form_viral": "Headlines de assuntos virais",
    "biblioteca": "Headline de um viral",
    "sugestao_auto": "Sugestão automática",
}

LOTE_COLS = (
    "id,marca_id,created_by,origem,parametros,status,etapa,estruturas_total,estruturas_processadas,"
    "estruturas_com_erro,aviso_poucas_estruturas,fallback_metodo,erro,created_at,finished_at"
)
HEADLINE_COLS = (
    "id,marca_id,lote_id,viral_id,template_metodo,texto,texto_original,angulo,itens_usados,favorita,"
    "favoritada_em,modo,created_at"
)


class HeadlineError(Exception):
    def __init__(self, status: int, detail: Any, *, retry_after: Optional[int] = None):
        super().__init__(str(detail))
        self.status = status
        self.detail = detail
        self.retry_after = retry_after


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat()


def _like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def resumo_do_lote(origem: str, params: Mapping[str, Any]) -> str:
    label = RESUMO_LABEL.get(origem, origem)
    assunto = (params.get("assunto") or params.get("assunto_livre") or "").strip()
    return f"{label} · {assunto[:80]}" if assunto else label


def metrica(card: Optional[Mapping[str, Any]]) -> int:
    """The viral metric used for ordering: views, else likes + comments (Business Discovery does not
    serve views); a headline without a viral sorts last."""
    if not card:
        return -1
    if card.get("views") is not None:
        return int(card["views"])
    return int(card.get("likes") or 0) + int(card.get("comments") or 0)


class HeadlineService:
    def __init__(
        self,
        db: Any,
        org_id: str,
        user_id: Optional[str] = None,
        *,
        cfg: Any = None,
        jobs: Optional[JobRepository] = None,
        storage: Optional[StorageBackend] = None,
    ):
        if cfg is None:
            from app.config import settings as cfg
        self.db = db
        self.org_id = org_id
        self.user_id = user_id
        self.cfg = cfg
        self.jobs = jobs
        self.storage = storage

    # ── guards ──────────────────────────────────────────────────────────

    def assert_marca(self, marca_id: str) -> None:
        rows = self.db.table("marcas").select("id").eq("id", marca_id).eq("org_id", self.org_id).execute().data
        if not rows:
            raise HeadlineError(404, "Marca não encontrada")

    def _perfil(self, marca_id: str) -> Optional[dict[str, Any]]:
        return pipe.carregar_perfil(self.db, self.org_id, marca_id)

    # ── presenters ──────────────────────────────────────────────────────

    async def _viral_cards(self, viral_ids: list[str]) -> dict[str, dict[str, Any]]:
        return await viral_cards(self.db, self.org_id, self.storage, viral_ids)

    def _roteiros_por_headline(self, headline_ids: list[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for chunk in batched(headline_ids):
            for r in (
                self.db.table("cs_roteiros").select("id,headline_id")
                .eq("org_id", self.org_id).in_("headline_id", chunk).order("created_at").execute().data or []
            ):
                out.setdefault(str(r["headline_id"]), str(r["id"]))
        return out

    async def present_headlines(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cards = await self._viral_cards([str(r["viral_id"]) for r in rows if r.get("viral_id")])
        roteiros = self._roteiros_por_headline([str(r["id"]) for r in rows])
        return [
            {
                "id": str(r["id"]), "marca_id": str(r["marca_id"]),
                "lote_id": str(r["lote_id"]) if r.get("lote_id") else None,
                "texto": r["texto"], "texto_original": r.get("texto_original"),
                "angulo": r.get("angulo"), "viral": cards.get(str(r["viral_id"])) if r.get("viral_id") else None,
                "template_metodo": r.get("template_metodo"), "itens_usados": r.get("itens_usados") or [],
                "favorita": bool(r.get("favorita")), "modo": r.get("modo"),
                "roteiro_id": roteiros.get(str(r["id"])), "created_at": r["created_at"],
            }
            for r in rows
        ]

    @staticmethod
    def present_lote(r: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": str(r["id"]), "marca_id": str(r["marca_id"]), "origem": r["origem"], "status": r["status"],
            "etapa": r.get("etapa"), "estruturas_total": r.get("estruturas_total") or 0,
            "estruturas_processadas": r.get("estruturas_processadas") or 0,
            "estruturas_com_erro": r.get("estruturas_com_erro") or 0,
            "aviso_poucas_estruturas": bool(r.get("aviso_poucas_estruturas")),
            "fallback_metodo": bool(r.get("fallback_metodo")), "erro": r.get("erro"),
            "resumo": resumo_do_lote(r["origem"], r.get("parametros") or {}),
            "created_at": r["created_at"], "finished_at": r.get("finished_at"),
        }

    # ── batch creation ──────────────────────────────────────────────────

    def _validate_params(self, marca_id: str, p: dict[str, Any]) -> None:
        origem = p["origem"]
        if origem in ("form_me", "form_public"):
            bad = [v for v in p["variaveis"] if v != "*" and v not in VARIABLE_SLUGS]
            if bad:
                raise HeadlineError(422, f"Variável desconhecida: {bad[0]}")
            valores = p.get("valores") or {}
            unknown = [s for s in valores if s not in VARIABLE_SLUGS]
            if unknown:
                raise HeadlineError(422, f"Variável desconhecida: {unknown[0]}")
            wanted = sorted({str(i) for ids in valores.values() for i in ids})
            if wanted:
                found = set()
                for chunk in batched(wanted):
                    found |= {
                        str(r["id"]) for r in (
                            self.db.table(pipe.ITENS).select("id")
                            .eq("org_id", self.org_id).eq("marca_id", marca_id).eq("status", "approved")
                            .in_("id", chunk).execute().data or []
                        )
                    }
                if len(found) != len(wanted):
                    raise HeadlineError(422, "Item da pesquisa não encontrado")
        ref = p.get("referencia")
        if ref:
            if ref["tipo"] == "perfil":
                self._assert_perfis(ref["perfil_ids"])
            elif ref["tipo"] == "formato" and any(f not in FORMATO_IDS for f in ref["formato_ids"]):
                raise HeadlineError(422, "Formato desconhecido")
        if p.get("assunto_ids"):
            ids = sorted({str(i) for i in p["assunto_ids"]})
            found = set()
            for chunk in batched(ids):
                found |= {
                    str(r["id"]) for r in (
                        self.db.table(pipe.TOPICOS).select("id")
                        .eq("org_id", self.org_id).eq("marca_id", marca_id).eq("status", "approved")
                        .in_("id", chunk).execute().data or []
                    )
                }
            if len(found) != len(ids):
                raise HeadlineError(404, "Assunto não encontrado")
        if origem == "biblioteca":
            rows = (
                self.db.table(pipe.VIRAIS).select("id,classificacao_status,blueprint")
                .eq("org_id", self.org_id).eq("id", str(p["viral_id"])).execute().data
            )
            if not rows:
                raise HeadlineError(404, "Viral não encontrado")
            if rows[0].get("classificacao_status") != "concluida" or not (rows[0].get("blueprint") or "").strip():
                raise HeadlineError(409, "Este viral ainda não tem estrutura — aguarde a classificação")

    def _assert_perfis(self, perfil_ids: list[Any]) -> None:
        ids = sorted({str(i) for i in perfil_ids})
        found = {
            str(r["id"]) for r in (
                self.db.table("cs_perfis_monitorados").select("id")
                .eq("org_id", self.org_id).in_("id", ids).execute().data or []
            )
        }
        if found != set(ids):
            raise HeadlineError(404, "Perfil não encontrado")

    def _check_user_limits(self) -> None:
        if not self.user_id:
            return
        active = (
            self.db.table(pipe.LOTES).select("id")
            .eq("org_id", self.org_id).eq("created_by", self.user_id)
            .in_("status", list(ACTIVE)).neq("origem", "sugestao_auto").execute().data
        )
        if active:
            raise HeadlineError(409, "Já existe uma geração em andamento")
        since = _iso(_now() - timedelta(hours=24))
        used = (
            self.db.table(pipe.LOTES).select("id", count="exact")
            .eq("org_id", self.org_id).eq("created_by", self.user_id)
            .neq("origem", "sugestao_auto").gte("created_at", since).execute()
        )
        n = used.count if getattr(used, "count", None) is not None else len(used.data or [])
        if n >= int(self.cfg.headline_lotes_dia_usuario):
            raise HeadlineError(429, "Limite diário de gerações de headlines atingido", retry_after=RETRY_AFTER_SECONDS)

    async def _insert_and_enqueue(self, marca_id: str, origem: str, params: dict[str, Any]) -> dict[str, Any]:
        if self.jobs is None:
            raise HeadlineError(503, {"codigo": "geracao_indisponivel", "mensagem": "A geração está indisponível no momento."})
        lote_id = str(uuid.uuid4())
        try:
            inserted = self.db.table(pipe.LOTES).insert({
                "id": lote_id, "org_id": self.org_id, "marca_id": marca_id, "created_by": self.user_id,
                "origem": origem, "parametros": params, "status": "criando",
                "etapa": "Na fila", "created_at": _iso(),
            }).execute().data
        except Exception as exc:  # noqa: BLE001 - the unique index = a concurrent active batch
            if is_unique_violation(exc):
                raise HeadlineError(409, "Já existe uma geração em andamento") from exc
            raise
        row = inserted[0] if inserted else {
            "id": lote_id, "marca_id": marca_id, "origem": origem, "parametros": params,
            "status": "criando", "created_at": _iso(),
        }
        try:
            queued = await self.jobs.enqueue(
                type=pipe.JOB_TYPE, payload={"lote_id": lote_id},
                dedupe_key=f"{pipe.JOB_TYPE}:{lote_id}", max_retries=2,
            )
        except Exception as exc:  # noqa: BLE001 - settled as failed, surfaced as 503
            logger.error("headline.gerar: enqueue falhou para %s: %s", lote_id, exc)
            self.db.table(pipe.LOTES).update({
                "status": "falha", "erro": "Falha ao iniciar a geração", "etapa": None, "finished_at": _iso(),
            }).eq("id", lote_id).eq("org_id", self.org_id).execute()
            raise HeadlineError(503, "Falha ao iniciar a geração") from exc
        upd = (
            self.db.table(pipe.LOTES).update({"queue_job_id": queued.id})
            .eq("id", lote_id).eq("org_id", self.org_id).execute().data
        )
        return self.present_lote(upd[0] if upd else {**row, "queue_job_id": queued.id})

    async def create_lote(self, params: dict[str, Any]) -> dict[str, Any]:
        """``params`` = the validated ``LoteCreate`` dumped with ``mode='json'``."""
        marca_id = str(params["marca_id"])
        self.assert_marca(marca_id)
        self._validate_params(marca_id, params)
        perfil = self._perfil(marca_id)
        if not ((perfil or {}).get("bio") or "").strip():
            raise HeadlineError(422, "Preencha a bio em Meu Perfil antes de gerar headlines")
        self._check_user_limits()
        return await self._insert_and_enqueue(marca_id, params["origem"], params)

    async def reprocessar(self, lote_id: str) -> dict[str, Any]:
        row = self._get_lote_row(lote_id)
        params = dict(row.get("parametros") or {})
        if row["origem"] != "sugestao_auto":
            self._validate_params(str(row["marca_id"]), {**params, "origem": row["origem"]})
        perfil = self._perfil(str(row["marca_id"]))
        if not ((perfil or {}).get("bio") or "").strip():
            raise HeadlineError(422, "Preencha a bio em Meu Perfil antes de gerar headlines")
        self._check_user_limits()
        return await self._insert_and_enqueue(str(row["marca_id"]), row["origem"], params)

    # ── batches: reads ──────────────────────────────────────────────────

    def _get_lote_row(self, lote_id: str) -> dict[str, Any]:
        rows = self.db.table(pipe.LOTES).select(LOTE_COLS).eq("id", lote_id).eq("org_id", self.org_id).execute().data
        if not rows:
            raise HeadlineError(404, "Lote não encontrado")
        return rows[0]

    def list_lotes(
        self, marca_id: str, *, origem_in: Optional[list[str]], q: Optional[str], limit: int, offset: int,
    ) -> dict[str, Any]:
        self.assert_marca(marca_id)
        origens = origem_in or list(FORM_ORIGENS)
        if any(o not in ALL_ORIGENS for o in origens):
            raise HeadlineError(422, "Origem inválida")

        def base(sel: str, **kw):
            return (
                self.db.table(pipe.LOTES).select(sel, **kw)
                .eq("org_id", self.org_id).eq("marca_id", marca_id).in_("origem", origens)
            )

        if q and q.strip():
            needle = q.strip().casefold()
            rows = list(iter_paged_rows(
                lambda s, e: base(LOTE_COLS).order("created_at", desc=True).order("id").range(s, e).execute().data,
                page_size=PAGE_SIZE, label="cs_headline_lotes busca",
            ))
            hits = [r for r in rows if needle in resumo_do_lote(r["origem"], r.get("parametros") or {}).casefold()]
            return {"items": [self.present_lote(r) for r in hits[offset: offset + limit]], "total": len(hits)}
        res = base(LOTE_COLS, count="exact").order("created_at", desc=True).order("id").range(offset, offset + limit - 1).execute()
        rows = res.data or []
        total = res.count if getattr(res, "count", None) is not None else len(rows)
        return {"items": [self.present_lote(r) for r in rows], "total": total}

    async def get_lote(self, lote_id: str) -> dict[str, Any]:
        row = self._get_lote_row(lote_id)
        hs = (
            self.db.table(pipe.HEADLINES).select(HEADLINE_COLS)
            .eq("org_id", self.org_id).eq("lote_id", lote_id).order("created_at").order("id").execute().data or []
        )
        hs.sort(key=lambda h: (h["created_at"], h.get("angulo") or 0))
        return {
            **self.present_lote(row), "parametros": row.get("parametros") or {},
            "headlines": await self.present_headlines(hs),
        }

    def excluir_lotes(self, ids: list[str]) -> dict[str, int]:
        uniq = sorted(set(ids))
        rows = self._owned(pipe.LOTES, uniq, "id,status")
        if len(rows) != len(uniq):
            raise HeadlineError(404, "Lote não encontrado")
        if any(r["status"] in ACTIVE for r in rows):
            raise HeadlineError(409, "Aguarde a geração terminar antes de excluir")
        for chunk in batched(uniq):
            self.db.table(pipe.HEADLINES).delete().eq("org_id", self.org_id).in_("lote_id", chunk).execute()
            self.db.table(pipe.LOTES).delete().eq("org_id", self.org_id).in_("id", chunk).execute()
        return {"excluidos": len(uniq)}

    def _owned(self, table: str, ids: list[str], cols: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for chunk in batched(ids):
            out.extend(self.db.table(table).select(cols).eq("org_id", self.org_id).in_("id", chunk).execute().data or [])
        return out

    # ── headlines ───────────────────────────────────────────────────────

    def _get_headline_row(self, headline_id: str) -> dict[str, Any]:
        rows = (
            self.db.table(pipe.HEADLINES).select(HEADLINE_COLS)
            .eq("id", headline_id).eq("org_id", self.org_id).execute().data
        )
        if not rows:
            raise HeadlineError(404, "Headline não encontrada")
        return rows[0]

    async def get_headline(self, headline_id: str) -> dict[str, Any]:
        return (await self.present_headlines([self._get_headline_row(headline_id)]))[0]

    async def list_headlines(
        self, marca_id: str, *, lista: str, modo: Optional[str], q: Optional[str], limit: int, offset: int,
    ) -> dict[str, Any]:
        self.assert_marca(marca_id)
        if lista not in ("favoritas", "sugeridas"):
            raise HeadlineError(422, "Lista inválida")
        if modo is not None and modo not in ("manual", "automatico"):
            raise HeadlineError(422, "Modo inválido")

        def base(**kw):
            qy = self.db.table(pipe.HEADLINES).select(HEADLINE_COLS, **kw).eq("org_id", self.org_id).eq("marca_id", marca_id)
            if q and q.strip():
                qy = qy.ilike("texto", _like(q.strip()))
            if lista == "favoritas":
                return qy.eq("favorita", True)
            return qy.eq("modo", modo) if modo else qy.in_("modo", ["manual", "automatico"])

        if lista == "favoritas":
            res = base(count="exact").order("favoritada_em", desc=True).order("id").range(offset, offset + limit - 1).execute()
            rows = res.data or []
            total = res.count if getattr(res, "count", None) is not None else len(rows)
            return {"items": await self.present_headlines(rows), "total": total}

        # sugeridas: ordered by the viral's metric, which lives on another table -> sort here (bounded:
        # at most ~10 per marca per day plus manual wizard runs)
        rows = list(iter_paged_rows(
            lambda s, e: base().order("created_at", desc=True).order("id").range(s, e).execute().data,
            page_size=PAGE_SIZE, label="cs_headlines sugeridas",
        ))
        items = await self.present_headlines(rows)
        items.sort(key=lambda h: (metrica(h["viral"]), h["created_at"]), reverse=True)
        return {"items": items[offset: offset + limit], "total": len(items)}

    async def editar(self, headline_id: str, texto: str) -> dict[str, Any]:
        row = self._get_headline_row(headline_id)
        texto = texto.strip()
        if not texto or len(texto) > 1000:
            raise HeadlineError(422, "O texto deve ter entre 1 e 1000 caracteres")
        patch = {"texto": texto, "updated_at": _iso()}
        if not row.get("texto_original"):
            patch["texto_original"] = row["texto"]
        self.db.table(pipe.HEADLINES).update(patch).eq("id", headline_id).eq("org_id", self.org_id).execute()
        return await self.get_headline(headline_id)

    async def favoritar(self, headline_id: str, favorita: bool) -> dict[str, Any]:
        self._get_headline_row(headline_id)
        self.db.table(pipe.HEADLINES).update({
            "favorita": favorita, "favoritada_em": _iso() if favorita else None, "updated_at": _iso(),
        }).eq("id", headline_id).eq("org_id", self.org_id).execute()
        return await self.get_headline(headline_id)

    async def criar(self, marca_id: str, texto: str) -> dict[str, Any]:
        self.assert_marca(marca_id)
        texto = texto.strip()
        if not texto or len(texto) > 1000:
            raise HeadlineError(422, "O texto deve ter entre 1 e 1000 caracteres")
        hid = str(uuid.uuid4())
        now = _iso()
        self.db.table(pipe.HEADLINES).insert({
            "id": hid, "org_id": self.org_id, "marca_id": marca_id, "lote_id": None,
            "texto": texto, "texto_original": texto, "itens_usados": [], "favorita": True,
            "favoritada_em": now, "created_by": self.user_id, "created_at": now,
        }).execute()
        return await self.get_headline(hid)

    def excluir_headlines(self, ids: list[str]) -> dict[str, int]:
        uniq = sorted(set(ids))
        if len(self._owned(pipe.HEADLINES, uniq, "id")) != len(uniq):
            raise HeadlineError(404, "Headline não encontrada")
        for chunk in batched(uniq):
            self.db.table(pipe.HEADLINES).delete().eq("org_id", self.org_id).in_("id", chunk).execute()
        return {"excluidos": len(uniq)}

    # ── structure count (the form's "compatible profiles") ──────────────

    def contagem_estruturas(self, marca_id: str, variaveis: list[str]) -> dict[str, Any]:
        """``{compativeis, por_perfil}``: how many classified structures carry at least one of the
        selected variables, per monitored profile, in the first non-empty pool tier."""
        self.assert_marca(marca_id)
        bad = [v for v in variaveis if v != "*" and v not in VARIABLE_SLUGS]
        if bad:
            raise HeadlineError(422, f"Variável desconhecida: {bad[0]}")
        wanted = set(VARIABLE_SLUGS) if "*" in variaveis else set(variaveis)
        wanted.discard(pipe.GPT_SLOT)
        candidatos = pipe.carregar_candidatos(self.db, self.org_id)
        perfil = self._perfil(marca_id)
        tier = pipe.pool_de_estruturas(
            candidatos, pipe.referencias_da_marca(self.db, self.org_id, marca_id),
            list((perfil or {}).get("nichos") or []),
        )
        por_perfil: dict[str, int] = {}
        total = 0
        for c in tier:
            if wanted & set(c.get("blueprint_slots") or ()):
                total += 1
                por_perfil[str(c["perfil_id"])] = por_perfil.get(str(c["perfil_id"]), 0) + 1
        perfis = sorted({str(c["perfil_id"]) for c in tier})
        return {
            "compativeis": total,
            "por_perfil": [{"perfil_id": p, "n": por_perfil.get(p, 0)} for p in perfis],
        }

    # ── daily suggestions (cron + "Gerar sugestões agora") ──────────────

    def _sugestao_de_hoje(self, marca_id: str) -> bool:
        inicio = datetime.now(BRT).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        rows = (
            self.db.table(pipe.LOTES).select("id,status")
            .eq("org_id", self.org_id).eq("marca_id", marca_id).eq("origem", "sugestao_auto")
            .gte("created_at", _iso(inicio)).execute().data or []
        )
        return any(r["status"] != "falha" for r in rows)

    def escolher_virais_para_sugestao(self, marca_id: str, nichos: list[int], n: int) -> list[str]:
        """The top ``n`` ``e_viral`` structures with a blueprint, ranked by ``score_viral``: first
        the marca's Minha Biblioteca, then the org's virals whose niches overlap the marca's. Virals
        this marca already used in the last 30 days are excluded."""
        candidatos = [c for c in pipe.carregar_candidatos(self.db, self.org_id) if c.get("e_viral")]
        cutoff = _iso(_now() - timedelta(days=SUGESTAO_JANELA_DIAS))
        usados = {
            str(r["viral_id"]) for r in self.db.table(pipe.HEADLINES).select("viral_id")
            .eq("org_id", self.org_id).eq("marca_id", marca_id).gte("created_at", cutoff).execute().data or []
            if r.get("viral_id")
        }
        livres = [c for c in candidatos if str(c["id"]) not in usados]
        refs = pipe.referencias_da_marca(self.db, self.org_id, marca_id)
        t1 = pipe.pool_da_biblioteca(livres, refs)
        nich = set(nichos or [])
        t2 = [c for c in livres if nich & set(c.get("nicho_ids") or [])]
        out: list[str] = []
        for tier in (t1, t2):
            for c in sorted(tier, key=pipe.rank_score):
                if str(c["id"]) not in out:
                    out.append(str(c["id"]))
                if len(out) >= n:
                    return out
        return out

    async def criar_sugestao(self, marca_id: str) -> dict[str, Any]:
        """One automatic-suggestion batch for the marca today (contract 3.5)."""
        self.assert_marca(marca_id)
        perfil = self._perfil(marca_id)
        if not ((perfil or {}).get("bio") or "").strip() or not (perfil or {}).get("nichos"):
            raise HeadlineError(422, "Preencha a bio e escolha ao menos um nicho em Meu Perfil")
        if self._sugestao_de_hoje(marca_id):
            raise HeadlineError(429, "As sugestões de hoje já foram geradas", retry_after=RETRY_AFTER_SECONDS)
        ids = self.escolher_virais_para_sugestao(
            marca_id, list(perfil["nichos"]), int(self.cfg.headlines_sugeridas_por_dia_marca),
        )
        if not ids:
            raise HeadlineError(409, "Ainda não há estruturas virais classificadas para sugerir")
        return await self._insert_and_enqueue(
            marca_id, "sugestao_auto",
            {"origem": "sugestao_auto", "marca_id": marca_id, "viral_ids": ids, "criatividade": "equilibrado"},
        )


__all__ = [
    "HeadlineError",
    "HeadlineService",
    "metrica",
    "resumo_do_lote",
]
