"""Segundo Cérebro — brains core (list / CRUD / content / answers / review /
synthesis / profile bio) over the PostgREST client.

Pure data service: the LLM is an injected callable (``cerebro_ai.CerebroLlm``)
and storage an injected backend, so every flow is testable through its real
seam. Every read/write is org-scoped AND marca-scoped; a foreign
marca/brain/question is a 404, a forbidden operation on an existing brain a 409
(``cerebro-contract.md`` §4).

Templates and questions are read from ``cerebro_templates`` (the same module
that generates the migration seed — a test pins the two together), not from the
DB, so the questionnaire can never disagree with the code that consumes it.

Status machines (§3): synthesis ``idle -> processing -> idle | error`` and
answer review ``none -> pending -> done | error`` move through background tasks
(``run_synthesis`` / ``run_review``); anything stranded by a restart is swept to
``error`` by :func:`sweep_stale` (scheduler + throttled read-time refresh).
"""
from __future__ import annotations

import hashlib
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.persistence.table_reads import PAGE_SIZE, batched
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from app.modules.media_creation.cerebro_templates import (
    TEMPLATES,
    TEMPLATES_BY_SLUG,
    BrainTemplateSpec,
    question_group,
    question_id,
)
from app.modules.media_creation.deps import CEREBRO_BUCKET
from app.modules.media_creation.prompts.cerebro_review import ReviewItem
from app.modules.media_creation.schemas.cerebro import MAX_CONTENT_CHARS
from app.modules.transcricoes.service import transcricoes_por_id
from app.modules.media_creation.services.cerebro_ai import (
    CerebroLlm,
    review_answers,
    synthesize_brain,
)

logger = logging.getLogger(__name__)

BRAINS = "cs_brains"
ANSWERS = "cs_brain_answers"
IMPORTS = "cs_brain_imports"
APPEND_RPC = "cs_brain_append"

BRAIN_COLS = (
    "id,marca_id,kind,template_slug,name,content,content_version,synthesis_status,"
    "synthesis_error,synthesis_started_at,synthesized_at,created_at,updated_at"
)
ANSWER_COLS = (
    "id,brain_id,question_id,text,transcricao_id,review_status,review_verdict,review_reason,"
    "review_improved,review_decision,review_error,reviewed_text_sha,review_requested_at,updated_at"
)
IMPORT_COLS = (
    "id,brain_id,kind,filename,source_url,status,chars_appended,error_message,created_at"
)

#: Stale thresholds (cerebro-contract.md §3).
STALE_SYNTHESIS_MINUTES = 10
STALE_REVIEW_MINUTES = 10
STALE_IMPORT_MINUTES = 15

MSG_SYNTHESIS_TIMEOUT = "Tempo esgotado ao gerar o cérebro"
MSG_SYNTHESIS_FAILED = "Ocorreu um erro ao gerar o cérebro. Tente novamente."
MSG_SYNTHESIS_STALE_VERSION = "O conteúdo mudou durante a geração; gere novamente."
MSG_OVER_LIMIT = "O cérebro excederia o limite de 200.000 caracteres."
MSG_REVIEW_FAILED = "Falha ao revisar com IA"
MSG_REVIEW_MISSING = "A IA não avaliou esta resposta."
MSG_REVIEW_TIMEOUT = "Tempo esgotado ao revisar com IA"
MSG_IMPORT_TIMEOUT = "Tempo esgotado ao importar o arquivo"

#: Throttle of the read-time stale refresh, per org (seconds).
_REFRESH_THROTTLE_SECONDS = 60.0
_last_refresh: dict[str, float] = {}


class CerebroError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat()


def text_sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def block_header(kind: str, label: str, when: Optional[datetime] = None) -> str:
    """Single source of the append headers (contract §4): ``### Arquivo:`` /
    ``### YouTube:`` / ``### Extração:`` ``«label» (dd/mm/aaaa)``."""
    return f"### {kind}: «{label}» ({(when or _now()).strftime('%d/%m/%Y')})"


def _is_over_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "check_violation" in msg or "23514" in msg or "cs_brains_content_check" in msg


