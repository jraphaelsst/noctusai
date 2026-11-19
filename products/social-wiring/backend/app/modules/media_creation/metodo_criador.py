"""Métodos de criadores — reference creators' content methodologies as validated data.

One JSON file per reference creator (``metodos_criadores/<slug>.json``), all in ONE shape: who the creator is,
where the reading came from, the emotional curve, the moldes (ordered steps, each mapped to a canonical block
type from ``estruturas_tipos_bloco``), what may and may not be copied, and a checklist.

Only the FORM of a creator's content lives here — never their words or transcripts. A client's adaptation
(voice, examples written for that client) is client data and does not belong in these files.

Consumers today: the local roteirista agents (they read the chosen file) and the "Metodologias de criadores"
picker artifact. The files map one-to-one onto Estruturas rows (``perfil`` = the creator's handle, blocks =
``moldes[].etapas[].bloco``), so moving them into the product library is an import, not a rewrite.
Pattern: KNOWLEDGE-BASE/CONTEXT/PRODUCTS/social-wiring/METODOS-CRIADORES.md
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.media_creation.estruturas_tipos_bloco import TIPO_NOMES

SCHEMA_VERSION = 1
DIRETORIO = Path(__file__).resolve().parent / "metodos_criadores"


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Criador(_Base):
    handle: str = Field(pattern=r"^@[\w.]+$")
    nome: str
    area: str
    seguidores: Optional[str] = None
    publico: str


class Fonte(_Base):
    data_leitura: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    amostra: str
    limites: str
    copia: str


class Stat(_Base):
    valor: str
    rotulo: str


class EtapaCurva(_Base):
    nome: str
    texto: str


class Curva(_Base):
    nome: str
    descricao: str
    etapas: tuple[EtapaCurva, ...] = Field(min_length=2)


class Ritmo(_Base):
    duracao_s: tuple[int, int]
    palavras_por_segundo: float = Field(gt=0)
    pessoa: str
    historia_propria: bool
    apresentacao: str


class Etapa(_Base):
    tempo: str
    bloco: str
    texto: str

    @field_validator("bloco")
    @classmethod
    def _bloco_canonico(cls, v: str) -> str:
        if v not in TIPO_NOMES:
            raise ValueError(f"bloco {v!r} não está no catálogo canônico (estruturas_tipos_bloco.TIPO_NOMES)")
        return v


class Molde(_Base):
    n: int = Field(ge=1)
    slug: str = Field(pattern=r"^[a-z0-9-]+$")
    titulo: str
    frequencia: str
    duracao_s: tuple[int, int]
    palavras: tuple[int, int]
    etapas: tuple[Etapa, ...] = Field(min_length=1)
    por_que_funciona: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _faixas_ordenadas(self) -> "Molde":
        for nome in ("duracao_s", "palavras"):
            lo, hi = getattr(self, nome)
            if not 0 < lo <= hi:
                raise ValueError(f"molde {self.n}: {nome} precisa ser 0 < min <= max, veio {lo}..{hi}")
        return self


class FamiliaHeadline(_Base):
    nome: str
    esqueleto: str


class Regras(_Base):
    pode: tuple[str, ...] = Field(min_length=1)
    nao: tuple[str, ...] = Field(min_length=1)


class MetodoCriador(_Base):
    schema_version: int
    slug: str = Field(pattern=r"^[a-z0-9-]+$")
    criador: Criador
    fonte: Fonte
    resumo: str
    stats: tuple[Stat, ...]
    curva: Curva
    ritmo: Ritmo
    moldes: tuple[Molde, ...] = Field(min_length=1)
    familias_headline: tuple[FamiliaHeadline, ...] = ()
    regras: Regras
    checklist: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistente(self) -> "MetodoCriador":
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version {self.schema_version} != {SCHEMA_VERSION}")
        numeros = [m.n for m in self.moldes]
        if numeros != list(range(1, len(numeros) + 1)):
            raise ValueError(f"moldes precisam ser numerados 1..N em ordem, vieram {numeros}")
        slugs = [m.slug for m in self.moldes]
        if len(set(slugs)) != len(slugs):
            raise ValueError(f"slug de molde repetido: {slugs}")
        return self

    def molde(self, ref: int | str) -> Molde:
        """Um molde pelo número ou pelo slug; KeyError nomeando as opções quando não existe."""
        for m in self.moldes:
            if m.n == ref or m.slug == ref:
                return m
        raise KeyError(f"{self.slug}: molde {ref!r} não existe; opções: {[m.slug for m in self.moldes]}")


def carregar(slug: str, diretorio: Path = DIRETORIO) -> MetodoCriador:
    """Carrega e valida ``<slug>.json``. O nome do arquivo precisa bater com o ``slug`` declarado."""
    caminho = diretorio / f"{slug}.json"
    metodo = MetodoCriador.model_validate(json.loads(caminho.read_text(encoding="utf-8")))
    if metodo.slug != slug:
        raise ValueError(f"{caminho.name}: slug declarado {metodo.slug!r} não bate com o nome do arquivo")
    return metodo


def listar(diretorio: Path = DIRETORIO) -> tuple[MetodoCriador, ...]:
    """Todos os métodos, em ordem de slug. Um arquivo inválido levanta, nunca é pulado em silêncio."""
    return tuple(carregar(p.stem, diretorio) for p in sorted(diretorio.glob("*.json")))
