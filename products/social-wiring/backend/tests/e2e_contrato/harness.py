#!/usr/bin/env python3
"""Read-only e2e harness for social-wiring's contract generator
(`app.modules.card_hub.contrato_gerador`) — proves, against a REAL card in
a REAL org, that:

1. the card loads exactly like production (`carregador.carregar` +
   `derivacao.avaliar` + `proveniencia.linhagem.linhagem_do_card`);
2. its readiness (`pronto?`, `faltando`, `bloqueios`, `avisos`) and the
   validation gate (`validacao_extracao.situacao` — the pending
   machine-extracted fields that would 409 `EXTRACAO_PENDENTE_VALIDACAO`
   on `POST .../gerar`) are reported honestly;
3. the contract renders in memory with the REAL docx adapter
   (`documento.renderizar` + `documento.gerar_pdf`) WITHOUT persisting a
   version — `service.gerar`'s render/lint/pdf steps, minus the
   `contratos_service.nova_versao_gerada` write;
4. when a reference `.docx` is given, the render is diffed against it
   (`comparador.py`), categorised as missing clause / wrong value / extra
   clause / formatting;
5. every missing/gap field is traced, where the field is inside the
   provenance REGISTRO (`validacao_extracao.REGISTRO`), to "document
   missing" / "extraction pending validation" / "manual field empty" —
   honestly reported as "outside the provenance ledger's scope" when the
   field is not one `linhagem_do_card` covers (financiamento, negociação,
   permuta, certidões, imobiliária, intermediação — see
   `proveniencia.linhagem`'s own module docstring "Scope" paragraph).

NEVER WRITES. `service.gerar`'s only side-effecting step
(`contratos_service.nova_versao_gerada`) is never called — everything this
module does mirrors `service.obter_geracao` + `service.gerar`'s render/lint
path, stopping one step short of the save.

PII: every function here returns/prints REAL values it reads from
production when asked to (`--mostrar-valores`) — the caller's terminal is
the caller's own session, not this repo. The default CLI output redacts to
counts + categories + document TYPES only (see `main()`); nothing this
module writes to disk (there is no disk write in the entire module) ever
carries a real name/CPF/address.

USAGE
-----
    cd products/social-wiring/backend/tests/e2e_contrato
    <repo-venv-python> harness.py \\
        --org <org_id> --cliente <cliente_id> --contrato <contrato_id> \\
        [--referencia /path/to/reference.docx] [--redigir]

    <repo-venv-python> harness.py --org <org_id> --descobrir --min-documentos 3

Both subcommands are READ-ONLY. `--redigir` (default ON) prints only
OK/MISSING/DIFF + counts; pass `--mostrar-valores` to see real field values
in a private terminal (never redirect that output into the repo).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

# ─── bootstrap: make `app.*` / `noctusai_lib` / `noctusai_seed` importable
#     when this file is run directly (not through pytest, which already
#     does this via its own rootdir insertion). Mirrors
#     `mcp/noctusai/tools/noctus/dev/testing.py::_worktree_pythonpath` so a
#     worktree's own seed copies are used, never the shared venv's
#     editable-installed primary copy. ─────────────────────────────────────
_THIS_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = _THIS_DIR.parents[1]  # products/social-wiring/backend
_REPO_ROOT = _BACKEND_ROOT.parents[2]  # repo root (or worktree root)
for _p in (
    str(_THIS_DIR),
    str(_BACKEND_ROOT),
    str(_REPO_ROOT / "seed" / "framework" / "backend"),
    str(_REPO_ROOT / "seed" / "lib" / "backend"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import comparador  # noqa: E402  (path insert must precede this)


# ─── readiness ──────────────────────────────────────────────────────────
#
# 🔴 NO RE-IMPLEMENTATION (2026-10-03). This used to compute `pode_gerar`
# from the per-field pending list (`validacao_extracao.situacao`) — the
# rollback mode. Production runs `Politica.revisao_final_unica=True`, where
# machine-pending values do NOT block `gerar` (they ride on the version for
# the one legal review) and only open CONFLICTS refuse. Readiness now comes
# from the SAME service calls production makes, with the SAME policy DI
# resolves (`deps.get_politica_contrato`):
#
# - `service.obter_geracao` — the GET readiness report (`pronto`, `faltando`,
#   `bloqueios`, `avisos`, `confirmacoes`, `modelo_derivado`);
# - `service.precondicao_gerar` — the extraction precondition `service.gerar`
#   itself calls first (per mode), its `ExtracaoPendenteValidacao` read as the
#   refusal it is.


@dataclass
class Prontidao:
    contrato_id: str
    pronto: bool
    modelo_derivado: str
    modelo_confere: bool
    pode_gerar: bool  #: `obter_geracao.pronto` AND the extraction precondition does not refuse
    revisao_final_unica: bool = True
    faltando: list[dict] = field(default_factory=list)
    bloqueios: list[dict] = field(default_factory=list)
    avisos: list[dict] = field(default_factory=list)
    confirmacoes: list[dict] = field(default_factory=list)
    pendentes: list[dict] = field(default_factory=list)  #: refusing pendentes (rollback mode only)
    conflitos: list[dict] = field(default_factory=list)
    revisao_campos: list[dict] = field(default_factory=list)  #: recorded for the legal review (non-blocking)


def _client() -> Any:
    """The exact schema-scoped admin client production DI resolves
    (`card_hub.deps.get_card_hub_client`) — real Supabase unless
    `DATABASE_BACKEND=sqlite` is set (see `app.dependencies._use_sqlite`)."""
    from app.modules.card_hub.deps import get_card_hub_client

    return get_card_hub_client()


def politica_producao() -> Any:
    """The policy production DI hands every contract-generation endpoint."""
    from app.modules.card_hub.contrato_gerador.deps import get_politica_contrato

    return get_politica_contrato()


def carregar_dados(client: Any, org_id: UUID, cliente_id: UUID, contrato_id: UUID):
    from app.modules.card_hub.contrato_gerador.carregador import carregar

    return carregar(client, org_id, cliente_id, contrato_id, usuario_id=None)


def precondicao_extracao(client: Any, org_id: UUID, dados, politica) -> dict:
    """`service.precondicao_gerar` — the very function `service.gerar` runs
    first — with its refusal (`ExtracaoPendenteValidacao`) read as data.
    Returns `{bloqueia, pendentes, conflitos, revisao_campos}`; never writes."""
    from app.modules.card_hub.contrato_gerador.service import precondicao_gerar
    from app.modules.card_hub.contrato_gerador.validacao_extracao import ExtracaoPendenteValidacao

    try:
        revisao = precondicao_gerar(client, org_id, dados, usuario_id=None, politica=politica)
        return {"bloqueia": False, "pendentes": [], "conflitos": [], "revisao_campos": revisao}
    except ExtracaoPendenteValidacao as exc:
        return {
            "bloqueia": True,
            "pendentes": list(exc.details.get("pendentes") or []),
            "conflitos": list(exc.details.get("conflitos") or []),
            "revisao_campos": [],
        }


def relatorio_prontidao(client: Any, org_id: UUID, cliente_id: UUID, contrato_id: UUID) -> tuple[Prontidao, Any]:
    """Returns `(Prontidao, dados)` — `dados` handed back so the caller can
    render/trace. `obter_geracao` loads the card itself (it is the endpoint's
    own function); `dados` is loaded once more for the render, read-only."""
    from app.modules.card_hub.contrato_gerador.service import obter_geracao

    politica = politica_producao()
    geracao = obter_geracao(client, org_id, cliente_id, contrato_id, usuario_id=None, politica=politica)
    dados, _atendimento_id = carregar_dados(client, org_id, cliente_id, contrato_id)
    pre = precondicao_extracao(client, org_id, dados, politica)
    prontidao = Prontidao(
        contrato_id=str(contrato_id),
        pronto=geracao["pronto"],
        modelo_derivado=geracao["modelo_derivado"],
        modelo_confere=geracao["modelo_confere"],
        pode_gerar=geracao["pronto"] and not pre["bloqueia"],
        revisao_final_unica=geracao["revisao_final_unica"],
        faltando=geracao["faltando"],
        bloqueios=geracao["bloqueios"],
        avisos=geracao["avisos"],
        confirmacoes=geracao.get("confirmacoes") or [],
        pendentes=pre["pendentes"],
        conflitos=pre["conflitos"],
        revisao_campos=pre["revisao_campos"],
    )
    return prontidao, dados


# ─── in-memory render (no persistence) ─────────────────────────────────

#: Printable free-text fields a not-`pronto` card may leave empty. Only these
#: are replaced by `comparador.MARCADOR_LACUNA` — never a CODE field
#: (estado_civil, regime_bens, genero, resultado, forma_pagamento, *_id, …),
#: whose value the context builder looks up in a phrase table and which a
#: marker would turn into a KeyError instead of a visible gap.
CAMPOS_TEXTO_MARCAVEIS = frozenset(
    {
        "nome", "nacionalidade", "profissao", "cpf", "rg", "rg_orgao", "email",
        "logradouro", "numero", "complemento", "bairro", "cidade", "uf", "cep",
        "razao_social", "banco", "agencia", "conta", "pix", "cpf_cnpj", "creci",
        "documento", "representante_nome", "representante_cpf", "endereco_registro_texto",
        "inscricao_municipal", "numero_registro_imoveis",
    }
)


#: Required DATE fields the context builder formats unconditionally — filled
#: with the date sentinel `comparador.DATA_LACUNA` when empty.
CAMPOS_DATA_MARCAVEIS = frozenset({"emitida_em", "data_casamento"})

#: Agreement stand-in for a printed person whose gender is missing (marker mode only).
GENERO_LACUNA = "m"


def dados_com_marcadores(dados: Any) -> tuple[Any, int]:
    """`(copy, n_marcadores)` — a copy of `dados` a not-`pronto` card can be
    rendered from with its gaps VISIBLE instead of as silently missing words:

    - every EMPTY printable text field (`CAMPOS_TEXTO_MARCAVEIS`, declared
      `str`) carries `comparador.MARCADOR_LACUNA`; every empty required
      date (`CAMPOS_DATA_MARCAVEIS`) the date sentinel
      `comparador.DATA_LACUNA` (01/01/1900); every empty `*_dias` int the
      day-count sentinel `comparador.INTEIRO_LACUNA` (999);
    - the two STRUCTURAL inputs the context builder refuses to go without
      (it asserts them — `contexto.montar_contexto`, "# gated") get the money
      sentinel `comparador.VALOR_LACUNA` (R$ 0,01, itself a gap marker for
      the scorecard): a missing `valor_negociado`, a parcela with no
      `valor`, and — when the deal has no `sinal` parcela at all — one
      synthetic `sinal` parcela worth the sentinel.

    Never mutates `dados`; code fields are left exactly as loaded. A gap
    the template cannot be fed a stand-in for (no imóvel at all) still makes
    the render fail — reported as such, never papered over."""
    import dataclasses
    from datetime import date
    from decimal import Decimal

    from app.modules.card_hub.contrato_gerador.concordancia import normalizar_genero

    contagem = 0
    valor_lacuna = Decimal(comparador.VALOR_LACUNA)
    data_lacuna = date.fromisoformat(comparador.DATA_LACUNA)

    def _visita(obj: Any) -> Any:
        nonlocal contagem
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            mudancas: dict[str, Any] = {}
            for f in dataclasses.fields(obj):
                valor = getattr(obj, f.name)
                tipo = f.type if isinstance(f.type, str) else getattr(f.type, "__name__", str(f.type))
                if f.name in CAMPOS_TEXTO_MARCAVEIS and valor in (None, "") and "str" in tipo:
                    mudancas[f.name] = comparador.MARCADOR_LACUNA
                    contagem += 1
                    continue
                if f.name == "genero" and normalizar_genero(valor) is None:
                    # A printed person's gender is a CODE field (agreement
                    # tokens), so it cannot carry the text marker; the
                    # generator refuses to guess it in production
                    # (`genero_exigido`). Marker mode needs SOME agreement to
                    # render at all, so it takes the grammatical default —
                    # counted as a marker, and the gap stays reported by the
                    # readiness gate (`qualificacao.genero`), never hidden.
                    mudancas[f.name] = GENERO_LACUNA
                    contagem += 1
                    continue
                if f.name.endswith("_dias") and valor is None and "int" in tipo:
                    mudancas[f.name] = comparador.INTEIRO_LACUNA
                    contagem += 1
                    continue
                if f.name in CAMPOS_DATA_MARCAVEIS and valor is None and "date" in tipo:
                    mudancas[f.name] = data_lacuna
                    contagem += 1
                    continue
                novo = _visita(valor)
                if novo is not valor:
                    mudancas[f.name] = novo
            return dataclasses.replace(obj, **mudancas) if mudancas else obj
        if isinstance(obj, list):
            novos = [_visita(v) for v in obj]
            return novos if any(a is not b for a, b in zip(novos, obj)) else obj
        if isinstance(obj, tuple) and not hasattr(obj, "_fields"):
            novos_t = tuple(_visita(v) for v in obj)
            return novos_t if any(a is not b for a, b in zip(novos_t, obj)) else obj
        return obj

    marcado = _visita(dados)
    estruturais: dict[str, Any] = {}
    if getattr(marcado, "valor_negociado", "ausente") is None:
        estruturais["valor_negociado"] = valor_lacuna
        contagem += 1
    parcelas = list(getattr(marcado, "parcelas", []) or [])
    if parcelas or hasattr(marcado, "parcelas"):
        novas = []
        for p in parcelas:
            if p.valor is None:
                p = dataclasses.replace(p, valor=valor_lacuna)
                contagem += 1
            novas.append(p)
        if not any(p.tipo == "sinal" for p in novas):
            from app.modules.card_hub.contrato_gerador.dados import Parcela

            primeira = min((p.ordem for p in novas), default=1)
            novas.insert(
                0,
                Parcela(
                    id="lacuna-sinal",
                    tipo="sinal",
                    valor=valor_lacuna,
                    vencimento=None,
                    evento=comparador.MARCADOR_LACUNA,
                    forma_pagamento=None,
                    favorecido_id=None,
                    confissao_divida=False,
                    ordem=primeira - 1,
                ),
            )
            contagem += 1
        if novas != parcelas:
            estruturais["parcelas"] = novas
    termos = getattr(marcado, "termos", None)
    if termos is not None and termos.posse_marco == "data_fixa" and termos.posse_data is None:
        # A fixed-date posse (migration 201) the render cannot go without.
        estruturais["termos"] = dataclasses.replace(termos, posse_data=data_lacuna)
        contagem += 1
    if estruturais:
        marcado = dataclasses.replace(marcado, **estruturais)
    return marcado, contagem


def switches_producao(dados) -> dict[str, bool]:
    """`derivacao.derivar_switches` with the production policy and today —
    the same call `service.gerar` makes before rendering."""
    from app.modules.card_hub.contrato_gerador.derivacao import derivar_switches
    from app.modules.card_hub.contrato_gerador.service import hoje

    return derivar_switches(dados, politica_producao(), hoje())


def clausulas_desligadas(switches: dict[str, bool]) -> list[str]:
    """Heading titles of the conditional clauses these switches turn OFF
    (`numeracao.CLAUSULA_CONDICIONAL` → `TITULO_CLAUSULA`) — read from the
    generator's own tables, never a hand-kept list."""
    from app.modules.card_hub.contrato_gerador.numeracao import CLAUSULA_CONDICIONAL, TITULO_CLAUSULA

    return [
        TITULO_CLAUSULA[chave]
        for chave, switch in CLAUSULA_CONDICIONAL.items()
        if not switches.get(switch, False) and chave in TITULO_CLAUSULA
    ]


