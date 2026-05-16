"""The ``register()`` ModuleRegistration seam contract.

Validates the W2.2 module exposes exactly the shape ``app/main.py``'s
assembly loop consumes — without editing ``main.py`` (the MODULES append
is returned as a TEXT delta for the architect).
"""
from __future__ import annotations


def test_register_returns_module_registration_shape():
    from app.main import ModuleRegistration
    from app.modules.email_marketing import register

    reg = register()
    assert isinstance(reg, ModuleRegistration)
    assert isinstance(reg.routers, list) and reg.routers, "routers non-empty"
    assert isinstance(reg.standard_routers, tuple)


def test_standard_routers_are_ai_output_surfaces():
    from app.modules.email_marketing import register

    reg = register()
    # W2.1 already requests health/notificacoes/team; the assembly loop
    # de-dupes, so this module only adds the AI-output surfaces.
    assert set(reg.standard_routers) == {"ai_outputs", "ai_feedback"}


def test_all_router_prefixes_namespaced_under_email_marketing():
    from app.modules.email_marketing import register

    reg = register()
    prefixes = {r.prefix for r in reg.routers}
    assert prefixes, "expected mounted routers with prefixes"
    for p in prefixes:
        assert p.startswith("/api/email-marketing/"), (
            f"router prefix {p!r} not namespaced — would collide with the "
            f"W2.1 media_wiring module (/api/settings, /api/dashboard, …)"
        )


def test_register_is_idempotent():
    """Re-invoking register() must not raise (scheduler re-register +
    consent re-register are idempotent by design)."""
    from app.modules.email_marketing import register

    r1 = register()
    r2 = register()
    assert {r.prefix for r in r1.routers} == {r.prefix for r in r2.routers}


def test_scheduler_jobs_registered_on_seed_scheduler():
    from app.modules.email_marketing import register
    from noctusai_lib.api import scheduler as seed_scheduler

    register()
    job_ids = {j.id for j in seed_scheduler.scheduler.get_jobs()}
    assert {
        "email_marketing_send_loop",
        "email_marketing_scheduled_campaigns",
        "email_marketing_automation_processor",
    }.issubset(job_ids)


def test_consent_features_registered_at_import():
    from app.modules.email_marketing import register
    from noctusai_lib.domain.ai import get_feature

    register()
    for key in (
        "mailing.subject_gen",
        "mailing.template_draft",
        "mailing.segment_contacts",
        "mailing.campaign_debrief",
    ):
        assert get_feature(key) is not None, f"consent feature {key} missing"
