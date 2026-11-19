"""The eval-loop REFINE step, pure part (owner 2026-11-19): what a refine reads, what it may propose, and the validator that refuses
what it must never write. No IO here -- the model call is :mod:`app.studio.eval_loop_refinador`, the orchestration is
:mod:`app.studio.eval_loop_refino_service`, the atomic write is :mod:`app.stores.studio_eval_refino`.

The rule the whole step rests on (KB § PATTERNS/ai/ai-engineering-canon.md §5): **the model's output is data; the server decides.**
The model proposes ONE edit of ONE existing row of the loop's OWN draft (a section's text, a text row, or a tool row's description).
:func:`validar_proposta` accepts it or refuses it with a fixed code; nothing the model says reaches the draft otherwise. Refused on
purpose, whatever the model argues:

* a row that does not exist / is inactive / is not the loop agent's own (the rows come from the raw store, never the layered view,
  so a parent layer -- agente-base, sdr-base -- is not even listed) / a section that declares rules (the canonical must-haves);
* anything but the row's text: no tool permission (``ativo`` / ``parametros`` / a new tool), no title, no new row;
* new text carrying a URL / domain, an e-mail / phone / CPF / CNPJ, a secret-shaped token, a mention of a tool the row did not
  mention, a changed ``{placeholder}`` / ``{{org.x}}`` marker;
* a rewrite that is not bounded (grows by more than :data:`MAX_CRESCIMENTO` characters, shrinks a long row to under 40%, leaves
  the type's size cap) or changes nothing;
* new text that copies a failing case's transcript, lead message or judge note verbatim (data smuggled into the prompt).

Hardening (red-team, owner 2026-11-19), in :mod:`app.studio.eval_loop_refino_protegido` / :mod:`app.studio.eval_loop_refino_checks`: a
PROTECTIVE row (opt-out / security / hand-off / identity-privacy / honesty sections, the platform's required texts, the hand-off / stop /
consent tools) is never a target; REMOVED or REWORDED protective sentences are ``enfraquece_protecao``; ADDED exceptions, triggers,
obey-the-lead and payment patterns are ``instrucao_proibida``; addresses and contacts are read after Unicode normalisation (also in the
rationale); a refine may also answer "no edit" (``sem_edicao``), which is recorded for a person and never forced into an edit.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from pydantic import model_validator

from noctusai_lib.primitives.accents import fold_accents_ascii

from app.studio.eval_loop import EPS, Recusa, Rodada, ordenar
from app.studio.eval_loop_refino_checks import (
    contem_arroba, contem_endereco, enfraquece_protecao, frases_novas, instrucao_proibida,
)
from app.studio.eval_loop_refino_protegido import ferramenta_protegida, linha_e_protegida, secao_protegida, texto_protegido
from app.studio.ferramentas_registry import FERRAMENTAS_CONHECIDAS
from app.studio.models import LIMITS

__all__ = [
    "TIPOS", "MAX_CASOS", "MAX_CRESCIMENTO", "MAX_DIFF_CHARS", "AlvoRefino", "SaidaRefino", "CasoFalhando", "SecaoLinha",
    "LinhasDoAgente", "PropostaRefino", "RefinoRecusado", "validar_proposta", "deve_refinar", "casos_falhando_comportamento",
    "casos_falhando_mecanismo", "linhas_do_rascunho", "detalhe_proposto", "detalhe_recusado", "EVENTOS_REFINO",
    "MENSAGENS_REFINO", "mensagem_refino", "trecho_do_diff", "refinamentos_do_estado", "resumo_de_refinamentos",
    "MAX_REFINOS_POR_LOOP", "DECISOES_REFINO", "refinamentos_sem_revisao", "linha_protegida_de", "detalhe_sem_edicao",
]

TIPOS = ("secao", "texto", "ferramenta")
#: how many failing cases a refine reads (worst-first is the caller's order; the rest is counted in the event)
MAX_CASOS = 8
MAX_TURNOS = 6
MAX_BOLHAS = 6
MAX_TEXTO_CASO = 400
MAX_RACIONAL = 600
#: a refine is ONE bounded edit: it may add at most this many characters and may not gut a long row.
MAX_CRESCIMENTO = 2000
MIN_CONTEUDO = 10
MIN_FRACAO_RESTANTE = 0.4
#: the diff stored in the event keeps both texts up to the type's own size cap (the owner reverts by hand from it)
MAX_DIFF_CHARS = 40_000
#: a case text of at least this many (normalised) characters may not reappear verbatim in the new row text
MIN_COPIA = 50
#: at most this many edits per loop (and one per row): a loop that keeps failing after three edits needs a person, not a fourth guess
MAX_REFINOS_POR_LOOP = 3
#: the refine decisions of a round (exactly one per base round) ...
DECISOES_REFINO = ("refinamento_proposto", "refinamento_recusado", "refinamento_sem_edicao")
#: ... and every refine event (the evaluation of the next round, the human review of an edit)
EVENTOS_REFINO = (*DECISOES_REFINO, "refinamento_avaliado", "refinamento_revisado")

_LIMITE_TIPO = {"secao": LIMITS["section.conteudo"], "texto": LIMITS["texto.conteudo"], "ferramenta": LIMITS["ferramenta.descricao"]}


# ── what the model returns (strict: any extra key is a refusal, never ignored) ────────────────────────────────


class AlvoRefino(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: Literal["secao", "texto", "ferramenta"]
    chave: str = Field(min_length=1, max_length=160)


class SaidaRefino(BaseModel):
    """What the model returns: EITHER the ONE edit it proposes (``alvo`` + ``novo_conteudo`` -- the row's whole new text -- + ``racional`` +
    ``casos_alvo``) OR "no edit" (``sem_edicao: true`` + ``motivo`` + ``casos_suspeitos``): the failing cases look wrong / hostile / not a
    prompt problem, and a person should look. Never forced into an edit; a mix of the two is invalid."""

    model_config = ConfigDict(extra="forbid")

    alvo: AlvoRefino | None = None
    novo_conteudo: str | None = Field(default=None, min_length=1)
    racional: str | None = Field(default=None, min_length=1, max_length=MAX_RACIONAL)
    casos_alvo: list[str] = Field(default_factory=list, max_length=MAX_CASOS)
    sem_edicao: bool = False
    motivo: str | None = Field(default=None, min_length=1, max_length=MAX_RACIONAL)
    casos_suspeitos: list[str] = Field(default_factory=list, max_length=MAX_CASOS)

    @model_validator(mode="after")
    def _uma_coisa_ou_a_outra(self) -> "SaidaRefino":
        if self.sem_edicao:
            if self.alvo is not None or self.novo_conteudo is not None or self.racional is not None or self.casos_alvo:
                raise ValueError("sem_edicao is exclusive of an edit")
            if self.motivo is None:
                raise ValueError("sem_edicao needs a motivo")
        else:
            if self.alvo is None or self.novo_conteudo is None or self.racional is None or not self.casos_alvo:
                raise ValueError("an edit needs alvo, novo_conteudo, racional and casos_alvo")
            if self.motivo is not None or self.casos_suspeitos:
                raise ValueError("motivo / casos_suspeitos belong to sem_edicao")
        return self


class RefinoRecusado(Exception):
    """A proposal the server refuses: a fixed machine ``code`` + a pt-BR line. Never carries row content."""

    def __init__(self, code: str, mensagem: str) -> None:
        super().__init__(code)
        self.code = code
        self.mensagem = mensagem


# ── what the refine reads ─────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CasoFalhando:
    """One failing case of the closed round, trimmed. Everything in it is DATA for the model (a transcript, a lead message, a
    judge note): it may be wrong, hostile or instruction-shaped, and is never treated as an instruction."""

    slug: str
    titulo: str
    suite: str
    #: mechanism suite: ``(assert, codigo)`` of the failed asserts; behaviour suite: ``()``
    falhas: tuple[tuple[str, str], ...] = ()
    notas_juiz: str | None = None
    saida: str | None = None
    esperado: Any = None
    turnos: tuple[dict[str, Any], ...] = ()

    def para_modelo(self) -> dict[str, Any]:
        return {
            "slug": self.slug, "titulo": self.titulo, "suite": self.suite,
            "asserts_falhados": [{"assert": a, "codigo": c} for a, c in self.falhas],
            "notas_do_juiz": self.notas_juiz, "resposta_do_agente": self.saida, "esperado": self.esperado,
            "transcricao": list(self.turnos),
        }

    def textos_livres(self) -> list[str]:
        """Every free text of the case (what the agent said, what the lead said, what the judge wrote)."""
        out: list[str] = []
        if self.notas_juiz:
            out.append(self.notas_juiz)
        if self.saida:
            out.append(self.saida)
        for t in self.turnos:
            for k in ("lead", "retomada"):
                if isinstance(t.get(k), str):
                    out.append(t[k])
            out.extend(b for b in t.get("bolhas") or [] if isinstance(b, str))
        return out


@dataclass(frozen=True)
class SecaoLinha:
    chave: str
    titulo: str
    conteudo: str
    ativo: bool
    regras: tuple[str, ...] = ()


@dataclass(frozen=True)
class LinhasDoAgente:
    """The loop agent's OWN draft rows (the raw store, never the layered/effective view)."""

    version_id: UUID
    compiled_hash: str | None
    secoes: tuple[SecaoLinha, ...] = ()
    textos: tuple[tuple[str, str], ...] = ()
    #: ``(ferramenta, descricao, ativo)``
    ferramentas: tuple[tuple[str, str, bool], ...] = ()

    def sem(self, pares: Iterable[tuple[str, str]]) -> "LinhasDoAgente":
        """The same rows without ``pares`` (``(tipo, chave)``): what the model is shown once a row was already edited in this loop."""
        fora = set(pares)
        return replace(
            self, secoes=tuple(x for x in self.secoes if ("secao", x.chave) not in fora),
            textos=tuple(x for x in self.textos if ("texto", x[0]) not in fora),
            ferramentas=tuple(x for x in self.ferramentas if ("ferramenta", x[0]) not in fora))

    def achar(self, tipo: str, chave: str) -> tuple[str, bool, tuple[str, ...]] | None:
        """``(conteudo, ativo, regras)`` of an own row, or ``None``."""
        if tipo == "secao":
            return next(((s.conteudo, s.ativo, s.regras) for s in self.secoes if s.chave == chave), None)
        if tipo == "texto":
            return next(((c, True, ()) for k, c in self.textos if k == chave), None)
        if tipo == "ferramenta":
            return next(((d, a, ()) for k, d, a in self.ferramentas if k == chave), None)
        return None

    def para_modelo(self) -> dict[str, Any]:
        return {
            "secoes": [{"chave": s.chave, "titulo": s.titulo, "conteudo": s.conteudo, "protegida": secao_protegida(s.chave, s.regras)}
                       for s in self.secoes if s.ativo],
            "textos": [{"chave": k, "conteudo": c, "protegida": texto_protegido(k)} for k, c in self.textos],
            "ferramentas": [{"ferramenta": k, "descricao": d, "protegida": ferramenta_protegida(k)} for k, d, a in self.ferramentas if a],
        }


