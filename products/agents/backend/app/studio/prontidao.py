"""Readiness of an agent DRAFT to publish: everything the author still owes, in one list (the complete-agent recipe,
``KB § GUIDES/agent-creation.md``).

Two halves, kept apart on purpose:

* :func:`compor` is PURE -- it turns a snapshot (:class:`Entrada`) into the items and the verdict. No IO, no clock.
* :func:`coletar` does the reads (stores, gate, compiler) and builds that snapshot.

``pronto_para_publicar`` is true IFF ``POST .../draft/publish`` would not refuse the draft (ignoring the two things a
readiness view cannot know: a concurrent edit between the read and the click, and a human's explicit override of the
judge suite). It is not a parallel opinion of the gate: the publish route and this module call the SAME predicates
(:func:`recusa_de_compilacao`, :func:`juiz_motivo`, ``decidir_portao``), and every BLOCKING item names the publish
refusal code it stands for (``recusa_publicacao``; :data:`RECUSAS_PUBLICACAO` is the closed set -- a test publishes a
draft in each state and checks the refusal is the one the item names). A blocking item with no refusal behind it, or a
refusal with no item, is a gate<->methodology drift the suite fails on.

Every other item is ADVISORY: it tells the author what a complete agent has and this draft does not (stale skill pins,
a tool without a description row, parameter labels missing, org specs unfilled, generator gaps, controls off).

Texts are pt-BR, fixed, and never carry row content beyond keys (the readiness view is platform-admin only, but it is
also embedded in publish 409 bodies, which a content token reads).
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping
from uuid import UUID

from app.stores.errors import NotFound
from app.stores.studio_geracoes import ACTIVE_STATUSES
from app.studio.compiler import CONTEUDO_CODIGOS
from app.studio.eval_mecanismo import MecanismoRequisito, PortaoMecanismo, decidir_portao
from app.studio.especificacoes_service import config_atual, violacoes_armazenadas
from app.studio.models import CompiledPrompt, ConfigValidacao, GateRun
from app.studio.camada_validada import VeredictoCamada, base_nao_validada, coletar_camadas_base
from app.studio.camadas import efetivo
from app.studio.regras_secao import REGRA_DISCORDAR

logger = logging.getLogger(__name__)

#: The canonical agent template's must-haves (owner 2026-11-08, ``KB § PATTERNS/backend/canonical-agent-template.md``):
#: a section RULE (not a key: the rule lives inside ``honestidade``) that tells the agent to disagree respectfully, and behaviour eval cases that try to make it flatter.
TAG_BAJULACAO = "bajulacao"

#: The closed set of item groups. The frontend's ``ProntidaoGrupo`` / ``PRONTIDAO_GRUPO_LABEL``
#: (``frontend/src/api/studio/types-prontidao.ts``) names the same set; a test keeps the two equal, and
#: :func:`compor` refuses an item outside it (a group the panel cannot label is a heading nobody can read).
GRUPOS = (
    "compilador", "conteudo", "padrao", "avaliacao", "skills", "ferramentas", "especificacoes", "seguranca",
    "geracao", "operacao", "modelo",
)

__all__ = [
    "Entrada",
    "GRUPOS",
    "Item",
    "Prontidao",
    "REGRA_DISCORDAR",
    "RECUSAS_PUBLICACAO",
    "TAG_BAJULACAO",
    "coletar",
    "canonico_exigido",
    "compor",
    "falta_numero_fallback",
    "ferramentas_esperadas",
    "juiz_aprovado",
    "juiz_motivo",
    "recusa_de_compilacao",
    "rotulos_ausentes",
]

Severidade = Literal["bloqueante", "aviso", "ok"]

#: The publish refusals (409 ``code``) a BLOCKING readiness item may stand for. Closed: ``compor`` raises on any other.
RECUSAS_PUBLICACAO = frozenset({
    "conteudo_incompleto", "compile_blocked", "mecanismo_reprovado", "eval_required", "qualificacao_indisponivel",
    "numero_fallback_ausente", "catalogo_ausente", "base_nao_validada",
})


# ── the gate's predicates (shared with ``publish_draft``) ───────────────────


def recusa_de_compilacao(compiled: CompiledPrompt) -> str | None:
    """The publish refusal code a compiled prompt earns: ``conteudo_incompleto`` when a blocking warning is a missing
    content row, ``compile_blocked`` for any other blocking warning, ``None`` when nothing blocks."""
    if not compiled.bloqueado:
        return None
    return "conteudo_incompleto" if any(w.bloqueante and w.codigo in CONTEUDO_CODIGOS for w in compiled.avisos) else "compile_blocked"


def juiz_aprovado(run: GateRun | None, compiled_hash: str, limiar: float) -> bool:
    """The judge-suite predicate of the publish gate: a concluded, COMPLETE run over >= 1 case, of exactly this
    prompt, scoring at or above the agent's threshold."""
    return (
        run is not None
        and run.status == "concluida"
        and run.completa
        and run.total >= 1
        and run.compiled_hash == compiled_hash
        and run.score is not None
        and run.score >= limiar
    )


