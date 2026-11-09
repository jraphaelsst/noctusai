"""Vista-vs-ours DIVERGENCE review -- TRANSITIONAL, removable (owner 2026-11-04).

NOC-REMEDIATE[transicao-vista-divergencias]: delete this module (and its hooks) when the owner moves the catalog off
Vista -- removal recipe: KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/vista.md § 6c -- 2026-11-04

Owner: "lets make our data count. the system recognizes divergencies from vista and warns us, so we human decide which
data is true. [...] with a notification via whatsapp on divergence. notes mapping the drift so we can check both systems
and the conversation that triggered it."

WHAT IT DOES
  During every Vista refresh (listar OR per-code), for each imóvel it compares Vista's value with OUR owned value, for the
  fields where both exist, and opens a PENDING `imovel_campo_conflitos` row (migration 154 -- the existing conflict
  machinery, no parallel store) with `origem_proposto='vista_sync'`:

    valor_anterior = OUR value, origem_anterior = where it lives, valor_proposto = Vista's, `notas` = the drift note.

  OUR value never changes here -- the sync does not write the owned layer, and a human decides:
  `POST /api/imoveis/{codigo}/divergencias/{id}/resolver` ('vista' writes Vista's value into our overlay or clears our
  override; 'nosso' keeps ours and records the decision so the same pair never alerts again; 'manual' types a third value).

OUR OWNED LAYER (the audit): `imovel_captacao` (manual captação, `atualizar_manual`), `imovel_dados` (the manual address and
  `empreendimento_manual`), and the owner's WhatsApp confirmation (`julia_proprietarios_contatos`, read through
  `julia_imovel_confirmado`: price and availability). Everything else on `imoveis` is Vista's.

NORMALISATION first: money -> 2-decimals, counts -> int, text -> accent/case/whitespace-folded, CEP -> digits, UF -> 2 upper
  letters; formatting noise is never a divergence. A side that is empty is not a divergence ("where both exist").

NOTIFICATION: ONE WhatsApp digest per refresh run to the org's destination USER (`vista_divergencias_config.destino_user_id`;
  the phone is read from core `noctus_users.telefone`, never stored here), capped per hour; no destination/phone/line =>
  an in-app notice to the org admins. Never silent.

FLAG: `vista_divergencias_config.ativa` (`divergencia_vista_ativa`), per org; missing row = OFF (the One org is seeded ON).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Awaitable, Callable, Optional
from uuid import UUID

from noctusai_lib.primitives.accents import fold_accents

from app.services import campo_conflitos, julia_imovel_confirmado

logger = logging.getLogger(__name__)

ORIGEM = "vista_sync"
T_CONFLITOS = "imovel_campo_conflitos"
T_CONFIG = "vista_divergencias_config"
T_CAPTACAO = "imovel_captacao"
T_DADOS = "imovel_dados"
T_MENSAGENS = "conversation_messages"
LIMITE_LINHAS_DIGEST = 15
DIGESTS_POR_HORA = 4
KIND_AVISO = "imoveis_vista_divergencia"
#: Catalog kind of the WhatsApp digest (core Notificações page switch).
KIND_DIGEST = "vista_divergencias"

# Origin labels of OUR value (what the review screen shows).
O_CAPTACAO = "captacao_manual"
O_DADOS = "imovel_dados_manual"
O_PROPRIETARIO = "julia_proprietario"
ROTULO_ORIGEM = {
    O_CAPTACAO: "captação manual", O_DADOS: "cadastro manual do imóvel", O_PROPRIETARIO: "confirmação do proprietário (WhatsApp)",
}
ROTULO_CAMPO = {
    "valor_venda": "valor de venda", "valor_locacao": "valor de locação", "valor_condominio": "condomínio", "valor_iptu": "IPTU",
    "area_total": "área total", "area_privativa": "área privativa", "dormitorios": "dormitórios", "suites": "suítes",
    "vagas": "vagas", "status": "status", "disponibilidade": "disponibilidade", "area_terreno_m2": "área do terreno",
    "area_construida_m2": "área construída", "logradouro": "logradouro", "numero": "número",
    "complemento": "complemento", "bairro": "bairro", "cidade": "cidade", "uf": "UF", "cep": "CEP", "empreendimento": "condomínio/empreendimento",
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
    """One refresh run's divergence context: the flag, the loaded overlay, the rows opened so far."""

    db: Any
    org_id: UUID
    captacao: dict[str, dict] = field(default_factory=dict)
    dados: dict[str, dict] = field(default_factory=dict)
    novas: list[dict] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)
    comparadas: int = 0


