"""Orçamento e-mail — send with PDF (R7) and reply watch (R8).

Send: the orçamento PDF (slice A writes ``pdf_key`` into the private ``igig``
bucket) leaves through the org's SMTP (seed ``EmailSender``), whose minted RFC
``Message-ID`` is recorded as an ``out`` row of ``orcamento_email``. When the
org also connected a Gmail mailbox, that address becomes the ``Reply-To`` —
it is the mailbox being WATCHED, so the lead's reply lands where we look.

Watch: Gmail ``users.watch`` → Pub/Sub push → ``POST /api/webhooks/gmail/push``
→ :func:`processar_notificacao`: ``list_history`` from the stored cursor →
``get_message_metadata`` → seed ``match_reply`` against the ``out`` rows the
reply's ``In-Reply-To``/``References`` name → ``in`` row, ``respondido_em``,
in-app notification + an e-mail to the org owner.

FastAPI-free: the router, the daily renewal job and tests all call in here;
refusals are :class:`RegraViolada`.
"""
from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone
from typing import Any

from noctusai_lib.integrations.email import Attachment, OutgoingEmail
from noctusai_lib.integrations.email.errors import EmailError
from noctusai_lib.integrations.gmail import (
    GmailClient,
    GmailHistoryExpiredError,
    GmailMessageMetadata,
    GmailPushNotification,
    match_reply,
    normalize_message_id,
)
from noctusai_lib.integrations.persistence import RecordNotFound

from app.email_deps import EmailSenderFactory, GmailClientFactory
from app.repositories import Repositorios
from app.repositories.email import (
    RepositoriosEmail,
    iter_todos_watches,
    repositorios_email,
    watches_por_email,
)
from app.services import email_config
from app.services.email_config import EmailSettings
from app.services.notificacoes import notificar
from app.services.regras import RegraViolada

logger = logging.getLogger(__name__)

__all__ = [
    "enviar_orcamento",
    "enviar_teste",
    "iniciar_watch",
    "processar_notificacao",
    "renovar_watches",
]

_STATUS_ENVIAVEIS = frozenset({"rascunho", "enviado"})
_MSGID = re.compile(r"<[^<>\s]+>")
_RECONCILIAR_MAX_PAGINAS = 5
TIPO_NOTIFICACAO = "orcamento_respondido"


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _moeda(valor: Any) -> str:
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        numero = 0.0
    inteiro, _, centavos = f"{numero:,.2f}".partition(".")
    return f"R$ {inteiro.replace(',', '.')},{centavos}"