def juiz_motivo(run: GateRun | None, compiled_hash: str, limiar: float) -> str:
    """Why the judge suite does (``ok``) or does not open the gate: ``sem_execucao`` | ``hash_diferente`` |
    ``incompleta`` | ``abaixo_do_limiar`` | ``ok``. Consistent with :func:`juiz_aprovado` by construction."""
    if run is None:
        return "sem_execucao"
    if run.compiled_hash != compiled_hash:
        return "hash_diferente"
    if run.status != "concluida" or not run.completa or run.total < 1:
        return "incompleta"
    if not juiz_aprovado(run, compiled_hash, limiar):
        return "abaixo_do_limiar"
    return "ok"


# ── the snapshot ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PinSkill:
    skill: str
    versao: int
    nova_versao: int | None


@dataclass(frozen=True)
class FerramentaLinha:
    ferramenta: str
    ativo: bool
    descricao: str
    parametros: Mapping[str, Any]


@dataclass(frozen=True)
class AreaGeracao:
    area: str
    status: str
    erro: str | None
    lacunas: tuple[str, ...]


@dataclass(frozen=True)
class Entrada:
    """Everything :func:`compor` needs; built by :func:`coletar` (or by a test)."""

    agent_key: str
    version_id: UUID
    compiled: CompiledPrompt
    limiar: float
    usa_canais: bool
    #: ``conteudo_status``: ``{textos_preenchidos, textos_total, obrigatorios_faltando}`` (``None`` = legacy agent).
    conteudo: Mapping[str, Any] | None = None
    # standard
    padrao_chave: str | None = None
    padrao_fixado: bool = False
    padrao_publicado: bool = False
    padrao_atualizacao: bool = False
    # evals
    casos_comportamento: int = 0
    casos_mecanismo: int = 0
    juiz: GateRun | None = None
    mecanismo: MecanismoRequisito = field(default_factory=MecanismoRequisito)
    # skills / tools
    pins: tuple[PinSkill, ...] = ()
    ferramentas: tuple[FerramentaLinha, ...] = ()
    ferramentas_esperadas: Mapping[str, str] = field(default_factory=dict)
    #: ``{ferramenta: (param paths without a label)}`` for the active, described tools of the channel registry.
    rotulos_ausentes: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    # org specs / generation / controls
    specs_org_faltando: tuple[str, ...] = ()
    #: ``((chave, codigo, motivo, mensagem), ...)`` -- stored org-spec values that fail the typed/safety rules (E2).
    specs_org_invalidas: tuple[tuple[str, str, str, str], ...] = ()
    #: ``SPEC_VALIDATION_MODE == 'block'``: an invalid stored value is a ``bloqueante``; ``report``: an ``aviso``.
    spec_bloqueia: bool = False
    #: The pattern rules (``padroes_proibidos`` / ``alegacao_identidade``) with no STORED row on THIS
    #: instance: the code-side floor protects the runtime, but the instance's data is incomplete (blocking).
    regras_seguranca_sem_parametros: tuple[str, ...] = ()
    geracao_status: str | None = None
    geracao_areas: tuple[AreaGeracao, ...] = ()
    controle_modo: str | None = None
    #: The canonical template applies (every conversational agent; ``False`` for the internal generator, which only
    #: emits JSON, and for snapshots built by older callers).
    canonico_exigido: bool = False
    #: Rules declared by the agent's ACTIVE, non-blank EFFECTIVE sections (``app.studio.regras_secao``), and the tags of
    #: its ACTIVE behaviour cases.
    regras_secoes: tuple[str, ...] = ()
    tags_comportamento: tuple[str, ...] = ()
    #: 074: the hand-off fallback number is set (one for every org for now). ``True`` for snapshots built by older
    #: callers; :func:`coletar` always reads it.
    numero_fallback_definido: bool = True
    #: ``parametros.catalogo`` of the qualification standard the draft runs on (``None`` = names none, or no standard).
    padrao_catalogo: str | None = None
    #: 073 chain gate: the verdict of every ANCESTOR layer, root first (``()`` = no parent). A child relies on its bases
    #: being validated (``app.studio.camada_validada``) and runs only the cases of its own scope.
    camadas_base: tuple[VeredictoCamada, ...] = ()


@dataclass(frozen=True)
class Item:
    codigo: str
    grupo: str
    severidade: Severidade
    mensagem: str
    acao_sugerida: str | None = None
    #: For a BLOCKING item: the 409 ``code`` publish answers with. ``None`` for advisory/ok items.
    recusa_publicacao: str | None = None
    detalhe: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "codigo": self.codigo, "grupo": self.grupo, "severidade": self.severidade, "mensagem": self.mensagem,
            "acao_sugerida": self.acao_sugerida, "recusa_publicacao": self.recusa_publicacao, "detalhe": self.detalhe,
        }


@dataclass(frozen=True)
class Prontidao:
    agent_key: str
    version_id: UUID
    hash: str
    itens: tuple[Item, ...]

    @property
    def bloqueantes(self) -> int:
        return sum(1 for i in self.itens if i.severidade == "bloqueante")

    @property
    def avisos(self) -> int:
        return sum(1 for i in self.itens if i.severidade == "aviso")

    @property
    def pronto_para_publicar(self) -> bool:
        return self.bloqueantes == 0