def config(db: Any, org_id: UUID | str) -> dict:
    """`{ativa, destino_user_id}`; a missing row or an unreadable table = OFF (logged)."""
    try:
        rows = db.table(T_CONFIG).select("*").eq("org_id", str(org_id)).limit(1).execute().data or []
    except Exception as exc:
        logger.error("vista divergences: config unreadable for org=%s (%s) -- treating as OFF", org_id, type(exc).__name__)
        return {"ativa": False, "destino_user_id": None}
    row = rows[0] if rows else {}
    return {"ativa": bool(row.get("ativa")), "destino_user_id": row.get("destino_user_id")}


def salvar_config(db: Any, org_id: UUID | str, *, ativa: Optional[bool], destino_user_id: Any, user_id: Any, mudar_destino: bool) -> dict:
    atual = db.table(T_CONFIG).select("org_id").eq("org_id", str(org_id)).limit(1).execute().data or []
    patch: dict[str, Any] = {"updated_by": str(user_id) if user_id else None, "updated_at": datetime.now(timezone.utc).isoformat()}
    if ativa is not None:
        patch["ativa"] = bool(ativa)
    if mudar_destino:
        patch["destino_user_id"] = str(destino_user_id) if destino_user_id else None
    if atual:
        db.table(T_CONFIG).update(patch).eq("org_id", str(org_id)).execute()
    else:
        db.table(T_CONFIG).insert({"org_id": str(org_id), "ativa": bool(ativa), **{k: v for k, v in patch.items() if k != "ativa"}}).execute()
    return config(db, org_id)


def iniciar(db: Any, org_id: UUID | str) -> Optional[Execucao]:
    """Open the run's context, or None when the flag is off (the single early-out: flag off => nothing happens)."""
    if not config(db, org_id)["ativa"]:
        return None
    ex = Execucao(db=db, org_id=UUID(str(org_id)))
    try:
        for r in _todas(db, T_CAPTACAO, org_id):
            ex.captacao[str(r.get("codigo_canonical") or "").upper()] = r
        for r in _todas(db, T_DADOS, org_id):
            ex.dados[str(r.get("codigo") or "").strip().upper()] = r
    except Exception as exc:
        logger.error("vista divergences: overlay unreadable for org=%s (%s) -- skipping this run", org_id, type(exc).__name__)
        return None
    return ex


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


# ── registering ─────────────────────────────────────────────────────────────
def _campo_db(d: Divergencia) -> str:
    return d.campo


def _decidido_igual(db: Any, org_id: Any, d: Divergencia) -> bool:
    """A human already decided THIS exact pair (Vista value x our value): never alert again."""
    rows = (db.table(T_CONFLITOS).select("valor_proposto,valor_anterior,decidido_por,status").eq("org_id", str(org_id))
            .eq("codigo", d.codigo).eq("campo", d.campo).eq("origem_proposto", ORIGEM).in_("status", ["aceito", "rejeitado"]).execute().data or [])
    return any(
        r.get("decidido_por") and iguais(d.campo, r.get("valor_proposto"), d.vista) and iguais(d.campo, r.get("valor_anterior"), d.nosso)
        for r in rows
    )


def registrar(db: Any, org_id: Any, d: Divergencia, notas: dict) -> Optional[dict]:
    """Open (or refresh) the pending divergence. None when nothing new: the same pair is already pending or was decided."""
    if _decidido_igual(db, org_id, d):
        return None
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
        db, campo_conflitos.IMOVEL, org_id, d.codigo, _campo_db(d),
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


