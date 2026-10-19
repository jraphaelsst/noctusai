"""The closed list of atendimento blocks + the default stage -> block map (maya-blocks CONTRACT §1).

ONE backend constant, mirrored by the four DB CHECKs of migration 286 (`atendimento_blocos_bloco_valido`,
`atendimento_handoffs_blocos_validos` x2, `agente_scorecards_bloco_valido`). Adding a block = a migration widening
those CHECKs + this list, same commit (`tests/modules/atendimento_blocos/test_blocos.py` pins the parity).

Pure: no I/O. The org's effective configuration (a saved row replaces the default for its block) is resolved in
`repository.configuracao_efetiva`; `dono` answers "which block owns this stage" over that configuration.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

BLOCO_SDR = "sdr"
PIPELINE_FUNIL = "funil"
PIPELINE_PROCESSOS = "processos_venda"
#: The atendimento pipelines a block can own. `esteira` (241, content production) is never mapped.
PIPELINES_ATENDIMENTO: tuple[str, ...] = (PIPELINE_FUNIL, PIPELINE_PROCESSOS)


@dataclass(frozen=True)
class Bloco:
    bloco: str
    ordem: int
    rotulo: str
    #: The pipeline whose stages the block owns -- fixed here, never accepted from a client. `sdr` owns none.
    pipeline: Optional[str]
    agent_key_padrao: Optional[str]


BLOCOS: tuple[Bloco, ...] = (
    Bloco("sdr", 1, "SDR (Julia)", None, "julia"),
    Bloco("atendimento", 2, "Atendimento (corretor)", PIPELINE_FUNIL, None),
    Bloco("negociacao", 3, "Negociação", PIPELINE_FUNIL, None),
    Bloco("juridico", 4, "Jurídico", PIPELINE_PROCESSOS, None),
    Bloco("financeiro", 5, "Financeiro", PIPELINE_PROCESSOS, None),
    Bloco("contador", 6, "Contador", PIPELINE_PROCESSOS, None),
)
BLOCO_POR_NOME: dict[str, Bloco] = {b.bloco: b for b in BLOCOS}
NOMES_BLOCOS: tuple[str, ...] = tuple(b.bloco for b in BLOCOS)

#: CONTRACT §1.2 -- derived from `ensure_default_pipeline_stages` as last redefined in migration 060.
ETAPAS_PADRAO: dict[str, tuple[str, ...]] = {
    "sdr": (),
    "atendimento": ("qualificacao", "visitas", "proposta_recebida"),
    "negociacao": ("negociacao", "proposta_decisao"),
    "juridico": ("elaboracao_contrato", "analise_partes", "revisao_contrato", "assinatura"),
    "financeiro": ("financiamento_escritura", "finalizacao", "entrega_chaves"),
    "contador": ("nota_fiscal",),
}

#: The agent keys allowed to run each block (v1: only Julia, studio key `julia`, on `sdr`).
AGENTES_POR_BLOCO: dict[str, frozenset[str]] = {"sdr": frozenset({"julia"})}

#: The studio key Julia carried before the 2026-10 rename. A row / client written during the deploy window may still
#: hold it; it is read and accepted as `julia`. NOC-REMEDIATE[drop-lead-imob-alias]: drop once no `lead-imob` row remains (migration 287 rewrote them).
ALIAS_AGENT_KEY_LEGADO: dict[str, str] = {"lead-imob": "julia"}


def normalizar_agent_key(agent_key: Optional[str]) -> Optional[str]:
    return ALIAS_AGENT_KEY_LEGADO.get(agent_key, agent_key) if agent_key else agent_key


@dataclass(frozen=True)
class ConfigBloco:
    """One block's effective configuration for an org (a saved row, or the code default)."""

    bloco: str
    agent_key: Optional[str]
    ativo: bool
    etapas: tuple[str, ...]
    origem: str  # "padrao" | "org"
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None

    @property
    def pipeline(self) -> Optional[str]:
        return BLOCO_POR_NOME[self.bloco].pipeline


def config_padrao(bloco: str) -> ConfigBloco:
    b = BLOCO_POR_NOME[bloco]
    # `ativo` DEFAULT false (CONTRACT §5.2): an absent row is always read as off.
    return ConfigBloco(bloco=bloco, agent_key=b.agent_key_padrao, ativo=False, etapas=ETAPAS_PADRAO[bloco], origem="padrao")


def agentes_permitidos(bloco: str) -> frozenset[str]:
    return AGENTES_POR_BLOCO.get(bloco, frozenset())


def dono(config: Mapping[str, ConfigBloco], pipeline: Optional[str], slug: Optional[str]) -> Optional[str]:
    """The block whose `(pipeline, etapas)` contains `slug`, else None (`sem_bloco`)."""
    if not pipeline or not slug:
        return None
    for b in BLOCOS:
        c = config.get(b.bloco)
        if c is not None and c.pipeline == pipeline and slug in c.etapas:
            return b.bloco
    return None


def sobreposicoes(config: Mapping[str, ConfigBloco]) -> list[tuple[str, str, str]]:
    """`(slug, bloco_a, bloco_b)` for every stage slug owned by two blocks of the same pipeline."""
    vistos: dict[tuple[str, str], str] = {}
    achados: list[tuple[str, str, str]] = []
    for b in BLOCOS:
        c = config.get(b.bloco)
        if c is None or c.pipeline is None:
            continue
        for slug in c.etapas:
            chave = (c.pipeline, slug)
            if chave in vistos and vistos[chave] != b.bloco:
                achados.append((slug, vistos[chave], b.bloco))
            else:
                vistos[chave] = b.bloco
    return achados


__all__ = [
    "AGENTES_POR_BLOCO", "ALIAS_AGENT_KEY_LEGADO", "normalizar_agent_key", "BLOCOS", "BLOCO_POR_NOME", "BLOCO_SDR", "Bloco", "ConfigBloco", "ETAPAS_PADRAO",
    "NOMES_BLOCOS", "PIPELINES_ATENDIMENTO", "PIPELINE_FUNIL", "PIPELINE_PROCESSOS", "agentes_permitidos",
    "config_padrao", "dono", "sobreposicoes",
]