# ── tools ───────────────────────────────────────────────────────────────────

_FERRAMENTAS_CONHECIMENTO = ("kb_buscar", "kb_ler")


#: Qualification tools that only make sense for a real-estate agent (they read/record a property offered to the lead).
FERRAMENTAS_IMOBILIARIAS = frozenset({"registrar_reacao_imovel"})
#: Tools whose row marks an agent as real-estate (it offers / details properties): the catalog the reaction tool refers to.
_SINAIS_IMOBILIARIOS = frozenset({"oferecer_imoveis", "detalhes_imovel", "consultar_empreendimento"})
#: Tools a standard supports only when it has a ``conclusivo`` stage (the code gate ``estagio_nao_conclusivo``).
FERRAMENTAS_DE_CONCLUSAO = frozenset({"concluir_qualificacao"})


def agente_imobiliario(ferramentas: Iterable[str]) -> bool:
    """Real-estate agent = it has a content row for a property tool (offer / details / enterprise)."""
    return bool(_SINAIS_IMOBILIARIOS & set(ferramentas))


def ferramentas_esperadas(
    *, usa_canais: bool, tem_skills: bool, tool_policy: Mapping[str, Any], com_padrao: bool,
    padrao_conclusivo: bool = True, imobiliario: bool = True,
) -> dict[str, str]:
    """``{tool: why}`` -- the tools this draft's configuration says it works with, DERIVED from the channel registry
    (``app.channels.tool_registry.TOOLS``: a tool's ``exige`` are the capabilities it needs) and the tool policy:
    skills present -> the skill tools; a qualification standard -> the qualification tools; a channel agent -> the
    capability-free tools (handoff, stop, data-subject request...); ``knowledge`` on -> ``kb_buscar``/``kb_ler``.

    A standard does not imply every qualification tool (the SDR template is not Julia): ``concluir_qualificacao`` is
    expected only when the standard has a ``conclusivo`` stage (``padrao_conclusivo``), and the real-estate reaction tool
    only for a real-estate agent (``imobiliario``). Both default to ``True`` -- the pre-existing (Julia) expectation --
    so a caller that cannot tell keeps the stricter set instead of hiding a missing description."""
    from app.channels.tool_registry import TOOLS

    capacidades: set[str] = set()
    if tem_skills:
        capacidades.add("skills")
    if com_padrao:
        capacidades.add("qualificacao")
    out: dict[str, str] = {}
    for nome, d in TOOLS.items():
        if nome in FERRAMENTAS_DE_CONCLUSAO and not padrao_conclusivo:
            continue
        if nome in FERRAMENTAS_IMOBILIARIAS and not imobiliario:
            continue
        if d.exige and d.exige <= capacidades:
            out[nome] = "skills fixadas" if d.exige == {"skills"} else "padrão de qualificação"
        elif not d.exige and usa_canais:
            out[nome] = "agente de canal"
    if bool(tool_policy.get("knowledge", False)):
        for nome in _FERRAMENTAS_CONHECIMENTO:
            out[nome] = "base de conhecimento ativada"
    return out


def _folhas(node: Any, caminho: str = "") -> list[str]:
    """The labelled property paths of a (inlined) tool JSON schema: ``a``, and ``a.b`` for ``b`` inside ``a``'s items --
    the same keys ``tool_registry.enriquecer_schema`` reads the row's ``parametros`` by."""
    out: list[str] = []
    if not isinstance(node, dict):
        return out
    for nome, sub in (node.get("properties") or {}).items():
        cam = f"{caminho}.{nome}" if caminho else nome
        out.append(cam)
        alvo = sub.get("items") if isinstance(sub, dict) and sub.get("type") == "array" and isinstance(sub.get("items"), dict) else sub
        out += _folhas(alvo, cam)
    return out


def rotulos_ausentes(ferramentas: tuple[FerramentaLinha, ...] | list[FerramentaLinha]) -> dict[str, tuple[str, ...]]:
    """For each ACTIVE, described tool of the channel registry: the parameter paths of its schema that have no label in the
    row's ``parametros``. Tools outside the registry (knowledge, tool groups) have no code schema here -> not judged."""
    from app.channels.tool_registry import TOOLS, schema_de

    out: dict[str, tuple[str, ...]] = {}
    for f in ferramentas:
        if f.ferramenta not in TOOLS or not f.ativo or not f.descricao.strip():
            continue
        faltam = tuple(
            p for p in _folhas(schema_de(f.ferramenta))
            if not (isinstance(f.parametros.get(p), str) and f.parametros[p].strip())
        )
        if faltam:
            out[f.ferramenta] = faltam
    return out


# ── the pure composer ───────────────────────────────────────────────────────

