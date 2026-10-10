"""É o mesmo imóvel — LINK a manual imóvel to a Vista listing, reversibly
(migration 228, CONTRACT §8.7).

LINK, DON'T MOVE
----------------
`vincular` sets `imovel_registry.vinculado_a` on the MANUAL registry row (it
points at the Vista registry row's id), flips the pair to `confirmado` and
writes an audit event. No FK in the 12+ tables referencing the manual código is
rewritten, so nothing is half-moved and `desvincular` is exact: it clears
`vinculado_a` and returns the pair to `pendente`.

Both actions are ADMIN-ONLY. The gate lives at the route (`require_org_admin_role`,
the trusted `noctus_users` predicate `DELETE /api/clientes/{id}` uses); this
module takes the already-authorised `actor_id` for the audit row.

PROPERTY-LEVEL LEGAL DATA FOLLOWS THE LINK
------------------------------------------
Matrícula / CRI / owners are property-level facts. They are reconciled by
`vinculo_legal` (built separately, `app/modules/imovel_hub/vinculo_legal.py`),
called through a LAZY import so this module works — and says so — while that
module is absent:

    reconciliar(client, org_id, vinculo)   after a link
    limpar(client, org_id, vinculo)        BEFORE an unlink

A missing module, or an exception from either function, is reported in the
response (`legal: {"status": "erro", "mensagem": ...}`) and logged; it NEVER
undoes the link (and never blocks an unlink). The `legal` outcome is also
recorded on the audit event.

`legal` is a DI port: tests (and any caller) pass an object exposing
`reconciliar`/`limpar`; the default loads `vinculo_legal` lazily.
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import AppException, NotFoundError

from app.modules.imovel_hub import busca_service
from app.modules.imovel_hub import dados_service as dados_svc
from app.modules.imovel_hub import duplicatas_service as dup_svc
from app.services import table_reads

logger = logging.getLogger(__name__)

REGISTRY_TABLE = "imovel_registry"
EVENTOS_TABLE = "imovel_vinculo_eventos"
MODULO_LEGAL = "app.modules.imovel_hub.vinculo_legal"
MENSAGEM_MODULO_AUSENTE = "módulo indisponível"

#: Sentinel: "load `vinculo_legal` lazily".
CARREGAR = object()


@dataclass(frozen=True)
class Vinculo:
    manual_codigo: str  # canonical
    vista_codigo: str  # canonical

    def as_dict(self) -> dict:
        return {"manual_codigo": self.manual_codigo, "vista_codigo": self.vista_codigo}


def carregar_vinculo_legal(nome_modulo: str = MODULO_LEGAL) -> Optional[Any]:
    """The `vinculo_legal` module, or `None` when it is not there.

    Only the module's OWN absence maps to `None`: an ImportError raised from
    INSIDE it (a broken dependency) propagates, so it is never mistaken for
    "not built yet".
    """
    try:
        return importlib.import_module(nome_modulo)
    except ModuleNotFoundError as exc:
        if exc.name == nome_modulo or (exc.name and nome_modulo.startswith(f"{exc.name}.")):
            return None
        raise


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _registro(client: Any, org_id: UUID, *, codigo: Optional[str] = None, id_: Any = None) -> Optional[dict]:
    q = _t(client, REGISTRY_TABLE).select("*").eq("org_id", str(org_id))
    q = q.eq("codigo_canonical", codigo) if codigo is not None else q.eq("id", str(id_))
    rows = q.limit(1).execute().data or []
    return rows[0] if rows else None


def resolver_vinculo(client: Any, org_id: UUID, codigo: str) -> Optional[Vinculo]:
    """The link `codigo` takes part in, from EITHER side, or `None`.

    A registry row with `vinculado_a` set is the manual side (its target is the
    Vista row); otherwise a row whose id is some other row's `vinculado_a` is the
    Vista side.
    """
    canonico = busca_service.canonical(codigo)
    row = _registro(client, org_id, codigo=canonico)
    if row is None:
        return None
    if row.get("vinculado_a"):
        alvo = _registro(client, org_id, id_=row["vinculado_a"])
        if alvo is None or not alvo.get("codigo_canonical"):
            return None
        return Vinculo(manual_codigo=canonico, vista_codigo=str(alvo["codigo_canonical"]))
    if not row.get("id"):
        # a row without an id (legacy fixtures) cannot be the target of a link
        return None
    manuais = (
        _t(client, REGISTRY_TABLE).select("codigo_canonical, vinculado_a")
        .eq("org_id", str(org_id)).eq("vinculado_a", str(row["id"])).limit(1).execute()
    ).data or []
    if manuais:
        return Vinculo(manual_codigo=str(manuais[0]["codigo_canonical"]), vista_codigo=canonico)
    return None


# ─── legal port ───────────────────────────────────────────────────────────


def _chamar_legal(legal: Any, funcao: str, client: Any, org_id: UUID, vinculo: Vinculo) -> dict:
    """Call `legal.<funcao>(client, org_id, vinculo)` and report — never raise."""
    if legal is CARREGAR:
        try:
            legal = carregar_vinculo_legal()
        except Exception as exc:  # noqa: BLE001 — reported, never swallowed
            logger.exception("vinculo: loading vinculo_legal failed")
            return {"status": "erro", "mensagem": f"{type(exc).__name__}: {exc}"}
    if legal is None:
        logger.error(
            "vinculo: %s skipped for %s <-> %s: vinculo_legal module unavailable",
            funcao, vinculo.manual_codigo, vinculo.vista_codigo,
        )
        return {"status": "erro", "mensagem": MENSAGEM_MODULO_AUSENTE}
    try:
        resultado = getattr(legal, funcao)(client, org_id, vinculo)
    except Exception as exc:  # noqa: BLE001 — reported, never undoes the link
        logger.exception(
            "vinculo: vinculo_legal.%s failed for %s <-> %s",
            funcao, vinculo.manual_codigo, vinculo.vista_codigo,
        )
        return {"status": "erro", "mensagem": f"{type(exc).__name__}: {exc}"}
    if isinstance(resultado, dict):
        return {"status": "ok", **resultado}
    if isinstance(resultado, int) and not isinstance(resultado, bool):
        return {"status": "ok", "removidos": resultado}
    return {"status": "ok"}


def _publico(legal: dict) -> dict:
    """The `legal` outcome as the wire/audit shape: `novos_conflitos` (the full
    conflict rows, for the caller to announce) is internal."""
    return {k: v for k, v in legal.items() if k != "novos_conflitos"}


# ─── audit ────────────────────────────────────────────────────────────────


def _auditar(
    client: Any, org_id: UUID, vinculo: Vinculo, acao: str,
    duplicata_id: Any, actor_id: Optional[UUID],
) -> Optional[str]:
    """Append the event; returns its id. A failure is LOUD (the link/unlink
    already happened — the caller reports it, see `_sem_auditoria`)."""
    rows = _t(client, EVENTOS_TABLE).insert({
        "org_id": str(org_id),
        "codigo_manual": vinculo.manual_codigo,
        "codigo_vista": vinculo.vista_codigo,
        "acao": acao,
        "duplicata_id": str(duplicata_id) if duplicata_id else None,
        "ator": str(actor_id) if actor_id else None,
    }).execute().data or []
    return str(rows[0]["id"]) if rows and rows[0].get("id") else None


def _sem_auditoria(vinculo: Vinculo, acao: str, exc: Exception) -> AppException:
    logger.error(
        "vinculo: %s %s <-> %s done but its audit event failed: %s",
        acao, vinculo.manual_codigo, vinculo.vista_codigo, exc,
    )
    return AppException(
        code="vinculo_auditoria_falhou",
        message=(
            f"A operação '{acao}' foi aplicada, mas o registro de auditoria falhou. "
            "Avise o suporte antes de repetir."
        ),
        status_code=500,
        details={"manual_codigo": vinculo.manual_codigo, "vista_codigo": vinculo.vista_codigo},
    )


def _registrar_legal_no_evento(client: Any, org_id: UUID, evento_id: Optional[str], legal: dict) -> None:
    if not evento_id:
        return
    try:
        _t(client, EVENTOS_TABLE).update({"legal": legal}).eq("org_id", str(org_id)).eq(
            "id", evento_id
        ).execute()
    except Exception:  # noqa: BLE001 — logged; the response still carries `legal`
        logger.exception("vinculo: could not record the legal outcome on audit event %s", evento_id)


# ─── link / unlink ────────────────────────────────────────────────────────


def vincular(
    client: Any, org_id: UUID, duplicata_id: Any, actor_id: Optional[UUID],
    *, legal: Any = CARREGAR,
) -> dict:
    """`POST /duplicatas/{id}/vincular` — "É o mesmo imóvel".

    `409 duplicata_ja_resolvida` unless the pair is `pendente`;
    `409 imovel_ja_vinculado` / `vista_ja_vinculada` when either side already
    takes part in a link. Returns `{duplicata, vinculo, legal, novos_conflitos}` (the route strips
    `novos_conflitos` after announcing them).
    """
    linha = dup_svc.obter_linha(client, org_id, duplicata_id)
    if linha["status"] != "pendente":
        raise dup_svc.ja_resolvida(duplicata_id, linha["status"])

    manual = _registro(client, org_id, codigo=str(linha["codigo_manual"]))
    vista = _registro(client, org_id, codigo=str(linha["codigo_vista"]))
    if manual is None or vista is None:
        raise NotFoundError("Imóvel", f"{linha['codigo_manual']}/{linha['codigo_vista']}")
    if manual.get("origem_descoberta") != "manual":
        raise AppException(
            code="imovel_nao_manual",
            message=f"O imóvel {manual['codigo_canonical']} não é um cadastro manual.",
            status_code=409,
        )
    if manual.get("vinculado_a"):
        raise AppException(
            code="imovel_ja_vinculado",
            message=f"O imóvel {manual['codigo_canonical']} já está vinculado a outro imóvel.",
            status_code=409,
            details={"codigo": str(manual["codigo_canonical"])},
        )
    ocupada = (
        _t(client, REGISTRY_TABLE).select("codigo_canonical")
        .eq("org_id", str(org_id)).eq("vinculado_a", str(vista["id"])).limit(1).execute()
    ).data or []
    if ocupada:
        raise AppException(
            code="vista_ja_vinculada",
            message=f"O imóvel {vista['codigo_canonical']} já tem um cadastro manual vinculado.",
            status_code=409,
            details={"codigo": str(vista["codigo_canonical"])},
        )

    vinculo = Vinculo(
        manual_codigo=str(manual["codigo_canonical"]), vista_codigo=str(vista["codigo_canonical"])
    )
    try:
        _t(client, REGISTRY_TABLE).update({"vinculado_a": str(vista["id"])}).eq(
            "org_id", str(org_id)
        ).eq("id", str(manual["id"])).execute()
    except Exception as exc:  # noqa: BLE001 — a lost race on the partial UNIQUE
        if table_reads.is_unique_violation(exc):
            raise AppException(
                code="vista_ja_vinculada",
                message=f"O imóvel {vinculo.vista_codigo} já tem um cadastro manual vinculado.",
                status_code=409,
            ) from exc
        raise

    agora = dados_svc._now()
    _t(client, dup_svc.TABLE).update({
        "status": "confirmado",
        "resolvido_por": str(actor_id) if actor_id else None,
        "resolvido_em": agora, "atualizado_em": agora,
    }).eq("org_id", str(org_id)).eq("id", str(duplicata_id)).execute()

    try:
        evento_id = _auditar(client, org_id, vinculo, "vincular", duplicata_id, actor_id)
    except Exception as exc:  # noqa: BLE001 — loud, see `_sem_auditoria`
        raise _sem_auditoria(vinculo, "vincular", exc) from exc

    resultado_legal = _chamar_legal(legal, "reconciliar", client, org_id, vinculo)
    _registrar_legal_no_evento(client, org_id, evento_id, _publico(resultado_legal))
    return {
        "duplicata": dup_svc.obter_par(client, org_id, duplicata_id),
        "vinculo": vinculo.as_dict(),
        "legal": _publico(resultado_legal),
        # internal: the conflict rows `reconciliar` opened, for the ROUTE to
        # announce (`campos_extraidos_service.notificar`, async) and strip.
        "novos_conflitos": list(resultado_legal.get("novos_conflitos") or []),
    }


def desvincular(
    client: Any, org_id: UUID, codigo_manual: str, actor_id: Optional[UUID],
    *, legal: Any = CARREGAR,
) -> dict:
    """`POST /{codigo}/desvincular` — undo a link exactly.

    `codigo_manual` may be either side's código (the link is resolved from it).
    `limpar` runs FIRST; then `vinculado_a` is cleared, the pair returns to
    `pendente` (resolvido_* cleared) and the audit event is written.
    `404 imovel_nao_vinculado` when the código takes part in no link.
    Returns `{vinculo, duplicata, legal}` (`vinculo` = what was removed).
    """
    vinculo = resolver_vinculo(client, org_id, codigo_manual)
    if vinculo is None:
        raise AppException(
            code="imovel_nao_vinculado",
            message=f"O imóvel {busca_service.canonical(codigo_manual)} não está vinculado.",
            status_code=404,
            details={"codigo": busca_service.canonical(codigo_manual)},
        )

    resultado_legal = _chamar_legal(legal, "limpar", client, org_id, vinculo)

    _t(client, REGISTRY_TABLE).update({"vinculado_a": None}).eq("org_id", str(org_id)).eq(
        "codigo_canonical", vinculo.manual_codigo
    ).execute()

    pares = (
        _t(client, dup_svc.TABLE).select("id")
        .eq("org_id", str(org_id)).eq("codigo_manual", vinculo.manual_codigo)
        .eq("codigo_vista", vinculo.vista_codigo).eq("status", "confirmado").limit(1).execute()
    ).data or []
    duplicata_id = pares[0]["id"] if pares else None
    if duplicata_id:
        _t(client, dup_svc.TABLE).update({
            "status": "pendente", "resolvido_por": None, "resolvido_em": None,
            "atualizado_em": dados_svc._now(),
        }).eq("org_id", str(org_id)).eq("id", str(duplicata_id)).execute()

    try:
        evento_id = _auditar(client, org_id, vinculo, "desvincular", duplicata_id, actor_id)
    except Exception as exc:  # noqa: BLE001 — loud, see `_sem_auditoria`
        raise _sem_auditoria(vinculo, "desvincular", exc) from exc
    _registrar_legal_no_evento(client, org_id, evento_id, resultado_legal)

    return {
        "vinculo": vinculo.as_dict(),
        "duplicata": dup_svc.obter_par(client, org_id, duplicata_id) if duplicata_id else None,
        "legal": _publico(resultado_legal),
    }


__all__ = [
    "CARREGAR", "MENSAGEM_MODULO_AUSENTE", "Vinculo", "carregar_vinculo_legal",
    "desvincular", "resolver_vinculo", "vincular",
]
