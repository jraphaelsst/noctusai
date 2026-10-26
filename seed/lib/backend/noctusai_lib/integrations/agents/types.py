"""Wire types of the org-specs surface (`GET|PUT /api/studio/agents/{key}/specs`)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class OrgSpecDeclarada:
    """One placeholder the platform definition asks the org for (`{{org.<chave>}}`)."""

    chave: str
    rotulo: str
    descricao: str = ""
    tipo: str = "texto"  # texto | texto_longo
    obrigatoria: bool = True
    exemplo: Optional[str] = None


@dataclass(frozen=True)
class OrgSpecs:
    """What the org sees: the form (declarations), its values and which required ones are missing."""

    agent_key: str
    declaradas: tuple[OrgSpecDeclarada, ...] = ()
    valores: dict[str, str] = field(default_factory=dict)
    faltando: tuple[str, ...] = ()
    version_id: Optional[str] = None
    versao: Optional[int] = None

    def as_dict(self) -> dict[str, Any]:
        """The same JSON shape agents answers (so a product proxy can pass it through untouched)."""
        return {
            "agent_key": self.agent_key,
            "version_id": self.version_id,
            "versao": self.versao,
            "declaradas": [
                {"chave": d.chave, "rotulo": d.rotulo, "descricao": d.descricao, "tipo": d.tipo,
                 "obrigatoria": d.obrigatoria, "exemplo": d.exemplo}
                for d in self.declaradas
            ],
            "valores": [{"chave": k, "valor": v} for k, v in self.valores.items()],
            "faltando": list(self.faltando),
        }
