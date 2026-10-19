"""Lais wave 1 -- "Conhecimento" (lais-build-contract section 3).

Per-org knowledge sections (`lais_conhecimento_secoes`): validated per section by a pydantic
model (`extra="forbid"`), saved with an optimistic lock (`versao`), rendered into deterministic
pt-BR markdown that becomes the `conhecimento` contexto provider (agents appends it to the system
prompt, so a save changes the next turn's `contexto.hash` with no agent republish).

Registration happens at import: `registrar_provider("conhecimento", contexto_provider)`.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Callable, Literal, Optional
from urllib.parse import quote
from uuid import UUID
from zoneinfo import ZoneInfo

from noctusai_lib.primitives.exceptions import AppException
from pydantic import BaseModel, ConfigDict, Field, RootModel, ValidationError, field_validator, model_validator

from app.services import lais_contexto_service
from app.services.lais_contexto_service import ContextoCtx, FUSO

logger = logging.getLogger(__name__)

TABLE = "lais_conhecimento_secoes"
#: Fallback persona name, used ONLY when the agent's status name is unavailable (agents not configured / down).
#: The live name is the agent's own status name (`AgentsClient.agent_status().nome`) -- per-org swappable.
PERSONA_NOME = "Julia"

SECOES: tuple[str, ...] = (
    "politicas", "telefones", "exibir_atendente", "recesso", "venda_info", "venda_documentos",
    "venda_financiamento", "locacao_info", "locacao_documentos", "locacao_processo",
    "locacao_garantias", "perfil_whatsapp", "endereco_iptu",
)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _chips(v: list[str]) -> list[str]:
    """Chip lists are open vocabularies (bubble §4): each a short non-empty label, at most 40."""
    for c in v:
        if not c or len(c) > 80:
            raise ValueError("chip vazio ou maior que 80 caracteres")
    if len(v) > 40:
        raise ValueError("no máximo 40 itens")
    return v


class Politicas(_Base):
    assinatura: Literal["digital_fisico", "digital", "fisico"] = "digital_fisico"
    chaves: Literal["acompanhado", "cliente_busca", "outro"] = "acompanhado"
    chaves_outro: Optional[str] = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _outro(self) -> "Politicas":
        if self.chaves != "outro" and self.chaves_outro:
            raise ValueError("chaves_outro só vale quando chaves = outro")
        return self


_E164 = re.compile(r"^\+?\d{10,15}$")


class Telefone(_Base):
    setor: str = Field(min_length=1, max_length=60)
    telefone: str
    principal: bool = False

    @field_validator("telefone")
    @classmethod
    def _tel(cls, v: str) -> str:
        digits = re.sub(r"[\s()\-.]", "", v)
        if not _E164.match(digits):
            raise ValueError("telefone deve ter 10 a 15 dígitos (E.164)")
        return digits


class Telefones(RootModel[list[Telefone]]):
    @model_validator(mode="after")
    def _um_principal(self) -> "Telefones":
        itens = self.root
        if len(itens) > 10:
            raise ValueError("no máximo 10 telefones")
        if itens and sum(1 for t in itens if t.principal) != 1:
            raise ValueError("exatamente um telefone principal")
        return self


class ExibirAtendente(_Base):
    ativo: bool = False


class Recesso(_Base):
    ativo: bool = False
    inicio: Optional[date] = None
    fim: Optional[date] = None
    mensagem: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def _periodo(self) -> "Recesso":
        if self.inicio and self.fim and self.fim < self.inicio:
            raise ValueError("fim anterior ao início")
        if self.ativo and not (self.inicio and self.fim):
            raise ValueError("recesso ativo exige início e término")
        return self


class OperacaoInfo(_Base):
    atende: bool = False
    nomenclatura_corretor: str = Field(default="", max_length=40)


class Documentos(_Base):
    pessoais: list[str] = Field(default_factory=list)
    renda: list[str] = Field(default_factory=list)
    endereco: list[str] = Field(default_factory=list)
    adicionais: str = Field(default="", max_length=1000)

    @field_validator("pessoais", "renda", "endereco")
    @classmethod
    def _chips_ok(cls, v: list[str]) -> list[str]:
        return _chips(v)


class VendaFinanciamento(_Base):
    acompanha: bool = False
    servicos: list[Literal["despachantes", "simulacao", "bancos"]] = Field(default_factory=list)
    custos: list[str] = Field(default_factory=list)
    detalhes: str = Field(default="", max_length=1000)

    @field_validator("custos")
    @classmethod
    def _chips_ok(cls, v: list[str]) -> list[str]:
        return _chips(v)


Prazo = Literal[12, 24, 30, 36, 48, 60]


class LocacaoProcesso(_Base):
    prazo_residencial: list[Prazo] = Field(default_factory=list)
    prazo_comercial: list[Prazo] = Field(default_factory=list)
    multa: Optional[Literal["dez_pct", "tres_alugueis"]] = None
    isencao: Optional[Literal["sim", "nao", "mediante_proposta"]] = None


class Caucao(_Base):
    aceita: bool = False
    oferecer: bool = False
    min_alugueis: Optional[int] = Field(default=None, ge=0, le=24)


class SeguroFianca(_Base):
    aceita: bool = False
    oferecer: bool = False
    seguradoras: list[str] = Field(default_factory=list)

    @field_validator("seguradoras")
    @classmethod
    def _chips_ok(cls, v: list[str]) -> list[str]:
        return _chips(v)


class Fiador(_Base):
    aceita: bool = False
    oferecer: bool = False
    nome_limpo: bool = False
    imovel_quitado: bool = False
    localizacao: Optional[Literal["mesma_cidade", "mesmo_estado"]] = None


class Titulo(_Base):
    aceita: bool = False
    oferecer: bool = False
    alugueis: str = Field(default="", max_length=40)
    inclui_encargos: bool = False


class Outras(_Base):
    aceita: bool = False
    opcoes: list[str] = Field(default_factory=list)
    sem_garantia: bool = False

    @field_validator("opcoes")
    @classmethod
    def _chips_ok(cls, v: list[str]) -> list[str]:
        return _chips(v)


class LocacaoGarantias(_Base):
    caucao: Caucao = Field(default_factory=Caucao)
    seguro_fianca: SeguroFianca = Field(default_factory=SeguroFianca)
    fiador: Fiador = Field(default_factory=Fiador)
    titulo: Titulo = Field(default_factory=Titulo)
    outras: Outras = Field(default_factory=Outras)


LINK_IMOVEL_PADRAO = "{site}/imovel/{codigo}"


class PerfilWhatsapp(_Base):
    nome_exibicao: str = PERSONA_NOME  # read-only: forced to the persona on save
    descricao: str = Field(default="", max_length=512)
    sobre: str = Field(default="", max_length=139)
    endereco: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=120)
    site: str = Field(default="", max_length=200)
    #: Public listing URL template Julia sends (`link` of the tools). `{site}` = `site` above, `{codigo}` = the
    #: Vista code as stored (e.g. ONE9551). Owner, 2026-10-19: `<site>/imovel/<codigo>`. Empty = no link.
    link_imovel: str = Field(default=LINK_IMOVEL_PADRAO, max_length=300)

    @field_validator("link_imovel")
    @classmethod
    def _link_ok(cls, v: str) -> str:
        if v and "{codigo}" not in v:
            raise ValueError("o modelo do link precisa conter {codigo}")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        if v and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("e-mail inválido")
        return v


class EnderecoIptu(_Base):
    endereco_completo: bool = False
    usar_iptu: bool = False


MODELOS: dict[str, type[BaseModel]] = {
    "politicas": Politicas, "telefones": Telefones, "exibir_atendente": ExibirAtendente, "recesso": Recesso,
    "venda_info": OperacaoInfo, "venda_documentos": Documentos, "venda_financiamento": VendaFinanciamento,
    "locacao_info": OperacaoInfo, "locacao_documentos": Documentos, "locacao_processo": LocacaoProcesso,
    "locacao_garantias": LocacaoGarantias, "perfil_whatsapp": PerfilWhatsapp, "endereco_iptu": EnderecoIptu,
}
assert set(MODELOS) == set(SECOES)


# ── validation / defaults ───────────────────────────────────────────────────
def padrao(secao: str) -> Any:
    """The never-saved value of a section (JSON-mode)."""
    return _dump(MODELOS[secao].model_validate([] if secao == "telefones" else {}))


def _dump(model: BaseModel) -> Any:
    return model.model_dump(mode="json")


def validar(secao: str, dados: Any, nome_agente: Optional[str] = None) -> Any:
    """Validate + normalise `dados` for `secao`. 422 `secao_invalida` / `invalid_field`. The read-only
    `perfil_whatsapp.nome_exibicao` is forced to `nome_agente` (the agent's status name; fallback persona)."""
    if secao not in MODELOS:
        raise AppException("secao_invalida", f"Seção desconhecida: {secao}", 422, {"secao": secao})
    try:
        model = MODELOS[secao].model_validate(dados)
    except ValidationError as exc:
        erros = [{"campo": ".".join(str(p) for p in e["loc"]), "motivo": e["msg"]} for e in exc.errors()]
        raise AppException("invalid_field", "Dados inválidos para a seção.", 422, {"secao": secao, "erros": erros}) from exc
    if isinstance(model, PerfilWhatsapp):
        model = model.model_copy(update={"nome_exibicao": nome_agente or PERSONA_NOME})
    return _dump(model)


# ── persistence (optimistic lock) ───────────────────────────────────────────
def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def ler_secoes(client: Any, org_id: UUID | str, nome_agente: Optional[str] = None) -> dict[str, dict[str, Any]]:
    """Every section: saved row or default (`versao` 0 = never saved). With `nome_agente`, the read-only
    `perfil_whatsapp.nome_exibicao` always reflects the agent's current status name."""
    rows = client.table(TABLE).select("*").eq("org_id", str(org_id)).execute().data or []
    salvas = {r["secao"]: r for r in rows if r.get("secao") in MODELOS}
    out: dict[str, dict[str, Any]] = {}
    for s in SECOES:
        r = salvas.get(s)
        if r is None:
            out[s] = {"dados": padrao(s), "versao": 0, "updated_at": None}
        else:
            out[s] = {"dados": r.get("dados"), "versao": int(r.get("versao") or 1), "updated_at": r.get("updated_at")}
    if nome_agente and isinstance(out["perfil_whatsapp"].get("dados"), dict):
        out["perfil_whatsapp"]["dados"] = {**out["perfil_whatsapp"]["dados"], "nome_exibicao": nome_agente}
    return out


def _conflito(secao: str, atual: int) -> AppException:
    return AppException(
        "versao_conflito", "A seção foi alterada por outra pessoa. Recarregue e tente de novo.", 409,
        {"secao": secao, "versao_atual": atual},
    )


def salvar_secao(
    client: Any, org_id: UUID | str, secao: str, dados: Any, versao: int, user_id: Any = None,
    nome_agente: Optional[str] = None,
) -> dict[str, Any]:
    """Save with compare-and-set on `versao` (0 = first save). 409 `versao_conflito` on a stale one."""
    limpo = validar(secao, dados, nome_agente)
    atual_rows = (
        client.table(TABLE).select("versao").eq("org_id", str(org_id)).eq("secao", secao).limit(1).execute().data or []
    )
    atual = int(atual_rows[0].get("versao") or 1) if atual_rows else 0
    if versao != atual:
        raise _conflito(secao, atual)
    por = str(user_id) if user_id else None
    if atual == 0:
        row = {"org_id": str(org_id), "secao": secao, "dados": limpo, "versao": 1, "updated_by": por,
               "updated_at": _agora()}
        try:
            client.table(TABLE).insert(row).execute()
        except Exception as exc:  # PK (org_id, secao): a concurrent first save won the race
            ganhou = client.table(TABLE).select("versao").eq("org_id", str(org_id)).eq("secao", secao).execute().data
            if ganhou:
                raise _conflito(secao, int(ganhou[0].get("versao") or 1)) from exc
            raise
        return {"secao": secao, "dados": limpo, "versao": 1}
    novo = atual + 1
    res = (
        client.table(TABLE)
        .update({"dados": limpo, "versao": novo, "updated_by": por, "updated_at": _agora()})
        .eq("org_id", str(org_id)).eq("secao", secao).eq("versao", atual).execute()
    )
    if not (res.data or []):
        raise _conflito(secao, atual)  # lost the CAS: someone saved between our read and write
    return {"secao": secao, "dados": limpo, "versao": novo}


# ── recesso ─────────────────────────────────────────────────────────────────
def _hoje(agora: Optional[datetime]) -> date:
    return (agora or datetime.now(timezone.utc)).astimezone(ZoneInfo(FUSO)).date()


def _fmt_data(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def recesso_vigente(secoes: dict[str, dict[str, Any]], hoje: date) -> Optional[dict[str, Any]]:
    r = (secoes.get("recesso") or {}).get("dados") or {}
    if not r.get("ativo") or not r.get("inicio") or not r.get("fim"):
        return None
    ini, fim = date.fromisoformat(str(r["inicio"])), date.fromisoformat(str(r["fim"]))
    return r if ini <= hoje <= fim else None


def texto_recesso(r: dict[str, Any]) -> str:
    """The deterministic recesso message (the org's own text, else a default naming the period)."""
    msg = (r.get("mensagem") or "").strip()
    if msg:
        return msg
    return (f"Estamos em recesso de {_fmt_data(date.fromisoformat(str(r['inicio'])))} "
            f"a {_fmt_data(date.fromisoformat(str(r['fim'])))}. Retornamos assim que o período terminar.")


def mensagem_recesso_primeiro_turno(
    client: Any, org_id: UUID | str, contato: dict[str, Any], interacao: Optional[dict[str, Any]],
    *, agora: Optional[datetime] = None,
) -> Optional[str]:
    """The recesso message to send ON THE FIRST TURN of an interação inside the period, else None.
    "First turn" = no outbound to this contato since the interação began."""
    try:
        inicio = _ts((interacao or {}).get("iniciada_at"))
        ultimo = _ts(contato.get("ultimo_outbound_at"))
        if inicio is not None and ultimo is not None and ultimo >= inicio:
            return None
        vigente = recesso_vigente(ler_secoes(client, org_id), _hoje(agora))
    except Exception:
        logger.exception("lais: recesso check failed org=%s -- no recesso message", org_id)
        return None
    return texto_recesso(vigente) if vigente else None


def _ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── render ──────────────────────────────────────────────────────────────────
def _sn(v: Any) -> str:
    return "sim" if v else "não"


def _lista(itens: list[str]) -> str:
    return ", ".join(itens) if itens else "não informado"


_ASSINATURA = {"digital_fisico": "digital ou física", "digital": "somente digital", "fisico": "somente física"}
_CHAVES = {
    "acompanhado": "as visitas são sempre acompanhadas por alguém da equipe",
    "cliente_busca": "o cliente pode buscar a chave e visitar sozinho",
    "outro": "outra regra",
}
_MULTA = {"dez_pct": "10% do valor do contrato, proporcional aos meses restantes",
          "tres_alugueis": "3 aluguéis, proporcionais ao tempo que falta"}
_ISENCAO = {"sim": "sim", "nao": "não", "mediante_proposta": "mediante proposta e aceitação do proprietário"}
_LOCALIZACAO = {"mesma_cidade": "mesma cidade", "mesmo_estado": "mesmo estado"}


def _bloco_documentos(titulo: str, d: dict[str, Any]) -> list[str]:
    out = [f"### {titulo}",
           f"- Documentos pessoais: {_lista(d.get('pessoais') or [])}",
           f"- Comprovante de renda: {_lista(d.get('renda') or [])}",
           f"- Comprovante de endereço: {_lista(d.get('endereco') or [])}"]
    if d.get("adicionais"):
        out.append(f"- Detalhes adicionais: {d['adicionais']}")
    return out


def _garantia(nome: str, g: dict[str, Any], extras: list[str]) -> Optional[str]:
    if not g.get("aceita"):
        return None
    base = f"- {nome}: aceita" + ("; a Julia pode oferecer" if g.get("oferecer") else "")
    return base + ("; " + "; ".join(extras) if extras else "")


def render_md_secoes(secoes: dict[str, dict[str, Any]], hoje: date) -> str:
    """Deterministic pt-BR markdown of the SAVED sections (a never-saved one adds nothing)."""
    def d(s: str) -> Any:
        return secoes[s]["dados"] if secoes[s]["versao"] else None

    out: list[str] = []
    r = recesso_vigente(secoes, hoje)
    if r:
        out += ["## Aviso de recesso", f"A imobiliária está em recesso até {_fmt_data(date.fromisoformat(str(r['fim'])))}. "
                f"Avise o cliente: {texto_recesso(r)}", ""]

    geral: list[str] = []
    if (p := d("politicas")):
        geral.append(f"- Assinatura de contrato: {_ASSINATURA[p['assinatura']]}")
        chaves = _CHAVES[p["chaves"]]
        if p["chaves"] == "outro" and p.get("chaves_outro"):
            chaves = p["chaves_outro"]
        geral.append(f"- Chaves para visitar: {chaves}")
    if (tels := d("telefones")):
        geral.append("- Telefones por setor:")
        for t in tels:
            geral.append(f"  - {t['setor']}: {t['telefone']}" + (" (principal)" if t["principal"] else ""))
    if geral:
        out += ["## Informações gerais", *geral, ""]

    venda: list[str] = []
    if (v := d("venda_info")):
        venda.append(f"- A imobiliária atende compra: {_sn(v['atende'])}")
        if v.get("nomenclatura_corretor"):
            venda.append(f"- Chame o profissional de: {v['nomenclatura_corretor']}")
    if (docs := d("venda_documentos")):
        venda += _bloco_documentos("Documentos necessários", docs)
    if (f := d("venda_financiamento")):
        nomes = {"despachantes": "parceria com despachantes", "simulacao": "simulação de financiamento",
                 "bancos": "parceria com bancos"}
        venda += ["### Financiamento", f"- A imobiliária acompanha o processo: {_sn(f['acompanha'])}",
                  f"- Serviços oferecidos: {_lista([nomes[s] for s in f['servicos']])}",
                  f"- Custos do financiamento: {_lista(f['custos'])}"]
        if f.get("detalhes"):
            venda.append(f"- Detalhes: {f['detalhes']}")
    if venda:
        out += ["## Vendas", *venda, ""]

    loc: list[str] = []
    if (v := d("locacao_info")):
        loc.append(f"- A imobiliária atende locação: {_sn(v['atende'])}")
        if v.get("nomenclatura_corretor"):
            loc.append(f"- Chame o profissional de: {v['nomenclatura_corretor']}")
    if (docs := d("locacao_documentos")):
        loc += _bloco_documentos("Documentos necessários", docs)
    if (pr := d("locacao_processo")):
        loc.append("### Processo de locação")
        loc.append(f"- Prazo padrão residencial (meses): {_lista([str(x) for x in pr['prazo_residencial']])}")
        loc.append(f"- Prazo padrão comercial (meses): {_lista([str(x) for x in pr['prazo_comercial']])}")
        loc.append(f"- Multa rescisória padrão: {_MULTA.get(pr['multa'], 'não informado')}")
        loc.append(f"- Isenção de multa: {_ISENCAO.get(pr['isencao'], 'não informado')}")
    if (g := d("locacao_garantias")):
        linhas = [x for x in (
            _garantia("Caução", g["caucao"], [f"mínimo de {g['caucao']['min_alugueis']} aluguéis"]
                      if g["caucao"].get("min_alugueis") is not None else []),
            _garantia("Seguro fiança", g["seguro_fianca"],
                      [f"seguradoras: {_lista(g['seguro_fianca']['seguradoras'])}"]),
            _garantia("Fiador", g["fiador"], [e for e in (
                "nome limpo" if g["fiador"]["nome_limpo"] else "",
                "imóvel quitado" if g["fiador"]["imovel_quitado"] else "",
                f"localização: {_LOCALIZACAO[g['fiador']['localizacao']]}" if g["fiador"].get("localizacao") else "") if e]),
            _garantia("Título de capitalização", g["titulo"], [e for e in (
                f"valor: {g['titulo']['alugueis']} aluguéis" if g["titulo"].get("alugueis") else "",
                "inclui encargos (IPTU, condomínio)" if g["titulo"]["inclui_encargos"] else "") if e]),
            _garantia("Outras garantias", g["outras"], [e for e in (
                f"opções: {_lista(g['outras']['opcoes'])}" if g["outras"]["opcoes"] else "",
                "é possível alugar sem garantia, com aprovação do proprietário" if g["outras"]["sem_garantia"] else "") if e]),
        ) if x]
        loc.append("### Garantias aceitas")
        loc += linhas or ["- nenhuma garantia informada"]
    if loc:
        out += ["## Locação", *loc, ""]
    return "\n".join(out).strip()


def hash_md(markdown: str) -> str:
    return hashlib.sha256(markdown.encode("utf-8")).hexdigest()


def render_md(client: Any, org_id: UUID | str, *, hoje: Optional[date] = None, agora: Optional[datetime] = None) -> str:
    return render_md_secoes(ler_secoes(client, org_id), hoje or _hoje(agora))


# ── endereco_iptu (read by the tools route) ─────────────────────────────────
def politica_endereco_iptu(client: Any, org_id: UUID | str) -> dict[str, bool]:
    """`{endereco_completo, usar_iptu}`; BOTH false when never saved or unreadable (privacy-safe)."""
    try:
        d = ler_secoes(client, org_id)["endereco_iptu"]["dados"]
    except Exception:
        logger.exception("lais: endereco_iptu read failed org=%s -- address/IPTU withheld", org_id)
        return {"endereco_completo": False, "usar_iptu": False}
    return {"endereco_completo": bool(d.get("endereco_completo")), "usar_iptu": bool(d.get("usar_iptu"))}


def _site_base(site: str) -> str:
    site = (site or "").strip().rstrip("/")
    if site and not re.match(r"^https?://", site, re.I):
        site = f"https://{site}"
    return site


def montar_link_imovel(modelo: str, site: str, codigo: str) -> Optional[str]:
    """The public listing URL from the org's template; None when the template is empty or needs a `site` the org
    never filled in (Julia then sends no link rather than a broken one)."""
    modelo, codigo = (modelo or "").strip(), (codigo or "").strip()
    if not modelo or not codigo:
        return None
    base = _site_base(site)
    if "{site}" in modelo and not base:
        return None
    return modelo.replace("{site}", base).replace("{codigo}", quote(codigo, safe=""))


def link_imovel_fn(client: Any, org_id: UUID | str) -> Callable[[str], Optional[str]]:
    """`codigo -> link` for one tool call (one read of "Meu negócio › Perfil do WhatsApp"). Unreadable => no links,
    logged (a link is a convenience; the listing data still goes out)."""
    try:
        d = ler_secoes(client, org_id)["perfil_whatsapp"]["dados"] or {}
    except Exception:
        logger.exception("lais: perfil_whatsapp read failed org=%s -- listings go out without a link", org_id)
        return lambda _codigo: None
    modelo = d.get("link_imovel", LINK_IMOVEL_PADRAO)
    site = d.get("site") or ""
    return lambda codigo: montar_link_imovel(modelo, site, codigo)


# ── contexto provider ───────────────────────────────────────────────────────
def contexto_provider(ctx: ContextoCtx) -> dict[str, Any]:
    return {"conhecimento_md": render_md(ctx.client, ctx.org_id, agora=ctx.agora)}


lais_contexto_service.registrar_provider("conhecimento", contexto_provider)

__all__ = [
    "MODELOS", "SECOES", "contexto_provider", "hash_md", "ler_secoes", "mensagem_recesso_primeiro_turno",
    "padrao", "politica_endereco_iptu", "recesso_vigente", "render_md", "render_md_secoes", "salvar_secao",
    "texto_recesso", "validar",
]
