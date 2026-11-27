"""Vista sync with HISTORY -- what the Vista refresh does with a difference between Vista and what we hold (owner 2026-11-04).

NOC-REMEDIATE[transicao-vista-divergencias]: delete this module (and its hooks) when the owner moves the catalog off
Vista -- removal recipe: KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/vista.md § 6c -- 2026-11-04

AMENDED (2026-11-15, owner option 1): the WhatsApp DIGEST of the approvals a run opens is KEPT, switchable per kind on the core
Notificações page (`KIND_DIGEST`) and aimed at `vista_divergencias_config.destino_user_id`; everything else below stands.

DECISION REVERSED (2026-11-04). The first version of this module only RECORDED a pending divergence and sent a WhatsApp
digest to a chosen user ("we human decide which data is true"). The owner reversed it: "no one receives the alert, we update
our database to the Vista data and history gets an action register [...] in-app notification only. no whatsapp, no email."
and "if julia is certain on a owner-confirmation, we edit vista [...] i need a switch to vista editing on and off default
off [...] if we cant edit/create on vista, vista wins for now and get an approval with link to the conversation."
So: no digest, no destination user, no phone, no hourly cap. Every case below writes an `imovel_historico` row.

WHAT THE SYNC DOES (`verificar`, per refreshed imóvel; `imovel_notas`, documents, owners and duplicates have no Vista
counterpart and are never touched):
  1. A MIRROR column changed (`CAMPOS_ESPELHO`; the upsert already applied it): history `campo_atualizado` (old -> new). The
     price columns are NOT repeated here -- migration 262's trigger records them (`imovel_preco_historico`, kind `preco`).
  2. An OVERLAY field (captação, `imovel_dados` manual address / empreendimento / areas) differs and is not owner-confirmed:
     Vista wins -- Vista's value goes into the overlay through `_escrever_nosso` (captação gets the value; `imovel_dados`
     is cleared so Vista shows through): history `vista_prevaleceu`.
  3. An OWNER-CONFIRMED price/availability (`julia_imovel_confirmado`) differs from Vista:
       a. CERTAIN (an explicit, recorded owner confirmation: `confirmado_at` set -- `julia_proprietarios_service.confirmar`
          only stores one after the owner answered a Cloud template) AND the org switch `vista_escrita_ativa` is on AND the
          PUT is permitted (cached probe) AND the field is pushable (`CAMPO_VISTA`: the two prices) => `PUT /imoveis/detalhes`
          sets Vista to our value; history `enviado_ao_vista` with the conversation {id, url}. A failed send => history
          `envio_vista_falhou` and the approval below.
       b. otherwise (switch off / not permitted / not certain / not pushable / failed) => Vista wins (`vista_prevaleceu`)
          AND an approval opens: a PENDING `imovel_campo_conflitos` row (origem_proposto `vista_sync`) carrying the
          conversation link + history `aprovacao_pendente` + an in-app notice `imovel_aprovacao_pendente` to the org admins.
     Resolving (`resolver`): `aprovar` pushes our value to Vista when the switch is on and the PUT is permitted, else records
     "atualizar manualmente no Vista"; `recusar` keeps Vista. Both write `aprovacao_decidida`.
  PER RUN: ONE in-app notice `imoveis_vista_sincronizado` to the admins when Vista changed >= 1 imóvel (`notificar_sincronizado`).

NORMALISATION first: money -> 2-decimals, counts -> int, text -> accent/case/whitespace-folded, CEP -> digits, UF -> 2 upper
letters; formatting noise is never a difference. A side that is empty is not a difference ("where both exist").

SWITCHES (`vista_divergencias_config`, per org; missing row = everything OFF; the One org is seeded `ativa` ON by 317):
  `ativa`               keep the imóveis in line with Vista (history + overlay + notices). Off => the sync touches nothing here.
  `vista_escrita_ativa` (default OFF) edit Vista when the owner confirmed. Needs the key's PUT grant (probe 2026-11-04: granted).

NOTE IN VISTA (owner 2026-11-04, binding: never edit Vista without a reason and a note): every send carries a `motivo` and writes
our dated line into the property's `ObsVenda`/`ObsLocacao` in the same PUT (seed `observacoes`: before the first dated line, header
untouched, read just before the PUT, a failed read writes nothing); the history `detalhe` mirrors that line. `ObsLocacao` is presumed
(unverified).
NOC-REMEDIATE[vista-escrita-disponibilidade]: availability is NOT pushed (the tenant's `Status` vocabulary for sold/suspended is
unproven); it takes the Vista-wins + approval path -- 2026-11-04
NOC-REMEDIATE[notificacoes-destinatarios-seed]: recipients (org owners + admins) come from `julia_notificacoes_service.admins_da_org`;
move to the seed `noctusai_lib.domain.notifications` recipients helper once the parallel branch lands it -- 2026-11-04
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import quote
from uuid import UUID

from noctusai_lib.primitives.accents import fold_accents

from app.services import campo_conflitos, imovel_historico_service as hist, julia_imovel_confirmado

logger = logging.getLogger(__name__)

ORIGEM = "vista_sync"
T_CONFLITOS = "imovel_campo_conflitos"
T_CONFIG = "vista_divergencias_config"
T_CAPTACAO = "imovel_captacao"
T_DADOS = "imovel_dados"
T_MENSAGENS = "conversation_messages"
T_MIRROR = "imoveis"
KIND_SINCRONIZADO = "imoveis_vista_sincronizado"
KIND_APROVACAO = "imovel_aprovacao_pendente"
LIMITE_LINHAS_DIGEST = 15
DIGESTS_POR_HORA = 4
KIND_AVISO = "imoveis_vista_divergencia"
#: Catalog kind of the WhatsApp digest of the approvals a run opened (core Notificações page switch).
KIND_DIGEST = "vista_divergencias"
#: Mirror columns whose change is written to the history (prices are NOT: the 262 trigger records them as kind `preco`).
CAMPOS_ESPELHO = (
    "status", "exibir_no_site", "categoria", "valor_condominio", "valor_iptu", "area_total", "area_privativa", "area_construida",
    "dormitorios", "suites", "vagas", "cep", "logradouro", "numero", "complemento", "bairro", "cidade", "uf", "empreendimento",
)
#: Our field -> the Vista field `PUT /imoveis/detalhes` sets. Only the two prices are pushed (see NOC-REMEDIATE[vista-escrita-disponibilidade]).
CAMPO_VISTA = {"valor_venda": "ValorVenda", "valor_locacao": "ValorLocacao"}
#: How long a write-permission verdict is trusted (one probe is one Vista call).
PERMISSAO_TTL_S = 900
PERMISSAO_TTL_DESCONHECIDA_S = 60
ENVIO_REPETIDO_H = 24

# Origin labels of OUR value (what the review screen shows).
O_CAPTACAO = "captacao_manual"
O_DADOS = "imovel_dados_manual"
O_PROPRIETARIO = "julia_proprietario"
ROTULO_ORIGEM = {
    O_CAPTACAO: "captação manual", O_DADOS: "cadastro manual do imóvel", O_PROPRIETARIO: "confirmação do proprietário (WhatsApp)",
}
ROTULO_CAMPO = {
    "exibir_no_site": "exibir no site", "categoria": "categoria",
    "valor_venda": "valor de venda", "valor_locacao": "valor de locação", "valor_condominio": "condomínio", "valor_iptu": "IPTU",
    "area_total": "área total", "area_privativa": "área privativa", "dormitorios": "dormitórios", "suites": "suítes",
    "vagas": "vagas", "status": "status", "disponibilidade": "disponibilidade", "area_terreno_m2": "área do terreno",
    "area_construida_m2": "área construída", "logradouro": "logradouro", "numero": "número",
    "complemento": "complemento", "bairro": "bairro", "cidade": "cidade", "uf": "UF", "cep": "CEP", "empreendimento": "condomínio/empreendimento",
    "video_youtube": "vídeo do YouTube",  # imovel_video_youtube_service (history `campo`)
}
DINHEIRO = {"valor_venda", "valor_locacao", "valor_condominio", "valor_iptu"}
MEDIDA = {"area_total", "area_privativa", "area_terreno_m2", "area_construida_m2"}
#: Our `imovel_dados` valuation columns -> the Vista attribute they correspond to (campo = OUR column name).
_DADOS_MEDIDAS = {"area_terreno_m2": "area_terreno", "area_construida_m2": "area_construida"}
CONTAGEM = {"dormitorios", "suites", "vagas"}


# ── normalisation ───────────────────────────────────────────────────────────
def _num(valor: Any) -> Optional[Decimal]:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return Decimal(str(valor).strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _texto(valor: Any) -> Optional[str]:
    if valor is None:
        return None
    t = " ".join(fold_accents(str(valor)).casefold().split())
    return t or None


def normalizar(campo: str, valor: Any) -> Any:
    """The canonical comparable of `valor` for `campo` (None = empty). Equal canonicals are NOT a divergence."""
    if campo in DINHEIRO or campo in MEDIDA:
        n = _num(valor)
        return n if n is not None and n != 0 else None  # Vista's "0" means unset
    if campo in CONTAGEM:
        n = _num(valor)
        return int(n) if n is not None else None
    if campo == "cep":
        d = re.sub(r"\D", "", str(valor or ""))
        return d or None
    if campo == "uf":
        t = _texto(valor)
        return t.upper()[:2] if t else None
    return _texto(valor)


def para_json(campo: str, valor: Any) -> Any:
    """The value as stored on the conflict row (JSONB): numbers as numbers, text as text."""
    if valor is None:
        return None
    if campo in DINHEIRO or campo in MEDIDA:
        n = _num(valor)
        return float(n) if n is not None else None
    if campo in CONTAGEM:
        n = _num(valor)
        return int(n) if n is not None else None
    return str(valor).strip()


def exibir(campo: str, valor: Any) -> str:
    if valor is None:
        return "—"
    if campo in DINHEIRO:
        n = _num(valor)
        return f"R$ {n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if n is not None else str(valor)
    return str(valor)


def iguais(campo: str, a: Any, b: Any) -> bool:
    return normalizar(campo, a) == normalizar(campo, b)


# ── the divergence model ────────────────────────────────────────────────────
@dataclass
class Divergencia:
    codigo: str
    campo: str
    nosso: Any
    vista: Any
    origem: str  # O_*
    nosso_em: Optional[str] = None
    nosso_por: Optional[str] = None
    conversa: Optional[dict] = None


@dataclass
class Execucao:
    """One refresh run's context: the switches, the loaded overlay, the mirror rows as they were BEFORE the upsert, and what the
    run did (the history rows to write, the approvals opened, the counts the per-run notice reports)."""

    db: Any
    org_id: UUID
    adapter: Any = None
    escrita_ativa: bool = False
    captacao: dict[str, dict] = field(default_factory=dict)
    dados: dict[str, dict] = field(default_factory=dict)
    antes: dict[str, dict] = field(default_factory=dict)
    novas: list[dict] = field(default_factory=list)  # approvals opened this run (pending `imovel_campo_conflitos` rows)
    erros: list[str] = field(default_factory=list)
    comparadas: int = 0
    imoveis_atualizados: set = field(default_factory=set)
    campos_atualizados: int = 0
    enviados: int = 0
    _permitida: Optional[bool] = None
    _permitida_lida: bool = False


def config(db: Any, org_id: UUID | str) -> dict:
    """`{ativa, vista_escrita_ativa, destino_user_id}`; a missing row or an unreadable table = both switches OFF (logged)."""
    try:
        rows = db.table(T_CONFIG).select("*").eq("org_id", str(org_id)).limit(1).execute().data or []
    except Exception as exc:
        logger.error("vista sync: config unreadable for org=%s (%s) -- treating as OFF", org_id, type(exc).__name__)
        return {"ativa": False, "vista_escrita_ativa": False, "destino_user_id": None}
    row = rows[0] if rows else {}
    return {"ativa": bool(row.get("ativa")), "vista_escrita_ativa": bool(row.get("vista_escrita_ativa")), "destino_user_id": row.get("destino_user_id")}


def salvar_config(
    db: Any, org_id: UUID | str, *, ativa: Optional[bool] = None, vista_escrita_ativa: Optional[bool] = None, user_id: Any = None,
    destino_user_id: Any = None, mudar_destino: bool = False,
) -> dict:
    atual = db.table(T_CONFIG).select("org_id").eq("org_id", str(org_id)).limit(1).execute().data or []
    patch: dict[str, Any] = {"updated_by": str(user_id) if user_id else None, "updated_at": datetime.now(timezone.utc).isoformat()}
    if ativa is not None:
        patch["ativa"] = bool(ativa)
    if vista_escrita_ativa is not None:
        patch["vista_escrita_ativa"] = bool(vista_escrita_ativa)
    if mudar_destino:
        patch["destino_user_id"] = str(destino_user_id) if destino_user_id else None
    if atual:
        db.table(T_CONFIG).update(patch).eq("org_id", str(org_id)).execute()
    else:
        db.table(T_CONFIG).insert({"org_id": str(org_id), "ativa": False, "vista_escrita_ativa": False, **patch}).execute()
    return config(db, org_id)


def iniciar(db: Any, org_id: UUID | str, adapter: Any = None) -> Optional[Execucao]:
    """Open the run's context, or None when `ativa` is off (the single early-out: switch off => nothing happens)."""
    cfg = config(db, org_id)
    if not cfg["ativa"]:
        return None
    ex = Execucao(db=db, org_id=UUID(str(org_id)), adapter=adapter, escrita_ativa=cfg["vista_escrita_ativa"])
    try:
        for r in _todas(db, T_CAPTACAO, org_id):
            ex.captacao[str(r.get("codigo_canonical") or "").upper()] = r
        for r in _todas(db, T_DADOS, org_id):
            ex.dados[str(r.get("codigo") or "").strip().upper()] = r
    except Exception as exc:
        logger.error("vista sync: overlay unreadable for org=%s (%s) -- skipping this run", org_id, type(exc).__name__)
        return None
    return ex


