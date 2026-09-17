"""Grupos (WhatsApp groups) service — contract §Grupos.

Consumes the seed's WAHA client (`WhatsAppGroupClient` surface) — never a
second client. Group mutations that touch WAHA (create, roster sync,
invite get/revoke) route through the caller-supplied client instance;
this service never constructs one itself so tests inject `FakeWahaClient`
and production injects the real `WahaClient` via `get_whatsapp_client()`
at the router layer.

Roster identity matching uses the seed's promoted
`noctusai_lib.integrations.whatsapp.identity.resolve_identity` — the
parallel seed-lift slice (`feat/seed-whatsapp-identity-lift`) this
product depends on. That import is deliberately LOCAL to
`sincronizar_roster` (not module-level): the lift lands in a separate
in-flight slice, and a module-level `ModuleNotFoundError` here would
break `app.main`'s import chain for every OTHER router in this product
(module 1 + module 2's 218 tests included) until the tech-lead
integrates that slice. Every other method in this service has zero
dependency on it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from noctusai_lib.integrations.whatsapp.client import WahaGroupError, WahaSessionNotReady
from noctusai_lib.integrations.whatsapp.lid_auth import normalize_phone
from noctusai_lib.integrations.whatsapp.types import WhatsAppGroupClient

_GRUPOS = "grupos"
_GRUPO_MEMBROS = "grupo_membros"
_MEMBROS = "membros"

_WAHA_UNREACHABLE_DETAIL = "O WhatsApp não respondeu. Tente novamente em alguns minutos."


class GruposServiceError(Exception):
    """Domain-level failure surfaced to the router as an HTTP error."""

    def __init__(self, detail: str, *, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class GruposService:
    def __init__(self, client: Any, *, org_id) -> None:
        self._client = client
        self._org_id = str(org_id)

    # ── reads ────────────────────────────────────────────────────────

    async def list(self, *, ativo: bool | None = None, page: int = 1, page_size: int = 50) -> dict:
        query = self._client.table(_GRUPOS).select("*").eq("org_id", self._org_id)
        if ativo is not None:
            query = query.eq("ativo", ativo)
        rows = query.execute().data or []
        rows.sort(key=lambda r: r.get("nome") or "")
        total = len(rows)
        start = (page - 1) * page_size
        page_rows = rows[start:start + page_size]
        return {"items": page_rows, "total": total}

    async def get(self, *, grupo_id: str) -> dict | None:
        result = (
            self._client.table(_GRUPOS).select("*")
            .eq("org_id", self._org_id).eq("id", str(grupo_id))
            .maybe_single().execute()
        )
        return result.data

    async def get_roster(self, *, grupo_id: str) -> list[dict]:
        """`grupo_membros` rows for `grupo_id`, denormalized with the
        matched member's name (`membro_nome`) and phone (`telefone`) —
        the router redacts both per D3 for a `moderador`."""
        rows = (
            self._client.table(_GRUPO_MEMBROS).select("*")
            .eq("org_id", self._org_id).eq("grupo_id", str(grupo_id))
            .execute().data or []
        )
        membro_ids = [r["membro_id"] for r in rows if r.get("membro_id")]
        membros_by_id: dict[str, dict] = {}
        if membro_ids:
            membro_rows = (
                self._client.table(_MEMBROS).select("id,nome,telefone")
                .eq("org_id", self._org_id).in_("id", membro_ids)
                .execute().data or []
            )
            membros_by_id = {str(m["id"]): m for m in membro_rows}
        out = []
        for row in rows:
            membro = membros_by_id.get(str(row.get("membro_id"))) if row.get("membro_id") else None
            out.append({
                **row,
                "membro_nome": membro.get("nome") if membro else None,
                "telefone": membro.get("telefone") if membro else None,
            })
        out.sort(key=lambda r: r.get("visto_em") or "")
        return out

    # ── writes ───────────────────────────────────────────────────────

    async def create(self, *, payload: dict, waha_client: WhatsAppGroupClient) -> dict:
        criar = payload.get("criar", False)
        nome = payload.get("nome")
        chat_id = payload.get("chat_id")

        if criar:
            if not nome:
                raise GruposServiceError(
                    "Informe um nome para criar o grupo.", status_code=422,
                )
            try:
                group_info = await waha_client.create_group(name=nome, participant_ids=[])
            except (WahaGroupError, WahaSessionNotReady) as exc:
                raise GruposServiceError(_WAHA_UNREACHABLE_DETAIL, status_code=502) from exc
            chat_id = group_info.id
            nome = group_info.name or nome
        else:
            if not chat_id:
                raise GruposServiceError(
                    "Informe o chat_id do grupo existente.", status_code=422,
                )
            if not nome:
                try:
                    group_info = await waha_client.get_group(chat_id)
                    nome = group_info.name
                except (WahaGroupError, WahaSessionNotReady):
                    nome = chat_id

        existing = (
            self._client.table(_GRUPOS).select("id")
            .eq("org_id", self._org_id).eq("chat_id", chat_id)
            .execute().data or []
        )
        if existing:
            raise GruposServiceError(
                "Esse grupo já está cadastrado.", status_code=409,
            )

        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id": str(uuid4()),
            "org_id": self._org_id,
            "nome": nome,
            "chat_id": chat_id,
            "descricao": payload.get("descricao"),
            "somente_admin": payload.get("somente_admin", False),
            "ativo": True,
            "participantes_observados": 0,
            "sincronizado_em": None,
            "created_at": now,
            "updated_at": now,
        }
        result = self._client.table(_GRUPOS).insert(row).execute()
        if not result.data:
            raise GruposServiceError("Falha ao criar grupo.")
        return result.data[0]

    async def update(self, *, grupo_id: str, payload: dict) -> dict | None:
        result = (
            self._client.table(_GRUPOS).update(payload)
            .eq("org_id", self._org_id).eq("id", str(grupo_id))
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]

    async def sincronizar_roster(
        self, *, grupo_id: str, waha_client: WhatsAppGroupClient,
    ) -> int:
        grupo = await self.get(grupo_id=grupo_id)
        if not grupo:
            raise GruposServiceError("Grupo não encontrado.", status_code=404)

        try:
            participants = await waha_client.list_participants(grupo["chat_id"])
        except (WahaGroupError, WahaSessionNotReady) as exc:
            raise GruposServiceError(_WAHA_UNREACHABLE_DETAIL, status_code=502) from exc

        # Local import — see the module docstring's rationale. Deferred
        # past both early-return branches above so a 404 / a WAHA
        # connectivity failure never depends on this in-flight seed lift.
        from noctusai_lib.integrations.whatsapp.identity import resolve_identity

        membro_rows = (
            self._client.table(_MEMBROS).select("id,telefone")
            .eq("org_id", self._org_id)
            .execute().data or []
        )
        membro_by_phone = {
            normalize_phone(m["telefone"]): m["id"]
            for m in membro_rows if m.get("telefone")
        }

        now = datetime.now(timezone.utc).isoformat()
        for participant in participants:
            identity = await resolve_identity(waha_client, participant.id)
            membro_id = membro_by_phone.get(identity.phone) if identity.phone else None
            existing = (
                self._client.table(_GRUPO_MEMBROS).select("id")
                .eq("grupo_id", str(grupo_id)).eq("participante_jid", participant.id)
                .execute().data or []
            )
            row = {
                "org_id": self._org_id,
                "grupo_id": str(grupo_id),
                "participante_jid": participant.id,
                "membro_id": membro_id,
                "papel": participant.role,
                "visto_em": now,
            }
            if existing:
                (
                    self._client.table(_GRUPO_MEMBROS).update(row)
                    .eq("id", existing[0]["id"]).execute()
                )
            else:
                row["id"] = str(uuid4())
                self._client.table(_GRUPO_MEMBROS).insert(row).execute()

        self._client.table(_GRUPOS).update({
            "participantes_observados": len(participants),
            "sincronizado_em": now,
        }).eq("org_id", self._org_id).eq("id", str(grupo_id)).execute()

        return len(participants)

    async def get_convite(self, *, grupo_id: str, waha_client: WhatsAppGroupClient) -> str:
        grupo = await self.get(grupo_id=grupo_id)
        if not grupo:
            raise GruposServiceError("Grupo não encontrado.", status_code=404)
        try:
            return await waha_client.get_invite_link(grupo["chat_id"])
        except (WahaGroupError, WahaSessionNotReady) as exc:
            raise GruposServiceError(_WAHA_UNREACHABLE_DETAIL, status_code=502) from exc

    async def revogar_convite(self, *, grupo_id: str, waha_client: WhatsAppGroupClient) -> str:
        grupo = await self.get(grupo_id=grupo_id)
        if not grupo:
            raise GruposServiceError("Grupo não encontrado.", status_code=404)
        try:
            return await waha_client.revoke_invite_link(grupo["chat_id"])
        except (WahaGroupError, WahaSessionNotReady) as exc:
            raise GruposServiceError(_WAHA_UNREACHABLE_DETAIL, status_code=502) from exc

async def get_sessao(*, waha_client: Any) -> dict:
    """Read-through `get_session` — module-level, no org/DB context needed."""
    try:
        info = await waha_client.get_session()
    except Exception as exc:  # noqa: BLE001 — session read is best-effort
        raise GruposServiceError(_WAHA_UNREACHABLE_DETAIL, status_code=502) from exc
    return {
        "estado": info.get("status") or info.get("estado") or "UNKNOWN",
        "sessao": info.get("name") or getattr(waha_client, "session", "default"),
    }
