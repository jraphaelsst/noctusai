"""Ad-lead intake -- a Meta lead-form lead -> its property, refreshed from Vista, linked both ways.

CONTRACT: products/social-wiring/projects/ad-lead-intake-CONTRACT.md. The pipeline, per lead:

    lead exists (ingest_meta_lead) -> the property CODE (leads.codigo_imovel | form REF)
      -> refresh that code from Vista (ALWAYS, even when we have the row: compare)     [ImovelSyncService.refresh_codigo]
      -> upsert `imoveis` (Vista columns) + `imovel_registry`; open the Vista-vs-ours divergences
      -> leads.imovel_ref_id := the registry id                       (lead  -> property)
      -> cliente interesse (+ card link) carrying lead_id AND meta_ads_lead_id (property -> lead, many-to-many)
      -> the property's Vista corretores recorded (`imovel_corretores`); the lead's corretor vs theirs: a pending
         `lead_corretor_divergencias` row + ONE in-app warning to the org admins
      -> leads.qualificacao_form := the form's budget / stage / region answers
      -> `lead_imovel_intakes`: the outcome, durable and retryable

GUARANTEES
  * IDEMPOTENT: every step is read-then-write or NULL-only; a re-run changes nothing and warns nobody twice.
  * NEVER BLOCKS THE LEAD: `tentar_intake` (the `ingest_meta_lead` seam) never raises. Vista down / not configured / any
    failure => a `pendente_retry|falhou` row with the error (no silent skip), re-driven by `retomar` or the backfill. The
    links that do not need Vista (registry, imovel_ref_id, interesse, qualification) are written regardless.
  * NO CROSS-PRODUCT WRITE: qualification lands on the SW lead (`qualificacao_form`); Julia's store in `agents` is not touched.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

from noctusai_lib.primitives.accents import fold_accents

from app.modules.imovel_hub import atendimento_imoveis_service, busca_service, interesses_service
from app.modules.leads.importer.resolvers import resolve_corretor
from app.modules.leads.services import dimensions_service, lead_notice, meta_form_aliases
from app.services import imoveis_service, vista_credenciais

logger = logging.getLogger(__name__)

T_INTAKES = "lead_imovel_intakes"
T_CORRETORES = "imovel_corretores"
T_DIVERGENCIAS = "lead_corretor_divergencias"

ST_OK = "ok"
ST_NAO_ENCONTRADO = "imovel_nao_encontrado"
ST_SEM_CODIGO = "sem_codigo"
ST_RETRY = "pendente_retry"
ST_FALHOU = "falhou"
#: Statuses `retomar` / the backfill re-drive.
ST_REPETIVEIS = (ST_RETRY, ST_FALHOU)
#: After this many failed attempts a `pendente_retry` becomes `falhou` (still retryable by hand; the backfill reports it).
MAX_TENTATIVAS_AUTO = 5

AdapterFactory = Callable[[Any], Any]


def _t(client: Any, nome: str):
    # `client` is the social_wiring-scoped / pinned admin client (same convention as meta_ingest_service).
    return client.table(nome)


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def rodar_coro_sync(coro: Any) -> Any:
    """Run a coroutine from sync code. No running loop => `asyncio.run`; inside a running loop (a threadpool handler is not,
    an `async def` route is) => a fresh loop on a worker thread, so it can never re-enter or block the caller's loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


# ─── reads ──────────────────────────────────────────────────────────────


def _um(client: Any, tabela: str, org_id: UUID, coluna: str, valor: Any) -> Optional[dict]:
    rows = _t(client, tabela).select("*").eq("org_id", str(org_id)).eq(coluna, str(valor)).limit(1).execute().data or []
    return rows[0] if rows else None


def _codigo_do_lead(lead: dict, meta: Optional[dict]) -> Optional[str]:
    """leads.codigo_imovel, else the Meta row's 180 column / REF answer. Canonical (upper/trim) or None."""
    from app.modules.leads.services.meta_ingest_service import codigo_do_meta_lead

    for bruto in (lead.get("codigo_imovel"), codigo_do_meta_lead(meta) if meta else None):
        if isinstance(bruto, str) and bruto.strip():
            return busca_service.canonical(bruto)
    return None


