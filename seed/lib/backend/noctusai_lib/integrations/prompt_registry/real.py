"""Real :class:`PromptRegistry` -- ``public.plataforma_agentes`` / ``public.plataforma_agente_chamadas`` through a
SERVICE-ROLE client targeting the ``public`` schema (``DatabaseModule.get_core_client``). Both tables are service-role
only (RLS on, no grant to anon/authenticated): a product reaches the registry here or not at all; nothing is shipped to
a frontend."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import UUID

from .types import ESTATISTICAS_JANELA, ChamadaMedida, ChaveNaoEncontrada, PromptEntry, calcular_estatisticas

__all__ = ["SupabasePromptRegistry"]

TABELA = "plataforma_agentes"
TABELA_CHAMADAS = "plataforma_agente_chamadas"
_COLS = "chave, nome, descricao, vendor, modelo, prompt, ativo, capacidade, atualizado_em, atualizado_por"


def _ts(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _map(row: dict) -> PromptEntry:
    return PromptEntry(
        chave=row["chave"], nome=row["nome"], descricao=row.get("descricao") or "", vendor=row["vendor"],
        modelo=row["modelo"], prompt=row["prompt"], ativo=bool(row["ativo"]), capacidade=row.get("capacidade") or "chat", atualizado_em=_ts(row.get("atualizado_em")),
        atualizado_por=UUID(str(row["atualizado_por"])) if row.get("atualizado_por") else None,
    )


# NOC-REMEDIATE[transition-log-primitive]: prompt/model edit history -> the seed transition-log primitive
# (transition_log_migration(TransitionLogConfig(...))); today only the current row is kept — 2026-11-08
class SupabasePromptRegistry:
    def __init__(self, core_client_factory: Callable[[], Any]) -> None:
        self._client_factory = core_client_factory

    def listar(self) -> list[PromptEntry]:
        rows = self._client_factory().table(TABELA).select(_COLS).order("chave").execute().data or []
        return [_map(r) for r in rows]

    def obter(self, chave: str) -> PromptEntry:
        rows = self._client_factory().table(TABELA).select(_COLS).eq("chave", chave).limit(1).execute().data or []
        if not rows:
            raise ChaveNaoEncontrada(chave)
        return _map(rows[0])

    def atualizar(
        self, chave: str, *, prompt: Optional[str] = None, modelo: Optional[str] = None,
        vendor: Optional[str] = None, actor: Optional[UUID] = None,
    ) -> PromptEntry:
        patch: dict[str, Any] = {
            "atualizado_em": datetime.now(timezone.utc).isoformat(), "atualizado_por": str(actor) if actor else None,
        }
        for k, v in (("prompt", prompt), ("modelo", modelo), ("vendor", vendor)):
            if v is not None:
                patch[k] = v
        rows = self._client_factory().table(TABELA).update(patch).eq("chave", chave).execute().data or []
        if not rows:
            raise ChaveNaoEncontrada(chave)
        return _map(rows[0])

    def registrar_chamada(self, chamada: ChamadaMedida) -> None:
        self._client_factory().table(TABELA_CHAMADAS).insert({
            "chave": chamada.chave, "vendor": chamada.vendor, "modelo": chamada.modelo,
            "capacidade": chamada.capacidade, "tokens_entrada": chamada.tokens_entrada,
            "tokens_saida": chamada.tokens_saida, "custo_usd": chamada.custo_usd, "latencia_ms": chamada.latencia_ms,
            "ok": chamada.ok, "erro": (chamada.erro or None) and chamada.erro[:200],
        }).execute()

    def estatisticas(self, chave: str) -> list[dict]:
        rows = (
            self._client_factory().table(TABELA_CHAMADAS).select("vendor, modelo, custo_usd, latencia_ms, ok")
            .eq("chave", chave).order("criado_em", desc=True).limit(ESTATISTICAS_JANELA).execute().data or []
        )
        return calcular_estatisticas(rows)
