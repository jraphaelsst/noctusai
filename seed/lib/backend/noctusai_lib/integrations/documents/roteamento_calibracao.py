"""Recalibration of the model routing table — evidence in, table out, with a
dry-run diff. The engine behind `noctus.dev.roteamento_modelos_recalibrar`
(run in a subprocess against the TARGET checkout's seed, so the generator
that writes a worktree's table is that worktree's own generator).

Two evidence sources, both reduced to DE-IDENTIFIED counts before anything is
written (model, doc type, field, reads, documents, hits — never a value):

1. A real-document BENCHMARK directory (`<bench>/corpus.json` with the
   answer key + `<bench>/results/<model>/<doc>_r<k>.json` with each run's
   transcription and cost). Every stored transcription is RE-PARSED with this
   checkout's parsers (`real.LadderIdentityExtractor._ler`), so the evidence
   measures the model through today's parser, and judged by the
   deterministic trust gate (`confianca.avaliar(..., medir_precisao=False)`)
   so residual precision can be computed. The benchmark files hold PII and
   stay local; only counts leave.
2. PRODUCTION outcomes: rows of social-wiring `extracao_leitura_resultados`
   (exported by the caller via the Supabase MCP — same split as
   `noctus.dev.divergencia_calibrar`), human-resolved rows only
   (`roteamento_gerador.celulas_de_resultados`).

A source id already in the evidence file is REPLACED, never double-counted.
Nothing is written unless `escrever=True`; the table moves only where the
generator's minimum-sample + separation rule says so.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from noctusai_lib.integrations.documents import roteamento_gerador as gerador
from noctusai_lib.primitives.accents import fold_accents_ascii

PACOTE = Path(__file__).resolve().parent
EVIDENCIA = PACOTE / "roteamento_evidencia.json"
MODULO_TABELA = PACOTE / "roteamento_modelos.py"


def _n(s: Any) -> str:
    texto = s.isoformat() if hasattr(s, "isoformat") else str(s or "")
    return re.sub(r"[^a-z0-9]", "", fold_accents_ascii(texto).lower())


def _correto(campo: str, esperado: Optional[str], lido: Any) -> tuple[bool, bool]:
    """`(acerto, presente)` with the benchmark's own scoring semantics: an
    expected `None` means the field must come out EMPTY; rg/rne accept a
    reading that extends the expected one (a check digit the key omits);
    `|` separates accepted alternatives."""
    presente = lido not in (None, "", [], ())
    if esperado is None:
        return (not presente, presente)
    if not presente:
        return (False, False)
    if campo in ("rg", "rne"):
        return (_n(lido) == _n(esperado) or _n(lido).startswith(_n(esperado)), True)
    return (any(_n(lido) == _n(x) for x in esperado.split("|")), True)


def _texto(resultado: dict) -> str:
    chamadas = resultado.get("ladder") or []
    ocr = [c.get("text") or "" for c in chamadas if c.get("source") == "ocr"]
    return "\n".join(ocr) or "\n".join(c.get("text") or "" for c in chamadas)


def evidencia_de_bench(bench_dir: str, *, fonte: str) -> dict[str, Any]:
    """De-identified evidence cells + per-read costs from a benchmark dir."""
    from noctusai_lib.integrations.documents import confianca
    from noctusai_lib.integrations.documents.real import LadderIdentityExtractor
    from noctusai_lib.integrations.documents.types import TextSource

    base = Path(bench_dir)
    corpus = {d["id"]: d for d in json.loads((base / "corpus.json").read_text(encoding="utf-8"))}
    leitor = LadderIdentityExtractor()
    celulas: dict[tuple[str, str, str], dict[str, Any]] = {}
    custos: dict[tuple[str, str], dict[str, Any]] = {}
    leituras = 0
    for caminho in sorted(glob.glob(str(base / "results" / "*" / "*.json"))):
        r = json.loads(Path(caminho).read_text(encoding="utf-8"))
        doc = corpus.get(r.get("doc"))
        if doc is None or r.get("exc"):
            continue
        texto = _texto(r)
        tipo_decl = doc.get("tipo_pipeline") or doc["tipo"]
        tipo = (tipo_decl or "").upper()
        fields = leitor._ler(texto, TextSource.OCR, None, None, tipo_decl)
        vereditos = confianca.avaliar(fields, tipo_decl, medir_precisao=False)
        leituras += 1
        k = (r["model"], tipo)
        cst = custos.setdefault(k, {"leituras": 0, "usd": 0.0, "_docs": set()})
        cst["leituras"] += 1
        cst["usd"] += float(r.get("usd") or 0.0)
        cst["_docs"].add(doc["id"])
        for campo, esperado in doc["exp"].items():
            lido = getattr(fields, campo, None)
            acerto, presente = _correto(campo, esperado, lido)
            c = celulas.setdefault((tipo, campo, r["model"]), {**gerador._vazio(), "_docs": set()})
            c["leituras"] += 1
            c["_docs"].add(doc["id"])
            c["acertos"] += acerto
            if presente:
                c["presentes"] += 1
                c["presentes_corretos"] += acerto
                v = vereditos.get(campo)
                if v is None or v.estado == confianca.CONFIAVEL:
                    c["presentes_portao"] += 1
                    c["corretos_portao"] += acerto
    saida_celulas = []
    for (tipo, campo, modelo), c in sorted(celulas.items()):
        docs = c.pop("_docs")
        saida_celulas.append({"fonte": fonte, "modelo": modelo, "tipo": tipo, "campo": campo,
                              **c, "documentos": len(docs)})
    saida_custos = []
    for (modelo, tipo), c in sorted(custos.items()):
        saida_custos.append({"fonte": fonte, "modelo": modelo, "tipo": tipo,
                             "leituras": c["leituras"], "documentos": len(c["_docs"]),
                             "usd": round(c["usd"], 5)})
    return {
        "fonte": {"id": fonte, "tipo": "benchmark", "leituras": leituras,
                  "documentos": len({d for c in custos.values() for d in c["_docs"]})},
        "celulas": saida_celulas,
        "custos": saida_custos,
    }


def ler_tabela(caminho: Path) -> dict[str, Any]:
    """The `TABELA` literal of a generated `roteamento_modelos.py`, read as
    DATA (`ast.literal_eval`), never imported — the file may belong to
    another checkout."""
    import ast

    if not caminho.exists():
        return {}
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    for no in arvore.body:
        if isinstance(no, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "TABELA" for t in no.targets
        ):
            return ast.literal_eval(no.value)
    raise ValueError(f"{caminho}: no TABELA assignment")


def _mesclar(evidencia: dict[str, Any], nova: dict[str, Any]) -> dict[str, Any]:
    fid = nova["fonte"]["id"]
    return {
        "versao": 1,
        "fontes": [f for f in evidencia.get("fontes", []) if f["id"] != fid] + [nova["fonte"]],
        "celulas": [c for c in evidencia.get("celulas", []) if c["fonte"] != fid] + nova["celulas"],
        "custos": [c for c in evidencia.get("custos", []) if c["fonte"] != fid] + nova.get("custos", []),
    }


def relatorio_custos(evidencia: dict[str, Any]) -> dict[str, Any]:
    """US$ per document and per correct field, per model (all sources)."""
    usd: dict[str, float] = defaultdict(float)
    leituras: dict[str, int] = defaultdict(int)
    acertos: dict[str, int] = defaultdict(int)
    for c in evidencia.get("custos", []):
        usd[c["modelo"]] += c["usd"]
        leituras[c["modelo"]] += c["leituras"]
    for c in evidencia.get("celulas", []):
        acertos[c["modelo"]] += c["presentes_corretos"]
    return {
        m: {
            "usd_por_documento": round(usd[m] / leituras[m], 5) if leituras[m] else None,
            "usd_por_campo_correto": round(usd[m] / acertos[m], 5) if acertos[m] else None,
            "leituras": leituras[m],
        }
        for m in sorted(usd)
    }


def recalibrar(
    *,
    bench_dir: Optional[str] = None,
    bench_fonte: Optional[str] = None,
    producao_path: Optional[str] = None,
    producao_fonte: str = "producao",
    escrever: bool = False,
    pacote: Optional[Path] = None,
) -> dict[str, Any]:
    """Merge new evidence, regenerate, diff against the committed table.
    `pacote` — the directory holding `roteamento_evidencia.json` +
    `roteamento_modelos.py` (default: this package)."""
    base = Path(pacote) if pacote is not None else PACOTE
    arq_evidencia, arq_tabela = base / EVIDENCIA.name, base / MODULO_TABELA.name
    TABELA = ler_tabela(arq_tabela)
    atual = json.loads(arq_evidencia.read_text(encoding="utf-8")) if arq_evidencia.exists() else {}
    evidencia = dict(atual) or {"versao": 1, "fontes": [], "celulas": [], "custos": []}
    if bench_dir:
        if not bench_fonte:
            raise ValueError("recalibrar: `bench_fonte` (a stable source id) is required with `bench_dir`")
        evidencia = _mesclar(evidencia, evidencia_de_bench(bench_dir, fonte=bench_fonte))
    if producao_path:
        linhas = json.loads(Path(producao_path).read_text(encoding="utf-8"))
        cel = gerador.celulas_de_resultados(linhas, fonte=producao_fonte)
        evidencia = _mesclar(evidencia, {
            "fonte": {"id": producao_fonte, "tipo": "producao", "leituras": len(linhas)},
            "celulas": cel, "custos": [],
        })
    nova = gerador.gerar(evidencia)
    mudancas = gerador.diff(TABELA, nova)
    if escrever:
        arq_evidencia.write_text(
            json.dumps(evidencia, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        arq_tabela.write_text(gerador.renderizar_modulo(nova), encoding="utf-8")
    return {
        "escrito": escrever,
        "mudancas": mudancas,
        "por_tipo": nova["por_tipo"],
        "por_campo_movidos": {k: v for k, v in nova["por_campo"].items() if v["origem"] == "medido"},
        "recomendacoes": nova["recomendacoes"],
        "custos": relatorio_custos(evidencia),
        "fontes": evidencia["fontes"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bench-dir")
    ap.add_argument("--bench-fonte")
    ap.add_argument("--producao-path")
    ap.add_argument("--producao-fonte", default="producao")
    ap.add_argument("--escrever", action="store_true")
    a = ap.parse_args(argv)
    out = recalibrar(
        bench_dir=a.bench_dir, bench_fonte=a.bench_fonte,
        producao_path=a.producao_path, producao_fonte=a.producao_fonte,
        escrever=a.escrever,
    )
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1, default=str)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry for the MCP tool
    raise SystemExit(main())
