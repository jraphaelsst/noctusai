"""The classification worker: drains `assistant.jobs` on the seed `Worker` and records each verdict.

Two job types, both carrying the intake row id ONLY (no text, no identifier):

* ``assistant.classificar_intake`` -- enqueued by the database itself (trigger on `intake_messages`, migration 017)
  in the intake row's own transaction; the webhook write path then wakes this worker in-process
  (`app.services.intake` -> `notify_enqueued`). First pass: records `ai_outputs` + moves the intake outcome
  `pending -> classified | failed | skipped_budget` (skipped_budget keeps the text; a replay can classify it later).
* ``assistant.reclassificar_intake`` -- the replay (`enfileirar_replay`, admin route): classifies the retained text
  again under the registry's CURRENT prompt_version/model and writes a NEW ai_outputs row only. It never touches the
  intake row or an older classification.

Idempotent: the unique key (intake row, prompt_version, model) is the guard, and both handlers check it BEFORE the
model is called -- a re-run neither double-writes nor double-pays.

Fail-closed money gate (P9): the worker does not start unless an ENFORCED `LLM_SPEND_LIMITS` entry covers this call
(`assistant:<feature>` -> `assistant` -> `*`), so a missing limit leaves rows `pending` (text kept, nothing lost) and
the boot log says why. Per call, a budget refusal or an unverifiable budget is the outcome `skipped_budget`.

"""
from __future__ import annotations

import logging
import os
import re
import socket
from typing import Any, Callable, Optional
from uuid import UUID

import anyio.to_thread

from noctusai_lib.api.scheduler import SCHEDULERS_ENABLED_ENV, schedulers_enabled
from noctusai_lib.domain.jobs import DeadLetterError, JobRepository, RetryPolicy, Worker, make_job_repository
from noctusai_lib.domain.jobs.entity import Job
from noctusai_lib.domain.jobs.lifecycle import WorkerHandle
from noctusai_lib.integrations.llm.spend_guard import parse_limits
from noctusai_lib.integrations.prompt_registry import PromptRegistry, RegistroIAIndisponivel

from app.services.intake import CLASSIFY_JOB_TYPE
from app.shadow import classificador as clf

logger = logging.getLogger(__name__)

SCHEMA = "assistant"
JOB_CLASSIFICAR = CLASSIFY_JOB_TYPE
JOB_RECLASSIFICAR = "assistant.reclassificar_intake"
#: The feature `chamar_ia` attributes the call to (the spend guard narrows on `product:feature`).
FEATURE = f"plataforma.{clf.CHAVE}"
RETRY_POLICY = RetryPolicy(max_retries=3, backoff_seconds=30.0)
LEASE_SECONDS = 120.0
#: Hard cap of rows one replay request may enqueue.
REPLAY_MAX = 200

_handle: Optional[WorkerHandle] = None


# ── data access (explicit columns, one row, no scans) ─────────────────────────────────────────────────────────────
class IntakeDb:
    """The worker's four round trips over a service-role client scoped to `assistant`."""

    def __init__(self, client_factory: Callable[[], Any]) -> None:
        self._client = client_factory

    def ler(self, intake_id: str) -> Optional[dict]:
        rows = (
            self._client().table("intake_messages").select("id, org_id, outcome, body")
            .eq("id", intake_id).limit(1).execute().data
        )
        return rows[0] if rows else None

    def ja_classificado(self, intake_id: str, prompt_version: str, modelo: str) -> bool:
        rows = (
            self._client().table("ai_outputs").select("id")
            .eq("ref_type", "intake_message").eq("ref_id", intake_id).eq("kind", "classification")
            .eq("prompt_version", prompt_version).eq("model_version", modelo).limit(1).execute().data
        )
        return bool(rows)

    def desfecho(self, intake_id: str, outcome: str, motivo: str) -> None:
        self._client().rpc("set_intake_outcome", {
            "p_intake_id": intake_id, "p_outcome": outcome, "p_reason": motivo, "p_actor_kind": "agent",
        }).execute()

    def registrar(self, intake_id: str, r: clf.Resultado, *, primeira: bool) -> dict:
        c = r.classificacao
        rows = self._client().rpc("record_classification", {
            "p_intake_id": intake_id, "p_is_scheduling": c.is_scheduling, "p_confidence": c.confidence,
            "p_reason_code": c.reason_code, "p_model": r.modelo, "p_prompt_version": r.prompt_version,
            "p_metadata": r.metadata("primeira" if primeira else "replay"), "p_set_outcome": primeira,
        }).execute().data
        return (rows or [{}])[0]


