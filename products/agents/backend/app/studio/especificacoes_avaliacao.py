"""Synthetic org-spec values for the surfaces that run a platform DEFINITION without an org behind it.

The judge eval, the mechanism eval and the Studio simulator all run the platform agent itself -- the platform org
has no spec values, so the definition's ``{{org.chave}}`` placeholders would stay raw in the prompt (the model then
repeats ``{{org.prazo_retorno_humano}}`` to the lead; prod judge run e98db8e6, 2026-11). ONE helper owns the
answer, for every such path: the value of a declared spec is, in this order, the roteiro's fixture value, the org's
STORED value (when the running org has one), the declaration's own ``exemplo``, a neutral synthetic value of its
type (validator-passing; never real data -- Meta 4.7). Pure, no IO.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

__all__ = ["VALOR_NEUTRO_POR_TIPO", "VALOR_NEUTRO_PADRAO", "specs_de_avaliacao"]

#: One synthetic value per ``SPEC_TIPOS`` entry, each accepted by ``spec_formatos.validar_valor`` (a test pins it).
VALOR_NEUTRO_POR_TIPO: dict[str, str] = {
    "texto_curto": "Imobiliária Exemplo",
    "texto": "Texto de exemplo da organização.",
    "texto_longo": "Texto de exemplo da organização, usado somente em avaliações.",
    "lista": "Centro, Zona Sul",
    "url": "https://exemplo.com.br/privacidade",
    "dominios": "exemplo.com.br",
    "contatos": "contato@exemplo.com.br",
    "cnpj": "11.222.333/0001-81",
    "creci": "CRECI/SP 12345-J",
    "horario": "seg-sex 09:00-18:00",
    "duracao": "2 dias úteis",
}
VALOR_NEUTRO_PADRAO = "exemplo"


def specs_de_avaliacao(
    declaradas: Iterable[Any], dados: Mapping[str, Any] | None = None, armazenados: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """``{chave: valor}`` for every declared spec (objects with ``chave`` / ``tipo`` / ``exemplo``)."""
    dados, armazenados = dados or {}, armazenados or {}
    out: dict[str, str] = {}
    for d in declaradas:
        tipo = getattr(d, "tipo", "texto")
        out[d.chave] = str(
            dados.get(d.chave) or (armazenados.get(d.chave) or "").strip()
            or getattr(d, "exemplo", None) or VALOR_NEUTRO_POR_TIPO.get(tipo, VALOR_NEUTRO_PADRAO))
    return out
