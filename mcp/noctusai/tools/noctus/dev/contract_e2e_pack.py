"""noctus.dev.contract_e2e_pack — a deal's private Drive mirror → the ORDERED upload pack for the
social-wiring contract-generation e2e run.

Reads the census written by ``drive_census`` (``<private>/census/<numero>.json``) and the mirror
tree it points at. ``plan`` is read-only and returns phase / slot / count labels only (rel_paths carry
person names, so they never leave private disk through the tool result). ``stage`` (confirm=True)
copies the files into phase folders under ``dest`` and writes ``run.json`` (the full private step list).
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Optional

from . import drive_census as _dc
from . import drive_pull as _dp

_PHASES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("01-IMOVEL", "imóvel page /imoveis/:codigo → Documentos", "documento do imóvel",
     ("matricula", "iptu_espelho", "cnd_iptu", "cnd_condominio")),
    ("02-PESSOAS", "card → party → Dados do cliente", "leitura de documento pessoal",
     ("identidade", "certidao_casamento", "certidao_nascimento", "comprovante_endereco")),
    ("03-SERASA", "party → checklist Serasa Crednet", "serasa", ("serasa_crednet",)),
    ("04-EMPRESAS", "card → Empresas", "cartão CNPJ", ("cartao_cnpj",)),
)
_FINANCIAMENTO = ("banco_proposta", "banco_dps", "contrato_financiamento")
_GABARITO = ("contrato", "contrato_d4sign", "aditivo", "certidoes_consolidado")
P_CERT, P_FIN, P_GAB, P_OUT = "05-CERTIDOES", "06-FINANCIAMENTO", "99-GABARITO-NAO-SUBIR", "98-OUTROS"
PHASE_ORDER = ("01-IMOVEL", "02-PESSOAS", "03-SERASA", "04-EMPRESAS", P_CERT, P_FIN, P_OUT, P_GAB)
UPLOAD_PHASES = frozenset({"01-IMOVEL", "02-PESSOAS", "03-SERASA", "04-EMPRESAS", P_CERT})

_DADOS_DIGITADOS = ("negociação", "parcelas", "favorecidos", "intermediação", "termos",
                    "financiamento", "testemunhas", "assinatura")


def _is_visualizacao(rel_path: str) -> bool:
    return "VISUALIZ" in _dc._fold(Path(rel_path).name)


def _census_path(numero: str) -> Path:
    return _dp.private_root() / "census" / f"{numero}.json"


def _load_census(numero: str) -> dict[str, Any]:
    import json
    path = _census_path(numero)
    if not path.is_file():
        raise FileNotFoundError(f"census for deal {numero} not found; run noctus.dev.drive_census action='census' first")
    return json.loads(path.read_text(encoding="utf-8"))


def _alias_map(census: dict[str, Any]) -> dict[str, str]:
    return {e["entity"]: f"entidade {i} ({e.get('kind') or '?'})"
            for i, e in enumerate(sorted(census.get("entities", []), key=lambda e: e["entity"]), start=1)}


def _entity_index(census: dict[str, Any]) -> dict[str, int]:
    return {e["entity"]: i for i, e in enumerate(sorted(census.get("entities", []), key=lambda e: e["entity"]), start=1)}


def _step(phase: str, sid: str, doc_type: str, entity: Optional[str], slot: str, surface: str,
          reader: str, files: list[dict[str, Any]], aliases: dict[str, str], **extra: Any) -> dict[str, Any]:
    return {"phase": phase, "id": sid, "doc_type": doc_type,
            "entity_alias": aliases.get(entity) if entity else None, "slot": slot,
            "surface": surface, "expected_reader": reader, "status": "pendente", "achados": [],
            "upload": phase in UPLOAD_PHASES, "count": len(files),
            "files": [{"rel_path": f["rel_path"], "sha256": f.get("sha256")} for f in files], **extra}


def build_steps(census: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """Pure: census → (ordered steps, missing-by-phase). Drafts never become upload steps."""
    aliases, eidx = _alias_map(census), _entity_index(census)
    files = census.get("files", [])
    live = [f for f in files if not f.get("draft")]
    steps: list[dict[str, Any]] = []
    missing: dict[str, list[str]] = {}
    n = 0

    def sid(phase: str) -> str:
        nonlocal n
        n += 1
        return f"{phase[:2]}.{n:03d}"

    for phase, surface, reader, types in _PHASES:
        for t in types:
            group = [f for f in live if f["doc_type"] == t]
            if not group:
                if phase == "01-IMOVEL" and t != "cnd_condominio":
                    missing.setdefault(phase, []).append(t)
                continue
            if t == "matricula":
                group = sorted(group, key=lambda f: (_is_visualizacao(f["rel_path"]), f["rel_path"]))
            else:
                group = sorted(group, key=lambda f: (str(f.get("entity")), f["rel_path"]))
            if t in ("matricula", "iptu_espelho", "cnd_iptu", "cnd_condominio"):
                extra = {"visualizacao_flags": [_is_visualizacao(f["rel_path"]) for f in group]} if t == "matricula" else {}
                steps.append(_step(phase, sid(phase), t, None, t, surface, reader, group, aliases, **extra))
                continue
            by_ent: dict[Optional[str], list[dict[str, Any]]] = {}
            for f in group:
                by_ent.setdefault(f.get("entity"), []).append(f)
            for ent in sorted(by_ent, key=lambda e: (e is None, eidx.get(e, 0))):
                steps.append(_step(phase, sid(phase), t, ent, t, surface, reader, by_ent[ent], aliases))
    # certidões: per entity, one cell per n (serasa slot 9 is its own phase)
    for e in sorted(census.get("entities", []), key=lambda e: e["entity"]):
        ent = e["entity"]
        cells: dict[int, list[dict[str, Any]]] = {}
        for f in live:
            if f.get("entity") == ent and f["doc_type"] == "certidao" and f.get("certidao_n"):
                cells.setdefault(int(f["certidao_n"]), []).append(f)
        for k in sorted(cells):
            grp = sorted(cells[k], key=lambda f: f["rel_path"])
            steps.append(_step(P_CERT, sid(P_CERT), "certidao", ent, f"certidão {k}",
                               f"card → Certidões tab → row {aliases[ent]} → cell {k}", "certidão", grp, aliases,
                               certidao_n=k, multi_file_cell=len(grp) > 1))
        if e.get("faltando"):
            missing.setdefault(P_CERT, []).append(f"{aliases[ent]}: faltando {sorted(e['faltando'])}")
    for t in _FINANCIAMENTO:
        group = [f for f in live if f["doc_type"] == t]
        if group:
            steps.append(_step(P_FIN, sid(P_FIN), t, None, t, "referência (não enviado hoje)", "-", group, aliases))
    handled = {t for _, _, _, ts in _PHASES for t in ts} | {"certidao"} | set(_FINANCIAMENTO) | set(_GABARITO)
    for t in _GABARITO:
        group = [f for f in files if f["doc_type"] == t]
        if group:
            steps.append(_step(P_GAB, sid(P_GAB), t, None, t, "comparação — nunca subir", "-", sorted(group, key=lambda f: f["rel_path"]), aliases))
    rest = [f for f in files if f["doc_type"] not in handled or f.get("draft")]
    rest = [f for f in rest if not (f.get("draft") and f["doc_type"] in _GABARITO)]
    if rest:
        steps.append(_step(P_OUT, sid(P_OUT), "outro", None, "outros", "não enviado — procurar fonte de dados digitados (ex.: Info PP)",
                           "-", sorted(rest, key=lambda f: f["rel_path"]), aliases))
    for t in ("cartao_cnpj",):
        if not any(s["doc_type"] == t for s in steps) and census.get("entities_pj"):
            missing.setdefault("04-EMPRESAS", []).append(t)
    steps.sort(key=lambda s: (PHASE_ORDER.index(s["phase"]), s["id"]))
    return steps, missing


def _checklists(numero: str) -> dict[str, Any]:
    return {
        "dados_digitados": [{"id": f"07.{i:02d}", "item": item, "status": "pendente", "achados": []}
                            for i, item in enumerate(_DADOS_DIGITADOS, start=1)],
        "geracao": [
            {"id": "08.1", "item": "readiness (obter_geracao + precondicao_gerar)", "status": "pendente", "achados": []},
            {"id": "08.2", "item": "gerar contrato", "status": "pendente", "achados": []},
            {"id": "08.3", "item": "noctus.dev.contract_score",
             "cards_entry": {"numero": numero, "org_id": None, "cliente_id": None, "contrato_id": None},
             "status": "pendente", "achados": []},
        ],
    }


def _plan_view(numero: str, steps: list[dict[str, Any]], missing: dict[str, list[str]]) -> dict[str, Any]:
    public = [{k: s[k] for k in ("phase", "id", "doc_type", "entity_alias", "slot", "count", "upload")}
              | ({"multi_file_cell": s["multi_file_cell"]} if "multi_file_cell" in s else {})
              | ({"visualizacao_flags": s["visualizacao_flags"]} if "visualizacao_flags" in s else {})
              for s in steps]
    return {"numero": numero, "steps": public, "missing": missing,
            "upload_steps": sum(1 for s in steps if s["upload"]),
            "phases": [p for p in PHASE_ORDER if any(s["phase"] == p for s in steps)]}


def contract_e2e_pack(numero: str, action: str = "plan", confirm: bool = False, dest: Optional[str] = None,
                      force: bool = False) -> dict[str, Any]:
    if action not in ("plan", "stage"):
        return {"ok": False, "error": f"unknown action {action!r}; use plan|stage"}
    try:
        census = _load_census(numero)
    except FileNotFoundError as exc:
        return {"ok": False, "error": str(exc)}
    steps, missing = build_steps(census)
    plan = _plan_view(numero, steps, missing)
    if action == "plan":
        return {"ok": True, "action": "plan", **plan}
    if not confirm:
        return {"ok": True, "action": "stage", "status": "planned", **plan}
    out = Path(dest).expanduser() if dest else _dp.private_root() / "e2e-runs" / numero
    run_json = out / "run.json"
    if run_json.exists() and not force:
        return {"ok": False, "status": "refused_existing_run", "error": "run.json exists; pass force=True to overwrite"}
    mirror = _dp.private_root() / "drive-mirror" / census["folder"]["drive_folder_id"] / "tree"
    out.mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    copied = absent = 0
    for s in steps:
        phase_dir = out / s["phase"]
        phase_dir.mkdir(exist_ok=True)
        os.chmod(phase_dir, 0o700)
        for i, f in enumerate(s["files"], start=1):
            src = mirror / f["rel_path"]
            if not src.is_file():
                f["staged_as"] = None
                absent += 1
                continue
            name = re.sub(r"[\\/]", "_", Path(f["rel_path"]).name)
            target = phase_dir / f"{s['id']}-{i:02d}_{name}"
            shutil.copyfile(src, target)
            os.chmod(target, 0o600)
            f["staged_as"] = str(target.relative_to(out))
            copied += 1
    _dc._write_private(run_json, {"numero": numero, "folder": census["folder"], "steps": steps, **_checklists(numero)})
    return {"ok": True, "action": "stage", "status": "staged", "files_copied": copied,
            "files_absent_in_mirror": absent, "dest": str(out), **plan}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.contract_e2e_pack",
        description=(
            "Turn a deal's private Drive mirror (+ drive_census census) into the ORDERED upload pack for the "
            "social-wiring contract-generation e2e run: 01-IMOVEL → 02-PESSOAS → 03-SERASA → 04-EMPRESAS → "
            "05-CERTIDOES → 06-FINANCIAMENTO (reference) → 98-OUTROS; 99-GABARITO-NAO-SUBIR is staged for "
            "comparison only, never an upload step. action='plan' (default, read-only) returns phase/slot/"
            "counts only — no names or paths. action='stage' confirm=True copies files into phase folders "
            "under dest (default <private>/e2e-runs/<numero>, 0700/0600) and writes run.json (full private "
            "step list + typed-data and generation/score checklists); refuses to overwrite run.json unless "
            "force=True."
        ),
    )
    def _contract_e2e_pack(numero: str, action: str = "plan", confirm: bool = False,
                           dest: str | None = None, force: bool = False) -> dict:
        return contract_e2e_pack(numero=numero, action=action, confirm=confirm, dest=dest, force=force)


__all__ = ["contract_e2e_pack", "build_steps", "register"]