# ── stale sweeps (scheduler + read-time refresh) ────────────────────────────


def sweep_stale(db, *, org_id: Optional[str] = None, now: Optional[datetime] = None) -> dict[str, int]:
    """Move stranded work to ``error``: synthesis ``processing`` > 10 min,
    answer review ``pending`` > 10 min, file import ``processing`` > 15 min.
    ``org_id=None`` sweeps every org (the scheduler); otherwise only that org
    (the read-time refresh). Returns the count moved per kind."""
    now = now or _now()

    def cutoff(minutes: int) -> str:
        return (now - timedelta(minutes=minutes)).isoformat()

    def scoped(q):
        return q.eq("org_id", org_id) if org_id else q

    brains = scoped(
        db.table(BRAINS).update({
            "synthesis_status": "error", "synthesis_error": MSG_SYNTHESIS_TIMEOUT,
        }).eq("synthesis_status", "processing").lt("synthesis_started_at", cutoff(STALE_SYNTHESIS_MINUTES))
    ).execute().data or []
    answers = scoped(
        db.table(ANSWERS).update({
            "review_status": "error", "review_error": MSG_REVIEW_TIMEOUT,
        }).eq("review_status", "pending").lt("review_requested_at", cutoff(STALE_REVIEW_MINUTES))
    ).execute().data or []
    imports = scoped(
        db.table(IMPORTS).update({
            "status": "error", "error_message": MSG_IMPORT_TIMEOUT,
        }).eq("status", "processing").lt("created_at", cutoff(STALE_IMPORT_MINUTES))
    ).execute().data or []
    return {"brains": len(brains), "answers": len(answers), "imports": len(imports)}


# ── serialisation of the contract types (§4) ────────────────────────────────


def template_dict(spec: BrainTemplateSpec) -> dict[str, Any]:
    return {
        "slug": spec.slug,
        "name": spec.name,
        "description": spec.description,
        "sort_order": spec.sort_order,
        "questions": [
            {
                "id": question_id(spec.slug, q.position),
                "position": q.position,
                "group": question_group(q.position),
                "text": q.text,
                "hint": q.hint,
                "optional": q.optional,
            }
            for q in spec.questions
        ],
    }


def answer_dict(
    qid: str, row: Optional[dict[str, Any]], transcricoes: Optional[dict[str, dict[str, Any]]] = None
) -> dict[str, Any]:
    """``transcricoes`` = ``{id: public job shape}`` (shared transcription layer);
    the answer's job is looked up by its ``transcricao_id``."""
    row = row or {}
    return {
        "question_id": qid,
        "text": row.get("text") or "",
        "updated_at": row.get("updated_at"),
        "transcricao": (transcricoes or {}).get(str(row.get("transcricao_id") or "")),
        "review": {
            "status": row.get("review_status") or "none",
            "verdict": row.get("review_verdict"),
            "reason": row.get("review_reason"),
            "improved": row.get("review_improved"),
            "decision": row.get("review_decision"),
            "error": row.get("review_error"),
        },
    }


def import_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "kind": row.get("kind"),
        "filename": row.get("filename"),
        "source_url": row.get("source_url"),
        "status": row.get("status"),
        "chars_appended": row.get("chars_appended"),
        "error_message": row.get("error_message"),
        "created_at": row.get("created_at"),
    }


