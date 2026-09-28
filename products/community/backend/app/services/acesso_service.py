"""What a member may do right now — the single tier resolver (CONTRACT.md §Tiers).

The `membros` row is the source of truth for access: billing writes keep
`membros.plano_id` + `membros.status` current (a paid charge sets the
plan; the billing sweep moves an expired or ended subscription back to
the free plan). Every gate — the portal, grupoterapia, the dashboard's
"members by tier" — asks this module instead of re-deriving it.

Access is kept during `atrasado` on purpose: that is the grace window
(`assinaturas.estado = 'carencia'`), and the user decided members keep
access while a late payment can still come in.
"""
from __future__ import annotations

from typing import Any, Literal

NivelGrupoterapia = Literal["nenhum", "ouvir", "falar"]

#: Member statuses that keep the plan's entitlements.
STATUS_COM_ACESSO: frozenset[str] = frozenset({"ativo", "atrasado"})

_NIVEL_ORDEM: dict[str, int] = {"nenhum": 0, "ouvir": 1, "falar": 2}


def nivel_grupoterapia(membro: dict[str, Any], plano: dict[str, Any] | None) -> NivelGrupoterapia:
    """The member's grupoterapia level: `nenhum`, `ouvir` or `falar`.

    `plano` is the row for `membro["plano_id"]` (None when the member has
    no plan). A plan whose entitlements predate the field reads as
    `nenhum` — the least privilege, never an implied upgrade.
    """
    if not plano or membro.get("status") not in STATUS_COM_ACESSO:
        return "nenhum"
    nivel = (plano.get("entitlements") or {}).get("grupoterapia", "nenhum")
    if nivel not in _NIVEL_ORDEM:
        raise ValueError(f"plano {plano.get('id')}: grupoterapia inválido {nivel!r}")
    return nivel  # type: ignore[return-value]


def pode(nivel: NivelGrupoterapia, exigido: NivelGrupoterapia) -> bool:
    """True when `nivel` covers `exigido` (falar ⊇ ouvir ⊇ nenhum)."""
    return _NIVEL_ORDEM[nivel] >= _NIVEL_ORDEM[exigido]
