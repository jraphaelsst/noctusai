"""InfoSimples emission WATCHER — record every call, learn from the record.

Why this exists
---------------
InfoSimples' docs state that a holder of a "positiva com efeitos de negativa"
(PCEN) certidão cannot get a NEW one from the PGFN portal, but give no code or
message for that refusal — the only signal is the broad 600-798 failure range.
Instead of guessing, every InfoSimples call (every tipo, success or failure)
is recorded in `certidao_emissao_observacoes` (migration 186) and this module
turns the record into three things:

* a normalised failure SIGNATURE (`normalizar_assinatura`) so identical
  failures group together;
* a LEARNED classification of each signature — `pcen` (the `nova` failed and
  the immediate `2via` returned a PCEN certidão), `transitoria` (the `2via`
  failed too, or a later `nova` worked), or `desconhecida` — that
  `service._precisa_segunda_via` consults (`decidir_retry_2via`);
* a read-only report (`relatorio`) the `noctus.dev.certidoes_emissao_
  aprendizado` MCP tool renders, to correct our own docs where reality
  differs from InfoSimples'.

PURE by design: stdlib only, no `app.*` import. The MCP tool loads this very
file by path (`importlib`) so the classification the product acts on and the
one the report shows can never drift apart.

Nothing here may break an emission: `registrar` logs at ERROR and returns.
LGPD: no token, no birthdate, no name and no full CPF/CNPJ is ever stored —
`params` is an allowlist, the document is an HMAC key (`documento_hash`).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

TABELA = "certidao_emissao_observacoes"
PROVIDER = "infosimples"

#: Observations of ONE signature needed before it is trusted as a class.
LIMIAR_CONFIRMACAO = 3
#: The winning class must also outnumber the opposing one by this factor — a
#: signature that is sometimes PCEN and sometimes an outage is not "confirmed".
MARGEM_CONFIRMACAO = 3

CLASSE_PCEN = "pcen"
CLASSE_TRANSITORIA = "transitoria"
CLASSE_DESCONHECIDA = "desconhecida"

#: Failure range of InfoSimples (docs: `code in range(600, 799)`); 612 = no data
#: at source, a valid nada-consta, never a failure.
FALHA_DA_ORIGEM = range(600, 799)
CODIGO_NADA_CONSTA = 612

#: The only `params` values stored verbatim — none is personal data.
PARAMS_ALLOWLIST = ("tipo", "abrangencia", "modelo", "preferencia_emissao")

_MAX_ASSINATURA = 300


# --------------------------------------------------------------------------
# Signature
# --------------------------------------------------------------------------


def _sem_acento(texto: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(ch)
    )


def normalizar_assinatura(code: Any, code_message: Any, errors: Any) -> str:
    """Deterministic fingerprint of a failure: `"<code>|<message>|<errors>"`.

    Text is lowercased, accent-folded, stripped of URLs / e-mails / every digit
    (ids, protocolos, dates, CPFs) and whitespace-collapsed, so two failures
    that differ only by an id/date group as one. The `code` itself is kept —
    it is the one number that IS the signal.
    """
    partes: list[str] = []
    textos = [code_message] + (list(errors) if isinstance(errors, (list, tuple)) else [errors])
    vistos: set[str] = set()
    for bruto in textos:
        if not isinstance(bruto, str):
            continue
        t = _sem_acento(bruto).lower()
        t = re.sub(r"https?://\S+|\S+@\S+", " ", t)
        t = re.sub(r"\d+", " ", t)
        t = re.sub(r"[^a-z\s]", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        if t and t not in vistos:
            vistos.add(t)
            partes.append(t)
    codigo = str(code) if isinstance(code, int) else ""
    msg = partes[0] if partes else ""
    erros = "; ".join(partes[1:])
    return f"{codigo}|{msg}|{erros}"[:_MAX_ASSINATURA]


def e_data_tipo_pcen(data_tipo: Any) -> bool:
    """`data[0].tipo` reads "Positiva com efeitos de negativa" (any accent/case)."""
    if not isinstance(data_tipo, str):
        return False
    t = _sem_acento(data_tipo).lower()
    return "positiva" in t and "negativa" in t


# --------------------------------------------------------------------------
# Building one observation
# --------------------------------------------------------------------------


def _so_digitos(valor: Any) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def chave_documento(org_id: Any, documento: Any) -> Optional[str]:
    """HMAC-SHA256 of the document's digits, org-scoped — a stable grouping
    key that does not reveal the CPF/CNPJ. Salt: `CERTIDAO_OBS_SALT` env, else
    the org id alone (still not reversible without the org)."""
    digitos = _so_digitos(documento)
    if not digitos:
        return None
    salt = os.environ.get("CERTIDAO_OBS_SALT") or ""
    chave = f"{salt}|{org_id}".encode()
    return hmac.new(chave, digitos.encode(), hashlib.sha256).hexdigest()[:32]


def _data_br(valor: Any) -> Optional[str]:
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        return datetime.strptime(valor.strip(), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def _preco(raw: Any) -> tuple[Optional[str], Optional[bool]]:
    header = raw.get("header") if isinstance(raw, dict) else None
    if not isinstance(header, dict):
        return None, None
    preco: Optional[str] = None
    bruto = header.get("price")
    if bruto is not None:
        try:
            preco = str(Decimal(str(bruto)))
        except (InvalidOperation, ValueError):
            preco = None
    billable = header.get("billable")
    return preco, billable if isinstance(billable, bool) else None


def montar_observacao(
    *,
    config: dict,
    consulta: dict,
    params: dict,
    tentativa: int,
    http_status: Optional[int],
    resposta: Optional[dict],
    elapsed_ms: Optional[int],
    fallback_de: Optional[str] = None,
    erro_excecao: Optional[str] = None,
) -> dict:
    """One row for `certidao_emissao_observacoes`, built from ONE InfoSimples
    call. `resposta` is the parsed JSON (None when the call raised)."""
    org_id = consulta.get("org_id")
    resposta = resposta if isinstance(resposta, dict) else None
    code = resposta.get("code") if resposta else None
    code_message = resposta.get("code_message") if resposta else erro_excecao
    errors = resposta.get("errors") if resposta else ([erro_excecao] if erro_excecao else [])
    item: dict = {}
    if resposta and isinstance(resposta.get("data"), list) and resposta["data"]:
        if isinstance(resposta["data"][0], dict):
            item = resposta["data"][0]
    sucesso = code == 200 or code == CODIGO_NADA_CONSTA
    preco, billable = _preco(resposta)
    seguros = {k: params[k] for k in PARAMS_ALLOWLIST if k in params}
    seguros["chaves_enviadas"] = sorted(k for k in params if k != "token")
    nao_sucesso = None if sucesso else normalizar_assinatura(code, code_message, errors)
    return {
        "id": str(uuid4()),
        "org_id": str(org_id) if org_id else None,
        "consulta_id": consulta.get("id"),
        "tipo": config["tipo"],
        "provider": PROVIDER,
        "endpoint": config["endpoint"],
        "documento_tipo": consulta.get("tipo_documento"),
        "documento_hash": chave_documento(org_id, consulta.get("documento")),
        "params": seguros,
        "tentativa": tentativa,
        "preferencia_emissao": params.get("preferencia_emissao"),
        "http_status": http_status,
        "code": code if isinstance(code, int) else None,
        "code_message": (code_message or None) if isinstance(code_message, str) or code_message is None else str(code_message),
        "errors": [str(e)[:500] for e in errors] if isinstance(errors, list) else [],
        "sucesso": sucesso,
        "data_tipo": item.get("tipo") if isinstance(item.get("tipo"), str) else None,
        "data_situacao": item.get("situacao") if isinstance(item.get("situacao"), str) else None,
        "emissao_data": _data_br(item.get("emissao_data")),
        "validade": _data_br(item.get("validade_data") or item.get("validade")),
        "validade_prorrogada": _data_br(item.get("validade_prorrogada")),
        "conseguiu_emitir_negativa": (
            item.get("conseguiu_emitir_certidao_negativa")
            if isinstance(item.get("conseguiu_emitir_certidao_negativa"), bool) else None
        ),
        "elapsed_ms": elapsed_ms,
        "price_brl": preco,
        "billable": billable,
        "fallback_de": fallback_de,
        "assinatura": nao_sucesso,
    }


def registrar(db: Any, observacoes: Iterable[dict], *, resultado_id: Optional[str]) -> None:
    """Persist observations. NEVER raises — a recording failure is logged at
    ERROR and the emission carries on (the watcher must not be able to break
    what it watches). Inserts in order so `fallback_de` always points at a row
    that already exists."""
    for obs in observacoes:
        try:
            db.table(TABELA).insert({**obs, "resultado_id": resultado_id}).execute()
        except Exception:  # noqa: BLE001 — recording is best-effort by contract
            logger.error(
                "certidao_emissao_observacoes: could not record %s call (resultado %s)",
                obs.get("tipo"), resultado_id, exc_info=True,
            )


# --------------------------------------------------------------------------
# Learning
# --------------------------------------------------------------------------


def _ordenadas(observacoes: Iterable[dict]) -> list[dict]:
    return sorted(observacoes, key=lambda o: (str(o.get("created_at") or ""), o.get("tentativa") or 0))


def desfechos_por_assinatura(observacoes: Iterable[dict]) -> dict[str, dict[str, int]]:
    """For each failure signature of a `nova` call, what happened next.

    * `pcen`        — the immediate 2ª via (`fallback_de` → this row) succeeded
                      and reads PCEN;
    * `transitoria` — the 2ª via failed too, OR a later `nova` for the same
                      documento+tipo succeeded (the refusal went away on its own);
    * `via2_outro`  — the 2ª via succeeded but is NOT PCEN (informational).
    """
    obs = _ordenadas(observacoes)
    filhos: dict[str, list[dict]] = defaultdict(list)
    for o in obs:
        if o.get("fallback_de"):
            filhos[o["fallback_de"]].append(o)
    out: dict[str, dict[str, int]] = defaultdict(
        lambda: {"pcen": 0, "transitoria": 0, "via2_outro": 0, "total": 0}
    )
    for i, o in enumerate(obs):
        ass = o.get("assinatura")
        if o.get("sucesso") or not ass or o.get("preferencia_emissao") != "nova":
            continue
        bucket = out[ass]
        bucket["total"] += 1
        seg = filhos.get(o.get("id"), [])
        if seg:
            via2 = seg[0]
            if not via2.get("sucesso"):
                bucket["transitoria"] += 1
            elif e_data_tipo_pcen(via2.get("data_tipo")):
                bucket["pcen"] += 1
            else:
                bucket["via2_outro"] += 1
            continue
        # No 2ª via was tried: a later nova success for the same documento
        # means the failure was passing.
        recuperou = any(
            p.get("sucesso") and p.get("preferencia_emissao") == "nova"
            and p.get("tipo") == o.get("tipo")
            and p.get("documento_hash") == o.get("documento_hash")
            and (str(p.get("created_at") or ""), p.get("tentativa") or 0)
            > (str(o.get("created_at") or ""), o.get("tentativa") or 0)
            for p in obs[i + 1:]
        )
        if recuperou:
            bucket["transitoria"] += 1
    return dict(out)


def classificar(desfechos: dict[str, int]) -> str:
    """`pcen` / `transitoria` only with LIMIAR_CONFIRMACAO observations AND a
    MARGEM_CONFIRMACAO× lead over the opposing class; else `desconhecida`."""
    pcen, trans = desfechos.get("pcen", 0), desfechos.get("transitoria", 0)
    if pcen >= LIMIAR_CONFIRMACAO and pcen >= MARGEM_CONFIRMACAO * trans:
        return CLASSE_PCEN
    if trans >= LIMIAR_CONFIRMACAO and trans >= MARGEM_CONFIRMACAO * pcen:
        return CLASSE_TRANSITORIA
    return CLASSE_DESCONHECIDA


def classificar_assinaturas(observacoes: Iterable[dict]) -> dict[str, str]:
    """signature → class, over every observation given."""
    return {a: classificar(d) for a, d in desfechos_por_assinatura(observacoes).items()}


def decidir_retry_2via(assinatura: Optional[str], classificacoes: Optional[dict[str, str]]) -> bool:
    """Should a refused `nova` be retried as `2via`? A signature CONFIRMED as
    transitória saves the billed call; confirmed PCEN and UNKNOWN both retry
    (unknown = current behaviour: try once, record, learn)."""
    return (classificacoes or {}).get(assinatura or "") != CLASSE_TRANSITORIA


def preferencia_inicial(
    observacoes_do_documento: Iterable[dict], hoje: date, *, tipo: str = "cnd_federal"
) -> str:
    """`2via` straight away ONLY when this exact documento's latest successful
    emission was a PCEN 2ª via whose printed validity still covers today.

    Justified by the docs themselves: while that certidão is valid the PGFN
    cannot issue a new one, so `nova` is a billed call that must fail. Per-
    documento evidence, not a signature statistic — it needs no confirmation
    threshold. Anything else (no history, expired, a later non-PCEN) → `nova`,
    the default.
    """
    sucessos = [
        o for o in _ordenadas(observacoes_do_documento)
        if o.get("sucesso") and o.get("tipo") == tipo
    ]
    if not sucessos:
        return "nova"
    ultima = sucessos[-1]
    validade = ultima.get("validade")
    if (
        ultima.get("preferencia_emissao") == "2via"
        and e_data_tipo_pcen(ultima.get("data_tipo"))
        and validade
        and str(validade)[:10] >= hoje.isoformat()
    ):
        return "2via"
    return "nova"


# --------------------------------------------------------------------------
# DB-facing helpers (all best-effort — never raise into the emission path)
# --------------------------------------------------------------------------

TABELA_APRENDIZADOS = "certidao_emissao_aprendizados"
#: Marker in the WARNING line so ops/log review can grep it.
MARCADOR_LOG = "CERTIDAO_APRENDIZADO"
#: Most recent observations considered when (re)classifying one tipo.
JANELA_OBSERVACOES = 1000


def _ultimos_aprendizados(linhas: Iterable[dict]) -> dict[str, dict]:
    """Latest event per signature (rows may arrive in any order)."""
    out: dict[str, dict] = {}
    for r in sorted(linhas, key=lambda r: str(r.get("decidido_em") or "")):
        out[r["assinatura"]] = r
    return out


def carregar_classificacoes(db: Any, org_id: Any, tipo: str) -> dict[str, str]:
    """signature → learned class (latest event per signature). `{}` on any
    failure — the trigger then behaves as unknown (today's behaviour)."""
    try:
        linhas = (
            db.table(TABELA_APRENDIZADOS).select("assinatura,classe,decidido_em")
            .eq("org_id", str(org_id)).eq("tipo", tipo).execute()
        ).data or []
        return {a: r["classe"] for a, r in _ultimos_aprendizados(linhas).items()}
    except Exception:  # noqa: BLE001 — learning must never block emission
        logger.warning("certidao_emissao_aprendizados: could not load (org %s, %s)", org_id, tipo, exc_info=True)
        return {}


def carregar_preferencia_inicial(db: Any, consulta: dict, tipo: str, hoje: date) -> str:
    """`preferencia_inicial` for this documento from its own history; `nova`
    (the default) when unknown or on any failure."""
    chave = chave_documento(consulta.get("org_id"), consulta.get("documento"))
    if not chave:
        return "nova"
    try:
        linhas = (
            db.table(TABELA).select(
                "tipo,sucesso,preferencia_emissao,data_tipo,validade,created_at,tentativa"
            ).eq("org_id", str(consulta.get("org_id"))).eq("tipo", tipo)
            .eq("documento_hash", chave).eq("sucesso", True)
            .order("created_at", desc=True).limit(5).execute()
        ).data or []
        return preferencia_inicial(linhas, hoje, tipo=tipo)
    except Exception:  # noqa: BLE001
        logger.warning("certidao_emissao_observacoes: could not read documento history (%s)", tipo, exc_info=True)
        return "nova"


def eventos_de_aprendizado(
    observacoes: Iterable[dict], ultimos: dict[str, dict]
) -> list[dict]:
    """Pure: the reclassification events implied by `observacoes` given the
    latest stored event per signature. A first-time `desconhecida` is not an
    event (nothing was learned)."""
    obs = list(observacoes)
    desf = desfechos_por_assinatura(obs)
    quando: dict[str, list[str]] = defaultdict(list)
    for o in obs:
        if o.get("assinatura"):
            quando[o["assinatura"]].append(str(o.get("created_at") or ""))
    eventos = []
    for ass, d in sorted(desf.items()):
        classe = classificar(d)
        anterior = (ultimos.get(ass) or {}).get("classe", CLASSE_DESCONHECIDA)
        if classe == anterior:
            continue
        datas = sorted(x for x in quando[ass] if x)
        eventos.append({
            "assinatura": ass, "classe": classe, "classe_anterior": anterior,
            "evidencia": dict(d),
            "primeira_obs_em": datas[0] if datas else None,
            "ultima_obs_em": datas[-1] if datas else None,
        })
    return eventos


def aprender(db: Any, org_id: Any, tipo: str) -> list[dict]:
    """Reclassify `tipo`'s signatures from the recent observations; persist an
    event for every change and log it at WARNING with `MARCADOR_LOG`. Returns
    the events; `[]` (logged) on any failure."""
    try:
        obs = (
            db.table(TABELA).select(
                "id,tipo,sucesso,assinatura,preferencia_emissao,fallback_de,data_tipo,"
                "documento_hash,created_at,tentativa"
            ).eq("org_id", str(org_id)).eq("tipo", tipo)
            .order("created_at", desc=True).limit(JANELA_OBSERVACOES).execute()
        ).data or []
        linhas = (
            db.table(TABELA_APRENDIZADOS).select("assinatura,classe,decidido_em")
            .eq("org_id", str(org_id)).eq("tipo", tipo).execute()
        ).data or []
        eventos = eventos_de_aprendizado(obs, _ultimos_aprendizados(linhas))
        for ev in eventos:
            db.table(TABELA_APRENDIZADOS).insert(
                {**ev, "org_id": str(org_id), "tipo": tipo}
            ).execute()
            logger.warning(
                "%s tipo=%s assinatura=%r %s -> %s evidencia=%s",
                MARCADOR_LOG, tipo, ev["assinatura"], ev["classe_anterior"], ev["classe"], ev["evidencia"],
            )
        return eventos
    except Exception:  # noqa: BLE001
        logger.error("certidao_emissao_aprendizados: could not learn (org %s, %s)", org_id, tipo, exc_info=True)
        return []


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def _mascarar(texto: Any) -> Optional[str]:
    if not isinstance(texto, str):
        return None
    return re.sub(r"\d{6,}", "#", texto)[:200]


def _dec(valor: Any) -> Decimal:
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def relatorio(observacoes: Iterable[dict]) -> dict:
    """Per tipo: call counts, success rate, failure signatures (count, class,
    masked examples), cost of fallback retries, and suggested trigger changes."""
    obs = _ordenadas(observacoes)
    classes = classificar_assinaturas(obs)
    desf = desfechos_por_assinatura(obs)
    por_id = {o.get("id"): o for o in obs}
    por_tipo: dict[str, list[dict]] = defaultdict(list)
    for o in obs:
        por_tipo[o.get("tipo") or "?"].append(o)
    tipos: dict[str, dict] = {}
    sugestoes: list[str] = []
    for tipo, lista in sorted(por_tipo.items()):
        ok = [o for o in lista if o.get("sucesso")]
        falhas = [o for o in lista if not o.get("sucesso")]
        sigs: dict[str, dict] = {}
        for o in falhas:
            a = o.get("assinatura") or "?"
            s = sigs.setdefault(a, {
                "assinatura": a, "ocorrencias": 0, "classe": classes.get(a, CLASSE_DESCONHECIDA),
                "desfechos": desf.get(a), "exemplos": [],
            })
            s["ocorrencias"] += 1
            if len(s["exemplos"]) < 3:
                s["exemplos"].append({
                    "code": o.get("code"), "code_message": _mascarar(o.get("code_message")),
                    "errors": [_mascarar(e) for e in (o.get("errors") or [])[:2]],
                    "preferencia_emissao": o.get("preferencia_emissao"),
                })
        retries = [o for o in lista if o.get("fallback_de")]
        desperdicio = [
            por_id[o["fallback_de"]] for o in retries
            if o["fallback_de"] in por_id and not o.get("sucesso")
        ]
        custo_retries = sum((_dec(o.get("price_brl")) for o in retries if o.get("billable") is not False), Decimal(0))
        custo_retries_falhos = sum((_dec(o.get("price_brl")) for o in retries if not o.get("sucesso") and o.get("billable") is not False), Decimal(0))
        pcen_obs = [o for o in ok if e_data_tipo_pcen(o.get("data_tipo"))]
        tipos[tipo] = {
            "chamadas": len(lista),
            "sucessos": len(ok),
            "taxa_sucesso": round(len(ok) / len(lista), 4) if lista else None,
            "assinaturas_de_falha": sorted(sigs.values(), key=lambda s: -s["ocorrencias"]),
            "retries_2via": len(retries),
            "retries_2via_sem_sucesso": len(desperdicio),
            "custo_retries_brl": str(custo_retries),
            "custo_retries_sem_sucesso_brl": str(custo_retries_falhos),
            "emissoes_pcen": len(pcen_obs),
        }
        for s in sigs.values():
            d = s["desfechos"] or {}
            if s["classe"] == CLASSE_TRANSITORIA:
                sugestoes.append(
                    f"{tipo}: a assinatura '{s['assinatura']}' é transitória "
                    f"({d.get('transitoria', 0)} casos) — o gatilho já NÃO pede 2ª via para ela."
                )
            elif s["classe"] == CLASSE_PCEN:
                sugestoes.append(
                    f"{tipo}: a assinatura '{s['assinatura']}' é PCEN confirmada "
                    f"({d.get('pcen', 0)} casos) — a 2ª via é sempre pedida; considere citá-la na doc."
                )
            elif d.get("total", 0) >= 1:
                faltam = LIMIAR_CONFIRMACAO - max(d.get("pcen", 0), d.get("transitoria", 0))
                sugestoes.append(
                    f"{tipo}: a assinatura '{s['assinatura']}' ainda é desconhecida "
                    f"(faltam ~{max(faltam, 0)} observações conclusivas)."
                )
    return {
        "total_observacoes": len(obs),
        "limiar_confirmacao": LIMIAR_CONFIRMACAO,
        "margem_confirmacao": MARGEM_CONFIRMACAO,
        "tipos": tipos,
        "sugestoes": sugestoes,
    }
