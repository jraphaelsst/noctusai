"""Aplicações service — manager-defined questions + public submissions +
review — contract §Aplicações.

`ordem`-sort is applied in Python after fetch (same rationale as the
sibling services — the in-repo `MockSupabaseClient` treats `.order()`
as a no-op).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

_PERGUNTAS_TABLE = "aplicacao_perguntas"
_APLICACOES_TABLE = "aplicacoes"
_MEMBROS_TABLE = "membros"

_CHOICE_TIPOS = ("escolha_unica", "escolha_multipla")


class AplicacoesServiceError(Exception):
    """Domain-level failure surfaced to the router as an HTTP error."""

    def __init__(self, detail: str, *, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _validate_opcoes(tipo: str, opcoes: list) -> None:
    if tipo in _CHOICE_TIPOS and not opcoes:
        raise AplicacoesServiceError(
            "Informe as opções para este tipo de pergunta.", status_code=422,
        )


class AplicacoesService:
    """Manager-facing (authenticated, org-scoped) half of the domain."""

    def __init__(self, client: Any, *, org_id: UUID) -> None:
        self._client = client
        self._org_id = str(org_id)

    # ── perguntas (questions) ────────────────────────────────────────

    async def list_perguntas(self) -> dict:
        rows = (
            self._client.table(_PERGUNTAS_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .execute()
            .data
            or []
        )
        rows.sort(key=lambda r: r.get("ordem") or 0)
        return {"items": rows, "total": len(rows)}

    async def create_pergunta(self, *, payload: dict) -> dict:
        _validate_opcoes(payload["tipo"], payload.get("opcoes") or [])
        # See `planos_service.create`'s comment: client-supplied id keeps
        # mock and real-Postgres behavior identical.
        row = {"id": str(uuid4()), **payload, "org_id": self._org_id}
        result = self._client.table(_PERGUNTAS_TABLE).insert(row).execute()
        if not result.data:
            raise AplicacoesServiceError("Falha ao criar pergunta.")
        return result.data[0]

    async def update_pergunta(self, *, pergunta_id: str, payload: dict) -> dict | None:
        if "tipo" in payload or "opcoes" in payload:
            current = (
                self._client.table(_PERGUNTAS_TABLE)
                .select("*")
                .eq("org_id", self._org_id)
                .eq("id", str(pergunta_id))
                .maybe_single()
                .execute()
            ).data
            if current:
                tipo = payload.get("tipo", current.get("tipo"))
                opcoes = payload.get("opcoes", current.get("opcoes") or [])
                _validate_opcoes(tipo, opcoes)
        result = (
            self._client.table(_PERGUNTAS_TABLE)
            .update(payload)
            .eq("org_id", self._org_id)
            .eq("id", str(pergunta_id))
            .execute()
        )
        return result.data[0] if result.data else None

    async def soft_delete_pergunta(self, *, pergunta_id: str) -> bool:
        result = (
            self._client.table(_PERGUNTAS_TABLE)
            .update({"ativa": False})
            .eq("org_id", self._org_id)
            .eq("id", str(pergunta_id))
            .execute()
        )
        return bool(result.data)

    # ── aplicacoes (submissions review) ──────────────────────────────

    async def list_aplicacoes(self, *, status: str | None = None, page: int = 1, page_size: int = 50) -> dict:
        rows = (
            self._client.table(_APLICACOES_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .execute()
            .data
            or []
        )
        resumo = {"pendente": 0, "aprovada": 0, "rejeitada": 0}
        for row in rows:
            st = row.get("status")
            if st in resumo:
                resumo[st] += 1
        filtered = [r for r in rows if status is None or r.get("status") == status]
        filtered.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        total = len(filtered)
        start = (page - 1) * page_size
        page_rows = filtered[start:start + page_size]
        return {"items": page_rows, "total": total, "resumo": resumo}

    async def aprovar(
        self, *, aplicacao_id: str, plano_id: str | None, ativar: bool, revisor_id: str,
    ) -> dict:
        aplicacao = (
            self._client.table(_APLICACOES_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("id", str(aplicacao_id))
            .maybe_single()
            .execute()
        ).data
        if not aplicacao:
            raise AplicacoesServiceError("Inscrição não encontrada.", status_code=404)

        if aplicacao.get("status") == "aprovada" and aplicacao.get("membro_id"):
            # Idempotent: already approved → return the SAME membro.
            membro = (
                self._client.table(_MEMBROS_TABLE)
                .select("*")
                .eq("org_id", self._org_id)
                .eq("id", str(aplicacao["membro_id"]))
                .maybe_single()
                .execute()
            ).data
            return {"aplicacao": aplicacao, "membro": membro}

        if aplicacao.get("status") == "rejeitada":
            raise AplicacoesServiceError(
                "Essa inscrição já foi rejeitada.", status_code=409,
            )

        email = aplicacao["email"]
        existing_membro = (
            self._client.table(_MEMBROS_TABLE)
            .select("id")
            .eq("org_id", self._org_id)
            .eq("email", email)
            .execute()
            .data
        )
        if existing_membro:
            raise AplicacoesServiceError(
                "Esse e-mail já é um membro.", status_code=409,
            )

        membro_status = "pendente"
        if plano_id and ativar:
            membro_status = "ativo"
        _now = datetime.now(timezone.utc).isoformat()
        membro_row = {
            "id": str(uuid4()),
            "org_id": self._org_id,
            "nome": aplicacao["nome"],
            "email": email,
            "telefone": aplicacao.get("telefone"),
            "status": membro_status,
            "plano_id": str(plano_id) if plano_id else None,
            "origem": "aplicacao",
            "tags": [],
            "entrou_em": _now,
            "created_at": _now,
            "updated_at": _now,
        }
        membro_result = self._client.table(_MEMBROS_TABLE).insert(membro_row).execute()
        if not membro_result.data:
            raise AplicacoesServiceError("Falha ao criar membro.")
        membro = membro_result.data[0]

        aplicacao_result = (
            self._client.table(_APLICACOES_TABLE)
            .update({
                "status": "aprovada",
                "revisado_por": revisor_id,
                "revisado_em": datetime.now(timezone.utc).isoformat(),
                "membro_id": membro["id"],
            })
            .eq("org_id", self._org_id)
            .eq("id", str(aplicacao_id))
            .execute()
        )
        aplicacao_out = aplicacao_result.data[0] if aplicacao_result.data else aplicacao
        return {"aplicacao": aplicacao_out, "membro": membro}

    async def rejeitar(self, *, aplicacao_id: str, motivo: str, revisor_id: str) -> dict | None:
        aplicacao = (
            self._client.table(_APLICACOES_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("id", str(aplicacao_id))
            .maybe_single()
            .execute()
        ).data
        if not aplicacao:
            return None
        if aplicacao.get("status") == "aprovada":
            raise AplicacoesServiceError(
                "Essa inscrição já foi aprovada.", status_code=409,
            )
        result = (
            self._client.table(_APLICACOES_TABLE)
            .update({
                "status": "rejeitada",
                "motivo": motivo,
                "revisado_por": revisor_id,
                "revisado_em": datetime.now(timezone.utc).isoformat(),
            })
            .eq("org_id", self._org_id)
            .eq("id", str(aplicacao_id))
            .execute()
        )
        return result.data[0] if result.data else None


class PublicAplicacoesService:
    """Public (unauthenticated) half of the domain — org resolved by the
    caller (`resolve_public_org_id`), client is the admin/service-role
    client (there is no user session to scope RLS to)."""

    def __init__(self, client: Any, *, org_id: UUID) -> None:
        self._client = client
        self._org_id = str(org_id)

    async def list_formulario(self) -> dict:
        rows = (
            self._client.table(_PERGUNTAS_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("ativa", True)
            .execute()
            .data
            or []
        )
        rows.sort(key=lambda r: r.get("ordem") or 0)
        return {"items": rows, "total": len(rows)}

    async def submit(self, *, payload: dict) -> dict:
        perguntas = (
            self._client.table(_PERGUNTAS_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("ativa", True)
            .execute()
            .data
            or []
        )
        pergunta_ids = {str(p["id"]) for p in perguntas}
        respostas = payload.get("respostas") or {}

        for pergunta_id in respostas:
            if str(pergunta_id) not in pergunta_ids:
                raise AplicacoesServiceError(
                    "Pergunta inválida no formulário.", status_code=422,
                )

        for pergunta in perguntas:
            if not pergunta.get("obrigatoria"):
                continue
            pid = str(pergunta["id"])
            resposta = respostas.get(pid)
            if resposta is None or resposta == "" or resposta == []:
                raise AplicacoesServiceError(
                    "Responda todas as perguntas obrigatórias.", status_code=422,
                )

        email = payload["email"]
        pendentes = (
            self._client.table(_APLICACOES_TABLE)
            .select("id")
            .eq("org_id", self._org_id)
            .eq("email", email)
            .eq("status", "pendente")
            .execute()
            .data
        )
        if pendentes:
            raise AplicacoesServiceError(
                "Já existe uma inscrição em análise para esse e-mail.", status_code=409,
            )

        _now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": str(uuid4()),
            **payload,
            "org_id": self._org_id,
            "respostas": respostas,
            "status": "pendente",
            "created_at": _now,
            "updated_at": _now,
        }
        result = self._client.table(_APLICACOES_TABLE).insert(row).execute()
        if not result.data:
            raise AplicacoesServiceError("Falha ao registrar inscrição.")
        return result.data[0]
