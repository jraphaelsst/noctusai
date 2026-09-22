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
"""
from __future__ import annotations

import hashlib
import math
from typing import Any

from app.studio.models import (
    ClientBundle,
    CollectionSummary,
    CompiledPrompt,
    CompileInput,
    CompileWarning,
    ManifestOrigin,
    ManifestSection,
    OnDemandItem,
    SectionData,
    SkillData,
)

__all__ = [
    "AUTO_TITLES",
    "CLIENT_ENTRY_ORDER",
    "CLIENT_ENTRY_LABELS",
    "TOKEN_WARNING_THRESHOLD",
    "compile_prompt",
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


def estimate_tokens(text: str) -> int:
    """§C: ``ceil(len(texto) / 4)``."""
    return math.ceil(len(text) / 4)


def prompt_hash(texto: str) -> str:
    """§C: ``"sha256:" + hexdigest(texto.encode("utf-8"))``."""
    return "sha256:" + hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _policy_flag(policy: dict[str, Any], key: str) -> bool:
    return bool(policy.get(key, False))


def _active_sections(secoes) -> list[SectionData]:
    return sorted((s for s in secoes if s.ativo), key=lambda s: (s.ordem, s.chave))


def _active_skills(skills) -> list[SkillData]:
    return sorted((s for s in skills if s.ativo), key=lambda s: (s.ordem, s.nome))


def _sorted_collections(knowledge) -> list[CollectionSummary]:
    return sorted(knowledge, key=lambda c: (c.ordem, c.slug))


def _collection_line(c: CollectionSummary) -> str:
    tag = f" [{c.tag}]" if c.tag else ""
    desc = f": {c.descricao.strip()}" if c.descricao and c.descricao.strip() else ""
    noun = "documento" if c.doc_count == 1 else "documentos"
    return f"- `{c.slug}`{tag} — {c.nome}{desc} ({c.doc_count} {noun})"


def _tools_block(web: bool, knowledge: bool, has_skills: bool) -> str:
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
    return f"# {TOOLS_TITLE}\n\n" + "\n".join(lines)


def _client_block(client: ClientBundle) -> str:
    parts = [f"# {CLIENT_TITLE_PREFIX}: {client.nome.strip()}"]
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
        parts.append(f"## {CLIENT_ENTRY_LABELS[tipo]}\n" + "\n".join(lines))
    return "\n\n".join(parts)


def compile_prompt(inp: CompileInput) -> CompiledPrompt:
    """Compile a version (+ knowledge catalog, + optional client) into the
    master prompt. Pure, deterministic, no IO."""
    avisos: list[CompileWarning] = []
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

    # ── 1. sections
    secoes = _active_sections(inp.version.secoes)
    if not secoes:
        avisos.append(CompileWarning(
            "sem_secoes", "A versão não tem nenhuma seção ativa.", True,
        ))
    reserved = {t.casefold() for t in AUTO_TITLES}
    for s in secoes:
        titulo = s.titulo.strip()
        if titulo.casefold() in reserved or titulo.casefold().startswith(CLIENT_TITLE_PREFIX.casefold()):
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

    # ── 2. skills
    skills = _active_skills(inp.version.skills)
    for sk in skills:
        if not (sk.corpo or "").strip():
            avisos.append(CompileWarning(
                "skill_sem_corpo", f"A skill '{sk.nome}' está ativa e sem corpo.", True,
            ))
    if skills:
        lines = "\n".join(f"- `{sk.nome}` — {sk.descricao.strip()}" for sk in skills)
        blocks.append((
            "skills", SKILLS_TITLE, ManifestOrigin("auto", None, "skills"),
            f"# {SKILLS_TITLE}\n\n{_SKILLS_INTRO}\n\n{lines}",
        ))

    # ── 3. knowledge
    knowledge_on = _policy_flag(inp.tool_policy, "knowledge")
    colecoes = _sorted_collections(inp.knowledge) if knowledge_on else []
    if colecoes:
        lines = "\n".join(_collection_line(c) for c in colecoes)
        blocks.append((
            "base-de-conhecimento", KNOWLEDGE_TITLE, ManifestOrigin("auto", None, "conhecimento"),
            f"# {KNOWLEDGE_TITLE}\n\n{_KNOWLEDGE_INTRO}\n\n{lines}",
        ))

    # ── 4. tools
    blocks.append((
        "ferramentas", TOOLS_TITLE, ManifestOrigin("auto", None, "tool_policy"),
        _tools_block(_policy_flag(inp.tool_policy, "web_search"), knowledge_on, bool(skills)),
    ))

    # ── 5. client
    if inp.client is not None:
        blocks.append((
            "cliente",
            f"{CLIENT_TITLE_PREFIX}: {inp.client.nome.strip()}",
            ManifestOrigin("auto", inp.client.id, "cliente"),
            _client_block(inp.client),
        ))

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
    for c in colecoes:
        # The catalog carries counts, not sizes — chars/tokens are not
        # measured at compile time for a collection.
        sob_demanda.append(OnDemandItem(
            "colecao", c.slug, None, 0, 0, f'kb_buscar(colecao="{c.slug}")',
        ))

    return CompiledPrompt(
        texto=texto,
        hash=prompt_hash(texto),
        manifest=manifest,
        tokens_estimados=tokens,
        sob_demanda=sob_demanda,
        avisos=avisos,
    )