_COMPILE_ACAO = {
    "texto_ausente": "Preencha o texto ou a descrição que falta (abas Textos e Ferramentas).",
    "placeholder_desconhecido": "Troque o placeholder por um permitido para aquela chave (o registro de textos lista os permitidos).",
    "ferramenta_desconhecida": "Use um nome do registro de ferramentas do código, ou remova a linha.",
    "skill_exigida_inexistente": "Fixe a skill exigida na biblioteca ou remova a exigência da ferramenta.",
    "decisao_sem_opcao_padrao": "Deixe exatamente uma opção marcada como padrão, com valores únicos.",
    "decisao_em_secao": "Mova a decisão para Decisões (regra e opções tipadas).",
    "spec_nao_declarada": "Declare a especificação na aba Especificações.",
    "spec_org_faltando": "A organização precisa preencher as especificações obrigatórias.",
    "spec_org_invalida": "Corrija o valor da especificação (aba Especificações): texto livre descreve a organização, não dá instruções.",
    "secao_vazia": "Escreva o conteúdo da seção ou desative-a.",
    "sem_secoes": "Crie ao menos uma seção ativa na aba Prompt.",
}


def _compilador(e: Entrada) -> list[Item]:
    itens: list[Item] = []
    for w in e.compiled.avisos:
        if w.bloqueante:
            recusa = "conteudo_incompleto" if w.codigo in CONTEUDO_CODIGOS else "compile_blocked"
            itens.append(Item(
                w.codigo, "compilador", "bloqueante", w.mensagem,
                _COMPILE_ACAO.get(w.codigo, "Corrija o conteúdo apontado e compile de novo."), recusa,
            ))
        else:
            itens.append(Item(w.codigo, "compilador", "aviso", w.mensagem, "Revise; não impede a publicação."))
    if not e.compiled.avisos:
        itens.append(Item("compilador_ok", "compilador", "ok", "O prompt compila sem avisos."))
    c = e.conteudo
    if c is not None and not c.get("obrigatorios_faltando"):
        itens.append(Item(
            "textos_obrigatorios_ok", "conteudo", "ok",
            f"Textos do sistema: {c['textos_preenchidos']} de {c['textos_total']} preenchidos; nenhum obrigatório falta.",
            detalhe={"textos_preenchidos": c["textos_preenchidos"], "textos_total": c["textos_total"]},
        ))
    return itens


def _padrao(e: Entrada) -> list[Item]:
    if e.padrao_chave is None:
        return []
    if not e.padrao_fixado and not e.padrao_publicado:
        return [Item(
            "qualificacao_indisponivel", "padrao", "bloqueante",
            f"O padrão de qualificação '{e.padrao_chave}' não tem versão publicada: a publicação do agente é recusada.",
            "Publique o padrão na aba Qualificação antes de publicar o agente.", "qualificacao_indisponivel",
        )]
    itens = [Item(
        "padrao_fixado" if e.padrao_fixado else "padrao_sera_fixado", "padrao", "ok",
        f"Padrão '{e.padrao_chave}': " + ("versão fixada no rascunho." if e.padrao_fixado else "a publicação fixa a versão mais nova."),
    )]
    if e.padrao_atualizacao:
        itens.append(Item(
            "padrao_atualizacao_disponivel", "padrao", "aviso",
            f"Há uma versão mais nova do padrão '{e.padrao_chave}' do que a fixada no rascunho.",
            "Atualize a versão do padrão na aba Qualificação e rode a avaliação de novo.",
        ))
    return itens


def _avaliacao(e: Entrada) -> list[Item]:
    itens: list[Item] = []
    consultivo = e.mecanismo.exigido and not e.mecanismo.comportamento_bloqueia
    sev: Severidade = "aviso" if consultivo else "bloqueante"
    recusa = None if consultivo else "eval_required"
    nota = " (consultiva: o agente exige a suíte de mecanismo)" if consultivo else ""
    if e.casos_comportamento < 1:
        itens.append(Item(
            "eval_sem_casos", "avaliacao", sev,
            f"O agente não tem casos de avaliação de comportamento ativos{nota}.",
            "Gere os casos com a IA (área 'Avaliações') ou crie-os na aba Avaliações; depois rode a avaliação completa.", recusa,
            {"casos_comportamento": 0},
        ))
    else:
        motivo = juiz_motivo(e.juiz, e.compiled.hash, e.limiar)
        det = {"casos_comportamento": e.casos_comportamento, "limiar": e.limiar,
               "score": e.juiz.score if e.juiz is not None else None}
        if motivo == "ok":
            itens.append(Item(
                "eval_juiz_ok", "avaliacao", "ok",
                f"A avaliação do prompt atual passou (nota {e.juiz.score:.2f} ≥ limiar {e.limiar:.2f}).", detalhe=det))
        else:
            msg = {
                "sem_execucao": "Nenhuma avaliação completa concluída para este agente.",
                "hash_diferente": "A última avaliação é de outro prompt: o rascunho mudou depois dela.",
                "incompleta": "A última avaliação não cobriu todos os casos ativos.",
                "abaixo_do_limiar": f"A nota da avaliação ({e.juiz.score if e.juiz and e.juiz.score is not None else '—'}) está abaixo do limiar {e.limiar:.2f}.",
            }[motivo]
            itens.append(Item(
                f"eval_juiz_{motivo}", "avaliacao", sev, msg + nota,
                "Clique em Rodar avaliação completa (todos os casos, com o modelo da versão). "
                "Só uma pessoa pode publicar com override.", recusa, det,
            ))
    if e.mecanismo.exigido:
        portao: PortaoMecanismo = decidir_portao(e.mecanismo, e.compiled.hash)
        if portao.liberado:
            itens.append(Item(
                "mecanismo_ok", "avaliacao", "ok",
                "A suíte de mecanismo passou (pass^k, modelo real) para o prompt atual.",
                detalhe={"casos_mecanismo": e.mecanismo.casos_ativos},
            ))
        else:
            itens.append(Item(
                f"mecanismo_{portao.codigo}", "avaliacao", "bloqueante",
                "A suíte de mecanismo não está aprovada para o prompt atual (portão sem override).",
                "Clique em Rodar suíte de mecanismo e corrija o que falhar.", "mecanismo_reprovado",
                {"motivo": portao.codigo, "casos_mecanismo": e.mecanismo.casos_ativos},
            ))
    else:
        itens.append(Item(
            "mecanismo_nao_configurado", "avaliacao", "aviso" if e.usa_canais else "ok",
            "O agente não tem suíte de mecanismo (casos roteirizados com asserts determinísticos)."
            if e.usa_canais else "Agente sem canal: a suíte de mecanismo não é exigida.",
            "Para um agente de canal, crie casos de mecanismo na aba Avaliações e passe a exigi-los." if e.usa_canais else None,
        ))
    return itens


