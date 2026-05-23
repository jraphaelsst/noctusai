"""Single gated read path for portal-facing ``documentos``.

LGPD gate (Art. 5 + Art. 11 + Art. 18): the public client portal must only
ever surface documents an admin has explicitly opted in via
``compartilhado_portal = true`` (default FALSE — migration
``031_documentos_compartilhado_portal.sql``). Without this filter the portal
leaks every document for the cliente.

There are two public portal read paths into ``documentos`` — the bearer-token
router (``portal_externo.portal_documentos``) and the client dashboard
(``portal_cliente_service.PortalClienteService.get_dashboard``). Both must
apply the SAME gate, so the gate lives HERE in one place; a third portal
surface inherits the gate by calling this helper instead of re-deriving it.

The gate is NEVER optional: there is intentionally no ``include_unshared``
escape hatch. An escape hatch would reintroduce the exact leak class this
helper exists to prevent (the original P0 missed the dashboard path and
leaked ALL client docs).
"""
from typing import Any, Dict, List, Optional


def fetch_shared_documentos(
    db,
    cliente_id: str,
    org_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return the cliente's documents that are shared to the portal.

    Performs the gated read:
    ``select(*).eq("cliente_id", ...).eq("compartilhado_portal", True)``,
    optionally scoped by ``org_id`` and capped by ``limit``, ordered by
    ``created_at`` descending. The ``compartilhado_portal = True`` gate is
    mandatory and cannot be turned off — that is the whole point of routing
    both portal read paths through this single function.

    Args:
        db: A Supabase client (``admin`` / service-role for portal access).
        cliente_id: The portal cliente whose documents are being read.
        org_id: When provided (truthy), scopes the read to the org. Callers
            that always have an org pass it unconditionally; callers whose
            org may be unset pass ``None`` (or omit) to skip the org filter —
            preserving each call site's existing behavior byte-for-byte.
        limit: When provided, caps the number of rows returned.

    Returns:
        The list of shared document rows (possibly empty).
    """
    query = (
        db.table("documentos")
        .select("*")
        .eq("cliente_id", cliente_id)
        .eq("compartilhado_portal", True)
    )
    if org_id:
        query = query.eq("org_id", org_id)
    query = query.order("created_at", desc=True)
    if limit is not None:
        query = query.limit(limit)
    result = query.execute()
    return result.data or []
