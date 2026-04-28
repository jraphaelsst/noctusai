"""Unit tests for daily-life `ai_service` (ai-expansion Phase 16, D4).

Covers `extract_tasks_from_note` — the only AI wrapper in daily-life today.
"""
from __future__ import annotations

import asyncio

import pytest
from unittest.mock import patch, AsyncMock


def _run(coro):
    return asyncio.run(coro)


class TestExtractTasksFromNote:

    def test_returns_parsed_task_list(self):
        from app.services.ai_service import extract_tasks_from_note
        canned = (
            '{"tasks": ['
            ' {"title": "Comprar leite", "due_hint": "amanhã"},'
            ' {"title": "Ligar para João", "due_hint": null}'
            ']}'
        )
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = canned
            tasks = _run(extract_tasks_from_note("Lembrar: comprar leite amanhã e ligar para João."))
        assert len(tasks) == 2
        assert tasks[0] == {"title": "Comprar leite", "due_hint": "amanhã"}
        assert tasks[1]["due_hint"] is None

    def test_empty_note_returns_empty_without_calling_llm(self):
        from app.services.ai_service import extract_tasks_from_note
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            tasks = _run(extract_tasks_from_note(""))
        assert tasks == []
        mock_chat.assert_not_called()

    def test_whitespace_only_note_returns_empty(self):
        from app.services.ai_service import extract_tasks_from_note
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            tasks = _run(extract_tasks_from_note("   \n\t  "))
        assert tasks == []
        mock_chat.assert_not_called()

    def test_unparseable_json_returns_empty(self):
        from app.services.ai_service import extract_tasks_from_note
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "not valid JSON"
            tasks = _run(extract_tasks_from_note("ok some note"))
        assert tasks == []

    def test_markdown_fenced_response_parsed(self):
        from app.services.ai_service import extract_tasks_from_note
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = '```json\n{"tasks": [{"title": "foo"}]}\n```'
            tasks = _run(extract_tasks_from_note("note"))
        assert tasks == [{"title": "foo", "due_hint": None}]

    def test_caps_at_10_tasks(self):
        from app.services.ai_service import extract_tasks_from_note
        body = {"tasks": [{"title": f"t{i}", "due_hint": None} for i in range(20)]}
        import json as _json
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = _json.dumps(body)
            tasks = _run(extract_tasks_from_note("note"))
        assert len(tasks) == 10

    def test_cache_is_false(self):
        """Critical: note text must NOT be cached (personal content)."""
        from app.services.ai_service import extract_tasks_from_note
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = '{"tasks": []}'
            _run(extract_tasks_from_note("some personal note"))
            assert mock_chat.call_args.kwargs.get("cache") is False

    def test_llm_not_configured_returns_empty(self):
        from app.services.ai_service import extract_tasks_from_note
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.side_effect = RuntimeError("LLM not configured")
            tasks = _run(extract_tasks_from_note("ok"))
        assert tasks == []

    def test_skips_tasks_without_title(self):
        from app.services.ai_service import extract_tasks_from_note
        with patch("app.services.ai_service.chat_completion", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = (
                '{"tasks": ['
                ' {"title": "real"},'
                ' {"title": ""},'
                ' {"due_hint": "x"}'
                ']}'
            )
            tasks = _run(extract_tasks_from_note("ok"))
        assert tasks == [{"title": "real", "due_hint": None}]
