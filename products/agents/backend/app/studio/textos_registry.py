"""The REGISTRY of the system texts a content-mode agent must carry (Julia v2, CONTRACT §2.2).

KEYS ONLY. Not one human-readable word lives here (D2/D3): the text of every key is a row of
``agents.agent_version_textos`` — versioned with the agent version, covered by its
``compiled_hash``, edited in Studio. The registry says which keys exist, which are REQUIRED,
which ``{placeholder}`` names the runtime may fill into each, and when a key applies:

* ``aplica_a`` — ``todas`` (every agent) · ``canal`` (turns driven by a channel transport,
  ``agents.owner_product`` set) · ``runtime`` (the in-app chat runtime);
* ``condicao`` — a compile-time condition under which the key is needed: ``web_search`` /
  ``!web_search`` / ``knowledge`` / ``!knowledge`` (the version's ``tool_policy`` flags),
  ``skills`` (the version has ≥ 1 active skill), ``cliente`` (a client is in focus).

A required, applicable key that is missing or blank makes the compile carry a BLOCKING
``texto_ausente`` warning and publish answers 409 ``conteudo_incompleto``. There is NO default
string anywhere: an empty row is a hole the author must fill, never something code papers over.

Other slices add their keys here (one dict entry each, additive): A-RT ``contexto.*`` /
``credito.*`` / ``ferramenta.resultado.*`` / ``runtime.*`` / ``resumo.*`` / ``decisao.*`` /
``reengajamento.*``; A-EVAL ``eval.*``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "APLICA_A",
    "CONDICOES",
    "CHAVE_RE",
    "TextoSpec",
    "TEXTOS",
    "chaves_exigidas",
    "placeholders_de",
]

APLICA_A = ("todas", "canal", "runtime")
CONDICOES = ("web_search", "!web_search", "knowledge", "!knowledge", "skills", "cliente", "qualificacao")
#: Same pattern as the migration 031 CHECK on ``agent_version_textos.chave``.
CHAVE_RE = re.compile(r"^[a-z0-9]+(\.[a-z0-9_]+)+$")

#: ``{nome}`` — a runtime placeholder (single brace). ``{{org.chave}}`` (an org spec) is NOT one
#: and is stripped before the scan (see :func:`placeholders_de`).
_ORG_PLACEHOLDER = re.compile(r"\{\{\s*org\.[a-z][a-z0-9_]*\s*\}\}")
_PLACEHOLDER = re.compile(r"(?<!\{)\{([a-z][a-z0-9_]*)\}(?!\})")


@dataclass(frozen=True)
class TextoSpec:
    categoria: str
    obrigatoria: bool = True
    placeholders_permitidos: tuple[str, ...] = ()
    aplica_a: str = "todas"
    condicao: str | None = None
    #: Platform-locked (``fixo_plataforma``): shown READ-ONLY to org admins; org specs may not
    #: contradict it (AI disclosure, opt-out, human escalation, real-estate-only scope).
    fixo_plataforma: bool = False

    def __post_init__(self) -> None:
        if self.aplica_a not in APLICA_A:
            raise ValueError(f"aplica_a must be one of {APLICA_A}")
        if self.condicao is not None and self.condicao not in CONDICOES:
            raise ValueError(f"condicao must be one of {CONDICOES}")


def _compilador(categoria: str = "compilador", **kw) -> TextoSpec:
    return TextoSpec(categoria=categoria, **kw)


TEXTOS: dict[str, TextoSpec] = {
    # compiler-owned layout strings (CONTRACT §2.1 row 4) -------------------------------
    "compilador.titulo_skills": _compilador(condicao="skills"),
    "compilador.skills_intro": _compilador(condicao="skills"),
    "compilador.titulo_conhecimento": _compilador(condicao="knowledge"),
    "compilador.conhecimento_intro": _compilador(condicao="knowledge"),
    "compilador.unidade_documento": _compilador(condicao="knowledge"),
    "compilador.unidade_documentos": _compilador(condicao="knowledge"),
    "compilador.titulo_ferramentas": _compilador(),
    "compilador.ferramenta_linha.web_ativada": _compilador(condicao="web_search"),
    "compilador.ferramenta_linha.web_desativada": _compilador(condicao="!web_search"),
    "compilador.ferramenta_linha.conhecimento_ativada": _compilador(condicao="knowledge"),
    "compilador.ferramenta_linha.conhecimento_desativada": _compilador(condicao="!knowledge"),
    "compilador.ferramenta_linha.skills_ativada": _compilador(condicao="skills"),
    # the "Qualificação" block generated from the pinned standard's rows
    **{
        f"compilador.{k}": _compilador(condicao="qualificacao")
        for k in (
            "titulo_qualificacao", "qualificacao_intro", "qualificacao_rotulo_criterios",
            "qualificacao_rotulo_opcoes", "qualificacao_rotulo_estagios", "qualificacao_rotulo_minimo",
            "qualificacao_rotulo_identidade",
        )
    },
    "compilador.titulo_cliente": _compilador(condicao="cliente"),
    **{
        f"compilador.cliente_rotulo.{tipo}": _compilador(condicao="cliente")
        for tipo in (
            "marca", "publico", "posicionamento", "trava", "decisao", "aprendizado",
            "evidencia", "nota",
        )
    },
}


def chaves_exigidas(
    *, tool_policy: dict, tem_skills: bool, com_cliente: bool, canal: bool, com_qualificacao: bool = False,
    registro: dict[str, TextoSpec] | None = None,
) -> set[str]:
    """The registry keys that are REQUIRED for this compile: ``obrigatoria``, applicable to the
    agent's kind (``canal`` vs in-app) and whose ``condicao`` holds."""
    registro = TEXTOS if registro is None else registro
    web = bool(tool_policy.get("web_search", False))
    kb = bool(tool_policy.get("knowledge", False))
    ativas = {
        "web_search": web, "!web_search": not web,
        "knowledge": kb, "!knowledge": not kb,
        "skills": tem_skills, "cliente": com_cliente, "qualificacao": com_qualificacao,
    }
    out: set[str] = set()
    for chave, spec in registro.items():
        if not spec.obrigatoria:
            continue
        if spec.aplica_a == "canal" and not canal:
            continue
        if spec.aplica_a == "runtime" and canal:
            continue
        if spec.condicao is not None and not ativas[spec.condicao]:
            continue
        out.add(chave)
    return out


def placeholders_de(texto: str) -> set[str]:
    """The runtime ``{nome}`` placeholders a text uses (org-spec ``{{org.x}}`` excluded)."""
    return set(_PLACEHOLDER.findall(_ORG_PLACEHOLDER.sub("", texto or "")))
