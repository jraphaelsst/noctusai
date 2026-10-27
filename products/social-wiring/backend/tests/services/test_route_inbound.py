"""Code-first routing for the YouTube upload chat (WhatsApp + platform chat).

`route_inbound` must answer every structured message without a model and
reach the LLM only when every deterministic path declines. The web half
(`web:` sessions) must reply into the conversation memory + the request's
collector instead of trying a WhatsApp send.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.services.chatbot_service import ChatbotService
from app.services.conversation_module import route_inbound
from app.services.whatsapp_intake_service import WhatsAppIntakeService, web_reply_sink
from tests.services.test_chatbot_service import _EmptyImoveisAdmin, _FakeRedis

DRIVE = "https://drive.google.com/drive/folders/1abcDEF"


class _RecordingIntake:
    """Intake stand-in that records which entry point the router used."""

    def __init__(self, state: str = "idle") -> None:
        self.state = state
        self.calls: list[tuple] = []

    async def _get_state(self, session_id):
        if self.state == "idle":
            return None
        return SimpleNamespace(state=self.state)

    async def handle_message(self, session_id, text):
        self.calls.append(("handle_message", text))

    async def send_reply(self, session_id, text):
        self.calls.append(("send_reply", text))

    async def start_file_upload(self, session_id, *, product_code, file_id):
        self.calls.append(("start_file_upload", product_code, file_id))


class _Commands:
    def __init__(self, *, pending: bool = False, handles: set[str] | None = None) -> None:
        self.pending = pending
        self.handles = handles or set()

    def has_pending_confirmation(self, session_id):
        return self.pending

    async def try_handle(self, session_id, text):
        return f"cmd:{text}" if text in self.handles else None


class _Llm:
    def __init__(self) -> None:
        self.seen: list[str] = []

    async def __call__(self, text: str) -> None:
        self.seen.append(text)


async def _route(intake, text, *, commands=None, file_id=None):
    llm = _Llm()
    path = await route_inbound(
        intake=intake,
        session_id="web:t",
        text=text,
        llm_fallback=llm,
        commands=commands,
        attached_file_id=file_id,
    )
    return path, llm


@pytest.mark.asyncio
class TestRouteOrder:
    async def test_code_and_drive_link_skip_the_model(self):
        intake = _RecordingIntake()
        path, llm = await _route(intake, f"ONE10874 {DRIVE}")
        assert path == "upload-drive"
        assert intake.calls == [("handle_message", f"ONE10874 {DRIVE}")]
        assert llm.seen == []

    @pytest.mark.parametrize("state", ["awaiting_confirmation", "awaiting_video_choice", "awaiting_manual_title", "processing"])
    async def test_mid_flow_answers_go_to_the_state_machine(self, state):
        intake = _RecordingIntake(state=state)
        path, llm = await _route(intake, "1")
        assert path == "state-machine"
        assert intake.calls == [("handle_message", "1")]
        assert llm.seen == []

    async def test_attached_video_with_code_starts_the_file_upload(self):
        intake = _RecordingIntake()
        path, llm = await _route(intake, "sobe esse ONE10874", file_id="stg-1")
        assert path == "upload-file"
        assert intake.calls == [("start_file_upload", "ONE10874", "stg-1")]
        assert llm.seen == []

    async def test_attached_video_without_code_asks_the_model(self):
        intake = _RecordingIntake()
        path, llm = await _route(intake, "sobe esse video", file_id="stg-1")
        assert path == "llm"
        assert llm.seen == ["sobe esse video"]

    async def test_free_text_reaches_the_model(self):
        intake = _RecordingIntake()
        path, llm = await _route(intake, "quais visitas tenho amanha?")
        assert path == "llm"
        assert intake.calls == []

    async def test_typed_command_is_answered_without_the_model(self):
        intake = _RecordingIntake()
        commands = _Commands(handles={"ONE10874 status"})
        path, llm = await _route(intake, "ONE10874 status", commands=commands)
        assert path == "command"
        assert intake.calls == [("send_reply", "cmd:ONE10874 status")]
        assert llm.seen == []

    async def test_pending_command_confirmation_beats_the_upload_state(self):
        intake = _RecordingIntake(state="awaiting_confirmation")
        commands = _Commands(pending=True, handles={"sim"})
        path, _ = await _route(intake, "sim", commands=commands)
        assert path == "command-confirm"
        assert intake.calls == [("send_reply", "cmd:sim")]

    async def test_upload_sim_is_not_stolen_by_commands(self):
        intake = _RecordingIntake(state="awaiting_confirmation")
        commands = _Commands(pending=False, handles={"sim"})
        path, _ = await _route(intake, "sim", commands=commands)
        assert path == "state-machine"


# ── the real intake on a web session ───────────────────────────────────────


@pytest.fixture
def redis():
    return _FakeRedis()


@pytest.fixture
def web_intake(redis):
    return WhatsAppIntakeService(
        waha_base_url="",
        waha_api_key="",
        waha_session="default",
        redis_client=redis,
        authorized_numbers=[],
        crm_service=None,
        admin_supabase=_EmptyImoveisAdmin(),
        youtube_service=None,
        upload_dir=Path("/tmp"),
        org_id=UUID("00000000-0000-4000-8000-000000000001"),
    )


def _history(redis, session_id):
    bot = ChatbotService(redis_client=redis, intake_service=None, session_id=session_id)
    return bot.load_history()


@pytest.mark.asyncio
class TestWebSessionReplies:
    async def test_web_reply_lands_in_memory_and_the_request_collector(self, redis, web_intake):
        collected: list[str] = []
        token = web_reply_sink.set(collected)
        try:
            await web_intake.send_reply("web:t", "olá")
        finally:
            web_reply_sink.reset(token)
        assert collected == ["olá"]
        assert _history(redis, "web:t") == [{"role": "assistant", "content": "olá"}]

    async def test_web_reply_outside_a_request_still_reaches_memory(self, redis, web_intake):
        await web_intake.send_reply("web:t", "publicado")
        assert _history(redis, "web:t")[-1]["content"] == "publicado"

    async def test_code_without_catalog_entry_asks_for_a_manual_title(self, redis, web_intake):
        """Drive request through the real router: the reply is the intake's
        own wording, collected for the HTTP response, no model involved."""
        collected: list[str] = []
        token = web_reply_sink.set(collected)
        llm = _Llm()
        try:
            path = await route_inbound(
                intake=web_intake,
                session_id="web:t",
                text=f"ONE10874 {DRIVE}",
                llm_fallback=llm,
            )
        finally:
            web_reply_sink.reset(token)
        assert path == "upload-drive"
        assert llm.seen == []
        assert any("título manual" in m for m in collected)
        pending = await web_intake.get_pending_upload("web:t")
        assert pending["state"] == "awaiting_manual_title"

    async def test_attached_file_flow_then_title_then_confirmation(self, redis, web_intake):
        web_intake.register_uploaded_file(
            file_id="stg-1",
            local_path="/tmp/uploads/staging-1__casa.mp4",
            file_name="casa.mp4",
            file_size_bytes=10,
        )
        collected: list[str] = []
        token = web_reply_sink.set(collected)
        try:
            await route_inbound(
                intake=web_intake,
                session_id="web:t",
                text="ONE10874",
                llm_fallback=_Llm(),
                attached_file_id="stg-1",
            )
            await route_inbound(
                intake=web_intake,
                session_id="web:t",
                text="Casa com piscina",
                llm_fallback=_Llm(),
            )
        finally:
            web_reply_sink.reset(token)
        assert "título manual" in collected[0]
        assert "Confirma o upload?" in collected[1]
        pending = await web_intake.get_pending_upload("web:t")
        assert pending["state"] == "awaiting_confirmation"
        assert pending["file_id"] == "stg-1"
        assert pending["title"] == "Casa com piscina"

    async def test_expired_attachment_says_so(self, web_intake):
        collected: list[str] = []
        token = web_reply_sink.set(collected)
        try:
            await web_intake.start_file_upload("web:t", product_code="ONE10874", file_id="stg-gone")
        finally:
            web_reply_sink.reset(token)
        assert collected == ["❌ O arquivo anexado expirou ou foi removido. Anexe o vídeo novamente."]


@pytest.mark.asyncio
async def test_prerecorded_inbound_is_not_sent_to_the_model_twice(redis):
    seen: list[list] = []

    async def chat(msgs, specs):
        from noctusai_lib.integrations.llm import ChatToolsResponse

        seen.append(list(msgs))
        return ChatToolsResponse(text="ok")

    bot = ChatbotService(redis_client=redis, intake_service=None, session_id="web:d", chat=chat)
    bot._append_memory("inbound", "quais visitas amanha?")
    await bot.reply("quais visitas amanha?", append_inbound=False, append_outbound=False)

    user_turns = [m for m in seen[0] if getattr(m, "role", None) == "user"]
    assert [m.content for m in user_turns] == ["quais visitas amanha?"]


def test_commands_are_off_without_a_youtube_connection(web_intake):
    """No connection → no command executor, so the router falls through
    instead of answering every command with a per-video failure."""
    assert web_intake.youtube_chat_commands() is None


def test_model_prompt_quotes_the_command_grammar_from_its_one_home():
    from app.services.chatbot_service import _system_prompt
    from app.services.youtube_chat_commands import HELP_TEXT

    prompt = _system_prompt()
    assert HELP_TEXT in prompt
    assert "{commands_help}" not in prompt
