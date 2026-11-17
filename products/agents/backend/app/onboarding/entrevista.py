"""The onboarding interviewer's state and tool logic (pure of the SDK: ports in, plain dicts out).

The model talks; this module decides. Every answer is checked here (the value validated by the SAME apply step in dry-run;
the client's own words found in the conversation), refused with a reason the model re-asks from, and recorded as one
intent-named event of ``agents.onboarding_eventos``. The per-item state the staff UI polls is a FOLD of those events.

The four handlers (``progresso_onboarding`` / ``registrar_resposta`` / ``importar_configuracao`` / ``revisar_e_aplicar``)
are bound to ONE session (target org + client agent) taken from the conversation by the server -- the model never names an
org, an item it cannot already see, or an id.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from noctusai_lib.primitives.accents import fold_accents

from app.onboarding import aplicar as ap
from app.onboarding.checklist import CHECKLIST, Item, item_por_numero, itens_aplicaveis, ordem_entrevista
from app.onboarding.importar import MAX_ENTRADA, importar
from app.onboarding.sw_settings import FakeSwSettings
from app.stores.onboarding_sessoes import EventoOnboarding, OnboardingStore, SessaoOnboarding
from app.studio.especificacoes_service import ConfigValidacao

__all__ = [
    "ABERTO", "ORIGENS", "PENDENTE", "PROPOSTO", "RECUSADO", "RESPONDIDO", "Entrevista", "Fala", "estado_dos_itens",
]

ABERTO, RESPONDIDO, PENDENTE, PROPOSTO, RECUSADO = "aberto", "respondido", "pendente", "proposto", "recusado"
ORIGENS = ("cliente", "padrao", "importado")
PROXIMO_PASSO = "modo_avaliacao"
MAX_VALOR = 6000
MAX_TRECHO = 600
_VAZIO = (None, "", [], {})


@dataclass(frozen=True)
class Fala:
    """One message the client (the person being interviewed) wrote."""

    texto: str
    quando: datetime


def _n(s: str) -> str:
    return " ".join(fold_accents(s.casefold()).split())


def _json(valor: Any) -> str:
    return json.dumps(valor, sort_keys=True, ensure_ascii=False, default=str)


def estado_dos_itens(eventos: list[EventoOnboarding]) -> dict[int, dict[str, Any]]:
    """Fold the ledger: the latest event about an item decides its state. ``respondido`` carries the confirmed value."""
    out: dict[int, dict[str, Any]] = {}
    for e in eventos:
        if e.item_n is None and e.event_type != "importacao_proposta":
            continue
        if e.event_type == "resposta_registrada":
            out[e.item_n] = {"estado": RESPONDIDO, "valor": e.dados.get("valor"), "origem": e.dados.get("origem")}
        elif e.event_type == "item_marcado_pendente":
            out[e.item_n] = {"estado": PENDENTE, "motivo": e.dados.get("motivo")}
        elif e.event_type == "resposta_recusada":
            if out.get(e.item_n, {}).get("estado") != RESPONDIDO:  # a refused retry never un-confirms a confirmed value
                out[e.item_n] = {"estado": RECUSADO, "codigo": e.dados.get("codigo"), "motivo": e.dados.get("motivo")}
        elif e.event_type == "importacao_proposta":
            for p in e.dados.get("preenchidas", []):
                if out.get(p["n"], {}).get("estado") not in (RESPONDIDO, PENDENTE):
                    out[p["n"]] = {"estado": PROPOSTO, "valor": p["valor"]}
    return out


class Entrevista:
    """One interview. ``falas`` = the client's own messages of the conversation; ``declaradas`` / ``armazenados`` = the
    client definition's declared spec keys (``{key: type}``) and the org's stored values; ``aplicar_fn`` = the one apply
    step bound to this org (raises the route's typed HTTP error on a refusal it cannot report per item)."""

    def __init__(
        self, *, sessao: SessaoOnboarding, store: OnboardingStore, falas: Callable[[], list[Fala]],
        declaradas: Callable[[], Mapping[str, str]], armazenados: Callable[[], Mapping[str, str]], config: ConfigValidacao,
        aplicar_fn: Callable[[Mapping[int, Any]], ap.Relatorio], actor_id: UUID | None = None,
    ) -> None:
        self._s, self._store, self._falas = sessao, store, falas
        self._declaradas, self._armazenados, self._config, self._aplicar = declaradas, armazenados, config, aplicar_fn
        self._actor = actor_id

    # -- helpers ---------------------------------------------------------------------------------------------------
    def _eventos(self) -> list[EventoOnboarding]:
        return self._store.eventos(self._s.id)

    def _registrar(self, tipo: str, item_n: int | None = None, **dados: Any) -> EventoOnboarding:
        return self._store.registrar_evento(self._s.id, tipo, item_n=item_n, dados=dados, actor_id=self._actor, actor_kind="agent")

    def _operacoes(self, estados: Mapping[int, Mapping[str, Any]]) -> set[str]:
        e9 = estados.get(9, {})
        if e9.get("estado") == RESPONDIDO:
            return ap.operacoes_de(e9.get("valor"))
        return ap.operacoes_de(self._armazenados().get("operacoes_atendidas"))

    @staticmethod
    def _erro(erro: str, motivo: str, **extra: Any) -> dict[str, Any]:
        return {"ok": False, "erro": erro, "motivo": motivo, **extra}

    def _trecho_ok(self, trecho: str, depois_de: datetime | None = None) -> bool:
        t = _n(trecho)
        if len(t) < 2:
            return False
        return any(t in _n(f.texto) for f in self._falas() if depois_de is None or f.quando >= depois_de)

    def _validar_valor(self, item: Item, valor: Any, estados: Mapping[int, Mapping[str, Any]]) -> ap.ItemRelatorio | None:
        """The apply step in DRY-RUN (a no-op spec write, a Fake SW): the SAME validation the real apply runs. The
        session's confirmed operations ride along so a conditional item is judged against them."""
        respostas: dict[int, Any] = {item.n: valor}
        if item.n != 9 and estados.get(9, {}).get("estado") == RESPONDIDO:
            respostas[9] = estados[9]["valor"]
        rel = ap.aplicar(
            respostas, org_id=self._s.alvo_org_id, declaradas=self._declaradas(), armazenados=self._armazenados(),
            config=self._config, gravar_specs=lambda _v: None, sw=FakeSwSettings(),
        )
        return next((i for i in rel.itens if i.n == item.n), None)

    def _proximo(self, estados: Mapping[int, Mapping[str, Any]]) -> dict[str, Any] | None:
        ordem = ordem_entrevista(self._operacoes(estados) or None)
        armazenados = self._armazenados()
        for passo in (ABERTO, RECUSADO, PROPOSTO, PENDENTE):  # open first; what was set aside comes back last
            for i in ordem:
                est = estados.get(i.n, {}).get("estado", ABERTO)
                if est == passo:
                    d = i.destino
                    return {
                        "n": i.n, "titulo": i.titulo, "nivel": i.nivel, "pergunta": i.pergunta, "padrao": i.padrao,
                        "estado": est, "destino": d.kind,
                        "ja_preenchido": d.kind == "spec" and bool((armazenados.get(d.alvo) or "").strip()),
                        **({"valor_proposto": estados[i.n]["valor"]} if est == PROPOSTO else {}),
                        **({"ultima_recusa": estados[i.n]["motivo"]} if est == RECUSADO else {}),
                    }
        return None

    def _faltando(self, estados: Mapping[int, Mapping[str, Any]]) -> list[int]:
        ops = self._operacoes(estados)
        return [i.n for i in itens_aplicaveis(ops or None)
                if i.nivel in ("R", "C") and estados.get(i.n, {}).get("estado") != RESPONDIDO]

    # -- tools -----------------------------------------------------------------------------------------------------
    def progresso(self) -> dict[str, Any]:
        """``progresso_onboarding``: what is confirmed / pending / still open, the next item to ask, what is missing."""
        estados = estado_dos_itens(self._eventos())
        ops = self._operacoes(estados)
        ordem = ordem_entrevista(ops or None)
        itens = [{"n": i.n, "titulo": i.titulo, "nivel": i.nivel, "estado": estados.get(i.n, {}).get("estado", ABERTO)}
                 for i in ordem]
        contagem = {e: sum(1 for x in itens if x["estado"] == e) for e in (RESPONDIDO, PENDENTE, PROPOSTO, RECUSADO, ABERTO)}
        return {
            "ok": True, "operacoes": sorted(ops), "operacoes_definidas": 9 in estados or bool(ops),
            "itens": itens, "contagem": contagem, "faltando_obrigatorios": self._faltando(estados),
            "proximo": self._proximo(estados),
        }

    def registrar_resposta(
        self, *, item: Any, situacao: Any, valor: Any = None, trecho: Any = None, origem: Any = "cliente", motivo: Any = None,
    ) -> dict[str, Any]:
        """``registrar_resposta``: ONE item, after the person confirmed it (or asked to leave it for later)."""
        if not isinstance(item, int) or isinstance(item, bool):
            return self._erro("item_invalido", "Informe o número do item (inteiro).")
        it = item_por_numero(item)
        if it is None:
            return self._erro("item_desconhecido", f"O item {item} não existe no checklist.")
        estados = estado_dos_itens(self._eventos())
        if item not in {i.n for i in itens_aplicaveis(self._operacoes(estados) or None)}:
            self._registrar("resposta_recusada", item, codigo="item_nao_aplicavel", motivo="Operação não atendida.")
            return self._erro("item_nao_aplicavel", "Este item só vale para quem atende " + " ou ".join(it.quando) + ".")
        if situacao == "pendente":
            if (m := str(motivo or "").strip()[:200]) not in ("nao_sabe", "depois"):
                return self._erro("motivo_invalido", "Para deixar pendente, motivo é 'nao_sabe' ou 'depois'.")
            self._registrar("item_marcado_pendente", item, motivo=m)
            return {"ok": True, "item": item, "estado": PENDENTE, "proximo": self._proximo(estado_dos_itens(self._eventos()))}
        if situacao != "respondido":
            return self._erro("situacao_invalida", "situacao é 'respondido' ou 'pendente'.")
        if origem not in ORIGENS:
            return self._erro("origem_invalida", f"origem é uma de {', '.join(ORIGENS)}.")
        if valor in _VAZIO or len(_json(valor)) > MAX_VALOR:
            return self._erro("valor_invalido", "Informe o valor que a pessoa confirmou (não vazio).")
        if not isinstance(trecho, str) or len(trecho) > MAX_TRECHO or not self._trecho_ok(trecho):
            return self._erro(
                "trecho_nao_encontrado",
                "Cite, em 'trecho', palavras que a PESSOA escreveu na conversa e que sustentam o valor. Se ela ainda não disse, pergunte.",
            )
        if origem == "padrao" and (it.padrao is None or _n(str(valor)) != _n(it.padrao)):
            return self._erro("padrao_invalido", "Este item não tem esse padrão. Pergunte à pessoa.", padrao=it.padrao)
        if origem == "importado" and estados.get(item, {}).get("estado") != PROPOSTO:
            return self._erro("nao_foi_importado", "Este item não veio de uma importação. Use origem 'cliente'.")
        rel = self._validar_valor(it, valor, estados)
        if rel is not None and rel.estado == ap.RECUSADO:
            self._registrar("resposta_recusada", item, codigo=rel.codigo, motivo=rel.motivo)
            if rel.codigo == "spec_nao_declarada":  # nothing the person can fix: asking again would loop
                return self._erro(
                    "item_indisponivel", "A definição do assistente ainda não declara este item; avise a equipe e siga em frente.",
                    codigo=rel.codigo, reperguntar=False, item=item)
            return self._erro("valor_recusado", rel.motivo or "Valor recusado.", codigo=rel.codigo, reperguntar=True, item=item)
        self._registrar("resposta_registrada", item, valor=valor, origem=origem, trecho=trecho.strip())
        return {"ok": True, "item": item, "estado": RESPONDIDO, "proximo": self._proximo(estado_dos_itens(self._eventos()))}

    def importar_configuracao(self, *, texto: Any) -> dict[str, Any]:
        """``importar_configuracao``: map a pasted export onto items. Nothing is confirmed by it."""
        if not isinstance(texto, str) or not texto.strip():
            return self._erro("texto_vazio", "Cole o texto da configuração.")
        try:
            res = importar(texto)
        except ValueError:
            return self._erro("texto_muito_longo", f"O texto passa de {MAX_ENTRADA} caracteres.")
        propostas = [{"n": r.n, "titulo": item_por_numero(r.n).titulo, "valor": r.valor, "fonte": r.fonte, "confirmado": False}
                     for r in res.preenchidas]
        self._registrar("importacao_proposta", None, preenchidas=[{"n": p["n"], "valor": p["valor"]} for p in propostas],
                        nao_reconhecidas=res.nao_reconhecidas, conflitos=res.conflitos)
        return {
            "ok": True, "propostas": propostas, "nao_reconhecidas": res.nao_reconhecidas, "conflitos": res.conflitos,
            "aviso": "Nada disto está confirmado. Leia cada valor para a pessoa e peça um sim explícito por item; só então "
                     "use registrar_resposta com origem 'importado'.",
        }

    def revisar_e_aplicar(self, *, fase: Any, confirmacao_cliente: Any = None) -> dict[str, Any]:
        """``revisar_e_aplicar``: phase 'resumo' (show what will be written) then 'aplicar' (only after a yes)."""
        estados = estado_dos_itens(self._eventos())
        respostas = {n: e["valor"] for n, e in sorted(estados.items()) if e["estado"] == RESPONDIDO}
        if fase == "resumo":
            if not respostas:
                return self._erro("sem_respostas", "Ainda não há nenhuma resposta confirmada para revisar.")
            digest = hashlib.sha256(_json(respostas).encode()).hexdigest()[:16]
            self._registrar("resumo_apresentado", None, digest=digest, itens=sorted(respostas))
            return {
                "ok": True, "fase": "resumo", "digest": digest,
                "itens": [{"n": n, "titulo": item_por_numero(n).titulo, "valor": v} for n, v in respostas.items()],
                "pendentes": [n for n, e in estados.items() if e["estado"] == PENDENTE],
                "faltando_obrigatorios": self._faltando(estados),
                "proximo": "Mostre este resumo à pessoa e pergunte se pode aplicar. Só depois, fase 'aplicar' citando o sim dela.",
            }
        if fase != "aplicar":
            return self._erro("fase_invalida", "fase é 'resumo' ou 'aplicar'.")
        resumos = [e for e in self._eventos() if e.event_type == "resumo_apresentado"]
        digest = hashlib.sha256(_json(respostas).encode()).hexdigest()[:16]
        if not resumos or resumos[-1].dados.get("digest") != digest:
            return self._erro("resumo_desatualizado", "O resumo não foi apresentado, ou as respostas mudaram depois dele. Refaça a fase 'resumo'.")
        if not isinstance(confirmacao_cliente, str) or not self._trecho_ok(confirmacao_cliente, resumos[-1].occurred_at):
            return self._erro(
                "confirmacao_ausente",
                "Cite em 'confirmacao_cliente' as palavras da pessoa, escritas DEPOIS do resumo, autorizando aplicar.",
            )
        try:
            rel = self._aplicar(respostas)
        except HTTPException as exc:  # the route's typed refusal (grant gone, definition without specs): the model can say it
            d = exc.detail if isinstance(exc.detail, dict) else {}
            return self._erro("aplicacao_recusada", str(d.get("detail") or d.get("message") or "A aplicação foi recusada."),
                              codigo=d.get("code"))
        self._registrar(
            "aplicacao_executada", None, aplicados=rel.aplicados, recusados=rel.recusados, digest=digest,
            itens=[{"n": i.n, "estado": i.estado, "codigo": i.codigo} for i in rel.itens],
        )
        return {
            "ok": True, "fase": "aplicar", "aplicados": rel.aplicados, "recusados": rel.recusados,
            "obrigatorios_faltando": rel.obrigatorios_faltando, "proximo_passo": PROXIMO_PASSO,
            "itens": [{"n": i.n, "titulo": i.titulo, "estado": i.estado, "codigo": i.codigo, "motivo": i.motivo} for i in rel.itens],
        }
