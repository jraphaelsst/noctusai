"""
Schedule service — recurrence expansion for calendar events.

Expands recurring events into individual occurrences within a date range.
Pure Python logic, no database queries.
"""
from __future__ import annotations

import logging
from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Optional
from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)
# Recurrence vocabulary — single source of truth (router filter consumes
# this so the "is recurring" predicate cannot drift from expansion).
RECURRING_VALUES = ("diario", "semanal", "mensal", "anual")


def expandir_recorrencias(
    events: list[dict],
    inicio: Optional[date] = None,
    fim: Optional[date] = None,
) -> list[dict]:
    """Expand recurring events into individual occurrences.

    Non-recurring events (recorrencia == 'nenhuma' or None) pass through unchanged.
    Recurring events generate child occurrences with shifted dates.

    Args:
        events: List of event dicts from the database.
        inicio: Start of the visible date range (inclusive).
        fim: End of the visible date range (inclusive).

    Returns:
        Expanded list including both original and generated occurrences.
    """
    if not fim:
        fim = date.today() + timedelta(days=90)
    if not inicio:
        inicio = date.today() - timedelta(days=30)

    result = []

    for event in events:
        recorrencia = event.get("recorrencia", "nenhuma")

        if not recorrencia or recorrencia == "nenhuma":
            result.append(event)
            continue

        # Parse the original event's start date
        data_inicio_raw = event.get("data_inicio")
        if not data_inicio_raw:
            result.append(event)
            continue

        if isinstance(data_inicio_raw, str):
            try:
                dt_inicio = datetime.fromisoformat(data_inicio_raw.replace("Z", "+00:00"))
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "schedule: event id=%s has unparseable data_inicio=%r (%s); "
                    "passing through without recurrence expansion",
                    event.get("id"), data_inicio_raw, exc,
                )
                result.append(event)
                continue
        elif isinstance(data_inicio_raw, datetime):
            dt_inicio = data_inicio_raw
        else:
            result.append(event)
            continue

        # Calculate event duration for shifting data_fim
        data_fim_raw = event.get("data_fim")
        duracao = None
        if data_fim_raw:
            if isinstance(data_fim_raw, str):
                try:
                    dt_fim = datetime.fromisoformat(data_fim_raw.replace("Z", "+00:00"))
                    duracao = dt_fim - dt_inicio
                except (ValueError, TypeError) as exc:
                    logger.warning(
                        "schedule: event id=%s has unparseable data_fim=%r (%s); "
                        "expansion will use point-in-time start without duration",
                        event.get("id"), data_fim_raw, exc,
                    )
            elif isinstance(data_fim_raw, datetime):
                duracao = data_fim_raw - dt_inicio

        # Determine recurrence end
        rec_fim_raw = event.get("recorrencia_fim")
        if rec_fim_raw:
            if isinstance(rec_fim_raw, str):
                try:
                    rec_fim = date.fromisoformat(rec_fim_raw)
                except (ValueError, TypeError) as exc:
                    logger.warning(
                        "schedule: event id=%s has unparseable recorrencia_fim=%r (%s); "
                        "defaulting to query window end",
                        event.get("id"), rec_fim_raw, exc,
                    )
                    rec_fim = fim
            elif isinstance(rec_fim_raw, date):
                rec_fim = rec_fim_raw
            else:
                rec_fim = fim
        else:
            rec_fim = fim

        # Limit expansion to prevent infinite loops
        max_occurrences = 365
        effective_fim = min(rec_fim, fim)

        # Include the original event
        result.append(event)

        # Generate occurrences
        delta = _get_delta(recorrencia)
        if delta is None:
            continue

        current = dt_inicio
        count = 0
        while count < max_occurrences:
            current = _add_delta(current, delta, recorrencia)
            if current.date() > effective_fim:
                break
            if current.date() < inicio:
                count += 1
                continue

            occurrence = deepcopy(event)
            occurrence["data_inicio"] = current.isoformat()
            if duracao:
                occurrence["data_fim"] = (current + duracao).isoformat()
            occurrence["evento_pai_id"] = event.get("id")
            occurrence["is_recorrencia"] = True
            # Don't give occurrences their own ID — they're virtual
            occurrence["id"] = f"{event.get('id')}__{current.date().isoformat()}"
            result.append(occurrence)
            count += 1

    # Sort by data_inicio
    result.sort(key=lambda e: e.get("data_inicio", ""))
    return result


def _get_delta(recorrencia: str):
    """Return the timedelta/relativedelta for a recurrence type."""
    if recorrencia == "diario":
        return "diario"
    elif recorrencia == "semanal":
        return "semanal"
    elif recorrencia == "mensal":
        return "mensal"
    elif recorrencia == "anual":
        return "anual"
    return None


def _add_delta(dt: datetime, delta: str, recorrencia: str) -> datetime:
    """Add one recurrence period to a datetime."""
    if recorrencia == "diario":
        return dt + timedelta(days=1)
    elif recorrencia == "semanal":
        return dt + timedelta(weeks=1)
    elif recorrencia == "mensal":
        return dt + relativedelta(months=1)
    elif recorrencia == "anual":
        return dt + relativedelta(years=1)
    return dt
