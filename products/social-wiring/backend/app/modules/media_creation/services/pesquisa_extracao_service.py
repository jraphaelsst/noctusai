"""Pesquisa Extrair — submit, caps, reconcile and the job handler.

An extraction is an LLM reading ONE of the marca's own posts (text + metrics)
and proposing research items and/or viral topics, saved as ``pending``.
Contract: projects/core-studio/specs/pesquisa-wave2-contract.md sections 2.3,
2.4 and 3. Both extractor prompts are DRAFT for owner validation.

Two halves:

* :class:`PesquisaExtracaoService` — the request side (org/user scoped):
  sources listing, limits, submit (refusals BEFORE anything is enqueued),
  list/get with reconcile, cancel.
* :func:`executar_extracao` — the queue handler. Resumable (a retried job
  skips every ``(tipo, post)`` that already has a ``post_run``); a per-post LLM
  failure is recorded and the loop continues; a database/infra exception
  PROPAGATES so the seed ``Worker`` retries the job.

Honest deviations from the contract text (also in the slice return):

* ``cs_extraction_jobs.posts`` entries carry an extra ``tipos`` list (the
  tipos still to run for that post once "already extracted" pairs are
  dropped), so the handler needs no second skip decision.
* Reconcile fails an extraction only when its queue row is ``dead_letter``;
  a queue row in ``failed`` is a retry in waiting (``JobStatus.FAILED`` →
  re-claimable), not a dead job.
* ``itens_descartados`` also counts discarded viral-topic lines.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from noctusai_lib.domain.jobs import DeadLetterError, JobRepository
from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.persistence.table_reads import PAGE_SIZE, batched
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from app.modules.media_creation.pesquisa_fontes import FONTES, InvalidCursor, PostFonte
from app.modules.media_creation.pesquisa_wave2_constants import (
    EXTRACAO_ACTIVE_STATUSES,
    FONTE_KINDS,
)
from app.modules.media_creation.prompts.assuntos_virais_extractor import (
    ASSUNTOS_VIRAIS_SYSTEM_PROMPT,
    parse_assuntos_output,
)
from app.modules.media_creation.prompts.pesquisa_extractor import (
    PESQUISA_EXTRACTOR_SYSTEM_PROMPT,
    build_post_user_message,
    parse_extractor_output,
    truncate_headline,
)
from app.modules.media_creation.schemas.pesquisa import MAX_CONTENT_CHARS
from app.modules.media_creation.services.assuntos_virais_service import AssuntosViraisService
from app.modules.media_creation.services.pesquisa_service import PesquisaError, PesquisaLlm, PesquisaService

logger = logging.getLogger(__name__)

JOB_TYPE = "pesquisa.extrair"
JOBS = "cs_extraction_jobs"
RUNS = "cs_extraction_post_runs"
QUEUE = "jobs"
WINDOW = timedelta(hours=24)
_TERMINAL = ("completed", "completed_with_errors", "failed", "cancelled")
_COUNTERS = (
    "tarefas_processadas", "tarefas_com_erro", "itens_salvos", "itens_ignorados",
    "itens_descartados", "assuntos_salvos", "assuntos_ignorados", "ja_extraidos_pulados",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def present_job(row: dict[str, Any]) -> dict[str, Any]:
    """``ExtractionJob`` (contract 3.1). Progress is computed server-side."""
    total = int(row.get("total_tarefas") or 0)
    done = int(row.get("tarefas_processadas") or 0)
    out = {
        k: row.get(k)
        for k in (
            "id", "marca_id", "tipos", "status", "step", "total_tarefas",
            "erro", "created_at", "started_at", "finished_at",
        )
    }
    for k in _COUNTERS:
        out[k] = int(row.get(k) or 0)
    out["progress"] = round(100 * done / max(total, 1))
    return out


def _fonte(db, kind: str, texto_max_chars: int):
    return FONTES[kind](db, texto_max_chars=texto_max_chars)


def _source_ref(post: PostFonte, excerpt: Optional[str], extracao_id: str) -> dict[str, Any]:
    return {
        "kind": post.kind, "account_id": post.account_id, "id": post.id, "url": post.url,
        "thumbnail_url": post.thumbnail_url, "published_at": post.published_at,
        "plays": post.plays, "likes": post.likes, "comments": post.comments,
        "excerpt": excerpt, "extracao_id": extracao_id,
    }


# ── request side ────────────────────────────────────────────────────────

class PesquisaExtracaoService:
    def __init__(
        self, db, org_id: str, user_id: Optional[str], *,
        cfg: Any, jobs: Optional[JobRepository] = None,
    ):
        self.db = db
        self.org_id = org_id
        self.user_id = user_id
        self.cfg = cfg
        self.jobs = jobs

    # guards / helpers

    def assert_marca(self, marca_id: str) -> None:
        PesquisaService(self.db, self.org_id).assert_marca(marca_id)

    def _source(self, kind: str):
        return _fonte(self.db, kind, int(self.cfg.pesquisa_extracao_texto_max_chars))

    def _job_table(self):
        return self.db.table(JOBS)

    def _active_job(self) -> Optional[dict[str, Any]]:
        rows = (
            self._job_table().select("id,status")
            .eq("org_id", self.org_id).eq("created_by", self.user_id)
            .in_("status", list(EXTRACAO_ACTIVE_STATUSES)).limit(1).execute().data
        )
        return rows[0] if rows else None

    def _usage(self) -> tuple[int, int]:
        """``(jobs of this user, tarefas of this org)`` in the rolling window."""
        cutoff = _iso(_now() - WINDOW)

        def page(start: int, end: int):
            return (
                self._job_table().select("id,created_by,total_tarefas")
                .eq("org_id", self.org_id).gte("created_at", cutoff)
                .order("id").range(start, end).execute().data
            )

        user_jobs = tarefas = 0
        for r in iter_paged_rows(page, page_size=PAGE_SIZE, label="cs_extraction_jobs usage"):
            tarefas += int(r.get("total_tarefas") or 0)
            if r.get("created_by") == self.user_id:
                user_jobs += 1
        return user_jobs, tarefas

    def _done_runs(
        self, marca_id: str, kind: str, source_ids: list[str],
    ) -> dict[tuple[Optional[str], str], dict[str, str]]:
        """``(account_id, source_id) -> {tipo: ISO of the last 'done' run}``."""
        out: dict[tuple[Optional[str], str], dict[str, str]] = {}
        for chunk in batched(sorted(set(source_ids))):
            def page(start: int, end: int, _c=chunk):
                return (
                    self.db.table(RUNS).select("tipo,account_id,source_id,created_at")
                    .eq("org_id", self.org_id).eq("marca_id", marca_id)
                    .eq("source_kind", kind).eq("status", "done").in_("source_id", _c)
                    .order("id").range(start, end).execute().data
                )
            for r in iter_paged_rows(page, page_size=PAGE_SIZE, label="cs_extraction_post_runs done"):
                slot = out.setdefault((r.get("account_id"), r["source_id"]), {})
                if r["tipo"] not in slot or str(r["created_at"]) > slot[r["tipo"]]:
                    slot[r["tipo"]] = str(r["created_at"])
        return out

    # reads: sources

    def fontes(self, marca_id: str) -> list[dict[str, Any]]:
        self.assert_marca(marca_id)
        out: list[dict[str, Any]] = []
        for kind in FONTE_KINDS:
            for conta in self._source(kind).contas(self.org_id, marca_id):
                out.append({"kind": kind, **conta})
        return out

    def posts(
        self, marca_id: str, kind: str, *, account_id: Optional[str],
        cursor: Optional[str], limit: int, busca: Optional[str],
    ) -> dict[str, Any]:
        self.assert_marca(marca_id)
        if kind != "mc_post" and not account_id:
            raise PesquisaError(422, "account_id é obrigatório para esta fonte")
        try:
            posts, nxt = self._source(kind).listar(
                self.org_id, marca_id, account_id=account_id, cursor=cursor,
                limit=limit, busca=busca,
            )
        except InvalidCursor as exc:
            raise PesquisaError(422, "Cursor inválido") from exc
        done = self._done_runs(marca_id, kind, [p.id for p in posts])
        items = []
        for p in posts:
            runs = done.get((p.account_id, p.id), {})
            items.append({
                **asdict(p),
                "extraido": {"pesquisa": runs.get("pesquisa"), "assuntos_virais": runs.get("assuntos_virais")},
            })
        return {"posts": items, "next_cursor": nxt}

    # reads: jobs

    def limits(self, marca_id: str) -> dict[str, Any]:
        self.assert_marca(marca_id)
        user_jobs, tarefas = self._usage()
        active = self._active_job()
        return {
            "worker_ativo": bool(self.cfg.pesquisa_extracao_worker_enabled),
            "max_posts_por_job": int(self.cfg.pesquisa_extracao_max_posts_por_job),
            "extracoes_restantes_hoje": max(0, int(self.cfg.pesquisa_extracao_jobs_por_dia_usuario) - user_jobs),
            "tarefas_restantes_hoje_org": max(0, int(self.cfg.pesquisa_extracao_posts_por_dia_org) - tarefas),
            "extracao_ativa_id": active["id"] if active else None,
        }

    def _reconcile(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """An active extraction whose queue row is dead-lettered can never
        finish: fail it (no stuck jobs). ``failed`` queue rows are retries in
        waiting, so they are left alone."""
        out = []
        for row in rows:
            qid = row.get("queue_job_id")
            if row["status"] in EXTRACAO_ACTIVE_STATUSES and qid:
                q = self.db.table(QUEUE).select("id,status").eq("id", qid).execute().data
                if q and q[0]["status"] == "dead_letter":
                    patch = {
                        "status": "failed", "erro": "Falha interna na extração",
                        "finished_at": _iso(_now()), "step": None,
                    }
                    upd = (
                        self._job_table().update(patch)
                        .eq("id", row["id"]).eq("org_id", self.org_id).execute().data
                    )
                    row = upd[0] if upd else {**row, **patch}
            out.append(row)
        return out

    def list_jobs(self, marca_id: str, limit: int) -> list[dict[str, Any]]:
        self.assert_marca(marca_id)
        rows = (
            self._job_table().select("*").eq("org_id", self.org_id).eq("marca_id", marca_id)
            .order("created_at", desc=True).order("id").limit(limit).execute().data or []
        )
        return [present_job(r) for r in self._reconcile(rows)]

    def _get_row(self, extracao_id: str) -> dict[str, Any]:
        rows = (
            self._job_table().select("*").eq("id", extracao_id).eq("org_id", self.org_id)
            .execute().data
        )
        if not rows:
            raise PesquisaError(404, "Extração não encontrada")
        return rows[0]

    def get_job(self, extracao_id: str) -> dict[str, Any]:
        return present_job(self._reconcile([self._get_row(extracao_id)])[0])

    def cancel(self, extracao_id: str) -> dict[str, Any]:
        row = self._reconcile([self._get_row(extracao_id)])[0]
        if row["status"] not in EXTRACAO_ACTIVE_STATUSES:
            raise PesquisaError(409, "A extração já foi finalizada")
        patch: dict[str, Any] = {"cancel_requested": True}
        if row["status"] == "queued":  # nothing running: settle now, free the user's slot
            patch.update(status="cancelled", finished_at=_iso(_now()), step=None)
        upd = (
            self._job_table().update(patch).eq("id", extracao_id).eq("org_id", self.org_id)
            .execute().data
        )
        return present_job(upd[0] if upd else {**row, **patch})

    # writes

    async def submit(
        self, marca_id: str, tipos: list[str], refs: list[dict[str, Any]], *, reextrair: bool,
    ) -> dict[str, Any]:
        cfg = self.cfg
        if not cfg.pesquisa_extracao_worker_enabled or self.jobs is None:
            raise PesquisaError(503, "Extração indisponível no momento")
        self.assert_marca(marca_id)
        max_posts = int(cfg.pesquisa_extracao_max_posts_por_job)
        unique: dict[tuple[str, Optional[str], str], dict[str, Any]] = {}
        for r in refs:
            unique.setdefault((r["kind"], r.get("account_id"), r["id"]), r)
        if len(unique) > max_posts:
            raise PesquisaError(422, f"Selecione no máximo {max_posts} posts por extração")
        if self._active_job():
            raise PesquisaError(409, "Já existe uma extração em andamento")
        user_jobs, org_tarefas = self._usage()
        if user_jobs >= int(cfg.pesquisa_extracao_jobs_por_dia_usuario):
            raise PesquisaError(429, "Limite diário de extrações atingido")

        # every post must belong to this marca
        by_kind: dict[str, list[tuple[Optional[str], str]]] = {}
        for kind, account_id, pid in unique:
            by_kind.setdefault(kind, []).append((account_id, pid))
        for kind, kind_refs in by_kind.items():
            got = self._source(kind).obter(self.org_id, marca_id, kind_refs)
            if any(ref not in got for ref in kind_refs):
                raise PesquisaError(422, "Post não encontrado para esta marca")

        # drop the (post, tipo) pairs already extracted, unless re-extracting
        selection: list[dict[str, Any]] = []
        pulados = 0
        done_by_kind = {
            kind: self._done_runs(marca_id, kind, [pid for _, pid in kind_refs])
            for kind, kind_refs in by_kind.items()
        }
        for (kind, account_id, pid) in unique:
            already = done_by_kind[kind].get((account_id, pid), {})
            todo = [t for t in tipos if reextrair or t not in already]
            pulados += len(tipos) - len(todo)
            if todo:
                selection.append({"kind": kind, "account_id": account_id, "id": pid, "tipos": todo})
        total = sum(len(s["tipos"]) for s in selection)
        if not selection:
            raise PesquisaError(422, "Todos os posts selecionados já foram extraídos")
        if org_tarefas + total > int(cfg.pesquisa_extracao_posts_por_dia_org):
            raise PesquisaError(429, "Limite diário de extrações atingido")

        extracao_id = str(uuid.uuid4())
        try:
            inserted = self._job_table().insert({
                "id": extracao_id, "org_id": self.org_id, "marca_id": marca_id,
                "created_by": self.user_id, "tipos": list(tipos), "status": "queued",
                "posts": selection, "total_tarefas": total, "ja_extraidos_pulados": pulados,
                "created_at": _iso(_now()),
            }).execute().data
        except Exception as exc:  # noqa: BLE001 - unique index = a concurrent active job
            if is_unique_violation(exc):
                raise PesquisaError(409, "Já existe uma extração em andamento") from exc
            raise
        row = inserted[0] if inserted else {
            "id": extracao_id, "marca_id": marca_id, "tipos": list(tipos), "status": "queued",
            "total_tarefas": total, "ja_extraidos_pulados": pulados,
        }
        try:
            queued = await self.jobs.enqueue(
                type=JOB_TYPE, payload={"extracao_id": extracao_id},
                dedupe_key=f"{JOB_TYPE}:{extracao_id}", max_retries=2,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as 503, row settled as failed
            logger.error("pesquisa extracao: enqueue failed for %s: %s", extracao_id, exc)
            self._job_table().update({
                "status": "failed", "erro": "Falha ao iniciar a extração", "finished_at": _iso(_now()),
            }).eq("id", extracao_id).eq("org_id", self.org_id).execute()
            raise PesquisaError(503, "Falha ao iniciar a extração") from exc
        upd = (
            self._job_table().update({"queue_job_id": queued.id})
            .eq("id", extracao_id).eq("org_id", self.org_id).execute().data
        )
        return present_job(upd[0] if upd else {**row, "queue_job_id": queued.id})


# ── queue handler ───────────────────────────────────────────────────────

def _fetch_job(db, extracao_id: str) -> Optional[dict[str, Any]]:
    rows = db.table(JOBS).select("*").eq("id", extracao_id).execute().data
    return rows[0] if rows else None


def _patch(db, extracao_id: str, patch: dict[str, Any]) -> None:
    db.table(JOBS).update(patch).eq("id", extracao_id).execute()


def _topic_excerpt(post: PostFonte, topic: str) -> Optional[str]:
    if topic.casefold() in post.texto.casefold():
        return truncate_headline(post.texto, topic)
    return None


async def executar_extracao(
    db, llm: PesquisaLlm, extracao_id: str, *, texto_max_chars: int,
    fontes: Optional[dict[str, Callable[..., Any]]] = None,
) -> None:
    """Run (or resume) one extraction. See the module docstring."""
    registry = fontes or FONTES
    row = _fetch_job(db, extracao_id)
    if row is None:
        raise DeadLetterError(f"Extração {extracao_id} não existe mais")
    if row["status"] in _TERMINAL:
        return  # settled already (cancelled while queued, reconciled as failed, finished)
    org_id, marca_id, user_id = row["org_id"], row["marca_id"], row["created_by"]
    if row.get("cancel_requested"):
        _patch(db, extracao_id, {"status": "cancelled", "finished_at": _iso(_now()), "step": None})
        return
    _patch(db, extracao_id, {
        "status": "running", "started_at": row.get("started_at") or _iso(_now()),
    })

    selection: list[dict[str, Any]] = row.get("posts") or []

    def runs_page(start: int, end: int):
        return (
            db.table(RUNS).select("tipo,source_kind,account_id,source_id")
            .eq("extracao_id", extracao_id).order("id").range(start, end).execute().data
        )

    done_keys = {
        (r["tipo"], r["source_kind"], r.get("account_id"), r["source_id"])
        for r in iter_paged_rows(runs_page, page_size=PAGE_SIZE, label="cs_extraction_post_runs resume")
    }
    posts: dict[tuple[str, Optional[str], str], PostFonte] = {}
    by_kind: dict[str, list[tuple[Optional[str], str]]] = {}
    for s in selection:
        by_kind.setdefault(s["kind"], []).append((s.get("account_id"), s["id"]))
    for kind, refs in by_kind.items():
        got = registry[kind](db, texto_max_chars=texto_max_chars).obter(org_id, marca_id, refs)
        for (account_id, pid), post in got.items():
            posts[(kind, account_id, pid)] = post

    counters = {k: int(row.get(k) or 0) for k in _COUNTERS}
    pesquisa = PesquisaService(db, org_id, user_id)
    assuntos = AssuntosViraisService(db, org_id, user_id)
    cancelled = False

    for idx, sel in enumerate(selection, start=1):
        post = posts.get((sel["kind"], sel.get("account_id"), sel["id"]))
        for tipo in sel["tipos"]:
            run_key = (tipo, sel["kind"], sel.get("account_id"), sel["id"])
            if run_key in done_keys:
                continue
            fresh = _fetch_job(db, extracao_id)
            if fresh is None:
                raise DeadLetterError(f"Extração {extracao_id} foi removida durante a execução")
            if fresh.get("cancel_requested"):
                cancelled = True
                break
            _patch(db, extracao_id, {"step": f"Analisando post {idx} de {len(selection)}"})

            status, motivo = "done", None
            run = {"itens_salvos": 0, "assuntos_salvos": 0}
            if post is None or not post.analisavel:
                status, motivo = "skipped", "sem_texto"
            else:
                system = PESQUISA_EXTRACTOR_SYSTEM_PROMPT if tipo == "pesquisa" else ASSUNTOS_VIRAIS_SYSTEM_PROMPT
                try:
                    reply = await llm(system, build_post_user_message(post), org_id)
                except Exception as exc:  # noqa: BLE001 - one post's LLM failure never stops the job
                    logger.warning(
                        "pesquisa extracao %s: LLM falhou em %s/%s: %s",
                        extracao_id, sel["kind"], sel["id"], exc,
                    )
                    status, motivo = "failed", "llm_erro"
                    counters["tarefas_com_erro"] += 1
                else:
                    if tipo == "pesquisa":
                        pairs, excerpts, desc = parse_extractor_output(reply, post.texto)
                        kept = [(s_, c) for s_, c in pairs if len(c) <= MAX_CONTENT_CHARS]
                        desc += len(pairs) - len(kept)
                        prov = {
                            p: {"source_ref": _source_ref(post, excerpts.get(p), extracao_id), "plays": post.plays}
                            for p in kept
                        }
                        res = pesquisa.save_extracted(marca_id, kept, prov) if kept else {"saved": 0, "skipped": 0}
                        run["itens_salvos"] = res["saved"]
                        counters["itens_salvos"] += res["saved"]
                        counters["itens_ignorados"] += res["skipped"]
                        counters["itens_descartados"] += desc
                    else:
                        topics, desc = parse_assuntos_output(reply)
                        res = (
                            assuntos.salvar_extraidos(
                                marca_id, extracao_id,
                                [(t, post, _topic_excerpt(post, t)) for t in topics],
                            ) if topics else {"saved": 0, "skipped": 0}
                        )
                        run["assuntos_salvos"] = res["saved"]
                        counters["assuntos_salvos"] += res["saved"]
                        counters["assuntos_ignorados"] += res["skipped"]
                        counters["itens_descartados"] += desc

            db.table(RUNS).insert({
                "id": str(uuid.uuid4()), "org_id": org_id, "marca_id": marca_id,
                "extracao_id": extracao_id, "tipo": tipo, "source_kind": sel["kind"],
                "account_id": sel.get("account_id"), "source_id": sel["id"],
                "status": status, "motivo": motivo, "created_at": _iso(_now()), **run,
            }).execute()
            counters["tarefas_processadas"] += 1
            _patch(db, extracao_id, dict(counters))
        if cancelled:
            break

    finished = {"finished_at": _iso(_now()), "step": None, **counters}
    if cancelled:
        _patch(db, extracao_id, {**finished, "status": "cancelled"})
        return
    n_done = len(
        db.table(RUNS).select("id").eq("extracao_id", extracao_id).eq("status", "done").execute().data or []
    )
    if counters["tarefas_com_erro"] == 0:
        _patch(db, extracao_id, {**finished, "status": "completed"})
    elif n_done > 0:
        _patch(db, extracao_id, {**finished, "status": "completed_with_errors"})
    else:
        _patch(db, extracao_id, {**finished, "status": "failed", "erro": "Falha ao analisar os posts com IA"})


__all__ = [
    "JOB_TYPE", "PesquisaExtracaoService", "executar_extracao", "present_job",
]
