"""Zero-API backfill for the canonical identifiers (owner rule 2026-10-01).

    "If we see a doc that claims to be a doc number/id/protocol but no
     punctuation we check it against the canonical form with punctuation to
     measure if it fits that type … check past work so no additional cost on
     api … so we can go on hardened on these processes."

WHAT IT DOES — only with data ALREADY STORED, never a model/provider call
------------------------------------------------------------------------
A. **Canonicalise stored values.** `clientes.cpf` / `rg` / `endereco_cep`,
   `imovel_dados.numero_matricula` / `prefeitura_cadastro_imobiliario` and
   `certidao_consultas.documento` that FIT their type but are stored in
   another spelling are rewritten to the punctuated canonical form
   (`identificadores.para_gravar`). The RAW reading goes to
   `identificador_canonizacoes` first (`origem='backfill'`) — the way back.
   A value that does NOT fit (bad check digit, unknown mask, another type's
   number) is never touched: it is COUNTED by reason, and stays visible.
   `empresas.cnpj` is left alone (it is the identity key — migration 187).
B. **Re-resolve pending conflicts** in `cliente_campo_conflitos`
   (cpf / rg / rg_orgao_expedidor — through the SAME `divergencia_resolucao`
   the live path runs: equivalence, type routing, DV validator, corroboration,
   tier), `imovel_campo_conflitos` (matrícula / inscrição municipal /
   cartório — equivalence only: no check digit exists to decide on) and
   `empresa_campo_conflitos` (no identifier field lives there today — counted,
   not skipped silently). A conflict decided without a human is closed as
   `resolvido_automatico` with its rule in `motivo_resolucao`, exactly the
   auditable shape the live resolver writes.

The report is COUNTS ONLY — no CPF, RG, name or number ever leaves this
module (LGPD). Idempotent: a second run finds nothing left to do.

RUNNING IT (the tech-lead's one-liner — dry-run FIRST)
-----------------------------------------------------
    cd products/social-wiring/backend
    python -m app.services.identificadores_backfill --org <ORG_UUID> --dry-run   # counts, writes nothing
    python -m app.services.identificadores_backfill --org <ORG_UUID>             # applies; safe to re-run

Apply migration 187 first: the log table + the triggers it creates are what
make the writes reversible and keep later writes canonical.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from typing import Any, Optional
from uuid import UUID, uuid4

from app.services import campo_conflitos, divergencia_resolucao, table_reads
from app.services import identificadores as idf
from app.services.divergencia_resolucao import Decisao

logger = logging.getLogger(__name__)

LOG_TABLE = "identificador_canonizacoes"

#: Campos of `cliente_campo_conflitos` the identifier backfill re-resolves.
CAMPOS_CONFLITO_CLIENTE = frozenset({"cpf", "rg", "rg_orgao_expedidor"})
#: Campos of `imovel_campo_conflitos` that are identifiers.
CAMPOS_CONFLITO_IMOVEL = frozenset(
    {"numero_matricula", "prefeitura_cadastro_imobiliario", "numero_registro_imoveis"}
)


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _registrar_bruto(
    client: Any, org_id: UUID, tabela: str, linha_id: str, campo: str, tipo: str,
    bruto: str, canonico: str,
) -> None:
    _t(client, LOG_TABLE).insert(
        {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "tabela": tabela,
            "linha_id": linha_id,
            "campo": campo,
            "tipo": tipo,
            "valor_bruto": bruto,
            "valor_canonico": canonico,
            "origem": "backfill",
        }
    ).execute()


class _Contagem:
    """`canonizados`, `ja_canonicos`, `nao_cabem[motivo]`, `tipo_trocado[...]`
    per `tabela.campo` — counts only."""

    def __init__(self) -> None:
        self.dados: dict[str, dict[str, Any]] = {}

    def _slot(self, chave: str) -> dict[str, Any]:
        return self.dados.setdefault(
            chave,
            {"lidos": 0, "ja_canonicos": 0, "canonizados": 0, "nao_cabem": Counter(), "tipo_trocado": 0},
        )

    def visto(self, chave: str) -> None:
        self._slot(chave)["lidos"] += 1

    def ja_canonico(self, chave: str) -> None:
        self._slot(chave)["ja_canonicos"] += 1

    def canonizado(self, chave: str) -> None:
        self._slot(chave)["canonizados"] += 1

    def nao_cabe(self, chave: str, motivo: str) -> None:
        self._slot(chave)["nao_cabem"][motivo] += 1

    def tipo_trocado(self, chave: str) -> None:
        self._slot(chave)["tipo_trocado"] += 1

    def como_dict(self) -> dict[str, dict[str, Any]]:
        return {
            chave: {**slot, "nao_cabem": dict(sorted(slot["nao_cabem"].items()))}
            for chave, slot in sorted(self.dados.items())
        }


def _canonizar_valor(
    client: Any, org_id: UUID, contagem: _Contagem, chave: str, *, tabela: str,
    linha_id: str, campo: str, tipo: str, valor: Any, dry_run: bool, ctx: dict,
) -> Optional[str]:
    """Count + (maybe) log one stored value; returns the canonical form to
    write, or None when there is nothing to write."""
    if valor is None or not str(valor).strip():
        return None
    contagem.visto(chave)
    g = idf.para_gravar(tipo, valor, **ctx)
    if g.rejeitado_por_tipo:
        contagem.tipo_trocado(chave)
        contagem.nao_cabe(chave, g.motivo)
        return None
    if not g.canonico:
        contagem.nao_cabe(chave, g.motivo)
        return None
    if g.valor == str(valor):
        contagem.ja_canonico(chave)
        return None
    contagem.canonizado(chave)
    if not dry_run:
        _registrar_bruto(client, org_id, tabela, linha_id, campo, tipo, str(valor), g.valor or "")
    return g.valor


def canonizar_clientes(client: Any, org_id: UUID, contagem: _Contagem, *, dry_run: bool) -> None:
    rows = table_reads.paged_rows(
        client, "clientes", org_id,
        select="id,cpf,rg,rg_orgao_expedidor,endereco_cep",
    )
    for row in rows:
        patch: dict[str, Any] = {}
        # The RG is read with the UF of ITS OWN órgão (an RG from another state
        # is never forced into the SP mask) and the holder's CPF (the CIN's
        # identity number IS the CPF).
        contexto = {
            "cpf": {},
            "rg": {
                "uf": idf.uf_do_orgao(row.get("rg_orgao_expedidor")),
                "cpf_proprio": row.get("cpf") if idf.cabe("cpf", row.get("cpf")) else None,
            },
            "endereco_cep": {},
        }
        for campo, tipo in (("cpf", "cpf"), ("rg", "rg"), ("endereco_cep", "cep")):
            novo = _canonizar_valor(
                client, org_id, contagem, f"clientes.{campo}", tabela="clientes",
                linha_id=str(row["id"]), campo=campo, tipo=tipo, valor=row.get(campo),
                dry_run=dry_run, ctx=contexto[campo],
            )
            if novo is not None:
                patch[campo] = novo
        if patch and not dry_run:
            _t(client, "clientes").update(patch).eq("org_id", str(org_id)).eq(
                "id", str(row["id"])
            ).execute()


def canonizar_imovel_dados(client: Any, org_id: UUID, contagem: _Contagem, *, dry_run: bool) -> None:
    from app.modules.imovel_hub import dados_service

    rows = table_reads.paged_rows(
        client, "imovel_dados", org_id,
        select="codigo,numero_matricula,prefeitura_cadastro_imobiliario,endereco_manual_cep",
        order_col="codigo", id_key="codigo",
    )
    for row in rows:
        patch: dict[str, Any] = {}
        for campo, tipo in idf.TIPO_POR_CAMPO_ESCRITA_IMOVEL.items():
            valor = row.get(campo)
            ctx: dict[str, Any] = {}
            if tipo == "inscricao_municipal" and valor:
                ctx = {"municipio": dados_service.municipio_do_imovel(client, org_id, row["codigo"])}
            novo = _canonizar_valor(
                client, org_id, contagem, f"imovel_dados.{campo}", tabela="imovel_dados",
                linha_id=str(row["codigo"]), campo=campo, tipo=tipo, valor=valor,
                dry_run=dry_run, ctx=ctx,
            )
            if novo is not None:
                patch[campo] = novo
        if patch and not dry_run:
            _t(client, "imovel_dados").update(patch).eq("org_id", str(org_id)).eq(
                "codigo", row["codigo"]
            ).execute()


def canonizar_certidao_consultas(
    client: Any, org_id: UUID, contagem: _Contagem, *, dry_run: bool
) -> None:
    rows = table_reads.paged_rows(
        client, "certidao_consultas", org_id, select="id,tipo_documento,documento",
    )
    for row in rows:
        tipo = str(row.get("tipo_documento") or "").lower()
        if tipo not in ("cpf", "cnpj"):
            continue
        novo = _canonizar_valor(
            client, org_id, contagem, "certidao_consultas.documento",
            tabela="certidao_consultas", linha_id=str(row["id"]), campo="documento",
            tipo=tipo, valor=row.get("documento"), dry_run=dry_run, ctx={},
        )
        if novo is not None and not dry_run:
            _t(client, "certidao_consultas").update({"documento": novo}).eq(
                "org_id", str(org_id)
            ).eq("id", str(row["id"])).execute()


def diagnosticar_empresas(client: Any, org_id: UUID, contagem: _Contagem) -> None:
    """READ-ONLY: `empresas.cnpj` is the identity key (digits-only on purpose
    — migration 187), so it is never rewritten; this only reports whether
    each stored CNPJ FITS its type, so a bad one is visible."""
    for row in table_reads.paged_rows(client, "empresas", org_id, select="id,cnpj"):
        if not row.get("cnpj"):
            continue
        contagem.visto("empresas.cnpj")
        g = idf.para_gravar("cnpj", row["cnpj"])
        if g.canonico:
            contagem.ja_canonico("empresas.cnpj")  # fits; stored as the key, by design
        else:
            contagem.nao_cabe("empresas.cnpj", g.motivo)


# ─── B. pending conflicts ───────────────────────────────────────────────────


def resolver_conflitos_cliente(client: Any, org_id: UUID) -> dict:
    """The live path's own resolver over every pending identifier conflict.
    Under `--dry-run` the caller hands in the READ-ONLY client, so this
    reports exactly what a real run would decide, writing nothing."""
    from app.modules.card_hub import identidade_extracao_service as identidade_svc

    out = identidade_svc.backfill_resolver_conflitos_pendentes(
        client, org_id, campos=CAMPOS_CONFLITO_CLIENTE
    )
    por_regra = Counter(
        f"{r.get('campo')}:{r.get('decisao_regra')}" for r in out["resolvidos"]
    )
    return {
        "resolvidos": len(out["resolvidos"]),
        "por_regra": dict(sorted(por_regra.items())),
        "ainda_pendentes": len(out["ainda_pendentes"]),
        "ignorado_composto": len(out["ignorado_composto"]),
    }


def _decisao_equivalencia(campo: str, motivo: str) -> Decisao:
    return Decisao(
        vencedor="atual", regra="equivalencia",
        motivo=f"{campo}: as duas leituras são o mesmo identificador ({motivo}) — nada a decidir.",
        requer_humano=False,
    )


def resolver_conflitos_imovel(client: Any, org_id: UUID, *, dry_run: bool) -> dict:
    """Equivalence only: matrícula / inscrição municipal / cartório have no
    check digit, so a pending conflict that is the same identifier in two
    spellings is closed `resolvido_automatico`; anything else stays for a
    human, untouched."""
    from app.modules.imovel_hub import campos_extraidos_service as campos_svc
    from app.modules.imovel_hub import dados_service

    pendentes = [
        r for r in table_reads.paged_rows(
            client, "imovel_campo_conflitos", org_id, eq_filters={"status": "pendente"},
        )
        if r.get("campo") in CAMPOS_CONFLITO_IMOVEL
    ]
    resolvidos = 0
    por_campo: Counter[str] = Counter()
    for row in pendentes:
        campo = campos_svc.CAMPOS.get(row["campo"])
        if campo is None:
            continue
        anterior, proposto = row.get("valor_anterior"), row.get("valor_proposto")
        mesmo = campos_svc.iguais(campo, anterior, proposto)
        if not mesmo and row["campo"] == "prefeitura_cadastro_imobiliario":
            mesmo = idf.iguais(
                "inscricao_municipal", anterior, proposto,
                municipio=dados_service.municipio_do_imovel(client, org_id, row["codigo"]),
            )
        if not mesmo:
            continue
        resolvidos += 1
        por_campo[row["campo"]] += 1
        if not dry_run:
            campo_conflitos.registrar_decisao_automatica(
                client, campo_conflitos.IMOVEL, org_id, row["codigo"], row["campo"],
                valor_anterior=anterior, origem_anterior=row.get("origem_anterior"),
                valor_proposto=proposto, origem_proposto=row.get("origem_proposto"),
                decisao=_decisao_equivalencia(row["campo"], "formatação"),
                conflito_existente_id=row["id"],
            )
    return {
        "pendentes": len(pendentes),
        "resolvidos": resolvidos,
        "por_campo": dict(sorted(por_campo.items())),
        "ainda_pendentes": len(pendentes) - resolvidos,
    }


def resolver_conflitos_empresa(client: Any, org_id: UUID) -> dict:
    """No identifier field lives in `empresa_campo_conflitos` (razão social,
    situação cadastral, … — and a divergent CNPJ is an `aviso`, never a
    conflict row), so there is nothing to equate; counted so the absence is
    a measured fact, not a silent skip."""
    pendentes = table_reads.paged_rows(
        client, "empresa_campo_conflitos", org_id, eq_filters={"status": "pendente"},
    )
    campos = Counter(str(r.get("campo")) for r in pendentes)
    return {"pendentes": len(pendentes), "por_campo": dict(sorted(campos.items())), "resolvidos": 0}


# ─── entry point ────────────────────────────────────────────────────────────


class _EscritaNula:
    """Any write chain (`.update(..).eq(..).execute()`) that lands nowhere."""

    def __getattr__(self, _nome: str):
        return lambda *a, **k: self

    def execute(self) -> Any:
        from types import SimpleNamespace

        return SimpleNamespace(data=[], count=None)


class _TabelaSomenteLeitura:
    def __init__(self, tabela: Any) -> None:
        self._tabela = tabela

    def __getattr__(self, nome: str) -> Any:
        return getattr(self._tabela, nome)

    def insert(self, *_a: Any, **_k: Any) -> _EscritaNula:
        return _EscritaNula()

    update = delete = upsert = insert


class _ClienteSomenteLeitura:
    """`--dry-run` by CONSTRUCTION, not by a flag every write site must
    remember: reads pass through, every write is dropped. The real resolvers
    (`backfill_resolver_conflitos_pendentes`, `registrar_decisao_automatica`)
    run over it unchanged, so the dry-run report is what the real run would
    decide."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def table(self, nome: str) -> _TabelaSomenteLeitura:
        return _TabelaSomenteLeitura(self._client.table(nome))

    def __getattr__(self, nome: str) -> Any:
        return getattr(self._client, nome)


