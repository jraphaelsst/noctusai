"""Shared harness for the help-chat organ suite.

Same "DI seams overridden by construction, nothing monkeypatched" posture
as `tests/domain/card_hub/conftest.py` — auth and the LLM stream call are
the factory's own seams (`auth_dependency`, `stream_fn`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Optional
from uuid import uuid4

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noctusai_lib.domain.help_chat import FakeHelpChatStore, HelpChatRateLimiter, create_help_chat_router
from noctusai_lib.integrations.llm.providers.fake_provider import FakeProvider
from noctusai_lib.primitives.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)

ORG_ID = str(uuid4())
USER_ID = str(uuid4())
OUTRO_USER_ID = str(uuid4())
AUTH_HEADER = {"Authorization": "Bearer test-token"}


def _auth_dependency(authorization: Optional[str] = Header(None)) -> tuple:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return (USER_ID, ORG_ID)


def _org_id_from_auth(auth: tuple) -> str:
    return auth[1]


def _user_id_from_auth(auth: tuple) -> str:
    return auth[0]


@dataclass
class FakeStream:
    """`stream_fn`-shaped callable backed by the seed `FakeProvider` —
    records every call (for assertions on what the router sends) and can be
    scripted to raise instead of streaming (simulating a seam failure "at
    stream open", matching `chat_completion_stream`'s documented contract).
    """

    chunks: tuple[tuple[str, ...], ...] = (("Olá!", " Como posso ajudar?"),)
    #: Aligned with `chunks` by round — True ⇒ that round reports it hit the
    #: token cap (`FakeProvider(stream_truncated=...)`).
    truncated: tuple[bool, ...] = ()
    erro: Optional[BaseException] = None
    calls: list[dict] = field(default_factory=list)
    provider: FakeProvider = field(init=False)

    def __post_init__(self) -> None:
        self.provider = FakeProvider(
            stream_responses=[list(c) for c in self.chunks],
            stream_truncated=list(self.truncated),
        )

    def __call__(
        self,
        messages: list[dict],
        *,
        model: str,
        provider: str,
        org_id: Optional[str],
        outcome: Any,
    ) -> AsyncIterator[str]:
        self.calls.append({"messages": messages, "model": model, "provider": provider, "org_id": org_id})
        if self.erro is not None:
            return self._raise()
        return self.provider.chat_completion_stream(
            messages, model=model, api_key="fake-key", outcome=outcome
        )

    async def _raise(self) -> AsyncIterator[str]:
        raise self.erro
        yield ""  # pragma: no cover — unreachable; makes this an async generator function


@dataclass
class Harness:
    app: FastAPI
    client: TestClient
    stream: FakeStream
    knowledge_path: Any
    store: FakeHelpChatStore


def build_harness(
    tmp_path,
    *,
    knowledge_text: str = "## Como criar um negócio\nClique em 'Novo negócio' na tela Comercial.",
    stream: Optional[FakeStream] = None,
    rate_limit: int = 20,
    max_turns: int = 20,
    max_chars_per_message: int = 4000,
    max_continuations: int = 2,
    rate_limiter: Optional[HelpChatRateLimiter] = None,
    store: Optional[FakeHelpChatStore] = None,
) -> Harness:
    knowledge_path = tmp_path / "help_chat_knowledge.md"
    knowledge_path.write_text(knowledge_text, encoding="utf-8")
    fake_stream = stream or FakeStream()
    fake_store = store or FakeHelpChatStore()

    router = create_help_chat_router(
        product_name="IgIg",
        product_slug="igig",
        store=fake_store,
        knowledge_path=knowledge_path,
        auth_dependency=_auth_dependency,
        org_id_from_auth=_org_id_from_auth,
        user_id_from_auth=_user_id_from_auth,
        rate_limit=rate_limit,
        max_turns=max_turns,
        max_chars_per_message=max_chars_per_message,
        max_continuations=max_continuations,
        stream_fn=fake_stream,
        rate_limiter=rate_limiter,
    )
    app = FastAPI()
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.include_router(router)
    return Harness(app=app, client=TestClient(app), stream=fake_stream, knowledge_path=knowledge_path, store=fake_store)


@pytest.fixture
def harness(tmp_path):
    return build_harness(tmp_path)
