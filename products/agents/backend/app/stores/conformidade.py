"""Conformance + abuse-limit store -- ``agents.conformidade_regras`` / ``conformidade_violacoes`` /
``conformidade_impressoes`` / ``canal_limites`` (migration 037, Julia v2 CONTRACT §3.5 E3).

* **regras** -- per agent instance: ``ativo`` + ``politica`` (``registrar`` | ``bloquear``) of each
  detector and its DATA parameters. A rule with no row runs on the code-side default
  (:data:`POLITICA_PADRAO`): ``registrar`` everywhere, ``bloquear`` for ``vazamento_prompt``.
* **violacoes** -- what a detector found. Codes and counts only: never the reply text, the lead's words
  or a prompt fragment.
* **impressoes** -- the prompt-leak fingerprint (hashed shingles) of a version, computed at publish.
* **limites** -- per-instance abuse limits in data. The column DEFAULTs of migration 037 are mirrored by
  :data:`LIMITES_PADRAO`, the value an instance without a row reads (the Real store upserts a row on first
  use, so the DB default is the single source and the constant is only its Fake mirror).

Seed IO shape: Protocol + Fake + Supabase (Real) + ``get_conformidade_store(settings)`` factory.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.stores._util import utcnow

logger = logging.getLogger(__name__)

__all__ = [
    "DETECTORES_BLOQUEANTES",
    "LIMITES_PADRAO",
    "SINAIS_SEGURANCA",
    "POLITICAS",
    "POLITICA_PADRAO",
    "REGRAS",
    "ConformidadeStore",
    "FakeConformidadeStore",
    "Impressao",
    "LimitesCanal",
    "RegraConfig",
    "SupabaseConformidadeStore",
    "Violacao",
    "get_conformidade_store",
]

_SCHEMA = "agents"
POLITICAS = ("registrar", "bloquear")

#: The detectors (post-turn) plus the deterministic escalations (pre/post-turn) and the input-side signal.
REGRAS = (
    "imovel_sem_ferramenta", "termina_sem_pergunta", "perfil_citado_sem_registro", "fallback_enviado",
    "pergunta_repetida", "vazamento_prompt", "tentativa_extracao",
    "escala_pedido_humano", "escala_fora_escopo", "escala_qualificacao_completa", "parada_segura",
    # public-line guardrails (spec B3/B4): the output filters, the identity-claim signal, the abuse escalation
    "link_nao_permitido", "contato_nao_permitido", "pii_na_resposta", "formato_suspeito", "padroes_proibidos",
    "alegacao_identidade", "escala_seguranca",
    "escala_loop", "injecao_ferramenta",
)
#: The detectors that block by default: a reply that leaks the prompt or carries an unvetted link, contact,
#: identity number, encoded/structured payload or a forbidden pattern never reaches the lead.
DETECTORES_BLOQUEANTES = (
    "vazamento_prompt", "link_nao_permitido", "contato_nao_permitido", "pii_na_resposta", "formato_suspeito",
    "padroes_proibidos",
)
#: The input-side signals that count toward ``escala_seguranca`` (per thread, 24 h).
SINAIS_SEGURANCA = ("tentativa_extracao", "alegacao_identidade")
#: Code-side default policy of a rule with no row (the contract: ``registrar`` everywhere; the owner's IP
#: mandate: the leak detector blocks by default).
POLITICA_PADRAO: dict[str, str] = {r: "registrar" for r in REGRAS} | {r: "bloquear" for r in DETECTORES_BLOQUEANTES}


@dataclass(frozen=True)
class RegraConfig:
    regra: str
    ativo: bool = True
    politica: str = "registrar"
    mensagem_correcao_texto_chave: str | None = None
    parametros: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Violacao:
    regra: str
    politica: str  # registrar | bloquear | sinal
    detalhe: dict[str, Any] = field(default_factory=dict)
    bloqueada: bool = False
    id: UUID | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class LimitesCanal:
    janela_segundos: int = 60
    max_turnos_janela: int = 6
    max_turnos_dia: int = 200
    max_custo_dia_usd: float = 2.0
    max_imoveis_distintos: int = 30
    max_recusas_por_turno: int = 2
    max_erros_ferramenta_por_turno: int = 3
    # ── migration 045: guardrails B5 / B6 (abuse limits as data) ──
    #: Per-lead rate: turns in the last hour (the per-window cap is ``max_turnos_janela``). Status ``limite_taxa``.
    max_turnos_hora: int = 60
    #: New-lead admission per agent (status ``novo_lead_limitado``).
    max_novos_leads_hora: int = 30
    max_novos_leads_dia: int = 200
    #: Share of the org's daily channel cap kept for threads that already exist; new threads spend the rest.
    reserva_leads_existentes_pct: int = 50
    #: Loop / flood / echo breaker (status ``loop_detectado``).
    loop_ativo: bool = True
    loop_repeticoes: int = 3
    loop_similaridade: float = 0.9
    loop_janela_segundos: int = 600
    loop_min_chars: int = 8
    loop_eco_tokens: int = 12
    loop_latencia_mediana_s: float = 3.0
    loop_trocas: int = 5
    #: Per-turn tool-call caps (a refusal past the cap, counted against the refusal budget).
    max_chamadas_ferramenta_turno: int = 8
    max_oferecer_turno: int = 1
    max_abrir_skill_turno: int = 4
    max_detalhes_turno: int = 3
    #: Caps of the untrusted catalogue text a tool hands the model.
    catalogo_descricao_max: int = 600
    catalogo_titulo_max: int = 120
    catalogo_caracteristicas_max: int = 30
    catalogo_item_max: int = 60


#: Mirror of the migration-037 + 045 column DEFAULTs (what a fresh instance reads).
LIMITES_PADRAO = LimitesCanal()


@dataclass(frozen=True)
class Impressao:
    version_id: UUID
    shingle_tokens: int
    shingles: frozenset[int]


class ConformidadeStore(Protocol):
    def regras(self, org_id: UUID, agent_id: UUID) -> dict[str, RegraConfig]:
        """Every rule's effective config for the agent: the stored rows over the code defaults
        (a rule with no row is active under :data:`POLITICA_PADRAO`)."""
        ...

    def definir_regra(
        self, org_id: UUID, agent_id: UUID, regra: str, *, ativo: bool | None = None,
        politica: str | None = None, mensagem_correcao_texto_chave: str | None = None,
        parametros: dict[str, Any] | None = None,
    ) -> RegraConfig: ...

    def registrar_violacao(
        self, org_id: UUID, agent_id: UUID, v: Violacao, *, thread_id: UUID | None = None,
        lead_ref_id: UUID | None = None, message_id: UUID | None = None, compiled_hash: str | None = None,
        origem: str = "canal",
    ) -> Violacao: ...

    def listar_violacoes(
        self, org_id: UUID, agent_id: UUID, *, thread_id: UUID | None = None, limite: int = 200
    ) -> list[Violacao]: ...

    def contar_sinais(
        self, org_id: UUID, agent_id: UUID, thread_id: UUID, regras: Sequence[str], desde: datetime,
    ) -> int:
        """How many violation rows of ``regras`` this thread has since ``desde`` (the ``escala_seguranca`` counter)."""
        ...

    def obter_impressao(self, org_id: UUID, version_id: UUID) -> Impressao | None: ...

    def salvar_impressao(self, org_id: UUID, impressao: Impressao) -> None: ...

    def limites(self, org_id: UUID, agent_id: UUID) -> LimitesCanal: ...

    def definir_limites(self, org_id: UUID, agent_id: UUID, **campos: Any) -> LimitesCanal: ...


_LIMITE_CAMPOS = frozenset(LimitesCanal.__dataclass_fields__)


class FakeConformidadeStore:
    def __init__(self) -> None:
        self._regras: dict[tuple[UUID, str], RegraConfig] = {}
        self._violacoes: list[tuple[UUID, UUID, UUID | None, Violacao]] = []
        self._impressoes: dict[UUID, Impressao] = {}
        self._limites: dict[UUID, LimitesCanal] = {}
        self.falha: Exception | None = None

    def regras(self, org_id: UUID, agent_id: UUID) -> dict[str, RegraConfig]:
        if self.falha is not None:
            raise self.falha
        out = {r: RegraConfig(r, True, POLITICA_PADRAO[r]) for r in REGRAS}
        for (aid, regra), cfg in self._regras.items():
            if aid == agent_id:
                out[regra] = cfg
        return out

    def definir_regra(
        self, org_id: UUID, agent_id: UUID, regra: str, *, ativo: bool | None = None,
        politica: str | None = None, mensagem_correcao_texto_chave: str | None = None,
        parametros: dict[str, Any] | None = None,
    ) -> RegraConfig:
        if regra not in REGRAS:
            raise ValueError(f"unknown rule {regra!r}")
        if politica is not None and politica not in POLITICAS:
            raise ValueError(f"politica must be one of {POLITICAS}")
        atual = self.regras(org_id, agent_id)[regra]
        novo = replace(
            atual,
            ativo=atual.ativo if ativo is None else ativo,
            politica=atual.politica if politica is None else politica,
            mensagem_correcao_texto_chave=(
                atual.mensagem_correcao_texto_chave if mensagem_correcao_texto_chave is None
                else mensagem_correcao_texto_chave
            ),
            parametros=atual.parametros if parametros is None else dict(parametros),
        )
        self._regras[(agent_id, regra)] = novo
        return novo

    def registrar_violacao(
        self, org_id: UUID, agent_id: UUID, v: Violacao, *, thread_id: UUID | None = None,
        lead_ref_id: UUID | None = None, message_id: UUID | None = None, compiled_hash: str | None = None,
        origem: str = "canal",
    ) -> Violacao:
        rec = replace(v, id=uuid4(), created_at=utcnow())
        self._violacoes.append((agent_id, thread_id, message_id, rec))
        return rec

    def listar_violacoes(
        self, org_id: UUID, agent_id: UUID, *, thread_id: UUID | None = None, limite: int = 200
    ) -> list[Violacao]:
        rows = [v for a, t, _m, v in self._violacoes if a == agent_id and (thread_id is None or t == thread_id)]
        return rows[-limite:]

    def contar_sinais(
        self, org_id: UUID, agent_id: UUID, thread_id: UUID, regras: Sequence[str], desde: datetime,
    ) -> int:
        return sum(
            1 for a, t, _m, v in self._violacoes
            if a == agent_id and t == thread_id and v.regra in regras and v.created_at is not None and v.created_at >= desde
        )

    def obter_impressao(self, org_id: UUID, version_id: UUID) -> Impressao | None:
        return self._impressoes.get(version_id)

    def salvar_impressao(self, org_id: UUID, impressao: Impressao) -> None:
        self._impressoes[impressao.version_id] = impressao

    def limites(self, org_id: UUID, agent_id: UUID) -> LimitesCanal:
        if self.falha is not None:
            raise self.falha
        return self._limites.get(agent_id, LIMITES_PADRAO)

    def definir_limites(self, org_id: UUID, agent_id: UUID, **campos: Any) -> LimitesCanal:
        desconhecidos = set(campos) - _LIMITE_CAMPOS
        if desconhecidos:
            raise ValueError(f"unknown limits {sorted(desconhecidos)}")
        novo = replace(self.limites(org_id, agent_id), **campos)
        self._limites[agent_id] = novo
        return novo


class SupabaseConformidadeStore:
    def __init__(self, client: Any) -> None:
        self._client = client

    def _t(self, name: str):
        return self._client.schema(_SCHEMA).table(name)

    def regras(self, org_id: UUID, agent_id: UUID) -> dict[str, RegraConfig]:
        out = {r: RegraConfig(r, True, POLITICA_PADRAO[r]) for r in REGRAS}
        rows = self._t("conformidade_regras").select("*").eq("org_id", str(org_id)).eq(
            "agent_id", str(agent_id)).execute().data or []
        for r in rows:
            if r["regra"] in out:
                out[r["regra"]] = RegraConfig(
                    r["regra"], bool(r["ativo"]), r["politica"], r.get("mensagem_correcao_texto_chave"),
                    dict(r.get("parametros") or {}),
                )
        return out

    def definir_regra(
        self, org_id: UUID, agent_id: UUID, regra: str, *, ativo: bool | None = None,
        politica: str | None = None, mensagem_correcao_texto_chave: str | None = None,
        parametros: dict[str, Any] | None = None,
    ) -> RegraConfig:
        if regra not in REGRAS:
            raise ValueError(f"unknown rule {regra!r}")
        if politica is not None and politica not in POLITICAS:
            raise ValueError(f"politica must be one of {POLITICAS}")
        atual = self.regras(org_id, agent_id)[regra]
        novo = RegraConfig(
            regra,
            atual.ativo if ativo is None else ativo,
            atual.politica if politica is None else politica,
            atual.mensagem_correcao_texto_chave if mensagem_correcao_texto_chave is None
            else mensagem_correcao_texto_chave,
            atual.parametros if parametros is None else dict(parametros),
        )
        self._t("conformidade_regras").upsert({
            "org_id": str(org_id), "agent_id": str(agent_id), "regra": regra, "ativo": novo.ativo,
            "politica": novo.politica, "mensagem_correcao_texto_chave": novo.mensagem_correcao_texto_chave,
            "parametros": novo.parametros, "updated_at": utcnow().isoformat(),
        }, on_conflict="agent_id,regra").execute()
        return novo

    def registrar_violacao(
        self, org_id: UUID, agent_id: UUID, v: Violacao, *, thread_id: UUID | None = None,
        lead_ref_id: UUID | None = None, message_id: UUID | None = None, compiled_hash: str | None = None,
        origem: str = "canal",
    ) -> Violacao:
        row = self._t("conformidade_violacoes").insert({
            "org_id": str(org_id), "agent_id": str(agent_id),
            "thread_id": str(thread_id) if thread_id else None,
            "lead_ref_id": str(lead_ref_id) if lead_ref_id else None,
            "message_id": str(message_id) if message_id else None,
            "regra": v.regra, "politica": v.politica, "bloqueada": v.bloqueada, "detalhe": v.detalhe,
            "compiled_hash": compiled_hash, "origem": origem,
        }).execute().data[0]
        return replace(v, id=UUID(str(row["id"])), created_at=row.get("created_at"))

    def listar_violacoes(
        self, org_id: UUID, agent_id: UUID, *, thread_id: UUID | None = None, limite: int = 200
    ) -> list[Violacao]:
        q = self._t("conformidade_violacoes").select("*").eq("org_id", str(org_id)).eq("agent_id", str(agent_id))
        if thread_id is not None:
            q = q.eq("thread_id", str(thread_id))
        rows = q.order("created_at", desc=True).limit(limite).execute().data or []
        return [
            Violacao(r["regra"], r["politica"], dict(r.get("detalhe") or {}), bool(r["bloqueada"]),
                     UUID(str(r["id"])), r.get("created_at"))
            for r in reversed(rows)
        ]

    def contar_sinais(
        self, org_id: UUID, agent_id: UUID, thread_id: UUID, regras: Sequence[str], desde: datetime,
    ) -> int:
        rows = self._t("conformidade_violacoes").select("id").eq("org_id", str(org_id)).eq(
            "agent_id", str(agent_id)).eq("thread_id", str(thread_id)).in_("regra", list(regras)).gte(
            "created_at", desde.isoformat()).limit(100).execute().data or []
        return len(rows)

    def obter_impressao(self, org_id: UUID, version_id: UUID) -> Impressao | None:
        rows = self._t("conformidade_impressoes").select("*").eq("org_id", str(org_id)).eq(
            "version_id", str(version_id)).limit(1).execute().data or []
        if not rows:
            return None
        return Impressao(version_id, int(rows[0]["shingle_tokens"]), frozenset(int(x) for x in rows[0]["shingles"]))

    def salvar_impressao(self, org_id: UUID, impressao: Impressao) -> None:
        self._t("conformidade_impressoes").upsert({
            "version_id": str(impressao.version_id), "org_id": str(org_id),
            "shingle_tokens": impressao.shingle_tokens, "shingles": sorted(impressao.shingles),
        }, on_conflict="version_id").execute()

    def limites(self, org_id: UUID, agent_id: UUID) -> LimitesCanal:
        rows = self._t("canal_limites").select("*").eq("org_id", str(org_id)).eq(
            "agent_id", str(agent_id)).limit(1).execute().data or []
        if not rows:
            # First use: the row is created with the DB column defaults (the single source of the numbers).
            self._t("canal_limites").upsert(
                {"agent_id": str(agent_id), "org_id": str(org_id)}, on_conflict="agent_id", ignore_duplicates=True,
            ).execute()
            rows = self._t("canal_limites").select("*").eq("agent_id", str(agent_id)).limit(1).execute().data or []
        if not rows:
            raise RuntimeError("canal_limites row unreadable after upsert")
        r = rows[0]
        return LimitesCanal(**{k: type(getattr(LIMITES_PADRAO, k))(r[k]) for k in _LIMITE_CAMPOS})

    def definir_limites(self, org_id: UUID, agent_id: UUID, **campos: Any) -> LimitesCanal:
        desconhecidos = set(campos) - _LIMITE_CAMPOS
        if desconhecidos:
            raise ValueError(f"unknown limits {sorted(desconhecidos)}")
        self.limites(org_id, agent_id)
        self._t("canal_limites").update({**campos, "updated_at": utcnow().isoformat()}).eq(
            "agent_id", str(agent_id)).eq("org_id", str(org_id)).execute()
        return self.limites(org_id, agent_id)


def get_conformidade_store(settings: Any) -> ConformidadeStore:
    if not getattr(settings, "supabase_service_role_key", None):
        return FakeConformidadeStore()
    from app.database import get_admin_client

    return SupabaseConformidadeStore(get_admin_client())