def _cliente_do_lead(client: Any, org_id: UUID, lead: dict, meta: Optional[dict]) -> Optional[str]:
    cards = atendimento_imoveis_service._atendimentos_do_lead(client, org_id, lead, meta)
    return next((str(a["cliente_id"]) for a in cards if a.get("cliente_id")), None)


# ─── the property's corretores ──────────────────────────────────────────


def _chave_corretor(c: dict) -> str:
    codigo = (c.get("codigo") or "").strip()
    return codigo or f"nome:{fold_accents(c.get('nome') or '').strip().lower()}"


def _resolver_corretor_sw(c: dict, por_vista: dict[str, dict], corretor_map: dict[str, str]) -> Optional[str]:
    """The SW `lead_corretores.id` of one Vista corretor: by Vista Codigo first (deterministic), else by NAME through the org's
    alias map (the same map the lead's corretor resolves through). `None` = unmatched; never a guess."""
    codigo = (c.get("codigo") or "").strip()
    if codigo and codigo in por_vista:
        return str(por_vista[codigo]["id"])
    return resolve_corretor(c.get("nome"), corretor_map)


def registrar_corretores_do_imovel(
    client: Any, org_id: UUID, codigo: str, corretores: list[dict], *, corretor_map: dict[str, str], corretores_sw: list[dict],
) -> list[dict]:
    """Record the property's Vista corretores as `imovel_corretores` rows (key = Vista Codigo). Read-then-write; a corretor no
    longer on the property flips `ativo=false` (never deleted). `principal` = the FIRST corretor Vista lists. Stamps
    `lead_corretores.vista_codigo` when a corretor resolved BY NAME has none and no other SW corretor claims that Codigo.
    Returns `(active rows with corretor_id resolved, stamps)`; every stamp is `{corretor_id, nome, vista_codigo, codigo_canonical}`
    so the intake `resultado` makes the self-learning auditable."""
    canonico = busca_service.canonical(codigo)
    por_vista = {str(r["vista_codigo"]): r for r in corretores_sw if r.get("vista_codigo")}
    existentes = {
        str(r["chave"]): r
        for r in (
            _t(client, T_CORRETORES).select("*").eq("org_id", str(org_id)).eq("codigo_canonical", canonico).execute().data or []
        )
    }
    agora = _agora()
    ativos: list[dict] = []
    stamps: list[dict] = []
    vistos: set[str] = set()
    for ordem, c in enumerate(corretores):
        chave = _chave_corretor(c)
        vistos.add(chave)
        corretor_id = _resolver_corretor_sw(c, por_vista, corretor_map)
        codigo_vista = (c.get("codigo") or "").strip() or None
        if corretor_id and codigo_vista and codigo_vista not in por_vista:
            alvo = next((r for r in corretores_sw if str(r["id"]) == corretor_id), None)
            if alvo is not None and not alvo.get("vista_codigo"):
                _t(client, "lead_corretores").update({"vista_codigo": codigo_vista}).eq("org_id", str(org_id)).eq("id", corretor_id).execute()
                alvo["vista_codigo"] = codigo_vista
                por_vista[codigo_vista] = alvo
                stamps.append({"corretor_id": corretor_id, "nome": alvo.get("nome"), "vista_codigo": codigo_vista, "codigo_canonical": canonico})
                logger.info("ad-lead intake: lead_corretores %s stamped vista_codigo=%s (name match, código %s)", corretor_id, codigo_vista, canonico)
        dados = {
            "vista_corretor_codigo": codigo_vista, "nome": c.get("nome"), "email": c.get("email"), "fone": c.get("fone"),
            "ordem": ordem, "principal": ordem == 0, "corretor_id": corretor_id, "ativo": True, "visto_em": agora,
        }
        if chave in existentes:
            _t(client, T_CORRETORES).update(dados).eq("org_id", str(org_id)).eq("id", str(existentes[chave]["id"])).execute()
        else:
            _t(client, T_CORRETORES).insert(
                {"id": str(uuid4()), "org_id": str(org_id), "codigo_canonical": canonico, "chave": chave, "created_at": agora, **dados}
            ).execute()
        ativos.append({"chave": chave, **dados})
    for chave, linha in existentes.items():
        if chave not in vistos and linha.get("ativo") is not False:
            _t(client, T_CORRETORES).update({"ativo": False}).eq("org_id", str(org_id)).eq("id", str(linha["id"])).execute()
    return ativos, stamps