def capturar_antes(ex: Execucao, imoveis: list[Any]) -> None:
    """Read the mirror columns as they are NOW (call BEFORE the upsert) so `verificar` can tell what the upsert changed. Never raises."""
    alvo = sorted({i.codigo for i in imoveis if getattr(i, "codigo", None)})
    colunas = "codigo, " + ", ".join(CAMPOS_ESPELHO)
    try:
        for i in range(0, len(alvo), 100):
            rows = (ex.db.table(T_MIRROR).select(colunas).eq("org_id", str(ex.org_id)).in_("codigo", alvo[i:i + 100]).limit(1000).execute().data or [])
            for r in rows:
                ex.antes[str(r["codigo"]).strip().upper()] = r
    except Exception as exc:
        ex.erros.append(f"antes: {type(exc).__name__}")
        logger.error("vista sync: the mirror 'before' read failed org=%s (%s) -- no field history for this batch", ex.org_id, type(exc).__name__)


def _todas(db: Any, tabela: str, org_id: Any) -> list[dict]:
    saida, inicio = [], 0
    while True:
        rows = db.table(tabela).select("*").eq("org_id", str(org_id)).range(inicio, inicio + 999).execute().data or []
        saida.extend(rows)
        if len(rows) < 1000:
            return saida
        inicio += 1000


