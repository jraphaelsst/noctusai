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

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from noctusai_lib.domain.jobs import JobRepository, Worker, make_job_repository
from noctusai_lib.domain.jobs.entity import Job
from noctusai_lib.integrations.rate_limit import acquire_async
from noctusai_lib.integrations.whatsapp.types import WhatsAppClient

_TRANSMISSOES = "transmissoes"
_DESTINOS = "transmissao_destinos"
_GRUPOS = "grupos"

_JOB_TYPE = "community.transmissao_envio"
_RATE_LIMIT_BUCKET = "whatsapp_groups"
_EDITABLE_ESTADOS = ("rascunho", "agendada")
_EDIT_BLOCKED_DETAIL = "Só é possível editar uma transmissão em rascunho."
_DELETE_BLOCKED_DETAIL = "Só é possível excluir uma transmissão em rascunho."

# NOC-REMEDIATE[whatsapp-broadcast-worker]: `community.jobs` (migration
# 009) ships the durable Postgres-backed queue shape (retry/lease/
# dedupe_key + the four RPCs) for when this product gains a real
# standing worker process. Until then there is no scheduler to run one
# against (same gap the contract already flags for the retention job),
# so `enviar` drains its own just-enqueued jobs INLINE within the same
# request via a process-lifetime in-memory `FakeJobRepository` — durable
# enough to protect a double-click within one running process (the
# `dedupe_key` still no-ops a duplicate enqueue), but NOT across a
# process restart. Swap to `make_job_repository(use_fake=False,
# supabase_client=<admin client>, schema_name="community",
# table_name="jobs")` once a persistent worker is wired. — 2026-09-17
_inline_jobs_repo: JobRepository = make_job_repository(use_fake=True)


def get_jobs_repo() -> JobRepository:
    """Process-lifetime singleton — see the NOC-REMEDIATE note above."""
    return _inline_jobs_repo


class TransmissoesServiceError(Exception):
    def __init__(self, detail: str, *, status_code: int = 409) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


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
        jobs_repo: JobRepository | None = None,
    ) -> dict:
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

        self._client.table(_TRANSMISSOES).update({"estado": "enviando"}).eq(
            "org_id", self._org_id,
        ).eq("id", str(transmissao_id)).execute()

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
        todas_falharam = bool(destinos_finais) and all(
            d.get("estado") == "falhou" for d in destinos_finais
        )
        now = datetime.now(timezone.utc).isoformat()
        if todas_falharam:
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
