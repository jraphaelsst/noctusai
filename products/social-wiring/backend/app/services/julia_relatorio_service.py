"""Julia v3 reports, alerts and identification documents (CONTRACT julia-v2 section 12.3 / 12.5 / 12.8).

Julia (hosted in agents) qualifies the lead and DECIDES when to hand off. At every hand-off / conclusion agents builds a
`relatorio` (ready-to-send `texto` + structured data); when something goes wrong with the lead it raises an `alerta`; when
the lead sends an ID document it raises `documento_identificacao`. SW applies all three AFTER the reply was sent (the
reply is never undone by this bookkeeping -- every public function here swallows and logs, nothing raises into the turn):

  report   `handoff` / `lead_pronto` action carrying `relatorio`
             -> a `julia_relatorios` row (tipo handoff | conclusao) on the lead card
             -> WhatsApp `relatorio.texto` to the org's DESTINATION, one message per paragraph (blank-line split)
             -> the existing in-app hand-off notice is untouched (`julia_agente_service.notificar_handoff`).
           An agents build that sends no `relatorio` still gets a hand-off report, built from the hand-off note.
  alerta   `alerta {tipo, descricao, alerta_id}` -> a `julia_relatorios` row (tipo alerta) + WhatsApp to the same destination
           (`⚠️ Julia — {tipo}\\nLead: ...`) + an in-app notice to the lead's attendant / the org admins.
  doc      `documento_identificacao {provider_message_id, tipo_provavel}` -> the lead's `clientes` card (found by the phone's
           `chave_canonica`, else created through the lead path -- `julia_envio_service.garantir_cliente`) -> that inbound
           media is fetched from WAHA and handed to `documento_intake_service.processar_midia` (classify -> identity
           extractor fills `clientes.extracao_*`). Any failure is an in-app alert, never silent.

DESTINATION (`julia_relatorio_destino`, one row per org): `modo numero` -> `numero_e164`; `modo responsavel` -> the lead's
responsavel's `julia_staff` number, else `numero_e164`; neither -> the row is stored with `envio_status='sem_destino'` and the
owners get the in-app alert `julia_relatorio_sem_destino` (refuse-not-null).

DELIVERY goes out through the outbound gate flow `interno` (`julia_envio_gate`): a staff notice, so it needs only that the
line exists -- NOT "Julia is on" -- and an alert still reaches the owner while Julia is being switched off. Idempotent: the
hand-off claims `(lote_hash, seq)` in `julia_acoes_aplicadas` (`julia_acoes_service.registrar_uma_vez`), every other action is
claimed by `aplicar` itself and only a NEWLY applied one is processed here; `julia_relatorios.chave` is unique per org.

Unknown / missing optional fields never crash: an older agents build keeps working during a deploy.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from urllib.parse import quote, urlparse
from uuid import UUID

from noctusai_lib.config.product_urls import resolve_product_url
from noctusai_lib.domain.notification_catalog import get_notification_gate
from noctusai_lib.domain.notifications import write_in_app
from noctusai_lib.primitives.exceptions import AppException

from app.services import julia_acoes_service, julia_envio_gate, julia_envio_service, julia_eventos_service as eventos
from app.services import julia_notificacoes_service as notificacoes
from app.services import julia_agente_service as julia
from app.services.identidade_mascara import ref as ref_log
from app.services.notification_kinds import PRODUCT as _CATALOG_PRODUCT
from app.services.whatsapp_outbound import send_paragraphs, split_for_whatsapp

logger = logging.getLogger(__name__)

T_DESTINO = "julia_relatorio_destino"
T_RELATORIOS = "julia_relatorios"
T_STAFF = "julia_staff"
T_AUDITORIA = "julia_relatorio_destino_auditoria"
T_MENSAGENS = "conversation_messages"

MODOS_DESTINO = ("usuario", "responsavel")
TIPO_HANDOFF, TIPO_CONCLUSAO, TIPO_ALERTA = "handoff", "conclusao", "alerta"
TIPOS = (TIPO_HANDOFF, TIPO_CONCLUSAO, TIPO_ALERTA)
STATUS_ENVIO = ("pendente", "enviado", "falhou", "sem_destino", "limitado")

KIND_SEM_DESTINO = "julia_relatorio_sem_destino"
KIND_ALERTA = "julia_alerta"
KIND_OPT_OUT = "julia_opt_out"
KIND_RELATORIO_FALHOU = "julia_relatorio_falhou"
KIND_DOCUMENTO_FALHOU = "julia_documento_falhou"

TEXTO_MAX = 4000
ERRO_MAX = 300
DESCRICAO_MAX = 500
#: How many recent WAHA messages are scanned to find the media of a `provider_message_id`.
HISTORICO_MIDIA = 100

#: `alerta.tipo` (agents' closed enum) as the human label of the WhatsApp text.
ALERTA_ROTULOS = {
    "lead_insatisfeito": "lead insatisfeito",
    "erro_agente": "erro da Julia",
    "desvio": "desvio de conduta",
    "outro": "alerta",
}
#: `opt_out.motivo` (agents' closed enum) as the human reason of the notices.
OPT_OUT_MOTIVOS = {"palavra_chave": "palavra-chave de parada", "pedido_do_lead": "pedido do próprio lead"}
IDENTIFICACAO_ROTULOS = {"cpf": "CPF", "rg": "RG", "email": "e-mail", "documento_enviado": "documento enviado"}
REACOES = {"gostou": "gostou", "nao_gostou": "não gostou", "sem_reacao": "sem reação"}


# ── destination (the settings API) ──────────────────────────────────────────
KIND_LIMITADO = "julia_relatorio_limitado"
KIND_DESTINO = "julia_relatorio_destino"
T_USUARIOS = "noctus_users"
MSG_CADASTRAR_WHATSAPP = "Cadastre seu WhatsApp no noc para receber os relatórios da Julia."


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _linha_destino(client: Any, org_id: UUID | str) -> dict[str, Any]:
    rows = client.table(T_DESTINO).select("*").eq("org_id", str(org_id)).limit(1).execute().data or []
    return rows[0] if rows else {}


def _telefone_valido(valor: Any) -> Optional[str]:
    """`+<10-15 digits>` from a core `noctus_users.telefone`, or None (unset / not a phone)."""
    digitos = "".join(c for c in str(valor or "") if c.isdigit())
    return f"+{digitos}" if 10 <= len(digitos) <= 15 else None


def usuarios_da_org(core: Any, org_id: UUID | str, ids: list[Any]) -> dict[str, dict[str, Any]]:
    """`{user_id: {id, nome, telefone}}` for the ids that belong to THIS org -- from core `public.noctus_users` (the one place a person's
    WhatsApp lives: "my number is set in noc"; `telefone` is E.164 or None). Reads the way `table_reads.resolve_actors` does; a core
    that has no `telefone` column yet answers without phones (logged), never a crash.
    NOC-REMEDIATE[resolve-user-phones]: switch to the seed `resolve_user_phones` once it lands — 2026-11-03."""
    limpos = sorted({str(i) for i in ids if i})
    if not limpos:
        return {}
    try:
        rows = core.table(T_USUARIOS).select("id,nome,org_id,telefone").in_("id", limpos).execute().data or []
    except Exception as exc:
        logger.error("julia: noctus_users.telefone not readable (%s) -- destinations resolve without phones", type(exc).__name__)
        rows = core.table(T_USUARIOS).select("id,nome,org_id").in_("id", limpos).execute().data or []
    return {
        str(r["id"]): {"id": str(r["id"]), "nome": r.get("nome"), "telefone": _telefone_valido(r.get("telefone"))}
        for r in rows if str(r.get("org_id")) == str(org_id)
    }


def obter_destino(client: Any, core: Any, org_id: UUID | str) -> dict[str, Any]:
    """The org's destination: `{modo, usuario_id, usuario_nome, telefone_resolvido}`. The destination is a USER of the org, never a
    typed number: the phone is read from that user's profile in noc at send time (`telefone_resolvido` is None until they set it)."""
    row = _linha_destino(client, org_id)
    uid = str(row["usuario_id"]) if row.get("usuario_id") else None
    usuario = usuarios_da_org(core, org_id, [uid]).get(uid) if uid else None
    return {
        "modo": row.get("modo") if row.get("modo") in MODOS_DESTINO else "usuario",
        "usuario_id": uid,
        "usuario_nome": usuario.get("nome") if usuario else None,
        "telefone_resolvido": usuario.get("telefone") if usuario else None,
        "atualizado_em": row.get("updated_at"),
    }