def renderizar_em_memoria(dados, *, com_marcadores: bool = False) -> Any:
    """`documento.renderizar` with the REAL docx adapter and the production
    policy — `service.gerar`'s own sequence (one `hoje()` snapshot for
    switches + render, `data_assinatura(dados, None)`), minus the save.

    `com_marcadores=True` (a not-`pronto` card): switches are derived from the
    card AS LOADED (a marker must never flip a switch), then the template is
    rendered from `dados_com_marcadores(dados)`. Raises whatever the template
    raises — the caller reports it."""
    from noctusai_lib.integrations.docx_render import get_docx_render_adapter

    from app.modules.card_hub.contrato_gerador.derivacao import derivar_switches
    from app.modules.card_hub.contrato_gerador.documento import renderizar
    from app.modules.card_hub.contrato_gerador.service import data_assinatura, hoje

    politica = politica_producao()
    referencia = hoje()
    switches = derivar_switches(dados, politica, referencia)
    assinatura = data_assinatura(dados, None)
    alvo = dados_com_marcadores(dados)[0] if com_marcadores else dados
    adapter = get_docx_render_adapter(real=True)
    return renderizar(adapter, alvo, switches, politica, assinatura, referencia)


def lint_renderizado(renderizado) -> list[dict]:
    from app.modules.card_hub.contrato_gerador.lint import lint

    return lint(renderizado.paragrafos, referencias=renderizado.referencias, clausulas=renderizado.clausulas)


