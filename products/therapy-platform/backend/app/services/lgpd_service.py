"""
LGPD Service — Data deletion per Brazilian data protection law.

Patient deletion removes patient-side data ONLY; therapist clinical data
(session_records, session_observations, session_summary_versions) is preserved
as the therapist's professional records.

Therapist deletion can target specific entities or everything.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.dependencies import log_action

logger = logging.getLogger(__name__)


async def delete_patient_data(patient_id: str, db: Any) -> Dict:
    """Delete all patient-owned data per LGPD request.

    Deletes:
        - patient_profiles
        - patient_session_notes
        - patient_longitudinal_analyses
        - wallets (patient's)
        - wallet_movements (patient's wallet)
        - conversation_participants (patient's)
        - messages (sent by patient)

    Keeps (therapist clinical data):
        - session_records
        - session_observations
        - session_summary_versions
    """
    deleted_tables: List[str] = []

    # Delete messages sent by patient
    db.table("messages").delete().eq("sender_id", patient_id).execute()
    deleted_tables.append("messages")

    # Delete conversation participations
    db.table("conversation_participants").delete().eq("user_id", patient_id).execute()
    deleted_tables.append("conversation_participants")

    # Delete wallet movements (via wallet lookup)
    wallet_result = (
        db.table("wallets")
        .select("id")
        .eq("user_id", patient_id)
        .execute()
    )
    for wallet in wallet_result.data or []:
        db.table("wallet_movements").delete().eq("wallet_id", wallet["id"]).execute()
    deleted_tables.append("wallet_movements")

    # Delete wallet
    db.table("wallets").delete().eq("user_id", patient_id).execute()
    deleted_tables.append("wallets")

    # Delete patient longitudinal analyses
    db.table("patient_longitudinal_analyses").delete().eq("patient_id", patient_id).execute()
    deleted_tables.append("patient_longitudinal_analyses")

    # Delete patient session notes
    db.table("patient_session_notes").delete().eq("patient_id", patient_id).execute()
    deleted_tables.append("patient_session_notes")

    # Delete patient profile
    db.table("patient_profiles").delete().eq("user_id", patient_id).execute()
    deleted_tables.append("patient_profiles")

    kept_tables = [
        "session_records",
        "session_observations",
        "session_summary_versions",
    ]

    # Audit log
    log_action(
        user_id=patient_id,
        tipo_acao="lgpd_delete",
        tipo_entidade="patient",
        entidade_id=patient_id,
        descricao="Exclusão de dados do paciente via LGPD",
        detalhes={"deleted_tables": deleted_tables, "kept_tables": kept_tables},
    )

    logger.info("LGPD patient data deleted: patient_id=%s tables=%s", patient_id, deleted_tables)
    return {"deleted_tables": deleted_tables, "kept_tables": kept_tables}


async def delete_therapist_data(
    therapist_id: str,
    entity_type: str,
    entity_id: Optional[str],
    db: Any,
) -> Dict:
    """Delete therapist-owned data — all or specific entities.

    entity_type:
        - "all": deletes everything (profile, settings, sessions, observations, summaries, wallet)
        - "session": deletes a specific session_record + its observations + summaries
        - "observation": deletes a specific observation
    """
    deleted: List[str] = []

    if entity_type == "all":
        # Delete in dependency order
        db.table("session_summary_versions").delete().eq("therapist_id", therapist_id).execute()
        deleted.append("session_summary_versions")

        db.table("session_observations").delete().eq("therapist_id", therapist_id).execute()
        deleted.append("session_observations")

        db.table("session_records").delete().eq("therapist_id", therapist_id).execute()
        deleted.append("session_records")

        db.table("messages").delete().eq("sender_id", therapist_id).execute()
        deleted.append("messages")

        db.table("conversation_participants").delete().eq("user_id", therapist_id).execute()
        deleted.append("conversation_participants")

        wallet_result = (
            db.table("wallets")
            .select("id")
            .eq("user_id", therapist_id)
            .execute()
        )
        for wallet in wallet_result.data or []:
            db.table("wallet_movements").delete().eq("wallet_id", wallet["id"]).execute()
        deleted.append("wallet_movements")

        db.table("wallets").delete().eq("user_id", therapist_id).execute()
        deleted.append("wallets")

        db.table("therapist_settings").delete().eq("user_id", therapist_id).execute()
        deleted.append("therapist_settings")

        db.table("therapist_profiles").delete().eq("user_id", therapist_id).execute()
        deleted.append("therapist_profiles")

    elif entity_type == "session":
        if not entity_id:
            raise HTTPException(status_code=400, detail="entity_id é obrigatório para exclusão de sessão")

        # Verify session belongs to therapist
        check = (
            db.table("session_records")
            .select("id")
            .eq("id", entity_id)
            .eq("therapist_id", therapist_id)
            .execute()
        )
        if not check.data:
            raise HTTPException(status_code=404, detail="Sessão não encontrada ou não pertence ao terapeuta")

        db.table("session_summary_versions").delete().eq("session_id", entity_id).execute()
        deleted.append("session_summary_versions")

        db.table("session_observations").delete().eq("session_id", entity_id).execute()
        deleted.append("session_observations")

        db.table("session_records").delete().eq("id", entity_id).execute()
        deleted.append("session_records")

    elif entity_type == "observation":
        if not entity_id:
            raise HTTPException(status_code=400, detail="entity_id é obrigatório para exclusão de observação")

        check = (
            db.table("session_observations")
            .select("id")
            .eq("id", entity_id)
            .eq("therapist_id", therapist_id)
            .execute()
        )
        if not check.data:
            raise HTTPException(status_code=404, detail="Observação não encontrada ou não pertence ao terapeuta")

        db.table("session_observations").delete().eq("id", entity_id).execute()
        deleted.append("session_observations")

    else:
        raise HTTPException(
            status_code=400,
            detail="Tipo de entidade inválido. Use 'all', 'session' ou 'observation'",
        )

    log_action(
        user_id=therapist_id,
        tipo_acao="lgpd_delete",
        tipo_entidade="therapist",
        entidade_id=entity_id or therapist_id,
        descricao=f"Exclusão de dados do terapeuta via LGPD: {entity_type}",
        detalhes={"deleted": deleted, "entity_type": entity_type, "entity_id": entity_id},
    )

    logger.info(
        "LGPD therapist data deleted: therapist_id=%s type=%s entity_id=%s deleted=%s",
        therapist_id, entity_type, entity_id, deleted,
    )
    return {"deleted": deleted}
