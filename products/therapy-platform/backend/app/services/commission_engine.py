"""
Commission Engine — Financial calculation core.

Resolves platform fees, clinic commissions, and session payment splits.
Processes session payments and no-show charges atomically.

Commission hierarchy:
  Platform fee:  per-therapist override > per-clinic override > global rate
  Clinic share:  per-therapist-origin override > clinic default for origin
"""
from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional

from fastapi import HTTPException

from app.dependencies import first_or_none
from app.services import wallet_service

logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")


# ---------------------------------------------------------------------------
# Platform settings helpers
# ---------------------------------------------------------------------------

def _get_platform_setting(db: Any, key: str, default: str) -> str:
    result = (
        db.table("platform_settings")
        .select("value")
        .eq("key", key)
        .execute()
    )
    row = first_or_none(result)
    return row["value"] if row else default


# ---------------------------------------------------------------------------
# Fee / Commission Resolution
# ---------------------------------------------------------------------------

async def resolve_platform_fee(
    therapist_id: str,
    clinic_id: Optional[str],
    db: Any,
) -> Decimal:
    """Resolve the platform fee percentage.

    Priority: per-therapist override > per-clinic override > global rate.
    """
    # 1. Per-therapist override
    therapist_override = (
        db.table("platform_commission_overrides")
        .select("custom_commission_pct")
        .eq("target_type", "therapist")
        .eq("target_id", therapist_id)
        .execute()
    )
    row = first_or_none(therapist_override)
    if row and row.get("custom_commission_pct") is not None:
        return Decimal(str(row["custom_commission_pct"]))

    # 2. Per-clinic override (only if clinic-affiliated)
    if clinic_id:
        clinic_override = (
            db.table("platform_commission_overrides")
            .select("custom_commission_pct")
            .eq("target_type", "clinic")
            .eq("target_id", clinic_id)
            .execute()
        )
        row = first_or_none(clinic_override)
        if row and row.get("custom_commission_pct") is not None:
            return Decimal(str(row["custom_commission_pct"]))

    # 3. Global rate
    global_rate = _get_platform_setting(db, "global_commission_rate", "10")
    return Decimal(global_rate)


async def resolve_clinic_commission(
    clinic_id: str,
    therapist_id: str,
    patient_origin: str,
    db: Any,
) -> Optional[Decimal]:
    """Resolve clinic commission percentage for a clinic-affiliated therapist.

    Only applicable when clinic_id is not None.
    Priority: per-therapist override for origin > clinic default for origin.

    patient_origin is either 'clinic_sourced' or 'therapist_sourced'.
    """
    # 1. Per-therapist override for this origin
    if patient_origin == "clinic_sourced":
        field = "commission_override_clinic_sourced"
    else:
        field = "commission_override_therapist_sourced"

    ctc = (
        db.table("clinic_therapist_config")
        .select(field)
        .eq("clinic_id", clinic_id)
        .eq("therapist_id", therapist_id)
        .execute()
    )
    ctc_row = first_or_none(ctc)
    if ctc_row and ctc_row.get(field) is not None:
        return Decimal(str(ctc_row[field]))

    # 2. Clinic default for this origin
    if patient_origin == "clinic_sourced":
        default_field = "default_commission_pct_clinic_sourced"
    else:
        default_field = "default_commission_pct_therapist_sourced"

    cs = (
        db.table("clinic_settings")
        .select(default_field)
        .eq("clinic_id", clinic_id)
        .execute()
    )
    cs_row = first_or_none(cs)
    if cs_row and cs_row.get(default_field) is not None:
        return Decimal(str(cs_row[default_field]))

    return None


# ---------------------------------------------------------------------------
# Split Calculation
# ---------------------------------------------------------------------------

