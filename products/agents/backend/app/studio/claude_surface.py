"""The Claude Code surface of a dev agent (Agent Packages §C2/§C3, §M) — ONE renderer for both sources.

``agent_package_build`` (git-source packages, A1) and the publish of a DB-source agent (A11, §M2) both render the
``.claude/agents/<key>.md`` file through these functions, so the two surfaces can never word the adapter differently.
Stdlib only: the MCP build loads this module by path (``_load_studio``) without the agents app's dependencies.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

#: §M3: the line every DB-source mirror opens its body with (the offline keeper finds the mirror by it).
DB_MIRROR_MARKER = "<!-- GENERATED from Agents Studio (the DB is the source)"


def adapter_block(key: str, idioma: str) -> str:
    """The ONLY surface-specific text (C2), rendered in the package language.

    The mapping sentence translates the Studio tool names that the compiled prompt mentions
    (`abrir_skill`, `kb_buscar`, …) into Claude Code actions — without it those names would be
    dangling references on this surface.
    """
    base = f"agents/{key}"
    if idioma.lower().startswith("pt"):
        return (
            "# Superfície: Claude Code\n\n"
            f"- Skills: `{base}/skills/<nome>/SKILL.md`; os arquivos de referência ficam ao lado "
            f"(`{base}/skills/<nome>/references/`).\n"
            f"- Conhecimento: `{base}/knowledge/<colecao>/<slug>.md`.\n"
            f"- Aprendizados: `{base}/LEARNINGS.md` (as linhas mais recentes prevalecem).\n"
            "- Todos os caminhos são relativos à raiz do repositório.\n"
            "- Contexto do projeto = o próprio repositório.\n"
            "- Equivalências: onde o prompt diz `abrir_skill` / `ler_arquivo_skill`, leia o arquivo da skill "
            "(ou de referência) com `Read`; onde diz `kb_buscar` / `kb_ler`, procure com `Grep`/`Glob` e leia "
            "o documento com `Read`, citando a tag da coleção."
        )
    return (
        "# Surface: Claude Code\n\n"
        f"- Skills: `{base}/skills/<name>/SKILL.md`; reference files sit beside it "
        f"(`{base}/skills/<name>/references/`).\n"
        f"- Knowledge: `{base}/knowledge/<collection>/<slug>.md`.\n"
        f"- Learnings: `{base}/LEARNINGS.md` (newest rows win).\n"
        "- All paths are relative to the repository root.\n"
        "- Project context = the repository itself.\n"
        "- Equivalences: where the prompt says `abrir_skill` / `ler_arquivo_skill`, read the skill (or reference) "
        "file with `Read`; where it says `kb_buscar` / `kb_ler`, search with `Grep`/`Glob` and read the document "
        "with `Read`, citing the collection tag."
    )


def surface_pointer(idioma: str) -> str:
    """One line at the TOP of the Claude Code file so the reader meets the surface mapping before the
    Studio tool names in the compiled prompt (live-test finding, 2026-10-03)."""
    if idioma.lower().startswith("pt"):
        return "> Claude Code: antes de tudo, leia a seção “Superfície: Claude Code” no fim deste prompt (caminhos e equivalências de ferramentas).\n\n"
    return "> Claude Code: first read the “Surface: Claude Code” section at the end of this prompt (paths and tool equivalences).\n\n"


def mirror_body(key: str, idioma: str, compiled_text: str) -> str:
    """The body below the generated header: surface pointer + compiled prompt + adapter (identical to a package)."""
    return surface_pointer(idioma) + compiled_text.rstrip("\n") + "\n\n" + adapter_block(key, idioma) + "\n"


def body_hash(body: str) -> str:
    """§M3 ``compiled_hash``: sha256 of the body below the header, so a hand edit anywhere in it is detectable."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def db_mirror_markdown(
    *, key: str, descricao: str, idioma: str, compiled_text: str, tools: Iterable[str], model: str | None,
    owns_kb: Iterable[str], versao: str, version_id: str,
) -> str:
    """§M2/§M3: the ``.claude/agents/<key>.md`` of a DB-source agent. The frontmatter carries ``studio:`` (what the
    offline keeper and the pre-push check compare against) and the harness fields (``tools``, ``model``,
    ``owns_kb``); the body is exactly :func:`mirror_body`."""
    body = mirror_body(key, idioma, compiled_text)
    lines = [
        "---",
        f"name: {key}",
        f"description: {json.dumps(descricao, ensure_ascii=False)}",
        f"tools: {', '.join(tools)}",
    ]
    if model:
        lines.append(f"model: {model}")
    owns = list(owns_kb)
    if owns:
        lines.append("owns_kb:")
        lines += [f"  - {o}" for o in owns]
    lines += [
        "studio:",
        f"  key: {key}",
        f"  versao: {versao}",
        f"  version_id: {version_id}",
        f"  compiled_hash: {body_hash(body)}",
        "---",
        f"{DB_MIRROR_MARKER} — edit in the Studio, publish, then noctus.dev.agent_export key={key}; never by hand -->",
    ]
    return "\n".join(lines) + "\n" + body


def split_db_mirror(text: str) -> tuple[dict[str, Any], str] | None:
    """Parse a mirror back: ``({key, versao, version_id, compiled_hash}, body)``, or ``None`` when ``text`` is not a
    DB-source mirror (no ``studio:`` block / no marker line). Line-based on purpose: the frontmatter is written by
    :func:`db_mirror_markdown` only."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    fm, rest = text[4:end].split("\n"), text[end + 5:]
    studio: dict[str, Any] = {}
    inside = False
    for line in fm:
        if line == "studio:":
            inside = True
            continue
        if inside and line.startswith("  ") and ":" in line:
            k, _, v = line.strip().partition(":")
            studio[k.strip()] = v.strip()
        elif inside:
            inside = False
    if not studio or not rest.startswith(DB_MIRROR_MARKER):
        return None
    nl = rest.find("\n")
    return studio, rest[nl + 1:] if nl >= 0 else ""
