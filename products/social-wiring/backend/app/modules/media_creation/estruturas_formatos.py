"""Closed vocabularies of the Estruturas library + the formato mapping (estruturas-contract.md sections 3.1, 3.3).

ONE home for every enum the ``cs_estruturas`` family stores, so the migration CHECKs, the request schemas and the
service all derive from the same tuples (a test pins the migration text to these).

The name ``estrutura`` is taken by the roteiro *beat order* (``cs_roteiros.estrutura`` = ``cta_inicio | cta_final``);
nothing here touches it (contract section 0.6): the library entity is "Estrutura (library)", its fields are
``estrutura_ids`` / ``estruturas...``.
"""
from __future__ import annotations

from typing import Optional

#: What an Estrutura (and, from M3, a roteiro) is a script FOR. ``stories`` blocks mean frames, ``carrossel``
#: slides, ``post`` on-screen text, ``reels`` seconds.
FORMATOS: tuple[str, ...] = ("reels", "carrossel", "stories", "post")
OBJETIVOS: tuple[str, ...] = ("alcance", "autoridade", "conexao", "venda")
MAX_OBJETIVOS = len(OBJETIVOS)
STATUS: tuple[str, ...] = ("rascunho", "ativa", "arquivada")
ORIGENS: tuple[str, ...] = ("manual", "import_corestudio", "import_maquina", "viral_auto")
#: The origem of an AI-derived draft (the EST-5 auto-draft). Every role is told an Estrutura is AI-generated
#: (`gerada_por_ia`, the legal attribution label), while the raw `origem` stays admin-only.
ORIGEM_GERADA_POR_IA = "viral_auto"

#: Per-field provenance (DC2). ``fonte`` = typed by the source system; ``referencia`` = filled by the owner's
#: reference dataset; ``ia_sugerido`` = filled by the app's AI (auto-draft / "a partir do video" only, NEVER the
#: import); ``admin`` = an admin typed or confirmed it. ``referencia`` and ``ia_sugerido`` are PENDING review.
PROVENIENCIAS: tuple[str, ...] = ("fonte", "referencia", "ia_sugerido", "admin")
PROVENIENCIAS_PENDENTES: tuple[str, ...] = ("referencia", "ia_sugerido")

ATOR_TIPOS: tuple[str, ...] = ("admin", "sistema_import", "sistema_ia")

EVENTO_TIPOS: tuple[str, ...] = (
    "criada", "criada_automatica", "importada", "atualizada_import", "ia_preenchida", "campo_editado",
    "campo_confirmado", "bloco_adicionado", "bloco_removido", "blocos_reordenados", "publicada", "arquivada",
    "restaurada", "excluida",
)
TIPO_EVENTO_TIPOS: tuple[str, ...] = ("criado", "editado", "ativado", "desativado", "excluido")

#: The block-level fields that carry a provenance column (``<campo>_origem``).
BLOCO_CAMPOS_COM_ORIGEM: tuple[str, ...] = ("nome", "tipo", "tempo", "instrucao")
#: The estrutura-level fields that carry one.
ESTRUTURA_CAMPOS_COM_ORIGEM: tuple[str, ...] = ("formula_headline", "formato", "objetivos")
#: Block fields an admin can edit / the ``campo`` grammar of an event: ``bloco.<id>.<campo>``.
BLOCO_CAMPOS_EDITAVEIS: tuple[str, ...] = ("nome", "tipo", "tempo", "instrucao", "nota", "repeticoes")

#: Limits (mirrored by the migration CHECKs).
FORMULA_MAX = 1000
BLOCOS_MIN = 1
BLOCOS_MAX = 60
BLOCO_NOME_MAX = 120
BLOCO_TEMPO_MAX = 40
BLOCO_INSTRUCAO_MAX = 2000
BLOCO_NOTA_MAX = 600
BLOCO_REPETICOES_MAX = 20
TIPO_NOME_MAX = 80
TIPO_INSTRUCAO_MAX = 600

#: ``cs_posts.formato`` vocabulary (S1: ``reel | carrossel | story | feed``) for each Estrutura / roteiro formato.
#: The card's ``formato`` CHECK is relaxed by M3 from ``IN ('reel')``.
FORMATO_PARA_POST: dict[str, str] = {
    "reels": "reel",
    "carrossel": "carrossel",
    "stories": "story",
    "post": "feed",
}
POST_PARA_FORMATO: dict[str, str] = {v: k for k, v in FORMATO_PARA_POST.items()}


def formato_do_post(formato: Optional[str]) -> Optional[str]:
    """The card's ``cs_posts.formato`` for an Estrutura / roteiro ``formato`` (None stays None).

    Raises ``ValueError`` on a value outside :data:`FORMATOS`: a bad formato is a bug upstream, never mapped silently.
    """
    if formato is None:
        return None
    try:
        return FORMATO_PARA_POST[formato]
    except KeyError:
        raise ValueError(f"formato desconhecido: {formato!r}; esperado um de {FORMATOS}") from None


def formato_da_estrutura(post_formato: Optional[str]) -> Optional[str]:
    """Inverse of :func:`formato_do_post` (a legacy ``cs_posts.formato`` of ``'reel'`` is ``reels``)."""
    if post_formato is None:
        return None
    try:
        return POST_PARA_FORMATO[post_formato]
    except KeyError:
        raise ValueError(f"formato de post desconhecido: {post_formato!r}; esperado um de {tuple(POST_PARA_FORMATO)}") from None


__all__ = [
    "ATOR_TIPOS",
    "BLOCOS_MAX",
    "BLOCOS_MIN",
    "BLOCO_CAMPOS_COM_ORIGEM",
    "BLOCO_CAMPOS_EDITAVEIS",
    "BLOCO_INSTRUCAO_MAX",
    "BLOCO_NOME_MAX",
    "BLOCO_NOTA_MAX",
    "BLOCO_REPETICOES_MAX",
    "BLOCO_TEMPO_MAX",
    "ESTRUTURA_CAMPOS_COM_ORIGEM",
    "EVENTO_TIPOS",
    "FORMATOS",
    "FORMATO_PARA_POST",
    "FORMULA_MAX",
    "MAX_OBJETIVOS",
    "OBJETIVOS",
    "ORIGENS",
    "POST_PARA_FORMATO",
    "PROVENIENCIAS",
    "PROVENIENCIAS_PENDENTES",
    "STATUS",
    "TIPO_EVENTO_TIPOS",
    "TIPO_INSTRUCAO_MAX",
    "TIPO_NOME_MAX",
    "formato_da_estrutura",
    "formato_do_post",
]