def run_backfill(client: Any, org_id: UUID, *, dry_run: bool = False) -> dict:
    """The whole backfill. Counts only; idempotent. `dry_run=True` runs the
    same code over a READ-ONLY client: nothing is canonicalised, no log row is
    written, no conflict is closed — and the report is what a real run would
    do."""
    if dry_run:
        client = _ClienteSomenteLeitura(client)
    contagem = _Contagem()
    canonizar_clientes(client, org_id, contagem, dry_run=dry_run)
    canonizar_imovel_dados(client, org_id, contagem, dry_run=dry_run)
    canonizar_certidao_consultas(client, org_id, contagem, dry_run=dry_run)
    diagnosticar_empresas(client, org_id, contagem)
    relatorio = {
        "dry_run": dry_run,
        "valores": contagem.como_dict(),
        "conflitos": {
            "cliente_campo_conflitos": resolver_conflitos_cliente(client, org_id),
            "imovel_campo_conflitos": resolver_conflitos_imovel(client, org_id, dry_run=dry_run),
            "empresa_campo_conflitos": resolver_conflitos_empresa(client, org_id),
        },
    }
    logger.info("identificadores.backfill org=%s %s", org_id, relatorio)
    return relatorio


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.services.identificadores_backfill",
        description=(
            "Zero-API backfill: canonicalise stored identifiers and re-resolve "
            "pending conflicts from stored data only (counts-only report)."
        ),
    )
    parser.add_argument("--org", required=True, help="org UUID")
    parser.add_argument("--dry-run", action="store_true", help="count only, write nothing")
    args = parser.parse_args(argv)

    from app.dependencies import get_scoped_admin_client

    resultado = run_backfill(get_scoped_admin_client(), UUID(args.org), dry_run=args.dry_run)
    print(json.dumps(resultado, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


__all__ = [
    "CAMPOS_CONFLITO_CLIENTE",
    "CAMPOS_CONFLITO_IMOVEL",
    "canonizar_certidao_consultas",
    "canonizar_clientes",
    "canonizar_imovel_dados",
    "diagnosticar_empresas",
    "main",
    "resolver_conflitos_cliente",
    "resolver_conflitos_empresa",
    "resolver_conflitos_imovel",
    "run_backfill",
]

if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    sys.exit(main())
