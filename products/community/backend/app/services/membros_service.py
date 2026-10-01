"""Membros service — contract §Membros.

`busca` (nome/email, case-insensitive, partial) and ordering are applied
in Python after a scoped fetch — same rationale as `planos_service`: the
in-repo `MockSupabaseClient` evaluates `.or_()` as match-all and
`.order()` as a no-op, so relying on the client for either would make
this service's behavior untestable. `status`, `plano_id` and `tag` DO
have real predicate evaluators (`in_` / `eq` / `contains`) and are
applied server-side.
"""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.domain.org import attach_user_to_org, find_auth_user_id_by_email, provision_invited_identity

from app.dependencies import MEMBRO_ORG_ROLE
from app.schemas.membros import MEMBRO_STATUSES
from app.services.eventos_service import registrar_evento

_TABLE = "membros"
_PLANOS_TABLE = "planos"
_EVENTOS_TABLE = "membro_eventos"
_NOCTUS_USERS_TABLE = "noctus_users"

#: `POST /api/membros/{id}/acesso` — contract §Identity, slice BE-A.
_SENHA_TEMP_LEN = 12
_SENHA_TEMP_ALPHABET = string.ascii_letters + string.digits


def _gerar_senha_temporaria() -> str:
    return "".join(secrets.choice(_SENHA_TEMP_ALPHABET) for _ in range(_SENHA_TEMP_LEN))


