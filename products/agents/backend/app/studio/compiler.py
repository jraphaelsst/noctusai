"""THE master-prompt compiler (contract §C, §A4).

``compile_prompt`` is pure and deterministic: no IO, no clock, no random, no
draft UUIDs in the text, no dict-iteration-order-dependent text. The same
input always yields the same ``texto`` and ``hash``; any field that reaches
the text changes the hash. The runtime (BE-RT ``build_studio_spec``), the
inspector (``GET .../compiled``) and the publish step all call this one
function — nobody re-implements composition.

Output layout (§C, exact; blocks joined by ``\\n\\n``, trailing newline
stripped):

1. every active section by ``(ordem, chave)``: ``# {titulo}\\n\\n{conteudo}``
   — an empty section is skipped AND reported (blocking);
2. ``# Skills`` — only with ≥1 active skill;
3. ``# Base de conhecimento`` — only when ``tool_policy.knowledge`` and ≥1
   collection;
4. ``# Ferramentas`` — always; web search and knowledge are stated on/off
   (the model must know a family is OFF, not just not see it), the skills
   line appears only with ≥1 active skill;
5. ``# Cliente em foco: {nome}`` — only with a client.

The just-in-time layer (skill bodies, skill files, collections) is listed in
``sob_demanda`` and NEVER inside ``texto``.

CONTENT MODE (Julia v2, CONTRACT §2.1 rows 4-5): when ``version.conteudo`` is a bundle the
compiler keeps ORDER and LAYOUT only — every human-readable string (block titles, intros, the
tools lines, the client labels) is a row of ``agent_version_textos`` and the ``# Ferramentas``
block lists the version's ``agent_version_ferramentas`` rows (name + DB description). A
required string that is missing is a BLOCKING warning, never a default. The hash then covers
``texto`` AND every content row (``hash_payload``); ``conteudo is None`` (legacy agents) keeps
the pre-v2 strings below and ``hash == prompt_hash(texto)`` byte for byte. Compiled FOR AN ORG
(``org_specs`` given) every ``{{org.chave}}`` placeholder is replaced by that org's value
first, so the text, the rows and the hash are exactly what the model receives.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from typing import Any

from app.studio.especificacoes import placeholders_org, resolver_texto
from app.studio.ferramentas_registry import ferramenta_conhecida, ferramenta_da_conversa, nome_no_modelo
from app.studio.models import (
    ClientBundle,
    CollectionSummary,
    CompiledPrompt,
    CompileInput,
    CompileWarning,
    ConteudoBundle,
    ManifestOrigin,
    ManifestSection,
    OnDemandItem,
    SectionData,
    SkillData,
    VersionBundle,
)
from app.studio.skills_contract import SkillRef
from app.studio.textos_registry import TEXTOS, chaves_exigidas, placeholders_de

__all__ = [
    "AUTO_TITLES",
    "CLIENT_ENTRY_ORDER",
    "CLIENT_ENTRY_LABELS",
    "TOKEN_WARNING_THRESHOLD",
    "CONTEUDO_CODIGOS",
    "compile_prompt",
    "hash_payload",
    "estimate_tokens",
    "prompt_hash",
]

#: §C: ``tokens_estimados > 12000`` ⇒ non-blocking warning.
TOKEN_WARNING_THRESHOLD = 12000

SKILLS_TITLE = "Skills"
KNOWLEDGE_TITLE = "Base de conhecimento"
TOOLS_TITLE = "Ferramentas"
CLIENT_TITLE_PREFIX = "Cliente em foco"

#: Titles the compiler emits itself — a section reusing one is ambiguous.
AUTO_TITLES = (SKILLS_TITLE, KNOWLEDGE_TITLE, TOOLS_TITLE)

#: §C fixed order for client entries.
CLIENT_ENTRY_ORDER = (
    "marca",
    "publico",
    "posicionamento",
    "trava",
    "decisao",
    "aprendizado",
    "evidencia",
    "nota",
)
CLIENT_ENTRY_LABELS = {
    "marca": "Marca",
    "publico": "Público",
    "posicionamento": "Posicionamento",
    "trava": "Travas",
    "decisao": "Decisões",
    "aprendizado": "Aprendizados",
    "evidencia": "Evidências",
    "nota": "Notas",
}

_SKILLS_INTRO = (
    "Skills são procedimentos especializados. Quando o pedido corresponder à descrição de uma skill,\n"
    "chame `abrir_skill` com o nome dela ANTES de responder e siga as instruções que ela devolver.\n"
    "Arquivos de referência de uma skill são lidos com `ler_arquivo_skill`."
)
_KNOWLEDGE_INTRO = (
    "Use `kb_buscar` para encontrar documentos e `kb_ler` para ler um documento pelo slug.\n"
    "Cite a origem com a tag da coleção (ex.: [AU]) quando usar um conteúdo."
)


#: The blocking-warning codes that mean "the content is incomplete" — publish answers them with
#: 409 ``conteudo_incompleto`` (every other blocking warning stays 409 ``compile_blocked``).
CONTEUDO_CODIGOS = frozenset({
    "texto_ausente", "placeholder_desconhecido", "ferramenta_desconhecida",
    "skill_exigida_inexistente", "decisao_sem_opcao_padrao", "decisao_em_secao",
    "spec_nao_declarada", "spec_org_faltando",
})


def estimate_tokens(text: str) -> int:
    """§C: ``ceil(len(texto) / 4)``."""
    return math.ceil(len(text) / 4)


def prompt_hash(texto: str) -> str:
    """§C: ``"sha256:" + hexdigest(texto.encode("utf-8"))``."""
    return "sha256:" + hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _policy_flag(policy: dict[str, Any], key: str) -> bool:
    return bool(policy.get(key, False))


#: Sections whose ``chave`` starts with this hold a RULE a channel transport asks the agent to apply
#: (``POST /api/channels/agents/{key}/decisoes/{chave}``), not conversation instructions: they are
#: edited in the studio like any section but never compiled into the conversation prompt.
#: LEGACY MODE ONLY — in content mode a decision is a row of ``agent_version_decisoes`` and a
#: ``decisao-*`` section is a blocking ``decisao_em_secao`` warning.
DECISAO_PREFIX = "decisao-"


def _active_sections(secoes, *, conteudo: bool = False) -> list[SectionData]:
    return sorted(
        (s for s in secoes if s.ativo and (conteudo or not s.chave.startswith(DECISAO_PREFIX))),
        key=lambda s: (s.ordem, s.chave),
    )


def _active_skills(skills) -> list[SkillData]:
    return sorted((s for s in skills if s.ativo), key=lambda s: (s.ordem, s.nome))


def _sorted_collections(knowledge) -> list[CollectionSummary]:
    return sorted(knowledge, key=lambda c: (c.ordem, c.slug))


class _Strings:
    """The compiler's human-readable strings. Legacy mode answers with the pre-v2 constant it is
    handed; content mode answers ONLY from ``agent_version_textos`` and records a key that is
    missing/blank (the caller turns the set into one blocking warning — never into a default)."""

    def __init__(self, conteudo: ConteudoBundle | None) -> None:
        self._c = conteudo
        self.ausentes: set[str] = set()

    @property
    def conteudo(self) -> bool:
        return self._c is not None

    def peek(self, chave: str, legado: str) -> str:
        """Like a call, but a missing key is NOT recorded (used only to know a reserved title)."""
        return legado if self._c is None else self._c.texto(chave).strip()

    def __call__(self, chave: str, legado: str) -> str:
        if self._c is None:
            return legado
        texto = self._c.texto(chave).strip()
        if not texto:
            self.ausentes.add(chave)
        return texto


def _collection_line(c: CollectionSummary, S: _Strings) -> str:
    tag = f" [{c.tag}]" if c.tag else ""
    desc = f": {c.descricao.strip()}" if c.descricao and c.descricao.strip() else ""
    noun = (
        S("compilador.unidade_documento", "documento")
        if c.doc_count == 1
        else S("compilador.unidade_documentos", "documentos")
    )
    return f"- `{c.slug}`{tag} — {c.nome}{desc} ({c.doc_count} {noun})"


def _tools_block(web: bool, knowledge: bool, has_skills: bool, S: _Strings, ferramentas) -> str:
    title = S("compilador.titulo_ferramentas", TOOLS_TITLE)
    if not S.conteudo:
        lines = [
            "- Pesquisa na web: ativada (`WebSearch`)."
            if web
            else "- Pesquisa na web: desativada — não há acesso à web nesta conversa.",
            "- Base de conhecimento: ativada (`kb_buscar`, `kb_ler`)."
            if knowledge
            else "- Base de conhecimento: desativada.",
        ]
        if has_skills:
            lines.append("- Skills: ativadas (`abrir_skill`, `ler_arquivo_skill`).")
        return f"# {title}\n\n" + "\n".join(lines)
    lines = [
        S("compilador.ferramenta_linha.web_ativada" if web else "compilador.ferramenta_linha.web_desativada", ""),
        S(
            "compilador.ferramenta_linha.conhecimento_ativada" if knowledge
            else "compilador.ferramenta_linha.conhecimento_desativada", "",
        ),
    ]
    if has_skills:
        lines.append(S("compilador.ferramenta_linha.skills_ativada", ""))
    # The tools the version actually offers IN THE CONVERSATION: name + the DB description (CONTRACT §2.1 row 5).
    # The extraction-only tools (``registrar_resumo`` / ``registrar_escolha``) are never offered on a turn.
    # A tool-group row (``academia_kb_buscar``) is named as the model sees it (``mcp__academia__kb_buscar``).
    lines += [
        f"- `{nome_no_modelo(f.ferramenta)}` — {f.descricao.strip()}"
        for f in sorted((f for f in ferramentas if f.ativo and ferramenta_da_conversa(f.ferramenta)),
                        key=lambda f: f.ferramenta)
    ]
    return f"# {title}\n\n" + "\n".join(line for line in lines if line)


def _qualificacao_block(q, S: _Strings) -> str:
    """The pinned standard as readable text. Headings/connectives are textos rows; every criterion,
    option, stage, minimum and identity timing is a data row — code only orders and lays out."""
    titulo = S("compilador.titulo_qualificacao", "")
    parts = [f"# {titulo}", S("compilador.qualificacao_intro", "")]
    crit = sorted(q.criterios, key=lambda c: (c.ordem, c.chave))
    rot = {c.chave: c.rotulo for c in crit}
    lines = []
    for c in crit:
        lines.append(f"- **{c.rotulo}** (`{c.chave}`) — {c.descricao_modelo.strip()}")
        if c.opcoes:
            lines.append(f"  {S('compilador.qualificacao_rotulo_opcoes', '')} " + "; ".join(
                f"`{v}` ({r})" + (f" — {d.strip()}" if d and d.strip() else "") for v, r, d in c.opcoes
            ))
    parts.append(f"## {S('compilador.qualificacao_rotulo_criterios', '')}\n" + "\n".join(lines))
    if q.estagios:
        est = sorted(q.estagios, key=lambda e: (e.ordem, e.chave))
        parts.append(
            f"## {S('compilador.qualificacao_rotulo_estagios', '')}\n"
            + "\n".join(f"- **{e.rotulo}** (`{e.chave}`) — {e.descricao.strip()}" for e in est)
        )
    if q.minimo_para_ofertar:
        parts.append(
            f"## {S('compilador.qualificacao_rotulo_minimo', '')}\n"
            + ", ".join(rot.get(k, k) for k in q.minimo_para_ofertar)
        )
    if q.identidade:
        parts.append(
            f"## {S('compilador.qualificacao_rotulo_identidade', '')}\n"
            + "\n".join(f"- {r.strip()}: {m.strip()}" for _k, r, m in q.identidade)
        )
    return "\n\n".join(parts)


def _client_block(client: ClientBundle, S: _Strings) -> str:
    prefix = S("compilador.titulo_cliente", CLIENT_TITLE_PREFIX)
    parts = [f"# {prefix}: {client.nome.strip()}"]
    resumo = (client.resumo or "").strip()
    if resumo:
        parts.append(resumo)
    active = [e for e in client.entradas if e.status == "ativo"]
    for tipo in CLIENT_ENTRY_ORDER:
        items = [e for e in active if e.tipo == tipo]
        if not items:
            continue
        lines = []
        for e in items:
            conteudo = (e.conteudo or "").strip()
            titulo = e.titulo.strip()
            lines.append(f"- **{titulo}** — {conteudo}" if conteudo else f"- **{titulo}**")
        rotulo = S(f"compilador.cliente_rotulo.{tipo}", CLIENT_ENTRY_LABELS[tipo])
        parts.append(f"## {rotulo}\n" + "\n".join(lines))
    return "\n\n".join(parts)


# ── org specs: compile the definition FOR an org ────────────────────────────


def _resolver_conteudo(c: ConteudoBundle, valores: dict[str, str]) -> ConteudoBundle:
    def r(t: str) -> str:
        return resolver_texto(t, valores)

    return ConteudoBundle(
        textos=tuple(replace(t, conteudo=r(t.conteudo)) for t in c.textos),
        ferramentas=tuple(
            replace(
                f, descricao=r(f.descricao),
                parametros={k: (r(v) if isinstance(v, str) else v) for k, v in f.parametros.items()},
            )
            for f in c.ferramentas
        ),
        decisoes=tuple(
            replace(
                d, titulo=r(d.titulo), regra=r(d.regra),
                opcoes=tuple(replace(o, rotulo=r(o.rotulo)) for o in d.opcoes),
            )
            for d in c.decisoes
        ),
        specs=c.specs,
    )


def _resolver_versao(v: VersionBundle, valores: dict[str, str]) -> VersionBundle:
    def r(t: str) -> str:
        return resolver_texto(t, valores)

    return replace(
        v,
        secoes=tuple(replace(s, titulo=r(s.titulo), conteudo=r(s.conteudo)) for s in v.secoes),
        skills=tuple(replace(sk, descricao=r(sk.descricao), corpo=r(sk.corpo)) for sk in v.skills),
        # a pinned library skill's index line is model-visible too (its body is resolved when opened)
        skill_refs=tuple(replace(ref, descricao=r(ref.descricao)) for ref in v.skill_refs),
        conteudo=_resolver_conteudo(v.conteudo, valores) if v.conteudo is not None else None,
    )


def _textos_de_conteudo(v: VersionBundle, cont: ConteudoBundle):
    """Every text the author wrote that may carry a ``{{org.x}}`` placeholder: (where, text)."""
    for s in v.secoes:
        yield f"seção '{s.chave}'", s.titulo
        yield f"seção '{s.chave}'", s.conteudo
    for sk in v.skills:
        yield f"skill '{sk.nome}'", sk.descricao
        yield f"skill '{sk.nome}'", sk.corpo
    for t in cont.textos:
        yield f"texto '{t.chave}'", t.conteudo
    for f in cont.ferramentas:
        yield f"ferramenta '{f.ferramenta}'", f.descricao
        for val in f.parametros.values():
            if isinstance(val, str):
                yield f"ferramenta '{f.ferramenta}'", val
    for d in cont.decisoes:
        yield f"decisão '{d.chave}'", d.titulo
        yield f"decisão '{d.chave}'", d.regra
        for o in d.opcoes:
            yield f"decisão '{d.chave}'", o.rotulo


def _avisos_conteudo(
    inp: CompileInput, cont: ConteudoBundle, S: _Strings, skills: list[SkillData], com_cliente: bool,
    refs: list[SkillRef] = (), autorada: VersionBundle | None = None,
) -> list[CompileWarning]:
    """Completeness of a content-mode compile (blocking — CONTEUDO_CODIGOS)."""
    out: list[CompileWarning] = []
    v = inp.version

    exigidas = chaves_exigidas(
        tool_policy=inp.tool_policy, tem_skills=bool(skills) or bool(refs), com_cliente=com_cliente, canal=inp.canal,
        com_qualificacao=inp.qualificacao is not None,
    )
    preenchidas = {t.chave for t in cont.textos if t.conteudo.strip()}
    faltam = sorted((exigidas - preenchidas) | S.ausentes)
    if faltam:
        out.append(CompileWarning(
            "texto_ausente", "Textos do sistema obrigatórios sem conteúdo: " + ", ".join(faltam) + ".", True,
        ))

    # a runtime {placeholder} the registry does not allow for that key
    for t in cont.textos:
        spec = TEXTOS.get(t.chave)
        permitidos = set(spec.placeholders_permitidos) if spec is not None else set()
        desconhecidos = sorted(placeholders_de(t.conteudo) - permitidos)
        if desconhecidos:
            out.append(CompileWarning(
                "placeholder_desconhecido",
                f"O texto '{t.chave}' usa placeholders não permitidos: "
                + ", ".join("{" + n + "}" for n in desconhecidos) + ".",
                True,
            ))

    ativas = {sk.nome for sk in skills} | {r.skill_key for r in refs}
    for r in refs:
        # D7: a pinned skill gates tools; a gate on a tool the code does not know can never fire.
        for nome_ferramenta in r.obrigatoria_para:
            if not ferramenta_conhecida(nome_ferramenta):
                out.append(CompileWarning(
                    "ferramenta_desconhecida",
                    f"A ferramenta '{nome_ferramenta}' (exigida pela skill '{r.skill_key}') não existe no registro do código.",
                    True,
                ))
    for f in cont.ferramentas:
        if not ferramenta_conhecida(f.ferramenta):
            out.append(CompileWarning(
                "ferramenta_desconhecida", f"A ferramenta '{f.ferramenta}' não existe no registro do código.", True,
            ))
        if f.ativo and not f.descricao.strip():
            out.append(CompileWarning(
                "texto_ausente", f"A ferramenta '{f.ferramenta}' está ativa e sem descrição.", True,
            ))
        if f.obrigatoria_skill and f.obrigatoria_skill not in ativas:
            out.append(CompileWarning(
                "skill_exigida_inexistente",
                f"A ferramenta '{f.ferramenta}' exige a skill '{f.obrigatoria_skill}', que não está ativa na versão.",
                True,
            ))

    for d in cont.decisoes:
        padroes = [o for o in d.opcoes if o.padrao]
        if len(padroes) != 1 or len({o.valor for o in d.opcoes}) != len(d.opcoes):
            out.append(CompileWarning(
                "decisao_sem_opcao_padrao",
                f"A decisão '{d.chave}' precisa de opções com valores únicos e exatamente uma marcada como padrão.",
                True,
            ))
        if not d.regra.strip():
            out.append(CompileWarning("texto_ausente", f"A decisão '{d.chave}' está sem regra.", True))

    for s in v.secoes:
        if s.ativo and s.chave.startswith(DECISAO_PREFIX):
            out.append(CompileWarning(
                "decisao_em_secao",
                f"A seção '{s.chave}' é uma decisão: mova-a para Decisões (regra e opções tipadas).", True,
            ))

    # org-spec declarations ↔ placeholders used
    # read the AUTHORED rows (an org compile has already replaced every placeholder in ``v`` / ``cont``)
    fonte = autorada if autorada is not None and autorada.conteudo is not None else v
    declaradas = {sp.chave for sp in cont.specs}
    usadas: set[str] = set()
    for _, texto in _textos_de_conteudo(fonte, fonte.conteudo if fonte.conteudo is not None else cont):
        usadas |= placeholders_org(texto)
    for ref in fonte.skill_refs:  # a pinned library skill: its index line + what its body / files use
        usadas |= placeholders_org(ref.descricao) | set(ref.placeholders)
    nao_declaradas = sorted(usadas - declaradas)
    if nao_declaradas:
        out.append(CompileWarning(
            "spec_nao_declarada",
            "Placeholders {{org.…}} sem declaração em Especificações da organização: "
            + ", ".join(nao_declaradas) + ".",
            True,
        ))
    sobra = sorted(declaradas - usadas)
    if sobra:
        out.append(CompileWarning(
            "spec_nao_usada", "Especificações declaradas e não usadas em nenhum texto: " + ", ".join(sobra) + ".", False,
        ))
    return out


# ── hash ────────────────────────────────────────────────────────────────────


def hash_payload(
    texto: str, cont: ConteudoBundle, version: VersionBundle, extras: dict[str, Any] | None,
    qualificacao: Any = None,
) -> dict[str, Any]:
    """The canonical, row-id-free payload a content-mode hash is taken over: the prompt text, the
    version settings and EVERY content row. Changing any one of them changes the hash."""
    return {
        "v": 1,
        "texto": texto,
        "config": {
            "provider": version.provider, "model": version.model, "effort": version.effort,
            "max_turns": version.max_turns, "idioma": version.idioma,
            "tool_policy": dict(version.tool_policy),
        },
        "textos": sorted([t.chave, t.conteudo] for t in cont.textos),
        "ferramentas": sorted(
            [f.ferramenta, f.ativo, f.descricao, sorted(f.parametros.items()), f.obrigatoria_skill]
            for f in cont.ferramentas
        ),
        "decisoes": sorted(
            [d.chave, d.titulo, d.regra, [[o.valor, o.rotulo, o.padrao] for o in d.opcoes]]
            for d in cont.decisoes
        ),
        "specs": sorted(
            [sp.chave, sp.rotulo, sp.descricao, sp.tipo, sp.obrigatoria, sp.exemplo] for sp in cont.specs
        ),
        "extras": extras or {},
        **_skills_hash(version),
        **_skill_refs_hash(version),
        "qualificacao": None if qualificacao is None else {
            "versao_id": str(qualificacao.versao_id) if qualificacao.versao_id else None,
            "criterios": sorted(
                [c.chave, c.rotulo, c.descricao_modelo, c.grupo, c.ordem, [list(o) for o in c.opcoes]]
                for c in qualificacao.criterios
            ),
            "estagios": sorted([e.chave, e.rotulo, e.descricao, e.ordem] for e in qualificacao.estagios),
            "minimo": list(qualificacao.minimo_para_ofertar),
            "identidade": [list(i) for i in qualificacao.identidade],
        },
    }


def _skills_hash(version: VersionBundle) -> dict[str, Any]:
    """The version's OWN skills -- name, index line, BODY, order, active flag and every reference file (path,
    title, sha256 of its text). The bodies are on-demand (never in ``texto``), so without this a skill edit left
    the hash -- the publish CAS and the eval stamp -- unchanged: the gate could judge one body and ship another.
    Present ONLY when the version has skills, so a version without any keeps the hash it always had."""
    if not version.skills:
        return {}
    return {"skills": sorted(
        [sk.nome, sk.descricao, sk.corpo, sk.ordem, sk.ativo,
         sorted([f.caminho, f.titulo, f.sha256] for f in sk.arquivos)]
        for sk in version.skills
    )}


def _skill_refs_hash(version: VersionBundle) -> dict[str, Any]:
    """The pinned library skills (key, version id, index text, gating tools) — present ONLY when the
    version pins any, so a version without pins keeps the hash it always had. A pinned skill version is
    immutable, so its id identifies its body."""
    if not version.skill_refs:
        return {}
    return {"skill_refs": sorted(
        [r.skill_key, str(r.skill_versao_id), r.descricao, sorted(r.obrigatoria_para)] for r in version.skill_refs
    )}


def _hash_of(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _manifest_conteudo(cont: ConteudoBundle) -> list[ManifestSection]:
    """Attribute the content that reaches the model OUTSIDE the system prompt to its row."""
    out: list[ManifestSection] = []

    def add(tipo: str, chave: str, titulo: str, id_, campo: str, texto: str) -> None:
        out.append(ManifestSection(
            chave=f"{tipo}:{chave}", titulo=titulo, origem=ManifestOrigin(tipo, id_, campo),
            inicio=None, fim=None, chars=len(texto), tokens=estimate_tokens(texto),
        ))

    for t in sorted(cont.textos, key=lambda t: t.chave):
        add("texto", t.chave, t.chave, t.id, "conteudo", t.conteudo)
    for f in sorted(cont.ferramentas, key=lambda f: f.ferramenta):
        add("ferramenta", f.ferramenta, f.ferramenta, f.id, "descricao", f.descricao)
    for d in sorted(cont.decisoes, key=lambda d: d.chave):
        add("decisao", d.chave, d.titulo, d.id, "regra", d.regra)
    return out


def compile_prompt(inp: CompileInput) -> CompiledPrompt:
    """Compile a version (+ knowledge catalog, + optional client) into the
    master prompt. Pure, deterministic, no IO."""
    avisos: list[CompileWarning] = []
    version = inp.version
    #: The AUTHORED version (placeholders intact). Spec usage (``spec_nao_usada`` / ``spec_nao_declarada``) is a
    #: property of what the definition WROTE, so it is read from here -- after an org compile the resolved text has
    #: no ``{{org.x}}`` left and every declared spec would read as unused.
    autorada = inp.version
    faltando_specs: tuple[str, ...] = ()

    # ── org specs: replace the {{org.x}} placeholders BEFORE composing, so the text, the rows
    # and the hash are exactly what this org's model receives.
    if inp.org_specs is not None and version.conteudo is not None:
        valores = {k: v for k, v in inp.org_specs.items() if isinstance(v, str)}
        faltam = sorted(
            sp.chave for sp in version.conteudo.specs
            if sp.obrigatoria and not valores.get(sp.chave, "").strip()
        )
        if faltam:
            faltando_specs = tuple(faltam)
            avisos.append(CompileWarning(
                "spec_org_faltando",
                "A organização não preencheu especificações obrigatórias: " + ", ".join(faltam) + ".",
                True,
            ))
        version = _resolver_versao(version, valores)
        inp = replace(inp, version=version)

    cont = version.conteudo
    S = _Strings(cont)
    blocks: list[tuple[str, str, ManifestOrigin, str]] = []  # (chave, titulo, origem, texto)

    # ── duplicate checks (impossible by DB unique constraints; still checked)
    seen_chaves: set[str] = set()
    for s in inp.version.secoes:
        if s.chave in seen_chaves:
            avisos.append(CompileWarning(
                "chave_duplicada", f"A chave de seção '{s.chave}' aparece mais de uma vez.", True,
            ))
        seen_chaves.add(s.chave)
    seen_nomes: set[str] = set()
    for sk in inp.version.skills:
        if sk.nome in seen_nomes:
            avisos.append(CompileWarning(
                "skill_duplicada", f"A skill '{sk.nome}' aparece mais de uma vez.", True,
            ))
        seen_nomes.add(sk.nome)
    refs = sorted(inp.version.skill_refs, key=lambda r: (r.ordem, r.skill_key))
    for r in refs:
        if r.skill_key in seen_nomes:
            avisos.append(CompileWarning(
                "skill_duplicada", f"A skill '{r.skill_key}' aparece mais de uma vez.", True,
            ))
        seen_nomes.add(r.skill_key)

    skills_title = S.peek("compilador.titulo_skills", SKILLS_TITLE)
    knowledge_title = S.peek("compilador.titulo_conhecimento", KNOWLEDGE_TITLE)
    tools_title = S.peek("compilador.titulo_ferramentas", TOOLS_TITLE)
    client_prefix = S.peek("compilador.titulo_cliente", CLIENT_TITLE_PREFIX)

    # ── 1. sections
    secoes = _active_sections(inp.version.secoes, conteudo=cont is not None)
    if not secoes:
        avisos.append(CompileWarning(
            "sem_secoes", "A versão não tem nenhuma seção ativa.", True,
        ))
    reserved = {t.casefold() for t in (skills_title, knowledge_title, tools_title) if t}
    for s in secoes:
        titulo = s.titulo.strip()
        if titulo.casefold() in reserved or (
            client_prefix and titulo.casefold().startswith(client_prefix.casefold())
        ):
            avisos.append(CompileWarning(
                "titulo_reservado",
                f"O título da seção '{s.chave}' ('{titulo}') repete um título gerado automaticamente.",
                False,
            ))
        conteudo = (s.conteudo or "").strip()
        if not conteudo:
            avisos.append(CompileWarning(
                "secao_vazia",
                f"A seção '{s.chave}' está ativa e vazia — ela foi omitida do prompt.",
                True,
            ))
            continue
        blocks.append((
            s.chave, titulo, ManifestOrigin("secao", s.id, "conteudo"), f"# {titulo}\n\n{conteudo}",
        ))

    # ── 1b. qualification standard (static, data-generated; before skills)
    if inp.qualificacao is not None and cont is not None:
        blocks.append((
            "qualificacao", S.peek("compilador.titulo_qualificacao", ""),
            ManifestOrigin("auto", inp.qualificacao.versao_id, "qualificacao"),
            _qualificacao_block(inp.qualificacao, S),
        ))

    # ── 2. skills
    skills = _active_skills(inp.version.skills)
    for sk in skills:
        if not (sk.corpo or "").strip():
            avisos.append(CompileWarning(
                "skill_sem_corpo", f"A skill '{sk.nome}' está ativa e sem corpo.", True,
            ))
    for r in refs:
        if not r.descricao.strip():
            avisos.append(CompileWarning(
                "skill_sem_descricao", f"A skill '{r.skill_key}' fixada da biblioteca está sem descrição.", True,
            ))
    if skills or refs:
        lines = "\n".join(
            [f"- `{sk.nome}` — {sk.descricao.strip()}" for sk in skills]
            + [f"- `{r.skill_key}` — {r.descricao.strip()}" for r in refs]
        )
        blocks.append((
            "skills", skills_title, ManifestOrigin("auto", None, "skills"),
            f"# {S('compilador.titulo_skills', SKILLS_TITLE)}\n\n"
            f"{S('compilador.skills_intro', _SKILLS_INTRO)}\n\n{lines}",
        ))

    # ── 3. knowledge
    knowledge_on = _policy_flag(inp.tool_policy, "knowledge")
    colecoes = _sorted_collections(inp.knowledge) if knowledge_on else []
    if colecoes:
        lines = "\n".join(_collection_line(c, S) for c in colecoes)
        blocks.append((
            "base-de-conhecimento", knowledge_title, ManifestOrigin("auto", None, "conhecimento"),
            f"# {S('compilador.titulo_conhecimento', KNOWLEDGE_TITLE)}\n\n"
            f"{S('compilador.conhecimento_intro', _KNOWLEDGE_INTRO)}\n\n{lines}",
        ))

    # ── 4. tools
    blocks.append((
        "ferramentas", tools_title, ManifestOrigin("auto", None, "tool_policy"),
        _tools_block(
            _policy_flag(inp.tool_policy, "web_search"), knowledge_on, bool(skills) or bool(refs), S,
            cont.ferramentas if cont is not None else (),
        ),
    ))

    # ── 5. client
    if inp.client is not None:
        blocks.append((
            "cliente",
            f"{S('compilador.titulo_cliente', CLIENT_TITLE_PREFIX)}: {inp.client.nome.strip()}",
            ManifestOrigin("auto", inp.client.id, "cliente"),
            _client_block(inp.client, S),
        ))

    # ── content-mode completeness (blocking; CONTEUDO_CODIGOS)
    if cont is not None:
        avisos += _avisos_conteudo(
            inp, cont, S, skills, com_cliente=inp.client is not None, refs=refs, autorada=autorada)

    # ── assemble with exact offsets
    manifest: list[ManifestSection] = []
    pieces: list[str] = []
    cursor = 0
    for i, (chave, titulo, origem, text) in enumerate(blocks):
        text = text.rstrip()
        if i:
            pieces.append("\n\n")
            cursor += 2
        pieces.append(text)
        manifest.append(ManifestSection(
            chave=chave, titulo=titulo, origem=origem, inicio=cursor,
            fim=cursor + len(text), chars=len(text), tokens=estimate_tokens(text),
        ))
        cursor += len(text)
    texto = "".join(pieces).rstrip("\n")
    # The client block is the only dynamic layer here: the cache breakpoint sits right before it.
    estatico = [m for m in manifest if m.origem.tipo != "auto" or m.origem.campo != "cliente"]
    ponto_cache = estatico[-1].fim if estatico else 0
    if cont is not None:
        manifest += _manifest_conteudo(cont)

    tokens = estimate_tokens(texto)
    if tokens > TOKEN_WARNING_THRESHOLD:
        avisos.append(CompileWarning(
            "prompt_extenso",
            f"O prompt compilado tem ~{tokens} tokens (acima de {TOKEN_WARNING_THRESHOLD}).",
            False,
        ))

    # ── on-demand layer (never inside texto)
    sob_demanda: list[OnDemandItem] = []
    for sk in skills:
        corpo = sk.corpo or ""
        sob_demanda.append(OnDemandItem(
            "skill", sk.nome, None, len(corpo), estimate_tokens(corpo), f'abrir_skill("{sk.nome}")',
        ))
        for f in sorted(sk.arquivos, key=lambda f: f.caminho):
            sob_demanda.append(OnDemandItem(
                "arquivo_skill", sk.nome, f.caminho, f.chars, math.ceil(f.chars / 4),
                f'ler_arquivo_skill("{sk.nome}", "{f.caminho}")',
            ))
    for r in refs:
        sob_demanda.append(OnDemandItem(
            "skill", r.skill_key, None, r.corpo_chars, math.ceil(r.corpo_chars / 4), f'abrir_skill("{r.skill_key}")',
        ))
        for caminho, chars in sorted(r.arquivos):
            sob_demanda.append(OnDemandItem(
                "arquivo_skill", r.skill_key, caminho, chars, math.ceil(chars / 4),
                f'ler_arquivo_skill("{r.skill_key}", "{caminho}")',
            ))
    for c in colecoes:
        # The catalog carries counts, not sizes — chars/tokens are not
        # measured at compile time for a collection.
        sob_demanda.append(OnDemandItem(
            "colecao", c.slug, None, 0, 0, f'kb_buscar(colecao="{c.slug}")',
        ))

    hash_ = (
        prompt_hash(texto) if cont is None
        else _hash_of(hash_payload(texto, cont, inp.version, inp.extras, inp.qualificacao))
    )
    return CompiledPrompt(
        texto=texto,
        hash=hash_,
        manifest=manifest,
        tokens_estimados=tokens,
        sob_demanda=sob_demanda,
        avisos=avisos,
        conteudo=cont,
        specs_faltando=faltando_specs,
        ponto_cache=ponto_cache,
    )
