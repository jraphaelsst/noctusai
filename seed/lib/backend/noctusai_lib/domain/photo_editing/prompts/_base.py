"""Versioned prompt value object shared by every engine prompt.

A prompt is DATA with an identity: ``(prompt_id, version)``. Every AI
call records the version it rendered, so a quality shift can be traced
to a prompt change instead of being blamed on the model. Changing the
wording of a template REQUIRES bumping ``version`` — the colocated test
pins each template's sha256 to its version so an unbumped edit fails.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PromptTemplate:
    prompt_id: str
    version: int
    template: str
    #: Strict JSON schema the model's answer must satisfy, or ``None`` for
    #: a free-text answer. Passed verbatim as ``response_schema`` to
    #: ``noctusai_lib.integrations.llm.analyze_images``.
    response_schema: dict[str, Any] | None = None

    @property
    def ref(self) -> str:
        """``"<prompt_id>@v<version>"`` — the string stored alongside a call."""
        return f"{self.prompt_id}@v{self.version}"

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.template.encode("utf-8")).hexdigest()

    def render(self, **values: str) -> str:
        """``str.format`` the template. A missing key raises ``KeyError``
        (never renders a half-filled prompt)."""
        return self.template.format(**values)


@dataclass(frozen=True)
class RenderedPrompt:
    text: str
    ref: str
    response_schema: dict[str, Any] | None = None


__all__ = ["PromptTemplate", "RenderedPrompt"]
