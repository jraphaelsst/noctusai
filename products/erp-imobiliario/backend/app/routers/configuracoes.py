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

async def _test_openai(api_key: str) -> TestResult:
    """Test OpenAI API key by listing models."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=15.0,
            )
        if resp.status_code == 200:
            return TestResult(key="openai_api_key", success=True, message="Conexão com OpenAI bem-sucedida.")
        if resp.status_code == 401:
            return TestResult(key="openai_api_key", success=False, message="API Key inválida ou expirada.")
        return TestResult(key="openai_api_key", success=False, message=f"Erro inesperado (HTTP {resp.status_code}).")
    except Exception as e:
        logger.warning("configuracoes: OpenAI key test failed (%s); returning failure to caller", e)
        return TestResult(key="openai_api_key", success=False, message=f"Erro de conexão: {e}")


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

    result = await _TESTERS[key](value)
    return success_response(result.model_dump())