@dataclass(frozen=True)
class PropostaRefino:
    """An accepted proposal: what the draft row held, what it will hold, and why."""

    tipo: str
    chave: str
    antes: str
    depois: str
    racional: str
    casos_alvo: tuple[str, ...]


# ── the validator ─────────────────────────────────────────────────────────────────────────────────────────────

_SEGREDO = re.compile(
    r"(?i)(?:\bsk-[A-Za-z0-9_-]{16,}|\beyJ[A-Za-z0-9_-]{10,}\.|\bAKIA[0-9A-Z]{12,}|\bbearer\s+[A-Za-z0-9._-]{16,}"
    r"|\b(?:api[_-]?key|secret|token|senha|password)\s*[:=]\s*\S{6,}|\b[A-Fa-f0-9]{32,}\b|\b[A-Za-z0-9+/_-]{40,}\b)")
_MARCADOR = re.compile(r"\{\{[^{}]*\}\}|\{[A-Za-z_][\w.]*\}")
def _norm(s: str) -> str:
    s = fold_accents_ascii(s)
    return re.sub(r"\s+", " ", s).strip().casefold()


def _adicionado(antes: str, depois: str) -> str:
    """The sentences/lines of ``depois`` that ``antes`` did not have: the only text the content checks judge (a row that already
    carried a link keeps it; a NEW one is refused)."""
    return "\n".join(frases_novas(antes, depois))