# ─── provenance ─────────────────────────────────────────────────────────


def provenance(client: Any, org_id: UUID, cliente_id: UUID, contrato_id: UUID) -> dict:
    """`proveniencia.linhagem.linhagem_do_card` verbatim — the public
    endpoint's own answer, unmodified."""
    from app.modules.card_hub.proveniencia.linhagem import linhagem_do_card

    return linhagem_do_card(client, org_id, cliente_id, contrato_id)


# ─── per-gap traceability (document missing / extraction pending / manual) ─

CATEGORIA_MANUAL = "manual_vazio"
CATEGORIA_DOCUMENTO_AUSENTE = "documento_ausente"
CATEGORIA_EXTRACAO_PENDENTE = "extracao_pendente_validacao"
CATEGORIA_FORA_DE_ESCOPO = "fora_do_escopo_da_linhagem"


def _mapa_linhagem_detalhado(client: Any, org_id: UUID, dados, contrato_id: UUID) -> dict[tuple[str, str, str], dict]:
    """Same computation `linhagem_do_card` does, keyed by
    `(entidade, entidade_id, campo)` instead of a flat list — the public
    function drops `entidade_id` (a card's "Proveniência" tab does not
    need it, one row per field is already scoped to the card), but a
    cross-reference against `avaliacao.faltando`'s `parte_id` needs it to
    disambiguate two parties with the same missing field. Reuses
    `linhagem`'s own private per-field helpers (`_estado`/`_documento`/
    `_fontes_possiveis`) rather than re-deriving their logic — same
    inputs, same outputs, this module just keeps the id the public shape
    throws away."""
    from app.modules.card_hub.contrato_gerador import validacao_extracao as vx
    from app.modules.card_hub.proveniencia import linhagem as linhagem_mod

    coleta = vx.coletar(client, org_id, dados, None)
    pares = linhagem_mod._todos_ativos(coleta)  # noqa: SLF001 — see docstring
    fontes = vx.documentos_de_origem(client, org_id, pares)
    decisoes = linhagem_mod._decisoes_recentes(client, org_id, contrato_id)  # noqa: SLF001
    mapa: dict[tuple[str, str, str], dict] = {}
    for alvo, campo in pares:
        ch = vx.chave(campo.entidade, alvo.entidade_id, campo.campo)
        decisao = decisoes.get(ch)
        mapa[(campo.entidade, alvo.entidade_id, campo.campo)] = {
            "estado": linhagem_mod._estado(campo, alvo.row),  # noqa: SLF001
            "documento": linhagem_mod._documento(campo, alvo, fontes, decisao),  # noqa: SLF001
            "fontes_possiveis": linhagem_mod._fontes_possiveis(campo.entidade, campo.campo, destino=None),  # noqa: SLF001
        }
    return mapa


