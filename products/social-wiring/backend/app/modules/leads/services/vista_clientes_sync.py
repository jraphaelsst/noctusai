"""Vista clientes -> our lead people, FILL-EMPTY-ONLY (CONTRACT ad-lead-intake § 8; owner 2026-11-09).

  "sync our lead data with theirs. they only add to leads, divergencies get warned but never overwritten. we bring what we have from
   leads there and enrich our own data"

THE RULE (one way, Vista -> us; NOTHING is ever written to Vista -- the seed Protocol has no client write):
  * a Vista value fills an EMPTY column of `social_wiring.clientes` (the canonical person layer of a lead: `clientes.chave_canonica`
    == `leads.contato_norm`; it is where nome_completo / celular / email / data_nascimento / estado_civil / profissao / endereco_* /
    cpf / rg already live, with their `*_origem` / `*_em` provenance columns -- stamped `vista`);
  * a DIFFERENT non-empty value is NEVER overwritten: it becomes one pending row in `vista_cliente_avisos` (`campo_divergente`) -- the
    same warn-never-overwrite organ as `lead_corretor_divergencias` / `imovel_ref_avisos` -- and ONE in-app warning per run;
  * the address is a BLOCK: filled only when ours is entirely empty (never a half-ours / half-Vista address); otherwise each differing
    sub-field is a divergence;
  * a phone / e-mail of ours that equals ANY phone / e-mail Vista holds for that person is not a divergence (people have several).

MATCHING (a Vista cliente -> OUR person): normalised phone (`noctusai_lib.primitives.phone.normalize_phone`, over Celular / FonePrincipal /
FoneResidencial / FoneComercial) or e-mail (EmailResidencial / EmailComercial) against `chave_canonica` / `celular` / `email`, or CPF (only
while the LGPD flag is on). Several of our people for one Vista cliente => `match_ambiguo` notice, NO write. No match => NOT created
here (an owner decision) -- counted by the Vista flags Cliente / Proprietario / Fiador. The link (`vista_cliente_links`) makes later
runs incremental (`modo=novos` skips linked ones; `refazer` re-compares them).

ALLOWLIST: `CAMPOS_IMPORTAVEIS` (+ `CAMPOS_IDENTIDADE` behind `importar_identidade`, default OFF) is the ONE place that says what is
brought; the item is projected to it on arrival, and `VISTA_PROIBIDOS` (SenhaWeb, UsuarioWeb, Banco/Agencia/Conta, CreditoSituacao,
CreditoMensagem, CODIGO_CREDPAGO) can never be requested -- asserted at import.

PACING: every Vista call goes through the client's per-org bucket (`VistaClient._request`); the org's budget is
`vista_clientes_sync_estado.vista_rps`. A real run is BOUNDED (`limite` per call, resumable `cursor` = the offset into Vista's list) and
ALWAYS manual: no scheduler runs it. DRY-RUN (default) reads Vista, writes nothing, and reports field NAMES only, never values.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.primitives.accents import fold_accents
from noctusai_lib.primitives.phone import normalize_phone

from app.services import table_reads

logger = logging.getLogger(__name__)

T_CLIENTES = "clientes"
T_LINKS = "vista_cliente_links"
T_AVISOS = "vista_cliente_avisos"
T_ESTADO = "vista_clientes_sync_estado"
TIPO_DIVERGENTE = "campo_divergente"
TIPO_AMBIGUO = "match_ambiguo"
ST_PENDENTE = "pendente"
ACOES = ("resolvida", "ignorada")
ORIGEM = "vista"
PAGE_SIZE = 50
LIMITE_PADRAO = 50
LIMITE_MAX = 500
AMOSTRA = 10
MODOS = ("novos", "refazer")

# ─── the allowlist (ONE place) ───────────────────────────────────────────

#: our `clientes` column -> the Vista field(s) it is filled from (first non-empty wins).
CAMPOS_IMPORTAVEIS: dict[str, tuple[str, ...]] = {
    "nome_completo": ("Nome",),
    "celular": ("Celular",),
    "email": ("EmailResidencial", "EmailComercial"),
    "data_nascimento": ("DataNascimento",),
    "estado_civil": ("EstadoCivil",),
    "profissao": ("Profissao",),
    "endereco_logradouro": ("EnderecoResidencial",),
    "endereco_numero": ("EnderecoNumero",),
    "endereco_complemento": ("EnderecoComplemento",),
    "endereco_bairro": ("BairroResidencial",),
    "endereco_cidade": ("CidadeResidencial",),
    "endereco_uf": ("UFResidencial",),
    "endereco_cep": ("CEPResidencial",),
}
#: LGPD gate: only while `importar_identidade` is on (default OFF). Spouse data is not imported at all (no home column for it here).
CAMPOS_IDENTIDADE: dict[str, tuple[str, ...]] = {"cpf": ("CPFCNPJ",), "rg": ("RG",), "rg_orgao_expedidor": ("RGEmissor",)}
#: only used to MATCH (never stored by this sync).
CAMPOS_CHAVE = ("FonePrincipal", "FoneResidencial", "FoneComercial")
FLAGS = ("Cliente", "Proprietario", "Fiador")
BLOCO_ENDERECO = tuple(c for c in CAMPOS_IMPORTAVEIS if c.startswith("endereco_"))
#: never requested, never read, never stored.
VISTA_PROIBIDOS = ("SenhaWeb", "UsuarioWeb", "Banco", "Agencia", "Conta", "CreditoSituacao", "CreditoMensagem", "CODIGO_CREDPAGO")
#: (origem column, em column) per filled column, where the cliente schema has provenance.
PROVENIENCIA: dict[str, tuple[str, str]] = {
    "email": ("email_origem", "email_em"),
    "data_nascimento": ("data_nascimento_origem", "data_nascimento_em"),
    "estado_civil": ("estado_civil_origem", "estado_civil_em"),
    "profissao": ("profissao_origem", "profissao_em"),
    **{c: ("endereco_origem", "endereco_em") for c in BLOCO_ENDERECO},
    "cpf": ("cpf_origem", "cpf_em"),
    "rg": ("rg_origem", "rg_em"),
    "rg_orgao_expedidor": ("rg_orgao_expedidor_origem", "rg_orgao_expedidor_em"),
}
MASCARADOS = ("cpf", "rg")


def campos_vista(identidade: bool) -> list[str]:
    """The Vista projection requested (the allowlist), in a stable order. Identity fields only with the LGPD flag."""
    mapa = {**CAMPOS_IMPORTAVEIS, **(CAMPOS_IDENTIDADE if identidade else {})}
    out = ["Codigo", *FLAGS, *CAMPOS_CHAVE]
    for fontes in mapa.values():
        out.extend(fontes)
    return list(dict.fromkeys(out))


assert not set(VISTA_PROIBIDOS) & set(campos_vista(True)), "a forbidden Vista field leaked into the allowlist"

# ─── normalisation ───────────────────────────────────────────────────────

_ESTADO_CIVIL = {
    "solteiro": "solteiro", "solteira": "solteiro", "casado": "casado", "casada": "casado", "divorciado": "divorciado", "divorciada": "divorciado",
    "viuvo": "viuvo", "viuva": "viuvo", "separado": "separado_judicialmente", "separada": "separado_judicialmente",
    "separado judicialmente": "separado_judicialmente", "separada judicialmente": "separado_judicialmente",
    "uniao estavel": "uniao_estavel", "uniao estavel.": "uniao_estavel", "amasiado": "uniao_estavel", "amasiada": "uniao_estavel",
}


def _txt(v: Any) -> Optional[str]:
    t = re.sub(r"\s+", " ", str(v)).strip() if v is not None else ""
    return t or None


def vazio(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _digitos(v: Any) -> str:
    return re.sub(r"\D", "", str(v or ""))


def _data(v: Any) -> Optional[str]:
    t = _txt(v)
    if not t or t.startswith("0000"):
        return None
    for fmt, n in (("%Y-%m-%d", 10), ("%d/%m/%Y", 10)):
        try:
            d = datetime.strptime(t[:n], fmt).date()
        except ValueError:
            continue
        return d.isoformat() if 1900 <= d.year <= date.today().year else None
    return None


def normalizar(coluna: str, bruto: Any) -> Optional[str]:
    """The value in OUR shape for `coluna`, or None when Vista's is empty / not usable (never guessed)."""
    t = _txt(bruto)
    if t is None:
        return None
    if coluna == "celular":
        return normalize_phone(t)
    if coluna == "email":
        e = t.lower()
        return e if "@" in e and " " not in e else None
    if coluna == "data_nascimento":
        return _data(t)
    if coluna == "estado_civil":
        return _ESTADO_CIVIL.get(re.sub(r"[^a-z ]", "", fold_accents(t).lower()).strip())
    if coluna == "endereco_cep":
        d = _digitos(t)
        return f"{d[:5]}-{d[5:]}" if len(d) == 8 else None
    if coluna == "endereco_uf":
        u = t.upper()
        return u if re.fullmatch(r"[A-Z]{2}", u) else None
    if coluna == "cpf":
        d = _digitos(t)  # a CNPJ (14 digits) is not a person's CPF
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 and len(set(d)) > 1 else None
    return t


