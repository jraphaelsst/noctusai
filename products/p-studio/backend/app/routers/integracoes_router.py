"""Webhook do provedor de cobrança e reprocessamento da fila.

A rota do webhook é a **única pública que escreve** no sistema. Ela não usa
`get_current_user` porque quem chama é o provedor, não o navegador — a
autenticação é um segredo compartilhado no header.

Sobre responder 200 em quase tudo: o Asaas interrompe a fila de entrega após
15 respostas não-2xx consecutivas, e só volta com reativação manual no painel.
Devolver 500 num evento que não sabemos tratar custa a conciliação de todos os
outros pagamentos. Então a única rejeição normal é 401 — o resto é gravado e
respondido 200, e a rota autenticada de reprocessamento drena o que falhou.
"""
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from app.config import settings
from app.database import get_admin_client
from app.dependencies import CurrentUser, get_current_user, get_provedor_cobranca
from app.providers.tipos import ProvedorCobranca
from app.services.integracao_service import IntegracaoService

router = APIRouter(prefix="/api/integracoes", tags=["integracoes"])


def verificar_token_asaas(
    token: Optional[str] = Header(default=None, alias="asaas-access-token"),
) -> None:
    """Autentica o webhook pelo segredo compartilhado.

    O Asaas **não assina o corpo com HMAC** — o que existe é um token que você
    define no painel ao cadastrar o webhook e que volta neste header em toda
    notificação. Como não é preciso ler o corpo cru para validar, nenhuma rota
    precisa virar `async def` só por causa disto.

    `compare_digest` porque é comparação de segredo.
    """
    esperado = settings.asaas_webhook_token
    if not esperado:
        # 503 e não 401: o problema é nosso, não de quem chamou. E fica
        # explícito no log em vez de parecer credencial errada do provedor.
        raise HTTPException(
            status_code=503,
            detail="Webhook não configurado — defina ASAAS_WEBHOOK_TOKEN.",
        )
    if not secrets.compare_digest(token or "", esperado):
        raise HTTPException(status_code=401, detail="Token de webhook inválido")


@router.post("/asaas/webhook")
def webhook_asaas(
    corpo: dict,
    _: None = Depends(verificar_token_asaas),
    provedor: ProvedorCobranca = Depends(get_provedor_cobranca),
):
    """Recebe notificação de cobrança.

    Usa o client service-role: a chamada não traz JWT, então não há client
    RLS-scoped a construir. É o primeiro chamador real de `get_admin_client()`,
    que existia justamente para operações administrativas como esta.
    """
    servico = IntegracaoService(get_admin_client(), provedor)
    return servico.receber(corpo)


@router.get("/eventos")
def listar_eventos(
    user: CurrentUser = Depends(get_current_user),
    provedor: ProvedorCobranca = Depends(get_provedor_cobranca),
):
    """Log dos eventos recebidos. Lê com o client do usuário — aqui a RLS vale."""
    return IntegracaoService(user.db, provedor).pendentes()


@router.post("/reprocessar")
def reprocessar(
    user: CurrentUser = Depends(get_current_user),
    provedor: ProvedorCobranca = Depends(get_provedor_cobranca),
):
    """Drena os eventos que falharam ao processar.

    Autenticada de propósito: é ação administrativa, e reprocessar em massa
    deve ser um ato deliberado de alguém da equipe.
    """
    return IntegracaoService(user.db, provedor).reprocessar()