def _corretores_do_espelho(client: Any, org_id: UUID, codigo: str) -> list[dict]:
    """The mirror's `imoveis.corretores` (JSONB, Vista-sourced) -- the fallback when Vista could not be reached now."""
    linha = _um(client, "imoveis", org_id, "codigo_norm", busca_service.canonical(codigo))
    return [c for c in ((linha or {}).get("corretores") or []) if isinstance(c, dict)]


TIPO_FORA = "fora_dos_corretores"
TIPO_NAO_PRINCIPAL = "nao_e_principal"
TIPO_SEM_CORRETOR = "lead_sem_corretor"
TIPOS_DIVERGENCIA = (TIPO_FORA, TIPO_NAO_PRINCIPAL, TIPO_SEM_CORRETOR)
_MOTIVO_FECHAMENTO = {
    TIPO_FORA: "auto: o corretor do lead passou a ser um dos corretores do imóvel",
    TIPO_NAO_PRINCIPAL: "auto: o corretor do lead passou a ser o corretor principal do imóvel",
    TIPO_SEM_CORRETOR: "auto: o lead passou a ter corretor",
}


def _tipos_ativos(lead_corretor: Any, ativos: list[dict]) -> list[str]:
    """Which of the three warnings hold NOW. `nao_e_principal` is deliberately NOT raised when `fora_dos_corretores` holds for the
    same pair: "not among the property's corretores" already implies "not the main one", so a second warning would say nothing new."""
    if not lead_corretor:
        return [TIPO_SEM_CORRETOR]
    if not ativos:
        return []  # the property has no corretor to compare against
    ids = {str(a["corretor_id"]) for a in ativos if a.get("corretor_id")}
    if str(lead_corretor) not in ids:
        return [TIPO_FORA]
    principal = next((a for a in ativos if a.get("principal")), ativos[0])
    if str(principal.get("corretor_id") or "") != str(lead_corretor):
        return [TIPO_NAO_PRINCIPAL]
    return []


def _checar_divergencia_corretor(
    client: Any, org_id: UUID, lead: dict, codigo: str, ativos: list[dict]
) -> dict[str, Any]:
    """Re-evaluate the three corretor warnings of (lead, código) and reconcile the stored rows: one OPEN row (+ ONE in-app warning)
    per tipo; a still-pending row whose condition no longer holds is auto-closed with its reason (e.g. a corretor assigned later
    closes `lead_sem_corretor`). A human-closed row (`resolvida`/`ignorada`) is never reopened or re-notified."""
    canonico = busca_service.canonical(codigo)
    lead_corretor = lead.get("corretor_id")
    ativos_tipos = _tipos_ativos(lead_corretor, ativos)
    existentes = {
        r["tipo"]: r
        for r in (_t(client, T_DIVERGENCIAS).select("*").eq("org_id", str(org_id)).eq("lead_id", str(lead["id"])).eq("codigo_canonical", canonico).execute().data or [])
    }
    fechadas: list[str] = []
    for tipo, linha in existentes.items():
        if tipo not in ativos_tipos and linha.get("status") == "pendente":
            _t(client, T_DIVERGENCIAS).update(
                {"status": "resolvida", "resolvido_em": _agora(), "nota": _MOTIVO_FECHAMENTO.get(tipo, "auto: sem divergência")}
            ).eq("org_id", str(org_id)).eq("id", str(linha["id"])).execute()
            fechadas.append(tipo)
    novas: list[str] = []
    nome_lead = lead.get("corretor_raw")
    if lead_corretor:
        sw = _um(client, "lead_corretores", org_id, "id", lead_corretor)
        nome_lead = (sw or {}).get("nome") or nome_lead
    snapshot = [
        {k: a.get(k) for k in ("vista_corretor_codigo", "nome", "email", "fone", "corretor_id", "principal")} | {"resolvido": bool(a.get("corretor_id"))}
        for a in ativos
    ]
    for tipo in ativos_tipos:
        if tipo in existentes:
            continue
        linha = {
            "id": str(uuid4()), "org_id": str(org_id), "lead_id": str(lead["id"]), "codigo_canonical": canonico, "tipo": tipo,
            "lead_corretor_id": str(lead_corretor) if lead_corretor else None, "lead_corretor_nome": nome_lead, "imovel_corretores": snapshot,
            "status": "pendente", "created_at": _agora(),
        }
        _t(client, T_DIVERGENCIAS).insert(linha).execute()
        avisados = lead_notice.avisar_corretor_divergente(
            org_id, lead_id=lead["id"], codigo=canonico, tipo=tipo, lead_corretor=nome_lead,
            imovel_corretores=[a.get("nome") for a in ativos if a.get("nome")],
            principal=next((a.get("nome") for a in ativos if a.get("principal")), None),
        )
        if avisados:
            _t(client, T_DIVERGENCIAS).update({"notificado_em": _agora()}).eq("org_id", str(org_id)).eq("id", linha["id"]).execute()
        novas.append(tipo)
    return {"divergencia": bool(ativos_tipos), "tipos": ativos_tipos, "novas": novas, "fechadas": fechadas}


