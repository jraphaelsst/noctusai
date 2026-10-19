"""``agents.lead_identificacao`` + access audit (migration 032): Fake + Real + factory.

The store only ever holds ciphertext for CPF/RG (the service encrypts); org-scoped on every call.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import UUID

from app.qualificacao.identificacao import (
    AcessoIdentificacao,
    EncryptionNotConfigured,
    IdentCipher,
    IdentificacaoService,
    IdentificacaoStore,
    IdentRecord,
)
from app.stores._db_errors import exec_query, exec_rpc
from app.stores._util import utcnow, utcnow_iso

_SCHEMA = "agents"
_COLS = ("nome", "telefone", "email", "cpf_cifrado", "rg_cifrado", "rg_uf", "cpf_hash")


class FakeIdentificacaoStore:
    def __init__(self) -> None:
        self._rows: dict[tuple[UUID, UUID], IdentRecord] = {}
        self._acessos: list[AcessoIdentificacao] = []

    def obter(self, org_id, lead_ref_id):
        return self._rows.get((org_id, lead_ref_id))

    def salvar_campos(self, org_id, lead_ref_id, campos, *, agent_id, origem_msg_id):
        atual = self._rows.get((org_id, lead_ref_id)) or IdentRecord(org_id, lead_ref_id)
        extra: dict[str, Any] = {"coletado_em": utcnow()}
        if agent_id is not None:
            extra["coletado_por_agent_id"] = agent_id
        if origem_msg_id is not None:
            extra["origem_msg_id"] = origem_msg_id
        self._rows[(org_id, lead_ref_id)] = replace(atual, **campos, **extra)

    def registrar_acesso(self, acesso):
        self._acessos.append(acesso)

    def listar_acessos(self, org_id, lead_ref_id):
        return [a for a in self._acessos if a.org_id == org_id and a.lead_ref_id == lead_ref_id]

    def apagar_por_lead(self, org_id, lead_ref_id):
        return 1 if self._rows.pop((org_id, lead_ref_id), None) is not None else 0


class SupabaseIdentificacaoStore:
    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self, name: str):
        return self._client.schema(_SCHEMA).table(name)

    def obter(self, org_id, lead_ref_id):
        resp = (
            self._t("lead_identificacao").select("*")
            .eq("org_id", str(org_id)).eq("lead_ref_id", str(lead_ref_id)).limit(1).execute()
        )
        if not resp.data:
            return None
        r = resp.data[0]
        return IdentRecord(
            org_id=org_id, lead_ref_id=lead_ref_id, nome=r.get("nome"), telefone=r.get("telefone"),
            email=r.get("email"), cpf_cifrado=r.get("cpf_cifrado"), rg_cifrado=r.get("rg_cifrado"),
            rg_uf=r.get("rg_uf"), cpf_hash=r.get("cpf_hash"), coletado_em=r.get("coletado_em"),
            coletado_por_agent_id=UUID(str(r["coletado_por_agent_id"])) if r.get("coletado_por_agent_id") else None,
            origem_msg_id=UUID(str(r["origem_msg_id"])) if r.get("origem_msg_id") else None,
        )

    def salvar_campos(self, org_id, lead_ref_id, campos, *, agent_id, origem_msg_id):
        row: dict[str, Any] = {"org_id": str(org_id), "lead_ref_id": str(lead_ref_id), "coletado_em": utcnow_iso()}
        row.update({k: v for k, v in campos.items() if k in _COLS})
        if agent_id is not None:
            row["coletado_por_agent_id"] = str(agent_id)
        if origem_msg_id is not None:
            row["origem_msg_id"] = str(origem_msg_id)
        exec_query(self._t("lead_identificacao").upsert(row, on_conflict="lead_ref_id"))

    def registrar_acesso(self, a):
        exec_query(self._t("lead_identificacao_acessos").insert({
            "org_id": str(a.org_id), "lead_ref_id": str(a.lead_ref_id), "ator_user_id": str(a.ator_user_id),
            "campos": list(a.campos), "motivo": a.motivo,
        }))

    def listar_acessos(self, org_id, lead_ref_id):
        resp = (
            self._t("lead_identificacao_acessos").select("*").eq("org_id", str(org_id))
            .eq("lead_ref_id", str(lead_ref_id)).order("created_at").limit(1000).execute()
        )
        return [AcessoIdentificacao(org_id, lead_ref_id, UUID(str(r["ator_user_id"])), tuple(r["campos"]),
                                    r.get("motivo"), r["created_at"]) for r in resp.data or []]

    def apagar_por_lead(self, org_id, lead_ref_id):
        resp = exec_query(
            self._t("lead_identificacao").delete().eq("org_id", str(org_id)).eq("lead_ref_id", str(lead_ref_id)))
        return len(resp.data or [])


def get_identificacao_store(settings: Any) -> IdentificacaoStore:
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeIdentificacaoStore()
    from app.database import get_admin_client

    return SupabaseIdentificacaoStore(get_admin_client())


def get_identificacao_service(settings: Any) -> IdentificacaoService:
    """The service over the right store; the cipher is the fleet ``ENCRYPTION_KEY`` (None = CPF/RG writes refused)."""
    key = getattr(settings, "encryption_key", "") or None
    try:
        cipher = IdentCipher(key) if key else None
    except EncryptionNotConfigured:  # pragma: no cover - guarded by `if key`
        cipher = None
    return IdentificacaoService(get_identificacao_store(settings), cipher)