def _resolver_cliente_id(dados, parte_id: Optional[str]) -> Optional[str]:
    if parte_id is None:
        return dados.cliente_id  # the titular has no atendimento_partes row
    for p in (*dados.vendedores, *dados.compradores):
        if p.parte_id == parte_id:
            return p.cliente_id
    return None


def classificar_gap(item: dict, dados, mapa_linhagem: dict[tuple[str, str, str], dict]) -> dict:
    """One `avaliacao.faltando` (or `bloqueios`) item -> a traceability
    verdict. Honest by construction: a field this harness cannot locate in
    `validacao_extracao.REGISTRO` (financiamento/negociação/permuta/
    certidões/imobiliária/intermediação/contrato-level fields — see
    `proveniencia.linhagem`'s own "Scope" docstring) is reported
    `fora_do_escopo_da_linhagem`, never guessed at."""
    from app.modules.card_hub.contrato_gerador import validacao_extracao as vx

    campo_str = item["campo"]
    nome_campo = campo_str.rsplit(".", 1)[-1]
    entidade: Optional[str] = None
    entidade_id: Optional[str] = None
    if campo_str.startswith("qualificacao."):
        entidade = vx.ENTIDADE_CLIENTE
        entidade_id = _resolver_cliente_id(dados, item.get("parte_id"))
    elif campo_str.startswith("imovel.") or campo_str.startswith("matricula."):
        entidade = vx.ENTIDADE_IMOVEL
        entidade_id = dados.imovel.codigo if dados.imovel is not None else None

    info = mapa_linhagem.get((entidade, entidade_id, nome_campo)) if entidade and entidade_id else None
    if info is None:
        return {
            "campo": campo_str,
            "categoria": CATEGORIA_FORA_DE_ESCOPO,
            "nota": "campo fora do REGISTRO de proveniência (linhagem_do_card) — "
            "ver 'onde'/'sugestoes' do próprio item de faltando",
        }
    if info["estado"] == "maquina_pendente":
        doc = info["documento"] or {}
        return {
            "campo": campo_str,
            "categoria": CATEGORIA_EXTRACAO_PENDENTE,
            "documento_tipo": doc.get("tipo"),
            "documento_entrada": doc.get("entrada"),
        }
    tipos = [s.get("tipo_documento") for s in info["fontes_possiveis"]]
    if tipos == [None]:
        return {"campo": campo_str, "categoria": CATEGORIA_MANUAL}
    if info["estado"] == "vazio":
        return {
            "campo": campo_str,
            "categoria": CATEGORIA_DOCUMENTO_AUSENTE,
            "candidatos_tipo_documento": [t for t in tipos if t],
        }
    return {"campo": campo_str, "categoria": "outro", "estado_linhagem": info["estado"]}