def _comparavel(coluna: str, v: Any) -> str:
    t = _txt(v) or ""
    if coluna == "celular":
        return normalize_phone(t) or _digitos(t)
    if coluna in ("cpf", "rg", "endereco_cep"):
        return re.sub(r"[^0-9A-Za-z]", "", t).upper()
    if coluna == "data_nascimento":
        return _data(t) or t
    return re.sub(r"\s+", " ", fold_accents(t).lower()).strip()


def mascarar(coluna: str, v: Any) -> Optional[str]:
    t = _txt(v)
    if t is None or coluna not in MASCARADOS:
        return t
    return "***" + re.sub(r"[^0-9A-Za-z]", "", t)[-3:]


# ─── one Vista cliente, projected + normalised ───────────────────────────


def mapear_cliente(item: dict, identidade: bool = False) -> dict[str, Any]:
    """Project a raw Vista item onto the allowlist and normalise it. Anything not on the allowlist is dropped HERE."""
    permitidos = set(campos_vista(identidade))
    bruto = {k: v for k, v in item.items() if k in permitidos}
    mapa = {**CAMPOS_IMPORTAVEIS, **(CAMPOS_IDENTIDADE if identidade else {})}
    valores: dict[str, str] = {}
    for coluna, fontes in mapa.items():
        for f in fontes:
            v = normalizar(coluna, bruto.get(f))
            if v is not None:
                valores[coluna] = v
                break
    telefones = {n for f in ("Celular", *CAMPOS_CHAVE) if (n := normalize_phone(_txt(bruto.get(f)))) }
    emails = {e for f in ("EmailResidencial", "EmailComercial") if (e := normalizar("email", bruto.get(f)))}
    cpf = valores.get("cpf")
    flags = {f: str(bruto.get(f) or "").strip().lower() in ("sim", "s", "true", "1") for f in FLAGS}
    return {"codigo": _txt(bruto.get("Codigo")), "valores": valores, "telefones": telefones, "emails": emails, "cpf": cpf, "flags": flags}


