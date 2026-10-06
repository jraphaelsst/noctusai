"""`noctus.dev.contract_score` — the measured, enforced reliability number of
social-wiring's contract generator against REAL signed contracts.

WHY THIS EXISTS
---------------
Owner, 2026-10-03: "reliable" must be a measured, enforced number. The old
`tests/e2e_contrato/harness.py` + `comparador.py` was a manual CLI that printed
a similarity and never failed. This tool runs the structured scorecard
(`comparador.pontuar` — per-section categories, EXACT numbers/dates, an
owner-approved patterns-only allowlist, configurable thresholds) over every
deal that has a signed-contract answer key, and returns ONE verdict per deal.

WHAT IT DOES
------------
1. Reads the card map (`cards_path`, default `~/.noctusai/private/p3/cards.json`:
   `{numero: {cliente_id, atendimento_id}}`) or an inline `cards` list.
2. For each deal, resolves the REFERENCE text: the answer key
   (`answer_keys_dir/<numero>.json`, produced by `noctus.dev.drive_census
   action=answer_key`) names the signed contract (`fonte.arquivo`) inside its
   Drive mirror (`folder.drive_folder_id`); the mirror manifest gives the
   file's sha256; the extract-once cache gives its text; drive_census's own
   `paragraphs_from_text` turns it into paragraphs (D4Sign furniture stripped).
   A deal without a usable reference is SKIPPED and named — never guessed.
3. Hands the batch to `harness.py --lote` in a SUBPROCESS (the product's
   `app` package cannot be imported into the MCP process — every product's
   backend is a top-level `app`, see `divergencia_calibrar._load_current_policy`
   for the collision class), with the repo venv and this tree's seed on
   `PYTHONPATH`. The harness loads each card from the LIVE DB exactly like
   production (`carregador.carregar`), takes readiness from production's own
   `service.obter_geracao` + `service.precondicao_gerar` (the extraction
   precondition `service.gerar` itself calls), renders in memory (a not-`pronto` card with explicit
   `[[LACUNA]]` gap markers, gaps reported apart from wording diffs; a
   reference clause the generator SWITCHED OFF for lack of data is a data gap,
   not a missing clause) — and
   NEVER writes to the database.
4. The harness writes the masked per-section scorecard to
   `~/.noctusai/private/scores/<ts>.json` (0600). This tool returns ONLY
   verdict-level numbers (verdicts, counts, ratios, reason codes) — every
   field is re-filtered through `_so_veredito`, so no name/CPF/value can leave
   even if the harness ever printed one.

The private request file (it carries the reference paragraphs) is written
0600 under the private root and deleted in a `finally`.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from settings import resolve_test_python  # noqa: E402  (path constants)
from workspace import resolve_caller_root  # noqa: E402

from . import drive_census as _dc
from . import drive_pull as _dp
from .testing import _worktree_pythonpath

#: The org the owner's social-wiring data lives in (same constant
#: `drive_census.ref_snapshot` reads against).
SW_ORG_ID = _dc.SW_ORG_ID
CARDS_PADRAO = ("p3", "cards.json")
HARNESS_REL = Path("products") / "social-wiring" / "backend" / "tests" / "e2e_contrato" / "harness.py"

Runner = Callable[..., subprocess.CompletedProcess]

# ─── verdict-only filter ────────────────────────────────────────────────

_CHAVES_NUMERICAS = (
    "secoes_ref", "secoes_gerado", "secoes_alinhadas", "clausulas_faltando", "clausulas_extras", "clausulas_desligadas",
    "clausulas_explicadas_allowlist", "numeros_divergentes", "datas_divergentes", "lacunas",
    "numeros_em_lacuna", "allowlist_aplicadas", "allowlist_pendentes", "campos_marcados", "lint_achados",
    # honest-comparison counters (2026-10-05): gaps and non-facts, reported apart from divergences
    "numeros_alinhados", "datas_alinhadas", "dados_indisponiveis", "assinatura_excluidos",
    "certidoes_lacuna", "certidoes_extras", "certidoes_reemitidas",
    # two-layer verdict (2026-10-06): MATERIAL failures vs OBSERVATIONS
    "clausulas_faltando_opcionais", "secoes_material_sem_correspondencia", "obs_numeros", "obs_datas",
    "certidoes_partes_lacuna",
)
#: dict-of-counts fields (key → int): material checks beyond tokens, and the
#: material number divergences by token KIND (cpf/rg/valor/…). Keys are codes.
_CHAVES_CONTAGENS = ("materiais_documento", "numeros_materiais_por_tipo")
#: …and the keys of those dicts are a CLOSED vocabulary (a name-shaped key
#: passes the generic code filter, so it is refused here).
_TIPOS_TOKEN = frozenset({"cpf", "cnpj", "rg", "cep", "valor", "parcela", "dec", "num", "cod", "data"})
_CHAVE_CONTAGEM_OK = {
    "materiais_documento": lambda c: c.startswith("mat_") and c == c.lower(),
    "numeros_materiais_por_tipo": lambda c: c in _TIPOS_TOKEN,
}
_CHAVES_CODIGO = ("veredito", "veredito_texto", "render_modo", "render_erro", "erro")
_GAPS_CHAVES = (
    "pronto", "pode_gerar", "revisao_final_unica", "faltando", "bloqueios", "confirmacoes_pendentes",
    "conflitos_extracao", "pendentes_extracao_bloqueantes", "revisao_campos",
)
_CODIGO_OK = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_:")


def _codigo(valor: Any) -> Optional[str]:
    """A reason/verdict CODE (`clausula_faltando:2`, `KeyError`) — anything
    else (spaces, punctuation, digits-heavy text) is dropped, never echoed."""
    if not isinstance(valor, str) or len(valor) > 64 or not valor or set(valor) - _CODIGO_OK:
        return None
    return valor


def _so_veredito(resumo: dict[str, Any]) -> dict[str, Any]:
    """Whitelist re-filter of one deal's harness summary: known keys only,
    numbers/bools/codes only."""
    out: dict[str, Any] = {}
    for k in _CHAVES_CODIGO:
        c = _codigo(resumo.get(k))
        if c is not None:
            out[k] = c
    for k in _CHAVES_NUMERICAS:
        v = resumo.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = v
    motivos = [c for c in (_codigo(m) for m in resumo.get("motivos") or []) if c]
    if motivos or "motivos" in resumo:
        out["motivos"] = motivos
    observacoes = [c for c in (_codigo(m) for m in resumo.get("observacoes") or []) if c]
    if observacoes or "observacoes" in resumo:
        out["observacoes"] = observacoes
    for k in _CHAVES_CONTAGENS:
        d = resumo.get(k)
        if isinstance(d, dict):
            out[k] = {
                c: v for c, v in ((_codigo(kk), vv) for kk, vv in d.items())
                if c and isinstance(v, int) and not isinstance(v, bool) and _CHAVE_CONTAGEM_OK[k](c)
            }
    cats = resumo.get("categorias")
    if isinstance(cats, dict):
        out["categorias"] = {
            k: (round(float(v), 4) if isinstance(v, (int, float)) and not isinstance(v, bool) else None)
            for k, v in cats.items()
            if _codigo(k)
        }
    gaps = resumo.get("gaps")
    if isinstance(gaps, dict):
        out["gaps"] = {k: gaps[k] for k in _GAPS_CHAVES if isinstance(gaps.get(k), (int, bool))}
    return out


# ─── reference resolution ───────────────────────────────────────────────


def _ler_json(caminho: Path) -> Optional[dict[str, Any]]:
    if not caminho.is_file():
        return None
    return json.loads(caminho.read_text(encoding="utf-8"))


def referencia_paragrafos(chave: dict[str, Any]) -> tuple[Optional[list[str]], str]:
    """`(paragraphs, motivo)` — the signed contract's paragraphs for one
    answer key, or `(None, <why not>)`. Same ground-truth file the answer
    key itself was parsed from (`fonte.arquivo`)."""
    if chave.get("status") != "ok":
        return None, f"answer_key_status_{chave.get('status') or 'desconhecido'}"
    arquivo = (chave.get("fonte") or {}).get("arquivo")
    pasta = (chave.get("folder") or {}).get("drive_folder_id")
    if not arquivo or not pasta:
        return None, "answer_key_sem_arquivo_ou_pasta"
    manifesto = _ler_json(_dp.private_root() / "drive-mirror" / pasta / "manifest.json")
    if manifesto is None:
        return None, "sem_espelho_drive"
    entrada = next((e for e in manifesto.get("entries") or [] if e.get("rel_path") == arquivo), None)
    if entrada is None or not entrada.get("sha256"):
        return None, "arquivo_fora_do_manifesto"
    extraido = _ler_json(_dp.private_root() / "extractions" / f"{entrada['sha256']}.json")
    if not extraido or extraido.get("error") or not extraido.get("text"):
        return None, "sem_texto_extraido"
    fonte = "docx" if extraido.get("text_source") == "docx" else "pdf"
    paragrafos = _dc.paragraphs_from_text(extraido["text"], source=fonte)
    if not paragrafos:
        return None, "texto_vazio"
    return paragrafos, "ok"


def _carregar_cards(cards_path: Optional[str], cards: Optional[list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    if cards is not None:
        return {str(c["numero"]): dict(c) for c in cards}
    caminho = Path(cards_path).expanduser() if cards_path else _dp.private_root().joinpath(*CARDS_PADRAO)
    dados = _ler_json(caminho)
    if dados is None:
        raise ValueError(f"cards file not found: {caminho}")
    return {str(k): dict(v) for k, v in dados.items()}


def _escrever_privado(caminho: Path, payload: Any) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(caminho.parent, 0o700)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    os.replace(tmp, caminho)


# ─── the tool ───────────────────────────────────────────────────────────


def contract_score(
    *,
    cards_path: Optional[str] = None,
    cards: Optional[list[dict[str, Any]]] = None,
    numeros: Optional[list[str]] = None,
    answer_keys_dir: Optional[str] = None,
    org_id: str = SW_ORG_ID,
    limiares: Optional[dict[str, Any]] = None,
    allowlist_path: Optional[str] = None,
    worktree_path: Optional[str] = None,
    timeout: int = 900,
    runner: Optional[Runner] = None,
) -> dict[str, Any]:
    """See the module docstring. `runner` is the subprocess DI seam (tests);
    it is never exposed on the MCP surface."""
    root = resolve_caller_root(worktree_path)
    harness = root / HARNESS_REL
    if not harness.is_file():
        return {"status": "error", "error": f"harness not found under {root}"}
    try:
        mapa = _carregar_cards(cards_path, cards)
    except ValueError as exc:
        return {"status": "error", "error": str(exc)}
    if numeros:
        mapa = {n: v for n, v in mapa.items() if n in {str(x) for x in numeros}}
    keys_dir = Path(answer_keys_dir).expanduser() if answer_keys_dir else _dp.private_root() / "answer-keys"

    deals: list[dict[str, Any]] = []
    pulados: list[dict[str, str]] = []
    for numero, card in sorted(mapa.items()):
        if not card.get("cliente_id"):
            pulados.append({"numero": numero, "motivo": "card_sem_cliente_id"})
            continue
        chave = _ler_json(keys_dir / f"{numero}.json")
        if chave is None:
            pulados.append({"numero": numero, "motivo": "sem_answer_key"})
            continue
        paragrafos, motivo = referencia_paragrafos(chave)
        if paragrafos is None:
            pulados.append({"numero": numero, "motivo": motivo})
            continue
        deals.append(
            {
                "numero": numero,
                "cliente_id": card["cliente_id"],
                "contrato_id": card.get("contrato_id"),
                "ref_paragrafos": paragrafos,
            }
        )
    if not deals:
        return {"status": "no_deals", "deals": {}, "deals_skipped": pulados}

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    scores_dir = _dp.private_root() / "scores"
    pedido_path = scores_dir / f".pedido-{ts}-{os.getpid()}.json"
    score_path = scores_dir / f"{ts}.json"
    pedido: dict[str, Any] = {"org_id": org_id, "deals": deals}
    if limiares is not None:
        pedido["limiares"] = limiares
    if allowlist_path:
        pedido["allowlist"] = str(Path(allowlist_path).expanduser())
    run = runner or subprocess.run
    try:
        _escrever_privado(pedido_path, pedido)
        proc = run(
            [resolve_test_python(), str(harness), "--lote", str(pedido_path), "--saida", str(score_path)],
            cwd=str(harness.parents[2]),  # products/social-wiring/backend
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONPATH": _worktree_pythonpath(root)},
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": f"harness timed out after {timeout}s", "deals_skipped": pulados}
    finally:
        pedido_path.unlink(missing_ok=True)

    if proc.returncode != 0:
        # stderr may carry a traceback with values — return only its last
        # line's exception CLASS, never the message.
        ultima = next((ln for ln in reversed((proc.stderr or "").splitlines()) if ln.strip()), "")
        classe = _codigo(ultima.split(":", 1)[0].strip().rsplit(".", 1)[-1]) or "desconhecido"
        return {"status": "error", "error": f"harness exit {proc.returncode} ({classe})", "deals_skipped": pulados}
    linha = next((ln for ln in reversed((proc.stdout or "").splitlines()) if ln.startswith("{")), None)
    if linha is None:
        return {"status": "error", "error": "harness printed no result", "deals_skipped": pulados}
    resultado = json.loads(linha)

    por_deal = {str(n): _so_veredito(r) for n, r in (resultado.get("deals") or {}).items()}
    contagem: dict[str, int] = {}
    for r in por_deal.values():
        v = r.get("veredito", "desconhecido")
        contagem[v] = contagem.get(v, 0) + 1
    total = resultado.get("total") or {}
    # `aprovado` and `aprovado_com_observacoes` are both ACCEPTED: the material
    # terms match (wording/structure differences are observations only).
    aprovados = contagem.get("aprovado", 0) + contagem.get("aprovado_com_observacoes", 0)
    return {
        "status": "ok",
        "verdict": "pass" if por_deal and aprovados == len(por_deal) else "fail",
        "deals_scored": len(por_deal),
        "aprovados": aprovados,
        "taxa_aprovacao": round(aprovados / len(por_deal), 4) if por_deal else None,
        "por_veredito": contagem,
        "deals": por_deal,
        "deals_skipped": pulados,
        "scorecard_path": str(score_path),
        "limiares": total.get("limiares"),
        "allowlist": {
            "entradas": total.get("allowlist_entradas"),
            "aprovadas": total.get("allowlist_aprovadas"),
        },
        "resolved_root": str(root),
    }


# ── MCP registration ───────────────────────────────────────────────────


def register(server) -> None:
    @server.tool(
        name="noctus.dev.contract_score",
        description=(
            "Measured reliability gate for social-wiring's contract generator "
            "against REAL signed contracts. For each deal in a card map "
            "(`cards_path`, default ~/.noctusai/private/p3/cards.json "
            "{numero: {cliente_id, atendimento_id}}, or inline `cards`) with a "
            "signed-contract answer key (~/.noctusai/private/answer-keys/, from "
            "noctus.dev.drive_census), renders the contract READ-ONLY from the "
            "live DB exactly like production (readiness = service.obter_geracao "
            "+ service.precondicao_gerar; a not-pronto card renders with "
            "[[LACUNA]] gap markers, gaps and clauses the generator switched off "
            "for lack of data reported apart from wording diffs), scores it with tests/e2e_contrato/comparador.pontuar "
            "(per-section categories, EXACT numbers/dates, owner-approved "
            "allowlist.json, limiares.json thresholds), writes a masked 0600 "
            "scorecard to ~/.noctusai/private/scores/<ts>.json and RETURNS ONLY "
            "verdict-level numbers (aprovado/aprovado_com_observacoes/reprovado/"
            "incompleto per deal — only MATERIAL terms fail a deal; wording and "
            "structure are observations — "
            "counts, ratios, reason codes) — never a value. `numeros` filters "
            "deals; `limiares` overrides thresholds. Pass worktree_path from "
            "inside a git worktree."
        ),
    )
    def _contract_score(
        cards_path: str | None = None,
        cards: list[dict[str, Any]] | None = None,
        numeros: list[str] | None = None,
        answer_keys_dir: str | None = None,
        org_id: str = SW_ORG_ID,
        limiares: dict[str, Any] | None = None,
        allowlist_path: str | None = None,
        worktree_path: str | None = None,
    ) -> dict[str, Any]:
        return contract_score(
            cards_path=cards_path,
            cards=cards,
            numeros=numeros,
            answer_keys_dir=answer_keys_dir,
            org_id=org_id,
            limiares=limiares,
            allowlist_path=allowlist_path,
            worktree_path=worktree_path,
        )