def tracar_gaps(client: Any, org_id: UUID, cliente_id: UUID, contrato_id: UUID, dados, prontidao: Prontidao) -> list[dict]:
    mapa = _mapa_linhagem_detalhado(client, org_id, dados, contrato_id)
    return [classificar_gap(item, dados, mapa) for item in prontidao.faltando]


# ─── discovery (org-wide scan for ≥N-document cards) ────────────────────


def descobrir_cards_com_documentos(client: Any, org_id: UUID, minimo: int = 3) -> list[dict]:
    """Every `clientes` row in `org_id` with >= `minimo` LIVE documents
    (`cliente_documentos`, `deleted_at is null`) — read-only, no
    extraction/derivation run. Returns `[{cliente_id, documentos}]` sorted
    by `documentos` DESC (no names — the caller redacts further)."""
    from app.services import table_reads

    rows = table_reads.paged_rows(
        client,
        "cliente_documentos",
        org_id,
        refine=lambda q: q.is_("deleted_at", "null"),
        select="id,cliente_id",
    )
    contagem: dict[str, int] = {}
    for row in rows:
        cid = str(row["cliente_id"])
        contagem[cid] = contagem.get(cid, 0) + 1
    itens = [{"cliente_id": cid, "documentos": n} for cid, n in contagem.items() if n >= minimo]
    itens.sort(key=lambda i: i["documentos"], reverse=True)
    return itens


def contrato_mais_recente(client: Any, org_id: UUID, cliente_id: UUID) -> Optional[str]:
    """The most recently CREATED `atendimento_contratos` row for this
    card (`contratos_service.listar` already sorts newest-first), or
    `None` when the card has no contract yet."""
    from app.modules.card_hub import contratos_service as contratos_svc

    try:
        linhas = contratos_svc.listar(client, org_id, cliente_id)["contratos"]
    except Exception:
        return None
    if not linhas:
        return None
    return str(linhas[0]["id"])


# ─── batch scoring (noctus.dev.contract_score's engine) ─────────────────


