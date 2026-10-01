"""Transmissões (broadcasts) service — contract §Transmissões.

`enviar` enqueues one `jobs` row per destino (contract: "Background send
worker (retry, lease, dedupe_key)" — `noctusai_lib.domain.jobs`), paced
on the `"whatsapp_groups"` rate-limit bucket, `dedupe_key =
f"transmissao:{id}:{grupo_id}"` so a re-send never double-fires the
same destino. Community has no standing scheduler process (see the
`NOC-REMEDIATE[whatsapp-broadcast-worker]` note below) — this request
handler drains its own just-enqueued jobs synchronously via
`Worker.run_once()` so the endpoint's 202 response reflects real
per-destino outcomes without inventing a second send path.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from noctusai_lib.domain.jobs import JobRepository, Worker, make_job_repository
from noctusai_lib.domain.jobs.entity import Job
from noctusai_lib.integrations.rate_limit import acquire_async
from noctusai_lib.integrations.whatsapp.types import WhatsAppClient

logger = logging.getLogger(__name__)

# A scheduled broadcast whose WhatsApp stayed disconnected this long past
# its `agendada_para` is marked "falhou" (a stale announcement sent days
# late is worse than a visible failure); younger ones wait for a reconnect.
AGENDADA_EXPIRA_APOS = timedelta(hours=24)
_NAO_CONECTADO_ERRO = "WhatsApp não conectado no horário agendado (expirou após 24h)."

_TRANSMISSOES = "transmissoes"
_DESTINOS = "transmissao_destinos"
_GRUPOS = "grupos"

_JOB_TYPE = "community.transmissao_envio"
_RATE_LIMIT_BUCKET = "whatsapp_groups"
_EDITABLE_ESTADOS = ("rascunho", "agendada")
_EDIT_BLOCKED_DETAIL = "Só é possível editar uma transmissão em rascunho."
_DELETE_BLOCKED_DETAIL = "Só é possível excluir uma transmissão em rascunho."

# NOC-REMEDIATE[whatsapp-broadcast-worker]: PARTIALLY CLOSED 2026-10-01.
# SCHEDULED sends are now driven by the standing scheduler job
# `community_transmissoes_agendadas` (`app/scheduler.py` ->
# `executar_agendadas` below), claimed atomically (agendada -> enviando)
# and sent through this same `enviar`. WHAT REMAINS: `community.jobs`
# (migration 009) ships the durable Postgres-backed queue (retry/lease/
# dedupe_key + the four RPCs) but `enviar` still drains its own
# just-enqueued jobs INLINE via a process-lifetime in-memory
# `FakeJobRepository` — the `dedupe_key` protects a double-enqueue within
# one process only, NOT across a restart (cross-process double-send is
# prevented by the atomic claim, not by this repo). Swap to
# `make_job_repository(use_fake=False, supabase_client=<admin client>,
# schema_name="community", table_name="jobs")` + a worker tick to make
# per-destino retry durable. — 2026-09-17
_inline_jobs_repo: JobRepository = make_job_repository(use_fake=True)


def get_jobs_repo() -> JobRepository:
    """Process-lifetime singleton — see the NOC-REMEDIATE note above."""
    return _inline_jobs_repo


JA_ENVIADA_DETAIL = "Esta transmissão já está sendo enviada ou já foi enviada."
JA_ENVIADA_CODE = "TRANSMISSAO_JA_ENVIADA"


class TransmissoesServiceError(Exception):
    def __init__(self, detail: str, *, status_code: int = 409, code: str | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.code = code


class TransmissoesService:
    def __init__(self, client: Any, *, org_id) -> None:
        self._client = client
        self._org_id = str(org_id)

    # ── reads ────────────────────────────────────────────────────────

    async def list(self, *, estado: str | None = None, page: int = 1, page_size: int = 50) -> dict:
        query = self._client.table(_TRANSMISSOES).select("*").eq("org_id", self._org_id)
        if estado:
            query = query.eq("estado", estado)
        rows = query.execute().data or []
        rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        total = len(rows)
        start = (page - 1) * page_size
        page_rows = rows[start:start + page_size]
        return {"items": [self._with_destinos(r) for r in page_rows], "total": total}

    async def get(self, *, transmissao_id: str) -> dict | None:
        row = (
            self._client.table(_TRANSMISSOES).select("*")
            .eq("org_id", self._org_id).eq("id", str(transmissao_id))
            .maybe_single().execute().data
        )
        return self._with_destinos(row) if row else None

    def _with_destinos(self, row: dict) -> dict:
        destinos = (
            self._client.table(_DESTINOS).select("*")
            .eq("org_id", self._org_id).eq("transmissao_id", row["id"])
            .execute().data or []
        )
        return {**row, "destinos": destinos}

    # ── writes ───────────────────────────────────────────────────────

    async def create(self, *, payload: dict, criada_por) -> dict:
        grupo_ids = payload["grupo_ids"]
        existentes = (
            self._client.table(_GRUPOS).select("id")
            .eq("org_id", self._org_id).in_("id", grupo_ids)
            .execute().data or []
        )
        existentes_ids = {str(g["id"]) for g in existentes}
        if any(str(g) not in existentes_ids for g in grupo_ids):
            raise TransmissoesServiceError(
                "Grupo inválido na lista de destinos.", status_code=422,
            )

        now = datetime.now(timezone.utc).isoformat()
        estado = "agendada" if payload.get("agendada_para") else "rascunho"
        row = {
            "id": str(uuid4()), "org_id": self._org_id,
            "titulo": payload["titulo"], "corpo": payload["corpo"], "tipo": payload["tipo"],
            "estado": estado, "agendada_para": payload.get("agendada_para"),
            "enviada_em": None, "criada_por": str(criada_por) if criada_por else None,
            "created_at": now, "updated_at": now,
        }
        result = self._client.table(_TRANSMISSOES).insert(row).execute()
        if not result.data:
            raise TransmissoesServiceError("Falha ao criar transmissão.", status_code=502)
        transmissao = result.data[0]

        for grupo_id in grupo_ids:
            self._client.table(_DESTINOS).insert({
                "id": str(uuid4()), "org_id": self._org_id,
                "transmissao_id": transmissao["id"], "grupo_id": str(grupo_id),
                "estado": "pendente",
            }).execute()

        return self._with_destinos(transmissao)

    async def update(self, *, transmissao_id: str, payload: dict) -> dict | None:
        current = (
            self._client.table(_TRANSMISSOES).select("*")
            .eq("org_id", self._org_id).eq("id", str(transmissao_id))
            .maybe_single().execute().data
        )
        if not current:
            return None
        if current["estado"] not in _EDITABLE_ESTADOS:
            raise TransmissoesServiceError(_EDIT_BLOCKED_DETAIL, status_code=409)

        grupo_ids = payload.pop("grupo_ids", None)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        result = (
            self._client.table(_TRANSMISSOES).update(payload)
            .eq("org_id", self._org_id).eq("id", str(transmissao_id))
            .execute()
        )
        if grupo_ids is not None:
            existing_destinos = (
                self._client.table(_DESTINOS).select("*")
                .eq("org_id", self._org_id).eq("transmissao_id", str(transmissao_id))
                .execute().data or []
            )
            existing_grupo_ids = {d["grupo_id"] for d in existing_destinos}
            for grupo_id in grupo_ids:
                if str(grupo_id) not in existing_grupo_ids:
                    self._client.table(_DESTINOS).insert({
                        "id": str(uuid4()), "org_id": self._org_id,
                        "transmissao_id": str(transmissao_id), "grupo_id": str(grupo_id),
                        "estado": "pendente",
                    }).execute()
        row = result.data[0] if result.data else current
        return self._with_destinos(row)

    async def delete(self, *, transmissao_id: str) -> bool:
        current = (
            self._client.table(_TRANSMISSOES).select("*")
            .eq("org_id", self._org_id).eq("id", str(transmissao_id))
            .maybe_single().execute().data
        )
        if not current:
            return False
        if current["estado"] not in _EDITABLE_ESTADOS:
            raise TransmissoesServiceError(_DELETE_BLOCKED_DETAIL, status_code=409)
        result = (
            self._client.table(_TRANSMISSOES).delete()
            .eq("org_id", self._org_id).eq("id", str(transmissao_id))
            .execute()
        )
        return bool(result.data)

    # ── enviar (contract §3 item 17) ────────────────────────────────────

    async def enviar(
        self, *, transmissao_id: str, waha_client: WhatsAppClient,
        jobs_repo: JobRepository | None = None, claimed: bool = False,
    ) -> dict:
        """`claimed=True` = the caller (scheduler) already won the atomic
        agendada -> enviando claim; otherwise this claims rascunho/agendada
        -> enviando itself and a lost claim raises 409 `TRANSMISSAO_JA_ENVIADA`.
        """
        jobs_repo = jobs_repo or get_jobs_repo()
        transmissao = (
            self._client.table(_TRANSMISSOES).select("*")
            .eq("org_id", self._org_id).eq("id", str(transmissao_id))
            .maybe_single().execute().data
        )
        if not transmissao:
            raise TransmissoesServiceError("Transmissão não encontrada.", status_code=404)

        destinos = (
            self._client.table(_DESTINOS).select("*")
            .eq("org_id", self._org_id).eq("transmissao_id", str(transmissao_id))
            .execute().data or []
        )

        if not destinos:
            # Nothing to send → never flip to "enviando"/"enviada".
            raise TransmissoesServiceError(
                "Selecione ao menos um grupo de destino antes de enviar.", status_code=422,
            )

        if not claimed:
            # Atomic claim — only one concurrent sender (manual or scheduled) wins.
            for origem in ("rascunho", "agendada"):
                if self._claim(transmissao_id, "enviando", origem=origem):
                    break
            else:
                raise TransmissoesServiceError(
                    JA_ENVIADA_DETAIL, status_code=409, code=JA_ENVIADA_CODE,
                )

        for destino in destinos:
            await jobs_repo.enqueue(
                type=_JOB_TYPE,
                payload={
                    "transmissao_id": str(transmissao_id),
                    "grupo_id": str(destino["grupo_id"]),
                    "corpo": transmissao["corpo"],
                },
                dedupe_key=f"transmissao:{transmissao_id}:{destino['grupo_id']}",
            )

        async def _handle(job: Job) -> None:
            await self._processar_destino_job(job, waha_client=waha_client)

        worker = Worker(jobs_repo, worker_id="transmissoes-inline", handlers={_JOB_TYPE: _handle})
        for _ in range(len(destinos)):
            processed = await worker.run_once()
            if not processed:
                break

        destinos_finais = (
            self._client.table(_DESTINOS).select("*")
            .eq("org_id", self._org_id).eq("transmissao_id", str(transmissao_id))
            .execute().data or []
        )
        # "enviada" is earned by at least one REAL send (a destino the
        # client confirmed) — never by the absence of failures.
        algum_enviado = any(d.get("estado") == "enviado" for d in destinos_finais)
        now = datetime.now(timezone.utc).isoformat()
        if not algum_enviado:
            primeiro_erro = next(
                (d.get("erro") for d in destinos_finais if d.get("erro")), None,
            )
            self._client.table(_TRANSMISSOES).update({
                "estado": "falhou",
            }).eq("org_id", self._org_id).eq("id", str(transmissao_id)).execute()
        else:
            self._client.table(_TRANSMISSOES).update({
                "estado": "enviada", "enviada_em": now,
            }).eq("org_id", self._org_id).eq("id", str(transmissao_id)).execute()

        return {"transmissao_id": transmissao_id, "destinos": len(destinos)}

    async def _processar_destino_job(self, job: Job, *, waha_client: WhatsAppClient) -> None:
        grupo_id = job.payload["grupo_id"]
        corpo = job.payload["corpo"]
        grupo = (
            self._client.table(_GRUPOS).select("chat_id")
            .eq("org_id", self._org_id).eq("id", grupo_id)
            .maybe_single().execute().data
        )
        await acquire_async(_RATE_LIMIT_BUCKET)
        try:
            if grupo is None:
                raise RuntimeError("grupo não encontrado")
            result = await waha_client.send_text(grupo["chat_id"], corpo)
        except Exception as exc:
            self._client.table(_DESTINOS).update({
                "estado": "falhou", "erro": str(exc),
            }).eq("org_id", self._org_id).eq(
                "transmissao_id", job.payload["transmissao_id"],
            ).eq("grupo_id", grupo_id).execute()
            raise
        self._client.table(_DESTINOS).update({
            "estado": "enviado",
            "provider_message_id": result.get("id") if isinstance(result, dict) else None,
            "enviado_em": datetime.now(timezone.utc).isoformat(),
        }).eq("org_id", self._org_id).eq(
            "transmissao_id", job.payload["transmissao_id"],
        ).eq("grupo_id", grupo_id).execute()


    # ── scheduled sends (scheduler tick) ────────────────────────────────

    async def executar_agendadas(
        self, *, waha_client: WhatsAppClient | None, now: datetime | None = None,
        jobs_repo: JobRepository | None = None,
    ) -> dict:
        """Send every due "agendada" transmissão through `enviar`.

        Each row is CLAIMED first with a conditional update
        (`estado='agendada'` -> `'enviando'`); only the tick whose update
        returns the row proceeds, so overlapping ticks/instances never
        double-send. `waha_client=None` (WhatsApp not connected) never
        fake-sends: rows stay "agendada" (one WARNING per tick) until
        `AGENDADA_EXPIRA_APOS` past their time, then become "falhou".
        """
        now = now or datetime.now(timezone.utc)
        rows = (
            self._client.table(_TRANSMISSOES).select("*")
            .eq("org_id", self._org_id).eq("estado", "agendada")
            .execute().data or []
        )
        vencidas = [r for r in rows if _due(r.get("agendada_para"), now)]
        resumo = {"vencidas": len(vencidas), "enviadas": 0, "falhas": 0, "adiadas": 0}
        if not vencidas:
            return resumo

        if waha_client is None:
            logger.warning(
                "transmissoes agendadas: org %s tem %d vencida(s) mas o WhatsApp não está "
                "conectado — mantidas 'agendada'", self._org_id, len(vencidas),
            )
            for row in vencidas:
                agendada = _parse_dt(row["agendada_para"])
                if agendada is not None and now - agendada > AGENDADA_EXPIRA_APOS:
                    if self._claim(row["id"], "falhou"):
                        logger.error("transmissao %s expirou sem WhatsApp conectado", row["id"])
                        self._client.table(_DESTINOS).update({
                            "estado": "falhou", "erro": _NAO_CONECTADO_ERRO,
                        }).eq("org_id", self._org_id).eq("transmissao_id", row["id"]).eq(
                            "estado", "pendente",
                        ).execute()
                        resumo["falhas"] += 1
                        continue
                resumo["adiadas"] += 1
            return resumo

        for row in vencidas:
            if not self._claim(row["id"], "enviando"):
                continue  # another tick/instance owns it
            try:
                await self.enviar(
                    transmissao_id=row["id"], waha_client=waha_client, jobs_repo=jobs_repo,
                    claimed=True,
                )
            except Exception as exc:  # noqa: BLE001 — logged + row marked, tick continues
                logger.error("transmissao %s: envio agendado falhou: %s", row["id"], exc, exc_info=True)
                self._client.table(_TRANSMISSOES).update({"estado": "falhou"}).eq(
                    "org_id", self._org_id,
                ).eq("id", row["id"]).execute()
                resumo["falhas"] += 1
                continue
            final = (
                self._client.table(_TRANSMISSOES).select("estado")
                .eq("org_id", self._org_id).eq("id", row["id"])
                .maybe_single().execute().data
            ) or {}
            resumo["enviadas" if final.get("estado") == "enviada" else "falhas"] += 1
        return resumo

    def _claim(self, transmissao_id: str, novo_estado: str, *, origem: str = "agendada") -> bool:
        """Atomic conditional update `origem` -> `novo_estado`; True iff won."""
        result = (
            self._client.table(_TRANSMISSOES).update({"estado": novo_estado})
            .eq("org_id", self._org_id).eq("id", str(transmissao_id))
            .eq("estado", origem).execute()
        )
        return bool(result.data)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _due(value: Any, now: datetime) -> bool:
    dt = _parse_dt(value)
    return dt is not None and dt <= now
