"""Gestão das credenciais do provedor de cobrança — leitura, escrita e o
ambiente ativo.

Roda sempre com client **service-role**: `provedor_credenciais` não tem policy
de leitura para `authenticated` (migration 008), e o webhook chega sem JWT.
A autorização de quem pode mexer é do router (`get_current_user`), não daqui —
este service já recebeu a decisão tomada.

O segredo NUNCA sai deste módulo em claro por um caminho HTTP: `status()`
devolve máscara, e só `credencial(...)` — consumido pelo adapter e pelo guard
do webhook — devolve o bundle decifrado.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Optional

from app.database import execute
from app.services.credenciais import (
    AMBIENTES,
    BASE_URL_POR_AMBIENTE,
    CredentialDecryptError,
    build_credential_store,
    chave_provider,
    mascarar,
    validar_chave_para_ambiente,
)

PROVEDOR_PADRAO = "asaas"
_TABELA_CONFIG = "integracao_config"


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def gerar_webhook_token() -> str:
    """Segredo compartilhado do webhook, com entropia de verdade.

    Gerado pelo backend e mostrado ao usuário para colar no painel do Asaas —
    o caminho inverso (usuário inventa) produz segredos fracos e é a razão de
    esta função existir em vez de um campo de texto livre obrigatório.
    """
    return secrets.token_urlsafe(32)


class CredenciaisService:
    """CRUD das credenciais + o seletor de ambiente."""

    def __init__(self, admin_db, org_id: str) -> None:
        self.db = admin_db
        self.org_id = org_id
        self._store = build_credential_store(admin_db)

    # ── ambiente ativo ───────────────────────────────────────────────────
    def ambiente_ativo(self) -> str:
        """O ambiente configurado, `sandbox` se a org nunca escolheu.

        O default vive em dois lugares (o `DEFAULT` da coluna e este
        fallback) porque a linha pode simplesmente não existir ainda. Os dois
        dizem `sandbox` pelo mesmo motivo: um deploy que não escolheu não pode
        emitir boleto real por omissão.
        """
        rows = execute(
            self.db.table(_TABELA_CONFIG)
            .select("ambiente")
            .eq("org_id", self.org_id)
            .limit(1)
        ).data or []
        return rows[0]["ambiente"] if rows else "sandbox"

    def definir_ambiente(self, ambiente: str) -> str:
        if ambiente not in AMBIENTES:
            raise ValueError(
                f"Ambiente desconhecido: {ambiente!r}. "
                f"Aceitos: {', '.join(AMBIENTES)}."
            )
        execute(
            self.db.table(_TABELA_CONFIG).upsert(
                {
                    "org_id": self.org_id,
                    "provedor": PROVEDOR_PADRAO,
                    "ambiente": ambiente,
                    "atualizado_em": _agora(),
                },
                on_conflict="org_id",
            )
        )
        return ambiente

    # ── credenciais ──────────────────────────────────────────────────────
    def credencial(self, ambiente: str) -> Optional[dict]:
        """Bundle DECIFRADO `{"api_key", "webhook_token"}`, ou `None`.

        Propaga `CredentialDecryptError` de propósito: uma linha que existe e
        não decifra é chave errada / rotação incompleta, e devolver `None` ali
        faria o adapter falhar com "não configurado" — a mensagem errada, longe
        da causa.
        """
        stored = self._store.get(self.org_id, chave_provider(PROVEDOR_PADRAO, ambiente))
        return dict(stored.tokens) if stored else None

    def salvar(
        self,
        ambiente: str,
        api_key: str,
        webhook_token: Optional[str] = None,
    ) -> dict:
        """Grava (ou substitui) a credencial de um ambiente.

        `webhook_token=None` PRESERVA o token existente em vez de apagá-lo —
        trocar a chave de API não deveria derrubar um webhook já registrado no
        painel do Asaas. Só um valor explícito substitui; se não havia nenhum,
        um é gerado.
        """
        api_key = (api_key or "").strip()
        if not api_key:
            raise ValueError("Chave de API vazia.")
        validar_chave_para_ambiente(api_key, ambiente)

        anterior = self.credencial(ambiente) or {}
        token = (
            webhook_token.strip()
            if webhook_token and webhook_token.strip()
            else anterior.get("webhook_token") or gerar_webhook_token()
        )

        self._store.put(
            self.org_id,
            chave_provider(PROVEDOR_PADRAO, ambiente),
            {"api_key": api_key, "webhook_token": token},
            # Máscara em texto claro no `metadata`: a UI lista os ambientes
            # sem que o backend precise decifrar N bundles só para desenhar a
            # tela. Não é segredo — é o que já mostramos.
            metadata={
                "api_key_mascarada": mascarar(api_key),
                "atualizado_em": _agora(),
            },
        )
        return self.status_de(ambiente)

    def remover(self, ambiente: str) -> bool:
        return self._store.delete(
            self.org_id, chave_provider(PROVEDOR_PADRAO, ambiente)
        )

    # ── leitura para a UI (sempre mascarada) ─────────────────────────────
    def status_de(self, ambiente: str) -> dict:
        """Status de UM ambiente. Nunca carrega segredo."""
        provider = chave_provider(PROVEDOR_PADRAO, ambiente)
        stored = None
        erro_decifra = False
        try:
            stored = self._store.get(self.org_id, provider)
        except CredentialDecryptError:
            # A linha existe e não abre. Dizer isso é melhor que "não
            # configurado", que mandaria o dono recadastrar uma chave que já
            # está lá — e o recadastro mascararia o problema real (a
            # ENCRYPTION_KEY do deploy mudou).
            erro_decifra = True

        if erro_decifra:
            return {
                "ambiente": ambiente,
                "configurado": True,
                "erro": "Credencial gravada não pôde ser decifrada — a "
                        "ENCRYPTION_KEY deste deploy não é a que a cifrou.",
                "api_key_mascarada": None,
                "webhook_token_configurado": False,
                "base_url": BASE_URL_POR_AMBIENTE[ambiente],
                "atualizado_em": None,
            }

        if stored is None:
            return {
                "ambiente": ambiente,
                "configurado": False,
                "erro": None,
                "api_key_mascarada": None,
                "webhook_token_configurado": False,
                "base_url": BASE_URL_POR_AMBIENTE[ambiente],
                "atualizado_em": None,
            }

        metadata = stored.metadata or {}
        return {
            "ambiente": ambiente,
            "configurado": True,
            "erro": None,
            "api_key_mascarada": metadata.get("api_key_mascarada")
            or mascarar(stored.tokens.get("api_key", "")),
            "webhook_token_configurado": bool(stored.tokens.get("webhook_token")),
            "base_url": BASE_URL_POR_AMBIENTE[ambiente],
            "atualizado_em": metadata.get("atualizado_em")
            or (stored.updated_at.isoformat() if stored.updated_at else None),
        }

    def status(self) -> dict:
        return {
            "provedor": PROVEDOR_PADRAO,
            "ambiente_ativo": self.ambiente_ativo(),
            "ambientes": [self.status_de(a) for a in AMBIENTES],
        }

    def webhook_token(self, ambiente: str) -> Optional[str]:
        """O segredo do webhook em claro — para MOSTRAR ao dono uma vez.

        Existe porque o token precisa ser colado no painel do Asaas, e o
        backend é quem o gerou. Rota autenticada, e só ela.
        """
        bundle = self.credencial(ambiente) or {}
        return bundle.get("webhook_token") or None

    def ambientes_configurados(self) -> list[str]:
        """Ambientes com credencial gravada. Não decifra nada."""
        providers = set(self._store.list_providers(self.org_id))
        return [
            a for a in AMBIENTES
            if chave_provider(PROVEDOR_PADRAO, a) in providers
        ]
