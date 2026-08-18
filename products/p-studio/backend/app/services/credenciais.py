"""Credenciais do provedor de cobrança — seam de consumo sobre o `token_store`
do seed.

A persistência cifrada NÃO é escrita aqui: ela é
`noctusai_lib.security.token_store` (Protocol + Fake + Real + factory, Fernet
sobre uma coluna TEXT). Este módulo é o ponto onde o P Studio a consome, e
concentra as três coisas que são do PRODUTO e não do seed:

1. **O check alto de chave ausente.** A factory do seed devolve um Fake
   silencioso quando `fernet_key` não é passada — comportamento correto para
   dev/teste e desastroso em produção, onde significaria "gravei sua chave de
   API" quando na verdade ela ficou num dicionário em memória que morre com o
   processo. Aqui isso vira `EncryptionNotConfigured`, que os routers mapeiam
   para 503. Mesma escolha que o `credential_vault.py` do social-wiring fez
   pelo mesmo motivo.

2. **O vocabulário `(provedor, ambiente)` → `provider`.** A chave natural do
   store é `(org_id, provider)`; o P Studio precisa de sandbox e produção
   coexistindo. `chave_provider("asaas", "sandbox") == "asaas_sandbox"` é a
   tradução, em UM lugar, para os dois lados nunca divergirem para strings
   diferentes — o modo de falha "conectado mas sem dados" que o
   `credential_resolvers.py` do seed documenta.

3. **A máscara.** O segredo nunca sai daqui em claro para o HTTP. `_mascarar`
   é o que a UI recebe.

N=2, não N=3: `encryption_key` como campo de settings existe hoje só no
social-wiring; este produto é o segundo. Pela regra de recorrência isso é
TRIAGEM, não formalização obrigatória — se um terceiro produto precisar, o
campo sobe para `ProductSettings` no seed.
→ `KB § PATTERNS/architect/project-execution.md` (regra de recorrência).
"""
from __future__ import annotations

from typing import Optional

from noctusai_lib.security.token_store import (
    CredentialDecryptError,
    CredentialStore,
    StoredCredential,
    make_credential_store,
)

from app.config import settings

__all__ = [
    "AMBIENTES",
    "CredentialDecryptError",
    "CredentialStore",
    "EncryptionNotConfigured",
    "StoredCredential",
    "TABELA",
    "ambiente_de_chave",
    "build_credential_store",
    "chave_provider",
    "mascarar",
    "validar_chave_para_ambiente",
]

TABELA = "provedor_credenciais"

AMBIENTES: tuple[str, ...] = ("sandbox", "producao")

# Prefixo da chave do Asaas → ambiente a que ela pertence. A chave é
# exclusiva do ambiente: uma chave de produção no sandbox devolve 401
# `invalid_environment` (verificado contra a API viva em 13/08/2026, ver
# `app/providers/asaas.py`). Conferir no momento da GRAVAÇÃO transforma um
# 401 futuro e distante — possivelmente dentro de um webhook, onde ninguém
# está olhando — numa mensagem imediata na tela de quem colou a chave.
_PREFIXO_AMBIENTE: dict[str, str] = {
    "$aact_hmlg_": "sandbox",
    "$aact_prod_": "producao",
}

# URL base por ambiente. Anda junto com a chave por construção, em vez de ser
# uma env var separada que pode divergir dela.
BASE_URL_POR_AMBIENTE: dict[str, str] = {
    "sandbox": "https://api-sandbox.asaas.com/v3",
    "producao": "https://api.asaas.com/v3",
}


class EncryptionNotConfigured(RuntimeError):
    """`ENCRYPTION_KEY` ausente ou malformada — recusa gravar em claro.

    Local do produto, não do seed: a factory do seed degrada para Fake em
    silêncio; aqui a ausência da chave é uma lacuna de configuração do deploy
    e precisa ser dita alto (503), nunca absorvida.
    """


def chave_provider(provedor: str, ambiente: str) -> str:
    """`("asaas", "sandbox")` → `"asaas_sandbox"`.

    Único lugar que compõe a string. Os dois lados (escrita pela UI, leitura
    pelo adapter) chamam esta função — nunca concatenam à mão.
    """
    if ambiente not in AMBIENTES:
        raise ValueError(
            f"Ambiente desconhecido: {ambiente!r}. Aceitos: {', '.join(AMBIENTES)}."
        )
    return f"{provedor}_{ambiente}"


def ambiente_de_chave(api_key: str) -> Optional[str]:
    """O ambiente que o prefixo da chave declara, ou `None` se não reconhecido.

    `None` não é erro por si — só o `validar_chave_para_ambiente` decide.
    """
    for prefixo, ambiente in _PREFIXO_AMBIENTE.items():
        if api_key.startswith(prefixo):
            return ambiente
    return None


def validar_chave_para_ambiente(api_key: str, ambiente: str) -> None:
    """Levanta `ValueError` se a chave não pertence ao ambiente declarado.

    Uma chave de prefixo DESCONHECIDO passa: o Asaas pode introduzir prefixos
    novos, e recusar o que não conhecemos travaria o produto por uma tabela
    desatualizada. Recusamos só a contradição explícita — prefixo conhecido
    que aponta para o outro ambiente. Errar para o lado de deixar passar é
    seguro aqui porque o adapter confere de novo contra a API real.
    """
    declarado = ambiente_de_chave(api_key)
    if declarado is not None and declarado != ambiente:
        raise ValueError(
            f"Esta chave é do ambiente '{declarado}' (prefixo "
            f"'{api_key[:11]}…'), mas está sendo salva como '{ambiente}'. "
            "Uma chave de produção no sandbox — ou o inverso — devolve 401 "
            "`invalid_environment` na primeira cobrança."
        )


def mascarar(api_key: str) -> str:
    """`"$aact_prod_000Mzk…f317"` — prefixo do ambiente + últimos 4.

    O suficiente para o dono confirmar QUAL chave está lá sem que a resposta
    HTTP carregue o segredo. Chave curta demais para mascarar com segurança
    vira só o prefixo — nunca a chave inteira.
    """
    if not api_key:
        return ""
    if len(api_key) <= 16:
        return f"{api_key[:6]}…"
    return f"{api_key[:11]}…{api_key[-4:]}"


def build_credential_store(client) -> CredentialStore:
    """O store cifrado, sobre um client admin (service-role) do schema.

    `client` precisa ser service-role: a tabela `provedor_credenciais` não tem
    policy de leitura para `authenticated` de propósito (ver migration 008), e
    o webhook chega sem JWT nenhum.
    """
    chave = (settings.encryption_key or "").strip()
    if not chave:
        raise EncryptionNotConfigured(
            "ENCRYPTION_KEY não configurada neste deploy — sem ela a chave do "
            "provedor seria gravada em claro. Gere com: python -c "
            "\"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    try:
        # Valida o formato ANTES de qualquer escrita. Uma chave malformada
        # descoberta só na hora de decifrar deixaria uma linha ilegível no
        # banco — e `CredentialDecryptError` apontaria para o lugar errado.
        from cryptography.fernet import Fernet

        Fernet(chave.encode())
    except Exception as exc:  # noqa: BLE001 — reempacota alto, não engole
        raise EncryptionNotConfigured(
            f"ENCRYPTION_KEY malformada ({exc}). Precisa ser uma chave Fernet "
            "de 32 bytes em base64 url-safe."
        ) from exc

    return make_credential_store(
        client=client,
        fernet_key=chave.encode(),
        table=TABELA,
    )
