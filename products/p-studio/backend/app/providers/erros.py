"""Erro de provedor externo.

Deliberadamente **não** é `HTTPException`, ao contrário do que `database.execute`
faz com os erros do PostgREST. A diferença é o contexto: falha do PostgREST é
sempre dentro de uma requisição, então traduzir para HTTP na hora é correto.
Falha de provedor acontece também no webhook e no reprocessamento em lote,
onde levantar erro HTTP é resposta errada — no caso do webhook é pior que
errada, porque o Asaas interrompe a fila de entrega após 15 respostas não-2xx
consecutivas.

Então o service levanta `ErroProvedor`, e um `@app.exception_handler` traduz
para HTTP só quando a chamada veio de uma rota.
"""
from typing import Optional


class ErroProvedor(Exception):
    """Falha ao falar com o provedor de cobrança."""

    def __init__(
        self,
        provedor: str,
        mensagem: str,
        *,
        status: Optional[int] = None,
        codigo: Optional[str] = None,
        trace_id: Optional[str] = None,
        retentavel: bool = False,
    ) -> None:
        self.provedor = provedor
        self.mensagem = mensagem
        self.status = status
        self.codigo = codigo
        # O Santander chama de `_traceId` e é o que o suporte pede; o BB
        # devolve um id de correlação equivalente. Sempre logar.
        self.trace_id = trace_id
        # Timeout e 5xx valem nova tentativa; 400 e 422 não — o payload está
        # errado e insistir só queima requisição.
        self.retentavel = retentavel
        super().__init__(f"[{provedor}] {mensagem}")

    def __repr__(self) -> str:  # pragma: no cover - diagnóstico
        return (
            f"ErroProvedor(provedor={self.provedor!r}, status={self.status!r}, "
            f"codigo={self.codigo!r}, trace_id={self.trace_id!r}, "
            f"retentavel={self.retentavel!r}, mensagem={self.mensagem!r})"
        )


class ProvedorNaoConfigurado(ErroProvedor):
    """Credencial ausente. Mesma forma do guard de `get_admin_client()`:
    o app sobe sem a credencial e só reclama quando alguém tenta usar."""

    def __init__(self, provedor: str, variavel: str) -> None:
        super().__init__(
            provedor,
            f"Integração com {provedor} não configurada — defina {variavel}.",
            status=503,
        )