# ── comparison ──────────────────────────────────────────────────────────────
_ENDERECO = {
    "logradouro": "endereco_manual_logradouro", "numero": "endereco_manual_numero", "complemento": "endereco_manual_complemento",
    "bairro": "endereco_manual_bairro", "cidade": "endereco_manual_cidade", "uf": "endereco_manual_uf", "cep": "endereco_manual_cep",
}
_CAPTACAO_CAMPOS = (*sorted(DINHEIRO), *sorted(MEDIDA), *sorted(CONTAGEM), "status")
_DISPONIVEIS = {"disponivel", "ativo", "ativa", "livre", "a venda", "para venda", "para alugar"}
_INDISPONIVEIS = {"vendido", "vendida", "alugado", "alugada", "indisponivel", "suspenso", "suspensa", "inativo", "inativa", "retirado", "retirada"}


def _vista(imovel: Any, campo: str) -> Any:
    return getattr(imovel, campo, None)


def _disponibilidade_vista(imovel: Any) -> str:
    listado = (imovel.status or "").strip().lower() in {"venda", "aluguel", "venda e aluguel"} and imovel.exibir_no_site is not False
    return "disponivel" if listado else "indisponivel"


def _disponibilidade_nossa(status: Any) -> Optional[str]:
    t = _texto(status)
    if t in _DISPONIVEIS:
        return "disponivel"
    if t in _INDISPONIVEIS:
        return "indisponivel"
    return None  # a status we cannot place on the axis is not comparable


def comparar(imovel: Any, ex: Execucao, confirmacoes: list[dict]) -> list[Divergencia]:
    """Every real difference between Vista's `imovel` and our owned values (pure given the loaded overlay)."""
    codigo = imovel.codigo
    chave = codigo.strip().upper()
    saida: list[Divergencia] = []

    cap = ex.captacao.get(chave)
    if cap:
        for campo in _CAPTACAO_CAMPOS:
            nosso, vista = cap.get(campo), _vista(imovel, campo)
            ex.comparadas += 1
            if normalizar(campo, nosso) is not None and normalizar(campo, vista) is not None and not iguais(campo, nosso, vista):
                saida.append(Divergencia(codigo, campo, nosso, vista, O_CAPTACAO, cap.get("updated_at"), cap.get("updated_por")))

    dados = ex.dados.get(chave)
    if dados:
        pares = [(c, dados.get(col)) for c, col in _ENDERECO.items()] + [("empreendimento", dados.get("empreendimento_manual"))]
        pares += [(c, dados.get(c)) for c in _DADOS_MEDIDAS]
        for campo, nosso in pares:
            vista = _vista(imovel, _DADOS_MEDIDAS.get(campo, campo))
            ex.comparadas += 1
            if normalizar(campo, nosso) is not None and normalizar(campo, vista) is not None and not iguais(campo, nosso, vista):
                if campo in _DADOS_MEDIDAS:
                    em, por = dados.get("avaliacao_campos_atualizado_em"), dados.get("avaliacao_campos_atualizado_por")
                elif campo in _ENDERECO:
                    em, por = dados.get("endereco_manual_confirmado_em"), dados.get("endereco_manual_confirmado_por")
                else:
                    em, por = dados.get("empreendimento_manual_confirmado_em"), dados.get("empreendimento_manual_confirmado_por")
                saida.append(Divergencia(codigo, campo, nosso, vista, O_DADOS, em or dados.get("updated_at"), por))

    if confirmacoes:
        for campo, tipo in (("valor_venda", "venda"), ("valor_locacao", "locacao")):
            conf = julia_imovel_confirmado.aplicar(confirmacoes, data_atualizacao=imovel.data_atualizacao, preco_tipo=tipo)
            if conf is None or "preco" not in conf:
                continue
            vista = _vista(imovel, campo)
            ex.comparadas += 1
            if normalizar(campo, vista) is not None and not iguais(campo, conf["preco"], vista):
                bruta = next((c for c in confirmacoes if c.get("preco_confirmado") is not None and c.get("preco_tipo_confirmado") == tipo), {})
                saida.append(Divergencia(codigo, campo, conf["preco"], vista, O_PROPRIETARIO, bruta.get("confirmado_at"), None, {"proprietario_contato_id": bruta.get("id")}))
        conf = julia_imovel_confirmado.aplicar(confirmacoes, data_atualizacao=imovel.data_atualizacao)
        if conf is not None and conf.get("status"):
            nossa = _disponibilidade_nossa(conf["status"])
            ex.comparadas += 1
            if nossa is not None and nossa != _disponibilidade_vista(imovel):
                bruta = next((c for c in confirmacoes if c.get("status_confirmado")), {})
                saida.append(Divergencia(codigo, "disponibilidade", nossa, _disponibilidade_vista(imovel), O_PROPRIETARIO, bruta.get("confirmado_at"), None, {"proprietario_contato_id": bruta.get("id"), "status_texto": conf["status"]}))
    return saida


# ── the drift note ──────────────────────────────────────────────────────────
_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_TEL = re.compile(r"\+?\d[\d\s().-]{8,}\d")


def sanitizar_para_staff(texto: str, limite: int = 240) -> str:
    """Strip links and phone numbers from a lead/owner message before staff sees it and cut it short.
    NOC-REMEDIATE[sanitizar-para-staff-compartilhado]: replace with `julia_relatorio_service.sanitizar_para_staff` once
    feat/julia-v3-sw-turno is merged -- 2026-11-04"""
    limpo = _TEL.sub("[telefone]", _URL.sub("[link]", texto or ""))
    return " ".join(limpo.split())[:limite]


def _conversa(db: Any, org_id: Any, d: Divergencia) -> Optional[dict]:
    """Where our value came from, when it was said in a conversation: the owner contact and the (sanitised) message that
    preceded the confirmation. Best-effort -- a lookup failure is reported in the note, never swallowed."""
    base = d.conversa
    if not base or not base.get("proprietario_contato_id"):
        return None
    saida: dict[str, Any] = {"tipo": "whatsapp_proprietario", "proprietario_contato_id": str(base["proprietario_contato_id"])}
    try:
        contato = (db.table("julia_proprietarios_contatos").select("telefone").eq("org_id", str(org_id))
                   .eq("id", str(base["proprietario_contato_id"])).limit(1).execute().data or [])
        tel = re.sub(r"\D", "", str(contato[0].get("telefone") or "")) if contato else ""
        if tel:
            saida["telefone_final"] = tel[-4:]
            contatos = (db.table("julia_contatos").select("id, chat_id").eq("org_id", str(org_id))
                        .in_("chat_id", [f"{tel}@c.us", f"{tel}@s.whatsapp.net"]).limit(1).execute().data or [])
            if contatos:
                saida["contato_id"] = str(contatos[0]["id"])
                saida["thread_id"] = contatos[0].get("chat_id")
            msgs = (db.table(T_MENSAGENS).select("body, created_at, direction, chat_id").eq("org_id", str(org_id))
                    .in_("chat_id", [f"{tel}@c.us", f"{tel}@s.whatsapp.net", f"+{tel}"]).eq("direction", "inbound")
                    .order("created_at", desc=True).limit(20).execute().data or [])
            corte = str(d.nosso_em or "")
            msg = next((m for m in msgs if not corte or str(m.get("created_at") or "") <= corte), msgs[0] if msgs else None)
            if msg:
                saida["trecho"] = sanitizar_para_staff(msg.get("body") or "")
                saida["trecho_em"] = msg.get("created_at")
    except Exception as exc:
        saida["trecho_indisponivel"] = type(exc).__name__
        logger.warning("vista divergences: conversation excerpt lookup failed org=%s (%s)", org_id, type(exc).__name__)
    return saida