def linha_protegida_de(linhas: LinhasDoAgente, tipo: str, chave: str) -> bool:
    """Is this row of the agent's draft one the refine never edits (derived: :mod:`app.studio.eval_loop_refino_protegido`)?"""
    achada = linhas.achar(tipo, chave)
    return linha_e_protegida(tipo, chave, achada[2] if achada else ())


def _ferramentas_mencionadas(texto: str) -> set[str]:
    achadas = {m.group(0) for m in re.finditer(r"mcp__[a-z0-9_]+", texto)}
    for nome in FERRAMENTAS_CONHECIDAS:
        # a plain word is not a tool mention ("encerrar", "handoff" in prose): only the machine names (with an underscore) or a
        # backticked name count
        if ("_" in nome and re.search(rf"(?<![\w]){re.escape(nome)}(?![\w])", texto)) or f"`{nome}`" in texto:
            achadas.add(nome)
    return achadas


def validar_proposta(
    saida: SaidaRefino, linhas: LinhasDoAgente, casos: Sequence[CasoFalhando],
    *, ja_refinadas: Mapping[tuple[str, str], str] | None = None,
) -> PropostaRefino:
    """Accept the model's proposal or raise :class:`RefinoRecusado`. See the module docstring for what is refused and why.

    ``ja_refinadas`` is ``{(tipo, chave): the row text at the START of the loop}`` for the rows this loop already edited: such a row is
    refused (one edit per row per loop), and the size / shrink checks always run against the row text at loop start, so no chain of small
    edits can walk a row far from where it began."""
    from app.studio.eval_pii import achar_pii

    if saida.sem_edicao or saida.alvo is None or saida.novo_conteudo is None or saida.racional is None:
        raise RefinoRecusado("saida_invalida", "A resposta do refinador não é uma edição.")
    ja = ja_refinadas or {}
    tipo, chave = saida.alvo.tipo, saida.alvo.chave
    achada = linhas.achar(tipo, chave)
    if achada is None:
        raise RefinoRecusado("linha_inexistente", "A linha proposta não existe no rascunho deste agente.")
    antes, ativo, regras = achada
    if linha_e_protegida(tipo, chave, regras):
        raise RefinoRecusado("linha_protegida", "A linha carrega obrigações da plataforma (opt-out, segurança, transferência, privacidade, "
                                                "honestidade, textos e ferramentas obrigatórios) e não é editada automaticamente.")
    if not ativo:
        raise RefinoRecusado("linha_inativa", "A linha proposta está desativada: editá-la não muda o comportamento.")
    slugs = {c.slug for c in casos}
    alvo = tuple(dict.fromkeys(saida.casos_alvo))
    if not alvo or any(s not in slugs for s in alvo):
        raise RefinoRecusado("casos_alvo_invalidos", "A proposta cita casos que não estavam falhando na rodada.")

    depois = saida.novo_conteudo.strip()
    inicio = ja.get((tipo, chave), antes)  # the row as it was when the loop started: the baseline of the size checks
    if _norm(depois) == _norm(antes):
        raise RefinoRecusado("sem_mudanca", "A proposta não muda o texto da linha.")
    if len(depois) < MIN_CONTEUDO:
        raise RefinoRecusado("conteudo_pequeno", "O novo texto é curto demais para ser uma correção.")
    if len(depois) > _LIMITE_TIPO[tipo]:
        raise RefinoRecusado("conteudo_grande", "O novo texto passa do limite de tamanho da linha.")
    if len(depois) - len(inicio) > MAX_CRESCIMENTO:
        raise RefinoRecusado("crescimento_excedido", f"A edição acrescenta mais de {MAX_CRESCIMENTO} caracteres: não é uma edição pontual.")
    if len(inicio) > 200 and len(depois) < MIN_FRACAO_RESTANTE * len(inicio):
        raise RefinoRecusado("reducao_excedida", "A edição apaga a maior parte da linha: não é uma edição pontual.")
    if (tipo, chave) in ja:  # one edit per row per loop (after the size checks, which already ran against the loop-start text)
        raise RefinoRecusado("linha_ja_refinada", "Esta linha já foi editada neste loop: uma edição por linha em cada loop.")

    if set(_MARCADOR.findall(antes)) != set(_MARCADOR.findall(depois)):
        raise RefinoRecusado("marcadores_alterados", "A edição muda os marcadores {…} da linha (preenchidos em tempo de execução).")
    # what a person reads of a refine is also checked: the rationale shows in the UI and the notifications
    novo = _adicionado(antes, depois)
    for texto in (novo, saida.racional):
        if contem_endereco(texto):
            raise RefinoRecusado("contem_url", "O texto contém endereço (URL, domínio ou IP), mesmo disfarçado.")
        if contem_arroba(texto) or achar_pii(texto):
            raise RefinoRecusado("contem_contato", "O texto contém dado pessoal ou de contato (e-mail, telefone, documento, @perfil).")
    if _SEGREDO.search(novo):
        raise RefinoRecusado("contem_segredo", "O texto novo contém algo com formato de segredo ou credencial.")
    if enfraquece_protecao(antes, depois):
        raise RefinoRecusado("enfraquece_protecao", "A edição remove ou reescreve uma frase que protege o lead ou a plataforma "
                                                    "(nunca / sempre / sair / humano / privacidade / dados ...).")
    if instrucao_proibida(novo):
        raise RefinoRecusado("instrucao_proibida", "O texto novo traz exceção, gatilho, obediência ao lead ou assunto de pagamento.")
    if _ferramentas_mencionadas(novo) - _ferramentas_mencionadas(antes):
        raise RefinoRecusado("menciona_ferramenta", "O texto novo cita ferramenta que a linha não citava: permissão de ferramenta não se edita aqui.")
    depois_n = _norm(depois)
    for c in casos:
        for t in c.textos_livres():
            tn = _norm(t)
            if len(tn) >= MIN_COPIA and tn in depois_n and tn not in _norm(antes):
                raise RefinoRecusado("copia_dados_do_caso", "O texto novo copia uma fala de um caso de teste.")
    return PropostaRefino(tipo=tipo, chave=chave, antes=antes, depois=depois, racional=saida.racional.strip(), casos_alvo=alvo)


