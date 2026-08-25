"""Document retention policy — the controller's number, resolvable and editable.

WHAT THIS OWNS
--------------
One question, asked from three places: *how many days do we keep a document of
type T on surface S for org O?* The answer used to live on
`cliente_documento_tipos.retencao_dias`, which meant changing it required a
migration. Migration 079 moves it here, into a two-tier table:

    org row (org_id = O)  →  platform row (org_id IS NULL)  →  None

`None` means keep indefinitely and is a real answer, not a missing one — the
sweep skips it rather than treating it as "expire now".

🔴 THE CLOCK ANCHOR IS PART OF THE POLICY, NOT AN IMPLEMENTATION DETAIL
-----------------------------------------------------------------------
`retencao_dias` is a duration; it is meaningless without saying *from when*.
The two surfaces answer differently and the difference is legal, not stylistic:

  * `cliente` → **envio**. Stamped at upload (057's behaviour, unchanged).
  * `atendimento` → **encerramento**. Lei 9.613/98 art. 10 III sets its
    minimum "a contar da conclusão da transação"; a deal runs for months, so
    an upload anchor would expire a month-1 document a full deal-length before
    the legal minimum, silently. The clock starts at `atendimentos.closed_at`,
    and an OPEN deal's documents have no expiry at all.

`ANCORAS` names that per surface so the screen can say it out loud. A user
setting "5 anos" needs to know five years from *what*, and a UI that shows a
number without its anchor is a UI that will be misread.

🔴 THE PLATFORM TIER IS ALSO THE ALLOW-LIST
--------------------------------------------
You can only set a policy for a `(superficie, tipo_documento)` that has a
platform row. Migration 079 seeds one per known type, so a typo'd tipo is
refused by construction instead of creating an orphan policy row that nothing
would ever read — the silent-error shape this would otherwise take.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import ValidationError_

from app.services import table_reads

logger = logging.getLogger(__name__)

TABLE = "documento_retencao_politicas"

#: The surfaces that HAVE a retention clock. `imovel` is deliberately absent —
#: `imovel_documentos` (075) has no `retencao_ate` column, so offering a
#: control for it would be a lying UI. Mirrors migration 079's CHECK; the two
#: must move together.
SUPERFICIES: tuple[str, ...] = ("cliente", "atendimento")

#: What the countdown starts from, per surface. See the module header.
ANCORAS: dict[str, str] = {
    "cliente": "envio",
    "atendimento": "encerramento",
}

#: Human-facing one-liners for the screen, so the anchor is never implicit.
ANCORA_ROTULOS: dict[str, str] = {
    "envio": "a partir do envio do documento",
    "encerramento": "a partir do encerramento do atendimento",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── reads ────────────────────────────────────────────────────────────


def _linhas(client: Any, org_id: UUID) -> list[dict]:
    """Every policy row visible to this org — its own AND the platform tier.

    🔴 TWO READS, NOT ONE `.or_()`. A single
    `or_("org_id.is.null,org_id.eq.<id>")` would be one round trip against a
    real PostgREST — but the test mock records `or_` as a synthetic match-all
    predicate (it does not parse the expression), so under test it would hand
    back EVERY org's rows and the tier resolution below would silently treat a
    neighbouring org's override as this org's. The bug would be invisible
    exactly where a test should have caught it. Two exactly-expressible reads
    against a table with a handful of rows is the cheaper mistake.
    """
    padrao = (
        table_reads.table(client, TABLE)
        .select("*")
        .is_("org_id", "null")
        .execute()
    ).data or []
    proprio = (
        table_reads.table(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .execute()
    ).data or []
    return [*padrao, *proprio]


def politicas(client: Any, org_id: UUID) -> list[dict]:
    """The effective policy for every known type, newest-surface-first.

    Each entry carries BOTH the effective value and the platform default it
    came from, plus `personalizado` — the screen needs all three to render
    "5 anos (padrão: 10 anos) · Restaurar padrão" without a second request.
    """
    rows = _linhas(client, org_id)
    padroes: dict[tuple[str, str], dict] = {}
    overrides: dict[tuple[str, str], dict] = {}
    for row in rows:
        chave = (row["superficie"], row["tipo_documento"])
        (padroes if row.get("org_id") is None else overrides)[chave] = row

    saida: list[dict] = []
    for chave, padrao in padroes.items():
        superficie, tipo = chave
        override = overrides.get(chave)
        efetiva = override if override is not None else padrao
        ancora = ANCORAS[superficie]
        saida.append(
            {
                "superficie": superficie,
                "tipo_documento": tipo,
                "retencao_dias": efetiva.get("retencao_dias"),
                "padrao_dias": padrao.get("retencao_dias"),
                "personalizado": override is not None,
                "motivo": efetiva.get("motivo"),
                "padrao_motivo": padrao.get("motivo"),
                "ancora": ancora,
                "ancora_rotulo": ANCORA_ROTULOS[ancora],
                "atualizado_em": efetiva.get("atualizado_em"),
                "atualizado_por": efetiva.get("atualizado_por"),
            }
        )
    saida.sort(key=lambda p: (SUPERFICIES.index(p["superficie"]), p["tipo_documento"]))
    return saida


def dias_para(
    client: Any, org_id: UUID, superficie: str, tipo_documento: str
) -> Optional[int]:
    """The effective retention in days, or `None` for "keep indefinitely".

    🔴 `None` is returned BOTH when the policy says keep-forever and when no
    policy row exists for this type at all. That collapse is deliberate and
    safe in one direction only: the worst case is a document kept longer than
    intended, never one deleted earlier. The reverse default would delete
    files because a seed row was missing.
    """
    melhor: Optional[dict] = None
    for row in _linhas(client, org_id):
        if row["superficie"] != superficie or row["tipo_documento"] != tipo_documento:
            continue
        # An org row always wins; a platform row only fills in.
        if row.get("org_id") is not None:
            return row.get("retencao_dias")
        melhor = row
    return melhor.get("retencao_dias") if melhor else None


# ─── writes ───────────────────────────────────────────────────────────


def _exigir_conhecido(client: Any, superficie: str, tipo_documento: str) -> None:
    """Refuse a policy for a type that has no platform row.

    The platform tier IS the allow-list (module header). Without this, a typo
    writes a row nothing ever reads — a policy the user believes they set.
    """
    if superficie not in SUPERFICIES:
        raise ValidationError_(
            f"superfície desconhecida: {superficie!r}. "
            f"Permitidas: {', '.join(SUPERFICIES)}",
            field="superficie",
        )
    conhecidos = [
        r["tipo_documento"]
        for r in (
            table_reads.table(client, TABLE)
            .select("tipo_documento")
            .is_("org_id", "null")
            .eq("superficie", superficie)
            .execute()
        ).data
        or []
    ]
    if tipo_documento not in conhecidos:
        raise ValidationError_(
            f"tipo_documento desconhecido para {superficie}: {tipo_documento!r}. "
            f"Permitidos: {', '.join(sorted(conhecidos))}",
            field="tipo_documento",
        )


def definir(
    client: Any,
    org_id: UUID,
    superficie: str,
    tipo_documento: str,
    retencao_dias: Optional[int],
    *,
    usuario_id: Optional[UUID] = None,
    motivo: Optional[str] = None,
) -> dict:
    """Write (or replace) this org's override for one type.

    `retencao_dias=None` is a legitimate choice — "keep indefinitely" — and is
    stored as an override row rather than by deleting the org row, because
    "the controller decided to keep these forever" and "the controller never
    touched this" are different facts and an audit will ask which one it is.
    Use `restaurar` for the second.
    """
    _exigir_conhecido(client, superficie, tipo_documento)
    if retencao_dias is not None and retencao_dias < 1:
        raise ValidationError_(
            "retencao_dias deve ser 1 ou mais; use null para manter "
            "indefinidamente.",
            field="retencao_dias",
        )

    patch = {
        "retencao_dias": retencao_dias,
        "motivo": motivo,
        "atualizado_em": _now_iso(),
        "atualizado_por": str(usuario_id) if usuario_id else None,
    }
    existente = (
        table_reads.table(client, TABLE)
        .select("id")
        .eq("org_id", str(org_id))
        .eq("superficie", superficie)
        .eq("tipo_documento", tipo_documento)
        .execute()
    ).data or []
    if existente:
        table_reads.table(client, TABLE).update(patch).eq(
            "id", existente[0]["id"]
        ).execute()
    else:
        table_reads.table(client, TABLE).insert(
            {
                "org_id": str(org_id),
                "superficie": superficie,
                "tipo_documento": tipo_documento,
                "created_at": _now_iso(),
                **patch,
            }
        ).execute()
    return {"superficie": superficie, "tipo_documento": tipo_documento, **patch}


def restaurar(
    client: Any, org_id: UUID, superficie: str, tipo_documento: str
) -> None:
    """Drop this org's override so the platform default applies again.

    A hard DELETE, not a null-out: the absence of a row is exactly what
    `politicas` reads as "not customised", and writing a row with a copy of
    the default would make the screen claim a decision nobody made.
    """
    _exigir_conhecido(client, superficie, tipo_documento)
    table_reads.table(client, TABLE).delete().eq("org_id", str(org_id)).eq(
        "superficie", superficie
    ).eq("tipo_documento", tipo_documento).execute()


__all__ = [
    "ANCORAS",
    "ANCORA_ROTULOS",
    "SUPERFICIES",
    "TABLE",
    "definir",
    "dias_para",
    "politicas",
    "restaurar",
]
