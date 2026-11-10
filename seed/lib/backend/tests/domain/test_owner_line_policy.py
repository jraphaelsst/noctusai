"""Owner line registers ITS OWN WAHA line as send-enabled -- tighten-only; a stricter policy on that host wins."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.notification_catalog import (
    FakeNotificationGate, FakeOwnerRecipientSource, NotificationKind, OwnerRecipient, WahaOwnerLineTransport,
    declare_kinds, notify_owner, register_owner_line_policy, reset_declarations_for_tests,
)
from noctusai_lib.integrations.whatsapp import get_whatsapp_client
from noctusai_lib.integrations.whatsapp.line_policy import (
    SEND_DISABLED, LinePolicy, LineWriteRefused, clear_line_policies, register_line_policy, resolve_line_policy,
    set_host_resolver,
)

URL, EXPECTED = "http://owner-waha.test:3000", "+5511999990099"
P = "owner-line-policy-product"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("WAHA_LINE_POLICIES", raising=False)
    clear_line_policies()
    set_host_resolver(lambda host: None)
    reset_declarations_for_tests(P)
    declare_kinds(P, [NotificationKind(kind="aviso", titulo="Aviso", descricao="d", gatilho="g")])
    yield
    clear_line_policies()
    set_host_resolver(None)
    reset_declarations_for_tests(P)


def test_owner_line_host_with_no_other_policy_may_send():
    assert register_owner_line_policy(URL, "default", EXPECTED) is None
    assert resolve_line_policy(URL, "default").send_enabled
    get_whatsapp_client(base_url=URL, session="default")._guard_write("POST", "/api/sendText")  # no raise


def test_owner_line_host_declared_read_only_is_refused():
    register_line_policy(URL, LinePolicy(SEND_DISABLED, False, False, False), allow_memory_sink=True)
    assert register_owner_line_policy(URL, "default", EXPECTED) == "linha_noc_politica_recusada"
    assert not resolve_line_policy(URL, "default").send_enabled
    with pytest.raises(LineWriteRefused):
        get_whatsapp_client(base_url=URL, session="default")._guard_write("POST", "/api/sendText")


def test_unrelated_host_still_no_line_policy():
    register_owner_line_policy(URL, "default", EXPECTED)
    other = get_whatsapp_client(base_url="http://client-waha.test:3000", session="default")
    with pytest.raises(LineWriteRefused, match="no_line_policy"):
        other._guard_write("POST", "/api/sendText")


def test_url_without_expected_number_registers_nothing():
    assert register_owner_line_policy(URL, "default", None) is None
    assert not resolve_line_policy(URL, "default").send_enabled
    with pytest.raises(LineWriteRefused, match="no_line_policy"):
        get_whatsapp_client(base_url=URL, session="default")._guard_write("POST", "/api/sendText")


def test_registered_host_whose_paired_number_differs_is_refused():
    register_owner_line_policy(URL, "default", EXPECTED)
    sent = []

    class C:
        def send_text_to_phone_sync(self, phone, text):
            sent.append(phone)

    t = WahaOwnerLineTransport(lambda: C(), expected_numero=EXPECTED, me_fetch=lambda: "5511888880000@c.us")
    d = notify_owner(P, "aviso", "oi", gate=FakeNotificationGate(P),
                     recipients=FakeOwnerRecipientSource([OwnerRecipient("+5511999990001")]), transport=t)
    assert d.status == "failed" and sent == []
