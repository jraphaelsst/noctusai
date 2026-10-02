"""`noctus.dev.divergencia_calibrar` — recompute the social-wiring
divergence-resolver's per-field per-source precision table from done
contracts, read-only, verdicts only.

WHY THIS EXISTS
---------------
Owner directive, 2026-09-29 (BUILD item 3 of the automatic divergence
resolver): the policy table hard-coded in `products/social-wiring/backend/
app/services/divergencia_resolucao.py` (`PRECISAO`) was measured ONCE
against the 10 signed P2 contracts on prod. As more contracts get signed,
that table needs to be RE-DERIVABLE, not re-typed by hand from a fresh
manual audit every time.

THE SAME SPLIT `noctus.dev.supabase_advisors` ALREADY ESTABLISHED
-------------------------------------------------------------------
This tool does NOT query prod itself — the noc MCP process has no live
Supabase credential/session for the social-wiring project, and chaining
MCP-to-MCP calls is out of scope (see `supabase_advisors`'s own docstring
for the identical reasoning). Instead: the CALLER (an agent with the
Supabase MCP, or `noctus.dev.drive_census`'s own answer-key machinery)
assembles the prod-side extraction snapshot and hands it to this tool via
`prod_extractions_path` (a JSON file) or `prod_extractions_raw` (inline) —
this tool does the deterministic comparison, aggregation, and verdict-only
report.

INPUTS
------
- `answer_keys_dir` (default `~/.noctusai/private/answer-keys`) — one
  `<numero>.json` per deal, produced by `noctus.dev.drive_census(action=
  "answer_key")`. Ground truth: `partes[i].clientes[<campo>]`.
- `cards_path` (default `~/.noctusai/private/p2/cards.json`) — which deal
  `numero`s this org actually has signed-contract ground truth for; scopes
  the comparison to exactly those (never a numero with no verified answer).
- `prod_extractions_path` / `prod_extractions_raw` — one entry PER PARTY per
  deal:

      {"numero": "897", "lado": "vendedor", "papel": "proprietario",
       "leituras": {"cpf": [{"valor": "412.954.238-98", "origem": "cnh"}, ...],
                    "nome_oficial": [...], ...}}

  `leituras[<campo>]` is every machine reading this party's card ever
  carried for that field, across every document — exactly what
  `app.services.campo_conflitos.historico_valores` accumulates on prod,
  pre-joined by the caller from `cliente_documentos.extracao_<campo>` +
  `tipo_documento` (or `crednet`/`matricula` origins) scoped to the deal's
  `atendimento_id` (via `cards_path`'s `numero -> atendimento_id`).

OUTPUT — VERDICTS ONLY, NEVER PERSONAL DATA
--------------------------------------------
`{"precisao": {campo: {origem: {"precisao": float, "n": int}}}, "diff_vs_policy":
[...], "deals_considered": int, "deals_skipped": [...], "leituras_comparadas": int}`
— aggregated ratios and origem/campo labels only; no name/cpf/rg/address
value from any contract ever leaves this function. `diff_vs_policy` flags
every (campo, origem) where the FRESH ratio disagrees with the CURRENT
`divergencia_resolucao.PRECISAO` cell by more than `diff_threshold` (default
0.10) — the signal that the policy table is due for a human-reviewed
re-derivation, never an auto-write (this tool has no write path at all).

Read-only by construction: no network call, no DB write, no mutation of
`divergencia_resolucao.py`. A human reads `diff_vs_policy` and edits that
module's `PRECISAO` table by hand, exactly like every other calibration
tool in this family (`noctus.dev.vector_calibration_decide`).
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Optional

# `divergencia_resolucao.PRECISAO` is the CURRENT policy table — imported
# for the `diff_vs_policy` comparison only, never mutated. `products/` is
# not on `sys.path` by default for the MCP process; resolved relative to
# the repo root the same way `settings.REPO_ROOT` is, so this stays correct
# whichever checkout runs it.
from settings import REPO_ROOT  # noqa: E402

_POLICY_MODULE_DIR = REPO_ROOT / "products" / "social-wiring" / "backend"


_POLICY_MODULE_FILE = _POLICY_MODULE_DIR / "app" / "services" / "divergencia_resolucao.py"
_POLICY_MODULE_NAME = "_noctus_calibrar_divergencia_resolucao"


_IDS_MODULE_FILE = _POLICY_MODULE_DIR / "app" / "services" / "identificadores.py"
#: The names the resolver reaches its one product-side sibling through
#: (`from app.services import identificadores`). Stubbed ONLY while it executes.
_SIBLING_KEYS = ("app", "app.services", "app.services.identificadores")


def _load_current_policy() -> dict[str, dict[str, tuple[float, int]]]:
    """Import `divergencia_resolucao.PRECISAO` fresh, BY FILE PATH under a
    private module name — never as a real `app.services...` import. A
    package-name import collides with whichever product's `app` package another
    caller already put in `sys.modules` (every product's backend is a top-level
    `app`), and popping `app` afterwards broke THAT caller in turn: the
    calibration tests passed alone and failed in the full MCP suite.

    The resolver imports `noctusai_lib` plus ONE product sibling,
    `app.services.identificadores` (canonical-identifier registry adapter, which
    itself imports only `noctusai_lib`). That sibling is loaded by file path
    too and exposed under a synthetic `app`/`app.services` for the duration of
    the resolver's exec; whatever `app` another caller had registered is saved
    and restored exactly, so the isolation guarantee above still holds."""
    import importlib.util
    import types

    saved = {k: sys.modules.get(k) for k in _SIBLING_KEYS}
    try:
        ids_spec = importlib.util.spec_from_file_location(_SIBLING_KEYS[2], _IDS_MODULE_FILE)
        spec = importlib.util.spec_from_file_location(_POLICY_MODULE_NAME, _POLICY_MODULE_FILE)
        if ids_spec is None or ids_spec.loader is None or spec is None or spec.loader is None:
            raise ImportError(f"cannot load the policy module from {_POLICY_MODULE_FILE}")
        ids_mod = importlib.util.module_from_spec(ids_spec)
        app_pkg, svc_pkg = types.ModuleType("app"), types.ModuleType("app.services")
        app_pkg.__path__, svc_pkg.__path__ = [], []
        app_pkg.services, svc_pkg.identificadores = svc_pkg, ids_mod
        sys.modules.update({"app": app_pkg, "app.services": svc_pkg, _SIBLING_KEYS[2]: ids_mod})
        ids_spec.loader.exec_module(ids_mod)
        mod = importlib.util.module_from_spec(spec)
        # Registered for the duration of exec only — `@dataclass` resolves its
        # annotations through `sys.modules[cls.__module__]`.
        sys.modules[_POLICY_MODULE_NAME] = mod
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop(_POLICY_MODULE_NAME, None)
        for key, previous in saved.items():
            if previous is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = previous
    return {
        campo: {origem: (p.precisao, p.n) for origem, p in origens.items()}
        for campo, origens in mod.PRECISAO.items()
    }


def _normalizar(campo: str, valor: Any) -> str:
    """Fold two readings of the same field onto one comparable string —
    digits-only for document numbers, accent/case/space-folded text
    otherwise. Deliberately simpler than `identidade_extracao_service.
    _mesmo_valor` (that module lives in product code this MCP toolkit must
    not import — a real layer boundary, not a DRY gap): a calibration ratio
    over many samples tolerates the rare edge this coarser fold misses;
    what it must never do is silently inflate precision by over-matching."""
    if valor is None:
        return ""
    texto = str(valor).strip()
    if not texto:
        return ""
    if campo in ("cpf", "rg", "endereco_cep"):
        return re.sub(r"\D", "", texto)
    decomposed = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento.upper()).strip()


def _carregar_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _parte_por_lado_papel(
    partes: list[dict[str, Any]], lado: str, papel: str
) -> Optional[dict[str, Any]]:
    """The ONE `partes[i]` entry matching (lado, papel) — `None` when zero
    or MORE THAN ONE match (an ambiguous party is skipped, never guessed
    at; two same-lado/papel entries — e.g. two `comprador`s — cannot be
    told apart by this pair alone)."""
    achados = [p for p in partes if p.get("lado") == lado and p.get("papel") == papel]
    return achados[0] if len(achados) == 1 else None


def divergencia_calibrar(
    *,
    answer_keys_dir: Optional[str] = None,
    cards_path: Optional[str] = None,
    prod_extractions_path: Optional[str] = None,
    prod_extractions_raw: Optional[list[dict[str, Any]]] = None,
    diff_threshold: float = 0.10,
) -> dict[str, Any]:
    """Recompute per-(campo, origem) precision from done contracts.
    Read-only. Verdicts only — see module docstring for the full contract.
    """
    if (prod_extractions_path is None) == (prod_extractions_raw is None):
        raise ValueError(
            "divergencia_calibrar: pass exactly one of "
            "`prod_extractions_path` or `prod_extractions_raw` (got "
            f"{'both' if prod_extractions_path is not None else 'neither'})"
        )

    home = Path.home()
    keys_dir = Path(answer_keys_dir) if answer_keys_dir else home / ".noctusai/private/answer-keys"
    cards_file = Path(cards_path) if cards_path else home / ".noctusai/private/p2/cards.json"

    cards = _carregar_json(cards_file) if cards_file.exists() else {}
    numeros_com_contrato = set(cards.keys()) if isinstance(cards, dict) else set()

    if prod_extractions_path is not None:
        registros = _carregar_json(Path(prod_extractions_path))
    else:
        registros = list(prod_extractions_raw or [])

    # (campo, origem) -> [acertos, total] — the ONLY state this function
    # accumulates; never a value, never a name.
    contagem: dict[tuple[str, str], list[int]] = {}
    deals_considerados: set[str] = set()
    deals_pulados: list[dict[str, str]] = []
    leituras_comparadas = 0

    for registro in registros:
        numero = str(registro.get("numero", ""))
        lado, papel = registro.get("lado"), registro.get("papel")
        leituras = registro.get("leituras") or {}
        if numero not in numeros_com_contrato:
            deals_pulados.append({"numero": numero, "motivo": "sem_card_cadastrado"})
            continue
        gabarito_path = keys_dir / f"{numero}.json"
        if not gabarito_path.exists():
            deals_pulados.append({"numero": numero, "motivo": "sem_gabarito"})
            continue
        gabarito = _carregar_json(gabarito_path)
        parte = _parte_por_lado_papel(gabarito.get("partes") or [], lado, papel)
        if parte is None:
            deals_pulados.append({
                "numero": numero, "motivo": "lado_papel_ambiguo_ou_ausente",
            })
            continue
        clientes_gabarito = parte.get("clientes") or {}
        deals_considerados.add(numero)

        for campo, leituras_campo in leituras.items():
            valor_esperado = _normalizar(campo, clientes_gabarito.get(campo))
            if not valor_esperado:
                continue  # nothing to check this field against for this party
            for leitura in leituras_campo:
                origem = leitura.get("origem")
                valor_lido = _normalizar(campo, leitura.get("valor"))
                if not origem or not valor_lido:
                    continue
                chave = (campo, origem)
                bucket = contagem.setdefault(chave, [0, 0])
                bucket[1] += 1
                if valor_lido == valor_esperado:
                    bucket[0] += 1
                leituras_comparadas += 1

    precisao: dict[str, dict[str, dict[str, Any]]] = {}
    for (campo, origem), (acertos, total) in contagem.items():
        precisao.setdefault(campo, {})[origem] = {
            "precisao": round(acertos / total, 4) if total else 0.0,
            "n": total,
        }

    politica_atual = _load_current_policy()
    diff_vs_policy: list[dict[str, Any]] = []
    for campo, origens in precisao.items():
        for origem, medida in origens.items():
            atual = politica_atual.get(campo, {}).get(origem)
            if atual is None:
                diff_vs_policy.append({
                    "campo": campo, "origem": origem,
                    "precisao_atual_na_politica": None,
                    "precisao_recem_medida": medida["precisao"],
                    "n": medida["n"],
                    "motivo": "sem_entrada_na_politica_atual",
                })
                continue
            precisao_politica, _n_politica = atual
            if abs(precisao_politica - medida["precisao"]) > diff_threshold:
                diff_vs_policy.append({
                    "campo": campo, "origem": origem,
                    "precisao_atual_na_politica": precisao_politica,
                    "precisao_recem_medida": medida["precisao"],
                    "n": medida["n"],
                    "motivo": "divergencia_acima_do_limiar",
                })

    return {
        "precisao": precisao,
        "diff_vs_policy": diff_vs_policy,
        "deals_considered": len(deals_considerados),
        "deals_skipped": deals_pulados,
        "leituras_comparadas": leituras_comparadas,
        "diff_threshold": diff_threshold,
    }


# ── MCP registration ───────────────────────────────────────────────────


def register(server) -> None:
    @server.tool(
        name="noctus.dev.divergencia_calibrar",
        description=(
            "Recompute the social-wiring automatic-divergence-resolver's "
            "per-field per-source precision table from done contracts, "
            "read-only. Reads the private answer keys "
            "(`~/.noctusai/private/answer-keys/<deal>.json`, produced by "
            "`noctus.dev.drive_census`) + the card<->deal map "
            "(`~/.noctusai/private/p2/cards.json`); pass `prod_extractions_"
            "path`/`prod_extractions_raw` (a per-party {numero, lado, papel, "
            "leituras} export YOU assemble via the Supabase MCP — this tool "
            "never queries prod itself, same split as `supabase_advisors`) "
            "for the prod-side readings. Prints VERDICTS ONLY — precision "
            "ratios + a `diff_vs_policy` flag against `divergencia_"
            "resolucao.PRECISAO` — never a personal value. Never writes "
            "anything; a human re-derives the policy table by hand."
        ),
    )
    def _divergencia_calibrar(
        answer_keys_dir: str | None = None,
        cards_path: str | None = None,
        prod_extractions_path: str | None = None,
        prod_extractions_raw: list[dict[str, Any]] | None = None,
        diff_threshold: float = 0.10,
    ) -> dict[str, Any]:
        return divergencia_calibrar(
            answer_keys_dir=answer_keys_dir,
            cards_path=cards_path,
            prod_extractions_path=prod_extractions_path,
            prod_extractions_raw=prod_extractions_raw,
            diff_threshold=diff_threshold,
        )
