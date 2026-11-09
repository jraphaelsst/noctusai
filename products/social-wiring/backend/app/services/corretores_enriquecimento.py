"""Enrich `lead_corretores` from the property's Vista `Corretor` relation (owner 2026-11-09).

`/corretores/listar` ignores `fields` and answers only Codigo+Nome on this tenant, so a broker's team and roles reach us ONLY through the
`Corretor` relation of a property detail (Nome, Codigo, Agenciador, Gerente, Corretor, Equipe, Email, Fone). Whenever a property is read (the
Vista sync, the ad-lead intake) each relation entry whose Codigo matches a `lead_corretores.vista_codigo` fills that row's EMPTY columns:
equipe, gerente, agenciador, eh_corretor, email, celular (<- Fone). Never overwrites a non-null value, never writes a null, never creates
a broker (the roster sync owns creation) and stamps `campos_origem='imovel_relacao'` only when something was filled.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable
from uuid import UUID

logger = logging.getLogger(__name__)

ORIGEM = "imovel_relacao"
#: lead_corretores column <- the relation entry's key (works for the seed `Corretor` model dump and for the raw dict).
_CAMPOS = (("equipe", "equipe"), ("gerente", "gerente"), ("agenciador", "agenciador"), ("eh_corretor", "eh_corretor"), ("email", "email"), ("celular", "fone"))


def _valor(entrada: Any, chave: str) -> Any:
    v = entrada.get(chave) if isinstance(entrada, dict) else getattr(entrada, chave, None)
    return None if v in (None, "") else v


def enriquecer(db: Any, org_id: UUID | str, corretores: Iterable[Any]) -> list[str]:
    """Fill empty broker columns from relation entries. `db` has `.table(...)` on the social_wiring schema. Returns the broker ids changed."""
    entradas = [c for c in corretores if _valor(c, "codigo")]
    if not entradas:
        return []
    rows = db.table("lead_corretores").select("*").eq("org_id", str(org_id)).execute().data or []
    por_codigo = {str(r["vista_codigo"]): r for r in rows if r.get("vista_codigo")}
    alterados: list[str] = []
    for e in entradas:
        alvo = por_codigo.get(str(_valor(e, "codigo")).strip())
        if alvo is None:
            continue
        patch = {col: _valor(e, chave) for col, chave in _CAMPOS if alvo.get(col) is None and _valor(e, chave) is not None}
        if not patch:
            continue
        patch["campos_origem"] = ORIGEM
        db.table("lead_corretores").update(patch).eq("org_id", str(org_id)).eq("id", str(alvo["id"])).execute()
        alvo.update(patch)
        alterados.append(str(alvo["id"]))
    return alterados


__all__ = ["ORIGEM", "enriquecer"]
