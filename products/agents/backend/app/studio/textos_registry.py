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

A-RT's keys (the channel runtime: ``contexto.*`` · ``credito.*`` · ``reengajamento.*`` ·
``ferramenta.resultado.*`` · ``ferramenta.handoff.*`` · ``historico.*`` · ``runtime.*`` · ``resumo.*`` ·
``decisao.*`` · ``conformidade.*`` · ``escalonamento.*``) are all ``aplica_a="canal"`` and required, except
the two ``runtime`` texts whose absence IS the defined behaviour (a channel turn that exhausts its tool loop,
or stops on its safety budget, answers with SILENCE unless the owner wrote a text). A-EVAL adds ``eval.*``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "CODIGOS_RECUSA",
    "MOTIVOS_HANDOFF",
    "MOTIVOS_HANDOFF_SERVIDOR",
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


#: Every machine refusal code a channel tool can answer with. The WORDING of each is the row
#: ``ferramenta.resultado.recusa.<codigo>``; a tool result is ``{"ok": false, "codigo": ..., "mensagem": <row>}``.
CODIGOS_RECUSA: tuple[str, ...] = (
    "skill_nao_aberta", "skill_inexistente", "arquivo_inexistente",
    "sem_itens", "itens_demais", "versao_nao_publicada", "fonte_invalida", "criterio_repetido",
    "criterio_derivado", "criterio_desconhecido", "nao_coletar", "fora_do_escopo", "valor_invalido",
    "opcao_invalida", "usar_identificacao",
    "trecho_ausente", "trecho_longo", "trecho_curto", "trecho_nao_confere",
    "evento_invalido", "origem_invalida", "codigo_invalido", "motivo_longo", "lote_invalido",
    "imovel_ja_oferecido", "imovel_nao_oferecido",
    "estagio_nao_conclusivo", "nao_pode_ofertar", "limite_ofertas", "sem_codigo_campanha",
    "identificacao_nao_devida", "campo_desconhecido", "valor_nao_confere", "identificacao_indisponivel",
    "credito_inativo", "limite_recusas", "indisponivel", "motivo_texto_ausente",
    # guardrails B6: consent / opt-out need the lead's words from THIS batch; per-turn tool-call caps
    "consentimento_sem_evidencia", "opt_out_sem_evidencia", "limite_ferramentas",
)
#: ``motivo_codigo`` values the MODEL may pass to ``handoff`` (labels live in the tool row's ``parametros``).
MOTIVOS_HANDOFF: tuple[str, ...] = (
    "pedido_humano", "reclamacao", "assunto_sensivel", "parceria", "fora_do_escopo", "outro",
    "seguranca", "direito_titular",
)
#: Values only the SERVER writes (deterministic escalation / safety stops).
MOTIVOS_HANDOFF_SERVIDOR: tuple[str, ...] = (
    "falhas_repetidas", "conformidade", "qualificacao_concluida", "limite_recusas",
)


def _canal(categoria: str, *placeholders: str, obrigatoria: bool = True) -> TextoSpec:
    return TextoSpec(
        categoria=categoria, obrigatoria=obrigatoria, placeholders_permitidos=tuple(placeholders),
        aplica_a="canal",
    )


TEXTOS.update({
    # the second system message (state + dossier) ------------------------------------------
    **{f"contexto.{k}": _canal("contexto") for k in (
        "titulo_estado", "rotulo_data_hora", "rotulo_encerrado", "sim", "nao", "rotulo_atendente",
        "rotulo_origem", "rotulo_campanha", "titulo_dossie", "dossie_vazio", "aviso_valores_cliente",
        "rotulo_estagio", "rotulo_score", "rotulo_faltando", "rotulo_oferecidos", "rotulo_gostou",
        "titulo_handoff", "titulo_credito", "titulo_reengajamento",
    )},
    **{f"credito.{k}": _canal("credito") for k in ("pedir", "consentiu", "recusou")},
    "reengajamento.minutos": _canal("reengajamento"),
    "reengajamento.horas": _canal("reengajamento"),
    "reengajamento.regua": _canal("reengajamento"),
    "reengajamento.texto_base": _canal("reengajamento", "texto_base"),
    # history of a shared thread: other agents / humans / events travel as platform ENVELOPES (no label text);
    # only the media object a lead message carried needs a label (guardrails B2) -----------------
    "historico.rotulo_midia": _canal("historico"),
    "historico.rotulo_truncado": _canal("historico"),
    # provenance: the section that tells the model which envelopes are platform data, and the honeytoken line
    # appended to the system prompt (guardrails B2/B7) ---------------------------------------------------
    "contexto.titulo_proveniencia": _canal("contexto"),
    "contexto.aviso_proveniencia": _canal("contexto", "tag"),
    "seguranca.marcador_interno": _canal("seguranca", "marcador"),
    # tool results the model reads ------------------------------------------------------------
    "ferramenta.resultado.registrado": _canal("ferramenta"),
    "ferramenta.resultado.argumentos_invalidos": _canal("ferramenta", "motivo"),
    "ferramenta.resultado.desconhecida": _canal("ferramenta"),
    "ferramenta.resultado.handoff": _canal("ferramenta"),
    "ferramenta.resultado.encerrado": _canal("ferramenta"),
    "ferramenta.resultado.encerrado_opt_out": _canal("ferramenta"),
    "ferramenta.resultado.concluido": _canal("ferramenta"),
    "ferramenta.resultado.solicitacao_registrada": _canal("ferramenta"),
    "ferramenta.handoff.resumo_titular": _canal("ferramenta", "tipo"),
    "ferramenta.handoff.motivo_padrao": _canal("ferramenta"),
    #: replaces a lead-influenced tool argument that reproduced the prompt (spec B3.6)
    "ferramenta.campo_removido": _canal("ferramenta"),
    "ferramenta.handoff.resumo_conclusao": _canal("ferramenta", "estagio", "score"),
    **{
        f"ferramenta.resultado.recusa.{c}": _canal("ferramenta", *(("skill",) if c == "skill_nao_aberta" else ()))
        for c in CODIGOS_RECUSA
    },
    # runtime ----------------------------------------------------------------------------------
    "runtime.ferramenta_falhou": _canal("runtime"),
    "runtime.resposta_fallback": _canal("runtime", obrigatoria=False),
    "runtime.parada_segura": _canal("runtime", obrigatoria=False),
    # extraction calls (episode summary + transport decisions) -------------------------------
    "resumo.sistema": _canal("resumo"),
    "resumo.rotulo_cliente": _canal("resumo"),
    "resumo.rotulo_atendente": _canal("resumo"),
    "resumo.rotulo_conversa": _canal("resumo"),
    "resumo.sem_mensagens": _canal("resumo"),
    "decisao.sistema": _canal("decisao", "regra"),
    "decisao.rotulo_opcoes": _canal("decisao"),
    "decisao.rotulo_dados": _canal("decisao"),
    "decisao.sem_dados": _canal("decisao"),
    # conformance: the corrective system message of a blocked reply + the owner's hand-off note ----
    **{f"conformidade.correcao.{r}": _canal("conformidade") for r in (
        "imovel_sem_ferramenta", "termina_sem_pergunta", "perfil_citado_sem_registro", "fallback_enviado",
        "pergunta_repetida", "vazamento_prompt",
        "link_nao_permitido", "contato_nao_permitido", "pii_na_resposta", "formato_suspeito", "padroes_proibidos",
    )},
    "conformidade.handoff_resumo": _canal("conformidade", "regra"),
    "escalonamento.resumo": _canal("escalonamento", "motivo_codigo"),
})


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
