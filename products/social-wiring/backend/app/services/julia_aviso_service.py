"""Per-org privacy notice for Julia (contract section 11.2).

Pure + table-access logic; the router stays thin. The notice belongs to the
org (the LGPD controller). A default pt-BR template is created lazily on the
first read; anything unknown renders as ``A_DEFINIR``.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from noctusai_lib.primitives.accents import fold_accents_ascii

logger = logging.getLogger(__name__)

TABLE = "julia_aviso_privacidade"
A_DEFINIR = "a definir"
LINK_TOKEN = "{link}"
#: The default opening message is a DATA row (`julia_textos_padrao`, migration 290), not a string in code: it names the
#: agent through the `{agente}` placeholder (resolved from agents' status name at send time) and the controller through
#: `{empresa}` / `{link}`.
TABLE_TEXTOS = "julia_textos_padrao"
TEXTO_MENSAGEM_INICIAL = "mensagem_inicial"
AGENTE_TOKEN = "{agente}"
RETENCAO_DIAS = 180

# Fields the PUBLIC endpoint may expose -- nothing else, ever.
CAMPOS_PUBLICOS = (
    "titulo", "empresa_nome", "contato_email", "contato_whatsapp",
    "secoes", "versao", "atualizado_em",
)


def slugify(nome: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold_accents_ascii(nome).lower()).strip("-")[:60]


def secoes_padrao(empresa: str, contato_email: str | None, contato_whatsapp: str | None) -> list[dict[str, Any]]:
    como = (
        f'Responda "apagar meus dados" nesta conversa ou escreva para {contato_email}.'
        if contato_email
        else f'Responda "apagar meus dados" nesta conversa ou use o e-mail de contato: {A_DEFINIR}.'
    )
    return [
        {"n": "1", "title": "Quem é o controlador", "blocks": [
            {"p": f"O controlador dos seus dados pessoais é {empresa}."},
            {"p": f"Contato para assuntos de privacidade: e-mail {contato_email or A_DEFINIR}; "
                  f"WhatsApp {contato_whatsapp or A_DEFINIR}."},
        ]},
        {"n": "2", "title": "Quais dados coletamos", "blocks": [
            {"p": "Ao conversar com nossa assistente virtual (Julia) pelo WhatsApp, coletamos:"},
            {"ul": ["nome", "número de telefone", "o conteúdo das mensagens que você envia",
                    "suas preferências de imóvel (por exemplo, comprar ou alugar, região, faixa de valor)"]},
        ]},
        {"n": "3", "title": "Para que usamos seus dados", "blocks": [
            {"p": "Usamos os dados para responder e qualificar consultas imobiliárias e encaminhar "
                  "você a um corretor humano."},
        ]},
        {"n": "4", "title": "Base legal", "blocks": [
            {"p": "O tratamento se apoia no art. 7º, V (procedimentos preliminares relacionados a "
                  "contrato a pedido do titular) e IX (legítimo interesse) da Lei Geral de Proteção "
                  "de Dados (LGPD, Lei 13.709/2018)."},
        ]},
        {"n": "5", "title": "Com quem compartilhamos", "blocks": [
            {"p": "Para prestar o atendimento, os dados são tratados por operadores:"},
            {"ul": ["provedor da infraestrutura do WhatsApp (WAHA), que transporta as mensagens",
                    "provedor de inteligência artificial (OpenAI), que gera as respostas — "
                    "isso envolve transferência internacional de dados",
                    f"NoctusAI, operadora da plataforma usada por {empresa}"]},
        ]},
        {"n": "6", "title": "Por quanto tempo guardamos", "blocks": [
            {"p": f"Mantemos os dados da conversa por {RETENCAO_DIAS} dias; depois disso eles são "
                  "excluídos ou anonimizados."},
        ]},
        {"n": "7", "title": "Seus direitos e como exercê-los", "blocks": [
            {"p": "Conforme o art. 18 da LGPD, você pode pedir confirmação do tratamento, acesso, "
                  "correção, anonimização, portabilidade, eliminação dos dados e informações sobre "
                  "compartilhamento, além de revogar o consentimento."},
            {"p": como},
        ]},
        {"n": "8", "title": "Decisões automatizadas", "blocks": [
            {"p": "A assistente virtual não toma decisões automatizadas com efeitos jurídicos sobre "
                  "você. Um corretor humano acompanha o atendimento."},
        ]},
        {"n": "9", "title": "Atualizações deste aviso", "blocks": [
            {"p": "Este aviso pode ser atualizado; a versão e a data de atualização aparecem no topo "
                  "da página."},
        ]},
    ]


def contem_link(mensagem: str) -> bool:
    return LINK_TOKEN in (mensagem or "")


def _tabela(client: Any):
    return client.table(TABLE)


def texto_padrao(client: Any, chave: str) -> str:
    """A platform default text from `julia_textos_padrao`. There is NO fallback string in code: a missing row is a
    503 (`texto_padrao_ausente`) -- the migration that seeds it was not applied."""
    from noctusai_lib.primitives.exceptions import AppException

    rows = client.table(TABLE_TEXTOS).select("conteudo").eq("chave", chave).limit(1).execute().data or []
    texto = (rows[0].get("conteudo") or "").strip() if rows else ""
    if not texto:
        raise AppException("texto_padrao_ausente", f"O texto padrão '{chave}' não está cadastrado.", status_code=503)
    return texto


def buscar_por_org(client: Any, org_id: UUID) -> dict[str, Any] | None:
    resp = _tabela(client).select("*").eq("org_id", str(org_id)).limit(1).execute()
    rows = resp.data or []
    return rows[0] if rows else None


def buscar_por_slug(client: Any, slug: str) -> dict[str, Any] | None:
    resp = _tabela(client).select("*").eq("slug", slug).limit(1).execute()
    rows = resp.data or []
    return rows[0] if rows else None


def nome_da_org(core_client: Any, org_id: UUID) -> str | None:
    """`public.organizations.nome`; None when unreadable/unknown (logged)."""
    try:
        resp = (
            core_client.table("organizations")
            .select("nome").eq("id", str(org_id)).limit(1).execute()
        )
    except Exception as exc:
        logger.error("julia_aviso: organization name lookup failed org=%s (%s)", org_id, type(exc).__name__)
        return None
    rows = resp.data or []
    return (rows[0].get("nome") or None) if rows else None


def _slug_unico(client: Any, base: str) -> str:
    base = base or "aviso"
    candidato, n = base, 2
    while buscar_por_slug(client, candidato) is not None:
        candidato = f"{base}-{n}"
        n += 1
    return candidato


def obter_ou_criar(client: Any, core_client: Any, org_id: UUID) -> dict[str, Any]:
    """The org's notice; creates the default-template row on first read."""
    existente = buscar_por_org(client, org_id)
    if existente:
        return existente
    nome = nome_da_org(core_client, org_id)
    empresa = nome or A_DEFINIR
    row = {
        "org_id": str(org_id),
        "slug": _slug_unico(client, slugify(nome or "") or f"aviso-{str(org_id)[:8]}"),
        "titulo": "Aviso de privacidade",
        "empresa_nome": nome,  # NULL when unknown -> the Agente page warns
        "contato_email": None,
        "contato_whatsapp": None,
        "secoes": secoes_padrao(empresa, None, None),
        "mensagem_inicial": texto_padrao(client, TEXTO_MENSAGEM_INICIAL),
        "versao": 1,
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
        "atualizado_por": None,
    }
    try:
        _tabela(client).insert(row).execute()
    except Exception:
        # Concurrent first read won the insert (org_id PK / slug UNIQUE).
        ganhou = buscar_por_org(client, org_id)
        if ganhou:
            return ganhou
        raise
    return row


def atualizar(client: Any, org_id: UUID, atual: dict[str, Any], dados: dict[str, Any], usuario_id: Any) -> dict[str, Any]:
    novo = {
        **dados,
        "versao": int(atual.get("versao") or 1) + 1,
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
        "atualizado_por": str(usuario_id) if usuario_id else None,
    }
    _tabela(client).update(novo).eq("org_id", str(org_id)).execute()
    return {**atual, **novo}


def somente_publico(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row.get(k) for k in CAMPOS_PUBLICOS}


def incompleto(row: dict[str, Any]) -> bool:
    """True while the notice still shows 'a definir' placeholders."""
    if not (row.get("empresa_nome") or "").strip():
        return True
    return A_DEFINIR in str(row.get("secoes") or "")