def _camadas(e: Entrada) -> list[Item]:
    """Chain gate: a child is not publishable while an ancestor layer's own critical cases are not consolidated on the
    ancestor's current content. One item for the whole chain; the detail lists each ancestor (never case text)."""
    if not e.camadas_base:
        return []
    det = {"camadas": [c.to_dict() for c in e.camadas_base]}
    pend = base_nao_validada(e.camadas_base)
    if not pend:
        nomes = ", ".join(f"{c.agent_key} (v{c.versao})" if c.versao is not None else c.agent_key for c in e.camadas_base)
        return [Item("base_validada", "avaliacao", "ok", f"A base está validada: {nomes}.", detalhe=det)]
    partes = "; ".join(
        f"{c.agent_key}: " + ("sem versão" if c.motivo == "sem_versao" else
                              "sem casos de avaliação" if c.motivo == "sem_casos" else
                              "não medida" if c.motivo == "sem_medicao" else
                              f"{len(c.criticos_pendentes)} de {c.criticos_total} casos críticos pendentes")
        for c in pend)
    return [Item(
        "base_nao_validada", "avaliacao", "bloqueante",
        f"A base não está validada ({partes}). Este agente só roda os casos do seu próprio escopo.",
        "Rode a avaliação da base (agente de origem) até consolidar os casos críticos; depois volte a este agente.",
        "base_nao_validada", det)]


def _skills(e: Entrada) -> list[Item]:
    itens = [
        Item(
            "skill_desatualizada", "skills", "aviso",
            f"A skill '{p.skill}' está fixada na versão {p.versao}; a versão {p.nova_versao} já foi publicada.",
            "Clique em Atualizar skills para fixar todas na versão publicada mais nova.",
            detalhe={"skill": p.skill, "versao_fixada": p.versao, "nova_versao": p.nova_versao},
        )
        for p in e.pins if p.nova_versao is not None
    ]
    if e.pins and not itens:
        itens.append(Item("skills_atuais", "skills", "ok", "Todas as skills fixadas estão na versão publicada mais nova."))
    return itens


def _ferramentas(e: Entrada) -> list[Item]:
    itens: list[Item] = []
    por_nome = {f.ferramenta: f for f in e.ferramentas}
    sem = sorted(n for n in e.ferramentas_esperadas if n not in por_nome)
    for nome in sem:
        itens.append(Item(
            "ferramenta_sem_descricao", "ferramentas", "aviso",
            f"A ferramenta '{nome}' é esperada pela configuração ({e.ferramentas_esperadas[nome]}) e não tem linha de descrição: "
            "o modelo não a recebe.",
            "Descreva a ferramenta na aba Ferramentas, com a descrição e os rótulos dos parâmetros.",
            detalhe={"ferramenta": nome, "motivo": e.ferramentas_esperadas[nome]},
        ))
    for nome, faltam in sorted(e.rotulos_ausentes.items()):
        itens.append(Item(
            "rotulo_parametro_ausente", "ferramentas", "aviso",
            f"A ferramenta '{nome}' tem parâmetros sem rótulo: {', '.join(faltam)}.",
            "Preencha 'parametros' da linha da ferramenta com a descrição de cada parâmetro (chave = nome do parâmetro).",
            detalhe={"ferramenta": nome, "parametros": list(faltam)},
        ))
    if e.ferramentas and not itens:
        itens.append(Item("ferramentas_ok", "ferramentas", "ok", "As ferramentas esperadas têm descrição e rótulos de parâmetros."))
    return itens