def pontuar_deal(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    contrato_id: Optional[UUID],
    ref_paragrafos: list[str],
    *,
    allowlist: list,
    limiares: Any,
) -> dict:
    """One deal → `{"resumo": <verdict-level>, "detalhe": <private, masked>}`.

    A `pronto` card renders exactly as production would; a not-`pronto` card
    renders with explicit gap markers (`dados_com_marcadores`) so its gaps
    are counted apart from wording/number diffs. The readiness gaps
    (`faltando` / `bloqueios` / `confirmacoes` / refusing conflicts) are
    reported by FIELD NAME + count only — never a value."""
    if contrato_id is None:
        resolved = contrato_mais_recente(client, org_id, cliente_id)
        if resolved is None:
            return {"resumo": {"veredito": "sem_contrato"}, "detalhe": {"veredito": "sem_contrato"}}
        contrato_id = UUID(resolved)
    prontidao, dados = relatorio_prontidao(client, org_id, cliente_id, contrato_id)
    gaps = {
        "pronto": prontidao.pronto,
        "pode_gerar": prontidao.pode_gerar,
        "revisao_final_unica": prontidao.revisao_final_unica,
        "faltando": len(prontidao.faltando),
        "bloqueios": len(prontidao.bloqueios),
        "confirmacoes_pendentes": sum(1 for c in prontidao.confirmacoes if not c.get("ciente")),
        "conflitos_extracao": len(prontidao.conflitos),
        "pendentes_extracao_bloqueantes": len(prontidao.pendentes),
        "revisao_campos": len(prontidao.revisao_campos),
    }
    gaps_campos = {
        "faltando": sorted({f.get("campo", "?") for f in prontidao.faltando}),
        "bloqueios": sorted({b.get("codigo", "?") for b in prontidao.bloqueios}),
    }
    com_marcadores = not prontidao.pronto
    modo = "marcadores" if com_marcadores else "producao"
    marcadores = dados_com_marcadores(dados)[1] if com_marcadores else 0
    try:
        renderizado = renderizar_em_memoria(dados, com_marcadores=com_marcadores)
    except Exception as exc:  # noqa: BLE001 — reported (class only), never swallowed
        # A pronto card that fails to render is a generator defect
        # (`render_falhou`). A not-pronto card whose gaps the template
        # cannot be fed a neutral stand-in for (e.g. a missing gênero — the
        # generator refuses to guess agreement since the 2026-10-03
        # hardening, and guessing here would mislabel wording) is a gap that
        # blocks rendering (`incompleto_sem_render`) — never a wording verdict.
        resumo = {
            "veredito": "incompleto_sem_render" if com_marcadores else "render_falhou",
            "render_modo": modo,
            "render_erro": type(exc).__name__,
            "gaps": gaps,
        }
        return {"resumo": resumo, "detalhe": {**resumo, "gaps_campos": gaps_campos}}
    achados = lint_renderizado(renderizado)
    card = comparador.pontuar(
        ref_paragrafos,
        comparador.paragrafos_de_lista(renderizado.paragrafos),
        allowlist=allowlist,
        limiares=limiares,
        clausulas_desligadas=clausulas_desligadas(switches_producao(dados)),
        # the card DECLARED its certidão data missing: a party left without
        # certidões is a gap (`incompleto`), not a material failure
        certidoes_ausentes_sao_lacuna=any(str(f.get("campo", "")).startswith("certidao.") for f in prontidao.faltando),
    )
    veredito = card.veredito
    if veredito in ("aprovado", "aprovado_com_observacoes") and not prontidao.pode_gerar:
        # Text matches, but production would still refuse this card — the
        # verdict must never read "aprovado" for a contract that cannot be
        # generated (e.g. a refusing extraction conflict, an unacknowledged
        # confirmation with no printable gap).
        veredito = "incompleto"
    resumo = {
        **card.resumo(),
        "veredito": veredito,
        "veredito_texto": card.veredito,
        "render_modo": modo,
        "campos_marcados": marcadores,
        "lint_achados": len(achados),
        "gaps": gaps,
    }
    detalhe = {
        **card.detalhe(),
        "veredito": veredito,
        "veredito_texto": card.veredito,
        "render_modo": modo,
        "campos_marcados": marcadores,
        "lint_codigos": sorted({a.get("codigo", "?") for a in achados}),
        "gaps": gaps,
        "gaps_campos": gaps_campos,
    }
    return {"resumo": resumo, "detalhe": detalhe}


def _escrever_privado(caminho: Path, payload: Any) -> None:
    """0600 atomic write — the scorecard lives on private disk only."""
    import os

    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp, caminho)


