"""Regenerate the SIMEC golden fixtures by evaluating the REAL workbook formulas.

The fixtures (``instagram_golden.json`` / ``tiktok_golden.json``) hold input
rows plus the values the owner's SIMEC 1.0 workbooks compute for them
(DADOS columns S–Z and PAINEL rows 6–17). ``test_golden_workbook.py`` checks
the seed calculator against those numbers — so the expected values come from
the spreadsheet itself, never from the code under test.

How: the rows below are written into a copy of each workbook
(``products/social-wiring/projects/marketing-intelligence/kits/simec-1.0/``)
and every formula cell is evaluated with ``pycel`` (an Excel formula engine).
Two shims cover pycel gaps, both of which match Excel semantics for these
sheets: ``COUNTA`` (not implemented by pycel) and ``COUNTIFS`` with a blank
criterion (pycel's ``IF`` is eager, so it evaluates the COUNTIFS branch of an
EMPTY row that Excel short-circuits away via ``COUNTA(A:R)=0 → ""``).

Not run by the test suite (pycel is a dev-only oracle, not a dependency).
Re-run after changing the cases:

    python3.12 -m venv /tmp/oracle && /tmp/oracle/bin/pip install pycel openpyxl
    /tmp/oracle/bin/python -I seed/lib/backend/tests/domain/content_performance/golden/generate_golden.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import types
from pathlib import Path

import openpyxl
from pycel import ExcelCompiler
from pycel.lib.stats import countifs as _pycel_countifs

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[6]
KIT = REPO / "products/social-wiring/projects/marketing-intelligence/kits/simec-1.0"


def _counta(*args):
    n = 0

    def walk(a):
        nonlocal n
        if isinstance(a, (tuple, list)):
            for x in a:
                walk(x)
        elif a is not None and a != "":
            n += 1

    walk(args)
    return n


def _countifs(*args):
    if any(a is None for a in args[1::2]):
        return 0
    return _pycel_countifs(*args)


_shim = types.ModuleType("simec_pycel_shims")
_shim.counta = _counta
_shim.countifs = _countifs
sys.modules["simec_pycel_shims"] = _shim

D = dt.date
P = D(2026, 8, 3)  # base publication date

# Workbook window labels -> calculator window keys.
WINDOWS = {"7d": "7d", "30d": "30d", "Atual": "atual"}
STATUS = {
    "OK": "ok", "INCOMPLETO": "incompleto", "DATA INVÁLIDA": "data_invalida",
    "FORA DA JANELA": "fora_da_janela", "DUPLICADO": "duplicado",
}

PLATFORMS = {
    "instagram": {
        "workbook": "SIMEC_Instagram.xlsx",
        # DADOS input columns A..R -> reading field / metric key
        "inputs": ["published_at", "collected_at", "content_id", "topic", "format",
                   "duration_s", "window", "views", "reach", "likes", "comments", "shares",
                   "saves", "follows", "avg_watch_time_s", "skip_rate", "source", "note"],
        "outputs": {"S": "total_interacoes", "T": "taxa_interacao", "U": "taxa_compartilhamento",
                    "V": "taxa_salvamento", "W": "taxa_seguidores", "X": "tempo_medio_duracao",
                    "Y": "age_days", "Z": "status"},
        "panel": {6: ("conteudos_validos", "Conteúdos válidos"),
                  7: ("visualizacoes_somadas", "Visualizações somadas"),
                  8: ("media_visualizacoes", "Média de visualizações"),
                  9: ("media_alcance", "Média de alcance"),
                  10: ("media_taxa_interacao", "Média da taxa de interação / alcance"),
                  11: ("media_taxa_compartilhamento", "Média compartilhamentos / alcance"),
                  12: ("media_taxa_salvamento", "Média salvamentos / alcance"),
                  13: ("media_taxa_seguidores", "Média seguidores / alcance"),
                  14: ("media_tempo_medio_duracao", "Média tempo médio / duração"),
                  15: ("media_taxa_pulo", "Média taxa de pulo registrada"),
                  16: ("amostra_taxa_interacao", "Amostra com taxa de interação"),
                  17: ("amostra_taxa_seguidores", "Amostra com taxa de seguidores")},
        # (pub, coll, id, topic, fmt, dur, win, views, reach, likes, comm, shares, saves, follows, avg, skip, src, note)
        "rows": [
            (P, D(2026, 8, 11), "R1", "maternidade", "Reel", 32, "7d", 1500, 1200, 90, 12, 30, 25, None, 14.5, 0.42, "Instagram Insights", None),
            (P, D(2026, 8, 10), "R2", "maturidade", "Reel", 45, "7d", 800, 700, 40, 3, 5, 9, None, 20, 0.55, "Instagram Insights", None),
            (P, D(2026, 8, 13), "F1", "livro", "Foto", None, "7d", 600, 450, 50, 6, 2, 4, 3, None, None, "Instagram Insights", None),
            (P, D(2026, 8, 12), "C1", "comunidade", "Carrossel", None, "7d", 2000, 1500, 120, 15, 40, 80, 7, None, None, "Instagram Insights", None),
            (P, D(2026, 8, 10), "C2", "curso", "Carrossel", None, "7d", 900, 0, 30, 2, 1, 5, 1, None, None, "reach zero", None),
            (P, D(2026, 8, 10), "C3", "palestra", "Carrossel", None, "7d", 1100, 1000, 70, None, 9, 14, 2, None, None, "comments missing", None),
            (P, D(2026, 8, 10), "Z1", "zeros", "Foto", None, "7d", 300, 250, 0, 0, 0, 0, 0, None, None, "proven zeros", None),
            (P, D(2026, 8, 10), "D1", "dup", "Reel", 30, "7d", 500, 400, 20, 2, 3, 4, None, 10, None, "dup a", None),
            (P, D(2026, 8, 10), "D1", "dup", "Reel", 30, "7d", 510, 410, 21, 2, 3, 4, None, 11, None, "dup b", None),
            (P, D(2026, 8, 14), "W1", "late", "Reel", 30, "7d", 700, 600, 30, 4, 5, 6, None, 12, None, "age 11", None),
            (P, D(2026, 8, 9), "W2", "early", "Reel", 30, "7d", 400, 380, 10, 1, 1, 2, None, 8, None, "age 6", None),
            (P, D(2026, 9, 2), "R1", "maternidade", "Reel", 32, "30d", 2600, 1900, 140, 18, 55, 41, None, 13.9, 0.44, "Instagram Insights", None),
            (P, D(2026, 9, 7), "F1", "livro", "Foto", None, "30d", 950, 700, 70, 9, 3, 6, 5, None, None, "Instagram Insights", None),
            (P, D(2026, 9, 8), "C1", "comunidade", "Carrossel", None, "30d", 2400, 1800, 150, 20, 51, 99, 9, None, None, "age 36", None),
            (P, D(2026, 9, 1), "R2", "maturidade", "Reel", 45, "30d", 1000, 800, 45, 4, 6, 10, None, 19, None, "age 29", None),
            (P, D(2026, 10, 1), "R1", "maternidade", "Reel", 32, "Atual", 3000, 2100, 160, 20, 60, 45, None, 13.2, 0.45, "Instagram Insights", None),
            (P, P, "F2", "lançamento", "Foto", None, "Atual", 120, 100, 8, 1, 0, 1, 0, None, None, "same day", None),
            (P, D(2026, 8, 11), "N1", "no views", "Reel", 30, "7d", None, 500, 10, 1, 1, 1, None, 9, None, "views blank", None),
            (P, None, "N2", "no collection date", "Reel", 30, "7d", 400, 300, 10, 1, 1, 1, None, 9, None, None, None),
            (P, D(2026, 8, 10), None, "no id", "Foto", None, "7d", 400, 300, 10, 1, 1, 1, 1, None, None, None, None),
            (D(2026, 8, 20), D(2026, 8, 10), "B1", "backwards", "Foto", None, "Atual", 400, 300, 10, 1, 1, 1, 1, None, None, "collected before published", None),
            (None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, "only a note"),
        ],
    },
    "tiktok": {
        "workbook": "SIMEC_TikTok.xlsx",
        "inputs": ["published_at", "collected_at", "content_id", "topic", "format",
                   "duration_s", "window", "views", "likes", "comments", "shares", "favorites",
                   "follows", "avg_watch_time_s", "completion_rate", "for_you_rate", "source", "note"],
        "outputs": {"S": "total_interacoes", "T": "taxa_interacao", "U": "taxa_compartilhamento",
                    "V": "taxa_favoritos", "W": "taxa_seguidores", "X": "tempo_medio_duracao",
                    "Y": "age_days", "Z": "status"},
        "panel": {6: ("conteudos_validos", "Conteúdos válidos"),
                  7: ("visualizacoes_somadas", "Visualizações somadas"),
                  8: ("media_visualizacoes", "Média de visualizações"),
                  9: ("media_curtidas", "Média de curtidas"),
                  10: ("media_taxa_interacao", "Média da taxa de interação / views"),
                  11: ("media_taxa_compartilhamento", "Média compartilhamentos / views"),
                  12: ("media_taxa_favoritos", "Média favoritos / views"),
                  13: ("media_taxa_seguidores", "Média seguidores / views"),
                  14: ("media_tempo_medio_duracao", "Média tempo médio / duração"),
                  15: ("media_assistiu_ate_o_fim", "Média assistiu até o fim"),
                  16: ("media_origem_para_voce", "Média origem Para Você"),
                  17: ("amostra_taxa_interacao", "Amostra com taxa de interação")},
        # (pub, coll, id, topic, fmt, dur, win, views, likes, comm, shares, favs, follows, avg, fim, fyp, src, note)
        "rows": [
            (P, D(2026, 8, 10), "T1", "maternidade", "Vídeo", 28, "7d", 5000, 400, 30, 60, 45, 12, 11.2, 0.18, 0.81, "TikTok Studio", None),
            (P, D(2026, 8, 13), "T2", "maturidade", "Vídeo", 60, "7d", 1200, 80, 6, 4, 9, None, 21, 0.09, 0.6, "TikTok Studio", None),
            (P, D(2026, 8, 12), "T3", "zero views", "Vídeo", 15, "7d", 0, 0, 0, 0, 0, 0, 0, None, None, "views zero", None),
            (P, D(2026, 8, 12), "T4", "missing favs", "Vídeo", 20, "7d", 900, 50, 3, 2, None, 1, 9, None, 0.5, None, None),
            (P, D(2026, 8, 12), "T4", "missing favs", "Vídeo", 20, "7d", 900, 50, 3, 2, None, 1, 9, None, 0.5, "dup", None),
            (P, D(2026, 9, 4), "T1", "maternidade", "Vídeo", 28, "30d", 7400, 520, 41, 77, 60, 15, 10.9, 0.17, 0.79, "TikTok Studio", None),
            (P, D(2026, 9, 9), "T2", "maturidade", "Vídeo", 60, "30d", 1500, 90, 7, 5, 10, 2, 20, 0.08, None, "age 37", None),
            (P, D(2026, 10, 5), "T1", "maternidade", "Vídeo", 28, "Atual", 8000, 560, 44, 80, 66, 16, 10.5, 0.16, 0.78, "TikTok Studio", None),
            (P, D(2026, 8, 10), "T5", "no views", "Vídeo", 28, "Atual", None, 10, 1, 1, 1, None, None, None, None, None, None),
        ],
    },
}


def _iso(v):
    return v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v


def _num(v):
    if v == "" or v is None:
        return None
    if isinstance(v, bool):
        raise TypeError(v)
    return v


def generate(platform: str) -> dict:
    spec = PLATFORMS[platform]
    wb = openpyxl.load_workbook(KIT / spec["workbook"])
    ws = wb["DADOS"]
    for i, row in enumerate(spec["rows"]):
        assert len(row) == 18, (platform, i, len(row))
        for j, v in enumerate(row):
            ws.cell(row=2 + i, column=1 + j, value=v)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "filled.xlsx"
        wb.save(path)
        xl = ExcelCompiler(filename=str(path), plugins=["simec_pycel_shims"])
        cases = []
        for i, row in enumerate(spec["rows"]):
            r = 2 + i
            inputs = {}
            for key, v in zip(spec["inputs"], row):
                if key == "window":
                    v = WINDOWS[v] if v is not None else None
                inputs[key] = _iso(v)
            expected = {}
            for col, key in spec["outputs"].items():
                val = xl.evaluate(f"DADOS!{col}{r}")
                if key == "status":
                    expected[key] = STATUS[val] if val else None
                else:
                    expected[key] = _num(val)
            cases.append({"inputs": inputs, "expected": expected})
        panel = {}
        pws = wb["PAINEL"]
        for col, label in (("B", "7d"), ("C", "30d"), ("D", "Atual")):
            assert pws[f"{col}5"].value == label
            colvals = {}
            for prow, (key, title) in spec["panel"].items():
                assert pws[f"A{prow}"].value == title, (platform, prow, pws[f"A{prow}"].value)
                colvals[key] = _num(xl.evaluate(f"PAINEL!{col}{prow}"))
            panel[WINDOWS[label]] = colvals
    return {
        "platform": platform,
        "source_workbook": f"products/social-wiring/projects/marketing-intelligence/kits/simec-1.0/{spec['workbook']}",
        "generator": "pycel (see generate_golden.py)",
        "cases": cases,
        "panel": panel,
    }


def main() -> None:
    for platform in PLATFORMS:
        out = HERE / f"{platform}_golden.json"
        out.write_text(json.dumps(generate(platform), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
