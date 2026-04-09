"""
No-Show Service — Background detection and charging.

Detects appointments where the scheduled end + 30 minutes has passed,
status is still 'waiting', and neither party attended. Charges the patient
a configurable percentage of the session price.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from app.dependencies import first_or_none
from app.services import commission_engine

logger = logging.getLogger(__name__)

SP_TZ = timezone(timedelta(hours=-3))


def _get_platform_setting(db: Any, key: str, default: str) -> str:
    result = (
        db.table("platform_settings")
        .select("value")
        .eq("key", key)
        .execute()
    )
    row = first_or_none(result)
    return row["value"] if row else default


async def detect_and_charge_no_shows(db: Any) -> Dict[str, Any]:
    """Background job: find and charge no-show appointments.

    Criteria:
    - scheduled_end + 30min has passed
    - status is 'waiting' (neither party joined)

    For each no-show:
    - Update appointment status to 'no_show'
    - Charge patient no_show_charge_pct % of session price
    - Update recurring_schedule.total_absences if applicable
    """
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(minutes=30)).isoformat()

    # Find waiting appointments past the cutoff
    result = (
        db.table("appointments")
        .select("*")
        .eq("status", "waiting")
        .lt("scheduled_end", cutoff)
        .execute()
    )
    appointments = result.data or []

    processed = 0
    charged = 0

    for appt in appointments:
        appointment_id = appt["id"]
        try:
            # Update status to no_show
            db.table("appointments").update({
                "status": "no_show",
            }).eq("id", appointment_id).execute()

            # Charge patient
            tx = await commission_engine.process_no_show_charge(appointment_id, db)
            if tx:
                charged += 1

            # Update recurring schedule absences if applicable
            recurring_id = appt.get("recurring_schedule_id")
            if recurring_id:
                schedule_result = (
                    db.table("recurring_schedules")
                    .select("total_absences")
                    .eq("id", recurring_id)
                    .execute()
                )
                schedule = first_or_none(schedule_result)
                if schedule:
                    new_absences = (schedule.get("total_absences") or 0) + 1
                    db.table("recurring_schedules").update({
                        "total_absences": new_absences,
                    }).eq("id", recurring_id).execute()

            processed += 1

        except Exception as e:
            logger.error(
                "Failed to process no-show for appointment %s: %s",
                appointment_id, e,
            )

    logger.info("No-show detection: processed=%d, charged=%d", processed, charged)
    return {"processed": processed, "charged": charged}
