"""The per-turn `contexto` SW sends to agents (julia-v2: agents' `ChannelContexto`, `channels.v2.json`).

Julia is hosted in agents and everything that makes her Julia (prompt, knowledge, questions, tool list, action list,
qualification) lives THERE. The `contexto` SW sends is DATA ONLY -- facts about the lead and the line that agents cannot
know -- and its shape is the closed, typed schema agents owns (`ContextoEstado`, `extra="forbid"`):

    {"hash", "agora", "fuso",
     "estado": {"interacao_id", "encerrado", "atendente_nome"?, "origem"?: {"canal_origem", "codigo_imovel_campanha"},
                "credito"?: {"ativo", "consentimento"},
                # a re-engagement turn only (gatilho="reengajamento"):
                "reengajamento"?: minutos|horas|regua, "reescrever"?, "texto_base"?, "tentativa"?},
     "capacidades": {"ferramentas_sw"}}

Removed in v2 (never sent again): `conhecimento_md` (org knowledge lives in agents, Q1), `perguntas` (the qualification
standard lives in agents), `ferramentas` / `acoes` (agents decides its tools from the agent version), `estado.slots` /
`estado.operacao` (the qualification state is agents', SW only mirrors it). The re-engagement flavour and the attendant's name
(which agents used to forbid, so SW stripped them) are fields now: DATA agents renders with its own DB texts. No string in
this module is prompt text.

`montar` renders the object and its hash from a PROVIDER REGISTRY, so a wave appends ONE entry and never edits this builder:

    PROVIDERS: list[tuple[str, Provider]]       # ordered; later entries win a key clash
    Provider = Callable[[ContextoCtx], dict]    # returns a PARTIAL contexto

Which keys a provider may return is closed: `estado` (merged key-by-key into the base) and `capacidades`.
`registrar_provider(nome, fn)` REPLACES an entry of that name in place, or appends a new one;
`registrar_estado_extra(fn)` adds keys on top of `estado` (credit, the attendant) without touching the list. A key outside
agents' `ContextoEstado` is stripped with an ERROR (agents would answer 422 and the lead would get no reply).

Hash: sha256 over the canonical JSON of the contexto minus `hash` and minus `agora` (the clock would otherwise make
every turn's hash unique). Provider failures are contained: a provider that raises is logged at ERROR and contributes
nothing -- one broken wave must never stop the lead path.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Sequence
from uuid import UUID

logger = logging.getLogger(__name__)

FUSO = "America/Sao_Paulo"
CONTEXTO_MAX = 80_000

#: These key sets mirror agents' committed `products/agents/backend/contracts/channels.v2.json` (`ChannelContexto` /
#: `ContextoEstado`); `tests/services/test_agents_contract_v2.py` makes that file the arbiter and always runs.
#: The closed key set of the wire `contexto` that SW sends (the schema also tolerates the retired v1 keys; SW sends none).
CONTEXTO_CHAVES: frozenset[str] = frozenset({"hash", "agora", "fuso", "estado", "capacidades"})
#: The `contexto.estado` keys SW sends. agents' schema ALSO accepts v1 `slots` / `operacao` (ignored): SW sends neither.
ESTADO_CHAVES_AGENTS: frozenset[str] = frozenset({
    "interacao_id", "encerrado", "atendente_nome", "credito", "origem",
    "reengajamento", "reescrever", "texto_base", "tentativa",
})
ORIGEM_CHAVES: frozenset[str] = frozenset({"canal_origem", "codigo_imovel_campanha"})
#: Keys SW computes for its OWN bookkeeping and that must never reach agents (`regua_id` goes to the outbound gate).
ESTADO_CHAVES_SW_ONLY: frozenset[str] = frozenset({"regua_id"})

TOOLS_TOKEN_LABEL = "agents · ferramentas julia"
#: NOC-REMEDIATE[rename-lais-tools-scope]: the scope string is stored in agents' token table and checked by agents'
#: `channel_tools_token_router`; it keeps its pre-rename spelling until both products rename it together (one-release dual accept).
TOOLS_TOKEN_SCOPE = "social-wiring:lais-tools"
TOOLS_TOKEN_ISSUER = "agents"


@dataclass(frozen=True)
class ContextoCtx:
    client: Any  # schema-scoped service-role client
    org_id: UUID | str
    contato: dict[str, Any]
    interacao: Optional[dict[str, Any]] = None
    agora: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ferramentas_habilitadas: bool = False
    #: Extra `contexto.estado` keys for THIS turn only (the re-engagement flavour: `reengajamento`, `reescrever`,
    #: `texto_base`, `tentativa`); merged key-by-key by `_prov_estado`, additive to the base estado.
    estado_extra: dict[str, Any] = field(default_factory=dict)


Provider = Callable[[ContextoCtx], dict[str, Any]]


# ── default providers ───────────────────────────────────────────────────────
def _prov_estado(ctx: ContextoCtx) -> dict[str, Any]:
    """The facts SW owns about the lead and the line. Data only: ids, flags, source labels."""
    estado: dict[str, Any] = {
        "interacao_id": str((ctx.interacao or {}).get("id") or ""),
        "encerrado": bool(ctx.contato.get("encerrado_at")),
    }
    origem = {
        "canal_origem": ctx.contato.get("origem_slug") or None,
        "codigo_imovel_campanha": ctx.contato.get("codigo_imovel_campanha") or None,
    }
    if any(origem.values()):
        estado["origem"] = origem
    return {"estado": {**estado, **ctx.estado_extra}}


def _prov_capacidades(ctx: ContextoCtx) -> dict[str, Any]:
    """What SW can do FOR the agent right now (the tools token is the only capability SW owns)."""
    return {"capacidades": {"ferramentas_sw": bool(ctx.ferramentas_habilitadas)}}


#: THE registry. One line per provider; waves swap their own line.
PROVIDERS: list[tuple[str, Provider]] = [
    ("estado", _prov_estado),
    ("capacidades", _prov_capacidades),
]


#: Extra `contexto.estado` keys a wave adds on top of the base: `fn(ctx) -> dict` merged key-by-key (the credit analysis
#: state, the attendant's name). It does NOT touch the ordered PROVIDERS list.
ESTADO_EXTRAS: list[Callable[[ContextoCtx], dict[str, Any]]] = []


def registrar_estado_extra(fn: Callable[[ContextoCtx], dict[str, Any]]) -> None:
    """Idempotent: binding the same function twice keeps one entry."""
    if fn not in ESTADO_EXTRAS:
        ESTADO_EXTRAS.append(fn)


def registrar_provider(nome: str, fn: Provider, *, registro: Optional[list[tuple[str, Provider]]] = None) -> None:
    """Replace the provider called `nome` in place (keeps its position), or append it.

    `registro` defaults to THE module registry; pass your own list (e.g. `list(PROVIDERS)`) to
    build an isolated registry and hand it to `montar(..., providers=...)` -- no module patching."""
    alvo = PROVIDERS if registro is None else registro
    for i, (n, _f) in enumerate(alvo):
        if n == nome:
            alvo[i] = (nome, fn)
            return
    alvo.append((nome, fn))


# ── the tools token ─────────────────────────────────────────────────────────
def org_tem_token_ferramentas(client: Any, org_id: UUID | str, *, agora: Optional[datetime] = None) -> bool:
    """True when the org has an ACTIVE agents-issued `social-wiring:lais-tools` token (minted by
    `PUT /api/julia/agente/token`). It does not prove the push to agents landed -- agents omits a
    read tool it has no token for, so a stale `true` degrades to "tool absent", never to a leak."""
    now = agora or datetime.now(timezone.utc)
    try:
        rows = (
            client.table("api_tokens").select("scopes, issuer, expires_at, revoked_at")
            .eq("org_id", str(org_id)).eq("label", TOOLS_TOKEN_LABEL).execute().data or []
        )
    except Exception as exc:
        logger.error("julia: could not read the tools token state for org=%s (%s)", org_id, type(exc).__name__)
        return False
    for r in rows:
        if r.get("revoked_at") or r.get("issuer") != TOOLS_TOKEN_ISSUER:
            continue
        if TOOLS_TOKEN_SCOPE not in (r.get("scopes") or []):
            continue
        exp = r.get("expires_at")
        if exp:
            try:
                dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
            except ValueError:
                continue
            if (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)) <= now:
                continue
        return True
    return False


# ── build ───────────────────────────────────────────────────────────────────
def calcular_hash(contexto: dict[str, Any]) -> str:
    base = {k: v for k, v in contexto.items() if k not in ("hash", "agora")}
    canon = json.dumps(base, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _estado_para_agents(estado: dict[str, Any], org_id: UUID | str) -> dict[str, Any]:
    """Keep only the keys agents' closed `ContextoEstado` accepts; a stray key is a bug (agents would answer 422).
    Empty optional values are dropped (an absent key and a null mean the same to agents, and the hash stays stable)."""
    fora = sorted(set(estado) - ESTADO_CHAVES_AGENTS)
    desconhecidas = [k for k in fora if k not in ESTADO_CHAVES_SW_ONLY]
    if desconhecidas:
        logger.error("julia: contexto.estado keys %s are not in agents' contract -- stripped, else agents answers 422 "
                     "(org=%s)", desconhecidas, org_id)
    if fora:
        logger.info("julia: contexto.estado keys %s kept SW-side, not sent to agents (org=%s)", fora, org_id)
    obrigatorias = ("interacao_id", "encerrado")
    return {k: v for k, v in estado.items() if k in ESTADO_CHAVES_AGENTS and (k in obrigatorias or v not in (None, "", {}, False))}


def montar(
    client: Any,
    org_id: UUID | str,
    contato: dict[str, Any],
    *,
    interacao: Optional[dict[str, Any]] = None,
    agora: Optional[datetime] = None,
    ferramentas_habilitadas: Optional[bool] = None,
    providers: Optional[Sequence[tuple[str, Provider]]] = None,
    estado_extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Render the wire `contexto`. `ferramentas_habilitadas=None` asks the DB (`org_tem_token_ferramentas`).
    `providers=None` uses THE registry (`PROVIDERS`); pass an explicit sequence to render with another."""
    agora = agora or datetime.now(timezone.utc)
    if ferramentas_habilitadas is None:
        ferramentas_habilitadas = org_tem_token_ferramentas(client, org_id, agora=agora)
    ctx = ContextoCtx(client=client, org_id=org_id, contato=contato, interacao=interacao, agora=agora,
                      ferramentas_habilitadas=ferramentas_habilitadas, estado_extra=dict(estado_extra or {}))

    out: dict[str, Any] = {"estado": {}, "capacidades": {}}
    for nome, fn in (PROVIDERS if providers is None else providers):
        try:
            parcial = fn(ctx) or {}
        except Exception as exc:
            logger.error("julia: contexto provider %r failed (org=%s) -- contributes nothing (%s)", nome, org_id, type(exc).__name__)
            continue
        for chave, valor in parcial.items():
            if chave not in out:
                logger.error("julia: contexto provider %r returned unknown key %r -- ignored", nome, chave)
            elif isinstance(valor, dict):
                out[chave] = {**out[chave], **valor}
            else:
                logger.error("julia: contexto provider %r returned a non-object %r -- ignored", nome, chave)

    for fn_estado in tuple(ESTADO_EXTRAS):
        try:
            out["estado"] = {**out["estado"], **(fn_estado(ctx) or {})}
        except Exception as exc:
            logger.error("julia: contexto estado extra %r failed (org=%s) -- contributes nothing (%s)", getattr(fn_estado, "__name__", "?"), org_id, type(exc).__name__)
    out["estado"] = _estado_para_agents(out["estado"], org_id)

    out["agora"] = agora.isoformat()
    out["fuso"] = FUSO
    out["hash"] = calcular_hash(out)
    if len(json.dumps(out, ensure_ascii=False, default=str)) > CONTEXTO_MAX:
        # agents answers a bigger one with 422 `contexto_grande`; data-only contexto is tiny, so this is a bug.
        logger.error("julia: contexto > %d chars (org=%s) -- a provider is returning prose or a blob", CONTEXTO_MAX, org_id)
    return out


__all__ = [
    "CONTEXTO_CHAVES", "ContextoCtx", "ESTADO_CHAVES_AGENTS", "ESTADO_CHAVES_SW_ONLY", "ESTADO_EXTRAS", "FUSO", "ORIGEM_CHAVES",
    "PROVIDERS", "Provider", "TOOLS_TOKEN_ISSUER", "TOOLS_TOKEN_LABEL", "TOOLS_TOKEN_SCOPE", "calcular_hash", "montar",
    "org_tem_token_ferramentas", "registrar_estado_extra", "registrar_provider",
]