def _auditar(client: Any, org_id: UUID | str, user_id: Any, evento: str, antes: dict[str, Any], depois: dict[str, Any]) -> None:
    client.table(T_AUDITORIA).insert({
        "org_id": str(org_id), "user_id": str(user_id) if user_id else None, "evento": evento, "antes": antes, "depois": depois,
    }).execute()


def _estado_publico(row: dict[str, Any]) -> dict[str, Any]:
    return {"modo": row.get("modo"), "usuario_id": str(row["usuario_id"]) if row.get("usuario_id") else None}


def _avisar_admins(servicos: Any, org_id: UUID | str, titulo: str, mensagem: str) -> None:
    try:
        core = servicos.core_client
        alvo = sorted(set(notificacoes.donos_da_org(core, org_id)) | set(notificacoes.admins_da_org(core, org_id)))
        write_in_app(core, user_ids=alvo, kind=KIND_DESTINO, title=titulo, message=mensagem[:500],
                     metadata={"link": "/julia/relatorios-config", "julia": True}, org_id=org_id)
    except Exception as exc:
        logger.error("julia: admin notice about the report destination not written org=%s (%s)", org_id, type(exc).__name__)


async def alterar_destino(
    servicos: Any, org_id: UUID | str, *, modo: str, usuario_id: Optional[UUID | str], user_id: Optional[UUID | str],
) -> dict[str, Any]:
    """Save the org's destination (org admin only -- the route guards it): `modo usuario` needs `usuario_id`, a member of the org
    (422 `usuario_obrigatorio` / `usuario_fora_da_org`); `modo responsavel` may carry one as the fallback. Every change is audited
    (before/after), told to the org admins in-app and -- when the previous destination user had a phone in noc -- to THAT phone by
    WhatsApp (a redirect of every lead's report must not go unseen)."""
    client = servicos.scoped
    if modo not in MODOS_DESTINO:
        raise AppException("modo_invalido", "Use modo=usuario ou modo=responsavel.", status_code=422)
    uid = str(usuario_id) if usuario_id else None
    if modo == "usuario" and uid is None:
        raise AppException("usuario_obrigatorio", "Escolha a pessoa que receberá os relatórios.", status_code=422)
    if uid is not None and uid not in usuarios_da_org(servicos.core_client, org_id, [uid]):
        raise AppException("usuario_fora_da_org", "O usuário informado não pertence a esta organização.", status_code=422)
    anterior = _linha_destino(client, org_id)
    antes = _estado_publico(anterior)
    antigo_uid = antes["usuario_id"] if antes["modo"] == "usuario" else None
    antigo_fone = (usuarios_da_org(servicos.core_client, org_id, [antigo_uid]).get(antigo_uid) or {}).get("telefone") if antigo_uid else None
    client.table(T_DESTINO).upsert({
        "org_id": str(org_id), "modo": modo, "usuario_id": uid,
        "updated_by": str(user_id) if user_id else None, "updated_at": _agora().isoformat(),
    }, on_conflict="org_id").execute()
    depois = _estado_publico(_linha_destino(client, org_id))
    if depois != antes:
        _auditar(client, org_id, user_id, "alterado", antes, depois)
        _avisar_admins(servicos, org_id, "Destino dos relatórios da Julia alterado", "Quem recebe os relatórios da Julia por WhatsApp foi alterado. Confira em Julia > Relatórios.")
        if antigo_fone and antigo_uid != (uid if modo == "usuario" else None):
            await enviar_aviso_interno(
                servicos, org_id, antigo_fone,
                "Aviso da Julia: você deixou de ser o destino dos relatórios dos leads por WhatsApp. Se não foi uma decisão sua ou da sua equipe, avise o responsável pela conta.")
    return obter_destino(client, servicos.core_client, org_id)


def resolver_destino(client: Any, core: Any, org_id: UUID | str, contato: dict[str, Any]) -> tuple[Optional[str], str, Optional[str]]:
    """`(phone, origem, usuario_id)` for this lead. `modo usuario` -> that user's phone in noc; `modo responsavel` -> the lead's
    responsavel's phone in noc, else their number in the staff list, else the configured user. `phone` is None when the person in
    charge has not set a WhatsApp in noc yet (`usuario_id` says WHO should); `(None, 'nenhum', None)` when nothing is configured."""
    cfg = _linha_destino(client, org_id)
    fallback = str(cfg["usuario_id"]) if cfg.get("usuario_id") else None
    resp = str(contato["responsavel_user_id"]) if contato.get("responsavel_user_id") else None
    if cfg.get("modo") == "responsavel" and resp:
        fone = (usuarios_da_org(core, org_id, [resp]).get(resp) or {}).get("telefone")
        if fone:
            return fone, "responsavel", resp
        rows = client.table(T_STAFF).select("telefone,ativo").eq("org_id", str(org_id)).eq("user_id", resp).eq("ativo", True).execute().data or []
        staff = next((r["telefone"] for r in rows if r.get("telefone")), None)
        if staff:
            return f"+{staff}", "responsavel", resp
    if fallback:
        fone = (usuarios_da_org(core, org_id, [fallback]).get(fallback) or {}).get("telefone")
        return fone, "usuario", fallback
    if cfg.get("modo") == "responsavel" and resp:
        return None, "responsavel", resp
    return None, "nenhum", None


# ── text ────────────────────────────────────────────────────────────────────
def _s(valor: Any, limite: int = 400) -> str:
    return " ".join(str(valor).split())[:limite] if valor is not None else ""


def _telefone_legivel(contato: dict[str, Any]) -> str:
    return str(contato.get("telefone_e164") or "").strip() or "sem telefone"


def cabecalho(contato: dict[str, Any]) -> str:
    nome = _limpar_nome(contato.get("nome")) or "Lead sem nome"
    return f"{nome} ({_telefone_legivel(contato)})"


def link_da_conversa(chat_id: Optional[str]) -> Optional[str]:
    """The absolute deep link to the conversation, or None when SW's public URL is not resolvable (the line is then left out)."""
    if not chat_id:
        return None
    try:
        base = resolve_product_url("social-wiring")
    except ValueError:
        logger.warning("julia: social-wiring public URL unresolvable -- the report goes out without the conversation link")
        return None
    return f"{base.rstrip('/')}/julia/conversas?chat={quote(chat_id, safe='')}"