# ─── the intake ledger ──────────────────────────────────────────────────


def _gravar_intake(
    client: Any, org_id: UUID, lead: dict, *, status: str, codigo: Optional[str], erro: Optional[str], resultado: dict,
) -> dict:
    atual = _um(client, T_INTAKES, org_id, "lead_id", lead["id"])
    tentativas = int((atual or {}).get("tentativas") or 0) + 1
    if status == ST_RETRY and tentativas >= MAX_TENTATIVAS_AUTO:
        status = ST_FALHOU
    linha = {
        "status": status, "codigo_canonical": codigo, "tentativas": tentativas, "ultimo_erro": erro, "resultado": resultado,
        "meta_ads_lead_id": lead.get("meta_lead_id"), "updated_at": _agora(),
        "concluido_em": _agora() if status in (ST_OK, ST_NAO_ENCONTRADO, ST_SEM_CODIGO) else None,
    }
    if atual:
        _t(client, T_INTAKES).update(linha).eq("org_id", str(org_id)).eq("id", str(atual["id"])).execute()
        return {**atual, **linha}
    nova = {"id": str(uuid4()), "org_id": str(org_id), "lead_id": str(lead["id"]), "created_at": _agora(), **linha}
    _t(client, T_INTAKES).insert(nova).execute()
    return nova


# ─── the public function ────────────────────────────────────────────────


