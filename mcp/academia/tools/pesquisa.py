"""academia.pesquisa.* tools — research sources (CONTRACT §B.5 / §C)."""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from ..client import get_client
from ..types import PesquisaCapturarFonteInput


async def pesquisa_capturar_fonte(args: dict) -> dict:
    inp = PesquisaCapturarFonteInput(**args)
    client = get_client()
    body: dict = {
        "url": inp.url,
        "titulo": inp.titulo,
        "trecho_citado": inp.trecho_citado,
        "resumo": inp.resumo,
        "kb_slug": inp.kb_slug,
        "vigencia_confirmada": inp.vigencia_confirmada,
    }
    if inp.exige_da_empresa is not None:
        body["exige_da_empresa"] = inp.exige_da_empresa
    return await client.request("POST", "/api/sources", json_body=body)


HANDLERS = {
    "academia.pesquisa.capturar_fonte": pesquisa_capturar_fonte,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="academia.pesquisa.capturar_fonte",
            description=(
                "ESCRITA — registra uma fonte de pesquisa vinculada a uma "
                "entrada da base de conhecimento (POST /api/sources). "
                "404 se kb_slug desconhecido."
            ),
            inputSchema=PesquisaCapturarFonteInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