def _catalogo(e: Entrada) -> list[Item]:
    """An agent with ``oferecer_opcoes`` ACTIVE needs a catalogue to offer from: the standard's ``parametros.catalogo``
    (a key of ``app.catalogos.CATALOGOS``). Without one the tool would answer ``indisponivel`` to every lead."""
    from app.catalogos import CATALOGOS

    ativa = any(f.ferramenta == "oferecer_opcoes" and f.ativo and (f.descricao or "").strip() for f in e.ferramentas)
    if not ativa:
        return []
    if e.padrao_catalogo not in CATALOGOS:
        return [Item(
            "catalogo_ausente", "ferramentas", "bloqueante",
            "A ferramenta 'oferecer_opcoes' está ativa, mas o padrão de qualificação não indica de onde vêm as opções "
            "(catálogo): o agente não teria o que oferecer.",
            f"Defina 'catalogo' nos parâmetros do padrão de qualificação ({', '.join(CATALOGOS)}) e publique o padrão.",
            "catalogo_ausente",
            detalhe={"catalogo": e.padrao_catalogo},
        )]
    return [Item(
        "catalogo_definido", "ferramentas", "ok", f"O catálogo de opções do agente é '{e.padrao_catalogo}'.",
    )]


def _periferia(e: Entrada) -> list[Item]:
    itens: list[Item] = []
    if e.specs_org_faltando:
        itens.append(Item(
            "spec_org_faltando", "especificacoes", "aviso",
            "A organização atual não preencheu especificações obrigatórias: " + ", ".join(e.specs_org_faltando) + ".",
            "Preencha na aba Especificações (cada organização preenche as suas).",
            detalhe={"chaves": list(e.specs_org_faltando)},
        ))
    for chave, codigo, motivo, mensagem in e.specs_org_invalidas:
        itens.append(Item(
            "spec_org_invalida", "especificacoes", "bloqueante" if e.spec_bloqueia else "aviso",
            f"Especificação da organização '{chave}' inválida ({codigo}/{motivo}): {mensagem}"
            + ("" if e.spec_bloqueia else " (modo report: um valor tipado NÃO é usado no prompt nem nas listas de links/contatos; texto livre vai só como dado.)"),
            f"Corrija a chave '{chave}' na aba Especificações ({motivo}); texto livre descreve a organização, não dá instruções.",
            detalhe={"chave": chave, "codigo": codigo, "motivo": motivo, "modo": "block" if e.spec_bloqueia else "report"},
            recusa_publicacao="compile_blocked" if e.spec_bloqueia else None,
        ))
    if e.regras_seguranca_sem_parametros:
        itens.append(Item(
            "regras_seguranca_sem_parametros", "seguranca", "bloqueante",
            "As regras de segurança desta instância estão sem linha gravada: "
            + ", ".join(e.regras_seguranca_sem_parametros)
            + ". (O piso da plataforma continua valendo em cada turno, mas a instância precisa das linhas.)",
            "Grave a regra na aba Conformidade (a migração 063 cria as linhas de toda instância).",
            detalhe={"regras": list(e.regras_seguranca_sem_parametros)},
            recusa_publicacao="compile_blocked",
        ))
    if e.geracao_status in ACTIVE_STATUSES:
        itens.append(Item(
            "geracao_em_andamento", "geracao", "aviso", "Uma geração por IA está em andamento: o rascunho ainda pode mudar.",
            "Espere a geração terminar (GET .../geracoes) antes de avaliar.",
        ))
    for a in e.geracao_areas:
        if a.status in ("falhou", "pulado", "cancelada"):
            itens.append(Item(
                "geracao_area_nao_concluida", "geracao", "aviso",
                f"Na última geração por IA, a área '{a.area}' terminou como '{a.status}'" + (f" ({a.erro})." if a.erro else "."),
                f"Repita a área na aba Geração com IA ou escreva à mão.",
                detalhe={"area": a.area, "status": a.status, "erro": a.erro},
            ))
        if a.lacunas:
            itens.append(Item(
                "geracao_lacunas", "geracao", "aviso",
                f"A geração por IA deixou {len(a.lacunas)} lacuna(s) na área '{a.area}': ela não inventa o que falta.",
                "Preencha cada lacuna à mão (os códigos dizem o que falta).",
                detalhe={"area": a.area, "lacunas": list(a.lacunas[:20])},
            ))
    if e.usa_canais and e.controle_modo is not None:
        if e.controle_modo == "desligado":
            itens.append(Item(
                "controles_desligado", "operacao", "aviso",
                "O agente de canal está 'desligado' (padrão de um agente novo): não responde a ninguém.",
                "Depois de publicar, clique em Ligar agente.",
                detalhe={"modo": e.controle_modo},
            ))
        else:
            itens.append(Item("controles_definidos", "operacao", "ok", f"Modo de operação: {e.controle_modo}."))
    return itens


def _atendimento(e: Entrada) -> list[Item]:
    """Every conversational agent can hand off to a human, so the team must be reachable: no fallback number, no publish."""
    if not e.canonico_exigido:
        return []
    if not e.numero_fallback_definido:
        return [Item(
            "numero_fallback_ausente", "operacao", "bloqueante",
            "Não há número de atendimento para avisar a equipe quando o agente passa a conversa para uma pessoa.",
            "Um administrador da plataforma informa o número em Configurações do agente.",
            "numero_fallback_ausente",
        )]
    return [Item("numero_fallback_definido", "operacao", "ok", "O número de atendimento para passagem a uma pessoa está definido.")]


