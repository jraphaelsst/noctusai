"""Property-level legal data follows the manual<->Vista link
(sw-lead-to-contract CONTRACT §8.7; owner rule noc-2, 2026-10-09).

THE RULE
--------
Matrícula, CRI, inscrição municipal, ônus, título aquisitivo, last transfer,
the registry address and the imóvel documents / proprietários describe the
PROPERTY, not the listing. Once a manual imóvel (SW-####) is linked to a Vista
listing, a read keyed by the VISTA código must still find what was authored
under the manual one, otherwise a new deal on the Vista código would lose the
matrícula + documents of the deal the manual record was created for.

DIRECTION — Vista -> manual ONLY. The manual record keeps its own data, so a
read keyed by the manual código is never overlaid (a manual row read through
`linha_efetiva` is returned untouched). The fallback is per FIELD GROUP (a
value and its provenance quintet / act pointers travel together, never
half-and-half) and only where the Vista side has nothing.

BOTH SIDES HAVE A VALUE — a human decides. `reconciliar` records a conflict in
the EXISTING `imovel_campo_conflitos` mechanism (migration 154), on the Vista
código, with `fonte_tabela = 'vinculo'` as its marker. While it is open the
reader returns the Vista side's OWN value plus the campo in `conflitos` — never
the other value silently. Accepting it (the existing `resolver`) is the one
sanctioned way the manual value lands on the Vista row. Link conflicts are
excluded from the automatic divergence resolver on purpose: the owner asked for
a human here.

ONE implementation: every reader (dados, contract loader, título/ônus reads,
documents, proprietários) goes through `legal_efetivo` / `codigos_leitura`; no
reader re-implements the fallback.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID

from app.modules.imovel_hub import campos_extraidos_service as campos
from app.modules.imovel_hub import dados_service
from app.modules.imovel_hub.vinculo_service import Vinculo, resolver_vinculo
from app.services import campo_conflitos, table_reads

logger = logging.getLogger(__name__)

CONFLITOS_TABLE = campos.CONFLITOS_TABLE
FONTE_VINCULO = campos.FONTE_VINCULO


@dataclass(frozen=True)
class GrupoLegal:
    """One field group that travels together. `campo` is the conflict-capable
    definition (None = fallback-only, no conflict support)."""

    chave: str
    colunas: tuple[str, ...]
    campo: Optional[campos.CampoImovel]
    #: columns whose emptiness decides "the Vista side has nothing".
    decisivas: tuple[str, ...]


#: Columns that belong to a conflict-capable group but are not in CAMPOS.
_EXTRAS: dict[str, tuple[str, ...]] = {
    "situacao_onus": (
        "onus_observacoes",
        "onus_certidao_em",
        "onus_documento_id",
        "onus_registrado_por",
        "onus_registrado_em",
    ),
}


def _construir_grupos() -> tuple[GrupoLegal, ...]:
    grupos: list[GrupoLegal] = []
    for chave, campo in campos.CAMPOS.items():
        colunas = tuple(
            dict.fromkeys(
                campo.colunas + campo.colunas_proveniencia() + _EXTRAS.get(chave, ())
            )
        )
        grupos.append(GrupoLegal(chave, colunas, campo, campo.colunas))
    grupos.append(
        GrupoLegal(
            "endereco_registro_texto",
            tuple(dados_service.CAMPOS_ENDERECO_CONTRATO),
            None,
            ("endereco_registro_texto",),
        )
    )
    grupos.append(
        GrupoLegal(
            "ultima_transferencia_manual",
            tuple(dados_service.CAMPOS_ULTIMA_TRANSFERENCIA_MANUAL),
            None,
            ("ultima_transferencia_manual_data", "ultima_transferencia_manual_sem_registro"),
        )
    )
    return tuple(grupos)


GRUPOS: tuple[GrupoLegal, ...] = _construir_grupos()
_GRUPO_DA_COLUNA: dict[str, GrupoLegal] = {c: g for g in GRUPOS for c in g.colunas}


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _grupo_vazio(grupo: GrupoLegal, row: Optional[dict]) -> bool:
    row = row or {}
    if grupo.chave == "ultima_transferencia_manual":
        # `sem_registro=False` is "not stated", not a value.
        return campo_conflitos.valor_vazio(
            row.get("ultima_transferencia_manual_data")
        ) and not row.get("ultima_transferencia_manual_sem_registro")
    return all(campo_conflitos.valor_vazio(row.get(c)) for c in grupo.decisivas)


@dataclass(frozen=True)
class LegalEfetivo:
    """The legal data of `codigo` as a reader must see it."""

    codigo: str
    linha: Optional[dict]
    #: group chave -> código the value came from (only groups taken through the link)
    fontes: dict[str, str] = field(default_factory=dict)
    #: group chaves with an OPEN link conflict (Vista's own value is shown)
    conflitos: frozenset[str] = frozenset()
    vinculo: Optional[Vinculo] = None

    def fonte_de(self, coluna: str) -> str:
        grupo = _GRUPO_DA_COLUNA.get(coluna)
        return self.fontes.get(grupo.chave, self.codigo) if grupo else self.codigo

    def como_dict(self) -> Optional[dict]:
        """The API-facing summary, or None for an unlinked / manual-side read."""
        if self.vinculo is None or self.codigo != self.vinculo.vista_codigo:
            return None
        return {
            "manual_codigo": self.vinculo.manual_codigo,
            "fontes": dict(self.fontes),
            "conflitos": sorted(self.conflitos),
        }


def _abertos(client: Any, org_id: UUID, codigo: str) -> dict[str, dict]:
    """Open conflicts on `codigo`, by campo (the one-open-per-field index
    guarantees at most one per campo)."""
    rows = (
        _t(client, CONFLITOS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("codigo", codigo)
        .eq("status", "pendente")
        .execute()
    ).data or []
    return {r["campo"]: r for r in rows}


def legal_efetivo(
    client: Any, org_id: UUID, codigo: str, *, vinculo: Optional[Vinculo] = None
) -> LegalEfetivo:
    """The effective legal row of `codigo`. See the module docstring for the
    direction and the conflict semantics. Unlinked or manual-side: the raw row,
    unchanged."""
    canonico = codigo.strip().upper()
    row = dados_service.linha(client, org_id, canonico)
    vinculo = vinculo or resolver_vinculo(client, org_id, canonico)
    if vinculo is None or vinculo.vista_codigo != canonico:
        return LegalEfetivo(canonico, row, vinculo=vinculo)

    manual = dados_service.linha(client, org_id, vinculo.manual_codigo)
    abertos = {
        k for k, v in _abertos(client, org_id, canonico).items()
        if v.get("fonte_tabela") == FONTE_VINCULO
    }
    efetiva = dict(row) if row is not None else None
    fontes: dict[str, str] = {}
    if manual:
        for grupo in GRUPOS:
            if _grupo_vazio(grupo, manual) or not _grupo_vazio(grupo, row):
                continue
            if efetiva is None:
                efetiva = {}
            for coluna in grupo.colunas:
                efetiva[coluna] = manual.get(coluna)
            fontes[grupo.chave] = vinculo.manual_codigo
    return LegalEfetivo(
        canonico, efetiva, fontes=fontes, conflitos=frozenset(abertos), vinculo=vinculo
    )


def linha_efetiva(client: Any, org_id: UUID, codigo: str) -> Optional[dict]:
    """READ-ONLY twin of `dados_service.linha`. Writers keep using `linha`."""
    return legal_efetivo(client, org_id, codigo).linha


def valor_efetivo(client: Any, org_id: UUID, codigo: str, coluna: str) -> dict:
    """`{valor, fonte_codigo, conflito}` for one `imovel_dados` column."""
    ef = legal_efetivo(client, org_id, codigo)
    grupo = _GRUPO_DA_COLUNA.get(coluna)
    return {
        "valor": (ef.linha or {}).get(coluna),
        "fonte_codigo": ef.fonte_de(coluna),
        "conflito": bool(grupo and grupo.chave in ef.conflitos),
    }


def codigos_leitura(client: Any, org_id: UUID, codigo: str) -> list[str]:
    """Códigos whose property-level children (documents, proprietários) a read
    keyed by `codigo` must union: itself, plus the manual record when `codigo`
    is the linked Vista side. First element is always `codigo` (canonical)."""
    canonico = codigo.strip().upper()
    vinculo = resolver_vinculo(client, org_id, canonico)
    if vinculo is not None and vinculo.vista_codigo == canonico:
        return [canonico, vinculo.manual_codigo]
    return [canonico]


def manuais_por_vista(
    client: Any, org_id: UUID, codigos: list[str]
) -> dict[str, str]:
    """`{vista_codigo: manual_codigo}` for the linked Vista códigos among
    `codigos` — the batch twin of `codigos_leitura` (two batched reads, not
    two per código)."""
    unicos = sorted({c.strip().upper() for c in codigos if c})
    if not unicos:
        return {}
    registros = table_reads.in_batched_rows(
        client, "imovel_registry", org_id, "codigo_canonical", unicos,
        select="id,codigo_canonical", order_col="id",
    )
    por_id = {str(r["id"]): r["codigo_canonical"] for r in registros}
    if not por_id:
        return {}
    manuais = table_reads.in_batched_rows(
        client, "imovel_registry", org_id, "vinculado_a", sorted(por_id),
        select="id,codigo_canonical,vinculado_a", order_col="id",
    )
    saida: dict[str, str] = {}
    for m in sorted(manuais, key=lambda r: str(r.get("created_at") or r["id"])):
        saida.setdefault(por_id[str(m["vinculado_a"])], m["codigo_canonical"])
    return saida


# ─── conflicts ────────────────────────────────────────────────────────────


def reconciliar(client: Any, org_id: UUID, vinculo: Vinculo) -> dict:
    """Record a link conflict for every group present on BOTH sides with a
    different value. Idempotent. Returns `{novos, fechados, ja_em_conflito}`
    (campo names; `novos_conflitos` holds the rows so an async caller can
    announce them via `campos_extraidos_service.notificar`)."""
    vista = dados_service.linha(client, org_id, vinculo.vista_codigo) or {}
    manual = dados_service.linha(client, org_id, vinculo.manual_codigo) or {}
    abertos = _abertos(client, org_id, vinculo.vista_codigo)
    saida: dict[str, Any] = {
        "novos": [], "fechados": [], "ja_em_conflito": [], "novos_conflitos": [],
    }
    for chave, campo in campos.CAMPOS.items():
        v = campos._valor_atual(vista, campo)
        m = campos._valor_atual(manual, campo)
        existente = abertos.get(chave)
        e_nosso = existente is not None and existente.get("fonte_tabela") == FONTE_VINCULO
        if campos._vazio(v) or campos._vazio(m) or campos.iguais(campo, v, m):
            if e_nosso:
                _fechar(client, existente)
                saida["fechados"].append(chave)
            continue
        if existente is not None and not e_nosso:
            # A human already has a question open on this field; do not
            # supersede it with ours. The reader still returns Vista's value.
            saida["ja_em_conflito"].append(chave)
            continue
        if campo_conflitos.ja_rejeitado_pelo_usuario(
            client, campo_conflitos.IMOVEL, org_id, vinculo.vista_codigo, chave, m,
            igual=lambda proposto, _c=campo, _m=m: campos.iguais(_c, proposto, _m),
        ):
            continue
        novo = campo_conflitos.registrar_conflito(
            client, campo_conflitos.IMOVEL, org_id, vinculo.vista_codigo, chave,
            valor_anterior=v,
            origem_anterior=vista.get(campo.origem),
            valor_proposto=m,
            origem_proposto=manual.get(campo.origem) or campos.ORIGEM_MANUAL,
            fonte_tabela=FONTE_VINCULO,
            igual=lambda a, b, _c=campo: campos.iguais(_c, a, b),
        )
        if novo is not None:
            saida["novos"].append(chave)
            saida["novos_conflitos"].append(novo)
    return saida


def _fechar(client: Any, conflito: dict) -> None:
    _t(client, CONFLITOS_TABLE).update(
        {"status": "rejeitado", "decidido_por": None, "decidido_em": campos._now()}
    ).eq("id", conflito["id"]).execute()


def limpar(client: Any, org_id: UUID, vinculo: Vinculo) -> int:
    """Remove exactly the link-originated conflicts of this pair so unlinking
    restores the pre-link state: open ones and the ones the system itself
    superseded/closed. A conflict a HUMAN decided stays (an audit of a real
    decision whose effect, if accepted, is already on the Vista row). Returns
    rows removed. Idempotent."""
    rows = (
        _t(client, CONFLITOS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("codigo", vinculo.vista_codigo)
        .eq("fonte_tabela", FONTE_VINCULO)
        .execute()
    ).data or []
    removiveis = [
        r for r in rows if r.get("status") == "pendente" or not r.get("decidido_por")
    ]
    for r in removiveis:
        _t(client, CONFLITOS_TABLE).delete().eq("id", r["id"]).execute()
    return len(removiveis)