# ─── the pure rule: fill empty, warn on divergence ───────────────────────


def _nosso(coluna: str, p: dict) -> Optional[str]:
    """Our value for a column, with the canonical-key fallback the checklist already uses (phone-keyed person has no `celular`)."""
    v = p.get(coluna)
    if coluna == "nome_completo" and vazio(v):
        return None  # `nome` is a channel name, a different assertion
    if vazio(v) and coluna == "celular" and p.get("chave_tipo") == "telefone":
        v = p.get("chave_canonica")
    if vazio(v) and coluna == "email" and p.get("chave_tipo") == "email":
        v = p.get("chave_canonica")
    return None if vazio(v) else str(v)


def planejar(vista: dict[str, Any], pessoa: dict[str, Any], identidade: bool = False) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """`(fills, divergencias)` for ONE matched pair. `fills` only ever targets a column that is empty on our side; a differing non-empty
    value is a divergence and is never in `fills`. Pure: no I/O."""
    mapa = {**CAMPOS_IMPORTAVEIS, **(CAMPOS_IDENTIDADE if identidade else {})}
    fills: dict[str, str] = {}
    diverg: list[dict[str, Any]] = []
    endereco_vazio = all(_nosso(c, pessoa) is None for c in BLOCO_ENDERECO)
    for coluna in mapa:
        novo = vista["valores"].get(coluna)
        if novo is None:
            continue
        atual = _nosso(coluna, pessoa)
        if atual is None:
            if coluna in BLOCO_ENDERECO and not endereco_vazio:
                continue  # a block: never a half-ours / half-Vista address
            fills[coluna] = novo
            continue
        if _comparavel(coluna, atual) == _comparavel(coluna, novo):
            continue
        if coluna == "celular" and _comparavel("celular", atual) in vista["telefones"]:
            continue
        if coluna == "email" and atual.lower() in vista["emails"]:
            continue
        diverg.append({"campo": coluna, "valor_nosso": mascarar(coluna, atual), "valor_vista": mascarar(coluna, novo)})
    return fills, diverg


