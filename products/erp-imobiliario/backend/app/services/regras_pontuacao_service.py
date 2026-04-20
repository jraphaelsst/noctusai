"""
Regras Pontuação Service — CRUD + rule resolution for point scoring.

Rules have a three-tier precedence:
    period-specific (vigencia_periodo_id set) → org default (org_id set, period NULL)
    → platform default (both NULL)

The `resolve_rule()` helper returns the winning rule for a given
(org_id, period_id, evento_tipo, modalidade) tuple, falling back through
the chain. This is the single lookup used by the Phase 5 event triggers.

See products/erp-imobiliario/METAS-PLAN.md §5.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

logger = logging.getLogger(__name__)

VALID_EVENTOS = {"captacao", "visita", "venda", "locacao", "reuniao"}
VALID_MODALIDADES = {"padrao", "compartilhada", "exclusividade"}


# ── CRUD ─────────────────────────────────────────────────────────────

def listar_regras(db, *, org_id: str | None = None,
                  periodo_id: str | None = None,
                  evento_tipo: str | None = None,
                  incluir_defaults: bool = True) -> list[dict]:
    """List point rules visible to the caller.

    When `org_id` is given and `incluir_defaults` is True, platform
    defaults (org_id NULL) are also returned so the UI can render the
    full effective rule set.
    """
    query = db.table("regras_pontuacao").select("*")
    if evento_tipo:
        query = query.eq("evento_tipo", evento_tipo)
    if periodo_id is not None:
        query = query.eq("vigencia_periodo_id", periodo_id)
    if org_id and not incluir_defaults:
        query = query.eq("org_id", org_id)
    elif org_id and incluir_defaults:
        # caller-side filter below since .or_ is driver-specific
        pass
    result = query.order("evento_tipo").execute()
    rows = result.data or []
    if org_id and incluir_defaults:
        rows = [r for r in rows if r.get("org_id") in (None, org_id)]
    return rows


def obter_regra(db, regra_id: str) -> dict | None:
    result = db.table("regras_pontuacao").select("*").eq("id", regra_id).limit(1).execute()
    return (result.data or [None])[0]


def upsert_regra(db, *, org_id: str | None, evento_tipo: str,
                 modalidade: str = "padrao", pontos: float,
                 vigencia_periodo_id: str | None = None,
                 descricao: str | None = None) -> dict:
    """Insert or update a rule. Uniqueness is (org_id, vigencia_periodo_id, evento_tipo, modalidade)."""
    if evento_tipo not in VALID_EVENTOS:
        raise ValueError(f"evento_tipo inválido: {evento_tipo}")
    if modalidade not in VALID_MODALIDADES:
        raise ValueError(f"modalidade inválida: {modalidade}")

    existing = (
        db.table("regras_pontuacao").select("*")
        .eq("evento_tipo", evento_tipo)
        .eq("modalidade", modalidade)
    )
    # Match NULL vs value for org_id
    if org_id is None:
        existing = existing.is_("org_id", "null")
    else:
        existing = existing.eq("org_id", org_id)
    if vigencia_periodo_id is None:
        existing = existing.is_("vigencia_periodo_id", "null")
    else:
        existing = existing.eq("vigencia_periodo_id", vigencia_periodo_id)

    existing_row = (existing.limit(1).execute().data or [None])[0]

    payload: dict[str, Any] = {
        "org_id": org_id,
        "vigencia_periodo_id": vigencia_periodo_id,
        "evento_tipo": evento_tipo,
        "modalidade": modalidade,
        "pontos": pontos,
        "descricao": descricao,
    }
    if existing_row:
        result = db.table("regras_pontuacao").update(payload).eq("id", existing_row["id"]).execute()
    else:
        result = db.table("regras_pontuacao").insert(payload).execute()
    if not result.data:
        raise RuntimeError("Falha ao salvar regra de pontuação")
    return result.data[0]


def atualizar_regra(db, regra_id: str, patch: dict) -> dict:
    clean = {k: v for k, v in patch.items() if v is not None}
    if not clean:
        existing = obter_regra(db, regra_id)
        if existing is None:
            raise LookupError("Regra não encontrada")
        return existing
    if "evento_tipo" in clean and clean["evento_tipo"] not in VALID_EVENTOS:
        raise ValueError(f"evento_tipo inválido: {clean['evento_tipo']}")
    if "modalidade" in clean and clean["modalidade"] not in VALID_MODALIDADES:
        raise ValueError(f"modalidade inválida: {clean['modalidade']}")
    result = db.table("regras_pontuacao").update(clean).eq("id", regra_id).execute()
    if not result.data:
        raise LookupError("Regra não encontrada")
    return result.data[0]


def deletar_regra(db, regra_id: str) -> None:
    result = db.table("regras_pontuacao").delete().eq("id", regra_id).execute()
    if not result.data:
        raise LookupError("Regra não encontrada")


# ── Rule resolution (the hot path for event triggers) ───────────────

def resolve_rule(db, *, org_id: str | None, periodo_id: str | None,
                 evento_tipo: str, modalidade: str = "padrao") -> dict | None:
    """Return the winning rule for (org, period, event, modality).

    Precedence:
      1. Period-specific rule for the org (vigencia_periodo_id = periodo_id, org_id = org_id)
      2. Period-specific rule at platform level (vigencia_periodo_id = periodo_id, org_id NULL)
      3. Org default (vigencia_periodo_id NULL, org_id = org_id)
      4. Platform default (both NULL)
    """
    if evento_tipo not in VALID_EVENTOS:
        raise ValueError(f"evento_tipo inválido: {evento_tipo}")
    if modalidade not in VALID_MODALIDADES:
        raise ValueError(f"modalidade inválida: {modalidade}")

    # Fetch all candidate rules for this event×modality and filter in Python —
    # cheaper than 4 separate queries and lets us pick deterministically.
    query = (
        db.table("regras_pontuacao").select("*")
        .eq("evento_tipo", evento_tipo)
        .eq("modalidade", modalidade)
    )
    rows = query.execute().data or []

    def matches(r: dict, _org: str | None, _period: str | None) -> bool:
        return r.get("org_id") == _org and r.get("vigencia_periodo_id") == _period

    # Try in precedence order
    for org_candidate, period_candidate in [
        (org_id, periodo_id),
        (None, periodo_id),
        (org_id, None),
        (None, None),
    ]:
        for r in rows:
            if matches(r, org_candidate, period_candidate):
                return r
    return None