def _canonico(e: Entrada) -> list[Item]:
    """The canonical template's must-haves. ADVISORY first (shadow, like every new gate): promoted to blocking once the
    fleet's published agents carry them (destination: ``KB § PATTERNS/backend/canonical-agent-template.md`` §4)."""
    if not e.canonico_exigido:
        return []
    itens: list[Item] = []
    if REGRA_DISCORDAR not in e.regras_secoes:
        itens.append(Item(
            "sem_secao_discordar", "modelo", "aviso",
            "Nenhuma seção ativa do agente traz a regra de discordar com respeito: sem ela o agente tende a concordar para agradar.",
            f"Marque com a regra '{REGRA_DISCORDAR}' a seção que diz ao agente para discordar com respeito "
            "(no modelo canônico é a seção 'Honestidade'; o Criador de Agentes já a marca).",
        ))
    if TAG_BAJULACAO not in e.tags_comportamento:
        itens.append(Item(
            "sem_evals_bajulacao", "modelo", "aviso",
            "Nenhum caso de comportamento testa bajulação (pedir que o agente concorde, elogie ou mude de opinião sem motivo).",
            f"Adicione 2 ou 3 casos de comportamento com a tag '{TAG_BAJULACAO}'.",
        ))
    if not itens:
        itens.append(Item("modelo_canonico", "modelo", "ok", "O rascunho tem os itens obrigatórios do modelo canônico."))
    return itens


def compor(e: Entrada) -> Prontidao:
    """The readiness items of the snapshot (blocking first, then advisory, then ok; stable within a severity)."""
    itens = [*_compilador(e), *_padrao(e), *_avaliacao(e), *_camadas(e), *_skills(e), *_ferramentas(e), *_catalogo(e), *_periferia(e), *_atendimento(e), *_canonico(e)]
    for i in itens:
        if i.grupo not in GRUPOS:
            raise ValueError(f"item {i.codigo!r} has group {i.grupo!r}, outside GRUPOS (the panel cannot label it)")
        if i.severidade == "bloqueante" and i.recusa_publicacao not in RECUSAS_PUBLICACAO:
            raise ValueError(f"blocking item {i.codigo!r} names no publish refusal ({i.recusa_publicacao!r})")
        if i.severidade != "bloqueante" and i.recusa_publicacao is not None:
            raise ValueError(f"item {i.codigo!r} is not blocking and must not name a refusal")
    ordem = {"bloqueante": 0, "aviso": 1, "ok": 2}
    itens.sort(key=lambda i: ordem[i.severidade])
    return Prontidao(e.agent_key, e.version_id, e.compiled.hash, tuple(itens))


# ── the reads ───────────────────────────────────────────────────────────────


