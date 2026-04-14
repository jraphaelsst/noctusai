"""
NoctusAI Therapy Platform — FastAPI Backend

Entry point for the API server.
Run with: uvicorn app.main:app --reload --port 8003
"""
import logging

from fastapi import FastAPI

from app.config import settings
from app.rate_limit import limiter
from app.logging_config import configure_logging
from noctusai_shared.app_factory import configure_app
from app.routers import (
    admin,
    admin_financials,
    anamnese,
    appointments,
    attachments,
    auth,
    availability,
    clinic_financials,
    clinics,
    crisis,
    dashboard_bi,
    evolution_notes,
    homework,
    invitations,
    invoices,
    lgpd,
    longitudinal,
    messaging,
    mood,
    notificacoes,
    observations,
    patient_notes,
    patients,
    payments,
    recurring,
    refunds,
    reviews,
    rooms,
    session_journal,
    sessions,
    settings as settings_router,
    support,
    therapeutic_journal,
    therapists,
    therapy_matching,
    transactions,
    wallets,
    whatsapp_therapy,
    treatment_plans,
)

logger = logging.getLogger(__name__)

# Configure structured logging
configure_logging(debug=settings.debug, json_logs=not settings.debug)

# Production safety checks
if not settings.debug and not settings.jwt_secret:
    raise RuntimeError(
        "JWT_SECRET must be set in production. "
        "Set DEBUG=true for development or provide a secure JWT_SECRET."
    )


# Create app
app = FastAPI(
    title="NoctusAI Therapy Platform API",
    description="Backend API for online therapy: video sessions, scheduling, clinical management, and financials",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Apply shared configuration (Sentry, CORS, exception handlers, middleware, rate limiting)
configure_app(app, settings, limiter=limiter)

app.include_router(auth.router)
app.include_router(therapists.router)
app.include_router(patients.router)
app.include_router(clinics.router)
app.include_router(reviews.router)
app.include_router(admin.router)
app.include_router(notificacoes.router)
app.include_router(availability.router)
app.include_router(appointments.router)
app.include_router(recurring.router)
app.include_router(sessions.router)
app.include_router(observations.router)
app.include_router(patient_notes.router)
app.include_router(session_journal.router)
app.include_router(longitudinal.router)
app.include_router(wallets.router)
app.include_router(payments.router)
app.include_router(transactions.router)
app.include_router(clinic_financials.router)
app.include_router(admin_financials.router)
app.include_router(refunds.router)
app.include_router(messaging.router)
app.include_router(support.router)
app.include_router(attachments.router)
app.include_router(settings_router.router)
app.include_router(lgpd.router)
app.include_router(anamnese.router)
app.include_router(treatment_plans.router)
app.include_router(evolution_notes.router)
app.include_router(mood.router)
app.include_router(therapeutic_journal.router)
app.include_router(homework.router)
app.include_router(rooms.router)
app.include_router(therapy_matching.router)
app.include_router(invoices.router)
app.include_router(dashboard_bi.router)
app.include_router(whatsapp_therapy.router)
app.include_router(crisis.router)
app.include_router(invitations.router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0", "product": "therapy-platform"}
