"""Encanamento HTTP compartilhado pelos adapters de provedor.

É o análogo de `database.execute()` para chamadas de saída: um único ponto que
traduz falha de transporte em `ErroProvedor`, para que service e router fiquem
sem try/except.

Três decisões que valem explicação:

**Síncrono.** Não existe um único `async def` em `app/` — toda rota e todo
service são `def` comum, e o FastAPI os roda no threadpool. Usar
`httpx.AsyncClient` aqui faria deste o único ponto assíncrono do backend, com
todo o custo de contágio que isso traz. `httpx.Client` é thread-safe, então o
threadpool não é problema.

**Client de módulo, reutilizado.** O idioma do `database.py` é criar um client
Supabase por requisição, mas ali o custo é montar um objeto; aqui seria abrir
conexão TCP e handshake TLS a cada chamada. Como não existe hook de lifespan
no `main.py` (e criar um só para isso seria desproporcional), o client é
preguiçoso e vive no módulo.

**Timeout explícito.** O default do httpx é 5s para a operação inteira, o que
é curto para registro de boleto em banco. 10s total, 5s para conectar.
"""
from typing import Any, Optional

import httpx

from app.providers.erros import ErroProvedor

TIMEOUT_PADRAO = httpx.Timeout(10.0, connect=5.0)


class ClienteHTTP:
    """Wrapper fino sobre `httpx.Client` com tradução de erro."""

    def __init__(
        self,
        provedor: str,
        base_url: str,
        headers: Optional[dict] = None,
        *,
        transport: Optional[httpx.BaseTransport] = None,
        cert: Any = None,
        timeout: httpx.Timeout = TIMEOUT_PADRAO,
    ) -> None:
        self.provedor = provedor
        # `transport` existe para os testes de contrato injetarem um
        # `httpx.MockTransport` com tráfego gravado; `cert` existe para o dia
        # do mTLS (Santander, e o BB em alguns fluxos). Ambos já são aceitos
        # pelo construtor do httpx — nada de infraestrutura própria.
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers or {},
            timeout=timeout,
            transport=transport,
            cert=cert,
        )

    # ── chamada ──────────────────────────────────────────────────────────
    def requisitar(
        self,
        metodo: str,
        caminho: str,
        *,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        """Faz a chamada e devolve o corpo JSON, ou levanta `ErroProvedor`."""
        try:
            resposta = self._client.request(
                metodo, caminho, json=json, params=params
            )
        except httpx.TimeoutException as e:
            raise ErroProvedor(
                self.provedor, f"Timeout ao chamar {metodo} {caminho}",
                status=504, retentavel=True,
            ) from e
        except httpx.HTTPError as e:
            raise ErroProvedor(
                self.provedor, f"Falha de conexão: {e}",
                status=502, retentavel=True,
            ) from e

        if resposta.status_code >= 400:
            raise self._traduzir_erro(resposta, metodo, caminho)

        if resposta.status_code == 204 or not resposta.content:
            return {}
        try:
            return resposta.json()
        except ValueError as e:
            raise ErroProvedor(
                self.provedor,
                f"Resposta não-JSON em {metodo} {caminho}",
                status=502,
            ) from e

    def _traduzir_erro(
        self, resposta: httpx.Response, metodo: str, caminho: str
    ) -> ErroProvedor:
        corpo: Any = {}
        try:
            corpo = resposta.json()
        except ValueError:
            corpo = {"texto": resposta.text[:300]}

        return ErroProvedor(
            self.provedor,
            self._mensagem(corpo) or f"{metodo} {caminho} devolveu {resposta.status_code}",
            status=resposta.status_code,
            codigo=self._codigo(corpo),
            trace_id=self._trace_id(resposta, corpo),
            # 5xx e 429 passam; 4xx de payload não — insistir num corpo
            # inválido só queima requisição contra o rate limit.
            retentavel=resposta.status_code >= 500 or resposta.status_code == 429,
        )

    # ── extração, tolerante a formatos diferentes ────────────────────────
    @staticmethod
    def _mensagem(corpo: Any) -> Optional[str]:
        if not isinstance(corpo, dict):
            return None
        # Asaas: {"errors": [{"code": ..., "description": ...}]}
        erros = corpo.get("errors")
        if isinstance(erros, list) and erros:
            partes = [
                str(e.get("description") or e.get("message"))
                for e in erros
                if isinstance(e, dict)
            ]
            if partes:
                return "; ".join(p for p in partes if p and p != "None")
        # Santander/BB: {"_message": ..., "_details": ...}
        for chave in ("_message", "message", "mensagem", "erro", "texto"):
            valor = corpo.get(chave)
            if valor:
                return str(valor)
        return None

    @staticmethod
    def _codigo(corpo: Any) -> Optional[str]:
        if not isinstance(corpo, dict):
            return None
        erros = corpo.get("errors")
        if isinstance(erros, list) and erros and isinstance(erros[0], dict):
            codigo = erros[0].get("code")
            if codigo:
                return str(codigo)
        for chave in ("_errorCode", "code", "codigo"):
            valor = corpo.get(chave)
            if valor:
                return str(valor)
        return None

    @staticmethod
    def _trace_id(resposta: httpx.Response, corpo: Any) -> Optional[str]:
        if isinstance(corpo, dict):
            for chave in ("_traceId", "traceId", "correlationId"):
                valor = corpo.get(chave)
                if valor:
                    return str(valor)
        for header in ("x-trace-id", "x-correlation-id", "x-request-id"):
            valor = resposta.headers.get(header)
            if valor:
                return valor
        return None

    def fechar(self) -> None:  # pragma: no cover - usado só em teardown
        self._client.close()