# ─── matching ────────────────────────────────────────────────────────────

_SELECT = ",".join(
    ["id", "nome", "chave_canonica", "chave_tipo", "arquivado_em", *CAMPOS_IMPORTAVEIS, *CAMPOS_IDENTIDADE]
)


def _chave_indice(coluna: str, r: dict) -> tuple[str, str]:
    v = r.get(coluna)
    if coluna == "chave_canonica":
        return ("telefone", str(v)) if r.get("chave_tipo") == "telefone" else ("email", str(v).lower())
    if coluna == "celular":
        return ("telefone", _comparavel("celular", v))
    if coluna == "email":
        return ("email", str(v).lower())
    return ("cpf", _comparavel("cpf", v))


def _candidatos(client: Any, org_id: UUID, itens: list[dict]) -> tuple[dict[str, dict[str, set[str]]], dict[str, dict]]:
    """`({vista_codigo: {cliente_id: {via...}}}, {cliente_id: row})` for a page of mapped Vista clientes: one batched query per key kind."""
    fones = sorted({t for i in itens for t in i["telefones"]})
    mails = sorted({e for i in itens for e in i["emails"]})
    cpf_vars = sorted({v for i in itens if i["cpf"] for v in (i["cpf"], _digitos(i["cpf"]))})
    pessoas: dict[str, dict] = {}
    indice: dict[tuple[str, str], set[str]] = {}
    for coluna, valores in (("chave_canonica", [*fones, *mails]), ("celular", fones), ("email", mails), ("cpf", cpf_vars)):
        for r in table_reads.in_batched_rows(client, T_CLIENTES, org_id, coluna, valores, select=_SELECT):
            if r.get("arquivado_em"):
                continue
            pessoas[str(r["id"])] = r
            indice.setdefault(_chave_indice(coluna, r), set()).add(str(r["id"]))
    saida: dict[str, dict[str, set[str]]] = {}
    for i in itens:
        achados: dict[str, set[str]] = {}
        chaves = [("telefone", t, "telefone") for t in i["telefones"]] + [("email", e, "email") for e in i["emails"]]
        if i["cpf"]:
            chaves.append(("cpf", _comparavel("cpf", i["cpf"]), "cpf"))
        for tipo, valor, via in chaves:
            for cid in indice.get((tipo, valor), ()):
                achados.setdefault(cid, set()).add(via)
        saida[i["codigo"]] = achados
    return saida, pessoas


def _casado_por(vias: set[str]) -> str:
    return "cpf" if "cpf" in vias else ("telefone" if "telefone" in vias else "email")


# ─── persistence ─────────────────────────────────────────────────────────


def _t(client: Any, nome: str):
    return client.table(nome)


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def estado_da_org(client: Any, org_id: UUID) -> dict[str, Any]:
    rows = _t(client, T_ESTADO).select("*").eq("org_id", str(org_id)).limit(1).execute().data or []
    base = {"org_id": str(org_id), "vista_rps": None, "importar_identidade": False, "ultimo_cursor": None, "ultima_execucao_em": None, "ultimo_resumo": None}
    return {**base, **(rows[0] if rows else {})}


def salvar_config(client: Any, org_id: UUID, *, vista_rps: Optional[float], importar_identidade: bool, user_id: Any = None) -> dict[str, Any]:
    if vista_rps is not None and not (0.2 <= float(vista_rps) <= 10):
        raise ValueError("vista_rps must be between 0.2 and 10 requests/second")
    patch = {"vista_rps": vista_rps, "importar_identidade": bool(importar_identidade), "updated_at": _agora(), "updated_by": str(user_id) if user_id else None}
    if (_t(client, T_ESTADO).select("org_id").eq("org_id", str(org_id)).limit(1).execute().data or []):
        _t(client, T_ESTADO).update(patch).eq("org_id", str(org_id)).execute()
    else:
        _t(client, T_ESTADO).insert({"org_id": str(org_id), **patch}).execute()
    return estado_da_org(client, org_id)


