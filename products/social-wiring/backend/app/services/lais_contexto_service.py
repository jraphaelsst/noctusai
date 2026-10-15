"""The per-turn `contexto` SW sends to agents (contract 2.1(a) / 2.2 / A2).

`montar` renders the whole object and its hash from a PROVIDER REGISTRY, so each wave appends
ONE entry and never edits this builder:

    PROVIDERS: list[tuple[str, Provider]]       # ordered; later entries win a key clash
    Provider = Callable[[ContextoCtx], dict]    # returns a PARTIAL contexto

Which keys a provider may return is closed: `conhecimento_md`, `perguntas`, `estado`
(merged key-by-key into the base `estado`), `ferramentas`, `acoes`. Default entries below:

  conhecimento   wave 1  -> {"conhecimento_md": str}   (here: "")
  perguntas      wave 2  -> {"perguntas": [..<=8]}     (here: [])
  estado         F       -> {"estado": {...}}          slots / operacao / interacao_id / encerrado
  ferramentas    F       -> the 4 read tools when the org has a tools token
  acoes          F       -> all actions incl. handoff (wave 3 may drop `qualificar_lead`)

A wave replaces its default by pointing the tuple at its own function (same name), e.g. wave 1:
`("conhecimento", lais_conhecimento_service.contexto_provider)`. `registrar_provider(nome, fn)`
does the same at runtime (tests / late binding): it REPLACES an entry of that name in place,
or appends a new one.

Hash: sha256 over the canonical JSON of the contexto minus `hash` and minus `agora` (the clock
would otherwise make every turn's hash unique and defeat "same knowledge => same hash").
Provider failures are contained: a provider that raises is logged at ERROR and contributes
nothing -- one broken wave must never stop Julia answering.
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
CONHECIMENTO_MAX = 60_000
CONTEXTO_MAX = 80_000
PERGUNTAS_MAX = 8

FERRAMENTAS_LAIS: tuple[str, ...] = ("buscar_imoveis", "detalhes_imovel", "horarios_visita", "consultar_empreendimento")
ACOES_LAIS: tuple[str, ...] = ("salvar_slots", "definir_operacao", "qualificar_lead", "pedido_visita", "captacao", "encerrar", "handoff")
#: `contexto.estado.operacao` accepts only these three (contract 2.1(a)); `atualizacao` is an action value only.
_OPERACOES_ESTADO = frozenset({"compra", "aluguel", "administracao"})

TOOLS_TOKEN_LABEL = "agents · ferramentas lais"
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
    #: Extra `contexto.estado` keys for THIS turn only (wave 4: `reengajamento`, `reescrever`, ...); merged
    #: key-by-key by `_prov_estado`, additive to the base estado.
    estado_extra: dict[str, Any] = field(default_factory=dict)


Provider = Callable[[ContextoCtx], dict[str, Any]]


# ── default providers (waves 1 / 2 replace the first two) ───────────────────
def _prov_conhecimento(_ctx: ContextoCtx) -> dict[str, Any]:
    return {"conhecimento_md": ""}


def _prov_perguntas(_ctx: ContextoCtx) -> dict[str, Any]:
    return {"perguntas": []}


def _prov_estado(ctx: ContextoCtx) -> dict[str, Any]:
    op = ctx.contato.get("operacao")
    return {"estado": {
        "slots": {str(k): str(v) for k, v in (ctx.contato.get("slots") or {}).items() if v is not None},
        "operacao": op if op in _OPERACOES_ESTADO else None,
        "interacao_id": str((ctx.interacao or {}).get("id") or ""),
        "encerrado": bool(ctx.contato.get("encerrado_at")),
        **ctx.estado_extra,
    }}


def _prov_ferramentas(ctx: ContextoCtx) -> dict[str, Any]:
    return {"ferramentas": list(FERRAMENTAS_LAIS) if ctx.ferramentas_habilitadas else []}


def _prov_acoes(_ctx: ContextoCtx) -> dict[str, Any]:
    return {"acoes": list(ACOES_LAIS)}


#: THE registry. One line per provider; waves swap their own line.
PROVIDERS: list[tuple[str, Provider]] = [
    ("conhecimento", _prov_conhecimento),
    ("perguntas", _prov_perguntas),
    ("estado", _prov_estado),
    ("ferramentas", _prov_ferramentas),
    ("acoes", _prov_acoes),
]


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
    `PUT /api/lais/agente/token`). It does not prove the push to agents landed -- agents omits a
    read tool it has no token for, so a stale `true` degrades to "tool absent", never to a leak."""
    now = agora or datetime.now(timezone.utc)
    try:
        rows = (
            client.table("api_tokens").select("scopes, issuer, expires_at, revoked_at")
            .eq("org_id", str(org_id)).eq("label", TOOLS_TOKEN_LABEL).execute().data or []
        )
    except Exception:
        logger.exception("lais: could not read the tools token state for org=%s", org_id)
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
    """Render contract 2.1(a). `ferramentas_habilitadas=None` asks the DB (`org_tem_token_ferramentas`).
    `providers=None` uses THE registry (`PROVIDERS`); pass an explicit sequence to render with another."""
    agora = agora or datetime.now(timezone.utc)
    if ferramentas_habilitadas is None:
        ferramentas_habilitadas = org_tem_token_ferramentas(client, org_id, agora=agora)
    ctx = ContextoCtx(client=client, org_id=org_id, contato=contato, interacao=interacao, agora=agora,
                      ferramentas_habilitadas=ferramentas_habilitadas,
                      estado_extra=dict(estado_extra or {}))

    out: dict[str, Any] = {"conhecimento_md": "", "perguntas": [], "estado": {}, "ferramentas": [], "acoes": []}
    for nome, fn in (PROVIDERS if providers is None else providers):
        try:
            parcial = fn(ctx) or {}
        except Exception:
            logger.exception("lais: contexto provider %r failed (org=%s) -- contributes nothing", nome, org_id)
            continue
        for chave, valor in parcial.items():
            if chave not in out:
                logger.error("lais: contexto provider %r returned unknown key %r -- ignored", nome, chave)
            elif chave == "estado" and isinstance(valor, dict):
                out["estado"] = {**out["estado"], **valor}
            else:
                out[chave] = valor

    if len(out["conhecimento_md"]) > CONHECIMENTO_MAX:
        logger.warning("lais: conhecimento_md %d chars > %d -- truncated (org=%s)",
                       len(out["conhecimento_md"]), CONHECIMENTO_MAX, org_id)
        out["conhecimento_md"] = out["conhecimento_md"][:CONHECIMENTO_MAX]
    if len(out["perguntas"]) > PERGUNTAS_MAX:
        logger.warning("lais: %d perguntas > %d -- trimmed (org=%s)", len(out["perguntas"]), PERGUNTAS_MAX, org_id)
        out["perguntas"] = out["perguntas"][:PERGUNTAS_MAX]

    out["agora"] = agora.isoformat()
    out["fuso"] = FUSO
    out["hash"] = calcular_hash(out)
    if len(json.dumps(out, ensure_ascii=False, default=str)) > CONTEXTO_MAX:
        # agents answers a bigger one with 422 `contexto_grande`; a turn without knowledge beats no turn.
        logger.error("lais: contexto > %d chars even after caps (org=%s) -- knowledge dropped", CONTEXTO_MAX, org_id)
        out["conhecimento_md"] = ""
        out["hash"] = calcular_hash(out)
    return out


__all__ = [
    "ACOES_LAIS", "ContextoCtx", "FERRAMENTAS_LAIS", "FUSO", "PROVIDERS", "Provider",
    "TOOLS_TOKEN_ISSUER", "TOOLS_TOKEN_LABEL", "TOOLS_TOKEN_SCOPE", "calcular_hash", "montar",
    "org_tem_token_ferramentas", "registrar_provider",
]
