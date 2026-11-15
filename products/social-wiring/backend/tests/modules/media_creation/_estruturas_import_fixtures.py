"""SYNTHETIC corpora shaped like the two Estruturas load files (estruturas-contract.md section 7).

Every string is invented neutral filler (``Fórmula sintética 3 de [tema]``): the real files are vendor-derived and never
enter git. ~20 rows per shape; helpers build single rows so a test can break exactly one thing.
"""
from __future__ import annotations

import copy
from typing import Any

#: A subset of the seeded catalog (names are OUR content, ``estruturas_tipos_bloco.py``).
TIPOS_CATALOGO = ("Headline", "Intensificador do Mistério", "Revelação", "Opinião Polêmica", "Outro")
SENTINELA = "ZZ-SENTINELA-TEXTO"  # appears in every synthetic text: a test greps responses/logs for it


def bloco_ref(ordem: int, *, tipo: str = "Headline", nome: str | None = None, nota: str = "") -> dict[str, Any]:
    return {
        "ordem": ordem, "nome_original": nome or f"{SENTINELA} bloco {ordem}", "nota": nota, "repeticoes": 1, "tipo": tipo,
        "tempo": f"{ordem * 3 - 3}–{ordem * 3}s", "instrucao": f"{SENTINELA} instrução {ordem}",
    }


def linha_ref(n: int, *, perfil: str | None = None, **over: Any) -> dict[str, Any]:
    row = {
        "corestudio_id": str(1000 + n), "perfil": perfil or f"criador.sintetico{n % 4}",
        "formula_headline": f"{SENTINELA} fórmula {n} de [tema]", "formato": "reels", "objetivos": ["alcance", "conexao"] if n % 2 else ["venda"],
        "blocos": [bloco_ref(1, tipo="Headline"), bloco_ref(2, tipo="Revelação", nota=f"{SENTINELA} nota"), bloco_ref(3, tipo="Outro")],
        "preenchido_por": "referencia-sintetica",
    }
    row.update(over)
    return row


def corpus_ref(n: int = 20) -> list[dict[str, Any]]:
    rows = [linha_ref(i) for i in range(1, n + 1)]
    if n >= 5:  # a variant that inherited its sibling's formula
        rows[4]["formula_herdada_de"] = rows[3]["corestudio_id"]
        rows[4]["formula_headline"] = rows[3]["formula_headline"]
    return rows


def molde(n: int, perfil_id: str = "p1", **over: Any) -> dict[str, Any]:
    row = {
        "id": f"molde-{n}", "aprovado": True, "criadoEm": 1, "exemplo": f"{SENTINELA} exemplo", "formato": "reels", "nome": f"{SENTINELA} molde {n}",
        "objetivos": ["alcance"], "perfil": "criador.sintetico0", "perfilId": perfil_id, "quandoNaoUsar": "x", "quandoUsar": "y", "validacao": "z",
        "blocos": [
            {"nome": "Headline", "tempo": "0-3s", "instrucao": f"{SENTINELA} a"},
            {"nome": "  revelacao ", "tempo": "3-6s", "instrucao": f"{SENTINELA} b"},  # accent/case/space-insensitive match
            {"nome": f"{SENTINELA} bloco livre", "tempo": "6-9s", "instrucao": f"{SENTINELA} c"},  # -> Outro
        ],
    }
    row.update(over)
    return row


def corpus_maquina(n: int = 20) -> dict[str, Any]:
    perfis = [
        {"id": "p1", "handle": "@Criador.Sintetico0", "nome": "Criador Sintético Zero", "dna": "x", "tom": "y"},
        {"id": "p2", "handle": "@criador.maquina", "nome": "Criador Máquina", "dna": "x"},
    ]
    moldes = [molde(i, "p1" if i % 2 else "p2") for i in range(1, n + 1)]
    return {"maquina": "sintetica", "exportadoEm": "2026-01-01", "totais": {"perfis": 2, "moldes": n}, "colecoes": {"perfis": perfis, "moldes": moldes, "marcas": [{"id": "m"}], "roteiros": []}}


def copia(x):
    return copy.deepcopy(x)