def _aplicar(client: Any, org_id: UUID, cliente_id: str, fills: dict[str, str]) -> None:
    patch: dict[str, Any] = dict(fills)
    agora = _agora()
    for coluna in fills:
        if coluna in PROVENIENCIA:
            origem, em = PROVENIENCIA[coluna]
            patch[origem], patch[em] = ORIGEM, agora
    patch["updated_at"] = agora
    _t(client, T_CLIENTES).update(patch).eq("org_id", str(org_id)).eq("id", cliente_id).execute()


def _gravar_link(client: Any, org_id: UUID, existente: Optional[dict], codigo: str, cliente_id: str, por: str, flags: dict, preenchidos: list[str]) -> None:
    agora = _agora()
    if existente is not None:
        junto = sorted(set(existente.get("campos_preenchidos") or []) | set(preenchidos))
        _t(client, T_LINKS).update({"ultima_sync_em": agora, "campos_preenchidos": junto, "flags": flags}).eq("org_id", str(org_id)).eq("id", str(existente["id"])).execute()
        return
    _t(client, T_LINKS).insert({
        "id": str(uuid4()), "org_id": str(org_id), "cliente_id": cliente_id, "vista_codigo": codigo, "casado_por": por, "flags": flags,
        "campos_preenchidos": sorted(preenchidos), "created_at": agora, "ultima_sync_em": agora,
    }).execute()


def _abrir(client: Any, org_id: UUID, abertos: set[tuple], aviso: dict) -> bool:
    chave = (aviso["tipo"], aviso["vista_codigo"], aviso.get("campo", ""), str(aviso.get("cliente_id") or ""))
    if chave in abertos:
        return False
    _t(client, T_AVISOS).insert({"id": str(uuid4()), "org_id": str(org_id), "status": ST_PENDENTE, "created_at": _agora(), "campo": "", **aviso}).execute()
    abertos.add(chave)
    return True


def _avisos_abertos(client: Any, org_id: UUID) -> set[tuple]:
    rows = table_reads.paged_rows(client, T_AVISOS, org_id, eq_filters={"status": ST_PENDENTE})
    return {(r["tipo"], r["vista_codigo"], r.get("campo") or "", str(r.get("cliente_id") or "")) for r in rows}


def _notificar(org_id: UUID, divergencias: int, ambiguos: int) -> None:
    try:
        from noctusai_lib.domain.notifications import notify_org_admins

        from app.database import get_core_client

        notify_org_admins(
            get_core_client(), org_id=org_id, kind="vista_cliente_aviso",
            title="Clientes do Vista com dados diferentes dos nossos",
            message=f"{divergencias} divergência(s) de campo e {ambiguos} cliente(s) com mais de um lead possível. Nada foi sobrescrito; confira.",
            produto="social-wiring", link="/leads", entidade=None,
        )
    except Exception:  # noqa: BLE001 -- the notice rows are the record
        logger.exception("vista clientes sync: in-app warning failed for org=%s", org_id)


# ─── the run ─────────────────────────────────────────────────────────────


async def _ler_lote(adapter: Any, campos: list[str], offset: int, limite: int, rel: dict) -> Optional[list[dict]]:
    """`limite` raw Vista rows starting at `offset` (page = offset // 50 + 1), or None when Vista failed (resumable: the cursor is unchanged)."""
    linhas: list[dict] = []
    pagina, pular = offset // PAGE_SIZE + 1, offset % PAGE_SIZE
    while len(linhas) < limite:
        rel["chamadas"] += 1
        try:
            rows, pag = await adapter.list_clientes(page=pagina, page_size=PAGE_SIZE, fields=campos)
        except Exception as exc:  # noqa: BLE001 -- surfaced in the report; the Vista client already redacted the key
            rel["erros"].append(f"pagina {pagina}: {type(exc).__name__}: {exc}"[:240])
            logger.error("vista clientes sync: page %d failed", pagina, exc_info=True)
            return None
        rel["total_vista"] = int((pag or {}).get("total") or rel["total_vista"] or 0)
        linhas.extend(rows[pular:])
        pular = 0
        if not rows or pagina >= int((pag or {}).get("paginas") or pagina):
            break
        pagina += 1
    return linhas[:limite]