# ── when a refine runs ────────────────────────────────────────────────────────────────────────────────────────


def deve_refinar(
    *, status: str, modo: str, alvo: float, rodadas: Sequence[Rodada], eventos: Sequence[dict[str, Any]],
) -> Rodada | None:
    """The round a refine should be based on, or ``None``. A refine runs for an ACTIVE AUTOMATIC loop with no round open whose last
    closed round was measured, scored below the target, still has failing cases, and has no refine decision yet (idempotent across a
    restart and across two drivers: one decision per base round, also a DB unique index)."""
    if status != "ativo" or modo != "automatico":
        return None
    rs = ordenar(rodadas)
    if not rs or any(r.aberta for r in rs):
        return None
    ultima = rs[-1]
    if ultima.status not in ("concluida", "parcial_com_erros") or ultima.score is None or not ultima.falhas:
        return None
    if ultima.score >= alvo - EPS:
        return None
    if any(e.get("evento") in DECISOES_REFINO and e.get("rodada_seq") == ultima.seq for e in eventos):
        return None
    return ultima


# ── reading the failures of a closed round ────────────────────────────────────────────────────────────────────


def _cortar(v: Any, n: int = MAX_TEXTO_CASO) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[:n] + "…"


def _aparar_turnos(transcricao: Sequence[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    out: list[dict[str, Any]] = []
    for t in list(transcricao)[-MAX_TURNOS:]:
        turno: dict[str, Any] = {}
        for k in ("lead", "retomada"):
            if t.get(k) is not None:
                turno[k] = _cortar(t[k])
        turno["bolhas"] = [_cortar(b) for b in (t.get("bolhas") or [])[:MAX_BOLHAS]]
        turno["ferramentas"] = [{"nome": f.get("nome"), "ok": f.get("ok")} for f in (t.get("ferramentas") or []) if isinstance(f, dict)]
        out.append(turno)
    return tuple(out)


def casos_falhando_comportamento(evals: Any, org_id: UUID, agent_id: UUID, run_id: UUID) -> list[CasoFalhando]:
    """The behaviour run's failed cases (``reprovado``; an errored case measured nothing), sorted by slug."""
    por_slug = {c.slug: c for c in evals.list_cases(org_id, agent_id)}
    out = []
    for r in evals.list_results_with_cases(org_id, agent_id, run_id):
        if r.result.status != "reprovado":
            continue
        caso = por_slug.get(r.case_slug)
        out.append(CasoFalhando(
            slug=r.case_slug, titulo=r.case_titulo, suite="comportamento", notas_juiz=_cortar(r.result.notas_juiz, 600) if r.result.notas_juiz else None,
            saida=_cortar(r.result.saida, 800) if r.result.saida else None,
            esperado={"entrada": _cortar(caso.entrada), "criterios": caso.criterios} if caso is not None else None))
    return sorted(out, key=lambda c: c.slug)


def casos_falhando_mecanismo(mecanismo: Any, org_id: UUID, agent_id: UUID, run_id: UUID) -> list[CasoFalhando]:
    """The mechanism run's failed cases: the failed asserts (code only) and the trimmed transcript of the first failing execution."""
    casos = {str(c.id): c for c in mecanismo.list_active_cases(org_id, agent_id)}
    execs: dict[str, list[dict[str, Any]]] = {}
    for e in mecanismo.list_execucoes(org_id, run_id):
        execs.setdefault(str(e["case_id"]), []).append(e)
    out = []
    for cid, es in execs.items():
        ruins = [e for e in es if e["status"] not in ("aprovado", "pulado")]
        caso = casos.get(cid)
        if not ruins or caso is None:
            continue
        falhas = tuple(dict.fromkeys((str(f.get("assert")), str(f.get("codigo"))) for e in ruins for f in e.get("falhas") or []))
        out.append(CasoFalhando(
            slug=caso.slug, titulo=caso.slug, suite="mecanismo", falhas=falhas, esperado=_cortar(caso.asserts, 1500),
            turnos=_aparar_turnos(ruins[0].get("transcricao") or [])))
    return sorted(out, key=lambda c: c.slug)


def linhas_do_rascunho(defs: Any, org_id: UUID, version_id: UUID, compiled_hash: str | None) -> LinhasDoAgente:
    """The OWN rows of a draft, read through the raw store (the same listings the Studio editors read)."""
    return LinhasDoAgente(
        version_id=version_id, compiled_hash=compiled_hash,
        secoes=tuple(SecaoLinha(s.chave, s.titulo, s.conteudo, s.ativo, tuple(s.regras)) for s in defs.list_sections(org_id, version_id)),
        textos=tuple((t.chave, t.conteudo) for t in defs.list_textos(org_id, version_id)),
        ferramentas=tuple((f.ferramenta, f.descricao, bool(f.ativo)) for f in defs.list_ferramentas(org_id, version_id)))


# ── the event shapes (contract: products/agents/docs/eval-loop-gate-contract.md § Refine step) ────────────────


def detalhe_proposto(p: PropostaRefino, *, suite: str, score_base: float | None, hash_base: str, custo_usd: float,
                     modelo: str | None, n_casos_falhando: int, version_id: UUID | None = None) -> dict[str, Any]:
    return {
        "suite": suite, "version_id": None if version_id is None else str(version_id), "alvo": {"tipo": p.tipo, "chave": p.chave}, "racional": p.racional, "casos_alvo": list(p.casos_alvo),
        "diff": {"antes": p.antes[:MAX_DIFF_CHARS], "depois": p.depois[:MAX_DIFF_CHARS]},
        "score_base": score_base, "hash_base": hash_base, "custo_usd": round(custo_usd, 4), "modelo": modelo,
        "casos_falhando": n_casos_falhando,
    }


def detalhe_recusado(codigo: str, mensagem: str, *, suite: str, score_base: float | None, hash_base: str, custo_usd: float,
                     modelo: str | None = None, n_casos_falhando: int = 0) -> dict[str, Any]:
    return {
        "suite": suite, "codigo": codigo, "mensagem": mensagem, "score_base": score_base, "hash_base": hash_base,
        "custo_usd": round(custo_usd, 4), "modelo": modelo, "casos_falhando": n_casos_falhando,
    }


def detalhe_sem_edicao(motivo: str, casos_suspeitos: Sequence[str], *, suite: str, score_base: float | None, hash_base: str,
                       custo_usd: float, modelo: str | None, n_casos_falhando: int) -> dict[str, Any]:
    return {
        "suite": suite, "motivo": motivo, "casos_suspeitos": list(casos_suspeitos), "score_base": score_base, "hash_base": hash_base,
        "custo_usd": round(custo_usd, 4), "modelo": modelo, "casos_falhando": n_casos_falhando,
    }


# ── what a person reads ───────────────────────────────────────────────────────────────────────────────────────

#: pt-BR line per refusal code (the ``codigo`` of ``refinamento_recusado``). The validator's own codes carry their line on
#: :class:`RefinoRecusado`; these are the step's: the model call, the draft and the budget.
MENSAGENS_REFINO: dict[str, str] = {
    "refinador_indisponivel": "O refinador não está configurado: falta a linha ativa do registro de IA da plataforma (agents.eval_loop.refinar).",
    "modelo_sem_preco": "O modelo do refinador não tem preço no catálogo; sem preço não há teto de custo, então a chamada não foi feita.",
    "limite_de_custo": "A chamada do refinador não cabe no orçamento que o loop ainda tem; nada foi gasto.",
    "llm_erro": "A chamada ao modelo do refinador falhou; nada foi gravado.",
    "saida_invalida": "A resposta do refinador não seguiu o formato exigido; nada foi gravado.",
    "refinador_falhou": "O refinador falhou antes de responder; nada foi gravado.",
    "agente_sem_linhas": "O conteúdo deste agente não é editável por linhas (texto do compilador no código ou definição da plataforma).",
    "sem_rascunho": "O agente não tem rascunho para refinar.",
    "rascunho_alterado": "O conteúdo do agente mudou desde a última rodada (alguém já editou); o refinamento foi dispensado.",
    "sem_casos": "Não foi possível ler os casos que falharam na rodada.",
    "pii_nos_casos": "Os casos da rodada trazem dado pessoal; não foram enviados ao modelo (fixtures são sintéticas).",
    "orcamento_insuficiente": "O orçamento que sobra ao loop é pequeno demais para refinar.",
    "camada_base": "Este agente é uma camada base (definição da plataforma ou modelo de outros agentes): uma edição automática o mudaria "
                   "para todos os que herdam dele. O refinamento automático não roda aqui.",
    "limite_de_refinos": f"O loop já fez {MAX_REFINOS_POR_LOOP} edições automáticas: o limite por loop foi atingido; as próximas são com uma pessoa.",
    "linha_ja_refinada": "Esta linha já foi editada neste loop: uma edição por linha em cada loop.",
    "versao_de_outro_agente": "O rascunho a editar não pertence ao agente do loop; nada foi gravado.",
    "linha_protegida": "A linha carrega obrigações da plataforma e não é editada automaticamente.",
    "conflito_de_versao": "O rascunho mudou enquanto o refinamento era proposto; nada foi gravado.",
    "linha_alterada": "A linha do rascunho mudou enquanto o refinamento era proposto; nada foi gravado.",
    "loop_encerrado": "O loop foi encerrado enquanto o refinamento era proposto; nada foi gravado.",
}


def mensagem_refino(codigo: str) -> str:
    return MENSAGENS_REFINO.get(codigo, "O refinamento não foi aplicado.")


def trecho_do_diff(antes: str, depois: str, *, contexto: int = 160) -> tuple[str, str]:
    """The window of ``antes`` / ``depois`` around the changed region (common prefix and suffix cut away), for the loop state the UI
    polls. The full texts stay in the event (``GET .../eventos``)."""
    p = 0
    while p < min(len(antes), len(depois)) and antes[p] == depois[p]:
        p += 1
    s = 0
    while s < min(len(antes), len(depois)) - p and antes[len(antes) - 1 - s] == depois[len(depois) - 1 - s]:
        s += 1
    ini = max(0, p - contexto)

    def janela(t: str) -> str:
        fim = min(len(t), len(t) - s + contexto)
        return ("…" if ini > 0 else "") + t[ini:fim] + ("…" if fim < len(t) else "")

    return janela(antes), janela(depois)


def refinamentos_do_estado(eventos: Sequence[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """``{base round seq: refinement}`` for the loop state: each refine decision with its evaluation and its human review attached.
    Pure over the loop's refine events."""
    avaliados = {e["rodada_seq"] - 1: e.get("detalhe") or {} for e in eventos
                 if e.get("evento") == "refinamento_avaliado" and e.get("rodada_seq") is not None}
    revisados = {e["rodada_seq"]: e.get("detalhe") or {} for e in eventos
                 if e.get("evento") == "refinamento_revisado" and e.get("rodada_seq") is not None}
    out: dict[int, dict[str, Any]] = {}
    for e in eventos:
        if e.get("evento") not in DECISOES_REFINO or e.get("rodada_seq") is None:
            continue
        d = e.get("detalhe") or {}
        seq = e["rodada_seq"]
        estado = {"refinamento_proposto": "proposto", "refinamento_recusado": "recusado", "refinamento_sem_edicao": "sem_edicao"}[e["evento"]]
        rev = revisados.get(seq) if estado == "proposto" else None
        item: dict[str, Any] = {
            "estado": estado, "custo_usd": float(d.get("custo_usd") or 0.0),
            "modelo": d.get("modelo"), "codigo": d.get("codigo"), "mensagem": d.get("mensagem"), "alvo": d.get("alvo"),
            "racional": d.get("racional"), "casos_alvo": list(d.get("casos_alvo") or []), "diff": None,
            "avaliado": False, "melhorou": None, "score_antes": d.get("score_base"), "score_depois": None,
            "motivo": d.get("motivo"), "casos_suspeitos": list(d.get("casos_suspeitos") or []),
            #: an edit waits for a person until a ``refinamento_revisado`` exists: ``aceito`` | ``revertido``
            "revisao": None if rev is None else rev.get("decisao"), "pendente_revisao": estado == "proposto" and rev is None}
        if isinstance(d.get("diff"), dict):
            a, b = trecho_do_diff(str(d["diff"].get("antes") or ""), str(d["diff"].get("depois") or ""))
            item["diff"] = {"antes": a, "depois": b}
        av = avaliados.get(seq)
        if av is not None:
            item.update(avaliado=True, melhorou=av.get("melhorou"), score_depois=av.get("score_depois"))
        out[seq] = item
    return out


def resumo_de_refinamentos(refinos: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Loop-level totals of the refine step (state + notifications): decisions, evaluated ones that raised the score, and the spend."""
    itens = list(refinos.values())
    return {
        "propostos": sum(1 for r in itens if r["estado"] == "proposto"),
        "recusados": sum(1 for r in itens if r["estado"] == "recusado"),
        "sem_edicao": sum(1 for r in itens if r["estado"] == "sem_edicao"),
        "avaliados": sum(1 for r in itens if r["estado"] == "proposto" and r["avaliado"]),
        "melhoraram": sum(1 for r in itens if r["estado"] == "proposto" and r["melhorou"] is True),
        "pendentes_revisao": sum(1 for r in itens if r["pendente_revisao"]),
        "custo_usd": round(sum(r["custo_usd"] for r in itens), 4),
    }


def refinamentos_sem_revisao(eventos: Sequence[dict[str, Any]], *, version_id: UUID | None = None) -> list[dict[str, Any]]:
    """The edits the refine step wrote into the draft that no person reviewed yet: every ``refinamento_proposto`` (of ``version_id``,
    when given -- an event without a version counts for any draft) with no ``refinamento_revisado`` for the same ``(loop, round)``.
    The publish gate and the readiness item read this. Pure over the events of ONE agent; ``[{loop_id, rodada, alvo}]``, oldest first."""
    revisados = {(str(e.get("loop_id")), e.get("rodada_seq")) for e in eventos if e.get("evento") == "refinamento_revisado"}
    out = []
    for e in eventos:
        if e.get("evento") != "refinamento_proposto":
            continue
        d = e.get("detalhe") or {}
        if version_id is not None and d.get("version_id") not in (None, str(version_id)):
            continue
        if (str(e.get("loop_id")), e.get("rodada_seq")) in revisados:
            continue
        out.append({"loop_id": str(e.get("loop_id")), "rodada": e.get("rodada_seq"), "alvo": d.get("alvo")})
    return out