def executar_lote(entrada: Path, saida: Path) -> dict:
    """`entrada` (private JSON, written by `noctus.dev.contract_score`):
    `{"org_id", "allowlist"?, "limiares"?, "deals": [{"numero", "cliente_id",
    "contrato_id"?, "ref_paragrafos"}]}`. Writes the full (masked) scorecard
    to `saida` (0600) and RETURNS the verdict-level summary only."""
    pedido = json.loads(Path(entrada).read_text(encoding="utf-8"))
    org_id = UUID(pedido["org_id"])
    allowlist = comparador.carregar_allowlist(Path(pedido["allowlist"]) if pedido.get("allowlist") else None)
    limiares = (
        comparador.Limiares.de_dict(pedido["limiares"])
        if isinstance(pedido.get("limiares"), dict)
        else comparador.Limiares.de_arquivo(Path(pedido["limiares"]) if pedido.get("limiares") else None)
    )
    client = _client()
    resumos: dict[str, Any] = {}
    detalhes: dict[str, Any] = {}
    for deal in pedido["deals"]:
        numero = str(deal["numero"])
        try:
            r = pontuar_deal(
                client,
                org_id,
                UUID(deal["cliente_id"]),
                UUID(deal["contrato_id"]) if deal.get("contrato_id") else None,
                deal["ref_paragrafos"],
                allowlist=allowlist,
                limiares=limiares,
            )
        except Exception as exc:  # noqa: BLE001 — per-deal, reported by class, the batch goes on
            r = {"resumo": {"veredito": "erro", "erro": type(exc).__name__}, "detalhe": {"veredito": "erro", "erro": type(exc).__name__}}
        resumos[numero] = r["resumo"]
        detalhes[numero] = r["detalhe"]
    contagem: dict[str, int] = {}
    for r in resumos.values():
        contagem[r["veredito"]] = contagem.get(r["veredito"], 0) + 1
    total = {
        "deals": len(resumos),
        "por_veredito": contagem,
        "aprovados": contagem.get("aprovado", 0) + contagem.get("aprovado_com_observacoes", 0),
        "limiares": asdict(limiares),
        "allowlist_entradas": len(allowlist),
        "allowlist_aprovadas": sum(1 for e in allowlist if e.aprovado_pelo_dono),
    }
    _escrever_privado(Path(saida), {"total": total, "deals": detalhes})
    return {"total": total, "deals": resumos}


# ─── CLI ─────────────────────────────────────────────────────────────────


def _redigir_faltando(faltando: list[dict]) -> list[dict]:
    return [{"campo": f["campo"], "rotulo": f["rotulo"], "onde": f["onde"]} for f in faltando]


def _redigir_gap(gap: dict) -> dict:
    out = {"campo": gap["campo"], "categoria": gap["categoria"]}
    if "candidatos_tipo_documento" in gap:
        out["candidatos_tipo_documento"] = gap["candidatos_tipo_documento"]
    if "documento_tipo" in gap:
        out["documento_tipo"] = gap["documento_tipo"]
    return out


def _redigir_diferenca(d) -> dict:
    return {"tipo": d.tipo, "n_paragrafos_ref": len(d.ref), "n_paragrafos_gerado": len(d.gerado)}


def executar(
    org_id: UUID,
    cliente_id: UUID,
    contrato_id: UUID,
    referencia: Optional[Path],
    redigir: bool,
    forcar_render: bool = False,
) -> dict:
    client = _client()
    prontidao, dados = relatorio_prontidao(client, org_id, cliente_id, contrato_id)
    gaps = tracar_gaps(client, org_id, cliente_id, contrato_id, dados, prontidao)
    prov = provenance(client, org_id, cliente_id, contrato_id)

    saida: dict[str, Any] = {
        "org_id": str(org_id),
        "cliente_id": str(cliente_id) if not redigir else "<redigido>",
        "contrato_id": str(contrato_id),
        "pronto": prontidao.pronto,
        "pode_gerar": prontidao.pode_gerar,
        "modelo_derivado": prontidao.modelo_derivado,
        "modelo_confere": prontidao.modelo_confere,
        "n_faltando": len(prontidao.faltando),
        "n_bloqueios": len(prontidao.bloqueios),
        "n_avisos": len(prontidao.avisos),
        "n_pendentes_validacao": len(prontidao.pendentes),
        "n_conflitos": len(prontidao.conflitos),
        "n_confirmacoes": len(prontidao.confirmacoes),
        "n_revisao_campos": len(prontidao.revisao_campos),
        "revisao_final_unica": prontidao.revisao_final_unica,
        "faltando": _redigir_faltando(prontidao.faltando) if redigir else prontidao.faltando,
        "bloqueios": prontidao.bloqueios,  # codigo+mensagem only, no PII by construction
        "gaps": [_redigir_gap(g) for g in gaps] if redigir else gaps,
        "n_itens_proveniencia": len(prov.get("items", [])),
    }

    render_erro: Optional[str] = None
    renderizado = None
    # Mirrors `service.gerar`'s own precondition: production NEVER calls
    # `documento.renderizar` on a not-`pronto` card (it raises
    # `ContratoIncompleto` first) — attempting it here regardless of
    # `--forcar-render` would surface KeyErrors/AttributeErrors from the
    # template context that are unreachable in production and would read
    # as false "generator defects".
    if prontidao.pronto or forcar_render:
        try:
            # A forced render of an incomplete card carries explicit gap
            # markers (`dados_com_marcadores`), never silently-missing words.
            renderizado = renderizar_em_memoria(dados, com_marcadores=not prontidao.pronto)
        except Exception as exc:  # noqa: BLE001 — surfaced verbatim, never swallowed
            render_erro = f"{type(exc).__name__}: {exc}"
    else:
        saida["render_pulado"] = "cartao_incompleto (avaliacao.pronto=False) — ver --forcar-render"
    saida["render_erro"] = render_erro

    if renderizado is not None:
        achados = lint_renderizado(renderizado)
        saida["lint_achados"] = len(achados)
        saida["lint"] = achados if not redigir else [{"codigo": a.get("codigo")} for a in achados]

        if referencia is not None:
            ref_paragrafos = comparador.paragrafos_de_arquivo(referencia)
            gen_paragrafos = comparador.paragrafos_de_lista(renderizado.paragrafos)
            diff = comparador.comparar(ref_paragrafos, gen_paragrafos)
            saida["diff"] = {
                "paragrafos_ref": diff.paragrafos_ref,
                "paragrafos_gerado": diff.paragrafos_gerado,
                "similaridade": round(diff.similaridade, 4),
                "contagem_por_tipo": diff.contagem_por_tipo(),
                "diferencas": (
                    [_redigir_diferenca(d) for d in diff.diferencas]
                    if redigir
                    else [asdict(d) for d in diff.diferencas]
                ),
            }
            card = comparador.pontuar(
                ref_paragrafos,
                gen_paragrafos,
                allowlist=comparador.carregar_allowlist(),
                limiares=comparador.Limiares.de_arquivo(),
                clausulas_desligadas=clausulas_desligadas(switches_producao(dados)),
            )
            saida["scorecard"] = card.resumo() if redigir else card.detalhe()
    return saida


