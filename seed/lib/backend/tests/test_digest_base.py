"""Unit tests for `noctusai_lib.domain.digest.BaseDigestService`.

The base class is pure orchestration — no IO. These tests exercise the
template-method `run()` against a `FakeDigestService` that overrides
each abstract method with predictable values, then assert the
envelope assembly + ordering.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from noctusai_lib.domain.digest import (
    BaseDigestService,
    DigestResult,
    DigestWindow,
)
from noctusai_lib.integrations.email.digest import Digest


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# A fully-overridden subclass for the happy path.
# ---------------------------------------------------------------------------


class FakeDigestService(BaseDigestService):
    """Minimal subclass exercising every override slot."""

    # Test fixture state — observable from the outside.
    fetch_calls: list[DigestWindow]
    aggregate_calls: list[Any]
    narrative_calls: list[tuple[Any, DigestWindow]]
    render_calls: list[tuple[Any, str]]
    subject_calls: list[tuple[Any, DigestWindow]]
    summary_calls: list[tuple[Any, str, DigestWindow]]

    def __init__(
        self,
        *,
        client: Any,
        org_id: str | None = None,
        empty: bool = False,
    ) -> None:
        super().__init__(client=client, org_id=org_id)
        self.empty = empty
        self.fetch_calls = []
        self.aggregate_calls = []
        self.narrative_calls = []
        self.render_calls = []
        self.subject_calls = []
        self.summary_calls = []

    async def _fetch_window(self, window: DigestWindow) -> Any:
        self.fetch_calls.append(window)
        if self.empty:
            return {"rows": []}
        return {"rows": [{"id": "r1"}, {"id": "r2"}]}

    def _aggregate(self, raw: Any) -> Any:
        self.aggregate_calls.append(raw)
        return {"count": len(raw["rows"])}

    async def _generate_narrative(
        self, agg: Any, window: DigestWindow
    ) -> str:
        self.narrative_calls.append((agg, window))
        if agg["count"] == 0:
            return "Nothing happened in this window."
        return f"Aggregate had {agg['count']} rows."

    def _render_bodies(self, agg: Any, narrative: str) -> tuple[str, str]:
        self.render_calls.append((agg, narrative))
        html = f"<p>{narrative}</p>"
        text = narrative
        return html, text

    def _build_subject(self, agg: Any, window: DigestWindow) -> str:
        self.subject_calls.append((agg, window))
        return f"Test digest — {agg['count']} rows"

    def _build_summary(
        self, agg: Any, narrative: str, window: DigestWindow
    ) -> dict[str, Any]:
        self.summary_calls.append((agg, narrative, window))
        return {"count": agg["count"], "narrative": narrative}


class TestRunOrchestratesPipeline:
    def test_calls_each_step_in_order_and_returns_result(self):
        svc = FakeDigestService(client=object(), org_id="org-1")
        window = DigestWindow(org_id="org-1", period_days=7)

        result = _run(svc.run(window))

        # Each step called exactly once with the right input.
        assert len(svc.fetch_calls) == 1
        assert svc.fetch_calls[0] is window
        assert len(svc.aggregate_calls) == 1
        assert svc.aggregate_calls[0] == {"rows": [{"id": "r1"}, {"id": "r2"}]}
        assert len(svc.narrative_calls) == 1
        assert svc.narrative_calls[0][0] == {"count": 2}
        assert svc.narrative_calls[0][1] is window
        assert len(svc.render_calls) == 1
        assert svc.render_calls[0][0] == {"count": 2}
        assert svc.render_calls[0][1] == "Aggregate had 2 rows."
        assert len(svc.subject_calls) == 1

        # Result envelope shape.
        assert isinstance(result, DigestResult)
        assert isinstance(result.digest, Digest)
        assert result.digest.subject == "Test digest — 2 rows"
        assert "Aggregate had 2 rows." in result.digest.html
        assert "Aggregate had 2 rows." in result.digest.text
        assert result.narrative == "Aggregate had 2 rows."
        assert result.summary == {"count": 2, "narrative": "Aggregate had 2 rows."}
        assert result.recipients == []  # default override returns []


class TestEmptyWindowPath:
    def test_empty_raw_still_runs_full_pipeline(self):
        """Empty windows are NOT short-circuited — the LLM still gets
        called with `count=0`, which the subclass can use to produce a
        deterministic 'nothing happened' narrative.

        This intentionally differs from a hypothetical `_empty_output`
        early-return — none of the four adopters short-circuit on
        emptiness. They all go through the full pipeline so the
        recipient still receives an email confirming the period was
        quiet.
        """
        svc = FakeDigestService(client=object(), empty=True)
        window = DigestWindow(period_days=7)

        result = _run(svc.run(window))

        assert result.narrative == "Nothing happened in this window."
        assert result.summary["count"] == 0
        assert result.digest.subject == "Test digest — 0 rows"
        # Confirm every abstract step was still hit.
        assert svc.fetch_calls and svc.aggregate_calls and svc.render_calls


class TestAbstractEnforcement:
    def test_cannot_instantiate_base_directly(self):
        with pytest.raises(TypeError):
            BaseDigestService(client=object())  # type: ignore[abstract]

    def test_subclass_missing_abstract_method_cannot_instantiate(self):
        class Incomplete(BaseDigestService):
            # Missing _fetch_window, etc.
            pass

        with pytest.raises(TypeError):
            Incomplete(client=object())  # type: ignore[abstract]


class TestDefaults:
    def test_default_summary_is_just_narrative(self):
        class MinimalSvc(BaseDigestService):
            async def _fetch_window(self, window):
                return {"rows": [1]}

            def _aggregate(self, raw):
                return {"x": 1}

            async def _generate_narrative(self, agg, window):
                return "narrative-text"

            def _render_bodies(self, agg, narrative):
                return ("<p>x</p>", "x")

            def _build_subject(self, agg, window):
                return "Subject"

        svc = MinimalSvc(client=object())
        result = _run(svc.run(DigestWindow()))
        # Default _build_summary returns {"narrative": narrative}.
        assert result.summary == {"narrative": "narrative-text"}
        # Default _initial_recipients returns [].
        assert result.recipients == []

    def test_initial_recipients_override_propagates(self):
        class FanOutSvc(BaseDigestService):
            async def _fetch_window(self, window):
                return {"rows": [], "admins": [{"email": "a@x"}]}

            def _aggregate(self, raw):
                return {}

            async def _generate_narrative(self, agg, window):
                return ""

            def _render_bodies(self, agg, narrative):
                return ("<p></p>", "")

            def _build_subject(self, agg, window):
                return "S"

            def _initial_recipients(self, raw):
                return raw["admins"]

        svc = FanOutSvc(client=object())
        result = _run(svc.run(DigestWindow()))
        assert result.recipients == [{"email": "a@x"}]


class TestNarrativeStaticHelper:
    def test_static_narrative_passes_through_to_helper(self):
        # Sanity — the static convenience method is a pass-through to
        # the module-level helper. Patch at the helper's import site
        # in base.py to verify the call.
        from unittest.mock import AsyncMock, patch

        with patch(
            "noctusai_lib.domain.digest.base._narrative_helper",
            new_callable=AsyncMock,
            return_value="ok",
        ) as mock_helper:
            result = _run(
                BaseDigestService._narrative(
                    system="sys",
                    user_prompt="u",
                    model="gpt-4o-mini",
                    cache=False,
                    org_id="org-1",
                    fallback="fb",
                )
            )
        assert result == "ok"
        mock_helper.assert_awaited_once_with(
            system="sys",
            user_prompt="u",
            model="gpt-4o-mini",
            cache=False,
            org_id="org-1",
            fallback="fb",
            max_tokens=600,
            temperature=0.0,
        )


class TestDigestWindow:
    def test_window_carries_extras(self):
        w = DigestWindow(
            org_id="o",
            period_days=7,
            extra={"campaign_id": "c1"},
        )
        assert w.extra["campaign_id"] == "c1"
        assert w.org_id == "o"
        assert w.period_days == 7

    def test_window_is_frozen(self):
        w = DigestWindow(org_id="o")
        # Frozen dataclass — assignment should raise.
        with pytest.raises(Exception):
            w.org_id = "other"  # type: ignore[misc]


class TestDigestResultShape:
    def test_result_dataclass_fields(self):
        d = Digest(subject="s", text="t", html="<p>h</p>")
        result = DigestResult(
            digest=d,
            narrative="n",
            summary={"k": 1},
            recipients=[{"email": "x"}],
        )
        assert result.digest is d
        assert result.narrative == "n"
        assert result.summary == {"k": 1}
        assert result.recipients == [{"email": "x"}]