async def sincronizar(
    client: Any, adapter: Any, org_id: UUID, *, dry_run: bool = True, limite: int = LIMITE_PADRAO, cursor: Optional[str] = None,
    modo: str = "novos", pausa_s: float = 0.0,
) -> dict[str, Any]:
    """One BOUNDED batch (`limite` Vista clientes from `cursor`). Never raises for a Vista outcome; a real run never overwrites."""
    if modo not in MODOS:
        raise ValueError(f"modo must be one of {MODOS}, got {modo!r}")
    limite = max(1, min(int(limite), LIMITE_MAX))
    offset = int(cursor) if cursor not in (None, "") else 0
    estado = estado_da_org(client, org_id)
    identidade = bool(estado["importar_identidade"])
    rel: dict[str, Any] = {
        "dry_run": dry_run, "modo": modo, "identidade": identidade, "cursor": str(offset), "lote": 0, "total_vista": 0, "chamadas": 0,
        "ja_vinculados": 0, "casados": 0, "campos_preenchidos": 0, "divergencias": 0, "ambiguos": 0, "sem_match": 0,
        "sem_match_por_flag": {"cliente": 0, "proprietario": 0, "fiador": 0, "sem_flag": 0},
        "amostra": {"casamentos": [], "preenchimentos": [], "divergencias": [], "ambiguos": []}, "erros": [], "proximo_cursor": None,
    }
    linhas = await _ler_lote(adapter, campos_vista(identidade), offset, limite, rel)
    if linhas is None:
        rel["status"] = "erro"
        rel["proximo_cursor"] = str(offset)  # nothing consumed: the caller retries the same batch
        return rel
    rel["lote"] = len(linhas)
    itens = [m for m in (mapear_cliente(r, identidade) for r in linhas) if m["codigo"]]
    links = {str(r["vista_codigo"]): r for r in table_reads.in_batched_rows(client, T_LINKS, org_id, "vista_codigo", [i["codigo"] for i in itens])}
    abertos = _avisos_abertos(client, org_id) if not dry_run else set()
    novas_div = novos_amb = 0
    alvo: list[dict] = []
    for i in itens:
        if i["codigo"] in links and modo == "novos":
            rel["ja_vinculados"] += 1
        else:
            alvo.append(i)
    achados, pessoas = _candidatos(client, org_id, [i for i in alvo if i["codigo"] not in links]) if alvo else ({}, {})
    ligadas = {str(l["cliente_id"]) for l in links.values()}
    faltam = [c for c in ligadas if c not in pessoas]
    for r in table_reads.in_batched_rows(client, T_CLIENTES, org_id, "id", faltam, select=_SELECT):
        pessoas[str(r["id"])] = r
    for n, i in enumerate(alvo):
        if pausa_s and n:
            await asyncio.sleep(pausa_s)
        codigo = i["codigo"]
        existente = links.get(codigo)
        if existente is not None:
            ids = {str(existente["cliente_id"]): {existente.get("casado_por") or "telefone"}}
        else:
            ids = achados.get(codigo, {})
        if not ids:
            rel["sem_match"] += 1
            marcadas = [k.lower() for k, v in i["flags"].items() if v]
            for k in marcadas or ["sem_flag"]:
                rel["sem_match_por_flag"][k] += 1
            continue
        if len(ids) > 1:
            rel["ambiguos"] += 1
            if len(rel["amostra"]["ambiguos"]) < AMOSTRA:
                rel["amostra"]["ambiguos"].append({"vista_codigo": codigo, "candidatos": sorted(ids)})
            if not dry_run and _abrir(client, org_id, abertos, {"tipo": TIPO_AMBIGUO, "vista_codigo": codigo, "cliente_id": None, "candidatos": sorted(ids)}):
                novos_amb += 1
            continue
        (cid, vias), = ids.items()
        pessoa = pessoas.get(cid)
        if pessoa is None:
            rel["erros"].append(f"vista {codigo}: pessoa {cid} ligada não existe mais")
            continue
        fills, diverg = planejar(i, pessoa, identidade)
        rel["casados"] += 1
        rel["campos_preenchidos"] += len(fills)
        rel["divergencias"] += len(diverg)
        if len(rel["amostra"]["casamentos"]) < AMOSTRA:
            rel["amostra"]["casamentos"].append({"vista_codigo": codigo, "cliente_id": cid, "casado_por": _casado_por(vias)})
        if fills and len(rel["amostra"]["preenchimentos"]) < AMOSTRA:
            rel["amostra"]["preenchimentos"].append({"vista_codigo": codigo, "cliente_id": cid, "campos": sorted(fills)})
        if diverg and len(rel["amostra"]["divergencias"]) < AMOSTRA:
            rel["amostra"]["divergencias"].append({"vista_codigo": codigo, "cliente_id": cid, "campos": [d["campo"] for d in diverg]})  # names only, no values
        if dry_run:
            continue
        if fills:
            _aplicar(client, org_id, cid, fills)
        _gravar_link(client, org_id, existente, codigo, cid, _casado_por(vias), {k.lower(): v for k, v in i["flags"].items()}, sorted(fills))
        for d in diverg:
            if _abrir(client, org_id, abertos, {"tipo": TIPO_DIVERGENTE, "vista_codigo": codigo, "cliente_id": cid, **d}):
                novas_div += 1
    consumidos = len(linhas)
    fim = consumidos < limite or (rel["total_vista"] and offset + consumidos >= rel["total_vista"])
    rel["proximo_cursor"] = None if fim else str(offset + consumidos)
    rel["status"] = "ok" if not rel["erros"] else "ok_com_avisos"
    if not dry_run:
        if novas_div or novos_amb:
            _notificar(org_id, novas_div, novos_amb)
        resumo = {k: rel[k] for k in ("lote", "casados", "campos_preenchidos", "divergencias", "ambiguos", "sem_match", "ja_vinculados")}
        patch = {"ultimo_cursor": rel["proximo_cursor"], "ultima_execucao_em": _agora(), "ultimo_resumo": resumo, "updated_at": _agora()}
        if (_t(client, T_ESTADO).select("org_id").eq("org_id", str(org_id)).limit(1).execute().data or []):
            _t(client, T_ESTADO).update(patch).eq("org_id", str(org_id)).execute()
        else:
            _t(client, T_ESTADO).insert({"org_id": str(org_id), **patch}).execute()
    logger.info("vista clientes sync org=%s dry=%s: %s", org_id, dry_run, {k: v for k, v in rel.items() if isinstance(v, int)})
    return rel


