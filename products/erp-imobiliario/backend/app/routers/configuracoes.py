"""
Configurações Router — Credential testing for org-level API keys.
"""
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header

from app.dependencies import get_current_user, get_org_id
from noctusai_lib.config.credentials import resolve_credential
from app.responses import success_response
from noctusai_lib.api import StrictHttpModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/configuracoes", tags=["Configurações"])


class TestResult(StrictHttpModel):
    key: str
    success: bool
    message: str


# --------------- Testers per credential key ---------------

async def _test_openai(api_key: str, org_id: Optional[str] = None) -> TestResult:
    """Test OpenAI API key by dispatching a one-token chat completion.

    Refactored 2026-05-11 (LLM-ERP rollout, Step A): replaced raw
    `httpx.get("https://api.openai.com/v1/models", ...)` with
    `noctusai_lib.integrations.llm.chat_completion`. Goes through the seed
    provider registry so connectivity tests share the same path as real
    inference — a key that passes here is genuinely usable for chat
    (the previous `/v1/models` check returned 200 for some scoped keys
    that couldn't actually invoke chat completions). Skips the response
    cache (`cache=False`) so each test is a real round-trip.

    The `api_key` arg is kept for signature parity with the _TESTERS map
    even though the seed wrapper resolves keys via `resolve_api_key(...)`
    — at the call-site we already pulled the credential via
    `resolve_credential(...)` to fail fast on missing keys, so the seed
    wrapper will resolve the same value.
    """
    try:
        from noctusai_lib.integrations.llm import chat_completion
        from noctusai_lib.integrations.llm.exceptions import (
            LLMAPIError,
            LLMNotConfigured,
        )
    except ImportError as exc:
        logger.warning("configuracoes: seed llm wrapper unavailable (%s)", exc)
        return TestResult(
            key="openai_api_key",
            success=False,
            message=f"Erro interno (seed indisponível): {exc}",
        )

    try:
        await chat_completion(
            messages=[{"role": "user", "content": "ping"}],
            provider="openai",
            org_id=org_id,
            max_tokens=1,
            cache=False,
        )
        return TestResult(
            key="openai_api_key",
            success=True,
            message="Conexão com OpenAI bem-sucedida.",
        )
    except LLMNotConfigured:
        return TestResult(
            key="openai_api_key",
            success=False,
            message="API Key inválida ou expirada.",
        )
    except LLMAPIError as e:
        # The seed wrapper raises LLMAPIError for upstream HTTP errors.
        # We can't easily distinguish 401 from other failures here without
        # inspecting the wrapped exception — surface the underlying message.
        msg = str(e)
        if "401" in msg or "Incorrect API key" in msg or "invalid_api_key" in msg:
            return TestResult(
                key="openai_api_key",
                success=False,
                message="API Key inválida ou expirada.",
            )
        return TestResult(
            key="openai_api_key",
            success=False,
            message=f"Erro inesperado: {msg}",
        )
    except Exception as e:
        logger.warning(
            "configuracoes: OpenAI key test failed (%s); returning failure to caller",
            e,
        )
        return TestResult(
            key="openai_api_key",
            success=False,
            message=f"Erro de conexão: {e}",
        )


async def _test_infosimples(token: str) -> TestResult:
    """Test InfoSimples token by calling the account/credits endpoint."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.infosimples.com/api/v2/consultas/receita-federal/pgfn",
                params={"token": token, "cpf": "00000000000", "timeout": "5"},
                timeout=15.0,
            )
        data = resp.json()
        code = data.get("code")
        if isinstance(code, int) and 400 <= code < 500:
            msg = data.get("message") or data.get("code_message") or f"Erro de autenticação (code: {code})"
            return TestResult(key="infosimples_token", success=False, message=msg)
        return TestResult(key="infosimples_token", success=True, message="Conexão com InfoSimples bem-sucedida.")
    except Exception as e:
        logger.warning("configuracoes: InfoSimples token test failed (%s); returning failure to caller", e)
        return TestResult(key="infosimples_token", success=False, message=f"Erro de conexão: {e}")


_TESTERS = {
    "openai_api_key": _test_openai,
    "infosimples_token": _test_infosimples,
}

TESTABLE_KEYS = set(_TESTERS.keys())


# --------------- Endpoint ---------------

@router.post("/testar-credencial/{key}")
async def testar_credencial(key: str, auth = Depends(get_current_user)):
    """Test if a configured credential is valid by making a lightweight API call."""
    user, token = auth
    org_id = get_org_id(user)

    if key not in _TESTERS:
        raise HTTPException(status_code=400, detail=f"Teste não disponível para '{key}'.")

    value = resolve_credential(key, org_id)
    if not value:
        raise HTTPException(
            status_code=422,
            detail=f"Credencial '{key}' não está configurada. Configure em Configurações > Chaves de API.",
        )

    # _test_openai routes via seed `chat_completion` and uses `org_id` to
    # resolve the per-org key; _test_infosimples is a plain HTTP probe.
    tester = _TESTERS[key]
    if key == "openai_api_key":
        result = await tester(value, org_id)
    else:
        result = await tester(value)
    return success_response(result.model_dump())
