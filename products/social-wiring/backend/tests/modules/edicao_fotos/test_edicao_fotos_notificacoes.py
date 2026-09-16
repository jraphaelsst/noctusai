"""Batch-ready fan-out (in-app + email + WhatsApp, per-user opt-in) +
the `/notificacoes/preferencias` self-service route. Resolves
NOC-REMEDIATE[edicao-fotos-notify-channels]."""
from __future__ import annotations

import asyncio

import pytest

from noctusai_lib.domain.photo_editing import (
    BatchReadyNotice,
    InMemoryPhotoEditingRepository,
    OrgSettings,
)
from noctusai_lib.integrations.whatsapp import FakeWahaClient
from noctusai_lib.testing import MockSupabaseClient

from app.modules.edicao_fotos.services.notificacoes_preferencias import (
    InMemoryNotificationPreferencesRepository,
    InvalidWhatsappNumberError,
    validate_whatsapp_number,
)
from app.modules.edicao_fotos.services.notifier import MultiChannelBatchReadyNotifier

from .conftest import ORG, USERS

CREATOR = USERS["corretor"].id  # 'member' role — not an agency admin
ADMIN = USERS["admin"].id  # 'owner' role — agency admin


def _notice() -> BatchReadyNotice:
    return BatchReadyNotice(
        lote_id="l1", org_id=ORG, criado_por=CREATOR, nome="Casa", total_fotos=3,
        aguardando_decisao=2, falhou=1,
    )


class _RecordingEmailSender:
    def __init__(self, *, sent: bool = True) -> None:
        self.calls: list[dict] = []
        self._sent = sent

    async def __call__(self, *, to, subject, html, text, org_id) -> bool:
        self.calls.append({"to": to, "subject": subject, "html": html, "text": text, "org_id": org_id})
        return self._sent


def _build(
    repo: InMemoryPhotoEditingRepository,
    preferences: InMemoryNotificationPreferencesRepository,
    *, email_sender=None, whatsapp_client=None,
) -> tuple[MockSupabaseClient, MultiChannelBatchReadyNotifier, FakeWahaClient]:
    core = MockSupabaseClient(validate_schema=False)
    core.set_table_data(
        "noctus_users",
        [
            {"id": CREATOR, "nome": "Caio Corretor", "email": "caio@example.com"},
            {"id": ADMIN, "nome": "Ana Admin", "email": "ana@example.com"},
        ],
    )
    waha = whatsapp_client if whatsapp_client is not None else FakeWahaClient()
    notifier = MultiChannelBatchReadyNotifier(
        core_client=lambda: core,
        repo=repo,
        preferences=preferences,
        whatsapp_client_factory=lambda **_kw: waha,
        send_email=email_sender,
    )
    return core, notifier, waha


def _preferences() -> InMemoryNotificationPreferencesRepository:
    prefs = InMemoryNotificationPreferencesRepository()
    prefs.seed_admin(ADMIN, org_id=ORG, nome="Ana Admin", email="ana@example.com", org_role="owner")
    return prefs


# --- recipient resolution + in-app -----------------------------------------


def test_notifies_creator_always_even_when_not_opted_in() -> None:
    repo = InMemoryPhotoEditingRepository()
    prefs = _preferences()  # admin NOT opted in
    core, notifier, _waha = _build(repo, prefs, email_sender=_RecordingEmailSender())
    asyncio.run(notifier.batch_ready(_notice()))
    rows = core.table("notifications").inserted_payloads
    assert [r["user_id"] for r in rows] == [CREATOR]


def test_opted_in_admin_is_also_notified_creator_is_never_duplicated() -> None:
    repo = InMemoryPhotoEditingRepository()
    prefs = _preferences()
    asyncio.run(prefs.save(org_id=ORG, user_id=ADMIN, ativo=True, whatsapp_number=None))
    core, notifier, _waha = _build(repo, prefs, email_sender=_RecordingEmailSender())
    asyncio.run(notifier.batch_ready(_notice()))
    rows = core.table("notifications").inserted_payloads
    assert sorted(r["user_id"] for r in rows) == sorted([CREATOR, ADMIN])


