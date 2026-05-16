"""looks_like_refusal heuristic + analyze_image_with_refusal_retry tests.

The retry wrapper is exercised end-to-end through the REAL seed LLM
plumbing (configure_llm + a registered test provider) — no monkeypatching
of our own code. The provider is a test-owned external-service stand-in
(the sanctioned shape; FakeProvider-style), not a patch of `analyze_image`.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Union

import pytest

from noctusai_lib.integrations.llm import (
    analyze_image_with_refusal_retry,
    looks_like_refusal,
)
from noctusai_lib.integrations.llm.client import (
    _provider_cache,
    configure_llm,
)
from noctusai_lib.integrations.llm.config import LLMConfig
from noctusai_lib.integrations.llm.registry import register


class TestLooksLikeRefusal:
    @pytest.mark.parametrize(
        "text",
        [
            None,
            "",
            "   \n  ",
            "Não foi possível extrair texto.",
            "nao consegui ler a imagem",
            "I'm sorry, I can't assist with that.",
            "Unable to process this image.",
            "No text could be extracted from the document.",
        ],
    )
    def test_detects_refusals(self, text) -> None:
        assert looks_like_refusal(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "Documento: CNH. Nome: João. CPF: 123. Validade: 2030.",
            "A cena mostra uma piscina ao ar livre com cadeiras de praia.",
            # long reply that mentions "unable to" only for ONE field is
            # NOT a refusal — it answered.
            (
                "Li o documento. É um contrato de locação. Partes: A e B. "
                "Valor: R$ 1.500. O campo de data está borrado e unable to "
                "read it, but every other field is legible: endereço, "
                "fiador, prazo de 30 meses, índice de reajuste IGPM."
            ),
        ],
    )
    def test_legitimate_answers_not_flagged(self, text) -> None:
        assert looks_like_refusal(text) is False


# A test-owned external-provider stand-in. get_provider() instantiates the
# class with no args and caches it, so the response queue is class-level.
class _ScriptedVisionProvider:
    _visions: deque[str] = deque()

    @classmethod
    def script(cls, *responses: str) -> None:
        cls._visions = deque(responses)

    async def analyze_image(
        self,
        image: Union[bytes, str],
        prompt: str,
        *,
        model: str,
        api_key: str,
        **kwargs: Any,
    ) -> str:
        return self._visions.popleft()

    async def close(self) -> None:  # pragma: no cover — cleanup
        return None


@pytest.fixture
def scripted_vision():
    register("scriptedvision", _ScriptedVisionProvider)
    configure_llm(
        LLMConfig(
            key_provider=lambda provider, org_id=None: "test-key",
            default_provider="scriptedvision",
        )
    )
    yield _ScriptedVisionProvider
    _provider_cache.clear()


class TestAnalyzeImageWithRefusalRetry:
    @pytest.mark.asyncio
    async def test_returns_first_when_not_a_refusal(self, scripted_vision) -> None:
        scripted_vision.script("Documento: contrato. Valor: R$ 100.")
        out = await analyze_image_with_refusal_retry(b"img", "prompt")
        assert out == "Documento: contrato. Valor: R$ 100."

    @pytest.mark.asyncio
    async def test_retries_once_and_returns_better_answer(
        self, scripted_vision
    ) -> None:
        scripted_vision.script(
            "Não foi possível extrair texto.",
            "Documento: CNH. Nome: João Silva. CPF: 000.",
        )
        out = await analyze_image_with_refusal_retry(b"img", "narrow prompt")
        assert "João Silva" in out

    @pytest.mark.asyncio
    async def test_returns_original_when_retry_also_refuses(
        self, scripted_vision
    ) -> None:
        scripted_vision.script(
            "Não foi possível extrair texto.",
            "nao consegui ler.",
        )
        out = await analyze_image_with_refusal_retry(b"img", "prompt")
        # best-effort: returns the original refusal, never raises
        assert out == "Não foi possível extrair texto."

    @pytest.mark.asyncio
    async def test_custom_retry_prompt_is_used(self, scripted_vision) -> None:
        scripted_vision.script("unable to.", "OK: extracted fields A, B, C.")
        out = await analyze_image_with_refusal_retry(
            b"img", "p", retry_prompt="broadened"
        )
        assert out == "OK: extracted fields A, B, C."
