"""Renata cutover seam (agents-unified): move a code-defined agent's in-app history onto a Studio agent, and retire
the code-defined rows of a key so the key is free.

The Real store is the 053 SECURITY DEFINER functions over ``.rpc()`` -- one call = one Postgres transaction, so a
transfer either moves every conversation (and with them every message / approval / transcript row, which hang off
the conversation) plus the bound ``agents.api_tokens`` and writes the definition audit row, or nothing. The Fake
applies the same rules over the in-memory stores the router suites share.

Runbook: ``products/agents/projects/agents-unified/RENATA-CUTOVER.md``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from app.stores._db_errors import StudioConflict, exec_rpc
from app.stores.errors import NotFound

__all__ = [
    "ContagemTransferencia",
    "ResultadoArquivamento",
    "CutoverStore",
    "FakeCutoverStore",
    "SupabaseCutoverStore",
    "get_cutover_store",
]

_SCHEMA = "agents"


@dataclass(frozen=True)
class ContagemTransferencia:
    """What a transfer moves (or, on a dry run, would move). ``executado`` is true only when rows were written."""

    conversas: int
    mensagens: int
    aprovacoes: int
    transcricoes: int
    tokens: int
    executado: bool
    #: academia_de_reciclagem.api_tokens rows re-bound (the academia principal); 0 where academia is absent.
    tokens_academia: int = 0

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ContagemTransferencia":
        return cls(
            conversas=int(row.get("conversas", 0)), mensagens=int(row.get("mensagens", 0)),
            aprovacoes=int(row.get("aprovacoes", 0)), transcricoes=int(row.get("transcricoes", 0)),
            tokens=int(row.get("tokens", 0)), executado=bool(row.get("executado", False)),
            tokens_academia=int(row.get("tokens_academia", 0)),
        )


@dataclass(frozen=True)
class ResultadoArquivamento:
    linhas: int
    com_historico: int
    executado: bool

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ResultadoArquivamento":
        return cls(
            linhas=int(row.get("linhas", 0)), com_historico=int(row.get("com_historico", 0)),
            executado=bool(row.get("executado", False)),
        )


class CutoverStore(Protocol):
    def transferir_historico(
        self, org_id: UUID, source_id: UUID, target_id: UUID, *, actor: UUID | None, executar: bool,
    ) -> ContagemTransferencia:
        """053 ``agents.transferir_historico_agente``. Raises ``StudioConflict`` ``origem_invalida`` /
        ``destino_invalido`` / ``mesmo_agente``."""
        ...

    def arquivar_legado(
        self, key: str, org_id: UUID | None, *, actor: UUID | None, executar: bool,
    ) -> ResultadoArquivamento:
        """053 ``agents.arquivar_agente_legado`` (``org_id=None`` = every org). Raises ``StudioConflict``
        ``historico_pendente`` when executing while a row still owns a conversation."""
        ...


def _unwrap(data: Any) -> dict[str, Any]:
    """A PostgREST ``jsonb`` RPC answer is the object itself (or, on some client versions, a 1-row list)."""
    if isinstance(data, list):
        data = data[0] if data else {}
    return data if isinstance(data, dict) else {}


class SupabaseCutoverStore:
    def __init__(self, client: Any) -> None:
        self._client = client

    def transferir_historico(self, org_id, source_id, target_id, *, actor, executar) -> ContagemTransferencia:
        resp = exec_rpc(self._client, _SCHEMA, "transferir_historico_agente", {
            "p_org_id": str(org_id), "p_source_id": str(source_id), "p_target_id": str(target_id),
            "p_actor": str(actor) if actor else None, "p_executar": bool(executar),
        })
        return ContagemTransferencia.from_row(_unwrap(resp.data))

    def arquivar_legado(self, key, org_id, *, actor, executar) -> ResultadoArquivamento:
        resp = exec_rpc(self._client, _SCHEMA, "arquivar_agente_legado", {
            "p_key": key, "p_org_id": str(org_id) if org_id else None,
            "p_actor": str(actor) if actor else None, "p_executar": bool(executar),
        })
        return ResultadoArquivamento.from_row(_unwrap(resp.data))


class FakeCutoverStore:
    """The 053 rules over the shared Fakes: ``agents`` (the code-defined rows), ``studio`` (the Studio rows + the
    audit log), ``conversations`` / ``messages`` / ``approvals`` (the history). Tokens are not modelled (0)."""

    def __init__(self, *, agents: Any, studio: Any, conversations: Any, messages: Any, approvals: Any) -> None:
        self._agents = agents
        self._studio = studio
        self._conversations = conversations
        self._messages = messages
        self._approvals = approvals

    def _legacy_row(self, org_id: UUID, agent_id: UUID) -> dict[str, Any] | None:
        for (o, _), row in self._agents._rows.items():
            if o == org_id and row["id"] == agent_id:
                return row
        return None

    def _conversas_de(self, org_id: UUID, agent_id: UUID) -> list[dict[str, Any]]:
        return [r for r in self._conversations._rows.values() if r["org_id"] == org_id and r["agent_id"] == agent_id]

    def transferir_historico(self, org_id, source_id, target_id, *, actor, executar) -> ContagemTransferencia:
        if source_id == target_id:
            raise StudioConflict("mesmo_agente", "transferir_mesmo_agente")
        src = self._legacy_row(org_id, source_id)
        if src is None or src.get("definition_mode", "legacy") not in ("legacy", "arquivado"):
            raise StudioConflict("origem_invalida", "transferir_origem_invalida")
        try:
            tgt = self._studio.get_agent_by_id(target_id)
        except NotFound:
            tgt = None
        if tgt is None or tgt.org_id != org_id or tgt.definition_mode != "studio":
            raise StudioConflict("destino_invalido", "transferir_destino_invalido")
        conversas = self._conversas_de(org_id, source_id)
        ids = {r["id"] for r in conversas}
        mensagens = sum(len(rows) for (o, cid), rows in self._messages._rows.items() if o == org_id and cid in ids)
        aprovacoes = sum(1 for a in self._approvals._rows.values() if a.get("conversation_id") in ids)
        escreve = bool(executar) and len(conversas) > 0
        contagem = ContagemTransferencia(len(conversas), mensagens, aprovacoes, 0, 0, escreve)
        if escreve:
            for r in conversas:
                r["agent_id"] = target_id
            self._studio.append_audit(
                org_id, target_id, actor, "historico_transferido",
                {"de_key": src["key"], "de_agent_id": str(source_id)},
                {"conversas": contagem.conversas, "mensagens": mensagens, "aprovacoes": aprovacoes,
                 "transcricoes": 0, "tokens": 0, "para_key": tgt.key},
            )
        return contagem

    def arquivar_legado(self, key, org_id, *, actor, executar) -> ResultadoArquivamento:
        alvos = [
            (k, row) for k, row in self._agents._rows.items()
            if row["key"] == key and row.get("definition_mode", "legacy") == "legacy"
            and (org_id is None or row["org_id"] == org_id)
        ]
        com_historico = sum(1 for _, row in alvos if self._conversas_de(row["org_id"], row["id"]))
        if executar and com_historico:
            raise StudioConflict("historico_pendente", "arquivar_historico_pendente")
        if executar:
            for k, row in alvos:
                nova = f"{row['key']}-arquivado-{str(row['id'])[:8]}"
                antes = {"key": row["key"], "definition_mode": "legacy", "ativo": row["ativo"]}
                del self._agents._rows[k]
                self._agents._rows[(row["org_id"], nova)] = {
                    **row, "key": nova, "definition_mode": "arquivado", "ativo": False,
                }
                self._studio._audit_append(
                    row["org_id"], row["id"], actor, "agente_arquivado", antes,
                    {"key": nova, "definition_mode": "arquivado", "ativo": False},
                )
        return ResultadoArquivamento(len(alvos), com_historico, bool(executar) and bool(alvos))


def get_cutover_store(settings: Any) -> CutoverStore:
    if not getattr(settings, "supabase_service_role_key", None):
        raise RuntimeError("cutover store needs SUPABASE_SERVICE_ROLE_KEY (no in-memory history to move)")
    from app.database import get_admin_client

    return SupabaseCutoverStore(get_admin_client())


