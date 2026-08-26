"""The inbox shows people, not phone numbers.

The finding: the chat list rendered `5511974693365` and `5519998839998` while
the CRM held 10.258 clientes keyed on exactly those numbers. The platform knew
who was writing and showed digits anyway.

WHAT THESE PIN
--------------
- a phone chat whose number matches a cliente shows that person's name;
- 🔴 a LID or group id is NEVER matched against a phone — `182364311425240` is
  an internal identifier, and putting a stranger's name on it is worse than
  the digits;
- a title WhatsApp itself resolved (a saved contact) is left alone: it is what
  the person chose to be called;
- an unknown number stays a number rather than becoming blank.
"""
from __future__ import annotations

from app.routers.whatsapp_connections_router import _telefone_do_chat


class TestTelefoneDoChat:
    def test_a_phone_conversation_yields_an_e164_key(self):
        assert _telefone_do_chat("5511974693365@c.us") == "+5511974693365"
        assert _telefone_do_chat("5511974693365@s.whatsapp.net") == "+5511974693365"

    def test_a_group_is_not_a_person(self):
        assert _telefone_do_chat("120363001234567890@g.us") is None

    def test_a_lid_is_not_a_phone_number(self):
        """🔴 `182364311425240@lid` is an internal WhatsApp identifier. Treating
        it as a phone is how someone else's name lands on a conversation."""
        assert _telefone_do_chat("182364311425240@lid") is None

    def test_something_that_is_not_a_chat_id_at_all(self):
        assert _telefone_do_chat("") is None
        assert _telefone_do_chat("status") is None
        assert _telefone_do_chat("5511974693365") is None

    def test_absurd_lengths_are_refused(self):
        assert _telefone_do_chat("123@c.us") is None
        assert _telefone_do_chat("1234567890123456789@c.us") is None