def calculate_session_split(
    gross_amount: Decimal,
    platform_fee_pct: Decimal,
    clinic_commission_pct: Optional[Decimal],
) -> Dict[str, Decimal]:
    """Calculate the financial split for a session.

    Returns {platform_fee_amount, clinic_share_amount, therapist_share_amount}.
    """
    platform_fee_amount = (gross_amount * platform_fee_pct / Decimal("100")).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )

    if clinic_commission_pct is not None:
        post_platform = gross_amount - platform_fee_amount
        clinic_share_amount = (post_platform * clinic_commission_pct / Decimal("100")).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )
        therapist_share_amount = post_platform - clinic_share_amount
    else:
        clinic_share_amount = Decimal("0")
        therapist_share_amount = gross_amount - platform_fee_amount

    return {
        "platform_fee_amount": platform_fee_amount,
        "clinic_share_amount": clinic_share_amount,
        "therapist_share_amount": therapist_share_amount,
    }


# ---------------------------------------------------------------------------
# Session Payment Processing
# ---------------------------------------------------------------------------

async def process_session_payment(
    appointment_id: str,
    db: Any,
) -> Dict[str, Any]:
    """Process payment at session end. Full atomic flow.

    1. Fetch appointment details
    2. Resolve platform fee and clinic commission
    3. Calculate split
    4. Debit patient wallet
    5. Credit therapist wallet (therapist_share)
    6. Credit clinic wallet (clinic_share, if applicable)
    7. Platform fee tracked in transaction record (no wallet)
    8. Create transaction record (status=captured)
    9. Return transaction with full breakdown
    """
    # 1. Get appointment
    appt_result = (
        db.table("appointments")
        .select("*")
        .eq("id", appointment_id)
        .execute()
    )
    appt = first_or_none(appt_result)
    if not appt:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")

    patient_id = appt["patient_id"]
    therapist_id = appt["therapist_id"]
    clinic_id = appt.get("clinic_id")
    patient_origin = appt.get("patient_origin", "therapist_sourced")
    gross_amount = Decimal(str(appt.get("session_price") or appt.get("resolved_price") or 0))

    if gross_amount <= 0:
        raise HTTPException(status_code=422, detail="Preço da sessão não definido")

    # 2. Resolve fees
    platform_fee_pct = await resolve_platform_fee(therapist_id, clinic_id, db)
    clinic_commission_pct = None
    if clinic_id:
        clinic_commission_pct = await resolve_clinic_commission(
            clinic_id, therapist_id, patient_origin, db
        )

    # 3. Calculate split
    split = calculate_session_split(gross_amount, platform_fee_pct, clinic_commission_pct)

    try:
        # 4. Debit patient wallet
        patient_wallet = await wallet_service.get_or_create_wallet(patient_id, "patient", db)
        await wallet_service.debit_wallet(
            wallet_id=patient_wallet["id"],
            amount=gross_amount,
            reference_type="session_commission",
            reference_id=appointment_id,
            description=f"Pagamento sessão #{appointment_id[:8]}",
            db=db,
        )

        # 5. Credit therapist wallet
        therapist_wallet = await wallet_service.get_or_create_wallet(therapist_id, "therapist", db)
        await wallet_service.credit_wallet(
            wallet_id=therapist_wallet["id"],
            amount=split["therapist_share_amount"],
            reference_type="session_commission",
            reference_id=appointment_id,
            description=f"Comissão sessão #{appointment_id[:8]}",
            db=db,
        )

        # 6. Credit clinic wallet (if applicable)
        if clinic_id and split["clinic_share_amount"] > 0:
            clinic_wallet = await wallet_service.get_or_create_wallet(clinic_id, "clinic", db)
            await wallet_service.credit_wallet(
                wallet_id=clinic_wallet["id"],
                amount=split["clinic_share_amount"],
                reference_type="session_commission",
                reference_id=appointment_id,
                description=f"Comissão clínica sessão #{appointment_id[:8]}",
                db=db,
            )

        # 8. Create transaction record
        transaction_data = {
            "appointment_id": appointment_id,
            "patient_id": patient_id,
            "therapist_id": therapist_id,
            "clinic_id": clinic_id,
            "patient_origin": patient_origin,
            "gross_amount": float(gross_amount),
            "platform_fee_pct": float(platform_fee_pct),
            "platform_fee_amount": float(split["platform_fee_amount"]),
            "clinic_commission_pct": float(clinic_commission_pct) if clinic_commission_pct is not None else None,
            "clinic_share_amount": float(split["clinic_share_amount"]) if clinic_id else None,
            "therapist_share_amount": float(split["therapist_share_amount"]),
            "status": "captured",
            "captured_at": "now()",
        }
        tx_result = db.table("transactions").insert(transaction_data).execute()
        transaction = tx_result.data[0]

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Session payment failed for appointment %s: %s", appointment_id, e)
        # Create failed transaction record
        db.table("transactions").insert({
            "appointment_id": appointment_id,
            "patient_id": patient_id,
            "therapist_id": therapist_id,
            "clinic_id": clinic_id,
            "patient_origin": patient_origin,
            "gross_amount": float(gross_amount),
            "platform_fee_pct": float(platform_fee_pct),
            "platform_fee_amount": float(split["platform_fee_amount"]),
            "therapist_share_amount": float(split["therapist_share_amount"]),
            "status": "failed",
        }).execute()
        raise HTTPException(
            status_code=500,
            detail="Falha no processamento do pagamento da sessão",
        )

    return transaction


