"""Replay de tráfego gravado, via `httpx.MockTransport`.

O `conftest.py` da raiz diz "nada de rede". Isso continua valendo — o
invariante correto, e mais forte, é: **a execução padrão do pytest não faz
nenhuma chamada de rede**. Aqui o tráfego é reproduzido a partir de fixtures
capturadas do sandbox real; só os testes marcados `ao_vivo` tocam a rede, e
eles estão fora da execução padrão por construção (`addopts` no pytest.ini).

Por que `MockTransport` e não respx/vcrpy: ele já vem no httpx, e intercepta
**abaixo** do `httpx.Client` que o adapter usa — então a construção de URL, os
headers, a serialização do corpo e o parsing da resposta são o código real. As
bibliotecas custariam uma dependência nova (o requirements.txt tem só duas de
teste) para comprar açúcar de matcher que não precisamos. E "as fixtures são
tráfego real" é propriedade de *procedência*, garantida pelo gravador — não é
algo que biblioteca nenhuma entrega.
"""
import json
from pathlib import Path
from typing import Callable, Optional

import httpx
import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "asaas"


def carregar(nome: str) -> dict:
    caminho = FIXTURES / f"{nome}.json"
    if not caminho.exists():
        pytest.skip(
            f"fixture {nome}.json ainda não gravada — "
            "rode ASAAS_API_KEY=... python scripts/gravar_asaas.py"
        )
    return json.loads(caminho.read_text(encoding="utf-8"))


def transporte_gravado(
    *nomes: str,
    ao_requisitar: Optional[Callable[[httpx.Request, dict], None]] = None,
) -> httpx.MockTransport:
    """Reproduz as trocas nomeadas, em ordem.

    `ao_requisitar` recebe a requisição real que o adapter montou junto da
    troca esperada. É aí que mora a diferença entre teste de contrato e stub:
    sem afirmar sobre a requisição de saída, isto só provaria que sabemos
    desserializar o nosso próprio arquivo.
    """
    pendentes = [carregar(n) for n in nomes]

    def handler(requisicao: httpx.Request) -> httpx.Response:
        assert pendentes, f"chamada inesperada: {requisicao.method} {requisicao.url}"
        troca = pendentes.pop(0)
        esperada = troca["requisicao"]

        assert requisicao.method == esperada["method"], (
            f"verbo divergente: enviamos {requisicao.method}, "
            f"a gravação tem {esperada['method']}"
        )
        assert requisicao.url.path == httpx.URL(esperada["url"]).path, (
            f"caminho divergente: enviamos {requisicao.url.path}, "
            f"a gravação tem {httpx.URL(esperada['url']).path}"
        )

        if ao_requisitar is not None:
            ao_requisitar(requisicao, troca)

        return _responder(troca["resposta"])

    return httpx.MockTransport(handler)


def _responder(gravada: dict) -> httpx.Response:
    """Reconstrói a resposta como ela veio, inclusive quando veio vazia.

    O 404 do Asaas não tem corpo nenhum. Devolver `json=None` aqui mandaria a
    string `"null"` pelo fio, e o adapter passaria a ser exercitado contra algo
    que a API nunca envia.
    """
    if "body" in gravada:
        return httpx.Response(gravada["status"], json=gravada["body"])
    return httpx.Response(gravada["status"], text=gravada.get("texto", ""))


def corpo_enviado(requisicao: httpx.Request) -> dict:
    return json.loads(requisicao.content) if requisicao.content else {}