def montar_notas(db: Any, org_id: Any, d: Divergencia, imovel: Any, *, link_site: Optional[str]) -> dict:
    return {
        "tipo": "vista_divergencia",
        "codigo": d.codigo,
        "campo": d.campo,
        "rotulo": ROTULO_CAMPO.get(d.campo, d.campo),
        "vista": {
            "valor": para_json(d.campo, d.vista),
            "definido_em": imovel.data_atualizacao.isoformat() if getattr(imovel, "data_atualizacao", None) else None,
            "nota": "DataAtualizacao do Vista (data da última edição do imóvel, não do campo)",
        },
        "nosso": {
            "valor": para_json(d.campo, d.nosso),
            "origem": d.origem,
            "origem_rotulo": ROTULO_ORIGEM.get(d.origem, d.origem),
            "definido_em": str(d.nosso_em) if d.nosso_em else None,
            "por": str(d.nosso_por) if d.nosso_por else None,
            "conversa": _conversa(db, org_id, d),
        },
        "links": {"vista_codigo": d.codigo, "site": link_site, "sistema": f"/imoveis/{d.codigo}"},
        "detectado_em": datetime.now(timezone.utc).isoformat(),
    }


# ── the conversation behind an owner-confirmed value ────────────────────────
def link_conversa(conversa: Optional[dict]) -> Optional[dict]:
    """`{id, url}` of the conversation a drift note cites (the Julia contact when known, else the chat), or None."""
    if not conversa:
        return None
    contato, thread = conversa.get("contato_id"), conversa.get("thread_id")
    if contato:
        url: Optional[str] = f"/julia/conversas?contato={contato}"
    elif thread:
        url = f"/julia/conversas?chat={quote(str(thread), safe='')}"
    else:
        url = None
    ident = contato or thread or conversa.get("proprietario_contato_id")
    return {"id": str(ident), "url": url} if ident else None


def _certo(d: Divergencia) -> bool:
    """Is Julia CERTAIN of this owner confirmation? -- an explicit, recorded confirmation: the row exists and carries
    `confirmado_at` (`_confirmacoes` only returns rows that do, and `julia_proprietarios_service.confirmar` only stores one after the
    owner answered a Cloud template). There is no finer-grained confidence in the data, so nothing weaker counts."""
    return d.origem == O_PROPRIETARIO and bool(d.conversa and d.conversa.get("proprietario_contato_id")) and d.nosso_em is not None


# ── registering ─────────────────────────────────────────────────────────────
def registrar(db: Any, org_id: Any, d: Divergencia, notas: dict) -> Optional[dict]:
    """Open the APPROVAL (a pending `imovel_campo_conflitos` row, `origem_proposto='vista_sync'`). None when nothing new: the same
    pair is already pending, or an extraction conflict owns this (codigo, campo)."""
    existente = campo_conflitos.conflito_pendente_existente(db, campo_conflitos.IMOVEL, org_id, d.codigo, d.campo)
    if existente is not None and existente.get("origem_proposto") != ORIGEM:
        return None  # an extraction conflict owns this (codigo, campo): never touched from here
    if existente is not None and iguais(d.campo, existente.get("valor_proposto"), d.vista):
        if iguais(d.campo, existente.get("valor_anterior"), d.nosso):
            return None  # the same pair, again: nothing new
        # Vista unchanged but OUR value changed: the old question is stale -- close it so the fresh one can open.
        campo_conflitos._t(db, T_CONFLITOS).update({"status": "rejeitado", "decidido_por": None, "decidido_em": datetime.now(timezone.utc).isoformat()}).eq(
            "id", existente["id"]).execute()
    linha = campo_conflitos.registrar_conflito(
        db, campo_conflitos.IMOVEL, org_id, d.codigo, d.campo,
        valor_anterior=para_json(d.campo, d.nosso), origem_anterior=d.origem,
        valor_proposto=para_json(d.campo, d.vista), origem_proposto=ORIGEM,
        fonte_tabela="imoveis", fonte_id=None, igual=lambda a, b: iguais(d.campo, a, b),
    )
    if linha is not None:
        campo_conflitos._t(db, T_CONFLITOS).update({"notas": notas}).eq("id", linha["id"]).execute()
        linha = {**linha, "notas": notas}
    return linha


def _confirmacoes(db: Any, org_id: Any, codigos: list[str]) -> dict[str, list[dict]]:
    """`{CODIGO: [confirmed rows, newest first]}` -- the same rows `julia_imovel_confirmado.carregar` reads, plus the row `id`
    (the owner contact, needed to trace the conversation). Only status / price / date / id leave this read: never the phone."""
    alvo = sorted({str(c).strip().upper() for c in codigos if c and str(c).strip()})
    saida: dict[str, list[dict]] = {}
    for i in range(0, len(alvo), 100):
        rows = (db.table(julia_imovel_confirmado.TABLE).select("id, imovel_codigo, status_confirmado, preco_confirmado, preco_tipo_confirmado, confirmado_at")
                .eq("org_id", str(org_id)).in_("imovel_codigo", alvo[i:i + 100]).limit(1000).execute().data or [])
        for r in rows:
            if julia_imovel_confirmado._instante(r.get("confirmado_at")) is not None:
                saida.setdefault(str(r["imovel_codigo"]).strip().upper(), []).append(r)
    for lista in saida.values():
        lista.sort(key=lambda r: julia_imovel_confirmado._instante(r["confirmado_at"]), reverse=True)
    return saida


# ── writing to Vista ────────────────────────────────────────────────────────
def _valor_vista(valor: Any) -> str:
    n = _num(valor)
    if n is None:
        raise ValueError("valor sem número")
    return str(int(n)) if n == n.to_integral_value() else f"{n:.2f}"


def _url_absoluta(link: Optional[str]) -> Optional[str]:
    """The conversation link as Vista's readers can open it: the frontend base URL + our relative path (relative when unset)."""
    if not link or link.startswith("http"):
        return link
    try:
        from app.config import settings

        base = (settings.frontend_base_url or "").rstrip("/")
    except Exception:
        base = ""
    return f"{base}{link}" if base else link


_FINALIDADE = {"valor_venda": "venda", "valor_locacao": "locacao"}


async def enviar_ao_vista(
    adapter: Any, codigo: str, campo: str, valor: Any, *, motivo: str, conversa: Optional[dict] = None, canal: str = "WhatsApp (Julia)",
    fonte: str = "Proprietário", autor: str = "NoctusAI",
) -> tuple[Optional[str], Optional[str]]:
    """Set `campo` to `valor` on Vista (`PUT /imoveis/detalhes`) AND leave the note in its internal observations (rule: never edit Vista
    without a reason and a note). Returns `(erro, nota)`: `(None, line)` = sent; `(failure's class name, None)` otherwise (never a body: a
    401 body embeds the key). Never raises."""
    if adapter is None:
        return "sem_adaptador", None
    if campo not in CAMPO_VISTA:
        return "campo_nao_enviavel", None
    try:
        nota = await adapter.atualizar_imovel(
            codigo, {CAMPO_VISTA[campo]: _valor_vista(valor)}, motivo=motivo, autor=autor, canal=canal, fonte=fonte, finalidade=_FINALIDADE[campo],
            conversa_url=_url_absoluta((conversa or {}).get("url")), rotulos={CAMPO_VISTA[c]: ROTULO_CAMPO[c] for c in CAMPO_VISTA},
        )
    except Exception as exc:
        logger.warning("vista sync: PUT of %s/%s failed (%s)", codigo, campo, type(exc).__name__)
        return type(exc).__name__, None
    return None, nota


_PERMISSAO: dict[str, tuple[float, Optional[bool]]] = {}


async def escrita_disponivel(org_id: Any, provider: Callable[[], Any], *, forcar: bool = False) -> Optional[bool]:
    """May this org's Vista key `PUT /imoveis/detalhes`? Cached probe (non-mutating: empty PUT on a non-existent code):
    True permitted / False denied / None unknown (no credential, timeout, ...). `provider()` returns the adapter or raises."""
    chave = str(org_id)
    agora = time.monotonic()
    em_cache = _PERMISSAO.get(chave)
    if em_cache and not forcar and em_cache[0] > agora:
        return em_cache[1]
    try:
        veredito: Optional[bool] = await provider().pode_atualizar_imovel()
    except Exception as exc:
        logger.info("vista sync: write-permission probe unavailable org=%s (%s)", org_id, type(exc).__name__)
        veredito = None
    _PERMISSAO[chave] = (agora + (PERMISSAO_TTL_S if veredito is not None else PERMISSAO_TTL_DESCONHECIDA_S), veredito)
    return veredito


