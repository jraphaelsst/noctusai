"""
Content-plan AI generation — strict output validation + the real seed LLM
plumbing (configure_llm + a test-owned scripted provider). No monkeypatching
of our own code: the provider is an external-service stand-in registered
through the seed registry (same shape as the seed's own LLM tests).
"""
from __future__ import annotations

import json
from collections import deque
from datetime import date
from typing import Any

import pytest

from noctusai_lib.integrations.llm.client import _provider_cache, configure_llm
from noctusai_lib.integrations.llm.config import LLMConfig
from noctusai_lib.integrations.llm.registry import register

from app.schemas.content_plans import AIGenerateParams
from app.services.content_plan_ai_service import (
    ContentPlanAIInvalidOutput,
    ContentPlanAINotConfigured,
    build_user_prompt,
    generate_plan_items,
    validate_output,
)

# 2026-11-02 is a Monday. Window = 11-02 .. 11-09. Allowed: Seg(1), Qua(3), Sex(5).
PARAMS = AIGenerateParams(
    items_count=3,
    period_days=7,
    start_date=date(2026, 11, 2),
    weekdays=[1, 3, 5],
    platforms=["instagram", "linkedin"],
    focus="Black Friday",
    allow_sales_cta=False,
)
PLAN = {"title": "Novembro", "month": "2026-11", "strategy_context": {"notes": "Autoridade"}}


def _item(title: str, post_date: str, platform: str = "instagram", **over: Any) -> dict:
    return {"title": title, "description": "Roteiro", "format": "reels",
            "platform": platform, "post_date": post_date, **over}


GOOD = {"items": [_item("A", "2026-11-02"), _item("B", "2026-11-04", "linkedin"), _item("C", "2026-11-06")]}


class _ScriptedProvider:
    """Test-owned provider stand-in; get_provider() builds it with no args."""

    replies: deque[str] = deque()
    seen: list[list[dict]] = []

    @classmethod
    def script(cls, *replies: Any) -> None:
        cls.replies = deque(r if isinstance(r, str) else json.dumps(r) for r in replies)
        cls.seen = []

    async def chat_completion(self, messages, *, model, api_key, **kwargs) -> str:
        type(self).seen.append(messages)
        return type(self).replies.popleft()

    async def close(self) -> None:  # pragma: no cover
        return None


@pytest.fixture
def scripted():
    register("scriptedorbity", _ScriptedProvider)
    configure_llm(LLMConfig(
        key_provider=lambda provider, org_id=None: "test-key",
        default_provider="scriptedorbity",
    ))
    yield _ScriptedProvider
    _provider_cache.clear()


@pytest.fixture
def unconfigured():
    register("scriptedorbity", _ScriptedProvider)
    configure_llm(LLMConfig(
        key_provider=lambda provider, org_id=None: None,
        default_provider="scriptedorbity",
    ))
    yield
    _provider_cache.clear()


class TestValidateOutput:
    def test_accepts_exact_valid_output(self):
        items, errors = validate_output(json.dumps(GOOD), PARAMS, set())
        assert errors == []
        assert [i.title for i in items] == ["A", "B", "C"]

    def test_wrong_count_rejected(self):
        raw = json.dumps({"items": GOOD["items"][:2]})
        _items, errors = validate_output(raw, PARAMS, set())
        assert any("Esperados exatamente 3" in e for e in errors)

    def test_date_outside_window_rejected(self):
        bad = {"items": [*GOOD["items"][:2], _item("C", "2026-11-13")]}
        _items, errors = validate_output(json.dumps(bad), PARAMS, set())
        assert any("fora da janela" in e for e in errors)

    def test_disallowed_weekday_rejected(self):
        bad = {"items": [*GOOD["items"][:2], _item("C", "2026-11-03")]}  # Tuesday
        _items, errors = validate_output(json.dumps(bad), PARAMS, set())
        assert any("dia da semana não permitido" in e for e in errors)

    def test_platform_not_requested_rejected(self):
        bad = {"items": [*GOOD["items"][:2], _item("C", "2026-11-06", "tiktok")]}
        _items, errors = validate_output(json.dumps(bad), PARAMS, set())
        assert any("plataforma" in e for e in errors)

    def test_repeat_of_existing_title_rejected(self):
        _items, errors = validate_output(json.dumps(GOOD), PARAMS, {"a"})
        assert any("repetido" in e for e in errors)

    def test_non_json_rejected(self):
        _items, errors = validate_output("claro, aqui estão", PARAMS, set())
        assert errors

    def test_code_fenced_json_is_tolerated(self):
        items, errors = validate_output("```json\n" + json.dumps(GOOD) + "\n```", PARAMS, set())
        assert errors == [] and len(items) == 3


class TestParams:
    def test_no_allowed_weekday_in_window_rejected(self):
        with pytest.raises(ValueError):
            AIGenerateParams(
                items_count=1, period_days=7, start_date=date(2026, 11, 2),
                weekdays=[], platforms=["instagram"],
            )

    def test_weekday_out_of_range_rejected(self):
        with pytest.raises(ValueError):
            AIGenerateParams(
                items_count=1, period_days=7, start_date=date(2026, 11, 2),
                weekdays=[7], platforms=["instagram"],
            )

    def test_count_bounds(self):
        for n in (0, 21):
            with pytest.raises(ValueError):
                AIGenerateParams(
                    items_count=n, period_days=7, start_date=date(2026, 11, 2),
                    weekdays=[1], platforms=["instagram"],
                )


def test_prompt_carries_briefing_and_existing_items():
    prompt = build_user_prompt(
        PARAMS, plan=PLAN, client_name="Acme",
        existing_items=[{"title": "Tema antigo", "format": "reels", "platform": "instagram",
                         "post_date": "2026-11-01"}],
    )
    assert "EXATAMENTE 3" in prompt
    assert "2026-11-02 até 2026-11-09" in prompt
    assert "Segunda, Quarta, Sexta" in prompt
    assert "Tema antigo" in prompt
    assert "NÃO permitido" in prompt
    assert "Black Friday" in prompt and "Acme" in prompt


class TestGenerate:
    @pytest.mark.asyncio
    async def test_returns_validated_items(self, scripted):
        scripted.script(GOOD)
        items = await generate_plan_items(
            PARAMS, plan=PLAN, client_name="Acme", existing_items=[], org_id="org-1"
        )
        assert len(items) == 3
        assert len(scripted.seen) == 1

    @pytest.mark.asyncio
    async def test_one_corrective_retry_then_success(self, scripted):
        scripted.script({"items": GOOD["items"][:2]}, GOOD)
        items = await generate_plan_items(
            PARAMS, plan=PLAN, client_name=None, existing_items=[], org_id="org-1"
        )
        assert len(items) == 3
        assert len(scripted.seen) == 2
        assert "rejeitada" in scripted.seen[1][-1]["content"]

    @pytest.mark.asyncio
    async def test_invalid_after_retry_raises_never_partial(self, scripted):
        scripted.script({"items": GOOD["items"][:1]}, {"items": GOOD["items"][:1]})
        with pytest.raises(ContentPlanAIInvalidOutput):
            await generate_plan_items(
                PARAMS, plan=PLAN, client_name=None, existing_items=[], org_id="org-1"
            )

    @pytest.mark.asyncio
    async def test_not_configured_is_explicit(self, unconfigured):
        with pytest.raises(ContentPlanAINotConfigured):
            await generate_plan_items(
                PARAMS, plan=PLAN, client_name=None, existing_items=[], org_id="org-1"
            )
