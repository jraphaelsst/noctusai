"""O2 -- apply the interview's answers as ONE step with a per-item report (applied / refused + why).

Spec answers go through the SAME validator the studio PUT uses (:func:`app.studio.especificacoes_service.validar`) and
are written with ONE ``gravar_specs`` call (the caller binds it to ``aplicar_org_specs``, so declared-key rule, audit
and report/block rollout stay in that one write path). Unlike the studio PUT in report mode, an INVALID value is never
written here: it is refused with the validator's reason, so the interview never stores something it knows is wrong.
SW operational settings go through the :class:`~app.onboarding.sw_settings.SwSettingsPort`; human steps (credentials,
approvals) are reported ``pendente_humano``. Nothing is skipped silently: every answered item lands in the report.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
from urllib.parse import urlparse
from uuid import UUID

from app.onboarding.checklist import CHECKLIST, Item, item_por_numero, itens_aplicaveis
from app.onboarding.sw_settings import SwSettingsPort
from app.studio.especificacoes_service import validar
from app.studio.models import ConfigValidacao

__all__ = ["ItemRelatorio", "Relatorio", "aplicar", "progresso", "operacoes_de"]

APLICADO, RECUSADO, PENDENTE_HUMANO = "aplicado", "recusado", "pendente_humano"
PENDENTE_CONFIRMACAO = "pendente_confirmacao"
MAX_PERGUNTAS_EXTRAS = 5
_VAZIO = (None, "", [], {})
_SIM = {"sim", "s", "true", "1", "yes", "on"}
_NAO = {"nao", "não", "n", "false", "0", "no", "off"}


@dataclass
class ItemRelatorio:
    n: int
    titulo: str
    estado: str
    codigo: str | None = None
    motivo: str | None = None
    destino: str = ""
    #: for a refused/pending SW item: where to apply it by hand and with what body.
    rota: str | None = None
    corpo: dict[str, Any] | None = None


@dataclass
class Relatorio:
    itens: list[ItemRelatorio] = field(default_factory=list)
    #: required items (that apply) still unanswered after this step -- the go-live gate's view of the interview.
    obrigatorios_faltando: list[int] = field(default_factory=list)

    @property
    def aplicados(self) -> int:
        return sum(1 for i in self.itens if i.estado == APLICADO)

    @property
    def recusados(self) -> int:
        return sum(1 for i in self.itens if i.estado == RECUSADO)


def _texto(v: Any) -> str:
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x).strip() for x in v if str(x).strip())
    return str(v).strip() if v is not None else ""


def operacoes_de(valor: Any) -> set[str]:
    from app.studio.especificacoes_service import _canonico_vocabulario  # the closed-vocabulary canon (accent/case)

    t = _texto(valor)
    return {p.strip() for p in _canonico_vocabulario(t).split(",") if p.strip()} if t else set()


def _bool(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    s = _texto(v).casefold()
    return True if s in _SIM else False if s in _NAO else None


class _Recusa(Exception):
    def __init__(self, codigo: str, motivo: str) -> None:
        super().__init__(motivo)
        self.codigo, self.motivo = codigo, motivo


def _inteiro(v: Any, lo: int, hi: int, nome: str, passo: int = 1) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise _Recusa("valor_invalido", f"{nome}: informe um número inteiro.") from None
    if not lo <= n <= hi or n % passo:
        raise _Recusa("valor_invalido", f"{nome}: de {lo} a {hi}" + (f", de {passo} em {passo}." if passo > 1 else "."))
    return n


def _booleano(v: Any, nome: str) -> bool:
    b = _bool(v)
    if b is None:
        raise _Recusa("valor_invalido", f"{nome}: responda sim ou não.")
    return b


def _opcao(v: Any, opcoes: tuple[str, ...], nome: str) -> str:
    s = _texto(v).casefold()
    if s not in opcoes:
        raise _Recusa("valor_invalido", f"{nome}: use {' ou '.join(opcoes)}.")
    return s


def _dict(v: Any, nome: str) -> dict[str, Any]:
    if not isinstance(v, Mapping):
        raise _Recusa("valor_invalido", f"{nome}: informe os campos (objeto).")
    return dict(v)


def _corpo_sw(item: Item, v: Any) -> dict[str, Any]:
    """The body for an SW setting, validated like SW validates it (its own validator stays the authority)."""
    a = item.destino.alvo
    if a == "reengajamento":
        d = _dict(v, "reengajamento")
        out: dict[str, Any] = {}
        if "lembrete_ativo" in d:
            out["minutos_ativo"] = _booleano(d["lembrete_ativo"], "lembrete_ativo")
        if "lembrete_min" in d:
            out["minutos_intervalo"] = _inteiro(d["lembrete_min"], 5, 60, "lembrete_min", 5)
        if "final_ativo" in d:
            out["horas_ativo"] = _booleano(d["final_ativo"], "final_ativo")
        if "final_horas" in d:
            out["horas_intervalo"] = _inteiro(d["final_horas"], 1, 11, "final_horas")
        if not out:
            raise _Recusa("valor_invalido", "reengajamento: informe lembrete e/ou final.")
        return out
    if a == "envio_frios_invalido":
        d = _dict(v, "leads frios")
        out = {}
        frios: dict[str, Any] = {}
        if "frios_ativo" in d:
            frios["ativo"] = _booleano(d["frios_ativo"], "frios_ativo")
        if "frios_min" in d:
            frios["minutos"] = _inteiro(d["frios_min"], 1, 1440, "frios_min")
        if frios:
            out["frios"] = frios
        if "whatsapp_invalido" in d:
            out["whatsapp_invalido"] = _booleano(d["whatsapp_invalido"], "whatsapp_invalido")
        if not out:
            raise _Recusa("valor_invalido", "leads frios: informe frios e/ou whatsapp_invalido.")
        return out
    if a == "envio_captacoes":
        return {"captacoes": _opcao(v, ("enviar", "notificar"), "captacao")}
    if a == "pesquisa":
        return {"pesquisa": _booleano(v, "pesquisa")}
    if a == "politica_endereco":
        return {"endereco_completo": _opcao(v, ("completo", "bairro"), "endereco") == "completo"}
    if a in ("politica_iptu", "mostrar_atendente", "visitas"):
        return {"ativo": _booleano(v, item.titulo)}
    if a == "recesso":
        d = _dict(v, "recesso")
        faltam = [k for k in ("inicio", "fim", "mensagem") if not _texto(d.get(k))]
        if faltam:
            raise _Recusa("valor_invalido", "recesso: falta " + ", ".join(faltam) + ".")
        return {k: _texto(d[k]) for k in ("inicio", "fim", "mensagem")}
    if a == "avaliacao_google":
        u = urlparse(_texto(v))
        if u.scheme != "https" or not u.netloc:
            raise _Recusa("valor_invalido", "link de avaliação: use um endereço https.")
        return {"url": _texto(v)}
    t = _texto(v)
    if not t or len(t) > 400:
        raise _Recusa("valor_invalido", f"{item.titulo}: informe um texto de até 400 caracteres.")
    return {"valor": t}


def _compor_spec(chave: str, itens: list[tuple[Item, Any]], armazenado: str) -> str:
    """The value one spec key takes from this step's answers. A key several items feed (the sale / rental knowledge)
    receives one labelled line per item, appended to what is already stored (a line already there is not repeated)."""
    compartilhada = sum(1 for i in CHECKLIST if i.destino.alvo == chave) > 1
    if not compartilhada:
        return _texto(itens[0][1])
    linhas = [f"{i.titulo}: {_texto(v)}" for i, v in itens]
    novas = [ln for ln in linhas if ln not in armazenado]
    return "\n".join(x for x in (armazenado.strip(), *novas) if x)


def aplicar(
    respostas: Mapping[int, Any], *, org_id: UUID, declaradas: Mapping[str, str], armazenados: Mapping[str, str],
    config: ConfigValidacao, gravar_specs: Callable[[dict[str, str]], None], sw: SwSettingsPort,
    nao_confirmados: frozenset[int] = frozenset(),
) -> Relatorio:
    """Apply ``respostas`` (``{item number: value}``). ``declaradas`` = ``{spec key: type}`` the definition declares;
    ``armazenados`` = the org's stored spec values; ``gravar_specs`` = the write path for the valid spec values.
    ``nao_confirmados`` = imported items nobody confirmed: reported ``pendente_confirmacao``, never written."""
    rel = Relatorio()
    por_n: dict[int, ItemRelatorio] = {}

    def anotar(item: Item, estado: str, codigo: str | None = None, motivo: str | None = None, corpo: dict | None = None) -> None:
        r = ItemRelatorio(item.n, item.titulo, estado, codigo, motivo, f"{item.destino.kind}:{item.destino.alvo}",
                          item.destino.rota, corpo)
        por_n[item.n] = r
        rel.itens.append(r)

    ops_resp = respostas.get(9)
    operacoes = operacoes_de(ops_resp) if ops_resp not in _VAZIO else operacoes_de(armazenados.get("operacoes_atendidas"))
    aplicaveis = {i.n for i in itens_aplicaveis(operacoes or None)}
    specs_por_chave: dict[str, list[tuple[Item, Any]]] = defaultdict(list)
    sw_itens: list[tuple[Item, dict[str, Any]]] = []

    for n in sorted(respostas):
        v = respostas[n]
        item = item_por_numero(n)
        if item is None:
            rel.itens.append(ItemRelatorio(n, "?", RECUSADO, "item_desconhecido", f"O item {n} não existe no checklist."))
            continue
        if v in _VAZIO:
            continue  # unanswered is not a refusal; the progress view lists it
        if n in nao_confirmados:
            anotar(item, PENDENTE_CONFIRMACAO, "nao_confirmado", "Valor importado: confirme com a empresa antes de aplicar.")
            continue
        if n not in aplicaveis:
            anotar(item, RECUSADO, "item_nao_aplicavel", "Este item só vale para quem atende " + " ou ".join(item.quando) + ".")
            continue
        k = item.destino.kind
        if k == "humano":
            anotar(item, PENDENTE_HUMANO, "passo_humano", "Passo feito pela equipe (credencial ou aprovação), não pela entrevista.")
        elif k == "spec":
            if item.destino.alvo not in declaradas:
                anotar(item, RECUSADO, "spec_nao_declarada", f"A definição ainda não declara {item.destino.alvo}.")
            elif item.n == 17 and len([x for x in re.split(r"[,\n;]", _texto(v)) if x.strip()]) > MAX_PERGUNTAS_EXTRAS:
                anotar(item, RECUSADO, "valor_invalido", f"Perguntas extras: no máximo {MAX_PERGUNTAS_EXTRAS}.")
            else:
                specs_por_chave[item.destino.alvo].append((item, v))
        else:
            try:
                sw_itens.append((item, _corpo_sw(item, v)))
            except _Recusa as exc:
                anotar(item, RECUSADO, exc.codigo, exc.motivo)

    candidatos = {c: _compor_spec(c, its, armazenados.get(c, "")) for c, its in specs_por_chave.items()}
    if candidatos:
        res = validar(declaradas, candidatos, armazenados=armazenados, config=config)
        invalidas = res.invalidas
        validos = {c: res.valores[c] for c in candidatos if c not in invalidas}
        for c, its in specs_por_chave.items():
            for item, _ in its:
                if c in invalidas:
                    anotar(item, RECUSADO, invalidas[c][0].codigo, invalidas[c][0].mensagem)
        if validos:
            try:
                gravar_specs(validos)
            except Exception as exc:  # the write path's own typed refusal (HTTP error) -- reported per item, never swallowed
                for c in validos:
                    for item, _ in specs_por_chave[c]:
                        anotar(item, RECUSADO, "gravacao_recusada", str(getattr(exc, "detail", exc))[:300])
            else:
                for c in validos:
                    for item, _ in specs_por_chave[c]:
                        anotar(item, APLICADO)

    for item, corpo in sw_itens:
        r = sw.aplicar(org_id, item.destino.alvo, item.destino.rota, corpo)
        if r.ok:
            anotar(item, APLICADO, corpo=corpo)
        else:
            anotar(item, RECUSADO, r.codigo or "sw_recusou", r.mensagem, corpo)

    rel.itens.sort(key=lambda r: r.n)
    rel.obrigatorios_faltando = progresso(operacoes, {**{n: True for n, r in por_n.items() if r.estado == APLICADO}})["faltando_obrigatorios"]
    return rel


def progresso(operacoes: set[str] | None, respondidos: Mapping[int, Any]) -> dict[str, Any]:
    """Interview progress: per level, how many applicable items are answered; ``faltando_obrigatorios`` = required
    items (and conditional ones that apply) still open -- these gate go-live."""
    itens = itens_aplicaveis(operacoes or None)
    feitos = {i.n for i in itens if respondidos.get(i.n) not in _VAZIO}
    por_nivel = {
        nv: {"total": sum(1 for i in itens if i.nivel == nv), "feitos": sum(1 for i in itens if i.nivel == nv and i.n in feitos)}
        for nv in ("R", "C", "O")
    }
    return {
        "por_nivel": por_nivel,
        "faltando_obrigatorios": [i.n for i in itens if i.nivel in ("R", "C") and i.n not in feitos],
    }