async def _permitida(ex: Execucao) -> Optional[bool]:
    if not ex._permitida_lida:
        ex._permitida = await escrita_disponivel(ex.org_id, lambda: ex.adapter) if ex.adapter is not None else None
        ex._permitida_lida = True
    return ex._permitida


# ── handling one difference ─────────────────────────────────────────────────
def _enviado_recentemente(db: Any, org_id: Any, d: Divergencia) -> bool:
    """We already sent THIS value for this field in the last day (Vista has not reflected it yet): do not send again."""
    rows = (db.table(hist.T_HISTORICO).select("valor_novo, ocorrido_em").eq("org_id", str(org_id)).eq("codigo_canonical", d.codigo.strip().upper())
            .eq("campo", d.campo).eq("acao", "enviado_ao_vista").order("ocorrido_em", desc=True).limit(1).execute().data or [])
    if not rows or not iguais(d.campo, rows[0].get("valor_novo"), d.nosso):
        return False
    instante = julia_imovel_confirmado._instante(rows[0].get("ocorrido_em"))
    return instante is not None and (datetime.now(timezone.utc) - instante).total_seconds() < ENVIO_REPETIDO_H * 3600


def _vista_prevalece(ex: Execucao, d: Divergencia) -> bool:
    """Vista wins: Vista's value goes into OUR layer (`_escrever_nosso`). False when the owned layer refused (reported, logged)."""
    row = {"campo": d.campo, "codigo": d.codigo, "origem_anterior": d.origem, "notas": {"nosso": {"conversa": d.conversa}}}
    try:
        _escrever_nosso(ex.db, ex.org_id, row, para_json(d.campo, d.vista), None, limpar=d.origem in (O_DADOS, O_PROPRIETARIO))
    except ResolucaoImpossivel as exc:
        ex.erros.append(f"{d.codigo}/{d.campo}: {exc}")
        return False
    return True


async def _tratar(ex: Execucao, d: Divergencia, notas: dict, historico: list[dict]) -> None:
    conversa = link_conversa((notas.get("nosso") or {}).get("conversa"))
    antes, depois = para_json(d.campo, d.nosso), para_json(d.campo, d.vista)
    rotulo = ROTULO_CAMPO.get(d.campo, d.campo)
    if d.origem != O_PROPRIETARIO:
        if _vista_prevalece(ex, d):
            historico.append(hist.montar_linha(ex.org_id, d.codigo, origem="vista_sync", acao="vista_prevaleceu", campo=d.campo, anterior=antes, novo=depois,
                                               detalhe=f"Vista prevaleceu em {rotulo} sobre o valor de {ROTULO_ORIGEM.get(d.origem, d.origem)}."))
            ex.imoveis_atualizados.add(d.codigo)
            ex.campos_atualizados += 1
        return
    # an owner-confirmed value
    if _enviado_recentemente(ex.db, ex.org_id, d):
        return
    motivo = "escrita_desligada" if not ex.escrita_ativa else ("campo_nao_enviavel" if d.campo not in CAMPO_VISTA else ("sem_certeza" if not _certo(d) else None))
    if motivo is None:
        permitida = await _permitida(ex)
        if permitida:
            erro, nota = await enviar_ao_vista(
                ex.adapter, d.codigo, d.campo, d.nosso, conversa=conversa,
                motivo=f"proprietário confirmou {rotulo} e o valor estava diferente no Vista")
            if erro is None:
                historico.append(hist.montar_linha(  # `detalhe` mirrors the note written into Vista's ObsVenda/ObsLocacao
                    ex.org_id, d.codigo, origem="julia", acao="enviado_ao_vista", campo=d.campo, anterior=depois, novo=antes, conversa=conversa,
                    detalhe=nota))
                ex.enviados += 1
                return
            historico.append(hist.montar_linha(ex.org_id, d.codigo, origem="julia", acao="envio_vista_falhou", campo=d.campo, anterior=depois, novo=antes,
                                               conversa=conversa, detalhe=f"Não foi possível enviar ao Vista ({erro}). Vista prevaleceu e abriu aprovação."))
            motivo = "falha_envio"
        else:
            motivo = "sem_permissao" if permitida is False else "permissao_desconhecida"
    linha = registrar(ex.db, ex.org_id, d, notas)
    if linha is None:
        return  # the same approval is already pending
    ex.novas.append(linha)
    _vista_prevalece(ex, d)
    ex.imoveis_atualizados.add(d.codigo)
    ex.campos_atualizados += 1
    historico.append(hist.montar_linha(ex.org_id, d.codigo, origem="vista_sync", acao="vista_prevaleceu", campo=d.campo, anterior=antes, novo=depois,
                                       conversa=conversa, detalhe=f"Vista prevaleceu em {rotulo} (envio ao Vista: {motivo})."))
    historico.append(hist.montar_linha(ex.org_id, d.codigo, origem="julia", acao="aprovacao_pendente", campo=d.campo, anterior=depois, novo=antes,
                                       conversa=conversa, conflito_id=linha["id"], detalhe="Valor confirmado pelo proprietário aguardando aprovação."))


async def verificar(ex: Execucao, imoveis: list[Any], *, link_site: Optional[Callable[[str], Optional[str]]] = None) -> None:
    """THE call site of the sync (after the upsert): for each refreshed imóvel write the history of what changed, let Vista win over
    our overlay, and send or approve an owner-confirmed value. Never raises."""
    codigos = [i.codigo for i in imoveis]
    try:
        conf = _confirmacoes(ex.db, ex.org_id, codigos)
    except Exception as exc:
        conf = {}
        ex.erros.append(f"confirmacoes: {type(exc).__name__}")
        logger.error("vista sync: owner confirmations unreadable (%s) -- skipping that source", type(exc).__name__)
    for imovel in imoveis:
        historico: list[dict] = []
        try:
            for campo in CAMPOS_ESPELHO:  # 1. what the upsert changed on the mirror
                velho = (ex.antes.get(imovel.codigo.strip().upper()) or {})
                if campo not in velho:
                    continue
                novo = getattr(imovel, campo, None)
                if normalizar(campo, novo) is not None and not iguais(campo, velho.get(campo), novo):
                    historico.append(hist.montar_linha(ex.org_id, imovel.codigo, origem="vista_sync", acao="campo_atualizado", campo=campo,
                                                       anterior=para_json(campo, velho.get(campo)), novo=para_json(campo, novo)))
                    ex.imoveis_atualizados.add(imovel.codigo)
                    ex.campos_atualizados += 1
            for d in comparar(imovel, ex, conf.get(imovel.codigo.strip().upper(), [])):  # 2. + 3. our layer vs Vista
                notas = montar_notas(ex.db, ex.org_id, d, imovel, link_site=link_site(d.codigo) if link_site else None)
                await _tratar(ex, d, notas, historico)
        except Exception as exc:
            ex.erros.append(f"{imovel.codigo}: {type(exc).__name__}")
            logger.error("vista sync: %s failed (%s)", imovel.codigo, type(exc).__name__, exc_info=True)
        try:
            hist.registrar_varias(ex.db, historico)
        except Exception as exc:
            ex.erros.append(f"{imovel.codigo}: historico {type(exc).__name__}")
            logger.error("vista sync: the history of %s could not be written (%s)", imovel.codigo, type(exc).__name__, exc_info=True)


