"""The profissão vocabulary the qualificação is allowed to print.

WHY A VOCABULARY HERE (AND NOT IN THE SEED)
-------------------------------------------
The seed's `noctusai_lib.integrations.documents.profession` is deliberately
LABEL-anchored, never vocabulary-driven: it reads whatever sits after a
`PROFISSÃO:` label, because a document's profissão is open text. That is the
right rule for READING. Printing is different: the contract repeats the
stored value verbatim in a legal qualification, so a misread or a typo
("aposentanda" — not a word; the deed meant "aposentada") goes straight into
the deed. This module is the render-side guard: a stored profissão the
vocabulary does not recognise becomes a readiness `falta`
(`derivacao._partes`) so a human fixes it — it is NEVER silently rewritten.

RECOGNISED =
- the whole value is a known profissão (`_PROFISSOES`), or
- its FIRST word is a known head noun that takes a free complement
  ("engenheiro civil", "analista de sistemas", "gerente comercial",
  "técnico em enfermagem") — `_NUCLEOS`.

Both sets hold masculine AND feminine forms; comparison is accent- and
case-insensitive. Add a word here when a real, correctly-spelled profissão
is flagged — the flag is the mechanism that surfaces it.
"""
from __future__ import annotations

import re
from typing import Optional

from noctusai_lib.primitives.accents import fold_accents_ascii


def _chave(valor: str) -> str:
    sem_acento = fold_accents_ascii(valor)
    return re.sub(r"\s+", " ", sem_acento.strip().lower())


#: Whole-value profissões (masc + fem), as the signed corpus and common
#: Brazilian qualification wording write them.
_PROFISSOES_BRUTAS: tuple[str, ...] = (
    "administrador", "administradora", "administrador de empresas", "administradora de empresas",
    "advogado", "advogada", "aeronauta", "agricultor", "agricultora", "agronomo", "agronoma",
    "aposentado", "aposentada", "arquiteto", "arquiteta", "artesao", "artesa", "artista",
    "atleta", "atleta profissional", "jogador de futebol", "jogadora de futebol",
    "autonomo", "autonoma", "ator", "atriz", "atuario", "atuaria", "aviador", "aviadora",
    "bancario", "bancaria", "biologo", "biologa", "biomedico", "biomedica", "bombeiro", "bombeira",
    "cabeleireiro", "cabeleireira", "comerciante", "comerciario", "comerciaria", "comissario de bordo",
    "comissaria de bordo", "contador", "contadora", "corretor", "corretora",
    "corretor de imoveis", "corretora de imoveis", "corretor de seguros", "corretora de seguros",
    "costureiro", "costureira", "cozinheiro", "cozinheira", "dentista", "cirurgiao-dentista",
    "cirurgia-dentista", "desembargador", "desembargadora", "designer", "despachante",
    "do lar", "economista", "economiario", "economiaria", "educador", "educadora", "eletricista",
    "empresario", "empresaria", "empreendedor", "empreendedora", "enfermeiro", "enfermeira",
    "escritor", "escritora", "estudante", "estagiario", "estagiaria", "estatistico", "estatistica",
    "esteticista", "farmaceutico", "farmaceutica", "fisico", "fisica", "fisioterapeuta",
    "fonoaudiologo", "fonoaudiologa", "fotografo", "fotografa", "funcionario publico",
    "funcionaria publica", "geologo", "geologa", "jornalista", "juiz", "juiza", "marceneiro",
    "marceneira", "medico", "medica", "medico veterinario", "medica veterinaria", "mecanico",
    "mecanica", "militar", "motorista", "musico", "musica", "nutricionista", "odontologo",
    "odontologa", "pedagogo", "pedagoga", "pedreiro", "pensionista", "piloto", "pintor", "pintora",
    "policial", "policial civil", "policial militar", "procurador", "procuradora", "produtor",
    "produtora", "profissional liberal", "programador", "programadora", "promotor", "promotora",
    "promotor de justica", "promotora de justica", "psicologo", "psicologa", "psicanalista",
    "psiquiatra", "publicitario", "publicitaria", "quimico", "quimica", "radialista",
    "recepcionista", "relacoes publicas", "secretario", "secretaria", "servidor publico",
    "servidora publica", "sociologo", "sociologa", "socio", "socia", "tabeliao", "tabelia",
    "tecnologo", "tecnologa", "terapeuta", "terapeuta ocupacional", "tradutor", "tradutora",
    "vendedor", "vendedora", "veterinario", "veterinaria", "zootecnista",
)

#: Head nouns that take a free complement — the profissão is recognised when
#: its FIRST word is one of these ("engenheiro civil", "analista de sistemas").
_NUCLEOS_BRUTOS: tuple[str, ...] = (
    "agente", "analista", "assessor", "assessora", "assistente", "atendente", "auditor", "auditora",
    "auxiliar", "bacharel", "chefe", "consultor", "consultora", "coordenador", "coordenadora",
    "delegado", "delegada", "desenvolvedor", "desenvolvedora", "diretor", "diretora", "docente",
    "engenheiro", "engenheira", "especialista", "executivo", "executiva", "fiscal", "gerente",
    "gestor", "gestora", "inspetor", "inspetora", "instrutor", "instrutora", "medico", "medica",
    "operador", "operadora", "perito", "perita", "pesquisador", "pesquisadora", "presidente",
    "professor", "professora", "representante", "superintendente", "supervisor", "supervisora",
    "tecnico", "tecnica", "vice-presidente",
)

_PROFISSOES = frozenset(_chave(p) for p in _PROFISSOES_BRUTAS)
_NUCLEOS = frozenset(_chave(p) for p in _NUCLEOS_BRUTOS)


def reconhecida(valor: Optional[str]) -> bool:
    """True when `valor` is a profissão the qualificação may print as stored.
    An empty value is not judged here (its absence is its own aviso,
    `PARTE_SEM_PROFISSAO`) — callers only ask about a non-blank value."""
    chave = _chave(valor or "")
    if not chave:
        return True
    if chave in _PROFISSOES:
        return True
    primeira = chave.split(" ", 1)[0]
    return primeira in _NUCLEOS


__all__ = ["reconhecida"]