async def intake_imovel_do_lead_async(
    client: Any,
    org_id: UUID,
    lead_id: Any,
    codigo: Optional[str] = None,
    *,
    adapter: Any = None,
    adapter_factory: Optional[AdapterFactory] = None,
    refresh_cache: Optional[dict[str, Any]] = None,
    sync_factory: Optional[Callable[..., Any]] = None,
) -> dict[str, Any]:
    """The intake (see the module docstring). `codigo` overrides the lead's own (else `leads.codigo_imovel` / form REF).

    `adapter`/`adapter_factory` (default `vista_credenciais.adapter_da_org`, the per-org DB credential) are the Vista seam;
    `refresh_cache` (`{CODIGO: RefreshCodigo}`) lets a batch fetch each code once. Returns the result summary (also persisted
    on `lead_imovel_intakes.resultado`): `status`, `codigo`, `vista` (desfecho), `imovel` (novo|atualizado|inalterado|nenhum),
    `mudancas`, `divergencias_vista`, `imovel_ref_id`, `interesse`, `corretores`, `divergencia_corretor`, `qualificacao`, `erros`.

    Raises only for a missing lead (a caller error). A Vista failure is a RESULT (`pendente_retry`), not an exception."""
    lead = _um(client, "leads", org_id, "id", lead_id)
    if lead is None:
        raise LookupError(f"lead {lead_id} not found in org {org_id}")
    meta = _um(client, "meta_ads_leads", org_id, "id", lead["meta_lead_id"]) if lead.get("meta_lead_id") else None
    canonico = busca_service.canonical(codigo) if codigo and codigo.strip() else _codigo_do_lead(lead, meta)
    resultado: dict[str, Any] = {"codigo": canonico, "erros": []}
    erros: list[str] = resultado["erros"]

    # Qualification needs no code and no Vista: always mapped.
    answers = (meta or {}).get("answers") if isinstance((meta or {}).get("answers"), dict) else None
    qualif = meta_form_aliases.mapear_qualificacao(answers)
    resultado["qualificacao"] = qualif or None

    if not canonico:
        if qualif and qualif != (lead.get("qualificacao_form") or None):
            _t(client, "leads").update({"qualificacao_form": qualif}).eq("org_id", str(org_id)).eq("id", str(lead["id"])).execute()
        _gravar_intake(client, org_id, lead, status=ST_SEM_CODIGO, codigo=None, erro=None, resultado=resultado)
        return {"status": ST_SEM_CODIGO, **resultado}

    # 1. identity: the registry row exists before anything links to it (idempotent; origem='lead').
    from app.modules.imovel_hub import dados_service

    dados_service.registrar_imovel(client, org_id, canonico, origem="lead")

    # 2. Vista refresh -> upsert imoveis + registry -> divergences.
    refresh = (refresh_cache or {}).get(canonico)
    status = ST_OK
    if refresh is None:
        try:
            vista = adapter if adapter is not None else (adapter_factory or vista_credenciais.adapter_da_org)(org_id)
            svc = (sync_factory or imoveis_service.build_sync_service)(client, vista)
            refresh = await svc.refresh_codigo(org_id, canonico)
            if refresh_cache is not None and refresh.desfecho != imoveis_service.DETALHE_FALHOU:
                refresh_cache[canonico] = refresh
        except Exception as exc:  # VistaConfigError (not configured) and anything unforeseen: durable + retryable
            status = ST_RETRY
            erros.append(f"vista: {type(exc).__name__}: {exc}"[:300])
            logger.warning("ad-lead intake: Vista unavailable for lead=%s código=%s (%s)", lead["id"], canonico, type(exc).__name__)
            refresh = None
    corretores_vista: Optional[list[dict]] = None
    if refresh is not None:
        resultado["vista"] = refresh.desfecho
        if refresh.desfecho == imoveis_service.DETALHE_FALHOU:
            status = ST_RETRY
            erros.append("vista: falha ao ler o imóvel (detalhes)")
        elif refresh.desfecho in (imoveis_service.DETALHE_SUMIU, imoveis_service.DETALHE_OCULTO):
            status = ST_NAO_ENCONTRADO
            erros.append(f"vista: imóvel {refresh.desfecho}")
        else:
            resultado["imovel"] = "atualizado" if refresh.mudancas else ("inalterado" if refresh.existia else "novo")
            resultado["mudancas"] = refresh.mudancas
            resultado["divergencias_vista"] = [
                {"campo": d.get("campo"), "vista": d.get("valor_proposto"), "nosso": d.get("valor_anterior")} for d in refresh.divergencias
            ]
            corretores_vista = [c.model_dump(mode="json") for c in (refresh.imovel.corretores if refresh.imovel else [])]
    else:
        resultado["vista"] = None

    # 3. lead -> property (leads.imovel_ref_id) + the structured qualification.
    reg = _um(client, "imovel_registry", org_id, "codigo_canonical", canonico)
    patch: dict[str, Any] = {}
    if reg and str(lead.get("imovel_ref_id") or "") != str(reg["id"]):
        patch["imovel_ref_id"] = str(reg["id"])
    if qualif and qualif != (lead.get("qualificacao_form") or None):
        patch["qualificacao_form"] = qualif
    if patch:
        _t(client, "leads").update(patch).eq("org_id", str(org_id)).eq("id", str(lead["id"])).execute()
        lead = {**lead, **patch}
    resultado["imovel_ref_id"] = str(reg["id"]) if reg else None

    # 4. property -> lead: card link + cliente interesse carrying lead_id AND meta_ads_lead_id.
    try:
        ligado = atendimento_imoveis_service.vincular_lead(
            client, org_id, lead_id=lead["id"], meta_ads_lead_id=lead.get("meta_lead_id"), codigo=canonico
        )
        resultado["interesse"] = {"cliente": bool(_cliente_do_lead(client, org_id, lead, meta)), "atendimentos": len(ligado["atendimentos"])}
        if not resultado["interesse"]["cliente"]:
            erros.append("interesse: lead sem cliente anexado ainda (o sweep de clientes completa)")
    except Exception as exc:
        status = ST_RETRY if status == ST_OK else status
        erros.append(f"vinculo: {type(exc).__name__}: {exc}"[:300])
        logger.error("ad-lead intake: linking lead=%s código=%s failed", lead["id"], canonico, exc_info=True)

    # 5. corretores of the property + the lead's divergence.
    try:
        fonte = "vista"
        if corretores_vista is None:
            corretores_vista, fonte = _corretores_do_espelho(client, org_id, canonico), "espelho"
        _, corretor_map = dimensions_service.build_resolution_maps(client, org_id)
        ativos, stamps = registrar_corretores_do_imovel(
            client, org_id, canonico, corretores_vista, corretor_map=corretor_map, corretores_sw=dimensions_service.list_corretores(client, org_id)
        )
        resultado["corretores"] = {"fonte": fonte, "total": len(ativos), "codigos": [a["vista_corretor_codigo"] for a in ativos]}
        resultado["vista_codigo_stamps"] = stamps or None
        resultado["divergencia_corretor"] = _checar_divergencia_corretor(client, org_id, lead, canonico, ativos)
    except Exception as exc:
        status = ST_RETRY if status == ST_OK else status
        erros.append(f"corretores: {type(exc).__name__}: {exc}"[:300])
        logger.error("ad-lead intake: corretores for lead=%s código=%s failed", lead["id"], canonico, exc_info=True)

    _gravar_intake(client, org_id, lead, status=status, codigo=canonico, erro="; ".join(erros) or None, resultado=resultado)
    return {"status": status, **resultado}


