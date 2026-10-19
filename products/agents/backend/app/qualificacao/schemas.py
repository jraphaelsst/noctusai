"""HTTP schemas of the qualification router (strict: unknown fields are a 422)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from app.qualificacao.models import CriterioDef, EstagioDef, Opcao, ParametrosDef, VersaoPadrao
from noctusai_lib.api import StrictHttpModel

Grupo = Literal["prontidao", "bloqueios", "interesse", "perfil_imovel", "perfil_vida", "contato"]
Tipo = Literal["enum", "multi", "bool", "numero", "faixa", "texto", "imovel_ref"]
_CHAVE = r"^[a-z][a-z0-9_]{1,63}$"


class OpcaoIn(StrictHttpModel):
    valor: str = Field(min_length=1, max_length=120)
    rotulo: str = Field(default="", max_length=200)
    descricao_modelo: str = Field(default="", max_length=1000)
    sinonimos: list[str] = Field(default_factory=list, max_length=30)


class CriterioIn(StrictHttpModel):
    grupo: Grupo
    rotulo: str = Field(min_length=1, max_length=200)
    descricao_modelo: str = Field(default="", max_length=2000)
    tipo: Tipo
    opcoes: list[OpcaoIn] = Field(default_factory=list, max_length=60)
    unidade: str | None = Field(default=None, max_length=40)
    sensivel: Literal["faixa", "nao_coletar"] | None = None
    pontuacao: dict[str, Any] | list[dict[str, Any]] = Field(default_factory=dict)
    ordem: int = 0
    ativo: bool = True
    eixo: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,31}$")
    validade_dias: int | None = Field(default=None, ge=1, le=3650)

    def to_def(self, chave: str) -> CriterioDef:
        return CriterioDef(
            chave=chave, grupo=self.grupo, rotulo=self.rotulo, descricao_modelo=self.descricao_modelo,
            tipo=self.tipo,
            opcoes=tuple(Opcao(o.valor, o.rotulo, o.descricao_modelo, tuple(o.sinonimos)) for o in self.opcoes),
            unidade=self.unidade, sensivel=self.sensivel, pontuacao=self.pontuacao, ordem=self.ordem,
            ativo=self.ativo, eixo=self.eixo, validade_dias=self.validade_dias,
        )


class EstagioIn(StrictHttpModel):
    rotulo: str = Field(min_length=1, max_length=200)
    descricao: str = Field(default="", max_length=2000)
    ordem: int
    regra: dict[str, Any]
    conclusivo: bool = False
    terminal: bool = False

    def to_def(self, chave: str) -> EstagioDef:
        return EstagioDef(
            chave=chave, rotulo=self.rotulo, descricao=self.descricao, ordem=self.ordem, regra=self.regra,
            conclusivo=self.conclusivo, terminal=self.terminal,
        )


class ParametrosIn(StrictHttpModel):
    minimo_para_ofertar: dict[str, Any]
    lote_ofertas: int = Field(default=3, ge=1, le=5)
    score_max: int = Field(default=100, ge=1, le=1000)

    def to_def(self) -> ParametrosDef:
        return ParametrosDef(self.minimo_para_ofertar, self.lote_ofertas, self.score_max)


class PadraoCreate(StrictHttpModel):
    chave: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    nome: str = Field(min_length=1, max_length=200)
    descricao: str | None = Field(default=None, max_length=2000)


class RascunhoCreate(StrictHttpModel):
    notas: str | None = Field(default=None, max_length=2000)
    copiar_de: UUID | None = None


class VersaoPatch(StrictHttpModel):
    notas: str | None = Field(default=None, max_length=2000)


class PadraoOut(StrictHttpModel):
    id: UUID
    chave: str
    nome: str
    descricao: str | None


class VersaoMetaOut(StrictHttpModel):
    id: UUID
    versao: int
    status: str
    notas: str | None
    publicada_em: datetime | None


def versao_out(v: VersaoPadrao) -> dict[str, Any]:
    return {
        "id": str(v.id), "padrao": v.padrao_chave, "versao": v.versao, "status": v.status, "notas": v.notas,
        "publicada_em": v.publicada_em.isoformat() if v.publicada_em else None,
        "criterios": [
            {
                "chave": c.chave, "grupo": c.grupo, "rotulo": c.rotulo, "descricao_modelo": c.descricao_modelo,
                "tipo": c.tipo,
                "opcoes": [
                    {"valor": o.valor, "rotulo": o.rotulo, "descricao_modelo": o.descricao_modelo,
                     "sinonimos": list(o.sinonimos)} for o in c.opcoes
                ],
                "unidade": c.unidade, "sensivel": c.sensivel, "pontuacao": c.pontuacao, "ordem": c.ordem,
                "ativo": c.ativo, "eixo": c.eixo, "validade_dias": c.validade_dias,
            }
            for c in v.criterios
        ],
        "estagios": [
            {
                "chave": e.chave, "rotulo": e.rotulo, "descricao": e.descricao, "ordem": e.ordem,
                "regra": e.regra, "conclusivo": e.conclusivo, "terminal": e.terminal,
            }
            for e in v.estagios
        ],
        "parametros": {
            "minimo_para_ofertar": v.parametros.minimo_para_ofertar,
            "lote_ofertas": v.parametros.lote_ofertas, "score_max": v.parametros.score_max,
        },
    }
