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
    "construir_provedor",
    "limpar_cache",
    "provedor_padrao",
]

# Memoização por CREDENCIAL, não por nome do provedor.
#
# Era `{nome: provedor}` enquanto a chave vinha do `.env` e não mudava sem
# reiniciar o processo. Agora a chave vem do banco e o dono do estúdio pode
# trocá-la pela UI: uma cache por nome devolveria para sempre o adapter
# construído com a chave ANTIGA, e o sintoma seria "salvei a chave nova e
# continua dando 401" — sem nada no log ligando uma coisa à outra. A chave da
# cache é (nome, base_url, api_key), então trocar a credencial troca a entrada.
_cache: dict[tuple[str, str, str], ProvedorCobranca] = {}


def construir_provedor(
    nome: str, *, api_key: str = "", base_url: str = ""
) -> ProvedorCobranca:
    """Monta (ou reaproveita) o adapter para uma credencial específica.

    Memoizado porque o adapter mantém um `httpx.Client` vivo para reaproveitar
    conexão — reabrir a cada requisição é desperdício.
    """
    nome = (nome or "asaas").strip().lower()
    chave = (nome, base_url, api_key)

    if chave in _cache:
        return _cache[chave]

    if nome == "fake":
        provedor: ProvedorCobranca = ProvedorFake()
    elif nome == "asaas":
        # Import tardio: manter `app.providers` importável sem httpx montado.
        from app.providers.asaas import ProvedorAsaas

        if not api_key:
            raise ProvedorNaoConfigurado("asaas", "ASAAS_API_KEY")
        provedor = ProvedorAsaas(api_key=api_key, base_url=base_url)
    else:
        raise ErroProvedor(
            nome,
            f"Provedor de cobrança desconhecido: {nome!r}. "
            "Valores aceitos: asaas, fake.",
            status=500,
        )

    _cache[chave] = provedor
    return provedor


def provedor_padrao() -> ProvedorCobranca:
    """O provedor do `.env` — caminho de DESENVOLVIMENTO e de fallback.

    Em produção a credencial vem do banco, cifrada, e quem resolve é
    `app.dependencies.get_provedor_cobranca`. Este caminho permanece porque
    (a) a suíte e o dev local rodam com `PROVEDOR_COBRANCA=fake` sem banco de
    credenciais nenhum, e (b) um deploy que ainda não migrou continua
    funcionando. Não é caminho morto: é o degrau de baixo, e está explícito.
    """
    return construir_provedor(
        settings.provedor_cobranca,
        api_key=settings.asaas_api_key,
        base_url=settings.asaas_base_url,
    )


def limpar_cache() -> None:
    """Descarta os provedores memoizados. Usado nos testes e após gravar uma
    credencial nova pela UI."""
    _cache.clear()
