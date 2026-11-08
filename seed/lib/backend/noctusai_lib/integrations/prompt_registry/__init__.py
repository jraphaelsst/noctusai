"""Platform prompt registry -- every AI call the platform owns reads its WHOLE prompt, model and vendor from the
database (``public.plataforma_agentes``), never from code, so prompts cannot leak through a repo or a bundle and are
edited by a platform admin without a deploy.

Protocol (`PromptRegistry`) + Fake + Real + factory, plus the call helpers:

    from noctusai_lib.integrations.prompt_registry import (
        configure_prompt_registry, make_prompt_registry, chamar_ia, prompt_e_modelo,
    )
    configure_prompt_registry(make_prompt_registry(get_core_client))   # once, at startup
    r = await chamar_ia("minha-chave", [{"role": "user", "content": "..."}], org_id=org)
"""
from __future__ import annotations

from .api import (
    ChamadaIA,
    chamar_ia,
    chamar_ia_visao,
    invalidar_cache,
    modelos_permitidos,
    prompt_e_modelo,
    transcrever_ia,
)
from .factory import configure_prompt_registry, get_prompt_registry, make_prompt_registry
from .fake import FakePromptRegistry
from .protocol import PromptRegistry
from .real import SupabasePromptRegistry
from .types import (
    CHAVE_RE,
    chave_valida,
    KIND_POR_CAPACIDADE,
    ChamadaMedida,
    ChaveNaoEncontrada,
    PromptEntry,
    RegistroIAIndisponivel,
    calcular_estatisticas,
)

__all__ = [
    "CHAVE_RE",
    "chave_valida",
    "KIND_POR_CAPACIDADE",
    "ChamadaIA",
    "ChamadaMedida",
    "ChaveNaoEncontrada",
    "FakePromptRegistry",
    "PromptEntry",
    "PromptRegistry",
    "RegistroIAIndisponivel",
    "SupabasePromptRegistry",
    "calcular_estatisticas",
    "chamar_ia",
    "chamar_ia_visao",
    "configure_prompt_registry",
    "get_prompt_registry",
    "invalidar_cache",
    "make_prompt_registry",
    "modelos_permitidos",
    "prompt_e_modelo",
    "transcrever_ia",
]
