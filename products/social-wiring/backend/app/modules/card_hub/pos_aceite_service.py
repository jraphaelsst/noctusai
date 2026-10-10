"""Post-aceite automation: certidões of every vendedor + the imóvel's matrícula.

CONTRACT `projects/sw-lead-to-contract/CONTRACT.md` §7 (owner 2026-10-09):
right after a proposta is accepted, certify the sellers and read the matrícula,
with no human click. `disparar` is §4.4's step 6; its failure never undoes the
accept and it is idempotent (re-runnable from the Aceitar response).

WHO IS A VENDEDOR (§7.1, SUPERSEDES the 2026-10-05 "anuente spouse gets no
certidões" rule)
-----------------------------------------------------------------------
The vendedor parties of the atendimento (PF and PJ) + the registered owners of
the imóvel (`imovel_proprietarios`) + EVERY one of their cônjuges
(`clientes.conjuge_cliente_id`, co-owner or anuente, registered now or later)
+ the `EMP n` companies the Certidões tab already derives (not re-derived here:
`certidoes_partes_service.todas_as_partes`). A cônjuge usually has NO
`atendimento_partes` row, so they are certified through
`solicitar_emissao_da_parte`, the write half of the same service.

IDEMPOTENCY / STALENESS
-----------------------
Per party and AUTOMATIC tipo, an emission is skipped when a non-stale
`sucesso` certidão exists (staleness = the contract gate's own predicate,
`certidoes_partes_service.montar_celula(...).stale_para_contrato`, i.e.
`politica.certidao_max_dias` — never a literal) or a consulta for that tipo is
still in flight. Only the missing/stale tipos are requested, in ONE consulta
per party. Manual tipos (TJSP, Serasa, ...) are reported in `manuais`, never
emitted.

SCHEDULING
----------
`solicitar_emissao_da_parte` only writes the consulta; something must run
`processar_consulta`. An `Agendador` carries that: a router passes
`agendador_em_background(background_tasks, ...)`; with none given (the
late-spouse hook, a re-run outside a request) `agendador_padrao()` runs the
SAME coroutines in a daemon thread.

NO MATRÍCULA EMISSION: the repo has no ARISP/ONR/InfoSimples matrícula
integration (owner question Q5), so an absent matrícula is reported
`faltando/matricula_ausente`, never emitted.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable, Literal, Optional
from uuid import UUID

from noctusai_lib.integrations.documents.cpf import only_digits
from noctusai_lib.primitives.exceptions import AppException, NotFoundError
from pydantic import BaseModel, Field

from app.modules.card_hub import certidoes_partes_service as partes_svc
from app.modules.certidoes import service as certidoes_svc
from app.modules.certidoes.registry import (
    CERTIDOES_CONFIG,
    MANUAL_CONFIG_BY_TIPO,
    TJSP_TIPO,
)
from app.services import table_reads

logger = logging.getLogger(__name__)

ATENDIMENTOS = "atendimentos"
PARTES = "atendimento_partes"
CLIENTES = "clientes"
EMPRESAS = "empresas"
NEGOCIACAO = "atendimento_negociacao"
PROPRIETARIOS = "imovel_proprietarios"
PROPOSTAS = "atendimento_propostas"
EXTRACOES = "matricula_extracoes"

STATUS_PROPOSTA_ACEITA = "aceita"
_EM_ANDAMENTO = partes_svc._EM_ANDAMENTO
#: A pending/processing resultado older than this was orphaned (the same window
#: `certidoes.service.recover_stale_processando` uses) — it no longer counts as
#: "in flight", or one dead job would block the tipo forever.
JANELA_EM_VOO_SEGUNDOS = certidoes_svc.STALE_PROCESSANDO_SECONDS

CertidaoStatus = Literal["emitindo", "ja_valida", "pulada", "bloqueado", "erro"]
MatriculaStatus = Literal["extraindo", "ok", "faltando", "erro"]


# ─── response (CONTRACT §7.3) ───────────────────────────────────────────────


class CertidaoPosAceite(BaseModel):
    parte_nome: str
    kind: Literal["pessoa", "empresa"]
    alvo_id: str
    consulta_id: Optional[str] = None
    status: CertidaoStatus
    motivo: Optional[str] = None
    tipos: list[str] = Field(default_factory=list)
    #: Manual-upload tipos with no valid certidão on file (a checklist, never
    #: an emission). An addition to the §7.3 shape.
    manuais: list[str] = Field(default_factory=list)


class MatriculaPosAceite(BaseModel):
    status: MatriculaStatus
    documento_id: Optional[str] = None
    motivo: Optional[str] = None


class PosAceite(BaseModel):
    certidoes: list[CertidaoPosAceite] = Field(default_factory=list)
    matricula: MatriculaPosAceite


# ─── scheduling ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Agendador:
    """What runs after the rows are written. `consulta(consulta_id)` runs the
    billed InfoSimples fan-out; `extracao(extracao_id, storage_path)` the
    matrícula transcription."""

    consulta: Callable[[str], None]
    extracao: Callable[[str, str], None]


def agendador_em_background(
    background_tasks: Any, client: Any, storage: Any, org_id: Any
) -> Agendador:
    """Schedule on the request's `BackgroundTasks` — exactly what the Certidões
    and Matrículas routers do."""
    from app.modules.certidoes.deps import get_certidoes_service
    from app.modules.matriculas import service as matriculas_svc
    from app.modules.matriculas.deps import get_notification_service, get_transcriber_factory

    certidoes = get_certidoes_service()

    def _consulta(consulta_id: str) -> None:
        background_tasks.add_task(certidoes.processar_consulta, consulta_id, client, storage)

    def _extracao(extracao_id: str, storage_path: str) -> None:
        background_tasks.add_task(
            matriculas_svc.processar_extracao_de_documento,
            extracao_id, storage_path, str(org_id), client, storage,
            transcriber_factory=get_transcriber_factory(),
            notificador=get_notification_service(),
        )

    return Agendador(consulta=_consulta, extracao=_extracao)


def _em_thread(nome: str, coro_fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    def _alvo() -> None:
        try:
            asyncio.run(coro_fn(*args, **kwargs))
        except Exception:  # noqa: BLE001 - detached; the sweeps recover the row, never silent
            logger.error("pos-aceite: %s falhou", nome, exc_info=True)

    threading.Thread(target=_alvo, name=f"pos-aceite-{nome}", daemon=True).start()


def agendador_padrao(client: Any, org_id: Any) -> Agendador:
    """Run the pipelines in daemon threads with the process-wide dependencies —
    for callers with no request (the late-spouse hook)."""
    from app.modules.card_hub.deps import get_storage_backend
    from app.modules.certidoes.deps import get_certidoes_service
    from app.modules.matriculas import service as matriculas_svc
    from app.modules.matriculas.deps import get_notification_service, get_transcriber_factory

    certidoes = get_certidoes_service()
    storage = get_storage_backend()

    def _consulta(consulta_id: str) -> None:
        _em_thread("consulta", certidoes.processar_consulta, consulta_id, client, storage)

    def _extracao(extracao_id: str, storage_path: str) -> None:
        _em_thread(
            "extracao", matriculas_svc.processar_extracao_de_documento,
            extracao_id, storage_path, str(org_id), client, storage,
            transcriber_factory=get_transcriber_factory(),
            notificador=get_notification_service(),
        )

    return Agendador(consulta=_consulta, extracao=_extracao)


# Process-wide seams for callers with no request (the late-spouse hook), filled
# by `configurar` — same module-slot pattern as the other `configure_*` DI
# seams. Unset ⇒ the real thing (`agendador_padrao` / the InfoSimples key check).
_agendador_factory: Optional[Callable[[Any, Any], Agendador]] = None
_check_credentials_padrao: Optional[Callable[[str], list[str]]] = None


def configurar(
    *,
    agendador_factory: Optional[Callable[[Any, Any], Agendador]] = None,
    check_credentials: Optional[Callable[[str], list[str]]] = None,
) -> None:
    """Install (or, with no args, clear) the scheduling / credentials seams used
    when `disparar` is called without explicit ones. Tests install a recording
    `Agendador` here — the external boundary — and clear it afterwards."""
    global _agendador_factory, _check_credentials_padrao
    _agendador_factory = agendador_factory
    _check_credentials_padrao = check_credentials


# ─── helpers ────────────────────────────────────────────────────────────────


def _t(client: Any, table: str):
    return table_reads.table(client, table)


def _uuid(v: Any) -> UUID:
    return v if isinstance(v, UUID) else UUID(str(v))


def _ator_id(actor: Any) -> Optional[str]:
    raw = getattr(actor, "id", actor)
    return str(raw) if raw else None


def _atendimento(client: Any, org_id: UUID, atendimento_id: str) -> dict:
    rows = (
        _t(client, ATENDIMENTOS)
        .select("id, cliente_id")
        .eq("org_id", str(org_id))
        .eq("id", str(atendimento_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError("atendimentos", str(atendimento_id))
    return rows[0]


def _codigo_do_imovel(client: Any, org_id: UUID, atendimento_id: str) -> Optional[str]:
    rows = (
        _t(client, NEGOCIACAO)
        .select("imovel_codigo")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id))
        .limit(1)
        .execute()
    ).data or []
    return (rows[0].get("imovel_codigo") if rows else None) or None


_propostas_ausente_logado = False


def _proposta_aceita(client: Any, org_id: UUID, atendimento_id: str) -> Optional[dict]:
    """The atendimento's accepted proposta, or `None` — also `None` (logged
    ONCE) while `atendimento_propostas` (CONTRACT §4.1, built in parallel) does
    not exist in this database yet."""
    global _propostas_ausente_logado
    try:
        rows = (
            _t(client, PROPOSTAS)
            .select("*")
            .eq("org_id", str(org_id))
            .eq("atendimento_id", str(atendimento_id))
            .eq("status", STATUS_PROPOSTA_ACEITA)
            .limit(1)
            .execute()
        ).data or []
    except Exception as exc:  # noqa: BLE001 - table not migrated yet; logged once, not silent
        if not _propostas_ausente_logado:
            _propostas_ausente_logado = True
            logger.warning("pos-aceite: %s indisponível (%s) — hook inativo", PROPOSTAS, exc)
        return None
    return rows[0] if rows else None


def _parse_ts(valor: Any) -> Optional[datetime]:
    if not valor:
        return None
    try:
        ts = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


# ─── 7.1 · who is a vendedor ────────────────────────────────────────────────


def _parte_pf(row: dict) -> dict:
    return {
        "parte_id": None, "titular": False, "lado": "vendedor", "papel": "conjuge",
        "tipo_pessoa": "PF", "cliente_id": str(row["id"]), "empresa_id": None,
        "nome": row.get("nome_oficial") or row.get("nome_completo") or row.get("nome") or "",
        "documento": only_digits(row.get("cpf") or "") or None,
        "grupo": "vendedor", "rotulo": "",
    }


def _parte_pj(row: dict) -> dict:
    return {
        "parte_id": None, "titular": False, "lado": "vendedor", "papel": "proprietario",
        "tipo_pessoa": "PJ", "cliente_id": None, "empresa_id": str(row["id"]),
        "nome": row.get("razao_social") or row.get("nome_fantasia") or "",
        "documento": only_digits(row.get("cnpj") or "") or None,
        "grupo": "vendedor", "rotulo": "",
    }


def _clientes(client: Any, org_id: UUID, ids: list[str]) -> list[dict]:
    return table_reads.in_batched_rows(
        client, CLIENTES, org_id, "id", ids,
        select="id, nome, nome_completo, nome_oficial, cpf, conjuge_cliente_id",
    )


def vendedores(client: Any, org_id: UUID, atendimento: dict, codigo: Optional[str]) -> list[dict]:
    """Every party to certify (see the module docstring), deduped, in order."""
    org = _uuid(org_id)
    todas = partes_svc.todas_as_partes(
        client, org, _uuid(atendimento["cliente_id"]), str(atendimento["id"])
    )
    out: list[dict] = [p for p in todas if p.get("grupo") == partes_svc.GRUPO_VENDEDOR]
    vistos = {partes_svc._chave(p) for p in out}

    if codigo:
        from app.modules.imovel_hub import vinculo_legal

        # The proprietários belong to the PROPERTY: union through the link.
        donos = [
            d
            for fonte in vinculo_legal.codigos_leitura(client, org, codigo)
            for d in table_reads.paged_rows(
                client, PROPRIETARIOS, org,
                eq_filters={"codigo": fonte}, refine=lambda q: q.is_("deleted_at", "null"),
            )
        ]
        ids_pf = [str(d["cliente_id"]) for d in donos if d.get("cliente_id")]
        ids_pj = [str(d["empresa_id"]) for d in donos if d.get("empresa_id")]
        for row in _clientes(client, org, [i for i in ids_pf if f"c:{i}" not in vistos]):
            out.append(_parte_pf({**row}) | {"papel": "proprietario"})
            vistos.add(f"c:{row['id']}")
        for row in table_reads.in_batched_rows(
            client, EMPRESAS, org, "id", [i for i in ids_pj if f"e:{i}" not in vistos],
            select="id, razao_social, nome_fantasia, cnpj",
        ):
            out.append(_parte_pj(row))
            vistos.add(f"e:{row['id']}")

    # Every PF seller's cônjuge — co-owner or anuente, with or without a party row.
    pf_ids = [str(p["cliente_id"]) for p in out if p.get("cliente_id")]
    conjuge_ids: list[str] = []
    for row in _clientes(client, org, pf_ids):
        cj = row.get("conjuge_cliente_id")
        if cj and f"c:{cj}" not in vistos and str(cj) not in conjuge_ids:
            conjuge_ids.append(str(cj))
    for row in _clientes(client, org, conjuge_ids):
        out.append(_parte_pf(row))
        vistos.add(f"c:{row['id']}")
    return out


# ─── 7.1 · what is missing per party ────────────────────────────────────────


def _tipos_automaticos() -> list[str]:
    return [c["tipo"] for c in CERTIDOES_CONFIG if c["tipo"] != TJSP_TIPO]


def _em_voo(resultado: dict, agora: datetime) -> bool:
    if resultado.get("status") not in _EM_ANDAMENTO:
        return False
    criado = _parse_ts(resultado.get("created_at"))
    return criado is None or (agora - criado).total_seconds() <= JANELA_EM_VOO_SEGUNDOS


def _plano(parte: dict, resultados: list[dict], hoje: date, agora: datetime) -> dict:
    """`{faltando, em_voo, validas, consulta_em_voo, manuais}` for one party."""
    por_tipo, _ = partes_svc.indexar_vencedores(resultados)
    limite = partes_svc.max_dias()
    faltando, em_voo, validas = [], [], []
    consulta_em_voo: Optional[str] = None
    for tipo in _tipos_automaticos():
        vencedor = por_tipo.get(tipo)
        celula = partes_svc.montar_celula(tipo, vencedor, hoje, limite)
        if vencedor and vencedor.get("status") == "sucesso" and not celula["stale_para_contrato"]:
            validas.append(tipo)
            continue
        voo = next(
            (r for r in resultados if r.get("tipo") == tipo and _em_voo(r, agora)), None
        )
        if voo is not None:
            em_voo.append(tipo)
            consulta_em_voo = consulta_em_voo or voo.get("consulta_id")
        else:
            faltando.append(tipo)
    manuais = []
    for tipo in dict.fromkeys([TJSP_TIPO, *MANUAL_CONFIG_BY_TIPO]):
        if not partes_svc._aplicavel({"tipo": tipo}, parte):
            continue
        vencedor = por_tipo.get(tipo)
        celula = partes_svc.montar_celula(tipo, vencedor, hoje, limite)
        if not (vencedor and vencedor.get("status") == "sucesso" and not celula["stale_para_contrato"]):
            manuais.append(tipo)
    return {
        "faltando": faltando, "em_voo": em_voo, "validas": validas,
        "consulta_em_voo": consulta_em_voo, "manuais": manuais,
    }


def _item(parte: dict, **campos: Any) -> CertidaoPosAceite:
    return CertidaoPosAceite(
        parte_nome=parte.get("nome") or "", kind=partes_svc._kind(parte),
        alvo_id=str(parte.get("cliente_id") or parte.get("empresa_id")), **campos,
    )


def _certidoes(
    client: Any,
    org_id: UUID,
    atendimento: dict,
    codigo: Optional[str],
    ator: Optional[str],
    agendador: Agendador,
    check_credentials: Callable[[str], list[str]],
    hoje: date,
) -> list[CertidaoPosAceite]:
    partes = vendedores(client, org_id, atendimento, codigo)
    if not partes:
        return []
    resultados = certidoes_svc.certidoes_por_alvos(
        client, org_id,
        cliente_ids=[p["cliente_id"] for p in partes if p.get("cliente_id")],
        empresa_ids=[p["empresa_id"] for p in partes if p.get("empresa_id")],
    )
    agora = datetime.now(timezone.utc)
    planos = [(p, _plano(p, resultados.get(partes_svc._chave(p), []), hoje, agora)) for p in partes]

    precisa_emitir = any(plano["faltando"] for _, plano in planos)
    bloqueio: Optional[str] = None
    if precisa_emitir:
        if not ator:
            bloqueio = "ator_ausente"
        elif check_credentials(str(org_id)):
            bloqueio = "credenciais"

    saida: list[CertidaoPosAceite] = []
    for parte, plano in planos:
        manuais = plano["manuais"]
        if not plano["faltando"]:
            if plano["em_voo"]:
                saida.append(_item(
                    parte, status="pulada", motivo="consulta_em_andamento",
                    consulta_id=plano["consulta_em_voo"], tipos=plano["em_voo"], manuais=manuais,
                ))
            else:
                saida.append(_item(
                    parte, status="ja_valida", tipos=plano["validas"], manuais=manuais,
                ))
            continue
        if bloqueio:
            saida.append(_item(
                parte, status="bloqueado", motivo=bloqueio, tipos=plano["faltando"], manuais=manuais,
            ))
            continue
        try:
            emitido = partes_svc.solicitar_emissao_da_parte(
                client, org_id, parte, tipos=plano["faltando"], user_id=ator,
                check_credentials=check_credentials,
            )
        except AppException as exc:
            saida.append(_item(
                parte, status="erro", motivo=exc.message, tipos=plano["faltando"], manuais=manuais,
            ))
            continue
        agendador.consulta(emitido["consulta_id"])
        saida.append(_item(
            parte, status="emitindo", consulta_id=emitido["consulta_id"],
            tipos=plano["faltando"], manuais=manuais,
        ))
    return saida


# ─── 7.2 · matrícula ────────────────────────────────────────────────────────


def _matricula(
    client: Any,
    org_id: UUID,
    codigo: Optional[str],
    ator: Optional[str],
    agendador: Agendador,
) -> MatriculaPosAceite:
    from app.modules.imovel_hub import documentos_service as docs_svc
    from app.modules.imovel_hub import vinculo_legal
    from app.modules.matriculas import autopiloto_service
    from app.modules.matriculas import estrutura_service as estrutura
    from app.modules.matriculas.service import check_required_credentials

    if not codigo:
        return MatriculaPosAceite(status="faltando", motivo="imovel_ausente")

    # The matrícula describes the PROPERTY: a Vista código linked to a manual
    # imóvel also sees the manual one's documents/transcriptions.
    docs = [
        d for d in docs_svc._linhas_do_imovel(client, org_id, codigo)
        if d.get("tipo_documento") == "matricula"
    ]
    extracoes = [
        e
        for fonte in vinculo_legal.codigos_leitura(client, org_id, codigo)
        for e in table_reads.paged_rows(
            client, EXTRACOES, org_id, eq_filters={"codigo": fonte},
        )
    ]
    vivas = [e for e in extracoes if not e.get("substituida_por")]
    vivas.sort(key=lambda e: str(e.get("created_at") or ""), reverse=True)
    pdfs = [d for d in docs if d.get("mime_type") == estrutura.MIME_TRANSCREVIVEL]  # newest first

    def _do_documento(doc: dict) -> list[dict]:
        return [e for e in vivas if str(e.get("imovel_documento_id")) == str(doc["id"])]

    def _aplicar(extracao: dict, documento_id: Optional[str]) -> MatriculaPosAceite:
        # Also syncs the antigos proprietários (their certidões), once the
        # matrícula is on the card — never duplicated here.
        resultado = autopiloto_service.aplicar_autopiloto(client, org_id, extracao["id"])
        if resultado.get("status") == "ok":
            return MatriculaPosAceite(status="ok", documento_id=documento_id)
        return MatriculaPosAceite(
            status="erro", documento_id=documento_id,
            motivo=f"autopiloto:{resultado.get('status')}",
        )

    if pdfs:
        doc = pdfs[0]
        atuais = [e for e in _do_documento(doc) if e.get("status") != "erro"]
        if atuais:
            extracao = atuais[0]
            if extracao.get("status") == estrutura.STATUS_CONCLUIDA:
                return _aplicar(extracao, str(doc["id"]))
            return MatriculaPosAceite(status="extraindo", documento_id=str(doc["id"]))
        # No usable extraction of the newest matrícula document: read it.
        if check_required_credentials(str(org_id)):
            return MatriculaPosAceite(status="erro", documento_id=str(doc["id"]), motivo="credenciais")
        nova = estrutura.criar_extracao_de_documento(
            client, org_id, codigo=doc.get("codigo") or codigo,
            imovel_documento_id=_uuid(doc["id"]), usuario_id=ator,
        )
        agendador.extracao(nova["id"], nova["storage_path"])
        return MatriculaPosAceite(status="extraindo", documento_id=str(doc["id"]))

    # No PDF on file — a matrícula pasted by hand (or an image the number reader
    # already handles) may still have a concluded extraction for this imóvel.
    concluida = next((e for e in vivas if e.get("status") == estrutura.STATUS_CONCLUIDA), None)
    if concluida is not None:
        return _aplicar(concluida, None)
    if any(e.get("status") in ("pendente", "processando") for e in vivas):
        return MatriculaPosAceite(status="extraindo")
    if docs:
        return MatriculaPosAceite(
            status="faltando", documento_id=str(docs[0]["id"]), motivo="matricula_nao_pdf",
        )
    # NOC-REMEDIATE[pos-aceite-pendencia-imovel]: no per-imóvel checklist exists
    # (`cliente_checklist_extras` is per-cliente), so the "Certidão de matrícula
    # atualizada" pendência is this reported `faltando` — 2026-10-09.
    return MatriculaPosAceite(status="faltando", motivo="matricula_ausente")


# ─── entry points ───────────────────────────────────────────────────────────


def disparar(
    client: Any,
    org_id: Any,
    atendimento_id: Any,
    actor: Any,
    *,
    agendador: Optional[Agendador] = None,
    check_credentials: Optional[Callable[[str], list[str]]] = None,
    hoje: Optional[date] = None,
) -> PosAceite:
    """CONTRACT §7: certify every vendedor + read the matrícula. Idempotent.

    Each step fails alone: an unexpected error in one is reported in its own
    slot (logged at ERROR) and never hides the other. `actor` is the acting
    user (or id); `None` falls back to whoever accepted the proposta."""
    org = _uuid(org_id)
    atendimento = _atendimento(client, org, str(atendimento_id))
    codigo = _codigo_do_imovel(client, org, str(atendimento_id))
    ator = _ator_id(actor)
    if ator is None:
        aceita = _proposta_aceita(client, org, str(atendimento_id)) or {}
        ator = str(aceita["aceita_por"]) if aceita.get("aceita_por") else None
    agendador = agendador or (_agendador_factory or agendador_padrao)(client, org)
    if check_credentials is None:
        check_credentials = _check_credentials_padrao
    if check_credentials is None:
        from app.modules.certidoes.deps import get_certidoes_service

        check_credentials = get_certidoes_service().check_required_credentials

    try:
        matricula = _matricula(client, org, codigo, ator, agendador)
    except Exception as exc:  # noqa: BLE001 - reported in its slot, never hides the certidões
        logger.error("pos-aceite %s: matrícula falhou: %s", atendimento_id, exc, exc_info=True)
        matricula = MatriculaPosAceite(status="erro", motivo=str(exc))
    try:
        certidoes = _certidoes(
            client, org, atendimento, codigo, ator, agendador, check_credentials,
            hoje or date.today(),
        )
    except Exception as exc:  # noqa: BLE001 - reported in its slot
        logger.error("pos-aceite %s: certidões falhou: %s", atendimento_id, exc, exc_info=True)
        certidoes = [CertidaoPosAceite(
            parte_nome="vendedores", kind="pessoa", alvo_id=str(atendimento["cliente_id"]),
            status="erro", motivo=str(exc),
        )]
    return PosAceite(certidoes=certidoes, matricula=matricula)


def _atendimentos_dos_conjuges(client: Any, org_id: UUID, cliente_ids: list[str]) -> list[str]:
    """Atendimentos where one of these people is a seller: a vendedor parte, or
    an owner of the imóvel the deal negotiates."""
    ids = {
        str(r["atendimento_id"])
        for r in table_reads.in_batched_rows(
            client, PARTES, org_id, "cliente_id", cliente_ids, select="atendimento_id, lado",
        )
        if r.get("lado") == "vendedor"
    }
    codigos = {
        str(r["codigo"])
        for r in table_reads.in_batched_rows(
            client, PROPRIETARIOS, org_id, "cliente_id", cliente_ids, select="codigo, deleted_at",
        )
        if not r.get("deleted_at")
    }
    if codigos:
        ids |= {
            str(r["atendimento_id"])
            for r in table_reads.in_batched_rows(
                client, NEGOCIACAO, org_id, "imovel_codigo", sorted(codigos),
                select="atendimento_id", order_col="atendimento_id",
            )
        }
    return sorted(ids)


def ao_vincular_conjuge(
    client: Any,
    org_id: Any,
    cliente_a: Any,
    cliente_b: Any,
    *,
    actor: Any = None,
    agendador: Optional[Agendador] = None,
    check_credentials: Optional[Callable[[str], list[str]]] = None,
) -> list[dict]:
    """§7.1 late-spouse hook: a cônjuge was linked to someone — for every
    atendimento where either is a seller AND the proposta is `aceita`, run
    `disparar`. NEVER raises (the link already landed) and is a logged no-op
    while `atendimento_propostas` does not exist. Returns
    `[{atendimento_id, pos_aceite|erro}]` for the atendimentos it touched."""
    org = _uuid(org_id)
    afetados: list[dict] = []
    try:
        candidatos = _atendimentos_dos_conjuges(client, org, [str(cliente_a), str(cliente_b)])
    except Exception as exc:  # noqa: BLE001 - the link landed; log, never raise
        logger.error("pos-aceite: hook de cônjuge falhou ao localizar atendimentos: %s", exc, exc_info=True)
        return afetados
    for atendimento_id in candidatos:
        if _proposta_aceita(client, org, atendimento_id) is None:
            continue
        try:
            pos = disparar(
                client, org, atendimento_id, actor,
                agendador=agendador, check_credentials=check_credentials,
            )
            afetados.append({"atendimento_id": atendimento_id, "pos_aceite": pos})
        except Exception as exc:  # noqa: BLE001 - the link landed; log, never raise
            logger.error("pos-aceite: hook de cônjuge falhou em %s: %s", atendimento_id, exc, exc_info=True)
            afetados.append({"atendimento_id": atendimento_id, "erro": str(exc)})
    return afetados


__all__ = [
    "Agendador", "CertidaoPosAceite", "MatriculaPosAceite", "PosAceite",
    "agendador_em_background", "agendador_padrao", "ao_vincular_conjuge", "configurar", "disparar",
    "vendedores",
]
