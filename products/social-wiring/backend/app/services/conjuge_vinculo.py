"""THE choke point for `clientes.conjuge_cliente_id` links.

Three paths write that column — `compradores_service._casar` (the "cônjuge"
role on a party), `identidade_extracao_service` (a spouse read off a
document) and the generic cliente PATCH (`clientes_service.update_cliente`).
Each keeps its own policy (who may overwrite whom, provenance, admin gating);
what they share, and what lives ONLY here, is the consequence of a link:
CONTRACT sw-lead-to-contract §7.1 — a cônjuge linked to a seller of an
already-accepted deal is certified now (`pos_aceite_service.ao_vincular_conjuge`).

* `vincular_conjuge` — writes one side of the link (+ the caller's provenance
  columns) and then runs the consequence.
* `apos_vincular_conjuge` — the consequence alone, for a path whose write is
  bundled into a larger UPDATE (the PATCH).

Never raises from the consequence: the link has already landed.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from app.services import table_reads

logger = logging.getLogger(__name__)

CLIENTES = "clientes"


def apos_vincular_conjuge(
    client: Any, org_id: Any, cliente_id: Any, conjuge_cliente_id: Any, *, actor: Any = None
) -> None:
    """The late-spouse consequence (see the module docstring). Lazy import:
    `card_hub` imports this package's services."""
    try:
        from app.modules.card_hub import pos_aceite_service

        pos_aceite_service.ao_vincular_conjuge(
            client, org_id, cliente_id, conjuge_cliente_id, actor=actor
        )
    except Exception as exc:  # noqa: BLE001 - the link landed; logged at ERROR, never raised
        logger.error("vínculo de cônjuge: pós-aceite falhou: %s", exc, exc_info=True)


def vincular_conjuge(
    client: Any,
    org_id: Any,
    cliente_id: Any,
    conjuge_cliente_id: Any,
    *,
    campos: Optional[dict] = None,
    actor: Any = None,
) -> None:
    """Write `cliente_id.conjuge_cliente_id = conjuge_cliente_id` (+ `campos`,
    the caller's own provenance columns), then run the consequence. ONE side —
    a marriage is symmetric, so the caller calls it for both."""
    patch = {"conjuge_cliente_id": str(conjuge_cliente_id), **(campos or {})}
    (
        table_reads.table(client, CLIENTES)
        .update(patch)
        .eq("id", str(cliente_id))
        .eq("org_id", str(org_id))
        .execute()
    )
    apos_vincular_conjuge(client, org_id, cliente_id, conjuge_cliente_id, actor=actor)
