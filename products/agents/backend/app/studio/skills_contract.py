"""The shared-skill runtime contract (Julia v2 CONTRACT D7/D8): the ONLY surface the runtime
(A-RT) and the compiler know about the skill library. Both sides import THIS module; the
library store (``app.stores.skills_biblioteca``) implements it; A-RT may Fake it.

Pure: types and a Protocol, no IO, no content. A skill's text lives in DB rows.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

__all__ = ["SkillRef", "SkillArquivo", "SkillAberta", "SkillsRuntime"]


@dataclass(frozen=True)
class SkillRef:
    """One library skill version pinned to an agent version.

    The first three fields are the contract; the rest feed the compiled index and the
    on-demand listing (the model sees ``descricao`` as the "when to open it" line).
    """

    skill_key: str
    skill_versao_id: UUID
    #: Tool names that refuse until this skill was opened in the thread (D7).
    obrigatoria_para: tuple[str, ...] = ()
    descricao: str = ""
    ordem: int = 0
    corpo_chars: int = 0
    #: ``(caminho, chars)`` of each reference file.
    arquivos: tuple[tuple[str, int], ...] = ()
    #: The ``{{org.chave}}`` keys the pinned version's text uses (index line, body, files) -- so the compiler's
    #: spec-usage check sees them; the body itself stays on-demand and is resolved when opened.
    placeholders: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillArquivo:
    caminho: str
    titulo: str | None
    conteudo: str


@dataclass(frozen=True)
class SkillAberta:
    """What ``abrir_skill`` / ``ler_arquivo_skill`` return: the body and the files."""

    skill_key: str
    skill_versao_id: UUID
    corpo: str
    arquivos: tuple[SkillArquivo, ...] = ()


class SkillsRuntime(Protocol):
    def skill_refs_for(self, version_id: UUID) -> list[SkillRef]:
        """The library pins of an agent version, by ``(ordem, skill_key)``. Empty when none."""
        ...

    def abrir(self, skill_key: str, skill_versao_id: UUID) -> SkillAberta | None:
        """Body + files of the PINNED version (never "the latest"): a published agent version
        always opens exactly what it was judged with. ``None`` when that pin does not exist."""
        ...
