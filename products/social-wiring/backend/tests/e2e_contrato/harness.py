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


@dataclass
class Prontidao:
    contrato_id: str
    pronto: bool
    modelo_derivado: str
    modelo_confere: bool
    pode_gerar: bool  # pronto AND no pendentes/conflitos (the real gerar precondition)
    faltando: list[dict] = field(default_factory=list)
    bloqueios: list[dict] = field(default_factory=list)
    avisos: list[dict] = field(default_factory=list)
    pendentes: list[dict] = field(default_factory=list)
    conflitos: list[dict] = field(default_factory=list)


def _client() -> Any:
    """The exact schema-scoped admin client production DI resolves
    (`card_hub.deps.get_card_hub_client`) — real Supabase unless
    `DATABASE_BACKEND=sqlite` is set (see `app.dependencies._use_sqlite`)."""
    from app.modules.card_hub.deps import get_card_hub_client

    return get_card_hub_client()


def carregar_dados(client: Any, org_id: UUID, cliente_id: UUID, contrato_id: UUID):
    from app.modules.card_hub.contrato_gerador.carregador import carregar

    return carregar(client, org_id, cliente_id, contrato_id, usuario_id=None)


def avaliar_prontidao(dados) -> tuple[Any, dict[str, bool], Any, str]:
    """`(avaliacao, switches, assinatura, modelo_derivado)` — the exact
    inputs/outputs `service.obter_geracao` computes, using the production
    default policy (`POLITICA_PADRAO`, same as `deps.get_politica_contrato`)."""
    from app.modules.card_hub.contrato_gerador.derivacao import avaliar, derivar_switches, modelo_derivado
    from app.modules.card_hub.contrato_gerador.politica import POLITICA_PADRAO
    from app.modules.card_hub.contrato_gerador.service import data_assinatura

    switches = derivar_switches(dados, POLITICA_PADRAO)
    assinatura = data_assinatura(dados, None)
    avaliacao = avaliar(dados, switches, POLITICA_PADRAO, assinatura)
    return avaliacao, switches, assinatura, modelo_derivado(switches)


def situacao_validacao(client: Any, org_id: UUID, dados) -> dict:
    """`validacao_extracao.situacao` — the SAME precondition `service.gerar`
    calls via `exigir_sem_pendentes` before it will render anything."""
    from app.modules.card_hub.contrato_gerador.validacao_extracao import situacao

    return situacao(client, org_id, dados, usuario_id=None)


def relatorio_prontidao(client: Any, org_id: UUID, cliente_id: UUID, contrato_id: UUID) -> tuple[Prontidao, Any]:
    """Returns `(Prontidao, dados)` — `dados` handed back so the caller can
    render/trace without re-loading the card a second time."""
    dados, _atendimento_id = carregar_dados(client, org_id, cliente_id, contrato_id)
    avaliacao, _switches, _assinatura, derivado = avaliar_prontidao(dados)
    estado = situacao_validacao(client, org_id, dados)
    pendentes, conflitos = estado["pendentes"], estado["conflitos"]
    prontidao = Prontidao(
        contrato_id=str(contrato_id),
        pronto=avaliacao.pronto,
        modelo_derivado=derivado,
        modelo_confere=dados.modelo == derivado,
        pode_gerar=avaliacao.pronto and not pendentes and not conflitos,
        faltando=avaliacao.faltando,
        bloqueios=avaliacao.bloqueios,
        avisos=avaliacao.avisos,
        pendentes=pendentes,
        conflitos=conflitos,
    )
    return prontidao, dados


# ─── in-memory render (no persistence) ─────────────────────────────────


def renderizar_em_memoria(dados) -> Any:
    """`documento.renderizar` with the REAL docx adapter — the exact
    rendering `service.gerar` would save, minus the save. Raises whatever
    `renderizar`/the template does; the caller decides whether a
    not-`pronto` card should even attempt this (the harness's CLI does
    attempt it regardless, so a broken template shows up even on an
    incomplete card — see `main()`)."""
    from noctusai_lib.integrations.docx_render import get_docx_render_adapter

    from app.modules.card_hub.contrato_gerador.documento import renderizar

    _avaliacao, switches, assinatura, _derivado = avaliar_prontidao(dados)
    from app.modules.card_hub.contrato_gerador.politica import POLITICA_PADRAO

    adapter = get_docx_render_adapter(real=True)
    return renderizar(adapter, dados, switches, POLITICA_PADRAO, assinatura)


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
            renderizado = renderizar_em_memoria(dados)
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
    return saida


def _parse_uuid(s: str) -> UUID:
    return UUID(s)


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--org", required=True, type=_parse_uuid)
    sub = p.add_mutually_exclusive_group(required=True)
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