# ── the digest ──────────────────────────────────────────────────────────────
def _telefone_valido(valor: Any) -> Optional[str]:
    digitos = "".join(c for c in str(valor or "") if c.isdigit())
    return f"+{digitos}" if 10 <= len(digitos) <= 15 else None


def telefone_do_usuario(core: Any, org_id: Any, user_id: Any) -> Optional[str]:
    """The destination's WhatsApp, read from core `public.noctus_users.telefone` (the one place a person's number lives).
    NOC-REMEDIATE[resolve-user-phones]: switch to the seed `resolve_user_phones` once it lands -- 2026-11-04"""
    if not user_id or core is None:
        return None
    try:
        rows = core.table("noctus_users").select("*").eq("id", str(user_id)).limit(1).execute().data or []
    except Exception as exc:
        logger.error("vista divergences: noctus_users.telefone unreadable (%s)", type(exc).__name__)
        return None
    row = rows[0] if rows else None
    return _telefone_valido(row.get("telefone")) if row and str(row.get("org_id")) == str(org_id) else None


def texto_digest(novas: list[dict], base_url: str = "") -> str:
    linhas = []
    for r in novas[:LIMITE_LINHAS_DIGEST]:
        n = r.get("notas") or {}
        campo = r["campo"]
        linhas.append(
            f"• {r['codigo']} · {ROTULO_CAMPO.get(campo, campo)}: Vista {exibir(campo, (n.get('vista') or {}).get('valor', r.get('valor_proposto')))}"
            f" × nosso {exibir(campo, (n.get('nosso') or {}).get('valor', r.get('valor_anterior')))} → {base_url}/imoveis/{r['codigo']}"
        )
    mais = len(novas) - LIMITE_LINHAS_DIGEST
    cab = f"Divergência com o Vista: {len(novas)} campo(s) em {len({r['codigo'] for r in novas})} imóvel(is). Decida qual dado vale:"
    return "\n".join([cab, *linhas, *([f"…e mais {mais}."] if mais > 0 else [])])


Enviador = Callable[[Any, str, str], Awaitable[Optional[str]]]


def _digests_na_ultima_hora(db: Any, org_id: Any) -> int:
    corte = datetime.now(timezone.utc).timestamp() - 3600
    rows = (db.table(T_CONFLITOS).select("notificado_em").eq("org_id", str(org_id)).eq("origem_proposto", ORIGEM).execute().data or [])
    vistos = set()
    for r in rows:
        ts = r.get("notificado_em")
        if not ts:
            continue
        try:
            if datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp() >= corte:
                vistos.add(str(ts))
        except ValueError:
            continue
    return len(vistos)


async def enviar_digest(
    db: Any, core: Any, org_id: Any, novas: list[dict], *, enviar: Optional[Enviador] = None, base_url: str = "",
) -> str:
    """ONE digest for the run. Returns how it went: `whatsapp` | `in_app:<motivo>` | `nada`. Never raises, never silent."""
    if not novas:
        return "nada"
    from noctusai_lib.domain.notification_catalog import get_notification_gate

    from app.services.notification_kinds import PRODUCT as _PRODUCT

    gate = get_notification_gate(_PRODUCT)
    if not gate.allowed(KIND_DIGEST):
        gate.record(KIND_DIGEST, org_id=org_id, status="suppressed", recipients=1, reason="desligada em Notificações")
        return "desligada"
    texto = texto_digest(novas, base_url)
    cfg = config(db, org_id)
    telefone = telefone_do_usuario(core, org_id, cfg["destino_user_id"])
    motivo = None
    if telefone is None:
        motivo = "sem_telefone_do_destino"
    elif _digests_na_ultima_hora(db, org_id) >= DIGESTS_POR_HORA:
        motivo = "limite_por_hora"
    elif enviar is None:
        motivo = "sem_transporte"
    else:
        try:
            erro = await enviar(org_id, telefone, texto)
        except Exception as exc:
            erro = type(exc).__name__
        if erro:
            motivo = f"falha_envio:{erro}"
    via = "whatsapp"
    gate.record(
        KIND_DIGEST, org_id=org_id,
        status=("no_recipient" if motivo == "sem_telefone_do_destino" else "failed") if motivo else "sent",
        recipients=0 if motivo == "sem_telefone_do_destino" else 1, delivered=0 if motivo else 1, reason=motivo,
    )
    if motivo is not None:
        via = f"in_app:{motivo}"
        _aviso_in_app(core, org_id, novas, texto)
        logger.warning("vista divergences: WhatsApp digest not sent for org=%s (%s) -- in-app notice instead", org_id, motivo)
    agora = datetime.now(timezone.utc).isoformat()
    for r in novas:
        campo_conflitos._t(db, T_CONFLITOS).update({"notificado_em": agora}).eq("id", r["id"]).execute()
    return via


def enviador_padrao(db: Any) -> Enviador:
    """The production sender: the org's Julia line (its WAHA/Cloud connection that is on Julia, else its first), free text to
    the destination user's number through `julia_transporte`.
    NOC-REMEDIATE[transicao-vista-divergencias-staff-send]: route through the staff-send path of feat/julia-v3-sw-turno
    (`julia_relatorio_service.enviar_aviso_interno`: outbound gate flow `interno`, per-paragraph split) once it is merged;
    until then the hourly cap lives here (`DIGESTS_POR_HORA`) -- 2026-11-04"""

    async def enviar(org_id: Any, telefone: str, texto: str) -> Optional[str]:
        from uuid import UUID as _UUID

        from app.config import settings
        from app.dependencies import get_admin_client
        from app.services import julia_transporte
        from app.services.whatsapp_connection_store import build_whatsapp_connection_store

        rows = db.table("whatsapp_connections").select("id,agente_leads_ativo").eq("org_id", str(org_id)).execute().data or []
        rows.sort(key=lambda r: (r.get("agente_leads_ativo") is not True, str(r.get("id"))))
        if not rows:
            return "sem_linha"
        record = build_whatsapp_connection_store(get_admin_client(), encryption_key=settings.encryption_key).get_by_id(
            _UUID(str(rows[0]["id"])), decrypt=True)
        if record is None:
            return "sem_linha"
        await julia_transporte.transporte_da_conexao(record).enviar_texto(telefone, texto)
        return None

    return enviar


def _aviso_in_app(core: Any, org_id: Any, novas: list[dict], texto: str) -> None:
    from noctusai_lib.domain.notifications import write_in_app

    try:
        rows = core.table("noctus_users").select("id,org_role").eq("org_id", str(org_id)).execute().data or []
        admins = sorted({str(r["id"]) for r in rows if r.get("org_role") in ("owner", "admin")})
        if not admins:
            raise RuntimeError("sem_destinatarios")
        write_in_app(core, user_ids=admins, kind=KIND_AVISO, org_id=org_id, title="Divergência com o Vista", message=texto[:900],
                     metadata={"product": "social-wiring", "link": "/imoveis", "total": len(novas)})
    except Exception as exc:
        logger.error("vista divergences: the in-app divergence notice failed org=%s (%s)", org_id, type(exc).__name__)


# ── the in-app notices (operational class; never WhatsApp / e-mail) ─────────
def _metadata(link: Optional[str], codigo: Optional[str] = None) -> dict:
    return {"categoria": "operacional", "link": link, "produto": "social-wiring",
            "entidade": {"tipo": "imovel", "id": codigo} if codigo else None}


def _avisar(core: Any, org_id: Any, kind: str, title: str, message: str, metadata: dict) -> int:
    """One in-app row per org owner/admin. An empty recipient set is logged at WARNING and returns 0; never raises."""
    from noctusai_lib.domain.notifications import write_in_app

    from app.services.julia_notificacoes_service import admins_da_org

    try:
        admins = admins_da_org(core, org_id) if core is not None else []
        if not admins:
            logger.warning("vista sync: notice %s for org=%s has no recipients (no owner/admin)", kind, org_id)
            return 0
        return write_in_app(core, user_ids=admins, kind=kind, org_id=org_id, title=title[:60], message=message[:160], metadata=metadata)
    except Exception as exc:
        logger.error("vista sync: notice %s failed org=%s (%s)", kind, org_id, type(exc).__name__)
        return 0