def test_admin_not_opted_in_is_excluded() -> None:
    repo = InMemoryPhotoEditingRepository()
    prefs = _preferences()
    asyncio.run(prefs.save(org_id=ORG, user_id=ADMIN, ativo=False, whatsapp_number="+5511999998888"))
    core, notifier, _waha = _build(repo, prefs, email_sender=_RecordingEmailSender())
    asyncio.run(notifier.batch_ready(_notice()))
    rows = core.table("notifications").inserted_payloads
    assert [r["user_id"] for r in rows] == [CREATOR]


def test_honours_both_switches() -> None:
    repo = InMemoryPhotoEditingRepository()
    prefs = _preferences()
    repo.seed_org_settings(OrgSettings(org_id=ORG, notificacoes_ativas=False))
    core, notifier, _waha = _build(repo, prefs, email_sender=_RecordingEmailSender())
    asyncio.run(notifier.batch_ready(_notice()))
    asyncio.run(repo.save_org_settings(OrgSettings(org_id=ORG)))
    asyncio.run(repo.update_platform_settings(notificacoes_globais_ativas=False))
    asyncio.run(notifier.batch_ready(_notice()))
    assert core.table("notifications").inserted_payloads == []


def test_in_app_failure_still_propagates_for_the_retry() -> None:
    class Broken:
        def table(self, _name):
            raise RuntimeError("core down")

    prefs = _preferences()
    notifier = MultiChannelBatchReadyNotifier(
        core_client=lambda: Broken(), repo=InMemoryPhotoEditingRepository(), preferences=prefs,
    )
    with pytest.raises(RuntimeError, match="core down"):
        asyncio.run(notifier.batch_ready(_notice()))


# --- email ------------------------------------------------------------------


def test_sends_email_to_every_recipient_with_an_address() -> None:
    repo = InMemoryPhotoEditingRepository()
    prefs = _preferences()
    asyncio.run(prefs.save(org_id=ORG, user_id=ADMIN, ativo=True, whatsapp_number=None))
    sender = _RecordingEmailSender()
    core, notifier, _waha = _build(repo, prefs, email_sender=sender)
    asyncio.run(notifier.batch_ready(_notice()))
    assert sorted(c["to"] for c in sender.calls) == ["ana@example.com", "caio@example.com"]
    assert all(c["org_id"] == ORG for c in sender.calls)
    assert "Casa" in sender.calls[0]["subject"]


def test_email_channel_failure_is_logged_never_raised() -> None:
    async def _boom(**_kw) -> bool:
        raise RuntimeError("resend down")

    repo = InMemoryPhotoEditingRepository()
    prefs = _preferences()
    core, notifier, _waha = _build(repo, prefs, email_sender=_boom)
    asyncio.run(notifier.batch_ready(_notice()))  # must not raise
    assert [r["user_id"] for r in core.table("notifications").inserted_payloads] == [CREATOR]


# --- whatsapp -----------------------------------------------------------------


def test_sends_whatsapp_only_to_recipients_with_a_number() -> None:
    repo = InMemoryPhotoEditingRepository()
    prefs = _preferences()
    asyncio.run(
        prefs.save(org_id=ORG, user_id=ADMIN, ativo=True, whatsapp_number="+5511988887777")
    )
    waha = FakeWahaClient()
    core, notifier, _waha = _build(repo, prefs, email_sender=_RecordingEmailSender(), whatsapp_client=waha)
    asyncio.run(notifier.batch_ready(_notice()))
    assert len(waha.sent_messages) == 1
    assert waha.sent_messages[0]["chatId"] == "5511988887777@c.us"
    assert "Casa" in waha.sent_messages[0]["text"]


def test_whatsapp_channel_failure_is_logged_never_raised() -> None:
    class BrokenWaha:
        async def send_text(self, *_a, **_kw):
            raise RuntimeError("waha down")

    repo = InMemoryPhotoEditingRepository()
    prefs = _preferences()
    asyncio.run(prefs.save(org_id=ORG, user_id=ADMIN, ativo=True, whatsapp_number="+5511988887777"))
    core, notifier, _waha = _build(
        repo, prefs, email_sender=_RecordingEmailSender(), whatsapp_client=BrokenWaha()
    )
    asyncio.run(notifier.batch_ready(_notice()))  # must not raise
    assert sorted(r["user_id"] for r in core.table("notifications").inserted_payloads) == sorted(
        [CREATOR, ADMIN]
    )


