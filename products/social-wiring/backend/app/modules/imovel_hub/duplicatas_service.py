"""Possível duplicado — detect, surface, dismiss (migration 228, CONTRACT §8.6).

A manual imóvel (`SW-####`, migration 226) and a Vista listing may be the same
property. This module DETECTS the pairs, LISTS them and lets a human DISMISS
one. It never merges anything: the only thing that links two imóveis is the
admin-only `vinculo_service.vincular` (§8.7), and that is a link, not a merge.

DETECTION (`detectar`)
----------------------
Each manual imóvel is compared against the Vista catalog (the mirror
`imoveis`). Signals, strongest first:

====================== ===================================================== =====
sinal                  match                                                 score
====================== ===================================================== =====
`matricula_cri`        same matrícula (digits only) AND same CRI             0.95
`matricula`            same matrícula, CRI unknown on one side (also against 0.80
                       the mirror's `matricula_vista`, which has no CRI)
`endereco`             same logradouro (accent-folded, type prefix stripped) 0.70
                       + same número + (same CEP digits OR same bairro)
`empreendimento_area_  same empreendimento + área (total or privativa)       0.50
preco`                 within ±5% + price within ±10%
====================== ===================================================== =====

score = the highest signal + 0.05 per OTHER matched signal, capped at 0.99. A
pair is recorded at ≥ 0.50.

Two matrículas that are both known but name DIFFERENT CRIs are two different
cartório records: that is NOT a `matricula` match (a bare number repeats across
cartórios). The CRI is compared as accent-folded alphanumerics, strictly: a
looser comparison ("1" ≙ "1º CRI de Cotia") would pair properties of different
comarcas.

Re-detection updates `score`/`sinais`/`atualizado_em` on `pendente` rows. It
NEVER touches a `descartado` pair (never resurrected, even if its signals
change) nor a `confirmado` one, and it skips a manual imóvel that is already
linked and a Vista imóvel that already has a manual linked to it (one manual
per Vista row). A `pendente` pair whose signals later stop matching is left in
place: only a human resolves a pair.

Reads: manual side from `imovel_registry` (origem 'manual') + `imovel_dados`
(matrícula, CRI, `endereco_manual_*`, `empreendimento_manual`) +
`imovel_captacao` (áreas, valores); Vista side from the mirror `imoveis` (+ its
`imovel_dados` matrícula/CRI). All per-row reads are paged / batched past
PostgREST's 1 000-row cap, and the matching runs in Python over indexes, never
through `.or_()` (the test mock treats it as match-all).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.integrations.documents.text import strip_accents_upper
from noctusai_lib.primitives.exceptions import AppException, NotFoundError, ValidationError_

from app.modules.imovel_hub import busca_service
from app.modules.imovel_hub import dados_service as dados_svc
from app.services import table_reads

logger = logging.getLogger(__name__)

TABLE = "imovel_duplicata_candidatos"
REGISTRY_TABLE = "imovel_registry"
MIRROR_TABLE = "imoveis"
DADOS_TABLE = "imovel_dados"
CAPTACAO_TABLE = "imovel_captacao"

STATUS_VALIDOS = ("pendente", "descartado", "confirmado")

SINAL_MATRICULA_CRI = "matricula_cri"
SINAL_MATRICULA = "matricula"
SINAL_ENDERECO = "endereco"
SINAL_EMPREENDIMENTO = "empreendimento_area_preco"

#: Signal -> base score. The order of this dict is "strongest first".
SCORE_SINAL = {
    SINAL_MATRICULA_CRI: 0.95,
    SINAL_MATRICULA: 0.80,
    SINAL_ENDERECO: 0.70,
    SINAL_EMPREENDIMENTO: 0.50,
}
BONUS_OUTRO_SINAL = 0.05
SCORE_TETO = 0.99
LIMIAR = 0.50

TOLERANCIA_AREA = 0.05
TOLERANCIA_PRECO = 0.10

_PREFIXOS_LOGRADOURO = frozenset({"RUA", "R", "AVENIDA", "AV", "ALAMEDA", "AL"})
_SEM_NUMERO = frozenset({"", "SN", "S", "N"})

_MIRROR_COLS = (
    "codigo, codigo_norm, logradouro, numero, cep, bairro, empreendimento, "
    "area_total, area_privativa, valor_venda, valor_locacao, matricula_vista"
)
_DADOS_COLS = (
    "codigo, numero_matricula, numero_registro_imoveis, endereco_manual_cep, "
    "endereco_manual_logradouro, endereco_manual_numero, endereco_manual_bairro, "
    "empreendimento_manual"
)

#: Test/DI seam type: the hook callers (sync, manual create/edit) take the
#: detector as a parameter so a failing detector can be injected without
#: patching this module.
Detector = Callable[..., Any]


# ─── normalisation (pure) ─────────────────────────────────────────────────


def _digitos(valor: Any) -> Optional[str]:
    """Digits only, `None` when there are none (a matrícula `79.826` ≙ `79826`)."""
    d = re.sub(r"\D", "", str(valor or ""))
    return d or None


def _texto(valor: Any) -> str:
    """Accent-folded, uppercased, punctuation → space, whitespace collapsed."""
    folded = strip_accents_upper(str(valor or ""))
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", folded)).strip()


def _cri(valor: Any) -> Optional[str]:
    """The CRI as accent-folded alphanumerics (`1º CRI` ≙ `1o cri`), `None` if blank."""
    # `°` (degree sign) is the usual mistyped `º` (ordinal indicator).
    texto = str(valor or "").replace("°", "º")
    t = re.sub(r"[^A-Z0-9]+", "", strip_accents_upper(texto))
    return t or None


def logradouro_norm(valor: Any) -> Optional[str]:
    """Accent-folded, lowercased-equivalent, with ONE leading type prefix
    (rua / r. / avenida / av. / alameda / al.) removed."""
    tokens = _texto(valor).split()
    if tokens and tokens[0] in _PREFIXOS_LOGRADOURO:
        tokens = tokens[1:]
    return " ".join(tokens) or None


def _numero_imovel(valor: Any) -> Optional[str]:
    t = re.sub(r"[^A-Z0-9]+", "", strip_accents_upper(str(valor or "")))
    return None if t in _SEM_NUMERO else t


def _decimal(valor: Any) -> Optional[float]:
    return busca_service._numero(valor)


def _perto(a: Optional[float], b: Optional[float], tolerancia: float) -> bool:
    if not a or not b:
        return False
    return abs(a - b) <= tolerancia * max(a, b)


# ─── per-side facts ───────────────────────────────────────────────────────


def _fatos(
    codigo: str, dados: Optional[dict], *, endereco: dict, empreendimento: Any,
    areas: dict, valores: dict, matriculas_extra: tuple = (),
) -> dict:
    dados = dados or {}
    matriculas = {
        m for m in (_digitos(dados.get("numero_matricula")), *map(_digitos, matriculas_extra)) if m
    }
    return {
        "codigo": codigo,
        "matricula_dados": _digitos(dados.get("numero_matricula")),
        "matriculas": matriculas,
        "cri": _cri(dados.get("numero_registro_imoveis")),
        "cri_texto": (str(dados.get("numero_registro_imoveis") or "").strip() or None),
        "logradouro": logradouro_norm(endereco.get("logradouro")),
        "numero": _numero_imovel(endereco.get("numero")),
        "cep": _digitos(endereco.get("cep")),
        "bairro": _texto(endereco.get("bairro")) or None,
        "empreendimento": _texto(empreendimento) or None,
        "areas": areas,
        "valores": valores,
    }


def fatos_manual(codigo: str, dados: Optional[dict], captacao: Optional[dict]) -> dict:
    dados = dados or {}
    captacao = captacao or {}
    return _fatos(
        codigo, dados,
        endereco={
            "logradouro": dados.get("endereco_manual_logradouro"),
            "numero": dados.get("endereco_manual_numero"),
            "cep": dados.get("endereco_manual_cep"),
            "bairro": dados.get("endereco_manual_bairro"),
        },
        empreendimento=dados.get("empreendimento_manual"),
        areas={k: _decimal(captacao.get(k)) for k in ("area_total", "area_privativa")},
        valores={k: _decimal(captacao.get(k)) for k in ("valor_venda", "valor_locacao")},
    )


def fatos_vista(codigo: str, espelho: dict, dados: Optional[dict]) -> dict:
    return _fatos(
        codigo, dados,
        endereco=espelho,
        empreendimento=espelho.get("empreendimento"),
        areas={k: _decimal(espelho.get(k)) for k in ("area_total", "area_privativa")},
        valores={k: _decimal(espelho.get(k)) for k in ("valor_venda", "valor_locacao")},
        matriculas_extra=(espelho.get("matricula_vista"),),
    )


# ─── signals ──────────────────────────────────────────────────────────────


def sinais_do_par(m: dict, v: dict) -> list[dict]:
    """The signals that match for one (manual, vista) pair, strongest first.
    Pure: no IO."""
    sinais: list[dict] = []

    mat_m = m["matricula_dados"]
    if mat_m:
        compartilhadas = mat_m in v["matriculas"]
        if compartilhadas:
            cri_m, cri_v = m["cri"], v["cri"]
            via_dados = mat_m == v["matricula_dados"]
            if via_dados and cri_m and cri_v:
                if cri_m == cri_v:
                    sinais.append({
                        "sinal": SINAL_MATRICULA_CRI,
                        "detalhe": f"matrícula {mat_m} no mesmo CRI ({m['cri_texto']})",
                    })
                # both CRIs known and different: two cartório records, no signal
            else:
                sinais.append({
                    "sinal": SINAL_MATRICULA,
                    "detalhe": f"matrícula {mat_m} (CRI desconhecido em um dos lados)",
                })

    if (
        m["logradouro"] and m["logradouro"] == v["logradouro"]
        and m["numero"] and m["numero"] == v["numero"]
        and ((m["cep"] and m["cep"] == v["cep"]) or (m["bairro"] and m["bairro"] == v["bairro"]))
    ):
        sinais.append({
            "sinal": SINAL_ENDERECO,
            "detalhe": f"{m['logradouro'].title()}, {m['numero']}"
            + (f" — CEP {m['cep']}" if m["cep"] and m["cep"] == v["cep"] else f" — {m['bairro'].title()}"),
        })

    if m["empreendimento"] and m["empreendimento"] == v["empreendimento"]:
        area_ok = next(
            (k for k in ("area_total", "area_privativa")
             if _perto(m["areas"][k], v["areas"][k], TOLERANCIA_AREA)),
            None,
        )
        preco_ok = next(
            (k for k in ("valor_venda", "valor_locacao")
             if _perto(m["valores"][k], v["valores"][k], TOLERANCIA_PRECO)),
            None,
        )
        if area_ok and preco_ok:
            sinais.append({
                "sinal": SINAL_EMPREENDIMENTO,
                "detalhe": (
                    f"{m['empreendimento'].title()}: {area_ok.replace('_', ' ')} e "
                    f"{preco_ok.replace('_', ' ')} dentro da tolerância"
                ),
            })

    ordem = list(SCORE_SINAL)
    sinais.sort(key=lambda s: ordem.index(s["sinal"]))
    return sinais


def pontuar(sinais: list[dict]) -> float:
    """Highest signal + 0.05 per other matched signal, capped at 0.99."""
    if not sinais:
        return 0.0
    base = max(SCORE_SINAL[s["sinal"]] for s in sinais)
    return round(min(SCORE_TETO, base + BONUS_OUTRO_SINAL * (len(sinais) - 1)), 3)


# ─── detection ────────────────────────────────────────────────────────────


def _agora() -> str:
    return dados_svc._now()


def detectar(
    client: Any, org_id: UUID, codigos_manuais: Optional[list[str]] = None
) -> dict:
    """Detect possible duplicates between manual imóveis and the Vista catalog.

    `codigos_manuais=None` evaluates every (unlinked) manual imóvel of the org;
    a list restricts it to those códigos (the manual create/edit hook).
    Returns `{avaliados, criados, atualizados, ignorados_resolvidos}`.
    """
    alvo = {busca_service.canonical(c) for c in codigos_manuais} if codigos_manuais else None

    registry_manual = table_reads.paged_rows(
        client, REGISTRY_TABLE, org_id,
        order_col="codigo_canonical", id_key="codigo_canonical",
        select="id, codigo_canonical, vinculado_a",
        refine=lambda q: q.eq("origem_descoberta", "manual"),
    )
    manuais = [
        str(r["codigo_canonical"]) for r in registry_manual
        if not r.get("vinculado_a") and (alvo is None or str(r["codigo_canonical"]) in alvo)
    ]
    resumo = {"avaliados": len(manuais), "criados": 0, "atualizados": 0, "ignorados_resolvidos": 0}
    if not manuais:
        return resumo

    # Vista rows that already have a manual linked to them are out of the pool
    # (one manual per Vista row).
    ids_vista_ocupadas = {str(r["vinculado_a"]) for r in registry_manual if r.get("vinculado_a")}
    registry_vista = {
        str(r["codigo_canonical"]): r
        for r in table_reads.paged_rows(
            client, REGISTRY_TABLE, org_id,
            order_col="codigo_canonical", id_key="codigo_canonical",
            select="id, codigo_canonical",
        )
    }

    espelho = table_reads.paged_rows(
        client, MIRROR_TABLE, org_id, order_col="codigo", id_key="codigo", select=_MIRROR_COLS,
    )
    dados = {
        str(r["codigo"]): r
        for r in table_reads.paged_rows(
            client, DADOS_TABLE, org_id, order_col="codigo", id_key="codigo", select=_DADOS_COLS,
        )
    }
    captacao = {
        str(r["codigo_canonical"]): r
        for r in table_reads.in_batched_rows(
            client, CAPTACAO_TABLE, org_id, "codigo_canonical", manuais,
            order_col="codigo_canonical",
        )
    }

    manuais_set = set(manuais)
    vistas: list[dict] = []
    for row in espelho:
        codigo = busca_service.canonical(str(row.get("codigo_norm") or row.get("codigo") or ""))
        reg = registry_vista.get(codigo)
        # a manual código never appears in the mirror, but never pair a row with itself
        if not codigo or codigo in manuais_set or reg is None or str(reg["id"]) in ids_vista_ocupadas:
            continue
        vistas.append(fatos_vista(codigo, row, dados.get(codigo)))

    existentes = {
        (str(r["codigo_manual"]), str(r["codigo_vista"])): r
        for r in table_reads.paged_rows(client, TABLE, org_id)
    }

    for codigo_manual in manuais:
        m = fatos_manual(codigo_manual, dados.get(codigo_manual), captacao.get(codigo_manual))
        for v in vistas:
            sinais = sinais_do_par(m, v)
            score = pontuar(sinais)
            if score < LIMIAR:
                continue
            chave = (codigo_manual, v["codigo"])
            atual = existentes.get(chave)
            if atual is None:
                table_reads.table(client, TABLE).insert({
                    "org_id": str(org_id), "codigo_manual": codigo_manual,
                    "codigo_vista": v["codigo"], "score": score, "sinais": sinais,
                    "status": "pendente",
                }).execute()
                resumo["criados"] += 1
            elif atual.get("status") == "pendente":
                table_reads.table(client, TABLE).update({
                    "score": score, "sinais": sinais, "atualizado_em": _agora(),
                }).eq("org_id", str(org_id)).eq("id", atual["id"]).execute()
                resumo["atualizados"] += 1
            else:
                resumo["ignorados_resolvidos"] += 1
    return resumo


def detectar_sem_falhar(
    client: Any, org_id: UUID, codigos_manuais: Optional[list[str]] = None,
    *, detector: Optional[Detector] = None, origem: str = "",
) -> Optional[dict]:
    """Run the detector as a SEPARATE step of a write that must not fail
    because of it (the Vista sync, a manual create/edit). A failure is logged
    LOUDLY (with the traceback) and returned as `None` — never raised, never
    swallowed silently."""
    try:
        return (detector or detectar)(client, org_id, codigos_manuais)
    except Exception:  # noqa: BLE001 — a hook must never fail its host write
        logger.exception(
            "duplicatas: detection failed after %s for org=%s codigos=%s "
            "(the host write is NOT affected; re-run detection to recover)",
            origem or "write", org_id, codigos_manuais,
        )
        return None


# ─── reads / wire shapes ──────────────────────────────────────────────────


def _resumo_do_imovel(enriquecido: Optional[dict], codigo: str) -> dict:
    e = enriquecido or {}
    return {
        "codigo": codigo,
        "titulo": e.get("titulo"),
        "endereco_resumo": e.get("endereco"),
        "valor_venda": e.get("valor_venda"),
        "area_total": e.get("area_total"),
        "foto_destaque": e.get("foto_destaque"),
    }


def _par_out(row: dict, resumos: dict) -> dict:
    manual, vista = str(row["codigo_manual"]), str(row["codigo_vista"])
    return {
        "id": str(row["id"]),
        "score": float(row["score"]),
        "sinais": row.get("sinais") or [],
        "status": row["status"],
        "detectado_em": row.get("detectado_em"),
        "resolvido_por": row.get("resolvido_por"),
        "resolvido_em": row.get("resolvido_em"),
        "manual": _resumo_do_imovel(resumos.get(manual), manual),
        "vista": _resumo_do_imovel(resumos.get(vista), vista),
    }


def _pares_out(client: Any, org_id: UUID, rows: list[dict]) -> list[dict]:
    codigos = sorted({str(r["codigo_manual"]) for r in rows} | {str(r["codigo_vista"]) for r in rows})
    # each side shows its OWN data, not the linked listing's
    resumos = (
        busca_service.enriquecer(client, org_id, codigos, seguir_vinculo=False) if codigos else {}
    )
    return [_par_out(r, resumos) for r in rows]


def listar(client: Any, org_id: UUID, *, status: Optional[str] = "pendente") -> list[dict]:
    """`GET /duplicatas?status=` — highest score first."""
    if status is not None and status not in STATUS_VALIDOS:
        raise ValidationError_(
            f"status inválido: {status} (use {', '.join(STATUS_VALIDOS)})", field="status"
        )
    rows = table_reads.paged_rows(
        client, TABLE, org_id,
        eq_filters={"status": status} if status else None,
    )
    rows.sort(key=lambda r: (-float(r["score"]), str(r.get("detectado_em") or "")))
    return _pares_out(client, org_id, rows)


def obter_linha(client: Any, org_id: UUID, duplicata_id: Any) -> dict:
    rows = (
        table_reads.table(client, TABLE).select("*")
        .eq("org_id", str(org_id)).eq("id", str(duplicata_id)).limit(1).execute()
    ).data or []
    if not rows:
        raise NotFoundError("Duplicata", str(duplicata_id))
    return rows[0]


def obter_par(client: Any, org_id: UUID, duplicata_id: Any) -> dict:
    return _pares_out(client, org_id, [obter_linha(client, org_id, duplicata_id)])[0]


def ja_resolvida(duplicata_id: Any, status: str) -> AppException:
    return AppException(
        code="duplicata_ja_resolvida",
        message=f"Esta duplicata já foi resolvida ({status}).",
        status_code=409,
        details={"id": str(duplicata_id), "status": status},
    )


def descartar(client: Any, org_id: UUID, duplicata_id: Any, actor_id: Optional[UUID]) -> dict:
    """`POST /duplicatas/{id}/descartar` — "Não é o mesmo". `409
    duplicata_ja_resolvida` unless the pair is `pendente`."""
    linha = obter_linha(client, org_id, duplicata_id)
    if linha["status"] != "pendente":
        raise ja_resolvida(duplicata_id, linha["status"])
    agora = _agora()
    table_reads.table(client, TABLE).update({
        "status": "descartado",
        "resolvido_por": str(actor_id) if actor_id else None,
        "resolvido_em": agora, "atualizado_em": agora,
    }).eq("org_id", str(org_id)).eq("id", str(duplicata_id)).eq("status", "pendente").execute()
    return obter_par(client, org_id, duplicata_id)


def pendentes_do_imovel(client: Any, org_id: UUID, codigo: str) -> list[dict]:
    """`[{id, outro_codigo, score}]` — the pending pairs involving `codigo`,
    from either side (two reads, never `.or_()`)."""
    canonico = busca_service.canonical(codigo)
    out: list[dict] = []
    for coluna, outra in (("codigo_manual", "codigo_vista"), ("codigo_vista", "codigo_manual")):
        rows = (
            table_reads.table(client, TABLE).select("id, codigo_manual, codigo_vista, score")
            .eq("org_id", str(org_id)).eq("status", "pendente").eq(coluna, canonico)
            .limit(200).execute()
        ).data or []
        out.extend(
            {"id": str(r["id"]), "outro_codigo": str(r[outra]), "score": float(r["score"])}
            for r in rows
        )
    out.sort(key=lambda p: -p["score"])
    return out


__all__ = [
    "Detector", "LIMIAR", "SCORE_SINAL", "STATUS_VALIDOS", "descartar", "detectar",
    "detectar_sem_falhar", "listar", "logradouro_norm", "obter_par", "pendentes_do_imovel",
    "pontuar", "sinais_do_par",
]