def notificar_sincronizado(core: Any, org_id: Any, imoveis: int, campos: int) -> int:
    """ONE notice per run, only when Vista changed at least one imóvel."""
    if imoveis <= 0:
        return 0
    plural = "imóvel" if imoveis == 1 else "imóveis"
    campo = "campo" if campos == 1 else "campos"
    return _avisar(core, org_id, KIND_SINCRONIZADO, f"Vista atualizou {imoveis} {plural}", f"Vista atualizou {imoveis} {plural} ({campos} {campo}).", _metadata("/imoveis"))


def notificar_aprovacoes(core: Any, org_id: Any, linhas: list[dict], *, maximo: int = 10) -> int:
    """One notice per approval opened (the first `maximo`; the rest folded into one), each linking to its imóvel."""
    total = 0
    for r in linhas[:maximo]:
        campo = r["campo"]
        rotulo = ROTULO_CAMPO.get(campo, campo)
        total += _avisar(core, org_id, KIND_APROVACAO, f"Aprovação pendente · {r['codigo']}",
                         f"O proprietário confirmou {rotulo} {exibir(campo, r.get('valor_anterior'))}; o Vista tem {exibir(campo, r.get('valor_proposto'))}.",
                         _metadata(f"/imoveis/{r['codigo']}", r["codigo"]))
    if len(linhas) > maximo:
        total += _avisar(core, org_id, KIND_APROVACAO, "Aprovações pendentes", f"Mais {len(linhas) - maximo} aprovações de imóveis aguardam decisão.", _metadata("/imoveis"))
    return total


# ── resolving (a human decides) ─────────────────────────────────────────────
class ResolucaoInvalida(ValueError):
    """`valor` missing/invalid for the chosen escolha (422)."""


class ResolucaoImpossivel(RuntimeError):
    """The owned layer refused the write (a constraint) -- nothing changed (409)."""


def _valor_manual(campo: str, valor: Any) -> Any:
    if campo == "disponibilidade":
        if _disponibilidade_nossa(valor) is None:
            raise ResolucaoInvalida("Use 'disponivel' ou 'indisponivel'.")
        return _disponibilidade_nossa(valor)
    if isinstance(valor, str) and (campo in DINHEIRO or campo in MEDIDA or campo in CONTAGEM) and "," in valor:
        valor = valor.replace(".", "").replace(",", ".")  # "815.000,50" -> "815000.50"
    n = normalizar(campo, valor)
    if n is None:
        raise ResolucaoInvalida("Informe um valor válido para este campo.")
    if campo in DINHEIRO or campo in MEDIDA:
        if n < 0:
            raise ResolucaoInvalida("O valor não pode ser negativo.")
        return float(n)
    if campo in CONTAGEM:
        if n < 0:
            raise ResolucaoInvalida("O valor não pode ser negativo.")
        return int(n)
    return str(valor).strip()


def _escrever_nosso(db: Any, org_id: Any, row: dict, valor: Any, user_id: Any, *, limpar: bool) -> None:
    """Write `valor` into (or, with `limpar`, clear) OUR owned value that `row` is about. One writer per origin."""
    campo, codigo, origem = row["campo"], row["codigo"], row.get("origem_anterior")
    agora = datetime.now(timezone.utc).isoformat()
    uid = str(user_id) if user_id else None
    try:
        if origem == O_CAPTACAO:
            db.table(T_CAPTACAO).update({campo: None if limpar else valor, "updated_por": uid, "updated_at": agora}).eq(
                "org_id", str(org_id)).eq("codigo_canonical", codigo.strip().upper()).execute()
        elif origem == O_DADOS:
            col = campo if campo in _DADOS_MEDIDAS else _ENDERECO.get(campo, "empreendimento_manual")
            patch: dict[str, Any] = {col: None if limpar else valor, "updated_at": agora}
            if campo == "empreendimento" and limpar:
                patch.update({"empreendimento_manual_confirmado_por": None, "empreendimento_manual_confirmado_em": None})
            db.table(T_DADOS).update(patch).eq("org_id", str(org_id)).eq("codigo", codigo).execute()
        elif origem == O_PROPRIETARIO:
            contato = (((row.get("notas") or {}).get("nosso") or {}).get("conversa") or {}).get("proprietario_contato_id")
            if campo in ("valor_venda", "valor_locacao"):
                tipo = "venda" if campo == "valor_venda" else "locacao"
                patch = ({"preco_confirmado": None, "preco_tipo_confirmado": None} if limpar
                         else {"preco_confirmado": valor, "preco_tipo_confirmado": tipo, "confirmado_at": agora})
            else:
                patch = {"status_confirmado": None} if limpar else {"status_confirmado": valor, "confirmado_at": agora}
            q = db.table(julia_imovel_confirmado.TABLE).update({**patch, "updated_at": agora}).eq("org_id", str(org_id))
            q = q.eq("id", str(contato)) if contato else q.eq("imovel_codigo", codigo)
            q.execute()
        else:
            raise ResolucaoImpossivel(f"origem desconhecida: {origem}")
    except ResolucaoImpossivel:
        raise
    except Exception as exc:
        logger.error("vista divergences: writing the owned value failed org=%s %s/%s (%s)", org_id, codigo, campo, type(exc).__name__)
        raise ResolucaoImpossivel("Não foi possível gravar o valor (o cadastro recusou a alteração).") from exc


TIPO_ORIGEM = {O_CAPTACAO: "captacao", O_DADOS: "cadastro", O_PROPRIETARIO: "julia"}


def _nomes(core: Any, org_id: Any, ids: set[str]) -> dict[str, Optional[str]]:
    ids = {i for i in ids if i}
    if not ids or core is None:
        return {}
    try:
        rows = core.table("noctus_users").select("*").in_("id", sorted(ids)).execute().data or []
    except Exception as exc:
        logger.warning("vista divergences: user names unreadable (%s)", type(exc).__name__)
        return {}
    return {str(r["id"]): r.get("nome") for r in rows if str(r.get("org_id")) == str(org_id)}


def para_api(row: dict, nomes: dict[str, Optional[str]]) -> dict:
    """The conflict row as the review screen's `Divergencia` (FE contract, 2026-11-04): status pendente|resolvido, both values with
    when/who set them, the origin of OUR value (`tipo` captacao|cadastro|julia + contato/thread/excerpt) and the resolution."""
    n = row.get("notas") or {}
    nosso = n.get("nosso") or {}
    conversa = nosso.get("conversa") or {}
    por = nosso.get("por")
    origem = None
    if row.get("origem_anterior"):
        origem = {"tipo": TIPO_ORIGEM.get(row["origem_anterior"], row["origem_anterior"])}
        if conversa:
            origem.update({"contato_id": conversa.get("contato_id"), "thread_id": conversa.get("thread_id"), "trecho": conversa.get("trecho")})
    saida: dict[str, Any] = {
        "id": str(row["id"]), "campo": row["campo"], "status": "pendente" if row.get("status") == "pendente" else "resolvido",
        "valor_vista": row.get("valor_proposto"), "vista_em": (n.get("vista") or {}).get("definido_em"),
        "valor_nosso": row.get("valor_anterior"), "nosso_em": nosso.get("definido_em"),
        "nosso_por": {"id": str(por), "nome": nomes.get(str(por))} if por else None,
        "origem": origem,
    }
    if row.get("status") != "pendente":
        motivo = str(row.get("motivo_resolucao") or "")
        escolha = "manual" if motivo.startswith("manual:") else motivo
        decidor = row.get("decidido_por")
        saida["resolucao"] = {
            "escolha": escolha, "valor": motivo[len("manual:"):] if escolha == "manual" else None,
            "por": {"id": str(decidor), "nome": nomes.get(str(decidor))} if decidor else None, "em": row.get("decidido_em"),
        }
    return saida


