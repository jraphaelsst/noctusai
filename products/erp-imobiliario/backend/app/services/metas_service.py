"""
Metas Service — Business logic for goals/targets creation.

Handles batch creation of daily metas from active configurations,
minimizing N+1 queries by batching DB inserts.
"""
import logging
from typing import List

logger = logging.getLogger(__name__)

TIPOS = ["diaria", "semanal", "mensal", "anual"]


def criar_metas_hoje(user_id: str, data_hoje: str, db, admin) -> int:
    """
    Create today's metas from active metas_config entries.

    For each active config and each tipo (diaria, semanal, mensal, anual),
    checks if a scaffold meta already exists. If not, calculates the
    proportional target and period end date, then inserts in bulk.

    Args:
        user_id: The user's ID.
        data_hoje: Current date in São Paulo timezone (ISO string).
        db: Supabase user client (respects RLS).
        admin: Supabase admin client (for RPCs).

    Returns:
        Number of metas created.
    """
    # Active configs
    configs_result = (
        db.table("metas_config")
        .select("*")
        .eq("usuario_id", user_id)
        .eq("ativo", True)
        .execute()
    )
    configs = configs_result.data or []
    if not configs:
        return 0

    metas_to_insert: List[dict] = []

    for cfg in configs:
        for tipo in TIPOS:
            # Check if meta already exists via scaffold RPC
            existing = db.rpc("ensure_scaffold_meta", {
                "p_usuario_id": user_id,
                "p_tipo": tipo,
                "p_categoria": cfg["categoria"],
                "p_data_ref": data_hoje,
            }).execute()

            if not existing.data:
                # Calculate proportional target
                prop = admin.rpc("calcular_meta_proporcional", {
                    "p_meta_mensal": cfg["meta_pretendida"],
                    "p_tipo": tipo,
                    "p_data_ref": data_hoje,
                }).execute()
                meta_pretendida = prop.data if prop.data else cfg["meta_pretendida"]

                # Get period end date
                prazo = admin.rpc("period_end_date", {
                    "tipo_meta": tipo,
                    "data_ref": data_hoje,
                }).execute()
                data_prazo_val = prazo.data if prazo.data else data_hoje

                metas_to_insert.append({
                    "usuario_id": user_id,
                    "tipo": tipo,
                    "categoria": cfg["categoria"],
                    "categoria_custom": cfg.get("categoria_custom"),
                    "meta_pretendida": meta_pretendida,
                    "meta_realizada": 0,
                    "data_prazo": data_prazo_val,
                    "status": "no_prazo",
                    "criada_manualmente": False,
                })

    # Batch insert all metas at once
    if metas_to_insert:
        db.table("metas").insert(metas_to_insert).execute()

    return len(metas_to_insert)
