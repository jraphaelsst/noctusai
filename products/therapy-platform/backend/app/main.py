"""
NoctusAI Therapy Platform — FastAPI Backend

Entry point for the API server.
Run with: uvicorn app.main:app --reload --port 8003
"""
from noctusai_seed import create_product_app
from app.config import settings
from app.rate_limit import limiter
from app.scheduler import configure as _configure_scheduler, start_scheduler, stop_scheduler

_configure_scheduler()
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
    consents,
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
    observations,
    patient_notes,
    patients,
    payments,
    recurring,
    refunds,
    reviews,
    rooms,
    scheduling,
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

# Per-route body-size cap. The app-wide default (`settings.max_body_bytes`,
# 1 MB — see `noctusai_seed.ProductSettings`) exists to DoS-guard inbound
# webhooks; browser uploads legitimately exceed it and need their own,
# larger, per-route ceiling instead of weakening the default everywhere.
# Plain prefix — no dynamic path segment before the upload leaf. See
# `products/social-wiring/backend/app/main.py`'s
# `_MAX_BODY_PATH_OVERRIDES` block for the wildcard-pattern shape (not
# needed here) and
# `noctusai_lib.api.middleware.MaxBodySizeMiddleware`'s docstring for the
# resolution rule.
_MAX_BODY_PATH_OVERRIDES = {
    # Message attachment upload (POST /api/attachments/upload —
    # `routers/attachments.py::upload_attachment`; images and audio).
    # `attachment_service.MAX_FILE_SIZE` (50 MB) is the real
    # business-policy limit — the router's own docstring already
    # advertises "up to 50MB" — enforced by `attachment_service.
    # upload_attachment` AFTER the whole file is read into memory
    # (`await file.read()`). This outer bound sits ~20% above it so the
    # service's own error is what the user sees, not an opaque 413 from
    # the middleware.
    "/api/attachments/upload": 60 * 1024 * 1024,  # 60 MB
}

app = create_product_app(
    name="Therapy Platform",
    schema="therapy",
    settings=settings,
    routers=[
        auth.router,
        therapists.router,
        patients.router,
        clinics.router,
        reviews.router,
        admin.router,
        availability.router,
        appointments.router,
        recurring.router,
        sessions.router,
        consents.router,
        observations.router,
        patient_notes.router,
        session_journal.router,
        longitudinal.router,
        wallets.router,
        payments.router,
        transactions.router,
        clinic_financials.router,
        admin_financials.router,
        refunds.router,
        messaging.router,
        support.router,
        attachments.router,
        settings_router.router,
        lgpd.router,
        anamnese.router,
        treatment_plans.router,
        evolution_notes.router,
        mood.router,
        therapeutic_journal.router,
        homework.router,
        rooms.router,
        scheduling.router,
        therapy_matching.router,
        invoices.router,
        dashboard_bi.router,
        whatsapp_therapy.router,
        crisis.router,
        invitations.router,
    ],
    version="0.1.0",
    limiter=limiter,
    standard_routers=["health", "notificacoes", "llm", "status_paginas"],
    consent_features="app.services.ai_consent_features",
    lifespan_startup=start_scheduler,
    lifespan_shutdown=stop_scheduler,
    max_body_path_overrides=_MAX_BODY_PATH_OVERRIDES,
)