def _lista(valor: Any) -> list[Any]:
    return list(valor) if isinstance(valor, (list, tuple)) else []


def texto_deterministico(relatorio: dict[str, Any], contato: dict[str, Any], *, motivo: Optional[str] = None) -> str:
    """The report text built from the STRUCTURED fields -- used when `relatorio.texto` is missing or blank (a partial shape).
    Same layout agents uses: header, Resumo, Perfil, Imóveis oferecidos, Recomendados, Disponibilidade, Documentos, Motivo."""
    blocos = [f"Relatório da Julia\nLead: {cabecalho(contato)}"]
    if relatorio.get("resumo_conversa"):
        blocos.append("Resumo: " + _s(relatorio["resumo_conversa"], 800))
    perfil = relatorio.get("perfil")
    if isinstance(perfil, dict) and perfil:
        blocos.append("Perfil:\n" + "\n".join(f"- {_s(k, 60)}: {_s(v, 120)}" for k, v in list(perfil.items())[:14] if v not in (None, "", [], {})))
    oferecidos = [i for i in _lista(relatorio.get("imoveis_oferecidos")) if isinstance(i, dict) and i.get("codigo")]
    if oferecidos:
        linhas = []
        for i in oferecidos[:12]:
            reacao = REACOES.get(str(i.get("reacao")), "")
            linhas.append(f"- {_s(i['codigo'], 40)}" + (f" ({reacao})" if reacao else "") + (f" {_s(i['link'], 200)}" if i.get("link") else ""))
        blocos.append("Imóveis oferecidos:\n" + "\n".join(linhas))
    recomendados = [str(c) for c in _lista(relatorio.get("imoveis_recomendados")) if c]
    if recomendados:
        blocos.append("Recomendados: " + ", ".join(_s(c, 40) for c in recomendados[:6]))
    if relatorio.get("disponibilidade_visita"):
        blocos.append("Disponibilidade para visita: " + _s(relatorio["disponibilidade_visita"], 300))
    ident = relatorio.get("identificacao")
    if isinstance(ident, dict) and ident:
        blocos.append("Documentos recebidos: " + ", ".join(
            f"{rotulo} {'sim' if ident.get(chave) else 'não'}" for chave, rotulo in IDENTIFICACAO_ROTULOS.items() if chave in ident))
    mot = relatorio.get("motivo") or motivo
    if mot:
        blocos.append("Motivo: " + _s(mot, 300))
    if relatorio.get("proximos_passos"):
        blocos.append("Próximos passos: " + _s(relatorio["proximos_passos"], 300))
    return "\n\n".join(blocos)[:TEXTO_MAX]


def texto_do_relatorio(relatorio: Optional[dict[str, Any]], contato: dict[str, Any], *, motivo: Optional[str], registro: Any = None) -> str:
    """The text to send: agents' `relatorio.texto` when it sent one; else the structured fields; else (an older agents build
    with NO `relatorio`) a minimal text from the hand-off reason and the hand-off note (`registro`)."""
    if isinstance(relatorio, dict):
        texto = relatorio.get("texto")
        if isinstance(texto, str) and texto.strip():
            return texto.strip()[:TEXTO_MAX]
        if any(relatorio.get(k) for k in ("resumo_conversa", "perfil", "imoveis_oferecidos", "motivo")):
            return texto_deterministico(relatorio, contato, motivo=motivo)
    base: dict[str, Any] = {}
    if registro is not None:
        base["resumo_conversa"] = getattr(registro, "resumo", None)
        base["perfil"] = getattr(registro, "perfil", None) or None
    return texto_deterministico(base, contato, motivo=motivo or "atendimento passado para uma pessoa")


def texto_do_alerta(tipo: str, contato: dict[str, Any], descricao: str, chat_id: Optional[str]) -> str:
    """CONTRACT §12.3: `⚠️ Julia — {tipo legível}\\nLead: {nome} ({telefone})\\n{descricao}\\nConversa: {deep link}`."""
    linhas = [f"⚠️ Julia — {ALERTA_ROTULOS.get(tipo, ALERTA_ROTULOS['outro'])}", f"Lead: {cabecalho(contato)}", _s(descricao, DESCRICAO_MAX)]
    link = link_da_conversa(chat_id)
    if link:
        linhas.append(f"Conversa: {link}")
    return "\n".join(linhas)


# ── staff-output sanitizer (defence in depth: agents sanitizes too) ─────────
#: Everything that reaches the staff number is DATA an outsider can influence (the lead's name, what the lead said, what the model
#: wrote). Only what SW itself renders survives: the conversation deep link and the org's own listing links (the org's domain), and
#: the lead's own phone. Everything else that could be an attack surface for a human reading it -- other links, bare domains,
#: phone numbers, e-mails, PIX keys, @-mentions -- is replaced by a visible marker.
_URL = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"']+")
_DOMINIO = re.compile(
    r"(?i)(?<![@\w.-])(?:[a-z0-9-]+\.)+(?:com|net|org|br|io|me|ly|app|co|xyz|info|link|site|online|ws|gl|to|gg|cc|tk|ml|ga|cf|top|club|store|shop|dev|page|click|live|vip|biz|us|ai|pro|tv|bio)\b(?:/[^\s<>\"']*)?")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_MENCAO = re.compile(r"(?<![\w])@\w[\w.]*")
_PIX_UUID = re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
_PIX_ROTULO = re.compile(r"(?i)\bchave\s+pix\b[^\n]*")
_TELEFONE = re.compile(r"(?<![\w])\+?\d[\d\s().-]{7,}\d(?![\w])")
_SEL = "\x00{}\x00"
MARCADORES = {"link": "[link removido]", "email": "[e-mail removido]", "numero": "[número removido]", "mencao": "[menção removida]", "chave": "[chave removida]"}


def _host(url: str) -> str:
    try:
        return (urlparse(url if "://" in url else "https://" + url).hostname or "").lower()
    except ValueError:
        return ""


def sanitizar_para_staff(texto: str, *, hosts_permitidos: frozenset[str] = frozenset(), telefones_permitidos: frozenset[str] = frozenset()) -> str:
    """`texto` with every link / bare domain outside `hosts_permitidos`, every phone number outside `telefones_permitidos` (digit
    strings), e-mail, PIX key and @-mention replaced by a marker. Allowed links are kept verbatim."""
    guardados: list[str] = []

    def guardar(valor: str) -> str:
        guardados.append(valor)
        return _SEL.format(len(guardados) - 1)

    def por_host(marcador: str):
        return lambda m: guardar(m.group(0)) if _host(m.group(0)) in hosts_permitidos else marcador

    saida = _EMAIL.sub(MARCADORES["email"], texto)
    saida = _URL.sub(por_host(MARCADORES["link"]), saida)
    saida = _DOMINIO.sub(por_host(MARCADORES["link"]), saida)
    saida = _MENCAO.sub(MARCADORES["mencao"], saida)
    saida = _PIX_ROTULO.sub(MARCADORES["chave"], saida)
    saida = _PIX_UUID.sub(MARCADORES["chave"], saida)

    def telefone(m: "re.Match[str]") -> str:
        digitos = re.sub(r"\D", "", m.group(0))
        if len(digitos) < 10:  # a price / a code, not a phone number or a document number
            return m.group(0)
        return m.group(0) if digitos in telefones_permitidos else MARCADORES["numero"]

    saida = _TELEFONE.sub(telefone, saida)
    return re.sub(r"\x00(\d+)\x00", lambda m: guardados[int(m.group(1))], saida)


