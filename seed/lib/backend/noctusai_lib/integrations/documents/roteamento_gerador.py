"""Generator of the model routing table: measured evidence -> `(doc_type,
field) -> primary model, fallback model`. Pure; the ONE place the routing
RULES live.

🔴 THE TABLE IS GENERATED, NEVER HAND-EDITED. `roteamento_modelos.py` is the
output of `gerar(evidencia)` over `roteamento_evidencia.json` (de-identified
counts: model, doc type, field, reads, documents, hits — no value), written by
`noctus.dev.roteamento_modelos_recalibrar` (the `divergencia_calibrar`
family). `test_roteamento.py` asserts the committed table equals
`gerar(<committed evidence>)`, so a hand edit fails CI.

THE RULES (owner direction 2026-10-13)
--------------------------------------
- Anthropic only. Candidates: `CANDIDATOS`. `claude-fable-5-1` is a
  DOCUMENTED candidate that is never routed to (30-day data retention on ID
  documents — the owner chose Opus 5.5 over it for the fallback). It is
  still measured, and a measured win over the fallback becomes a FLAGGED
  recommendation ("if Opus keeps failing, switch to Fable"), never a switch.
- Global default: Sonnet 5 primary / Opus 5.5 fallback (the owner's choice).
- A doc-type row (all critical fields of that type pooled) or a
  (doc-type, field) row moves AWAY from its default only when the data clearly
  separates models:
    1. MINIMUM SAMPLE — both the challenger and the incumbent have at least
       `N_MIN_LEITURAS` scored reads over at least `N_MIN_DOCUMENTOS`
       distinct documents in that cell (repeated runs of one document are
       correlated, so documents are counted separately); and
    2. SEPARATION — the challenger's Wilson 95% lower bound on accuracy is
       above the incumbent's Wilson 95% upper bound.
  A row that does not clear both keeps its default and says so
  (`origem="padrao"`), with its sample size recorded either way.
- Fallback: the incumbent fallback stays unless a non-primary candidate
  separates from it under the same rule; when the primary moved onto the
  incumbent fallback, the previous primary becomes the fallback (second best).
- Residual precision per (model, doc type, field) — precision among reads
  that passed the deterministic trust gate (`confianca.avaliar(...,
  medir_precisao=False)`) — feeds the gate's measured-precision rule
  (`roteamento.precisao`). Recorded with its sample; `suficiente` says whether
  it clears the minimum-sample rule.

Accuracy = scored reads where the field came out right (present and correct,
or correctly absent) / scored reads. Residual precision = correct among
gate-passing PRESENT reads.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable, Mapping, Optional

PROVEDOR = "anthropic"
PRIMARIO_PADRAO = "claude-sonnet-5"
FALLBACK_PADRAO = "claude-opus-5-5"

#: Models a row may route to, in the owner's preference order (ties keep
#: the earlier one).
CANDIDATOS: tuple[str, ...] = (
    "claude-sonnet-5",
    "claude-opus-5-5",
    "claude-sonnet-5-5",
    "claude-haiku-5-5",
    "claude-haiku-4-5",
)

#: Measured, never routed to — see the module docstring.
EXCLUIDOS: dict[str, str] = {
    "claude-fable-5-1": (
        "retenção de dados de 30 dias (sem ZDR) para documentos de identidade "
        "— decisão do dono 2026-10-13; candidato documentado, só por "
        "recomendação sinalizada"
    ),
}

N_MIN_LEITURAS = 24
N_MIN_DOCUMENTOS = 8
Z_95 = 1.96
LIMIAR_PRECISAO = 0.95

#: The fields pooled into a doc-type row (`releitura.CAMPOS_CRITICOS` plus
#: the document-level groups) — kept literal so this module stays import-free.
CAMPOS_CRITICOS_POOL = frozenset({
    "nome", "cpf", "rg", "rne", "data_nascimento", "estado_civil",
    "regime_bens", "data_casamento", "conjuges", "matricula_certidao",
})


def wilson(acertos: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n <= 0:
        return (0.0, 1.0)
    p = acertos / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    meia = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centro - meia), min(1.0, centro + meia))


def _suficiente(c: Mapping[str, int]) -> bool:
    return c["leituras"] >= N_MIN_LEITURAS and c["documentos"] >= N_MIN_DOCUMENTOS


def separa(desafiante: Mapping[str, int], incumbente: Mapping[str, int]) -> bool:
    """Does `desafiante` clearly beat `incumbente`? (minimum sample on BOTH,
    Wilson intervals do not overlap)."""
    if not (_suficiente(desafiante) and _suficiente(incumbente)):
        return False
    return wilson(desafiante["acertos"], desafiante["leituras"])[0] > wilson(
        incumbente["acertos"], incumbente["leituras"]
    )[1]


def _vazio() -> dict[str, int]:
    return {
        "leituras": 0, "documentos": 0, "acertos": 0, "presentes": 0,
        "presentes_corretos": 0, "presentes_portao": 0, "corretos_portao": 0,
    }


def _somar(dst: dict[str, int], src: Mapping[str, Any]) -> None:
    for k in dst:
        dst[k] += int(src.get(k, 0))


def _escolher(
    medidas: Mapping[str, Mapping[str, int]], primario: str, fallback: str
) -> tuple[str, str]:
    """Apply the separation rule to one cell."""
    vazio = _vazio()
    novo_primario = primario
    melhores = sorted(
        (m for m in CANDIDATOS if m != primario and m in medidas),
        key=lambda m: (-(medidas[m]["acertos"] / max(1, medidas[m]["leituras"])), CANDIDATOS.index(m)),
    )
    for m in melhores:
        if separa(medidas[m], medidas.get(primario, vazio)):
            novo_primario = m
            break
    novo_fallback = fallback
    if novo_fallback == novo_primario:
        novo_fallback = primario
    for m in melhores:
        if m in (novo_primario, novo_fallback):
            continue
        if separa(medidas[m], medidas.get(novo_fallback, vazio)):
            novo_fallback = m
            break
    return novo_primario, novo_fallback


def _linha(medidas: Mapping[str, Mapping[str, int]], primario: str, fallback: str) -> dict[str, Any]:
    p, f = _escolher(medidas, primario, fallback)
    base = medidas.get(p, _vazio())
    return {
        "primario": p,
        "fallback": f,
        "origem": "medido" if (p, f) != (primario, fallback) else "padrao",
        "n_leituras": base["leituras"],
        "n_documentos": base["documentos"],
    }


def gerar(evidencia: Mapping[str, Any]) -> dict[str, Any]:
    """Evidence (see `roteamento_evidencia.json`) -> the routing table."""
    # (tipo, campo, modelo) -> counts, summed over every evidence source.
    celulas: dict[tuple[str, str, str], dict[str, int]] = defaultdict(_vazio)
    for c in evidencia.get("celulas", ()):
        _somar(celulas[(c["tipo"], c["campo"], c["modelo"])], c)
    # (tipo, modelo) pooled over critical fields; documents = max over fields
    # (the same documents carry every field of that type).
    pool: dict[tuple[str, str], dict[str, int]] = defaultdict(_vazio)
    docs_pool: dict[tuple[str, str], int] = defaultdict(int)
    for (tipo, campo, modelo), c in celulas.items():
        if campo not in CAMPOS_CRITICOS_POOL:
            continue
        d = pool[(tipo, modelo)]
        docs = d["documentos"]
        _somar(d, c)
        d["documentos"] = docs
        docs_pool[(tipo, modelo)] = max(docs_pool[(tipo, modelo)], c["documentos"])
    for k, n in docs_pool.items():
        pool[k]["documentos"] = n

    tipos = sorted({t for t, _ in pool} | {t for t, _, _ in celulas})
    por_tipo: dict[str, Any] = {}
    for tipo in tipos:
        medidas = {m: c for (t, m), c in pool.items() if t == tipo}
        por_tipo[tipo] = _linha(medidas, PRIMARIO_PADRAO, FALLBACK_PADRAO)

    por_campo: dict[str, Any] = {}
    for tipo, campo in sorted({(t, c) for t, c, _ in celulas}):
        medidas = {m: c for (t, cc, m), c in celulas.items() if (t, cc) == (tipo, campo)}
        linha_tipo = por_tipo[tipo]
        linha = _linha(medidas, linha_tipo["primario"], linha_tipo["fallback"])
        linha["origem"] = "medido" if linha["origem"] == "medido" else "tipo"
        por_campo[f"{tipo}/{campo}"] = linha

    precisao: dict[str, Any] = {}
    for (tipo, campo, modelo), c in sorted(celulas.items()):
        residual = (
            round(c["corretos_portao"] / c["presentes_portao"], 4)
            if c["presentes_portao"] else None
        )
        precisao[f"{modelo}|{tipo}|{campo}"] = {
            "n_leituras": c["leituras"],
            "n_documentos": c["documentos"],
            "acuracia": round(c["acertos"] / c["leituras"], 4) if c["leituras"] else None,
            "presentes_portao": c["presentes_portao"],
            "precisao_residual": residual,
            "suficiente": _suficiente(c),
        }

    recomendacoes = _recomendacoes(celulas, pool, por_tipo, por_campo)

    custos: dict[str, Any] = {}
    agreg: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0, 0.0])
    for c in evidencia.get("custos", ()):
        a = agreg[(c["modelo"], c["tipo"])]
        a[0] += int(c["leituras"])
        a[1] += float(c["usd"])
    for (modelo, tipo), (n, usd) in sorted(agreg.items()):
        custos.setdefault(modelo, {})[tipo] = round(usd / n, 5) if n else None

    return {
        "versao": 1,
        "provedor": PROVEDOR,
        "fontes": [f["id"] for f in evidencia.get("fontes", ())],
        "regras": {
            "n_min_leituras": N_MIN_LEITURAS,
            "n_min_documentos": N_MIN_DOCUMENTOS,
            "z": Z_95,
            "limiar_precisao": LIMIAR_PRECISAO,
        },
        "padrao_global": {"primario": PRIMARIO_PADRAO, "fallback": FALLBACK_PADRAO},
        "candidatos": list(CANDIDATOS),
        "excluidos": dict(EXCLUIDOS),
        "por_tipo": por_tipo,
        "por_campo": por_campo,
        "precisao": precisao,
        "recomendacoes": recomendacoes,
        "usd_por_leitura": custos,
    }


def _recomendacoes(celulas, pool, por_tipo, por_campo) -> list[dict[str, Any]]:
    """Flagged, never applied: an excluded model that separates from the
    routed fallback, and a routed fallback whose residual precision is below
    the threshold on a sufficient sample ("if Opus keeps failing")."""
    out: list[dict[str, Any]] = []
    for excluido in EXCLUIDOS:
        for tipo, linha in sorted(por_tipo.items()):
            ex = pool.get((tipo, excluido))
            fb = pool.get((tipo, linha["fallback"]))
            if ex and fb and separa(ex, fb):
                out.append({
                    "tipo": tipo, "campo": None, "modelo": excluido,
                    "contra": linha["fallback"],
                    "motivo": "modelo_excluido_supera_fallback",
                    "acao": "decisão do dono (retenção) — nunca automático",
                })
        for chave, linha in sorted(por_campo.items()):
            tipo, campo = chave.split("/", 1)
            ex = celulas.get((tipo, campo, excluido))
            fb = celulas.get((tipo, campo, linha["fallback"]))
            if ex and fb and separa(ex, fb):
                out.append({
                    "tipo": tipo, "campo": campo, "modelo": excluido,
                    "contra": linha["fallback"],
                    "motivo": "modelo_excluido_supera_fallback",
                    "acao": "decisão do dono (retenção) — nunca automático",
                })
    for chave, linha in sorted(por_campo.items()):
        tipo, campo = chave.split("/", 1)
        fb = celulas.get((tipo, campo, linha["fallback"]))
        if fb and _suficiente(fb) and fb["presentes_portao"]:
            residual = fb["corretos_portao"] / fb["presentes_portao"]
            if residual < LIMIAR_PRECISAO:
                out.append({
                    "tipo": tipo, "campo": campo, "modelo": linha["fallback"],
                    "contra": None,
                    "motivo": "fallback_precisao_abaixo_do_limiar",
                    "precisao_residual": round(residual, 4),
                    "acao": (
                        "re-rodar o benchmark real; se persistir, considerar "
                        "claude-fable-5-1 (decisão do dono — retenção)"
                    ),
                })
    return out


def celulas_de_resultados(linhas: Iterable[Mapping[str, Any]], *, fonte: str) -> list[dict[str, Any]]:
    """Production outcome rows (social-wiring `extracao_leitura_resultados`,
    exported by the caller) -> evidence cells. Only rows a HUMAN resolved
    carry ground truth: `primario_correto` / `fallback_correto` (true/false,
    from the human's final value vs each reading's fingerprint). Unresolved
    rows are not counted — an unadjudicated read is not evidence."""
    acc: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in linhas:
        tipo = (r.get("tipo_documento") or "").upper()
        campo = r.get("campo")
        for papel in ("primario", "fallback"):
            correto = r.get(f"{papel}_correto")
            modelo = r.get(f"modelo_{papel}")
            if correto is None or not modelo or not tipo or not campo:
                continue
            c = acc.setdefault((tipo, campo, modelo), {**_vazio(), "_docs": set()})
            c["leituras"] += 1
            c["_docs"].add(r.get("documento_id"))
            c["acertos"] += bool(correto)
            presente = r.get(f"{papel}_presente", True)
            if presente:
                c["presentes"] += 1
                c["presentes_corretos"] += bool(correto)
                if papel == "fallback" or r.get("veredito") == "confiavel":
                    c["presentes_portao"] += 1
                    c["corretos_portao"] += bool(correto)
    out = []
    for (tipo, campo, modelo), c in sorted(acc.items()):
        docs = c.pop("_docs")
        c["documentos"] = len(docs)
        out.append({"fonte": fonte, "modelo": modelo, "tipo": tipo, "campo": campo, **c})
    return out


def diff(atual: Mapping[str, Any], nova: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Row-level diff of two tables (routing rows only — `por_tipo`,
    `por_campo` — plus precision cells whose `suficiente` flips or whose
    residual precision crosses the threshold)."""
    out: list[dict[str, Any]] = []
    for secao in ("por_tipo", "por_campo"):
        a, b = atual.get(secao, {}), nova.get(secao, {})
        for k in sorted(set(a) | set(b)):
            ra, rb = a.get(k), b.get(k)
            if ra is None or rb is None or (ra["primario"], ra["fallback"]) != (rb["primario"], rb["fallback"]):
                out.append({"secao": secao, "chave": k, "antes": ra, "depois": rb})
    pa, pb = atual.get("precisao", {}), nova.get("precisao", {})
    for k in sorted(set(pa) | set(pb)):
        ra, rb = pa.get(k), pb.get(k)

        def abaixo(r: Optional[Mapping[str, Any]]) -> Optional[bool]:
            if not r or not r.get("suficiente") or r.get("precisao_residual") is None:
                return None
            return r["precisao_residual"] < LIMIAR_PRECISAO

        if abaixo(ra) != abaixo(rb):
            out.append({"secao": "precisao", "chave": k, "antes": ra, "depois": rb})
    return out


CABECALHO_MODULO = (
    '"""GERADO — NÃO EDITE À MÃO. The model routing table, output of\n'
    "`roteamento_gerador.gerar` over `roteamento_evidencia.json`; regenerate\n"
    "with `noctus.dev.roteamento_modelos_recalibrar`. `test_roteamento.py`\n"
    'asserts this file equals its generator."""\n'
)


def renderizar_modulo(tabela: Mapping[str, Any]) -> str:
    """The exact source text of `roteamento_modelos.py` for `tabela`."""
    import pprint

    corpo = pprint.pformat(dict(tabela), indent=1, width=100, sort_dicts=True)
    return f"{CABECALHO_MODULO}\nTABELA = {corpo}\n"


__all__ = [
    "CANDIDATOS",
    "EXCLUIDOS",
    "FALLBACK_PADRAO",
    "LIMIAR_PRECISAO",
    "N_MIN_DOCUMENTOS",
    "N_MIN_LEITURAS",
    "PRIMARIO_PADRAO",
    "celulas_de_resultados",
    "diff",
    "gerar",
    "renderizar_modulo",
    "separa",
    "wilson",
]