def verificar(ex: Execucao, imoveis: list[Any], *, link_site: Optional[Callable[[str], Optional[str]]] = None) -> None:
    """THE call site of the sync: compare each refreshed imóvel and open the pending divergences. Never raises."""
    codigos = [i.codigo for i in imoveis]
    try:
        conf = _confirmacoes(ex.db, ex.org_id, codigos)
    except Exception as exc:
        conf = {}
        ex.erros.append(f"confirmacoes: {type(exc).__name__}")
        logger.error("vista divergences: owner confirmations unreadable (%s) -- skipping that source", type(exc).__name__)
    for imovel in imoveis:
        try:
            for d in comparar(imovel, ex, conf.get(imovel.codigo.strip().upper(), [])):
                notas = montar_notas(ex.db, ex.org_id, d, imovel, link_site=link_site(d.codigo) if link_site else None)
                linha = registrar(ex.db, ex.org_id, d, notas)
                if linha is not None:
                    ex.novas.append(linha)
        except Exception as exc:
            ex.erros.append(f"{imovel.codigo}: {type(exc).__name__}")
            logger.error("vista divergences: %s failed (%s)", imovel.codigo, type(exc).__name__, exc_info=True)


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


def resolver(db: Any, core: Any, org_id: Any, codigo: str, conflito_id: Any, escolha: str, valor: Any, user_id: Any) -> dict:
    """A human decides one pending divergence. 'vista' writes Vista's value into our overlay (or clears our override), 'nosso'
    keeps ours and records the decision (the same pair never alerts again), 'manual' types a third value. First decision wins."""
    rows = (db.table(T_CONFLITOS).select("*").eq("org_id", str(org_id)).in_("codigo", sorted({codigo, codigo.upper()}))
            .eq("id", str(conflito_id)).eq("origem_proposto", ORIGEM).limit(1).execute().data or [])
    if not rows:
        raise LookupError("divergência não encontrada")
    row = rows[0]
    if row.get("status") != "pendente":
        raise ResolucaoImpossivel("Esta divergência já foi decidida.")
    agora = datetime.now(timezone.utc).isoformat()
    if escolha == "vista":
        _escrever_nosso(db, org_id, row, row["valor_proposto"], user_id, limpar=row.get("origem_anterior") in (O_DADOS, O_PROPRIETARIO))
        status, motivo = "aceito", "vista"
    elif escolha == "manual":
        tipado = _valor_manual(row["campo"], valor)
        _escrever_nosso(db, org_id, row, tipado, user_id, limpar=False)
        status, motivo = "aceito", f"manual:{tipado}"
    else:
        status, motivo = "rejeitado", "nosso"
    db.table(T_CONFLITOS).update({"status": status, "decidido_por": str(user_id) if user_id else None, "decidido_em": agora, "motivo_resolucao": motivo}).eq(
        "id", row["id"]).execute()
    logger.info("audit: vista_divergencia resolvida org=%s codigo=%s campo=%s escolha=%s ator=%s", org_id, row["codigo"], row["campo"], escolha, user_id)
    atualizada = {**row, "status": status, "decidido_por": str(user_id) if user_id else None, "decidido_em": agora, "motivo_resolucao": motivo}
    por = (((row.get("notas") or {}).get("nosso") or {}).get("por"))
    return para_api(atualizada, _nomes(core, org_id, {str(user_id) if user_id else "", str(por) if por else ""}))


__all__ = [
    "Divergencia", "Execucao", "ORIGEM", "comparar", "config", "enviar_digest", "iguais", "iniciar", "montar_notas", "normalizar",
    "enviador_padrao", "ResolucaoImpossivel", "ResolucaoInvalida", "listar_do_imovel", "para_api", "registrar", "resolver", "salvar_config", "sanitizar_para_staff", "telefone_do_usuario", "texto_digest", "verificar",
]
