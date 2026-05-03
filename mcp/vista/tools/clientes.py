"""vista.clientes.* tools — permission-gated on most tenants.

Per `KB § INTEGRATIONS/vista.md § 4.2`, the `/clientes/*` family is
permission-gated and returns 401 on `oneconsu-rest`. The MCP exposes the
tool anyway (different tenants have permission); the typed-error response
makes the gating explicit to the host LLM.

LGPD: clientes payloads carry CPF, addresses, phones — handle as personal
data. The MCP server itself does not persist responses.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool
from pydantic import BaseModel, Field

from noctusai_lib.integrations.vista import (
    VistaClient,
    VistaConfigError,
    VistaFieldNotAvailable,
    VistaNotFound,
    VistaPermissionDenied,
    VistaTimeout,
    VistaUpstreamError,
    extract_items,
)

from ..settings import get_settings
from ..types import ListClientesOutput


CLIENTE_CANDIDATE_FIELDS = [
    "Codigo", "Nome", "Email", "Fone", "FoneCelular", "Bairro", "Cidade",
    "Estado", "UF", "CEP", "Endereco", "Numero", "Complemento",
    "DataCadastro",
]


class ListClientesInput(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=50)


def _client() -> VistaClient:
    s = get_settings()
    return VistaClient(s.base_url, s.api_key, timeout_seconds=s.timeout_seconds)


def _typed_error(e: Exception) -> dict:
    return {
        "error_class": type(e).__name__,
        "message": str(e),
        "status": getattr(e, "status", None),
    }


async def list_clientes(args: dict) -> dict:
    """Returns typed_error when the tenant key lacks permission."""
    inp = ListClientesInput(**args)
    client = _client()
    try:
        # Use a conservative starter set; real calibration will refine if
        # the endpoint ever returns 200 on this tenant.
        result = await client.listar_clientes(fields=["Codigo", "Nome"])
    except VistaPermissionDenied as e:
        return ListClientesOutput(
            items=[],
            typed_error=_typed_error(e),
            probe_status="live_probed",
        ).model_dump()
    except (
        VistaConfigError,
        VistaNotFound,
        VistaFieldNotAvailable,
        VistaTimeout,
        VistaUpstreamError,
    ) as e:
        return ListClientesOutput(
            items=[],
            typed_error=_typed_error(e),
            probe_status="live_probed",
        ).model_dump()

    raw_items, _ = extract_items(result.data)
    return ListClientesOutput(
        items=raw_items,
        typed_error=None,
        probe_status="live_probed",
    ).model_dump()


HANDLERS = {"vista.clientes.list": list_clientes}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="vista.clientes.list",
            description=(
                "List Vista clients (LEADs/customers). PERMISSION-GATED: most "
                "tenants return 401 here, in which case the response carries "
                "a typed_error and an empty items list. LGPD: clientes carry "
                "CPF / addresses / phones — handle as personal data."
            ),
            inputSchema=ListClientesInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors"]
