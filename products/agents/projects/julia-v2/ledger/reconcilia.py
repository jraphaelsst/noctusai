"""Reconcile hook of Julia's ledger: the eval runner decides whether a row is open or closed.

    python reconcilia.py RESULT.json [--run-id ID] [--hash H] [--sha SHA] [--apply]   # propose / apply status changes
    python reconcilia.py --check                                                     # exit 1 on status vs latest-run drift

``RESULT.json`` is the output of ``rodar_mecanismo_local.py`` (merged partitions allowed: pass several files).
Pure functions + a thin CLI; the plain-file write is the INTERIM path until ``noctus.dev.findings_ledger`` owns the file.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# NOC-REMEDIATE[ledger-plug]: INTERIM plain file. When `noctus.dev.findings_ledger` lands (feat/access-tiers-gate), register_ledger(
# LedgerType(name="julia", extra={"attribution": (...), "regression_case_id": None}, scanner=<the latest run's failures>)) replaces
# `ler/escrever`; `reconciliar` stays as the hook that decides open vs closed from the eval runner. -- 2026-11-06
LEDGER = Path(__file__).with_name("julia-mistakes.ndjson")


def ler(path: Path = LEDGER) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def escrever(rows: list[dict], path: Path = LEDGER) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows))


def _estado(status: str) -> str:
    return status.split(" ", 1)[0]


def reconciliar(rows: list[dict], casos: dict[str, dict], *, run: str, hash_: str | None, sha: str | None) -> list[dict]:
    """``casos``: slug -> {k, aprovadas, passou}. Returns the proposed changes (row id, from, to, why)."""
    mudancas = []
    for r in rows:
        slug = r.get("caso_eval")
        c = casos.get(slug or "")
        if c is None or _estado(r["status"]) == "accepted":
            continue
        atual = _estado(r["status"])
        if c["passou"] and atual in ("open", "in-progress"):
            novo = f"fixed {sha or 'run:' + run}"
        elif not c["passou"] and atual == "fixed":
            novo = "open"
        else:
            novo = None
        mudancas.append({
            "id": r["id"], "de": r["status"], "para": novo or r["status"], "caso": slug,
            "passk": {"k": c["k"], "aprovadas": c["aprovadas"], "run": run, "hash": hash_, "em": str(date.today())},
        })
    return mudancas


def aplicar(rows: list[dict], mudancas: list[dict]) -> list[dict]:
    por_id = {m["id"]: m for m in mudancas}
    for r in rows:
        if r["id"] in por_id:
            m = por_id[r["id"]]
            r["status"], r["passk"], r["atualizado_em"] = m["para"], m["passk"], str(date.today())
    return rows


def divergencias(rows: list[dict]) -> list[str]:
    """Status that disagrees with what the latest recorded run of its case shows."""
    erros = []
    for r in rows:
        est, pk = _estado(r["status"]), r.get("passk")
        if r.get("atribuicao") not in ("MODEL", "STRUCTURAL", "CONTENT", "AMBIGUOUS"):
            erros.append(f"{r['id']}: atribuicao invalida")
        if est == "fixed" and not r.get("caso_eval"):
            erros.append(f"{r['id']}: fixed sem caso_eval (um fix so existe com o caso que o reproduz)")
        if pk and r.get("caso_eval"):
            passou = pk["aprovadas"] == pk["k"]
            if est == "fixed" and not passou:
                erros.append(f"{r['id']}: fixed mas o ultimo run de {r['caso_eval']} reprovou ({pk['aprovadas']}/{pk['k']})")
            if est in ("open", "in-progress") and passou:
                erros.append(f"{r['id']}: {est} mas o ultimo run de {r['caso_eval']} passou pass^k")
    return erros


def casos_de(resultados: list[Path]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in resultados:
        for c in json.loads(p.read_text())["por_caso"]:
            ex = [e for e in c["execucoes"] if e["status"] != "pulado"]
            out[c["slug"]] = {"k": c["k"], "aprovadas": sum(e["status"] == "aprovado" for e in ex), "passou": c["passou"]}
    return out


def renderizar(rows: list[dict]) -> str:
    cab = "| id | atribuicao | status | caso | pass^k | titulo |\n|---|---|---|---|---|---|\n"
    linhas = []
    for r in rows:
        pk = r.get("passk")
        linhas.append(f"| {r['id']} | {r['atribuicao']} | {r['status']} | {r.get('caso_eval') or '-'} | "
                      f"{(str(pk['aprovadas']) + '/' + str(pk['k'])) if pk else '-'} | {r['titulo']} |")
    return "# Julia mistakes ledger (rendered; source: julia-mistakes.ndjson)\n\n" + cab + "\n".join(linhas) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("resultados", nargs="*", type=Path)
    ap.add_argument("--run-id", default="local")
    ap.add_argument("--hash")
    ap.add_argument("--sha")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--render", action="store_true")
    a = ap.parse_args()
    rows = ler()
    if a.render:
        LEDGER.with_name("LEDGER.md").write_text(renderizar(rows))
        return 0
    if a.check:
        erros = divergencias(rows)
        print("\n".join(erros) or "ledger ok")
        return 1 if erros else 0
    mud = reconciliar(rows, casos_de(a.resultados), run=a.run_id, hash_=a.hash, sha=a.sha)
    print(json.dumps(mud, ensure_ascii=False, indent=1))
    if a.apply:
        escrever(aplicar(rows, mud))
    return 0


if __name__ == "__main__":
    sys.exit(main())