def _limpar_nome(nome: Any) -> str:
    """A lead's display name (Meta form / WhatsApp pushName) as shown to staff: attack surfaces removed, capped."""
    return sanitizar_para_staff(" ".join(str(nome or "").split()))[:120]


def _permissoes_do_staff(client: Any, org_id: UUID | str, contato: dict[str, Any]) -> tuple[frozenset[str], frozenset[str]]:
    """`(hosts, phones)` a staff text may keep: SW's own public host (the conversation deep link), the host of the org's
    `link_imovel` template (its listings), and the lead's own phone digits."""
    hosts: set[str] = set()
    try:
        hosts.add(_host(resolve_product_url("social-wiring")))
    except ValueError:
        pass
    try:
        from app.services import julia_conhecimento_service

        hosts.add(_host(julia_conhecimento_service.link_imovel_fn(client, org_id)("X") or ""))
    except Exception as exc:
        logger.error("julia: could not read the org listing-link host org=%s (%s)", org_id, type(exc).__name__)
    telefone = "".join(c for c in str(contato.get("telefone_e164") or "") if c.isdigit())
    return frozenset(h for h in hosts if h), frozenset({telefone} if telefone else set())


# ── ledger ──────────────────────────────────────────────────────────────────
def registrar_relatorio(
    client: Any, *, org_id: UUID | str, contato: dict[str, Any], tipo: str, texto: str, dados: dict[str, Any],
    thread_id: Optional[str], chave: str, destino: Optional[str],
) -> Optional[dict[str, Any]]:
    """Insert the report row (`envio_status` pendente, or `sem_destino` when there is no destination). None when the
    `(org, chave)` row already exists -- a replay writes nothing twice."""
    if tipo not in TIPOS:
        raise ValueError(f"tipo de relatorio desconhecido: {tipo!r}")
    ja = client.table(T_RELATORIOS).select("id").eq("org_id", str(org_id)).eq("chave", chave).limit(1).execute().data or []
    if ja:
        return None
    linha = {
        "org_id": str(org_id), "contato_id": str(contato["id"]),
        "lead_id": str(contato["lead_id"]) if contato.get("lead_id") else None,
        "thread_id": thread_id, "tipo": tipo, "texto": texto[:TEXTO_MAX], "dados": dados, "destino_e164": destino,
        "envio_status": "pendente" if destino else "sem_destino", "chave": chave,
    }
    data = client.table(T_RELATORIOS).insert(linha).execute().data or []
    return data[0] if data else linha


def _marcar(client: Any, row: dict[str, Any], status: str, erro: Optional[str] = None) -> None:
    if row.get("id") is None:
        logger.error("julia: report row has no id -- delivery status %s not stored", status)
        return
    try:
        client.table(T_RELATORIOS).update({"envio_status": status, "envio_erro": erro[:ERRO_MAX] if erro else None}).eq("id", str(row["id"])).execute()
    except Exception as exc:
        logger.error("julia: could not store the delivery status of report %s (%s)", row.get("id"), type(exc).__name__)
    row["envio_status"], row["envio_erro"] = status, erro


def listar_relatorios(client: Any, org_id: UUID | str, contato_id: UUID | str, *, limite: int = 50) -> list[dict[str, Any]]:
    """The contato's reports + alerts, newest first -- the lead card's feed."""
    rows = (
        client.table(T_RELATORIOS).select("*").eq("org_id", str(org_id)).eq("contato_id", str(contato_id))
        .order("created_at", desc=True).limit(limite).execute().data or []
    )
    return [saida_relatorio(r) for r in rows]


def saida_relatorio(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row.get(k) for k in (
        "id", "contato_id", "lead_id", "thread_id", "tipo", "texto", "dados", "destino_e164", "envio_status", "envio_erro", "created_at")}


# ── in-app ──────────────────────────────────────────────────────────────────
def avisar_in_app(
    servicos: Any, *, org_id: UUID | str, kind: str, titulo: str, mensagem: str, contato_id: Any = None, chat_id: Optional[str] = None,
    so_donos: bool = False,
) -> int:
    """One in-app notification (core `public.notifications`): the org OWNERS (`so_donos`: a config problem only an owner can fix)
    or the lead's attendant -> connection owner -> admins (the Julia recipient rule). Best-effort: a failure is logged, never raised.
    Returns how many were written."""
    try:
        core = servicos.core_client
        if so_donos:
            alvo = notificacoes.donos_da_org(core, org_id) or notificacoes.admins_da_org(core, org_id)
        else:
            alvo = notificacoes.resolver_destinatarios(servicos.scoped, core, org_id, contato_id)
        link = f"/julia/conversas?chat={quote(chat_id, safe='')}" if chat_id else "/julia/relatorios-config"
        return write_in_app(
            core, user_ids=alvo, kind=kind, title=titulo, message=mensagem[:500],
            metadata={"link": link, "contato_id": str(contato_id) if contato_id else None, "chat_id": chat_id, "julia": True},
            org_id=org_id,
        )
    except Exception as exc:
        logger.error("julia: in-app notice %s not written org=%s (%s)", kind, org_id, type(exc).__name__)
        return 0


# ── delivery ────────────────────────────────────────────────────────────────
class InternoSender:
    """`send_paragraphs`' `intake` seam for a STAFF notice: sends through the org line's WAHA client and PRE-WRITES the outbound row
    (`origem='interno'`, keyed by the provider id WAHA returned) via `MessageStore.registrar_interno_enviado`, so WAHA's `fromMe`
    echo trips UNIQUE(provider_message_id) and is never mistaken for a human taking over Julia's line. Not a lead send: nothing is
    recorded as a lead outbound. The send is bracketed by the in-flight flag (`marcar_envio_em_curso` / `encerrar_envio`) so an
    echo that beats the row write is still recognised."""

    def __init__(self, *, connection: Any, waha: Any, redis: Any, liberacao: julia_envio_gate.Liberacao, message_store: Any):
        self._c = connection
        self._waha = waha
        self._redis = redis
        self._liberacao = liberacao
        self._store = message_store

    async def send_reply(self, sender: str, text: str) -> None:
        from app.schemas.whatsapp import extract_waha_message_id

        julia_envio_gate.conferir(self._liberacao, self._c.id)  # the outbound gate (flow `interno`) passed for this line
        julia.marcar_envio_em_curso(self._redis, self._c.id, sender)
        try:
            result = await self._waha.send_text(sender, text)
        finally:
            julia.encerrar_envio(self._redis, self._c.id, sender)
        provider_id = extract_waha_message_id(result) if isinstance(result, dict) else None
        try:
            self._store.registrar_interno_enviado(
                connection_id=self._c.id, chat_id=sender, body=text, provider_message_id=provider_id,
                structured_payload={"fluxo": "interno"},
            )
        except Exception as exc:  # the notice WAS delivered: a failed pre-write must be loud, not a failed send
            logger.error("julia: internal send delivered but its row was not pre-written org=%s (%s)", self._c.org_id, type(exc).__name__)