def sincronizar_sync(client: Any, adapter: Any, org_id: UUID, **kw: Any) -> dict[str, Any]:
    from app.modules.leads.services.ad_lead_intake_service import rodar_coro_sync

    return rodar_coro_sync(sincronizar(client, adapter, org_id, **kw))


# ─── read side ───────────────────────────────────────────────────────────


def resumo(client: Any, org_id: UUID) -> dict[str, Any]:
    links = table_reads.paged_rows(client, T_LINKS, org_id)
    avisos = table_reads.paged_rows(client, T_AVISOS, org_id, eq_filters={"status": ST_PENDENTE})
    por_tipo: dict[str, int] = {}
    for a in avisos:
        por_tipo[a["tipo"]] = por_tipo.get(a["tipo"], 0) + 1
    e = estado_da_org(client, org_id)
    return {
        "vinculados": len(links), "avisos_pendentes": por_tipo,
        "config": {"vista_rps": e["vista_rps"], "importar_identidade": e["importar_identidade"]},
        "ultima_execucao_em": e["ultima_execucao_em"], "ultimo_cursor": e["ultimo_cursor"], "ultimo_resumo": e["ultimo_resumo"],
    }


def listar_avisos(client: Any, org_id: UUID, status: Optional[str] = ST_PENDENTE, tipo: Optional[str] = None) -> list[dict]:
    eq = {k: v for k, v in (("status", status), ("tipo", tipo)) if v}
    rows = table_reads.paged_rows(client, T_AVISOS, org_id, eq_filters=eq or None)
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return rows


def resolver_aviso(client: Any, org_id: UUID, aviso_id: Any, acao: str, user_id: Any = None, nota: Optional[str] = None) -> dict:
    if acao not in ACOES:
        raise ValueError(f"acao must be one of {ACOES}")
    rows = _t(client, T_AVISOS).select("*").eq("org_id", str(org_id)).eq("id", str(aviso_id)).limit(1).execute().data or []
    if not rows:
        raise LookupError(f"aviso {aviso_id} not found")
    patch = {"status": acao, "nota": nota, "resolvido_em": _agora(), "resolvido_por": str(user_id) if user_id else None}
    _t(client, T_AVISOS).update(patch).eq("org_id", str(org_id)).eq("id", str(aviso_id)).execute()
    return {**rows[0], **patch}


__all__ = ["CAMPOS_IDENTIDADE", "CAMPOS_IMPORTAVEIS", "VISTA_PROIBIDOS", "campos_vista", "listar_avisos", "mapear_cliente", "planejar", "resolver_aviso", "resumo", "salvar_config", "sincronizar", "sincronizar_sync"]