def coletar(
    *, store: Any, catalog: Any, org_id: UUID, agent: Any, draft: Any, gate: Any, padroes: Any, skills: Any,
    geracoes: Any, evals: Any, controles: Any | None, compiled: CompiledPrompt | None = None,
    spec_validacao: ConfigValidacao | None = None, conformidade: Any | None = None, consolidacao: Any | None = None,
) -> Entrada:
    """Read everything the composer needs for ``draft`` of ``agent`` (``org_id`` owns the definition). ``compiled``:
    the prompt the caller already compiled (publish) -- otherwise compiled here, read-only (nothing is stamped)."""
    from app.studio.bundles import compile_version
    from app.studio.geracao import conteudo_status
    from app.studio.plataforma import padrao_de
    from app.studio.resolucao import resolve_agent_for_org

    compiled = compiled or compile_version(store, catalog, org_id, agent, draft)
    chave = padrao_de(agent)
    publicado = atualizacao = False
    if chave is not None:
        try:
            nova = padroes.obter_versao_publicada(chave)
            publicado = True
            atualizacao = draft.qualificacao_versao_id is not None and draft.qualificacao_versao_id != nova.id
        except NotFound:
            publicado = False

    padrao_catalogo: str | None = None
    if chave is not None and publicado:
        try:
            pinada = draft.qualificacao_versao_id
            vp = padroes.obter_versao(pinada) if pinada is not None else padroes.obter_versao_publicada(chave)
            padrao_catalogo = vp.parametros.catalogo
        except NotFound:
            padrao_catalogo = None

    # chain gate: an agent with a parent is judged against its bases. No consolidation store for a child is a loud
    # failure (readiness must never read "no bases" for an agent that has one).
    camadas_base: tuple[VeredictoCamada, ...] = ()
    if getattr(agent, "pai_agent_id", None) is not None:
        if consolidacao is None:
            raise ValueError("coletar: um agente com pai exige a store de consolidação (portão da cadeia)")
        camadas_base = coletar_camadas_base(store=store, catalog=catalog, consolidacao=consolidacao, org_id=org_id, agent=agent, draft=draft)

    casos = evals.list_cases(org_id, agent.id)
    ativos = [c for c in casos if c.ativo]
    refs = skills.listar_refs(draft.id)
    ef = efetivo(store)  # 073: readiness judges what compiles -- the parent chain merged in
    rows = ef.list_ferramentas(org_id, draft.id)
    linhas = tuple(FerramentaLinha(f.ferramenta, f.ativo, f.descricao, dict(f.parametros)) for f in rows)
    tem_skills = (bool(refs) or any(skills.listar_refs(vid) for _, vid in ef.cadeia(org_id, draft.id))
                  or any(s.ativo for s in ef.list_skills(org_id, draft.id)))

    cfg = spec_validacao or config_atual()
    invalidas: tuple[tuple[str, str, str, str], ...] = ()
    try:
        r_org = resolve_agent_for_org(store, org_id, agent.key, versao="rascunho")
        faltando = r_org.faltando
        invalidas = tuple(
            (v.chave, v.codigo, v.motivo, v.mensagem)
            for v in violacoes_armazenadas({d.chave: d.tipo for d in r_org.specs_declaradas}, r_org.valores, config=cfg)
        )
    except NotFound:
        faltando = ()

    ultima = next(iter(geracoes.list_geracoes(org_id, agent.id, 1)), None)
    areas: tuple[AreaGeracao, ...] = ()
    if ultima is not None:
        areas = tuple(
            AreaGeracao(a.area, a.status, a.erro, tuple(a.lacunas)) for a in geracoes.list_areas(org_id, ultima.id)
        )

    modo = None
    if controles is not None and agent.usa_canais:
        try:
            modo = controles.get(org_id, agent.id).modo
        except NotFound:
            modo = None

    sem_regras: tuple[str, ...] = ()
    if conformidade is not None and agent.usa_canais and getattr(agent, "definition_scope", None) == "instancia":
        sem_regras = tuple(conformidade.regras_sem_parametros(org_id, agent.id))

    return Entrada(
        agent_key=agent.key, version_id=draft.id, compiled=compiled, limiar=float(agent.publicacao_limiar),
        usa_canais=agent.usa_canais, conteudo=conteudo_status(store, skills, agent),
        padrao_chave=chave, padrao_fixado=draft.qualificacao_versao_id is not None, padrao_publicado=publicado,
        padrao_atualizacao=atualizacao,
        casos_comportamento=sum(1 for c in ativos if c.suite == "comportamento"),
        casos_mecanismo=sum(1 for c in ativos if c.suite == "mecanismo"),
        juiz=gate.latest_concluded_run(org_id, draft.id),
        mecanismo=gate.mecanismo_requisito(org_id, agent.id, draft.id),
        pins=tuple(PinSkill(r.skill_chave, r.versao, r.nova_versao) for r in refs),
        ferramentas=linhas,
        ferramentas_esperadas=ferramentas_esperadas(
            usa_canais=agent.usa_canais, tem_skills=tem_skills, tool_policy=dict(draft.tool_policy), com_padrao=chave is not None,
            padrao_conclusivo=_padrao_tem_estagio_conclusivo(padroes, chave, draft),
            imobiliario=agente_imobiliario(f.ferramenta for f in rows)),
        rotulos_ausentes=rotulos_ausentes(linhas),
        specs_org_faltando=tuple(faltando),
        specs_org_invalidas=invalidas,
        spec_bloqueia=cfg.bloqueia,
        regras_seguranca_sem_parametros=sem_regras,
        geracao_status=ultima.status if ultima is not None else None,
        geracao_areas=areas,
        controle_modo=modo,
        canonico_exigido=canonico_exigido(agent),
        regras_secoes=tuple(sorted({r for s in ef.list_sections(org_id, draft.id) if s.ativo and s.conteudo.strip() for r in s.regras})),
        tags_comportamento=tuple(sorted({t for c in ativos if c.suite == "comportamento" for t in c.tags})),
        numero_fallback_definido=_numero_fallback() is not None,
        padrao_catalogo=padrao_catalogo,
        camadas_base=camadas_base,
    )


def _padrao_tem_estagio_conclusivo(padroes: Any, chave: str | None, draft: Any) -> bool:
    """Does the standard this draft works with have a ``conclusivo`` stage? Reads the version the draft pins, else the
    published one. Unreadable -> ``True`` (unmeasurable keeps the expectation; it never hides a missing description)."""
    if chave is None:
        return True
    try:
        pin = getattr(draft, "qualificacao_versao_id", None)
        versao = padroes.obter_versao(pin) if pin is not None else padroes.obter_versao_publicada(chave)
    except NotFound:
        try:
            versao = padroes.obter_versao_publicada(chave)
        except NotFound:
            return True
    return any(e.conclusivo for e in versao.estagios)


def canonico_exigido(agent: Any) -> bool:
    """Every conversational agent (all but the internal generator, which only emits JSON)."""
    return getattr(agent, "papel", None) != "gerador"


def falta_numero_fallback(agent: Any) -> bool:
    """The publish refusal ``numero_fallback_ausente`` -- the same predicate the readiness item uses."""
    return canonico_exigido(agent) and _numero_fallback() is None


def _numero_fallback() -> str | None:
    """The platform runtime setting (074), read through the process singleton every consumer shares."""
    from app.config import settings
    from app.services.runtime_settings import get_runtime_settings_service

    return get_runtime_settings_service(settings).numero_fallback_atendimento()


def avaliar(**kw: Any) -> Prontidao:
    """``compor(coletar(**kw))`` -- the readiness of a draft in one call (the route and the publish refusals)."""
    return compor(coletar(**kw))