def _primeira_do_periodo(servicos: Any, assunto: str, org_id: UUID | str, *, limite: int = 1, periodo: str = "dia") -> bool:
    """True while `assunto` has been raised at most `limite` times for the org in the current `periodo` (`dia` America/Sao_Paulo, or
    `hora`). A counter store that is down answers True: better a repeated notice than a missed one."""
    marca = notificacoes.dia_sp() if periodo == "dia" else _agora().strftime("%Y%m%d%H")
    chave = f"julia:aviso:{assunto}:{org_id}:{marca}"
    try:
        n = int(servicos.redis.incr(chave))
        if n == 1:
            servicos.redis.expire(chave, 90000)
        return n <= limite
    except Exception as exc:
        logger.error("julia: notice counter unavailable (%s) -- allowing", type(exc).__name__)
        return True


@dataclass
class ServicosInternos:
    """The collaborators the staff sends need (a slice of the lead worker's `LeadDeps`): the schema-scoped DB, core, the WAHA client
    factory, the connection lookup (decrypting), redis and the settings. The settings API builds one; the worker passes its own deps."""

    scoped: Any
    core_client: Any
    waha_factory: Callable[..., Any]
    connection_lookup: Callable[[UUID], Any]
    redis: Any
    cfg: Any
    documento_intake: Optional[Callable[..., Any]] = None
    #: `(org_id) -> MessageStore` (default: over the service-role client) -- the `interno` pre-write.
    message_store_factory: Optional[Callable[[Any], Any]] = None
    #: `(org_id) -> LinhaDaOrg` (default: `julia_linha.linha_da_org`).
    linha_resolver: Optional[Callable[[Any], Any]] = None


def _conexao(servicos: Any, connection_id: UUID | str) -> Any:
    return servicos.connection_lookup(UUID(str(connection_id)))


async def entregar(servicos: Any, *, connection: Any, contato: dict[str, Any], row: dict[str, Any]) -> str:
    """Send the report/alert `row` to its destination from the org's Julia line; returns the final `envio_status`.
    A row with no destination is `sem_destino` + the in-app alert `julia_relatorio_sem_destino` (never silent). Every failure
    is stored on the row (`falhou` + `envio_erro`) and surfaced in-app; nothing raises."""
    client = servicos.scoped
    org_id = connection.org_id
    destino = row.get("destino_e164")
    if not destino:
        _marcar(client, row, "sem_destino")
        uid = (row.get("dados") or {}).get("destino_usuario_id")
        if _primeira_do_periodo(servicos, f"sem_destino_{uid or 'org'}", org_id):  # every report is stored; the person is told once a day
            if uid:  # a person is in charge but has no WhatsApp in noc yet: tell THEM
                try:
                    write_in_app(
                        servicos.core_client, user_ids=[uid], kind=KIND_SEM_DESTINO, title="Cadastre seu WhatsApp no noc",
                        message=MSG_CADASTRAR_WHATSAPP, metadata={"link": "/perfil", "julia": True}, org_id=org_id)
                except Exception as exc:
                    logger.error("julia: no-phone notice not written org=%s (%s)", org_id, type(exc).__name__)
            else:
                avisar_in_app(
                    servicos, org_id=org_id, kind=KIND_SEM_DESTINO, so_donos=True, titulo="Relatório da Julia sem destino",
                    mensagem="A Julia gerou um relatório, mas ninguém está definido para recebê-lo. Escolha a pessoa em Julia > Relatórios.",
                    contato_id=contato.get("id"), chat_id=contato.get("chat_id"),
                )
        eventos.emitir(client, org_id, "relatorio_entregue", contato.get("id"), {"relatorio_id": row.get("id"), "tipo": row.get("tipo"), "status": "sem_destino"})
        return "sem_destino"
    if not _primeira_do_periodo(servicos, "staff_envios", org_id, limite=int(servicos.cfg.julia_staff_envios_por_hora), periodo="hora"):
        # M3: a runaway producer must not turn the Julia line into a message cannon at the staff number -- the text stays on the card
        # and the owners get ONE digest per hour instead of the WhatsApp message
        _marcar(client, row, "limitado")
        if _primeira_do_periodo(servicos, "limitado", org_id, periodo="hora"):
            avisar_in_app(
                servicos, org_id=org_id, kind=KIND_LIMITADO, so_donos=True, titulo="Relatórios da Julia limitados",
                mensagem=f"O limite de {int(servicos.cfg.julia_staff_envios_por_hora)} envios por hora ao número de destino foi atingido. Os relatórios seguem salvos no cartão de cada lead.",
                contato_id=contato.get("id"), chat_id=contato.get("chat_id"),
            )
        eventos.emitir(client, org_id, "relatorio_entregue", contato.get("id"), {"relatorio_id": row.get("id"), "tipo": row.get("tipo"), "status": "limitado"})
        return "limitado"
    erro = await _enviar_texto(servicos, connection, destino, str(row.get("texto") or ""), contato_id=contato.get("id"))
    if erro:
        return _falha(servicos, client, connection, contato, row, erro)
    _marcar(client, row, "enviado")
    eventos.emitir(client, org_id, "relatorio_entregue", contato.get("id"), {"relatorio_id": row.get("id"), "tipo": row.get("tipo"), "status": "enviado"})
    return "enviado"


async def _enviar_texto(servicos: Any, connection: Any, numero: str, texto: str, *, contato_id: Any = None) -> Optional[str]:
    """THE staff send: through the outbound gate flow `interno`, from the connection's Julia line, one WhatsApp message per
    paragraph. None on success, else the error label (nothing raises)."""
    try:
        liberacao = julia_envio_gate.exigir(servicos.scoped, connection.org_id, connection.id, julia_envio_gate.Fluxo.INTERNO, contato_id=contato_id)
    except julia_envio_gate.EnvioBloqueado as exc:  # already logged + `envio_bloqueado` event by the gate
        return f"bloqueado: {exc.motivo}"
    try:
        from app.services.julia_linha import linha_da_conexao

        waha = linha_da_conexao(connection).waha_client(servicos.waha_factory)
        chat = (await waha.resolve_chat_id(numero)).chat_id
        sender = InternoSender(
            connection=connection, waha=waha, redis=servicos.redis, liberacao=liberacao,
            message_store=_message_store(servicos, connection.org_id))
        esperadas = len(split_for_whatsapp(texto, enabled=True))
        enviadas = await send_paragraphs(
            intake=sender, sender=chat, text=texto, delay_seconds=float(servicos.cfg.whatsapp_paragraph_delay_seconds), split=True)
    except Exception as exc:
        return f"envio_falhou: {type(exc).__name__}"
    if enviadas < esperadas:  # `send_paragraphs` logs and swallows a failed part: a short count IS the failure
        return f"enviadas {enviadas}/{esperadas}"
    return None


def _message_store(servicos: Any, org_id: Any) -> Any:
    factory = getattr(servicos, "message_store_factory", None)
    if factory is not None:
        return factory(org_id)
    from app.dependencies import get_admin_client
    from app.services.message_store import MessageStore

    return MessageStore(admin_supabase=get_admin_client(), org_id=UUID(str(org_id)))