def _data_br(valor: Any) -> str | None:
    if not valor:
        return None
    texto = str(valor)[:10]
    try:
        return datetime.strptime(texto, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return texto


# ── envio ────────────────────────────────────────────────────────────
def _corpo_html(orcamento: dict, lead: dict | None, mensagem: str | None, remetente: str) -> str:
    saudacao = f"Olá, {html.escape(str(lead.get('nome')))}!" if lead and lead.get("nome") else "Olá!"
    if mensagem:
        paragrafo = "<br>".join(html.escape(linha) for linha in mensagem.strip().splitlines())
    else:
        paragrafo = (
            "Segue em anexo a nossa proposta. Qualquer dúvida, é só responder a este e-mail."
        )
    validade = _data_br(orcamento.get("validade"))
    linha_validade = (
        f"<p style=\"margin:4px 0;color:#555\">Válida até <b>{validade}</b></p>" if validade else ""
    )
    return (
        "<div style=\"font-family:Arial,Helvetica,sans-serif;font-size:15px;color:#222;"
        "max-width:560px\">"
        f"<p>{saudacao}</p>"
        f"<p>{paragrafo}</p>"
        "<div style=\"border:1px solid #e5e5e5;border-radius:8px;padding:12px 16px;margin:16px 0\">"
        f"<p style=\"margin:0 0 4px;font-weight:bold\">{html.escape(str(orcamento.get('titulo') or 'Orçamento'))}</p>"
        f"<p style=\"margin:4px 0\">Investimento mensal: <b>{_moeda(orcamento.get('total_mensal'))}</b></p>"
        f"{linha_validade}"
        "<p style=\"margin:4px 0;color:#555\">Proposta completa no PDF em anexo.</p>"
        "</div>"
        f"<p>Atenciosamente,<br>{html.escape(remetente)}</p>"
        "</div>"
    )


def _corpo_texto(orcamento: dict, lead: dict | None, mensagem: str | None, remetente: str) -> str:
    saudacao = f"Olá, {lead.get('nome')}!" if lead and lead.get("nome") else "Olá!"
    linhas = [
        saudacao, "",
        mensagem.strip() if mensagem else
        "Segue em anexo a nossa proposta. Qualquer dúvida, é só responder a este e-mail.",
        "",
        f"{orcamento.get('titulo') or 'Orçamento'} — investimento mensal "
        f"{_moeda(orcamento.get('total_mensal'))}",
    ]
    validade = _data_br(orcamento.get("validade"))
    if validade:
        linhas.append(f"Válida até {validade}")
    linhas += ["", "Atenciosamente,", remetente]
    return "\n".join(linhas)


def _mailbox_observada(repos: Repositorios, org_id: str) -> str | None:
    registro = repos.integracao.por_canal(org_id, email_config.CANAL_GMAIL)
    if registro is None or not registro.get("token_cifrado") or not registro.get("ativo"):
        return None
    email = (registro.get("config") or {}).get("email") or registro.get("conta_externa")
    return str(email) if email else None


async def enviar_orcamento(
    repos: Repositorios,
    erepos: RepositoriosEmail,
    org_id: str,
    orcamento_id: str,
    *,
    para: list[str] | None,
    cc: list[str] | None,
    assunto: str | None,
    mensagem: str | None,
    sender_factory: EmailSenderFactory,
    storage: Any,
    bucket: str,
    settings: EmailSettings,
) -> tuple[dict, str]:
    """Send the orçamento PDF. Returns ``(orcamento_atualizado, message_id)``."""
    orcamento = repos.orcamento.buscar(org_id, orcamento_id)
    if orcamento.get("status") not in _STATUS_ENVIAVEIS:
        raise RegraViolada(
            409, "orcamento_bloqueado",
            f"Orçamento {orcamento.get('status')} não pode ser enviado.",
        )
    if not orcamento.get("pdf_key"):
        raise RegraViolada(409, "pdf_nao_gerado", "Gere o PDF do orçamento antes de enviar.")

    lead: dict | None = None
    if orcamento.get("lead_id"):
        try:
            lead = repos.lead.buscar(org_id, str(orcamento["lead_id"]))
        except RecordNotFound:
            logger.warning("orçamento %s aponta para lead ausente", orcamento_id)
    destinatarios = [p for p in (para or []) if p] or (
        [str(lead["email"])] if lead and lead.get("email") else []
    )
    if not destinatarios:
        raise RegraViolada(
            422, "email_destinatario_ausente",
            "O lead não tem e-mail cadastrado — informe o destinatário.",
        )

    config, origem = email_config.resolver_smtp(repos, org_id, settings)
    blob = await storage.get(bucket=bucket, key=str(orcamento["pdf_key"]))
    if blob is None:
        raise RegraViolada(
            409, "pdf_nao_gerado",
            "O PDF do orçamento não foi encontrado no armazenamento — gere-o novamente.",
        )

    remetente = config.from_name or config.from_email
    titulo = str(orcamento.get("titulo") or "Orçamento")
    versao = orcamento.get("versao") or 1
    assunto_final = (assunto or "").strip() or f"Proposta: {titulo} (v{versao})"
    observada = _mailbox_observada(repos, org_id)
    email = OutgoingEmail(
        to=destinatarios,
        cc=[c for c in (cc or []) if c],
        subject=assunto_final,
        html=_corpo_html(orcamento, lead, mensagem, remetente),
        text=_corpo_texto(orcamento, lead, mensagem, remetente),
        reply_to=observada if observada and observada.lower() != config.from_email.lower() else None,
        attachments=[Attachment(
            filename=f"orcamento-{titulo[:40].strip().replace(' ', '-').lower()}-v{versao}.pdf",
            content=blob.data,
            mime_type="application/pdf",
        )],
    )
    try:
        enviado = await sender_factory(config).send(email)
    except EmailError as erro:
        logger.error("envio do orçamento falhou org=%s orcamento=%s: %s", org_id, orcamento_id, erro)
        raise RegraViolada(502, "envio_falhou", f"Falha ao enviar o e-mail: {erro}") from erro

    agora = _agora()
    erepos.emails.criar(org_id, {
        "orcamento_id": orcamento_id,
        "direction": "out",
        "message_id": enviado.message_id,
        "thread_id": None,
        "from_addr": config.from_email,
        "subject": assunto_final,
        "snippet": (mensagem or "")[:200] or None,
        "occurred_at": agora,
    })
    atualizado = repos.orcamento.atualizar(org_id, orcamento_id, {
        "status": "enviado",
        "enviado_em": agora,
        "email_message_id": enviado.message_id,
    })
    logger.info(
        "orçamento enviado org=%s orcamento=%s para=%d smtp=%s",
        org_id, orcamento_id, len(destinatarios), origem,
    )
    return atualizado, enviado.message_id


async def enviar_teste(
    repos: Repositorios,
    org_id: str,
    para: str,
    *,
    sender_factory: EmailSenderFactory,
    settings: EmailSettings,
) -> str:
    config, origem = email_config.resolver_smtp(repos, org_id, settings)
    try:
        enviado = await sender_factory(config).send(OutgoingEmail(
            to=[para],
            subject="Teste de envio — IgIg",
            text="Este é um e-mail de teste enviado pela tela de Integrações do IgIg.",
            html="<p>Este é um e-mail de teste enviado pela tela de Integrações do IgIg.</p>",
        ))
    except EmailError as erro:
        logger.warning("teste de SMTP falhou org=%s origem=%s: %s", org_id, origem, erro)
        raise RegraViolada(502, "envio_falhou", f"Falha ao enviar o e-mail: {erro}") from erro
    return enviado.message_id


# ── watch ────────────────────────────────────────────────────────────
async def iniciar_watch(
    repos: Repositorios,
    erepos: RepositoriosEmail,
    org_id: str,
    email: str,
    client: GmailClient,
    settings: EmailSettings,
) -> bool:
    """Start the watch for a freshly connected mailbox. True when started.

    Missing GCP config ⇒ NOT attempted and logged at ERROR — never a fake
    success; the status endpoint reports ``configuracao_gcp_ok=false``.
    """
    gcp = email_config.gcp_config(settings)
    if gcp is None:
        logger.error(
            "gmail watch NÃO iniciado org=%s mailbox=%s: configuração GCP ausente (%s) — "
            "respostas de leads não serão detectadas",
            org_id, email, ", ".join(email_config.gcp_faltando(settings)),
        )
        return False
    try:
        resultado = await client.watch(gcp.topic)
    except Exception as erro:  # noqa: BLE001 — recorded + surfaced, connection stays
        logger.exception("gmail watch falhou org=%s mailbox=%s", org_id, email)
        repos.integracao.registrar_erro(org_id, email_config.CANAL_GMAIL, f"watch falhou: {erro}")
        return False
    erepos.watches.registrar(
        org_id, email=email, history_id=resultado.history_id,
        expiration=resultado.expiration, topic=gcp.topic,
    )
    logger.info("gmail watch ativo org=%s mailbox=%s expira=%s", org_id, email, resultado.expiration)
    return True


async def renovar_watches(
    admin_db: Any,
    repos: Repositorios,
    *,
    gmail_factory: GmailClientFactory,
    settings: EmailSettings,
) -> dict[str, int]:
    """Daily: re-``watch()`` every mailbox (a lapsed watch silently stops).

    Only the expiration moves — the history cursor is kept, so changes that
    arrived since the last processed push are still read.
    """
    gcp = email_config.gcp_config(settings)
    if gcp is None:
        logger.error(
            "renovação de gmail watch NÃO executada: configuração GCP ausente (%s)",
            ", ".join(email_config.gcp_faltando(settings)),
        )
        return {"renovados": 0, "falhas": 0, "ignorados": 0}
    renovados = falhas = ignorados = 0
    erepos = repositorios_email(repos.store)
    for watch in iter_todos_watches(admin_db):
        org_id = str(watch["org_id"])
        resolvido = email_config.credenciais_gmail(repos, org_id, settings)
        if resolvido is None:
            logger.warning("gmail watch org=%s sem credencial utilizável — não renovado", org_id)
            ignorados += 1
            continue
        creds, email = resolvido
        try:
            resultado = await gmail_factory(creds).watch(gcp.topic)
        except Exception as erro:  # noqa: BLE001 — per-org; the loop continues
            falhas += 1
            logger.exception("renovação do gmail watch falhou org=%s", org_id)
            repos.integracao.registrar_erro(org_id, email_config.CANAL_GMAIL, f"renovação falhou: {erro}")
            continue
        valores: dict[str, Any] = {
            "expiration": resultado.expiration.astimezone(timezone.utc).isoformat(),
            "topic": gcp.topic,
        }
        if not watch.get("history_id"):
            valores["history_id"] = resultado.history_id
        erepos.watches.atualizar(org_id, str(watch["id"]), valores)
        renovados += 1
    logger.info("gmail watch renovados=%d falhas=%d ignorados=%d", renovados, falhas, ignorados)
    return {"renovados": renovados, "falhas": falhas, "ignorados": ignorados}


# ── reply processing ─────────────────────────────────────────────────
def _header(meta: GmailMessageMetadata, nome: str) -> str:
    alvo = nome.lower()
    for chave, valor in meta.headers.items():
        if chave.lower() == alvo:
            return valor or ""
    return ""


def _candidatos(meta: GmailMessageMetadata) -> list[str]:
    """Stored-form variants of every id the reply points at."""
    valores: list[str] = []
    for nome in ("In-Reply-To", "References"):
        for token in _MSGID.findall(_header(meta, nome)):
            valores.append(token)
            normal = normalize_message_id(token)
            if normal:
                valores.append(f"<{normal}>")
    return list(dict.fromkeys(valores))


def _destinatarios_internos(
    repos: Repositorios, core: Any, org_id: str, orcamento: dict
) -> tuple[list[str], list[str]]:
    """``(user_ids para o in-app, e-mails dos donos)``."""
    donos = (
        core.table("noctus_users").select("id,email,org_role")
        .eq("org_id", org_id).eq("org_role", "owner").limit(20).execute().data
    ) or []
    responsavel: str | None = None
    if orcamento.get("negocio_id"):
        try:
            negocio = repos.store.get("negocio", org_id, str(orcamento["negocio_id"]))
            if negocio.get("responsavel_id"):
                responsavel = repos.profissional.buscar(
                    org_id, str(negocio["responsavel_id"])
                ).get("usuario_id")
        except RecordNotFound:
            logger.warning("orçamento %s: negócio/responsável ausente", orcamento.get("id"))
    usuarios = [str(responsavel)] if responsavel else [str(d["id"]) for d in donos]
    emails = [str(d["email"]) for d in donos if d.get("email")]
    return usuarios, emails


async def _avisar(
    repos: Repositorios,
    core: Any,
    org_id: str,
    orcamento: dict,
    remetente: str,
    snippet: str,
    sender_factory: EmailSenderFactory,
    settings: EmailSettings,
) -> None:
    usuarios, emails_donos = _destinatarios_internos(repos, core, org_id, orcamento)
    titulo = f"Resposta ao orçamento: {orcamento.get('titulo') or ''}".strip()
    link = f"/orcamentos?id={orcamento['id']}"
    try:
        notificar(
            core, org_id=org_id, user_ids=usuarios, tipo=TIPO_NOTIFICACAO,
            titulo=titulo, mensagem=f"{remetente}: {snippet}"[:500],
            metadata={"orcamento_id": str(orcamento["id"]), "link": link},
        )
    except Exception:  # noqa: BLE001 — the reply is already recorded
        logger.exception("falha na notificação in-app org=%s orcamento=%s", org_id, orcamento["id"])
    if not emails_donos:
        logger.warning("resposta ao orçamento %s: org=%s sem dono com e-mail", orcamento["id"], org_id)
        return
    try:
        config, _origem = email_config.resolver_smtp(repos, org_id, settings)
    except RegraViolada as erro:
        logger.warning(
            "resposta ao orçamento %s: e-mail ao dono NÃO enviado org=%s — %s",
            orcamento["id"], org_id, erro.mensagem,
        )
        return
    try:
        await sender_factory(config).send(OutgoingEmail(
            to=emails_donos,
            subject=titulo,
            text=f"{remetente} respondeu ao orçamento \"{orcamento.get('titulo')}\":\n\n{snippet}\n\n"
                 f"Abra no IgIg: {link}",
            html=(
                f"<p><b>{html.escape(remetente)}</b> respondeu ao orçamento "
                f"<b>{html.escape(str(orcamento.get('titulo') or ''))}</b>:</p>"
                f"<blockquote>{html.escape(snippet)}</blockquote>"
                f"<p>Abra no IgIg: {html.escape(link)}</p>"
            ),
        ))
    except EmailError:
        logger.exception("e-mail ao dono falhou org=%s orcamento=%s", org_id, orcamento["id"])


async def _processar_mensagem(
    repos: Repositorios,
    erepos: RepositoriosEmail,
    core: Any,
    org_id: str,
    meta: GmailMessageMetadata,
    sender_factory: EmailSenderFactory,
    settings: EmailSettings,
) -> bool:
    """Record one inbound message if it answers one of our orçamentos."""
    enviados = erepos.emails.enviados_com_ids(org_id, _candidatos(meta))
    threads = erepos.emails.enviados_na_thread(org_id, meta.thread_id) if meta.thread_id else []
    conhecidos = {str(e["message_id"]): e for e in [*enviados, *threads]}
    alvo = match_reply(
        meta.headers, list(conhecidos),
        thread_id=meta.thread_id,
        known_threads={str(e["thread_id"]): str(e["message_id"]) for e in threads},
    )
    if alvo is None:
        return False
    saida = conhecidos[alvo]
    proprio_id = _header(meta, "Message-ID").strip() or f"gmail:{meta.id}"
    if erepos.emails.por_message_id(org_id, proprio_id) is not None:
        return False  # redelivered push — already recorded
    agora = _agora()
    remetente = _header(meta, "From") or "(desconhecido)"
    erepos.emails.criar(org_id, {
        "orcamento_id": str(saida["orcamento_id"]),
        "direction": "in",
        "message_id": proprio_id,
        "thread_id": meta.thread_id,
        "from_addr": remetente[:500],
        "subject": _header(meta, "Subject")[:500] or None,
        "snippet": (meta.snippet or "")[:500] or None,
        "occurred_at": (meta.received_at.isoformat() if meta.received_at else agora),
    })
    if not saida.get("thread_id") and meta.thread_id:
        erepos.emails.atualizar(org_id, str(saida["id"]), {"thread_id": meta.thread_id})
    orcamento = repos.orcamento.buscar(org_id, str(saida["orcamento_id"]))
    if not orcamento.get("respondido_em"):
        orcamento = repos.orcamento.atualizar(org_id, str(orcamento["id"]), {"respondido_em": agora})
    logger.info("resposta registrada org=%s orcamento=%s", org_id, orcamento["id"])
    await _avisar(
        repos, core, org_id, orcamento, remetente, meta.snippet or "", sender_factory, settings,
    )
    return True


async def _refs_desde(client: GmailClient, cursor: str) -> tuple[list[str], str | None]:
    """``(message ids, new cursor)``; on an expired cursor, reconcile the most
    recent INBOX pages and return ``None`` (caller re-watches for a new one)."""
    try:
        refs, novo = await client.list_history(cursor, label_id="INBOX")
        return [r.id for r in refs], novo
    except GmailHistoryExpiredError:
        logger.warning("gmail history expirado (cursor=%s) — reconciliando INBOX recente", cursor)
    ids: list[str] = []
    token: str | None = None
    for _ in range(_RECONCILIAR_MAX_PAGINAS):
        pagina = await client.list_messages(label="INBOX", page_token=token)
        ids.extend(m.id for m in pagina.items)
        token = pagina.next_page_token
        if not token:
            break
    return ids, None


async def processar_notificacao(
    admin_db: Any,
    repos: Repositorios,
    core: Any,
    nota: GmailPushNotification,
    *,
    gmail_factory: GmailClientFactory,
    sender_factory: EmailSenderFactory,
    settings: EmailSettings,
) -> dict[str, int]:
    """Handle one verified push. Idempotent (the in-row is unique per message)."""
    erepos = repositorios_email(repos.store)
    watches = watches_por_email(admin_db, nota.email_address)
    if not watches:
        logger.warning("push do gmail para mailbox sem watch: %s", nota.email_address)
    respostas = 0
    for watch in watches:
        org_id = str(watch["org_id"])
        resolvido = email_config.credenciais_gmail(repos, org_id, settings)
        if resolvido is None:
            logger.warning("push do gmail org=%s: mailbox sem credencial utilizável", org_id)
            continue
        creds, _email = resolvido
        client = gmail_factory(creds)
        cursor = str(watch.get("history_id") or "")
        if not cursor:
            erepos.watches.avancar_cursor(org_id, str(watch["id"]), nota.history_id)
            logger.warning("gmail watch org=%s sem cursor — iniciado em %s", org_id, nota.history_id)
            continue
        ids, novo_cursor = await _refs_desde(client, cursor)
        for message_id in ids:
            meta = await client.get_message_metadata(message_id)
            if meta is None:
                continue
            if await _processar_mensagem(
                repos, erepos, core, org_id, meta, sender_factory, settings,
            ):
                respostas += 1
        if novo_cursor is None:
            gcp = email_config.gcp_config(settings)
            if gcp is not None:
                novo_cursor = (await client.watch(gcp.topic)).history_id
            else:
                novo_cursor = nota.history_id
        erepos.watches.avancar_cursor(org_id, str(watch["id"]), novo_cursor)
    return {"watches": len(watches), "respostas": respostas}