def intake_imovel_do_lead(client: Any, org_id: UUID, lead_id: Any, codigo: Optional[str] = None, **kw: Any) -> dict[str, Any]:
    """Sync wrapper of `intake_imovel_do_lead_async` (threadpool handlers, the webhook worker, the backfill)."""
    return rodar_coro_sync(intake_imovel_do_lead_async(client, org_id, lead_id, codigo, **kw))


def tentar_intake(client: Any, org_id: UUID, lead_id: Any, **kw: Any) -> dict[str, Any]:
    """THE seam `ingest_meta_lead` calls. NEVER raises: the lead is already committed. A failure is logged loudly and, as far as
    the DB allows, recorded as a retryable intake row -- never a silent skip."""
    try:
        return intake_imovel_do_lead(client, org_id, lead_id, **kw)
    except Exception as exc:
        logger.error("ad-lead intake FAILED for lead=%s org=%s -- recorded for retry", lead_id, org_id, exc_info=True)
        try:
            lead = _um(client, "leads", org_id, "id", lead_id) or {"id": lead_id}
            _gravar_intake(client, org_id, lead, status=ST_RETRY, codigo=None, erro=f"{type(exc).__name__}: {exc}"[:300], resultado={})
        except Exception:
            logger.error("ad-lead intake: could not record the failure of lead=%s either", lead_id, exc_info=True)
        return {"status": ST_RETRY, "erros": [f"{type(exc).__name__}: {exc}"[:300]]}


__all__ = [
    "intake_imovel_do_lead", "intake_imovel_do_lead_async", "tentar_intake", "registrar_corretores_do_imovel", "rodar_coro_sync", "TIPOS_DIVERGENCIA", "TIPO_FORA", "TIPO_NAO_PRINCIPAL", "TIPO_SEM_CORRETOR",
    "ST_OK", "ST_NAO_ENCONTRADO", "ST_SEM_CODIGO", "ST_RETRY", "ST_FALHOU", "ST_REPETIVEIS", "T_INTAKES", "T_CORRETORES", "T_DIVERGENCIAS",
]
