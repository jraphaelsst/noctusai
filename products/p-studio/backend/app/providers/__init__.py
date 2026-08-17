"""Provedores de cobrança.

Hoje: Asaas. Em produção: Banco do Brasil. A escolha é por env var, e a
resolução é **preguiçosa** — `settings` é instanciado no import do módulo e o
`conftest.py` dos testes só define as cinco variáveis originais, então montar
provedor no import quebraria a suíte inteira. Nada aqui toca rede antes de
alguém chamar de fato.

O guard de credencial ausente segue o formato de `database.get_admin_client()`:
o app sobe sem a credencial e só reclama quando o caminho que precisa dela é
exercitado.
"""
from typing import Optional

from app.config import settings
from app.providers.erros import ErroProvedor, ProvedorNaoConfigurado
from app.providers.fake import ProvedorFake
from app.providers.tipos import (
    Cobranca,
    ClienteCobranca,
    EventoCobranca,
    FormaCobranca,
    PedidoCobranca,
    ProvedorCobranca,
    StatusCobranca,
)

__all__ = [
    "Cobranca",
    "ClienteCobranca",
    "ErroProvedor",
    "EventoCobranca",
    "FormaCobranca",
    "PedidoCobranca",
    "ProvedorCobranca",
    "ProvedorFake",
    "ProvedorNaoConfigurado",
    "StatusCobranca",
    "provedor_padrao",
]

_cache: dict[str, ProvedorCobranca] = {}


def provedor_padrao() -> ProvedorCobranca:
    """O provedor configurado em `PROVEDOR_COBRANCA`.

    Memoizado: o adapter mantém um `httpx.Client` vivo para reaproveitar
    conexão, e não faz sentido reabrir a cada requisição.
    """
    nome = (settings.provedor_cobranca or "asaas").strip().lower()

    if nome in _cache:
        return _cache[nome]

    if nome == "fake":
        provedor: ProvedorCobranca = ProvedorFake()
    elif nome == "asaas":
        # Import tardio: manter `app.providers` importável sem httpx montado.
        from app.providers.asaas import ProvedorAsaas

        if not settings.asaas_api_key:
            raise ProvedorNaoConfigurado("asaas", "ASAAS_API_KEY")
        provedor = ProvedorAsaas(
            api_key=settings.asaas_api_key,
            base_url=settings.asaas_base_url,
        )
    else:
        raise ErroProvedor(
            nome,
            f"Provedor de cobrança desconhecido: {nome!r}. "
            "Valores aceitos: asaas, fake.",
            status=500,
        )

    _cache[nome] = provedor
    return provedor


def limpar_cache() -> None:
    """Descarta os provedores memoizados. Usado nos testes."""
    _cache.clear()