def _codigo(exc: BaseException) -> str:
    """CamelCase exception class -> snake_case reason code (never the message: it may carry org ids / amounts)."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", type(exc).__name__).lower()


class Classificador:
    """The two handlers. `registry` / `chat` are passed through to `chamar_ia`'s own test seams."""

    def __init__(
        self, db: IntakeDb, *, max_chars: int = clf.MAX_CHARS_PADRAO,
        registry: Optional[PromptRegistry] = None, chat: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._db = db
        self._max_chars = max_chars
        self._registry = registry
        self._chat = chat

    async def _io(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return await anyio.to_thread.run_sync(lambda: fn(*args, **kwargs))

    async def _classificar(self, body: str, org_id: str) -> clf.Resultado:
        return await clf.classificar(
            body, org_id=org_id, max_chars=self._max_chars, registry=self._registry, chat=self._chat,
        )

    async def classificar_intake(self, job: Job) -> None:
        intake_id = str(job.payload["intake_id"])
        row = await self._io(self._db.ler, intake_id)
        if row is None or row.get("outcome") != "pending":
            return  # already decided (a re-run) or gone: nothing to do, nothing paid
        if not (row.get("body") or "").strip():
            await self._io(self._db.desfecho, intake_id, "failed", "sem_texto")
            return
        # No extra idempotency read here: `record_classification` writes the verdict AND moves the outcome in one
        # transaction, so a `pending` row has no first-pass verdict yet; the unique key backs it up.
        try:
            r = await self._classificar(row["body"], str(row["org_id"]))
        except clf.ERROS_ORCAMENTO as exc:
            await self._io(self._db.desfecho, intake_id, "skipped_budget", _codigo(exc))
            logger.warning("assistant classifier: skipped_budget (%s) intake=%s", _codigo(exc), intake_id)
            return
        except clf.SaidaInvalida as exc:
            await self._io(self._db.desfecho, intake_id, "failed", f"saida_invalida:{exc.motivo}")
            logger.warning("assistant classifier: invalid model output (%s) intake=%s", exc.motivo, intake_id)
            return
        except clf.RegistroMudou:
            raise  # retry: nothing was written
        except Exception as exc:
            if isinstance(exc, RegistroIAIndisponivel) or job.retry_count < job.max_retries:
                raise  # retry; a missing registry row leaves the row pending (text kept), never a guess
            await self._io(self._db.desfecho, intake_id, "failed", f"erro_provedor:{_codigo(exc)}")
            logger.error("assistant classifier: provider failed after retries (%s) intake=%s", _codigo(exc), intake_id)
            return
        await self._io(self._db.registrar, intake_id, r, primeira=True)

    async def reclassificar_intake(self, job: Job) -> None:
        intake_id = str(job.payload["intake_id"])
        pedido = (job.payload.get("prompt_version"), job.payload.get("modelo"))
        versao, modelo = await self._io(clf.versao_atual, registry=self._registry)
        if pedido != (versao, modelo):
            raise DeadLetterError("replay asked for a prompt_version/model the registry no longer serves")
        if await self._io(self._db.ja_classificado, intake_id, versao, modelo):
            return  # idempotent: this (row, version, model) is already classified
        row = await self._io(self._db.ler, intake_id)
        if row is None or not (row.get("body") or "").strip():
            return  # text no longer retained: nothing to replay
        try:
            r = await self._classificar(row["body"], str(row["org_id"]))
        except clf.ERROS_ORCAMENTO as exc:
            raise DeadLetterError(f"replay refused by the budget: {_codigo(exc)}") from None
        except clf.SaidaInvalida as exc:
            raise DeadLetterError(f"replay: invalid model output ({exc.motivo})") from None
        await self._io(self._db.registrar, intake_id, r, primeira=False)

    def handlers(self) -> dict[str, Callable[[Job], Any]]:
        return {JOB_CLASSIFICAR: self.classificar_intake, JOB_RECLASSIFICAR: self.reclassificar_intake}


# ── replay enqueue (admin route) ──────────────────────────────────────────────────────────────────────────────────
async def enfileirar_replay(
    repo: JobRepository, client_factory: Callable[[], Any], *, org_id: UUID, intake_ids: list[UUID],
    registry: Optional[PromptRegistry] = None,
) -> dict:
    """Enqueue a re-classification of `intake_ids` (this org's, already through the first pass -- classified|failed,
    or skipped_budget (a budget outage keeps the text; the replay classifies it) -- text still retained) under the
    registry's CURRENT
    prompt_version/model. Dedupe key = (row, version, model): asking twice enqueues once."""
    ids = list(dict.fromkeys(str(i) for i in intake_ids))[:REPLAY_MAX]
    versao, modelo = await anyio.to_thread.run_sync(lambda: clf.versao_atual(registry=registry))
    elegiveis = await anyio.to_thread.run_sync(lambda: [
        r["id"] for r in (
            client_factory().table("intake_messages").select("id").eq("org_id", str(org_id)).in_("id", ids)
            .in_("outcome", ["classified", "failed", "skipped_budget"]).not_.is_("body", "null").limit(len(ids)).execute().data or []
        )
    ]) if ids else []
    for intake_id in elegiveis:
        await repo.enqueue(
            type=JOB_RECLASSIFICAR,
            payload={"intake_id": intake_id, "prompt_version": versao, "modelo": modelo},
            max_retries=RETRY_POLICY.max_retries,
            dedupe_key=f"reclassificar:{intake_id}:{versao}:{modelo}",
        )
    return {"prompt_version": versao, "modelo": modelo, "enfileirados": len(elegiveis),
            "ignorados": len(ids) - len(elegiveis)}


# ── lifecycle ─────────────────────────────────────────────────────────────────────────────────────────────────────
def limite_de_gasto_aplicado(raw: Optional[str] = None) -> Optional[str]:
    """The surface of the ENFORCED spend limit that covers the classifier call, or None (=> refuse to start).
    Same resolution order as the seed guard: `assistant:<feature>` -> `assistant` -> `*`."""
    limites = parse_limits(os.environ.get("LLM_SPEND_LIMITS") if raw is None else raw)
    for chave in (f"assistant:{FEATURE}", "assistant", "*"):
        limite = limites.get(chave)
        if limite is not None:
            return chave if limite.mode == "enforce" else None
    return None


def worker_id() -> str:
    return f"assistant-classificador-{socket.gethostname()}-{os.getpid()}"


# poll-budget: seed Worker, idle 1s doubling to the seed 300s cap, reset on claim; 1 call/tick idle (claim_next_job); worst 288/day idle per process (+ ~6 calls per message: claim, read row, LLM ledger + registry measurement, record_classification, complete); idle=backoff+event (in-process notify_enqueued on intake)
def build_worker(repo: JobRepository, classificador: Classificador, *, idle_sleep: Any = None) -> Worker:
    return Worker(
        repo, worker_id=worker_id(), handlers=classificador.handlers(), retry_policy=RETRY_POLICY,
        poll_interval_seconds=1.0, lease_seconds=LEASE_SECONDS,
        idle_sleep=idle_sleep,
    )


def job_repository(client: Any) -> JobRepository:
    return make_job_repository(supabase_client=client, schema_name=SCHEMA)


def is_running() -> bool:
    return _handle is not None and _handle.is_running()


async def start_worker(cfg: Any = None) -> bool:
    """Start the classifier worker when this process may run it. Returns whether it is running; every refusal is
    logged with its reason (a worker is a side effect of the API process, never a precondition for serving)."""
    global _handle
    if cfg is None:
        from app.config import settings as cfg
    if not cfg.assistant_classifier_enabled:
        logger.info("assistant classifier: OFF (ASSISTANT_CLASSIFIER_ENABLED=false).")
        return False
    if not schedulers_enabled():
        logger.info("assistant classifier: OFF (%s absent -- only the deployed container runs it).", SCHEDULERS_ENABLED_ENV)
        return False
    superficie = limite_de_gasto_aplicado()
    if superficie is None:
        logger.error(
            "assistant classifier: NOT STARTED -- no ENFORCED LLM_SPEND_LIMITS entry covers it "
            "('assistant:%s' / 'assistant' / '*' with mode=enforce). Intake rows stay pending (text kept).", FEATURE,
        )
        return False
    if is_running():
        return True
    from app.dependencies import get_admin_client

    client = get_admin_client()
    if client is None:
        logger.error("assistant classifier: NOT STARTED -- no Supabase admin client.")
        return False
    classificador = Classificador(IntakeDb(get_admin_client), max_chars=int(cfg.assistant_classifier_max_chars))
    _handle = WorkerHandle(build_worker(job_repository(client), classificador), name="assistant-classificador")
    _handle.start()
    logger.info("assistant classifier: started (%s; spend limit '%s').", worker_id(), superficie)
    return True


async def stop_worker() -> None:
    global _handle
    handle, _handle = _handle, None
    if handle is not None:
        await handle.stop()