# ---------------------------------------------------------------------------
# No-Show Charge
# ---------------------------------------------------------------------------

async def process_no_show_charge(
    appointment_id: str,
    db: Any,
) -> Dict[str, Any]:
    """Charge patient for a no-show (configurable percentage of session price).

    Debits patient wallet. No credits to therapist/clinic (no session happened).
    """
    appt_result = (
        db.table("appointments")
        .select("*")
        .eq("id", appointment_id)
        .execute()
    )
    appt = first_or_none(appt_result)
    if not appt:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")

    patient_id = appt["patient_id"]
    therapist_id = appt["therapist_id"]
    clinic_id = appt.get("clinic_id")
    patient_origin = appt.get("patient_origin", "therapist_sourced")
    session_price = Decimal(str(appt.get("session_price") or appt.get("resolved_price") or 0))

    if session_price <= 0:
        raise HTTPException(status_code=422, detail="Preço da sessão não definido")

    # Get no-show charge percentage
    no_show_pct = Decimal(_get_platform_setting(db, "no_show_charge_pct", "50"))
    charge_amount = (session_price * no_show_pct / Decimal("100")).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )

    if charge_amount <= 0:
        return {"charged": False, "amount": 0}

    # Debit patient wallet
    patient_wallet = await wallet_service.get_or_create_wallet(patient_id, "patient", db)
    await wallet_service.debit_wallet(
        wallet_id=patient_wallet["id"],
        amount=charge_amount,
        reference_type="no_show_fee",
        reference_id=appointment_id,
        description=f"Taxa de não comparecimento — sessão #{appointment_id[:8]}",
        db=db,
    )

    # Resolve platform fee for transaction record
    platform_fee_pct = await resolve_platform_fee(therapist_id, clinic_id, db)
    platform_fee_amount = (charge_amount * platform_fee_pct / Decimal("100")).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )

    # Create transaction
    tx_data = {
        "appointment_id": appointment_id,
        "patient_id": patient_id,
        "therapist_id": therapist_id,
        "clinic_id": clinic_id,
        "patient_origin": patient_origin,
        "gross_amount": float(charge_amount),
        "platform_fee_pct": float(platform_fee_pct),
        "platform_fee_amount": float(platform_fee_amount),
        "clinic_commission_pct": None,
        "clinic_share_amount": None,
        "therapist_share_amount": 0,
        "status": "captured",
        "captured_at": "now()",
    }
    tx_result = db.table("transactions").insert(tx_data).execute()

    return tx_result.data[0]
