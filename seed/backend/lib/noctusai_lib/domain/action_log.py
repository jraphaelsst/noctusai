"""
Shared action logging for NoctusAI products.

Each product has an action log table with the same structure but different
table names and user-id column names:

- ERP: ``user_actions_log``, column ``usuario_id``
- Therapy: ``action_log``, column ``user_id``

The ``log_action`` function accepts these as parameters so every product
can reuse the same insertion logic.
"""
import logging
from typing import Optional

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
    try:
        db.table(table_name).insert({
            user_id_column: user_id,
            "tipo_acao": tipo_acao,
            "tipo_entidade": tipo_entidade,
            "entidade_id": entidade_id,
            "descricao": descricao,
            "detalhes": detalhes or {},
        }).execute()
    except Exception as e:
        logger.warning("Failed to log action: %s", e)
