"""Value objects of a Diretor de Edição production run. Pure data, no IO.

Everything that crosses a step boundary is a plain JSON dict (the seed ledger stores ``resultado`` as JSON, a worker
restart resumes from it); these dataclasses are the typed face of those dicts, with ``para_dict`` / ``de_dict`` pairs.

Anchors are WORD IDS (``w0..wN``) of the approved script, never seconds (``script-to-media-production.md`` section 2): a
later voice only rewrites word times, nothing else is re-planned.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Optional


def sha256_texto(texto: str) -> str:
    return hashlib.sha256((texto or "").encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Palavra:
    id: str  # "w0", "w1", ...
    texto: str


@dataclass(frozen=True)
class EntradaCongelada:
    """What the approvals froze: the approved headline + roteiro, hashed, tokenised once (the single source of word ids)."""

    org_id: str
    post_id: str
    marca_id: str
    rodada: int
    headline_id: str
    headline: str
    roteiro_id: str
    roteiro_versao: int
    roteiro_sha256: str
    headline_sha256: str
    palavras: tuple[Palavra, ...]

    def para_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["palavras"] = [asdict(p) for p in self.palavras]
        return d

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> "EntradaCongelada":
        return cls(**{**d, "palavras": tuple(Palavra(**p) for p in d["palavras"])})

    def ids(self) -> list[str]:
        return [p.id for p in self.palavras]


@dataclass(frozen=True)
class EstiloRef:
    """Which approved style (the "estilo"/preset) the run uses. ``origem`` says who approved it. The owner's rules: a style
    from a reference is structure/rhythm/layout, never a creator's brand, and a brand's visual identity is NOT a Reel style."""

    id: str
    versao: str
    origem: str  # "aprovado_pelo_dono" | "fake"

    def para_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> "EstiloRef":
        return cls(**d)


@dataclass(frozen=True)
class CenaPlanejada:
    """One planned scene. ``palavra_inicio`` / ``palavra_fim`` are word ids (inclusive). ``texto_na_tela`` strings must be
    literal spans of the script or approved labels (the validator enforces it). ``dados`` is the OPAQUE payload the
    storytelling decision fills (settings, camera, transitions, asset usage...): the skeleton never reads it."""

    id: str
    palavra_inicio: str
    palavra_fim: str
    texto_na_tela: tuple[str, ...] = ()
    intencao: str = ""
    dados: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanoDeCenas:
    planejador: str  # adapter id, e.g. "fake"
    versao: str  # adapter/prompt version: lets approval rate be compared per planner version
    estilo: EstiloRef
    cenas: tuple[CenaPlanejada, ...]
    rotulos_aprovados: tuple[str, ...] = ()  # on-screen labels allowed besides literal pieces of the speech
    custo_usd: Optional[Decimal] = None  # what planning cost (an LLM leg, say); None = not measured, never an estimate

    def para_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["cenas"] = [asdict(c) for c in self.cenas]
        d["custo_usd"] = None if self.custo_usd is None else str(self.custo_usd)
        return d

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> "PlanoDeCenas":
        cenas = tuple(CenaPlanejada(**{**c, "texto_na_tela": tuple(c.get("texto_na_tela") or ())}) for c in d["cenas"])
        custo = d.get("custo_usd")
        return cls(
            d["planejador"], d["versao"], EstiloRef.de_dict(d["estilo"]), cenas, tuple(d.get("rotulos_aprovados") or ()),
            None if custo is None else Decimal(str(custo)),
        )


@dataclass(frozen=True)
class ItemMidia:
    papel: str  # "voz" | "visual" | ... (open vocabulary: the generator decision names its own)
    chave: str  # storage key (never a local path)
    cena_id: Optional[str] = None
    duracao_s: Optional[float] = None


@dataclass(frozen=True)
class MidiaGerada:
    gerador: str
    versao: str
    itens: tuple[ItemMidia, ...]
    sintetico: bool  # True: produced by a Fake -- never reaches a human approval
    request_id: Optional[str] = None
    unidades: dict[str, Any] = field(default_factory=dict)  # measured vendor units (credits, seconds...); {} = none
    custo_usd: Optional[Decimal] = None  # None = not measured (named nao_medido by the runner), never an estimate

    def para_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["itens"] = [asdict(i) for i in self.itens]
        d["custo_usd"] = None if self.custo_usd is None else str(self.custo_usd)
        return d

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> "MidiaGerada":
        custo = d.get("custo_usd")
        return cls(
            d["gerador"], d["versao"], tuple(ItemMidia(**i) for i in d["itens"]), bool(d["sintetico"]),
            d.get("request_id"), dict(d.get("unidades") or {}), None if custo is None else Decimal(str(custo)),
        )


@dataclass(frozen=True)
class Montagem:
    montador: str
    versao: str
    arquivo_chave: str  # storage key of the assembled video
    sintetico: bool
    medicoes: dict[str, Any] = field(default_factory=dict)  # taken on the ENCODED file; a missing key = not measured
    custo_usd: Optional[Decimal] = None  # local compute = a measured 0; a vendor render = its bill; None = not measured

    def para_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["custo_usd"] = None if self.custo_usd is None else str(self.custo_usd)
        return d

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> "Montagem":
        custo = d.get("custo_usd")
        return cls(**{**d, "custo_usd": None if custo is None else Decimal(str(custo))})


@dataclass(frozen=True)
class Violacao:
    """A failed guard. ``codigo`` is stable and machine-readable; ``detalhe`` never carries script text (LGPD)."""

    codigo: str
    detalhe: str = ""

    def __str__(self) -> str:
        return f"{self.codigo}:{self.detalhe}" if self.detalhe else self.codigo