async def enviar_aviso_interno(servicos: Any, org_id: UUID | str, numero: str, texto: str) -> Optional[str]:
    """A short staff notice (the destination confirmation code, the "your number was replaced" warning) from the org's ONE line,
    resolved through `julia_linha.linha_da_org`. None on success, else the error label (`sem_linha` / `linha_ambigua` when the
    org has no usable line -- logged, never a fallback)."""
    import asyncio

    from app.services.julia_linha import LinhaIndisponivel, linha_da_org

    resolver = getattr(servicos, "linha_resolver", None) or (lambda org: linha_da_org(org, admin_client=getattr(servicos, "admin", None)))
    try:
        linha = await asyncio.to_thread(resolver, org_id)
    except LinhaIndisponivel as exc:
        motivo = exc.motivo
        logger.error("julia: staff notice not sent org=%s: %s", org_id, motivo)
        return motivo
    return await _enviar_texto(servicos, linha.connection, numero, texto)


def _falha(servicos: Any, client: Any, connection: Any, contato: dict[str, Any], row: dict[str, Any], erro: str) -> str:
    logger.error("julia: report %s (%s) not delivered org=%s: %s", row.get("id"), row.get("tipo"), connection.org_id, erro)
    _marcar(client, row, "falhou", erro)
    avisar_in_app(
        servicos, org_id=connection.org_id, kind=KIND_RELATORIO_FALHOU, so_donos=True,
        titulo="Relatório da Julia não enviado",
        mensagem="O relatório da Julia foi salvo no cartão do lead, mas não foi possível enviá-lo por WhatsApp. Confira o número de destino e a linha.",
        contato_id=contato.get("id"), chat_id=contato.get("chat_id"),
    )
    eventos.emitir(client, connection.org_id, "relatorio_entregue", contato.get("id"), {"relatorio_id": row.get("id"), "tipo": row.get("tipo"), "status": "falhou"})
    return "falhou"


async def _gerar_e_entregar(
    servicos: Any, *, connection: Any, contato: dict[str, Any], tipo: str, texto: str, dados: dict[str, Any],
    thread_id: Optional[str], chave: str,
) -> Optional[dict[str, Any]]:
    client = servicos.scoped
    # Owner switch (core admin "Notificações"): a switched-off kind is neither stored nor delivered; the send ledger says so.
    kind = catalogo_kind(tipo, dados)
    gate = get_notification_gate(_CATALOG_PRODUCT)
    if not gate.allowed(kind):
        gate.record(kind, org_id=connection.org_id, status="suppressed", recipients=1, reason="desligada em Notificações")
        logger.info("julia: %s for org=%s suppressed (switched off in core Notificações)", kind, connection.org_id)
        return None
    hosts, telefones = _permissoes_do_staff(client, connection.org_id, contato)
    texto = sanitizar_para_staff(texto, hosts_permitidos=hosts, telefones_permitidos=telefones)
    destino, origem, destino_uid = resolver_destino(client, servicos.core_client, connection.org_id, contato)
    row = registrar_relatorio(
        client, org_id=connection.org_id, contato=contato, tipo=tipo, texto=texto, dados={**dados, "destino_origem": origem, "destino_usuario_id": destino_uid},
        thread_id=thread_id, chave=chave, destino=destino,
    )
    if row is None:
        logger.info("julia: report %s already stored -- not delivered twice", chave)
        return None
    envio = await entregar(servicos, connection=connection, contato=contato, row=row)
    gate.record(
        kind, org_id=connection.org_id,
        status={"enviado": "sent", "sem_destino": "no_recipient"}.get(envio, "failed"),
        recipients=0 if envio == "sem_destino" else 1, delivered=1 if envio == "enviado" else 0,
        reason=None if envio == "enviado" else envio,
    )
    return row


def catalogo_kind(tipo: str, dados: dict[str, Any]) -> str:
    """The core-catalog kind (`notification_kinds.py`) of a Julia staff report/alert."""
    if tipo == TIPO_ALERTA:
        return "julia_opt_out" if dados.get("tipo_alerta") == "opt_out" else "julia_alerta"
    return {TIPO_HANDOFF: "julia_handoff", TIPO_CONCLUSAO: "julia_conclusao"}.get(tipo, "julia_alerta")