class MembrosServiceError(Exception):
    """Domain-level failure surfaced to the router as an HTTP error."""

    def __init__(self, detail: str, *, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class MembrosService:
    def __init__(self, client: Any, *, org_id: UUID) -> None:
        self._client = client
        self._org_id = str(org_id)

    # ── reads ────────────────────────────────────────────────────────

    async def list(
        self,
        *,
        status: str | None = None,
        plano_id: str | None = None,
        tag: str | None = None,
        busca: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        rows = self._fetch_filtered(plano_id=plano_id, tag=tag, busca=busca)
        resumo = self._compute_resumo(rows)
        if status:
            wanted = {s.strip() for s in status.split(",") if s.strip()}
            rows = [r for r in rows if r.get("status") in wanted]
        rows.sort(key=lambda r: (r.get("nome") or "").lower())
        total = len(rows)
        start = (page - 1) * page_size
        page_rows = rows[start:start + page_size]
        plano_nomes = self._plano_nomes([r.get("plano_id") for r in page_rows])
        items = [self._to_out(r, plano_nomes) for r in page_rows]
        return {"items": items, "total": total, "resumo": resumo}

    def _fetch_filtered(self, *, plano_id: str | None, tag: str | None, busca: str | None) -> list[dict]:
        query = self._client.table(_TABLE).select("*").eq("org_id", self._org_id)
        if plano_id:
            query = query.eq("plano_id", str(plano_id))
        if tag:
            query = query.contains("tags", [tag])
        rows = query.execute().data or []
        if busca:
            needle = busca.lower()
            rows = [
                r for r in rows
                if needle in (r.get("nome") or "").lower()
                or needle in (r.get("email") or "").lower()
            ]
        return rows

    @staticmethod
    def _compute_resumo(rows: list[dict]) -> dict[str, int]:
        resumo = {s: 0 for s in MEMBRO_STATUSES}
        for row in rows:
            st = row.get("status")
            if st in resumo:
                resumo[st] += 1
        return resumo

    def _plano_nomes(self, plano_ids: list) -> dict[str, str]:
        ids = sorted({str(i) for i in plano_ids if i})
        if not ids:
            return {}
        rows = (
            self._client.table(_PLANOS_TABLE)
            .select("id,nome")
            .eq("org_id", self._org_id)
            .in_("id", ids)
            .execute()
            .data
            or []
        )
        return {str(r["id"]): r["nome"] for r in rows}

    @staticmethod
    def _to_out(row: dict, plano_nomes: dict[str, str]) -> dict:
        plano_id = row.get("plano_id")
        plano_nome = plano_nomes.get(str(plano_id)) if plano_id else None
        return {**row, "plano_nome": plano_nome}

    async def get(self, *, membro_id: str) -> dict | None:
        result = (
            self._client.table(_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("id", str(membro_id))
            .maybe_single()
            .execute()
        )
        row = result.data
        if not row:
            return None
        plano_nomes = self._plano_nomes([row.get("plano_id")])
        return self._to_out(row, plano_nomes)

    # ── writes ───────────────────────────────────────────────────────

    async def create(self, *, payload: dict, autor_id: Optional[UUID | str] = None) -> dict:
        email = payload["email"]
        existing = (
            self._client.table(_TABLE)
            .select("id")
            .eq("org_id", self._org_id)
            .eq("email", email)
            .execute()
            .data
        )
        if existing:
            raise MembrosServiceError(
                "Já existe um membro com esse e-mail.", status_code=409,
            )
        # See `planos_service.create`'s comment: client-supplied id keeps
        # mock and real-Postgres behavior identical.
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": str(uuid4()),
            **payload,
            "org_id": self._org_id,
            "entrou_em": now,
            "created_at": now,
            "updated_at": now,
        }
        if row.get("plano_id") is not None:
            row["plano_id"] = str(row["plano_id"])
        result = self._client.table(_TABLE).insert(row).execute()
        if not result.data:
            raise MembrosServiceError("Falha ao criar membro.")
        created = result.data[0]
        registrar_evento(
            self._client, org_id=self._org_id, membro_id=created["id"], tipo="sistema",
            descricao="Membro cadastrado pela equipe.",
            dados={"origem": created.get("origem")},
            autor_id=autor_id,
        )
        plano_nomes = self._plano_nomes([created.get("plano_id")])
        return self._to_out(created, plano_nomes)

    async def update(
        self, *, membro_id: str, payload: dict, autor_id: Optional[UUID | str] = None,
    ) -> dict | None:
        if "email" in payload:
            existing = (
                self._client.table(_TABLE)
                .select("id")
                .eq("org_id", self._org_id)
                .eq("email", payload["email"])
                .execute()
                .data
                or []
            )
            if any(str(r["id"]) != str(membro_id) for r in existing):
                raise MembrosServiceError(
                    "Já existe um membro com esse e-mail.", status_code=409,
                )
        current_plano_id = None
        plano_changing = "plano_id" in payload
        if plano_changing:
            current = (
                self._client.table(_TABLE)
                .select("plano_id")
                .eq("org_id", self._org_id)
                .eq("id", str(membro_id))
                .maybe_single()
                .execute()
            ).data
            current_plano_id = current.get("plano_id") if current else None
        if payload.get("plano_id") is not None:
            payload = {**payload, "plano_id": str(payload["plano_id"])}
        result = (
            self._client.table(_TABLE)
            .update(payload)
            .eq("org_id", self._org_id)
            .eq("id", str(membro_id))
            .execute()
        )
        if not result.data:
            return None
        row = result.data[0]
        # Contract §Identity: "PATCH changing plano_id writes evento plano."
        if plano_changing and str(current_plano_id) != str(row.get("plano_id")):
            registrar_evento(
                self._client, org_id=self._org_id, membro_id=membro_id, tipo="plano",
                descricao="Plano alterado.",
                dados={"de": current_plano_id, "para": row.get("plano_id")},
                autor_id=autor_id,
            )
        plano_nomes = self._plano_nomes([row.get("plano_id")])
        return self._to_out(row, plano_nomes)

    async def set_status(
        self, *, membro_id: str, novo_status: str, motivo: str | None = None,
        autor_id: Optional[UUID | str] = None,
    ) -> dict | None:
        """Set status — an event, module 2 hangs payment-driven transitions
        off this same function. Idempotent: same status → 200, unchanged.

        `motivo` is persisted inside the `status` evento's `dados`
        (contract §Identity: "closes NOC-REMEDIATE[status-history]") — the
        timeline (`community.membro_eventos`, migration 013) IS the
        status-change audit trail module 1's marker deferred to.
        """
        current = (
            self._client.table(_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("id", str(membro_id))
            .maybe_single()
            .execute()
        ).data
        if not current:
            return None
        # Captured BEFORE the update below: some request-builder test
        # doubles mutate the row dict returned by `select()` in place, so
        # reading `current.get("status")` AFTER the update would silently
        # report the NEW status as the "de" value.
        status_anterior = current.get("status")
        if status_anterior == novo_status:
            plano_nomes = self._plano_nomes([current.get("plano_id")])
            return self._to_out(current, plano_nomes)
        if novo_status == "ativo" and not current.get("plano_id"):
            raise MembrosServiceError(
                "Defina um plano antes de ativar o membro.", status_code=409,
            )
        result = (
            self._client.table(_TABLE)
            .update({"status": novo_status})
            .eq("org_id", self._org_id)
            .eq("id", str(membro_id))
            .execute()
        )
        if not result.data:
            return None
        row = result.data[0]
        registrar_evento(
            self._client, org_id=self._org_id, membro_id=membro_id, tipo="status",
            descricao=f"Status alterado de {status_anterior} para {novo_status}.",
            dados={"de": status_anterior, "para": novo_status, "motivo": motivo},
            autor_id=autor_id,
        )
        plano_nomes = self._plano_nomes([row.get("plano_id")])
        return self._to_out(row, plano_nomes)

    async def soft_delete(self, *, membro_id: str) -> bool:
        """Sets `status='cancelado'`. NEVER hard-deletes (LGPD erasure is
        a separate, later flow)."""
        result = (
            self._client.table(_TABLE)
            .update({"status": "cancelado"})
            .eq("org_id", self._org_id)
            .eq("id", str(membro_id))
            .execute()
        )
        return bool(result.data)

    # ── access provisioning — contract §Identity, slice BE-A ───────────

    async def criar_acesso(
        self, *, membro_id: str, core_client: Any, autor_id: Optional[UUID | str] = None,
    ) -> dict | None:
        """`POST /api/membros/{id}/acesso` — create the member's login when
        they have none.

        `core_client` reaches the PLATFORM tables (`noctus_users`,
        `auth.admin.*`) — see `app/dependencies.py`'s `get_core_client`.
        """
        membro = (
            self._client.table(_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("id", str(membro_id))
            .maybe_single()
            .execute()
        ).data
        if not membro:
            return None
        if membro.get("user_id"):
            raise MembrosServiceError("Este membro já tem acesso.", status_code=409)

        email = membro["email"]
        existing_id = find_auth_user_id_by_email(core_client, email)
        if existing_id:
            self._client.table(_TABLE).update({"user_id": existing_id}).eq(
                "org_id", self._org_id,
            ).eq("id", str(membro_id)).execute()
            raise MembrosServiceError(
                "Este e-mail já tinha login; o acesso foi vinculado.", status_code=409,
            )

        senha = _gerar_senha_temporaria()
        user_id, _created = provision_invited_identity(
            core_client, email=email, password=senha, nome=membro["nome"],
        )
        attach_user_to_org(
            core_client, user_id, org_id=self._org_id, email=email, nome=membro["nome"],
            org_role=MEMBRO_ORG_ROLE,
        )
        self._client.table(_TABLE).update({"user_id": user_id}).eq(
            "org_id", self._org_id,
        ).eq("id", str(membro_id)).execute()
        registrar_evento(
            self._client, org_id=self._org_id, membro_id=membro_id, tipo="acesso",
            descricao="Acesso criado pela equipe", autor_id=autor_id,
        )
        return {"email": email, "senha_temporaria": senha}

    # ── relationship timeline — contract §Identity, slice BE-A ─────────

    async def list_eventos(
        self, *, membro_id: str, page: int = 1, page_size: int = 50, core_client: Any,
    ) -> dict:
        rows = (
            self._client.table(_EVENTOS_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("membro_id", str(membro_id))
            .execute()
            .data
            or []
        )
        rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        total = len(rows)
        start = (page - 1) * page_size
        page_rows = rows[start:start + page_size]
        autor_nomes = self._autor_nomes(core_client, [r.get("autor_id") for r in page_rows])
        items = [
            {**r, "autor_nome": autor_nomes.get(str(r["autor_id"])) if r.get("autor_id") else None}
            for r in page_rows
        ]
        return {"items": items, "total": total}

    @staticmethod
    def _autor_nomes(core_client: Any, autor_ids: list) -> dict[str, str]:
        ids = sorted({str(i) for i in autor_ids if i})
        if not ids:
            return {}
        rows = (
            core_client.table(_NOCTUS_USERS_TABLE)
            .select("id,nome")
            .in_("id", ids)
            .execute()
            .data
            or []
        )
        return {str(r["id"]): r.get("nome") for r in rows}

    async def criar_evento(
        self, *, membro_id: str, tipo: str, descricao: str,
        autor_id: Optional[UUID | str] = None, autor_nome: str | None = None,
    ) -> dict | None:
        membro = (
            self._client.table(_TABLE)
            .select("id")
            .eq("org_id", self._org_id)
            .eq("id", str(membro_id))
            .maybe_single()
            .execute()
        ).data
        if not membro:
            return None
        # Explicit id: this row is echoed straight back as the HTTP
        # response (unlike every other `registrar_evento` call in this
        # module, which is fire-and-forget) — see `registrar_evento`'s
        # docstring for why the id must be client-supplied here.
        row = registrar_evento(
            self._client, org_id=self._org_id, membro_id=membro_id, tipo=tipo,
            descricao=descricao, autor_id=autor_id, id=uuid4(),
        )
        # `created_at` is a DB-computed default (migration 013); a real
        # write always returns it, but nothing here re-derives it if the
        # underlying client didn't — `setdefault` only fires when it's
        # genuinely absent.
        row.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        return {**row, "autor_nome": autor_nome}