class CerebroService:
    def __init__(
        self, db, org_id: str, user_id: Optional[str] = None,
        storage: Optional[StorageBackend] = None,
    ):
        self.db = db
        self.org_id = org_id
        self.user_id = user_id
        self.storage = storage

    # ── guards ──────────────────────────────────────────────────────────

    def assert_marca(self, marca_id: str) -> None:
        rows = (
            self.db.table("marcas").select("id")
            .eq("id", marca_id).eq("org_id", self.org_id).execute().data
        )
        if not rows:
            raise CerebroError(404, "Marca não encontrada")

    def _brains(self):
        return self.db.table(BRAINS)

    def get_brain_row(self, brain_id: str) -> dict[str, Any]:
        rows = (
            self._brains().select(BRAIN_COLS)
            .eq("id", brain_id).eq("org_id", self.org_id).execute().data
        )
        if not rows:
            raise CerebroError(404, "Cérebro não encontrado")
        return rows[0]

    def _spec(self, row: dict[str, Any]) -> Optional[BrainTemplateSpec]:
        slug = row.get("template_slug")
        return TEMPLATES_BY_SLUG.get(slug) if slug else None

    def _refresh_stale(self) -> None:
        """Locally the seed scheduler never fires, so reads also settle stranded
        state — on the caller's own org, throttled, never fatal."""
        now = time.monotonic()
        if now - _last_refresh.get(self.org_id, 0.0) < _REFRESH_THROTTLE_SECONDS:
            return
        _last_refresh[self.org_id] = now
        try:
            sweep_stale(self.db, org_id=self.org_id)
        except Exception as exc:  # noqa: BLE001 - a read must not fail on housekeeping
            logger.warning("cerebro: read-time stale refresh failed: %s", exc)

    # ── bulk reads for summaries ────────────────────────────────────────

    def _answers_of(self, brain_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {b: [] for b in brain_ids}
        for chunk in batched(sorted(brain_ids)):
            def page(start: int, end: int, _chunk=chunk):
                return (
                    self.db.table(ANSWERS).select(ANSWER_COLS)
                    .eq("org_id", self.org_id).in_("brain_id", _chunk)
                    .order("id").range(start, end).execute().data
                )
            for row in iter_paged_rows(page, page_size=PAGE_SIZE, label="cs_brain_answers"):
                out.setdefault(row["brain_id"], []).append(row)
        return out

    def _processing_import_brains(self, brain_ids: list[str]) -> set[str]:
        found: set[str] = set()
        for chunk in batched(sorted(brain_ids)):
            rows = (
                self.db.table(IMPORTS).select("brain_id")
                .eq("org_id", self.org_id).eq("status", "processing")
                .in_("brain_id", chunk).execute().data
            ) or []
            found.update(r["brain_id"] for r in rows)
        return found

    def _summaries(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ids = [r["id"] for r in rows]
        answers = self._answers_of(ids) if ids else {}
        busy = self._processing_import_brains(ids) if ids else set()
        out = []
        for r in rows:
            spec = self._spec(r)
            content = r.get("content") or ""
            processing = r.get("synthesis_status") == "processing" or r["id"] in busy
            status = "processando" if processing else ("pronto" if content.strip() else "vazio")
            out.append({
                "id": r["id"],
                "marca_id": r["marca_id"],
                "kind": r["kind"],
                "template_slug": r.get("template_slug"),
                "name": r["name"],
                "status": status,
                "content_chars": len(content),
                "answered": (
                    sum(1 for a in answers.get(r["id"], []) if (a.get("text") or "").strip())
                    if spec else None
                ),
                "total_questions": len(spec.questions) if spec else None,
                "synthesis_status": r.get("synthesis_status") or "idle",
                "updated_at": r.get("updated_at") or r.get("created_at"),
            })
        return out

    def _summary(self, row: dict[str, Any]) -> dict[str, Any]:
        return self._summaries([row])[0]

    # ── templates + brains (endpoints 1-6) ──────────────────────────────

    def list_templates(self) -> list[dict[str, Any]]:
        return [template_dict(t) for t in sorted(TEMPLATES, key=lambda t: t.sort_order)]

    def ensure_sistema_brains(self, marca_id: str) -> list[dict[str, Any]]:
        """Create the 4 Sistema brains of a marca, idempotently (lazy). Returns
        every brain row of the marca."""
        rows = self._marca_brain_rows(marca_id)
        have = {r["template_slug"] for r in rows if r["kind"] == "sistema"}
        missing = [t for t in TEMPLATES if t.slug not in have]
        for spec in missing:
            try:
                self._brains().insert({
                    "id": str(uuid.uuid4()), "org_id": self.org_id, "marca_id": marca_id,
                    "kind": "sistema", "template_slug": spec.slug, "name": spec.name,
                    "content": "", "content_version": 0, "synthesis_status": "idle",
                    "created_by": self.user_id,
                }).execute()
            except Exception as exc:  # noqa: BLE001 - lost a creation race? re-read decides
                if not is_unique_violation(exc):
                    raise
                logger.info("cerebro: sistema brain %s already created concurrently", spec.slug)
        if missing:
            rows = self._marca_brain_rows(marca_id)
        return rows

    def _marca_brain_rows(self, marca_id: str) -> list[dict[str, Any]]:
        def page(start: int, end: int):
            return (
                self._brains().select(BRAIN_COLS)
                .eq("org_id", self.org_id).eq("marca_id", marca_id)
                .order("id").range(start, end).execute().data
            )
        return list(iter_paged_rows(page, page_size=PAGE_SIZE, label="cs_brains"))

    def list_brains(self, marca_id: str) -> list[dict[str, Any]]:
        self.assert_marca(marca_id)
        self._refresh_stale()
        rows = self.ensure_sistema_brains(marca_id)

        def sort_key(r: dict[str, Any]):
            spec = self._spec(r)
            return (0, spec.sort_order, "") if spec else (1, 0, str(r.get("created_at") or ""))

        return self._summaries(sorted(rows, key=sort_key))

    def create_brain(self, marca_id: str, name: str) -> dict[str, Any]:
        self.assert_marca(marca_id)
        rows = self.ensure_sistema_brains(marca_id)
        if any((r["name"] or "").lower() == name.lower() for r in rows):
            raise CerebroError(409, "Já existe um cérebro com esse nome")
        try:
            res = self._brains().insert({
                "id": str(uuid.uuid4()), "org_id": self.org_id, "marca_id": marca_id,
                "kind": "custom", "template_slug": None, "name": name,
                "content": "", "content_version": 0, "synthesis_status": "idle",
                "created_by": self.user_id,
            }).execute().data
        except Exception as exc:  # noqa: BLE001 - unique backstop under a race
            if is_unique_violation(exc):
                raise CerebroError(409, "Já existe um cérebro com esse nome") from exc
            raise
        return self._summary(res[0])

    def get_brain(self, brain_id: str) -> dict[str, Any]:
        self._refresh_stale()
        row = self.get_brain_row(brain_id)
        spec = self._spec(row)
        stored = {a["question_id"]: a for a in self._answers_of([row["id"]]).get(row["id"], [])}
        jobs = transcricoes_por_id(
            self.db, self.org_id, [a.get("transcricao_id") for a in stored.values() if a.get("transcricao_id")]
        )
        answers = (
            [answer_dict(question_id(spec.slug, q.position), stored.get(question_id(spec.slug, q.position)), jobs)
             for q in spec.questions]
            if spec else []
        )
        return {
            **self._summary(row),
            "content": row.get("content") or "",
            "content_version": row.get("content_version") or 0,
            "synthesis_error": row.get("synthesis_error"),
            "synthesized_at": row.get("synthesized_at"),
            "template": template_dict(spec) if spec else None,
            "answers": answers,
            "imports": self.list_imports(row["id"], limit=20),
        }

    def rename_brain(self, brain_id: str, name: str) -> dict[str, Any]:
        row = self.get_brain_row(brain_id)
        if row["kind"] == "sistema":
            raise CerebroError(409, "Cérebros do sistema não podem ser renomeados")
        siblings = self._marca_brain_rows(row["marca_id"])
        if any(r["id"] != row["id"] and (r["name"] or "").lower() == name.lower() for r in siblings):
            raise CerebroError(409, "Já existe um cérebro com esse nome")
        try:
            res = (
                self._brains().update({"name": name})
                .eq("id", brain_id).eq("org_id", self.org_id).execute().data
            )
        except Exception as exc:  # noqa: BLE001 - unique backstop under a race
            if is_unique_violation(exc):
                raise CerebroError(409, "Já existe um cérebro com esse nome") from exc
            raise
        return self._summary(res[0] if res else {**row, "name": name})

    async def delete_brain(self, brain_id: str) -> None:
        row = self.get_brain_row(brain_id)
        if row["kind"] == "sistema":
            raise CerebroError(409, "Cérebros do sistema não podem ser excluídos")
        files = (
            self.db.table(IMPORTS).select("storage_path")
            .eq("brain_id", brain_id).eq("org_id", self.org_id).execute().data
        ) or []
        failed = 0
        for f in files:
            key = f.get("storage_path")
            if not key:
                continue
            try:
                if self.storage is None:
                    raise RuntimeError("storage backend not configured")
                await self.storage.delete(bucket=CEREBRO_BUCKET, key=key)
            except Exception as exc:  # noqa: BLE001 - surfaced below; the row is kept so it can be retried
                failed += 1
                logger.error("cerebro: failed to delete %s for brain %s: %s", key, brain_id, exc)
        if failed:
            raise CerebroError(
                502, "Não foi possível remover os arquivos do cérebro. Tente novamente."
            )
        self._brains().delete().eq("id", brain_id).eq("org_id", self.org_id).execute()

    # ── content (endpoint 7) + the atomic append write path ─────────────

    def update_content(self, brain_id: str, content: str, expected_version: int) -> dict[str, Any]:
        row = self.get_brain_row(brain_id)
        self._assert_not_synthesizing(row)
        if (row.get("content_version") or 0) != expected_version:
            raise CerebroError(409, "O conteúdo do cérebro mudou enquanto você editava.")
        res = (
            self._brains().update({"content": content, "content_version": expected_version + 1})
            .eq("id", brain_id).eq("org_id", self.org_id)
            .eq("content_version", expected_version).neq("synthesis_status", "processing")
            .execute().data
        )
        if not res:  # lost a race between the read and the write: re-read to say why
            fresh = self.get_brain_row(brain_id)
            self._assert_not_synthesizing(fresh)
            raise CerebroError(409, "O conteúdo do cérebro mudou enquanto você editava.")
        return self._summary(res[0])

    @staticmethod
    def _assert_not_synthesizing(row: dict[str, Any]) -> None:
        if row.get("synthesis_status") == "processing":
            raise CerebroError(409, "Aguarde a geração do cérebro terminar.")

    def append_block(self, brain_id: str, block: str) -> int:
        """The only write path for imports/extractions: ``cs_brain_append``
        (one statement, bumps ``content_version``). Over the 200 000-char limit
        the DB raises; that surfaces as ``CerebroError(422, MSG_OVER_LIMIT)`` —
        never truncated."""
        try:
            data = self.db.rpc(
                APPEND_RPC, {"p_brain": brain_id, "p_org": self.org_id, "p_block": block}
            ).execute().data
        except Exception as exc:  # noqa: BLE001 - classified below, otherwise re-raised
            if _is_over_limit(exc):
                raise CerebroError(422, MSG_OVER_LIMIT) from exc
            raise
        if isinstance(data, list):
            data = data[0] if data else None
        if data is None:
            raise RuntimeError("cs_brain_append returned no version")
        return int(data)

    # ── answers (endpoints 8, 9) ────────────────────────────────────────

    def _require_questionnaire(self, brain_id: str) -> tuple[dict[str, Any], BrainTemplateSpec]:
        row = self.get_brain_row(brain_id)
        spec = self._spec(row)
        if spec is None:
            raise CerebroError(404, "Pergunta não encontrada")
        return row, spec

    def _answer_row(self, brain_id: str, qid: str) -> Optional[dict[str, Any]]:
        rows = (
            self.db.table(ANSWERS).select(ANSWER_COLS)
            .eq("brain_id", brain_id).eq("question_id", qid).eq("org_id", self.org_id)
            .execute().data
        )
        return rows[0] if rows else None

    def _answer_out(self, qid: str, row: dict[str, Any]) -> dict[str, Any]:
        tid = row.get("transcricao_id")
        jobs = transcricoes_por_id(self.db, self.org_id, [tid]) if tid else None
        return answer_dict(qid, row, jobs)

    @staticmethod
    def _assert_question(spec: BrainTemplateSpec, qid: str) -> None:
        if qid not in {question_id(spec.slug, q.position) for q in spec.questions}:
            raise CerebroError(404, "Pergunta não encontrada")

    def put_answer(self, brain_id: str, qid: str, text: str) -> dict[str, Any]:
        _, spec = self._require_questionnaire(brain_id)
        self._assert_question(spec, qid)
        existing = self._answer_row(brain_id, qid)
        if existing is None:
            try:
                res = self.db.table(ANSWERS).insert({
                    "id": str(uuid.uuid4()), "org_id": self.org_id, "brain_id": brain_id,
                    "question_id": qid, "text": text, "review_status": "none",
                }).execute().data
                return self._answer_out(qid, res[0])
            except Exception as exc:  # noqa: BLE001 - concurrent first autosave: fall through to update
                if not is_unique_violation(exc):
                    raise
                existing = self._answer_row(brain_id, qid)
                if existing is None:
                    raise
        patch: dict[str, Any] = {"text": text}
        if (
            existing.get("review_status") not in (None, "none")
            and text_sha(text) != existing.get("reviewed_text_sha")
        ):
            patch.update(self._review_reset())
        res = (
            self.db.table(ANSWERS).update(patch)
            .eq("id", existing["id"]).eq("org_id", self.org_id).execute().data
        )
        return self._answer_out(qid, res[0] if res else {**existing, **patch})

    def link_transcricao(self, brain_id: str, qid: str, transcricao_id: str) -> dict[str, Any]:
        """Point the answer at its (just submitted) voice transcription so the brain detail
        shows the job's status / position / error from the moment of the upload. The text
        itself is only written by the completion hook. Creates a blank answer row when the
        user recorded before typing anything."""
        existing = self._answer_row(brain_id, qid)
        if existing is None:
            try:
                res = self.db.table(ANSWERS).insert({
                    "id": str(uuid.uuid4()), "org_id": self.org_id, "brain_id": brain_id,
                    "question_id": qid, "text": "", "review_status": "none",
                    "transcricao_id": transcricao_id,
                }).execute().data
                return self._answer_out(qid, res[0])
            except Exception as exc:  # noqa: BLE001 - concurrent first autosave: fall through to update
                if not is_unique_violation(exc):
                    raise
                existing = self._answer_row(brain_id, qid)
                if existing is None:
                    raise
        res = (
            self.db.table(ANSWERS).update({"transcricao_id": transcricao_id})
            .eq("id", existing["id"]).eq("org_id", self.org_id).execute().data
        )
        return self._answer_out(qid, res[0] if res else {**existing, "transcricao_id": transcricao_id})

    @staticmethod
    def _review_reset() -> dict[str, Any]:
        return {
            "review_status": "none", "review_verdict": None, "review_reason": None,
            "review_improved": None, "review_decision": None, "review_error": None,
            "reviewed_text_sha": None, "review_requested_at": None,
        }

    def reset_answers(self, brain_id: str) -> int:
        self.get_brain_row(brain_id)
        res = (
            self.db.table(ANSWERS).delete()
            .eq("brain_id", brain_id).eq("org_id", self.org_id).execute().data
        )
        return len(res or [])

    # ── review (endpoints 10, 11) ───────────────────────────────────────

    def request_review(
        self, brain_id: str, question_ids: Optional[list[str]]
    ) -> list[tuple[str, str]]:
        """Mark the targeted non-empty answers ``pending``; returns the
        ``(question_id, text_sha)`` pairs the background task reviews."""
        row = self.get_brain_row(brain_id)
        spec = self._spec(row)
        answers = self._answers_of([brain_id]).get(brain_id, []) if spec else []
        wanted = set(question_ids) if question_ids is not None else None
        targets = [
            a for a in answers
            if (a.get("text") or "").strip() and (wanted is None or a["question_id"] in wanted)
        ]
        if not targets:
            raise CerebroError(422, "Responda ao menos uma pergunta")
        queued = []
        now = _iso()
        for a in targets:
            sha = text_sha(a["text"])
            self.db.table(ANSWERS).update({
                **self._review_reset(),
                "review_status": "pending", "reviewed_text_sha": sha, "review_requested_at": now,
            }).eq("id", a["id"]).eq("org_id", self.org_id).execute()
            queued.append((a["question_id"], sha))
        return queued

    async def run_review(
        self, brain_id: str, targets: list[tuple[str, str]], llm: CerebroLlm
    ) -> None:
        """Background task: one LLM call for the whole request. Never raises."""
        try:
            row = self.get_brain_row(brain_id)
            spec = self._spec(row)
            if spec is None:
                return
            by_qid = {question_id(spec.slug, q.position): q for q in spec.questions}
            current = {a["question_id"]: a for a in self._answers_of([brain_id]).get(brain_id, [])}
            live = [
                (qid, sha) for qid, sha in targets
                if (a := current.get(qid)) and a.get("review_status") == "pending"
                and a.get("reviewed_text_sha") == sha
            ]
            if not live:
                return
            items = [
                ReviewItem(qid, by_qid[qid].text, by_qid[qid].hint, by_qid[qid].optional,
                           current[qid]["text"])
                for qid, _ in live
            ]
            try:
                parsed = await review_answers(llm, self.org_id, spec.name, items)
            except Exception as exc:  # noqa: BLE001 - every pending answer of the request fails together
                logger.error("cerebro review: brain %s failed: %s", brain_id, exc)
                for qid, sha in live:
                    self._finish_review(brain_id, qid, sha, {
                        "review_status": "error", "review_error": MSG_REVIEW_FAILED,
                    })
                return
            for qid, sha in live:
                result = parsed.results.get(qid)
                if result is None:
                    self._finish_review(brain_id, qid, sha, {
                        "review_status": "error", "review_error": MSG_REVIEW_MISSING,
                    })
                else:
                    self._finish_review(brain_id, qid, sha, {
                        "review_status": "done", "review_verdict": result.verdict,
                        "review_reason": result.reason, "review_improved": result.improved,
                        "review_error": None,
                    })
        except Exception as exc:  # noqa: BLE001 - a background task must not die loudly; the sweep settles it
            logger.error("cerebro review task crashed for brain %s: %s", brain_id, exc, exc_info=True)

    def _finish_review(self, brain_id: str, qid: str, sha: str, patch: dict[str, Any]) -> None:
        # Conditional on still-pending + same text: an edit in the meantime reset
        # the review and this late result must be dropped, not written over it.
        self.db.table(ANSWERS).update(patch).eq("brain_id", brain_id).eq("question_id", qid) \
            .eq("org_id", self.org_id).eq("review_status", "pending") \
            .eq("reviewed_text_sha", sha).execute()

    def apply_suggestion(self, brain_id: str, qid: str, action: str) -> dict[str, Any]:
        _, spec = self._require_questionnaire(brain_id)
        self._assert_question(spec, qid)
        ans = self._answer_row(brain_id, qid)
        if ans is None:
            raise CerebroError(404, "Resposta não encontrada")
        if ans.get("review_status") != "done":
            raise CerebroError(409, "Não há sugestão de revisão para esta resposta.")
        patch: dict[str, Any] = {
            "review_decision": "accepted" if action == "accept" else "dismissed"
        }
        improved = ans.get("review_improved")
        if action == "accept" and improved:
            # The accepted text is the reviewed text now: keep the review and
            # move the sha so the "text changed -> reset" rule doesn't discard it.
            patch.update({"text": improved, "reviewed_text_sha": text_sha(improved)})
        res = (
            self.db.table(ANSWERS).update(patch)
            .eq("id", ans["id"]).eq("org_id", self.org_id).execute().data
        )
        return self._answer_out(qid, res[0] if res else {**ans, **patch})

    # ── synthesis (endpoint 12) ─────────────────────────────────────────

    def start_synthesis(self, brain_id: str, mode: str, expected_version: int) -> dict[str, Any]:
        """Validate + atomically claim the brain (``idle|error -> processing``).
        Returns the BrainSummary the 202 carries."""
        row = self.get_brain_row(brain_id)
        if row["kind"] != "sistema":
            raise CerebroError(409, "Apenas cérebros do sistema podem ser gerados a partir das respostas.")
        self._assert_not_synthesizing(row)
        if (row.get("content_version") or 0) != expected_version:
            raise CerebroError(409, "O conteúdo do cérebro mudou enquanto você editava.")
        answers = self._answers_of([brain_id]).get(brain_id, [])
        if not any((a.get("text") or "").strip() for a in answers):
            raise CerebroError(422, "Responda ao menos uma pergunta")
        claimed = (
            self._brains().update({
                "synthesis_status": "processing", "synthesis_error": None,
                "synthesis_started_at": _iso(),
            }).eq("id", brain_id).eq("org_id", self.org_id)
            .neq("synthesis_status", "processing").execute().data
        )
        if not claimed:
            raise CerebroError(409, "Aguarde a geração do cérebro terminar.")
        return self._summary(claimed[0])

    async def run_synthesis(
        self, brain_id: str, mode: str, expected_version: int, llm: CerebroLlm
    ) -> None:
        """Background task. LLM failure -> ``error`` with the content untouched
        (no partial write). Never raises."""
        try:
            row = self.get_brain_row(brain_id)
            spec = self._spec(row)
            if spec is None:
                return
            current = {a["question_id"]: a for a in self._answers_of([brain_id]).get(brain_id, [])}
            qa = []
            for q in spec.questions:
                text = ((current.get(question_id(spec.slug, q.position)) or {}).get("text") or "").strip()
                if text:
                    qa.append((q.text, q.hint, text))
            try:
                document = await synthesize_brain(llm, self.org_id, spec.slug, spec.name, qa)
            except Exception as exc:  # noqa: BLE001 - content untouched, error surfaced to the user
                logger.error("cerebro synthesis: brain %s LLM step failed: %s", brain_id, exc)
                self._synthesis_error(brain_id, MSG_SYNTHESIS_FAILED)
                return
            self._write_synthesis(brain_id, mode, expected_version, document)
        except Exception as exc:  # noqa: BLE001 - last resort; the sweep would also settle it
            logger.error("cerebro synthesis task crashed for brain %s: %s", brain_id, exc, exc_info=True)
            self._synthesis_error(brain_id, MSG_SYNTHESIS_FAILED)

    def _write_synthesis(self, brain_id: str, mode: str, expected_version: int, document: str) -> None:
        done = {
            "synthesis_status": "idle", "synthesis_error": None, "synthesized_at": _iso(),
        }
        try:
            if mode == "replace":
                if len(document) > MAX_CONTENT_CHARS:
                    self._synthesis_error(brain_id, MSG_OVER_LIMIT)
                    return
                res = (
                    self._brains().update({
                        **done, "content": document, "content_version": expected_version + 1,
                    }).eq("id", brain_id).eq("org_id", self.org_id)
                    .eq("content_version", expected_version)
                    .eq("synthesis_status", "processing").execute().data
                )
                if not res:
                    self._synthesis_error(brain_id, MSG_SYNTHESIS_STALE_VERSION)
                return
            row = self.get_brain_row(brain_id)
            if (row.get("content_version") or 0) != expected_version:
                self._synthesis_error(brain_id, MSG_SYNTHESIS_STALE_VERSION)
                return
            self.append_block(brain_id, document)
            self._brains().update(done).eq("id", brain_id).eq("org_id", self.org_id).execute()
        except CerebroError as exc:
            self._synthesis_error(brain_id, exc.detail)
        except Exception as exc:  # noqa: BLE001 - content untouched on any failed write
            logger.error("cerebro synthesis: brain %s write failed: %s", brain_id, exc)
            self._synthesis_error(brain_id, MSG_SYNTHESIS_FAILED)

    def _synthesis_error(self, brain_id: str, message: str) -> None:
        self._brains().update({"synthesis_status": "error", "synthesis_error": message}) \
            .eq("id", brain_id).eq("org_id", self.org_id).execute()

    # ── imports list (endpoint 16) ──────────────────────────────────────

    def list_imports(self, brain_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        self._refresh_stale()
        self.get_brain_row(brain_id)
        rows = (
            self.db.table(IMPORTS).select(IMPORT_COLS)
            .eq("brain_id", brain_id).eq("org_id", self.org_id)
            .order("created_at", desc=True).limit(limit).execute().data
        ) or []
        rows = sorted(rows, key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return [import_dict(r) for r in rows]