def completar_links(client: Any, org_id: UUID | str, relatorio: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """A copy of `relatorio` whose offered listings without a `link` get one from the org's `link_imovel` template (agents may
    send null). Never raises; unchanged when there is nothing to fill."""
    itens = relatorio.get("imoveis_oferecidos") if isinstance(relatorio, dict) else None
    if not isinstance(itens, list) or not any(isinstance(i, dict) and i.get("codigo") and not i.get("link") for i in itens):
        return relatorio
    try:
        from app.services import julia_conhecimento_service

        link = julia_conhecimento_service.link_imovel_fn(client, org_id)
        novos = [{**i, "link": link(str(i["codigo"]))} if isinstance(i, dict) and i.get("codigo") and not i.get("link") else i for i in itens]
        return {**relatorio, "imoveis_oferecidos": novos}
    except Exception as exc:
        logger.error("julia: could not complete the report links org=%s (%s)", org_id, type(exc).__name__)
        return relatorio


def _dados_do_relatorio(relatorio: Optional[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    dados = {k: v for k, v in (relatorio or {}).items() if k != "texto"}
    dados.update({k: v for k, v in extra.items() if v is not None})
    dados["relatorio_de_agents"] = bool(relatorio)
    return dados


# ── hand-off report ─────────────────────────────────────────────────────────
async def entregar_relatorio_do_handoff(
    servicos: Any, *, connection: Any, chat_id: str, handoff: Any, result: Any, lote_hash: str, registro: Any = None,
) -> Optional[dict[str, Any]]:
    """The hand-off report: claim `(lote_hash, handoff.seq)` in the actions ledger (a replayed turn does it once), store the row and
    send it. Never raises. None when the batch had already done it."""
    try:
        client = servicos.scoped
        contato = _contato_do_chat(client, connection, chat_id)
        if contato is None:
            logger.error("julia: hand-off report skipped -- no contato for chat=%s", ref_log(chat_id))
            return None
        if not julia_acoes_service.registrar_uma_vez(
            client, org_id=connection.org_id, contato_id=contato["id"], conversation_id=result.thread, lote_hash=lote_hash,
            seq=handoff.seq, tipo="handoff", payload={"motivo_codigo": handoff.motivo_codigo, "relatorio": bool(handoff.relatorio)},
        ):
            return None
        rel = completar_links(client, connection.org_id, handoff.relatorio)
        texto = texto_do_relatorio(rel, contato, motivo=handoff.motivo, registro=registro)
        dados = _dados_do_relatorio(rel, motivo=handoff.motivo, motivo_codigo=handoff.motivo_codigo)
        return await _gerar_e_entregar(
            servicos, connection=connection, contato=contato, tipo=TIPO_HANDOFF, texto=texto, dados=dados,
            thread_id=result.thread, chave=f"{lote_hash}:{handoff.seq}",
        )
    except Exception as exc:
        logger.error("julia: hand-off report failed conn=%s (%s)", connection.id, type(exc).__name__)
        return None


def _contato_do_chat(client: Any, connection: Any, chat_id: str) -> Optional[dict[str, Any]]:
    from app.services import julia_contatos_service

    return julia_contatos_service.buscar_contato(client, connection.org_id, connection.id, chat_id)


# ── the other actions of a turn ─────────────────────────────────────────────
async def processar_acoes(
    servicos: Any, *, connection: Any, chat_id: str, result: Any, resumo_acoes: list[dict[str, Any]], lote_hash: str,
) -> None:
    """After `julia_acoes_service.aplicar`: act on the julia-v3 actions that were NEWLY applied this batch (`repetida` = a replay,
    skipped) -- `lead_pronto` with a `relatorio`, `alerta`, `documento_identificacao`. Each runs alone: a failure is logged and
    recorded as an `acao_falhou` event, never raised, never stopping the next."""
    novas = {a["seq"] for a in resumo_acoes if a.get("estado") != "repetida"}
    for acao in result.julia_actions:
        if acao.seq not in novas or acao.type not in ("lead_pronto", "alerta", "documento_identificacao", "opt_out"):
            continue
        try:
            contato = _contato_do_chat(servicos.scoped, connection, chat_id)
            if contato is None:
                logger.error("julia: %s skipped -- no contato for chat=%s", acao.type, ref_log(chat_id))
                continue
            if acao.type == "lead_pronto":
                await _conclusao(servicos, connection, contato, acao, result, lote_hash)
            elif acao.type == "alerta":
                await _alerta(servicos, connection, contato, chat_id, acao, result, lote_hash)
            elif acao.type == "opt_out":
                await _opt_out(servicos, connection, contato, chat_id, acao, result, lote_hash)
            else:
                await processar_documento(servicos, connection=connection, contato=contato, chat_id=chat_id, payload=acao.payload)
        except Exception as exc:
            logger.error("julia: action %s seq=%s post-processing failed org=%s (%s)", acao.type, acao.seq, connection.org_id, type(exc).__name__)
            eventos.emitir(servicos.scoped, connection.org_id, "acao_falhou", None, {"tipo": acao.type, "seq": acao.seq, "erro": type(exc).__name__})


async def _conclusao(servicos: Any, connection: Any, contato: dict[str, Any], acao: Any, result: Any, lote_hash: str) -> None:
    relatorio = completar_links(servicos.scoped, connection.org_id, acao.payload.get("relatorio"))
    if not isinstance(relatorio, dict) or not relatorio:
        return  # an older agents build: `lead_pronto` carried no report -- nothing to send
    await _gerar_e_entregar(
        servicos, connection=connection, contato=contato, tipo=TIPO_CONCLUSAO,
        texto=texto_do_relatorio(relatorio, contato, motivo=None), dados=_dados_do_relatorio(relatorio, estagio=acao.payload.get("estagio")),
        thread_id=result.thread, chave=f"{lote_hash}:{acao.seq}",
    )


async def _alerta(servicos: Any, connection: Any, contato: dict[str, Any], chat_id: str, acao: Any, result: Any, lote_hash: str) -> None:
    tipo = str(acao.payload.get("tipo") or "outro")
    tipo = tipo if tipo in ALERTA_ROTULOS else "outro"
    descricao = _s(acao.payload.get("descricao"), DESCRICAO_MAX) or "Sem descrição."
    texto = texto_do_alerta(tipo, contato, descricao, chat_id)
    dados = {"tipo_alerta": tipo, "descricao": descricao, "alerta_id": acao.payload.get("alerta_id")}
    if acao.payload.get("trecho"):
        dados["trecho"] = _s(acao.payload["trecho"], 500)
    avisar_in_app(
        servicos, org_id=connection.org_id, kind=KIND_ALERTA, titulo=f"Alerta da Julia: {ALERTA_ROTULOS[tipo]}",
        mensagem=f"{cabecalho(contato)}: {descricao}", contato_id=contato["id"], chat_id=chat_id,
    )
    eventos.emitir(servicos.scoped, connection.org_id, "alerta_julia", contato["id"], {"tipo": tipo, "alerta_id": acao.payload.get("alerta_id")})
    await _gerar_e_entregar(
        servicos, connection=connection, contato=contato, tipo=TIPO_ALERTA, texto=texto, dados=dados,
        thread_id=result.thread, chave=f"{lote_hash}:{acao.seq}",
    )


def mascarar_nome(nome: Any) -> str:
    """`Maria Souza` -> `Maria S.`: the first name and the initial of the rest (the staff recognises the lead, the notice carries no full name)."""
    partes = _limpar_nome(nome).split()
    if not partes:
        return "sem nome"
    return partes[0] if len(partes) == 1 else f"{partes[0]} {partes[-1][0]}."


def mascarar_telefone(telefone: Any) -> str:
    """`+5511988887777` -> `+5511*****7777`: country + area code and the last 4 digits only."""
    bruto = str(telefone or "").strip()
    digitos = re.sub(r"\D", "", bruto)
    if len(digitos) < 8:
        return "sem telefone"
    return f"+{digitos[:4]}{'*' * (len(digitos) - 8)}{digitos[-4:]}"


async def _opt_out(servicos: Any, connection: Any, contato: dict[str, Any], chat_id: str, acao: Any, result: Any, lote_hash: str) -> None:
    """The lead asked to stop being contacted (agents recorded the opt-out and sends the `opt_out` action): tell the org ADMINS in-app
    and the report destination by WhatsApp (outbound flow `interno`) -- ONE notice per opt-out action (the ledger makes a replay
    `repetida`, and the report row's `chave` makes the WhatsApp one idempotent). Every skipped leg is a named, logged reason."""
    motivo = acao.payload.get("motivo")
    # The agent's own reason (agents' `motivo_texto`) is WHY; the closed enum only says how it was detected (fallback).
    motivo_txt = _s(acao.payload.get("motivo_texto"), 300) or OPT_OUT_MOTIVOS.get(motivo, "não informado")
    trecho = _s(acao.payload.get("trecho"), 300)
    quem = f"{mascarar_nome(contato.get('nome'))} ({mascarar_telefone(contato.get('telefone_e164'))})"
    org_id = connection.org_id
    titulo = "Lead pediu para não receber mais mensagens"
    mensagem = f"Lead {quem} pediu para não receber mais mensagens — motivo: {motivo_txt}."
    try:
        admins = notificacoes.admins_da_org(servicos.core_client, org_id)
        if not admins:
            logger.error("julia: opt-out in-app notice not written org=%s: sem_destinatarios", org_id)
        else:
            write_in_app(
                servicos.core_client, user_ids=admins, kind=KIND_OPT_OUT, title=titulo, message=mensagem[:500],
                metadata={"link": f"/julia/conversas?chat={quote(chat_id, safe='')}", "contato_id": str(contato["id"]), "chat_id": chat_id, "julia": True},
                org_id=org_id,
            )
    except Exception as exc:
        logger.error("julia: opt-out in-app notice failed org=%s (%s)", org_id, type(exc).__name__)
    linhas = [f"🚫 Julia — pedido para parar de receber mensagens", f"Lead: {quem}", f"Motivo: {motivo_txt}"]
    if trecho:
        linhas.append(f"O lead disse: “{trecho}”")
    link = link_da_conversa(chat_id)
    if link:
        linhas.append(f"Conversa: {link}")
    dados = {"tipo_alerta": "opt_out", "motivo": motivo, "motivo_texto": _s(acao.payload.get("motivo_texto"), 300) or None, "descricao": mensagem, "trecho": trecho or None}
    row = await _gerar_e_entregar(
        servicos, connection=connection, contato=contato, tipo=TIPO_ALERTA, texto="\n".join(linhas), dados=dados,
        thread_id=result.thread, chave=f"opt_out:{lote_hash}:{acao.seq}",
    )
    if row is not None and row.get("envio_status") == "sem_destino":
        logger.error("julia: opt-out WhatsApp notice has no destination org=%s: sem_destino", org_id)
    eventos.emitir(servicos.scoped, org_id, "opt_out_notificado", contato["id"], {"motivo": motivo})


# ── identification document ─────────────────────────────────────────────────
def _id_da_mensagem(m: Any) -> str:
    raw = m.get("id") if isinstance(m, dict) else None
    if isinstance(raw, dict):
        raw = raw.get("_serialized") or raw.get("id")
    return str(raw or "")


def _midia_da_mensagem(m: dict[str, Any]) -> Optional[dict[str, Any]]:
    midia = m.get("media") if isinstance(m.get("media"), dict) else {}
    url = midia.get("url") or m.get("mediaUrl")
    if not url:
        return None
    return {"url": str(url), "mimetype": midia.get("mimetype") or m.get("mimetype"), "filename": midia.get("filename") or m.get("filename")}


#: The only files an ID document may be (M1): images and PDF -- the lead media caps live in the intake downloader.
MIMES_DOCUMENTO = ("image/jpeg", "image/png", "image/webp", "image/heic", "image/heif", "application/pdf")


def _url_da_linha(url: str, base_url: Optional[str]) -> bool:
    """M1: the media URL must be on the connection's WAHA host (scheme + host + port) or relative to it -- never an address the
    sender or the model chose. Without a base URL only a relative path passes."""
    try:
        alvo = urlparse(url)
    except ValueError:
        return False
    if not alvo.scheme and not alvo.netloc:
        return url.startswith("/")
    if not base_url:
        return False
    base = urlparse(base_url)
    return bool(base.netloc) and (alvo.scheme, alvo.netloc.lower()) == (base.scheme, base.netloc.lower())


async def buscar_midia(waha: Any, chat_id: str, provider_message_id: str, *, base_url: Optional[str] = None) -> Optional[dict[str, Any]]:
    """`{url, mimetype, filename}` of the INBOUND message `provider_message_id` of THIS lead's chat, from WAHA's recent history, or
    None. Refused (None, logged): a message we sent (`fromMe`), media with no URL, a URL outside the connection's WAHA host, a type
    that is not an image / PDF. The id the model passes is a pointer, never trusted for what it points at."""
    mensagens = await waha.fetch_chat_messages(chat_id, limit=HISTORICO_MIDIA)
    for m in mensagens or []:
        if not isinstance(m, dict) or _id_da_mensagem(m) != provider_message_id:
            continue
        if m.get("fromMe") is True or str(m.get("id") or "").startswith("true_"):
            logger.warning("julia: ID document pointer is an outbound message -- refused")
            return None
        midia = _midia_da_mensagem(m)
        if midia is None:
            return None
        if not _url_da_linha(midia["url"], base_url):
            logger.warning("julia: ID document media is not on the connection's WAHA host -- refused")
            return None
        mime = str(midia.get("mimetype") or "").split(";")[0].strip().lower()
        if mime not in MIMES_DOCUMENTO:
            logger.warning("julia: ID document media type %r not accepted -- refused", mime)
            return None
        return midia
    return None


def _mensagem_armazenada(client: Any, org_id: UUID | str, provider_message_id: str) -> Optional[dict[str, Any]]:
    rows = (
        client.table(T_MENSAGENS).select("id,structured_payload,direction").eq("org_id", str(org_id))
        .eq("provider_message_id", provider_message_id).limit(1).execute().data or []
    )
    return rows[0] if rows else None


def _anexo_ja_processado(mensagem: dict[str, Any]) -> bool:
    import json

    sp = mensagem.get("structured_payload")
    if isinstance(sp, str):
        try:
            sp = json.loads(sp)
        except ValueError:
            return False
    anexo = sp.get("anexo") if isinstance(sp, dict) else None
    return bool(isinstance(anexo, dict) and anexo.get("documento_id"))


async def processar_documento(servicos: Any, *, connection: Any, contato: dict[str, Any], chat_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """CONTRACT §12.8: the lead sent an ID document (`provider_message_id`). Find/create the lead's `clientes` card, fetch that
    inbound media from WAHA and run `documento_intake_service.processar_midia` through `servicos.documento_intake`. Returns
    `{status, ...}`; any failure raises the in-app alert `julia_documento_falhou` (never silent) and an event."""
    client = servicos.scoped
    org_id = connection.org_id
    pid = str(payload.get("provider_message_id") or "").strip()
    tipo_provavel = str(payload.get("tipo_provavel") or "outro")[:20]

    def falha(motivo: str) -> dict[str, Any]:
        logger.error("julia: identification document not processed org=%s contato=%s: %s", org_id, contato.get("id"), motivo)
        avisar_in_app(
            servicos, org_id=org_id, kind=KIND_DOCUMENTO_FALHOU, titulo="Documento do lead não processado",
            mensagem=f"{cabecalho(contato)} enviou um documento de identificação que a Julia não conseguiu processar ({motivo}). Abra a conversa e anexe-o ao cartão manualmente.",
            contato_id=contato.get("id"), chat_id=chat_id,
        )
        eventos.emitir(client, org_id, "documento_identificacao", contato.get("id"), {"status": "falhou", "motivo": motivo, "tipo_provavel": tipo_provavel})
        return {"status": "falhou", "motivo": motivo}

    if not pid:
        return falha("mensagem_sem_id")
    mensagem = _mensagem_armazenada(client, org_id, pid)
    if mensagem is not None and _anexo_ja_processado(mensagem):  # the chat was already linked to a card: the webhook intake did it
        eventos.emitir(client, org_id, "documento_identificacao", contato.get("id"), {"status": "ja_processado", "tipo_provavel": tipo_provavel})
        return {"status": "ja_processado"}
    cliente_id = julia_envio_service.garantir_cliente(client, org_id, contato)
    if not cliente_id:
        return falha("cartao_nao_resolvido")
    try:
        waha = servicos.waha_factory(base_url=connection.base_url or None, api_key=connection.api_key, session=connection.session_name)
        midia = await buscar_midia(waha, chat_id, pid, base_url=connection.base_url)
    except Exception as exc:
        return falha(f"midia_indisponivel: {type(exc).__name__}")
    if midia is None:
        return falha("midia_nao_encontrada")
    resultado = await servicos.documento_intake(
        UUID(str(org_id)), UUID(cliente_id), mensagem_id=mensagem.get("id") if mensagem else None,
        media_url=midia["url"], mimetype=midia.get("mimetype"), filename=midia.get("filename"),
    )
    status = str((resultado or {}).get("status") or "erro")
    if status not in ("extraido", "a_classificar"):
        return falha(f"intake_{status}: {(resultado or {}).get('motivo') or 'sem_motivo'}")
    eventos.emitir(client, org_id, "documento_identificacao", contato.get("id"), {"status": status, "tipo_provavel": tipo_provavel})
    return {"status": status, "cliente_id": cliente_id, "documento_id": (resultado or {}).get("documento_id")}


__all__ = [
    "ALERTA_ROTULOS", "InternoSender", "MODOS_DESTINO", "TIPOS", "avisar_in_app", "buscar_midia", "entregar",
    "entregar_relatorio_do_handoff", "listar_relatorios", "obter_destino", "processar_acoes",
    "processar_documento", "registrar_relatorio", "resolver_destino", "alterar_destino", "usuarios_da_org", "sanitizar_para_staff", "ServicosInternos", "texto_do_alerta",
    "texto_do_relatorio", "texto_deterministico",
]