def test_creators_own_whatsapp_number_is_used_when_registered() -> None:
    repo = InMemoryPhotoEditingRepository()
    prefs = _preferences()
    asyncio.run(prefs.save(org_id=ORG, user_id=CREATOR, ativo=False, whatsapp_number="+5511977776666"))
    waha = FakeWahaClient()
    core, notifier, _waha = _build(repo, prefs, email_sender=_RecordingEmailSender(), whatsapp_client=waha)
    asyncio.run(notifier.batch_ready(_notice()))
    assert waha.sent_messages[0]["chatId"] == "5511977776666@c.us"


# --- preferences repository --------------------------------------------------


@pytest.mark.parametrize(
    "value", ["+5511999998888", "+15551234567", None, "", "  "],
)
def test_validate_whatsapp_number_accepts_e164_or_blank(value) -> None:
    validate_whatsapp_number(value)  # must not raise


@pytest.mark.parametrize("value", ["5511999998888", "not-a-phone", "+abc", "+55119999988888888"])
def test_validate_whatsapp_number_rejects_non_e164(value) -> None:
    with pytest.raises(InvalidWhatsappNumberError):
        validate_whatsapp_number(value)


def test_preferences_get_defaults_when_unset() -> None:
    repo = InMemoryNotificationPreferencesRepository()
    pref = asyncio.run(repo.get(org_id=ORG, user_id=ADMIN))
    assert pref.ativo is False and pref.whatsapp_number is None


def test_preferences_save_roundtrips() -> None:
    repo = InMemoryNotificationPreferencesRepository()
    saved = asyncio.run(
        repo.save(org_id=ORG, user_id=ADMIN, ativo=True, whatsapp_number="+5511999998888")
    )
    assert saved.ativo is True
    got = asyncio.run(repo.get(org_id=ORG, user_id=ADMIN))
    assert got == saved


def test_list_opted_in_admins_excludes_non_admins_and_the_excluded_id() -> None:
    repo = InMemoryNotificationPreferencesRepository()
    repo.seed_admin(ADMIN, org_id=ORG, nome="Ana", email="ana@example.com", org_role="owner")
    repo.seed_admin("not-admin", org_id=ORG, nome="Caio", email="caio@example.com", org_role="member")
    asyncio.run(repo.save(org_id=ORG, user_id=ADMIN, ativo=True, whatsapp_number=None))
    asyncio.run(repo.save(org_id=ORG, user_id="not-admin", ativo=True, whatsapp_number=None))
    targets = asyncio.run(repo.list_opted_in_admins(org_id=ORG))
    assert [t.user_id for t in targets] == [ADMIN]
    targets = asyncio.run(repo.list_opted_in_admins(org_id=ORG, exclude_user_id=ADMIN))
    assert targets == []


# --- router: /notificacoes/preferencias --------------------------------------


def test_preferencias_get_defaults_to_off(edicao) -> None:
    edicao.as_user("corretor")
    resp = edicao.http.get("/api/edicao-fotos/notificacoes/preferencias")
    assert resp.status_code == 200
    assert resp.json() == {"ativo": False, "whatsapp_number": None}


def test_preferencias_put_is_self_scoped_and_roundtrips(edicao) -> None:
    edicao.as_user("corretor")
    resp = edicao.http.put(
        "/api/edicao-fotos/notificacoes/preferencias",
        json={"ativo": True, "whatsapp_number": "+5511999998888"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ativo": True, "whatsapp_number": "+5511999998888"}
    saved = asyncio.run(edicao.preferences.get(org_id=USERS["corretor"].org, user_id=USERS["corretor"].id))
    assert saved.ativo is True and saved.whatsapp_number == "+5511999998888"
    # a different user's own row is untouched
    other = asyncio.run(edicao.preferences.get(org_id=USERS["admin"].org, user_id=USERS["admin"].id))
    assert other.ativo is False


def test_preferencias_put_rejects_non_e164_number(edicao) -> None:
    edicao.as_user("admin")
    resp = edicao.http.put(
        "/api/edicao-fotos/notificacoes/preferencias",
        json={"ativo": True, "whatsapp_number": "not-a-phone"},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "whatsapp_invalido"