def _parse_uuid(s: str) -> UUID:
    return UUID(s)


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lote", type=Path, default=None, help="batch-score request JSON (noctus.dev.contract_score); needs --saida")
    p.add_argument("--saida", type=Path, default=None, help="private 0600 scorecard path for --lote")
    p.add_argument("--org", type=_parse_uuid, default=None)
    sub = p.add_mutually_exclusive_group(required=False)
    sub.add_argument("--cliente", type=_parse_uuid, help="cliente_id (the card)")
    sub.add_argument("--descobrir", action="store_true", help="scan the org for cards with >= --min-documentos live documents")
    p.add_argument("--contrato", type=_parse_uuid, default=None, help="contrato_id; defaults to the most recently updated one")
    p.add_argument("--referencia", type=Path, default=None, help="reference .docx/.txt to diff the in-memory render against")
    p.add_argument("--min-documentos", type=int, default=3)
    p.add_argument("--mostrar-valores", action="store_true", help="print real field values (PII) — use in a private terminal only")
    p.add_argument(
        "--forcar-render",
        action="store_true",
        help="attempt the in-memory render even when the card is not 'pronto' (debugging the template only — never a reachable production path)",
    )
    args = p.parse_args(argv)

    if args.lote is not None:
        if args.saida is None:
            p.error("--lote requires --saida")
        resultado = executar_lote(args.lote, args.saida)
        # stdout carries VERDICT-LEVEL numbers only (the scorecard file is private)
        print(json.dumps(resultado, ensure_ascii=False, default=str))
        return 0
    if args.org is None or (args.cliente is None and not args.descobrir):
        p.error("--org and one of --cliente/--descobrir are required (or --lote)")

    if args.descobrir:
        client = _client()
        achados = descobrir_cards_com_documentos(client, args.org, minimo=args.min_documentos)
        linhas = []
        for item in achados:
            cliente_id = UUID(item["cliente_id"])
            contrato_id = contrato_mais_recente(client, args.org, cliente_id)
            entrada: dict[str, Any] = {"documentos": item["documentos"], "tem_contrato": contrato_id is not None}
            if contrato_id is not None:
                prontidao, _dados = relatorio_prontidao(client, args.org, cliente_id, UUID(contrato_id))
                entrada.update(
                    {
                        "pronto": prontidao.pronto,
                        "n_faltando": len(prontidao.faltando),
                        "n_bloqueios": len(prontidao.bloqueios),
                        "n_pendentes_validacao": len(prontidao.pendentes),
                    }
                )
            if not args.mostrar_valores:
                entrada["cliente_id"] = "<redigido>"
                entrada["contrato_id"] = "<redigido>" if contrato_id else None
            else:
                entrada["cliente_id"] = str(cliente_id)
                entrada["contrato_id"] = contrato_id
            linhas.append(entrada)
        linhas.sort(key=lambda e: (not e.get("tem_contrato"), e.get("n_faltando", 999)))
        print(json.dumps({"org_id": str(args.org), "min_documentos": args.min_documentos, "cards": linhas}, indent=2, ensure_ascii=False, default=str))
        return 0

    contrato_id = args.contrato
    if contrato_id is None:
        client = _client()
        resolved = contrato_mais_recente(client, args.org, args.cliente)
        if resolved is None:
            print(json.dumps({"erro": "cliente sem contrato"}), file=sys.stderr)
            return 2
        contrato_id = UUID(resolved)

    saida = executar(
        args.org,
        args.cliente,
        contrato_id,
        args.referencia,
        redigir=not args.mostrar_valores,
        forcar_render=args.forcar_render,
    )
    print(json.dumps(saida, indent=2, ensure_ascii=False, default=str))
    return 0 if saida["render_erro"] is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
