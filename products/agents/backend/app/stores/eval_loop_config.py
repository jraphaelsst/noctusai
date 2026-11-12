"""Eval-loop config store (migration 086): the three platform values in ``agents.runtime_settings`` + the
``loop_config_alterada`` events. Reads are plain selects; the write is ONE RPC (``agents.set_eval_loop_config``) so the
values and their event land in one transaction.

Seed IO shape: ``EvalLoopConfigStore`` Protocol + ``FakeEvalLoopConfigStore`` + ``SupabaseEvalLoopConfigStore`` + factory.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.stores._db_errors import exec_rpc
from app.stores._util import db_ts, utcnow
from app.studio.eval_loop_config import KEYS, EvalLoopConfig

__all__ = ["ConfigRegistrada", "EvalLoopConfigStore", "FakeEvalLoopConfigStore", "SupabaseEvalLoopConfigStore",
           "get_eval_loop_config_store"]

_SCHEMA = "agents"


@dataclass(frozen=True)
class ConfigRegistrada:
    config: EvalLoopConfig
    alterado_por: UUID | None = None
    alterado_em: datetime | None = None


class EvalLoopConfigStore(Protocol):
    def get(self) -> ConfigRegistrada:
        """The effective config: stored values, the code defaults for any key never stored."""
        ...

    def set(self, config: EvalLoopConfig, *, actor: UUID | None) -> ConfigRegistrada:
        """Store the three values and record a ``loop_config_alterada`` event (nothing recorded when unchanged)."""
        ...


class FakeEvalLoopConfigStore:
    def __init__(self, config: EvalLoopConfig | None = None) -> None:
        self._rec = ConfigRegistrada(config or EvalLoopConfig())
        #: ``(evento, antes, depois, actor)`` per change, the rows the RPC appends.
        self.eventos: list[tuple[str, dict[str, Any], dict[str, Any], UUID | None]] = []

    def get(self) -> ConfigRegistrada:
        return self._rec

    def set(self, config: EvalLoopConfig, *, actor: UUID | None) -> ConfigRegistrada:
        antes = self._rec.config
        if config != antes:
            self.eventos.append((
                "loop_config_alterada", {k: getattr(antes, k) for k in KEYS}, {k: getattr(config, k) for k in KEYS}, actor))
        self._rec = ConfigRegistrada(config, actor, utcnow())
        return self._rec


class SupabaseEvalLoopConfigStore:
    def __init__(self, client: Any) -> None:
        self._client = client

    def get(self) -> ConfigRegistrada:
        rows = (self._client.schema(_SCHEMA).table("runtime_settings").select("key, value, updated_by, updated_at")
                .in_("key", list(KEYS.values())).execute().data or [])
        por_chave = {r["key"]: r for r in rows}
        padrao = EvalLoopConfig()

        def val(campo: str, tipo: type, default: Any) -> Any:
            row = por_chave.get(KEYS[campo])
            return tipo(row["value"]) if row is not None else default

        cfg = EvalLoopConfig(
            alvo=val("alvo", float, padrao.alvo), orcamento_usd=val("orcamento_usd", float, padrao.orcamento_usd),
            rodadas_max=val("rodadas_max", int, padrao.rodadas_max))
        ultimo = max(rows, key=lambda r: r["updated_at"], default=None)
        return ConfigRegistrada(
            cfg, UUID(str(ultimo["updated_by"])) if ultimo and ultimo.get("updated_by") else None,
            db_ts(ultimo["updated_at"]) if ultimo else None)

    def set(self, config: EvalLoopConfig, *, actor: UUID | None) -> ConfigRegistrada:
        exec_rpc(self._client, _SCHEMA, "set_eval_loop_config", {
            "p_alvo": config.alvo, "p_orcamento_usd": config.orcamento_usd, "p_rodadas_max": config.rodadas_max,
            "p_actor": str(actor) if actor else None})
        return self.get()


def get_eval_loop_config_store(settings: Any) -> EvalLoopConfigStore:
    """Real when a service-role key is configured, Fake otherwise (same signal as every agents store)."""
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeEvalLoopConfigStore()
    from app.database import get_admin_client

    return SupabaseEvalLoopConfigStore(get_admin_client())
