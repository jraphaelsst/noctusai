"""In-house brokers refined from Vista (`/corretores/listar`) — owner 2026-11-09: "develop and refine our in-home brokers with Vista's data".

Syncs the Vista roster into SW's broker dimension (`lead_corretores`): matched by `vista_codigo`, else by the org's name-alias map, else
by the normalised name; an unmatched Vista broker is CREATED (never a guess at a merge). Fields kept from Vista: Codigo, Nome
(`vista_nome`; OUR `nome` -- the alias/analytics key -- is never overwritten), Nomecompleto, Email, Celular, CRECI, Equipe/CodigoEquipe,
Gerente, Agenciador, Corretor, Inativo/Datasaida, AtuacaoVenda/AtuacaoLocacao.

NEVER DELETE (same rule as the imóveis): a broker that is missing from Vista's roster or marked Inativo is MARKED (`vista_status`
`ausente|inativo`, `vista_ausente_em`) and noticed (`corretor_avisos`, tipo `corretor_sumiu_no_vista`, ONE in-app warning per run); `ativo`
(the owner's flag) is untouched. A broker that comes back keeps the notice open with a note -- never auto-closed. "Missing" is only
concluded from a COMPLETE roster (every page read) and behind a circuit breaker (`MAX_AUSENTES_PCT`): a partial or empty answer is a Vista
fault, not a hundred resignations.

KEY CAVEAT (CONTRACT ad-lead-intake § 6b): the 2026-10-26 live finding was that `/corretores/listar` answers only `Codigo` + `Nome` and ignores
`fields`; the key was re-granted 2026-11-09 but the richer fields are UNVERIFIED here (no live read). The sync requests them, falls back to the plain
roster when Vista rejects the field list (recorded in `campos`), and stores whatever it gets. There is no `/corretores/listarcampos` on this tenant.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations import rate_limit
from noctusai_lib.integrations.vista.client import VistaFieldNotAvailable

from app.modules.leads.seed_data import normalize_alias
from app.modules.leads.services import dimensions_service
from noctusai_lib.primitives.accents import fold_accents

logger = logging.getLogger(__name__)

T_AVISOS = "corretor_avisos"
TIPO_SUMIU = "corretor_sumiu_no_vista"
CAMPOS = [
    "Codigo", "Nome", "Nomecompleto", "Email", "Celular", "CRECI", "Equipe", "CodigoEquipe", "Gerente", "Agenciador", "Corretor",
    "Inativo", "Datasaida", "AtuacaoVenda", "AtuacaoLocacao",
]
PAGE_SIZE = 50
MAX_PAGINAS = 100
MAX_AUSENTES_PCT = 50.0
VISTA_RATE_BUCKET = "vista"
ST_PENDENTE = "pendente"
ACOES = ("resolvida", "ignorada")


def _t(client: Any, nome: str):
    return client.table(nome)


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get(item: dict, *chaves: str) -> Any:
    """Case/accent-insensitive read of a Vista key (`Nomecompleto` vs `NomeCompleto`)."""
    alvo = {re.sub(r"[^a-z0-9]", "", fold_accents(k).lower()): v for k, v in item.items()}
    for c in chaves:
        v = alvo.get(re.sub(r"[^a-z0-9]", "", c.lower()))
        if v not in (None, "", []):
            return v
    return None


def _texto(v: Any) -> Optional[str]:
    t = str(v).strip() if v is not None else ""
    return t or None


def _bool(v: Any) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    t = fold_accents(str(v)).strip().lower() if v is not None else ""
    if t in ("sim", "s", "true", "1", "yes"):
        return True
    if t in ("nao", "n", "false", "0", "no"):
        return False
    return None


def _data(v: Any) -> Optional[str]:
    t = _texto(v)
    if not t or t.startswith("0000"):
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(t[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return None


def mapear_item(item: dict) -> dict[str, Any]:
    """One Vista roster item -> the `lead_corretores` Vista columns (only what Vista sent; `None` = not sent)."""
    inativo = _bool(_get(item, "Inativo"))
    return {
        "vista_codigo": _texto(_get(item, "Codigo")),
        "vista_nome": _texto(_get(item, "Nome")),
        "nome_completo": _texto(_get(item, "Nomecompleto", "NomeCompleto")),
        "email": _texto(_get(item, "Email")),
        "celular": _texto(_get(item, "Celular")),
        "creci": _texto(_get(item, "CRECI")),
        "equipe": _texto(_get(item, "Equipe")),
        "codigo_equipe": _texto(_get(item, "CodigoEquipe")),
        "gerente": _bool(_get(item, "Gerente")),
        "agenciador": _bool(_get(item, "Agenciador")),
        "eh_corretor": _bool(_get(item, "Corretor")),
        "atuacao_venda": _bool(_get(item, "AtuacaoVenda")),
        "atuacao_locacao": _bool(_get(item, "AtuacaoLocacao")),
        "data_saida": _data(_get(item, "Datasaida", "DataSaida")),
        "vista_status": "inativo" if inativo else "ativo",
    }


async def _ler_roster(adapter: Any, relatorio: dict) -> Optional[list[dict]]:
    """Every page of the roster, or None when it could not be read COMPLETELY (the caller then marks nobody missing)."""
    campos: Optional[list[str]] = CAMPOS
    itens: list[dict] = []
    pagina = 1
    while pagina <= MAX_PAGINAS:
        await rate_limit.acquire_async(VISTA_RATE_BUCKET)
        relatorio["chamadas"] += 1
        try:
            rows, pag = await adapter.list_corretores(page=pagina, page_size=PAGE_SIZE, fields=campos)
        except VistaFieldNotAvailable as exc:
            if campos is None:
                relatorio["erros"].append(f"pagina {pagina}: {type(exc).__name__}")
                return None
            relatorio["campos"] = "basico"
            relatorio["erros"].append(f"campos rejeitados pelo Vista ({exc}); roster lido só com Codigo+Nome")
            campos = None
            continue
        except Exception as exc:
            relatorio["erros"].append(f"pagina {pagina}: {type(exc).__name__}: {exc}"[:200])
            logger.error("corretores vista sync: page %d failed", pagina, exc_info=True)
            return None
        itens.extend(rows)
        paginas = int((pag or {}).get("paginas") or 1)
        if pagina >= paginas or not rows:
            break
        pagina += 1
    else:
        relatorio["erros"].append("limite de páginas atingido")
        return None
    relatorio.setdefault("campos", "completo" if campos else "basico")
    return itens


def _indices(corretores: list[dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    por_codigo = {str(c["vista_codigo"]): c for c in corretores if c.get("vista_codigo")}
    por_nome = {str(c.get("nome_norm") or normalize_alias(c.get("nome") or "")): c for c in corretores}
    return por_codigo, por_nome


async def sincronizar(client: Any, adapter: Any, org_id: UUID, *, dry_run: bool = False) -> dict[str, Any]:
    """One roster sync for one org. Returns the report; never raises for a Vista outcome."""
    rel: dict[str, Any] = {
        "dry_run": dry_run, "chamadas": 0, "campos": None, "total_vista": 0, "criados": [], "atualizados": 0, "vinculados_por_nome": [],
        "inativos": [], "ausentes": [], "voltaram": [], "ausentes_recusados": False, "erros": [],
    }
    itens = await _ler_roster(adapter, rel)
    if itens is None:
        rel["status"] = "incompleto"  # nobody is marked missing from a partial read
        return rel
    rel["total_vista"] = len(itens)
    corretores = dimensions_service.list_corretores(client, org_id)
    por_codigo, por_nome = _indices(corretores)
    _, alias_map = dimensions_service.build_resolution_maps(client, org_id)
    from app.modules.leads.importer.resolvers import resolve_corretor

    vistos: set[str] = set()
    agora = _agora()
    for item in itens:
        campos = mapear_item(item)
        codigo = campos["vista_codigo"]
        if not codigo or not campos["vista_nome"]:
            rel["erros"].append(f"item sem Codigo/Nome ignorado: {sorted(item)[:4]}")
            continue
        vistos.add(codigo)
        alvo = por_codigo.get(codigo)
        if alvo is None:
            achado = resolve_corretor(campos["vista_nome"], alias_map)
            alvo = next((c for c in corretores if str(c["id"]) == achado), None) if achado else por_nome.get(normalize_alias(campos["vista_nome"]))
            if alvo is not None and alvo.get("vista_codigo") and str(alvo["vista_codigo"]) != codigo:
                rel["erros"].append(f"{campos['vista_nome']}: já ligado ao Vista {alvo['vista_codigo']}, Vista diz {codigo} — não reatribuído")
                alvo = None
            elif alvo is not None:
                rel["vinculados_por_nome"].append({"corretor_id": str(alvo["id"]), "vista_codigo": codigo, "nome": alvo.get("nome")})
        patch = {k: v for k, v in campos.items() if v is not None or k in ("vista_status",)}
        patch.update({"vista_sincronizado_em": agora, "vista_ausente_em": None})
        if alvo is None:
            rel["criados"].append(campos["vista_nome"])
            if not dry_run:
                novo = dimensions_service.create_corretor(client, org_id, nome=campos["vista_nome"], ativo=campos["vista_status"] != "inativo")
                _t(client, "lead_corretores").update(patch).eq("org_id", str(org_id)).eq("id", str(novo["id"])).execute()
                alvo = {**novo, **patch}
                corretores.append(alvo)
                por_codigo[codigo] = alvo
        else:
            voltou = alvo.get("vista_status") in ("ausente", "inativo") and campos["vista_status"] == "ativo"
            if voltou:
                rel["voltaram"].append(str(alvo["id"]))
            if campos["vista_status"] == "inativo":
                rel["inativos"].append(str(alvo["id"]))
            rel["atualizados"] += 1
            if not dry_run:
                _t(client, "lead_corretores").update(patch).eq("org_id", str(org_id)).eq("id", str(alvo["id"])).execute()
                alvo.update(patch)
                if voltou:
                    _anotar(client, org_id, alvo["id"], "voltou ao roster ativo do Vista; o aviso continua aberto para um humano decidir")

    # missing: only from a COMPLETE read, behind a circuit breaker
    conhecidos = [c for c in corretores if c.get("vista_codigo") and str(c["vista_codigo"]) not in vistos and c.get("vista_status") != "ausente"]
    base = [c for c in corretores if c.get("vista_codigo")]
    if conhecidos and len(itens) and len(conhecidos) * 100.0 / max(1, len(base)) > MAX_AUSENTES_PCT:
        rel["ausentes_recusados"] = True
        rel["erros"].append(f"{len(conhecidos)} de {len(base)} corretores ligados sumiram do roster: recusado (falha do Vista até prova em contrário)")
        conhecidos = []
    if not itens:
        conhecidos = []  # an empty roster is Vista going silent, not an agency with no brokers
        rel["erros"].append("roster vazio: ninguém marcado como ausente")
    sumiram = [c for c in conhecidos]
    rel["ausentes"] = [str(c["id"]) for c in sumiram]
    if not dry_run:
        for c in sumiram:
            _t(client, "lead_corretores").update({"vista_status": "ausente", "vista_ausente_em": agora}).eq("org_id", str(org_id)).eq("id", str(c["id"])).execute()
        _abrir_avisos(client, org_id, sumiram, [c for c in corretores if str(c["id"]) in set(rel["inativos"])])
    rel["status"] = "ok" if not rel["erros"] else "ok_com_avisos"
    logger.info("corretores vista sync org=%s: %s", org_id, {k: (len(v) if isinstance(v, list) else v) for k, v in rel.items() if k != "erros"})
    return rel


# ─── notices ─────────────────────────────────────────────────────────────


def _avisos_abertos(client: Any, org_id: UUID) -> dict[str, dict]:
    rows = _t(client, T_AVISOS).select("*").eq("org_id", str(org_id)).eq("tipo", TIPO_SUMIU).eq("status", ST_PENDENTE).execute().data or []
    return {str(r["corretor_id"]): r for r in rows}


def _anotar(client: Any, org_id: UUID, corretor_id: Any, texto: str) -> None:
    abertos = _avisos_abertos(client, org_id)
    aviso = abertos.get(str(corretor_id))
    if aviso is None:
        return
    notas = list(aviso.get("notas") or []) + [{"em": _agora(), "tipo": "voltou", "texto": texto}]
    _t(client, T_AVISOS).update({"notas": notas}).eq("org_id", str(org_id)).eq("id", str(aviso["id"])).execute()


def _abrir_avisos(client: Any, org_id: UUID, ausentes: list[dict], inativos: list[dict]) -> list[str]:
    """One open notice per broker (missing OR Inativo); ONE in-app warning for the run. Nothing is deleted or deactivated."""
    abertos = _avisos_abertos(client, org_id)
    novos: list[dict] = []
    for c, motivo in [(c, "sumiu do roster do Vista") for c in ausentes] + [(c, "marcado Inativo no Vista") for c in inativos]:
        if str(c["id"]) in abertos:
            continue
        _t(client, T_AVISOS).insert({
            "id": str(uuid4()), "org_id": str(org_id), "corretor_id": str(c["id"]), "vista_codigo": c.get("vista_codigo"), "tipo": TIPO_SUMIU,
            "status": ST_PENDENTE, "notas": [{"em": _agora(), "texto": f"{motivo}; cadastro mantido, nada apagado"}], "created_at": _agora(),
        }).execute()
        abertos[str(c["id"])] = {}
        novos.append(c)
    if novos:
        try:
            from noctusai_lib.domain.notifications import notify_org_admins

            from app.database import get_core_client

            nomes = ", ".join(str(c.get("nome")) for c in novos[:8]) + (f" e mais {len(novos) - 8}" if len(novos) > 8 else "")
            if notify_org_admins(
                get_core_client(), org_id=org_id, kind=TIPO_SUMIU, title=f"{len(novos)} corretor(es) sumiram/inativos no Vista",
                message=f"Cadastro mantido: {nomes}. Confira.", produto="social-wiring", link="/leads", entidade=None,
            ):
                for c in novos:
                    _t(client, T_AVISOS).update({"notificado_em": _agora()}).eq("org_id", str(org_id)).eq("corretor_id", str(c["id"])).eq("status", ST_PENDENTE).execute()
        except Exception:  # noqa: BLE001 -- the notice rows are the record
            logger.exception("corretores vista sync: in-app warning failed for org=%s", org_id)
    return [str(c["id"]) for c in novos]


def listar_avisos(client: Any, org_id: UUID, status: Optional[str] = ST_PENDENTE) -> list[dict]:
    q = _t(client, T_AVISOS).select("*").eq("org_id", str(org_id))
    if status:
        q = q.eq("status", status)
    rows = list(q.execute().data or [])
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return rows


def resolver_aviso(client: Any, org_id: UUID, aviso_id: Any, acao: str, user_id: Any = None, nota: Optional[str] = None) -> dict:
    if acao not in ACOES:
        raise ValueError(f"acao must be one of {ACOES}")
    rows = _t(client, T_AVISOS).select("*").eq("org_id", str(org_id)).eq("id", str(aviso_id)).limit(1).execute().data or []
    if not rows:
        raise LookupError(f"aviso {aviso_id} not found")
    notas = list(rows[0].get("notas") or []) + [{"em": _agora(), "tipo": acao, "por": str(user_id) if user_id else None, "texto": nota or acao}]
    patch = {"status": acao, "notas": notas, "resolvido_em": _agora(), "resolvido_por": str(user_id) if user_id else None}
    _t(client, T_AVISOS).update(patch).eq("org_id", str(org_id)).eq("id", str(aviso_id)).execute()
    return {**rows[0], **patch}


def sincronizar_sync(client: Any, adapter: Any, org_id: UUID, **kw: Any) -> dict[str, Any]:
    from app.modules.leads.services.ad_lead_intake_service import rodar_coro_sync

    return rodar_coro_sync(sincronizar(client, adapter, org_id, **kw))


__all__ = ["CAMPOS", "TIPO_SUMIU", "listar_avisos", "mapear_item", "resolver_aviso", "sincronizar", "sincronizar_sync"]
