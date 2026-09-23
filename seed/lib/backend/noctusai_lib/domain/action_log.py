"""
Shared action logging for NoctusAI products.

Each product has an action log table with the same structure but different
table names and user-id column names:

- ERP: ``user_actions_log``, column ``usuario_id``
- Therapy: ``action_log``, column ``user_id``

The ``log_action`` function accepts these as parameters so every product
can reuse the same insertion logic.

**Thin adapter over `noctusai_lib.api.audit`.** ``log_action`` still
writes to the CALLER-SPECIFIED product table — it must, since ERP's
`user_actions_log` (and Therapy's `action_log`) are live tables real
UI features read today; silently redirecting this write to the new
platform-wide `public.audit_logs` (the S2 `noctusai_lib.api.audit`
sink's target) would be a silent regression, not an adapter. What IS
thin here is failure-handling: a write failure goes through
:func:`noctusai_lib.api.audit.sink.log_overflow_or_failure` — the
SAME named-counter + stdout-JSON-fallback contract
:class:`~noctusai_lib.api.audit.sink.RealAuditSink` uses on a failed
flush — instead of the bare ``except Exception as e:
logger.warning(...)`` this module shipped with, which recorded
nothing an operator could act on and had no visibility counter at
all.
"""
import logging
from typing import Optional

from noctusai_lib.api.audit.sink import log_overflow_or_failure

logger = logging.getLogger(__name__)


def log_action(
    db,
    table_name: str,
    user_id_column: str,
    user_id: str,
    tipo_acao: str,
    tipo_entidade: str,
    entidade_id: Optional[str] = None,
    descricao: str = "",
    detalhes: Optional[dict] = None,
) -> None:
    """Insert a row into a product's action log table.

    Parameters
    ----------
    db:
        Supabase admin client (service role) — caller provides this.
    table_name:
        Name of the action log table (e.g. ``"user_actions_log"``).
    user_id_column:
        Column that stores the acting user's id (e.g. ``"usuario_id"``).
    user_id:
        The acting user's UUID.
    tipo_acao / tipo_entidade / entidade_id / descricao / detalhes:
        Standard action metadata.
    """
    row = {
        user_id_column: user_id,
        "tipo_acao": tipo_acao,
        "tipo_entidade": tipo_entidade,
        "entidade_id": entidade_id,
        "descricao": descricao,
        "detalhes": detalhes or {},
    }
    try:
        db.table(table_name).insert(row).execute()
    except Exception as exc:
        # Was `logger.warning(...)` with no counter and no fallback —
        # a dropped action-log row was indistinguishable from "nothing
        # happened" in every log aggregator. See module docstring.
        log_overflow_or_failure(
            kind="action_log_write_failed",
            entry={"table_name": table_name, **row},
            exc=exc,
        )