def listar_do_imovel(db: Any, core: Any, org_id: Any, codigo: str) -> dict:
    """`{items}`: the pending divergences first (newest first), then the decided ones. A row the SYSTEM closed (superseded by a
    newer Vista value, no human) is not history a person made, so it is left out."""
    rows = (db.table(T_CONFLITOS).select("*").eq("org_id", str(org_id)).in_("codigo", sorted({codigo, codigo.upper()}))
            .eq("origem_proposto", ORIGEM).order("created_at", desc=True).limit(500).execute().data or [])
    rows = [r for r in rows if r.get("status") == "pendente" or r.get("decidido_por")]
    rows.sort(key=lambda r: (r.get("status") != "pendente",))  # stable: pending first, order kept
    ids = {str(r.get("notas", {}).get("nosso", {}).get("por")) for r in rows if (r.get("notas") or {}).get("nosso", {}).get("por")}
    ids |= {str(r["decidido_por"]) for r in rows if r.get("decidido_por")}
    nomes = _nomes(core, org_id, ids)
    return {"items": [para_api(r, nomes) for r in rows]}


#: `empurrar(codigo, campo, valor, conversa) -> (reason, nota)`: sends our value to Vista (with its note) when the org switch is on and the
#: PUT is permitted; `(None, line)` = sent, else a reason (`escrita_desligada`, `sem_permissao`, `campo_nao_enviavel`, a failure's class name).
Empurrar = Callable[[str, str, Any, Optional[dict]], tuple[Optional[str], Optional[str]]]


def _historico_decisao(db: Any, org_id: Any, row: dict, user_id: Any, *, detalhe: str, enviado: Optional[str], erro: Optional[str]) -> None:
    """The `aprovacao_decidida` row (+ `enviado_ao_vista` / `envio_vista_falhou` when a send was attempted). A failed history write is
    logged at ERROR: the decision itself is already stored."""
    n = row.get("notas") or {}
    conversa = link_conversa((n.get("nosso") or {}).get("conversa"))
    campo, codigo = row["campo"], row["codigo"]
    linhas = []
    if enviado is not None:
        linhas.append(hist.montar_linha(org_id, codigo, origem="usuario", acao="enviado_ao_vista", campo=campo, anterior=row.get("valor_proposto"),
                                        novo=row.get("valor_anterior"), ator=user_id, conversa=conversa, detalhe=enviado))
    if erro is not None:
        linhas.append(hist.montar_linha(org_id, codigo, origem="usuario", acao="envio_vista_falhou", campo=campo, anterior=row.get("valor_proposto"),
                                        novo=row.get("valor_anterior"), ator=user_id, conversa=conversa, detalhe=erro))
    linhas.append(hist.montar_linha(org_id, codigo, origem="usuario", acao="aprovacao_decidida", campo=campo, anterior=row.get("valor_proposto"),
                                    novo=row.get("valor_anterior"), ator=user_id, conversa=conversa, conflito_id=row["id"], detalhe=detalhe))
    try:
        hist.registrar_varias(db, linhas)
    except Exception as exc:
        logger.error("vista sync: the approval decision of %s/%s could not be written to the history (%s)", codigo, campo, type(exc).__name__)


def resolver(
    db: Any, core: Any, org_id: Any, codigo: str, conflito_id: Any, escolha: str, valor: Any, user_id: Any, empurrar: Optional[Empurrar] = None,
) -> dict:
    """A person decides one pending approval. `aprovar` = our (owner-confirmed) value is right: pushed to Vista through `empurrar` when
    the switch is on and the PUT is permitted, else recorded as "atualizar manualmente no Vista" (the link stays). `recusar` = keep
    Vista (already applied for an owner value; for an older overlay row it is written into our layer now). The legacy `vista | nosso |
    manual` choices of the first version still resolve rows opened by it. Every decision writes `aprovacao_decidida`. First decision wins."""
    rows = (db.table(T_CONFLITOS).select("*").eq("org_id", str(org_id)).in_("codigo", sorted({codigo, codigo.upper()}))
            .eq("id", str(conflito_id)).eq("origem_proposto", ORIGEM).limit(1).execute().data or [])
    if not rows:
        raise LookupError("divergência não encontrada")
    row = rows[0]
    if row.get("status") != "pendente":
        raise ResolucaoImpossivel("Esta divergência já foi decidida.")
    agora = datetime.now(timezone.utc).isoformat()
    enviado = erro = None
    if escolha == "aprovar":
        conversa_link = link_conversa((((row.get("notas") or {}).get("nosso") or {}).get("conversa")))
        motivo_envio, nota = empurrar(row["codigo"], row["campo"], row["valor_anterior"], conversa_link) if empurrar is not None else ("escrita_desligada", None)
        if motivo_envio is None:
            enviado = nota  # the note line written into Vista
            detalhe = "Aprovado e enviado ao Vista."
        else:
            if motivo_envio not in ("escrita_desligada", "sem_permissao", "campo_nao_enviavel", "permissao_desconhecida"):
                erro = f"Não foi possível enviar ao Vista ({motivo_envio})."
            detalhe = "Aprovado — atualizar manualmente no Vista" + (f" ({motivo_envio})." if motivo_envio != "escrita_desligada" else ".")
        status, motivo = "aceito", "aprovar"
    elif escolha == "recusar":
        if row.get("origem_anterior") in (O_CAPTACAO, O_DADOS):
            _escrever_nosso(db, org_id, row, row["valor_proposto"], user_id, limpar=row.get("origem_anterior") == O_DADOS)
        status, motivo, detalhe = "rejeitado", "recusar", "Mantido o valor do Vista."
    elif escolha == "vista":
        _escrever_nosso(db, org_id, row, row["valor_proposto"], user_id, limpar=row.get("origem_anterior") in (O_DADOS, O_PROPRIETARIO))
        status, motivo, detalhe = "aceito", "vista", "Mantido o valor do Vista."
    elif escolha == "manual":
        tipado = _valor_manual(row["campo"], valor)
        _escrever_nosso(db, org_id, row, tipado, user_id, limpar=False)
        status, motivo, detalhe = "aceito", f"manual:{tipado}", f"Valor digitado: {tipado}."
    else:
        status, motivo, detalhe = "rejeitado", "nosso", "Mantido o nosso valor."
    db.table(T_CONFLITOS).update({"status": status, "decidido_por": str(user_id) if user_id else None, "decidido_em": agora, "motivo_resolucao": motivo}).eq(
        "id", row["id"]).execute()
    logger.info("audit: vista_divergencia resolvida org=%s codigo=%s campo=%s escolha=%s ator=%s", org_id, row["codigo"], row["campo"], escolha, user_id)
    _historico_decisao(db, org_id, row, user_id, detalhe=detalhe, enviado=enviado, erro=erro)
    atualizada = {**row, "status": status, "decidido_por": str(user_id) if user_id else None, "decidido_em": agora, "motivo_resolucao": motivo}
    por = (((row.get("notas") or {}).get("nosso") or {}).get("por"))
    return para_api(atualizada, _nomes(core, org_id, {str(user_id) if user_id else "", str(por) if por else ""}))


__all__ = [
    "Divergencia", "Execucao", "ORIGEM", "ResolucaoImpossivel", "ResolucaoInvalida", "capturar_antes", "comparar", "config", "enviar_ao_vista",
    "escrita_disponivel", "iguais", "iniciar", "link_conversa", "listar_do_imovel", "montar_notas", "normalizar", "notificar_aprovacoes",
    "notificar_sincronizado", "para_api", "registrar", "resolver", "salvar_config", "sanitizar_para_staff", "verificar",
]
